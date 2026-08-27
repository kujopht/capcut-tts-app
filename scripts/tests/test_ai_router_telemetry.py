#!/usr/bin/env python3
"""Kiem thu `scripts/ai_router_telemetry.py` — dung file log TAM (khong
dung file that cua repo), kiem tra: ghi/doc dung, tu choi truong khong
duoc phep, tom tat dung theo tier."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import ai_router_telemetry as rt


class LogRunTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._duong_dan = Path(self._tmp.name) / "telemetry.jsonl"
        self._patch = mock.patch.object(rt, "_DUONG_DAN_LOG", self._duong_dan)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_ghi_mot_ban_ghi_doc_lai_dung(self):
        rt.log_run(category="repo-search", tier="haiku", seconds=12.5, success=True)
        ban_ghi = rt.doc_tat_ca()
        self.assertEqual(len(ban_ghi), 1)
        self.assertEqual(ban_ghi[0]["category"], "repo-search")
        self.assertEqual(ban_ghi[0]["tier"], "haiku")
        self.assertEqual(ban_ghi[0]["seconds"], 12.5)
        self.assertTrue(ban_ghi[0]["success"])

    def test_ghi_nhieu_lan_moi_lan_mot_dong(self):
        rt.log_run(category="a", tier="haiku", seconds=1, success=True)
        rt.log_run(category="b", tier="sonnet", seconds=2, success=False)
        noi_dung = self._duong_dan.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(noi_dung), 2)
        for dong in noi_dung:
            json.loads(dong)  # moi dong PHAI la mot doi tuong JSON hop le doc lap.

    def test_khong_bao_gio_ghi_prompt_hay_noi_dung(self):
        # `log_run` khong nhan tham so "prompt"/"content" nao ca — dam bao
        # bang cach goi voi MOI tham so hop le roi kiem tra khoa ghi ra
        # dung tap da khai bao, khong co gi khac lot vao.
        ban_ghi = rt.log_run(category="x", tier="opus", seconds=1.0, success=True,
                              model="claude-opus-5", effort="high", tests_run=True,
                              tests_passed=True, escalated=True, escalation_reason="race condition")
        self.assertEqual(set(ban_ghi), rt._TRUONG_CHO_PHEP)

    def test_tom_tat_dem_dung_theo_tier(self):
        rt.log_run(category="a", tier="haiku", seconds=1, success=True)
        rt.log_run(category="b", tier="haiku", seconds=2, success=False)
        rt.log_run(category="c", tier="opus", seconds=5, success=True, escalated=True)
        tt = rt.tom_tat()
        self.assertEqual(tt["tong_so_ban_ghi"], 3)
        self.assertEqual(tt["theo_tier"]["haiku"]["lan_chay"], 2)
        self.assertEqual(tt["theo_tier"]["haiku"]["thanh_cong"], 1)
        self.assertEqual(tt["theo_tier"]["opus"]["leo_thang"], 1)

    def test_doc_khi_chua_co_file_tra_ve_danh_sach_rong(self):
        self.assertEqual(rt.doc_tat_ca(), [])
        self.assertEqual(rt.tom_tat()["tong_so_ban_ghi"], 0)


if __name__ == "__main__":
    unittest.main()
