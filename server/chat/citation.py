"""Citation building — Fanfic AI Chat V1 Phase 5. Never fabricated: every
`Citation` is built directly from a `RetrievalResult` that actually
contributed to an answer, never invented from the LLM's own response text.
"""
from __future__ import annotations

from typing import List, Sequence

from server.chat.domain import Citation, RetrievalResult

#: A citation excerpt is a POINTER, not a content mirror - short and
#: bounded, matching the same discipline as V5's `fingerprint._clip`.
MAX_EXCERPT_CHARS = 200


def build_citations(results: Sequence[RetrievalResult]) -> List[Citation]:
    """One citation per distinct (chapter, chunk) actually retrieved -
    order preserved, duplicates (the same chunk retrieved twice) collapsed."""
    citations: List[Citation] = []
    seen = set()
    for r in results:
        key = (r.chapter_id, r.chunk_order)
        if key in seen:
            continue
        seen.add(key)
        citations.append(Citation(
            novel_id=r.novel_id, chapter_id=r.chapter_id,
            chapter_index=r.chapter_index, chapter_title=r.chapter_title,
            excerpt=r.chunk_text[:MAX_EXCERPT_CHARS].strip(),
            chunk_order=r.chunk_order))
    return citations
