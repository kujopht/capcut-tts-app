"""
Kho Trusted Video Sources ben vung tren Appwrite (Phase 5).

Cung giao dien voi `MockTrustedSourceStore` — cung mau voi
`appwrite_animation_store.py`. BA collection RIENG: `trusted_sources`,
`series_mappings`, `video_imports` — xem `scripts/setup_appwrite.py`.
"""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx

from server.adapters import NotFoundError, raise_for_appwrite_404
from server.config import AppwriteSettings
from server.domain import now_iso
from server.secret_redaction import thong_diep_loi_an_toan
from server.trusted_source_domain import (
    ImportStatus,
    SeriesMapping,
    SubscriptionStatus,
    TrustedSource,
    TrustedSourceType,
    VideoImport,
    video_import_id,
)

COL_SOURCES = "trusted_sources"
COL_MAPPINGS = "series_mappings"
COL_IMPORTS = "video_imports"

_PERSISTED_FIELDS: Dict[str, tuple] = {
    COL_SOURCES: (
        "source_id", "source_type", "youtube_channel_id",
        "youtube_playlist_id", "uploads_playlist_id", "youtube_video_id",
        "display_name",
        "thumbnail_url", "enabled",
        "auto_discover", "auto_import", "auto_publish", "minimum_confidence",
        "created_by", "last_scan_at", "last_success_at", "last_error_at",
        "last_error_message", "subscription_status", "subscription_expires_at",
        "last_subscription_attempt_at", "last_notification_at",
        "last_websub_error", "last_successful_sync_at", "websub_secret",
        "created_at", "updated_at",
    ),
    COL_MAPPINGS: (
        "mapping_id", "trusted_source_id", "animation_series_id", "aliases",
        "include_keywords", "exclude_keywords", "minimum_confidence",
        "auto_import", "auto_publish", "created_at", "updated_at",
    ),
    COL_IMPORTS: (
        "import_id", "trusted_source_id", "youtube_video_id", "title",
        "channel_id", "channel_title", "thumbnail_url", "published_at",
        "duration_seconds", "detected_mapping_id", "detected_series_id",
        "detected_episode_number", "confidence", "signals", "status",
        "reason", "created_episode_id", "reviewed_by", "reviewed_at",
        "discovered_via", "possible_duplicate_novel_id",
        "created_at", "updated_at",
    ),
}

# Cac thuoc tinh KIEU `datetime` (khong bat buoc) tren tung collection — xem
# ghi chu o `_writable`: Appwrite (tu luu tru) TU DIEN gio server HIEN TAI khi
# nhan chuoi rong "" cho thuoc tinh datetime khong bat buoc, thay vi null nhu
# ky vong (da xac nhan THAT tren moi truong dev — KHONG phai suy doan). Bug
# nay lam MOI nguon tin cay/video import MOI tao trong nhu da tung quet/dang
# ky/duyet ngay tu luc tao.
_DATETIME_FIELDS: Dict[str, tuple] = {
    COL_SOURCES: (
        "last_scan_at", "last_success_at", "last_error_at",
        "subscription_expires_at", "last_subscription_attempt_at",
        "last_notification_at", "last_successful_sync_at",
    ),
    COL_IMPORTS: ("published_at", "reviewed_at"),
}

REQUEST_TIMEOUT = 15.0
PAGE_SIZE = 100


def q_equal(attribute: str, *values: Any) -> str:
    return json.dumps({"method": "equal", "attribute": attribute,
                       "values": list(values)})


def q_order_desc(attribute: str) -> str:
    return json.dumps({"method": "orderDesc", "attribute": attribute})


def q_limit(count: int) -> str:
    return json.dumps({"method": "limit", "values": [int(count)]})


def q_offset(count: int) -> str:
    return json.dumps({"method": "offset", "values": [int(count)]})


def q_contains(attribute: str, value: Any) -> str:
    return json.dumps({"method": "contains", "attribute": attribute, "values": [value]})


def q_greater_equal(attribute: str, value: Any) -> str:
    #: Ten method THAT cua Appwrite la "greaterThanEqual" — xem muc 6 handoff.
    return json.dumps({"method": "greaterThanEqual", "attribute": attribute,
                       "values": [value]})


def _nguon_tu_doc(doc: Dict[str, Any]) -> TrustedSource:
    try:
        loai = TrustedSourceType(str(doc.get("source_type") or "youtube_channel"))
    except ValueError:
        loai = TrustedSourceType.YOUTUBE_CHANNEL
    try:
        sub = SubscriptionStatus(str(doc.get("subscription_status") or "none"))
    except ValueError:
        sub = SubscriptionStatus.NONE
    return TrustedSource(
        source_id=str(doc.get("source_id") or doc.get("$id") or ""),
        source_type=loai,
        youtube_channel_id=str(doc.get("youtube_channel_id") or ""),
        youtube_playlist_id=str(doc.get("youtube_playlist_id") or ""),
        uploads_playlist_id=(str(doc["uploads_playlist_id"])
                             if doc.get("uploads_playlist_id") else None),
        youtube_video_id=str(doc.get("youtube_video_id") or ""),
        display_name=str(doc.get("display_name") or ""),
        thumbnail_url=str(doc.get("thumbnail_url") or ""),
        enabled=bool(doc.get("enabled", True)),
        auto_discover=bool(doc.get("auto_discover", False)),
        auto_import=bool(doc.get("auto_import", False)),
        auto_publish=bool(doc.get("auto_publish", False)),
        minimum_confidence=float(doc.get("minimum_confidence", 0.9)),
        created_by=str(doc.get("created_by") or ""),
        last_scan_at=str(doc.get("last_scan_at") or ""),
        last_success_at=str(doc.get("last_success_at") or ""),
        last_error_at=str(doc.get("last_error_at") or ""),
        last_error_message=str(doc.get("last_error_message") or ""),
        subscription_status=sub,
        subscription_expires_at=str(doc.get("subscription_expires_at") or ""),
        last_subscription_attempt_at=str(doc.get("last_subscription_attempt_at") or ""),
        last_notification_at=str(doc.get("last_notification_at") or ""),
        last_websub_error=str(doc.get("last_websub_error") or ""),
        last_successful_sync_at=str(doc.get("last_successful_sync_at") or ""),
        websub_secret=str(doc.get("websub_secret") or ""),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
    )


def _nguon_thanh_hang(source: TrustedSource) -> Dict[str, Any]:
    """
    Ban ghi DAY DU de GHI len Appwrite — KHAC `TrustedSource.to_dict()`
    (an toan, tra ve API) o DUY NHAT MOT diem: co them `websub_secret`. Cung
    mau voi `appwrite_translation_store.py::_connection_to_row` (BYOK,
    V5.1) — hai ham serialize TACH BIET cho hai muc dich, khong phai mot
    dict dung chung.
    """
    ra = source.to_dict()
    ra["websub_secret"] = source.websub_secret
    return ra


def _anh_xa_tu_doc(doc: Dict[str, Any]) -> SeriesMapping:
    return SeriesMapping(
        mapping_id=str(doc.get("mapping_id") or doc.get("$id") or ""),
        trusted_source_id=str(doc.get("trusted_source_id") or ""),
        animation_series_id=str(doc.get("animation_series_id") or ""),
        aliases=list(doc.get("aliases") or []),
        include_keywords=list(doc.get("include_keywords") or []),
        exclude_keywords=list(doc.get("exclude_keywords") or []),
        minimum_confidence=(
            float(doc["minimum_confidence"])
            if doc.get("minimum_confidence") is not None else None),
        auto_import=doc.get("auto_import"),
        auto_publish=doc.get("auto_publish"),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
    )


def _import_tu_doc(doc: Dict[str, Any]) -> VideoImport:
    try:
        trang_thai = ImportStatus(str(doc.get("status") or "new"))
    except ValueError:
        trang_thai = ImportStatus.NEW
    so_tap = doc.get("detected_episode_number")
    return VideoImport(
        import_id=str(doc.get("import_id") or doc.get("$id") or ""),
        trusted_source_id=str(doc.get("trusted_source_id") or ""),
        youtube_video_id=str(doc.get("youtube_video_id") or ""),
        title=str(doc.get("title") or ""),
        channel_id=str(doc.get("channel_id") or ""),
        channel_title=str(doc.get("channel_title") or ""),
        thumbnail_url=str(doc.get("thumbnail_url") or ""),
        published_at=str(doc.get("published_at") or ""),
        duration_seconds=float(doc.get("duration_seconds") or 0.0),
        detected_mapping_id=str(doc.get("detected_mapping_id") or ""),
        detected_series_id=str(doc.get("detected_series_id") or ""),
        detected_episode_number=int(so_tap) if so_tap is not None else None,
        confidence=float(doc.get("confidence") or 0.0),
        signals=list(doc.get("signals") or []),
        status=trang_thai,
        reason=str(doc.get("reason") or ""),
        created_episode_id=str(doc.get("created_episode_id") or ""),
        reviewed_by=str(doc.get("reviewed_by") or ""),
        reviewed_at=str(doc.get("reviewed_at") or ""),
        discovered_via=str(doc.get("discovered_via") or ""),
        possible_duplicate_novel_id=(
            str(doc["possible_duplicate_novel_id"])
            if doc.get("possible_duplicate_novel_id") else None),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
    )


class AppwriteTrustedSourceStore:
    mode = "appwrite"

    def __init__(self, settings: AppwriteSettings, client: Any = None):
        from server.appwrite_adapter import AppwriteConfigError

        if not settings.configured:
            raise AppwriteConfigError(
                "Cấu hình Appwrite chưa đủ cho kho Trusted Sources. Cần cả bốn "
                "biến APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY, "
                "APPWRITE_DATABASE_ID.")
        self._settings = settings
        self._endpoint = settings.api_base
        self._db = settings.database_id
        self._client = client
        self._attrs_cache: Dict[str, Set[str]] = {}
        self._pool: Optional[httpx.Client] = None
        self._lock = threading.RLock()

    # -- ha tang REST — giong het AppwriteAnimationStore ----------------------

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
            raise NotFoundError(f"Không kết nối được Appwrite: {exc}") from exc
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
        allowed = _PERSISTED_FIELDS.get(collection)
        fields = ({k: v for k, v in data.items() if k in allowed}
                 if allowed is not None else dict(data))
        for ten in _DATETIME_FIELDS.get(collection, ()):
            if fields.get(ten) == "":
                fields[ten] = None
        available = self._supported_fields(collection)
        if available is None:
            return fields
        return {k: v for k, v in fields.items() if k in available}

    def _create(self, collection: str, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._call("POST", self._docs(collection), payload={
            "documentId": doc_id,
            "data": self._writable(collection, data),
            # KHONG co quyen doc cong khai nao ca — day la du lieu QUAN TRI
            # noi bo, khong bao gio ra API cong khai.
            "permissions": [],
        })

    def _get(self, collection: str, doc_id: str) -> Dict[str, Any]:
        return self._call("GET", f"{self._docs(collection)}/{doc_id}")

    def _update(self, collection: str, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._call("PATCH", f"{self._docs(collection)}/{doc_id}",
                          payload={"data": self._writable(collection, data)})

    def _delete(self, collection: str, doc_id: str) -> None:
        try:
            self._call("DELETE", f"{self._docs(collection)}/{doc_id}")
        except NotFoundError:
            pass

    def _list_all(self, collection: str, queries: List[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        offset = 0
        while True:
            data = self._call("GET", self._docs(collection),
                              params={"queries[]": queries + [
                                  q_limit(PAGE_SIZE), q_offset(offset)]})
            page = list(data.get("documents") or [])
            out.extend(page)
            if len(page) < PAGE_SIZE:
                return out
            offset += PAGE_SIZE

    def _page(self, collection: str,
             queries: List[str]) -> Tuple[List[Dict[str, Any]], int]:
        data = self._call("GET", self._docs(collection),
                          params={"queries[]": queries})
        return list(data.get("documents") or []), int(data.get("total") or 0)

    # -- trusted source -------------------------------------------------------

    def create_source(self, source: TrustedSource) -> TrustedSource:
        self._create(COL_SOURCES, source.source_id, _nguon_thanh_hang(source))
        return source

    def create_source_once(self, source: TrustedSource) -> Tuple[TrustedSource, bool]:
        """
        Cuong che DUY NHAT theo `source.source_id` TAT DINH (xem
        `trusted_source_domain.trusted_source_id`) — cung ky thuat "POST
        trung documentId la tao-hoac-lay an toan" voi `create_import_once`/
        `create_mapping_once`. Nguoi goi (`TrustedSourceService.create_source`)
        PHAI da gan `source.source_id` bang `trusted_source_id(...)` truoc
        khi goi — day la NGUOI CHAN CUOI CUNG chong hai yeu cau "Thêm nguồn
        tin cậy" cho CUNG mot kenh/playlist/video gan nhu dong thoi deu vuot
        qua kiem tra doc-truoc (`_dinh_danh_da_ton_tai`, van CHAY TRUOC vi no
        cho thong diep loi than thien hon o truong hop thuong, khong dua
        nhau) va deu tao thanh cong.
        """
        try:
            self._create(COL_SOURCES, source.source_id, _nguon_thanh_hang(source))
            return source, True
        except NotFoundError:
            # `_call` boc MOI loi >=400 thanh `NotFoundError` — 409 trung
            # `documentId` cung roi vao day. Doc lai ban DA CO thay vi doan
            # la loi that (cung nguyen tac voi `create_import_once`).
            return _nguon_tu_doc(self._get(COL_SOURCES, source.source_id)), False

    def get_source(self, source_id: str) -> TrustedSource:
        return _nguon_tu_doc(self._get(COL_SOURCES, source_id))

    def get_sources_by_ids(self, source_ids: Sequence[str]) -> Dict[str, TrustedSource]:
        """Nhieu nguon theo ID, MOT truy van moi lo 50 — tranh N+1 khi lam
        giau Import Queue (Phase 5 hieu nang: truoc day moi ID rieng le goi
        `get_source` MOT truy van HTTP rieng). Loc theo `$id` (KHONG can chi
        muc rieng): `create_source` dung thang `source.source_id` lam ID tai
        lieu Appwrite, nen `$id` va `source_id` LUON trung nhau, cung ly do
        voi `get_series_by_ids` o `appwrite_animation_store.py`."""
        ds = [s for s in dict.fromkeys(source_ids) if s]
        ra: Dict[str, TrustedSource] = {}
        for i in range(0, len(ds), 50):
            lo = ds[i:i + 50]
            for row in self._list_all(COL_SOURCES, [q_equal("$id", *lo)]):
                s = _nguon_tu_doc(row)
                ra[s.source_id] = s
        return ra

    SOURCE_EDITABLE = (
        "display_name", "enabled", "auto_discover", "auto_import",
        "auto_publish", "minimum_confidence",
    )

    def update_source(self, source_id: str, fields: Dict[str, Any]) -> TrustedSource:
        data = {k: v for k, v in fields.items() if k in self.SOURCE_EDITABLE}
        data["updated_at"] = now_iso()
        self._update(COL_SOURCES, source_id, data)
        return self.get_source(source_id)

    def delete_source(self, source_id: str) -> None:
        self.get_source(source_id)
        for m in self.list_mappings(source_id):
            self._delete(COL_MAPPINGS, m.mapping_id)
        self._delete(COL_SOURCES, source_id)

    def find_sources(self, *, query: str = "", enabled: Optional[bool] = None,
                     limit: Optional[int] = None,
                     offset: int = 0) -> Tuple[List[TrustedSource], int]:
        queries: List[str] = []
        if enabled is not None:
            queries.append(q_equal("enabled", enabled))
        needle = query.strip()
        if needle:
            queries.append(q_contains("display_name", needle))
        queries.append(q_order_desc("created_at"))
        if limit is None:
            items = [_nguon_tu_doc(d) for d in self._list_all(COL_SOURCES, queries)]
            return items, len(items)
        docs, total = self._page(COL_SOURCES, queries + [
            q_limit(limit), q_offset(max(0, offset))])
        return [_nguon_tu_doc(d) for d in docs], total

    def record_scan_result(self, source_id: str, *, success: bool,
                           error_message: str = "") -> TrustedSource:
        moc = now_iso()
        data: Dict[str, Any] = {"last_scan_at": moc, "updated_at": moc}
        if success:
            data["last_success_at"] = moc
            data["last_error_message"] = ""
        else:
            data["last_error_at"] = moc
            data["last_error_message"] = error_message
        self._update(COL_SOURCES, source_id, data)
        return self.get_source(source_id)

    def find_source_by_channel_id(self, channel_id: str) -> Optional[TrustedSource]:
        """Tra cuu THEO `channel_idx` (index co san tu Phase 5) — dung boi
        callback WebSub (Phase 6) de biet mot thong bao thuoc nguon nao,
        KHONG can quet toan bang."""
        if not channel_id:
            return None
        docs, _total = self._page(COL_SOURCES, [
            q_equal("youtube_channel_id", channel_id), q_limit(1)])
        return _nguon_tu_doc(docs[0]) if docs else None

    def record_websub_subscription(
        self, source_id: str, *, status: SubscriptionStatus,
        expires_at: str = "", secret: Optional[str] = None,
    ) -> TrustedSource:
        """
        Ghi lai KET QUA mot lan thu dang ky/gia han/huy dang ky WebSub
        (Phase 6). `secret` CHI ghi de khi truyen THAT (khac `None`) — goi
        de HUY dang ky (`status=NONE`) khong can/khong nen xoa bi mat dang
        dung do dang ky co the dang xu ly dong thoi; `subscribe_source` moi
        la noi sinh bi mat MOI va truyen vao day.
        """
        moc = now_iso()
        data: Dict[str, Any] = {
            "subscription_status": status.value,
            "last_subscription_attempt_at": moc,
            "updated_at": moc,
        }
        if expires_at:
            data["subscription_expires_at"] = expires_at
        if secret is not None:
            data["websub_secret"] = secret
        self._update(COL_SOURCES, source_id, data)
        return self.get_source(source_id)

    def record_websub_notification(self, source_id: str) -> TrustedSource:
        moc = now_iso()
        self._update(COL_SOURCES, source_id,
                     {"last_notification_at": moc, "updated_at": moc})
        return self.get_source(source_id)

    def record_websub_failure(self, source_id: str, *, error_message: str) -> TrustedSource:
        moc = now_iso()
        self._update(COL_SOURCES, source_id, {
            "last_websub_error": error_message, "updated_at": moc,
        })
        return self.get_source(source_id)

    def record_reconciliation_sync(self, source_id: str) -> TrustedSource:
        moc = now_iso()
        self._update(COL_SOURCES, source_id,
                     {"last_successful_sync_at": moc, "updated_at": moc})
        return self.get_source(source_id)

    def record_uploads_playlist_id(
        self, source_id: str, uploads_playlist_id: str) -> TrustedSource:
        """Ghi lai `uploads_playlist_id` DA RESOLVE qua `channels.list` —
        xem docstring `TrustedSource.uploads_playlist_id`. CHI goi MOT LAN
        cho moi kenh (lan dau tien `_lay_ung_vien` thay truong nay con
        rong), cac lan quet/doi chieu sau doc lai gia tri da cache, khong
        goi lai `channels.list`."""
        moc = now_iso()
        self._update(COL_SOURCES, source_id,
                     {"uploads_playlist_id": uploads_playlist_id, "updated_at": moc})
        return self.get_source(source_id)

    # -- series mapping -----------------------------------------------------

    def create_mapping(self, mapping: SeriesMapping) -> SeriesMapping:
        self._create(COL_MAPPINGS, mapping.mapping_id, mapping.to_dict())
        return mapping

    def create_mapping_once(self, mapping: SeriesMapping) -> Tuple[SeriesMapping, bool]:
        """
        Cuong che DUY NHAT theo `mapping.mapping_id` TAT DINH (xem
        `trusted_source_domain.inferred_mapping_id`) — cung ky thuat "POST
        trung documentId la tao-hoac-lay an toan" voi `create_import_once`/
        `AppwriteAnimationStore.create_episode_once`. Nguoi goi PHAI da gan
        `mapping.mapping_id` bang `inferred_mapping_id(...)` truoc khi goi.
        """
        try:
            self._create(COL_MAPPINGS, mapping.mapping_id, mapping.to_dict())
            return mapping, True
        except NotFoundError:
            # `_call` boc MOI loi >=400 thanh `NotFoundError` — 409 trung
            # `documentId` cung roi vao day. Doc lai ban DA CO thay vi doan
            # la loi that (cung nguyen tac voi `create_import_once`).
            return _anh_xa_tu_doc(self._get(COL_MAPPINGS, mapping.mapping_id)), False

    def get_mapping(self, mapping_id: str) -> SeriesMapping:
        return _anh_xa_tu_doc(self._get(COL_MAPPINGS, mapping_id))

    def list_mappings(self, trusted_source_id: str) -> List[SeriesMapping]:
        docs = self._list_all(COL_MAPPINGS, [
            q_equal("trusted_source_id", trusted_source_id),
        ])
        items = [_anh_xa_tu_doc(d) for d in docs]
        items.sort(key=lambda m: m.created_at)
        return items

    MAPPING_EDITABLE = (
        "aliases", "include_keywords", "exclude_keywords",
        "minimum_confidence", "auto_import", "auto_publish",
    )

    def update_mapping(self, mapping_id: str, fields: Dict[str, Any]) -> SeriesMapping:
        data = {k: v for k, v in fields.items() if k in self.MAPPING_EDITABLE}
        data["updated_at"] = now_iso()
        self._update(COL_MAPPINGS, mapping_id, data)
        return self.get_mapping(mapping_id)

    def delete_mapping(self, mapping_id: str) -> None:
        self.get_mapping(mapping_id)
        self._delete(COL_MAPPINGS, mapping_id)

    def mapping_counts(self, source_ids: Sequence[str]) -> Dict[str, int]:
        ds = [s for s in dict.fromkeys(source_ids) if s]
        dem = {sid: 0 for sid in ds}
        for i in range(0, len(ds), 50):
            lo = ds[i:i + 50]
            for row in self._list_all(COL_MAPPINGS, [
                    q_equal("trusted_source_id", *lo)]):
                sid = str(row.get("trusted_source_id") or "")
                if sid in dem:
                    dem[sid] += 1
        return dem

    def imported_episode_ids(self, source_ids: Sequence[str]) -> Dict[str, List[str]]:
        """Xem docstring `MockTrustedSourceStore.imported_episode_ids` —
        MOT truy van moi lo 50 nguon."""
        ds = [s for s in dict.fromkeys(source_ids) if s]
        ra: Dict[str, List[str]] = {sid: [] for sid in ds}
        for i in range(0, len(ds), 50):
            lo = ds[i:i + 50]
            for row in self._list_all(COL_IMPORTS, [
                    q_equal("trusted_source_id", *lo)]):
                sid = str(row.get("trusted_source_id") or "")
                eid = str(row.get("created_episode_id") or "")
                if sid in ra and eid:
                    ra[sid].append(eid)
        return ra

    # -- video import (hang doi nhap) ----------------------------------------

    def create_import_once(self, video_import: VideoImport) -> Tuple[VideoImport, bool]:
        """
        Cuong che DUY NHAT theo `youtube_video_id` bang `documentId` TAT
        DINH (`video_import_id()` — CUNG gia tri duoc gan lam
        `VideoImport.import_id`, xem docstring ham do) — CUNG ky thuat voi
        `appwrite_store.py::_job_lock_id` (Appwrite tu choi `POST` trung
        `documentId`, nen day la mot phep "tao-hoac-lay" AN TOAN duoi tai
        dua nhau, khong can transaction rieng).
        """
        video_import = replace(
            video_import, import_id=video_import_id(video_import.youtube_video_id))
        try:
            self._create(COL_IMPORTS, video_import.import_id, video_import.to_dict())
            return video_import, True
        except NotFoundError:
            # `_call` boc MOI loi >=400 thanh `NotFoundError` (xem ghi chu o
            # `appwrite_animation_store.py`) — 409 trung `documentId` cung
            # roi vao day. Doc lai ban ĐÃ CO thay vi doan la loi that.
            return _import_tu_doc(self._get(COL_IMPORTS, video_import.import_id)), False

    def get_import(self, import_id: str) -> VideoImport:
        return _import_tu_doc(self._get(COL_IMPORTS, import_id))

    def get_import_by_video_id(self, video_id: str) -> Optional[VideoImport]:
        try:
            return _import_tu_doc(self._get(COL_IMPORTS, video_import_id(video_id)))
        except NotFoundError:
            return None

    def imports_by_video_ids(self, video_ids: Sequence[str]) -> Dict[str, VideoImport]:
        ds = [v for v in dict.fromkeys(video_ids) if v]
        ra: Dict[str, VideoImport] = {}
        for i in range(0, len(ds), 50):
            lo = ds[i:i + 50]
            for row in self._list_all(COL_IMPORTS, [
                    q_equal("youtube_video_id", *lo)]):
                item = _import_tu_doc(row)
                ra[item.youtube_video_id] = item
        return ra

    def find_imports(self, *, status: str = "", trusted_source_id: str = "",
                     series_id: str = "", created_after: str = "",
                     limit: int = 25,
                     offset: int = 0) -> Tuple[List[VideoImport], int]:
        queries: List[str] = []
        if status:
            queries.append(q_equal("status", status))
        if trusted_source_id:
            queries.append(q_equal("trusted_source_id", trusted_source_id))
        if series_id:
            queries.append(q_equal("detected_series_id", series_id))
        if created_after:
            queries.append(q_greater_equal("created_at", created_after))
        queries += [q_order_desc("created_at"), q_limit(limit), q_offset(max(0, offset))]
        docs, total = self._page(COL_IMPORTS, queries)
        return [_import_tu_doc(d) for d in docs], total

    def update_import(self, import_id: str, fields: Dict[str, Any]) -> VideoImport:
        data = dict(fields)
        data["updated_at"] = now_iso()
        self._update(COL_IMPORTS, import_id, data)
        return self.get_import(import_id)

    def count_sources_by_subscription_status(self) -> Dict[str, int]:
        """Bo dem nguon THEO trang thai dang ky WebSub — Phase 7 analytics
        (trang He thong: suc khoe WebSub). MOI gia tri enum MOT truy van bi
        chan rieng (Appwrite khong ho tro group-by) — CHAP NHAN DUOC vi CHI
        5 gia tri co the va CHI goi tu trang phan tich chi tiet, khong phai
        dashboard chinh (xem muc 6 handoff ve nguyen tac hieu nang)."""
        return {s.value: self._page(
            COL_SOURCES, [q_equal("subscription_status", s.value), q_limit(1)])[1]
            for s in SubscriptionStatus}

    def has_active_websub_subscription(self) -> bool:
        """
        CO it nhat MOT nguon `ACTIVE` hay khong — MOT truy van bi chan
        (`limit=1`), an toan de goi tu dashboard chinh (khac
        `count_sources_by_subscription_status` o tren, von can 5 truy van
        rieng nen CHI danh cho trang phan tich chi tiet). Xem docstring ban
        Mock (`server/trusted_source_store.py`) ve ly do can tin hieu THAT
        nay thay vi chi "da cau hinh".
        """
        _, total = self._page(
            COL_SOURCES, [q_equal("subscription_status", SubscriptionStatus.ACTIVE.value),
                         q_limit(1)])
        return total > 0


def build_trusted_source_store(settings: Any):
    """Chon kho theo `DATA_BACKEND` — cung mau voi
    `build_animation_store`. KHONG bat `AppwriteConfigError`: cau hinh sai
    phai CHET NGAY luc khoi dong, khong am tham lui ve mock."""
    from server.trusted_source_store import MockTrustedSourceStore

    if getattr(settings, "data_backend", "mock") == "appwrite":
        return AppwriteTrustedSourceStore(settings.appwrite)
    return MockTrustedSourceStore()
