"""
External Content Import Contract v1 for Fanfic World.

Standardized, crawler-independent, deterministic contract for importing:
1. Fanfic / Tiểu thuyết
2. Sách (Books)
3. Chapter audio attachments

Design Principles:
- Scraper-independent: Any external crawler can serialize to this schema.
- Deterministic: Stable fingerprints and IDs prevent duplicates and support resume.
- Validate-first: Strict validation before any database mutation.
- Non-empty guarantee: Must never create a novel/book with zero valid chapters.
- Reader-safe: Automatically strips internal technical tags (e.g. work:*, imported, long_form_audio).
- High capacity: Supports large works with hundreds of chapters.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, Field, field_validator, model_validator


class ContentType(str, Enum):
    """Supported product content types."""
    FANFIC = "fanfic"
    BOOK = "book"
    NOVEL = "novel"          # General fiction (not tied to anime fandom)


class WorkStatus(str, Enum):
    """Release status of the work."""
    ONGOING = "ongoing"
    COMPLETED = "completed"
    HIATUS = "hiatus"


class PublicationMode(str, Enum):
    """Publication mode in Fanfic World."""
    FULL_TEXT = "full_text"
    METADATA_ONLY = "metadata_only"


# Internal technical tags that must NEVER leak to reader-facing UI
_INTERNAL_TAG_PREFIXES = ("work:", "work-", "temp:", "internal:", "job:")
_INTERNAL_TAG_EXACT = {
    "imported", "long_form_audio", "unresolved", "fandom_unresolved",
    "da_fandom_unresolved", "scraper_raw", "crawler_v1", "batch_import"
}


def is_internal_tag(tag: str) -> bool:
    """Check if a tag is an internal technical/pipeline tag."""
    if not tag:
        return True
    lower = tag.lower().strip()
    if any(lower.startswith(p) for p in _INTERNAL_TAG_PREFIXES):
        return True
    if lower in _INTERNAL_TAG_EXACT:
        return True
    if "unresolved" in lower:
        return True
    return False


def clean_reader_tags(raw_tags: List[str]) -> Tuple[List[str], List[str]]:
    """
    Split tags into (sanitized_reader_tags, rejected_internal_tags).
    Strips duplicates case-insensitively, normalizes whitespace.
    """
    reader_tags: List[str] = []
    rejected_tags: List[str] = []
    seen: set[str] = set()

    for tag in raw_tags or []:
        if not tag:
            continue
        cleaned = " ".join(str(tag).strip().split())
        if not cleaned:
            continue
        lower = cleaned.lower()
        if is_internal_tag(cleaned):
            if lower not in seen:
                rejected_tags.append(cleaned)
                seen.add(lower)
            continue
        if lower not in seen:
            # Enforce 64 char max to match Appwrite schema
            reader_tags.append(cleaned[:64])
            seen.add(lower)

    return reader_tags, rejected_tags


def canonicalize_url(url: str) -> str:
    """
    Normalize URL for deterministic comparison and deduplication:
    strips tracking params, trailing slash, lowercases host.
    """
    if not url or not url.strip():
        return ""
    raw = url.strip()
    if "://" not in raw and not raw.startswith("//"):
        raw = f"https://{raw}"

    parts = urlsplit(raw)
    scheme = (parts.scheme or "https").lower()
    netloc = (parts.netloc or "").lower()
    if ":" in netloc:
        host, port = netloc.split(":", 1)
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host

    path = re.sub(r"/+", "/", parts.path or "")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    # Filter tracking params
    tracking_prefixes = ("utm_",)
    tracking_exact = {"fbclid", "gclid", "ref", "referrer", "spm", "si", "igshid"}
    filtered_queries = []
    for k, v in parse_qsl(parts.query or "", keep_blank_values=True):
        kl = k.lower()
        if kl in tracking_exact or any(kl.startswith(p) for p in tracking_prefixes):
            continue
        filtered_queries.append((k, v))

    filtered_queries.sort(key=lambda x: x[0])
    query = urlencode(filtered_queries)
    return urlunsplit((scheme, netloc, path, query, ""))


def compute_work_fingerprint(
    content_type: str,
    title: str,
    author: Optional[str] = None,
    source_url: Optional[str] = None,
    source_id: Optional[str] = None,
    language: str = "vi"
) -> str:
    """
    Compute a deterministic 24-character hex fingerprint for the work.
    Used for duplicate detection and idempotent novel_id generation.
    """
    canon_url = canonicalize_url(source_url or "")
    norm_title = " ".join(unicodedata.normalize("NFKD", title or "").lower().split())
    norm_author = " ".join(unicodedata.normalize("NFKD", author or "").lower().split())
    norm_lang = (language or "vi").lower().strip()

    if canon_url:
        payload = f"url:{canon_url}"
    elif source_id and source_id.strip():
        payload = f"src:{source_id.strip()}:{content_type}:{norm_lang}"
    else:
        payload = f"meta:{content_type}:{norm_title}:{norm_author}:{norm_lang}"

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


class ExternalCover(BaseModel):
    """Cover image specification for external import."""
    url: Optional[str] = Field(default=None, description="Direct public HTTP URL of cover image")
    base64: Optional[str] = Field(default=None, description="Raw base64-encoded image data")
    mime: Optional[str] = Field(default="image/jpeg", description="MIME type e.g. image/jpeg, image/png, image/webp")
    key: Optional[str] = Field(default=None, description="Pre-existing R2/S3 object key if already uploaded")


class ExternalAudio(BaseModel):
    """Audio attachment for a chapter."""
    url: Optional[str] = Field(default=None, description="Direct audio URL (MP3/M4A) to download or link")
    base64: Optional[str] = Field(default=None, description="Direct base64 audio payload (for short audio)")
    key: Optional[str] = Field(default=None, description="Pre-existing R2/S3 object key if already uploaded")
    duration_seconds: Optional[float] = Field(default=0.0, ge=0.0, description="Audio duration in seconds")
    size_bytes: Optional[int] = Field(default=0, ge=0, description="Audio file size in bytes")
    voice_name: Optional[str] = Field(default="external", description="Voice or narrator identifier")


class ExternalChapter(BaseModel):
    """A single chapter in the external import contract."""
    order: int = Field(default=1, ge=1, description="1-based chapter order sequence")
    title: str = Field(..., min_length=1, max_length=200, description="Chapter title")
    content: str = Field(..., min_length=10, description="Clean chapter body text/markdown")
    source_chapter_id: Optional[str] = Field(default=None, max_length=128, description="Original chapter ID on source site")
    audio: Optional[ExternalAudio] = Field(default=None, description="Optional audio track attached to this chapter")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Chapter title cannot be empty or blank")
        return s

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 10:
            raise ValueError("Chapter content must contain at least 10 non-whitespace characters")
        return s


class ExternalWorkImport(BaseModel):
    """
    Top-level External Content Import Contract v1.
    Represents a complete work (Fanfic, Book, or Novel) with chapters and metadata.
    """
    content_type: ContentType = Field(default=ContentType.FANFIC, description="'fanfic', 'book', or 'novel'")
    source_id: Optional[str] = Field(default=None, max_length=128, description="Source-specific ID from external crawler")
    source_url: Optional[str] = Field(default=None, max_length=1000, description="Canonical source URL of the work")
    title: str = Field(..., min_length=1, max_length=200, description="Work title")
    author: Optional[str] = Field(default=None, max_length=200, description="Original author name")
    description: Optional[str] = Field(default="", max_length=4000, description="Synopsis or description")
    cover: Optional[ExternalCover] = Field(default=None, description="Optional cover image")
    language: str = Field(default="vi", max_length=16, description="Language code (default 'vi')")
    status: WorkStatus = Field(default=WorkStatus.ONGOING, description="'ongoing', 'completed', or 'hiatus'")
    publication_mode: PublicationMode = Field(default=PublicationMode.FULL_TEXT, description="'full_text' or 'metadata_only'")
    tags: List[str] = Field(default_factory=list, description="Reader-facing genre or topic tags")
    fandom: Optional[str] = Field(default=None, max_length=128, description="Primary fandom name (for fanfics)")
    fandoms: List[str] = Field(default_factory=list, description="Multiple fandom names (for crossovers)")
    characters: List[str] = Field(default_factory=list, description="Featured characters")
    pairings: List[str] = Field(default_factory=list, description="Character pairings/relationships")
    chapters: List[ExternalChapter] = Field(..., min_length=1, description="List of chapters (must have >= 1)")
    rejected_tags: List[str] = Field(default_factory=list, description="Rejected technical tags that were stripped")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Work title cannot be empty or whitespace")
        return s

    @model_validator(mode="after")
    def validate_work_and_chapters(self) -> ExternalWorkImport:
        # 1. Non-empty chapter guarantee
        if not self.chapters:
            raise ValueError("Work must contain at least 1 valid chapter")

        # 2. Normalize and preserve chapter order
        seen_orders: set[int] = set()
        has_duplicates = False
        for c in self.chapters:
            if c.order in seen_orders:
                has_duplicates = True
                break
            seen_orders.add(c.order)

        # If duplicate orders exist or unindexed, re-sequence consecutively 1..N
        if has_duplicates or sorted(seen_orders) != list(range(1, len(self.chapters) + 1)):
            for idx, ch in enumerate(self.chapters, start=1):
                ch.order = idx

        # 3. Content-type specific taxonomy adjustments
        clean_tags, rejected = clean_reader_tags(self.tags)
        self.rejected_tags = rejected
        if self.content_type == ContentType.BOOK:
            if "Sách" not in clean_tags:
                clean_tags.insert(0, "Sách")
        elif self.content_type == ContentType.FANFIC:
            if "Fanfic" not in clean_tags:
                clean_tags.insert(0, "Fanfic")
        self.tags = clean_tags

        # 4. Consolidate fandom into fandoms list
        if self.fandom and self.fandom.strip():
            f_norm = self.fandom.strip()
            if f_norm not in self.fandoms:
                self.fandoms.insert(0, f_norm)

        return self

    def get_fingerprint(self) -> str:
        """Compute the deterministic 24-char fingerprint for this work."""
        return compute_work_fingerprint(
            content_type=self.content_type.value,
            title=self.title,
            author=self.author,
            source_url=self.source_url,
            source_id=self.source_id,
            language=self.language
        )
