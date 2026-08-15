"""
Kho gamification trong bo nho — V4 visual completion, vong 2.

Logic idempotent (chan XP/thanh tuu/vat pham bi cong/mo/cap hai lan) DAY DU
va CO TEST o day, doc lap voi ha tang — dung lam kho cho test va cho
`DATA_BACKEND != appwrite`. Ban ben vung that qua restart la
`server/appwrite_gamification_store.py::AppwriteGamificationStore` (them ở
vong 3 overnight) — CUNG giao dien nay, `gamification_service.py` va route
trong `server/main.py` khong biet dang chay tren kho nao.

`build_gamification_store()` cua kho THAT (chon Mock/Appwrite theo
`DATA_BACKEND`) nam o `appwrite_gamification_store.py`, KHONG phai o day —
module nay chi con dinh nghia `MockGamificationStore`.

MOT MIXIN doc lap — khong dung chung bang voi `tts_jobs`/`translation_*`.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional, Sequence

from server.adapters import NotFoundError
from server.gamification_domain import (
    CosmeticInventoryItem,
    UnlockedAchievement,
    UserProgress,
    XpLedgerEntry,
)


class MockGamificationStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._progress: Dict[str, UserProgress] = {}
        #: entry_id -> XpLedgerEntry — DAY la diem chan cong XP hai lan.
        self._xp_events: Dict[str, XpLedgerEntry] = {}
        #: user_id -> {achievement_key: UnlockedAchievement}
        self._achievements: Dict[str, Dict[str, UnlockedAchievement]] = {}
        #: user_id -> {cosmetic_key: CosmeticInventoryItem}
        self._cosmetics: Dict[str, Dict[str, CosmeticInventoryItem]] = {}

    # ======================================================== cap do / XP

    def get_progress(self, user_id: str) -> UserProgress:
        with self._lock:
            return self._progress.get(user_id) or UserProgress(user_id=user_id)

    def save_progress(self, progress: UserProgress) -> UserProgress:
        with self._lock:
            self._progress[progress.user_id] = progress
            return progress

    def record_xp_event(self, entry: XpLedgerEntry) -> bool:
        """
        Ghi MOT su kien XP — tra `False` va KHONG ghi gi neu `entry_id` da co
        (su kien nay DA duoc cong roi). Goi ham nay LA phep kiem idempotent
        duy nhat can co: tang service khong can tu hoi "da cong chua" truoc,
        chi can nhin gia tri tra ve.
        """
        with self._lock:
            if entry.entry_id in self._xp_events:
                return False
            self._xp_events[entry.entry_id] = entry
            return True

    def list_xp_events(self, user_id: str) -> List[XpLedgerEntry]:
        with self._lock:
            ds = [e for e in self._xp_events.values() if e.user_id == user_id]
        return sorted(ds, key=lambda e: e.created_at)

    # ======================================================== thanh tuu

    def list_unlocked_achievements(self, user_id: str) -> List[UnlockedAchievement]:
        with self._lock:
            return list(self._achievements.get(user_id, {}).values())

    def unlock_achievement(self, record: UnlockedAchievement) -> bool:
        """Tra `False` neu thanh tuu nay DA mo khoa roi (idempotent, cung
        triet ly voi `record_xp_event`)."""
        with self._lock:
            cua_nguoi_dung = self._achievements.setdefault(record.user_id, {})
            if record.achievement_key in cua_nguoi_dung:
                return False
            cua_nguoi_dung[record.achievement_key] = record
            return True

    # ======================================================== vat pham

    def list_cosmetics(self, user_id: str) -> List[CosmeticInventoryItem]:
        with self._lock:
            return list(self._cosmetics.get(user_id, {}).values())

    def list_cosmetics_by_ids(
            self, user_ids: Sequence[str]) -> Dict[str, List[CosmeticInventoryItem]]:
        """Ban HANG LOAT cua `list_cosmetics` — cho the tac gia gon
        (`SocialService._the_nguoi`) hien khung dang trang bi ma KHONG di mot
        truy van rieng cho tung nguoi (N+1). Nguoi khong co gi thi VANG MAT
        khoi dict, khong phai danh sach rong — goi noi chi can `.get(uid, [])`."""
        with self._lock:
            return {uid: list(self._cosmetics[uid].values())
                    for uid in user_ids if uid in self._cosmetics}

    def get_cosmetic(self, user_id: str, cosmetic_key: str) -> Optional[CosmeticInventoryItem]:
        with self._lock:
            return self._cosmetics.get(user_id, {}).get(cosmetic_key)

    def grant_cosmetic(self, item: CosmeticInventoryItem) -> Optional[CosmeticInventoryItem]:
        """Tra `None` neu nguoi dung DA CO vat pham nay (xu ly trung lap khi
        rut trung — xem `gamification_domain.them_vao_kho_neu_chua_co`, ham
        nay la ban CO KHO THAT cua cung chinh sach)."""
        with self._lock:
            cua_nguoi_dung = self._cosmetics.setdefault(item.user_id, {})
            if item.cosmetic_key in cua_nguoi_dung:
                return None
            cua_nguoi_dung[item.cosmetic_key] = item
            return item

    def set_cosmetic_equipped(self, user_id: str, cosmetic_key: str,
                              equipped: bool) -> None:
        """Bat/tat co `equipped` cua MOT vat pham DA CO. Logic "moi vi tri
        toi da mot vat pham dang trang bi" nam o tang SERVICE (can biet
        catalog de biet vat pham nao cung vi tri) — kho chi luu gia tri."""
        with self._lock:
            muc = self._cosmetics.get(user_id, {}).get(cosmetic_key)
            if muc is None:
                raise NotFoundError("Bạn chưa có vật phẩm này.")
            muc.equipped = equipped
