"""Ke toan pool mien phi — overnight Phase 3, Phan 3I."""

from __future__ import annotations

import unittest
from dataclasses import replace

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.translation_provider_registry import (
    ConfiguredProvider,
    ProviderRateLimited,
    ProviderRegistry,
)
from server.translation_providers import TranslationContext, TranslationProviderError
from server.translation_usage import UsageRecorder, usage_recorder


class _FakeInnerProvider:
    name = "fake"

    def __init__(self, kich_ban):
        self._kich_ban = list(kich_ban)

    def translate_segment(self, text, *, context):
        hanh_dong = self._kich_ban.pop(0) if self._kich_ban else "ok"
        if hanh_dong == "ok":
            return f"[{self.name}] {text}"
        raise hanh_dong


class UsageRecorderTest(unittest.TestCase):
    def test_ghi_va_doc_lai(self):
        rec = UsageRecorder()
        rec.ghi(provider_id="groq_qwen", model_id="qwen/qwen3.6-27b",
               credential_source="shared", pass_type="translator",
               outcome="success", latency_ms=120)
        su_kien = rec.gan_day(10)
        self.assertEqual(len(su_kien), 1)
        self.assertEqual(su_kien[0].provider_id, "groq_qwen")
        self.assertEqual(su_kien[0].outcome, "success")

    def test_khong_bao_gio_ghi_credential(self):
        """`UsageEvent` khong co truong nao cho api key/secret — kiem tra
        TEN TRUONG cu the, khong phai substring tho tren toan chuoi: kiem tra
        do (thay vi ten truong) se bao loi GIA voi `input_tokens`/
        `output_tokens` (dem SO LUONG token dich — hop phap, khong phai bi
        mat) vi chuoi do TINH CO chua chu "token"."""
        rec = UsageRecorder()
        rec.ghi(provider_id="groq_qwen", model_id="qwen/qwen3.6-27b",
               credential_source="personal", pass_type="translator",
               outcome="success", latency_ms=10)
        d = rec.gan_day(1)[0].to_dict()
        for truong_cam in ("api_key", "secret", "authorization", "key"):
            self.assertNotIn(truong_cam, d)

    def test_tom_tat_theo_model_dem_dung(self):
        rec = UsageRecorder()
        for _ in range(3):
            rec.ghi(provider_id="groq_qwen", model_id="qwen/qwen3.6-27b",
                   credential_source="shared", pass_type="translator",
                   outcome="success", latency_ms=100)
        rec.ghi(provider_id="groq_qwen", model_id="qwen/qwen3.6-27b",
               credential_source="shared", pass_type="translator",
               outcome="rate_limited", latency_ms=50)
        rec.ghi(provider_id="groq_gpt_oss_120b", model_id="openai/gpt-oss-120b",
               credential_source="shared", pass_type="editor",
               outcome="success", latency_ms=200)

        tt = rec.tom_tat_theo_model()
        self.assertEqual(tt["groq_qwen"]["total"], 4)
        self.assertEqual(tt["groq_qwen"]["success"], 3)
        self.assertEqual(tt["groq_qwen"]["rate_limited"], 1)
        self.assertEqual(tt["groq_gpt_oss_120b"]["total"], 1)

    def test_gioi_han_ghi_de_vong_khong_phinh_vo_han(self):
        rec = UsageRecorder()
        rec.GIOI_HAN = 5
        for i in range(10):
            rec.ghi(provider_id="groq_qwen", model_id="m",
                   credential_source="shared", pass_type="translator",
                   outcome="success", latency_ms=i)
        self.assertEqual(len(rec.gan_day(100)), 5)


class ConfiguredProviderReportsUsageTest(unittest.TestCase):
    """`ConfiguredProvider.translate_segment` phai bao ve recorder TOAN CUC —
    day la duong that duoc dung khi dich (khac test ghi/doc truc tiep o
    tren, chi kiem cau truc `UsageRecorder`)."""

    def setUp(self):
        usage_recorder()._su_kien.clear()

    def test_thanh_cong_ghi_mot_su_kien_success(self):
        cp = ConfiguredProvider(
            provider_id="groq_qwen", model_id="qwen/qwen3.6-27b",
            display_name="Qwen", quality_hint="test",
            provider=_FakeInnerProvider(["ok"]))
        cp.translate_segment("x", context=TranslationContext(vai_tro="translator"))
        gan_day = usage_recorder().gan_day(1)
        self.assertEqual(gan_day[-1].provider_id, "groq_qwen")
        self.assertEqual(gan_day[-1].outcome, "success")
        self.assertEqual(gan_day[-1].pass_type, "translator")

    def test_rate_limited_ghi_dung_ket_qua(self):
        cp = ConfiguredProvider(
            provider_id="groq_qwen", model_id="qwen/qwen3.6-27b",
            display_name="Qwen", quality_hint="test",
            provider=_FakeInnerProvider([ProviderRateLimited("cham")]))
        with self.assertRaises(ProviderRateLimited):
            cp.translate_segment("x", context=TranslationContext(vai_tro="qa"))
        gan_day = usage_recorder().gan_day(1)
        self.assertEqual(gan_day[-1].outcome, "rate_limited")
        self.assertEqual(gan_day[-1].pass_type, "qa")


class AdminUsageRouteTest(unittest.TestCase):
    def setUp(self):
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self.client = TestClient(server_main.app)
        usage_recorder()._su_kien.clear()

    def test_khong_dang_nhap_bi_tu_choi(self):
        resp = self.client.get("/api/admin/translate/usage")
        self.assertEqual(resp.status_code, 401)

    def test_dang_nhap_nhung_khong_phai_admin_bi_tu_choi(self):
        r = self.client.post("/api/auth/register", json={
            "email": "usage-qa@example.com", "password": "matkhau123"})
        tok = r.json()["token"]
        resp = self.client.get("/api/admin/translate/usage",
                               headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(resp.status_code, 403)

    def test_admin_xem_duoc_tom_tat(self):
        r = self.client.post("/api/auth/register", json={
            "email": "usage-admin@example.com", "password": "matkhau123"})
        profile = r.json()["profile"]
        tok = r.json()["token"]
        settings_cu = server_main.settings
        server_main.settings = replace(
            server_main.settings, admin_user_ids=(profile["user_id"],))
        try:
            usage_recorder().ghi(
                provider_id="groq_qwen", model_id="qwen/qwen3.6-27b",
                credential_source="shared", pass_type="translator",
                outcome="success", latency_ms=42)
            resp = self.client.get("/api/admin/translate/usage",
                                   headers={"Authorization": f"Bearer {tok}"})
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertIn("groq_qwen", body["summary_by_provider"])
            self.assertEqual(len(body["recent_events"]), 1)
        finally:
            server_main.settings = settings_cu


if __name__ == "__main__":
    unittest.main()
