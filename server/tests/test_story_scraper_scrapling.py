"""
Universal Story Scraper — Tier 1 (`ScraplingAdapter`). Cung mo hinh fixture
cuc bo voi Tier 0 (`server/tests/test_story_scraper_adapters.py`), CONG
THEM cac kich ban ma chinh Tier 1 duoc dua vao de xu ly: DOM doi cau truc
HOAN TOAN (chi Scrapling moi song sot), HTML loi dinh dang, phan trang,
chuong doi thu tu, va noi dung nguon bi sua (revision) — tat ca kiem qua
chinh adapter nay, khong chi qua `dedupe.py` don le.
"""
import gc
import os
import tempfile
import unittest

from server.scraper.adapters.scrapling_adapter import ScraplingAdapter
from server.scraper.dedupe import ScrapeState
from server.scraper.http_fetcher import FixtureFetcher

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "scraper")


def _doc_fixture(ten: str) -> str:
    with open(os.path.join(_FIXTURES, ten), encoding="utf-8") as f:
        return f.read()


_BASE = "https://vd-truyen.example"


def _tao_adapter(pages, storage_file=None):
    fetcher = FixtureFetcher(pages)
    return ScraplingAdapter(
        fetcher, chapter_href_pattern=r"/chuong-\d+",
        title_suffix_to_strip=" - Trang Web Giả",
        storage_file=storage_file,
    )


class BaselineParityTest(unittest.TestCase):
    """Tren fixture BINH THUONG (khong doi cau truc), Tier 1 phai cho ket
    qua tuong duong Tier 0 — no khong duoc kem hon o truong hop de."""

    def test_kham_pha_series_va_trich_xuat_chuong_binh_thuong(self):
        pages = {
            f"{_BASE}/truyen/thu-nghiem": _doc_fixture("index.html"),
            f"{_BASE}/truyen/thu-nghiem/chuong-1": _doc_fixture("chuong-1.html"),
        }
        adapter = _tao_adapter(pages)
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")
        self.assertEqual(series.title, "Truyện Thử Nghiệm")
        self.assertEqual(len(series.chapter_urls), 3)

        url = series.chapter_urls[0]
        chapter = adapter.normalize_chapter(url, adapter.fetch_chapter(url), series)
        self.assertEqual(chapter.chapter_title, "Chương 1: Khởi đầu")
        self.assertIn("đoạn văn đầu tiên", chapter.clean_text)
        self.assertNotIn("trackingPixel", chapter.clean_text)


class ChangedDomRelocateTest(unittest.TestCase):
    """Kich ban Tier 1 DUOC DUA VAO de xu ly: site doi HET class/the bao
    VA doi ca duong dan chuong giua hai lan quet. Mau href CU khong con
    khop lien ket nao — chi `.relocate()` (dua tren dau van tay da luu tu
    lan quet truoc) moi con tim dung khu vuc va doc duoc href MOI."""

    def _storage_file(self):
        return os.path.join(tempfile.mkdtemp(), "scrapling_test_storage.db")

    def _don_dep(self, storage_file):
        # Scrapling giu ket noi sqlite mo tren doi tuong Selector/storage;
        # tren Windows, xoa file khi handle chua dong se nem PermissionError.
        # gc.collect() ep giai phong cac Selector da het pham vi truoc khi
        # thu xoa — that bai xoa o day KHONG lam hong ket qua test, chi la
        # don dep file tam, nen bo qua loi thay vi de no che lap assertion
        # that su cua test.
        gc.collect()
        try:
            os.remove(storage_file)
        except OSError:
            pass

    def test_doi_cau_truc_DOM_hoan_toan_van_tim_dung_danh_sach_chuong(self):
        storage_file = self._storage_file()
        try:
            index_url = f"{_BASE}/truyen/thu-nghiem"

            # Lan quet 1: cau truc cu, mau href khop binh thuong — luu dau van tay.
            adapter_1 = _tao_adapter({index_url: _doc_fixture("index.html")}, storage_file)
            series_1 = adapter_1.discover_series(index_url)
            self.assertEqual(len(series_1.chapter_urls), 3, "lan quet dau phai thanh cong binh thuong")

            # Lan quet 2: CUNG storage_file (mo phong chay lai vao lan sau) —
            # nhung trang gio la ban DA DOI CAU TRUC HOAN TOAN.
            adapter_2 = _tao_adapter({index_url: _doc_fixture("index_v2_changed_dom.html")}, storage_file)
            series_2 = adapter_2.discover_series(index_url)

            self.assertEqual(
                len(series_2.chapter_urls), 3,
                "mau href cu khong con khop — PHAI dua vao .relocate() de tim lai",
            )
            # href THAT SU phai la duong dan MOI (/doc/.../tap-N), doc truc
            # tiep tu phan tu vua dinh vi lai — khong phai du lieu cu.
            self.assertTrue(all("/doc/thu-nghiem/tap-" in u for u in series_2.chapter_urls))
        finally:
            self._don_dep(storage_file)

    def test_khong_co_dau_van_tay_cu_thi_bao_0_chuong_khong_gia_mao(self):
        """Neu CHUA TUNG quet thanh cong lan nao (khong co gi de relocate),
        DOM doi cau truc phai tra ve DANH SACH RONG that su — khong duoc
        bia dat chuong tu hu vo."""
        storage_file = self._storage_file()
        try:
            index_url = f"{_BASE}/truyen/thu-nghiem"
            adapter = _tao_adapter({index_url: _doc_fixture("index_v2_changed_dom.html")}, storage_file)
            series = adapter.discover_series(index_url)
            self.assertEqual(series.chapter_urls, [])
        finally:
            self._don_dep(storage_file)


class MalformedHtmlTest(unittest.TestCase):
    def test_html_loi_dinh_dang_van_trich_xuat_duoc_lien_ket_chuong(self):
        pages = {f"{_BASE}/loi": _doc_fixture("malformed.html")}
        adapter = _tao_adapter(pages)
        series = adapter.discover_series(f"{_BASE}/loi")
        self.assertEqual(len(series.chapter_urls), 2)
        self.assertTrue(any(u.endswith("chuong-1") for u in series.chapter_urls))
        self.assertTrue(any(u.endswith("chuong-2") for u in series.chapter_urls))


class PaginationTest(unittest.TestCase):
    def test_gop_hai_trang_muc_luc_giu_dung_thu_tu_khong_trung(self):
        """`discover_series` chi doc MOT trang — phan trang la trach nhiem
        cua noi goi lap qua nhieu trang muc luc roi gop lai. Kiem tra viec
        gop giu dung thu tu VA khong trung lap qua `canonicalize_url`."""
        page1_url = f"{_BASE}/truyen/thu-nghiem?page=1"
        page2_url = f"{_BASE}/truyen/thu-nghiem?page=2"
        adapter = _tao_adapter({
            page1_url: _doc_fixture("index.html"),
            page2_url: _doc_fixture("index_page2.html"),
        })
        s1 = adapter.discover_series(page1_url)
        s2 = adapter.discover_series(page2_url)
        gop = s1.chapter_urls + s2.chapter_urls
        self.assertEqual(len(gop), 5)
        self.assertTrue(gop[0].endswith("chuong-1"))
        self.assertTrue(gop[-1].endswith("chuong-5"))


class ChapterReorderAndRevisionTest(unittest.TestCase):
    def test_muc_luc_doi_thu_tu_state_van_nhan_dung_qua_canonical_url(self):
        """Nguon dao lai thu tu hien thi chuong (vd chen chuong moi o dau
        danh sach) — `ScrapeState` phai VAN nhan ra cac chuong DA xu ly
        qua canonical_url, bat ke vi tri hien tai trong danh sach."""
        pages = {
            f"{_BASE}/truyen/thu-nghiem": _doc_fixture("index.html"),
            f"{_BASE}/truyen/thu-nghiem/chuong-1": _doc_fixture("chuong-1.html"),
            f"{_BASE}/truyen/thu-nghiem/chuong-2": _doc_fixture("chuong-2.html"),
            f"{_BASE}/truyen/thu-nghiem/chuong-3": _doc_fixture("chuong-3.html"),
        }
        adapter = _tao_adapter(pages)
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")

        state = ScrapeState()
        for url in series.chapter_urls:
            chapter = adapter.normalize_chapter(url, adapter.fetch_chapter(url), series)
            state.record_success(url, content_hash_value=chapter.content_hash,
                                 chapter_number=chapter.chapter_number)

        # Mo phong danh sach BI DAO NGUOC thu tu hien thi (chuong 3 len dau).
        dao_nguoc = list(reversed(series.chapter_urls))
        con_lai = adapter.resume(state, dao_nguoc)
        self.assertEqual(con_lai, [], "tat ca da xong — dao thu tu khong duoc lam mat trang thai")

    def test_noi_dung_nguon_bi_sua_duoc_danh_dau_revision_khong_am_tham_de(self):
        pages = {
            f"{_BASE}/truyen/thu-nghiem": _doc_fixture("index.html"),
            f"{_BASE}/truyen/thu-nghiem/chuong-1": _doc_fixture("chuong-1.html"),
        }
        adapter = _tao_adapter(pages)
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")
        url = series.chapter_urls[0]

        chapter_v1 = adapter.normalize_chapter(url, adapter.fetch_chapter(url), series)
        state = ScrapeState()
        state.record_success(url, content_hash_value=chapter_v1.content_hash)

        # Nguon SUA LAI noi dung chuong 1 (mo phong bang HTML khac, cung url).
        pages[url] = _doc_fixture("chuong-2.html")
        adapter_v2 = _tao_adapter(pages)
        chapter_v2 = adapter_v2.normalize_chapter(url, adapter_v2.fetch_chapter(url), series)
        self.assertNotEqual(chapter_v1.content_hash, chapter_v2.content_hash)

        row = state.record_success(url, content_hash_value=chapter_v2.content_hash)
        self.assertTrue(row["is_revision"], "noi dung doi PHAI duoc gan co revision, khong am tham de")


if __name__ == "__main__":
    unittest.main()
