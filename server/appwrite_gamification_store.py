"""
Kho ben vung tren Appwrite cho gamification (V4 visual completion, vong 3
overnight — Phan 1A).

Cung giao dien voi `MockGamificationStore` (`server/gamification_store.py`) —
`gamification_service.py` va route trong `server/main.py` KHONG biet dang
chay tren kho nao, dung y het `AppwriteTranslationStore`/`MockTranslationStore`.

BON collection RIENG, doc lap voi `tts_jobs`/`novels`/`profiles`/`translation_*`:
`user_progress`, `xp_ledger`, `achievement_unlocks`, `cosmetic_inventory` — da
co trong `scripts/setup_appwrite.py` (dry-run xac nhan additive tu vong 2).

IDEMPOTENT QUA RESTART/NHIEU WORKER: ba loai ban ghi (XP event, thanh tuu mo
khoa, vat pham kho) dung documentId TAT DINH (`gamification.id_xp_entry` /
`id_mo_khoa_thanh_tuu` / `id_vat_pham_kho` — sha256, KHONG dung `hash()` cua
Python vi ham do bi "muoi" ngau nhien theo tien trinh). Ghi lai lan hai voi
cung id se bi Appwrite tu choi (409 -> `NotFoundError` qua `_call`), va ham
kho bat loi do de tra ve y nghia "da co roi" giong het `MockGamificationStore`
— KHONG doc-truoc-roi-ghi (tranh dua giua hai request/worker cung luc).
"""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, List, Optional, Set

import httpx

from server.adapters import NotFoundError
from server.config import AppwriteSettings
from server.gamification import id_mo_khoa_thanh_tuu, id_vat_pham_kho
from server.gamification_domain import (
    CosmeticInventoryItem,
    UnlockedAchievement,
    UserProgress,
    XpLedgerEntry,
)

COL_PROGRESS = "user_progress"
COL_XP_LEDGER = "xp_ledger"
COL_ACHIEVEMENT_UNLOCKS = "achievement_unlocks"
COL_COSMETIC_INVENTORY = "cosmetic_inventory"

#: Ten thuoc tinh THAT SU muon luu — cung vai tro voi `_PERSISTED_FIELDS` o
#: `appwrite_translation_store.py`. Phai KHOP CHINH XAC voi SCHEMA trong
#: `scripts/setup_appwrite.py` (xem cac collection cung ten o do).
_PERSISTED_FIELDS: Dict[str, tuple] = {
    COL_PROGRESS: (
        "user_id", "xp", "equipped_title_key", "pending_reward_packs",
        "updated_at",
    ),
    COL_XP_LEDGER: (
        "entry_id", "user_id", "event_type", "source_kind", "source_id",
        "xp_awarded", "created_at",
    ),
    COL_ACHIEVEMENT_UNLOCKS: (
        "user_id", "achievement_key", "unlocked_at",
    ),
    COL_COSMETIC_INVENTORY: (
        "user_id", "cosmetic_key", "acquired_at", "equipped",
    ),
}

REQUEST_TIMEOUT = 30.0
PAGE_SIZE = 100


def q_equal(attribute: str, *values: Any) -> str:
    return json.dumps({"method": "equal", "attribute": attribute,
                       "values": list(values)})


def q_order_asc(attribute: str) -> str:
    return json.dumps({"method": "orderAsc", "attribute": attribute})


def q_limit(count: int) -> str:
    return json.dumps({"method": "limit", "values": [int(count)]})


def q_offset(count: int) -> str:
    return json.dumps({"method": "offset", "values": [int(count)]})


def _progress_to_row(p: UserProgress) -> Dict[str, Any]:
    return {
        "user_id": p.user_id,
        "xp": p.xp,
        "equipped_title_key": p.equipped_title_key,
        "pending_reward_packs": p.goi_thuong_dang_cho,
        "updated_at": p.updated_at,
    }


def _progress_from_row(row: Dict[str, Any]) -> UserProgress:
    return UserProgress(
        user_id=str(row.get("user_id") or ""),
        xp=int(row.get("xp") or 0),
        equipped_title_key=str(row.get("equipped_title_key") or ""),
        goi_thuong_dang_cho=int(row.get("pending_reward_packs") or 0),
        updated_at=str(row.get("updated_at") or ""),
    )


def _xp_entry_to_row(e: XpLedgerEntry) -> Dict[str, Any]:
    return {
        "entry_id": e.entry_id,
        "user_id": e.user_id,
        "event_type": e.event_type,
        "source_kind": e.source_kind,
        "source_id": e.source_id,
        "xp_awarded": e.xp_awarded,
        "created_at": e.created_at,
    }


def _xp_entry_from_row(row: Dict[str, Any]) -> XpLedgerEntry:
    return XpLedgerEntry(
        entry_id=str(row.get("entry_id") or row.get("$id") or ""),
        user_id=str(row.get("user_id") or ""),
        event_type=str(row.get("event_type") or ""),
        source_kind=str(row.get("source_kind") or ""),
        source_id=str(row.get("source_id") or ""),
        xp_awarded=int(row.get("xp_awarded") or 0),
        created_at=str(row.get("created_at") or ""),
    )


def _achievement_to_row(a: UnlockedAchievement) -> Dict[str, Any]:
    return {
        "user_id": a.user_id,
        "achievement_key": a.achievement_key,
        "unlocked_at": a.unlocked_at,
    }


def _achievement_from_row(row: Dict[str, Any]) -> UnlockedAchievement:
    return UnlockedAchievement(
        user_id=str(row.get("user_id") or ""),
        achievement_key=str(row.get("achievement_key") or ""),
        unlocked_at=str(row.get("unlocked_at") or ""),
    )


def _cosmetic_to_row(c: CosmeticInventoryItem) -> Dict[str, Any]:
    return {
        "user_id": c.user_id,
        "cosmetic_key": c.cosmetic_key,
        "acquired_at": c.acquired_at,
        "equipped": c.equipped,
    }


def _cosmetic_from_row(row: Dict[str, Any]) -> CosmeticInventoryItem:
    return CosmeticInventoryItem(
        user_id=str(row.get("user_id") or ""),
        cosmetic_key=str(row.get("cosmetic_key") or ""),
        acquired_at=str(row.get("acquired_at") or ""),
        equipped=bool(row.get("equipped") or False),
    )


class AppwriteGamificationStore:
    """Ban Appwrite cua `MockGamificationStore` — cung giao dien, KHAC ha tang."""

    mode = "appwrite"

    def __init__(self, settings: AppwriteSettings, client: Any = None):
        """:param client: tiem client gia lap cho test hop dong (xem
        `test_gamification_contract.py`), thay vi mo ket noi httpx that."""
        from server.appwrite_adapter import AppwriteConfigError

        if not settings.configured:
            raise AppwriteConfigError(
                "Cấu hình Appwrite chưa đủ cho kho gamification. Cần cả bốn "
                "biến APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, "
                "APPWRITE_API_KEY, APPWRITE_DATABASE_ID.")
        self._settings = settings
        self._endpoint = settings.api_base
        self._db = settings.database_id
        self._client = client
        self._attrs_cache: Dict[str, Set[str]] = {}
        self._pool: Optional[httpx.Client] = None
        #: Khoa CUC BO — chi bao ve viec doc `_attrs_cache` tu nhieu luong
        #: trong CUNG mot tien trinh; idempotency THAT giua nhieu tien trinh/
        #: worker den tu documentId tat dinh + Appwrite tu choi trung id.
        self._lock = threading.RLock()

    # -- ha tang REST — GIONG HET AppwriteTranslationStore, xem ghi chu o do -----

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
            message = f"Appwrite trả về lỗi {response.status_code}."
            try:
                body = response.json()
                if isinstance(body, dict) and body.get("message"):
                    message = str(body["message"])
            except Exception:
                pass
            raise NotFoundError(message)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def _docs(self, collection: str) -> str:
        return f"/v1/databases/{self._db}/collections/{collection}/documents"

    @staticmethod
    def _owner_permissions(user_id: str) -> List[str]:
        # CHI DOC cho chinh chu — moi ghi di qua backend bang API key, cung
        # nguyen tac voi cac kho Appwrite khac trong kho nay.
        return [f'read("user:{user_id}")'] if user_id else []

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
               user_id: str) -> Dict[str, Any]:
        return self._call("POST", self._docs(collection), payload={
            "documentId": doc_id,
            "data": self._writable(collection, data),
            "permissions": self._owner_permissions(user_id),
        })

    def _get(self, collection: str, doc_id: str) -> Dict[str, Any]:
        return self._call("GET", f"{self._docs(collection)}/{doc_id}")

    def _update(self, collection: str, doc_id: str,
               data: Dict[str, Any]) -> Dict[str, Any]:
        return self._call("PATCH", f"{self._docs(collection)}/{doc_id}",
                          payload={"data": self._writable(collection, data)})

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

    # ======================================================== cap do / XP

    def get_progress(self, user_id: str) -> UserProgress:
        try:
            row = self._get(COL_PROGRESS, user_id)
        except NotFoundError:
            return UserProgress(user_id=user_id)
        return _progress_from_row(row)

    def save_progress(self, progress: UserProgress) -> UserProgress:
        """Upsert THAT: thu tao truoc (documentId = user_id, MOT hang moi
        nguoi dung), khong duoc (409 -> NotFoundError) thi cap nhat — cung ky
        thuat voi `AppwriteTranslationStore.save_connection`."""
        row = _progress_to_row(progress)
        try:
            self._create(COL_PROGRESS, progress.user_id, row, progress.user_id)
        except NotFoundError:
            self._update(COL_PROGRESS, progress.user_id, row)
        return progress

    def record_xp_event(self, entry: XpLedgerEntry) -> bool:
        """Tra `False` (khong ghi gi) neu `entry_id` da co — Appwrite tu choi
        tao hang trung id (409), va ta doc dieu do la "da cong roi", KHONG
        phai loi that. `entry_id` la sha256 tat dinh cua (user_id, event_type,
        source_id) nen ket qua giong het `MockGamificationStore` ke ca sau
        restart hoac tren worker khac (xem `gamification.id_xp_entry`)."""
        try:
            self._create(COL_XP_LEDGER, entry.entry_id, _xp_entry_to_row(entry),
                        entry.user_id)
        except NotFoundError:
            return False
        return True

    def list_xp_events(self, user_id: str) -> List[XpLedgerEntry]:
        rows = self._list_all(COL_XP_LEDGER, [q_equal("user_id", user_id)])
        ds = [_xp_entry_from_row(r) for r in rows]
        return sorted(ds, key=lambda e: e.created_at)

    # ======================================================== thanh tuu

    def list_unlocked_achievements(self, user_id: str) -> List[UnlockedAchievement]:
        rows = self._list_all(COL_ACHIEVEMENT_UNLOCKS,
                              [q_equal("user_id", user_id)])
        return [_achievement_from_row(r) for r in rows]

    def unlock_achievement(self, record: UnlockedAchievement) -> bool:
        """Tra `False` neu thanh tuu nay DA mo khoa — cung ky thuat voi
        `record_xp_event`: documentId tat dinh
        (`gamification.id_mo_khoa_thanh_tuu`), Appwrite tu choi hang trung."""
        muon_id = id_mo_khoa_thanh_tuu(record.user_id, record.achievement_key)
        try:
            self._create(COL_ACHIEVEMENT_UNLOCKS, muon_id,
                        _achievement_to_row(record), record.user_id)
        except NotFoundError:
            return False
        return True

    # ======================================================== vat pham

    def list_cosmetics(self, user_id: str) -> List[CosmeticInventoryItem]:
        rows = self._list_all(COL_COSMETIC_INVENTORY,
                              [q_equal("user_id", user_id)])
        return [_cosmetic_from_row(r) for r in rows]

    def get_cosmetic(self, user_id: str,
                     cosmetic_key: str) -> Optional[CosmeticInventoryItem]:
        muon_id = id_vat_pham_kho(user_id, cosmetic_key)
        try:
            row = self._get(COL_COSMETIC_INVENTORY, muon_id)
        except NotFoundError:
            return None
        item = _cosmetic_from_row(row)
        return item if item.user_id == user_id else None

    def grant_cosmetic(self, item: CosmeticInventoryItem) -> Optional[CosmeticInventoryItem]:
        """Tra `None` neu nguoi dung DA CO vat pham nay — documentId tat dinh
        (`gamification.id_vat_pham_kho`) khien lan rut trung tu nhien khong
        tao ban sao, giong het `MockGamificationStore.grant_cosmetic`."""
        muon_id = id_vat_pham_kho(item.user_id, item.cosmetic_key)
        try:
            self._create(COL_COSMETIC_INVENTORY, muon_id, _cosmetic_to_row(item),
                        item.user_id)
        except NotFoundError:
            return None
        return item

    def set_cosmetic_equipped(self, user_id: str, cosmetic_key: str,
                              equipped: bool) -> None:
        muon_id = id_vat_pham_kho(user_id, cosmetic_key)
        current = self.get_cosmetic(user_id, cosmetic_key)
        if current is None:
            raise NotFoundError("Bạn chưa có vật phẩm này.")
        self._update(COL_COSMETIC_INVENTORY, muon_id, {"equipped": equipped})


def build_gamification_store(settings: Any):
    """
    Chon kho gamification theo `DATA_BACKEND` — CUNG MAU va CUNG NGUYEN TAC
    voi `translation_store.build_translation_store`: `settings` la `Settings`
    cap cao nhat (tu `get_settings()`), khong phai `AppwriteSettings`.

    Part L (nhac lai o day vi day la lan dau kho nay THAT SU co the chon
    Appwrite): "khong bao gio am tham lui ve bo nho khi da cau hinh dung ben
    vung". KHONG bat `AppwriteConfigError` o day — `DATA_BACKEND=appwrite` ma
    thieu bien cau hinh PHAI CHET NGAY luc khoi dong server, khong duoc chay
    tiep roi ngo la du lieu gamification duoc luu that trong khi thuc te moi
    lan restart la mat sach.

    Truoc ban nay (vong 2), ham cung ten trong `gamification_store.py` LUON
    tra Mock bat ke cau hinh, vi chua co ban Appwrite. Gio `server/main.py`
    import ham NAY thay vi ban cu.
    """
    from server.gamification_store import MockGamificationStore

    if getattr(settings, "data_backend", "mock") == "appwrite":
        return AppwriteGamificationStore(settings.appwrite)
    return MockGamificationStore()
