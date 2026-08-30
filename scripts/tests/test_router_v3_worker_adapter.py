"""Hợp đồng WorkerAdapter trung lập nhà cung cấp — Router LTS Phase 1.

Bài quyết định: `Scheduler` gọi được `adapter_executor(...)` y hệt một
Executor kiểu cũ mà không cần sửa `scheduler.py` — đó là bằng chứng
"provider gỡ ra được mà không đụng core".
"""
from __future__ import annotations

import json
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.dag import RiskClass, TaskNode
from scripts.router_v3.packet import TaskResult, packet_for
from scripts.router_v3.registry import ExecutionType, Health, WorkerSpec
from scripts.router_v3.worker_adapter import (HealthReport, WorkerAdapter,
                                              adapter_executor)


class _FakeAdapter(WorkerAdapter):
    provider = "fake"

    def __init__(self, ok=True):
        self._ok = ok
        self._last = None

    def register(self):
        return WorkerSpec(worker_id="FAKE01", provider_family="fake",
                          execution_type=ExecutionType.LOCAL_CLI, pool="P")

    def health(self):
        return HealthReport(Health.HEALTHY)

    def capabilities(self):
        return frozenset({"implement"})

    def start_session(self, *, workspace=None):
        return True

    def send_task(self, packet):
        kq = TaskResult(task_id=packet.task_id, worker_id="FAKE01",
                        status="ok" if self._ok else "failed",
                        summary="lam xong" if self._ok else "hong",
                        provider=self.provider, duration_seconds=1.5)
        self._last = kq
        return kq

    def cancel(self):
        pass

    def result(self):
        return self._last

    def reset_context(self):
        pass

    def shutdown(self):
        pass


class KhongTheKhoiTaoThieuPhuongThucTest(unittest.TestCase):
    def test_thieu_mot_phuong_thuc_thi_khong_khoi_tao_duoc(self):
        class Thieu(WorkerAdapter):
            provider = "x"
            # thieu tat ca 9 phuong thuc

        with self.assertRaises(TypeError):
            Thieu()


class AdapterExecutorTest(unittest.TestCase):
    def _goi(self, adapter, node) -> tuple:
        ex = adapter_executor({"FAKE01": adapter})
        goi = packet_for(node, base_sha="deadbeef",
                         workspace="C:/fake/ws", branch="b")
        spec = adapter.register()
        return ex(goi, spec)

    def test_ok_di_qua_duoc_dung_hinh_dang_scheduler_doc(self):
        node = TaskNode(id="t1", objective="lam viec X",
                        write_scope=("a.py",), risk_class=RiskClass.LOW)
        adapter = _FakeAdapter(ok=True)
        raw, giay = self._goi(adapter, node)
        d = json.loads(raw)
        self.assertEqual(d["status"], "ok")
        self.assertEqual(giay, 1.5)

    def test_hong_di_qua_duoc_dung_hinh_dang(self):
        node = TaskNode(id="t2", objective="lam viec Y",
                        write_scope=("b.py",), risk_class=RiskClass.LOW)
        adapter = _FakeAdapter(ok=False)
        raw, _ = self._goi(adapter, node)
        d = json.loads(raw)
        self.assertEqual(d["status"], "failed")

    def test_thieu_adapter_cho_worker_khong_nem_loi(self):
        ex = adapter_executor({})
        node = TaskNode(id="t3", objective="x", write_scope=("c.py",))
        goi = packet_for(node, base_sha="deadbeef", workspace="C:/fake/ws")
        spec = WorkerSpec(worker_id="KHONG_CO", provider_family="x",
                          execution_type=ExecutionType.LOCAL_CLI, pool="P")
        raw, giay = ex(goi, spec)
        d = json.loads(raw)
        self.assertEqual(d["status"], "failed")
        self.assertIn("không có adapter", d["summary"])


if __name__ == "__main__":
    unittest.main()
