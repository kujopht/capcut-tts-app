"""`server/image_byop_service.py` — BYOP OAuth PKCE, PHASE 4C/14."""

from __future__ import annotations

import unittest

import httpx

from server.image_byop_crypto import build_image_byop_crypto
from server.image_byop_service import (
    ByopError,
    ByopExchangeFailed,
    ByopStateMismatch,
    MockByopConnectionStore,
    MockPendingAuthorizationStore,
    PollinationsByopService,
    tao_pkce,
    tao_state,
)

_MASTER_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="  # 32 byte base64 gia, CHI dung trong test


def _client_gia(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _crypto_gia():
    return build_image_byop_crypto({"IMAGE_BYOP_MASTER_KEY": _MASTER_KEY})


class PkceTest(unittest.TestCase):
    def test_verifier_va_challenge_khac_nhau_moi_lan(self):
        a = tao_pkce()
        b = tao_pkce()
        self.assertNotEqual(a.code_verifier, b.code_verifier)
        self.assertNotEqual(a.code_challenge, b.code_challenge)

    def test_khong_co_padding_base64url(self):
        p = tao_pkce()
        self.assertNotIn("=", p.code_challenge)
        self.assertNotIn("+", p.code_challenge)
        self.assertNotIn("/", p.code_challenge)

    def test_state_khac_nhau_moi_lan(self):
        self.assertNotEqual(tao_state(), tao_state())


class BatDauKetNoiTest(unittest.TestCase):
    def test_khong_co_crypto_thi_tu_choi(self):
        svc = PollinationsByopService(
            client_id="pk_test", redirect_uri="https://vidu.test/callback",
            crypto=None,
        )
        self.assertFalse(svc.enabled)
        with self.assertRaises(ByopError):
            svc.bat_dau_ket_noi(user_id="u1")

    def test_co_crypto_thi_tra_ve_url_dung_authorize_endpoint(self):
        svc = PollinationsByopService(
            client_id="pk_test", redirect_uri="https://vidu.test/callback",
            crypto=_crypto_gia(),
        )
        url = svc.bat_dau_ket_noi(user_id="u1")
        self.assertTrue(url.startswith("https://enter.pollinations.ai/authorize?"))
        self.assertIn("client_id=pk_test", url)
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn("scope=keys", url)
        # KHONG xin them scope khong can thiet.
        self.assertNotIn("profile", url)
        self.assertNotIn("usage", url)


class CallbackTest(unittest.TestCase):
    def _svc(self, handler=None, crypto=None):
        client = _client_gia(handler) if handler else None
        return PollinationsByopService(
            client_id="pk_test", redirect_uri="https://vidu.test/callback",
            crypto=crypto if crypto is not None else _crypto_gia(),
            http_client=client,
        )

    def test_state_sai_bi_tu_choi(self):
        svc = self._svc()
        svc.bat_dau_ket_noi(user_id="u1")
        with self.assertRaises(ByopStateMismatch):
            svc.xu_ly_callback(
                user_id="u1", state="state-gia-mao", code="abc",
                redirect_uri="https://vidu.test/callback",
            )

    def test_state_dung_nhung_khac_user_id_bi_tu_choi(self):
        svc = self._svc()
        url = svc.bat_dau_ket_noi(user_id="u1")
        state = _lay_query(url)["state"]
        with self.assertRaises(ByopStateMismatch):
            svc.xu_ly_callback(
                user_id="ke-gia-mao", state=state, code="abc",
                redirect_uri="https://vidu.test/callback",
            )

    def test_redirect_uri_khong_khop_bi_tu_choi(self):
        svc = self._svc()
        url = svc.bat_dau_ket_noi(user_id="u1")
        state = _lay_query(url)["state"]
        with self.assertRaises(ByopStateMismatch):
            svc.xu_ly_callback(
                user_id="u1", state=state, code="abc",
                redirect_uri="https://ke-gia-mao.test/callback",
            )

    def test_state_dung_mot_lan_roi_khong_dung_lai_duoc(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"access_token": "sk_fake", "scope": "keys"})

        svc = self._svc(handler)
        url = svc.bat_dau_ket_noi(user_id="u1")
        state = _lay_query(url)["state"]
        svc.xu_ly_callback(
            user_id="u1", state=state, code="abc", redirect_uri="https://vidu.test/callback")
        with self.assertRaises(ByopStateMismatch):
            svc.xu_ly_callback(
                user_id="u1", state=state, code="abc",
                redirect_uri="https://vidu.test/callback")

    def test_doi_code_thanh_cong_luu_token_da_ma_hoa(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers.get("content-type"),
                             "application/x-www-form-urlencoded")
            return httpx.Response(200, json={
                "access_token": "sk_real_secret_value", "refresh_token": "sk_refresh",
                "scope": "keys", "expires_in": 3600,
            })

        svc = self._svc(handler)
        url = svc.bat_dau_ket_noi(user_id="u1")
        state = _lay_query(url)["state"]
        conn = svc.xu_ly_callback(
            user_id="u1", state=state, code="abc", redirect_uri="https://vidu.test/callback")
        self.assertTrue(conn.active)
        # Token PLAINTEXT khong duoc xuat hien nguyen van trong ban ghi luu.
        self.assertNotIn("sk_real_secret_value", conn.encrypted_access_token)
        self.assertEqual(svc.giai_ma_access_token(conn), "sk_real_secret_value")

    def test_code_khong_hop_le_nem_loi_an_toan(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "invalid_grant"})

        svc = self._svc(handler)
        url = svc.bat_dau_ket_noi(user_id="u1")
        state = _lay_query(url)["state"]
        with self.assertRaises(ByopExchangeFailed):
            svc.xu_ly_callback(
                user_id="u1", state=state, code="het-han", redirect_uri="https://vidu.test/callback")

    def test_phan_hoi_thieu_access_token_nem_loi(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"scope": "keys"})

        svc = self._svc(handler)
        url = svc.bat_dau_ket_noi(user_id="u1")
        state = _lay_query(url)["state"]
        with self.assertRaises(ByopExchangeFailed):
            svc.xu_ly_callback(
                user_id="u1", state=state, code="abc", redirect_uri="https://vidu.test/callback")


class RevokeTest(unittest.TestCase):
    def test_ngat_ket_noi_xoa_token_va_dat_revoked_at(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"access_token": "sk_x", "scope": "keys"})

        svc = PollinationsByopService(
            client_id="pk_test", redirect_uri="https://vidu.test/callback",
            crypto=_crypto_gia(), http_client=_client_gia(handler),
        )
        url = svc.bat_dau_ket_noi(user_id="u1")
        state = _lay_query(url)["state"]
        svc.xu_ly_callback(user_id="u1", state=state, code="abc",
                          redirect_uri="https://vidu.test/callback")
        self.assertTrue(svc.trang_thai("u1").active)

        svc.ngat_ket_noi("u1")
        sau = svc.trang_thai("u1")
        self.assertFalse(sau.active)
        self.assertEqual(sau.encrypted_access_token, "")

    def test_ngat_ket_noi_khi_chua_tung_ket_noi_khong_loi(self):
        svc = PollinationsByopService(
            client_id="pk_test", redirect_uri="https://vidu.test/callback",
            crypto=_crypto_gia(),
        )
        self.assertIsNone(svc.ngat_ket_noi("chua-ket-noi"))


def _lay_query(url: str) -> dict:
    from urllib.parse import parse_qs, urlsplit
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


if __name__ == "__main__":
    unittest.main()
