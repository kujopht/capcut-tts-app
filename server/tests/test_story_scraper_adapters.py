"""
Universal Story Scraper — kiem thu adapter Tier 0 tren fixture CUC BO
(server/tests/fixtures/scraper/), KHONG cham mang that. Chung minh: kham
pha series, thu tu chuong, trich xuat van ban, rerun idempotent, resume
sau gian doan mo phong, va uu tien JSON-LD khi co.
"""
import os
import unittest

from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
from server.scraper.adapters.json_ld_adapter import JsonLdAwareAdapter
from server.scraper.dedupe import ScrapeState
from server.scraper.http_fetcher import FixtureFetcher

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "scraper")


def _doc_fixture(ten: str) -> str:
    with open(os.path.join(_FIXTURES, ten), encoding="utf-8") as f:
        return f.read()


_BASE = "https://vd-truyen.example"
_PAGES = {
    f"{_BASE}/truyen/thu-nghiem": _doc_fixture("index.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-1": _doc_fixture("chuong-1.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-2": _doc_fixture("chuong-2.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-3": _doc_fixture("chuong-3.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-jsonld": _doc_fixture("chuong-jsonld.html"),
}


def _tao_adapter(cls=GenericIndexAdapter):
    fetcher = FixtureFetcher(_PAGES)
    return cls(fetcher, chapter_href_pattern=r"/chuong-\d+",
               title_suffix_to_strip=" - Trang Web Giả")


class SeriesDiscoveryTest(unittest.TestCase):
    def test_kham_pha_series_dung_tieu_de_va_mo_ta(self):
        adapter = _tao_adapter()
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")
        self.assertEqual(series.title, "Truyện Thử Nghiệm")
        self.assertEqual(series.author, "Tác Giả Ẩn Danh")
        self.assertIn("kiểm thử", series.description)

    def test_danh_sach_chuong_DUNG_THU_TU_hien_thi_khong_bi_sap_lai(self):
        adapter = _tao_adapter()
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")
        # Fixture liet ke chuong 1, 2, 3 THEO DUNG thu tu do trong HTML —
        # adapter khong duoc tu sap lai (vi du theo alpha) lam sai thu tu that.
        self.assertEqual(len(series.chapter_urls), 3)
        self.assertTrue(series.chapter_urls[0].endswith("chuong-1"))
        self.assertTrue(series.chapter_urls[1].endswith("chuong-2"))
        self.assertTrue(series.chapter_urls[2].endswith("chuong-3"))

    def test_lien_ket_dieu_huong_khong_khop_mau_KHONG_bi_coi_la_chuong(self):
        adapter = _tao_adapter()
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")
        for url in series.chapter_urls:
            self.assertNotIn("/lien-he", url)
            self.assertNotIn("/the-loai", url)


class ChapterExtractionTest(unittest.TestCase):
    def test_trich_xuat_van_ban_sach_bo_script_va_dieu_huong(self):
        adapter = _tao_adapter()
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")
        url = series.chapter_urls[0]
        raw = adapter.fetch_chapter(url)
        chapter = adapter.normalize_chapter(url, raw, series)

        self.assertEqual(chapter.chapter_title, "Chương 1: Khởi đầu")
        self.assertIn("đoạn văn đầu tiên", chapter.clean_text)
        self.assertNotIn("trackingPixel", chapter.clean_text)
        self.assertNotIn("Bản quyền thuộc", chapter.clean_text,
                          "noi dung footer khong duoc lan vao noi dung chuong")
        self.assertNotIn("Trang chủ", chapter.clean_text,
                          "lien ket dieu huong (nav) khong duoc lan vao noi dung chuong")

    def test_so_chuong_trich_tu_tieu_de(self):
        adapter = _tao_adapter()
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")
        url = series.chapter_urls[1]
        chapter = adapter.normalize_chapter(url, adapter.fetch_chapter(url), series)
        self.assertEqual(chapter.chapter_number, 2)


class IdempotentRerunTest(unittest.TestCase):
    def test_chay_lai_cung_url_ra_cung_content_hash_va_fingerprint(self):
        adapter = _tao_adapter()
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")
        url = series.chapter_urls[0]

        lan_1 = adapter.normalize_chapter(url, adapter.fetch_chapter(url), series)
        lan_2 = adapter.normalize_chapter(url, adapter.fetch_chapter(url), series)

        self.assertEqual(lan_1.content_hash, lan_2.content_hash)
        self.assertEqual(lan_1.source_fingerprint, lan_2.source_fingerprint)


class ResumeAfterInterruptionTest(unittest.TestCase):
    def test_resume_bo_qua_chuong_da_xong_chi_lam_chuong_con_lai(self):
        """Mo phong: crawl bi ngat giua chung sau khi da xu ly xong chuong 1 —
        `resume()` phai chi tra ve chuong 2 va 3, khong lam lai chuong 1."""
        adapter = _tao_adapter()
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")

        state = ScrapeState()
        chuong_1 = series.chapter_urls[0]
        ket_qua_1 = adapter.normalize_chapter(chuong_1, adapter.fetch_chapter(chuong_1), series)
        state.record_success(chuong_1, content_hash_value=ket_qua_1.content_hash,
                              chapter_number=ket_qua_1.chapter_number)

        con_lai = adapter.resume(state, series.chapter_urls)
        self.assertEqual(len(con_lai), 2)
        self.assertNotIn(chuong_1, con_lai)

    def test_resume_thu_lai_chuong_da_that_bai_lan_truoc(self):
        adapter = _tao_adapter()
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")
        state = ScrapeState()
        chuong_1 = series.chapter_urls[0]
        state.record_failure(chuong_1)

        con_lai = adapter.resume(state, series.chapter_urls)
        self.assertIn(chuong_1, con_lai, "chuong that bai lan truoc PHAI duoc thu lai")


class JsonLdPreferenceTest(unittest.TestCase):
    def test_uu_tien_JSON_LD_hon_van_ban_hien_thi_khi_co(self):
        adapter = _tao_adapter(JsonLdAwareAdapter)
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")
        url = f"{_BASE}/truyen/thu-nghiem/chuong-jsonld"
        chapter = adapter.normalize_chapter(url, adapter.fetch_chapter(url), series)

        self.assertEqual(chapter.chapter_title, "Chương JSON-LD: Dữ liệu có cấu trúc")
        self.assertIn("không phải từ văn bản hiển thị lộn xộn", chapter.clean_text)
        self.assertNotIn("Quảng cáo không liên quan", chapter.clean_text)
        self.assertEqual(chapter.author, "Tác Giả JSON-LD")
        self.assertEqual(chapter.published_at, "2026-01-01T00:00:00Z")

    def test_khong_co_JSON_LD_thi_roi_ve_van_ban_hien_thi_binh_thuong(self):
        """Trang KHONG co JSON-LD (da test o ChapterExtractionTest) khong
        duoc phep loi hay tra ve rong — phai roi ve dung hanh vi cua
        GenericIndexAdapter."""
        adapter = _tao_adapter(JsonLdAwareAdapter)
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")
        url = series.chapter_urls[0]
        chapter = adapter.normalize_chapter(url, adapter.fetch_chapter(url), series)
        self.assertIn("đoạn văn đầu tiên", chapter.clean_text)


if __name__ == "__main__":
    unittest.main()
