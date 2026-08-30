import unittest

from server.chat.chunking import ChunkRecord
from server.chat.domain import ChatContext, ChatScope, RetrievalResult, UserReadingContext
from server.chat.embedding_provider import HashEmbeddingProvider
from server.chat.retrieval import (
    DEFAULT_MAX_CONTEXT_CHARS, assemble_bounded_context, classify_intent, retrieve,
)
from server.chat.vector_store import InMemoryVectorStore


class ClassifyIntentTest(unittest.TestCase):
    def test_explicit_scope_always_wins(self):
        self.assertEqual(
            classify_intent("who is X?", explicit_scope=ChatScope.THIS_CHAPTER),
            ChatScope.THIS_CHAPTER)

    def test_character_keyword(self):
        self.assertEqual(classify_intent("Who is the main villain?"), ChatScope.CHARACTER)

    def test_relationship_keyword(self):
        self.assertEqual(
            classify_intent("What is the relationship between A and B?"),
            ChatScope.CHARACTER)

    def test_search_keyword(self):
        self.assertEqual(
            classify_intent("In which chapter did X first meet Y?"), ChatScope.SEARCH)

    def test_summary_keyword(self):
        self.assertEqual(classify_intent("Can you summarize the last 5 chapters?"),
                         ChatScope.THIS_STORY)

    def test_default_general(self):
        self.assertEqual(classify_intent("hello there"), ChatScope.GENERAL)


class AssembleBoundedContextTest(unittest.TestCase):
    def _result(self, chapter_index, text_len):
        return RetrievalResult(
            novel_id="n1", chapter_id=f"c{chapter_index}", chapter_index=chapter_index,
            chapter_title=f"Ch{chapter_index}", chunk_text="x" * text_len, chunk_order=0,
            similarity_score=1.0, content_hash="h")

    def test_caps_chunk_count(self):
        results = [self._result(i, 10) for i in range(20)]
        assembled = assemble_bounded_context(results, max_chunks=3, max_chars=1_000_000)
        self.assertEqual(len(assembled), 3)

    def test_caps_char_budget(self):
        results = [self._result(i, 3000) for i in range(5)]
        assembled = assemble_bounded_context(results, max_chunks=100, max_chars=6000)
        self.assertEqual(len(assembled), 2)

    def test_always_keeps_at_least_one_even_if_it_alone_exceeds_budget(self):
        """A single very long chunk shouldn't be dropped entirely just
        because it alone exceeds the char budget - that would leave zero
        context, worse than one long chunk."""
        results = [self._result(1, 10_000)]
        assembled = assemble_bounded_context(results, max_chars=DEFAULT_MAX_CONTEXT_CHARS)
        self.assertEqual(len(assembled), 1)

    def test_empty_input(self):
        self.assertEqual(assemble_bounded_context([]), [])


def _chunk(novel_id, chapter_id, chapter_index, text):
    return ChunkRecord(
        novel_id=novel_id, chapter_id=chapter_id, chapter_index=chapter_index,
        chapter_title=f"Chapter {chapter_index}", chunk_order=0, chunk_text=text,
        content_hash="h", chunk_hash=f"{chapter_id}-hash")


class RetrieveEndToEndTest(unittest.TestCase):
    """Real InMemoryVectorStore + real HashEmbeddingProvider - no mocks of
    the business logic. Proves the spoiler/scope gates are actually wired
    into retrieve(), not just unit-tested in isolation."""

    def setUp(self):
        self.store = InMemoryVectorStore()
        self.embedder = HashEmbeddingProvider(dimensions=32)
        chunks = [
            _chunk("n1", "c4", 4, "the hero discovered a hidden sword in chapter four"),
            _chunk("n1", "c9", 9, "the hero discovered a hidden sword was cursed in chapter nine"),
            _chunk("OTHER_NOVEL", "oc1", 1, "the hero discovered a hidden sword in another novel"),
        ]
        vectors = self.embedder.embed([c.chunk_text for c in chunks])
        self.store.upsert(list(zip(chunks, vectors)))

    def test_future_chapter_never_returned_when_user_has_not_read_it(self):
        reading = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=7)
        context = ChatContext(user_reading_context=reading, scope=ChatScope.THIS_STORY)
        results = retrieve(
            "what did the hero discover about the sword?", context,
            vector_store=self.store, embedding_provider=self.embedder)
        self.assertTrue(all(r.chapter_index <= 7 for r in results))
        self.assertTrue(any(r.chapter_index == 4 for r in results))

    def test_cross_novel_leakage_blocked_in_this_story_scope(self):
        reading = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=20)
        context = ChatContext(user_reading_context=reading, scope=ChatScope.THIS_STORY)
        results = retrieve(
            "what did the hero discover?", context,
            vector_store=self.store, embedding_provider=self.embedder)
        self.assertTrue(all(r.novel_id == "n1" for r in results))

    def test_disabling_spoiler_protection_allows_future_chapter(self):
        reading = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=1,
                                     spoiler_protection_enabled=False)
        context = ChatContext(user_reading_context=reading, scope=ChatScope.THIS_STORY)
        results = retrieve(
            "what did the hero discover about the cursed sword?", context,
            vector_store=self.store, embedding_provider=self.embedder)
        self.assertTrue(any(r.chapter_index == 9 for r in results))


if __name__ == "__main__":
    unittest.main()
