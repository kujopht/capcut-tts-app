"""Checkpoint agent dẫn dắt — Router LTS Phase 10 + 14.

Bài quyết định: `Checkpoint` không được chứa nội dung việc/hội thoại đầy
đủ — chỉ bảy trường cấu trúc. Kiểm bằng cách dựng một RunReport có
`raw_excerpt` "bí mật" và xác nhận nó KHÔNG lọt vào checkpoint.
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

from scripts.router_v3.checkpoint import Checkpoint, doc, luu, tu_run_report
from scripts.router_v3.dag import RiskClass, TaskDag, TaskNode
from scripts.router_v3.packet import TaskResult
from scripts.router_v3.scheduler import RunReport


def _dag_hai_nut():
    return TaskDag([
        TaskNode(id="a", objective="x", write_scope=("a.py",)),
        TaskNode(id="b", objective="y", write_scope=("b.py",)),
    ])


class TuRunReportTest(unittest.TestCase):
    def test_dag_state_dung_cho_moi_nut(self):
        dag = _dag_hai_nut()
        report = RunReport(results={
            "a": TaskResult(task_id="a", worker_id="W", status="ok",
                            commit="deadbeef", tests="5 passed",
                            raw_excerpt="BI MAT khong duoc lo"),
        }, skipped=["b"])
        cp = tu_run_report(dag, report)
        self.assertEqual(cp.dag_state, {"a": "ok", "b": "skipped"})
        self.assertIn("deadbeef", cp.commits)
        self.assertEqual(cp.tests["a"], "5 passed")

    def test_KHONG_chua_raw_excerpt_cua_worker(self):
        dag = _dag_hai_nut()
        report = RunReport(results={
            "a": TaskResult(task_id="a", worker_id="W", status="ok",
                            raw_excerpt="BI MAT khong duoc lo tam thoi"),
        })
        cp = tu_run_report(dag, report)
        noi_dung = str(cp.__dict__)
        self.assertNotIn("BI MAT", noi_dung)

    def test_vi_pham_pham_vi_thanh_blocker(self):
        dag = _dag_hai_nut()
        report = RunReport(results={
            "a": TaskResult(task_id="a", worker_id="W", status="blocked"),
        }, scope_violations={"a": ["c.py"]})
        cp = tu_run_report(dag, report)
        self.assertTrue(any("c.py" in b for b in cp.blockers))

    def test_con_lai_la_nhung_nut_chua_ok(self):
        dag = _dag_hai_nut()
        report = RunReport(results={
            "a": TaskResult(task_id="a", worker_id="W", status="ok"),
            "b": TaskResult(task_id="b", worker_id="W", status="failed"),
        })
        cp = tu_run_report(dag, report)
        self.assertEqual(cp.con_lai, ["b"])


class LuuDocTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rv-cp-"))
        self.duong = self.tmp / "cp.json"

    def test_luu_roi_doc_lai_dung(self):
        cp = Checkpoint(dag_state={"a": "ok"}, commits=["deadbeef"],
                        next_actions=["chạy Phase 8"])
        luu(cp, duong=self.duong)
        cp2 = doc(duong=self.duong)
        self.assertEqual(cp2.dag_state, {"a": "ok"})
        self.assertEqual(cp2.next_actions, ["chạy Phase 8"])

    def test_doc_tep_khong_ton_tai_ra_None(self):
        self.assertIsNone(doc(duong=self.tmp / "khong-co.json"))

    def test_tu_choi_luu_neu_giong_credential(self):
        cp = Checkpoint(findings=["sk-" + "x" * 30])
        with self.assertRaises(ValueError):
            luu(cp, duong=self.duong)
        self.assertFalse(self.duong.exists())


if __name__ == "__main__":
    unittest.main()
