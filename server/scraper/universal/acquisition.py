"""
Universal Acquisition Contract — Story Harvester V5 Phase 1.

`AcquisitionResult` is the ONE result shape every source class returns,
regardless of how different their content actually is: a fiction chapter is
HTML, a YouTube video is JSON metadata + no HTML at all, an RSS feed is XML
turned into structured_json, an unknown page might only yield a fingerprint.
Every field below is OPTIONAL except the ones that make sense for literally
any source (final_url/source_type/status/method) — do not force every
source into HTML, per the mission brief.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SourceClass(Enum):
    """Kind of source being acquired — drives which adapter/tier applies."""

    WEB_FICTION = "web_fiction"
    GENERIC_WEB = "generic_web"
    YOUTUBE = "youtube"
    VIDEO_PLATFORM = "video_platform"
    RSS_FEED = "rss_feed"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class AcquisitionMethod(Enum):
    """Which acquisition tier actually produced this result — see
    `router.py` for the full T0-T5 tier ladder this enum names.

    `NETWORK_OBSERVED`/`DOCUMENT` them o Universal Acquisition Engine
    Hardening (2026-08-31) cho T3/T4 — CO CHU Y KHONG doi ten 4 gia tri cu:
    `STRUCTURED_API` da duoc adapter THAT dung (YouTube oEmbed, Bilibili
    view-info), doi ten se pha vo ca adapter lan test da xanh. `PLUGIN` van
    la gia tri T5 (Optional Managed Provider) — T5 CHINH LA "provider quan
    ly ben ngoai qua plugin", khong can mot ten rieng thu 7."""

    DIRECT_HTTP = "direct_http"
    BROWSER_RENDER = "browser_render"
    STRUCTURED_API = "structured_api"
    PLUGIN = "plugin"
    NETWORK_OBSERVED = "network_observed"
    DOCUMENT = "document"


class AcquisitionStatus(Enum):
    OK = "ok"
    NOT_MODIFIED = "not_modified"
    FAILED = "failed"
    #: robots.txt disallow, SSRF-unsafe target, or another deliberate
    #: policy refusal — distinct from FAILED (a plain network/parse error)
    #: so callers don't blindly retry a source that will never be allowed.
    BLOCKED = "blocked"
    #: Acquisition partially succeeded (e.g. metadata but not full body) —
    #: callers should inspect `errors` for what's missing.
    PARTIAL = "partial"


@dataclass(frozen=True)
class NetworkEndpointCandidate:
    """A JSON/XHR/GraphQL endpoint OBSERVED while acquiring a page — a
    candidate only. Nothing in this module trusts it; see
    `network_intelligence.py` for the validation gate before any candidate
    is allowed to influence future acquisition."""

    url: str
    method: str = "GET"
    content_type: str = ""
    #: e.g. "xhr", "fetch", "graphql", "script_tag_json" — how it was found.
    discovered_via: str = ""
    response_size_bytes: int = 0


@dataclass(frozen=True)
class AcquisitionError:
    #: Which stage produced this — "fetch"/"parse"/"extract"/"validate" —
    #: lets a caller distinguish a network problem from a content problem.
    stage: str
    message: str
    recoverable: bool = True


@dataclass
class AcquisitionResult:
    """The one result shape every source class returns. Optional fields
    default to empty/None — a caller must never assume `html` or
    `structured_json` is populated just because acquisition succeeded."""

    final_url: str
    source_type: SourceClass
    status: AcquisitionStatus
    acquisition_method: AcquisitionMethod
    content_type: str = ""
    html: Optional[str] = None
    structured_json: Optional[Any] = None
    text_markdown: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    links: List[str] = field(default_factory=list)
    media_references: List[str] = field(default_factory=list)
    network_endpoints: List[NetworkEndpointCandidate] = field(default_factory=list)
    #: Free-text trail of WHAT acquired this — adapter name, tier, version —
    #: for debugging/telemetry, not a machine-parsed field.
    provenance: str = ""
    duration_seconds: float = 0.0
    errors: List[AcquisitionError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in (AcquisitionStatus.OK, AcquisitionStatus.NOT_MODIFIED)
