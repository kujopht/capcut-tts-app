"""Image Studio V1 — `MockWalletStore` (so cai vi Fanfic Credit), kiem truc
tiep, khong qua tang service. Theo khuon `test_gamification_store.py`."""

from __future__ import annotations

import unittest

from server.adapters import NotFoundError
from server.image_domain import GenerationMode, GenerationStatus, LedgerEntryType
from server.image_wallet_store import (
    DuplicateReservation,
    InsufficientBalance,
    InvalidReservationTransition,
    MockWalletStore,
)


class SoDuTest(unittest.TestCase):
    def test_chua_giao_dich_thi_so_du_bang_khong(self):
        store = MockWalletStore()
        so_du = store.lay_so_du("u1")
        self.assertEqual(so_du.available_micro, 0)
        self.assertEqual(so_du.reserved_micro, 0)

    def test_nap_tien_test_tang_so_du_kha_dung(self):
        store = MockWalletStore()
        store.nap_tien_test("u1", 1000, idempotency_key="topup-1")
        self.assertEqual(store.lay_so_du("u1").available_micro, 1000)

    def test_nap_am_bi_tu_choi(self):
        store = MockWalletStore()
        with self.assertRaises(ValueError):
            store.nap_tien_test("u1", -5, idempotency_key="x")


class DatChoTest(unittest.TestCase):
    def test_du_tien_thi_dat_cho_thanh_cong_va_tru_kha_dung(self):
        store = MockWalletStore()
        store.nap_tien_test("u1", 1000, idempotency_key="topup-1")
        r = store.dat_cho(
            user_id="u1", generation_id="gen-1", mode=GenerationMode.SHARED_PREMIUM,
            provider_id="pollinations_shared", model="flux",
            estimated_cost_micro=300, idempotency_key="idem-1",
        )
        self.assertEqual(r.status, GenerationStatus.RESERVED)
        so_du = store.lay_so_du("u1")
        self.assertEqual(so_du.available_micro, 700)
        self.assertEqual(so_du.reserved_micro, 300)

    def test_khong_du_tien_thi_tu_choi_khong_ghi_gi(self):
        store = MockWalletStore()
        store.nap_tien_test("u1", 100, idempotency_key="topup-1")
        with self.assertRaises(InsufficientBalance):
            store.dat_cho(
                user_id="u1", generation_id="gen-1", mode=GenerationMode.SHARED_PREMIUM,
                provider_id="p", model="flux", estimated_cost_micro=300,
                idempotency_key="idem-1",
            )
        self.assertEqual(store.lay_so_du("u1").available_micro, 100)
        self.assertEqual(len(store.liet_ke_giao_dich("u1")), 1)  # chi co topup

    def test_cung_idempotency_key_khong_tru_tien_lan_hai(self):
        """Yeu cau bat buoc PHASE 5: khong tru tien hai lan khi thu lai."""
        store = MockWalletStore()
        store.nap_tien_test("u1", 1000, idempotency_key="topup-1")
        r1 = store.dat_cho(
            user_id="u1", generation_id="gen-1", mode=GenerationMode.SHARED_PREMIUM,
            provider_id="p", model="flux", estimated_cost_micro=300,
            idempotency_key="idem-1",
        )
        r2 = store.dat_cho(
            user_id="u1", generation_id="gen-1", mode=GenerationMode.SHARED_PREMIUM,
            provider_id="p", model="flux", estimated_cost_micro=300,
            idempotency_key="idem-1",
        )
        self.assertEqual(r1.generation_id, r2.generation_id)
        self.assertEqual(store.lay_so_du("u1").available_micro, 700)  # KHONG tru lai
        self.assertEqual(len(store.liet_ke_giao_dich("u1")), 2)  # topup + 1 reserve

    def test_idempotency_key_dung_lai_cho_generation_khac_bi_tu_choi(self):
        store = MockWalletStore()
        store.nap_tien_test("u1", 1000, idempotency_key="topup-1")
        store.dat_cho(
            user_id="u1", generation_id="gen-1", mode=GenerationMode.SHARED_PREMIUM,
            provider_id="p", model="flux", estimated_cost_micro=100,
            idempotency_key="idem-1",
        )
        with self.assertRaises(DuplicateReservation):
            store.dat_cho(
                user_id="u1", generation_id="gen-2", mode=GenerationMode.SHARED_PREMIUM,
                provider_id="p", model="flux", estimated_cost_micro=100,
                idempotency_key="idem-1",
            )


class TatToanVaHoanTienTest(unittest.TestCase):
    def _dat_cho(self, store, **override):
        store.nap_tien_test("u1", 1000, idempotency_key="topup-1")
        params = dict(
            user_id="u1", generation_id="gen-1", mode=GenerationMode.SHARED_PREMIUM,
            provider_id="p", model="flux", estimated_cost_micro=300,
            idempotency_key="idem-1",
        )
        params.update(override)
        return store.dat_cho(**params)

    def test_tat_toan_dung_gia_uoc_tinh_khong_hoan_them(self):
        store = MockWalletStore()
        self._dat_cho(store)
        r = store.tat_toan("gen-1")
        self.assertEqual(r.status, GenerationStatus.SUCCEEDED)
        self.assertEqual(r.actual_cost_micro, 300)
        self.assertEqual(store.lay_so_du("u1").available_micro, 700)
        self.assertEqual(store.lay_so_du("u1").reserved_micro, 0)

    def test_tat_toan_gia_that_thap_hon_thi_hoan_chenh_lech(self):
        store = MockWalletStore()
        self._dat_cho(store)
        r = store.tat_toan("gen-1", actual_cost_micro=200)
        self.assertEqual(r.actual_cost_micro, 200)
        self.assertEqual(store.lay_so_du("u1").available_micro, 800)  # 1000-300+100

    def test_hoan_tien_tra_lai_toan_bo(self):
        store = MockWalletStore()
        self._dat_cho(store)
        r = store.hoan_tien("gen-1", ly_do="Pollinations 503")
        self.assertEqual(r.status, GenerationStatus.REFUNDED)
        self.assertEqual(store.lay_so_du("u1").available_micro, 1000)
        self.assertEqual(store.lay_so_du("u1").reserved_micro, 0)

    def test_giai_phong_truoc_khi_goi_provider_tra_lai_toan_bo(self):
        store = MockWalletStore()
        self._dat_cho(store)
        store.giai_phong("gen-1", ly_do="hết hạn mức shared premium")
        self.assertEqual(store.lay_so_du("u1").available_micro, 1000)

    def test_tat_toan_hai_lan_bao_loi_khong_tru_them(self):
        store = MockWalletStore()
        self._dat_cho(store)
        store.tat_toan("gen-1")
        with self.assertRaises(InvalidReservationTransition):
            store.tat_toan("gen-1")
        self.assertEqual(store.lay_so_du("u1").available_micro, 700)

    def test_hoan_tien_sau_khi_da_tat_toan_bao_loi(self):
        store = MockWalletStore()
        self._dat_cho(store)
        store.tat_toan("gen-1")
        with self.assertRaises(InvalidReservationTransition):
            store.hoan_tien("gen-1")

    def test_khong_co_reservation_bao_not_found(self):
        store = MockWalletStore()
        with self.assertRaises(NotFoundError):
            store.tat_toan("khong-ton-tai")


class ConcurrencyTest(unittest.TestCase):
    def test_hai_luong_dat_cho_dong_thoi_khong_am_so_du(self):
        """So du 100, hai request cung xin giu 100 — CHI mot thanh cong."""
        import threading

        store = MockWalletStore()
        store.nap_tien_test("u1", 100, idempotency_key="topup-1")
        ket_qua = []

        def thu(idx):
            try:
                store.dat_cho(
                    user_id="u1", generation_id=f"gen-{idx}",
                    mode=GenerationMode.SHARED_PREMIUM, provider_id="p",
                    model="flux", estimated_cost_micro=100,
                    idempotency_key=f"idem-{idx}",
                )
                ket_qua.append("ok")
            except InsufficientBalance:
                ket_qua.append("tu_choi")

        threads = [threading.Thread(target=thu, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(ket_qua.count("ok"), 1)
        self.assertEqual(ket_qua.count("tu_choi"), 4)
        self.assertGreaterEqual(store.lay_so_du("u1").available_micro, 0)


if __name__ == "__main__":
    unittest.main()
