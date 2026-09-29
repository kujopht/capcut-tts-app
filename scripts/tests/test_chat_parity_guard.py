"""Rao may kiem tuong duong 1.9.6 (`scripts.chat_parity.guard`): chi loopback, chi `parity-*`, khong production."""
from __future__ import annotations

import unittest
from unittest import mock

from scripts.chat_parity import guard
from scripts.ops.cutover_target import PROD_APPWRITE_DATABASE_ID, PROD_APPWRITE_ENDPOINT, PROD_APPWRITE_PROJECT_ID


def cfg(**kw):
    d = {"endpoint": "http://127.0.0.1:8080/v1", "project_id": "parity-chat", "database_id": "parity_chat",
         "api_key": "khoa-gia-" + "x" * 20}
    d.update(kw)
    return guard.CauHinhParity(**d)


class KiemDichTest(unittest.TestCase):
    def test_loopback_parity_hop_le(self):
        for ep in ("http://127.0.0.1:8080/v1", "http://127.0.0.2/v1", "http://[::1]:8080/v1/",
                   "http://[0:0:0:0:0:0:0:1]/v1"):
            guard.kiem_dich(cfg(endpoint=ep))

    def test_tu_choi_moi_host_khong_phai_loopback(self):
        for ep in (PROD_APPWRITE_ENDPOINT, "https://sgp.cloud.appwrite.io/v1", "http://10.0.0.5:8080/v1",
                   "http://127.0.0.1.nip.io/v1", "http://localhost.fanfic.world/v1", "file:///v1", "",
                   # ten mien (ke ca localhost) khong duoc tin — hosts/DNS tro di dau cung duoc
                   "http://localhost/v1",
                   # thong tin dang nhap trong URL (review doc lap): tu choi du host sau @ la loopback
                   "http://evil.example@127.0.0.1:8080/v1", "http://u:p@127.0.0.1/v1"):
            with self.assertRaises(guard.DichBiTuChoi, msg=ep):
                guard.kiem_dich(cfg(endpoint=ep))

    def test_them_khong_duoc_ghi_de_toa_do(self):
        for k in ("APPWRITE_ENDPOINT", "APPWRITE_API_KEY", "FAS_ENV_FILE", "DATA_BACKEND"):
            with self.assertRaises(guard.DichBiTuChoi, msg=k):
                guard.moi_truong_con(cfg(), them={k: "https://x.example/v1"})

    def test_tu_choi_project_khong_parity_va_toa_do_production(self):
        for pid in (PROD_APPWRITE_PROJECT_ID, "fanfic-staging", "chat"):
            with self.assertRaises(guard.DichBiTuChoi):
                guard.kiem_dich(cfg(project_id=pid))
        with self.assertRaises(guard.DichBiTuChoi):
            guard.kiem_dich(cfg(database_id=PROD_APPWRITE_DATABASE_ID))
        with self.assertRaises(guard.DichBiTuChoi):
            guard.kiem_dich(cfg(api_key=""))
        with self.assertRaises(guard.DichBiTuChoi):
            guard.kiem_dich(cfg(endpoint="http://127.0.0.1:8080/"))

    def test_moi_truong_con_toi_thieu_khong_thua_ke(self):
        with mock.patch.dict("os.environ", {"APPWRITE_API_KEY": "khoa-that-cua-shell", "FAS_XP_ATOMIC": "1",
                                            "R2_BUCKET": "fanfic-prod", "PATH": "/bin"}, clear=True):
            env = guard.moi_truong_con(cfg(), them={"FAS_CHAT_V1": "1"})
        self.assertEqual(env["APPWRITE_ENDPOINT"], "http://127.0.0.1:8080/v1")
        self.assertEqual((env["FAS_ENV_FILE"], env["DATA_BACKEND"], env["FAS_CHAT_V1"]), ("", "appwrite", "1"))
        self.assertNotIn("FAS_XP_ATOMIC", env)
        self.assertNotIn("R2_BUCKET", env)
        self.assertNotEqual(env["APPWRITE_API_KEY"], "khoa-that-cua-shell")

    def test_che_khoa_trong_log(self):
        c = cfg()
        self.assertNotIn(c.api_key, c.an(f"loi 401 voi khoa {c.api_key}"))


class XacMinhSongTest(unittest.TestCase):
    def _gia(self, ver="1.9.6", users=None):
        users = users if users is not None else [{"email": "qa-1@example.test"}]

        def goi(_cfg, method, path, khoa=True):
            if path == "/health/version":
                assert not khoa, "1.9.6: /health/version kèm khoá = 401"
                return 200, {"version": ver}
            if path == "/databases":
                return 200, {"total": 0}
            if path.startswith("/users"):
                return 200, {"total": len(users), "users": users if "%22values%22%3A%5B0%5D" in path else []}
            raise AssertionError(path)
        return goi

    def test_dung_1_9_x_va_tai_khoan_tong_hop(self):
        with mock.patch.object(guard, "_goi", self._gia()):
            self.assertEqual(guard.xac_minh_song(cfg())["appwrite_version"], "1.9.6")

    def test_tu_choi_phien_ban_khac_va_nguoi_dung_that(self):
        for ver in ("2.3.0", "1.8.1", ""):
            with mock.patch.object(guard, "_goi", self._gia(ver=ver)), self.assertRaises(guard.DichBiTuChoi):
                guard.xac_minh_song(cfg())
        with mock.patch.object(guard, "_goi", self._gia(users=[{"email": "ban.doc@gmail.com"}])), \
                self.assertRaises(guard.DichBiTuChoi):
            guard.xac_minh_song(cfg())


if __name__ == "__main__":
    unittest.main()
