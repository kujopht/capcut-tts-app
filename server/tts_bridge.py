"""
Cau noi giua backend web va pipeline TTS cua desktop.

NGUYEN TAC:
- KHONG sao chep logic TTS. Chunking, provider, phan loai loi... deu goi lai
  code da kiem chung trong `desktop_app`.
- KHONG import GUI. Module nay chi cham toi `desktop_app.providers.*`,
  `desktop_app.text_chunker` va `desktop_app.models` - da xac minh khong keo
  theo PySide6.
- KHONG tu doi sang giong khac khi that bai.
- Ghi file tam roi doi ten (atomic) de khong bao gio de lai file do dang.
"""

from __future__ import annotations

import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Cac import duoi day deu la Python thuan, khong keo theo Qt.
from desktop_app.models import ErrorKind
from desktop_app.providers.base import ProviderError, Voice
from desktop_app.text_chunker import chunk_text, normalize_chunk_size


class TtsBridgeError(Exception):
    """Loi da phan loai tu cau noi TTS."""

    def __init__(self, kind: str, message: str, detail: str = ""):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.detail = detail


_registry_lock = threading.RLock()
_registry: Any = None


def get_registry() -> Any:
    """
    ProviderRegistry dung chung cho backend.

    Tao mot lan roi dung lai: nap catalog kha ton kem (doc Voice.json + danh
    sach giong Edge online).
    """
    global _registry
    with _registry_lock:
        if _registry is None:
            from desktop_app.providers.registry import build_default_registry

            _registry = build_default_registry()
        return _registry


def reset_registry() -> None:
    """Dung trong test."""
    global _registry
    with _registry_lock:
        if _registry is not None:
            try:
                _registry.close()
            except Exception:
                pass
        _registry = None


def list_voices(settings: Any = None) -> List[Dict[str, Any]]:
    """
    Danh sach giong cho giao dien web.

    Giong chay cuc bo (Piper) chua xac minh giay phep se bi ANH DAU
    `commercial_ready=False` va bi loai hoan toan khi khong duoc phep bat.
    """
    registry = get_registry()
    allow_local = True
    if settings is not None:
        allow_local = bool(getattr(settings, "allow_unverified_local_voices", True))

    out: List[Dict[str, Any]] = []
    for voice in registry.voices:
        is_local = voice.provider == "piper"
        if is_local and not allow_local:
            continue
        info = registry.status_of(voice)
        out.append({
            "voice_id": voice.id,
            "provider": voice.provider,
            "provider_label": voice.provider_label,
            "display_name": voice.display_name or voice.engine_voice_id,
            "description": voice.description,
            "language": voice.language,
            "gender": voice.gender,
            "installed": voice.installed,
            "status": info.status.value,
            "status_label": info.status.label,
            "status_reason": info.reason,
            # Giay phep giong cuc bo CHUA duoc xac minh -> khong duoc coi la
            # san sang cho muc dich thuong mai.
            "commercial_ready": not is_local,
        })
    return out


def resolve_voice(voice_id: str) -> Voice:
    voice = get_registry().voice_by_id(voice_id)
    if voice is None:
        raise TtsBridgeError(
            ErrorKind.VOICE_NOT_FOUND.value, f"Không có giọng '{voice_id}'."
        )
    return voice


def _find_ffmpeg() -> Optional[str]:
    from desktop_app.output_manager import find_ffmpeg

    return find_ffmpeg(None)


def _concat_mp3(parts: List[Path], dest: Path) -> int:
    """
    Ghep cac part thanh mot file MP3.

    Mot part thi chi doi ten. Nhieu part thi ghep bang ffmpeg (stream copy).
    Luon ghi ra file tam roi doi ten.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    if len(parts) == 1:
        tmp.write_bytes(parts[0].read_bytes())
    else:
        ffmpeg = _find_ffmpeg()
        if not ffmpeg:
            raise TtsBridgeError(
                ErrorKind.MERGE_FFMPEG_MISSING.value,
                "Cần ffmpeg để ghép nhiều phần audio nhưng không tìm thấy.",
            )
        listing = dest.parent / f"{dest.stem}_concat.txt"
        listing.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8"
        )
        try:
            proc = subprocess.run(
                [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                 "-f", "concat", "-safe", "0", "-i", str(listing),
                 "-c", "copy", "-f", "mp3", str(tmp)],
                capture_output=True, text=True, timeout=600,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TtsBridgeError(
                ErrorKind.MERGE_ERROR.value, f"Không chạy được ffmpeg: {exc}"
            ) from exc
        finally:
            listing.unlink(missing_ok=True)

        if proc.returncode != 0:
            tmp.unlink(missing_ok=True)
            raise TtsBridgeError(
                ErrorKind.MERGE_ERROR.value,
                "ffmpeg không ghép được các phần audio.",
                (proc.stderr or "")[:500],
            )

    size = tmp.stat().st_size
    tmp.replace(dest)          # atomic
    return size


def synthesize_chapter(
    text: str,
    voice_id: str,
    dest: Path,
    rate: str = "1.0",
    chunk_chars: int = 2000,
    on_progress: Optional[Callable[[int, int], None]] = None,
    cancel: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Tao audio cho mot chuong.

    Dung DUNG chunker va provider cua desktop. Khi mot part that bai, toan bo
    job that bai voi loi da phan loai - TUYET DOI khong tu doi sang giong khac.
    """
    if not (text or "").strip():
        raise TtsBridgeError(ErrorKind.EMPTY_TEXT.value, "Nội dung chương đang trống.")

    voice = resolve_voice(voice_id)
    registry = get_registry()

    chunk_chars = normalize_chunk_size(chunk_chars)
    chunks = chunk_text(text, chunk_chars)
    if not chunks:
        raise TtsBridgeError(ErrorKind.EMPTY_TEXT.value, "Không chia được nội dung thành phần nào.")

    work_dir = Path(tempfile.mkdtemp(prefix="fas_web_tts_"))
    part_paths: List[Path] = []
    try:
        for index, chunk in enumerate(chunks, start=1):
            part = work_dir / f"part_{index:03d}.mp3"
            try:
                registry.synthesize(
                    text=chunk, voice=voice, dest=part, cancel=cancel, rate=rate
                )
            except ProviderError as exc:
                raise TtsBridgeError(
                    exc.kind.value,
                    f"Phần {index}/{len(chunks)}: {exc.message}",
                    exc.detail,
                ) from exc
            except Exception as exc:
                raise TtsBridgeError(
                    ErrorKind.UNEXPECTED.value,
                    f"Phần {index}/{len(chunks)}: lỗi ngoài dự kiến: {exc}",
                ) from exc

            part_paths.append(part)
            if on_progress:
                on_progress(index, len(chunks))

        size = _concat_mp3(part_paths, Path(dest))
        return {
            "size_bytes": size,
            "total_parts": len(chunks),
            "voice_id": voice.id,
            "provider": voice.provider,
        }
    finally:
        for part in part_paths:
            part.unlink(missing_ok=True)
        try:
            work_dir.rmdir()
        except OSError:
            pass
