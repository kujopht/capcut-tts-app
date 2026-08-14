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

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


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
    "publish_chapter": 10,
    "listen_milestone_qualified": 5,
    "community_contribution": 5,
    "translation_project_completed": 20,
}


def id_xp_entry(user_id: str, event_type: str, source_id: str) -> str:
    """
    ID TAT DINH cho MOT lan cong XP — cung ky thuat voi
    `translation_domain.id_ket_noi_provider`/`creator.credit_key`: cung
    (user_id, event_type, source_id) luon ra CUNG mot id, nen ghi lai lan
    hai chi la upsert vo hai thay vi cong don sai.
    """
    return f"xp_{abs(hash((user_id, event_type, source_id))) % (10 ** 12):012x}"
