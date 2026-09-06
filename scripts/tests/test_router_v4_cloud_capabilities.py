"""Bai kiem cho tu vung nang luc HA TANG cua Router V4.

Trong tam: ba muc (cai dat / xac thuc / uy quyen) KHONG duoc phep keo theo
nhau. Do la ca ly do module ton tai — dot di tru 2026-09 lien tuc doan sai
o dung cho do.
"""
from __future__ import annotations

import unittest
from unittest import mock

from scripts.router_v4 import cloud_capabilities as cc


class TestBaMuc(unittest.TestCase):
    def test_co_binary_khong_dong_nghia_da_xac_thuc(self):
        with mock.patch.object(cc, "_co", return_value=True), \
             mock.patch.object(cc, "_chay", return_value=(1, "")):
            n = cc.do_gcloud()
        self.assertEqual(n.muc, cc.CO_BINARY)
        self.assertEqual(n.lam_duoc, [])

    def test_chua_cai_thi_khong_co_nang_luc_nao(self):
        with mock.patch.object(cc, "_co", return_value=False):
            self.assertEqual(cc.do_gcloud().muc, cc.CHUA_CAI)
            self.assertEqual(cc.do_gh().muc, cc.CHUA_CAI)

    def test_xac_thuc_roi_thi_co_nang_luc(self):
        with mock.patch.object(cc, "_co", return_value=True), \
             mock.patch.object(cc, "_chay", return_value=(0, "ai@do.com")):
            n = cc.do_gcloud()
        self.assertEqual(n.muc, cc.DA_XAC_THUC)
        self.assertIn("secret_manager", n.lam_duoc)


class TestRanhGioiConNguoi(unittest.TestCase):
    def test_chi_gom_dung_thu_KHONG_lam_duoc(self):
        kq = {
            "a": {"lam_duoc": ["x", "y"], "khong_lam_duoc": []},
            "b": {"lam_duoc": ["z"], "khong_lam_duoc": ["tao_api_token"]},
        }
        self.assertEqual(cc.ranh_gioi_con_nguoi(kq), ["tao_api_token"])

    def test_khong_co_gi_thieu_thi_rong(self):
        kq = {"a": {"lam_duoc": ["x"], "khong_lam_duoc": []}}
        self.assertEqual(cc.ranh_gioi_con_nguoi(kq), [])

    def test_khong_trung_lap(self):
        kq = {
            "a": {"khong_lam_duoc": ["p"]},
            "b": {"khong_lam_duoc": ["p"]},
        }
        self.assertEqual(cc.ranh_gioi_con_nguoi(kq), ["p"])


class TestWranglerQuaNpx(unittest.TestCase):
    def test_khong_cai_toan_cuc_van_dung_duoc_qua_npx(self):
        # Bay that: `command -v wrangler` that bai KHONG co nghia la khong
        # dung duoc Cloudflare — `npx wrangler` chay duoc, va phien OAuth
        # nam o cho khac.
        def gia_co(ten):
            return ten == "npx"
        with mock.patch.object(cc, "_co", side_effect=gia_co), \
             mock.patch("os.path.exists", return_value=False):
            n = cc.do_wrangler()
        self.assertEqual(n.muc, cc.CO_BINARY)
        self.assertIn("npx", n.ghi_chu)

    def test_co_phien_thi_liet_ke_duoc_R2_nhung_VAN_khong_tao_duoc_token(self):
        # Do that 2026-09-06: cung mot phien lam duoc R2 nhung 403 khi tao token.
        with mock.patch.object(cc, "_co", return_value=True), \
             mock.patch("os.path.exists", return_value=True):
            n = cc.do_wrangler()
        self.assertEqual(n.muc, cc.DA_XAC_THUC)
        self.assertIn("r2_bucket_create", n.lam_duoc)
        self.assertTrue(any("api_token" in x for x in n.khong_lam_duoc))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
