"""
E2E Scenario — Fanfic AI Chat V1 Phase 14.

Proves the full reader journey end to end on a fixture story, exactly as
specified in the mission brief: a >=10-chapter story, a user at chapter 7,
asking about evidence in an earlier chapter (must cite it), asking about
evidence only in a LATER chapter (must not reveal it), explaining a
reader-selected paragraph, and a chapter-lookup search question.

Uses the real pipeline (`answer_question`), a real `InMemoryVectorStore`,
a real `HashEmbeddingProvider`, and `MockLLMProvider` (no live API key in
this environment) - only the LLM's own prose is mocked; every retrieval/
citation/spoiler decision is the real code path.
"""
from __future__ import annotations

from typing import Dict

from server.chat.chunking import build_chunk_records
from server.chat.domain import ChatScope, UserReadingContext
from server.chat.embedding_provider import HashEmbeddingProvider
from server.chat.pipeline import answer_question
from server.chat.vector_store import InMemoryVectorStore
from server.llm_gateway.provider import MockLLMProvider

NOVEL_ID = "e2e-reader-novel"
#: 10 chapters, chapter 4 holds the "early evidence", chapter 9 holds the
#: "future evidence" that must never reach a user at chapter 7.
_CHAPTER_TEXT: Dict[int, str] = {
    1: "Kai arrived at the old academy, uncertain of what lay ahead.",
    2: "The academy's halls were lined with portraits of forgotten mages.",
    3: "Kai met Sera, a fellow student with a sharp tongue and sharper mind.",
    4: "Kai discovered a hidden door behind the library's oldest shelf, "
      "leading to a forgotten archive of banned spells.",
    5: "Sera warned Kai that the archive was rumored to be cursed.",
    6: "The two of them began sneaking into the archive at night to study "
      "the banned spells together.",
    7: "Kai and Sera first met the archive's silent guardian, a spirit "
      "bound to protect the banned spells.",
    8: "The guardian tested Kai's resolve with a series of riddles.",
    9: "Kai later learned the archive's true purpose: it was built to "
      "seal away a corrupted mage from centuries past.",
    10: "The corrupted mage's seal began to weaken as Kai's power grew.",
}


def _build_store() -> InMemoryVectorStore:
    store = InMemoryVectorStore()
    embedder = HashEmbeddingProvider(dimensions=48)
    for chapter_index, text in _CHAPTER_TEXT.items():
        records = build_chunk_records(
            novel_id=NOVEL_ID, chapter_id=f"ch{chapter_index}",
            chapter_index=chapter_index, chapter_title=f"Chapter {chapter_index}",
            clean_text=text)
        vectors = embedder.embed([r.chunk_text for r in records])
        store.upsert(list(zip(records, vectors)))
    return store, embedder


def _echo_llm(system: str, user: str) -> str:
    provider = MockLLMProvider()
    return provider.complete(
        system=system, user=user, model="mock", max_output_tokens=200).text


def run_scenario() -> dict:
    store, embedder = _build_store()
    reading = UserReadingContext(user_id="reader-1", novel_id=NOVEL_ID,
                                 current_chapter_index=7)

    # 1. Evidence in an EARLIER chapter (4) than the user's progress (7) -
    #    must be cited.
    early_answer = answer_question(
        "What did Kai discover in the library?", reading_context=reading,
        vector_store=store, embedding_provider=embedder, llm_complete=_echo_llm,
        explicit_scope=ChatScope.THIS_STORY)
    early_cited_chapters = {c.chapter_index for c in early_answer.citations}

    # 2. Evidence ONLY in a chapter (9) AFTER the user's progress (7) -
    #    must NEVER be revealed.
    future_answer = answer_question(
        "What does Kai learn about the archive's true purpose later?",
        reading_context=reading, vector_store=store, embedding_provider=embedder,
        llm_complete=_echo_llm, explicit_scope=ChatScope.THIS_STORY)
    future_cited_chapters = {c.chapter_index for c in future_answer.citations}

    # 3. Reader-selected paragraph -> "Explain this paragraph" (THIS_CHAPTER
    #    scope, with selected_text carrying the reader's own selection).
    explain_answer = answer_question(
        "Explain this paragraph", reading_context=reading, vector_store=store,
        embedding_provider=embedder, llm_complete=_echo_llm,
        explicit_scope=ChatScope.THIS_CHAPTER, active_chapter_id="ch7",
        selected_text=_CHAPTER_TEXT[7])

    # 4. Exact chapter lookup via search.
    search_answer = answer_question(
        "When did Kai first meet the guardian?", reading_context=reading,
        vector_store=store, embedding_provider=embedder, llm_complete=_echo_llm,
        explicit_scope=ChatScope.SEARCH)
    search_top_chapter = (search_answer.citations[0].chapter_index
                         if search_answer.citations else None)

    return {
        "early_evidence": {
            "cited_chapters": sorted(early_cited_chapters),
            "chapter_4_cited": 4 in early_cited_chapters,
        },
        "future_evidence_blocked": {
            "cited_chapters": sorted(future_cited_chapters),
            "chapter_9_leaked": 9 in future_cited_chapters,
            "evidence_insufficient": future_answer.evidence_insufficient,
        },
        "explain_paragraph": {
            "answer_text": explain_answer.answer_text,
            "cited_chapters": sorted({c.chapter_index for c in explain_answer.citations}),
        },
        "search_lookup": {
            "top_cited_chapter": search_top_chapter,
            "correct": search_top_chapter == 7,
        },
    }
