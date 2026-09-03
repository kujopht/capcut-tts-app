"""Bộ điều phối + vòng chạy — DAG song song, thử lại có chặn, đổi worker.

Dùng adapter GIẢ để chạy tất định (không gọi mạng, không đợi model), nhưng
chạy trên `git worktree` THẬT: cô lập cây làm việc là thứ không giả lập
được cho có — nếu nó hỏng thì hai worker giẫm lên nhau ở lần chạy thật.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional

from scripts.router_v3.dag import DagError, RiskClass, TaskNode
from scripts.router_v3.packet import TaskPacket, TaskResult
from scripts.router_v3.pool import identity as I
from scripts.router_v3.pool import routing
from scripts.router_v3.pool.orchestrator import Orchestrator, OrchestratorError
from scripts.router_v3.pool.runner import RunnerConfig
from scripts.router_v3.pool.store import PoolStore
from scripts.router_v3.registry import Health, WorkerRegistry
from scripts.router_v3.worker_adapter import HealthReport, WorkerAdapter
from scripts.router_v3.worktree import WorktreeManager


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


class FakeAdapter(WorkerAdapter):
    """Adapter giả: ghi đúng thứ được bảo ghi, hoặc hỏng theo kịch bản."""

    provider = "fake"

    def __init__(self, worker_id: str, *, ghi: Optional[Dict[str, str]] = None,
                 hong_lan_dau: int = 0, cham: float = 0.0,
                 luon_hong: bool = False, bao_ok_nhung_khong_ghi: bool = False):
        self.worker_id = worker_id
        self._ghi = ghi or {}
        self._hong_con = hong_lan_dau
        self._cham = cham
        self._luon_hong = luon_hong
        self._doi_tra = bao_ok_nhung_khong_ghi
        self.so_lan_goi = 0
        self.da_nhan: List[str] = []
        self._last: Optional[TaskResult] = None

    def register(self):                                   # pragma: no cover
        raise NotImplementedError

    def health(self) -> HealthReport:
        return HealthReport(Health.HEALTHY, "giả")

    def capabilities(self) -> FrozenSet[str]:
        return frozenset({"implement", "tests", "recon", "review"})

    def start_session(self, *, workspace: Optional[str] = None) -> bool:
        return True

    def send_task(self, packet: TaskPacket) -> TaskResult:
        self.so_lan_goi += 1
        self.da_nhan.append(packet.task_id)
        if self._cham:
            time.sleep(self._cham)
        if self._luon_hong or self._hong_con > 0:
            self._hong_con -= 1
            return TaskResult(task_id=packet.task_id, worker_id=self.worker_id,
                              status="failed", failure_reason="fake_transient",
                              summary="hỏng theo kịch bản")
        da_ghi = []
        if packet.workspace and not self._doi_tra:
            for ten, noi_dung in self._ghi.items():
                p = Path(packet.workspace) / ten
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(noi_dung, encoding="utf-8")
                da_ghi.append(ten)
        kq = TaskResult(task_id=packet.task_id, worker_id=self.worker_id,
                        status="ok", summary=f"{self.worker_id} xong",
                        files_changed=list(self._ghi) if self._ghi else [])
        self._last = kq
        return kq

    def cancel(self) -> None:
        pass

    def result(self) -> Optional[TaskResult]:
        return self._last

    def reset_context(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


def _idn(worker_id: str, realm: str) -> I.Identity:
    return I.Identity(worker_id=worker_id, provider="antigravity",
                      transport=I.Transport.NATIVE, auth_realm=realm,
                      model="fake", pool="GEMINI_FLASH_HIGH",
                      capabilities=frozenset({"implement", "tests", "recon",
                                              "review"}))


class _Nen(unittest.TestCase):
    """Một kho git thật + worktree thật, adapter giả."""

    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.root = Path(self._d.name) / "repo"
        self.root.mkdir()
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "config", "user.email", "t@t")
        _git(self.root, "config", "user.name", "t")
        (self.root / "seed.txt").write_text("seed\n", encoding="utf-8")
        # Như kho thật: `.router/` (sổ việc, worktree, log của Router) bị bỏ
        # qua. Bể CŨNG tự loại đường này khi kiểm "cây bẩn" (xem
        # `Orchestrator._cay_ban`), nên bài kiểm không phụ thuộc dòng này —
        # nó chỉ giữ cho kho tạm giống kho thật.
        (self.root / ".gitignore").write_text(".router/\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "seed")

    def tearDown(self):
        try:
            self._d.cleanup()
        except (OSError, PermissionError):
            pass                      # Windows giu handle git — khong phai loi

    def _dieu_phoi(self, adapters: Dict[str, WorkerAdapter], *,
                   identities=None, max_parallel: int = 4,
                   max_attempts: int = 3) -> Orchestrator:
        ids = identities or [_idn(w, f"windows-user:{w}") for w in adapters]
        pol = routing.RoutingPolicy(prefer={}, max_attempts=max_attempts,
                                    max_parallel=max_parallel)
        return Orchestrator(
            root=self.root, identities=ids, adapters=dict(adapters),
            policy=pol, inline=True, probe_health=False,
            worktrees=WorktreeManager(self.root),
            config=RunnerConfig(max_parallel=max_parallel))


class TestPlan(_Nen):
    def test_plan_do_duoc_be_rong_va_duong_toi_han(self):
        d = self._dieu_phoi({"W1": FakeAdapter("W1")})
        kh = d.plan([
            TaskNode(id="A", objective="a", estimated_seconds=10),
            TaskNode(id="B", objective="b", estimated_seconds=10),
            TaskNode(id="C", objective="c", estimated_seconds=10),
            TaskNode(id="E", objective="e", dependencies=("A", "B", "C"),
                     estimated_seconds=5),
        ])
        self.assertEqual(kh.waves, [["A", "B", "C"], ["E"]])
        self.assertEqual(kh.critical_seconds, 15.0)
        self.assertEqual(kh.recommended_workers, 3)

    def test_plan_tu_choi_chu_trinh(self):
        d = self._dieu_phoi({"W1": FakeAdapter("W1")})
        with self.assertRaises(DagError):
            d.plan([TaskNode(id="A", objective="a", dependencies=("B",)),
                    TaskNode(id="B", objective="b", dependencies=("A",))])

    def test_plan_tu_choi_hai_nut_cung_ghi_mot_cho(self):
        d = self._dieu_phoi({"W1": FakeAdapter("W1")})
        with self.assertRaises(DagError):
            d.plan([TaskNode(id="A", objective="a", write_scope=("pkg",)),
                    TaskNode(id="B", objective="b", write_scope=("pkg/x.py",))])


class TestChayDag(_Nen):
    def test_dag_hinh_kim_cuong_chay_dung_thu_tu(self):
        ws = {f"W{i}": FakeAdapter(f"W{i}") for i in range(1, 5)}
        d = self._dieu_phoi(ws)
        kh = d.plan([
            TaskNode(id="A", objective="a"),
            TaskNode(id="B", objective="b"),
            TaskNode(id="C", objective="c"),
            TaskNode(id="D", objective="d"),
            TaskNode(id="E", objective="e", dependencies=("A", "B", "C")),
            TaskNode(id="F", objective="f", dependencies=("D",)),
            TaskNode(id="G", objective="g", dependencies=("E", "F")),
        ])
        rid = d.dispatch_many(kh)
        jobs = d.wait_all(rid, timeout=60)
        self.assertTrue(all(j.status == "ok" for j in jobs),
                        [(j.node_id, j.status, j.result) for j in jobs])
        theo = {j.node_id: j for j in jobs}
        # G phai bat dau SAU khi E va F ket thuc.
        self.assertGreaterEqual(theo["G"].started_at, theo["E"].ended_at)
        self.assertGreaterEqual(theo["G"].started_at, theo["F"].ended_at)
        self.assertGreaterEqual(theo["E"].started_at, theo["A"].ended_at)

    def test_nut_doc_lap_chay_song_song_that(self):
        ws = {f"W{i}": FakeAdapter(f"W{i}", cham=0.6) for i in range(1, 4)}
        d = self._dieu_phoi(ws, max_parallel=3)
        kh = d.plan([TaskNode(id=n, objective=n) for n in ("A", "B", "C")])
        rid = d.dispatch_many(kh)
        t0 = time.time()
        jobs = d.wait_all(rid, timeout=60)
        wall = time.time() - t0
        self.assertTrue(all(j.status == "ok" for j in jobs))
        tong = sum(j.duration_seconds for j in jobs)
        self.assertGreater(tong, wall,
                           f"song song không thật: tổng {tong}s <= wall {wall}s")

    def test_phu_thuoc_hong_thi_nut_sau_bi_bo_qua(self):
        ws = {"W1": FakeAdapter("W1", luon_hong=True),
              "W2": FakeAdapter("W2", luon_hong=True)}
        d = self._dieu_phoi(ws, max_attempts=1)
        kh = d.plan([TaskNode(id="A", objective="a"),
                     TaskNode(id="B", objective="b", dependencies=("A",))])
        rid = d.dispatch_many(kh)
        jobs = {j.node_id: j for j in d.wait_all(rid, timeout=60)}
        self.assertEqual(jobs["A"].status, "failed")
        self.assertEqual(jobs["B"].status, "skipped")
        self.assertEqual(jobs["B"].result["failure_reason"], "dependency_failed")


class TestCoLapWorktree(_Nen):
    def test_moi_nut_co_ghi_duoc_worktree_rieng(self):
        ws = {"W1": FakeAdapter("W1", ghi={"a/x.py": "1\n"}),
              "W2": FakeAdapter("W2", ghi={"b/y.py": "2\n"})}
        d = self._dieu_phoi(ws)
        kh = d.plan([TaskNode(id="A", objective="a", write_scope=("a",)),
                     TaskNode(id="B", objective="b", write_scope=("b",))])
        rid = d.dispatch_many(kh)
        jobs = {j.node_id: j for j in d.wait_all(rid, timeout=60)}
        self.assertTrue(all(j.status == "ok" for j in jobs.values()),
                        [(k, v.status, v.result) for k, v in jobs.items()])
        nhanh = {jobs["A"].result["branch"], jobs["B"].result["branch"]}
        self.assertEqual(len(nhanh), 2, "hai nút phải ở hai nhánh khác nhau")
        # Cay lam viec CHINH khong duoc bi cham vao. Bo qua `.router/` —
        # do la trang thai CUA Router, khong phai ma nguon worker sua.
        con_lai = [d for d in _git(self.root, "status",
                                   "--porcelain").stdout.splitlines()
                   if ".router/" not in d]
        self.assertEqual(con_lai, [],
                         "worker đã chạm vào cây làm việc chính")

    def test_ghi_ngoai_pham_vi_bi_chan_o_kiem_dinh(self):
        ws = {"W1": FakeAdapter("W1", ghi={"a/x.py": "1\n",
                                           "ngoai/z.py": "2\n"})}
        d = self._dieu_phoi(ws, max_attempts=1)
        kh = d.plan([TaskNode(id="A", objective="a", write_scope=("a",))])
        rid = d.dispatch_many(kh)
        j = d.wait_all(rid, timeout=60)[0]
        self.assertNotEqual(j.status, "ok")
        self.assertFalse(j.validation["passed"])
        self.assertIn("scope", [g["name"] for g in j.validation["gates"]
                                if not g["passed"]])

    def test_bao_ok_nhung_khong_ghi_bi_bat(self):
        ws = {"W1": FakeAdapter("W1", ghi={"a/x.py": "1\n"},
                                bao_ok_nhung_khong_ghi=True)}
        d = self._dieu_phoi(ws, max_attempts=1)
        kh = d.plan([TaskNode(id="A", objective="a", write_scope=("a",))])
        rid = d.dispatch_many(kh)
        j = d.wait_all(rid, timeout=60)[0]
        self.assertNotEqual(j.status, "ok",
                            "worker khai ok mà không ghi gì phải bị chặn")

    def test_tu_choi_giao_viec_co_ghi_khi_cay_ban(self):
        (self.root / "ban.txt").write_text("x\n", encoding="utf-8")
        d = self._dieu_phoi({"W1": FakeAdapter("W1")})
        kh = d.plan([TaskNode(id="A", objective="a", write_scope=("a",))])
        with self.assertRaises(OrchestratorError):
            d.dispatch_many(kh)


class TestThuLaiVaDoiWorker(_Nen):
    def test_thu_lai_cung_worker_khi_hong_thoang_qua(self):
        w = FakeAdapter("W1", hong_lan_dau=1)
        d = self._dieu_phoi({"W1": w}, max_attempts=3)
        kh = d.plan([TaskNode(id="A", objective="a")])
        rid = d.dispatch_many(kh)
        j = d.wait_all(rid, timeout=60)[0]
        self.assertEqual(j.status, "ok")
        self.assertEqual(j.attempt, 2)
        self.assertEqual(w.so_lan_goi, 2)

    def test_doi_worker_khi_mot_worker_hong_lien_tuc(self):
        xau = FakeAdapter("W_XAU", luon_hong=True)
        tot = FakeAdapter("W_TOT")
        d = self._dieu_phoi({"W_XAU": xau, "W_TOT": tot}, max_attempts=3,
                            max_parallel=1)
        kh = d.plan([TaskNode(id="A", objective="a")])
        rid = d.dispatch_many(kh)
        j = d.wait_all(rid, timeout=60)[0]
        self.assertEqual(j.status, "ok", j.result)
        self.assertEqual(j.worker_id, "W_TOT")
        self.assertIn("W_XAU", j.tried)
        self.assertGreaterEqual(tot.so_lan_goi, 1)

    def test_het_luot_thi_dung_han_khong_lap_vo_han(self):
        ws = {"W1": FakeAdapter("W1", luon_hong=True),
              "W2": FakeAdapter("W2", luon_hong=True)}
        d = self._dieu_phoi(ws, max_attempts=2, max_parallel=1)
        kh = d.plan([TaskNode(id="A", objective="a")])
        rid = d.dispatch_many(kh)
        j = d.wait_all(rid, timeout=60)[0]
        self.assertEqual(j.status, "failed")
        self.assertLessEqual(j.attempt, 2, "vòng thử lại không được vượt trần")
        self.assertLessEqual(ws["W1"].so_lan_goi + ws["W2"].so_lan_goi, 2)

    def test_hong_bao_mat_khong_bao_gio_thu_lai(self):
        """Cổng bảo mật hỏng là dừng hẳn — thử lại chỉ tăng cơ hội lọt."""
        w = FakeAdapter("W1", ghi={"a/x.py": 'K = "sk-' + "c" * 30 + '"\n'})
        d = self._dieu_phoi({"W1": w}, max_attempts=5)
        kh = d.plan([TaskNode(id="A", objective="a", write_scope=("a",))])
        rid = d.dispatch_many(kh)
        j = d.wait_all(rid, timeout=60)[0]
        self.assertEqual(j.status, "blocked")
        self.assertEqual(j.attempt, 1, "không được thử lại lỗi bảo mật")
        self.assertEqual(w.so_lan_goi, 1)


class TestDongTuDieuPhoi(_Nen):
    def test_dispatch_khong_chan(self):
        d = self._dieu_phoi({"W1": FakeAdapter("W1", cham=2.0)})
        kh = d.plan([TaskNode(id="A", objective="a")])
        t0 = time.time()
        rid = d.dispatch_many(kh)
        self.assertLess(time.time() - t0, 1.0, "dispatch phải trả về NGAY")
        self.assertTrue(rid)
        d.wait_all(rid, timeout=60)

    def test_wait_any_tra_ve_nut_xong_som_nhat(self):
        ws = {"W1": FakeAdapter("W1", cham=0.2),
              "W2": FakeAdapter("W2", cham=2.5)}
        ids = [_idn("W1", "windows-user:W1"), _idn("W2", "windows-user:W2")]
        d = self._dieu_phoi(ws, identities=ids, max_parallel=2)
        # `preferred_provider` khong tach duoc hai worker cung provider, nen
        # chi kiem "co mot nut ve truoc", khong kiem NUT NAO.
        kh = d.plan([TaskNode(id="A", objective="a"),
                     TaskNode(id="B", objective="b")])
        rid = d.dispatch_many(kh)
        j = d.wait_any(rid, timeout=60)
        self.assertIsNotNone(j)
        self.assertTrue(j.finished)
        j2 = d.wait_any(rid, timeout=60, exclude=[j.job_id])
        self.assertIsNotNone(j2)
        self.assertNotEqual(j2.job_id, j.job_id)

    def test_wait_any_het_gio_tra_none(self):
        d = self._dieu_phoi({"W1": FakeAdapter("W1", cham=5.0)})
        kh = d.plan([TaskNode(id="A", objective="a")])
        rid = d.dispatch_many(kh)
        self.assertIsNone(d.wait_any(rid, timeout=1.0))
        d.wait_all(rid, timeout=60)

    def test_status_hien_worker_va_nut(self):
        d = self._dieu_phoi({"W1": FakeAdapter("W1")})
        kh = d.plan([TaskNode(id="A", objective="a")])
        rid = d.dispatch_many(kh)
        d.wait_all(rid, timeout=60)
        st = d.status(rid)
        self.assertEqual(st["run_id"], rid)
        self.assertTrue(st["workers"])
        self.assertEqual(st["counts"].get("ok"), 1)

    def test_result_tra_phong_bi_day_du(self):
        d = self._dieu_phoi({"W1": FakeAdapter("W1")})
        kh = d.plan([TaskNode(id="A", objective="a")])
        rid = d.dispatch_many(kh)
        d.wait_all(rid, timeout=60)
        r = d.result(run_id=rid, node_id="A")
        pb = r["envelope"]
        for truong in ("status", "worker_id", "job_id", "summary",
                       "files_changed", "branch", "commit", "tests",
                       "artifacts", "warnings", "failure_reason", "timing"):
            self.assertIn(truong, pb, f"phong bì thiếu `{truong}`")
        self.assertIn("duration_seconds", pb["timing"])

    def test_cancel_viec_dang_cho(self):
        d = self._dieu_phoi({"W1": FakeAdapter("W1")})
        rid, jid = d.dispatch(TaskNode(id="A", objective="a"))
        r = d.cancel(jid)
        self.assertTrue(r["stopped_now"])
        self.assertEqual(d.store.job(jid).status, "cancelled")

    def test_retry_sau_khi_can_luot(self):
        w = FakeAdapter("W1", hong_lan_dau=99)
        d = self._dieu_phoi({"W1": w}, max_attempts=1)
        kh = d.plan([TaskNode(id="A", objective="a")])
        rid = d.dispatch_many(kh)
        j = d.wait_all(rid, timeout=60)[0]
        self.assertEqual(j.status, "failed")
        w._hong_con = 0                            # lan sau se thanh cong
        r = d.retry(j.job_id)
        self.assertTrue(r["requeued"])
        jobs = d.wait_all(rid, timeout=60)
        self.assertEqual(jobs[0].status, "ok")

    def test_reassign_chuyen_sang_worker_khac(self):
        xau = FakeAdapter("W_XAU", luon_hong=True)
        tot = FakeAdapter("W_TOT")
        d = self._dieu_phoi({"W_XAU": xau, "W_TOT": tot}, max_attempts=1,
                            max_parallel=1)
        kh = d.plan([TaskNode(id="A", objective="a")])
        rid = d.dispatch_many(kh)
        j = d.wait_all(rid, timeout=60)[0]
        self.assertEqual(j.status, "failed")
        r = d.reassign(j.job_id)
        self.assertTrue(r["reassigned"], r)
        self.assertNotEqual(r["to"], r["from"])
        jobs = d.wait_all(rid, timeout=60)
        self.assertEqual(jobs[0].status, "ok")
        self.assertEqual(jobs[0].worker_id, "W_TOT")


class TestRaoCung(_Nen):
    def test_security_review_khong_bao_gio_di_toi_codex(self):
        from scripts.router_v3.policy import NoWorkerAvailable
        reg = WorkerRegistry()
        codex = I.Identity(worker_id="CODEX01", provider="codex",
                           transport=I.Transport.CLI,
                           auth_realm="codex-cli:default",
                           capabilities=frozenset({"review", "security_review"}),
                           trusted_for_high_risk=True)
        reg.register(codex.to_spec())
        reg.set_health("CODEX01", Health.HEALTHY)
        nut = TaskNode(id="S", objective="review",
                       required_capabilities=("security_review",),
                       risk_class=RiskClass.HIGH)
        with self.assertRaises(NoWorkerAvailable):
            routing.chon_worker(reg, nut)

    def test_uu_tien_cau_hinh_khong_lat_duoc_rao_tin_cay(self):
        from scripts.router_v3.policy import NoWorkerAvailable
        reg = WorkerRegistry()
        yeu = I.Identity(worker_id="AGX", provider="antigravity",
                         transport=I.Transport.NATIVE,
                         auth_realm="windows-user:x", pool="GEMINI_FLASH_HIGH",
                         capabilities=frozenset({"implement"}),
                         trusted_for_high_risk=False)
        reg.register(yeu.to_spec())
        reg.set_health("AGX", Health.HEALTHY)
        pol = routing.RoutingPolicy(prefer={"implement": ["GEMINI_FLASH_HIGH"]},
                                    bonus_top=1000.0)
        nut = TaskNode(id="H", objective="x",
                       required_capabilities=("implement",),
                       risk_class=RiskClass.HIGH)
        with self.assertRaises(NoWorkerAvailable):
            routing.chon_worker(reg, nut, policy=pol)

    def test_loai_tru_het_thi_khong_quay_lai_worker_da_hong(self):
        from scripts.router_v3.policy import NoWorkerAvailable
        reg = WorkerRegistry()
        reg.register(_idn("W1", "windows-user:W1").to_spec())
        reg.set_health("W1", Health.HEALTHY)
        nut = TaskNode(id="A", objective="a",
                       required_capabilities=("implement",))
        with self.assertRaises(NoWorkerAvailable):
            routing.chon_worker(reg, nut, loai_tru=("W1",))


if __name__ == "__main__":
    unittest.main()
