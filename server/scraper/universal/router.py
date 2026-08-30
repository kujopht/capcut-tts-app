"""
Acquisition Router — Story Harvester V5 Phase 2.

Tiered acquisition: Tier 1 (direct HTTP, real, always available - reuses
the EXISTING `HttpFetcher`, so every SSRF/robots.txt/response-size/redirect
protection already proven in `http_fetcher.py` applies here for free, not
reimplemented) then Tier 2 (browser rendering) then Tier 3 (structured/
network intelligence) as PLUGIN hooks. No paid service is mandatory: a
router with zero plugins registered is a fully supported configuration
(Tier-1-only), matching this repo's actual current dependencies.

Strategy selection uses simple, transparent history: the last tier that
worked for a given host is preferred next time, avoiding a repeat Tier-1
failure when a plugin is known to work for that host - mirrors the
existing "learn from history" precedent in `site_profile.py` (a per-host
learned fact persisted by the CALLER, not by this module - this module is
pure/in-memory, matching `harvest_scheduler.py`'s own "foundation-only, no
I/O" boundary).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence

from server.scraper.contract import domain_of
from server.scraper.http_fetcher import FetchError, HttpFetcher
from server.scraper.universal.acquisition import (
    AcquisitionError, AcquisitionMethod, AcquisitionResult, AcquisitionStatus,
    SourceClass,
)


class AcquisitionTier(Enum):
    TIER1_DIRECT_HTTP = 1
    TIER2_BROWSER = 2
    TIER3_STRUCTURED = 3


class AcquisitionPlugin(ABC):
    """A Tier-2/Tier-3 strategy - Firecrawl, Bright Data, Crawl4AI, or a
    provider-specific API are all expected to be one of these. NONE are
    implemented in this repo (no such dependency/credential exists here) -
    this ABC is the seam a future adapter plugs into without touching the
    router's core selection logic."""

    tier: AcquisitionTier
    name: str

    @abstractmethod
    def available(self) -> bool:
        """Cheap check - is this plugin actually usable right now (binary
        installed, credential present, service reachable)? Never assume
        yes just because the plugin is registered."""

    @abstractmethod
    def acquire(self, url: str, *,
               source_hint: SourceClass = SourceClass.UNKNOWN) -> AcquisitionResult:
        ...


_TIER_ORDER_FROM = {
    AcquisitionTier.TIER1_DIRECT_HTTP: (
        AcquisitionTier.TIER1_DIRECT_HTTP, AcquisitionTier.TIER2_BROWSER,
        AcquisitionTier.TIER3_STRUCTURED),
    AcquisitionTier.TIER2_BROWSER: (
        AcquisitionTier.TIER2_BROWSER, AcquisitionTier.TIER1_DIRECT_HTTP,
        AcquisitionTier.TIER3_STRUCTURED),
    AcquisitionTier.TIER3_STRUCTURED: (
        AcquisitionTier.TIER3_STRUCTURED, AcquisitionTier.TIER1_DIRECT_HTTP,
        AcquisitionTier.TIER2_BROWSER),
}

_TIER_TO_METHOD = {
    AcquisitionTier.TIER1_DIRECT_HTTP: AcquisitionMethod.DIRECT_HTTP,
    AcquisitionTier.TIER2_BROWSER: AcquisitionMethod.BROWSER_RENDER,
    AcquisitionTier.TIER3_STRUCTURED: AcquisitionMethod.STRUCTURED_API,
}


@dataclass
class AcquisitionRouter:
    http_fetcher: HttpFetcher = field(default_factory=HttpFetcher)
    plugins: Sequence[AcquisitionPlugin] = field(default_factory=tuple)
    #: host -> last tier that SUCCEEDED for that host. In-memory only -
    #: a caller wanting this to survive a process restart persists it
    #: externally (e.g. alongside `site_profile.py`'s learned profiles),
    #: this module never writes to disk itself.
    _history: Dict[str, AcquisitionTier] = field(default_factory=dict, repr=False)

    def preferred_tier(self, url: str) -> AcquisitionTier:
        return self._history.get(domain_of(url), AcquisitionTier.TIER1_DIRECT_HTTP)

    def record_observation(self, url: str, tier: AcquisitionTier, *, success: bool) -> None:
        if success:
            self._history[domain_of(url)] = tier

    def _plugins_for(self, tier: AcquisitionTier) -> List[AcquisitionPlugin]:
        return [p for p in self.plugins if p.tier == tier and p.available()]

    def _acquire_tier1(self, url: str, source_hint: SourceClass) -> AcquisitionResult:
        try:
            fetched = self.http_fetcher.fetch(url)
        except FetchError as exc:
            return AcquisitionResult(
                final_url=url, source_type=source_hint,
                status=AcquisitionStatus.FAILED,
                acquisition_method=AcquisitionMethod.DIRECT_HTTP,
                errors=[AcquisitionError(stage="fetch", message=str(exc)[:500])])
        status = (AcquisitionStatus.NOT_MODIFIED if fetched.not_modified
                 else AcquisitionStatus.OK)
        return AcquisitionResult(
            final_url=fetched.final_url, source_type=source_hint, status=status,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            content_type=fetched.content_type,
            html=fetched.text if "html" in fetched.content_type.lower() or not fetched.content_type else None,
            text_markdown=None,
            metadata={"etag": fetched.etag, "last_modified": fetched.last_modified},
            provenance="AcquisitionRouter/tier1_direct_http")

    def acquire(self, url: str, *,
               source_hint: SourceClass = SourceClass.UNKNOWN) -> AcquisitionResult:
        order = _TIER_ORDER_FROM[self.preferred_tier(url)]
        last_result: Optional[AcquisitionResult] = None
        tried: List[AcquisitionTier] = []
        for tier in order:
            if tier == AcquisitionTier.TIER1_DIRECT_HTTP:
                result = self._acquire_tier1(url, source_hint)
                tried.append(tier)
            else:
                plugins = self._plugins_for(tier)
                if not plugins:
                    continue
                result = plugins[0].acquire(url, source_hint=source_hint)
                tried.append(tier)
            if result.ok:
                self.record_observation(url, tier, success=True)
                return result
            last_result = result

        if last_result is not None:
            return last_result
        return AcquisitionResult(
            final_url=url, source_type=source_hint, status=AcquisitionStatus.FAILED,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            errors=[AcquisitionError(
                stage="route", recoverable=False,
                message="Khong co tang acquisition nao kha dung (khong plugin "
                       "Tier-2/Tier-3 nao duoc dang ky va Tier-1 that bai).")])
