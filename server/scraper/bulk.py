"""
Dieu phoi MOT dot scrape HANG LOAT (quy mo 10/100/500 chuong) — tang dieu
phoi TREN `StoryIngestionPipeline` (`pipeline.py`), them tien do/uoc luong
so viec/resume/thu-lai-muc-loi/bo-qua/huy an toan giua chung.

CUNG HINH DANG voi `server/bulk_import_service.py::BulkImportService`
(`ImportBatch`/`ItemStatus`, dinh danh TAT DINH tao-mot-lan, huy AN TOAN
qua truong trang thai thay vi khoa/lease, vong lap dieu phoi theo pha)
nhung KHONG dung chung code voi he thong do: he thong do gan chat voi
owner_id/novel_id va ghi `Chapter` THAT su vao kho — SAI hinh cho scraper,
noi ket qua CHI la HANG DOI DUYET (xem docstring `pipeline.py`), khong tu
ghi Novel/Chapter/audio nao ca.

PHAM VI: file nay van la tang DIEU PHOI GIUA CAC LAN GOI ('a run dang o
dau'), KHONG PHAI tang tich hop API/Appwrite — dung nguyen tac voi
`pipeline.py` va `run_state.py` (kho `MockScrapeRunStore` trong bo nho,
mock-first). Mot khu quan tri THAT poll/goi cac phuong thuc o day la mot
lop tich hop THEM, chua thuoc pham vi nay.

TINH CHAT HUY AN TOAN (quan trong nhat o file nay): `request_cancel` chi
BAT MOT CO trang thai (`CANCEL_REQUESTED`) — no KHONG tu minh dung bat ky
chuong nao dang xu ly. `drive_once` la noi DUY NHAT doc co do, va no CHI
duoc phep doc NGAY TRUOC KHI tai chuong TIEP THEO — chuong dang xu ly dot
nay (neu co) van hoan tat binh thuong, va MOI muc CHUA duoc dung toi khi
huy duoc phat hien van GIU NGUYEN trang thai `pending` (khong bi danh dau
`failed` hay `skipped` oan) de mot lan `drive_once` sau co the tiep tuc
dung cho nay.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from server.scraper.contract import SeriesInfo, canonicalize_url
from server.scraper.dedupe import source_fingerprint
from server.scraper.pipeline import IngestionDecision, StoryIngestionPipeline
from server.scraper.quality import assess_chapter_quality
from server.scraper.run_state import (
    TERMINAL_RUN_STATUSES,
    MockScrapeRunStore,
    ScrapeItemStatus,
    ScrapeRun,
    ScrapeRunItem,
    ScrapeRunStatus,
    item_id_for,
    run_fingerprint,
    run_id_from_fingerprint,
)


class ScrapeRunService:
    def __init__(self, pipeline: StoryIngestionPipeline, store: MockScrapeRunStore,
                 chapters_per_cycle: int = 5):
        self._pipeline = pipeline
        self._store = store
        self._chapters_per_cycle = max(1, int(chapters_per_cycle))
        #: `SeriesInfo` cua lan `plan_run()` gan nhat cho MOI `run_id` — can
        #: lai o `drive_once` de `normalize_chapter()` co du ngu canh (tieu
        #: de series, domain...). KHONG luu trong `ScrapeRun` (chi la cache
        #: trong tien trinh nay, khong phai du lieu ben vung cua dot scrape).
        self._series_cache: Dict[str, SeriesInfo] = {}

    # =========================================================================
    # Duong OPERATOR goi
    # =========================================================================

    def plan_run(self, url: str, *, chapter_limit: Optional[int] = None,
                 dry_run: bool = False) -> ScrapeRun:
        """
        Kham pha series + tao/tiep tuc mot `ScrapeRun` cho no.

        `dry_run=True`: goi `pipeline.plan()` va tra ve mot `ScrapeRun`
        CHUA-GHI (khong qua `store`) — dung de xem truoc so chuong con lai
        ma KHONG cam ket gi, dung hop dong dry-run cua `pipeline.py`.

        `dry_run=False`: tao dot (hoac lay dot da co qua `run_id` TAT DINH
        bam tu URL series), ghi cac muc `pending` cho tat ca chuong con lai
        (idempotent — goi lai chi THEM muc moi, khong xoa/tao trung), doi
        soat voi `ScrapeState` (xem `_reconcile_items_from_state`), roi
        chuyen PLANNING -> RUNNING. Mot dot da KET nhung con muc `pending`
        (vd vua them chuong moi qua mot lan `plan_run` sau, hoac vua duoc
        `retry_failed`) duoc HOI SINH ve RUNNING; mot dot da KET ma chi con
        muc `failed` thi KHONG tu hoi sinh — do la viec tuong minh cua
        `retry_failed`.
        """
        ke_hoach = self._pipeline.plan(url, chapter_limit=chapter_limit)
        fp = run_fingerprint(ke_hoach.series.canonical_url)
        run_id = run_id_from_fingerprint(fp)

        if dry_run:
            return ScrapeRun(
                source_url=url, fingerprint=fp, run_id=run_id,
                status=ScrapeRunStatus.PLANNING,
                series_title=ke_hoach.series.title,
                source_domain=ke_hoach.series.source_domain,
                series_author=ke_hoach.series.author or "",
                series_description=ke_hoach.series.description or "",
                estimated_total=len(ke_hoach.chapter_urls_to_process),
                already_done_count=ke_hoach.already_done_count,
                total_discovered=ke_hoach.total_discovered,
                ordering_evidence=ke_hoach.series.ordering_evidence,
            )

        self._series_cache[run_id] = ke_hoach.series

        run = self._store.create_run_once(ScrapeRun(
            source_url=url, fingerprint=fp, run_id=run_id,
            status=ScrapeRunStatus.PLANNING,
            series_title=ke_hoach.series.title,
            source_domain=ke_hoach.series.source_domain,
            series_author=ke_hoach.series.author or "",
            series_description=ke_hoach.series.description or "",
            estimated_total=len(ke_hoach.chapter_urls_to_process),
            already_done_count=ke_hoach.already_done_count,
            total_discovered=ke_hoach.total_discovered,
            ordering_evidence=ke_hoach.series.ordering_evidence,
        ))

        # `sequence` tiep tuc tu SAU `sequence` LON NHAT hien co cua dot
        # nay (khong phai luon bat dau tu 0, va KHONG PHAI dem so muc —
        # dem sai khi mot lan `plan_run` truoc do de lai khoang trong
        # trong day so, vd huy giua chung/lap ke hoach nhieu lan truoc khi
        # drive; dem se cap phat lai mot `sequence` DA DUNG, gay trung —
        # phat hien qua review Codex). `create_item_once` la idempotent
        # nen muc cu giu nguyen `sequence` cu du duoc "cap" lai o day;
        # muc moi phai noi tiep SAU max that, khong duoc trung voi muc da
        # co.
        base_sequence = self._store.max_sequence(run.run_id) + 1
        for offset, chapter_url in enumerate(ke_hoach.chapter_urls_to_process):
            fp_item = source_fingerprint(chapter_url)
            self._store.create_item_once(ScrapeRunItem(
                run_id=run.run_id, chapter_url=chapter_url,
                source_fingerprint=fp_item,
                item_id=item_id_for(run.run_id, fp_item),
                sequence=base_sequence + offset,
            ))

        self._reconcile_items_from_state(run)

        dem = self._store.count_items_by_status(run.run_id)
        con_pending = dem.get(ScrapeItemStatus.PENDING.value, 0)

        truong: Dict[str, Any] = self._truong_dem(dem)
        truong.update(
            estimated_total=sum(dem.values()),
            series_title=ke_hoach.series.title,
            source_domain=ke_hoach.series.source_domain,
            total_discovered=ke_hoach.total_discovered,
            already_done_count=ke_hoach.already_done_count,
        )

        run_hien_tai = self._store.get_run(run.run_id)
        if run_hien_tai.status in TERMINAL_RUN_STATUSES:
            if con_pending > 0:
                # Hoi sinh: co muc CHUA lam (vd chuong moi vua duoc them
                # vao/vua duoc thu lai) tren mot dot tuong da xong.
                truong.update(status=ScrapeRunStatus.RUNNING,
                              cancelled_at="", finished_at="", last_error="")
            # Con lai CHI muc `failed` (khong `pending`) -> KHONG tu hoi
            # sinh, giu nguyen trang thai KET da co.
        elif run_hien_tai.status is ScrapeRunStatus.PLANNING:
            truong["status"] = ScrapeRunStatus.RUNNING

        return self._store.save_run(run.run_id, **truong)

    def _reconcile_items_from_state(self, run: ScrapeRun) -> None:
        """
        Dong khe ho crash: neu tien trinh chet GIUA luc `state.record_success`
        da ghi xong nhung muc (`ScrapeRunItem`) TUONG UNG chua kip chuyen
        khoi `pending`, mot lan `plan_run` sau se thay muc do van `pending`
        MAI MAI (vi `resume()` da loc chuong nay ra khoi ke hoach moi — no
        "da xong" theo `ScrapeState`, nen se KHONG BAO GIO xuat hien lai
        trong `chapter_urls_to_process` de duoc drive lai).

        Vi vay o day KHONG dua vao `ke_hoach.chapter_urls_to_process` cua
        lan goi nay — quet TAT CA muc `pending` HIEN CO cua dot (co the tu
        nhung lan `plan_run` truoc), doi chieu tung muc voi `ScrapeState`
        that su cua pipeline.
        """
        state = self._pipeline.state
        muc_pending = self._store.list_items(
            run.run_id, statuses=[ScrapeItemStatus.PENDING], limit=None)
        for muc in muc_pending:
            ban_ghi = state.get(canonicalize_url(muc.chapter_url))
            if ban_ghi is not None and ban_ghi.get("status") == "ok":
                self._store.save_item(
                    muc.item_id,
                    status=ScrapeItemStatus.REVIEW_READY,
                    decision=IngestionDecision.ALREADY_IMPORTED.value,
                    content_hash=ban_ghi.get("content_hash") or "",
                    chapter_number=ban_ghi.get("chapter_number"),
                    error_message="", claimed_at="",
                )

    # =========================================================================
    # Bo DIEU PHOI (goi lap lai theo chu ky, tu ben ngoai)
    # =========================================================================

    def drive_once(self, run_id: str, *, max_chapters: Optional[int] = None
                   ) -> Dict[str, int]:
        """MOT chu ky dieu phoi cho MOT dot — tai + phan loai toi da
        `chapters_per_cycle` (hoac `max_chapters` neu nho hon) chuong dang
        `pending`, roi dong bo trang thai dot. Xem docstring module ve tinh
        chat HUY AN TOAN."""
        run = self._store.get_run(run_id)
        if run is None:
            raise ValueError(f"Không tìm thấy dot scrape: {run_id}")
        if run.is_terminal:
            # Dot da KET (vd CANCELLED/COMPLETED/PARTIAL/FAILED tu mot chu ky
            # truoc) -- goi lai `drive_once` KHONG duoc dung toi muc `pending`
            # con lai cua no (neu co, do la muc doi `retry_failed`/`plan_run`
            # hoi sinh mot cach TUONG MINH, khong phai mot chu ky drive vo tinh).
            return self._store.count_items_by_status(run_id)

        gioi_han = self._chapters_per_cycle
        if max_chapters is not None:
            gioi_han = min(gioi_han, max(1, int(max_chapters)))

        # Phase 16 ("races"): `claim_pending_items` (khong phai `list_items`
        # thuan doc) — dong khe ho hai loi goi `drive_once` DONG THOI tren
        # CUNG `run_id` doc TRUNG cung mot lo muc `pending` (tai hien duoc
        # that qua nhieu luong goi song song, xem docstring ham do).
        muc_can_lam = self._store.claim_pending_items(run_id, gioi_han)

        series = self._series_cache.get(run_id)
        if series is None:
            # Cache mat (vd `plan_run` chay o tien trinh/lan goi khac) —
            # xay lai bang chinh duong ma `pipeline.plan()` da dung.
            series = self._pipeline._provider.discover_series(run.source_url)
            self._series_cache[run_id] = series

        provider = self._pipeline._provider
        state = self._pipeline.state
        bi_huy = False

        # Ngu canh "sibling" cho `check_chapter_order` (quality.py) — LAY TU
        # TOAN BO cac muc DA XONG cua dot nay (khong chi trong chu ky hien
        # tai, khac `pipeline.py::run()` — o day co the doc lai tu store),
        # roi CONG DON THEM trong luc chay chu ky nay.
        cac_so_chuong_da_biet = [
            i.chapter_number for i in
            self._store.list_items(run_id, statuses=[ScrapeItemStatus.REVIEW_READY], limit=None)
            if i.chapter_number is not None
        ]

        for muc in muc_can_lam:
            # (1) Doc lai trang thai TRUOC KHI dung toi chuong nay — day la
            # DIEM MAU CHOT cua an toan huy: muc nay CHUA bi tai/ghi gi ca
            # neu dot da bi yeu cau huy, nen no duoc GIU NGUYEN `pending`.
            run_hien_tai = self._store.get_run(run_id)
            if run_hien_tai is not None and (
                    run_hien_tai.status is ScrapeRunStatus.CANCEL_REQUESTED):
                bi_huy = True
                break

            try:
                raw_html = provider.fetch_chapter(muc.chapter_url)
                chapter = provider.normalize_chapter(muc.chapter_url, raw_html, series)
            except Exception as exc:
                # BAT `Exception` NOI CHUNG (khong chi `FetchError`/
                # `ValueError`) — cung ly do voi `pipeline.py::run()`: mot
                # trang HTML bat thuong co the lam mot buoc phan tich noi
                # bo nem loi khong luong truoc duoc (vd
                # `content_extraction.py`, tai hien that bang
                # `RecursionError` tren HTML long ~1000 cap the truoc khi
                # sua o nguon — xem review doc lap Codex), va MOT chuong
                # loi khong duoc phep dung ca dot quet hang tram/nghin
                # chuong khac dang cho o `muc_can_lam`.
                state.record_failure(muc.chapter_url)
                self._store.save_item(
                    muc.item_id, status=ScrapeItemStatus.FAILED,
                    error_message=str(exc)[:1000], attempts=muc.attempts + 1,
                    claimed_at="")
                continue

            ban_ghi = state.record_success(
                muc.chapter_url, content_hash_value=chapter.content_hash,
                chapter_number=chapter.chapter_number)
            trung_voi: str = ""
            if ban_ghi.get("is_revision"):
                quyet_dinh = IngestionDecision.REVISION
            else:
                # Phase 8 ("POSSIBLE_DUPLICATE") — xem docstring cung ten
                # trong `pipeline.py::run()` cho ly do CHI kiem tra o day
                # (khong phai nhanh REVISION).
                danh_sach_trung = state.find_canonical_urls_by_content_hash(
                    chapter.content_hash, exclude_canonical=chapter.canonical_url)
                if danh_sach_trung:
                    quyet_dinh = IngestionDecision.POSSIBLE_DUPLICATE
                    trung_voi = danh_sach_trung[0]
                else:
                    quyet_dinh = IngestionDecision.NEW
            # Phase 6 ("khong am tham chap nhan trich xuat yeu") — CHUA
            # tung duoc goi tren duong drive_once THAT (chi co o
            # `pipeline.py::run()`, duong preview/test rieng) truoc ban sua
            # nay, nghia la TOAN BO 11 check tat dinh cua quality.py chua
            # tung chay tren MOT chuong THAT nao tung vao hang doi duyet —
            # phat hien qua review doc lap (Codex). GAN NHAN, KHONG chan
            # (giong triet ly quality.py — xem docstring o do).
            bao_cao_chat_luong = assess_chapter_quality(
                chapter, sibling_chapter_numbers=cac_so_chuong_da_biet)
            if chapter.chapter_number is not None:
                cac_so_chuong_da_biet.append(chapter.chapter_number)

            self._store.save_item(
                muc.item_id, status=ScrapeItemStatus.REVIEW_READY,
                decision=quyet_dinh.value, chapter_title=chapter.chapter_title,
                chapter_number=chapter.chapter_number,
                content_hash=chapter.content_hash, error_message="",
                duplicate_of_url=trung_voi,
                quality_passed=bao_cao_chat_luong.passed,
                quality_score=bao_cao_chat_luong.score,
                quality_warnings=" | ".join(
                    bao_cao_chat_luong.block_reasons + bao_cao_chat_luong.warn_reasons),
                claimed_at="")

        # DEM LAI CHINH XAC dung MOT LAN o cuoi chu ky — khong tin bo dem
        # cong don rai rac trong vong lap. Cung mau voi
        # `BulkImportService._drive_batch` (xem `bulk_import_service.py`).
        dem = self._store.count_items_by_status(run_id)
        con_pending = dem.get(ScrapeItemStatus.PENDING.value, 0)
        truong: Dict[str, Any] = self._truong_dem(dem)
        moc = self._store.now()

        if bi_huy:
            truong.update(status=ScrapeRunStatus.CANCELLED,
                          cancelled_at=moc, finished_at=moc)
        elif con_pending <= 0:
            trang_thai = (ScrapeRunStatus.COMPLETED
                          if dem.get(ScrapeItemStatus.FAILED.value, 0) == 0
                          else ScrapeRunStatus.PARTIAL)
            truong.update(status=trang_thai, finished_at=moc)
        else:
            truong["status"] = ScrapeRunStatus.RUNNING

        self._store.save_run(run_id, **truong)
        return dem

    # =========================================================================
    # Duong OPERATOR goi (tiep) — huy / thu lai / bo qua / xem
    # =========================================================================

    def request_cancel(self, run_id: str) -> Dict[str, Any]:
        """BAT CO huy — xem docstring module. KHONG tu dung chuong nao dang
        xu ly; `drive_once` la noi THUC THI viec dung dung luc."""
        run = self._store.get_run(run_id)
        if run is None:
            raise ValueError(f"Không tìm thấy dot scrape: {run_id}")
        if run.is_terminal:
            raise ValueError(
                "Dot scrape này đã kết thúc, không thể huỷ.")
        run = self._store.save_run(run_id, status=ScrapeRunStatus.CANCEL_REQUESTED)
        return {"run": run, "progress": run.progress()}

    def retry_failed(self, run_id: str, *, item_id: str = "") -> Dict[str, Any]:
        """
        Dua muc `failed` ve `pending` de `drive_once` thu lai — CHI muc
        `failed` (goi nham tren muc khac: co `item_id` thi loi ro, khong co
        thi im lang bo qua nhung muc khong phai `failed`). KHONG dat lai
        `attempts` — do la lich su so lan da thu, khong phai bo dem can reset.
        """
        run = self._store.get_run(run_id)
        if run is None:
            raise ValueError(f"Không tìm thấy dot scrape: {run_id}")

        if item_id:
            muc = self._store.get_item(item_id)
            if muc is None or muc.run_id != run_id:
                raise ValueError(f"Không tìm thấy mục: {item_id}")
            if muc.status is not ScrapeItemStatus.FAILED:
                raise ValueError(
                    "Mục này không ở trạng thái lỗi nên không cần thử lại.")
            self._store.save_item(item_id, status=ScrapeItemStatus.PENDING,
                                  error_message="")
            da_thu = 1
        else:
            ds = self._store.list_items(
                run_id, statuses=[ScrapeItemStatus.FAILED], limit=None)
            da_thu = 0
            for muc in ds:
                self._store.save_item(muc.item_id, status=ScrapeItemStatus.PENDING,
                                      error_message="")
                da_thu += 1

        dem = self._store.count_items_by_status(run_id)
        truong: Dict[str, Any] = self._truong_dem(dem)
        run_hien_tai = self._store.get_run(run_id)
        # CHI hoi sinh khi CA HAI dung: (1) LAN GOI NAY that su dua it nhat
        # mot muc `failed` ve `pending` (`da_thu > 0`) — thieu dieu kien
        # nay khien goi `retry_failed` tren mot dot DA HUY (khong co muc
        # failed nao) am tham HOI SINH dot do vi cac muc chua dung toi VAN
        # con `pending` theo dung tinh chat huy an toan, vo hieu quyet dinh
        # huy cua operator ngoai y muon (phat hien qua mot lan di qua luong
        # operator that: huy roi thu lai); (2) THAT SU con muc `pending`
        # LUC DOC dem (`pending > 0`) — thieu dieu kien nay bo mat mot ca
        # bien hiem nhung that: muc vua duoc thu lai o day co the da bi
        # `skip` qua mot yeu cau DONG THOI khac truoc khi dem duoc doc,
        # khien dot bi hoi sinh ve RUNNING nhung khong con viec gi de lam
        # (phat hien qua review Codex).
        if (run_hien_tai.is_terminal and da_thu > 0
                and dem.get(ScrapeItemStatus.PENDING.value, 0) > 0):
            truong.update(status=ScrapeRunStatus.RUNNING, cancelled_at="",
                          finished_at="", last_error="")
        run = self._store.save_run(run_id, **truong)
        return {"run": run, "progress": run.progress(), "retried": da_thu}

    def skip(self, run_id: str, item_id: str, *, reason: str = "") -> Dict[str, Any]:
        """Bo qua VINH VIEN mot muc — danh dau `skipped` VA ghi vao
        `ScrapeState` (`record_skip`) de mot lan `plan_run` sau tren CUNG
        series khong dua chuong nay tro lai qua `resume()`."""
        run = self._store.get_run(run_id)
        if run is None:
            raise ValueError(f"Không tìm thấy dot scrape: {run_id}")
        muc = self._store.get_item(item_id)
        if muc is None or muc.run_id != run_id:
            raise ValueError(f"Không tìm thấy mục: {item_id}")

        self._store.save_item(item_id, status=ScrapeItemStatus.SKIPPED,
                              skipped_reason=reason)
        self._pipeline.state.record_skip(muc.chapter_url)

        dem = self._store.count_items_by_status(run_id)
        run = self._store.save_run(run_id, **self._truong_dem(dem))
        return {"run": run, "progress": run.progress()}

    def list_runs(self, *, statuses=None):
        """Chuyen tiep MONG toi `store.list_runs` — dung cho trang danh
        sach dot scrape cua UI quan tri. KHONG tac dung phu."""
        return self._store.list_runs(statuses=statuses)

    def run_view(self, run_id: str, *, limit: int = 50, offset: int = 0,
                status: str = "") -> Dict[str, Any]:
        """Doc TIEN DO + danh sach muc cua mot dot — KHONG tac dung phu,
        dung cho mot giao dien UI poll sau nay."""
        run = self._store.get_run(run_id)
        if run is None:
            raise ValueError(f"Không tìm thấy dot scrape: {run_id}")
        loc = None
        if status:
            try:
                loc = [ScrapeItemStatus(status)]
            except ValueError as exc:
                raise ValueError(
                    f"Trạng thái '{status}' không hợp lệ. Chấp nhận: "
                    + ", ".join(s.value for s in ScrapeItemStatus)) from exc
        items = self._store.list_items(
            run_id, statuses=loc, limit=max(1, min(limit, 500)),
            offset=max(0, offset))
        return {"run": run, "items": items, "progress": run.progress()}

    # -- bo dem ------------------------------------------------------------

    @staticmethod
    def _truong_dem(dem: Dict[str, int]) -> Dict[str, int]:
        return {
            "count_pending": max(0, dem.get(ScrapeItemStatus.PENDING.value, 0)),
            "count_review_ready": max(
                0, dem.get(ScrapeItemStatus.REVIEW_READY.value, 0)),
            "count_failed": max(0, dem.get(ScrapeItemStatus.FAILED.value, 0)),
            "count_skipped": max(0, dem.get(ScrapeItemStatus.SKIPPED.value, 0)),
        }
