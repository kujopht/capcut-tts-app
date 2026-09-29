"""
Fanfic Chat V1 — ma nguoi dung chat (`server/messaging/ids.py`) va hai route `/api/chat/session`,
`/api/chat/identities`. Tin nhan chu chay tren Appwrite (`server/messaging/`); KHONG co Tencent.
"""

from __future__ import annotations

import time
import unittest
from typing import Dict
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.requests import Request

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.messaging.ids import chat_user_id
from server.messaging.ids import fanfic_user_id_from_chat as fanfic_user_id_tu_chat
from server.rate_limit import TIER_A, TIER_B, SlidingWindowRateLimiter, classify_request
from server.rate_limit import limiter as rate_limit_limiter
from server.secret_redaction import loc_bo_de_qui


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

    def test_tat_tin_nhan_503_ro_rang(self):
        tok = self.user("a@example.com")
        rt = server_main.messaging_runtime
        cu = rt.enabled
        rt.enabled = False
        try:
            r = self.client.post("/api/chat/session", headers=self.auth(tok))
        finally:
            rt.enabled = cu
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "chat_not_configured")

    def test_phien_nhan_tin_khong_co_credential_rieng(self):
        """Phien khong ky gi, khong co khoa/credential nao: moi request chat dung chinh token Fanfic."""
        tok = self.user("b@example.com")
        me = self.client.get("/api/auth/me", headers=self.auth(tok)).json()["profile"]
        truoc = int(time.time() * 1000)
        r = self.client.post("/api/chat/session", headers=self.auth(tok))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers.get("cache-control"), "no-store")
        d = r.json()
        self.assertEqual(set(d), {"provider", "userId", "expiresAt", "environment"})
        self.assertEqual(d["provider"], "fanfic")
        self.assertEqual(d["environment"], "memory")
        self.assertEqual(d["userId"], chat_user_id(me["user_id"]))
        self.assertGreaterEqual(d["expiresAt"], truoc + 3600 * 1000 - 5000)
        self.assertNotIn(tok, r.text, "token Fanfic khong duoc phan hoi lai")

    def test_han_muc_rieng_429_kem_retry_after(self):
        tok = self.user("c@example.com")
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

    def test_log_che_khoa_bi_mat(self):
        sach = loc_bo_de_qui({"secret_key": "k", "sdk_secret_key": "k2", "userSig": "abc", "sdkAppId": 1})
        self.assertNotEqual(sach["secret_key"], "k")
        self.assertNotEqual(sach["sdk_secret_key"], "k2")
        self.assertNotEqual(sach["userSig"], "abc")
        self.assertEqual(sach["sdkAppId"], 1)


if __name__ == "__main__":
    unittest.main()
