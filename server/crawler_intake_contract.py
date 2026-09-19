"""
Crawler Intake Contract v0 — Upstream Raw Content Boundary.

This contract defines the strict Pydantic models for RAW crawler payloads
ingested from completely independent external crawlers.

Guarantees & Constraints:
- Scraper-independent: No scraper implementation in this repo.
- JSON serializable and strictly validated.
- Computes deterministic source text hashes.
- Normalizes URLs and language hints.
- No audio is required or allowed at crawler intake.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, Field, field_validator, model_validator


def _normalize_whitespace(text: str) -> str:
    """Normalize runs of whitespace to a single space and strip."""
    return re.sub(r"\s+", " ", (text or "").strip())


def compute_source_text_hash(text: str) -> str:
    """Deterministic SHA-256 of whitespace-normalized source text."""
    norm = _normalize_whitespace(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def canonicalize_url(url: str) -> str:
    """Normalize URL: strip tracking parameters, lower hostname, strip trailing slash."""
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

    tracking_prefixes = ("utm_",)
    tracking_exact = {"fbclid", "gclid", "ref", "referrer", "spm", "si", "igshid"}
    filtered = []
    for k, v in parse_qsl(parts.query or "", keep_blank_values=True):
        kl = k.lower()
        if kl in tracking_exact or any(kl.startswith(p) for p in tracking_prefixes):
            continue
        filtered.append((k, v))

    filtered.sort(key=lambda x: x[0])
    query = urlencode(filtered)
    return urlunsplit((scheme, netloc, path, query, ""))


def detect_script_language(text: str) -> str:
    """
    Lightweight script-range language detector (CJK -> zh/ja/ko, Latin -> en/vi).
    """
    s = (text or "").strip()
    if len(s) < 6:
        return "unknown"

    cjk = 0
    hiragana = 0
    katakana = 0
    hangul = 0
    latin = 0
    vietnamese_specific = 0
    total_alpha = 0

    for ch in s:
        cp = ord(ch)
        if (0x1EA0 <= cp <= 0x1EF9) or cp in (0x0110, 0x0111):
            vietnamese_specific += 1
            latin += 1
            total_alpha += 1
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("L"):
            total_alpha += 1
        if 0x4E00 <= cp <= 0x9FFF:
            cjk += 1
            total_alpha += 1
        elif 0x3040 <= cp <= 0x309F:
            hiragana += 1
            total_alpha += 1
        elif 0x30A0 <= cp <= 0x30FF:
            katakana += 1
            total_alpha += 1
        elif 0xAC00 <= cp <= 0xD7AF:
            hangul += 1
            total_alpha += 1
        elif cat.startswith("L") and cp < 0x0600:
            latin += 1

    if total_alpha == 0:
        return "unknown"

    kana = hiragana + katakana
    if cjk > 0 and (kana / max(cjk, 1)) >= 0.03:
        return "ja"
    if hangul / max(total_alpha, 1) >= 0.03:
        return "ko"
    if cjk > total_alpha * 0.3:
        return "zh"
    if latin > total_alpha * 0.3 and vietnamese_specific >= 2:
        return "vi"
    if latin > total_alpha * 0.3:
        return "en"
    return "unknown"


class RawCrawlerChapter(BaseModel):
    """A single raw chapter received from the upstream crawler."""
    source_chapter_id: Optional[str] = Field(
        default=None, max_length=128, description="Identifier of chapter on source site"
    )
    source_order: int = Field(
        ..., ge=1, description="1-indexed sequence order of chapter from source"
    )
    source_title: str = Field(
        ..., min_length=1, max_length=255, description="Original chapter title"
    )
    source_text: str = Field(
        ..., min_length=10, description="Raw chapter body text"
    )
    source_text_hash: Optional[str] = Field(
        default=None, description="SHA-256 hash of normalized source text (auto-computed if None)"
    )

    @field_validator("source_title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Chapter title cannot be blank")
        return s

    @field_validator("source_text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 10:
            raise ValueError("Chapter text must be at least 10 characters")
        return s

    @model_validator(mode="after")
    def compute_hash_if_missing(self) -> RawCrawlerChapter:
        if not self.source_text_hash:
            self.source_text_hash = compute_source_text_hash(self.source_text)
        return self


class RawCrawlerWork(BaseModel):
    """
    Top-level upstream raw intake payload representing a scraped fanfic.
    """
    source_id: str = Field(
        ..., min_length=1, max_length=128, description="Source-specific ID from external crawler"
    )
    source_url: str = Field(
        ..., min_length=5, max_length=1000, description="Canonical source URL of the work"
    )
    source_language: str = Field(
        default="auto", max_length=16, description="Source language: 'zh', 'en', 'ja', 'ko', 'auto'"
    )
    title: str = Field(
        ..., min_length=1, max_length=255, description="Raw original work title"
    )
    author: Optional[str] = Field(
        default=None, max_length=200, description="Original author name"
    )
    description: Optional[str] = Field(
        default="", max_length=5000, description="Raw synopsis or description"
    )
    fandom: Optional[str] = Field(
        default=None, max_length=128, description="Primary fandom"
    )
    fandoms: List[str] = Field(
        default_factory=list, description="Fandom list (crossover)"
    )
    tags: List[str] = Field(
        default_factory=list, description="Raw tags from source site"
    )
    cover_url: Optional[str] = Field(
        default=None, max_length=1000, description="Optional raw cover image URL"
    )
    chapters: List[RawCrawlerChapter] = Field(
        ..., min_length=1, description="List of chapters (must have at least 1)"
    )

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        canon = canonicalize_url(v)
        if not canon:
            raise ValueError("source_url must be a valid HTTP/HTTPS URL")
        return canon

    @field_validator("title")
    @classmethod
    def validate_work_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Work title cannot be blank")
        return s

    @model_validator(mode="after")
    def validate_and_detect(self) -> RawCrawlerWork:
        # Guarantee non-empty chapters
        if not self.chapters:
            raise ValueError("Work must contain at least 1 chapter")

        # Auto-detect source language if "auto" or unknown
        if not self.source_language or self.source_language.lower() in ("auto", "unknown", ""):
            sample_text = self.chapters[0].source_text[:2000] if self.chapters else ""
            detected = detect_script_language(sample_text)
            self.source_language = detected if detected != "unknown" else "zh"

        # Consolidate fandom
        if self.fandom and self.fandom.strip():
            fn = self.fandom.strip()
            if fn not in self.fandoms:
                self.fandoms.insert(0, fn)

        # Sort and re-index chapters if necessary
        seen_orders = set()
        duplicate_orders = False
        for ch in self.chapters:
            if ch.source_order in seen_orders:
                duplicate_orders = True
                break
            seen_orders.add(ch.source_order)

        if duplicate_orders:
            for idx, ch in enumerate(self.chapters, start=1):
                ch.source_order = idx

        return self
