"""
Tang service gamification — noi cac ham thuan cua `gamification.py` /
`gamification_domain.py` vao MOT kho that (`GamificationStore`).

Module nay la noi DUY NHAT duoc phep GHI vao kho gamification — route trong
`server/main.py` khong bao gio tu ghi thang, luon di qua day. Nho vay moi
quy tac idempotent (khong cong XP hai lan, khong mo thanh tuu hai lan,
khong tao vat pham trung) nam o MOT cho.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from server.gamification import (
    ACHIEVEMENTS,
    COSMETIC_CATALOG,
    LEVEL_TIERS,
    REWARD_PACKS,
    XP_EVENTS,
    cosmetic_pool_for_pack,
    id_xp_entry,
    level_for,
    next_level,
    tinh_trang_thanh_tuu,
    title_unlocked,
)
from server.gamification_domain import (
    CosmeticInventoryItem,
    RewardPackError,
    UnlockedAchievement,
    UserProgress,
    XpLedgerEntry,
    roll_cosmetic,
)


class GamificationError(ValueError):
    """Loi CO Y NGHIA cho nguoi dung (danh xung chua mo khoa, vat pham
    khong co, khong con goi thuong...) — route anh xa sang 400/404 ro rang,
    khac AssertionError/KeyError am tham."""


def award_xp(store: Any, user_id: str, event_type: str, *,
            source_kind: str, source_id: str) -> Optional[UserProgress]:
    """
    Cong XP cho MOT su kien MAY CHU DA XAC NHAN — KHONG BAO GIO nhan gia tri
    XP tu client, chi nhan `event_type` (tra ve gia tri tu `XP_EVENTS`).

    IDEMPOTENT: cung `(user_id, event_type, source_id)` goi lai bao nhieu
    lan cung CHI cong XP MOT LAN — `store.record_xp_event` la diem chan.
    Tra `None` khi su kien nay DA duoc cong roi (khong co gi thay doi), tra
    `UserProgress` moi khi THAT SU cong duoc — goi noi lam "co len bac hay
    khong" ma khong phai tu doi chieu XP truoc/sau.
    """
    if event_type not in XP_EVENTS:
        raise GamificationError(f"Loại sự kiện XP không xác định: {event_type!r}.")
    entry_id = id_xp_entry(user_id, event_type, source_id)
    entry = XpLedgerEntry(
        entry_id=entry_id, user_id=user_id, event_type=event_type,
        source_kind=source_kind, source_id=source_id,
        xp_awarded=XP_EVENTS[event_type])
    if not store.record_xp_event(entry):
        return None  # Su kien nay da duoc cong truoc do — khong lam gi them.

    progress = store.get_progress(user_id)
    bac_truoc = level_for(progress.xp)
    progress.xp += entry.xp_awarded
    bac_sau = level_for(progress.xp)
    if bac_sau.level > bac_truoc.level:
        # Len (it nhat) mot bac — cap goi thuong mien phi cho MOI bac vua
        # vuot qua, khong chi mot goi du nhay may bac cung luc.
        progress.goi_thuong_dang_cho += bac_sau.level - bac_truoc.level
    return store.save_progress(progress)


def cap_do_hien_thi(progress: UserProgress) -> dict:
    """
    Hinh dang tra ve cho API cap do — TAT CA gia tri do MAY CHU tinh, giao
    dien KHONG duoc tu tinh nguong (dung mau voi `creator.rank_progress`).
    """
    bac = level_for(progress.xp)
    sau = next_level(progress.xp)
    if sau:
        khoang = max(1, sau.min_xp - bac.min_xp)
        phan_tram = max(0, min(100, int(round(
            100.0 * (progress.xp - bac.min_xp) / khoang))))
    else:
        phan_tram = 100
    danh_xung_hien = progress.equipped_title_key or bac.key
    danh_xung = next((t for t in LEVEL_TIERS if t.key == danh_xung_hien), bac)
    return {
        "xp": progress.xp,
        "level": bac.level,
        "level_key": bac.key,
        "current_level_xp": bac.min_xp,
        "next_level_xp": sau.min_xp if sau else None,
        "progress_percent": phan_tram,
        "equipped_title_key": danh_xung.key,
        "equipped_title": danh_xung.title,
        "pending_reward_packs": progress.goi_thuong_dang_cho,
    }


def equip_title(store: Any, user_id: str, title_key: str) -> UserProgress:
    """`title_key` rong = quay ve danh xung MAC DINH theo bac hien tai."""
    progress = store.get_progress(user_id)
    if title_key and not title_unlocked(progress.xp, title_key):
        raise GamificationError("Danh xưng này chưa được mở khoá.")
    progress.equipped_title_key = title_key
    return store.save_progress(progress)


def sync_achievements(store: Any, user_id: str, *, so_truyen_xuat_ban: int,
                      so_chuong_xuat_ban: int, ky_tu_da_tong_hop: int,
                      phut_da_nghe: int) -> List[UnlockedAchievement]:
    """
    Doi chieu dieu kien THAT (tinh tai cho) voi kho THAT — mo khoa (ghi
    `unlocked_at`) cho MOI thanh tuu dat dieu kien nhung CHUA co ban ghi.
    Goi lai nhieu lan an toan: thanh tuu da mo khong bi ghi de moc thoi
    gian moi (`store.unlock_achievement` tra `False` va bo qua).

    Tra ve danh sach thanh tuu VUA moi mo trong LAN GOI NAY (rong neu khong
    co gi moi) — dung de bao "vua dat thanh tuu X" mot lan duy nhat.
    """
    trang_thai = tinh_trang_thanh_tuu(
        so_truyen_xuat_ban=so_truyen_xuat_ban,
        so_chuong_xuat_ban=so_chuong_xuat_ban,
        ky_tu_da_tong_hop=ky_tu_da_tong_hop, phut_da_nghe=phut_da_nghe)
    vua_mo: List[UnlockedAchievement] = []
    for t in trang_thai:
        if not t.dat_duoc:
            continue
        record = UnlockedAchievement(user_id=user_id, achievement_key=t.dinh_nghia.key)
        if store.unlock_achievement(record):
            vua_mo.append(record)
    return vua_mo


def achievements_hien_thi(store: Any, user_id: str, *, so_truyen_xuat_ban: int,
                          so_chuong_xuat_ban: int, ky_tu_da_tong_hop: int,
                          phut_da_nghe: int) -> List[dict]:
    """Dong bo roi tra hinh dang DAY DU (kem `unlocked_at` that tu kho) cho
    API — goi mot lan la co ca hai buoc, tranh route quen dong bo truoc khi doc."""
    sync_achievements(
        store, user_id, so_truyen_xuat_ban=so_truyen_xuat_ban,
        so_chuong_xuat_ban=so_chuong_xuat_ban,
        ky_tu_da_tong_hop=ky_tu_da_tong_hop, phut_da_nghe=phut_da_nghe)
    da_mo = {a.achievement_key: a for a in store.list_unlocked_achievements(user_id)}
    trang_thai = tinh_trang_thanh_tuu(
        so_truyen_xuat_ban=so_truyen_xuat_ban,
        so_chuong_xuat_ban=so_chuong_xuat_ban,
        ky_tu_da_tong_hop=ky_tu_da_tong_hop, phut_da_nghe=phut_da_nghe)
    ra = []
    for t in trang_thai:
        ban_ghi = da_mo.get(t.dinh_nghia.key)
        ra.append({
            "key": t.dinh_nghia.key,
            "name": t.dinh_nghia.name,
            "description": t.dinh_nghia.description,
            "icon": t.dinh_nghia.icon,
            "rarity": t.dinh_nghia.rarity,
            "unlocked": ban_ghi is not None,
            "progress": list(t.tien_do) if t.tien_do else None,
            "unlocked_at": ban_ghi.unlocked_at if ban_ghi else None,
        })
    return ra


def cong_khai_cap_do(progress: UserProgress) -> dict:
    """
    Hinh dang CONG KHAI cho `/u/[username]` — CHI bac + danh xung dang
    trang bi. KHONG co `xp`/`next_level_xp`/`progress_percent`/`pending_
    reward_packs`: day la "noi bo tien trien", khong phai danh tinh cong
    khai — dac ta yeu cau ro "khong lo noi bo tien trien".
    """
    bac = level_for(progress.xp)
    danh_xung_hien = progress.equipped_title_key or bac.key
    danh_xung = next((t for t in LEVEL_TIERS if t.key == danh_xung_hien), bac)
    return {
        "level": bac.level,
        "level_key": bac.key,
        "equipped_title_key": danh_xung.key,
        "equipped_title": danh_xung.title,
    }


def cong_khai_thanh_tuu(store: Any, user_id: str) -> List[dict]:
    """
    Thanh tuu CONG KHAI cua MOT nguoi dung BAT KY — chi doc kho MO KHOA THAT
    (`list_unlocked_achievements`), KHONG BAO GIO tinh lai tu bo dem rieng
    tu (`tts_characters_used`/`listened_minutes`) nhu `achievements_hien_thi`
    (chi danh cho chinh chu). An toan cho `/u/[username]`.
    """
    da_mo = {a.achievement_key for a in store.list_unlocked_achievements(user_id)}
    return [
        {"key": a.key, "name": a.name, "icon": a.icon, "rarity": a.rarity,
         "unlocked": a.key in da_mo}
        for a in ACHIEVEMENTS
    ]


def cong_khai_vat_pham_dang_trang_bi(store: Any, user_id: str) -> List[dict]:
    """CHI vat pham DANG TRANG BI — khong lo toan bo bo suu tap rieng tu."""
    dinh_nghia = {c.key: c for c in COSMETIC_CATALOG}
    ra = []
    for muc in store.list_cosmetics(user_id):
        if not muc.equipped:
            continue
        dn = dinh_nghia.get(muc.cosmetic_key)
        if dn is None:
            continue
        ra.append({"key": dn.key, "name": dn.name, "rarity": dn.rarity,
                   "slot": dn.slot, "asset_ref": dn.asset_ref})
    return ra


def _dinh_nghia_vat_pham(cosmetic_key: str):
    return next((c for c in COSMETIC_CATALOG if c.key == cosmetic_key), None)


def equip_cosmetic(store: Any, user_id: str, cosmetic_key: str) -> CosmeticInventoryItem:
    """
    Trang bi MOT vat pham NGUOI DUNG DA CO. Moi vi tri (`slot`) toi da MOT
    vat pham dang trang bi — bo trang bi vat pham KHAC cung vi tri truoc.
    """
    dinh_nghia = _dinh_nghia_vat_pham(cosmetic_key)
    if dinh_nghia is None:
        raise GamificationError("Vật phẩm không tồn tại.")
    muc = store.get_cosmetic(user_id, cosmetic_key)
    if muc is None:
        raise GamificationError("Bạn chưa có vật phẩm này.")

    for da_co in store.list_cosmetics(user_id):
        if not da_co.equipped or da_co.cosmetic_key == cosmetic_key:
            continue
        dn_khac = _dinh_nghia_vat_pham(da_co.cosmetic_key)
        if dn_khac and dn_khac.slot == dinh_nghia.slot:
            store.set_cosmetic_equipped(user_id, da_co.cosmetic_key, False)

    store.set_cosmetic_equipped(user_id, cosmetic_key, True)
    return store.get_cosmetic(user_id, cosmetic_key)


def open_reward_pack(store: Any, user_id: str, pack_key: str,
                     rng: Any) -> Tuple[Any, bool]:
    """
    Mo MOT goi thuong dang cho — tra `(CosmeticDef, da_trung_lap)`.

    Thu tu BAT BUOC: tru `pending_reward_packs` va LUU truoc, roi moi rut
    vat pham va luu ket qua — "khong mo lai duoc bang cach tai lai trang"
    dat duoc vi so goi cho da giam NGAY KHI request nay chay, khong phai
    khi nguoi dung thay ket qua. Mot lan crash giua chung se mat mot goi
    (nguoi dung thiet), khong bao gio TANG so lan mo duoc — danh doi an
    toan hon la de client rut nhieu lan.
    """
    pack = next((p for p in REWARD_PACKS if p.key == pack_key), None)
    if pack is None:
        raise GamificationError("Gói thưởng không tồn tại.")

    progress = store.get_progress(user_id)
    if progress.goi_thuong_dang_cho <= 0:
        raise GamificationError("Bạn không có gói thưởng nào để mở.")
    progress.goi_thuong_dang_cho -= 1
    store.save_progress(progress)

    try:
        vat_pham = roll_cosmetic(pack, cosmetic_pool_for_pack(pack_key), rng)
    except RewardPackError as exc:
        raise GamificationError(str(exc)) from exc

    item = CosmeticInventoryItem(user_id=user_id, cosmetic_key=vat_pham.key)
    da_luu = store.grant_cosmetic(item)
    da_trung_lap = da_luu is None
    return vat_pham, da_trung_lap
