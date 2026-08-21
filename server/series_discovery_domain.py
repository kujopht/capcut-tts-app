"""
Cau truc du lieu cho Auto-Ingestion Phase 1 ("Seed Video -> Series Discovery
-> Backfill") — xem `server/trusted_source_service.py::discover_series_from_seed`
cho tang dieu phoi dung cac cau truc nay.

Python thuan, cung quy uoc voi `trusted_source_domain.py`/`animation_domain.py`
— khong phu thuoc Appwrite/FastAPI, de test doc lap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from server.episode_parser import EpisodeSpan
from server.series_fingerprint import SeriesFingerprint


@dataclass
class SeriesDiscoveryCandidate:
    """MOT video ung vien xem xet trong luc quet kenh/playlist tim cac tap
    cung series voi seed — buoc trung gian TRUOC khi thanh `VideoImport`
    that (chi cac ung vien "confident" moi duoc dua qua pipeline nhap binh
    thuong, xem `SeriesDiscoveryResult`)."""

    video_id: str
    title: str
    channel_id: str
    channel_title: str
    published_at: str
    duration_seconds: float
    fingerprint: SeriesFingerprint
    span: Optional[EpisodeSpan]
    #: Do tuong dong fingerprint voi seed — [0.0, 1.0], xem
    #: `series_fingerprint.similarity`.
    similarity_to_seed: float
    #: True neu bi tu khoa loai tru mac dinh (trailer/OST/...) khop — khong
    #: bao gio dua vao cum, bat ke similarity cao the nao.
    excluded: bool = False
    exclude_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "channel_id": self.channel_id,
            "channel_title": self.channel_title,
            "published_at": self.published_at,
            "duration_seconds": self.duration_seconds,
            "canonical_name": self.fingerprint.canonical_name,
            "span_kind": self.span.kind.value if self.span else None,
            "episode_number": (
                self.span.start if self.span and self.span.is_single else None),
            "similarity_to_seed": self.similarity_to_seed,
            "excluded": self.excluded,
            "exclude_reason": self.exclude_reason,
        }


@dataclass
class ExistingSeriesResolution:
    """Ket qua buoc "existing-series resolver": video seed co khop mot
    series DA CO cua trusted source nay hay khong."""

    matched: bool
    series_id: str = ""
    mapping_id: str = ""
    confidence: float = 0.0
    signals: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched": self.matched,
            "series_id": self.series_id,
            "mapping_id": self.mapping_id,
            "confidence": self.confidence,
            "signals": list(self.signals),
        }


@dataclass
class SeriesDiscoveryResult:
    """Bao cao TOAN BO mot lan `discover_series_from_seed` — tra ve cho
    route quan tri VA hien tren UI (tom tat series suy ra, quyet dinh cu/moi,
    video tim duoc, tap/dai tap tim duoc, so nhap tin cay, cho duyet, trung
    lap, xung dot/loai tru)."""

    seed_video_id: str
    resolution: ExistingSeriesResolution
    series_id: str = ""
    mapping_id: str = ""
    created_new_series: bool = False
    candidates_scanned: int = 0
    confident_imports: List[str] = field(default_factory=list)
    pending_review: List[str] = field(default_factory=list)
    duplicates: List[str] = field(default_factory=list)
    excluded: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    candidates: List[SeriesDiscoveryCandidate] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seed_video_id": self.seed_video_id,
            "resolution": self.resolution.to_dict(),
            "series_id": self.series_id,
            "mapping_id": self.mapping_id,
            "created_new_series": self.created_new_series,
            "candidates_scanned": self.candidates_scanned,
            "confident_imports": list(self.confident_imports),
            "pending_review": list(self.pending_review),
            "duplicates": list(self.duplicates),
            "excluded": list(self.excluded),
            "conflicts": list(self.conflicts),
            "candidates": [c.to_dict() for c in self.candidates],
        }
