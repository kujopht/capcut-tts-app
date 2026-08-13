"""
V4 Phase 6 — anh dai dien (avatar). Cung khuon voi `test_cover.py`.

Khac cover mot diem ky thuat: `set_avatar`/`remove_avatar` song trong
`CreatorService` (tham chieu `self._storage` CHUP LUC KHOI TAO), khong phai
mot ham module-level doc bien toan cuc `storage` truc tiep nhu route bia
truyen — nen test PHAI dung lai `server_main.creators` voi kho gia SAU khi
doi `server_main.storage`, neu khong service van giu tham chieu kho CU.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.creator_service import CreatorService

PNG_1X1 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
          "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


class SignedStorage(LocalStorageAdapter):
    """
    Gia lap kho co URL ky (nhu R2) — cung mau voi `test_cover.py`.

    `LocalStorageAdapter` that tra `None` tu `signed_url()` (dung y: kho dev
    khong ky duoc), nen bat ky test nao can THAY avatar_url phai la mot chuoi
    (khong phai None) can ban gia nay thay vi ban that.
    """

    mode = "r2"

    def signed_url(self, key, expires_seconds=3600, download_name=None):
        return f"https://khong-co-that.example/{key}?X-Amz-Signature=gia-lap"


class AvatarTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self._storage_cu = server_main.storage
        self._creators_cu = server_main.creators
        server_main.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        # PHAI dung lai: `CreatorService` chup `storage` LUC KHOI TAO.
        server_main.creators = CreatorService(
            server_main.identity, server_main.store, server_main.storage)
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.storage = self._storage_cu
        server_main.creators = self._creators_cu

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str = "chu@example.com") -> str:
        return self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"}
        ).json()["token"]


class TestAvatarUpload(AvatarTestCase):
    def test_tai_len_dat_avatar_key_va_luu_object(self):
        token = self.user()
        r = self.client.put("/api/creator/avatar", headers=self.auth(token),
                            json={"base64": PNG_1X1, "mime": "image/png",
                                  "width": 1, "height": 1})
        self.assertEqual(r.status_code, 200, r.text)
        prof = r.json()["profile"]
        self.assertTrue(prof["avatar_key"])
        self.assertTrue(prof["avatar_key"].startswith("avatars/"))
        self.assertTrue(server_main.storage._path(prof["avatar_key"]).is_file())

    def test_avatar_url_ky_duoc_tra_ve_cung_luc(self):
        """Khong bat client goi lai `/api/auth/me` de co URL xem duoc ngay."""
        server_main.storage = SignedStorage(Path(tempfile.mkdtemp()))
        server_main.creators = CreatorService(
            server_main.identity, server_main.store, server_main.storage)
        token = self.user()
        r = self.client.put("/api/creator/avatar", headers=self.auth(token),
                            json={"base64": PNG_1X1, "mime": "image/png"})
        self.assertIsNotNone(r.json()["profile"]["avatar_url"])

    def test_khoa_khong_co_email(self):
        token = self.user("rieng-tu@example.com")
        r = self.client.put("/api/creator/avatar", headers=self.auth(token),
                            json={"base64": PNG_1X1, "mime": "image/png"})
        khoa = r.json()["profile"]["avatar_key"]
        self.assertNotIn("@", khoa)
        self.assertNotIn("example.com", khoa)

    def test_dinh_dang_khong_hop_le_bi_tu_choi_400(self):
        token = self.user()
        r = self.client.put("/api/creator/avatar", headers=self.auth(token),
                            json={"base64": PNG_1X1, "mime": "application/pdf"})
        self.assertEqual(r.status_code, 400)

    def test_chua_dang_nhap_bi_401(self):
        r = self.client.put("/api/creator/avatar",
                            json={"base64": PNG_1X1, "mime": "image/png"})
        self.assertEqual(r.status_code, 401)

    def test_thay_avatar_moi_xoa_object_cu_khi_doi_duoi(self):
        token = self.user()
        head = self.auth(token)
        r1 = self.client.put("/api/creator/avatar", headers=head,
                             json={"base64": PNG_1X1, "mime": "image/jpeg"})
        khoa_cu = r1.json()["profile"]["avatar_key"]
        self.assertTrue(server_main.storage._path(khoa_cu).is_file())

        r2 = self.client.put("/api/creator/avatar", headers=head,
                             json={"base64": PNG_1X1, "mime": "image/png"})
        khoa_moi = r2.json()["profile"]["avatar_key"]
        self.assertNotEqual(khoa_cu, khoa_moi)
        self.assertFalse(server_main.storage._path(khoa_cu).is_file(),
                         "avatar cũ (đuôi khác) phải bị xoá sau khi thay")

    def test_go_avatar_xoa_ca_khoa_lan_object(self):
        token = self.user()
        head = self.auth(token)
        khoa = self.client.put("/api/creator/avatar", headers=head,
                               json={"base64": PNG_1X1, "mime": "image/png"}
                               ).json()["profile"]["avatar_key"]

        r = self.client.delete("/api/creator/avatar", headers=head)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["profile"]["avatar_key"], "")
        self.assertIsNone(r.json()["profile"]["avatar_url"])
        self.assertFalse(server_main.storage._path(khoa).is_file())

    def test_go_avatar_khi_chua_co_khong_loi(self):
        token = self.user()
        r = self.client.delete("/api/creator/avatar", headers=self.auth(token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["profile"]["avatar_key"], "")


class TestAvatarInAuthMe(AvatarTestCase):
    def test_me_tra_avatar_key_va_url(self):
        token = self.user()
        r = self.client.get("/api/auth/me", headers=self.auth(token))
        self.assertIn("avatar_key", r.json()["profile"])
        self.assertIn("avatar_url", r.json()["profile"])
        self.assertIsNone(r.json()["profile"]["avatar_url"])

    def test_dang_ky_va_dang_nhap_cung_mang_avatar_url(self):
        r = self.client.post("/api/auth/register", json={
            "email": "moi@example.com", "password": "matkhau123"})
        self.assertIn("avatar_url", r.json()["profile"])
        r2 = self.client.post("/api/auth/login", json={
            "email": "moi@example.com", "password": "matkhau123"})
        self.assertIn("avatar_url", r2.json()["profile"])


class TestAvatarPublicProfile(AvatarTestCase):
    def test_ho_so_cong_khai_co_avatar_url_khi_da_tai(self):
        server_main.storage = SignedStorage(Path(tempfile.mkdtemp()))
        server_main.creators = CreatorService(
            server_main.identity, server_main.store, server_main.storage)
        token = self.user()
        head = self.auth(token)
        self.client.put("/api/creator/username", headers=head,
                        json={"username": "co-avatar"})
        self.client.put("/api/creator/avatar", headers=head,
                        json={"base64": PNG_1X1, "mime": "image/png"})
        r = self.client.get("/api/users/co-avatar")
        self.assertIsNotNone(r.json()["profile"]["avatar_url"])

    def test_ho_so_cong_khai_avatar_url_null_khi_chua_tai(self):
        token = self.user()
        self.client.put("/api/creator/username", headers=self.auth(token),
                        json={"username": "chua-avatar"})
        r = self.client.get("/api/users/chua-avatar")
        self.assertIsNone(r.json()["profile"]["avatar_url"])

    def test_ho_so_cong_khai_khong_lo_avatar_key_tho(self):
        """Danh sach cho phep: khoa noi bo khong ra ngoai, chi URL da ky."""
        token = self.user()
        head = self.auth(token)
        self.client.put("/api/creator/username", headers=head,
                        json={"username": "khong-lo-khoa"})
        self.client.put("/api/creator/avatar", headers=head,
                        json={"base64": PNG_1X1, "mime": "image/png"})
        r = self.client.get("/api/users/khong-lo-khoa")
        self.assertNotIn("avatar_key", r.json()["profile"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
