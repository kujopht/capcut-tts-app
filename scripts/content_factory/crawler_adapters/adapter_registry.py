"""
Crawler Adapter Registry — Content Factory v2.

Dispatches URLs or work IDs to the appropriate site adapter.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from scripts.content_factory.crawler_adapters.base_adapter import BaseCrawlerAdapter
from scripts.content_factory.crawler_adapters.royalroad_adapter import RoyalRoadAdapter

_ADAPTERS: List[BaseCrawlerAdapter] = [
    RoyalRoadAdapter(),
]


def get_adapter_for_url(url_or_id: str) -> Optional[BaseCrawlerAdapter]:
    """Finds the registered crawler adapter capable of handling url_or_id."""
    for adapter in _ADAPTERS:
        if adapter.identify_work(url_or_id):
            return adapter
    return None


def get_adapter_by_platform(platform_id: str) -> Optional[BaseCrawlerAdapter]:
    """Finds adapter by platform ID string (e.g. 'royalroad')."""
    for adapter in _ADAPTERS:
        if adapter.platform_id.lower() == platform_id.lower():
            return adapter
    return None


def list_supported_platforms() -> List[Dict[str, str]]:
    """Returns list of supported platforms with ID and display name."""
    return [{"id": a.platform_id, "name": a.display_name} for a in _ADAPTERS]
