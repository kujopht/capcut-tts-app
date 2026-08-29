"""
Kho nhap chuong hang loat ben vung tren Appwrite.

Cung giao dien voi `MockBulkImportStore` (`server/bulk_import_store.py`) — cac
route trong `server/main.py` va bo dieu phoi trong
`server/bulk_import_service.py` KHONG biet dang chay tren kho nao. Cung mau voi
`appwrite_animation_store.py` / `appwrite_trusted_source_store.py`.

HAI collection RIENG: `chapter_import_batches`, `chapter_import_items` — da khai
bao trong `scripts/setup_appwrite.py`.

BA diem phai giu dung, va ca ba deu tung lam vo mot tinh nang khac o kho nay:

  1. `_writable` doi chuoi RONG cua thuoc tinh `datetime` thanh `None`. Appwrite
     tu dien GIO HIEN TAI khi nhan `""` cho mot datetime khong bat buoc — da xac
     nhan that, xem `appwrite_trusted_source_store.py::_DATETIME_FIELDS`. Khong
     lam vay thi moi lo MOI trong nhu da huy va da ket thuc ngay luc tao.

  2. Doc theo TRANG. Appwrite mac dinh tra 25 document; mot lo 500 chuong doc
     bang `_list` tran se AM THAM chi thay 25 muc dau.

  3. Duong doc cua API `select` BO cot `content`. Mot lan poll bang tien do
     khong duoc keo ve vai MB van ban.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx

from server.adapters import AppwriteUnavailableError, NotFoundError, raise_for_appwrite_404
from server.bulk_import_domain import (
    BatchStatus,
    ImportBatch,
    ImportItem,
    ItemStatus,
    batch_status_from,
    item_status_from,
)
from server.bulk_import_store import BATCH_EDITABLE, ITEM_EDITABLE
from server.config import AppwriteSettings
from server.domain import now_iso
from server.secret_redaction import thong_diep_loi_an_toan

COL_BATCHES = "chapter_import_batches"
COL_ITEMS = "chapter_import_items"

#: Phai khop CHINH XAC schema trong `scripts/setup_appwrite.py` — bo test hop
#: dong `server/tests/test_bulk_import_schema_contract.py` so sanh hai tap nay.
#:
#: Ghi chu nay TRUOC DAY chi sang `test_bulk_chapter_import.py`, va do la mot
#: loi: tep do khong he nhac toi `PERSISTED_FIELDS`, con
#: `test_appwrite_schema_contract.py` chi phu bon collection novels/chapters/
#: tts_jobs/audio_tracks. Nghia la hai collection nay tung KHONG co luoi nao —
#: chung khop duoc la nho ky luat, khong nho kiem chung. Them mot truong o day
#: ma quen khai trong SCHEMA se lam Appwrite tu choi CA ban ghi bang HTTP 400,
#: va chi lo ra tren moi truong THAT vi store gia trong test nhan moi truong.
PERSISTED_FIELDS: Dict[str, tuple] = {
    COL_BATCHES: (
        "batch_id", "owner_id", "novel_id", "fingerprint", "total_items",
        "status", "voice_id", "rate", "chunk_chars", "order_base",
        "source_name", "count_pending", "count_chapter_created",
        "count_job_queued", "count_completed", "count_failed", "last_error",
        "created_at", "updated_at", "cancelled_at", "finished_at",
    ),
    COL_ITEMS: (
        "item_id", "batch_id", "owner_id", "novel_id", "item_index", "title",
        "content", "content_hash", "char_count", "status", "chapter_id",
        "job_id", "error_message", "attempts", "created_at", "updated_at",
    ),
}

#: Thuoc tinh kieu `datetime` KHONG BAT BUOC — xem diem 1 o docstring dau tep.
_DATETIME_FIELDS: Dict[str, tuple] = {
    COL_BATCHES: ("cancelled_at", "finished_at"),
    COL_ITEMS: (),
}

#: Cac cot cua MUC tru `content` — dung cho duong doc cua API.
_ITEM_FIELDS_NO_CONTENT: Tuple[str, ...] = tuple(
    f for f in PERSISTED_FIELDS[COL_ITEMS] if f != "content")

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


def q_select(*attributes: str) -> str:
    return json.dumps({"method": "select", "values": list(attributes)})


def _int(value: Any, mac_dinh: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return mac_dinh


def _batch_from_doc(doc: Dict[str, Any]) -> ImportBatch:
    return ImportBatch(
        batch_id=str(doc.get("batch_id") or doc.get("$id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        novel_id=str(doc.get("novel_id") or ""),
        fingerprint=str(doc.get("fingerprint") or ""),
        total_items=_int(doc.get("total_items")),
        status=batch_status_from(doc.get("status")),
        voice_id=str(doc.get("voice_id") or ""),
        rate=str(doc.get("rate") or "1.0"),
        chunk_chars=_int(doc.get("chunk_chars"), 2000),
        order_base=_int(doc.get("order_base")),
        source_name=str(doc.get("source_name") or ""),
        count_pending=_int(doc.get("count_pending")),
        count_chapter_created=_int(doc.get("count_chapter_created")),
        count_job_queued=_int(doc.get("count_job_queued")),
        count_completed=_int(doc.get("count_completed")),
        count_failed=_int(doc.get("count_failed")),
        last_error=str(doc.get("last_error") or ""),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
        cancelled_at=str(doc.get("cancelled_at") or ""),
        finished_at=str(doc.get("finished_at") or ""),
    )


def _item_from_doc(doc: Dict[str, Any]) -> ImportItem:
    return ImportItem(
        item_id=str(doc.get("item_id") or doc.get("$id") or ""),
        batch_id=str(doc.get("batch_id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        novel_id=str(doc.get("novel_id") or ""),
        item_index=_int(doc.get("item_index"), 1),
        title=str(doc.get("title") or ""),
        content=str(doc.get("content") or ""),
        content_hash=str(doc.get("content_hash") or ""),
        char_count=_int(doc.get("char_count")),
        status=item_status_from(doc.get("status")),
        chapter_id=str(doc.get("chapter_id") or ""),
        job_id=str(doc.get("job_id") or ""),
        error_message=str(doc.get("error_message") or ""),
        attempts=_int(doc.get("attempts")),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
    )


class AppwriteBulkImportStore:
    mode = "appwrite"

    def __init__(self, settings: AppwriteSettings, client: Any = None):
        from server.appwrite_adapter import AppwriteConfigError

        if not settings.configured:
            raise AppwriteConfigError(
                "Cấu hình Appwrite chưa đủ cho kho nhập chương hàng loạt. Cần "
                "cả bốn biến APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, "
                "APPWRITE_API_KEY, APPWRITE_DATABASE_ID.")
        self._settings = settings
        self._endpoint = settings.api_base
        self._db = settings.database_id
        self._client = client
        self._attrs_cache: Dict[str, Set[str]] = {}
        self._pool: Optional[httpx.Client] = None
        self._lock = threading.RLock()

    # -- ha tang REST — giong het AppwriteTrustedSourceStore -------------------

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
            # PHAI la `AppwriteUnavailableError`, KHONG phai `NotFoundError`:
            # `create_*_once` bat `NotFoundError` va hieu no la "hang da ton
            # tai". Mot loi TRANSPORT bi boc thanh `NotFoundError` se lam
            # `create_batch_once` tra ve "da co lo nay" trong khi that ra chua
            # he ghi duoc gi — dung cai loi da vap o `appwrite_store._call`.
            raise AppwriteUnavailableError(
                f"Không kết nối được Appwrite: {exc}") from exc
        if response.status_code == 404:
            # Phan biet "thieu collection" voi "thieu ban ghi" — xem
            # `adapters.raise_for_appwrite_404`.
            raise_for_appwrite_404(response, path)
        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = None
            raise NotFoundError(
                thong_diep_loi_an_toan(body, status_code=response.status_code))
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def _docs(self, collection: str) -> str:
        return f"/v1/databases/{self._db}/collections/{collection}/documents"

    def _supported_fields(self, collection: str) -> Optional[Set[str]]:
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
            # KHONG quyen doc cong khai. Day la trang thai dieu phoi cua chu
            # truyen; noi dung chuong that di ra cong chung qua `chapters`.
            "permissions": [],
        })

    def _get(self, collection: str, doc_id: str) -> Dict[str, Any]:
        return self._call("GET", f"{self._docs(collection)}/{doc_id}")

    def _update(self, collection: str, doc_id: str,
                data: Dict[str, Any]) -> Dict[str, Any]:
        return self._call("PATCH", f"{self._docs(collection)}/{doc_id}",
                          payload={"data": self._writable(collection, data)})

    def _page(self, collection: str,
              queries: List[str]) -> Tuple[List[Dict[str, Any]], int]:
        data = self._call("GET", self._docs(collection),
                          params={"queries[]": queries})
        return list(data.get("documents") or []), int(data.get("total") or 0)

    def _list_all(self, collection: str,
                  queries: List[str]) -> Tuple[List[Dict[str, Any]], int]:
        """Lay HET (co lat trang). Xem diem 2 o docstring dau tep."""
        out: List[Dict[str, Any]] = []
        offset = 0
        tong = 0
        while True:
            page, tong = self._page(collection, queries + [
                q_limit(PAGE_SIZE), q_offset(offset)])
            out.extend(page)
            if len(page) < PAGE_SIZE:
                return out, max(tong, len(out))
            offset += PAGE_SIZE

    # -- lo --------------------------------------------------------------------

    def create_batch_once(self, batch: ImportBatch) -> Tuple[ImportBatch, bool]:
        """Tao-hoac-lay theo `batch_id` TAT DINH — Appwrite tu choi `POST` trung
        `documentId` (409, `_call` boc thanh `NotFoundError`), nen day la
        compare-and-set that su, khong can transaction rieng. Cung ky thuat voi
        `AppwriteAnimationStore.create_episode_once`."""
        try:
            self._create(COL_BATCHES, batch.batch_id, batch.to_dict())
            return batch, True
        except NotFoundError:
            return _batch_from_doc(self._get(COL_BATCHES, batch.batch_id)), False

    def get_batch(self, batch_id: str) -> ImportBatch:
        return _batch_from_doc(self._get(COL_BATCHES, batch_id))

    def save_batch(self, batch_id: str, fields: Dict[str, Any]) -> ImportBatch:
        duoc = {k: v for k, v in fields.items() if k in BATCH_EDITABLE}
        if "status" in duoc:
            gia_tri = duoc["status"]
            duoc["status"] = (gia_tri.value if isinstance(gia_tri, BatchStatus)
                              else str(gia_tri))
        duoc.setdefault("updated_at", now_iso())
        self._update(COL_BATCHES, batch_id, duoc)
        return self.get_batch(batch_id)

    def list_batches(self, *, owner_id: str = "", novel_id: str = "",
                     statuses: Optional[Sequence[BatchStatus]] = None,
                     limit: Optional[int] = None,
                     offset: int = 0) -> Tuple[List[ImportBatch], int]:
        queries: List[str] = []
        if owner_id:
            queries.append(q_equal("owner_id", owner_id))
        if novel_id:
            queries.append(q_equal("novel_id", novel_id))
        if statuses:
            # `equal` voi nhieu gia tri la OR o Appwrite — mot truy van, khong
            # phai mot truy van moi trang thai.
            queries.append(q_equal("status", *[BatchStatus(s).value
                                               for s in statuses]))
        queries.append(q_order_desc("created_at"))
        if limit is None:
            docs, tong = self._list_all(COL_BATCHES, queries)
            if offset:
                docs = docs[offset:]
        else:
            docs, tong = self._page(COL_BATCHES, queries + [
                q_limit(limit), q_offset(offset)])
        return [_batch_from_doc(d) for d in docs], tong

    # -- muc -------------------------------------------------------------------

    def create_item_once(self, item: ImportItem) -> Tuple[ImportItem, bool]:
        try:
            self._create(COL_ITEMS, item.item_id, item.to_dict(include_content=True))
            return item, True
        except NotFoundError:
            return _item_from_doc(self._get(COL_ITEMS, item.item_id)), False

    def get_item(self, item_id: str) -> ImportItem:
        return _item_from_doc(self._get(COL_ITEMS, item_id))

    def save_item(self, item_id: str, fields: Dict[str, Any]) -> ImportItem:
        duoc = {k: v for k, v in fields.items() if k in ITEM_EDITABLE}
        if "status" in duoc:
            gia_tri = duoc["status"]
            duoc["status"] = (gia_tri.value if isinstance(gia_tri, ItemStatus)
                              else str(gia_tri))
        duoc.setdefault("updated_at", now_iso())
        self._update(COL_ITEMS, item_id, duoc)
        return self.get_item(item_id)

    def list_items(self, batch_id: str, *,
                   statuses: Optional[Sequence[ItemStatus]] = None,
                   limit: Optional[int] = None, offset: int = 0,
                   include_content: bool = False) -> Tuple[List[ImportItem], int]:
        queries: List[str] = [q_equal("batch_id", batch_id)]
        if statuses:
            queries.append(q_equal("status", *[ItemStatus(s).value
                                               for s in statuses]))
        queries.append(q_order_asc("item_index"))
        if not include_content:
            # Xem diem 3 o docstring dau tep.
            queries.append(q_select(*_ITEM_FIELDS_NO_CONTENT))
        if limit is None:
            docs, tong = self._list_all(COL_ITEMS, queries)
            if offset:
                docs = docs[offset:]
        else:
            docs, tong = self._page(COL_ITEMS, queries + [
                q_limit(limit), q_offset(offset)])
        return [_item_from_doc(d) for d in docs], tong

    def count_items_by_status(self, batch_id: str) -> Dict[str, int]:
        """MOT truy van bi chan (`limit=1`, doc `total`) moi trang thai — nam
        truy van. CHI goi khi that can, xem docstring `ImportBatch`."""
        return {
            s.value: self._page(COL_ITEMS, [
                q_equal("batch_id", batch_id), q_equal("status", s.value),
                q_limit(1)])[1]
            for s in ItemStatus
        }


def build_bulk_import_store(settings: Any):
    """
    Chon kho theo `DATA_BACKEND` — cung mau voi `build_animation_store` /
    `build_trusted_source_store`.

    KHONG bat `AppwriteConfigError`: `DATA_BACKEND=appwrite` ma thieu bien cau
    hinh PHAI CHET NGAY luc khoi dong, khong am tham lui ve bo nho (mot lo nhap
    500 chuong "dang chay" trong RAM la thu bien mat lang le nhat co the).
    """
    from server.bulk_import_store import MockBulkImportStore

    if getattr(settings, "data_backend", "mock") == "appwrite":
        return AppwriteBulkImportStore(settings.appwrite)
    return MockBulkImportStore()
