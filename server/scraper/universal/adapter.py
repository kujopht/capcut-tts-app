"""
Source Adapter plugin contract — Story Harvester V5 Phase 4.

`SourceAdapter` is the ONE contract every source-class adapter implements —
known-source (fiction/YouTube/RSS) and generic/unknown-source adapters
alike use this SAME contract, so the router/pipeline never special-cases a
particular source class. This does NOT replace `contract.StoryProvider`
(the existing V4 fiction adapter interface) — `StoryProviderAdapter` below
is a compatibility bridge so every existing fiction adapter
(`GenericIndexAdapter`, `ScraplingAdapter`, ...) satisfies this contract
for free, with zero changes to those adapters.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional

from server.scraper.contract import SeriesInfo, StoryProvider
from server.scraper.universal.acquisition import (
    AcquisitionMethod, AcquisitionResult, AcquisitionStatus, SourceClass,
)


@dataclass(frozen=True)
class SourceCapabilities:
    """Declarative capability metadata — validated at registration time,
    never inferred via `isinstance`, matching the existing
    `adapters.AdapterCapabilities` convention in the V4 fiction registry."""

    source_classes: FrozenSet[SourceClass]
    supports_metadata: bool = True
    supports_unit_listing: bool = True
    supports_incremental_updates: bool = False
    supports_network_intelligence: bool = False
    requires_browser: bool = False
    stable_identity: bool = True

    def validate(self) -> None:
        if not self.source_classes:
            raise ValueError("SourceCapabilities.source_classes khong duoc rong")


class SourceAdapter(ABC):
    """Moi adapter cu the (nguon da biet HOAC nguon generic/chua biet) trien
    khai giao dien nay — KHONG duoc bien thanh mot bo giai ma van nang."""

    source_class: SourceClass = SourceClass.UNKNOWN

    @abstractmethod
    def probe(self, url: str) -> bool:
        """Cheap, no-network-required (or at most one lightweight request)
        check: can this adapter plausibly handle `url`? Used by the router
        to pick an adapter BEFORE committing to a full acquisition."""

    @abstractmethod
    def capabilities(self) -> SourceCapabilities:
        ...

    @abstractmethod
    def canonicalize(self, url: str) -> str:
        """Network-resolved canonical URL (follows real redirects) — raises
        `ValueError` if this adapter doesn't handle `url`."""

    @abstractmethod
    def extract_metadata(self, url: str) -> Dict[str, Any]:
        """Source/series/channel-level metadata for `url` (title, author,
        description, ...) — NOT a single unit's content."""

    @abstractmethod
    def list_units(self, url: str) -> List[str]:
        """Unit references discoverable from `url` — chapter URLs, video
        IDs, feed item GUIDs, document section IDs, whatever this source
        class's units are. Order matters where the source has one."""

    @abstractmethod
    def fetch_unit(self, unit_ref: str) -> AcquisitionResult:
        """Acquire ONE unit's raw content. Raw only — no cleaning here,
        matching `StoryProvider.fetch_chapter`'s separation of concerns."""

    @abstractmethod
    def normalize(self, unit_ref: str, acquisition: AcquisitionResult) -> Any:
        """Turn a raw `AcquisitionResult` into a normalized domain unit
        (see `units.py`) — the only step allowed to extract/clean content."""

    @abstractmethod
    def stable_identity(self, normalized_unit: Any) -> str:
        """Stable identifier of the UNIT's source position — must not
        change if content is revised, matching
        `StoryProvider.fingerprint`'s semantics."""


class StoryProviderAdapter(SourceAdapter):
    """Bridges an existing `StoryProvider` (fiction, V4) into the V5
    `SourceAdapter` contract with ZERO changes to the wrapped provider.

    Known inefficiency, documented rather than hidden: `StoryProvider`
    methods fetch internally (they were designed before the Router existed
    to drive acquisition externally), so `extract_metadata`/`list_units`
    each call `discover_series` again rather than reusing a
    router-acquired `AcquisitionResult` — a real double-fetch cost for
    fiction sources specifically. Acceptable for V5: it keeps the proven
    V4 adapters completely unmodified rather than forcing a fetch-contract
    change onto code with heavy existing test coverage.

    Stateful by design (mirrors how `StoryProvider` instances are already
    used one-per-task in `bulk.py`): `normalize()` must be called after
    `list_units()`/`extract_metadata()` on the SAME instance, since it
    reuses the `SeriesInfo` discovered there instead of re-discovering it.
    """

    source_class = SourceClass.WEB_FICTION

    def __init__(self, provider: StoryProvider):
        self._provider = provider
        self._last_series: Optional[SeriesInfo] = None

    def probe(self, url: str) -> bool:
        try:
            self._provider.resolve(url)
        except ValueError:
            return False
        return True

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            source_classes=frozenset({SourceClass.WEB_FICTION}),
            supports_incremental_updates=True,
            requires_browser=False,
        )

    def canonicalize(self, url: str) -> str:
        return self._provider.resolve(url)

    def extract_metadata(self, url: str) -> Dict[str, Any]:
        series = self._provider.discover_series(url)
        self._last_series = series
        return {
            "title": series.title, "author": series.author,
            "description": series.description,
            "source_domain": series.source_domain,
            "canonical_url": series.canonical_url,
        }

    def list_units(self, url: str) -> List[str]:
        series = self._last_series or self._provider.discover_series(url)
        self._last_series = series
        return self._provider.list_chapters(series)

    def fetch_unit(self, unit_ref: str) -> AcquisitionResult:
        try:
            raw_html = self._provider.fetch_chapter(unit_ref)
        except Exception as exc:                              # noqa: BLE001
            from server.scraper.universal.acquisition import AcquisitionError
            return AcquisitionResult(
                final_url=unit_ref, source_type=SourceClass.WEB_FICTION,
                status=AcquisitionStatus.FAILED,
                acquisition_method=AcquisitionMethod.DIRECT_HTTP,
                errors=[AcquisitionError(stage="fetch", message=str(exc)[:500])])
        return AcquisitionResult(
            final_url=unit_ref, source_type=SourceClass.WEB_FICTION,
            status=AcquisitionStatus.OK,
            acquisition_method=AcquisitionMethod.DIRECT_HTTP,
            content_type="text/html", html=raw_html,
            provenance=type(self._provider).__name__)

    def normalize(self, unit_ref: str, acquisition: AcquisitionResult) -> Any:
        if self._last_series is None:
            raise RuntimeError(
                "StoryProviderAdapter.normalize() goi truoc list_units()/"
                "extract_metadata() - can SeriesInfo de chuan hoa chuong.")
        return self._provider.normalize_chapter(
            unit_ref, acquisition.html or "", self._last_series)

    def stable_identity(self, normalized_unit: Any) -> str:
        return self._provider.fingerprint(normalized_unit)
