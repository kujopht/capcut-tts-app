"""
Generic video-platform adapter marker — Story Harvester V5.

`SourceAdapter` is the ONE contract every source adapter implements (see
`adapter.py`). This module exists so every video-platform adapter (Bilibili
today, more later) shares a single marker base that defaults its
`source_class` to `SourceClass.VIDEO_PLATFORM`. Concrete platform adapters
may override the class default (e.g. a YouTube adapter wants
`SourceClass.YOUTUBE`).

Intentionally small: it adds the one class-level default and nothing else —
no extra abstraction, no shared logic. Concrete adapters implement every
abstract `SourceAdapter` method themselves.
"""
from __future__ import annotations

from server.scraper.universal.acquisition import SourceClass
from server.scraper.universal.adapter import SourceAdapter


class VideoPlatformAdapter(SourceAdapter):
    """Marker base for any adapter that acquires a unit from a generic
    video platform. Defaults `source_class` to VIDEO_PLATFORM; individual
    platforms may override it."""

    source_class: SourceClass = SourceClass.VIDEO_PLATFORM
