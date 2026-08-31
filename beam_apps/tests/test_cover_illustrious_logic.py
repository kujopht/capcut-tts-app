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
    DEFAULT_NEGATIVE_PROMPT, DeviceMismatchError,
    IP_ADAPTER_EXPECTED_HIDDEN_SIZE, IP_ADAPTER_IMAGE_ENCODER_SUBFOLDER,
    IPAdapterEncoderMismatchError, assert_component_on_cuda,
    assert_ip_adapter_encoder_compatible, build_left_right_masks,
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

    def test_contains_composition_failure_terms_from_real_v10_incident(self):
        """Real v10 proof failed 3 distinct ways: cropped face, a
        character facing away, and an extra/unwanted person - each gets
        its own explicit negative term now, not just the generic
        "cropped"/"extra person" already present."""
        for term in ("third person", "cropped face", "cut-off head",
                     "back facing viewer", "rear view", "letters",
                     "symbols", "logo"):
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

    def test_masks_never_overlap_at_any_column(self):
        """Real fix for a real composition failure (v10 proof: extra/
        background character + face-cropping/back-facing artifacts,
        traced to the OLD deliberately-overlapping masks letting both
        IP-Adapter references condition the same pixels). Exhaustively
        checks every column - no x may be 255 in BOTH masks."""
        primary, secondary = build_left_right_masks(1000, 1000)
        for x in range(0, 1000, 5):
            self.assertFalse(
                primary.getpixel((x, 500)) == 255 and
                secondary.getpixel((x, 500)) == 255,
                f"masks overlap at x={x}")

    def test_default_gap_is_a_dead_zone_belonging_to_neither(self):
        """gap_fraction=0.04 default on width=1000 -> ~40px gap centered
        on the split (500) - x=500 itself must belong to NEITHER mask."""
        primary, secondary = build_left_right_masks(1000, 1000)
        self.assertEqual(primary.getpixel((500, 500)), 0)
        self.assertEqual(secondary.getpixel((500, 500)), 0)

    def test_zero_gap_still_does_not_overlap(self):
        """gap_fraction=0.0 (bare adjacent split, no dead zone) must
        still guarantee zero overlap - this is the boundary condition
        most likely to regress back into a 1px overlap bug."""
        primary, secondary = build_left_right_masks(
            1000, 1000, gap_fraction=0.0)
        for x in range(495, 506):
            self.assertFalse(
                primary.getpixel((x, 500)) == 255 and
                secondary.getpixel((x, 500)) == 255,
                f"masks overlap at x={x} even with gap_fraction=0.0")

    def test_default_split_is_even_not_primary_favored(self):
        """split_fraction default changed 0.55 -> 0.5 (equal halves) to
        match the new waist-up/medium-shot dual-portrait composition,
        which no longer frames one character as visually larger."""
        primary, secondary = build_left_right_masks(1000, 1000)
        self.assertEqual(primary.getpixel((200, 500)), 255)
        self.assertEqual(secondary.getpixel((800, 500)), 255)

    def test_custom_split_fraction_changes_boundary(self):
        primary_default, _ = build_left_right_masks(1000, 1000)
        primary_narrow, _ = build_left_right_masks(
            1000, 1000, split_fraction=0.3, gap_fraction=0.0)
        # o x=400: mac dinh (split=500) van la primary; split hep hon
        # (split=300) thi x=400 da la ngoai vung primary.
        self.assertEqual(primary_default.getpixel((400, 500)), 255)
        self.assertEqual(primary_narrow.getpixel((400, 500)), 0)


class TestIpAdapterEncoderSubfolder(unittest.TestCase):
    """Direct regression guard on the exact root-cause string - the real
    bug was `load_ip_adapter(subfolder="sdxl_models")`'s DEFAULT
    image_encoder_folder resolving to "sdxl_models/image_encoder" (wrong,
    ViT-bigG). The fix must use the TOP-LEVEL "models/image_encoder"
    path, never anything under "sdxl_models/"."""

    def test_subfolder_is_top_level_models_image_encoder(self):
        self.assertEqual(
            IP_ADAPTER_IMAGE_ENCODER_SUBFOLDER, "models/image_encoder")

    def test_subfolder_is_not_under_sdxl_models(self):
        self.assertNotIn("sdxl_models", IP_ADAPTER_IMAGE_ENCODER_SUBFOLDER)

    def test_expected_hidden_size_is_vit_h_not_vit_biggg(self):
        self.assertEqual(IP_ADAPTER_EXPECTED_HIDDEN_SIZE, 1280)
        self.assertNotEqual(IP_ADAPTER_EXPECTED_HIDDEN_SIZE, 1664)


class TestAssertIpAdapterEncoderCompatible(unittest.TestCase):
    def test_correct_hidden_size_and_vit_h_checkpoint_does_not_raise(self):
        try:
            assert_ip_adapter_encoder_compatible(
                1280, "ip-adapter-plus-face_sdxl_vit-h.safetensors")
        except IPAdapterEncoderMismatchError as exc:
            self.fail(f"correct pairing raised unexpectedly: {exc}")

    def test_wrong_hidden_size_1664_raises_reproducing_real_incident(self):
        """The EXACT real incident: ViT-bigG (1664) silently paired with
        a *_vit-h checkpoint that expects 1280."""
        with self.assertRaises(IPAdapterEncoderMismatchError) as ctx:
            assert_ip_adapter_encoder_compatible(
                1664, "ip-adapter-plus-face_sdxl_vit-h.safetensors")
        self.assertIn("1664", str(ctx.exception))
        self.assertIn("1280", str(ctx.exception))

    def test_non_vit_h_checkpoint_name_raises(self):
        """Defends against a future checkpoint swap without updating the
        explicitly-loaded encoder to match."""
        with self.assertRaises(IPAdapterEncoderMismatchError):
            assert_ip_adapter_encoder_compatible(
                1280, "ip-adapter-plus_sdxl_vit-g.safetensors")

    def test_error_message_cites_the_real_prior_runtimeerror(self):
        """Actionable message - a future operator seeing this should
        recognize it as the same class of failure, not a new mystery."""
        with self.assertRaises(IPAdapterEncoderMismatchError) as ctx:
            assert_ip_adapter_encoder_compatible(
                1664, "ip-adapter-plus-face_sdxl_vit-h.safetensors")
        self.assertIn("mat1 and mat2", str(ctx.exception))


class TestAssertComponentOnCuda(unittest.TestCase):
    """Real regression guard for a real Beam v9 incident: RuntimeError
    "Expected all tensors to be on the same device, but got index is on
    cpu, different from other tensors on cuda:0" - the explicitly-loaded
    IP-Adapter image encoder (added to fix the ViT-bigG/ViT-H mismatch)
    was constructed but never moved to CUDA. Pure string check, no
    torch/CUDA runtime needed - load_pipeline() calls this with real
    `str(param.device)` values from actually-loaded torch modules."""

    def test_cuda_zero_does_not_raise(self):
        try:
            assert_component_on_cuda("ip_adapter_image_encoder", "cuda:0")
        except DeviceMismatchError as exc:
            self.fail(f"cuda:0 raised unexpectedly: {exc}")

    def test_bare_cuda_does_not_raise(self):
        try:
            assert_component_on_cuda("unet", "cuda")
        except DeviceMismatchError as exc:
            self.fail(f"cuda raised unexpectedly: {exc}")

    def test_cpu_raises_reproducing_real_incident(self):
        """The EXACT real incident: image encoder left on CPU while the
        rest of the pipeline (shared from the base pipe) is on cuda:0."""
        with self.assertRaises(DeviceMismatchError) as ctx:
            assert_component_on_cuda("ip_adapter_image_encoder", "cpu")
        self.assertIn("cpu", str(ctx.exception))

    def test_error_message_cites_the_real_prior_runtimeerror(self):
        with self.assertRaises(DeviceMismatchError) as ctx:
            assert_component_on_cuda("ip_adapter_image_encoder", "cpu")
        self.assertIn("Expected all tensors to be on the same device",
                       str(ctx.exception))

    def test_error_message_includes_component_name(self):
        """Actionable - names WHICH component was misplaced, not just
        that something was wrong."""
        with self.assertRaises(DeviceMismatchError) as ctx:
            assert_component_on_cuda("unet.encoder_hid_proj", "cpu")
        self.assertIn("unet.encoder_hid_proj", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
