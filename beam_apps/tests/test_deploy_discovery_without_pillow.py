"""
Regression test for a REAL production incident: `beam deploy
beam_apps/cover_illustrious_app.py:generate` failed BEFORE reaching the
remote container build, at:

    beam_apps/cover_illustrious_logic.py:19
    from PIL import Image, ImageDraw

Root cause: `beam deploy`'s DISCOVERY step imports the target Python file
LOCALLY (in whatever environment runs the `beam` CLI, e.g. a bare Cloud
Shell python3) to introspect the `@endpoint`-decorated function - a
completely separate environment from the REMOTE container that
`Image().add_python_packages([...])` builds. That local discovery
environment does not have Pillow installed. A module-level `from PIL
import ...` in cover_illustrious_logic.py (imported by
cover_illustrious_app.py at ITS module level) broke discovery entirely,
before any GPU container was even built - PIL usage is now lazy, moved
inside build_left_right_masks() itself (the only function that needs
it).

WHY sys.modules poisoning: Pillow genuinely IS installed in THIS repo's
own venv (desktop app dependency), so simply running these tests here
would never exercise the "PIL missing" case by itself. `sys.modules[name]
= None` is the standard, documented CPython technique to force `import
name` to raise ImportError without needing to actually uninstall the
real package - see docs.python.org's own note on this sys.modules
convention. Both target modules are re-imported FRESH via importlib
(bypassing any already-cached sys.modules entry from other test files in
this same discovery run) so the poisoning actually takes effect.
"""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

_APP_DIR = Path(__file__).resolve().parent.parent

_PIL_POISON = {
    "PIL": None, "PIL.Image": None, "PIL.ImageDraw": None,
    "PIL.ImageFile": None,
}


def _fresh_import_with_pil_poisoned(
        module_name: str, file_path: Path, extra_sys_modules=None,
        also_evict=()):
    """Evict `module_name` (plus anything in `also_evict`, e.g. a module
    imported bare by `module_name` itself that might already be cached
    from an earlier test file) from sys.modules, poison PIL, then import
    the target file fresh via importlib.util - proving it does NOT need
    PIL merely to be imported."""
    poison = dict(_PIL_POISON)
    if extra_sys_modules:
        poison.update(extra_sys_modules)

    saved = {}
    for name in list(poison) + [module_name] + list(also_evict):
        if name in sys.modules:
            saved[name] = sys.modules.pop(name)

    try:
        with mock.patch.dict(sys.modules, poison):
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
            return mod
    finally:
        sys.modules.pop(module_name, None)
        for name, real_mod in saved.items():
            sys.modules[name] = real_mod


def _fake_beam_module() -> types.ModuleType:
    """Same fake used by test_cover_illustrious_app_signature.py - `beam`
    is a remote-deploy-only dependency not installed in this repo's venv,
    unrelated to the Pillow question this file tests."""
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
    return fake_beam


class TestCoverIllustriousLogicImportableWithoutPillow(unittest.TestCase):
    def test_module_imports_without_pillow_installed(self):
        try:
            mod = _fresh_import_with_pil_poisoned(
                "cover_illustrious_logic_no_pil_test",
                _APP_DIR / "cover_illustrious_logic.py")
        except ImportError as exc:
            self.fail(
                f"cover_illustrious_logic.py failed to import without "
                f"Pillow available: {exc} - this is the exact real "
                f"failure that broke `beam deploy` at the discovery step.")
        self.assertTrue(hasattr(mod, "build_left_right_masks"))
        self.assertTrue(hasattr(mod, "build_response_payload"))
        self.assertTrue(hasattr(mod, "build_reference_conditioning_metadata"))


class TestCoverIllustriousAppImportableWithoutPillow(unittest.TestCase):
    """cover_illustrious_app.py imports cover_illustrious_logic at ITS OWN
    module level - proving the FULL chain Beam's discovery step actually
    walks (app.py -> logic.py) survives without Pillow, not just logic.py
    in isolation."""

    def test_module_imports_without_pillow_installed(self):
        try:
            mod = _fresh_import_with_pil_poisoned(
                "cover_illustrious_app_no_pil_test",
                _APP_DIR / "cover_illustrious_app.py",
                extra_sys_modules={"beam": _fake_beam_module()},
                also_evict=("cover_illustrious_logic",))
        except ImportError as exc:
            self.fail(
                f"cover_illustrious_app.py failed to import without "
                f"Pillow available: {exc} - this is the exact real "
                f"failure that broke `beam deploy` at the discovery step.")
        self.assertTrue(hasattr(mod, "generate"))
        self.assertTrue(hasattr(mod, "load_pipeline"))


if __name__ == "__main__":
    unittest.main()
