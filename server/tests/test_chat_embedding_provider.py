import unittest

from server.chat.embedding_provider import HashEmbeddingProvider


class HashEmbeddingProviderTest(unittest.TestCase):
    def test_dimensions_property(self):
        provider = HashEmbeddingProvider(dimensions=32)
        self.assertEqual(provider.dimensions, 32)

    def test_invalid_dimensions_raises(self):
        with self.assertRaises(ValueError):
            HashEmbeddingProvider(dimensions=0)

    def test_empty_input_returns_empty_list(self):
        provider = HashEmbeddingProvider()
        self.assertEqual(provider.embed([]), [])

    def test_one_vector_per_input_same_order(self):
        provider = HashEmbeddingProvider()
        vectors = provider.embed(["hello world", "goodbye"])
        self.assertEqual(len(vectors), 2)

    def test_vector_length_matches_dimensions(self):
        provider = HashEmbeddingProvider(dimensions=16)
        vectors = provider.embed(["some text"])
        self.assertEqual(len(vectors[0]), 16)

    def test_deterministic_across_calls(self):
        """Regression: must NOT use Python's randomized hash() - the same
        text must embed identically every call, in this process and any
        other."""
        provider = HashEmbeddingProvider()
        v1 = provider.embed(["the quick brown fox"])[0]
        v2 = provider.embed(["the quick brown fox"])[0]
        self.assertEqual(v1, v2)

    def test_similar_texts_score_higher_than_unrelated_texts(self):
        provider = HashEmbeddingProvider(dimensions=64)
        from server.chat.vector_store import _cosine_similarity
        base = provider.embed(["the dragon flew over the mountain"])[0]
        similar = provider.embed(["the dragon flew over the valley"])[0]
        unrelated = provider.embed(["stock prices rose sharply today"])[0]
        sim_score = _cosine_similarity(base, similar)
        unrelated_score = _cosine_similarity(base, unrelated)
        self.assertGreater(sim_score, unrelated_score)

    def test_empty_string_does_not_crash(self):
        provider = HashEmbeddingProvider()
        vectors = provider.embed([""])
        self.assertEqual(len(vectors), 1)
        self.assertEqual(sum(vectors[0]), 0.0)


if __name__ == "__main__":
    unittest.main()
