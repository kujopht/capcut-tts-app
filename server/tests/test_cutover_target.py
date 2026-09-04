"""Bai kiem cho cac phep khang dinh cua cutover GCE -> AWS.

Moi phep chuyen trang thai NGUY HIEM deu co bai kiem rieng o day. "Nguy
hiem" nghia hep va cu the: mot cau hinh sai o cho nay lam AWS va GCE cung
claim job THAT cua production, hoac lam worker production ghi vao bucket
staging (mat audio nguoi dung), hoac nguoc lai.

Cac bai kiem nay KHONG cham mang, khong doc tep that, khong can credential.
"""
from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ops.cutover_target import (  # noqa: E402
    PROD_APPWRITE_DATABASE_ID,
    PROD_APPWRITE_ENDPOINT,
    PROD_APPWRITE_PROJECT_ID,
    PROD_R2_BUCKET,
    PROD_UNITS,
    STAGING_UNITS,
    CutoverRefused,
    doc_env_text,
    khang_dinh_khong_phai_production,
    khang_dinh_production,
    kiem_unit_production,
    kiem_unit_staging,
    phan_loai_bucket,
    render_env_text,
    thieu_bien,
    tom_tat_env,
)


def env_production_hop_le(**ghi_de) -> dict:
    """Mot tep env production DUNG. Cac bai kiem lam hong tung truong mot."""
    e = {
        "FAS_ENV": "production",
        "DATA_BACKEND": "appwrite",
        "STORAGE_BACKEND": "r2",
        "FAS_INLINE_WORKER": "false",
        "APPWRITE_ENDPOINT": PROD_APPWRITE_ENDPOINT,
        "APPWRITE_PROJECT_ID": PROD_APPWRITE_PROJECT_ID,
        "APPWRITE_DATABASE_ID": PROD_APPWRITE_DATABASE_ID,
        "APPWRITE_API_KEY": "x" * 265,
        "R2_ACCOUNT_ID": "a" * 32,
        "R2_BUCKET": PROD_R2_BUCKET,
        "R2_ACCESS_KEY_ID": "k" * 32,
        "R2_SECRET_ACCESS_KEY": "s" * 64,
        "FAS_LOCAL_VOICES": "piper:ngochuyen,piper:ngochuyennew",
        "FAS_PUBLIC_VOICE_LANGUAGES": "vi",
    }
    e.update(ghi_de)
    return e


class KhangDinhProduction(unittest.TestCase):
    def test_env_dung_thi_qua(self):
        khang_dinh_production(env_production_hop_le())

    def test_thieu_bat_ky_bien_bat_buoc_nao_deu_bi_tu_choi(self):
        goc = env_production_hop_le()
        for ten in goc:
            with self.subTest(bien=ten):
                e = dict(goc)
                del e[ten]
                with self.assertRaises(CutoverRefused) as ctx:
                    khang_dinh_production(e)
                self.assertIn(ten, str(ctx.exception))

    def test_bien_rong_bi_coi_nhu_thieu(self):
        with self.assertRaises(CutoverRefused):
            khang_dinh_production(env_production_hop_le(APPWRITE_API_KEY=""))
        with self.assertRaises(CutoverRefused):
            khang_dinh_production(env_production_hop_le(APPWRITE_API_KEY="   "))

    # --- CHE DO THAT BAI NGUY HIEM NHAT -----------------------------------
    def test_TU_CHOI_bucket_staging_trong_env_production(self):
        """Worker production ghi vao bucket staging = audio nguoi dung bien mat."""
        for xau in ("fanfic-staging", "fanfic-dev"):
            with self.subTest(bucket=xau):
                with self.assertRaises(CutoverRefused) as ctx:
                    khang_dinh_production(env_production_hop_le(R2_BUCKET=xau))
                self.assertIn("STAGING", str(ctx.exception))

    def test_TU_CHOI_bucket_la_bien_khong_biet(self):
        with self.assertRaises(CutoverRefused):
            khang_dinh_production(env_production_hop_le(R2_BUCKET="fanfic-prod-2"))
        with self.assertRaises(CutoverRefused):
            khang_dinh_production(env_production_hop_le(R2_BUCKET="fanfic-prodx"))

    def test_TU_CHOI_du_an_appwrite_khong_phai_production(self):
        with self.assertRaises(CutoverRefused) as ctx:
            khang_dinh_production(
                env_production_hop_le(APPWRITE_PROJECT_ID="fanfic-world-staging"))
        self.assertIn("APPWRITE_PROJECT_ID", str(ctx.exception))

    def test_TU_CHOI_database_khong_phai_production(self):
        with self.assertRaises(CutoverRefused):
            khang_dinh_production(
                env_production_hop_le(APPWRITE_DATABASE_ID="fanfic_world_staging"))

    def test_TU_CHOI_endpoint_khac(self):
        """Bao gom ca Appwrite Cloud — tai lieu cu ghi nham day la production."""
        with self.assertRaises(CutoverRefused):
            khang_dinh_production(
                env_production_hop_le(APPWRITE_ENDPOINT="https://sgp.cloud.appwrite.io/v1"))

    def test_TU_CHOI_inline_worker_true(self):
        """`FAS_INLINE_WORKER=true` lam tien trinh worker tu cam chinh minh:
        no NHAN job (tang attempts) roi KHONG chay — job that bai oan."""
        with self.assertRaises(CutoverRefused) as ctx:
            khang_dinh_production(env_production_hop_le(FAS_INLINE_WORKER="true"))
        self.assertIn("FAS_INLINE_WORKER", str(ctx.exception))

    def test_TU_CHOI_storage_backend_local(self):
        """`local` la PASS GIA: job xong nhung audio khong len R2."""
        with self.assertRaises(CutoverRefused) as ctx:
            khang_dinh_production(env_production_hop_le(STORAGE_BACKEND="local"))
        self.assertIn("STORAGE_BACKEND", str(ctx.exception))

    def test_TU_CHOI_fas_env_staging(self):
        with self.assertRaises(CutoverRefused):
            khang_dinh_production(env_production_hop_le(FAS_ENV="staging"))

    def test_TU_CHOI_data_backend_khong_phai_appwrite(self):
        with self.assertRaises(CutoverRefused):
            khang_dinh_production(env_production_hop_le(DATA_BACKEND="mock"))


class CRLF(unittest.TestCase):
    """CRLF la loi THAT da gap hai lan: `systemd` cat \\r con `bash .` thi
    khong, nen hai ben doc ra hai gia tri khac nhau tu cung mot tep."""

    def test_gia_tri_co_CR_o_cuoi_van_duoc_chap_nhan(self):
        khang_dinh_production(env_production_hop_le(
            APPWRITE_ENDPOINT=PROD_APPWRITE_ENDPOINT + "\r",
            R2_BUCKET=PROD_R2_BUCKET + "\r",
            FAS_ENV="production\r",
        ))

    def test_doc_env_text_chuan_hoa_CRLF(self):
        e = doc_env_text("A=1\r\nB=2\r\n# ghi chu\r\n\r\nC=3\n")
        self.assertEqual(e, {"A": "1", "B": "2", "C": "3"})

    def test_doc_env_text_dong_sau_ghi_de_dong_truoc(self):
        """Giong `systemd` va giong `grep ... | tail -1` cua cac script ops."""
        self.assertEqual(doc_env_text("STORAGE_BACKEND=local\nSTORAGE_BACKEND=r2\n"),
                         {"STORAGE_BACKEND": "r2"})

    def test_render_env_text_luon_LF_thuan(self):
        s = render_env_text(env_production_hop_le())
        self.assertNotIn("\r", s)
        self.assertTrue(s.endswith("\n"))

    def test_render_env_text_tu_choi_gia_tri_rong(self):
        with self.assertRaises(CutoverRefused):
            render_env_text(env_production_hop_le(R2_BUCKET=""))

    def test_render_roi_doc_lai_thi_khang_dinh_van_qua(self):
        """Vong tron: sinh -> ghi -> doc -> khang dinh. Day dung la duong
        ma tep env di qua tren may that."""
        goc = env_production_hop_le()
        khang_dinh_production(doc_env_text(render_env_text(goc)))


class KhangDinhNguocLai(unittest.TestCase):
    """Env staging KHONG duoc tro vao production."""

    def test_staging_binh_thuong_thi_qua(self):
        khang_dinh_khong_phai_production({
            "R2_BUCKET": "fanfic-staging",
            "APPWRITE_PROJECT_ID": "fanfic-world-staging",
        })

    def test_TU_CHOI_staging_tro_vao_bucket_production(self):
        with self.assertRaises(CutoverRefused):
            khang_dinh_khong_phai_production({
                "R2_BUCKET": PROD_R2_BUCKET,
                "APPWRITE_PROJECT_ID": "fanfic-world-staging",
            })

    def test_TU_CHOI_staging_tro_vao_du_an_production(self):
        with self.assertRaises(CutoverRefused):
            khang_dinh_khong_phai_production({
                "R2_BUCKET": "fanfic-staging",
                "APPWRITE_PROJECT_ID": PROD_APPWRITE_PROJECT_ID,
            })


class DanhSachUnit(unittest.TestCase):
    def test_chi_unit_production_duoc_phep(self):
        for u in PROD_UNITS:
            kiem_unit_production(u)
        for u in STAGING_UNITS:
            with self.subTest(unit=u):
                with self.assertRaises(CutoverRefused):
                    kiem_unit_production(u)

    def test_unit_bia_dat_bi_tu_choi(self):
        for u in ("sshd.service", "fanfic-worker-prod.service.evil",
                  "../../etc/passwd", "fanfic-worker-prod"):
            with self.subTest(unit=u):
                with self.assertRaises(CutoverRefused):
                    kiem_unit_production(u)
                with self.assertRaises(CutoverRefused):
                    kiem_unit_staging(u)

    def test_hai_danh_sach_khong_giao_nhau(self):
        """Neu giao nhau thi mot verb 'stop staging' co the tat production."""
        self.assertEqual(set(PROD_UNITS) & set(STAGING_UNITS), set())

    def test_moi_unit_production_deu_co_chu_prod(self):
        for u in PROD_UNITS:
            self.assertIn("prod", u)

    def test_khong_unit_staging_nao_co_chu_prod(self):
        for u in STAGING_UNITS:
            self.assertNotIn("prod", u)


class KhongLoBiMat(unittest.TestCase):
    def test_tom_tat_khong_chua_gia_tri_bi_mat(self):
        e = env_production_hop_le(
            APPWRITE_API_KEY="SIEU_BI_MAT_APPWRITE",
            R2_SECRET_ACCESS_KEY="SIEU_BI_MAT_R2",
            R2_ACCESS_KEY_ID="SIEU_BI_MAT_ID",
            R2_ACCOUNT_ID="SIEU_BI_MAT_TK",
        )
        text = "\n".join(tom_tat_env(e))
        for bi_mat in ("SIEU_BI_MAT_APPWRITE", "SIEU_BI_MAT_R2",
                       "SIEU_BI_MAT_ID", "SIEU_BI_MAT_TK"):
            self.assertNotIn(bi_mat, text)

    def test_tom_tat_VAN_in_toa_do_khong_bi_mat(self):
        """Khong doc duoc bucket/project thi khong biet co tro nham hay khong."""
        text = "\n".join(tom_tat_env(env_production_hop_le()))
        self.assertIn(PROD_R2_BUCKET, text)
        self.assertIn(PROD_APPWRITE_PROJECT_ID, text)
        self.assertIn("[production]", text)

    def test_thong_bao_loi_khong_lo_gia_tri_bi_mat(self):
        e = env_production_hop_le(APPWRITE_API_KEY="")
        try:
            khang_dinh_production(e)
        except CutoverRefused as exc:
            self.assertNotIn("x" * 20, str(exc))
        else:
            self.fail("dang le phai tu choi")


class PhanLoaiBucket(unittest.TestCase):
    def test_ba_nhanh(self):
        self.assertEqual(phan_loai_bucket(PROD_R2_BUCKET), "production")
        self.assertEqual(phan_loai_bucket("fanfic-staging"), "staging")
        self.assertEqual(phan_loai_bucket("gi-do"), "unknown")
        self.assertEqual(phan_loai_bucket(None), "unknown")
        self.assertEqual(phan_loai_bucket(""), "unknown")

    def test_khong_khop_theo_tien_to(self):
        """`fanfic-prod-backup` KHONG phai production; khop phai la tuyet doi."""
        self.assertEqual(phan_loai_bucket("fanfic-prod-backup"), "unknown")


class BienThieu(unittest.TestCase):
    def test_tra_ve_ten_theo_dung_thu_tu_khai_bao(self):
        e = env_production_hop_le()
        del e["R2_BUCKET"]
        del e["FAS_ENV"]
        self.assertEqual(thieu_bien(e), ["FAS_ENV", "R2_BUCKET"])

    def test_thieu_FAS_LOCAL_VOICES_bi_tu_choi(self):
        """Thieu bien nay thi MOI job that bai voi VOICE_NOT_FOUND — worker
        van 'active', nen su co nay im lang cho toi khi co nguoi tao job."""
        e = env_production_hop_le()
        del e["FAS_LOCAL_VOICES"]
        with self.assertRaises(CutoverRefused) as ctx:
            khang_dinh_production(e)
        self.assertIn("FAS_LOCAL_VOICES", str(ctx.exception))

    def test_khong_thieu_gi_thi_rong(self):
        self.assertEqual(thieu_bien(env_production_hop_le()), [])


if __name__ == "__main__":
    unittest.main()
