"""
Hinh dang du lieu + kho luu tru TRONG BO NHO cho MOT dot scrape hang loat
(`ScrapeRunService` o `server/scraper/bulk.py` la tang dieu phoi dung cac
kieu nay).

CUNG MAU voi `server/bulk_import_domain.py` (`ImportBatch`/`ItemStatus`,
dinh danh TAT DINH, tao-mot-lan idempotent) nhung KHONG dung chung code:
he thong do gan chat voi owner_id/novel_id va viec ghi `Chapter` that —
sai hinh cho scraper, noi ket qua CHI la hang doi duyet (xem
`server/scraper/pipeline.py`), khong tu ghi Novel/Chapter nao ca.

DINH DANH TAT DINH: `run_id` bam tu CANONICAL URL cua series — KHONG bam
tu `chapter_limit` hay danh sach chuong. Nho vay mot lan chay canary
(`chapter_limit=10`) va mot lan chay day du sau nay cua CUNG series chia
se CUNG `run_id`: goi `plan_run()` lai chi THEM muc, khong bao gio xoa hay
tao mot dot moi.

CO Y BO SOT: `ScrapeRunItem` KHONG luu `clean_text`/noi dung day du cua
chuong — noi dung do CHI ton tai trong `IngestionResult.review_items`
(tra ve TRONG BO NHO cua tung lan goi `pipeline.run()`), khong bao gio
duoc chep vao day. O quy mo 500 chuong, giu ca noi dung trong mot dict
song suot doi tien trinh la mot lo lang phi bo nho khong can thiet — kho
nay chi giu METADATA de theo doi tien do/trang thai.
"""
from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence

from server.scraper.contract import canonicalize_url


class ScrapeRunStatus(str, Enum):
    PLANNING = "planning"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


#: Dot o cac trang thai nay KHONG con duoc `drive_once` nhan them viec.
TERMINAL_RUN_STATUSES = frozenset({
    ScrapeRunStatus.CANCELLED, ScrapeRunStatus.COMPLETED,
    ScrapeRunStatus.PARTIAL, ScrapeRunStatus.FAILED,
})


class ScrapeItemStatus(str, Enum):
    PENDING = "pending"
    REVIEW_READY = "review_ready"
    FAILED = "failed"
    SKIPPED = "skipped"


# -----------------------------------------------------------------------------
# Dinh danh tat dinh
# -----------------------------------------------------------------------------


def run_fingerprint(series_canonical_url: str) -> str:
    """sha256 cua canonical_url cua SERIES — CUNG triet ly voi
    `dedupe.source_fingerprint`, nhung o cap SERIES chu khong phai cap
    chuong. Danh tinh cua mot dot scrape la VI TRI series, khong phai
    tham so cua lan goi (`chapter_limit`)."""
    return hashlib.sha256(
        canonicalize_url(series_canonical_url).encode("utf-8")).hexdigest()


def run_id_from_fingerprint(fp: str) -> str:
    return "scr_" + fp[:16]


def item_id_for(run_id: str, source_fingerprint: str) -> str:
    return f"{run_id}-{source_fingerprint[:15]}"


# -----------------------------------------------------------------------------
# Thuc the
# -----------------------------------------------------------------------------


@dataclass
class ScrapeRun:
    source_url: str
    fingerprint: str
    run_id: str = ""
    status: ScrapeRunStatus = ScrapeRunStatus.PLANNING
    series_title: str = ""
    source_domain: str = ""
    #: So chuong SE xu ly TINH DEN LAN plan() gan nhat — dan xuat tu
    #: `IngestionPlan.chapter_urls_to_process`, cap nhat lai moi lan
    #: `plan_run()` (co the TANG neu mot lan goi sau them chuong moi).
    estimated_total: int = 0
    already_done_count: int = 0
    total_discovered: int = 0
    count_pending: int = 0
    count_review_ready: int = 0
    count_failed: int = 0
    count_skipped: int = 0
    last_error: str = ""
    created_at: str = ""
    updated_at: str = ""
    cancelled_at: str = ""
    finished_at: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_RUN_STATUSES

    def progress(self) -> Dict[str, Any]:
        """Bang tien do CONG DON cho giao dien poll — mau so la
        `estimated_total` (uoc luong tai thoi diem `plan()` gan nhat)."""
        da_xong = self.count_review_ready + self.count_failed + self.count_skipped
        return {
            "estimated_total": self.estimated_total,
            "already_done_count": self.already_done_count,
            "total_discovered": self.total_discovered,
            "pending": self.count_pending,
            "review_ready": self.count_review_ready,
            "failed": self.count_failed,
            "skipped": self.count_skipped,
            "done": da_xong,
            "percent": (round(100 * da_xong / self.estimated_total)
                        if self.estimated_total else 0),
        }


@dataclass
class ScrapeRunItem:
    run_id: str
    chapter_url: str
    source_fingerprint: str
    item_id: str = ""
    status: ScrapeItemStatus = ScrapeItemStatus.PENDING
    #: `IngestionDecision.value` mot khi da phan loai (xem `pipeline.py`).
    decision: str = ""
    chapter_title: str = ""
    chapter_number: Optional[int] = None
    content_hash: str = ""
    error_message: str = ""
    attempts: int = 0
    skipped_reason: str = ""
    #: Vi tri THEO THU TU KHAM PHA (0, 1, 2, ...) — dat MOT LAN luc tao,
    #: KHONG BAO GIO doi. Day la THU TU HANG DOI DUYET, tach biet voi
    #: `chapter_number` (co the None cho chuong khong doc duoc so tu tieu
    #: de, vd "Prologue" — xem generic_index_adapter.py, va du sao cung chi
    #: co GIA TRI sau khi da drive, khong dung duoc de sap xep muc con
    #: `pending`). Cung triet ly voi `item_index` cua
    #: `bulk_import_domain.ImportItem` — phat hien can co truong nay qua
    #: mot lan di qua luong operator that: sap theo `created_at` bi trung
    #: gio (do phan giai thoi gian) roi lui ve sap theo `item_id` (mot ma
    #: bam, khong lien quan thu tu that), lam hang doi duyet hien SAI thu
    #: tu chuong.
    sequence: int = 0
    created_at: str = ""
    updated_at: str = ""


# -----------------------------------------------------------------------------
# Kho luu tru TRONG BO NHO
# -----------------------------------------------------------------------------


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MockScrapeRunStore:
    """Kho TRONG BO NHO, khong Appwrite — CUNG MAU voi
    `server/bulk_import_store.py::MockBulkImportStore` (khoa `RLock` bao
    quanh dict, tao-hoac-lay idempotent theo id TAT DINH).

    `now_fn` duoc tiem vao (mac dinh gio UTC that) de bo test kiem soat
    duoc thoi gian — CUNG nguyen tac voi `HttpFetcher.__init__` (tham so
    `sleep_fn`/`clock_fn`) o `server/scraper/http_fetcher.py`.
    """

    def __init__(self, now_fn: Callable[[], str] = _now_utc_iso) -> None:
        self._lock = threading.RLock()
        self._now = now_fn
        self.runs: Dict[str, ScrapeRun] = {}
        self.items: Dict[str, ScrapeRunItem] = {}

    def now(self) -> str:
        """Moc thoi gian HIEN TAI theo `now_fn` da tiem — dung cho tang
        dieu phoi (`bulk.py`) can dong dau `cancelled_at`/`finished_at`
        CUNG mot nguon thoi gian voi kho nay (de bo test kiem soat duoc)."""
        return self._now()

    # -- dot -------------------------------------------------------------------

    def create_run_once(self, run: ScrapeRun) -> ScrapeRun:
        """Tao-hoac-lay AN TOAN theo `run.run_id` TAT DINH — neu da co, tra
        ve ban HIEN CO KHONG DOI (khong ghi de), giong het
        `MockBulkImportStore.create_batch_once`."""
        with self._lock:
            hien_co = self.runs.get(run.run_id)
            if hien_co is not None:
                return hien_co
            moc = self._now()
            if not run.created_at:
                run.created_at = moc
            if not run.updated_at:
                run.updated_at = moc
            self.runs[run.run_id] = run
            return run

    def get_run(self, run_id: str) -> Optional[ScrapeRun]:
        return self.runs.get(run_id)

    def save_run(self, run_id: str, **fields: Any) -> ScrapeRun:
        with self._lock:
            hien_tai = self.runs.get(run_id)
            if hien_tai is None:
                raise ValueError(f"Không tìm thấy dot scrape: {run_id}")
            fields.setdefault("updated_at", self._now())
            moi = replace(hien_tai, **fields)
            self.runs[run_id] = moi
            return moi

    def list_runs(self, *, statuses: Optional[Sequence[ScrapeRunStatus]] = None
                 ) -> List[ScrapeRun]:
        with self._lock:
            ds = list(self.runs.values())
        if statuses:
            can = {ScrapeRunStatus(s) for s in statuses}
            ds = [r for r in ds if r.status in can]
        ds.sort(key=lambda r: r.created_at, reverse=True)
        return ds

    # -- muc -------------------------------------------------------------------

    def create_item_once(self, item: ScrapeRunItem) -> ScrapeRunItem:
        with self._lock:
            hien_co = self.items.get(item.item_id)
            if hien_co is not None:
                return hien_co
            moc = self._now()
            if not item.created_at:
                item.created_at = moc
            if not item.updated_at:
                item.updated_at = moc
            self.items[item.item_id] = item
            return item

    def get_item(self, item_id: str) -> Optional[ScrapeRunItem]:
        return self.items.get(item_id)

    def save_item(self, item_id: str, **fields: Any) -> ScrapeRunItem:
        with self._lock:
            hien_tai = self.items.get(item_id)
            if hien_tai is None:
                raise ValueError(f"Không tìm thấy mục: {item_id}")
            fields.setdefault("updated_at", self._now())
            moi = replace(hien_tai, **fields)
            self.items[item_id] = moi
            return moi

    def list_items(self, run_id: str, *,
                   statuses: Optional[Sequence[ScrapeItemStatus]] = None,
                   limit: Optional[int] = 50, offset: int = 0
                  ) -> List[ScrapeRunItem]:
        with self._lock:
            ds = [i for i in self.items.values() if i.run_id == run_id]
        if statuses:
            can = {ScrapeItemStatus(s) for s in statuses}
            ds = [i for i in ds if i.status in can]
        # Thu tu KHAM PHA (`sequence`, xem dataclass) — KHONG dung
        # `created_at`: tung bi trung gio o quy mo tao nhanh (Mock hay ca
        # Appwrite that), lam hang doi duyet hien SAI thu tu chuong khi lui
        # ve `item_id` (ma bam, khong lien quan thu tu that).
        ds.sort(key=lambda i: (i.sequence, i.item_id))
        if offset:
            ds = ds[offset:]
        if limit is not None:
            ds = ds[:limit]
        return ds

    def max_sequence(self, run_id: str) -> int:
        """`sequence` LON NHAT hien co cua dot nay, `-1` neu chua co muc
        nao — dung de cap phat `sequence` TIEP THEO khong trung, xem
        `bulk.py::plan_run`. PHAI la max THAT, khong phai dem so muc: dem
        so muc bi sai khi mot lan `plan_run` truoc do de lai khoang trong
        trong day so (vd huy giua chung/lap ke hoach nhieu lan truoc khi
        drive) — phat hien qua review Codex."""
        with self._lock:
            gia_tri = [i.sequence for i in self.items.values() if i.run_id == run_id]
        return max(gia_tri) if gia_tri else -1

    def count_items_by_status(self, run_id: str) -> Dict[str, int]:
        ra = {s.value: 0 for s in ScrapeItemStatus}
        with self._lock:
            for item in self.items.values():
                if item.run_id == run_id:
                    ra[item.status.value] = ra.get(item.status.value, 0) + 1
        return ra
