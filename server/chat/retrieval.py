"""
RAG pipeline: intent classification -> retrieval scope -> retrieve -> rank
-> bounded context assembly — Fanfic AI Chat V1 Phase 3.

Never sends an entire story to the LLM: `assemble_bounded_context` caps
both the NUMBER of chunks and the TOTAL character budget, and the anti-
spoiler/scope gates (`spoiler_gate.py`) are applied unconditionally on
every retrieval, not just when a vector-store backend happens to support
metadata filtering.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from server.chat.domain import ChatContext, ChatScope, RetrievalResult
from server.chat.embedding_provider import EmbeddingProvider
from server.chat.spoiler_gate import apply_retrieval_gates
from server.chat.vector_store import VectorStore

#: How many candidates to pull from the vector store before ranking/gating.
DEFAULT_TOP_K = 20
#: Bounded context assembly - never more than this many chunks reach the
#: prompt, regardless of how many the vector store returned.
DEFAULT_MAX_CONTEXT_CHUNKS = 6
#: ...and never more than this many TOTAL characters either - a handful of
#: very long chunks must not blow the context budget just because each
#: individually stayed under the chunk-count cap.
DEFAULT_MAX_CONTEXT_CHARS = 6000

#: Scopes with no single novel to scope retrieval to.
_CROSS_NOVEL_SCOPES = frozenset({ChatScope.GENERAL, ChatScope.SEARCH, ChatScope.RECOMMENDATION})

_CHARACTER_KEYWORDS = ("who is", "who was", "relationship between", "character")
_SEARCH_KEYWORDS = ("which chapter", "when did", "when does", "where did", "first met", "find the")
_STORY_SUMMARY_KEYWORDS = ("summarize", "summary", "recap", "what happened so far")


def classify_intent(question: str, *, explicit_scope: Optional[ChatScope] = None) -> ChatScope:
    """If the UI already knows the scope (a quick action like "Ask this
    chapter" was clicked), that ALWAYS wins - `explicit_scope` takes
    precedence over any text classification. Free-text classification
    below is a plain keyword heuristic (deterministic, no ML) for
    General-chat-box input where the user didn't pick a quick action."""
    if explicit_scope is not None:
        return explicit_scope
    lowered = question.lower()
    if any(kw in lowered for kw in _CHARACTER_KEYWORDS):
        return ChatScope.CHARACTER
    if any(kw in lowered for kw in _SEARCH_KEYWORDS):
        return ChatScope.SEARCH
    if any(kw in lowered for kw in _STORY_SUMMARY_KEYWORDS):
        return ChatScope.THIS_STORY
    return ChatScope.GENERAL


def assemble_bounded_context(
        results: Sequence[RetrievalResult], *,
        max_chunks: int = DEFAULT_MAX_CONTEXT_CHUNKS,
        max_chars: int = DEFAULT_MAX_CONTEXT_CHARS) -> List[RetrievalResult]:
    """Greedily keeps highest-ranked results (caller must pass them
    pre-sorted) until either the chunk-count or character-budget cap would
    be exceeded. Never truncates a chunk's own text - it either fits
    whole or is excluded, so a citation never quotes a mid-sentence cut."""
    kept: List[RetrievalResult] = []
    total_chars = 0
    for result in results:
        if len(kept) >= max_chunks:
            break
        if kept and total_chars + len(result.chunk_text) > max_chars:
            break
        kept.append(result)
        total_chars += len(result.chunk_text)
    return kept


def retrieve(
        question: str, context: ChatContext, *, vector_store: VectorStore,
        embedding_provider: EmbeddingProvider, top_k: int = DEFAULT_TOP_K,
        max_context_chunks: int = DEFAULT_MAX_CONTEXT_CHUNKS,
        max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS) -> List[RetrievalResult]:
    [query_vector] = embedding_provider.embed([question])

    reading = context.user_reading_context
    novel_hint = None if context.scope in _CROSS_NOVEL_SCOPES else reading.novel_id
    chapter_hint = reading.current_chapter_index if reading.spoiler_protection_enabled else None

    raw = vector_store.query(
        query_vector, novel_id=novel_hint, max_chapter_index=chapter_hint, top_k=top_k)

    candidates = [
        RetrievalResult(
            novel_id=record.novel_id, chapter_id=record.chapter_id,
            chapter_index=record.chapter_index, chapter_title=record.chapter_title,
            chunk_text=record.chunk_text, chunk_order=record.chunk_order,
            similarity_score=score, content_hash=record.content_hash,
            language=record.language)
        for record, score in raw
    ]

    # Hard backstop - re-applied regardless of whether the store honored
    # the query-level hints above (see vector_store.py's module docstring).
    gated = apply_retrieval_gates(candidates, context=context)
    ranked = sorted(gated, key=lambda r: r.similarity_score, reverse=True)
    return assemble_bounded_context(ranked, max_chunks=max_context_chunks, max_chars=max_context_chars)
