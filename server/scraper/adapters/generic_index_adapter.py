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
from typing import Dict, List, Optional
from urllib.parse import urljoin

from server.scraper.contract import (
    NormalizedChapter, ScraperTier, SeriesInfo, StoryProvider, canonicalize_url,
)
from server.scraper.content_extraction import extract_content_v3
from server.scraper.dedupe import content_hash, source_fingerprint
from server.scraper.html_extract import extract
from server.scraper.http_fetcher import FetchError

_CHAPTER_NUMBER_RE = re.compile(r"(\d+)")


def _dam_bao_la_html(result) -> None:
    """Chan TRUOC khi parse: mot content-type ro rang KHONG PHAI van ban
    (anh, PDF, octet-stream, ...) khong duoc dua qua `html.parser` — trinh
    phan tich khong nem loi tren du lieu nhi phan, no chi tra ve rac (van
    ban vo nghia trich tu byte nhi phan) ma khong ai phat hien duoc o tang
    tren. Chan som o day thay vi tin parser tu phat hien."""
    ct = (result.content_type or "").split(";")[0].strip().lower()
    if ct and not (ct.startswith("text/") or ct in (
        "application/xhtml+xml", "application/xml", "application/json",
    )):
        raise FetchError(
            f"{result.final_url} tra ve content-type khong phai van ban: {ct!r}")


class GenericIndexAdapter(StoryProvider):
    tier = ScraperTier.DIRECT_HTTP

    def __init__(self, fetcher, *, chapter_href_pattern: str,
                 title_suffix_to_strip: Optional[str] = None,
                 next_page_href_pattern: Optional[str] = None,
                 max_index_pages: int = 20):
        """
        :param fetcher: doi tuong co `.fetch(url) -> FetchResult` (xem
            `http_fetcher.HttpFetcher`/`FixtureFetcher`) — tiem vao de test
            khong cham mang that.
        :param chapter_href_pattern: regex ap len href THO (chua resolve)
            de nhan dien lien ket la MOT chuong, vi du `r"/chuong-\\d+"`.
        :param title_suffix_to_strip: hau to lap lai tren MOI tieu de trang
            chuong (vd `" - Ten Site"`) can bo khi lay tieu de chuong rieng.
        :param next_page_href_pattern: regex ap len href de nhan dien lien
            ket "trang muc luc tiep theo" (vd `r"/truyen/x\\?page=\\d+"`).
            KHONG cau hinh (mac dinh) = mot trang muc luc DUY NHAT, hanh vi
            CU khong doi — pagination la tinh nang CONG THEM, khong bat buoc.
        :param max_index_pages: chan tren SO TRANG muc luc se theo — an toan
            chong vong lap vo han (mot site loi tro next-page ve chinh no).
        """
        self._fetcher = fetcher
        self._chapter_re = re.compile(chapter_href_pattern)
        self._title_suffix = title_suffix_to_strip
        self._next_page_re = (
            re.compile(next_page_href_pattern) if next_page_href_pattern else None
        )
        self._max_index_pages = max_index_pages
        #: hash doan van -> tap canonical_url cac chuong DA co doan do —
        #: Phase 6: "boilerplate lap lai qua nhieu trang" (xem
        #: `content_extraction.py`). CHI dung khi trang KHONG co boundary da
        #: xac minh tay (xem `normalize_chapter`) — Wikisource/Royal Road
        #: khong can no. Khoa theo canonical_url (KHONG PHAI mot tap don) de
        #: `_boilerplate_hashes_cho` co the LOAI TRU chinh chuong dang xu ly
        #: khi dem — thieu buoc nay, XU LY LAI cung MOT chuong (retry, hoac
        #: goi `normalize_chapter` hai lan y het, xem
        #: `IdempotentRerunTest`) se coi CHINH doan van cua no la
        #: "boilerplate da biet" (tu no xuat hien trong chinh no) va loai bo
        #: het noi dung — phat hien qua mot lan chay bo test hien co (khong
        #: phai fixture moi), content_hash ra `sha256("")` o lan goi thu hai.
        self._boilerplate_chapter_urls_theo_hash: Dict[str, set] = {}

    #: So chuong KHAC (khong tinh chinh chuong dang xu ly) tung co MOT doan
    #: van GIONG HET truoc khi doan do bi coi la boilerplate toan site —
    #: >=2 de tranh loai oan mot doan chi tinh co giong nhau giua HAI chuong
    #: (vd mot cau thoai lap lai co chu y trong truyen).
    _SO_LAN_LAP_TOI_THIEU_LA_BOILERPLATE = 2

    def _boilerplate_hashes_cho(self, canon_hien_tai: str) -> set:
        return {
            h for h, urls in self._boilerplate_chapter_urls_theo_hash.items()
            if len(urls - {canon_hien_tai}) >= self._SO_LAN_LAP_TOI_THIEU_LA_BOILERPLATE
        }

    def _ghi_nhan_doan_van_boilerplate(self, canon_hien_tai: str, hashes: set) -> None:
        for h in hashes:
            self._boilerplate_chapter_urls_theo_hash.setdefault(h, set()).add(canon_hien_tai)

    def resolve(self, url: str) -> str:
        try:
            result = self._fetcher.fetch(url)
        except FetchError as exc:
            raise ValueError(str(exc)) from exc
        return canonicalize_url(result.final_url)

    def discover_series(self, url: str) -> SeriesInfo:
        result = self._fetcher.fetch(url)
        _dam_bao_la_html(result)
        page = extract(result.text)
        title = page.meta.get("og:title") or page.title or "(không có tiêu đề)"
        domain = canonicalize_url(result.final_url).split("/")[2]

        seen_chapter = set()
        seen_index_page = {canonicalize_url(result.final_url)}
        chapter_urls: List[str] = []
        trang_hien_tai = page
        base_url = result.final_url

        for _ in range(self._max_index_pages):
            for href, _text in trang_hien_tai.links:
                if not self._chapter_re.search(href):
                    continue
                absolute = urljoin(base_url, href)
                canon = canonicalize_url(absolute)
                if canon in seen_chapter:
                    continue
                seen_chapter.add(canon)
                chapter_urls.append(absolute)

            if self._next_page_re is None:
                break

            trang_ke = self._tim_trang_tiep_theo(trang_hien_tai, base_url, seen_index_page)
            if trang_ke is None:
                break
            base_url, trang_hien_tai = trang_ke

        return SeriesInfo(
            canonical_url=canonicalize_url(result.final_url),
            title=title,
            source_domain=domain,
            author=page.meta.get("author") or page.meta.get("article:author"),
            description=page.meta.get("og:description") or page.meta.get("description"),
            chapter_urls=chapter_urls,
        )

    def _tim_trang_tiep_theo(self, trang, base_url: str, da_tham: set):
        """Tra ve `(url_moi, ExtractedPage_moi)` cua trang muc luc TIEP
        THEO, hoac `None` neu khong co/da tham (chan vong lap). Tach rieng
        thanh phuong thuc de `discover_series` khong lam qua nhieu viec."""
        for href, _text in trang.links:
            if not self._next_page_re.search(href):
                continue
            absolute = urljoin(base_url, href)
            canon = canonicalize_url(absolute)
            if canon in da_tham:
                return None  # da tham trang nay roi — dung, tranh vong lap.
            da_tham.add(canon)
            ket_qua = self._fetcher.fetch(absolute)
            _dam_bao_la_html(ket_qua)
            return ket_qua.final_url, extract(ket_qua.text)
        return None

    def fetch_chapter(self, url: str) -> str:
        result = self._fetcher.fetch(url)
        _dam_bao_la_html(result)
        return result.text

    def normalize_chapter(self, url: str, raw_html: str,
                           series: SeriesInfo) -> NormalizedChapter:
        page = extract(raw_html)
        title = page.meta.get("og:title") or page.title or series.title
        if self._title_suffix and title.endswith(self._title_suffix):
            title = title[: -len(self._title_suffix)].strip()
        canon = canonicalize_url(url)

        # `boundary_matched` = trang co the ranh gioi DA XAC MINH TAY (xem
        # `html_extract.py`, Wikisource/Royal Road) — dung thang, DA CHUNG
        # MINH dung, khong can cham diem. Nguoc lai (nguon hoc duoc/dang
        # kham pha, Phase 6 Story Harvester V3): qua `extract_content_v3`
        # (cham diem ung vien + loai vung rac/boilerplate lap lai), luon
        # dien `extraction_confidence` de quality gate (xem `quality.py`,
        # check "Do not silently accept weak extraction").
        extraction_confidence = ""
        if page.boundary_matched:
            clean_text = page.visible_text()
        else:
            ket_qua_v3 = extract_content_v3(
                raw_html, chapter_title=title,
                known_boilerplate_hashes=self._boilerplate_hashes_cho(canon))
            clean_text = ket_qua_v3.clean_text
            extraction_confidence = ket_qua_v3.confidence.value
            self._ghi_nhan_doan_van_boilerplate(canon, ket_qua_v3.paragraph_hashes)

        # CHI tim so trong TIEU DE — tung co nhanh du phong tim trong URL,
        # bo di sau khi phat hien qua review Codex: mot URL dang
        # "/fiction/{id_truyen}/.../chapter/{id_chuong}/{ten-khong-so}"
        # (Royal Road) khien nhanh do bat NHAM id_truyen (so DAU TIEN trong
        # URL, thuong rat lon va khong lien quan) lam chapter_number cho
        # moi chuong khong-so (Prologue, Interlude, ...). KHONG doan tu URL
        # nua — chuong khong co so trong tieu de thi `chapter_number` la
        # `None` THAT SU (da la Optional[int] tu dau, xem NormalizedChapter),
        # dung thu tu kham pha (`chapter_urls_to_process`) de sap xep thay
        # vi mot con so bia dat.
        number_match = _CHAPTER_NUMBER_RE.search(title)
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
            extraction_confidence=extraction_confidence,
        )
