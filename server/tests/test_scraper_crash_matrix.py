"""
Overnight mega task, Phase 12 ("crash matrix") — mo phong "chet tien
trinh" tai nhieu DIEM khac nhau trong luong dieu phoi, khoi dong lai, kiem
tra: KHONG mat tien do da cam ket, KHONG chuong trung, KHONG trang thai
hong, trang thai co the tiep tuc RO RANG.

CAC DIEM da duoc BAO PHU o noi khac, ghi lai o day de tranh trung lap:
  - "sau fetch, truoc persist" (state.record_success ghi xong nhung
    ScrapeRunItem chua kip cap nhat) — test_scraper_bulk_scale.py::
    CrashRecoveryReconcileAtScaleTest.
  - "trong luc huy" — test_scraper_bulk_scale.py::CancelMidRunSafetyAtScaleTest.
  - "skip() giua luc dang fetch" (mot dang "chet nua chung" khac cua thao
    tac dong thoi) — test_scraper_bulk_races.py::SkipDuringInFlightFetchTest.

CAC DIEM MOI kiem tra o day: giua batch dang fetch (mot phan da xong, mot
phan con "claimed" khi tien trinh chet), ngay sau khi tao ke hoach (truoc
khi drive lan dau), va trong luc thu lai (retry) mot muc loi.
"""
from __future__ import annotations

import unittest

from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
from server.scraper.bulk import ScrapeRunService
from server.scraper.dedupe import ScrapeState
from server.scraper.http_fetcher import FetchError, FixtureFetcher
from server.scraper.pipeline import StoryIngestionPipeline
from server.scraper.run_state import (
    CLAIM_LEASE_SECONDS, MockScrapeRunStore, ScrapeItemStatus, ScrapeRunStatus,
)

_BASE = "https://vd-crash.example"


def _make_pages(n: int) -> dict:
    links = "".join(f'<li><a href="/truyen/x/chuong-{i}">C{i}</a></li>' for i in range(1, n + 1))
    pages = {f"{_BASE}/truyen/x": f"<html><body><ul>{links}</ul></body></html>"}
    for i in range(1, n + 1):
        pages[f"{_BASE}/truyen/x/chuong-{i}"] = (
            f"<html><body><article><h1>Chương {i}</h1><p>"
            + ("Nội dung đầy đủ của chương. " * 15)
            + "</p></article></body></html>")
    return pages


def _make_service(pages, *, chapters_per_cycle=10, now_fn=None):
    adapter = GenericIndexAdapter(FixtureFetcher(dict(pages)), chapter_href_pattern=r"/chuong-\d+")
    pipeline = StoryIngestionPipeline(adapter, ScrapeState())
    store = MockScrapeRunStore(now_fn=now_fn) if now_fn else MockScrapeRunStore()
    service = ScrapeRunService(pipeline, store, chapters_per_cycle=chapters_per_cycle)
    return pipeline, store, service


class CrashMidFetchBatchTest(unittest.TestCase):
    """Diem crash: GIUA MOT batch dang fetch — mot phan chuong DA xong
    (REVIEW_READY that su), phan CON LAI van "claimed" (gia lap: tien
    trinh chet ngay sau khi claim ca lo, moi kip xu ly vai chuong dau).
    Khoi dong lai (lease het han) phai tiep tuc DUNG, khong bo sot/trung."""

    def test_khoi_dong_lai_sau_khi_lease_het_han_xu_ly_het_phan_con_lai(self):
        dong_ho = {"t": 0.0}

        def now_fn():
            return f"2026-01-01T00:{int(dong_ho['t']):02d}:00+00:00"

        pages = _make_pages(20)
        _, store, service = _make_service(pages, chapters_per_cycle=20, now_fn=now_fn)
        run = service.plan_run(f"{_BASE}/truyen/x")

        # Gia lap "chet giua batch": TU claim toan bo 20 muc (nhu the
        # drive_once vua bat dau mot chu ky) nhung KHONG xu ly gi ca —
        # tien trinh "chet" ngay sau claim.
        claimed = store.claim_pending_items(run.run_id, 20)
        self.assertEqual(len(claimed), 20)
        dem_ngay_sau_chet = store.count_items_by_status(run.run_id)
        self.assertEqual(dem_ngay_sau_chet[ScrapeItemStatus.PENDING.value], 20,
                         "muc claimed VAN la 'pending' (claim khong doi status)")

        # Thoi gian troi qua VUOT lease — mot trinh dieu phoi MOI (khoi
        # dong lai) gio co the claim LAI cac muc nay, khong bi khoa chet
        # vinh vien boi lan claim "chet" truoc do.
        dong_ho["t"] = CLAIM_LEASE_SECONDS + 10
        service.drive_once(run.run_id)

        dem_cuoi = store.count_items_by_status(run.run_id)
        self.assertEqual(dem_cuoi[ScrapeItemStatus.REVIEW_READY.value], 20)
        self.assertEqual(dem_cuoi[ScrapeItemStatus.PENDING.value], 0)
        self.assertEqual(store.get_run(run.run_id).status, ScrapeRunStatus.COMPLETED)


class CrashRightAfterPlanCreationTest(unittest.TestCase):
    """Diem crash: NGAY SAU khi tao ke hoach (`plan_run` da tao xong TAT
    CA muc `pending`), TRUOC khi bat ky `drive_once` nao chay. Khoi dong
    lai (mot `ScrapeRunService` MOI, cung store) phai thay dung trang
    thai va tiep tuc duoc, KHONG tao trung muc nao qua `plan_run` lai."""

    def test_plan_run_lai_sau_crash_khong_tao_trung_muc(self):
        pages = _make_pages(15)
        pipeline, store, service = _make_service(pages, chapters_per_cycle=5)
        run = service.plan_run(f"{_BASE}/truyen/x")
        # "Chet" ngay sau day — KHONG drive gi ca.

        # Khoi dong lai: MOT pipeline/service MOI tu CUNG store (mo phong
        # tien trinh moi, state duoc nap lai tu ban ghi ben vung — dung
        # nguyen tac voi `state_reconstruct.rebuild_state` that).
        from server.scraper.state_reconstruct import rebuild_state
        adapter_moi = GenericIndexAdapter(
            FixtureFetcher(dict(pages)), chapter_href_pattern=r"/chuong-\d+")
        pipeline_moi = StoryIngestionPipeline(adapter_moi, rebuild_state(store, run.run_id))
        service_moi = ScrapeRunService(pipeline_moi, store, chapters_per_cycle=5)

        run_lai = service_moi.plan_run(f"{_BASE}/truyen/x")
        self.assertEqual(len(store.list_items(run.run_id, limit=None)), 15,
                         "plan_run lai sau crash KHONG duoc tao them muc")
        self.assertEqual(run_lai.run_id, run.run_id)

        while True:
            r = store.get_run(run.run_id)
            if r.is_terminal:
                break
            service_moi.drive_once(run.run_id)

        dem = store.count_items_by_status(run.run_id)
        self.assertEqual(dem[ScrapeItemStatus.REVIEW_READY.value], 15)


class CrashDuringRetryTest(unittest.TestCase):
    """Diem crash: TRONG LUC operator vua goi `retry_failed` (muc da
    chuyen ve `pending`) nhung TRUOC khi `drive_once` tiep theo chay.
    Khoi dong lai phai thay muc do van `pending`, san sang duoc drive
    binh thuong — khong bi "ket" o trang thai lung chung."""

    def test_muc_da_retry_nhung_chua_drive_van_an_toan_sau_crash(self):
        so_lan_goi = {"chuong-3": 0}

        def handler_that_bai_mot_lan(inner):
            def fetch(url, **kw):
                if url.endswith("chuong-3") and so_lan_goi["chuong-3"] == 0:
                    so_lan_goi["chuong-3"] += 1
                    raise FetchError("lỗi mạng tạm thời giả lập")
                return inner.fetch(url, **kw)
            return fetch

        pages = _make_pages(5)
        adapter = GenericIndexAdapter(FixtureFetcher(dict(pages)), chapter_href_pattern=r"/chuong-\d+")
        adapter._fetcher.fetch = handler_that_bai_mot_lan(FixtureFetcher(dict(pages)))
        pipeline = StoryIngestionPipeline(adapter, ScrapeState())
        store = MockScrapeRunStore()
        service = ScrapeRunService(pipeline, store, chapters_per_cycle=5)
        run = service.plan_run(f"{_BASE}/truyen/x")
        service.drive_once(run.run_id)

        dem_truoc_retry = store.count_items_by_status(run.run_id)
        self.assertEqual(dem_truoc_retry[ScrapeItemStatus.FAILED.value], 1)

        service.retry_failed(run.run_id)
        # "Chet" NGAY SAU retry_failed — muc do gio la 'pending'. Mo
        # phong khoi dong lai bang chinh service nay (store la nguon su
        # that ben vung, khong quan he gi toi viec service con "song"
        # hay khong trong mo hinh tien trinh moi-lan-goi-moi).
        muc_sau_retry = [m for m in store.list_items(run.run_id, limit=None)
                        if m.chapter_url.endswith("chuong-3")][0]
        self.assertEqual(muc_sau_retry.status, ScrapeItemStatus.PENDING)
        self.assertEqual(muc_sau_retry.claimed_at, "",
                         "muc retry KHONG duoc con giu claim cu tu lan that bai truoc")

        while True:
            r = store.get_run(run.run_id)
            if r.is_terminal:
                break
            service.drive_once(run.run_id)

        dem_cuoi = store.count_items_by_status(run.run_id)
        self.assertEqual(dem_cuoi[ScrapeItemStatus.REVIEW_READY.value], 5)
        self.assertEqual(dem_cuoi[ScrapeItemStatus.FAILED.value], 0)


if __name__ == "__main__":
    unittest.main()
