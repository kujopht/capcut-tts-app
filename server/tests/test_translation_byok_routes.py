"""
Duong API `/api/translate/provider-connections/*` (V5.1 BYOK) — qua
`TestClient`, cung phong cach voi `test_translate_routes.py`.

Đay CUNG la noi phu mot phan lon danh sach 16 muc "SECURITY TESTS" (Part K
cua yeu cau goc) — nhung muc CO THE quan sat duoc o tang HTTP (plaintext
khong bao gio tra ve qua API, loi validation duoc lam sach, nguoi dung khac
khong doc/xoa duoc ket noi cua nhau...). Cac muc con lai (ma hoa/AAD/fail-
closed o tang crypto thuan) da co o `test_translation_byok_crypto.py`.
"""

from __future__ import annotations

import unittest
from typing import Dict
from unittest.mock import patch

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.translation_byok_crypto import ByokCrypto, sinh_master_key_moi
from server.translation_byok_service import ProviderConnectionService
from server.translation_service import TranslationService
from server.translation_store import MockTranslationStore

KHOA_TEST = sinh_master_key_moi()


class ByokRouteTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.translation_store = MockTranslationStore()
        server_main.translation_byok_crypto = ByokCrypto.tu_moi_truong(KHOA_TEST)
        server_main.translation_byok_svc = ProviderConnectionService(
            server_main.translation_store, crypto=server_main.translation_byok_crypto)
        server_main.translation_svc = TranslationService(
            server_main.translation_store, server_main.store,
            byok=server_main.translation_byok_svc)
        self.client = TestClient(server_main.app)

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str) -> str:
        return self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"}
        ).json()["token"]


class ChuaDangNhapTest(ByokRouteTestCase):
    def test_moi_route_deu_doi_hoi_dang_nhap(self):
        r1 = self.client.get("/api/translate/provider-connections")
        r2 = self.client.post("/api/translate/provider-connections/groq",
                              json={"api_key": "gsk_x"})
        r3 = self.client.post("/api/translate/provider-connections/groq/test")
        r4 = self.client.delete("/api/translate/provider-connections/groq")
        for r in (r1, r2, r3, r4):
            self.assertEqual(r.status_code, 401)


class ConnectRouteTest(ByokRouteTestCase):
    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_ket_noi_thanh_cong_tra_metadata_an_toan(self, kiem_tra):
        token = self.user("a@vidu.vn")
        r = self.client.post(
            "/api/translate/provider-connections/groq",
            headers=self.auth(token), json={"api_key": "gsk_abcdefgh1234AB42"})
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()["connection"]
        self.assertEqual(body["last4"], "AB42")
        self.assertEqual(body["provider_id"], "groq")
        # Muc 2 (Part K) — plaintext KHONG BAO GIO tra ve qua API.
        self.assertNotIn("gsk_abcdefgh1234AB42", str(r.json()))
        self.assertNotIn("encrypted_secret", r.json()["connection"])
        self.assertNotIn("api_key", r.json()["connection"])

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_response_khong_bao_gio_chua_authorization_header_goc(self, kiem_tra):
        from server.translation_provider_registry import ConnectionCheckError
        kiem_tra.side_effect = ConnectionCheckError(
            "INVALID_KEY", "API key không hợp lệ.")
        token = self.user("a@vidu.vn")
        r = self.client.post(
            "/api/translate/provider-connections/groq",
            headers=self.auth(token), json={"api_key": "gsk_sai"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"]["code"], "INVALID_KEY")
        self.assertNotIn("gsk_sai", str(r.json()))
        self.assertNotIn("Authorization", str(r.json()))

    def test_provider_khong_ho_tro_tra_400(self):
        token = self.user("a@vidu.vn")
        r = self.client.post(
            "/api/translate/provider-connections/openai",
            headers=self.auth(token), json={"api_key": "sk_x"})
        self.assertEqual(r.status_code, 400)

    def test_key_rong_bi_tu_choi_boi_pydantic(self):
        token = self.user("a@vidu.vn")
        r = self.client.post(
            "/api/translate/provider-connections/groq",
            headers=self.auth(token), json={"api_key": ""})
        self.assertEqual(r.status_code, 422)

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_ma_loi_sach_cho_ca_bon_loai(self, kiem_tra):
        from server.translation_provider_registry import ConnectionCheckError
        token = self.user("a@vidu.vn")
        for ma, status_mong_doi in (
            ("INVALID_KEY", 400), ("RATE_LIMITED", 429),
            ("PROVIDER_UNAVAILABLE", 503), ("MODEL_UNAVAILABLE", 400),
        ):
            kiem_tra.side_effect = ConnectionCheckError(ma, "loi")
            r = self.client.post(
                "/api/translate/provider-connections/groq",
                headers=self.auth(token), json={"api_key": "gsk_x"})
            self.assertEqual(r.status_code, status_mong_doi, ma)
            self.assertEqual(r.json()["detail"]["code"], ma)


class ListDeleteRouteTest(ByokRouteTestCase):
    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_liet_ke_sau_khi_ket_noi(self, kiem_tra):
        token = self.user("a@vidu.vn")
        self.client.post("/api/translate/provider-connections/groq",
                         headers=self.auth(token), json={"api_key": "gsk_x0000AB42"})
        r = self.client.get("/api/translate/provider-connections",
                            headers=self.auth(token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total"], 1)
        self.assertEqual(r.json()["connections"][0]["last4"], "AB42")

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_xoa_roi_khong_con_trong_danh_sach(self, kiem_tra):
        token = self.user("a@vidu.vn")
        self.client.post("/api/translate/provider-connections/groq",
                         headers=self.auth(token), json={"api_key": "gsk_x0000AB42"})
        r = self.client.delete("/api/translate/provider-connections/groq",
                               headers=self.auth(token))
        self.assertEqual(r.status_code, 200)
        r2 = self.client.get("/api/translate/provider-connections",
                             headers=self.auth(token))
        self.assertEqual(r2.json()["total"], 0)

    def test_xoa_khi_chua_ket_noi_khong_loi(self):
        token = self.user("a@vidu.vn")
        r = self.client.delete("/api/translate/provider-connections/groq",
                               headers=self.auth(token))
        self.assertEqual(r.status_code, 200)


class TestConnectionRouteTest(ByokRouteTestCase):
    def test_kiem_tra_khi_chua_ket_noi_tra_404(self):
        token = self.user("a@vidu.vn")
        r = self.client.post("/api/translate/provider-connections/groq/test",
                             headers=self.auth(token))
        self.assertEqual(r.status_code, 404)


class OwnershipHttpTest(ByokRouteTestCase):
    """Muc 4/5/6 (Part K) o tang HTTP: nguoi dung B khong doc/xoa/dung duoc
    ket noi cua nguoi dung A qua BAT KY request nao, ke ca ID doan duoc."""

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def setUp(self, kiem_tra):
        super().setUp()
        self.token_a = self.user("a@vidu.vn")
        self.token_b = self.user("b@vidu.vn")
        self.client.post("/api/translate/provider-connections/groq",
                         headers=self.auth(self.token_a),
                         json={"api_key": "gsk_cua_a_00000CCCC"})

    def test_b_khong_thay_ket_noi_cua_a_trong_list(self):
        r = self.client.get("/api/translate/provider-connections",
                            headers=self.auth(self.token_b))
        self.assertEqual(r.json()["total"], 0)

    def test_b_test_connection_cua_a_tra_404_khong_phai_du_lieu_cua_a(self):
        r = self.client.post("/api/translate/provider-connections/groq/test",
                             headers=self.auth(self.token_b))
        self.assertEqual(r.status_code, 404)

    def test_b_xoa_khong_anh_huong_ket_noi_cua_a(self):
        r = self.client.delete("/api/translate/provider-connections/groq",
                               headers=self.auth(self.token_b))
        self.assertEqual(r.status_code, 200)  # idempotent, khong loi
        # Ket noi cua A VAN CON — B chi "xoa" duoc du lieu (khong ton tai)
        # cua CHINH B, khong dung toi ban ghi cua A.
        r2 = self.client.get("/api/translate/provider-connections",
                             headers=self.auth(self.token_a))
        self.assertEqual(r2.json()["total"], 1)

if __name__ == "__main__":
    unittest.main()
