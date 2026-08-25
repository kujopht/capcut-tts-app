"""
Adapter Tier 0 tong quat cho dang trang PHO BIEN NHAT o cac site truyen
tinh: MOT trang muc luc liet ke lien ket toi tung chuong (khop mot mau
regex tren href), moi trang chuong la MOT trang HTML voi tieu de + noi
dung van ban. KHONG dung JS render — chi HTTP + parse HTML tinh.

Day KHONG phai adapter cho MOT site cu the: `chapter_href_pattern` do noi
goi cau hinh. Cau hinh san mot site that (vd mot chuong cu the tren
`docs/reports/`) la viec cua tang tren, khong phai cua file nay.
"""
from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urljoin

from server.scraper.contract import (
    NormalizedChapter, ScraperTier, SeriesInfo, StoryProvider, canonicalize_url,
)
from server.scraper.dedupe import content_hash, source_fingerprint
from server.scraper.html_extract import extract
from server.scraper.http_fetcher import FetchError

_CHAPTER_NUMBER_RE = re.compile(r"(\d+)")


class GenericIndexAdapter(StoryProvider):
    tier = ScraperTier.DIRECT_HTTP

    def __init__(self, fetcher, *, chapter_href_pattern: str,
                 title_suffix_to_strip: Optional[str] = None):
        """
        :param fetcher: doi tuong co `.fetch(url) -> FetchResult` (xem
            `http_fetcher.HttpFetcher`/`FixtureFetcher`) — tiem vao de test
            khong cham mang that.
        :param chapter_href_pattern: regex ap len href THO (chua resolve)
            de nhan dien lien ket la MOT chuong, vi du `r"/chuong-\\d+"`.
        :param title_suffix_to_strip: hau to lap lai tren MOI tieu de trang
            chuong (vd `" - Ten Site"`) can bo khi lay tieu de chuong rieng.
        """
        self._fetcher = fetcher
        self._chapter_re = re.compile(chapter_href_pattern)
        self._title_suffix = title_suffix_to_strip

    def resolve(self, url: str) -> str:
        try:
            result = self._fetcher.fetch(url)
        except FetchError as exc:
            raise ValueError(str(exc)) from exc
        return canonicalize_url(result.final_url)

    def discover_series(self, url: str) -> SeriesInfo:
        result = self._fetcher.fetch(url)
        page = extract(result.text)
        title = page.meta.get("og:title") or page.title or "(không có tiêu đề)"

        seen = set()
        chapter_urls: List[str] = []
        for href, _text in page.links:
            if not self._chapter_re.search(href):
                continue
            absolute = urljoin(result.final_url, href)
            canon = canonicalize_url(absolute)
            if canon in seen:
                continue
            seen.add(canon)
            chapter_urls.append(absolute)

        domain = canonicalize_url(result.final_url).split("/")[2]
        return SeriesInfo(
            canonical_url=canonicalize_url(result.final_url),
            title=title,
            source_domain=domain,
            author=page.meta.get("author") or page.meta.get("article:author"),
            description=page.meta.get("og:description") or page.meta.get("description"),
            chapter_urls=chapter_urls,
        )

    def fetch_chapter(self, url: str) -> str:
        result = self._fetcher.fetch(url)
        return result.text

    def normalize_chapter(self, url: str, raw_html: str,
                           series: SeriesInfo) -> NormalizedChapter:
        page = extract(raw_html)
        title = page.meta.get("og:title") or page.title or series.title
        if self._title_suffix and title.endswith(self._title_suffix):
            title = title[: -len(self._title_suffix)].strip()

        clean_text = page.visible_text()
        canon = canonicalize_url(url)

        number_match = _CHAPTER_NUMBER_RE.search(title) or _CHAPTER_NUMBER_RE.search(url)
        chapter_number = int(number_match.group(1)) if number_match else None

        return NormalizedChapter(
            source_url=url,
            canonical_url=canon,
            source_domain=series.source_domain,
            series_title=series.title,
            chapter_title=title,
            raw_text=raw_html,
            clean_text=clean_text,
            content_hash=content_hash(clean_text),
            source_fingerprint=source_fingerprint(canon),
            chapter_number=chapter_number,
            author=page.meta.get("author") or series.author,
            published_at=page.meta.get("article:published_time"),
        )
