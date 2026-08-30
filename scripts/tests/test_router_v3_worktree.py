"""Worktree ↔ bộ lập lịch — Router V3.1, Phase 1.

Dùng một kho git THẬT trong thư mục tạm. Cô lập là thứ không giả lập được:
điều cần chứng minh là hai worker chạy song song thực sự ghi vào hai cây khác
nhau, và điều đó chỉ đúng nếu `git worktree` thật sự làm việc đó.

Kho tạm bị xoá ở `tearDown`; kho THẬT của dự án không bị đụng tới.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.dag import RiskClass, TaskDag, TaskNode
from scripts.router_v3.registry import (ExecutionType, Health, WorkerRegistry,
                                        WorkerSpec)
from scripts.router_v3.scheduler import Scheduler
from scripts.router_v3.worktree import WorktreeError, WorktreeManager


def _git(cwd, *a):
    p = subprocess.run(["git", "-C", str(cwd), *a], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(a[:2])}: {p.stderr[:200]}")
    return p.stdout


class _KhoTam(unittest.TestCase):
    """Kho git thật, dùng một lần, trong thư mục tạm."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rv31-"))
        _git(self.tmp, "init", "-q", "-b", "main")
        _git(self.tmp, "config", "user.email", "t@t.test")
        _git(self.tmp, "config", "user.name", "t")
        for ten in ("a.txt", "b.txt"):
            (self.tmp / ten).write_text("goc\n", encoding="utf-8")
        _git(self.tmp, "add", "-A")
        _git(self.tmp, "commit", "-q", "-m", "goc")
        self.wt = WorktreeManager(self.tmp)
        self.sha = self.wt.base_sha()

    def tearDown(self):
        # Go worktree truoc de git khong giu khoa tep tren Windows.
        try:
            for w in self.wt.list_worktrees():
                p = w.get("worktree", "")
                if p and Path(p).resolve() != self.tmp.resolve():
                    subprocess.run(["git", "-C", str(self.tmp), "worktree",
                                    "remove", "--force", p],
                                   capture_output=True, text=True)
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reg(self, n=2):
        r = WorkerRegistry()
        for i in range(n):
            wid = f"W{i}"
            r.register(WorkerSpec(worker_id=wid, provider_family="antigravity",
                                  execution_type=ExecutionType.LOCAL_CLI,
                                  pool="P",
                                  capabilities=frozenset({"implement"}),
                                  max_concurrent=1))
            r.set_health(wid, Health.HEALTHY)
        return r


class DungWorktreeTest(_KhoTam):
    def test_tao_worktree_va_nhanh_rieng(self):
        h = self.wt.create("AG01", "T1", base_sha=self.sha)
        self.assertTrue(h.path.exists())
        self.assertEqual(h.branch, "router/AG01/T1")
        self.assertEqual(h.base_sha, self.sha)
        self.assertTrue((h.path / "a.txt").exists())

    def test_hai_worker_duoc_hai_cay_KHAC_NHAU(self):
        a = self.wt.create("AG01", "T1", base_sha=self.sha)
        b = self.wt.create("AG02", "T2", base_sha=self.sha)
        self.assertNotEqual(a.path, b.path)
        (a.path / "a.txt").write_text("A sua\n", encoding="utf-8")
        (b.path / "a.txt").write_text("B sua\n", encoding="utf-8")
        # Cô lập THẬT: mỗi cây giữ nội dung riêng, không giẫm lên nhau.
        self.assertEqual((a.path / "a.txt").read_text(encoding="utf-8"), "A sua\n")
        self.assertEqual((b.path / "a.txt").read_text(encoding="utf-8"), "B sua\n")
        self.assertEqual((self.tmp / "a.txt").read_text(encoding="utf-8"), "goc\n")

    def test_KHONG_ghi_de_worktree_da_co(self):
        self.wt.create("AG01", "T1", base_sha=self.sha)
        with self.assertRaises(WorktreeError) as ctx:
            self.wt.create("AG01", "T1", base_sha=self.sha)
        self.assertIn("KHÔNG ghi đè", str(ctx.exception))

    def test_base_sha_khong_hop_le_bi_tu_choi(self):
        with self.assertRaises(WorktreeError):
            self.wt.create("AG01", "T1", base_sha="deadbeef" * 5)

    def test_pham_vi_ghi_duoc_kiem_that(self):
        h = self.wt.create("AG01", "T1", base_sha=self.sha)
        (h.path / "a.txt").write_text("sua\n", encoding="utf-8")
        self.assertEqual(self.wt.verify_scope(h, ["a.txt"]), [])
        self.assertEqual(self.wt.verify_scope(h, ["b.txt"]), ["a.txt"])

    def test_tep_moi_ngoai_pham_vi_bi_bat(self):
        h = self.wt.create("AG01", "T1", base_sha=self.sha)
        (h.path / "la.txt").write_text("x\n", encoding="utf-8")
        self.assertIn("la.txt", self.wt.verify_scope(h, ["a.txt"]))

    def test_worktree_KHONG_bi_tu_xoa(self):
        """Một worktree hỏng là bằng chứng để điều tra."""
        h = self.wt.create("AG01", "T1", base_sha=self.sha)
        self.assertTrue(h.path.exists())
        self.assertEqual(self.wt.stale(), [])   # cua chinh luot nay -> khong cu


class LapLichCoLapTest(_KhoTam):
    def _exec_ghi(self, ten_tep="a.txt"):
        def f(packet, worker):
            # Worker THAT lam viec trong `packet.workspace`.
            self.assertTrue(packet.workspace, "goi viec phai mang workspace")
            (Path(packet.workspace) / ten_tep).write_text(
                f"{packet.task_id}\n", encoding="utf-8")
            return '{"status":"ok","summary":"xong"}', 0.01
        return f

    def test_nut_CO_GHI_khong_co_manager_bi_TU_CHOI(self):
        """Chạy chúng trên cây chung sẽ để hai worker giẫm lên nhau."""
        d = TaskDag([TaskNode(id="a", objective="x", write_scope=("a.txt",))])
        s = Scheduler(self._reg(), self._exec_ghi(), max_parallel=1)
        with self.assertRaises(WorktreeError) as ctx:
            s.run(d)
        self.assertIn("CÓ GHI", str(ctx.exception))

    def test_cay_chinh_BAN_thi_tu_choi(self):
        """SHA gốc phải là điểm xuất phát SẠCH."""
        (self.tmp / "a.txt").write_text("chua commit\n", encoding="utf-8")
        d = TaskDag([TaskNode(id="a", objective="x", write_scope=("a.txt",))])
        s = Scheduler(self._reg(), self._exec_ghi(), max_parallel=1,
                      base_sha=self.sha, worktrees=self.wt)
        with self.assertRaises(WorktreeError) as ctx:
            s.run(d)
        self.assertIn("BẨN", str(ctx.exception))

    def test_nut_chi_doc_KHONG_can_worktree(self):
        d = TaskDag([TaskNode(id="r", objective="doc", read_scope=("a.txt",))])
        s = Scheduler(self._reg(), lambda p, w: ('{"status":"ok"}', 0.01),
                      max_parallel=1, base_sha=self.sha, worktrees=self.wt)
        bc = s.run(d)
        self.assertTrue(bc.ok)
        self.assertEqual(bc.workspaces, {})

    def test_hai_nut_ghi_SONG_SONG_vao_hai_cay_rieng(self):
        d = TaskDag([
            TaskNode(id="A", objective="x", write_scope=("a.txt",)),
            TaskNode(id="B", objective="y", write_scope=("b.txt",)),
        ])
        s = Scheduler(self._reg(2), self._exec_ghi(), max_parallel=2,
                      base_sha=self.sha, worktrees=self.wt)
        bc = s.run(d)
        self.assertEqual(len(bc.workspaces), 2)
        self.assertNotEqual(bc.workspaces["A"], bc.workspaces["B"])
        # Cay CHINH khong bi dong toi.
        self.assertEqual((self.tmp / "a.txt").read_text(encoding="utf-8"), "goc\n")

    def test_ghi_NGOAI_pham_vi_bi_chan_lai(self):
        """`write_scope` là HỢP ĐỒNG, và worker có thể phá nó. Nếu tích hợp
        tin kết quả mà không kiểm, thay đổi ngoài phạm vi sẽ lên main."""
        d = TaskDag([TaskNode(id="A", objective="x", write_scope=("a.txt",))])
        # Worker ghi `b.txt` du chi duoc phep ghi `a.txt`.
        s = Scheduler(self._reg(), self._exec_ghi("b.txt"), max_parallel=1,
                      base_sha=self.sha, worktrees=self.wt)
        bc = s.run(d)
        self.assertFalse(bc.ok)
        self.assertEqual(bc.results["A"].status, "blocked")
        self.assertIn("A", bc.scope_violations)
        self.assertIn("b.txt", bc.scope_violations["A"][0])

    def test_ket_qua_mang_nhanh_de_tich_hop_doc_lai(self):
        """Tích hợp phải tiêu thụ COMMIT/nhánh, không phải trạng thái tệp
        đang thay đổi đồng thời."""
        d = TaskDag([TaskNode(id="A", objective="x", write_scope=("a.txt",))])
        s = Scheduler(self._reg(), self._exec_ghi(), max_parallel=1,
                      base_sha=self.sha, worktrees=self.wt)
        bc = s.run(d)
        self.assertIn("branch=router/", bc.results["A"].integration_notes)
        self.assertIn(self.sha[:12], bc.results["A"].integration_notes)


if __name__ == "__main__":
    unittest.main()


class NativeWorkerHopDongTest(unittest.TestCase):
    """`native_worker` — hợp đồng, không gọi mạng.

    Bài quan trọng nhất ở đây khoá lại một điều đã ĐO ĐƯỢC: `agy --print`
    trả `status=SUCCESS` cho một việc sửa tệp mà **không hề sửa tệp nào**.
    Nên `ok` của worker KHÔNG BAO GIỜ đủ để kết luận một nút CÓ GHI đã xong.
    """

    def test_tach_bach_do_tre_model_va_overhead(self):
        from scripts.router_v3.native_worker import NativeRun

        r = NativeRun(ok=True, wall_seconds=6.5, model_seconds=1.42)
        self.assertAlmostEqual(r.overhead_seconds, 5.08, places=2)
        self.assertGreater(r.overhead_ratio, 0.7)

    def test_overhead_khong_bao_gio_am(self):
        from scripts.router_v3.native_worker import NativeRun

        # `duration_seconds` cua agy co the nhinh hon wall do lam tron.
        r = NativeRun(wall_seconds=1.0, model_seconds=1.2)
        self.assertEqual(r.overhead_seconds, 0.0)

    def test_mac_dinh_KHONG_cho_sua_tep(self):
        """Một worker chỉ-đọc không được có quyền ghi."""
        import inspect

        from scripts.router_v3.native_worker import run_native

        sig = inspect.signature(run_native)
        self.assertIs(sig.parameters["allow_edits"].default, False)

    def test_ok_cua_worker_KHONG_du_de_ket_luan_da_ghi(self):
        """Đã đo: agy trả SUCCESS + "XONG." mà không tạo tệp nào. Lưới thật
        là `verify_scope` trên tệp THẬT, không phải lời worker."""
        from scripts.router_v3.worktree import WorktreeManager

        self.assertTrue(hasattr(WorktreeManager, "verify_scope"))


class WarmWorkerHopDongTest(unittest.TestCase):
    """Worker ấm — hợp đồng, không gọi mạng."""

    def test_hinh_dang_ban_tin_dung_chuan(self):
        """PHẢI có `event` (không phải `type`) và `message`. Sai hình dạng thì
        CLI trả ERROR: 'stream input message is missing the "event" field'."""
        import json as _json

        from scripts.router_v3.native_worker import _ban_tin

        d = _json.loads(_ban_tin("xin chao"))
        self.assertEqual(d["event"], "user")
        self.assertEqual(d["message"]["role"], "user")
        self.assertEqual(d["message"]["content"], "xin chao")
        self.assertNotIn("type", d)

    def test_thieu_ket_qua_KHONG_bi_nuot(self):
        """Lô bị cắt giữa chừng mà trả về ít kết quả hơn số việc sẽ làm nơi
        gọi GHÉP NHẦM kết quả với việc — hỏng im lặng, khó thấy nhất."""
        from unittest import mock

        from scripts.router_v3 import native_worker as nw

        gia = mock.Mock()
        gia.stdout = ('{"event":"result","result":{"status":"SUCCESS",'
                      '"response":"1"}}\n')
        gia.stderr = ""
        with mock.patch.object(nw.subprocess, "run", return_value=gia), \
             mock.patch.object(nw, "find_agy", return_value="agy"):
            ra = nw.run_warm_batch(["a", "b", "c"], model="m")
        self.assertEqual(len(ra), 3)
        self.assertTrue(ra[0].ok)
        self.assertFalse(ra[1].ok)
        self.assertIn("không nhận được kết quả", ra[1].error)

    def test_khong_co_agy_thi_moi_viec_deu_that_bai(self):
        from unittest import mock

        from scripts.router_v3 import native_worker as nw

        with mock.patch.object(nw, "find_agy", return_value=None):
            ra = nw.run_warm_batch(["a", "b"], model="m")
        self.assertEqual(len(ra), 2)
        self.assertFalse(any(r.ok for r in ra))


class GhiTepCanWorkspaceTest(unittest.TestCase):
    def test_allow_edits_ma_thieu_workspace_bi_TU_CHOI(self):
        """`--add-dir` là BẮT BUỘC cho việc có ghi. Thiếu nó, worker im lặng
        không làm gì — chính điểm này từng làm một phép đo kết luận nhầm rằng
        headless không ghi được."""
        from scripts.router_v3.native_worker import run_native

        r = run_native("x", model="m", allow_edits=True, workspace=None)
        self.assertFalse(r.ok)
        self.assertIn("add-dir", r.error)
