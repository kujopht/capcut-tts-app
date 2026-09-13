"""
Kiem tham so mot du an video — HANG RAO DUY NHAT truoc tang render.

`video_render.dung_dong_lenh` TIN rang so da sach. Nghia la moi duong di toi
no phai qua day truoc, va day phai tu choi thay vi sua lang le: mot gia tri
bi "kep" ve khoang hop le se cho ra mot ban render khac cai nguoi dung yeu
cau, va ho khong duoc bao gi.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from server.video_domain import (AM_LUONG_TOI_DA, DAI_TOI_DA, LECH_TOI_DA)


class VideoValidationError(ValueError):
    """Tham so khong hop le. Thong diep danh cho NGUOI DUNG doc."""


#: Duoi MIME cho phep lam video nguon. Danh sach CHO PHEP, khong phai danh
#: sach cam: mot dinh dang la khong doan truoc duoc, va FFmpeg doc duoc rat
#: nhieu thu ma ta khong muon nhan (vd anh dong, luong mang).
MIME_VIDEO = frozenset({
    "video/mp4", "video/quicktime", "video/webm", "video/x-matroska",
})
MIME_PHU_DE = frozenset({
    "text/vtt", "application/x-subrip", "text/plain",
})

#: 200 MB. Duong len hien tai di qua base64 trong than JSON (xem
#: `AuthorizedImportIn` cho cung rang buoc), nen moi byte video thanh ~1.37
#: byte tren duong truyen. Day la mot chot THUC DUNG cho V1, khong phai mot
#: gioi han ky thuat cua dinh dang.
KICH_THUOC_VIDEO_TOI_DA = 200 * 1024 * 1024
KICH_THUOC_PHU_DE_TOI_DA = 2 * 1024 * 1024


def _so(gia_tri: Any, ten: str) -> float:
    if isinstance(gia_tri, bool) or not isinstance(gia_tri, (int, float)):
        raise VideoValidationError(f"{ten} phải là một số.")
    x = float(gia_tri)
    # NaN khong bang chinh no; `inf` lot qua moi phep so sanh khoang.
    if x != x or x in (float("inf"), float("-inf")):
        raise VideoValidationError(f"{ten} không phải một số hợp lệ.")
    return x


def kiem_am_luong(gia_tri: Any, ten: str = "Âm lượng") -> float:
    x = _so(gia_tri, ten)
    if not (0.0 <= x <= AM_LUONG_TOI_DA):
        raise VideoValidationError(
            f"{ten} phải trong khoảng 0–{AM_LUONG_TOI_DA:g}.")
    return x


def kiem_lech(gia_tri: Any) -> float:
    x = _so(gia_tri, "Độ lệch lời đọc")
    if abs(x) > LECH_TOI_DA:
        raise VideoValidationError(
            f"Độ lệch lời đọc phải trong khoảng ±{LECH_TOI_DA:g} giây.")
    return x


def kiem_cat(bat_dau: Any, ket_thuc: Any,
             *, dai_nguon: float = 0.0) -> Tuple[float, float]:
    """Kiem cap (trim_start, trim_end). `ket_thuc == 0` = toi het video."""
    d = _so(bat_dau, "Điểm cắt đầu")
    c = _so(ket_thuc, "Điểm cắt cuối")
    if d < 0 or c < 0:
        raise VideoValidationError("Điểm cắt không được âm.")
    if c > 0 and c <= d:
        raise VideoValidationError("Điểm cắt cuối phải sau điểm cắt đầu.")
    if dai_nguon > 0:
        if d >= dai_nguon:
            raise VideoValidationError(
                "Điểm cắt đầu nằm ngoài độ dài video.")
        # `c > dai_nguon` KHONG phai loi: nguoi dung keo toi cuoi la chuyen
        # binh thuong, va FFmpeg tu dung o cuoi nguon. Kep ve dung do dai.
        if c > dai_nguon:
            c = 0.0
    dai = (c - d) if c > 0 else max(0.0, dai_nguon - d)
    if dai_nguon > 0 and dai > DAI_TOI_DA:
        raise VideoValidationError(
            f"Bản render dài quá {DAI_TOI_DA / 3600:g} giờ — cắt ngắn lại.")
    return d, c


def kiem_mime_video(mime: str, kich_thuoc: int) -> None:
    if (mime or "").split(";")[0].strip().lower() not in MIME_VIDEO:
        raise VideoValidationError(
            "Định dạng video không được hỗ trợ — dùng MP4, MOV, WebM hoặc MKV.")
    if kich_thuoc <= 0:
        raise VideoValidationError("Tệp video rỗng.")
    if kich_thuoc > KICH_THUOC_VIDEO_TOI_DA:
        raise VideoValidationError(
            f"Video vượt quá {KICH_THUOC_VIDEO_TOI_DA // (1024 * 1024)} MB.")


def kiem_mime_phu_de(mime: str, kich_thuoc: int) -> None:
    if (mime or "").split(";")[0].strip().lower() not in MIME_PHU_DE:
        raise VideoValidationError(
            "Phụ đề phải là tệp .srt hoặc .vtt.")
    if kich_thuoc <= 0:
        raise VideoValidationError("Tệp phụ đề rỗng.")
    if kich_thuoc > KICH_THUOC_PHU_DE_TOI_DA:
        raise VideoValidationError("Tệp phụ đề quá lớn.")


def kiem_tieu_de(tieu_de: Any) -> str:
    if not isinstance(tieu_de, str):
        raise VideoValidationError("Tên dự án phải là chữ.")
    t = tieu_de.strip()
    if not t:
        raise VideoValidationError("Dự án cần một cái tên.")
    if len(t) > 120:
        raise VideoValidationError("Tên dự án tối đa 120 ký tự.")
    return t


#: Cac truong NGUOI DUNG duoc sua. Danh sach CHO PHEP: mot ban vá gui thang
#: vao `setattr` se cho phep doi `owner_id` hoac `render_state`.
TRUONG_SUA_DUOC = frozenset({
    "title", "video_asset_id", "audio_track_id", "subtitle_asset_id",
    "video_trim_start", "video_trim_end", "audio_offset",
    "video_volume", "audio_volume", "mute_original_audio",
})


def kiem_ban_va(ban_va: Dict[str, Any], *,
                dai_nguon: float = 0.0) -> Dict[str, Any]:
    """Loc + kiem mot ban va truoc khi ap vao du an.

    Truong la xuat hien thi TU CHOI, khong bo qua im lang: giao dien gui
    nham mot ten truong ma khong ai bao thi loi do song rat lau.
    """
    la = set(ban_va) - TRUONG_SUA_DUOC
    if la:
        raise VideoValidationError(
            f"Không sửa được trường: {', '.join(sorted(la))}.")

    ra: Dict[str, Any] = {}
    if "title" in ban_va:
        ra["title"] = kiem_tieu_de(ban_va["title"])
    for k in ("video_asset_id", "audio_track_id", "subtitle_asset_id"):
        if k in ban_va:
            v = ban_va[k]
            if v is None:
                v = ""
            if not isinstance(v, str) or len(v) > 64:
                raise VideoValidationError(f"{k} không hợp lệ.")
            ra[k] = v
    if "video_volume" in ban_va:
        ra["video_volume"] = kiem_am_luong(ban_va["video_volume"], "Âm lượng video")
    if "audio_volume" in ban_va:
        ra["audio_volume"] = kiem_am_luong(ban_va["audio_volume"], "Âm lượng lời đọc")
    if "audio_offset" in ban_va:
        ra["audio_offset"] = kiem_lech(ban_va["audio_offset"])
    if "mute_original_audio" in ban_va:
        if not isinstance(ban_va["mute_original_audio"], bool):
            raise VideoValidationError("mute_original_audio phải là true/false.")
        ra["mute_original_audio"] = ban_va["mute_original_audio"]
    if "video_trim_start" in ban_va or "video_trim_end" in ban_va:
        d, c = kiem_cat(ban_va.get("video_trim_start", 0.0),
                        ban_va.get("video_trim_end", 0.0),
                        dai_nguon=dai_nguon)
        if "video_trim_start" in ban_va:
            ra["video_trim_start"] = d
        if "video_trim_end" in ban_va:
            ra["video_trim_end"] = c
    return ra
