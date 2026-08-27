"""Kiem thu `server/scraper/adapters/navigation_only_adapter.py` (Phase 3
Story Harvester V3, bien the "next/prev-navigation-only sources") — nguon
KHONG co trang muc luc, chi theo doi lien ket "chuong tiep theo" tuan tu."""
from __future__ import annotations

import unittest

from server.scraper.adapters.navigation_only_adapter import NavigationOnlyAdapter
from server.scraper.chapter_ordering import OrderingSource
from server.scraper.http_fetcher import FixtureFetcher

_BASE = "https://nav-truyen.example"


def _trang(so: int, tiep_theo: int | None) -> str:
    lien_ket_tiep = (
        f'<a class="next" href="/c/{tiep_theo}">Chương tiếp theo</a>'
        if tiep_theo is not None else "")
    return f"""
    <html><head><title>Chương {so} - Truyện Điều Hướng</title>
    <meta property="og:title" content="Truyện Điều Hướng"></head>
    <body>
      <div class="chapter-content">
        <p>Nội dung chương {so}, đủ dài để vượt ngưỡng tối thiểu cho một
        vùng nội dung hợp lệ trong bộ kiểm thử điều hướng tuần tự này.</p>
      </div>
      {lien_ket_tiep}
    </body></html>
    """


def _pages(so_chuong: int) -> dict:
    return {
        f"{_BASE}/c/{i}": _trang(i, i + 1 if i < so_chuong else None)
        for i in range(1, so_chuong + 1)
    }


class DiscoverySequenceTest(unittest.TestCase):
    def test_theo_doi_next_link_tuan_tu_dung_thu_tu(self):
        pages = _pages(5)
        adapter = NavigationOnlyAdapter(FixtureFetcher(pages), next_href_pattern=r"/c/\d+")
        series = adapter.discover_series(f"{_BASE}/c/1")

        self.assertEqual(len(series.chapter_urls), 5)
        for i, url in enumerate(series.chapter_urls, start=1):
            self.assertTrue(url.endswith(f"/c/{i}"))
        self.assertIn("theo dõi liên kết", series.ordering_evidence)

    def test_dung_lai_khi_khong_con_lien_ket_tiep_theo(self):
        pages = _pages(3)
        adapter = NavigationOnlyAdapter(FixtureFetcher(pages), next_href_pattern=r"/c/\d+")
        series = adapter.discover_series(f"{_BASE}/c/1")
        self.assertEqual(len(series.chapter_urls), 3)

    def test_vong_lap_tu_tro_khong_treo_vo_han(self):
        """Trang cuoi TRO NGUOC lai chinh no (loi cau hinh nguon that) —
        phai dung, khong duoc treo vo han."""
        pages = _pages(3)
        # Ghi de chuong 3: lien ket "tiep theo" tro VE CHINH NO.
        pages[f"{_BASE}/c/3"] = _trang(3, 3)
        adapter = NavigationOnlyAdapter(FixtureFetcher(pages), next_href_pattern=r"/c/\d+")
        series = adapter.discover_series(f"{_BASE}/c/1")
        self.assertEqual(len(series.chapter_urls), 3)


class MaxChaptersLimitTest(unittest.TestCase):
    def test_gioi_han_max_chapters_dung_lai_va_ghi_ro_trong_evidence(self):
        pages = _pages(10)
        adapter = NavigationOnlyAdapter(
            FixtureFetcher(pages), next_href_pattern=r"/c/\d+", max_chapters=5)
        series = adapter.discover_series(f"{_BASE}/c/1")

        self.assertEqual(len(series.chapter_urls), 5)
        self.assertIn("LƯU Ý", series.ordering_evidence)
        self.assertIn("giới hạn 5 chương", series.ordering_evidence)

    def test_khong_vuot_gioi_han_thi_khong_co_ghi_chu_gioi_han(self):
        pages = _pages(3)
        adapter = NavigationOnlyAdapter(
            FixtureFetcher(pages), next_href_pattern=r"/c/\d+", max_chapters=5)
        series = adapter.discover_series(f"{_BASE}/c/1")

        self.assertEqual(len(series.chapter_urls), 3)
        self.assertNotIn("LƯU Ý", series.ordering_evidence)


class NormalizeChapterTest(unittest.TestCase):
    def test_trich_xuat_noi_dung_va_khong_doan_so_chuong(self):
        pages = _pages(2)
        adapter = NavigationOnlyAdapter(FixtureFetcher(pages), next_href_pattern=r"/c/\d+")
        series = adapter.discover_series(f"{_BASE}/c/1")

        url = series.chapter_urls[0]
        raw = adapter.fetch_chapter(url)
        chapter = adapter.normalize_chapter(url, raw, series)

        self.assertIn("Nội dung chương 1", chapter.clean_text)
        self.assertIsNone(chapter.chapter_number)
        self.assertEqual(chapter.series_title, "Truyện Điều Hướng")

    def test_resolve_tra_ve_canonical_url(self):
        pages = _pages(1)
        adapter = NavigationOnlyAdapter(FixtureFetcher(pages), next_href_pattern=r"/c/\d+")
        self.assertEqual(adapter.resolve(f"{_BASE}/c/1"), f"{_BASE}/c/1")
