"""AppwriteQuizStore tren fake HTTP: ownership query, phan trang, permissions,
loi ha tang, va gioi han dong thoi. Bo test authority HTTP cung chay lai tren
adapter nay. Parity voi Appwrite hosted CHUA duoc xac minh."""

from __future__ import annotations

import unittest
import uuid

import httpx

from server.quiz import appwrite_store as aw
from server.quiz.contracts import DraftCreateRequest, DraftUpdateRequest, PublishRequest, SubmitRequest
from server.quiz.service import QuizError, QuizService
from server.quiz.store import RevisionConflict, StoreUnavailable
from server.tests import test_quiz_api as api_suite
from server.tests.quiz_appwrite_fake import FakeAppwrite
from server.tests.quiz_support import Clock, auth, make_env, opt, question


def _req(n: int, theme: str = "neon-tactics") -> DraftCreateRequest:
    return DraftCreateRequest.model_validate({"title": f"Quiz {n}", "theme_id": theme,
                                              "questions": [question(n)]})


class AppwriteCase(unittest.TestCase):
    def setUp(self):
        self.fake = FakeAppwrite()
        self.store = self.fake.store()
        self.clock = Clock()
        self.svc = QuizService(self.store, clock=self.clock)


class TestOwnershipAndPagination(AppwriteCase):
    def test_list_queries_are_owner_scoped_and_paginated(self):
        self.fake.max_page = 100
        for i in range(7):
            self.svc.create_draft("alice", _req(i + 1))
            self.clock.advance(seconds=1)
        self.svc.create_draft("mallory", _req(99))
        page1 = self.svc.list_drafts("alice", limit=3, offset=0)
        page3 = self.svc.list_drafts("alice", limit=3, offset=6)
        self.assertEqual((page1.total, len(page1.items), page1.next_offset), (7, 3, 3))
        self.assertEqual((len(page3.items), page3.next_offset), (1, None))
        self.assertEqual(page1.items[0].title, "Quiz 7")  # newest first
        lists = self.fake.requests("GET", aw.COL_DRAFTS)
        lists = [r for r in lists if r.doc_id is None]
        for r in lists:
            self.assertIn({"method": "equal", "attribute": "owner_user_id", "values": ["alice"]}, r.queries)
            self.assertIn({"method": "limit", "values": [3]}, r.queries)
        self.assertEqual([q for q in lists[1].queries if q["method"] == "offset"],
                         [{"method": "offset", "values": [6]}])

    def test_list_all_pages_through_large_result_sets(self):
        self.fake.max_page = 100
        from server.quiz.entitlements import grant_pro
        for i in range(230):
            grant_pro(self.store, user_id="alice", actor="qa", reason="paging", now=self.clock())
        self.assertEqual(len(self.store.list_grants("alice")), 230)
        offsets = [q["values"][0] for r in self.fake.requests("GET", aw.COL_GRANTS)
                   for q in r.queries if q["method"] == "offset"]
        self.assertEqual(offsets, [0, 100, 200])

    def test_cross_user_access_is_not_found(self):
        d = self.svc.create_draft("alice", _req(1))
        with self.assertRaises(QuizError) as ctx:
            self.svc.get_draft("mallory", d.draft_id)
        self.assertEqual(ctx.exception.status, 404)
        with self.assertRaises(QuizError):
            self.svc.publish("mallory", d.draft_id, PublishRequest(expected_revision=1))
        self.assertEqual(self.store.count_published("mallory"), 0)

    def test_server_side_owner_check_does_not_trust_query_results(self):
        self.svc.create_draft("mallory", _req(1))
        # Fake that ignores the owner filter (misconfigured index) must not leak rows.
        orig = self.fake._list
        self.fake._list = lambda docs, qs: orig(docs, [q for q in qs if q["method"] != "equal"])
        rows, _ = self.store.list_drafts("alice", limit=10, offset=0)
        self.assertEqual(rows, [])


class TestPermissions(AppwriteCase):
    def test_documents_are_server_only_except_owner_draft_read(self):
        d = self.svc.create_draft("alice", _req(1))
        pub = self.svc.publish("alice", d.draft_id, PublishRequest(expected_revision=1))
        view = self.svc.create_session("bob", pub.share_id)
        self.svc.submit("bob", view.session_id, SubmitRequest(
            request_id=str(uuid.uuid4()), question_id=view.question.id, selected_option_ids=[opt(1, 2)],
            expected_question_revision=1, expected_attempt=1))
        from server.quiz.entitlements import grant_pro
        grant_pro(self.store, user_id="alice", actor="qa", reason="perm test", now=self.clock())
        perms = {col: [doc["$permissions"] for doc in docs.values()] for col, docs in self.fake.cols.items()}
        self.assertEqual(perms[aw.COL_DRAFTS], [['read("user:alice")']])
        for col in (aw.COL_VERSION_KEYS, aw.COL_VERSIONS, aw.COL_PUBLISH_SLOTS, aw.COL_SHARES,
                    aw.COL_SESSIONS, aw.COL_SESSION_STATES, aw.COL_GRANTS):
            self.assertTrue(perms[col], col)
            self.assertTrue(all(p == [] for p in perms[col]), (col, perms[col]))
        for creates in self.fake.log:
            if creates.method == "POST":
                self.assertFalse(any("write" in p or "any" in p for p in creates.body["permissions"]))

    def test_answer_keys_live_only_in_private_collection(self):
        q = question(1, correct=[3])
        d = self.svc.create_draft("alice", DraftCreateRequest.model_validate(
            {"title": "t", "theme_id": "neon-tactics", "questions": [q]}))
        self.svc.publish("alice", d.draft_id, PublishRequest(expected_revision=1))
        public_doc = next(iter(self.fake.cols[aw.COL_VERSIONS].values()))
        self.assertNotIn("correct_option_ids", public_doc["content"])
        self.assertNotIn("Giải thích", public_doc["content"])
        key_doc = next(iter(self.fake.cols[aw.COL_VERSION_KEYS].values()))
        self.assertIn(opt(1, 3), key_doc["content"])


class TestErrors(AppwriteCase):
    def test_transport_and_5xx_errors_are_unavailable_not_not_found(self):
        d = self.svc.create_draft("alice", _req(1))

        def boom(method, col, did):
            raise httpx.ConnectError("refused")
        self.fake.hooks.append(boom)
        with self.assertRaises(StoreUnavailable):
            self.store.get_draft(d.draft_id)
        self.fake.hooks[:] = [lambda m, c, i: httpx.Response(503, json={"type": "general_server_error",
                                                                          "message": "secret internals"})]
        with self.assertRaises(StoreUnavailable) as ctx:
            self.store.get_draft(d.draft_id)
        self.assertNotIn("secret internals", str(ctx.exception))
        client, _, _, _ = make_env(store=self.store)
        r = client.get(f"/api/quiz/drafts/{d.draft_id}", headers=auth("alice"))
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "store_unavailable")

    def test_missing_collection_is_unavailable(self):
        self.fake.hooks.append(lambda m, c, i: httpx.Response(404, json={"type": "collection_not_found"}))
        with self.assertRaises(StoreUnavailable):
            self.store.get_draft(str(uuid.uuid4()))

    def test_unconfigured_settings_refused(self):
        class S:
            configured = False
        with self.assertRaises(StoreUnavailable):
            aw.AppwriteQuizStore(S())


class TestConcurrencyLimits(AppwriteCase):
    def _race_on_create(self, col, action):
        """Chay `action` CHEN vao ngay truoc POST dau tien toi `col` (sau khi ben kia da doc-kiem)."""
        fired = []

        def hook(method, c, did):
            if method == "POST" and c == col and not fired:
                fired.append(did)
                action()
            return None
        self.fake.hooks.append(hook)

    def test_draft_revision_claim_beats_read_check_race(self):
        d = self.svc.create_draft("alice", _req(1))
        other = QuizService(self.fake.store(), clock=self.clock)
        upd = lambda title: DraftUpdateRequest.model_validate(
            {"expected_revision": 1, "title": title, "theme_id": "neon-tactics", "questions": []})
        self._race_on_create(aw.COL_DRAFT_REVISIONS, lambda: other.update_draft("alice", d.draft_id, upd("B")))
        with self.assertRaises(QuizError) as ctx:
            self.svc.update_draft("alice", d.draft_id, upd("A"))
        self.assertEqual(ctx.exception.code, "revision_conflict")
        self.assertEqual(self.svc.get_draft("alice", d.draft_id).title, "B")

    def test_last_quota_slot_cannot_be_taken_twice(self):
        drafts = [self.svc.create_draft("alice", _req(i + 1)) for i in range(6)]
        for d in drafts[:4]:
            self.svc.publish("alice", d.draft_id, PublishRequest(expected_revision=1))
        other = QuizService(self.fake.store(), clock=self.clock)
        self._race_on_create(aw.COL_PUBLISH_SLOTS, lambda: other.publish(
            "alice", drafts[4].draft_id, PublishRequest(expected_revision=1)))
        with self.assertRaises(QuizError) as ctx:
            self.svc.publish("alice", drafts[5].draft_id, PublishRequest(expected_revision=1))
        self.assertEqual(ctx.exception.code, "quota_exceeded")
        self.assertEqual(self.store.count_published("alice"), 5)

    def test_session_state_claim_makes_duplicate_submit_count_once(self):
        d = self.svc.create_draft("alice", _req(1))
        pub = self.svc.publish("alice", d.draft_id, PublishRequest(expected_revision=1))
        view = self.svc.create_session("bob", pub.share_id)
        req = SubmitRequest(request_id=str(uuid.uuid4()), question_id=view.question.id,
                            selected_option_ids=[opt(1, 1)], expected_question_revision=1, expected_attempt=1)
        other = QuizService(self.fake.store(), clock=self.clock)
        results = []
        self._race_on_create(aw.COL_SESSION_STATES,
                             lambda: results.append(other.submit("bob", view.session_id, req)))
        results.append(self.svc.submit("bob", view.session_id, req))
        self.assertEqual(sorted(r.outcome for r in results), ["accepted", "duplicate"])
        final = self.store.get_session(view.session_id)
        self.assertEqual((final.score, len(final.receipts)), (1, 1))

    def test_crash_between_log_and_head_rolls_forward(self):
        d = self.svc.create_draft("alice", _req(1))
        self.fake.hooks.append(lambda m, c, i: httpx.Response(503) if (m, c) == ("PATCH", aw.COL_DRAFTS) else None)
        saved = self.svc.update_draft("alice", d.draft_id, DraftUpdateRequest.model_validate(
            {"expected_revision": 1, "title": "after crash", "theme_id": "neon-tactics", "questions": []}))
        self.assertEqual(saved.revision, 2)
        self.fake.hooks.clear()
        head = self.fake.cols[aw.COL_DRAFTS][d.draft_id]
        self.assertEqual(head["revision"], 1)                     # head is stale ...
        listed = self.svc.list_drafts("alice", limit=10, offset=0).items[0]
        self.assertEqual(listed.revision, 1)                      # KNOWN LIMIT: listing reads heads
        got = self.svc.get_draft("alice", d.draft_id)             # ... single read rolls forward
        self.assertEqual((got.revision, got.title), (2, "after crash"))
        self.assertEqual(self.fake.cols[aw.COL_DRAFTS][d.draft_id]["revision"], 2)  # head healed
        stale_writer = self.store.get_draft(d.draft_id).model_copy(update={"revision": 2})
        with self.assertRaises(RevisionConflict):
            self.store.replace_draft(stale_writer, expected_revision=1)

    def test_orphan_slot_counts_until_same_draft_republishes(self):
        """KNOWN LIMIT: tien trinh chet sau khi claim slot, truoc khi tao share."""
        d = self.svc.create_draft("alice", _req(1))
        self.fake.hooks.append(lambda m, c, i: httpx.Response(503) if (m, c) == ("POST", aw.COL_SHARES) else None)
        with self.assertRaises(StoreUnavailable):
            self.svc.publish("alice", d.draft_id, PublishRequest(expected_revision=1))
        self.fake.hooks.clear()
        self.assertEqual(self.store.count_published("alice"), 1)  # slot leaked for now
        pub = self.svc.publish("alice", d.draft_id, PublishRequest(expected_revision=1))
        self.assertEqual((pub.version, self.store.count_published("alice")), (1, 1))  # reused


class TestAppwriteRunsApiAuthoritySuite(api_suite.TestAuthAndOwnership):
    """Bo authority HTTP chay lai tren AppwriteQuizStore + fake."""

    def setUp(self):
        self.fake = FakeAppwrite()
        self.client, self.service, self.store, self.clock = make_env(store=self.fake.store())


class TestAppwriteRunsPublishSuite(api_suite.TestPublishAndShare):
    def setUp(self):
        self.fake = FakeAppwrite()
        self.client, self.service, self.store, self.clock = make_env(store=self.fake.store())


class TestAppwriteRunsSessionSuite(api_suite.TestSoloSession):
    def setUp(self):
        self.fake = FakeAppwrite()
        self.client, self.service, self.store, self.clock = make_env(store=self.fake.store())


class TestAppwriteRunsEntitlementSuite(api_suite.TestEntitlements):
    def setUp(self):
        self.fake = FakeAppwrite()
        self.client, self.service, self.store, self.clock = make_env(store=self.fake.store())


class TestAppwriteRunsDraftSuite(api_suite.TestDraftsAndRevisions):
    def setUp(self):
        self.fake = FakeAppwrite()
        self.client, self.service, self.store, self.clock = make_env(store=self.fake.store())


class TestAppwriteRunsCsvSuite(api_suite.TestCsv):
    def setUp(self):
        self.fake = FakeAppwrite()
        self.client, self.service, self.store, self.clock = make_env(store=self.fake.store())


if __name__ == "__main__":
    unittest.main()
