"""
Anti-spoiler as a hard invariant — Fanfic AI Chat V1 Phase 2.

THE most safety-critical module in this feature. Enforced at the
RETRIEVAL/QUERY level, on the candidate list itself, BEFORE anything reaches
prompt construction — never as an instruction inside the LLM prompt that the
model is merely asked to "please obey". A prompt-level instruction can be
overridden by prompt injection embedded in retrieved chapter text (see
`prompt_builder.py`'s threat model) or simply ignored by the model; a
Python `if` on a list of candidates cannot be talked out of doing its job.

Two composable, independent boundaries:
  - `enforce_spoiler_boundary` — for the CURRENT novel the user is reading,
    never return a chunk from a chapter later than they've reached.
  - `enforce_scope_boundary` — for novel-scoped chat modes (THIS_CHAPTER/
    THIS_STORY/CHARACTER), never return a chunk from a DIFFERENT novel at
    all — prevents cross-story retrieval leakage regardless of spoiler
    settings (a spoiler for novel A is not "safe" just because it came
    from novel B's retrieval pass by mistake).
"""
from __future__ import annotations

from typing import List, Sequence

from server.chat.domain import ChatScope, RetrievalResult, UserReadingContext

#: Scopes that are intentionally NOT bound to one novel - a query here may
#: legitimately span many novels, so `enforce_scope_boundary` is a no-op
#: for these (GENERAL chit-chat, SEARCH across the catalog, RECOMMENDATION
#: across the catalog).
_CROSS_NOVEL_SCOPES = frozenset({ChatScope.GENERAL, ChatScope.SEARCH, ChatScope.RECOMMENDATION})


def enforce_scope_boundary(
        candidates: Sequence[RetrievalResult], *, novel_id: str,
        scope: ChatScope) -> List[RetrievalResult]:
    """For THIS_CHAPTER/THIS_STORY/CHARACTER: only `novel_id`'s own chunks
    pass. For GENERAL/SEARCH/RECOMMENDATION: no filtering (cross-novel is
    the intended behavior for those scopes)."""
    if scope in _CROSS_NOVEL_SCOPES:
        return list(candidates)
    return [c for c in candidates if c.novel_id == novel_id]


def enforce_spoiler_boundary(
        candidates: Sequence[RetrievalResult], *,
        reading_context: UserReadingContext) -> List[RetrievalResult]:
    """The hard invariant: drop every candidate from
    `reading_context.novel_id` whose `chapter_index` is beyond
    `reading_context.current_chapter_index`, UNLESS the user has
    explicitly disabled spoiler protection. Candidates from OTHER novels
    are untouched here (that is `enforce_scope_boundary`'s job) - this
    function's only concern is the ONE novel this reading context is for.
    """
    if not reading_context.spoiler_protection_enabled:
        return list(candidates)
    return [
        c for c in candidates
        if c.novel_id != reading_context.novel_id
        or c.chapter_index <= reading_context.current_chapter_index
    ]


def apply_retrieval_gates(
        candidates: Sequence[RetrievalResult], *, context) -> List[RetrievalResult]:
    """Convenience composition of both gates, in the correct order (scope
    first narrows to the right novel[s], then spoiler filters within
    that). `context` is a `domain.ChatContext` - imported lazily via
    duck-typing on `.scope`/`.user_reading_context` to avoid a circular
    import (`domain` doesn't import this module)."""
    scoped = enforce_scope_boundary(
        candidates, novel_id=context.user_reading_context.novel_id, scope=context.scope)
    return enforce_spoiler_boundary(scoped, reading_context=context.user_reading_context)
