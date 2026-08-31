"""
Regression test for a REAL production incident: task
04d22fcf-55f3-4f5e-acd3-337de6ff4432 failed on the deployed Beam endpoint
with `TypeError: generate() got an unexpected keyword argument 'seed'`
after ~73ms - before model inference ever ran. Root cause was a STALE
deployment (the running container predated the `seed` parameter being
added to generate()'s signature, not a defect in the committed source -
confirmed by reading beam_apps/cover_illustrious_app.py at the failing
commit vs the current one). This test protects the actual code contract
going forward: if `seed` (or any other kwarg beam_cover_refinement.py
sends) is ever removed or renamed from generate()'s signature again, this
test fails locally BEFORE a deploy, instead of only failing on a real,
billed, remote GPU call.

WHY sys.modules injection: `beam` is a remote-deploy-only dependency not
installed in this repo's venv (see cover_illustrious_app.py's own
docstring), so the module cannot be imported at all otherwise. `endpoint`
is faked as an identity decorator (`lambda **kw: lambda f: f`) so
`generate` in the imported module is the REAL, undecorated function
object with its REAL signature - this test never fakes/reimplements
generate()'s logic, it inspects the actual one. `torch`/`diffusers` are
NOT needed here: they're imported lazily inside load_pipeline()/generate()
bodies, and inspect.Signature.bind() proves argument-binding succeeds
WITHOUT executing the function body (which is exactly where the real
73ms-in TypeError happened, before any torch/diffusers/CUDA code ran).
"""
from __future__ import annotations

import inspect
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _load_generate_with_fake_beam():
    fake_beam = types.ModuleType("beam")

    class _FakeImage:
        def __init__(self, *a, **kw):
            pass

        def add_python_packages(self, *a, **kw):
            return self

    class _FakeVolume:
        def __init__(self, *a, **kw):
            pass

    def _fake_endpoint(**kw):
        def _decorator(fn):
            return fn
        return _decorator

    fake_beam.Image = _FakeImage
    fake_beam.Volume = _FakeVolume
    fake_beam.endpoint = _fake_endpoint

    app_dir = str(Path(__file__).resolve().parent.parent)
    with mock.patch.dict(sys.modules, {"beam": fake_beam}):
        sys.path.insert(0, app_dir)
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "cover_illustrious_app_under_test",
                Path(app_dir) / "cover_illustrious_app.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        finally:
            sys.path.remove(app_dir)
    return mod.generate


def _load_module_and_capture_endpoint_kwargs():
    """Same fake-`beam`-module technique as _load_generate_with_fake_beam(),
    but the fake `endpoint` CAPTURES the kwargs it was called with instead
    of discarding them - proving exactly what the real source file passes
    to `@endpoint(...)` (name, timeout, gpu, etc.), since that's a
    decorator ARGUMENT, not a parameter of generate() itself, and
    inspect.signature() on generate() cannot see it."""
    fake_beam = types.ModuleType("beam")
    captured_kwargs = {}

    class _FakeImage:
        def __init__(self, *a, **kw):
            pass

        def add_python_packages(self, *a, **kw):
            return self

    class _FakeVolume:
        def __init__(self, *a, **kw):
            pass

    def _fake_endpoint(**kw):
        captured_kwargs.update(kw)

        def _decorator(fn):
            return fn
        return _decorator

    fake_beam.Image = _FakeImage
    fake_beam.Volume = _FakeVolume
    fake_beam.endpoint = _fake_endpoint

    app_dir = str(Path(__file__).resolve().parent.parent)
    with mock.patch.dict(sys.modules, {"beam": fake_beam}):
        sys.path.insert(0, app_dir)
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "cover_illustrious_app_endpoint_kwargs_test",
                Path(app_dir) / "cover_illustrious_app.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        finally:
            sys.path.remove(app_dir)
    return captured_kwargs


class TestEndpointTimeoutConfig(unittest.TestCase):
    """Regression test for a REAL production incident: a reference-proof
    call ended in the Beam dashboard as task status=Cancelled with
    Started="-"/Duration="-" - the task never actually ran before being
    killed by Beam's own @endpoint `timeout` (default 180s, confirmed via
    docs.beam.cloud/v2/reference/py-sdk.md's own decorator signature).
    Protects the actual `@endpoint(...)` call in the source file - if
    `timeout` is ever removed or shrunk back below what a cold reference-
    model startup needs, this fails locally before a deploy."""

    @classmethod
    def setUpClass(cls):
        cls.endpoint_kwargs = _load_module_and_capture_endpoint_kwargs()

    def test_timeout_is_explicitly_set(self):
        self.assertIn("timeout", self.endpoint_kwargs)

    def test_timeout_is_900_seconds(self):
        self.assertEqual(self.endpoint_kwargs["timeout"], 900)

    def test_timeout_exceeds_beam_sdk_180_second_default(self):
        """900 must genuinely be more headroom than the SDK default this
        incident was caused by, not just 'set to something'."""
        BEAM_SDK_DEFAULT_TIMEOUT_SECONDS = 180
        self.assertGreater(
            self.endpoint_kwargs["timeout"], BEAM_SDK_DEFAULT_TIMEOUT_SECONDS)

    def test_timeout_is_not_disabled(self):
        """timeout=-1 disables the timeout entirely (per the real SDK
        docs) - that would remove crash/hang protection, which was never
        asked for; only more headroom was."""
        self.assertNotEqual(self.endpoint_kwargs["timeout"], -1)

    def test_keep_warm_seconds_left_at_scale_to_zero_default(self):
        """Requirement 3 - must NOT force a permanently warm GPU. This
        source file must not explicitly set keep_warm_seconds at all
        (leaving the SDK's own default - the scale-to-zero idle-shutdown
        knob - untouched, distinct from `timeout` above)."""
        self.assertNotIn("keep_warm_seconds", self.endpoint_kwargs)

    def test_gpu_and_model_config_unchanged(self):
        """Requirement 2 - do not change model/GPU/proof logic alongside
        the timeout fix."""
        self.assertEqual(self.endpoint_kwargs.get("gpu"), "RTX4090")
        self.assertEqual(self.endpoint_kwargs.get("cpu"), 4)
        self.assertEqual(self.endpoint_kwargs.get("memory"), "16Gi")
        self.assertEqual(self.endpoint_kwargs.get("name"), "cover-illustrious")


class TestGenerateAcceptsSeedKeyword(unittest.TestCase):
    """Bind-only (does NOT execute the body - no torch/diffusers/CUDA
    needed), proving the exact calling convention Beam uses against the
    REAL function object from the REAL deploy file."""

    @classmethod
    def setUpClass(cls):
        cls.generate = _load_generate_with_fake_beam()
        cls.sig = inspect.signature(cls.generate)

    def test_call_without_seed_does_not_raise(self):
        """Backward compat: requests sent before the seed param existed
        (or that simply omit it) must keep working."""
        try:
            self.sig.bind(context=object(), prompt="a cover prompt")
        except TypeError as exc:
            self.fail(f"binding without seed raised TypeError: {exc}")

    def test_call_with_seed_20260901_does_not_raise(self):
        """The exact real failure this test exists for: beam_cover_refinement.py
        sends seed=20260901/...902/...903 - this must bind cleanly."""
        try:
            self.sig.bind(
                context=object(), prompt="a cover prompt", seed=20260901)
        except TypeError as exc:
            self.fail(
                f"binding with seed=20260901 raised TypeError: {exc} - this "
                f"is the exact class of error from real task "
                f"04d22fcf-55f3-4f5e-acd3-337de6ff4432")

    def test_seed_parameter_exists_with_default_minus_one(self):
        self.assertIn("seed", self.sig.parameters)
        self.assertEqual(self.sig.parameters["seed"].default, -1)

    def test_seed_is_not_a_required_positional_only_parameter(self):
        """Guards against a future edit accidentally making seed
        positional-only or required, which would break the JSON-body ->
        kwargs mapping Beam uses to invoke this handler."""
        seed_param = self.sig.parameters["seed"]
        self.assertNotEqual(
            seed_param.kind, inspect.Parameter.POSITIONAL_ONLY)
        self.assertNotEqual(seed_param.default, inspect.Parameter.empty)


class TestGenerateAcceptsReferenceConditioningKeywords(unittest.TestCase):
    """Same bind-only technique as TestGenerateAcceptsSeedKeyword, applied
    PROACTIVELY (before any deploy) to the reference-conditioning kwargs
    added for the "Reference-Conditioned Cover Proof" mission - the exact
    class of bug that caused the real seed incident (a client sending a
    kwarg the deployed generate() doesn't accept) is checked here BEFORE
    scripts/beam_cover_reference_proof.py ever makes a real GPU call."""

    @classmethod
    def setUpClass(cls):
        cls.generate = _load_generate_with_fake_beam()
        cls.sig = inspect.signature(cls.generate)

    def test_call_with_no_reference_kwargs_does_not_raise(self):
        """Requirement 9 - fallback: no references -> must keep binding
        exactly like the pre-reference-conditioning signature."""
        try:
            self.sig.bind(context=object(), prompt="a cover prompt", seed=1)
        except TypeError as exc:
            self.fail(f"binding without reference kwargs raised TypeError: {exc}")

    def test_call_with_both_reference_image_lists_and_strength_does_not_raise(self):
        try:
            self.sig.bind(
                context=object(), prompt="a cover prompt", seed=1,
                primary_reference_images_base64=["ZmFrZQ=="],
                secondary_reference_images_base64=["ZmFrZQ=="],
                reference_strength=0.6)
        except TypeError as exc:
            self.fail(
                f"binding with both reference kwargs raised TypeError: {exc} "
                f"- this is the exact class of error the real seed incident "
                f"was (task 04d22fcf-55f3-4f5e-acd3-337de6ff4432)")

    def test_call_with_only_primary_reference_list_does_not_raise(self):
        try:
            self.sig.bind(
                context=object(), prompt="a cover prompt",
                primary_reference_images_base64=["ZmFrZQ=="])
        except TypeError as exc:
            self.fail(f"binding with only primary reference raised TypeError: {exc}")

    def test_call_with_multiple_images_in_one_list_does_not_raise(self):
        """Item 3 cua mission V1 - reference_images[] o cap schema/request
        ho tro NHIEU anh/nhan vat, du generate() hien chi dung anh dau
        tien (xem module docstring "MULTI-IMAGE PER CHARACTER")."""
        try:
            self.sig.bind(
                context=object(), prompt="a cover prompt",
                primary_reference_images_base64=["ZmFrZQ==", "ZmFrZTI="])
        except TypeError as exc:
            self.fail(f"binding with multiple images in one list raised TypeError: {exc}")

    def test_reference_kwargs_exist_with_none_defaults(self):
        for name in ("primary_reference_images_base64",
                     "secondary_reference_images_base64"):
            self.assertIn(name, self.sig.parameters)
            self.assertIsNone(self.sig.parameters[name].default)

    def test_reference_strength_defaults_to_0_6(self):
        self.assertIn("reference_strength", self.sig.parameters)
        self.assertEqual(self.sig.parameters["reference_strength"].default, 0.6)


if __name__ == "__main__":
    unittest.main()
