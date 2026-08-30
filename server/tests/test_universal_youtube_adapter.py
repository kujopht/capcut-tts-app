import json
import unittest

from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.universal.acquisition import (
    AcquisitionMethod,
    AcquisitionStatus,
    SourceClass,
)
from server.scraper.universal.adapters_v5.youtube_adapter import (
    YouTubeAdapter,
    _extract_youtube_id,
)
from server.scraper.universal.units import Video


class TestUniversalYouTubeAdapter(unittest.TestCase):
    def setUp(self):
        self.sample_oembed = {
            "title": "Sample Video Title",
            "author_name": "Channel Name",
            "author_url": "https://www.youtube.com/@channelhandle",
            "type": "video",
            "height": 113,
            "width": 200,
            "version": "1.0",
            "provider_name": "YouTube",
            "provider_url": "https://www.youtube.com/",
            "thumbnail_height": 360,
            "thumbnail_width": 480,
            "thumbnail_url": "https://i.ytimg.com/vi/VIDEO_ID/hqdefault.jpg",
            "html": "<iframe ...></iframe>",
        }
        self.canonical_watch = "https://www.youtube.com/watch?v=VIDEO_ID"
        self.oembed_url = f"https://www.youtube.com/oembed?url={self.canonical_watch}&format=json"
        self.fetcher = FixtureFetcher({
            self.oembed_url: json.dumps(self.sample_oembed),
        })
        self.adapter = YouTubeAdapter(fetcher=self.fetcher)

    def test_video_id_extraction_all_shapes(self):
        urls = [
            ("https://www.youtube.com/watch?v=VIDEO_ID", "VIDEO_ID"),
            ("https://youtube.com/watch?v=VIDEO_ID&t=10s", "VIDEO_ID"),
            ("https://youtu.be/VIDEO_ID", "VIDEO_ID"),
            ("https://www.youtube.com/embed/VIDEO_ID", "VIDEO_ID"),
            ("https://m.youtube.com/watch?v=VIDEO_ID", "VIDEO_ID"),
        ]
        for url, expected_id in urls:
            with self.subTest(url=url):
                self.assertEqual(_extract_youtube_id(url), expected_id)
                self.assertEqual(self.adapter.canonicalize(url), f"https://www.youtube.com/watch?v={expected_id}")

    def test_probe_true_and_false(self):
        valid_urls = [
            "https://www.youtube.com/watch?v=abc123XYZ",
            "https://youtu.be/abc123XYZ",
            "https://youtube.com/embed/abc123XYZ",
            "https://m.youtube.com/watch?v=abc123XYZ",
        ]
        for url in valid_urls:
            with self.subTest(url=url):
                self.assertTrue(self.adapter.probe(url))

        invalid_urls = [
            "https://vimeo.com/123456",
            "https://example.com/watch?v=123",
            "https://youtube.com/user/channel",
            "not a url",
            "",
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                self.assertFalse(self.adapter.probe(url))
                with self.assertRaises(ValueError):
                    self.adapter.canonicalize(url)

    def test_extract_metadata(self):
        meta = self.adapter.extract_metadata("https://youtu.be/VIDEO_ID")
        self.assertEqual(meta["title"], "Sample Video Title")
        self.assertEqual(meta["channel_name"], "Channel Name")
        self.assertEqual(meta["channel_url"], "https://www.youtube.com/@channelhandle")
        self.assertEqual(meta["thumbnail_url"], "https://i.ytimg.com/vi/VIDEO_ID/hqdefault.jpg")
        self.assertEqual(meta["video_id"], "VIDEO_ID")
        self.assertEqual(meta["canonical_url"], self.canonical_watch)

    def test_list_units(self):
        units = self.adapter.list_units("https://youtu.be/VIDEO_ID")
        self.assertEqual(units, ["https://www.youtube.com/watch?v=VIDEO_ID"])

    def test_capabilities(self):
        caps = self.adapter.capabilities()
        self.assertEqual(caps.source_classes, frozenset({SourceClass.YOUTUBE}))
        self.assertFalse(caps.supports_incremental_updates)
        self.assertFalse(caps.requires_browser)

    def test_fetch_unit_normalize_stable_identity_roundtrip(self):
        url_watch = "https://www.youtube.com/watch?v=VIDEO_ID"
        url_short = "https://youtu.be/VIDEO_ID"

        acq_watch = self.adapter.fetch_unit(url_watch)
        self.assertEqual(acq_watch.status, AcquisitionStatus.OK)
        self.assertEqual(acq_watch.source_type, SourceClass.YOUTUBE)
        self.assertEqual(acq_watch.acquisition_method, AcquisitionMethod.STRUCTURED_API)
        self.assertIsNone(acq_watch.html)
        self.assertEqual(acq_watch.structured_json, self.sample_oembed)

        acq_short = self.adapter.fetch_unit(url_short)
        self.assertEqual(acq_short.status, AcquisitionStatus.OK)

        norm_watch = self.adapter.normalize(url_watch, acq_watch)
        norm_short = self.adapter.normalize(url_short, acq_short)

        self.assertIsInstance(norm_watch, Video)
        self.assertEqual(norm_watch.video_id, "VIDEO_ID")
        self.assertEqual(norm_watch.title, "Sample Video Title")
        self.assertEqual(norm_watch.thumbnail_url, "https://i.ytimg.com/vi/VIDEO_ID/hqdefault.jpg")
        self.assertIsNotNone(norm_watch.evidence)
        self.assertEqual(norm_watch.evidence.acquisition_method, AcquisitionMethod.STRUCTURED_API)
        self.assertEqual(norm_watch.evidence.provenance, "youtube_oembed")

        ident_watch = self.adapter.stable_identity(norm_watch)
        ident_short = self.adapter.stable_identity(norm_short)

        self.assertTrue(ident_watch)
        self.assertEqual(ident_watch, ident_short)

    def test_fetch_unit_failure(self):
        bad_adapter = YouTubeAdapter(fetcher=FixtureFetcher({}))
        res = bad_adapter.fetch_unit("https://www.youtube.com/watch?v=MISSING_ID")
        self.assertEqual(res.status, AcquisitionStatus.FAILED)
        self.assertEqual(res.source_type, SourceClass.YOUTUBE)
        self.assertEqual(res.acquisition_method, AcquisitionMethod.STRUCTURED_API)
        self.assertTrue(len(res.errors) > 0)
        self.assertEqual(res.errors[0].stage, "fetch")

    def test_fetch_transcript_raises(self):
        with self.assertRaises(NotImplementedError) as ctx:
            self.adapter.fetch_transcript("VIDEO_ID")
        self.assertIn("Transcript acquisition", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
