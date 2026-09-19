"""Crawler adapters package."""
from scripts.content_factory.crawler_adapters.base_adapter import BaseCrawlerAdapter
from scripts.content_factory.crawler_adapters.royalroad_adapter import RoyalRoadAdapter
from scripts.content_factory.crawler_adapters.adapter_registry import (
    get_adapter_for_url,
    get_adapter_by_platform,
    list_supported_platforms,
)
