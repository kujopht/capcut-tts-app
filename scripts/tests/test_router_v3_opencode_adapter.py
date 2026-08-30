"""Adapter OpenCode — Router LTS Phase 3.

Không cài OpenCode trên máy CI/dev này: `health()` PHẢI báo UNAVAILABLE
THẬT (không mock — cổng 4096 thật sự không có ai nghe), đúng yêu cầu
"không giả vờ tích hợp thành công". Phần còn lại kiểm logic của adapter
bằng cách giả `_goi` (tầng HTTP), không giả toàn bộ hành vi.
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
from scripts.router_v3.opencode_adapter import OpenCodeAdapter, _rut_van_ban
from scripts.router_v3.packet import packet_for
from scripts.router_v3.registry import Health


def _goi_packet():
    node = TaskNode(id="t1", objective="lam viec", write_scope=("a.py",))
    return packet_for(node, base_sha="deadbeef", workspace="C:/ws")


class KhongCoServerThatTest(unittest.TestCase):
    """Cổng 4096 KHÔNG có ai nghe trên máy này — bằng chứng thật, không mock."""

    def test_health_UNAVAILABLE_that_khi_khong_co_server(self):
        a = OpenCodeAdapter("OPENCODE01")
        h = a.health()
        self.assertEqual(h.state, Health.UNAVAILABLE)
        self.assertIn("không chạy", h.detail)

    def test_start_session_that_bai_khi_khong_co_server(self):
        a = OpenCodeAdapter("OPENCODE01")
        self.assertFalse(a.start_session(workspace="C:/ws"))

    def test_send_task_khi_chua_co_session_bao_hong_khong_nem_loi(self):
        a = OpenCodeAdapter("OPENCODE01")
        kq = a.send_task(_goi_packet())
        self.assertEqual(kq.status, "failed")


class RutVanBanTest(unittest.TestCase):
    """Suy đoán hình dạng phản hồi — hàm thuần, không mạng."""

    def test_truong_text_truc_tiep(self):
        self.assertEqual(_rut_van_ban({"text": "xin chao"}), "xin chao")

    def test_truong_content(self):
        self.assertEqual(_rut_van_ban({"content": "noi dung"}), "noi dung")

    def test_mang_parts_kieu_text(self):
        d = {"parts": [{"type": "text", "text": "a"}, {"type": "tool"},
                       {"type": "text", "text": "b"}]}
        self.assertEqual(_rut_van_ban(d), "a\nb")

    def test_long_trong_message(self):
        d = {"message": {"text": "trong long"}}
        self.assertEqual(_rut_van_ban(d), "trong long")

    def test_hinh_dang_la_tra_ve_rong_khong_nem_loi(self):
        self.assertEqual(_rut_van_ban({"gi_do_khac": 1}), "")
        self.assertEqual(_rut_van_ban("khong phai dict"), "")


class LuongGoiGiaTest(unittest.TestCase):
    """Giả tầng HTTP (`_goi`) để kiểm logic adapter mà không cần server."""

    def test_start_session_thanh_cong_khi_healthy_va_tao_duoc_phien(self):
        a = OpenCodeAdapter("OPENCODE01")
        with mock.patch.object(a, "health") as gia_health, \
             mock.patch.object(a, "_goi") as gia_goi:
            from scripts.router_v3.worker_adapter import HealthReport
            gia_health.return_value = HealthReport(Health.HEALTHY)
            gia_goi.return_value = {"id": "ses_123"}
            self.assertTrue(a.start_session(workspace="C:/ws"))
            self.assertEqual(a._session_id, "ses_123")

    def test_send_task_ok_sau_khi_co_session(self):
        a = OpenCodeAdapter("OPENCODE01")
        a._session_id = "ses_123"
        with mock.patch.object(a, "_goi") as gia_goi:
            gia_goi.return_value = {"parts": [{"type": "text", "text":
                '{"status":"ok","summary":"xong","files_changed":["a.py"]}'}]}
            kq = a.send_task(_goi_packet())
            self.assertEqual(kq.status, "ok")
            self.assertEqual(kq.provider, "opencode")

    def test_loi_ket_noi_giua_luot_tra_failed_khong_nem_loi(self):
        a = OpenCodeAdapter("OPENCODE01")
        a._session_id = "ses_123"
        with mock.patch.object(a, "_goi", side_effect=ConnectionError("mat mang")):
            kq = a.send_task(_goi_packet())
            self.assertEqual(kq.status, "failed")

    def test_reset_context_bo_session_id(self):
        a = OpenCodeAdapter("OPENCODE01")
        a._session_id = "ses_123"
        a.reset_context()
        self.assertIsNone(a._session_id)

    def test_capabilities_la_tap_con_CAPABILITIES(self):
        from scripts.router_v3.registry import CAPABILITIES
        a = OpenCodeAdapter("OPENCODE01")
        self.assertLessEqual(a.capabilities(), CAPABILITIES)


if __name__ == "__main__":
    unittest.main()
