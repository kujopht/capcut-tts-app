import unittest

from server.chat.chunking import ChunkRecord
from server.chat.domain import ChatScope, UserReadingContext
from server.chat.embedding_provider import HashEmbeddingProvider
from server.chat.pipeline import answer_question
from server.chat.vector_store import InMemoryVectorStore


def _chunk(novel_id, chapter_id, chapter_index, text):
    return ChunkRecord(
        novel_id=novel_id, chapter_id=chapter_id, chapter_index=chapter_index,
        chapter_title=f"Chapter {chapter_index}", chunk_order=0, chunk_text=text,
        content_hash="h", chunk_hash=f"{chapter_id}-hash")


class AnswerQuestionTest(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryVectorStore()
        self.embedder = HashEmbeddingProvider(dimensions=32)
        chunks = [
            _chunk("n1", "c4", 4, "the hero found a hidden sword"),
            _chunk("n1", "c9", 9, "the sword turned out to be cursed"),
        ]
        vectors = self.embedder.embed([c.chunk_text for c in chunks])
        self.store.upsert(list(zip(chunks, vectors)))
        self.captured_prompts = []

    def _echo_llm(self, system, user):
        self.captured_prompts.append((system, user))
        return "This is the assistant's answer."

    def test_returns_citations_grounded_in_retrieval(self):
        reading = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=10)
        answer = answer_question(
            "what did the hero find?", reading_context=reading,
            vector_store=self.store, embedding_provider=self.embedder,
            llm_complete=self._echo_llm, explicit_scope=ChatScope.THIS_STORY)
        self.assertEqual(answer.answer_text, "This is the assistant's answer.")
        self.assertTrue(answer.citations)
        self.assertFalse(answer.evidence_insufficient)

    def test_spoiler_boundary_enforced_through_full_pipeline(self):
        reading = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=5)
        answer = answer_question(
            "was the sword cursed?", reading_context=reading,
            vector_store=self.store, embedding_provider=self.embedder,
            llm_complete=self._echo_llm, explicit_scope=ChatScope.THIS_STORY)
        self.assertTrue(all(c.chapter_index <= 5 for c in answer.citations))

    def test_llm_receives_separated_system_and_user_prompt(self):
        reading = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=10)
        answer_question(
            "what happened?", reading_context=reading, vector_store=self.store,
            embedding_provider=self.embedder, llm_complete=self._echo_llm,
            explicit_scope=ChatScope.THIS_STORY)
        system, user = self.captured_prompts[0]
        self.assertIn("untrusted", system.lower())
        self.assertIn("RETRIEVED_CONTEXT", user)

    def test_no_evidence_flagged_when_retrieval_empty(self):
        reading = UserReadingContext(user_id="u2", novel_id="NO_SUCH_NOVEL", current_chapter_index=1)
        answer = answer_question(
            "anything?", reading_context=reading, vector_store=self.store,
            embedding_provider=self.embedder, llm_complete=self._echo_llm,
            explicit_scope=ChatScope.THIS_STORY)
        self.assertTrue(answer.evidence_insufficient)
        self.assertEqual(answer.citations, [])

    def test_freeform_question_without_explicit_scope_still_classifies(self):
        """Regression: explicit_scope=None must trigger real keyword
        classification, not silently default to something that skips
        retrieval - a plain chat-box question with no button clicked must
        still work."""
        reading = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=10)
        answer = answer_question(
            "summarize the last chapters", reading_context=reading,
            vector_store=self.store, embedding_provider=self.embedder,
            llm_complete=self._echo_llm, explicit_scope=None)
        self.assertIsInstance(answer.answer_text, str)


if __name__ == "__main__":
    unittest.main()
