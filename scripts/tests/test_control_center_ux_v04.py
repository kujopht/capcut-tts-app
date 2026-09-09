"""V0.4 — không nhấp cửa sổ, ô soạn tự trống, một màn hình thấy hết.

SỰ CỐ UX ĐƯỢC GHÌM Ở ĐÂY. Người dùng báo: *"mỗi lần xử lý lại bật/tắt
terminal window trên Windows, rất khó chịu"*.

CƠ CHẾ: `Router Control Center.exe` build `--noconsole` nên tiến trình
không có console. Trên Windows, một tiến trình KHÔNG có console mà sinh ra
một ứng dụng **console** (`git.exe`, `agy.exe`, `codex.exe`, `python.exe`,
`icacls.exe`) thì hệ điều hành **cấp cho nó console mới** — kèm một cửa sổ
nhấp lên và **giành focus**. Chạy từ mã nguồn thì cửa sổ đó trùng console
sẵn có nên không ai thấy; chỉ bản EXE mới nhấp nháy. Lại đúng một lớp lỗi
"chỉ lộ ra ở EXE".

Số lần nhấp tỉ lệ với số lệnh: `AnhChupDuAn` chạy ~6 lệnh `git` cho MỖI
tin nhắn, nên một câu "ê" cũng đủ thấy.

Bài kiểm quan trọng nhất ở đây là bài AST: nó quét CẢ bao đóng khởi động
và đòi mọi chỗ sinh tiến trình phải ẩn cửa sổ. Sửa từng chỗ thì lần thêm
adapter sau lại quên; một phép kiểm trên cả bao đóng thì không quên được.
"""
from __future__ import annotations

import ast
import collections
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.router_v3.tien_trinh import AN_HIEN, an_cua_so  # noqa: E402

#: Hàm sinh tiến trình con.
SINH = {"run", "Popen", "call", "check_call", "check_output"}

#: Đường CỐ Ý cho người dùng thấy cửa sổ (nút "mở terminal gỡ lỗi").
MIEN_TRU = {
    # `pool/daemon.py` tu quan cac co cua no (CREATE_NEW_PROCESS_GROUP +
    # CREATE_NO_WINDOW) va co ly do rieng duoc ghi trong docstring.
    "scripts/router_v3/pool/daemon.py",
}


def _bao_dong_khoi_dong():
    """Mọi tệp `scripts/**` mà việc mở EXE có thể nạp tới."""
    def tep(mod):
        p = GOC.joinpath(*mod.split("."))
        for c in (p.with_suffix(".py"), p / "__init__.py"):
            if c.is_file():
                return c
        return None

    def nhap(f, mod):
        ra = set()
        t = ast.parse(f.read_text(encoding="utf-8"))
        goi = mod if f.name == "__init__.py" else mod.rsplit(".", 1)[0]
        for n in ast.walk(t):
            if isinstance(n, ast.Import):
                for al in n.names:
                    if al.name.startswith("scripts"):
                        ra.add(al.name)
            elif isinstance(n, ast.ImportFrom):
                if n.level:
                    b = goi.split(".")
                    m = ".".join(b[:len(b) - n.level + 1]
                                 + ([n.module] if n.module else []))
                else:
                    m = n.module or ""
                if m.startswith("scripts"):
                    ra.add(m)
                    for al in n.names:
                        ra.add(m + "." + al.name)
        return ra

    goc = "scripts.control_center.desktop"
    tham, q = {goc}, collections.deque([goc])
    while q:
        m = q.popleft()
        f = tep(m)
        if f is None:
            continue
        for x in nhap(f, m):
            if tep(x) is not None and x not in tham:
                tham.add(x)
                q.append(x)
    return sorted({tep(m) for m in tham if tep(m)})


class TestKhongNhapCuaSo(unittest.TestCase):
    """A — không tiến trình nền nào được mở cửa sổ console."""

    def test_moi_cho_sinh_tien_trinh_tren_duong_EXE_deu_AN_cua_so(self):
        loi = []
        for f in _bao_dong_khoi_dong():
            rel = f.relative_to(GOC).as_posix()
            if rel in MIEN_TRU:
                continue
            src = f.read_text(encoding="utf-8")
            dong = src.splitlines()
            for n in ast.walk(ast.parse(src)):
                if not isinstance(n, ast.Call):
                    continue
                ten = (n.func.attr if isinstance(n.func, ast.Attribute)
                       else getattr(n.func, "id", ""))
                if ten not in SINH:
                    continue
                if isinstance(n.func, ast.Attribute):
                    if getattr(n.func.value, "id", "") != "subprocess":
                        continue
                d = ast.dump(n)
                if ("an_cua_so" in d or "creationflags" in d
                        or "startupinfo" in d or "AN_HIEN" in d):
                    continue
                loi.append(f"{rel}:{n.lineno}  "
                           f"{dong[n.lineno - 1].strip()[:80]}")
        self.assertEqual(
            loi, [],
            "Mỗi chỗ dưới đây nhấp một cửa sổ console trong bản "
            "`--noconsole` và giành focus của người dùng. Thêm "
            "`**an_cua_so()`:\n" + "\n".join(loi))

    def test_an_cua_so_dat_dung_co_tren_windows(self):
        kw = an_cua_so()
        if sys.platform != "win32":
            self.assertEqual(kw, {}, "nền khác không có cửa sổ console")
            return
        self.assertEqual(kw["creationflags"] & 0x08000000, 0x08000000,
                         "thiếu CREATE_NO_WINDOW")
        si = kw["startupinfo"]
        self.assertEqual(si.wShowWindow, 0)          # SW_HIDE

    def test_AN_HIEN_la_rong_va_ton_tai_de_doc_ra_y_dinh(self):
        self.assertEqual(AN_HIEN, {})

    def test_tien_trinh_con_THAT_khong_mo_cua_so(self):
        """Chạy thật một lệnh console và vẫn bắt được stdout.

        Ẩn cửa sổ KHÔNG được đánh đổi bằng việc mất log — đó mới là chỗ
        một bản sửa "cho yên tĩnh" dễ làm sai.
        """
        p = subprocess.run([sys.executable, "-c", "print('xin chao')"],
                           capture_output=True, text=True, timeout=60,
                           **an_cua_so())
        self.assertEqual(p.returncode, 0)
        self.assertIn("xin chao", p.stdout)


class TestOSoanTuTrong(unittest.TestCase):
    """B — gửi xong thì ô nhập phải trống, và giữ focus."""

    def _js(self) -> str:
        return (GOC / "scripts/control_center/web/app.js").read_text(
            encoding="utf-8")

    def test_xoa_o_soan_SAU_khi_gui_thanh_cong(self):
        js = self._js()
        i = js.find("async function gui(")
        self.assertGreater(i, 0, "không tìm thấy hàm gửi")
        than = js[i:i + 2600]
        self.assertIn("o.value = ''", than.replace('"', "'"),
                      "gửi xong phải xoá ô soạn")

    def test_giu_focus_o_o_nhap(self):
        self.assertIn(".focus()", self._js())

    def test_Enter_gui_Shift_Enter_xuong_dong(self):
        js = self._js()
        self.assertIn("shiftKey", js,
                      "Shift+Enter phải xuống dòng, không gửi")

    def test_gui_HONG_thi_KHONG_xoa_o_soan(self):
        """Xoá trước khi biết kết quả = người dùng mất câu vừa gõ."""
        js = self._js()
        i = js.find("async function gui(")
        than = js[i:i + 2600]
        i_api = than.find("await api(")
        i_xoa = than.replace('"', "'").find("o.value = ''")
        self.assertGreater(i_api, 0)
        self.assertGreater(i_xoa, i_api,
                           "phải xoá SAU khi gọi API thành công")


class TestMotManHinh(unittest.TestCase):
    """C/G — một màn hình là biết hệ thống đang làm gì."""

    def _html(self) -> str:
        return (GOC / "scripts/control_center/web/index.html").read_text(
            encoding="utf-8")

    def test_co_panel_quan_sat_ben_phai(self):
        h = self._html()
        for x in ("insp-dangchay", "insp-tasks", "insp-agents",
                  "insp-usage", "insp-snapshot"):
            with self.subTest(x=x):
                self.assertIn(x, h, f"thiếu ô quan sát {x}")

    def test_khung_cu_van_con_lam_duong_go_loi(self):
        h = self._html()
        for x in ("bang-tasks", "ds-tin", "o-soan"):
            self.assertIn(x, h)


class TestUsageDungHinhDang(unittest.TestCase):
    """G — usage theo agent/provider, và frontend đọc ĐÚNG khoá.

    LỖI THẬT ĐƯỢC GHÌM Ở ĐÂY. `UsageReporter.report()` trả về
    `{local, pools, runtimes, accounts, providers}`. Frontend V0.2/V0.3
    đọc `bc.metrics` — một khoá KHÔNG tồn tại — nên bảng Usage luôn rỗng
    và dòng tóm tắt luôn là "0 hạng mục".

    Đây là hình dạng lỗi xấu nhất: không ngoại lệ, không dòng log, chỉ
    một bảng trắng trông như "chưa có dữ liệu". Bài kiểm này so hai đầu
    của ranh giới với NHAU thay vì với một hằng số chép tay, nên đổi hình
    dạng ở một bên mà quên bên kia sẽ đỏ.
    """

    def test_report_khong_he_co_khoa_metrics(self):
        from scripts.control_center.store import ControlStore
        from scripts.control_center.usage import UsageReporter
        goc = Path(tempfile.mkdtemp(prefix="cc-usage-"))
        st = ControlStore(root=goc)
        self.addCleanup(st.close)
        bc = UsageReporter(st).report("p")
        self.assertNotIn("metrics", bc,
                         "nếu khoá này xuất hiện thì frontend cũ đã đúng "
                         "— cập nhật cả hai đầu")
        for k in ("local", "pools", "providers", "provider_probe_ran"):
            self.assertIn(k, bc)

    def test_frontend_doc_dung_local_va_pools(self):
        js = (GOC / "scripts/control_center/web/app.js").read_text(
            encoding="utf-8")
        i = js.find("function usageNhom(")
        self.assertGreater(i, 0, "thiếu bộ gom usage theo nguồn")
        than = js[i:i + 1200]
        for k in ("bc.local", "bc.pools", "bc.providers"):
            self.assertIn(k, than, f"bộ gom phải đọc {k}")
        # Bo dong chu thich truoc khi doi: chinh tep nay GIAI THICH loi cu
        # bang cach nhac ten khoa sai, va mot phep kiem bat ca chu thich
        # se buoc nguoi sau xoa loi giai thich de lam no xanh.
        ma = "\n".join(d for d in js.splitlines()
                       if not d.lstrip().startswith("//"))
        self.assertNotIn("bc.metrics", ma,
                         "`metrics` không phải khoá của /api/usage")
        # `p.metrics` VAN dung — moi be quota trong `pools` co `metrics`
        # rieng. Cai sai la doc `metrics` o CAP TREN CUNG cua bao cao.
        self.assertIn("p.metrics", ma)
        # Ca hai cho ve usage phai di qua CUNG bo gom, khong tu doc lai
        # hinh dang bao cao mot lan nua.
        for ham in ("veUsageTuCache", "veInspUsageTuCache"):
            j = ma.find(f"function {ham}(")
            self.assertGreater(j, 0, f"thiếu {ham}")
            self.assertIn("usageNhom(usageCache)", ma[j:j + 200],
                          f"{ham} phải dùng bộ gom dùng chung")

    def test_moi_hang_usage_mang_ten_NGUON(self):
        """Yêu cầu là "usage theo agent/provider" — một con số không nói
        nó thuộc provider nào thì không trả lời được câu hỏi đó."""
        js = (GOC / "scripts/control_center/web/app.js").read_text(
            encoding="utf-8")
        i = js.find("function veUsageTuCache(")
        than = js[i:i + 1400]
        self.assertIn("g.nguon", than)
        h = (GOC / "scripts/control_center/web/index.html").read_text(
            encoding="utf-8")
        j = h.find('id="bang-usage"')
        self.assertIn("Nguồn", h[j:j + 400], "bảng thiếu cột Nguồn")


class TestTienDoSong(unittest.TestCase):
    """D — o chat phải nói được nó đang làm gì trong lúc chờ.

    `chat()` chạy đồng bộ; một lần mở Leader lạnh đo được 67.87s. Không
    có tín hiệu nào thì màn hình không phân biệt được "đang nghĩ" với
    "treo", và người dùng bấm lại hoặc đóng app.
    """

    def setUp(self):
        from scripts.control_center.engine import ControlCenter
        self.goc = Path(tempfile.mkdtemp(prefix="cc-buoc-"))
        self.cc = ControlCenter(root=self.goc, probe=False)
        self.addCleanup(self.cc.store.close)

    def test_buoc_rong_luc_khong_lam_gi(self):
        self.assertIsNone(self.cc.buoc_dang_lam("p"))
        self.assertIsNone(self.cc.snapshot("").get("buoc"))

    def test_dat_va_xoa_buoc(self):
        self.cc._dat_buoc("p", "Leader đang suy nghĩ")
        b = self.cc.buoc_dang_lam("p")
        self.assertEqual(b["nhan"], "Leader đang suy nghĩ")
        self.assertGreater(b["tu_luc"], 0)
        self.cc._dat_buoc("p", "")
        self.assertIsNone(self.cc.buoc_dang_lam("p"))

    def test_moc_thoi_gian_GIU_NGUYEN_qua_cac_buoc(self):
        """Đồng hồ trên màn hình đếm TỔNG thời gian chờ. Reset mỗi bước
        thì nó nói dối đúng ở chỗ người dùng đang mất kiên nhẫn."""
        self.cc._dat_buoc("p", "bước một")
        moc = self.cc.buoc_dang_lam("p")["tu_luc"]
        self.cc._dat_buoc("p", "bước hai")
        self.assertEqual(self.cc.buoc_dang_lam("p")["tu_luc"], moc)

    def test_buoc_theo_TUNG_du_an(self):
        self.cc._dat_buoc("a", "x")
        self.assertIsNone(self.cc.buoc_dang_lam("b"))

    def test_van_tay_WebSocket_co_chua_buoc(self):
        """Nếu bước không nằm trong vân tay thì tiến độ SỐNG không bao
        giờ được đẩy đi: một lần `chat()` dài không đổi task/session/chat
        nào cả, nên vân tay cũ sẽ trùng và server im lặng."""
        from scripts.control_center import webapi
        src = Path(webapi.__file__).read_text(encoding="utf-8")
        i = src.find('"locks": len(')
        self.assertGreater(i, 0)
        self.assertIn('"buoc"', src[i:i + 500])

    def test_frontend_hien_buoc_va_dong_ho(self):
        js = (GOC / "scripts/control_center/web/app.js").read_text(
            encoding="utf-8")
        self.assertIn("S.buoc", js)
        self.assertIn("dang-lam-nhan", js)
        h = (GOC / "scripts/control_center/web/index.html").read_text(
            encoding="utf-8")
        self.assertIn('id="dang-lam"', h)


class TestAnhNen(unittest.TestCase):
    """F — ảnh nền local, và nó phải BỀN qua khởi động lại.

    `wallpaper` giữ một **mã đính kèm**, không phải đường dẫn tệp. Nhận
    đường dẫn thì để vẽ được nó phải mở một endpoint đọc tệp tuỳ ý trên
    đĩa — dựng lại đúng lỗ mà `attachments.py` tồn tại để bịt.
    """

    #: Hinh dang that cua mot ma dinh kem (bam noi dung).
    AID = "a1b2c3d4e5f60718"

    def setUp(self):
        from scripts.control_center.store import ControlStore
        self.goc = Path(tempfile.mkdtemp(prefix="cc-ux-"))
        self.st = ControlStore(root=self.goc)
        self.addCleanup(self.st.close)

    def test_cai_dat_giao_dien_luu_va_doc_lai_duoc(self):
        self.assertEqual(self.st.cai_dat_ui(), {})
        self.st.luu_cai_dat_ui({"wallpaper": self.AID,
                                "dim": 0.55, "blur": 6})
        d = self.st.cai_dat_ui()
        self.assertEqual(d["wallpaper"], self.AID)
        self.assertEqual(d["dim"], 0.55)
        self.assertEqual(d["blur"], 6)

    def test_ben_qua_khoi_dong_lai(self):
        from scripts.control_center.store import ControlStore
        self.st.luu_cai_dat_ui({"wallpaper": self.AID, "dim": 0.4})
        self.st.close()
        st2 = ControlStore(root=self.goc)
        self.addCleanup(st2.close)
        self.assertEqual(st2.cai_dat_ui()["wallpaper"], self.AID)

    def test_ghi_de_giu_nguyen_khoa_khong_gui(self):
        self.st.luu_cai_dat_ui({"wallpaper": self.AID, "dim": 0.4})
        self.st.luu_cai_dat_ui({"dim": 0.7})
        d = self.st.cai_dat_ui()
        self.assertEqual(d["dim"], 0.7)
        self.assertEqual(d["wallpaper"], self.AID,
                         "đổi độ tối không được xoá ảnh nền")

    def test_khong_co_khoa_nao_giu_duong_dan_tep(self):
        """Chốt lại ranh giới: giá trị đi vào chỉ là dữ liệu, không
        có mã nào ở tầng dưới coi nó là đường dẫn để mở."""
        from scripts.control_center import webapi
        src = Path(webapi.__file__).read_text(encoding="utf-8")
        i = src.find("async def ghi_ui")
        self.assertGreater(i, 0)
        than = src[i:i + 2000]
        self.assertIn("dinh_kem.lay", than,
                      "phải xác minh mã đính kèm tồn tại")
        self.assertIn("la_anh", than, "phải từ chối tệp không phải ảnh")
        for xau in ("open(", "read_bytes", "read_text", "FileResponse"):
            self.assertNotIn(xau, than,
                             "endpoint cài đặt không được đọc tệp")


class TestChuDeToi(unittest.TestCase):
    """E — giao diện tối, và không hy sinh khả năng đọc."""

    def _css(self) -> str:
        return (GOC / "scripts/control_center/web/style.css").read_text(
            encoding="utf-8")

    def test_bang_mau_toi_duoc_khai_bang_bien(self):
        css = self._css()
        for x in ("--nen", "--chu", "--vien", "--neon"):
            self.assertIn(x, css, f"thiếu biến màu {x}")

    def test_khong_con_nen_trang_o_body(self):
        css = self._css()
        i = css.find("body")
        self.assertGreater(i, 0)
        than = css[i:i + 400].lower()
        for xau in ("#fff", "#ffffff", "white"):
            self.assertNotIn(xau, than, "body vẫn còn nền trắng")


if __name__ == "__main__":
    unittest.main(verbosity=2)
