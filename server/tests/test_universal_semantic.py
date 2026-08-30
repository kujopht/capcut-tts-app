import unittest

from server.scraper.universal.semantic import (
    ChunkBoundary, TimestampRange, build_semantic_ready_output, chunk_text,
)


class ChunkTextTest(unittest.TestCase):
    def test_empty_text_no_chunks(self):
        self.assertEqual(chunk_text(""), [])

    def test_text_shorter_than_max_chars_is_one_chunk(self):
        chunks = chunk_text("short text", max_chars=1000, overlap_chars=100)
        self.assertEqual(chunks, [ChunkBoundary(0, len("short text"))])

    def test_chunks_cover_the_whole_text(self):
        text = "x" * 2500
        chunks = chunk_text(text, max_chars=1000, overlap_chars=100)
        self.assertEqual(chunks[-1].end_char, len(text))
        self.assertEqual(chunks[0].start_char, 0)

    def test_consecutive_chunks_overlap_by_requested_amount(self):
        text = "x" * 2500
        chunks = chunk_text(text, max_chars=1000, overlap_chars=100)
        self.assertEqual(chunks[1].start_char, chunks[0].end_char - 100)

    def test_last_chunk_not_padded_past_text_end(self):
        text = "x" * 1050
        chunks = chunk_text(text, max_chars=1000, overlap_chars=100)
        self.assertEqual(chunks[-1].end_char, 1050)
        for c in chunks:
            self.assertLessEqual(c.end_char, 1050)

    def test_invalid_max_chars_raises(self):
        with self.assertRaises(ValueError):
            chunk_text("x", max_chars=0)

    def test_invalid_overlap_raises(self):
        with self.assertRaises(ValueError):
            chunk_text("x" * 100, max_chars=10, overlap_chars=10)


class BuildSemanticReadyOutputTest(unittest.TestCase):
    def test_defaults_embedding_and_entity_input_to_clean_text(self):
        out = build_semantic_ready_output("hello world")
        self.assertEqual(out.embedding_ready_text, "hello world")
        self.assertEqual(out.entity_extraction_input, "hello world")

    def test_summary_placeholder_is_none_not_fabricated(self):
        out = build_semantic_ready_output("hello world")
        self.assertIsNone(out.summary_placeholder)

    def test_timestamp_ranges_passed_through_for_transcript_units(self):
        ranges = [TimestampRange(0.0, 5.0), TimestampRange(5.0, 10.0)]
        out = build_semantic_ready_output("hello", timestamp_ranges=ranges)
        self.assertEqual(out.timestamp_ranges, ranges)

    def test_language_tag_passed_through(self):
        out = build_semantic_ready_output("xin chao", language="vi")
        self.assertEqual(out.language, "vi")

    def test_chunk_boundaries_computed_with_custom_size(self):
        out = build_semantic_ready_output("x" * 50, max_chunk_chars=20, chunk_overlap_chars=5)
        self.assertGreater(len(out.chunk_boundaries), 1)


if __name__ == "__main__":
    unittest.main()
