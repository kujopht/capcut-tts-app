"""
Abstract vector-store interface — Fanfic AI Chat V1 Phase 3/4.

Kept abstract per the mission brief ("do not prematurely lock the whole
platform to one vendor"). `InMemoryVectorStore` is a real, correct
reference implementation (useful for development/tests and a genuinely
small deployment) - a production-scale backend (pgvector/Pinecone/
Qdrant/...) implements the same `VectorStore` contract without the rest of
this package changing.

`query()`'s `max_chapter_index` parameter is an OPTIMIZATION HINT a real
backend can push down as a metadata filter (never fetching spoiler
content into memory at all) - it is NOT the enforcement point for the
anti-spoiler invariant. `retrieval.py` ALWAYS re-applies
`spoiler_gate.apply_retrieval_gates` on whatever a `VectorStore` returns,
regardless of whether the store honored this hint, so the hard invariant
never depends on trusting a specific backend's filter implementation.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Sequence, Tuple

from server.chat.chunking import ChunkRecord


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, records: Sequence[Tuple[ChunkRecord, Sequence[float]]]) -> None:
        """Insert or replace, keyed by `ChunkRecord.chunk_hash`."""

    @abstractmethod
    def query(self, query_vector: Sequence[float], *, novel_id: Optional[str] = None,
              max_chapter_index: Optional[int] = None,
              top_k: int = 10) -> List[Tuple[ChunkRecord, float]]:
        """Returns (record, similarity_score) pairs, highest score first.
        `novel_id`/`max_chapter_index` are optimization hints only - see
        module docstring."""

    @abstractmethod
    def delete_by_chapter(self, chapter_id: str) -> None:
        """Remove every chunk belonging to `chapter_id` - used when a
        chapter is deleted/unpublished, or before re-embedding it."""

    @abstractmethod
    def get_content_hash(self, chapter_id: str) -> Optional[str]:
        """The `content_hash` currently stored for `chapter_id`, or `None`
        if never embedded - feeds `chunking.needs_reembedding`."""

    @abstractmethod
    def get_chunking_version(self, chapter_id: str) -> Optional[int]:
        """The `chunking_version` currently stored for `chapter_id`, or
        `None` if never embedded - feeds `chunking.needs_reembedding`."""


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError(
            f"Vector khac chieu dai: {len(a)} != {len(b)} - khong the so sanh.")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class InMemoryVectorStore(VectorStore):
    """Real, correct, in-process reference implementation - brute-force
    cosine similarity. Fine for development, tests, and a genuinely small
    catalog; not meant to scale to a large embedding count, which is
    exactly what the abstract interface exists to allow swapping out."""

    def __init__(self):
        self._rows: Dict[str, Tuple[ChunkRecord, List[float]]] = {}

    def upsert(self, records: Sequence[Tuple[ChunkRecord, Sequence[float]]]) -> None:
        for record, vector in records:
            self._rows[record.chunk_hash] = (record, list(vector))

    def query(self, query_vector: Sequence[float], *, novel_id: Optional[str] = None,
              max_chapter_index: Optional[int] = None,
              top_k: int = 10) -> List[Tuple[ChunkRecord, float]]:
        scored = []
        for record, vector in self._rows.values():
            if novel_id is not None and record.novel_id != novel_id:
                continue
            if max_chapter_index is not None and record.chapter_index > max_chapter_index:
                continue
            scored.append((record, _cosine_similarity(query_vector, vector)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    def delete_by_chapter(self, chapter_id: str) -> None:
        stale_keys = [k for k, (r, _) in self._rows.items() if r.chapter_id == chapter_id]
        for key in stale_keys:
            del self._rows[key]

    def get_content_hash(self, chapter_id: str) -> Optional[str]:
        for record, _ in self._rows.values():
            if record.chapter_id == chapter_id:
                return record.content_hash
        return None

    def get_chunking_version(self, chapter_id: str) -> Optional[int]:
        for record, _ in self._rows.values():
            if record.chapter_id == chapter_id:
                return record.chunking_version
        return None
