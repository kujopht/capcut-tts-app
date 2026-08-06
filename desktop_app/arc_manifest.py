"""
Manifest cua mot arc: trang thai hoan tat va vong doi cua job audio.

NGUYEN TAC QUAN TRONG NHAT cua module nay: "arc da hoan tat" la mot trang thai
TUONG MINH do nguoi dung xac nhan, KHONG BAO GIO duoc suy dien tu noi dung ban
thao (do dai, co chuong ket, co dong "het arc"...). Chi khi
`status == "finalized"` thi pipeline moi duoc phep tao audio.

Manifest cung la noi ghi lai vong doi cua job audio
(pending / running / completed / failed) kem hash noi dung, nho vay lan chay sau
biet duoc co phai tao lai hay khong (idempotent).

Module nay khong import PySide6, khong goi mang, nen unit test chay hoan toan
offline.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from desktop_app.models import DEFAULT_CHUNK_CHARS, slugify
from desktop_app.text_chunker import normalize_chunk_size

MANIFEST_VERSION = 1

#: Duoi file manifest theo quy uoc: `<ten-arc>.arc.json`
MANIFEST_SUFFIX = ".arc.json"

#: Ten manifest dung chung trong mot thu muc arc (phuong an thay the)
MANIFEST_DIR_NAME = "arc.json"

# -----------------------------------------------------------------------------
# Trang thai arc
# -----------------------------------------------------------------------------

STATUS_DRAFT = "draft"
STATUS_FINALIZED = "finalized"

#: Chi hai gia tri nay hop le. Bat ky gia tri la nao khac deu bi coi la KHONG
#: hoan tat - khong duoc doan y nguoi dung.
ARC_STATUSES = (STATUS_DRAFT, STATUS_FINALIZED)

# -----------------------------------------------------------------------------
# Trang thai audio
# -----------------------------------------------------------------------------

AUDIO_PENDING = "pending"
AUDIO_RUNNING = "running"
AUDIO_COMPLETED = "completed"
AUDIO_FAILED = "failed"

AUDIO_STATES = (AUDIO_PENDING, AUDIO_RUNNING, AUDIO_COMPLETED, AUDIO_FAILED)

# -----------------------------------------------------------------------------
# Mac dinh
# -----------------------------------------------------------------------------

#: Giong mac dinh: Ngoc Huyen chay cuc bo bang Piper.
#: Day CHI la mac dinh khi nguoi dung khong chi dinh giong nao — khong bao gio
#: duoc dung lam giong DU PHONG khi giong nguoi dung chon that bai.
DEFAULT_VOICE_ID = "piper:ngochuyen"

DEFAULT_RATE = "1.0"

#: Thu muc chua audio thanh pham trong thu muc output.
AUDIO_DIR_NAME = "audio"

# -----------------------------------------------------------------------------
# Ten file an toan tren Windows
# -----------------------------------------------------------------------------

#: Ten thiet bi DOS: Windows tu choi tao file mang cac ten nay o BAT KY duoi
#: file nao (CON.mp3 cung khong duoc). `slugify` khong loc chung nen phai chan
#: rieng o day.
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


def safe_name_component(value: str, fallback: str = "arc", max_length: int = 60) -> str:
    """
    Doi mot chuoi bat ky thanh mot thanh phan ten file an toan tren Windows.

    `slugify` da bo dau tieng Viet va chi giu [a-z0-9_], nen khong con ky tu bi
    cam (`< > : " / \\ | ? *`), khong con dau cach hay dau cham o cuoi. O day chi
    can chan them cac ten thiet bi DOS.
    """
    slug = slugify(value, fallback=fallback, max_length=max_length)
    if slug in _WINDOWS_RESERVED:
        return f"{slug}_"
    return slug


def audio_relative_path(arc_id: str, voice_slug: str) -> Path:
    """
    Duong dan audio thanh pham, TUONG DOI so voi thu muc output:

        audio/<arc-id>/<arc-id>_<voice>.mp3

    Cau truc nay on dinh: cung mot arc + cung mot giong luon cho ra dung mot
    duong dan, nho vay lan chay sau nhan ra ket qua cu de bo qua (idempotent).
    """
    arc = safe_name_component(arc_id, fallback="arc")
    voice = safe_name_component(voice_slug, fallback="voice")
    return Path(AUDIO_DIR_NAME) / arc / f"{arc}_{voice}.mp3"


def default_work_root() -> Path:
    """
    Thu muc lam viec tam mac dinh: %LOCALAPPDATA%\\FanficAudioStudio\\arc-work

    KHONG dat trong thu muc output vi hai ly do:
      - thu muc output chi nen chua audio thanh pham, khong lan part_*.mp3;
      - duong dan phai NGAN. Hang doi cua ung dung tu them ba cap thu muc
        (<thoi-diem>/<nguon>/<giong>) ben duoi goc lam viec; neu goc lam viec lai
        nam sau mot duong dan output dai thi tong do dai vuot gioi han 260 ky tu
        cua Windows va toan bo job that bai voi WinError 206.
    """
    from desktop_app.providers.piper_models import user_data_dir

    return user_data_dir() / "arc-work"


def arc_work_dir(
    arc_id: str,
    voice_id: str,
    rate: str = DEFAULT_RATE,
    base: Optional[Path | str] = None,
) -> Path:
    """
    Thu muc lam viec tam cho MOT to hop (arc, giong, toc do).

    Ten thu muc gom phan doc duoc (de con nguoi tim thay) va mot hash ngan cua
    ca ba yeu to. Viec tach rieng tung to hop khong phai de cho dep: co che
    checkpoint-resume dung chung cua ung dung (`find_resume_parts`) doi chieu
    hash noi dung, voice_type va chunk_chars — NHUNG khong doi chieu toc do doc,
    va voice_type cua giong cuc bo (Piper) la chuoi rong. Neu dung chung mot thu
    muc, doi giong hoac doi toc do co the vo tinh nhan lai part cu, tuc la audio
    sai ma khong ai bao. Moi to hop mot thu muc thi chi bao gio thay part cua
    chinh no.

    Ten duoc giu NGAN co chu dich — xem `default_work_root`.
    """
    import hashlib

    root = Path(base) if base else default_work_root()
    digest = hashlib.sha256(
        f"{arc_id}|{voice_id}|{rate}".encode("utf-8")
    ).hexdigest()[:8]
    label = safe_name_component(arc_id, fallback="arc", max_length=16)
    return root / f"{label}_{digest}"


# -----------------------------------------------------------------------------
# Loi
# -----------------------------------------------------------------------------


class ArcManifestError(Exception):
    """Manifest khong doc/ghi duoc hoac khong dung dinh dang."""


# -----------------------------------------------------------------------------
# Trang thai audio trong manifest
# -----------------------------------------------------------------------------


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class ArcAudioStatus:
    """
    Vong doi cua job tao audio cho mot arc.

    `content_sha256` la hash cua ban thao DA THUC SU duoc doc thanh audio — chu
    khong phai hash hien tai cua file. Nho tach hai gia tri nay ma ta biet duoc
    ban thao co thay doi sau khi tao audio hay khong.
    """

    state: str = AUDIO_PENDING
    output_path: Optional[str] = None
    provider: str = ""
    provider_label: str = ""
    voice_id: str = ""
    voice_label: str = ""
    content_sha256: str = ""
    rate: str = DEFAULT_RATE
    chunk_chars: int = DEFAULT_CHUNK_CHARS
    total_parts: int = 0
    done_parts: int = 0
    size_bytes: int = 0
    duration_seconds: Optional[float] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    elapsed_seconds: float = 0.0
    error_kind: Optional[str] = None
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "output_path": self.output_path,
            "provider": self.provider,
            "provider_label": self.provider_label,
            "voice_id": self.voice_id,
            "voice_label": self.voice_label,
            "content_sha256": self.content_sha256,
            "rate": self.rate,
            "chunk_chars": self.chunk_chars,
            "total_parts": self.total_parts,
            "done_parts": self.done_parts,
            "size_bytes": self.size_bytes,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": round(float(self.elapsed_seconds or 0.0), 2),
            "error_kind": self.error_kind,
            "error_message": (self.error_message or "")[:1000],
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "ArcAudioStatus":
        """Doc lai tu JSON. Du lieu la/thieu thi quay ve mac dinh an toan."""
        if not isinstance(raw, dict):
            return cls()
        state = _as_str(raw.get("state"), AUDIO_PENDING).strip().lower()
        if state not in AUDIO_STATES:
            state = AUDIO_PENDING
        return cls(
            state=state,
            output_path=(_as_str(raw.get("output_path")) or None),
            provider=_as_str(raw.get("provider")),
            provider_label=_as_str(raw.get("provider_label")),
            voice_id=_as_str(raw.get("voice_id")),
            voice_label=_as_str(raw.get("voice_label")),
            content_sha256=_as_str(raw.get("content_sha256")),
            rate=_as_str(raw.get("rate"), DEFAULT_RATE) or DEFAULT_RATE,
            chunk_chars=normalize_chunk_size(_as_int(raw.get("chunk_chars"), DEFAULT_CHUNK_CHARS)),
            total_parts=_as_int(raw.get("total_parts")),
            done_parts=_as_int(raw.get("done_parts")),
            size_bytes=_as_int(raw.get("size_bytes")),
            duration_seconds=_as_float(raw.get("duration_seconds")),
            started_at=(_as_str(raw.get("started_at")) or None),
            finished_at=(_as_str(raw.get("finished_at")) or None),
            elapsed_seconds=float(_as_float(raw.get("elapsed_seconds")) or 0.0),
            error_kind=(_as_str(raw.get("error_kind")) or None),
            error_message=_as_str(raw.get("error_message")),
        )


# -----------------------------------------------------------------------------
# Manifest
# -----------------------------------------------------------------------------

#: Cac khoa manifest da biet — khoa la duoc GIU NGUYEN trong `extra` de khong
#: bao gio lam mat du lieu nguoi dung tu them vao.
_KNOWN_KEYS = frozenset(
    {
        "manifest_version",
        "arc_id",
        "title",
        "status",
        "manuscript",
        "content_sha256",
        "finalized_at",
        "voice",
        "output_dir",
        "rate",
        "chunk_chars",
        "audio",
        "history",
    }
)


@dataclass
class ArcManifest:
    """
    Mot arc va trang thai audio cua no.

    `path` la vi tri file manifest tren dia (khong duoc ghi vao JSON). Moi duong
    dan tuong doi trong manifest deu duoc hieu la TUONG DOI SO VOI THU MUC CHUA
    MANIFEST, nho vay ca thu muc arc co the di chuyen ma khong hong.
    """

    arc_id: str
    manuscript: str
    title: str = ""
    status: str = STATUS_DRAFT
    content_sha256: str = ""
    finalized_at: Optional[str] = None
    voice: str = DEFAULT_VOICE_ID
    output_dir: str = ""
    rate: str = DEFAULT_RATE
    chunk_chars: int = DEFAULT_CHUNK_CHARS
    audio: ArcAudioStatus = field(default_factory=ArcAudioStatus)
    history: List[Dict[str, Any]] = field(default_factory=list)
    manifest_version: int = MANIFEST_VERSION
    extra: Dict[str, Any] = field(default_factory=dict)
    path: Optional[Path] = None

    # -- trang thai -----------------------------------------------------------

    @property
    def is_finalized(self) -> bool:
        """
        CHI `status == "finalized"` moi duoc coi la hoan tat.

        Moi gia tri khac (draft, rong, sai chinh ta, thieu khoa) deu la CHUA
        hoan tat — tuyet doi khong suy dien tu noi dung ban thao.
        """
        return (self.status or "").strip().lower() == STATUS_FINALIZED

    @property
    def base_dir(self) -> Path:
        """Thu muc chua manifest — goc de giai cac duong dan tuong doi."""
        if self.path is not None:
            return Path(self.path).resolve().parent
        return Path.cwd()

    def manuscript_path(self) -> Path:
        """Duong dan tuyet doi tuong ung voi `manuscript`."""
        raw = Path(self.manuscript or "")
        if raw.is_absolute():
            return raw
        return (self.base_dir / raw).resolve()

    def resolved_output_dir(self, override: Optional[Path | str] = None) -> Path:
        """
        Thu muc output theo do uu tien: tham so dong lenh -> manifest -> thu muc
        chua manifest.
        """
        if override:
            return Path(override).expanduser().resolve()
        if (self.output_dir or "").strip():
            raw = Path(self.output_dir).expanduser()
            if raw.is_absolute():
                return raw.resolve()
            return (self.base_dir / raw).resolve()
        return self.base_dir

    # -- chuyen doi JSON ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "manifest_version": int(self.manifest_version or MANIFEST_VERSION),
            "arc_id": self.arc_id,
            "title": self.title,
            "status": self.status,
            "manuscript": self.manuscript,
            "content_sha256": self.content_sha256,
            "finalized_at": self.finalized_at,
            "voice": self.voice,
            "output_dir": self.output_dir,
            "rate": self.rate,
            "chunk_chars": int(self.chunk_chars),
            "audio": self.audio.to_dict(),
            "history": list(self.history),
        }
        # Khoa la cua nguoi dung duoc giu lai, nhung khong duoc ghi de khoa that
        for key, value in (self.extra or {}).items():
            if key not in data:
                data[key] = value
        return data

    @classmethod
    def from_dict(cls, raw: Any, path: Optional[Path | str] = None) -> "ArcManifest":
        if not isinstance(raw, dict):
            raise ArcManifestError("Manifest phải là một object JSON.")

        arc_id = _as_str(raw.get("arc_id")).strip()
        manuscript = _as_str(raw.get("manuscript")).strip()
        if not arc_id:
            raise ArcManifestError("Manifest thiếu 'arc_id'.")
        if not manuscript:
            raise ArcManifestError("Manifest thiếu 'manuscript' (đường dẫn bản thảo).")

        status = _as_str(raw.get("status"), STATUS_DRAFT).strip().lower()

        return cls(
            arc_id=arc_id,
            manuscript=manuscript,
            title=_as_str(raw.get("title")),
            # Gia tri la duoc giu nguyen de `arc-status` noi that ra cho nguoi
            # dung thay, nhung `is_finalized` van chi chap nhan "finalized".
            status=status,
            content_sha256=_as_str(raw.get("content_sha256")).strip(),
            finalized_at=(_as_str(raw.get("finalized_at")) or None),
            voice=_as_str(raw.get("voice"), DEFAULT_VOICE_ID).strip() or DEFAULT_VOICE_ID,
            output_dir=_as_str(raw.get("output_dir")),
            rate=_as_str(raw.get("rate"), DEFAULT_RATE).strip() or DEFAULT_RATE,
            chunk_chars=normalize_chunk_size(_as_int(raw.get("chunk_chars"), DEFAULT_CHUNK_CHARS)),
            audio=ArcAudioStatus.from_dict(raw.get("audio")),
            history=[h for h in (raw.get("history") or []) if isinstance(h, dict)],
            manifest_version=_as_int(raw.get("manifest_version"), MANIFEST_VERSION),
            extra={k: v for k, v in raw.items() if k not in _KNOWN_KEYS},
            path=Path(path) if path else None,
        )

    # -- doc / ghi ------------------------------------------------------------

    @classmethod
    def load(cls, path: Path | str) -> "ArcManifest":
        """Doc manifest tu dia. Nem ArcManifestError khi that bai."""
        target = Path(path)
        if not target.is_file():
            raise ArcManifestError(f"Không tìm thấy manifest: {target}")
        try:
            with open(target, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except UnicodeDecodeError as exc:
            raise ArcManifestError(f"Manifest không phải UTF-8: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ArcManifestError(f"Manifest không phải JSON hợp lệ: {exc}") from exc
        except OSError as exc:
            raise ArcManifestError(f"Không đọc được manifest: {exc}") from exc
        return cls.from_dict(data, path=target)

    def save(self, path: Optional[Path | str] = None) -> Path:
        """
        Ghi manifest xuong dia: file tam truoc, roi doi ten (atomic).

        Nho vay manifest cu KHONG bao gio bi cat doi neu tien trinh bi ngat giua
        luc ghi.
        """
        target = Path(path) if path else self.path
        if target is None:
            raise ArcManifestError("Chưa biết ghi manifest vào đâu.")
        target = Path(target)
        tmp = target.with_name(target.name + ".tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump(self.to_dict(), fp, ensure_ascii=False, indent=2)
                fp.write("\n")
            os.replace(tmp, target)
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise ArcManifestError(f"Không ghi được manifest: {exc}") from exc
        self.path = target
        return target

    # -- lich su --------------------------------------------------------------

    def archive_audio(self) -> None:
        """
        Day trang thai audio hien tai vao `history` truoc khi chay lan moi.

        Chi luu lai nhung lan DA CO ket qua (completed/failed) — trang thai
        pending rong khong co gia tri lich su.
        """
        if self.audio.state in (AUDIO_COMPLETED, AUDIO_FAILED):
            self.history.append(self.audio.to_dict())
            # Giu lich su ngan gon, tranh manifest phinh vo han
            if len(self.history) > 20:
                self.history = self.history[-20:]


# -----------------------------------------------------------------------------
# Tim manifest tu duong dan nguoi dung dua vao
# -----------------------------------------------------------------------------


def manifest_path_for(manuscript: Path | str) -> Path:
    """Duong dan manifest theo quy uoc cho mot ban thao: `<ten>.arc.json`."""
    source = Path(manuscript)
    return source.with_name(f"{source.stem}{MANIFEST_SUFFIX}")


def find_manifest(input_path: Path | str) -> Path:
    """
    Tim manifest tu duong dan nguoi dung dua vao `--input`.

    Chap nhan:
      - chinh file manifest (`*.json`);
      - mot file ban thao -> tim `<ten>.arc.json` ben canh;
      - mot thu muc -> tim `arc.json` ben trong.

    KHONG BAO GIO tu tao manifest va khong bao gio coi ban thao khong co manifest
    la "da hoan tat": thieu manifest thi phai bao loi de nguoi dung xac nhan
    tuong minh.
    """
    target = Path(input_path).expanduser()

    if target.is_dir():
        candidate = target / MANIFEST_DIR_NAME
        if candidate.is_file():
            return candidate
        raise ArcManifestError(
            f"Thư mục '{target}' không có {MANIFEST_DIR_NAME}. "
            "Hãy tạo manifest bằng lệnh 'init-arc' rồi đánh dấu hoàn tất bằng "
            "'finalize-arc'."
        )

    if target.suffix.lower() == ".json":
        if target.is_file():
            return target
        raise ArcManifestError(f"Không tìm thấy manifest: {target}")

    sibling = manifest_path_for(target)
    if sibling.is_file():
        return sibling

    if not target.exists():
        raise ArcManifestError(f"Không tìm thấy file: {target}")

    raise ArcManifestError(
        f"Bản thảo '{target.name}' chưa có manifest ({sibling.name}). "
        "Trạng thái hoàn tất phải tường minh — hãy chạy 'init-arc' rồi "
        "'finalize-arc' sau khi bạn xác nhận arc đã xong."
    )
