"""
`scripts/validate_nghitts_models.py` — bộ kiểm tra thư mục model.

Mọi trường hợp ở đây đều dựng bằng tệp giả trong thư mục tạm. Không chạm thư
mục model thật, không nạp model thật (mọi test dùng `nap_that=False` trừ nơi
nói rõ), không gọi mạng.

Điều đáng kiểm nhất không phải "model tốt thì báo tốt", mà là **model hỏng theo
từng kiểu khác nhau thì báo đúng kiểu đó** — vì cách sửa mỗi kiểu một khác:
symlink gãy thì tạo lại link, tệp 132 byte thì tải lại, thiếu config thì copy.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]


def nap_script():
    duong = GOC / "scripts" / "validate_nghitts_models.py"
    spec = importlib.util.spec_from_file_location("validate_nghitts_models", duong)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["validate_nghitts_models"] = mod
    spec.loader.exec_module(mod)
    return mod


CONFIG_TOI_THIEU = {"audio": {"sample_rate": 22050}, "phoneme_id_map": {}}


class Nen(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = nap_script()
        self.d = Path(tempfile.mkdtemp())

    def _onnx(self, ten: str, byte: int = 2 * 1024 * 1024) -> Path:
        p = self.d / f"{ten}.onnx"
        p.write_bytes(b"\0" * byte)
        return p

    def _config(self, ten: str, noi_dung=None) -> Path:
        p = self.d / f"{ten}.onnx.json"
        p.write_text(json.dumps(noi_dung if noi_dung is not None else CONFIG_TOI_THIEU),
                     encoding="utf-8")
        return p

    def _soi(self, ten: str):
        return self.mod.soi_mot_model(self.d / f"{ten}.onnx", nap_that=False)


class TimModel(Nen):

    def test_chi_lay_onnx_khong_lay_config(self) -> None:
        """`glob("*.onnx")` khớp cả `x.onnx.json` — phải loại tường minh."""
        self._onnx("a"); self._config("a")
        self._onnx("b"); self._config("b")
        ten = [p.name for p in self.mod.tim_model(self.d)]
        self.assertEqual(ten, ["a.onnx", "b.onnx"])

    def test_thu_muc_khong_ton_tai_tra_rong(self) -> None:
        self.assertEqual(self.mod.tim_model(self.d / "khong-co"), [])


class PhanBietTungKieuHong(Nen):

    def test_cap_day_du_thi_hop_le(self) -> None:
        self._onnx("ok"); self._config("ok")
        r = self._soi("ok")
        self.assertTrue(r["hop_le"], r["loi"])
        self.assertEqual(r["voice_id"], "piper:ok")
        self.assertEqual(r["sample_rate"], 22050)

    def test_onnx_qua_nho_bi_bat(self) -> None:
        """Con trỏ Git LFS chỉ vài trăm byte — nhìn như tệp thật nhưng không phải."""
        self._onnx("lfs", byte=132); self._config("lfs")
        r = self._soi("lfs")
        self.assertFalse(r["hop_le"])
        self.assertIn("LFS", r["loi"])

    def test_thieu_config(self) -> None:
        self._onnx("thieu")
        r = self._soi("thieu")
        self.assertFalse(r["hop_le"])
        self.assertIn("thiếu", r["loi"])

    def test_config_khong_phai_json(self) -> None:
        self._onnx("xau")
        (self.d / "xau.onnx.json").write_text("{khong phai json", encoding="utf-8")
        r = self._soi("xau")
        self.assertFalse(r["hop_le"])
        self.assertIn("JSON", r["loi"])

    def test_config_thieu_khoa_bat_buoc(self) -> None:
        self._onnx("cut"); self._config("cut", {"audio": {"sample_rate": 22050}})
        r = self._soi("cut")
        self.assertFalse(r["hop_le"])
        self.assertIn("phoneme_id_map", r["loi"])

    @unittest.skipUnless(hasattr(os, "symlink"), "nền tảng không có symlink")
    def test_symlink_con_song_thi_hop_le(self) -> None:
        """Bộ NghiTTS dùng một `config.json` chung + symlink cho từng giọng."""
        chung = self.d / "config.json"
        chung.write_text(json.dumps(CONFIG_TOI_THIEU), encoding="utf-8")
        self._onnx("link")
        try:
            os.symlink(chung, self.d / "link.onnx.json")
        except OSError as exc:
            self.skipTest(f"không tạo được symlink: {exc}")
        r = self._soi("link")
        self.assertTrue(r["hop_le"], r["loi"])
        self.assertIsNotNone(r["config_target"])

    @unittest.skipUnless(hasattr(os, "symlink"), "nền tảng không có symlink")
    def test_symlink_gay_duoc_bao_RIENG_khong_lan_voi_thieu_tep(self) -> None:
        """
        Hai lỗi khác nhau, cách sửa khác nhau: symlink gãy thì tạo lại link,
        thiếu tệp thì copy config vào. Gộp thành một thông báo là bắt người vận
        hành tự đoán.
        """
        self._onnx("gay")
        try:
            os.symlink(self.d / "khong-he-co.json", self.d / "gay.onnx.json")
        except OSError as exc:
            self.skipTest(f"không tạo được symlink: {exc}")
        r = self._soi("gay")
        self.assertFalse(r["hop_le"])
        self.assertIn("symlink gãy", r["loi"])


class MaThoat(Nen):

    def test_thoat_0_khi_moi_model_deu_hop_le(self) -> None:
        self._onnx("a"); self._config("a")
        self.assertEqual(
            self.mod.main(["--models-dir", str(self.d), "--no-load"]), 0)

    def test_thoat_1_khi_co_model_hong(self) -> None:
        self._onnx("tot"); self._config("tot")
        self._onnx("hong")          # thiếu config
        self.assertEqual(
            self.mod.main(["--models-dir", str(self.d), "--no-load"]), 1)

    def test_thoat_2_khi_thu_muc_sai(self) -> None:
        self.assertEqual(
            self.mod.main(["--models-dir", str(self.d / "khong-co")]), 2)

    def test_thoat_2_khi_thu_muc_rong(self) -> None:
        self.assertEqual(self.mod.main(["--models-dir", str(self.d)]), 2)

    def test_ghi_duoc_bao_cao_json(self) -> None:
        self._onnx("a"); self._config("a")
        ra = self.d / "bao-cao.json"
        self.mod.main(["--models-dir", str(self.d), "--no-load",
                       "--json", str(ra)])
        d = json.loads(ra.read_text(encoding="utf-8"))
        self.assertEqual(d["tong"], 1)
        self.assertEqual(d["hop_le"], 1)
        self.assertEqual(d["chi_tiet"][0]["voice"], "a")


class ChiDoc(unittest.TestCase):
    """Script không được ghi vào thư mục model, không được gọi Appwrite/R2."""

    def test_khong_import_appwrite_r2_hay_cau_hinh_may_chu(self) -> None:
        """
        Xét IMPORT THẬT bằng AST, không so chuỗi.

        Docstring của script có nhắc "không gọi Appwrite, không gọi R2" — so
        chuỗi thô sẽ bắt nhầm chính câu cam kết đó.
        """
        import ast

        cay = ast.parse((GOC / "scripts" / "validate_nghitts_models.py")
                        .read_text(encoding="utf-8"))
        nhap = set()
        for nut in ast.walk(cay):
            if isinstance(nut, ast.Import):
                nhap.update(a.name.split(".")[0] for a in nut.names)
            elif isinstance(nut, ast.ImportFrom) and nut.module:
                nhap.add(nut.module.split(".")[0])
        for cam in ("boto3", "httpx", "requests", "server"):
            self.assertNotIn(cam, nhap,
                             f"script chỉ đọc, không được import {cam}")
        # `piper` là ngoại lệ hợp lệ: nạp model chính là việc của nó.
        self.assertLessEqual(nhap - {"argparse", "json", "os", "sys", "time",
                                     "pathlib", "typing", "piper", "__future__"},
                             set(), f"import ngoài dự kiến: {nhap}")

    def test_khong_ghi_vao_thu_muc_model(self) -> None:
        nguon = (GOC / "scripts" / "validate_nghitts_models.py").read_text(
            encoding="utf-8")
        # Chỗ ghi DUY NHẤT được phép là tệp báo cáo `--json`.
        so_lan_mo_ghi = nguon.count('open(a.json, "w"')
        self.assertEqual(so_lan_mo_ghi, 1)
        for cam in ("unlink(", "rmdir(", "mkdir(", "write_bytes(", "rename("):
            self.assertNotIn(cam, nguon, f"script không được {cam}")


if __name__ == "__main__":
    unittest.main()
