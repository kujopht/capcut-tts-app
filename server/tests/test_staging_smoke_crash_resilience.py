"""
`scripts/staging_smoke.py` phai CHIU DUOC tao-do-dang va khong de loi don
fixture DE LEN loi CHINH.

BOI CANH: canary staging that (2026-08-23, su co Appwrite het han muc doc) lam
`buoc_noi_dung` doc thang `r["chapter"]["chapter_id"]` sau khi `POST
/api/chapters` tra 404 — nem `KeyError` GIUA CHUNG, truoc khi ham kip
`return`. Hau qua: `main()` khong bao gio biet novel vua tao (`nid`) ton tai,
nen `don_dep` (nhan `ids=None`) bo qua hoan toan — truyen [SMOKE] nam lai
tren staging KHONG THE don duoc.

Ba dieu duoc khoa lai o day:
1. `buoc_noi_dung` TRA VE (khong nem loi) khi tao-do-dang, giu lai phan da
   tao duoc de con don.
2. `don_dep` CHIU DUOC `ids` chi co mot phan (thieu `chapter`).
3. `main()` giu nguyen loi CHINH (khong bi loi don-fixture de len) VA van
   chay don fixture du co loi chinh hay khong.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

GOC = Path(__file__).resolve().parents[2]


def nap_script():
    """Nap `scripts/staging_smoke.py` nhu MOT MODULE MOI moi lan goi — tranh
    trang thai `KET_QUA` (danh sach toan cuc) ro ri giua cac test."""
    duong = GOC / "scripts" / "staging_smoke.py"
    spec = importlib.util.spec_from_file_location(
        "staging_smoke_crash_test", duong)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class BuocNoiDungKhongCrashTest(unittest.TestCase):
    """`buoc_noi_dung` — khong duoc nem loi khi tao-do-dang."""

    def setUp(self) -> None:
        self.mod = nap_script()
        self.tk = {"a": "x@example.test", "mk": "mk", "dau": "abc12345",
                  "tok_a": "token-gia"}

    def _goi_gia(self, kich_ban):
        def goi(api, method, path, payload=None, token=None, timeout=300):
            key = (method, path)
            if key in kich_ban:
                return kich_ban[key]
            raise AssertionError(f"khong mong doi goi: {method} {path}")
        return goi

    def test_novel_that_bai_tra_ve_rong_khong_nem_loi(self):
        self.mod.goi = self._goi_gia({
            ("POST", "/api/novels"): (500, {"detail": "loi gia"}),
        })
        ids = self.mod.buoc_noi_dung("http://fake", self.tk)
        self.assertEqual(ids, {})

    def test_chapter_that_bai_SAU_khi_novel_thanh_cong_giu_lai_novel_id(self):
        """DAY LA DUNG kich ban that xay ra tren staging 2026-08-23."""
        self.mod.goi = self._goi_gia({
            ("POST", "/api/novels"): (201, {"novel": {"novel_id": "nov_that"}}),
            ("POST", "/api/chapters"): (
                404, {"detail": "Database reads limit for the current "
                               "billing cycle has been exceeded."}),
        })
        ids = self.mod.buoc_noi_dung("http://fake", self.tk)
        self.assertEqual(ids, {"novel": "nov_that"},
                         "phai giu novel_id de don_dep con xoa duoc")


class DonDepChiuDuocTaoDoDangTest(unittest.TestCase):
    """`don_dep` khong duoc gia dinh moi khoa cua `ids` deu co mat, va khong
    duoc de loi cua chinh no thoat ra ngoai."""

    def setUp(self) -> None:
        self.mod = nap_script()
        self.tk = {"tok_a": "token-gia"}

    def test_ids_rong_thi_bo_qua_an_toan(self):
        self.mod.goi = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("khong duoc goi HTTP nao khi ids rong"))
        self.mod.don_dep("http://fake", self.tk, {})  # khong duoc nem loi
        self.mod.don_dep("http://fake", self.tk, None)  # khong duoc nem loi

    def test_ids_chi_co_novel_van_xoa_duoc_khong_gia_dinh_co_chapter(self):
        goi_da_thuc_hien: List[Tuple[str, str]] = []

        def goi_gia(api, method, path, payload=None, token=None, timeout=300):
            goi_da_thuc_hien.append((method, path))
            if method == "POST" and path.endswith("/unpublish"):
                return 200, {}
            if method == "DELETE":
                # KHONG co chapter nao that su duoc tao — kho tra ve 0.
                return 200, {"removed": {"chapters": 0, "tracks": 0}}
            if method == "GET" and path == "/api/novels?mine=true":
                return 200, {"novels": []}
            if method == "GET" and path == "/api/jobs":
                return 200, {"count": 0}
            raise AssertionError(f"khong mong doi: {method} {path}")

        self.mod.goi = goi_gia
        # KHONG duoc nem KeyError/NameError du `ids` thieu "chapter".
        self.mod.don_dep("http://fake", self.tk, {"novel": "nov_that"})
        self.assertIn(("DELETE", "/api/novels/nov_that"), goi_da_thuc_hien)

    def test_loi_trong_chinh_don_dep_khong_thoat_ra_ngoai(self):
        """Neu chinh buoc don dep gap su co ha tang (vi du CUNG loi han muc
        vua lam chapter that bai), no phai duoc ghi lai nhu mot CANH BAO,
        khong duoc nem tiep — nguoi goi (`main()`) can `don_dep` LUON tra ve
        binh thuong de con chay `don_tai_khoan` sau do."""
        def goi_nem_loi(api, method, path, payload=None, token=None, timeout=300):
            raise RuntimeError("mat mang giua luc don dep")

        self.mod.goi = goi_nem_loi
        try:
            self.mod.don_dep("http://fake", self.tk, {"novel": "nov_that"})
        except Exception as exc:  # pragma: no cover - chinh la dieu dang kiem
            self.fail(f"don_dep khong duoc nem loi ra ngoai, nhung da nem: {exc!r}")


class MainGiuNguyenLoiChinhTest(unittest.TestCase):
    """`main()` — mot loi KHONG LUONG TRUOC o giua pipeline van phai la thu
    CUOI CUNG nguoi goi thay, du `don_dep` sau do CO gap loi rieng cua no."""

    def setUp(self) -> None:
        self.mod = nap_script()
        self.mod.KET_QUA.clear()

        # Rut gon toan bo pipeline ve muc toi thieu can de chay qua diem
        # nem loi: cac buoc TRUOC diem hong phai thanh cong binh thuong,
        # cac buoc SAU khong bao gio duoc goi toi (loi da nem truoc do).
        self.mod.danh_thuc = lambda *a, **k: True
        self.mod.buoc_suc_khoe = lambda *a, **k: {"author_gate_enabled": False}
        self.mod.buoc_xac_thuc = lambda *a, **k: {"tok_a": "token-gia"}
        self.mod.buoc_noi_dung = lambda *a, **k: {"novel": "nov1", "chapter": "chp1"}

        self.goi_don_dep: List[Optional[Dict[str, Any]]] = []
        self.goi_don_tai_khoan: List[Any] = []

    def _dat_don_dep(self, *, nem_loi: bool):
        def don_dep_gia(api, tk, ids):
            self.goi_don_dep.append(ids)
            if nem_loi:
                raise RuntimeError("loi PHU: don dep cung gap su co ha tang")
        self.mod.don_dep = don_dep_gia
        self.mod.don_tai_khoan = lambda tk, moi_truong: self.goi_don_tai_khoan.append(tk)

    def test_loi_khong_luong_truoc_duoc_nem_lai_SAU_khi_don_xong(self):
        self._dat_don_dep(nem_loi=False)
        self.mod.buoc_tts = self._nem(RuntimeError("loi that o buoc TTS"))

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.main(["--api", "http://fake",
                          "--skip-local-voice", "--skip-lifecycle"])
        self.assertEqual(str(ctx.exception), "loi that o buoc TTS")
        # Don van phai chay, kem dung `ids` da co tai thoi diem hong.
        self.assertEqual(self.goi_don_dep, [{"novel": "nov1", "chapter": "chp1"}])
        self.assertEqual(len(self.goi_don_tai_khoan), 1)

    def test_loi_don_dep_KHONG_de_len_loi_chinh(self):
        """Day la phep kiem QUYET DINH: `don_dep` CUNG nem loi (rieng cua
        no), nhung nguoi goi phai thay loi CHINH (tu buoc_tts), khong phai
        loi cua don_dep."""
        self._dat_don_dep(nem_loi=True)
        self.mod.buoc_tts = self._nem(RuntimeError("loi that o buoc TTS"))

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.main(["--api", "http://fake",
                          "--skip-local-voice", "--skip-lifecycle"])
        self.assertEqual(
            str(ctx.exception), "loi that o buoc TTS",
            "loi CHINH bi loi don-dep de len — dung chinh loi da mo ta trong "
            "docstring cua file nay")
        self.assertEqual(len(self.goi_don_dep), 1, "don_dep van phai duoc goi")

    def test_khong_co_loi_thi_khong_nem_gi_them(self):
        """Duong vui: khong co loi khong luong truoc thi `main()` tra ve int
        binh thuong (hanh vi cu, khong doi)."""
        self._dat_don_dep(nem_loi=False)
        for ten in ("buoc_tts", "buoc_danh_sach_giong", "buoc_tu_choi_giong",
                    "buoc_phan_quyen", "buoc_giao_dien", "buoc_dang_xuat"):
            setattr(self.mod, ten, lambda *a, **k: None)

        ma = self.mod.main(["--api", "http://fake",
                           "--skip-local-voice", "--skip-lifecycle"])
        self.assertIsInstance(ma, int)
        self.assertEqual(len(self.goi_don_dep), 1)

    def test_chua_tao_duoc_chuong_thi_dung_som_van_don_duoc_KHONG_nem_loi(self):
        """Tao-do-dang (chi co novel, khong co chapter) KHONG PHAI mot loi
        khong luong truoc — day la mot ket qua kt() HONG binh thuong, pipeline
        dung som mot cach co kiem soat, main() KHONG nem gi ca."""
        self._dat_don_dep(nem_loi=False)
        self.mod.buoc_noi_dung = lambda *a, **k: {"novel": "nov1"}  # KHONG co chapter
        self.mod.buoc_tts = self._nem(
            AssertionError("KHONG duoc goi buoc_tts khi chua co chapter"))

        ma = self.mod.main(["--api", "http://fake",
                           "--skip-local-voice", "--skip-lifecycle"])
        self.assertIsInstance(ma, int, "khong duoc nem loi cho truong hop nay")
        self.assertEqual(self.goi_don_dep, [{"novel": "nov1"}])

    @staticmethod
    def _nem(loi: Exception):
        def f(*a, **k):
            raise loi
        return f


if __name__ == "__main__":
    unittest.main()
