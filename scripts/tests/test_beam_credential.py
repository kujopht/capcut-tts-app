"""`scripts/beam_credential.py::resolve_beam_token` — resolution order only.

Mission "REMOVE THE HUMAN FROM BEAM OPERATIONS" (2026-09-01): this must
never touch the real Windows Credential Manager (CI runs on Linux, and even
on Windows a test must not depend on operator-specific stored secrets) —
every case here mocks the environment and the broker's `fetch`.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PATH = os.path.join(_ROOT, "scripts", "beam_credential.py")


def _load():
    spec = importlib.util.spec_from_file_location("_beam_credential_qa", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ResolveBeamTokenTest(unittest.TestCase):
    def test_env_var_wins_when_present(self):
        mod = _load()
        with patch.dict(os.environ, {"BEAM_TOKEN": "from-env"}, clear=False):
            self.assertEqual(mod.resolve_beam_token(), "from-env")

    def test_falls_back_to_broker_when_env_absent(self):
        mod = _load()
        env_without_token = {k: v for k, v in os.environ.items()
                             if k != "BEAM_TOKEN"}
        fake_broker = type(sys)("fanfic_credential_broker")
        fake_broker.fetch = lambda name: "from-broker" if name == "BEAM_TOKEN" else None
        fake_broker.BrokerEnvironmentError = RuntimeError
        with patch.dict(os.environ, env_without_token, clear=True), \
             patch.dict(sys.modules, {"fanfic_credential_broker": fake_broker}), \
             patch.object(sys, "platform", "win32"):
            self.assertEqual(mod.resolve_beam_token(), "from-broker")

    def test_returns_none_when_both_absent(self):
        mod = _load()
        env_without_token = {k: v for k, v in os.environ.items()
                             if k != "BEAM_TOKEN"}
        fake_broker = type(sys)("fanfic_credential_broker")
        fake_broker.fetch = lambda name: None
        fake_broker.BrokerEnvironmentError = RuntimeError
        with patch.dict(os.environ, env_without_token, clear=True), \
             patch.dict(sys.modules, {"fanfic_credential_broker": fake_broker}), \
             patch.object(sys, "platform", "win32"):
            self.assertIsNone(mod.resolve_beam_token())

    def test_non_windows_skips_broker_entirely(self):
        """The broker is Windows-only (advapi32) — resolve_beam_token must
        not even attempt to import it elsewhere, so it degrades to
        env-var-only rather than raising on an unsupported platform."""
        mod = _load()
        env_without_token = {k: v for k, v in os.environ.items()
                             if k != "BEAM_TOKEN"}
        with patch.dict(os.environ, env_without_token, clear=True), \
             patch.object(sys, "platform", "linux"):
            self.assertIsNone(mod.resolve_beam_token())


if __name__ == "__main__":
    unittest.main()
