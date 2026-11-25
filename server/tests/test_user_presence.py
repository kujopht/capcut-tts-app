"""
HIEN DIEN USER: heartbeat + trang quan tri "User online".

- `POST /api/auth/me/heartbeat` ghi `last_seen_at` cho chinh chu.
- `GET /api/admin/users/online` chi ADMIN tro len xem duoc, tra user kem
  moc hien dien, sap xep online len dau.

Route admin moi duoc bao ve boi `test_moi_route_admin_deu_duoc_bao_ve` o
`test_admin.py` (tu liet ke `/api/admin/*`) — khong can lap lai o day.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.creator_service import CreatorService


class Base(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.creators = CreatorService(server_main.identity,
                                              server_main.store)
        self.identity = server_main.identity
        self.store = server_main.store
        self.svc = server_main.creators
        self._settings_cu = server_main.settings
        self.client = TestClient(server_main.app)

        self.admin, self.h_admin = self._dang_ky("admin@fanfic.local",
                                                 "Quản Trị")
        server_main.settings = replace(
            server_main.settings,
            admin_user_ids=(self.admin["user_id"],))
        self.thuong, self.h_thuong = self._dang_ky("thuong@fanfic.local",
                                                   "Người Thường")

    def tearDown(self) -> None:
        server_main.settings = self._settings_cu

    def _dang_ky(self, email, ten):
        self.client.post("/api/auth/register", json={
            "email": email, "password": "matkhau123", "display_name": ten})
        r = self.client.post("/api/auth/login",
                             json={"email": email, "password": "matkhau123"})
        d = r.json()
        return d["profile"], {"Authorization": f"Bearer {d['token']}"}

    def _dat_last_seen(self, user_id, giay_truoc):
        """Dat moc hien dien cho mot user ve qua khu (gia lap)."""
        moc = (datetime.now(timezone.utc)
               - timedelta(seconds=giay_truoc)).isoformat(timespec="seconds")
        self.identity._profiles[user_id].last_seen_at = moc
        return moc


class HeartbeatTest(Base):
    def test_khong_token_401(self):
        self.assertEqual(
            self.client.post("/api/auth/me/heartbeat").status_code, 401)

    def test_ghi_last_seen_cho_chinh_chu(self):
        r = self.client.post("/api/auth/me/heartbeat", headers=self.h_thuong)
        self.assertEqual(r.status_code, 200)
        than = r.json()
        self.assertTrue(than["tracked"])
        self.assertTrue(than["last_seen_at"])
        # Ban ghi trong kho phai la dung moc vua tra ve.
        ho_so = self.identity._profiles[self.thuong["user_id"]]
        self.assertEqual(ho_so.last_seen_at, than["last_seen_at"])

    def test_goi_lai_cap_nhat_moc(self):
        truoc = self.client.post("/api/auth/me/heartbeat",
                                 headers=self.h_thuong).json()["last_seen_at"]
        sau = self.client.post("/api/auth/me/heartbeat",
                               headers=self.h_thuong).json()["last_seen_at"]
        # `now_iso` cat o giay: hai lan goi trong cung giay cho moc bang nhau.
        self.assertGreaterEqual(sau, truoc)

    def test_touch_user_khong_co_ho_so_tra_false(self):
        self.assertFalse(
            self.identity.touch_last_seen("khong-ton-tai", "2026-11-23T00:00:00+00:00"))


class AppwriteTouchGateTest(unittest.TestCase):
    """Ban that: chua co thuoc tinh `last_seen_at` trong bang thi bo qua,
    khong nem, khong goi Appwrite."""

    def _adapter(self, attrs):
        from server.appwrite_adapter import AppwriteIdentityAdapter
        a = AppwriteIdentityAdapter.__new__(AppwriteIdentityAdapter)
        a._profile_attrs = set(attrs)
        goi = []
        a._request = lambda method, path, **kw: goi.append((method, path, kw)) or {}
        a._profile_path = lambda uid: f"/v1/x/documents/{uid}"
        return a, goi

    def test_thieu_thuoc_tinh_thi_tra_false_khong_goi_api(self):
        a, goi = self._adapter({"username", "bio"})
        self.assertFalse(a.touch_last_seen("u1", "2026-11-23T00:00:00+00:00"))
        self.assertEqual(goi, [])

    def test_co_thuoc_tinh_thi_patch_dung_mot_truong(self):
        a, goi = self._adapter({"username", "last_seen_at"})
        self.assertTrue(a.touch_last_seen("u1", "2026-11-23T00:00:00+00:00"))
        self.assertEqual(len(goi), 1)
        method, _path, kw = goi[0]
        self.assertEqual(method, "PATCH")
        self.assertEqual(kw["payload"],
                         {"data": {"last_seen_at": "2026-11-23T00:00:00+00:00"}})


class AdminOnlineTest(Base):
    def test_an_danh_401_nguoi_thuong_403(self):
        self.assertEqual(
            self.client.get("/api/admin/users/online").status_code, 401)
        self.assertEqual(
            self.client.get("/api/admin/users/online",
                            headers=self.h_thuong).status_code, 403)

    def test_admin_vao_duoc_va_thay_ca_hai_user(self):
        r = self.client.get("/api/admin/users/online", headers=self.h_admin)
        self.assertEqual(r.status_code, 200)
        than = r.json()
        self.assertEqual(than["total"], 2)
        ids = {u["user_id"] for u in than["users"]}
        self.assertEqual(ids, {self.admin["user_id"], self.thuong["user_id"]})
        for u in than["users"]:
            self.assertIn("last_seen_at", u)
            self.assertIn("is_online", u)
            self.assertIn("email", u)

    def test_online_len_dau_chua_tung_thay_xuong_cuoi(self):
        # Chi "Người Thường" ping — phai dung dau, admin chua tung thay cuoi.
        self.client.post("/api/auth/me/heartbeat", headers=self.h_thuong)
        r = self.client.get("/api/admin/users/online", headers=self.h_admin)
        ds = r.json()["users"]
        self.assertEqual(ds[0]["user_id"], self.thuong["user_id"])
        self.assertTrue(ds[0]["is_online"])
        self.assertTrue(ds[0]["last_seen_at"])
        self.assertEqual(ds[1]["user_id"], self.admin["user_id"])
        self.assertFalse(ds[1]["is_online"])
        self.assertIsNone(ds[1]["last_seen_at"])

    def test_moc_cu_qua_5_phut_la_offline(self):
        self._dat_last_seen(self.thuong["user_id"], 6 * 60)
        r = self.client.get("/api/admin/users/online", headers=self.h_admin)
        hang = [u for u in r.json()["users"]
                if u["user_id"] == self.thuong["user_id"]][0]
        self.assertFalse(hang["is_online"])
        # Moc 4 phut truoc van online.
        self._dat_last_seen(self.thuong["user_id"], 4 * 60)
        r = self.client.get("/api/admin/users/online", headers=self.h_admin)
        hang = [u for u in r.json()["users"]
                if u["user_id"] == self.thuong["user_id"]][0]
        self.assertTrue(hang["is_online"])

    def test_tim_kiem_theo_email(self):
        r = self.client.get("/api/admin/users/online?q=thuong",
                            headers=self.h_admin)
        ds = r.json()["users"]
        self.assertEqual(len(ds), 1)
        self.assertEqual(ds[0]["email"], "thuong@fanfic.local")

    def test_phan_trang_limit_offset(self):
        for i in range(3):
            self._dang_ky(f"them{i}@fanfic.local", f"Thêm {i}")
        r = self.client.get("/api/admin/users/online?limit=2",
                            headers=self.h_admin)
        than = r.json()
        self.assertEqual(len(than["users"]), 2)
        self.assertEqual(than["total"], 5)
        r2 = self.client.get("/api/admin/users/online?limit=2&offset=2",
                             headers=self.h_admin)
        self.assertEqual(len(r2.json()["users"]), 2)
        ids1 = {u["user_id"] for u in than["users"]}
        ids2 = {u["user_id"] for u in r2.json()["users"]}
        self.assertFalse(ids1 & ids2)


if __name__ == "__main__":
    unittest.main()
