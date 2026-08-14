"""
Dinh tuyen da model Groq theo vai tro/che do chat luong — overnight Phase 3
(Part R, Phan 3B-3H).

Khac `test_translation_provider_registry.py` (kiem TUNG provider doc lap):
file nay kiem `ProviderRegistry` khi co NHIEU model Groq CUNG luc trong
registry — dung thu tu, doc lap trang thai, cach ghep voi Cloudflare/BYOK.
"""

from __future__ import annotations

import unittest

from server.translation_model_profiles import GROQ_MODEL_PROFILES, ROLE_ROUTING, route_order
from server.translation_provider_registry import (
    AllProvidersUnavailable,
    ConfiguredProvider,
    ProviderRateLimited,
    ProviderRegistry,
    ProviderStatus,
    build_provider_registry,
)
from server.translation_providers import TranslationContext, TranslationProviderError


class _FakeInnerProvider:
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


def _groq_cp(profile_key: str, kich_ban, credential_source="shared"):
    profile = GROQ_MODEL_PROFILES[profile_key]
    return ConfiguredProvider(
        provider_id=f"groq_{profile_key}", model_id=profile.model_id,
        display_name=profile.display_name, quality_hint=profile.quality_hint,
        provider=_FakeInnerProvider(kich_ban), free_tier=True,
        credential_source=credential_source)


class RouteOrderTableTest(unittest.TestCase):
    """Bang dinh tuyen dung DUNG cac to hop THAT SU xay ra
    (`translation_service._VAI_TRO_THEO_CHE_DO`)."""

    def test_dung_sau_to_hop_hop_le(self):
        to_hop_hop_le = {
            ("nhanh", "translator"),
            ("can_bang", "translator"), ("can_bang", "qa"),
            ("van_hoc", "translator"), ("van_hoc", "editor"), ("van_hoc", "qa"),
        }
        self.assertEqual(set(ROLE_ROUTING.keys()), to_hop_hop_le)

    def test_thu_tu_chi_chua_khoa_model_curated_hop_le(self):
        """MOI khoa trong danh sach dinh tuyen phai la mot model curated THAT
        (khong go nham/dat sai khoa) — nhung KHONG bat buoc ca ba khoa deu co
        mat: VAN_HOC co y CHI DINH DUNG MOT model cho moi vai tro (dac ta 3D
        — "Translator: Qwen", "Editor: GPT-OSS 120B", "QA: GPT-OSS 20B", mỗi
        vai trò MỘT model, không phải cả ba xếp hàng)."""
        khoa_hop_le = set(GROQ_MODEL_PROFILES.keys())
        for to_hop, thu_tu in ROLE_ROUTING.items():
            with self.subTest(to_hop=to_hop):
                self.assertTrue(set(thu_tu).issubset(khoa_hop_le), to_hop)
                self.assertEqual(len(thu_tu), len(set(thu_tu)),
                                 f"{to_hop}: có khoá lặp lại")

    def test_nhanh_va_can_bang_liet_ke_du_ca_ba_model(self):
        """NHANH va CAN_BANG (khac VAN_HOC) CO du phong giua ca ba model,
        dung dac ta 3D."""
        khoa_hop_le = set(GROQ_MODEL_PROFILES.keys())
        for to_hop in [("nhanh", "translator"), ("can_bang", "translator"),
                      ("can_bang", "qa")]:
            with self.subTest(to_hop=to_hop):
                self.assertEqual(set(ROLE_ROUTING[to_hop]), khoa_hop_le, to_hop)

    def test_van_hoc_chi_dinh_dung_mot_model_moi_vai_tro(self):
        self.assertEqual(ROLE_ROUTING[("van_hoc", "translator")], ["qwen"])
        self.assertEqual(ROLE_ROUTING[("van_hoc", "editor")], ["gpt_oss_120b"])
        self.assertEqual(ROLE_ROUTING[("van_hoc", "qa")], ["gpt_oss_20b"])

    def test_to_hop_la_tra_rong(self):
        self.assertEqual(route_order("khong_ton_tai", "translator"), [])
        self.assertEqual(route_order("", ""), [])


class AutoRoleRoutingTest(unittest.TestCase):
    """Phan 3D: AUTO thu DUNG THU TU theo (quality_mode, vai_tro)."""

    def test_nhanh_translator_uu_tien_qwen(self):
        qwen = _groq_cp("qwen", ["ok"])
        gpt120 = _groq_cp("gpt_oss_120b", ["ok"])
        gpt20 = _groq_cp("gpt_oss_20b", ["ok"])
        # Cho vao registry theo thu tu NGUOC — neu khong dinh tuyen dung thi
        # test se thay provider dau tien theo thu tu CAU HINH (gpt120)
        # thanh cong, khong phai qwen.
        reg = ProviderRegistry([gpt120, gpt20, qwen])
        _, prov = reg.translate_segment(
            "x", context=TranslationContext(
                vai_tro="translator", quality_mode="nhanh"))
        self.assertEqual(prov.provider_id, "groq_qwen")

    def test_can_bang_qa_uu_tien_gpt_oss_20b(self):
        qwen = _groq_cp("qwen", ["ok"])
        gpt120 = _groq_cp("gpt_oss_120b", ["ok"])
        gpt20 = _groq_cp("gpt_oss_20b", ["ok"])
        reg = ProviderRegistry([qwen, gpt120, gpt20])
        _, prov = reg.translate_segment(
            "x", context=TranslationContext(vai_tro="qa", quality_mode="can_bang"))
        self.assertEqual(prov.provider_id, "groq_gpt_oss_20b")

    def test_van_hoc_editor_chi_dinh_gpt_oss_120b(self):
        qwen = _groq_cp("qwen", ["ok"])
        gpt120 = _groq_cp("gpt_oss_120b", ["ok"])
        gpt20 = _groq_cp("gpt_oss_20b", ["ok"])
        reg = ProviderRegistry([qwen, gpt120, gpt20])
        _, prov = reg.translate_segment(
            "x", context=TranslationContext(vai_tro="editor", quality_mode="van_hoc"))
        self.assertEqual(prov.provider_id, "groq_gpt_oss_120b")

    def test_qwen_that_bai_fallback_dung_thu_tu_sang_gpt_oss_120b_roi_20b(self):
        """Vi du dung dac ta 3F: Qwen 429 -> GPT-OSS 120B -> GPT-OSS 20B."""
        qwen = _groq_cp("qwen", [ProviderRateLimited("het luot")])
        gpt120 = _groq_cp("gpt_oss_120b", [ProviderRateLimited("het luot")])
        gpt20 = _groq_cp("gpt_oss_20b", ["ok"])
        reg = ProviderRegistry([qwen, gpt120, gpt20])
        _, prov = reg.translate_segment(
            "x", context=TranslationContext(
                vai_tro="translator", quality_mode="can_bang"))
        self.assertEqual(prov.provider_id, "groq_gpt_oss_20b")
        self.assertEqual(qwen.provider.so_lan_goi, 1)
        self.assertEqual(gpt120.provider.so_lan_goi, 1)

    def test_manual_khong_bi_dinh_tuyen_lai(self):
        """MANUAL giu nguyen lua chon cua nguoi dung — dinh tuyen theo vai
        tro CHI ap dung cho AUTO (khong tu doi y nguoi dung da chon ro)."""
        qwen = _groq_cp("qwen", ["ok"])
        gpt120 = _groq_cp("gpt_oss_120b", ["ok"])
        reg = ProviderRegistry([qwen, gpt120])
        _, prov = reg.translate_segment(
            "x", context=TranslationContext(
                vai_tro="qa", quality_mode="can_bang"),
            mode="manual", selected_provider_id="groq_qwen")
        self.assertEqual(prov.provider_id, "groq_qwen")

    def test_khong_co_quality_mode_khong_dinh_tuyen_giu_nguyen_thu_tu_cau_hinh(self):
        qwen = _groq_cp("qwen", ["ok"])
        gpt120 = _groq_cp("gpt_oss_120b", ["ok"])
        reg = ProviderRegistry([gpt120, qwen])
        _, prov = reg.translate_segment(
            "x", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(prov.provider_id, "groq_gpt_oss_120b")

    def test_cloudflare_va_provider_khac_giu_nguyen_vi_tri_sau_nhom_groq(self):
        """Provider KHONG phai Groq curated khong bi dinh tuyen lai — chi
        noi TIEP SAU nhom Groq da sap (dung mau 3F)."""
        qwen = _groq_cp("qwen", [ProviderRateLimited("het luot")])
        gpt120 = _groq_cp("gpt_oss_120b", [ProviderRateLimited("het luot")])
        gpt20 = _groq_cp("gpt_oss_20b", [ProviderRateLimited("het luot")])
        cloudflare = ConfiguredProvider(
            provider_id="cloudflare", model_id="@cf/qwen",
            display_name="Cloudflare", quality_hint="miễn phí",
            provider=_FakeInnerProvider(["ok"]), free_tier=True)
        reg = ProviderRegistry([qwen, gpt120, gpt20, cloudflare])
        _, prov = reg.translate_segment(
            "x", context=TranslationContext(
                vai_tro="translator", quality_mode="can_bang"))
        self.assertEqual(prov.provider_id, "cloudflare")


class PerModelStatusIndependentTest(unittest.TestCase):
    """Phan 3E: mot model Groq bi rate-limit KHONG duoc lam sai trang thai
    cua model Groq KHAC — moi model la MOT `ConfiguredProvider` doc lap."""

    def test_qwen_rate_limited_gpt_oss_van_available(self):
        qwen = _groq_cp("qwen", [ProviderRateLimited("het luot")])
        gpt120 = _groq_cp("gpt_oss_120b", ["ok"])
        reg = ProviderRegistry([qwen, gpt120])
        reg.translate_segment(
            "x", context=TranslationContext(
                vai_tro="translator", quality_mode="can_bang"))
        catalog = {e.provider_id: e for e in reg.catalog()}
        self.assertEqual(catalog["groq_qwen"].status, ProviderStatus.RATE_LIMITED)
        self.assertEqual(catalog["groq_gpt_oss_120b"].status, ProviderStatus.AVAILABLE)


class BuildRegistryMultiModelTest(unittest.TestCase):
    """Phan 3B/3H: MOT `GROQ_API_KEY` -> BA entry catalog rieng biet."""

    def test_groq_api_key_don_le_sinh_ba_model_curated(self):
        reg = build_provider_registry(env={"GROQ_API_KEY": "gsk_x"})
        catalog = {e.provider_id: e for e in reg.catalog()}
        self.assertEqual(
            set(catalog.keys()),
            {"groq_qwen", "groq_gpt_oss_120b", "groq_gpt_oss_20b"})
        self.assertEqual(catalog["groq_qwen"].model_id, "qwen/qwen3.6-27b")
        self.assertEqual(catalog["groq_gpt_oss_120b"].model_id,
                         "openai/gpt-oss-120b")
        self.assertEqual(catalog["groq_gpt_oss_20b"].model_id,
                         "openai/gpt-oss-20b")

    def test_groq_model_cu_khop_mot_trong_ba_curated_khong_tao_trung(self):
        reg = build_provider_registry(env={
            "GROQ_API_KEY": "gsk_x", "GROQ_MODEL": "qwen/qwen3.6-27b"})
        ids = [e.provider_id for e in reg.catalog()]
        self.assertEqual(len(ids), 3)  # khong co "groq" trung voi "groq_qwen"
        self.assertNotIn("groq", ids)

    def test_groq_model_cu_khac_curated_them_vao_nhu_muc_rieng(self):
        reg = build_provider_registry(env={
            "GROQ_API_KEY": "gsk_x", "GROQ_MODEL": "llama-3.1-8b-instant"})
        ids = [e.provider_id for e in reg.catalog()]
        self.assertEqual(len(ids), 4)
        self.assertIn("groq", ids)


class BuildAllModelProvidersTest(unittest.TestCase):
    """Phan 3G: MOT ket noi Groq ca nhan -> BA `ConfiguredProvider`, cung
    api key da giai ma, KHONG can nhap key rieng cho tung model."""

    def setUp(self):
        from server.translation_byok_crypto import ByokCrypto, sinh_master_key_moi
        from server.translation_byok_service import ProviderConnectionService
        from server.translation_store import MockTranslationStore

        self.crypto = ByokCrypto.tu_moi_truong(sinh_master_key_moi())
        self.store = MockTranslationStore()
        self.svc = ProviderConnectionService(self.store, crypto=self.crypto)

    def test_ket_noi_groq_mo_rong_thanh_ba_model(self):
        import unittest.mock as mock

        with mock.patch(
            "server.translation_byok_service.kiem_tra_ket_noi_groq"):
            self.svc.connect("u1", "groq", "gsk_real_key_here",
                             selected_model="qwen/qwen3.6-27b")

        ds = self.svc.build_all_model_providers("u1", "groq")
        ids = {p.provider_id for p in ds}
        self.assertEqual(
            ids, {"groq_qwen", "groq_gpt_oss_120b", "groq_gpt_oss_20b"})
        for p in ds:
            self.assertEqual(p.credential_source, "personal")

    def test_khong_co_ket_noi_tra_danh_sach_rong(self):
        ds = self.svc.build_all_model_providers("u-khong-co", "groq")
        self.assertEqual(ds, [])

    def test_nguoi_dung_khac_khong_lay_duoc_model_cua_nguoi_nay(self):
        import unittest.mock as mock

        with mock.patch(
            "server.translation_byok_service.kiem_tra_ket_noi_groq"):
            self.svc.connect("owner", "groq", "gsk_real_key_here")

        ds = self.svc.build_all_model_providers("ke_khac", "groq")
        self.assertEqual(ds, [])


if __name__ == "__main__":
    unittest.main()
