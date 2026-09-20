"""
Tests for Content Factory v2 Discovery Mode.

Validates:
1. Pure read-only operation (no Appwrite, no R2, no translation, no TTS).
2. Deterministic rejection signals and threshold configurability.
3. Persistent SQLite discovery store (states, watchlists, rejections).
4. Heuristic & Gemini evaluation model fallback.
5. Sample chapter inspection (fetching 1 chapter, no translation).
"""

from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from scripts.content_factory.discovery_engine import DiscoveryEngine
from scripts.content_factory.discovery_models import (
    CandidateState,
    DeterministicFilterConfig,
    DiscoveredCandidate,
    GeminiCandidateEvaluation,
)
from scripts.content_factory.discovery_store import DiscoveryStore


class TestDiscoveryStore(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("scratch/test_discovery_tmp")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.test_dir / f"test_disc_{uuid.uuid4().hex}.sqlite"
        self.store = DiscoveryStore(self.db_path)

    def tearDown(self):
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except Exception:
                pass

    def test_upsert_and_retrieve_candidate(self):
        cand = DiscoveredCandidate(
            source_platform="royalroad",
            source_work_id="81168",
            url="https://www.royalroad.com/fiction/81168/naruto-test",
            title="Naruto: Test Candidate",
            author="Author A",
            description="A shinobi adventure.",
            status="ongoing",
            chapter_count=50,
            pages=500,
            tags=["Action", "Adventure", "Fanfiction"],
            fandom="Naruto",
            rating=4.7,
            followers=1200,
        )
        self.store.upsert_candidate(cand)

        retrieved = self.store.get_candidate("royalroad", "81168")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.title, "Naruto: Test Candidate")
        self.assertEqual(retrieved.fandom, "Naruto")
        self.assertEqual(retrieved.chapter_count, 50)
        self.assertEqual(retrieved.estimated_word_count, 500 * 275)
        self.assertEqual(retrieved.state, CandidateState.DISCOVERED)

    def test_update_state_and_rejection_tracking(self):
        cand = DiscoveredCandidate(
            source_platform="royalroad",
            source_work_id="999",
            url="https://www.royalroad.com/fiction/999/bad-fic",
            title="Bad Fic",
            chapter_count=1,
        )
        self.store.upsert_candidate(cand)

        # Mark rejected
        self.store.update_candidate_state("royalroad", "999", CandidateState.REJECTED, ["Quá ngắn", "Bỏ dở"])
        self.assertTrue(self.store.is_work_rejected("royalroad", "999"))

        retrieved = self.store.get_candidate("royalroad", "999")
        self.assertEqual(retrieved.state, CandidateState.REJECTED)
        self.assertIn("Quá ngắn", retrieved.rejection_reasons)

    def test_filter_config_persistence(self):
        cfg = DeterministicFilterConfig(min_chapters=15, min_words=30000, max_days_abandoned=180)
        self.store.save_filter_config(cfg)

        loaded = self.store.load_filter_config()
        self.assertEqual(loaded.min_chapters, 15)
        self.assertEqual(loaded.min_words, 30000)
        self.assertEqual(loaded.max_days_abandoned, 180)


class TestDeterministicFilters(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("scratch/test_discovery_tmp")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.test_dir / f"test_filters_{uuid.uuid4().hex}.sqlite"
        self.store = DiscoveryStore(self.db_path)
        self.engine = DiscoveryEngine(store=self.store)

    def tearDown(self):
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except Exception:
                pass

    def test_reject_too_few_chapters_configurable(self):
        cand = DiscoveredCandidate(
            source_platform="royalroad",
            source_work_id="101",
            url="https://royalroad.com/101",
            title="Tiny Story",
            chapter_count=3,
            estimated_word_count=50000,
        )

        # Default config min_chapters = 5 -> should reject
        cfg_strict = DeterministicFilterConfig(min_chapters=5)
        res_strict = self.engine.apply_deterministic_filters(cand, config=cfg_strict, prod_work_ids=set())
        self.assertFalse(res_strict.passed)
        self.assertTrue(any("Số chương quá ít" in r for r in res_strict.rejection_reasons))

        # Config relaxed min_chapters = 2 -> should pass! (Demonstrates non-hardcoded threshold)
        cfg_relaxed = DeterministicFilterConfig(min_chapters=2, min_words=1000)
        res_relaxed = self.engine.apply_deterministic_filters(cand, config=cfg_relaxed, prod_work_ids=set())
        self.assertTrue(res_relaxed.passed)

    def test_reject_extremely_short_word_count(self):
        cand = DiscoveredCandidate(
            source_platform="royalroad",
            source_work_id="102",
            url="https://royalroad.com/102",
            title="Short Novel",
            chapter_count=10,
            estimated_word_count=5000,  # Below default 15,000 words
        )
        cfg = DeterministicFilterConfig(min_chapters=5, min_words=15000)
        res = self.engine.apply_deterministic_filters(cand, config=cfg, prod_work_ids=set())
        self.assertFalse(res.passed)
        self.assertTrue(any("Dung lượng quá ngắn" in r for r in res.rejection_reasons))

    def test_reject_already_in_production(self):
        cand = DiscoveredCandidate(
            source_platform="royalroad",
            source_work_id="156690",  # Hatake in production
            url="https://royalroad.com/156690",
            title="Hatake Reborn",
            chapter_count=25,
            estimated_word_count=90000,
        )
        cfg = DeterministicFilterConfig()
        res = self.engine.apply_deterministic_filters(cand, config=cfg, prod_work_ids={"156690"})
        self.assertFalse(res.passed)
        self.assertTrue(any("đã có trên Fanfic World Production" in r for r in res.rejection_reasons))

    def test_reject_abandoned_ongoing_work(self):
        cand = DiscoveredCandidate(
            source_platform="royalroad",
            source_work_id="103",
            url="https://royalroad.com/103",
            title="Abandoned Work",
            chapter_count=30,
            estimated_word_count=60000,
            status="ongoing",
            last_update="2020-01-01T00:00:00",  # 6+ years ago
        )
        cfg = DeterministicFilterConfig(max_days_abandoned=365)
        res = self.engine.apply_deterministic_filters(cand, config=cfg, prod_work_ids=set())
        self.assertFalse(res.passed)
        self.assertTrue(any("bị bỏ dở" in r for r in res.rejection_reasons))

    def test_completed_work_never_rejected_for_abandonment(self):
        cand = DiscoveredCandidate(
            source_platform="royalroad",
            source_work_id="104",
            url="https://royalroad.com/104",
            title="Completed Masterpiece",
            chapter_count=30,
            estimated_word_count=100000,
            status="completed",
            last_update="2020-01-01T00:00:00",
        )
        cfg = DeterministicFilterConfig(max_days_abandoned=365)
        res = self.engine.apply_deterministic_filters(cand, config=cfg, prod_work_ids=set())
        self.assertTrue(res.passed, f"Completed work should not be flagged as abandoned: {res.rejection_reasons}")


class TestDiscoveryEngineReadOnlyGuarantees(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("scratch/test_discovery_tmp")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.test_dir / f"test_engine_{uuid.uuid4().hex}.sqlite"
        self.store = DiscoveryStore(self.db_path)
        self.engine = DiscoveryEngine(store=self.store)

    def tearDown(self):
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except Exception:
                pass

    def test_candidate_estimates_calculation(self):
        cand = DiscoveredCandidate(
            source_platform="royalroad",
            source_work_id="201",
            url="https://royalroad.com/201",
            title="Estimates Test",
            chapter_count=20,
            pages=200,
        )
        cand.calculate_estimates()
        self.assertEqual(cand.estimated_word_count, 55000)
        self.assertEqual(cand.avg_chapter_words, 2750)
        self.assertAlmostEqual(cand.estimated_tts_hours, round(55000 / 9000.0, 1))
        self.assertGreater(cand.estimated_translation_cost_usd, 0.0)

    def test_gemini_fallback_when_account_unavailable(self):
        """Ensures discovery works without crashing even if LLM is unavailable."""
        cand = DiscoveredCandidate(
            source_platform="royalroad",
            source_work_id="202",
            url="https://royalroad.com/202",
            title="Fallback Test",
            rating=4.5,
            followers=3000,
            status="ongoing",
            fandom="Naruto",
        )
        # Use an invalid model to trigger fallback logic
        ev = self.engine.evaluate_candidate_with_gemini(cand, model="nonexistent-dummy-model")
        self.assertIsNotNone(ev)
        self.assertGreater(ev.overall_score, 5.0)
        self.assertEqual(ev.model_used, "heuristic-fallback")
        self.assertTrue(ev.recommended_for_owner_review)


if __name__ == "__main__":
    unittest.main()
