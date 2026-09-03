"""Kiểm định kết quả — không tin worker tự khai PASS.

Bài kiểm quan trọng nhất ở đây là `test_bao_ok_nhung_dia_sach_bi_chan`: đó
chính xác là chế độ hỏng đã ĐO ĐƯỢC trong `native_worker.py` — worker trả
`SUCCESS` tự tin trong khi công cụ ghi tệp bị từ chối quyền và không có gì
lên đĩa.
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.router_v3.packet import TaskResult
from scripts.router_v3.pool import validation as V


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


class _KhoTam(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.wt = Path(self._d.name)
        _git(self.wt, "init", "-q")
        _git(self.wt, "config", "user.email", "t@t")
        _git(self.wt, "config", "user.name", "t")
        (self.wt / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(self.wt, "add", "-A")
        _git(self.wt, "commit", "-qm", "seed")

    def tearDown(self):
        self._d.cleanup()


class TestCongDiff(_KhoTam):
    def test_bao_ok_nhung_dia_sach_bi_chan(self):
        kq = TaskResult(task_id="A", worker_id="AG01", status="ok",
                        summary="đã tạo module", files_changed=["a.py"])
        bc = V.kiem_dinh(kq, worktree=self.wt, write_scope=("a.py",))
        self.assertFalse(bc.passed)
        self.assertIn("diff", bc.failed_gates)
        chi_tiet = " ".join(g.detail for g in bc.gates if not g.passed)
        self.assertIn("SẠCH", chi_tiet)

    def test_sua_that_thi_dat(self):
        (self.wt / "a.py").write_text("x = 1\n", encoding="utf-8")
        kq = TaskResult(task_id="A", worker_id="AG01", status="ok",
                        summary="đã tạo module", files_changed=["a.py"])
        bc = V.kiem_dinh(kq, worktree=self.wt, write_scope=("a.py",))
        self.assertTrue(bc.passed, bc.failed_gates)
        self.assertEqual(bc.files_changed_observed, ["a.py"])

    def test_khong_khai_ma_dia_ban_bi_chan(self):
        (self.wt / "la.py").write_text("x\n", encoding="utf-8")
        kq = TaskResult(task_id="A", worker_id="AG01", status="ok",
                        summary="xong", files_changed=[])
        bc = V.kiem_dinh(kq, worktree=self.wt, write_scope=("la.py",))
        self.assertFalse(bc.passed)
        self.assertIn("diff", bc.failed_gates)

    def test_viec_chi_doc_ma_sua_dia_bi_chan(self):
        (self.wt / "x.py").write_text("x\n", encoding="utf-8")
        kq = TaskResult(task_id="A", worker_id="AG01", status="ok",
                        summary="đã đọc")
        bc = V.kiem_dinh(kq, worktree=self.wt, write_scope=())
        self.assertFalse(bc.passed)
        self.assertIn("diff", bc.failed_gates)

    def test_tep_chua_theo_doi_van_duoc_dem(self):
        (self.wt / "moi.py").write_text("x\n", encoding="utf-8")
        self.assertEqual(V.tep_da_doi(self.wt), ["moi.py"])


class TestCongPhamVi(_KhoTam):
    def test_ghi_ngoai_pham_vi_bi_chan(self):
        (self.wt / "a.py").write_text("x\n", encoding="utf-8")
        (self.wt / "ngoai.py").write_text("y\n", encoding="utf-8")
        kq = TaskResult(task_id="A", worker_id="AG01", status="ok",
                        summary="xong", files_changed=["a.py", "ngoai.py"])
        bc = V.kiem_dinh(kq, worktree=self.wt, write_scope=("a.py",))
        self.assertFalse(bc.passed)
        self.assertIn("scope", bc.failed_gates)
        self.assertEqual(bc.scope_violations, ["ngoai.py"])

    def test_thu_muc_trong_pham_vi_duoc_phep(self):
        (self.wt / "pkg").mkdir()
        (self.wt / "pkg" / "a.py").write_text("x\n", encoding="utf-8")
        kq = TaskResult(task_id="A", worker_id="AG01", status="ok",
                        summary="xong", files_changed=["pkg/a.py"])
        bc = V.kiem_dinh(kq, worktree=self.wt, write_scope=("pkg",))
        self.assertTrue(bc.passed, bc.failed_gates)


class TestCongBaoMat(_KhoTam):
    def test_diff_chua_thu_giong_credential_bi_chan(self):
        (self.wt / "a.py").write_text(
            'TOKEN = "ghp_' + "A" * 30 + '"\n', encoding="utf-8")
        kq = TaskResult(task_id="A", worker_id="AG01", status="ok",
                        summary="xong", files_changed=["a.py"])
        bc = V.kiem_dinh(kq, worktree=self.wt, write_scope=("a.py",))
        self.assertFalse(bc.passed)
        self.assertIn("security", bc.failed_gates)

    def test_tep_MOI_chua_bi_mat_van_bi_bat(self):
        """`git diff` không hiện tệp chưa theo dõi — nếu cổng chỉ đọc diff
        thì một tệp bí mật tạo mới lọt hoàn toàn."""
        (self.wt / "moi.py").write_text(
            'K = "sk-' + "b" * 30 + '"\n', encoding="utf-8")
        kq = TaskResult(task_id="A", worker_id="AG01", status="ok",
                        summary="xong", files_changed=["moi.py"])
        bc = V.kiem_dinh(kq, worktree=self.wt, write_scope=("moi.py",))
        self.assertFalse(bc.passed)
        self.assertIn("security", bc.failed_gates)

    def test_dung_duong_cam_bi_chan(self):
        (self.wt / ".github").mkdir()
        (self.wt / ".github" / "workflows").mkdir()
        (self.wt / ".github" / "workflows" / "ci.yml").write_text(
            "on: push\n", encoding="utf-8")
        kq = TaskResult(task_id="A", worker_id="AG01", status="ok",
                        summary="xong",
                        files_changed=[".github/workflows/ci.yml"])
        bc = V.kiem_dinh(kq, worktree=self.wt,
                         write_scope=(".github/workflows",))
        self.assertFalse(bc.passed)
        self.assertIn("security", bc.failed_gates)


class TestCongTest(_KhoTam):
    def test_lenh_ngoai_danh_sach_trang_bi_tu_choi(self):
        cong, da = V.cong_test([["curl", "http://x"]], self.wt)
        self.assertFalse(cong.passed)
        self.assertIn("danh sách trắng", cong.detail)
        self.assertEqual(da, [])

    def test_test_do_thi_cong_hong(self):
        (self.wt / "t.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
        cong, da = V.cong_test([["python", "t.py"]], self.wt)
        self.assertFalse(cong.passed)
        self.assertIn("rc=3", cong.detail)
        self.assertEqual(da, ["python t.py"])

    def test_test_xanh_thi_cong_dat(self):
        (self.wt / "t.py").write_text("print('ok')\n", encoding="utf-8")
        cong, da = V.cong_test([["python", "t.py"]], self.wt)
        self.assertTrue(cong.passed, cong.detail)
        self.assertEqual(da, ["python t.py"])

    def test_khong_yeu_cau_test_thi_bo_qua(self):
        cong, da = V.cong_test([], self.wt)
        self.assertTrue(cong.passed)
        self.assertEqual(da, [])


class TestCongHinhDang(unittest.TestCase):
    def test_ok_ma_rong_summary_bi_chan(self):
        g = V.cong_hinh_dang(TaskResult(task_id="A", worker_id="W",
                                        status="ok", summary="  "))
        self.assertFalse(g.passed)

    def test_ok_ma_co_blocker_bi_chan(self):
        g = V.cong_hinh_dang(TaskResult(task_id="A", worker_id="W", status="ok",
                                        summary="xong", blockers=["kẹt"]))
        self.assertFalse(g.passed)

    def test_status_la_bi_chan(self):
        g = V.cong_hinh_dang(TaskResult(task_id="A", worker_id="W",
                                        status="tuyệt vời"))
        self.assertFalse(g.passed)


if __name__ == "__main__":
    unittest.main()
