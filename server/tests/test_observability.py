"""
Sentry backend (`server/observability.py`) — TAT mac dinh, va KHONG BAO GIO gui bi mat.

Bai end-to-end dung `sentry_sdk` THAT + tich hop FastAPI THAT, nhung transport GIA (bat envelope
trong bo nho) — khong goi mang. Mot route nem loi mang du loai bi mat trong thong diep, request
mang du loai header/cookie/query nhay cam; su kien bat duoc phai sach het.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from server import observability as ob

# Gia tri GIA hinh dang bi mat — khong phai khoa that.
KHOA_APPWRITE = "standard_" + "ab12" * 20
JWT = "eyJhbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + "." + "c2lnbmF0dXJlZ2lhMTIzNDU2"
USERSIG = "eJw" + "1jcEOgjAQRH9lwjXGUqmoFYz3" + "Rz0g0xa1RjG"
URL_KY = ("https://r2.example.com/audio/a.mp3?X-Amz-Algorithm=AWS4&X-Amz-Credential=AKIA" + "X" * 16
          + "&X-Amz-Signature=" + "f" * 64)
EMAIL = "nguoi.dung@vidu.vn"
TOKEN_PHIEN = "phien-" + "z9" * 20
# Ghep luc chay: Sentry gui kem vai dong MA NGUON quanh moi frame, nen mot literal nam trong chinh
# tep test nay se lot vao su kien du request that da sach — bai test se bao nham.
COOKIE = "cookie-" + "bi-mat"
MAT_KHAU = "s3cr3t-" + "value"


def _cam(than: str):
    return [x for x in (KHOA_APPWRITE, JWT, USERSIG, "X-Amz-Signature=" + "f" * 64, "X-Amz-Credential=AKIA",
                        EMAIL, TOKEN_PHIEN, "Bearer tok", COOKIE, MAT_KHAU) if x in than]


class TatMacDinhTest(unittest.TestCase):
    def test_khong_dsn_thi_khong_khoi_tao(self):
        st = SimpleNamespace(environment="production")
        self.assertIsNone(ob.tuy_chon_sentry(st, {}))
        self.assertFalse(ob.khoi_tao_sentry(st, env={}))

    def test_main_goi_sentry_truoc_khi_tao_app(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertLess(src.index("khoi_tao_sentry(get_settings())"), src.index("app = FastAPI("))


class CauHinhTest(unittest.TestCase):
    def test_moi_truong_ba_gia_tri(self):
        for vao, ra in (("development", "development"), ("local", "development"), ("staging", "staging"),
                        ("production", "production"), ("", "development"), ("la", "development")):
            self.assertEqual(ob.moi_truong(vao), ra)

    def test_release_theo_sha_build(self):
        self.assertEqual(ob.ban_phat_hanh({"RENDER_GIT_COMMIT": "A1B2C3D4E5F60718"}), "fanfic-api@a1b2c3d4e5f6")
        self.assertEqual(ob.ban_phat_hanh({"FAS_BUILD_SHA": "abc1234", "RENDER_GIT_COMMIT": "ffffffff"}),
                         "fanfic-api@abc1234")
        self.assertIsNone(ob.ban_phat_hanh({"RENDER_GIT_COMMIT": "khong-phai-sha"}))

    def test_lay_mau_hop_ly_va_khong_pii(self):
        t = ob.tuy_chon_sentry(SimpleNamespace(environment="staging"),
                               {ob.BIEN_DSN: "https://pub@o1.ingest.us.sentry.io/1", ob.BIEN_TRACES: "5"})
        self.assertEqual((t["environment"], t["sample_rate"], t["traces_sample_rate"]), ("staging", 1.0, 0.2))
        self.assertFalse(t["send_default_pii"])
        self.assertFalse(t["include_local_variables"])
        self.assertEqual(t["max_request_body_size"], "never")
        t = ob.tuy_chon_sentry(SimpleNamespace(environment="production"), {ob.BIEN_DSN: "https://p@o/1"})
        self.assertEqual(t["traces_sample_rate"], 0.0)


class LamSachTest(unittest.TestCase):
    def test_su_kien_tong_hop_sach_het(self):
        ev = {
            "message": f"loi {KHOA_APPWRITE} {EMAIL}",
            "request": {"url": URL_KY, "query_string": f"token={TOKEN_PHIEN}", "cookies": {"s": COOKIE},
                        "data": {"password": MAT_KHAU},
                        "headers": {"Authorization": f"Bearer {JWT}", "Cookie": f"a={COOKIE}",
                                    "X-Appwrite-Key": KHOA_APPWRITE, "X-Appwrite-Session": TOKEN_PHIEN,
                                    "User-Agent": "Mozilla/5.0", "Referer": URL_KY}},
            "user": {"id": "usr_1", "email": EMAIL, "ip_address": "10.0.0.1"},
            "exception": {"values": [{"type": "RuntimeError", "value": f"usersig={USERSIG} url {URL_KY} Bearer {JWT}",
                                      "stacktrace": {"frames": [{"function": "f", "vars": {"api_key": KHOA_APPWRITE}}]}}]},
            "breadcrumbs": {"values": [{"category": "httpx", "message": f"GET {URL_KY}",
                                        "data": {"url": URL_KY, "http.query": "X-Amz-Signature=" + "f" * 64,
                                                 "headers": {"authorization": f"Bearer {JWT}"}}}]},
            "extra": {"token": TOKEN_PHIEN, "ghi_chu": f"secret: {MAT_KHAU} {USERSIG}"},
            "tags": {"x": EMAIL},
        }
        ra = ob.lam_sach_su_kien(ev, {})
        than = json.dumps(ra, ensure_ascii=False)
        self.assertEqual(_cam(than), [], than)
        self.assertEqual(ra["request"]["url"], "https://r2.example.com/audio/a.mp3")
        self.assertEqual(sorted(ra["request"]["headers"]), ["User-Agent"])
        self.assertEqual(ra["user"], {"id": ob._an_danh("usr_1")})
        self.assertNotIn("vars", ra["exception"]["values"][0]["stacktrace"]["frames"][0])

    def test_lam_sach_hong_thi_bo_su_kien_khong_gui_tho(self):
        class Xau(dict):
            def get(self, *a, **k):
                raise RuntimeError("hong")

        self.assertIsNone(ob.lam_sach_su_kien(Xau()))


class EndToEndTest(unittest.TestCase):
    """sentry_sdk THAT + FastAPI THAT, transport gia — chung minh duong that dung khong lo bi mat."""

    def test_loi_route_that_duoc_bat_va_da_sach(self):
        import sentry_sdk
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from sentry_sdk.transport import Transport

        bat = []

        class Gia(Transport):
            def capture_envelope(self, envelope):
                bat.append(envelope)

        st = SimpleNamespace(environment="staging")
        # CHINH duong production (`khoi_tao_sentry`: tich hop, tag), chi thay transport.
        self.assertTrue(ob.khoi_tao_sentry(st, env={ob.BIEN_DSN: "https://pub@o1.ingest.us.sentry.io/1",
                                                   "RENDER_GIT_COMMIT": "a1b2c3d4e5f6a7b8"}, transport=Gia))
        try:
            app = FastAPI()

            @app.get("/hong")
            def hong():
                raise RuntimeError(f"Appwrite {KHOA_APPWRITE} usersig={USERSIG} {URL_KY} {EMAIL}")

            c = TestClient(app, raise_server_exceptions=False)
            r = c.get(f"/hong?token={TOKEN_PHIEN}&next=/a", headers={
                "Authorization": f"Bearer {JWT}", "Cookie": f"sid={COOKIE}", "X-Appwrite-Key": KHOA_APPWRITE})
            self.assertEqual(r.status_code, 500)
            sentry_sdk.flush(2)
        finally:
            sentry_sdk.get_client().close()
            sentry_sdk.init()  # client KHONG DSN: cac bai khac chay sau khong gui gi
        su_kien = [it.payload.json for env in bat for it in env.items if it.type == "event"]
        self.assertEqual(len(su_kien), 1, "lỗi 500 phải thành đúng MỘT sự kiện")
        ev = su_kien[0]
        than = json.dumps(ev, ensure_ascii=False)
        self.assertEqual(_cam(than), [], than[:2000])
        self.assertEqual(ev["environment"], "staging")
        self.assertEqual(ev["release"], "fanfic-api@a1b2c3d4e5f6")
        self.assertEqual(ev["tags"]["service"], "fanfic-api")
        self.assertNotIn("cookies", ev.get("request", {}))
        self.assertNotIn(TOKEN_PHIEN, ev.get("request", {}).get("query_string", ""))


if __name__ == "__main__":
    unittest.main()
