"""
Fanfic Chat V1 — cap UserSig Tencent Chat phia may chu (`server/chat_tencent.py`)
va hai route `/api/chat/session`, `/api/chat/identities`.

Khoa bi mat trong file nay la GIA (khong phai khoa that cua app nao); moi bai
test dung `patch.dict(os.environ, ...)` nen khong de lai cau hinh cho bai khac.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import unittest
import zlib
from typing import Dict
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.requests import Request

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.chat_tencent import (
    ChatNotConfigured,
    TencentChatSettings,
    cap_phien,
    chat_user_id,
    fanfic_user_id_tu_chat,
    gen_user_sig,
)
from server.rate_limit import TIER_A, TIER_B, SlidingWindowRateLimiter, classify_request
from server.rate_limit import limiter as rate_limit_limiter
from server.secret_redaction import loc_bo_de_qui

KHOA_GIA = "khoa-gia-chi-de-test-0123456789abcdef0123456789abcdef"
ENV_DEV = {"FAS_TENCENT_CHAT_ENV": "dev", "FAS_TENCENT_CHAT_DEV_SDKAPPID": "20047363",
           "FAS_TENCENT_CHAT_DEV_SECRET_KEY": KHOA_GIA}
ENV_SACH = {k: "" for k in ("FAS_TENCENT_CHAT_ENV", "FAS_TENCENT_CHAT_DEV_SDKAPPID",
                            "FAS_TENCENT_CHAT_DEV_SECRET_KEY", "FAS_TENCENT_CHAT_PROD_SDKAPPID",
                            "FAS_TENCENT_CHAT_PROD_SECRET_KEY", "FAS_TENCENT_CHAT_USERSIG_TTL_SECONDS")}


def giai_ma_sig(sig: str) -> dict:
    """Nguoc cua TLSSigAPIv2: `* - _` -> `+ / =`, base64, zlib, JSON."""
    b64 = sig.replace("*", "+").replace("-", "/").replace("_", "=")
    return json.loads(zlib.decompress(base64.b64decode(b64)))


class TestUserSig(unittest.TestCase):
    def test_cau_truc_va_chu_ky_tlssigapiv2(self):
        luc = 1_759_000_000
        sig = gen_user_sig(20047363, KHOA_GIA, "fw_usr_abc", 7200, now=luc)
        self.assertRegex(sig, r"^[A-Za-z0-9*\-_]+$", "chi ky tu base64-url kieu Tencent")
        goi = giai_ma_sig(sig)
        self.assertEqual(goi["TLS.ver"], "2.0")
        self.assertEqual(goi["TLS.identifier"], "fw_usr_abc")
        self.assertEqual(goi["TLS.sdkappid"], 20047363)
        self.assertEqual(goi["TLS.expire"], 7200)
        self.assertEqual(goi["TLS.time"], luc)
        noi_dung = ("TLS.identifier:fw_usr_abc\nTLS.sdkappid:20047363\n"
                    f"TLS.time:{luc}\nTLS.expire:7200\n")
        mong_doi = base64.b64encode(hmac.new(KHOA_GIA.encode(), noi_dung.encode(),
                                             hashlib.sha256).digest()).decode()
        self.assertEqual(goi["TLS.sig"], mong_doi)

    def test_tat_dinh_va_khoa_khac_thi_chu_ky_khac(self):
        a = gen_user_sig(1, "k1", "fw_x", 300, now=100)
        self.assertEqual(a, gen_user_sig(1, "k1", "fw_x", 300, now=100))
        self.assertNotEqual(giai_ma_sig(a)["TLS.sig"], giai_ma_sig(gen_user_sig(1, "k2", "fw_x", 300, now=100))["TLS.sig"])

    def test_sig_khong_chua_khoa(self):
        sig = gen_user_sig(20047363, KHOA_GIA, "fw_x", 7200, now=1)
        self.assertNotIn(KHOA_GIA, json.dumps(giai_ma_sig(sig)))


class TestChatUserId(unittest.TestCase):
    def test_id_appwrite_va_mock_giu_nguyen_co_tien_to(self):
        for uid in ("68d1f2a3b4c5d6e7f8a9", "usr_20ae9faa08db4dc3"):
            cid = chat_user_id(uid)
            self.assertEqual(cid, "fw_" + uid)
            self.assertLessEqual(len(cid.encode()), 32)
            self.assertEqual(fanfic_user_id_tu_chat(cid), uid)

    def test_id_la_hoac_dai_bam_dung_32_byte_mot_chieu(self):
        for uid in ("người-dùng@ví dụ", "x" * 40):
            cid = chat_user_id(uid)
            self.assertTrue(cid.startswith("fwh_"))
            self.assertEqual(len(cid), 32)
            self.assertRegex(cid, r"^[A-Za-z0-9_-]+$")
            self.assertEqual(cid, chat_user_id(uid), "phai tat dinh")
            self.assertIsNone(fanfic_user_id_tu_chat(cid))

    def test_hai_dang_khong_trung(self):
        self.assertNotEqual(chat_user_id("h" + "0" * 28)[:4], "fwh_")
        with self.assertRaises(ValueError):
            chat_user_id("")
        self.assertIsNone(fanfic_user_id_tu_chat("administrator"))


class TestSettings(unittest.TestCase):
    def test_khong_co_mac_dinh_env_trong_la_tat(self):
        s = TencentChatSettings.from_env({})
        self.assertEqual(s.env, "")
        self.assertFalse(s.configured)
        with self.assertRaises(ChatNotConfigured):
            cap_phien(s, "usr_x")

    def test_env_trong_ma_du_bien_dev_van_tat(self):
        """Quen dat ENV tren may co san bien DEV khong duoc lang le ky bang app DEV."""
        du = {k: v for k, v in ENV_DEV.items() if k != "FAS_TENCENT_CHAT_ENV"}
        self.assertFalse(TencentChatSettings.from_env(du).configured)

    def test_prod_thieu_bien_khong_roi_ve_dev(self):
        s = TencentChatSettings.from_env({**ENV_DEV, "FAS_TENCENT_CHAT_ENV": "prod"})
        self.assertFalse(s.configured, "prod thieu cau hinh phai TAT, khong duoc dung app DEV")
        self.assertEqual(s.sdk_app_id, 0)

    def test_env_la_khong_co_app(self):
        self.assertFalse(TencentChatSettings.from_env({**ENV_DEV, "FAS_TENCENT_CHAT_ENV": "staging"}).configured)

    def test_describe_va_repr_khong_lo_khoa(self):
        s = TencentChatSettings.from_env(ENV_DEV)
        self.assertTrue(s.configured)
        self.assertNotIn(KHOA_GIA, json.dumps(s.describe()))
        self.assertNotIn(KHOA_GIA, repr(s))

    def test_ttl_bi_kep(self):
        self.assertEqual(TencentChatSettings.from_env({"FAS_TENCENT_CHAT_USERSIG_TTL_SECONDS": "5"}).usersig_ttl_seconds, 300)
        self.assertEqual(TencentChatSettings.from_env({"FAS_TENCENT_CHAT_USERSIG_TTL_SECONDS": "999999"}).usersig_ttl_seconds, 86400)


class ChatRouteCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main._han_muc_phien_chat = SlidingWindowRateLimiter()
        # Bo dem Tier cua middleware la TOAN TIEN TRINH: chay ca bo test thi
        # cac bai truoc da tieu het han muc cua IP "testclient" — xoa de bai
        # nay khong phu thuoc thu tu chay (CI tung tra 429 o day).
        rate_limit_limiter.reset()
        self.client = TestClient(server_main.app)

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str, username: str = "") -> str:
        # Tao thang qua adapter (nhu `test_creator_service`), khong qua
        # `/api/auth/register` — route do co han muc Tier A theo IP.
        server_main.identity.register(email, "matkhau123", email.split("@")[0])
        tok = server_main.identity.login(email, "matkhau123")
        if username:
            r = self.client.put("/api/creator/username", headers=self.auth(tok), json={"username": username})
            self.assertEqual(r.status_code, 200, r.text)
        return tok


class TestSessionRoute(ChatRouteCase):
    def test_chua_dang_nhap_401(self):
        self.assertEqual(self.client.post("/api/chat/session").status_code, 401)

    def test_thieu_cau_hinh_503_ro_rang(self):
        tok = self.user("a@example.com")
        with patch.dict(os.environ, ENV_SACH):
            r = self.client.post("/api/chat/session", headers=self.auth(tok))
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "chat_not_configured")

    def test_cap_phien_dev(self):
        tok = self.user("b@example.com")
        me = self.client.get("/api/auth/me", headers=self.auth(tok)).json()["profile"]
        truoc = int(time.time() * 1000)
        with patch.dict(os.environ, {**ENV_SACH, **ENV_DEV}):
            r = self.client.post("/api/chat/session", headers=self.auth(tok))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers.get("cache-control"), "no-store")
        d = r.json()
        self.assertEqual(set(d), {"sdkAppId", "userId", "userSig", "expiresAt", "environment"})
        self.assertEqual(d["sdkAppId"], 20047363)
        self.assertEqual(d["environment"], "dev")
        self.assertEqual(d["userId"], chat_user_id(me["user_id"]))
        self.assertGreaterEqual(d["expiresAt"], truoc + 7200 * 1000 - 5000)
        self.assertEqual(giai_ma_sig(d["userSig"])["TLS.identifier"], d["userId"])
        self.assertNotIn(KHOA_GIA, r.text, "khoa bi mat KHONG BAO GIO duoc roi khoi may chu")

    def test_han_muc_rieng_429_kem_retry_after(self):
        tok = self.user("c@example.com")
        with patch.dict(os.environ, {**ENV_SACH, **ENV_DEV}):
            ma = [self.client.post("/api/chat/session", headers=self.auth(tok)).status_code
                  for _ in range(server_main.CHAT_PHIEN_TOI_DA)]
            r = self.client.post("/api/chat/session", headers=self.auth(tok))
        self.assertEqual(server_main.CHAT_PHIEN_TOI_DA, 20)
        self.assertEqual(ma, [200] * 20)
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.json()["detail"]["code"], "chat_rate_limited")
        self.assertGreaterEqual(int(r.headers["retry-after"]), 1)


class TestIdentitiesRoute(ChatRouteCase):
    def test_chua_dang_nhap_401(self):
        self.assertEqual(self.client.post("/api/chat/identities", json={}).status_code, 401)

    def test_tra_danh_tinh_fanfic_khong_co_email(self):
        tok_a = self.user("an@example.com", "an_doc_gia")
        tok_b = self.user("binh@example.com", "binh_tac_gia")
        cid_b = chat_user_id(self.client.get("/api/auth/me", headers=self.auth(tok_b)).json()["profile"]["user_id"])
        r = self.client.post("/api/chat/identities", headers=self.auth(tok_a),
                             json={"chat_user_ids": [cid_b, "fw_khong_ton_tai", "fwh_" + "0" * 28],
                                   "usernames": ["binh_tac_gia", "khong_co_ai"]})
        self.assertEqual(r.status_code, 200, r.text)
        items = r.json()["items"]
        self.assertEqual(len(items), 5)
        theo_cid, theo_ten = items[0], items[3]
        for it in (theo_cid, theo_ten):
            self.assertTrue(it["found"])
            self.assertEqual(it["chat_user_id"], cid_b)
            self.assertEqual(it["username"], "binh_tac_gia")
            self.assertIn("level", it)
            self.assertIn("equipped_title", it)
            self.assertIn("avatar_frame", it)
        self.assertEqual([it["found"] for it in items], [True, False, False, True, False])
        self.assertNotIn("@example.com", r.text, "khong duoc lo email")

    def test_ho_so_da_xoa_authError_khong_lam_500_ca_lo(self):
        """Appwrite nem `AuthError` cho MOI ma >=400 (ke ca 404) — mot peer da xoa
        tai khoan khong duoc lam hong ca hop thu cua nguoi kia."""
        from server.adapters import AuthError
        tok = self.user("e@example.com", "e_nguoi_dung")

        def nem(*_a, **_k):
            raise AuthError("Document with the requested ID could not be found.")

        with patch.object(server_main.identity, "profiles_by_ids", nem), \
                patch.object(server_main.identity, "profile_by_username", nem):
            r = self.client.post("/api/chat/identities", headers=self.auth(tok),
                                 json={"chat_user_ids": ["fw_da_xoa_123"], "usernames": ["ai_do"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([it["found"] for it in r.json()["items"]], [False, False])

    def test_appwrite_sap_van_la_503(self):
        """`AppwriteUnavailableError` (lop con cua AuthError) KHONG bi nuot thanh 'khong tim thay'."""
        from server.adapters import AppwriteUnavailableError
        tok = self.user("f@example.com")

        def sap(*_a, **_k):
            raise AppwriteUnavailableError("Không kết nối được Appwrite.")

        with patch.object(server_main.identity, "profiles_by_ids", sap):
            r = self.client.post("/api/chat/identities", headers=self.auth(tok),
                                 json={"chat_user_ids": ["fw_x"]})
        self.assertEqual(r.status_code, 503)

    def test_gioi_han_kich_thuoc(self):
        tok = self.user("d@example.com")
        r = self.client.post("/api/chat/identities", headers=self.auth(tok),
                             json={"chat_user_ids": [f"fw_{i}" for i in range(51)]})
        self.assertEqual(r.status_code, 422)


class TestHaTang(unittest.TestCase):
    def test_route_chat_thuoc_tier_a(self):
        for duong in ("/api/chat/session", "/api/chat/identities"):
            req = Request({"type": "http", "method": "POST", "path": duong, "headers": [], "query_string": b""})
            self.assertEqual(classify_request(req)[0], TIER_A, duong)

    def test_ai_chat_ask_khong_doi_tier(self):
        # `/api/chat/ask` (AI chat co san) khong thuoc Chat V1 — giu Tier B.
        req = Request({"type": "http", "method": "POST", "path": "/api/chat/ask",
                       "headers": [], "query_string": b""})
        self.assertEqual(classify_request(req)[0], TIER_B)

    def test_log_che_usersig_va_khoa(self):
        sach = loc_bo_de_qui({"userSig": "abc", "secret_key": "k", "sdkAppId": 1})
        self.assertNotEqual(sach["userSig"], "abc")
        self.assertNotEqual(sach["secret_key"], "k")
        self.assertEqual(sach["sdkAppId"], 1)


if __name__ == "__main__":
    unittest.main()
