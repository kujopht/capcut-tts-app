"""
Pipeline tao audio cho mot arc da hoan tat — dung cho ban headless/CLI.

Module nay KHONG sao chep logic TTS. No dung dung nhung thanh phan ma giao dien
dang dung:

    desktop_app.text_importer   - doc ban thao (.txt/.md/.docx)
    desktop_app.text_chunker    - chia van ban dai (qua build_jobs)
    desktop_app.queue_manager   - vong lap part, checkpoint, ghep MP3
    desktop_app.providers.*     - dinh tuyen toi CapCut / Edge / Piper

Nho vay CLI va GUI luon cho ra ket qua giong nhau, va sua provider mot lan la ca
hai duong deu duoc sua.

Bao dam quan trong:
- CHI tao audio khi manifest ghi ro `status: finalized`.
- KHONG BAO GIO tu dong doi sang giong khac khi giong duoc chon that bai:
  bao loi ro rang va tra ve ma loi khac 0.
- Ghi file tam roi doi ten (atomic) — audio tot dang co khong bao gio bi hong
  vi mot lan chay that bai.
- Chay lai voi cung noi dung + giong + thiet lap thi KHONG tao lai.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from desktop_app import APP_NAME, APP_VERSION
from desktop_app.arc_manifest import (
    AUDIO_COMPLETED,
    AUDIO_FAILED,
    AUDIO_RUNNING,
    DEFAULT_VOICE_ID,
    ArcAudioStatus,
    ArcManifest,
    arc_work_dir,
    audio_relative_path,
    safe_name_component,
)
from desktop_app.models import ErrorKind, JobState, content_hash
from desktop_app.providers.base import Voice, provider_label

# -----------------------------------------------------------------------------
# Ma tra ve cua tien trinh
# -----------------------------------------------------------------------------

EXIT_OK = 0
EXIT_ERROR = 1              # loi ngoai du kien
EXIT_USAGE = 2              # sai cu phap dong lenh (argparse dung san ma nay)
EXIT_MANIFEST = 3           # thieu manifest / manifest khong hop le
EXIT_NOT_FINALIZED = 4      # arc chua duoc danh dau hoan tat
EXIT_MANUSCRIPT = 5         # khong doc duoc ban thao / ban thao da doi
EXIT_VOICE = 6              # khong tim ra giong, hoac giong chua san sang
EXIT_SYNTHESIS = 7          # provider tao audio that bai
EXIT_OUTPUT = 8             # khong ghi duoc file ket qua

#: Y nghia tieng Viet cua tung ma — in ra khi loi de nguoi dung/Claude hieu ngay.
EXIT_LABELS: Dict[int, str] = {
    EXIT_OK: "thành công",
    EXIT_ERROR: "lỗi ngoài dự kiến",
    EXIT_USAGE: "sai cú pháp dòng lệnh",
    EXIT_MANIFEST: "manifest thiếu hoặc không hợp lệ",
    EXIT_NOT_FINALIZED: "arc chưa được đánh dấu hoàn tất",
    EXIT_MANUSCRIPT: "không đọc được bản thảo hoặc bản thảo đã thay đổi",
    EXIT_VOICE: "không dùng được giọng đã chọn",
    EXIT_SYNTHESIS: "tạo audio thất bại",
    EXIT_OUTPUT: "không ghi được file kết quả",
}

#: Trang thai ket qua cua mot lan chay `generate-arc`
RESULT_COMPLETED = "completed"
RESULT_SKIPPED = "skipped"       # da co ban dung roi (idempotent)
RESULT_FAILED = "failed"


class ArcError(Exception):
    """
    Loi da phan loai, kem ma tra ve cua tien trinh va goi y cach xu ly.

    Dung cho cac loi TIEN KIEM TRA (chua he goi provider): thieu manifest, arc
    chua hoan tat, ban thao doi noi dung. Nhung truong hop nay KHONG duoc ghi
    trang thai `failed` vao manifest, vi khong co lan chay nao that su xay ra.
    """

    def __init__(self, exit_code: int, message: str, hint: str = ""):
        super().__init__(message)
        self.exit_code = int(exit_code)
        self.message = message
        self.hint = hint


# -----------------------------------------------------------------------------
# Ket qua mot lan chay
# -----------------------------------------------------------------------------


@dataclass
class ArcAudioOutcome:
    """Ket qua mot lan chay `generate-arc` — du de in bao cao va ghi report."""

    status: str
    exit_code: int
    arc_id: str = ""
    manifest_path: str = ""
    manuscript_path: str = ""
    output_path: Optional[str] = None
    voice_id: str = ""
    voice_label: str = ""
    provider: str = ""
    provider_label: str = ""
    rate: str = ""
    chunk_chars: int = 0
    total_parts: int = 0
    done_parts: int = 0
    size_bytes: int = 0
    duration_seconds: Optional[float] = None
    elapsed_seconds: float = 0.0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    content_sha256: str = ""
    message: str = ""
    error_kind: Optional[str] = None
    error_message: str = ""
    work_dir: Optional[str] = None
    messages: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exit_code == EXIT_OK

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app": {"name": APP_NAME, "version": APP_VERSION},
            "status": self.status,
            "exit_code": self.exit_code,
            "exit_reason": EXIT_LABELS.get(self.exit_code, ""),
            "arc_id": self.arc_id,
            "manifest": self.manifest_path,
            "manuscript": self.manuscript_path,
            "output_path": self.output_path,
            "voice_id": self.voice_id,
            "voice_label": self.voice_label,
            "provider": self.provider,
            "provider_label": self.provider_label,
            "rate": self.rate,
            "chunk_chars": self.chunk_chars,
            "total_parts": self.total_parts,
            "done_parts": self.done_parts,
            "size_bytes": self.size_bytes,
            "duration_seconds": self.duration_seconds,
            "elapsed_seconds": round(float(self.elapsed_seconds or 0.0), 2),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "content_sha256": self.content_sha256,
            "message": self.message,
            "error_kind": self.error_kind,
            "error_message": (self.error_message or "")[:1000],
            "work_dir": self.work_dir,
            "log": list(self.messages),
        }


# -----------------------------------------------------------------------------
# Registry headless
# -----------------------------------------------------------------------------


def build_headless_registry(
    catalog_path: Optional[str] = None,
    device_path: Optional[str] = None,
    ffmpeg_path: Optional[str] = None,
):
    """
    Tao ProviderRegistry cho ban khong co giao dien.

    KHONG import PySide6 va khong doc QSettings: CLI phai chay duoc tren may
    khong cai giao dien va trong moi truong tu dong hoa.
    """
    from desktop_app.providers.registry import build_default_registry
    from desktop_app.tts_service import TtsService
    from desktop_app.voice_catalog import VoiceCatalog

    catalog = None
    try:
        catalog = VoiceCatalog()
        catalog.load(Path(catalog_path) if catalog_path else None)
    except Exception:
        # Thieu Voice.json chi lam mat cac giong CapCut; Edge/Piper van dung duoc.
        catalog = None

    service = TtsService(device_path=device_path) if device_path else None
    return build_default_registry(
        catalog=catalog, service=service, ffmpeg_path=ffmpeg_path, refresh=True
    )


# -----------------------------------------------------------------------------
# Chon giong
# -----------------------------------------------------------------------------


def _describe(voice: Voice) -> str:
    return f"{voice.id} ({voice.label} — {provider_label(voice.provider)})"


def resolve_voice(registry: Any, requested: Optional[str]) -> Voice:
    """
    Tim giong theo chuoi nguoi dung dua vao.

    Thu tu doi chieu, dung lai ngay khi CHAC CHAN:
      1. dung `provider:voice_key` (vi du `piper:ngochuyen`);
      2. dung `voice_key`;
      3. ten hien thi trung khop chinh xac (bo dau, khong phan biet hoa/thuong);
      4. tim gan dung — va CHI nhan khi co dung MOT ket qua.

    Nhieu ket qua thi bao loi kem danh sach de nguoi dung chon lai. Khong co ket
    qua thi bao loi. TUYET DOI khong tu chon giup mot giong "gan giong nhat".
    """
    from desktop_app.models import slugify

    needle = (requested or "").strip() or DEFAULT_VOICE_ID
    voices: List[Voice] = list(getattr(registry, "voices", []) or [])
    if not voices:
        raise ArcError(
            EXIT_VOICE,
            "Không đọc được danh sách giọng nào từ các nguồn TTS.",
            "Kiểm tra Voice.json (giọng CapCut) hoặc cài gói edge-tts / piper-tts.",
        )

    # 1. Dung id day du
    exact = registry.voice_by_id(needle)
    if exact is not None:
        return exact

    # 2. Dung voice_key (chi nhan khi khong nhap nhang giua cac nguon)
    by_key = [v for v in voices if v.voice_key == needle]
    if len(by_key) == 1:
        return by_key[0]
    if len(by_key) > 1:
        raise _ambiguous(needle, by_key)

    # 3. Ten hien thi trung khop chinh xac (bo dau tieng Viet)
    needle_slug = slugify(needle, fallback="")
    by_name = [
        v
        for v in voices
        if (v.display_name or "").strip().lower() == needle.lower()
        or (needle_slug and slugify(v.display_name or "", fallback="") == needle_slug)
    ]
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        raise _ambiguous(needle, by_name)

    # 4. Tim gan dung — chi nhan khi duy nhat
    fuzzy = [v for v in voices if v.matches(needle)]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        raise _ambiguous(needle, fuzzy)

    raise ArcError(
        EXIT_VOICE,
        f"Không tìm thấy giọng nào khớp với '{needle}'.",
        "Chạy lệnh 'list-voices' để xem danh sách giọng và dùng đúng id "
        "(ví dụ: piper:ngochuyen).",
    )


def _ambiguous(needle: str, candidates: List[Voice]) -> ArcError:
    shown = "\n".join(f"  - {_describe(v)}" for v in candidates[:12])
    more = "" if len(candidates) <= 12 else f"\n  ... và {len(candidates) - 12} giọng khác"
    return ArcError(
        EXIT_VOICE,
        f"'{needle}' khớp với {len(candidates)} giọng nên không xác định được giọng nào.",
        f"Hãy dùng id đầy đủ. Các giọng khớp:\n{shown}{more}",
    )


def ensure_voice_ready(registry: Any, voice: Voice) -> None:
    """
    Kiem tra giong da san sang truoc khi chay.

    Chua tai model (Piper) hay chua cai goi phu thuoc (Edge) thi bao loi NGAY va
    dung lai — KHONG BAO GIO lang le doi sang mot giong khac dang san sang.
    """
    if not voice.installed:
        info = registry.status_of(voice)
        raise ArcError(
            EXIT_VOICE,
            f"Giọng '{voice.label}' ({voice.id}) chưa dùng được: "
            f"{info.reason or 'chưa cài đặt'}.",
            "Cài model/gói phụ thuộc cho giọng này rồi chạy lại. "
            "Lệnh này không tự đổi sang giọng khác.",
        )


# -----------------------------------------------------------------------------
# Do thoi luong & ghi file ket qua
# -----------------------------------------------------------------------------

# Hai ham nay da don sang `output_manager` de backend web dung chung (backend
# khong duoc phep import `arc_pipeline` — xem CLAUDE.md). Re-export de giu
# nguyen cho nguoi goi cu (arc_cli, test) va cac cho patch theo duong dan cu.
from desktop_app.output_manager import (  # noqa: E402,F401
    find_ffprobe,
    probe_duration_seconds,
)


def publish_audio(source: Path | str, target: Path | str) -> int:
    """
    Dua file audio da tao vao vi tri chinh thuc mot cach AN TOAN.

    Ghi ra file tam `<ten>.mp3.tmp` NGAY TRONG thu muc dich (cung o dia nen doi
    ten la thao tac atomic), kiem tra kich thuoc, roi moi `os.replace`. Neu buoc
    nao that bai thi file cu van con nguyen ven — mot lan chay loi khong bao gio
    lam hong audio tot dang co.
    """
    source = Path(source)
    target = Path(target)

    if not source.is_file():
        raise ArcError(EXIT_OUTPUT, f"Không tìm thấy file audio vừa tạo: {source}")

    tmp = target.with_name(target.name + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, tmp)
        size = tmp.stat().st_size
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise ArcError(EXIT_OUTPUT, f"Không ghi được file audio: {exc}") from exc

    if size <= 0:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise ArcError(EXIT_OUTPUT, "File audio vừa tạo rỗng (0 byte) nên không được dùng.")

    try:
        os.replace(tmp, target)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise ArcError(EXIT_OUTPUT, f"Không thay thế được file audio đích: {exc}") from exc
    return size


# -----------------------------------------------------------------------------
# Idempotency
# -----------------------------------------------------------------------------


def is_up_to_date(
    audio: ArcAudioStatus,
    content_sha256: str,
    voice_id: str,
    rate: str,
    chunk_chars: int,
    target: Path,
) -> bool:
    """
    Ban audio hien co da dung chua?

    Phai khop TOAN BO: trang thai completed, hash noi dung, id giong, toc do,
    kich thuoc chunk, va file tren dia phai that su ton tai va khong rong.
    Thieu bat ky dieu kien nao thi coi nhu chua co va se tao lai.
    """
    if audio.state != AUDIO_COMPLETED:
        return False
    if not content_sha256 or audio.content_sha256 != content_sha256:
        return False
    if audio.voice_id != voice_id:
        return False
    if (audio.rate or "") != (rate or ""):
        return False
    if int(audio.chunk_chars or 0) != int(chunk_chars):
        return False
    try:
        return target.is_file() and target.stat().st_size > 0
    except OSError:
        return False


# -----------------------------------------------------------------------------
# Chay job qua hang doi dung chung cua ung dung
# -----------------------------------------------------------------------------


def _run_single_job(
    text: str,
    voice: Voice,
    manuscript: Optional[Path],
    arc_id: str,
    work_root: Path,
    rate: str,
    chunk_chars: int,
    ffmpeg_path: Optional[str],
    registry: Any,
    gap_between_parts: float,
    log: Callable[[str], None],
):
    """
    Chay MOT job (arc x giong) qua `QueueManager` — dung hang doi that cua ung
    dung chu khong viet lai vong lap part.

    Tra ve `Job` da chay xong (ke ca khi that bai) de phia goi doc trang thai.
    """
    from desktop_app.models import InputItem, InputKind
    from desktop_app.queue_manager import QueueHooks, QueueManager, build_jobs

    # `name` duoc cat ngan co chu dich: hang doi dung slug cua no lam mot cap thu
    # muc ben duoi goc lam viec, va tong duong dan phai o duoi 260 ky tu cua
    # Windows. Ten arc day du van duoc giu trong manifest.
    item = InputItem(
        name=safe_name_component(arc_id, fallback="arc", max_length=24),
        text=text,
        kind=InputKind.FILE if manuscript else InputKind.TEXT,
        path=str(manuscript) if manuscript else None,
    )
    jobs = build_jobs([item], [voice], chunk_chars, rate)
    if not jobs:
        raise ArcError(
            EXIT_MANUSCRIPT,
            "Bản thảo không tạo được phần nào để đọc (nội dung rỗng sau khi chuẩn hoá).",
        )
    job = jobs[0]

    last_message = {"text": ""}

    def on_job_updated(updated) -> None:
        # Chi bao khi thong diep doi, tranh in lap lai hang tram dong giong nhau
        if updated.message and updated.message != last_message["text"]:
            last_message["text"] = updated.message
            log(f"  {updated.message}")

    queue = QueueManager(
        outputs_root=work_root,
        hooks=QueueHooks(
            job_updated=on_job_updated,
            message=lambda level, text: log(f"  [{level}] {text}"),
        ),
        workers=1,
        ffmpeg_path=ffmpeg_path or "",
        gap_between_jobs=0.0,
        gap_between_parts=float(gap_between_parts),
        registry_factory=lambda: registry,
    )
    queue.set_jobs([job])
    queue.output_manager.create_run()

    log(
        f"Đang tạo audio: {job.total_parts} phần "
        f"(mỗi phần tối đa {chunk_chars} ký tự) · giọng {voice.label}"
    )
    if not queue.start(run_dir=queue.output_manager.run_dir):
        raise ArcError(EXIT_SYNTHESIS, "Không khởi động được hàng đợi tạo audio.")
    queue.wait()
    return job


# -----------------------------------------------------------------------------
# Ham chinh
# -----------------------------------------------------------------------------


def _noop_log(_message: str) -> None:
    return None


def generate_arc_audio(
    manifest: ArcManifest,
    output_dir: Optional[Path | str] = None,
    voice_query: Optional[str] = None,
    rate: Optional[str] = None,
    chunk_chars: Optional[int] = None,
    ffmpeg_path: Optional[str] = None,
    device_path: Optional[str] = None,
    catalog_path: Optional[str] = None,
    registry: Optional[Any] = None,
    force: bool = False,
    keep_work: bool = False,
    work_dir: Optional[Path | str] = None,
    gap_between_parts: Optional[float] = None,
    log: Callable[[str], None] = _noop_log,
) -> ArcAudioOutcome:
    """
    Tao audio cho mot arc DA HOAN TAT.

    Nem `ArcError` cho cac loi tien kiem tra (arc chua hoan tat, ban thao doi
    noi dung...) — nhung truong hop do khong ghi gi vao manifest.

    Cac that bai THUC SU trong luc chay (khong dung duoc giong, provider loi,
    khong ghi duoc file) duoc ghi `state: failed` vao manifest va tra ve
    `ArcAudioOutcome` co `exit_code` khac 0.
    """
    from desktop_app.text_chunker import normalize_chunk_size
    from desktop_app.text_importer import import_file

    collected: List[str] = []

    def emit(message: str) -> None:
        collected.append(message)
        log(message)

    # -- 1. Trang thai hoan tat phai TUONG MINH -------------------------------
    if not manifest.is_finalized:
        raise ArcError(
            EXIT_NOT_FINALIZED,
            f"Arc '{manifest.arc_id}' đang ở trạng thái '{manifest.status or '(trống)'}', "
            "không phải 'finalized' — chưa được tạo audio.",
            "Sau khi bạn xác nhận arc đã hoàn tất, hãy chạy 'finalize-arc' rồi chạy lại "
            "lệnh này. Bản nháp và autosave không bao giờ được tự động tạo audio.",
        )

    # -- 2. Doc ban thao -----------------------------------------------------
    manuscript = manifest.manuscript_path()
    item = import_file(manuscript)
    if item.error:
        raise ArcError(
            EXIT_MANUSCRIPT,
            f"Không đọc được bản thảo '{manuscript}': {item.error}",
        )
    text = item.text
    current_hash = content_hash(text)

    # -- 3. Ban thao phai dung ban da duoc xac nhan hoan tat -----------------
    if manifest.content_sha256 and manifest.content_sha256 != current_hash:
        raise ArcError(
            EXIT_MANUSCRIPT,
            f"Bản thảo đã thay đổi sau khi arc '{manifest.arc_id}' được đánh dấu hoàn tất "
            f"(hash trong manifest {manifest.content_sha256[:12]}…, "
            f"hash hiện tại {current_hash[:12]}…).",
            "Nội dung mới chưa được xác nhận là bản cuối. Hãy chạy lại 'finalize-arc' "
            "sau khi bạn xác nhận, rồi chạy lại lệnh này.",
        )

    # -- 4. Thiet lap --------------------------------------------------------
    out_dir = manifest.resolved_output_dir(output_dir)
    effective_rate = (rate or manifest.rate or "1.0").strip() or "1.0"
    effective_chunk = normalize_chunk_size(
        chunk_chars if chunk_chars is not None else manifest.chunk_chars
    )

    owns_registry = registry is None
    if registry is None:
        registry = build_headless_registry(
            catalog_path=catalog_path, device_path=device_path, ffmpeg_path=ffmpeg_path
        )

    try:
        # -- 5. Chon giong (khong bao gio tu doi giong khac) ------------------
        # `fallback_map` phai rong: co che giong thay the chi duoc dung khi
        # nguoi dung cau hinh ro trong giao dien, khong bao gio o che do tu dong.
        registry.fallback_map = {}

        voice = resolve_voice(registry, voice_query or manifest.voice)
        target = out_dir / audio_relative_path(manifest.arc_id, voice.slug)

        outcome = ArcAudioOutcome(
            status=RESULT_FAILED,
            exit_code=EXIT_ERROR,
            arc_id=manifest.arc_id,
            manifest_path=str(manifest.path or ""),
            manuscript_path=str(manuscript),
            output_path=str(target),
            voice_id=voice.id,
            voice_label=voice.label,
            provider=voice.provider,
            provider_label=provider_label(voice.provider),
            rate=effective_rate,
            chunk_chars=effective_chunk,
            content_sha256=current_hash,
        )

        # -- 6. Idempotent: da co ban dung thi khong tao lai ------------------
        if not force and is_up_to_date(
            manifest.audio, current_hash, voice.id, effective_rate, effective_chunk, target
        ):
            try:
                size = target.stat().st_size
            except OSError:
                size = manifest.audio.size_bytes
            emit(
                f"Bỏ qua: audio của arc '{manifest.arc_id}' đã đúng với nội dung, giọng "
                "và thiết lập hiện tại."
            )
            outcome.status = RESULT_SKIPPED
            outcome.exit_code = EXIT_OK
            outcome.size_bytes = size
            outcome.duration_seconds = manifest.audio.duration_seconds
            outcome.total_parts = manifest.audio.total_parts
            outcome.done_parts = manifest.audio.done_parts
            outcome.started_at = manifest.audio.started_at
            outcome.finished_at = manifest.audio.finished_at
            outcome.elapsed_seconds = manifest.audio.elapsed_seconds
            outcome.message = "Đã có bản audio đúng — không tạo lại."
            outcome.messages = collected
            return outcome

        ensure_voice_ready(registry, voice)

        # -- 7. Danh dau dang chay ------------------------------------------
        started_at = datetime.now().isoformat(timespec="seconds")
        started = time.monotonic()

        manifest.archive_audio()
        manifest.audio = ArcAudioStatus(
            state=AUDIO_RUNNING,
            output_path=str(target),
            provider=voice.provider,
            provider_label=provider_label(voice.provider),
            voice_id=voice.id,
            voice_label=voice.label,
            content_sha256=current_hash,
            rate=effective_rate,
            chunk_chars=effective_chunk,
            started_at=started_at,
        )
        manifest.save()
        outcome.started_at = started_at

        work_root = arc_work_dir(manifest.arc_id, voice.id, effective_rate, base=work_dir)
        outcome.work_dir = str(work_root)

        if gap_between_parts is None:
            # Giong cuc bo khong goi mang nen khong can nghi giua cac phan.
            # Giong qua mang thi giu nhip nghi mac dinh de khong bi gioi han tan suat.
            from desktop_app.models import GAP_BETWEEN_PARTS

            gap = 0.0 if voice.is_local else GAP_BETWEEN_PARTS
        else:
            gap = float(gap_between_parts)

        # -- 8. Chay job qua hang doi dung chung ---------------------------
        job = _run_single_job(
            text=text,
            voice=voice,
            manuscript=manuscript if item.path else None,
            arc_id=manifest.arc_id,
            work_root=work_root,
            rate=effective_rate,
            chunk_chars=effective_chunk,
            ffmpeg_path=ffmpeg_path,
            registry=registry,
            gap_between_parts=gap,
            log=log,
        )
        collected.append(f"Hàng đợi kết thúc: {job.state.value} — {job.message}")

        outcome.total_parts = job.total_parts
        outcome.done_parts = job.done_parts
        elapsed = time.monotonic() - started

        # -- 9. Ket qua ----------------------------------------------------
        if job.state != JobState.SUCCESS or not job.full_path:
            reason = job.message or "Không rõ nguyên nhân"
            kind = job.error_kind or ErrorKind.UNEXPECTED.value
            _record_failure(
                manifest, outcome, kind, reason, elapsed,
                exit_code=EXIT_SYNTHESIS,
            )
            emit(f"Tạo audio THẤT BẠI: {reason}")
            if job.done_parts:
                emit(
                    f"Đã giữ {job.done_parts}/{job.total_parts} phần trong {work_root} "
                    "để lần sau tiếp tục."
                )
            emit("File audio cũ (nếu có) KHÔNG bị thay đổi.")
            outcome.messages = collected
            return outcome

        # -- 10. Ghi file ket qua (atomic) ---------------------------------
        try:
            size = publish_audio(job.full_path, target)
        except ArcError as exc:
            _record_failure(
                manifest, outcome, ErrorKind.DISK_ERROR.value, exc.message, elapsed,
                exit_code=exc.exit_code,
            )
            emit(f"Không ghi được file kết quả: {exc.message}")
            outcome.messages = collected
            return outcome

        duration = probe_duration_seconds(target, ffmpeg_path)
        finished_at = datetime.now().isoformat(timespec="seconds")

        manifest.audio.state = AUDIO_COMPLETED
        manifest.audio.output_path = str(target)
        manifest.audio.total_parts = job.total_parts
        manifest.audio.done_parts = job.done_parts
        manifest.audio.size_bytes = size
        manifest.audio.duration_seconds = duration
        manifest.audio.finished_at = finished_at
        manifest.audio.elapsed_seconds = elapsed
        manifest.audio.error_kind = None
        manifest.audio.error_message = ""
        manifest.save()

        outcome.status = RESULT_COMPLETED
        outcome.exit_code = EXIT_OK
        outcome.size_bytes = size
        outcome.duration_seconds = duration
        outcome.finished_at = finished_at
        outcome.elapsed_seconds = elapsed
        outcome.message = f"Đã tạo audio {job.total_parts} phần."

        # Thu muc lam viec chi con gia tri khi that bai (de tiep tuc duoc)
        if not keep_work:
            shutil.rmtree(work_root, ignore_errors=True)

        emit(f"Xong: {target}")
        outcome.messages = collected
        return outcome
    finally:
        if owns_registry:
            try:
                registry.close()
            except Exception:
                pass


def _record_failure(
    manifest: ArcManifest,
    outcome: ArcAudioOutcome,
    error_kind: str,
    error_message: str,
    elapsed: float,
    exit_code: int,
) -> None:
    """Ghi that bai vao manifest va vao ket qua tra ve."""
    finished_at = datetime.now().isoformat(timespec="seconds")

    manifest.audio.state = AUDIO_FAILED
    manifest.audio.done_parts = outcome.done_parts
    manifest.audio.total_parts = outcome.total_parts
    manifest.audio.error_kind = error_kind
    manifest.audio.error_message = error_message
    manifest.audio.finished_at = finished_at
    manifest.audio.elapsed_seconds = elapsed
    # KHONG ghi output_path cho lan that bai: chua co file nao o do.
    manifest.audio.output_path = None
    try:
        manifest.save()
    except Exception:
        pass

    outcome.status = RESULT_FAILED
    outcome.exit_code = exit_code
    outcome.error_kind = error_kind
    outcome.error_message = error_message
    outcome.finished_at = finished_at
    outcome.elapsed_seconds = elapsed
    outcome.message = error_message


# -----------------------------------------------------------------------------
# Ghi report JSON
# -----------------------------------------------------------------------------


def write_report(path: Path | str, data: Dict[str, Any]) -> Optional[str]:
    """Ghi report JSON (file tam roi doi ten). Tra None neu khong ghi duoc."""
    import json

    target = Path(path)
    tmp = target.with_name(target.name + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
            fp.write("\n")
        os.replace(tmp, target)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    return str(target)
