"""
Alibaba Model Studio inside the AI control plane — what must hold BEFORE any canary:

  * production compatibility: Gemini behaviour, the Appwrite payload of a Gemini slot, and a config written by the previous
    release (6 provider types, no `meta_json`) are untouched;
  * NO Alibaba request unless explicitly enabled: server gate, type flag, slot flag and a routing profile must all say yes;
    the global kill switch still applies; no Gemini -> Alibaba fallback exists in the default profiles;
  * capability tiers, free-quota metadata (+ the dormant "prefer expiring free quota" ordering), provider-side quota wall,
    TTFT/latency accounting, probe through stream, admin API shape, and no provider/model metadata for ordinary clients.

Everything is deterministic: fake providers, fake clocks, `httpx.MockTransport`. No network, no real key, no Alibaba quota.
"""
from __future__ import annotations

import json
import os
import random
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional
from unittest import mock

import httpx

from server.ai_assistant.control import build_control_plane
from server.ai_assistant.control.admin_routes import build_ai_admin_router
from server.ai_assistant.control.capability import (
    free_quota_block_reason, free_quota_state, order_by_expiring_free_quota, serves_tier, tier_map,
)
from server.ai_assistant.control.model import (
    CAPABILITY_TIERS, CHAT_TIERS, DEFAULT_PROFILE_STEPS, PROVIDER_TYPES, ConfigValidationError, ControlConfig,
    GlobalControls, ProviderSlot, RoutingProfile, default_profiles, slot_from_dict, slot_meta, validate_config,
    validate_controls, validate_slot,
)
from server.ai_assistant.control.providers import ProviderFactory
from server.ai_assistant.control.router import (
    SKIP_FREE_QUOTA_EXHAUSTED, SKIP_FREE_QUOTA_EXPIRED, SKIP_FREE_QUOTA_STALE, SKIP_GATE_CLOSED, SKIP_META_CORRUPT,
    SKIP_QUOTA_EXHAUSTED, SKIP_SLOT_DISABLED, SKIP_TIER, SKIP_TYPE_DISABLED, ControlledGateway, exhausted_event,
)
from server.ai_assistant.control.secrets import SecretResolver
from server.ai_assistant.control.service import ControlConflict, ControlPlane, today_utc
from server.ai_assistant.control.store import (
    AppwriteControlStore, ControlSchemaOutdated, ControlStoreUnavailable, InMemoryControlStore,
)
from server.ai_assistant.gateway import ErrorEvent, ProviderServed
from server.llm_gateway.chat_provider import (
    ChatProvider, ChatTurn, Delta, Done, GenerateRequest, GenerateResult, ProviderCapabilities, ProviderError,
    ProviderUsageSnapshot, UsageEvent,
)
from server.llm_gateway.usage_limits import CircuitBreaker
from server.tests.test_ai_control_plane import FAKE_KEY, Clock, Scripted, _FakeAppwrite, env_for, slot, turns
from server.tests.test_ai_e2e_regression import Prov, World, detail, ev

BASE = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
LEGACY_TYPES = ("gemini", "groq", "workers_ai", "qwen", "azure_openai", "openrouter")
LEAK = "LEAKMARKER-" + "q7x" * 4
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
#: Exactly the attributes `AppwriteControlStore.save_slot` wrote BEFORE Alibaba support — production's schema has these and no more.
LEGACY_SLOT_KEYS = {"slot_id", "provider_type", "label", "secret_ref", "model", "enabled", "endpoint", "api_version",
                    "priority", "weight", "daily_request_cap", "daily_token_cap", "rpm_soft_cap", "tpm_soft_cap",
                    "workloads_json", "price_in_micro_per_mtok", "price_out_micro_per_mtok", "updated_at"}


def a_slot(slot_id: str = "alibaba-01", **kw: Any) -> ProviderSlot:
    base: Dict[str, Any] = dict(
        slot_id=slot_id, provider_type="alibaba", label=slot_id.upper(), secret_ref="ALIBABA_" + slot_id.upper().replace("-", "_"),
        model="model-from-owner", enabled=True, endpoint=BASE, workloads=("general", "story", "writer", "support"))
    base.update(kw)
    return ProviderSlot(**base)


class StreamProbeProvider(Scripted):
    """A fake that opts into `probe_via_stream` like the real adapter, and can advance a fake clock."""

    probe_via_stream = True

    def __init__(self, name: str, *, clock: Optional[Clock] = None, ttft_s: float = 0.0, total_s: float = 0.0,
                 fail: Optional[ProviderError] = None) -> None:
        super().__init__(name, fail=fail)
        self.clock, self.ttft_s, self.total_s = clock, ttft_s, total_s
        self.generate_calls = 0

    def generate(self, req: GenerateRequest) -> GenerateResult:  # a stream-probe must NOT come here
        self.generate_calls += 1
        raise AssertionError("probe must go through stream()")

    def stream(self, req: GenerateRequest) -> Iterator[Any]:
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        if self.clock:
            self.clock.t += self.ttft_s
        yield Delta(text="OK")
        if self.clock:
            self.clock.t += max(0.0, self.total_s - self.ttft_s)
        yield UsageEvent(input_tokens=7, output_tokens=2)
        yield Done()


def build_plane(slots: List[ProviderSlot], *, gate: bool = True, alibaba_type: Optional[bool] = True,
                profiles: Optional[Dict[str, RoutingProfile]] = None, providers: Optional[Dict[str, ChatProvider]] = None,
                prefer: bool = False, clock: Optional[Clock] = None, ai_enabled: bool = True,
                store: Optional[InMemoryControlStore] = None, wall_now=lambda: NOW) -> ControlPlane:
    st = store or InMemoryControlStore()
    types: Dict[str, bool] = {t: True for t in LEGACY_TYPES}  # the previous release's 6 keys…
    if alibaba_type is not None:
        types["alibaba"] = alibaba_type  # …plus (optionally) the new one
    st.controls = GlobalControls(ai_enabled=ai_enabled, provider_types=types, version=1)
    for s in slots:
        st.slots[s.slot_id] = s
    for p in (profiles or {}).values():
        st.profiles[p.name] = p
    provs = providers if providers is not None else {s.slot_id: Scripted(s.slot_id) for s in slots}
    clk = clock or Clock()
    return ControlPlane(st, secrets=SecretResolver(env_for(*slots)), factory=ProviderFactory(builder=lambda s, k: provs[s.slot_id]),
                        breaker=CircuitBreaker(clock_fn=clk), clock=clk, rng=random.Random(5), alibaba_enabled=gate,
                        prefer_free_quota=prefer, wall_now=wall_now)


def only(*steps: str) -> Dict[str, RoutingProfile]:
    return {"FREE_FIRST": RoutingProfile("FREE_FIRST", tuple(steps))}


def go(plane: ControlPlane, tier: Optional[str] = None) -> List[Any]:
    return list(ControlledGateway(plane).stream(turns(), mode="general", tier=tier))


def served(events: List[Any]) -> List[str]:
    return [e.provider_name for e in events if isinstance(e, ProviderServed)]


# ================================================================== production compatibility


class TestProductionCompatibility(unittest.TestCase):
    def test_a_config_written_by_the_previous_release_stays_valid_and_alibaba_is_off(self) -> None:
        six = {t: True for t in LEGACY_TYPES}
        validate_controls(GlobalControls(ai_enabled=True, provider_types=six))  # a 6-key dict is NOT corrupt
        with self.assertRaises(ConfigValidationError):
            validate_controls(GlobalControls(provider_types={**six, "nonsense": True}))
        with self.assertRaises(ConfigValidationError):
            validate_controls(GlobalControls(provider_types={**six, "gemini": "yes"}))  # type: ignore[dict-item]

    def test_default_profiles_never_route_to_alibaba(self) -> None:
        for name, steps in DEFAULT_PROFILE_STEPS.items():
            self.assertNotIn("alibaba", steps, name)
        self.assertNotIn("alibaba", {s for p in default_profiles().values() for s in p.steps})

    def test_new_type_exists_and_is_off_by_default(self) -> None:
        self.assertIn("alibaba", PROVIDER_TYPES)
        self.assertFalse(GlobalControls().provider_types["alibaba"])

    def test_stored_controls_without_the_new_key_load_with_alibaba_off(self) -> None:
        st, fake = _appwrite_store()
        fake.cols["ai_control_settings"] = {"global": {
            "$id": "global", "ai_enabled": True, "provider_types_json": json.dumps({t: t == "gemini" for t in LEGACY_TYPES}),
            "mode_profiles_json": json.dumps({"general": "FREE_FIRST", "story": "STORY", "writer": "WRITER",
                                              "support": "SUPPORT_SAFE"}),
            "global_daily_request_cap": 150, "global_daily_token_cap": 450000, "per_user_daily_request_cap": 5,
            "per_user_daily_token_cap": 15000, "max_output_tokens": 400, "max_context_tokens": 4000, "version": 7}}
        cfg = st.load()
        validate_config(cfg)
        self.assertTrue(cfg.controls.ai_enabled)
        self.assertEqual(cfg.controls.provider_types["alibaba"], False)
        self.assertTrue(cfg.controls.provider_types["gemini"])

    def test_a_gemini_slot_is_written_with_exactly_the_attributes_production_already_has(self) -> None:
        rec = _Recorder()
        st = _appwrite_store(rec)[0]
        st.save_slot(slot("gemini-01"))
        st.save_slot(replace(slot("gemini-02"), enabled=False, weight=20))  # an emergency toggle of one slot
        for body in rec.writes:
            self.assertEqual(set(body["data"]) if "data" in body else set(), LEGACY_SLOT_KEYS)
            self.assertNotIn("meta_json", body["data"])

    def test_meta_json_is_written_only_when_there_is_metadata_and_cleared_explicitly(self) -> None:
        rec = _Recorder()
        st = _appwrite_store(rec)[0]
        plain = slot("gemini-01")
        st.save_slot(plain)
        with_meta = replace(plain, tiers=("FAST",), free_quota_remaining=1000, free_quota_only=True)
        st.save_slot(with_meta)
        self.assertEqual(json.loads(rec.writes[-1]["data"]["meta_json"]),
                         {"tiers": ["FAST"], "free_quota_remaining": 1000, "free_quota_only": True})
        st.save_slot(plain)  # nothing to say: the stored value is NOT touched…
        self.assertNotIn("meta_json", rec.writes[-1]["data"])
        self.assertEqual(st.load().slots["gemini-01"].tiers, ("FAST",))
        st.save_slot(plain, clear_meta=True)  # …unless the service asks to clear it
        self.assertEqual(rec.writes[-1]["data"]["meta_json"], "")
        loaded = st.load().slots["gemini-01"]
        self.assertEqual((loaded.tiers, loaded.free_quota_remaining, loaded.free_quota_only), ((), None, False))

    def test_every_attribute_this_release_can_write_is_in_the_schema_spec(self) -> None:
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[2] / "scripts" / "setup_appwrite.py"
        spec = importlib.util.spec_from_file_location("setup_appwrite_alibaba_contract", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        attrs = {a[0]: a for a in mod.SCHEMA["ai_provider_slots"]["attributes"]}
        rec = _Recorder()
        st = _appwrite_store(rec)[0]
        st.save_slot(a_slot(tiers=("FAST", "SMART"), free_quota_remaining=5, free_quota_expires_at="2026-12-31T00:00:00+00:00",
                            free_quota_only=True, free_quota_updated_at="2026-10-02T00:00:00+00:00"))
        written = set(rec.writes[-1]["data"])
        self.assertLessEqual(written, set(attrs), f"missing from schema: {written - set(attrs)}")
        self.assertLessEqual(set(PROVIDER_TYPES), set(attrs["provider_type"][3]), "the enum must know every provider type")
        self.assertLess(len(rec.writes[-1]["data"]["meta_json"]), attrs["meta_json"][3], "meta_json fits its attribute size")

    def test_a_corrupt_meta_row_parks_only_that_slot_and_never_breaks_the_config(self) -> None:
        for bad in ("{not json", "[1,2]", json.dumps({"tiers": "FAST"}), json.dumps({"tiers": ["NOPE"]}),
                    json.dumps({"free_quota_remaining": -5}), json.dumps({"free_quota_expires_at": "not a date"}),
                    json.dumps({"free_quota_only": True}),  # a free-only lock without a balance is inconsistent
                    json.dumps({"free_quota_remaining": True})):
            with self.subTest(meta=bad):
                st, fake = _appwrite_store()
                st.save_slot(slot("gemini-01"))
                st.save_slot(a_slot())
                fake.cols["ai_provider_slots"]["alibaba-01"]["meta_json"] = bad
                cfg = st.load()
                validate_config(cfg)  # the WHOLE config is still valid: Gemini keeps serving
                self.assertTrue(cfg.slots["alibaba-01"].meta_corrupt)
                self.assertFalse(cfg.slots["gemini-01"].meta_corrupt)
                p = build_plane([], store=_with(cfg))
                p.secrets = SecretResolver(env_for(*cfg.slots.values()))
                live = p.snapshot()  # the plane's own (validated) view: types on, gate open
                self.assertEqual(p.skip_reason(live.slots["alibaba-01"], "general", 10, cfg=live), SKIP_META_CORRUPT)
                self.assertIsNone(p.skip_reason(live.slots["gemini-01"], "general", 10, cfg=live))

    def test_a_store_that_refuses_the_new_schema_says_so_and_only_for_new_things(self) -> None:
        st, _ = _appwrite_store(_Rejecting())
        for s in (a_slot(), replace(slot("gemini-01"), tiers=("FAST",))):
            with self.assertRaises(ControlSchemaOutdated) as ctx:
                st.save_slot(s)
            self.assertIn("migration", str(ctx.exception))
        with self.assertRaises(ControlStoreUnavailable) as ctx2:  # a plain Gemini slot refused with 400 is NOT "outdated schema"
            _appwrite_store(_Rejecting(always=True))[0].save_slot(slot("gemini-01"))
        self.assertNotIsInstance(ctx2.exception, ControlSchemaOutdated)

    def test_gemini_routing_is_identical_with_the_new_type_present(self) -> None:
        g1, g2 = slot("gemini-01", priority=10), slot("gemini-02", priority=20)
        for with_alibaba in (False, True):
            slots = [g1, g2] + ([a_slot(priority=1)] if with_alibaba else [])
            p = build_plane(slots, gate=False, profiles=only("gemini"))
            self.assertEqual([s.slot_id for s, why in p.plan(p.snapshot(), mode="general", workload="general") if why is None],
                             ["gemini-01", "gemini-02"])
            self.assertEqual(served(go(p)), ["gemini-01"])


# ================================================================== nothing runs unless explicitly enabled


class TestExplicitEnablement(unittest.TestCase):
    def _call_count(self, p: ControlPlane, slot_id: str) -> int:
        return p.factory.cached(slot_id).calls if p.factory.cached(slot_id) else 0

    def test_gate_closed_means_no_request_even_with_everything_else_enabled(self) -> None:
        a, g = a_slot(priority=1), slot("gemini-01", priority=50)
        provs = {"alibaba-01": Scripted("alibaba-01"), "gemini-01": Scripted("gemini-01")}
        p = build_plane([a, g], gate=False, profiles=only("alibaba", "gemini"), providers=provs)
        self.assertEqual(p.skip_reason(a, "general", 10), SKIP_GATE_CLOSED)
        self.assertEqual(served(go(p)), ["gemini-01"])
        self.assertEqual(provs["alibaba-01"].calls, 0)
        with self.assertRaises(ProviderError) as ctx:
            p.provider_for(a, FAKE_KEY)
        self.assertEqual(ctx.exception.code, "provider_gate_closed")
        health = next(s["health"] for s in p.config_view()["slots"] if s["slot_id"] == "alibaba-01")
        self.assertEqual(health["status"], "GATE_CLOSED")
        self.assertEqual(health["gate"], {"env": "FAS_AI_ALIBABA_ENABLED", "open": False})

    def test_gate_closed_stays_closed_when_gemini_fails_there_is_no_fallback(self) -> None:
        a = a_slot()
        g = slot("gemini-01")
        provs = {"alibaba-01": Scripted("alibaba-01"),
                 "gemini-01": Scripted("gemini-01", fail=ProviderError("x", code="provider_http_503"))}
        p = build_plane([a, g], gate=False, profiles=only("gemini", "alibaba"), providers=provs)
        events = go(p)
        self.assertEqual(provs["alibaba-01"].calls, 0)
        self.assertEqual([e.code for e in events if isinstance(e, ErrorEvent)], ["ai_provider_unavailable"])

    def test_the_legacy_qwen_type_is_also_alibaba_and_shares_the_gate(self) -> None:
        """`qwen` (DashScope) predates this work and sits in the DEFAULT profiles (SUPPORT_SAFE = azure > qwen > gemini …).
        Without the shared gate, enabling one qwen slot would put Alibaba ahead of / behind Gemini in live traffic."""
        q, g = slot("qwen-01", "qwen", priority=1), slot("gemini-01", priority=50)
        for gate_open in (False, True):
            provs = {"qwen-01": Scripted("qwen-01"), "gemini-01": Scripted("gemini-01")}
            p = build_plane([q, g], gate=gate_open, providers=provs)  # DEFAULT profiles, qwen type flag ON
            events = list(ControlledGateway(p).stream(turns(), mode="support"))
            if gate_open:  # documents WHY the gate exists: the shipped default profile prefers qwen once it is reachable
                self.assertEqual(served(events), ["qwen-01"])
            else:
                self.assertEqual(p.skip_reason(q, "support", 10), SKIP_GATE_CLOSED)
                self.assertEqual(served(events), ["gemini-01"])
                self.assertEqual(provs["qwen-01"].calls, 0)
                with self.assertRaises(ProviderError):
                    p.provider_for(q, FAKE_KEY)
        self.assertEqual({t for t in PROVIDER_TYPES if not build_plane([], gate=False).gate_open(t)}, {"alibaba", "qwen"},
                         "exactly the two Alibaba types are gated; Gemini and the rest are never affected")

    def test_the_legacy_env_chain_for_qwen_goes_through_the_same_gate(self) -> None:
        """With `FAS_AI_ADMIN_V1` off the chat uses `FAS_AI_PROVIDERS=qwen,…` + `AI_QWEN_API_KEY`: DashScope again."""
        from server.ai_assistant.runtime import build_ai_runtime
        from server.config import AiAssistantSettings, Settings
        for gate_open in (False, True):
            ai = AiAssistantSettings(enabled=True, providers=("qwen",), qwen_api_key=FAKE_KEY, audience="all",
                                     alibaba_enabled=gate_open)
            rt = build_ai_runtime(replace(Settings(), ai_assistant=ai))
            self.assertEqual(rt.enabled, gate_open, f"gate_open={gate_open}")
            if not gate_open:
                self.assertEqual(rt.reason, "no_provider")

    def test_every_other_switch_also_blocks(self) -> None:
        a = a_slot()
        cases = [("slot off", build_plane([replace(a, enabled=False)], profiles=only("alibaba")), SKIP_SLOT_DISABLED),
                 ("type off", build_plane([a], alibaba_type=False, profiles=only("alibaba")), SKIP_TYPE_DISABLED),
                 ("type missing (old config)", build_plane([a], alibaba_type=None, profiles=only("alibaba")), SKIP_TYPE_DISABLED)]
        for label, p, reason in cases:
            with self.subTest(label):
                self.assertEqual(p.skip_reason(a if "slot off" not in label else replace(a, enabled=False), "general", 10), reason)
                self.assertEqual(served(go(p)), [])

    def test_not_in_any_profile_means_no_traffic_even_with_all_switches_on(self) -> None:
        provs = {"alibaba-01": Scripted("alibaba-01"), "gemini-01": Scripted("gemini-01")}
        p = build_plane([a_slot(), slot("gemini-01")], providers=provs)  # DEFAULT profiles: no alibaba step
        for mode in ("general", "story", "writer", "support"):
            events = list(ControlledGateway(p).stream(turns(), mode=mode))
            self.assertNotIn("alibaba-01", served(events), mode)
        self.assertEqual(provs["alibaba-01"].calls, 0)

    def test_when_explicitly_routed_it_serves_first_or_as_a_fallback(self) -> None:
        provs = {"alibaba-01": Scripted("alibaba-01"), "gemini-01": Scripted("gemini-01")}
        p = build_plane([a_slot(priority=1), slot("gemini-01", priority=50)], profiles=only("alibaba", "gemini"), providers=provs)
        self.assertEqual(served(go(p)), ["alibaba-01"])
        provs2 = {"alibaba-01": Scripted("alibaba-01"),
                  "gemini-01": Scripted("gemini-01", fail=ProviderError("x", code="provider_http_500"))}
        p2 = build_plane([a_slot(), slot("gemini-01")], profiles=only("gemini", "alibaba"), providers=provs2)
        self.assertEqual(served(go(p2)), ["alibaba-01"])

    def test_the_global_kill_switch_still_applies(self) -> None:
        provs = {"alibaba-01": Scripted("alibaba-01")}
        p = build_plane([a_slot()], profiles=only("alibaba"), providers=provs, ai_enabled=False)
        self.assertEqual(go(p), [ErrorEvent(code="ai_no_provider", message="Chưa có nhà cung cấp AI nào khả dụng.")])
        self.assertEqual(provs["alibaba-01"].calls, 0)

    def test_a_probe_with_the_gate_closed_sends_nothing_and_is_not_counted(self) -> None:
        prov = StreamProbeProvider("alibaba-01")
        p = build_plane([a_slot(enabled=False)], gate=False, providers={"alibaba-01": prov})
        with self.assertRaises(ControlConflict) as ctx:
            p.probe("owner", "alibaba-01")
        self.assertIn("FAS_AI_ALIBABA_ENABLED", str(ctx.exception))
        self.assertEqual((prov.calls, prov.generate_calls), (0, 0))
        self.assertEqual(p.probe_view("alibaba-01")["probes_today"]["count"], 0)

    def test_new_alibaba_slots_are_created_disabled_and_validated(self) -> None:
        p = build_plane([], profiles=only("gemini"))
        body = dict(slot_id="alibaba-01", provider_type="alibaba", label="A", secret_ref="ALIBABA_ONE", model="m-1", endpoint=BASE,
                    workloads=["general"])
        with self.assertRaises(ConfigValidationError) as ctx:
            p.create_slot("owner", {**body, "enabled": True})
        self.assertEqual([e["field"] for e in ctx.exception.errors], ["enabled"])
        created = p.create_slot("owner", body)
        self.assertFalse(created["enabled"])
        bad = {"endpoint": "https://evil.example.com/compatible-mode/v1", "secret_ref": "GEMINI_ONE", "model": "bad model"}
        with self.assertRaises(ConfigValidationError) as ctx2:
            p.create_slot("owner", {**body, "slot_id": "alibaba-02", **bad})
        self.assertEqual({e["field"] for e in ctx2.exception.errors}, {"endpoint", "secret_ref", "model"})
        with self.assertRaises(ConfigValidationError) as ctx3:  # no endpoint: the region is the owner's to state
            p.create_slot("owner", {**body, "slot_id": "alibaba-03", "endpoint": ""})
        self.assertEqual([e["field"] for e in ctx3.exception.errors], ["endpoint"])
        p.update_slot("owner", "alibaba-01", {"enabled": True})  # enabling later is a separate, audited step
        fields = [(a["entity"], a["field"], a["new_value"]) for a in p.audit(50)]
        self.assertIn(("slot:alibaba-01", "enabled", "true"), fields)

    def test_the_gate_variable_is_read_leniently_and_defaults_closed(self) -> None:
        from server.config import _ai_assistant_settings
        for raw, expected in ((None, False), ("", False), ("0", False), ("flase", False), ("maybe", False), ("1", True),
                              ("true", True), ("ON", True), (" yes ", True)):
            env = {} if raw is None else {"FAS_AI_ALIBABA_ENABLED": raw}
            with mock.patch.dict(os.environ, env, clear=False):
                if raw is None:
                    os.environ.pop("FAS_AI_ALIBABA_ENABLED", None)
                self.assertIs(_ai_assistant_settings().alibaba_enabled, expected, raw)
        with mock.patch.dict(os.environ, {"FAS_AI_PREFER_FREE_QUOTA": "oops"}):
            self.assertIs(_ai_assistant_settings().prefer_free_quota, False)

    def test_build_control_plane_passes_the_gate_from_settings(self) -> None:
        from server.config import AiAssistantSettings

        class S:
            data_backend = "mock"
            ai_assistant = AiAssistantSettings(admin_v1=True, alibaba_enabled=True, prefer_free_quota=True)

        plane = build_control_plane(S())
        self.assertTrue(plane.gate_open("alibaba"))
        S.ai_assistant = AiAssistantSettings(admin_v1=True)
        self.assertFalse(build_control_plane(S()).gate_open("alibaba"))
        self.assertTrue(build_control_plane(S()).gate_open("gemini"), "types without a gate are never gated")


# ================================================================== capability tiers


class TestCapabilityTiers(unittest.TestCase):
    def test_tier_constants(self) -> None:
        self.assertEqual(CAPABILITY_TIERS, ("FAST", "SMART", "ADVANCED", "TRANSLATION", "VISION", "EMBEDDING"))
        self.assertNotIn("EMBEDDING", CHAT_TIERS)

    def test_validation_and_normalisation(self) -> None:
        validate_slot(a_slot(tiers=("FAST", "SMART")))
        self.assertEqual(slot_from_dict({**_dict(a_slot()), "tiers": ["fast", " smart "]}).tiers, ("FAST", "SMART"))
        for bad in (("NOPE",), ("FAST", "FAST"), (5,), (["FAST"],)):
            with self.subTest(bad=bad):
                with self.assertRaises(ConfigValidationError) as ctx:
                    validate_slot(replace(a_slot(), tiers=bad))  # type: ignore[arg-type]
                self.assertEqual([e["field"] for e in ctx.exception.errors], ["tiers"])

    def test_serving_rules(self) -> None:
        legacy, fast, emb = a_slot(), a_slot(tiers=("FAST",)), a_slot(tiers=("EMBEDDING",))
        self.assertTrue(serves_tier(legacy, None) and serves_tier(fast, None), "no tier asked: unclassified/chat slots serve")
        self.assertFalse(serves_tier(emb, None), "an embedding-only model never gets a chat request")
        self.assertTrue(serves_tier(fast, "FAST") and not serves_tier(fast, "SMART") and not serves_tier(legacy, "FAST"))

    def test_plan_without_a_tier_is_unchanged_and_with_a_tier_selects_only_declared_slots(self) -> None:
        fast, smart = a_slot("alibaba-fast", tiers=("FAST",)), a_slot("alibaba-smart", tiers=("SMART",), priority=60)
        g = slot("gemini-01", priority=70)
        p = build_plane([fast, smart, g], profiles=only("alibaba", "gemini"))
        eligible = lambda tier=None: [s.slot_id for s, why in p.plan(p.snapshot(), mode="general", workload="general", tier=tier) if why is None]  # noqa: E731
        self.assertEqual(eligible(), ["alibaba-fast", "alibaba-smart", "gemini-01"])
        self.assertEqual(eligible("SMART"), ["alibaba-smart"])
        self.assertEqual(eligible("FAST"), ["alibaba-fast"])
        self.assertEqual(eligible("VISION"), [])
        self.assertEqual(p.plan(p.snapshot(), mode="general", workload="general", tier="EMBEDDING"), [])
        self.assertEqual(p.plan(p.snapshot(), mode="general", workload="general", tier="NOPE"), [])
        reasons = {s.slot_id: why for s, why in p.plan(p.snapshot(), mode="general", workload="general", tier="SMART")}
        self.assertEqual(reasons["alibaba-fast"], SKIP_TIER)
        self.assertEqual(served(go(p, "SMART")), ["alibaba-smart"])

    def test_an_embedding_only_slot_is_skipped_for_chat(self) -> None:
        emb = a_slot(tiers=("EMBEDDING",))
        p = build_plane([emb], profiles=only("alibaba"))
        self.assertEqual(p.skip_reason(emb, "general", 10), SKIP_TIER)

    def test_capability_map_and_meta_for_the_admin(self) -> None:
        p = build_plane([a_slot("a-1", tiers=("FAST", "TRANSLATION")), a_slot("a-2", tiers=("FAST",)), slot("gemini-01")])
        cv = p.config_view()
        self.assertEqual(cv["capability_map"]["FAST"], ["a-1", "a-2"])
        self.assertEqual(cv["capability_map"]["TRANSLATION"], ["a-1"])
        self.assertEqual(cv["capability_map"]["VISION"], [])
        self.assertEqual(cv["meta"]["capability_tiers"], list(CAPABILITY_TIERS))
        self.assertEqual(tier_map(p.snapshot())["FAST"], ["a-1", "a-2"])

    def test_no_chat_route_asks_for_a_tier_yet(self) -> None:
        import inspect
        from server.ai_assistant import routes
        # The one gateway call of the chat route ends at `on_attempt=_note_attempt)`: no `tier=` argument is passed.
        self.assertIn("cancel=gateway_cancel.is_set, on_attempt=_note_attempt)", inspect.getsource(routes))


# ================================================================== free-quota metadata


def fq(slot_id: str = "alibaba-01", **kw: Any) -> ProviderSlot:
    return a_slot(slot_id, **kw)


class TestFreeQuotaMetadata(unittest.TestCase):
    def test_state_machine(self) -> None:
        cases = [({}, "none"),
                 ({"free_quota_remaining": 1000}, "active"),
                 ({"free_quota_remaining": 1000, "free_quota_expires_at": "2027-01-01T00:00:00+00:00"}, "active"),
                 ({"free_quota_remaining": 1000, "free_quota_expires_at": "2026-10-05T00:00:00+00:00"}, "expiring"),
                 ({"free_quota_remaining": 1000, "free_quota_expires_at": "2026-10-01T00:00:00+00:00"}, "expired"),
                 ({"free_quota_remaining": 0}, "exhausted"),
                 ({"free_quota_expires_at": "2026-12-31T00:00:00+00:00"}, "active")]
        for kw, expected in cases:
            with self.subTest(kw=kw):
                self.assertEqual(free_quota_state(fq(**kw), NOW)["state"], expected)
        st = free_quota_state(fq(free_quota_remaining=5, free_quota_expires_at="2026-10-05T00:00:00+00:00"), NOW)
        self.assertEqual((st["days_left"], st["remaining"], st["only"]), (2.5, 5, False))

    def test_validation(self) -> None:
        validate_slot(fq(free_quota_remaining=10, free_quota_expires_at="2026-12-31T00:00:00+00:00", free_quota_only=True))
        bad = [dict(free_quota_remaining=-1), dict(free_quota_remaining=10 ** 13), dict(free_quota_remaining=True),
               dict(free_quota_remaining=1.5), dict(free_quota_expires_at="2026-12-31T00:00:00"),  # naive time
               dict(free_quota_expires_at="tomorrow"), dict(free_quota_only=True)]  # a lock without a balance
        for kw in bad:
            with self.subTest(kw=kw):
                with self.assertRaises(ConfigValidationError):
                    validate_slot(fq(**kw))
        parsed = slot_from_dict({**_dict(fq()), "free_quota_remaining": "250000", "free_quota_expires_at": "2026-12-31T07:00:00+07:00"})
        self.assertEqual((parsed.free_quota_remaining, parsed.free_quota_expires_at), (250000, "2026-12-31T00:00:00+00:00"))
        self.assertIsNone(slot_from_dict({**_dict(fq()), "free_quota_remaining": ""}).free_quota_remaining)
        with self.assertRaises(ConfigValidationError):
            slot_from_dict({**_dict(fq()), "free_quota_only": "yes"})

    SNAP = dict(free_quota_only=True, free_quota_remaining=50_000, free_quota_expires_at="2026-12-31T00:00:00+00:00",
                free_quota_updated_at="2026-10-02T00:00:00+00:00")  # NOW = 2026-10-02 12:00Z

    def test_free_quota_only_is_a_hard_lock_against_paid_usage(self) -> None:
        base = self.SNAP
        with mock.patch("server.ai_assistant.control.service.today_utc", return_value="20261002"):
            p = build_plane([fq(**base)], profiles=only("alibaba"))
            self.assertIsNone(p.skip_reason(fq(**base), "general", 1000))
            self.assertEqual(p.skip_reason(fq(**{**base, "free_quota_expires_at": "2026-10-01T00:00:00+00:00"}), "general", 10),
                             SKIP_FREE_QUOTA_EXPIRED)
            self.assertEqual(p.skip_reason(fq(**{**base, "free_quota_remaining": 0}), "general", 10), SKIP_FREE_QUOTA_EXHAUSTED)
            self.assertEqual(p.skip_reason(fq(**{**base, "free_quota_remaining": 500}), "general", 1000), SKIP_FREE_QUOTA_EXHAUSTED,
                             "a request (+ the 5% reserve) that may not fit in the free quota would spill into paid usage")
            self.assertEqual(free_quota_block_reason(fq(**base), NOW, 10, consumed_tokens=0), None)
            events = go(build_plane([fq(**{**base, "free_quota_remaining": 0})], profiles=only("alibaba")))
            self.assertEqual([e.code for e in events if isinstance(e, ErrorEvent)], ["ai_budget_exhausted"])

    def test_free_quota_only_subtracts_what_the_slot_already_served_since_the_snapshot(self) -> None:
        """The snapshot is static; without this the 'lock' would let 10 M tokens through a 1 M balance."""
        snap = {**self.SNAP, "free_quota_updated_at": "2026-09-20T08:00:00+00:00"}  # taken on 20 Sept, today is 2 Oct
        s = fq(**snap)
        store = InMemoryControlStore()
        store.add_usage("alibaba-01", "20260925", input_tokens=30_000, output_tokens=10_000)  # a closed day inside the window
        store.add_usage("alibaba-01", "20260919", input_tokens=999_999)  # BEFORE the snapshot day: not counted
        store.add_usage("gemini-01", "20260926", input_tokens=999_999)  # another slot: not counted
        with mock.patch("server.ai_assistant.control.service.today_utc", return_value="20261002"):
            p = build_plane([s], profiles=only("alibaba"), store=store)
            store.add_usage("alibaba-01", "20261002", input_tokens=4_000)  # today (live counters)
            p.invalidate()
            # consumed 40 000 + 4 000 = 44 000; 50 000 - 44 000 - 2 500 (5% reserve) = 3 500 left
            self.assertIsNone(p.skip_reason(s, "general", 3_000, usage=p.usage_today()))
            self.assertEqual(p.skip_reason(s, "general", 4_000, usage=p.usage_today()), SKIP_FREE_QUOTA_EXHAUSTED)
            view = next(x["health"]["quota"] for x in p.config_view()["slots"] if x["slot_id"] == "alibaba-01")
            self.assertEqual((view["consumed_since_snapshot"], view["estimated_remaining"]), (44_000, 6_000))
            self.assertEqual(view["snapshot_age_days"], 12.2)

    def test_closed_days_are_read_once_and_only_for_free_quota_only_slots(self) -> None:
        reads: List[str] = []

        class Spy(InMemoryControlStore):
            def usage_for_day(self, day: str):  # type: ignore[override]
                reads.append(day)
                return super().usage_for_day(day)

        snap = {**self.SNAP, "free_quota_updated_at": "2026-09-30T00:00:00+00:00"}
        with mock.patch("server.ai_assistant.control.service.today_utc", return_value="20261002"):
            only_lock, plain = fq("a-lock", **snap), fq("a-plain", **{**snap, "free_quota_only": False})
            p = build_plane([only_lock, plain], profiles=only("alibaba"), store=Spy())
            p.skip_reason(plain, "general", 10, usage=p.usage_today())
            self.assertEqual([d for d in reads if d != "20261002"], [], "a slot without the lock never costs a ledger read")
            for _ in range(3):
                p.skip_reason(only_lock, "general", 10, usage=p.usage_today())
            self.assertEqual(sorted(d for d in reads if d != "20261002"), ["20260930", "20261001"],
                             "each closed day of the window is read exactly once")

    def test_free_quota_only_fails_closed_when_it_cannot_verify(self) -> None:
        class Flaky(InMemoryControlStore):
            def usage_for_day(self, day: str):  # type: ignore[override]
                if day == "20260930":
                    raise ControlStoreUnavailable("down")
                return super().usage_for_day(day)

        with mock.patch("server.ai_assistant.control.service.today_utc", return_value="20261002"):
            cases = [("old snapshot (> 31 days)", {**self.SNAP, "free_quota_updated_at": "2026-08-01T00:00:00+00:00"}, None),
                     ("no server stamp", {**self.SNAP, "free_quota_updated_at": ""}, None),
                     ("ledger day unreadable", {**self.SNAP, "free_quota_updated_at": "2026-09-30T00:00:00+00:00"}, Flaky())]
            for label, kw, st in cases:
                with self.subTest(label):
                    s = fq(**kw)
                    p = build_plane([s], profiles=only("alibaba"), store=st)
                    self.assertEqual(p.skip_reason(s, "general", 10, usage=p.usage_today()), SKIP_FREE_QUOTA_STALE)
                    self.assertEqual([e.code for e in go(p) if isinstance(e, ErrorEvent)], ["ai_budget_exhausted"])
            # …and a fresh-enough snapshot with a readable ledger is fine
            fresh = fq(**{**self.SNAP, "free_quota_updated_at": "2026-09-30T00:00:00+00:00"})
            p = build_plane([fresh], profiles=only("alibaba"))
            self.assertIsNone(p.skip_reason(fresh, "general", 10, usage=p.usage_today()))
            self.assertEqual(served(go(p)), ["alibaba-01"])

    def test_without_the_lock_the_metadata_is_informational_only(self) -> None:
        s = fq(free_quota_remaining=0, free_quota_expires_at="2026-10-01T00:00:00+00:00")  # expired AND empty, paid allowed
        p = build_plane([s], profiles=only("alibaba"))
        self.assertIsNone(p.skip_reason(s, "general", 10))
        self.assertEqual(served(go(p)), ["alibaba-01"])

    def test_the_server_stamps_the_snapshot_time_and_clients_cannot(self) -> None:
        p = build_plane([], profiles=only("gemini"))
        body = dict(slot_id="alibaba-01", provider_type="alibaba", label="A", secret_ref="ALIBABA_ONE", model="m", endpoint=BASE,
                    workloads=["general"], free_quota_remaining=1000, free_quota_updated_at="1999-01-01T00:00:00+00:00")
        created = p.create_slot("owner", body)
        self.assertNotEqual(created["free_quota_updated_at"], "1999-01-01T00:00:00+00:00")
        self.assertTrue(created["free_quota_updated_at"])
        stamp = created["free_quota_updated_at"]
        same = p.update_slot("owner", "alibaba-01", {"label": "B", "free_quota_updated_at": "2000-01-01T00:00:00+00:00"})
        self.assertEqual(same["free_quota_updated_at"], stamp, "unchanged balance keeps its stamp")
        cleared = p.update_slot("owner", "alibaba-01", {"free_quota_remaining": None})
        self.assertEqual(cleared["free_quota_updated_at"], "")
        self.assertIn("free_quota_remaining", {a["field"] for a in p.audit(50)}, "metadata changes are audited")

    def test_clearing_all_metadata_asks_the_store_to_clear_it(self) -> None:
        calls: List[bool] = []

        class Spy(InMemoryControlStore):
            def save_slot(self, s: ProviderSlot, *, clear_meta: bool = False) -> None:
                calls.append(clear_meta)
                super().save_slot(s, clear_meta=clear_meta)

        p = build_plane([fq(tiers=("FAST",))], profiles=only("alibaba"), store=Spy())
        p.update_slot("owner", "alibaba-01", {"label": "renamed"})
        p.update_slot("owner", "alibaba-01", {"tiers": []})
        p.update_slot("owner", "alibaba-01", {"label": "again"})
        self.assertEqual(calls, [False, True, False])

    def test_preferring_expiring_free_quota_is_implemented_but_dormant(self) -> None:
        soon = a_slot("a-soon", free_quota_remaining=900, free_quota_expires_at="2026-10-06T00:00:00+00:00")
        later = a_slot("a-later", free_quota_remaining=900, free_quota_expires_at="2026-12-31T00:00:00+00:00")
        none = a_slot("a-none")
        urgent_but_lower_priority = a_slot("a-low", priority=90, free_quota_remaining=900,
                                           free_quota_expires_at="2026-10-03T00:00:00+00:00")
        self.assertEqual([s.slot_id for s in order_by_expiring_free_quota([none, later, soon, urgent_but_lower_priority], NOW)],
                         ["a-soon", "a-later", "a-none", "a-low"], "free quota first, soonest expiry first, priority still dominates")
        slots = [soon, later, none]
        for prefer, first in ((False, None), (True, "a-soon")):
            p = build_plane(slots, profiles=only("alibaba"), prefer=prefer)
            order = [s.slot_id for s, why in p.plan(p.snapshot(), mode="general", workload="general") if why is None]
            if first:
                self.assertEqual(order[:2], ["a-soon", "a-later"])
            else:
                self.assertEqual(sorted(order), ["a-later", "a-none", "a-soon"])
        self.assertFalse(build_plane(slots).config_view()["meta"]["free_quota"]["prefer_expiring_active"],
                         "default OFF: nothing drains free quota in production")
        self.assertTrue(build_plane(slots, prefer=True).config_view()["meta"]["free_quota"]["prefer_expiring_active"])


# ================================================================== provider-side quota wall


class TestProviderQuotaWall(unittest.TestCase):
    QUOTA = ProviderError("quota", transient=False, code="provider_http_429", category="QUOTA_EXHAUSTED")

    def test_a_quota_wall_parks_the_slot_until_midnight_without_counting_as_a_health_failure(self) -> None:
        a, g = a_slot(priority=1), slot("gemini-01", priority=50)
        provs = {"alibaba-01": Scripted("alibaba-01", fail=self.QUOTA), "gemini-01": Scripted("gemini-01")}
        p = build_plane([a, g], profiles=only("alibaba", "gemini"), providers=provs)
        self.assertEqual(served(go(p)), ["gemini-01"])
        self.assertEqual(provs["alibaba-01"].calls, 1)
        self.assertEqual(p.skip_reason(a, "general", 10), SKIP_QUOTA_EXHAUSTED)
        self.assertEqual(served(go(p)), ["gemini-01"])
        self.assertEqual(provs["alibaba-01"].calls, 1, "not retried every 30 s")
        h = p.config_view()["slots"]
        health = next(s["health"] for s in h if s["slot_id"] == "alibaba-01")
        self.assertEqual(health["status"], "QUOTA_EXHAUSTED")
        self.assertEqual((health["consecutive_failures"], health["cooldown_s"], health["recent_429"]), (0, 0.0, 0))
        self.assertEqual((health["last_error_code"], health["last_error_category"]), ("provider_http_429", "QUOTA_EXHAUSTED"))
        self.assertEqual(health["usage_today"]["errors"], 1)
        self.assertEqual(health["usage_today"]["rate_limited"], 0)
        with mock.patch("server.ai_assistant.control.service.today_utc", return_value="20991231"):
            self.assertIsNone(p.skip_reason(a, "general", 10), "a new UTC day: try again")

    def test_a_plain_rate_limit_keeps_the_existing_cooldown_behaviour(self) -> None:
        rl = ProviderError("429", code="provider_http_429", retry_after_s=90, category="RATE_LIMITED")
        a = a_slot()
        p = build_plane([a], profiles=only("alibaba"), providers={"alibaba-01": Scripted("alibaba-01", fail=rl)})
        go(p)
        self.assertTrue(p.breaker.is_open("alibaba-01"))
        self.assertEqual(p.recent_429("alibaba-01"), 1)
        self.assertNotIn("alibaba-01", p._quota_out)  # noqa: SLF001

    def test_requests_the_vendor_rejects_cannot_open_the_breaker_but_real_slot_faults_do(self) -> None:
        """Anyone can send content a vendor refuses. That must never take the pool offline (3 failures = 60 s cooldown)."""
        for category, code, opens in (("CONTENT_FILTERED", "provider_http_400", False), ("CONTEXT_TOO_LONG", "provider_http_400", False),
                                      ("BAD_REQUEST", "provider_http_400", False), ("AUTH_FAILED", "provider_http_401", True),
                                      ("MODEL_NOT_FOUND", "provider_http_404", True), ("UNAVAILABLE", "provider_http_503", True)):
            with self.subTest(category):
                err = ProviderError("x", transient=False, code=code, category=category)
                p = build_plane([a_slot()], profiles=only("alibaba"), providers={"alibaba-01": Scripted("alibaba-01", fail=err)})
                for _ in range(5):
                    go(p)
                self.assertEqual(p.breaker.is_open("alibaba-01"), opens)
                health = next(s["health"] for s in p.config_view()["slots"] if s["slot_id"] == "alibaba-01")
                if opens:  # after 3 failures the slot is cooling down and is no longer tried
                    self.assertEqual(health["usage_today"]["errors"], 3)
                else:
                    self.assertEqual(health["usage_today"]["errors"], 5, "every rejected request is still counted")
                self.assertEqual(health["last_error_category"], category, "still visible to the owner")

    def test_every_slot_parked_by_quota_reads_as_budget_exhausted_not_as_no_provider(self) -> None:
        a = a_slot()
        p = build_plane([a], profiles=only("alibaba"), providers={"alibaba-01": Scripted("alibaba-01", fail=self.QUOTA)})
        go(p)
        events = go(p)
        self.assertEqual([e.code for e in events if isinstance(e, ErrorEvent)], ["ai_budget_exhausted"])
        self.assertEqual(exhausted_event([(a, SKIP_FREE_QUOTA_EXPIRED)]).code, "ai_budget_exhausted")
        self.assertEqual(exhausted_event([(a, SKIP_GATE_CLOSED)]).code, "ai_no_provider")
        self.assertEqual(exhausted_event([(a, SKIP_TIER)]).code, "ai_no_provider")

    def test_the_owner_can_lift_the_park_and_it_is_audited(self) -> None:
        a = a_slot()
        p = build_plane([a], profiles=only("alibaba"), providers={"alibaba-01": Scripted("alibaba-01", fail=self.QUOTA)})
        go(p)
        p.reset_cooldown("owner", "alibaba-01")
        self.assertIsNone(p.skip_reason(a, "general", 10))
        self.assertIn("provider_quota_exhausted", {e["field"] for e in p.audit(20)})

    def test_a_quota_wall_in_a_probe_parks_the_slot_but_never_touches_the_usage_ledger(self) -> None:
        a = a_slot(enabled=False)
        prov = StreamProbeProvider("alibaba-01", fail=self.QUOTA)
        p = build_plane([a], providers={"alibaba-01": prov})
        out = p.probe("owner", "alibaba-01")
        self.assertEqual((out["ok"], out["category"]), (False, "QUOTA_EXHAUSTED"))
        self.assertEqual(p.store.usage_for_day(today_utc()), {})
        self.assertFalse(p.breaker.is_open("alibaba-01"))
        self.assertEqual(p.skip_reason(replace(a, enabled=True), "general", 10), SKIP_QUOTA_EXHAUSTED)


# ================================================================== latency + probe through stream


class TestLatencyAccounting(unittest.TestCase):
    def test_ttft_and_total_are_measured_at_the_gateway(self) -> None:
        clk = Clock()
        a = a_slot()
        p = build_plane([a], clock=clk, profiles=only("alibaba"),
                        providers={"alibaba-01": StreamProbeProvider("alibaba-01", clock=clk, ttft_s=0.5, total_s=1.5)})
        go(p)  # binary-exact fake times (0.5 / 1.5): no float rounding in the millisecond conversion
        lat = p.latency_view("alibaba-01")
        self.assertEqual((lat["samples"], lat["ok"], lat["probe_samples"]), (1, 1, 0))
        self.assertEqual(lat["ttft_ms"], {"p50": 500, "p95": 500, "last": 500})
        self.assertEqual(lat["total_ms"], {"p50": 1500, "p95": 1500, "last": 1500})

    def test_failures_are_recorded_without_a_ttft(self) -> None:
        clk = Clock()
        p = build_plane([a_slot()], clock=clk, profiles=only("alibaba"),
                        providers={"alibaba-01": Scripted("alibaba-01", fail=ProviderError("x", code="provider_http_500"))})
        go(p)
        lat = p.latency_view("alibaba-01")
        self.assertEqual((lat["samples"], lat["ok"]), (1, 0))
        self.assertEqual(lat["ttft_ms"]["last"], None)

    def test_percentiles_window_and_health_exposure(self) -> None:
        a = a_slot()
        p = build_plane([a], profiles=only("alibaba"))
        for i in range(1, 101):
            p.note_latency(a, ttft_ms=i, total_ms=2 * i, ok=True)
        lat = p.latency_view("alibaba-01")
        self.assertEqual(lat["ttft_ms"], {"p50": 50, "p95": 95, "last": 100})
        self.assertEqual(lat["total_ms"]["p95"], 190)
        for i in range(250):
            p.note_latency(a, ttft_ms=1, total_ms=1, ok=True)
        self.assertEqual(p.latency_view("alibaba-01")["samples"], 200, "bounded window")
        health = p.slot_health(a, p.snapshot(), p.usage_today())
        self.assertEqual(health["latency"]["samples"], 200)
        self.assertEqual(p.latency_view("never-called")["samples"], 0)
        self.assertEqual(p.latency_view("never-called")["ttft_ms"], {"p50": None, "p95": None, "last": None})

    def test_gemini_slots_get_latency_too_and_routing_is_unchanged(self) -> None:
        clk = Clock()
        g = slot("gemini-01")
        p = build_plane([g], clock=clk, providers={"gemini-01": StreamProbeProvider("gemini-01", clock=clk, ttft_s=0.25, total_s=1.0)})
        self.assertEqual(served(go(p)), ["gemini-01"])
        self.assertEqual(p.latency_view("gemini-01")["ttft_ms"]["last"], 250)

    def test_a_failing_latency_hook_never_breaks_a_turn(self) -> None:
        p = build_plane([a_slot()], profiles=only("alibaba"))

        def boom(*a: Any, **k: Any) -> None:
            raise RuntimeError("metrics down")

        p.note_latency = boom  # type: ignore[assignment]
        self.assertEqual(served(go(p)), ["alibaba-01"])


class TestProbeThroughStream(unittest.TestCase):
    def test_probe_times_the_first_token_and_never_uses_generate_or_the_usage_ledger(self) -> None:
        prov = StreamProbeProvider("alibaba-01")
        p = build_plane([a_slot(enabled=False)], providers={"alibaba-01": prov})
        out = p.probe("owner", "alibaba-01")
        self.assertTrue(out["ok"])
        self.assertIsInstance(out["ttft_ms"], int)
        self.assertEqual((prov.calls, prov.generate_calls), (1, 0))
        self.assertNotIn("tokens", out)
        self.assertEqual(out["health"]["latency"]["probe_samples"], 1)
        self.assertEqual(p.store.usage, {}, "a probe never writes the usage ledger")
        row = p.audit(5)[0]
        self.assertEqual((row["entity"], row["field"]), ("slot:alibaba-01", "probe"))
        self.assertIn("ttft", row["new_value"])
        self.assertEqual(row["admin_id"], "owner", "audit attribution: WHO ran the probe")

    def test_probe_of_a_non_stream_provider_still_uses_generate_and_has_no_ttft(self) -> None:
        class Plain(Scripted):
            def generate(self, req: GenerateRequest) -> GenerateResult:
                return GenerateResult(text="OK", provider_name=self.name, model=req.model, input_tokens=3, output_tokens=1)

        p = build_plane([slot("gemini-01", enabled=False)], providers={"gemini-01": Plain("gemini-01")})
        out = p.probe("owner", "gemini-01")
        self.assertTrue(out["ok"])
        self.assertNotIn("ttft_ms", out, "the Gemini probe result is byte-identical to before")

    def test_an_empty_stream_probe_is_a_failure(self) -> None:
        class Empty(StreamProbeProvider):
            def stream(self, req: GenerateRequest) -> Iterator[Any]:
                yield UsageEvent(input_tokens=1, output_tokens=0)
                yield Done()

        p = build_plane([a_slot(enabled=False)], providers={"alibaba-01": Empty("alibaba-01")})
        out = p.probe("owner", "alibaba-01")
        self.assertEqual((out["ok"], out["code"], out["category"]), (False, "provider_empty", "EMPTY_RESPONSE"))


# ================================================================== admin API + client leaks


def _admin_client(plane: ControlPlane):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    class P:
        user_id = "owner_1"

    def reader() -> P:
        return P()

    app = FastAPI()
    app.include_router(build_ai_admin_router(plane, reader=reader, owner=reader))
    return TestClient(app)


class TestAdminSurface(unittest.TestCase):
    def test_config_exposes_the_alibaba_fields_and_no_secret(self) -> None:
        a = a_slot(tiers=("FAST",), free_quota_remaining=123456, free_quota_expires_at="2026-12-31T00:00:00+00:00",
                   free_quota_only=True, free_quota_updated_at="2026-10-02T00:00:00+00:00")
        p = build_plane([a, slot("gemini-01")], gate=False)
        r = _admin_client(p).get("/api/admin/ai/config")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertNotIn(FAKE_KEY, r.text)
        row = next(s for s in body["slots"] if s["slot_id"] == "alibaba-01")
        for key in ("model", "enabled", "tiers", "free_quota_remaining", "free_quota_expires_at", "free_quota_only",
                    "free_quota_updated_at", "effective_endpoint"):
            self.assertIn(key, row)
        h = row["health"]
        for key in ("status", "usage_today", "latency", "quota", "last_error_code", "probes_today", "secret", "gate"):
            self.assertIn(key, h)
        self.assertEqual(h["quota"]["state"], "active")
        self.assertEqual(h["gate"], {"env": "FAS_AI_ALIBABA_ENABLED", "open": False})
        self.assertEqual(h["status"], "GATE_CLOSED")
        pt = {t["type"]: t for t in body["provider_types"]}
        self.assertEqual(pt["alibaba"]["label"], "Alibaba Model Studio")
        self.assertEqual(pt["alibaba"]["gate"], {"env": "FAS_AI_ALIBABA_ENABLED", "open": False})
        self.assertIsNone(pt["gemini"]["gate"])
        self.assertIn("alibaba", body["meta"]["requires_endpoint"])
        self.assertIn("alibaba", body["meta"]["created_disabled_types"])
        self.assertIn("alibaba", body["meta"]["endpoint_hints"])
        ov = _admin_client(p).get("/api/admin/ai/overview").json()
        self.assertEqual(ov["gates"], {"alibaba": {"env": "FAS_AI_ALIBABA_ENABLED", "open": False},
                                       "qwen": {"env": "FAS_AI_ALIBABA_ENABLED", "open": False}},
                         "the legacy DashScope type shares the gate: no path to Alibaba without the explicit switch")
        self.assertIs(ov["free_quota_preference"], False)
        self.assertIn("alibaba", {x["type"] for x in ov["providers"]})

    def test_owner_flow_create_disabled_edit_metadata_probe_enable(self) -> None:
        p = build_plane([], gate=True, alibaba_type=True, providers={"alibaba-01": StreamProbeProvider("alibaba-01")},
                        profiles=only("gemini"))
        c = _admin_client(p)
        env = SecretResolver(env_for(a_slot()))
        p.secrets = env
        body = dict(slot_id="alibaba-01", provider_type="alibaba", label="A", secret_ref="ALIBABA_ALIBABA_01", model="m-owner",
                    endpoint=BASE, workloads=["general"], tiers=["FAST"])
        r = c.post("/api/admin/ai/slots", json={**body, "enabled": True})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["errors"][0]["field"], "enabled")
        self.assertEqual(c.post("/api/admin/ai/slots", json=body).status_code, 200)
        r = c.put("/api/admin/ai/slots/alibaba-01", json={"free_quota_remaining": 90000, "free_quota_only": True,
                                                          "free_quota_expires_at": "2026-12-31T00:00:00+00:00"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["slot"]["free_quota_remaining"], 90000)
        r = c.put("/api/admin/ai/slots/alibaba-01", json={"free_quota_expires_at": "next week"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"]["errors"][0]["field"], "free_quota_expires_at")
        probe = c.post("/api/admin/ai/slots/alibaba-01/probe").json()["probe"]
        self.assertTrue(probe["ok"])
        self.assertIsInstance(probe["ttft_ms"], int)
        self.assertEqual(set(probe) - {"health"}, {"slot_id", "model", "ok", "latency_ms", "code", "category", "ttft_ms"})
        self.assertEqual(c.put("/api/admin/ai/slots/alibaba-01", json={"enabled": True}).status_code, 200)

    def test_probe_with_the_gate_closed_is_a_409_with_the_instruction_and_sends_nothing(self) -> None:
        prov = StreamProbeProvider("alibaba-01")
        p = build_plane([a_slot(enabled=False)], gate=False, providers={"alibaba-01": prov})
        r = _admin_client(p).post("/api/admin/ai/slots/alibaba-01/probe")
        self.assertEqual(r.status_code, 409)
        self.assertIn("FAS_AI_ALIBABA_ENABLED", r.json()["detail"]["message"])
        self.assertEqual(prov.calls, 0)

    def test_a_schema_the_store_refuses_is_a_409_with_the_migration_hint(self) -> None:
        class Refusing(InMemoryControlStore):
            def save_slot(self, s: ProviderSlot, *, clear_meta: bool = False) -> None:
                raise ControlSchemaOutdated("Schema Appwrite chưa có thuộc tính mới — chạy migration trước.", status=400)

        p = build_plane([], store=Refusing(), profiles=only("gemini"))
        r = _admin_client(p).post("/api/admin/ai/slots", json=dict(
            slot_id="alibaba-01", provider_type="alibaba", label="A", secret_ref="ALIBABA_ONE", model="m", endpoint=BASE,
            workloads=["general"]))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["code"], "ai_admin_schema_outdated")
        self.assertIn("migration", r.json()["detail"]["message"])


class TestNoMetadataLeaksToOrdinaryClients(unittest.TestCase):
    FORBIDDEN = ("alibaba", "dashscope", "aliyuncs", "model-from-owner", "qwen", "alibaba-01", LEAK)

    def _world(self, script: Optional[List[Any]] = None) -> World:
        w = World(slots=1, global_cap=500)
        a = a_slot(model="model-from-owner")
        w.store.slots[a.slot_id] = a
        w.store.controls = replace(w.store.controls, provider_types={**w.store.controls.provider_types, "alibaba": True})
        w.store.profiles["FREE_FIRST"] = RoutingProfile("FREE_FIRST", ("alibaba",))
        w.provs["alibaba-01"] = Prov("alibaba-01", script=script or ())
        w.plane._gates["alibaba"] = True  # noqa: SLF001
        w.plane.secrets = SecretResolver({**env_for(*w.slots), **env_for(a)})
        w.plane.invalidate()
        return w

    def _assert_clean(self, text: str) -> None:
        low = text.lower()
        for word in self.FORBIDDEN:
            self.assertNotIn(word.lower(), low, word)

    def test_a_turn_served_by_alibaba_shows_the_user_nothing_about_the_provider(self) -> None:
        w = self._world()
        cid, r = w.ask("alice", "xin chào")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(ev(r, "delta") and ev(r, "done"))
        self.assertEqual(w.per_slot(), {"alibaba-01": 1}, "it really was served by the Alibaba slot")
        self._assert_clean(r.text)
        self._assert_clean(w.c.get("/api/ai/availability", headers=w.hdr("alice")).text)
        self._assert_clean(w.c.get(f"/api/ai/conversations/{cid}", headers=w.hdr("alice")).text)
        self._assert_clean(w.c.get("/api/ai/conversations", headers=w.hdr("alice")).text)
        self._assert_clean(w.c.get("/api/ai/access", headers=w.hdr("alice")).text)

    def test_provider_failures_reach_the_user_only_as_fixed_messages(self) -> None:
        errs = [ProviderError(f"upstream said {LEAK}", code="provider_http_401", category="AUTH_FAILED"),
                ProviderError(f"upstream said {LEAK}", transient=False, code="provider_http_429", category="QUOTA_EXHAUSTED"),
                ProviderError(f"upstream said {LEAK}", code="provider_timeout", category="TIMEOUT")]
        for e in errs:
            w = self._world([e])
            _, r = w.ask("alice", "xin chào")
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(ev(r, "error"), r.text)
            self._assert_clean(r.text)
            self.assertEqual(w.avail("alice")["limits"]["requests_used"], 0, "a provider-side failure is free for the user")

    def test_the_admin_sees_the_sanitised_enum_but_not_the_vendor_text(self) -> None:
        w = self._world([ProviderError(f"upstream said {LEAK}", transient=False, code="provider_http_429", category="QUOTA_EXHAUSTED")])
        w.ask("alice", "xin chào")
        raw = w.c.get("/api/admin/ai/config", headers={"Authorization": "Bearer owner"}).text
        self.assertNotIn(LEAK, raw)
        self.assertIn("QUOTA_EXHAUSTED", raw)


# ================================================================== helpers


def _dict(s: ProviderSlot) -> Dict[str, Any]:
    from server.ai_assistant.control.model import slot_to_dict
    return slot_to_dict(s)


def _with(cfg: ControlConfig) -> InMemoryControlStore:
    st = InMemoryControlStore()
    st.controls, st.slots = cfg.controls, dict(cfg.slots)
    return st


class _Recorder(_FakeAppwrite):
    """Fake Appwrite that remembers every slot write."""

    def __init__(self) -> None:
        super().__init__()
        self.writes: List[Dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method in ("PATCH", "POST") and "/ai_provider_slots/" in request.url.path:
            self.writes.append(json.loads(request.content))
        return super().__call__(request)


class _Rejecting(_FakeAppwrite):
    """Appwrite as production IS today: 400 for an attribute it does not have / an enum value it does not know."""

    def __init__(self, always: bool = False) -> None:
        super().__init__()
        self.always = always

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method in ("PATCH", "POST") and "/ai_provider_slots/" in request.url.path:
            data = json.loads(request.content).get("data", {})
            if self.always or "meta_json" in data or data.get("provider_type") == "alibaba":
                return httpx.Response(400, json={"message": "Invalid document structure"})
        return super().__call__(request)


def _appwrite_store(fake: Optional[_FakeAppwrite] = None):
    from server.config import AppwriteSettings
    fake = fake or _FakeAppwrite()
    aw = AppwriteSettings(endpoint="https://appwrite.example/v1", project_id="p", api_key="k", database_id="db")
    return AppwriteControlStore(aw, client=httpx.Client(transport=httpx.MockTransport(fake))), fake


if __name__ == "__main__":
    unittest.main()
