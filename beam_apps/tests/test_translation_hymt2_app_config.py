"""
Regression guard for `beam_apps/translation_hymt2_app.py`'s deploy CONFIG
(mission "Hy-MT2 1.8B translation production readiness", Track B).

This file has no functions to test (unlike cover_illustrious_app.py's
`generate()`) - it is two declarative `VLLM(...)` instantiations. The real
risk here is a SILENT config regression (someone flips a GPU tier, drops
`trust_remote_code`, or points `served_model_name` at the wrong model
string) that would only surface on a real, billed Beam deploy/call. This
test catches that locally, for free, by faking `beam.integrations` (a
remote-deploy-only dependency NOT installed in this repo's venv - see the
module's own docstring) with fake `VLLM`/`VLLMArgs` classes that just
RECORD their kwargs, then asserting on the real values `translation_hymt2_app.py`
actually passes - same `sys.modules` injection technique already used by
`test_deploy_discovery_without_pillow.py`/`test_cover_illustrious_app_signature.py`
in this same directory.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _load_module_with_fake_beam():
    fake_beam = types.ModuleType("beam")
    fake_beam_integrations = types.ModuleType("beam.integrations")

    recorded = {"calls": []}

    class _FakeVLLMArgs:
        def __init__(self, **kw):
            self.kwargs = kw

    class _FakeVLLM:
        def __init__(self, **kw):
            self.kwargs = kw
            recorded["calls"].append(kw)

    fake_beam_integrations.VLLM = _FakeVLLM
    fake_beam_integrations.VLLMArgs = _FakeVLLMArgs
    fake_beam.integrations = fake_beam_integrations

    app_dir = str(Path(__file__).resolve().parent.parent)
    with mock.patch.dict(sys.modules, {
        "beam": fake_beam, "beam.integrations": fake_beam_integrations}):
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)
        import importlib

        if "translation_hymt2_app" in sys.modules:
            del sys.modules["translation_hymt2_app"]
        module = importlib.import_module("translation_hymt2_app")
    return module, recorded


class TranslationHyMT2AppConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module, self.recorded = _load_module_with_fake_beam()

    def test_both_deployments_registered(self):
        self.assertEqual(len(self.recorded["calls"]), 2)

    def test_1_8b_uses_rtx4090_gpu(self):
        """Real deploy evidence (2026-09-01): `gpu="T4"` FAILED with Beam's
        own error "This GPU type is not supported. Please use an A10G or
        RTX 4090 instead." - this must never regress back to T4."""
        self.assertEqual(self.module.hymt2_1_8b.kwargs["gpu"], "RTX4090")

    def test_1_8b_does_not_use_t4_gpu(self):
        self.assertNotEqual(self.module.hymt2_1_8b.kwargs["gpu"], "T4")

    def test_7b_uses_a10g_gpu(self):
        self.assertEqual(self.module.hymt2_7b.kwargs["gpu"], "A10G")

    def test_1_8b_trust_remote_code_true(self):
        args = self.module.hymt2_1_8b.kwargs["vllm_args"]
        self.assertTrue(args.kwargs["trust_remote_code"])

    def test_7b_trust_remote_code_true(self):
        args = self.module.hymt2_7b.kwargs["vllm_args"]
        self.assertTrue(args.kwargs["trust_remote_code"])

    def test_1_8b_served_model_name_matches_model_id(self):
        args = self.module.hymt2_1_8b.kwargs["vllm_args"]
        self.assertEqual(args.kwargs["model"], self.module.HYMT2_1_8B)
        self.assertEqual(args.kwargs["served_model_name"], [self.module.HYMT2_1_8B])

    def test_7b_served_model_name_matches_model_id(self):
        args = self.module.hymt2_7b.kwargs["vllm_args"]
        self.assertEqual(args.kwargs["model"], self.module.HYMT2_7B)
        self.assertEqual(args.kwargs["served_model_name"], [self.module.HYMT2_7B])

    def test_model_ids_are_distinct(self):
        self.assertNotEqual(self.module.HYMT2_1_8B, self.module.HYMT2_7B)
        self.assertEqual(self.module.HYMT2_1_8B, "tencent/Hy-MT2-1.8B")
        self.assertEqual(self.module.HYMT2_7B, "tencent/Hy-MT2-7B")

    def test_max_model_len_is_a_deliberate_reduction_not_full_context(self):
        """Real research finding (fetched 2026-09-01): the model's own
        config.json reports max_position_embeddings=262144 - max_model_len
        here must stay meaningfully SMALLER (VRAM/KV-cache headroom), not
        accidentally raised to the model's full theoretical context."""
        for deployment in (self.module.hymt2_1_8b, self.module.hymt2_7b):
            args = deployment.kwargs["vllm_args"]
            self.assertLess(args.kwargs["max_model_len"], 262144)
            self.assertGreaterEqual(args.kwargs["max_model_len"], 4096)

    def test_gpu_memory_utilization_leaves_headroom(self):
        """Never 1.0 - some headroom must be left for framework overhead."""
        for deployment in (self.module.hymt2_1_8b, self.module.hymt2_7b):
            args = deployment.kwargs["vllm_args"]
            self.assertLess(args.kwargs["gpu_memory_utilization"], 1.0)
            self.assertGreater(args.kwargs["gpu_memory_utilization"], 0.5)


if __name__ == "__main__":
    unittest.main()
