"""CLI dùng lại — Router LTS Phase 16.

Không giả lập một tiến trình Router nền không tồn tại — `status`/`workers`
gọi `default_registry(probe=True)` THẬT (dò `agy`/`codex` có thật trên máy
này không), chỉ `--checkpoint` là đường dẫn kiểm soát được để bài kiểm tất định.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3 import checkpoint as cp_mod
from scripts.router_v3 import router_cli as cli


class _CoCheckpointTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rv-cli-"))
        self.duong = self.tmp / "cp.json"

    def _chay(self, *args) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--checkpoint", str(self.duong), *args])
        return buf.getvalue()


class StatusTest(_CoCheckpointTest):
    def test_khong_co_checkpoint_bao_ro(self):
        ra = self._chay("status")
        self.assertIn("AI ROUTER LTS", ra)
        self.assertIn("Chưa có checkpoint", ra)

    def test_co_checkpoint_hien_dung_so_nut(self):
        cp = cp_mod.Checkpoint(dag_state={"a": "ok", "b": "pending"},
                               commits=["deadbeef"], next_actions=["chạy tiếp b"])
        cp_mod.luu(cp, duong=self.duong)
        ra = self._chay("status")
        self.assertIn("Nodes: 1/2", ra)
        self.assertIn("chạy tiếp b", ra)

    def test_luon_co_it_nhat_CLAUDE_LEAD_trong_danh_sach_worker(self):
        ra = self._chay("status")
        self.assertIn("CLAUDE_LEAD", ra)


class WorkersTest(_CoCheckpointTest):
    def test_liet_ke_worker_that(self):
        ra = self._chay("workers")
        self.assertIn("CLAUDE_LEAD", ra)
        self.assertIn("provider=", ra)
        self.assertIn("success_rate=", ra)

    def test_adapter_plugin_GROK01_va_OPENCODE01_co_mat(self):
        """Grok/OpenCode la plugin adapter (Phase 2-4), khong phai AG_SLOTS
        cung — phai xuat hien trong danh sach worker that qua chinh
        register() cua adapter, khong phan cung trong registry core."""
        ra = self._chay("workers")
        self.assertIn("GROK01", ra)
        self.assertIn("OPENCODE01", ra)


class TaskTest(_CoCheckpointTest):
    def test_khong_co_checkpoint_bao_loi(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["--checkpoint", str(self.duong), "task", "a"])
        self.assertEqual(rc, 1)

    def test_nut_khong_ton_tai_bao_loi(self):
        cp_mod.luu(cp_mod.Checkpoint(dag_state={"a": "ok"}), duong=self.duong)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["--checkpoint", str(self.duong), "task", "khong_co"])
        self.assertEqual(rc, 1)

    def test_nut_ton_tai_in_dung_trang_thai(self):
        cp_mod.luu(cp_mod.Checkpoint(dag_state={"a": "ok"},
                                     tests={"a": "5 passed"}), duong=self.duong)
        ra = self._chay("task", "a")
        self.assertIn("a: ok", ra)
        self.assertIn("5 passed", ra)


class ResumeTest(_CoCheckpointTest):
    def test_khong_co_checkpoint_khong_co_gi_resume(self):
        ra = self._chay("resume")
        self.assertIn("không có gì để resume", ra)

    def test_moi_nut_da_ok_khong_can_resume(self):
        cp_mod.luu(cp_mod.Checkpoint(dag_state={"a": "ok", "b": "ok"}),
                  duong=self.duong)
        ra = self._chay("resume")
        self.assertIn("không cần resume", ra)

    def test_con_nut_chua_xong_liet_ke_dung(self):
        cp_mod.luu(cp_mod.Checkpoint(dag_state={"a": "ok", "b": "failed"}),
                  duong=self.duong)
        ra = self._chay("resume")
        self.assertIn("b", ra)
        self.assertNotIn("Còn 1 nút cần resume: a", ra)


class DoctorTest(_CoCheckpointTest):
    def test_chay_khong_nem_loi_va_in_tieu_de(self):
        ra = self._chay("doctor")
        self.assertIn("ROUTER DOCTOR", ra)


if __name__ == "__main__":
    unittest.main()
