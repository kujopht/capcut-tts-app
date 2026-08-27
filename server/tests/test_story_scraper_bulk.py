"""
Kiem thu `server/scraper/bulk.py` (`ScrapeRunService`) + phan bo sung cua
`server/scraper/run_state.py` — dieu phoi mot dot scrape HANG LOAT (tien
do/uoc luong/resume/thu-lai-muc-loi/bo-qua/huy an toan). Dung LAI DUNG bo
fixture cua `test_story_scraper_pipeline.py` (`FixtureFetcher` +
`GenericIndexAdapter` + `_PAGES`), khong cham mang that.
"""
import os
import unittest

from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
from server.scraper.bulk import ScrapeRunService
from server.scraper.dedupe import ScrapeState
from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.pipeline import IngestionDecision, StoryIngestionPipeline
from server.scraper.run_state import MockScrapeRunStore, ScrapeItemStatus, ScrapeRunStatus

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
_SERIES_URL = f"{_BASE}/truyen/thu-nghiem"


def _tao_pipeline(state=None, pages=None):
    adapter = GenericIndexAdapter(FixtureFetcher(dict(pages if pages is not None else _PAGES)),
                                   chapter_href_pattern=r"/chuong-\d+",
                                   title_suffix_to_strip=" - Trang Web Giả")
    return StoryIngestionPipeline(adapter, state if state is not None else ScrapeState())


def _tao_bo_ba(state=None, pages=None, chapters_per_cycle=5):
    """`(pipeline, store, service)` moi tinh — dung khi mot bai test khong
    can giu rieng tung phan."""
    pipeline = _tao_pipeline(state, pages)
    store = MockScrapeRunStore()
    service = ScrapeRunService(pipeline, store, chapters_per_cycle=chapters_per_cycle)
    return pipeline, store, service


class PlanRunTest(unittest.TestCase):
    def test_plan_run_tao_dot_va_muc_roi_chuyen_RUNNING(self):
        _, store, service = _tao_bo_ba()
        run = service.plan_run(_SERIES_URL)

        self.assertEqual(run.status, ScrapeRunStatus.RUNNING)
        self.assertEqual(run.estimated_total, 3)
        self.assertTrue(run.run_id)
        muc = store.list_items(run.run_id, limit=None)
        self.assertEqual(len(muc), 3)
        self.assertTrue(all(m.status == ScrapeItemStatus.PENDING for m in muc))

    def test_plan_run_dry_run_khong_ghi_gi_vao_store(self):
        _, store, service = _tao_bo_ba()
        run = service.plan_run(_SERIES_URL, dry_run=True)

        self.assertEqual(run.estimated_total, 3)
        self.assertEqual(run.already_done_count, 0)
        self.assertEqual(run.total_discovered, 3)
        self.assertEqual(store.list_runs(), [], "dry-run khong duoc ghi bat ky gi vao store")
        self.assertEqual(store.items, {})


class IdentityTest(unittest.TestCase):
    def test_cung_series_url_ra_cung_run_id_hai_lan_plan_run(self):
        _, store, service = _tao_bo_ba()
        run_1 = service.plan_run(_SERIES_URL)
        run_2 = service.plan_run(_SERIES_URL)

        self.assertEqual(run_1.run_id, run_2.run_id)
        self.assertEqual(len(store.list_runs()), 1, "khong tao dot thu hai cho cung mot series")

    def test_estimated_total_dung_bang_so_chuong_fixture(self):
        _, _, service = _tao_bo_ba()
        run = service.plan_run(_SERIES_URL)
        self.assertEqual(run.estimated_total, 3)
        self.assertEqual(run.total_discovered, 3)
        self.assertEqual(run.already_done_count, 0)


class DriveOnceTest(unittest.TestCase):
    def test_drive_once_xu_ly_het_va_ket_COMPLETED(self):
        _, store, service = _tao_bo_ba()
        run = service.plan_run(_SERIES_URL)

        dem = service.drive_once(run.run_id)

        self.assertEqual(dem[ScrapeItemStatus.REVIEW_READY.value], 3)
        self.assertEqual(dem[ScrapeItemStatus.PENDING.value], 0)
        run_sau = store.get_run(run.run_id)
        self.assertEqual(run_sau.status, ScrapeRunStatus.COMPLETED)
        self.assertTrue(run_sau.finished_at)
        self.assertEqual(run_sau.count_review_ready, 3)

    def test_loi_mot_chuong_ket_PARTIAL_khong_lam_hong_ca_dot(self):
        pages_hong = dict(_PAGES)
        del pages_hong[f"{_BASE}/truyen/thu-nghiem/chuong-2"]
        _, store, service = _tao_bo_ba(pages=pages_hong)
        run = service.plan_run(_SERIES_URL)

        dem = service.drive_once(run.run_id)

        self.assertEqual(dem[ScrapeItemStatus.FAILED.value], 1)
        self.assertEqual(dem[ScrapeItemStatus.REVIEW_READY.value], 2)
        run_sau = store.get_run(run.run_id)
        self.assertEqual(run_sau.status, ScrapeRunStatus.PARTIAL)


class CancelSafetyTest(unittest.TestCase):
    """Bai test QUAN TRONG NHAT cua file nay — xem docstring
    `server/scraper/bulk.py` ve tinh chat huy AN TOAN."""

    def test_huy_giua_chung_khong_dung_toi_muc_chua_xu_ly_va_giu_PENDING(self):
        _, store, service = _tao_bo_ba(chapters_per_cycle=1)
        run = service.plan_run(_SERIES_URL)
        self.assertEqual(len(store.list_items(run.run_id, limit=None)), 3)

        # Chu ky dau: xu ly DUNG mot chuong (chapters_per_cycle=1).
        service.drive_once(run.run_id, max_chapters=1)
        dem_giua = store.count_items_by_status(run.run_id)
        self.assertEqual(dem_giua[ScrapeItemStatus.REVIEW_READY.value], 1)
        self.assertEqual(dem_giua[ScrapeItemStatus.PENDING.value], 2)
        run_giua = store.get_run(run.run_id)
        self.assertEqual(run_giua.status, ScrapeRunStatus.RUNNING)

        service.request_cancel(run.run_id)
        self.assertEqual(store.get_run(run.run_id).status, ScrapeRunStatus.CANCEL_REQUESTED)

        # Chu ky thu hai: PHAI dung TRUOC KHI tai chuong tiep theo.
        dem_cuoi = service.drive_once(run.run_id, max_chapters=5)

        run_ket = store.get_run(run.run_id)
        self.assertEqual(run_ket.status, ScrapeRunStatus.CANCELLED)
        self.assertTrue(run_ket.cancelled_at)
        self.assertTrue(run_ket.finished_at)

        # DIEM MAU CHOT: hai muc CHUA duoc dung toi phai con nguyen
        # `pending` -- KHONG bi danh dau `failed` hay `skipped`.
        self.assertEqual(dem_cuoi[ScrapeItemStatus.PENDING.value], 2)
        self.assertEqual(dem_cuoi[ScrapeItemStatus.REVIEW_READY.value], 1)
        self.assertEqual(dem_cuoi[ScrapeItemStatus.FAILED.value], 0)
        self.assertEqual(dem_cuoi[ScrapeItemStatus.SKIPPED.value], 0)

        muc_sau = store.list_items(run.run_id, limit=None)
        so_pending = sum(1 for m in muc_sau if m.status == ScrapeItemStatus.PENDING)
        self.assertEqual(so_pending, 2)
        self.assertEqual(run_ket.count_pending, 2)

        # Mot chu ky drive THEM sau khi da CANCELLED khong duoc dung toi
        # cac muc pending con lai (dot da o trang thai KET).
        dem_sau_nua = service.drive_once(run.run_id, max_chapters=5)
        self.assertEqual(dem_sau_nua[ScrapeItemStatus.PENDING.value], 2,
                         "drive_once tren dot da CANCELLED khong duoc dung toi muc pending")


class ReconcileFromStateTest(unittest.TestCase):
    def test_crash_giua_ghi_state_va_ghi_muc_duoc_doi_soat_thanh_review_ready(self):
        state = ScrapeState()
        pipeline = _tao_pipeline(state)
        store = MockScrapeRunStore()
        service = ScrapeRunService(pipeline, store)

        run = service.plan_run(_SERIES_URL)
        url_chuong_1 = f"{_BASE}/truyen/thu-nghiem/chuong-1"

        # Mo phong crash: `state` DA duoc ghi "ok" (nhu the drive_once vua
        # goi state.record_success) nhung muc TUONG UNG chua kip chuyen
        # khoi `pending` (tien trinh chet truoc khi save_item kip chay).
        state.record_success(url_chuong_1, content_hash_value="gia_lap_hash",
                             chapter_number=1)

        run_2 = service.plan_run(_SERIES_URL)  # gia lap khoi dong lai.
        self.assertEqual(run_2.run_id, run.run_id)

        muc_chuong_1 = next(m for m in store.list_items(run.run_id, limit=None)
                            if m.chapter_url == url_chuong_1)
        self.assertEqual(muc_chuong_1.status, ScrapeItemStatus.REVIEW_READY)
        self.assertEqual(muc_chuong_1.decision, IngestionDecision.ALREADY_IMPORTED.value)

        dem = store.count_items_by_status(run.run_id)
        self.assertEqual(dem[ScrapeItemStatus.PENDING.value], 2, "hai chuong con lai van pending")
        self.assertEqual(dem[ScrapeItemStatus.REVIEW_READY.value], 1)


class RetryFailedTest(unittest.TestCase):
    def test_retry_failed_chi_dua_muc_FAILED_ve_pending(self):
        pages_hong = dict(_PAGES)
        del pages_hong[f"{_BASE}/truyen/thu-nghiem/chuong-2"]
        _, store, service = _tao_bo_ba(pages=pages_hong)
        run = service.plan_run(_SERIES_URL)
        service.drive_once(run.run_id)

        dem_truoc = store.count_items_by_status(run.run_id)
        self.assertEqual(dem_truoc[ScrapeItemStatus.FAILED.value], 1)
        self.assertEqual(dem_truoc[ScrapeItemStatus.REVIEW_READY.value], 2)
        self.assertEqual(store.get_run(run.run_id).status, ScrapeRunStatus.PARTIAL)

        ket = service.retry_failed(run.run_id)

        self.assertEqual(ket["retried"], 1)
        dem_sau = store.count_items_by_status(run.run_id)
        self.assertEqual(dem_sau[ScrapeItemStatus.PENDING.value], 1)
        self.assertEqual(dem_sau[ScrapeItemStatus.REVIEW_READY.value], 2,
                         "muc da xong khong bi dung toi")
        self.assertEqual(dem_sau[ScrapeItemStatus.FAILED.value], 0)
        # Dot da KET (PARTIAL) nhung vua co muc pending -- phai hoi sinh.
        self.assertEqual(store.get_run(run.run_id).status, ScrapeRunStatus.RUNNING)

    def test_retry_failed_tren_muc_khong_FAILED_bi_tu_choi(self):
        pages_hong = dict(_PAGES)
        del pages_hong[f"{_BASE}/truyen/thu-nghiem/chuong-2"]
        _, store, service = _tao_bo_ba(pages=pages_hong)
        run = service.plan_run(_SERIES_URL)
        service.drive_once(run.run_id)

        muc_da_xong = next(m for m in store.list_items(run.run_id, limit=None)
                           if m.status == ScrapeItemStatus.REVIEW_READY)
        with self.assertRaises(ValueError):
            service.retry_failed(run.run_id, item_id=muc_da_xong.item_id)

    def test_retry_failed_khong_item_id_bo_qua_am_tham_muc_khong_failed(self):
        # Chi con toan bo muc THANH CONG (khong co item_id) -- retried == 0,
        # khong loi, khong dung toi muc nao khac.
        _, store, service = _tao_bo_ba()
        run = service.plan_run(_SERIES_URL)
        service.drive_once(run.run_id)

        ket = service.retry_failed(run.run_id)
        self.assertEqual(ket["retried"], 0)
        dem = store.count_items_by_status(run.run_id)
        self.assertEqual(dem[ScrapeItemStatus.REVIEW_READY.value], 3)

    def test_retry_tren_dot_da_HUY_khong_lam_muc_no_hoi_sinh_lai(self):
        """Phat hien qua mot lan di qua luong operator that (huy roi bam
        'Thử lại tất cả lỗi'): mot dot vua bi HUY (chua dung toi muc nao,
        tat ca con `pending` theo dung tinh chat huy an toan) — goi
        `retry_failed` (0 muc that su duoc thu lai, vi khong co muc
        `failed` nao) KHONG duoc am tham dua dot tro lai `RUNNING`. Truoc
        day dieu kien hoi sinh chi kiem "co pending hay khong" (dung, vi
        cac muc chua dung toi VAN pending) ma khong kiem da_thu > 0, vo
        hieu hoa quyet dinh huy cua operator ngoai y muon."""
        _, store, service = _tao_bo_ba(chapters_per_cycle=5)
        run = service.plan_run(_SERIES_URL)
        service.request_cancel(run.run_id)
        service.drive_once(run.run_id)  # hoan tat huy — muc van con pending
        self.assertEqual(store.get_run(run.run_id).status, ScrapeRunStatus.CANCELLED)

        ket = service.retry_failed(run.run_id)
        self.assertEqual(ket["retried"], 0)
        self.assertEqual(store.get_run(run.run_id).status, ScrapeRunStatus.CANCELLED,
                         "huy phai duoc GIU NGUYEN, khong bi thu lai hoi sinh am tham")


class SkipTest(unittest.TestCase):
    def test_skip_ghi_vao_state_va_bi_loai_khoi_plan_run_sau(self):
        state = ScrapeState()
        _, store, service = _tao_bo_ba(state=state)
        run = service.plan_run(_SERIES_URL)

        url_chuong_2 = f"{_BASE}/truyen/thu-nghiem/chuong-2"
        muc_chuong_2 = next(m for m in store.list_items(run.run_id, limit=None)
                            if m.chapter_url == url_chuong_2)
        ket = service.skip(run.run_id, muc_chuong_2.item_id, reason="tam bo qua")
        self.assertEqual(store.get_item(muc_chuong_2.item_id).status, ScrapeItemStatus.SKIPPED)
        self.assertEqual(store.get_item(muc_chuong_2.item_id).skipped_reason, "tam bo qua")
        self.assertEqual(ket["run"].count_skipped, 1)

        # Mot lan `plan_run` MOI (kho `ScrapeRunItem` moi, nhung CUNG
        # `ScrapeState` ben vung) tren cung series khong duoc de xuat lai
        # chuong da bi bo qua.
        pipeline_2 = _tao_pipeline(state)
        store_2 = MockScrapeRunStore()
        service_2 = ScrapeRunService(pipeline_2, store_2)
        run_2 = service_2.plan_run(_SERIES_URL)

        urls_2 = {m.chapter_url for m in store_2.list_items(run_2.run_id, limit=None)}
        self.assertNotIn(url_chuong_2, urls_2)
        self.assertEqual(len(urls_2), 2)
        self.assertEqual(run_2.already_done_count, 1)


class CounterConsistencyTest(unittest.TestCase):
    def test_bo_dem_tra_ve_tu_drive_once_khop_dem_lai_tu_kho(self):
        pages_hong = dict(_PAGES)
        del pages_hong[f"{_BASE}/truyen/thu-nghiem/chuong-2"]
        _, store, service = _tao_bo_ba(pages=pages_hong)
        run = service.plan_run(_SERIES_URL)

        dem_tra_ve = service.drive_once(run.run_id)
        dem_thuc = store.count_items_by_status(run.run_id)
        self.assertEqual(dem_tra_ve, dem_thuc)

        run_sau = store.get_run(run.run_id)
        self.assertEqual(run_sau.count_pending, dem_thuc[ScrapeItemStatus.PENDING.value])
        self.assertEqual(run_sau.count_review_ready, dem_thuc[ScrapeItemStatus.REVIEW_READY.value])
        self.assertEqual(run_sau.count_failed, dem_thuc[ScrapeItemStatus.FAILED.value])
        self.assertEqual(run_sau.count_skipped, dem_thuc[ScrapeItemStatus.SKIPPED.value])


class ChapterLimitGrowthTest(unittest.TestCase):
    def test_canary_roi_full_run_dung_chung_run_id_chi_them_muc(self):
        _, store, service = _tao_bo_ba(chapters_per_cycle=5)

        run_canary = service.plan_run(_SERIES_URL, chapter_limit=1)
        self.assertEqual(run_canary.estimated_total, 1)
        service.drive_once(run_canary.run_id)
        self.assertEqual(store.get_run(run_canary.run_id).status, ScrapeRunStatus.COMPLETED)

        run_full = service.plan_run(_SERIES_URL)
        self.assertEqual(run_full.run_id, run_canary.run_id, "cung series -- cung run_id")
        self.assertEqual(run_full.status, ScrapeRunStatus.RUNNING,
                         "dot da COMPLETED nhung vua co muc pending moi -- hoi sinh")
        muc = store.list_items(run_full.run_id, limit=None)
        self.assertEqual(len(muc), 3, "chi THEM muc moi, khong xoa muc canary da co")

    def test_dot_ket_chi_con_muc_failed_khong_tu_hoi_sinh_qua_plan_run(self):
        pages_hong = dict(_PAGES)
        del pages_hong[f"{_BASE}/truyen/thu-nghiem/chuong-2"]
        _, store, service = _tao_bo_ba(pages=pages_hong)
        run = service.plan_run(_SERIES_URL)
        service.drive_once(run.run_id)
        self.assertEqual(store.get_run(run.run_id).status, ScrapeRunStatus.PARTIAL)

        # Goi lai plan_run tren CUNG series (van thieu chuong-2 trong
        # fixture) -- khong co muc pending MOI nao xuat hien (muc
        # chuong-2 da co san, van FAILED). Con lai la CHI muc failed ->
        # KHONG duoc tu hoi sinh.
        run_2 = service.plan_run(_SERIES_URL)
        self.assertEqual(run_2.status, ScrapeRunStatus.PARTIAL,
                         "chi con muc failed -- khong tu hoi sinh qua plan_run")


class ItemOrderingTest(unittest.TestCase):
    """Phat hien qua mot lan di qua luong operator that (khong phai suy
    doan): hang doi duyet tung sap theo `created_at`, bi trung gio o quy
    mo tao nhanh (Mock hay Appwrite that), lui ve `item_id` (ma bam,
    khong lien quan thu tu that) — operator thay chuong hien LON XON
    (vd 3, 2, 1 thay vi 1, 2, 3). `sequence` (dat MOT LAN luc tao) sua
    dut diem van de nay."""

    def test_hang_doi_duyet_dung_thu_tu_kham_pha_khong_phai_thu_tu_tao(self):
        _, store, service = _tao_bo_ba(chapters_per_cycle=5)
        run = service.plan_run(_SERIES_URL)
        service.drive_once(run.run_id)
        muc = store.list_items(run.run_id, limit=None)
        self.assertEqual([m.chapter_number for m in muc], [1, 2, 3])

    def test_sequence_qua_nhieu_lan_plan_run_van_giu_dung_thu_tu_khong_trung(self):
        """Cung kich ban voi `ChapterLimitGrowthTest` o tren (canary roi
        full run) — xac nhan `sequence` khong TRUNG giua muc canary va muc
        moi (se lam sap sai hang doi duyet). CO THE co khoang trong trong
        day so (vd 0, 2, 3 thay vi 0, 1, 2) khi mot lan `plan_run` sau lap
        lai ca chuong da co LAN chuong moi — VAN AN TOAN vi thu tu TUONG
        DOI van dung, chi kiem tra thu tu tuong doi, khong doi day lien
        tuc tuyet doi."""
        _, store, service = _tao_bo_ba(chapters_per_cycle=5)
        service.plan_run(_SERIES_URL, chapter_limit=1)
        run_full = service.plan_run(_SERIES_URL)
        muc = store.list_items(run_full.run_id, limit=None)
        sequences = [m.sequence for m in muc]
        self.assertEqual(len(sequences), len(set(sequences)), "khong duoc trung sequence")
        # `chapter_number` chi co gia tri SAU khi drive — chua drive o day,
        # nen kiem thu tu bang `chapter_url` (biet truoc thu tu that tu
        # fixture: chuong-1, chuong-2, chuong-3).
        muc_theo_thu_tu = sorted(muc, key=lambda m: m.sequence)
        self.assertTrue(muc_theo_thu_tu[0].chapter_url.endswith("chuong-1"))
        self.assertTrue(muc_theo_thu_tu[1].chapter_url.endswith("chuong-2"))
        self.assertTrue(muc_theo_thu_tu[2].chapter_url.endswith("chuong-3"))

    def test_khong_trung_sequence_khi_nguon_co_them_chuong_moi_sau_khoang_trong(self):
        """Kich ban CU THE Codex chi ra: mot dot da co khoang trong trong
        `sequence` (canary + full-run truoc khi drive, xem test o tren),
        RANG DA DRIVE xong, roi nguon co THEM MOT CHUONG MOI — muc moi
        PHAI khong trung `sequence` voi bat ky muc da co (kien nghi ban
        dau dung `dem so muc` se cap phat lai mot `sequence` DA DUNG)."""
        pipeline, store, service = _tao_bo_ba(chapters_per_cycle=5)
        service.plan_run(_SERIES_URL, chapter_limit=1)  # canary -> khoang trong
        run = service.plan_run(_SERIES_URL)  # full run -> sequence 0, 2, 3
        service.drive_once(run.run_id)  # drive HET — dem muc van la 3, khong doi

        pages_moi = dict(_PAGES)
        pages_moi[f"{_BASE}/truyen/thu-nghiem"] = pages_moi[
            f"{_BASE}/truyen/thu-nghiem"].replace(
            "</ul>",
            '<li><a href="/truyen/thu-nghiem/chuong-4">Chương 4: Mới</a></li></ul>')
        pages_moi[f"{_BASE}/truyen/thu-nghiem/chuong-4"] = _doc_fixture("chuong-3.html").replace(
            "Chương 3", "Chương 4")
        pipeline_moi = _tao_pipeline(pipeline.state, pages_moi)
        service_moi = ScrapeRunService(pipeline_moi, store, chapters_per_cycle=5)
        service_moi.plan_run(_SERIES_URL)  # nguon "vua co" chuong 4 moi

        muc = store.list_items(run.run_id, limit=None)
        sequences = [m.sequence for m in muc]
        self.assertEqual(len(sequences), len(set(sequences)),
                         f"sequence bi TRUNG: {sequences}")
        muc_chuong_4 = next(m for m in muc if m.chapter_url.endswith("chuong-4"))
        self.assertEqual(muc_chuong_4.sequence, max(sequences),
                         "chuong moi phai co sequence LON HON tat ca muc da co")


class PossibleDuplicateTest(unittest.TestCase):
    """Phase 8 Story Harvester V3 — hai URL KHAC NHAU nhung noi dung
    (content_hash) TRUNG HET phai duoc gan nhan `possible_duplicate`,
    KHONG tu dong bo qua (van vao hang doi duyet)."""

    def test_hai_chuong_trung_noi_dung_qua_URL_khac_nhau_duoc_gan_nhan(self):
        noi_dung_trung = (
            '<html><body><div class="chapter-content"><p>Nội dung hoàn '
            "toàn giống hệt nhau giữa hai đường dẫn khác nhau, đủ dài để "
            "vượt ngưỡng tối thiểu cho một vùng nội dung hợp lệ trong bộ "
            "kiểm thử phát hiện trùng lặp của Story Harvester V3.</p>"
            "</div></body></html>")
        index = (
            '<html><head><title>Truyện Trùng Lặp</title></head><body><ul>'
            '<li><a href="/d/chuong-1">Chương 1</a></li>'
            '<li><a href="/d/chuong-2-trung">Chương 2</a></li>'
            "</ul></body></html>")
        pages = {
            f"{_BASE}/d": index,
            f"{_BASE}/d/chuong-1": noi_dung_trung,
            f"{_BASE}/d/chuong-2-trung": noi_dung_trung,
        }
        pipeline, store, service = _tao_bo_ba(
            pages=pages, chapters_per_cycle=5)
        run = service.plan_run(f"{_BASE}/d")
        service.drive_once(run.run_id)

        muc = store.list_items(run.run_id, limit=None)
        self.assertEqual(len(muc), 2)
        muc_1 = next(m for m in muc if m.chapter_url.endswith("chuong-1"))
        muc_2 = next(m for m in muc if m.chapter_url.endswith("chuong-2-trung"))

        self.assertEqual(muc_1.decision, IngestionDecision.NEW.value)
        self.assertEqual(muc_2.decision, IngestionDecision.POSSIBLE_DUPLICATE.value)
        self.assertTrue(muc_2.duplicate_of_url.endswith("chuong-1"))
        # VAN vao hang doi duyet (khong tu dong bo qua).
        self.assertEqual(muc_2.status, ScrapeItemStatus.REVIEW_READY)


class RunViewTest(unittest.TestCase):
    def test_run_view_tra_ve_tien_do_khong_tac_dung_phu(self):
        _, store, service = _tao_bo_ba()
        run = service.plan_run(_SERIES_URL)
        service.drive_once(run.run_id, max_chapters=1)

        xem = service.run_view(run.run_id)
        self.assertEqual(xem["run"].run_id, run.run_id)
        self.assertEqual(len(xem["items"]), 3)
        self.assertEqual(xem["progress"]["estimated_total"], 3)

        # Khong tac dung phu: goi lai khong doi trang thai kho.
        dem_truoc = store.count_items_by_status(run.run_id)
        service.run_view(run.run_id)
        dem_sau = store.count_items_by_status(run.run_id)
        self.assertEqual(dem_truoc, dem_sau)


if __name__ == "__main__":
    unittest.main()
