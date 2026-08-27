#!/usr/bin/env python3
"""Kiem thu ham phan loai NORMAL/WARNING/CRITICAL cua
`scripts.cloudflare_request_monitor` — thuan, khong goi mang, chi kiem tra
logic nguong dua tren du lieu that da ghi nhan (xem docstring cua module
chinh cho nguon con so 2026-08-27)."""
import unittest
from unittest import mock

from scripts.cloudflare_request_monitor import (
    _BIEN_MOI_TRUONG_TOKEN,
    NGUONG_CANH_BAO_MOI_GIO,
    NGUONG_NGHIEM_TRONG_MOI_GIO,
    NGUONG_NGHIEM_TRONG_TICH_LUY_NGAY,
    _doc_token,
    phan_loai,
)


class PhanLoaiTest(unittest.TestCase):
    def test_gio_sach_that_2026_08_27_la_normal(self):
        # 75-90 req/gio quan sat that sau khi sua storm — phai la NORMAL,
        # khong duoc bao dong gia tren du lieu that.
        muc_do, _ = phan_loai(gio_gan_nhat=89, tong_hom_nay=164)
        self.assertEqual(muc_do, "NORMAL")

    def test_khong_co_request_nao_la_normal(self):
        muc_do, _ = phan_loai(gio_gan_nhat=0, tong_hom_nay=0)
        self.assertEqual(muc_do, "NORMAL")

    def test_ngay_duoi_nguong_canh_bao_la_normal(self):
        muc_do, _ = phan_loai(gio_gan_nhat=NGUONG_CANH_BAO_MOI_GIO - 1, tong_hom_nay=1000)
        self.assertEqual(muc_do, "NORMAL")

    def test_dung_nguong_canh_bao_la_warning(self):
        muc_do, _ = phan_loai(gio_gan_nhat=NGUONG_CANH_BAO_MOI_GIO, tong_hom_nay=1000)
        self.assertEqual(muc_do, "WARNING")

    def test_duoi_nguong_nghiem_trong_van_la_warning(self):
        muc_do, _ = phan_loai(gio_gan_nhat=NGUONG_NGHIEM_TRONG_MOI_GIO - 1, tong_hom_nay=1000)
        self.assertEqual(muc_do, "WARNING")

    def test_dung_nguong_nghiem_trong_moi_gio_la_critical(self):
        muc_do, _ = phan_loai(gio_gan_nhat=NGUONG_NGHIEM_TRONG_MOI_GIO, tong_hom_nay=1000)
        self.assertEqual(muc_do, "CRITICAL")

    def test_gio_gan_nhat_thap_nhung_tich_luy_ngay_vuot_nguong_van_la_critical(self):
        # Bat truong hop "khong dot bien tung gio, nhung cong don ca ngay da
        # gan cham tran" — day la ly do co CA HAI dieu kien, khong chi mot.
        muc_do, ly_do = phan_loai(gio_gan_nhat=100, tong_hom_nay=NGUONG_NGHIEM_TRONG_TICH_LUY_NGAY)
        self.assertEqual(muc_do, "CRITICAL")
        self.assertIn("tổng hôm nay", ly_do)

    def test_storm_that_2026_08_26_la_critical_ro_rang(self):
        # So that tu su co: 122.905 request trong MOT gio (02:00 UTC).
        muc_do, _ = phan_loai(gio_gan_nhat=122_905, tong_hom_nay=250_000)
        self.assertEqual(muc_do, "CRITICAL")


class DocTokenTest(unittest.TestCase):
    """`_doc_token` uu tien bien moi truong (portable, dung cho VM) truoc
    khi roi ve doc tep config cua wrangler (cuc bo)."""

    def test_bien_moi_truong_duoc_uu_tien_khi_co(self):
        with mock.patch.dict("os.environ", {_BIEN_MOI_TRUONG_TOKEN: "tep-token-tu-moi-truong"}):
            self.assertEqual(_doc_token(), "tep-token-tu-moi-truong")

    def test_bien_moi_truong_rong_thi_roi_ve_tep_wrangler(self):
        # Chuoi rong (vd bien dat nhung khong co gia tri) KHONG duoc coi la
        # "co" — phai roi tiep xuong doc tep config, khong tra ve rong.
        with mock.patch.dict("os.environ", {_BIEN_MOI_TRUONG_TOKEN: ""}):
            with self.assertRaises(RuntimeError):
                # Khong co tep wrangler that trong moi truong test — phai
                # nem loi ro rang, khong tra ve chuoi rong am tham.
                with mock.patch(
                    "scripts.cloudflare_request_monitor._WRANGLER_CONFIG_CANDIDATES", []):
                    _doc_token()

    def test_khong_co_gi_ca_nem_loi_ro_rang_khong_tao_credential(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch(
                    "scripts.cloudflare_request_monitor._WRANGLER_CONFIG_CANDIDATES", []):
                with self.assertRaises(RuntimeError) as ctx:
                    _doc_token()
                self.assertIn(_BIEN_MOI_TRUONG_TOKEN, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
