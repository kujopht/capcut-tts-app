import unittest

from server.scraper.universal.acquisition import AcquisitionMethod
from server.scraper.universal.units import (
    Document, DocumentSection, Feed, FeedItem, RawEvidence, TranscriptSegment,
    Video, VideoChapter,
)


class UnitsConstructionTest(unittest.TestCase):
    def test_video_minimal(self):
        v = Video(platform="youtube", video_id="abc", canonical_url="https://youtube.com/watch?v=abc")
        self.assertEqual(v.title, "")
        self.assertIsNone(v.evidence)

    def test_video_with_evidence(self):
        ev = RawEvidence(acquisition_method=AcquisitionMethod.STRUCTURED_API,
                         final_url="https://youtube.com/oembed?url=x", provenance="youtube_oembed")
        v = Video(platform="youtube", video_id="abc", canonical_url="u", evidence=ev)
        self.assertEqual(v.evidence.provenance, "youtube_oembed")

    def test_video_chapter_and_transcript_segment(self):
        vc = VideoChapter(video_id="abc", title="Intro", start_seconds=0.0, end_seconds=30.0)
        ts = TranscriptSegment(video_id="abc", text="hello", start_seconds=0.0, end_seconds=2.0)
        self.assertLess(vc.start_seconds, vc.end_seconds)
        self.assertEqual(ts.language, "")

    def test_document_and_section(self):
        d = Document(source_url="https://example.com/doc.pdf", content_type="application/pdf")
        s = DocumentSection(document_id="d1", order=0, heading="Intro", text="body")
        self.assertEqual(s.order, 0)
        self.assertEqual(d.content_type, "application/pdf")

    def test_feed_and_item(self):
        f = Feed(source_url="https://example.com/rss", canonical_url="https://example.com/rss")
        item = FeedItem(feed_id="f1", guid="guid-1", title="Post")
        self.assertEqual(item.feed_id, "f1")
        self.assertEqual(f.title, "")


if __name__ == "__main__":
    unittest.main()
