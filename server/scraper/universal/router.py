"""
Acquisition Router — Universal Acquisition Engine (Story Harvester V5 Phase 2,
hardened 2026-08-31 into the full T0-T5 ladder).

Escalation order is CHEAPEST-FIRST: T0 direct HTTP (reuses the EXISTING
`HttpFetcher`, so every SSRF/robots.txt/response-size/redirect protection
already proven in `http_fetcher.py` applies here for free, not
reimplemented), then T1 structured data (JSON-LD/embedded JSON/RSS/
sitemap/documented APIs — cheap, no browser needed), then T2 browser
rendering, then T3 observing the public network requests a normal page
already makes, then T4 documents (PDF/OCR), then T5 an optional managed
provider (Firecrawl/Bright Data/Crawl4AI-shaped external service) as a
LAST resort. T1-T5 are PLUGIN hooks (`AcquisitionPlugin`) — a router with
zero plugins registered is a fully supported configuration (T0-only),
matching this repo's actual current dependencies (no Playwright, no PDF
library, no managed-provider credential exists here today; adding any of
those is a real, explicit dependency decision, not made by this module).

Strategy selection uses simple, transparent history: the last tier that
worked for a given host is preferred next time, avoiding a repeat T0
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
from typing import Dict, List, Optional, Sequence, Tuple

from server.scraper.contract import domain_of
from server.scraper.http_fetcher import FetchError, HttpFetcher
from server.scraper.universal.acquisition import (
    AcquisitionError, AcquisitionMethod, AcquisitionResult, AcquisitionStatus,
    SourceClass,
)


class AcquisitionTier(Enum):
    """T0-T5, gia tri SO CO Y NGHIA THU TU (re nhat truoc) — dung de sap
    `_CANONICAL_ORDER` on dinh ma khong can liet ke tay tung hoan vi."""

    T0_DIRECT = 0
    T1_STRUCTURED = 1
    T2_BROWSER_RENDERED = 2
    T3_PUBLIC_NETWORK = 3
    T4_DOCUMENT = 4
    T5_MANAGED_PROVIDER = 5


class AcquisitionPlugin(ABC):
    """A T1-T5 strategy - Firecrawl, Bright Data, Crawl4AI, a real browser
    renderer, an RSS/sitemap fetcher, or a provider-specific API are all
    expected to be one of these. NONE are implemented in this repo by
    default (no such dependency/credential exists here) - this ABC is the
    seam a future adapter plugs into without touching the router's core
    selection logic."""

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


#: Re nhat -> dat nhat, dung lam thu tu MAC DINH khi khong co lich su cho
#: mot host. KHONG con la mot dict liet ke tay tung hoan vi (3! = 6 truoc
#: day, gio la 6! = 720 neu lam kieu cu) — `_order_from()` sinh thu tu tu
#: danh sach nay MOI LAN goi, dat tang uu tien len dau.
_CANONICAL_ORDER: Tuple[AcquisitionTier, ...] = (
    AcquisitionTier.T0_DIRECT,
    AcquisitionTier.T1_STRUCTURED,
    AcquisitionTier.T2_BROWSER_RENDERED,
    AcquisitionTier.T3_PUBLIC_NETWORK,
    AcquisitionTier.T4_DOCUMENT,
    AcquisitionTier.T5_MANAGED_PROVIDER,
)


def _order_from(preferred: AcquisitionTier) -> Tuple[AcquisitionTier, ...]:
    """Tang UU TIEN (thanh cong lan truoc cho host nay) len dau, phan con
    lai giu nguyen thu tu RE-NHAT-TRUOC chinh tac — khong doan mot thu tu
    "hop ly hon" cho phan con lai, tranh hanh vi ngac nhien khi them tang moi."""
    return (preferred,) + tuple(t for t in _CANONICAL_ORDER if t != preferred)


_TIER_TO_METHOD = {
    AcquisitionTier.T0_DIRECT: AcquisitionMethod.DIRECT_HTTP,
    AcquisitionTier.T1_STRUCTURED: AcquisitionMethod.STRUCTURED_API,
    AcquisitionTier.T2_BROWSER_RENDERED: AcquisitionMethod.BROWSER_RENDER,
    AcquisitionTier.T3_PUBLIC_NETWORK: AcquisitionMethod.NETWORK_OBSERVED,
    AcquisitionTier.T4_DOCUMENT: AcquisitionMethod.DOCUMENT,
    AcquisitionTier.T5_MANAGED_PROVIDER: AcquisitionMethod.PLUGIN,
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
        return self._history.get(domain_of(url), AcquisitionTier.T0_DIRECT)

    def record_observation(self, url: str, tier: AcquisitionTier, *, success: bool) -> None:
        if success:
            self._history[domain_of(url)] = tier

    def _plugins_for(self, tier: AcquisitionTier) -> List[AcquisitionPlugin]:
        return [p for p in self.plugins if p.tier == tier and p.available()]

    def _acquire_t0_direct(self, url: str, source_hint: SourceClass) -> AcquisitionResult:
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
            provenance="AcquisitionRouter/t0_direct")

    def acquire(self, url: str, *,
               source_hint: SourceClass = SourceClass.UNKNOWN) -> AcquisitionResult:
        order = _order_from(self.preferred_tier(url))
        last_result: Optional[AcquisitionResult] = None
        tried: List[AcquisitionTier] = []
        for tier in order:
            if tier == AcquisitionTier.T0_DIRECT:
                result = self._acquire_t0_direct(url, source_hint)
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
                       "T1-T5 nao duoc dang ky va T0 that bai).")])
