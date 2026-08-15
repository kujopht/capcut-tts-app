"""
Thanh tuu (achievement) — V4 visual completion, Phan G-J.

Module nay la Python THUAN — khong FastAPI, khong Appwrite, khong mang, cung
trieu ly voi `server/creator.py`: quy tac dat mot cho, kiem duoc ma khong can
ha tang nao.

PHAM VI CO Y THU HEP so voi dac ta goc (Phan G-L day du: UserProgress/XP/
Level/Title, CosmeticInventory, RewardPack/gacha). Ly do:

  XP/Level/Title/Cosmetic/Gacha can MOT KHAI NIEM MOI hoan toan — luy ke hanh
  dong qua thoi gian, ton kho vat pham, lich su phan thuong. Khong the tinh
  "dung luc doc" tu du lieu san co; can bang moi that su luu (xem
  `docs/GAMIFICATION_DESIGN.md` cho thiet ke day du, THIET KE + TEST logic
  thuan CHUA AP schema production).

  THANH TUU o file nay CHI can biet "dieu kien co dat hay chua NGAY BAY GIO",
  va moi dieu kien deu tinh duoc tu du lieu DA CO SAN (Profile.tts_characters_
  used/listened_minutes, so truyen/chuong da xuat ban). Nen thanh tuu o day
  la TINH TAI CHO — khong luu "unlocked_at", khong can bang moi. Danh doi:
  khong biet CHINH XAC luc mo khoa, chi biet dang mo khoa hay chua — chap
  nhan duoc cho mot trang ho so, khong chap nhan duoc cho mot nhat ky.

KHONG dat ten trung voi `RANK_TIERS` (huy hieu HANG TAC GIA, uy tin tu luot
nghe) — day la truc THU HAI, doc lap: thanh tuu la "ban da lam gi", hang la
"nguoi khac nghe ban nhieu den dau". Xem `docs/AUTHOR_RANK.md`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from server.gamification_domain import CosmeticDef, QuestDef, RewardPack


@dataclass(frozen=True)
class AchievementDef:
    #: Khoa on dinh — di vao API va class CSS. KHONG bao gio doi (cung ly do
    #: voi `RankTier.key`).
    key: str
    name: str
    description: str
    #: Icon la MOT ky tu emoji don, khong phai anh — giu nhe, khong can kho
    #: tai san rieng cho giai doan nay.
    icon: str
    #: Do hiem — chi anh huong VIEN/mau hien thi (`--rarity-*`), khong anh
    #: huong dieu kien mo khoa.
    rarity: str


#: Do hiem tang dan — dung de sap xep hien thi, KHONG dung de tinh diem.
RARITIES: Tuple[str, ...] = ("common", "rare", "epic", "legendary", "mythic")

#: Danh sach thanh tuu Giai doan 1 — dieu kien deu tinh tai cho tu du lieu
#: DA CO SAN. Them thanh tuu moi thi them mot dong o day VA mot nhanh trong
#: `_dieu_kien()` — KHONG suy doan dieu kien tu ten.
ACHIEVEMENTS: Tuple[AchievementDef, ...] = (
    AchievementDef(
        key="chuong_dau_tien", name="Chương đầu tiên",
        description="Xuất bản chương đầu tiên của một truyện.",
        icon="📝", rarity="common"),
    AchievementDef(
        key="cat_tieng", name="Cất tiếng",
        description="Tổng hợp giọng đọc đầu tiên trong Audio Studio.",
        icon="🎙️", rarity="common"),
    AchievementDef(
        key="ra_mat_tieu_thuyet", name="Ra mắt tiểu thuyết",
        description="Xuất bản một tiểu thuyết hoàn chỉnh.",
        icon="📖", rarity="rare"),
    AchievementDef(
        key="dem_dai_thu_vien", name="Đêm dài thư viện",
        description="Nghe đủ 60 phút audio trên Fanfic World.",
        icon="🌙", rarity="rare"),
)

#: Nguong cua `dem_dai_thu_vien`, giay o mot cho — cung triet ly voi
#: `RANK_TIERS`: nguong CHO PHAT TRIEN, xem lai truoc khi mo cho nguoi that.
NGUONG_PHUT_NGHE_THU_VIEN = 60


@dataclass(frozen=True)
class TinhTrangThanhTuu:
    dinh_nghia: AchievementDef
    dat_duoc: bool
    #: `(hien_tai, muc_tieu)` khi do luong duoc theo mot con so; `None` khi
    #: dieu kien la nhi phan (co/chua, khong co "phan tram" co nghia).
    tien_do: Tuple[int, int] | None = None


def _dieu_kien(khoa: str, *, so_truyen_xuat_ban: int, so_chuong_xuat_ban: int,
                ky_tu_da_tong_hop: int, phut_da_nghe: int) -> TinhTrangThanhTuu:
    dinh_nghia = next(a for a in ACHIEVEMENTS if a.key == khoa)
    if khoa == "chuong_dau_tien":
        return TinhTrangThanhTuu(dinh_nghia, so_chuong_xuat_ban >= 1)
    if khoa == "cat_tieng":
        return TinhTrangThanhTuu(dinh_nghia, ky_tu_da_tong_hop > 0)
    if khoa == "ra_mat_tieu_thuyet":
        return TinhTrangThanhTuu(dinh_nghia, so_truyen_xuat_ban >= 1)
    if khoa == "dem_dai_thu_vien":
        muc_tieu = NGUONG_PHUT_NGHE_THU_VIEN
        return TinhTrangThanhTuu(
            dinh_nghia, phut_da_nghe >= muc_tieu,
            tien_do=(min(phut_da_nghe, muc_tieu), muc_tieu))
    raise ValueError(f"Thanh tuu khong xac dinh: {khoa}")


def tinh_trang_thanh_tuu(*, so_truyen_xuat_ban: int, so_chuong_xuat_ban: int,
                         ky_tu_da_tong_hop: int,
                         phut_da_nghe: int) -> Tuple[TinhTrangThanhTuu, ...]:
    """
    Tinh trang TOAN BO thanh tuu Giai doan 1, tai cho — HAM THUAN, khong doc
    kho. Goi lai voi cung tham so luon ra cung ket qua; khong co ngau nhien,
    khong co dong ho.
    """
    return tuple(
        _dieu_kien(
            a.key, so_truyen_xuat_ban=so_truyen_xuat_ban,
            so_chuong_xuat_ban=so_chuong_xuat_ban,
            ky_tu_da_tong_hop=ky_tu_da_tong_hop, phut_da_nghe=phut_da_nghe)
        for a in ACHIEVEMENTS
    )


# =============================================================================
# Cap do / danh xung (Phan G-I) — THIET KE + logic thuan, CHUA NOI vao route
# hay UI nao.
# =============================================================================
#
# LY DO tach khoi thanh tuu o tren: cap do can XP LUY KE qua thoi gian (mot
# gia tri phai LUU, cong don tu nhieu su kien server-authoritative), khong
# tinh lai duoc tu du lieu hien co nhu thanh tuu. Chua co bang luu (`xp_ledger`
# o Phan G) nen CHUA THE cap XP that cho ai — dua logic nay ra san la de khi
# co bang that, phan con lai (`level_for`/`level_progress`) khong doi.
#
# KHONG dat ten trung `RANK_TIERS` — xem canh bao dau file. "Nguoi Ke Chuyen"
# trong danh sach vi du cua dac ta goc BI BO co y: no trung voi
# `RANK_TIERS[1].title`.

@dataclass(frozen=True)
class LevelTier:
    key: str
    title: str
    min_xp: int
    level: int


#: Nguong CHO PHAT TRIEN, cung triet ly voi `RANK_TIERS` — xem lai bang so
#: lieu that truoc khi mo cho nguoi dung that.
LEVEL_TIERS: Tuple[LevelTier, ...] = (
    LevelTier("lu_khach", "Lữ Khách", 0, 1),
    LevelTier("ke_du_hanh_thu_gioi", "Kẻ Du Hành Thư Giới", 100, 2),
    LevelTier("hoc_gia_ma_phap", "Học Giả Ma Pháp", 500, 3),
    LevelTier("nguoi_giu_thu_vien", "Người Giữ Thư Viện", 2_000, 4),
    LevelTier("su_gia_thu_gioi", "Sứ Giả Thư Giới", 8_000, 5),
    LevelTier("dai_hien_gia_thu_gioi", "Đại Hiền Giả Thư Giới", 30_000, 6),
)


def level_for(xp: int) -> LevelTier:
    """Cung cong thuc voi `creator.rank_for` — bac cao nhat ma XP nay dat toi."""
    dat = LEVEL_TIERS[0]
    for tier in LEVEL_TIERS:
        if xp >= tier.min_xp:
            dat = tier
        else:
            break
    return dat


def next_level(xp: int) -> Optional[LevelTier]:
    for tier in LEVEL_TIERS:
        if xp < tier.min_xp:
            return tier
    return None


#: Diem XP cho tung SU KIEN may chu xac nhan — KHONG BAO GIO nhan gia tri XP
#: tu client. Danh sach nay la GIA TRI, chua phai noi CAP: noi cap that (khi
#: co bang `xp_ledger`) phai tu mot key DUY NHAT moi su kien (vi du
#: `id_xp_entry(user_id, "publish_chapter", chapter_id)`) de mot su kien chi
#: cong XP dung MOT LAN, giong ky thuat `credit_key` cua `creator.py`.
XP_EVENTS: Dict[str, int] = {
    "publish_first_novel": 50,
    "publish_first_chapter": 20,
    "publish_chapter": 10,
    "listen_milestone_qualified": 5,
    "community_contribution": 5,
    "translation_project_completed": 20,
}


def id_xp_entry(user_id: str, event_type: str, source_id: str) -> str:
    """
    ID TAT DINH cho MOT lan cong XP: cung (user_id, event_type, source_id)
    LUON ra cung mot id — o MOI tien trinh, MOI lan chay, MOI worker.

    Dung `hashlib.sha256` chu KHONG dung `hash()` cua Python: `hash()` tren
    str/tuple duoc "muoi" ngau nhien theo `PYTHONHASHSEED` MOI KHI tien
    trinh Python khoi dong (chong tan cong hash-flooding) — nghia la cung
    mot bo ba tren HAI tien trinh khac nhau (vi du sau khi restart server,
    hoac hai worker gunicorn khac nhau) se ra HAI id KHAC NHAU. Voi kho
    trong bo nho (`MockGamificationStore`, chi song trong MOT tien trinh)
    dieu do vo hai, nhung vua pha vo dung yeu cau idempotent-qua-restart ma
    `AppwriteGamificationStore` can co — mot lan thu lai sau khi server
    restart se sinh entry_id moi va CONG XP LAN HAI. `sha256` khong phu
    thuoc tien trinh, nen id luon giong het nhau bat ke chay o dau.
    """
    khoa = "\x1f".join((user_id, event_type, source_id)).encode("utf-8")
    return f"xp_{hashlib.sha256(khoa).hexdigest()[:24]}"


def id_mo_khoa_thanh_tuu(user_id: str, achievement_key: str) -> str:
    """ID TAT DINH cho MOT ban ghi mo khoa thanh tuu — cung ky thuat va cung
    ly do voi `id_xp_entry` (sha256, khong dung `hash()`): dung lam Appwrite
    documentId de chinh Appwrite cuong che "mot nguoi chi mo MOT lan cho MOI
    thanh tuu", khong can doc-truoc-roi-ghi."""
    khoa = "\x1f".join((user_id, achievement_key)).encode("utf-8")
    return f"au_{hashlib.sha256(khoa).hexdigest()[:24]}"


def id_vat_pham_kho(user_id: str, cosmetic_key: str) -> str:
    """ID TAT DINH cho MOT hang trong kho vat pham — cung ky thuat voi
    `id_xp_entry`/`id_mo_khoa_thanh_tuu`: Appwrite tu choi tao hang thu hai
    cung id, nen rut trung vat pham tu nhien khong tao ban sao."""
    khoa = "\x1f".join((user_id, cosmetic_key)).encode("utf-8")
    return f"ci_{hashlib.sha256(khoa).hexdigest()[:24]}"


def id_thuong_nhiem_vu(user_id: str, quest_key: str, period_key: str) -> str:
    """ID TAT DINH cho MOT lan nhan thuong nhiem vu, dung LAM `entry_id`
    trong CUNG nhat ky XP voi `id_xp_entry` — cung ky thuat (sha256), khac
    tien to de doc nhat ky de phan biet nguon. `period_key` doi (ky moi) la
    mot ID KHAC, nen nhiem vu cua ky moi nhan thuong duoc, khong bi coi la
    "da nhan roi" cua ky truoc."""
    khoa = "\x1f".join((user_id, "quest_reward", quest_key, period_key)).encode("utf-8")
    return f"qr_{hashlib.sha256(khoa).hexdigest()[:24]}"


def id_tien_do_nhiem_vu(user_id: str, quest_key: str, period_key: str) -> str:
    """ID TAT DINH cho MOT hang tien do nhiem vu (user_id, quest_key,
    period_key) — cung ky thuat voi cac ham `id_*` khac o tren. `period_key`
    doi (ngay/tuan khac) nghia la mot ID KHAC, tuc mot HANG MOI — day chinh
    la co che "reset" tu nhien cua nhiem vu, khong can xoa hay ghi de gi."""
    khoa = "\x1f".join((user_id, quest_key, period_key)).encode("utf-8")
    return f"qp_{hashlib.sha256(khoa).hexdigest()[:24]}"


def title_unlocked(xp: int, title_key: str) -> bool:
    """Danh xung `title_key` co MO KHOA voi `xp` hien tai hay khong."""
    tier = next((t for t in LEVEL_TIERS if t.key == title_key), None)
    return tier is not None and xp >= tier.min_xp


# =============================================================================
# Vat pham suu tam — catalog THAT (Phan K, V4 visual completion vong 2)
# =============================================================================
#
# Tai san la THAM CHIEU (`asset_ref`) toi mot component SVG/CSS o frontend
# (`web/src/components/cosmetics/`), KHONG PHAI anh — khong nhan vat hoat
# hinh co ban quyen, dung phong cach huyen ao TIET CHE nhu phan con lai cua
# giao dien (xem `web/src/app/globals.css`, khoi "hoa van huyen ao").

COSMETIC_CATALOG: Tuple[CosmeticDef, ...] = (
    # --- khung avatar (5, moi bac hiem mot cai) -----------------------------
    CosmeticDef("khung_go", "Khung Gỗ Mộc", "common", "avatar_frame", "frame_go"),
    CosmeticDef("khung_bac", "Khung Bạc Cổ", "rare", "avatar_frame", "frame_bac"),
    CosmeticDef("khung_ngoc", "Khung Ngọc Bích", "epic", "avatar_frame", "frame_ngoc"),
    CosmeticDef("khung_vang", "Khung Vàng Hoàng Gia", "legendary", "avatar_frame", "frame_vang"),
    CosmeticDef("khung_sao", "Khung Tinh Tú", "mythic", "avatar_frame", "frame_sao"),
    # --- hoa tiet ho so (3) --------------------------------------------------
    CosmeticDef("hoa_van_la", "Hoạ Tiết Lá Rừng", "common", "profile_ornament", "ornament_la"),
    CosmeticDef("hoa_van_may", "Hoạ Tiết Mây Trời", "rare", "profile_ornament", "ornament_may"),
    CosmeticDef("hoa_van_sao_bang", "Hoạ Tiết Sao Băng", "epic", "profile_ornament", "ornament_sao_bang"),
    # --- huy hieu (5) ---------------------------------------------------------
    CosmeticDef("huy_hieu_but_long", "Huy Hiệu Bút Lông", "common", "badge", "badge_but_long"),
    CosmeticDef("huy_hieu_cuon_giay", "Huy Hiệu Cuộn Giấy Cổ", "common", "badge", "badge_cuon_giay"),
    CosmeticDef("huy_hieu_la_ban_sao", "Huy Hiệu La Bàn Sao", "rare", "badge", "badge_la_ban"),
    CosmeticDef("huy_hieu_dom_lua", "Huy Hiệu Đốm Lửa Ma Thuật", "epic", "badge", "badge_dom_lua"),
    CosmeticDef("huy_hieu_phuong_hoang", "Huy Hiệu Phượng Hoàng Tro Tàn", "legendary", "badge", "badge_phuong_hoang"),
)

#: Goi thuong MIEN PHI duy nhat cua Giai doan 1 — cap khi len bac (xem
#: `gamification_service.award_xp`). Trong so THEO DO HIEM, cong khai duoc.
REWARD_PACKS: Tuple[RewardPack, ...] = (
    RewardPack("goi_len_bac", "Gói Lên Bậc",
              {"common": 120, "rare": 54, "epic": 20, "legendary": 5, "mythic": 1}),
)


def cosmetic_pool_for_pack(pack_key: str) -> Tuple[CosmeticDef, ...]:
    """Toan bo catalog la mot ho boi DUY NHAT trong Giai doan 1 — chua co
    goi rieng theo vi tri trang bi."""
    return COSMETIC_CATALOG


# =============================================================================
# Nhiem vu (quest) — V4 visual completion, vong 5.
# =============================================================================
#
# `event_type` doi chieu VOI SU KIEN THAT MAY CHU DA XAC NHAN (doc chuong,
# nghe, binh luan, dang bai) — cung triet ly voi `XP_EVENTS`: khong bao gio
# nhan tien do tu client, chi dem su kien server tu ghi nhan. Phan thuong
# nhiem vu la GIA TRI CO DINH da biet truoc (khac goi gacha ngau nhien): lam
# xong dung viec do thi chac chan nhan dung phan thuong do, khong may rui.
QUEST_CATALOG: Tuple[QuestDef, ...] = (
    # --- hang ngay (reset moi ngay UTC) --------------------------------------
    QuestDef(
        key="doc_hang_ngay", name="Đọc một chương",
        description="Đọc ít nhất một chương truyện hôm nay.",
        period="daily", event_type="chapter_read",
        target_count=1, xp_reward=10),
    QuestDef(
        key="nghe_hang_ngay", name="Nghe một chương",
        description="Nghe ít nhất một chương audio hôm nay.",
        period="daily", event_type="chapter_listened",
        target_count=1, xp_reward=10),
    QuestDef(
        key="binh_luan_hang_ngay", name="Để lại một bình luận",
        description="Bình luận một chương hoặc bài đăng hôm nay.",
        period="daily", event_type="comment_posted",
        target_count=1, xp_reward=10),
    # --- hang tuan (reset moi tuan ISO, thu Hai) ------------------------------
    QuestDef(
        key="doc_5_chuong_tuan", name="Đọc 5 chương trong tuần",
        description="Đọc đủ 5 chương truyện trong tuần này.",
        period="weekly", event_type="chapter_read",
        target_count=5, xp_reward=50),
    QuestDef(
        key="nghe_5_chuong_tuan", name="Nghe 5 chương trong tuần",
        description="Nghe đủ 5 chương audio trong tuần này.",
        period="weekly", event_type="chapter_listened",
        target_count=5, xp_reward=50),
    QuestDef(
        key="tuong_tac_cong_dong_tuan", name="Gắn bó cộng đồng",
        description="Bình luận hoặc đăng bài 3 lần trong tuần này.",
        period="weekly", event_type="community_interaction",
        target_count=3, xp_reward=40, cosmetic_reward_key="huy_hieu_but_long"),
)


def quests_for_period(period: str) -> Tuple[QuestDef, ...]:
    return tuple(q for q in QUEST_CATALOG if q.period == period)
