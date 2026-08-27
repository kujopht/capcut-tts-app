"""
Phase 13 cua Story Harvester V3 — kiem chung kien truc dieu phoi hang loat
(`server/scraper/bulk.py::ScrapeRunService`) o QUY MO 100/500/1000 chuong,
dung FIXTURE tong hop (khong cham mang that, dung nguyen tac "fixture uu
tien hon con bao yeu cau mang that" cua Phase 13). Tap trung vao NHUNG
DAC TINH chi bieu hien ro o quy mo lon hoac qua nhieu chu ky: chu ky bi
CHAN (bounded cycles) hoan tat dung so luong, resume/idempotent khi
`plan_run` goi lai, thu lai muc loi (`retry_failed`), huy an toan giua
chung (khong dung/mat chuong dang xu ly), va dong bo lai "khe ho crash"
(`_reconcile_items_from_state`) khi tien trinh chet giua hai buoc ghi.
"""
from __future__ import annotations

import math
import unittest

from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
from server.scraper.bulk import ScrapeRunService
from server.scraper.dedupe import ScrapeState
from server.scraper.http_fetcher import FetchError, FixtureFetcher
from server.scraper.pipeline import IngestionDecision, StoryIngestionPipeline
from server.scraper.run_state import MockScrapeRunStore, ScrapeItemStatus, ScrapeRunStatus

_BASE = "https://vd-quy-mo-lon.example"


def _make_pages(story_slug: str, n: int) -> dict:
    links = "\n".join(
        f'<li><a href="/truyen/{story_slug}/chuong-{i}">Chương {i}</a></li>'
        for i in range(1, n + 1)
    )
    pages = {
        f"{_BASE}/truyen/{story_slug}": (
            f"<html><head><title>{story_slug}</title>"
            f'<meta property="og:title" content="Truyện Quy Mô Lớn">'
            f"</head><body><ul class=\"chapter-list\">{links}</ul></body></html>"
        ),
    }
    for i in range(1, n + 1):
        pages[f"{_BASE}/truyen/{story_slug}/chuong-{i}"] = (
            f"<html><head><title>Chương {i}</title>"
            f'<meta property="og:title" content="Chương {i}"></head>'
            f"<body><article><h1>Chương {i}</h1>"
            f"<p>Nội dung chương số {i} của truyện quy mô lớn dùng để kiểm "
            "thử Phase 13, đủ dài để vượt ngưỡng tối thiểu cho một vùng "
            "nội dung hợp lệ trong bài kiểm tra trích xuất, viết thêm một "
            "câu nữa cho chắc chắn vượt hẳn hai trăm ký tự tối thiểu cần "
            "có cho ngưỡng trích xuất đáng tin cậy.</p>"
            "</article></body></html>"
        )
    return pages


def _make_service(pages: dict, *, chapters_per_cycle: int, fetcher=None):
    fetcher = fetcher or FixtureFetcher(dict(pages))
    adapter = GenericIndexAdapter(fetcher, chapter_href_pattern=r"/chuong-\d+")
    pipeline = StoryIngestionPipeline(adapter, ScrapeState())
    store = MockScrapeRunStore()
    service = ScrapeRunService(pipeline, store, chapters_per_cycle=chapters_per_cycle)
    return pipeline, store, service


def _drive_to_terminal(service: ScrapeRunService, run_id: str, *, max_cycles: int = 10_000) -> int:
    cycles = 0
    while True:
        run = service._store.get_run(run_id)
        if run.is_terminal:
            return cycles
        service.drive_once(run_id)
        cycles += 1
        if cycles > max_cycles:
            raise AssertionError(
                "quá nhiều chu kỳ điều phối — có thể vòng lặp vô hạn "
                f"(đã chạy {cycles} chu kỳ mà đợt vẫn chưa kết thúc)")


class _FlakyOnceFetcher:
    """Boc MOT fetcher that — moi URL trong `urls_loi_lan_dau` that bai
    (nem `FetchError`) DUNG MOT LAN goi `fetch()` dau tien, roi thanh cong
    binh thuong tu lan thu hai tro di — mo phong loi mang TAM THOI, dung
    de kiem chung `retry_failed` o quy mo lon."""

    def __init__(self, inner, urls_loi_lan_dau) -> None:
        self._inner = inner
        self._con_lai = dict.fromkeys(urls_loi_lan_dau, 1)

    def fetch(self, url: str, **kwargs):
        if self._con_lai.get(url, 0) > 0:
            self._con_lai[url] -= 1
            raise FetchError(f"Lỗi mạng tạm thời giả lập cho {url}")
        return self._inner.fetch(url, **kwargs)


class FullCycleCompletionTest(unittest.TestCase):
    def test_100_chuong_hoan_tat_dung_so_luong_qua_nhieu_chu_ky_bi_chan(self):
        pages = _make_pages("truyen-100", 100)
        _, store, service = _make_service(pages, chapters_per_cycle=7)
        run = service.plan_run(f"{_BASE}/truyen/truyen-100")

        cycles = _drive_to_terminal(service, run.run_id)

        dem = store.count_items_by_status(run.run_id)
        self.assertEqual(dem[ScrapeItemStatus.REVIEW_READY.value], 100)
        self.assertEqual(dem[ScrapeItemStatus.PENDING.value], 0)
        self.assertEqual(dem[ScrapeItemStatus.FAILED.value], 0)
        self.assertEqual(cycles, math.ceil(100 / 7))
        self.assertEqual(store.get_run(run.run_id).status, ScrapeRunStatus.COMPLETED)

    def test_500_chuong_hoan_tat_dung_so_luong_qua_nhieu_chu_ky_bi_chan(self):
        pages = _make_pages("truyen-500", 500)
        _, store, service = _make_service(pages, chapters_per_cycle=25)
        run = service.plan_run(f"{_BASE}/truyen/truyen-500")

        cycles = _drive_to_terminal(service, run.run_id)

        dem = store.count_items_by_status(run.run_id)
        self.assertEqual(dem[ScrapeItemStatus.REVIEW_READY.value], 500)
        self.assertEqual(dem[ScrapeItemStatus.PENDING.value], 0)
        self.assertEqual(cycles, math.ceil(500 / 25))
        self.assertEqual(store.get_run(run.run_id).status, ScrapeRunStatus.COMPLETED)

        # Khong item_id/sequence nao trung — moi chuong dung MOT muc.
        muc = store.list_items(run.run_id, limit=None)
        self.assertEqual(len(muc), 500)
        self.assertEqual(len({m.item_id for m in muc}), 500)
        self.assertEqual(len({m.sequence for m in muc}), 500)


class ThousandChapterIdempotencyTest(unittest.TestCase):
    """1000 chuong: tap trung vao khong-mat/khong-trung o quy mo lon +
    resume idempotent, thay vi lap lai toan bo cac kiem tra chi tiet da
    co o quy mo 100/500 (giu thoi gian chay hop ly)."""

    def test_1000_chuong_hoan_tat_va_plan_run_lai_khong_tao_them_muc(self):
        pages = _make_pages("truyen-1000", 1000)
        _, store, service = _make_service(pages, chapters_per_cycle=50)
        run = service.plan_run(f"{_BASE}/truyen/truyen-1000")

        _drive_to_terminal(service, run.run_id)

        dem = store.count_items_by_status(run.run_id)
        self.assertEqual(dem[ScrapeItemStatus.REVIEW_READY.value], 1000)
        muc = store.list_items(run.run_id, limit=None)
        self.assertEqual(len(muc), 1000)
        self.assertEqual(len({m.item_id for m in muc}), 1000)

        # goi lai plan_run tren dot DA XONG — idempotent, KHONG tao them
        # muc nao, KHONG chuyen lai ve RUNNING (khong con pending nao).
        run_lai = service.plan_run(f"{_BASE}/truyen/truyen-1000")
        self.assertEqual(len(store.list_items(run.run_id, limit=None)), 1000)
        self.assertEqual(run_lai.status, ScrapeRunStatus.COMPLETED)


class RetryFailedAtScaleTest(unittest.TestCase):
    def test_muc_loi_tam_thoi_thanh_cong_het_sau_retry_failed(self):
        pages = _make_pages("truyen-retry", 100)
        urls_loi = [f"{_BASE}/truyen/truyen-retry/chuong-{i}" for i in (5, 37, 82)]
        fetcher = _FlakyOnceFetcher(FixtureFetcher(dict(pages)), urls_loi)
        _, store, service = _make_service(pages, chapters_per_cycle=10, fetcher=fetcher)
        run = service.plan_run(f"{_BASE}/truyen/truyen-retry")

        _drive_to_terminal(service, run.run_id)
        dem = store.count_items_by_status(run.run_id)
        self.assertEqual(dem[ScrapeItemStatus.FAILED.value], 3)
        self.assertEqual(dem[ScrapeItemStatus.REVIEW_READY.value], 97)
        self.assertEqual(store.get_run(run.run_id).status, ScrapeRunStatus.PARTIAL)

        ket_qua = service.retry_failed(run.run_id)
        self.assertEqual(ket_qua["retried"], 3)
        _drive_to_terminal(service, run.run_id)

        dem2 = store.count_items_by_status(run.run_id)
        self.assertEqual(dem2[ScrapeItemStatus.FAILED.value], 0)
        self.assertEqual(dem2[ScrapeItemStatus.REVIEW_READY.value], 100)
        self.assertEqual(store.get_run(run.run_id).status, ScrapeRunStatus.COMPLETED)


class CancelMidRunSafetyAtScaleTest(unittest.TestCase):
    def test_huy_giua_chung_giu_nguyen_dung_cac_muc_chua_dung_toi(self):
        pages = _make_pages("truyen-huy", 100)
        _, store, service = _make_service(pages, chapters_per_cycle=10)
        run = service.plan_run(f"{_BASE}/truyen/truyen-huy")

        service.drive_once(run.run_id)
        service.drive_once(run.run_id)
        dem_truoc_huy = store.count_items_by_status(run.run_id)
        self.assertEqual(dem_truoc_huy[ScrapeItemStatus.REVIEW_READY.value], 20)

        service.request_cancel(run.run_id)
        service.drive_once(run.run_id)

        dem = store.count_items_by_status(run.run_id)
        self.assertEqual(dem[ScrapeItemStatus.REVIEW_READY.value], 20)
        self.assertEqual(dem[ScrapeItemStatus.PENDING.value], 80)
        self.assertEqual(dem[ScrapeItemStatus.FAILED.value], 0)
        self.assertEqual(dem[ScrapeItemStatus.SKIPPED.value], 0)
        self.assertEqual(store.get_run(run.run_id).status, ScrapeRunStatus.CANCELLED)

        # Dot da HUY (KET) — goi drive_once lai KHONG dung toi gi them,
        # du van con 80 muc `pending` chua xu ly (tinh chat huy an toan).
        service.drive_once(run.run_id)
        dem_sau = store.count_items_by_status(run.run_id)
        self.assertEqual(dem, dem_sau)


class CrashRecoveryReconcileAtScaleTest(unittest.TestCase):
    def test_khe_ho_crash_giua_state_va_store_duoc_dong_bo_lai_qua_plan_run(self):
        """Tai hien CHINH XAC tinh huong duoc mo ta trong docstring
        `ScrapeRunService._reconcile_items_from_state`: tien trinh "chet"
        NGAY SAU `state.record_success()` nhung TRUOC KHI `store.save_item`
        kip chay cho MOT muc cu the — muc do con `pending` trong store du
        `ScrapeState` (bo nho) da biet no thanh cong. Lan `plan_run` KE
        TIEP (mo phong tien trinh khoi dong lai) phai tu dong dong bo lai
        muc do thanh REVIEW_READY, KHONG duoc de no "pending" mai mai (vi
        no se khong bao gio xuat hien lai trong ke hoach moi qua resume())."""
        pages = _make_pages("truyen-crash", 20)
        pipeline, store, service = _make_service(pages, chapters_per_cycle=5)
        url = f"{_BASE}/truyen/truyen-crash"
        run = service.plan_run(url)
        service.drive_once(run.run_id)  # 5 muc xu ly binh thuong, dung.

        muc_con_pending = store.list_items(
            run.run_id, statuses=[ScrapeItemStatus.PENDING], limit=None)
        muc_bi_crash = muc_con_pending[0]

        provider = pipeline._provider
        series = pipeline.plan(url).series
        raw = provider.fetch_chapter(muc_bi_crash.chapter_url)
        chapter = provider.normalize_chapter(muc_bi_crash.chapter_url, raw, series)
        # GIA LAP crash: chi ghi vao `state` (bo nho), KHONG goi
        # `store.save_item` — day CHINH LA khe ho can dong lai.
        pipeline.state.record_success(
            muc_bi_crash.chapter_url, content_hash_value=chapter.content_hash,
            chapter_number=chapter.chapter_number)

        muc_truoc_dong_bo = store.get_item(muc_bi_crash.item_id)
        self.assertEqual(muc_truoc_dong_bo.status, ScrapeItemStatus.PENDING)

        service.plan_run(url)  # kich hoat _reconcile_items_from_state

        muc_sau_dong_bo = store.get_item(muc_bi_crash.item_id)
        self.assertEqual(muc_sau_dong_bo.status, ScrapeItemStatus.REVIEW_READY)
        self.assertEqual(muc_sau_dong_bo.decision, IngestionDecision.ALREADY_IMPORTED.value)
        self.assertEqual(muc_sau_dong_bo.content_hash, chapter.content_hash)

        # Dot van tiep tuc dung — cac muc PENDING con lai (14) van con do,
        # khong bi mat/trung do lan dong bo nay.
        dem = store.count_items_by_status(run.run_id)
        self.assertEqual(dem[ScrapeItemStatus.REVIEW_READY.value], 6)
        self.assertEqual(dem[ScrapeItemStatus.PENDING.value], 14)

        _drive_to_terminal(service, run.run_id)
        dem_cuoi = store.count_items_by_status(run.run_id)
        self.assertEqual(dem_cuoi[ScrapeItemStatus.REVIEW_READY.value], 20)
        self.assertEqual(dem_cuoi[ScrapeItemStatus.PENDING.value], 0)


if __name__ == "__main__":
    unittest.main()
