"""Điều phối THẬT từ bản ĐÃ ĐÓNG GÓI — bài kiểm chống tái phạm.

SỰ CỐ ĐƯỢC GHÌM Ở ĐÂY (2026-09-09, nghiệm thu tay trên EXE thật).

Người dùng gõ một việc tầm thường ("ê") vào `Router Control Center.exe`.
Việc **HỎNG sau 3 lượt**, mỗi lượt trên một runtime khác (AG01 → AG02 →
AG03), mỗi lượt chỉ ~2 giây. Sổ ghi lại:

    failure_reason : "no_session"
    summary        : "chưa start_session"

Cả hai đều là TRIỆU CHỨNG. Chuỗi thật, đọc từ sổ + mã, không đoán:

    switch(acc) chạy  [sys.executable, "agy_profile.py", "switch", "acc1"]
      -> trong bản đóng gói, `sys.executable` LÀ "Router Control Center.exe"
      -> nên nó TỰ GỌI LẠI CHÍNH MÌNH với một tệp .py làm tham số
      -> argparse của ứng dụng desktop: "unrecognized arguments", thoát 2
      -> switch() -> False   (lý do "unrecognized arguments" bị VỨT ĐI)
      -> start_session() -> False   (giá trị trả về bị BỎ QUA)
      -> send_task() thấy `_worker is None` -> "no_session"
      -> thử lại 3 lượt, mỗi lượt hỏng y hệt vì lỗi không phụ thuộc runtime

Đo được, không suy đoán:

    $ "Router Control Center.exe" "…/agy_profile.py" switch acc1
    Router Control Center: error: unrecognized arguments: …
    (mã thoát 2)

BỐN khuyết tật riêng biệt, và mỗi cái đều phải có bài kiểm riêng:

    1. `sys.executable` bị dùng như "một Python" — chỉ đúng khi CHƯA đóng gói
    2. `switch()` bắt được lý do thật rồi VỨT nó đi
    3. `executor` BỎ QUA giá trị trả về của `start_session`
    4. một lỗi CẤU HÌNH (không phụ thuộc runtime) vẫn được thử lại 3 lần

Sửa một mình (1) thì hôm nay xanh, nhưng lần sau vẫn mất một buổi để tìm.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.router_v4 import thong_dich                     # noqa: E402
from scripts.router_v4.thong_dich import argv_python         # noqa: E402


class _Dong:
    """Giả vờ đang chạy trong bản đã đóng gói."""

    def __init__(self, exe: str):
        self.exe = exe
        self._cu = None

    def __enter__(self):
        self._cu = (getattr(sys, "frozen", None), sys.executable)
        sys.frozen = True                                # type: ignore[attr-defined]
        sys.executable = self.exe
        thong_dich.quen()
        return self

    def __exit__(self, *a):
        fr, ex = self._cu
        if fr is None:
            try:
                del sys.frozen                           # type: ignore[attr-defined]
            except AttributeError:
                pass
        else:
            sys.frozen = fr                              # type: ignore[attr-defined]
        sys.executable = ex
        thong_dich.quen()
        return False


class TestThongDich(unittest.TestCase):
    """Khuyết tật (1): `sys.executable` chỉ là Python khi CHƯA đóng gói."""

    def tearDown(self):
        thong_dich.quen()

    def test_chua_dong_goi_thi_dung_chinh_sys_executable(self):
        thong_dich.quen()
        argv, vi_sao = argv_python()
        self.assertEqual(argv, [sys.executable])
        self.assertIn("chưa đóng gói", vi_sao)

    def test_da_dong_goi_thi_KHONG_BAO_GIO_tra_ve_chinh_EXE(self):
        """Đây là bài kiểm của chính sự cố."""
        gia = str(GOC / "dist" / "Router Control Center"
                  / "Router Control Center.exe")
        with _Dong(gia):
            argv, vi_sao = argv_python()
            self.assertNotEqual(argv[:1], [gia],
                                "trả về chính EXE = tái phạm đúng sự cố")
            if argv:
                self.assertNotIn("Router Control Center", argv[0])

    def test_da_dong_goi_thi_tim_duoc_mot_python_CHAY_DUOC(self):
        with _Dong(r"C:\khong\ton\tai\Router Control Center.exe"):
            argv, vi_sao = argv_python()
        if not argv:                                     # pragma: no cover
            self.skipTest(f"máy này không có Python nào ngoài venv: {vi_sao}")
        p = subprocess.run(argv + ["--version"], capture_output=True,
                           timeout=30)
        ra = ((p.stdout or b"") + (p.stderr or b"")).decode("utf-8", "replace")
        self.assertEqual(p.returncode, 0, ra)
        self.assertTrue(ra.strip().startswith("Python 3"), ra)

    def test_khong_tim_duoc_thi_noi_LY_DO_chu_khong_tra_rong_cam(self):
        that = thong_dich._ung_vien
        try:
            thong_dich._ung_vien = lambda: []
            with _Dong(r"C:\gia\app.exe"):
                argv, vi_sao = argv_python()
            self.assertEqual(argv, [])
            self.assertIn("ROUTER_PYTHON", vi_sao)
            self.assertGreater(len(vi_sao), 60, "lý do phải đọc được")
        finally:
            thong_dich._ung_vien = that
            thong_dich.quen()

    def test_stub_microsoft_store_bi_loai(self):
        """`which` thấy nó, chạy thì nó không phải Python. Phải bị loại."""
        d = Path(tempfile.mkdtemp(prefix="cc-stub-"))
        stub = d / "python.cmd"
        stub.write_text("@echo off\r\nexit /b 9\r\n", encoding="ascii")
        self.assertFalse(thong_dich._chay_duoc([str(stub)]))


class TestKhongDungSysExecutableTrenDuongDispatch(unittest.TestCase):
    """Khuyết tật (1), chặn bằng AST — không chỉ chặn đúng một dòng."""

    #: `sys.executable` HỢP LỆ khi ý là "chính tệp thực thi đang chạy".
    CHINH_DANG = {
        "scripts/control_center/desktop.py",     # thu muc canh EXE
    }

    def test_khong_sinh_tien_trinh_python_bang_sys_executable(self):
        from scripts.tests.test_control_center_utf8_locale import \
            bao_dong_khoi_dong
        loi = []
        for f in bao_dong_khoi_dong():
            rel = f.relative_to(GOC).as_posix()
            if rel in self.CHINH_DANG:
                continue
            src = f.read_text(encoding="utf-8")
            dong = src.splitlines()
            for n in ast.walk(ast.parse(src)):
                if not isinstance(n, ast.Call):
                    continue
                ten = (n.func.attr if isinstance(n.func, ast.Attribute)
                       else getattr(n.func, "id", ""))
                if ten not in ("run", "Popen", "check_output", "call",
                               "check_call"):
                    continue
                # Doi so dau la mot list argv; xet phan tu dau cua no.
                if not n.args or not isinstance(n.args[0], (ast.List,
                                                            ast.Tuple)):
                    continue
                pt = n.args[0].elts[0] if n.args[0].elts else None
                if (isinstance(pt, ast.Attribute) and pt.attr == "executable"
                        and isinstance(pt.value, ast.Name)
                        and pt.value.id == "sys"):
                    loi.append(f"{rel}:{n.lineno}  "
                               f"{dong[n.lineno - 1].strip()[:90]}")
        self.assertEqual(
            loi, [],
            "`sys.executable` KHÔNG phải một thông dịch Python trong bản đã "
            "đóng gói — nó là chính EXE. Dùng `thong_dich.argv_python()`:\n"
            + "\n".join(loi))


class TestSwitchGiuLaiLyDo(unittest.TestCase):
    """Khuyết tật (2): lý do thật phải sống sót tới người đọc."""

    def test_switch_dung_argv_python_chu_khong_dung_sys_executable(self):
        src = (GOC / "scripts/router_v4/antigravity_launcher.py").read_text(
            encoding="utf-8")
        cay = ast.parse(src)
        ham = next(n for n in ast.walk(cay)
                   if isinstance(n, ast.FunctionDef) and n.name == "switch")
        than = ast.dump(ham)
        self.assertIn("argv_python", than,
                      "`switch` phải giải thông dịch qua `argv_python()`")
        self.assertNotIn("executable", than,
                         "`switch` không được chạm `sys.executable`")

    def test_khong_co_thong_dich_thi_switch_bao_dung_ly_do(self):
        from scripts.router_v4 import antigravity_launcher as al
        that = al.argv_python
        try:
            al.argv_python = lambda: ([], "KHÔNG tìm thấy thông dịch Python")
            if not al.LAUNCHER.is_file():                # pragma: no cover
                self.skipTest("máy này không có launcher")
            ok, chi_tiet = al.switch("acc1")
            self.assertFalse(ok)
            self.assertIn("thông dịch", chi_tiet)
        finally:
            al.argv_python = that


class _AdapterHong:
    """Adapter mở phiên KHÔNG được, và nói rõ vì sao."""

    provider = "antigravity"

    def __init__(self, ly_do: str = "switch acc1 hỏng: unrecognized arguments"):
        self.start_error = ly_do
        self.da_goi_send = False

    def set_write_mode(self, cho_ghi):
        pass

    def start_session(self, *, workspace=None):
        return False

    def send_task(self, packet):                         # pragma: no cover
        self.da_goi_send = True
        raise AssertionError("KHÔNG được gửi việc khi phiên chưa mở")


class TestExecutorKiemGiaTriTraVe(unittest.TestCase):
    """Khuyết tật (3): `start_session()` trả False thì phải DỪNG ở đó."""

    def _chay(self, adapter):
        from scripts.tests.test_control_center_slice import fabric_gia
        from scripts.router_v4.contract import TaskContract
        from scripts.router_v4.scheduler import Placement
        from scripts.router_v4.executor import Executor

        goc = Path(tempfile.mkdtemp(prefix="cc-exec-"))
        f = fabric_gia()
        ex = Executor(f, root=goc)
        p = Placement(runtime_id="RT01", model_id="m-re")
        ex._cache[p.key] = adapter
        # `worktree_required` mac dinh da la False — viec CHI DOC, khong
        # dung toi cay lam viec nao.
        c = TaskContract(task_id="t1", objective="đọc một tệp")
        self.assertFalse(c.execution.worktree_required)
        return ex.run(c, p)

    def test_phien_hong_thi_KHONG_gui_viec_va_bao_dung_ly_do(self):
        a = _AdapterHong()
        kq = self._chay(a)
        pb = kq.envelope
        self.assertEqual(pb.status, "failed")
        self.assertEqual(pb.failure_reason, "session_start_failed",
                         "‘no_session’ là triệu chứng, không phải lý do")
        self.assertIn("unrecognized arguments", pb.summary,
                      "lý do THẬT phải tới được người đọc")
        self.assertFalse(a.da_goi_send)

    def test_adapter_cam_nhu_hen_thi_van_noi_duoc_mot_cau(self):
        a = _AdapterHong(ly_do="")
        pb = self._chay(a).envelope
        self.assertEqual(pb.failure_reason, "session_start_failed")
        self.assertTrue(pb.summary.strip())


class TestWarmWorkerNoiViSaoHong(unittest.TestCase):
    """Khuyết tật (2), vế `agy`: bốn nhánh hỏng, bốn lý do khác nhau."""

    def _worker(self, **kw):
        from scripts.router_v3.warm_pool import WarmAgyWorker
        return WarmAgyWorker("AG01", model="m", **kw)

    @staticmethod
    def _gia_binary(ten: str, *, windows: str, posix: str) -> Path:
        """Một `agy` GIẢ chạy được trên nền đang chạy bài kiểm.

        Windows cần `.cmd`; POSIX cần shebang + bit thực thi. Viết một
        `.cmd` rồi chạy nó trên Linux chỉ ra `PermissionError`, và bài
        kiểm sẽ 'đạt' vì nhầm lý do — CI Linux đã bắt đúng chuyện đó.
        """
        d = Path(tempfile.mkdtemp(prefix="cc-agy-"))
        if sys.platform == "win32":
            p = d / f"{ten}.cmd"
            p.write_text(windows, encoding="ascii")
        else:
            p = d / ten
            p.write_text("#!/bin/sh\n" + posix, encoding="ascii")
            p.chmod(0o755)
        return p

    def test_khong_tim_thay_agy_noi_ro_la_khong_tim_thay(self):
        from scripts.router_v3 import warm_pool as wp
        that = wp.find_agy
        try:
            wp.find_agy = lambda: None
            w = self._worker()
            self.assertFalse(w.start())
            self.assertIn("agy", w.start_error)
            self.assertIn("PATH", w.start_error)
        finally:
            wp.find_agy = that

    def test_binary_khong_ton_tai_noi_ro_loi_sinh_tien_trinh(self):
        w = self._worker(binary=r"C:\khong\ton\tai\agy.exe")
        self.assertFalse(w.start())
        self.assertIn("FileNotFoundError", w.start_error)

    def test_tien_trinh_chet_som_thi_KEM_MA_THOAT_va_stderr(self):
        gia = self._gia_binary(
            "gia",
            windows="@echo off\r\necho loi cau hinh gia 1>&2\r\nexit /b 7\r\n",
            posix="echo loi cau hinh gia 1>&2\nexit 7\n")
        w = self._worker(binary=str(gia), turn_timeout=20.0)
        self.assertFalse(w.start())
        self.assertIn("7", w.start_error)
        self.assertIn("loi cau hinh gia", w.start_error)

    def test_treo_o_man_hinh_tuong_tac_duoc_goi_dung_ten(self):
        """Tiến trình SỐNG mà không phát `init` — màn hình tương tác."""
        # Song, khong in `init`, khong thoat — dung hinh dang cua mot menu
        # chon model dang cho nguoi bam.
        gia = self._gia_binary(
            "treo",
            windows="@echo off\r\nping -n 30 127.0.0.1 >nul\r\n",
            posix="sleep 30\n")
        w = self._worker(binary=str(gia), turn_timeout=3.0)
        self.assertFalse(w.start())
        self.assertIn("TƯƠNG TÁC", w.start_error)
        w.close()


class TestKhongThuLaiLoiKhongPhuThuocCho(unittest.TestCase):
    """Khuyết tật (4): cùng một lỗi cấu hình, ba runtime, ba lượt quota.

    Sự cố thật đi AG01 → AG02 → AG03 trong 6 giây, mỗi lượt cùng một câu.
    """

    def _pb(self, ly_do: str, tom: str, worker: str):
        from scripts.router_v4.envelope import ResultEnvelope
        return ResultEnvelope(task_id="t1", status="failed",
                              failure_reason=ly_do, summary=tom,
                              worker=worker)

    def test_chu_ky_hong_bo_duoi_cau_hay_doi(self):
        from scripts.control_center.engine import ControlCenter
        a = ControlCenter._chu_ky_hong(
            self._pb("session_start_failed",
                     "switch acc1 hỏng: unrecognized arguments X", "AG01"))
        b = ControlCenter._chu_ky_hong(
            self._pb("session_start_failed",
                     "switch acc1 hỏng: unrecognized arguments X", "AG02"))
        self.assertEqual(a, b, "cùng bản chất phải cùng chữ ký")
        c = ControlCenter._chu_ky_hong(
            self._pb("turn_failed", "hết quota", "AG01"))
        self.assertNotEqual(a, c)

    def test_chu_ky_rong_khi_khong_co_gi_de_so(self):
        from scripts.control_center.engine import ControlCenter
        self.assertEqual(
            ControlCenter._chu_ky_hong(self._pb("", "", "AG01")), "")

    def test_hong_y_het_o_cho_khac_thi_TU_CHOI_thu_lai(self):
        import tempfile as _tf
        from scripts.control_center.engine import ControlCenter
        from scripts.control_center.model import Project

        goc = Path(_tf.mkdtemp(prefix="cc-retry-"))
        cc = ControlCenter(root=goc, max_parallel=1)
        self.addCleanup(cc.shutdown)
        cc.store.luu_project(Project(project_id="p", name="P",
                                     repo_path=str(goc)))
        ctx = cc.ctx("p")

        from scripts.control_center.model import Task, TaskState
        cc.store.luu_task(Task(task_id="p.t1", project_id="p", title="ê",
                               objective="ê", state=TaskState.FAILED,
                               attempts=2))

        sig = "session_start_failed|switch acc1 hỏng: unrecognized arguments"
        # Hai lan hong Y HET o HAI cho khac nhau, dung thu tu that.
        for cho in ("AG01/m", "AG02/m"):
            cc.store.ghi_su_kien(
                "TASK_FINISHED", project_id="p", task_id="p.t1",
                level="ERROR", detail="hỏng",
                meta={"ok": False, "fail_sig": sig, "placement": cho})

        pb = self._pb("session_start_failed",
                      "switch acc1 hỏng: unrecognized arguments", "AG02")
        cc._thu_lai_neu_dang(ctx, "p.t1", pb, "s-1", placement_key="AG02/m")

        kinds = [e["kind"] for e in cc.store.su_kien(task_id="p.t1", limit=20)]
        self.assertIn("RETRY_REFUSED", kinds,
                      f"lẽ ra phải từ chối thử lại; đã ghi: {kinds}")
        self.assertNotIn("RETRY_QUEUED", kinds)
        self.assertEqual(cc.store.task("p.t1").state, TaskState.FAILED.value)

    def test_loi_TAM_THOI_lap_lai_VAN_duoc_thu_o_cho_khac(self):
        """Tấn công: đừng biến một rào chống bão thành một lỗi bỏ sót.

        Hai tài khoản cùng hết quota KHÔNG có nghĩa tài khoản thứ ba cũng
        hết. Chặn thử lại ở đây chính là chế độ hỏng "báo FAILED trong khi
        một nhà cung cấp khoẻ khác đang làm được".
        """
        import tempfile as _tf
        from scripts.control_center.engine import ControlCenter
        from scripts.control_center.model import Project, Task, TaskState

        goc = Path(_tf.mkdtemp(prefix="cc-retry3-"))
        cc = ControlCenter(root=goc, max_parallel=1)
        self.addCleanup(cc.shutdown)
        cc.store.luu_project(Project(project_id="p", name="P",
                                     repo_path=str(goc)))
        ctx = cc.ctx("p")
        cc.store.luu_task(Task(task_id="p.t3", project_id="p", title="ê",
                               objective="ê", state=TaskState.FAILED,
                               attempts=2))
        sig = "turn_failed|hết quota"
        for cho in ("AG01/m", "AG02/m"):
            cc.store.ghi_su_kien("TASK_FINISHED", project_id="p",
                                 task_id="p.t3", level="ERROR", detail="hỏng",
                                 meta={"ok": False, "fail_sig": sig,
                                       "placement": cho})
        pb = self._pb("turn_failed", "hết quota", "AG02")
        cc._thu_lai_neu_dang(ctx, "p.t3", pb, "s-3", placement_key="AG02/m")
        kinds = [e["kind"] for e in cc.store.su_kien(task_id="p.t3", limit=20)]
        self.assertIn("RETRY_QUEUED", kinds,
                      f"`turn_failed` là lỗi TẠM THỜI — vẫn phải được thử ở "
                      f"chỗ khác; đã ghi: {kinds}")

    def test_lan_hong_DAU_TIEN_van_duoc_thu_lai(self):
        """Chứng cứ chống rỗng: guard không được chặn mọi lượt thử lại."""
        import tempfile as _tf
        from scripts.control_center.engine import ControlCenter
        from scripts.control_center.model import Project, Task, TaskState

        goc = Path(_tf.mkdtemp(prefix="cc-retry2-"))
        cc = ControlCenter(root=goc, max_parallel=1)
        self.addCleanup(cc.shutdown)
        cc.store.luu_project(Project(project_id="p", name="P",
                                     repo_path=str(goc)))
        ctx = cc.ctx("p")
        cc.store.luu_task(Task(task_id="p.t2", project_id="p", title="ê",
                               objective="ê", state=TaskState.FAILED,
                               attempts=1))
        sig = "turn_failed|hết quota"
        cc.store.ghi_su_kien("TASK_FINISHED", project_id="p", task_id="p.t2",
                             level="ERROR", detail="hỏng",
                             meta={"ok": False, "fail_sig": sig,
                                   "placement": "AG01/m"})
        pb = self._pb("turn_failed", "hết quota", "AG01")
        cc._thu_lai_neu_dang(ctx, "p.t2", pb, "s-2", placement_key="AG01/m")
        kinds = [e["kind"] for e in cc.store.su_kien(task_id="p.t2", limit=20)]
        self.assertIn("RETRY_QUEUED", kinds,
                      f"lượt hỏng đầu tiên PHẢI được thử lại; đã ghi: {kinds}")


class TestMotThucTheTheoGoc(unittest.TestCase):
    """"Một thực thể" tính theo NƠI LÀM VIỆC, không theo cả máy."""

    def test_cung_goc_thi_cung_ten_mutex(self):
        from scripts.control_center.desktop_shell import ten_mutex_cua
        d = Path(tempfile.mkdtemp(prefix="cc-mtx-"))
        self.assertEqual(ten_mutex_cua(d), ten_mutex_cua(d))

    def test_hoa_thuong_va_dau_gach_khong_lam_ra_hai_ten(self):
        from scripts.control_center.desktop_shell import ten_mutex_cua
        d = Path(tempfile.mkdtemp(prefix="cc-mtx2-"))
        self.assertEqual(ten_mutex_cua(str(d).upper()),
                         ten_mutex_cua(str(d).lower()))

    def test_hai_goc_khac_nhau_thi_KHAC_ten(self):
        from scripts.control_center.desktop_shell import ten_mutex_cua
        a = Path(tempfile.mkdtemp(prefix="cc-mtx3-"))
        b = Path(tempfile.mkdtemp(prefix="cc-mtx4-"))
        self.assertNotEqual(ten_mutex_cua(a), ten_mutex_cua(b),
                            "hai nơi làm việc khác nhau không tranh nhau sổ "
                            "nào cả — chặn chúng là chặn nhầm")

    def test_van_giu_tien_to_toan_cuc(self):
        from scripts.control_center.desktop_shell import (TEN_MUTEX,
                                                          ten_mutex_cua)
        d = Path(tempfile.mkdtemp(prefix="cc-mtx5-"))
        self.assertTrue(ten_mutex_cua(d).startswith(TEN_MUTEX + "."))

    def test_desktop_dung_ten_theo_goc_chu_khong_dung_mac_dinh(self):
        src = (GOC / "scripts/control_center/desktop.py").read_text(
            encoding="utf-8")
        self.assertIn("MotThucThe(ten_mutex_cua(goc))", src,
                      "desktop.py phải khoá theo thư mục gốc")


if __name__ == "__main__":
    unittest.main(verbosity=2)
