"""
Dung DONG LENH FFmpeg cho mot lan render — va khong chay gi o day.

TACH RIENG co chu dich: dung tham so la phan de sai nhat va de kiem nhat cua
ca tinh nang, con chay tien trinh thi nguoc lai. De chung mot cho thi muon
kiem mot bieu do loc phai co FFmpeg that, mot tep video that, va vai giay —
nen trong thuc te no se khong duoc kiem.

BA LUAT KHONG DUOC PHA:

1. **Khong bao gio noi chuoi cua nguoi dung vao dong lenh.** Ham nay tra ve
   `List[str]` va chi duoc goi qua `subprocess.run(argv)` — khong
   `shell=True`, khong f-string vao mot chuoi lenh. Ten tep do nguoi dung
   dat co the chua `;`, `&&`, `$(...)`; voi mang tham so thi chung chi la
   ky tu trong mot doi so.

2. **Moi gia tri so phai qua `video_validate` TRUOC.** Ham nay tin rang so
   da sach; no khong phai hang rao thu hai.

3. **Duong dan do GOI BEN truyen vao, deu la duong tuyet doi may chu tu
   dung.** Khong nhan duong dan tu thân yeu cau HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from server.video_domain import VideoProject


@dataclass(frozen=True)
class NguonRender:
    """Duong dan CUC BO da tai ve, do tang dich vu chuan bi."""

    video_path: str
    audio_path: str = ""
    subtitle_path: str = ""
    #: Do dai video nguon (giay) — de tinh diem cat khi `video_trim_end` = 0.
    video_duration: float = 0.0


def _loc_am(du_an: VideoProject, co_loi_doc: bool) -> str:
    """Bieu do loc cho phan TIENG.

    Ba truong hop, va ca ba deu co that:

      * chi tieng goc (chua chon loi doc);
      * chi loi doc (da tat tieng goc);
      * tron ca hai.

    `adelay` nhan MILI-giay va can mot gia tri cho MOI kenh (`|`), neu khong
    chi kenh trai bi tre — mot loi rat de bo sot vi tai nguoi chi nghe thay
    "hoi la" chu khong thay "hong".
    """
    tieng_goc = not du_an.mute_original_audio
    phan: List[str] = []

    if tieng_goc:
        phan.append(f"[0:a]volume={du_an.video_volume:.4f}[va]")
    if co_loi_doc:
        # Lech AM = loi doc bat dau truoc video -> cat bot dau loi doc thay vi
        # day video di, vi day video se lam lech ca hinh.
        if du_an.audio_offset >= 0:
            ms = int(round(du_an.audio_offset * 1000))
            phan.append(
                f"[1:a]volume={du_an.audio_volume:.4f},"
                f"adelay={ms}|{ms}[na]")
        else:
            phan.append(
                f"[1:a]volume={du_an.audio_volume:.4f},"
                f"atrim=start={abs(du_an.audio_offset):.4f},"
                f"asetpts=PTS-STARTPTS[na]")

    if tieng_goc and co_loi_doc:
        # `dropout_transition=0` + `normalize=0`: mac dinh cua `amix` HA am
        # luong khi mot nguon ket thuc, nen loi doc se to dan len o doan
        # cuoi video mot cach kho hieu. Ta da dat am luong tuong minh roi.
        phan.append("[va][na]amix=inputs=2:duration=longest"
                    ":dropout_transition=0:normalize=0[aout]")
    elif tieng_goc:
        phan.append("[va]anull[aout]")
    elif co_loi_doc:
        phan.append("[na]anull[aout]")
    return ";".join(phan)


def _thoat_duong_dan_phu_de(duong: str) -> str:
    """Thoat duong dan cho bo loc `subtitles=`.

    Day la cho DUY NHAT trong ca tep ma mot duong dan bi nhung vao mot chuoi
    — vi `-vf subtitles=...` la mot NGON NGU LOC, khong phai mot doi so binh
    thuong. Tren Windows `C:\\x` co ca dau hai cham lan gach cheo nguoc, va
    ca hai deu la ky tu dac biet cua ngon ngu do.

    Van KHONG phai shell: chuoi nay di vao MOT phan tu cua `argv`, nen
    `;`/`&&` trong ten tep khong the thoat ra thanh lenh. Thu can chan o day
    la lam hong CU PHAP BO LOC, khong phai chiem quyen thuc thi.
    """
    return (duong.replace("\\", "/")
                 .replace(":", "\\:")
                 .replace("'", "\\'")
                 .replace("[", "\\[")
                 .replace("]", "\\]")
                 .replace(",", "\\,"))


def dung_dong_lenh(du_an: VideoProject, nguon: NguonRender, *,
                   dich: str, ffmpeg: str = "ffmpeg") -> List[str]:
    """Tra ve `argv` day du cho mot lan render.

    Thu tu dau vao la HOP DONG: `0:` luon la video, `1:` luon la loi doc
    (neu co). Bieu do loc o `_loc_am` dua vao dieu do.
    """
    argv: List[str] = [ffmpeg, "-hide_banner", "-nostdin", "-y"]

    # Cat video: `-ss`/`-to` dat TRUOC `-i` de FFmpeg tua o muc goi, nhanh
    # hon nhieu so voi giai ma tu dau roi vut bo.
    if du_an.video_trim_start > 0:
        argv += ["-ss", f"{du_an.video_trim_start:.4f}"]
    if du_an.video_trim_end > 0:
        argv += ["-to", f"{du_an.video_trim_end:.4f}"]
    argv += ["-i", nguon.video_path]

    co_loi_doc = bool(nguon.audio_path and du_an.audio_track_id)
    if co_loi_doc:
        argv += ["-i", nguon.audio_path]

    loc_am = _loc_am(du_an, co_loi_doc)
    if loc_am:
        argv += ["-filter_complex", loc_am, "-map", "0:v:0", "-map", "[aout]"]
    else:
        # Tat tieng goc va khong co loi doc = mot tep CHI HINH. Noi ro bang
        # `-an` thay vi de FFmpeg tu doan.
        argv += ["-map", "0:v:0", "-an"]

    if nguon.subtitle_path:
        argv += ["-vf", f"subtitles={_thoat_duong_dan_phu_de(nguon.subtitle_path)}"]

    argv += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "21",
        # `yuv420p` de QuickTime/Safari/dien thoai doc duoc. Thieu no thi tep
        # van hop le nhung mot so may phat chi hien mot khung den.
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        # `+faststart` dua chi muc len dau tep — bat buoc de phat duoc trong
        # trinh duyet ma khong phai tai het tep ve truoc.
        "-movflags", "+faststart",
    ]
    argv += [dich]
    return argv


def mo_ta_loi(ma_thoat: int, stderr: str) -> str:
    """Doi mot lan FFmpeg hong thanh cau NGUOI DUNG doc duoc.

    KHONG tra `stderr` tho ra giao dien: no chua duong dan tuyet doi tren may
    chu va toan bo dong lenh. Vua vo nghia voi nguoi dung, vua la ro ri cau
    truc ben trong.
    """
    manh = (stderr or "").lower()
    if "no such file" in manh or "does not exist" in manh:
        return "Không tìm thấy tệp nguồn — thử chọn lại video hoặc audio."
    if "invalid data" in manh or "moov atom not found" in manh:
        return "Tệp video hỏng hoặc không đúng định dạng."
    if "permission denied" in manh:
        return "Không đọc được tệp nguồn."
    if "killed" in manh or ma_thoat in (137, -9):
        return "Bản render bị dừng vì quá nặng — thử cắt ngắn video lại."
    return f"Render thất bại (mã {ma_thoat}). Thử lại hoặc đổi tệp nguồn."
