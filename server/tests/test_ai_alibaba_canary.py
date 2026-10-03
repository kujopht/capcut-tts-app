"""
Owner-only Alibaba real-chat canary route (`ALIBABA_CANARY`).

What must hold BEFORE the slot is ever enabled for it:

  * the route is selectable ONLY by an authenticated Owner request that also asked for the QA lane (`qa: true`), decided
    server-side; a normal user, an anonymous caller, an Owner on the ordinary lane, an ordinary conversation mode, a client
    field / header / query value, or any default fallback can NEVER reach it;
  * it is not a routing profile: no mode, `web_search_profile`, `PUT /profiles/<name>` or default profile can name it;
  * it contains only slots of the isolated Alibaba partition, and never falls back to Gemini (or anything else) when its
    slot fails — a canary failure must be visible, not silently served by someone else;
  * public Gemini routing, the per-user limit, the global limit and the kill switch behave exactly as before;
  * the route lives only in the isolated collection (the previous production release never reads it).

Deterministic: fake providers + fake Appwrite. No network, no real key, no Alibaba quota.
"""
from __future__ import annotations

import json
import re
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

from server.ai_assistant.control.model import CANARY_PROFILES, PROFILES, ConfigValidationError
from server.ai_assistant.control.secrets import SecretResolver
from server.ai_assistant.control.service import ControlConflict
from server.llm_gateway.chat_provider import ProviderError
from server.tests.test_ai_alibaba_control_plane import a_slot, persist_slot
from server.tests.test_ai_alibaba_isolation import Rig, old_release_view
from server.tests.test_ai_control_plane import env_for
from server.tests.test_ai_e2e_regression import Prov, World, ev

SLOT = "alibaba-sg-01"
ROUTE = "ALIBABA_CANARY"
FORBID = ("alibaba", "sg-01", "qwen", "dashscope", "aliyun", "maas", "thinking", "reasoning", "gemini", "canary")


def canary_world(*, configure: bool = True, alibaba_script: Any = (), **kw: Any) -> World:
    """Two Gemini slots (deterministic order) + one Alibaba slot ENABLED with its type flag ON and the gate open — the exact
    state of the real canary — and, unless told otherwise, the canary route set to that one slot."""
    kw.setdefault("slots", 2)
    kw.setdefault("global_cap", 500)
    kw.setdefault("per_user", 100)
    kw.setdefault("owner_qa", 50)
    kw.setdefault("prio", {"gemini-01": 10, "gemini-02": 20})
    w = World(**kw)
    a = a_slot(SLOT, thinking="off")
    persist_slot(w.store, a)
    w.store.controls = replace(w.store.controls, provider_types={**w.store.controls.provider_types, "alibaba": True})
    w.provs[SLOT] = Prov(SLOT, script=alibaba_script)
    w.plane._gates["alibaba"] = True  # noqa: SLF001
    w.plane.secrets = SecretResolver({**env_for(*w.slots), **env_for(a)})
    if configure:
        w.plane.update_canary("owner", ROUTE, [SLOT])
    w.plane.invalidate()
    return w


def alibaba_calls(w: World) -> int:
    return len(w.provs[SLOT].requests)


def gemini_calls(w: World) -> int:
    return sum(len(p.requests) for sid, p in w.provs.items() if sid != SLOT)


def clean(testcase: unittest.TestCase, text: str) -> None:
    low = text.lower()
    for word in FORBID:
        testcase.assertNotIn(word, low, word)


# ================================================================== the Owner path works, and only for the Owner


class TestOwnerCanaryPath(unittest.TestCase):
    def test_an_owner_qa_request_naming_the_route_is_served_by_the_canary_slot_and_nothing_else(self) -> None:
        w = canary_world()
        for mode in ("general", "story", "writer", "support"):
            cid, r = w.ask("owner", "xin chào", mode=mode, qa=True, qa_route=ROUTE)
            self.assertEqual(r.status_code, 200, (mode, r.text))
            self.assertTrue(ev(r, "delta") and ev(r, "done"), mode)
            clean(self, r.text)  # no slot / provider / model / route / reasoning metadata in the ordinary stream
        self.assertEqual((alibaba_calls(w), gemini_calls(w)), (4, 0), "every turn went to the canary slot, none to Gemini")
        self.assertEqual(w.per_slot(), {SLOT: 4}, "slot usage is counted like any real traffic")
        self.assertEqual(w.avail("owner")["qa"]["requests_used"], 4, "it spends the Owner QA allowance …")
        self.assertEqual(w.avail("owner")["limits"]["requests_used"], 0, "… and never the Owner's ordinary per-user allowance")

    def test_continuation_with_context_stop_and_regenerate_keep_the_route_only_when_asked(self) -> None:
        w = canary_world()
        cid, r1 = w.ask("owner", "Viết mở đầu một truyện ngắn.", mode="story", qa=True, qa_route=ROUTE)
        self.assertEqual(r1.status_code, 200)
        _, r2 = w.ask("owner", "Viết tiếp đoạn sau.", cid=cid, mode="story", qa=True, qa_route=ROUTE)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(alibaba_calls(w), 2)
        # the route is per REQUEST: a follow-up that does not ask for it is an ordinary turn (Gemini) — nothing is "sticky"
        _, r3 = w.ask("owner", "Tiếp nữa.", cid=cid, mode="story", qa=True)
        self.assertEqual(r3.status_code, 200)
        self.assertEqual((alibaba_calls(w), gemini_calls(w)), (2, 1))
        # regenerate of a previous answer, asking for the route again
        first = [m for m in w.messages(cid) if getattr(m, "role", "") == "assistant"][0]
        r4 = w.c.post(f"/api/ai/conversations/{cid}/messages", headers=w.hdr("owner"),
                      json={"content": "Viết lại.", "client_id": "regen-1", "regenerate_of": first.message_id, "qa": True,
                            "qa_route": ROUTE})
        self.assertEqual(r4.status_code, 200, r4.text)
        self.assertEqual(alibaba_calls(w), 3)


class TestNobodyElseCanSelectIt(unittest.TestCase):
    #: Everything a client can put on a request that might smell like "give me that route".
    BODY_FIELDS = [
        {"qa": True, "qa_route": ROUTE}, {"qa_route": ROUTE}, {"route": ROUTE}, {"profile": ROUTE}, {"canary": ROUTE},
        {"qa_profile": ROUTE}, {"mode_profile": ROUTE}, {"provider": "alibaba"}, {"slot_id": SLOT}, {"slot": SLOT},
        {"model": "qwen3.7-plus"}, {"workload": ROUTE}, {"tier": "SMART"}, {"qa": True, "route": ROUTE, "profile": ROUTE},
        {"qa": True, "qa_route": {"name": ROUTE}}, {"qa": True, "qa_route": [ROUTE]}, {"qa": True, "qa_route": 1234},
        {"qa": True, "qa_route": "x" * 5000}, {"qa": "true", "qa_route": ROUTE}, {"qa": 1, "qa_route": ROUTE},
    ]

    def test_a_normal_user_gets_an_ordinary_turn_whatever_the_request_body_says(self) -> None:
        w = canary_world()
        for i, extra in enumerate(self.BODY_FIELDS):
            with self.subTest(extra=str(extra)[:60]):
                before = w.avail("alice")["limits"]["requests_used"]
                _, r = w.ask("alice", "xin chào", **extra)
                self.assertEqual(r.status_code, 200, r.text)
                self.assertTrue(ev(r, "delta") and ev(r, "done"))
                self.assertEqual(alibaba_calls(w), 0, "the canary slot was NEVER called")
                self.assertEqual(w.avail("alice")["limits"]["requests_used"], before + 1,
                                 "…and it was counted as an ordinary user turn, not a QA turn")
        self.assertGreaterEqual(gemini_calls(w), len(self.BODY_FIELDS))

    def test_headers_and_query_strings_select_nothing(self) -> None:
        w = canary_world()
        for who in ("alice", "owner"):
            cid = w.conv(who)
            r = w.c.post(f"/api/ai/conversations/{cid}/messages?qa_route={ROUTE}&route={ROUTE}&qa=true&profile={ROUTE}",
                         headers={**w.hdr(who), "X-QA-Route": ROUTE, "X-AI-Route": ROUTE, "X-AI-Profile": ROUTE},
                         json={"content": "xin chào", "client_id": f"h-{who}"})
            self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(alibaba_calls(w), 0)

    def test_an_owner_on_the_ordinary_lane_cannot_use_it_either(self) -> None:
        """`qa_route` without `qa: true` is ignored: the route is a property of the QA lane, never a standalone switch."""
        w = canary_world()
        _, r = w.ask("owner", "xin chào", qa_route=ROUTE)
        self.assertEqual(r.status_code, 200)
        self.assertEqual((alibaba_calls(w), gemini_calls(w)), (0, 1))
        self.assertEqual(w.avail("owner")["qa"]["requests_used"], 0, "and it did not spend the QA allowance")

    def test_anonymous_and_expired_callers_are_refused_before_anything_runs(self) -> None:
        w = canary_world()
        cid = w.conv("owner")
        for headers in ({}, {"Authorization": "Bearer "}, {"Authorization": "Basic x"}):
            r = w.c.post(f"/api/ai/conversations/{cid}/messages", headers=headers,
                         json={"content": "hi", "client_id": "a", "qa": True, "qa_route": ROUTE})
            self.assertEqual(r.status_code, 401, headers)
        w.revoked.add("owner")
        r = w.c.post(f"/api/ai/conversations/{cid}/messages", headers=w.hdr("owner"),
                     json={"content": "hi", "client_id": "b", "qa": True, "qa_route": ROUTE})
        self.assertEqual(r.status_code, 401)
        self.assertEqual((alibaba_calls(w), gemini_calls(w)), (0, 0))

    def test_an_ordinary_conversation_mode_cannot_be_the_route(self) -> None:
        w = canary_world()
        for who in ("alice", "owner"):
            for mode in (ROUTE, ROUTE.lower(), "alibaba", SLOT):
                r = w.c.post("/api/ai/conversations", headers=w.hdr(who), json={"mode": mode})
                self.assertEqual(r.status_code, 200)
                cid = r.json()["conversation_id"]
                _, msg = w.ask(who, "xin chào", cid=cid)
                self.assertEqual(msg.status_code, 200)
        self.assertEqual(alibaba_calls(w), 0, "an unknown mode just becomes the general mode, on the public profiles")

    def test_a_malformed_or_unknown_route_from_the_owner_is_refused_not_silently_served_by_gemini(self) -> None:
        w = canary_world()
        for bad in ("alibaba_canary", ROUTE + " ", " " + ROUTE, "ALIBABA", "", "FREE_FIRST", "../x", ROUTE + "\n", 1, ["x"], {"a": 1}):
            with self.subTest(bad=repr(bad)[:40]):
                _, r = w.ask("owner", "xin chào", qa=True, qa_route=bad)
                self.assertEqual(r.status_code, 422, r.text)
                self.assertEqual(r.json()["detail"]["code"], "ai_canary_unavailable")
                if isinstance(bad, str) and len(bad.strip()) >= 3:
                    self.assertNotIn(bad.strip(), r.text, "the value is not echoed")
        self.assertEqual((alibaba_calls(w), gemini_calls(w)), (0, 0))
        self.assertEqual(w.avail("owner")["qa"]["requests_used"], 0, "a refused request spends nothing")

    def test_an_unconfigured_route_is_refused_for_the_owner_and_invisible_to_everyone_else(self) -> None:
        w = canary_world(configure=False)
        _, r = w.ask("owner", "xin chào", qa=True, qa_route=ROUTE)
        self.assertEqual((r.status_code, r.json()["detail"]["code"]), (422, "ai_canary_unavailable"))
        _, r = w.ask("alice", "xin chào", qa=True, qa_route=ROUTE)
        self.assertEqual(r.status_code, 200, "a normal user gets no hint that the route exists or not")
        self.assertEqual(alibaba_calls(w), 0)


# ================================================================== it can never be reached by configuration either


class TestOnlyTheValidatedCallSiteForwardsARoute(unittest.TestCase):
    """The isolation rests on one convention: the gateway/planner only ever receive a route name the chat handler validated
    (Owner + QA lane + exact match). A new production caller that forwards a route must be a conscious, reviewed decision, so the
    complete set of places that do it is pinned here."""

    ROOT = Path(__file__).resolve().parents[1]

    def _hits(self, pattern: str) -> dict:
        found = {}
        for path in sorted((self.ROOT).rglob("*.py")):
            if "tests" in path.relative_to(self.ROOT).parts:
                continue
            for m in re.finditer(pattern, path.read_text(encoding="utf-8")):
                found.setdefault(path.relative_to(self.ROOT).as_posix(), []).append(m.group(1))
        return found

    def test_the_route_reaches_the_gateway_only_from_the_handlers_server_side_decision(self) -> None:
        self.assertEqual(self._hits(r'\{"route":\s*(\w+)\}'),
                         {"ai_assistant/routes.py": ["canary_route"], "ai_assistant/control/router.py": ["route"]})
        self.assertEqual(self._hits(r"\broute=(\w+)"), {"ai_assistant/control/service.py": ["route"]})
        handler = (self.ROOT / "ai_assistant/routes.py").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"\bcanary_route\s*(?::[^=\n]+)?=", handler)), 2, "declared once, assigned once")
        self.assertNotIn("payload.qa_route", handler.split("canary_route_name, payload.qa_route")[1])


class TestItIsNotARoutingProfile(unittest.TestCase):
    def test_the_name_is_outside_the_profile_namespace_so_no_mode_or_default_can_point_at_it(self) -> None:
        self.assertEqual(CANARY_PROFILES, (ROUTE,))
        self.assertFalse(set(CANARY_PROFILES) & set(PROFILES))
        w = canary_world()
        c = w.c
        owner = {"Authorization": "Bearer owner"}
        r = c.put(f"/api/admin/ai/profiles/{ROUTE}", headers=owner, json={"steps": [SLOT], "enabled": True})
        self.assertEqual(r.status_code, 422, "not a profile: it cannot be created through the profile API")
        with self.assertRaises(ConfigValidationError):
            w.plane.update_controls("owner", {"mode_profiles": {"general": ROUTE, "story": "STORY", "writer": "WRITER",
                                                                 "support": "SUPPORT_SAFE"}})
        with self.assertRaises(ConfigValidationError):
            w.plane.update_controls("owner", {"web_search_profile": ROUTE})
        cfg = w.plane.snapshot()
        self.assertNotIn(ROUTE, cfg.profiles)
        self.assertEqual({p.name for p in cfg.profiles.values()}, set(PROFILES))
        for p in cfg.profiles.values():
            self.assertNotIn(SLOT, p.steps)
            self.assertNotIn("alibaba", p.steps)

    def test_public_routing_is_identical_with_the_slot_enabled_the_type_on_and_the_route_configured(self) -> None:
        baseline = World(slots=2, global_cap=500, per_user=100, prio={"gemini-01": 10, "gemini-02": 20})
        w = canary_world()
        for mode in ("general", "story", "writer", "support"):
            for plane in (baseline.plane, w.plane):
                plane.invalidate()
            a = [(s.slot_id, why) for s, why in baseline.plane.plan(baseline.plane.snapshot(), mode=mode, workload=mode)]
            b = [(s.slot_id, why) for s, why in w.plane.plan(w.plane.snapshot(), mode=mode, workload=mode)]
            self.assertEqual(a, b, mode)
            self.assertNotIn(SLOT, [sid for sid, _ in b])
        wa = w.plane.plan(w.plane.snapshot(), mode="general", workload="web_search")
        self.assertNotIn(SLOT, [s.slot_id for s, _ in wa])
        for i in range(8):  # real public traffic, every mode, normal users
            _, r = w.ask(f"user{i}", "xin chào", mode=("general", "story", "writer", "support")[i % 4])
            self.assertEqual(r.status_code, 200)
        self.assertEqual(alibaba_calls(w), 0)

    def test_the_route_accepts_only_alibaba_slots_that_exist_and_nothing_else(self) -> None:
        w = canary_world(configure=False)
        p = w.plane
        for bad, why in ((["gemini-01"], "a public Gemini slot"), (["alibaba"], "a provider TYPE name"), (["ghost-01"], "unknown"),
                         ([SLOT, SLOT], "duplicate"), (["gemini-01", SLOT], "mixed with a public slot"), ([""], "empty id"),
                         ("alibaba-sg-01", "not a list"), ([1], "not strings"), (None, "none")):
            with self.subTest(why):
                with self.assertRaises(ConfigValidationError):
                    p.update_canary("owner", ROUTE, bad)
        with self.assertRaises(ConfigValidationError):
            p.update_canary("owner", "FREE_FIRST", [SLOT])
        with self.assertRaises(ConfigValidationError):
            p.update_canary("owner", "alibaba_canary", [SLOT])
        self.assertEqual(p.snapshot().canary, {})
        self.assertEqual(p.update_canary("owner", ROUTE, [SLOT]), {"name": ROUTE, "steps": [SLOT]})
        self.assertEqual(p.snapshot().canary, {ROUTE: (SLOT,)})
        self.assertEqual(p.config_view()["canary_profiles"], [{"name": ROUTE, "steps": [SLOT]}])
        with self.assertRaises(ControlConflict):
            p.delete_slot("owner", SLOT)  # a slot the route uses cannot be deleted from under it
        p.update_canary("owner", ROUTE, [])  # empty = remove the route
        self.assertEqual(p.snapshot().canary, {})
        p.delete_slot("owner", SLOT)

    def test_only_the_owner_can_change_the_route_and_the_change_is_audited(self) -> None:
        w = canary_world(configure=False)
        url = f"/api/admin/ai/canary-profiles/{ROUTE}"
        for who, status in ((None, 401), ("user", 403), ("mod", 403), ("admin", 403), ("alice", 403), ("owner", 200)):
            r = w.c.put(url, headers=({"Authorization": f"Bearer {who}"} if who else {}), json={"steps": [SLOT]})
            self.assertEqual(r.status_code, status, who)
        self.assertEqual(w.plane.snapshot().canary, {ROUTE: (SLOT,)})
        entries = [(a["entity"], a["field"], a["new_value"]) for a in w.plane.audit(50) if a["entity"] == f"canary:{ROUTE}"]
        self.assertEqual(entries, [(f"canary:{ROUTE}", "steps", json.dumps([SLOT]))])


# ================================================================== no fallback; limits and the kill switch still apply


class TestCanaryNeverFallsBackAndLimitsStillApply(unittest.TestCase):
    def test_when_the_canary_slot_fails_the_owner_sees_an_error_and_gemini_is_never_called(self) -> None:
        err = ProviderError("boom", code="provider_http_503", category="UNAVAILABLE")
        w = canary_world(alibaba_script=[err, err])
        for _ in range(2):
            _, r = w.ask("owner", "xin chào", qa=True, qa_route=ROUTE)
            self.assertEqual(r.status_code, 200)
            self.assertTrue(ev(r, "error"), r.text)
            self.assertFalse(ev(r, "delta"))
            clean(self, r.text)
        self.assertEqual(gemini_calls(w), 0, "no silent fallback — a failed canary must look failed")

    def test_a_disabled_or_gated_canary_slot_means_no_provider_not_gemini(self) -> None:
        for how in ("slot off", "type off", "gate closed"):
            with self.subTest(how):
                w = canary_world()
                if how == "slot off":
                    w.plane.update_slot("owner", SLOT, {"enabled": False})
                elif how == "type off":
                    w.plane.set_provider_type("owner", "alibaba", False)
                else:
                    w.plane._gates["alibaba"] = False  # noqa: SLF001
                w.plane.invalidate()
                _, r = w.ask("owner", "xin chào", qa=True, qa_route=ROUTE)
                self.assertTrue(ev(r, "error"), r.text)
                self.assertEqual((alibaba_calls(w), gemini_calls(w)), (0, 0))

    def test_the_planner_itself_returns_nothing_for_a_canary_route_when_the_switch_is_off(self) -> None:
        """Defence in depth: the admission layer refuses first, but `plan` must not depend on that."""
        w = canary_world()
        self.assertEqual([s.slot_id for s, _ in w.plane.plan(w.plane.snapshot(), mode="general", workload="general", route=ROUTE)], [SLOT])
        w.set_controls(ai_enabled=False)
        self.assertEqual(w.plane.plan(w.plane.snapshot(), mode="general", workload="general", route=ROUTE), [])
        self.assertEqual(w.plane.plan(w.plane.snapshot(), mode="general", workload="general"), [])

    def test_an_unknown_route_name_reaching_the_planner_yields_no_slot_and_never_a_default_profile(self) -> None:
        w = canary_world()
        for name in ("NOPE", "", "gemini-01", "general", "GENERAL", "SMART_FIRST"):
            self.assertEqual(w.plane.plan(w.plane.snapshot(), mode="general", workload="general", route=name), [], name)

    def test_the_kill_switch_beats_the_canary(self) -> None:
        w = canary_world()
        _, ok = w.ask("owner", "xin chào", qa=True, qa_route=ROUTE)
        self.assertTrue(ev(ok, "delta"))
        w.set_controls(ai_enabled=False)
        _, r = w.ask("owner", "xin chào", qa=True, qa_route=ROUTE)
        self.assertNotEqual(r.status_code, 200)
        self.assertEqual((alibaba_calls(w), gemini_calls(w)), (1, 0), "nothing ran after the switch")

    def test_the_global_ceiling_and_the_owner_qa_allowance_still_apply_to_canary_turns(self) -> None:
        w = canary_world(global_cap=2)
        for _ in range(2):
            _, r = w.ask("owner", "xin chào", qa=True, qa_route=ROUTE)
            self.assertEqual(r.status_code, 200)
        _, r = w.ask("owner", "xin chào", qa=True, qa_route=ROUTE)
        self.assertEqual((r.status_code, r.json()["detail"]["code"], r.json()["detail"].get("scope")), (429, "ai_budget_exhausted", "global"))
        self.assertEqual(alibaba_calls(w), 2)
        w2 = canary_world(owner_qa=1)
        _, r = w2.ask("owner", "xin chào", qa=True, qa_route=ROUTE)
        self.assertEqual(r.status_code, 200)
        _, r = w2.ask("owner", "xin chào", qa=True, qa_route=ROUTE)
        self.assertEqual((r.status_code, r.json()["detail"].get("scope")), (429, "qa"))
        self.assertEqual(alibaba_calls(w2), 1)

    def test_normal_user_limits_are_untouched_by_canary_turns(self) -> None:
        w = canary_world(per_user=5)
        for _ in range(3):
            w.ask("owner", "xin chào", qa=True, qa_route=ROUTE)
        self.assertEqual(w.avail("alice")["limits"]["requests_used"], 0)
        for _ in range(5):
            _, r = w.ask("alice", "xin chào")
            self.assertEqual(r.status_code, 200)
        _, r = w.ask("alice", "xin chào")
        self.assertEqual(r.status_code, 429, "alice's own 5/day is exactly as before")


# ================================================================== persistence: isolated store only, rollback-safe


class TestCanaryPersistence(unittest.TestCase):
    def test_the_route_lives_only_in_the_isolated_collection_and_round_trips(self) -> None:
        rig = Rig().configure()
        rig.plane.update_canary("owner", ROUTE, ["alibaba-01"])
        rig.plane.invalidate()
        self.assertEqual(rig.plane.snapshot().canary, {ROUTE: ("alibaba-01",)})
        row = rig.fake.cols["ai_alibaba_config"][f"c-{ROUTE}"]
        self.assertEqual((row["kind"], row["key"], json.loads(row["data_json"])), ("canary", ROUTE, {"steps": ["alibaba-01"]}))
        for coll in ("ai_routing_profiles", "ai_provider_slots", "ai_control_settings"):
            self.assertNotIn(ROUTE, json.dumps(rig.fake.cols.get(coll, {})), coll)
        old = old_release_view(rig.fake)  # the previous production release still finds the configuration valid
        self.assertNotIn(ROUTE, old.profiles)
        self.assertTrue(old.controls.ai_enabled)

    def test_a_hand_edited_row_cannot_point_the_route_at_a_public_slot(self) -> None:
        rig = Rig().configure()
        rig.plane.update_canary("owner", ROUTE, ["alibaba-01"])
        row = rig.fake.cols["ai_alibaba_config"][f"c-{ROUTE}"]
        row["data_json"] = json.dumps({"steps": ["gemini-01", "alibaba-01", "ghost"]})
        rig.plane.invalidate()
        self.assertEqual(rig.plane.snapshot().canary[ROUTE], ("alibaba-01",), "only isolated-partition slots survive")

    def test_malformed_canary_rows_cost_only_themselves(self) -> None:
        rig = Rig().configure()
        rows = rig.fake.cols.setdefault("ai_alibaba_config", {})
        rows["c-NOPE"] = {"$id": "c-NOPE", "kind": "canary", "key": "NOPE", "data_json": json.dumps({"steps": ["alibaba-01"]})}
        rows["c-x"] = {"$id": "c-x", "kind": "canary", "key": ROUTE, "data_json": json.dumps({"steps": ["alibaba-01"]})}  # id mismatch
        rows[f"c-{ROUTE}"] = {"$id": f"c-{ROUTE}", "kind": "canary", "key": ROUTE, "data_json": "{not json"}
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertEqual(rig.plane.state, "ok")
        self.assertEqual(cfg.canary, {})
        self.assertEqual(cfg.ext.unreadable, 3)
        self.assertEqual([s.slot_id for s in rig.plane.snapshot().slots.values() if s.provider_type == "gemini"],
                         ["gemini-01", "gemini-02"])

    def test_in_memory_store_round_trip(self) -> None:
        from server.ai_assistant.control.store import InMemoryControlStore
        st = InMemoryControlStore()
        st.save_ext_canary(ROUTE, (SLOT,))
        self.assertEqual(st.load_ext().canaries, {ROUTE: (SLOT,)})
        st.delete_ext_canary(ROUTE)
        self.assertEqual(st.load_ext().canaries, {})


if __name__ == "__main__":
    unittest.main()
