"""
Regression guard for `beam_apps/translation_hymt2_transformers_app.py` —
mission "HY-MT2 1.8B TRANSFORMERS FALLBACK, NO MANAGED VLLM" (2026-09-01).

Same fake-`beam`-module technique as test_cover_illustrious_app_signature.py
(`beam` is a remote-deploy-only dependency, `torch` is a GPU-container-only
dependency — NEITHER is installed in this repo's dev venv, confirmed via
`pip show torch`/`pip show beam-client` before writing this file). Routes
that internally `import torch` (`/chat/completions`) are verified by
REGISTRATION (path exists on the real FastAPI app, built by really calling
`web_server(context)`) rather than by EXECUTION — this file follows
`cover_illustrious_app.py`'s own established pattern of never faking torch
tensor behavior, only ever inspecting real signatures/kwargs/routes.
`/health` has no torch dependency in its body and IS executed for real
against a fake tokenizer/model.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _load_module_with_fake_beam():
    fake_beam = types.ModuleType("beam")
    captured_asgi_kwargs = {}

    class _FakeImage:
        def __init__(self, *a, **kw):
            self.packages = []

        def add_python_packages(self, packages, *a, **kw):
            self.packages = list(packages)
            return self

    class _FakeVolume:
        def __init__(self, *, name="", mount_path="", **kw):
            self.name = name
            self.mount_path = mount_path

    def _fake_asgi(**kw):
        captured_asgi_kwargs.update(kw)

        def _decorator(fn):
            return fn
        return _decorator

    fake_beam.Image = _FakeImage
    fake_beam.Volume = _FakeVolume
    fake_beam.asgi = _fake_asgi

    app_dir = str(Path(__file__).resolve().parent.parent)
    with mock.patch.dict(sys.modules, {"beam": fake_beam}):
        sys.path.insert(0, app_dir)
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "hymt2_transformers_app_under_test",
                Path(app_dir) / "translation_hymt2_transformers_app.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        finally:
            sys.path.remove(app_dir)
    return mod, captured_asgi_kwargs


class AsgiConfigTest(unittest.TestCase):
    """Protects the actual `@asgi(...)` call - if GPU tier, timeout,
    on_start, or the cache volume are ever silently changed, this fails
    locally before a deploy."""

    @classmethod
    def setUpClass(cls):
        cls.module, cls.kwargs = _load_module_with_fake_beam()

    def test_gpu_is_rtx4090(self):
        self.assertEqual(self.kwargs["gpu"], "RTX4090")

    def test_on_start_is_load_model(self):
        self.assertIs(self.kwargs["on_start"], self.module.load_model)

    def test_timeout_generous_for_cold_weight_download(self):
        """Same real incident class as cover_illustrious_app.py's
        @endpoint(timeout=900) - a fully cold container downloading a
        ~4GB model plus running generation on the same request can
        plausibly exceed Beam's 180s @asgi default."""
        self.assertGreaterEqual(self.kwargs["timeout"], 900)

    def test_cache_volume_is_dedicated_not_reused_from_vllm_attempt(self):
        volumes = self.kwargs["volumes"]
        self.assertEqual(len(volumes), 1)
        self.assertEqual(volumes[0].name, "hymt2-transformers-cache")
        self.assertNotIn("vllm_cache", volumes[0].name)

    def test_image_pins_transformers_at_official_minimum(self):
        image = self.kwargs["image"]
        matching = [p for p in image.packages if p.startswith("transformers==")]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0], "transformers==5.6.0")

    def test_image_does_not_include_vllm(self):
        """Mission's explicit 'Do not use... managed vLLM... in this
        iteration' - a stray vllm dependency here would silently
        reintroduce the abandoned, unsupported path."""
        image = self.kwargs["image"]
        joined = " ".join(image.packages).lower()
        self.assertNotIn("vllm", joined)
        self.assertNotIn("sglang", joined)


class RouteRegistrationTest(unittest.TestCase):
    """`web_server(context)` must register BOTH real OpenAI-compatible
    routes without needing torch (route DEFINITION is torch-free; only
    /chat/completions' body imports torch, lazily, on actual invocation -
    never executed here, matching cover_illustrious_app.py's own
    established testing pattern for GPU-only code paths)."""

    @classmethod
    def setUpClass(cls):
        cls.module, _ = _load_module_with_fake_beam()

    def _build_app(self):
        class _FakeContext:
            on_start_value = ("fake-tokenizer", "fake-model", 12.3, "")
        return self.module.web_server(_FakeContext())

    def test_chat_completions_route_registered(self):
        app = self._build_app()
        paths = [r.path for r in app.routes]
        self.assertIn("/chat/completions", paths)

    def test_health_route_registered(self):
        app = self._build_app()
        paths = [r.path for r in app.routes]
        self.assertIn("/health", paths)

    def test_health_never_calls_generate(self):
        """Mission Section E: readiness must NOT run text generation.
        Real execution against a fake model whose .generate() raises -
        proves /health genuinely never reaches it."""
        from starlette.testclient import TestClient

        class _ExplodingModel:
            def parameters(self):
                yield types.SimpleNamespace(device="cuda:0")

            def generate(self, *a, **kw):
                raise AssertionError("/health must never call generate()")

        class _FakeContext:
            on_start_value = ("fake-tokenizer", _ExplodingModel(), 12.3, "")

        app = self.module.web_server(_FakeContext())
        client = TestClient(app)
        resp = client.post("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["device"], "cuda:0")
        self.assertEqual(body["model_load_seconds"], 12.3)

    def test_health_surfaces_load_error_without_crashing(self):
        """Real incident (2026-09-01): a failed on_start left /health
        returning a bare HTTP 500 with no way to see why (beam logs was
        separately blocked by an unrelated local SSL issue). load_model()
        now catches its own exceptions and /health must report them
        cleanly instead of raising on None tokenizer/model."""
        from starlette.testclient import TestClient

        class _FakeContext:
            on_start_value = (None, None, 3.4, "ImportError: bad transformers pin")

        app = self.module.web_server(_FakeContext())
        client = TestClient(app)
        resp = client.post("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["load_error"], "ImportError: bad transformers pin")
        self.assertFalse(body["model_loaded"])

    def test_chat_completions_reports_load_error_instead_of_crashing(self):
        class _FakeContext:
            on_start_value = (None, None, 3.4, "some load failure")

        app = self.module.web_server(_FakeContext())
        from starlette.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/chat/completions", json={
            "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("some load failure", resp.json()["error"])


class ExtractPromptTextTest(unittest.TestCase):
    """Pure logic, no beam/torch needed - real execution."""

    @classmethod
    def setUpClass(cls):
        cls.module, _ = _load_module_with_fake_beam()

    def test_folds_system_and_user_content(self):
        out = self.module._extract_prompt_text([
            {"role": "system", "content": "Dịch sang tiếng Việt."},
            {"role": "user", "content": "萧炎看向药老。"},
        ])
        self.assertIn("Dịch sang tiếng Việt.", out)
        self.assertIn("萧炎看向药老。", out)
        self.assertTrue(out.index("Dịch") < out.index("萧炎"))

    def test_user_only_returns_user_content(self):
        out = self.module._extract_prompt_text([
            {"role": "user", "content": "hello"},
        ])
        self.assertEqual(out, "hello")

    def test_empty_messages_returns_empty_string(self):
        self.assertEqual(self.module._extract_prompt_text([]), "")

    def test_only_first_system_message_used(self):
        out = self.module._extract_prompt_text([
            {"role": "system", "content": "first"},
            {"role": "system", "content": "second"},
            {"role": "user", "content": "u"},
        ])
        self.assertIn("first", out)
        self.assertNotIn("second", out)


if __name__ == "__main__":
    unittest.main()
