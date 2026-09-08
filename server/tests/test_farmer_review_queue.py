"""Ranh gioi danh gia HYBRID — hang doi Appwrite + may danh gia o xa.

Kien truc, va tung phan cua no la mot yeu cau an ninh:

    AWS farmer  --ghi PENDING-->  Appwrite  <--poll RA NGOAI--  laptop
                                                                (Router V4 +
                                                                 pool Antigravity)

Bon bat bien duoc dong cung o day:

1. **Khong bao gio tu duyet.** May danh gia bien mat -> cong viec o lai
   PENDING mai mai, va farmer khong san xuat gi.
2. **Khong roi ve am tham sang Gemini.** Mot ban roi ve tu dong sang mot han
   muc CO TRA PHI la dung thu nguoi van hanh da noi khong.
3. **Farmer khong biet tai khoan nao.** Chi ten NHA CUNG CAP di vao ket qua.
4. **Xep lai la no-op.** `job_id` tat dinh nen mot lan chay lai khong tao
   cong viec thu hai.
"""
from __future__ import annotations

import json
import unittest
from unittest import mock

from server.domain import ReviewJob
from server.farmer.review import ReviewUnavailable
from server.farmer.review_provider import (
    ENV_PROVIDER, PROVIDER_GEMINI, PROVIDER_QUEUE, QueuedReviewProvider,
    ReviewPending, ReviewRequest, build_review_provider,
)


class _Store:
    def __init__(self, jobs=None):
        self.jobs = dict(jobs or {})
        self.created = []
        self.updates = []

    def get_review_job(self, job_id):
        if job_id not in self.jobs:
            raise KeyError(job_id)
        return self.jobs[job_id]

    def create_review_job_once(self, job):
        self.created.append(job)
        if job.job_id in self.jobs:
            return self.jobs[job.job_id], False
        self.jobs[job.job_id] = job
        return job, True

    def update_review_job(self, job_id, **fields):
        self.updates.append((job_id, dict(fields)))
        job = self.jobs[job_id]
        for k, v in fields.items():
            if hasattr(job, k):
                setattr(job, k, v)
        return job


def _provider(store, *, verdict_bytes=b""):
    uploaded = {}

    def up(key, data):
        uploaded[key] = data

    def down(key):
        if not verdict_bytes:
            raise KeyError(key)
        return verdict_bytes

    p = QueuedReviewProvider(
        store, upload_sample=up, download_verdict=down,
        sample_key_for=lambda w: f"review/samples/{w}.json",
        verdict_key_for=lambda w: f"review/verdicts/{w}.json")
    p._uploaded = uploaded            # cho bai test soi
    return p


def _req(work_id="w_1"):
    return ReviewRequest(work_id=work_id, bucket="works/fanfic-tts",
                         lane="text", title="T", body="noi dung " * 40,
                         source_url="https://e.com/a")


class NeverSelfApprovesTest(unittest.TestCase):
    def test_a_new_work_is_queued_and_raises_pending(self):
        store = _Store()
        p = _provider(store)
        with self.assertRaises(ReviewPending):
            p.review(_req())
        self.assertEqual(len(store.created), 1)
        self.assertEqual(store.created[0].status, "PENDING")

    def test_an_already_queued_work_stays_pending_forever(self):
        """May danh gia tat = cho mai mai. Do la hanh vi DUNG."""
        store = _Store({"w_1": ReviewJob(job_id="w_1", work_id="w_1",
                                         bucket="b", lane="text",
                                         status="PENDING")})
        p = _provider(store)
        for _ in range(5):
            with self.assertRaises(ReviewPending):
                p.review(_req())
        # Khong tao them cong viec nao, va khong bao gio tra ve mot ban an.
        self.assertEqual(store.created, [])

    def test_a_claimed_job_is_still_pending_not_approved(self):
        store = _Store({"w_1": ReviewJob(job_id="w_1", work_id="w_1",
                                         bucket="b", lane="text",
                                         status="CLAIMED")})
        with self.assertRaises(ReviewPending):
            _provider(store).review(_req())

    def test_a_failed_review_is_unavailable_not_an_approval(self):
        store = _Store({"w_1": ReviewJob(job_id="w_1", work_id="w_1",
                                         bucket="b", lane="text",
                                         status="FAILED",
                                         last_error="agy chet")})
        with self.assertRaises(ReviewUnavailable):
            _provider(store).review(_req())


class VerdictReadTest(unittest.TestCase):
    def _done_store(self):
        return _Store({"w_1": ReviewJob(
            job_id="w_1", work_id="w_1", bucket="b", lane="text",
            status="DONE", verdict_key="review/verdicts/w_1.json",
            decision="approve", score=88,
            reviewed_by_provider="antigravity")})

    def test_a_completed_verdict_is_read_back_in_full(self):
        verdict = json.dumps({
            "decision": "approve", "score": 88, "reasons": ["mach lac"],
            "canonical_title": "Tieu de chuan", "display_title": "Hien thi",
            "fandom": "F", "category": "C", "author": "A", "language": "vi",
            "content_type": "fanfic", "completeness": "complete",
            "tags": ["a", "b"], "provider": "antigravity",
        }).encode("utf-8")

        v = _provider(self._done_store(), verdict_bytes=verdict).review(_req())

        self.assertTrue(v.approved)
        self.assertEqual(v.decision, "approve")
        self.assertEqual(v.score, 88)
        self.assertEqual(v.canonical_title, "Tieu de chuan")
        self.assertEqual(v.content_type, "fanfic")
        self.assertEqual(v.tags, ("a", "b"))

    def test_the_result_names_a_provider_never_an_account(self):
        """Farmer khong duoc biet tai khoan Antigravity nao da chay — do la
        viec cua Router V4."""
        verdict = json.dumps({"decision": "approve", "score": 90,
                              "provider": "antigravity"}).encode("utf-8")
        v = _provider(self._done_store(), verdict_bytes=verdict).review(_req())
        self.assertEqual(v.model, "antigravity")
        for xau in ("acc1", "acc2", "account", "saved_profiles"):
            self.assertNotIn(xau, json.dumps(v.as_dict()))

    def test_an_unreadable_verdict_is_unavailable_not_an_approval(self):
        store = self._done_store()
        p = _provider(store, verdict_bytes=b"khong-phai-json")
        with self.assertRaises(ReviewUnavailable):
            p.review(_req())


class NoSilentGeminiFallbackTest(unittest.TestCase):
    def test_default_provider_is_the_queue_not_gemini(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            os_env = dict()
            with mock.patch.dict("os.environ", os_env, clear=False):
                p = build_review_provider(
                    _Store(), upload_sample=lambda *a: None,
                    download_verdict=lambda k: b"",
                    sample_key_for=lambda w: w, verdict_key_for=lambda w: w)
        self.assertIsInstance(p, QueuedReviewProvider)

    def test_a_queue_failure_never_becomes_a_gemini_call(self):
        """Khong tai duoc mau -> ReviewUnavailable. KHONG mot duong nao di
        sang mot han muc co tra phi."""
        def up_hong(key, data):
            raise RuntimeError("R2 chet")

        p = QueuedReviewProvider(
            _Store(), upload_sample=up_hong, download_verdict=lambda k: b"",
            sample_key_for=lambda w: w, verdict_key_for=lambda w: w)
        with self.assertRaises(ReviewUnavailable):
            p.review(_req())

    def test_an_unknown_provider_name_is_refused_not_guessed(self):
        with mock.patch.dict("os.environ", {ENV_PROVIDER: "co-le-la-gemini"}):
            with self.assertRaises(ReviewUnavailable):
                build_review_provider(_Store())

    def test_gemini_requires_an_explicit_opt_in(self):
        """Bat duoc, nhung phai TUONG MINH — va van nem neu thieu khoa thay vi
        im lang bo qua cong danh gia."""
        with mock.patch.dict("os.environ", {ENV_PROVIDER: PROVIDER_GEMINI},
                             clear=False):
            for bien in ("FARMER_GEMINI_API_KEY", "GEMINI_API_KEY"):
                os_patch = {ENV_PROVIDER: PROVIDER_GEMINI, bien: ""}
                with mock.patch.dict("os.environ", os_patch, clear=False):
                    pass
            with mock.patch("server.farmer.review.build_reviewer",
                            side_effect=ReviewUnavailable("thieu khoa")):
                with self.assertRaises(ReviewUnavailable):
                    build_review_provider(_Store())


class DeterministicEnqueueTest(unittest.TestCase):
    def test_requeueing_the_same_work_is_a_no_op(self):
        store = _Store()
        p = _provider(store)
        with self.assertRaises(ReviewPending):
            p.review(_req("w_same"))
        with self.assertRaises(ReviewPending):
            p.review(_req("w_same"))
        # Lan hai doc thay job da co -> khong goi create nua.
        self.assertEqual(len(store.created), 1)

    def test_the_sample_goes_to_r2_not_into_the_queue_row(self):
        """Mot chuong dai vuot gioi han chuoi cua Appwrite, va nhet no vao
        mot cot se lam moi truy van hang doi keo ca noi dung ve."""
        store = _Store()
        p = _provider(store)
        with self.assertRaises(ReviewPending):
            p.review(_req("w_2"))
        self.assertTrue(p._uploaded, "mau phai duoc tai len R2")
        job = store.created[0]
        self.assertTrue(job.sample_key)
        self.assertNotIn("noi dung", json.dumps(job.to_dict()))


class MetricsTest(unittest.TestCase):
    def test_metrics_are_account_independent(self):
        store = _Store()
        p = _provider(store)
        with self.assertRaises(ReviewPending):
            p.review(_req())
        m = p.metrics()
        self.assertEqual(m["provider"], "queue_antigravity")
        self.assertEqual(m["enqueued"], 1)
        for xau in ("acc", "account", "profile"):
            self.assertNotIn(xau, json.dumps(m).replace("queue_antigravity", ""))


if __name__ == "__main__":
    unittest.main()
