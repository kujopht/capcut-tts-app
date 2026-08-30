import unittest

from server.chat.chunking import CHUNKING_VERSION, build_chunk_records, needs_reembedding
from server.scraper.dedupe import content_hash


class BuildChunkRecordsTest(unittest.TestCase):
    def test_empty_text_no_records(self):
        records = build_chunk_records(
            novel_id="n1", chapter_id="c1", chapter_index=1, chapter_title="Ch1",
            clean_text="")
        self.assertEqual(records, [])

    def test_short_text_one_record(self):
        records = build_chunk_records(
            novel_id="n1", chapter_id="c1", chapter_index=1, chapter_title="Ch1",
            clean_text="short chapter text")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].chunk_order, 0)
        self.assertEqual(records[0].novel_id, "n1")
        self.assertEqual(records[0].chapter_index, 1)

    def test_long_text_multiple_records_with_increasing_order(self):
        records = build_chunk_records(
            novel_id="n1", chapter_id="c1", chapter_index=1, chapter_title="Ch1",
            clean_text="x" * 2500, max_chunk_chars=1000, chunk_overlap_chars=100)
        self.assertGreater(len(records), 1)
        orders = [r.chunk_order for r in records]
        self.assertEqual(orders, sorted(orders))

    def test_content_hash_same_across_all_chunks_of_one_chapter(self):
        records = build_chunk_records(
            novel_id="n1", chapter_id="c1", chapter_index=1, chapter_title="Ch1",
            clean_text="x" * 2500, max_chunk_chars=1000, chunk_overlap_chars=100)
        hashes = {r.content_hash for r in records}
        self.assertEqual(len(hashes), 1)
        self.assertEqual(hashes.pop(), content_hash("x" * 2500))

    def test_chunk_hash_differs_between_different_chunks(self):
        records = build_chunk_records(
            novel_id="n1", chapter_id="c1", chapter_index=1, chapter_title="Ch1",
            clean_text="a" * 1000 + "b" * 1000, max_chunk_chars=1000, chunk_overlap_chars=0)
        chunk_hashes = {r.chunk_hash for r in records}
        self.assertEqual(len(chunk_hashes), len(records))

    def test_chunking_version_stamped(self):
        records = build_chunk_records(
            novel_id="n1", chapter_id="c1", chapter_index=1, chapter_title="Ch1",
            clean_text="text")
        self.assertEqual(records[0].chunking_version, CHUNKING_VERSION)

    def test_source_identity_key_default_empty_for_native_content(self):
        records = build_chunk_records(
            novel_id="n1", chapter_id="c1", chapter_index=1, chapter_title="Ch1",
            clean_text="text")
        self.assertEqual(records[0].source_identity_key, "")

    def test_source_identity_key_passed_through_for_scraped_content(self):
        records = build_chunk_records(
            novel_id="n1", chapter_id="c1", chapter_index=1, chapter_title="Ch1",
            clean_text="text", source_identity_key="abc123")
        self.assertEqual(records[0].source_identity_key, "abc123")


class NeedsReembeddingTest(unittest.TestCase):
    def test_never_embedded_needs_embedding(self):
        self.assertTrue(needs_reembedding(
            stored_content_hash=None, stored_chunking_version=None,
            current_content_hash="h1"))

    def test_unchanged_content_and_version_does_not_need_reembedding(self):
        self.assertFalse(needs_reembedding(
            stored_content_hash="h1", stored_chunking_version=CHUNKING_VERSION,
            current_content_hash="h1", current_chunking_version=CHUNKING_VERSION))

    def test_changed_content_needs_reembedding(self):
        self.assertTrue(needs_reembedding(
            stored_content_hash="h1", stored_chunking_version=CHUNKING_VERSION,
            current_content_hash="h2", current_chunking_version=CHUNKING_VERSION))

    def test_changed_chunking_version_needs_reembedding_even_if_content_same(self):
        self.assertTrue(needs_reembedding(
            stored_content_hash="h1", stored_chunking_version=0,
            current_content_hash="h1", current_chunking_version=CHUNKING_VERSION))


if __name__ == "__main__":
    unittest.main()
