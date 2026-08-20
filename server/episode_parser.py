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
from dataclasses import dataclass
from enum import Enum
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


def _khop_mot_tap(text: str) -> Optional[re.Match]:
    """Tim tu khoa+so tap DON LE trong `text` (da chuan hoa NFC) — dung
    chung boi `parse_episode_number` (chi can `so`) VA `parse_episode_span`
    (can ca `m.group(0)` de biet DOAN VAN BAN khop, phuc vu tach ten series
    trong `series_fingerprint.py`). Thu tu uu tien: tu khoa DAY DU truoc (do
    dac hieu cao — "Tập"/"Episode" kho nham vao noi khac), "E12" xet SAU
    CUNG (do dac hieu thap hon, de bi nham voi ma khac trong tieu de)."""
    m = _KEYWORD_RE.search(text)
    if m is None:
        m = _BARE_E_RE.search(text)
    return m


def parse_episode_number(title: str) -> Optional[int]:
    """
    Tra so tap DAU TIEN doc duoc tu tieu de, hoac `None` neu khong khop mau
    nao ca. Chuan hoa Unicode (NFC) truoc khi khop de cac to hop dau thanh
    tieng Viet go theo nhieu kieu ban phim van khop dung.
    """
    text = unicodedata.normalize("NFC", title or "")
    m = _khop_mot_tap(text)
    if m is None:
        return None
    so = int(m.group(1))
    # Chan gia tri phi ly (vd nham so nam "2024" thanh so tap) — mot bo phim
    # hoat hinh hiem khi vuot 9999 tap.
    return so if 0 < so < 10000 else None


#: Dang "Tập 1-13"/"Ep 1-12" — DINH LIEN, khong khoang trang quanh dau gach
#: noi (phan biet voi "Tập 12 - 2024 Remastered", noi dau gach co khoang
#: trang hai ben va la ranh gioi cum tu, khong phai ky hieu dai tap). Chap
#: nhan gach ngang/gach ngang dai/gach em (-, –, —) vi tieu de YouTube tieng
#: Viet hay dung lan lon.
_RANGE_RE = re.compile(
    rf"(?i)\b{_TU_KHOA}\.?\s*#?\s*(\d{{1,4}})[-–—](\d{{1,4}})\b"
)

#: Video "tong hop ca series" (khong danh so tap ro rang, hoac co the co so
#: nhung tu nay la tin hieu manh hon) — "ALL IN ONE" (cum tu, it nham lan),
#: "FULL"/"trọn bộ" (mot tu, RUI RO nham cao hon nhung day la yeu cau ro rang
#: cua dac ta; hau qua cua nham chi la video bi day ve hang doi xem xet thu
#: cong thay vi tu dong nhap — an toan, xem `EpisodeSpanKind.COMPILATION`).
_COMPILATION_RE = re.compile(
    r"(?i)\ball in one\b|\bfull\b|\btrọn bộ\b|\btron bo\b"
)


class EpisodeSpanKind(str, Enum):
    """Video mot tap don le, mot DAI nhieu tap gop trong MOT video, mot ban
    "tong hop ca series", hoac khong doc duoc gi ca."""

    SINGLE = "single"
    RANGE = "range"
    COMPILATION = "compilation"
    UNKNOWN = "unknown"


@dataclass
class EpisodeSpan:
    """
    Dai tap ma MOT video YouTube dai dien — co the la MOT tap (`SINGLE`,
    `start == end`), NHIEU tap gop trong mot video (`RANGE`, vd "Tập 1-13"),
    hoac "tong hop ca series" khong ro so tap (`COMPILATION`).

    Day la representation TUONG MINH de KHONG BAO GIO thu gon mot dai nhieu
    tap thanh "tap dau tien" mot cach am tham — pipeline nhap (Auto-Ingestion
    Phase 1) doc `kind` truoc khi quyet dinh co the tu dong nhap MOT
    `AnimationEpisode` cho video nay hay khong (CHI khi `kind is SINGLE` —
    mot video KHONG the tach thanh nhieu tap ma khong co du lieu thoi diem
    cat canh, ngoai pham vi Phase 1).
    """

    kind: EpisodeSpanKind
    start: Optional[int] = None
    end: Optional[int] = None
    #: Doan van ban khop duoc (de hien tin hieu/go loi) — vd "Tập 1-13".
    raw_text: str = ""

    @property
    def is_single(self) -> bool:
        return self.kind is EpisodeSpanKind.SINGLE

    @property
    def count(self) -> Optional[int]:
        """So tap trong dai, hoac `None` neu khong xac dinh duoc (COMPILATION/
        UNKNOWN, hoac SINGLE/RANGE thieu mot dau)."""
        if self.start is None or self.end is None:
            return None
        return self.end - self.start + 1


def parse_episode_span(title: str) -> Optional[EpisodeSpan]:
    """
    Doc DAI tap tu tieu de — mo rong CO KIEM SOAT cua `parse_episode_number`
    o tren, KHONG thay the: `parse_episode_number` giu nguyen hanh vi (mot so
    duy nhat) cho tuong thich nguoc, con ham nay tra ve representation day du
    hon (`EpisodeSpan`) de goi tu noi CAN phan biet mot-tap/dai-tap/tong-hop.

    Thu tu uu tien: DAI so truoc (dac hieu nhat, vd "Tập 1-13"), roi mot so
    don (dung lai `parse_episode_number`), roi tu khoa "tong hop ca series",
    cuoi cung `None` neu khong khop gi.
    """
    text = unicodedata.normalize("NFC", title or "")

    m = _RANGE_RE.search(text)
    if m is not None:
        dau, cuoi = int(m.group(1)), int(m.group(2))
        if 0 < dau < 10000 and 0 < cuoi < 10000 and cuoi > dau:
            return EpisodeSpan(
                kind=EpisodeSpanKind.RANGE, start=dau, end=cuoi,
                raw_text=m.group(0))
        # DAI vo ly (vd "13-1", hoac mot dau vuot nguong) — roi xuong thu
        # so don, khong tra RANGE sai.

    m_don = _khop_mot_tap(text)
    if m_don is not None:
        so_tap = int(m_don.group(1))
        if 0 < so_tap < 10000:
            return EpisodeSpan(
                kind=EpisodeSpanKind.SINGLE, start=so_tap, end=so_tap,
                raw_text=m_don.group(0))

    m2 = _COMPILATION_RE.search(text)
    if m2 is not None:
        return EpisodeSpan(kind=EpisodeSpanKind.COMPILATION, raw_text=m2.group(0))

    return None
