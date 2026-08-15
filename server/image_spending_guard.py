"""
Bao ve ngan sach Shared Premium — PHASE 7, overnight build.

DOC LAP voi Pollinations Auto Top-Up (ho tu quan ly phia ho). Day la lop
phong thu RIENG cua Fanfic World: mot loi ung dung/bot spam khong duoc phep
lam Auto Top-Up cham tien khong gioi han o phia Pollinations.

Hanh vi:

    chi tieu binh thuong        -> Shared Premium kha dung
    cham nguong canh bao        -> ghi log/metric cho quan tri thay (KHONG chan)
    cham han muc thang          -> TAT Shared Premium; Quick Free + BYOP van chay

Co cong tac VIEN (kill switch) TAT THU CONG, doc lap voi han muc thang —
dung khi can dung khan cap ma khong doi sang thang sau.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional


class SharedPremiumDisabled(Exception):
    """Shared Premium hien KHONG kha dung — Quick Free/BYOP khong bi anh
    huong. Thong diep o day AN TOAN de hien thi truc tiep."""


@dataclass(frozen=True)
class SpendingSnapshot:
    thang: str  # "YYYY-MM"
    spent_usd: float
    budget_usd: float
    warning_usd: float
    kill_switch_engaged: bool
    active_concurrent: int
    max_concurrent: int

    @property
    def over_budget(self) -> bool:
        return self.spent_usd >= self.budget_usd

    @property
    def over_warning(self) -> bool:
        return self.spent_usd >= self.warning_usd


class SharedPremiumSpendingGuard:
    """Trong bo nho, MOT tien trinh — du cho MVP overnight. San xuat that
    (nhieu tien trinh) can chuyen bo dem sang kho dung chung; ghi ro trong
    tai lieu ban giao (`docs/reports/image-studio-v1-summary.md`)."""

    def __init__(
        self, *, monthly_budget_usd: float, warning_budget_usd: float,
        max_concurrent: int, canh_bao: Optional[Callable[[SpendingSnapshot], None]] = None,
    ) -> None:
        self._budget = monthly_budget_usd
        self._warning = warning_budget_usd
        self._max_concurrent = max_concurrent
        self._canh_bao = canh_bao or (lambda snap: None)
        # RLock, KHONG PHAI Lock: `ket_thuc_request` goi `self.snapshot()`
        # (tu no lock lai) TRONG LUC dang giu khoa — Lock thuong se tu-deadlock
        # o dung tien trinh nay (da bat duoc bang test that, khong phai doan).
        self._lock = threading.RLock()
        self._thang_hien_tai = _thang_nay()
        self._spent_usd = 0.0
        self._active = 0
        self._kill_switch = False
        self._da_canh_bao_thang_nay = False

    # ------------------------------------------------------------- doc

    def snapshot(self) -> SpendingSnapshot:
        with self._lock:
            self._doi_thang_neu_can()
            return SpendingSnapshot(
                thang=self._thang_hien_tai, spent_usd=self._spent_usd,
                budget_usd=self._budget, warning_usd=self._warning,
                kill_switch_engaged=self._kill_switch,
                active_concurrent=self._active, max_concurrent=self._max_concurrent,
            )

    def _doi_thang_neu_can(self) -> None:
        thang_nay = _thang_nay()
        if thang_nay != self._thang_hien_tai:
            self._thang_hien_tai = thang_nay
            self._spent_usd = 0.0
            self._da_canh_bao_thang_nay = False

    # ------------------------------------------------------- vong doi request

    def bat_dau_request(self) -> None:
        """Goi TRUOC khi goi provider — nem `SharedPremiumDisabled` neu het
        han muc/kill switch/qua tai dong thoi. PHAI goi `ket_thuc_request`
        (finally) du thanh cong hay that bai de khong ro ri dem dong thoi."""
        with self._lock:
            self._doi_thang_neu_can()
            if self._kill_switch:
                raise SharedPremiumDisabled(
                    "Fanfic Credits (Shared Premium) đang tạm khoá bởi quản trị — "
                    "Quick Free và My Pollinations vẫn dùng được."
                )
            if self._spent_usd >= self._budget:
                raise SharedPremiumDisabled(
                    "Đã đạt hạn mức chi tiêu tháng này cho Shared Premium — "
                    "Quick Free và My Pollinations vẫn dùng được."
                )
            if self._active >= self._max_concurrent:
                raise SharedPremiumDisabled(
                    "Shared Premium đang quá tải, vui lòng thử lại sau ít phút."
                )
            self._active += 1

    def ket_thuc_request(self, *, actual_cost_usd: float = 0.0) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)
            if actual_cost_usd > 0:
                self._spent_usd += actual_cost_usd
            if self._spent_usd >= self._warning and not self._da_canh_bao_thang_nay:
                self._da_canh_bao_thang_nay = True
                self._canh_bao(self.snapshot())

    # -------------------------------------------------------- quan tri

    def dat_kill_switch(self, engaged: bool) -> None:
        with self._lock:
            self._kill_switch = engaged


def _thang_nay() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")
