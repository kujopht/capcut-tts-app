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

import hashlib
import json
import threading
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx

from server.adapters import AppwriteUnavailableError, NotFoundError, raise_for_appwrite_404
from server.config import AppwriteSettings
from server.domain import now_iso
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
    bao_cao_xoa_gamification,
)

COL_PROGRESS = "user_progress"
COL_XP_LEDGER = "xp_ledger"
COL_ACHIEVEMENT_UNLOCKS = "achievement_unlocks"
COL_COSMETIC_INVENTORY = "cosmetic_inventory"
#: Hai collection MOI, V4 visual completion vong 5 — xem
#: `server/gamification_domain.py` (ReadingStreak/QuestProgress).
COL_READING_STREAKS = "reading_streaks"
COL_QUEST_PROGRESS = "quest_progress"
#: Marker CAS cho `award_xp_atomic` — Social & Play V1 Goi C, xem docstring
#: cua ham do ve VI SAO can bang nay (khong chi transaction la du).
COL_XP_PROGRESS_CAS = "xp_progress_cas"

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


#: So lan thu toi da cua `update_progress_atomic` va thoi gian cho truoc moi lan thu lai — backoff mu
#: voi jitter DAY DU (0..tran), tran 25 ms x 2^lan, chan tren 800 ms: tong cho ky vong ~1.5 s truoc khi
#: bo cuoc, du de tach 8+ writer cung ghi MOT nguoi (moi lan thu la 3-4 luot goi Appwrite).
_SO_LAN_THU_CAS = 9


def _cho_truoc_lan_thu(attempt: int, u: float) -> float:
    """`u` trong [0, 1) — tach khoi `random` de kiem thu duoc."""
    return u * min(0.8, 0.025 * (2 ** attempt))


def xp_progress_cas_row_id(user_id: str, prior_xp: int, prior_state: str = "") -> str:
    """ID TAT DINH cho marker CAS cua `award_xp_atomic`, tu `(user_id,
    prior_xp, prior_state)` — sha256 (Appwrite id <=36 ky tu), cung ky thuat
    voi `gamification.id_xp_entry`. Hai request/worker CUNG doc thay mot
    TRANG THAI hang tien do se sinh CUNG marker id, nen chi MOT trong hai tao
    duoc hang — day la khoa chan "lost update" ma transaction MOT MINH khong
    dam bao (xem docstring `AppwriteGamificationStore.award_xp_atomic`).

    `prior_state` = `$updatedAt` cua hang tien do vua doc (Appwrite tu dat o
    MOI lan ghi; rong neu hang chua ton tai). Truoc ban sua nay khoa chi la
    `(user_id, prior_xp)`: XP tung bi GIAM (dieu chinh bu) roi quay lai dung
    gia tri cu thi marker cu da ton tai va MOI lan cong sau do deu thua commit
    mai mai — nguoi dung khong bao gio duoc cong XP nua (hoi quy:
    `test_games_appwrite_contract.test_xp_chinh_ve_gia_tri_cu_khong_lam_ket_marker`)."""
    khoa = f"{user_id}\x1f{prior_xp}\x1f{prior_state}".encode("utf-8")
    return f"xc_{hashlib.sha256(khoa).hexdigest()[:24]}"


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
            # Xem giai thich day du o `appwrite_store.py::AppwriteMetadataStore.
            # _call` (phat hien khi review PR #23, 2026-08-21) — loi TRANSPORT
            # phai la `AppwriteUnavailableError` (503, thu lai duoc), khong
            # phai `NotFoundError` (404), vi ta CHUA BIET ban ghi co ton tai
            # hay khong khi khong ket noi duoc.
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

    def _delete(self, collection: str, doc_id: str) -> None:
        self._call("DELETE", f"{self._docs(collection)}/{doc_id}")

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

    def list_xp_events_since(self, user_id: str, since_iso: str) -> List[XpLedgerEntry]:
        rows = self._list_all(COL_XP_LEDGER, [
            q_equal("user_id", user_id), q_greater_equal("created_at", since_iso)])
        ds = [_xp_entry_from_row(r) for r in rows]
        return sorted(ds, key=lambda e: e.created_at)

    #: Duong ghi tien do NGUYEN TU cho MOI writer (award_xp, claim_quest_reward, equip_title,
    #: open_reward_pack, quyet toan game). MAC DINH TAT tren Appwrite (`FAS_XP_ATOMIC`, xem
    #: `server/config.py`) cho toi khi duong nay duoc kiem tren mot project Appwrite THU NGHIEM —
    #: khi tat, `gamification_service` giu nguyen duong cu (production khong doi hanh vi).
    xp_atomic = False

    def update_progress_atomic(self, user_id: str, mutator,
                               ledger_entry: Optional[XpLedgerEntry] = None) -> Optional[UserProgress]:
        """
        Doc hang tien do -> `mutator(progress)` -> MOT transaction TablesDB gom:

        ```
        [create  xp_ledger        rowId = entry_id]              (chi khi co ledger_entry)
         update  user_progress    rowId = user_id                 (create neu chua co hang)
         create  xp_progress_cas  rowId = xc_sha256(user|prior_xp|prior_$updatedAt)
        ```

        Cung ky thuat DA DO tren Appwrite 1.9.6 boi `AppwriteMetadataStore.claim_job`: rowId duy
        nhat do database cuong che. Hang `xp_progress_cas` bien "hai writer cung doc MOT trang thai
        hang tien do" thanh "hai writer cung xin tao MOT rowId" -> chi MOT commit duoc, ke ca khi hai
        transaction KHONG chong lan (transaction mot minh chi bat xung dot dong thoi). Khoa gan voi
        TRANG THAI hang (`$updatedAt`), khong chi con so XP: XP tung bi chinh ve gia tri cu van cong
        tiep duoc (hoi quy `test_xp_chinh_ve_gia_tri_cu_khong_lam_ket_marker`).

        Thua commit (nem loi, HOAC tra ve binh thuong ma `status != "committed"`): co `ledger_entry`
        va hang so cai DA TON TAI -> "da cong roi", tra `None`; con lai -> doc lai trang thai MOI,
        goi lai `mutator`, thu lai (toi da `_SO_LAN_THU_CAS` lan, backoff mu voi jitter DAY DU) -> het
        luot: `AppwriteUnavailableError`. `mutator` phai la ham thuan theo `progress` (co the bi goi
        nhieu lan) va co the nem de huy.

        DO THAT tren Appwrite 1.9.6 + MongoDB THU (2026-09-26): XP LUON dung bang tong cac lan commit
        (khong mat, khong nhan doi — ca khi 2 TIEN TRINH cung ghi). Nhung ban cu (5 lan, cho 10-50 ms)
        de 7/24 lan ghi that bai khi 8 luong cung ghi MOT nguoi, 29/48 khi 16 luong — moi lan thu la
        3-4 luot goi Appwrite, cho qua ngan khong tach duoc cac writer. Xem `_cho_truoc_lan_thu`.
        """
        import copy
        import random
        import time

        from server.appwrite_store import TRANSACTION_TTL_SECONDS

        for attempt in range(_SO_LAN_THU_CAS):
            try:
                hang = self._get(COL_PROGRESS, user_id)
                progress = _progress_from_row(hang)
                progress_exists = True
                prior_state = str(hang.get("$updatedAt") or "")
            except NotFoundError:
                progress = UserProgress(user_id=user_id)
                progress_exists = False
                prior_state = ""
            prior_xp = progress.xp
            moi = mutator(copy.deepcopy(progress))

            operations = []
            if ledger_entry is not None:
                operations.append(
                    {"action": "create", "databaseId": self._db, "tableId": COL_XP_LEDGER,
                     "rowId": ledger_entry.entry_id,
                     "data": self._writable(COL_XP_LEDGER, _xp_entry_to_row(ledger_entry))})
            operations.append(
                {"action": "update" if progress_exists else "create",
                 "databaseId": self._db, "tableId": COL_PROGRESS, "rowId": user_id,
                 "data": self._writable(COL_PROGRESS, _progress_to_row(moi))})
            operations.append(
                {"action": "create", "databaseId": self._db, "tableId": COL_XP_PROGRESS_CAS,
                 "rowId": xp_progress_cas_row_id(user_id, prior_xp, prior_state),
                 "data": {"user_id": user_id, "prior_xp": prior_xp,
                          "entry_id": ledger_entry.entry_id if ledger_entry else "",
                          "created_at": now_iso()}})
            committed = False
            try:
                tx = self._call("POST", "/v1/tablesdb/transactions",
                                payload={"ttl": TRANSACTION_TTL_SECONDS})
                tx_id = tx["$id"]
                self._call("POST", f"/v1/tablesdb/transactions/{tx_id}/operations",
                           payload={"operations": operations})
                result = self._call("PATCH", f"/v1/tablesdb/transactions/{tx_id}",
                                    payload={"commit": True})
                committed = result.get("status") == "committed"
            except Exception:
                committed = False

            if committed:
                return moi

            # CA hai duong thua (nem loi / status != committed) di qua CUNG mot phep kiem — truoc
            # ban sua o vong review goi C, nhanh "khong nem loi" bo qua phep kiem va thu lai vo han.
            if ledger_entry is not None:
                try:
                    self._get(COL_XP_LEDGER, ledger_entry.entry_id)
                    return None  # Hang xp_ledger DA TON TAI -> da cong roi.
                except NotFoundError:
                    pass
            if attempt + 1 < _SO_LAN_THU_CAS:
                time.sleep(_cho_truoc_lan_thu(attempt, random.random()))

        raise AppwriteUnavailableError(
            "Không ghi được tiến độ XP sau nhiều lần thử — Appwrite đang xung đột.")

    def award_xp_atomic(self, entry: XpLedgerEntry) -> Optional[UserProgress]:
        """Ghi MOT entry so cai VA cong XP vao tien do trong MOT transaction — xem
        `update_progress_atomic`. Trung `entry_id` -> `None`, khong doi gi."""
        from server.gamification_store import mutator_cong_xp

        return self.update_progress_atomic(entry.user_id, mutator_cong_xp(entry), ledger_entry=entry)

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
            if entry.xp_awarded:  # hang 0 XP (vd `reward_pack_open`) — xem ban mock
                ra[entry.user_id] = ra.get(entry.user_id, 0) + entry.xp_awarded
        return ra

    # ======================================================== xoa tai khoan

    def delete_account_data(self, user_id: str) -> Dict[str, int]:
        """Xem contract o `MockGamificationStore.delete_account_data`.

        SAU collection, cung MOT phep loc `equal("user_id", ...)` — moi collection
        deu co chi muc theo `user_id` (xem `scripts/setup_appwrite.py`), nen
        khong co truy van nao o day quet toan bang.

        KHONG dung `rowId` tat dinh du biet cach tinh (`id_vat_pham_kho`,
        `id_tien_do_nhiem_vu`...): lam vay doi hoi biet TRUOC moi
        `cosmetic_key`/`quest_key`/`period_key` da tung ghi, va bo sot mot khoa
        la de lai du lieu ca nhan cua mot tai khoan da xoa. Truy van thi don
        dung nhung gi that su co trong bang."""
        bc = bao_cao_xoa_gamification()
        if not user_id:
            return bc
        for ten, collection in (
            ("user_progress", COL_PROGRESS),
            ("xp_ledger", COL_XP_LEDGER),
            ("achievement_unlocks", COL_ACHIEVEMENT_UNLOCKS),
            ("cosmetic_inventory", COL_COSMETIC_INVENTORY),
            ("reading_streaks", COL_READING_STREAKS),
            ("quest_progress", COL_QUEST_PROGRESS),
        ):
            for row in self._list_all(collection, [q_equal("user_id", user_id)]):
                doc_id = str(row.get("$id") or "")
                if not doc_id:
                    continue
                self._delete(collection, doc_id)
                bc[ten] += 1
        return bc


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
        kho = AppwriteGamificationStore(settings.appwrite)
        # Duong ghi nguyen tu chi bat khi cau hinh TUONG MINH (`FAS_XP_ATOMIC=1`) — xem config.py.
        kho.xp_atomic = bool(getattr(settings, "xp_atomic_enabled", False))
        return kho
    return MockGamificationStore()
