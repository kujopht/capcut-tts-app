"""
Pollinations.ai — nha cung cap dich CHINH (feature/pollinations-translation).

Cung mau fixture voi `test_translation_provider_registry.py`
(`httpx.MockTransport`, khong goi mang that). Ba nhom test:

  - `PollinationsProviderTest`      — MOT provider doc lap (thanh cong, 429,
    timeout + thu lai cuc bo, phan hoi sai hinh dang, thieu cau hinh).
  - `PollinationsFallbackChainTest` — CA CHUOI qua `ProviderRegistry`:
    deepseek that bai -> deepseek-pro, Pollinations that bai het -> Groq,
    dinh tuyen AUTO theo vai tro KHONG dao nguoc uu tien Pollinations-truoc.
  - `BuildRegistryPollinationsTest` — `build_provider_registry` doc dung bien
    moi truong, thieu POLLINATIONS_API_KEY thi Groq-only van chay binh
    thuong (hoi quy), uu tien co the doi qua TRANSLATION_PROVIDER_PRIORITY.
"""

from __future__ import annotations

import json
import unittest

import httpx

from server.translation_model_profiles import GROQ_MODEL_PROFILES
from server.translation_providers import TranslationContext, TranslationProviderError
from server.translation_provider_registry import (
    AllProvidersUnavailable,
    ConfiguredProvider,
    ConnectionCheckError,
    GroqProvider,
    PollinationsProvider,
    ProviderAccountError,
    ProviderRateLimited,
    ProviderRegistry,
    ProviderTransientError,
    build_provider_registry,
    kiem_tra_ket_noi_pollinations,
)

_QWEN = GROQ_MODEL_PROFILES["qwen"]


def _client_gia(handler):
    return httpx.Client(base_url="https://vidu.test",
                        transport=httpx.MockTransport(handler))


def _tra_loi_chat(noi_dung: str, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code,
                          json={"choices": [{"message": {"content": noi_dung}}]})


class PollinationsProviderTest(unittest.TestCase):
    def test_dich_thanh_cong(self):
        p = PollinationsProvider(
            api_key="sk_vidu", model="deepseek",
            client=_client_gia(lambda r: _tra_loi_chat("Xin chào")))
        ra = p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Xin chào")

    def test_dung_dung_base_url_va_model_mac_dinh(self):
        than_gui = {}
        duong_dan = {}

        def handler(request):
            than_gui.update(json.loads(request.content))
            duong_dan["url"] = str(request.url)
            return _tra_loi_chat("ok")

        p = PollinationsProvider(api_key="sk_vidu", model="deepseek",
                                 client=_client_gia(handler))
        p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(than_gui.get("model"), "deepseek")
        self.assertIn("/chat/completions", duong_dan["url"])

    def test_dung_nhiet_do_thap_khong_sang_tao(self):
        """Yeu cau goc: 'use a low/non-creative translation temperature'."""
        than_gui = {}

        def handler(request):
            than_gui.update(json.loads(request.content))
            return _tra_loi_chat("ok")

        p = PollinationsProvider(api_key="sk_vidu", model="deepseek",
                                 client=_client_gia(handler))
        p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertLessEqual(than_gui.get("temperature"), 0.3)

    def test_thieu_api_key_nem_loi_ngay_luc_tao(self):
        with self.assertRaises(TranslationProviderError):
            PollinationsProvider(api_key="", model="deepseek")

    def test_thieu_model_nem_loi_ngay_luc_tao(self):
        with self.assertRaises(TranslationProviderError):
            PollinationsProvider(api_key="sk_vidu", model="")

    def test_429_thanh_rate_limited(self):
        p = PollinationsProvider(api_key="sk_vidu", model="deepseek", client=_client_gia(
            lambda r: httpx.Response(429, text="too many requests")))
        with self.assertRaises(ProviderRateLimited):
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))

    def test_phan_hoi_sai_hinh_dang_nem_loi_ro_rang(self):
        """'malformed response' — JSON hop le nhung thieu truong mong doi."""
        p = PollinationsProvider(api_key="sk_vidu", model="deepseek", client=_client_gia(
            lambda r: httpx.Response(200, json={"khong_phai": "cau_truc_dung"})))
        with self.assertRaises(TranslationProviderError):
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))

    def test_noi_dung_rong_nem_loi_khong_coi_la_thanh_cong(self):
        p = PollinationsProvider(api_key="sk_vidu", model="deepseek",
                                 client=_client_gia(lambda r: _tra_loi_chat("")))
        with self.assertRaises(TranslationProviderError):
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))

    def test_het_so_du_402_nem_loi_ro_rang(self):
        """Kich ban THAT gap khi kiem thu song voi Pollinations that (tai
        khoan chua nap 'pollen'): 402 kem `PAYMENT_REQUIRED` — day la mot
        `ProviderAccountError` RO RANG (Phan refactor dinh tuyen theo pham
        vi loi, muc PROVIDER/ACCOUNT), khong phai `ProviderRateLimited`,
        khong bao gio bi coi la thanh cong."""
        than_that = ('{"success":false,"error":{"message":"Insufficient '
                    'balance. This request costs ~0.0021 pollen, but your '
                    'available balance is 0.0000.","code":"PAYMENT_REQUIRED"'
                    '}}')
        p = PollinationsProvider(api_key="sk_vidu", model="deepseek", client=_client_gia(
            lambda r: httpx.Response(402, text=than_that)))
        with self.assertRaises(ProviderAccountError) as ctx:
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertNotIsInstance(ctx.exception, ProviderRateLimited)

    def test_timeout_khong_thu_lai_khi_retry_count_0(self):
        so_lan = {"n": 0}

        def handler(request):
            so_lan["n"] += 1
            raise httpx.ConnectTimeout("timeout", request=request)

        p = PollinationsProvider(api_key="sk_vidu", model="deepseek",
                                 client=_client_gia(handler), retry_count=0)
        with self.assertRaises(ProviderTransientError):
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(so_lan["n"], 1)

    def test_timeout_thu_lai_va_thanh_cong_o_lan_hai(self):
        """'timeout' + retry count — mot lan mat mang thoang qua khong lam
        that bai ca doan neu lan thu lai sau do thanh cong."""
        so_lan = {"n": 0}

        def handler(request):
            so_lan["n"] += 1
            if so_lan["n"] == 1:
                raise httpx.ReadTimeout("timeout", request=request)
            return _tra_loi_chat("Xin chào")

        p = PollinationsProvider(api_key="sk_vidu", model="deepseek",
                                 client=_client_gia(handler), retry_count=1)
        ra = p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Xin chào")
        self.assertEqual(so_lan["n"], 2)

    def test_timeout_het_luot_thu_lai_nem_loi(self):
        def handler(request):
            raise httpx.ConnectTimeout("timeout", request=request)

        p = PollinationsProvider(api_key="sk_vidu", model="deepseek",
                                 client=_client_gia(handler), retry_count=2)
        with self.assertRaises(ProviderTransientError):
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))

    def test_429_thu_lai_cuc_bo_het_luot_van_nem_loi(self):
        """Phan refactor dinh tuyen theo pham vi loi, muc RATE LIMIT: '429
        thu lai cuc bo (bounded), het luot van con 429 thi de loi lan len
        cho tang tren chuyen sang nha cung cap khac' — retry_count=3 nghia
        la TOI DA 4 lan goi (1 dau + 3 thu lai)."""
        so_lan = {"n": 0}

        def handler(request):
            so_lan["n"] += 1
            return httpx.Response(429, text="rate limited")

        p = PollinationsProvider(api_key="sk_vidu", model="deepseek",
                                 client=_client_gia(handler), retry_count=3)
        with self.assertRaises(ProviderRateLimited):
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(so_lan["n"], 4)

    def test_429_thu_lai_thanh_cong_o_lan_hai(self):
        so_lan = {"n": 0}

        def handler(request):
            so_lan["n"] += 1
            if so_lan["n"] == 1:
                return httpx.Response(429, text="rate limited")
            return _tra_loi_chat("Xin chào")

        p = PollinationsProvider(api_key="sk_vidu", model="deepseek",
                                 client=_client_gia(handler), retry_count=1)
        ra = p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Xin chào")
        self.assertEqual(so_lan["n"], 2)

    def test_402_khong_thu_lai_cuc_bo(self):
        """`ProviderAccountError` (401/402) KHONG duoc thu lai cuc bo — cung
        mot yeu cau se that bai giong het (sai key/het so du khong tu
        thay doi giua hai lan goi lien tiep)."""
        so_lan = {"n": 0}

        def handler(request):
            so_lan["n"] += 1
            return httpx.Response(402, text="insufficient balance")

        p = PollinationsProvider(api_key="sk_vidu", model="deepseek",
                                 client=_client_gia(handler), retry_count=3)
        with self.assertRaises(ProviderAccountError):
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(so_lan["n"], 1)


class PollinationsFallbackChainTest(unittest.TestCase):
    """Day fallback THAT qua `ProviderRegistry` (Phan yeu cau failure
    handling): deepseek -> deepseek-pro -> Groq -> loi co kiem soat."""

    def _cp_pollinations(self, provider_id, model, handler,
                         rate_limit_la_toan_tai_khoan=True):
        # Mac dinh `True` — dung KHOP cau hinh THAT cua
        # `build_provider_registry` (moi model Pollinations dung chung MOT
        # credential, gia dinh han muc toc do la toan tai khoan).
        return ConfiguredProvider(
            provider_id=provider_id, model_id=model, display_name=provider_id,
            quality_hint="test",
            provider=PollinationsProvider(
                api_key="sk_vidu", model=model, client=_client_gia(handler)),
            free_tier=True,
            rate_limit_la_toan_tai_khoan=rate_limit_la_toan_tai_khoan)

    def _cp_groq(self, handler):
        return ConfiguredProvider(
            provider_id="groq_qwen", model_id=_QWEN.model_id,
            display_name="Groq", quality_hint="test",
            provider=GroqProvider(api_key="k", profile=_QWEN,
                                  client=_client_gia(handler)),
            free_tier=True)

    def test_deepseek_model_that_bai_chuyen_sang_deepseek_pro(self):
        """MODEL-SPECIFIC (vd 500/phan hoi loi cua RIENG model nay, khong
        phai 401/402/429) — chi bo qua THE HIEN DO, thu model KE TIEP CUNG
        Pollinations nhu binh thuong."""
        deepseek = self._cp_pollinations(
            "pollinations_deepseek", "deepseek",
            lambda r: httpx.Response(500, text="model error"))
        deepseek_pro = self._cp_pollinations(
            "pollinations_deepseek_pro", "deepseek-pro",
            lambda r: _tra_loi_chat("Bản dịch chất lượng cao"))
        reg = ProviderRegistry([deepseek, deepseek_pro])
        ra, prov = reg.translate_segment(
            "你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Bản dịch chất lượng cao")
        self.assertEqual(prov.provider_id, "pollinations_deepseek_pro")

    def test_het_so_du_that_ca_hai_pollinations_chuyen_sang_groq(self):
        """Hoi quy TU KIEM THU SONG (2026-08-15): tai khoan Pollinations
        chua nap 'pollen' tra 402 that cho CA HAI model — xac nhan day van
        la MOT `TranslationProviderError` chung (khong phai 429), va
        registry van chuyen dung sang Groq thay vi coi 402 la thanh cong
        hoac dung lai giua chung."""
        than_402 = ('{"success":false,"error":{"message":"Insufficient '
                   'balance. This request costs ~0.0021 pollen, but your '
                   'available balance is 0.0000.","code":"PAYMENT_REQUIRED"}}')
        deepseek = self._cp_pollinations(
            "pollinations_deepseek", "deepseek",
            lambda r: httpx.Response(402, text=than_402))
        deepseek_pro = self._cp_pollinations(
            "pollinations_deepseek_pro", "deepseek-pro",
            lambda r: httpx.Response(402, text=than_402))
        groq = self._cp_groq(lambda r: _tra_loi_chat("Xin chào từ Groq"))
        reg = ProviderRegistry([deepseek, deepseek_pro, groq])
        ra, prov = reg.translate_segment(
            "你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Xin chào từ Groq")
        self.assertEqual(prov.provider_id, "groq_qwen")

    def test_ca_hai_pollinations_that_bai_chuyen_sang_groq(self):
        deepseek = self._cp_pollinations(
            "pollinations_deepseek", "deepseek",
            lambda r: httpx.Response(500, text="server error"))
        deepseek_pro = self._cp_pollinations(
            "pollinations_deepseek_pro", "deepseek-pro",
            lambda r: httpx.Response(500, text="server error"))
        groq = self._cp_groq(lambda r: _tra_loi_chat("Xin chào từ Groq"))
        reg = ProviderRegistry([deepseek, deepseek_pro, groq])
        ra, prov = reg.translate_segment(
            "你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Xin chào từ Groq")
        self.assertEqual(prov.provider_id, "groq_qwen")

    def test_tat_ca_that_bai_tra_loi_co_kiem_soat(self):
        """'return a controlled translation error' — KHONG BAO GIO tra ve
        mot ban dich rong/hong am tham; nem `AllProvidersUnavailable` ro
        rang de tang tren doi thanh trang thai job an toan."""
        deepseek = self._cp_pollinations(
            "pollinations_deepseek", "deepseek",
            lambda r: httpx.Response(500, text="server error"))
        deepseek_pro = self._cp_pollinations(
            "pollinations_deepseek_pro", "deepseek-pro",
            lambda r: httpx.Response(500, text="server error"))
        groq = self._cp_groq(lambda r: httpx.Response(500, text="server error"))
        reg = ProviderRegistry([deepseek, deepseek_pro, groq])
        with self.assertRaises(AllProvidersUnavailable):
            reg.translate_segment(
                "你好", context=TranslationContext(vai_tro="translator"))

    def test_auto_theo_vai_tro_khong_dao_nguoc_uu_tien_pollinations(self):
        """Hoi quy TRUC TIEP cho loi da sua o `_sap_theo_vai_tro`: du dinh
        tuyen AUTO sap lai NOI BO nhom Groq theo (quality_mode, vai_tro),
        Pollinations (dat TRUOC Groq trong cau hinh) KHONG duoc phep bi day
        xuong SAU nhom Groq."""
        deepseek = self._cp_pollinations(
            "pollinations_deepseek", "deepseek",
            lambda r: _tra_loi_chat("Ưu tiên hàng đầu"))
        groq_qwen = ConfiguredProvider(
            provider_id="groq_qwen", model_id=GROQ_MODEL_PROFILES["qwen"].model_id,
            display_name="Groq Qwen", quality_hint="test",
            provider=GroqProvider(api_key="k", profile=GROQ_MODEL_PROFILES["qwen"],
                                  client=_client_gia(lambda r: _tra_loi_chat("Groq"))),
            free_tier=True)
        gpt120 = ConfiguredProvider(
            provider_id="groq_gpt_oss_120b",
            model_id=GROQ_MODEL_PROFILES["gpt_oss_120b"].model_id,
            display_name="Groq GPT-OSS 120B", quality_hint="test",
            provider=GroqProvider(api_key="k", profile=GROQ_MODEL_PROFILES["gpt_oss_120b"],
                                  client=_client_gia(lambda r: _tra_loi_chat("Groq 120b"))),
            free_tier=True)
        reg = ProviderRegistry([deepseek, groq_qwen, gpt120])
        # can_bang/translator dinh tuyen AUTO nhom Groq theo thu tu rieng —
        # Pollinations van phai duoc thu TRUOC vi no dung o dau danh sach.
        ra, prov = reg.translate_segment(
            "你好", context=TranslationContext(
                vai_tro="translator", quality_mode="can_bang"))
        self.assertEqual(prov.provider_id, "pollinations_deepseek")
        self.assertEqual(ra, "Ưu tiên hàng đầu")


class PollinationsFailureScopeTest(unittest.TestCase):
    """
    Phan refactor dinh tuyen theo PHAM VI loi (yeu cau hien tai) — trong tam
    la XAC NHAN mot loi cap TAI KHOAN KHONG lam registry lang phi thu tung
    model Pollinations con lai mot cach vo ich, khac han loi RIENG mot
    model (van thu tiep model ke, xem `PollinationsFallbackChainTest`).
    """

    def _cp_pollinations(self, provider_id, model, handler):
        return ConfiguredProvider(
            provider_id=provider_id, model_id=model, display_name=provider_id,
            quality_hint="test",
            provider=PollinationsProvider(
                api_key="sk_vidu", model=model, client=_client_gia(handler)),
            free_tier=True, rate_limit_la_toan_tai_khoan=True)

    def _cp_groq(self, handler):
        return ConfiguredProvider(
            provider_id="groq_qwen", model_id=_QWEN.model_id,
            display_name="Groq", quality_hint="test",
            provider=GroqProvider(api_key="k", profile=_QWEN,
                                  client=_client_gia(handler)),
            free_tier=True)

    def test_402_bo_qua_deepseek_pro_chuyen_thang_groq(self):
        """'Pollinations 402 -> Groq immediately' — deepseek-pro KHONG
        duoc goi (so_lan_goi == 0), khac voi loi RIENG mot model (vd 500)
        van thu deepseek-pro binh thuong."""
        so_lan_deepseek_pro = {"n": 0}
        than_402 = ('{"success":false,"error":{"message":"Insufficient '
                   'balance."}}')

        def handler_pro(request):
            so_lan_deepseek_pro["n"] += 1
            return _tra_loi_chat("không nên tới đây")

        deepseek = self._cp_pollinations(
            "pollinations_deepseek", "deepseek",
            lambda r: httpx.Response(402, text=than_402))
        deepseek_pro = self._cp_pollinations(
            "pollinations_deepseek_pro", "deepseek-pro", handler_pro)
        groq = self._cp_groq(lambda r: _tra_loi_chat("Xin chào từ Groq"))
        reg = ProviderRegistry([deepseek, deepseek_pro, groq])
        ra, prov = reg.translate_segment(
            "你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Xin chào từ Groq")
        self.assertEqual(prov.provider_id, "groq_qwen")
        self.assertEqual(so_lan_deepseek_pro["n"], 0,
                         "deepseek-pro KHÔNG được gọi sau lỗi 402 của deepseek")

    def test_401_bo_qua_cac_model_con_lai_chuyen_thang_groq(self):
        """'Pollinations auth failure -> Groq immediately' — 401 (sai/thu
        hoi API key) cung la loi cap TAI KHOAN, hanh vi GIONG HET 402."""
        so_lan_kimi = {"n": 0}

        def handler_kimi(request):
            so_lan_kimi["n"] += 1
            return _tra_loi_chat("không nên tới đây")

        deepseek = self._cp_pollinations(
            "pollinations_deepseek", "deepseek",
            lambda r: httpx.Response(401, text='{"error":"invalid api key"}'))
        kimi = self._cp_pollinations("pollinations_kimi", "kimi", handler_kimi)
        groq = self._cp_groq(lambda r: _tra_loi_chat("Xin chào từ Groq"))
        reg = ProviderRegistry([deepseek, kimi, groq])
        ra, prov = reg.translate_segment(
            "你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Xin chào từ Groq")
        self.assertEqual(prov.provider_id, "groq_qwen")
        self.assertEqual(so_lan_kimi["n"], 0,
                         "kimi KHÔNG được gọi sau lỗi 401 của deepseek")

    def test_rate_limit_toan_tai_khoan_bo_qua_cac_model_con_lai(self):
        """429 tren MOT nha cung cap co `rate_limit_la_toan_tai_khoan=True`
        (Pollinations) — sau khi thu lai cuc bo (trong `PollinationsProvider`)
        van con 429, bo qua CAC MODEL CON LAI cung Pollinations, chuyen
        thang Groq — khac Groq TU (rate limit RIENG tung model, xem
        `test_qwen_that_bai_fallback_dung_thu_tu_sang_gpt_oss_120b_roi_20b`,
        KHONG doi)."""
        so_lan_glm = {"n": 0}

        def handler_glm(request):
            so_lan_glm["n"] += 1
            return _tra_loi_chat("không nên tới đây")

        deepseek = self._cp_pollinations(
            "pollinations_deepseek", "deepseek",
            lambda r: httpx.Response(429, text="rate limited"))
        glm = self._cp_pollinations("pollinations_glm", "glm", handler_glm)
        groq = self._cp_groq(lambda r: _tra_loi_chat("Xin chào từ Groq"))
        reg = ProviderRegistry([deepseek, glm, groq])
        ra, prov = reg.translate_segment(
            "你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(prov.provider_id, "groq_qwen")
        self.assertEqual(so_lan_glm["n"], 0)

    def test_tat_ca_provider_khong_dung_duoc_tra_loi_co_kiem_soat(self):
        """'all providers unavailable -> controlled error' — ke ca sau khi
        bo qua ca nhom Pollinations vi loi tai khoan, Groq CUNG that bai
        thi van la MOT `AllProvidersUnavailable` ro rang."""
        deepseek = self._cp_pollinations(
            "pollinations_deepseek", "deepseek",
            lambda r: httpx.Response(402, text='{"error":"no balance"}'))
        groq = self._cp_groq(lambda r: httpx.Response(500, text="server error"))
        reg = ProviderRegistry([deepseek, groq])
        with self.assertRaises(AllProvidersUnavailable):
            reg.translate_segment(
                "你好", context=TranslationContext(vai_tro="translator"))


class BuildRegistryPollinationsTest(unittest.TestCase):
    def test_thieu_pollinations_api_key_thi_khong_co_mat(self):
        reg = build_provider_registry(env={"GROQ_API_KEY": "k"})
        ids = [e.provider_id for e in reg.catalog()]
        self.assertNotIn("pollinations_deepseek", ids)
        self.assertNotIn("pollinations_deepseek_pro", ids)

    def test_groq_only_van_hoat_dong_binh_thuong(self):
        """Hoi quy: khong co POLLINATIONS_API_KEY, Groq-only phai chay Y HET
        truoc khi Pollinations duoc them vao he thong."""
        reg = build_provider_registry(env={"GROQ_API_KEY": "k"})
        self.assertTrue(bool(reg))
        ids = {e.provider_id for e in reg.catalog()}
        self.assertEqual(ids, {"groq_qwen", "groq_gpt_oss_120b", "groq_gpt_oss_20b"})

    def test_co_du_pollinations_api_key_thi_co_ca_hai_model_mac_dinh(self):
        reg = build_provider_registry(env={"POLLINATIONS_API_KEY": "sk_vidu"})
        ids = [e.provider_id for e in reg.catalog()]
        self.assertIn("pollinations_deepseek", ids)
        self.assertIn("pollinations_deepseek_pro", ids)
        models = {e.provider_id: e.model_id for e in reg.catalog()}
        self.assertEqual(models["pollinations_deepseek"], "deepseek")
        self.assertEqual(models["pollinations_deepseek_pro"], "deepseek-pro")

    def test_mac_dinh_pollinations_dung_truoc_groq(self):
        reg = build_provider_registry(env={
            "POLLINATIONS_API_KEY": "sk_vidu", "GROQ_API_KEY": "k",
        })
        ids = [e.provider_id for e in reg.as_list()]
        self.assertEqual(ids[0], "pollinations_deepseek")
        self.assertEqual(ids[1], "pollinations_deepseek_pro")
        self.assertTrue(ids[2].startswith("groq"))

    def test_pollinations_models_mo_rong_qua_bien_moi_truong(self):
        """Yeu cau refactor: 'Make the Pollinations candidate model order
        configurable through env/config rather than hard-coded' — danh
        sach UNG VIEN (khong chi hai model) va THU TU deu doc tu
        `POLLINATIONS_MODELS`, khong hard-code trong ung dung."""
        reg = build_provider_registry(env={
            "POLLINATIONS_API_KEY": "sk_vidu",
            "POLLINATIONS_MODELS": "kimi,glm,deepseek,deepseek-pro,command-a-plus",
        })
        ids = [e.provider_id for e in reg.as_list()]
        self.assertEqual(ids, [
            "pollinations_kimi", "pollinations_glm", "pollinations_deepseek",
            "pollinations_deepseek_pro", "pollinations_command_a_plus",
        ])
        models = {e.provider_id: e.model_id for e in reg.catalog()}
        self.assertEqual(models["pollinations_kimi"], "kimi")
        self.assertEqual(models["pollinations_command_a_plus"], "command-a-plus")

    def test_pollinations_models_thu_tu_theo_dung_cau_hinh_khong_theo_ten(self):
        """'Do not add command-a-plus unless...' + 'final ordering must be
        determined by real... benchmarks' — thu tu THUC SU dung LA thu tu
        trong `POLLINATIONS_MODELS`, khong tu sap xep lai theo bang chu cai
        hay theo ten nha cung cap goc."""
        reg = build_provider_registry(env={
            "POLLINATIONS_API_KEY": "sk_vidu",
            "POLLINATIONS_MODELS": "glm,command-a-plus,kimi",
        })
        ids = [e.provider_id for e in reg.as_list()]
        self.assertEqual(ids, [
            "pollinations_glm", "pollinations_command_a_plus", "pollinations_kimi",
        ])

    def test_pollinations_models_loc_trung_lap_giu_lan_dau(self):
        reg = build_provider_registry(env={
            "POLLINATIONS_API_KEY": "sk_vidu",
            "POLLINATIONS_MODELS": "deepseek,kimi,deepseek",
        })
        ids = [e.provider_id for e in reg.as_list()]
        self.assertEqual(ids, ["pollinations_deepseek", "pollinations_kimi"])

    def test_tuy_chinh_model_qua_bien_cu_van_tuong_thich_nguoc(self):
        """Chua dat `POLLINATIONS_MODELS` — lui ve cap bien CU
        (`POLLINATIONS_PRIMARY_MODEL`/`POLLINATIONS_QUALITY_MODEL`) tu dot
        trien khai dau tien, khong lam hong cau hinh da co."""
        reg = build_provider_registry(env={
            "POLLINATIONS_API_KEY": "sk_vidu",
            "POLLINATIONS_PRIMARY_MODEL": "deepseek-v3",
            "POLLINATIONS_QUALITY_MODEL": "deepseek-r1",
        })
        models = {e.provider_id: e.model_id for e in reg.catalog()}
        self.assertEqual(models["pollinations_deepseek_v3"], "deepseek-v3")
        self.assertEqual(models["pollinations_deepseek_r1"], "deepseek-r1")

    def test_pollinations_models_thang_the_bien_cu_neu_ca_hai_cung_dat(self):
        reg = build_provider_registry(env={
            "POLLINATIONS_API_KEY": "sk_vidu",
            "POLLINATIONS_MODELS": "kimi,glm",
            "POLLINATIONS_PRIMARY_MODEL": "deepseek",
            "POLLINATIONS_QUALITY_MODEL": "deepseek-pro",
        })
        ids = [e.provider_id for e in reg.as_list()]
        self.assertEqual(ids, ["pollinations_kimi", "pollinations_glm"])

    def test_free_tier_false_thi_bi_loc_het(self):
        """Rao chan an toan: dat ro rang KHONG phai mien phi thi Pollinations
        KHONG duoc dua vao duong thu, du co API key."""
        reg = build_provider_registry(env={
            "POLLINATIONS_API_KEY": "sk_vidu",
            "POLLINATIONS_FREE_TIER": "false",
        })
        ids = [e.provider_id for e in reg.catalog()]
        self.assertNotIn("pollinations_deepseek", ids)

    def test_uu_tien_qua_cau_hinh_doi_duoc_thu_tu(self):
        """'reordered through configuration rather than hard-coded' —
        TRANSLATION_PROVIDER_PRIORITY dua Groq len truoc Pollinations ma
        khong can sua code."""
        reg = build_provider_registry(env={
            "POLLINATIONS_API_KEY": "sk_vidu", "GROQ_API_KEY": "k",
            "TRANSLATION_PROVIDER_PRIORITY": "groq_qwen,groq_gpt_oss_120b,groq_gpt_oss_20b",
        })
        ids = [e.provider_id for e in reg.as_list()]
        self.assertEqual(ids[0], "groq_qwen")
        # Pollinations khong duoc nhac toi trong uu tien -> noi vao SAU,
        # nhung van CO MAT (khong bi mat).
        self.assertIn("pollinations_deepseek", ids)
        self.assertIn("pollinations_deepseek_pro", ids)

    def test_timeout_va_retry_count_doc_tu_bien_moi_truong(self):
        reg = build_provider_registry(env={
            "POLLINATIONS_API_KEY": "sk_vidu",
            "POLLINATIONS_TIMEOUT_SECONDS": "10",
            "POLLINATIONS_RETRY_COUNT": "3",
        })
        cp = reg.get("pollinations_deepseek")
        self.assertIsNotNone(cp)
        provider = cp.provider
        self.assertEqual(provider._retry_count, 3)
        self.assertEqual(provider._client.timeout.connect, 10.0)

    def test_bien_moi_truong_hong_dung_gia_tri_mac_dinh(self):
        """Mot bien so hong (khong doc duoc) khong duoc phep lam sap ca
        tien trinh luc khoi dong — phai roi ve mac dinh an toan."""
        reg = build_provider_registry(env={
            "POLLINATIONS_API_KEY": "sk_vidu",
            "POLLINATIONS_TIMEOUT_SECONDS": "khong-phai-so",
            "POLLINATIONS_RETRY_COUNT": "khong-phai-so",
        })
        cp = reg.get("pollinations_deepseek")
        self.assertEqual(cp.provider._retry_count, 1)

    def test_moi_model_deu_danh_dau_han_muc_toan_tai_khoan(self):
        """Moi `ConfiguredProvider` Pollinations phai dat
        `rate_limit_la_toan_tai_khoan=True` — day la co so de
        `ProviderRegistry` bo qua ca nhom Pollinations khi mot model bi
        gioi han toc do, thay vi thu tung model mot cach vo ich (xem
        `PollinationsFailureScopeTest`)."""
        reg = build_provider_registry(env={
            "POLLINATIONS_API_KEY": "sk_vidu",
            "POLLINATIONS_MODELS": "deepseek,kimi,glm",
        })
        for cp in reg.as_list():
            if cp.provider_id.startswith("pollinations_"):
                self.assertTrue(cp.rate_limit_la_toan_tai_khoan, cp.provider_id)


class KiemTraKetNoiPollinationsTest(unittest.TestCase):
    """Kiem tra suc khoe NHE, GOI THEO YEU CAU (khong phai polling dinh ky —
    xem yeu cau 'model-health checking without introducing aggressive
    polling'), cung mau voi `KiemTraKetNoiGroqTest`."""

    def _client(self, handler):
        return httpx.Client(base_url="https://vidu.test",
                            transport=httpx.MockTransport(handler))

    def test_key_hop_le_va_model_co_san_thanh_cong(self):
        kiem_tra_ket_noi_pollinations(
            "sk_hop_le", "deepseek", client=self._client(
                lambda r: httpx.Response(200, json={"data": [{"id": "deepseek"}]})))

    def test_danh_sach_model_rong_khong_chan_cung(self):
        """Endpoint co that nhung khong liet ke model theo dang OpenAI
        chuan — KHONG coi day la bang chung model khong ton tai."""
        kiem_tra_ket_noi_pollinations(
            "sk_hop_le", "deepseek", client=self._client(
                lambda r: httpx.Response(200, json={"data": []})))

    def test_401_thanh_invalid_key(self):
        with self.assertRaises(ConnectionCheckError) as ctx:
            kiem_tra_ket_noi_pollinations("sk_sai", "deepseek", client=self._client(
                lambda r: httpx.Response(401, json={"error": "unauthorized"})))
        self.assertEqual(ctx.exception.code, "INVALID_KEY")

    def test_429_thanh_rate_limited(self):
        with self.assertRaises(ConnectionCheckError) as ctx:
            kiem_tra_ket_noi_pollinations("sk_x", "deepseek", client=self._client(
                lambda r: httpx.Response(429, text="rate limited")))
        self.assertEqual(ctx.exception.code, "RATE_LIMITED")

    def test_model_vang_mat_trong_danh_sach_thanh_model_unavailable(self):
        with self.assertRaises(ConnectionCheckError) as ctx:
            kiem_tra_ket_noi_pollinations(
                "sk_hop_le", "model-khong-ton-tai", client=self._client(
                    lambda r: httpx.Response(
                        200, json={"data": [{"id": "deepseek"}]})))
        self.assertEqual(ctx.exception.code, "MODEL_UNAVAILABLE")

    def test_loi_mang_thanh_provider_unavailable(self):
        def handler(request):
            raise httpx.ConnectTimeout("timeout", request=request)

        with self.assertRaises(ConnectionCheckError) as ctx:
            kiem_tra_ket_noi_pollinations("sk_x", "deepseek",
                                          client=self._client(handler))
        self.assertEqual(ctx.exception.code, "PROVIDER_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
