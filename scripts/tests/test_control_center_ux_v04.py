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
import time
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


def _ma_js(van: str) -> str:
    """Bỏ dòng chú thích `//` trước khi phân tích VỊ TRÍ.

    ĐÃ VẤP HAI LẦN trong chính tệp này: một chú thích GIẢI THÍCH lỗi
    cũ bằng cách dẫn lại đoạn mã sai (`o.value = ''` SAU
    `await api(...)`, hay `if (!document.hidden) veInspUsage()`), và
    phép `find()` khớp vào chú thích đó chứ không vào mã. Bài kiểm khi
    ấy xanh/đỏ vì lời văn, không vì hành vi — và cách sửa nó tệ nhất
    là đi xoá lời giải thích.
    """
    return chr(10).join(d for d in van.splitlines()
                        if not d.lstrip().startswith('//'))


#: Chuong trinh CONSOLE ma ung dung nay co the goi. Mot loi goi mang
#: mot trong nhung ten nay o dau danh sach tham so LA mot cho sinh tien
#: trinh, bat ke ham duoc goi ten la gi.
LENH_CONSOLE = {
    "git", "agy", "agy.exe", "codex", "codex.exe", "python", "python.exe",
    "py", "py.exe", "icacls", "tasklist", "taskkill", "where", "cmd",
    "powershell", "pwsh", "node", "npm", "npx", "rclone", "gcloud",
}


def _la_sinh(n: ast.Call) -> bool:
    """Lời gọi này có sinh một tiến trình con không?

    HAI hình dạng, và hình dạng thứ hai là một lỗi đã vấp:

    1. `subprocess.run(...)` / `subprocess.Popen(...)` — hiển nhiên.
    2. `self._run(["git", ...])` — một **runner được tiêm**. Bản quét đầu
       của V0.4 chỉ tìm hình dạng (1), nên `worktree.py::verify_scope`
       lọt lưới và cửa sổ console vẫn nhấp lên trong bản đóng gói. Nhận
       theo THAM SỐ (danh sách bắt đầu bằng tên một chương trình console)
       thì tên hàm không còn quan trọng.
    """
    ten = (n.func.attr if isinstance(n.func, ast.Attribute)
           else getattr(n.func, "id", ""))
    if ten in SINH:
        if isinstance(n.func, ast.Attribute):
            if getattr(n.func.value, "id", "") == "subprocess":
                return True
        else:
            return True
    if not n.args:
        return False
    dau = n.args[0]
    if not isinstance(dau, (ast.List, ast.Tuple)) or not dau.elts:
        return False
    p0 = dau.elts[0]
    if not isinstance(p0, ast.Constant) or not isinstance(p0.value, str):
        return False
    return Path(p0.value).name.lower() in LENH_CONSOLE


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
            # MOT MODULE co the phu moi diem goi bang cach BOC runner mot
            # lan (`_boc_an_cua_so`) thay vi them kwargs o tung cho. Do
            # la hinh dang MANH HON — mot diem goi them ve sau cung duoc
            # phu tu dong — nen phep quet phai chap nhan no, khong thi no
            # se day nguoi sua ve lai cach de quen.
            boc_ca_module = "_boc_an_cua_so" in src
            for n in ast.walk(ast.parse(src)):
                if not isinstance(n, ast.Call):
                    continue
                if not _la_sinh(n):
                    continue
                d = ast.dump(n)
                if ("an_cua_so" in d or "creationflags" in d
                        or "startupinfo" in d or "AN_HIEN" in d):
                    continue
                if boc_ca_module:
                    continue
                loi.append(f"{rel}:{n.lineno}  "
                           f"{dong[n.lineno - 1].strip()[:80]}")
        self.assertEqual(
            loi, [],
            "Mỗi chỗ dưới đây nhấp một cửa sổ console trong bản "
            "`--noconsole` và giành focus của người dùng. Thêm "
            "`**an_cua_so()`:\n" + "\n".join(loi))

    def test_bat_duoc_ca_RUNNER_DUOC_TIEM(self):
        """Chứng cứ chống rỗng cho chính phép quét ở trên.

        LỖI THẬT ĐÃ VẤP: `router_v3/worktree.py::verify_scope` gọi
        `self._run(["git", …])` — một **runner được tiêm**, không phải
        `subprocess.run` — nên bản quét cũ (chỉ tìm `subprocess.run`/
        `Popen`) **không thấy nó**, và cửa sổ console vẫn nhấp lên trong
        bản đóng gói. Hai lớp phòng vệ cùng trượt đúng một chỗ.

        Bài này bắt phép quét phải nhận ra hình dạng đó: một lời gọi mà
        THAM SỐ ĐẦU là danh sách bắt đầu bằng tên một chương trình
        console, bất kể hàm được gọi tên là gì.
        """
        mau = ast.parse(
            "def f(self):\n"
            "    return self._run(['git', '-C', x, 'status'],\n"
            "                     capture_output=True)\n")
        goi = [n for n in ast.walk(mau) if isinstance(n, ast.Call)]
        self.assertTrue(any(_la_sinh(n) for n in goi),
                        "phép quét bỏ sót runner được tiêm — đúng lỗi đã "
                        "làm cửa sổ console nhấp lên ở bản V0.4 đầu")

    def test_khong_bat_bua_bai(self):
        """Và nó KHÔNG được coi mọi lời gọi có danh sách là sinh tiến
        trình — một phép quét báo động giả sẽ bị người sau tắt đi."""
        mau = ast.parse("y = ham(['khong', 'phai', 'lenh'])\n"
                        "z = self._run(cai_gi_do)\n")
        goi = [n for n in ast.walk(mau) if isinstance(n, ast.Call)]
        self.assertFalse(any(_la_sinh(n) for n in goi))

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

    def test_gui_HONG_thi_ban_nhap_KHONG_bi_mat(self):
        """Bài này TỪNG đòi điều ngược lại — "xoá SAU khi gọi API thành
        công" — và chính điều đó là DEFECT 1: tin nhắn hiện trong chat
        mà chữ còn trong ô soạn suốt cả lượt Leader (6.12s ấm / 67.87s
        lạnh). Xem `TestOSoanXoaNGAY`.

        Yêu cầu thật không phải "xoá muộn" mà là "xoá ngay VÀ không mất
        bản nháp nếu gửi hỏng". Hai điều đó không xung đột: giữ bản nháp
        trong biến rồi trả lại ở nhánh lỗi.
        """
        js = self._js()
        i = js.find("async function gui(")
        than = _ma_js(js[i:i + 3600])
        self.assertIn("const nhap = {", than,
                      "phải giữ bản nháp trước khi xoá")
        self.assertIn("tra_lai_nhap(nhap", than,
                      "nhánh lỗi phải trả bản nháp lại")
        self.assertNotIn("o.value = ''", than.split("await api(")[-1],
                         "không được còn chỗ xoá nào SAU lời gọi API")


class TestOSoanXoaNGAY(unittest.TestCase):
    """DEFECT 1 — ô soạn phải trống NGAY, không đợi lượt Leader.

    HÌNH DẠNG LỖI, và vì sao bài kiểm cũ không bắt được nó:

    `POST /api/chat` chạy trọn một lượt `chat()` ĐỒNG BỘ ở server (Leader
    quyết định, phân rã, giao việc cho Router V4) — 6.12s khi Leader đã
    ấm, 67.87s ở lần mở lạnh. Nhưng server ghi dòng chat của NGƯỜI DÙNG ở
    dòng đầu `_chat()`, nên WebSocket đẩy tin nhắn lên dòng thời gian
    trong ~1s.

    Bản trước xoá ô soạn SAU `await api(...)`. Kết quả người dùng thấy:
    tin nhắn đã hiện trong chat, mà câu vừa gõ VẪN CÒN trong ô soạn, rồi
    vài giây (hoặc cả phút) sau mới biến mất.

    Bài kiểm cũ chỉ đòi "xoá SAU khi gọi API thành công" — nên nó CHẤM
    ĐẠT đúng cái hành vi bị báo lỗi. Bài dưới đây phân biệt được:

        tin nhắn đã hiện + ô soạn CÒN chữ      -> HỎNG
        tin nhắn đã hiện + ô soạn TRỐNG ĐỒNG BỘ -> ĐẠT
    """

    def _than_gui(self) -> str:
        js = (GOC / "scripts/control_center/web/app.js").read_text(
            encoding="utf-8")
        i = js.find("async function gui(")
        self.assertGreater(i, 0, "không tìm thấy hàm gửi")
        j = js.find("\nfunction tra_lai_nhap(", i)
        self.assertGreater(j, i, "không tìm thấy hàm trả lại bản nháp")
        return _ma_js(js[i:j])

    def test_xoa_o_soan_TRUOC_moi_await(self):
        """Phép kiểm cốt lõi: `o.value = ''` phải nằm TRƯỚC `await` đầu
        tiên trong thân hàm — tức là trong cùng lượt tương tác."""
        than = self._than_gui().replace('"', "'")
        i_xoa = than.find("o.value = ''")
        i_await = than.find("await api(")
        self.assertGreater(i_xoa, 0, "không thấy chỗ xoá ô soạn")
        self.assertGreater(i_await, 0, "không thấy `await api(`")
        self.assertLess(
            i_xoa, i_await,
            "ô soạn bị xoá SAU một `await` — người dùng sẽ thấy tin nhắn "
            "hiện trong chat mà chữ vẫn còn trong ô soạn cho tới khi cả "
            "lượt Leader xong (đo được 6.12s ấm / 67.87s lạnh)")

    def test_khay_dinh_kem_cung_trong_NGAY(self):
        than = self._than_gui()
        i_dk = than.find("dinhKemChoGui = []")
        i_await = than.find("await api(")
        self.assertGreater(i_dk, 0)
        self.assertLess(i_dk, i_await,
                        "khay đính kèm cũng phải trống ngay, không thì ô "
                        "soạn trống mà thẻ tệp vẫn còn")

    def test_giu_focus_NGAY_khong_doi_finally(self):
        than = self._than_gui()
        i_focus = than.find("o.focus()")
        i_await = than.find("await api(")
        self.assertGreater(i_focus, 0)
        self.assertLess(i_focus, i_await,
                        "phải trả con trỏ về ô soạn ngay, để gõ tiếp được "
                        "trong lúc Leader còn đang nghĩ")

    def test_ban_nhap_duoc_GIU_de_lay_lai(self):
        than = self._than_gui()
        self.assertIn("const nhap = {", than,
                      "xoá đồng bộ thì phải giữ bản nháp lại")
        self.assertIn("tra_lai_nhap(nhap", than,
                      "đường hỏng phải gọi bộ trả lại bản nháp")

    def test_tra_lai_KHONG_de_len_van_ban_moi(self):
        js = (GOC / "scripts/control_center/web/app.js").read_text(
            encoding="utf-8")
        i = js.find("function tra_lai_nhap(")
        self.assertGreater(i, 0)
        than = js[i:i + 1200]
        self.assertIn("o.value.trim() === ''", than,
                      "chỉ được trả bản nháp vào ô soạn khi ô ĐANG TRỐNG")
        self.assertIn("nhapChuaGui = nhap", than,
                      "ô soạn có chữ mới thì phải giữ bản nháp ở chỗ khác")

    def test_chan_gui_trung_khi_giu_Enter(self):
        js = (GOC / "scripts/control_center/web/app.js").read_text(
            encoding="utf-8")
        self.assertIn("if (dangGui) return;", js)
        i = js.find("o.addEventListener('keydown'")
        than = js[i:i + 900]
        self.assertIn("e.repeat", than,
                      "giữ Enter làm bàn phím bắn ra một chuỗi keydown")
        self.assertIn("shiftKey", than)


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


class TestHoSoWebView2(unittest.TestCase):
    """Hồ sơ WebView2 theo THƯ MỤC GỐC, không dùng chung cả máy.

    SỰ CỐ THẬT, đo được trên bản đóng gói của chính V0.4:

        pywebview WebView2 initialization failed with exception:
        (0x8007139F): The group or resource is not in the correct state
        to perform the requested operation.

    `pywebview` mặc định để hồ sơ ở `%APPDATA%/pywebview/EBWebView` —
    MỘT thư mục dùng chung cho MỌI ứng dụng pywebview trên máy. WebView2
    cho nhiều tiến trình dùng chung một hồ sơ nhưng CHỈ KHI
    `AdditionalBrowserArguments` giống nhau, nên một bản thứ hai của app
    (hoặc một app pywebview của bên thứ ba) đủ để `webview.start()` nổ
    ngay lúc mở, với một thông điệp không ai suy ra được nguyên nhân.

    Đây đúng là bất biến `ten_mutex_cua` đã chọn: "một thực thể" tính
    theo thư mục gốc, để một bản KIỂM chạy được cạnh bản của người dùng.
    Hồ sơ toàn máy phá lại đúng bảo đảm đó.
    """

    def test_hai_goc_khac_nhau_thi_KHAC_ho_so(self):
        from scripts.control_center.desktop_shell import duong_webview2
        a = Path(tempfile.mkdtemp(prefix="cc-wv-a-"))
        b = Path(tempfile.mkdtemp(prefix="cc-wv-b-"))
        self.assertNotEqual(duong_webview2(a), duong_webview2(b))

    def test_cung_goc_thi_cung_ho_so(self):
        from scripts.control_center.desktop_shell import duong_webview2
        d = Path(tempfile.mkdtemp(prefix="cc-wv-c-"))
        self.assertEqual(duong_webview2(d), duong_webview2(d))

    def test_hoa_thuong_khong_lam_ra_hai_ho_so(self):
        from scripts.control_center.desktop_shell import duong_webview2
        d = Path(tempfile.mkdtemp(prefix="cc-wv-d-"))
        self.assertEqual(duong_webview2(str(d).upper()),
                         duong_webview2(str(d).lower()))

    def test_KHONG_nam_duoi_goc_de_khong_vuot_MAX_PATH(self):
        """WebView2 tạo cây sâu (`EBWebView/Default/…`). Đặt dưới một
        `goc` đã dài — ví dụ thư mục tạm của bộ kiểm — sẽ đẩy tổng đường
        dẫn qua `MAX_PATH` và lỗi hiện ra ở một chỗ không liên quan."""
        from scripts.control_center.desktop_shell import duong_webview2
        d = Path(tempfile.mkdtemp(prefix="cc-wv-e-"))
        p = duong_webview2(d)
        self.assertNotIn(str(d).lower(), str(p).lower())
        # Còn chỗ cho `EBWebView/Default/...` bên trong.
        self.assertLess(len(str(p)), 160, str(p))

    def test_dung_cung_khoa_bam_voi_mutex(self):
        """Một khoá, hai người dùng: đổi cách băm ở một chỗ mà quên chỗ
        kia thì "một thực thể" và "một hồ sơ" lệch nhau."""
        from scripts.control_center.desktop_shell import (duong_webview2,
                                                          ten_mutex_cua)
        d = Path(tempfile.mkdtemp(prefix="cc-wv-f-"))
        self.assertTrue(ten_mutex_cua(d).endswith(duong_webview2(d).name))

    def test_desktop_TRUYEN_storage_path_vao_webview_start(self):
        src = (GOC / "scripts/control_center/desktop.py").read_text(
            encoding="utf-8")
        # `rfind`: chinh tep do GIAI THICH su co bang cach nhac ten
        # `webview.start()` trong mot dong chu thich o tren, va
        # `find` se dung vao do.
        i = src.rfind("        webview.start(")
        self.assertGreater(i, 0)
        than = src[i:i + 260]
        self.assertIn("storage_path=", than,
                      "không truyền thì pywebview dùng thư mục CHUNG "
                      "của cả máy và app chết lúc mở với 0x8007139F")
        self.assertIn("duong_webview2(", src)


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


class TestUsageDemThat(unittest.TestCase):
    """DEFECT 2 — số Usage phải phản ánh sổ Router thật.

    Bằng chứng tay trên bản đóng gói: một việc được tạo và tới DONE, AG01
    được giao, phiên BUSY rồi IDLE, kết quả báo ~57s — mà bảng Usage vẫn
    hiện 0/0/0/0/0.

    Bài kiểm cũ chỉ đếm SỐ HẠNG MỤC ("43 hạng mục"), nên nó vẫn ĐẠT khi
    mọi giá trị bằng 0. Bài dưới đây đòi GIÁ TRỊ.
    """

    def setUp(self):
        from scripts.control_center.store import ControlStore
        self.goc = Path(tempfile.mkdtemp(prefix="cc-usg-"))
        self.st = ControlStore(root=self.goc)
        self.addCleanup(self.st.close)

    def _gieo_mot_luot_that(self, *, pid=None, tuoi=0.0):
        """Một việc ĐÃ CHẠY XONG + một phiên, đúng hình dạng sổ thật."""
        from scripts.control_center.model import (Project, Session,
                                                  SessionState, Task,
                                                  TaskState)
        now = time.time()
        self.st.luu_project(Project(project_id="p", name="Dự án",
                                    repo_path=str(self.goc)))
        self.st.luu_task(Task(
            task_id="p.t1", project_id="p", title="Việc thật",
            objective="chạy thật", state=TaskState.DONE,
            owner_session="s-1", attempts=1,
            started_at=now - 57.0, ended_at=now))
        self.st.luu_session(Session(
            session_id="s-1", project_id="p", provider="antigravity",
            runtime_id="AG01", model_id="gemini-3.8-flash-high",
            state=SessionState.IDLE, pid=pid,
            created_at=now - 60, last_activity=now - tuoi))
        # `luu_session` LUON dat `last_activity = time.time()` (no ghi
        # nhan mot lan cham vao phien), nen phai ha tuoi hang bang mot
        # UPDATE — dung hinh dang mot hang con lai tu lan chay truoc.
        if tuoi:
            self.st._c().execute(
                "UPDATE sessions SET last_activity=? WHERE session_id=?",
                (now - tuoi, "s-1"))

    def _so(self, project="p"):
        from scripts.control_center.usage import UsageReporter
        return {m.label: m.value
                for m in UsageReporter(self.st).cuc_bo(project)}

    def test_sau_mot_luot_THAT_moi_con_so_deu_LON_HON_0(self):
        self._gieo_mot_luot_that()
        d = self._so()
        self.assertGreater(d["việc đã tạo"], 0)
        self.assertGreater(d["lượt dispatch agent"], 0)
        self.assertGreater(d["phiên đã dựng"], 0)
        self.assertGreater(d["giây agent tích luỹ"], 0,
                           "việc chạy 57s mà tích luỹ 0s là lỗi kế toán")
        self.assertGreaterEqual(d["giây agent tích luỹ"], 56.0)

    def test_phien_con_song_KHONG_dem_hang_LICH_SU(self):
        """`recover()` để phiên không PID ở `IDLE` — CỐ Ý, để không dựng
        phiên thứ hai chồng lên một tiến trình có thể còn sống. Nhưng một
        hàng như thế nằm lại trong sổ MÃI MÃI, nên đếm nó là "còn sống"
        biến một con số hiện tại thành một con số lịch sử."""
        self._gieo_mot_luot_that(pid=None, tuoi=4000.0)   # im lặng 66 phút
        d = self._so()
        self.assertEqual(d["phiên còn sống"], 0,
                         "phiên không PID, im lặng hơn 15 phút, là một "
                         "hàng cũ — không phải phiên đang sống")
        self.assertGreater(d["phiên đã dựng"], 0,
                           "tổng lịch sử thì VẪN phải đếm")

    def test_phien_vua_hoat_dong_thi_VAN_tinh_la_song(self):
        """Và phép siết không được siết quá: một phiên không PID vừa hoạt
        động là phiên đang dùng được, phải đếm."""
        self._gieo_mot_luot_that(pid=None, tuoi=5.0)
        self.assertEqual(self._so()["phiên còn sống"], 1)

    def test_phien_co_PID_da_chet_thi_khong_tinh(self):
        # PID chac chan khong ton tai.
        self._gieo_mot_luot_that(pid=4294967294, tuoi=1.0)
        self.assertEqual(self._so()["phiên còn sống"], 0)

    def test_ben_qua_dong_mo_lai(self):
        """Số đếm nằm trong SQLite nên phải sống qua một vòng đóng/mở."""
        from scripts.control_center.store import ControlStore
        self._gieo_mot_luot_that()
        truoc = self._so()
        self.st.close()
        st2 = ControlStore(root=self.goc)
        self.addCleanup(st2.close)
        from scripts.control_center.usage import UsageReporter
        sau = {m.label: m.value for m in UsageReporter(st2).cuc_bo("p")}
        for k in ("việc đã tạo", "lượt dispatch agent", "phiên đã dựng",
                  "giây agent tích luỹ"):
            self.assertEqual(truoc[k], sau[k], k)
            self.assertGreater(sau[k], 0, k)

    def test_KHONG_dieu_phoi_nao_doi_theo(self):
        """Phép siết chỉ ở tầng BÁO CÁO. `SessionManager` vẫn dùng
        `state.alive` để quyết REUSE/CREATE/WAIT — đổi chỗ đó là đổi
        semantics điều phối, đúng thứ bị cấm."""
        src = (GOC / "scripts/control_center/sessions.py").read_text(
            encoding="utf-8")
        self.assertNotIn("_phien_that_su_song", src)
        usg = (GOC / "scripts/control_center/usage.py").read_text(
            encoding="utf-8")
        self.assertIn("_phien_that_su_song", usg)


class TestUsageLamMoiKhiDoi(unittest.TestCase):
    """DEFECT 2, phần frontend: vì sao thẻ Usage đứng ở 0 mãi.

    Bản trước lam moi usage bằng
    `setInterval(() => { if (!document.hidden) veInspUsage(); }, 60000)`.
    `document.hidden` KHÔNG đáng tin trong cửa sổ WebView2 đóng gói — đo
    được 1/10 lần lấy mẫu trên bản EXE cho `visibilityState === "hidden"`
    trong khi cửa sổ đang mở. Nên phép làm mới không bao giờ chạy và thẻ
    giữ nguyên ảnh chụp lúc khởi động (toàn số 0), trong khi thẻ
    Tasks/Agents vẫn sống vì chúng đi theo WebSocket.
    """

    def _js(self) -> str:
        return (GOC / "scripts/control_center/web/app.js").read_text(
            encoding="utf-8")

    def test_KHONG_con_gate_document_hidden_tren_usage(self):
        js = self._js()
        i = js.find("setInterval(veInspUsage")
        self.assertGreater(i, 0,
                           "usage phải có một đồng hồ KHÔNG điều kiện")
        # Khong con dong nao gate usage theo `document.hidden`.
        # Chi xet DONG HO. `visibilitychange` cung nhac
        # `document.hidden`, nhung do la lam moi KHI HIEN LAI — dung
        # huong, khong phai mot cai gate.
        for d in _ma_js(js).splitlines():
            if ("setInterval" in d and "veInspUsage" in d
                    and "document.hidden" in d):
                self.fail(f"đồng hồ usage vẫn bị gate: {d}")

    def test_lam_moi_usage_khi_van_tay_viec_phien_DOI(self):
        js = self._js()
        i = js.find("function veHet(")
        than = js[i:i + 1400]
        self.assertIn("dauUsage", than,
                      "phải lấy lại usage khi trạng thái đổi, không chỉ "
                      "theo đồng hồ")
        self.assertIn("veInspUsage()", than)
        self.assertIn("attempts", than,
                      "vân tay phải gồm số lượt thử — `lượt dispatch "
                      "agent` đếm đúng thứ đó")

    def test_lam_moi_khi_cua_so_hien_lai(self):
        self.assertIn("visibilitychange", self._js())

    def test_anh_chup_git_VAN_giu_nhip_cham(self):
        """Và phép sửa không được nới cả ô đắt: ảnh chụp dự án chạy ~6
        lệnh `git` mỗi lần, tức ~6 tiến trình con — nó phải ở lại nhịp
        chậm, không theo vân tay."""
        js = self._js()
        self.assertIn("if (!document.hidden) veInspSnapshot();", js)
        i = js.find("function veHet(")
        self.assertNotIn("veInspSnapshot", js[i:i + 1400])


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
