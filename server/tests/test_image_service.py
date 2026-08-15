"""`server/image_service.py` — dieu phoi 3 che do, PHASE 5/14 (kich ban tich hop)."""

from __future__ import annotations

import unittest

import httpx

from server.image_byop_service import MockByopConnectionStore, PollinationsByopService
from server.image_byop_crypto import build_image_byop_crypto
from server.image_community_catalogue import CommunityCatalogueCache
from server.image_domain import GenerationStatus, PollinationsConnection
from server.image_provider_registry import (
    ImageProviderUnavailable,
    QuickFreeImageProvider,
    SharedPremiumImageProvider,
)
from server.image_service import (
    ByopNotConnected,
    CommunityModelNoLongerFree,
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


def _catalogue_gia(models_payload):
    """`models_payload`: list dict dung dinh dang that cua
    `GET https://gen.pollinations.ai/image/models`."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=models_payload)
    return CommunityCatalogueCache(http_client=_client_gia(handler))


def _dich_vu(
    *, wallet=None, shared_handler=None, quick_handler=None,
    guard=None, byop_store=None, byop_handler=None, community_catalogue=None,
    no_shared=False,
):
    wallet = wallet or MockWalletStore()
    quick = QuickFreeImageProvider(client=_client_gia(quick_handler or _anh_ok))
    shared = None if no_shared else SharedPremiumImageProvider(
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
        community_catalogue=community_catalogue or _catalogue_gia([]),
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


_MODEL_MIEN_PHI = {
    "name": "vendouple/free-test", "title": "Free Test",
    "output_modalities": ["image"],
    "pricing": {"currency": "pollen", "completionImageTokens": "0"},
}
_MODEL_TRA_PHI = {
    "name": "flux", "output_modalities": ["image"],
    "pricing": {"currency": "pollen", "completionImageTokens": "0.002"},
}


class CommunityFreeServiceTest(unittest.TestCase):
    def test_danh_sach_rong_that_thi_khong_the_sinh_anh(self):
        svc, _, _ = _dich_vu(community_catalogue=_catalogue_gia([_MODEL_TRA_PHI]))
        with self.assertRaises(CommunityModelNoLongerFree):
            svc.sinh_anh_cong_dong(
                user_id="u1", prompt="p", negative_prompt="", model_id="vendouple/free-test",
                aspect_ratio="1:1", quality="standard", idempotency_key="k1",
            )

    def test_model_dang_mien_phi_sinh_anh_thanh_cong_khong_tru_vi(self):
        svc, wallet, _ = _dich_vu(
            community_catalogue=_catalogue_gia([_MODEL_MIEN_PHI]),
        )
        anh = svc.sinh_anh_cong_dong(
            user_id="u1", prompt="p", negative_prompt="", model_id="vendouple/free-test",
            aspect_ratio="1:1", quality="standard", idempotency_key="k1",
        )
        self.assertEqual(anh.image.content, _ANH_GIA)
        self.assertEqual(wallet.lay_so_du("u1").available_micro, 0)
        self.assertEqual(anh.reservation.status, GenerationStatus.SUCCEEDED)
        self.assertEqual(anh.reservation.actual_cost_micro, 0)

    def test_model_bi_ru_khoi_danh_sach_thi_khong_tu_chuyen_sang_shared(self):
        """ADDENDUM: 'Never silently fall back from a free community model to
        a paid model' — model KHONG con trong danh sach (gia da doi/model bi
        go) phai bi CHAN, khong duoc am tham goi Shared Premium/tru tien."""
        goi_provider = []

        def shared_handler(request: httpx.Request) -> httpx.Response:
            goi_provider.append(1)
            return _anh_ok(request)

        svc, wallet, _ = _dich_vu(
            shared_handler=shared_handler,
            community_catalogue=_catalogue_gia([_MODEL_TRA_PHI]),  # KHONG co free-test
        )
        with self.assertRaises(CommunityModelNoLongerFree):
            svc.sinh_anh_cong_dong(
                user_id="u1", prompt="p", negative_prompt="", model_id="vendouple/free-test",
                aspect_ratio="1:1", quality="standard", idempotency_key="k1",
            )
        self.assertEqual(goi_provider, [])
        self.assertEqual(wallet.lay_so_du("u1").available_micro, 0)

    def test_danh_sach_khong_lay_duoc_thi_chan_sinh_anh(self):
        def loi(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        svc, _, _ = _dich_vu(community_catalogue=_catalogue_gia_loi(loi))
        with self.assertRaises(CommunityModelNoLongerFree):
            svc.sinh_anh_cong_dong(
                user_id="u1", prompt="p", negative_prompt="", model_id="vendouple/free-test",
                aspect_ratio="1:1", quality="standard", idempotency_key="k1",
            )

    def test_chua_cau_hinh_shared_premium_thi_bao_loi_ro_rang(self):
        svc, _, _ = _dich_vu(
            no_shared=True, community_catalogue=_catalogue_gia([_MODEL_MIEN_PHI]),
        )
        with self.assertRaises(Exception):
            svc.sinh_anh_cong_dong(
                user_id="u1", prompt="p", negative_prompt="", model_id="vendouple/free-test",
                aspect_ratio="1:1", quality="standard", idempotency_key="k1",
            )

    def test_catalogue_cong_dong_bao_available_false_khi_loi(self):
        def loi(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        svc, _, _ = _dich_vu(community_catalogue=_catalogue_gia_loi(loi))
        ket_qua = svc.catalogue_cong_dong()
        self.assertFalse(ket_qua["available"])
        self.assertEqual(ket_qua["models"], [])

    def test_catalogue_cong_dong_tra_danh_sach_da_loc(self):
        svc, _, _ = _dich_vu(
            community_catalogue=_catalogue_gia([_MODEL_MIEN_PHI, _MODEL_TRA_PHI]),
        )
        ket_qua = svc.catalogue_cong_dong()
        self.assertTrue(ket_qua["available"])
        self.assertEqual([m.model_id for m in ket_qua["models"]], ["vendouple/free-test"])


def _catalogue_gia_loi(handler):
    return CommunityCatalogueCache(http_client=_client_gia(handler))


if __name__ == "__main__":
    unittest.main()
