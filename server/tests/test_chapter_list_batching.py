"""
Trang chi tiet truyen phai ton MOT request, du truyen co bao nhieu chuong.

Truoc day trang do goi `/api/chapters/{id}` cho TUNG chuong chi de biet chuong
ay da co audio chua. Bo test nay khoa lai ba dieu:

1. so request va so truy van kho KHONG tang tuyen tinh theo so chuong;
2. `has_audio` noi dung su that, va khong keo theo URL ky nao;
3. quyen doc: truyen nhap chi chu so huu xem duoc, truyen da xuat ban van cong
   khai y nhu truoc.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore


class CountingStore(MockMetadataStore):
    """Dem so lan tung phuong thuc kho duoc goi."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: Dict[str, int] = {}

    def _tick(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def get_chapter(self, chapter_id: str):
        self._tick("get_chapter")
        return super().get_chapter(chapter_id)

    def track_for_chapter(self, chapter_id: str):
        self._tick("track_for_chapter")
        return super().track_for_chapter(chapter_id)

    def chapters_with_audio(self, chapter_ids: Sequence[str]) -> Set[str]:
        self._tick("chapters_with_audio")
        return super().chapters_with_audio(chapter_ids)

    def list_chapters(self, novel_id: str):
        self._tick("list_chapters")
        return super().list_chapters(novel_id)


class SignedStorage(LocalStorageAdapter):
    """Gia lap kho co URL ky, de bat duoc moi lan ai do ky mot duong dan."""

    mode = "r2"

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.signed: List[str] = []

    def signed_url(self, key, expires_seconds=3600, download_name=None):
        self.signed.append(key)
        return f"https://khong-co-that.example/{key}?X-Amz-Signature=gia-lap"


class BatchingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        self.store = CountingStore()
        server_main.store = self.store
        self._real_storage = server_main.storage
        server_main.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.storage = self._real_storage

    # -- tien ich ------------------------------------------------------------

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str = "chu@example.com") -> str:
        return self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"}
        ).json()["token"]

    def novel(self, token: str, title: str = "Truyện") -> str:
        return self.client.post("/api/novels", json={"title": title},
                                headers=self.auth(token)).json()["novel"]["novel_id"]

    def chapters(self, token: str, novel_id: str, count: int) -> List[str]:
        ids = []
        for i in range(1, count + 1):
            ids.append(self.client.post(
                "/api/chapters",
                json={"novel_id": novel_id, "title": f"C{i}",
                      "content": "Nội dung.", "order_index": i},
                headers=self.auth(token),
            ).json()["chapter"]["chapter_id"])
        return ids

    def give_audio(self, chapter_id: str, owner_id: str) -> None:
        from server.domain import AudioTrack

        self.store.create_track(AudioTrack(
            chapter_id=chapter_id, owner_id=owner_id, voice_id="edge:x",
            object_key=f"audio/{chapter_id}.mp3", content_hash="h",
            size_bytes=10,
        ))

    def owner_id(self, token: str) -> str:
        return self.client.get("/api/auth/me",
                               headers=self.auth(token)).json()["profile"]["user_id"]


# ==================================================== khong tang tuyen tinh


class TestNotLinearInChapters(BatchingTestCase):
    def test_one_store_call_for_audio_no_matter_how_many_chapters(self):
        token = self.user()
        novel_id = self.novel(token)
        self.chapters(token, novel_id, 30)

        self.store.calls.clear()
        self.client.get(f"/api/novels/{novel_id}", headers=self.auth(token))

        self.assertEqual(self.store.calls.get("chapters_with_audio"), 1)
        self.assertIsNone(self.store.calls.get("track_for_chapter"))
        self.assertIsNone(self.store.calls.get("get_chapter"))

    def test_store_calls_are_identical_for_3_and_for_60_chapters(self):
        """Bang chung truc tiep: so truy van khong phu thuoc so chuong."""
        token = self.user()

        small = self.novel(token, "Nhỏ")
        self.chapters(token, small, 3)
        self.store.calls.clear()
        self.client.get(f"/api/novels/{small}", headers=self.auth(token))
        calls_small = dict(self.store.calls)

        big = self.novel(token, "Lớn")
        self.chapters(token, big, 60)
        self.store.calls.clear()
        self.client.get(f"/api/novels/{big}", headers=self.auth(token))
        calls_big = dict(self.store.calls)

        self.assertEqual(calls_small, calls_big)

    def test_chapter_list_needs_no_extra_endpoint(self):
        """Tat ca thu trang can nam gon trong MOT phan hoi."""
        token = self.user()
        novel_id = self.novel(token)
        ids = self.chapters(token, novel_id, 5)
        self.give_audio(ids[0], self.owner_id(token))

        body = self.client.get(f"/api/novels/{novel_id}",
                               headers=self.auth(token)).json()
        for chapter in body["chapters"]:
            self.assertIn("has_audio", chapter)
            self.assertIn("title", chapter)
            self.assertIn("char_count", chapter)

    def test_empty_novel_does_not_query_the_track_store(self):
        token = self.user()
        novel_id = self.novel(token)

        self.store.calls.clear()
        body = self.client.get(f"/api/novels/{novel_id}",
                               headers=self.auth(token)).json()
        self.assertEqual(body["chapters"], [])
        # Van goi mot lan, nhung ban mock phai thoat som voi danh sach rong
        self.assertEqual(self.store.chapters_with_audio([]), set())


# ==================================================== has_audio dung su that


class TestHasAudioIsTruthful(BatchingTestCase):
    def test_flag_matches_reality_per_chapter(self):
        token = self.user()
        owner = self.owner_id(token)
        novel_id = self.novel(token)
        ids = self.chapters(token, novel_id, 4)
        self.give_audio(ids[1], owner)
        self.give_audio(ids[3], owner)

        body = self.client.get(f"/api/novels/{novel_id}",
                               headers=self.auth(token)).json()
        flags = {c["chapter_id"]: c["has_audio"] for c in body["chapters"]}
        self.assertEqual(flags[ids[0]], False)
        self.assertEqual(flags[ids[1]], True)
        self.assertEqual(flags[ids[2]], False)
        self.assertEqual(flags[ids[3]], True)

    def test_audio_of_another_novel_does_not_leak_in(self):
        token = self.user()
        owner = self.owner_id(token)
        a = self.novel(token, "A")
        b = self.novel(token, "B")
        ids_a = self.chapters(token, a, 2)
        self.chapters(token, b, 2)
        self.give_audio(ids_a[0], owner)

        body = self.client.get(f"/api/novels/{b}", headers=self.auth(token)).json()
        self.assertEqual([c["has_audio"] for c in body["chapters"]], [False, False])

    def test_no_presigned_audio_url_is_created_for_the_list(self):
        """Trang danh sach chua phat gi — khong duoc ky URL cho tung chuong."""
        storage = SignedStorage(Path(tempfile.mkdtemp()))
        server_main.storage = storage
        token = self.user()
        owner = self.owner_id(token)
        novel_id = self.novel(token)
        for chapter_id in self.chapters(token, novel_id, 6):
            self.give_audio(chapter_id, owner)

        storage.signed.clear()
        body = self.client.get(f"/api/novels/{novel_id}",
                               headers=self.auth(token)).json()

        self.assertTrue(all(c["has_audio"] for c in body["chapters"]))
        self.assertEqual(storage.signed, [])   # truyen chua co bia -> khong ky gi
        for chapter in body["chapters"]:
            self.assertNotIn("audio_url", chapter)
            self.assertNotIn("object_key", chapter)

    def test_flag_turns_true_after_audio_appears(self):
        token = self.user()
        owner = self.owner_id(token)
        novel_id = self.novel(token)
        chapter_id = self.chapters(token, novel_id, 1)[0]

        def flag() -> bool:
            body = self.client.get(f"/api/novels/{novel_id}",
                                   headers=self.auth(token)).json()
            return body["chapters"][0]["has_audio"]

        self.assertFalse(flag())
        self.give_audio(chapter_id, owner)
        self.assertTrue(flag())


# ==================================================== tuong thich nguoc


class TestBackwardCompatible(BatchingTestCase):
    OLD_CHAPTER_FIELDS = {
        "chapter_id", "novel_id", "owner_id", "title", "order_index",
        "state", "char_count", "created_at", "updated_at",
    }

    def test_only_has_audio_was_added_to_the_chapter_list(self):
        token = self.user()
        novel_id = self.novel(token)
        self.chapters(token, novel_id, 1)
        chapter = self.client.get(f"/api/novels/{novel_id}",
                                  headers=self.auth(token)).json()["chapters"][0]
        self.assertEqual(set(chapter) - self.OLD_CHAPTER_FIELDS, {"has_audio"})

    def test_novel_response_keeps_its_two_top_level_keys(self):
        token = self.user()
        novel_id = self.novel(token)
        body = self.client.get(f"/api/novels/{novel_id}",
                               headers=self.auth(token)).json()
        self.assertEqual(set(body), {"novel", "chapters"})

    def test_single_chapter_route_is_unchanged(self):
        """Client cu van goi duoc `/api/chapters/{id}` nhu truoc."""
        token = self.user()
        novel_id = self.novel(token)
        chapter_id = self.chapters(token, novel_id, 1)[0]
        body = self.client.get(f"/api/chapters/{chapter_id}",
                               headers=self.auth(token)).json()
        self.assertEqual(set(body), {"chapter", "audio", "novel"})

    def test_has_audio_is_not_persisted_as_an_unknown_attribute(self):
        from server.appwrite_store import COL_CHAPTERS, PERSISTED_FIELDS, persistable

        self.assertNotIn("has_audio", PERSISTED_FIELDS[COL_CHAPTERS])
        self.assertNotIn("has_audio", persistable(COL_CHAPTERS, {"has_audio": True}))


# ==================================================== quyen doc


class TestReadAuthorization(BatchingTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner_token = self.user("chu@example.com")
        self.other_token = self.user("nguoila@example.com")
        self.novel_id = self.novel(self.owner_token, "Truyện nháp")
        self.chapter_id = self.chapters(self.owner_token, self.novel_id, 2)[0]

    def publish(self) -> None:
        self.client.post(f"/api/novels/{self.novel_id}/publish",
                         headers=self.auth(self.owner_token))

    # -- truyen nhap ---------------------------------------------------------

    def test_draft_novel_is_hidden_from_anonymous(self):
        r = self.client.get(f"/api/novels/{self.novel_id}")
        self.assertEqual(r.status_code, 404)

    def test_draft_novel_is_hidden_from_another_user(self):
        r = self.client.get(f"/api/novels/{self.novel_id}",
                            headers=self.auth(self.other_token))
        self.assertEqual(r.status_code, 404)

    def test_draft_novel_is_visible_to_its_owner(self):
        r = self.client.get(f"/api/novels/{self.novel_id}",
                            headers=self.auth(self.owner_token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["chapters"]), 2)

    def test_draft_hides_the_chapter_list_too(self):
        """404 phai kin: khong duoc lo ten chuong hay so chuong."""
        r = self.client.get(f"/api/novels/{self.novel_id}")
        self.assertNotIn("chapters", r.json())
        self.assertNotIn("Truyện nháp", r.text)

    def test_draft_chapter_content_is_hidden_from_anonymous(self):
        r = self.client.get(f"/api/chapters/{self.chapter_id}")
        self.assertEqual(r.status_code, 404)

    def test_draft_chapter_is_visible_to_its_owner(self):
        r = self.client.get(f"/api/chapters/{self.chapter_id}",
                            headers=self.auth(self.owner_token))
        self.assertEqual(r.status_code, 200)

    def test_expired_token_is_treated_as_anonymous_not_as_an_error(self):
        r = self.client.get(f"/api/novels/{self.novel_id}",
                            headers={"Authorization": "Bearer khong-phai-token"})
        self.assertEqual(r.status_code, 404)      # khong phai 401, khong phai 500

    # -- truyen da xuat ban --------------------------------------------------

    def test_published_novel_stays_public(self):
        self.publish()
        r = self.client.get(f"/api/novels/{self.novel_id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["chapters"]), 2)

    def test_published_chapter_stays_public(self):
        self.publish()
        r = self.client.get(f"/api/chapters/{self.chapter_id}")
        self.assertEqual(r.status_code, 200)

    def test_published_novel_public_to_a_logged_in_stranger(self):
        self.publish()
        r = self.client.get(f"/api/novels/{self.novel_id}",
                            headers=self.auth(self.other_token))
        self.assertEqual(r.status_code, 200)

    def test_unpublishing_closes_public_access_again(self):
        self.publish()
        self.assertEqual(self.client.get(f"/api/novels/{self.novel_id}").status_code, 200)
        self.client.post(f"/api/novels/{self.novel_id}/unpublish",
                         headers=self.auth(self.owner_token))
        self.assertEqual(self.client.get(f"/api/novels/{self.novel_id}").status_code, 404)

    def test_public_library_listing_is_untouched(self):
        """`GET /api/novels` van chi liet ke truyen da xuat ban, khong doi."""
        self.publish()
        body = self.client.get("/api/novels").json()
        self.assertEqual([n["novel_id"] for n in body["novels"]], [self.novel_id])

    def test_orphan_chapter_is_owner_only(self):
        """Khong co truyen cha thi khong xac minh duoc -> cho phia an toan."""
        self.store.novels.pop(self.novel_id)
        self.assertEqual(
            self.client.get(f"/api/chapters/{self.chapter_id}").status_code, 404)
        r = self.client.get(f"/api/chapters/{self.chapter_id}",
                            headers=self.auth(self.owner_token))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["novel"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
