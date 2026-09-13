"""
Chay render — tang DUY NHAT sinh tien trinh con.

`RenderProvider` la mot giao dien co chu dich: V1 chay FFmpeg ngay tren may
chu web, nhung render la viec nang va dai, va cho no o day mai se lam chet
tien trinh phuc vu HTTP. Giao dien nay de sau nay doi sang mot may rieng
(hoac mot hang doi) ma khong phai sua tang dich vu.

KHONG `shell=True`, khong bao gio. Xem ba luat o dau `video_render.py`.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from server.video_domain import VideoProject
from server.video_render import NguonRender, dung_dong_lenh, mo_ta_loi


@dataclass(frozen=True)
class KetQuaRender:
    thanh_cong: bool
    #: Duong dan CUC BO cua tep ket qua khi thanh cong.
    duong_dan: str = ""
    #: Cau cho NGUOI DUNG doc. Khong bao gio la `stderr` tho.
    loi: str = ""


class RenderProvider(Protocol):
    def render(self, du_an: VideoProject, nguon: NguonRender, *,
               thu_muc_ra: str) -> KetQuaRender: ...


class LocalFfmpegProvider:
    """Chay FFmpeg cua chinh may nay.

    Dung cho phat trien va cho bo kiem. Production nen dung mot provider
    khac — xem ghi chu dau tep.
    """

    def __init__(self, ffmpeg: str = "", han_giay: float = 1800.0) -> None:
        self._ffmpeg = ffmpeg or os.environ.get("FAS_FFMPEG", "ffmpeg")
        self._han = float(han_giay)

    @property
    def san_sang(self) -> bool:
        """May nay co FFmpeg khong.

        Hoi TRUOC khi xep hang thi bao duoc cho nguoi dung ngay, thay vi de
        ho cho mot job chac chan se hong.
        """
        try:
            ra = subprocess.run([self._ffmpeg, "-version"],
                                capture_output=True, timeout=15)
            return ra.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def render(self, du_an: VideoProject, nguon: NguonRender, *,
               thu_muc_ra: str) -> KetQuaRender:
        dich = str(Path(thu_muc_ra) / f"{du_an.project_id}.mp4")
        argv = dung_dong_lenh(du_an, nguon, dich=dich, ffmpeg=self._ffmpeg)
        try:
            ra = subprocess.run(argv, capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                timeout=self._han)
        except subprocess.TimeoutExpired:
            return KetQuaRender(False, loi="Render quá lâu và đã bị dừng.")
        except OSError as exc:
            # FFmpeg khong co tren may — mot loi CAU HINH, khong phai loi cua
            # nguoi dung; noi ro de nguoi van hanh doc log biet ngay.
            return KetQuaRender(
                False, loi="Máy chủ chưa cài FFmpeg nên chưa render được.")
        if ra.returncode != 0:
            return KetQuaRender(False, loi=mo_ta_loi(ra.returncode, ra.stderr))
        if not os.path.exists(dich) or os.path.getsize(dich) == 0:
            # Ma thoat 0 KHONG phai bang chung: FFmpeg co the tra 0 ma khong
            # ghi duoc gi (vd bieu do loc khong noi toi dau ra nao).
            return KetQuaRender(False, loi="Render không tạo ra tệp nào.")
        return KetQuaRender(True, duong_dan=dich)


class KhongCoProvider:
    """Provider MAC DINH khi may khong co FFmpeg.

    Ton tai de he thong noi that thay vi im lang: khong co no thi `render`
    se nem `FileNotFoundError` tu sau trong tang dich vu, va nguoi dung thay
    mot loi 500 khong giai thich duoc.
    """

    san_sang = False

    def render(self, du_an: VideoProject, nguon: NguonRender, *,
               thu_muc_ra: str) -> KetQuaRender:
        return KetQuaRender(
            False, loi="Máy chủ chưa bật dịch vụ render video.")


def provider_mac_dinh() -> RenderProvider:
    p = LocalFfmpegProvider()
    return p if p.san_sang else KhongCoProvider()


def thu_muc_tam() -> str:
    d = Path(tempfile.gettempdir()) / "fanfic_video_render"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)
