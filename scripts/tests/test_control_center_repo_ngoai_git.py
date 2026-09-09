"""EXE nằm NGOÀI mọi kho git — đúng đường bản đóng gói đi.

SỰ CỐ ĐƯỢC GHÌM Ở ĐÂY (2026-09-09, nghiệm thu tay lần hai).

Người dùng gõ `ê bro` vào `Router Control Center.exe` đặt ở
`C:\\FanficWorkers\\rcc-dispatch-fix\\…`. Việc `fanfic.ta268-1` HỎNG sau
0.84 giây, phiên `s-2755e59837` ở AG01, `result_json` **RỖNG**:

    TASK_CRASHED  WorktreeError: git rev-parse HEAD thất bại:
    fatal: not a git repository (or any of the parent directories): .git

KHÔNG có tiến trình Antigravity nào được sinh. `base_sha()` được tính như
ĐỐI SỐ của `ctx.executor.run(...)`, nên nó ném **trước khi** `run()` kịp
được vào: không adapter, không `start_session`, không `agy`, `pid=None`.

Chuỗi thật:

    goc_kho_chinh(root) chạy `git worktree list`
      -> git hỏng (thư mục EXE không nằm trong kho nào)
      -> bản cũ RƠI VỀ `return goc`  (im lặng)
      -> gieo hai dự án trỏ vào CHÍNH THƯ MỤC EXE
      -> việc đầu tiên chết ở `git rev-parse HEAD`

Vì sao nó ẩn được lâu: bản EXE trước nằm ở `dist/Router Control Center`,
**tình cờ** ở trong worktree router, nên `git` trả về kho thật. Mọi vị trí
cài đặt bình thường — Desktop, `Program Files`, ổ khác — đều dính.

Và vì sao bằng chứng tự động không bắt được: nó GIEO SẴN một dự án trỏ
vào kho git thật, nên nó đi vòng qua đúng đoạn mã đã hỏng. Bài kiểm ở đây
cố ý dựng lại **thư mục gốc nằm ngoài git**, không gieo sẵn gì.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.bootstrap import (  # noqa: E402
    du_an_mac_dinh, goc_kho_chinh, khoi_tao, la_kho_git, worktree_hien_tai)


def _ngoai_git() -> Path:
    """Một thư mục KHÔNG nằm trong kho git nào — như thư mục cài EXE.

    `tempfile` trên Windows nằm dưới `AppData\\Local\\Temp`, ngoài mọi kho.
    Kiểm lại bằng chính `git` thay vì tin điều đó.
    """
    d = Path(tempfile.mkdtemp(prefix="cc-ngoai-git-"))
    p = subprocess.run(["git", "-C", str(d), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=30)
    if p.returncode == 0:                                # pragma: no cover
        raise unittest.SkipTest(f"{d} lại nằm trong một kho git")
    return d


def _kho_git() -> Path:
    d = Path(tempfile.mkdtemp(prefix="cc-kho-git-"))
    (d / "docs").mkdir()
    (d / "docs" / "a.md").write_text("a\n", encoding="utf-8")
    for c in (["git", "init", "-q"], ["git", "config", "user.email", "t@l"],
              ["git", "config", "user.name", "t"], ["git", "add", "-A"],
              ["git", "commit", "-q", "-m", "hạt giống"]):
        subprocess.run(c, cwd=d, check=True, capture_output=True, timeout=60)
    return d


class TestDoKho(unittest.TestCase):
    """Không đoán: ngoài kho git thì trả `None`, không trả bừa `start`."""

    def test_ngoai_kho_git_thi_tra_None_chu_khong_tra_chinh_no(self):
        d = _ngoai_git()
        self.assertIsNone(goc_kho_chinh(d),
                          "rơi về chính thư mục EXE = gieo một dự án hỏng")
        self.assertIsNone(worktree_hien_tai(d))

    def test_trong_kho_git_thi_tra_dung_kho(self):
        d = _kho_git()
        self.assertIsNotNone(goc_kho_chinh(d))
        self.assertEqual(Path(worktree_hien_tai(d)).resolve(), d.resolve())

    def test_la_kho_git(self):
        self.assertFalse(la_kho_git(_ngoai_git()))
        self.assertTrue(la_kho_git(_kho_git()))
        self.assertFalse(la_kho_git(""))
        self.assertFalse(la_kho_git(Path(tempfile.gettempdir()) / "khong-co"))


class TestGieoDuAn(unittest.TestCase):
    def test_ngoai_kho_git_thi_KHONG_gieo_du_an_nao(self):
        self.assertEqual(du_an_mac_dinh(root=_ngoai_git()), [])

    def test_trong_kho_git_thi_van_gieo_du(self):
        ds = du_an_mac_dinh(root=_kho_git())
        self.assertEqual(len(ds), 2)
        for p in ds:
            self.assertTrue(la_kho_git(p.repo_path),
                            f"{p.project_id} trỏ vào chỗ không phải kho git")

    def test_khoi_tao_ghi_su_kien_noi_ro_phai_lam_gi(self):
        from scripts.control_center.store import ControlStore
        goc = _ngoai_git()
        st = ControlStore(root=goc)
        self.addCleanup(st.close)
        self.assertEqual(khoi_tao(st, root=goc), [])
        kinds = [e["kind"] for e in st.su_kien(limit=20)]
        self.assertIn("PROJECT_SEED_SKIPPED", kinds)
        e = next(x for x in st.su_kien(limit=20)
                 if x["kind"] == "PROJECT_SEED_SKIPPED")
        self.assertEqual(e["level"], "WARNING")
        self.assertIn("kho git", e["detail"])

    def test_khong_gieo_du_an_TRO_VAO_CHINH_THU_MUC_EXE(self):
        """Chính hình dạng của sự cố: dự án trỏ vào thư mục EXE."""
        goc = _ngoai_git()
        for p in du_an_mac_dinh(root=goc):               # phải rỗng
            self.assertNotEqual(Path(p.repo_path).resolve(), goc.resolve())


class TestViecChiDocKhongChetViGit(unittest.TestCase):
    """`base_sha()` chỉ được tính khi việc THẬT SỰ cần worktree."""

    def test_engine_khong_tinh_base_sha_cho_viec_chi_doc(self):
        import ast
        src = (GOC / "scripts/control_center/engine.py").read_text(
            encoding="utf-8")
        cay = ast.parse(src)
        # Moi lan goi `base_sha` phai nam trong mot bieu thuc DIEU KIEN
        # (`IfExp`) co dieu kien nhac toi `worktree_required`. Duyet cay
        # chu khong cat chuoi theo `col_offset` — `col_offset` la CỘT, cat
        # chuoi bang no cho ra mot doan van ban vo nghia.
        trong_ifexp = set()
        for n in ast.walk(cay):
            if not isinstance(n, ast.IfExp):
                continue
            if "worktree_required" not in ast.dump(n.test):
                continue
            for con in ast.walk(n):
                if isinstance(con, ast.Call) \
                        and isinstance(con.func, ast.Attribute) \
                        and con.func.attr == "base_sha":
                    trong_ifexp.add(con.lineno)

        goi = [n.lineno for n in ast.walk(cay)
               if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute)
               and n.func.attr == "base_sha"]
        self.assertTrue(goi, "không tìm thấy lời gọi `base_sha` nào")
        tran = sorted(set(goi) - trong_ifexp)
        self.assertEqual(
            tran, [],
            f"engine.py dòng {tran}: tính `base_sha` vô điều kiện — một "
            f"việc CHỈ ĐỌC sẽ chết vì git ở một kho không hợp lệ")

    def test_hop_dong_chi_doc_khong_doi_worktree(self):
        from scripts.router_v4.contract import TaskContract
        c = TaskContract(task_id="t", objective="đọc")
        self.assertFalse(c.execution.worktree_required)


class TestCongVaoKhoKhongHopLe(unittest.TestCase):
    """Việc trên một dự án không-phải-kho phải hỏng CÓ LÝ DO, không crash."""

    def test_project_repo_invalid_nam_trong_KHONG_THU_LAI(self):
        from scripts.control_center.engine import ControlCenter
        self.assertIn("project_repo_invalid", ControlCenter.KHONG_THU_LAI,
                      "đổi nhà cung cấp không sửa được một đường dẫn sai — "
                      "thử lại chỉ tạo thêm phiên vô ích")

    def test_engine_kiem_kho_TRUOC_khi_chay_executor(self):
        src = (GOC / "scripts/control_center/engine.py").read_text(
            encoding="utf-8")
        i_kiem = src.find("la_kho_git(ctx.project.repo_path)")
        i_chay = src.find("ctx.executor.run(")
        self.assertGreater(i_kiem, 0, "thiếu cổng kiểm kho git")
        self.assertLess(i_kiem, i_chay,
                        "phải kiểm TRƯỚC khi gọi executor")


if __name__ == "__main__":
    unittest.main(verbosity=2)
