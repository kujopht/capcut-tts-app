"""
Test phan trang, bo loc, sap xep va quy mo lon (synthetic scale 300+ ban ghi)
cho he thong Novel Catalog.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import List

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.domain import Novel, NovelStatus, PublishState


class TestNovelPaginationAndFiltering(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        self.store = MockMetadataStore()
        server_main.store = self.store
        self._real_storage = server_main.storage
        server_main.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.storage = self._real_storage

    def test_synthetic_scale_300_records_pagination_and_sorting(self):
        """Kiem thu quy mo tong hop 300+ ban ghi truyen."""
        fandom_list = ["fan_naruto", "fan_onepiece", "fan_conan", "fan_genshin"]
        statuses = [NovelStatus.ONGOING, NovelStatus.COMPLETED, NovelStatus.HIATUS]

        novels: List[Novel] = []
        for i in range(300):
            fid = fandom_list[i % len(fandom_list)]
            st = statuses[i % len(statuses)]
            has_audio_tag = ["long_form_audio"] if (i % 3 == 0) else []
            novel = Novel(
                owner_id="owner_synthetic",
                title=f"Novel Synthetic {i:03d} Title",
                description=f"Description for novel {i}",
                tags=["synthetic"] + has_audio_tag,
                novel_id=f"nov_synth_{i:04d}",
                state=PublishState.PUBLISHED,
                fandom_ids=[fid],
                status=st,
                external_chapter_count=(i * 7) % 150,
                created_at=f"2026-08-{(i % 28) + 1:02d}T10:00:00Z",
                updated_at=f"2026-09-{(i % 28) + 1:02d}T12:00:00Z",
            )
            self.store.novels[novel.novel_id] = novel
            novels.append(novel)

        # 1. Total count: default public catalog hides legacy audio-only (200 readable)
        res_default = self.client.get("/api/novels", params={"limit": 12, "offset": 0}).json()
        self.assertEqual(res_default["total"], 200)
        self.assertEqual(res_default["count"], 12)

        # Total count with content_mode="all" (300 records)
        res = self.client.get("/api/novels", params={"limit": 12, "offset": 0, "content_mode": "all"}).json()
        self.assertEqual(res["total"], 300)
        self.assertEqual(res["count"], 12)
        self.assertEqual(res["limit"], 12)
        self.assertTrue(res["has_more"])
        self.assertIsNotNone(res["next_cursor"])

        # 2. Iterate through all pages using offset pagination (content_mode="all")
        seen_offset: List[str] = []
        offset = 0
        limit = 25
        while True:
            r = self.client.get("/api/novels", params={"limit": limit, "offset": offset, "content_mode": "all"}).json()
            ids = [n["novel_id"] for n in r["novels"]]
            seen_offset.extend(ids)
            if not r["has_more"]:
                break
            offset += limit
        self.assertEqual(len(seen_offset), 300)
        self.assertEqual(len(set(seen_offset)), 300, "Offset pagination must not duplicate items")

        # 3. Iterate through all pages using cursor pagination (content_mode="all")
        seen_cursor: List[str] = []
        cursor = None
        while True:
            params = {"limit": limit, "content_mode": "all"}
            if cursor:
                params["cursor"] = cursor
            r = self.client.get("/api/novels", params=params).json()
            ids = [n["novel_id"] for n in r["novels"]]
            seen_cursor.extend(ids)
            if not r["has_more"] or not r.get("next_cursor"):
                break
            cursor = r["next_cursor"]
        self.assertEqual(len(seen_cursor), 300)
        self.assertEqual(len(set(seen_cursor)), 300, "Cursor pagination must not duplicate items")
        self.assertEqual(seen_offset, seen_cursor, "Offset and cursor ordering must match")

        # 4. Filter by fandom (content_mode="all")
        r_naruto = self.client.get("/api/novels", params={"fandom": "fan_naruto", "limit": 100, "content_mode": "all"}).json()
        self.assertEqual(r_naruto["total"], 75)
        for n in r_naruto["novels"]:
            self.assertIn("fan_naruto", n["fandom_ids"])

        # 5. Filter by status (content_mode="all")
        r_ongoing = self.client.get("/api/novels", params={"status": "ongoing", "limit": 100, "content_mode": "all"}).json()
        self.assertEqual(r_ongoing["total"], 100)
        for n in r_ongoing["novels"]:
            self.assertEqual(n["status"], "ongoing")

        # 6. Filter by audio (content_mode="all")
        r_audio = self.client.get("/api/novels", params={"audio": "true", "limit": 100, "content_mode": "all"}).json()
        self.assertEqual(r_audio["total"], 100)
        for n in r_audio["novels"]:
            self.assertTrue(n["has_audio"])

        r_text = self.client.get("/api/novels", params={"audio": "false", "limit": 100, "content_mode": "all"}).json()
        self.assertEqual(r_text["total"], 200)
        for n in r_text["novels"]:
            self.assertFalse(n["has_audio"])

        # 7. Sort by title (content_mode="all")
        r_title = self.client.get("/api/novels", params={"sort": "title", "limit": 5, "content_mode": "all"}).json()
        titles = [n["title"] for n in r_title["novels"]]
        self.assertEqual(titles, sorted(titles))

        # 8. Sort by chapters (content_mode="all")
        r_chp = self.client.get("/api/novels", params={"sort": "chapters", "limit": 5, "content_mode": "all"}).json()
        counts = [n["external_chapter_count"] for n in r_chp["novels"]]
        self.assertEqual(counts, sorted(counts, reverse=True))

        # 9. Hard maximum limit capping
        r_max = self.client.get("/api/novels", params={"limit": 500}).json()
        self.assertLessEqual(r_max["limit"], server_main.MAX_PAGE_SIZE)
        self.assertEqual(r_max["count"], server_main.MAX_PAGE_SIZE)

        # 10. Filter by content_mode="readable"
        r_readable = self.client.get("/api/novels", params={"content_mode": "readable", "limit": 100}).json()
        self.assertEqual(r_readable["total"], 200)
        for n in r_readable["novels"]:
            self.assertEqual(n["content_mode"], "readable")

        # 11. Filter by content_mode="audio_only"
        r_audio_only = self.client.get("/api/novels", params={"content_mode": "audio_only", "limit": 100}).json()
        self.assertEqual(r_audio_only["total"], 100)
        for n in r_audio_only["novels"]:
            self.assertEqual(n["content_mode"], "audio_only")
