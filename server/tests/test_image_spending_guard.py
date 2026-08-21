"""`server/image_spending_guard.py` — PHASE 7/14."""

from __future__ import annotations

import unittest

from server.image_spending_guard import SharedPremiumDisabled, SharedPremiumSpendingGuard


class NormalSpendTest(unittest.TestCase):
    def test_duoi_han_muc_thi_cho_phep(self):
        guard = SharedPremiumSpendingGuard(
            monthly_budget_usd=100.0, warning_budget_usd=80.0, max_concurrent=5)
        guard.bat_dau_request()
        guard.ket_thuc_request(actual_cost_usd=1.0)
        self.assertEqual(guard.snapshot().spent_usd, 1.0)


class WarningTest(unittest.TestCase):
    def test_cham_nguong_canh_bao_goi_callback_khong_chan(self):
        canh_bao_goi = []
        guard = SharedPremiumSpendingGuard(
            monthly_budget_usd=100.0, warning_budget_usd=10.0, max_concurrent=5,
            canh_bao=lambda snap: canh_bao_goi.append(snap),
        )
        guard.bat_dau_request()
        guard.ket_thuc_request(actual_cost_usd=15.0)
        self.assertEqual(len(canh_bao_goi), 1)
        # KHONG chan — request tiep theo van chay duoc (chua cham budget cung).
        guard.bat_dau_request()
        guard.ket_thuc_request(actual_cost_usd=1.0)

    def test_canh_bao_chi_goi_mot_lan_trong_thang(self):
        canh_bao_goi = []
        guard = SharedPremiumSpendingGuard(
            monthly_budget_usd=100.0, warning_budget_usd=10.0, max_concurrent=5,
            canh_bao=lambda snap: canh_bao_goi.append(snap),
        )
        for _ in range(3):
            guard.bat_dau_request()
            guard.ket_thuc_request(actual_cost_usd=15.0)
        self.assertEqual(len(canh_bao_goi), 1)


class HardLimitTest(unittest.TestCase):
    def test_cham_han_muc_thi_khoa_shared_premium(self):
        guard = SharedPremiumSpendingGuard(
            monthly_budget_usd=10.0, warning_budget_usd=8.0, max_concurrent=5)
        guard.bat_dau_request()
        guard.ket_thuc_request(actual_cost_usd=10.0)
        with self.assertRaises(SharedPremiumDisabled):
            guard.bat_dau_request()

    def test_qua_han_muc_khong_lam_am_dem_dong_thoi(self):
        guard = SharedPremiumSpendingGuard(
            monthly_budget_usd=10.0, warning_budget_usd=8.0, max_concurrent=5)
        guard.bat_dau_request()
        guard.ket_thuc_request(actual_cost_usd=10.0)
        with self.assertRaises(SharedPremiumDisabled):
            guard.bat_dau_request()
        self.assertEqual(guard.snapshot().active_concurrent, 0)


class ConcurrencyCapTest(unittest.TestCase):
    def test_vuot_gioi_han_dong_thoi_bi_chan(self):
        guard = SharedPremiumSpendingGuard(
            monthly_budget_usd=1000.0, warning_budget_usd=900.0, max_concurrent=2)
        guard.bat_dau_request()
        guard.bat_dau_request()
        with self.assertRaises(SharedPremiumDisabled):
            guard.bat_dau_request()
        guard.ket_thuc_request()
        guard.bat_dau_request()  # sau khi 1 xong, co cho lai

    def test_that_bai_van_phai_giai_phong_dem_dong_thoi(self):
        """Mo phong: caller PHAI goi ket_thuc_request trong finally, ke ca
        khi provider that bai — o day chi kiem tra dem giam dung khi goi."""
        guard = SharedPremiumSpendingGuard(
            monthly_budget_usd=1000.0, warning_budget_usd=900.0, max_concurrent=1)
        guard.bat_dau_request()
        try:
            raise RuntimeError("provider loi")
        except RuntimeError:
            pass
        finally:
            guard.ket_thuc_request(actual_cost_usd=0.0)
        guard.bat_dau_request()  # khong bi ket vi da giai phong


class KillSwitchTest(unittest.TestCase):
    def test_kill_switch_khoa_ngay_du_con_ngan_sach(self):
        guard = SharedPremiumSpendingGuard(
            monthly_budget_usd=1000.0, warning_budget_usd=900.0, max_concurrent=5)
        guard.dat_kill_switch(True)
        with self.assertRaises(SharedPremiumDisabled):
            guard.bat_dau_request()

    def test_tat_kill_switch_lai_cho_phep_tiep(self):
        guard = SharedPremiumSpendingGuard(
            monthly_budget_usd=1000.0, warning_budget_usd=900.0, max_concurrent=5)
        guard.dat_kill_switch(True)
        guard.dat_kill_switch(False)
        guard.bat_dau_request()
        guard.ket_thuc_request()


if __name__ == "__main__":
    unittest.main()
