"""Bài kiểm ALLOWLIST của agent — khoá lại cả hai chiều.

Quyền `command(...)` của `agy` khớp **chuỗi chính xác** (đo 2026-09-08:
`command(git)` và `command(git *)` đều KHÔNG cho chạy `git status
--porcelain`). Nên có đúng hai cách hỏng, và bài kiểm ở đây chặn cả hai:

    LỆCH   danh sách trong mã và tệp settings thật trôi khỏi nhau. Lúc đó
           agent nhận một chuỗi lệnh mà `agy` từ chối — hỏng LẶNG LẼ, mất
           trắng một lượt, và thông báo thật chỉ nằm ở stderr.
    NỚI    ai đó thêm `command(*)` (hoặc một escape-hatch như
           `escalate_admin`) cho tiện. Đó là truy cập hệ tệp tuỳ ý bằng
           shell, đúng thứ cả tầng này tồn tại để không phải cấp.

BÀI KIỂM NÀY CHẠY OFFLINE. Nó không gọi `agy`, không tốn quota, chạy được
trong CI. Phần chứng minh bằng tiến trình `agy` THẬT (lệnh được phép chạy
được, lệnh bị cấm vẫn bị từ chối) nằm ở
`scripts/control_center_allowlist_proof.py`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.control_center.planner import (KHONG_CAP_CHO_AGENT,
                                            LENH_CHO_PHEP, _TOOL)

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "scripts" / "cc_agent_tool.py"
SETTINGS = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"

#: Khong mot muc allowlist nao duoc chua nhung chuoi nay.
CAM = ("command(*)", "read_file(*)", "write_file(*)", "escalate_admin",
       "dangerously", "bypassPermissions")


class TestAllowlistKhopSettings(unittest.TestCase):
    """Danh sách trong mã và tệp settings thật không được lệch nhau."""

    @unittest.skipUnless(SETTINGS.is_file(),
                         "máy này chưa có settings.json của agy")
    def test_settings_that_cho_phep_DUNG_nhung_lenh_trong_ma(self):
        d = json.loads(SETTINGS.read_text(encoding="utf-8"))
        allow = list(((d.get("permissions") or {}).get("allow")) or [])
        mong_doi = [f"command({c})" for c in LENH_CHO_PHEP]
        self.assertEqual(sorted(allow), sorted(mong_doi),
                         "allowlist trong settings.json đã trôi khỏi "
                         "`planner.LENH_CHO_PHEP`")

    @unittest.skipUnless(SETTINGS.is_file(), "chưa có settings.json")
    def test_settings_KHONG_chua_ky_tu_dai_dien_hay_escape_hatch(self):
        tho = SETTINGS.read_text(encoding="utf-8")
        for x in CAM:
            with self.subTest(cam=x):
                self.assertNotIn(x, tho)

    @unittest.skipUnless(SETTINGS.is_file(), "chưa có settings.json")
    def test_dong_tu_bi_giu_lai_thi_KHONG_co_trong_settings(self):
        """Nếu có động từ nào bị giữ lại, nó phải vắng mặt thật sự.

        Hiện `KHONG_CAP_CHO_AGENT` rỗng — cả ba động từ đều được cấp. Bài
        kiểm vẫn giữ vì nó là chỗ khoá cho lần sau có ai đó muốn giữ lại một
        động từ: giữ trong danh sách mà quên gỡ khỏi settings là đúng loại
        lệch âm thầm mà tệp này tồn tại để chặn.
        """
        tho = SETTINGS.read_text(encoding="utf-8")
        for c in KHONG_CAP_CHO_AGENT:
            with self.subTest(lenh=c):
                self.assertNotIn(c, tho)

    def test_MOI_dong_tu_cua_wrapper_deu_duoc_cap_hoac_bi_giu_TUONG_MINH(self):
        """Không động từ nào được rơi vào khoảng giữa.

        Một động từ có trong wrapper mà không nằm ở `LENH_CHO_PHEP` cũng
        không ở `KHONG_CAP_CHO_AGENT` là một quyết định chưa ai ra — agent
        sẽ gọi nó, bị từ chối lặng lẽ, và mất trắng một lượt.
        """
        from scripts.cc_agent_tool import DONG_TU
        cap = {c.rsplit(" ", 1)[1] for c in LENH_CHO_PHEP}
        giu = {c.rsplit(" ", 1)[1] for c in KHONG_CAP_CHO_AGENT}
        self.assertEqual(set(DONG_TU), cap | giu)
        self.assertEqual(cap & giu, set(), "không được vừa cấp vừa giữ")


class TestAllowlistHopLe(unittest.TestCase):
    """Mỗi chuỗi được phép phải THẬT SỰ chạy được, và phải hẹp."""

    def test_moi_lenh_tro_toi_wrapper_bang_duong_dan_TUYET_DOI(self):
        for c in LENH_CHO_PHEP:
            with self.subTest(lenh=c):
                self.assertIn("cc_agent_tool.py", c)
                self.assertTrue(c.startswith("python C:\\"),
                                "đường dẫn tuyệt đối ghim SCRIPT NÀO chạy; "
                                "đường dẫn tương đối để `cwd` đổi mục tiêu")
                self.assertNotIn("*", c)

    def test_duong_dan_wrapper_SUY_RA_tu_vi_tri_module_khong_go_cung(self):
        """Gói phát hành KHÔNG được mang đường dẫn của máy dựng gói.

        Bản trước gõ cứng một đường dẫn tuyệt đối. Giải nén gói ở chỗ khác
        thì `LENH_CHO_PHEP` trỏ tới một đường dẫn không tồn tại: hợp đồng
        bảo agent chạy một lệnh sai, `agy` từ chối, agent mất trắng cả lượt.
        """
        self.assertEqual(str(TOOL), _TOOL,
                         "`_TOOL` phải bằng đúng vị trí thật của wrapper")
        for c in LENH_CHO_PHEP:
            with self.subTest(lenh=c):
                self.assertIn(str(TOOL), c)

    def test_dong_tu_cua_moi_lenh_co_that_trong_wrapper(self):
        from scripts.cc_agent_tool import DONG_TU
        for c in LENH_CHO_PHEP:
            with self.subTest(lenh=c):
                self.assertIn(c.rsplit(" ", 1)[1], DONG_TU)

    def test_wrapper_khong_dung_shell_True(self):
        """`shell=True` biến mọi phần tử argv thành một chuỗi shell diễn
        giải được — tức là mở lại đúng cánh cửa vừa đóng.

        Kiểm trên CÂY CÚ PHÁP, không grep văn bản: chính docstring của
        wrapper GIẢI THÍCH rằng nó không bao giờ dùng `shell=True`, nên một
        phép grep sẽ báo động vì đúng câu nói nó an toàn. Cùng bài học đã
        gặp ở `test_control_center_core.TestRaoAnToanTinh`.
        """
        import ast
        cay = ast.parse(TOOL.read_text(encoding="utf-8"))
        for n in ast.walk(cay):
            if isinstance(n, ast.keyword) and n.arg == "shell":
                self.assertFalse(
                    isinstance(n.value, ast.Constant) and n.value.value is True,
                    "wrapper đặt shell=True trong MÃ CHẠY")


class TestWrapperChanDiVong(unittest.TestCase):
    """`cwd`/đường dẫn KHÔNG được biến một lệnh hẹp thành thực thi tuỳ ý."""

    def _chay(self, verb: str, cwd: Path):
        return subprocess.run(
            [sys.executable, str(TOOL), verb], cwd=str(cwd),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300)

    def test_cwd_NGOAI_kho_bi_tu_choi(self):
        """Đây là bài kiểm quan trọng nhất của tệp này.

        `python -m unittest discover -s scripts/tests -t .` giải đường dẫn
        theo `cwd`. Nếu `cwd` là một cây khác có `scripts/tests/` riêng, cùng
        một chuỗi lệnh ĐÃ ĐƯỢC DUYỆT sẽ nạp và chạy mã ở đó. Wrapper phải
        chặn trước khi tới đó.
        """
        ngoai = Path(tempfile.mkdtemp(prefix="cc-outside-"))
        (ngoai / "scripts" / "tests").mkdir(parents=True)
        (ngoai / "scripts" / "tests" / "test_evil.py").write_text(
            "raise SystemExit('mã lạ đã chạy')", encoding="utf-8")
        for verb in ("changes", "compile", "tests"):
            with self.subTest(verb=verb):
                p = self._chay(verb, ngoai)
                self.assertEqual(p.returncode, 2)
                self.assertIn("TỪ CHỐI", p.stdout + p.stderr)
                self.assertNotIn("mã lạ đã chạy", p.stdout + p.stderr)

    def test_cwd_TRONG_kho_duoc_chap_nhan(self):
        """Siết chặt không được biến công cụ thành vô dụng."""
        p = self._chay("changes", REPO)
        self.assertEqual(p.returncode, 0)

    def test_dong_tu_LA_bi_tu_choi(self):
        p = subprocess.run(
            [sys.executable, str(TOOL), "rm-rf"], cwd=str(REPO),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("invalid choice", p.stdout + p.stderr)

    def test_wrapper_KHONG_nhan_tham_so_tuy_y(self):
        """Không có đường nào truyền một chuỗi tuỳ ý xuống `subprocess`."""
        p = subprocess.run(
            [sys.executable, str(TOOL), "changes", "--", "extra"],
            cwd=str(REPO), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120)
        self.assertNotEqual(p.returncode, 0)

    def test_argv_cua_moi_dong_tu_la_HANG_SO(self):
        """Không phần tử argv nào được lấy từ dòng lệnh hay môi trường."""
        from scripts.cc_agent_tool import DONG_TU
        for verb, argv in DONG_TU.items():
            with self.subTest(verb=verb):
                self.assertTrue(all(isinstance(x, str) for x in argv))
                self.assertNotIn("*", " ".join(argv))


class TestDonTrangThaiThuNghiem(unittest.TestCase):
    """Gỡ dự án demo/thử nghiệm bằng một đường HẸP, không phải búa tạ."""

    def setUp(self):
        import tempfile as _tf
        from scripts.control_center.engine import ControlCenter
        from scripts.control_center.model import Project
        self.root = Path(_tf.mkdtemp(prefix="cc-clean-"))
        self.cc = ControlCenter(root=self.root, fabric=None, probe=False)
        for pid, ten in (("fanfic", "Fanfic"), ("router", "Router"),
                         ("proof", "Proof")):
            self.cc.them_project(Project(project_id=pid, name=ten,
                                         repo_path=str(self.root)))

    def tearDown(self):
        try:
            self.cc.shutdown()
        except Exception:                                 # noqa: BLE001
            pass

    def test_go_du_an_thu_nghiem_xoa_HET_hang_cua_no(self):
        from scripts.control_center.model import Task, TaskState
        self.cc.store.luu_task(Task(task_id="proof.t1", project_id="proof",
                                    title="x", objective="y",
                                    state=TaskState.BLOCKED))
        self.cc.store.them_chat("proof", "user", "hello")
        self.assertTrue(self.cc.store.tasks("proof"))

        self.cc.xoa_project("proof", xac_nhan=True)
        self.assertNotIn("proof",
                         [x.project_id for x in self.cc.store.projects()])
        self.assertEqual(self.cc.store.tasks("proof"), [])
        self.assertEqual(self.cc.store.chat("proof"), [])
        self.assertIsNone(self.cc.store.task("proof.t1"))

    def test_KHONG_go_duoc_du_an_MAC_DINH(self):
        """`fanfic`/`router` là dự án THẬT, không phải đồ thử."""
        for pid in ("fanfic", "router"):
            with self.subTest(pid=pid):
                with self.assertRaises(ValueError):
                    self.cc.xoa_project(pid, xac_nhan=True)
                self.assertIn(pid, [x.project_id
                                    for x in self.cc.store.projects()])

    def test_phai_XAC_NHAN_tuong_minh(self):
        with self.assertRaises(ValueError):
            self.cc.xoa_project("proof")
        self.assertIn("proof",
                      [x.project_id for x in self.cc.store.projects()])

    def test_go_du_an_KHONG_dung_toi_du_an_khac(self):
        from scripts.control_center.model import Task
        self.cc.store.luu_task(Task(task_id="fanfic.keep",
                                    project_id="fanfic", title="giữ",
                                    objective="y"))
        self.cc.xoa_project("proof", xac_nhan=True)
        self.assertIsNotNone(self.cc.store.task("fanfic.keep"))


class TestGoiKhongRoTrangThaiThuNghiem(unittest.TestCase):
    """Trạng thái demo/thử KHÔNG được lọt vào gói phát hành."""

    def test_danh_sach_dong_goi_KHONG_gom_so_hay_worktree(self):
        from scripts.package_control_center import GOM, LOAI
        for x in (".router", ".git", ".env", "__pycache__"):
            self.assertIn(x, LOAI, f"{x} phải nằm trong danh sách loại trừ")
        for muc in GOM:
            with self.subTest(muc=muc):
                self.assertFalse(muc.startswith(".router"))

    def test_goi_that_KHONG_chua_control_db_hay_worktree(self):
        """Kiểm trên GÓI THẬT nếu nó đã được dựng.

        Một danh sách loại trừ đúng mà gói vẫn lẫn tệp lạ thì vô nghĩa —
        kiểm hiện vật, không kiểm ý định.
        """
        import zipfile
        goi = REPO / "dist" / "router-control-center-v0.1.0.zip"
        if not goi.is_file():
            self.skipTest("chưa dựng gói")
        with zipfile.ZipFile(goi) as z:
            ten = z.namelist()
        for n in ten:
            with self.subTest(tep=n):
                self.assertNotIn(".router/", n)
                self.assertFalse(n.endswith(".db"))
                self.assertNotIn("__pycache__", n)
                self.assertNotIn(".git/", n)

    def test_du_an_mac_dinh_chi_gom_fanfic_va_router(self):
        """Gói mới giải nén phải khởi động SẠCH — không dự án thử nào."""
        from scripts.control_center.bootstrap import du_an_mac_dinh
        self.assertEqual(
            sorted(p.project_id for p in du_an_mac_dinh()),
            ["fanfic", "router"])


if __name__ == "__main__":
    unittest.main()
