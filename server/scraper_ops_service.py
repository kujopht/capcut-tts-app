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
from urllib.parse import urlsplit

from server.scraper import site_registry
from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
from server.scraper.adapters.json_ld_adapter import JsonLdAwareAdapter
from server.scraper.bulk import ScrapeRunService
from server.scraper.discovery import (
    SourceConfidence, UnknownSiteDiscoveryEngine,
)
from server.scraper.http_fetcher import HttpFetcher
from server.scraper.pipeline import StoryIngestionPipeline
from server.scraper.run_state import run_fingerprint, run_id_from_fingerprint
from server.scraper.site_profile import (
    MockSiteProfileStore, profile_from_proposal,
)
from server.scraper.state_reconstruct import rebuild_state


class UnsupportedSiteError(Exception):
    """Domain cua URL chua co cau hinh SU DUNG DUOC (ca `site_registry` LAN
    mot `SiteProfile` da xac nhan deu khong co) — loi RO RANG cho operator,
    khong doan bua mot pattern co the sai. Neu day la lan dau gap domain
    nay, operator can goi `discover()` roi `confirm_unknown_source()`
    truoc (xem Phase 2/4 cua Story Harvester V3, docstring module nay)."""


class ScrapeRunNotFoundError(Exception):
    pass


def _domain_of(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


class ScraperOpsService:
    def __init__(self, store, *, chapters_per_cycle: int = 25,
                fetcher_factory=HttpFetcher, profile_store=None):
        self._store = store
        self._chapters_per_cycle = chapters_per_cycle
        #: Tiem duoc (mac dinh `HttpFetcher` that) — bo test thay bang
        #: `FixtureFetcher` de khong cham mang that, cung nguyen tac voi
        #: `sleep_fn`/`clock_fn` cua chinh `HttpFetcher`.
        self._fetcher_factory = fetcher_factory
        #: Kho `SiteProfile` (Phase 4) — mac dinh mot kho bo nho RIENG cho
        #: instance nay neu khong tiem (khop hanh vi CU truoc khi co
        #: SiteProfile: domain chua cau hinh luon that bai ro rang). Route
        #: THAT (`server/main.py`) LUON tiem mot kho ben vung dung chung —
        #: xem `server.appwrite_site_profile_store.build_site_profile_store`.
        self._profile_store = profile_store or MockSiteProfileStore()

    # -- xay dung pipeline/service MOI moi lan goi --------------------------

    def _adapter_from_config(self, cfg: site_registry.SiteConfig) -> JsonLdAwareAdapter:
        return JsonLdAwareAdapter(
            self._fetcher_factory(), chapter_href_pattern=cfg.chapter_href_pattern,
            title_suffix_to_strip=cfg.title_suffix_to_strip or None)

    def _adapter_for_url(self, url: str) -> JsonLdAwareAdapter:
        """Phan cap Phase 4: SiteConfig da xac minh (ky su) truoc, roi
        SiteProfile da hoc+xac nhan (operator) — CHI dung khi
        `is_usable` (LEARNING/VERIFIED, khong bao gio DEGRADED/DISABLED).
        Domain hoan toan chua biet PHAI di qua `discover()` +
        `confirm_unknown_source()` truoc, khong duoc tu dong doan o day."""
        cfg = site_registry.lookup(url)
        if cfg is not None:
            return self._adapter_from_config(cfg)

        profile = self._profile_store.get(_domain_of(url))
        if profile is not None and profile.is_usable and profile.chapter_pattern:
            return JsonLdAwareAdapter(
                self._fetcher_factory(), chapter_href_pattern=profile.chapter_pattern)

        ho_tro = ", ".join(site_registry.supported_domains()) or "(chưa có site nào)"
        raise UnsupportedSiteError(
            f"Trang này chưa được cấu hình cho việc quét tự động. "
            f"Các trang đã hỗ trợ sẵn: {ho_tro}. Nếu đây là trang mới, hãy "
            f"dùng 'Phân tích nguồn' để khám phá cấu trúc rồi xác nhận "
            f"trước khi bắt đầu quét thật.")

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

    def _co_the_dung_ngay(self, url: str) -> bool:
        """Domain nay co MOT cau hinh su dung duoc NGAY (SiteConfig xac
        minh HOAC SiteProfile is_usable co pattern) hay khong — dung de
        `discover()` re nhanh sang duong kham pha (Phase 2) thay vi thu
        xay adapter roi bat `UnsupportedSiteError`."""
        if site_registry.lookup(url) is not None:
            return True
        profile = self._profile_store.get(_domain_of(url))
        return bool(profile is not None and profile.is_usable and profile.chapter_pattern)

    def discover(self, url: str) -> Dict[str, Any]:
        """Xem truoc. Domain DA co cau hinh: KHONG ghi gi
        (`plan_run(dry_run=True)`) — dung cho buoc 'paste URL -> preview'
        truoc khi operator bam 'Bắt đầu nhập'. Domain CHUA co cau hinh:
        chay `UnknownSiteDiscoveryEngine` (Phase 2), tra ve DE XUAT
        ('NEW SOURCE DETECTED') thay vi bat loi — operator xac nhan qua
        `confirm_unknown_source()` neu muon dung tiep."""
        if self._co_the_dung_ngay(url):
            svc = self._service_for_new(url)
            run = svc.plan_run(url, dry_run=True)
            return {"run": run, "supported": True}

        engine = UnknownSiteDiscoveryEngine(self._fetcher_factory())
        proposal = engine.discover(url)
        return {"supported": False, "new_source_detected": True, "proposal": proposal}

    def confirm_unknown_source(self, url: str) -> Dict[str, Any]:
        """Operator xac nhan MOT de xuat discovery — chay LAI discovery
        (khong trang thai, toi da hai lan fetch, xem `discovery.py`) de co
        de xuat TUOI, roi luu thanh `SiteProfile` (status LEARNING). KHONG
        BAO GIO tu dong goi trong `discover()` — xac nhan PHAI la hanh
        dong RO RANG cua operator (Phase 2: "MEDIUM cần operator review"),
        va LOW luon bi tu choi o day (Phase 2: "LOW fails safely")."""
        if site_registry.lookup(url) is not None:
            raise ValueError(
                "Domain này đã có cấu hình xác minh sẵn — không cần xác "
                "nhận qua khám phá tự động.")
        engine = UnknownSiteDiscoveryEngine(self._fetcher_factory())
        proposal = engine.discover(url)
        if proposal.confidence == SourceConfidence.LOW or not proposal.chapter_url_pattern:
            raise ValueError(
                "Độ tin cậy khám phá quá thấp (LOW) hoặc không tìm được "
                "mẫu URL chương lặp lại — không thể xác nhận nguồn này. "
                "Đây có thể không phải trang mục lục, trang cần "
                "JavaScript để hiển thị, hoặc cần một kỹ sư cấu hình thủ "
                "công (site_registry) nếu đây là nguồn quan trọng.")
        saved = self._profile_store.upsert(profile_from_proposal(proposal))
        return {"profile": saved, "proposal": proposal}

    def start_or_continue(self, url: str, *, chapter_limit: Optional[int] = None
                          ) -> Dict[str, Any]:
        svc = self._service_for_new(url)
        run = svc.plan_run(url, chapter_limit=chapter_limit)
        return {"run": run, "progress": run.progress()}

    def drive(self, run_id: str, *, max_chapters: Optional[int] = None) -> Dict[str, Any]:
        svc = self._service_for_run(run_id)
        before = self._store.count_items_by_status(run_id)
        counts = svc.drive_once(run_id, max_chapters=max_chapters)
        run = self._store.get_run(run_id)
        self._dong_bo_ket_qua_profile(run, before, counts)
        return {"run": run, "counts": counts, "progress": run.progress() if run else {}}

    def _dong_bo_ket_qua_profile(self, run, before: Dict[str, int],
                                 after: Dict[str, int]) -> None:
        """Cap nhat SiteProfile (neu domain nay dang dung mot profile HOC
        duoc, khong phai SiteConfig xac minh — `get()` tra ve `None` cho
        domain xac minh vi chua bao gio co profile nao duoc tao) dua tren
        SO CHUONG MOI thanh cong/loi trong CHINH chu ky nay. PHAI la HIEU
        SO truoc/sau, KHONG PHAI dung thang `after` — `after` la TONG TICH
        LUY tu dau dot (xem `bulk.py::drive_once`), dung thang se lam
        `consecutive_failures` tang moi chu ky chi vi dot TUNG co it nhat
        mot loi tu truoc, du chu ky hien tai khong loi them chuong nao."""
        if run is None:
            return
        domain = _domain_of(run.source_url)
        profile = self._profile_store.get(domain)
        if profile is None:
            return
        moi_thanh_cong = after.get("review_ready", 0) - before.get("review_ready", 0)
        moi_loi = after.get("failed", 0) - before.get("failed", 0)
        for _ in range(max(0, moi_thanh_cong)):
            self._profile_store.record_success(domain)
        for _ in range(max(0, moi_loi)):
            self._profile_store.record_failure(domain)

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
