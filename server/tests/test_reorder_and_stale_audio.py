"""
M3 — sap xep lai thu tu chuong. M4 — canh bao audio khong con khop.

Hai dieu bo test nay giu chat nhat:

- Sap xep lai KHONG duoc lam mat chuong, mat noi dung, mat audio hay doi trang
  thai publish. Danh sach thu tu phai gom dung tap chuong cua truyen; lech mot
  cai thi khong duoc ghi gi ca.
- Canh bao audio cu chi la CANH BAO. Khong route nao duoc xoa file audio vi no
  "cu", va nguoi dung phai duoc quyen giu audio hien tai.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.domain import AudioTrack


def iso(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc)
            + timedelta(seconds=offset_seconds)).isoformat(timespec="seconds")


class Base(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        self.store = MockMetadataStore()
        server_main.store = self.store
        self._real_storage = server_main.storage
        self.root = Path(tempfile.mkdtemp())
        server_main.storage = LocalStorageAdapter(self.root)
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

    def owner_id(self, token: str) -> str:
        return self.client.get("/api/auth/me",
                               headers=self.auth(token)).json()["profile"]["user_id"]

    def novel(self, token: str, title: str = "Truyện") -> str:
        return self.client.post("/api/novels", json={"title": title},
                                headers=self.auth(token)).json()["novel"]["novel_id"]

    def chapter(self, token: str, novel_id: str, title: str,
                order: int, content: str = "Nội dung.") -> str:
        return self.client.post(
            "/api/chapters",
            json={"novel_id": novel_id, "title": title,
                  "content": content, "order_index": order},
            headers=self.auth(token),
        ).json()["chapter"]["chapter_id"]

    def three(self, token: str) -> tuple:
        novel_id = self.novel(token)
        a = self.chapter(token, novel_id, "A", 1)
        b = self.chapter(token, novel_id, "B", 2)
        c = self.chapter(token, novel_id, "C", 3)
        return novel_id, a, b, c

    def reorder(self, token: str, novel_id: str, ids: List[str]):
        return self.client.post(f"/api/novels/{novel_id}/chapters/order",
                                json={"chapter_ids": ids},
                                headers=self.auth(token))

    def reorder_ok(self, token: str, novel_id: str, ids: List[str]):
        """
        Sap xep lai va KHANG DINH da thanh cong.

        Dung ham nay o cac test kieu "sap xep lai khong lam mat gi". Neu chi goi
        `reorder()` roi kiem tra "khong mat gi", test se dat ca khi route khong
        ton tai: POST tra 404, khong doi gi, va tat nhien la khong mat gi.
        """
        r = self.reorder(token, novel_id, ids)
        self.assertEqual(r.status_code, 200, f"sắp xếp lại thất bại: {r.text[:200]}")
        return r

    def titles(self, novel_id: str, token: str) -> List[str]:
        body = self.client.get(f"/api/novels/{novel_id}",
                               headers=self.auth(token)).json()
        return [c["title"] for c in body["chapters"]]

    def give_audio(self, chapter_id: str, owner: str, made_at: str) -> AudioTrack:
        track = AudioTrack(
            chapter_id=chapter_id, owner_id=owner, voice_id="edge:x",
            object_key=f"audio/{chapter_id}.mp3", content_hash="h",
            size_bytes=10, created_at=made_at,
        )
        return self.store.create_track(track)


# ============================================================= M3 thu tu


class TestReorderWorks(Base):
    def test_order_is_actually_changed(self):
        token = self.user()
        novel_id, a, b, c = self.three(token)
        self.assertEqual(self.titles(novel_id, token), ["A", "B", "C"])

        r = self.reorder(token, novel_id, [c, a, b])
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x["title"] for x in r.json()["chapters"]], ["C", "A", "B"])

    def test_order_survives_a_fresh_read(self):
        """Phai luu that vao kho, khong chi doi tam tren frontend."""
        token = self.user()
        novel_id, a, b, c = self.three(token)
        self.reorder(token, novel_id, [c, b, a])
        self.assertEqual(self.titles(novel_id, token), ["C", "B", "A"])

    def test_order_index_is_renumbered_from_one_without_gaps(self):
        token = self.user()
        novel_id, a, b, c = self.three(token)
        self.reorder_ok(token, novel_id, [b, c, a])
        body = self.client.get(f"/api/novels/{novel_id}",
                               headers=self.auth(token)).json()
        # Kiem CA hai: day so lien tuc VA dung thu tu vua yeu cau. Kiem rieng
        # day so thi test dat ca khi khong co gi doi, vi 1,2,3 co san tu dau.
        self.assertEqual([x["order_index"] for x in body["chapters"]], [1, 2, 3])
        self.assertEqual([x["title"] for x in body["chapters"]], ["B", "C", "A"])

    def test_public_list_and_author_page_agree(self):
        """Danh sach cong khai va trang quan ly phai cung mot thu tu."""
        token = self.user()
        novel_id, a, b, c = self.three(token)
        self.client.post(f"/api/novels/{novel_id}/publish", headers=self.auth(token))
        self.reorder(token, novel_id, [c, a, b])

        khach = self.client.get(f"/api/novels/{novel_id}").json()
        chu = self.client.get(f"/api/novels/{novel_id}",
                              headers=self.auth(token)).json()
        self.assertEqual([x["chapter_id"] for x in khach["chapters"]],
                         [x["chapter_id"] for x in chu["chapters"]])
        self.assertEqual([x["title"] for x in khach["chapters"]], ["C", "A", "B"])

    def test_reordering_is_one_request_not_one_per_chapter(self):
        """Doi thu tu n chuong phai la 1 request, khong phai n request."""
        import inspect

        source = inspect.getsource(server_main.reorder_chapters)
        self.assertIn("store.reorder_chapters", source)
        # Route nhan CA danh sach mot lan
        self.assertIn("payload.chapter_ids", source)

    def test_reorder_response_carries_the_audio_flags(self):
        """Tang tren ve lai danh sach ngay, khong phai goi lai getNovel."""
        token = self.user()
        owner = self.owner_id(token)
        novel_id, a, b, c = self.three(token)
        self.give_audio(a, owner, iso())

        body = self.reorder(token, novel_id, [c, b, a]).json()
        flags = {x["chapter_id"]: x["has_audio"] for x in body["chapters"]}
        self.assertTrue(flags[a])
        self.assertFalse(flags[b])
        for row in body["chapters"]:
            self.assertIn("audio_outdated", row)


class TestReorderLosesNothing(Base):
    def test_titles_and_content_are_untouched(self):
        token = self.user()
        novel_id = self.novel(token)
        a = self.chapter(token, novel_id, "A", 1, "Noi dung A dai hon.")
        b = self.chapter(token, novel_id, "B", 2, "Noi dung B.")
        self.reorder_ok(token, novel_id, [b, a])

        got_a = self.client.get(f"/api/chapters/{a}",
                                headers=self.auth(token)).json()["chapter"]
        self.assertEqual(got_a["title"], "A")
        self.assertEqual(got_a["content"], "Noi dung A dai hon.")

    def test_audio_survives_reordering(self):
        token = self.user()
        owner = self.owner_id(token)
        novel_id, a, b, c = self.three(token)
        self.give_audio(a, owner, iso())
        before = self.store.track_for_chapter(a)

        self.reorder_ok(token, novel_id, [c, b, a])

        after = self.store.track_for_chapter(a)
        self.assertIsNotNone(after)
        self.assertEqual(after.track_id, before.track_id)
        self.assertEqual(after.object_key, before.object_key)

    def test_publish_state_survives_reordering(self):
        token = self.user()
        novel_id, a, b, c = self.three(token)
        self.client.post(f"/api/novels/{novel_id}/publish", headers=self.auth(token))
        self.reorder_ok(token, novel_id, [b, a, c])
        novel = self.client.get(f"/api/novels/{novel_id}").json()["novel"]
        self.assertEqual(novel["state"], "published")

    def test_no_chapter_disappears(self):
        token = self.user()
        novel_id, a, b, c = self.three(token)
        self.reorder_ok(token, novel_id, [c, a, b])
        body = self.client.get(f"/api/novels/{novel_id}",
                               headers=self.auth(token)).json()
        self.assertEqual(len(body["chapters"]), 3)
        self.assertEqual({x["chapter_id"] for x in body["chapters"]}, {a, b, c})

    def test_reorder_does_not_bump_updated_at(self):
        """
        Sap xep lai khong sua noi dung, nen khong duoc lam moi chuong bi bao
        "audio cu" oan — `updated_at` chinh la moc dung cho canh bao do.
        """
        token = self.user()
        owner = self.owner_id(token)
        novel_id, a, b, c = self.three(token)
        self.give_audio(a, owner, iso(60))       # audio tao SAU khi soan chuong

        self.reorder_ok(token, novel_id, [c, b, a])

        row = next(x for x in self.client.get(
            f"/api/novels/{novel_id}", headers=self.auth(token)
        ).json()["chapters"] if x["chapter_id"] == a)
        self.assertFalse(row["audio_outdated"],
                         "sắp xếp lại không được làm audio bị coi là cũ")


class TestReorderRejectsBadInput(Base):
    def test_missing_a_chapter_is_rejected(self):
        token = self.user()
        novel_id, a, b, c = self.three(token)
        r = self.reorder(token, novel_id, [c, a])            # thieu b
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.titles(novel_id, token), ["A", "B", "C"])

    def test_duplicate_id_is_rejected(self):
        token = self.user()
        novel_id, a, b, c = self.three(token)
        r = self.reorder(token, novel_id, [a, a, b, c])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.titles(novel_id, token), ["A", "B", "C"])

    def test_chapter_from_another_novel_is_rejected(self):
        token = self.user()
        novel_id, a, b, c = self.three(token)
        other = self.novel(token, "Truyện khác")
        lac = self.chapter(token, other, "Lạc", 1)

        r = self.reorder(token, novel_id, [a, b, lac])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.titles(novel_id, token), ["A", "B", "C"])
        # Va chuong cua truyen khac khong bi keo sang
        self.assertEqual(self.titles(other, token), ["Lạc"])

    def test_unknown_id_is_rejected(self):
        token = self.user()
        novel_id, a, b, c = self.three(token)
        r = self.reorder(token, novel_id, [a, b, "chp_khong_ton_tai"])
        self.assertEqual(r.status_code, 400)

    def test_nothing_is_written_when_input_is_rejected(self):
        """400 phai la KHONG GHI GI, khong phai ghi mot nua."""
        token = self.user()
        novel_id, a, b, c = self.three(token)
        # Chung minh co che ghi CO hoat dong truoc da, neu khong thi phan sau
        # dat mot cach rong: route khong ton tai thi tat nhien khong ghi gi.
        self.reorder_ok(token, novel_id, [c, b, a])

        before = {cid: self.store.get_chapter(cid).order_index for cid in (a, b, c)}
        r = self.reorder(token, novel_id, [c, b])       # thieu a
        self.assertEqual(r.status_code, 400)
        after = {cid: self.store.get_chapter(cid).order_index for cid in (a, b, c)}
        self.assertEqual(before, after)

    def test_empty_list_is_rejected(self):
        token = self.user()
        novel_id, a, b, c = self.three(token)
        r = self.reorder(token, novel_id, [])
        self.assertIn(r.status_code, (400, 422))
        self.assertEqual(self.titles(novel_id, token), ["A", "B", "C"])


class TestReorderAuthorization(Base):
    def setUp(self) -> None:
        super().setUp()
        self.owner_token = self.user("chu@example.com")
        self.other_token = self.user("nguoila@example.com")
        self.novel_id, self.a, self.b, self.c = self.three(self.owner_token)

    def test_owner_can_reorder(self):
        r = self.reorder(self.owner_token, self.novel_id, [self.c, self.b, self.a])
        self.assertEqual(r.status_code, 200)

    def test_another_user_cannot_reorder(self):
        r = self.reorder(self.other_token, self.novel_id, [self.c, self.b, self.a])
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.titles(self.novel_id, self.owner_token), ["A", "B", "C"])

    def test_anonymous_cannot_reorder(self):
        r = self.client.post(f"/api/novels/{self.novel_id}/chapters/order",
                             json={"chapter_ids": [self.c, self.b, self.a]})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.titles(self.novel_id, self.owner_token), ["A", "B", "C"])

    def test_published_novel_is_still_owner_only(self):
        """Xuat ban roi cung khong cho nguoi khac doi thu tu."""
        self.client.post(f"/api/novels/{self.novel_id}/publish",
                         headers=self.auth(self.owner_token))
        r = self.reorder(self.other_token, self.novel_id, [self.c, self.b, self.a])
        self.assertEqual(r.status_code, 403)

    def test_unknown_novel_is_404(self):
        # Route CO ton tai — neu khong, 404 duoi day chi la "khong tim thay
        # duong dan" va test dat vi ly do sai.
        self.reorder_ok(self.owner_token, self.novel_id, [self.c, self.b, self.a])
        r = self.reorder(self.owner_token, "nov_khong_ton_tai", [self.a])
        self.assertEqual(r.status_code, 404)


# ============================================================= M4 audio cu


class TestOutdatedAudioSignal(Base):
    def test_fresh_audio_is_not_flagged(self):
        token = self.user()
        owner = self.owner_id(token)
        novel_id = self.novel(token)
        a = self.chapter(token, novel_id, "A", 1)
        self.give_audio(a, owner, iso(60))          # audio moi hon chuong

        body = self.client.get(f"/api/chapters/{a}",
                               headers=self.auth(token)).json()
        self.assertFalse(body["audio_outdated"])

    def test_editing_content_flags_the_audio(self):
        token = self.user()
        owner = self.owner_id(token)
        novel_id = self.novel(token)
        a = self.chapter(token, novel_id, "A", 1)
        self.give_audio(a, owner, iso(-60))         # audio tao TRUOC do

        self.client.patch(f"/api/chapters/{a}", json={"content": "Nội dung mới."},
                          headers=self.auth(token))

        body = self.client.get(f"/api/chapters/{a}",
                               headers=self.auth(token)).json()
        self.assertTrue(body["audio_outdated"])

    def test_flag_shows_up_in_the_chapter_list_too(self):
        """Badge o trang quan ly doc tu day, nen phai co trong danh sach."""
        token = self.user()
        owner = self.owner_id(token)
        novel_id = self.novel(token)
        a = self.chapter(token, novel_id, "A", 1)
        self.give_audio(a, owner, iso(-60))
        self.client.patch(f"/api/chapters/{a}", json={"content": "Khác."},
                          headers=self.auth(token))

        row = self.client.get(f"/api/novels/{novel_id}",
                              headers=self.auth(token)).json()["chapters"][0]
        self.assertTrue(row["has_audio"])
        self.assertTrue(row["audio_outdated"])

    def test_no_audio_means_not_flagged(self):
        token = self.user()
        novel_id = self.novel(token)
        a = self.chapter(token, novel_id, "A", 1)
        self.client.patch(f"/api/chapters/{a}", json={"content": "Khác."},
                          headers=self.auth(token))
        body = self.client.get(f"/api/chapters/{a}",
                               headers=self.auth(token)).json()
        self.assertFalse(body["audio_outdated"])
        self.assertIsNone(body["audio"])

    def test_regenerating_audio_clears_the_flag(self):
        token = self.user()
        owner = self.owner_id(token)
        novel_id = self.novel(token)
        a = self.chapter(token, novel_id, "A", 1)
        self.give_audio(a, owner, iso(-60))
        self.client.patch(f"/api/chapters/{a}", json={"content": "Nội dung mới."},
                          headers=self.auth(token))
        self.assertTrue(self.client.get(
            f"/api/chapters/{a}", headers=self.auth(token)).json()["audio_outdated"])

        self.give_audio(a, owner, iso(60))          # tao lai audio
        self.assertFalse(self.client.get(
            f"/api/chapters/{a}", headers=self.auth(token)).json()["audio_outdated"])

    def test_newest_track_decides_not_the_oldest(self):
        token = self.user()
        owner = self.owner_id(token)
        novel_id = self.novel(token)
        a = self.chapter(token, novel_id, "A", 1)
        self.give_audio(a, owner, iso(-600))        # ban cu
        self.give_audio(a, owner, iso(600))         # ban moi

        row = self.client.get(f"/api/novels/{novel_id}",
                              headers=self.auth(token)).json()["chapters"][0]
        self.assertFalse(row["audio_outdated"])


class TestOutdatedAudioIsOnlyAWarning(Base):
    def test_the_audio_file_is_never_deleted_for_being_stale(self):
        token = self.user()
        owner = self.owner_id(token)
        novel_id = self.novel(token)
        a = self.chapter(token, novel_id, "A", 1)
        self.give_audio(a, owner, iso(-60))
        track_id = self.store.track_for_chapter(a).track_id

        self.client.patch(f"/api/chapters/{a}", json={"content": "Nội dung mới."},
                          headers=self.auth(token))

        after = self.store.track_for_chapter(a)
        self.assertIsNotNone(after, "không được xoá audio chỉ vì nội dung đã sửa")
        self.assertEqual(after.track_id, track_id)

    def test_editing_content_does_not_touch_the_stored_object(self):
        token = self.user()
        owner = self.owner_id(token)
        novel_id = self.novel(token)
        a = self.chapter(token, novel_id, "A", 1)
        key = f"audio/{a}.mp3"
        server_main.storage.put(key, b"gia lap mp3")
        self.give_audio(a, owner, iso(-60))

        self.client.patch(f"/api/chapters/{a}", json={"content": "Nội dung mới."},
                          headers=self.auth(token))

        self.assertTrue(server_main.storage.exists(key),
                        "object trong kho phải còn nguyên")

    def test_stale_audio_is_still_playable(self):
        """Nguoi dung duoc quyen GIU audio hien tai — nen no phai phat duoc."""
        token = self.user()
        owner = self.owner_id(token)
        novel_id = self.novel(token)
        a = self.chapter(token, novel_id, "A", 1)
        key = f"audio/{a}.mp3"
        server_main.storage.put(key, b"gia lap mp3")
        self.store.create_track(AudioTrack(
            chapter_id=a, owner_id=owner, voice_id="edge:x", object_key=key,
            content_hash="h", size_bytes=11, created_at=iso(-60)))
        self.client.patch(f"/api/chapters/{a}", json={"content": "Nội dung mới."},
                          headers=self.auth(token))

        link = self.client.get(f"/api/audio/{a}/url", headers=self.auth(token))
        self.assertEqual(link.status_code, 200)
        body = link.json()
        self.assertTrue(body["url"] or body["stream_url"])

    def test_the_flag_is_not_persisted_as_an_unknown_attribute(self):
        from server.appwrite_store import COL_CHAPTERS, PERSISTED_FIELDS, persistable

        self.assertNotIn("audio_outdated", PERSISTED_FIELDS[COL_CHAPTERS])
        self.assertNotIn("audio_outdated",
                         persistable(COL_CHAPTERS, {"audio_outdated": True}))


class TestTimestampComparison(Base):
    """
    Khong duoc so sanh hai moc thoi gian bang chuoi.

    `now_iso()` sinh `...T03:01:36+00:00`, Appwrite tra `...T03:01:36.000+00:00`.
    So sanh chuoi thi `+` (0x2B) < `.` (0x2E), nen ban khong co mili giay luon bi
    coi la som hon — sai o dung cho quan trong nhat.
    """

    def test_millisecond_form_is_compared_correctly(self):
        from server.domain import AudioStamp, Chapter

        # Cung mot thoi diem, hai cach viet khac nhau. `AudioStamp` khong co
        # `rate`/`chunk_chars` -> di duong DU PHONG, tuc la so moc thoi gian.
        chapter = Chapter(novel_id="n", owner_id="u", title="A",
                          updated_at="2026-08-07T03:01:36+00:00")
        self.assertFalse(
            server_main._audio_outdated(
                chapter, AudioStamp(created_at="2026-08-07T03:01:36.000+00:00")),
            "cùng một thời điểm thì không được coi là audio cũ")

    def test_string_comparison_would_have_been_wrong(self):
        """Chung minh cai bay that su ton tai."""
        khong_ms = "2026-08-07T03:01:36+00:00"
        co_ms = "2026-08-07T03:01:36.000+00:00"
        self.assertTrue(khong_ms < co_ms, "so sánh chuỗi cho kết quả sai thứ tự")

    def test_unparseable_timestamp_does_not_raise_or_guess(self):
        from server.domain import AudioStamp, Chapter

        chapter = Chapter(novel_id="n", owner_id="u", title="A",
                          updated_at="khong-phai-thoi-gian")
        self.assertFalse(server_main._audio_outdated(
            chapter, AudioStamp(created_at="2026-08-07T03:01:36+00:00")))

    def test_no_audio_means_not_outdated(self):
        from server.domain import AudioStamp, Chapter

        chapter = Chapter(novel_id="n", owner_id="u", title="A")
        self.assertFalse(server_main._audio_outdated(chapter, None))
        self.assertFalse(server_main._audio_outdated(chapter, AudioStamp(created_at="")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
