"""
Tach worker TTS khoi tien trinh web.

Ranh gioi phai khoa lai: web KHONG duoc chay job khi da tach, va worker PHAI
chay duoc. Mot loi that da xay ra khi dung hai y do vao cung mot co — worker doc
`FAS_INLINE_WORKER=false` roi tu cam chinh minh, nen no NHAN job xong khong chay,
va moi vong quet lai dot them mot `attempts` cho den khi job `failed` oan.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server import main as server_main
from server.tests.voice_stub import dung_registry_gia
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.config import ConfigError, _env_bool
from server.domain import JobStatus, TtsJob, job_fingerprint


class Base(unittest.TestCase):
    def setUp(self) -> None:
        dung_registry_gia(self)
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self._storage = server_main.storage
        server_main.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self._can_run = server_main._CAN_RUN_JOBS
        self.client = TestClient(server_main.app)
        self.token = self.client.post(
            "/api/auth/register",
            json={"email": "tacgia@example.com", "password": "matkhau123"},
        ).json()["token"]
        self.head = {"Authorization": f"Bearer {self.token}"}
        self.owner = self.client.get(
            "/api/auth/me", headers=self.head).json()["profile"]["user_id"]

    def tearDown(self) -> None:
        server_main.storage = self._storage
        server_main._CAN_RUN_JOBS = self._can_run

    def a_chapter(self) -> str:
        nid = self.client.post("/api/novels", json={"title": "T"},
                               headers=self.head).json()["novel"]["novel_id"]
        return self.client.post(
            "/api/chapters",
            json={"novel_id": nid, "title": "C", "content": "Nội dung.",
                  "order_index": 1},
            headers=self.head).json()["chapter"]["chapter_id"]


class TestTheWebProcessDoesNotRunJobs(Base):
    def test_creating_a_job_leaves_it_pending(self):
        server_main._CAN_RUN_JOBS = False
        cid = self.a_chapter()
        r = self.client.post("/api/jobs",
                             json={"chapter_id": cid, "voice_id": "mock:v1"},
                             headers=self.head)
        self.assertIn(r.status_code, (200, 201, 202), r.text[:200])
        job_id = r.json()["job"]["job_id"]

        self.assertNotIn(job_id, server_main._job_threads,
                         "web khong duoc spawn thread khi da tach worker")
        sau = self.client.get(f"/api/jobs/{job_id}",
                              headers=self.head).json()["job"]
        self.assertEqual(sau["status"], "pending")
        self.assertEqual(sau["attempts"] or 0, 0)

    def test_the_inline_mode_still_runs_jobs(self):
        """
        Che do cu phai giu nguyen — may lap trinh vien van chay mot tien trinh.

        Doi theo KET QUA chu khong theo `_job_threads`: job mock chay xong gan
        nhu tuc thi, va `_run_job` tu go ban ghi cua minh trong `finally`, nen
        doc dict ngay sau khi tao thuong thay None ke ca khi job da chay dung.
        """
        import time

        # STUB CO CHU Y: `mock:v1` khong phai giong that, nen goi TTS that se
        # `voice_not_found`. Phep thu nay hoi ve DIEU PHOI (co chay job khong),
        # khong hoi ve chat luong giong — nen thay dung buoc tong hop.
        that = server_main.tts_bridge.synthesize_chapter

        def gia(*, text, voice_id, dest, rate, chunk_chars, on_progress):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\xff\xfb" + b"0" * 200)
            on_progress(1, 1)
            return {"size_bytes": dest.stat().st_size, "total_parts": 1}

        server_main.tts_bridge.synthesize_chapter = gia
        self.addCleanup(setattr, server_main.tts_bridge,
                        "synthesize_chapter", that)

        server_main._CAN_RUN_JOBS = True
        cid = self.a_chapter()
        job_id = self.client.post(
            "/api/jobs", json={"chapter_id": cid, "voice_id": "mock:v1"},
            headers=self.head).json()["job"]["job_id"]

        han = time.time() + 30
        while time.time() < han:
            sau = self.client.get(f"/api/jobs/{job_id}",
                                  headers=self.head).json()["job"]
            if sau["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)
        self.assertEqual(sau["status"], "completed",
                         "che do inline phai chay job den noi den chon")
        self.assertGreaterEqual(sau["attempts"] or 0, 1)


class TestASweeperThatCannotRunMustNotClaim(Base):
    """
    LOI DA GAP: worker nhan job roi khong chay duoc.

    `recover_stale_jobs` tang `attempts` moi lan nhan. Mot tien trinh khong chay
    duoc job ma van nhan se day job den `JOB_MAX_ATTEMPTS` chi sau vai vong quet,
    va job `failed` du chua he thu tong hop lan nao.
    """

    def a_stale_job(self) -> TtsJob:
        cid = self.a_chapter()
        return server_main.store.create_job(TtsJob(
            owner_id=self.owner, chapter_id=cid, voice_id="mock:v1",
            content_hash=job_fingerprint("Nội dung.", "mock:v1", "1.0", 2000),
            status=JobStatus.RUNNING,
            lease_expires_at="2020-01-01T00:00:00+00:00",
            lease_owner="worker-da-chet", attempts=1))

    def test_a_process_that_cannot_run_jobs_claims_nothing(self):
        server_main._CAN_RUN_JOBS = False
        job = self.a_stale_job()
        bao_cao = server_main.recover_stale_jobs()
        self.assertEqual(bao_cao.get("khong_duoc_phep_chay"), 1)
        self.assertEqual(bao_cao["da_quet"], 0)
        sau = server_main.store.get_job(job.job_id)
        self.assertEqual(sau.attempts, 1, "khong duoc dot them lan thu nao")
        self.assertEqual(sau.lease_owner, "worker-da-chet")

    def test_repeated_sweeps_never_burn_attempts(self):
        server_main._CAN_RUN_JOBS = False
        job = self.a_stale_job()
        for _ in range(5):
            server_main.recover_stale_jobs()
        self.assertEqual(server_main.store.get_job(job.job_id).attempts, 1)

    def test_a_process_that_can_run_jobs_does_claim(self):
        server_main._CAN_RUN_JOBS = True
        job = self.a_stale_job()
        bao_cao = server_main.recover_stale_jobs()
        self.assertEqual(bao_cao["chay_lai"], 1)
        luong = server_main._job_threads.get(job.job_id)
        if luong is not None:
            luong.join(timeout=30)
        self.assertGreater(server_main.store.get_job(job.job_id).attempts, 1)

    def test_the_report_counts_runs_not_intentions(self):
        """`chay_lai` phai dem thu THAT SU chay, khong dem y dinh."""
        import inspect

        nguon = inspect.getsource(server_main.recover_stale_jobs)
        self.assertIn("if _start_job_thread(", nguon,
                      "phai dem theo ket qua that cua `_start_job_thread`")


class TestTheWorkerOptsInExplicitly(unittest.TestCase):
    def test_enable_job_execution_flips_the_switch(self):
        cu = server_main._CAN_RUN_JOBS
        try:
            server_main._CAN_RUN_JOBS = False
            self.assertFalse(server_main.can_run_jobs())
            server_main.enable_job_execution()
            self.assertTrue(server_main.can_run_jobs())
        finally:
            server_main._CAN_RUN_JOBS = cu

    def test_the_worker_module_enables_execution_before_sweeping(self):
        """
        Worker PHAI bat tuong minh, va phai bat TRUOC vong quet.

        Doc ma nguon vi chay `worker.chay()` that se vao vong lap vo han.
        """
        import inspect

        from server import worker

        nguon = inspect.getsource(worker.chay)
        vi_tri_bat = nguon.find("enable_job_execution()")
        vi_tri_quet = nguon.find("recover_stale_jobs(")
        self.assertGreater(vi_tri_bat, 0, "worker phai goi enable_job_execution()")
        self.assertGreater(vi_tri_quet, 0)
        self.assertLess(vi_tri_bat, vi_tri_quet,
                        "phai bat TRUOC khi quet, neu khong vong quet dau se "
                        "nhan job ma khong chay duoc")

    def test_the_worker_picks_up_fresh_pending_jobs_at_once(self):
        """
        Worker truyen `pending_min_age_seconds=0`.

        Nguong mac dinh 90 giay la de tranh gianh job ma thread cua route dang
        lo. O worker rieng khong co thread nhu vay — cho 90 giay moi doc mot job
        vua tao la vo ly.
        """
        import inspect

        from server import worker

        self.assertIn("pending_min_age_seconds=0",
                      inspect.getsource(worker.chay))

    def test_the_worker_does_not_open_a_port(self):
        import inspect

        from server import worker

        nguon = inspect.getsource(worker)
        for cam in ("uvicorn", "FastAPI(", "app.run(", "socket.bind"):
            self.assertNotIn(cam, nguon,
                             "worker khong phuc vu request, khong mo cong")


class TestDeletingAJobCleansItsClaims(Base):
    """
    LOI DA GAP: xoa truyen/chuong don track, job va object, nhung bo lai cac
    dong `job_claims`.

    `job_claims` chi tang len. Sau hai luot kiem thu, kho con lai hang chuc dong
    tro toi job khong con ton tai — phai don tay hai lan moi sach.
    """

    def a_job_with_claims(self):
        cid = self.a_chapter()
        job = server_main.store.create_job(TtsJob(
            owner_id=self.owner, chapter_id=cid, voice_id="mock:v1",
            content_hash=job_fingerprint("Nội dung.", "mock:v1", "1.0", 2000),
            status=JobStatus.PENDING, attempts=0))
        # Hai lan nhan -> hai dong so ghi chep.
        f1 = server_main.store.claim_job(job, "worker-1", "2020-01-01T00:00:00+00:00")
        job = server_main.store.get_job(job.job_id)
        f2 = server_main.store.claim_job(job, "worker-2", "2030-01-01T00:00:00+00:00")
        self.assertIsNotNone(f1)
        self.assertIsNotNone(f2)
        return job

    def test_deleting_a_job_removes_its_claim_rows(self):
        job = self.a_job_with_claims()
        con = {k for k in server_main.store._claims if k[0] == job.job_id}
        self.assertEqual(len(con), 2, "phai co hai dong claim truoc khi xoa")

        server_main.store.delete_job(job.job_id)

        con = {k for k in server_main.store._claims if k[0] == job.job_id}
        self.assertEqual(con, set(), "xoa job phai don luon so ghi chep claim")

    def test_deleting_one_job_leaves_other_jobs_claims_alone(self):
        a = self.a_job_with_claims()
        b = self.a_job_with_claims()
        server_main.store.delete_job(a.job_id)
        con_b = {k for k in server_main.store._claims if k[0] == b.job_id}
        self.assertEqual(len(con_b), 2, "khong duoc don claim cua job khac")

    def test_the_appwrite_store_deletes_claims_too(self):
        import inspect

        from server import appwrite_store

        nguon = inspect.getsource(appwrite_store.AppwriteMetadataStore.delete_job)
        self.assertIn("COL_CLAIMS", nguon,
                      "ban Appwrite cung phai don `job_claims`")
        vi_tri_job = nguon.find("COL_JOBS")
        vi_tri_claim = nguon.find("COL_CLAIMS")
        self.assertLess(vi_tri_job, vi_tri_claim,
                        "xoa job TRUOC, don claim SAU")


class TestTheFlagIsReadStrictly(unittest.TestCase):
    def test_recognised_values(self):
        import os

        for gia_tri, mong in (("true", True), ("1", True), ("yes", True),
                              ("on", True), ("false", False), ("0", False),
                              ("no", False), ("off", False), ("TRUE", True)):
            os.environ["FAS_TEST_CO"] = gia_tri
            try:
                self.assertEqual(_env_bool("FAS_TEST_CO", not mong), mong,
                                 f"{gia_tri!r} phai doc thanh {mong}")
            finally:
                os.environ.pop("FAS_TEST_CO", None)

    def test_an_unreadable_value_stops_the_process(self):
        """`flase` gõ nhầm KHONG duoc am tham lay mac dinh."""
        import os

        for xau in ("flase", "maybe", "2", "tru"):
            os.environ["FAS_TEST_CO"] = xau
            try:
                with self.assertRaises(ConfigError, msg=f"{xau!r} phai bi tu choi"):
                    _env_bool("FAS_TEST_CO", True)
            finally:
                os.environ.pop("FAS_TEST_CO", None)

    def test_missing_takes_the_default(self):
        import os

        os.environ.pop("FAS_TEST_CO", None)
        self.assertTrue(_env_bool("FAS_TEST_CO", True))
        self.assertFalse(_env_bool("FAS_TEST_CO", False))


class TestReadiness(Base):
    def test_health_does_not_touch_the_backends(self):
        """
        `/api/health` la LIVENESS. Su co tam thoi cua Appwrite khong duoc lam
        nen tang hosting giet mot tien trinh web dang lanh manh.
        """
        import inspect

        nguon = inspect.getsource(server_main.health)
        for cam in ("store.", "storage."):
            self.assertNotIn(cam, nguon,
                             "health khong duoc cham kho du lieu")

    def test_ready_reports_both_dependencies(self):
        r = self.client.get("/api/ready")
        self.assertEqual(r.status_code, 200, r.text[:200])
        d = r.json()
        self.assertEqual(d["status"], "ready")
        self.assertTrue(d["phu_thuoc"]["metadata"]["dat"])
        self.assertTrue(d["phu_thuoc"]["storage"]["dat"])

    def test_ready_returns_503_when_a_dependency_is_down(self):
        class KhoHong:
            def __getattr__(self, ten):
                def no(*a, **k):
                    raise RuntimeError("kho khong tra loi")
                return no

        that = server_main.store
        server_main.store = KhoHong()
        try:
            r = self.client.get("/api/ready")
            self.assertEqual(r.status_code, 503)
            d = r.json()
            self.assertEqual(d["status"], "not_ready")
            self.assertFalse(d["phu_thuoc"]["metadata"]["dat"])
            self.assertEqual(d["phu_thuoc"]["metadata"]["loai_loi"], "RuntimeError")
        finally:
            server_main.store = that

    def test_ready_never_leaks_the_error_message(self):
        """Thong diep loi co the chua endpoint hoac dinh danh. Chi TEN loai loi."""
        class KhoHong:
            def __getattr__(self, ten):
                def no(*a, **k):
                    raise RuntimeError("appwrite tai project 6a749d bi tu choi")
                return no

        that = server_main.store
        server_main.store = KhoHong()
        try:
            r = self.client.get("/api/ready")
            self.assertNotIn("6a749d", r.text)
            self.assertNotIn("appwrite tai project", r.text)
        finally:
            server_main.store = that

    def test_ready_actually_consumes_the_storage_iterator(self):
        """
        `list_objects` tra ve ITERATOR. Khong tieu thu thi khong he goi mang, va
        phep kiem tra se bao "dat" ma chua kiem gi ca.
        """
        da_goi = {"n": 0}

        class KhoFileGia:
            def list_objects(self, prefix=""):
                da_goi["n"] += 1
                raise RuntimeError("phai no ra khi duoc tieu thu")
                yield  # pragma: no cover

        that = server_main.storage
        server_main.storage = KhoFileGia()
        try:
            r = self.client.get("/api/ready")
            self.assertEqual(r.status_code, 503,
                             "iterator phai duoc tieu thu, khong chi tao ra")
        finally:
            server_main.storage = that


if __name__ == "__main__":
    unittest.main()
