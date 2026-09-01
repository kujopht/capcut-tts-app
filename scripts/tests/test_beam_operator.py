"""`scripts/beam_operator.py` — pure logic only: JSON parsing, wait-ready
classification. No real `beam` subprocess, no real HTTP call, no real
credential — mission "REMOVE THE HUMAN FROM BEAM OPERATIONS" (2026-09-01).
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PATH = os.path.join(_ROOT, "scripts", "beam_operator.py")


def _load():
    spec = importlib.util.spec_from_file_location("_beam_operator_qa", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class BeamSubprocessEnvTest(unittest.TestCase):
    def test_sets_ci_and_utf8_encoding_without_mutating_process_env(self):
        """Two separate real Windows console crashes (2026-09-01): the
        interactive first-auth banner (CI=1) and a plain UnicodeEncodeError
        in `rich`'s legacy console writer during normal deploy output
        (PYTHONIOENCODING=utf-8) - both must be set on every beam
        subprocess call, and neither may leak into this process's own env."""
        mod = _load()
        before = dict(os.environ)
        env = mod._beam_subprocess_env("tok")
        self.assertEqual(env["CI"], "1")
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(env[mod.TOKEN_ENV_VAR], "tok")
        self.assertEqual(dict(os.environ), before)


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

    def test_forward_slash_handler_normalized_to_os_separator(self):
        """Real bug (2026-09-01): beta9's own load_module_spec converts a
        handler path to a module name via
        `.replace(os.path.sep, ".")` - on Windows that's a backslash, so a
        forward-slash handler (this repo's own convention everywhere)
        silently failed with ModuleNotFoundError, never reaching Beam's
        gateway. cmd_deploy_endpoint must normalize before shelling out."""
        mod = _load()
        fake_result = MagicMock(returncode=0, stdout=json.dumps({
            "deployment_id": "dep_1", "invoke_url": "https://x.app.beam.cloud",
        }), stderr="")
        with patch("subprocess.run", return_value=fake_result) as mock_run:
            mod.cmd_deploy_endpoint("beam_apps/foo.py:handler", "tok")
        argv = mock_run.call_args[0][0]
        handler_arg = argv[argv.index("deploy") + 1]
        self.assertEqual(handler_arg, "beam_apps/foo.py:handler".replace("/", os.sep))


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

    def test_transformers_kind_posts_to_health_not_v1_models(self):
        """Mission 'HY-MT2 1.8B TRANSFORMERS FALLBACK' muc E: the old
        vLLM /v1/models readiness signal is meaningless for this
        architecture - wait-ready must POST to /health instead."""
        mod = _load()
        fake_client = MagicMock()
        fake_client.__enter__.return_value.post.return_value = httpx.Response(200)
        with patch("httpx.Client", return_value=fake_client):
            result = mod.cmd_wait_ready(
                "https://x.app.beam.cloud", "tok", kind="transformers",
                max_wait_seconds=30)
        self.assertEqual(result["status"], "READY")
        called_url = fake_client.__enter__.return_value.post.call_args[0][0]
        self.assertTrue(called_url.endswith("/health"))
        fake_client.__enter__.return_value.get.assert_not_called()


class SecretRedactionTest(unittest.TestCase):
    """Real incident, 2026-09-01: an early cmd_deploy_vllm() implementation
    called print_invocation_snippet(), which prints a curl snippet
    containing 'Authorization: Bearer <the real BEAM_TOKEN>' straight to
    stdout - that leaked into a background-task log file and this
    conversation's transcript before being caught and redeployed around.
    These tests guard the fix and the defense-in-depth redaction layer
    added afterward - they must never regress."""

    def test_redact_secrets_strips_bearer_value(self):
        mod = _load()
        text = ("curl -X POST 'https://x' -H 'Authorization: Bearer "
               "9cayz2Fpxa-QLfWyqfwxLpIUsy7v7uwXApPd3bxNS1Y8LmGhLUTSNQWDz1w=='")
        out = mod._redact_secrets(text)
        self.assertNotIn("9cayz2Fpxa", out)
        self.assertIn("Bearer <redacted>", out)

    def test_redact_secrets_handles_empty_and_none_like_input(self):
        mod = _load()
        self.assertEqual(mod._redact_secrets(""), "")

    def test_cmd_deploy_vllm_never_calls_print_invocation_snippet(self):
        """The real fix: URL discovery must go through gateway_stub.get_url
        directly, never through print_invocation_snippet (which prints the
        secret as a side effect with no way to suppress it). Behavioral
        check, not a source-text grep, so it can't be fooled by comments
        that merely mention the method name (as the incident's own
        docstring in this file does)."""
        import tempfile

        class _FakeGatewayStub:
            def get_url(self, request):
                return type("R", (), {"ok": True, "url": "https://fake.beam.cloud"})()

        class _FakeVLLM:
            name = "hymt2-1-8b"
            stub_id = "stub-1"
            deployment_id = "dep-1"
            gateway_stub = _FakeGatewayStub()

            def deploy(self, name=None, invocation_details_func=None):
                if invocation_details_func:
                    invocation_details_func()
                return {"deployment_id": self.deployment_id}, True

            def print_invocation_snippet(self, *a, **kw):
                raise AssertionError(
                    "cmd_deploy_vllm must never call print_invocation_snippet "
                    "- it prints the real BEAM_TOKEN to stdout as a side "
                    "effect (see this file's real 2026-09-01 incident)")

        mod = _load()
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("hymt2_1_8b = None\n")
            handler_path = f.name
        try:
            with patch("importlib.util.module_from_spec") as fake_from_spec:
                fake_module = type(sys)("fake_handler")
                fake_module.hymt2_1_8b = _FakeVLLM()
                fake_from_spec.return_value = fake_module
                with patch("importlib.util.spec_from_file_location"):
                    result = mod.cmd_deploy_vllm(f"{handler_path}:hymt2_1_8b", "tok")
        finally:
            os.unlink(handler_path)
        self.assertEqual(result["status"], "DEPLOYED")
        self.assertEqual(result["invoke_url"], "https://fake.beam.cloud")

    def test_deploy_endpoint_stderr_is_redacted_on_failure(self):
        mod = _load()
        fake_result = MagicMock(
            returncode=1, stdout="",
            stderr="failed: Authorization: Bearer abcdEFGH12345678ijkl")
        with patch("subprocess.run", return_value=fake_result):
            result = mod.cmd_deploy_endpoint("app.py:generate", "tok")
        self.assertNotIn("abcdEFGH12345678ijkl", result["stderr"])

    def test_list_filters_out_connection_string_secret(self):
        """`Deployment` proto messages carry `connection_string_secret` for
        database-kind deployments - cmd_list must never forward it, even
        though this repo only deploys VLLM/endpoint apps today."""
        mod = _load()
        fake_result = MagicMock(returncode=0, stdout=json.dumps([
            {"id": "d1", "name": "some-db", "active": True,
             "stub_type": "database", "connection_string_secret": "sekret",
             "connection_env_name": "DATABASE_URL"},
        ]), stderr="")
        with patch("subprocess.run", return_value=fake_result), \
             patch.object(mod, "_beam_executable", return_value="beam"):
            result = mod.cmd_list("tok")
        self.assertEqual(result["status"], "OK")
        dumped = json.dumps(result["deployments"])
        self.assertNotIn("sekret", dumped)
        self.assertNotIn("connection_string_secret", dumped)


class CheckPayloadSizeTest(unittest.TestCase):
    """Real incident, 2026-09-01: `beam deploy` collected 2.64 GB per
    deploy because `.beamignore` didn't cover this repo's own large
    directories (.router/ worktrees, .claude/worktrees/) - fixed by
    extending .beamignore. This is the automated sanity check mission
    muc 5 asked for: treat >500MB (before model weights, which never
    live in the local repo) as a packaging regression."""

    def test_real_repo_payload_is_under_threshold(self):
        """Regression guard against the ACTUAL current .beamignore and
        repo tree - this is what would have caught the 2.64 GB incident
        before ever running a real (billed) deploy."""
        mod = _load()
        result = mod.cmd_check_payload_size()
        self.assertEqual(result["status"], "OK",
                         f"deploy payload regression: {result}")
        self.assertLess(result["total_mb"], 500.0)

    def test_missing_beamignore_reports_error(self):
        import tempfile
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            result = mod.cmd_check_payload_size(repo_root=Path(tmp))
        self.assertEqual(result["status"], "ERROR")

    def test_large_untracked_directory_triggers_regression(self):
        """Isolated fixture, not the real repo: a big file NOT covered by
        any ignore pattern must be caught, proving the check actually
        measures real bytes rather than trusting the ignore list blindly."""
        import tempfile
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".beamignore").write_text(".venv\n", encoding="utf-8")
            (root / "beam_apps").mkdir()
            (root / "beam_apps" / "app.py").write_text("x = 1\n", encoding="utf-8")
            big = root / "big_untracked_blob.bin"
            with open(big, "wb") as f:
                f.seek(mod.PAYLOAD_SIZE_REGRESSION_THRESHOLD_BYTES + 1024)
                f.write(b"\0")
            result = mod.cmd_check_payload_size(repo_root=root)
        self.assertEqual(result["status"], "REGRESSION")
        self.assertIn("big_untracked_blob.bin",
                      [f["path"] for f in result["largest_files"]])

    def test_ignored_directory_is_pruned_not_just_filtered(self):
        """Pruning during os.walk (like beta9's own _collect_files) means
        an ignored directory's contents are never even statted - functional
        proof: a huge file INSIDE an ignored dir must not count."""
        import tempfile
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".beamignore").write_text(".router\n", encoding="utf-8")
            (root / "beam_apps").mkdir()
            (root / "beam_apps" / "app.py").write_text("x = 1\n", encoding="utf-8")
            router_dir = root / ".router" / "worktrees"
            router_dir.mkdir(parents=True)
            with open(router_dir / "huge.bin", "wb") as f:
                f.seek(2 * 1024 * 1024)
                f.write(b"\0")
            result = mod.cmd_check_payload_size(repo_root=root)
        self.assertEqual(result["status"], "OK")
        self.assertLess(result["total_mb"], 1.0)


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
