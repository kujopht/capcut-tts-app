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

from scripts.router_v3 import bridge_store, pair_bridge, bridge_status, pairing_file
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


class GhepBangTepTest(_CauNoiThatTest):
    """Ghép qua tệp dùng chung — không gõ tay, không qua model context."""

    def setUp(self):
        super().setUp()
        self.thu_muc = self.tmp / "pairing"
        self.thu_muc.mkdir()
        self.tep = self.thu_muc / "AG_TEST.pair"

    def _ghi_tep(self, worker_id="AG_TEST", port=None, token="dung-token"):
        pairing_file.write(self.tep, worker_id=worker_id,
                           port=port if port is not None else self.bridge.port,
                           token=token)

    def _ghep(self) -> int:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = pair_bridge.main(["--pairing-file", str(self.tep)])
        self._ra = buf.getvalue()
        return rc

    def test_tep_dung_thi_ghep_OK_va_xoa_tep(self):
        self._ghi_tep()
        rc = self._ghep()
        self.assertEqual(rc, 0)
        self.assertIn("GHÉP OK", self._ra)
        luu = bridge_store.doc("AG_TEST")
        self.assertEqual(luu["token"], "dung-token")
        self.assertFalse(self.tep.exists(), "tệp ghép PHẢI bị xoá sau khi ghép OK")

    def test_tep_khong_ton_tai_thi_bao_ro_khong_nem_loi(self):
        rc = self._ghep()
        self.assertEqual(rc, 2)
        self.assertIn("không đọc được tệp ghép", self._ra)

    def test_token_sai_trong_tep_thi_KHONG_luu_va_GIU_tep(self):
        self._ghi_tep(token="token-sai")
        rc = self._ghep()
        self.assertEqual(rc, 1)
        self.assertIsNone(bridge_store.doc("AG_TEST"))
        self.assertTrue(self.tep.exists(),
                        "ghép hỏng thì PHẢI giữ tệp lại để còn thử lại được")

    def test_worker_id_khong_khop_thi_tu_choi_khong_luu(self):
        self._ghi_tep(worker_id="AG_NHAM")
        rc = self._ghep()
        self.assertEqual(rc, 1)
        self.assertIn("worker_id", self._ra)
        self.assertIsNone(bridge_store.doc("AG_NHAM"))

    def test_out_khong_bao_gio_in_token_du_thanh_cong_hay_that_bai(self):
        self._ghi_tep()
        self._ghep()
        self.assertNotIn("dung-token", self._ra)
        self._ghi_tep(token="token-khac")
        self._ghep()
        self.assertNotIn("token-khac", self._ra)

    def test_khong_the_dung_ca_hai_che_do_cung_luc(self):
        rc = pair_bridge.main(["--pairing-file", str(self.tep),
                               "--port", "1234"])
        self.assertEqual(rc, 2)


class PairingFileModuleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rv32-pairfile-"))
        self.thu_muc = self.tmp / "pairing"
        self.thu_muc.mkdir()
        self.tep = self.thu_muc / "AG01.pair"

    def test_ghi_roi_doc_lai_dung(self):
        pairing_file.write(self.tep, worker_id="AG01", port=999, token="t")
        d = pairing_file.read(self.tep)
        self.assertEqual(d, {"worker_id": "AG01", "port": 999, "token": "t"})

    def test_doc_tep_khong_ton_tai_ra_None(self):
        self.assertIsNone(pairing_file.read(self.tmp / "khong-co.pair"))

    def test_doc_tep_sai_dinh_dang_ra_None_khong_nem_loi(self):
        self.tep.write_text("khong phai json", encoding="utf-8")
        self.assertIsNone(pairing_file.read(self.tep))

    def test_ghi_khi_thu_muc_cha_chua_co_thi_TU_CHOI(self):
        with self.assertRaises(FileNotFoundError):
            pairing_file.write(self.tmp / "chua-tao" / "x.pair",
                               worker_id="A", port=1, token="t")

    def test_xoa_an_toan_xoa_that_va_khong_con_noi_dung_cu(self):
        pairing_file.write(self.tep, worker_id="AG01", port=999,
                           token="bi-mat-can-xoa")
        raw_truoc = self.tep.read_bytes()
        self.assertIn(b"bi-mat-can-xoa", raw_truoc)
        ok = pairing_file.secure_delete(self.tep)
        self.assertTrue(ok)
        self.assertFalse(self.tep.exists())

    def test_xoa_an_toan_tren_tep_khong_ton_tai_tra_False(self):
        self.assertFalse(pairing_file.secure_delete(self.tmp / "khong-co.pair"))


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
