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

    def test_call_with_both_reference_images_and_strength_does_not_raise(self):
        try:
            self.sig.bind(
                context=object(), prompt="a cover prompt", seed=1,
                primary_reference_image_base64="ZmFrZQ==",
                secondary_reference_image_base64="ZmFrZQ==",
                reference_strength=0.6)
        except TypeError as exc:
            self.fail(
                f"binding with both reference kwargs raised TypeError: {exc} "
                f"- this is the exact class of error the real seed incident "
                f"was (task 04d22fcf-55f3-4f5e-acd3-337de6ff4432)")

    def test_call_with_only_primary_reference_does_not_raise(self):
        try:
            self.sig.bind(
                context=object(), prompt="a cover prompt",
                primary_reference_image_base64="ZmFrZQ==")
        except TypeError as exc:
            self.fail(f"binding with only primary reference raised TypeError: {exc}")

    def test_reference_kwargs_exist_with_empty_string_defaults(self):
        for name in ("primary_reference_image_base64",
                     "secondary_reference_image_base64"):
            self.assertIn(name, self.sig.parameters)
            self.assertEqual(self.sig.parameters[name].default, "")

    def test_reference_strength_defaults_to_0_6(self):
        self.assertIn("reference_strength", self.sig.parameters)
        self.assertEqual(self.sig.parameters["reference_strength"].default, 0.6)


if __name__ == "__main__":
    unittest.main()
