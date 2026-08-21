"""
V4 visual completion, vong 2 — `GET /api/users/{username}` phai lo
gamification CONG KHAI (bac/danh xung/thanh tuu/vat pham dang trang bi)
nhung KHONG BAO GIO lo xp/bo dem rieng tu.
"""

from __future__ import annotations

import unittest
from typing import Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.domain import Novel, PublishState
from server.gamification_domain import CosmeticInventoryItem, UnlockedAchievement
from server.gamification_service import award_xp
from server.gamification_store import MockGamificationStore


class PublicProfileGamificationTest(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.gamification_store = MockGamificationStore()
        self.client = TestClient(server_main.app)

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user_with_username(self, email: str, username: str) -> str:
        resp = self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"})
        token = resp.json()["token"]
        r2 = self.client.put("/api/creator/username", headers=self.auth(token),
                             json={"username": username})
        assert r2.status_code == 200, r2.text
        return token

    def test_ho_so_cong_khai_co_gamification_nhung_khong_lo_xp(self):
        token = self.user_with_username("a@example.com", "nguoi-choi-a")
        uid = self.client.get("/api/auth/me", headers=self.auth(token)) \
            .json()["profile"]["user_id"]
        award_xp(server_main.gamification_store, uid, "publish_first_novel",
                source_kind="novel", source_id=uid)
        server_main.gamification_store.unlock_achievement(
            UnlockedAchievement(user_id=uid, achievement_key="ra_mat_tieu_thuyet"))
        server_main.gamification_store.grant_cosmetic(
            CosmeticInventoryItem(user_id=uid, cosmetic_key="khung_go", equipped=True))

        body = self.client.get("/api/users/nguoi-choi-a").json()["profile"]
        gam = body["gamification"]
        self.assertEqual(gam["level"], 1)
        self.assertEqual(gam["equipped_title_key"], "lu_khach")
        self.assertNotIn("xp", gam)
        self.assertNotIn("pending_reward_packs", gam)
        self.assertNotIn("next_level_xp", gam)

        theo_khoa = {a["key"]: a for a in gam["achievements"]}
        self.assertTrue(theo_khoa["ra_mat_tieu_thuyet"]["unlocked"])
        self.assertFalse(theo_khoa["chuong_dau_tien"]["unlocked"])

        self.assertEqual(len(gam["equipped_cosmetics"]), 1)
        self.assertEqual(gam["equipped_cosmetics"][0]["key"], "khung_go")

    def test_vat_pham_chua_trang_bi_khong_xuat_hien(self):
        token = self.user_with_username("b@example.com", "nguoi-choi-b")
        uid = self.client.get("/api/auth/me", headers=self.auth(token)) \
            .json()["profile"]["user_id"]
        server_main.gamification_store.grant_cosmetic(
            CosmeticInventoryItem(user_id=uid, cosmetic_key="khung_go", equipped=False))

        body = self.client.get("/api/users/nguoi-choi-b").json()["profile"]
        self.assertEqual(body["gamification"]["equipped_cosmetics"], [])


if __name__ == "__main__":
    unittest.main()
