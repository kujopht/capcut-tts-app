"""
Universal canonical identity — Story Harvester V5 Phase 9.

Reuses `contract.canonicalize_url`/`dedupe.source_fingerprint` for the
URL-alias/tracking-parameter layer (already solved, don't reinvent it).
This module adds the layer ABOVE that: a source-neutral identity shape that
also works for sources with no meaningful URL at all in the traditional
sense (a YouTube video's real identity is its video ID, not its URL - the
same video is reachable via youtube.com/watch, youtu.be, m.youtube.com,
and an embed URL, all different strings after `canonicalize_url`).

Fiction-specific cross-mirror "same work" fuzzy matching (title+author
overlap when there's no shared native ID) already exists and is NOT
duplicated here — see `story_identity.compare_identity`.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from server.scraper.dedupe import source_fingerprint
from server.scraper.universal.acquisition import SourceClass

_TITLE_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — a weak fallback
    signal only, never sufficient alone to merge two identities (mirrors
    `story_identity.py`'s existing rule that title match alone never
    reaches HIGH confidence)."""
    sin = _TITLE_PUNCTUATION.sub(" ", title.lower())
    return _WHITESPACE.sub(" ", sin).strip()


@dataclass(frozen=True)
class CanonicalIdentity:
    """Universal identity of one acquired item (a story, a video, a feed,
    a document) — the shape every source class maps into so dedup logic
    doesn't need to special-case source classes."""

    source_platform: str
    source_type: SourceClass
    #: The platform's OWN stable ID when it has one (YouTube video ID,
    #: Bilibili bvid, an RSS item GUID) — the single most reliable dedup
    #: signal when present, since a platform's own ID essentially never
    #: aliases across URL variants (mobile/desktop/embed/tracking params).
    source_native_id: str = ""
    canonical_url: str = ""
    normalized_title: str = ""
    creator_identity: str = ""
    content_fingerprint: str = ""
    version: int = 1

    def identity_key(self) -> str:
        """Stable dedup key. Prefers `(source_platform, source_native_id)`
        when a real native ID exists - falls back to
        `dedupe.source_fingerprint(canonical_url)` for sources with no
        native ID concept (generic web fiction, unknown sources)."""
        if self.source_native_id:
            raw = f"{self.source_platform}:{self.source_native_id}"
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if not self.canonical_url:
            raise ValueError(
                "CanonicalIdentity can source_native_id HOAC canonical_url "
                "de sinh identity_key - ca hai deu rong.")
        return source_fingerprint(self.canonical_url)


def dedupe_identities(identities):
    """Given an iterable of `CanonicalIdentity`, return the first-seen
    identity per `identity_key()` - pure, order-preserving, no I/O."""
    seen = {}
    for ident in identities:
        key = ident.identity_key()
        if key not in seen:
            seen[key] = ident
    return list(seen.values())
