"""
V4 visual completion, vong 2 — tang service gamification (`GamificationService`
khong ton tai nhu mot class, chi la mot module ham thuan nhan `store`).
"""

from __future__ import annotations

import random
import unittest

from server.adapters import MockIdentityAdapter
from server.gamification_service import (
    GamificationError,
    achievements_hien_thi,
    award_xp,
    cap_do_hien_thi,
    claim_quest_reward,
    equip_cosmetic,
    equip_title,
    leaderboard_all_time,
    leaderboard_weekly,
    list_quests_with_progress,
    open_reward_pack,
    record_daily_read,
    record_quest_event,
    reset_xp_earned_since_cache_for_test,
    streak_hien_thi,
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


class RecordDailyReadTest(unittest.TestCase):
    def setUp(self):
        self.store = MockGamificationStore()

    def test_lan_dau_bat_dau_chuoi(self):
        s = record_daily_read(self.store, "u1", "2026-08-15")
        self.assertEqual(streak_hien_thi(s)["current_streak"], 1)

    def test_goi_lai_cung_ngay_khong_ghi_lai(self):
        record_daily_read(self.store, "u1", "2026-08-15")
        s = record_daily_read(self.store, "u1", "2026-08-15")
        self.assertEqual(s.current_streak, 1)

    def test_luu_lai_qua_kho(self):
        record_daily_read(self.store, "u1", "2026-08-15")
        record_daily_read(self.store, "u1", "2026-08-16")
        self.assertEqual(self.store.get_streak("u1").current_streak, 2)


class QuestServiceTest(unittest.TestCase):
    def setUp(self):
        self.store = MockGamificationStore()

    def test_danh_sach_nhiem_vu_mac_dinh_tien_do_0(self):
        qs = list_quests_with_progress(self.store, "u1", "2026-08-15")
        self.assertEqual(len(qs), 6)
        self.assertTrue(all(q["count"] == 0 for q in qs))
        self.assertTrue(all(not q["completed"] for q in qs))

    def test_su_kien_khong_khop_nhiem_vu_nao_thi_khong_lam_gi(self):
        record_quest_event(self.store, "u1", "su_kien_la", "2026-08-15")
        self.assertEqual(self.store.list_quest_progress("u1"), [])

    def test_su_kien_cong_ca_nhiem_vu_ngay_lan_tuan_khop(self):
        # "chapter_read" khop CA "doc_hang_ngay" (daily) lan
        # "doc_5_chuong_tuan" (weekly).
        record_quest_event(self.store, "u1", "chapter_read", "2026-08-15")
        qs = {q["key"]: q for q in
              list_quests_with_progress(self.store, "u1", "2026-08-15")}
        self.assertEqual(qs["doc_hang_ngay"]["count"], 1)
        self.assertTrue(qs["doc_hang_ngay"]["completed"])
        self.assertEqual(qs["doc_5_chuong_tuan"]["count"], 1)
        self.assertFalse(qs["doc_5_chuong_tuan"]["completed"])  # can 5

    def test_dem_khong_vuot_qua_muc_tieu_khi_hien_thi(self):
        for _ in range(10):
            record_quest_event(self.store, "u1", "chapter_read", "2026-08-15")
        qs = {q["key"]: q for q in
              list_quests_with_progress(self.store, "u1", "2026-08-15")}
        self.assertEqual(qs["doc_hang_ngay"]["count"], 1)  # target=1, khong "11"

    def test_ky_moi_reset_tu_nhien(self):
        record_quest_event(self.store, "u1", "chapter_read", "2026-08-15")
        qs_ngay_khac = {q["key"]: q for q in
                        list_quests_with_progress(self.store, "u1", "2026-08-16")}
        self.assertEqual(qs_ngay_khac["doc_hang_ngay"]["count"], 0)

    def test_claim_chua_hoan_thanh_bi_tu_choi(self):
        with self.assertRaises(GamificationError):
            claim_quest_reward(self.store, "u1", "doc_hang_ngay", "2026-08-15")

    def test_claim_nhiem_vu_khong_ton_tai_bi_tu_choi(self):
        with self.assertRaises(GamificationError):
            claim_quest_reward(self.store, "u1", "khong_ton_tai", "2026-08-15")

    def test_claim_thanh_cong_cong_dung_xp(self):
        record_quest_event(self.store, "u1", "chapter_read", "2026-08-15")
        ket_qua = claim_quest_reward(self.store, "u1", "doc_hang_ngay", "2026-08-15")
        self.assertEqual(ket_qua["xp_awarded"], 10)
        self.assertEqual(self.store.get_progress("u1").xp, 10)

    def test_claim_hai_lan_bi_tu_choi_lan_hai(self):
        record_quest_event(self.store, "u1", "chapter_read", "2026-08-15")
        claim_quest_reward(self.store, "u1", "doc_hang_ngay", "2026-08-15")
        with self.assertRaises(GamificationError):
            claim_quest_reward(self.store, "u1", "doc_hang_ngay", "2026-08-15")
        # XP chi cong MOT lan, khong phai hai.
        self.assertEqual(self.store.get_progress("u1").xp, 10)

    def test_claim_nhiem_vu_co_vat_pham_thi_cap_vat_pham(self):
        for _ in range(3):
            record_quest_event(self.store, "u1", "community_interaction",
                               "2026-08-15")
        ket_qua = claim_quest_reward(
            self.store, "u1", "tuong_tac_cong_dong_tuan", "2026-08-15")
        self.assertEqual(ket_qua["cosmetic"]["key"], "huy_hieu_but_long")
        muc = self.store.get_cosmetic("u1", "huy_hieu_but_long")
        self.assertIsNotNone(muc)


class LeaderboardServiceTest(unittest.TestCase):
    def setUp(self):
        self.store = MockGamificationStore()
        self.identity = MockIdentityAdapter()
        # Cache TTL cua xp_earned_since() la MODULE-LEVEL (dung chung mot
        # tien trinh) — bat buoc reset giua cac test, khong thi mot test
        # dung LAI cung `since_iso` voi test truoc se doc nham ket qua da
        # cache cua store CU (xem test_weekly_cache_khong_ro_ri_qua_cac_lan_goi).
        reset_xp_earned_since_cache_for_test()

    def test_all_time_sap_giam_dan_va_danh_dau_nguoi_xem(self):
        u1 = self.identity.register("u1@x.com", "MatKhau123", "Một")
        u2 = self.identity.register("u2@x.com", "MatKhau123", "Hai")
        award_xp(self.store, u1.user_id, "publish_first_novel",
                source_kind="novel", source_id=u1.user_id)
        award_xp(self.store, u2.user_id, "publish_first_novel",
                source_kind="novel", source_id=u2.user_id)
        award_xp(self.store, u2.user_id, "publish_chapter",
                source_kind="chapter", source_id="c1")
        lb = leaderboard_all_time(self.store, self.identity, limit=10, offset=0,
                                  viewer_id=u1.user_id)
        self.assertEqual([it["user_id"] for it in lb["items"]],
                         [u2.user_id, u1.user_id])
        self.assertEqual(lb["items"][1]["rank"], 2)
        self.assertTrue(lb["items"][1]["is_you"])
        self.assertIsNone(lb["viewer_entry"])  # da nam trong trang

    def test_viewer_ngoai_trang_van_co_the_rieng(self):
        u1 = self.identity.register("u1@x.com", "MatKhau123", "Một")
        u2 = self.identity.register("u2@x.com", "MatKhau123", "Hai")
        award_xp(self.store, u1.user_id, "publish_first_novel",
                source_kind="novel", source_id=u1.user_id)
        award_xp(self.store, u2.user_id, "publish_first_novel",
                source_kind="novel", source_id=u2.user_id)
        award_xp(self.store, u2.user_id, "publish_chapter",
                source_kind="chapter", source_id="c1")
        lb = leaderboard_all_time(self.store, self.identity, limit=1, offset=0,
                                  viewer_id=u1.user_id)
        self.assertEqual(len(lb["items"]), 1)
        self.assertIsNotNone(lb["viewer_entry"])
        self.assertEqual(lb["viewer_entry"]["rank"], 2)
        self.assertEqual(lb["viewer_entry"]["user_id"], u1.user_id)

    def test_weekly_chi_tinh_xp_trong_khoang_thoi_gian(self):
        u1 = self.identity.register("u1@x.com", "MatKhau123", "Một")
        award_xp(self.store, u1.user_id, "publish_first_novel",
                source_kind="novel", source_id=u1.user_id)
        lb_qua_khu = leaderboard_weekly(
            self.store, self.identity, limit=10, offset=0,
            since_iso="2099-01-01T00:00:00+00:00", viewer_id=u1.user_id)
        self.assertEqual(lb_qua_khu["items"], [])
        lb_hien_tai = leaderboard_weekly(
            self.store, self.identity, limit=10, offset=0,
            since_iso="2000-01-01T00:00:00+00:00", viewer_id=u1.user_id)
        self.assertEqual(len(lb_hien_tai["items"]), 1)

    def test_the_bang_xep_hang_kem_avatar_va_danh_xung(self):
        class _KhoAnhGia:
            def signed_url(self, key, expires_seconds=3600, download_name=None):
                return f"https://cdn.test/{key}?sig=abc"

        u1 = self.identity.register("u1@x.com", "MatKhau123", "Một")
        u1.avatar_key = "avt/u1.png"
        self.identity.save_profile(u1)
        award_xp(self.store, u1.user_id, "publish_first_novel",
                source_kind="novel", source_id=u1.user_id)
        equip_title(self.store, u1.user_id, "")  # danh xung mac dinh theo bac

        lb = leaderboard_all_time(self.store, self.identity, _KhoAnhGia(),
                                  limit=10, offset=0, viewer_id=u1.user_id)
        hang_dau = lb["items"][0]
        self.assertEqual(hang_dau["avatar_url"], "https://cdn.test/avt/u1.png?sig=abc")
        self.assertTrue(hang_dau["title"])

        lb_tuan = leaderboard_weekly(
            self.store, self.identity, _KhoAnhGia(), limit=10, offset=0,
            since_iso="2000-01-01T00:00:00+00:00", viewer_id=u1.user_id)
        self.assertEqual(lb_tuan["items"][0]["avatar_url"],
                         "https://cdn.test/avt/u1.png?sig=abc")
        self.assertEqual(lb_tuan["items"][0]["title"], hang_dau["title"])

    def test_weekly_khong_quet_lai_nhat_ky_xp_trong_ttl(self):
        """docs/reports/appwrite-read-audit.md — nguyen nhan doc Appwrite ro
        rang nhat: moi lan mo tab 'tuan nay' quet LAI toan bo nhat ky XP.
        Hai lan goi cung `since_iso` trong TTL CHI duoc goi `xp_earned_since`
        MOT lan xuong kho that."""
        u1 = self.identity.register("u1@x.com", "MatKhau123", "Một")
        award_xp(self.store, u1.user_id, "publish_first_novel",
                source_kind="novel", source_id=u1.user_id)

        so_lan_goi = {"n": 0}
        goc = self.store.xp_earned_since

        def dem(since_iso):
            so_lan_goi["n"] += 1
            return goc(since_iso)

        self.store.xp_earned_since = dem

        since_iso = "2000-01-01T00:00:00+00:00"
        lb1 = leaderboard_weekly(self.store, self.identity, limit=10, offset=0,
                                 since_iso=since_iso, viewer_id=u1.user_id)
        lb2 = leaderboard_weekly(self.store, self.identity, limit=10, offset=0,
                                 since_iso=since_iso, viewer_id=u1.user_id)

        self.assertEqual(so_lan_goi["n"], 1)
        self.assertEqual(lb1["items"], lb2["items"])

    def test_weekly_since_iso_khac_nhau_khong_dung_chung_cache(self):
        """Doi tuan (since_iso khac) PHAI goi lai kho that — cache khong
        duoc phep tra ve du lieu cua tuan khac."""
        u1 = self.identity.register("u1@x.com", "MatKhau123", "Một")
        award_xp(self.store, u1.user_id, "publish_first_novel",
                source_kind="novel", source_id=u1.user_id)

        so_lan_goi = {"n": 0}
        goc = self.store.xp_earned_since

        def dem(since_iso):
            so_lan_goi["n"] += 1
            return goc(since_iso)

        self.store.xp_earned_since = dem

        leaderboard_weekly(self.store, self.identity, limit=10, offset=0,
                           since_iso="2000-01-01T00:00:00+00:00", viewer_id=u1.user_id)
        leaderboard_weekly(self.store, self.identity, limit=10, offset=0,
                           since_iso="2099-01-01T00:00:00+00:00", viewer_id=u1.user_id)

        self.assertEqual(so_lan_goi["n"], 2)


if __name__ == "__main__":
    unittest.main()
