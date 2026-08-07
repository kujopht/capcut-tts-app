"""
A. Worker recovery — job ket o `running`.
B. Doi soat object audio mo coi.

Hai dieu bo test nay giu chat nhat:

- Recovery KHONG duoc danh dau moi job `running` thanh `failed` luc khoi dong,
  khong duoc giat job cua worker con song, va chay lai bao nhieu lan cung cho
  cung ket qua.
- Doi soat mac dinh KHONG XOA GI. Che do xoa chi cham vao object da qua an han,
  khong duoc tham chieu, va khong thuoc job dang xu ly — kiem lai ngay truoc khi
  xoa.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi.testclient import TestClient

from server import main as server_main
from server import reconcile
from server.adapters import (
    LocalStorageAdapter,
    MockIdentityAdapter,
    MockMetadataStore,
    StoredObject,
)
from server.domain import AudioTrack, JobStatus, TtsJob, job_fingerprint


def iso(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc)
            + timedelta(seconds=offset_seconds)).isoformat(timespec="seconds")


def hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc)
            - timedelta(hours=hours)).isoformat(timespec="seconds")


class Base(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        self.store = MockMetadataStore()
        server_main.store = self.store
        self._real_storage = server_main.storage
        self.root = Path(tempfile.mkdtemp())
        self.storage = LocalStorageAdapter(self.root)
        server_main.storage = self.storage
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.storage = self._real_storage

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

    def chapter(self, token: str, novel_id: str, content: str = "Nội dung.") -> str:
        return self.client.post(
            "/api/chapters",
            json={"novel_id": novel_id, "title": "C1", "content": content,
                  "order_index": 1},
            headers=self.auth(token),
        ).json()["chapter"]["chapter_id"]

    def a_job(self, owner: str, chapter_id: str, *, status: JobStatus,
              lease: Optional[str] = None, attempts: int = 1,
              content: str = "Nội dung.", output_key: Optional[str] = None) -> TtsJob:
        return self.store.create_job(TtsJob(
            owner_id=owner, chapter_id=chapter_id, voice_id="mock:v1",
            content_hash=job_fingerprint(content, "mock:v1", "1.0", 2000),
            status=status, lease_expires_at=lease,
            lease_owner="worker-khac" if lease else None,
            attempts=attempts, output_key=output_key,
        ))


# ================================================================ A. recovery


class TestLeaseSemantics(Base):
    def test_a_live_lease_is_not_stale(self):
        token = self.user()
        job = self.a_job(self.owner_id(token),
                         self.chapter(token, self.novel(token)),
                         status=JobStatus.RUNNING, lease=iso(60))
        self.assertTrue(job.lease_is_live())
        self.assertFalse(job.is_stale)

    def test_an_expired_lease_is_stale(self):
        token = self.user()
        job = self.a_job(self.owner_id(token),
                         self.chapter(token, self.novel(token)),
                         status=JobStatus.RUNNING, lease=iso(-60))
        self.assertFalse(job.lease_is_live())
        self.assertTrue(job.is_stale)

    def test_no_lease_at_all_counts_as_stale(self):
        """Job cu, tao truoc khi co lease — chinh la thu can recovery."""
        token = self.user()
        job = self.a_job(self.owner_id(token),
                         self.chapter(token, self.novel(token)),
                         status=JobStatus.RUNNING, lease=None)
        self.assertTrue(job.is_stale)

    def test_unparseable_lease_counts_as_expired(self):
        job = TtsJob(owner_id="u", chapter_id="c", voice_id="v", content_hash="h",
                     status=JobStatus.RUNNING, lease_expires_at="khong-phai-gio")
        self.assertFalse(job.lease_is_live())

    def test_a_completed_job_is_never_stale(self):
        job = TtsJob(owner_id="u", chapter_id="c", voice_id="v", content_hash="h",
                     status=JobStatus.COMPLETED, lease_expires_at=None)
        self.assertFalse(job.is_stale)

    def test_millisecond_lease_form_parses(self):
        """Appwrite tra datetime kem `.000` — khong duoc coi la khong doc duoc."""
        future = (datetime.now(timezone.utc) + timedelta(minutes=5))
        job = TtsJob(owner_id="u", chapter_id="c", voice_id="v", content_hash="h",
                     status=JobStatus.RUNNING,
                     lease_expires_at=future.isoformat(timespec="milliseconds"))
        self.assertTrue(job.lease_is_live())

    def test_lease_outlives_the_heartbeat_interval(self):
        """Mot nhip heartbeat tre khong duoc lam job bi giat."""
        self.assertGreater(server_main.JOB_LEASE_SECONDS,
                           server_main.JOB_HEARTBEAT_SECONDS * 2)


class TestSweepDoesNotHarm(Base):
    def test_it_never_fails_every_running_job_on_startup(self):
        """Job con lease hop le phai duoc de yen — day la lan can pha du lieu."""
        token = self.user()
        owner = self.owner_id(token)
        chapter_id = self.chapter(token, self.novel(token))
        alive = self.a_job(owner, chapter_id, status=JobStatus.RUNNING,
                           lease=iso(300))

        report = server_main.recover_stale_jobs()

        self.assertEqual(report["bo_qua_con_lease"], 1)
        self.assertEqual(report["chay_lai"], 0)
        self.assertEqual(self.store.get_job(alive.job_id).status, JobStatus.RUNNING)

    def test_it_does_not_touch_a_completed_job(self):
        token = self.user()
        owner = self.owner_id(token)
        chapter_id = self.chapter(token, self.novel(token))
        done = self.a_job(owner, chapter_id, status=JobStatus.COMPLETED,
                          output_key="audio/x.mp3")

        server_main.recover_stale_jobs()

        after = self.store.get_job(done.job_id)
        self.assertEqual(after.status, JobStatus.COMPLETED)
        self.assertEqual(after.output_key, "audio/x.mp3")

    def test_it_does_not_touch_a_failed_job(self):
        token = self.user()
        owner = self.owner_id(token)
        job = self.a_job(owner, self.chapter(token, self.novel(token)),
                         status=JobStatus.FAILED)
        server_main.recover_stale_jobs()
        self.assertEqual(self.store.get_job(job.job_id).status, JobStatus.FAILED)

    def test_a_brand_new_pending_job_is_left_alone(self):
        """Job vua tao xong dang cho thread khoi dong — khong duoc nhan lai."""
        token = self.user()
        job = self.a_job(self.owner_id(token),
                         self.chapter(token, self.novel(token)),
                         status=JobStatus.PENDING, lease=None)
        report = server_main.recover_stale_jobs()
        self.assertEqual(report["bo_qua_con_moi"], 1)
        self.assertEqual(self.store.get_job(job.job_id).status, JobStatus.PENDING)

    def test_it_never_deletes_anything(self):
        import inspect

        source = inspect.getsource(server_main.recover_stale_jobs)
        for banned in ("delete_track", "delete_job", "storage.delete",
                       "delete_chapter", "delete_novel"):
            self.assertNotIn(banned, source,
                             f"recovery khong duoc goi {banned}")

    def test_the_startup_hook_never_runs_the_purge_tool(self):
        import inspect

        source = inspect.getsource(server_main.start_job_sweeper)
        self.assertNotIn("purge", source)
        self.assertNotIn("reconcile", source)


class TestRetryLimit(Base):
    def test_a_job_past_the_limit_becomes_failed_with_a_readable_message(self):
        token = self.user()
        owner = self.owner_id(token)
        job = self.a_job(owner, self.chapter(token, self.novel(token)),
                         status=JobStatus.RUNNING, lease=iso(-60),
                         attempts=server_main.JOB_MAX_ATTEMPTS)

        report = server_main.recover_stale_jobs()

        self.assertEqual(report["het_luot_thu"], 1)
        after = self.store.get_job(job.job_id)
        self.assertEqual(after.status, JobStatus.FAILED)
        self.assertEqual(after.error_kind, "worker_lost")
        self.assertIn("Hãy thử lại", after.error_message)
        self.assertIsNone(after.output_key)

    def test_a_job_below_the_limit_is_retried_not_failed(self):
        token = self.user()
        owner = self.owner_id(token)
        job = self.a_job(owner, self.chapter(token, self.novel(token)),
                         status=JobStatus.RUNNING, lease=iso(-60), attempts=1)

        report = server_main.recover_stale_jobs()
        self.assertEqual(report["chay_lai"], 1)
        self.assertEqual(report["het_luot_thu"], 0)

    def test_attempts_never_grow_without_bound(self):
        """Quet lien tuc khong duoc thu vo han."""
        token = self.user()
        owner = self.owner_id(token)
        job = self.a_job(owner, self.chapter(token, self.novel(token)),
                         status=JobStatus.RUNNING, lease=iso(-60),
                         attempts=server_main.JOB_MAX_ATTEMPTS + 5)
        server_main.recover_stale_jobs()
        self.assertEqual(self.store.get_job(job.job_id).status, JobStatus.FAILED)

    def test_a_failed_job_releases_its_lease(self):
        token = self.user()
        owner = self.owner_id(token)
        job = self.a_job(owner, self.chapter(token, self.novel(token)),
                         status=JobStatus.RUNNING, lease=iso(-60),
                         attempts=server_main.JOB_MAX_ATTEMPTS)
        server_main.recover_stale_jobs()
        after = self.store.get_job(job.job_id)
        self.assertIsNone(after.lease_expires_at)
        self.assertIsNone(after.lease_owner)


# Tranh claim va fencing token nay nam o `test_claim_atomicity.py`: cach do cu
# gia lap bang cach ghi de `get_job`, con claim moi la mot thao tac NGUYEN TU o
# tang kho nen phai do bang barrier va nhieu luong that.


class TestRecoveryIsIdempotent(Base):
    def test_running_the_sweep_twice_does_not_double_anything(self):
        token = self.user()
        owner = self.owner_id(token)
        job = self.a_job(owner, self.chapter(token, self.novel(token)),
                         status=JobStatus.RUNNING, lease=iso(-60),
                         attempts=server_main.JOB_MAX_ATTEMPTS)

        first = server_main.recover_stale_jobs()
        second = server_main.recover_stale_jobs()

        self.assertEqual(first["het_luot_thu"], 1)
        # Lan hai: job da `failed` nen khong con trong danh sach quet
        self.assertEqual(second["da_quet"], 0)
        self.assertEqual(self.store.get_job(job.job_id).status, JobStatus.FAILED)

    def test_running_the_sweep_on_an_empty_store_is_harmless(self):
        report = server_main.recover_stale_jobs()
        self.assertEqual(report["da_quet"], 0)
        self.assertEqual(report["chay_lai"], 0)

    def test_two_runs_never_create_two_tracks_for_one_result(self):
        """
        Day la thu lam cho recovery dung dan DO CAU TRUC.

        `create_track` la tim-hoac-tao theo `(chapter_id, content_hash)`, nen hai
        lan chay cua cung mot job chi cho ra MOT track.
        """
        token = self.user()
        owner = self.owner_id(token)
        chapter_id = self.chapter(token, self.novel(token))
        digest = job_fingerprint("Nội dung.", "mock:v1", "1.0", 2000)

        def make() -> AudioTrack:
            return self.store.create_track(AudioTrack(
                chapter_id=chapter_id, owner_id=owner, voice_id="mock:v1",
                object_key=reconcile.expected_output_key(owner, chapter_id, digest),
                content_hash=digest, size_bytes=10,
            ))

        first, second = make(), make()
        self.assertEqual(first.track_id, second.track_id)
        self.assertEqual(len(self.store.tracks_for_chapter(chapter_id)), 1)

    def test_a_second_run_never_overwrites_a_valid_track(self):
        token = self.user()
        owner = self.owner_id(token)
        chapter_id = self.chapter(token, self.novel(token))
        digest = "cung-mot-dau-van-tay"
        original = self.store.create_track(AudioTrack(
            chapter_id=chapter_id, owner_id=owner, voice_id="mock:v1",
            object_key="audio/ban-goc.mp3", content_hash=digest, size_bytes=111,
        ))
        again = self.store.create_track(AudioTrack(
            chapter_id=chapter_id, owner_id=owner, voice_id="mock:v1",
            object_key="audio/ban-khac.mp3", content_hash=digest, size_bytes=222,
        ))
        self.assertEqual(again.track_id, original.track_id)
        self.assertEqual(again.object_key, "audio/ban-goc.mp3")
        self.assertEqual(again.size_bytes, 111)


class TestStuckJobIsNoLongerReused(Base):
    def test_creating_a_job_resumes_a_stuck_one_instead_of_returning_it_dead(self):
        """
        Truoc day nhanh nay tra lai chinh cai job chet, mai mai.

        `find_job_by_fingerprint` chi loai `failed`, nen mot job ket `running`
        duoc tai dung vinh vien va nguoi dung khong bao gio tao duoc audio.
        """
        token = self.user()
        owner = self.owner_id(token)
        novel_id = self.novel(token)
        chapter_id = self.chapter(token, novel_id, "Nội dung.")
        stuck = self.a_job(owner, chapter_id, status=JobStatus.RUNNING,
                           lease=iso(-600), attempts=1)
        # CHOT thanh so nguyen: `MockMetadataStore` giu CUNG THAM CHIEU voi object
        # nay, va `_run_job` sua thuoc tinh tai cho — doc `stuck.attempts` sau khi
        # goi API se ra gia tri da bi doi, va phep so tro thanh vo nghia.
        attempts_before = int(stuck.attempts)

        r = self.client.post("/api/jobs",
                             json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
                             headers=self.auth(token))
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertTrue(body["reused"])
        self.assertEqual(body["job"]["job_id"], stuck.job_id)

        # KHONG khang dinh `lease_owner == WORKER_ID`: thread recovery co the da
        # chay xong ngay (TTS bi gia lap trong bo test) va nha lease, nen phep so
        # do phu thuoc thoi diem. Dieu can khang dinh la job KHONG con ket voi
        # lease cua worker da chet.
        after = self.store.get_job(stuck.job_id)
        self.assertNotEqual(after.lease_owner, "worker-khac")
        self.assertGreater(after.attempts, attempts_before,
                           "phai tinh them mot lan thu")
        if not after.status.is_terminal:
            self.assertEqual(after.lease_owner, server_main.WORKER_ID)
            self.assertTrue(after.lease_is_live())

    def test_creating_a_job_fails_a_stuck_one_past_the_retry_limit(self):
        token = self.user()
        owner = self.owner_id(token)
        chapter_id = self.chapter(token, self.novel(token), "Nội dung.")
        stuck = self.a_job(owner, chapter_id, status=JobStatus.RUNNING,
                           lease=iso(-600), attempts=server_main.JOB_MAX_ATTEMPTS)

        body = self.client.post(
            "/api/jobs", json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
            headers=self.auth(token)).json()
        self.assertEqual(body["job"]["status"], "failed")
        self.assertEqual(self.store.get_job(stuck.job_id).error_kind, "worker_lost")

    def test_a_healthy_running_job_is_still_reused_untouched(self):
        token = self.user()
        owner = self.owner_id(token)
        chapter_id = self.chapter(token, self.novel(token), "Nội dung.")
        alive = self.a_job(owner, chapter_id, status=JobStatus.RUNNING,
                           lease=iso(300))

        body = self.client.post(
            "/api/jobs", json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
            headers=self.auth(token)).json()
        self.assertTrue(body["reused"])
        after = self.store.get_job(alive.job_id)
        self.assertEqual(after.status, JobStatus.RUNNING)
        self.assertEqual(after.lease_owner, "worker-khac",
                         "khong duoc giat job cua worker con song")


class TestJobResponseStaysCompatible(Base):
    OLD_KEYS = {
        "job_id", "owner_id", "chapter_id", "voice_id", "content_hash", "status",
        "progress", "total_parts", "done_parts", "output_key", "error_kind",
        "error_message", "rate", "chunk_chars", "created_at", "started_at",
        "finished_at",
    }

    def test_only_additive_keys_appear(self):
        token = self.user()
        owner = self.owner_id(token)
        job = self.a_job(owner, self.chapter(token, self.novel(token)),
                         status=JobStatus.RUNNING, lease=iso(60))
        body = self.client.get(f"/api/jobs/{job.job_id}",
                               headers=self.auth(token)).json()["job"]
        self.assertEqual(self.OLD_KEYS - set(body), set(), "mất khoá cũ")
        self.assertEqual(set(body) - self.OLD_KEYS,
                         {"lease_expires_at", "lease_owner", "attempts"})

    def test_old_jobs_without_the_new_fields_still_load(self):
        """Job cu trong Appwrite khong co ba thuoc tinh moi."""
        from server.appwrite_store import _job_from_doc

        job = _job_from_doc({
            "job_id": "job_cu", "owner_id": "u", "chapter_id": "c",
            "voice_id": "v", "content_hash": "h", "status": "running",
            "created_at": iso(-3600),
        })
        self.assertIsNone(job.lease_expires_at)
        self.assertEqual(job.attempts, 0)
        self.assertTrue(job.is_stale, "job cu ket running -> can recovery")

    def test_the_new_fields_are_optional_in_appwrite(self):
        from scripts.setup_appwrite import SCHEMA

        attrs = {a[0]: a for a in SCHEMA["tts_jobs"]["attributes"]}
        for name in ("lease_expires_at", "lease_owner", "attempts"):
            self.assertIn(name, attrs, f"schema thiếu {name}")
            self.assertFalse(attrs[name][2],
                             f"{name} phải là tuỳ chọn để tương thích ngược")


# ================================================================ B. doi soat


class ReconcileBase(Base):
    def setUp(self) -> None:
        super().setUp()
        self.token = self.user()
        self.owner = self.owner_id(self.token)
        self.novel_id = self.novel(self.token)
        self.chapter_id = self.chapter(self.token, self.novel_id)

    def key_for(self, digest: str) -> str:
        return reconcile.expected_output_key(self.owner, self.chapter_id, digest)

    def put_object(self, key: str, data: bytes = b"gia lap mp3",
                   age_hours: float = 0) -> None:
        self.storage.put(key, data)
        if age_hours:
            import os
            path = self.root / key
            old = (datetime.now(timezone.utc)
                   - timedelta(hours=age_hours)).timestamp()
            os.utime(path, (old, old))

    def track_for(self, key: str, digest: str) -> AudioTrack:
        return self.store.create_track(AudioTrack(
            chapter_id=self.chapter_id, owner_id=self.owner, voice_id="mock:v1",
            object_key=key, content_hash=digest, size_bytes=11,
        ))


class TestScanClassifies(ReconcileBase):
    def test_a_referenced_object_is_not_orphaned(self):
        key = self.key_for("h1")
        self.put_object(key, age_hours=48)
        self.track_for(key, "h1")

        report = reconcile.scan(self.store, self.storage)
        self.assertEqual(report.da_tham_chieu, 1)
        self.assertEqual(report.mo_coi, [])

    def test_an_unreferenced_old_object_is_orphaned(self):
        key = self.key_for("h-mo-coi")
        self.put_object(key, age_hours=48)

        report = reconcile.scan(self.store, self.storage)
        self.assertEqual([o["key"] for o in report.mo_coi], [key])

    def test_an_object_newer_than_the_grace_period_is_spared(self):
        """Object vua upload xong ma track chua kip ghi."""
        key = self.key_for("h-vua-upload")
        self.put_object(key, age_hours=1)

        report = reconcile.scan(self.store, self.storage)
        self.assertEqual(report.mo_coi, [])
        self.assertEqual(report.con_moi, [key])

    def test_an_object_of_a_running_job_is_spared_even_if_old(self):
        digest = job_fingerprint("Nội dung.", "mock:v1", "1.0", 2000)
        key = self.key_for(digest)
        self.put_object(key, age_hours=48)
        self.a_job(self.owner, self.chapter_id, status=JobStatus.RUNNING,
                   lease=iso(300))

        report = reconcile.scan(self.store, self.storage)
        self.assertEqual(report.mo_coi, [])
        self.assertEqual(report.dang_xu_ly, [key])

    def test_an_object_of_a_pending_job_is_spared(self):
        digest = job_fingerprint("Nội dung.", "mock:v1", "1.0", 2000)
        key = self.key_for(digest)
        self.put_object(key, age_hours=48)
        self.a_job(self.owner, self.chapter_id, status=JobStatus.PENDING)

        report = reconcile.scan(self.store, self.storage)
        self.assertEqual(report.dang_xu_ly, [key])

    def test_a_record_pointing_at_a_missing_object_is_reported(self):
        self.track_for(self.key_for("h-mat-file"), "h-mat-file")

        report = reconcile.scan(self.store, self.storage)
        self.assertEqual(len(report.ban_ghi_thieu_file), 1)
        self.assertEqual(report.ban_ghi_thieu_file[0]["object_key"],
                         self.key_for("h-mat-file"))

    def test_the_expected_key_matches_what_the_job_runner_writes(self):
        """
        Lech mot ky tu la coi audio cua job dang chay la mo coi.

        Doc cong thuc tu chinh `main._run_job` de hai cho khong the troi nhau.
        """
        import inspect
        import re

        source = inspect.getsource(server_main._run_job)
        match = re.search(r'output_key = f"([^"]+)"', source)
        self.assertIsNotNone(match, "khong tim thay cong thuc output_key")
        template = match.group(1)
        built = (template
                 .replace("{job.owner_id}", "U")
                 .replace("{job.chapter_id}", "C")
                 .replace("{job.content_hash}", "H"))
        self.assertEqual(built, reconcile.expected_output_key("U", "C", "H"))

    def test_scan_reports_the_dry_run_mode(self):
        self.assertEqual(reconcile.scan(self.store, self.storage).che_do, "dry-run")

    def test_scan_creates_no_presigned_url(self):
        class StorageThatRefusesToSign(LocalStorageAdapter):
            def signed_url(self, *a, **k):
                raise AssertionError("doi soat khong duoc ky URL nao")

        storage = StorageThatRefusesToSign(self.root)
        self.put_object(self.key_for("h1"), age_hours=48)
        reconcile.scan(self.store, storage)   # khong duoc nem

    def test_the_report_contains_no_secret(self):
        self.put_object(self.key_for("h1"), age_hours=48)
        text = str(reconcile.scan(self.store, self.storage).to_dict())
        for banned in ("X-Amz-Signature", "cloudflarestorage", "APPWRITE_API_KEY",
                       "secret", "password"):
            self.assertNotIn(banned, text)


class TestScanPagination(ReconcileBase):
    def test_it_walks_past_one_page_of_objects(self):
        for i in range(120):
            self.put_object(self.key_for(f"h{i:04d}"), age_hours=48)

        report = reconcile.scan(self.store, self.storage)
        self.assertEqual(report.tong_object, 120)
        self.assertEqual(len(report.mo_coi), 120)

    def test_it_walks_past_25_tracks(self):
        """Gioi han 25 cua Appwrite khong duoc lam mat ban ghi khi doi soat."""
        for i in range(30):
            key = self.key_for(f"h{i:04d}")
            self.put_object(key, age_hours=48)
            self.track_for(key, f"h{i:04d}")

        report = reconcile.scan(self.store, self.storage)
        self.assertEqual(report.da_tham_chieu, 30)
        self.assertEqual(report.mo_coi, [])

    def test_r2_listing_uses_a_paginator(self):
        """S3 tra toi da 1000 khoa moi lan — goi mot lan la mat phan con lai."""
        import inspect

        from server.r2_adapter import R2StorageAdapter

        source = inspect.getsource(R2StorageAdapter.list_objects)
        self.assertIn("get_paginator", source)
        self.assertIn("paginate", source)


class TestPurgeIsSafe(ReconcileBase):
    def test_without_confirm_nothing_is_deleted(self):
        key = self.key_for("h-mo-coi")
        self.put_object(key, age_hours=48)

        report = reconcile.purge(self.store, self.storage, confirm=False)

        self.assertEqual(report.da_xoa, [])
        self.assertEqual(report.che_do, "dry-run")
        self.assertTrue(self.storage.exists(key), "object phải còn nguyên")

    def test_with_confirm_only_eligible_objects_go(self):
        orphan = self.key_for("h-mo-coi")
        referenced = self.key_for("h-dung")
        fresh = self.key_for("h-moi")
        self.put_object(orphan, age_hours=48)
        self.put_object(referenced, age_hours=48)
        self.put_object(fresh, age_hours=1)
        self.track_for(referenced, "h-dung")

        report = reconcile.purge(self.store, self.storage, confirm=True)

        self.assertEqual(report.da_xoa, [orphan])
        self.assertFalse(self.storage.exists(orphan))
        self.assertTrue(self.storage.exists(referenced))
        self.assertTrue(self.storage.exists(fresh))

    def test_it_rechecks_references_right_before_deleting(self):
        """
        Giua luc quet va luc xoa, mot job co the vua hoan tat.

        Kho gia lap nay tao track NGAY SAU khi quet xong — object phai duoc tha.
        """
        key = self.key_for("h-vua-duoc-dung")
        self.put_object(key, age_hours=48)

        real_scan = reconcile.scan
        chapter_id, owner = self.chapter_id, self.owner
        store = self.store

        def scan_then_reference(*a, **k):
            report = real_scan(*a, **k)
            store.create_track(AudioTrack(
                chapter_id=chapter_id, owner_id=owner, voice_id="mock:v1",
                object_key=key, content_hash="h-vua-duoc-dung", size_bytes=1,
            ))
            return report

        reconcile.scan = scan_then_reference
        try:
            report = reconcile.purge(self.store, self.storage, confirm=True)
        finally:
            reconcile.scan = real_scan

        self.assertEqual(report.da_xoa, [])
        self.assertEqual(len(report.bo_qua_khi_xoa), 1)
        self.assertEqual(report.bo_qua_khi_xoa[0]["vi_sao"],
                         "vua co ban ghi tro toi")
        self.assertTrue(self.storage.exists(key))

    def test_it_never_deletes_an_object_of_a_live_job(self):
        digest = job_fingerprint("Nội dung.", "mock:v1", "1.0", 2000)
        key = self.key_for(digest)
        self.put_object(key, age_hours=48)
        self.a_job(self.owner, self.chapter_id, status=JobStatus.RUNNING,
                   lease=iso(300))

        report = reconcile.purge(self.store, self.storage, confirm=True)
        self.assertEqual(report.da_xoa, [])
        self.assertTrue(self.storage.exists(key))

    def test_one_failing_delete_does_not_lose_the_whole_report(self):
        good = self.key_for("h-xoa-duoc")
        bad = self.key_for("h-xoa-loi")
        self.put_object(good, age_hours=48)
        self.put_object(bad, age_hours=48)

        class StorageThatFailsOnOne(LocalStorageAdapter):
            def delete(self, key: str) -> bool:
                if key == bad:
                    raise OSError("ổ đĩa lỗi")
                return super().delete(key)

        report = reconcile.purge(self.store, StorageThatFailsOnOne(self.root),
                                 confirm=True)

        self.assertEqual(report.da_xoa, [good])
        self.assertEqual(len(report.loi), 1)
        self.assertIn("OSError", report.loi[0]["loi"])
        self.assertEqual(report.tong_object, 2, "bao cao van day du")

    def test_it_never_deletes_a_track_record(self):
        """Ban ghi thieu file la MAT DU LIEU — chi bao, khong bao gio tu xoa."""
        import inspect

        source = inspect.getsource(reconcile.purge) + inspect.getsource(reconcile.scan)
        for banned in ("delete_track", "delete_job", "delete_chapter",
                       "delete_novel"):
            self.assertNotIn(banned, source)

    def test_purge_mode_is_labelled_in_the_report(self):
        report = reconcile.purge(self.store, self.storage, confirm=True)
        self.assertEqual(report.che_do, "delete")


class TestCommandLineNeedsTwoFlags(unittest.TestCase):
    def test_delete_alone_is_refused(self):
        import inspect

        from scripts import reconcile_audio

        source = inspect.getsource(reconcile_audio.main)
        self.assertIn("yes_really_delete", source)
        self.assertIn("Từ chối xoá", source)

    def test_dry_run_is_the_default(self):
        import inspect

        from scripts import reconcile_audio

        source = inspect.getsource(reconcile_audio.main)
        # `--delete` phai la co bat, tuc la mac dinh khong xoa
        self.assertIn('"--delete", action="store_true"', source)

    def test_the_script_is_not_imported_by_the_server(self):
        import inspect

        from server import main as m

        source = inspect.getsource(m)
        self.assertNotIn("reconcile_audio", source)
        self.assertNotIn("from server.reconcile import", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
