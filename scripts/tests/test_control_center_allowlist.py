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

        `tests` đang bị giữ lại (thực thi mã tuỳ ý — xem
        `test_dong_tu_THUC_THI_MA_khong_duoc_cap_cho_agent`), nên bài kiểm
        này canh đúng thứ nguy hiểm: giữ trong danh sách mà QUÊN GỠ khỏi
        `settings.json` thì quyền vẫn còn sống, chỉ có tài liệu là sai. Đó
        là loại lệch âm thầm tệp này tồn tại để chặn.
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
                # Kiem TINH TUYET DOI, khong kiem "co bat dau bang C:\\".
                # Ban truoc gan cung o dia Windows nen CI Linux bao hong
                # tren mot duong dan `/home/runner/...` VON DA tuyet doi —
                # bai kiem sai, khong phai san pham sai.
                # Doi chieu voi `_TOOL` chu khong cat chuoi: cat theo dau
                # cach se sai ngay khi duong dan co dau cach.
                self.assertIn(_TOOL, c)
                self.assertTrue(
                    Path(_TOOL).is_absolute(),
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

    def test_dong_tu_THUC_THI_MA_khong_duoc_cap_cho_agent(self):
        """`tests` nạp và CHẠY mọi module trong `scripts/tests/` của `cwd`,
        và `cwd` hợp lệ là worktree agent ĐANG CÓ QUYỀN GHI.

        Agent không cần thoát rào `cwd` — nó chỉ cần trồng một tệp vào bên
        trong rồi chạy đúng dòng lệnh đã được duyệt. Cổng `scope`/`security`
        chỉ chạy SAU lượt, lúc mã đã chạy xong. Đó chính là năng lực mà
        `command(*)` bị cấm vì nó.
        """
        for c in LENH_CHO_PHEP:
            with self.subTest(lenh=c):
                self.assertNotEqual(
                    c.rsplit(" ", 1)[1], "tests",
                    "`tests` KHÔNG được nằm trong allowlist của agent")
        self.assertIn("tests", " ".join(KHONG_CAP_CHO_AGENT))

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

    def test_cwd_gia_o_BAT_KY_dau_khong_chay_duoc_ma_cua_no(self):
        """Rào `cwd` chấp nhận **bất kỳ** đường dẫn có `.router/worktrees`
        kề nhau trong tổ tiên — kể cả một cây dựng ở chỗ khác trên đĩa.

        Phải nới như vậy vì worktree của dự án `fanfic` nằm dưới KHO CHÍNH,
        không dưới `REPO_ROOT` của tệp này; bản siết chặt hơn đã từ chối
        100% động từ trên đúng dự án MẶC ĐỊNH (xem review đối kháng #4).

        Nới rào chỉ an toàn vì MỘT lý do, và lý do đó là bất biến mà bài
        kiểm này khoá lại: **không động từ nào ĐƯỢC CẤP nạp mã theo `cwd`.**
        `changes` chạy `git status`; `compile` chỉ BIÊN DỊCH (ghi `.pyc`,
        không thực thi). Động từ duy nhất từng chạy mã của `cwd` là `tests`,
        và nó đã bị rút khỏi allowlist.

        Nếu ai đó cấp lại một động từ chạy mã, bài kiểm này hỏng — và đó
        đúng là lúc `_kiem_cwd` phải được siết lại, không phải lúc sửa bài
        kiểm cho xanh.
        """
        gia = Path(tempfile.mkdtemp(prefix="cc-fake-")) / ".router" / "worktrees" / "x"
        (gia / "scripts" / "tests").mkdir(parents=True)
        # `__init__.py` KHONG phai chi tiet trang tri. Tu Python 3.11,
        # `unittest discover` chi nap thu muc IMPORT DUOC — thieu hai tep nay
        # thi khong tim thay gi va bai kiem XANH MA KHONG KIEM GI. Da kiem
        # bang mutation: cap lai `tests` khi thieu chung -> van xanh.
        # Cay that cua agent LA mot ban checkout cua kho, nen no CO san hai
        # tep nay; cay gia phai giong cho do moi la mo hinh doi thu dung.
        for goi in (gia / "scripts", gia / "scripts" / "tests"):
            (goi / "__init__.py").write_text("", encoding="utf-8")
        # Tep nay CHAY duoc neu bi `unittest discover` nap. Neu mot dong tu
        # duoc cap nao nap no, tep chung tich duoi day se xuat hien.
        dau = gia / "DA_CHAY.txt"
        (gia / "scripts" / "tests" / "test_evil.py").write_text(
            "import pathlib\n"
            f"pathlib.Path(r'{dau}').write_text('x', encoding='utf-8')\n",
            encoding="utf-8")

        # Rao THAT SU chap nhan cwd nay — bai kiem khong vo tinh xanh vi bi
        # tu choi tu vong ngoai.
        # Kiem DUNG cai rao, khong kiem ma thoat cua lenh: `git status` o mot
        # cay khong phai kho se thoat 128 du rao da cho qua. Chung cu rao cho
        # qua la VANG mat loi tu choi (`TuChoi` luon thoat 2 kem "TU CHOI").
        p = self._chay("changes", gia)
        self.assertNotEqual(p.returncode, 2, "rào phải chấp nhận cwd này")
        self.assertNotIn("TỪ CHỐI", p.stdout + p.stderr)

        for verb in {c.rsplit(" ", 1)[1] for c in LENH_CHO_PHEP}:
            with self.subTest(verb=verb):
                # Xoa dau truoc MOI dong tu: neu de lai, dong tu dau tien
                # chay ma se lam moi dong tu sau do bao loi oan.
                if dau.exists():
                    dau.unlink()
                self._chay(verb, gia)
                self.assertFalse(
                    dau.exists(),
                    f"động từ được cấp {verb!r} đã CHẠY mã của cwd — "
                    f"phải siết lại `_kiem_cwd`, không phải sửa bài kiểm")

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

    def test_TU_CHOI_xoa_du_an_con_viec_DANG_CHAY(self):
        """Xoá giữa chừng thì agent vẫn chạy nhưng mọi hàng của nó biến mất.

        `ghi_ket_qua` thành no-op, `doi_trang_thai` ném `StoreError`, kết quả
        mất. Tệ hơn: `lm.tra()` nhả MỌI khoá của dự án — kể cả khoá
        PRODUCTION mà `reclaim()` cố ý không bao giờ đụng — trong khi một
        agent vẫn đang ghi.
        """
        from scripts.control_center.model import Task, TaskState
        self.cc.store.luu_task(Task(task_id="proof.dangchay",
                                    project_id="proof", title="x",
                                    objective="y", state=TaskState.RUNNING))
        with self.assertRaises(ValueError) as ctx:
            self.cc.xoa_project("proof", xac_nhan=True)
        self.assertIn("ĐANG CHẠY", str(ctx.exception))
        self.assertIn("proof", [x.project_id
                                for x in self.cc.store.projects()])

    def test_xoa_du_an_quet_ca_su_kien_gan_theo_TASK(self):
        """`TASK_CLAIMED` ghi KHÔNG kèm `project_id`, nên điều kiện
        `project_id=?` không quét được nó — rác của một dự án đã xoá."""
        from scripts.control_center.model import Task, TaskState
        self.cc.store.luu_task(Task(task_id="proof.t9", project_id="proof",
                                    title="x", objective="y"))
        self.cc.store.claim_task("proof.t9", "s-x")
        self.assertTrue(self.cc.store.su_kien(task_id="proof.t9"))
        self.cc.store.doi_trang_thai("proof.t9", TaskState.FAILED, force=True)
        self.cc.xoa_project("proof", xac_nhan=True)
        self.assertEqual(self.cc.store.su_kien(task_id="proof.t9"), [])

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
        # Lay TU `VERSION` cua chinh bo dong goi, khong go cung: go cung
        # thi bump phien ban se lam bai kiem im lang bo qua (tep khong ton
        # tai -> `skipTest`) thay vi kiem goi that.
        from scripts.package_control_center import VERSION
        goi = REPO / "dist" / f"router-control-center-v{VERSION}.zip"
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

    def test_goi_PHAI_gom_loi_vao_GIAO_DIEN_DO_HOA(self):
        """Từ V0.1.1, GUI là đường CHÍNH — gói thiếu nó là gói hỏng.

        Đây là loại lỗi im lặng nhất của cả bản đóng gói:
        `scripts/control_center` là một thư mục nên `gui/` tự đi theo, và
        gói vẫn "chạy được" — bằng TUI. Không ai phát hiện đường chính đã
        biến mất cho tới khi bấm đôi vào một tệp không tồn tại.
        """
        from scripts.package_control_center import GOM
        for x in ("router-cc-gui", "router-cc-gui.cmd",
                  "requirements-control-center-gui.txt"):
            with self.subTest(muc=x):
                self.assertIn(x, GOM)
                self.assertTrue((REPO / x).is_file(),
                                f"{x} có trong GOM nhưng KHÔNG có trên đĩa")

    def test_goi_PHAI_gom_ma_nguon_giao_dien(self):
        """Và `gui/` phải thật sự nằm dưới một mục của `GOM`."""
        from scripts.package_control_center import GOM
        self.assertIn("scripts/control_center", GOM)
        for ten in ("app.py", "bridge.py", "widgets.py", "views.py",
                    "views_chat.py", "__main__.py"):
            with self.subTest(tep=ten):
                self.assertTrue(
                    (REPO / "scripts" / "control_center" / "gui" / ten).is_file())


if __name__ == "__main__":
    unittest.main()
