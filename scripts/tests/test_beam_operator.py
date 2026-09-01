"""`scripts/beam_operator.py` — pure logic only: JSON parsing, wait-ready
classification. No real `beam` subprocess, no real HTTP call, no real
credential — mission "REMOVE THE HUMAN FROM BEAM OPERATIONS" (2026-09-01).
"""
from __future__ import annotations

import importlib.util
import json
import os
import unittest
from unittest.mock import MagicMock, patch

import httpx

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PATH = os.path.join(_ROOT, "scripts", "beam_operator.py")


def _load():
    spec = importlib.util.spec_from_file_location("_beam_operator_qa", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DeployEndpointParsingTest(unittest.TestCase):
    def test_clean_json_response_extracts_fields(self):
        mod = _load()
        fake_result = MagicMock(returncode=0, stdout=json.dumps({
            "deployment_id": "dep_1", "deployment_name": "cover-illustrious",
            "invoke_url": "https://x.app.beam.cloud", "version": 3,
        }), stderr="")
        with patch("subprocess.run", return_value=fake_result):
            result = mod.cmd_deploy_endpoint("app.py:generate", "tok")
        self.assertEqual(result["status"], "DEPLOYED")
        self.assertEqual(result["invoke_url"], "https://x.app.beam.cloud")
        self.assertEqual(result["deployment_id"], "dep_1")

    def test_nonzero_exit_is_deploy_failed_not_a_crash(self):
        mod = _load()
        fake_result = MagicMock(returncode=1, stdout="", stderr="auth error")
        with patch("subprocess.run", return_value=fake_result):
            result = mod.cmd_deploy_endpoint("app.py:generate", "tok")
        self.assertEqual(result["status"], "DEPLOY_FAILED")

    def test_beam_binary_missing_reports_error_not_traceback(self):
        mod = _load()
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = mod.cmd_deploy_endpoint("app.py:generate", "tok")
        self.assertEqual(result["status"], "ERROR")

    def test_zero_exit_but_garbage_stdout_reports_error_not_crash(self):
        """`beam deploy` exiting 0 with non-JSON stdout must be reported as
        a structured error, never let a JSONDecodeError escape uncaught."""
        mod = _load()
        fake_result = MagicMock(returncode=0, stdout="not json at all", stderr="")
        with patch("subprocess.run", return_value=fake_result):
            result = mod.cmd_deploy_endpoint("app.py:generate", "tok")
        self.assertEqual(result["status"], "ERROR")


class WaitReadyClassificationTest(unittest.TestCase):
    """Mission muc D: readiness check phai la MOT lan goi /v1/models nhe -
    KHONG sinh token, va phan biet loi TAM THOI (thu lai) vs that bai THAT
    (dung ngay)."""

    def test_200_is_ready_on_first_attempt(self):
        mod = _load()
        fake_client = MagicMock()
        fake_client.__enter__.return_value.get.return_value = httpx.Response(200)
        with patch("httpx.Client", return_value=fake_client):
            result = mod.cmd_wait_ready(
                "https://x.app.beam.cloud", "tok", kind="vllm",
                max_wait_seconds=30)
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["attempts"], 1)

    def test_401_fails_immediately_no_retry(self):
        """401 la loi xac thuc THAT (khong nam trong danh sach tam thoi) -
        phai dung NGAY, khong duoc phep thu lai roi in waiting mai."""
        mod = _load()
        fake_client = MagicMock()
        fake_client.__enter__.return_value.get.return_value = httpx.Response(401)
        with patch("httpx.Client", return_value=fake_client):
            result = mod.cmd_wait_ready(
                "https://x.app.beam.cloud", "tok", kind="vllm",
                max_wait_seconds=30)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["attempts"], 1)

    def test_503_then_200_recovers_within_budget(self):
        """503 (serverless dang khoi dong) PHAI duoc coi la tam thoi va
        thu lai - khong duoc dung ngay nhu 401."""
        mod = _load()
        responses = [httpx.Response(503), httpx.Response(200)]
        fake_client = MagicMock()
        fake_client.__enter__.return_value.get.side_effect = responses
        with patch("httpx.Client", return_value=fake_client), \
             patch("time.sleep"):
            result = mod.cmd_wait_ready(
                "https://x.app.beam.cloud", "tok", kind="vllm",
                max_wait_seconds=30, initial_delay_seconds=0.01)
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["attempts"], 2)

    def test_persistent_transient_error_times_out_bounded(self):
        """Loi 503 lien tuc PHAI dung lai sau max_wait_seconds, khong
        duoc phep poll vo han. Dung mot ngan sach that RAT nho (khong
        mock time.monotonic - qua nhieu diem goi noi bo de dem chinh
        xac) va patch time.sleep de test khong that su cho."""
        mod = _load()
        fake_client = MagicMock()
        fake_client.__enter__.return_value.get.return_value = httpx.Response(503)
        with patch("httpx.Client", return_value=fake_client), \
             patch("time.sleep"):
            result = mod.cmd_wait_ready(
                "https://x.app.beam.cloud", "tok", kind="vllm",
                max_wait_seconds=0.05, initial_delay_seconds=0.01)
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertGreaterEqual(result["attempts"], 1)

    def test_unsupported_kind_rejected(self):
        mod = _load()
        result = mod.cmd_wait_ready("https://x", "tok", kind="endpoint")
        self.assertEqual(result["status"], "ERROR")


class CheckVersionTest(unittest.TestCase):
    def test_matching_version_reports_ok(self):
        mod = _load()
        fake_result = MagicMock(
            returncode=0,
            stdout=f"Name: beam-client\nVersion: {mod.BEAM_CLIENT_TESTED_VERSION}\n")
        with patch("subprocess.run", return_value=fake_result):
            result = mod.cmd_check_version()
        self.assertEqual(result["status"], "OK")

    def test_mismatched_version_warns_but_does_not_silently_pass(self):
        mod = _load()
        fake_result = MagicMock(
            returncode=0, stdout="Name: beam-client\nVersion: 0.1.1\n")
        with patch("subprocess.run", return_value=fake_result):
            result = mod.cmd_check_version()
        self.assertEqual(result["status"], "VERSION_MISMATCH")
        self.assertTrue(result["note"])

    def test_not_installed_reports_install_command(self):
        mod = _load()
        fake_result = MagicMock(returncode=1, stdout="")
        with patch("subprocess.run", return_value=fake_result):
            result = mod.cmd_check_version()
        self.assertEqual(result["status"], "NOT_INSTALLED")
        self.assertIn("pip install beam-client", result["install_command"])


if __name__ == "__main__":
    unittest.main()
