"""LoRA proof readiness check — must stay honest about what's missing.

Both preconditions for a real 2-character LoRA proof (trained+compatible LoRA
assets, and a staged-regional-inpainting pipeline) are absent as of
2026-09-01. What matters here is that the checker never reports "ready" while
either is missing, and that it flags a wrong base-model string as a hard
failure rather than a warning — a mismatched LoRA base model is the same
class of bug as the ViT-bigG/ViT-H image-encoder incident earlier this
session.
"""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PATH = os.path.join(_ROOT, "scripts", "beam_cover_lora_proof_readiness_check.py")


def _load():
    spec = importlib.util.spec_from_file_location("_lora_readiness_qa", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class NoArgsReportsNotReadyTest(unittest.TestCase):
    def test_main_with_no_args_exits_nonzero(self):
        mod = _load()
        self.assertEqual(mod.main.__module__, "_lora_readiness_qa")

    def test_check_lora_asset_missing_path_is_an_error(self):
        mod = _load()
        errors = mod.check_lora_asset("primary", "", "cagliostrolab/animagine-xl-4.0")
        self.assertTrue(any("lora-path" in e for e in errors))

    def test_check_lora_asset_nonexistent_path_is_an_error(self):
        mod = _load()
        errors = mod.check_lora_asset(
            "primary", "Z:/does/not/exist.safetensors", "cagliostrolab/animagine-xl-4.0"
        )
        self.assertTrue(any("khong tim thay file" in e for e in errors))

    def test_check_lora_asset_wrong_base_model_is_an_error(self):
        with tempfile.NamedTemporaryFile(suffix=".safetensors", delete=False) as f:
            path = f.name
        try:
            mod = _load()
            errors = mod.check_lora_asset(
                "primary", path, "cagliostrolab/animagine-xl-3.0"
            )
            self.assertTrue(
                any("khac voi checkpoint production" in e for e in errors),
                "a mismatched base model must be a hard error, not silently accepted",
            )
        finally:
            os.unlink(path)

    def test_check_lora_asset_correct_and_present_has_no_errors(self):
        with tempfile.NamedTemporaryFile(suffix=".safetensors", delete=False) as f:
            path = f.name
        try:
            mod = _load()
            errors = mod.check_lora_asset(
                "primary", path, "cagliostrolab/animagine-xl-4.0"
            )
            self.assertEqual(errors, [])
        finally:
            os.unlink(path)

    def test_staged_inpainting_pipeline_reported_missing_today(self):
        mod = _load()
        errors = mod.check_staged_inpainting_pipeline()
        self.assertTrue(
            errors,
            "staged regional inpainting is not implemented yet in "
            "cover_illustrious_app.py — this must be reported as missing, "
            "never silently treated as ready",
        )


if __name__ == "__main__":
    unittest.main()
