"""
Deterministic chunking / embedding-ready index — Fanfic AI Chat V1 Phase 4.

Builds `ChunkRecord`s carrying every field the mission requires
(novel_id/chapter_id/chapter_index/source identity/language/chunk order/
content hash+version) from EITHER this repo's own native `Chapter.content`
(author-uploaded, the majority of real content) OR a Story-Harvester-V5
`NormalizedChapter.clean_text` (scraped content) - both are just "a
chapter's clean text plus some identifying metadata" from this module's
point of view, so one function serves both.

Reuses `server.scraper.universal.semantic.chunk_text` (V5 Phase 12) for the
actual sliding-window boundaries and `server.scraper.dedupe.content_hash`
for hashing - neither is reimplemented here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from server.scraper.dedupe import content_hash as compute_content_hash
from server.scraper.universal.semantic import (
    DEFAULT_CHUNK_CHARS, DEFAULT_CHUNK_OVERLAP_CHARS, chunk_text,
)

#: Bumped whenever the CHUNKING STRATEGY itself changes (window size,
#: overlap, boundary algorithm) - independent of content_hash (which
#: tracks the SOURCE TEXT changing). A vector store row's real staleness
#: check is "either of these changed", see `needs_reembedding`.
CHUNKING_VERSION = 1


@dataclass(frozen=True)
class ChunkRecord:
    novel_id: str
    chapter_id: str
    #: See `domain.UserReadingContext.current_chapter_index`'s docstring -
    #: same chat-domain concept, mapped from `Chapter.order_index` (native
    #: content) or `NormalizedChapter.chapter_number` (scraped content) by
    #: the caller building this record.
    chapter_index: int
    chapter_title: str
    chunk_order: int
    chunk_text: str
    #: sha256 of the FULL chapter's clean text - the staleness signal:
    #: unchanged means this chunk's embedding is still valid, avoiding
    #: re-embedding content that hasn't changed.
    content_hash: str
    #: sha256 of THIS chunk's own text - a stable per-chunk identity for a
    #: vector store row, independent of `content_hash` (which is
    #: chapter-wide) since two different chapters could coincidentally
    #: share a full-text hash under adversarial input but chunk-level
    #: identity should still be unique per chunk in practice.
    chunk_hash: str
    chunking_version: int = CHUNKING_VERSION
    language: str = ""
    #: `CanonicalIdentity.identity_key()` (V5 `universal.identity`) when
    #: this chapter came from a scraped source - empty for native content,
    #: which has no cross-source identity concept.
    source_identity_key: str = ""


def build_chunk_records(
        *, novel_id: str, chapter_id: str, chapter_index: int, chapter_title: str,
        clean_text: str, language: str = "", source_identity_key: str = "",
        max_chunk_chars: int = DEFAULT_CHUNK_CHARS,
        chunk_overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS) -> List[ChunkRecord]:
    if not clean_text:
        return []
    full_hash = compute_content_hash(clean_text)
    boundaries = chunk_text(clean_text, max_chars=max_chunk_chars, overlap_chars=chunk_overlap_chars)
    records = []
    for order, boundary in enumerate(boundaries):
        piece = clean_text[boundary.start_char:boundary.end_char]
        records.append(ChunkRecord(
            novel_id=novel_id, chapter_id=chapter_id, chapter_index=chapter_index,
            chapter_title=chapter_title, chunk_order=order, chunk_text=piece,
            content_hash=full_hash, chunk_hash=compute_content_hash(piece),
            language=language, source_identity_key=source_identity_key))
    return records


def needs_reembedding(
        *, stored_content_hash: Optional[str], stored_chunking_version: Optional[int],
        current_content_hash: str, current_chunking_version: int = CHUNKING_VERSION) -> bool:
    """True when a chapter has never been embedded (`stored_content_hash`
    is None) OR its text changed OR the chunking strategy itself changed
    since it was last embedded - false only when both match exactly."""
    if stored_content_hash is None or stored_chunking_version is None:
        return True
    return (stored_content_hash != current_content_hash
           or stored_chunking_version != current_chunking_version)
