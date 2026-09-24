"""
Regression tests for Ngọc Huyền canonical voice display and alias resolution.

Enforces:
1. `piper:ngochuyen` continues resolving to `piper:ngochuyennew` for backward compatibility.
2. The public voice list (/api/voices) exposes only ONE Ngọc Huyền entry (piper:ngochuyennew).
3. The display name of the canonical entry is "Ngọc Huyền".
4. The legacy alias remains accepted by all backend guard functions (ensure_voice_public, ensure_voice_runnable).
"""

import unittest
from server import tts_bridge
from server.config import Settings
from desktop_app.providers.recommended import (
    RECOMMENDED_FANFIC_VOICES,
    RECOMMENDED_CODES,
)
from desktop_app.providers.builtin_catalog import (
    NGHITTS_DISPLAY_NAMES,
    PIPER_PREFERRED_KEY,
)


class TestNgochuyenCanonical(unittest.TestCase):

    def test_old_alias_still_resolves_to_canonical(self):
        """piper:ngochuyen must resolve to piper:ngochuyennew."""
        v_alias = tts_bridge.resolve_voice("piper:ngochuyen")
        self.assertEqual(v_alias.id, "piper:ngochuyennew")
        self.assertEqual(v_alias.engine_voice_id, "ngochuyennew")

        v_canonical = tts_bridge.resolve_voice("piper:ngochuyennew")
        self.assertEqual(v_canonical.id, "piper:ngochuyennew")
        self.assertEqual(v_canonical.engine_voice_id, "ngochuyennew")

    def test_public_voice_list_single_ngochuyen_entry(self):
        """Public voice list must expose only ONE entry for Ngọc Huyền, using canonical ID."""
        settings = Settings()
        voices = tts_bridge.list_voices(settings)

        # Check all entries related to Ngọc Huyền
        huyen_entries = [
            v for v in voices
            if "ngochuyen" in v["voice_id"] or v["display_name"] == "Ngọc Huyền"
        ]

        self.assertEqual(
            len(huyen_entries),
            1,
            f"Expected exactly 1 Ngọc Huyền entry, found: {huyen_entries}",
        )

        canonical_entry = huyen_entries[0]
        self.assertEqual(canonical_entry["voice_id"], "piper:ngochuyennew")
        self.assertEqual(canonical_entry["display_name"], "Ngọc Huyền")
        self.assertTrue(canonical_entry["public_enabled"])

        # Old alias must NOT be in public selectable voice list
        voice_ids = [v["voice_id"] for v in voices]
        self.assertNotIn("piper:ngochuyen", voice_ids)
        self.assertIn("piper:ngochuyennew", voice_ids)

    def test_legacy_alias_accepted_for_jobs_and_guards(self):
        """Backend guard functions must still accept the legacy alias."""
        settings = Settings()

        # Both alias and canonical must be allowed locally
        self.assertTrue(tts_bridge.voice_is_local_allowed("piper:ngochuyen", settings))
        self.assertTrue(tts_bridge.voice_is_local_allowed("piper:ngochuyennew", settings))

        # ensure_voice_public must not raise for either
        try:
            tts_bridge.ensure_voice_public("piper:ngochuyen", settings)
            tts_bridge.ensure_voice_public("piper:ngochuyennew", settings)
        except Exception as exc:
            self.fail(f"ensure_voice_public raised unexpectedly: {exc}")

        # ensure_voice_runnable must not raise for either
        try:
            tts_bridge.ensure_voice_runnable("piper:ngochuyen", settings)
            tts_bridge.ensure_voice_runnable("piper:ngochuyennew", settings)
        except Exception as exc:
            self.fail(f"ensure_voice_runnable raised unexpectedly: {exc}")

    def test_recommended_fanfic_voices_canonical(self):
        """Recommended fanfic voices must list only the canonical piper:ngochuyennew."""
        piper_recs = [
            (provider, code, name)
            for provider, code, name in RECOMMENDED_FANFIC_VOICES
            if provider == "piper"
        ]
        self.assertEqual(
            piper_recs,
            [("piper", "ngochuyennew", "Ngọc Huyền")],
            "Recommended list must only have 1 canonical Ngọc Huyền entry",
        )

    def test_catalog_display_names(self):
        """Display name of ngochuyennew must be canonical 'Ngọc Huyền'."""
        self.assertEqual(NGHITTS_DISPLAY_NAMES["ngochuyennew"], "Ngọc Huyền")
        self.assertEqual(PIPER_PREFERRED_KEY, "ngochuyennew")


if __name__ == "__main__":
    unittest.main()
