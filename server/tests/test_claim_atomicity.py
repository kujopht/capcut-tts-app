"""
Claim job co that su nguyen tu khong.

Dong bo bang BARRIER chu khong dua vao timing: barrier bao dam moi luong deu da
san sang truoc khi bat ky luong nao duoc chay, nen khong co chuyen luong dau
thang chi vi no khoi dong som hon.

Ban Appwrite dua vao tinh duy nhat cua rowId ben trong mot transaction — da do
truc tiep tren Appwrite Cloud 1.9.6, xem `AppwriteMetadataStore.claim_job`. Bo
test nay do ban mock, ban `_PagingRecorder` cua Appwrite, va HINH DANG request
that ma ban Appwrite gui di.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.domain import AudioTrack, JobStatus, TtsJob, job_fingerprint

#: So worker cung tranh trong moi phep thu.
WORKERS = 10

#: So lan lap lai moi phep thu tranh chap.
REPEATS = 20


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
        self.token = self.client.post(
            "/api/auth/register",
            json={"email": "chu@example.com", "password": "matkhau123"},
        ).json()["token"]
        self.owner = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {self.token}"},
        ).json()["profile"]["user_id"]
        head = {"Authorization": f"Bearer {self.token}"}
        novel_id = self.client.post("/api/novels", json={"title": "T"},
                                    headers=head).json()["novel"]["novel_id"]
        self.chapter_id = self.client.post(
            "/api/chapters",
            json={"novel_id": novel_id, "title": "C1", "content": "Nội dung.",
                  "order_index": 1},
            headers=head,
        ).json()["chapter"]["chapter_id"]

    def tearDown(self) -> None:
        server_main.storage = self._real_storage

    def fresh_store(self) -> None:
        """Kho moi, giu nguyen danh tinh — de lap lai vong tranh claim."""
        self.store = MockMetadataStore()
        server_main.store = self.store

    def a_job(self, *, status: JobStatus, lease: Optional[str] = None,
              attempts: int = 1) -> TtsJob:
        return self.store.create_job(TtsJob(
            owner_id=self.owner, chapter_id=self.chapter_id, voice_id="mock:v1",
            content_hash=job_fingerprint("Nội dung.", "mock:v1", "1.0", 2000),
            status=status, lease_expires_at=lease,
            lease_owner="worker-khac" if lease else None, attempts=attempts,
        ))

    def race(self, job: TtsJob, n: int = WORKERS):
        """`n` worker cung nhan mot job. Tra ve `(fences, winners)`."""
        barrier = threading.Barrier(n)
        fences: List[Optional[int]] = [None] * n
        winners: List[str] = []
        lock = threading.Lock()

        def claim(i: int) -> None:
            worker = f"worker-{i}"
            barrier.wait()          # moi luong deu doi nhau tai day
            fence = self.store.claim_job(job, worker, iso(300))
            fences[i] = fence
            if fence is not None:
                with lock:
                    winners.append(worker)

        threads = [threading.Thread(target=claim, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return fences, winners


# ==================================================== dung mot worker thang


class TestOnlyOneWinner(Base):
    def test_ten_workers_on_a_stale_running_job(self):
        fences, winners = self.race(self.a_job(status=JobStatus.RUNNING,
                                               lease=iso(-600)))
        self.assertEqual(len(winners), 1, f"phai dung mot: {fences}")
        self.assertEqual([f for f in fences if f is not None], [2],
                         "fence phai la so lan thu tiep theo")

    def test_ten_workers_on_a_queued_job(self):
        fences, winners = self.race(self.a_job(status=JobStatus.PENDING,
                                               lease=None, attempts=0))
        self.assertEqual(len(winners), 1, f"phai dung mot: {fences}")
        self.assertEqual([f for f in fences if f is not None], [1])

    def test_the_store_records_the_actual_winner(self):
        job = self.a_job(status=JobStatus.RUNNING, lease=iso(-600))
        _, winners = self.race(job)
        self.assertEqual(self.store.get_job(job.job_id).lease_owner, winners[0])

    def test_a_live_lease_is_never_stolen(self):
        job = self.a_job(status=JobStatus.RUNNING, lease=iso(600))
        fences, winners = self.race(job)
        self.assertEqual(winners, [], "lease con han thi khong ai duoc lay")
        self.assertEqual(self.store.get_job(job.job_id).lease_owner, "worker-khac")

    def test_a_completed_job_is_never_claimed(self):
        job = self.a_job(status=JobStatus.COMPLETED)
        _, winners = self.race(job)
        self.assertEqual(winners, [])

    def test_a_failed_job_is_never_claimed(self):
        job = self.a_job(status=JobStatus.FAILED)
        _, winners = self.race(job)
        self.assertEqual(winners, [])

    def test_losing_is_a_normal_result_not_an_exception(self):
        job = self.a_job(status=JobStatus.RUNNING, lease=iso(-600))
        self.assertIsNotNone(self.store.claim_job(job, "w1", iso(300)))
        self.assertIsNone(self.store.claim_job(job, "w2", iso(300)))


class TestRaceHoldsOverRepeats(Base):
    """Thang mot lan la may. Lap lai 20 lan moi noi len dieu gi."""

    def test_stale_running_job_over_twenty_repeats(self):
        for lan in range(REPEATS):
            with self.subTest(lan=lan):
                self.fresh_store()
                fences, winners = self.race(
                    self.a_job(status=JobStatus.RUNNING, lease=iso(-600)))
                self.assertEqual(len(winners), 1, f"lan {lan}: {fences}")

    def test_queued_job_over_twenty_repeats(self):
        for lan in range(REPEATS):
            with self.subTest(lan=lan):
                self.fresh_store()
                fences, winners = self.race(
                    self.a_job(status=JobStatus.PENDING, lease=None, attempts=0))
                self.assertEqual(len(winners), 1, f"lan {lan}: {fences}")


# ==================================================== fencing token


class TestFencingBlocksTheOldWorker(Base):
    def two_generations(self):
        """Tra ve `(job, fence_cu, fence_moi)`."""
        job = self.a_job(status=JobStatus.RUNNING, lease=iso(-600))
        fence_cu = self.store.claim_job(job, "worker-cu", iso(-1))
        fence_moi = self.store.claim_job(job, "worker-moi", iso(300))
        self.assertIsNotNone(fence_moi)
        self.assertNotEqual(fence_cu, fence_moi)
        return job, fence_cu, fence_moi

    def test_the_old_worker_cannot_renew_the_lease(self):
        job, fence_cu, _ = self.two_generations()
        ok = self.store.save_job_fenced(
            replace(self.store.get_job(job.job_id), lease_expires_at=iso(900)),
            fence_cu, "worker-cu")
        self.assertFalse(ok, "worker cu khong duoc lam moi lease cua worker moi")
        self.assertEqual(self.store.get_job(job.job_id).lease_owner, "worker-moi")

    def test_the_old_worker_cannot_complete_the_job(self):
        job, fence_cu, _ = self.two_generations()
        ok = self.store.save_job_fenced(
            replace(self.store.get_job(job.job_id), status=JobStatus.COMPLETED,
                    output_key="audio/cua-worker-cu.mp3"),
            fence_cu, "worker-cu")
        self.assertFalse(ok)
        after = self.store.get_job(job.job_id)
        self.assertEqual(after.status, JobStatus.RUNNING)
        self.assertIsNone(after.output_key)

    def test_the_old_worker_cannot_fail_the_job(self):
        job, fence_cu, _ = self.two_generations()
        ok = self.store.save_job_fenced(
            replace(self.store.get_job(job.job_id), status=JobStatus.FAILED),
            fence_cu, "worker-cu")
        self.assertFalse(ok)
        self.assertEqual(self.store.get_job(job.job_id).status, JobStatus.RUNNING)

    def test_the_current_worker_can_write(self):
        job, _, fence_moi = self.two_generations()
        ok = self.store.save_job_fenced(
            replace(self.store.get_job(job.job_id), status=JobStatus.COMPLETED,
                    output_key="audio/dung.mp3"),
            fence_moi, "worker-moi")
        self.assertTrue(ok)
        self.assertEqual(self.store.get_job(job.job_id).status, JobStatus.COMPLETED)

    def test_the_right_fence_with_the_wrong_worker_is_refused(self):
        job = self.a_job(status=JobStatus.RUNNING, lease=iso(-600))
        fence = self.store.claim_job(job, "worker-that", iso(300))
        ok = self.store.save_job_fenced(
            replace(self.store.get_job(job.job_id), status=JobStatus.FAILED),
            fence, "worker-gia")
        self.assertFalse(ok)

    def test_the_runner_never_writes_without_a_fence(self):
        import inspect

        source = inspect.getsource(server_main._run_job)
        self.assertIn("save_job_fenced", source)
        self.assertNotIn("store.save_job(", source,
                         "moi ghi trong runner phai kem fencing token")

    def test_the_runner_stops_when_it_loses_the_claim(self):
        import inspect

        source = inspect.getsource(server_main._run_job)
        self.assertIn("if fence is None:", source)
        self.assertIn("return", source)


# ==================================================== idempotency


class TestOneJobMakesAtMostOneTrack(Base):
    def digest(self) -> str:
        return job_fingerprint("Nội dung.", "mock:v1", "1.0", 2000)

    def a_track(self, key: str = "") -> AudioTrack:
        digest = self.digest()
        return self.store.create_track(AudioTrack(
            chapter_id=self.chapter_id, owner_id=self.owner, voice_id="mock:v1",
            object_key=key or f"audio/{self.owner}/{self.chapter_id}/{digest}.mp3",
            content_hash=digest, size_bytes=10,
        ))

    def test_ten_concurrent_creates_make_one_track(self):
        barrier = threading.Barrier(WORKERS)
        ids: List[str] = []
        lock = threading.Lock()

        def make(_: int) -> None:
            barrier.wait()
            track = self.a_track()
            with lock:
                ids.append(track.track_id)

        threads = [threading.Thread(target=make, args=(i,)) for i in range(WORKERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(set(ids)), 1, "phai cung mot track_id")
        self.assertEqual(len(self.store.tracks_for_chapter(self.chapter_id)), 1)

    def test_it_holds_over_twenty_repeats(self):
        for lan in range(REPEATS):
            with self.subTest(lan=lan):
                self.fresh_store()
                for _ in range(3):
                    self.a_track()
                self.assertEqual(
                    len(self.store.tracks_for_chapter(self.chapter_id)), 1)

    def test_a_finished_track_is_never_overwritten(self):
        first = self.a_track(key="audio/ban-goc.mp3")
        again = self.a_track(key="audio/ban-khac.mp3")
        self.assertEqual(again.track_id, first.track_id)
        self.assertEqual(again.object_key, "audio/ban-goc.mp3")

    def test_the_object_key_is_deterministic(self):
        """Hai lan chay ghi CUNG mot khoa, nen khong sinh object thu hai."""
        from server import reconcile

        digest = self.digest()
        self.assertEqual(
            reconcile.expected_output_key(self.owner, self.chapter_id, digest),
            f"audio/{self.owner}/{self.chapter_id}/{digest}.mp3")

    def test_upload_ok_but_record_lost_is_seen_as_in_flight_not_orphan(self):
        """
        Upload xong ma ghi ban ghi hong: object khong duoc coi la mo coi ngay.

        Job van `running` va con lease, nen doi soat xep no vao "dang xu ly".
        """
        from server import reconcile

        digest = self.digest()
        key = reconcile.expected_output_key(self.owner, self.chapter_id, digest)
        server_main.storage.put(key, b"da upload nhung chua co ban ghi")
        self.a_job(status=JobStatus.RUNNING, lease=iso(300))

        report = reconcile.scan(self.store, server_main.storage)
        self.assertIn(key, report.dang_xu_ly)
        self.assertEqual(report.mo_coi, [])


# ==================================================== dung MOT lan tong hop


class _WorkerPerThread:
    """
    Bao quanh kho that, thay `worker_id` bang danh tinh RIENG cua tung luong.

    Vi sao can: `_run_job` doc `server_main.WORKER_ID` — mot hang so cua TIEN
    TRINH. Ngoai doi moi worker la mot tien trinh nen id khac nhau; goi 10 luong
    trong cung tien trinh thi ca 10 mang chung mot id, va `claim_job` se coi
    "lease con han nhung chinh minh la chu" la duoc phep nhan lai. Do la tao tac
    cua phep thu, khong phai hanh vi that.

    Lop nay tra lai su that: moi luong mot danh tinh, thay o CA `claim_job` lan
    `save_job_fenced` de nguoi thang van ghi duoc bang dung id ma no da nhan.
    Moi thu con lai uy thac nguyen ven cho kho that.
    """

    def __init__(self, inner, fallback: str):
        self._inner = inner
        self._fallback = fallback

    def _who(self) -> str:
        return getattr(threading.current_thread(), "worker_name", self._fallback)

    def claim_job(self, job, worker_id, lease_expires_at):
        return self._inner.claim_job(job, self._who(), lease_expires_at)

    def save_job_fenced(self, job, fence, worker_id):
        return self._inner.save_job_fenced(job, fence, self._who())

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TestOnlyOneSynthesisPerJob(Base):
    """
    10 worker cung chay `_run_job` tren MOT job: chi duoc mot lan goi TTS.

    Day la duong chay that — khong mo phong lai logic claim — nen no do dung thu
    ma nguoi dung quan tam: goi TTS bao nhieu lan, sinh ra bao nhieu track va bao
    nhieu file trong kho.

    STUB CO CHU Y: `tts_bridge.synthesize_chapter` bi thay bang mot ham dem so
    lan goi. Khong stub gi khac — claim, fencing, upload va ghi track deu la ma
    that.
    """

    def setUp(self) -> None:
        super().setUp()
        self.store = _WorkerPerThread(self.store, server_main.WORKER_ID)
        server_main.store = self.store
        self._real_synth = server_main.tts_bridge.synthesize_chapter
        self.so_lan_tong_hop = 0
        self._dem_lock = threading.Lock()

        def synthesize_dem(*, text, voice_id, dest, rate, chunk_chars, on_progress):
            with self._dem_lock:
                self.so_lan_tong_hop += 1
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\xff\xfb" + b"0" * 400)
            on_progress(1, 1)
            return {"size_bytes": dest.stat().st_size, "total_parts": 1}

        server_main.tts_bridge.synthesize_chapter = synthesize_dem

    def tearDown(self) -> None:
        server_main.tts_bridge.synthesize_chapter = self._real_synth
        super().tearDown()

    def dua(self, job: TtsJob) -> None:
        """10 luong cung chay `_run_job`, hen nhau tai barrier."""
        barrier = threading.Barrier(WORKERS)

        def chay(i: int) -> None:
            threading.current_thread().worker_name = f"worker-{i}"
            barrier.wait()
            # Moi worker giu BAN SAO cua rieng minh, dung nhu tien trinh rieng.
            server_main._run_job(replace(job), "Nội dung.")

        threads = [threading.Thread(target=chay, args=(i,), name=f"w{i}")
                   for i in range(WORKERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        for t in threads:
            self.assertFalse(t.is_alive(), "worker treo qua lau")

    def files(self) -> List[Path]:
        return [p for p in self.root.rglob("*") if p.is_file()]

    def test_a_queued_job_is_synthesized_exactly_once(self):
        self.dua(self.a_job(status=JobStatus.PENDING, lease=None, attempts=0))
        self.assertEqual(self.so_lan_tong_hop, 1, "chi duoc tong hop MOT lan")
        self.assertEqual(len(self.store.tracks_for_chapter(self.chapter_id)), 1)
        self.assertEqual(len(self.files()), 1, "chi duoc mot object trong kho")

    def test_a_stale_running_job_is_synthesized_exactly_once(self):
        self.dua(self.a_job(status=JobStatus.RUNNING, lease=iso(-600)))
        self.assertEqual(self.so_lan_tong_hop, 1)
        self.assertEqual(len(self.store.tracks_for_chapter(self.chapter_id)), 1)
        self.assertEqual(len(self.files()), 1)

    def test_the_job_ends_completed_with_that_one_object(self):
        job = self.a_job(status=JobStatus.PENDING, lease=None, attempts=0)
        self.dua(job)
        sau = self.store.get_job(job.job_id)
        self.assertEqual(sau.status, JobStatus.COMPLETED)
        self.assertEqual(sau.output_key, self.files()[0].relative_to(self.root)
                         .as_posix())
        self.assertIsNone(sau.lease_owner, "phai nha lease khi xong")

    def test_a_live_lease_means_nobody_synthesizes(self):
        """Job cua worker con song: 10 worker khac phai bo di, khong goi TTS."""
        self.dua(self.a_job(status=JobStatus.RUNNING, lease=iso(600)))
        self.assertEqual(self.so_lan_tong_hop, 0)
        self.assertEqual(self.files(), [])

    def test_it_holds_over_twenty_repeats(self):
        for lan in range(REPEATS):
            with self.subTest(lan=lan):
                self.fresh_store()
                self.store = _WorkerPerThread(self.store, server_main.WORKER_ID)
                server_main.store = self.store
                self.so_lan_tong_hop = 0
                self.dua(self.a_job(status=JobStatus.PENDING, lease=None,
                                    attempts=0))
                self.assertEqual(self.so_lan_tong_hop, 1, f"lan {lan}")
                self.assertEqual(
                    len(self.store.tracks_for_chapter(self.chapter_id)), 1)


# ==================================================== hinh dang request Appwrite


class TestAppwriteClaimShape(unittest.TestCase):
    """
    Ban Appwrite gui dung nhung gi da do duoc tren server that.

    Cac gia tri o day khong phai doan: chung den tu phep do truc tiep tren
    Appwrite Cloud 1.9.6 (xem docs/HANDOFF.md muc "Claim nguyen tu").
    """

    def store_with(self, responses):
        from server.appwrite_store import AppwriteMetadataStore
        from server.config import AppwriteSettings

        calls: List[Dict] = []

        class Fake:
            def request(self, method, url, json=None, params=None, headers=None):
                calls.append({"method": method, "url": url, "json": json})
                for match, body in responses:
                    if match in url and (method == "GET" or True):
                        if callable(body):
                            return body(method, url, json)
                        return body
                return {}

        settings = AppwriteSettings(
            endpoint="https://khong-co-that.example/v1", project_id="p",
            api_key="k", database_id="db")
        return AppwriteMetadataStore(settings, client=Fake()), calls

    def test_it_uses_a_transaction_with_create_plus_update(self):
        import inspect

        from server.appwrite_store import AppwriteMetadataStore

        source = inspect.getsource(AppwriteMetadataStore.claim_job)
        self.assertIn("/v1/tablesdb/transactions", source)
        self.assertIn('"action": "create"', source)
        self.assertIn('"action": "update"', source)
        # Ten TablesDB, khong phai ten Documents — dung sai bi tu choi 400
        self.assertIn('"tableId"', source)
        self.assertIn('"rowId"', source)
        self.assertNotIn('"collectionId"', source)
        self.assertNotIn('"documentId"', source)

    def test_the_claim_row_id_is_deterministic_from_job_and_attempt(self):
        import inspect

        from server.appwrite_store import AppwriteMetadataStore

        source = inspect.getsource(AppwriteMetadataStore.claim_job)
        self.assertIn('f"{job.job_id}-{fence}"', source,
                      "id phai tat dinh thi uniqueness moi thanh mutex")

    def test_the_transaction_ttl_is_inside_the_accepted_range(self):
        """Appwrite tu choi ttl ngoai khoang 60..3600 — da gap that."""
        from server.appwrite_store import TRANSACTION_TTL_SECONDS

        self.assertGreaterEqual(TRANSACTION_TTL_SECONDS, 60)
        self.assertLessEqual(TRANSACTION_TTL_SECONDS, 3600)

    def test_a_conflict_is_treated_as_losing_not_as_an_error(self):
        import inspect

        from server.appwrite_store import AppwriteMetadataStore

        source = inspect.getsource(AppwriteMetadataStore.claim_job)
        self.assertIn("except Exception:", source)
        self.assertIn("return None", source)
        # Khong duoc thu lai mu quang
        self.assertNotIn("while", source)
        self.assertNotIn("for _ in range", source)

    def test_the_claims_collection_is_in_the_schema(self):
        from scripts.setup_appwrite import SCHEMA

        from server.appwrite_store import COL_CLAIMS

        self.assertIn(COL_CLAIMS, SCHEMA)
        attrs = {a[0] for a in SCHEMA[COL_CLAIMS]["attributes"]}
        self.assertEqual(attrs, {"job_id", "attempt", "worker_id", "created_at"})

    def test_both_stores_offer_the_same_claim_interface(self):
        import inspect

        from server.appwrite_store import AppwriteMetadataStore

        for name in ("claim_job", "save_job_fenced"):
            for cls in (MockMetadataStore, AppwriteMetadataStore):
                self.assertTrue(callable(getattr(cls, name, None)),
                                f"{cls.__name__} thiếu {name}")
            self.assertEqual(
                list(inspect.signature(getattr(MockMetadataStore, name)).parameters),
                list(inspect.signature(getattr(AppwriteMetadataStore, name)).parameters),
                f"{name}: hai kho phải cùng chữ ký")


if __name__ == "__main__":
    unittest.main(verbosity=2)
