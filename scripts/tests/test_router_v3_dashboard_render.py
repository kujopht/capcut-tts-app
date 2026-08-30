"""Bảng trạng thái `render()`/`utilization()` — Router V3, Phase 14.

Dataclass thật (TaskDag/TaskNode/WorkerRegistry/WorkerSpec/WorkerState) đều
rẻ, thuần tuý trong bộ nhớ, không mạng không file — nên không mock module
dashboard và cũng không giả driver của registry. Chạy từ gốc kho:
`python -m unittest scripts.tests.test_router_v3_dashboard_render -v`.
"""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.dag import TaskDag, TaskNode
from scripts.router_v3.dashboard import render, utilization
from scripts.router_v3.registry import (ExecutionType, Health, WorkerRegistry,
                                        WorkerSpec)


def _spec(worker_id: str, **kw) -> WorkerSpec:
    kw.setdefault("provider_family", "antigravity")
    kw.setdefault("execution_type", ExecutionType.LOCAL_CLI)
    kw.setdefault("pool", "GEMINI_FLASH")
    return WorkerSpec(worker_id=worker_id, **kw)


def _dag_one_node(node_id: str = "n-1", **kw) -> TaskDag:
    kw.setdefault("estimated_seconds", 60.0)
    return TaskDag([TaskNode(id=node_id, objective="việc x", **kw)])


class RenderTest(unittest.TestCase):
    def _hoan_thanh(self, reg: WorkerRegistry, wid: str, giay: float) -> None:
        """`completed`/`total_seconds` qua driver thật, không sửa state tay."""
        reg.mark_started(wid, "task-tam")
        reg.mark_finished(wid, ok=True, seconds=giay)

    def test_running_hien_elapsed(self) -> None:
        reg = WorkerRegistry()
        reg.register(_spec("w-1"))
        dag = _dag_one_node()
        reg.mark_started("w-1", "n-1")

        s = render(dag, reg, done=set(), failed=set(),
                   started_at={"n-1": 10.0}, now=100.0, parallelism=2)

        self.assertIn("w-1", s)
        self.assertIn("RUNNING", s)
        self.assertIn("n-1", s)
        self.assertIn("01:30", s)          # 90 giây trôi qua

    def test_unavailable_duoc_hien(self) -> None:
        reg = WorkerRegistry()
        reg.register(_spec("w-1"))
        reg.set_health("w-1", Health.UNAVAILABLE)
        dag = _dag_one_node()

        s = render(dag, reg, done=set(), failed=set(), started_at={}, now=5.0)

        self.assertIn("w-1", s)
        self.assertIn("UNAVAILABLE", s)

    def test_idle_khi_khong_co_viec(self) -> None:
        reg = WorkerRegistry()
        reg.register(_spec("w-1"))
        reg.set_health("w-1", Health.HEALTHY)
        dag = _dag_one_node()

        s = render(dag, reg, done=set(), failed=set(), started_at={}, now=5.0)

        self.assertIn("w-1", s)
        self.assertIn("IDLE", s)
        self.assertNotIn("RUNNING", s)

    def test_khong_lo_tu_khoa(self) -> None:
        reg = WorkerRegistry()
        reg.register(_spec("w-1"))
        reg.register(_spec("w-2"))
        reg.set_health("w-1", Health.HEALTHY)
        reg.set_health("w-2", Health.UNAVAILABLE)
        dag = _dag_one_node()
        reg.mark_started("w-1", "n-1")

        s = render(dag, reg, done=set(), failed=set(),
                   started_at={"n-1": 1.0}, now=61.0, task_name="t",
                   parallelism=4, retries=1)

        lowercase = s.lower()
        self.assertNotIn("token", lowercase)
        self.assertNotIn("password", lowercase)
        self.assertNotIn("mật khẩu", lowercase)

    def test_render_khong_can_task_name(self) -> None:
        reg = WorkerRegistry()
        reg.register(_spec("w-1"))
        dag = _dag_one_node()

        s = render(dag, reg, done=set(), failed=set(), started_at={}, now=1.0)

        self.assertTrue(s.startswith("ROUTER V3"))

    def test_utilization_tinh_busy_ratio(self) -> None:
        reg = WorkerRegistry()
        reg.register(_spec("w-1"))
        # 2 lần hoàn thành, mỗi lần 15 giây -> completed=2, avg=15.0
        self._hoan_thanh(reg, "w-1", 15.0)
        self._hoan_thanh(reg, "w-1", 15.0)

        rows = utilization(reg, wall_seconds=120.0)

        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["worker_id"], "w-1")
        self.assertEqual(r["completed"], 2)
        self.assertEqual(r["busy_seconds"], 30.0)
        self.assertAlmostEqual(r["busy_ratio"], 30.0 / 120.0, places=3)

    def test_utilization_wall_zero_thi_ratio_zero(self) -> None:
        reg = WorkerRegistry()
        reg.register(_spec("w-1"))
        self._hoan_thanh(reg, "w-1", 10.0)

        rows = utilization(reg, wall_seconds=0.0)

        self.assertEqual(rows[0]["busy_ratio"], 0.0)

    def test_utilization_worker_moi_bang_khong(self) -> None:
        reg = WorkerRegistry()
        reg.register(_spec("w-1"))

        rows = utilization(reg, wall_seconds=60.0)

        self.assertEqual(rows[0]["completed"], 0)
        self.assertEqual(rows[0]["busy_seconds"], 0.0)
        self.assertEqual(rows[0]["busy_ratio"], 0.0)


if __name__ == "__main__":
    unittest.main()