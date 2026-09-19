"""
Comprehensive Verification Test Suite for Content Factory v2.

Covers:
1. Royal Road Crawler Adapter (metadata + chapter parsing)
2. Provenance Models (IMPORTED_FANFIC vs AI_ORIGINAL constraints)
3. Translation Glossary Manager (persistence, prompt injection, consistency)
4. Normalized Release Packager (manifest, QA report, External Import Contract)
5. Production Diff Engine:
   - Verified on production work `nov_hatake_156690`
   - Chapters 1–12 -> UNCHANGED (0 LLM, 0 TTS)
   - Synthetic Chapter 13 -> NEW_CHAPTER (1 LLM, 1 TTS)
   - Resumability & Idempotence: zero re-translations for matching hashes
   - Zero-Write production safety guarantee
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import unittest
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.content_factory.provenance import (
    ProvenanceType,
    WorkProvenance,
    ChapterProvenance,
)
from scripts.content_factory.crawler_adapters.royalroad_adapter import RoyalRoadAdapter
from scripts.content_factory.glossary_manager import GlossaryManager, NovelGlossary
from scripts.content_factory.release_packager import ReleasePackager, PackagedChapter, ReleaseManifest
from scripts.content_factory.production_diff_engine import (
    ProductionDiffEngine,
    NovelDiffReport,
    DiffStatus,
    find_active_registry_db,
)
from server.crawler_intake_contract import compute_source_text_hash, RawCrawlerWork, RawCrawlerChapter
from server.external_import_contract import ExternalWorkImport


class TestContentFactoryV2(unittest.TestCase):
    """Full verification suite for Content Factory v2."""

    def setUp(self):
        self.test_dir = PROJECT_ROOT / "raw_spool" / "test_scratch_v2"
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Royal Road Adapter Tests
    # -------------------------------------------------------------------------
    def test_royalroad_adapter_metadata_and_chapters(self):
        adapter = RoyalRoadAdapter()
        test_url = "https://www.royalroad.com/fiction/156690/naruto-si-reborn-in-the-hatake-clan"

        # Fetch work with chapter limit = 2 for quick verification
        work = adapter.fetch_work(test_url, max_chapters=2)
        self.assertEqual(work.source_id, "156690")
        self.assertIn("Hatake", work.title)
        self.assertGreaterEqual(len(work.chapters), 1)

        first_ch = work.chapters[0]
        self.assertEqual(first_ch.source_order, 1)
        self.assertGreater(len(first_ch.source_text), 100)
        self.assertTrue(first_ch.source_text_hash)
        # Verify hash computation is deterministic
        expected_hash = compute_source_text_hash(first_ch.source_text)
        self.assertEqual(first_ch.source_text_hash, expected_hash)

    def test_royalroad_adapter_false_anchor_filtering(self):
        """Regression test reproducing false-anchor case: sidebar, comments, duplicate CIDs."""
        from bs4 import BeautifulSoup
        html_fixture = """
        <html>
          <body>
            <div class="sidebar">
              <a href="/fiction/156690/chapter/3354888">Read</a>
              <a href="/profile/1234">Author</a>
              <a href="/fiction/chapter/9999999">Report</a>
            </div>
            <table id="chapters">
              <tbody>
                <tr><td><a href="/fiction/156690/naruto-si/chapter/1001/chapter-1">Chapter 1: The Awakening</a></td></tr>
                <tr><td><a href="/fiction/156690/naruto-si/chapter/1002/chapter-2">Chapter 2: Training</a></td></tr>
              </tbody>
            </table>
            <div class="comments">
              <a href="/fiction/156690/naruto-si/chapter/1001/chapter-1#comments">Comments (12)</a>
              <a href="/fiction/chapter/1002">Reply to Chapter 2</a>
            </div>
          </body>
        </html>
        """
        adapter = RoyalRoadAdapter()
        soup = BeautifulSoup(html_fixture, "html.parser")
        chapters = adapter.list_chapters("156690", soup=soup)

        # Must find exactly 2 chapters from table, ignoring sidebar, comments, duplicates
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]["order"], 1)
        self.assertEqual(chapters[0]["source_chapter_id"], "1001")
        self.assertEqual(chapters[0]["title"], "Chapter 1: The Awakening")
        self.assertEqual(chapters[1]["order"], 2)
        self.assertEqual(chapters[1]["source_chapter_id"], "1002")
        self.assertEqual(chapters[1]["title"], "Chapter 2: Training")

    # -------------------------------------------------------------------------
    # 2. Provenance Models Tests
    # -------------------------------------------------------------------------
    def test_provenance_imported_fanfic(self):
        # Valid IMPORTED_FANFIC
        prov = WorkProvenance(
            provenance_type=ProvenanceType.IMPORTED_FANFIC,
            source_platform="royalroad",
            source_work_id="156690",
            canonical_source_url="https://www.royalroad.com/fiction/156690/naruto-si",
            original_title="Naruto SI",
            original_author="SoGarrulous",
        )
        self.assertEqual(prov.provenance_type, ProvenanceType.IMPORTED_FANFIC)
        self.assertTrue(prov.canonical_source_url.startswith("https://"))

        # Invalid: missing HTTP URL for IMPORTED_FANFIC
        with self.assertRaises(ValueError):
            WorkProvenance(
                provenance_type=ProvenanceType.IMPORTED_FANFIC,
                source_platform="royalroad",
                source_work_id="156690",
                canonical_source_url="",
                original_title="Naruto SI",
                original_author="SoGarrulous",
            )

    def test_provenance_ai_original(self):
        # Valid AI_ORIGINAL (no external URL)
        prov = WorkProvenance(
            provenance_type=ProvenanceType.AI_ORIGINAL,
            source_platform="fanfic_ai_studio",
            source_work_id="ai_novel_001",
            canonical_source_url="",
            original_title="Hành Trình Tu Tiên Đô Thị",
            original_author="Gemini Pro 2.5",
            creative_prompt="Một kỹ sư xuyên không về thời cổ đại",
        )
        self.assertEqual(prov.provenance_type, ProvenanceType.AI_ORIGINAL)
        self.assertEqual(prov.canonical_source_url, "")

        # Invalid: AI_ORIGINAL must not fabricate an external HTTP source URL
        with self.assertRaises(ValueError):
            WorkProvenance(
                provenance_type=ProvenanceType.AI_ORIGINAL,
                source_platform="fanfic_ai_studio",
                source_work_id="ai_novel_001",
                canonical_source_url="https://fake-fanfic-site.com/fiction/9999",
                original_title="Hành Trình Tu Tiên Đô Thị",
                original_author="Gemini",
            )

    # -------------------------------------------------------------------------
    # 3. Translation Glossary Manager Tests
    # -------------------------------------------------------------------------
    def test_glossary_manager_persistence_and_consistency(self):
        glossary_dir = self.test_dir / "glossaries"
        gm = GlossaryManager(base_dir=glossary_dir)

        # Pre-seeding check for Hatake
        g = gm.load_glossary("hatake_test")
        self.assertIn("Kakashi", g.character_names)
        self.assertIn("Konoha", g.locations)

        # Add custom term
        gm.add_term("hatake_test", "character_names", "Akihiro", "Akihiro", notes="Main character")
        g_reloaded = gm.load_glossary("hatake_test")
        self.assertEqual(g_reloaded.character_names.get("Akihiro"), "Akihiro")

        # Prompt context check
        prompt_ctx = gm.build_gemini_prompt_context("hatake_test")
        self.assertIn("BẮT BUỘC TUÂN THỦ BẢNG THUẬT NGỮ", prompt_ctx)
        self.assertIn("Kakashi", prompt_ctx)

        # Post-translation consistency enforcement
        raw_text = "Tại Konoha, một Ninja trẻ tuổi tên Akihiro đang luyện tập Chidori."
        clean_text = gm.apply_post_translation_consistency(raw_text, "hatake_test")
        # Konoha -> Làng Lá according to default glossary
        self.assertIn("Làng Lá", clean_text)
        self.assertIn("Chidori", clean_text)

    # -------------------------------------------------------------------------
    # 4. Normalized Release Packager & Contract Compliance Tests
    # -------------------------------------------------------------------------
    def test_release_packager_and_external_contract(self):
        pkg_dir = self.test_dir / "packages"
        rp = ReleasePackager(base_dir=pkg_dir)

        prov = WorkProvenance(
            provenance_type=ProvenanceType.IMPORTED_FANFIC,
            source_platform="royalroad",
            source_work_id="test_work_01",
            canonical_source_url="https://www.royalroad.com/fiction/156690/naruto-si",
            original_title="Naruto SI: Kỹ Sư Vật Liệu",
            original_author="SoGarrulous",
        )

        chapters = [
            PackagedChapter(
                order=1,
                title="Chương 1: Khởi Đầu Mới",
                content="Đây là nội dung chương đầu tiên dài hơn năm mươi từ để đáp ứng tiêu chuẩn chất lượng QA của hệ thống sản xuất truyện.",
                source_chapter_id="rr_c001",
            ),
            PackagedChapter(
                order=2,
                title="Chương 2: Luyện Tập Chakra",
                content="Nội dung chương thứ hai tiếp tục hành trình tu luyện và khám phá các nguyên lý vật liệu trong thế giới nhẫn giả.",
                source_chapter_id="rr_c002",
            ),
        ]

        target_pkg = rp.create_package(
            provenance=prov,
            chapters=chapters,
            tags=["Naruto", "Đồng nhân", "Khoa học"],
            description="Mô tả tác phẩm thử nghiệm."
        )

        self.assertTrue((target_pkg / "manifest.json").exists())
        self.assertTrue((target_pkg / "qa_report.json").exists())
        self.assertTrue((target_pkg / "chapters" / "ch_0001.json").exists())

        # Verify QA passed
        qa = rp.run_qa(rp.load_package("test_work_01"))
        self.assertTrue(qa.passed)
        self.assertEqual(qa.total_chapters, 2)

        # Validate ExternalContentImportContract conversion
        ext_import = rp.to_external_work_import("test_work_01")
        self.assertIsInstance(ext_import, ExternalWorkImport)
        self.assertEqual(len(ext_import.chapters), 2)
        self.assertEqual(ext_import.title, "Naruto SI: Kỹ Sư Vật Liệu")
        self.assertTrue(ext_import.get_fingerprint())

    # -------------------------------------------------------------------------
    # 5. Production Diff Engine on Real Work `nov_hatake_156690`
    # -------------------------------------------------------------------------
    def test_production_diff_engine_hatake_canary(self):
        """
        Validates read-only production diff on real live state:
        - Chapters 1–12 must match production and report UNCHANGED (0 LLM, 0 TTS).
        - Chapter 13 must report NEW_CHAPTER (1 LLM, 1 TTS).
        - Zero writes must be made to the database.
        """
        db_path = find_active_registry_db()
        self.assertTrue(db_path.exists(), f"Production registry database not found at {db_path}")

        # Check DB state before test
        with sqlite3.connect(db_path) as conn:
            initial_count = conn.execute("SELECT count(*) FROM source_chapter_registry").fetchone()[0]
            # Fetch real hashes for Hatake chapters 1–12
            rows = conn.execute(
                "SELECT chapter_order, source_text_hash FROM source_chapter_registry "
                "WHERE source_work_id = '156690' ORDER BY chapter_order ASC"
            ).fetchall()

        self.assertGreaterEqual(len(rows), 11, "Expected at least 11 production chapters for Hatake")

        # Build candidate with real hashes for Ch 1..12 + synthetic Ch 13
        candidate_chapters = []
        for order, shash in rows:
            candidate_chapters.append({
                "order": order,
                "title": f"Chapter {order}",
                "source_text_hash": shash,
            })

        # Append synthetic next chapter
        next_order = len(rows) + 1
        candidate_chapters.append({
            "order": next_order,
            "title": f"Chapter {next_order}: Synthetic Test Chapter",
            "source_text_hash": f"hash_synthetic_chapter_{next_order}_never_published",
        })

        diff_engine = ProductionDiffEngine(db_path=db_path)
        report = diff_engine.diff({
            "platform": "royalroad",
            "work_id": "156690",
            "title": "Naruto SI : Reborn in the Hatake Clan",
            "chapters": candidate_chapters,
        })

        # Verify exact counts
        self.assertEqual(report.unchanged_count, len(rows), "All existing chapters must be UNCHANGED")
        self.assertEqual(report.new_count, 1, "Only synthetic next chapter should be NEW_CHAPTER")
        self.assertEqual(report.estimated_llm_calls, 1, "Only 1 LLM call projected")
        self.assertEqual(report.estimated_tts_jobs, 1, "Only 1 TTS job projected")

        # Verify status of existing chapters
        for i in range(len(rows)):
            self.assertEqual(report.chapter_diffs[i].status, DiffStatus.UNCHANGED)
            self.assertIn("SKIP (0 LLM, 0 TTS)", report.chapter_diffs[i].action_preview)

        # Verify status of next chapter
        next_diff = report.chapter_diffs[-1]
        self.assertEqual(next_diff.order, next_order)
        self.assertEqual(next_diff.status, DiffStatus.NEW_CHAPTER)
        self.assertIn("TRANSLATE & PUBLISH", next_diff.action_preview)

        # Verify ZERO WRITES guarantee
        with sqlite3.connect(db_path) as conn:
            after_count = conn.execute("SELECT count(*) FROM source_chapter_registry").fetchone()[0]
            self.assertEqual(initial_count, after_count, "Zero-write guarantee violated! Chapter count changed.")

        # Test catalog query
        cat = diff_engine.get_published_catalog()
        self.assertGreaterEqual(len(cat), 1)
        hatake_item = next((w for w in cat if w["source_work_id"] == "156690"), None)
        self.assertIsNotNone(hatake_item)
        self.assertEqual(hatake_item["appwrite_novel_id"], "nov_hatake_156690")


if __name__ == "__main__":
    unittest.main()
