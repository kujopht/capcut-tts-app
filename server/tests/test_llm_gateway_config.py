"""`server/config.py::LlmGatewaySettings` — theo khuon test_image_studio_config.py."""

from __future__ import annotations

import os
import unittest

from server.config import load_settings, reset_settings

_TOUCHED = (
    "FAS_ENV_FILE", "LLM_OPENAI_API_KEY", "LLM_OPENAI_BASE_URL",
    "LLM_OPENROUTER_API_KEY", "LLM_OPENROUTER_BASE_URL", "LLM_GEMINI_API_KEY",
    "LLM_ANTHROPIC_API_KEY", "LLM_SELF_HOSTED_BASE_URL", "LLM_SELF_HOSTED_API_KEY",
)


class LlmGatewaySettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {name: os.environ.get(name) for name in _TOUCHED}
        for name in _TOUCHED:
            os.environ.pop(name, None)
        os.environ["FAS_ENV_FILE"] = ""
        reset_settings()

    def tearDown(self) -> None:
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        reset_settings()

    def test_no_env_vars_no_provider_configured(self):
        s = load_settings().llm_gateway
        self.assertFalse(s.any_provider_configured)
        self.assertEqual(s.openai_base_url, "https://api.openai.com/v1")
        self.assertEqual(s.openrouter_base_url, "https://openrouter.ai/api/v1")

    def test_setting_one_key_makes_any_provider_configured_true(self):
        os.environ["LLM_GEMINI_API_KEY"] = "k"
        reset_settings()
        s = load_settings().llm_gateway
        self.assertTrue(s.any_provider_configured)
        self.assertTrue(s.gemini_api_key)

    def test_describe_never_leaks_the_actual_key(self):
        os.environ["LLM_OPENAI_API_KEY"] = "sk-super-secret"
        reset_settings()
        s = load_settings().llm_gateway
        described = s.describe()
        self.assertNotIn("sk-super-secret", str(described))
        self.assertTrue(described["openai_configured"])

    def test_settings_describe_includes_llm_gateway_section(self):
        described = load_settings().describe()
        self.assertIn("llm_gateway", described)

    def test_self_hosted_base_url_configures_without_requiring_a_key(self):
        os.environ["LLM_SELF_HOSTED_BASE_URL"] = "http://localhost:8080/v1"
        reset_settings()
        s = load_settings().llm_gateway
        self.assertTrue(s.any_provider_configured)
        self.assertTrue(s.describe()["self_hosted_configured"])


if __name__ == "__main__":
    unittest.main()
