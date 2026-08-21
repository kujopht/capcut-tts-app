"""
Tang service gamification — noi cac ham thuan cua `gamification.py` /
`gamification_domain.py` vao MOT kho that (`GamificationStore`).

Module nay la noi DUY NHAT duoc phep GHI vao kho gamification — route trong
`server/main.py` khong bao gio tu ghi thang, luon di qua day. Nho vay moi
quy tac idempotent (khong cong XP hai lan, khong mo thanh tuu hai lan,
khong tao vat pham trung) nam o MOT cho.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from server.domain import now_iso
from server.gamification import (
    ACHIEVEMENTS,
    COSMETIC_CATALOG,
    LEVEL_TIERS,
    QUEST_CATALOG,
    REWARD_PACKS,
    XP_EVENTS,
    cosmetic_pool_for_pack,
    id_thuong_nhiem_vu,
    id_xp_entry,
    level_for,
    next_level,
    tinh_trang_thanh_tuu,
    title_unlocked,
)
from server.gamification_domain import (
    CosmeticInventoryItem,
    QuestProgress,
    ReadingStreak,
    RewardPackError,
    UnlockedAchievement,
    UserProgress,
    XpLedgerEntry,
    advance_streak,
    quest_period_key,
    roll_cosmetic,
)


class GamificationError(ValueError):
    """Loi CO Y NGHIA cho nguoi dung (danh xung chua mo khoa, vat pham
    khong co, khong con goi thuong...) — route anh xa sang 400/404 ro rang,
    khac AssertionError/KeyError am tham."""


def _ap_dung_xp(store: Any, user_id: str, xp_amount: int) -> UserProgress:
    """
    Cong THAT `xp_amount` vao tien do VA cap goi thuong mien phi cho MOI bac
    vua vuot qua — logic DUNG CHUNG giua `award_xp` (gia tri co dinh tu
    `XP_EVENTS`) va `claim_quest_reward` (gia tri rieng cua tung nhiem vu).
    KHONG kiem idempotency o day — goi noi (da qua `store.record_xp_event`)
    chiu trach nhiem dam bao ham nay chi duoc goi DUNG MOT LAN cho MOI su
    kien, mot cho de tranh hai noi cong-XP-hai-lan-vi-quen-kiem.
    """
    progress = store.get_progress(user_id)
    bac_truoc = level_for(progress.xp)
    progress.xp += xp_amount
    bac_sau = level_for(progress.xp)
    if bac_sau.level > bac_truoc.level:
        # Len (it nhat) mot bac — cap goi thuong mien phi cho MOI bac vua
        # vuot qua, khong chi mot goi du nhay may bac cung luc.
        progress.goi_thuong_dang_cho += bac_sau.level - bac_truoc.level
    return store.save_progress(progress)


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
    return _ap_dung_xp(store, user_id, entry.xp_awarded)


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


def cong_khai_vat_pham_dang_trang_bi_hang_loat(
        store: Any, user_ids: Sequence[str]) -> Dict[str, List[dict]]:
    """
    Ban HANG LOAT cua `cong_khai_vat_pham_dang_trang_bi` — cho the tac gia gon
    dung chung o nhieu noi cung luc (binh luan, bai dang, thong bao, tim kiem —
    xem `SocialService._the_nguoi`). MOT truy van kho du lieu cho ca danh sach
    (`list_cosmetics_by_ids`), khong phai mot truy van rieng cho tung nguoi.

    Nguoi khong trang bi gi VANG MAT khoi dict tra ve (khong phai danh sach
    rong) — noi goi dung `.get(uid, [])`.
    """
    dinh_nghia = {c.key: c for c in COSMETIC_CATALOG}
    theo_nguoi = store.list_cosmetics_by_ids(user_ids)
    ra: Dict[str, List[dict]] = {}
    for uid, muc_list in theo_nguoi.items():
        cua_nguoi = []
        for muc in muc_list:
            if not muc.equipped:
                continue
            dn = dinh_nghia.get(muc.cosmetic_key)
            if dn is None:
                continue
            cua_nguoi.append({"key": dn.key, "name": dn.name, "rarity": dn.rarity,
                              "slot": dn.slot, "asset_ref": dn.asset_ref})
        if cua_nguoi:
            ra[uid] = cua_nguoi
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


# =============================================================================
# Chuoi ngay doc — V4 visual completion, vong 5.
# =============================================================================


def record_daily_read(store: Any, user_id: str, today: str) -> ReadingStreak:
    """Ghi MOT lan doc trong ngay `today` (chuoi `YYYY-MM-DD`, UTC) — tien
    len chuoi qua ham thuan `advance_streak` roi luu. AN TOAN goi lai nhieu
    lan trong CUNG mot ngay: `advance_streak` tra ve chinh doi tuong dau
    vao khi khong co gi thay doi, nen ham nay bo qua viec ghi lai (tranh
    mot lan ghi kho thua cho moi lan bao cao doc trong ngay)."""
    hien_tai = store.get_streak(user_id)
    moi = advance_streak(hien_tai, today)
    if moi is hien_tai:
        return hien_tai
    return store.save_streak(moi)


def streak_hien_thi(streak: ReadingStreak) -> dict:
    """Hinh dang tra ve cho API — CHI ba gia tri nguoi doc can thay, khong
    lo `grace_used_this_run` (chi tiet trien khai noi bo, khong phai thu
    nguoi dung can biet hay dieu khien)."""
    return {
        "current_streak": streak.current_streak,
        "longest_streak": streak.longest_streak,
        "last_read_date": streak.last_read_date or None,
    }


# =============================================================================
# Nhiem vu (quest) — V4 visual completion, vong 5.
# =============================================================================


def record_quest_event(store: Any, user_id: str, event_type: str, today: str, *,
                       amount: int = 1) -> None:
    """
    Cong tien do cho MOI nhiem vu (ngay VA tuan) co `event_type` khop, cho
    KY HIEN TAI (`today`) — mot su kien THAT co the cong tien do cho ca
    nhiem vu ngay lan nhiem vu tuan cung luc (vi du doc mot chuong tinh ca
    vao "Đọc một chương" HANG NGAY lan "Đọc 5 chương trong tuần" HANG TUAN).

    Nhiem vu DA nhan thuong (`claimed=True`) VAN duoc cong tien do binh
    thuong — khong them mot nhanh dieu kien rieng chi de "dung cong nua".
    Tien do vuot muc tieu sau khi da nhan thuong la vo hai (hien thi da bi
    chan o `list_quests_with_progress`/`claim_quest_reward`), va don gian
    hon la phai nho kiem `claimed` o CA hai noi ghi va doc.

    MOT truy van doc (`list_quest_progress`, toan bo ban ghi cua nguoi
    dung) cho ca danh sach nhiem vu khop, khong phai mot truy van rieng cho
    tung nhiem vu.
    """
    khop = [q for q in QUEST_CATALOG if q.event_type == event_type]
    if not khop:
        return
    hien_co = {(p.quest_key, p.period_key): p
              for p in store.list_quest_progress(user_id)}
    for quest in khop:
        period_key = quest_period_key(quest.period, today)
        tien_do = hien_co.get((quest.key, period_key)) or QuestProgress(
            user_id=user_id, quest_key=quest.key, period_key=period_key)
        tien_do.count += amount
        tien_do.updated_at = now_iso()
        store.save_quest_progress(tien_do)


def list_quests_with_progress(store: Any, user_id: str, today: str) -> List[dict]:
    """Toan bo nhiem vu (ngay+tuan) kem tien do KY HIEN TAI. Nhiem vu chua
    tung dong gop gi trong ky nay hien tien do 0 (khong co ban ghi nao,
    khong phai loi) — day chinh la "reset" tu nhien khi sang ky moi."""
    theo_khoa = {(p.quest_key, p.period_key): p
                for p in store.list_quest_progress(user_id)}
    ra: List[dict] = []
    for quest in QUEST_CATALOG:
        period_key = quest_period_key(quest.period, today)
        tien_do = theo_khoa.get((quest.key, period_key))
        count = tien_do.count if tien_do else 0
        ra.append({
            "key": quest.key, "name": quest.name, "description": quest.description,
            "period": quest.period, "target_count": quest.target_count,
            "xp_reward": quest.xp_reward,
            "cosmetic_reward_key": quest.cosmetic_reward_key or None,
            "count": min(count, quest.target_count),
            "completed": count >= quest.target_count,
            "claimed": tien_do.claimed if tien_do else False,
        })
    return ra


def claim_quest_reward(store: Any, user_id: str, quest_key: str,
                       today: str) -> dict:
    """
    Nhan thuong MOT nhiem vu DA HOAN THANH trong KY HIEN TAI.

    Thu tu BAT BUOC, cung triet ly voi `open_reward_pack`: danh dau
    `claimed=True` va LUU TRUOC, roi moi cong XP/cap vat pham — mot lan
    crash giua chung se mat phan thuong (nguoi dung phai bao lai), KHONG
    BAO GIO de client nhan duoc thuong hai lan bang cach goi lai/tai lai
    trang giua luc dang xu ly.
    """
    quest = next((q for q in QUEST_CATALOG if q.key == quest_key), None)
    if quest is None:
        raise GamificationError("Nhiệm vụ không tồn tại.")
    period_key = quest_period_key(quest.period, today)
    tien_do = store.get_quest_progress(user_id, quest.key, period_key)
    if tien_do.count < quest.target_count:
        raise GamificationError("Bạn chưa hoàn thành nhiệm vụ này.")
    if tien_do.claimed:
        raise GamificationError("Bạn đã nhận thưởng nhiệm vụ này rồi.")

    tien_do.claimed = True
    tien_do.updated_at = now_iso()
    store.save_quest_progress(tien_do)

    if quest.xp_reward > 0:
        entry = XpLedgerEntry(
            entry_id=id_thuong_nhiem_vu(user_id, quest.key, period_key),
            user_id=user_id, event_type="quest_reward", source_kind="quest",
            source_id=f"{quest.key}:{period_key}", xp_awarded=quest.xp_reward)
        if store.record_xp_event(entry):
            _ap_dung_xp(store, user_id, entry.xp_awarded)

    vat_pham_duoc_cap = None
    if quest.cosmetic_reward_key:
        dinh_nghia = _dinh_nghia_vat_pham(quest.cosmetic_reward_key)
        if dinh_nghia is not None:
            store.grant_cosmetic(CosmeticInventoryItem(
                user_id=user_id, cosmetic_key=dinh_nghia.key))
            vat_pham_duoc_cap = {
                "key": dinh_nghia.key, "name": dinh_nghia.name,
                "rarity": dinh_nghia.rarity, "slot": dinh_nghia.slot,
                "asset_ref": dinh_nghia.asset_ref,
            }

    return {"quest_key": quest.key, "xp_awarded": quest.xp_reward,
            "cosmetic": vat_pham_duoc_cap}


# =============================================================================
# Bang xep hang — V4 visual completion, vong 5.
# =============================================================================


def _anh_url(storage: Any, key: str) -> str:
    """URL avatar da ky, ngan han — CUNG logic voi `SocialService._anh_url`,
    lap lai (khong import) o day vi `social_service` da import NGUOC lai tu
    module nay (`cong_khai_vat_pham_dang_trang_bi_hang_loat`); import chieu
    kia se tao vong lap. `storage=None` (vi du trong test khong quan tam
    avatar) tra chuoi rong, khong loi."""
    if storage is None or not key:
        return ""
    try:
        return storage.signed_url(key, expires_seconds=3600) or ""
    except Exception:
        return ""


def _danh_xung_cua(progress: UserProgress) -> str:
    """Ten danh xung DANG TRANG BI cua mot nguoi — cung logic chon voi
    `cap_do_hien_thi`, rut gon chi lay ten hien thi."""
    bac = level_for(progress.xp)
    khoa = progress.equipped_title_key or bac.key
    danh_xung = next((t for t in LEVEL_TIERS if t.key == khoa), bac)
    return danh_xung.title


def _the_bang_xep_hang(uid: str, xp: int, hang: int, is_you: bool,
                       ho_so: Dict[str, Dict[str, Any]],
                       vat_pham: Dict[str, List[dict]]) -> dict:
    """MOT hang trong bang xep hang — ghep the tac gia gon (ten/avatar/khung
    dang trang bi/danh xung) voi hang + XP. Dung CHUNG mot dinh dang cho ca
    hai che do (all_time/weekly), chi khac nguon `xp`."""
    the = ho_so.get(uid, {})
    return {
        "user_id": uid,
        "username": the.get("username", ""),
        "display_name": the.get("display_name", ""),
        "avatar_url": the.get("avatar_url") or None,
        "title": the.get("title", ""),
        "rank": hang,
        "xp": xp,
        "is_you": is_you,
        "equipped_cosmetics": vat_pham.get(uid, []),
    }


def _the_rieng_cho_nguoi_xem(store: Any, identity: Any, storage: Any,
                             viewer_id: str, xp: int, hang: int,
                             progress: UserProgress) -> dict:
    """Dung khi nguoi xem KHONG nam trong trang dang hien — van can mot the
    rieng cho ho (hang that, du o ngoai trang), chi phai tra cuu ho so/vat
    pham cho MOT nguoi thay vi ca trang."""
    the_nguoi = identity.profiles_by_ids([viewer_id])
    vat_pham = cong_khai_vat_pham_dang_trang_bi_hang_loat(store, [viewer_id])
    p = the_nguoi.get(viewer_id)
    ho_so = ({viewer_id: {
        "username": p.username, "display_name": p.display_name or p.username,
        "avatar_url": _anh_url(storage, p.avatar_key),
        "title": _danh_xung_cua(progress),
    }} if p else {})
    return _the_bang_xep_hang(viewer_id, xp, hang, True, ho_so, vat_pham)


def leaderboard_all_time(store: Any, identity: Any, storage: Any = None, *,
                         limit: int, offset: int, viewer_id: str = "") -> dict:
    """
    Bang xep hang XP TOAN THOI GIAN — MAY CHU sap xep + phan trang
    (`store.list_all_progress_ranked`), khong tai ca bang ve Python.

    `viewer_id` (neu co dang nhap) duoc DANH DAU `is_you` trong trang NEU
    xuat hien, VA luon kem `viewer_rank`/`viewer_xp` RIENG du ho co nam
    trong trang dang xem hay khong — nguoi xem hang 5000 van muon biet hang
    cua minh ma khong phai lat 250 trang.

    `storage` (tuy chon) dung de ky URL avatar — bo qua (avatar_url rong)
    neu khong truyen, vi du trong test chi quan tam thu tu/XP.
    """
    trang, tong = store.list_all_progress_ranked(limit, offset)
    ids = [p.user_id for p in trang]
    the_nguoi = identity.profiles_by_ids(ids) if ids else {}
    tien_do_theo_id = {p.user_id: p for p in trang}
    ho_so = {
        uid: {
            "username": p.username, "display_name": p.display_name or p.username,
            "avatar_url": _anh_url(storage, p.avatar_key),
            "title": _danh_xung_cua(tien_do_theo_id[uid]) if uid in tien_do_theo_id else "",
        }
        for uid, p in the_nguoi.items()
    }
    vat_pham = cong_khai_vat_pham_dang_trang_bi_hang_loat(store, ids)

    items = [
        _the_bang_xep_hang(p.user_id, p.xp, offset + i + 1, p.user_id == viewer_id,
                          ho_so, vat_pham)
        for i, p in enumerate(trang)
    ]

    viewer_entry = None
    if viewer_id and not any(it["user_id"] == viewer_id for it in items):
        viewer_progress = store.get_progress(viewer_id)
        if viewer_progress.xp > 0:
            viewer_rank = store.count_users_above_xp(viewer_progress.xp) + 1
            viewer_entry = _the_rieng_cho_nguoi_xem(
                store, identity, storage, viewer_id, viewer_progress.xp,
                viewer_rank, viewer_progress)

    return {"items": items, "total": tong, "limit": limit, "offset": offset,
            "viewer_entry": viewer_entry}


def leaderboard_weekly(store: Any, identity: Any, storage: Any = None, *,
                       limit: int, offset: int, since_iso: str,
                       viewer_id: str = "") -> dict:
    """
    Bang xep hang XP KIEM DUOC TU `since_iso` (thuong la dau tuan ISO) —
    tinh tu nhat ky XP (`store.xp_earned_since`), sap giam dan O PYTHON (chi
    sau khi da gioi han theo thoi gian, nen kich thuoc bi chan boi so su
    kien trong MOT tuan, khong phai toan bo lich su).

    Bac/danh xung hien thi van la tien do THAT (tong XP moi thoi, khong
    phai XP-trong-tuan) — mot nguoi moi vao co the dan dau tuan nay nhung
    van o bac thap, va do la dieu dung, khong phai loi. Lay qua MOT truy
    van hang loat (`store.get_progress_by_ids`), khong phai N+1.
    """
    theo_nguoi = store.xp_earned_since(since_iso)
    sap = sorted(theo_nguoi.items(), key=lambda kv: (-kv[1], kv[0]))
    tong = len(sap)
    trang = sap[offset:offset + max(0, limit)]
    ids = [uid for uid, _ in trang]
    the_nguoi = identity.profiles_by_ids(ids) if ids else {}
    tien_do_theo_id = store.get_progress_by_ids(ids) if ids else {}
    ho_so = {
        uid: {
            "username": p.username, "display_name": p.display_name or p.username,
            "avatar_url": _anh_url(storage, p.avatar_key),
            "title": _danh_xung_cua(tien_do_theo_id[uid]) if uid in tien_do_theo_id else "",
        }
        for uid, p in the_nguoi.items()
    }
    vat_pham = cong_khai_vat_pham_dang_trang_bi_hang_loat(store, ids)

    items = [
        _the_bang_xep_hang(uid, xp, offset + i + 1, uid == viewer_id, ho_so, vat_pham)
        for i, (uid, xp) in enumerate(trang)
    ]

    viewer_entry = None
    if viewer_id and not any(it["user_id"] == viewer_id for it in items):
        xp_tuan_cua_ban = theo_nguoi.get(viewer_id, 0)
        if xp_tuan_cua_ban > 0:
            hang = sum(1 for _, xp in sap if xp > xp_tuan_cua_ban) + 1
            viewer_progress = store.get_progress(viewer_id)
            viewer_entry = _the_rieng_cho_nguoi_xem(
                store, identity, storage, viewer_id, xp_tuan_cua_ban, hang,
                viewer_progress)

    return {"items": items, "total": tong, "limit": limit, "offset": offset,
            "viewer_entry": viewer_entry}
