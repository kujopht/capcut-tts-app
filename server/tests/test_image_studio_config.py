"""`server/config.py::ImageStudioSettings` — PHASE 7, theo khuon test_env_loading.py."""

from __future__ import annotations

import os
import unittest

from server.config import ConfigError, load_settings, reset_settings

_TOUCHED = (
    "FAS_ENV_FILE", "IMAGE_SHARED_PREMIUM_ENABLED", "IMAGE_MONTHLY_BUDGET_USD",
    "IMAGE_WARNING_BUDGET_USD", "IMAGE_MAX_COST_PER_REQUEST_USD",
    "IMAGE_MAX_CONCURRENT_SHARED_GENERATIONS", "IMAGE_MARKUP_MULTIPLIER",
    "IMAGE_DISABLED_MODELS", "POLLINATIONS_API_KEY", "POLLINATIONS_CLIENT_ID",
    "IMAGE_BYOP_MASTER_KEY", "IMAGE_BYOP_REDIRECT_URI",
)


class ImageStudioSettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {name: os.environ.get(name) for name in _TOUCHED}
        for name in _TOUCHED:
            os.environ.pop(name, None)
        os.environ["FAS_ENV_FILE"] = ""  # khong nap .env that cua may nay
        reset_settings()

    def tearDown(self) -> None:
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        reset_settings()

    def test_mac_dinh_tat_shared_premium(self):
        s = load_settings().image_studio
        self.assertFalse(s.shared_premium_enabled)
        self.assertFalse(s.shared_premium_configured)
        self.assertEqual(s.monthly_budget_usd, 20.0)
        self.assertEqual(s.warning_budget_usd, 15.0)
        self.assertEqual(s.max_concurrent_shared_generations, 3)

    def test_bat_nhung_thieu_key_thi_van_chua_configured(self):
        os.environ["IMAGE_SHARED_PREMIUM_ENABLED"] = "true"
        s = load_settings().image_studio
        self.assertTrue(s.shared_premium_enabled)
        self.assertFalse(s.shared_premium_configured)  # thieu POLLINATIONS_API_KEY

    def test_bat_va_co_key_thi_configured(self):
        os.environ["IMAGE_SHARED_PREMIUM_ENABLED"] = "true"
        os.environ["POLLINATIONS_API_KEY"] = "sk-fake-for-test"
        s = load_settings().image_studio
        self.assertTrue(s.shared_premium_configured)

    def test_bien_moi_truong_ghi_de_duoc_ngan_sach(self):
        os.environ["IMAGE_MONTHLY_BUDGET_USD"] = "500"
        os.environ["IMAGE_WARNING_BUDGET_USD"] = "400"
        os.environ["IMAGE_MAX_CONCURRENT_SHARED_GENERATIONS"] = "10"
        s = load_settings().image_studio
        self.assertEqual(s.monthly_budget_usd, 500.0)
        self.assertEqual(s.warning_budget_usd, 400.0)
        self.assertEqual(s.max_concurrent_shared_generations, 10)

    def test_ngan_sach_khong_phai_so_thi_fail_fast(self):
        os.environ["IMAGE_MONTHLY_BUDGET_USD"] = "khong-phai-so"
        with self.assertRaises(ConfigError):
            load_settings()

    def test_danh_sach_model_tat_duoc_doc_tach_dau_phay(self):
        os.environ["IMAGE_DISABLED_MODELS"] = "kontext, nanobanana"
        s = load_settings().image_studio
        self.assertEqual(s.disabled_models, ("kontext", "nanobanana"))

    def test_byop_configured_can_du_ca_ba_bien(self):
        os.environ["POLLINATIONS_CLIENT_ID"] = "pk_test"
        os.environ["IMAGE_BYOP_MASTER_KEY"] = "khong-quan-trong-dinh-dang-o-day"
        s = load_settings().image_studio
        self.assertFalse(s.byop_configured)  # thieu redirect uri
        os.environ["IMAGE_BYOP_REDIRECT_URI"] = "https://vidu.test/callback"
        reset_settings()
        s = load_settings().image_studio
        self.assertTrue(s.byop_configured)

    def test_describe_khong_bao_gio_chua_secret(self):
        os.environ["POLLINATIONS_API_KEY"] = "sk-secret-value-khong-duoc-lo"
        os.environ["IMAGE_BYOP_MASTER_KEY"] = "secret-master-key-khong-duoc-lo"
        s = load_settings().image_studio
        mo_ta = s.describe()
        chuoi = str(mo_ta)
        self.assertNotIn("sk-secret-value-khong-duoc-lo", chuoi)
        self.assertNotIn("secret-master-key-khong-duoc-lo", chuoi)


if __name__ == "__main__":
    unittest.main()
