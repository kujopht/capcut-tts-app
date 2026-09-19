"""
Unit and integration tests for External Content Import Contract v1.
"""

from __future__ import annotations

import unittest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from server.adapters import MockMetadataStore, MockMediaAssetStore
from server.domain import Fandom, FandomMediaType
from server.external_import_contract import (
    ContentType,
    ExternalAudio,
    ExternalChapter,
    ExternalCover,
    ExternalWorkImport,
    WorkStatus,
    canonicalize_url,
    clean_reader_tags,
    compute_work_fingerprint,
    is_internal_tag,
)
from server.external_import_service import ExternalImportService
from server.fandom_registry import FandomRegistry
from server.main import app


class TestExternalImportContract(unittest.TestCase):

    def setUp(self):
        self.store = MockMetadataStore()
        self.storage = MockMediaAssetStore()
        self.fandom_reg = FandomRegistry(seed=True)
        self.service = ExternalImportService(
            store=self.store,
            storage=self.storage,
            fandom_reg=self.fandom_reg,
            default_owner_id="test_importer"
        )

    def test_canonicalize_url(self):
        url1 = "https://example.com/books/123/?utm_source=fb&utm_medium=cpc#reviews"
        url2 = "http://example.com/books/123?fbclid=xyz"
        canon1 = canonicalize_url(url1)
        canon2 = canonicalize_url(url2)
        self.assertEqual(canon1, "https://example.com/books/123")
        self.assertEqual(canon2, "http://example.com/books/123")

    def test_clean_reader_tags(self):
        raw_tags = [
            "Hành động",
            "work:internal_123",
            "imported",
            "long_form_audio",
            "unresolved_tag",
            "Phiêu lưu",
            "Hành động"  # duplicate
        ]
        clean, rejected = clean_reader_tags(raw_tags)
        self.assertEqual(clean, ["Hành động", "Phiêu lưu"])
        self.assertIn("work:internal_123", rejected)
        self.assertIn("imported", rejected)
        self.assertIn("long_form_audio", rejected)
        self.assertIn("unresolved_tag", rejected)

    def test_deterministic_fingerprint(self):
        fp1 = compute_work_fingerprint(
            content_type="book",
            title="Đắc Nhân Tâm",
            author="Dale Carnegie",
            source_url="https://example.com/dac-nhan-tam?utm_source=twitter"
        )
        fp2 = compute_work_fingerprint(
            content_type="book",
            title="Đắc Nhân Tâm",
            author="Dale Carnegie",
            source_url="https://example.com/dac-nhan-tam?utm_campaign=summer"
        )
        self.assertEqual(fp1, fp2)

    def test_validation_rejects_empty_chapters(self):
        with self.assertRaises(ValidationError) as ctx:
            ExternalWorkImport(
                title="Sách Rỗng",
                chapters=[]
            )
        err = str(ctx.exception)
        self.assertTrue("at least 1" in err or "too_short" in err)

    def test_validation_rejects_empty_title(self):
        with self.assertRaises(ValidationError):
            ExternalWorkImport(
                title="   ",
                chapters=[ExternalChapter(order=1, title="Chương 1", content="Nội dung dài hơn 10 ký tự")]
            )

    def test_validation_rejects_short_content(self):
        with self.assertRaises(ValidationError):
            ExternalChapter(order=1, title="Chương 1", content="ngắn")

    def test_fanfic_validation_and_fandom_resolution(self):
        payload = ExternalWorkImport(
            content_type=ContentType.FANFIC,
            title="Naruto Truyền Kỳ",
            author="AuthorA",
            fandom="Naruto",
            tags=["Ninja", "work:task_1"],
            chapters=[
                ExternalChapter(order=1, title="Mở đầu", content="Đây là nội dung chương một rất hay và dài.")
            ]
        )
        self.assertEqual(payload.content_type, ContentType.FANFIC)
        self.assertIn("Fanfic", payload.tags)
        self.assertIn("Ninja", payload.tags)
        self.assertNotIn("work:task_1", payload.tags)
        self.assertIn("Naruto", payload.fandoms)

        preview = self.service.preview(payload)
        self.assertTrue(preview.valid)
        self.assertFalse(preview.is_duplicate)
        self.assertEqual(preview.action, "create")
        self.assertEqual(preview.new_chapters_count, 1)
        self.assertTrue(len(preview.resolved_fandom_ids) > 0)

    def test_book_import_flow(self):
        payload = ExternalWorkImport(
            content_type=ContentType.BOOK,
            title="Lược Sử Thời Gian",
            author="Stephen Hawking",
            tags=["Khoa học", "Vũ trụ"],
            chapters=[
                ExternalChapter(order=1, title="Chương 1: Bức tranh về vũ trụ", content="Con người từ lâu đã ngước nhìn bầu trời sao để tìm hiểu nguồn gốc thế giới."),
                ExternalChapter(order=2, title="Chương 2: Không gian và thời gian", content="Khái niệm về không gian và thời gian đã thay đổi hoàn toàn sau thuyết tương đối.")
            ]
        )
        self.assertIn("Sách", payload.tags)
        self.assertEqual(len(payload.chapters), 2)

        # 1. Preview
        prev = self.service.preview(payload)
        self.assertEqual(prev.action, "create")
        self.assertEqual(prev.total_chapters, 2)
        # Store should have 0 novels still
        self.assertEqual(len(self.store.list_novels()), 0)

        # 2. Execute
        res = self.service.execute(payload, owner_id="test_user")
        self.assertTrue(res.success)
        self.assertEqual(res.chapters_created, 2)

        # Store now has novel and 2 chapters
        novel = self.store.get_novel(res.novel_id)
        self.assertIsNotNone(novel)
        self.assertEqual(novel.title, "Lược Sử Thời Gian")
        self.assertEqual(novel.external_author_name, "Stephen Hawking")
        chps = self.store.list_chapters(res.novel_id)
        self.assertEqual(len(chps), 2)
        self.assertEqual(chps[0].order_index, 1)
        self.assertEqual(chps[1].order_index, 2)

    def test_idempotent_resume_and_chapter_append(self):
        payload_v1 = ExternalWorkImport(
            content_type=ContentType.NOVEL,
            source_url="https://novels.example.com/n/100",
            title="Đại Lục Huyền Bí",
            author="Tác Giả X",
            chapters=[
                ExternalChapter(order=1, title="Chương 1", content="Nội dung chương 1 trên đại lục huyền bí."),
                ExternalChapter(order=2, title="Chương 2", content="Nội dung chương 2 trên đại lục huyền bí.")
            ]
        )
        # First import
        res1 = self.service.execute(payload_v1, owner_id="test_user")
        self.assertEqual(res1.chapters_created, 2)
        self.assertEqual(res1.chapters_skipped, 0)

        # Second import with SAME chapters (should skip all without duplicating)
        res2 = self.service.execute(payload_v1, owner_id="test_user")
        self.assertEqual(res2.chapters_created, 0)
        self.assertEqual(res2.chapters_skipped, 2)
        self.assertEqual(len(self.store.list_chapters(res1.novel_id)), 2)

        # Third import with NEW Chapter 3 (should append chapter 3 only)
        payload_v2 = ExternalWorkImport(
            content_type=ContentType.NOVEL,
            source_url="https://novels.example.com/n/100",
            title="Đại Lục Huyền Bí",
            author="Tác Giả X",
            chapters=[
                ExternalChapter(order=1, title="Chương 1", content="Nội dung chương 1 trên đại lục huyền bí."),
                ExternalChapter(order=2, title="Chương 2", content="Nội dung chương 2 trên đại lục huyền bí."),
                ExternalChapter(order=3, title="Chương 3", content="Nội dung chương 3 hoàn toàn mới xuất hiện.")
            ]
        )
        prev_v2 = self.service.preview(payload_v2)
        self.assertTrue(prev_v2.is_duplicate)
        self.assertEqual(prev_v2.action, "resume_append")
        self.assertEqual(prev_v2.new_chapters_count, 1)
        self.assertEqual(prev_v2.existing_chapters_count, 2)

        res3 = self.service.execute(payload_v2, owner_id="test_user")
        self.assertEqual(res3.chapters_created, 1)
        self.assertEqual(res3.chapters_skipped, 2)
        self.assertEqual(len(self.store.list_chapters(res1.novel_id)), 3)

    def test_audio_track_attachment(self):
        payload = ExternalWorkImport(
            content_type=ContentType.BOOK,
            title="Sách Nói Mẫu",
            chapters=[
                ExternalChapter(
                    order=1,
                    title="Chương 1 Có Audio",
                    content="Nội dung chương có đính kèm file âm thanh phát thanh viên.",
                    audio=ExternalAudio(
                        url="https://audio.example.com/ch1.mp3",
                        duration_seconds=125.0,
                        size_bytes=1000000,
                        voice_name="VoiceSpeaker"
                    )
                )
            ]
        )
        res = self.service.execute(payload, owner_id="test_user")
        self.assertEqual(res.audio_tracks_created, 1)
        ch_id = res.chapters[0]["chapter_id"]
        track = self.store.track_for_chapter(ch_id)
        self.assertIsNotNone(track)
        self.assertEqual(track.duration_seconds, 125.0)
        self.assertEqual(track.voice_id, "VoiceSpeaker")


class TestExternalImportApi(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_api_validate_endpoint(self):
        valid_payload = {
            "content_type": "fanfic",
            "title": "One Piece: Đảo Trời Khác",
            "author": "OdaFan",
            "fandom": "One Piece",
            "tags": ["Hải tặc", "work:debug_12"],
            "chapters": [
                {"order": 1, "title": "Chương 1", "content": "Tàu Going Merry bay lên những đám mây trắng."}
            ]
        }
        res = self.client.post("/api/external-import/validate", json=valid_payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["valid"])
        self.assertIn("Hải tặc", data["sanitized_tags"])
        self.assertIn("work:debug_12", data["rejected_technical_tags"])

    def test_api_validate_endpoint_rejects_empty(self):
        invalid_payload = {
            "title": "",
            "chapters": []
        }
        res = self.client.post("/api/external-import/validate", json=invalid_payload)
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
