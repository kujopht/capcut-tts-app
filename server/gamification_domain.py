"""
Ban ghi ben vung cho cap do va vat pham suu tam — V4 visual completion,
Phan G/K/L.

TRANG THAI (cap nhat vong 2): DA CO KHO THAT (`server/gamification_store.py`,
`MockGamificationStore`) va TANG SERVICE (`server/gamification_service.py`)
noi cac dataclass o day vao route that (`GET/POST /api/account/progress`,
`/api/account/title`, `/api/account/cosmetics/*`, `/api/account/reward-
packs/*`). Schema Appwrite van CHI o dang THIET KE — xem
`scripts/setup_appwrite.py` (dry-run xac nhan additive), CHUA AP production.
Ban Appwrite that cua kho (tuong tu `appwrite_translation_store.py`) CHUA
viet — kho dang dung la `MockGamificationStore` (trong bo nho, dung y het
`MockTranslationStore` o giai doan dau cua V5).

Module nay la Python THUAN — khong FastAPI, khong Appwrite, khong mang,
khong dong ho toan cuc (moi ham nhan du lieu can thiet qua tham so).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence

from server.domain import now_iso


@dataclass
class UserProgress:
    """Ban ghi CAP DO cua mot nguoi dung — MOT hang moi user_id.

    `xp` la GIA TRI CONG DON, ghi boi tang service (chua viet) tu
    `gamification.XP_EVENTS` qua `gamification.id_xp_entry()` de chong cong
    hai lan cho cung mot su kien — cung ky thuat voi
    `author_stats.qualified_listens`/`ListenCredit` (xem
    `docs/AUTHOR_RANK.md`, muc "Cong don thay vi dem lai")."""

    user_id: str
    xp: int = 0
    #: Rong = dung danh xung MAC DINH theo XP hien tai (`gamification.level_for`).
    #: Nguoi dung CHON mot danh xung DA MO KHOA de "dong bang" hien thi, khong
    #: bi tu doi khi len bac moi ho khong thich ten moi.
    equipped_title_key: str = ""
    #: So goi thuong MIEN PHI dang CHO MO — cong 1 moi lan len bac moi (xem
    #: `gamification_service.award_xp`), tru 1 moi lan mo thanh cong. KHONG
    #: BAO GIO am — service phai kiem `> 0` truoc khi cho mo.
    goi_thuong_dang_cho: int = 0
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "xp": self.xp,
            "equipped_title_key": self.equipped_title_key or None,
            "pending_reward_packs": self.goi_thuong_dang_cho,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class XpLedgerEntry:
    """
    MOT lan cong XP — nhat ky KIEM TOAN DUOC, khong phai chi mot so nguyen
    `xp` co the bi ghi de sai. `entry_id` TAT DINH tu (user_id, event_type,
    source_id) qua `gamification.id_xp_entry()` — cung id nghia la CUNG mot
    su kien, nen kho chi can kiem "id nay da co chua" de chan cong hai lan,
    khong can khoa giao dich rieng (cung ky thuat voi `ListenCredit`/
    `job_locks`, xem `docs/AUTHOR_RANK.md`).
    """

    entry_id: str
    user_id: str
    event_type: str
    #: Loai nguon sinh ra su kien — vi du "chapter", "novel", "listen_credit".
    #: Giup doc nhat ky ma khong phai doan tu `event_type`.
    source_kind: str
    source_id: str
    xp_awarded: int
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "xp_awarded": self.xp_awarded,
            "created_at": self.created_at,
        }


@dataclass
class UnlockedAchievement:
    """MOT thanh tuu DA MO KHOA that su, kem MOC THOI GIAN — khac
    `gamification.TinhTrangThanhTuu` (tinh tai cho, khong co `unlocked_at`).
    MOT hang cho moi (user_id, achievement_key)."""

    user_id: str
    achievement_key: str
    unlocked_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "achievement_key": self.achievement_key,
            "unlocked_at": self.unlocked_at,
        }


#: Vi tri trang bi mot vat pham — MOI vi tri toi da MOT vat pham dang trang bi.
COSMETIC_SLOTS: Sequence[str] = (
    "avatar_frame", "profile_ornament", "badge", "card_border", "title_effect",
)


@dataclass(frozen=True)
class CosmeticDef:
    """Dinh nghia MOT vat pham — tuong tu `gamification.AchievementDef`.

    `asset_ref` la THAM CHIEU (ten class SVG/CSS goc), KHONG PHAI anh — cam
    nhan vat hoat hinh co ban quyen theo dung yeu cau (chi tai san SVG/CSS
    NGUYEN BAN cua Fanfic World)."""

    key: str
    name: str
    rarity: str
    slot: str
    asset_ref: str


@dataclass
class CosmeticInventoryItem:
    """Mot vat pham NGUOI DUNG DA CO — MOT hang moi (user_id, cosmetic_key)."""

    user_id: str
    cosmetic_key: str
    acquired_at: str = field(default_factory=now_iso)
    equipped: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "cosmetic_key": self.cosmetic_key,
            "acquired_at": self.acquired_at,
            "equipped": self.equipped,
        }


@dataclass(frozen=True)
class RewardPack:
    """
    Mot goi phan thuong MIEN PHI — KHONG co phien ban tra phi trong pham vi
    nay (xem canh bao "KHONG mo purchase flow" o dac ta goc, Phan L).

    `rarity_weights` la TRONG SO CONG KHAI DUOC — minh bach xac suat la yeu
    cau ro rang cua dac ta, nen khong co gi trong cong thuc nay can giau.
    """

    key: str
    name: str
    rarity_weights: Dict[str, int]


class RewardPackError(ValueError):
    pass


def roll_cosmetic(pack: RewardPack, pool: Sequence[CosmeticDef],
                  rng: Any) -> CosmeticDef:
    """
    Rut MOT vat pham tu `pool`, theo trong so do hiem cua `pack`.

    `rng` PHAI la mot `random.Random` (hoac tuong thich) DUOC TRUYEN VAO —
    ham nay khong bao gio tu tao hay doc bo sinh so ngau nhien toan cuc. Nho
    vay ket qua KIEM DUOC TAT DINH: test seed rng truoc khi goi thi luon ra
    cung mot vat pham, khong phu thuoc thoi gian chay.

    May chu la noi DUY NHAT goi ham nay — client khong bao gio tu chon hay
    tu tinh ket qua rut duoc.
    """
    if not pool:
        raise RewardPackError(f"Kho vat pham rong cho goi {pack.key!r}.")
    trong_so = [pack.rarity_weights.get(c.rarity, 0) for c in pool]
    if sum(trong_so) <= 0:
        raise RewardPackError(
            f"Khong co vat pham nao trong {pack.key!r} co trong so hop le.")
    return rng.choices(list(pool), weights=trong_so, k=1)[0]


def them_vao_kho_neu_chua_co(
    kho_hien_tai: Sequence[CosmeticInventoryItem], user_id: str,
    cosmetic_key: str) -> Optional[CosmeticInventoryItem]:
    """
    Xu ly TRUNG LAP khi rut phai vat pham DA CO — dac ta goc yeu cau
    "duplicate handling" ro rang. CHINH SACH Giai doan 1: giu nguyen ban ghi
    cu (khong tao ban ghi thu hai, khong tu quy doi trung thanh gia tri
    khac) — tra `None` de tang goi bao "trung, khong them gi moi", thay vi
    im lang tao du lieu trung.
    """
    for muc in kho_hien_tai:
        if muc.user_id == user_id and muc.cosmetic_key == cosmetic_key:
            return None
    return CosmeticInventoryItem(user_id=user_id, cosmetic_key=cosmetic_key)
