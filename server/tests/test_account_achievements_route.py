"""V4 visual completion, Phan G-J — route `/api/account/achievements`."""

from __future__ import annotations

import unittest
from typing import Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.domain import Chapter, Novel, PublishState


class AccountAchievementsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self.client = TestClient(server_main.app)

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str = "tac-gia@example.com") -> tuple[str, str]:
        resp = self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"})
        body = resp.json()
        return body["token"], body["profile"]["user_id"]


class KhongDangNhapTest(AccountAchievementsTestCase):
    def test_can_dang_nhap(self):
        resp = self.client.get("/api/account/achievements")
        self.assertEqual(resp.status_code, 401)


class NguoiDungMoiTest(AccountAchievementsTestCase):
    def test_chua_dat_thanh_tuu_nao(self):
        token, _ = self.user()
        resp = self.client.get("/api/account/achievements", headers=self.auth(token))
        self.assertEqual(resp.status_code, 200)
        ds = resp.json()["achievements"]
        self.assertEqual(len(ds), 4)
        self.assertTrue(all(a["unlocked"] is False for a in ds))


class DaXuatBanTest(AccountAchievementsTestCase):
    def test_xuat_ban_truyen_va_chuong_thi_mo_dung_thanh_tuu(self):
        token, uid = self.user()
        novel = server_main.store.create_novel(Novel(
            owner_id=uid, title="Truyện", state=PublishState.PUBLISHED))
        server_main.store.create_chapter(Chapter(
            novel_id=novel.novel_id, owner_id=uid, title="Chương 1",
            state=PublishState.PUBLISHED))
        # Chuong NHAP thi khong duoc tinh.
        server_main.store.create_chapter(Chapter(
            novel_id=novel.novel_id, owner_id=uid, title="Chương nháp",
            state=PublishState.DRAFT))

        ds = self.client.get(
            "/api/account/achievements", headers=self.auth(token)).json()["achievements"]
        theo_khoa = {a["key"]: a for a in ds}
        self.assertTrue(theo_khoa["chuong_dau_tien"]["unlocked"])
        self.assertTrue(theo_khoa["ra_mat_tieu_thuyet"]["unlocked"])
        self.assertFalse(theo_khoa["cat_tieng"]["unlocked"])
        self.assertFalse(theo_khoa["dem_dai_thu_vien"]["unlocked"])
        self.assertIsNone(theo_khoa["chuong_dau_tien"]["progress"])
        self.assertEqual(theo_khoa["dem_dai_thu_vien"]["progress"], [0, 60])

    def test_khong_lo_bo_dem_rieng_cua_nguoi_khac(self):
        token_a, uid_a = self.user("a@example.com")
        _, uid_b = self.user("b@example.com")
        server_main.store.create_novel(Novel(
            owner_id=uid_b, title="Truyện của B", state=PublishState.PUBLISHED))

        ds = self.client.get(
            "/api/account/achievements", headers=self.auth(token_a)).json()["achievements"]
        theo_khoa = {a["key"]: a for a in ds}
        self.assertFalse(theo_khoa["ra_mat_tieu_thuyet"]["unlocked"])


if __name__ == "__main__":
    unittest.main()
