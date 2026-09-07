"""Dieu kien do dai nguon — cong vao truoc hang doi thuc thi.

Van de that, do duoc (2026-09-07): watcher dang hut ve cac ban tong hop
10-31 gio tu cung nhung kenh RSS truoc day cho ra tung tap le. Do thong luong
ASR do tren may san xuat la **0,96x thoi gian thuc**, mot nguon 10,6 gio ton
~11 gio ASR truoc khi cham toi buoc dich. Lan san xuat thanh cong da chung
minh truoc do dung mot video **102 giay**.

Nen mot nguon qua dai khong phai loi va cung khong phai viec that bai — no
la viec **chua du dieu kien** de chay bang duong day hien tai. Module nay chi
tra loi mot cau: nguon nay co du dieu kien khong, va neu khong thi vi sao.

CHU DICH KHONG lam o day: cat nho video dai. Do la mot muc backlog rieng
(`docs/CONTENT_ORCHESTRATOR.md`), khong phai mot nhanh `if` giau trong ham
nay.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

#: Nguong san xuat mac dinh: 2 gio.
#:
#: Can cu: ASR chay 0,96x thoi gian thuc tren may san xuat, nen 2 gio nguon
#: ~ 2 gio ASR — con nam trong mot lan chay khong nguoi truc. Vuot nguong nay
#: thi mot muc chiem ban tieu thu DUY NHAT ca ngay va lam dung ca hang doi.
DEFAULT_MAX_SOURCE_SECONDS = 2 * 60 * 60

#: Bien moi truong de ha/nang nguong ma khong sua ma.
MAX_SOURCE_SECONDS_ENV = "FAS_MAX_SOURCE_SECONDS"

#: Tien to danh dau MOT muc bi loai vi do dai. Dat o dau `last_error` de ca
#: giao dien quan tri lan mot lan doc bang mat deu phan biet duoc "chua du
#: dieu kien" voi "dang cho" (`CHO:`) va voi "hong" (loi that).
#:
#: Tien to nay la HOP DONG giua watcher, bo danh gia lai, va
#: `content_queue_service._overall`. Doi no phai doi ca ba.
INELIGIBLE_PREFIX = "INELIGIBLE:"


class DurationUnknown(RuntimeError):
    """Khong do duoc do dai.

    FAIL CLOSED: khong biet do dai thi KHONG cho vao hang doi thuc thi. Doan
    la "chac ngan" roi de mot nguon 22 gio lot vao se lam ket ban tieu thu duy
    nhat ca ngay — dat hon nhieu so voi mot lan bo sot phai kiem lai tay.
    """


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reason: str
    duration_seconds: Optional[int]
    max_seconds: int

    def as_last_error(self) -> str:
        """Chuoi ghi vao `last_error` cho mot muc bi loai."""
        return f"{INELIGIBLE_PREFIX} {self.reason}"


def max_source_seconds() -> int:
    """Nguong dang hieu luc. Gia tri xau/am -> quay ve mac dinh thay vi tat
    cong kiem tra: mot bien moi truong danh sai khong duoc mo toang cong."""
    raw = (os.environ.get(MAX_SOURCE_SECONDS_ENV) or "").strip()
    if not raw:
        return DEFAULT_MAX_SOURCE_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_SOURCE_SECONDS
    return value if value > 0 else DEFAULT_MAX_SOURCE_SECONDS


def _hms(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def evaluate(duration_seconds: Optional[int],
             max_seconds: Optional[int] = None) -> Eligibility:
    """Mot nguon co chay duoc bang duong day hien tai khong.

    `duration_seconds is None` nghia la KHONG DO DUOC — va do la mot ket qua
    "khong du dieu kien", khong phai mot ly do de cho qua.
    """
    cap = max_source_seconds() if max_seconds is None else max_seconds

    if duration_seconds is None:
        return Eligibility(
            False,
            f"khong do duoc do dai nguon (nguong {_hms(cap)}) — fail closed",
            None, cap)
    if duration_seconds <= 0:
        return Eligibility(
            False,
            f"do dai nguon bao ve {duration_seconds}s, khong tin duoc "
            f"(nguong {_hms(cap)})",
            int(duration_seconds), cap)
    if duration_seconds > cap:
        return Eligibility(
            False,
            f"nguon dai {_hms(duration_seconds)} > nguong {_hms(cap)}; "
            f"cat nho video dai la muc backlog rieng, chua trien khai",
            int(duration_seconds), cap)
    return Eligibility(
        True, f"nguon dai {_hms(duration_seconds)} <= nguong {_hms(cap)}",
        int(duration_seconds), cap)


def evaluate_unavailable(max_seconds: Optional[int] = None) -> Eligibility:
    """Nguon KHONG CON TON TAI (bi go, rieng tu, hoac chan theo vung).

    Tach khoi "khong do duoc do dai" mot cach co chu dich: ca hai deu loai
    muc ra, nhung chung KHAC NHAU ve tuong lai. Mot video khong do duoc co the
    do duoc o lan chay sau; mot video da bi go thi khong bao gio. Gop chung
    lai se lam nguoi van hanh di tim mot loi cong cu khong ton tai.
    """
    cap = max_source_seconds() if max_seconds is None else max_seconds
    return Eligibility(
        False,
        "nguon khong con truy cap duoc (da go / rieng tu / chan theo vung) — "
        "khong phai loi do do dai",
        None, cap)


def is_ineligible_marker(last_error: str) -> bool:
    return (last_error or "").startswith(INELIGIBLE_PREFIX)
