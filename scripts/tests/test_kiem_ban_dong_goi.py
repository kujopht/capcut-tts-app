# -*- coding: utf-8 -*-
"""Kiểm bộ báo cáo đóng gói (`kiem_ban_dong_goi`) và vỏ ký (`ky_ban_dong_goi`).

Không cần chứng chỉ, không cần dist: oracle là chính `python.exe` đang chạy
(Python Software Foundation ký, chuỗi tới CA công cộng) và một tệp tạm.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import kiem_ban_dong_goi as KB          # noqa: E402
from scripts import ky_ban_dong_goi as KY            # noqa: E402

WINDOWS = os.name == "nt"
PYTHON_EXE = Path(sys.executable)


class TestPE(unittest.TestCase):

    def test_python_exe_la_pe_co_thu_muc_security(self):
        pe = KB.pe_thong_tin(PYTHON_EXE)
        self.assertTrue(pe["la_pe"])
        self.assertIn(pe["machine"], ("x64", "x86", "arm64"))
        self.assertGreater(pe["het_section"], 0)
        self.assertEqual(len(pe["bootloader_sha256"]), 64)
        # python.exe cua PSF co chu ky nhung -> security_dir.size > 0.
        self.assertGreater(pe["security_dir"]["size"], 0)
        self.assertFalse(pe["pyinstaller_overlay"])

    def test_tep_khong_phai_pe(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.bin"
            p.write_bytes(b"khong phai PE " * 10)
            pe = KB.pe_thong_tin(p)
            self.assertFalse(pe["la_pe"])
            self.assertIn("MZ", pe["loi"])

    def test_sha256_tep_va_gioi_han(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.bin"
            p.write_bytes(b"abc" * 1000)
            import hashlib
            self.assertEqual(KB.sha256_tep(p), hashlib.sha256(b"abc" * 1000).hexdigest())
            self.assertEqual(KB.sha256_tep(p, den=3), hashlib.sha256(b"abc").hexdigest())


@unittest.skipUnless(WINDOWS, "Zone.Identifier / wintrust chỉ có trên Windows")
class TestMOTWVaChuKy(unittest.TestCase):

    def test_motw_khong_co_va_co(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.exe"
            p.write_bytes(b"MZ")
            self.assertEqual(KB.motw(p), {"co": False, "zone_id": None})
            with open(str(p) + ":Zone.Identifier", "w", encoding="utf-8") as f:
                f.write("[ZoneTransfer]\r\nZoneId=3\r\n")
            mo = KB.motw(p)
            self.assertTrue(mo["co"])
            self.assertEqual(mo["zone_id"], "3")

    def test_python_exe_ky_hop_le_boi_PSF(self):
        ck = KB.chu_ky(PYTHON_EXE)
        self.assertEqual(ck["loai"], "hop_le", ck)
        self.assertIn("Python Software Foundation", ck.get("subject", ""))
        self.assertTrue(ck.get("issuer"))
        self.assertEqual(len(ck.get("sha1", "")), 40)

    def test_tep_khong_ky_ra_khong_ky(self):
        # Sao chep python.exe roi cat bo bang chu ky? Don gian hon: mot PE
        # that nhung khong ky — bootloader PyInstaller neu co san; khong thi
        # dung tep MZ gia (wintrust bao khong ky / khong phai PE).
        ung = sorted(Path(sys.prefix).rglob("PyInstaller/bootloader/Windows-64bit-intel/runw.exe"))
        ung += sorted(Path(os.environ.get("APPDATA", "")).rglob("PyInstaller/bootloader/Windows-64bit-intel/runw.exe")) \
            if os.environ.get("APPDATA") else []
        if not ung:
            self.skipTest("không có bootloader PyInstaller để làm oracle không ký")
        ck = KB.chu_ky(ung[0])
        self.assertEqual(ck["loai"], "khong_ky", ck)
        self.assertEqual(ck["ma"], "0x800B0100")


class TestDuDoanSAC(unittest.TestCase):

    def test_bang_quyet_dinh(self):
        pe = {"pyinstaller_overlay": True}
        self.assertEqual(KB.du_doan_sac({"loai": "khong_ky"}, pe)["muc"], "khong_dam_bao")
        self.assertIn("băm mới", KB.du_doan_sac({"loai": "khong_ky"}, pe)["ly_do"])
        self.assertEqual(KB.du_doan_sac({"loai": "goc_khong_tin"}, pe)["muc"], "chan")
        self.assertIn("kho gốc cục bộ", KB.du_doan_sac({"loai": "goc_khong_tin"}, pe)["ly_do"])
        self.assertEqual(KB.du_doan_sac({"loai": "hop_le", "issuer": "Microsoft ID Verified CS EOC CA 01"}, pe)["muc"], "cao")
        self.assertEqual(KB.du_doan_sac({"loai": "hop_le", "issuer": "DigiCert Trusted G4 Code Signing"}, pe)["muc"], "kha")
        self.assertEqual(KB.du_doan_sac({"loai": "het_han"}, pe)["muc"], "chan")
        self.assertEqual(KB.du_doan_sac({"loai": "khong_kiem_duoc", "mo_ta": "x"}, pe)["muc"], "khong_ro")

    def test_bao_cao_python_exe_dong_du_truong(self):
        kq = KB.kiem_exe(PYTHON_EXE)
        van = KB.dong_bao_cao(kq)
        for tu in ("sha256", "bootloader", "chữ ký", "MOTW", "Smart App Control"):
            self.assertIn(tu, van)
        self.assertEqual(kq["sha256"], KB.sha256_tep(PYTHON_EXE))


class TestVoKy(unittest.TestCase):

    def test_lenh_artifact_signing(self):
        l = KY.lenh_ky("signtool.exe", Path("a.exe"), dlib="d.dll", metadata="m.json")
        self.assertEqual(l[:2], ["signtool.exe", "sign"])
        self.assertIn("/dlib", l)
        self.assertIn("/dmdf", l)
        self.assertIn("/tr", l)
        self.assertIn(KY.TIMESTAMP_MAC_DINH, l)
        self.assertEqual(l[-1], "a.exe")
        self.assertNotIn("/f", l)                    # khong bao gio nhan PFX
        self.assertNotIn("/p", l)

    def test_lenh_thumbprint_va_kiem_dinh_dang(self):
        l = KY.lenh_ky("signtool.exe", Path("a.exe"), thumbprint="AB" * 20)
        self.assertIn("/sha1", l)
        self.assertIn("ab" * 20, l)
        with self.assertRaises(ValueError):
            KY.lenh_ky("signtool.exe", Path("a.exe"), thumbprint="khong-phai-hex")
        with self.assertRaises(ValueError):
            KY.lenh_ky("signtool.exe", Path("a.exe"))                    # khong chon gi
        with self.assertRaises(ValueError):
            KY.lenh_ky("signtool.exe", Path("a.exe"), dlib="d.dll")        # thieu metadata

    def test_khong_co_duong_tu_ky_hay_pfx(self):
        nguon = Path(KY.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"--pfx"', nguon)
        self.assertNotIn("New-SelfSignedCertificate", nguon.replace("KHÔNG có đường \"tự ký\"", ""))
        # Vo ky khong bao gio doc PFX/khoa rieng.
        self.assertNotIn("/p ", nguon)

    def test_dry_run_in_lenh_khong_chay(self):
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "x.exe"
            exe.write_bytes(b"MZ")
            import io
            from contextlib import redirect_stdout
            ra = io.StringIO()
            with redirect_stdout(ra):
                rc = KY.main([str(exe), "--thumbprint", "cd" * 20, "--dry-run", "--signtool", "signtool.exe"])
            self.assertEqual(rc, 0)
            self.assertIn("dry-run", ra.getvalue())
            self.assertIn("/sha1", ra.getvalue())


if __name__ == "__main__":
    unittest.main()
