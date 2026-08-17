"""
Kho Animation ben vung tren Appwrite (V6, overnight Phase 5).

Cung giao dien voi `MockAnimationStore` (`server/animation_store.py`) —
route trong `server/main.py` KHONG biet dang chay tren kho nao, dung y het
`AppwriteGamificationStore`/`MockGamificationStore`.

HAI collection RIENG, doc lap voi `novels`/`chapters`/`tts_jobs`:
`animation_series`, `animation_episodes` — da co trong
`scripts/setup_appwrite.py`.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx

from server.adapters import NotFoundError, PermissionDenied
from server.animation_domain import AnimationEpisode, AnimationSeries, AnimationSource
from server.config import AppwriteSettings
from server.secret_redaction import thong_diep_loi_an_toan
from server.domain import ContentState, PublishState, now_iso

COL_SERIES = "animation_series"
COL_EPISODES = "animation_episodes"

#: Ten thuoc tinh THAT SU muon luu — phai khop CHINH XAC voi SCHEMA trong
#: `scripts/setup_appwrite.py`. Ba truong `moderation_state`/`removed_by`/
#: `removed_reason` la THEM SAU (Phase 4, Admin Control Center V2) — ca ba
#: deu KHONG BAT BUOC trong schema, dung CUNG co che dong-thieu-thi-bo-qua
#: voi cac truong V2 cua `profiles` (xem `appwrite_adapter.py`).
_PERSISTED_FIELDS: Dict[str, tuple] = {
    COL_SERIES: (
        "series_id", "owner_id", "title", "description", "cover_key",
        "state", "tags", "related_novel_id", "moderation_state",
        "removed_by", "removed_reason", "created_at", "updated_at",
    ),
    COL_EPISODES: (
        "episode_id", "series_id", "owner_id", "title", "source",
        "external_id", "order_index", "state", "duration_seconds",
        "moderation_state", "removed_by", "removed_reason",
        "created_at", "updated_at",
    ),
}

REQUEST_TIMEOUT = 15.0
PAGE_SIZE = 100


def q_equal(attribute: str, *values: Any) -> str:
    return json.dumps({"method": "equal", "attribute": attribute,
                       "values": list(values)})


def q_order_desc(attribute: str) -> str:
    return json.dumps({"method": "orderDesc", "attribute": attribute})


def q_order_asc(attribute: str) -> str:
    return json.dumps({"method": "orderAsc", "attribute": attribute})


def q_select(*attributes: str) -> str:
    return json.dumps({"method": "select", "values": list(attributes)})


def q_equal_or_null(attribute: str, value: Any) -> str:
    """
    `attribute == value` HOAC `attribute` CHUA CO (NULL) — dung khi loc theo
    mot thuoc tinh THEM SAU (Phase 4: `moderation_state`) tren mot collection
    da co du lieu tu truoc migration.

    Series/tap TAO TRUOC Phase 4 khong co gia tri nao cho `moderation_state`
    ca (thuoc tinh khong bat buoc, moi them) — `equal("moderation_state",
    "visible")` KHONG khop NULL, nen loc rieng "visible" se lam BIEN MAT moi
    ban ghi cu khoi thu vien cong khai. Cung ly do va cung cach lam voi
    `list_comments_all`'s xu ly `target_kind` cu (xem `appwrite_social.py`).
    """
    return json.dumps({"method": "or", "values": [
        {"method": "equal", "attribute": attribute, "values": [value]},
        {"method": "isNull", "attribute": attribute},
    ]})


def q_limit(count: int) -> str:
    return json.dumps({"method": "limit", "values": [int(count)]})


def q_offset(count: int) -> str:
    return json.dumps({"method": "offset", "values": [int(count)]})


def q_contains(attribute: str, value: Any) -> Dict[str, Any]:
    return {"method": "contains", "attribute": attribute, "values": [value]}


def _moderation_state_from_doc(doc: Dict[str, Any]) -> ContentState:
    """`None`/thieu (hang TAO TRUOC Phase 4) -> VISIBLE, giu nguyen hien
    trang cong khai cua du lieu cu. Xem `q_equal_or_null`."""
    try:
        return ContentState(str(doc.get("moderation_state") or "visible"))
    except ValueError:
        return ContentState.VISIBLE


def _publish_state_from_doc(doc: Dict[str, Any]) -> PublishState:
    """Gia tri la/hong -> DRAFT thay vi nem `ValueError` — cung ly do voi
    `_moderation_state_from_doc` o tren."""
    try:
        return PublishState(str(doc.get("state") or "draft"))
    except ValueError:
        return PublishState.DRAFT


def _series_from_doc(doc: Dict[str, Any]) -> AnimationSeries:
    return AnimationSeries(
        series_id=str(doc.get("series_id") or doc.get("$id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        title=str(doc.get("title") or ""),
        description=str(doc.get("description") or ""),
        cover_key=doc.get("cover_key"),
        state=_publish_state_from_doc(doc),
        tags=list(doc.get("tags") or []),
        related_novel_id=str(doc.get("related_novel_id") or ""),
        moderation_state=_moderation_state_from_doc(doc),
        removed_by=str(doc.get("removed_by") or ""),
        removed_reason=str(doc.get("removed_reason") or ""),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
    )


def _episode_from_doc(doc: Dict[str, Any]) -> AnimationEpisode:
    try:
        source = AnimationSource(str(doc.get("source") or "youtube"))
    except ValueError:
        source = AnimationSource.YOUTUBE
    return AnimationEpisode(
        episode_id=str(doc.get("episode_id") or doc.get("$id") or ""),
        series_id=str(doc.get("series_id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        title=str(doc.get("title") or ""),
        source=source,
        external_id=str(doc.get("external_id") or ""),
        order_index=int(doc.get("order_index") or 1),
        state=_publish_state_from_doc(doc),
        duration_seconds=float(doc.get("duration_seconds") or 0.0),
        moderation_state=_moderation_state_from_doc(doc),
        removed_by=str(doc.get("removed_by") or ""),
        removed_reason=str(doc.get("removed_reason") or ""),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
    )


class AppwriteAnimationStore:
    """Ban Appwrite cua `MockAnimationStore` — cung giao dien, KHAC ha tang."""

    mode = "appwrite"

    def __init__(self, settings: AppwriteSettings, client: Any = None):
        from server.appwrite_adapter import AppwriteConfigError

        if not settings.configured:
            raise AppwriteConfigError(
                "Cấu hình Appwrite chưa đủ cho kho Animation. Cần cả bốn biến "
                "APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY, "
                "APPWRITE_DATABASE_ID.")
        self._settings = settings
        self._endpoint = settings.api_base
        self._db = settings.database_id
        self._client = client
        self._attrs_cache: Dict[str, Set[str]] = {}
        self._pool: Optional[httpx.Client] = None
        self._lock = threading.RLock()

    # -- ha tang REST — giong het AppwriteGamificationStore, xem ghi chu o do --

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
            raise NotFoundError("Không tìm thấy bản ghi.")
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

    @staticmethod
    def _owner_permissions(owner_id: str, public_read: bool = False) -> List[str]:
        """
        Quyen tren document: CHI DOC, cung nguyen tac voi
        `AppwriteMetadataStore._owner_permissions` — moi thao tac GHI deu di
        qua backend bang API key (bo qua document permission), nen khong cap
        `update`/`delete` cho ai ca, ke ca chu so huu. Xem ghi chu day du o
        `appwrite_store.py`.

        `public_read` chi dung cho `animation_series` (mo sau khi xuat ban,
        cung mau voi `novels`) — `animation_episodes` KHONG bao gio dung tham
        so nay: hien thi cua mot tap phu thuoc trang thai SERIES cha, duoc
        gac o tang route (giong `chapters` phu thuoc `novels`), khong phai o
        quyen document.
        """
        perms = [f'read("user:{owner_id}")'] if owner_id else []
        if public_read:
            perms.append('read("any")')
        return perms

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
        available = self._supported_fields(collection)
        if available is None:
            return fields
        return {k: v for k, v in fields.items() if k in available}

    def _create(self, collection: str, doc_id: str, data: Dict[str, Any],
               permissions: List[str]) -> Dict[str, Any]:
        return self._call("POST", self._docs(collection), payload={
            "documentId": doc_id,
            "data": self._writable(collection, data),
            "permissions": permissions,
        })

    def _get(self, collection: str, doc_id: str) -> Dict[str, Any]:
        return self._call("GET", f"{self._docs(collection)}/{doc_id}")

    def _update(self, collection: str, doc_id: str, data: Dict[str, Any],
               permissions: Optional[List[str]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"data": self._writable(collection, data)}
        if permissions is not None:
            payload["permissions"] = permissions
        return self._call("PATCH", f"{self._docs(collection)}/{doc_id}", payload=payload)

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

    # -- series ---------------------------------------------------------------

    def create_series(self, series: AnimationSeries) -> AnimationSeries:
        self._create(COL_SERIES, series.series_id, series.to_dict(),
                    self._owner_permissions(series.owner_id, public_read=False))
        return series

    def get_series(self, series_id: str) -> AnimationSeries:
        return _series_from_doc(self._get(COL_SERIES, series_id))

    def owned_series(self, series_id: str, owner_id: str) -> AnimationSeries:
        series = self.get_series(series_id)
        if series.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu series này.")
        return series

    def find_series(self, owner_id: Optional[str] = None,
                    published_only: bool = False, query: str = "",
                    tag: str = "", limit: Optional[int] = None,
                    offset: int = 0, state: str = "",
                    include_removed: bool = False,
                    sort: str = "newest") -> Tuple[List[AnimationSeries], int]:
        """Xem docstring day du o `MockAnimationStore.find_series` — CUNG
        hop dong, `state`/`include_removed`/`sort` la mo rong Phase 4."""
        queries: List[str] = []
        if owner_id:
            queries.append(q_equal("owner_id", owner_id))
        if state:
            queries.append(q_equal("state", state))
        elif published_only:
            queries.append(q_equal("state", "published"))
        if not include_removed:
            queries.append(q_equal_or_null("moderation_state", "visible"))
        needle = query.strip()
        if tag and needle:
            queries.append(json.dumps({"method": "or", "values": [
                q_contains("tags", tag), q_contains("title", needle),
                q_contains("description", needle)]}))
        elif tag:
            queries.append(q_contains("tags", tag))
        elif needle:
            queries.append(json.dumps({"method": "or", "values": [
                q_contains("title", needle), q_contains("description", needle)]}))
        queries.append(q_order_asc("created_at") if sort == "oldest"
                       else q_order_desc("created_at"))

        if limit is None:
            items = [_series_from_doc(d) for d in self._list_all(COL_SERIES, queries)]
            return items, len(items)
        docs, total = self._page(COL_SERIES, queries + [
            q_limit(limit), q_offset(max(0, offset))])
        return [_series_from_doc(d) for d in docs], total

    def episode_counts(self, series_ids: Sequence[str]) -> Dict[str, int]:
        """So tap cua nhieu series, MOT truy van moi lo 50 — cung idiom voi
        `AppwriteMetadataStore.chapter_counts` (khong N+1)."""
        ds = [s for s in dict.fromkeys(series_ids) if s]
        dem = {sid: 0 for sid in ds}
        for i in range(0, len(ds), 50):
            lo = ds[i:i + 50]
            for row in self._list_all(COL_EPISODES, [
                    q_equal("series_id", *lo), q_select("series_id")]):
                sid = str(row.get("series_id") or "")
                if sid in dem:
                    dem[sid] += 1
        return dem

    def get_series_by_ids(self, series_ids: Sequence[str]) -> Dict[str, AnimationSeries]:
        """Nhieu series theo ID, MOT truy van moi lo 50 — tranh N+1 khi lam
        giau danh sach quan tri (Trusted Sources/Import Queue, Phase 5 hieu
        nang: truoc day moi ID rieng le goi `get_series` MOT truy van HTTP
        rieng). Loc theo `$id` (KHONG can chi muc rieng): `create_series`
        dung thang `series.series_id` lam ID tai lieu Appwrite, nen `$id`
        va `series_id` LUON trung nhau — xem `create_series` o tren."""
        ds = [s for s in dict.fromkeys(series_ids) if s]
        ra: Dict[str, AnimationSeries] = {}
        for i in range(0, len(ds), 50):
            lo = ds[i:i + 50]
            for row in self._list_all(COL_SERIES, [q_equal("$id", *lo)]):
                s = _series_from_doc(row)
                ra[s.series_id] = s
        return ra

    def series_tags(self, published_only: bool = True) -> List[str]:
        queries = [q_equal("state", "published")] if published_only else []
        docs = self._list_all(COL_SERIES, queries)
        tags = {t for d in docs for t in (d.get("tags") or []) if t}
        return sorted(tags, key=lambda t: t.casefold())

    #: Chi nhung truong nay moi cho nguoi dung sua — CUNG danh sach voi
    #: `MockAnimationStore.SERIES_EDITABLE`. `_writable()` chi loc theo SCHEMA
    #: (thu Appwrite THAT SU co), khong loc theo quyen sua cua client — thieu
    #: buoc loc nay thi `owner_id`/`state` (deu la cot hop le trong schema) se
    #: bi ghi de tuy y tu payload nguoi dung gui len.
    SERIES_EDITABLE = ("title", "description", "tags", "related_novel_id")

    def update_series(self, series_id: str, owner_id: str,
                      fields: Dict[str, Any]) -> AnimationSeries:
        self.owned_series(series_id, owner_id)
        data = {k: v for k, v in fields.items() if k in self.SERIES_EDITABLE}
        data["updated_at"] = now_iso()
        self._update(COL_SERIES, series_id, data)
        return self.get_series(series_id)

    def set_series_cover(self, series_id: str, owner_id: str,
                         cover_key: Optional[str]) -> AnimationSeries:
        self.owned_series(series_id, owner_id)
        self._update(COL_SERIES, series_id,
                     {"cover_key": cover_key, "updated_at": now_iso()})
        return self.get_series(series_id)

    def publish_series(self, series_id: str, owner_id: str) -> AnimationSeries:
        """Xuat ban: cap nhat trang thai VA mo quyen doc cong khai TRONG MOT
        PATCH — cung ky thuat va cung ly do voi `AppwriteMetadataStore.publish_novel`."""
        current = self.owned_series(series_id, owner_id)
        if current.state == PublishState.PUBLISHED:
            return current
        self._update(COL_SERIES, series_id,
                     {"state": "published", "updated_at": now_iso()},
                     permissions=self._owner_permissions(owner_id, public_read=True))
        return self.get_series(series_id)

    def unpublish_series(self, series_id: str, owner_id: str) -> AnimationSeries:
        current = self.owned_series(series_id, owner_id)
        if current.state != PublishState.PUBLISHED:
            return current
        self._update(COL_SERIES, series_id,
                     {"state": "draft", "updated_at": now_iso()},
                     permissions=self._owner_permissions(owner_id, public_read=False))
        return self.get_series(series_id)

    def delete_series(self, series_id: str, owner_id: str) -> None:
        self.owned_series(series_id, owner_id)
        self._delete(COL_SERIES, series_id)

    # -- kiem duyet (Phase 4, Admin Control Center V2) -----------------------
    #
    # KHONG kiem chu so huu, KHONG dong toi `state`/quyen doc — xem docstring
    # `MockAnimationStore.admin_unpublish_series`.

    def admin_unpublish_series(self, series_id: str, *, removed_by: str,
                               reason: str = "") -> AnimationSeries:
        current = self.get_series(series_id)
        if current.moderation_state is ContentState.REMOVED:
            return current
        self._update(COL_SERIES, series_id, {
            "moderation_state": "removed", "removed_by": removed_by,
            "removed_reason": reason, "updated_at": now_iso(),
        })
        return self.get_series(series_id)

    def admin_restore_series(self, series_id: str) -> AnimationSeries:
        current = self.get_series(series_id)
        if current.moderation_state is ContentState.VISIBLE:
            return current
        self._update(COL_SERIES, series_id, {
            "moderation_state": "visible", "removed_by": "",
            "removed_reason": "", "updated_at": now_iso(),
        })
        return self.get_series(series_id)

    # -- episode ----------------------------------------------------------------

    def create_episode(self, episode: AnimationEpisode) -> AnimationEpisode:
        # KHONG bao gio `public_read=True` — xem docstring `_owner_permissions`.
        self._create(COL_EPISODES, episode.episode_id, episode.to_dict(),
                    self._owner_permissions(episode.owner_id))
        return episode

    def get_episode(self, episode_id: str) -> AnimationEpisode:
        return _episode_from_doc(self._get(COL_EPISODES, episode_id))

    def episodes_by_external_ids(
        self, external_ids: Sequence[str]) -> Dict[str, AnimationEpisode]:
        """Xem docstring o `MockAnimationStore.episodes_by_external_ids` —
        MOT truy van moi lo 50, dung index `external_id_idx` (xem
        `scripts/setup_appwrite.py`)."""
        ds = [e for e in dict.fromkeys(external_ids) if e]
        ra: Dict[str, AnimationEpisode] = {}
        for i in range(0, len(ds), 50):
            lo = ds[i:i + 50]
            for row in self._list_all(COL_EPISODES, [q_equal("external_id", *lo)]):
                ep = _episode_from_doc(row)
                ra[ep.external_id] = ep
        return ra

    def owned_episode(self, episode_id: str, owner_id: str) -> AnimationEpisode:
        episode = self.get_episode(episode_id)
        if episode.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu tập này.")
        return episode

    def list_episodes(self, series_id: str,
                      include_removed: bool = False) -> List[AnimationEpisode]:
        queries = [q_equal("series_id", series_id)]
        if not include_removed:
            queries.append(q_equal_or_null("moderation_state", "visible"))
        docs = self._list_all(COL_EPISODES, queries)
        items = [_episode_from_doc(d) for d in docs]
        items.sort(key=lambda e: e.order_index)
        return items

    def total_episodes(self) -> int:
        """Tong so tap TREN TOAN NEN TANG — bang dieu khien quan tri (Admin
        Control Center V2, A1). `limit(1)` + doc `total`, KHONG vong lap tren
        tung series (do se la N+1)."""
        return self._page(COL_EPISODES, [q_limit(1)])[1]

    #: Cung danh sach voi `MockAnimationStore.EPISODE_EDITABLE` — xem ghi chu
    #: o `SERIES_EDITABLE` ve vi sao buoc loc nay khong duoc bo qua.
    EPISODE_EDITABLE = ("title", "external_id", "order_index", "duration_seconds")

    def update_episode(self, episode_id: str, owner_id: str,
                       fields: Dict[str, Any]) -> AnimationEpisode:
        self.owned_episode(episode_id, owner_id)
        data = {k: v for k, v in fields.items() if k in self.EPISODE_EDITABLE}
        data["updated_at"] = now_iso()
        self._update(COL_EPISODES, episode_id, data)
        return self.get_episode(episode_id)

    def delete_episode(self, episode_id: str, owner_id: str) -> None:
        self.owned_episode(episode_id, owner_id)
        self._delete(COL_EPISODES, episode_id)

    # -- kiem duyet (Phase 4) — xem ghi chu o khoi tuong ung cua series ------

    def admin_unpublish_episode(self, episode_id: str, *, removed_by: str,
                                reason: str = "") -> AnimationEpisode:
        current = self.get_episode(episode_id)
        if current.moderation_state is ContentState.REMOVED:
            return current
        self._update(COL_EPISODES, episode_id, {
            "moderation_state": "removed", "removed_by": removed_by,
            "removed_reason": reason, "updated_at": now_iso(),
        })
        return self.get_episode(episode_id)

    def admin_restore_episode(self, episode_id: str) -> AnimationEpisode:
        current = self.get_episode(episode_id)
        if current.moderation_state is ContentState.VISIBLE:
            return current
        self._update(COL_EPISODES, episode_id, {
            "moderation_state": "visible", "removed_by": "",
            "removed_reason": "", "updated_at": now_iso(),
        })
        return self.get_episode(episode_id)

    def reorder_episodes(self, series_id: str, owner_id: str,
                         episode_ids: Sequence[str]) -> List[AnimationEpisode]:
        self.owned_series(series_id, owner_id)
        current_items = self.list_episodes(series_id)
        current = {e.episode_id for e in current_items}
        wanted = list(dict.fromkeys(episode_ids))
        if set(wanted) != current or len(wanted) != len(episode_ids):
            raise ValueError(
                "Danh sách thứ tự phải gồm đúng các tập của series này.")
        for position, episode_id in enumerate(wanted, start=1):
            self._update(COL_EPISODES, episode_id, {"order_index": position})
        return self.list_episodes(series_id)


def build_animation_store(settings: Any):
    """
    Chon kho Animation theo `DATA_BACKEND` — cung mau voi
    `appwrite_gamification_store.build_gamification_store`.

    KHONG bat `AppwriteConfigError` o day: `DATA_BACKEND=appwrite` ma thieu
    bien cau hinh PHAI CHET NGAY luc khoi dong server.
    """
    from server.animation_store import MockAnimationStore

    if getattr(settings, "data_backend", "mock") == "appwrite":
        return AppwriteAnimationStore(settings.appwrite)
    return MockAnimationStore()
