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
    DEFAULT_NEGATIVE_PROMPT, build_left_right_masks,
    build_reference_conditioning_metadata, build_response_payload,
    resolve_negative_prompt,
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
             "width", "height", "size_bytes", "seed"})

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

    def test_seed_defaults_to_minus_one_when_unrequested(self):
        payload = build_response_payload(
            _TINY_PNG_BYTES, model_load_seconds=1.0, inference_seconds=1.0,
            width=1024, height=1536)
        self.assertEqual(payload["seed"], -1)

    def test_seed_is_echoed_back_verbatim(self):
        payload = build_response_payload(
            _TINY_PNG_BYTES, model_load_seconds=1.0, inference_seconds=1.0,
            width=1024, height=1536, seed=20260901)
        self.assertEqual(payload["seed"], 20260901)


class TestDefaultNegativePromptCoversCrowding(unittest.TestCase):
    """Ban Re:Zero dau tien la mot poster ensemble dong nguoi/nhan vat
    trung lap that su - dam bao negative prompt chan cu the dieu nay."""

    def test_contains_anti_crowd_terms(self):
        for term in ("crowd", "group", "ensemble cast", "extra person",
                     "background character", "duplicate character",
                     "cloned face", "multiple girls", "multiple boys",
                     "collage", "character sheet"):
            self.assertIn(term, DEFAULT_NEGATIVE_PROMPT)

    def test_original_quality_terms_still_present(self):
        for term in ("lowres", "bad anatomy", "watermark", "blurry"):
            self.assertIn(term, DEFAULT_NEGATIVE_PROMPT)


class TestBuildReferenceConditioningMetadata(unittest.TestCase):
    def test_unused_returns_false_and_zero_strength(self):
        meta = build_reference_conditioning_metadata(used=False, strength=0.6)
        self.assertEqual(meta, {
            "reference_conditioned": False, "reference_strength_used": 0.0})

    def test_used_returns_true_and_actual_strength(self):
        meta = build_reference_conditioning_metadata(used=True, strength=0.6)
        self.assertEqual(meta, {
            "reference_conditioned": True, "reference_strength_used": 0.6})

    def test_keys_are_disjoint_from_build_response_payload_keys(self):
        """Requirement 9 - khong tham chieu thi response GIONG HET truoc
        day: generate() chi .update() metadata nay vao KHI used=True, nen
        cac khoa o day khong duoc trung voi build_response_payload() (neu
        trung, .update() se GHI DE mot khoa da co, thay vi CHI THEM khoa
        moi khi thuc su dung reference-conditioning)."""
        base_keys = set(build_response_payload(
            b"x", model_load_seconds=1.0, inference_seconds=1.0,
            width=1, height=1).keys())
        meta_keys = set(build_reference_conditioning_metadata(used=True).keys())
        self.assertEqual(base_keys & meta_keys, set())


class TestBuildLeftRightMasks(unittest.TestCase):
    def test_returns_two_masks_of_requested_size(self):
        primary, secondary = build_left_right_masks(1024, 1536)
        self.assertEqual(primary.size, (1024, 1536))
        self.assertEqual(secondary.size, (1024, 1536))
        self.assertEqual(primary.mode, "L")
        self.assertEqual(secondary.mode, "L")

    def test_primary_mask_covers_left_side(self):
        primary, _ = build_left_right_masks(1000, 1000)
        self.assertEqual(primary.getpixel((10, 500)), 255)

    def test_primary_mask_excludes_far_right(self):
        primary, _ = build_left_right_masks(1000, 1000)
        self.assertEqual(primary.getpixel((990, 500)), 0)

    def test_secondary_mask_covers_right_side(self):
        _, secondary = build_left_right_masks(1000, 1000)
        self.assertEqual(secondary.getpixel((990, 500)), 255)

    def test_secondary_mask_excludes_far_left(self):
        _, secondary = build_left_right_masks(1000, 1000)
        self.assertEqual(secondary.getpixel((10, 500)), 0)

    def test_masks_overlap_in_the_middle_no_hard_seam(self):
        """split_fraction=0.55, overlap_fraction=0.08 mac dinh tren
        width=1000 -> split=550, overlap=80 -> vung chong lan [470, 630)."""
        primary, secondary = build_left_right_masks(1000, 1000)
        self.assertEqual(primary.getpixel((500, 500)), 255)
        self.assertEqual(secondary.getpixel((500, 500)), 255)

    def test_custom_split_fraction_changes_boundary(self):
        primary_default, _ = build_left_right_masks(1000, 1000)
        primary_narrow, _ = build_left_right_masks(
            1000, 1000, split_fraction=0.3, overlap_fraction=0.0)
        # o x=400: mac dinh (split=550) van la primary; split hep hon
        # (split=300) thi x=400 da la ngoai vung primary.
        self.assertEqual(primary_default.getpixel((400, 500)), 255)
        self.assertEqual(primary_narrow.getpixel((400, 500)), 0)


if __name__ == "__main__":
    unittest.main()
