import unittest

from server.chat.chunking import ChunkRecord
from server.chat.vector_store import InMemoryVectorStore, _cosine_similarity


def _record(novel_id, chapter_id, chapter_index, chunk_order=0):
    return ChunkRecord(
        novel_id=novel_id, chapter_id=chapter_id, chapter_index=chapter_index,
        chapter_title=f"Ch{chapter_index}", chunk_order=chunk_order,
        chunk_text=f"text {chapter_id} {chunk_order}", content_hash="ch",
        chunk_hash=f"{chapter_id}-{chunk_order}")


class CosineSimilarityTest(unittest.TestCase):
    def test_identical_vectors_similarity_one(self):
        self.assertAlmostEqual(_cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)

    def test_orthogonal_vectors_similarity_zero(self):
        self.assertAlmostEqual(_cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_zero_vector_returns_zero_not_nan_or_crash(self):
        self.assertEqual(_cosine_similarity([0.0, 0.0], [1.0, 1.0]), 0.0)

    def test_mismatched_length_raises(self):
        with self.assertRaises(ValueError):
            _cosine_similarity([1.0], [1.0, 2.0])


class InMemoryVectorStoreTest(unittest.TestCase):
    def test_upsert_then_query_returns_the_record(self):
        store = InMemoryVectorStore()
        store.upsert([(_record("n1", "c1", 1), [1.0, 0.0])])
        results = store.query([1.0, 0.0], top_k=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0].chapter_id, "c1")
        self.assertAlmostEqual(results[0][1], 1.0)

    def test_novel_id_filter_excludes_other_novels(self):
        store = InMemoryVectorStore()
        store.upsert([(_record("n1", "c1", 1), [1.0, 0.0]),
                     (_record("n2", "c2", 1), [1.0, 0.0])])
        results = store.query([1.0, 0.0], novel_id="n1", top_k=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0].novel_id, "n1")

    def test_max_chapter_index_filter_excludes_later_chapters(self):
        store = InMemoryVectorStore()
        store.upsert([(_record("n1", "c1", 1), [1.0, 0.0]),
                     (_record("n1", "c99", 99), [1.0, 0.0])])
        results = store.query([1.0, 0.0], max_chapter_index=10, top_k=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0].chapter_index, 1)

    def test_top_k_caps_results(self):
        store = InMemoryVectorStore()
        store.upsert([(_record("n1", f"c{i}", i), [1.0, 0.0]) for i in range(5)])
        results = store.query([1.0, 0.0], top_k=2)
        self.assertEqual(len(results), 2)

    def test_results_sorted_highest_similarity_first(self):
        store = InMemoryVectorStore()
        store.upsert([(_record("n1", "close", 1), [0.9, 0.1]),
                     (_record("n1", "far", 2), [0.1, 0.9])])
        results = store.query([1.0, 0.0], top_k=5)
        self.assertEqual(results[0][0].chapter_id, "close")

    def test_delete_by_chapter_removes_only_that_chapter(self):
        store = InMemoryVectorStore()
        store.upsert([(_record("n1", "c1", 1, 0), [1.0, 0.0]),
                     (_record("n1", "c1", 1, 1), [1.0, 0.0]),
                     (_record("n1", "c2", 2, 0), [1.0, 0.0])])
        store.delete_by_chapter("c1")
        results = store.query([1.0, 0.0], top_k=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0].chapter_id, "c2")

    def test_get_content_hash_and_chunking_version_roundtrip(self):
        store = InMemoryVectorStore()
        rec = _record("n1", "c1", 1)
        store.upsert([(rec, [1.0, 0.0])])
        self.assertEqual(store.get_content_hash("c1"), rec.content_hash)
        self.assertEqual(store.get_chunking_version("c1"), rec.chunking_version)

    def test_get_content_hash_none_when_unknown_chapter(self):
        store = InMemoryVectorStore()
        self.assertIsNone(store.get_content_hash("nope"))
        self.assertIsNone(store.get_chunking_version("nope"))


if __name__ == "__main__":
    unittest.main()
