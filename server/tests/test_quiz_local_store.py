"""LocalQuizStore: ben vung qua restart, an toan khi tien trinh chet giua chung,
va nguyen tu khi submit/publish dong thoi (nhieu luong VA nhieu tien trinh)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

from server.quiz import local_store as local_store_mod
from server.quiz.contracts import DraftCreateRequest, PublishRequest, SubmitRequest
from server.quiz.local_store import LocalQuizStore
from server.quiz.service import QuizError, QuizService
from server.quiz.store import DraftRecord, StoreUnavailable
from server.tests.quiz_support import Clock, auth, make_env, opt, question

REPO_ROOT = Path(__file__).resolve().parents[2]


def _kill_tree(proc: subprocess.Popen) -> None:
    """Giet CUNG ca cay: tren Windows `python.exe` cua venv la launcher sinh tien trinh con."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        proc.kill()
    proc.wait(30)


def _draft_req(n: int) -> DraftCreateRequest:
    return DraftCreateRequest.model_validate(
        {"title": f"Quiz {n}", "theme_id": "neon-tactics", "questions": [question(n)]})


class TestRestartAndCrash(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="quiz-local-"))
        self.store = LocalQuizStore(self.root)
        self.clock = Clock()
        self.svc = QuizService(self.store, clock=self.clock)

    def test_namespace_is_own_directory(self):
        s = LocalQuizStore.under_var_dir(self.root / "var")
        s.create_draft(DraftRecord(draft_id=str(uuid.uuid4()), owner_user_id="u", title="t",
                                   theme_id="neon-tactics", questions=[], revision=1,
                                   created_at="2026-10-08T12:00:00.000000Z",
                                   updated_at="2026-10-08T12:00:00.000000Z"))
        self.assertEqual(sorted(p.name for p in (self.root / "var" / "quiz").iterdir()),
                         ["store.json", "store.lock"])

    def test_state_survives_restart(self):
        d = self.svc.create_draft("alice", _draft_req(1))
        pub = self.svc.publish("alice", d.draft_id, PublishRequest(expected_revision=1))
        view = self.svc.create_session("bob", pub.share_id)
        res = self.svc.submit("bob", view.session_id, SubmitRequest(
            request_id=str(uuid.uuid4()), question_id=view.question.id,
            selected_option_ids=[opt(1, 1)], expected_question_revision=1, expected_attempt=1))
        self.assertEqual(res.view.score, 1)

        restarted = QuizService(LocalQuizStore(self.root), clock=self.clock)
        self.assertEqual(restarted.get_draft("alice", d.draft_id).share_id, pub.share_id)
        self.assertEqual(restarted.get_share(pub.share_id).content_hash, pub.content_hash)
        again = restarted.get_session("bob", view.session_id)
        self.assertEqual((again.score, again.phase, again.state_revision), (1, "revealed", 2))

    def test_failed_replace_keeps_previous_state(self):
        d = self.svc.create_draft("alice", _draft_req(1))
        before = (self.root / "store.json").read_bytes()
        with mock.patch.object(local_store_mod.os, "replace", side_effect=OSError("disk gone")):
            with self.assertRaises(StoreUnavailable):
                self.svc.publish("alice", d.draft_id, PublishRequest(expected_revision=1))
        self.assertEqual((self.root / "store.json").read_bytes(), before)
        self.assertEqual(list(self.root.glob("store.json.tmp-*")), [])
        restarted = QuizService(LocalQuizStore(self.root), clock=self.clock)
        self.assertIsNone(restarted.get_draft("alice", d.draft_id).share_id)
        self.assertEqual(restarted.store.count_published("alice"), 0)

    def test_orphan_temp_file_from_dead_process_is_ignored_and_cleaned(self):
        self.svc.create_draft("alice", _draft_req(1))
        orphan = self.root / "store.json.tmp-99999-deadbeef"
        orphan.write_bytes(b'{"format_version": 1, "drafts": {"half-writ')
        reopened = LocalQuizStore(self.root)
        self.assertFalse(orphan.exists())
        self.assertEqual(reopened.list_drafts("alice", limit=10, offset=0)[1], 1)

    def test_corrupt_file_is_reported_not_silently_reset(self):
        (self.root / "store.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(StoreUnavailable):
            self.store.get_draft(str(uuid.uuid4()))
        client, _, _, _ = make_env(store=self.store)
        r = client.get("/api/quiz/drafts", headers=auth("alice"))
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "store_unavailable")
        self.assertEqual((self.root / "store.json").read_text(encoding="utf-8"), "{broken")

    def test_hard_kill_mid_write_leaves_loadable_state(self):
        script = textwrap.dedent(f"""
            import sys, uuid
            sys.path.insert(0, {str(REPO_ROOT)!r})
            from server.quiz.local_store import LocalQuizStore
            from server.quiz.service import QuizService
            from server.quiz.contracts import DraftCreateRequest, DraftUpdateRequest
            svc = QuizService(LocalQuizStore({str(self.root)!r}))
            q = lambda n: {{"id": str(uuid.UUID(int=n)), "kind": "boolean", "prompt": "P%d?" % n,
                  "options": [{{"id": str(uuid.UUID(int=n * 10 + 1)), "text": "A"}},
                              {{"id": str(uuid.UUID(int=n * 10 + 2)), "text": "B"}}],
                  "correct_option_ids": [str(uuid.UUID(int=n * 10 + 1))], "explanation": "x" * 900,
                  "difficulty": "easy", "time_limit_ms": None}}
            d = svc.create_draft("crash", DraftCreateRequest.model_validate(
                {{"title": "c", "theme_id": "neon-tactics", "questions": []}}))
            print("ready", flush=True)
            rev = 1
            while True:
                d = svc.update_draft("crash", d.draft_id, DraftUpdateRequest.model_validate(
                    {{"expected_revision": rev, "title": "c%d" % rev, "theme_id": "neon-tactics",
                      "questions": [q(i + 1) for i in range(rev % 150 + 1)]}}))
                rev = d.revision
        """)
        for round_no in range(3):
            proc = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, cwd=str(REPO_ROOT))
            try:
                line = proc.stdout.readline().strip()
                if line != b"ready":
                    self.fail(proc.stderr.read(4000).decode("utf-8", "replace"))
                time.sleep(0.4 + 0.15 * round_no)
            finally:
                _kill_tree(proc)
                proc.stdout.close()
                proc.stderr.close()
            reopened = LocalQuizStore(self.root)
            drafts, total = reopened.list_drafts("crash", limit=50, offset=0)
            self.assertEqual(total, round_no + 1)
            for d in drafts:
                self.assertGreaterEqual(d.revision, 1)
                self.assertEqual(len(d.questions), (d.revision - 1) % 150 + (1 if d.revision > 1 else 0))
            raw = json.loads((self.root / "store.json").read_text(encoding="utf-8"))
            self.assertEqual(raw["format_version"], 1)


class TestConcurrency(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="quiz-conc-"))
        self.clock = Clock()

    def _svc(self) -> QuizService:
        # Moi luong mot instance rieng tren CUNG thu muc => di qua khoa file, giong nhieu worker.
        return QuizService(LocalQuizStore(self.root), clock=self.clock)

    def _race(self, fn, n):
        barrier = threading.Barrier(n)
        results, errors = [None] * n, []

        def run(i):
            try:
                barrier.wait()
                results[i] = fn(i)
            except Exception as exc:  # noqa: BLE001
                results[i] = exc
        threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        return results

    def _published_session(self):
        svc = self._svc()
        d = svc.create_draft("alice", _draft_req(1))
        pub = svc.publish("alice", d.draft_id, PublishRequest(expected_revision=1))
        return svc, svc.create_session("bob", pub.share_id)

    def test_same_request_id_submitted_concurrently_counts_once(self):
        _, view = self._published_session()
        req = SubmitRequest(request_id=str(uuid.uuid4()), question_id=view.question.id,
                            selected_option_ids=[opt(1, 1)], expected_question_revision=1,
                            expected_attempt=1)
        results = self._race(lambda i: self._svc().submit("bob", view.session_id, req), 8)
        outcomes = sorted(r.outcome for r in results)
        self.assertEqual(outcomes, ["accepted"] + ["duplicate"] * 7)
        self.assertEqual(len({r.receipt.receipt_id for r in results}), 1)
        final = self._svc().store.get_session(view.session_id)
        self.assertEqual((final.score, len(final.receipts), final.state_revision), (1, 1, 2))

    def test_distinct_requests_for_same_attempt_only_one_wins(self):
        _, view = self._published_session()

        def go(i):
            return self._svc().submit("bob", view.session_id, SubmitRequest(
                request_id=str(uuid.uuid4()), question_id=view.question.id,
                selected_option_ids=[opt(1, 2 + i % 3)], expected_question_revision=1,
                expected_attempt=1))
        results = self._race(go, 8)
        accepted = [r for r in results if r.outcome == "accepted"]
        self.assertEqual(len(accepted), 1, [getattr(r, "reason", r) for r in results])
        self.assertTrue(all(r.reason == "attempt_mismatch" for r in results if r.outcome == "rejected"))
        final = self._svc().store.get_session(view.session_id)
        self.assertEqual((final.attempts_used, len(final.receipts)), (1, 1))

    def test_concurrent_publish_respects_free_quota(self):
        svc = self._svc()
        drafts = [svc.create_draft("alice", _draft_req(i + 1)) for i in range(9)]

        def go(i):
            try:
                return self._svc().publish("alice", drafts[i].draft_id, PublishRequest(expected_revision=1))
            except QuizError as exc:
                return exc.code
        results = self._race(go, 9)
        self.assertEqual(sum(1 for r in results if not isinstance(r, str)), 5)
        self.assertEqual(sorted(r for r in results if isinstance(r, str)), ["quota_exceeded"] * 4)
        self.assertEqual(self._svc().store.count_published("alice"), 5)
        self.assertEqual(len({r.share_id for r in results if not isinstance(r, str)}), 5)

    def test_concurrent_republish_of_same_draft_creates_one_version(self):
        svc = self._svc()
        d = svc.create_draft("alice", _draft_req(1))
        results = self._race(lambda i: self._svc().publish(
            "alice", d.draft_id, PublishRequest(expected_revision=1)), 6)
        self.assertEqual(sum(1 for r in results if not r.replayed), 1)
        self.assertEqual({(r.share_id, r.version) for r in results}, {(results[0].share_id, 1)})
        self.assertEqual(self._svc().store.count_published("alice"), 1)

    def test_concurrent_draft_updates_one_wins(self):
        svc = self._svc()
        d = svc.create_draft("alice", _draft_req(1))
        from server.quiz.contracts import DraftUpdateRequest

        def go(i):
            try:
                return self._svc().update_draft("alice", d.draft_id, DraftUpdateRequest.model_validate(
                    {"expected_revision": 1, "title": f"writer {i}", "theme_id": "neon-tactics",
                     "questions": []}))
            except QuizError as exc:
                return exc.code
        results = self._race(go, 6)
        self.assertEqual(sum(1 for r in results if not isinstance(r, str)), 1)
        self.assertEqual(sorted(r for r in results if isinstance(r, str)), ["revision_conflict"] * 5)

    def test_publish_quota_across_processes(self):
        svc = self._svc()
        ids = [svc.create_draft("alice", _draft_req(i + 1)).draft_id for i in range(9)]
        script = textwrap.dedent(f"""
            import sys, json
            sys.path.insert(0, {str(REPO_ROOT)!r})
            from server.quiz.local_store import LocalQuizStore
            from server.quiz.service import QuizService, QuizError
            from server.quiz.contracts import PublishRequest
            svc = QuizService(LocalQuizStore({str(self.root)!r}))
            out = []
            for did in sys.argv[1:]:
                try:
                    out.append(svc.publish("alice", did, PublishRequest(expected_revision=1)).share_id)
                except QuizError as exc:
                    out.append(exc.code)
            print(json.dumps(out))
        """)
        procs = [subprocess.Popen([sys.executable, "-c", script, *ids[i::3]], stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, cwd=str(REPO_ROOT)) for i in range(3)]
        outs = []
        for p in procs:
            stdout, stderr = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, stderr.decode("utf-8", "replace")[-2000:])
            outs += json.loads(stdout.decode().strip().splitlines()[-1])
        self.assertEqual(sum(1 for o in outs if o != "quota_exceeded"), 5)
        self.assertEqual(outs.count("quota_exceeded"), 4)
        self.assertEqual(LocalQuizStore(self.root).count_published("alice"), 5)


if __name__ == "__main__":
    unittest.main()
