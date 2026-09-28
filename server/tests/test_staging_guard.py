"""
Guard Appwrite STAGING (`scripts/staging/*`) — KHONG goi mang, chay duoc trong CI.

Canh ba nguyen tac trong `scripts/staging/__init__.py`: mot dich duy nhat, khong thua ke bien
production cua shell goi, khong in bi mat.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ops.cutover_target import PROD_APPWRITE_DATABASE_ID, PROD_APPWRITE_ENDPOINT, PROD_APPWRITE_PROJECT_ID
from scripts.staging import bi_mat, guard, migrate
from scripts.staging.bi_mat import CauHinhStaging

# Gia tri GIA, dung de kiem che/an — khong phai khoa that.
KHOA_GIA = "standard_" + "ab" * 40
TOKEN_GIA = "cd" * 32


def _cfg(**kw) -> CauHinhStaging:
    goc = dict(endpoint=guard.DICH_DUYET.endpoint, project_id=guard.DICH_DUYET.project_id,
               database_id="fanfic_staging", api_key=KHOA_GIA)
    goc.update(kw)
    return CauHinhStaging(**goc)


class NapBiMatTest(unittest.TestCase):
    def _tep(self, noi_dung: str) -> str:
        d = tempfile.mkdtemp()
        p = Path(d) / "ghi_chu.txt"
        p.write_text(noi_dung, encoding="utf-8")
        return str(p)

    def test_doc_tep_ghi_chu_cua_chu_du_an_ke_ca_bi_danh(self):
        p = self._tep(f"FAS_STAGING_APPWRITE_ENDPOINT={guard.DICH_DUYET.endpoint}/\n"
                      f"FAS_STAGING_APPWRITE_PROJECT_ID={guard.DICH_DUYET.project_id}\n"
                      f"# chu thich\nFAS_STAGING_APPWRITE_API_KEY={KHOA_GIA}\nSentrytoken: {TOKEN_GIA}\ndong rac\n")
        cfg = bi_mat.nap({bi_mat.BIEN_TEP: p})
        self.assertEqual(cfg.endpoint, guard.DICH_DUYET.endpoint)  # bo "/" cuoi
        self.assertEqual(cfg.database_id, bi_mat.DATABASE_MAC_DINH)
        self.assertEqual(cfg.sentry_token, TOKEN_GIA)
        self.assertEqual(cfg.khoa_schema, KHOA_GIA)

    def test_bien_moi_truong_thang_tep(self):
        p = self._tep(f"FAS_STAGING_APPWRITE_ENDPOINT=https://khac.cloud.appwrite.io/v1\n"
                      f"FAS_STAGING_APPWRITE_PROJECT_ID=x\nFAS_STAGING_APPWRITE_API_KEY={KHOA_GIA}\n")
        cfg = bi_mat.nap({bi_mat.BIEN_TEP: p, "FAS_STAGING_APPWRITE_ENDPOINT": guard.DICH_DUYET.endpoint})
        self.assertEqual(cfg.endpoint, guard.DICH_DUYET.endpoint)

    def test_thieu_chi_bao_ten_bien_khong_dung_bien_production(self):
        with self.assertRaises(bi_mat.ThieuCauHinh) as cm:
            bi_mat.nap({"APPWRITE_ENDPOINT": PROD_APPWRITE_ENDPOINT, "APPWRITE_API_KEY": KHOA_GIA})
        self.assertIn("FAS_STAGING_APPWRITE_API_KEY", str(cm.exception))
        self.assertNotIn(KHOA_GIA, str(cm.exception))

    def test_repr_va_an_khong_lo_bi_mat(self):
        cfg = _cfg(sentry_token=TOKEN_GIA)
        self.assertNotIn(KHOA_GIA, repr(cfg))
        self.assertNotIn(TOKEN_GIA, repr(cfg))
        self.assertEqual(cfg.an(f"loi {KHOA_GIA} va {TOKEN_GIA}"), "loi <an> va <an>")


class KiemDichTest(unittest.TestCase):
    def test_dich_duyet_qua(self):
        guard.kiem_dich(_cfg(), env={})

    def test_moi_dich_khac_bi_tu_choi(self):
        sai = [
            _cfg(project_id="fanfic-staging"),                       # ten project, khong phai ID
            _cfg(project_id=PROD_APPWRITE_PROJECT_ID),
            _cfg(endpoint="https://fra.cloud.appwrite.io/v1"),       # dung Cloud nhung sai vung
            _cfg(endpoint="http://sgp.cloud.appwrite.io/v1"),
            _cfg(endpoint=PROD_APPWRITE_ENDPOINT),
            _cfg(endpoint="https://appwrite.fanfic.world/v1"),
            _cfg(endpoint="https://sgp.cloud.appwrite.io.evil.example/v1"),
            _cfg(database_id=PROD_APPWRITE_DATABASE_ID),
            _cfg(database_id="Bad-Id"),
        ]
        for c in sai:
            with self.subTest(endpoint=c.endpoint, project=c.project_id, db=c.database_id):
                with self.assertRaises(guard.DichBiTuChoi):
                    guard.kiem_dich(c, env={})

    def test_tien_trinh_goi_la_production_bi_tu_choi(self):
        with self.assertRaises(guard.DichBiTuChoi):
            guard.kiem_dich(_cfg(), env={"FAS_ENV": "production"})


class MoiTruongConTest(unittest.TestCase):
    def test_khong_thua_ke_bien_production_cua_shell_goi(self):
        ban = {"APPWRITE_ENDPOINT": PROD_APPWRITE_ENDPOINT, "APPWRITE_PROJECT_ID": PROD_APPWRITE_PROJECT_ID,
               "APPWRITE_DATABASE_ID": PROD_APPWRITE_DATABASE_ID, "APPWRITE_API_KEY": "khoa-prod-gia",
               "R2_BUCKET": "fanfic-prod", "FAS_ENV_FILE": "server/.env.production", "SENTRY_AUTH_TOKEN": "x",
               "FAS_SOMETHING": "1", "PATH": os.environ.get("PATH", "")}
        with patch.dict(os.environ, ban, clear=True):
            env = guard.moi_truong_con(_cfg())
        self.assertEqual(env["APPWRITE_ENDPOINT"], guard.DICH_DUYET.endpoint)
        self.assertEqual(env["APPWRITE_PROJECT_ID"], guard.DICH_DUYET.project_id)
        self.assertEqual(env["APPWRITE_API_KEY"], KHOA_GIA)
        self.assertEqual(env["FAS_ENV_FILE"], "")
        self.assertEqual((env["DATA_BACKEND"], env["STORAGE_BACKEND"], env["FAS_ENV"]), ("appwrite", "local", "staging"))
        for ten in ("R2_BUCKET", "SENTRY_AUTH_TOKEN", "FAS_SOMETHING"):
            self.assertNotIn(ten, env)
        self.assertNotIn("APPWRITE_SCHEMA_API_KEY", env)
        self.assertEqual(guard.moi_truong_con(_cfg(), schema=True)["APPWRITE_SCHEMA_API_KEY"], KHOA_GIA)

    def test_them_bien_tro_vao_production_bi_tu_choi(self):
        with self.assertRaises(guard.DichBiTuChoi):
            guard.moi_truong_con(_cfg(), them={"R2_BUCKET": "fanfic-prod"})


class _Resp:
    def __init__(self, status: int, body):
        self.status_code = status
        self._body = body
        self.content = b"x"

    def json(self):
        return self._body


class _ClientGia:
    """Tra loi theo duong dan; ghi lai moi request (de chung minh khong co thao tac ghi)."""

    def __init__(self, users, db_status=200):
        self.users, self.db_status, self.goi = users, db_status, []

    def get(self, url, **kw):
        self.goi.append(("GET", url))
        return _Resp(200, {"version": "2.3.0"})

    def request(self, method, url, **kw):
        self.goi.append((method, url))
        if "/databases" in url:
            return _Resp(self.db_status, {"total": 0, "databases": []} if self.db_status == 200 else {"message": "no"})
        if "/users" in url:
            return _Resp(200, {"total": len(self.users), "users": self.users})
        return _Resp(404, {"message": "?"})


class XacMinhSongTest(unittest.TestCase):
    def test_project_trong_hoac_chi_tai_khoan_tong_hop_thi_qua_va_chi_doc(self):
        c = _ClientGia([{"email": "qa-1-an-1@example.test"}])
        bc = guard.xac_minh_song(_cfg(), client=c)
        self.assertEqual((bc["appwrite_version"], bc["users_total"], bc["users_tong_hop"]), ("2.3.0", 1, 1))
        self.assertTrue(all(m == "GET" for m, _ in c.goi), c.goi)

    def test_co_nguoi_dung_that_thi_dung(self):
        with self.assertRaises(guard.DichBiTuChoi):
            guard.xac_minh_song(_cfg(), client=_ClientGia([{"email": "nguoi.that@gmail.com"}]))

    def test_khoa_khong_thuoc_project_thi_dung(self):
        with self.assertRaises(guard.DichBiTuChoi):
            guard.xac_minh_song(_cfg(), client=_ClientGia([], db_status=401))


class KeHoachMigrationTest(unittest.TestCase):
    def test_pham_vi_hep_va_bao_vang_thay_vi_bia(self):
        cot = migrate.moi_collection()
        self.assertEqual(len(cot), len(set(cot)))
        for khong_duoc in ("novels", "chapters", "tts_jobs", "audio_tracks", "translation_jobs"):
            self.assertNotIn(khong_duoc, cot)
        kh = migrate.ke_hoach({"profiles": {"attributes": [1, 2], "indexes": [1]}})
        hs = next(m for m in kh if m["collection"] == "profiles")
        self.assertEqual((hs["co_trong_cay"], hs["so_thuoc_tinh"], hs["so_index"]), (True, 2, 1))
        self.assertTrue(all(not m["co_trong_cay"] for m in kh if m["collection"] != "profiles"))

    def test_moi_collection_trong_pham_vi_co_that_tren_nhanh_da_gop_hoac_duoc_bao_vang(self):
        from scripts.setup_appwrite import SCHEMA

        for m in migrate.ke_hoach(SCHEMA):
            if m["co_trong_cay"]:
                self.assertGreater(m["so_thuoc_tinh"], 0, m["collection"])


if __name__ == "__main__":
    unittest.main()
