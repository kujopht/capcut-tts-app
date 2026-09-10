"""UTF-8 TƯỜNG MINH trên locale cp1252 — bài kiểm chống tái phạm.

SỰ CỐ ĐƯỢC GHÌM Ở ĐÂY. `Router Control Center.exe` đã đóng gói **chết ngay
khi bấm đôi**, trên máy Windows của người dùng:

    Failed to execute script 'desktop' due to unhandled exception:
    UnicodeEncodeError: 'charmap' codec can't encode character '\\u01b0'
    character maps to <undefined>
    ... desktop.py line 145 -> encodings/cp1252.py

`U+01B0` là chữ **ư**. Dòng đó là `print(f"[desktop] {kh.ly_do}")`, và ở
lần mở đầu tiên `quyet_dinh()` trả về `ly_do = "chưa có backend nào — tự
chạy"`. Câu ấy có bốn ký tự ngoài cp1252: `ư` `—` `ự` `ạ`.

GỐC RỄ: `print()` giao chuỗi cho **tầng văn bản** của luồng, và codec của
tầng đó do **locale của Windows** quyết định. Lỗi không nằm ở tiếng Việt và
không nằm ở console — lỗi là **để locale quyết định codec** cho dữ liệu ta
đã biết chắc là Unicode. Cách sửa gốc rễ là tự mã hoá UTF-8 rồi ghi BYTE:
UTF-8 biểu diễn được mọi điểm mã Unicode nên phép mã hoá đó KHÔNG THỂ thất
bại, và không mất một byte tiếng Việt nào. Xem `ghi_utf8.py`.

VÌ SAO BỘ KIỂM TỰ ĐỘNG CŨ KHÔNG BẮT ĐƯỢC — phần đáng nhớ nhất:
`control_center_desktop_acceptance.py` **tự tiêm `PYTHONUTF8=1` và
`PYTHONIOENCODING=utf-8`** vào tiến trình con. Nó đo một môi trường không
người dùng nào có. 19/19 xanh trên một đường không ai đi. Nên tệp này làm
điều ngược lại: nó **CƯỠNG CHẾ** locale hẹp và *tự kiểm tra rằng mình đã
cưỡng chế thành công* trước khi tin bất kỳ kết quả nào.

    Nếu thấy `PYTHONIOENCODING` trong tệp này, đọc kỹ: nó dùng để LÀM HẸP
    tiến trình con (bắt nó dùng cp1252), KHÔNG dùng để sửa lỗi. Bài kiểm
    `test_khung_kiem_that_su_han_che_duoc` sẽ ĐỎ nếu ai nới nó thành utf-8.
"""
from __future__ import annotations

import ast
import collections
import io
import json
import locale
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.ghi_utf8 import (  # noqa: E402
    GhiUTF8, duong_nhat_ky, hop_thoai_loi)

#: Ba câu yêu cầu nghiệm thu đòi ĐÚNG TỪNG CHỮ.
CAU = ("Đường dẫn thử nghiệm", "Hàng đợi sản xuất", "Người dùng")

#: Các ký tự yêu cầu nghiệm thu đòi, ĐÚNG danh sách này.
KY_TU = ("ă", "â", "đ", "ê", "ô", "ơ", "ư",
         "Ă", "Â", "Đ", "Ê", "Ô", "Ơ", "Ư")

#: Ký tự trong báo lỗi thật của người dùng: `ư`.
U01B0 = "ư"

#: Câu `quyet_dinh()` trả về ở lần mở đầu tiên — chuỗi ĐÃ làm EXE chết.
LY_DO_GAY_CHET = "chưa có backend nào — tự chạy"


def _ma_hoa_duoc_cp1252(s: str) -> bool:
    try:
        s.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def _luong_cp1252():
    """Một luồng văn bản cp1252 NGHIÊM NGẶT — máy của người dùng, thu nhỏ.

    `errors="strict"` là mặc định, viết ra tường minh để nói rõ ý: bài kiểm
    này MUỐN ngoại lệ, vì ngoại lệ là thứ người dùng đã thấy.
    """
    dem = io.BytesIO()
    return dem, io.TextIOWrapper(dem, encoding="cp1252", errors="strict",
                                 write_through=True)


def _than_ma(rel: str) -> str:
    """Mã của một tệp, KHÔNG có chú thích và KHÔNG có docstring của module.

    Cần thế vì `ghi_utf8.py` cố ý *kể về* những cách bị cấm (`chcp`,
    `PYTHONUTF8`, `errors="replace"`) trong docstring — kể lại một cách sai
    để đừng ai làm lại không phải là dùng nó.
    """
    src = (GOC / rel).read_text(encoding="utf-8")
    cay = ast.parse(src)
    ds = ast.get_docstring(cay, clean=False)
    dong = src.splitlines()
    bo = set()
    if ds is not None and cay.body:
        n0 = cay.body[0]
        bo = set(range(n0.lineno, (n0.end_lineno or n0.lineno) + 1))
    return "\n".join(d for i, d in enumerate(dong, 1)
                     if i not in bo and not d.strip().startswith("#"))


# --------------------------------------------------------------------------
# Bao đóng import của `desktop.py` = "đường khởi động trực tiếp" trong yêu
# cầu số 4. Tính bằng AST chứ không gõ tay: gõ tay thì thêm một import mới
# là bài kiểm lặng lẽ mất phạm vi mà không ai biết.
# --------------------------------------------------------------------------
def _tep_cua(mod: str):
    p = GOC.joinpath(*mod.split("."))
    for c in (p.with_suffix(".py"), p / "__init__.py"):
        if c.is_file():
            return c
    return None


def _import_cua(f: Path, mod: str):
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
                base = goi.split(".")
                m = ".".join(base[:len(base) - n.level + 1]
                             + ([n.module] if n.module else []))
            else:
                m = n.module or ""
            if m.startswith("scripts"):
                ra.add(m)
                for al in n.names:          # `from goi import module`
                    ra.add(m + "." + al.name)
    return ra


def bao_dong_khoi_dong():
    """Mọi tệp `scripts/**` mà việc mở EXE có thể nạp tới."""
    goc_mod = "scripts.control_center.desktop"
    tham, q = {goc_mod}, collections.deque([goc_mod])
    while q:
        m = q.popleft()
        f = _tep_cua(m)
        if f is None:
            continue
        for x in _import_cua(f, m):
            if _tep_cua(x) is not None and x not in tham:
                tham.add(x)
                q.append(x)
    return sorted({_tep_cua(m) for m in tham if _tep_cua(m)})


#: Bốn tệp NGƯỜI DÙNG chạm trực tiếp. Ở đây luật nghiêm hơn cả bao đóng:
#: không một `print()` nào, vì `print()` chính là dòng đã làm EXE chết.
VO_KHOI_DONG = ("scripts/control_center/desktop.py",
                "scripts/control_center/desktop_shell.py",
                "scripts/control_center/webmain.py",
                "scripts/control_center/ghi_utf8.py")

#: `.open`/`open` KHÔNG mở tệp văn bản — không có codec nào để sai.
OPEN_KHONG_PHAI_TEP = {"os", "webbrowser"}

#: `json.dumps` thiếu `ensure_ascii=False` mà đã soi từng chỗ và chứng minh
#: an toàn. Khoá theo DÒNG MÃ, không theo số dòng: dịch dòng thì không sao,
#: đổi nội dung thì bài kiểm đỏ và người sau buộc phải soi lại.
JSON_MIEN_TRU = {
    ("scripts/control_center/webapi.py",
     "gon = json.dumps("):
        "dấu vân tay so sánh thay đổi giữa hai nhịp WebSocket; không ghi "
        "đĩa, không gửi đi đâu. Escape là song ánh nên vẫn là khoá đúng.",
    ("scripts/router_v3/native_worker.py",
     'return json.dumps({"event": "user",'):
        "đi vào `subprocess.run(..., encoding=\"utf-8\")` — UTF-8 tường "
        "minh; escape của JSON là không mất mát.",
    ("scripts/router_v3/warm_pool.py",
     'return (json.dumps({"event": "user",'):
        "ngay sau đó là `.encode(\"utf-8\")` rồi ghi vào ống NHỊ PHÂN.",
    ("scripts/router_v3/opencode_adapter.py",
     'du_lieu = json.dumps(body).encode("utf-8") if body is not None '
     'else None'):
        "`.encode(\"utf-8\")` tường minh cho thân HTTP; không phải văn bản "
        "cho người đọc.",
    ("scripts/router_v4/antigravity_launcher.py",
     'os.write(fd, json.dumps({"pid": os.getpid(),'):
        "`.encode(\"utf-8\")` tường minh, và nội dung chỉ có pid + mốc thời "
        "gian — không có chữ nào của con người.",
    ("scripts/router_v4/envelope.py",
     "pb.truncated_bytes = max(0, len(tho) - len(json.dumps(pb.to_dict())))"):
        "chỉ ĐO độ dài để báo số byte đã cắt; chuỗi bị bỏ đi ngay sau đó.",
}

#: Cách sửa BỊ CẤM (yêu cầu số 2), quét trên chính vỏ khởi động.
CACH_BI_CAM = ('errors="replace"', "errors='replace'",
               'errors="ignore"', "errors='ignore'",
               "PYTHONUTF8", "PYTHONIOENCODING", "chcp")


class TestGiaDinh(unittest.TestCase):
    """Dữ liệu kiểm phải THẬT SỰ nguy hiểm, nếu không cả tệp này là trang trí."""

    def test_ranh_gioi_cp1252_dung_nhu_do_duoc(self):
        """Sáu trong mười bốn ký tự yêu cầu NẰM TRONG cp1252. Ghi ra cho rõ.

        `â ê ô Â Ê Ô` thuộc khối Latin-1 nên cp1252 mã hoá được; tám ký tự
        còn lại (`ă đ ơ ư Ă Đ Ơ Ư`) thì không. Bài kiểm này chốt đúng ranh
        giới ấy, vì nếu ai đó chỉ kiểm bằng `â` thì phép kiểm sẽ xanh mà
        chẳng chứng minh gì — `â` sống sót qua cp1252.
        """
        ngoai = tuple(c for c in KY_TU if not _ma_hoa_duoc_cp1252(c))
        trong = tuple(c for c in KY_TU if _ma_hoa_duoc_cp1252(c))
        self.assertEqual(ngoai, ("ă", "đ", "ơ", "ư", "Ă", "Đ", "Ơ", "Ư"))
        self.assertEqual(trong, ("â", "ê", "ô", "Â", "Ê", "Ô"))
        self.assertIn(U01B0, ngoai, "chữ trong báo lỗi thật phải nằm ở đây")

    def test_moi_cau_yeu_cau_deu_ngoai_cp1252(self):
        for s in CAU:
            self.assertFalse(_ma_hoa_duoc_cp1252(s), repr(s))

    def test_u01b0_dung_la_chu_u_trong_bao_loi(self):
        self.assertEqual(U01B0, "ư")
        self.assertEqual(ord(U01B0), 0x01B0)
        self.assertIn(U01B0, LY_DO_GAY_CHET)

    def test_luong_cp1252_that_su_tu_choi(self):
        """Khung kiểm không nâng ngoại lệ = nó không mô phỏng gì cả."""
        _, txt = _luong_cp1252()
        with self.assertRaises(UnicodeEncodeError):
            txt.write(LY_DO_GAY_CHET)
            txt.flush()

    def test_locale_may_nay_duoc_ghi_lai(self):
        """Không phải phép xác nhận — là ghi chép để đọc khi bài kiểm đỏ."""
        self.assertIsInstance(locale.getpreferredencoding(False), str)


class TestChungLaThat(unittest.TestCase):
    """ĐÚNG sự cố người dùng gặp — yêu cầu số 11."""

    def setUp(self):
        self.goc = Path(tempfile.mkdtemp(prefix="cc-utf8-"))

    def test_ly_do_lan_mo_dau_tien_that_su_chua_chu_u(self):
        """Chuỗi gây chết không do tôi bịa — nó tới từ mã thật."""
        from scripts.control_center.desktop_shell import quyet_dinh
        kh = quyet_dinh(self.goc, co_thuc_the_khac=False, cong_muon=0)
        self.assertEqual(kh.hanh_dong, "tu_chay")
        self.assertIn(U01B0, kh.ly_do,
                      f"ly_do={kh.ly_do!r} không còn chứa 'ư' — nếu câu đã "
                      f"đổi thì cập nhật LY_DO_GAY_CHET, đừng bỏ bài kiểm")
        self.assertFalse(_ma_hoa_duoc_cp1252(kh.ly_do))

    def test_print_tai_hien_dung_ngoai_le_cua_nguoi_dung(self):
        """Mã CŨ. Giữ lại để chứng minh bài kiểm dưới không phải may mắn."""
        from scripts.control_center.desktop_shell import quyet_dinh
        kh = quyet_dinh(self.goc, co_thuc_the_khac=False, cong_muon=0)
        _, txt = _luong_cp1252()
        with self.assertRaises(UnicodeEncodeError) as ngl:
            print(f"[desktop] {kh.ly_do}", file=txt)
            txt.flush()
        # `charmap`, không phải `cp1252` — và đó ĐÚNG là chữ trong báo lỗi
        # người dùng gửi: "'charmap' codec can't encode character".
        # `cp1252` dùng bộ giải mã bảng chung nên tự gọi mình là `charmap`.
        self.assertEqual(ngl.exception.encoding, "charmap")
        self.assertIn("maps to <undefined>", str(ngl.exception))
        # Ký tự cụ thể làm nó vỡ phải ĐÚNG là `ư` = U+01B0, y như báo lỗi.
        vo = ngl.exception.object[ngl.exception.start]
        self.assertEqual((vo, hex(ord(vo))), (U01B0, "0x1b0"))

    def test_ghi_utf8_di_qua_dung_cho_do(self):
        """Mã MỚI trên đúng luồng cp1252 đó: không ngoại lệ, không mất byte."""
        from scripts.control_center.desktop_shell import quyet_dinh
        kh = quyet_dinh(self.goc, co_thuc_the_khac=False, cong_muon=0)
        dem, _ = _luong_cp1252()
        ghi = GhiUTF8(ra_luong=False)
        ghi._nhi = [dem]                   # đúng tầng NHỊ PHÂN của luồng đó
        ghi(f"[desktop] {kh.ly_do}")
        self.assertEqual(dem.getvalue().decode("utf-8"),
                         f"[desktop] {kh.ly_do}\n")

    def test_desktop_py_khong_con_mot_print_nao(self):
        """Dòng 145 cũ là `print(...)`. Nó không được phép quay lại."""
        src = (GOC / "scripts/control_center/desktop.py").read_text(
            encoding="utf-8")
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id == "print":
                self.fail(f"desktop.py:{n.lineno} lại có print() — đó chính "
                          f"là lỗi đã làm EXE chết")


class TestGhiUTF8(unittest.TestCase):
    def setUp(self):
        self.goc = Path(tempfile.mkdtemp(prefix="cc-ghi-"))

    def test_ghi_ra_luong_la_byte_utf8_nguyen_ven(self):
        for s in CAU + KY_TU:
            dem = io.BytesIO()
            ghi = GhiUTF8(ra_luong=False)
            ghi._nhi = [dem]
            ghi(s)
            self.assertEqual(dem.getvalue(), (s + "\n").encode("utf-8"))
            self.assertEqual(dem.getvalue().decode("utf-8"), s + "\n")

    def test_tep_nhat_ky_la_utf8_chu_khong_phai_locale(self):
        tep = duong_nhat_ky(self.goc)
        ghi = GhiUTF8(tep, ra_luong=False)
        for s in CAU:
            ghi(s)
        tho = tep.read_bytes()
        self.assertEqual(tho.decode("utf-8").splitlines(), list(CAU))
        # Đọc lại bằng cp1252 mà RA ĐÚNG thì tệp là ASCII và bài kiểm không
        # chứng minh gì — nên nó BUỘC phải khác.
        self.assertNotEqual(tho.decode("cp1252", errors="replace"),
                            tho.decode("utf-8"))

    def test_ghi_them_khong_ghi_de(self):
        tep = duong_nhat_ky(self.goc)
        GhiUTF8(tep, ra_luong=False)("Người dùng")
        GhiUTF8(tep, ra_luong=False)("Hàng đợi sản xuất")
        self.assertEqual(tep.read_text(encoding="utf-8").splitlines(),
                         ["Người dùng", "Hàng đợi sản xuất"])

    def test_dat_tep_muon_tu_tao_thu_muc_cha(self):
        ghi = GhiUTF8(ra_luong=False)
        self.assertIsNone(ghi.tep)
        ghi("dòng này chưa có tệp — không được nâng ngoại lệ")
        tep = duong_nhat_ky(self.goc / "chưa" / "tồn tại")
        ghi.dat_tep(tep)
        ghi("Đường dẫn thử nghiệm")
        self.assertEqual(tep.read_text(encoding="utf-8"),
                         "Đường dẫn thử nghiệm\n")

    def test_stdout_la_none_thi_im_lang_chu_khong_no(self):
        """Thực tế của bản `--noconsole`: `sys.stdout` có thể là `None`."""
        cu = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = None
        try:
            GhiUTF8(duong_nhat_ky(self.goc))("Người dùng")
        finally:
            sys.stdout, sys.stderr = cu
        self.assertEqual(duong_nhat_ky(self.goc).read_text(encoding="utf-8"),
                         "Người dùng\n")

    def test_stdout_khong_co_buffer_thi_cung_khong_no(self):
        class _Khong:
            encoding = "cp1252"

            def write(self, _):            # pragma: no cover
                raise AssertionError("không được đi qua tầng văn bản")

        cu = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = _Khong()
        try:
            GhiUTF8(duong_nhat_ky(self.goc))("Hàng đợi sản xuất")
        finally:
            sys.stdout, sys.stderr = cu
        self.assertIn("Hàng đợi sản xuất",
                      duong_nhat_ky(self.goc).read_text(encoding="utf-8"))

    def test_luong_da_dong_thi_tep_van_con(self):
        dem = io.BytesIO()
        dem.close()
        tep = duong_nhat_ky(self.goc)
        ghi = GhiUTF8(tep, ra_luong=False)
        ghi._nhi = [dem]
        ghi("Đường dẫn thử nghiệm")        # không được nâng ngoại lệ
        self.assertEqual(tep.read_text(encoding="utf-8"),
                         "Đường dẫn thử nghiệm\n")

    def test_khong_bao_gio_nang_ngoai_le_ra_ngoai(self):
        """Một dòng chẩn đoán không được hạ ứng dụng. Lần trước nó đã hạ."""
        class _No:
            def write(self, _):
                raise OSError("ống vỡ")

            def flush(self):
                raise OSError("ống vỡ")

        ghi = GhiUTF8(ra_luong=False)
        ghi._nhi = [_No()]
        ghi("Người dùng")                  # đạt = không nâng gì cả

    def test_hop_thoai_loi_khong_no_ngoai_windows(self):
        """Đúng như TÊN của nó: đường NGOÀI Windows phải trả về im lặng.

        BẢN TRƯỚC TREO CẢ BỘ KIỂM (đo 2026-09-10, `pytest` hết giờ ở đúng bài
        này, exit 124, lặp lại được). Nó gọi `hop_thoai_loi` THẲNG trên
        Windows, nên `MessageBoxW` bật một hộp thoại MODAL và chặn luồng gọi
        cho tới khi có người BẤM — một bài kiểm không thể chạy không người
        trực. Nay: nhánh ngoài-Windows kiểm bằng cách ép `sys.platform`
        (đúng tên bài), nhánh Windows kiểm bằng cách thay `MessageBoxW` để
        khẳng định "không nâng ngoại lệ" mà không dựng hộp thoại nào.
        """
        import ctypes
        from unittest import mock
        from scripts.control_center import ghi_utf8 as G

        # 1. NGOÀI Windows: trả về ngay, không chạm ctypes.
        with mock.patch.object(G.sys, "platform", "linux"):
            hop_thoai_loi("Router Control Center", "Đường dẫn thử nghiệm")

        # 2. TRÊN Windows: gọi đúng MessageBoxW, không nâng gì — hộp thoại
        #    được thay nên không có gì chặn.
        if sys.platform == "win32":
            goi = []
            with mock.patch.object(ctypes.windll.user32, "MessageBoxW",
                                   lambda *a: goi.append(a) or 1):
                hop_thoai_loi("Router Control Center", "Đường dẫn thử nghiệm")
            self.assertEqual(len(goi), 1, "phải gọi MessageBoxW đúng một lần")
            self.assertIn("Đường dẫn thử nghiệm", goi[0])

    def test_ghi_utf8_khong_dung_cach_bi_cam(self):
        than = _than_ma("scripts/control_center/ghi_utf8.py")
        for x in CACH_BI_CAM:
            self.assertNotIn(x, than, f"ghi_utf8.py dùng cách bị cấm {x!r}")


class TestKhongPhuThuocLocale(unittest.TestCase):
    """Yêu cầu số 4: KHÔNG chỗ nào trên đường khởi động để locale quyết định."""

    @classmethod
    def setUpClass(cls):
        cls.teps = bao_dong_khoi_dong()

    @staticmethod
    def _kw(n, ten):
        for k in n.keywords:
            if k.arg == ten:
                return k
        return None

    @staticmethod
    def _dong(dong, n):
        i = getattr(n, "lineno", 0)
        return dong[i - 1].strip() if 0 < i <= len(dong) else ""

    def test_bao_dong_khong_rong_va_co_dung_cac_tep_tam(self):
        rel = {p.relative_to(GOC).as_posix() for p in self.teps}
        self.assertGreater(len(rel), 20, "bao đóng quá nhỏ — cách tính hỏng")
        for x in ("scripts/control_center/desktop.py",
                  "scripts/control_center/desktop_shell.py",
                  "scripts/control_center/ghi_utf8.py",
                  "scripts/control_center/webapi.py",
                  "scripts/control_center/store.py",
                  "scripts/control_center/attachments.py",
                  "scripts/router_v4/scheduler.py"):
            self.assertIn(x, rel)

    def test_khong_mo_tep_van_ban_nao_thieu_encoding(self):
        loi = []
        for f in self.teps:
            src = f.read_text(encoding="utf-8")
            dong = src.splitlines()
            rel = f.relative_to(GOC).as_posix()
            for n in ast.walk(ast.parse(src)):
                if not isinstance(n, ast.Call):
                    continue
                if isinstance(n.func, ast.Attribute):
                    ten = n.func.attr
                    chu = n.func.value
                    if ten == "open" and isinstance(chu, ast.Name) \
                            and chu.id in OPEN_KHONG_PHAI_TEP:
                        continue           # `os.open` (fd), `webbrowser.open`
                elif isinstance(n.func, ast.Name):
                    ten = n.func.id
                else:
                    continue
                if ten not in ("open", "read_text", "write_text"):
                    continue
                if self._kw(n, "encoding") is not None:
                    continue
                if ten == "open":
                    mode = ""
                    if len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
                        mode = str(n.args[1].value)
                    km = self._kw(n, "mode")
                    if km is not None and isinstance(km.value, ast.Constant):
                        mode = str(km.value.value)
                    if "b" in mode:        # nhị phân: không qua codec nào
                        continue
                loi.append(f"{rel}:{n.lineno}  {self._dong(dong, n)}")
        self.assertEqual(loi, [], "thiếu `encoding=` tường minh — codec do "
                                  "LOCALE quyết định:\n" + "\n".join(loi))

    def test_khong_subprocess_nao_giai_ma_bang_locale(self):
        loi = []
        for f in self.teps:
            src = f.read_text(encoding="utf-8")
            dong = src.splitlines()
            rel = f.relative_to(GOC).as_posix()
            for n in ast.walk(ast.parse(src)):
                if not isinstance(n, ast.Call):
                    continue
                ten = (n.func.attr if isinstance(n.func, ast.Attribute)
                       else getattr(n.func, "id", ""))
                if ten not in ("run", "Popen", "check_output", "call",
                               "check_call"):
                    continue
                if (self._kw(n, "text") or self._kw(n, "universal_newlines")) \
                        and self._kw(n, "encoding") is None:
                    loi.append(f"{rel}:{n.lineno}  {self._dong(dong, n)}")
        self.assertEqual(loi, [],
                         "`text=True` không kèm `encoding=` GIẢI MÃ đầu ra "
                         "bằng codec của locale:\n" + "\n".join(loi))

    def test_json_dumps_ghi_ra_ngoai_phai_ensure_ascii_false(self):
        loi = []
        for f in self.teps:
            src = f.read_text(encoding="utf-8")
            dong = src.splitlines()
            rel = f.relative_to(GOC).as_posix()
            for n in ast.walk(ast.parse(src)):
                if not (isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Attribute)
                        and n.func.attr in ("dump", "dumps")
                        and isinstance(n.func.value, ast.Name)
                        and n.func.value.id == "json"):
                    continue
                if self._kw(n, "ensure_ascii") is not None:
                    continue
                d = self._dong(dong, n)
                if (rel, d) in JSON_MIEN_TRU:
                    continue
                loi.append(f"{rel}:{n.lineno}  {d}")
        self.assertEqual(loi, [],
                         "`json.dumps` thiếu `ensure_ascii=False` và không "
                         "có miễn trừ đã soi:\n" + "\n".join(loi))

    def test_moi_mien_tru_json_van_con_dung_cho(self):
        """Miễn trừ mồ côi là miễn trừ đã hết đúng. Bắt nó ngay."""
        con = set()
        for f in self.teps:
            rel = f.relative_to(GOC).as_posix()
            for d in f.read_text(encoding="utf-8").splitlines():
                con.add((rel, d.strip()))
        for k in JSON_MIEN_TRU:
            self.assertIn(k, con, f"miễn trừ mồ côi: {k} — dòng mã đã đổi "
                                  f"hoặc biến mất; soi lại rồi cập nhật")

    def test_vo_khoi_dong_khong_dung_cach_bi_cam(self):
        """Yêu cầu số 2: không chcp, không PYTHONUTF8, không errors=."""
        for rel in VO_KHOI_DONG:
            than = _than_ma(rel)
            for x in CACH_BI_CAM:
                self.assertNotIn(x, than, f"{rel} dùng cách bị cấm {x!r}")

    def test_vo_khoi_dong_khong_ghi_truc_tiep_ra_luong_van_ban(self):
        loi = []
        for rel in VO_KHOI_DONG:
            src = (GOC / rel).read_text(encoding="utf-8")
            for n in ast.walk(ast.parse(src)):
                if not isinstance(n, ast.Call):
                    continue
                if isinstance(n.func, ast.Name) and n.func.id == "print":
                    loi.append(f"{rel}:{n.lineno} print()")
                if isinstance(n.func, ast.Attribute) \
                        and n.func.attr in ("write", "reconfigure") \
                        and isinstance(n.func.value, ast.Attribute) \
                        and isinstance(n.func.value.value, ast.Name) \
                        and n.func.value.value.id == "sys":
                    loi.append(f"{rel}:{n.lineno} "
                               f"sys.{n.func.value.attr}.{n.func.attr}()")
        self.assertEqual(loi, [], "ghi thẳng ra tầng VĂN BẢN của luồng — "
                                  "codec do locale quyết định:\n"
                                  + "\n".join(loi))


# --------------------------------------------------------------------------
# Tiến trình con: thông dịch thật, tầng văn bản cp1252 thật.
#
# Kịch bản con là ASCII THUẦN. Tiếng Việt đi vào nó qua `json.dumps` (mặc
# định `ensure_ascii=True`, tức escape `\\uXXXX`) — đúng công dụng của cờ
# ấy, và nhờ vậy không có câu hỏi nào về encoding của chính TỆP MÃ NGUỒN
# con. Thứ duy nhất đang được kiểm là LUỒNG RA.
# --------------------------------------------------------------------------
def _kich_ban(*than: str) -> str:
    dau = [
        "import json, sys",
        "CAU = json.loads(%r)" % json.dumps(list(CAU)),
        'enc = (getattr(sys.stdout, "encoding", "") or "").lower()',
        'sys.stderr.write("ENC=%s\\n" % enc)',
        # Tự kiểm khung: nếu luồng con KHÔNG hẹp thì cả bài kiểm vô nghĩa,
        # và mã 9 nói đúng điều đó thay vì báo "đạt".
        'if "utf" in enc:',
        '    sys.stderr.write("KHUNG-HONG: luong con khong bi han che\\n")',
        "    raise SystemExit(9)",
        "try:",
        "    CAU[0].encode(enc)",
        "except UnicodeEncodeError:",
        "    pass",
        "else:",
        '    sys.stderr.write("KHUNG-HONG: codec %s ma hoa duoc\\n" % enc)',
        "    raise SystemExit(9)",
    ]
    ma = "\n".join(dau + list(than)) + "\n"
    ma.encode("ascii")                     # bất biến: kịch bản con là ASCII
    return ma


KB_PRINT = _kich_ban(
    "# Ma CU: giao chuoi cho tang van ban -> codec cua locale -> no.",
    "for s in CAU:",
    "    print(s)")

KB_GHI = _kich_ban(
    "from scripts.control_center.ghi_utf8 import GhiUTF8",
    "ghi = GhiUTF8()",
    "for s in CAU:",
    "    ghi(s)")


class TestTienTrinhConCp1252(unittest.TestCase):
    """Gần nhất với "bấm đôi EXE" mà `unittest` làm được.

    Mọi thứ trong tiến trình con là thật — chỉ locale bị cưỡng chế hẹp.
    """

    @staticmethod
    def _moi_truong():
        e = dict(os.environ)
        for k in ("PYTHONUTF8", "PYTHONLEGACYWINDOWSSTDIO",
                  "PYTHONWARNDEFAULTENCODING"):
            e.pop(k, None)
        # LÀM HẸP, không phải để sửa: bắt tầng văn bản của con là cp1252
        # nghiêm ngặt trên MỌI máy, kể cả CI Linux mặc định UTF-8.
        e["PYTHONIOENCODING"] = "cp1252:strict"
        e["PYTHONPATH"] = str(GOC)
        return e

    def _chay(self, argv):
        return subprocess.run([sys.executable, "-X", "utf8=0"] + argv,
                              cwd=str(GOC), env=self._moi_truong(),
                              capture_output=True, timeout=180)

    def _chay_kich_ban(self, ma: str):
        p = Path(tempfile.mkdtemp(prefix="cc-kb-")) / "kb.py"
        p.write_text(ma, encoding="ascii")
        return self._chay([str(p)])

    def _khong_hong(self, r):
        self.assertNotEqual(r.returncode, 9,
                            "khung kiểm không hẹp được: "
                            + r.stderr.decode("utf-8", "replace"))

    def test_khung_kiem_that_su_han_che_duoc(self):
        """Chứng cứ chống rỗng: mã CŨ phải VẪN chết trong khung này."""
        r = self._chay_kich_ban(KB_PRINT)
        self._khong_hong(r)
        self.assertNotEqual(r.returncode, 0, "print() lẽ ra phải chết")
        self.assertIn(b"UnicodeEncodeError", r.stderr)
        self.assertIn(b"cp1252", r.stderr)

    def test_ghi_utf8_song_trong_dung_khung_do(self):
        r = self._chay_kich_ban(KB_GHI)
        self._khong_hong(r)
        self.assertEqual(r.returncode, 0,
                         r.stderr.decode("utf-8", "replace"))
        self.assertEqual(r.stdout.decode("utf-8").splitlines(), list(CAU))

    def test_desktop_check_khong_no_tren_cp1252(self):
        """`-m scripts.control_center.desktop --check` in tiếng Việt.

        Nhận cả 0 (đủ gói) và 2 (thiếu gói): cả hai đường đều in tiếng
        Việt, và điều đang kiểm là NÓ KHÔNG NÉM UnicodeEncodeError.
        """
        r = self._chay(["-m", "scripts.control_center.desktop", "--check"])
        self.assertNotIn(b"UnicodeEncodeError", r.stderr)
        self.assertIn(r.returncode, (0, 2),
                      r.stderr.decode("utf-8", "replace"))
        ra = r.stdout.decode("utf-8")      # nghiêm ngặt: phải là UTF-8 hợp lệ
        if r.returncode == 0:
            self.assertIn("phụ thuộc desktop: đủ", ra)
        else:
            self.assertIn("Thiếu gói", ra)

    def test_help_khong_no_tren_cp1252(self):
        """Chỗ THỨ HAI của đúng một sự cố — `argparse._print_message`.

        Sau khi `print()` đã được sửa, EXE đã đóng gói VẪN chết ở `--help`:
        mọi chuỗi `help=`/`description=` là tiếng Việt và `argparse` ghi
        thẳng ra tầng văn bản của luồng. Ký tự làm vỡ là `ứ` (U+1EE9), từ
        `"… ứng dụng desktop"`.
        """
        for mod in ("scripts.control_center.desktop",
                    "scripts.control_center.webmain"):
            with self.subTest(mod=mod):
                r = self._chay(["-m", mod, "--help"])
                self.assertNotIn(b"UnicodeEncodeError", r.stderr,
                                 f"{mod} --help vẫn nổ")
                self.assertEqual(r.returncode, 0,
                                 r.stderr.decode("utf-8", "replace"))
                ra = r.stdout.decode("utf-8")   # phải là UTF-8 hợp lệ
                self.assertIn("--root", ra)
                # Phần help NÀY phải thật sự chứa ký tự cp1252 không mã hoá
                # được — nếu không, `--help` in ra được chẳng chứng minh gì.
                nguy = sorted({c for c in ra
                               if not _ma_hoa_duoc_cp1252(c)})
                self.assertTrue(nguy, f"{mod}: help không có ký tự ngoài "
                                      f"cp1252 nên bài kiểm rỗng")
                self.assertIn("ư", nguy)
        # Riêng `desktop`: ĐÚNG ký tự trong lần nổ thứ hai, `ứ` (U+1EE9).
        r = self._chay(["-m", "scripts.control_center.desktop", "--help"])
        self.assertIn("ứ", r.stdout.decode("utf-8"))

    def test_co_sai_khong_no_tren_cp1252(self):
        """Nhánh `error()`: usage + thông điệp lỗi, mã thoát 2."""
        r = self._chay(["-m", "scripts.control_center.desktop",
                        "--khong-co-co-nay"])
        self.assertNotIn(b"UnicodeEncodeError", r.stderr)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unrecognized arguments",
                      r.stderr.decode("utf-8") + r.stdout.decode("utf-8"))

    def test_webmain_check_khong_no_tren_cp1252(self):
        r = self._chay(["-m", "scripts.control_center.webmain", "--check"])
        self.assertNotIn(b"UnicodeEncodeError", r.stderr)
        self.assertIn(r.returncode, (0, 2),
                      r.stderr.decode("utf-8", "replace"))
        ra = r.stdout.decode("utf-8")
        self.assertTrue("phụ thuộc giao diện web: đủ" in ra
                        or "Thiếu gói" in ra, repr(ra[:200]))

    def test_ca_ba_nhanh_quyet_dinh_in_duoc_ly_do_tieng_viet(self):
        """Cả `tu_chay` lẫn `nhuong` đều `ghi(...{ly_do})` với chữ `ư`."""
        d = Path(tempfile.mkdtemp(prefix="cc-qd-"))
        r = self._chay_kich_ban(_kich_ban(
            "from pathlib import Path",
            "from scripts.control_center.desktop_shell import quyet_dinh",
            "from scripts.control_center.ghi_utf8 import GhiUTF8",
            "ghi = GhiUTF8()",
            "for khac in (False, True):",
            "    kh = quyet_dinh(Path(%r), co_thuc_the_khac=khac," % str(d),
            "                    cong_muon=0)",
            '    ghi("[desktop] %s" % kh.ly_do)'))
        self._khong_hong(r)
        self.assertEqual(r.returncode, 0,
                         r.stderr.decode("utf-8", "replace"))
        ra = r.stdout.decode("utf-8")
        self.assertIn(U01B0, ra, "lẽ ra phải in được chữ 'ư'")
        self.assertEqual(len(ra.strip().splitlines()), 2)


class TestTrangThaiTiengViet(unittest.TestCase):
    """Yêu cầu số 7 — tiếng Việt qua MỌI lớp lưu trữ, nguyên vẹn từng byte."""

    def setUp(self):
        # Thư mục gốc CÓ TIẾNG VIỆT trong tên: chỗ nào dựng đường dẫn bằng
        # codec của locale sẽ vỡ ngay tại đây.
        self.goc = (Path(tempfile.mkdtemp(prefix="cc-vn-"))
                    / "Đường dẫn thử nghiệm")
        self.goc.mkdir(parents=True)
        from scripts.control_center.store import ControlStore
        self.st = ControlStore(root=self.goc)
        self.addCleanup(self.st.close)

    def _du_an(self, pid="p", ten="Hàng đợi sản xuất"):
        from scripts.control_center.model import Project
        return self.st.luu_project(Project(project_id=pid, name=ten,
                                           repo_path=str(self.goc)))

    def test_ten_du_an_tieng_viet_nguyen_ven(self):
        for i, ten in enumerate(CAU):
            self._du_an(f"p{i}", ten)
        for i, ten in enumerate(CAU):
            doc = self.st.project(f"p{i}").name
            self.assertEqual(doc, ten)
            self.assertEqual(doc.encode("utf-8"), ten.encode("utf-8"))

    def test_chat_tieng_viet_nguyen_ven_ke_ca_nhieu_dong(self):
        self._du_an()
        van = ("Đường dẫn thử nghiệm\nHàng đợi sản xuất\nNgười dùng\n"
               + " ".join(KY_TU))
        self.st.them_chat("p", "user", van)
        doc = self.st.chat("p")[-1].text
        self.assertEqual(doc, van)
        self.assertEqual(doc.encode("utf-8"), van.encode("utf-8"))
        for c in KY_TU:
            self.assertIn(c, doc)

    def test_ten_tep_dinh_kem_tieng_viet_nguyen_ven_va_hash_khop(self):
        import hashlib
        from scripts.control_center.attachments import KhoDinhKem
        self._du_an(ten="Người dùng")
        kho = KhoDinhKem(self.st, goc=self.goc)
        noi_dung = "cột1,cột2\nĐường,dẫn\n".encode("utf-8")
        dk = kho.them_tu_bytes("p", noi_dung, "Đường dẫn thử nghiệm.csv")
        self.assertEqual(dk.filename, "Đường dẫn thử nghiệm.csv")
        self.assertEqual(dk.sha256, hashlib.sha256(noi_dung).hexdigest())
        self.assertEqual(dk.size_bytes, len(noi_dung))
        self.assertEqual(kho.duong_dan(dk.attachment_id).read_bytes(),
                         noi_dung)
        self.assertEqual(self.st.dinh_kem_cua_project("p")[0].filename,
                         "Đường dẫn thử nghiệm.csv")

    def test_lam_sach_ten_khong_phien_am_tieng_viet(self):
        """Yêu cầu số 5: giữ nguyên, KHÔNG bỏ dấu, KHÔNG phiên âm."""
        from scripts.control_center.attachments import lam_sach_ten
        for ten in ("Đường dẫn thử nghiệm.pdf", "Hàng đợi sản xuất.csv",
                    "Người dùng.txt", " ".join(KY_TU) + ".md"):
            self.assertEqual(lam_sach_ten(ten), ten)
        # ...nhưng vẫn phải chặn thoát thư mục.
        self.assertEqual(lam_sach_ten("../../Đường dẫn.pdf"),
                         "Đường dẫn.pdf")

    def test_tep_khoa_vo_desktop_la_utf8_va_di_vong_duoc(self):
        from scripts.control_center.desktop_shell import (
            ThongTinPhien, doc_tep_khoa, duong_tep_khoa, ghi_tep_khoa)
        tt = ThongTinPhien(pid=os.getpid(), cong=54321, token="Abc-123_x",
                           bat_dau_luc=1.5)
        ghi_tep_khoa(self.goc, tt)
        tho = duong_tep_khoa(self.goc).read_bytes()
        self.assertEqual(json.loads(tho.decode("utf-8"))["cong"], 54321)
        lai = doc_tep_khoa(self.goc)
        self.assertEqual((lai.cong, lai.token), (54321, "Abc-123_x"))

    def test_nhat_ky_desktop_nam_duoi_goc_co_tieng_viet(self):
        tep = duong_nhat_ky(self.goc)
        GhiUTF8(tep, ra_luong=False)(LY_DO_GAY_CHET)
        self.assertEqual(tep.read_text(encoding="utf-8"),
                         LY_DO_GAY_CHET + "\n")
        self.assertIn("Đường dẫn thử nghiệm", str(tep))

    def test_anh_chup_snapshot_giu_tieng_viet_qua_json(self):
        """IPC: đúng thứ frontend nhận. `ensure_ascii=False` + UTF-8."""
        self._du_an(ten="Hàng đợi sản xuất")
        self.st.them_chat("p", "user", "Đường dẫn thử nghiệm")
        d = {"projects": [{"name": p.name} for p in self.st.projects()],
             "chat": [m.text for m in self.st.chat("p")]}
        tho = json.dumps(d, ensure_ascii=False).encode("utf-8")
        lai = json.loads(tho.decode("utf-8"))
        self.assertEqual(lai["projects"][0]["name"], "Hàng đợi sản xuất")
        self.assertEqual(lai["chat"][-1], "Đường dẫn thử nghiệm")


class TestBoNghiemThuKhongTiemLoiThoat(unittest.TestCase):
    """Bài kiểm về BỘ KIỂM: nó không được tự tiêm lối thoát encoding.

    Đây đúng là lỗi đã để sự cố lọt: bộ nghiệm thu EXE tiêm `PYTHONUTF8=1`
    và `PYTHONIOENCODING=utf-8` vào tiến trình con, nên nó đo một môi
    trường không người dùng nào có, và báo 19/19 xanh.
    """

    #: Đặt bằng ba hình dạng này là ĐẶT. Quét bằng AST chứ không bằng tìm
    #: chuỗi: bộ nghiệm thu giờ có một vòng `pop()` để GỠ đúng các biến ấy,
    #: và phép tìm chuỗi sẽ tưởng dòng gỡ đó là dòng đặt.
    BIEN_CAM = ("PYTHONUTF8", "PYTHONIOENCODING", "PYTHONLEGACYWINDOWSSTDIO")

    def _cho_dat_bien(self, rel: str):
        cay = ast.parse((GOC / rel).read_text(encoding="utf-8"))
        ra = []
        for n in ast.walk(cay):
            # `dict(os.environ, PYTHONUTF8="1")`
            if isinstance(n, ast.Call):
                for k in n.keywords:
                    if k.arg in self.BIEN_CAM:
                        ra.append(f"{rel}:{n.lineno} tham số {k.arg}=")
            # `{"PYTHONUTF8": "1"}`
            elif isinstance(n, ast.Dict):
                for k in n.keys:
                    if isinstance(k, ast.Constant) and k.value in self.BIEN_CAM:
                        ra.append(f"{rel}:{n.lineno} khoá {k.value!r}")
            # `moi["PYTHONUTF8"] = "1"`
            elif isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Subscript) \
                            and isinstance(t.slice, ast.Constant) \
                            and t.slice.value in self.BIEN_CAM:
                        ra.append(f"{rel}:{n.lineno} gán [{t.slice.value!r}]")
        return ra

    def test_bo_nghiem_thu_exe_khong_tiem_bien_encoding(self):
        rel = "scripts/control_center_desktop_acceptance.py"
        if not (GOC / rel).is_file():      # pragma: no cover
            self.skipTest("chưa có bộ nghiệm thu")
        self.assertEqual(
            self._cho_dat_bien(rel), [],
            "bộ nghiệm thu tiêm biến encoding vào tiến trình con — đó chính "
            "là cách sự cố cp1252 lọt qua 19/19 bài kiểm")

    def test_phep_quet_ay_khong_rong(self):
        """Chứng cứ chống rỗng: cả ba hình dạng phải bị bắt."""
        p = Path(tempfile.mkdtemp(prefix="cc-quet-")) / "gia.py"
        p.write_text('moi = dict(os.environ, PYTHONUTF8="1")\n'
                     'khac = {"PYTHONIOENCODING": "utf-8"}\n'
                     'moi["PYTHONLEGACYWINDOWSSTDIO"] = "1"\n',
                     encoding="utf-8")
        cay = ast.parse(p.read_text(encoding="utf-8"))
        self.assertEqual(len(cay.body), 3)
        # Dùng lại đúng phép quét, chỉ đổi gốc.
        goc_cu = globals()["GOC"]
        globals()["GOC"] = p.parent
        try:
            bat = self._cho_dat_bien("gia.py")
        finally:
            globals()["GOC"] = goc_cu
        self.assertEqual(len(bat), 3, bat)


if __name__ == "__main__":
    unittest.main(verbosity=2)
