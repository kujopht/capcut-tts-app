"""
Chien luoc san xuat TAM THOI: Cerebras (GPT-OSS 120B) + Groq (Qwen, du phong
doc lap) — `feature/cerebras-groq-translation`.

`zai-glm-4.7` KHONG con trong dinh tuyen — tai lieu Cerebras chinh thuc
(kiem tra 2026-08-15) ghi ro day la model Preview va SE NGUNG HO TRO
2026-08-17, nen da bi go khoi `CEREBRAS_MODEL_PROFILES` (xem
`translation_model_profiles.py`) TRUOC KHI benchmark that. Cerebras hien
CHI co MOT model curated (`gpt_oss_120b`).

Bo cuc file (khop voi 17 kich ban yeu cau goc, da dieu chinh cho dung MOT
model Cerebras):
  - `CerebrasProviderTest`            : co che `CerebrasProvider` (Phan 1-5)
  - `KiemTraKetNoiCerebrasTest`       : kiem tra ket noi BYOK (khong dich thu)
  - `BuildProviderRegistryTest`       : doc CEREBRAS_API_KEY/GROQ_API_KEY
  - `SharedRoutingTest`               : kich ban 1-5, 13 (thu tu that bai)
  - `CerebrasByokTest`/`GroqByokTest` : kich ban 6-11
  - `ByokNeverConsumesSharedTest`     : kich ban 12
  - `ChunkOrderingTest`               : kich ban 14-15
  - `CacheAvoidsRepeatedCallTest`     : kich ban 16
  - `NoSecretsLeakTest`               : kich ban 17
"""

from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch

import httpx

from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.translation_byok_crypto import ByokCrypto, sinh_master_key_moi
from server.translation_byok_service import ProviderConnectionService
from server.translation_model_profiles import CEREBRAS_MODEL_PROFILES, GROQ_MODEL_PROFILES
from server.translation_provider_registry import (
    AllProvidersUnavailable,
    CerebrasProvider,
    ConfiguredProvider,
    ConnectionCheckError,
    ProviderRateLimited,
    ProviderRegistry,
    build_provider_registry,
    kiem_tra_ket_noi_cerebras,
)
from server.translation_providers import TranslationContext, TranslationProviderError
from server.translation_service import TranslationService
from server.translation_store import MockTranslationStore

#: Cerebras hien CHI co MOT model curated (`zai-glm-4.7` da bi go — xem
#: docstring dau file). Bien nay giu ten "GPT_OSS" (khong phai "MODEL" chung
#: chung) de neu Cerebras them model curated thu hai sau nay, cac test o day
#: khong nham lan gia dinh "chi co mot model mai mai".
_CEREBRAS_GPT_OSS = CEREBRAS_MODEL_PROFILES["gpt_oss_120b"]
_QWEN = GROQ_MODEL_PROFILES["qwen"]

KHOA_TEST = sinh_master_key_moi()


def _client_gia(handler):
    return httpx.Client(base_url="https://vidu.test",
                        transport=httpx.MockTransport(handler))


def _tra_loi_chat(noi_dung: str, *, status_code: int = 200, headers=None,
                  usage=None) -> httpx.Response:
    than = {"choices": [{"message": {"content": noi_dung}}]}
    if usage is not None:
        than["usage"] = usage
    return httpx.Response(status_code, json=than, headers=headers or {})


class _FakeInnerProvider:
    """Spy tat dinh — kich ban la danh sach hanh dong ("ok" hoac mot
    Exception) tra ve/nem theo THU TU moi lan goi."""

    name = "fake"

    def __init__(self, kich_ban):
        self._kich_ban = list(kich_ban)
        self.so_lan_goi = 0

    def translate_segment(self, text, *, context):
        self.so_lan_goi += 1
        hanh_dong = self._kich_ban.pop(0) if self._kich_ban else "ok"
        if hanh_dong == "ok":
            return f"[{self.name}] {text}"
        raise hanh_dong


def _cerebras_cp(profile_key: str, kich_ban, credential_source="shared"):
    profile = CEREBRAS_MODEL_PROFILES[profile_key]
    return ConfiguredProvider(
        provider_id=f"cerebras_{profile_key}", model_id=profile.model_id,
        display_name=profile.display_name, quality_hint=profile.quality_hint,
        provider=_FakeInnerProvider(kich_ban), free_tier=True,
        credential_source=credential_source)


def _groq_cp(profile_key: str, kich_ban, credential_source="shared"):
    profile = GROQ_MODEL_PROFILES[profile_key]
    return ConfiguredProvider(
        provider_id=f"groq_{profile_key}", model_id=profile.model_id,
        display_name=profile.display_name, quality_hint=profile.quality_hint,
        provider=_FakeInnerProvider(kich_ban), free_tier=True,
        credential_source=credential_source)


# =============================================================================
# 1) Co che CerebrasProvider — REST, tham so, loc <think> (rao chan chung)
# =============================================================================

class CerebrasProviderTest(unittest.TestCase):
    def test_phan_hoi_binh_thuong(self):
        p = CerebrasProvider(api_key="k", profile=_CEREBRAS_GPT_OSS,
                             client=_client_gia(lambda r: _tra_loi_chat("Xin chào")))
        ra = p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Xin chào")

    def test_429_thanh_rate_limited(self):
        p = CerebrasProvider(api_key="k", profile=_CEREBRAS_GPT_OSS, client=_client_gia(
            lambda r: httpx.Response(429, text="too many requests",
                                     headers={"retry-after": "20"})))
        with self.assertRaises(ProviderRateLimited) as ctx:
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertTrue(ctx.exception.retry_at)

    def test_401_thanh_loi_chung_khong_bi_coi_la_rate_limit(self):
        p = CerebrasProvider(api_key="sai-key", profile=_CEREBRAS_GPT_OSS, client=_client_gia(
            lambda r: httpx.Response(401, text="invalid api key")))
        with self.assertRaises(TranslationProviderError) as ctx:
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertNotIsInstance(ctx.exception, ProviderRateLimited)

    def test_timeout_mang_thanh_loi_chung(self):
        def handler(request):
            raise httpx.ConnectTimeout("timeout", request=request)

        p = CerebrasProvider(api_key="k", profile=_CEREBRAS_GPT_OSS, client=_client_gia(handler))
        with self.assertRaises(TranslationProviderError):
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))

    def test_thieu_cau_hinh_nem_loi_ngay_luc_tao(self):
        with self.assertRaises(TranslationProviderError):
            CerebrasProvider(api_key="", profile=_CEREBRAS_GPT_OSS)

    def test_gpt_oss_gui_reasoning_effort_low(self):
        than_gui = {}

        def handler(request):
            than_gui.update(json.loads(request.content))
            return _tra_loi_chat("Xin chào")

        p = CerebrasProvider(api_key="k", profile=_CEREBRAS_GPT_OSS,
                             client=_client_gia(handler))
        p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(than_gui.get("reasoning_effort"), "low")
        self.assertEqual(than_gui.get("model"), "gpt-oss-120b")

    def test_loc_khoi_think_neu_model_van_tra_ve(self):
        """Rao chan chung (`_bo_khoi_nghi`) ap dung cho MOI provider tuong
        thich OpenAI, khong rieng Groq — Cerebras cung dung chung lop nen
        `_OpenAICompatFreeProvider`."""
        p = CerebrasProvider(api_key="k", profile=_CEREBRAS_GPT_OSS, client=_client_gia(
            lambda r: _tra_loi_chat(
                "<think>\nsuy nghĩ nội bộ...\n</think>\n\nTiêu Viêm nhìn về phía Dược Lão.")))
        ra = p.translate_segment("萧炎看向药老。",
                                 context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Tiêu Viêm nhìn về phía Dược Lão.")

    def test_luu_lai_so_token_tu_usage(self):
        p = CerebrasProvider(api_key="k", profile=_CEREBRAS_GPT_OSS, client=_client_gia(
            lambda r: _tra_loi_chat("Xin chào",
                                   usage={"prompt_tokens": 42, "completion_tokens": 7})))
        p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(p.last_usage, {"input_tokens": 42, "output_tokens": 7})

    def test_khong_co_usage_trong_phan_hoi_thi_last_usage_none(self):
        p = CerebrasProvider(api_key="k", profile=_CEREBRAS_GPT_OSS,
                             client=_client_gia(lambda r: _tra_loi_chat("Xin chào")))
        p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertIsNone(p.last_usage)


# =============================================================================
# 2) Kiem tra ket noi CA NHAN (khong dich thu, khong ton han muc)
# =============================================================================

class KiemTraKetNoiCerebrasTest(unittest.TestCase):
    def test_thanh_cong(self):
        client = _client_gia(lambda r: httpx.Response(
            200, json={"data": [{"id": "gpt-oss-120b"}]}))
        kiem_tra_ket_noi_cerebras("k", "gpt-oss-120b", client=client)  # khong nem gi

    def test_401_thanh_invalid_key(self):
        client = _client_gia(lambda r: httpx.Response(401))
        with self.assertRaises(ConnectionCheckError) as ctx:
            kiem_tra_ket_noi_cerebras("sai", "gpt-oss-120b", client=client)
        self.assertEqual(ctx.exception.code, "INVALID_KEY")

    def test_429_thanh_rate_limited(self):
        client = _client_gia(lambda r: httpx.Response(429))
        with self.assertRaises(ConnectionCheckError) as ctx:
            kiem_tra_ket_noi_cerebras("k", "gpt-oss-120b", client=client)
        self.assertEqual(ctx.exception.code, "RATE_LIMITED")

    def test_model_khong_co_trong_danh_sach(self):
        client = _client_gia(lambda r: httpx.Response(
            200, json={"data": [{"id": "khac-hoan-toan"}]}))
        with self.assertRaises(ConnectionCheckError) as ctx:
            kiem_tra_ket_noi_cerebras("k", "gpt-oss-120b", client=client)
        self.assertEqual(ctx.exception.code, "MODEL_UNAVAILABLE")

    def test_loi_khong_bao_gio_kem_api_key(self):
        client = _client_gia(lambda r: httpx.Response(401))
        with self.assertRaises(ConnectionCheckError) as ctx:
            kiem_tra_ket_noi_cerebras("bi-mat-cua-toi-12345", "gpt-oss-120b", client=client)
        self.assertNotIn("bi-mat-cua-toi-12345", str(ctx.exception))


# =============================================================================
# 3) build_provider_registry — doc CEREBRAS_API_KEY/GROQ_API_KEY tu moi truong
# =============================================================================

class BuildProviderRegistryTest(unittest.TestCase):
    def test_khong_co_bien_moi_truong_khong_co_cerebras(self):
        reg = build_provider_registry(env={})
        ids = {p.provider_id for p in reg.as_list()}
        self.assertFalse(any(pid.startswith("cerebras") for pid in ids))

    def test_co_cerebras_api_key_them_dung_mot_model(self):
        reg = build_provider_registry(env={"CEREBRAS_API_KEY": "csk_test"})
        ids = [p.provider_id for p in reg.as_list()]
        self.assertIn("cerebras_gpt_oss_120b", ids)
        # `zai-glm-4.7` (Preview, ngung ho tro 2026-08-17) da bi go khoi
        # `CEREBRAS_MODEL_PROFILES` — KHONG duoc xuat hien du CEREBRAS_API_KEY
        # co cau hinh.
        self.assertNotIn("cerebras_glm", ids)

    def test_khong_can_allow_paid_provider_de_bat_cerebras(self):
        """Cerebras la MIEN PHI (free_tier=True, giong Groq) — khong can
        `TRANSLATION_ALLOW_PAID_PROVIDER=true` de kich hoat."""
        reg = build_provider_registry(env={
            "CEREBRAS_API_KEY": "csk_test",
            "TRANSLATION_ALLOW_PAID_PROVIDER": "false",
        })
        ids = {p.provider_id for p in reg.as_list()}
        self.assertIn("cerebras_gpt_oss_120b", ids)

    def test_cerebras_dung_TRUOC_groq_trong_danh_sach(self):
        """Chien luoc san xuat tam thoi: Cerebras la nha cung cap CHIA SE
        CHINH, dang ky truoc Groq trong danh sach dau vao — day la tien de de
        `_sap_theo_vai_tro` (gin nguyen vi tri) giu dung thu tu uu tien nay."""
        reg = build_provider_registry(env={
            "CEREBRAS_API_KEY": "csk_test", "GROQ_API_KEY": "gsk_test"})
        ids = [p.provider_id for p in reg.as_list()]
        self.assertLess(ids.index("cerebras_gpt_oss_120b"), ids.index("groq_qwen"))


# =============================================================================
# 4) Kich ban 1-5, 13: dinh tuyen THAT bai o che do dung chung (shared)
#
# Chi con HAI buoc that su (Cerebras GPT-OSS 120B -> Groq Qwen) thay vi ba —
# `zai-glm-4.7` da bi go, nen "hai model Cerebras that bai" (kich ban 3 ban
# dau) va "GLM that bai -> GPT-OSS" (kich ban 2 ban dau) khong con ap dung
# duoc THEO DUNG NGHIA GOC: gop lai thanh "Cerebras (mot model) that bai ->
# Groq".
# =============================================================================

class SharedRoutingTest(unittest.TestCase):
    """Dung `ProviderRegistry` truc tiep (khong qua build_provider_registry)
    voi provider GIA — kiem THU TU va hanh vi fallback, khong can API that."""

    def _registry(self, cerebras_kich_ban, qwen_kich_ban):
        cerebras = _cerebras_cp("gpt_oss_120b", cerebras_kich_ban)
        qwen = _groq_cp("qwen", qwen_kich_ban)
        # Dang ky Cerebras TRUOC Groq — dung thu tu san xuat.
        return ProviderRegistry([cerebras, qwen]), cerebras, qwen

    def test_1_cerebras_thanh_cong(self):
        reg, cerebras, qwen = self._registry(["ok"], ["ok"])
        _, prov = reg.translate_segment(
            "x", context=TranslationContext(vai_tro="translator", quality_mode="van_hoc"))
        self.assertEqual(prov.provider_id, "cerebras_gpt_oss_120b")
        self.assertEqual(qwen.provider.so_lan_goi, 0)

    def test_3_cerebras_that_bai_fallback_sang_groq(self):
        reg, cerebras, qwen = self._registry(
            [TranslationProviderError("hết hạn mức")], ["ok"])
        _, prov = reg.translate_segment(
            "x", context=TranslationContext(vai_tro="translator", quality_mode="van_hoc"))
        self.assertEqual(prov.provider_id, "groq_qwen")

    def test_4_cerebras_loi_xac_thuc_sang_groq_ngay(self):
        """"Auth failure" duoc mo phong bang mot `TranslationProviderError`
        chung (401 khong duoc 429-hoa) — Cerebras that bai NGAY LAN DAU (chi
        MOT model, khong co du phong noi bo nao de thu tiep), roi Groq
        (credential KHAC) thanh cong ngay."""
        reg, cerebras, qwen = self._registry(
            [TranslationProviderError("401: invalid api key")], ["ok"])
        _, prov = reg.translate_segment(
            "x", context=TranslationContext(vai_tro="translator", quality_mode="van_hoc"))
        self.assertEqual(prov.provider_id, "groq_qwen")
        self.assertEqual(cerebras.provider.so_lan_goi, 1)

    def test_5_groq_thanh_cong_khi_cerebras_loi(self):
        reg, cerebras, qwen = self._registry([TranslationProviderError("x")], ["ok"])
        ra, prov = reg.translate_segment(
            "x", context=TranslationContext(vai_tro="translator", quality_mode="van_hoc"))
        self.assertEqual(prov.provider_id, "groq_qwen")
        self.assertIn("[fake] x", ra)

    def test_13_tat_ca_deu_loi_nem_controlled_error(self):
        reg, cerebras, qwen = self._registry(
            [TranslationProviderError("x")], [TranslationProviderError("z")])
        with self.assertRaises(AllProvidersUnavailable):
            reg.translate_segment(
                "x", context=TranslationContext(vai_tro="translator", quality_mode="van_hoc"))

    def test_khong_dinh_tuyen_lai_manual_giu_nguyen_lua_chon(self):
        reg, cerebras, qwen = self._registry(["ok"], ["ok"])
        _, prov = reg.translate_segment(
            "x", context=TranslationContext(vai_tro="translator", quality_mode="van_hoc"),
            mode="manual", selected_provider_id="groq_qwen")
        self.assertEqual(prov.provider_id, "groq_qwen")
        self.assertEqual(cerebras.provider.so_lan_goi, 0)


# =============================================================================
# 6-11) BYOK — Cerebras va Groq ca nhan
# =============================================================================

def _byok_svc():
    store = MockTranslationStore()
    return ProviderConnectionService(
        store, crypto=ByokCrypto.tu_moi_truong(KHOA_TEST))


class CerebrasByokTest(unittest.TestCase):
    def setUp(self):
        self.svc = _byok_svc()

    @patch("server.translation_byok_service.kiem_tra_ket_noi_cerebras")
    def test_6_ket_noi_thanh_cong(self, kiem_tra):
        conn = self.svc.connect("u1", "cerebras", "csk_abcdefgh1234AB42")
        self.assertEqual(conn.provider_id, "cerebras")
        self.assertEqual(conn.last4, "AB42")
        self.assertNotIn("csk_abcdefgh1234AB42", conn.encrypted_secret)
        kiem_tra.assert_called_once()

    @patch("server.translation_byok_service.kiem_tra_ket_noi_cerebras")
    def test_7_key_khong_hop_le_khong_luu_gi(self, kiem_tra):
        kiem_tra.side_effect = ConnectionCheckError("INVALID_KEY", "sai key")
        with self.assertRaises(Exception):
            self.svc.connect("u1", "cerebras", "csk_sai")
        self.assertEqual(self.svc.list_connections("u1"), [])

    @patch("server.translation_byok_service.kiem_tra_ket_noi_cerebras")
    def test_8_rate_limited_bao_loi_ro_rang(self, kiem_tra):
        kiem_tra.side_effect = ConnectionCheckError("RATE_LIMITED", "cham lai")
        with self.assertRaises(ConnectionCheckError) as ctx:
            self.svc.connect("u1", "cerebras", "csk_test")
        self.assertEqual(ctx.exception.code, "RATE_LIMITED")

    @patch("server.translation_byok_service.kiem_tra_ket_noi_cerebras")
    def test_build_all_model_providers_tra_dung_mot_model_cerebras(self, kiem_tra):
        self.svc.connect("u1", "cerebras", "csk_test")
        ds = self.svc.build_all_model_providers("u1", "cerebras")
        ids = {p.provider_id for p in ds}
        self.assertEqual(ids, {"cerebras_gpt_oss_120b"})
        for p in ds:
            self.assertEqual(p.credential_source, "personal")

    @patch("server.translation_byok_service.kiem_tra_ket_noi_cerebras")
    def test_model_mac_dinh_la_gpt_oss_khong_phai_glm_da_go(self, kiem_tra):
        conn = self.svc.connect("u1", "cerebras", "csk_test")
        self.assertEqual(conn.selected_model, "gpt-oss-120b")


class GroqByokTest(unittest.TestCase):
    """Kich ban 9-11 — dung lai HANH VI da co (Part E/V5.1), viet lai ro rang
    theo dung ten kich ban yeu cau goc de de doi chieu."""

    def setUp(self):
        self.svc = _byok_svc()

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_9_ket_noi_thanh_cong(self, kiem_tra):
        conn = self.svc.connect("u1", "groq", "gsk_abcdefgh1234AB42")
        self.assertEqual(conn.last4, "AB42")
        kiem_tra.assert_called_once()

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_10_key_khong_hop_le_khong_luu_gi(self, kiem_tra):
        kiem_tra.side_effect = ConnectionCheckError("INVALID_KEY", "sai key")
        with self.assertRaises(Exception):
            self.svc.connect("u1", "groq", "gsk_sai")
        self.assertEqual(self.svc.list_connections("u1"), [])

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_11_rate_limited_bao_loi_ro_rang(self, kiem_tra):
        kiem_tra.side_effect = ConnectionCheckError("RATE_LIMITED", "cham lai")
        with self.assertRaises(ConnectionCheckError) as ctx:
            self.svc.connect("u1", "groq", "gsk_test")
        self.assertEqual(ctx.exception.code, "RATE_LIMITED")


# =============================================================================
# 12) BYOK tuong minh KHONG BAO GIO cham toi credential dung chung
#
# Cerebras chi con MOT model curated nen KHONG con vi du "tu fallback noi bo
# giua hai model Cerebras" — vi du do gio dung GROQ (van co ba model curated)
# de chung minh dung tinh chat "chi fallback CUNG ho ca nhan". Rieng phan
# "mot model Cerebras ca nhan that bai thi KHONG dung shared" van giu (don
# gian hoa: khong con fallback noi bo nao de thu truoc khi bao loi).
# =============================================================================

class ByokNeverConsumesSharedTest(unittest.TestCase):
    def test_manual_ca_nhan_that_bai_chi_fallback_noi_bo_ho_groq(self):
        shared_qwen = _groq_cp("qwen", ["ok"], credential_source="shared")
        shared_gpt120 = _groq_cp("gpt_oss_120b", ["ok"], credential_source="shared")
        shared_cerebras = _cerebras_cp("gpt_oss_120b", ["ok"], credential_source="shared")
        ca_nhan_qwen = _groq_cp(
            "qwen", [TranslationProviderError("model-specific")], credential_source="personal")
        ca_nhan_gpt120 = _groq_cp("gpt_oss_120b", ["ok"], credential_source="personal")

        reg = ProviderRegistry([shared_cerebras, shared_qwen, shared_gpt120])
        # `prefer_personal=True`: dung y nguoi dung tuong minh chon "API key
        # của tôi" — day la co the tim ca nhan TRUOC khi ca hai (dung chung
        # + ca nhan) co CUNG provider_id "groq_qwen" (xem
        # `build_provider_registry`/`build_all_model_providers`: ca hai deu
        # dat ten theo cung quy uoc `{provider_id}_{profile_key}`).
        _, prov = reg.translate_segment_with_personal(
            "x", context=TranslationContext(vai_tro="translator"),
            mode="manual", selected_provider_id="groq_qwen",
            allow_fallback=True, prefer_personal=True,
            personal_providers=[ca_nhan_qwen, ca_nhan_gpt120])

        # Model ca nhan THU HAI (cung ho Groq, cung mot api key) duoc dung —
        # KHONG BAO GIO cham toi bat ky provider DUNG CHUNG nao (ke ca
        # Cerebras dung chung, du no dung TRUOC Groq trong danh sach).
        self.assertEqual(prov.provider_id, "groq_gpt_oss_120b")
        self.assertEqual(prov.credential_source, "personal")
        self.assertEqual(shared_cerebras.provider.so_lan_goi, 0)
        self.assertEqual(shared_qwen.provider.so_lan_goi, 0)
        self.assertEqual(shared_gpt120.provider.so_lan_goi, 0)

    def test_ca_nhan_cerebras_that_bai_khong_cham_shared_nem_loi(self):
        shared_qwen = _groq_cp("qwen", ["ok"], credential_source="shared")
        ca_nhan_cerebras = _cerebras_cp(
            "gpt_oss_120b", [TranslationProviderError("x")], credential_source="personal")

        reg = ProviderRegistry([shared_qwen])
        with self.assertRaises(AllProvidersUnavailable):
            reg.translate_segment_with_personal(
                "x", context=TranslationContext(vai_tro="translator"),
                mode="manual", selected_provider_id="cerebras_gpt_oss_120b",
                allow_fallback=True, prefer_personal=True,
                personal_providers=[ca_nhan_cerebras])
        self.assertEqual(shared_qwen.provider.so_lan_goi, 0)


# =============================================================================
# 14-15) Thu tu doan giu nguyen, khong trung lap sau failover
# =============================================================================

class ChunkOrderingTest(unittest.TestCase):
    def setUp(self):
        self.identity = MockIdentityAdapter()
        self.novels = MockMetadataStore()
        self.store = MockTranslationStore()
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")

    def test_thu_tu_doan_giu_nguyen_khong_trung_lap_sau_khi_mot_model_that_bai(self):
        # Moi doan la MOT chuong rieng (mot cau), danh dau THU TU trong noi
        # dung tra ve de kiem tra ghep dung thu tu, khong trung.
        van_ban = "\n".join(
            f"第{i}章 C{i}\n{ky_tu}。" for i, ky_tu in
            enumerate(["甲", "乙", "丙", "丁"], start=1))

        # Cerebras that bai o LAN GOI DAU (chuong 1), Groq nhan chuong do —
        # cac chuong sau van thu Cerebras TRUOC (trang thai KHONG bi "dinh"
        # mai o unavailable sau MOT loi tam thoi thuoc loai
        # TranslationProviderError chung — day la hanh vi hien co, ghi nhan
        # lai o day khong phai thay doi moi), thanh cong tu chuong 2 tro di.
        cerebras = _cerebras_cp("gpt_oss_120b", [TranslationProviderError("tam thoi loi mot lan")])
        qwen = _groq_cp("qwen", ["ok", "ok", "ok", "ok"])
        registry = ProviderRegistry([cerebras, qwen])

        svc = TranslationService(self.store, self.novels, registry=registry)
        p = svc.create_project(self.an.user_id, title="t", source_text=van_ban,
                               quality_mode="nhanh")
        job = svc.create_job(p.project_id, self.an.user_id)

        han = time.time() + 5.0
        while time.time() < han:
            job = svc.get_job(job.job_id, self.an.user_id)
            if job.status.value in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.005)

        self.assertEqual(job.status.value, "completed", job.error)
        p_cuoi = svc.get_project(p.project_id, self.an.user_id)
        self.assertEqual(len(p_cuoi.translated_chapters), 4)
        # Moi chuong xuat hien DUNG MOT LAN, dung noi dung, dung thu tu —
        # khong doan nao bi lap/mat/sai vi tri.
        for i, ky_tu in enumerate(["甲", "乙", "丙", "丁"]):
            self.assertIn(ky_tu, p_cuoi.translated_chapters[i])
        # Khong co chuong nao trung noi dung voi chuong khac (khong trung lap).
        self.assertEqual(len(set(p_cuoi.translated_chapters)), 4)


# =============================================================================
# 16) Cache tranh goi lai model cho CUNG mot dau vao
# =============================================================================

class CacheAvoidsRepeatedCallTest(unittest.TestCase):
    def setUp(self):
        self.identity = MockIdentityAdapter()
        self.novels = MockMetadataStore()
        self.store = MockTranslationStore()
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")

    def test_doan_trung_lap_giua_hai_chuong_chi_goi_model_mot_lan(self):
        # Hai chuong CO CHUNG mot cau hoi thoai lap lai (chuyen rat thuong
        # gap trong fanfic mang) — lan thu hai phai la CACHE HIT. Ca hai
        # chuong dung CHINH XAC cung tieu de+noi dung (`tach_chuong` giu ca
        # dong tieu de nhu mot phan cua van ban chuong — xem
        # `ChunkOrderingTest`) de dam bao van ban goi provider GIONG HET
        # nhau giua hai chuong, khong chi phan cau hoi thoai.
        van_ban = "第1章\n你好。\n第1章\n你好。"
        qwen = _groq_cp("qwen", ["ok", "ok"])
        registry = ProviderRegistry([qwen])

        svc = TranslationService(self.store, self.novels, registry=registry)
        p = svc.create_project(self.an.user_id, title="t", source_text=van_ban,
                               quality_mode="nhanh")
        job = svc.create_job(p.project_id, self.an.user_id)

        han = time.time() + 5.0
        while time.time() < han:
            job = svc.get_job(job.job_id, self.an.user_id)
            if job.status.value in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.005)

        self.assertEqual(job.status.value, "completed", job.error)
        self.assertEqual(qwen.provider.so_lan_goi, 1,
                         "chương 2 lẽ ra phải trúng cache, không gọi lại model")
        p_cuoi = svc.get_project(p.project_id, self.an.user_id)
        self.assertEqual(p_cuoi.translated_chapters[0], p_cuoi.translated_chapters[1])

    def test_regenerate_KHONG_dung_cache_luon_goi_model_moi(self):
        """Nguoi dung bam "dịch lại" phai luon nhan MOT lan goi that moi —
        cache CHI danh cho duong ong tu dong (`_dich_mot_chuong`)."""
        van_ban = "第1章 Một\n你好。"
        qwen = _groq_cp("qwen", ["ok", "ok"])
        registry = ProviderRegistry([qwen])

        svc = TranslationService(self.store, self.novels, registry=registry)
        p = svc.create_project(self.an.user_id, title="t", source_text=van_ban,
                               quality_mode="nhanh")
        job = svc.create_job(p.project_id, self.an.user_id)

        han = time.time() + 5.0
        while time.time() < han:
            job = svc.get_job(job.job_id, self.an.user_id)
            if job.status.value in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.005)
        self.assertEqual(job.status.value, "completed", job.error)
        self.assertEqual(qwen.provider.so_lan_goi, 1)

        svc.regenerate_chapter(p.project_id, self.an.user_id, 0, force=True)
        self.assertEqual(qwen.provider.so_lan_goi, 2,
                         "\"dịch lại\" phải luôn gọi model mới, không dùng cache")


# =============================================================================
# 17) Khong bao gio lo bi mat trong loi/log
# =============================================================================

class NoSecretsLeakTest(unittest.TestCase):
    def test_loi_provider_khong_kem_api_key(self):
        p = CerebrasProvider(api_key="bi-mat-cua-toi-xyz", profile=_CEREBRAS_GPT_OSS,
                             client=_client_gia(lambda r: httpx.Response(
                                 500, text="internal server error")))
        with self.assertRaises(TranslationProviderError) as ctx:
            p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertNotIn("bi-mat-cua-toi-xyz", str(ctx.exception))

    def test_usage_event_khong_kem_api_key(self):
        from server.translation_usage import UsageRecorder

        rec = UsageRecorder()
        rec.ghi(provider_id="cerebras_gpt_oss_120b", model_id="gpt-oss-120b",
               credential_source="personal", pass_type="translator",
               outcome="success", latency_ms=5, input_tokens=10, output_tokens=3)
        d = rec.gan_day(1)[0].to_dict()
        self.assertNotIn("api_key", d)
        self.assertNotIn("secret", d)

    def test_connection_error_khong_kem_api_key(self):
        client = _client_gia(lambda r: httpx.Response(401))
        with self.assertRaises(ConnectionCheckError) as ctx:
            kiem_tra_ket_noi_cerebras("cyc_secret_value_999", "gpt-oss-120b", client=client)
        self.assertNotIn("cyc_secret_value_999", str(ctx.exception))
        self.assertNotIn("cyc_secret_value_999", ctx.exception.code)


if __name__ == "__main__":
    unittest.main()
