"""
Unit and Integration Tests for Living Novel Continuous Update Orchestrator.
Covers NEW_CHAPTER, UNCHANGED (NO-OP), and STALE_SOURCE (silent rewrite) reconciliation.
"""

from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
import shutil

from server.crawler_intake_contract import (
    RawCrawlerChapter,
    RawCrawlerWork,
    compute_source_text_hash,
)
from server.living_novel_sync import (
    IsolatedStagingStorage,
    LivingNovelRegistry,
    LivingNovelSyncOrchestrator,
)


class TestLivingNovelSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.db_path = self.temp_dir / "test_living_novel_sync.sqlite"
        self.registry = LivingNovelRegistry(self.db_path)
        self.storage = IsolatedStagingStorage()
        self.tx_log = []
        self.tts_log = []

        def mock_tx(src: str, title: str) -> str:
            self.tx_log.append(title)
            return f"[VI] {title}: {src}"

        def mock_tts(vi: str, novel_id: str, order: int) -> dict:
            self.tts_log.append((novel_id, order))
            return {
                "audio_url": f"https://cdn.fanfic.world/{novel_id}_{order}.mp3",
                "duration": 120.0,
                "voice": "piper:ngochuyennew"
            }

        self.orchestrator = LivingNovelSyncOrchestrator(
            registry=self.registry,
            storage=self.storage,
            translator=mock_tx,
            tts_synthesizer=mock_tts
        )
        self.novel_id = "test_novel_001"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_new_chapter_then_noop_then_hash_edit(self):
        # 1. First sync with Chapter 1
        work_1 = RawCrawlerWork(
            source_id="fiction_123",
            source_url="https://example.com/fiction/123",
            title="Living Test Fiction",
            author="Author One",
            chapters=[
                RawCrawlerChapter(
                    source_chapter_id="c_01",
                    source_order=1,
                    source_title="Chapter 1: The Beginning",
                    source_text="This is chapter 1 original text content.",
                )
            ]
        )

        res_1 = self.orchestrator.sync_manifest(work_1, self.novel_id)
        self.assertEqual(res_1.new_chapters_count, 1)
        self.assertEqual(res_1.unchanged_chapters_count, 0)
        self.assertEqual(res_1.translation_calls_made, 1)
        self.assertEqual(res_1.tts_jobs_created, 1)
        self.assertEqual(self.storage.novels[self.novel_id]["total_chapters"], 1)

        # 2. Second sync with identical manifest -> Complete NO-OP
        mutations_before = self.storage.mutation_counter
        res_2 = self.orchestrator.sync_manifest(work_1, self.novel_id)
        self.assertTrue(res_2.is_complete_noop)
        self.assertEqual(res_2.unchanged_chapters_count, 1)
        self.assertEqual(res_2.translation_calls_made, 0)
        self.assertEqual(res_2.tts_jobs_created, 0)
        self.assertEqual(self.storage.mutation_counter, mutations_before)

        # 3. Third sync with Chapter 2 added
        work_2 = RawCrawlerWork(
            source_id="fiction_123",
            source_url="https://example.com/fiction/123",
            title="Living Test Fiction",
            author="Author One",
            chapters=[
                work_1.chapters[0],
                RawCrawlerChapter(
                    source_chapter_id="c_02",
                    source_order=2,
                    source_title="Chapter 2: The Next Step",
                    source_text="This is chapter 2 original text content.",
                )
            ]
        )

        res_3 = self.orchestrator.sync_manifest(work_2, self.novel_id)
        self.assertEqual(res_3.new_chapters_count, 1)
        self.assertEqual(res_3.unchanged_chapters_count, 1)
        self.assertEqual(res_3.translation_calls_made, 1)  # only chapter 2
        self.assertEqual(res_3.tts_jobs_created, 1)        # only chapter 2
        self.assertEqual(self.storage.novels[self.novel_id]["total_chapters"], 2)

        # 4. Fourth sync with Chapter 2 rewritten upstream
        work_3 = RawCrawlerWork(
            source_id="fiction_123",
            source_url="https://example.com/fiction/123",
            title="Living Test Fiction",
            author="Author One",
            chapters=[
                work_1.chapters[0],
                RawCrawlerChapter(
                    source_chapter_id="c_02",
                    source_order=2,
                    source_title="Chapter 2: The Next Step (Rewritten)",
                    source_text="This is REWRITTEN chapter 2 text content.",
                )
            ]
        )

        res_4 = self.orchestrator.sync_manifest(work_3, self.novel_id)
        self.assertEqual(res_4.new_chapters_count, 0)
        self.assertEqual(res_4.edited_chapters_count, 1)
        self.assertEqual(res_4.unchanged_chapters_count, 1)
        self.assertEqual(res_4.translation_calls_made, 1)
        self.assertEqual(res_4.tts_jobs_created, 1)

        # Chapter 2 ID preserved
        ch2_doc = self.storage.chapters[f"ch_{self.novel_id}_0002"]
        self.assertIn("REWRITTEN", ch2_doc["content"])
        self.assertEqual(ch2_doc["order"], 2)


if __name__ == "__main__":
    unittest.main()
