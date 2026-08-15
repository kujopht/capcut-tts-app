"""`server/image_service.py` — dieu phoi 3 che do, PHASE 5/14 (kich ban tich hop)."""

from __future__ import annotations

import unittest

import httpx

from server.image_byop_service import MockByopConnectionStore, PollinationsByopService
from server.image_byop_crypto import build_image_byop_crypto
from server.image_domain import GenerationStatus, PollinationsConnection
from server.image_provider_registry import (
    ImageProviderUnavailable,
    QuickFreeImageProvider,
    SharedPremiumImageProvider,
)
from server.image_service import (
    ByopNotConnected,
    GenerationAlreadyProcessed,
    ImageStudioService,
    UnknownOrDisabledModel,
)
from server.image_spending_guard import SharedPremiumDisabled, SharedPremiumSpendingGuard
from server.image_wallet_store import InsufficientBalance, MockWalletStore

_ANH_GIA = b"\xff\xd8\xff\xe0fake-jpeg"
_MASTER_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


def _client_gia(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _anh_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=_ANH_GIA, headers={"content-type": "image/jpeg"})


def _dich_vu(
    *, wallet=None, shared_handler=None, quick_handler=None,
    guard=None, byop_store=None, byop_handler=None,
):
    wallet = wallet or MockWalletStore()
    quick = QuickFreeImageProvider(client=_client_gia(quick_handler or _anh_ok))
    shared = SharedPremiumImageProvider(
        api_key="sk-server-fake", client=_client_gia(shared_handler or _anh_ok))
    guard = guard or SharedPremiumSpendingGuard(
        monthly_budget_usd=1000.0, warning_budget_usd=900.0, max_concurrent=5)
    byop = PollinationsByopService(
        client_id="pk_test", redirect_uri="https://vidu.test/callback",
        crypto=build_image_byop_crypto({"IMAGE_BYOP_MASTER_KEY": _MASTER_KEY}),
        connection_store=byop_store,
    )
    return ImageStudioService(
        wallet_store=wallet, quick_free_provider=quick,
        shared_premium_provider=shared, byop_service=byop, spending_guard=guard,
        byop_http_client=_client_gia(byop_handler) if byop_handler else None,
    ), wallet, byop


class QuickFreeServiceTest(unittest.TestCase):
    def test_thanh_cong_khong_cham_vi(self):
        svc, wallet, _ = _dich_vu()
        anh = svc.sinh_anh_quick_free(prompt="a cat", aspect_ratio="1:1", client_ip="1.2.3.4")
        self.assertEqual(anh.content, _ANH_GIA)
        self.assertEqual(wallet.lay_so_du("bat_ky_ai").available_micro, 0)

    def test_provider_loi_truyen_thang_khong_fallback_shared(self):
        def loi(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        svc, _, _ = _dich_vu(quick_handler=loi)
        with self.assertRaises(ImageProviderUnavailable):
            svc.sinh_anh_quick_free(prompt="a", aspect_ratio="1:1", client_ip="1.1.1.1")


class SharedPremiumServiceTest(unittest.TestCase):
    def test_thieu_tien_bao_loi_khong_goi_provider(self):
        goi_provider = []

        def handler(request: httpx.Request) -> httpx.Response:
            goi_provider.append(1)
            return httpx.Response(200, content=_ANH_GIA, headers={"content-type": "image/jpeg"})

        svc, wallet, _ = _dich_vu(shared_handler=handler)
        with self.assertRaises(InsufficientBalance):
            svc.sinh_anh_shared_premium(
                user_id="u1", prompt="p", negative_prompt="", model_id="flux",
                aspect_ratio="1:1", quality="standard", idempotency_key="idem-1",
            )
        self.assertEqual(len(goi_provider), 0)

    def test_thanh_cong_tru_vi_va_tra_anh(self):
        svc, wallet, _ = _dich_vu()
        wallet.nap_tien_test("u1", 100_00, idempotency_key="topup-1")
        ket_qua = svc.sinh_anh_shared_premium(
            user_id="u1", prompt="p", negative_prompt="", model_id="flux",
            aspect_ratio="1:1", quality="standard", idempotency_key="idem-1",
        )
        self.assertEqual(ket_qua.image.content, _ANH_GIA)
        self.assertEqual(ket_qua.reservation.status, GenerationStatus.SUCCEEDED)
        self.assertLess(wallet.lay_so_du("u1").available_micro, 100_00)

    def test_provider_loi_thi_hoan_tien_toan_bo(self):
        def loi(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        svc, wallet, _ = _dich_vu(shared_handler=loi)
        wallet.nap_tien_test("u1", 100_00, idempotency_key="topup-1")
        with self.assertRaises(ImageProviderUnavailable):
            svc.sinh_anh_shared_premium(
                user_id="u1", prompt="p", negative_prompt="", model_id="flux",
                aspect_ratio="1:1", quality="standard", idempotency_key="idem-1",
            )
        self.assertEqual(wallet.lay_so_du("u1").available_micro, 100_00)

    def test_model_khong_ton_tai_bao_loi(self):
        svc, wallet, _ = _dich_vu()
        wallet.nap_tien_test("u1", 100_00, idempotency_key="topup-1")
        with self.assertRaises(UnknownOrDisabledModel):
            svc.sinh_anh_shared_premium(
                user_id="u1", prompt="p", negative_prompt="", model_id="model-la",
                aspect_ratio="1:1", quality="standard", idempotency_key="idem-1",
            )

    def test_cung_idempotency_key_lan_hai_tra_lai_anh_da_cache_khong_goi_provider_lai(self):
        so_lan_goi = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            so_lan_goi["n"] += 1
            return httpx.Response(200, content=_ANH_GIA, headers={"content-type": "image/jpeg"})

        svc, wallet, _ = _dich_vu(shared_handler=handler)
        wallet.nap_tien_test("u1", 100_00, idempotency_key="topup-1")
        r1 = svc.sinh_anh_shared_premium(
            user_id="u1", prompt="p", negative_prompt="", model_id="flux",
            aspect_ratio="1:1", quality="standard", idempotency_key="idem-1",
        )
        r2 = svc.sinh_anh_shared_premium(
            user_id="u1", prompt="p", negative_prompt="", model_id="flux",
            aspect_ratio="1:1", quality="standard", idempotency_key="idem-1",
        )
        self.assertEqual(so_lan_goi["n"], 1)  # KHONG goi provider lan hai
        self.assertEqual(r1.image.content, r2.image.content)
        # KHONG tru tien lan hai — so du sau lan 2 phai bang sau lan 1.
        so_du_sau_1 = wallet.lay_so_du("u1").available_micro
        r3 = svc.sinh_anh_shared_premium(
            user_id="u1", prompt="p", negative_prompt="", model_id="flux",
            aspect_ratio="1:1", quality="standard", idempotency_key="idem-1",
        )
        self.assertEqual(wallet.lay_so_du("u1").available_micro, so_du_sau_1)

    def test_kill_switch_khoa_shared_premium_khong_giu_tien(self):
        guard = SharedPremiumSpendingGuard(
            monthly_budget_usd=1000.0, warning_budget_usd=900.0, max_concurrent=5)
        guard.dat_kill_switch(True)
        svc, wallet, _ = _dich_vu(guard=guard)
        wallet.nap_tien_test("u1", 100_00, idempotency_key="topup-1")
        with self.assertRaises(SharedPremiumDisabled):
            svc.sinh_anh_shared_premium(
                user_id="u1", prompt="p", negative_prompt="", model_id="flux",
                aspect_ratio="1:1", quality="standard", idempotency_key="idem-1",
            )
        self.assertEqual(wallet.lay_so_du("u1").available_micro, 100_00)

    def test_vuot_han_muc_dong_thoi_bao_loi(self):
        guard = SharedPremiumSpendingGuard(
            monthly_budget_usd=1000.0, warning_budget_usd=900.0, max_concurrent=1)
        guard.bat_dau_request()  # chiem cho truoc, mo phong mot request khac dang chay
        svc, wallet, _ = _dich_vu(guard=guard)
        wallet.nap_tien_test("u1", 100_00, idempotency_key="topup-1")
        with self.assertRaises(SharedPremiumDisabled):
            svc.sinh_anh_shared_premium(
                user_id="u1", prompt="p", negative_prompt="", model_id="flux",
                aspect_ratio="1:1", quality="standard", idempotency_key="idem-1",
            )


class ByopServiceTest(unittest.TestCase):
    def test_chua_ket_noi_bao_loi(self):
        svc, _, _ = _dich_vu()
        with self.assertRaises(ByopNotConnected):
            svc.sinh_anh_byop(
                user_id="u1", prompt="p", negative_prompt="", model_id="flux",
                aspect_ratio="1:1", quality="standard",
            )

    def test_da_ket_noi_thi_dung_token_ca_nhan_khong_cham_vi(self):
        crypto = build_image_byop_crypto({"IMAGE_BYOP_MASTER_KEY": _MASTER_KEY})
        store = MockByopConnectionStore()
        conn = PollinationsConnection(
            user_id="u1",
            encrypted_access_token=crypto.ma_hoa(
                "sk_ca_nhan", user_id="u1", provider_id="pollinations_byop"),
        )
        store.luu(conn)

        ghi_nhan = {}

        def handler(request: httpx.Request) -> httpx.Response:
            ghi_nhan["auth"] = request.headers.get("authorization")
            return httpx.Response(200, content=_ANH_GIA, headers={"content-type": "image/jpeg"})

        svc, wallet, _ = _dich_vu(byop_store=store, byop_handler=handler)
        anh = svc.sinh_anh_byop(
            user_id="u1", prompt="p", negative_prompt="", model_id="flux",
            aspect_ratio="1:1", quality="standard",
        )
        self.assertEqual(anh.content, _ANH_GIA)
        # Dung DUNG token ca nhan (khong phai khoa server dung chung).
        self.assertEqual(ghi_nhan["auth"], "Bearer sk_ca_nhan")
        self.assertEqual(wallet.lay_so_du("u1").available_micro, 0)  # khong cham vi

    def test_ket_noi_da_bi_ngat_thi_coi_nhu_chua_ket_noi(self):
        crypto = build_image_byop_crypto({"IMAGE_BYOP_MASTER_KEY": _MASTER_KEY})
        store = MockByopConnectionStore()
        conn = PollinationsConnection(
            user_id="u1",
            encrypted_access_token=crypto.ma_hoa(
                "sk_ca_nhan", user_id="u1", provider_id="pollinations_byop"),
        )
        store.luu(conn)
        store.ngat_ket_noi("u1")

        svc, _, _ = _dich_vu(byop_store=store)
        with self.assertRaises(ByopNotConnected):
            svc.sinh_anh_byop(
                user_id="u1", prompt="p", negative_prompt="", model_id="flux",
                aspect_ratio="1:1", quality="standard",
            )


if __name__ == "__main__":
    unittest.main()
