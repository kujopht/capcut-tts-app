"""
V4 visual completion, vong 2 — cac route `/api/account/{progress,title,
titles,cosmetics,reward-packs}` va sua loi dem chuong xuat ban cua
`/api/account/achievements`.
"""

from __future__ import annotations

import unittest
from typing import Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.domain import Chapter, Novel, PublishState
from server.gamification_domain import UserProgress
from server.gamification_store import MockGamificationStore


class GamificationRouteTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.gamification_store = MockGamificationStore()
        self.client = TestClient(server_main.app)

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str = "u@example.com") -> tuple[str, str]:
        resp = self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"})
        body = resp.json()
        return body["token"], body["profile"]["user_id"]


class KhongDangNhapTest(GamificationRouteTestCase):
    def test_moi_duong_gamification_can_dang_nhap(self):
        for resp in (
            self.client.get("/api/account/progress"),
            self.client.post("/api/account/title", json={"title_key": "lu_khach"}),
            self.client.get("/api/account/titles"),
            self.client.get("/api/account/cosmetics"),
            self.client.post("/api/account/cosmetics/khung_go/equip"),
            self.client.post("/api/account/reward-packs/goi_len_bac/open"),
        ):
            self.assertEqual(resp.status_code, 401)

    def test_danh_sach_goi_thuong_cong_khai_khong_can_dang_nhap(self):
        resp = self.client.get("/api/account/reward-packs")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()["packs"]), 1)


class ProgressTest(GamificationRouteTestCase):
    def test_nguoi_dung_moi_o_bac_1(self):
        token, _ = self.user()
        body = self.client.get("/api/account/progress", headers=self.auth(token)).json()
        self.assertEqual(body["level"], 1)
        self.assertEqual(body["xp"], 0)
        self.assertEqual(body["equipped_title_key"], "lu_khach")


class TitleTest(GamificationRouteTestCase):
    def test_chua_mo_khoa_thi_400(self):
        token, _ = self.user()
        resp = self.client.post("/api/account/title", headers=self.auth(token),
                                json={"title_key": "dai_hien_gia_thu_gioi"})
        self.assertEqual(resp.status_code, 400)

    def test_danh_sach_danh_xung_co_co_mo_khoa(self):
        token, _ = self.user()
        body = self.client.get("/api/account/titles", headers=self.auth(token)).json()
        khoa_mo = [t["key"] for t in body["titles"] if t["unlocked"]]
        self.assertEqual(khoa_mo, ["lu_khach"])


class AchievementCountingFixTest(GamificationRouteTestCase):
    """Khoa lai LOI THAT: dem chuong theo `chapter.state` luon ra 0 vi
    kien truc hien tai khong bao gio dat truong do — phai dem theo truyen
    cha da xuat ban."""

    def test_chuong_thuoc_truyen_da_xuat_ban_duoc_tinh_du_chapter_state_van_draft(self):
        token, uid = self.user()
        novel = server_main.store.create_novel(Novel(
            owner_id=uid, title="Truyện", state=PublishState.PUBLISHED))
        chapter = server_main.store.create_chapter(Chapter(
            novel_id=novel.novel_id, owner_id=uid, title="Chương 1"))
        self.assertIs(chapter.state, PublishState.DRAFT)  # dung y — xem docstring

        body = self.client.get(
            "/api/account/achievements", headers=self.auth(token)).json()
        theo_khoa = {a["key"]: a for a in body["achievements"]}
        self.assertTrue(theo_khoa["chuong_dau_tien"]["unlocked"])
        self.assertTrue(theo_khoa["ra_mat_tieu_thuyet"]["unlocked"])

    def test_chuong_thuoc_truyen_nhap_khong_duoc_tinh(self):
        token, uid = self.user()
        novel = server_main.store.create_novel(Novel(
            owner_id=uid, title="Truyện nháp", state=PublishState.DRAFT))
        server_main.store.create_chapter(Chapter(
            novel_id=novel.novel_id, owner_id=uid, title="Chương 1"))

        body = self.client.get(
            "/api/account/achievements", headers=self.auth(token)).json()
        theo_khoa = {a["key"]: a for a in body["achievements"]}
        self.assertFalse(theo_khoa["chuong_dau_tien"]["unlocked"])


class CosmeticRouteTest(GamificationRouteTestCase):
    def test_trang_bi_vat_pham_chua_co_bi_tu_choi(self):
        token, _ = self.user()
        resp = self.client.post("/api/account/cosmetics/khung_go/equip",
                                headers=self.auth(token))
        self.assertEqual(resp.status_code, 400)

    def test_danh_sach_rong_khi_chua_co_gi(self):
        token, _ = self.user()
        body = self.client.get("/api/account/cosmetics", headers=self.auth(token)).json()
        self.assertEqual(body["cosmetics"], [])


class RewardPackRouteTest(GamificationRouteTestCase):
    def test_khong_co_goi_thi_400(self):
        token, _ = self.user()
        resp = self.client.post("/api/account/reward-packs/goi_len_bac/open",
                                headers=self.auth(token))
        self.assertEqual(resp.status_code, 400)

    def test_co_goi_thi_mo_duoc_va_tra_ve_vat_pham(self):
        token, uid = self.user()
        server_main.gamification_store.save_progress(
            UserProgress(user_id=uid, goi_thuong_dang_cho=1))
        resp = self.client.post("/api/account/reward-packs/goi_len_bac/open",
                                headers=self.auth(token))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("key", body["cosmetic"])
        self.assertEqual(body["pending_reward_packs"], 0)


if __name__ == "__main__":
    unittest.main()
