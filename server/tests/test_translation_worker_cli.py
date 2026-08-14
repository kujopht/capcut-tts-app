"""
`server/translation_worker.py` — chi phan LOGIC THUAN kiem duoc ma khong dung
vao mang/tien trinh that: parse tham so dong lenh, va healthcheck doc tep
nhip. Logic claim/lease/recovery da duoc kiem qua CHINH `TranslationService`
o `test_translation_worker.py` — worker CLI chi la mot vong lap goi lai cac
phuong thuc do, khong co logic nghiep vu rieng dang kiem lai o day.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from server.translation_worker import _doc_tham_so


class ThamSoTest(unittest.TestCase):
    def test_khong_co_gi_dung_mac_dinh(self):
        ns = _doc_tham_so([])
        self.assertFalse(ns.check)
        self.assertIsNone(ns.require_env)

    def test_co_check(self):
        ns = _doc_tham_so(["--check"])
        self.assertTrue(ns.check)

    def test_co_require_env(self):
        ns = _doc_tham_so(["--require-env", "staging"])
        self.assertEqual(ns.require_env, "staging")


class KiemTraHealthcheckTest(unittest.TestCase):
    """`kiem_tra()` doc tep nhip — kiem logic tuoi/nguong THUAN, khong dung
    vao `_svc`/`_settings` module-level (tach rieng bang monkeypatch
    `HEARTBEAT_FILE`)."""

    def setUp(self) -> None:
        self._dir = tempfile.mkdtemp()
        import server.translation_worker as tw

        self._tw = tw
        self._goc = tw.HEARTBEAT_FILE
        tw.HEARTBEAT_FILE = Path(self._dir) / "heartbeat.json"

    def tearDown(self) -> None:
        self._tw.HEARTBEAT_FILE = self._goc

    def _ghi_nhip(self, tuoi_giay: int, trang_thai: str = "dang_chay") -> None:
        from datetime import datetime, timedelta, timezone

        luc = datetime.now(timezone.utc) - timedelta(seconds=tuoi_giay)
        self._tw.HEARTBEAT_FILE.write_text(json.dumps({
            "worker_id": "w1", "pid": 1, "trang_thai": trang_thai,
            "chu_ky": 1, "luc": luc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "job_dang_chay": 0, "lan_quet_gan_nhat": None,
        }), encoding="utf-8")

    def test_khong_co_tep_nhip_tra_1(self):
        self.assertEqual(self._tw.kiem_tra(), 1)

    def test_nhip_moi_tra_0(self):
        self._ghi_nhip(tuoi_giay=1)
        self.assertEqual(self._tw.kiem_tra(), 0)

    def test_nhip_cu_qua_nguong_tra_1(self):
        self._ghi_nhip(tuoi_giay=self._tw.STALE_SECONDS + 100)
        self.assertEqual(self._tw.kiem_tra(), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
