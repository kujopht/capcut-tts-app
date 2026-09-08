"""Bốn bất biến an toàn của kho đính kèm — CI cưỡng chế.

Tệp này ở `scripts/tests` chứ không ở `tests/` là có chủ đích: tầng đính
kèm không import Qt, nên CI (`unittest discover -s scripts/tests`) chạy
được nó trên Linux, trong môi trường sạch, mỗi PR. Bộ kiểm giao diện chỉ
chạy cục bộ; một ranh giới an toàn không nên phụ thuộc vào việc tôi có nhớ
chạy bộ kiểm cục bộ hay không.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.attachments import (  # noqa: E402
    DinhKem, DinhKemLoi, KhoDinhKem, lam_sach_ten, loai_cua, ma_dinh_kem)
from scripts.control_center.store import ControlStore  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
PDF = (b"%PDF-1.7\n" + b"x" * 64)


class _Nen(unittest.TestCase):
    def setUp(self):
        self.goc = Path(tempfile.mkdtemp(prefix="cc-att-"))
        self.store = ControlStore(root=self.goc)
        self.kho = KhoDinhKem(self.store, goc=self.goc)

    def tearDown(self):
        try:
            self.store.close()
        except Exception:                                   # noqa: BLE001
            pass
        shutil.rmtree(self.goc, ignore_errors=True)

    def _tep(self, ten: str, noi_dung: bytes) -> Path:
        p = self.goc / "nguon" / ten
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(noi_dung)
        return p


class TestLamSachTen(_Nen):
    """Tên tệp: không được mang theo đường dẫn, và Windows có bẫy riêng."""

    def test_bo_moi_thanh_phan_thu_muc(self):
        for xau in (r"..\..\..\Windows\System32\evil.png",
                    "../../etc/passwd.txt",
                    r"C:\Users\nguye\.ssh\id_rsa.txt",
                    "/etc/shadow.txt",
                    r"a\b/c\d.png"):
            with self.subTest(ten=xau):
                sach = lam_sach_ten(xau)
                self.assertNotIn("/", sach)
                self.assertNotIn("\\", sach)
                self.assertNotIn("..", sach)

    def test_bo_ky_tu_dieu_khien_va_ky_tu_Windows_cam(self):
        sach = lam_sach_ten('a\x00b<c>d:e"f|g?h*i.txt')
        for x in '\x00<>:"|?*':
            self.assertNotIn(x, sach)

    def test_ten_DANH_RIENG_cua_Windows_duoc_doi(self):
        """`CON.txt` không mở được trên Windows — phải đổi, không giữ."""
        for xau in ("CON.txt", "con.txt", "PRN.md", "COM1.log", "NUL.json"):
            with self.subTest(ten=xau):
                sach = lam_sach_ten(xau)
                goc = os.path.splitext(sach)[0].lower()
                self.assertNotIn(goc, {"con", "prn", "com1", "nul"})

    def test_dau_cham_va_khoang_trang_hai_dau_bi_cat(self):
        """Windows tự cắt chúng, nên `..` là một đường dẫn nguỵ trang."""
        self.assertNotIn("..", lam_sach_ten(".."))
        self.assertEqual(lam_sach_ten("   "), "khong_ten")
        self.assertEqual(lam_sach_ten(""), "khong_ten")

    def test_cat_do_dai_nhung_GIU_duoi_tep(self):
        sach = lam_sach_ten("x" * 400 + ".png")
        self.assertTrue(sach.endswith(".png"), "cắt tên làm mất đuôi tệp")
        self.assertLess(len(sach), 200)


class TestAllowlistLoaiTep(_Nen):
    """Fail closed: không có trong bảng thì từ chối."""

    def test_cac_loai_YEU_CAU_deu_duoc_phep(self):
        can = ("a.png", "a.jpg", "a.jpeg", "a.webp",          # anh
               "a.pdf", "a.txt", "a.md", "a.docx",            # tai lieu
               "a.csv", "a.json", "a.xlsx",                   # du lieu
               "a.py", "a.ts", "a.sql", "a.toml", "a.log",    # ma/cau hinh
               "a.zip")                                       # nen
        for t in can:
            with self.subTest(tep=t):
                self.assertIsNotNone(loai_cua(t), f"{t} phải được phép")

    def test_loai_thi_hanh_bi_TU_CHOI(self):
        for t in ("a.exe", "a.dll", "a.msi", "a.scr", "a.com", "a.vbs",
                  "a.lnk", "a.reg", "a.jar", "a", "a.", "a.PNG.exe"):
            with self.subTest(tep=t):
                self.assertIsNone(loai_cua(t), f"{t} KHÔNG được phép")

    def test_them_tep_ngoai_allowlist_thi_no_ngoai_le(self):
        p = self._tep("evil.exe", b"MZ" + b"\x00" * 64)
        with self.assertRaises(DinhKemLoi):
            self.kho.them_tu_tep("p", p)


class TestDuoiTepPhaiKhopNoiDung(_Nen):
    """Đổi đuôi tệp là thao tác dễ nhất thế giới."""

    def test_tep_thi_hanh_doi_ten_thanh_png_bi_TU_CHOI(self):
        p = self._tep("anh.png", b"MZ\x90\x00" + b"\x00" * 64)
        with self.assertRaises(DinhKemLoi) as ctx:
            self.kho.them_tu_tep("p", p)
        self.assertIn("không khớp", str(ctx.exception))

    def test_png_that_thi_nhan(self):
        dk = self.kho.them_tu_tep("p", self._tep("anh.png", PNG))
        self.assertEqual(dk.media_type, "image")

    def test_pdf_gia_bi_TU_CHOI_pdf_that_thi_nhan(self):
        with self.assertRaises(DinhKemLoi):
            self.kho.them_tu_tep("p", self._tep("x.pdf", b"not a pdf" * 8))
        self.assertTrue(self.kho.them_tu_tep("p", self._tep("y.pdf", PDF)))

    def test_zip_that_thi_nhan(self):
        z = self.goc / "nguon" / "a.zip"
        z.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("a.txt", "xin chao")
        self.assertEqual(self.kho.them_tu_tep("p", z).media_type, "archive")

    def test_van_ban_KHONG_bi_doi_chu_ky(self):
        """`.txt`/`.py` không có chữ ký — không được vì thế mà từ chối."""
        for ten, noi in (("a.txt", b"chi la van ban"),
                         ("b.py", b"print('xin chao')\n"),
                         ("c.json", b'{"a": 1}'),
                         ("d.csv", b"a,b\n1,2\n")):
            with self.subTest(tep=ten):
                self.assertTrue(
                    self.kho.them_tu_tep("p", self._tep(ten, noi)))


class TestKhongDeDuongDanTuyChenVao(_Nen):
    """Bất biến #2 và #3 — phần quan trọng nhất của tệp này."""

    def test_duong_dan_luu_tru_KHONG_chua_mot_byte_nao_cua_ten_nguoi_dung(self):
        """Nó là `objects/<sha[:2]>/<sha>.<đuôi>`, hết.

        Nên `../../` trong tên tệp không có chỗ nào để chen vào.
        """
        p = self._tep("bao cao QUAN TRONG.pdf", PDF)
        dk = self.kho.them_tu_tep("p", p)
        self.assertEqual(dk.rel_path,
                         f"objects/{dk.sha256[:2]}/{dk.sha256}.pdf")
        self.assertNotIn("bao", dk.rel_path)
        self.assertNotIn("QUAN", dk.rel_path)

    def test_ten_co_duong_dan_van_luu_duoc_va_KHONG_thoat_ra(self):
        p = self._tep("hop_le.png", PNG)
        dk = self.kho.them_tu_tep(
            "p", p, ten_hien=r"..\..\..\Windows\System32\drivers\etc\hosts.png")
        that = self.kho.duong_dan(dk.attachment_id)
        self.assertTrue(str(that).startswith(str(self.kho.thu_muc)))
        self.assertNotIn("System32", str(that))

    def test_ban_ghi_bi_SUA_TAY_de_tro_ra_ngoai_thi_bi_TU_CHOI(self):
        """Đây là mô hình đối thủ đúng: kẻ tấn công ghi được vào sổ.

        Nếu ai đó sửa `rel_path` thành `../../../...` thì `duong_dan()`
        phải TỪ CHỐI, chứ không đọc tệp đó. Kiểm bằng chuỗi thì lọt; phải
        so sánh sau khi RESOLVE.
        """
        dk = self.kho.them_tu_tep("p", self._tep("a.png", PNG))
        self.store._c().execute(
            "UPDATE attachments SET rel_path=? WHERE attachment_id=?",
            ("../../../../../../Windows/System32/config/SAM",
             dk.attachment_id))
        with self.assertRaises(DinhKemLoi) as ctx:
            self.kho.duong_dan(dk.attachment_id)
        self.assertIn("ngoài kho", str(ctx.exception))

    def test_duong_dan_cua_ma_khong_ton_tai_thi_no_ngoai_le(self):
        with self.assertRaises(DinhKemLoi):
            self.kho.duong_dan("att_khong_co_that")

    def test_so_luu_duong_dan_TUONG_DOI_khong_phai_tuyet_doi(self):
        """Đường dẫn tuyệt đối làm sổ vỡ khi thư mục gốc bị đổi chỗ, và
        nó rò cây thư mục của máy người dùng vào mọi bản xuất."""
        dk = self.kho.them_tu_tep("p", self._tep("a.png", PNG))
        h = self.store._c().execute(
            "SELECT rel_path FROM attachments WHERE attachment_id=?",
            (dk.attachment_id,)).fetchone()
        self.assertFalse(Path(h["rel_path"]).is_absolute())
        self.assertNotIn(str(self.goc), h["rel_path"])


class TestNhiPhanKhongVaoSQLite(_Nen):
    """Bất biến #1."""

    def test_khong_cot_nao_giu_byte_cua_tep(self):
        dk = self.kho.them_tu_tep("p", self._tep("a.png", PNG))
        h = self.store._c().execute(
            "SELECT * FROM attachments WHERE attachment_id=?",
            (dk.attachment_id,)).fetchone()
        for k in h.keys():
            with self.subTest(cot=k):
                self.assertNotIsInstance(h[k], (bytes, bytearray),
                                         f"cột {k} giữ nhị phân")

    def test_byte_nam_tren_dia_va_bam_KHOP(self):
        goc_byte = PNG
        dk = self.kho.them_tu_tep("p", self._tep("a.png", goc_byte))
        p = self.kho.duong_dan(dk.attachment_id)
        self.assertEqual(p.read_bytes(), goc_byte)
        self.assertEqual(dk.sha256, hashlib.sha256(goc_byte).hexdigest())
        self.assertEqual(dk.size_bytes, len(goc_byte))
        self.assertTrue(self.kho.kiem_toan_ven(dk.attachment_id))

    def test_so_KHONG_phinh_len_theo_kich_co_tep(self):
        """Sổ phải gần như không đổi kích cỡ khi thêm một tệp lớn."""
        db = self.goc / ".router" / "control_center" / "control.db"
        truoc = db.stat().st_size
        self.kho.them_tu_tep("p", self._tep("to.txt", b"x" * (4 * 1024 * 1024)))
        sau = db.stat().st_size
        self.assertLess(sau - truoc, 200 * 1024,
                        "sổ phình lên — nhị phân đã lọt vào SQLite")


class TestPhamViVaQuyenAgent(_Nen):
    """Bất biến #4."""

    def test_cho_agent_CHI_tra_dinh_kem_cua_dung_viec_do(self):
        a = self.kho.them_tu_tep("p", self._tep("a.png", PNG), message_id=1)
        b = self.kho.them_tu_tep("p", self._tep("b.pdf", PDF), message_id=2)
        self.kho.gan_cho_task(a.attachment_id, "p.t1")
        self.kho.gan_cho_task(b.attachment_id, "p.t2")
        self.assertEqual([x.filename for x in self.kho.cho_agent("p.t1")],
                         ["a.png"])
        self.assertEqual([x.filename for x in self.kho.cho_agent("p.t2")],
                         ["b.pdf"])

    def test_dinh_kem_CHUA_duoc_gan_thi_KHONG_agent_nao_thay(self):
        """Mặc định là không cấp. Một tin nhắn có ảnh không tự cho mọi
        việc trong dự án đọc ảnh đó."""
        self.kho.them_tu_tep("p", self._tep("a.png", PNG), message_id=1)
        self.assertEqual(self.kho.cho_agent("p.t1"), [])
        self.assertEqual(self.kho.cho_agent(""), [])

    def test_cung_du_an_KHONG_du_de_duoc_doc(self):
        a = self.kho.them_tu_tep("p", self._tep("a.png", PNG), message_id=1)
        self.kho.gan_cho_task(a.attachment_id, "p.t1")
        self.assertEqual(self.kho.cho_agent("p.t9"), [],
                         "cùng dự án là phạm vi quá rộng để làm quyền")

    def test_mo_ta_cho_agent_rong_khi_khong_duoc_cap(self):
        self.assertEqual(self.kho.mo_ta_cho_agent("p.t1"), "")

    def test_mo_ta_cho_agent_co_duong_dan_CUC_BO(self):
        a = self.kho.them_tu_tep("p", self._tep("a.png", PNG), message_id=1)
        self.kho.gan_cho_task(a.attachment_id, "p.t1")
        mo = self.kho.mo_ta_cho_agent("p.t1")
        self.assertIn("a.png", mo)
        self.assertIn(str(self.kho.thu_muc), mo)
        for x in ("http://", "https://", "upload"):
            with self.subTest(x=x):
                self.assertNotIn(x, mo.lower())


class TestMaTatDinhVaTrungLap(_Nen):
    def test_ma_TAT_DINH_theo_pham_vi_va_noi_dung(self):
        self.assertEqual(ma_dinh_kem("p", 1, "", "abc", "a.png"),
                         ma_dinh_kem("p", 1, "", "abc", "a.png"))
        self.assertNotEqual(ma_dinh_kem("p", 1, "", "abc", "a.png"),
                            ma_dinh_kem("q", 1, "", "abc", "a.png"))
        self.assertNotEqual(ma_dinh_kem("p", 1, "", "abc", "a.png"),
                            ma_dinh_kem("p", 2, "", "abc", "a.png"))

    def test_dan_LAI_dung_anh_do_vao_dung_tin_do_khong_sinh_hai_ban_ghi(self):
        a = self.kho.them_tu_bytes("p", PNG, "dan.png", message_id=7)
        b = self.kho.them_tu_bytes("p", PNG, "dan.png", message_id=7)
        self.assertEqual(a.attachment_id, b.attachment_id)
        self.assertEqual(len(self.kho.cua_message("p", 7)), 1)

    def test_cung_noi_dung_hai_du_an_thi_CHUNG_blob_nhung_HAI_ban_ghi(self):
        a = self.kho.them_tu_bytes("p", PNG, "a.png", message_id=1)
        b = self.kho.them_tu_bytes("q", PNG, "a.png", message_id=1)
        self.assertNotEqual(a.attachment_id, b.attachment_id)
        self.assertEqual(a.rel_path, b.rel_path, "phải dùng chung blob")

    def test_xoa_mot_ban_ghi_KHONG_lam_hong_ban_ghi_kia(self):
        a = self.kho.them_tu_bytes("p", PNG, "a.png", message_id=1)
        b = self.kho.them_tu_bytes("q", PNG, "a.png", message_id=1)
        self.assertTrue(self.kho.xoa(a.attachment_id))
        self.assertTrue(self.kho.duong_dan(b.attachment_id).is_file(),
                        "xoá tin nhắn này đã xoá byte của tin nhắn kia")

    def test_xoa_ban_ghi_CUOI_thi_don_luon_blob(self):
        a = self.kho.them_tu_bytes("p", PNG, "a.png", message_id=1)
        p = self.kho.duong_dan(a.attachment_id)
        self.assertTrue(self.kho.xoa(a.attachment_id))
        self.assertFalse(p.exists(), "blob mồ côi còn nằm lại trên đĩa")


class TestTranVaDongChay(_Nen):
    def test_vuot_tran_thi_TU_CHOI(self):
        kho = KhoDinhKem(self.store, goc=self.goc, tran_moi_tep=4096)
        p = self._tep("to.txt", b"x" * 9000)
        with self.assertRaises(DinhKemLoi) as ctx:
            kho.them_tu_tep("p", p)
        self.assertIn("vượt trần", str(ctx.exception))

    def test_tep_bi_tu_choi_KHONG_de_lai_rac_trong_kho(self):
        kho = KhoDinhKem(self.store, goc=self.goc, tran_moi_tep=4096)
        try:
            kho.them_tu_tep("p", self._tep("to.txt", b"x" * 9000))
        except DinhKemLoi:
            pass
        con = list(kho.tam.glob("*"))
        self.assertEqual(con, [], f"còn tệp tạm: {con}")

    def test_tep_rong_bi_TU_CHOI(self):
        with self.assertRaises(DinhKemLoi):
            self.kho.them_tu_tep("p", self._tep("rong.txt", b""))

    def test_thu_muc_KHONG_phai_tep_thi_bi_tu_choi(self):
        d = self.goc / "mot_thu_muc.txt"
        d.mkdir()
        with self.assertRaises(DinhKemLoi):
            self.kho.them_tu_tep("p", d)

    def test_KHONG_nap_het_tep_vao_RAM(self):
        """Đọc theo khối 1 MiB — kiểm bằng cách đếm lần gọi `read`.

        Một tệp 5 MiB phải được đọc thành nhiều lượt. Nếu ai đó đổi sang
        `f.read()` một lần, số lượt về 1 và bài kiểm này hỏng — đúng lúc
        cần hỏng, vì `f.read()` trên một tệp 2 GB sẽ giết tiến trình.
        """
        import io
        goc_byte = b"y" * (5 * 1024 * 1024 + 7)
        dem = {"n": 0}
        that = io.BytesIO(goc_byte)

        class DemRead(io.RawIOBase):
            def readable(self):
                return True

            def read(self, n=-1):
                dem["n"] += 1
                return that.read(n)

        dk = self.kho.them_tu_bytes("p", goc_byte, "to.txt", message_id=1)
        self.assertEqual(dk.size_bytes, len(goc_byte))
        # Duong `them_tu_bytes` boc bang BytesIO nen dem qua wrapper rieng:
        self.kho._nhan_dong("p", DemRead(), "to2.txt", "log",
                            message_id=1, task_id="", owner="")
        self.assertGreater(dem["n"], 4,
                           "đọc một lượt duy nhất — không phải streaming")


class TestKhongTuTaiLenDau(_Nen):
    """Lời hứa với người dùng, kiểm trên CÂY CÚ PHÁP.

    Grep văn bản sẽ báo động vì chính docstring của module nói về việc
    "không tải lên" — cùng bài học đã gặp ở `cc_agent_tool`.
    """

    def test_module_dinh_kem_KHONG_import_thu_vien_mang(self):
        import ast
        ma = (GOC / "scripts" / "control_center" / "attachments.py").read_text(
            encoding="utf-8")
        cay = ast.parse(ma)
        cam = {"requests", "urllib", "urllib3", "http", "httpx", "socket",
               "ftplib", "smtplib", "boto3", "aiohttp"}
        thay = []
        for n in ast.walk(cay):
            if isinstance(n, ast.Import):
                thay += [a.name.split(".")[0] for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module:
                thay.append(n.module.split(".")[0])
        self.assertEqual(sorted(set(thay) & cam), [],
                         "tầng đính kèm đã import một thư viện mạng")


if __name__ == "__main__":
    unittest.main()
