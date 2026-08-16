"""
Kho Trusted Video Sources trong bo nho (Phase 5) — MOCK, dung cho dev/test.

Ban ben vung that qua restart la
`server/appwrite_trusted_source_store.py::AppwriteTrustedSourceStore`, CUNG
giao dien — cung mau voi `animation_store.py`/`appwrite_animation_store.py`.

BA bang DOC LAP: `sources` (TrustedSource), `mappings` (SeriesMapping),
`imports` (VideoImport) — KHONG dung chung bang voi `animation_series`/
`animation_episodes`.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from server.adapters import NotFoundError
from server.domain import now_iso
from server.trusted_source_domain import (
    SeriesMapping,
    SubscriptionStatus,
    TrustedSource,
    VideoImport,
    video_import_id,
)


class MockTrustedSourceStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.sources: Dict[str, TrustedSource] = {}
        self.mappings: Dict[str, SeriesMapping] = {}
        self.imports: Dict[str, VideoImport] = {}
        #: youtube_video_id -> import_id — cuong che DUY NHAT, xem
        #: `create_import_once`.
        self._video_index: Dict[str, str] = {}

    # -- trusted source -------------------------------------------------------

    def create_source(self, source: TrustedSource) -> TrustedSource:
        with self._lock:
            self.sources[source.source_id] = source
            return source

    def get_source(self, source_id: str) -> TrustedSource:
        source = self.sources.get(source_id)
        if source is None:
            raise NotFoundError("Không tìm thấy nguồn tin cậy.")
        return source

    #: Truong nguoi dung SUA duoc qua route cai dat — KHONG cho sua
    #: `source_type`/`youtube_channel_id`/`youtube_playlist_id` (doi nguon
    #: video la mot quyet dinh du lon de phai xoa-tao-lai, tranh am tham
    #: doi "nguon tin cay" ma khong ai de y).
    SOURCE_EDITABLE = (
        "display_name", "enabled", "auto_discover", "auto_import",
        "auto_publish", "minimum_confidence",
    )

    def update_source(self, source_id: str, fields: Dict[str, Any]) -> TrustedSource:
        with self._lock:
            current = self.get_source(source_id)
            allowed = {k: v for k, v in fields.items() if k in self.SOURCE_EDITABLE}
            updated = replace(current, **allowed, updated_at=now_iso())
            self.sources[source_id] = updated
            return updated

    def delete_source(self, source_id: str) -> None:
        with self._lock:
            self.get_source(source_id)
            self.sources.pop(source_id, None)
            mapping_ids = [m.mapping_id for m in self.mappings.values()
                          if m.trusted_source_id == source_id]
            for mid in mapping_ids:
                self.mappings.pop(mid, None)

    def find_sources(self, *, query: str = "", enabled: Optional[bool] = None,
                     limit: Optional[int] = None,
                     offset: int = 0) -> Tuple[List[TrustedSource], int]:
        with self._lock:
            items = list(self.sources.values())
        if enabled is not None:
            items = [s for s in items if s.enabled == enabled]
        needle = query.strip().casefold()
        if needle:
            items = [s for s in items if needle in s.display_name.casefold()]
        items.sort(key=lambda s: s.created_at, reverse=True)
        total = len(items)
        start = max(0, offset)
        page = items[start:] if limit is None else items[start:start + max(0, limit)]
        return page, total

    def record_scan_result(self, source_id: str, *, success: bool,
                           error_message: str = "") -> TrustedSource:
        """Cap nhat `last_scan_at`/`last_success_at`/`last_error_at` sau MOI
        lan quet — GOI DU du co tim thay video moi hay khong, vi day la dau
        vet "da thu", khong phai "da thanh cong tim duoc gi"."""
        with self._lock:
            current = self.get_source(source_id)
            moc = now_iso()
            allowed: Dict[str, Any] = {"last_scan_at": moc}
            if success:
                allowed["last_success_at"] = moc
                allowed["last_error_message"] = ""
            else:
                allowed["last_error_at"] = moc
                allowed["last_error_message"] = error_message
            updated = replace(current, **allowed, updated_at=moc)
            self.sources[source_id] = updated
            return updated

    def count_sources_by_subscription_status(self) -> Dict[str, int]:
        """Bo dem nguon THEO trang thai dang ky WebSub — Phase 7 analytics
        (trang He thong: suc khoe WebSub)."""
        with self._lock:
            items = list(self.sources.values())
        ra = {s.value: 0 for s in SubscriptionStatus}
        for src in items:
            ra[src.subscription_status.value] += 1
        return ra

    def find_source_by_channel_id(self, channel_id: str) -> Optional[TrustedSource]:
        if not channel_id:
            return None
        with self._lock:
            for s in self.sources.values():
                if s.youtube_channel_id == channel_id:
                    return s
        return None

    def record_websub_subscription(
        self, source_id: str, *, status: SubscriptionStatus,
        expires_at: str = "", secret: Optional[str] = None,
    ) -> TrustedSource:
        with self._lock:
            current = self.get_source(source_id)
            moc = now_iso()
            allowed: Dict[str, Any] = {
                "subscription_status": status,
                "last_subscription_attempt_at": moc,
            }
            if expires_at:
                allowed["subscription_expires_at"] = expires_at
            if secret is not None:
                allowed["websub_secret"] = secret
            updated = replace(current, **allowed, updated_at=moc)
            self.sources[source_id] = updated
            return updated

    def record_websub_notification(self, source_id: str) -> TrustedSource:
        with self._lock:
            current = self.get_source(source_id)
            moc = now_iso()
            updated = replace(current, last_notification_at=moc, updated_at=moc)
            self.sources[source_id] = updated
            return updated

    def record_websub_failure(self, source_id: str, *, error_message: str) -> TrustedSource:
        with self._lock:
            current = self.get_source(source_id)
            moc = now_iso()
            updated = replace(current, last_websub_error=error_message, updated_at=moc)
            self.sources[source_id] = updated
            return updated

    def record_reconciliation_sync(self, source_id: str) -> TrustedSource:
        with self._lock:
            current = self.get_source(source_id)
            moc = now_iso()
            updated = replace(current, last_successful_sync_at=moc, updated_at=moc)
            self.sources[source_id] = updated
            return updated

    # -- series mapping -----------------------------------------------------

    def create_mapping(self, mapping: SeriesMapping) -> SeriesMapping:
        with self._lock:
            self.mappings[mapping.mapping_id] = mapping
            return mapping

    def get_mapping(self, mapping_id: str) -> SeriesMapping:
        mapping = self.mappings.get(mapping_id)
        if mapping is None:
            raise NotFoundError("Không tìm thấy ánh xạ series.")
        return mapping

    def list_mappings(self, trusted_source_id: str) -> List[SeriesMapping]:
        with self._lock:
            items = [m for m in self.mappings.values()
                    if m.trusted_source_id == trusted_source_id]
        items.sort(key=lambda m: m.created_at)
        return items

    MAPPING_EDITABLE = (
        "aliases", "include_keywords", "exclude_keywords",
        "minimum_confidence", "auto_import", "auto_publish",
    )

    def update_mapping(self, mapping_id: str, fields: Dict[str, Any]) -> SeriesMapping:
        with self._lock:
            current = self.get_mapping(mapping_id)
            allowed = {k: v for k, v in fields.items() if k in self.MAPPING_EDITABLE}
            updated = replace(current, **allowed, updated_at=now_iso())
            self.mappings[mapping_id] = updated
            return updated

    def delete_mapping(self, mapping_id: str) -> None:
        with self._lock:
            self.get_mapping(mapping_id)
            self.mappings.pop(mapping_id, None)

    def mapping_counts(self, source_ids: Sequence[str]) -> Dict[str, int]:
        """So anh xa cua nhieu nguon trong MOT lan quet — dung cho cot 'so
        series da anh xa' o danh sach quan tri, khong N+1."""
        can = set(source_ids)
        dem = {sid: 0 for sid in can}
        with self._lock:
            for m in self.mappings.values():
                if m.trusted_source_id in can:
                    dem[m.trusted_source_id] += 1
        return dem

    # -- video import (hang doi nhap) ----------------------------------------

    def create_import_once(self, video_import: VideoImport) -> Tuple[VideoImport, bool]:
        """Tao MOI neu `youtube_video_id` CHUA tung xuat hien, nguoc lai tra
        ve BAN GHI CU NGUYEN VEN (khong ghi de) — day la co so cua "quet
        idempotent": quet lai mot nguon khong tao ban trung, khong doi
        quyet dinh quan tri da co.

        Ghi de `import_id` bang `video_import_id()` TAT DINH — xem docstring
        ham do ve vi sao (dong bo voi `documentId` that o ban Appwrite)."""
        with self._lock:
            video_import = replace(
                video_import, import_id=video_import_id(video_import.youtube_video_id))
            da_co_id = self._video_index.get(video_import.youtube_video_id)
            if da_co_id is not None:
                return self.imports[da_co_id], False
            self.imports[video_import.import_id] = video_import
            self._video_index[video_import.youtube_video_id] = video_import.import_id
            return video_import, True

    def get_import(self, import_id: str) -> VideoImport:
        item = self.imports.get(import_id)
        if item is None:
            raise NotFoundError("Không tìm thấy video trong hàng đợi nhập.")
        return item

    def get_import_by_video_id(self, video_id: str) -> Optional[VideoImport]:
        with self._lock:
            iid = self._video_index.get(video_id)
            return self.imports.get(iid) if iid else None

    def imports_by_video_ids(self, video_ids: Sequence[str]) -> Dict[str, VideoImport]:
        with self._lock:
            ra: Dict[str, VideoImport] = {}
            for vid in dict.fromkeys(video_ids):
                iid = self._video_index.get(vid)
                if iid and iid in self.imports:
                    ra[vid] = self.imports[iid]
            return ra

    def find_imports(self, *, status: str = "", trusted_source_id: str = "",
                     series_id: str = "", created_after: str = "",
                     limit: int = 25,
                     offset: int = 0) -> Tuple[List[VideoImport], int]:
        with self._lock:
            items = list(self.imports.values())
        if status:
            items = [i for i in items if i.status.value == status]
        if trusted_source_id:
            items = [i for i in items if i.trusted_source_id == trusted_source_id]
        if series_id:
            items = [i for i in items if i.detected_series_id == series_id]
        if created_after:
            items = [i for i in items if i.created_at >= created_after]
        items.sort(key=lambda i: i.created_at, reverse=True)
        total = len(items)
        start = max(0, offset)
        page = items[start:start + max(0, limit)]
        return page, total

    def update_import(self, import_id: str, fields: Dict[str, Any]) -> VideoImport:
        with self._lock:
            current = self.get_import(import_id)
            updated = replace(current, **fields, updated_at=now_iso())
            self.imports[import_id] = updated
            return updated
