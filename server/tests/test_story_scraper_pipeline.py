"""
Kiem thu `server/scraper/pipeline.py` — bo dieu phoi dau-cuoi (plan/run,
dry-run, hang doi duyet, resumable import). Dung fixture cuc bo giong
`test_story_scraper_adapters.py`, KHONG cham mang that.
"""
import os
import unittest

from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
from server.scraper.dedupe import ScrapeState
from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.pipeline import IngestionDecision, StoryIngestionPipeline

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
}


def _tao_pipeline(state=None):
    adapter = GenericIndexAdapter(FixtureFetcher(dict(_PAGES)), chapter_href_pattern=r"/chuong-\d+",
                                   title_suffix_to_strip=" - Trang Web Giả")
    return StoryIngestionPipeline(adapter, state if state is not None else ScrapeState())


class PlanTest(unittest.TestCase):
    def test_plan_khong_tai_chuong_nao_chi_kham_pha(self):
        pipeline = _tao_pipeline()
        ke_hoach = pipeline.plan(f"{_BASE}/truyen/thu-nghiem")
        self.assertEqual(ke_hoach.total_discovered, 3)
        self.assertEqual(len(ke_hoach.chapter_urls_to_process), 3)
        self.assertEqual(ke_hoach.already_done_count, 0)

    def test_plan_tren_state_da_co_mot_phan_bao_dung_already_done_count(self):
        state = ScrapeState()
        state.record_success(f"{_BASE}/truyen/thu-nghiem/chuong-1", content_hash_value="x")
        pipeline = _tao_pipeline(state)
        ke_hoach = pipeline.plan(f"{_BASE}/truyen/thu-nghiem")
        self.assertEqual(ke_hoach.already_done_count, 1)
        self.assertEqual(len(ke_hoach.chapter_urls_to_process), 2)

    def test_chapter_limit_cat_bot_SAU_khi_da_loc_resume(self):
        pipeline = _tao_pipeline()
        ke_hoach = pipeline.plan(f"{_BASE}/truyen/thu-nghiem", chapter_limit=1)
        self.assertEqual(len(ke_hoach.chapter_urls_to_process), 1)
        self.assertEqual(ke_hoach.total_discovered, 3, "total_discovered không bị ảnh hưởng bởi limit")


class RunTest(unittest.TestCase):
    def test_lan_dau_tat_ca_deu_la_NEW(self):
        pipeline = _tao_pipeline()
        ket_qua = pipeline.run(f"{_BASE}/truyen/thu-nghiem")
        self.assertEqual(len(ket_qua.review_items), 3)
        self.assertTrue(all(i.decision == IngestionDecision.NEW for i in ket_qua.review_items))
        self.assertTrue(all(i.chapter is not None for i in ket_qua.review_items))
        self.assertEqual(ket_qua.dem_theo_quyet_dinh()["new"], 3)

    def test_moi_muc_thanh_cong_co_kem_bao_cao_chat_luong(self):
        pipeline = _tao_pipeline()
        ket_qua = pipeline.run(f"{_BASE}/truyen/thu-nghiem")
        self.assertTrue(all(i.quality is not None for i in ket_qua.review_items))
        # Fixture kiem thu la doan van NGAN (chi vai cau, duoi nguong
        # text_length_min 200 ky tu that su cua mot chuong) — dung y KHONG
        # gia lap mot chuong day du dai, nen chi kiem tra "khong loi TIEU
        # DE/encoding/nav-leakage/URL" (cac check khong phu thuoc do dai),
        # khong khang dinh `passed` toan phan.
        for item in ket_qua.review_items:
            ten_that_bai = {c.name for c in item.quality.checks if not c.passed}
            self.assertNotIn("title", ten_that_bai)
            self.assertNotIn("encoding", ten_that_bai)
            self.assertNotIn("nav_leakage", ten_that_bai)
            self.assertNotIn("source_url", ten_that_bai)

    def test_muc_FAILED_khong_co_bao_cao_chat_luong(self):
        pages_hong = dict(_PAGES)
        del pages_hong[f"{_BASE}/truyen/thu-nghiem/chuong-2"]
        adapter = GenericIndexAdapter(FixtureFetcher(pages_hong), chapter_href_pattern=r"/chuong-\d+",
                                       title_suffix_to_strip=" - Trang Web Giả")
        pipeline = StoryIngestionPipeline(adapter, ScrapeState())
        ket_qua = pipeline.run(f"{_BASE}/truyen/thu-nghiem")
        muc_loi = next(i for i in ket_qua.review_items if i.decision == IngestionDecision.FAILED)
        self.assertIsNone(muc_loi.quality)

    def test_chay_lai_ngay_sau_do_khong_con_gi_de_lam(self):
        # Idempotent: state da ghi tu lan chay truoc, resume() phai loc het.
        state = ScrapeState()
        pipeline = _tao_pipeline(state)
        pipeline.run(f"{_BASE}/truyen/thu-nghiem")

        pipeline_2 = _tao_pipeline(state)  # instance MOI, CUNG state — mo phong tien trinh mới.
        ket_qua_2 = pipeline_2.run(f"{_BASE}/truyen/thu-nghiem")
        self.assertEqual(len(ket_qua_2.review_items), 0, "resumable: không làm lại chương đã xong")

    def test_noi_dung_doi_so_voi_ban_ghi_cu_duoc_bao_la_REVISION(self):
        # `resume()` se loc bo chuong da co ban ghi "ok" ra khoi
        # `chapter_urls_to_process` — nen kiem thu PHAN LOAI khi noi dung
        # doi phai goi thang nhanh phan loai (giong cach DryRunTest kiem
        # ALREADY_IMPORTED), khong di qua toan bo `run()` (se bi loc mat).
        state = ScrapeState()
        adapter = GenericIndexAdapter(FixtureFetcher(dict(_PAGES)), chapter_href_pattern=r"/chuong-\d+",
                                       title_suffix_to_strip=" - Trang Web Giả")
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")
        url_chuong_1 = f"{_BASE}/truyen/thu-nghiem/chuong-1"

        state.record_success(url_chuong_1, content_hash_value="hash_cu_gia_lap")

        chapter_moi = adapter.normalize_chapter(
            url_chuong_1, adapter.fetch_chapter(url_chuong_1), series)
        self.assertNotEqual(chapter_moi.content_hash, "hash_cu_gia_lap")

        pipeline = StoryIngestionPipeline(adapter, state)
        quyet_dinh, trung_voi = pipeline._phan_loai_khong_ghi(chapter_moi)
        self.assertEqual(quyet_dinh, IngestionDecision.REVISION)
        self.assertEqual(trung_voi, [])

    def test_loi_mot_chuong_khong_lam_hong_ca_lo(self):
        pages_hong = dict(_PAGES)
        del pages_hong[f"{_BASE}/truyen/thu-nghiem/chuong-2"]  # chuong-2 se 404 khi tai.
        adapter = GenericIndexAdapter(FixtureFetcher(pages_hong), chapter_href_pattern=r"/chuong-\d+",
                                       title_suffix_to_strip=" - Trang Web Giả")
        pipeline = StoryIngestionPipeline(adapter, ScrapeState())
        ket_qua = pipeline.run(f"{_BASE}/truyen/thu-nghiem")

        self.assertEqual(len(ket_qua.review_items), 3, "vẫn có đủ 3 mục, kể cả mục lỗi")
        dem = ket_qua.dem_theo_quyet_dinh()
        self.assertEqual(dem["failed"], 1)
        self.assertEqual(dem["new"], 2, "2 chương còn lại vẫn xử lý bình thường")

    def test_chuong_loi_duoc_ghi_that_bai_de_thu_lai_lan_sau(self):
        state = ScrapeState()
        pages_hong = dict(_PAGES)
        del pages_hong[f"{_BASE}/truyen/thu-nghiem/chuong-2"]
        adapter_hong = GenericIndexAdapter(FixtureFetcher(pages_hong), chapter_href_pattern=r"/chuong-\d+",
                                            title_suffix_to_strip=" - Trang Web Giả")
        StoryIngestionPipeline(adapter_hong, state).run(f"{_BASE}/truyen/thu-nghiem")

        # Lan sau, nguon da co lai chuong-2 (loi tam thoi da qua) — resume()
        # phai THU LAI no (khong bo qua vinh vien chi vi lan truoc that bai).
        pipeline_sua = _tao_pipeline(state)
        ke_hoach = pipeline_sua.plan(f"{_BASE}/truyen/thu-nghiem")
        self.assertIn(f"{_BASE}/truyen/thu-nghiem/chuong-2", ke_hoach.chapter_urls_to_process)


class DryRunTest(unittest.TestCase):
    def test_dry_run_khong_ghi_gi_vao_state(self):
        state = ScrapeState()
        pipeline = _tao_pipeline(state)
        ket_qua = pipeline.run(f"{_BASE}/truyen/thu-nghiem", dry_run=True)

        self.assertEqual(len(ket_qua.review_items), 3)
        self.assertTrue(ket_qua.dry_run)
        self.assertEqual(len(state._rows), 0, "dry-run không được ghi bất kỳ gì vào state")

    def test_dry_run_van_phan_loai_dung_NEW(self):
        pipeline = _tao_pipeline()
        ket_qua = pipeline.run(f"{_BASE}/truyen/thu-nghiem", dry_run=True)
        self.assertTrue(all(i.decision == IngestionDecision.NEW for i in ket_qua.review_items))

    def test_dry_run_phan_loai_ALREADY_IMPORTED_khi_hash_khop_ban_ghi_cu(self):
        # `_phan_loai_khong_ghi` la nhanh noi bo `run(dry_run=True)` dung —
        # kiem thu truc tiep vi `run()` qua `resume()` se loc chuong da
        # xong ra truoc khi toi buoc phan loai (xem test REVISION o tren
        # cho cung ly do).
        state = ScrapeState()
        adapter = GenericIndexAdapter(FixtureFetcher(dict(_PAGES)), chapter_href_pattern=r"/chuong-\d+",
                                       title_suffix_to_strip=" - Trang Web Giả")
        url_chuong_1 = f"{_BASE}/truyen/thu-nghiem/chuong-1"
        series = adapter.discover_series(f"{_BASE}/truyen/thu-nghiem")
        chapter = adapter.normalize_chapter(url_chuong_1, adapter.fetch_chapter(url_chuong_1), series)

        state.record_success(url_chuong_1, content_hash_value=chapter.content_hash)

        pipeline = StoryIngestionPipeline(adapter, state)
        quyet_dinh, trung_voi = pipeline._phan_loai_khong_ghi(chapter)
        self.assertEqual(quyet_dinh, IngestionDecision.ALREADY_IMPORTED)
        self.assertEqual(trung_voi, [])


class UnexpectedErrorIsolationTest(unittest.TestCase):
    """Tai hien phat hien tu review doc lap (Codex): `run()` tung chi bat
    `(FetchError, ValueError)` — mot loi KHONG LUONG TRUOC duoc tu buoc
    phan tich noi bo (vd `RecursionError` tren HTML long bat thuong, xem
    `content_extraction.py`) se KHONG bi bat, dung ca dot quet vi MOT
    chuong. Gio bat `Exception` noi chung."""

    def test_loi_bat_thuong_tu_normalize_chapter_khong_dung_ca_dot(self):
        class _NhaCungCapLoi:
            tier = None

            def resolve(self, url):
                return url

            def discover_series(self, url):
                from server.scraper.contract import SeriesInfo
                return SeriesInfo(
                    canonical_url=url, title="T", source_domain="vd.example",
                    chapter_urls=[f"{url}/c1", f"{url}/c2"])

            def list_chapters(self, series):
                return list(series.chapter_urls)

            def fetch_chapter(self, url):
                return "<html></html>"

            def normalize_chapter(self, url, raw_html, series):
                if url.endswith("/c1"):
                    raise RecursionError("mô phỏng lỗi không lường trước được")
                from server.scraper.contract import NormalizedChapter
                return NormalizedChapter(
                    source_url=url, canonical_url=url, source_domain="vd.example",
                    series_title="T", chapter_title="C2", raw_text=raw_html,
                    clean_text="Nội dung chương hai hợp lệ.",
                    content_hash="h", source_fingerprint="f")

            def resume(self, state, chapter_urls):
                return list(chapter_urls)

            def fingerprint(self, chapter):
                return chapter.source_fingerprint

        pipeline = StoryIngestionPipeline(_NhaCungCapLoi(), ScrapeState())
        ket_qua = pipeline.run("https://vd.example/truyen")

        self.assertEqual(len(ket_qua.review_items), 2)
        c1 = next(i for i in ket_qua.review_items if i.url.endswith("/c1"))
        c2 = next(i for i in ket_qua.review_items if i.url.endswith("/c2"))
        self.assertEqual(c1.decision, IngestionDecision.FAILED)
        self.assertIn("mô phỏng lỗi", c1.error)
        self.assertEqual(c2.decision, IngestionDecision.NEW)


if __name__ == "__main__":
    unittest.main()
