"""
Ba lo hong ve tinh dung dan va kha nang mo rong.

1. `audio_outdated` phai so DAU VAN TAY, khong phai moc thoi gian. Sua noi dung
   roi hoan nguyen chinh xac thi canh bao phai TU TAT.
2. Truy van danh sach Appwrite khong duoc dung o 25 ban ghi mac dinh.
3. Thu vien audio khong duoc goi `/api/novels/{id}` cho tung truyen.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.domain import AudioTrack, TtsJob, job_fingerprint


def iso(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc)
            + timedelta(seconds=offset_seconds)).isoformat(timespec="seconds")


class CountingStore(MockMetadataStore):
    """Dem so lan tung phuong thuc kho duoc goi."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: Dict[str, int] = {}

    def _tick(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def list_chapters(self, novel_id: str):
        self._tick("list_chapters")
        return super().list_chapters(novel_id)

    def chapters_for_owner(self, owner_id: str):
        self._tick("chapters_for_owner")
        return super().chapters_for_owner(owner_id)

    def get_novel(self, novel_id: str):
        self._tick("get_novel")
        return super().get_novel(novel_id)

    def audio_by_chapter(self, chapter_ids: Sequence[str]):
        self._tick("audio_by_chapter")
        return super().audio_by_chapter(chapter_ids)

    def job_settings(self, owner_id: str, fingerprints: Sequence[str]):
        self._tick("job_settings")
        return super().job_settings(owner_id, fingerprints)

    def list_jobs(self, owner_id: str, chapter_id: Optional[str] = None):
        self._tick("list_jobs")
        return super().list_jobs(owner_id, chapter_id)


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.fresh_backend()
        self._real_storage = server_main.storage
        server_main.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.client = TestClient(server_main.app)

    def fresh_backend(self) -> None:
        """
        Kho VA danh tinh moi hoan toan.

        Phai cap lai ca `identity`: cac vong `subTest` dung lai cung email, ma
        `MockIdentityAdapter` cu thi email da ton tai -> dang ky tra 400 va test
        chet o `KeyError: 'token'` chu khong phai o dieu dang kiem.
        """
        server_main.identity = MockIdentityAdapter()
        self.store = CountingStore()
        server_main.store = self.store

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

    def chapter(self, token: str, novel_id: str, title: str = "C1",
                content: str = "Nội dung gốc.", order: int = 1) -> str:
        return self.client.post(
            "/api/chapters",
            json={"novel_id": novel_id, "title": title,
                  "content": content, "order_index": order},
            headers=self.auth(token),
        ).json()["chapter"]["chapter_id"]

    def render(self, chapter_id: str, owner: str, content: str,
               voice: str = "edge:vi-VN-A", rate: str = "1.0",
               chunk: int = 2000, made_at: Optional[str] = None) -> Tuple[str, str]:
        """
        Tao MOT cap job + track nhu duong chay that.

        Tra ve `(fingerprint, track_id)`. Day la diem quan trong: track chi luu
        `content_hash`, con `rate`/`chunk_chars` nam o job — dung nhu that.
        """
        fingerprint = job_fingerprint(content, voice, rate, chunk)
        self.store.create_job(TtsJob(
            owner_id=owner, chapter_id=chapter_id, voice_id=voice,
            content_hash=fingerprint, rate=rate, chunk_chars=chunk,
        ))
        track = self.store.create_track(AudioTrack(
            chapter_id=chapter_id, owner_id=owner, voice_id=voice,
            object_key=f"audio/{chapter_id}-{fingerprint[:8]}.mp3",
            content_hash=fingerprint, size_bytes=10,
            created_at=made_at or iso(),
        ))
        return fingerprint, track.track_id

    def outdated(self, chapter_id: str, token: str) -> bool:
        return self.client.get(f"/api/chapters/{chapter_id}",
                               headers=self.auth(token)).json()["audio_outdated"]

    def row_outdated(self, novel_id: str, chapter_id: str, token: str) -> bool:
        body = self.client.get(f"/api/novels/{novel_id}",
                               headers=self.auth(token)).json()
        row = next(c for c in body["chapters"] if c["chapter_id"] == chapter_id)
        return row["audio_outdated"]

    def edit(self, chapter_id: str, token: str, content: str):
        return self.client.patch(f"/api/chapters/{chapter_id}",
                                 json={"content": content},
                                 headers=self.auth(token))


# =============================================== 1. dau van tay


class TestFingerprintDecidesOutdated(Base):
    def setUp(self) -> None:
        super().setUp()
        self.token = self.user()
        self.owner = self.owner_id(self.token)
        self.novel_id = self.novel(self.token)
        self.goc = "Nội dung gốc."
        self.chapter_id = self.chapter(self.token, self.novel_id, content=self.goc)
        self.render(self.chapter_id, self.owner, self.goc)

    def test_fresh_audio_is_not_outdated(self):
        self.assertFalse(self.outdated(self.chapter_id, self.token))

    def test_editing_content_marks_it_outdated(self):
        self.edit(self.chapter_id, self.token, "Nội dung đã đổi.")
        self.assertTrue(self.outdated(self.chapter_id, self.token))

    def test_restoring_the_exact_content_clears_the_warning(self):
        """
        Day la ca lo hong duoc sua.

        Cach do bang `updated_at` khong bao gio tat duoc canh bao nay, vi hoan
        nguyen noi dung cung lam moc thoi gian moi hon.
        """
        self.edit(self.chapter_id, self.token, "Nội dung đã đổi.")
        self.assertTrue(self.outdated(self.chapter_id, self.token))

        self.edit(self.chapter_id, self.token, self.goc)
        self.assertFalse(self.outdated(self.chapter_id, self.token),
                         "hoàn nguyên nội dung thì cảnh báo phải tự tắt")

    def test_restoring_works_in_the_chapter_list_too(self):
        self.edit(self.chapter_id, self.token, "Khác.")
        self.assertTrue(self.row_outdated(self.novel_id, self.chapter_id, self.token))
        self.edit(self.chapter_id, self.token, self.goc)
        self.assertFalse(self.row_outdated(self.novel_id, self.chapter_id, self.token))

    def test_whitespace_difference_still_counts_as_changed(self):
        """Dau van tay la ma bam — them mot dau cach cung la noi dung khac."""
        self.edit(self.chapter_id, self.token, self.goc + " ")
        self.assertTrue(self.outdated(self.chapter_id, self.token))

    def test_updated_at_alone_does_not_decide(self):
        """Sua rieng TIEU DE khong lam audio cu — noi dung khong doi."""
        self.client.patch(f"/api/chapters/{self.chapter_id}",
                          json={"title": "Tiêu đề mới"}, headers=self.auth(self.token))
        self.assertFalse(self.outdated(self.chapter_id, self.token),
                         "sửa tiêu đề không làm audio lệch nội dung")


class TestRenderParametersMatter(Base):
    def setUp(self) -> None:
        super().setUp()
        self.token = self.user()
        self.owner = self.owner_id(self.token)
        self.novel_id = self.novel(self.token)
        self.goc = "Nội dung gốc."

    def test_a_track_rendered_at_another_rate_is_not_falsely_outdated(self):
        """
        Phai dung tham so CUA TRACK, khong dung gia tri mac dinh.

        Lay mac dinh `rate=1.0` de so voi track render o `rate=1.5` thi dau van
        tay khac nhau vinh vien, va chuong bi bao cu mai.
        """
        chapter_id = self.chapter(self.token, self.novel_id, content=self.goc)
        self.render(chapter_id, self.owner, self.goc, rate="1.5")
        self.assertFalse(self.outdated(chapter_id, self.token))

    def test_a_track_rendered_with_another_chunk_size_is_not_falsely_outdated(self):
        chapter_id = self.chapter(self.token, self.novel_id, content=self.goc)
        self.render(chapter_id, self.owner, self.goc, chunk=1500)
        self.assertFalse(self.outdated(chapter_id, self.token))

    def test_a_track_rendered_with_another_voice_is_not_falsely_outdated(self):
        chapter_id = self.chapter(self.token, self.novel_id, content=self.goc)
        self.render(chapter_id, self.owner, self.goc, voice="piper:vi-B")
        self.assertFalse(self.outdated(chapter_id, self.token))

    def test_all_four_parameters_are_in_the_fingerprint(self):
        base = job_fingerprint("noi dung", "voice-a", "1.0", 2000)
        self.assertNotEqual(base, job_fingerprint("khac", "voice-a", "1.0", 2000))
        self.assertNotEqual(base, job_fingerprint("noi dung", "voice-b", "1.0", 2000))
        self.assertNotEqual(base, job_fingerprint("noi dung", "voice-a", "1.5", 2000))
        self.assertNotEqual(base, job_fingerprint("noi dung", "voice-a", "1.0", 1500))

    def test_regenerating_after_an_edit_clears_the_warning(self):
        chapter_id = self.chapter(self.token, self.novel_id, content=self.goc)
        self.render(chapter_id, self.owner, self.goc, made_at=iso(-60))
        moi = "Nội dung mới hoàn toàn."
        self.edit(chapter_id, self.token, moi)
        self.assertTrue(self.outdated(chapter_id, self.token))

        # Tao lai audio cho noi dung MOI
        self.render(chapter_id, self.owner, moi, made_at=iso(60))
        self.assertFalse(self.outdated(chapter_id, self.token))

    def test_the_newest_track_decides(self):
        chapter_id = self.chapter(self.token, self.novel_id, content=self.goc)
        moi = "Nội dung mới."
        self.render(chapter_id, self.owner, self.goc, made_at=iso(-600))
        self.edit(chapter_id, self.token, moi)
        self.render(chapter_id, self.owner, moi, made_at=iso(600))
        self.assertFalse(self.outdated(chapter_id, self.token))


class TestOldTrackWithoutFingerprintData(Base):
    """
    Track cu: co `content_hash` nhung khong tra duoc `rate`/`chunk_chars` (job da
    bi xoa). Phai quay ve so moc thoi gian, KHONG duoc no hay doan bua.
    """

    def setUp(self) -> None:
        super().setUp()
        self.token = self.user()
        self.owner = self.owner_id(self.token)
        self.novel_id = self.novel(self.token)
        self.chapter_id = self.chapter(self.token, self.novel_id,
                                       content="Nội dung gốc.")

    def old_track(self, made_at: str) -> None:
        """Track khong co job kem theo — dung nhu du lieu tao truoc thay doi nay."""
        self.store.create_track(AudioTrack(
            chapter_id=self.chapter_id, owner_id=self.owner, voice_id="edge:x",
            object_key="audio/cu.mp3", content_hash="dau-van-tay-cu",
            size_bytes=10, created_at=made_at,
        ))

    def test_audio_newer_than_the_edit_is_not_outdated(self):
        self.old_track(iso(60))
        self.assertFalse(self.outdated(self.chapter_id, self.token))

    def test_audio_older_than_the_edit_is_outdated(self):
        self.old_track(iso(-60))
        self.edit(self.chapter_id, self.token, "Đã đổi.")
        self.assertTrue(self.outdated(self.chapter_id, self.token))

    def test_it_does_not_raise(self):
        self.old_track(iso(-60))
        r = self.client.get(f"/api/chapters/{self.chapter_id}",
                            headers=self.auth(self.token))
        self.assertEqual(r.status_code, 200)

    def test_the_old_track_is_never_rewritten_or_deleted(self):
        """Khong migration pha du lieu: track cu duoc doc nhu no von co."""
        self.old_track(iso(-60))
        before = self.store.track_for_chapter(self.chapter_id)
        self.edit(self.chapter_id, self.token, "Đã đổi.")
        self.outdated(self.chapter_id, self.token)
        after = self.store.track_for_chapter(self.chapter_id)
        self.assertEqual(after.track_id, before.track_id)
        self.assertEqual(after.content_hash, "dau-van-tay-cu")
        self.assertEqual(after.object_key, before.object_key)

    def test_a_mix_of_old_and_new_tracks_both_work(self):
        old_chapter = self.chapter_id
        self.old_track(iso(-60))
        new_chapter = self.chapter(self.token, self.novel_id, "C2",
                                   content="Chương hai.", order=2)
        self.render(new_chapter, self.owner, "Chương hai.")

        self.edit(old_chapter, self.token, "Đã đổi.")
        body = self.client.get(f"/api/novels/{self.novel_id}",
                               headers=self.auth(self.token)).json()
        flags = {c["chapter_id"]: c["audio_outdated"] for c in body["chapters"]}
        self.assertTrue(flags[old_chapter], "track cũ: dùng mốc thời gian")
        self.assertFalse(flags[new_chapter], "track mới: dùng dấu vân tay")

    def test_no_appwrite_attribute_was_added_for_this(self):
        """Khong doi luoc do: `rate`/`chunk_chars` lay tu job, khong tu track."""
        from server.appwrite_store import COL_TRACKS, PERSISTED_FIELDS

        self.assertNotIn("rate", PERSISTED_FIELDS[COL_TRACKS])
        self.assertNotIn("chunk_chars", PERSISTED_FIELDS[COL_TRACKS])
        # Job thi VON DA co san hai truong nay
        from server.appwrite_store import COL_JOBS

        self.assertIn("rate", PERSISTED_FIELDS[COL_JOBS])
        self.assertIn("chunk_chars", PERSISTED_FIELDS[COL_JOBS])


class TestFingerprintLookupIsBatched(Base):
    def test_one_job_settings_call_for_the_whole_chapter_list(self):
        token = self.user()
        owner = self.owner_id(token)
        novel_id = self.novel(token)
        for i in range(1, 31):
            cid = self.chapter(token, novel_id, f"C{i}", content=f"Nội dung {i}.", order=i)
            self.render(cid, owner, f"Nội dung {i}.")

        self.store.calls.clear()
        self.client.get(f"/api/novels/{novel_id}", headers=self.auth(token))
        self.assertEqual(self.store.calls.get("job_settings"), 1)
        self.assertEqual(self.store.calls.get("audio_by_chapter"), 1)

    def test_store_calls_do_not_grow_with_chapter_count(self):
        token = self.user()
        owner = self.owner_id(token)

        def calls_for(count: int) -> Dict[str, int]:
            novel_id = self.novel(token, f"N{count}")
            for i in range(1, count + 1):
                cid = self.chapter(token, novel_id, f"C{i}",
                                   content=f"Nội dung {i}.", order=i)
                self.render(cid, owner, f"Nội dung {i}.")
            self.store.calls.clear()
            self.client.get(f"/api/novels/{novel_id}", headers=self.auth(token))
            return dict(self.store.calls)

        self.assertEqual(calls_for(3), calls_for(60))

    def test_no_job_settings_call_when_no_chapter_has_audio(self):
        token = self.user()
        novel_id = self.novel(token)
        self.chapter(token, novel_id)
        self.store.calls.clear()
        self.client.get(f"/api/novels/{novel_id}", headers=self.auth(token))
        self.assertIsNone(self.store.calls.get("job_settings"))

    def test_job_settings_never_leaks_another_users_job(self):
        mine = self.user("toi@example.com")
        other = self.user("nguoikhac@example.com")
        other_owner = self.owner_id(other)
        # Nguoi khac co job cung dau van tay
        fingerprint = job_fingerprint("Nội dung gốc.", "edge:vi-VN-A", "1.0", 2000)
        self.store.create_job(TtsJob(
            owner_id=other_owner, chapter_id="chp_cua_nguoi_khac",
            voice_id="edge:vi-VN-A", content_hash=fingerprint,
            rate="1.0", chunk_chars=2000,
        ))
        found = self.store.job_settings(self.owner_id(mine), [fingerprint])
        self.assertEqual(found, {}, "không được lấy job của người khác")


# =============================================== 2. phan trang


class TestPaginationBoundaries(Base):
    """Bien 0, 1, 25, 26 va nhieu trang — 25 la gioi han mac dinh cua Appwrite."""

    def setUp(self) -> None:
        super().setUp()
        self.token = self.user()
        self.owner = self.owner_id(self.token)

    def make_novels(self, count: int) -> None:
        for i in range(count):
            self.novel(self.token, f"Truyện {i:03d}")

    def make_jobs(self, count: int) -> None:
        novel_id = self.novel(self.token, "Chứa job")
        chapter_id = self.chapter(self.token, novel_id)
        for i in range(count):
            self.store.create_job(TtsJob(
                owner_id=self.owner, chapter_id=chapter_id, voice_id="edge:x",
                content_hash=f"h{i:04d}", rate="1.0", chunk_chars=2000,
            ))

    # -- list_novels ---------------------------------------------------------

    def test_novels_at_each_boundary(self):
        for count in (0, 1, 25, 26, 60, 137):
            with self.subTest(count=count):
                self.fresh_backend()
                self.token = self.user()
                self.owner = self.owner_id(self.token)
                self.make_novels(count)
                items = self.store.list_novels(owner_id=self.owner)
                self.assertEqual(len(items), count,
                                 f"{count} truyện: lấy về {len(items)}")

    def test_mine_endpoint_returns_all_novels_past_25(self):
        self.make_novels(26)
        body = self.client.get("/api/novels", params={"mine": "true"},
                               headers=self.auth(self.token)).json()
        self.assertEqual(body["count"], 26)

    # -- list_jobs -----------------------------------------------------------

    def test_jobs_at_each_boundary(self):
        for count in (0, 1, 25, 26, 60, 137):
            with self.subTest(count=count):
                self.fresh_backend()
                self.token = self.user()
                self.owner = self.owner_id(self.token)
                self.make_jobs(count)
                items = self.store.list_jobs(self.owner)
                self.assertEqual(len(items), count,
                                 f"{count} job: lấy về {len(items)}")

    def test_jobs_endpoint_returns_all_past_25(self):
        self.make_jobs(26)
        body = self.client.get("/api/jobs", headers=self.auth(self.token)).json()
        self.assertEqual(body["count"], 26)

    def test_jobs_keep_newest_first(self):
        """Phan trang khong duoc lam mat thu tu."""
        self.make_jobs(30)
        items = self.store.list_jobs(self.owner)
        stamps = [j.created_at for j in items]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

    def test_jobs_of_another_user_never_appear(self):
        self.make_jobs(30)
        other = self.user("nguoikhac@example.com")
        body = self.client.get("/api/jobs", headers=self.auth(other)).json()
        self.assertEqual(body["count"], 0)

    # -- tracks_for_chapter --------------------------------------------------

    def test_tracks_at_each_boundary(self):
        """
        `_purge_chapter` dung ham nay de lay object can xoa. Cat o 25 thi track
        thu 26 tro di khong bao gio duoc xoa — object mo coi.
        """
        for count in (0, 1, 25, 26, 60):
            with self.subTest(count=count):
                novel_id = self.novel(self.token, f"N{count}")
                chapter_id = self.chapter(self.token, novel_id)
                for i in range(count):
                    self.store.create_track(AudioTrack(
                        chapter_id=chapter_id, owner_id=self.owner,
                        voice_id="edge:x", object_key=f"audio/{chapter_id}-{i}.mp3",
                        content_hash=f"h{i}", size_bytes=1,
                    ))
                items = self.store.tracks_for_chapter(chapter_id)
                self.assertEqual(len(items), count)

    def test_deleting_a_chapter_removes_every_track_past_25(self):
        novel_id = self.novel(self.token, "Nhiều track")
        chapter_id = self.chapter(self.token, novel_id)
        for i in range(30):
            self.store.create_track(AudioTrack(
                chapter_id=chapter_id, owner_id=self.owner, voice_id="edge:x",
                object_key=f"audio/{chapter_id}-{i}.mp3",
                content_hash=f"h{i}", size_bytes=1,
            ))
        r = self.client.delete(f"/api/chapters/{chapter_id}",
                               headers=self.auth(self.token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["removed"]["tracks"], 30,
                         "phải xoá hết track, không dừng ở 25")
        self.assertEqual(self.store.tracks_for_chapter(chapter_id), [])


class TestNoListQueryStillTruncates(unittest.TestCase):
    """
    Ra soat TOAN BO truy van danh sach cua ban Appwrite.

    Moi truy van co the vuot 25 ban ghi PHAI di qua `_list_all`. Test nay doc
    ma nguon nen se bat duoc mot ham moi viet sai ngay tu dau.
    """

    #: Co gioi han so ban ghi ngay trong truy van -> khong the bi cat.
    BOUNDED = {
        "track_for_chapter": "co q_limit(1)",
        "_list_all": "chinh no la vong lat trang",
        "find_novels": "co nhanh limit=None dung _list_all",
    }

    def test_every_unbounded_list_query_paginates(self):
        """
        Doc nguon TUNG PHUONG THUC bang `inspect`, khong tach bang regex.

        Ban truoc tach bang regex `def (\\w+)\\(self[^)]*\\):` va no truot o cac
        ham co chu ky nhieu dong hoac co `-> Optional[...]`, khien than ham bi
        gop vao ham truoc do. Test khi ay dat ca tren code CON LOI.
        """
        import inspect

        from server import appwrite_store

        offenders = []
        for name, member in vars(appwrite_store.AppwriteMetadataStore).items():
            if not inspect.isfunction(member) or name in self.BOUNDED:
                continue
            body = inspect.getsource(member)
            if "self._list(" in body and "q_limit(" not in body:
                offenders.append(name)
        self.assertEqual(sorted(offenders), [],
                         f"cac ham nay dung _list ma khong gioi han: {offenders}")

    def test_the_paginating_helper_asks_for_more_than_25(self):
        from server.appwrite_store import PAGE_SIZE

        self.assertGreater(PAGE_SIZE, 25)

    def test_pagination_is_a_loop_not_one_big_limit(self):
        """Khong duoc va bang cach dat mot `limit` that lon."""
        import inspect

        from server import appwrite_store

        source = inspect.getsource(appwrite_store.AppwriteMetadataStore._list_all)
        self.assertIn("while True", source)
        self.assertIn("q_offset", source)
        self.assertLessEqual(appwrite_store.PAGE_SIZE, 100,
                             "trang qua lon la mot ban va, khong phai phan trang")


# =============================================== 3. N+1 o thu vien


class TestMyChaptersEndpoint(Base):
    def setUp(self) -> None:
        super().setUp()
        self.token = self.user()
        self.owner = self.owner_id(self.token)

    def test_it_returns_chapters_from_every_novel(self):
        a = self.novel(self.token, "A")
        b = self.novel(self.token, "B")
        self.chapter(self.token, a, "A1")
        self.chapter(self.token, a, "A2", order=2)
        self.chapter(self.token, b, "B1")

        body = self.client.get("/api/chapters", params={"mine": "true"},
                               headers=self.auth(self.token)).json()
        self.assertEqual(sorted(c["title"] for c in body["chapters"]),
                         ["A1", "A2", "B1"])
        self.assertEqual(body["count"], 3)

    def test_one_store_call_no_matter_how_many_novels(self):
        for i in range(20):
            novel_id = self.novel(self.token, f"N{i}")
            self.chapter(self.token, novel_id, f"C{i}")

        self.store.calls.clear()
        self.client.get("/api/chapters", params={"mine": "true"},
                        headers=self.auth(self.token))
        self.assertEqual(self.store.calls.get("chapters_for_owner"), 1)
        self.assertIsNone(self.store.calls.get("list_chapters"),
                          "khong duoc goi list_chapters cho tung truyen")
        self.assertIsNone(self.store.calls.get("get_novel"))

    def test_store_calls_are_identical_for_3_and_for_40_novels(self):
        def calls_for(count: int) -> Dict[str, int]:
            self.fresh_backend()
            token = self.user(f"u{count}@example.com")
            for i in range(count):
                novel_id = self.novel(token, f"N{i}")
                self.chapter(token, novel_id, f"C{i}")
            self.store.calls.clear()
            self.client.get("/api/chapters", params={"mine": "true"},
                            headers=self.auth(token))
            return dict(self.store.calls)

        self.assertEqual(calls_for(3), calls_for(40))

    def test_it_carries_no_chapter_content(self):
        """Day la du lieu DANH SACH — noi dung chuong se lam phan hoi phinh to."""
        novel_id = self.novel(self.token)
        self.chapter(self.token, novel_id, content="Nội dung rất dài." * 100)
        body = self.client.get("/api/chapters", params={"mine": "true"},
                               headers=self.auth(self.token)).json()
        self.assertNotIn("content", body["chapters"][0])
        self.assertIn("char_count", body["chapters"][0])

    def test_it_creates_no_presigned_audio_url(self):
        novel_id = self.novel(self.token)
        chapter_id = self.chapter(self.token, novel_id)
        self.render(chapter_id, self.owner, "Nội dung gốc.")
        body = self.client.get("/api/chapters", params={"mine": "true"},
                               headers=self.auth(self.token)).json()
        for row in body["chapters"]:
            for key in ("audio_url", "object_key", "url"):
                self.assertNotIn(key, row)

    # -- quyen ---------------------------------------------------------------

    def test_anonymous_is_rejected(self):
        self.assertEqual(self.client.get("/api/chapters",
                                         params={"mine": "true"}).status_code, 401)

    def test_it_never_returns_another_users_chapters(self):
        mine = self.novel(self.token, "Của tôi")
        self.chapter(self.token, mine, "Chương của tôi")

        other = self.user("nguoikhac@example.com")
        other_novel = self.novel(other, "Của người khác")
        self.chapter(other, other_novel, "Chương của người khác")

        body = self.client.get("/api/chapters", params={"mine": "true"},
                               headers=self.auth(self.token)).json()
        titles = [c["title"] for c in body["chapters"]]
        self.assertEqual(titles, ["Chương của tôi"])

    def test_it_includes_drafts_because_they_are_mine(self):
        novel_id = self.novel(self.token, "Nháp")     # khong publish
        self.chapter(self.token, novel_id, "Chương nháp")
        body = self.client.get("/api/chapters", params={"mine": "true"},
                               headers=self.auth(self.token)).json()
        self.assertEqual([c["title"] for c in body["chapters"]], ["Chương nháp"])

    def test_without_mine_it_refuses_instead_of_leaking(self):
        """Khong co che do cong khai — de tranh lo chuong cua nguoi khac."""
        r = self.client.get("/api/chapters", headers=self.auth(self.token))
        self.assertEqual(r.status_code, 400)

    def test_public_novel_chapter_list_still_works_as_before(self):
        novel_id = self.novel(self.token, "Công khai")
        self.chapter(self.token, novel_id, "C1")
        self.client.post(f"/api/novels/{novel_id}/publish",
                         headers=self.auth(self.token))
        body = self.client.get(f"/api/novels/{novel_id}").json()
        self.assertEqual([c["title"] for c in body["chapters"]], ["C1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
