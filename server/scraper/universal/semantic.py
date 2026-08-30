"""
Semantic-ready output — Story Harvester V5 Phase 12.

Prepares normalized content for a FUTURE chatbot/RAG system without
building one - no vector database choice is made here (none is clearly
justified yet, per the mission brief). This module only computes the
deterministic, reusable pieces: chunk boundaries, a language tag, and
placeholders for work that genuinely needs a model (summarization, entity
extraction) rather than pure computation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

#: Sliding-window chunk size/overlap defaults - reasonable for a first
#: pass (roughly a paragraph-to-page's worth of characters per chunk);
#: not tuned against any specific embedding model's token limit, since no
#: embedding model has been chosen yet.
DEFAULT_CHUNK_CHARS = 1000
DEFAULT_CHUNK_OVERLAP_CHARS = 100


@dataclass(frozen=True)
class ChunkBoundary:
    start_char: int
    end_char: int


@dataclass(frozen=True)
class TimestampRange:
    """Only meaningful for transcript-derived units - a chunk of a
    document/story has no natural start/end time."""

    start_seconds: float
    end_seconds: float


@dataclass
class SemanticReadyOutput:
    clean_text: str
    language: str = ""
    chunk_boundaries: List[ChunkBoundary] = field(default_factory=list)
    #: `None` = not yet summarized. A real summarizer is a MODEL call, not
    #: pure computation - this module never fabricates a summary, it only
    #: reserves the field so a future summarization step has somewhere to
    #: write its result without changing this shape.
    summary_placeholder: Optional[str] = None
    embedding_ready_text: str = ""
    entity_extraction_input: str = ""
    timestamp_ranges: List[TimestampRange] = field(default_factory=list)


def chunk_text(text: str, *, max_chars: int = DEFAULT_CHUNK_CHARS,
               overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS) -> List[ChunkBoundary]:
    """Pure, deterministic sliding-window chunk boundaries over character
    offsets. Every chunk after the first overlaps the previous one by
    `overlap_chars` (context continuity across a chunk boundary) - the
    LAST chunk is never expanded/duplicated just to hit a full window, it
    simply runs to the end of the text."""
    if max_chars <= 0:
        raise ValueError("max_chars phai duong")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars phai >= 0 va < max_chars")
    if not text:
        return []

    boundaries: List[ChunkBoundary] = []
    start = 0
    length = len(text)
    stride = max_chars - overlap_chars
    while start < length:
        end = min(start + max_chars, length)
        boundaries.append(ChunkBoundary(start_char=start, end_char=end))
        if end == length:
            break
        start += stride
    return boundaries


def build_semantic_ready_output(
        clean_text: str, *, language: str = "",
        timestamp_ranges: Sequence[TimestampRange] = (),
        max_chunk_chars: int = DEFAULT_CHUNK_CHARS,
        chunk_overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS) -> SemanticReadyOutput:
    """`clean_text` is expected to already be boilerplate-free (the output
    of `content_extraction.extract_content_v3` or an adapter's own
    `normalize()`) - this function does not re-clean it. `embedding_ready_text`/
    `entity_extraction_input` default to `clean_text` itself: a real,
    honest starting point, not a placeholder, since `clean_text` genuinely
    is usable input for either today; a future step MAY apply model-
    specific preprocessing without changing this function's contract."""
    return SemanticReadyOutput(
        clean_text=clean_text, language=language,
        chunk_boundaries=chunk_text(
            clean_text, max_chars=max_chunk_chars, overlap_chars=chunk_overlap_chars),
        summary_placeholder=None,
        embedding_ready_text=clean_text,
        entity_extraction_input=clean_text,
        timestamp_ranges=list(timestamp_ranges))
