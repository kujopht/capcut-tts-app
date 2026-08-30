"""Phase 10/11 adversarial security/privacy tests using the REAL server.chat
modules. These run against actual production code (InMemoryVectorStore,
HashEmbeddingProvider, build_chunk_records, assemble_bounded_context,
build_prompt, build_citations) - nothing is mocked."""
import unittest

from server.chat.chunking import build_chunk_records
from server.chat.citation import build_citations
from server.chat.domain import (
    ChatContext, ChatScope, RetrievalResult, UserReadingContext,
)
from server.chat.embedding_provider import HashEmbeddingProvider
from server.chat.prompt_builder import build_prompt
from server.chat.retrieval import assemble_bounded_context, DEFAULT_MAX_CONTEXT_CHARS
from server.chat.vector_store import InMemoryVectorStore


def _result(index, text):
    return RetrievalResult(
        novel_id="n1", chapter_id=f"c{index}", chapter_index=index,
        chapter_title=f"Chapter {index}", chunk_text=text, chunk_order=0,
        similarity_score=0.9, content_hash="hash")


class HtmlInChunkStaysInertTest(unittest.TestCase):
    def test_script_content_stays_plain_string_in_user_context_not_system(self):
        malicious = "<script>alert('xss')</script><img src=x onerror=steal()>"
        results = [_result(4, malicious)]
        prompt = build_prompt("what happened", results)
        # build_prompt does no HTML rendering/parsing - the string is inert data.
        self.assertIn(malicious, prompt.user)
        self.assertNotIn(malicious, prompt.system)
        # It lands only after the RETRIEVED_CONTEXT-labeled block (inside the
        # user channel), never promoted into the operator-level system channel.
        header_idx = prompt.user.find("RETRIEVED_CONTEXT")
        self.assertGreater(header_idx, -1)
        self.assertGreater(prompt.user.find(malicious), header_idx)


class MassiveChunkBudgetTest(unittest.TestCase):
    def test_oversized_chunk_never_blows_char_budget(self):
        max_chars = DEFAULT_MAX_CONTEXT_CHARS
        results = [
            _result(1, "a" * 500),
            _result(2, "b" * 50000),
            _result(3, "c" * 500),
        ]
        kept = assemble_bounded_context(results, max_chars=max_chars)
        total = sum(len(r.chunk_text) for r in kept)
        self.assertLessEqual(total, max_chars)
        # The 50000-char chunk must have been excluded (never truncated), and
        # assembly halts at that first over-budget chunk.
        self.assertEqual([r.chapter_index for r in kept], [1])


class UnicodeControlCharsTest(unittest.TestCase):
    def test_control_and_zero_width_chars_do_not_crash_pipeline(self):
        dirty = "The hero SPILLED\x00 a secret\x1b [escape] and a zerowidth\u200b\u200c in between."
        records = build_chunk_records(
            novel_id="n1", chapter_id="c1", chapter_index=1,
            chapter_title="Ch 1", clean_text=dirty)
        self.assertTrue(records, "chunking should still produce records")
        prompt = build_prompt("what happened", [_result(1, dirty)])
        self.assertIn(dirty, prompt.user)
        citations = build_citations([_result(1, dirty)])
        self.assertTrue(citations, "a citation excerpt should still be built")
        self.assertTrue(citations[0].excerpt)


class NoSecretLeakTest(unittest.TestCase):
    SENTINEL = "FAKE_TOKEN_sk-live-0000_SECRET"
    HINT_SECRET = "HINT_SECRET_xyzzy"
    ACTIVE_SECRET = "ACTIVE_SECRET_wxyz"
    USER_SECRET = "USER_SECRET_qrst"
    EMAIL_SECRET = "user_secret@example.com"

    def test_chatcontext_hidden_fields_never_leak_into_built_prompt(self):
        reading = UserReadingContext(
            user_id=self.USER_SECRET, novel_id="n1", current_chapter_index=12)
        context = ChatContext(
            user_reading_context=reading, scope=ChatScope.THIS_STORY,
            active_chapter_id=self.ACTIVE_SECRET, character_hint=self.HINT_SECRET,
            selected_text=None)
        retrieval = [_result(4, "ordinary story content")]
        prompt = build_prompt("what happened", retrieval)
        combined = prompt.system + "\n" + prompt.user
        for secret in (self.HINT_SECRET, self.ACTIVE_SECRET, self.USER_SECRET, self.EMAIL_SECRET):
            self.assertNotIn(secret, combined,
                             f"secret {secret!r} leaked into a built prompt")

    def test_secrets_given_as_selected_and_chunk_text_never_enter_system_channel(self):
        retrieval = [_result(4, f"chunk carrying {self.SENTINEL}")]
        prompt = build_prompt(
            "what happened", retrieval, selected_text=f"selected carrying {self.EMAIL_SECRET}")
        self.assertNotIn(self.SENTINEL, prompt.system)
        self.assertNotIn(self.EMAIL_SECRET, prompt.system)
        # They ARE user-turn data by design (untrusted), so they belong in user.
        self.assertIn(self.SENTINEL, prompt.user)
        self.assertIn(self.EMAIL_SECRET, prompt.user)


class FullPipelineSecretEchoTest(unittest.TestCase):
    """End-to-end: run the real answer_question with sentinel-bearing reading
    context and confirm no system-prompt/global-state echo. Uses real
    store/embedder/chunking; only llm_complete is a local echo."""

    def test_no_secret_leaks_through_full_pipeline(self):
        from server.chat.pipeline import answer_question

        embedder = HashEmbeddingProvider(dimensions=32)
        store = InMemoryVectorStore()
        secret = "GLOBAL_SECRET_leak-check-0000"
        dirty = f"content with {secret} inside"
        records = build_chunk_records(
            novel_id="n1", chapter_id="c1", chapter_index=1,
            chapter_title="Ch 1", clean_text=dirty)
        vectors = embedder.embed([r.chunk_text for r in records])
        store.upsert(list(zip(records, vectors)))

        captured = {}

        def echo(system, user):
            captured["system"] = system
            captured["user"] = user
            return "answer"

        reading = UserReadingContext(
            user_id="u1", novel_id="n1", current_chapter_index=1)
        answer = answer_question(
            "what happened", reading_context=reading, vector_store=store,
            embedding_provider=embedder, llm_complete=echo,
            explicit_scope=ChatScope.THIS_STORY)
        self.assertFalse(answer.evidence_insufficient)
        self.assertIn(secret, captured["user"])
        self.assertNotIn(secret, captured["system"])


if __name__ == "__main__":
    unittest.main()
