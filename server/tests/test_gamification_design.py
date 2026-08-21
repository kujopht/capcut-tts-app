"""
V4 visual completion, Phan G/K/L — THIET KE (chua noi vao route/schema
production). Kiem logic THUAN: cong thuc cap do, id XP tat dinh, rut vat
pham co trong so, xu ly trung lap.
"""

from __future__ import annotations

import random
import unittest

from server.creator import RANK_TIERS
from server.gamification import LEVEL_TIERS, id_xp_entry, level_for, next_level
from server.gamification_domain import (
    CosmeticDef,
    CosmeticInventoryItem,
    ReadingStreak,
    RewardPack,
    RewardPackError,
    advance_streak,
    quest_period_key,
    roll_cosmetic,
    them_vao_kho_neu_chua_co,
)


class KhoaKhongTrungRankTest(unittest.TestCase):
    def test_khoa_cap_do_khong_trung_khoa_hang_tac_gia(self):
        khoa_hang = {t.key for t in RANK_TIERS}
        khoa_cap_do = {t.key for t in LEVEL_TIERS}
        self.assertEqual(khoa_hang & khoa_cap_do, set())

    def test_ten_cap_do_khong_trung_ten_hang_tac_gia(self):
        ten_hang = {t.title for t in RANK_TIERS}
        ten_cap_do = {t.title for t in LEVEL_TIERS}
        self.assertEqual(ten_hang & ten_cap_do, set())


class CapDoTest(unittest.TestCase):
    def test_xp_0_la_bac_thap_nhat(self):
        self.assertEqual(level_for(0).key, LEVEL_TIERS[0].key)

    def test_dung_nguong_thi_len_bac(self):
        nguong = LEVEL_TIERS[1].min_xp
        self.assertEqual(level_for(nguong - 1).key, LEVEL_TIERS[0].key)
        self.assertEqual(level_for(nguong).key, LEVEL_TIERS[1].key)

    def test_bac_cao_nhat_thi_next_level_la_none(self):
        xp_toi_da = LEVEL_TIERS[-1].min_xp + 999_999
        self.assertIsNone(next_level(xp_toi_da))

    def test_nguong_tang_dan_don_dieu(self):
        nguongs = [t.min_xp for t in LEVEL_TIERS]
        self.assertEqual(nguongs, sorted(nguongs))
        self.assertEqual(len(nguongs), len(set(nguongs)))


class IdXpEntryTest(unittest.TestCase):
    def test_tat_dinh_cung_dau_vao_ra_cung_id(self):
        a = id_xp_entry("u1", "publish_chapter", "chp_1")
        b = id_xp_entry("u1", "publish_chapter", "chp_1")
        self.assertEqual(a, b)

    def test_khac_nguon_thi_khac_id(self):
        a = id_xp_entry("u1", "publish_chapter", "chp_1")
        b = id_xp_entry("u1", "publish_chapter", "chp_2")
        self.assertNotEqual(a, b)


class RollCosmeticTest(unittest.TestCase):
    def setUp(self):
        self.pool = [
            CosmeticDef("khung_dong", "Khung Đồng", "common", "avatar_frame", "svg:dong"),
            CosmeticDef("khung_vang", "Khung Vàng", "legendary", "avatar_frame", "svg:vang"),
        ]
        self.pack = RewardPack("goi_co_ban", "Gói Cơ Bản",
                               {"common": 95, "rare": 4, "legendary": 1})

    def test_seed_giong_nhau_ra_ket_qua_giong_nhau(self):
        a = roll_cosmetic(self.pack, self.pool, random.Random(42))
        b = roll_cosmetic(self.pack, self.pool, random.Random(42))
        self.assertEqual(a.key, b.key)

    def test_trong_so_khong_hop_le_thi_bao_loi_ro_rang(self):
        goi_hong = RewardPack("goi_hong", "Gói Hỏng", {"common": 0})
        with self.assertRaises(RewardPackError):
            roll_cosmetic(goi_hong, self.pool, random.Random(1))

    def test_kho_rong_thi_bao_loi(self):
        with self.assertRaises(RewardPackError):
            roll_cosmetic(self.pack, [], random.Random(1))

    def test_chi_rut_trong_pham_vi_trong_so_duong(self):
        # Trong so "legendary" = 0 -> khong bao gio rut trung khung vang.
        goi_khong_hiem = RewardPack("goi_thuong", "Gói Thường",
                                    {"common": 1, "legendary": 0})
        rng = random.Random(7)
        for _ in range(50):
            ket_qua = roll_cosmetic(goi_khong_hiem, self.pool, rng)
            self.assertEqual(ket_qua.rarity, "common")


class TrungLapTest(unittest.TestCase):
    def test_chua_co_thi_them_moi(self):
        muc = them_vao_kho_neu_chua_co([], "u1", "khung_dong")
        self.assertIsNotNone(muc)
        self.assertEqual(muc.cosmetic_key, "khung_dong")

    def test_da_co_thi_khong_them_ban_thu_hai(self):
        kho = [CosmeticInventoryItem(user_id="u1", cosmetic_key="khung_dong")]
        muc = them_vao_kho_neu_chua_co(kho, "u1", "khung_dong")
        self.assertIsNone(muc)

    def test_nguoi_khac_cung_vat_pham_van_them_duoc(self):
        kho = [CosmeticInventoryItem(user_id="u1", cosmetic_key="khung_dong")]
        muc = them_vao_kho_neu_chua_co(kho, "u2", "khung_dong")
        self.assertIsNotNone(muc)


class AdvanceStreakTest(unittest.TestCase):
    """V4 visual completion, vong 5 — chuoi ngay doc. Xem
    `gamification_domain.advance_streak` de biet day du bon truong hop."""

    def test_lan_dau_bat_dau_chuoi_bang_1(self):
        s = advance_streak(ReadingStreak(user_id="u1"), "2026-08-10")
        self.assertEqual(s.current_streak, 1)
        self.assertEqual(s.longest_streak, 1)
        self.assertEqual(s.last_read_date, "2026-08-10")
        self.assertFalse(s.grace_used_this_run)

    def test_goi_lai_cung_ngay_khong_doi_gi(self):
        s1 = advance_streak(ReadingStreak(user_id="u1"), "2026-08-10")
        s2 = advance_streak(s1, "2026-08-10")
        self.assertEqual(s2.current_streak, 1)
        self.assertIs(s2, s1)  # tra ve chinh doi tuong dau vao, khong tao moi

    def test_ngay_lien_tiep_tang_chuoi(self):
        s = advance_streak(ReadingStreak(user_id="u1"), "2026-08-10")
        s = advance_streak(s, "2026-08-11")
        self.assertEqual(s.current_streak, 2)
        self.assertEqual(s.longest_streak, 2)

    def test_bo_lo_dung_mot_ngay_duoc_an_han_cuu(self):
        s = advance_streak(ReadingStreak(user_id="u1"), "2026-08-10")
        s = advance_streak(s, "2026-08-11")
        s = advance_streak(s, "2026-08-13")  # bo qua 08-12
        self.assertEqual(s.current_streak, 3)
        self.assertTrue(s.grace_used_this_run)

    def test_an_han_chi_dung_duoc_mot_lan_moi_chuoi(self):
        s = advance_streak(ReadingStreak(user_id="u1"), "2026-08-10")
        s = advance_streak(s, "2026-08-11")
        s = advance_streak(s, "2026-08-13")  # dung an han lan 1
        s = advance_streak(s, "2026-08-15")  # bo lo 08-14, an han da het -> dut
        self.assertEqual(s.current_streak, 1)
        self.assertFalse(s.grace_used_this_run)

    def test_bo_lo_hai_ngay_lien_tiep_dut_chuoi_ngay_ca_khi_con_an_han(self):
        s = advance_streak(ReadingStreak(user_id="u1"), "2026-08-10")
        s = advance_streak(s, "2026-08-14")  # bo 3 ngay, qua xa de an han cuu
        self.assertEqual(s.current_streak, 1)
        self.assertFalse(s.grace_used_this_run)

    def test_longest_streak_giu_nguyen_sau_khi_dut(self):
        s = advance_streak(ReadingStreak(user_id="u1"), "2026-08-10")
        s = advance_streak(s, "2026-08-11")
        s = advance_streak(s, "2026-08-12")  # longest = 3
        s = advance_streak(s, "2026-08-20")  # dut, ve 1
        self.assertEqual(s.current_streak, 1)
        self.assertEqual(s.longest_streak, 3)


class QuestPeriodKeyTest(unittest.TestCase):
    def test_daily_la_chinh_ngay(self):
        self.assertEqual(quest_period_key("daily", "2026-08-15"), "2026-08-15")

    def test_weekly_dung_tuan_iso(self):
        self.assertEqual(quest_period_key("weekly", "2026-08-15"), "2026-W33")

    def test_weekly_doi_khi_sang_tuan_moi(self):
        # 2026-08-17 la thu Hai, dau tuan ISO ke tiep.
        self.assertEqual(quest_period_key("weekly", "2026-08-17"), "2026-W34")

    def test_chu_ky_khong_xac_dinh_nem_loi(self):
        with self.assertRaises(ValueError):
            quest_period_key("monthly", "2026-08-15")


if __name__ == "__main__":
    unittest.main()
