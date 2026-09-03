"""Mã hoá tệp profile bằng DPAPI — vòng tròn, tương thích ngược, an toàn.

Bài kiểm quan trọng nhất ở đây là `test_tep_thuan_van_doc_duoc`: tương thích
ngược không phải tuỳ chọn. Nếu nó mất, một trạng thái nửa-di-trú làm launcher
mất quyền vào tài khoản, và hoàn tác cũng không cứu được.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from scripts.router_v4 import profile_crypto as PC

#: Blob giong thuc: cung hinh dang JSON launcher luu, nhung gia tri LA GIA.
BLOB_GIA = (b'{"auth_method":"oauth","token":{"access_token":"KHONG-PHAI-'
            b'TOKEN-THAT","refresh_token":"CUNG-KHONG-PHAI","expiry":'
            b'"2026-01-01T00:00:00Z","token_type":"Bearer"}}')


@unittest.skipUnless(PC.kha_dung(), "DPAPI chỉ có trên Windows")
class TestVongTron(unittest.TestCase):
    def test_ma_hoa_roi_giai_ma_ra_dung_byte_ban_dau(self):
        self.assertEqual(PC.giai_ma(PC.ma_hoa(BLOB_GIA)), BLOB_GIA)

    def test_ban_ma_khong_chua_ban_ro(self):
        """Kiểm THẬT: không mảnh nào của bản rõ lọt ra bản mã."""
        ct = PC.ma_hoa(BLOB_GIA)
        self.assertNotIn(b"KHONG-PHAI-TOKEN-THAT", ct)
        self.assertNotIn(b"refresh_token", ct)
        self.assertNotIn(b"auth_method", ct)

    def test_co_magic_header(self):
        self.assertTrue(PC.ma_hoa(BLOB_GIA).startswith(PC.MAGIC))
        self.assertTrue(PC.da_ma_hoa(PC.ma_hoa(BLOB_GIA)))

    def test_hai_lan_ma_hoa_cho_ban_ma_khac_nhau(self):
        """DPAPI thêm ngẫu nhiên; bản mã tất định sẽ để lọt thông tin qua
        việc so sánh hai tệp bằng nhau hay không."""
        self.assertNotEqual(PC.ma_hoa(BLOB_GIA), PC.ma_hoa(BLOB_GIA))

    def test_blob_rong_van_xu_ly_duoc(self):
        self.assertEqual(PC.giai_ma(PC.ma_hoa(b"")), b"")


@unittest.skipUnless(PC.kha_dung(), "DPAPI chỉ có trên Windows")
class TestTuongThichNguoc(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.d = Path(self._d.name)

    def tearDown(self):
        try:
            self._d.cleanup()
        except (OSError, PermissionError):
            pass

    def test_tep_thuan_van_doc_duoc(self):
        """Bài kiểm QUAN TRỌNG NHẤT. Tệp cũ dạng thuần phải đọc y như trước
        — nếu không, nửa-di-trú làm mất quyền vào tài khoản."""
        p = self.d / "acc9.bin"
        p.write_bytes(BLOB_GIA)
        self.assertFalse(PC.da_ma_hoa(p.read_bytes()))
        self.assertEqual(PC.doc_blob(p), BLOB_GIA)

    def test_tep_da_ma_hoa_doc_duoc(self):
        p = self.d / "acc9.bin"
        PC.ghi_blob(p, BLOB_GIA)
        self.assertTrue(PC.da_ma_hoa(p.read_bytes()))
        self.assertEqual(PC.doc_blob(p), BLOB_GIA)

    def test_nua_di_tru_ca_hai_dinh_dang_cung_song(self):
        thuan, ma = self.d / "a.bin", self.d / "b.bin"
        thuan.write_bytes(BLOB_GIA)
        PC.ghi_blob(ma, BLOB_GIA)
        self.assertEqual(PC.doc_blob(thuan), PC.doc_blob(ma))

    def test_ghi_la_NGUYEN_TU(self):
        """Ghi trực tiếp có thể để lại profile cắt nửa = mất tài khoản."""
        p = self.d / "acc9.bin"
        PC.ghi_blob(p, BLOB_GIA)
        cu = p.read_bytes()
        PC.ghi_blob(p, BLOB_GIA + b"x")
        self.assertNotEqual(p.read_bytes(), cu)
        self.assertEqual(PC.doc_blob(p), BLOB_GIA + b"x")
        self.assertFalse(list(self.d.glob("*.tmp")), "còn tệp tạm sót lại")

    def test_trang_thai_khong_tra_ban_ro(self):
        p = self.d / "acc9.bin"
        PC.ghi_blob(p, BLOB_GIA)
        enc, kt = PC.trang_thai(p)
        self.assertTrue(enc)
        self.assertIsInstance(kt, int)


@unittest.skipUnless(PC.kha_dung(), "DPAPI chỉ có trên Windows")
class TestThatBaiRoRang(unittest.TestCase):
    def test_giai_ma_tep_khong_co_header_thi_NEM(self):
        with self.assertRaises(PC.CryptoError):
            PC.giai_ma(BLOB_GIA)

    def test_ban_ma_bi_hong_thi_NEM_chu_khong_tra_rac(self):
        """Một lần giải mã hỏng bị nuốt sẽ thành 'profile trống' rồi 'chưa
        đăng nhập', và người vận hành đi tìm sai chỗ hoàn toàn."""
        ct = bytearray(PC.ma_hoa(BLOB_GIA))
        ct[-1] ^= 0xFF
        with self.assertRaises(PC.CryptoError):
            PC.giai_ma(bytes(ct))

    def test_thieu_entropy_dung_thi_khong_giai_ma_duoc(self):
        """Bản mã gắn với ĐỊNH DẠNG này — một blob DPAPI của ứng dụng khác
        (cùng người dùng) không được tình cờ lọt qua."""
        import ctypes
        from ctypes import wintypes
        goc = PC.ENTROPY
        try:
            PC.ENTROPY = b"entropy-khac-hoan-toan"
            khac = PC.ma_hoa(BLOB_GIA)
        finally:
            PC.ENTROPY = goc
        with self.assertRaises(PC.CryptoError):
            PC.giai_ma(khac)


class TestKhongInBanRo(unittest.TestCase):
    def test_module_khong_print_ban_ro(self):
        t = Path(PC.__file__).read_text(encoding="utf-8", errors="replace")
        for i, dong in enumerate(t.splitlines(), 1):
            l = dong.lstrip()
            if l.startswith("print("):
                self.fail(f"dòng {i}: module mã hoá không được `print` gì")

    def test_script_di_tru_khong_print_ban_ro(self):
        p = Path(PC.__file__).resolve().parents[1] / "migrate_agy_profiles_dpapi.py"
        t = p.read_text(encoding="utf-8", errors="replace")
        import ast
        cay = ast.parse(t)
        for node in ast.walk(cay):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in ("print", "_in")):
                continue
            for arg in node.args:
                for con in ast.walk(arg):
                    if isinstance(con, ast.Name) and con.id in ("plain", "blob",
                                                                "lai"):
                        self.fail(f"dòng {node.lineno}: có thể in bản rõ "
                                  f"({con.id})")


if __name__ == "__main__":
    unittest.main()
