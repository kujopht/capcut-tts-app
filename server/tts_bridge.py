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

#: Chi MOT job Piper duoc chay tai mot thoi diem trong tien trinh nay.
#: Khong phai RLock: hai job la hai thread khac nhau, khong co de quy.
_PIPER_LOCK = threading.Lock()


class _KhongKhoa:
    """Khoa rong cho cac provider di qua mang — chung khong can xep hang."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


_KHONG_KHOA = _KhongKhoa()


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


#: Provider chay TREN MAY worker chu khong qua mang.
LOCAL_PROVIDER = "piper"


def nghitts_voice_ids() -> frozenset:
    """
    Vu tru cac voice_id thuoc bo NghiTTS, suy ra TU CATALOG chu khong go tay.

    Go tay se lech: them mot giong vao `builtin_catalog.PIPER_BUILTIN` roi quen
    cap nhat cho nay thi giong do vinh vien khong bat duoc, va khong co gi bao.
    """
    from desktop_app.providers.builtin_catalog import piper_builtin_voices

    return frozenset(v.id for v in piper_builtin_voices())


def allowed_local_voice_ids(settings: Any = None) -> frozenset:
    """
    Danh sach TRANG cuoi cung cho giong cuc bo. DUY NHAT mot nguon su that.

    Ca `/api/voices` lan duong tao job deu goi ham nay. Hai cho dung hai dieu
    kien khac nhau la cach sinh ra lo hong kinh dien: giong bi an khoi danh sach
    nhung van submit job duoc.

    HAI VONG LOC, va vong thu hai moi la cai quan trong:
      1. cau hinh `settings.local_voices` (bien `FAS_LOCAL_VOICES`);
      2. GIAO voi vu tru NghiTTS.

    Vong 2 nghia la khong bien moi truong nao mo duoc mot giong cuc bo nam
    ngoai bo NghiTTS — ke ca khi nguoi dung tu tha mot file `.onnx` la vao thu
    muc models. Model la nguoi dung, con thu duoc PHUC VU la quyet dinh cua ma
    nguon.
    """
    if settings is None:
        # Doc cau hinh THAT chu khong lay mac dinh cua lop. Worker goi ham nay
        # khong kem `settings`; neu roi ve mac dinh thi dat `FAS_LOCAL_VOICES=""`
        # se tat giong o `/api/voices` ma worker van chay — hai nua he thong
        # bat dong y nhau, dung cai ma ham nay sinh ra de tranh.
        from server.config import get_settings

        settings = get_settings()
    cau_hinh = tuple(getattr(settings, "local_voices", ()) or ())
    return frozenset(cau_hinh) & nghitts_voice_ids()


def _public_languages(settings: Any = None) -> tuple:
    if settings is None:
        from server.config import get_settings

        settings = get_settings()
    return tuple(getattr(settings, "public_voice_languages", ()) or ())


def language_in_scope(language: str, settings: Any = None) -> bool:
    """
    Ngon ngu nay co nam trong pham vi cua web khong.

    So khop theo TIEN TO: cau hinh "vi" bat duoc "vi-VN". Danh sach rong nghia
    la khong gioi han ngon ngu nao.
    """
    cho_phep = _public_languages(settings)
    if not cho_phep:
        return True
    ma = (language or "").lower()
    return any(ma.startswith(tien_to) for tien_to in cho_phep)


def voice_is_local_allowed(voice_id: str, settings: Any = None) -> bool:
    """
    Rieng dieu kien MODEL CUC BO. Khong xet ngon ngu.

    Tach khoi `voice_is_public` vi hai cau hoi khac nhau va duoc hoi o hai noi
    khac nhau — xem `ensure_voice_runnable`.
    """
    provider = (voice_id or "").split(":", 1)[0]
    if provider != LOCAL_PROVIDER:
        return True
    return voice_id in allowed_local_voice_ids(settings)


def voice_is_public(voice: Any, settings: Any = None) -> bool:
    """
    Giong nay co duoc CHAO BAN tren web khong. Nhan mot doi tuong `Voice`.

    HAI dieu kien, va ca hai deu bat buoc:
      1. ngon ngu nam trong pham vi web (hien tai: chi tieng Viet);
      2. neu la giong cuc bo thi phai nam trong danh sach trang.
    """
    return (language_in_scope(getattr(voice, "language", ""), settings)
            and voice_is_local_allowed(voice.id, settings))


def ensure_voice_public(voice_id: str, settings: Any = None) -> None:
    """
    Chan mot `voice_id` khong duoc chao ban. Dung o MOI endpoint nhan voice_id.

    Phai tra loi qua registry chu khong doan tu tien to: ngon ngu la thuoc tinh
    cua giong, khong doc duoc tu chuoi id. Gui thang mot id nuoc ngoai vao
    `POST /api/jobs` phai bi tu choi — do la ca muc dich cua ham nay.

    TUYET DOI khong tu chon mot giong Viet khac thay the. Bao loi ro rang de
    nguoi dung biet minh vua gui gi.
    """
    voice = get_registry().voice_by_id(voice_id)
    if voice is None:
        raise TtsBridgeError(
            ErrorKind.VOICE_NOT_FOUND.value, f"Không có giọng '{voice_id}'.")
    if not language_in_scope(voice.language, settings):
        raise TtsBridgeError(
            ErrorKind.VOICE_NOT_FOUND.value,
            f"Giọng '{voice_id}' không phải giọng tiếng Việt. "
            "Phiên bản này chỉ hỗ trợ giọng tiếng Việt.",
        )
    if not voice_is_local_allowed(voice_id, settings):
        raise TtsBridgeError(
            ErrorKind.VOICE_NOT_FOUND.value,
            f"Giọng '{voice_id}' hiện không được cung cấp.",
        )


def ensure_voice_runnable(voice_id: str, settings: Any = None) -> None:
    """
    Kiem tra o phia WORKER. CHI xet danh sach trang giong cuc bo.

    KHONG xet ngon ngu, va do la co y. Pham vi ngon ngu la mot quyet dinh SAN
    PHAM ve viec chao ban cai gi hom nay; no duoc cuong che luc TAO job. Mot
    job cu dang nam `pending` tu truoc khi thu hep pham vi van phai chay xong —
    thu hep pham vi khong duoc lam hong du lieu da co.
    """
    if not voice_is_local_allowed(voice_id, settings):
        raise TtsBridgeError(
            ErrorKind.VOICE_NOT_FOUND.value,
            f"Giọng '{voice_id}' hiện không được cung cấp.",
        )


def list_voices(settings: Any = None) -> List[Dict[str, Any]]:
    """
    Danh sach giong cho giao dien web.

    Giong cuc bo chi xuat hien khi nam trong danh sach trang — CUNG ham ma
    `ensure_voice_public()` dung. An khoi danh sach va tu choi tao job luon di
    cung nhau.
    """
    from desktop_app.providers.recommended import RECOMMENDED_CODES, voice_code

    registry = get_registry()
    # Thu tu de xuat lay THANG tu `desktop_app/providers/recommended.py` — do la
    # nguon duy nhat khai bao bay giong nay. Chep lai danh sach sang day la cach
    # chac chan de hai ban lech nhau sau vai thang.
    thu_tu = {ma: i for i, ma in enumerate(RECOMMENDED_CODES)}

    out: List[Dict[str, Any]] = []
    for voice in registry.voices:
        is_local = voice.provider == LOCAL_PROVIDER
        if not voice_is_public(voice, settings):
            continue
        info = registry.status_of(voice)
        vi_tri = thu_tu.get(voice_code(voice))
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
            # Giong nay dang duoc phuc vu nguoi dung hay khong. Truoc day cho
            # nay la `commercial_ready`, mot phan doan ve GIAY PHEP — thu ma ma
            # nguon khong biet va khong nen doan. Day la mot su that ky thuat:
            # no den tu danh sach trang.
            "public_enabled": True,
            # Model nam tren may worker, KHONG nam trong tien trinh nay. Tien
            # trinh web tren Render khong co file `.onnx` nao nen `installed` se
            # la False o do — va dieu do khong noi len gi ve viec giong co dung
            # duoc khong. Giao dien phai doc co nay, khong doc `installed`.
            "runs_on_worker": is_local,
            # Muc "Giọng đề xuất". `recommended_order` giu DUNG thu tu cua app
            # desktop; giao dien sap xep theo no chu khong tu bay ra thu tu
            # rieng. `None` = khong thuoc muc do.
            "recommended": vi_tri is not None,
            "recommended_order": vi_tri,
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

    ensure_voice_runnable(voice_id)
    voice = resolve_voice(voice_id)
    registry = get_registry()

    # MOT job Piper tai mot thoi diem, tren toan tien trinh worker.
    #
    # Piper chay tren CPU va mot doi tuong `PiperVoice` duy nhat duoc dung
    # chung cho moi job (cache theo duong dan `.onnx`). Hai job cung goi
    # `synthesize_wav` tren cung doi tuong do la dieu chua ai chung minh la an
    # toan — piper-tts khong he tuyen bo thread-safe. Va ngay ca khi an toan
    # thi tren mot laptop, chay hai job song song chi lam ca hai cung cham.
    #
    # Khoa o day, o CAP JOB, chu khong o cap tung doan: xen ke cac doan cua hai
    # chuong khac nhau khong nhanh hon, chi lam ca hai cung ve dich muon.
    #
    # An toan voi lease: `_run_job` da khoi dong thread heartbeat TRUOC khi goi
    # ham nay, nen job dang xep hang van gia han lease deu va khong bi worker
    # khac giat mat trong luc cho.
    khoa = _PIPER_LOCK if voice.provider == LOCAL_PROVIDER else _KHONG_KHOA

    chunk_chars = normalize_chunk_size(chunk_chars)
    chunks = chunk_text(text, chunk_chars)
    if not chunks:
        raise TtsBridgeError(ErrorKind.EMPTY_TEXT.value, "Không chia được nội dung thành phần nào.")

    # `with khoa` BAO NGOAI `try/finally`, khong nam trong: don dep tep tam
    # khong can giu khoa, va giu them mot nhip nao cung la chan job Piper ke
    # tiep vo co.
    with khoa:
        return _tong_hop_cac_doan(registry, voice, chunks, dest, rate, cancel,
                                  on_progress)


def _tong_hop_cac_doan(registry, voice, chunks, dest, rate, cancel,
                       on_progress) -> Dict[str, Any]:
    """Tong hop tung doan roi ghep. Tach ra chi de `synthesize_chapter` con doc duoc."""
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
        # Xoa MOI THU trong thu muc lam viec, khong chi nhung part da ghi nhan.
        #
        # `part_paths` chi chua cac part TONG HOP XONG. Provider ghi ra
        # `<ten>.mp3.part` roi moi doi ten, nen mot job bi ngat giua chung —
        # worker bi kill, may sap nguon — de lai mot tep `.part` do dang khong
        # nam trong danh sach do. `rmdir` khi ay nem `OSError` (thu muc khong
        # rong), bi nuot lang le, va CA thu muc o lai vinh vien.
        #
        # Da thay that tren may nay: 6 thu muc `fas_web_tts_*` sot lai, cai
        # lon nhat giu 50 tep part cua mot chuong dai — vai chuc MB rac ma
        # khong co gi bao. Duyet thu muc thi don duoc ca hai loai.
        for con in work_dir.iterdir() if work_dir.exists() else ():
            try:
                con.unlink()
            except OSError:
                # Tep dang bi giu (ffmpeg chua thoat han). Bo qua: `rmdir` ben
                # duoi se that bai va lan chay sau van don duoc.
                continue
        try:
            work_dir.rmdir()
        except OSError:
            pass
