"""
V4 visual completion, vong 2 — tang service gamification (`GamificationService`
khong ton tai nhu mot class, chi la mot module ham thuan nhan `store`).
"""

from __future__ import annotations

import random
import unittest

from server.gamification_service import (
    GamificationError,
    achievements_hien_thi,
    award_xp,
    cap_do_hien_thi,
    equip_cosmetic,
    equip_title,
    open_reward_pack,
    sync_achievements,
)
from server.gamification_domain import CosmeticInventoryItem
from server.gamification_store import MockGamificationStore


class AwardXpTest(unittest.TestCase):
    def setUp(self):
        self.store = MockGamificationStore()

    def test_su_kien_khong_ton_tai_bi_tu_choi(self):
        with self.assertRaises(GamificationError):
            award_xp(self.store, "u1", "khong_ton_tai",
                     source_kind="x", source_id="1")

    def test_cong_dung_gia_tri_tu_bang(self):
        p = award_xp(self.store, "u1", "publish_first_novel",
                     source_kind="novel", source_id="nov_1")
        self.assertEqual(p.xp, 50)

    def test_cung_su_kien_goi_lai_khong_cong_them(self):
        award_xp(self.store, "u1", "publish_first_novel",
                source_kind="novel", source_id="nov_1")
        ket_qua_2 = award_xp(self.store, "u1", "publish_first_novel",
                             source_kind="novel", source_id="nov_1")
        self.assertIsNone(ket_qua_2)
        self.assertEqual(self.store.get_progress("u1").xp, 50)

    def test_nguon_khac_thi_duoc_cong_them(self):
        award_xp(self.store, "u1", "publish_chapter",
                source_kind="chapter", source_id="chp_1")
        award_xp(self.store, "u1", "publish_chapter",
                source_kind="chapter", source_id="chp_2")
        self.assertEqual(self.store.get_progress("u1").xp, 20)

    def test_len_bac_thi_duoc_cap_goi_thuong(self):
        # 50 (truyen) + 6*10 (chuong) = 110 -> vuot nguong bac 2 (100).
        award_xp(self.store, "u1", "publish_first_novel",
                source_kind="novel", source_id="nov_1")
        for i in range(6):
            award_xp(self.store, "u1", "publish_chapter",
                    source_kind="chapter", source_id=f"chp_{i}")
        p = self.store.get_progress("u1")
        self.assertEqual(p.goi_thuong_dang_cho, 1)

    def test_khong_len_bac_thi_khong_cap_goi(self):
        award_xp(self.store, "u1", "publish_chapter",
                source_kind="chapter", source_id="chp_1")
        self.assertEqual(self.store.get_progress("u1").goi_thuong_dang_cho, 0)

    def test_nhat_ky_ghi_lai_dung_so_su_kien(self):
        award_xp(self.store, "u1", "publish_chapter",
                source_kind="chapter", source_id="chp_1")
        award_xp(self.store, "u1", "publish_chapter",
                source_kind="chapter", source_id="chp_1")  # trung, bo qua
        award_xp(self.store, "u1", "publish_chapter",
                source_kind="chapter", source_id="chp_2")
        self.assertEqual(len(self.store.list_xp_events("u1")), 2)


class CapDoHienThiTest(unittest.TestCase):
    def test_chua_co_xp_thi_bac_1_danh_xung_mac_dinh(self):
        store = MockGamificationStore()
        disp = cap_do_hien_thi(store.get_progress("moi"))
        self.assertEqual(disp["level"], 1)
        self.assertEqual(disp["current_level_xp"], 0)
        self.assertEqual(disp["progress_percent"], 0)
        self.assertIsNotNone(disp["next_level_xp"])

    def test_bac_toi_da_thi_next_level_none_va_100_phan_tram(self):
        store = MockGamificationStore()
        p = store.get_progress("u1")
        p.xp = 999_999
        store.save_progress(p)
        disp = cap_do_hien_thi(store.get_progress("u1"))
        self.assertIsNone(disp["next_level_xp"])
        self.assertEqual(disp["progress_percent"], 100)


class EquipTitleTest(unittest.TestCase):
    def setUp(self):
        self.store = MockGamificationStore()

    def test_chua_mo_khoa_thi_bi_tu_choi(self):
        with self.assertRaises(GamificationError):
            equip_title(self.store, "u1", "dai_hien_gia_thu_gioi")

    def test_da_mo_khoa_thi_trang_bi_duoc(self):
        award_xp(self.store, "u1", "publish_first_novel",
                source_kind="novel", source_id="nov_1")  # 50 xp, bac 1
        p = equip_title(self.store, "u1", "lu_khach")
        self.assertEqual(p.equipped_title_key, "lu_khach")

    def test_chuoi_rong_tra_ve_danh_xung_mac_dinh(self):
        p = equip_title(self.store, "u1", "")
        self.assertEqual(p.equipped_title_key, "")
        self.assertEqual(cap_do_hien_thi(p)["equipped_title_key"], "lu_khach")

    def test_khoa_khong_ton_tai_bi_tu_choi(self):
        with self.assertRaises(GamificationError):
            equip_title(self.store, "u1", "khong_ton_tai")


class AchievementsHienThiTest(unittest.TestCase):
    def test_dong_bo_va_doc_lai_dung_unlocked_at(self):
        store = MockGamificationStore()
        ds = achievements_hien_thi(
            store, "u1", so_truyen_xuat_ban=1, so_chuong_xuat_ban=1,
            ky_tu_da_tong_hop=0, phut_da_nghe=0)
        theo_khoa = {a["key"]: a for a in ds}
        self.assertTrue(theo_khoa["chuong_dau_tien"]["unlocked"])
        self.assertIsNotNone(theo_khoa["chuong_dau_tien"]["unlocked_at"])
        self.assertFalse(theo_khoa["cat_tieng"]["unlocked"])

    def test_goi_lai_khong_doi_moc_thoi_gian_da_mo(self):
        store = MockGamificationStore()
        a1 = achievements_hien_thi(
            store, "u1", so_truyen_xuat_ban=1, so_chuong_xuat_ban=1,
            ky_tu_da_tong_hop=0, phut_da_nghe=0)
        a2 = achievements_hien_thi(
            store, "u1", so_truyen_xuat_ban=1, so_chuong_xuat_ban=1,
            ky_tu_da_tong_hop=0, phut_da_nghe=0)
        moc1 = next(a for a in a1 if a["key"] == "chuong_dau_tien")["unlocked_at"]
        moc2 = next(a for a in a2 if a["key"] == "chuong_dau_tien")["unlocked_at"]
        self.assertEqual(moc1, moc2)

    def test_khong_mat_thanh_tuu_da_mo_du_du_lieu_sau_giam(self):
        # Vi du: truyen bi xoa sau khi da mo thanh tuu — thanh tuu KHONG bi
        # thu hoi (mo khoa la MOT MOC, khong phai mot dieu kien giam sat lien tuc).
        store = MockGamificationStore()
        sync_achievements(store, "u1", so_truyen_xuat_ban=1, so_chuong_xuat_ban=1,
                          ky_tu_da_tong_hop=0, phut_da_nghe=0)
        ds = achievements_hien_thi(
            store, "u1", so_truyen_xuat_ban=0, so_chuong_xuat_ban=0,
            ky_tu_da_tong_hop=0, phut_da_nghe=0)
        theo_khoa = {a["key"]: a for a in ds}
        self.assertTrue(theo_khoa["ra_mat_tieu_thuyet"]["unlocked"])


class CosmeticFlowTest(unittest.TestCase):
    def setUp(self):
        self.store = MockGamificationStore()

    def _len_bac_2(self, user_id="u1"):
        award_xp(self.store, user_id, "publish_first_novel",
                source_kind="novel", source_id="nov_1")
        for i in range(6):
            award_xp(self.store, user_id, "publish_chapter",
                    source_kind="chapter", source_id=f"chp_{i}")

    def test_mo_goi_thi_tru_dung_mot_goi_dang_cho(self):
        self._len_bac_2()
        self.assertEqual(self.store.get_progress("u1").goi_thuong_dang_cho, 1)
        open_reward_pack(self.store, "u1", "goi_len_bac", random.Random(1))
        self.assertEqual(self.store.get_progress("u1").goi_thuong_dang_cho, 0)

    def test_khong_con_goi_thi_tu_choi(self):
        with self.assertRaises(GamificationError):
            open_reward_pack(self.store, "u1", "goi_len_bac", random.Random(1))

    def test_goi_khong_ton_tai_bi_tu_choi(self):
        self._len_bac_2()
        with self.assertRaises(GamificationError):
            open_reward_pack(self.store, "u1", "goi_khong_ton_tai", random.Random(1))

    def test_seed_giong_nhau_ra_vat_pham_giong_nhau(self):
        self._len_bac_2("u1")
        self._len_bac_2("u2")
        c1, _ = open_reward_pack(self.store, "u1", "goi_len_bac", random.Random(99))
        c2, _ = open_reward_pack(self.store, "u2", "goi_len_bac", random.Random(99))
        self.assertEqual(c1.key, c2.key)

    def test_trang_bi_vat_pham_chua_co_bi_tu_choi(self):
        with self.assertRaises(GamificationError):
            equip_cosmetic(self.store, "u1", "khung_go")

    def test_trang_bi_vat_pham_da_co(self):
        self._len_bac_2()
        cosmetic, _ = open_reward_pack(self.store, "u1", "goi_len_bac", random.Random(1))
        muc = equip_cosmetic(self.store, "u1", cosmetic.key)
        self.assertTrue(muc.equipped)

    def test_trang_bi_vi_tri_moi_thi_bo_trang_bi_cai_cu_cung_vi_tri(self):
        # Cap thang cho ca hai khung avatar (cung slot) roi trang bi lan luot.
        self.store.grant_cosmetic(
            CosmeticInventoryItem(user_id="u1", cosmetic_key="khung_go"))
        self.store.grant_cosmetic(
            CosmeticInventoryItem(user_id="u1", cosmetic_key="khung_bac"))
        equip_cosmetic(self.store, "u1", "khung_go")
        equip_cosmetic(self.store, "u1", "khung_bac")
        kho = {m.cosmetic_key: m for m in self.store.list_cosmetics("u1")}
        self.assertFalse(kho["khung_go"].equipped)
        self.assertTrue(kho["khung_bac"].equipped)


if __name__ == "__main__":
    unittest.main()
