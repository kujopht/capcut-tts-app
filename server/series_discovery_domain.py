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
class ChannelDiscoveryGroup:
    """
    Auto-Ingestion Phase 5 ("Multi-Series Channel Ingestion") — MOT cum ung
    vien suy doan la CUNG mot series trong luc kham pha TOAN nguon (kenh/
    playlist), khac voi `SeriesDiscoveryCandidate` (Phase 1) von chi so
    sanh tung ung vien voi MOT seed. Bao cao truoc/sau khi thuc thi de
    quan tri xem lai qua trinh gom nhom co hop ly khong.
    """

    canonical_name: str
    representative_video_id: str
    video_ids: List[str] = field(default_factory=list)
    series_id: str = ""
    mapping_id: str = ""
    created_new_series: bool = False
    matched_existing_series: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "representative_video_id": self.representative_video_id,
            "video_ids": list(self.video_ids),
            "video_count": len(self.video_ids),
            "series_id": self.series_id,
            "mapping_id": self.mapping_id,
            "created_new_series": self.created_new_series,
            "matched_existing_series": self.matched_existing_series,
        }


@dataclass
class ChannelDiscoveryResult:
    """
    Bao cao TOAN BO mot lan `discover_channel` (Phase 5) — kham pha BOUNDED
    mot nguon kieu kenh/playlist, gom nhieu series cung luc thay vi MOT seed
    quan tri chon san (khac `SeriesDiscoveryResult` cua Phase 1).

    `confident_imports`/`pending_review`/`duplicates`/`excluded`/`conflicts`:
    CUNG TEN truong voi `SeriesDiscoveryResult` CO CHU DICH —
    `TrustedSourceService._xu_ly_mot_video_discovery` (dung chung boi ca
    Phase 1 lan Phase 5) ghi thang vao NAM danh sach nay bang duck-typing,
    khong can biet dang goi no la loai ket qua nao — MOT duong ghi duy nhat
    cho ca hai luong kham pha.
    """

    source_id: str
    videos_discovered: int = 0
    #: Video da co MOT quyet dinh quan tri truoc do (khac NEW) — "existing
    #: admin decisions must win", KHONG dua vao gom nhom/phan loai lai.
    already_tracked: int = 0
    #: Video khop THANG mot SeriesMapping da co (qua alias/tu khoa) ngay tu
    #: buoc phan loai dau tien — KHONG can gom cum, xem `discover_channel`.
    matched_existing_mapping: int = 0
    candidate_groups: int = 0
    new_series_created: int = 0
    existing_series_reused_by_fingerprint: int = 0
    confident_imports: List[str] = field(default_factory=list)
    pending_review: List[str] = field(default_factory=list)
    duplicates: List[str] = field(default_factory=list)
    excluded: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    #: Tieu de khop mot tu khoa AM mac dinh (trailer/OST/...) NGAY TRUOC buoc
    #: gom nhom — bi loai HOAN TOAN khoi cum, KHONG tao VideoImport (cung
    #: nguyen tac "khong nhap tran lan ca kenh" voi Phase 1). Rieng voi
    #: `excluded` o tren (loai boi CHINH pipeline nhap sau khi da vao mot
    #: cum/mapping — vi du khop exclude_keywords cua mapping).
    excluded_negative_keyword: int = 0
    internal_errors: int = 0
    groups: List[ChannelDiscoveryGroup] = field(default_factory=list)
    next_page_token: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "videos_discovered": self.videos_discovered,
            "already_tracked": self.already_tracked,
            "matched_existing_mapping": self.matched_existing_mapping,
            "candidate_groups": self.candidate_groups,
            "new_series_created": self.new_series_created,
            "existing_series_reused_by_fingerprint": self.existing_series_reused_by_fingerprint,
            "confident_imports": list(self.confident_imports),
            "pending_review": list(self.pending_review),
            "duplicates": list(self.duplicates),
            "excluded": list(self.excluded),
            "conflicts": list(self.conflicts),
            "excluded_negative_keyword": self.excluded_negative_keyword,
            "internal_errors": self.internal_errors,
            "groups": [g.to_dict() for g in self.groups],
            "next_page_token": self.next_page_token,
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
