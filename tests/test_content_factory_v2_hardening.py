"""
Tests for Content Factory v2 Quality Gate, Content Classifier, Reader Order, and Living Novel Sync.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from scripts.content_factory.content_classifier import ContentClassifier, EntryClassification
from scripts.content_factory.publish_quality_gate import (
    PublishQualityGate,
    QualityGateResult,
    compute_cache_identity,
)
from server.living_novel_sync import LivingNovelRegistry


class TestPublishQualityGate(unittest.TestCase):
    def setUp(self):
        self.gate = PublishQualityGate(glossary_version="hatake_v2")

    def test_pass_all_11_checks(self):
        source_text = "Kakashi adjusted his headband and looked at the horizon. " * 30
        trans_text = "Kakashi chỉnh lại băng trán của mình và nhìn về phía chân trời. " * 30
        chunks_src = [
            {"chunk_id": "c01", "text": "Kakashi adjusted his headband. " * 15},
            {"chunk_id": "c02", "text": "He looked at the horizon. " * 15},
        ]
        chunks_tr = [
            {"chunk_id": "c01", "text": "Kakashi chỉnh lại băng trán của mình. " * 15},
            {"chunk_id": "c02", "text": "Cậu nhìn về phía chân trời. " * 15},
        ]
        res = self.gate.audit_chapter(
            chapter_id="chp_test_0001",
            source_order=1,
            display_order=1,
            source_text=source_text,
            translated_text=trans_text,
            classification=EntryClassification.STORY_CHAPTER,
            source_chunks=chunks_src,
            translated_chunks=chunks_tr,
            tts_input_text=trans_text,
            audio_duration_seconds=120.0,
        )
        self.assertTrue(res.passed_all_checks, f"Gate failed with reasons: {res.blocking_reasons}")
        self.assertTrue(res.publish_allowed)
        self.assertEqual(len(res.blocking_reasons), 0)
        self.assertIn("✅", res.summary_badge())

    def test_block_on_empty_source(self):
        res = self.gate.audit_chapter(
            chapter_id="chp_test_empty_src",
            source_order=1,
            source_text="",
            translated_text="Đoạn văn dịch hợp lệ.",
            classification=EntryClassification.STORY_CHAPTER,
        )
        self.assertFalse(res.publish_allowed)
        self.assertTrue(any("Nguồn chương trống" in r for r in res.blocking_reasons))

    def test_block_on_unclassified_entry(self):
        res = self.gate.audit_chapter(
            chapter_id="chp_test_unknown",
            source_order=1,
            source_text="Some valid content here. " * 10,
            translated_text="Nội dung hợp lệ tại đây. " * 10,
            classification=EntryClassification.UNKNOWN,
        )
        self.assertFalse(res.publish_allowed)
        self.assertTrue(any("UNKNOWN" in r for r in res.blocking_reasons))

    def test_block_on_chunk_count_mismatch(self):
        chunks_src = [{"chunk_id": "c01", "text": "One " * 20}, {"chunk_id": "c02", "text": "Two " * 20}]
        chunks_tr = [{"chunk_id": "c01", "text": "Một " * 20}]
        res = self.gate.audit_chapter(
            chapter_id="chp_test_mismatch",
            source_order=1,
            source_text="One " * 20 + "\n\n" + "Two " * 20,
            translated_text="Một " * 20,
            classification=EntryClassification.STORY_CHAPTER,
            source_chunks=chunks_src,
            translated_chunks=chunks_tr,
        )
        self.assertFalse(res.publish_allowed)
        self.assertTrue(any("không khớp" in r for r in res.blocking_reasons))

    def test_block_on_empty_translated_chunk(self):
        chunks_src = [{"chunk_id": "c01", "text": "One " * 20}, {"chunk_id": "c02", "text": "Two " * 20}]
        chunks_tr = [{"chunk_id": "c01", "text": "Một " * 20}, {"chunk_id": "c02", "text": "   "}]
        res = self.gate.audit_chapter(
            chapter_id="chp_test_blank_chunk",
            source_order=1,
            source_text="One " * 20 + "\n\n" + "Two " * 20,
            translated_text="Một " * 20,
            classification=EntryClassification.STORY_CHAPTER,
            source_chunks=chunks_src,
            translated_chunks=chunks_tr,
        )
        self.assertFalse(res.publish_allowed)
        self.assertTrue(any("chunk dịch rỗng" in r for r in res.blocking_reasons))

    def test_block_on_accidental_summarization(self):
        res = self.gate.audit_chapter(
            chapter_id="chp_test_sum",
            source_order=1,
            source_text="Original long text here. " * 20,
            translated_text="Tóm tắt: Kakashi luyện tập cùng Minato và hoàn thành nhẫn thuật.",
            classification=EntryClassification.STORY_CHAPTER,
        )
        self.assertFalse(res.publish_allowed)
        self.assertTrue(any("tóm tắt" in r.lower() for r in res.blocking_reasons))

    def test_block_on_model_cutoff(self):
        res = self.gate.audit_chapter(
            chapter_id="chp_test_cutoff",
            source_order=1,
            source_text="Original text here. " * 20,
            translated_text="Kakashi nhìn thấy ánh mắt nghiêm túc của cha mình và",
            classification=EntryClassification.STORY_CHAPTER,
        )
        self.assertFalse(res.publish_allowed)
        self.assertTrue(any("cắt cụt" in r.lower() or "cutoff" in r.lower() for r in res.blocking_reasons))

    def test_block_on_tts_input_hash_mismatch(self):
        res = self.gate.audit_chapter(
            chapter_id="chp_test_hash_mismatch",
            source_order=1,
            source_text="Original text here. " * 20,
            translated_text="Bản dịch tiếng Việt chuẩn xác và đầy đủ chi tiết. " * 10,
            classification=EntryClassification.STORY_CHAPTER,
            tts_input_text="Bản dịch tiếng Việt đã bị chỉnh sửa khác hoàn toàn.",
            audio_duration_seconds=10.0,
        )
        self.assertFalse(res.publish_allowed)
        self.assertTrue(any("đầu vào TTS không khớp" in r for r in res.blocking_reasons))

    def test_ratio_alone_does_not_block(self):
        source_text = "The leaf fell slowly. " * 30
        trans_text = "Chiếc lá rơi chầm chậm xuống mặt đất trong buổi chiều hoàng hôn tĩnh lặng của làng Lá. " * 30
        chunks_src = [{"chunk_id": "c01", "text": source_text}]
        chunks_tr = [{"chunk_id": "c01", "text": trans_text}]
        res = self.gate.audit_chapter(
            chapter_id="chp_test_ratio",
            source_order=1,
            source_text=source_text,
            translated_text=trans_text,
            classification=EntryClassification.STORY_CHAPTER,
            source_chunks=chunks_src,
            translated_chunks=chunks_tr,
            tts_input_text=trans_text,
            audio_duration_seconds=300.0,
        )
        self.assertTrue(res.passed_all_checks)
        self.assertTrue(res.publish_allowed)


class TestContentClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = ContentClassifier()

    def test_classification_rules(self):
        d1 = self.classifier.classify_entry("Ch. 1 - The White Fang's Son", content="A long chapter " * 100)
        self.assertEqual(d1.entry_type, EntryClassification.STORY_CHAPTER)

        d2 = self.classifier.classify_entry("Interlude - The Land of Wind", content="A long story " * 100)
        self.assertEqual(d2.entry_type, EntryClassification.EXTRA)

        d3 = self.classifier.classify_entry("Side Story 1: White Fang's Honor", content="A long story " * 100)
        self.assertEqual(d3.entry_type, EntryClassification.EXTRA)

        d4 = self.classifier.classify_entry("Announcement - Hiatus for Exams", content="Taking a break.")
        self.assertEqual(d4.entry_type, EntryClassification.ANNOUNCEMENT)

        d5 = self.classifier.classify_entry("Important Notice: Schedule Update", content="Update delayed.")
        self.assertEqual(d5.entry_type, EntryClassification.ANNOUNCEMENT)

        d6 = self.classifier.classify_entry("Author Note: Thanks for 1000 followers", content="Thanks everyone.")
        self.assertEqual(d6.entry_type, EntryClassification.AUTHOR_NOTE)

    def test_hatake_25_upstream_entries_ordering(self):
        """Validates that 25 upstream entries map cleanly to 23 reader chapters and 2 archived announcements."""
        entries = [
            {"source_order": i, "source_title": f"Chapter {i}: Title {i}", "source_text": "Story text " * 100}
            for i in range(1, 19)
        ]
        entries.append({"source_order": 19, "source_title": "Archived Announcement: Hiatus Notice", "source_text": "Break"})
        entries.append({"source_order": 20, "source_title": "Chapter 19: The Silence Behind The Door", "source_text": "Story " * 100})
        entries.append({"source_order": 21, "source_title": "Chapter 20: Happy Birthday", "source_text": "Story " * 100})
        entries.append({"source_order": 22, "source_title": "Interlude: The White Fang Strikes Fear", "source_text": "Story " * 100})
        entries.append({"source_order": 23, "source_title": "Announcement: Rewrites and Notes", "source_text": "Notes"})
        entries.append({"source_order": 24, "source_title": "Chapter 21: Back to School", "source_text": "Story " * 100})
        entries.append({"source_order": 25, "source_title": "Chapter 22: Classmates", "source_text": "Story " * 100})

        res = self.classifier.calculate_display_orders(entries, work_id="156690")
        self.assertEqual(len(res), 25)

        # Count classifications
        story_chapters = [r for r in res if r["classification"] == EntryClassification.STORY_CHAPTER.value]
        extras = [r for r in res if r["classification"] == EntryClassification.EXTRA.value]
        announcements = [r for r in res if r["classification"] == EntryClassification.ANNOUNCEMENT.value]

        self.assertEqual(len(announcements), 2)
        self.assertEqual(len(extras), 1)
        self.assertEqual(len(story_chapters) + len(extras), 23)

        # Verify contiguous reader display orders 1..23
        reader_entries = [r for r in res if r["display_order"] is not None]
        self.assertEqual(len(reader_entries), 23)
        display_orders = [r["display_order"] for r in reader_entries]
        self.assertEqual(display_orders, list(range(1, 24)))

        # Verify announcements have display_order is None and display_in_toc is False
        for a in announcements:
            self.assertIsNone(a["display_order"])
            self.assertFalse(a["display_in_toc"])

        # Check specific mapping for chapter 22 (Interlude -> Extra 1, display 21)
        ch22 = next(r for r in res if r["source_order"] == 22)
        self.assertEqual(ch22["display_order"], 21)
        self.assertEqual(ch22["classification"], EntryClassification.EXTRA.value)

        # Check source 24 (Chapter 21 -> display 22)
        ch24 = next(r for r in res if r["source_order"] == 24)
        self.assertEqual(ch24["display_order"], 22)

        # Check source 25 (Chapter 22 -> display 23)
        ch25 = next(r for r in res if r["source_order"] == 25)
        self.assertEqual(ch25["display_order"], 23)


class TestLivingNovelRegistry(unittest.TestCase):
    def setUp(self):
        import uuid
        self.test_dir = Path("scratch/test_registry_tmp")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.test_dir / f"test_{uuid.uuid4().hex}.sqlite"
        self.registry = LivingNovelRegistry(self.db_path)

    def tearDown(self):
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except Exception:
                pass

    def test_schema_and_display_order_columns(self):
        with sqlite3.connect(self.db_path) as conn:
            cols = [c[1] for c in conn.execute("PRAGMA table_info(source_chapter_registry)").fetchall()]
            self.assertIn("display_order", cols)
            self.assertIn("entry_type", cols)

    def test_record_chapter_and_announcement(self):
        self.registry.upsert_novel(
            platform="royalroad",
            work_id="test_work",
            appwrite_novel_id="nov_test",
            source_url="https://royalroad.com/fiction/123",
            title="Test Work",
            author="Test Author",
        )

        # Record standard chapter
        self.registry.record_chapter_synced(
            platform="royalroad",
            work_id="test_work",
            chapter_id="rr_1",
            order=1,
            appwrite_chapter_id="chp_1",
            source_text_hash="hash_1",
            display_order=1,
            entry_type="STORY_CHAPTER",
        )

        # Record announcement
        self.registry.record_announcement_archived(
            platform="royalroad",
            work_id="test_work",
            chapter_id="rr_ann_1",
            order=2,
            appwrite_chapter_id="chp_ann_1",
            source_text_hash="hash_ann",
        )

        with sqlite3.connect(self.db_path) as conn:
            row_ch = conn.execute(
                "SELECT display_order, entry_type, sync_status FROM source_chapter_registry WHERE source_chapter_id = 'rr_1'"
            ).fetchone()
            self.assertEqual(row_ch[0], 1)
            self.assertEqual(row_ch[1], "STORY_CHAPTER")
            self.assertEqual(row_ch[2], "SYNCED")

            row_ann = conn.execute(
                "SELECT display_order, entry_type, sync_status FROM source_chapter_registry WHERE source_chapter_id = 'rr_ann_1'"
            ).fetchone()
            self.assertIsNone(row_ann[0])
            self.assertEqual(row_ann[1], "ANNOUNCEMENT")
            self.assertEqual(row_ann[2], "ARCHIVED")


class TestProductionHatakeRegistryState(unittest.TestCase):
    """Verifies that the local SQLite registry matches production requirements."""

    def setUp(self):
        self.db_path = Path("raw_spool/living_novel_registry.sqlite")
        if not self.db_path.exists():
            self.skipTest("Local production registry not present")

    def test_canonical_25_upstream_entries(self):
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT source_chapter_id, chapter_order, display_order, entry_type, sync_status, appwrite_chapter_id, audio_track_id "
                "FROM source_chapter_registry WHERE source_platform = 'royalroad' AND source_work_id = '156690' "
                "ORDER BY chapter_order ASC"
            ).fetchall()

            self.assertEqual(len(rows), 25, f"Expected exactly 25 upstream entries, found {len(rows)}")

            # Verify display_order 1..23
            reader_rows = [r for r in rows if r[2] is not None]
            self.assertEqual(len(reader_rows), 23)
            display_orders = [r[2] for r in reader_rows]
            self.assertEqual(display_orders, list(range(1, 24)))

            # Verify chapters 1..11 untouched
            for r in rows[:11]:
                self.assertEqual(r[1], r[2])  # source_order == display_order for 1..11
                self.assertIsNotNone(r[6])   # audio_track_id present
                self.assertEqual(r[4], "SYNCED")

            # Verify announcements 19 and 23
            ann19 = next(r for r in rows if r[1] == 19)
            self.assertEqual(ann19[3], "ANNOUNCEMENT")
            self.assertIsNone(ann19[2])
            self.assertEqual(ann19[4], "ARCHIVED")

            ann23 = next(r for r in rows if r[1] == 23)
            self.assertEqual(ann23[3], "ANNOUNCEMENT")
            self.assertIsNone(ann23[2])
            self.assertEqual(ann23[4], "ARCHIVED")

            # Verify repaired chapters 12-18, 20-22, 24-25 all have audio
            repaired_orders = [12, 13, 14, 15, 16, 17, 18, 20, 21, 22, 24, 25]
            for order in repaired_orders:
                ch = next(r for r in rows if r[1] == order)
                self.assertIsNotNone(ch[6], f"Chapter with source_order {order} missing audio_track_id")
                self.assertEqual(ch[4], "SYNCED")


class TestProductionDiffEngine(unittest.TestCase):
    def setUp(self):
        from scripts.content_factory.production_diff_engine import ProductionDiffEngine, DiffStatus
        self.ProductionDiffEngine = ProductionDiffEngine
        self.DiffStatus = DiffStatus
        self.db_path = Path("raw_spool/living_novel_registry.sqlite")
        if not self.db_path.exists():
            self.skipTest("Local production registry not present")
        self.engine = ProductionDiffEngine(self.db_path)

    def test_check_source_is_complete_noop_when_unchanged(self):
        """Simulates checking upstream RoyalRoad 156690 when all 25 chapters are already registered."""
        with sqlite3.connect(self.db_path) as conn:
            reg_title = conn.execute("SELECT title_original FROM source_novel_registry WHERE source_work_id = '156690'").fetchone()[0]
            rows = conn.execute(
                "SELECT source_chapter_id, chapter_order, source_text_hash FROM source_chapter_registry "
                "WHERE source_platform = 'royalroad' AND source_work_id = '156690' ORDER BY chapter_order ASC"
            ).fetchall()

        candidate_data = {
            "platform": "royalroad",
            "work_id": "156690",
            "title": reg_title,
            "chapters": [
                {
                    "order": r[1],
                    "title": f"Chapter {r[1]}",
                    "source_chapter_id": r[0],
                    "source_text_hash": r[2],
                }
                for r in rows
            ],
        }

        diff_report = self.engine.diff(candidate_data)
        self.assertEqual(diff_report.total_source_chapters, 25)
        self.assertEqual(diff_report.unchanged_count, 25)
        self.assertEqual(diff_report.new_count, 0)
        self.assertEqual(diff_report.updated_count, 0)
        self.assertEqual(diff_report.estimated_llm_calls, 0)
        self.assertEqual(diff_report.estimated_tts_jobs, 0)
        self.assertFalse(diff_report.metadata_changed)

        for d in diff_report.chapter_diffs:
            self.assertEqual(d.status, self.DiffStatus.UNCHANGED)
            self.assertEqual(d.action_preview, "SKIP (0 LLM, 0 TTS)")


if __name__ == "__main__":
    unittest.main()
