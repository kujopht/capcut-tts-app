"""Kiem thu `server/scraper/discovery.py` (Phase 2 Story Harvester V3) —
engine kham pha site CHUA cau hinh, dung `FixtureFetcher` de khong cham
mang that."""
from __future__ import annotations

import unittest

from server.scraper.discovery import (
    PaginationStrategy, SourceConfidence, UnknownSiteDiscoveryEngine,
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
