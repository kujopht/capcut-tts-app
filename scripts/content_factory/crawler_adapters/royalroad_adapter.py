"""
Royal Road Site Adapter — Content Factory v2.

Crawls and normalizes web fiction from RoyalRoad.com into RawCrawlerWork and RawCrawlerChapter.
Reuses and refactors the battle-tested scraping logic from web_novel_saga_harvester.py.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scripts.content_factory.crawler_adapters.base_adapter import BaseCrawlerAdapter
from server.crawler_intake_contract import (
    RawCrawlerChapter,
    RawCrawlerWork,
    canonicalize_url,
    compute_source_text_hash,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _fetch_html(url: str, timeout: int = 15) -> str:
    """Fetches HTML with curl using desktop browser user-agent."""
    cmd = [
        "curl.exe", "-s", "-L", "--max-time", str(timeout),
        "-A", USER_AGENT,
        url,
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=NO_WINDOW,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"Failed to fetch {url}: {proc.stderr or 'Empty response'}")
    return proc.stdout


class RoyalRoadAdapter(BaseCrawlerAdapter):
    """Adapter for Royal Road fiction scraping."""

    @property
    def platform_id(self) -> str:
        return "royalroad"

    @property
    def display_name(self) -> str:
        return "Royal Road"

    def identify_work(self, url_or_id: str) -> bool:
        s = url_or_id.strip().lower()
        if "royalroad.com/fiction/" in s:
            return True
        if s.isdigit():
            return True
        return False

    def extract_work_id(self, url_or_id: str) -> str:
        s = url_or_id.strip()
        m = re.search(r"/fiction/(\d+)", s)
        if m:
            return m.group(1)
        if s.isdigit():
            return s
        raise ValueError(f"Cannot extract RoyalRoad fiction ID from '{url_or_id}'")

    def _get_fiction_url(self, url_or_id: str) -> str:
        s = url_or_id.strip()
        if s.startswith("http"):
            return s
        fid = self.extract_work_id(s)
        return f"https://www.royalroad.com/fiction/{fid}"

    def fetch_metadata(self, url_or_id: str) -> Dict[str, Any]:
        url = self._get_fiction_url(url_or_id)
        work_id = self.extract_work_id(url_or_id)
        html = _fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")

        title_el = soup.find("h1")
        title = title_el.text.strip() if title_el else f"RoyalRoad Fiction {work_id}"

        author_el = soup.find("h4", class_="font-white") or soup.find("a", href=re.compile(r"/profile/\d+"))
        author = author_el.text.strip() if author_el else "Unknown Author"

        desc_el = soup.find("div", class_="description")
        desc = desc_el.text.strip() if desc_el else ""

        cover_el = soup.find("img", class_="thumbnail") or soup.find("img", class_="inline-block")
        cover_url = ""
        if cover_el and cover_el.get("src"):
            src = cover_el.get("src")
            cover_url = urljoin("https://www.royalroad.com", src)

        # Tags and Fandom extraction
        tags = []
        for tag_el in soup.find_all("span", class_="tags"):
            for a in tag_el.find_all("a"):
                t = a.text.strip()
                if t:
                    tags.append(t)

        fandom = "Fanfiction"
        for t in tags:
            if any(k in t.lower() for k in ("fanfiction", "fanfic")):
                fandom = t
                break

        # Check common anime/fanfic cues in title
        title_lower = title.lower()
        if "naruto" in title_lower:
            fandom = "Naruto"
        elif "one piece" in title_lower:
            fandom = "One Piece"
        elif "conan" in title_lower:
            fandom = "Detective Conan"
        elif "genshin" in title_lower:
            fandom = "Genshin Impact"
        elif "harry potter" in title_lower:
            fandom = "Harry Potter"

        status = self.detect_status(url_or_id, soup=soup)

        return {
            "source_id": work_id,
            "source_url": canonicalize_url(url),
            "source_language": "en",
            "title": title,
            "author": author,
            "description": desc,
            "fandom": fandom,
            "tags": tags,
            "cover_url": cover_url,
            "source_status": status,
        }

    def list_chapters(self, url_or_id: str, soup: Optional[BeautifulSoup] = None) -> List[Dict[str, Any]]:
        if soup is None:
            url = self._get_fiction_url(url_or_id)
            html = _fetch_html(url)
            soup = BeautifulSoup(html, "html.parser")

        chapters: List[Dict[str, Any]] = []
        seen = set()
        order = 1

        # Look for chapter table / links
        for a in soup.find_all("a"):
            href = a.get("href")
            if href and "/chapter/" in href and href not in seen:
                seen.add(href)
                ch_name = a.text.strip()
                full_url = urljoin("https://www.royalroad.com", href)
                
                # Extract chapter ID from URL
                m_cid = re.search(r"/chapter/(\d+)", href)
                cid = m_cid.group(1) if m_cid else f"c{order:04d}"

                chapters.append({
                    "order": order,
                    "source_chapter_id": cid,
                    "title": ch_name or f"Chapter {order}",
                    "url": full_url,
                })
                order += 1

        return chapters

    def fetch_chapter(self, chapter_info: Dict[str, Any]) -> RawCrawlerChapter:
        url = chapter_info["url"]
        html = _fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")

        title_el = soup.find("h1")
        title = title_el.text.strip() if title_el else chapter_info.get("title", f"Chapter {chapter_info['order']}")

        content_div = soup.find("div", class_="chapter-content")
        if not content_div:
            raise RuntimeError(f"Could not find .chapter-content on {url}")

        # Extract clean text preserving paragraphs
        paragraphs = []
        for p in content_div.find_all(["p", "div"]):
            txt = p.get_text().strip()
            if txt:
                paragraphs.append(txt)

        if not paragraphs:
            # Fallback to direct get_text
            raw_text = content_div.get_text("\n\n").strip()
        else:
            raw_text = "\n\n".join(paragraphs)

        return RawCrawlerChapter(
            source_chapter_id=str(chapter_info.get("source_chapter_id", chapter_info["order"])),
            source_order=chapter_info["order"],
            source_title=title,
            source_text=raw_text,
            source_text_hash=compute_source_text_hash(raw_text),
        )

    def detect_status(self, url_or_id: str, soup: Optional[BeautifulSoup] = None) -> str:
        if soup is None:
            url = self._get_fiction_url(url_or_id)
            html = _fetch_html(url)
            soup = BeautifulSoup(html, "html.parser")

        # Check status badge (COMPLETED / ONGOING / HIATUS)
        text_content = soup.get_text().lower()
        if "completed" in text_content:
            return "completed"
        return "ongoing"
