"""
Adapter Tier 0 cho nguon KHONG CO trang muc luc — Phase 3 Story Harvester
V3, bien the "next/prev-navigation-only sources". Chi biet MOT url chuong
BAT DAU (thuong la chuong 1); danh sach chuong day du CHI kham pha duoc
bang cach THEO DOI lien ket "chuong tiep theo" tren TUNG trang chuong, tuan
tu, cho den khi KHONG con lien ket tiep theo nao.

KHAC BIET CO CHU DICH voi `GenericIndexAdapter`: adapter do doc lien ket
chuong tu MOT (vai) trang muc luc RIENG (RE, khong lien quan noi dung
chuong that su). Adapter nay KHONG CO trang muc luc de doc re — `discover_series()`
O DAY THAT SU TAI TUNG TRANG CHUONG de tim lien ket tiep theo cua no, nghia
la CHI PHI kham pha VA chi phi quet la MOT — khong co "xem truoc re" that
su cho nguon dang nay.

CO Y GIOI HAN (`max_chapters`, mac dinh NHO — xem hang so ben duoi): kham
pha BI CHAN, khong theo duoi vo han. Nguon co NHIEU chuong hon gioi han se
CHI duoc kham pha MOT PHAN trong MOT lan goi `discover_series()` — ghi RO
trong `SeriesInfo.ordering_evidence`, KHONG am tham cat bot ma khong bao.
Day la danh doi CO CHU DICH giua "an toan/re cho preview" va "day du ngay
lan dau" — xem docstring `__init__.py` ve triet ly "khong con bao yeu cau".
"""
from __future__ import annotations

from typing import List, Optional
from urllib.parse import urljoin

from server.scraper.chapter_ordering import ChapterOrderingSignal, determine_order
from server.scraper.contract import (
    NormalizedChapter, ScraperTier, SeriesInfo, StoryProvider, canonicalize_url,
)
from server.scraper.content_extraction import extract_content_v3
from server.scraper.dedupe import content_hash, source_fingerprint
from server.scraper.html_extract import extract
from server.scraper.http_fetcher import FetchError

#: Mac dinh NHO co chu dich — du cho da so truyen ngan/vua trong MOT lan
#: kham pha, nhung KHONG de mot nguon that dai bien MOT lan goi
#: `discover_series()` (dung cho "xem truoc") thanh hang tram yeu cau HTTP
#: dong bo. Operator/ky su co the nang qua tham so constructor cho nguon
#: da biet la dai.
_MAC_DINH_MAX_CHUONG = 50


class NavigationOnlyAdapter(StoryProvider):
    tier = ScraperTier.DIRECT_HTTP

    def __init__(self, fetcher, *, next_href_pattern: str,
                 max_chapters: int = _MAC_DINH_MAX_CHUONG):
        """
        :param fetcher: xem `GenericIndexAdapter` — cung giao dien tiem vao.
        :param next_href_pattern: regex ap len href THO de nhan dien lien
            ket "chuong tiep theo" tren MOT trang chuong (vd
            `r"class=.next-chapter."` khong dung duoc — phai la mau khop
            TREN CHINH gia tri href, vi du `r"/chuong-\\d+$"` neu URL chuong
            tiep theo co dang do; hoac mot phan duong dan on dinh khac).
        :param max_chapters: chan tren SO CHUONG se kham pha trong MOT lan
            `discover_series()` — xem "CO Y GIOI HAN" o docstring module.
        """
        self._fetcher = fetcher
        self._next_re = __import__("re").compile(next_href_pattern)
        self._max_chapters = max_chapters
        self._boilerplate_chapter_urls_theo_hash: dict = {}

    def resolve(self, url: str) -> str:
        try:
            result = self._fetcher.fetch(url)
        except FetchError as exc:
            raise ValueError(str(exc)) from exc
        return canonicalize_url(result.final_url)

    def discover_series(self, url: str) -> SeriesInfo:
        first = self._fetcher.fetch(url)
        first_page = extract(first.text)
        title = (first_page.meta.get("og:title") or first_page.title
                or "(không có tiêu đề)")
        domain = canonicalize_url(first.final_url).split("/")[2]

        chapter_urls: List[str] = [first.final_url]
        da_tham = {canonicalize_url(first.final_url)}
        trang_hien_tai = first_page
        base_url = first.final_url
        bi_chan_boi_gioi_han = False

        while len(chapter_urls) < self._max_chapters:
            tiep_theo = self._tim_lien_ket_tiep_theo(trang_hien_tai, base_url, da_tham)
            if tiep_theo is None:
                break
            base_url, trang_hien_tai = tiep_theo
            chapter_urls.append(base_url)
        else:
            # Vong `while` dung vi DAT gioi han (khong phai vi het lien
            # ket) — CHI khi do moi thuc su "bi chan boi gioi han". Dung
            # ban KHONG TAI (`_co_lien_ket_tiep_theo_chua_tham`), KHONG
            # PHAI `_tim_lien_ket_tiep_theo` — ham do THAT SU tai them MOT
            # trang chi de "kiem tra", vuot qua chinh gioi han dang co
            # tinh kiem tra, VA neu lan tai do loi (mang) se lam HONG ca
            # lan `discover_series()` nay du da co du lieu hop le trong
            # tay — phat hien qua review doc lap (Codex).
            bi_chan_boi_gioi_han = self._co_lien_ket_tiep_theo_chua_tham(
                trang_hien_tai, base_url, da_tham)

        signals = [
            ChapterOrderingSignal(url=u, navigation_position=i)
            for i, u in enumerate(chapter_urls)
        ]
        ket_qua_thu_tu = determine_order(signals)
        evidence = ket_qua_thu_tu.evidence
        if bi_chan_boi_gioi_han:
            evidence += (
                f" LƯU Ý: đã dừng ở giới hạn {self._max_chapters} chương cho "
                "MỘT lần khám phá (nguồn này không có trang mục lục, phải "
                "tải từng trang chương để tìm chương tiếp theo) — nguồn có "
                "thể còn nhiều chương hơn nữa chưa được khám phá.")

        return SeriesInfo(
            canonical_url=canonicalize_url(first.final_url),
            title=title,
            source_domain=domain,
            author=first_page.meta.get("author") or first_page.meta.get("article:author"),
            description=(first_page.meta.get("og:description")
                        or first_page.meta.get("description")),
            chapter_urls=ket_qua_thu_tu.ordered_urls,
            ordering_evidence=evidence,
        )

    def _co_lien_ket_tiep_theo_chua_tham(self, trang, base_url: str, da_tham: set) -> bool:
        """KHONG TAI gi ca — chi quet `trang.links` (da co san trong bo
        nho) xem co href khop `next_href_pattern` VA CHUA tham hay khong.
        Dung khi CHI can biet "co con duong hay khong", khong can NOI DUNG
        trang tiep theo (xem `discover_series`'s nhanh `else`)."""
        for href, _text in trang.links:
            if not self._next_re.search(href):
                continue
            canon = canonicalize_url(urljoin(base_url, href))
            if canon not in da_tham:
                return True
        return False

    def _tim_lien_ket_tiep_theo(self, trang, base_url: str, da_tham: set):
        for href, _text in trang.links:
            if not self._next_re.search(href):
                continue
            absolute = urljoin(base_url, href)
            canon = canonicalize_url(absolute)
            if canon in da_tham:
                # Lien ket nay DA tham — KHONG dung ngay (mot trang co the
                # co CA lien ket "chuong truoc" LAN "chuong sau" cung khop
                # `next_href_pattern`, vd cung dang `/c/\d+`; neu "truoc"
                # xuat hien TRUOC "sau" trong HTML, dung ngay o day se lam
                # kham pha DUNG SAI HUONG hoac dung qua som — phat hien qua
                # review doc lap Codex). Bo qua, THU lien ket khop TIEP
                # THEO tren CUNG trang truoc khi ket luan "het duong".
                continue
            da_tham.add(canon)
            ket_qua = self._fetcher.fetch(absolute)
            return ket_qua.final_url, extract(ket_qua.text)
        return None

    def fetch_chapter(self, url: str) -> str:
        result = self._fetcher.fetch(url)
        return result.text

    def normalize_chapter(self, url: str, raw_html: str,
                           series: SeriesInfo) -> NormalizedChapter:
        page = extract(raw_html)
        title = page.meta.get("og:title") or page.title or series.title
        canon = canonicalize_url(url)

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
            # KHONG trich so chuong tu tieu de o day — nguon dang nay
            # thuong khong co danh sach de doi chieu, va viec trich lieu
            # linh (giong ly do da bo o GenericIndexAdapter voi Royal Road)
            # de bat nham so khac trong tieu de hon la giup ich; thu tu THAT
            # da duoc bao dam qua `chapter_ordering` (navigation_position).
            chapter_number=None,
            author=page.meta.get("author") or series.author,
            published_at=page.meta.get("article:published_time"),
            extraction_confidence=extraction_confidence,
        )

    _SO_LAN_LAP_TOI_THIEU_LA_BOILERPLATE = 2

    def _boilerplate_hashes_cho(self, canon_hien_tai: str) -> set:
        return {
            h for h, urls in self._boilerplate_chapter_urls_theo_hash.items()
            if len(urls - {canon_hien_tai}) >= self._SO_LAN_LAP_TOI_THIEU_LA_BOILERPLATE
        }

    def _ghi_nhan_doan_van_boilerplate(self, canon_hien_tai: str, hashes: set) -> None:
        for h in hashes:
            self._boilerplate_chapter_urls_theo_hash.setdefault(h, set()).add(canon_hien_tai)
