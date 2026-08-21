"""
`POST /api/tools/subtitles/translate` — overnight Phase 4, Phan 4E/4F.

Dich TUNG DONG doc lap qua registry chung cua Translation Studio, KHONG tao
TranslationProject/job rieng — kiem tra dich vu THAT (Mock provider, khong
can Groq that) va cac rao chan (dang nhap bat buoc, gioi han so dong).
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.translation_provider_registry import (
    ConfiguredProvider,
    ProviderRegistry,
)
from server.translation_providers import TranslationProviderError


class _FakeProvider:
    name = "fake"

    def translate_segment(self, text, *, context):
        return f"[dịch] {text}"


class _FakeFailingProvider:
    name = "fake-fail"

    def translate_segment(self, text, *, context):
        raise TranslationProviderError("hết hạn mức")


class SubtitleTranslateRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self.client = TestClient(server_main.app)
        self._registry_cu = server_main.translation_registry

    def tearDown(self) -> None:
        server_main.translation_registry = self._registry_cu

    def _dang_ky(self) -> str:
        r = self.client.post("/api/auth/register", json={
            "email": "sub-translate-qa@example.com", "password": "matkhau123"})
        return r.json()["token"]

    def test_khong_dang_nhap_bi_tu_choi(self):
        resp = self.client.post("/api/tools/subtitles/translate",
                                json={"texts": ["你好"]})
        self.assertEqual(resp.status_code, 401)

    def test_dich_thanh_cong(self):
        server_main.translation_registry = ProviderRegistry([
            ConfiguredProvider(provider_id="fake", model_id="m",
                              display_name="Fake", quality_hint="test",
                              provider=_FakeProvider()),
        ])
        tok = self._dang_ky()
        resp = self.client.post(
            "/api/tools/subtitles/translate",
            json={"texts": ["你好", "  ", "再见"]},
            headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["translated"], ["[dịch] 你好", "", "[dịch] 再见"])

    def test_danh_sach_rong_tra_400(self):
        tok = self._dang_ky()
        resp = self.client.post(
            "/api/tools/subtitles/translate", json={"texts": []},
            headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(resp.status_code, 400)

    def test_qua_gioi_han_dong_tra_400(self):
        tok = self._dang_ky()
        resp = self.client.post(
            "/api/tools/subtitles/translate",
            json={"texts": ["x"] * 51},
            headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(resp.status_code, 400)

    def test_tat_ca_provider_het_han_muc_tra_503(self):
        server_main.translation_registry = ProviderRegistry([
            ConfiguredProvider(provider_id="fake", model_id="m",
                              display_name="Fake", quality_hint="test",
                              provider=_FakeFailingProvider()),
        ])
        tok = self._dang_ky()
        resp = self.client.post(
            "/api/tools/subtitles/translate", json={"texts": ["你好"]},
            headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(resp.status_code, 503)

    def test_khong_co_provider_nao_tra_503(self):
        server_main.translation_registry = ProviderRegistry([])
        tok = self._dang_ky()
        resp = self.client.post(
            "/api/tools/subtitles/translate", json={"texts": ["你好"]},
            headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(resp.status_code, 503)


if __name__ == "__main__":
    unittest.main()
