"""
Base Crawler Adapter Interface — Content Factory v2.

Defines the clean, pluggable contract for all external site crawlers.
Converts upstream source data into normalized RawCrawlerWork and RawCrawlerChapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from server.crawler_intake_contract import RawCrawlerChapter, RawCrawlerWork


class BaseCrawlerAdapter(ABC):
    """Abstract base class for all external site crawler adapters."""

    @property
    @abstractmethod
    def platform_id(self) -> str:
        """Unique identifier for the platform (e.g. 'royalroad', 'ao3', 'syosetu')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for the platform (e.g. 'Royal Road')."""
        pass

    @abstractmethod
    def identify_work(self, url_or_id: str) -> bool:
        """Returns True if this adapter can handle the given URL or identifier."""
        pass

    @abstractmethod
    def extract_work_id(self, url_or_id: str) -> str:
        """Extracts the canonical source work ID from the URL or identifier."""
        pass

    @abstractmethod
    def fetch_metadata(self, url_or_id: str) -> Dict[str, Any]:
        """Fetches upstream novel metadata (title, author, synopsis, cover, status)."""
        pass

    @abstractmethod
    def list_chapters(self, url_or_id: str) -> List[Dict[str, Any]]:
        """Lists all chapter items from the index (order, title, chapter_id, url)."""
        pass

    @abstractmethod
    def fetch_chapter(self, chapter_info: Dict[str, Any]) -> RawCrawlerChapter:
        """Fetches and cleans a single chapter's body text."""
        pass

    @abstractmethod
    def detect_status(self, url_or_id: str) -> str:
        """Detects whether upstream work is 'ongoing' or 'completed'."""
        pass

    def crawl_work(self, url_or_id: str, max_chapters: Optional[int] = None) -> RawCrawlerWork:
        """End-to-end convenience method to fetch work metadata and all chapters."""
        meta = self.fetch_metadata(url_or_id)
        chapter_items = self.list_chapters(url_or_id)
        if max_chapters:
            chapter_items = chapter_items[:max_chapters]

        chapters: List[RawCrawlerChapter] = []
        for ch_info in chapter_items:
            ch = self.fetch_chapter(ch_info)
            chapters.append(ch)

        return RawCrawlerWork(
            source_id=meta["source_id"],
            source_url=meta["source_url"],
            source_language=meta.get("source_language", "en"),
            title=meta["title"],
            author=meta.get("author", "Unknown"),
            description=meta.get("description", ""),
            fandom=meta.get("fandom"),
            tags=meta.get("tags", []),
            cover_url=meta.get("cover_url"),
            chapters=chapters,
        )

    # Alias for convenience
    fetch_work = crawl_work
