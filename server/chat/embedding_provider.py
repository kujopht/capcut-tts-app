"""
Embedding generation, behind a provider interface — Fanfic AI Chat V1
Phase 4. Kept abstract for the same reason as `vector_store.VectorStore`:
no embedding vendor is chosen yet. `HashEmbeddingProvider` is a real,
deterministic, dependency-free implementation useful for development/tests
without any API key - not semantically meaningful like a real model's
embeddings, but genuinely functional and swappable for one (OpenAI
`text-embedding-3-*`, Gemini `embedding-001`, a self-hosted model) via the
same interface.
"""
from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from typing import List, Sequence


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """One vector per input text, same order. Must never raise on
        empty input - return `[]`."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        ...


def _stable_trigram_index(trigram: str, dimensions: int) -> int:
    """`hash()` on a `str` is PYTHONHASHSEED-randomized per process in
    real Python - using it here would make embeddings silently different
    across process restarts, breaking any persisted vector store. sha256
    is deterministic across processes/machines, which is the actual
    requirement for anything meant to be stored and compared later."""
    digest = hashlib.sha256(trigram.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % dimensions


class HashEmbeddingProvider(EmbeddingProvider):
    """Character-trigram hashing into a fixed-size vector, L2-normalized.
    Deterministic, no network, no model weights - similar texts (sharing
    many trigrams) score more similar under cosine similarity than
    unrelated texts, which is enough for development/tests exercising the
    retrieval pipeline's plumbing without a real embedding API key."""

    def __init__(self, dimensions: int = 64):
        if dimensions <= 0:
            raise ValueError("dimensions phai duong")
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> List[float]:
        vector = [0.0] * self._dimensions
        normalized = (text or "").lower()
        for i in range(len(normalized) - 2):
            trigram = normalized[i:i + 3]
            vector[_stable_trigram_index(trigram, self._dimensions)] += 1.0
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0.0:
            vector = [x / norm for x in vector]
        return vector
