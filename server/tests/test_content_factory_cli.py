"""
Unit tests for Content Factory Unified CLI & Pipeline Engine (PR-D).

Tests:
1. stage_selection: --from, --through, and explicit stage flags
2. resume: checkpoint reuse without re-execution
3. idempotency: multiple identical runs produce stable state
4. source_hash_invalidation: downstream invalidation on source text change
5. translation_cache_invalidation: cache identity changes with version/glossary
6. partial_tts_resume: resumes missing audio without re-synthesizing existing
7. announcement_exclusion: ignores author notes / announcements from reader chapters
8. display_order_mapping: maps source entry 2 -> reader chapter 1 contiguously
9. dry_run_mutation_prevention: zero Appwrite/R2 writes and fails closed on promotion
10. explicit_promotion_gate: promotion requires explicit --promote flag
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.content_factory.cli import (
    build_parser,
    resolve_stages,
    parse_stage_name,
)
from scripts.content_factory.content_classifier import ContentClassifier, EntryClassification
from scripts.content_factory.publish_quality_gate import compute_cache_identity
from scripts.content_factory.unified_pipeline import (
    PipelineCheckpoint,
    PipelineStage,
    PipelineState,
    StageResult,
    UnifiedContentPipeline,
)


class TestUnifiedPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.spool_dir = self.temp_dir / "raw_spool"
        self.spool_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. Stage selection
    def test_stage_selection_through_qa(self):
        parser = build_parser()
        args = parser.parse_args(["run", "136586", "--through", "qa"])
        stages = resolve_stages(args)
        expected = [
            PipelineStage.INTAKE,
            PipelineStage.CRAWL,
            PipelineStage.CLASSIFY,
            PipelineStage.TRANSLATE,
            PipelineStage.QA,
        ]
        self.assertEqual(stages, expected)
        self.assertNotIn(PipelineStage.COVER, stages)
        self.assertNotIn(PipelineStage.TTS, stages)
        self.assertNotIn(PipelineStage.PROMOTE, stages)

    def test_stage_selection_from_through_and_explicit(self):
        parser = build_parser()
        # From-through
        args = parser.parse_args(["run", "136586", "--from", "classify", "--through", "cover"])
        stages = resolve_stages(args)
        self.assertEqual(
            stages,
            [PipelineStage.CLASSIFY, PipelineStage.TRANSLATE, PipelineStage.QA, PipelineStage.COVER],
        )

        # Explicit stage flags
        args_explicit = parser.parse_args(["run", "136586", "--intake", "--crawl", "--tts"])
        stages_explicit = resolve_stages(args_explicit)
        self.assertEqual(stages_explicit, [PipelineStage.INTAKE, PipelineStage.CRAWL, PipelineStage.TTS])

    # 2. Resume
    def test_resume_checkpoint_reuse(self):
        cp = PipelineCheckpoint("test_work", self.spool_dir)
        res = StageResult(
            stage=PipelineStage.INTAKE,
            passed=True,
            status_label="PASS",
            summary="Intake complete",
            data={"glossary_terms": 45},
        )
        cp.record_stage(res, PipelineState.INTAKED)
        self.assertTrue(cp.is_stage_completed(PipelineStage.INTAKE))
        self.assertEqual(cp.current_state, PipelineState.INTAKED.value)

        # Reload from disk
        cp_reloaded = PipelineCheckpoint("test_work", self.spool_dir)
        self.assertTrue(cp_reloaded.is_stage_completed(PipelineStage.INTAKE))
        self.assertEqual(cp_reloaded.current_state, PipelineState.INTAKED.value)

    # 3. Idempotency
    def test_idempotency(self):
        cp = PipelineCheckpoint("idempotent_work", self.spool_dir)
        res1 = StageResult(PipelineStage.CRAWL, True, "PASS", "10 entries")
        cp.record_stage(res1, PipelineState.CRAWLED)
        state_first = cp.current_state
        completed_first = list(cp.completed_stages)

        # Record again identically
        res2 = StageResult(PipelineStage.CRAWL, True, "CACHED", "10 entries", cached=True)
        cp.record_stage(res2, PipelineState.CRAWLED)
        self.assertEqual(cp.current_state, state_first)
        self.assertEqual(cp.completed_stages, completed_first)

    # 4. Source-hash invalidation
    def test_source_hash_invalidation(self):
        cp = PipelineCheckpoint("hash_work", self.spool_dir)
        for st in [PipelineStage.INTAKE, PipelineStage.CRAWL, PipelineStage.CLASSIFY, PipelineStage.TRANSLATE, PipelineStage.QA]:
            cp.record_stage(StageResult(st, True, "PASS", "ok"), PipelineState.QA_PASSED)
        self.assertIn("translate", cp.completed_stages)
        self.assertIn("qa", cp.completed_stages)

        # Invalidate from translate
        cp.invalidate_from(PipelineStage.TRANSLATE)
        self.assertNotIn("translate", cp.completed_stages)
        self.assertNotIn("qa", cp.completed_stages)
        self.assertIn("crawl", cp.completed_stages)
        self.assertEqual(cp.current_state, PipelineState.CLASSIFIED.value)

    # 5. Translation-cache invalidation
    def test_translation_cache_invalidation(self):
        src_hash = "abc12345"
        id1 = compute_cache_identity(src_hash, glossary_version="v1", pipeline_version="fulltext-v1")
        id2 = compute_cache_identity(src_hash, glossary_version="v2", pipeline_version="fulltext-v1")
        id3 = compute_cache_identity(src_hash, glossary_version="v1", pipeline_version="fulltext-v2")
        self.assertNotEqual(id1, id2, "Glossary change must invalidate cache identity")
        self.assertNotEqual(id1, id3, "Pipeline version change must invalidate cache identity")

    # 6. Partial TTS resume
    def test_partial_tts_resume(self):
        pipeline = UnifiedContentPipeline("partial_tts", spool_dir=self.spool_dir, dry_run=True)
        crawl_dir = self.spool_dir / "crawled_chapters" / "partial_tts"
        crawl_dir.mkdir(parents=True, exist_ok=True)
        entries = [
            {"order": 1, "display_order": 1, "cid": "c1", "title": "Ch 1", "classification": "STORY_CHAPTER"},
            {"order": 2, "display_order": 2, "cid": "c2", "title": "Ch 2", "classification": "STORY_CHAPTER"},
            {"order": 3, "display_order": 3, "cid": "c3", "title": "Ch 3", "classification": "STORY_CHAPTER"},
        ]
        (crawl_dir / "crawl_manifest.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")

        # Fake staging audio for chapter 1 and 2 only (> 10000 bytes)
        staging_dir = self.spool_dir / "staging_audio" / "partial_tts"
        staging_dir.mkdir(parents=True, exist_ok=True)
        (staging_dir / "staging_ch_partial_tts_0001.mp3").write_bytes(b"A" * 15000)
        (staging_dir / "staging_ch_partial_tts_0002.mp3").write_bytes(b"A" * 15000)

        res = pipeline.run_tts()
        self.assertTrue(res.passed)
        self.assertEqual(res.data.get("staged_count"), 2)
        self.assertEqual(res.data.get("total_target"), 3)
        self.assertEqual(res.status_label, "PARTIAL_DRY_RUN")

    # 7. Announcement / Author Note exclusion
    def test_announcement_exclusion(self):
        classifier = ContentClassifier()
        dec_glos = classifier.classify_entry("Chapter 00 - Glossary", content="Terms and guide", source_order=1)
        self.assertEqual(dec_glos.entry_type, EntryClassification.AUTHOR_NOTE)
        self.assertFalse(dec_glos.display_in_toc)
        self.assertEqual(dec_glos.action, "ARCHIVE_IGNORE")

        dec_ann = classifier.classify_entry("Hiatus Announcement for Next Month", content="Taking a break", source_order=15)
        self.assertEqual(dec_ann.entry_type, EntryClassification.ANNOUNCEMENT)
        self.assertFalse(dec_ann.display_in_toc)

        dec_story = classifier.classify_entry("Chapter 1: The Beginning", content="Once upon a time in Konoha...", source_order=2)
        self.assertEqual(dec_story.entry_type, EntryClassification.STORY_CHAPTER)
        self.assertTrue(dec_story.display_in_toc)

    # 8. Display order mapping
    def test_display_order_mapping(self):
        classifier = ContentClassifier()
        raw_entries = [
            {"source_order": 1, "title": "Chapter 00 - Glossary", "content": "Characters list"},
            {"source_order": 2, "title": "Chapter 0 - Prologue", "content": "Prologue of story"},
            {"source_order": 3, "title": "Chapter 1 - Awakening", "content": "Chapter 1 story body"},
        ]
        mapped = classifier.calculate_display_orders(raw_entries)
        self.assertIsNone(mapped[0]["display_order"], "Glossary must have display_order=None")
        self.assertEqual(mapped[1]["display_order"], 1, "Source entry 2 must become Reader Chapter 1")
        self.assertEqual(mapped[2]["display_order"], 2, "Source entry 3 must become Reader Chapter 2")

    # 9. Dry-run mutation prevention
    def test_dry_run_mutation_prevention(self):
        pipeline = UnifiedContentPipeline("safe_work", spool_dir=self.spool_dir, dry_run=True)
        res_promote = pipeline.run_promote()
        self.assertFalse(res_promote.passed)
        self.assertEqual(res_promote.status_label, "BLOCKED")
        self.assertIn("prohibited in --dry-run mode", res_promote.summary)

    # 10. Explicit promotion gate
    def test_explicit_promotion_gate(self):
        parser = build_parser()
        # Without --promote, PROMOTE stage must never appear
        args_default = parser.parse_args(["run", "136586"])
        stages_default = resolve_stages(args_default)
        self.assertNotIn(PipelineStage.PROMOTE, stages_default)

        # With --through promote without --promote flag, PROMOTE must still be excluded
        args_through = parser.parse_args(["run", "136586", "--through", "promote"])
        stages_through = resolve_stages(args_through)
        self.assertNotIn(PipelineStage.PROMOTE, stages_through)

        # Only with explicit --promote is PROMOTE included
        args_promote = parser.parse_args(["run", "136586", "--promote", "--no-dry-run"])
        stages_promote = resolve_stages(args_promote)
        self.assertIn(PipelineStage.PROMOTE, stages_promote)


if __name__ == "__main__":
    unittest.main()
