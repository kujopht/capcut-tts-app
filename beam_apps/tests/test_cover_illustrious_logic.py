"""
Test pure logic tach ra tu cover_illustrious_app.py (server tests goc
khong the import module do vi no can package `beam` - remote-deploy-only,
khong cai trong venv cua repo nay). Chay:

    .venv\\Scripts\\python.exe -m unittest discover -s beam_apps/tests -t .
"""
from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cover_illustrious_logic import (  # noqa: E402
    DEFAULT_NEGATIVE_PROMPT, build_response_payload, resolve_negative_prompt,
)

_TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42Y"
    "AAAAASUVORK5CYII="
)


class TestResolveNegativePrompt(unittest.TestCase):
    def test_empty_string_falls_back_to_default(self):
        self.assertEqual(resolve_negative_prompt(""), DEFAULT_NEGATIVE_PROMPT)

    def test_caller_override_is_used_verbatim(self):
        self.assertEqual(resolve_negative_prompt("blurry only"), "blurry only")


class TestBuildResponsePayload(unittest.TestCase):
    def test_shape_and_keys(self):
        payload = build_response_payload(
            _TINY_PNG_BYTES, model_load_seconds=12.3456, inference_seconds=4.321,
            width=1024, height=1536)
        self.assertEqual(
            set(payload.keys()),
            {"image_base64", "model_load_seconds", "inference_seconds",
             "width", "height", "size_bytes"})

    def test_image_base64_roundtrips_to_original_bytes(self):
        payload = build_response_payload(
            _TINY_PNG_BYTES, model_load_seconds=1.0, inference_seconds=1.0,
            width=1024, height=1536)
        self.assertEqual(
            base64.b64decode(payload["image_base64"]), _TINY_PNG_BYTES)

    def test_size_bytes_matches_input_length(self):
        payload = build_response_payload(
            _TINY_PNG_BYTES, model_load_seconds=1.0, inference_seconds=1.0,
            width=1024, height=1536)
        self.assertEqual(payload["size_bytes"], len(_TINY_PNG_BYTES))

    def test_seconds_are_rounded_to_3_decimals(self):
        payload = build_response_payload(
            _TINY_PNG_BYTES, model_load_seconds=12.34567891,
            inference_seconds=4.32109, width=1024, height=1536)
        self.assertEqual(payload["model_load_seconds"], 12.346)
        self.assertEqual(payload["inference_seconds"], 4.321)

    def test_same_model_load_seconds_reported_across_multiple_calls(self):
        """Mo phong 2 request tren CUNG container: model_load_seconds phai
        GIONG NHAU (tu on_start), khong phai 0 o request thu hai - day la
        dung ban chat that (load 1 lan, dung lai nhieu lan)."""
        first = build_response_payload(
            _TINY_PNG_BYTES, model_load_seconds=45.0, inference_seconds=5.0,
            width=1024, height=1536)
        second = build_response_payload(
            _TINY_PNG_BYTES, model_load_seconds=45.0, inference_seconds=5.2,
            width=1024, height=1536)
        self.assertEqual(
            first["model_load_seconds"], second["model_load_seconds"])
        self.assertNotEqual(
            first["inference_seconds"], second["inference_seconds"])

    def test_width_height_passed_through_unchanged(self):
        payload = build_response_payload(
            _TINY_PNG_BYTES, model_load_seconds=1.0, inference_seconds=1.0,
            width=768, height=1152)
        self.assertEqual(payload["width"], 768)
        self.assertEqual(payload["height"], 1152)


if __name__ == "__main__":
    unittest.main()
