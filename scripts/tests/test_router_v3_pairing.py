"""Ghép Router với cầu nối qua getpass cục bộ — Router V3.2, Phase 5.

Bài quyết định: token SAI thì KHÔNG được lưu gì cả (`pair_bridge` xác minh
bằng một lượt "health" thật trước khi ghi tệp), và tệp đã lưu không bao giờ
đi qua sys.path/argv — chỉ `bridge_store` mới biết đường dẫn.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.router_v3 import bridge_store, pair_bridge, bridge_status
from scripts.router_v3.bridge import BridgeConfig, WorkerBridge


class _CauNoiThatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rv32-pair-"))
        self._env_cu = dict(os.environ)
        os.environ["LOCALAPPDATA"] = str(self.tmp)

        self.bridge = WorkerBridge(
            BridgeConfig(worker_id="AG_TEST", token="dung-token"),
            lambda p, f: {"ok": True},
            health_fn=lambda: True, state_fn=lambda: "warm_idle")
        self.bridge.start()

    def tearDown(self):
        self.bridge.stop()
        os.environ.clear()
        os.environ.update(self._env_cu)


class GhepBangGetpassTest(_CauNoiThatTest):
    def _ghep(self, token_nhap: str) -> int:
        buf = io.StringIO()
        with mock.patch("getpass.getpass", return_value=token_nhap), \
             redirect_stdout(buf):
            rc = pair_bridge.main(["--worker-id", "AG_TEST",
                                   "--port", str(self.bridge.port)])
        self._ra = buf.getvalue()
        return rc

    def test_token_dung_thi_ghep_OK_va_luu_duoc(self):
        rc = self._ghep("dung-token")
        self.assertEqual(rc, 0)
        self.assertIn("GHÉP OK", self._ra)
        luu = bridge_store.doc("AG_TEST")
        self.assertIsNotNone(luu)
        self.assertEqual(luu["port"], self.bridge.port)
        self.assertEqual(luu["token"], "dung-token")

    def test_token_SAI_thi_KHONG_luu_gi_ca(self):
        rc = self._ghep("token-sai")
        self.assertEqual(rc, 1)
        self.assertIsNone(bridge_store.doc("AG_TEST"),
                          "token sai mà vẫn lưu — lỗ hổng ghép nhầm")

    def test_token_rong_thi_huy_som_khong_goi_cau_noi(self):
        rc = self._ghep("")
        self.assertEqual(rc, 2)
        self.assertIsNone(bridge_store.doc("AG_TEST"))

    def test_out_khong_bao_gio_in_lai_token(self):
        self._ghep("dung-token")
        self.assertNotIn("dung-token", self._ra)


class TrangThaiTest(_CauNoiThatTest):
    def _trang_thai(self) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            bridge_status.main(["--worker-id", "AG_TEST"])
        return buf.getvalue()

    def test_chua_ghep_thi_bao_ro(self):
        ra = self._trang_thai()
        self.assertIn("CHƯA GHÉP", ra)

    def test_da_ghep_thi_bao_healthy_va_state(self):
        bridge_store.luu("AG_TEST", host="127.0.0.1", port=self.bridge.port,
                         token="dung-token")
        ra = self._trang_thai()
        self.assertIn("HEALTHY", ra)
        self.assertIn("WARM-IDLE", ra)

    def test_token_da_luu_nhung_sai_thi_bao_hong_khong_bao_ok(self):
        bridge_store.luu("AG_TEST", host="127.0.0.1", port=self.bridge.port,
                         token="token-sai-da-bi-doi")
        ra = self._trang_thai()
        self.assertNotIn("HEALTHY", ra)

    def test_khong_bao_gio_in_token_da_luu(self):
        bridge_store.luu("AG_TEST", host="127.0.0.1", port=self.bridge.port,
                         token="dung-token")
        self.assertNotIn("dung-token", self._trang_thai())


class BridgeStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rv32-store-"))
        self._env_cu = dict(os.environ)
        os.environ["LOCALAPPDATA"] = str(self.tmp)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_cu)

    def test_luu_roi_doc_lai_dung(self):
        bridge_store.luu("AG02", host="127.0.0.1", port=1234, token="t")
        d = bridge_store.doc("AG02")
        self.assertEqual(d, {"host": "127.0.0.1", "port": 1234, "token": "t"})

    def test_chua_luu_thi_doc_ra_None(self):
        self.assertIsNone(bridge_store.doc("KHONG_TON_TAI"))

    def test_duong_dan_nam_duoi_LOCALAPPDATA_khong_phai_trong_kho(self):
        p = bridge_store.duong_luu("AG02")
        self.assertTrue(str(p).startswith(str(self.tmp)))


if __name__ == "__main__":
    unittest.main()
