"""
Pre-canary regression suite: Alibaba can be switched off, broken, or ROLLED BACK without ever touching the Gemini AI.

Four guarantees, each with its own class:

  * TestCodeRollbackWithPersistedSlots — the REAL previous release (a frozen byte-for-byte copy of production's `model.py` +
    `store.py`, `fixtures/legacy_release_3f86706`) loads a configuration that the new code wrote WITH persisted Alibaba slots and
    routes, and finds it valid. A negative control proves the fixture really rejects what the isolation avoids.
  * TestAlibabaDisabled — gate closed / type off / slot off / kill switch: no Alibaba request, no provider built, Gemini serves.
  * TestMalformedAlibabaConfiguration — garbage, missing, unreachable or misplaced Alibaba rows cost ONLY the Alibaba rows; the
    legacy collections keep their strict validation (a bad Gemini row still fails closed — pinned too).
  * TestGeminiOnlyOperation — with no Alibaba anywhere (and with every kind of broken Alibaba partition) Gemini routing, caps and
    the user-facing responses are unchanged.
  * TestLegacyQwenRetired — `FAS_AI_ALIBABA_ENABLED=1` does not wake the legacy `qwen` path; `qwen` is gone from the default
    profiles; the rollback path (own gate + explicit steps) works.

Deterministic: fake providers, fake clocks, `httpx.MockTransport`. No network, no real key, no Alibaba request.
"""
from __future__ import annotations

import json
import os
import random
import unittest
from dataclasses import replace
from typing import Any, Dict, List, Optional
from unittest import mock

import httpx

from server.ai_assistant.control.model import (
    DEFAULT_MODE_PROFILES, DEFAULT_PROFILE_STEPS, GATED_PROVIDER_TYPES, LEGACY_QWEN_PROFILE_STEPS, PROFILES,
    ConfigValidationError, ExtRoute, GlobalControls, ProviderSlot, RoutingProfile, is_ext_step, slot_to_dict, split_steps,
)
from server.ai_assistant.control.providers import ProviderFactory
from server.ai_assistant.control.router import SKIP_GATE_CLOSED, ControlledGateway
from server.ai_assistant.control.secrets import SecretResolver
from server.ai_assistant.control.service import ControlConflict, ControlPlane
from server.ai_assistant.control.store import (
    EXT_DATA_MAX, T_EXT, T_PROFILES, T_SLOTS, ControlSchemaOutdated, ControlStoreUnavailable, ExtPartition,
    InMemoryControlStore, parse_ext_rows,
)
from server.llm_gateway.chat_provider import ProviderError
from server.llm_gateway.usage_limits import CircuitBreaker
from server.tests.fixtures.legacy_release_3f86706 import model as old_model
from server.tests.fixtures.legacy_release_3f86706 import store as old_store
from server.tests.test_ai_alibaba_control_plane import (
    BASE, LEGACY_TYPES, _admin_client, _appwrite_store, _NoExtCollection, a_slot, served,
)
from server.tests.test_ai_control_plane import FAKE_KEY, Clock, Scripted, _FakeAppwrite, env_for, slot, turns
from server.tests.test_ai_e2e_regression import World, ev

ALL_TYPES_ON = {**{t: True for t in LEGACY_TYPES}, "alibaba": True}
STAMP = "2026-10-03T10:11:12+00:00"


# ------------------------------------------------------------------ rig: a production-shaped, Appwrite-backed plane


class _Writes(_FakeAppwrite):
    """Fake Appwrite that remembers every write (collection, document id, data) — to prove WHERE things are stored."""

    def __init__(self) -> None:
        super().__init__()
        self.writes: List[Any] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method in ("PATCH", "POST"):
            coll = request.url.path.split("/collections/")[1].split("/")[0]
            self.writes.append((coll, json.loads(request.content).get("data", {})))
        return super().__call__(request)


class Rig:
    """Two Gemini slots + one Alibaba slot, configured through the same admin API the owner uses, over a fake Appwrite."""

    def __init__(self, fake: Optional[_FakeAppwrite] = None, *, gate: bool = True, qwen_gate: bool = False) -> None:
        self.store, self.fake = _appwrite_store(fake or _Writes())
        self.gem = [slot("gemini-01", priority=10), slot("gemini-02", priority=20)]
        self.ali = a_slot("alibaba-01", priority=1)
        self.provs: Dict[str, Scripted] = {s.slot_id: Scripted(s.slot_id) for s in self.gem + [self.ali]}
        self.clk = Clock()
        self.plane = ControlPlane(
            self.store, secrets=SecretResolver(env_for(*self.gem, self.ali)),
            factory=ProviderFactory(builder=lambda s, k: self.provs[s.slot_id]), breaker=CircuitBreaker(clock_fn=self.clk),
            clock=self.clk, rng=random.Random(5), alibaba_enabled=gate, qwen_legacy_enabled=qwen_gate,
            background=lambda job: job())

    def configure(self, *, alibaba: bool = True) -> "Rig":
        """Exactly what an owner does in /admin/ai (all through the service, so what is stored is what the release stores)."""
        p = self.plane
        self.store.save_controls(GlobalControls(ai_enabled=True, provider_types=dict(ALL_TYPES_ON), version=1))
        for g in self.gem:
            p.create_slot("owner", slot_to_dict(g))
        if alibaba:
            p.create_slot("owner", {**slot_to_dict(self.ali), "enabled": False, "tiers": ["FAST"],
                                    "free_quota_remaining": 1000})
            p.update_slot("owner", "alibaba-01", {"enabled": True})
            p.update_profile("owner", "FREE_FIRST", ["alibaba-01", "gemini-01", "gemini-02"], True)
            p.update_profile("owner", "WRITER", ["alibaba", "azure_openai", "gemini"], True)
        p.invalidate()
        return self

    def turn(self, mode: str = "general") -> List[Any]:
        return list(ControlledGateway(self.plane).stream(turns(), mode=mode))


def old_release_view(fake: _FakeAppwrite) -> "old_model.ControlConfig":
    """What the PREVIOUS release (production today) makes of the rows now stored: its own loader + its own strict validation —
    exactly the two steps its `snapshot()` takes before deciding a config is usable or corrupt (AI off for everyone)."""
    from server.config import AppwriteSettings
    aw = AppwriteSettings(endpoint="https://appwrite.example/v1", project_id="p", api_key="k", database_id="db")
    st = old_store.AppwriteControlStore(aw, client=httpx.Client(transport=httpx.MockTransport(fake)))
    cfg = st.load()
    old_model.validate_config(cfg)
    return cfg


# ================================================================== code rollback with persisted slots


class TestCodeRollbackWithPersistedSlots(unittest.TestCase):
    def test_the_previous_release_finds_a_config_with_persisted_alibaba_state_valid(self) -> None:
        rig = Rig().configure()
        new = rig.plane.snapshot()
        self.assertEqual(new.profiles["FREE_FIRST"].steps, ("alibaba-01", "gemini-01", "gemini-02"), "new code routes Alibaba first")
        self.assertIn("alibaba-01", new.slots)
        self.assertEqual(rig.plane.state, "ok")

        old = old_release_view(rig.fake)  # raises if the old release would call this configuration corrupt
        self.assertEqual(set(old.slots), {"gemini-01", "gemini-02"}, "the old release sees the Gemini slots, and only them")
        self.assertEqual(old.profiles["FREE_FIRST"].steps, ("gemini-01", "gemini-02"))
        self.assertEqual(old.profiles["WRITER"].steps, ("azure_openai", "gemini"))
        self.assertTrue(old.controls.ai_enabled, "AI stays on after a rollback")
        self.assertEqual({t: old.controls.provider_types[t] for t in LEGACY_TYPES}, {t: True for t in LEGACY_TYPES})
        for name in PROFILES:
            self.assertTrue(old.profiles[name].enabled)

    def test_the_fixture_has_teeth_the_old_release_rejects_alibaba_rows_in_its_collections(self) -> None:
        """Negative control. The guarantee above is only worth something if THIS old code really does fall over on what the
        isolation avoids: a slot row of an unknown type, or a profile step it does not know."""
        rig = Rig().configure(alibaba=False)
        old_release_view(rig.fake)  # a Gemini-only config is fine
        row = {"$id": "alibaba-01", "slot_id": "alibaba-01", "provider_type": "alibaba", "label": "A", "secret_ref": "ALIBABA_A",
               "model": "m", "enabled": True, "endpoint": BASE, "priority": 1, "weight": 10, "workloads_json": '["general"]'}
        rig.fake.cols[T_SLOTS]["alibaba-01"] = row
        with self.assertRaises(old_model.ConfigValidationError):
            old_release_view(rig.fake)
        del rig.fake.cols[T_SLOTS]["alibaba-01"]
        old_release_view(rig.fake)
        rig.store.save_profile(RoutingProfile("FREE_FIRST", ("gemini-01",)))  # then a route step the old release cannot place
        rig.fake.cols[T_PROFILES]["FREE_FIRST"]["steps_json"] = json.dumps(["alibaba", "gemini-01"])
        with self.assertRaises(old_model.ConfigValidationError):
            old_release_view(rig.fake)

    def test_nothing_alibaba_is_ever_written_to_the_legacy_collections(self) -> None:
        rig = Rig().configure()
        rig.plane.set_provider_type("owner", "alibaba", True)
        rig.plane.update_slot("owner", "alibaba-01", {"label": "renamed", "tiers": ["FAST", "SMART"]})
        rig.plane.update_profile("owner", "STORY", ["alibaba-01", "gemini"], True)
        by_coll: Dict[str, List[Dict[str, Any]]] = {}
        for coll, data in rig.fake.writes:
            by_coll.setdefault(coll, []).append(data)
        for data in by_coll[T_SLOTS]:
            self.assertIn(data["provider_type"], LEGACY_TYPES)
            self.assertNotIn("alibaba", json.dumps(data).lower())
        for data in by_coll[T_PROFILES]:
            self.assertNotIn("alibaba", data["steps_json"].lower(), "no Alibaba step, by type or by slot id")
        self.assertTrue(by_coll[T_EXT], "the Alibaba state went to its own collection")
        self.assertEqual({d["kind"] for d in by_coll[T_EXT]}, {"slot", "route"})
        # the stores refuse it even if a caller tries
        with self.assertRaises(ValueError):
            rig.store.save_slot(a_slot())
        with self.assertRaises(ValueError):
            InMemoryControlStore().save_slot(a_slot())
        with self.assertRaises(ValueError):
            rig.store.save_profile(RoutingProfile("WRITER", ("alibaba", "gemini")))
        with self.assertRaises(ValueError):
            rig.store.save_ext_slot(slot("gemini-09"))

    def test_rolling_back_and_forward_loses_nothing_and_a_gemini_edit_made_meanwhile_wins(self) -> None:
        rig = Rig().configure()
        # --- the old release runs for a while and the owner edits a Gemini profile there ---
        from server.config import AppwriteSettings
        aw = AppwriteSettings(endpoint="https://appwrite.example/v1", project_id="p", api_key="k", database_id="db")
        old = old_store.AppwriteControlStore(aw, client=httpx.Client(transport=httpx.MockTransport(rig.fake)))
        old.save_profile(old_model.RoutingProfile("FREE_FIRST", ("gemini-02", "gemini-01")))
        # --- roll forward again ---
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertEqual(rig.plane.state, "ok")
        self.assertEqual(cfg.profiles["FREE_FIRST"].steps, ("gemini-02", "gemini-01"),
                         "the Gemini edit made by the old release is NOT overridden by the stale Alibaba route")
        self.assertEqual(cfg.ext.stale_routes, ("FREE_FIRST",), "…and the admin is told the route was dropped")
        self.assertIn("alibaba-01", cfg.slots, "the Alibaba slot itself survived the round trip")
        self.assertEqual(cfg.profiles["WRITER"].steps, ("alibaba", "azure_openai", "gemini"), "an untouched route is back")
        self.assertEqual(served(rig.turn("general")), ["gemini-02"], "no Alibaba in the stale profile")

    def test_deleting_the_alibaba_slots_is_not_required_before_a_rollback_any_more(self) -> None:
        """The previous design needed 'delete every alibaba slot first'. Now the old release is simply unaware of them."""
        rig = Rig().configure()
        self.assertIn("alibaba-01", rig.plane.snapshot().slots)
        old = old_release_view(rig.fake)
        self.assertNotIn("alibaba-01", old.slots)
        # a SECOND old-release round trip after owner changes on the new side
        rig.plane.update_slot("owner", "alibaba-01", {"enabled": False})
        rig.plane.set_provider_type("owner", "alibaba", False)
        old_release_view(rig.fake)


# ================================================================== alibaba disabled


class TestAlibabaDisabled(unittest.TestCase):
    def test_gate_closed_means_no_provider_built_and_no_http_even_with_everything_else_on(self) -> None:
        rig = Rig(gate=False).configure()
        built: List[str] = []

        def builder(s: ProviderSlot, k: str) -> Any:
            built.append(s.slot_id)
            return rig.provs[s.slot_id]
        rig.plane.factory = ProviderFactory(builder=builder)
        a = rig.plane.snapshot().slots["alibaba-01"]
        self.assertTrue(a.enabled)
        self.assertTrue(rig.plane.snapshot().controls.provider_types["alibaba"])
        self.assertEqual(rig.plane.skip_reason(a, "general", 10), SKIP_GATE_CLOSED)
        # Block the REAL transport only (the store's own fake Appwrite is an httpx.MockTransport, which this does not touch).
        with mock.patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("a network call was attempted")):
            for mode in ("general", "story", "writer", "support"):
                self.assertNotIn("alibaba-01", served(rig.turn(mode)), mode)
            with self.assertRaises(ProviderError) as ctx:
                rig.plane.provider_for(a, FAKE_KEY)
            self.assertEqual(ctx.exception.code, "provider_gate_closed")
            with self.assertRaises(ControlConflict):  # the owner's probe is a real request: refused, nothing sent
                rig.plane.probe("owner", "alibaba-01")
        r = _admin_client(rig.plane).post("/api/admin/ai/slots/alibaba-01/probe")  # (the test client itself uses httpx)
        self.assertEqual(r.status_code, 409)
        self.assertNotIn("alibaba-01", built, "no provider (so no HTTP client) is ever constructed for a gated slot")
        self.assertEqual(rig.provs["alibaba-01"].calls, 0)

    def test_the_real_adapter_never_sends_a_request_while_the_gate_is_closed(self) -> None:
        """Same, with the REAL `AlibabaModelStudioProvider` behind the real builder: the transport must stay untouched."""
        from server.ai_assistant.control.providers import default_builder
        rig = Rig(gate=False).configure()
        rig.plane.factory = ProviderFactory(builder=lambda s, k: default_builder(s, k) if s.provider_type == "alibaba"
                                            else rig.provs[s.slot_id])
        with mock.patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("a network call was attempted")):
            self.assertEqual(served(rig.turn("general")), ["gemini-01"])
            self.assertEqual(served(rig.turn("writer")), ["gemini-01"])

    def test_each_switch_alone_silences_alibaba_and_gemini_never_notices(self) -> None:
        for label, kw in (("gate", dict(gate=False)), ("type flag", {}), ("slot flag", {}), ("kill switch", {})):
            with self.subTest(label):
                rig = Rig(**kw).configure()
                if label == "type flag":
                    rig.plane.set_provider_type("owner", "alibaba", False)
                if label == "slot flag":
                    rig.plane.update_slot("owner", "alibaba-01", {"enabled": False})
                if label == "kill switch":
                    rig.plane.update_controls("owner", {"ai_enabled": False})
                rig.plane.invalidate()
                events = rig.turn("general")
                self.assertEqual(rig.provs["alibaba-01"].calls, 0)
                if label == "kill switch":
                    self.assertEqual(served(events), [], "the global kill switch stops EVERY provider")
                else:
                    self.assertEqual(served(events), ["gemini-01"])

    def test_the_kill_switch_beats_an_open_gate_an_enabled_slot_and_an_alibaba_first_profile(self) -> None:
        rig = Rig(gate=True).configure()
        self.assertEqual(served(rig.turn("general")), ["alibaba-01"], "sanity: everything on, Alibaba is first")
        rig.plane.update_controls("owner", {"ai_enabled": False})
        rig.plane.invalidate()
        calls = rig.provs["alibaba-01"].calls
        self.assertEqual(served(rig.turn("general")), [])
        self.assertEqual(rig.provs["alibaba-01"].calls, calls)

    def test_removing_alibaba_state_leaves_gemini_exactly_as_it_was(self) -> None:
        rig = Rig().configure()
        before = rig.plane.update_profile("owner", "FREE_FIRST", ["gemini-01", "gemini-02"], True)  # drop the route
        self.assertEqual(before["steps"], ["gemini-01", "gemini-02"])
        self.assertEqual(rig.plane.snapshot().ext.stale_routes, ())
        rig.plane.update_profile("owner", "WRITER", ["azure_openai", "gemini"], True)
        rig.plane.delete_slot("owner", "alibaba-01")
        self.assertNotIn("alibaba-01", rig.plane.snapshot().slots)
        self.assertEqual({r["kind"] for r in rig.fake.cols.get(T_EXT, {}).values()}, set(), "no route or slot rows are left behind")
        old_release_view(rig.fake)

    def test_a_slot_that_a_route_still_uses_cannot_be_deleted(self) -> None:
        rig = Rig().configure()
        with self.assertRaises(ControlConflict):
            rig.plane.delete_slot("owner", "alibaba-01")
        self.assertIn("alibaba-01", rig.plane.snapshot().slots)

    def test_alibaba_can_never_be_the_only_route_of_a_profile(self) -> None:
        rig = Rig().configure()
        for steps in (["alibaba-01"], ["alibaba"], ["alibaba", "alibaba-01"]):
            with self.assertRaises(ConfigValidationError, msg=steps):
                rig.plane.update_profile("owner", "STORY", steps, True)
        self.assertEqual(rig.plane.snapshot().profiles["STORY"].steps, DEFAULT_PROFILE_STEPS["STORY"])


# ================================================================== malformed alibaba configuration


def _ext_rows(rig: Rig) -> Dict[str, Dict[str, Any]]:
    return rig.fake.cols.setdefault(T_EXT, {})


def _slot_row(slot_id: str = "alibaba-02", **over: Any) -> Dict[str, Any]:
    s = a_slot(slot_id)
    d = {**slot_to_dict(s), **{k: v for k, v in over.items() if k not in ("kind", "key", "data_json")}}
    return {"$id": "s-" + slot_id, "kind": over.get("kind", "slot"), "key": over.get("key", slot_id),
            "data_json": over.get("data_json", json.dumps(d))}


class TestMalformedAlibabaConfiguration(unittest.TestCase):
    #: (label, row) — each is something that must cost only itself.
    BAD_ROWS = [
        ("not json", _slot_row(data_json="{not json")),
        ("json but not an object", _slot_row(data_json="[1, 2]")),
        ("empty payload", _slot_row(data_json="")),
        ("unknown kind", _slot_row(kind="mystery")),
        ("a Gemini slot hiding in the partition", _slot_row(provider_type="gemini", secret_ref="GEMINI_X")),
        ("key does not match the slot id", _slot_row(key="alibaba-99")),
        ("non-boolean enabled", _slot_row(enabled="yes")),
        ("route for a profile that does not exist", {"$id": "r-NOPE", "kind": "route", "key": "NOPE",
                                                     "data_json": json.dumps({"steps": ["gemini"]})}),
        ("route steps not a list", {"$id": "r-WRITER", "kind": "route", "key": "WRITER",
                                    "data_json": json.dumps({"steps": "gemini"})}),
        ("route steps not strings", {"$id": "r-WRITER", "kind": "route", "key": "WRITER",
                                     "data_json": json.dumps({"steps": [1, 2]})}),
        ("route too long", {"$id": "r-WRITER", "kind": "route", "key": "WRITER",
                            "data_json": json.dumps({"steps": ["gemini"] * 40})}),
    ]

    def _assert_gemini_unaffected(self, rig: Rig) -> None:
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertEqual(rig.plane.state, "ok", "a broken Alibaba partition is never a corrupt configuration")
        self.assertTrue(rig.plane.enabled(), "AI stays ON")
        self.assertEqual(cfg.profiles["FREE_FIRST"].steps, DEFAULT_PROFILE_STEPS["FREE_FIRST"], "Gemini's profile is untouched")
        self.assertEqual(served(rig.turn("general")), ["gemini-01"])
        self.assertEqual(served(rig.turn("support")), ["gemini-01"])
        old_release_view(rig.fake)  # and a rollback still works

    def test_every_kind_of_bad_row_costs_only_that_row(self) -> None:
        for label, row in self.BAD_ROWS:
            with self.subTest(label):
                rig = Rig().configure(alibaba=False)
                _ext_rows(rig)[row["$id"]] = row
                self._assert_gemini_unaffected(rig)
                ext = rig.plane.snapshot().ext
                self.assertEqual(ext.unreadable, 1, "counted, never echoed")
                self.assertEqual(rig.plane.snapshot().slots.keys() & {"alibaba-02", "alibaba-99"}, set())

    def test_bad_rows_do_not_hide_the_good_ones_next_to_them(self) -> None:
        rig = Rig().configure()
        for i, (_label, row) in enumerate(self.BAD_ROWS[:4]):
            _ext_rows(rig)[f"bad-{i}"] = {**row, "$id": f"bad-{i}"}
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertIn("alibaba-01", cfg.slots)
        self.assertEqual(cfg.profiles["FREE_FIRST"].steps, ("alibaba-01", "gemini-01", "gemini-02"))
        self.assertEqual(cfg.ext.unreadable, 4)
        self.assertEqual(served(rig.turn("general")), ["alibaba-01"], "the good Alibaba slot keeps working")

    def test_a_readable_but_invalid_slot_is_parked_not_routed_not_probed(self) -> None:
        rig = Rig().configure()
        bad = a_slot("alibaba-02", endpoint="https://evil.example.com/v1", enabled=True)  # outside the DashScope allowlist
        _ext_rows(rig)["s-alibaba-02"] = {"$id": "s-alibaba-02", "kind": "slot", "key": "alibaba-02",
                                          "data_json": json.dumps(slot_to_dict(bad))}
        rig.provs["alibaba-02"] = Scripted("alibaba-02")
        rig.plane.secrets = SecretResolver(env_for(*rig.gem, rig.ali, bad))
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertTrue(cfg.slots["alibaba-02"].meta_corrupt, "parked")
        self.assertIsNotNone(rig.plane.skip_reason(cfg.slots["alibaba-02"], "general", 10, cfg=cfg))
        with self.assertRaises(ControlConflict):
            rig.plane.probe("owner", "alibaba-02")
        self.assertEqual(rig.provs["alibaba-02"].calls, 0)
        self.assertEqual(rig.plane.state, "ok")
        health = next(s["health"] for s in rig.plane.config_view()["slots"] if s["slot_id"] == "alibaba-02")
        self.assertEqual(health["status"], "META_CORRUPT")
        # the owner repairs it from /admin/ai: a valid edit overwrites the row and un-parks it
        rig.plane.update_slot("owner", "alibaba-02", {"endpoint": BASE})
        self.assertFalse(rig.plane.snapshot().slots["alibaba-02"].meta_corrupt)

    def test_a_route_that_names_a_slot_that_does_not_exist_is_dropped_not_fatal(self) -> None:
        rig = Rig().configure(alibaba=False)
        rig.store.save_profile(RoutingProfile("FREE_FIRST", ("gemini-01", "gemini-02")), stamp=STAMP)  # a stored legacy row
        # a route carrying the CORRECT stamp, so only its content can make it stale
        _ext_rows(rig)["r-FREE_FIRST"] = {"$id": "r-FREE_FIRST", "kind": "route", "key": "FREE_FIRST",
                                          "data_json": json.dumps({"steps": ["ghost-slot", "gemini-01", "gemini-02"],
                                                                   "stamp": STAMP})}
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertEqual(rig.plane.state, "ok")
        self.assertEqual(cfg.profiles["FREE_FIRST"].steps, ("gemini-01", "gemini-02"))
        self.assertEqual(served(rig.turn("general")), ["gemini-01"])
        self.assertEqual(cfg.ext.stale_routes, ("FREE_FIRST",))

    def test_a_route_that_disagrees_with_the_legacy_profile_is_dropped(self) -> None:
        rig = Rig().configure()
        row = _ext_rows(rig)["r-FREE_FIRST"]
        row["data_json"] = json.dumps({**json.loads(row["data_json"]), "steps": ["alibaba-01", "gemini-02", "gemini-01"]})
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertEqual(cfg.profiles["FREE_FIRST"].steps, ("gemini-01", "gemini-02"))
        self.assertEqual(cfg.ext.stale_routes, ("FREE_FIRST",))
        notes = rig.plane.config_view()["isolated_store"]["notices"]
        self.assertEqual(len(notes), 1)
        self.assertIn("FREE_FIRST", notes[0])
        self.assertIn("bước Alibaba bị bỏ", notes[0])

    def test_unreadable_rows_are_reported_as_a_count_never_as_content(self) -> None:
        rig = Rig().configure(alibaba=False)
        secret_looking = "sk-" + "A1b2C3" * 6
        _ext_rows(rig)["bad-0"] = {"$id": "bad-0", "kind": "slot", "key": "alibaba-02", "data_json": "{" + secret_looking}
        rig.plane.invalidate()
        view = rig.plane.config_view()["isolated_store"]
        self.assertEqual(view["unreadable"], 1)
        self.assertNotIn(secret_looking, json.dumps(view), "a broken row is counted, its content is never echoed")
        self.assertIn("1 dòng", view["notices"][0])

    def test_the_partition_missing_unreachable_or_unparseable_never_touches_gemini(self) -> None:
        class Down(_Writes):
            def __call__(self, request: httpx.Request) -> httpx.Response:
                if "/collections/ai_alibaba_config/" in request.url.path:
                    return httpx.Response(503, json={"message": "busy"})
                return super().__call__(request)

        class Refused(_Writes):
            def __call__(self, request: httpx.Request) -> httpx.Response:
                if "/collections/ai_alibaba_config/" in request.url.path:
                    return httpx.Response(401, json={"message": "missing scope"})
                return super().__call__(request)

        for label, fake, expected in (("collection missing (pre-migration)", _NoExtCollection(), "schema_missing"),
                                      ("503", Down(), "unavailable"), ("401", Refused(), "unavailable")):
            with self.subTest(label):
                rig = Rig(fake).configure(alibaba=False)
                self._assert_gemini_unaffected(rig)
                self.assertEqual(rig.plane.snapshot().ext.state, expected)
                view = rig.plane.config_view()["isolated_store"]
                self.assertEqual(view["state"], expected)
                self.assertEqual(len(view["notices"]), 1, "the owner is told, in one sentence")
                self.assertIn("Gemini không bị ảnh hưởng", view["notices"][0])
                self.assertEqual(rig.plane.overview()["isolated_store"], view)
        with self.subTest("a parser bug"):
            rig = Rig().configure()
            with mock.patch("server.ai_assistant.control.store.parse_ext_rows", side_effect=RuntimeError("bug")):
                rig.plane.invalidate()
                self.assertEqual(rig.plane.snapshot().ext.state, "unavailable")
                self.assertEqual(rig.plane.state, "ok")
                self.assertEqual(served(rig.turn("general")), ["gemini-01"])
        with self.subTest("a store whose load_ext blows up for any reason"):
            class Exploding(InMemoryControlStore):
                def load_ext(self) -> ExtPartition:
                    raise RuntimeError("boom")
            st = Exploding()
            st.controls = GlobalControls(ai_enabled=True, provider_types=dict(ALL_TYPES_ON), version=1)
            st.slots["gemini-01"] = slot("gemini-01")
            p = ControlPlane(st, secrets=SecretResolver(env_for(slot("gemini-01"))),
                             factory=ProviderFactory(builder=lambda s, k: Scripted(s.slot_id)))
            self.assertEqual(served(list(ControlledGateway(p).stream(turns(), mode="general"))), ["gemini-01"])
            self.assertEqual(p.state, "ok")

    def test_with_the_partition_down_a_gemini_edit_works_and_an_alibaba_edit_fails_cleanly(self) -> None:
        class Down(_Writes):
            down = False

            def __call__(self, request: httpx.Request) -> httpx.Response:
                if self.down and "/collections/ai_alibaba_config/" in request.url.path:
                    return httpx.Response(503, json={"message": "busy"})
                return super().__call__(request)

        fake = Down()
        rig = Rig(fake).configure()
        fake.down = True
        rig.plane.invalidate()
        out = rig.plane.update_profile("owner", "STORY", ["gemini-02", "gemini-01"], True)  # a Gemini-only edit
        self.assertEqual(out["steps"], ["gemini-02", "gemini-01"])
        legacy_row = json.loads(fake.cols[T_PROFILES]["STORY"]["steps_json"])
        # An Alibaba edit needs the partition: refused with a clear reason, and NOTHING changed — by slot id and by type step.
        with self.assertRaises(ControlConflict) as ctx:
            rig.plane.update_profile("owner", "STORY", ["alibaba-01", "gemini-01"], True)
        self.assertIn("ai_alibaba_config", str(ctx.exception))
        with self.assertRaises(ControlStoreUnavailable):
            rig.plane.update_profile("owner", "STORY", ["alibaba", "gemini-01"], True)
        self.assertEqual(json.loads(fake.cols[T_PROFILES]["STORY"]["steps_json"]), legacy_row, "the legacy row was not touched")

    def test_a_missing_collection_is_a_clean_409_not_a_silent_no_op_write(self) -> None:
        rig = Rig(_NoExtCollection())
        rig.store.save_controls(GlobalControls(ai_enabled=True, provider_types=dict(ALL_TYPES_ON), version=1))
        r = _admin_client(rig.plane).post("/api/admin/ai/slots", json={
            "slot_id": "alibaba-01", "provider_type": "alibaba", "label": "A", "secret_ref": "ALIBABA_ALIBABA_01",
            "model": "m", "endpoint": BASE, "workloads": ["general"]})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["code"], "ai_admin_schema_outdated")
        self.assertIn("ai_alibaba_config", r.json()["detail"]["message"])
        self.assertEqual(rig.fake.cols.get(T_SLOTS, {}), {}, "and nothing leaked into the legacy collection")

    def test_an_alibaba_row_found_in_a_legacy_collection_is_ignored_and_counted(self) -> None:
        """A hand edit (or an early draft) put an Alibaba row where the old release reads. New code ignores it, so it is never
        routed and never makes the config corrupt."""
        rig = Rig().configure(alibaba=False)
        rig.fake.cols[T_SLOTS]["alibaba-01"] = {
            "$id": "alibaba-01", "slot_id": "alibaba-01", "provider_type": "alibaba", "label": "A", "secret_ref": "ALIBABA_A",
            "model": "m", "enabled": True, "endpoint": BASE, "priority": 1, "weight": 10, "workloads_json": '["general"]'}
        rig.fake.cols[T_PROFILES]["WRITER"] = {"$id": "WRITER", "name": "WRITER", "enabled": True,
                                               "steps_json": json.dumps(["alibaba", "alibaba-01", "gemini-01"])}
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertEqual(rig.plane.state, "ok")
        self.assertNotIn("alibaba-01", cfg.slots)
        self.assertEqual(cfg.profiles["WRITER"].steps, ("gemini-01",))
        self.assertEqual(cfg.ext.unreadable, 2)
        self.assertEqual(served(rig.turn("writer")), ["gemini-01"])

    def test_a_bad_row_in_the_LEGACY_collections_still_fails_closed_exactly_as_before(self) -> None:
        """We relaxed nothing about the legacy partition: Gemini's own config is validated as strictly as it ever was."""
        rig = Rig().configure(alibaba=False)
        rig.fake.cols[T_SLOTS]["gemini-02"]["provider_type"] = "not-a-provider"
        rig.plane.invalidate()
        rig.plane.snapshot()
        self.assertEqual(rig.plane.state, "corrupt")
        self.assertFalse(rig.plane.enabled())

    def test_the_payload_limit_is_enforced_before_a_write(self) -> None:
        rig = Rig().configure(alibaba=False)
        huge = a_slot("alibaba-77", label="x" * 60, model="m" * 120, endpoint=BASE + "/" + "p" * 150)
        rig.store.save_ext_slot(huge)  # the largest legal slot fits
        self.assertLess(len(rig.fake.cols[T_EXT]["s-alibaba-77"]["data_json"]), EXT_DATA_MAX)
        with self.assertRaises(ValueError):
            rig.store.save_ext_route("WRITER", tuple("s" * 27 for _ in range(12)) + ("x" * 4000,), stamp=STAMP)

    def test_parse_ext_rows_itself_never_raises(self) -> None:
        junk: List[Dict[str, Any]] = [{}, {"kind": None}, {"kind": "slot", "key": "k", "data_json": None},
                                      {"kind": "slot", "key": 5, "data_json": "{}"}, {"data_json": "\x00"}]
        got = parse_ext_rows(junk)
        self.assertEqual((got.slots, got.routes, got.unreadable, got.state), ({}, {}, 5, "ok"))
        self.assertEqual(parse_ext_rows([]).state, "empty")


# ================================================================== gemini-only operation


class TestGeminiOnlyOperation(unittest.TestCase):
    MODES = ("general", "story", "writer", "support")

    def _outcomes(self, rig: Rig) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for m in self.MODES:
            rig.plane.invalidate()
            plan = rig.plane.plan(rig.plane.snapshot(), mode=m, workload=m)
            out[m] = ([(s.slot_id, why) for s, why in plan], served(rig.turn(m)))
        return out

    def test_gemini_routing_is_identical_with_every_kind_of_alibaba_partition(self) -> None:
        baseline = self._outcomes(Rig().configure(alibaba=False))

        class Down(_Writes):
            def __call__(self, request: httpx.Request) -> httpx.Response:
                if "/collections/ai_alibaba_config/" in request.url.path:
                    return httpx.Response(503, json={})
                return super().__call__(request)

        variants = {
            "no collection (production before the migration)": Rig(_NoExtCollection()).configure(alibaba=False),
            "collection unreachable": Rig(Down()).configure(alibaba=False),
            "empty collection": Rig().configure(alibaba=False),
            "gate open, nothing configured": Rig(gate=True).configure(alibaba=False),
        }
        garbage = Rig().configure(alibaba=False)
        for i, (_, row) in enumerate(TestMalformedAlibabaConfiguration.BAD_ROWS):
            _ext_rows(garbage)[f"junk-{i}"] = {**row, "$id": f"junk-{i}"}
        variants["a partition full of garbage rows"] = garbage
        # An Alibaba slot present but silenced (gate closed): still no change to Gemini's plan or the served slot.
        silenced = Rig(gate=False).configure(alibaba=True)
        silenced.plane.update_profile("owner", "FREE_FIRST", ["gemini-01", "gemini-02"], True)
        silenced.plane.update_profile("owner", "WRITER", ["azure_openai", "gemini"], True)
        variants["slot persisted, gate closed, no route"] = silenced
        for label, rig in variants.items():
            with self.subTest(label):
                got = self._outcomes(rig)
                for m in self.MODES:
                    gem_only = [(sid, why) for sid, why in got[m][0] if sid.startswith("gemini")]
                    self.assertEqual(gem_only, baseline[m][0], m)
                    self.assertEqual(got[m][1], baseline[m][1], m)

    def test_the_legacy_collections_see_the_same_requests_with_or_without_alibaba_data(self) -> None:
        rig_a, rig_b = Rig().configure(alibaba=False), Rig().configure(alibaba=True)
        seen_a: List[str] = []
        seen_b: List[str] = []
        for rig, seen in ((rig_a, seen_a), (rig_b, seen_b)):
            orig = rig.fake.__call__

            def spy(request: httpx.Request, orig=orig, seen=seen) -> httpx.Response:
                if request.method == "GET" and "/collections/ai_alibaba_config/" not in request.url.path:
                    seen.append(request.url.path.split("/collections/")[1].split("/")[0])
                return orig(request)
            rig.store._client = httpx.Client(transport=httpx.MockTransport(spy))  # noqa: SLF001
            rig.plane.invalidate()
            rig.plane.snapshot()
        self.assertEqual(sorted(seen_a), sorted(seen_b), "reading the Alibaba partition adds requests ONLY to its own collection")

    def test_user_facing_responses_are_unchanged_when_the_partition_is_missing_or_broken(self) -> None:
        for fault in ("schema_missing", "unavailable"):
            with self.subTest(fault):
                w = World(slots=2, global_cap=500, prio={"gemini-01": 10, "gemini-02": 20})
                w.store.ext_fault = fault
                w.plane.invalidate()
                cid, r = w.ask("alice", "xin chào")
                self.assertEqual(r.status_code, 200, r.text)
                self.assertTrue(ev(r, "delta") and ev(r, "done"))
                self.assertEqual(w.per_slot(), {"gemini-01": 1})
                av = w.avail("alice")
                self.assertTrue(av["enabled"])
                self.assertNotIn("alibaba", json.dumps(av).lower())

    def test_default_profiles_route_gemini_only_configs_exactly_as_the_old_defaults_did(self) -> None:
        """Retiring `qwen` from the defaults changes nothing for a deployment without a qwen slot (production has none)."""
        for qwen_gate in (False, True):
            gem = [slot("gemini-01", priority=10), slot("gemini-02", priority=20)]
            old_defaults = {n: RoutingProfile(n, s) for n, s in LEGACY_QWEN_PROFILE_STEPS.items()}
            results = []
            for profiles in (None, old_defaults):
                st = InMemoryControlStore()
                st.controls = GlobalControls(ai_enabled=True, provider_types=dict(ALL_TYPES_ON), version=1)
                for s in gem:
                    st.slots[s.slot_id] = s
                for p in (profiles or {}).values():
                    st.profiles[p.name] = p
                p = ControlPlane(st, secrets=SecretResolver(env_for(*gem)), qwen_legacy_enabled=qwen_gate, rng=random.Random(3),
                                 factory=ProviderFactory(builder=lambda s, k: Scripted(s.slot_id)))
                row = {}
                for m in list(DEFAULT_MODE_PROFILES) + ["web_search"]:
                    row[m] = [(s.slot_id, why) for s, why in p.plan(p.snapshot(), mode=m if m != "web_search" else "general",
                                                                    workload=m)]
                results.append(row)
            self.assertEqual(results[0], results[1], f"qwen_gate={qwen_gate}")


# ================================================================== the legacy qwen path is retired, and independent


class TestLegacyQwenRetired(unittest.TestCase):
    def test_the_rollback_table_is_exactly_what_production_ran_before_the_retirement(self) -> None:
        self.assertEqual({k: tuple(v) for k, v in old_model.DEFAULT_PROFILE_STEPS.items()}, LEGACY_QWEN_PROFILE_STEPS,
                         "LEGACY_QWEN_PROFILE_STEPS is the frozen production default, step for step")
        for name, steps in DEFAULT_PROFILE_STEPS.items():
            self.assertEqual(steps, tuple(s for s in LEGACY_QWEN_PROFILE_STEPS[name] if s != "qwen"),
                             f"{name}: the new default is the old default minus qwen — nothing else moved")
            self.assertNotIn("qwen", steps)
            self.assertNotIn("alibaba", steps)

    def test_the_two_gates_are_independent_in_both_directions(self) -> None:
        self.assertEqual(GATED_PROVIDER_TYPES, {"alibaba": "FAS_AI_ALIBABA_ENABLED", "qwen": "FAS_AI_QWEN_LEGACY_ENABLED"})
        self.assertEqual(len(set(GATED_PROVIDER_TYPES.values())), 2)
        both_off = ControlPlane(InMemoryControlStore())
        self.assertFalse(both_off.gate_open("alibaba") or both_off.gate_open("qwen"))
        only_alibaba = ControlPlane(InMemoryControlStore(), alibaba_enabled=True)
        self.assertTrue(only_alibaba.gate_open("alibaba"))
        self.assertFalse(only_alibaba.gate_open("qwen"), "FAS_AI_ALIBABA_ENABLED=1 must not wake the legacy qwen path")
        only_qwen = ControlPlane(InMemoryControlStore(), qwen_legacy_enabled=True)
        self.assertTrue(only_qwen.gate_open("qwen"))
        self.assertFalse(only_qwen.gate_open("alibaba"), "…and the legacy switch does not open Model Studio")
        self.assertTrue(only_alibaba.gate_open("gemini") and only_alibaba.gate_open("azure_openai"), "Gemini etc. are never gated")

    def test_the_environment_variables_are_separate_and_lenient(self) -> None:
        from server.config import _ai_assistant_settings
        cases = [({"FAS_AI_ALIBABA_ENABLED": "1"}, True, False), ({"FAS_AI_QWEN_LEGACY_ENABLED": "1"}, False, True),
                 ({"FAS_AI_ALIBABA_ENABLED": "1", "FAS_AI_QWEN_LEGACY_ENABLED": "1"}, True, True),
                 ({"FAS_AI_QWEN_LEGACY_ENABLED": "tru"}, False, False), ({}, False, False)]
        for env, ali, qw in cases:
            with self.subTest(env=env):
                with mock.patch.dict(os.environ, env, clear=False):
                    for name in ("FAS_AI_ALIBABA_ENABLED", "FAS_AI_QWEN_LEGACY_ENABLED"):
                        if name not in env:
                            os.environ.pop(name, None)
                    s = _ai_assistant_settings()
                    self.assertIs(s.alibaba_enabled, ali)
                    self.assertIs(s.qwen_legacy_enabled, qw)

    def test_the_control_plane_is_built_with_each_gate_from_its_own_setting(self) -> None:
        from server.ai_assistant.control import build_control_plane
        from server.config import AiAssistantSettings

        class S:
            data_backend = "mock"
            ai_assistant = AiAssistantSettings(admin_v1=True, alibaba_enabled=True)
        p = build_control_plane(S())
        self.assertTrue(p.gate_open("alibaba"))
        self.assertFalse(p.gate_open("qwen"))
        S.ai_assistant = AiAssistantSettings(admin_v1=True, qwen_legacy_enabled=True)
        p = build_control_plane(S())
        self.assertTrue(p.gate_open("qwen"))
        self.assertFalse(p.gate_open("alibaba"))

    def test_a_qwen_slot_is_not_woken_by_the_alibaba_gate_and_the_defaults_never_reach_it(self) -> None:
        q, g = slot("qwen-01", "qwen", priority=1), slot("gemini-01", priority=50)
        for alibaba_gate in (False, True):
            provs = {"qwen-01": Scripted("qwen-01"), "gemini-01": Scripted("gemini-01")}
            st = InMemoryControlStore()
            st.controls = GlobalControls(ai_enabled=True, provider_types=dict(ALL_TYPES_ON), version=1)
            st.slots.update({"qwen-01": q, "gemini-01": g})
            # even with an explicit legacy profile (qwen first), the alibaba gate does nothing for it
            st.profiles["SUPPORT_SAFE"] = RoutingProfile("SUPPORT_SAFE", LEGACY_QWEN_PROFILE_STEPS["SUPPORT_SAFE"])
            p = ControlPlane(st, secrets=SecretResolver(env_for(q, g)), alibaba_enabled=alibaba_gate,
                             factory=ProviderFactory(builder=lambda s, k, provs=provs: provs[s.slot_id]))
            events = list(ControlledGateway(p).stream(turns(), mode="support"))
            self.assertEqual(p.skip_reason(q, "support", 10), SKIP_GATE_CLOSED, f"alibaba_gate={alibaba_gate}")
            self.assertEqual(served(events), ["gemini-01"])
            self.assertEqual(provs["qwen-01"].calls, 0)
            with self.assertRaises(ProviderError):
                p.provider_for(q, FAKE_KEY)

    def test_the_rollback_path_works_end_to_end_gate_plus_explicit_steps(self) -> None:
        q, g = slot("qwen-01", "qwen", priority=1), slot("gemini-01", priority=50)
        provs = {"qwen-01": Scripted("qwen-01"), "gemini-01": Scripted("gemini-01")}
        st = InMemoryControlStore()
        st.controls = GlobalControls(ai_enabled=True, provider_types=dict(ALL_TYPES_ON), version=1)
        st.slots.update({"qwen-01": q, "gemini-01": g})

        def plane(qwen_gate: bool) -> ControlPlane:
            return ControlPlane(st, secrets=SecretResolver(env_for(q, g)), qwen_legacy_enabled=qwen_gate, rng=random.Random(1),
                                factory=ProviderFactory(builder=lambda s, k: provs[s.slot_id]))

        # 1. gate open but the DEFAULT profiles: qwen is retired, nothing routes to it
        p = plane(True)
        self.assertEqual(served(list(ControlledGateway(p).stream(turns(), mode="writer"))), ["gemini-01"])
        # 2. the owner restores the legacy order through the normal, validated admin path…
        for name, steps in LEGACY_QWEN_PROFILE_STEPS.items():
            p.update_profile("owner", name, list(steps), True)
        p.invalidate()
        # 3. …and with the gate closed it STILL does not run (the switch is the safety)
        closed = plane(False)
        self.assertEqual(served(list(ControlledGateway(closed).stream(turns(), mode="writer"))), ["gemini-01"])
        self.assertEqual(provs["qwen-01"].calls, 0)
        # 4. gate + steps = the old behaviour is back
        self.assertEqual(served(list(ControlledGateway(p).stream(turns(), mode="writer"))), ["qwen-01"])
        self.assertEqual(provs["qwen-01"].models, ["qwen-model"])

    def test_persisted_qwen_steps_and_slots_from_before_the_retirement_still_load(self) -> None:
        rig = Rig().configure(alibaba=False)
        rig.fake.cols[T_PROFILES]["WRITER"] = {"$id": "WRITER", "name": "WRITER", "enabled": True,
                                               "steps_json": json.dumps(["qwen", "azure_openai", "gemini"])}
        rig.store.save_slot(slot("qwen-01", "qwen"))
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertEqual(rig.plane.state, "ok")
        self.assertEqual(cfg.profiles["WRITER"].steps, ("qwen", "azure_openai", "gemini"))
        self.assertIn("qwen-01", cfg.slots)
        old_release_view(rig.fake)  # and the previous release is happy with it too (qwen is one of ITS types)

    def test_the_legacy_env_chain_follows_the_qwen_gate_only(self) -> None:
        from server.ai_assistant.runtime import build_ai_runtime
        from server.config import AiAssistantSettings, Settings
        for alibaba_gate, qwen_gate in ((False, False), (True, False), (False, True), (True, True)):
            ai = AiAssistantSettings(enabled=True, providers=("qwen",), qwen_api_key=FAKE_KEY, audience="all",
                                     alibaba_enabled=alibaba_gate, qwen_legacy_enabled=qwen_gate)
            rt = build_ai_runtime(replace(Settings(), ai_assistant=ai))
            self.assertEqual(rt.enabled, qwen_gate, f"alibaba={alibaba_gate} qwen={qwen_gate}")
            if not qwen_gate:
                self.assertEqual(rt.reason, "no_provider")

    def test_the_admin_sees_two_distinct_gates(self) -> None:
        p = ControlPlane(InMemoryControlStore(), alibaba_enabled=True)
        ov = p.overview()["gates"]
        self.assertEqual(ov, {"alibaba": {"env": "FAS_AI_ALIBABA_ENABLED", "open": True},
                              "qwen": {"env": "FAS_AI_QWEN_LEGACY_ENABLED", "open": False}})


# ================================================================== second-round review findings


class _Switchable(_Writes):
    """Fake Appwrite whose ext collection / profile collection / ext deletes can be broken on demand."""

    def __init__(self) -> None:
        super().__init__()
        self.ext_down = False        # GET/PATCH/POST/DELETE on ai_alibaba_config -> 503
        self.ext_delete_down = False  # only DELETE on ai_alibaba_config -> 503
        self.profiles_down = False   # PATCH/POST on ai_routing_profiles -> 503
        self.dead_after_ext_write = False  # once an ext write happened, EVERYTHING fails
        self._ext_writes = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        in_ext = "/collections/ai_alibaba_config/" in path
        if self.dead_after_ext_write and self._ext_writes:
            return httpx.Response(503, json={"message": "busy"})
        if in_ext and (self.ext_down or (self.ext_delete_down and request.method == "DELETE")):
            return httpx.Response(503, json={"message": "busy"})
        if self.profiles_down and request.method in ("PATCH", "POST") and "/collections/ai_routing_profiles/" in path:
            return httpx.Response(503, json={"message": "busy"})
        if in_ext and request.method in ("PATCH", "POST"):
            self._ext_writes += 1
        return super().__call__(request)


class TestSecondRoundReviewFindings(unittest.TestCase):
    # ---- finding 1: a step resolves exactly as the router resolves it ----
    def test_a_slot_named_like_a_provider_type_never_changes_how_steps_split(self) -> None:
        ali_named_gemini = a_slot("gemini")  # what a hostile/careless row could claim
        self.assertFalse(is_ext_step("gemini", {"gemini": ali_named_gemini}), "a TYPE name is resolved as the type, like router.plan")
        self.assertTrue(is_ext_step("alibaba", {}))
        self.assertFalse(is_ext_step("groq", {"groq": a_slot("groq")}))
        self.assertEqual(split_steps(("azure_openai", "gemini"), {"gemini": ali_named_gemini}),
                         (("azure_openai", "gemini"), ()), "Gemini stays in the legacy-visible profile")

    def test_such_a_slot_cannot_be_created_and_a_row_claiming_it_is_unreadable(self) -> None:
        rig = Rig().configure(alibaba=False)
        for bad_id in ("gemini", "qwen", "groq", "alibaba", "azure_openai"):
            with self.assertRaises(ConfigValidationError, msg=bad_id) as ctx:
                rig.plane.create_slot("owner", {**slot_to_dict(a_slot("alibaba-77")), "slot_id": bad_id,
                                                "secret_ref": "ALIBABA_X77", "enabled": False})
            self.assertEqual(ctx.exception.errors[0]["field"], "slot_id")
            _ext_rows(rig)["s-" + bad_id] = _slot_row(bad_id)  # a well-formed Alibaba slot row that merely uses a type name
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertEqual(cfg.ext.unreadable, 5, "all five hostile rows were refused")
        self.assertFalse({"gemini", "qwen", "groq", "alibaba", "azure_openai"} & set(cfg.slots) - {"gemini-01", "gemini-02"})
        self.assertEqual(rig.plane.update_profile("owner", "WEB_SEARCH", ["gemini"], True)["steps"], ["gemini"],
                         "WEB_SEARCH = [gemini] stays saveable (it used to be misread as 'Alibaba only')")

    # ---- finding 2 / 4 (+ cross-family #2): a removed or half-written Alibaba step can never come back ----
    def test_a_failed_route_delete_cannot_keep_or_resurrect_a_removed_alibaba_step(self) -> None:
        fake = _Switchable()
        rig = Rig(fake).configure()
        self.assertEqual(rig.plane.snapshot().profiles["WRITER"].steps, ("alibaba", "azure_openai", "gemini"))
        fake.ext_delete_down = True  # the owner removes the Alibaba step but the route row cannot be deleted
        out = rig.plane.update_profile("owner", "WRITER", ["azure_openai", "gemini"], True)  # legacy steps do NOT change
        self.assertEqual(out["steps"], ["azure_openai", "gemini"])
        fake.ext_delete_down = False
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertEqual(cfg.profiles["WRITER"].steps, ("azure_openai", "gemini"), "the operator's removal is honoured")
        self.assertEqual(cfg.ext.stale_routes, ("WRITER",), "…and the orphan row is reported")

    def test_two_gemini_edits_during_an_outage_cannot_resurrect_the_old_route(self) -> None:
        fake = _Switchable()
        rig = Rig(fake).configure()
        fake.ext_down = True
        rig.plane.invalidate()
        rig.plane.update_profile("owner", "FREE_FIRST", ["gemini-02", "gemini-01"], True)
        rig.plane.update_profile("owner", "FREE_FIRST", ["gemini-01", "gemini-02"], True)  # back to the route's own base
        fake.ext_down = False
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertEqual(cfg.profiles["FREE_FIRST"].steps, ("gemini-01", "gemini-02"), "no Alibaba step the owner removed")
        self.assertEqual(cfg.ext.stale_routes, ("FREE_FIRST",))
        self.assertEqual(served(rig.turn("general")), ["gemini-01"])

    def test_the_old_release_editing_back_to_the_same_steps_also_orphans_the_route(self) -> None:
        from server.config import AppwriteSettings
        rig = Rig().configure()
        aw = AppwriteSettings(endpoint="https://appwrite.example/v1", project_id="p", api_key="k", database_id="db")
        old = old_store.AppwriteControlStore(aw, client=httpx.Client(transport=httpx.MockTransport(rig.fake)))
        with mock.patch.object(old_store, "now_iso", return_value="2031-01-01T00:00:00+00:00"):
            old.save_profile(old_model.RoutingProfile("FREE_FIRST", ("gemini-01", "gemini-02")))  # SAME steps as the base
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertEqual(cfg.profiles["FREE_FIRST"].steps, ("gemini-01", "gemini-02"))
        self.assertEqual(cfg.ext.stale_routes, ("FREE_FIRST",), "the old release re-saved the profile: the route is no longer ours")

    def test_a_failure_between_the_two_writes_restores_the_previous_route(self) -> None:
        fake = _Switchable()
        rig = Rig(fake).configure()
        before = rig.plane.snapshot().profiles["FREE_FIRST"].steps
        fake.profiles_down = True
        with self.assertRaises(ControlStoreUnavailable):
            rig.plane.update_profile("owner", "FREE_FIRST", ["gemini-01", "alibaba-01", "gemini-02"], True)
        fake.profiles_down = False
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertEqual(cfg.profiles["FREE_FIRST"].steps, before, "the error left the previous (valid) state in place")
        self.assertEqual(cfg.ext.stale_routes, ())

    def test_if_even_the_restore_fails_the_half_written_route_is_not_applied(self) -> None:
        fake = _Switchable()
        rig = Rig(fake).configure()
        fake.profiles_down = True
        fake._ext_writes = 0  # noqa: SLF001 — count from here: the route write succeeds, then EVERYTHING (profile write + restore) fails
        fake.dead_after_ext_write = True
        with self.assertRaises(ControlStoreUnavailable):
            rig.plane.update_profile("owner", "FREE_FIRST", ["gemini-01", "alibaba-01", "gemini-02"], True)
        fake.profiles_down = False
        fake.dead_after_ext_write = False
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        # The new route's legacy projection equals the stored steps, yet it must NOT apply: it was never stamped onto the row.
        self.assertEqual(cfg.profiles["FREE_FIRST"].steps, ("gemini-01", "gemini-02"))
        self.assertEqual(cfg.ext.stale_routes, ("FREE_FIRST",))
        old_release_view(rig.fake)

    def test_two_edits_in_the_same_second_still_get_different_stamps(self) -> None:
        rig = Rig().configure()
        fixed = "2036-01-01T00:00:00+00:00"
        with mock.patch("server.ai_assistant.control.service.now_iso", return_value=fixed):
            rig.plane.update_profile("owner", "STORY", ["gemini-01", "alibaba-01", "gemini-02"], True)
            first = rig.fake.cols[T_PROFILES]["STORY"]["updated_at"]
            rig.plane.update_profile("owner", "STORY", ["gemini-01", "gemini-02"], True)
            second = rig.fake.cols[T_PROFILES]["STORY"]["updated_at"]
        self.assertEqual(first, fixed)
        self.assertGreater(second, first, "the stamp is strictly increasing, even inside one second")

    # ---- finding 3: ids and pages ----
    def test_a_row_whose_document_id_disagrees_with_its_key_is_a_shadow_and_is_ignored(self) -> None:
        rig = Rig().configure()
        genuine = _ext_rows(rig)["s-alibaba-01"]
        _ext_rows(rig)["s-zzz"] = {**genuine, "$id": "s-zzz"}  # claims key alibaba-01, lives under another id
        _ext_rows(rig)["r-STORY"] = {"$id": "r-STORY", "kind": "route", "key": "WRITER",
                                     "data_json": json.dumps({"steps": ["alibaba", "gemini"], "stamp": STAMP})}
        rig.plane.invalidate()
        cfg = rig.plane.snapshot()
        self.assertEqual(cfg.ext.unreadable, 2)
        self.assertIn("alibaba-01", cfg.slots)
        # the API's delete/disable address the REAL row, which is the only one that counts
        rig.plane.update_slot("owner", "alibaba-01", {"enabled": False})
        rig.plane.invalidate()
        self.assertFalse(rig.plane.snapshot().slots["alibaba-01"].enabled)

    def test_a_full_page_of_rows_is_treated_as_degraded_not_silently_truncated(self) -> None:
        rig = Rig().configure(alibaba=False)
        for i in range(100):
            _ext_rows(rig)[f"junk-{i}"] = {"$id": f"junk-{i}", "kind": "slot", "key": f"k{i}", "data_json": "{}"}
        rig.plane.invalidate()
        self.assertEqual(rig.plane.snapshot().ext.state, "unavailable")
        self.assertEqual(rig.plane.state, "ok")
        self.assertEqual(served(rig.turn("general")), ["gemini-01"])

    # ---- finding 5: caps per partition, and no blind overwrite ----
    def test_slot_caps_are_per_partition(self) -> None:
        from server.tests.test_ai_alibaba_control_plane import build_plane
        from server.ai_assistant.control.model import MAX_EXT_SLOTS
        slots = [a_slot(f"alibaba-{i:02d}", enabled=False) for i in range(MAX_EXT_SLOTS)] + [slot("gemini-01")]
        p = build_plane(slots)
        with self.assertRaises(ConfigValidationError):
            p.create_slot("owner", {**slot_to_dict(a_slot("alibaba-99")), "enabled": False})
        out = p.create_slot("owner", {**slot_to_dict(slot("gemini-02")), "enabled": False})  # Alibaba slots do not use up Gemini's room
        self.assertEqual(out["slot_id"], "gemini-02")

    def test_creating_an_alibaba_slot_needs_a_readable_partition(self) -> None:
        st = InMemoryControlStore()
        st.controls = GlobalControls(ai_enabled=True, provider_types=dict(ALL_TYPES_ON), version=1)
        body = {**slot_to_dict(a_slot("alibaba-01")), "enabled": False}
        st.ext_fault = "unavailable"
        p = ControlPlane(st)
        with self.assertRaises(ControlConflict):
            p.create_slot("owner", body)
        self.assertEqual(st.ext_rows, {}, "nothing was written blind")
        st.ext_fault = "schema_missing"
        with self.assertRaises(ControlSchemaOutdated):
            p.create_slot("owner", body)

    def test_a_create_race_409_is_retried_as_an_update(self) -> None:
        class Racy(_FakeAppwrite):
            posts = 0

            def __call__(self, request: httpx.Request) -> httpx.Response:
                if "/collections/ai_alibaba_config/" in request.url.path:
                    if request.method == "PATCH" and not self.cols.get(T_EXT, {}).get("s-alibaba-01"):
                        return httpx.Response(404, json={})
                    if request.method == "POST":
                        Racy.posts += 1
                        # another instance created the row in between
                        self.cols.setdefault(T_EXT, {})["s-alibaba-01"] = {"$id": "s-alibaba-01", "kind": "slot",
                                                                           "key": "alibaba-01", "data_json": "{}"}
                        return httpx.Response(409, json={"message": "exists"})
                return super().__call__(request)

        st, fake = _appwrite_store(Racy())
        st.save_ext_slot(a_slot())  # no exception: the 409 became a PATCH
        self.assertEqual(Racy.posts, 1)
        self.assertIn('"alibaba-01"', fake.cols[T_EXT]["s-alibaba-01"]["data_json"])


# ================================================================== the in-memory store behaves like Appwrite


class TestInMemoryPartition(unittest.TestCase):
    def test_round_trip_and_fault_hooks(self) -> None:
        st = InMemoryControlStore()
        self.assertEqual(st.load_ext().state, "empty")
        st.save_ext_slot(a_slot())
        st.save_ext_route("WRITER", ("alibaba", "gemini"), stamp=STAMP)
        ext = st.load_ext()
        self.assertEqual((ext.state, sorted(ext.slots), ext.routes),
                         ("ok", ["alibaba-01"], {"WRITER": ExtRoute(("alibaba", "gemini"), STAMP)}))
        st.delete_ext_route("WRITER")
        st.delete_ext_slot("alibaba-01")
        self.assertEqual(st.load_ext().state, "empty")
        st.ext_fault = "schema_missing"
        with self.assertRaises(ControlSchemaOutdated):
            st.save_ext_slot(a_slot())
        self.assertEqual(st.load_ext().state, "schema_missing")


if __name__ == "__main__":
    unittest.main()
