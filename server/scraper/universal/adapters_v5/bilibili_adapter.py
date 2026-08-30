"""
Bilibili metadata adapter — Story Harvester V5.

Conservative by design: metadata comes ONLY from Bilibili's real public
unauthenticated view-info endpoint. NO video download, NO login/cookie
handling, NO anti-bot circumvention anywhere in this module.

    GET https://api.bilibili.com/x/web-interface/view?bvid={{bvid}}

returns rich public metadata (title, desc, duration, owner, stat, ...) for
a public video without any authentication. `code != 0` in the JSON envelope
means the API itself reported an error (video not found / restricted) —
that is a FAILED acquisition, not a network success.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from server.scraper.http_fetcher import FetchError, FetchResult
from server.scraper.universal.acquisition import (
    AcquisitionError, AcquisitionMethod, AcquisitionResult, AcquisitionStatus,
    SourceClass,
)
from server.scraper.universal.adapter import SourceCapabilities
from server.scraper.universal.identity import CanonicalIdentity
from server.scraper.universal.units import RawEvidence, Video

from server.scraper.universal.adapters_v5.generic_video_platform import (
    VideoPlatformAdapter,
)

#: Matches Bilibili video URLs shaped like
#: https://www.bilibili.com/video/BVxxxxxxxxxx — captures the "BV..." bvid.
_BVID_PATTERN = re.compile(
    r"^https://(?:www\.)?bilibili\.com/video/(BV[0-9A-Za-z]+)(?:[/?#].*)?$"
)

_VIEW_INFO_API = "https://api.bilibili.com/x/web-interface/view"


def _is_fetch_result(value: Any) -> bool:
    return isinstance(value, FetchResult) or (
        hasattr(value, "final_url")
        and hasattr(value, "status_code")
        and hasattr(value, "text")
    )


class BilibiliAdapter(VideoPlatformAdapter):
    """Single-video Bilibili metadata adapter built on the real public
    unauthenticated view-info API."""

    source_class = SourceClass.VIDEO_PLATFORM

    def __init__(self, fetcher):
        self._fetcher = fetcher

    # -- URL shaping -----------------------------------------------------

    def _extract_bvid(self, url: str) -> str:
        match = _BVID_PATTERN.match(url)
        if not match:
            raise ValueError(f"Khong phai URL video Bilibili hop le: {url}")
        return match.group(1)

    def canonicalize(self, url: str) -> str:
        bvid = self._extract_bvid(url)
        return f"https://www.bilibili.com/video/{bvid}"

    def probe(self, url: str) -> bool:
        try:
            self._extract_bvid(url)
        except ValueError:
            return False
        return True

    def list_units(self, url: str) -> List[str]:
        return [self.canonicalize(url)]

    # -- Metadata --------------------------------------------------------

    def _load_data(self, unit_ref: str) -> Dict[str, Any]:
        bvid = self._extract_bvid(unit_ref)
        try:
            result = self._fetcher.fetch(
                f"{_VIEW_INFO_API}?bvid={bvid}")
        except FetchError as exc:
            raise RuntimeError(f"Khong tai duoc view-info Bilibili: {exc}") from exc
        if not _is_fetch_result(result) or result.status_code >= 400:
            raise RuntimeError(
                f"View-info Bilibili tra ve HTTP {getattr(result, 'status_code', '?')}")
        try:
            payload = json.loads(result.text)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                f"View-info Bilibili khong phai JSON hop le: {exc}") from exc
        if payload.get("code") != 0:
            raise ValueError(
                f"API Bilibili bao loi: code={payload.get('code')} "
                f"message={payload.get('message')}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("View-info Bilibili thieu truong 'data' hop le")
        return data

    def extract_metadata(self, url: str) -> Dict[str, Any]:
        data = self._load_data(url)
        stat = data.get("stat") or {}
        owner = data.get("owner") or {}
        pic = data.get("pic", "") or ""
        if pic and not pic.startswith("http"):
            pic = f"https:{pic}"
        return {
            "title": data.get("title", ""),
            "description": data.get("desc", ""),
            "duration_seconds": data.get("duration"),
            "thumbnail_url": pic,
            "uploader_name": owner.get("name", ""),
            "uploader_id": str(owner.get("mid", "")),
            "view_count": stat.get("view"),
        }

    # -- Unit acquisition ------------------------------------------------

    def fetch_unit(self, unit_ref: str) -> AcquisitionResult:
        try:
            data = self._load_data(unit_ref)
        except ValueError as exc:
            return AcquisitionResult(
                final_url=self._api_url(unit_ref),
                source_type=self.source_class,
                status=AcquisitionStatus.FAILED,
                acquisition_method=AcquisitionMethod.STRUCTURED_API,
                errors=[AcquisitionError(stage="extract", message=str(exc)[:500])],
            )
        except RuntimeError as exc:
            return AcquisitionResult(
                final_url=self._api_url(unit_ref),
                source_type=self.source_class,
                status=AcquisitionStatus.FAILED,
                acquisition_method=AcquisitionMethod.STRUCTURED_API,
                errors=[AcquisitionError(stage="fetch", message=str(exc)[:500])],
            )
        return AcquisitionResult(
            final_url=self._api_url(unit_ref),
            source_type=self.source_class,
            status=AcquisitionStatus.OK,
            acquisition_method=AcquisitionMethod.STRUCTURED_API,
            content_type="application/json",
            structured_json=data,
            provenance="bilibili_view_api",
        )

    def _api_url(self, unit_ref: str) -> str:
        bvid = self._extract_bvid(unit_ref)
        return f"{_VIEW_INFO_API}?bvid={bvid}"

    def normalize(self, unit_ref: str, acquisition: AcquisitionResult) -> Video:
        data = acquisition.structured_json or {}
        owner = data.get("owner") or {}
        stat = data.get("stat") or {}
        pic = data.get("pic", "") or ""
        if pic and not pic.startswith("http"):
            pic = f"https:{pic}"
        bvid = self._extract_bvid(unit_ref)
        return Video(
            platform="bilibili",
            video_id=bvid,
            channel_id=str(owner.get("mid", "")),
            title=data.get("title", ""),
            description=data.get("desc", ""),
            duration_seconds=data.get("duration"),
            thumbnail_url=pic,
            canonical_url=self.canonicalize(unit_ref),
            evidence=RawEvidence(
                acquisition_method=AcquisitionMethod.STRUCTURED_API,
                final_url=acquisition.final_url,
                provenance="bilibili_view_api",
            ),
        )

    def stable_identity(self, video: Video) -> str:
        return CanonicalIdentity(
            source_platform="bilibili",
            source_type=SourceClass.VIDEO_PLATFORM,
            source_native_id=video.video_id,
            canonical_url=video.canonical_url,
        ).identity_key()

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            source_classes=frozenset({SourceClass.VIDEO_PLATFORM}),
            supports_metadata=True,
            supports_unit_listing=True,
            requires_browser=False,
            stable_identity=True,
        )
