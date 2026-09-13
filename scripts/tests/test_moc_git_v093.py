# -*- coding: utf-8 -*-
"""MỐC GIT CHO DỰ ÁN MỚI — V0.9.3.

NGÕ CỤT THỨ HAI của một dự án vừa tạo, đo được trên RouterDogfood02
(2026-09-13) NGAY SAU khi V0.9.3 đã sửa xong phạm vi ghi. Gói việc lần này
đúng — `type=testing`, `allowed_scope=['.']`, `WRITE:FILESYSTEM:.` — mà việc
vẫn dừng:

    BLOCKED: không cấp được cây làm việc: git rev-parse HEAD thất bại:
    fatal: ambiguous argument 'HEAD': unknown revision

`tao_du_an` (V0.9.2) chạy `git init` TRẦN, để lại một kho không có `HEAD`.
Tầng worktree gọi `git rev-parse HEAD` để lấy `base_sha`, nên MỌI việc GHI
trên một dự án vừa tạo đều chết ngay lúc xin cây làm việc.

Sâu hơn một lỗi git: toàn bộ mô hình kiểm định của Router là SO VỚI MỘT MỐC.
Kho không có commit nào thì không có mốc để so.

Và `la_kho_git` — hàm mà docstring của chính nó nói tồn tại để bắt lỗi kho
"ở CỔNG VÀO … chứ không để `git rev-parse HEAD` ném ra giữa đường điều
phối" — hỏi `--is-inside-work-tree`, câu trả `true` cho kho chưa commit. Nên
đúng thứ nó hứa chặn vẫn lọt.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.control_center.bootstrap import co_moc_git, la_kho_git
from scripts.control_center.engine import ControlCenter
from scripts.control_center.tao_du_an import tao_du_an


def _git(d: Path, *a: str):
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


class TestCoMocGit(unittest.TestCase):
    """Phép kiểm mới: kho đã có commit chưa."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="moc-git-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_kho_CHUA_commit___la_kho_git_van_TRUE(self):
        """Khoá lại đúng cái đã lọt: `la_kho_git` KHÔNG đủ để bắt ca này."""
        d = self.tmp / "trong"
        d.mkdir()
        _git(d, "init", "-q")
        self.assertTrue(la_kho_git(d),
                        "vẫn là kho git hợp lệ — nên nó lọt qua cổng cũ")
        self.assertFalse(co_moc_git(d), "nhưng CHƯA có mốc")

    def test_02_kho_DA_commit_thi_co_moc(self):
        d = self.tmp / "co"
        d.mkdir()
        _git(d, "init", "-q")
        (d / "a.txt").write_text("x", encoding="utf-8")
        _git(d, "add", "-A")
        _git(d, "-c", "user.name=t", "-c", "user.email=t@local",
             "commit", "-q", "-m", "seed")
        self.assertTrue(la_kho_git(d))
        self.assertTrue(co_moc_git(d))

    def test_03_khong_phai_kho_thi_FALSE(self):
        d = self.tmp / "khong-kho"
        d.mkdir()
        self.assertFalse(co_moc_git(d))
        self.assertFalse(co_moc_git(self.tmp / "khong-ton-tai"))
        self.assertFalse(co_moc_git(""))


class TestTaoDuAnCoCommit(unittest.TestCase):
    """Dự án do Router tạo phải DÙNG ĐƯỢC NGAY, không chỉ tồn tại."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tao-moc-"))
        self.goc = self.tmp / "RouterProjects"
        self.cc = ControlCenter(root=self.tmp / "data", probe=False,
                                max_parallel=3)

    def tearDown(self):
        try:
            self.cc.shutdown()
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_04_du_an_moi_CO_commit_dau_tien(self):
        kq = tao_du_an(self.cc, "CoMoc", goc=self.goc)
        self.assertTrue(kq.ok, kq.ly_do)
        d = Path(kq.duong)
        self.assertTrue(co_moc_git(d),
                        "dự án mới phải có mốc — nếu không, mọi việc GHI "
                        "trên nó đều chết lúc xin cây làm việc")

    def test_05_commit_dau_tien_CHUA_khung_da_dung(self):
        kq = tao_du_an(self.cc, "KhungTrongCommit", goc=self.goc)
        d = Path(kq.duong)
        ra = _git(d, "ls-tree", "-r", "--name-only", "HEAD").stdout
        self.assertIn("README.md", ra)
        self.assertIn(".gitignore", ra)

    def test_06_cay_lam_viec_SACH_ngay_sau_khi_tao(self):
        """Kho vừa tạo mà `git status` đã bẩn thì mọi cổng diff chấm sai."""
        kq = tao_du_an(self.cc, "Sach", goc=self.goc)
        d = Path(kq.duong)
        self.assertEqual(
            _git(d, "status", "--porcelain").stdout.strip(), "",
            "cây làm việc phải sạch ngay sau khi tạo")

    def test_07_khong_phu_thuoc_cau_hinh_git_TOAN_CUC(self):
        """`user.email` chưa cấu hình toàn cục là chuyện thường.

        Đặt `-c user.*` TẠI LỆNH nên việc tạo dự án không hỏng vì điều đó.
        Bài kiểm này chỉ khẳng định commit có tác giả — tức là lệnh đã tự
        mang danh tính chứ không mượn cấu hình máy.
        """
        kq = tao_du_an(self.cc, "CoTacGia", goc=self.goc)
        d = Path(kq.duong)
        self.assertTrue(
            _git(d, "log", "-1", "--format=%an").stdout.strip())

    def test_08_ghi_chu_noi_DUNG_su_that(self):
        kq = tao_du_an(self.cc, "GhiChu", goc=self.goc)
        van = " ".join(kq.ghi_chu)
        self.assertIn("commit đầu tiên", van)
        self.assertNotIn("chưa có commit", van)

    def test_09_nhan_nuoi_kho_TRONG_thi_KHONG_tu_commit_ho(self):
        """Kho người dùng là tài sản của họ — Router không tự commit vào.

        Đây là ranh giới cố ý: dự án do Router tạo thì Router lo mốc; kho
        nhận nuôi thì Router chỉ được NÓI là thiếu mốc.
        """
        from scripts.control_center.nhan_du_an import nhan_du_an
        ngoai = self.tmp / "kho-nguoi-dung"
        (ngoai / "docs").mkdir(parents=True)
        _git(ngoai, "init", "-q")
        kq = nhan_du_an(self.cc, ngoai, ten="KhoTrong")
        self.assertTrue(kq.ok, kq.ly_do)
        self.assertFalse(co_moc_git(ngoai),
                         "Router KHÔNG được tự tạo commit trong kho đã có")


class TestCongVao(unittest.TestCase):
    """Engine phải NÓI RÕ thay vì để git nổ ra một câu thô."""

    def test_10_engine_kiem_moc_truoc_khi_xin_cay(self):
        goc = Path(__file__).resolve().parents[2]
        van = (goc / "scripts" / "control_center" / "engine.py").read_text(
            encoding="utf-8")
        self.assertIn("co_moc_git(ctx.project.repo_path)", van)
        self.assertIn("PROJECT_REPO_NO_BASELINE", van)
        # Chỉ chặn việc CẦN cây làm việc — việc chỉ đọc vẫn chạy được.
        i = van.index("PROJECT_REPO_NO_BASELINE")
        self.assertIn("worktree_required", van[max(0, i - 600):i])

    def test_11_cau_bao_loi_NOI_DUOC_phai_lam_gi(self):
        goc = Path(__file__).resolve().parents[2]
        van = (goc / "scripts" / "control_center" / "engine.py").read_text(
            encoding="utf-8")
        self.assertIn("chưa có commit nào", van)
        self.assertIn("tạo commit đầu tiên", van)


if __name__ == "__main__":
    unittest.main()
