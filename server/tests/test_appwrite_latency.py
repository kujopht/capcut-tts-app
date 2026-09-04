"""Bai kiem cho bo do do tre Appwrite.

Khoang trong that duoc dong o day: **do tre phai duoc ghi nhan ngay ca khi
HTTP tra ve khong-2xx**, va **mot trang thai hong khong bao gio duoc dien
giai thanh mot cong suc khoe da dat**.

Khong cham mang: moi bai kiem thay `urlopen` bang mot ban gia.
"""
from __future__ import annotations

import io
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ops.appwrite_latency import (  # noqa: E402
    LOP_DNS,
    LOP_HET_GIO,
    LOP_HTTP,
    LOP_KET_NOI,
    LOP_KHONG,
    LOP_TLS,
    do_tre,
    dong_tom_tat,
)

EP = "https://appwrite-dev.fanfic.world/v1"


class PhanHoiGia:
    def __init__(self, status: int, than: bytes = b'{"version":"1.9.6"}'):
        self.status = status
        self._than = than

    def read(self, n: int = -1) -> bytes:
        return self._than

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Hai_Xx(unittest.TestCase):
    def test_200_thi_khoe_va_co_do_tre(self):
        with mock.patch("urllib.request.urlopen", return_value=PhanHoiGia(200)):
            k = do_tre(EP)
        self.assertTrue(k["khoe"])
        self.assertEqual(k["http_status"], 200)
        self.assertEqual(k["lop_that_bai"], LOP_KHONG)
        self.assertIsNotNone(k["do_tre_giay"])
        self.assertGreaterEqual(k["do_tre_giay"], 0.0)
        self.assertEqual(k["than"], {"version": "1.9.6"})

    def test_than_khong_phai_json_van_khoe(self):
        with mock.patch("urllib.request.urlopen",
                        return_value=PhanHoiGia(204, b"khong phai json")):
            k = do_tre(EP)
        self.assertTrue(k["khoe"])
        self.assertIsNone(k["than"])


class KhongHaiXx(unittest.TestCase):
    """Day la khoang trong that: 401/404 van phai cho ra mot so do tre."""

    def _http_error(self, code: int):
        return urllib.error.HTTPError(
            url=EP, code=code, msg="loi", hdrs=None, fp=io.BytesIO(b""))

    def test_401_VAN_ghi_nhan_do_tre(self):
        with mock.patch("urllib.request.urlopen", side_effect=self._http_error(401)):
            k = do_tre(EP)
        self.assertIsNotNone(k["do_tre_giay"])   # <-- cai da mat truoc day
        self.assertEqual(k["http_status"], 401)
        self.assertFalse(k["khoe"])
        self.assertEqual(k["lop_that_bai"], LOP_HTTP)

    def test_404_VAN_ghi_nhan_do_tre(self):
        with mock.patch("urllib.request.urlopen", side_effect=self._http_error(404)):
            k = do_tre(EP)
        self.assertIsNotNone(k["do_tre_giay"])
        self.assertEqual(k["http_status"], 404)
        self.assertFalse(k["khoe"])

    def test_500_khong_bao_gio_duoc_coi_la_khoe(self):
        with mock.patch("urllib.request.urlopen", side_effect=self._http_error(500)):
            k = do_tre(EP)
        self.assertFalse(k["khoe"])

    def test_moi_ma_ngoai_2xx_deu_khong_khoe(self):
        for ma in (300, 301, 400, 401, 403, 404, 429, 500, 502, 503):
            with self.subTest(ma=ma):
                with mock.patch("urllib.request.urlopen",
                                side_effect=self._http_error(ma)):
                    k = do_tre(EP)
                self.assertFalse(k["khoe"], f"{ma} khong duoc coi la khoe")
                self.assertIsNotNone(k["do_tre_giay"])

    def test_2xx_khong_phai_200_thi_khoe(self):
        for ma in (200, 201, 204, 299):
            with self.subTest(ma=ma):
                with mock.patch("urllib.request.urlopen",
                                return_value=PhanHoiGia(ma)):
                    self.assertTrue(do_tre(EP)["khoe"])


class PhanLoaiThatBai(unittest.TestCase):
    def test_dns(self):
        err = urllib.error.URLError(OSError("[Errno -2] Name or service not known"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            k = do_tre(EP)
        self.assertEqual(k["lop_that_bai"], LOP_DNS)
        self.assertFalse(k["khoe"])
        self.assertIsNotNone(k["do_tre_giay"])

    def test_het_gio(self):
        err = urllib.error.URLError(TimeoutError("timed out"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            self.assertEqual(do_tre(EP)["lop_that_bai"], LOP_HET_GIO)

    def test_tls(self):
        err = urllib.error.URLError(OSError("certificate verify failed"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            self.assertEqual(do_tre(EP)["lop_that_bai"], LOP_TLS)

    def test_ket_noi(self):
        err = urllib.error.URLError(ConnectionRefusedError("Connection refused"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            self.assertEqual(do_tre(EP)["lop_that_bai"], LOP_KET_NOI)

    def test_khong_bao_gio_nem_ngoai_le(self):
        """Bo thu thap so lieu lam do vong quan sat con toi hon khong co."""
        with mock.patch("urllib.request.urlopen", side_effect=RuntimeError("bat ngo")):
            k = do_tre(EP)
        self.assertFalse(k["khoe"])
        self.assertIsNotNone(k["do_tre_giay"])


class KhongLoThongTin(unittest.TestCase):
    def test_chi_tiet_khong_chua_url_day_du(self):
        """URL co the mang tham so truy van, va mot ngay nao do tham so do
        co the la khoa."""
        err = urllib.error.URLError(OSError("bi tu choi khi goi ?key=SIEU_BI_MAT"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            k = do_tre(EP + "?key=SIEU_BI_MAT")
        self.assertNotIn("SIEU_BI_MAT", k["chi_tiet"])


class TomTat(unittest.TestCase):
    def test_luon_in_duoc_mot_dong_duy_nhat(self):
        for k in (
            {"do_tre_giay": 0.42, "http_status": 200, "khoe": True, "lop_that_bai": ""},
            {"do_tre_giay": 0.11, "http_status": 401, "khoe": False, "lop_that_bai": LOP_HTTP},
            {"do_tre_giay": None, "http_status": None, "khoe": False, "lop_that_bai": LOP_DNS},
        ):
            with self.subTest(k=k):
                d = dong_tom_tat(k)
                self.assertEqual(len(d.splitlines()), 1)
                self.assertTrue(d.strip())

    def test_khong_khoe_thi_noi_ro_la_khong_khoe(self):
        d = dong_tom_tat({"do_tre_giay": 0.11, "http_status": 401,
                          "khoe": False, "lop_that_bai": LOP_HTTP})
        self.assertIn("KHONG-KHOE", d)
        self.assertIn("401", d)

    def test_co_do_tre_nhung_khong_khoe_thi_KHONG_hien_thi_nhu_dat(self):
        """Chinh la cai bay: co so do dep khong co nghia la cong da dat."""
        d = dong_tom_tat({"do_tre_giay": 0.05, "http_status": 500,
                          "khoe": False, "lop_that_bai": LOP_HTTP})
        self.assertNotIn("KHOE ", d + " ")
        self.assertIn("KHONG-KHOE", d)


if __name__ == "__main__":
    unittest.main()
