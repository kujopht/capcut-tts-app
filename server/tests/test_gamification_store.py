"""V4 visual completion, vong 2 — `MockGamificationStore` (kiem truc tiep,
khong qua tang service)."""

from __future__ import annotations

import unittest

from server.adapters import NotFoundError
from server.gamification_domain import (
    CosmeticInventoryItem,
    UnlockedAchievement,
    UserProgress,
    XpLedgerEntry,
)
from server.gamification_store import MockGamificationStore


class ProgressTest(unittest.TestCase):
    def test_chua_co_thi_tra_ve_mac_dinh_khong_luu(self):
        store = MockGamificationStore()
        p = store.get_progress("u1")
        self.assertEqual(p.xp, 0)
        # Khong tu luu — goi lai lan hai van la doi tuong moi.
        self.assertEqual(len(store.list_xp_events("u1")), 0)

    def test_luu_roi_doc_lai_dung_gia_tri(self):
        store = MockGamificationStore()
        p = UserProgress(user_id="u1", xp=42)
        store.save_progress(p)
        self.assertEqual(store.get_progress("u1").xp, 42)


class XpEventTest(unittest.TestCase):
    def test_entry_id_da_co_thi_tra_false_khong_ghi_de(self):
        store = MockGamificationStore()
        e1 = XpLedgerEntry(entry_id="xp_1", user_id="u1", event_type="a",
                           source_kind="k", source_id="1", xp_awarded=10)
        e2 = XpLedgerEntry(entry_id="xp_1", user_id="u1", event_type="a",
                           source_kind="k", source_id="1", xp_awarded=999)
        self.assertTrue(store.record_xp_event(e1))
        self.assertFalse(store.record_xp_event(e2))
        self.assertEqual(store.list_xp_events("u1")[0].xp_awarded, 10)


class AchievementTest(unittest.TestCase):
    def test_mo_khoa_lan_hai_tra_false(self):
        store = MockGamificationStore()
        rec = UnlockedAchievement(user_id="u1", achievement_key="a")
        self.assertTrue(store.unlock_achievement(rec))
        self.assertFalse(store.unlock_achievement(rec))
        self.assertEqual(len(store.list_unlocked_achievements("u1")), 1)


class CosmeticTest(unittest.TestCase):
    def test_cap_trung_lap_tra_none(self):
        store = MockGamificationStore()
        item = CosmeticInventoryItem(user_id="u1", cosmetic_key="khung_go")
        self.assertIsNotNone(store.grant_cosmetic(item))
        self.assertIsNone(store.grant_cosmetic(
            CosmeticInventoryItem(user_id="u1", cosmetic_key="khung_go")))
        self.assertEqual(len(store.list_cosmetics("u1")), 1)

    def test_dat_equipped_vat_pham_khong_co_bao_loi(self):
        store = MockGamificationStore()
        with self.assertRaises(NotFoundError):
            store.set_cosmetic_equipped("u1", "khong_co", True)


class ListXpEventsSinceTest(unittest.TestCase):
    """Social & Play V1 Goi C: `list_xp_events_since` dung cho tran XP hang
    ngay cua mini-game (`games_domain.decide_caro_rewards`/`decide_memory_reward`)."""

    def test_loc_theo_moc_thoi_gian(self):
        store = MockGamificationStore()
        cu = XpLedgerEntry(entry_id="xp_cu", user_id="u1", event_type="game_x",
                           source_kind="game_match", source_id="s1",
                           xp_awarded=2, created_at="2026-01-01T00:00:00+00:00")
        moi = XpLedgerEntry(entry_id="xp_moi", user_id="u1", event_type="game_x",
                            source_kind="game_match", source_id="s2",
                            xp_awarded=3, created_at="2026-01-02T00:00:00+00:00")
        store.record_xp_event(cu)
        store.record_xp_event(moi)
        ds = store.list_xp_events_since("u1", "2026-01-02T00:00:00+00:00")
        self.assertEqual([e.entry_id for e in ds], ["xp_moi"])

    def test_khong_lan_sang_nguoi_khac(self):
        store = MockGamificationStore()
        store.record_xp_event(XpLedgerEntry(
            entry_id="xp_1", user_id="u1", event_type="a", source_kind="k",
            source_id="1", xp_awarded=5))
        self.assertEqual(store.list_xp_events_since("u2", "2000-01-01"), [])


class AwardXpAtomicTest(unittest.TestCase):
    def test_cong_xp_va_ap_dung_tien_do_mot_lan(self):
        store = MockGamificationStore()
        entry = XpLedgerEntry(entry_id="xp_a", user_id="u1", event_type="game_match_completed",
                              source_kind="game_match", source_id="m1|caro-v1", xp_awarded=2)
        progress = store.award_xp_atomic(entry)
        self.assertIsNotNone(progress)
        self.assertEqual(progress.xp, 2)
        self.assertEqual(store.get_progress("u1").xp, 2)
        self.assertEqual(len(store.list_xp_events("u1")), 1)

    def test_trung_entry_id_tra_none_khong_cong_lai(self):
        store = MockGamificationStore()
        entry = XpLedgerEntry(entry_id="xp_b", user_id="u1", event_type="game_match_completed",
                              source_kind="game_match", source_id="m1|caro-v1", xp_awarded=2)
        self.assertIsNotNone(store.award_xp_atomic(entry))
        self.assertIsNone(store.award_xp_atomic(entry))
        self.assertEqual(store.get_progress("u1").xp, 2)

    def test_len_bac_cap_goi_thuong_giong_ap_dung_xp(self):
        store = MockGamificationStore()
        entry = XpLedgerEntry(entry_id="xp_c", user_id="u1", event_type="e",
                              source_kind="k", source_id="s", xp_awarded=100)
        progress = store.award_xp_atomic(entry)
        self.assertEqual(progress.xp, 100)
        self.assertGreaterEqual(progress.goi_thuong_dang_cho, 1)

    def test_20_luong_cung_mot_nguoi_20_entry_khac_nhau(self):
        import threading

        store = MockGamificationStore()

        def work(i: int) -> None:
            store.award_xp_atomic(XpLedgerEntry(
                entry_id=f"xp_thread_{i}", user_id="u1", event_type="e",
                source_kind="k", source_id=str(i), xp_awarded=10))

        threads = [threading.Thread(target=work, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(store.get_progress("u1").xp, 200)
        self.assertEqual(len(store.list_xp_events("u1")), 20)

    def test_20_luong_cung_mot_entry_id_chi_cong_mot_lan(self):
        import threading

        store = MockGamificationStore()
        results = []

        def work() -> None:
            results.append(store.award_xp_atomic(XpLedgerEntry(
                entry_id="xp_same", user_id="u1", event_type="e",
                source_kind="k", source_id="1", xp_awarded=10)))

        threads = [threading.Thread(target=work) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(store.get_progress("u1").xp, 10)
        self.assertEqual(len(store.list_xp_events("u1")), 1)
        self.assertEqual(sum(1 for r in results if r is not None), 1)


if __name__ == "__main__":
    unittest.main()
