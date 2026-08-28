"""
Tier 1 — Scrapling (`https://github.com/D4Vinci/Scrapling`).

Danh gia thuc te (2026-08-26, xem docs/reports/): goi `scrapling` co ban
(KHONG bao gom cac trinh render trinh duyet `DynamicFetcher`/
`StealthyFetcher`, hai thu do can cai them rieng) la mot lop parse HTML
gon (lxml + cssselect + orjson + w3lib + tld — khong keo theo Playwright/
trinh duyet), va no THAT SU co mot kha nang Tier 0 khong co: dinh vi LAI
mot phan tu da "luu dau van tay" truoc do (`.save()`/`.relocate()`) bang
diem tuong dong cau truc/noi dung, KE CA khi site doi HET class VA the
bao ngoai giua hai lan quet — da kiem chung truc tiep: selector CU tra ve
RONG tren HTML moi, nhung `.relocate()` van tim dung phan tu.

Day la LY DO DUY NHAT de dua no vao lam Tier 1: KHONG phai vi no "manh
hon" `html.parser` cho truong hop binh thuong (GenericIndexAdapter da du
cho do), ma vi no song sot duoc mot kieu thay doi DOM cu the ma Tier 0
khong the — dung ke hoach adaptive: SAU LAN QUET DAU, luu dau van tay
cua khu vuc danh sach chuong; LAN QUET SAU, neu mau href cu (hoac CSS cu)
khong con khop MOT lien ket nao, moi thu `.relocate()` truoc khi bao
that bai — Tier 0 (`GenericIndexAdapter`) khong co duong lui nay.

P2 (overnight hardening) — SUA loi `from scrapling.parser import Selector`
o MUC MODULE: dieu nay khien CHI import module nay thoi (vd mot cong cu
liet ke adapter, hoac mot test khong lien quan) da lam sap toan bo tien
trinh neu `scrapling` chua cai — vi pham truc tiep yeu cau "Harvester
phai hoat dong binh thuong voi Tier 0/HTTP truc tiep, khong crash khi
khoi dong" cua nhiem vu nay. Nhap `Selector` CHI khi khoi tao instance
(`__init__`), va nem `ScraplingUnavailableError` (tu
`scrapling_relocation.py` — dinh nghia CHUNG mot cho, khong lap lai logic
tham do) voi thong bao ro rang thay vi de `ImportError` tho thoat ra."""
from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urljoin

from server.scraper.adapters.scrapling_relocation import (
    ScraplingUnavailableError, is_scrapling_available,
)
from server.scraper.contract import (
    NormalizedChapter, ScraperTier, SeriesInfo, StoryProvider, canonicalize_url,
)
from server.scraper.dedupe import content_hash, source_fingerprint
from server.scraper.http_fetcher import FetchError

_CHAPTER_NUMBER_RE = re.compile(r"(\d+)")

#: Dinh danh co dinh trong kho luu Scrapling cho khu vuc danh sach chuong
#: cua MOT series — khoa theo canonical_url cua trang muc luc de nhieu
#: series khac nhau khong dam len dau van tay cua nhau.
_FINGERPRINT_PREFIX = "fanficworld_chapter_list::"


class ScraplingAdapter(StoryProvider):
    """Nhu `GenericIndexAdapter` (mau href danh cho chuong + hau to tieu
    de can bo), nhung khi mau href KHONG con khop lien ket nao tren mot
    lan quet sau, thu dinh vi lai khu vuc danh sach chuong da luu dau van
    tay tu lan quet TRUOC do truoc khi coi la that bai that su."""

    tier = ScraperTier.HTML_PARSER

    def __init__(self, fetcher, *, chapter_href_pattern: str,
                 title_suffix_to_strip: Optional[str] = None,
                 storage_file: Optional[str] = None):
        if not is_scrapling_available():
            raise ScraplingUnavailableError(
                "Gói `scrapling` chưa được cài trong môi trường này — "
                "ScraplingAdapter không thể khởi tạo. Đây là khả năng "
                "nâng tầng (Tier 1) tùy chọn, caller phải bắt lỗi này và "
                "lùi về Tier 0 (GenericIndexAdapter/JsonLdAwareAdapter).")
        self._fetcher = fetcher
        self._chapter_re = re.compile(chapter_href_pattern)
        self._title_suffix = title_suffix_to_strip
        self._storage_args = {"storage_file": storage_file} if storage_file else {}

    def resolve(self, url: str) -> str:
        try:
            result = self._fetcher.fetch(url)
        except FetchError as exc:
            raise ValueError(str(exc)) from exc
        return canonicalize_url(result.final_url)

    def _tai_trang(self, url: str, final_url: str, html: str):
        from scrapling import Selector
        return Selector(html, url=final_url, adaptive=True, storage_args=self._storage_args)

    def discover_series(self, url: str) -> SeriesInfo:
        result = self._fetcher.fetch(url)
        canon = canonicalize_url(result.final_url)
        page = self._tai_trang(url, result.final_url, result.text)

        title = None
        meta_title = page.css("meta[property='og:title']")
        if meta_title:
            title = meta_title[0].attrib.get("content")
        if not title:
            title_tag = page.css("title")
            title = title_tag[0].text if title_tag else "(không có tiêu đề)"

        meta_desc = page.css("meta[property='og:description']") or page.css("meta[name='description']")
        description = meta_desc[0].attrib.get("content") if meta_desc else None
        meta_author = page.css("meta[name='author']")
        author = meta_author[0].attrib.get("content") if meta_author else None

        links = page.css("a")
        chapter_container_candidates = [
            el for el in links if el.attrib.get("href") and self._chapter_re.search(el.attrib["href"])
        ]

        if not chapter_container_candidates:
            # Mau href khong khop lien ket nao — co the site da doi cau
            # truc tu lan quet truoc. Thu dinh vi lai TUNG lien ket chuong
            # da luu dau van tay rieng le tu lan quet TRUOC (luu theo VI
            # TRI, khong phai mot "vung chua" — cau truc long nhau khac
            # nhau giua v1/v2 khien viec tim mot to tien chung khong dang
            # tin cay bang dinh vi tung phan tu rieng).
            fp_id = _FINGERPRINT_PREFIX + canon
            relocated_links = []
            i = 0
            while True:
                saved = page.retrieve(f"{fp_id}::{i}")
                if saved is None:
                    break
                found = page.relocate(saved, selector_type=True)
                if found:
                    relocated_links.append(found[0])
                i += 1
            chapter_container_candidates = [
                el for el in relocated_links if el.attrib.get("href")
            ]
        else:
            # Quet thanh cong voi mau hien tai — luu dau van tay CUA TUNG
            # lien ket chuong rieng le (theo vi tri) de lan quet SAU co the
            # dinh vi lai tung cai mot neu mau href thay doi.
            fp_id = _FINGERPRINT_PREFIX + canon
            for i, el in enumerate(chapter_container_candidates):
                page.save(el, f"{fp_id}::{i}")

        seen = set()
        chapter_urls: List[str] = []
        for el in chapter_container_candidates:
            href = el.attrib.get("href")
            if not href:
                continue
            absolute = urljoin(result.final_url, href)
            c = canonicalize_url(absolute)
            if c in seen:
                continue
            seen.add(c)
            chapter_urls.append(absolute)

        domain = canon.split("/")[2]
        return SeriesInfo(
            canonical_url=canon, title=title, source_domain=domain,
            author=author, description=description, chapter_urls=chapter_urls,
        )

    def fetch_chapter(self, url: str) -> str:
        result = self._fetcher.fetch(url)
        return result.text

    def normalize_chapter(self, url: str, raw_html: str,
                           series: SeriesInfo) -> NormalizedChapter:
        from scrapling import Selector
        page = Selector(raw_html, url=url)
        meta_title = page.css("meta[property='og:title']")
        if meta_title:
            title = meta_title[0].attrib.get("content")
        else:
            title_tag = page.css("title")
            title = title_tag[0].text if title_tag else series.title
        # `og:title`/`<title>`/`series.title` co the deu vang (trang khong
        # co tieu de nao ca) — khong duoc de mot chuoi rong/None lam vo
        # `.endswith()`/regex ben duoi.
        title = title or "(không có tiêu đề)"
        if self._title_suffix and title.endswith(self._title_suffix):
            title = title[: -len(self._title_suffix)].strip()

        clean_text = page.get_all_text(
            strip=True,
            ignore_tags=("script", "style", "noscript", "nav", "header", "footer", "aside"),
        )
        canon = canonicalize_url(url)

        number_match = _CHAPTER_NUMBER_RE.search(title) or _CHAPTER_NUMBER_RE.search(url)
        chapter_number = int(number_match.group(1)) if number_match else None

        meta_author = page.css("meta[name='author']")
        author = meta_author[0].attrib.get("content") if meta_author else series.author
        meta_published = page.css("meta[property='article:published_time']")
        published_at = meta_published[0].attrib.get("content") if meta_published else None

        return NormalizedChapter(
            source_url=url, canonical_url=canon, source_domain=series.source_domain,
            series_title=series.title, chapter_title=title, raw_text=raw_html,
            clean_text=clean_text, content_hash=content_hash(clean_text),
            source_fingerprint=source_fingerprint(canon),
            chapter_number=chapter_number, author=author, published_at=published_at,
        )
