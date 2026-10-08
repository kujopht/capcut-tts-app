"""Authority cua `/api/quiz/*` qua HTTP that (TestClient) tren LocalQuizStore.

Bao phu: dang nhap, cross-user 404, khong nhan diem/owner tu client, khong lo
dap an truoc reveal, phat lai idempotent, xung dot revision, luat Tactical
Summon, het gio, quota/theme Free vs Pro, CSV tat-ca-hoac-khong, publish bat bien.
"""

from __future__ import annotations

import json
import unittest
import uuid

from server.quiz.entitlements import revoke_grant
from server.tests.quiz_support import (
    auth, create_draft, give_pro, make_env, opt, publish, question, walk_keys,
)

SECRET_FIELDS = {"correct_option_ids", "explanation", "keys", "owner_user_id", "difficulty"}


def _rid() -> str:
    return str(uuid.uuid4())


class QuizApiBase(unittest.TestCase):
    def setUp(self):
        self.client, self.service, self.store, self.clock = make_env()

    def published(self, user="alice", questions=None, theme="neon-tactics"):
        draft = create_draft(self.client, user, questions or [question(1)], theme_id=theme)
        r = publish(self.client, user, draft)
        self.assertEqual(r.status_code, 201, r.text)
        return draft, r.json()

    def start(self, share_id, user="bob"):
        r = self.client.post(f"/api/quiz/shares/{share_id}/sessions", headers=auth(user))
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def submit(self, view, selected, *, user="bob", request_id=None, attempt=None, qrev=None,
               question_id=None):
        body = {"request_id": request_id or _rid(),
                "question_id": question_id or view["question"]["id"],
                "selected_option_ids": selected,
                "expected_question_revision": qrev or view["question_revision"],
                "expected_attempt": attempt or view["attempts_used"] + 1}
        r = self.client.post(f"/api/quiz/sessions/{view['session_id']}/submit",
                             headers=auth(user), json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def advance(self, view, user="bob"):
        r = self.client.post(f"/api/quiz/sessions/{view['session_id']}/advance", headers=auth(user),
                             json={"expected_question_revision": view["question_revision"]})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()


class TestAuthAndOwnership(QuizApiBase):
    def test_creator_routes_require_auth(self):
        for method, path in [("get", "/api/quiz/drafts"), ("post", "/api/quiz/drafts"),
                             ("get", "/api/quiz/me/entitlements")]:
            r = getattr(self.client, method)(path)
            self.assertEqual(r.status_code, 401)
            self.assertEqual(r.json()["detail"]["code"], "auth_required")

    def test_identity_outage_is_503_not_401(self):
        r = self.client.get("/api/quiz/drafts", headers={"Authorization": "Bearer tok-outage"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "identity_unavailable")

    def test_cross_user_draft_access_is_404_everywhere(self):
        draft = create_draft(self.client, "alice", [question(1)])
        did = draft["draft_id"]
        mallory = auth("mallory")
        calls = [
            self.client.get(f"/api/quiz/drafts/{did}", headers=mallory),
            self.client.put(f"/api/quiz/drafts/{did}", headers=mallory,
                            json={"expected_revision": 1, "title": "x", "theme_id": "neon-tactics",
                                  "questions": []}),
            self.client.delete(f"/api/quiz/drafts/{did}?expected_revision=1", headers=mallory),
            self.client.post(f"/api/quiz/drafts/{did}/publish", headers=mallory,
                             json={"expected_revision": 1}),
            self.client.post(f"/api/quiz/drafts/{did}/csv/validate", headers=mallory,
                             json={"csv": "kind,prompt,options,correct\n", "strategy": "append"}),
            self.client.post(f"/api/quiz/drafts/{did}/csv/commit", headers=mallory,
                             json={"csv": "kind,prompt,options,correct\n", "strategy": "append",
                                   "expected_revision": 1}),
        ]
        for r in calls:
            self.assertEqual(r.status_code, 404, r.text)
            self.assertEqual(r.json()["detail"]["code"], "draft_not_found")
        listing = self.client.get("/api/quiz/drafts", headers=mallory).json()
        self.assertEqual(listing["items"], [])
        # alice's draft is untouched
        again = self.client.get(f"/api/quiz/drafts/{did}", headers=auth("alice")).json()
        self.assertEqual(again["revision"], 1)

    def test_cross_user_session_access_is_404(self):
        _, pub = self.published()
        view = self.start(pub["share_id"], "bob")
        sid = view["session_id"]
        r = self.client.get(f"/api/quiz/sessions/{sid}", headers=auth("mallory"))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "session_not_found")
        r = self.client.post(f"/api/quiz/sessions/{sid}/submit", headers=auth("mallory"),
                             json={"request_id": _rid(), "question_id": view["question"]["id"],
                                   "selected_option_ids": [opt(1, 1)],
                                   "expected_question_revision": 1, "expected_attempt": 1})
        self.assertEqual(r.status_code, 404)
        # even the quiz owner cannot read a participant's session
        r = self.client.get(f"/api/quiz/sessions/{sid}", headers=auth("alice"))
        self.assertEqual(r.status_code, 404)

    def test_malformed_ids_are_404_not_500(self):
        r = self.client.get("/api/quiz/drafts/not-a-uuid", headers=auth("alice"))
        self.assertEqual(r.status_code, 404)
        r = self.client.get("/api/quiz/shares/../../etc")
        self.assertIn(r.status_code, (404,))

    def test_client_cannot_supply_owner_or_score(self):
        r = self.client.post("/api/quiz/drafts", headers=auth("alice"),
                             json={"title": "t", "theme_id": "neon-tactics", "questions": [],
                                   "owner_user_id": "alice"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["code"], "invalid_request")
        _, pub = self.published()
        view = self.start(pub["share_id"])
        r = self.client.post(f"/api/quiz/sessions/{view['session_id']}/submit", headers=auth("bob"),
                             json={"request_id": _rid(), "question_id": view["question"]["id"],
                                   "selected_option_ids": [opt(1, 1)],
                                   "expected_question_revision": 1, "expected_attempt": 1,
                                   "score": 99, "correct": True})
        self.assertEqual(r.status_code, 422)
        fresh = self.client.get(f"/api/quiz/sessions/{view['session_id']}", headers=auth("bob")).json()
        self.assertEqual(fresh["score"], 0)
        self.assertEqual(fresh["state_revision"], 1)

    def test_strict_types_and_bad_json(self):
        draft = create_draft(self.client, "alice", [question(1)])
        r = self.client.post(f"/api/quiz/drafts/{draft['draft_id']}/publish", headers=auth("alice"),
                             json={"expected_revision": "1"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["field_errors"][0]["loc"], ["expected_revision"])
        r = self.client.post(f"/api/quiz/drafts/{draft['draft_id']}/publish", headers=auth("alice"),
                             content=b"{not json", )
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["code"], "invalid_json")
        r = self.client.post("/api/quiz/drafts", headers=auth("alice"),
                             content=b"x" * (1_048_577))
        self.assertEqual(r.status_code, 413)


class TestDraftsAndRevisions(QuizApiBase):
    def test_crud_and_revision_conflict(self):
        draft = create_draft(self.client, "alice", [question(1)])
        self.assertEqual(draft["revision"], 1)
        self.assertEqual(draft["mode"], {"id": "tactical-summon", "version": 1})
        body = {"expected_revision": 1, "title": "Đổi tên", "theme_id": "neon-tactics",
                "questions": [question(1), question(2, "boolean")]}
        r = self.client.put(f"/api/quiz/drafts/{draft['draft_id']}", headers=auth("alice"), json=body)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["revision"], 2)
        stale = self.client.put(f"/api/quiz/drafts/{draft['draft_id']}", headers=auth("alice"), json=body)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["detail"]["code"], "revision_conflict")
        self.assertEqual(stale.json()["detail"]["current_revision"], 2)
        listing = self.client.get("/api/quiz/drafts?limit=1", headers=auth("alice")).json()
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["question_count"], 2)
        r = self.client.delete(f"/api/quiz/drafts/{draft['draft_id']}?expected_revision=1",
                               headers=auth("alice"))
        self.assertEqual(r.status_code, 409)
        r = self.client.delete(f"/api/quiz/drafts/{draft['draft_id']}?expected_revision=2",
                               headers=auth("alice"))
        self.assertEqual(r.status_code, 204)
        r = self.client.get(f"/api/quiz/drafts/{draft['draft_id']}", headers=auth("alice"))
        self.assertEqual(r.status_code, 404)

    def test_invalid_question_shapes_rejected(self):
        bad = [
            dict(question(1), kind="boolean"),                       # 4 options for boolean
            dict(question(1), correct_option_ids=[opt(1, 1), opt(1, 2)]),  # single with 2 keys
            dict(question(1), correct_option_ids=[opt(9, 9)]),        # key not an option
            dict(question(1), options=[{"id": opt(1, 1), "text": "a"}] * 2),  # dup option ids
            dict(question(1), prompt="   "),                           # blank
            dict(question(1), time_limit_ms=100),                      # too short
        ]
        for q in bad:
            r = self.client.post("/api/quiz/drafts", headers=auth("alice"),
                                 json={"title": "t", "theme_id": "neon-tactics", "questions": [q]})
            self.assertEqual(r.status_code, 422, q)
        dup = self.client.post("/api/quiz/drafts", headers=auth("alice"),
                               json={"title": "t", "theme_id": "neon-tactics",
                                     "questions": [question(1), question(1)]})
        self.assertEqual(dup.status_code, 422)

    def test_published_draft_cannot_be_deleted(self):
        draft, _ = self.published()
        r = self.client.delete(f"/api/quiz/drafts/{draft['draft_id']}?expected_revision=1",
                               headers=auth("alice"))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["code"], "draft_published")


class TestPublishAndShare(QuizApiBase):
    def test_share_snapshot_is_public_and_keyless(self):
        draft, pub = self.published(questions=[question(1), question(2, "multiple", correct=[1, 3])])
        self.assertEqual(pub["version"], 1)
        r = self.client.get(f"/api/quiz/shares/{pub['share_id']}")  # no auth
        self.assertEqual(r.status_code, 200)
        snap = r.json()
        self.assertEqual(snap["question_count"], 2)
        self.assertFalse(SECRET_FIELDS & set(walk_keys(snap)), snap)
        self.assertEqual(r.headers["cache-control"], "no-store")
        self.assertEqual(self.client.get("/api/quiz/shares/AAAAAAAAAAAAAAAA").status_code, 404)

    def test_publish_is_immutable_and_republish_versions(self):
        draft, pub = self.published(questions=[question(1)])
        v1 = self.client.get(f"/api/quiz/shares/{pub['share_id']}").json()
        session_v1 = self.start(pub["share_id"])
        # same revision again -> replay, no new version
        again = publish(self.client, "alice", draft)
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.json()["replayed"])
        self.assertEqual(again.json()["version"], 1)
        # edit the draft after publish: the published version must not change
        edited_q = dict(question(1), prompt="Câu hỏi ĐÃ SỬA?")
        r = self.client.put(f"/api/quiz/drafts/{draft['draft_id']}", headers=auth("alice"),
                            json={"expected_revision": 1, "title": "Quiz v2", "theme_id": "neon-tactics",
                                  "questions": [edited_q, question(2)]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(f"/api/quiz/shares/{pub['share_id']}").json(), v1)
        r2 = self.client.post(f"/api/quiz/drafts/{draft['draft_id']}/publish", headers=auth("alice"),
                              json={"expected_revision": 2})
        self.assertEqual(r2.status_code, 201)
        self.assertEqual((r2.json()["share_id"], r2.json()["version"]), (pub["share_id"], 2))
        v2 = self.client.get(f"/api/quiz/shares/{pub['share_id']}").json()
        self.assertEqual(v2["questions"][0]["prompt"], "Câu hỏi ĐÃ SỬA?")
        self.assertNotEqual(v2["content_hash"], v1["content_hash"])
        # version 1 is still stored byte-for-byte and the old session stays pinned to it
        stored_v1 = self.store.get_version(pub["share_id"], 1)
        self.assertEqual(stored_v1.public.model_dump(mode="json"), v1)
        old = self.client.get(f"/api/quiz/sessions/{session_v1['session_id']}", headers=auth("bob")).json()
        self.assertEqual(old["version"], 1)
        self.assertEqual(old["question"]["prompt"], v1["questions"][0]["prompt"])
        self.assertEqual(old["question_count"], 1)

    def test_publish_requires_current_revision_and_questions(self):
        draft = create_draft(self.client, "alice", [])
        r = publish(self.client, "alice", draft)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["code"], "draft_empty")
        draft = create_draft(self.client, "alice", [question(1)])
        r = self.client.post(f"/api/quiz/drafts/{draft['draft_id']}/publish", headers=auth("alice"),
                             json={"expected_revision": 7})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["current_revision"], 1)


class TestEntitlements(QuizApiBase):
    def test_free_quota_is_five(self):
        for i in range(5):
            self.published(questions=[question(i + 1)])
        summary = self.client.get("/api/quiz/me/entitlements", headers=auth("alice")).json()
        self.assertEqual(summary, {"plan": "free", "published_limit": 5, "published_used": 5,
                                   "themes": ["neon-tactics"], "pro_expires_at": None})
        draft = create_draft(self.client, "alice", [question(9)])
        r = publish(self.client, "alice", draft)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"]["code"], "quota_exceeded")
        self.assertEqual(r.json()["detail"]["limit"], 5)
        # republishing an already published quiz does not need a new slot
        items = self.client.get("/api/quiz/drafts?limit=50", headers=auth("alice")).json()["items"]
        first = next(d for d in items if d["share_id"] is not None)
        r = self.client.put(f"/api/quiz/drafts/{first['draft_id']}", headers=auth("alice"),
                            json={"expected_revision": 1, "title": "v2", "theme_id": "neon-tactics",
                                  "questions": [question(1)]})
        self.assertEqual(r.status_code, 200)
        r = self.client.post(f"/api/quiz/drafts/{first['draft_id']}/publish", headers=auth("alice"),
                             json={"expected_revision": 2})
        self.assertEqual(r.status_code, 201)
        # another user's quota is independent
        self.published(user="carol")

    def test_pro_grant_raises_quota_and_unlocks_arcane(self):
        r = self.client.post("/api/quiz/drafts", headers=auth("alice"),
                             json={"title": "t", "theme_id": "arcane-academy", "questions": []})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"]["code"], "theme_not_entitled")
        grant = give_pro(self.store, "alice", self.clock)
        summary = self.client.get("/api/quiz/me/entitlements", headers=auth("alice")).json()
        self.assertEqual(summary["plan"], "pro")
        self.assertEqual(summary["published_limit"], 50)
        self.assertEqual(summary["themes"], ["neon-tactics", "arcane-academy"])
        for i in range(6):
            self.published(questions=[question(i + 1)], theme="arcane-academy")
        draft = create_draft(self.client, "alice", [question(7)], theme_id="arcane-academy")
        # revoke -> back to Free: premium theme cannot be published and quota is 5 again
        revoke_grant(self.store, user_id="alice", grant_id=grant.grant_id, actor="qa-fixture",
                     reason="test revoke", now=self.clock())
        r = publish(self.client, "alice", draft)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"]["code"], "theme_not_entitled")
        stored = self.store.list_grants("alice")[0]
        self.assertEqual((stored.revoked_by, stored.revoke_reason), ("qa-fixture", "test revoke"))

    def test_expired_grant_and_role_names_do_not_grant_pro(self):
        from datetime import timedelta
        give_pro(self.store, "alice", self.clock, expires_at=self.clock() + timedelta(days=1))
        self.assertEqual(self.client.get("/api/quiz/me/entitlements",
                                         headers=auth("alice")).json()["plan"], "pro")
        self.clock.advance(days=2)
        self.assertEqual(self.client.get("/api/quiz/me/entitlements",
                                         headers=auth("alice")).json()["plan"], "free")
        # a user id that *looks* privileged gets nothing special
        self.assertEqual(self.client.get("/api/quiz/me/entitlements",
                                         headers=auth("admin")).json()["plan"], "free")

    def test_no_http_route_grants_pro(self):
        paths = {getattr(r, "path", "") for r in self.client.app.routes}
        self.assertFalse([p for p in paths if "grant" in p or "entitlement" in p and p != "/api/quiz/me/entitlements"])
        for method in ("post", "put", "patch"):
            r = getattr(self.client, method)("/api/quiz/me/entitlements", headers=auth("alice"),
                                              json={"plan": "pro"})
            self.assertEqual(r.status_code, 405)


class TestSoloSession(QuizApiBase):
    def test_no_key_before_reveal_and_elimination(self):
        _, pub = self.published(questions=[question(1, options=4, correct=[3])])
        view = self.start(pub["share_id"])
        self.assertEqual((view["phase"], view["attempt_limit"], view["can_submit"]), ("answering", 2, True))
        self.assertIsNone(view["reveal"])
        self.assertFalse({"correct_option_ids", "explanation"} & set(walk_keys(view["question"])))
        self.assertEqual(view["cue"]["cue"], "summon")
        res = self.submit(view, [opt(1, 1)])
        self.assertEqual(res["outcome"], "accepted")
        self.assertFalse(res["receipt"]["correct"])
        v = res["view"]
        self.assertEqual((v["phase"], v["attempts_remaining"], v["eliminated_option_ids"]),
                         ("answering", 1, [opt(1, 1)]))
        self.assertIsNone(v["reveal"])
        self.assertNotIn(opt(1, 3), json.dumps(v["last_attempt"]))
        # eliminated option cannot be picked again
        self.assertEqual(self.submit(v, [opt(1, 1)])["reason"], "invalid_option")
        res = self.submit(v, [opt(1, 3)])
        v = res["view"]
        self.assertEqual((v["phase"], v["score"], v["cue"]["cue"]), ("revealed", 1, "hit-second"))
        self.assertEqual(v["reveal"]["correct_option_ids"], [opt(1, 3)])
        self.assertEqual(v["reveal"]["explanation"], "Giải thích câu 1.")
        self.assertFalse(v["can_submit"])

    def test_attempt_rules_per_kind(self):
        qs = [question(1, "boolean"), question(2, "single", options=2),
              question(3, "multiple", options=4, correct=[1, 2])]
        _, pub = self.published(questions=qs)
        v = self.start(pub["share_id"])
        self.assertEqual(v["attempt_limit"], 1)                       # boolean: 1
        v = self.submit(v, [opt(1, 2)])["view"]
        self.assertEqual((v["phase"], v["score"], v["cue"]["cue"]), ("revealed", 0, "miss"))
        v = self.advance(v)
        self.assertEqual(v["attempt_limit"], 1)                       # single 2 options: min(2,1)
        v = self.advance(self.submit(v, [opt(2, 1)])["view"])
        self.assertEqual(v["attempt_limit"], 2)                       # multiple: 2, exact set
        r1 = self.submit(v, [opt(3, 1)])                              # subset is wrong
        self.assertFalse(r1["receipt"]["correct"])
        self.assertEqual(r1["view"]["eliminated_option_ids"], [])    # no elimination for multiple
        r2 = self.submit(r1["view"], [opt(3, 1), opt(3, 2), opt(3, 3)])  # superset is wrong
        v = r2["view"]
        self.assertEqual((v["phase"], v["score"]), ("revealed", 1))
        self.assertFalse(v["reveal"]["correct"])
        v = self.advance(v)
        self.assertEqual((v["phase"], v["score"], v["max_score"], v["cue"]["cue"]),
                         ("finished", 1, 3, "victory"))
        self.assertEqual([r["correct"] for r in v["results"]], [False, True, False])
        self.assertIsNone(v["question"])
        # finished: advance replay is idempotent, submit is rejected
        self.assertEqual(self.advance(v)["state_revision"], v["state_revision"])

    def test_multiple_exact_set_scores_one_point_no_speed_bonus(self):
        _, pub = self.published(questions=[question(1, "multiple", correct=[2, 4])])
        v = self.start(pub["share_id"])
        res = self.submit(v, [opt(1, 4), opt(1, 2)])
        self.assertTrue(res["receipt"]["correct"])
        self.assertEqual((res["view"]["score"], res["view"]["cue"]["cue"]), (1, "hit-first"))

    def test_idempotent_replay_and_payload_conflict(self):
        _, pub = self.published(questions=[question(1, options=4, correct=[2])])
        v = self.start(pub["share_id"])
        rid = _rid()
        first = self.submit(v, [opt(1, 2)], request_id=rid)
        self.assertEqual(first["outcome"], "accepted")
        replay = self.submit(v, [opt(1, 2)], request_id=rid)
        self.assertEqual(replay["outcome"], "duplicate")
        self.assertEqual(replay["receipt"], first["receipt"])
        self.assertEqual(replay["view"]["score"], 1)
        self.assertEqual(replay["view"]["state_revision"], first["view"]["state_revision"])
        conflict = self.submit(v, [opt(1, 3)], request_id=rid)
        self.assertEqual((conflict["outcome"], conflict["reason"]), ("rejected", "payload_conflict"))
        self.assertIsNone(conflict["receipt"])
        self.assertEqual(conflict["view"]["score"], 1)

    def test_revision_and_attempt_guards(self):
        _, pub = self.published(questions=[question(1), question(2)])
        v = self.start(pub["share_id"])
        self.assertEqual(self.submit(v, [opt(1, 2)], qrev=2)["reason"], "wrong_revision")
        self.assertEqual(self.submit(v, [opt(2, 1)], question_id=question(2)["id"])["reason"],
                         "wrong_revision")
        self.assertEqual(self.submit(v, [opt(1, 2)], attempt=2)["reason"], "attempt_mismatch")
        self.assertEqual(self.submit(v, [opt(1, 2), opt(1, 3)])["reason"], "invalid_option")
        self.assertEqual(self.submit(v, [opt(7, 1)])["reason"], "invalid_option")
        unchanged = self.client.get(f"/api/quiz/sessions/{v['session_id']}", headers=auth("bob")).json()
        self.assertEqual(unchanged["state_revision"], 1)
        done = self.submit(v, [opt(1, 1)])["view"]
        self.assertEqual(self.submit(done, [opt(1, 2)], attempt=2)["reason"], "not_answering")
        r = self.client.post(f"/api/quiz/sessions/{v['session_id']}/advance", headers=auth("bob"),
                             json={"expected_question_revision": 2})
        self.assertEqual(r.status_code, 409)
        nxt = self.advance(done)
        self.assertEqual(nxt["question_revision"], 2)
        self.assertEqual(self.advance(done)["question_revision"], 2)  # replayed advance

    def test_deadline_is_server_side(self):
        _, pub = self.published(questions=[question(1, time_limit_ms=5000), question(2)])
        v = self.start(pub["share_id"])
        self.assertEqual(v["deadline_at"], "2026-10-08T12:00:05.000000Z")
        self.clock.advance(seconds=6)  # inside 1.5 s grace
        self.assertTrue(self.client.get(f"/api/quiz/sessions/{v['session_id']}",
                                        headers=auth("bob")).json()["can_submit"])
        self.clock.advance(seconds=1)
        res = self.submit(v, [opt(1, 1)])
        self.assertEqual((res["outcome"], res["reason"]), ("rejected", "late"))
        self.assertEqual(res["view"]["phase"], "revealed")
        self.assertTrue(res["view"]["reveal"]["timed_out"])
        self.assertEqual(res["view"]["score"], 0)
        self.assertIsNone(self.advance(res["view"])["deadline_at"])


class TestCsv(QuizApiBase):
    GOOD = ("kind,prompt,options,correct,explanation,difficulty,time_limit_ms\n"
            "single,Thủ đô Nhật?,Tokyo|Osaka|Kyoto,1,Tokyo.,easy,20000\n"
            "multiple,Số chẵn?,1|2|3|4,2|4,,hard,\n"
            "boolean,Trời xanh?,Đúng|Sai,1,,,\n")

    def _draft(self, n=1):
        return create_draft(self.client, "alice", [question(i + 1) for i in range(n)])

    def test_validate_and_commit_append(self):
        d = self._draft()
        r = self.client.post(f"/api/quiz/drafts/{d['draft_id']}/csv/validate", headers=auth("alice"),
                             json={"csv": self.GOOD, "strategy": "append"})
        body = r.json()
        self.assertTrue(body["valid"], body)
        self.assertEqual((body["row_count"], body["resulting_question_count"]), (3, 4))
        self.assertEqual([row["row"] for row in body["rows"]], [2, 3, 4])
        r = self.client.post(f"/api/quiz/drafts/{d['draft_id']}/csv/commit", headers=auth("alice"),
                             json={"csv": self.GOOD, "strategy": "append", "expected_revision": 1})
        self.assertEqual(r.status_code, 200, r.text)
        draft = r.json()
        self.assertEqual((draft["revision"], len(draft["questions"])), (2, 4))
        q = draft["questions"][2]
        self.assertEqual(q["kind"], "multiple")
        self.assertEqual(q["correct_option_ids"], [q["options"][1]["id"], q["options"][3]["id"]])

    def test_commit_is_all_or_nothing_with_one_based_rows(self):
        d = self._draft()
        bad = self.GOOD + "single,Thiếu đáp án,A|B,5,,,\nweird,X?,A|B,1,,,\n"
        r = self.client.post(f"/api/quiz/drafts/{d['draft_id']}/csv/commit", headers=auth("alice"),
                             json={"csv": bad, "strategy": "replace", "expected_revision": 1})
        self.assertEqual(r.status_code, 422)
        detail = r.json()["detail"]
        self.assertEqual(detail["code"], "csv_invalid")
        self.assertEqual([(e["row"], e["column"], e["code"]) for e in detail["csv_errors"]],
                         [(5, "correct", "invalid_correct"), (6, "kind", "invalid_kind")])
        after = self.client.get(f"/api/quiz/drafts/{d['draft_id']}", headers=auth("alice")).json()
        self.assertEqual((after["revision"], len(after["questions"])), (1, 1))

    def test_header_and_size_limits(self):
        d = self._draft()
        cases = {
            "prompt,options\nx,y\n": ("header", "missing_column"),
            "kind,prompt,options,correct,colour\n": ("header", "unknown_column"),
            "   \n": ("file", "empty_file"),
            "kind,prompt,options,correct\n": ("file", "empty_file"),
            "kind,prompt,options,correct\n" + "single,Q?,A|B,1\n" * 201: ("file", "too_many_rows"),
            'kind,prompt,options,correct\nsingle,"unterminated,A|B,1\n': ("file", "csv_syntax"),
        }
        for text, (column, code) in cases.items():
            r = self.client.post(f"/api/quiz/drafts/{d['draft_id']}/csv/validate", headers=auth("alice"),
                                 json={"csv": text, "strategy": "replace"})
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertFalse(body["valid"])
            self.assertEqual((body["errors"][0]["column"], body["errors"][0]["code"]), (column, code), text[:60])
        full = self._draft(199)
        two = "kind,prompt,options,correct\nsingle,Q1?,A|B,1\nsingle,Q2?,A|B,2\n"
        r = self.client.post(f"/api/quiz/drafts/{full['draft_id']}/csv/validate", headers=auth("alice"),
                             json={"csv": two, "strategy": "append"})
        self.assertEqual(r.json()["errors"][0]["code"], "draft_capacity")
        r = self.client.post(f"/api/quiz/drafts/{full['draft_id']}/csv/validate", headers=auth("alice"),
                             json={"csv": two, "strategy": "replace"})
        self.assertTrue(r.json()["valid"])

    def test_commit_stale_revision_conflicts(self):
        d = self._draft()
        r = self.client.post(f"/api/quiz/drafts/{d['draft_id']}/csv/commit", headers=auth("alice"),
                             json={"csv": self.GOOD, "strategy": "append", "expected_revision": 3})
        self.assertEqual(r.status_code, 409)


if __name__ == "__main__":
    unittest.main()
