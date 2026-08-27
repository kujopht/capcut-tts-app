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
from server.scraper.dedupe import ScrapeState, content_hash
from server.scraper.html_extract import extract
from server.scraper.http_fetcher import FetchError, FetchResult, FixtureFetcher

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

    def test_tieu_de_khong_co_so_thi_chapter_number_la_None_khong_doan_tu_URL(self):
        """Phat hien qua review doc lap (Codex) tren cau hinh Royal Road:
        mot URL dang '/fiction/{id_truyen}/.../chapter/{id_chuong}/prologue'
        tung khien nhanh du phong bat NHAM id_truyen (so dau tien trong
        URL, thuong rat lon) lam chapter_number. Gio KHONG con doan tu
        URL nua — chuong khong co so trong tieu de la `None` that su."""
        from server.scraper.contract import SeriesInfo

        adapter = GenericIndexAdapter(
            FixtureFetcher({}), chapter_href_pattern=r"/fiction/12345/[^/\"]+/chapter/\d+/",
            title_suffix_to_strip=" | Royal Road")
        series = SeriesInfo(canonical_url="https://vd.example/fiction/12345/story",
                            title="Story", source_domain="vd.example", chapter_urls=[])
        html = ('<title>Prologue | Royal Road</title>'
                '<div class="chapter-content"><p>' + "x" * 250 + ".</p></div>")
        chapter = adapter.normalize_chapter(
            "https://vd.example/fiction/12345/story/chapter/987654/prologue", html, series)
        self.assertEqual(chapter.chapter_title, "Prologue")
        self.assertIsNone(chapter.chapter_number)


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


class PaginationTest(unittest.TestCase):
    """Muc luc trai dai qua NHIEU trang (vd `?page=1`, `?page=2`, ...) —
    tinh nang CONG THEM, tat mac dinh (xem docstring constructor)."""

    def _trang_muc_luc(self, so_trang: int, tong_so_trang: int, tien_to_chuong: str):
        chuong_html = "".join(
            f'<li><a href="/truyen/x/{tien_to_chuong}-{n}">Chương {n}</a></li>'
            for n in range((so_trang - 1) * 2 + 1, (so_trang - 1) * 2 + 3)
        )
        next_html = (
            f'<a href="/truyen/x?page={so_trang + 1}" class="next">Trang sau</a>'
            if so_trang < tong_so_trang else ""
        )
        return f"<html><body><ul>{chuong_html}</ul>{next_html}</body></html>"

    def _tao_adapter_phan_trang(self, pages: dict, max_index_pages: int = 20):
        return GenericIndexAdapter(
            FixtureFetcher(pages), chapter_href_pattern=r"/truyen/x/chuong-\d+",
            next_page_href_pattern=r"/truyen/x\?page=\d+", max_index_pages=max_index_pages)

    def test_gop_chuong_tu_nhieu_trang_muc_luc_THEO_DUNG_THU_TU(self):
        pages = {
            f"{_BASE}/truyen/x": self._trang_muc_luc(1, 3, "chuong"),
            f"{_BASE}/truyen/x?page=2": self._trang_muc_luc(2, 3, "chuong"),
            f"{_BASE}/truyen/x?page=3": self._trang_muc_luc(3, 3, "chuong"),
        }
        adapter = self._tao_adapter_phan_trang(pages)
        series = adapter.discover_series(f"{_BASE}/truyen/x")
        self.assertEqual(len(series.chapter_urls), 6, "3 trang x 2 chương/trang = 6")
        # Thu tu PHAI la 1..6, khong duoc dao lon giua cac trang.
        so_thu_tu = [int(u.rsplit("-", 1)[1]) for u in series.chapter_urls]
        self.assertEqual(so_thu_tu, [1, 2, 3, 4, 5, 6])

    def test_khong_cau_hinh_next_page_thi_CHI_lay_MOT_trang(self):
        # Hanh vi MAC DINH (khong next_page_href_pattern) phai giu nguyen —
        # day la phep hoi quy chong tinh nang moi lam vo hanh vi cu.
        pages = {
            f"{_BASE}/truyen/x": self._trang_muc_luc(1, 3, "chuong"),
            f"{_BASE}/truyen/x?page=2": self._trang_muc_luc(2, 3, "chuong"),
        }
        adapter = GenericIndexAdapter(
            FixtureFetcher(pages), chapter_href_pattern=r"/truyen/x/chuong-\d+")
        series = adapter.discover_series(f"{_BASE}/truyen/x")
        self.assertEqual(len(series.chapter_urls), 2, "không cấu hình pagination — chỉ trang đầu")

    def test_lien_ket_next_page_tro_ve_trang_da_tham_KHONG_lap_vo_han(self):
        # Trang 2 tro nguoc lai trang 1 (loi cau hinh site, hoac site that
        # co bug) — adapter phai DUNG, khong duoc treo.
        vong_lap = {
            f"{_BASE}/truyen/x": (
                '<html><body><li><a href="/truyen/x/chuong-1">C1</a></li>'
                '<a href="/truyen/x?page=2" class="next">Sau</a></body></html>'),
            f"{_BASE}/truyen/x?page=2": (
                '<html><body><li><a href="/truyen/x/chuong-2">C2</a></li>'
                '<a href="/truyen/x" class="next">Quay lại</a></body></html>'),
        }
        adapter = self._tao_adapter_phan_trang(vong_lap)
        series = adapter.discover_series(f"{_BASE}/truyen/x")
        self.assertEqual(len(series.chapter_urls), 2, "phải dừng sau khi phát hiện vòng lặp")

    def test_max_index_pages_chan_tren_dung_muc(self):
        pages = {f"{_BASE}/truyen/x": self._trang_muc_luc(1, 10, "chuong")}
        for i in range(2, 11):
            pages[f"{_BASE}/truyen/x?page={i}"] = self._trang_muc_luc(i, 10, "chuong")
        adapter = self._tao_adapter_phan_trang(pages, max_index_pages=3)
        series = adapter.discover_series(f"{_BASE}/truyen/x")
        self.assertEqual(len(series.chapter_urls), 6, "3 trang cho phép x 2 chương/trang")

    def test_lien_ket_chuong_trung_giua_cac_trang_van_duoc_gop(self):
        # Mot so site lap lai chuong dau cua trang truoc o cuoi trang sau
        # (dieu huong "tiep tuc doc") — khong duoc nhan doi qua bien trang.
        pages = {
            f"{_BASE}/truyen/x": (
                '<html><body><li><a href="/truyen/x/chuong-1">C1</a></li>'
                '<a href="/truyen/x?page=2" class="next">Sau</a></body></html>'),
            f"{_BASE}/truyen/x?page=2": (
                '<html><body>'
                '<li><a href="/truyen/x/chuong-1">C1 (lặp lại)</a></li>'
                '<li><a href="/truyen/x/chuong-2">C2</a></li>'
                '</body></html>'),
        }
        adapter = self._tao_adapter_phan_trang(pages)
        series = adapter.discover_series(f"{_BASE}/truyen/x")
        self.assertEqual(len(series.chapter_urls), 2)


class RobustnessTest(unittest.TestCase):
    """Cac tinh huong trang THAT thuong gap: HTML hong, than trang rong,
    JSON-LD hong, lien ket trung, va Unicode tieng Viet — Tier 0 phai song
    sot TAT CA ma khong nem loi (mot trang xau khong duoc lam hong ca crawl)."""

    def test_the_khong_dong_khong_lam_hong_trich_xuat(self):
        # <p> khong dong, <div> long nhau khong dong — html.parser (stdlib)
        # von da khoan dung, nhung day la bang chung TUONG MINH cho hanh vi
        # do o tang extract() cua chinh du an, khong chi tin vao stdlib.
        html = (
            "<html><body><div><p>Đoạn một chưa đóng"
            "<p>Đoạn hai cũng chưa đóng<div>Lồng thêm không đóng"
            "</body></html>"
        )
        page = extract(html)  # KHONG duoc nem loi
        self.assertIn("Đoạn một chưa đóng", page.visible_text())
        self.assertIn("Đoạn hai cũng chưa đóng", page.visible_text())

    def test_than_trang_rong_khong_lam_hong_extract(self):
        page = extract("")
        self.assertEqual(page.visible_text(), "")
        self.assertIsNone(page.title)
        # content_hash cua chuoi rong la mot gia tri xac dinh, khong loi.
        self.assertEqual(len(content_hash(page.visible_text())), 64)

    def test_khoi_json_ld_hong_bi_bo_qua_am_tham_khong_lam_hong_trang(self):
        html = (
            '<html><head><script type="application/ld+json">'
            "{khong phai JSON hop le,,,}"
            "</script></head><body><p>Nội dung vẫn đọc được bình thường."
            "</p></body></html>"
        )
        page = extract(html)  # KHONG duoc nem loi du JSON-LD hong
        self.assertEqual(page.json_ld, [])
        self.assertIn("Nội dung vẫn đọc được bình thường", page.visible_text())

    def test_lien_ket_chuong_trung_lap_tren_cung_trang_muc_luc_bi_gop(self):
        # Mot so site lap lai link chuong trong ca ban desktop lan mobile
        # cua cung mot trang — discover_series khong duoc dem hai lan.
        html_muc_luc = (
            '<html><body><ul class="desktop">'
            '<li><a href="/truyen/x/chuong-1">Chương 1</a></li>'
            "</ul>"
            '<ul class="mobile">'
            '<li><a href="/truyen/x/chuong-1">Chương 1</a></li>'
            "</ul></body></html>"
        )
        pages = {f"{_BASE}/truyen/x": html_muc_luc}
        adapter = GenericIndexAdapter(FixtureFetcher(pages), chapter_href_pattern=r"/chuong-\d+")
        series = adapter.discover_series(f"{_BASE}/truyen/x")
        self.assertEqual(len(series.chapter_urls), 1,
                         "link chuong trung lap (desktop+mobile) phai duoc gop, khong nhan doi")

    def test_tieng_viet_co_dau_dich_hash_on_dinh_qua_nhieu_lan_chay(self):
        html = (
            "<html><body><p>Chương thử: Nguyễn Thị Bích Ngọc gặp lại "
            "người xưa ở Đà Lạt, trời se lạnh, sương giăng khắp lối."
            "</p></body></html>"
        )
        text_1 = extract(html).visible_text()
        text_2 = extract(html).visible_text()
        self.assertEqual(text_1, text_2)
        self.assertEqual(content_hash(text_1), content_hash(text_2))
        self.assertIn("Nguyễn Thị Bích Ngọc", text_1)

    def test_content_type_khong_phai_van_ban_bi_tu_choi_truoc_khi_parse(self):
        """Mot URL tra ve `image/jpeg` (vd link chuong bi hong, tro nham vao
        anh bia) khong duoc dua qua html.parser — se ra "van ban" vo nghia
        ma khong ai phat hien duoc o tang tren. Phai FetchError NGAY."""
        class _FetcherAnhGia:
            def fetch(self, url):
                return FetchResult(final_url=url, status_code=200,
                                    content_type="image/jpeg", text="\xff\xd8\xff...")

        adapter = GenericIndexAdapter(_FetcherAnhGia(), chapter_href_pattern=r"/chuong-\d+")
        with self.assertRaises(FetchError):
            adapter.fetch_chapter(f"{_BASE}/truyen/x/chuong-1")
        with self.assertRaises(FetchError):
            adapter.discover_series(f"{_BASE}/truyen/x")

    def test_doi_TIEU_DE_ma_giu_nguyen_noi_dung_KHONG_bi_coi_la_revision(self):
        """`content_hash` chi tinh tren `clean_text` (than bai, khong gom
        tieu de) — day la HANH VI CO CHU DICH, khong phai loi: tieu de la
        SIEU DU LIEU hien thi, revision-detection quan tam NOI DUNG doc
        duoc thay doi. Ghi lai tuong minh de khong ai "sua" nham sau nay."""
        state = ScrapeState()
        than_bai = "Nội dung không đổi giữa hai lần cào."
        state.record_success(f"{_BASE}/truyen/x/chuong-1",
                              content_hash_value=content_hash(than_bai))
        ban_ghi = state.record_success(f"{_BASE}/truyen/x/chuong-1",
                                        content_hash_value=content_hash(than_bai))
        self.assertFalse(ban_ghi.get("is_revision"),
                         "than bai khong doi (du tieu de nguon co doi o ngoai) "
                         "khong duoc bao la revision")


if __name__ == "__main__":
    unittest.main()
