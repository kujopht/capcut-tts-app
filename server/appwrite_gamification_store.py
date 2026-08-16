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
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx

from server.adapters import NotFoundError
from server.config import AppwriteSettings
from server.secret_redaction import thong_diep_loi_an_toan
from server.gamification import (
    id_mo_khoa_thanh_tuu,
    id_tien_do_nhiem_vu,
    id_vat_pham_kho,
)
from server.gamification_domain import (
    CosmeticInventoryItem,
    QuestProgress,
    ReadingStreak,
    UnlockedAchievement,
    UserProgress,
    XpLedgerEntry,
)

COL_PROGRESS = "user_progress"
COL_XP_LEDGER = "xp_ledger"
COL_ACHIEVEMENT_UNLOCKS = "achievement_unlocks"
COL_COSMETIC_INVENTORY = "cosmetic_inventory"
#: Hai collection MOI, V4 visual completion vong 5 — xem
#: `server/gamification_domain.py` (ReadingStreak/QuestProgress).
COL_READING_STREAKS = "reading_streaks"
COL_QUEST_PROGRESS = "quest_progress"

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
    COL_READING_STREAKS: (
        "user_id", "current_streak", "longest_streak", "last_read_date",
        "grace_used_this_run", "updated_at",
    ),
    COL_QUEST_PROGRESS: (
        "user_id", "quest_key", "period_key", "count", "claimed", "updated_at",
    ),
}

REQUEST_TIMEOUT = 30.0
PAGE_SIZE = 100


def q_equal(attribute: str, *values: Any) -> str:
    return json.dumps({"method": "equal", "attribute": attribute,
                       "values": list(values)})


def q_greater(attribute: str, value: Any) -> str:
    return json.dumps({"method": "greaterThan", "attribute": attribute,
                       "values": [value]})


def q_greater_equal(attribute: str, value: Any) -> str:
    return json.dumps({"method": "greaterThanEqual", "attribute": attribute,
                       "values": [value]})


def q_order_asc(attribute: str) -> str:
    return json.dumps({"method": "orderAsc", "attribute": attribute})


def q_order_desc(attribute: str) -> str:
    return json.dumps({"method": "orderDesc", "attribute": attribute})


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


def _streak_to_row(s: ReadingStreak) -> Dict[str, Any]:
    return {
        "user_id": s.user_id,
        "current_streak": s.current_streak,
        "longest_streak": s.longest_streak,
        "last_read_date": s.last_read_date,
        "grace_used_this_run": s.grace_used_this_run,
        "updated_at": s.updated_at,
    }


def _streak_from_row(row: Dict[str, Any]) -> ReadingStreak:
    return ReadingStreak(
        user_id=str(row.get("user_id") or ""),
        current_streak=int(row.get("current_streak") or 0),
        longest_streak=int(row.get("longest_streak") or 0),
        last_read_date=str(row.get("last_read_date") or ""),
        grace_used_this_run=bool(row.get("grace_used_this_run") or False),
        updated_at=str(row.get("updated_at") or ""),
    )


def _quest_to_row(q: QuestProgress) -> Dict[str, Any]:
    return {
        "user_id": q.user_id,
        "quest_key": q.quest_key,
        "period_key": q.period_key,
        "count": q.count,
        "claimed": q.claimed,
        "updated_at": q.updated_at,
    }


def _quest_from_row(row: Dict[str, Any]) -> QuestProgress:
    return QuestProgress(
        user_id=str(row.get("user_id") or ""),
        quest_key=str(row.get("quest_key") or ""),
        period_key=str(row.get("period_key") or ""),
        count=int(row.get("count") or 0),
        claimed=bool(row.get("claimed") or False),
        updated_at=str(row.get("updated_at") or ""),
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

    def _page(self, collection: str,
             queries: List[str]) -> Tuple[List[Dict[str, Any]], int]:
        """MOT trang (khong lat het) — kem `total` Appwrite tra ve, dung cho
        bang xep hang: `total` la so KHOP TOAN BO ke ca ngoai trang, khong
        can doc het moi hang de dem."""
        data = self._call("GET", self._docs(collection), params={"queries[]": queries})
        return list(data.get("documents") or []), int(data.get("total") or 0)

    def _count(self, collection: str, queries: List[str]) -> int:
        """So hang KHOP — muon MOT gia tri `total`, khong can tai du lieu:
        `q_limit(1)` de Appwrite khong tra ve nhieu hon can, `total` van la
        so khop THAT SU ke ca ngoai gioi han do."""
        _, tong = self._page(collection, queries + [q_limit(1)])
        return tong

    # ======================================================== cap do / XP

    def get_progress(self, user_id: str) -> UserProgress:
        try:
            row = self._get(COL_PROGRESS, user_id)
        except NotFoundError:
            return UserProgress(user_id=user_id)
        return _progress_from_row(row)

    def get_progress_by_ids(self, user_ids: Sequence[str]) -> Dict[str, UserProgress]:
        """Ban HANG LOAT — MOT truy van `equal("user_id", [...])`, khong
        phai N truy van rieng. Xem `MockGamificationStore.get_progress_by_ids`."""
        ids = [u for u in user_ids if u]
        if not ids:
            return {}
        rows = self._list_all(COL_PROGRESS, [q_equal("user_id", *ids)])
        return {str(r.get("user_id")): _progress_from_row(r) for r in rows}

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

    def list_cosmetics_by_ids(
            self, user_ids: Sequence[str]) -> Dict[str, List[CosmeticInventoryItem]]:
        """Ban HANG LOAT — MOT truy van `equal("user_id", [...])` cho ca danh
        sach (Appwrite khop OR tren nhieu gia tri), khong phai N truy van rieng.
        Xem `MockGamificationStore.list_cosmetics_by_ids`."""
        ids = [u for u in user_ids if u]
        if not ids:
            return {}
        rows = self._list_all(COL_COSMETIC_INVENTORY, [q_equal("user_id", *ids)])
        ra: Dict[str, List[CosmeticInventoryItem]] = {}
        for row in rows:
            item = _cosmetic_from_row(row)
            ra.setdefault(item.user_id, []).append(item)
        return ra

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

    # ======================================================== chuoi ngay doc

    def get_streak(self, user_id: str) -> ReadingStreak:
        try:
            row = self._get(COL_READING_STREAKS, user_id)
        except NotFoundError:
            return ReadingStreak(user_id=user_id)
        return _streak_from_row(row)

    def save_streak(self, streak: ReadingStreak) -> ReadingStreak:
        """Upsert THAT — documentId = user_id (MOT hang moi nguoi dung),
        cung ky thuat voi `save_progress`."""
        row = _streak_to_row(streak)
        try:
            self._create(COL_READING_STREAKS, streak.user_id, row, streak.user_id)
        except NotFoundError:
            self._update(COL_READING_STREAKS, streak.user_id, row)
        return streak

    # ======================================================== nhiem vu

    def get_quest_progress(self, user_id: str, quest_key: str,
                           period_key: str) -> QuestProgress:
        muon_id = id_tien_do_nhiem_vu(user_id, quest_key, period_key)
        try:
            row = self._get(COL_QUEST_PROGRESS, muon_id)
        except NotFoundError:
            return QuestProgress(user_id=user_id, quest_key=quest_key,
                                 period_key=period_key)
        return _quest_from_row(row)

    def save_quest_progress(self, progress: QuestProgress) -> QuestProgress:
        """Upsert qua documentId TAT DINH (`id_tien_do_nhiem_vu`) — MOT hang
        moi (user_id, quest_key, period_key), cung ky thuat voi cac ham
        `save_*`/`grant_*` khac trong tep nay."""
        muon_id = id_tien_do_nhiem_vu(
            progress.user_id, progress.quest_key, progress.period_key)
        row = _quest_to_row(progress)
        try:
            self._create(COL_QUEST_PROGRESS, muon_id, row, progress.user_id)
        except NotFoundError:
            self._update(COL_QUEST_PROGRESS, muon_id, row)
        return progress

    def list_quest_progress(self, user_id: str) -> List[QuestProgress]:
        rows = self._list_all(COL_QUEST_PROGRESS, [q_equal("user_id", user_id)])
        return [_quest_from_row(r) for r in rows]

    # ======================================================== bang xep hang

    def list_all_progress_ranked(
            self, limit: int, offset: int) -> Tuple[List[UserProgress], int]:
        """Trang XP toan thoi gian, MAY CHU sap xep+phan trang (`orderDesc`
        + `limit`/`offset`) — khong tai ca bang ve roi sap o Python."""
        docs, tong = self._page(COL_PROGRESS, [
            q_order_desc("xp"), q_limit(max(0, limit)), q_offset(max(0, offset))])
        return [_progress_from_row(d) for d in docs], tong

    def count_users_above_xp(self, xp: int) -> int:
        """Dung `total` cua Appwrite (xem `_count`) — KHONG tai ve tung
        nguoi dung co XP cao hon chi de dem so luong."""
        return self._count(COL_PROGRESS, [q_greater("xp", xp)])

    def xp_earned_since(self, since_iso: str) -> Dict[str, int]:
        """Tong XP tu `since_iso` — quet toan bo nhat ky XP tu moc do
        (`_list_all`, bi chan boi mot moc thoi gian nen KHONG phai quet vo
        han), roi cong don theo nguoi dung o Python. Xem ghi chu day du o
        `MockGamificationStore.xp_earned_since`."""
        rows = self._list_all(
            COL_XP_LEDGER, [q_greater_equal("created_at", since_iso)])
        ra: Dict[str, int] = {}
        for row in rows:
            entry = _xp_entry_from_row(row)
            ra[entry.user_id] = ra.get(entry.user_id, 0) + entry.xp_awarded
        return ra


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
