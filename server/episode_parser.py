"""
Doc so tap tu tieu de video YouTube (Phase 5, Trusted Video Sources).

TAT DINH — KHONG dung LLM: cung mot tieu de phai LUON ra cung ket qua, va ket
qua phai GIAI THICH duoc (mot regex khop la mot regex khop, khong phai "mo
hinh nghi vay"). Day la nen tang de `video_classifier.py` tinh diem, va sai o
day se lam sai het pipeline nhap tap.

Ho tro CA hai each viet tieng Viet (co dau/khong dau) VA tieng Anh, khong
phan biet hoa/thuong:
    Tap 12 / Tập 12 / Tập12 / EP 12 / EP12 / Episode 12 / E12 /
    Chương 12 / Chapter 12 / Part 12 / Phần 12
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

#: Tu khoa DAY DU (co "ep"/"episode" cung nhom vi ca hai deu la tu khoa tap).
#: Khong phan biet hoa/thuong (bien `re.IGNORECASE` ap dung o cho bien dich).
_TU_KHOA = (
    r"(?:tập|tap|episode|ep|chương|chuong|chapter|"
    r"phần|phan|part)"
)

#: Tu khoa + tuy chon dau cham/khong gian/dau # + so — khop ca "Tập12" (dinh
#: lien, khong khoang trang) lan "Tap. #12".
_KEYWORD_RE = re.compile(
    rf"(?i)\b{_TU_KHOA}\.?\s*#?\s*(\d{{1,4}})\b"
)

#: Dang "E12" — chi MOT chu cai, RIENG vi qua ngan de nhap chung voi tu khoa
#: day du (de nham voi ky tu dau cua mot tu khac). Yeu cau ranh gioi tu ca
#: hai phia (`\b`) de "E12" trong "SE12x01" (vi du) khong bi bat nham — dang
#: do hiem trong tieu de Animation tieng Viet nen chap nhan duoc.
#: `re.IGNORECASE` BAT BUOC — module nay cam ket "khong phan biet hoa/thuong"
#: (xem docstring dau file); thieu co nay se lam "e12" (thuong) khong khop
#: trong khi "E12" (hoa) khop, mau thuan voi chinh cam ket do (bug tim thay
#: qua fuzz corpus Phase 7).
_BARE_E_RE = re.compile(r"\bE(\d{1,4})\b", re.IGNORECASE)


def parse_episode_number(title: str) -> Optional[int]:
    """
    Tra so tap DAU TIEN doc duoc tu tieu de, hoac `None` neu khong khop mau
    nao ca. Chuan hoa Unicode (NFC) truoc khi khop de cac to hop dau thanh
    tieng Viet go theo nhieu kieu ban phim van khop dung.

    Thu tu uu tien: tu khoa DAY DU truoc (do dac hieu cao — "Tập"/"Episode"
    kho nham vao noi khac), "E12" xet SAU CUNG (do dac hieu thap hon, de bi
    nham voi ma khac trong tieu de).
    """
    text = unicodedata.normalize("NFC", title or "")
    m = _KEYWORD_RE.search(text)
    if m is None:
        m = _BARE_E_RE.search(text)
    if m is None:
        return None
    so = int(m.group(1))
    # Chan gia tri phi ly (vd nham so nam "2024" thanh so tap) — mot bo phim
    # hoat hinh hiem khi vuot 9999 tap.
    return so if 0 < so < 10000 else None
