"""Adapter Grok Build + Kiro CLI — Router LTS Phase 4 + 5.

Cả hai KHÔNG cài trên máy này — `health()` phải báo UNAVAILABLE THẬT
(không mock việc thiếu binary), và không adapter nào được giả vờ gọi
subprocess với cờ dòng lệnh chưa xác nhận (Kiro).
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.dag import TaskNode
from scripts.router_v3.grok_adapter import GrokBuildAdapter, _rut_van_ban_grok
from scripts.router_v3.kiro_adapter import KiroAdapter
from scripts.router_v3.packet import packet_for
from scripts.router_v3.registry import CAPABILITIES, Health


def _goi_packet():
    node = TaskNode(id="t1", objective="lam viec", write_scope=("a.py",))
    return packet_for(node, base_sha="deadbeef", workspace="C:/ws")


class GrokKhongCaiTest(unittest.TestCase):
    def test_health_UNAVAILABLE_that(self):
        a = GrokBuildAdapter("GROK01")
        h = a.health()
        self.assertEqual(h.state, Health.UNAVAILABLE)
        self.assertIn("không tìm thấy", h.detail)

    def test_start_session_that_bai(self):
        a = GrokBuildAdapter("GROK01")
        self.assertFalse(a.start_session(workspace="C:/ws"))

    def test_send_task_bao_hong_khong_nem_loi(self):
        a = GrokBuildAdapter("GROK01")
        kq = a.send_task(_goi_packet())
        self.assertEqual(kq.status, "failed")

    def test_capabilities_hop_le(self):
        a = GrokBuildAdapter("GROK01")
        self.assertLessEqual(a.capabilities(), CAPABILITIES)


class RutVanBanGrokTest(unittest.TestCase):
    def test_truong_result(self):
        self.assertEqual(_rut_van_ban_grok('{"result": "xin chao"}'), "xin chao")

    def test_khong_phai_json_tra_ve_nguyen_van(self):
        self.assertEqual(_rut_van_ban_grok("van ban thuan"), "van ban thuan")

    def test_rong_tra_ve_rong(self):
        self.assertEqual(_rut_van_ban_grok(""), "")

    def test_hinh_dang_la_khong_nhan_ra_tra_rong(self):
        self.assertEqual(_rut_van_ban_grok('{"gi_do": 1}'), "")


class GrokGoiGiaTest(unittest.TestCase):
    def test_send_task_that_bai_ket_noi_khong_nem_loi(self):
        a = GrokBuildAdapter("GROK01", binary="grok.exe")
        with mock.patch("scripts.router_v3.grok_adapter.subprocess.run",
                        side_effect=OSError("khong chay duoc")):
            kq = a.send_task(_goi_packet())
            self.assertEqual(kq.status, "failed")

    def test_send_task_ok_khi_grok_tra_JSON_dung_hinh_dang(self):
        a = GrokBuildAdapter("GROK01", binary="grok.exe")
        gia = mock.Mock(stdout='{"result": "{\\"status\\":\\"ok\\",'
                               '\\"summary\\":\\"xong\\"}"}', returncode=0)
        with mock.patch("scripts.router_v3.grok_adapter.subprocess.run",
                        return_value=gia):
            kq = a.send_task(_goi_packet())
            self.assertEqual(kq.status, "ok")
            self.assertEqual(kq.provider, "grok")


class KiroKhongCaiTest(unittest.TestCase):
    def test_health_UNAVAILABLE_that(self):
        a = KiroAdapter("KIRO01")
        self.assertEqual(a.health().state, Health.UNAVAILABLE)

    def test_send_task_KHONG_goi_subprocess_nao(self):
        """Bai quyet dinh: KHONG duoc goi subprocess voi co chua xac nhan."""
        a = KiroAdapter("KIRO01")
        with mock.patch("subprocess.run") as gia_run:
            kq = a.send_task(_goi_packet())
            gia_run.assert_not_called()
        self.assertEqual(kq.status, "blocked")

    def test_capabilities_hop_le(self):
        a = KiroAdapter("KIRO01")
        self.assertLessEqual(a.capabilities(), CAPABILITIES)

    def test_khong_nem_loi_du_khong_lam_duoc_gi(self):
        a = KiroAdapter("KIRO01")
        a.cancel()
        a.reset_context()
        a.shutdown()
        self.assertFalse(a.start_session())


if __name__ == "__main__":
    unittest.main()
