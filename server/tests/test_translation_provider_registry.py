"""
`server/translation_provider_registry.py` — Part Q1-Q7.

Fixture GIA (khong can credential that, dung `httpx.MockTransport` — cung
mau voi `test_translation_providers.py`) mo phong: phan hoi binh thuong, 429
co `Retry-After`, 429 khong header, het han muc (chua "quota" trong than
loi), timeout mang, phuc hoi sau khi het thoi gian cho.
"""

from __future__ import annotations

import unittest

import httpx

from server.translation_providers import TranslationContext, TranslationProviderError
from server.translation_provider_registry import (
    AllProvidersUnavailable,
    CloudflareWorkersAIProvider,
    ConfiguredProvider,
    GroqProvider,
    ProviderCatalogEntry,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderRegistry,
    ProviderStatus,
    build_provider_registry,
)


def _client_gia(handler):
    return httpx.Client(base_url="https://vidu.test",
                        transport=httpx.MockTransport(handler))


def _tra_loi_chat(noi_dung: str, *, status_code: int = 200,
                  headers=None) -> httpx.Response:
    return httpx.Response(status_code,
                          json={"choices": [{"message": {"content": noi_dung}}]},
                          headers=headers or {})


class GroqProviderTest(unittest.TestCase):
    def test_phan_hoi_binh_thuong(self):
        p = GroqProvider(api_key="k", model="qwen",
                         client=_client_gia(lambda r: _tra_loi_chat("Xin chào")))
        ra = p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Xin chào")

    def test_429_co_retry_after_thanh_rate_limited(self):
        p = GroqProvider(api_key="k", model="qwen", client=_client_gia(
            lambda r: httpx.Response(429, text="too many requests",
                                     headers={"retry-after": "30"})))
        with self.assertRaises(ProviderRateLimited) as ctx:
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertTrue(ctx.exception.retry_at)  # co moc ISO, khong rong

    def test_429_khong_header_van_la_rate_limited_nhung_khong_bia_moc(self):
        p = GroqProvider(api_key="k", model="qwen", client=_client_gia(
            lambda r: httpx.Response(429, text="rate limited")))
        with self.assertRaises(ProviderRateLimited) as ctx:
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ctx.exception.retry_at, "")

    def test_429_chua_tu_quota_thanh_quota_exhausted(self):
        p = GroqProvider(api_key="k", model="qwen", client=_client_gia(
            lambda r: httpx.Response(429, text="daily quota exceeded")))
        with self.assertRaises(ProviderQuotaExhausted):
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))

    def test_timeout_mang_thanh_loi_chung(self):
        def handler(request):
            raise httpx.ConnectTimeout("timeout", request=request)

        p = GroqProvider(api_key="k", model="qwen", client=_client_gia(handler))
        with self.assertRaises(TranslationProviderError):
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))

    def test_thieu_cau_hinh_nem_loi_ngay_luc_tao(self):
        with self.assertRaises(TranslationProviderError):
            GroqProvider(api_key="", model="qwen")


class CloudflareProviderTest(unittest.TestCase):
    def test_phan_hoi_binh_thuong(self):
        p = CloudflareWorkersAIProvider(
            account_id="acc", api_token="tok", model="@cf/qwen",
            client=_client_gia(lambda r: httpx.Response(
                200, json={"success": True, "result": {"response": "Xin chào"}})))
        ra = p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Xin chào")

    def test_429_thanh_rate_limited(self):
        p = CloudflareWorkersAIProvider(
            account_id="acc", api_token="tok", model="@cf/qwen",
            client=_client_gia(lambda r: httpx.Response(
                429, text="rate limited", headers={"retry-after": "60"})))
        with self.assertRaises(ProviderRateLimited):
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))

    def test_success_false_thanh_loi(self):
        p = CloudflareWorkersAIProvider(
            account_id="acc", api_token="tok", model="@cf/qwen",
            client=_client_gia(lambda r: httpx.Response(
                200, json={"success": False, "errors": ["model unavailable"]})))
        with self.assertRaises(TranslationProviderError):
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))


class _FakeInnerProvider:
    """Provider gia CO THE cau hinh tra loi/loi theo kich ban — dung de kiem
    `ConfiguredProvider`/`ProviderRegistry` ma khong dung lop HTTP that."""

    name = "fake"

    def __init__(self, kich_ban):
        self._kich_ban = list(kich_ban)
        self.so_lan_goi = 0

    def translate_segment(self, text, *, context):
        self.so_lan_goi += 1
        hanh_dong = self._kich_ban.pop(0) if self._kich_ban else "ok"
        if hanh_dong == "ok":
            return f"[{self.name}] {text}"
        raise hanh_dong  # hanh_dong la MOT exception instance


def _cp(provider_id, kich_ban, free_tier=True):
    return ConfiguredProvider(
        provider_id=provider_id, model_id=f"{provider_id}-model",
        display_name=provider_id, quality_hint="test",
        provider=_FakeInnerProvider(kich_ban), free_tier=free_tier)


class ConfiguredProviderStatusTest(unittest.TestCase):
    def test_thanh_cong_thanh_available(self):
        cp = _cp("a", ["ok"])
        cp.translate_segment("x", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(cp.catalog_entry().status, ProviderStatus.AVAILABLE)

    def test_rate_limited_khoa_den_moc_reset(self):
        cp = _cp("a", [ProviderRateLimited("cham", retry_at="2999-01-01T00:00:00+00:00")])
        with self.assertRaises(ProviderRateLimited):
            cp.translate_segment("x", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(cp.catalog_entry().status, ProviderStatus.RATE_LIMITED)
        self.assertFalse(cp.is_available_now())

    def test_qua_moc_reset_thi_lai_dung_duoc(self):
        cp = _cp("a", [ProviderRateLimited("cham", retry_at="2000-01-01T00:00:00+00:00")])
        with self.assertRaises(ProviderRateLimited):
            cp.translate_segment("x", context=TranslationContext(vai_tro="translator"))
        self.assertTrue(cp.is_available_now())  # moc da qua


class ProviderCatalogSafetyTest(unittest.TestCase):
    def test_to_dict_khong_lo_bat_ky_thong_tin_bi_mat_nao(self):
        entry = ProviderCatalogEntry(
            provider_id="groq", model_id="qwen", display_name="Qwen · Groq",
            quality_hint="nhanh", free_tier=True, status=ProviderStatus.AVAILABLE)
        d = entry.to_dict()
        chuoi = str(d).lower()
        for tu_cam in ("key", "token", "secret", "authorization"):
            self.assertNotIn(tu_cam, chuoi)


class ProviderRegistryModeTest(unittest.TestCase):
    def setUp(self):
        self.a = _cp("a", [TranslationProviderError("het han muc a")])
        self.b = _cp("b", ["ok"])
        self.c = _cp("c", ["ok"])
        self.reg = ProviderRegistry([self.a, self.b, self.c])

    def test_registry_rong_nem_all_unavailable(self):
        with self.assertRaises(AllProvidersUnavailable):
            ProviderRegistry([]).translate_segment(
                "x", context=TranslationContext(vai_tro="translator"))

    def test_auto_thu_lan_luot_den_khi_thanh_cong(self):
        ra, prov = self.reg.translate_segment(
            "x", context=TranslationContext(vai_tro="translator"), mode="auto")
        self.assertEqual(prov.provider_id, "b")  # a loi, b thanh cong

    def test_manual_khong_fallback_loi_ngay_khong_thu_provider_khac(self):
        with self.assertRaises(AllProvidersUnavailable):
            self.reg.translate_segment(
                "x", context=TranslationContext(vai_tro="translator"),
                mode="manual", selected_provider_id="a", allow_fallback=False)
        self.assertEqual(self.b.provider.so_lan_goi, 0)
        self.assertEqual(self.c.provider.so_lan_goi, 0)

    def test_manual_co_fallback_thu_provider_mien_phi_khac(self):
        ra, prov = self.reg.translate_segment(
            "x", context=TranslationContext(vai_tro="translator"),
            mode="manual", selected_provider_id="a", allow_fallback=True)
        self.assertEqual(prov.provider_id, "b")

    def test_tat_ca_that_bai_nem_all_unavailable(self):
        reg = ProviderRegistry([
            _cp("x", [TranslationProviderError("loi 1")]),
            _cp("y", [TranslationProviderError("loi 2")]),
        ])
        with self.assertRaises(AllProvidersUnavailable):
            reg.translate_segment("x", context=TranslationContext(vai_tro="translator"))

    def test_khong_bao_gio_dua_provider_tra_phi_vao_duong_thu(self):
        tra_phi = _cp("paid", ["ok"], free_tier=False)
        reg = ProviderRegistry([tra_phi])
        self.assertFalse(bool(reg))  # loc het, rong


class BuildProviderRegistryTest(unittest.TestCase):
    def test_moi_truong_rong_tra_registry_rong(self):
        reg = build_provider_registry(env={})
        self.assertFalse(bool(reg))

    def test_groq_du_bien_thi_co_mat(self):
        reg = build_provider_registry(env={
            "GROQ_API_KEY": "k", "GROQ_MODEL": "qwen-vi",
        })
        ids = [e.provider_id for e in reg.catalog()]
        self.assertIn("groq", ids)

    def test_thieu_mot_bien_cloudflare_thi_khong_dua_vao(self):
        reg = build_provider_registry(env={
            "CLOUDFLARE_ACCOUNT_ID": "acc",
            "CLOUDFLARE_API_TOKEN": "tok",
            # thieu CLOUDFLARE_WORKERS_AI_MODEL
        })
        self.assertFalse(bool(reg))

    def test_custom_provider_mac_dinh_khong_duoc_coi_la_mien_phi(self):
        reg = build_provider_registry(env={
            "TRANSLATION_BASE_URL": "https://vidu.test",
            "TRANSLATION_API_KEY": "k",
            "TRANSLATION_MODEL": "m",
        })
        # Khong danh dau TRANSLATION_CUSTOM_PROVIDER_FREE=true va khong bat
        # TRANSLATION_ALLOW_PAID_PROVIDER -> KHONG duoc dua vao registry.
        self.assertFalse(bool(reg))

    def test_custom_provider_danh_dau_mien_phi_thi_duoc_dua_vao(self):
        reg = build_provider_registry(env={
            "TRANSLATION_BASE_URL": "https://vidu.test",
            "TRANSLATION_API_KEY": "k",
            "TRANSLATION_MODEL": "m",
            "TRANSLATION_CUSTOM_PROVIDER_FREE": "true",
        })
        self.assertTrue(bool(reg))

    def test_allow_paid_provider_false_loc_provider_tra_phi(self):
        reg = build_provider_registry(env={
            "TRANSLATION_BASE_URL": "https://vidu.test",
            "TRANSLATION_API_KEY": "k",
            "TRANSLATION_MODEL": "m",
            "TRANSLATION_ALLOW_PAID_PROVIDER": "false",
        })
        self.assertFalse(bool(reg))


if __name__ == "__main__":
    unittest.main()
