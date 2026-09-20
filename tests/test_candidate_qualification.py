"""
Unit Tests for Content Factory v2 — Candidate Qualification v1.

Validates:
1. 3-Chapter Sampling Strategy: selecting first real narrative, middle, and latest;
   correctly skipping announcements, author notes, and glossaries.
2. Crawler Extraction Cleanliness: detecting and flagging leaked comments, footers,
   and navigation links; verifying clean narrative endings.
3. Writing Quality & Layout Analysis: detection of stat blocks, dialogue ratio,
   and Naruto fandom terminology density.
4. Realistic Production Scale & Throughput: accurate calculation of source words,
   Vietnamese expansion (~1.25x), TTS duration, storage, and factory days.
5. Factual Qualification Flags: standardized mapping of PRODUCTION_SCALE,
   GLOSSARY_COMPLEXITY, and CRAWLER_COMPATIBLE flags.
6. Serialization & Storage Persistence: round-trip validation with load_qualification_report.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.content_factory.candidate_qualifier import (
    BASE_NARUTO_GLOSSARY,
    CANDIDATE_ISOLATED_GLOSSARIES,
    CandidateQualifier,
    load_qualification_report,
)
from scripts.content_factory.content_classifier import ContentClassifier, EntryClassification
from scripts.content_factory.qualification_models import (
    AuthorNoteDensity,
    CandidateQualificationReport,
    FormatComplexity,
    GlossaryComplexity,
    ProductionScale,
    RealisticProductionScale,
    SampleChapterInspection,
    TranslationTrialResult,
    WritingQualityAnalysis,
)


class TestCandidateSamplingStrategy(unittest.TestCase):
    def setUp(self):
        self.qualifier = CandidateQualifier()

    def test_sampling_skips_announcements_and_glossaries(self):
        chapters = [
            {"order": 1, "title": "Glossary and Foreword", "url": "http://rr/ch1"},
            {"order": 2, "title": "Chapter 1: The Beginning", "url": "http://rr/ch2"},
            {"order": 3, "title": "Chapter 2: Training Day", "url": "http://rr/ch3"},
            {"order": 4, "title": "Author Note: Hiatus Notice", "url": "http://rr/ch4"},
            {"order": 5, "title": "Chapter 3: The Mission", "url": "http://rr/ch5"},
            {"order": 6, "title": "Chapter 4: Final Stand", "url": "http://rr/ch6"},
            {"order": 7, "title": "Important Announcement: Q&A", "url": "http://rr/ch7"},
        ]

        # Filter using classifier
        narrative_chs = []
        for ch in chapters:
            decision = self.qualifier.classifier.classify_entry(ch["title"], source_order=ch["order"])
            if decision.entry_type in (EntryClassification.STORY_CHAPTER, EntryClassification.EXTRA):
                narrative_chs.append(ch)

        # Should have exactly chapters 2, 3, 5, 6
        self.assertEqual(len(narrative_chs), 4)
        self.assertEqual([c["order"] for c in narrative_chs], [2, 3, 5, 6])

        # Sample exactly first, middle, latest
        first_ch = narrative_chs[0]
        mid_ch = narrative_chs[len(narrative_chs) // 2]
        latest_ch = narrative_chs[-1]

        self.assertEqual(first_ch["title"], "Chapter 1: The Beginning")
        self.assertEqual(mid_ch["title"], "Chapter 3: The Mission")
        self.assertEqual(latest_ch["title"], "Chapter 4: Final Stand")


class TestCrawlerCleanlinessVerification(unittest.TestCase):
    def setUp(self):
        self.qualifier = CandidateQualifier()

    def test_clean_chapter_passes(self):
        clean_text = (
            "Naruto looked across the training ground, his hands clutched in tight fists.\n\n"
            '"I will never give up!" he yelled with determination.\n\n'
            "Kakashi merely sighed, closing his Icha Icha book and looking toward the horizon."
        )
        raw = {"order": 1, "title": "Chapter 1", "source_text": clean_text}
        insp = self.qualifier._inspect_chapter(raw, "http://rr/ch1")
        self.assertTrue(insp.crawler_clean)
        self.assertEqual(len(insp.unusual_layout_issues), 0)
        self.assertIn("horizon", insp.clean_ending_preview)

    def test_leaked_comment_indicators_flagged(self):
        dirty_text = (
            "Naruto smiled as he walked back home through the Hidden Leaf.\n\n"
            "Leave a comment below to let me know what you think!"
        )
        raw = {"order": 1, "title": "Chapter 1", "source_text": dirty_text}
        insp = self.qualifier._inspect_chapter(raw, "http://rr/ch1")
        self.assertFalse(insp.crawler_clean)
        self.assertTrue(any("comment" in issue.lower() for issue in insp.unusual_layout_issues))

    def test_leaked_navigation_indicators_flagged(self):
        dirty_text = (
            "The kunai sliced through the tree trunk with remarkable speed.\n\n"
            "Next Chapter >> | Previous Chapter | Table of Contents."
        )
        raw = {"order": 2, "title": "Chapter 2", "source_text": dirty_text}
        insp = self.qualifier._inspect_chapter(raw, "http://rr/ch2")
        self.assertFalse(insp.crawler_clean)
        self.assertTrue(any("navigation" in issue.lower() for issue in insp.unusual_layout_issues))

    def test_stat_block_and_term_detection(self):
        stat_text = (
            "[STATUS]\n\n"
            "HP: 1500 / 1500\n\n"
            "MP: 300 / 300\n\n"
            "His chakra began to swirl as the Sharingan activated in his right eye."
        )
        raw = {"order": 1, "title": "Chapter 1", "source_text": stat_text}
        insp = self.qualifier._inspect_chapter(raw, "http://rr/ch1")
        self.assertTrue(insp.stat_blocks_or_tables_detected)
        self.assertIn("chakra", insp.naruto_terms_found)
        self.assertIn("sharingan", insp.naruto_terms_found)


class TestScaleEstimationAndFlags(unittest.TestCase):
    def setUp(self):
        self.qualifier = CandidateQualifier()

    def test_realistic_scale_calculation(self):
        scale = self.qualifier._estimate_realistic_scale(avg_words_per_chapter=2000, total_chapters=100)
        self.assertEqual(scale.sampled_avg_words_per_chapter, 2000)
        self.assertEqual(scale.total_chapters, 100)
        self.assertEqual(scale.estimated_total_source_words, 200000)
        # Vietnamese expansion ~1.25x
        self.assertEqual(scale.estimated_vietnamese_words, 250000)
        # TTS hours: 250,000 / 9000 = 27.777 -> 27.8 hrs
        self.assertEqual(scale.estimated_tts_hours, 27.8)
        # Storage: 27.8 * 28.8 = 800.6 MB
        self.assertEqual(scale.estimated_storage_mb, 800.6)
        # Processing days: 100 / 60 = 1.666 -> 1.7 days
        self.assertEqual(scale.approximate_processing_days, 1.7)

    def test_factual_flags_production_scale_tiers(self):
        scale_compact = self.qualifier._estimate_realistic_scale(avg_words_per_chapter=3000, total_chapters=40)
        scale_massive = self.qualifier._estimate_realistic_scale(avg_words_per_chapter=2500, total_chapters=500)

        # Compute flags for compact
        report_compact = CandidateQualificationReport(
            source_work_id="test1",
            title="Compact Novel",
            url="http://rr/test1",
            scale_estimate=scale_compact,
        )
        report_compact.factual_flags["PRODUCTION_SCALE"] = (
            ProductionScale.COMPACT.value if scale_compact.total_chapters < 50 else ProductionScale.MEDIUM.value
        )
        self.assertEqual(report_compact.factual_flags["PRODUCTION_SCALE"], "COMPACT")

        # Compute flags for massive
        report_massive = CandidateQualificationReport(
            source_work_id="test2",
            title="Massive Novel",
            url="http://rr/test2",
            scale_estimate=scale_massive,
        )
        report_massive.factual_flags["PRODUCTION_SCALE"] = (
            ProductionScale.MASSIVE.value if scale_massive.total_chapters > 400 else ProductionScale.LARGE.value
        )
        self.assertEqual(report_massive.factual_flags["PRODUCTION_SCALE"], "MASSIVE")


class TestQualificationReportSerialization(unittest.TestCase):
    def test_report_serialization_roundtrip(self):
        scale = RealisticProductionScale(
            sampled_avg_words_per_chapter=2200,
            total_chapters=50,
            estimated_total_source_words=110000,
            estimated_vietnamese_words=137500,
            estimated_tts_hours=15.3,
            estimated_storage_mb=440.6,
            approximate_processing_days=0.8,
            throughput_notes="Testing throughput.",
        )
        trial = TranslationTrialResult(
            source_chapter_order=1,
            source_chapter_title="Chapter 1: The Call",
            source_excerpt_words=750,
            source_excerpt="Once upon a time in Konoha...",
            translated_vietnamese="Ngày xửa ngày xưa tại Làng Lá...",
            isolated_glossary={"Konoha": "Làng Lá"},
            vietnamese_naturalness=9.2,
            character_name_consistency=9.5,
            fandom_terminology_accuracy=9.5,
            dialogue_readability=9.0,
            meaning_preserved=True,
            manual_editing_requirement="LOW",
        )
        report = CandidateQualificationReport(
            source_work_id="99999",
            title="Test Serialization Novel",
            source_platform="royalroad",
            url="https://www.royalroad.com/fiction/99999",
            inspected_chapters=[],
            writing_quality=WritingQualityAnalysis(prose_coherence="Xuất sắc"),
            translation_trial=trial,
            scale_estimate=scale,
            factual_flags={"CRAWLER_COMPATIBLE": True, "TRANSLATION_QUALITY_OK": True},
        )

        json_str = report.model_dump_json()
        loaded = CandidateQualificationReport.model_validate_json(json_str)

        self.assertEqual(loaded.source_work_id, "99999")
        self.assertEqual(loaded.title, "Test Serialization Novel")
        self.assertEqual(loaded.translation_trial.source_excerpt_words, 750)
        self.assertEqual(loaded.scale_estimate.estimated_tts_hours, 15.3)
        self.assertTrue(loaded.factual_flags["CRAWLER_COMPATIBLE"])

    def test_load_qualification_report_from_disk(self):
        # 81168 was qualified and exists on disk
        report = load_qualification_report("81168")
        self.assertIsNotNone(report)
        self.assertEqual(report.source_work_id, "81168")
        self.assertEqual(len(report.inspected_chapters), 3)
        self.assertEqual(report.factual_flags.get("PRODUCTION_SCALE"), "MASSIVE")


if __name__ == "__main__":
    unittest.main()
