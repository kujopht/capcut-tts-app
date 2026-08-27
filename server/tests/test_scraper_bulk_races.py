"""
Phase 16 cua Story Harvester V3 ("adversarial": races) — kiem chung
`ScrapeRunItem.claimed_at`/`MockScrapeRunStore.claim_pending_items`
(server/scraper/run_state.py) dong khe ho HAI loi goi `drive_once`
(server/scraper/bulk.py) DONG THOI tren CUNG mot `run_id`.

TAI HIEN TRUOC KHI SUA (ghi lai o day de nguoi doc sau hieu ly do can khoa
thue): 5 luong goi `service.drive_once(run_id)` song song tren MOT dot 40
chuong (`chapters_per_cycle=40`, du de MOI luong co the doc TOAN BO muc
`pending` trong MOT lan neu khong co claim) khien 6 chuong bi FETCH/XU LY
TRUNG — hai (hoac nhieu) luong cung doc duoc CUNG mot muc qua
`list_items(statuses=[pending])` (chi doc, khong giu cho) truoc khi bat
ky luong nao kip ghi lai trang thai moi. Sau ban sua nay (claim nguyen
tu), khong con URL nao bi fetch nhieu hon MOT lan.
"""
from __future__ import annotations

import threading
import unittest

from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
from server.scraper.bulk import ScrapeRunService
from server.scraper.dedupe import ScrapeState
from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.pipeline import StoryIngestionPipeline
from server.scraper.run_state import (
    MockScrapeRunStore, ScrapeItemStatus, ScrapeRunItem, ScrapeRunStatus,
)

_BASE = "https://vd-dua-tranh.example"


def _make_pages(n: int) -> dict:
    links = "".join(f'<li><a href="/truyen/x/chuong-{i}">C{i}</a></li>' for i in range(1, n + 1))
    pages = {f"{_BASE}/truyen/x": f"<html><body><ul>{links}</ul></body></html>"}
    for i in range(1, n + 1):
        pages[f"{_BASE}/truyen/x/chuong-{i}"] = (
            f"<html><body><article><h1>Chương {i}</h1><p>"
            + ("Nội dung chương đầy đủ dùng để kiểm thử đua tranh. " * 15)
            + "</p></article></body></html>"
        )
    return pages


class _CountingFetcher:
    """Boc MOT fetcher that, dem so lan `fetch()` duoc goi cho MOI URL —
    dung de phat hien fetch TRUNG (dau hieu hai trinh dieu phoi cung xu ly
    MOT chuong)."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self._lock = threading.Lock()
        self.counts: dict = {}

    def fetch(self, url: str, **kwargs):
        with self._lock:
            self.counts[url] = self.counts.get(url, 0) + 1
        return self._inner.fetch(url, **kwargs)


class ClaimPendingItemsUnitTest(unittest.TestCase):
    def test_claim_khong_tra_ve_muc_da_duoc_claim_con_thue(self):
        store = MockScrapeRunStore(now_fn=lambda: "2026-01-01T00:00:00+00:00")
        store.create_run_once(_run("r1"))
        store.create_item_once(ScrapeRunItem(
            run_id="r1", chapter_url="https://x.test/1", source_fingerprint="fp1",
            item_id="r1-fp1", sequence=0))
        store.create_item_once(ScrapeRunItem(
            run_id="r1", chapter_url="https://x.test/2", source_fingerprint="fp2",
            item_id="r1-fp2", sequence=1))

        lan_1 = store.claim_pending_items("r1", 1)
        self.assertEqual(len(lan_1), 1)
        self.assertEqual(lan_1[0].item_id, "r1-fp1")

        # Muc r1-fp1 DA duoc claim (thue chua het han) — lan claim tiep
        # theo PHAI bo qua no, lay muc CON LAI.
        lan_2 = store.claim_pending_items("r1", 5)
        self.assertEqual([m.item_id for m in lan_2], ["r1-fp2"])

    def test_claim_lai_duoc_muc_da_het_han_thue(self):
        dong_ho = {"t": 0}

        def now_fn():
            dong_ho["t"] += 1
            # Lan goi dau (t=1) dung cho create_item_once/create_run_once,
            # lan claim DAU (t=2) claim luc "t=2s", lan claim SAU (t=3)
            # phai thay DA het han neu lease_seconds=1.
            trai = ["2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00",
                   "2026-01-01T00:00:02+00:00", "2026-01-01T00:00:10+00:00"]
            return trai[min(dong_ho["t"] - 1, len(trai) - 1)]

        store = MockScrapeRunStore(now_fn=now_fn)
        store.create_run_once(_run("r2"))
        store.create_item_once(ScrapeRunItem(
            run_id="r2", chapter_url="https://x.test/1", source_fingerprint="fp1",
            item_id="r2-fp1", sequence=0))

        lan_1 = store.claim_pending_items("r2", 1, lease_seconds=1)
        self.assertEqual(len(lan_1), 1)

        # 8 giay sau (vuot lease_seconds=1) — muc phai claim LAI duoc, KHONG
        # bi khoa chet vinh vien vi trinh dieu phoi truoc "chet" giua chung.
        lan_2 = store.claim_pending_items("r2", 1, lease_seconds=1)
        self.assertEqual(len(lan_2), 1)
        self.assertEqual(lan_2[0].item_id, "r2-fp1")


class ConcurrentDriveOnceRaceTest(unittest.TestCase):
    def test_nhieu_luong_goi_drive_once_dong_thoi_khong_fetch_trung_mot_chuong(self):
        pages = _make_pages(40)
        counting = _CountingFetcher(FixtureFetcher(dict(pages)))
        adapter = GenericIndexAdapter(counting, chapter_href_pattern=r"/chuong-\d+")
        pipeline = StoryIngestionPipeline(adapter, ScrapeState())
        store = MockScrapeRunStore()
        service = ScrapeRunService(pipeline, store, chapters_per_cycle=40)
        run = service.plan_run(f"{_BASE}/truyen/x")

        errors = []

        def worker():
            try:
                service.drive_once(run.run_id)
            except Exception as exc:  # pragma: no cover - chi de bat loi that
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        chuong_urls = [u for u in counting.counts if "/chuong-" in u]
        fetch_trung = {u: c for u, c in counting.counts.items() if c > 1}
        self.assertEqual(fetch_trung, {}, "không được fetch trùng bất kỳ chương nào")
        self.assertEqual(len(chuong_urls), 40, "vẫn phải fetch đủ cả 40 chương")

        dem = store.count_items_by_status(run.run_id)
        self.assertEqual(dem[ScrapeItemStatus.REVIEW_READY.value], 40)
        self.assertEqual(dem[ScrapeItemStatus.PENDING.value], 0)
        self.assertEqual(store.get_run(run.run_id).status, ScrapeRunStatus.COMPLETED)


def _run(run_id: str):
    from server.scraper.run_state import ScrapeRun
    return ScrapeRun(source_url="https://x.test/", fingerprint="fp", run_id=run_id)


class _SkipDuringFetchFetcher:
    """Fetcher that goi MOT callback NGAY TRUOC KHI tra ve noi dung cho
    MOT url cu the — dung de mo phong "operator bam skip GIUA LUC
    drive_once dang fetch chuong nay", CHINH XAC thu tu thoi gian ma
    review doc lap (Codex) tim thay."""

    def __init__(self, inner, url_kich_hoat, callback) -> None:
        self._inner = inner
        self._url_kich_hoat = url_kich_hoat
        self._callback = callback
        self._da_kich_hoat = False

    def fetch(self, url: str, **kwargs):
        if url == self._url_kich_hoat and not self._da_kich_hoat:
            self._da_kich_hoat = True
            self._callback()
        return self._inner.fetch(url, **kwargs)


class SkipDuringInFlightFetchTest(unittest.TestCase):
    """Phase 16/adversarial follow-up (phat hien qua review doc lap,
    Codex): `drive_once` ghi hoan tat (REVIEW_READY/FAILED) VO DIEU KIEN,
    khong biet muc nay co the DA bi operator bam `skip()` giua luc dang
    fetch — "hoi sinh" am tham mot quyet dinh operator vua dua ra."""

    def test_skip_giua_luc_dang_fetch_khong_bi_ghi_de_thanh_review_ready(self):
        pages = _make_pages(5)
        url_dich = f"{_BASE}/truyen/x/chuong-3"

        adapter = GenericIndexAdapter(FixtureFetcher(dict(pages)), chapter_href_pattern=r"/chuong-\d+")
        pipeline = StoryIngestionPipeline(adapter, ScrapeState())
        store = MockScrapeRunStore()
        service = ScrapeRunService(pipeline, store, chapters_per_cycle=5)
        run = service.plan_run(f"{_BASE}/truyen/x")

        item_dich = next(m for m in store.list_items(run.run_id, limit=None)
                         if m.chapter_url == url_dich)

        def gia_lap_operator_bam_skip():
            service.skip(run.run_id, item_dich.item_id, reason="qua thoi han duyet")

        adapter._fetcher = _SkipDuringFetchFetcher(
            adapter._fetcher, url_dich, gia_lap_operator_bam_skip)

        service.drive_once(run.run_id)

        muc_sau = store.get_item(item_dich.item_id)
        self.assertEqual(muc_sau.status, ScrapeItemStatus.SKIPPED,
                         "skip() giữa lúc fetch KHÔNG được bị drive_once ghi đè lại")

        dem = store.count_items_by_status(run.run_id)
        self.assertEqual(dem[ScrapeItemStatus.SKIPPED.value], 1)
        self.assertEqual(dem[ScrapeItemStatus.REVIEW_READY.value], 4)


if __name__ == "__main__":
    unittest.main()
