"""
Adapter Tier 0 uu tien du lieu co cau truc (JSON-LD `schema.org/Article` hay
`CreativeWork`) hon van ban hien thi tho — chinh xac hon (tach dung tieu
de/tac gia/ngay dang khoi noi dung, khong lan voi menu/quang cao quanh no)
khi trang THAT SU co khai bao JSON-LD. Trang khong co JSON-LD (hoac JSON-LD
hong/thieu truong) roi ve dung `GenericIndexAdapter` — KHONG bao gio coi
thieu JSON-LD la loi.
"""
from __future__ import annotations

from dataclasses import replace
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


def _trich_tac_gia(author_field: Any) -> Optional[str]:
    if isinstance(author_field, dict):
        return author_field.get("name")
    if isinstance(author_field, list) and author_field:
        first = author_field[0]
        return first.get("name") if isinstance(first, dict) else str(first)
    return author_field


class JsonLdAwareAdapter(GenericIndexAdapter):
    def normalize_chapter(self, url: str, raw_html: str,
                           series: SeriesInfo) -> NormalizedChapter:
        page = extract(raw_html)
        article = _tim_article_ld(page.json_ld)

        if article is None:
            return super().normalize_chapter(url, raw_html, series)

        body = article.get("articleBody")
        if not body:
            # JSON-LD CO nhung THIEU `articleBody` — van uu tien tieu de/
            # tac gia/ngay dang tu JSON-LD (dang tin cay), nhung PHAI di
            # qua duong trich xuat THAT SU cho `clean_text` (boundary_matched
            # da xac minh tay HOAC Phase 6 v3), KHONG duoc goi thang
            # `page.visible_text()` — truoc day nhanh nay bo qua CA HAI co
            # che do, tuong duong lam nhu Phase 6 CHUA TUNG duoc xay cho
            # nguon nao co JSON-LD-nhung-thieu-body — phat hien qua review
            # doc lap (Codex).
            chapter = super().normalize_chapter(url, raw_html, series)
            tieu_de_ld = article.get("headline") or article.get("name")
            tac_gia_ld = _trich_tac_gia(article.get("author"))
            ngay_dang_ld = article.get("datePublished")
            if tieu_de_ld or tac_gia_ld or ngay_dang_ld:
                chapter = replace(
                    chapter,
                    chapter_title=str(tieu_de_ld) if tieu_de_ld else chapter.chapter_title,
                    author=tac_gia_ld or chapter.author,
                    published_at=ngay_dang_ld or chapter.published_at,
                )
            return chapter

        title = article.get("headline") or article.get("name") or page.title or series.title
        clean_text = str(body).strip()
        author = _trich_tac_gia(article.get("author"))

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
