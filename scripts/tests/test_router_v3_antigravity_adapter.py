"""Adapter Antigravity thật (native + cầu nối) qua hợp đồng WorkerAdapter —
Router LTS Phase 2.

Native: giả `WarmAgyWorker` (không gọi `agy` thật — CI Linux không có nó).
Cầu nối: cầu nối THẬT chạy trên 127.0.0.1 với một `run_fn` giả — mạng thật,
chỉ mô hình được giả.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.antigravity_adapter import (AntigravityBridgeAdapter,
                                                   AntigravityNativeAdapter)
from scripts.router_v3.bridge import BridgeConfig, WorkerBridge
from scripts.router_v3.dag import TaskNode
from scripts.router_v3.packet import packet_for
from scripts.router_v3.registry import Health
from scripts.router_v3.warm_pool import WarmState, WarmTurn


def _goi(**kw):
    node = TaskNode(id="t1", objective="lam viec", write_scope=("a.py",))
    return packet_for(node, base_sha="deadbeef", workspace="C:/fake/ws", **kw)


class NativeAdapterTest(unittest.TestCase):
    def test_health_truoc_start_session_la_UNKNOWN(self):
        a = AntigravityNativeAdapter("AG01", model="m")
        self.assertEqual(a.health().state, Health.UNKNOWN)

    def test_start_session_that_bai_thi_health_bao_FAILED(self):
        a = AntigravityNativeAdapter("AG01", model="m")
        with mock.patch(
            "scripts.router_v3.antigravity_adapter.WarmAgyWorker") as GiaWorker:
            gia = GiaWorker.return_value
            gia.start.return_value = False
            gia.state = WarmState.FAILED
            ok = a.start_session(workspace="C:/ws")
            self.assertFalse(ok)
            self.assertEqual(a.health().state, Health.FAILED)

    def test_send_task_ok_tra_ve_TaskResult_co_provider_model(self):
        a = AntigravityNativeAdapter("AG01", model="gemini-x")
        with mock.patch(
            "scripts.router_v3.antigravity_adapter.WarmAgyWorker") as GiaWorker:
            gia = GiaWorker.return_value
            gia.start.return_value = True
            gia.state = WarmState.WARM_IDLE
            gia.send.return_value = WarmTurn(
                ok=True, response='{"status":"ok","summary":"xong",'
                '"files_changed":["a.py"],"tests":"5 passed"}', seconds=2.0)
            a.start_session(workspace="C:/ws")
            kq = a.send_task(_goi())
            self.assertEqual(kq.status, "ok")
            self.assertEqual(kq.provider, "antigravity")
            self.assertEqual(kq.model, "gemini-x")
            self.assertEqual(a.result(), kq)

    def test_cancel_danh_dau_blocked_va_dong_tien_trinh(self):
        a = AntigravityNativeAdapter("AG01", model="m")
        with mock.patch(
            "scripts.router_v3.antigravity_adapter.WarmAgyWorker") as GiaWorker:
            gia = GiaWorker.return_value
            gia.start.return_value = True
            gia.state = WarmState.WARM_IDLE
            gia.send.return_value = WarmTurn(ok=True, response="{}", seconds=1.0)
            a.start_session(workspace="C:/ws")
            a.cancel()
            kq = a.send_task(_goi())
            self.assertEqual(kq.status, "blocked")
            gia.close.assert_called()

    def test_gui_viec_khi_chua_start_session_bao_hong_khong_nem_loi(self):
        a = AntigravityNativeAdapter("AG01", model="m")
        kq = a.send_task(_goi())
        self.assertEqual(kq.status, "failed")

    def test_register_nang_luc_la_tap_con_CAPABILITIES(self):
        from scripts.router_v3.registry import CAPABILITIES
        a = AntigravityNativeAdapter("AG01", model="m")
        self.assertLessEqual(a.capabilities(), CAPABILITIES)


class BridgeAdapterThatTest(unittest.TestCase):
    """Cầu nối THẬT trên loopback — không phải mock ở tầng socket."""

    def setUp(self):
        self.goi_nhan = []

        def chay(prompt, family):
            self.goi_nhan.append((prompt, family))
            return {"response": '{"status":"ok","summary":"da lam",'
                    '"files_changed":["b.py"]}', "ok": True}

        self.bridge = WorkerBridge(
            BridgeConfig(worker_id="AG02"), chay,
            health_fn=lambda: True, state_fn=lambda: "warm_idle")
        self.bridge.start()
        self.a = AntigravityBridgeAdapter(
            "AG02", host="127.0.0.1", port=self.bridge.port,
            token=self.bridge.token, model="gemini-x")

    def tearDown(self):
        self.bridge.stop()

    def test_health_that_qua_mang_that(self):
        h = self.a.health()
        self.assertEqual(h.state, Health.HEALTHY)
        self.assertEqual(h.detail, "warm_idle")

    def test_start_session_kiem_con_song_khong_dung_tien_trinh_moi(self):
        self.assertTrue(self.a.start_session(workspace="C:/ws"))

    def test_send_task_that_qua_mang_va_lam_tron_TaskResult(self):
        kq = self.a.send_task(_goi())
        self.assertEqual(kq.status, "ok")
        self.assertEqual(kq.provider, "antigravity")
        self.assertEqual(self.goi_nhan[0][0], _goi().render())

    def test_token_sai_thi_health_UNAVAILABLE(self):
        xau = AntigravityBridgeAdapter("AG02", host="127.0.0.1",
                                       port=self.bridge.port, token="sai")
        self.assertEqual(xau.health().state, Health.UNAVAILABLE)

    def test_cancel_khong_dung_duoc_viec_tu_xa_nhung_bao_ro_trong_ket_qua(self):
        self.a.cancel()
        kq = self.a.send_task(_goi())
        self.assertEqual(kq.status, "blocked")
        self.assertIn("KHÔNG bị dừng", kq.summary)
        # nhung viec TU XA van thuc su chay (dung dong bo) — bang chung no
        # van nhan duoc prompt, dung y "gioi han that, khong gia vo".
        self.assertEqual(len(self.goi_nhan), 1)

    def test_reset_context_va_shutdown_khong_nem_loi_du_khong_lam_gi(self):
        self.a.reset_context()
        self.a.shutdown()


if __name__ == "__main__":
    unittest.main()
