"""
Tests for the Bilibili adapter (V5) — Story Harvester.
"""
from __future__ import annotations

import unittest

from server.scraper.http_fetcher import FetchError, FixtureFetcher
from server.scraper.universal.acquisition import (
    AcquisitionMethod, AcquisitionStatus,
)
from server.scraper.universal.adapters_v5.bilibili_adapter import BilibiliAdapter

BV_ID = "BV1xx411c7mD"
VIDEO_URL = f"https://www.bilibili.com/video/{BV_ID}"
API_URL = f"https://api.bilibili.com/x/web-interface/view?bvid={BV_ID}"

VIEW_JSON = """{"code": 0, "message": "0", "data": {
    "bvid": "BV1xx411c7mD", "aid": 123456, "title": "Video Title",
    "desc": "Video description text", "duration": 300,
    "pic": "http://i0.hdslb.com/bfs/archive/example.jpg",
    "pubdate": 1600000000,
    "owner": {"mid": 12345, "name": "UploaderName"},
    "stat": {"view": 10000, "danmaku": 50, "reply": 20,
             "favorite": 100, "coin": 30, "share": 10, "like": 500}
}}"""

ERROR_JSON = '{"code": -404, "message": "啥都木有", "data": null}'


class BilibiliAdapterTest(unittest.TestCase):
    def setUp(self):
        self.fetcher = FixtureFetcher({
            API_URL: VIEW_JSON,
            "https://api.bilibili.com/x/web-interface/view?bvid=BVmissing": ERROR_JSON,
        })
        self.adapter = BilibiliAdapter(self.fetcher)

    def test_bvid_extraction(self):
        self.assertEqual(
            self.adapter._extract_bvid("https://www.bilibili.com/video/BV1xx411c7mD"),
            BV_ID)

    def test_canonicalize(self):
        self.assertEqual(self.adapter.canonicalize(VIDEO_URL), VIDEO_URL)

    def test_probe_true_for_video_url(self):
        self.assertTrue(self.adapter.probe(VIDEO_URL))

    def test_probe_false_for_non_video_url(self):
        self.assertFalse(self.adapter.probe("https://www.bilibili.com/"))
        self.assertFalse(self.adapter.probe("https://example.com/video/BV1xx411c7mD"))

    def test_canonicalize_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.adapter.canonicalize("https://www.bilibili.com/")

    def test_full_round_trip(self):
        acquire = self.adapter.fetch_unit(VIDEO_URL)
        self.assertEqual(acquire.status, AcquisitionStatus.OK)
        self.assertEqual(acquire.acquisition_method, AcquisitionMethod.STRUCTURED_API)
        self.assertEqual(acquire.source_type.value, "video_platform")
        self.assertEqual(acquire.structured_json["title"], "Video Title")
        self.assertEqual(acquire.structured_json["owner"]["name"], "UploaderName")

        video = self.adapter.normalize(VIDEO_URL, acquire)
        self.assertEqual(video.platform, "bilibili")
        self.assertEqual(video.video_id, BV_ID)
        self.assertEqual(video.channel_id, "12345")
        self.assertEqual(video.title, "Video Title")
        self.assertEqual(video.description, "Video description text")
        self.assertEqual(video.duration_seconds, 300)
        self.assertEqual(video.thumbnail_url, "http://i0.hdslb.com/bfs/archive/example.jpg")
        self.assertEqual(video.canonical_url, VIDEO_URL)
        self.assertIsNotNone(video.evidence)
        self.assertEqual(video.evidence.provenance, "bilibili_view_api")

        key = self.adapter.stable_identity(video)
        self.assertTrue(isinstance(key, str) and key)

    def test_extract_metadata(self):
        meta = self.adapter.extract_metadata(VIDEO_URL)
        self.assertEqual(meta["title"], "Video Title")
        self.assertEqual(meta["description"], "Video description text")
        self.assertEqual(meta["duration_seconds"], 300)
        self.assertEqual(meta["thumbnail_url"], "http://i0.hdslb.com/bfs/archive/example.jpg")
        self.assertEqual(meta["uploader_name"], "UploaderName")
        self.assertEqual(meta["uploader_id"], "12345")
        self.assertEqual(meta["view_count"], 10000)

    def test_list_units_single_video(self):
        self.assertEqual(self.adapter.list_units(VIDEO_URL), [VIDEO_URL])

    def test_api_error_code_is_failed_not_ok(self):
        missing_url = "https://www.bilibili.com/video/BVmissing"
        acquire = self.adapter.fetch_unit(missing_url)
        self.assertEqual(acquire.status, AcquisitionStatus.FAILED)
        self.assertTrue(acquire.errors)

    def test_missing_fixture_resolves_to_failed_without_raising(self):
        missing_url = "https://www.bilibili.com/video/BVunknown12345"
        acquire = self.adapter.fetch_unit(missing_url)
        self.assertEqual(acquire.status, AcquisitionStatus.FAILED)
        self.assertTrue(acquire.errors)

    def test_capabilities(self):
        caps = self.adapter.capabilities()
        self.assertIn("video_platform",
                      {c.value for c in caps.source_classes})
        self.assertFalse(caps.requires_browser)


if __name__ == "__main__":
    unittest.main()
