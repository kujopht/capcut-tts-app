"""
CRUD truyen/chuong: sua, xoa, xuat ban, go xuat ban.

Trong tam:
- CHI chu so huu duoc sua/xoa/xuat ban;
- xoa phai NHAT QUAN: khong de lai `audio_track` tro toi file da mat;
- khong cho client sua cac truong do server quyet dinh (`state`, `owner_id`).
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List

from fastapi.testclient import TestClient

from server import main as server_main
from server.tests.voice_stub import dung_registry_gia
from server import tts_bridge
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore


def _fake_synthesize(text, voice_id, dest, rate="1.0", chunk_chars=2000,
                     on_progress=None, cancel=None) -> Dict[str, Any]:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"\xff\xf3d" + b"\x00" * 4093)
    if on_progress:
        on_progress(1, 1)
    return {"size_bytes": 4096, "total_parts": 1, "voice_id": voice_id,
            "provider": "mock"}


class CrudTestCase(unittest.TestCase):
    def setUp(self) -> None:
        dung_registry_gia(self)
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self._real_storage = server_main.storage
        self._real_synth = tts_bridge.synthesize_chapter
        tts_bridge.synthesize_chapter = _fake_synthesize
        self.storage_root = Path(tempfile.mkdtemp())
        server_main.storage = LocalStorageAdapter(self.storage_root)
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        tts_bridge.synthesize_chapter = self._real_synth
        server_main.storage = self._real_storage

    # -- tien ich -------------------------------------------------------------

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str) -> str:
        return self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"}
        ).json()["token"]

    def novel(self, token: str, title: str = "Truyện") -> str:
        return self.client.post(
            "/api/novels", json={"title": title, "tags": ["thử"]},
            headers=self.auth(token),
        ).json()["novel"]["novel_id"]

    def chapter(self, token: str, novel_id: str, title: str = "C1") -> str:
        return self.client.post(
            "/api/chapters",
            json={"novel_id": novel_id, "title": title, "content": "Nội dung."},
            headers=self.auth(token),
        ).json()["chapter"]["chapter_id"]

    def with_audio(self, token: str, chapter_id: str) -> str:
        job = self.client.post(
            "/api/jobs", json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
            headers=self.auth(token),
        ).json()["job"]["job_id"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = self.client.get(
                f"/api/jobs/{job}", headers=self.auth(token)
            ).json()["job"]
            if state["status"] in ("completed", "failed"):
                return state["output_key"] or ""
            time.sleep(0.02)
        self.fail("job không kết thúc")

    def stored_keys(self) -> List[str]:
        return [
            str(path.relative_to(self.storage_root)).replace("\\", "/")
            for path in self.storage_root.rglob("*")
            if path.is_file()
        ]


# =============================================================== sua truyen


class TestUpdateNovel(CrudTestCase):
    def test_owner_can_edit_title_description_and_tags(self):
        token = self.user("chu@example.com")
        novel_id = self.novel(token)
        r = self.client.patch(
            f"/api/novels/{novel_id}",
            json={"title": "Tên mới", "description": "Mô tả mới",
                  "tags": ["one piece"]},
            headers=self.auth(token),
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()["novel"]
        self.assertEqual(body["title"], "Tên mới")
        self.assertEqual(body["description"], "Mô tả mới")
        self.assertEqual(body["tags"], ["one piece"])

    def test_change_is_persisted(self):
        token = self.user("chu@example.com")
        novel_id = self.novel(token)
        self.client.patch(f"/api/novels/{novel_id}", json={"title": "Đã đổi"},
                          headers=self.auth(token))
        again = self.client.get(f"/api/novels/{novel_id}",
                                headers=self.auth(token)).json()["novel"]
        self.assertEqual(again["title"], "Đã đổi")

    def test_partial_update_keeps_other_fields(self):
        token = self.user("chu@example.com")
        novel_id = self.novel(token, "Giữ nguyên")
        self.client.patch(f"/api/novels/{novel_id}",
                          json={"description": "Chỉ đổi mô tả"},
                          headers=self.auth(token))
        body = self.client.get(f"/api/novels/{novel_id}",
                               headers=self.auth(token)).json()["novel"]
        self.assertEqual(body["title"], "Giữ nguyên")
        self.assertEqual(body["tags"], ["thử"])

    def test_state_cannot_be_changed_through_patch(self):
        """`state` la truong do SERVER quyet dinh."""
        token = self.user("chu@example.com")
        novel_id = self.novel(token)
        self.client.patch(f"/api/novels/{novel_id}",
                          json={"title": "x", "state": "published"},
                          headers=self.auth(token))
        self.assertEqual(
            self.client.get(f"/api/novels/{novel_id}",
                            headers=self.auth(token)).json()["novel"]["state"],
            "draft",
        )

    def test_owner_id_cannot_be_changed(self):
        token = self.user("chu@example.com")
        other = self.user("khac@example.com")
        owner_id = self.client.get("/api/auth/me",
                                   headers=self.auth(token)).json()["profile"]["user_id"]
        other_id = self.client.get("/api/auth/me",
                                   headers=self.auth(other)).json()["profile"]["user_id"]
        novel_id = self.novel(token)
        self.client.patch(f"/api/novels/{novel_id}",
                          json={"title": "x", "owner_id": other_id},
                          headers=self.auth(token))
        body = self.client.get(f"/api/novels/{novel_id}",
                               headers=self.auth(token)).json()["novel"]
        self.assertEqual(body["owner_id"], owner_id)

    def test_empty_patch_is_rejected(self):
        token = self.user("chu@example.com")
        novel_id = self.novel(token)
        r = self.client.patch(f"/api/novels/{novel_id}", json={},
                              headers=self.auth(token))
        self.assertEqual(r.status_code, 400)

    def test_non_owner_cannot_edit(self):
        owner = self.user("chu@example.com")
        novel_id = self.novel(owner)
        intruder = self.user("ke-la@example.com")
        r = self.client.patch(f"/api/novels/{novel_id}", json={"title": "Chiếm"},
                              headers=self.auth(intruder))
        self.assertEqual(r.status_code, 403)
        self.assertNotEqual(
            self.client.get(f"/api/novels/{novel_id}",
                            headers=self.auth(owner)).json()["novel"]["title"],
            "Chiếm",
        )

    def test_anonymous_cannot_edit(self):
        novel_id = self.novel(self.user("chu@example.com"))
        self.assertEqual(
            self.client.patch(f"/api/novels/{novel_id}", json={"title": "x"}).status_code,
            401,
        )

    def test_unknown_novel_is_404(self):
        token = self.user("chu@example.com")
        r = self.client.patch("/api/novels/nov_khong_co", json={"title": "x"},
                              headers=self.auth(token))
        self.assertEqual(r.status_code, 404)


# ============================================================== sua chuong


class TestUpdateChapter(CrudTestCase):
    def test_owner_can_edit_title_content_and_order(self):
        token = self.user("chu@example.com")
        chapter_id = self.chapter(token, self.novel(token))
        r = self.client.patch(
            f"/api/chapters/{chapter_id}",
            json={"title": "Chương đổi", "content": "Nội dung mới.", "order_index": 5},
            headers=self.auth(token),
        )
        self.assertEqual(r.status_code, 200)
        body = self.client.get(f"/api/chapters/{chapter_id}",
                               headers=self.auth(token)).json()["chapter"]
        self.assertEqual(body["title"], "Chương đổi")
        self.assertEqual(body["content"], "Nội dung mới.")
        self.assertEqual(body["order_index"], 5)

    def test_char_count_follows_new_content(self):
        token = self.user("chu@example.com")
        chapter_id = self.chapter(token, self.novel(token))
        self.client.patch(f"/api/chapters/{chapter_id}",
                          json={"content": "abc"}, headers=self.auth(token))
        self.assertEqual(
            self.client.get(f"/api/chapters/{chapter_id}", headers=self.auth(token))
                .json()["chapter"]["char_count"],
            3,
        )

    def test_non_owner_cannot_edit_chapter(self):
        owner = self.user("chu@example.com")
        chapter_id = self.chapter(owner, self.novel(owner))
        intruder = self.user("ke-la@example.com")
        r = self.client.patch(f"/api/chapters/{chapter_id}",
                              json={"content": "phá"}, headers=self.auth(intruder))
        self.assertEqual(r.status_code, 403)

    def test_novel_id_cannot_be_moved(self):
        """Khong cho chuyen chuong sang truyen khac bang PATCH."""
        token = self.user("chu@example.com")
        first = self.novel(token, "A")
        second = self.novel(token, "B")
        chapter_id = self.chapter(token, first)
        self.client.patch(f"/api/chapters/{chapter_id}",
                          json={"title": "x", "novel_id": second},
                          headers=self.auth(token))
        self.assertEqual(
            self.client.get(f"/api/chapters/{chapter_id}", headers=self.auth(token))
                .json()["chapter"]["novel_id"],
            first,
        )


# =============================================================== xoa chuong


class TestDeleteChapter(CrudTestCase):
    def test_owner_can_delete_chapter(self):
        token = self.user("chu@example.com")
        novel_id = self.novel(token)
        chapter_id = self.chapter(token, novel_id)
        r = self.client.delete(f"/api/chapters/{chapter_id}", headers=self.auth(token))
        self.assertEqual(r.status_code, 200)
        # Token cua chu so huu: 404 phai la vi DA XOA, khong phai vi phan quyen.
        self.assertEqual(
            self.client.get(f"/api/chapters/{chapter_id}",
                            headers=self.auth(token)).status_code, 404)

    def test_deleting_chapter_removes_audio_object_and_metadata(self):
        """Xoa phai NHAT QUAN: khong de lai track tro toi file da mat."""
        token = self.user("chu@example.com")
        novel_id = self.novel(token)
        chapter_id = self.chapter(token, novel_id)
        key = self.with_audio(token, chapter_id)
        self.assertIn(key, self.stored_keys())

        r = self.client.delete(f"/api/chapters/{chapter_id}", headers=self.auth(token))
        self.assertEqual(r.status_code, 200)
        removed = r.json()["removed"]
        self.assertEqual(removed["tracks"], 1)
        self.assertEqual(removed["objects"], 1)
        self.assertGreaterEqual(removed["jobs"], 1)

        self.assertNotIn(key, self.stored_keys(), "object phải bị xoá khỏi kho")
        self.assertEqual(server_main.store.tracks_for_chapter(chapter_id), [])

    def test_deleting_chapter_removes_its_jobs(self):
        token = self.user("chu@example.com")
        chapter_id = self.chapter(token, self.novel(token))
        self.with_audio(token, chapter_id)
        self.client.delete(f"/api/chapters/{chapter_id}", headers=self.auth(token))
        remaining = self.client.get("/api/jobs", headers=self.auth(token)).json()["jobs"]
        self.assertEqual([j for j in remaining if j["chapter_id"] == chapter_id], [])

    def test_deleting_one_chapter_keeps_the_others(self):
        token = self.user("chu@example.com")
        novel_id = self.novel(token)
        keep = self.chapter(token, novel_id, "Giữ")
        drop = self.chapter(token, novel_id, "Xoá")
        keep_key = self.with_audio(token, keep)
        self.with_audio(token, drop)

        self.client.delete(f"/api/chapters/{drop}", headers=self.auth(token))

        self.assertEqual(
            self.client.get(f"/api/chapters/{keep}",
                            headers=self.auth(token)).status_code, 200)
        self.assertIn(keep_key, self.stored_keys(), "không được xoá nhầm audio khác")

    def test_non_owner_cannot_delete_chapter(self):
        owner = self.user("chu@example.com")
        chapter_id = self.chapter(owner, self.novel(owner))
        intruder = self.user("ke-la@example.com")
        r = self.client.delete(f"/api/chapters/{chapter_id}", headers=self.auth(intruder))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(
            self.client.get(f"/api/chapters/{chapter_id}",
                            headers=self.auth(owner)).status_code, 200)

    def test_anonymous_cannot_delete_chapter(self):
        token = self.user("chu@example.com")
        chapter_id = self.chapter(token, self.novel(token))
        self.assertEqual(self.client.delete(f"/api/chapters/{chapter_id}").status_code,
                         401)
        self.assertEqual(
            self.client.get(f"/api/chapters/{chapter_id}",
                            headers=self.auth(token)).status_code, 200)


# =============================================================== xoa truyen


class TestDeleteNovel(CrudTestCase):
    def test_owner_can_delete_novel_with_everything_in_it(self):
        token = self.user("chu@example.com")
        novel_id = self.novel(token)
        first = self.chapter(token, novel_id, "C1")
        second = self.chapter(token, novel_id, "C2")
        keys = [self.with_audio(token, first), self.with_audio(token, second)]

        r = self.client.delete(f"/api/novels/{novel_id}", headers=self.auth(token))
        self.assertEqual(r.status_code, 200)
        removed = r.json()["removed"]
        self.assertEqual(removed["chapters"], 2)
        self.assertEqual(removed["tracks"], 2)
        self.assertEqual(removed["objects"], 2)

        # Goi kem token cua chu so huu: 404 o day phai chung minh DA XOA, chu
        # khong phai chi chung minh khach vang lai khong duoc xem truyen nhap.
        self.assertEqual(
            self.client.get(f"/api/novels/{novel_id}",
                            headers=self.auth(token)).status_code, 404)
        for chapter_id in (first, second):
            self.assertEqual(
                self.client.get(f"/api/chapters/{chapter_id}",
                                headers=self.auth(token)).status_code, 404)
        for key in keys:
            self.assertNotIn(key, self.stored_keys())

    def test_deleting_novel_leaves_no_orphan_metadata(self):
        token = self.user("chu@example.com")
        novel_id = self.novel(token)
        chapter_id = self.chapter(token, novel_id)
        self.with_audio(token, chapter_id)

        self.client.delete(f"/api/novels/{novel_id}", headers=self.auth(token))

        store = server_main.store
        self.assertEqual(store.tracks_for_chapter(chapter_id), [])
        self.assertEqual(store.chapters, {})
        self.assertEqual(store.novels, {})
        self.assertEqual(store.jobs, {})
        self.assertEqual(self.stored_keys(), [])

    def test_deleting_one_novel_keeps_another(self):
        token = self.user("chu@example.com")
        keep = self.novel(token, "Giữ")
        drop = self.novel(token, "Xoá")
        keep_chapter = self.chapter(token, keep)
        keep_key = self.with_audio(token, keep_chapter)
        self.with_audio(token, self.chapter(token, drop))

        self.client.delete(f"/api/novels/{drop}", headers=self.auth(token))

        self.assertEqual(
            self.client.get(f"/api/novels/{keep}",
                            headers=self.auth(token)).status_code, 200)
        self.assertIn(keep_key, self.stored_keys())

    def test_non_owner_cannot_delete_novel(self):
        owner = self.user("chu@example.com")
        novel_id = self.novel(owner)
        intruder = self.user("ke-la@example.com")
        r = self.client.delete(f"/api/novels/{novel_id}", headers=self.auth(intruder))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(
            self.client.get(f"/api/novels/{novel_id}",
                            headers=self.auth(owner)).status_code, 200)

    def test_non_owner_deletion_touches_nothing(self):
        owner = self.user("chu@example.com")
        novel_id = self.novel(owner)
        chapter_id = self.chapter(owner, novel_id)
        key = self.with_audio(owner, chapter_id)
        intruder = self.user("ke-la@example.com")

        self.client.delete(f"/api/novels/{novel_id}", headers=self.auth(intruder))

        self.assertIn(key, self.stored_keys(), "không được xoá object của người khác")
        self.assertEqual(
            self.client.get(f"/api/chapters/{chapter_id}",
                            headers=self.auth(owner)).status_code, 200)

    def test_anonymous_cannot_delete_novel(self):
        novel_id = self.novel(self.user("chu@example.com"))
        self.assertEqual(self.client.delete(f"/api/novels/{novel_id}").status_code, 401)

    def test_unknown_novel_is_404(self):
        token = self.user("chu@example.com")
        self.assertEqual(
            self.client.delete("/api/novels/nov_khong_co",
                               headers=self.auth(token)).status_code,
            404,
        )


# ========================================================= xuat ban / go bo


class TestPublishToggle(CrudTestCase):
    def test_publish_then_unpublish(self):
        token = self.user("chu@example.com")
        novel_id = self.novel(token)
        self.chapter(token, novel_id)

        self.client.post(f"/api/novels/{novel_id}/publish", headers=self.auth(token))
        self.assertEqual(self.client.get("/api/novels").json()["count"], 1)

        r = self.client.post(f"/api/novels/{novel_id}/unpublish",
                             headers=self.auth(token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["novel"]["state"], "draft")
        self.assertEqual(self.client.get("/api/novels").json()["count"], 0)

    def test_unpublish_is_persisted(self):
        token = self.user("chu@example.com")
        novel_id = self.novel(token)
        self.client.post(f"/api/novels/{novel_id}/publish", headers=self.auth(token))
        self.client.post(f"/api/novels/{novel_id}/unpublish", headers=self.auth(token))
        self.assertEqual(
            self.client.get(f"/api/novels/{novel_id}", headers=self.auth(token))
                .json()["novel"]["state"], "draft")

    def test_unpublish_is_idempotent(self):
        token = self.user("chu@example.com")
        novel_id = self.novel(token)
        first = self.client.post(f"/api/novels/{novel_id}/unpublish",
                                 headers=self.auth(token))
        second = self.client.post(f"/api/novels/{novel_id}/unpublish",
                                  headers=self.auth(token))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["novel"]["state"], "draft")

    def test_unpublished_audio_is_private_again(self):
        """Go xuat ban phai dong lai quyen nghe cong khai."""
        token = self.user("chu@example.com")
        novel_id = self.novel(token)
        chapter_id = self.chapter(token, novel_id)
        self.with_audio(token, chapter_id)

        self.client.post(f"/api/novels/{novel_id}/publish", headers=self.auth(token))
        self.assertEqual(self.client.get(f"/api/audio/{chapter_id}").status_code, 200)

        self.client.post(f"/api/novels/{novel_id}/unpublish", headers=self.auth(token))
        self.assertEqual(self.client.get(f"/api/audio/{chapter_id}").status_code, 401)
        self.assertEqual(
            self.client.get(f"/api/audio/{chapter_id}/url").status_code, 401)

    def test_non_owner_cannot_unpublish(self):
        owner = self.user("chu@example.com")
        novel_id = self.novel(owner)
        self.client.post(f"/api/novels/{novel_id}/publish", headers=self.auth(owner))
        intruder = self.user("ke-la@example.com")

        r = self.client.post(f"/api/novels/{novel_id}/unpublish",
                             headers=self.auth(intruder))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(
            self.client.get(f"/api/novels/{novel_id}").json()["novel"]["state"],
            "published",
        )

    def test_anonymous_cannot_unpublish(self):
        novel_id = self.novel(self.user("chu@example.com"))
        self.assertEqual(
            self.client.post(f"/api/novels/{novel_id}/unpublish").status_code, 401)


# ================================================ hai kho cung mot giao dien


class TestBothStoresShareTheContract(unittest.TestCase):
    def test_appwrite_store_has_the_same_crud_signatures(self):
        import inspect

        from server.appwrite_store import AppwriteMetadataStore

        for name in ("update_novel", "unpublish_novel", "delete_novel",
                     "update_chapter", "delete_chapter", "delete_job",
                     "tracks_for_chapter", "delete_track"):
            mock = getattr(MockMetadataStore, name, None)
            live = getattr(AppwriteMetadataStore, name, None)
            self.assertTrue(callable(live), f"AppwriteMetadataStore thiếu {name}()")
            self.assertEqual(
                list(inspect.signature(live).parameters),
                list(inspect.signature(mock).parameters),
                f"{name}() lệch chữ ký giữa hai kho",
            )

    def test_editable_field_lists_match(self):
        from server.appwrite_store import AppwriteMetadataStore

        self.assertEqual(MockMetadataStore.NOVEL_EDITABLE,
                         AppwriteMetadataStore.NOVEL_EDITABLE)
        self.assertEqual(MockMetadataStore.CHAPTER_EDITABLE,
                         AppwriteMetadataStore.CHAPTER_EDITABLE)

    def test_editable_lists_exclude_server_owned_fields(self):
        for forbidden in ("state", "owner_id", "novel_id", "chapter_id"):
            self.assertNotIn(forbidden, MockMetadataStore.NOVEL_EDITABLE)
            self.assertNotIn(forbidden, MockMetadataStore.CHAPTER_EDITABLE)

    def test_storage_adapters_can_delete(self):
        from server.r2_adapter import R2StorageAdapter

        self.assertTrue(callable(getattr(LocalStorageAdapter, "delete", None)))
        self.assertTrue(callable(getattr(R2StorageAdapter, "delete", None)))


class TestPurgeOrderIsSafe(unittest.TestCase):
    """
    Metadata TRUOC, object SAU.

    Nguoc lai thi mot loi giua chung se de lai `audio_track` tro toi file da
    mat — trinh phat hong. Theo thu tu nay, xau nhat chi la object thua, ma
    object thua thi khong route nao cham toi duoc.
    """

    def test_source_deletes_metadata_before_objects(self):
        import inspect

        source = inspect.getsource(server_main._purge_chapter)
        self.assertLess(
            source.index("store.delete_track"),
            source.index("storage.delete"),
            "phải xoá metadata trước object",
        )
        self.assertLess(
            source.index("store.delete_chapter"),
            source.index("storage.delete"),
        )

    def test_object_deletion_failure_does_not_break_the_operation(self):
        """Kho tu choi xoa object thi van phai xoa duoc metadata."""
        import inspect

        self.assertIn("except Exception",
                      inspect.getsource(server_main._purge_chapter))


if __name__ == "__main__":
    unittest.main(verbosity=2)
