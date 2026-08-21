"""
Kho vi Fanfic Credit — Image Studio V1 (overnight build).

Theo dung khuon `server/gamification_store.py`: `MockWalletStore` la NGUON SU
THAT cho test va cho `DATA_BACKEND != appwrite`; ban ben vung Appwrite se noi
tiep sau (xem PHASE 9 — production Appwrite dang bi chan, nen chi day GIAO
DIEN o day, chua co `AppwriteWalletStore` that).

SO CAI, KHONG PHAI SO DU CO THE SUA: moi thay doi la MOT giao dich moi
(`WalletTransaction`), khong bao gio UPDATE-IN-PLACE mot con so. So du la TONG
cua so cai, tinh lai luc doc — day la co che chong:
  - tru tien hai lan khi thu lai (idempotency_key chan ghi trung)
  - so du am do dua tren dieu kien (rong lock quanh doc-sua-ghi)
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from server.adapters import NotFoundError
from server.image_domain import (
    GenerationReservation,
    GenerationStatus,
    LedgerEntryType,
    WalletBalance,
    WalletTransaction,
)


class InsufficientBalance(Exception):
    """So du kha dung khong du de giu cho generation nay."""


class DuplicateReservation(Exception):
    """`idempotency_key` da co mot reservation khac — tra ve reservation CU,
    khong tao moi (xem `MockWalletStore.dat_cho`)."""


class InvalidReservationTransition(Exception):
    """Settle/refund/release mot reservation khong con o trang thai RESERVED."""


class MockWalletStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        #: user_id -> danh sach giao dich, THEO THU TU ghi (append-only).
        self._transactions: Dict[str, List[WalletTransaction]] = {}
        #: idempotency_key -> transaction_id — diem chan ghi trung DUY NHAT.
        self._idempotency_index: Dict[str, str] = {}
        #: generation_id -> GenerationReservation (trang thai MOI NHAT).
        self._reservations: Dict[str, GenerationReservation] = {}

    # ============================================================ so du

    def lay_so_du(self, user_id: str) -> WalletBalance:
        """
        `available_micro` = tong so cai (giao dich RESERVE da la mot dong ghi
        AM trong so cai — xem `_ghi_giao_dich` trong `dat_cho` — nen no da
        duoc tru vao day roi, KHONG tru lai lan hai).

        `reserved_micro` CHI la nhan hien thi rieng (bao nhieu trong tong do
        dang bi giu cho generation chua tat toan) — KHONG phai mot khoan tru
        THEM.
        """
        with self._lock:
            giao_dich = self._transactions.get(user_id, [])
            tong = sum(tx.amount_micro for tx in giao_dich)
            reserved = sum(
                r.estimated_cost_micro
                for r in self._reservations.values()
                if r.user_id == user_id and r.status == GenerationStatus.RESERVED
            )
            return WalletBalance(
                user_id=user_id,
                available_micro=tong,
                reserved_micro=reserved,
            )

    def liet_ke_giao_dich(self, user_id: str) -> List[WalletTransaction]:
        with self._lock:
            return list(self._transactions.get(user_id, []))

    def nap_tien_test(
        self, user_id: str, amount_micro: int, *, idempotency_key: str,
        entry_type: LedgerEntryType = LedgerEntryType.TOP_UP,
        note: str = "",
    ) -> WalletTransaction:
        """Nap tien — dung cho seed test/dev VA cho luong thanh toan mock (xem
        `server/image_payment.py::MockPaymentProvider`). `amount_micro` PHAI
        duong; hoan tien that dung `hoan_tien`, khong dung ham nay."""
        if amount_micro <= 0:
            raise ValueError("Nạp tiền phải là số dương.")
        return self._ghi_giao_dich(
            user_id=user_id,
            generation_id="",
            entry_type=entry_type,
            amount_micro=amount_micro,
            idempotency_key=idempotency_key,
            note=note,
        )

    # ==================================================== vong doi reservation

    def dat_cho(
        self,
        *,
        user_id: str,
        generation_id: str,
        mode,
        provider_id: str,
        model: str,
        estimated_cost_micro: int,
        idempotency_key: str,
        pricing_snapshot_version: str = "",
    ) -> GenerationReservation:
        """Giu `estimated_cost_micro` khoi so du kha dung.

        Goi lai VOI CUNG `idempotency_key` (vd nguoi dung bam nut hai lan do
        mang cham) tra ve CHINH reservation da tao — KHONG tru tien lan hai,
        KHONG tao ban ghi moi. Day la yeu cau bat buoc PHASE 5: "Never allow
        double charging on retries".
        """
        with self._lock:
            if idempotency_key in self._idempotency_index:
                r = self._reservations.get(generation_id)
                if r is not None:
                    return r
                raise DuplicateReservation(
                    f"idempotency_key {idempotency_key!r} đã dùng cho một "
                    "generation khác."
                )

            so_du = self.lay_so_du(user_id)
            if so_du.available_micro < estimated_cost_micro:
                raise InsufficientBalance(
                    f"Số dư khả dụng ({so_du.available_micro}) không đủ cho "
                    f"chi phí ước tính ({estimated_cost_micro})."
                )

            self._ghi_giao_dich(
                user_id=user_id,
                generation_id=generation_id,
                entry_type=LedgerEntryType.RESERVE,
                amount_micro=-estimated_cost_micro,
                idempotency_key=idempotency_key,
                note="reserve",
                bo_qua_kiem_tra_am=True,
            )
            reservation = GenerationReservation(
                generation_id=generation_id,
                user_id=user_id,
                mode=mode,
                provider_id=provider_id,
                model=model,
                estimated_cost_micro=estimated_cost_micro,
                status=GenerationStatus.RESERVED,
                idempotency_key=idempotency_key,
                pricing_snapshot_version=pricing_snapshot_version,
            )
            self._reservations[generation_id] = reservation
            return reservation

    def _reservation_dang_giu(self, generation_id: str) -> GenerationReservation:
        r = self._reservations.get(generation_id)
        if r is None:
            raise NotFoundError(f"Không có reservation cho {generation_id!r}.")
        if r.status != GenerationStatus.RESERVED:
            raise InvalidReservationTransition(
                f"Reservation {generation_id!r} đang ở trạng thái "
                f"{r.status.value!r}, không phải RESERVED."
            )
        return r

    def tat_toan(
        self, generation_id: str, *, actual_cost_micro: Optional[int] = None,
    ) -> GenerationReservation:
        """Provider THANH CONG. `actual_cost_micro=None` -> dung dung so da
        giu (khong co gia that tu provider). Neu gia that THAP hon uoc tinh,
        phan chenh lech duoc tra lai ngay (khong giu du hon can thiet)."""
        with self._lock:
            r = self._reservation_dang_giu(generation_id)
            chenh_lech = 0
            if actual_cost_micro is not None and actual_cost_micro < r.estimated_cost_micro:
                chenh_lech = r.estimated_cost_micro - actual_cost_micro
                self._ghi_giao_dich(
                    user_id=r.user_id,
                    generation_id=generation_id,
                    entry_type=LedgerEntryType.SETTLE,
                    amount_micro=chenh_lech,
                    idempotency_key=f"{r.idempotency_key}:settle-diff",
                    note="hoàn phần chênh lệch giá thật thấp hơn ước tính",
                )
            moi = GenerationReservation(
                **{
                    **r.__dict__,
                    "status": GenerationStatus.SUCCEEDED,
                    "actual_cost_micro": (
                        actual_cost_micro
                        if actual_cost_micro is not None
                        else r.estimated_cost_micro
                    ),
                    "settled_at": _now(),
                }
            )
            self._reservations[generation_id] = moi
            return moi

    def hoan_tien(
        self, generation_id: str, *, ly_do: str = "provider thất bại",
    ) -> GenerationReservation:
        """Provider THAT BAI sau khi da goi — tra lai TOAN BO so da giu."""
        with self._lock:
            r = self._reservation_dang_giu(generation_id)
            self._ghi_giao_dich(
                user_id=r.user_id,
                generation_id=generation_id,
                entry_type=LedgerEntryType.REFUND,
                amount_micro=r.estimated_cost_micro,
                idempotency_key=f"{r.idempotency_key}:refund",
                note=ly_do,
            )
            moi = GenerationReservation(
                **{**r.__dict__, "status": GenerationStatus.REFUNDED,
                  "settled_at": _now(), "error_message": ly_do}
            )
            self._reservations[generation_id] = moi
            return moi

    def giai_phong(
        self, generation_id: str, *, ly_do: str = "huỷ trước khi gọi provider",
    ) -> GenerationReservation:
        """Huy CHUA HE goi provider (vd het han muc chia se, nguoi dung huy
        thao tac) — ve mat ke toan giong `hoan_tien` nhung ngu nghia khac
        (RELEASE khong ham y "provider da tinh phi roi hoan lai")."""
        with self._lock:
            r = self._reservation_dang_giu(generation_id)
            self._ghi_giao_dich(
                user_id=r.user_id,
                generation_id=generation_id,
                entry_type=LedgerEntryType.RELEASE,
                amount_micro=r.estimated_cost_micro,
                idempotency_key=f"{r.idempotency_key}:release",
                note=ly_do,
            )
            moi = GenerationReservation(
                **{**r.__dict__, "status": GenerationStatus.REFUNDED,
                  "settled_at": _now(), "error_message": ly_do}
            )
            self._reservations[generation_id] = moi
            return moi

    def lay_reservation(self, generation_id: str) -> Optional[GenerationReservation]:
        with self._lock:
            return self._reservations.get(generation_id)

    # ============================================================ noi bo

    def _ghi_giao_dich(
        self, *, user_id: str, generation_id: str, entry_type: LedgerEntryType,
        amount_micro: int, idempotency_key: str, note: str = "",
        bo_qua_kiem_tra_am: bool = False,
    ) -> WalletTransaction:
        """Diem ghi DUY NHAT — moi duong khac trong class nay deu di qua day,
        nen kiem tra trung idempotency_key CHI can nam o mot cho."""
        if idempotency_key in self._idempotency_index:
            tx_id = self._idempotency_index[idempotency_key]
            for tx in self._transactions.get(user_id, []):
                if tx.transaction_id == tx_id:
                    return tx
        tx = WalletTransaction.moi(
            user_id=user_id, generation_id=generation_id, entry_type=entry_type,
            amount_micro=amount_micro, idempotency_key=idempotency_key, note=note,
        )
        self._transactions.setdefault(user_id, []).append(tx)
        self._idempotency_index[idempotency_key] = tx.transaction_id
        return tx


def _now() -> str:
    from server.domain import now_iso
    return now_iso()
