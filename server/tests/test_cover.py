"""
Truong anh bia trong phan hoi API.

Hai dieu quan trong nhat:
- CHI THEM truong, khong doi ten va khong bo truong nao -> client cu van chay;
- khong co bia thi tra `null`, KHONG bao gio bia ra mot URL anh gia.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore


class SignedStorage(LocalStorageAdapter):
    """Gia lap kho co URL ky (nhu R2)."""

    mode = "r2"

    def signed_url(self, key, expires_seconds=3600, download_name=None):
        return f"https://khong-co-that.example/{key}?X-Amz-Signature=gia-lap"


class CoverTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self._real_storage = server_main.storage
        server_main.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.storage = self._real_storage

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str = "chu@example.com") -> str:
        return self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"}
        ).json()["token"]

    def novel(self, token: str, title: str = "Truyện") -> str:
        return self.client.post("/api/novels", json={"title": title},
                                headers=self.auth(token)).json()["novel"]["novel_id"]

    def chapter(self, token: str, novel_id: str) -> str:
        return self.client.post(
            "/api/chapters",
            json={"novel_id": novel_id, "title": "C1", "content": "Nội dung."},
            headers=self.auth(token),
        ).json()["chapter"]["chapter_id"]

    def set_cover(self, novel_id: str, key: Optional[str]) -> None:
        """Dat `cover_key` thang qua kho — chua co duong upload bia."""
        from dataclasses import replace

        store = server_main.store
        store.novels[novel_id] = replace(store.novels[novel_id], cover_key=key)


# ============================================================ novel


class TestNovelCoverField(CoverTestCase):
    def test_novel_response_has_cover_url(self):
        token = self.user()
        novel_id = self.novel(token)
        body = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        self.assertIn("cover_url", body)

    def test_no_cover_means_null_not_a_fake_image(self):
        token = self.user()
        novel_id = self.novel(token)
        body = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        self.assertIsNone(body["cover_url"])
        self.assertIsNone(body["cover_key"])

    def test_cover_url_is_signed_when_storage_can_sign(self):
        server_main.storage = SignedStorage(Path(tempfile.mkdtemp()))
        token = self.user()
        novel_id = self.novel(token)
        self.set_cover(novel_id, "covers/abc.jpg")

        body = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        self.assertIn("X-Amz-Signature", body["cover_url"])
        self.assertIn("covers/abc.jpg", body["cover_url"])

    def test_local_storage_without_signing_returns_null(self):
        """Kho khong ky duoc thi tra null — giao dien dung anh du phong."""
        token = self.user()
        novel_id = self.novel(token)
        self.set_cover(novel_id, "covers/abc.jpg")
        body = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        self.assertIsNone(body["cover_url"])
        self.assertEqual(body["cover_key"], "covers/abc.jpg")

    def test_cover_url_present_in_every_novel_response(self):
        token = self.user()
        novel_id = self.novel(token)
        self.chapter(token, novel_id)

        places = {
            "tao moi": self.client.post("/api/novels", json={"title": "T2"},
                                        headers=self.auth(token)).json()["novel"],
            "chi tiet": self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"],
            "danh sach cua toi":
                self.client.get("/api/novels?mine=true",
                                headers=self.auth(token)).json()["novels"][0],
            "sua": self.client.patch(f"/api/novels/{novel_id}", json={"title": "T3"},
                                     headers=self.auth(token)).json()["novel"],
            "xuat ban": self.client.post(f"/api/novels/{novel_id}/publish",
                                         headers=self.auth(token)).json()["novel"],
            "go xuat ban": self.client.post(f"/api/novels/{novel_id}/unpublish",
                                            headers=self.auth(token)).json()["novel"],
        }
        for where, body in places.items():
            self.assertIn("cover_url", body, f"{where}: thiếu cover_url")

        published = self.client.post(f"/api/novels/{novel_id}/publish",
                                     headers=self.auth(token))
        self.assertIn("cover_url", self.client.get("/api/novels").json()["novels"][0])
        self.assertEqual(published.status_code, 200)


class TestBackwardCompatible(CoverTestCase):
    """CHI THEM truong. Client cu doc cac truong cu phai khong doi gi."""

    OLD_NOVEL_FIELDS = {
        "novel_id", "owner_id", "title", "description", "cover_key",
        "state", "tags", "created_at", "updated_at",
    }

    def test_no_old_novel_field_was_removed_or_renamed(self):
        token = self.user()
        novel_id = self.novel(token)
        body = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        missing = self.OLD_NOVEL_FIELDS - set(body)
        self.assertEqual(missing, set(), f"mất trường cũ: {missing}")

    def test_only_cover_url_was_added(self):
        token = self.user()
        novel_id = self.novel(token)
        body = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        self.assertEqual(set(body) - self.OLD_NOVEL_FIELDS, {"cover_url"})

    def test_chapter_response_keeps_its_old_shape(self):
        token = self.user()
        chapter_id = self.chapter(token, self.novel(token))
        body = self.client.get(f"/api/chapters/{chapter_id}", headers=self.auth(token)).json()
        self.assertIn("chapter", body)
        self.assertIn("audio", body)          # van con, du la None
        self.assertEqual(set(body) - {"chapter", "audio"}, {"novel"})

    def test_cover_field_is_not_persisted_as_an_unknown_attribute(self):
        """`cover_url` la truong tinh — khong duoc gui len Appwrite."""
        from server.appwrite_store import PERSISTED_FIELDS, COL_NOVELS, persistable

        token = self.user()
        novel_id = self.novel(token)
        body = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        self.assertNotIn("cover_url", PERSISTED_FIELDS[COL_NOVELS])
        self.assertNotIn("cover_url", persistable(COL_NOVELS, body))


# ============================================================ chapter


class TestChapterCarriesItsNovel(CoverTestCase):
    """Luong nghe can bia va ten truyen ngay trong phan hoi cua chuong."""

    def test_chapter_response_includes_its_novel(self):
        token = self.user()
        novel_id = self.novel(token, "Hải Tặc Mũ Rơm")
        chapter_id = self.chapter(token, novel_id)

        novel = self.client.get(f"/api/chapters/{chapter_id}", headers=self.auth(token)).json()["novel"]
        self.assertEqual(novel["novel_id"], novel_id)
        self.assertEqual(novel["title"], "Hải Tặc Mũ Rơm")
        self.assertEqual(novel["state"], "draft")
        self.assertIn("cover_url", novel)
        self.assertIn("cover_key", novel)

    def test_chapter_novel_carries_the_signed_cover(self):
        server_main.storage = SignedStorage(Path(tempfile.mkdtemp()))
        token = self.user()
        novel_id = self.novel(token)
        chapter_id = self.chapter(token, novel_id)
        self.set_cover(novel_id, "covers/bia.png")

        novel = self.client.get(f"/api/chapters/{chapter_id}", headers=self.auth(token)).json()["novel"]
        self.assertIn("covers/bia.png", novel["cover_url"])

    def test_chapter_novel_is_a_summary_not_the_whole_record(self):
        """Chi vua du: khong ro ri `owner_id` hay mo ta dai."""
        token = self.user()
        chapter_id = self.chapter(token, self.novel(token))
        novel = self.client.get(f"/api/chapters/{chapter_id}", headers=self.auth(token)).json()["novel"]
        self.assertEqual(
            set(novel), {"novel_id", "title", "state", "cover_key", "cover_url"}
        )
        self.assertNotIn("owner_id", novel)

    def test_missing_parent_novel_does_not_break_the_chapter(self):
        """
        Mat truyen cha thi chuong van tra ve duoc, `novel` la None.

        Goi bang token cua CHU SO HUU: khong co truyen cha thi khong xac minh
        duoc trang thai xuat ban, nen route chi cho chu so huu doc. Phan quyen
        do co bo test rieng o `test_chapter_list_batching.py`.
        """
        token = self.user()
        novel_id = self.novel(token)
        chapter_id = self.chapter(token, novel_id)
        server_main.store.novels.pop(novel_id)      # mo phong du lieu le loi

        body = self.client.get(f"/api/chapters/{chapter_id}", headers=self.auth(token))
        self.assertEqual(body.status_code, 200)
        self.assertIsNone(body.json()["novel"])
        self.assertIsNotNone(body.json()["chapter"])

    def test_publishing_is_reflected_in_the_chapter_response(self):
        token = self.user()
        novel_id = self.novel(token)
        chapter_id = self.chapter(token, novel_id)
        self.client.post(f"/api/novels/{novel_id}/publish", headers=self.auth(token))
        self.assertEqual(
            self.client.get(f"/api/chapters/{chapter_id}", headers=self.auth(token)).json()["novel"]["state"],
            "published",
        )


class TestNoFakeCover(CoverTestCase):
    """Backend khong bao gio tu bia ra mot duong dan anh."""

    def test_cover_url_never_invented_from_thin_air(self):
        import inspect

        source = inspect.getsource(server_main._cover_url)
        self.assertIn("if not novel.cover_key", source)
        self.assertIn("return None", source)
        # Khong co chuoi URL nao duoc viet cung trong ham
        self.assertNotIn("http", source.split('"""')[-1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
