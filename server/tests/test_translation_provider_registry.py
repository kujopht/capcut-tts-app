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
    ConnectionCheckError,
    GroqProvider,
    ProviderCatalogEntry,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderRegistry,
    ProviderStatus,
    build_provider_registry,
    kiem_tra_ket_noi_groq,
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

    def test_yeu_cau_groq_an_khoi_suy_luan_o_nguon(self):
        """Phat hien THAT qua kiem thu song voi Groq that (qwen/qwen3.6-27b
        la model "reasoning"): phai gui `reasoning_format=hidden`."""
        than_gui = {}

        def handler(request):
            than_gui.update(__import__("json").loads(request.content))
            return _tra_loi_chat("Xin chào")

        p = GroqProvider(api_key="k", model="qwen", client=_client_gia(handler))
        p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(than_gui.get("reasoning_format"), "hidden")

    def test_gui_max_tokens_du_lon_cho_model_reasoning(self):
        """Phat hien THAT qua kiem thu song: khong dat `max_tokens` du lon,
        model danh gan het ngan sach cho suy luan noi bo va cat ngang TRUOC
        khi kip viet cau tra loi — API tra 200 nhung content RONG (khong
        phai loi, khong phai 429). Da do duoc voi mot cau ngan don gian (3793/
        4096 token la suy luan). Khoa lai: PHAI gui `max_tokens` du lon."""
        than_gui = {}

        def handler(request):
            than_gui.update(__import__("json").loads(request.content))
            return _tra_loi_chat("Xin chào")

        p = GroqProvider(api_key="k", model="qwen", client=_client_gia(handler))
        p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertIsInstance(than_gui.get("max_tokens"), int)
        self.assertGreaterEqual(than_gui.get("max_tokens"), 2048)

    def test_loc_khoi_think_neu_model_van_tra_ve(self):
        """RAO CHAN CUOI: du da yeu cau `reasoning_format=hidden`, mot model/
        phien ban khong tuan thu van khong duoc phep lam hong ban dich —
        loi thu THAT tung xay ra voi qwen/qwen3.6-27b luc kiem thu song."""
        p = GroqProvider(api_key="k", model="qwen", client=_client_gia(
            lambda r: _tra_loi_chat(
                "<think>\nSuy nghĩ nội bộ dài dòng ở đây...\n</think>\n\n"
                "Tiêu Viêm nhìn về phía Dược Lão.")))
        ra = p.translate_segment("萧炎看向药老。",
                                 context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Tiêu Viêm nhìn về phía Dược Lão.")
        self.assertNotIn("<think>", ra)

    def test_content_toan_khoi_think_sau_loc_thanh_rong_nem_loi(self):
        """Khac voi test tren (con cau tra loi SAU khoi think): o day content
        CHI la khoi think, khong con gi sau khi loc — PHAI nem loi ro rang,
        KHONG DUOC coi chuoi rong la mot ban dich thanh cong (mot ban dich
        rong lam mat noi dung ma khong ai biet — dung nguyen tac chung cua
        `TranslationProvider.translate_segment`)."""
        p = GroqProvider(api_key="k", model="qwen", client=_client_gia(
            lambda r: _tra_loi_chat(
                "<think>\nSuy nghĩ dài dòng nhưng KHÔNG BAO GIỜ kết luận...\n</think>")))
        with self.assertRaises(TranslationProviderError):
            p.translate_segment("萧炎看向药老。",
                               context=TranslationContext(vai_tro="translator"))

    def test_content_rong_that_do_bi_cat_ngang_nem_loi_ro_rang(self):
        """Kich ban THAT tung gap khi kiem thu song: model bi cat ngang GIUA
        CHUNG suy luan (het `max_tokens` truoc khi kip viet cau tra loi) —
        API tra 200 nhung `message.content` la CHUOI RONG tu dau (khong co
        khoi think nao de loc). Phai nem loi, khong duoc coi la thanh cong."""
        p = GroqProvider(api_key="k", model="qwen", client=_client_gia(
            lambda r: _tra_loi_chat("")))
        with self.assertRaises(TranslationProviderError) as ctx:
            p.translate_segment("萧炎看向药老。",
                               context=TranslationContext(vai_tro="translator"))
        self.assertIn("rỗng", str(ctx.exception))


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


class TranslateWithPersonalTest(unittest.TestCase):
    """V5.1 Part F — thu tu shared/personal, tich hop TUY CHON (khong pha
    hanh vi cu khi khong co danh sach ca nhan)."""

    def setUp(self):
        self.shared_ok = _cp("shared-groq", ["ok"])
        self.reg = ProviderRegistry([self.shared_ok])

    def test_khong_co_personal_hanh_vi_y_het_translate_segment(self):
        ra, prov = self.reg.translate_segment_with_personal(
            "x", context=TranslationContext(vai_tro="translator"),
            personal_providers=None)
        self.assertEqual(prov.provider_id, "shared-groq")
        self.assertEqual(prov.credential_source, "shared")

    def test_mac_dinh_shared_truoc_personal_sau(self):
        ca_nhan = _cp("personal-groq", ["ok"], free_tier=True)
        ca_nhan.credential_source = "personal"
        ra, prov = self.reg.translate_segment_with_personal(
            "x", context=TranslationContext(vai_tro="translator"),
            personal_providers=[ca_nhan])
        # Shared thanh cong ngay -> khong bao gio cham toi personal.
        self.assertEqual(prov.provider_id, "shared-groq")
        self.assertEqual(prov.credential_source, "shared")

    def test_shared_that_bai_fallback_sang_personal(self):
        reg = ProviderRegistry([_cp("shared-groq", [TranslationProviderError("het han muc")])])
        ca_nhan = _cp("personal-groq", ["ok"])
        ca_nhan.credential_source = "personal"
        ra, prov = reg.translate_segment_with_personal(
            "x", context=TranslationContext(vai_tro="translator"),
            personal_providers=[ca_nhan])
        self.assertEqual(prov.provider_id, "personal-groq")
        self.assertEqual(prov.credential_source, "personal")

    def test_prefer_personal_thu_ca_nhan_truoc(self):
        ca_nhan = _cp("personal-groq", ["ok"])
        ca_nhan.credential_source = "personal"
        ra, prov = self.reg.translate_segment_with_personal(
            "x", context=TranslationContext(vai_tro="translator"),
            personal_providers=[ca_nhan], prefer_personal=True)
        self.assertEqual(prov.provider_id, "personal-groq")
        # shared khong duoc goi vi personal da thanh cong.
        self.assertEqual(self.shared_ok.provider.so_lan_goi, 0)

    def test_ca_hai_that_bai_nem_all_unavailable(self):
        reg = ProviderRegistry([_cp("shared-groq", [TranslationProviderError("x")])])
        ca_nhan = _cp("personal-groq", [TranslationProviderError("y")])
        with self.assertRaises(AllProvidersUnavailable):
            reg.translate_segment_with_personal(
                "x", context=TranslationContext(vai_tro="translator"),
                personal_providers=[ca_nhan])

    def test_khong_bao_gio_tron_provider_cua_nguoi_khac(self):
        """Ham nay KHONG tu tra cuu personal provider — no CHI dung DUNG
        danh sach duoc truyen vao. Day la bang chung cau truc: khong co
        duong nao de mot provider ca nhan cua nguoi dung KHAC lot vao neu
        tang goi (service) khong tu the truyen no vao."""
        ra, prov = self.reg.translate_segment_with_personal(
            "x", context=TranslationContext(vai_tro="translator"),
            personal_providers=[])  # danh sach RONG mo phong "khong ket noi"
        self.assertEqual(prov.credential_source, "shared")


class KiemTraKetNoiGroqTest(unittest.TestCase):
    def _client(self, handler):
        return httpx.Client(base_url="https://vidu.test",
                            transport=httpx.MockTransport(handler))

    def test_key_hop_le_va_model_co_san_thanh_cong(self):
        def handler(request):
            return httpx.Response(200, json={"data": [{"id": "qwen/qwen3.6-27b"}]})

        kiem_tra_ket_noi_groq("gsk_hop_le", "qwen/qwen3.6-27b",
                             client=self._client(handler))  # khong nem gi

    def test_401_thanh_invalid_key(self):
        with self.assertRaises(ConnectionCheckError) as ctx:
            kiem_tra_ket_noi_groq("gsk_sai", "m", client=self._client(
                lambda r: httpx.Response(401, json={"error": "unauthorized"})))
        self.assertEqual(ctx.exception.code, "INVALID_KEY")

    def test_429_thanh_rate_limited(self):
        with self.assertRaises(ConnectionCheckError) as ctx:
            kiem_tra_ket_noi_groq("gsk_x", "m", client=self._client(
                lambda r: httpx.Response(429, text="rate limited")))
        self.assertEqual(ctx.exception.code, "RATE_LIMITED")

    def test_model_khong_co_trong_danh_sach_thanh_model_unavailable(self):
        with self.assertRaises(ConnectionCheckError) as ctx:
            kiem_tra_ket_noi_groq("gsk_hop_le", "model-khong-ton-tai",
                                 client=self._client(lambda r: httpx.Response(
                                     200, json={"data": [{"id": "model-khac"}]})))
        self.assertEqual(ctx.exception.code, "MODEL_UNAVAILABLE")

    def test_loi_mang_thanh_provider_unavailable(self):
        def handler(request):
            raise httpx.ConnectTimeout("timeout", request=request)

        with self.assertRaises(ConnectionCheckError) as ctx:
            kiem_tra_ket_noi_groq("gsk_x", "m", client=self._client(handler))
        self.assertEqual(ctx.exception.code, "PROVIDER_UNAVAILABLE")

    def test_loi_khong_bao_gio_kem_header_goc(self):
        """`str(exc)` (thong diep tieng Viet hien cho nguoi dung) KHONG BAO
        GIO chua noi dung response goc cua Groq — chi ma loi SACH."""
        with self.assertRaises(ConnectionCheckError) as ctx:
            kiem_tra_ket_noi_groq("gsk_x", "m", client=self._client(
                lambda r: httpx.Response(
                    401, json={"error": {"message": "RẤT BÍ MẬT NỘI BỘ"}})))
        self.assertNotIn("RẤT BÍ MẬT NỘI BỘ", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
