"""
Tang dich vu cho API quan tri "Universal Story Scraper" — noi
`site_registry` (cau hinh site da xac minh), `HttpFetcher`/
`GenericIndexAdapter` (Tier 0), `StoryIngestionPipeline`,
`state_reconstruct` (nap lai `ScrapeState` tu kho ben vung) va
`ScrapeRunService` (`server/scraper/bulk.py`) gap nhau thanh cac ham don
gian cho route HTTP trong `server/main.py` goi — CUNG VAI TRO voi
`TrustedSourceService` cho YouTube.

MOI LOI GOI xay MOT `StoryIngestionPipeline` + `ScrapeRunService` MOI,
`ScrapeState` cua no duoc NAP LAI tu `ScrapeRunItem` da luu (xem
`state_reconstruct.py`) — khong co gi giu trong bo nho giua cac yeu cau
HTTP, moi thu ben vung deu di qua `store` (Mock hoac Appwrite, xem
`server/appwrite_scrape_run_store.py::build_scrape_run_store`).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from server.scraper import site_registry
from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
from server.scraper.bulk import ScrapeRunService
from server.scraper.http_fetcher import HttpFetcher
from server.scraper.pipeline import StoryIngestionPipeline
from server.scraper.run_state import run_fingerprint, run_id_from_fingerprint
from server.scraper.state_reconstruct import rebuild_state


class UnsupportedSiteError(Exception):
    """Domain cua URL chua duoc cau hinh trong `site_registry` — loi RO
    RANG cho operator, khong doan bua mot pattern co the sai."""


class ScrapeRunNotFoundError(Exception):
    pass


class ScraperOpsService:
    def __init__(self, store, *, chapters_per_cycle: int = 25,
                fetcher_factory=HttpFetcher):
        self._store = store
        self._chapters_per_cycle = chapters_per_cycle
        #: Tiem duoc (mac dinh `HttpFetcher` that) — bo test thay bang
        #: `FixtureFetcher` de khong cham mang that, cung nguyen tac voi
        #: `sleep_fn`/`clock_fn` cua chinh `HttpFetcher`.
        self._fetcher_factory = fetcher_factory

    # -- xay dung pipeline/service MOI moi lan goi --------------------------

    def _adapter_for_url(self, url: str) -> GenericIndexAdapter:
        cfg = site_registry.lookup(url)
        if cfg is None:
            ho_tro = ", ".join(site_registry.supported_domains()) or "(chưa có site nào)"
            raise UnsupportedSiteError(
                f"Trang này chưa được cấu hình cho việc quét tự động. "
                f"Các trang đã hỗ trợ: {ho_tro}. Cần một kỹ sư thêm cấu hình "
                f"cho domain mới trước khi dùng được.")
        return GenericIndexAdapter(
            self._fetcher_factory(), chapter_href_pattern=cfg.chapter_href_pattern,
            title_suffix_to_strip=cfg.title_suffix_to_strip or None)

    def _service_for_new(self, url: str) -> ScrapeRunService:
        """Neu series nay DA tung co dot scrape (cung URL, sau chuan hoa),
        phai nap lai `ScrapeState` cua no TRUOC khi goi `plan()` de
        resume()/loc trung hoat dong dung ngay tu lan preview dau tien —
        khong the biet `run_id` that su cho den khi `discover_series()`
        chay xong, nen goi mot lan RE de biet, roi de `plan_run()` (goi
        sau, o `discover`/`start_or_continue`) tu goi lai lan hai. Trang
        muc luc nhe, chi phi goi hai lan chap nhan duoc — xem docstring
        module."""
        adapter = self._adapter_for_url(url)
        series = adapter.discover_series(url)
        run_id = run_id_from_fingerprint(run_fingerprint(series.canonical_url))
        pipeline = StoryIngestionPipeline(adapter, rebuild_state(self._store, run_id))
        return ScrapeRunService(pipeline, self._store,
                                chapters_per_cycle=self._chapters_per_cycle)

    def _service_for_run(self, run_id: str) -> ScrapeRunService:
        run = self._store.get_run(run_id)
        if run is None:
            raise ScrapeRunNotFoundError(f"Không tìm thấy đợt quét: {run_id}")
        adapter = self._adapter_for_url(run.source_url)
        state = rebuild_state(self._store, run_id)
        pipeline = StoryIngestionPipeline(adapter, state)
        return ScrapeRunService(pipeline, self._store,
                                chapters_per_cycle=self._chapters_per_cycle)

    # -- duong operator goi ---------------------------------------------------

    def discover(self, url: str) -> Dict[str, Any]:
        """Xem truoc — KHONG ghi gi (`plan_run(dry_run=True)`). Dung cho
        buoc 'paste URL -> preview' truoc khi operator bam 'Bắt đầu nhập'."""
        svc = self._service_for_new(url)
        run = svc.plan_run(url, dry_run=True)
        return {"run": run, "supported": True}

    def start_or_continue(self, url: str, *, chapter_limit: Optional[int] = None
                          ) -> Dict[str, Any]:
        svc = self._service_for_new(url)
        run = svc.plan_run(url, chapter_limit=chapter_limit)
        return {"run": run, "progress": run.progress()}

    def drive(self, run_id: str, *, max_chapters: Optional[int] = None) -> Dict[str, Any]:
        svc = self._service_for_run(run_id)
        counts = svc.drive_once(run_id, max_chapters=max_chapters)
        run = self._store.get_run(run_id)
        return {"run": run, "counts": counts, "progress": run.progress() if run else {}}

    def cancel(self, run_id: str) -> Dict[str, Any]:
        svc = self._service_for_run(run_id)
        return svc.request_cancel(run_id)

    def retry(self, run_id: str, *, item_id: str = "") -> Dict[str, Any]:
        svc = self._service_for_run(run_id)
        return svc.retry_failed(run_id, item_id=item_id)

    def skip(self, run_id: str, item_id: str, *, reason: str = "") -> Dict[str, Any]:
        svc = self._service_for_run(run_id)
        return svc.skip(run_id, item_id, reason=reason)

    def view(self, run_id: str, *, limit: int = 50, offset: int = 0,
            status: str = "") -> Dict[str, Any]:
        run = self._store.get_run(run_id)
        if run is None:
            raise ScrapeRunNotFoundError(f"Không tìm thấy đợt quét: {run_id}")
        svc = self._service_for_run(run_id)
        return svc.run_view(run_id, limit=limit, offset=offset, status=status)

    def list_runs(self) -> Dict[str, Any]:
        return {"runs": self._store.list_runs(), "supported_domains": site_registry.supported_domains()}
