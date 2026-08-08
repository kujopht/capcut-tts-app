"""
Quan ly thu muc ket qua, manifest/report, checkpoint-resume, ghep MP3 va xuat ZIP.

Cau truc thu muc:

    outputs/
      YYYY-MM-DD_HH-MM-SS/
        ten_input/
          ten_voice/
            part_001.mp3
            part_002.mp3
            ten_input_ten_voice_full.mp3
            manifest.json
        report.json

Khong bao gio ghi de ket qua cua lan chay truoc: moi lan chay la mot thu muc
dau thoi gian rieng (trung giay thi them hau to _2, _3...).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from desktop_app import APP_NAME, APP_VERSION
from desktop_app.models import ErrorKind, Job, JobState, PartState

MANIFEST_NAME = "manifest.json"
REPORT_NAME = "report.json"

#: Vi tri ffmpeg thuong gap tren Windows (chi do khi PATH khong co)
_FFMPEG_HINTS = (
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
)

FFMPEG_HELP = (
    "Chưa tìm thấy ffmpeg nên chưa thể ghép các part thành một file MP3 hoàn "
    "chỉnh. Toàn bộ part_*.mp3 vẫn được giữ nguyên.\n\n"
    "Cách khắc phục:\n"
    "  1) Tải ffmpeg cho Windows tại https://www.gyan.dev/ffmpeg/builds/ "
    "(bản 'release essentials').\n"
    "  2) Giải nén, ví dụ vào C:\\ffmpeg\\bin\\ffmpeg.exe\n"
    "  3) Mở Cài đặt trong app và trỏ 'Đường dẫn ffmpeg' tới file ffmpeg.exe "
    "(hoặc thêm thư mục bin vào PATH rồi mở lại app).\n"
    "  4) Bấm 'Ghép lại' hoặc chạy lại job để tạo file full."
)


def find_ffmpeg(configured: Optional[str] = None) -> Optional[str]:
    """
    Tim ffmpeg theo do uu tien: cau hinh nguoi dung -> PATH -> vi tri thuong gap.
    Tra None neu khong tim thay (KHONG nem exception).
    """
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return str(candidate)
        if candidate.is_dir():
            exe = candidate / "ffmpeg.exe"
            if exe.is_file():
                return str(exe)

    found = shutil.which("ffmpeg")
    if found:
        return found

    for hint in _FFMPEG_HINTS:
        if Path(hint).is_file():
            return hint
    return None


def _unique_dir(parent: Path, name: str) -> Path:
    """Tao thu muc con voi ten duy nhat (them _2, _3... neu da ton tai)."""
    parent.mkdir(parents=True, exist_ok=True)
    candidate = parent / name
    suffix = 2
    while candidate.exists():
        candidate = parent / f"{name}_{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


class OutputManager:
    """Tao thu muc ket qua va ghi manifest/report cho mot lan chay."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.run_dir: Optional[Path] = None
        self.run_started_at: Optional[str] = None
        self._input_dirs: Dict[str, Path] = {}

    # -- tao thu muc ----------------------------------------------------------

    def create_run(self, timestamp: Optional[datetime] = None) -> Path:
        """Tao thu muc cho lan chay moi: outputs/YYYY-MM-DD_HH-MM-SS/"""
        now = timestamp or datetime.now()
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        run_dir = self.root / stamp
        suffix = 2
        while run_dir.exists():
            run_dir = self.root / f"{stamp}_{suffix}"
            suffix += 1
        run_dir.mkdir(parents=True)
        self.run_dir = run_dir
        self.run_started_at = now.isoformat(timespec="seconds")
        self._input_dirs = {}
        return run_dir

    def input_dir(self, input_key: str, input_slug: str) -> Path:
        """
        Thu muc cho mot input. Hai input khac nhau nhung cung slug se duoc tach
        rieng (input_slug_2...) de khong tron file.
        """
        if self.run_dir is None:
            raise RuntimeError("Chưa gọi create_run().")
        existing = self._input_dirs.get(input_key)
        if existing is not None:
            return existing
        created = _unique_dir(self.run_dir, input_slug)
        self._input_dirs[input_key] = created
        return created

    def job_dir(self, job: Job) -> Path:
        """Thu muc <run>/<ten_input>/<ten_voice>/ cho mot job."""
        parent = self.input_dir(job.input_slug + "::" + (job.input_path or job.input_name), job.input_slug)
        voice_dir = parent / job.voice.slug
        suffix = 2
        while voice_dir.exists() and any(voice_dir.iterdir()):
            # cung mot input + cung slug voice (2 voice_type trung ten) -> tach rieng
            voice_dir = parent / f"{job.voice.slug}_{suffix}"
            suffix += 1
        voice_dir.mkdir(parents=True, exist_ok=True)
        return voice_dir

    @staticmethod
    def full_audio_name(job: Job) -> str:
        return f"{job.input_slug}_{job.voice.slug}_full.mp3"

    # -- manifest / report ----------------------------------------------------

    def write_manifest(self, job: Job, extra: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Ghi manifest.json cho job (dong thoi la CHECKPOINT).
        Duoc goi sau moi part thanh cong.
        """
        if not job.job_dir:
            return None
        data = job.to_manifest()
        data["app"] = {"name": APP_NAME, "version": APP_VERSION}
        data["manifest_version"] = 1
        if extra:
            data.update(extra)
        path = Path(job.job_dir) / MANIFEST_NAME
        try:
            tmp = path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
                fp.write("\n")
            tmp.replace(path)
        except OSError:
            return None
        return str(path)

    def write_report(self, jobs: List[Job], stopped: bool = False, blocked_reason: str = "") -> Optional[str]:
        """Ghi report.json tong cho ca lan chay."""
        if self.run_dir is None:
            return None
        report = {
            "app": {"name": APP_NAME, "version": APP_VERSION},
            "run_dir": str(self.run_dir),
            "started_at": self.run_started_at,
            "written_at": datetime.now().isoformat(timespec="seconds"),
            "stopped_by_user": bool(stopped),
            "blocked_reason": blocked_reason,
            "summary": {
                "total": len(jobs),
                "success": sum(1 for j in jobs if j.state == JobState.SUCCESS),
                "partial": sum(1 for j in jobs if j.state == JobState.PARTIAL),
                "failed": sum(1 for j in jobs if j.state == JobState.FAILED),
                "stopped": sum(1 for j in jobs if j.state == JobState.STOPPED),
                "skipped": sum(1 for j in jobs if j.state == JobState.SKIPPED),
                "pending": sum(1 for j in jobs if j.state == JobState.PENDING),
            },
            "jobs": [j.to_manifest() for j in jobs],
        }
        path = self.run_dir / REPORT_NAME
        try:
            tmp = path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump(report, fp, ensure_ascii=False, indent=2)
                fp.write("\n")
            tmp.replace(path)
        except OSError:
            return None
        return str(path)


# -----------------------------------------------------------------------------
# Checkpoint / resume
# -----------------------------------------------------------------------------


def load_manifest(path: Path | str) -> Optional[Dict[str, Any]]:
    try:
        with open(Path(path), "r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def find_resume_parts(
    outputs_root: Path | str,
    content_sha256: str,
    voice_type: str,
    resource_id: str,
    chunk_chars: int,
    total_parts: int,
) -> Dict[int, str]:
    """
    Tim cac part DA THANH CONG cua lan chay truoc cho cung noi dung + cung giong
    + cung kich thuoc chunk. Tra ve {chi_so_part: duong_dan_file}.

    Chi nhan part con ton tai tren dia va co dung luong > 0.
    """
    root = Path(outputs_root)
    if not root.is_dir() or not content_sha256:
        return {}

    best: Dict[int, str] = {}
    try:
        manifests = sorted(root.glob(f"*/*/*/{MANIFEST_NAME}"), reverse=True)
    except OSError:
        return {}

    for manifest_path in manifests:
        data = load_manifest(manifest_path)
        if not data:
            continue
        if data.get("content_sha256") != content_sha256:
            continue
        if str(data.get("voice_type") or "") != str(voice_type):
            continue
        if str(data.get("resource_id") or "") != str(resource_id):
            continue
        try:
            if int(data.get("chunk_chars") or 0) != int(chunk_chars):
                continue
            if int(data.get("total_parts") or 0) != int(total_parts):
                continue
        except (TypeError, ValueError):
            continue

        job_dir = manifest_path.parent
        for part in data.get("parts") or []:
            if not isinstance(part, dict):
                continue
            if part.get("state") != PartState.SUCCESS.value:
                continue
            try:
                index = int(part.get("index"))
            except (TypeError, ValueError):
                continue
            if index in best:
                continue
            candidate = job_dir / str(part.get("file") or f"part_{index:03d}.mp3")
            try:
                if candidate.is_file() and candidate.stat().st_size > 0:
                    best[index] = str(candidate)
            except OSError:
                continue

        if len(best) >= total_parts:
            break

    return best


def adopt_resumed_parts(job: Job, found: Dict[int, str]) -> int:
    """
    Copy cac part da co tu lan chay truoc vao thu muc job hien tai va danh dau
    SUCCESS. Lan chay cu KHONG bi sua/xoa. Tra so part da tiep tuc duoc.
    """
    if not job.job_dir or not found:
        return 0
    adopted = 0
    for part in job.parts:
        source = found.get(part.index)
        if not source:
            continue
        target = Path(job.job_dir) / part.file_name
        try:
            if not target.is_file() or target.stat().st_size == 0:
                shutil.copyfile(source, target)
            size = target.stat().st_size
        except OSError:
            continue
        if size <= 0:
            continue
        part.state = PartState.SUCCESS
        part.file_path = str(target)
        part.file_size = size
        part.error_kind = None
        part.error_message = ""
        adopted += 1
    return adopted


# -----------------------------------------------------------------------------
# Ghep MP3
# -----------------------------------------------------------------------------


class MergeResult:
    def __init__(self, path: Optional[str], note: str = "", error_kind: Optional[str] = None):
        self.path = path
        self.note = note
        self.error_kind = error_kind

    @property
    def ok(self) -> bool:
        return bool(self.path)


def _run_ffmpeg(args: List[str], cwd: Optional[Path] = None) -> Tuple[int, str]:
    """Chay ffmpeg khong hien cua so console. Tra (returncode, stderr_tail)."""
    creation_flags = 0
    if os.name == "nt":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=600,
            creationflags=creation_flags,
        )
    except FileNotFoundError:
        return 127, "Không tìm thấy ffmpeg"
    except subprocess.TimeoutExpired:
        return 124, "ffmpeg quá thời gian (600s)"
    except OSError as exc:
        return 1, f"Không chạy được ffmpeg: {exc}"
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
    return proc.returncode, stderr[-800:]


def merge_job_audio(job: Job, ffmpeg_path: Optional[str] = None) -> MergeResult:
    """
    Ghep cac part thanh mot MP3 hoan chinh, DUNG THU TU part_001, part_002, ...

    - 1 part: chi can copy, khong can ffmpeg.
    - Nhieu part: uu tien ffmpeg (concat -c copy, du phong re-encode).
    - Khong co ffmpeg: giu nguyen part, tra note huong dan, KHONG bao gia la da
      tao duoc file full.
    """
    if not job.job_dir:
        return MergeResult(None, "Job chưa có thư mục kết quả.", ErrorKind.MERGE_ERROR.value)

    job_dir = Path(job.job_dir)
    done = [p for p in sorted(job.parts, key=lambda x: x.index) if p.state == PartState.SUCCESS]
    if not done:
        return MergeResult(None, "Chưa có part nào thành công để ghép.", ErrorKind.MERGE_ERROR.value)

    if len(done) != len(job.parts):
        return MergeResult(
            None,
            f"Chỉ {len(done)}/{len(job.parts)} part thành công nên chưa ghép file full. "
            "Các part đã tạo vẫn được giữ nguyên.",
            ErrorKind.MERGE_ERROR.value,
        )

    target = job_dir / OutputManager.full_audio_name(job)

    # Truong hop 1 part: copy truc tiep, khong phu thuoc ffmpeg
    if len(done) == 1:
        try:
            shutil.copyfile(done[0].file_path, target)
        except OSError as exc:
            return MergeResult(None, f"Không tạo được file full: {exc}", ErrorKind.MERGE_ERROR.value)
        return MergeResult(str(target), "Chỉ có 1 part nên sao chép trực tiếp (không cần ffmpeg).")

    exe = find_ffmpeg(ffmpeg_path)
    if not exe:
        return MergeResult(None, FFMPEG_HELP, ErrorKind.MERGE_FFMPEG_MISSING.value)

    # File danh sach cho concat demuxer (ten file tuong doi, tranh loi dau/khoang trang)
    list_path = job_dir / "_concat_list.txt"
    try:
        with open(list_path, "w", encoding="utf-8") as fp:
            for part in done:
                name = Path(part.file_path).name.replace("'", "'\\''")
                fp.write(f"file '{name}'\n")
    except OSError as exc:
        return MergeResult(None, f"Không ghi được danh sách ghép: {exc}", ErrorKind.MERGE_ERROR.value)

    try:
        code, stderr = _run_ffmpeg(
            [exe, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", list_path.name,
             "-c", "copy", target.name],
            cwd=job_dir,
        )
        if code != 0 or not target.is_file() or target.stat().st_size == 0:
            # Du phong: re-encode (cham hon nhung chac chan hon voi mp3 khac tham so)
            code2, stderr2 = _run_ffmpeg(
                [exe, "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "concat", "-safe", "0", "-i", list_path.name,
                 "-c:a", "libmp3lame", "-b:a", "192k", target.name],
                cwd=job_dir,
            )
            if code2 != 0 or not target.is_file() or target.stat().st_size == 0:
                return MergeResult(
                    None,
                    "ffmpeg không ghép được file. Các part vẫn được giữ nguyên.\n"
                    f"copy: {stderr}\nre-encode: {stderr2}",
                    ErrorKind.MERGE_ERROR.value,
                )
            return MergeResult(str(target), f"Đã ghép {len(done)} part bằng ffmpeg (re-encode).")
        return MergeResult(str(target), f"Đã ghép {len(done)} part bằng ffmpeg (stream copy).")
    except OSError as exc:
        return MergeResult(None, f"Lỗi khi ghép: {exc}", ErrorKind.MERGE_ERROR.value)
    finally:
        try:
            list_path.unlink(missing_ok=True)
        except OSError:
            pass


# -----------------------------------------------------------------------------
# ZIP
# -----------------------------------------------------------------------------


def export_zip(source_dir: Path | str, zip_path: Optional[Path | str] = None) -> str:
    """
    Nen mot thu muc ket qua (ca lan chay hoac mot job) thanh ZIP.
    ZIP duoc dat ben canh thu muc de khong nam trong chinh no.
    """
    source = Path(source_dir)
    if not source.is_dir():
        raise ValueError(f"Không tìm thấy thư mục: {source}")

    if zip_path is None:
        target = source.parent / f"{source.name}.zip"
        suffix = 2
        while target.exists():
            target = source.parent / f"{source.name}_{suffix}.zip"
            suffix += 1
    else:
        target = Path(zip_path)
        target.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() == ".zip":
                continue
            if path.name.endswith(".part") or path.name.endswith(".tmp"):
                continue
            zf.write(path, arcname=str(path.relative_to(source)))
    return str(target)
