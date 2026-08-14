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


if __name__ == "__main__":
    unittest.main()
