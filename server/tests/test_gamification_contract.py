"""
HOP DONG giua kho mock va kho Appwrite cho gamification.

Cung ly do ton tai voi `test_translation_contract.py`/`test_appwrite_v2_contract.py`:
`test_gamification_service.py`/`test_gamification_store.py` chay tren
`MockGamificationStore`. Neu ban Appwrite (`server/appwrite_gamification_store.py`)
lech ngu nghia du mot cho — cho phep cong XP hai lan, mo thanh tuu hai lan, cap
vat pham trung — thi toan bo test kia van xanh va he thong van hong o
production ngay khi ap schema that.

Dung lai `FakeAppwrite`/`_bo_client` cua `test_appwrite_v2_contract.py` — cung
MOT ban gia lap REST trong bo nho, khong can xay lai tu dau.
"""

from __future__ import annotations

import unittest

from server.adapters import NotFoundError
from server.appwrite_gamification_store import AppwriteGamificationStore
from server.config import AppwriteSettings
from server.gamification_domain import (
    CosmeticInventoryItem,
    UnlockedAchievement,
    UserProgress,
    XpLedgerEntry,
)
from server.gamification_store import MockGamificationStore
from server.tests.test_appwrite_v2_contract import FakeAppwrite, _bo_client


def _kho_appwrite(fake: FakeAppwrite) -> AppwriteGamificationStore:
    cfg = AppwriteSettings(endpoint="https://x.invalid/v1", project_id="p",
                           api_key="k", database_id="db")
    kho = AppwriteGamificationStore(cfg, client=_bo_client(fake))
    kho._attrs_cache = {}
    return kho


class HopDongGamification(unittest.TestCase):
    """Moi bai duoi day chay tren CA HAI kho — `ten` bao ro ban nao lech."""

    def _cac_kho(self):
        return [("mock", MockGamificationStore()),
                ("appwrite", _kho_appwrite(FakeAppwrite()))]

    # ===================================================== cap do / XP

    def test_progress_mac_dinh_khi_chua_co(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                p = kho.get_progress("u1")
                self.assertEqual(p.user_id, "u1", ten)
                self.assertEqual(p.xp, 0, ten)
                self.assertEqual(p.goi_thuong_dang_cho, 0, ten)

    def test_save_progress_ghi_de_khong_tao_ban_thu_hai(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                p = UserProgress(user_id="u1", xp=50,
                                 updated_at="2026-08-14T00:00:00+00:00")
                kho.save_progress(p)
                p2 = UserProgress(user_id="u1", xp=120,
                                  equipped_title_key="ke_du_hanh_thu_gioi",
                                  goi_thuong_dang_cho=1,
                                  updated_at="2026-08-14T01:00:00+00:00")
                kho.save_progress(p2)
                lai = kho.get_progress("u1")
                self.assertEqual(lai.xp, 120, ten)
                self.assertEqual(lai.equipped_title_key,
                                 "ke_du_hanh_thu_gioi", ten)
                self.assertEqual(lai.goi_thuong_dang_cho, 1, ten)

    def test_progress_hai_nguoi_dung_doc_lap(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.save_progress(UserProgress(user_id="u1", xp=10))
                kho.save_progress(UserProgress(user_id="u2", xp=999))
                self.assertEqual(kho.get_progress("u1").xp, 10, ten)
                self.assertEqual(kho.get_progress("u2").xp, 999, ten)

    def test_record_xp_event_idempotent(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                e = XpLedgerEntry(entry_id="xp_abc", user_id="u1",
                                  event_type="publish_chapter",
                                  source_kind="chapter", source_id="c1",
                                  xp_awarded=10,
                                  created_at="2026-08-14T00:00:00+00:00")
                self.assertTrue(kho.record_xp_event(e), ten)
                # Lan hai CUNG entry_id -> False, KHONG ghi de/nhan ban.
                e2 = XpLedgerEntry(entry_id="xp_abc", user_id="u1",
                                   event_type="publish_chapter",
                                   source_kind="chapter", source_id="c1",
                                   xp_awarded=999,
                                   created_at="2026-08-14T02:00:00+00:00")
                self.assertFalse(kho.record_xp_event(e2), ten)
                ds = kho.list_xp_events("u1")
                self.assertEqual(len(ds), 1, ten)
                self.assertEqual(ds[0].xp_awarded, 10, ten)

    def test_list_xp_events_chi_cua_dung_nguoi_dung_sap_theo_thoi_gian(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.record_xp_event(XpLedgerEntry(
                    entry_id="xp_1", user_id="u1", event_type="a",
                    source_kind="k", source_id="1", xp_awarded=5,
                    created_at="2026-08-14T02:00:00+00:00"))
                kho.record_xp_event(XpLedgerEntry(
                    entry_id="xp_2", user_id="u1", event_type="b",
                    source_kind="k", source_id="2", xp_awarded=5,
                    created_at="2026-08-14T01:00:00+00:00"))
                kho.record_xp_event(XpLedgerEntry(
                    entry_id="xp_3", user_id="u2", event_type="a",
                    source_kind="k", source_id="3", xp_awarded=5,
                    created_at="2026-08-14T00:00:00+00:00"))
                ds = kho.list_xp_events("u1")
                self.assertEqual([e.entry_id for e in ds],
                                 ["xp_2", "xp_1"], ten)

    # ===================================================== thanh tuu

    def test_unlock_achievement_idempotent(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                r = UnlockedAchievement(
                    user_id="u1", achievement_key="chuong_dau_tien",
                    unlocked_at="2026-08-14T00:00:00+00:00")
                self.assertTrue(kho.unlock_achievement(r), ten)
                r2 = UnlockedAchievement(
                    user_id="u1", achievement_key="chuong_dau_tien",
                    unlocked_at="2026-08-14T05:00:00+00:00")
                self.assertFalse(kho.unlock_achievement(r2), ten)
                ds = kho.list_unlocked_achievements("u1")
                self.assertEqual(len(ds), 1, ten)
                # Moc thoi gian GOC duoc giu — khong bi ghi de boi lan goi sau.
                self.assertEqual(ds[0].unlocked_at,
                                 "2026-08-14T00:00:00+00:00", ten)

    def test_achievements_hai_nguoi_dung_doc_lap(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.unlock_achievement(UnlockedAchievement(
                    user_id="u1", achievement_key="a"))
                kho.unlock_achievement(UnlockedAchievement(
                    user_id="u2", achievement_key="a"))
                kho.unlock_achievement(UnlockedAchievement(
                    user_id="u1", achievement_key="b"))
                self.assertEqual(len(kho.list_unlocked_achievements("u1")), 2, ten)
                self.assertEqual(len(kho.list_unlocked_achievements("u2")), 1, ten)

    # ===================================================== vat pham

    def test_grant_cosmetic_trung_lap_tra_none(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                item = CosmeticInventoryItem(
                    user_id="u1", cosmetic_key="khung_go",
                    acquired_at="2026-08-14T00:00:00+00:00")
                self.assertIsNotNone(kho.grant_cosmetic(item), ten)
                trung = CosmeticInventoryItem(
                    user_id="u1", cosmetic_key="khung_go",
                    acquired_at="2026-08-14T05:00:00+00:00")
                self.assertIsNone(kho.grant_cosmetic(trung), ten)
                self.assertEqual(len(kho.list_cosmetics("u1")), 1, ten)

    def test_get_cosmetic_khong_co_tra_none(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self.assertIsNone(kho.get_cosmetic("u1", "khong_ton_tai"), ten)

    def test_set_cosmetic_equipped_chua_so_huu_nem_loi(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                with self.assertRaises(NotFoundError, msg=ten):
                    kho.set_cosmetic_equipped("u1", "khong_ton_tai", True)

    def test_set_cosmetic_equipped_thanh_cong(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.grant_cosmetic(CosmeticInventoryItem(
                    user_id="u1", cosmetic_key="khung_go"))
                kho.set_cosmetic_equipped("u1", "khung_go", True)
                muc = kho.get_cosmetic("u1", "khung_go")
                self.assertTrue(muc.equipped, ten)
                kho.set_cosmetic_equipped("u1", "khung_go", False)
                muc2 = kho.get_cosmetic("u1", "khung_go")
                self.assertFalse(muc2.equipped, ten)

    def test_cosmetics_hai_nguoi_dung_doc_lap(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.grant_cosmetic(CosmeticInventoryItem(
                    user_id="u1", cosmetic_key="khung_go"))
                kho.grant_cosmetic(CosmeticInventoryItem(
                    user_id="u2", cosmetic_key="khung_go"))
                self.assertEqual(len(kho.list_cosmetics("u1")), 1, ten)
                self.assertEqual(len(kho.list_cosmetics("u2")), 1, ten)

    def test_list_cosmetics_by_ids_gom_dung_nguoi(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.grant_cosmetic(CosmeticInventoryItem(
                    user_id="u1", cosmetic_key="khung_go"))
                kho.grant_cosmetic(CosmeticInventoryItem(
                    user_id="u1", cosmetic_key="khung_bac"))
                kho.grant_cosmetic(CosmeticInventoryItem(
                    user_id="u2", cosmetic_key="khung_go"))
                ra = kho.list_cosmetics_by_ids(["u1", "u2", "u3_khong_ton_tai"])
                self.assertEqual({m.cosmetic_key for m in ra["u1"]},
                                 {"khung_go", "khung_bac"}, ten)
                self.assertEqual({m.cosmetic_key for m in ra["u2"]},
                                 {"khung_go"}, ten)
                self.assertNotIn("u3_khong_ton_tai", ra, ten)

    def test_list_cosmetics_by_ids_rong_tra_dict_rong(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self.assertEqual(kho.list_cosmetics_by_ids([]), {}, ten)


class BuildGamificationStoreTest(unittest.TestCase):
    """`build_gamification_store` phai chon dung kho theo `DATA_BACKEND`,
    va KHONG bao gio am tham lui ve mock khi da khai bao Appwrite."""

    def test_mac_dinh_mock(self):
        from server.appwrite_gamification_store import build_gamification_store
        from server.gamification_store import MockGamificationStore as MGS

        class GiaSettings:
            data_backend = "mock"

        self.assertIsInstance(build_gamification_store(GiaSettings()), MGS)

    def test_appwrite_thieu_cau_hinh_nem_loi_ngay(self):
        from server.appwrite_adapter import AppwriteConfigError
        from server.appwrite_gamification_store import build_gamification_store
        from server.config import AppwriteSettings as AS

        class GiaSettings:
            data_backend = "appwrite"
            appwrite = AS(endpoint="", project_id="", api_key="", database_id="")

        with self.assertRaises(AppwriteConfigError):
            build_gamification_store(GiaSettings())

    def test_appwrite_du_cau_hinh_tra_dung_lop(self):
        from server.appwrite_gamification_store import (
            AppwriteGamificationStore,
            build_gamification_store,
        )
        from server.config import AppwriteSettings as AS

        class GiaSettings:
            data_backend = "appwrite"
            appwrite = AS(endpoint="https://x.invalid/v1", project_id="p",
                          api_key="k", database_id="db")

        self.assertIsInstance(build_gamification_store(GiaSettings()),
                              AppwriteGamificationStore)


if __name__ == "__main__":
    unittest.main()
