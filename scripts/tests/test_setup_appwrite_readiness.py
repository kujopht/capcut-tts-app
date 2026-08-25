"""
`scripts/setup_appwrite.py` — cho SAN SANG that su cua thuoc tinh/index,
khong chi "da ton tai".

Su co that (2026-08-21, self-host PROD): job nen tao `profiles.user_id` bi
Appwrite danh dau "failed" trong hang doi (Utopia queue), khong co co che tu
dong thu lai. Thuoc tinh ket vinh vien o "processing". Ham cu
(`_doi_thuoc_tinh_san_sang`) chi cho khi CO thuoc tinh MOI trong lan chay
hien tai, va im lang bo qua sau khi het luot thu — nen lan chay lai nao cung
thay thuoc tinh "da co" va khong bao gio phat hien no khong dung duoc, cho
toi khi `_ensure_index` that bai voi loi 400 mo ho "not yet available".

Cac test o day dung mock truc tiep `Setup._call` (khong goi mang that) de
tai hien tung tinh huong trang thai ma khong can Appwrite that.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import httpx

os.environ.setdefault("FAS_ENV_FILE", "")

from scripts.setup_appwrite import Setup  # noqa: E402


def _tao_setup() -> Setup:
    # dry_run=True chi de qua duoc __init__ (khong doi hoi credential that) —
    # cac ham duoc test o day khong tu kiem tra `self.dry_run`.
    return Setup(dry_run=True)


def _thuoc_tinh(key: str, status: str, error: str = "") -> dict:
    return {"attributes": [{"key": key, "status": status, "error": error}]}


def _index(key: str, status: str, error: str = "") -> dict:
    return {"indexes": [{"key": key, "status": status, "error": error}]}


class ChoThuocTinhSanSangTest(unittest.TestCase):
    def test_1_available_ngay_lap_tuc(self):
        """Kich ban 1: da 'available' tu lan kiem tra dau — khong lap lai."""
        s = _tao_setup()
        with patch.object(s, "_call", return_value=_thuoc_tinh("user_id", "available")) as m:
            s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id")
        self.assertEqual(m.call_count, 1)

    def test_2_processing_roi_available(self):
        """Kich ban 2: 'processing' vai lan roi chuyen 'available'."""
        s = _tao_setup()
        ket_qua = [
            _thuoc_tinh("user_id", "processing"),
            _thuoc_tinh("user_id", "processing"),
            _thuoc_tinh("user_id", "available"),
        ]
        with patch.object(s, "_call", side_effect=ket_qua), \
             patch("time.sleep", return_value=None):
            s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id")

    def test_3_processing_roi_failed_nem_loi_ro_rang(self):
        """Kich ban 3: chuyen 'failed' — phai nem loi NGAY, khong cho tiep,
        va thong diep phai chua nguyen van loi Appwrite tra ve."""
        s = _tao_setup()
        ket_qua = [
            _thuoc_tinh("user_id", "processing"),
            _thuoc_tinh("user_id", "failed", error="Mongo write conflict"),
        ]
        with patch.object(s, "_call", side_effect=ket_qua), \
             patch("time.sleep", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id")
        self.assertIn("failed", str(ctx.exception))
        self.assertIn("Mongo write conflict", str(ctx.exception))

    def test_4_stuck_nem_loi_ro_rang(self):
        """Kich ban 4: trang thai 'stuck' cung phai nem loi ngay lap tuc,
        khong tiep tuc cho vo ich."""
        s = _tao_setup()
        with patch.object(s, "_call", return_value=_thuoc_tinh("user_id", "stuck")):
            with self.assertRaises(SystemExit) as ctx:
                s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id")
        self.assertIn("stuck", str(ctx.exception))

    def test_5_het_thoi_gian_cho_nem_loi_ro_rang(self):
        """Kich ban 5: mai 'processing', khong bao gio 'available'/'failed' —
        phai nem loi RO RANG sau `timeout_giay`, khong treo vo han va khong
        im lang bo qua (khac ham cu)."""
        s = _tao_setup()
        # timeout_giay rat nho de test chay nhanh — dung time.monotonic that
        # (khong mock) vi ham dung no de tinh han chot.
        with patch.object(s, "_call", return_value=_thuoc_tinh("user_id", "processing")), \
             patch("time.sleep", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id", timeout_giay=0.01)
        self.assertIn("processing", str(ctx.exception))

    def test_thuoc_tinh_bien_mat_nem_loi(self):
        s = _tao_setup()
        with patch.object(s, "_call", return_value={"attributes": []}):
            with self.assertRaises(SystemExit):
                s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id")


class ChoIndexSanSangTest(unittest.TestCase):
    def test_available_ngay(self):
        s = _tao_setup()
        with patch.object(s, "_call", return_value=_index("email_unique", "available")):
            s._cho_index_san_sang("/v1/.../profiles", "email_unique")

    def test_failed_nem_loi(self):
        s = _tao_setup()
        with patch.object(s, "_call", return_value=_index("email_unique", "failed", "duplicate key")):
            with self.assertRaises(SystemExit) as ctx:
                s._cho_index_san_sang("/v1/.../profiles", "email_unique")
        self.assertIn("duplicate key", str(ctx.exception))


class IndexChoTatCaThuocTinhTest(unittest.TestCase):
    """Kich ban 6: tao index phai kiem TRUOC rang moi thuoc tinh no tham
    chieu deu 'available' — bao loi RO RANG liet ke dung thuoc tinh nao chua
    san sang, thay vi de Appwrite tra 400 mo ho."""

    def test_index_tu_choi_khi_mot_thuoc_tinh_chua_available(self):
        s = _tao_setup()
        trang_thai = {
            "attributes": [
                {"key": "a", "status": "available"},
                {"key": "b", "status": "processing"},
            ]
        }
        with patch.object(s, "_call", return_value=trang_thai):
            with self.assertRaises(SystemExit) as ctx:
                s._kiem_thuoc_tinh_san_sang_cho_index(
                    "/v1/.../t", "t_idx", ["a", "b"])
        thong_diep = str(ctx.exception)
        self.assertIn("t_idx", thong_diep)
        self.assertIn("['b']", thong_diep)
        self.assertNotIn("'a'", thong_diep)

    def test_index_khong_bao_loi_khi_tat_ca_da_available(self):
        s = _tao_setup()
        trang_thai = {
            "attributes": [
                {"key": "a", "status": "available"},
                {"key": "b", "status": "available"},
            ]
        }
        with patch.object(s, "_call", return_value=trang_thai):
            s._kiem_thuoc_tinh_san_sang_cho_index("/v1/.../t", "t_idx", ["a", "b"])


class IdempotentSauThatBaiMotPhanTest(unittest.TestCase):
    """Kich ban 7: chay lai sau khi mot thuoc tinh da bi xoa+tao lai (mo
    phong sua loi thu cong sau su co that) — thuoc tinh 'da co' van phai
    duoc cho san sang, khong duoc coi 'da co' la xong ngay."""

    def test_da_co_van_duoc_kiem_lai_san_sang(self):
        s = _tao_setup()
        # Mo phong: thuoc tinh da ton tai (tu lan chay truoc) nhung van
        # 'processing' (chua kip san sang khi script chay lai ngay sau).
        ket_qua = [
            _thuoc_tinh("user_id", "processing"),
            _thuoc_tinh("user_id", "available"),
        ]
        with patch.object(s, "_call", side_effect=ket_qua), \
             patch("time.sleep", return_value=None):
            # Goi thang ham cho, dung nhu duong _ensure_collection se di qua
            # cho truong hop "key in da_co" (bo qua _ensure_attribute nhung
            # VAN goi _cho_thuoc_tinh_san_sang).
            s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id")


class LoiMangThoangQuaTest(unittest.TestCase):
    """Su co that thu hai cung ngay (2026-08-21): tren cung self-host PROD,
    mot lan GET rieng bi `httpx.ReadTimeout` (loi mang that, khong phai
    status Appwrite) khien toan bo script sap ngang giua vong cho, ngay sau
    khi da qua duoc su co dau tien. `_goi_doc_thoi_thu_lai` phai coi day la
    MOT LAN THU THAT BAI binh thuong, khong phai ly do dung khac
    ('thuoc tinh bien mat')."""

    def test_read_timeout_duoc_thu_lai_roi_thanh_cong(self):
        s = _tao_setup()
        ket_qua = [
            httpx.ReadTimeout("The read operation timed out"),
            _thuoc_tinh("user_id", "available"),
        ]

        def _call_gia(*a, **kw):
            gia_tri = ket_qua.pop(0)
            if isinstance(gia_tri, Exception):
                raise gia_tri
            return gia_tri

        with patch.object(s, "_call", side_effect=_call_gia), \
             patch("time.sleep", return_value=None):
            s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id")
        self.assertEqual(ket_qua, [])

    def test_read_timeout_lap_lai_het_thoi_gian_nem_loi_ro_rang(self):
        s = _tao_setup()
        with patch.object(s, "_call",
                          side_effect=httpx.ReadTimeout("timed out")), \
             patch("time.sleep", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                s._cho_thuoc_tinh_san_sang(
                    "/v1/.../profiles", "user_id", timeout_giay=0.01)
        self.assertIn("mạng", str(ctx.exception))


class NovelsKhongCanFulltextTest(unittest.TestCase):
    """2026-08-26: PR #56 them title_fulltext_idx + description_fulltext_idx
    vao `novels` dua tren gia dinh sai la `contains()` can chi muc fulltext.
    Kiem tra truc tiep tren Appwrite self-host 1.9.6 (khong phai Cloud) —
    dung mot collection dung mot lan roi tu xoa trong chinh
    fanfic-world-prod/fanfic_world_prod — chung minh nguoc lai:
    q_or(contains(title,...), contains(description,...)) tra dung ket qua
    voi KHONG chi muc fulltext nao ca. Appwrite cung chi cho MOT chi muc
    fulltext moi collection nen phien ban hai chi muc chua bao gio triem
    khai duoc nhu code. Test nay khoa lai viec da go ca hai, tranh vo tinh
    them lai khi chua co bang chung song moi."""

    def test_novels_khong_con_chi_muc_fulltext(self):
        from scripts.setup_appwrite import SCHEMA

        indexes = SCHEMA["novels"]["indexes"]
        kinds = [kind for (_key, kind, _attrs) in indexes]
        self.assertNotIn("fulltext", kinds)

    def test_novels_van_giu_cac_chi_muc_key_khac(self):
        from scripts.setup_appwrite import SCHEMA

        keys = {key for (key, _kind, _attrs) in SCHEMA["novels"]["indexes"]}
        self.assertEqual(
            keys,
            {"owner_idx", "state_idx", "state_created_idx", "novel_id_idx"},
        )


if __name__ == "__main__":
    unittest.main()
