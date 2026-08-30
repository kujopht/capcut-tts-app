"""
YouTube Source Adapter — Story Harvester V5.

Fetches public video metadata via YouTube's official oEmbed endpoint.
Media acquisition (video/audio streaming or downloading) is strictly out of scope
by design for this adapter.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from server.scraper.http_fetcher import FetchResult, HttpFetcher
from server.scraper.universal.acquisition import (
    AcquisitionError,
    AcquisitionMethod,
    AcquisitionResult,
    AcquisitionStatus,
    SourceClass,
)
from server.scraper.universal.adapter import SourceAdapter, SourceCapabilities
from server.scraper.universal.identity import CanonicalIdentity
from server.scraper.universal.units import RawEvidence, Video


def _extract_youtube_id(url: str) -> str:
    """Extract the YouTube video ID from supported URL shapes:
    - youtube.com/watch?v=ID (or www.youtube.com, etc., possibly with extra query params)
    - m.youtube.com/watch?v=ID
    - youtu.be/ID
    - youtube.com/embed/ID
    Raises ValueError if the URL does not match any valid YouTube video shape.
    """
    if not url:
        raise ValueError("URL cannot be empty")

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    # youtu.be/ID
    if hostname == "youtu.be" or hostname.endswith(".youtu.be"):
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        if path_parts:
            video_id = path_parts[0]
            if video_id:
                return video_id
        raise ValueError(f"Invalid youtu.be URL: {url}")

    # youtube.com, www.youtube.com, m.youtube.com, etc.
    if hostname == "youtube.com" or hostname.endswith(".youtube.com"):
        path = parsed.path.rstrip("/")
        if path == "/watch":
            qs = parse_qs(parsed.query)
            v_list = qs.get("v")
            if v_list and v_list[0]:
                return v_list[0]
            raise ValueError(f"Missing 'v' parameter in watch URL: {url}")
        if path.startswith("/embed/"):
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 2 and parts[1]:
                return parts[1]
            raise ValueError(f"Invalid embed URL: {url}")

    raise ValueError(f"Unsupported or invalid YouTube URL: {url}")


class YouTubeAdapter(SourceAdapter):
    """First-class YouTube metadata adapter using public oEmbed endpoint."""

    source_class = SourceClass.YOUTUBE

    def __init__(self, fetcher: Optional[Any] = None) -> None:
        self._fetcher = fetcher or HttpFetcher()

    def probe(self, url: str) -> bool:
        try:
            _extract_youtube_id(url)
            return True
        except ValueError:
            return False

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            source_classes=frozenset({SourceClass.YOUTUBE}),
            supports_incremental_updates=False,
            requires_browser=False,
        )

    def canonicalize(self, url: str) -> str:
        video_id = _extract_youtube_id(url)
        return f"https://www.youtube.com/watch?v={video_id}"

    def extract_metadata(self, url: str) -> Dict[str, Any]:
        canonical_url = self.canonicalize(url)
        video_id = _extract_youtube_id(url)
        oembed_url = f"https://www.youtube.com/oembed?url={canonical_url}&format=json"
        fetch_res: FetchResult = self._fetcher.fetch(oembed_url)
        data = json.loads(fetch_res.text)

        return {
            "title": data.get("title", ""),
            "channel_name": data.get("author_name", ""),
            "channel_url": data.get("author_url", ""),
            "thumbnail_url": data.get("thumbnail_url", ""),
            "video_id": video_id,
            "canonical_url": canonical_url,
        }

    def list_units(self, url: str) -> List[str]:
        # Lone video has exactly one unit: itself. Playlist expansion is out of scope.
        return [self.canonicalize(url)]

    def fetch_unit(self, unit_ref: str) -> AcquisitionResult:
        try:
            canonical_url = self.canonicalize(unit_ref)
            oembed_url = f"https://www.youtube.com/oembed?url={canonical_url}&format=json"
            fetch_res: FetchResult = self._fetcher.fetch(oembed_url)
            data = json.loads(fetch_res.text)
            return AcquisitionResult(
                final_url=canonical_url,
                source_type=SourceClass.YOUTUBE,
                status=AcquisitionStatus.OK,
                acquisition_method=AcquisitionMethod.STRUCTURED_API,
                structured_json=data,
                provenance="youtube_oembed",
            )
        except Exception as exc:
            return AcquisitionResult(
                final_url=unit_ref,
                source_type=SourceClass.YOUTUBE,
                status=AcquisitionStatus.FAILED,
                acquisition_method=AcquisitionMethod.STRUCTURED_API,
                errors=[AcquisitionError(stage="fetch", message=str(exc)[:500])],
            )

    def normalize(self, unit_ref: str, acquisition: AcquisitionResult) -> Video:
        canonical_url = self.canonicalize(unit_ref)
        video_id = _extract_youtube_id(unit_ref)
        data = acquisition.structured_json or {}

        evidence = RawEvidence(
            acquisition_method=acquisition.acquisition_method,
            final_url=acquisition.final_url or canonical_url,
            provenance="youtube_oembed",
        )

        return Video(
            platform="youtube",
            video_id=video_id,
            canonical_url=canonical_url,
            title=data.get("title", ""),
            thumbnail_url=data.get("thumbnail_url", ""),
            evidence=evidence,
        )

    def stable_identity(self, normalized_unit: Any) -> str:
        if isinstance(normalized_unit, Video):
            video_id = normalized_unit.video_id
            canonical_url = normalized_unit.canonical_url
        else:
            video_id = getattr(normalized_unit, "video_id", "")
            canonical_url = getattr(normalized_unit, "canonical_url", "")

        return CanonicalIdentity(
            source_platform="youtube",
            source_type=SourceClass.YOUTUBE,
            source_native_id=video_id,
            canonical_url=canonical_url,
        ).identity_key()

    def fetch_transcript(self, video_id: str) -> None:
        """Transcript acquisition requires a separate, not-yet-implemented legitimate
        access path and is deliberately not attempted in this pass.
        """
        raise NotImplementedError(
            "Transcript acquisition requires a separate, not-yet-implemented legitimate "
            "access path and is deliberately not attempted in this pass."
        )
