"""
Adapter Tier 0 uu tien du lieu co cau truc (JSON-LD `schema.org/Article` hay
`CreativeWork`) hon van ban hien thi tho — chinh xac hon (tach dung tieu
de/tac gia/ngay dang khoi noi dung, khong lan voi menu/quang cao quanh no)
khi trang THAT SU co khai bao JSON-LD. Trang khong co JSON-LD (hoac JSON-LD
hong/thieu truong) roi ve dung `GenericIndexAdapter` — KHONG bao gio coi
thieu JSON-LD la loi.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
from server.scraper.contract import NormalizedChapter, SeriesInfo, canonicalize_url
from server.scraper.dedupe import content_hash, source_fingerprint
from server.scraper.html_extract import extract

_ARTICLE_TYPES = {"Article", "NewsArticle", "CreativeWork", "Chapter", "Book"}


def _tim_article_ld(json_ld_blocks: list) -> Optional[Dict[str, Any]]:
    for block in json_ld_blocks:
        candidates = block if isinstance(block, list) else [block]
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") in _ARTICLE_TYPES:
                return item
    return None


class JsonLdAwareAdapter(GenericIndexAdapter):
    def normalize_chapter(self, url: str, raw_html: str,
                           series: SeriesInfo) -> NormalizedChapter:
        page = extract(raw_html)
        article = _tim_article_ld(page.json_ld)

        if article is None:
            return super().normalize_chapter(url, raw_html, series)

        title = (article.get("headline") or article.get("name")
                 or page.title or series.title)
        body = article.get("articleBody")
        clean_text = str(body).strip() if body else page.visible_text()

        author_field = article.get("author")
        if isinstance(author_field, dict):
            author = author_field.get("name")
        elif isinstance(author_field, list) and author_field:
            first = author_field[0]
            author = first.get("name") if isinstance(first, dict) else str(first)
        else:
            author = author_field

        canon = canonicalize_url(url)
        return NormalizedChapter(
            source_url=url,
            canonical_url=canon,
            source_domain=series.source_domain,
            series_title=series.title,
            chapter_title=str(title),
            raw_text=raw_html,
            clean_text=clean_text,
            content_hash=content_hash(clean_text),
            source_fingerprint=source_fingerprint(canon),
            author=author or series.author,
            published_at=article.get("datePublished"),
        )
