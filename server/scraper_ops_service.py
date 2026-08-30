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

import hashlib
from dataclasses import replace
from typing import Any, Dict, List, Optional

from server.domain import Chapter, Novel, PublishState
from server.scraper import site_registry
from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
from server.scraper.adapters.json_ld_adapter import JsonLdAwareAdapter
from server.scraper.adapters.navigation_only_adapter import NavigationOnlyAdapter
from server.scraper.bulk import ScrapeRunService
from server.scraper.contract import domain_of
from server.scraper.content_extraction import extract_content_v3
from server.scraper.dedupe import content_hash
from server.scraper.discovery import (
    SourceConfidence, UnknownSiteDiscoveryEngine,
)
from server.scraper.http_fetcher import FetchError, HttpFetcher
from server.scraper.incremental import diff_toc
from server.scraper.pipeline import StoryIngestionPipeline
from server.scraper.run_state import (
    ScrapeItemStatus, ScrapeRun, run_fingerprint, run_id_from_fingerprint,
)
from server.scraper.adapters.scrapling_relocation import (
    attempt_adaptive_relocation, is_scrapling_available, save_verified_element,
)
from server.scraper.self_healing import RelocationConfidence, validate_relocated_content
from server.scraper.site_profile import (
    MockSiteProfileStore, ProfileStatus, profile_from_proposal,
)
from server.scraper.state_reconstruct import rebuild_state
from server.scraper.story_identity import (
    IdentitySignals, SameWorkConfidence, compare_identity,
)


#: PHAI khop `scripts/setup_appwrite.py` (collection `site_profiles`,
#: thuoc tinh `adaptive_fingerprint_json`) — xem `_thu_luu_dau_van_tay_thich_ung`.
_GIOI_HAN_KY_TU_DAU_VAN_TAY = 2000


class UnsupportedSiteError(Exception):
    """Domain cua URL chua co cau hinh SU DUNG DUOC (ca `site_registry` LAN
    mot `SiteProfile` da xac nhan deu khong co) — loi RO RANG cho operator,
    khong doan bua mot pattern co the sai. Neu day la lan dau gap domain
    nay, operator can goi `discover()` roi `confirm_unknown_source()`
    truoc (xem Phase 2/4 cua Story Harvester V3, docstring module nay)."""


class ScrapeRunNotFoundError(Exception):
    pass


class PublishNotConfiguredError(Exception):
    """`ScraperOpsService` duoc dung KHONG co `metadata_store` — chi doc/
    duyet duoc, khong the `publish_reviewed_items`. Xem
    `server/main.py`'s wiring cua `ScraperOpsService`."""


def deterministic_novel_id(run_id: str) -> str:
    """Novel_id TAT DINH tu run_id — cung MOT dot scrape LUON tao (hoac tai
    su dung) CUNG mot Novel du `publish_reviewed_items` duoc goi lai bao
    nhieu lan. Ngan hon `run_id` (da co tien to `scr_`) de tranh nham voi
    Novel do tac gia that tao (`new_id("nov")`, UUID ngau nhien)."""
    return "nov_" + hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:20]


def deterministic_chapter_id(item_id: str) -> str:
    """Chapter_id TAT DINH tu item_id — la co so cho tinh idempotent cua
    `create_chapter_once` qua nhieu lan goi publish cho CUNG mot muc."""
    return "chp_" + hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:20]


def _mo_ta_nguon_goc(run: ScrapeRun) -> str:
    """Van ban mo ta cho Novel THAT tao boi harvester — provenance may doc
    duoc THAT SU van la lien ket `ScrapeRun`/`ScrapeRunItem` (run_id ->
    source_url), day chi la ban tom tat cho NGUOI xem trang quan tri/trang
    Novel truoc khi publish that su."""
    phan = []
    if run.series_description:
        phan.append(run.series_description)
    if run.series_author:
        phan.append(f"Tác giả: {run.series_author}")
    phan.append(f"Nguồn: {run.source_url}")
    return "\n\n".join(phan)[:2000]


class ScraperOpsService:
    def __init__(self, store, *, chapters_per_cycle: int = 25,
                fetcher_factory=HttpFetcher, profile_store=None,
                metadata_store=None):
        self._store = store
        self._chapters_per_cycle = chapters_per_cycle
        #: Tiem duoc (mac dinh `HttpFetcher` that) — bo test thay bang
        #: `FixtureFetcher` de khong cham mang that, cung nguyen tac voi
        #: `sleep_fn`/`clock_fn` cua chinh `HttpFetcher`.
        self._fetcher_factory = fetcher_factory
        #: Kho Novel/Chapter THAT (`server.adapters.MetadataStore`) — RIENG
        #: voi `self._store` (chi la hang doi duyet). `None` = instance nay
        #: CHI doc/duyet, `publish_reviewed_items` se tu choi ro rang thay
        #: vi nem `AttributeError` mo ho. Production Story + Audio
        #: Harvester Launch — truoc ban nay, khong co duong nao noi hang doi
        #: duyet toi Novel/Chapter that ca (xem docstring
        #: `publish_reviewed_items`).
        self._metadata_store = metadata_store
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
        de xuat TUOI, roi luu thanh `SiteProfile`. KHONG BAO GIO tu dong
        goi trong `discover()` — xac nhan PHAI la hanh dong RO RANG cua
        operator (Phase 2: "MEDIUM cần operator review"), va LOW luon bi
        tu choi o day (Phase 2: "LOW fails safely").

        Phase 5 (self-healing): neu domain nay DA co mot `SiteProfile`
        DEGRADED (vuot nguong loi lien tiep), day la mot lan "tu-chua" —
        KHONG chi tin discovery confidence MEDIUM/HIGH don thuan, con phai
        qua `validate_relocated_content` (kiem tra cau truc THEM: khong
        trung chuong truoc/khong giong trang dang nhap-loi) truoc khi chap
        nhan revision moi. `revision` tang len 1 moi lan xac nhan LAI mot
        domain DA co profile (bat ke DEGRADED hay khong).

        P2 (overnight hardening) — NANG TANG THAT qua Scrapling: neu kiem
        tra Tier 0 (`validate_relocated_content`, dua tren heuristic mat do
        doan van/ranh gioi noi dung) o tren KHONG dat HIGH, VA domain nay
        co dau van tay thich ung da luu tu lan xac nhan THANH CONG gan nhat
        (`profile_cu.adaptive_fingerprint_json`), thu THEM mot lan dinh vi
        lai qua Scrapling THAT SU (`attempt_adaptive_relocation`) truoc khi
        chap nhan/tu choi — dung nguyen tac "chi nang tang khi Tier 0 that
        bai" cua `tier_escalation.py`. Ket qua CHI co the CAI THIEN quyet
        dinh Tier 0 (LOW/MEDIUM -> HIGH) hoac CHAN THEM (MEDIUM tu Scrapling
        -> yeu cau operator xem lai, NGHIEM NGAT hon MEDIUM cua Tier 0 vi
        day la doan lai cau truc tren toan bo cay HTML, khong phai heuristic
        don gian) — KHONG BAO GIO lam GIAM mot ket qua Tier 0 da HIGH san
        (Scrapling khong duoc goi trong truong hop do, xem yeu cau "khong
        goi khong can thiet" cua nhiem vu)."""
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

        domain = domain_of(proposal.canonical_url)
        profile_cu = self._profile_store.get(domain)
        profile_moi = profile_from_proposal(proposal)
        if profile_cu is not None:
            profile_moi = replace(profile_moi, revision=profile_cu.revision + 1)

        mau_html_da_tai: Optional[str] = None
        if profile_cu is not None and profile_cu.status == ProfileStatus.DEGRADED:
            if not proposal.sample_chapter_urls:
                raise ValueError(
                    "Nguồn này đang ở trạng thái DEGRADED (nhiều lần lỗi "
                    "liên tiếp) và lần khám phá lại không tìm được trang "
                    "chương mẫu để xác nhận cấu trúc — không thể tự động "
                    "khôi phục, cần kỹ sư kiểm tra thủ công.")
            try:
                mau = self._fetcher_factory().fetch(proposal.sample_chapter_urls[0])
            except FetchError as exc:
                raise ValueError(
                    f"Không tải được trang chương mẫu để xác nhận khôi "
                    f"phục: {exc}") from exc
            mau_html_da_tai = mau.text

            # Phase 5 ("kiem tra khong trung chuong TRUOC DO"): tai THEM
            # mot trang chuong mau THU HAI (neu discovery tim duoc) de co
            # gi do THAT SU de so sanh — phat hien qua review doc lap
            # (Codex): thieu buoc nay, `previous_chapter_content_hash`
            # LUON la `None` (chi fetch DUY NHAT mot trang mau), khien
            # nhanh kiem tra "trung chuong truoc" cua `validate_relocated_content`
            # KHONG BAO GIO thuc su chay trong luong nay — mot selector da
            # hong tra ve CUNG mot noi dung tinh cho MOI URL chuong se
            # khong bi bat o day (chi bi bat SAU do, khi `drive_once` that
            # su chay va Phase 8 gan nhan POSSIBLE_DUPLICATE tren tung
            # chuong — cham hon nhieu so voi muc dich cua cong kiem tra
            # nay). KHONG bat buoc (`len(...) < 2` hoac fetch loi thi bo
            # qua kiem tra THEM nay, KHONG chan ca luong khoi phuc — day
            # la mot lop phong ve BO SUNG, khong phai dieu kien tien quyet).
            hash_chuong_mau_khac: Optional[str] = None
            if len(proposal.sample_chapter_urls) >= 2:
                try:
                    mau_khac = self._fetcher_factory().fetch(
                        proposal.sample_chapter_urls[1])
                    hash_chuong_mau_khac = content_hash(extract_content_v3(
                        mau_khac.text, chapter_title=proposal.work_title).clean_text)
                except FetchError:
                    pass

            xac_thuc = validate_relocated_content(
                mau.text, chapter_title=proposal.work_title,
                previous_chapter_content_hash=hash_chuong_mau_khac)

            if (xac_thuc.confidence != RelocationConfidence.HIGH
                    and profile_cu.adaptive_fingerprint_json
                    and is_scrapling_available()):
                thich_ung = attempt_adaptive_relocation(
                    profile_cu.adaptive_fingerprint_json, mau.text,
                    url=proposal.sample_chapter_urls[0],
                    chapter_title=proposal.work_title,
                    previous_chapter_content_hash=hash_chuong_mau_khac)
                if (thich_ung.confidence == RelocationConfidence.HIGH
                        and not thich_ung.is_ambiguous):
                    xac_thuc = replace(xac_thuc, confidence=RelocationConfidence.HIGH,
                                       evidence=xac_thuc.evidence + thich_ung.evidence,
                                       clean_text=thich_ung.clean_text or xac_thuc.clean_text)
                    if thich_ung.candidate_selector:
                        profile_moi = replace(
                            profile_moi, content_fingerprint=thich_ung.candidate_selector)
                elif thich_ung.confidence == RelocationConfidence.MEDIUM:
                    raise ValueError(
                        "Scrapling định vị lại thích ứng tìm được một ứng "
                        "viên, nhưng độ tin cậy chỉ ở mức MEDIUM (mơ hồ "
                        "hoặc bằng chứng nội dung chưa đủ mạnh): " +
                        " ".join(thich_ung.evidence) +
                        " — cần kỹ sư/operator xem lại thủ công trước khi "
                        "chấp nhận khôi phục, KHÔNG tự động ghi đè "
                        "SiteProfile.")

            if xac_thuc.confidence == RelocationConfidence.LOW:
                raise ValueError(
                    "Kiểm tra cấu trúc (Phase 5) từ chối đề xuất khôi "
                    "phục này: " + " ".join(xac_thuc.evidence) +
                    " — nguồn vẫn ở trạng thái DEGRADED, cần kỹ sư kiểm "
                    "tra thủ công thay vì tự động khôi phục.")

        # P2 (overnight hardening): "known-good chapter element -> save/
        # fingerprint" — luu lai dau van tay CAU TRUC (KHONG PHAI HTML tho,
        # xem docstring `scrapling_relocation.save_verified_element`) cua
        # vung noi dung VUA duoc xac nhan o tren, de LAN DEGRADED SAU (neu
        # co) co gi do THAT de thu dinh vi lai — BEST-EFFORT TUYET DOI:
        # bat MOI ngoai le, khong bao gio de buoc nay chan xac nhan dang
        # thanh cong (Scrapling la kha nang nang tang tuy chon, khong phai
        # dieu kien de xac nhan mot nguon).
        profile_moi = replace(
            profile_moi,
            adaptive_fingerprint_json=self._thu_luu_dau_van_tay_thich_ung(
                proposal, profile_cu, sample_html=mau_html_da_tai))

        saved = self._profile_store.upsert(profile_moi)
        return {"profile": saved, "proposal": proposal}

    def _thu_luu_dau_van_tay_thich_ung(
            self, proposal, profile_cu: Optional["SiteProfile"],
            *, sample_html: Optional[str] = None) -> str:
        """Tra ve JSON cua dau van tay moi (de ghi vao
        `SiteProfile.adaptive_fingerprint_json`), hoac chuoi rong neu
        khong the luu (Scrapling khong san sang, khong co
        `content_container_candidate`/`sample_chapter_urls`, fetch loi,
        hoac selector khong khop trang mau) — chuoi rong la trang thai AN
        TOAN MAC DINH, giu nguyen hanh vi truoc khi co tinh nang nay.

        `sample_html` cho phep tai su dung trang mau DA TAI o nhanh DEGRADED
        (tranh fetch lai CUNG mot URL lan thu hai trong cung mot lan goi
        `confirm_unknown_source`)."""
        if not is_scrapling_available():
            return ""
        if not proposal.content_container_candidate or not proposal.sample_chapter_urls:
            return (profile_cu.adaptive_fingerprint_json
                    if profile_cu is not None else "")
        try:
            if sample_html is None:
                sample_html = self._fetcher_factory().fetch(
                    proposal.sample_chapter_urls[0]).text
            fingerprint = save_verified_element(
                sample_html, proposal.content_container_candidate,
                url=proposal.sample_chapter_urls[0])
        except Exception:
            return profile_cu.adaptive_fingerprint_json if profile_cu is not None else ""
        if fingerprint is None:
            return profile_cu.adaptive_fingerprint_json if profile_cu is not None else ""
        import json
        as_json = json.dumps(fingerprint)
        if len(as_json) > _GIOI_HAN_KY_TU_DAU_VAN_TAY:
            # Vuot gioi han thuoc tinh Appwrite (xem scripts/setup_appwrite.py,
            # collection site_profiles) — bo qua BAN GHI MOI thay vi de
            # Appwrite tu choi ghi sau nay, giu nguyen dau van tay CU (van
            # con dung duoc cho lan DEGRADED sau, hon la mat trang HOAN
            # TOAN chi vi mot chuong bat thuong co qua nhieu anh em/thuoc
            # tinh).
            return profile_cu.adaptive_fingerprint_json if profile_cu is not None else ""
        return as_json

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

    def publish_reviewed_items(
            self, run_id: str, *, owner_id: str,
            item_ids: Optional[List[str]] = None,
            max_items: Optional[int] = None) -> Dict[str, Any]:
        """
        Cầu nối còn thiếu (Production Story + Audio Harvester Launch):
        biến mục `REVIEW_READY` thành Novel/Chapter THẬT ở trạng thái
        `draft` — trước bản này, hàng đợi duyệt không có đường nào dẫn tới
        Novel/Chapter thật cả (`run_state.py` cố ý không lưu `clean_text`;
        đường ghi thật duy nhất từng có là kịch bản canary dùng
        `settings.canary_user_id`, tạo rồi TỰ XOÁ ngay trong cùng lần chạy).

        KHÔNG tự publish (không gọi `/api/novels/{id}/publish`) — Novel/
        Chapter tạo ra ở đây LUÔN ở trạng thái `draft`, chờ một bước RÕ
        RÀNG riêng (operator thật, hoặc một lời gọi publish riêng) trước
        khi công khai — đúng yêu cầu "staging before publication".

        Idempotent ở CẢ HAI cấp: đợt (`ScrapeRun.published_novel_id`) và
        từng mục (`ScrapeRunItem.published_chapter_id`) — gọi lại hàm này
        nhiều lần trên CÙNG một đợt chỉ xử lý các mục CHƯA publish, không
        tạo trùng Novel/Chapter, kể cả khi tiến trình chết giữa chừng (xem
        `deterministic_chapter_id`/`create_chapter_once`'s compare-and-set).

        NỘI DUNG ĐƯỢC TẢI LẠI TỪ NGUỒN (không đọc từ `ScrapeRunItem` — cố ý
        không lưu `clean_text`, xem docstring đầu `run_state.py`) rồi
        `content_hash` tính lại được SO SÁNH với `content_hash` đã lưu từ
        lúc duyệt — lệch nhau nghĩa là nội dung nguồn đã đổi KỂ TỪ lúc
        duyệt, từ chối publish mục đó và báo rõ thay vì âm thầm xuất bản
        nội dung KHÁC với nội dung đã được duyệt.

        Một mục lỗi (mạng, phân tích, lệch content_hash) KHÔNG được dừng cả
        đợt publish — ghi lại lỗi của riêng mục đó, tiếp tục các mục còn
        lại (cùng nguyên tắc với `bulk.py::drive_once`: "một chương lỗi
        không được dừng cả đợt quét hàng trăm/nghìn chương khác").
        """
        if self._metadata_store is None:
            raise PublishNotConfiguredError(
                "ScraperOpsService không có metadata_store — không thể publish.")
        run = self._store.get_run(run_id)
        if run is None:
            raise ScrapeRunNotFoundError(f"Không tìm thấy đợt quét: {run_id}")

        ung_vien = self._store.list_items(
            run_id, statuses=[ScrapeItemStatus.REVIEW_READY], limit=None)
        if item_ids is not None:
            muon = set(item_ids)
            ung_vien = [m for m in ung_vien if m.item_id in muon]
        # Da publish tu lan goi truoc — bo qua NGAY tu day (khong tai lai
        # noi dung vo ich), day la lop idempotent CHINH; `create_chapter_once`
        # ben duoi la lop BACKSTOP cho truong hop tien trinh chet GIUA
        # fetch xong va `save_item` ghi lai `published_chapter_id`.
        ung_vien = [m for m in ung_vien if not m.published_chapter_id]
        if max_items is not None:
            ung_vien = ung_vien[:max(0, max_items)]

        # Tao Novel CHI khi that su co viec de lam (`ung_vien` khong rong)
        # HOAC dot nay da tung publish tu truoc (tai su dung, khong tao
        # lai) — mot loi goi voi `item_ids` loc ra RONG (vd go nham id)
        # khong duoc phep de lai mot Novel draft MO COI, khong chuong nao.
        novel_id = run.published_novel_id
        if not novel_id and ung_vien:
            novel = Novel(
                owner_id=owner_id, title=run.series_title or run.source_domain,
                description=_mo_ta_nguon_goc(run),
                novel_id=deterministic_novel_id(run_id), state=PublishState.DRAFT)
            self._metadata_store.create_novel(novel)
            run = self._store.save_run(run_id, published_novel_id=novel.novel_id)
            novel_id = novel.novel_id

        adapter = self._adapter_for_url(run.source_url)
        series = adapter.discover_series(run.source_url) if ung_vien else None

        da_publish: List[str] = []
        da_co_tu_truoc = 0
        loi: List[Dict[str, Any]] = []
        for muc in ung_vien:
            try:
                raw_html = adapter.fetch_chapter(muc.chapter_url)
                chuong_chuan = adapter.normalize_chapter(muc.chapter_url, raw_html, series)
            except Exception as exc:                            # noqa: BLE001
                loi.append({"item_id": muc.item_id, "stage": "fetch",
                           "message": str(exc)[:500]})
                continue

            hash_hien_tai = content_hash(chuong_chuan.clean_text)
            if muc.content_hash and hash_hien_tai != muc.content_hash:
                loi.append({
                    "item_id": muc.item_id, "stage": "content_mismatch",
                    "message": (
                        "Nội dung nguồn đã đổi kể từ lúc duyệt "
                        f"(hash cũ {muc.content_hash[:12]}, hash mới "
                        f"{hash_hien_tai[:12]}) - từ chối publish, cần duyệt lại.")})
                continue

            chapter = Chapter(
                novel_id=novel_id, owner_id=owner_id,
                title=muc.chapter_title or chuong_chuan.chapter_title,
                content=chuong_chuan.clean_text,
                order_index=muc.chapter_number or (muc.sequence + 1),
                state=PublishState.DRAFT,
                chapter_id=deterministic_chapter_id(muc.item_id))
            da_tao, la_moi = self._metadata_store.create_chapter_once(chapter)
            self._store.save_item(muc.item_id, published_chapter_id=da_tao.chapter_id)
            if la_moi:
                da_publish.append(da_tao.chapter_id)
            else:
                da_co_tu_truoc += 1

        return {
            "run_id": run_id, "novel_id": novel_id,
            "published_count": len(da_publish),
            "published_chapter_ids": da_publish,
            "already_published_count": da_co_tu_truoc,
            "error_count": len(loi),
            "errors": loi,
        }
