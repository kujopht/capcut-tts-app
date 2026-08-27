"""Kiem thu `server/scraper/discovery.py` (Phase 2 Story Harvester V3) —
engine kham pha site CHUA cau hinh, dung `FixtureFetcher` de khong cham
mang that."""
from __future__ import annotations

import unittest

import re

from server.scraper.discovery import (
    PaginationStrategy, SourceConfidence, UnknownSiteDiscoveryEngine, _scan_content_container,
)
from server.scraper.http_fetcher import FixtureFetcher

_INDEX_URL = "https://vidu-truyen.test/truyen/mot-truyen-hay"
_CHAPTER_1 = "https://vidu-truyen.test/truyen/mot-truyen-hay/chuong-1"
_CHAPTER_2 = "https://vidu-truyen.test/truyen/mot-truyen-hay/chuong-2"
_CHAPTER_3 = "https://vidu-truyen.test/truyen/mot-truyen-hay/chuong-3"


def _index_html(chapter_links: str = "") -> str:
    links = chapter_links or "\n".join(
        f'<li><a href="/truyen/mot-truyen-hay/chuong-{i}">Chương {i}</a></li>'
        for i in range(1, 6)
    )
    return f"""
    <html><head>
      <title>Một Truyện Hay - Trang Chủ</title>
      <meta property="og:title" content="Một Truyện Hay">
      <meta property="og:description" content="Mô tả truyện hay ho.">
      <meta name="author" content="Tác Giả X">
      <script type="application/ld+json">
        {{"@type": "Book", "name": "Một Truyện Hay", "author": {{"name": "Tác Giả X"}}}}
      </script>
    </head><body>
      <nav><a href="/gioi-thieu">Giới thiệu</a><a href="/lien-he">Liên hệ</a></nav>
      <ul>{links}</ul>
      <footer><a href="/rss">RSS</a></footer>
    </body></html>
    """


_CHAPTER_HTML = """
<html><head><title>Chương 1 - Một Truyện Hay</title></head>
<body>
  <nav>menu linh tinh</nav>
  <div class="chapter-content">
    <p>Đây là đoạn văn bản đầu tiên của chương một, đủ dài để vượt ngưỡng
    tối thiểu cho một vùng nội dung hợp lệ trong bộ kiểm tra này.</p>
    <p>Một đoạn văn thứ hai để tăng thêm độ dài văn bản hiển thị bên trong
    vùng nội dung, tránh bị coi là quá ngắn so với ngưỡng đã đặt ra.</p>
  </div>
  <footer>chân trang linh tinh</footer>
</body></html>
"""


def _engine(pages: dict) -> UnknownSiteDiscoveryEngine:
    return UnknownSiteDiscoveryEngine(FixtureFetcher(pages))


class HighConfidenceTest(unittest.TestCase):
    def test_cum_lien_ket_ro_rang_co_content_container_ra_HIGH(self):
        pages = {
            _INDEX_URL: _index_html(),
            _CHAPTER_1: _CHAPTER_HTML,
        }
        proposal = _engine(pages).discover(_INDEX_URL)

        assert proposal.confidence == SourceConfidence.HIGH
        assert proposal.chapter_count_estimate == 5
        assert proposal.chapter_url_pattern is not None
        assert proposal.content_container_candidate == "div.chapter-content"
        assert proposal.work_title == "Một Truyện Hay"
        assert proposal.author == "Tác Giả X"
        assert proposal.fetch_tier.name == "DIRECT_HTTP"
        assert proposal.sample_chapter_urls[0] == _CHAPTER_1
        assert any("JSON-LD" in e for e in proposal.evidence)


class MediumConfidenceTest(unittest.TestCase):
    def test_cum_du_nho_nhung_khong_co_trang_chuong_mau_ra_MEDIUM(self):
        links = "\n".join(
            f'<li><a href="/truyen/mot-truyen-hay/chuong-{i}">Chương {i}</a></li>'
            for i in range(1, 4)
        )
        pages = {_INDEX_URL: _index_html(links)}
        proposal = _engine(pages).discover(_INDEX_URL)

        assert proposal.confidence == SourceConfidence.MEDIUM
        assert proposal.chapter_count_estimate == 3
        assert proposal.content_container_candidate is None
        assert any("Không tải được" in e for e in proposal.evidence)


class LowConfidenceTest(unittest.TestCase):
    def test_khong_co_cum_lien_ket_lap_lai_ra_LOW_khong_doan_pattern(self):
        html = """
        <html><head><title>Trang không rõ ràng</title></head>
        <body>
          <a href="/a">Một liên kết</a>
          <a href="/b">Liên kết khác</a>
        </body></html>
        """
        pages = {_INDEX_URL: html}
        proposal = _engine(pages).discover(_INDEX_URL)

        assert proposal.confidence == SourceConfidence.LOW
        assert proposal.chapter_url_pattern is None
        assert proposal.chapter_count_estimate == 0
        assert proposal.sample_chapter_urls == []

    def test_trang_gan_nhu_rong_co_ghi_chu_co_the_can_JS_nhung_khong_tu_nang_tier(self):
        html = "<html><head><title>Rỗng</title></head><body></body></html>"
        pages = {_INDEX_URL: html}
        proposal = _engine(pages).discover(_INDEX_URL)

        assert proposal.confidence == SourceConfidence.LOW
        assert proposal.fetch_tier.name == "DIRECT_HTTP"
        assert any("JavaScript" in e for e in proposal.evidence)


class ClusterVsNoiseTest(unittest.TestCase):
    def test_menu_chia_se_hai_lien_ket_giong_nhau_khong_bi_coi_la_cum_chuong(self):
        html = _index_html("") .replace(
            "<nav>", '<nav><a href="/share?x=1">Chia sẻ</a><a href="/share?x=2">Chia sẻ 2</a>',
        )
        pages = {_INDEX_URL: html, _CHAPTER_1: _CHAPTER_HTML}
        proposal = _engine(pages).discover(_INDEX_URL)

        # 5 chuong van la cum thang (>=3), khong bi 2 lien ket "share" gay nham.
        assert proposal.chapter_count_estimate == 5

    def test_cum_khong_phai_chuong_nhung_co_so_khong_duoc_dat_HIGH(self):
        """Tai hien that phat hien tu review doc lap (Codex): mot trang CHI
        co mot cum lien ket "chia sẻ" (khong phai chuong) nhung van ban
        lien ket co so (1..5) — truoc khi co `_word_fraction` (Phase 2 sua
        loi), cum nay du diem de dat HIGH chi vi "co so" duoc tinh nhu tin
        hieu chuong that. Trang chuong mau (`_CHAPTER_1`) van co vung noi
        dung hop le (dieu kien HIGH khac van dat duoc) — CHI thieu tu khoa
        chuong that trong van ban cum, phai bi chan o MEDIUM."""
        html = f"""
        <html><head><title>Trang Chia Sẻ</title>
        <meta property="og:title" content="Trang Chia Sẻ">
        <script type="application/ld+json">
          {{"@type": "Book", "name": "Trang Chia Sẻ"}}
        </script>
        </head><body>
        <ul>{"".join(f'<li><a href="/share?x={i}">{i}</a></li>' for i in range(1, 6))}</ul>
        </body></html>
        """
        # href la duong dan TUYET DOI ("/share?x=1") nen urljoin() ra domain
        # goc, KHONG phai duoi `_INDEX_URL` — dung URL "chuong mau" DUNG mau
        # cum de discovery that su fetch no, giu nguyen vung noi dung hop le.
        pages = {_INDEX_URL: html, "https://vidu-truyen.test/share?x=1": _CHAPTER_HTML}
        proposal = UnknownSiteDiscoveryEngine(FixtureFetcher(pages)).discover(_INDEX_URL)

        assert proposal.chapter_count_estimate == 5
        assert proposal.confidence != SourceConfidence.HIGH
        assert any("KHÔNG liên kết nào" in e for e in proposal.evidence)


class PaginationDetectionTest(unittest.TestCase):
    def test_lien_ket_next_rel_duoc_nhan_dien(self):
        html = _index_html().replace(
            "</ul>", '</ul><a rel="next" href="/truyen/mot-truyen-hay?page=2">Tiếp theo</a>')
        pages = {_INDEX_URL: html, _CHAPTER_1: _CHAPTER_HTML}
        proposal = _engine(pages).discover(_INDEX_URL)

        assert proposal.pagination_strategy == PaginationStrategy.NEXT_PREV

    def test_khong_co_dau_hieu_phan_trang_ra_NONE(self):
        pages = {_INDEX_URL: _index_html(), _CHAPTER_1: _CHAPTER_HTML}
        proposal = _engine(pages).discover(_INDEX_URL)

        assert proposal.pagination_strategy == PaginationStrategy.NONE


class CanonicalUrlTest(unittest.TestCase):
    def test_uu_tien_link_rel_canonical_hon_final_url(self):
        html = _index_html().replace(
            "<head>",
            '<head><link rel="canonical" href="https://vidu-truyen.test/truyen/mot-truyen-hay/">')
        pages = {_INDEX_URL: html, _CHAPTER_1: _CHAPTER_HTML}
        proposal = _engine(pages).discover(_INDEX_URL)

        assert proposal.canonical_url == "https://vidu-truyen.test/truyen/mot-truyen-hay"

    def test_canonical_khac_domain_bi_bo_qua_dung_final_url(self):
        """Tai hien phat hien tu review doc lap (Codex): mot trang khai bao
        `<link rel="canonical">` tro SANG DOMAIN KHAC — chap nhan gia tri
        do se khien SiteProfile sau nay luu duoi TEN domain khac ("dau
        doc"). Phai bo qua, dung `final_url` that."""
        html = _index_html().replace(
            "<head>", '<head><link rel="canonical" href="https://evil.test/hijacked">')
        pages = {_INDEX_URL: html, _CHAPTER_1: _CHAPTER_HTML}
        proposal = _engine(pages).discover(_INDEX_URL)

        assert proposal.canonical_url == _INDEX_URL
        assert "evil.test" not in proposal.canonical_url


class SsrfGuardTest(unittest.TestCase):
    def test_chuong_mau_khac_domain_khong_duoc_tu_dong_tai(self):
        """Tai hien phat hien tu review doc lap (Codex, dat ten "SSRF"):
        href chuong LA NOI DUNG TRANG (nguoi khac kiem soat), khong phai
        url operator tu dan — mot href tro sang domain KHAC (vd noi bo/
        dich vu khac) khong duoc tu dong tai."""
        links = "".join(
            f'<li><a href="https://noi-khac.test/x?i={i}">Chương {i}</a></li>'
            for i in range(1, 6)
        )
        html = _index_html(links)
        # KHONG dua trang o "noi-khac.test" vao fixture — neu engine LO tai
        # no, `FixtureFetcher` se nem `FetchError` (khong co trang), that
        # bai ro rang thay vi am tham "thanh cong" theo huong sai.
        pages = {_INDEX_URL: html}
        proposal = _engine(pages).discover(_INDEX_URL)

        assert proposal.content_container_candidate is None
        assert proposal.confidence != SourceConfidence.HIGH
        assert any("domain khác" in e for e in proposal.evidence)


class QueryStringPatternTest(unittest.TestCase):
    def test_chuong_danh_so_qua_query_string_ra_mau_co_neo_dung(self):
        """Tai hien phat hien tu review doc lap (Codex): chuong khac nhau
        CHI o query string (`?chapter=N`), PATH giong het nhau — truoc sua
        loi, mau de xuat la chuoi van ban KHONG neo (`/doc`), khop NHAM bat
        ky href nao chua no lam chuoi con."""
        links = "".join(
            f'<li><a href="/doc?chapter={i}">Chương {i}</a></li>' for i in range(1, 6))
        html = _index_html(links)
        pages = {_INDEX_URL: html, "https://vidu-truyen.test/doc?chapter=1": _CHAPTER_HTML}
        proposal = _engine(pages).discover(_INDEX_URL)

        assert proposal.chapter_count_estimate == 5
        assert proposal.chapter_url_pattern is not None
        assert re.search(proposal.chapter_url_pattern, "/doc?chapter=1")
        # Mau KHONG duoc khop NHAM mot href khong lien quan chi vi chua
        # chuoi con "/doc" — day chinh la loi da sua (mau khong neo).
        assert not re.search(proposal.chapter_url_pattern, "/doc-khac-hoan-toan")
        assert not re.search(proposal.chapter_url_pattern, "/tai-lieu/doc")


class ContainerAggregationTest(unittest.TestCase):
    def test_nhieu_widget_nho_rieng_biet_khong_cong_don_thanh_ung_vien_gia(self):
        """Tai hien phat hien tu review doc lap (Codex): nhieu the
        `<div class="content-item">` RIENG BIET (vd khung "bai viet lien
        quan"), moi the CHI 30 ky tu (duoi nguong), nhung TONG CONG (5 the
        x 30 = 150, hoac du de vuot nguong khi cong don sai) truoc day bi
        tinh gop thanh MOT ung vien "hop le" — trong khi KHONG the nao
        THAT SU du dai."""
        widgets = "".join(
            f'<div class="content-item">Đoạn văn bản ngắn thứ {i} đây thôi.</div>'
            for i in range(1, 8)
        )
        html = f"<html><body>{widgets}</body></html>"

        candidate, _ratio = _scan_content_container(html)
        assert candidate is None, (
            "Nhiều widget nhỏ riêng biệt không được cộng dồn thành một ứng viên giả")

    def test_mot_the_duy_nhat_du_dai_van_duoc_nhan_dien(self):
        """Doi chung voi test tren: MOT the DUY NHAT du dai (khong phai
        nhieu the nho cong don) van phai duoc nhan dien binh thuong."""
        html = (
            '<html><body><div class="chapter-content">'
            + "Một đoạn văn bản đủ dài để vượt ngưỡng tối thiểu cho một vùng "
              "nội dung hợp lệ trong bộ kiểm tra này, viết thêm cho chắc chắn "
              "vượt hẳn hai trăm ký tự yêu cầu, cộng thêm một câu nữa cho thật "
              "chắc chắn là đã vượt xa hai trăm ký tự tối thiểu cần có."
            + "</div></body></html>"
        )
        candidate, _ratio = _scan_content_container(html)
        assert candidate == "div.chapter-content"


class NumberedPaginationPatternTest(unittest.TestCase):
    def test_numbered_pages_co_next_page_url_pattern(self):
        html = _index_html().replace(
            "</ul>",
            "</ul>" + "".join(
                f'<a href="/truyen/mot-truyen-hay?page={i}">{i}</a>' for i in range(2, 5)),
        )
        pages = {_INDEX_URL: html, _CHAPTER_1: _CHAPTER_HTML}
        proposal = _engine(pages).discover(_INDEX_URL)

        assert proposal.pagination_strategy == PaginationStrategy.NUMBERED_PAGES
        assert proposal.next_page_url_pattern is not None
        assert re.search(proposal.next_page_url_pattern, "/truyen/mot-truyen-hay?page=2")
