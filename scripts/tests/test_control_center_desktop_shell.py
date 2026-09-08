"""Logic khởi động của vỏ desktop — CI cưỡng chế.

`desktop_shell.py` tách khỏi `desktop.py` đúng để tệp này tồn tại được:
quyết định "nối lại / tự chạy / nhường" là hàm THUẦN trên trạng thái đĩa,
nên dựng được mọi tình huống mà không cần WebView2 và không cần khởi động
một server thật.

Tình huống được phủ, và mỗi cái là một chế độ hỏng đã thấy ở loại app này:

    chưa có gì              -> tự chạy
    tệp khoá MỒ CÔI         -> tự chạy (không đứng chờ vĩnh viễn)
    backend đang SỐNG       -> nối lại, và KHÔNG sở hữu
    pid còn sống nhưng câm  -> tự chạy ở cổng khác, KHÔNG giết pid đó
    có thực thể desktop khác-> nhường
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.desktop_shell import (  # noqa: E402
    DIA_CHI, MotThucThe, ThongTinPhien, backend_khoe, cong_rong,
    doc_tep_khoa, duong_giao_dien, duong_tep_khoa, ghi_tep_khoa, quyet_dinh,
    tien_trinh_con_song, xoa_tep_khoa)


class _Nen(unittest.TestCase):
    def setUp(self):
        self.goc = Path(tempfile.mkdtemp(prefix="cc-desk-"))

    def tearDown(self):
        shutil.rmtree(self.goc, ignore_errors=True)


class TestTepKhoa(_Nen):
    def test_ghi_roi_doc_lai_duoc(self):
        tt = ThongTinPhien(pid=1234, cong=54321, token="abc",
                           bat_dau_luc=99.0)
        ghi_tep_khoa(self.goc, tt)
        lai = doc_tep_khoa(self.goc)
        self.assertEqual((lai.pid, lai.cong, lai.token), (1234, 54321, "abc"))

    def test_ghi_la_doi_ten_NGUYEN_TU_khong_de_lai_tep_tam(self):
        ghi_tep_khoa(self.goc, ThongTinPhien(1, 2, "t"))
        con = list(duong_tep_khoa(self.goc).parent.glob("*.tmp"))
        self.assertEqual(con, [], f"còn tệp tạm: {con}")

    def test_tep_khoa_HONG_thi_coi_nhu_khong_co(self):
        """FAIL OPEN ở đây là đúng.

        Tệp khoá không phải một rào an toàn — nó chỉ nói "nối vào đâu".
        Fail closed sẽ chặn người dùng mở app vì một tệp rác, và cách sửa
        duy nhất là tự đi tìm tệp mà xoá.
        """
        p = duong_tep_khoa(self.goc)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{khong phai json", encoding="utf-8")
        self.assertIsNone(doc_tep_khoa(self.goc))

    def test_chua_co_tep_thi_tra_None(self):
        self.assertIsNone(doc_tep_khoa(self.goc))

    def test_xoa_duoc_va_xoa_hai_lan_khong_no(self):
        ghi_tep_khoa(self.goc, ThongTinPhien(1, 2, "t"))
        xoa_tep_khoa(self.goc)
        xoa_tep_khoa(self.goc)
        self.assertIsNone(doc_tep_khoa(self.goc))

    def test_tep_khoa_nam_CANH_so_khong_o_thu_muc_tam(self):
        """Cùng chỗ với `control.db`: sao lưu một chỗ là đủ cả hai."""
        p = duong_tep_khoa(self.goc)
        self.assertEqual(p.parent.name, "control_center")
        self.assertEqual(p.parent.parent.name, ".router")


class TestTienTrinhConSong(unittest.TestCase):
    def test_pid_cua_CHINH_MINH_la_song(self):
        self.assertTrue(tien_trinh_con_song(os.getpid()))

    def test_pid_khong_hop_le_la_chet(self):
        for pid in (0, -1, -999):
            with self.subTest(pid=pid):
                self.assertFalse(tien_trinh_con_song(pid))

    def test_KHONG_dung_os_kill_de_kiem_tren_Windows(self):
        """Trên Windows `os.kill(pid, 0)` GIẾT tiến trình.

        Nó gọi `TerminateProcess`, không gửi signal — nên dùng nó để "kiểm
        tra xem còn sống không" là giết mất đúng cái backend mình đang định
        nối vào. Bài kiểm đọc cây cú pháp để chắc nhánh Windows không gọi
        nó.
        """
        import ast
        ma = (GOC / "scripts" / "control_center"
              / "desktop_shell.py").read_text(encoding="utf-8")
        cay = ast.parse(ma)
        for n in ast.walk(cay):
            if (isinstance(n, ast.FunctionDef)
                    and n.name == "tien_trinh_con_song"):
                than = ast.unparse(n)
                # `os.kill` chi duoc phep xuat hien trong nhanh
                # non-Windows, va nhanh do bat dau bang `if sys.platform
                # != 'win32'`.
                self.assertIn("win32", than,
                              "không phân nhánh theo nền tảng")
                self.assertIn("WaitForSingleObject", than,
                              "nhánh Windows phải dùng WaitForSingleObject")
                return
        self.fail("không tìm thấy `tien_trinh_con_song`")


class TestBackendKhoe(_Nen):
    def test_cong_khong_ai_nghe_thi_KHONG_khoe(self):
        self.assertFalse(backend_khoe(cong_rong(), "token-nao-do",
                                      timeout=0.5))

    def test_cong_0_hoac_token_rong_thi_KHONG_khoe(self):
        self.assertFalse(backend_khoe(0, "t"))
        self.assertFalse(backend_khoe(12345, ""))

    def test_backend_THAT_thi_khoe_va_token_SAI_thi_khong(self):
        """Đây cũng là phép kiểm DANH TÍNH, không chỉ kiểm sống.

        Một tiến trình lạ tình cờ chiếm cổng đó sẽ không trả 200 cho token
        của ta — nên `backend_khoe` phân biệt được "server của mình" với
        "có ai đó đang nghe ở cổng này".
        """
        try:
            import uvicorn
            from scripts.control_center.engine import ControlCenter
            from scripts.control_center.webapi import PhienWeb, dung_app
        except ModuleNotFoundError:
            self.skipTest("chưa có fastapi/uvicorn")
        cc = ControlCenter(root=self.goc, probe=False)
        cong = cong_rong()
        phien = PhienWeb(cc, token="TOKEN-THAT", cong=cong)
        sv = uvicorn.Server(uvicorn.Config(
            dung_app(phien), host=DIA_CHI, port=cong, log_level="error",
            access_log=False))
        th = threading.Thread(target=sv.run, daemon=True)
        th.start()
        try:
            het = time.time() + 20
            while time.time() < het and not sv.started:
                time.sleep(0.05)
            self.assertTrue(sv.started, "server không khởi động")
            self.assertTrue(backend_khoe(cong, "TOKEN-THAT", timeout=3))
            self.assertFalse(backend_khoe(cong, "TOKEN-SAI", timeout=3),
                             "token sai vẫn được coi là khoẻ")
        finally:
            sv.should_exit = True
            th.join(timeout=10)
            cc.shutdown()

    def test_KHONG_them_endpoint_mien_token_de_lam_health(self):
        """Bất biến "mọi `/api/` đòi token" không được nới cho tiện.

        Cách dễ nhất để làm health check là thêm một `/health` miễn token.
        Nhưng ta ĐÃ CÓ token (đọc từ tệp khoá), nên không cần lỗ nào — và
        mở một lỗ là làm yếu đúng cái ranh giới mà
        `test_control_center_webapi.py` đang khoá lại.
        """
        ma = (GOC / "scripts" / "control_center" / "webapi.py").read_text(
            encoding="utf-8")
        for xau in ('"/api/health"', "'/api/health'", '"/health"'):
            with self.subTest(duong=xau):
                self.assertNotIn(xau, ma)
        # Va middleware chi mien token cho `/` va `/static/`.
        self.assertIn('duong == "/" or duong.startswith("/static/")', ma)


class TestQuyetDinhKhoiDong(_Nen):
    def test_chua_co_gi_thi_TU_CHAY_va_SO_HUU(self):
        kh = quyet_dinh(self.goc, co_thuc_the_khac=False)
        self.assertEqual(kh.hanh_dong, "tu_chay")
        self.assertTrue(kh.so_huu)
        self.assertGreater(kh.cong, 0)
        self.assertTrue(kh.token)

    def test_tep_khoa_MO_COI_thi_TU_CHAY_khong_dung_cho(self):
        """Mất điện giữa chừng để lại một tệp khoá trỏ pid đã chết.

        Nếu vỏ desktop đứng chờ hoặc từ chối mở, người dùng phải tự đi tìm
        tệp mà xoá — và họ sẽ không biết phải tìm gì.
        """
        ghi_tep_khoa(self.goc, ThongTinPhien(pid=999_999_999, cong=1,
                                             token="cu"))
        kh = quyet_dinh(self.goc, co_thuc_the_khac=False)
        self.assertEqual(kh.hanh_dong, "tu_chay")
        self.assertTrue(kh.so_huu)
        self.assertNotEqual(kh.token, "cu", "phải sinh token MỚI")

    def test_co_thuc_the_khac_ma_chua_co_backend_thi_NHUONG(self):
        kh = quyet_dinh(self.goc, co_thuc_the_khac=True)
        self.assertEqual(kh.hanh_dong, "nhuong")

    def test_pid_CON_SONG_nhung_backend_cam_thi_tu_chay_o_cong_KHAC(self):
        """Không được giết tiến trình đó.

        Pid có thể đã bị hệ điều hành tái sử dụng cho một tiến trình hoàn
        toàn khác; giết nó là giết một thứ không liên quan.
        """
        ghi_tep_khoa(self.goc, ThongTinPhien(pid=os.getpid(), cong=1,
                                             token="cam"))
        kh = quyet_dinh(self.goc, co_thuc_the_khac=False)
        self.assertEqual(kh.hanh_dong, "tu_chay")
        self.assertNotEqual(kh.cong, 1)
        self.assertIn("KHÔNG tắt", kh.ly_do)

    def test_backend_DANG_SONG_thi_NOI_LAI_va_KHONG_so_huu(self):
        """Đây là bất biến quan trọng nhất của tệp này.

        Người dùng chạy `router-cc-web.cmd` rồi bấm đôi EXE: có MỘT backend
        và HAI người muốn nó. Đóng cửa sổ desktop KHÔNG được tắt backend mà
        cửa sổ đó không tự khởi động — nếu không, người đang dùng đường gỡ
        lỗi sẽ mất server giữa lúc làm việc.
        """
        try:
            import uvicorn
            from scripts.control_center.engine import ControlCenter
            from scripts.control_center.webapi import PhienWeb, dung_app
        except ModuleNotFoundError:
            self.skipTest("chưa có fastapi/uvicorn")
        cc = ControlCenter(root=self.goc, probe=False)
        cong = cong_rong()
        phien = PhienWeb(cc, token="DANG-CHAY", cong=cong)
        sv = uvicorn.Server(uvicorn.Config(
            dung_app(phien), host=DIA_CHI, port=cong, log_level="error",
            access_log=False))
        th = threading.Thread(target=sv.run, daemon=True)
        th.start()
        try:
            het = time.time() + 20
            while time.time() < het and not sv.started:
                time.sleep(0.05)
            ghi_tep_khoa(self.goc, ThongTinPhien(
                pid=os.getpid(), cong=cong, token="DANG-CHAY"))
            kh = quyet_dinh(self.goc, co_thuc_the_khac=False)
            self.assertEqual(kh.hanh_dong, "noi_lai")
            self.assertFalse(kh.so_huu,
                             "nối lại mà lại nhận sở hữu — đóng cửa sổ sẽ "
                             "tắt backend của người khác")
            self.assertEqual(kh.cong, cong)
            self.assertEqual(kh.token, "DANG-CHAY")
        finally:
            sv.should_exit = True
            th.join(timeout=10)
            cc.shutdown()

    def test_noi_lai_duoc_UU_TIEN_hon_nhuong(self):
        """Có backend sống thì nối lại, kể cả khi mutex nói có thực thể khác.

        Thứ tự này quan trọng: nếu `nhuong` xét trước, bấm đôi lần hai sẽ
        thoát im lặng thay vì mở một cửa sổ nữa vào cùng backend.
        """
        import ast
        ma = (GOC / "scripts" / "control_center"
              / "desktop_shell.py").read_text(encoding="utf-8")
        cay = ast.parse(ma)
        for n in ast.walk(cay):
            if isinstance(n, ast.FunctionDef) and n.name == "quyet_dinh":
                than = ast.unparse(n)
                self.assertLess(than.index("noi_lai"), than.index("nhuong"),
                                "`nhuong` được xét trước `noi_lai`")
                return
        self.fail("không tìm thấy `quyet_dinh`")


class TestDuongGiaoDien(unittest.TestCase):
    def test_chi_127_va_mang_token(self):
        u = duong_giao_dien(1234, "TOK")
        self.assertTrue(u.startswith("http://127.0.0.1:1234/"))
        self.assertIn("t=TOK", u)

    def test_KHONG_bao_gio_0_0_0_0(self):
        import ast
        p = GOC / "scripts" / "control_center" / "desktop_shell.py"
        cay = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(cay):
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                if (n.body and isinstance(n.body[0], ast.Expr)
                        and isinstance(n.body[0].value, ast.Constant)
                        and isinstance(n.body[0].value.value, str)):
                    n.body = n.body[1:] or [ast.Pass()]
        self.assertNotIn("0.0.0.0",
                         ast.unparse(ast.fix_missing_locations(cay)))


class TestMotThucThe(unittest.TestCase):
    def test_thuc_the_dau_tien_KHONG_thay_cai_nao_khac(self):
        m = MotThucThe("Global\\RCC.Test.MotThucThe.A")
        try:
            self.assertFalse(m.da_co)
        finally:
            m.nha()

    @unittest.skipUnless(sys.platform == "win32", "mutex chỉ có ở Windows")
    def test_thuc_the_THU_HAI_thay_cai_dau_tien(self):
        a = MotThucThe("Global\\RCC.Test.MotThucThe.B")
        try:
            b = MotThucThe("Global\\RCC.Test.MotThucThe.B")
            try:
                self.assertTrue(b.da_co, "không phát hiện được thực thể thứ hai")
            finally:
                b.nha()
        finally:
            a.nha()

    @unittest.skipUnless(sys.platform == "win32", "mutex chỉ có ở Windows")
    def test_nha_roi_thi_thuc_the_sau_lai_la_dau_tien(self):
        """Mutex do HỆ ĐIỀU HÀNH nhả khi tiến trình chết.

        Đó là lý do dùng mutex để CHẶN chứ không dùng tệp khoá: một tệp
        khoá mồ côi sẽ chặn vĩnh viễn.
        """
        a = MotThucThe("Global\\RCC.Test.MotThucThe.C")
        a.nha()
        b = MotThucThe("Global\\RCC.Test.MotThucThe.C")
        try:
            self.assertFalse(b.da_co)
        finally:
            b.nha()


class TestKhongNhetBackendVaoVo(unittest.TestCase):
    """Vỏ desktop phải MỎNG. Bài kiểm này canh đúng điều đó."""

    def test_vo_desktop_KHONG_import_tang_dieu_phoi_sau(self):
        """`desktop_shell.py` chỉ được biết về HTTP và tệp khoá.

        Nó không được import `scheduler`/`executor`/`sessions`/`locks` —
        nếu một ngày nào đó nó cần, đó là dấu hiệu logic điều phối đang rỉ
        vào vỏ.
        """
        import ast
        ma = (GOC / "scripts" / "control_center"
              / "desktop_shell.py").read_text(encoding="utf-8")
        ten = []
        for n in ast.walk(ast.parse(ma)):
            if isinstance(n, ast.Import):
                ten += [x.name for x in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module:
                ten.append(n.module)
        xau = [x for x in ten
               if any(k in x for k in ("scheduler", "executor", "sessions",
                                       "locks", "planner", "router_v4",
                                       "router_v3"))]
        self.assertEqual(xau, [], f"vỏ desktop đã import: {xau}")

    def test_desktop_py_KHONG_tu_quyet_dinh_dieu_phoi(self):
        """`desktop.py` chỉ THỰC HIỆN kế hoạch, không tự quyết."""
        ma = (GOC / "scripts" / "control_center" / "desktop.py").read_text(
            encoding="utf-8")
        self.assertIn("quyet_dinh(", ma)
        for k in ("Scheduler(", "Executor(", "SessionManager(",
                  "LockManager("):
            with self.subTest(k=k):
                self.assertNotIn(k, ma)


if __name__ == "__main__":
    unittest.main()
