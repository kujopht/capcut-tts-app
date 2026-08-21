"""
PaymentProvider — PHASE 6 (mua Fanfic Credit), overnight build.

Kiem tra rong toan bo repo (server/ va web/) TRUOC khi viet file nay: KHONG
tim thay Stripe/PayOS/cong thanh toan nao da ton tai (chi co hai false
positive — mot dong comment "KHONG mo purchase flow" trong
gamification_domain.py, va truong `credited` khong lien quan trong api.ts).
Vi vay Image Studio KHONG duoc phep tao tai khoan thanh toan production that
— chi trien khai GIAO DIEN + MOT ban mock/test-mode, dung nguyen van yeu cau
PHASE 6 khi chua co payment provider san co.

`MockPaymentProvider` KHONG BAO GIO goi mang, KHONG BAO GIO tinh phi tien
that — no chi mo phong 3 trang thai (thanh cong/that bai/dang xu ly) de UI
checkout co gi de kiem thu ngay ca khi chua noi Stripe/PayOS that.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

from server.domain import new_id, now_iso


class CheckoutStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class CheckoutSession:
    checkout_id: str
    user_id: str
    credit_micro: int
    price_usd_cents: int
    status: CheckoutStatus
    provider_id: str
    created_at: str = field(default_factory=now_iso)
    completed_at: str = ""
    #: KHONG BAO GIO chua thong tin the/tai khoan — chi id phien cua provider.
    provider_reference: str = ""


class PaymentProvider(ABC):
    """Giao dien CHUNG cho moi cong thanh toan — trien khai that (Stripe,
    PayOS, ...) se noi tiep sau, ung dung tren chi biet giao dien nay."""

    provider_id: str

    @abstractmethod
    def tao_checkout(
        self, *, user_id: str, credit_micro: int, price_usd_cents: int,
    ) -> CheckoutSession:
        """Tao mot phien thanh toan — KHONG tru/cong Fanfic Credit o day.
        Credit chi duoc cong SAU KHI `xac_nhan` bao thanh cong that su (vd
        qua webhook cua provider that)."""

    @abstractmethod
    def xac_nhan(self, checkout_id: str) -> CheckoutSession:
        """Kiem tra trang thai HIEN TAI cua mot phien — dung o webhook hoac
        polling, KHONG BAO GIO tin tuong trang thai do client tu bao."""

    @abstractmethod
    def hoan_tien(self, checkout_id: str) -> CheckoutSession:
        """Hoan tien mot giao dich DA thanh cong."""


class MockPaymentProvider(PaymentProvider):
    """CHI dung cho dev/test — mo phong luong checkout, KHONG BAO GIO cham
    tien that. `luon_thanh_cong=True` (mac dinh) de UI happy-path kiem thu
    duoc ngay; dat `False` de mo phong that bai cho UI error-state."""

    provider_id = "mock_test_mode"

    def __init__(self, *, luon_thanh_cong: bool = True) -> None:
        self._luon_thanh_cong = luon_thanh_cong
        self._lock = threading.Lock()
        self._phien: Dict[str, CheckoutSession] = {}

    def tao_checkout(
        self, *, user_id: str, credit_micro: int, price_usd_cents: int,
    ) -> CheckoutSession:
        with self._lock:
            phien = CheckoutSession(
                checkout_id=new_id("chk"), user_id=user_id,
                credit_micro=credit_micro, price_usd_cents=price_usd_cents,
                status=CheckoutStatus.PENDING, provider_id=self.provider_id,
                provider_reference=f"mock-ref-{new_id('x')[:8]}",
            )
            self._phien[phien.checkout_id] = phien
            return phien

    def xac_nhan(self, checkout_id: str) -> CheckoutSession:
        with self._lock:
            phien = self._phien.get(checkout_id)
            if phien is None:
                raise KeyError(f"Không có phiên checkout {checkout_id!r}.")
            if phien.status != CheckoutStatus.PENDING:
                return phien
            trang_thai = (
                CheckoutStatus.SUCCEEDED if self._luon_thanh_cong
                else CheckoutStatus.FAILED
            )
            moi = CheckoutSession(
                **{**phien.__dict__, "status": trang_thai, "completed_at": now_iso()}
            )
            self._phien[checkout_id] = moi
            return moi

    def hoan_tien(self, checkout_id: str) -> CheckoutSession:
        with self._lock:
            phien = self._phien.get(checkout_id)
            if phien is None:
                raise KeyError(f"Không có phiên checkout {checkout_id!r}.")
            if phien.status != CheckoutStatus.SUCCEEDED:
                raise ValueError(
                    "Chỉ hoàn tiền được phiên đã SUCCEEDED, hiện tại là "
                    f"{phien.status.value!r}."
                )
            moi = CheckoutSession(**{**phien.__dict__, "status": CheckoutStatus.FAILED})
            self._phien[checkout_id] = moi
            return moi
