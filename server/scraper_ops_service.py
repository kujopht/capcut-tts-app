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
from server.scraper.adapters.json_ld_adapter import JsonLdAwareAdapter
from server.scraper.adapters.navigation_only_adapter import NavigationOnlyAdapter
from server.scraper.bulk import ScrapeRunService
from server.scraper.contract import domain_of
from server.scraper.discovery import (
    SourceConfidence, UnknownSiteDiscoveryEngine,
)
from server.scraper.http_fetcher import HttpFetcher
from server.scraper.incremental import diff_toc
from server.scraper.pipeline import StoryIngestionPipeline
from server.scraper.run_state import run_fingerprint, run_id_from_fingerprint
from server.scraper.site_profile import (
    MockSiteProfileStore, profile_from_proposal,
)
from server.scraper.state_reconstruct import rebuild_state
from server.scraper.story_identity import (
    IdentitySignals, SameWorkConfidence, compare_identity,
)


class UnsupportedSiteError(Exception):
    """Domain cua URL chua co cau hinh SU DUNG DUOC (ca `site_registry` LAN
    mot `SiteProfile` da xac nhan deu khong co) — loi RO RANG cho operator,
    khong doan bua mot pattern co the sai. Neu day la lan dau gap domain
    nay, operator can goi `discover()` roi `confirm_unknown_source()`
    truoc (xem Phase 2/4 cua Story Harvester V3, docstring module nay)."""


class ScrapeRunNotFoundError(Exception):
    pass


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

    def _adapter_from_config(self, cfg: site_registry.SiteConfig):
        if cfg.adapter_kind == "navigation_only":
            # Phase 3 Story Harvester V3: nguon KHONG co trang muc luc —
            # `chapter_href_pattern` duoc HIEU LAI thanh `next_href_pattern`
            # (xem docstring `SiteConfig.adapter_kind`). Truoc ban sua nay,
            # `NavigationOnlyAdapter` CHUA BAO GIO duoc tao qua duong that
            # (chi test truc tiep goi no) — phat hien qua review doc lap
            # (Codex).
            return NavigationOnlyAdapter(
                self._fetcher_factory(), next_href_pattern=cfg.chapter_href_pattern)
        return JsonLdAwareAdapter(
            self._fetcher_factory(), chapter_href_pattern=cfg.chapter_href_pattern,
            title_suffix_to_strip=cfg.title_suffix_to_strip or None)

    def _adapter_for_url(self, url: str):
        """Phan cap Phase 4: SiteConfig da xac minh (ky su) truoc, roi
        SiteProfile da hoc+xac nhan (operator) — CHI dung khi
        `is_usable` (LEARNING/VERIFIED, khong bao gio DEGRADED/DISABLED).
        Domain hoan toan chua biet PHAI di qua `discover()` +
        `confirm_unknown_source()` truoc, khong duoc tu dong doan o day."""
        cfg = site_registry.lookup(url)
        if cfg is not None:
            return self._adapter_from_config(cfg)

        profile = self._profile_store.get(domain_of(url))
        if profile is not None and profile.is_usable and profile.chapter_pattern:
            # `min_delay_seconds`/`next_page_href_pattern` PHAI duoc dua tu
            # profile da hoc — thieu hai dong nay (phat hien qua review doc
            # lap, Codex), mot nguon hoc duoc luon dung gioi han toc do MAC
            # DINH cua `HttpFetcher` (bo qua `rate_limit_seconds` da hoc)
            # VA mot nguon co phan trang so (`pagination_strategy ==
            # numbered_pages`) am tham chi bao gio quet TRANG DAU cua muc
            # luc, khong bao gio thay chuong o cac trang sau.
            return JsonLdAwareAdapter(
                self._fetcher_factory(min_delay_seconds=profile.rate_limit_seconds),
                chapter_href_pattern=profile.chapter_pattern,
                next_page_href_pattern=profile.next_page_pattern or None)

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
        profile = self._profile_store.get(domain_of(url))
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

    def check_for_updates(self, run_id: str) -> Dict[str, Any]:
        """Phase 9 (Story Harvester V3): MOT LAN tai trang muc luc (KHONG
        tai chuong nao) de biet series nay co chuong MOI/da MAT so voi lan
        quet truoc hay khong — dung cho operator quyet dinh co dang
        `start_or_continue` lai hay khong, KHONG tu dong ghi gi (xem
        `incremental.diff_toc`). Khac `drive()`: khong xu ly muc PENDING
        nao, chi so sanh URL."""
        run = self._store.get_run(run_id)
        if run is None:
            raise ScrapeRunNotFoundError(f"Không tìm thấy đợt quét: {run_id}")
        adapter = self._adapter_for_url(run.source_url)
        state = rebuild_state(self._store, run_id)
        series = adapter.discover_series(run.source_url)
        chapter_urls = adapter.list_chapters(series)
        diff = diff_toc(state, chapter_urls)
        return {
            "run_id": run_id,
            "new_count": len(diff.new_urls),
            "removed_count": len(diff.removed_urls),
            "unchanged_count": diff.unchanged_count,
            "has_changes": diff.has_changes,
            "removed_urls": diff.removed_urls,
        }

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
        chu ky drive VUA CHAY. PHAI la HIEU SO truoc/sau, KHONG PHAI dung
        thang `after` — `after` la TONG TICH LUY tu dau dot (xem
        `bulk.py::drive_once`), dung thang se lam `consecutive_failures`
        tang moi chu ky chi vi dot TUNG co it nhat mot loi tu truoc, du chu
        ky hien tai khong loi them chuong nao.

        Goi `record_success`/`record_failure` TOI DA MOT LAN moi chu ky
        (uu tien thanh cong neu chu ky co CA HAI) — KHONG lap N lan theo so
        chuong moi thanh cong/loi. `drive_once` xu ly NHIEU chuong trong
        MOT chu ky nhung khong tra ve thu tu THAT SU cac chuong do thanh
        cong/loi xen ke nhau; lap rieng "tat ca thanh cong" roi "tat ca
        loi" theo hai vong lap tach biet (ban sua truoc day cua chinh ham
        nay) co the tinh SAI `consecutive_failures` so voi thu tu that su
        xay ra — phat hien qua review doc lap (Codex). Coi "chu ky nay co
        it nhat mot thanh cong" la tin hieu on dinh hon, du mat mot chut do
        chi tiet — muc dich cua `consecutive_failures` la phat hien "site
        nay dang LIEN TUC loi qua NHIEU CHU KY", khong phai theo doi tung
        chuong rieng le.

        GIOI HAN DA BIET, CHUA XU LY: ham nay (va `drive_once` no goi) KHONG
        khoa theo `run_id` — hai yeu cau `/drive` dong thoi cho CUNG mot
        `run_id` (vd double-click, retry client) co the doc CUNG `before`,
        xu ly CHONG CHEO cac muc pending, va goi `record_success`/
        `record_failure` nhieu hon thuc te. Day la khoang trong DA CO SAN
        o tang `bulk.py::drive_once` (khong rieng ham nay them ra) — sua
        dung dan can mot co che khoa/nhan muc theo `run_id`, ngoai pham vi
        PR nay; frontend da tu gioi han goi tuan tu (xem admin/scraper/
        page.tsx, vong lap tu dong dung `setTimeout` noi tiep khong phai
        `setInterval`), nhung mot client khac/tab khac van co the gay ra."""
        if run is None:
            return
        domain = domain_of(run.source_url)
        profile = self._profile_store.get(domain)
        if profile is None:
            return
        moi_thanh_cong = after.get("review_ready", 0) - before.get("review_ready", 0)
        moi_loi = after.get("failed", 0) - before.get("failed", 0)
        if moi_thanh_cong > 0:
            self._profile_store.record_success(domain)
        elif moi_loi > 0:
            self._profile_store.record_failure(domain)

    def check_possible_mirror(self, url: str) -> Dict[str, Any]:
        """Phase 7 (Story Harvester V3): truoc khi bat dau quet mot nguon
        MOI, kiem tra xem no co GIONG mot dot da co trong kho hay khong
        (vd truyen bi dang lai/mirror tren domain khac) — tra ve TAT CA dot
        hien co voi confidence >= MEDIUM, sap xep confidence cao truoc.
        KHONG tu dong chan/gop gi — CHI la thong tin cho operator xem xet
        (xem `story_identity.py`, nguyen tac "khong bao gio gop chi tu
        title"). CHUA chua NOI DUNG chuong nao (chua quet), nen CHI dung
        tin hieu tieu de/tac gia/mo ta/so chuong — content_hash (tin hieu
        manh nhat) khong ap dung duoc o buoc TRUOC KHI quet nay."""
        tin_hieu_moi = self._tin_hieu_nhan_dang_cho(url)
        ket_qua: list = []
        for run in self._store.list_runs():
            tin_hieu_cu = IdentitySignals(
                canonical_url=run.source_url,
                title=run.series_title,
                author=run.series_author or None,
                description=run.series_description or None,
                chapter_count=run.total_discovered or None,
            )
            so_sanh = compare_identity(tin_hieu_moi, tin_hieu_cu)
            if so_sanh.confidence in (SameWorkConfidence.HIGH, SameWorkConfidence.MEDIUM):
                ket_qua.append({
                    "run_id": run.run_id,
                    "series_title": run.series_title,
                    "source_url": run.source_url,
                    "confidence": so_sanh.confidence.value,
                    "evidence": so_sanh.evidence,
                    "matched_signals": so_sanh.matched_signals,
                })
        ket_qua.sort(key=lambda r: r["confidence"] != "high")
        return {"possible_mirrors": ket_qua}

    def _tin_hieu_nhan_dang_cho(self, url: str) -> IdentitySignals:
        """Xay `IdentitySignals` cho MOT url — dung duong DA CO CAU HINH
        (SiteConfig/SiteProfile) neu co, khong thi qua discovery engine
        (Phase 2) — CA HAI deu cho title/author/description/uoc luong so
        chuong ma KHONG can operator xac nhan gi truoc (chi kham pha, xem
        `discover()`)."""
        if self._co_the_dung_ngay(url):
            adapter = self._adapter_for_url(url)
            series = adapter.discover_series(url)
            return IdentitySignals(
                canonical_url=series.canonical_url, title=series.title,
                author=series.author, description=series.description,
                chapter_count=len(series.chapter_urls) or None)
        engine = UnknownSiteDiscoveryEngine(self._fetcher_factory())
        proposal = engine.discover(url)
        return IdentitySignals(
            canonical_url=proposal.canonical_url, title=proposal.work_title or "",
            author=proposal.author, description=proposal.description,
            chapter_count=proposal.chapter_count_estimate or None)

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
