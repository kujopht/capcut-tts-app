"""Crash/resume — Router LTS Phase 14.

Bằng chứng THẬT trên đĩa: một kho git tạm thật, một worktree thật, một
commit thật cho nút đã xong — không phải chỉ trạng thái trong bộ nhớ.
Kịch bản: Router "chết" giữa chừng (nút thứ hai không bao giờ trả lời),
"khởi động lại" bằng một `Scheduler`/`WorktreeManager` MỚI trỏ vào ĐÚNG
kho đó, và chạy lại với `already_done` — nút đã xong không bị chạy lại
(cùng SHA commit trước/sau), nút chưa xong chạy thật và xong.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.checkpoint import tu_run_report
from scripts.router_v3.dag import RiskClass, TaskDag, TaskNode
from scripts.router_v3.registry import ExecutionType, WorkerRegistry, WorkerSpec
from scripts.router_v3.scheduler import Scheduler
from scripts.router_v3.worktree import WorktreeManager


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                          text=True, encoding="utf-8", check=True)


def _dag_2_nut():
    return TaskDag([
        TaskNode(id="a", objective="viet a.py", write_scope=("a.py",),
                risk_class=RiskClass.LOW),
        TaskNode(id="b", objective="viet b.py", write_scope=("b.py",),
                risk_class=RiskClass.LOW),
    ])


def _registry_hai_worker():
    r = WorkerRegistry()
    for wid in ("W1", "W2"):
        r.register(WorkerSpec(worker_id=wid, provider_family="fake",
                              execution_type=ExecutionType.LOCAL_CLI, pool="P",
                              max_concurrent=1))
    from scripts.router_v3.registry import Health
    r.set_health("W1", Health.HEALTHY)
    r.set_health("W2", Health.HEALTHY)
    return r


def _executor_ghi_that_va_commit(hong_voi=frozenset()):
    """Executor GIẢ nhưng ghi/commit THẬT vào worktree — mô phỏng một
    worker thật đã hoàn thành việc, không chỉ trả JSON suông."""

    def _thuc_thi(packet, spec):
        if packet.task_id in hong_voi:
            raise RuntimeError(f"{packet.task_id}: worker không bao giờ trả lời (mô phỏng crash)")
        ws = Path(packet.workspace)
        tep = ws / packet.write_scope[0]
        tep.write_text(f"# {packet.task_id}\n", encoding="utf-8")
        _git(ws, "add", packet.write_scope[0])
        _git(ws, "commit", "-q", "-m", f"lam {packet.task_id}")
        sha = _git(ws, "rev-parse", "HEAD").stdout.strip()
        return json.dumps({"status": "ok", "summary": "xong", "commit": sha,
                           "files_changed": list(packet.write_scope),
                           "tests": "ok"}, ensure_ascii=False), 0.01

    return _thuc_thi


class CrashResumeThatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rv-crash-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "--quiet", "-b", "main")
        _git(self.repo, "config", "user.email", "t@t.test")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "README.md").write_text("x", encoding="utf-8")
        # `.router/worktrees/...` nam TRONG cay lam viec chinh khi khong dat
        # goc dung chung rieng — thieu dong nay thi git status thay no la
        # tep chua theo doi va coi cay lam viec la "ban", dung y that voi
        # cach kho That cua du an nay da cau hinh (.router/ da gitignore).
        (self.repo / ".gitignore").write_text(".router/\n", encoding="utf-8")
        _git(self.repo, "add", "README.md", ".gitignore")
        _git(self.repo, "commit", "-q", "-m", "dau")
        self.base_sha = _git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def test_crash_giua_chung_roi_resume_khong_chay_lai_nut_da_xong(self):
        dag = _dag_2_nut()

        # --- "Phien Router" THU NHAT: nut b khong bao gio tra loi (crash) ---
        wt1 = WorktreeManager(self.repo)
        reg1 = _registry_hai_worker()
        sch1 = Scheduler(reg1, _executor_ghi_that_va_commit(hong_voi={"b"}),
                         base_sha=self.base_sha, worktrees=wt1, node_timeout=30)
        report1 = sch1.run(dag)

        self.assertTrue(report1.results["a"].ok)
        self.assertFalse(report1.results["b"].ok)
        sha_a_lan1 = report1.results["a"].commit
        self.assertTrue(sha_a_lan1)

        cp = tu_run_report(dag, report1, base_sha=self.base_sha)
        self.assertEqual(cp.dag_state["a"], "ok")
        self.assertIn("b", cp.con_lai)
        self.assertNotIn("a", cp.con_lai)

        # --- "KHOI DONG LAI": Scheduler/WorktreeManager MOI, TRO VAO DUNG kho ---
        wt2 = WorktreeManager(self.repo)          # instance MOI, khong phai wt1
        reg2 = _registry_hai_worker()
        sch2 = Scheduler(reg2, _executor_ghi_that_va_commit(),  # lan nay b KHONG hong
                         base_sha=self.base_sha, worktrees=wt2, node_timeout=30)
        report2 = sch2.run(dag, already_done=report1.results)

        # Nut a: `results` cua lan hai VAN co "a" (bao cao day du de tich hop
        # mot lan) — nhung do la ket qua DA LUU tu lan truoc, khong phai
        # dispatch lai: cung SHA commit, khong co worktree THU HAI nao.
        self.assertEqual(report2.results["a"].commit, sha_a_lan1,
                         "nút 'a' phải giữ nguyên commit cũ, không chạy lại")
        duong_worktree_a = Path(report1.workspaces["a"])
        self.assertTrue(duong_worktree_a.exists(),
                        "worktree của nút đã xong phải còn nguyên, không bị dọn")
        sha_a_con_lai = _git(duong_worktree_a, "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(sha_a_con_lai, sha_a_lan1,
                         "worktree của nút đã xong KHÔNG được có commit mới")

        # Nut b: chay THAT o lan nay, thanh cong.
        self.assertTrue(report2.results["b"].ok)
        self.assertTrue(report2.results["b"].commit)

        # Tich hop: gop hai lan chay lai, khong trung lap task_id nao.
        tat_ca = {**report1.results, **report2.results}
        self.assertEqual(set(tat_ca), {"a", "b"})
        self.assertTrue(all(r.ok for r in tat_ca.values()))

    def test_nut_that_bai_KHONG_duoc_coi_la_xong_khi_resume(self):
        """already_done chua mot ket qua "failed" -> phai chay LAI, khong
        duoc gia vo da xong."""
        from scripts.router_v3.packet import TaskResult

        dag = _dag_2_nut()
        wt = WorktreeManager(self.repo)
        reg = _registry_hai_worker()
        sch = Scheduler(reg, _executor_ghi_that_va_commit(),
                        base_sha=self.base_sha, worktrees=wt, node_timeout=30)
        gia_da_xong = {
            "a": TaskResult(task_id="a", worker_id="W1", status="failed",
                            summary="hỏng ở lần trước"),
        }
        report = sch.run(dag, already_done=gia_da_xong)
        self.assertIn("a", report.results)
        self.assertTrue(report.results["a"].ok, "phải chạy lại và lần này thành công")


if __name__ == "__main__":
    unittest.main()
