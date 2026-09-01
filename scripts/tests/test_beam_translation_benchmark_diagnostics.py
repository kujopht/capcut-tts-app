"""`scripts/beam_translation_benchmark.py::_safe_wait_diagnostic` — must
never leak secrets and must degrade gracefully when the provider is
missing. Mission "REMOVE THE HUMAN FROM BEAM OPERATIONS" muc F.
"""
from __future__ import annotations

import importlib.util
import os
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PATH = os.path.join(_ROOT, "scripts", "beam_translation_benchmark.py")


def _load():
    spec = importlib.util.spec_from_file_location("_benchmark_diag_qa", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeEntry:
    def __init__(self, provider_id, error_class, reset_at):
        self.provider_id = provider_id
        self.error_class = error_class
        self.reset_at = reset_at


class _FakeConfiguredProvider:
    def __init__(self, entry):
        self._entry = entry

    def catalog_entry(self):
        return self._entry


class _FakeRegistry:
    def __init__(self, providers):
        self._providers = providers

    def get(self, provider_id):
        return self._providers.get(provider_id)


class SafeWaitDiagnosticTest(unittest.TestCase):
    def test_reports_provider_error_class_and_retry_at(self):
        mod = _load()
        reg = _FakeRegistry({"custom": _FakeConfiguredProvider(
            _FakeEntry("custom", "transient", "2026-09-01T00:00:20+00:00"))})
        out = mod._safe_wait_diagnostic(reg, "custom")
        self.assertIn("provider_id=custom", out)
        self.assertIn("error_class=transient", out)
        self.assertIn("2026-09-01T00:00:20+00:00", out)

    def test_missing_provider_degrades_gracefully(self):
        mod = _load()
        reg = _FakeRegistry({})
        out = mod._safe_wait_diagnostic(reg, "custom")
        self.assertIsInstance(out, str)
        self.assertTrue(out)

    def test_never_contains_secret_shaped_substrings(self):
        """Regression guard: whatever this prints, it must never look like
        it echoed a token/header — a real API key/bearer value would never
        legitimately appear in provider_id/error_class/reset_at."""
        mod = _load()
        reg = _FakeRegistry({"custom": _FakeConfiguredProvider(
            _FakeEntry("custom", "permanent", ""))})
        out = mod._safe_wait_diagnostic(reg, "custom")
        for forbidden in ("bearer", "authorization", "api_key", "token="):
            self.assertNotIn(forbidden, out.lower())


if __name__ == "__main__":
    unittest.main()
