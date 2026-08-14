"""
Claim job dich co that su nguyen tu khong — cung phuong phap voi
`test_claim_atomicity.py` (TTS), nhung tren `MockTranslationStore` truc tiep
(khong can di qua HTTP: tinh nguyen tu la mot tinh chat cua TANG KHO, khong
phai cua route).

Dong bo bang BARRIER chu khong dua vao timing: moi luong deu san sang truoc
khi bat ky luong nao duoc chay, nen khong co chuyen mot luong thang chi vi no
khoi dong som hon.
"""

from __future__ import annotations

import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from server.translation import TranslationJobStatus
from server.translation_domain import TranslationJob
from server.translation_service import TranslationService
from server.translation_store import MockTranslationStore

WORKERS = 10
REPEATS = 20


def iso(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc)
            + timedelta(seconds=offset_seconds)).isoformat(timespec="seconds")


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MockTranslationStore()

    def a_job(self, *, status: TranslationJobStatus,
             lease: Optional[str] = None, attempts: int = 1) -> TranslationJob:
        return self.store.create_job(TranslationJob(
            project_id="trp_x", owner_id="u1", status=status,
            lease_expires_at=lease or "",
            lease_owner="worker-khac" if lease else "",
            attempts=attempts, created_at=iso(-3600)))

    def race(self, job: TranslationJob, n: int = WORKERS):
        barrier = threading.Barrier(n)
        fences: List[Optional[int]] = [None] * n
        winners: List[str] = []
        lock = threading.Lock()

        def claim(i: int) -> None:
            worker = f"worker-{i}"
            barrier.wait()
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


class TestOnlyOneWinner(Base):
    def test_ten_workers_on_a_stale_running_job(self):
        fences, winners = self.race(
            self.a_job(status=TranslationJobStatus.TRANSLATING, lease=iso(-600)))
        self.assertEqual(len(winners), 1, f"phải đúng một: {fences}")
        self.assertEqual([f for f in fences if f is not None], [2],
                         "fence phải là số lần thử tiếp theo")

    def test_ten_workers_on_a_queued_job(self):
        fences, winners = self.race(
            self.a_job(status=TranslationJobStatus.QUEUED, lease=None, attempts=0))
        self.assertEqual(len(winners), 1, f"phải đúng một: {fences}")
        self.assertEqual([f for f in fences if f is not None], [1])

    def test_the_store_records_the_actual_winner(self):
        job = self.a_job(status=TranslationJobStatus.TRANSLATING, lease=iso(-600))
        _, winners = self.race(job)
        self.assertEqual(self.store.get_job(job.job_id).lease_owner, winners[0])

    def test_a_live_lease_is_never_stolen(self):
        job = self.a_job(status=TranslationJobStatus.TRANSLATING, lease=iso(600))
        fences, winners = self.race(job)
        self.assertEqual(winners, [], "lease còn hạn thì không ai được lấy")
        self.assertEqual(self.store.get_job(job.job_id).lease_owner, "worker-khac")

    def test_a_completed_job_is_never_claimed(self):
        job = self.a_job(status=TranslationJobStatus.COMPLETED)
        _, winners = self.race(job)
        self.assertEqual(winners, [])

    def test_a_failed_job_is_never_claimed(self):
        job = self.a_job(status=TranslationJobStatus.FAILED)
        _, winners = self.race(job)
        self.assertEqual(winners, [])

    def test_a_cancelled_job_is_never_claimed(self):
        job = self.a_job(status=TranslationJobStatus.CANCELLED)
        _, winners = self.race(job)
        self.assertEqual(winners, [])

    def test_losing_is_a_normal_result_not_an_exception(self):
        job = self.a_job(status=TranslationJobStatus.TRANSLATING, lease=iso(-600))
        self.assertIsNotNone(self.store.claim_job(job, "w1", iso(300)))
        self.assertIsNone(self.store.claim_job(job, "w2", iso(300)))

    def test_all_six_non_terminal_statuses_are_claimable_when_stale(self):
        """Khac TTS (chi pending/running): dich co 6 trang thai chua ket
        thuc. Job mat lease o BAT KY trang thai nao trong so do van phai
        nhan lai duoc."""
        from server.translation_service import NON_TERMINAL_STATUSES

        for trang_thai in NON_TERMINAL_STATUSES:
            with self.subTest(trang_thai=trang_thai.value):
                self.store = MockTranslationStore()
                job = self.a_job(status=trang_thai, lease=iso(-600))
                fence = self.store.claim_job(job, "w1", iso(300))
                self.assertIsNotNone(fence, trang_thai.value)


class TestRaceHoldsOverRepeats(Base):
    """Thắng một lần là may. Lặp lại 20 lần mới nói lên điều gì."""

    def test_stale_running_job_over_twenty_repeats(self):
        for lan in range(REPEATS):
            with self.subTest(lan=lan):
                self.store = MockTranslationStore()
                fences, winners = self.race(self.a_job(
                    status=TranslationJobStatus.TRANSLATING, lease=iso(-600)))
                self.assertEqual(len(winners), 1, f"lần {lan}: {fences}")

    def test_queued_job_over_twenty_repeats(self):
        for lan in range(REPEATS):
            with self.subTest(lan=lan):
                self.store = MockTranslationStore()
                fences, winners = self.race(self.a_job(
                    status=TranslationJobStatus.QUEUED, lease=None, attempts=0))
                self.assertEqual(len(winners), 1, f"lần {lan}: {fences}")


class TestFencingBlocksTheOldWorker(Base):
    def two_generations(self):
        """Hai 'thế hệ' worker: A claim trước, mất lease, B claim lại."""
        job = self.a_job(status=TranslationJobStatus.TRANSLATING, lease=iso(-600))
        fence_a = self.store.claim_job(job, "worker-a", iso(-1))  # het han ngay
        fence_b = self.store.claim_job(job, "worker-b", iso(300))
        return job, fence_a, fence_b

    def test_the_old_worker_cannot_renew_the_lease(self):
        job, fence_a, fence_b = self.two_generations()
        self.assertFalse(
            self.store.renew_lease(job.job_id, fence_a, "worker-a", iso(300)))

    def test_the_old_worker_cannot_save_progress(self):
        job, fence_a, fence_b = self.two_generations()
        self.assertFalse(self.store.save_progress(
            job.job_id, fence_a, "worker-a", current_chapter=99))

    def test_the_old_worker_cannot_complete_the_job(self):
        job, fence_a, fence_b = self.two_generations()
        job.status = TranslationJobStatus.COMPLETED
        self.assertFalse(
            self.store.save_job_fenced(job, fence_a, "worker-a"))

    def test_the_current_worker_can_write(self):
        job, fence_a, fence_b = self.two_generations()
        self.assertTrue(
            self.store.renew_lease(job.job_id, fence_b, "worker-b", iso(300)))

    def test_the_right_fence_with_the_wrong_worker_is_refused(self):
        job, fence_a, fence_b = self.two_generations()
        self.assertFalse(
            self.store.renew_lease(job.job_id, fence_b, "worker-a", iso(300)))


class RecoverStaleJobsTest(unittest.TestCase):
    """
    `TranslationService.recover_stale_jobs` — cung ly do ton tai voi
    `main.recover_stale_jobs` (TTS): mot worker chet giua chung, worker khac
    (hoac vong quet dinh ky cua chinh no) phai nhan lai job MA KHONG dot mat
    `attempts` cua job dang chay binh thuong o noi khac.
    """

    def setUp(self) -> None:
        from server.adapters import MockMetadataStore

        self.store = MockTranslationStore()
        self.novels = MockMetadataStore()
        self.svc = TranslationService(self.store, self.novels)

    def a_stale_job(self, *, attempts: int = 1) -> TranslationJob:
        return self.store.create_job(TranslationJob(
            project_id="trp_x", owner_id="u1",
            status=TranslationJobStatus.TRANSLATING,
            lease_expires_at=iso(-600), lease_owner="worker-da-chet",
            attempts=attempts, created_at=iso(-3600)))

    def test_a_process_that_cannot_run_jobs_claims_nothing(self):
        self.svc.stop_accepting_new_jobs()
        job = self.a_stale_job()
        bao_cao = self.svc.recover_stale_jobs()
        self.assertEqual(bao_cao.get("khong_duoc_phep_chay"), 1)
        self.assertEqual(bao_cao["da_quet"], 0)
        sau = self.store.get_job(job.job_id)
        self.assertEqual(sau.attempts, 1, "không được đốt thêm lần thử nào")
        self.assertEqual(sau.lease_owner, "worker-da-chet")

    def test_repeated_sweeps_never_burn_attempts_when_cannot_run(self):
        self.svc.stop_accepting_new_jobs()
        job = self.a_stale_job()
        for _ in range(5):
            self.svc.recover_stale_jobs()
        self.assertEqual(self.store.get_job(job.job_id).attempts, 1)

    def test_a_process_that_can_run_jobs_does_claim(self):
        job = self.a_stale_job()
        bao_cao = self.svc.recover_stale_jobs()
        self.assertEqual(bao_cao["chay_lai"], 1)
        with self.svc._job_lock:
            luong = self.svc._job_threads.get(job.job_id)
        if luong is not None:
            luong.join(timeout=5)
        self.assertGreater(self.store.get_job(job.job_id).attempts, 1)

    def test_job_qua_han_thu_thanh_failed_khong_xoay_vong_mai(self):
        from server.translation_service import TRANSLATION_JOB_MAX_ATTEMPTS

        job = self.a_stale_job(attempts=TRANSLATION_JOB_MAX_ATTEMPTS)
        bao_cao = self.svc.recover_stale_jobs()
        self.assertEqual(bao_cao["het_luot_thu"], 1)
        sau = self.store.get_job(job.job_id)
        self.assertEqual(sau.status, TranslationJobStatus.FAILED)
        self.assertTrue(sau.error)

    def test_job_con_lease_song_khong_bi_dong_cham(self):
        job = self.store.create_job(TranslationJob(
            project_id="trp_x", owner_id="u1",
            status=TranslationJobStatus.TRANSLATING,
            lease_expires_at=iso(600), lease_owner="worker-con-song",
            attempts=1, created_at=iso(-3600)))
        bao_cao = self.svc.recover_stale_jobs()
        self.assertEqual(bao_cao["bo_qua_con_lease"], 1)
        self.assertEqual(bao_cao["chay_lai"], 0)
        self.assertEqual(self.store.get_job(job.job_id).lease_owner,
                         "worker-con-song")

    def test_job_queued_qua_moi_duoc_bo_qua_theo_nguong_tuoi(self):
        job = self.store.create_job(TranslationJob(
            project_id="trp_x", owner_id="u1",
            status=TranslationJobStatus.QUEUED, created_at=iso(0)))
        # Nguong mac dinh (TRANSLATION_JOB_LEASE_SECONDS) con rat xa — job vua
        # tao PHAI duoc bo qua, khong nhan ngay (co the thread inline dang lo).
        bao_cao = self.svc.recover_stale_jobs()
        self.assertEqual(bao_cao["bo_qua_con_moi"], 1)
        self.assertEqual(bao_cao["chay_lai"], 0)
        self.assertEqual(self.store.get_job(job.job_id).status,
                         TranslationJobStatus.QUEUED)

    def test_worker_rieng_truyen_nguong_0_nhan_job_queued_ngay(self):
        job = self.store.create_job(TranslationJob(
            project_id="trp_x", owner_id="u1",
            status=TranslationJobStatus.QUEUED, created_at=iso(0)))
        bao_cao = self.svc.recover_stale_jobs(pending_min_age_seconds=0)
        self.assertEqual(bao_cao["chay_lai"], 1)
        with self.svc._job_lock:
            luong = self.svc._job_threads.get(job.job_id)
        if luong is not None:
            luong.join(timeout=5)


class _ChanMaiChoToiKhiTha(object):
    """Provider chan MOI lan goi cho toi khi test tha ra — dung de giu mot
    job "dang chay" that su, chiem mot cho trong tran dong thoi, cho toi khi
    test muon no xong."""

    name = "chan-mai"

    def __init__(self):
        self.duoc_tha = threading.Event()

    def translate_segment(self, text, *, context):
        self.duoc_tha.wait(timeout=10)
        return "đã dịch"


class ConcurrencyTest(unittest.TestCase):
    """Part K: "configurable concurrency" — so job chay dong thoi TRONG MOT
    tien trinh phai co tran, va tran do doc duoc tu cau hinh."""

    def setUp(self) -> None:
        from server.adapters import MockMetadataStore

        self.store = MockTranslationStore()
        self.novels = MockMetadataStore()

    def test_tran_dong_thoi_doc_tu_tham_so(self):
        svc = TranslationService(self.store, self.novels, max_concurrent_jobs=7)
        self.assertEqual(svc._max_concurrent_jobs, 7)

    def test_tran_dong_thoi_mac_dinh_doc_tu_env(self):
        import os

        cu = os.environ.get("FAS_TRANSLATION_MAX_CONCURRENT_JOBS")
        os.environ["FAS_TRANSLATION_MAX_CONCURRENT_JOBS"] = "5"
        try:
            svc = TranslationService(self.store, self.novels)
            self.assertEqual(svc._max_concurrent_jobs, 5)
        finally:
            if cu is None:
                os.environ.pop("FAS_TRANSLATION_MAX_CONCURRENT_JOBS", None)
            else:
                os.environ["FAS_TRANSLATION_MAX_CONCURRENT_JOBS"] = cu

    def test_qua_tran_thi_job_moi_nam_cho_khong_bi_chay_ngay(self):
        from server.adapters import MockIdentityAdapter

        identity = MockIdentityAdapter()
        an = identity.register("an@vidu.vn", "MatKhau123", "An")
        provider = _ChanMaiChoToiKhiTha()
        svc = TranslationService(self.store, self.novels, provider=provider,
                                 max_concurrent_jobs=2)

        projects = [svc.create_project(an.user_id, title=f"p{i}",
                                       source_text="một câu.",
                                       quality_mode="nhanh")
                   for i in range(3)]
        jobs = [svc.create_job(p.project_id, an.user_id) for p in projects]

        # Cho toi khi CA HAI cho da bi chiem (thread nen that su dang goi
        # provider bi chan) — khong doan mo bang sleep co dinh.
        han = time.time() + 5
        while time.time() < han and svc.job_threads_alive() < 2:
            time.sleep(0.005)
        self.assertEqual(svc.job_threads_alive(), 2,
                         "phải đúng 2 job chạy đồng thời, không hơn")

        # Job thu ba PHAI con nam `queued` — khong co cho, khong bi chay.
        job3_hien_tai = svc.get_job(jobs[2].job_id, an.user_id)
        self.assertEqual(job3_hien_tai.status, TranslationJobStatus.QUEUED)

        provider.duoc_tha.set()
        # Job0/job1 gio hoan tat, giai phong cho. Trong he thong that, vong
        # quet dinh ky (`start_translation_job_sweeper`/worker rieng) se tu
        # nhan job3 khi co cho — o day goi thang de kiem dung DIEU DO, khong
        # phai hanh vi cua mot vong lap nen rieng.
        self._cho_xong(svc, jobs[0].job_id, an.user_id)
        self._cho_xong(svc, jobs[1].job_id, an.user_id)
        bao_cao = svc.recover_stale_jobs(pending_min_age_seconds=0)
        self.assertEqual(bao_cao["chay_lai"], 1,
                         "job3 phải được nhận ngay khi có chỗ trống")
        for j in jobs:
            job_cuoi = self._cho_xong(svc, j.job_id, an.user_id)
            self.assertEqual(job_cuoi.status, TranslationJobStatus.COMPLETED)

    def _cho_xong(self, svc, job_id, owner_id, timeout=5.0):
        han = time.time() + timeout
        while time.time() < han:
            job = svc.get_job(job_id, owner_id)
            if job.status in (TranslationJobStatus.COMPLETED,
                             TranslationJobStatus.FAILED,
                             TranslationJobStatus.CANCELLED):
                return job
            time.sleep(0.01)
        raise AssertionError(f"job {job_id} không xong sau {timeout}s")


if __name__ == "__main__":
    unittest.main(verbosity=2)
