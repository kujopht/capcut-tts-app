"""
Kho nhap chuong hang loat TRONG BO NHO.

CUNG MAU va CUNG NGUYEN TAC voi `server/animation_store.py` /
`server/trusted_source_store.py`: module nay CHI dinh nghia
`MockBulkImportStore`. Ban ben vung qua restart la
`server/appwrite_bulk_import_store.py::AppwriteBulkImportStore` — CUNG giao
dien — va `build_bulk_import_store()` (chon Mock/Appwrite theo `DATA_BACKEND`)
nam o do, KHONG phai o day.

HAI collection RIENG (`chapter_import_batches`, `chapter_import_items`), doc
lap voi `novels`/`chapters`/`tts_jobs`. Lo nhap la trang thai DIEU PHOI: xoa
ca hai bang di thi khong mat chuong hay audio nao, chi mat kha nang tiep tuc
mot dot nhap dang do.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from server.adapters import NotFoundError
from server.bulk_import_domain import (
    BatchStatus,
    ImportBatch,
    ImportItem,
    ItemStatus,
    batch_status_from,
    item_status_from,
)
from server.domain import now_iso

#: Truong cua LO ma tang tren duoc phep ghi qua `save_batch`. Danh sach trang
#: — khong bao gio de mot dict tuy y ghi thang vao hang: `batch_id`/`owner_id`/
#: `fingerprint`/`total_items` la danh tinh cua lo, doi chung la doi y nghia
#: cua ca tinh idempotent.
BATCH_EDITABLE = frozenset({
    "status", "voice_id", "rate", "chunk_chars", "source_name",
    "count_pending", "count_chapter_created", "count_job_queued",
    "count_completed", "count_failed", "last_error",
    "updated_at", "cancelled_at", "finished_at",
})

#: Tuong tu cho MUC. `content`/`content_hash`/`title`/`item_index` la ban goc
#: da nhap — bo dieu phoi khong bao gio sua chung.
ITEM_EDITABLE = frozenset({
    "status", "chapter_id", "job_id", "error_message", "attempts",
    "updated_at",
})


class MockBulkImportStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.batches: Dict[str, ImportBatch] = {}
        self.items: Dict[str, ImportItem] = {}

    # -- lo --------------------------------------------------------------------

    def create_batch_once(self, batch: ImportBatch) -> Tuple[ImportBatch, bool]:
        """
        Tao-hoac-lay AN TOAN theo `batch.batch_id` TAT DINH.

        Mo phong dung hanh vi Appwrite tu choi `POST` trung `documentId` — xem
        `MockAnimationStore.create_episode_once`. Day la ca co che idempotent
        cua "gui lai cung mot tep": nguoi thu hai khong ghi duoc gi va nhan ve
        lo cua nguoi thu nhat.
        """
        with self._lock:
            hien_co = self.batches.get(batch.batch_id)
            if hien_co is not None:
                return hien_co, False
            self.batches[batch.batch_id] = batch
            return batch, True

    def get_batch(self, batch_id: str) -> ImportBatch:
        batch = self.batches.get(batch_id)
        if batch is None:
            raise NotFoundError("Không tìm thấy lô nhập chương.")
        return batch

    def save_batch(self, batch_id: str, fields: Dict[str, Any]) -> ImportBatch:
        with self._lock:
            hien_tai = self.get_batch(batch_id)
            duoc = {k: v for k, v in fields.items() if k in BATCH_EDITABLE}
            if "status" in duoc:
                duoc["status"] = batch_status_from(duoc["status"],
                                                   hien_tai.status)
            duoc.setdefault("updated_at", now_iso())
            moi = replace(hien_tai, **duoc)
            self.batches[batch_id] = moi
            return moi

    def list_batches(self, *, owner_id: str = "", novel_id: str = "",
                     statuses: Optional[Sequence[BatchStatus]] = None,
                     limit: Optional[int] = None,
                     offset: int = 0) -> Tuple[List[ImportBatch], int]:
        with self._lock:
            ds = list(self.batches.values())
        if owner_id:
            ds = [b for b in ds if b.owner_id == owner_id]
        if novel_id:
            ds = [b for b in ds if b.novel_id == novel_id]
        if statuses:
            can = {BatchStatus(s) for s in statuses}
            ds = [b for b in ds if b.status in can]
        # Moi nhat truoc — cung quy uoc voi moi danh sach khac cua nguoi dung.
        ds.sort(key=lambda b: b.created_at, reverse=True)
        tong = len(ds)
        if offset:
            ds = ds[offset:]
        if limit is not None:
            ds = ds[:limit]
        return ds, tong

    # -- muc -------------------------------------------------------------------

    def create_item_once(self, item: ImportItem) -> Tuple[ImportItem, bool]:
        """Tao-hoac-lay theo `item.item_id` TAT DINH — nho vay viec ghi danh
        sach muc co the bi cat giua chung roi chay lai ma khong sinh ban
        trung."""
        with self._lock:
            hien_co = self.items.get(item.item_id)
            if hien_co is not None:
                return hien_co, False
            self.items[item.item_id] = item
            return item, True

    def get_item(self, item_id: str) -> ImportItem:
        item = self.items.get(item_id)
        if item is None:
            raise NotFoundError("Không tìm thấy chương trong lô nhập.")
        return item

    def save_item(self, item_id: str, fields: Dict[str, Any]) -> ImportItem:
        with self._lock:
            hien_tai = self.get_item(item_id)
            duoc = {k: v for k, v in fields.items() if k in ITEM_EDITABLE}
            if "status" in duoc:
                duoc["status"] = item_status_from(duoc["status"], hien_tai.status)
            duoc.setdefault("updated_at", now_iso())
            moi = replace(hien_tai, **duoc)
            self.items[item_id] = moi
            return moi

    def list_items(self, batch_id: str, *,
                   statuses: Optional[Sequence[ItemStatus]] = None,
                   limit: Optional[int] = None, offset: int = 0,
                   include_content: bool = False) -> Tuple[List[ImportItem], int]:
        """
        Muc cua mot lo, LUON theo `item_index` tang — thu tu nhap la thu tu
        chuong, va bo dieu phoi dua vao dieu do de tao chuong dung thu tu.

        `include_content` khong doi gi o ban mock (cung doi tuong trong bo nho)
        nhung PHAI co trong giao dien: ban Appwrite dung no de `select` bo cot
        `content` ra khoi duong doc cua API.
        """
        with self._lock:
            ds = [i for i in self.items.values() if i.batch_id == batch_id]
        if statuses:
            can = {ItemStatus(s) for s in statuses}
            ds = [i for i in ds if i.status in can]
        ds.sort(key=lambda i: i.item_index)
        tong = len(ds)
        if offset:
            ds = ds[offset:]
        if limit is not None:
            ds = ds[:limit]
        if not include_content:
            ds = [replace(i, content="") for i in ds]
        return ds, tong

    def count_items_by_status(self, batch_id: str) -> Dict[str, int]:
        """Dem CHINH XAC theo trang thai. Ban Appwrite ton mot truy van bi chan
        moi trang thai, nen cho nay CHI duoc goi khi that can — xem docstring
        `ImportBatch`."""
        ra = {s.value: 0 for s in ItemStatus}
        with self._lock:
            for item in self.items.values():
                if item.batch_id == batch_id:
                    ra[item.status.value] = ra.get(item.status.value, 0) + 1
        return ra
