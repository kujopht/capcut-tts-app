"""Danh tính cầu nối ổn định qua nhiều lần khởi động — Router LTS Phase 6.

Bài quyết định: lần khởi động THỨ HAI phải nhận lại ĐÚNG token của lần
đầu (không sinh mới) — đó là điều kiện để Router không phải ghép lại sau
một lần khởi động lại bình thường.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3 import worker_identity as wi


class DanhTinhOnDinhTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rv-ltsid-"))
        self._env_cu = dict(os.environ)
        os.environ["LOCALAPPDATA"] = str(self.tmp)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_cu)

    def test_lan_dau_sinh_moi_port_0(self):
        d = wi.doc_hoac_tao("AG02")
        self.assertEqual(d["port"], 0)
        self.assertTrue(d["token"])

    def test_lan_thu_hai_DUNG_LAI_dung_token_lan_dau(self):
        d1 = wi.doc_hoac_tao("AG02")
        d2 = wi.doc_hoac_tao("AG02")
        self.assertEqual(d1["token"], d2["token"])

    def test_ghi_cong_that_su_luu_lai_cho_lan_sau(self):
        wi.doc_hoac_tao("AG02")
        wi.ghi_cong_that_su("AG02", 54321)
        d = wi.doc_hoac_tao("AG02")
        self.assertEqual(d["port"], 54321)

    def test_hai_worker_khac_nhau_khong_dam_danh_tinh(self):
        d1 = wi.doc_hoac_tao("AG01")
        d2 = wi.doc_hoac_tao("AG02")
        self.assertNotEqual(d1["token"], d2["token"])

    def test_xoay_token_buoc_khac_han_lan_truoc(self):
        d1 = wi.doc_hoac_tao("AG02")
        d2 = wi.xoay_token("AG02")
        self.assertNotEqual(d1["token"], d2["token"])

    def test_tep_sai_dinh_dang_sinh_moi_khong_nem_loi(self):
        p = wi.duong_danh_tinh("AG02")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("khong phai json", encoding="utf-8")
        d = wi.doc_hoac_tao("AG02")
        self.assertTrue(d["token"])

    def test_duong_dan_khong_nam_trong_kho(self):
        p = wi.duong_danh_tinh("AG02")
        self.assertTrue(str(p).startswith(str(self.tmp)))


if __name__ == "__main__":
    unittest.main()
