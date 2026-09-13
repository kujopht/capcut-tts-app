# -*- coding: utf-8 -*-
"""MÔI GIỚI BẢO TRÌ KHO — mọi rào phải FAIL CLOSED và nói lý do CHÍNH XÁC.

Bối cảnh đo được (dogfood thật, 2026-09-12): việc *"dọn worktree cũ và nhả
xung đột tài nguyên"* — hợp lệ, thuần repo-local — tới được Router V4 rồi
worker `BLOCKED` vì phải tự gọi `git worktree`/ghi `.git`, thứ mà quyền
headless chối.

Cách sửa KHÔNG phải nới quyền, mà là Router làm hộ bằng thao tác CÓ KIỂU.
Nhưng thao tác này có ĐỘT BIẾN, nên bài kiểm ở đây chủ yếu là kiểm những
lần PHẢI TỪ CHỐI.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.control_center.bao_tri_kho import MoiGioiBaoTri
from scripts.control_center.execution.so import SoThucThi
from scripts.control_center.model import (LockKind, Project, Session,
                                          SessionState, Task, TaskState)
from scripts.control_center.store import ControlStore
from scripts.control_center.worktrees import WT_STALE, WorktreeCoordinator
from scripts.router_v3.tien_trinh import an_cua_so


def _git(cwd: Path, *a: str):
    return subprocess.run(["git", *a], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=60, **an_cua_so())


def _kho() -> Path:
    d = Path(tempfile.mkdtemp(prefix="bt-kho-"))
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    (d / "a.txt").write_text("x", encoding="utf-8")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "init")
    return d


class TestBaoTriKho(unittest.TestCase):

    def setUp(self):
        self.repo = _kho()
        self.store = ControlStore(self.repo / ".router" / "control.db")
        self.store.luu_project(Project(project_id="demo", name="demo",
                                       repo_path=str(self.repo)))
        self.wt = WorktreeCoordinator("demo", self.repo, self.store)
        self.so = SoThucThi(self.store)
        self.mg = MoiGioiBaoTri("demo", self.store, worktrees=self.wt,
                                so_thuc_thi=self.so)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.repo, ignore_errors=True)

    def _cay(self, ten="w1", *, ban=False, chu=""):
        h = self.wt.tao_moi(session_id=chu or "s-1", task_id="t-1")
        p = Path(h.path)
        if ban:
            (p / "ban.txt").write_text("chua commit", encoding="utf-8")
        self.store.luu_worktree(path=str(p), project_id="demo",
                                branch=h.branch, owner_session="",
                                state=WT_STALE)
        return p

    # -- rào TUYỆT ĐỐI ----------------------------------------------------
    def test_01_KHONG_go_cay_lam_viec_chinh(self):
        kq = self.mg.go_cay_cu(str(self.repo), ly_do="dọn")
        self.assertFalse(kq.lam_duoc)
        self.assertIn("CÂY LÀM VIỆC CHÍNH", kq.chi_tiet)

    def test_02_KHONG_go_duong_ngoai_pham_vi(self):
        ngoai = Path(tempfile.mkdtemp(prefix="ngoai-"))
        try:
            kq = self.mg.go_cay_cu(str(ngoai), ly_do="dọn")
            self.assertFalse(kq.lam_duoc)
            self.assertIn("nằm ngoài", kq.chi_tiet)
        finally:
            shutil.rmtree(ngoai, ignore_errors=True)

    def test_03_thu_muc_LA_trong_worktrees_van_bi_tu_choi(self):
        la = self.wt.manager.worktree_root / "khong-qua-router"
        la.mkdir(parents=True, exist_ok=True)
        kq = self.mg.go_cay_cu(str(la), ly_do="dọn")
        self.assertFalse(kq.lam_duoc)
        self.assertIn("không có trong sổ", kq.chi_tiet)

    # -- rào theo TRẠNG THÁI SỐNG -----------------------------------------
    def test_04_phien_con_song_so_huu_thi_TU_CHOI(self):
        p = self._cay()
        self.store.luu_session(Session(
            session_id="s-song", project_id="demo", provider="x",
            runtime_id="R", model_id="m", state=SessionState.BUSY))
        self.store.luu_worktree(path=str(p), project_id="demo", branch="b",
                                owner_session="s-song", state=WT_STALE)
        kq = self.mg.go_cay_cu(str(p), ly_do="dọn")
        self.assertFalse(kq.lam_duoc)
        self.assertIn("còn sống", kq.chi_tiet)

    def test_05_lan_thuc_thi_SONG_tro_toi_thi_TU_CHOI(self):
        p = self._cay()
        from scripts.control_center.execution import ke_hoach as KH
        from scripts.control_center.execution import ket_qua as KQ
        from scripts.control_center.execution import y_dinh as YD
        y = YD.tao_y_dinh(project_id="demo", goal="làm gì đó",
                          cau_nguoi_dung="làm gì đó")
        b = KH.BuocKeHoach(buoc_id="a", tieu_de="a", muc_tieu="a")
        self.so.luu(y)
        self.so.luu_ke_hoach(KH.KeHoachThucThi(execution_id=y.execution_id,
                                               buoc=(b,)))
        self.so.luu_buoc(y.execution_id, 1, "a",
                         ket_qua=KQ.HopDongKetQua(
                             task_id="t", buoc_id="a", status="ok",
                             summary="x", worktree=str(p)))
        kq = self.mg.go_cay_cu(str(p), ly_do="dọn")
        self.assertFalse(kq.lam_duoc)
        self.assertIn("còn trỏ tới cây này", kq.chi_tiet)

    def test_06_khong_co_so_thuc_thi_thi_FAIL_CLOSED(self):
        p = self._cay()
        mg = MoiGioiBaoTri("demo", self.store, worktrees=self.wt,
                           so_thuc_thi=None)
        kq = mg.go_cay_cu(str(p), ly_do="dọn")
        self.assertFalse(kq.lam_duoc)
        self.assertIn("từ chối gỡ", kq.chi_tiet)

    # -- rào THAY ĐỔI CHƯA COMMIT -----------------------------------------
    def test_07_cay_BAN_thi_TU_CHOI_khi_chua_cho_phep(self):
        p = self._cay(ban=True)
        kq = self.mg.go_cay_cu(str(p), ly_do="dọn")
        self.assertFalse(kq.lam_duoc)
        self.assertIn("CHƯA COMMIT", kq.chi_tiet)

    def test_08_cay_BAN_go_duoc_khi_CHO_PHEP_tuong_minh(self):
        p = self._cay(ban=True)
        kq = self.mg.go_cay_cu(str(p), ly_do="dọn", cho_phep_ban=True)
        self.assertTrue(kq.lam_duoc, kq.chi_tiet)
        self.assertFalse(p.exists())

    # -- đường AN TOÀN ----------------------------------------------------
    def test_09_cay_cu_SACH_go_duoc(self):
        p = self._cay()
        kq = self.mg.go_cay_cu(str(p), ly_do="dọn dogfood")
        self.assertTrue(kq.lam_duoc, kq.chi_tiet)
        self.assertFalse(p.exists())

    def test_10_hang_trong_so_O_LAI_lam_bang_chung(self):
        """Không xoá bằng chứng: hàng còn, chỉ đổi trạng thái."""
        p = self._cay()
        self.mg.go_cay_cu(str(p), ly_do="dọn")
        self.assertIsNotNone(self.store.worktree(str(p)))

    def test_11_moi_phan_xu_deu_co_KIEM_TOAN(self):
        p = self._cay()
        self.mg.go_cay_cu(str(self.repo), ly_do="x")     # từ chối
        self.mg.go_cay_cu(str(p), ly_do="x")             # cho phép
        sk = [e for e in self.store.su_kien(project_id="demo", limit=50)
              if e["kind"] == "REPO_MAINTENANCE"]
        self.assertGreaterEqual(len(sk), 2, "thiếu dấu vết kiểm toán")

    def test_12_tia_sieu_du_lieu_khong_xoa_thu_muc(self):
        p = self._cay()
        kq = self.mg.tia_sieu_du_lieu()
        self.assertTrue(kq.lam_duoc, kq.chi_tiet)
        self.assertTrue(p.exists(), "prune đã xoá nhầm một cây còn sống")

    # -- khoá --------------------------------------------------------------
    def test_13_nha_khoa_cua_viec_DA_KET_THUC(self):
        from scripts.control_center.locks import LockManager
        self.store.luu_task(Task(task_id="t-xong", project_id="demo",
                                 title="t", objective="t",
                                 state=TaskState.DONE))
        lm = LockManager(self.store)
        lm.xin("demo", [(LockKind.FILESYSTEM, "docs/a.md", "write")],
               task_id="t-xong", session_id="s")
        kq = self.mg.nha_khoa_mo_coi()
        self.assertTrue(kq.lam_duoc)
        self.assertEqual(lm.dang_giu("demo"), [])

    def test_14_GIU_khoa_cua_viec_dang_chay(self):
        from scripts.control_center.locks import LockManager
        self.store.luu_task(Task(task_id="t-chay", project_id="demo",
                                 title="t", objective="t",
                                 state=TaskState.RUNNING))
        lm = LockManager(self.store)
        lm.xin("demo", [(LockKind.FILESYSTEM, "docs/a.md", "write")],
               task_id="t-chay", session_id="s")
        self.mg.nha_khoa_mo_coi()
        self.assertEqual(len(lm.dang_giu("demo")), 1,
                         "đã nhả khoá của một việc ĐANG CHẠY")

    def test_15_KHONG_BAO_GIO_nha_khoa_PRODUCTION(self):
        """Luật cũ không đổi: khoá production không tự thu hồi."""
        from scripts.control_center.locks import LockManager
        self.store.luu_task(Task(task_id="t-xong", project_id="demo",
                                 title="t", objective="t",
                                 state=TaskState.DONE))
        lm = LockManager(self.store)
        lm.xin("demo", [(LockKind.PRODUCTION, "fanfic.world", "write")],
               task_id="t-xong", session_id="s")
        self.mg.nha_khoa_mo_coi()
        self.assertEqual(len(lm.dang_giu("demo")), 1,
                         "đã tự nhả một khoá PRODUCTION")

    # -- API không nhận chuỗi lệnh ----------------------------------------
    def test_16_API_khong_co_cua_hau_chuoi_lenh(self):
        import inspect
        src = inspect.getsource(MoiGioiBaoTri)
        self.assertNotIn("shell=True", src)
        for ten in ("chay_lenh", "lenh", "exec_", "run_cmd"):
            self.assertFalse(hasattr(self.mg, ten),
                             f"môi giới lộ cửa hậu {ten!r}")


if __name__ == "__main__":
    unittest.main()
