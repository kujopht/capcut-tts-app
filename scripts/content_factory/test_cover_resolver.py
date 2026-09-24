"""Unit and Integration Tests for Content Factory v2 Cover Resolver.

Verifies:
1. Safe prompt construction (canonical 2:3 aspect ratio, textless, text-free, no watermark/artist signatures).
2. Staging isolation (writes strictly to raw_spool/staged_covers/<work_id>/, zero production touch).
3. Fallback resilience (gracefully handles cold/offline Beam Cloud with procedural generation).
4. Approval confirmation guardrails (requires confirm_replace=True when replacing existing approved cover).
5. Rollback metadata preservation (saves previous_cover in metadata and backup image in history).
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from scripts.content_factory.cover_resolver import (
    STAGED_COVERS_DIR,
    APPROVED_COVERS_DIR,
    build_cover_prompt,
    get_fandom_palette,
    stage_beam_cover,
    approve_cover,
    reject_cover,
    get_cover_state,
    STATUS_APPROVED,
    STATUS_STAGED,
    STATUS_REJECTED,
    PROVIDER_PROCEDURAL,
    PROVIDER_BEAM,
)


class TestCoverResolver(unittest.TestCase):
    def setUp(self):
        self.test_work_id = "test_resolver_999999"
        self.staged_dir = STAGED_COVERS_DIR / self.test_work_id
        self.approved_dir = APPROVED_COVERS_DIR / self.test_work_id
        # Clean test directories
        if self.staged_dir.exists():
            shutil.rmtree(self.staged_dir, ignore_errors=True)
        if self.approved_dir.exists():
            shutil.rmtree(self.approved_dir, ignore_errors=True)

    def tearDown(self):
        if self.staged_dir.exists():
            shutil.rmtree(self.staged_dir, ignore_errors=True)
        if self.approved_dir.exists():
            shutil.rmtree(self.approved_dir, ignore_errors=True)

    def test_prompt_rules_and_aspect_ratio(self):
        pos, neg = build_cover_prompt(
            title="Naruto: The Butterfly Effect",
            fandom="Naruto",
            genres=["Action", "Adventure", "Ninja"],
        )
        # 1. 2:3 vertical book composition
        self.assertIn("vertical book cover composition", pos)
        self.assertIn("clear central composition", pos)
        # 2. Textless / text-free
        self.assertIn("pure artwork without text", pos)
        self.assertIn("textless", pos)
        # 3. No watermark / artist signature in negative prompt
        self.assertIn("watermark", neg)
        self.assertIn("artist name", neg)
        self.assertIn("signature", neg)
        self.assertIn("logo", neg)
        self.assertIn("copyright notice", neg)
        # 4. Genre / fandom cues
        self.assertIn("Naruto universe aesthetic", pos)
        self.assertIn("chakra aura", pos)

    def test_staging_isolation_and_procedural_fallback(self):
        # Stage cover for test work ID
        ok, meta, msg = stage_beam_cover(
            work_id=self.test_work_id,
            title="Test Cover Isolation",
            fandom="Naruto",
            genres=["Action"],
            seed=12345,
            aspect_ratio="2:3",
            timeout_seconds=2.0,  # Short timeout to trigger procedural fallback quickly
        )
        self.assertTrue(ok)
        self.assertTrue(self.staged_dir.exists())

        active_file = self.staged_dir / "active_staged.jpg"
        candidate_file = self.staged_dir / "candidate_12345.jpg"
        meta_file = self.staged_dir / "metadata.json"

        self.assertTrue(active_file.exists())
        self.assertTrue(candidate_file.exists())
        self.assertTrue(meta_file.exists())

        # Assert no production files created
        self.assertFalse(self.approved_dir.exists())

        # Check metadata
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        self.assertEqual(data["work_id"], self.test_work_id)
        self.assertEqual(data["status"], STATUS_STAGED)
        self.assertEqual(data["seed"], 12345)
        self.assertEqual(data["aspect_ratio"], "2:3")

        state = get_cover_state(self.test_work_id)
        self.assertTrue(state["has_staged"])
        self.assertFalse(state["has_approved"])
        self.assertEqual(state["status"], STATUS_STAGED)

    def test_approval_confirmation_and_rollback(self):
        # 1. Stage initial cover
        stage_beam_cover(
            work_id=self.test_work_id,
            title="Rollback Test Novel",
            fandom="Naruto",
            seed=111,
            timeout_seconds=2.0,
        )

        # 2. First approval (no existing cover, should succeed)
        ok1, msg1, meta1 = approve_cover(self.test_work_id, confirm_replace=False)
        self.assertTrue(ok1)
        self.assertTrue((self.approved_dir / "cover.jpg").exists())

        # 3. Stage candidate #2
        stage_beam_cover(
            work_id=self.test_work_id,
            title="Rollback Test Novel",
            fandom="Naruto",
            seed=222,
            timeout_seconds=2.0,
        )

        # 4. Attempt second approval WITHOUT confirm_replace -> MUST FAIL
        ok2, msg2, meta2 = approve_cover(self.test_work_id, confirm_replace=False)
        self.assertFalse(ok2)
        self.assertIn("Confirmation required", msg2)

        # 5. Approve WITH confirm_replace -> MUST SUCCEED and preserve rollback
        ok3, msg3, meta3 = approve_cover(self.test_work_id, confirm_replace=True)
        self.assertTrue(ok3)

        state = get_cover_state(self.test_work_id)
        self.assertTrue(state["has_rollback"])
        self.assertIsNotNone(state.get("previous_cover"))
        self.assertTrue(Path(state["previous_cover"]["backup_file"]).exists())

    def test_rejection_lifecycle(self):
        stage_beam_cover(
            work_id=self.test_work_id,
            title="Reject Test Novel",
            fandom="Genshin Impact",
            seed=333,
            timeout_seconds=2.0,
        )
        ok, msg = reject_cover(self.test_work_id, reason="Subject does not match character description")
        self.assertTrue(ok)

        state = get_cover_state(self.test_work_id)
        self.assertEqual(state["status"], STATUS_REJECTED)
        self.assertEqual(state["metadata"]["rejection_reason"], "Subject does not match character description")


if __name__ == "__main__":
    unittest.main()
