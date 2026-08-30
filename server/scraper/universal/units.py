"""
Normalized content units — Story Harvester V5 Phase 10.

Fiction's normalized units already exist and are NOT redefined here:
Story == `contract.SeriesInfo`, Chapter == `contract.NormalizedChapter`.
This module adds the remaining unit families the mission asks for
(video/document/feed), each carrying an optional `RawEvidence` pointer
back to the `AcquisitionResult` it was derived from - raw acquisition
evidence (html/structured_json) stays OUT of these dataclasses so
normalized entities remain small and independently serializable/archivable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from server.scraper.universal.acquisition import AcquisitionMethod


@dataclass(frozen=True)
class RawEvidence:
    """Pointer back to the acquisition a normalized unit was derived from -
    intentionally NOT the full `AcquisitionResult` (which may carry a lot
    of html/structured_json); just enough to trace provenance."""

    acquisition_method: AcquisitionMethod
    final_url: str
    provenance: str = ""


@dataclass
class Video:
    platform: str
    video_id: str
    canonical_url: str
    channel_id: str = ""
    title: str = ""
    description: str = ""
    upload_time: Optional[str] = None
    duration_seconds: Optional[float] = None
    thumbnail_url: str = ""
    playlist_id: Optional[str] = None
    evidence: Optional[RawEvidence] = None


@dataclass
class VideoChapter:
    video_id: str
    title: str
    start_seconds: float
    end_seconds: Optional[float] = None


@dataclass
class TranscriptSegment:
    video_id: str
    text: str
    start_seconds: float
    end_seconds: Optional[float] = None
    language: str = ""


@dataclass
class Document:
    source_url: str
    title: str = ""
    content_type: str = ""
    evidence: Optional[RawEvidence] = None


@dataclass
class DocumentSection:
    document_id: str
    order: int
    heading: str = ""
    text: str = ""


@dataclass
class Feed:
    source_url: str
    canonical_url: str
    title: str = ""
    evidence: Optional[RawEvidence] = None


@dataclass
class FeedItem:
    feed_id: str
    guid: str
    title: str = ""
    link: str = ""
    published_at: Optional[str] = None
    summary: str = ""
