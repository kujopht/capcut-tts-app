"""
Kho dieu phoi dot scrape hang loat ben vung tren Appwrite.

Cung giao dien voi `MockScrapeRunStore` (`server/scraper/run_state.py`) —
`ScrapeRunService` (`server/scraper/bulk.py`) KHONG biet dang chay tren kho
nao. Cung mau voi `appwrite_bulk_import_store.py`/`appwrite_trusted_source_store.py`.

HAI collection RIENG: `scrape_runs`, `scrape_run_items` — da khai bao trong
`scripts/setup_appwrite.py`.

BON diem phai giu dung:

  1. `_writable` doi chuoi RONG cua thuoc tinh `datetime` thanh `None` — xem
     `appwrite_bulk_import_store.py::_DATETIME_FIELDS` cho su co da xac
     nhan (Appwrite tu dien GIO HIEN TAI cho `""`).

  2. `chapter_number` la `Optional[int]` THAT SU — `None` (chuong khong
     doc duoc so) khac `0`. Dung `_int_or_none`, KHONG dung ham ep-ve-0
     kieu `appwrite_bulk_import_store._int`.

  3. `item_id` DUNG 36 ky tu — dung TRAN `$id` cua Appwrite. `create_item_once`
     tra ve THAM SO DAU VAO (khong GET lai) khi gap 409: `bulk.py` khong
     bao gio dung gia tri tra ve cua loi goi nay (chi tao roi bo qua), nen
     bo GET thua o day AN TOAN va tiet kiem mot luot doc moi muc trong lo
     500 chuong lap lai `plan_run`.

  4. `save_run`/`save_item` doc TRUC TIEP tu than PATCH response (da la
     document day du sau cap nhat), KHONG GET lai — giam mot nua so luot
     goi tren duong ghi nong nhat (`drive_once` goi ca hai lien tuc).
"""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence

import httpx

from server.adapters import AppwriteUnavailableError, NotFoundError
from server.config import AppwriteSettings
from server.scraper.run_state import (
    ScrapeItemStatus,
    ScrapeRun,
    ScrapeRunItem,
    ScrapeRunStatus,
    _now_utc_iso,
)
from server.secret_redaction import thong_diep_loi_an_toan

COL_RUNS = "scrape_runs"
COL_ITEMS = "scrape_run_items"


class _ConflictError(Exception):
    """RIENG cho `create_*_once` — Appwrite tra 409 (trung `documentId`) —
    khac voi `NotFoundError` (404, ban ghi khong ton tai) va
    `AppwriteUnavailableError` (moi loi >=400 khac, that su can lo ra)."""

#: Phai khop CHINH XAC schema trong `scripts/setup_appwrite.py`.
PERSISTED_FIELDS: Dict[str, tuple] = {
    COL_RUNS: (
        "run_id", "source_url", "fingerprint", "status", "series_title",
        "source_domain", "estimated_total", "already_done_count",
        "total_discovered", "count_pending", "count_review_ready",
        "count_failed", "count_skipped", "last_error", "ordering_evidence",
        "created_at", "updated_at", "cancelled_at", "finished_at",
    ),
    COL_ITEMS: (
        "item_id", "run_id", "chapter_url", "source_fingerprint", "status",
        "decision", "chapter_title", "chapter_number", "content_hash",
        "error_message", "attempts", "skipped_reason", "sequence",
        "created_at", "updated_at",
    ),
}

#: Thuoc tinh kieu `datetime` KHONG BAT BUOC — xem diem 1 o docstring dau tep.
_DATETIME_FIELDS: Dict[str, tuple] = {
    COL_RUNS: ("cancelled_at", "finished_at"),
    COL_ITEMS: (),
}

REQUEST_TIMEOUT = 15.0
PAGE_SIZE = 100


def q_equal(attribute: str, *values: Any) -> str:
    return json.dumps({"method": "equal", "attribute": attribute,
                       "values": list(values)})


def q_order_asc(attribute: str) -> str:
    return json.dumps({"method": "orderAsc", "attribute": attribute})


def q_order_desc(attribute: str) -> str:
    return json.dumps({"method": "orderDesc", "attribute": attribute})


def q_limit(count: int) -> str:
    return json.dumps({"method": "limit", "values": [int(count)]})


def q_offset(count: int) -> str:
    return json.dumps({"method": "offset", "values": [int(count)]})


def _int(value: Any, mac_dinh: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return mac_dinh


def _int_or_none(value: Any) -> Optional[int]:
    """Khac `_int`: giu `None` la `None` — xem diem 2 o docstring dau tep."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _run_from_doc(doc: Dict[str, Any]) -> ScrapeRun:
    return ScrapeRun(
        source_url=str(doc.get("source_url") or ""),
        fingerprint=str(doc.get("fingerprint") or ""),
        run_id=str(doc.get("run_id") or doc.get("$id") or ""),
        status=ScrapeRunStatus(doc.get("status") or ScrapeRunStatus.PLANNING.value),
        series_title=str(doc.get("series_title") or ""),
        source_domain=str(doc.get("source_domain") or ""),
        estimated_total=_int(doc.get("estimated_total")),
        already_done_count=_int(doc.get("already_done_count")),
        total_discovered=_int(doc.get("total_discovered")),
        count_pending=_int(doc.get("count_pending")),
        count_review_ready=_int(doc.get("count_review_ready")),
        count_failed=_int(doc.get("count_failed")),
        count_skipped=_int(doc.get("count_skipped")),
        last_error=str(doc.get("last_error") or ""),
        ordering_evidence=str(doc.get("ordering_evidence") or ""),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
        cancelled_at=str(doc.get("cancelled_at") or ""),
        finished_at=str(doc.get("finished_at") or ""),
    )


def _item_from_doc(doc: Dict[str, Any]) -> ScrapeRunItem:
    return ScrapeRunItem(
        run_id=str(doc.get("run_id") or ""),
        chapter_url=str(doc.get("chapter_url") or ""),
        source_fingerprint=str(doc.get("source_fingerprint") or ""),
        item_id=str(doc.get("item_id") or doc.get("$id") or ""),
        status=ScrapeItemStatus(doc.get("status") or ScrapeItemStatus.PENDING.value),
        decision=str(doc.get("decision") or ""),
        chapter_title=str(doc.get("chapter_title") or ""),
        chapter_number=_int_or_none(doc.get("chapter_number")),
        content_hash=str(doc.get("content_hash") or ""),
        error_message=str(doc.get("error_message") or ""),
        attempts=_int(doc.get("attempts")),
        skipped_reason=str(doc.get("skipped_reason") or ""),
        sequence=_int(doc.get("sequence")),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
    )


def _run_to_data(run: ScrapeRun) -> Dict[str, Any]:
    data = {f: getattr(run, f) for f in PERSISTED_FIELDS[COL_RUNS] if f != "status"}
    data["status"] = run.status.value
    return data


def _item_to_data(item: ScrapeRunItem) -> Dict[str, Any]:
    data = {f: getattr(item, f) for f in PERSISTED_FIELDS[COL_ITEMS] if f != "status"}
    data["status"] = item.status.value
    return data


class AppwriteScrapeRunStore:
    mode = "appwrite"

    def __init__(self, settings: AppwriteSettings, client: Any = None,
                 now_fn=_now_utc_iso):
        from server.appwrite_adapter import AppwriteConfigError

        if not settings.configured:
            raise AppwriteConfigError(
                "Cấu hình Appwrite chưa đủ cho kho quét hàng loạt. Cần cả "
                "bốn biến APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, "
                "APPWRITE_API_KEY, APPWRITE_DATABASE_ID.")
        self._settings = settings
        self._endpoint = settings.api_base
        self._db = settings.database_id
        self._client = client
        self._now = now_fn
        self._attrs_cache: Dict[str, set] = {}
        self._pool: Optional[httpx.Client] = None
        self._lock = threading.RLock()

    def now(self) -> str:
        return self._now()

    # -- ha tang REST — giong het AppwriteBulkImportStore ---------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Appwrite-Project": self._settings.project_id,
            "X-Appwrite-Key": self._settings.api_key,
        }

    def _http(self) -> httpx.Client:
        if self._pool is None:
            self._pool = httpx.Client(timeout=REQUEST_TIMEOUT)
        return self._pool

    def _call(self, method: str, path: str, *, payload: Optional[Dict] = None,
              params: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self._endpoint}{path}"
        if self._client is not None:
            return self._client.request(method, url, json=payload, params=params,
                                        headers=self._headers())
        try:
            response = self._http().request(method, url, json=payload,
                                            params=params, headers=self._headers())
        except httpx.HTTPError as exc:
            # PHAI la `AppwriteUnavailableError`, KHONG phai `NotFoundError`
            # — xem docstring `appwrite_bulk_import_store.py::_call` cho su
            # co da vap: mot loi TRANSPORT bi hieu nham thanh "da co ban ghi
            # nay roi" se lam `create_run_once` tra ve "da co dot nay" trong
            # khi chua he ghi duoc gi.
            raise AppwriteUnavailableError(
                f"Không kết nối được Appwrite: {exc}") from exc
        if response.status_code == 404:
            raise NotFoundError("Không tìm thấy bản ghi.")
        if response.status_code == 409:
            # RIENG cho `create_*_once` — "da co ban ghi nay" that su, KHAC
            # voi moi loi >=400 khac (xem nhanh duoi day). Doc review that
            # tu Codex: gop chung ca hai truoc day lam 401/loi xac thuc/5xx
            # bi HIEU NHAM thanh "da ton tai", `create_run_once` im lang
            # tra ve mot ban ghi KHONG co that thay vi bao loi that.
            raise _ConflictError("Đã tồn tại bản ghi này.")
        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = None
            # KHONG PHAI `NotFoundError` — mot loi 401/400/5xx that su phai
            # LO RA, khong duoc `get_run`/`get_item` nuot thanh `None` (doc
            # thanh "khong ton tai" trong khi that ra Appwrite dang loi).
            raise AppwriteUnavailableError(
                thong_diep_loi_an_toan(body, status_code=response.status_code))
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def _docs(self, collection: str) -> str:
        return f"/v1/databases/{self._db}/collections/{collection}/documents"

    def _supported_fields(self, collection: str) -> Optional[set]:
        with self._lock:
            cached = self._attrs_cache.get(collection)
        if cached is not None:
            return cached or None
        try:
            meta = self._call(
                "GET", f"/v1/databases/{self._db}/collections/{collection}")
        except Exception:
            return None
        names = {a.get("key") for a in (meta.get("attributes") or [])
                 if a.get("key")}
        with self._lock:
            self._attrs_cache[collection] = names
        return names or None

    def _writable(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        allowed = PERSISTED_FIELDS.get(collection)
        fields = ({k: v for k, v in data.items() if k in allowed}
                  if allowed is not None else dict(data))
        for ten in _DATETIME_FIELDS.get(collection, ()):
            if fields.get(ten) == "":
                fields[ten] = None
        available = self._supported_fields(collection)
        if available is None:
            return fields
        return {k: v for k, v in fields.items() if k in available}

    def _create(self, collection: str, doc_id: str,
               data: Dict[str, Any]) -> Dict[str, Any]:
        return self._call("POST", self._docs(collection), payload={
            "documentId": doc_id,
            "data": self._writable(collection, data),
            # KHONG quyen doc cong khai — trang thai dieu phoi noi bo, khong
            # phai noi dung cong bo.
            "permissions": [],
        })

    def _get(self, collection: str, doc_id: str) -> Dict[str, Any]:
        return self._call("GET", f"{self._docs(collection)}/{doc_id}")

    def _update(self, collection: str, doc_id: str,
               data: Dict[str, Any]) -> Dict[str, Any]:
        return self._call("PATCH", f"{self._docs(collection)}/{doc_id}",
                          payload={"data": self._writable(collection, data)})

    def _page(self, collection: str, queries: List[str]) -> List[Dict[str, Any]]:
        data = self._call("GET", self._docs(collection),
                          params={"queries[]": queries})
        return list(data.get("documents") or [])

    def _count(self, collection: str, queries: List[str]) -> int:
        data = self._call("GET", self._docs(collection),
                          params={"queries[]": queries + [q_limit(1)]})
        return int(data.get("total") or 0)

    def _list_all(self, collection: str, queries: List[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        offset = 0
        while True:
            page = self._page(collection, queries + [
                q_limit(PAGE_SIZE), q_offset(offset)])
            out.extend(page)
            if len(page) < PAGE_SIZE:
                return out
            offset += PAGE_SIZE

    # -- dot --------------------------------------------------------------

    def create_run_once(self, run: ScrapeRun) -> ScrapeRun:
        """Tao-hoac-lay AN TOAN theo `run.run_id` TAT DINH — Appwrite tu
        choi `POST` trung `documentId` (409, boc thanh `_ConflictError`), nen
        day la compare-and-set that su."""
        moc = run.created_at or self._now()
        data = _run_to_data(replace(run, created_at=moc,
                                    updated_at=run.updated_at or moc))
        try:
            self._create(COL_RUNS, run.run_id, data)
            return _run_from_doc({**data, "run_id": run.run_id})
        except _ConflictError:
            return _run_from_doc(self._get(COL_RUNS, run.run_id))

    def get_run(self, run_id: str) -> Optional[ScrapeRun]:
        try:
            return _run_from_doc(self._get(COL_RUNS, run_id))
        except NotFoundError:
            return None

    def save_run(self, run_id: str, **fields: Any) -> ScrapeRun:
        if "status" in fields and isinstance(fields["status"], ScrapeRunStatus):
            fields["status"] = fields["status"].value
        fields.setdefault("updated_at", self._now())
        doc = self._update(COL_RUNS, run_id, fields)
        return _run_from_doc(doc)

    def list_runs(self, *, statuses: Optional[Sequence[ScrapeRunStatus]] = None
                 ) -> List[ScrapeRun]:
        queries: List[str] = []
        if statuses:
            queries.append(q_equal("status", *[ScrapeRunStatus(s).value
                                               for s in statuses]))
        queries.append(q_order_desc("created_at"))
        docs = self._list_all(COL_RUNS, queries)
        return [_run_from_doc(d) for d in docs]

    # -- muc ----------------------------------------------------------------

    def create_item_once(self, item: ScrapeRunItem) -> ScrapeRunItem:
        moc = item.created_at or self._now()
        data = _item_to_data(replace(item, created_at=moc,
                                     updated_at=item.updated_at or moc))
        try:
            self._create(COL_ITEMS, item.item_id, data)
            return _item_from_doc({**data, "item_id": item.item_id})
        except _ConflictError:
            # Xem diem 3 o docstring dau tep: `bulk.py` khong dung gia tri
            # tra ve o nhanh nay, nen bo GET lai la an toan va re hon.
            return item

    def get_item(self, item_id: str) -> Optional[ScrapeRunItem]:
        try:
            return _item_from_doc(self._get(COL_ITEMS, item_id))
        except NotFoundError:
            return None

    def save_item(self, item_id: str, **fields: Any) -> ScrapeRunItem:
        if "status" in fields and isinstance(fields["status"], ScrapeItemStatus):
            fields["status"] = fields["status"].value
        fields.setdefault("updated_at", self._now())
        doc = self._update(COL_ITEMS, item_id, fields)
        return _item_from_doc(doc)

    def list_items(self, run_id: str, *,
                   statuses: Optional[Sequence[ScrapeItemStatus]] = None,
                   limit: Optional[int] = 50, offset: int = 0
                  ) -> List[ScrapeRunItem]:
        queries: List[str] = [q_equal("run_id", run_id)]
        if statuses:
            queries.append(q_equal("status", *[ScrapeItemStatus(s).value
                                               for s in statuses]))
        # `sequence`, KHONG PHAI `created_at` — xem docstring `sequence`
        # trong `run_state.ScrapeRunItem` cho ly do (trung gio o quy mo tao
        # nhanh lam sai thu tu hien thi cho operator).
        queries.append(q_order_asc("sequence"))
        if limit is None:
            docs = self._list_all(COL_ITEMS, queries)
            if offset:
                docs = docs[offset:]
        else:
            docs = self._page(COL_ITEMS, queries + [
                q_limit(max(1, min(limit, 500))), q_offset(max(0, offset))])
        return [_item_from_doc(d) for d in docs]

    def count_items_by_status(self, run_id: str) -> Dict[str, int]:
        """BON truy van bi chan (`limit=1`, doc `total`) — MOT truy van moi
        trang thai, khong keo toan bo muc ve dem o may khach (co the toi
        500 muc/dot). Xem khuyen nghi cua ban ke hoach Opus."""
        return {
            s.value: self._count(COL_ITEMS, [
                q_equal("run_id", run_id), q_equal("status", s.value)])
            for s in ScrapeItemStatus
        }

    def max_sequence(self, run_id: str) -> int:
        """`sequence` LON NHAT hien co — MOT truy van re (`orderDesc` +
        `limit(1)`), KHONG keo toan bo muc ve chi de lay max. Dung de cap
        phat `sequence` tiep theo khong trung, xem `bulk.py::plan_run`.
        `-1` neu dot chua co muc nao."""
        docs = self._page(COL_ITEMS, [
            q_equal("run_id", run_id), q_order_desc("sequence"), q_limit(1)])
        return int(docs[0].get("sequence") or 0) if docs else -1


def build_scrape_run_store(settings: Any):
    """Chon kho theo `DATA_BACKEND` — cung mau voi `build_bulk_import_store`.

    KHONG bat `AppwriteConfigError`: `DATA_BACKEND=appwrite` ma thieu bien
    cau hinh PHAI CHET NGAY luc khoi dong, khong am tham lui ve bo nho (mot
    dot quet 500 chuong "dang chay" trong RAM la thu bien mat lang le nhat
    co the — cung ly do voi nhap chuong hang loat)."""
    from server.scraper.run_state import MockScrapeRunStore

    if getattr(settings, "data_backend", "mock") == "appwrite":
        return AppwriteScrapeRunStore(settings.appwrite)
    return MockScrapeRunStore()
