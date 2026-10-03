"""
AI control plane (docs/ai/AI_ADMIN_CONTROL_PLANE.md) — model validation,
secret references, routing, fail-closed config, quotas, audit, Appwrite store.
Fake secrets are built at runtime (repo gitleaks convention).
"""
from __future__ import annotations

import random
import unittest
from collections import Counter
from dataclasses import replace
from typing import Dict, Iterator, List, Optional

import httpx

from server.ai_assistant.control.model import (
    LEGACY_QWEN_PROFILE_STEPS, ConfigValidationError, ControlConfig, GlobalControls, ProviderSlot, RoutingProfile,
    default_profiles, slot_from_dict, validate_profile, validate_slot,
)
from server.ai_assistant.control.providers import ProviderFactory
from server.ai_assistant.control.router import (
    SKIP_COOLDOWN, SKIP_MISSING_SECRET, SKIP_REQUEST_CAP, SKIP_RPM, SKIP_SLOT_DISABLED, SKIP_TOKEN_CAP,
    SKIP_TPM, SKIP_TYPE_DISABLED, SKIP_WORKLOAD, ControlledGateway, weighted_order,
)
from server.ai_assistant.control.secrets import SecretResolver
from server.ai_assistant.control.service import ControlConflict, ControlPlane, today_utc
from server.ai_assistant.control.store import (
    AppwriteControlStore, ControlStoreUnavailable, InMemoryControlStore,
)
from server.ai_assistant.gateway import ErrorEvent, ProviderServed
from server.llm_gateway.chat_provider import (
    ChatProvider, ChatTurn, Delta, Done, GenerateRequest, GenerateResult, ProviderCapabilities, ProviderError,
    ProviderUsageSnapshot, StreamEvent, UsageEvent,
)
from server.llm_gateway.usage_limits import CircuitBreaker

FAKE_KEY = "sk-" + "controlplane" * 3
FAKE_KEY_2 = "gsk_" + "rotated" * 4


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class Scripted(ChatProvider):
    def __init__(self, name: str, *, fail: Optional[ProviderError] = None, fail_after_delta: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.fail_after_delta = fail_after_delta
        self.calls = 0
        self.models: List[str] = []

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(streaming=True, tools=False, web_search=False, vision=False, max_context_tokens=8000)

    def generate(self, req: GenerateRequest) -> GenerateResult:  # pragma: no cover
        raise NotImplementedError

    def stream(self, req: GenerateRequest) -> Iterator[StreamEvent]:
        self.calls += 1
        self.models.append(req.model)
        if self.fail is not None and not self.fail_after_delta:
            raise self.fail
        yield Delta(text=f"từ {self.name}")
        if self.fail is not None and self.fail_after_delta:
            raise self.fail
        yield UsageEvent(input_tokens=10, output_tokens=5)
        yield Done()

    def usage(self) -> ProviderUsageSnapshot:
        return ProviderUsageSnapshot(requests=self.calls)


def slot(slot_id: str, ptype: str = "gemini", **kw) -> ProviderSlot:
    ref = slot_id.upper().replace("-", "_")
    if not ref.startswith(ptype.upper() + "_"):
        ref = f"{ptype.upper()}_{ref}"  # a key is bound to its provider type (secret_ref prefix)
    base = dict(slot_id=slot_id, provider_type=ptype, label=slot_id.upper(), secret_ref=ref,
                model=f"{ptype}-model", enabled=True, workloads=("general", "story", "writer", "support", "web_search"))
    if ptype == "workers_ai":
        base["endpoint"] = "https://api.cloudflare.com/client/v4/accounts/abc123/ai/v1"
    if ptype == "azure_openai":
        base["endpoint"] = "https://fanfic.openai.azure.com"
    base.update(kw)
    return ProviderSlot(**base)


def env_for(*slots: ProviderSlot) -> Dict[str, str]:
    return {f"FAS_AI_SECRET_{s.secret_ref}": FAKE_KEY for s in slots}


def plane_with(slots: List[ProviderSlot], *, controls: Optional[GlobalControls] = None,
               profiles: Optional[Dict[str, RoutingProfile]] = None, env: Optional[Dict[str, str]] = None,
               providers: Optional[Dict[str, Scripted]] = None, seed: int = 7, clock: Optional[Clock] = None,
               user_usage=None) -> ControlPlane:
    store = InMemoryControlStore()
    types = {t: True for t in ("gemini", "groq", "workers_ai", "qwen", "azure_openai", "openrouter")}
    store.controls = controls or GlobalControls(ai_enabled=True, provider_types=types, version=1)
    for s in slots:
        store.slots[s.slot_id] = s
    for p in (profiles or {}).values():
        store.profiles[p.name] = p
    providers = providers or {s.slot_id: Scripted(s.slot_id) for s in slots}
    clk = clock or Clock()
    return ControlPlane(store, secrets=SecretResolver(env if env is not None else env_for(*slots)),
                        factory=ProviderFactory(builder=lambda s, k: providers[s.slot_id]),
                        breaker=CircuitBreaker(clock_fn=clk), clock=clk, rng=random.Random(seed),
                        user_usage_fn=user_usage,
                        # Some routing tests use the retired legacy `qwen` (DashScope) type; ITS server gate is open here on
                        # purpose (it is independent of the Alibaba Model Studio gate, which stays closed) — the gate-closed
                        # behaviour is covered in test_ai_alibaba_control_plane.py / test_ai_alibaba_isolation.py.
                        qwen_legacy_enabled=True)


def turns() -> List[ChatTurn]:
    return [ChatTurn(role="user", content="xin chào")]


def run(plane: ControlPlane, mode: str = "general", workload: Optional[str] = None) -> List[StreamEvent]:
    return list(ControlledGateway(plane).stream(turns(), mode=mode, workload=workload))


# ============================================================ model / validation


class TestValidation(unittest.TestCase):
    def test_valid_slot_passes(self) -> None:
        validate_slot(slot("gemini-01"))

    def test_bad_fields_are_all_reported(self) -> None:
        s = ProviderSlot(slot_id="X!", provider_type="nope", label="", secret_ref="sk-live-abc", model="bad model")
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_slot(s)
        fields = {e["field"] for e in ctx.exception.errors}
        self.assertTrue({"slot_id", "provider_type", "label", "secret_ref", "model"} <= fields)

    def test_endpoint_host_allowlist_blocks_ssrf(self) -> None:
        for bad in ("http://generativelanguage.googleapis.com/v1", "https://evil.example.com/v1",
                    "https://169.254.169.254/latest", "https://user:pw@generativelanguage.googleapis.com/x",
                    "https://generativelanguage.googleapis.com:8443/x"):
            with self.assertRaises(ConfigValidationError, msg=bad):
                validate_slot(slot("gemini-01", endpoint=bad))
        validate_slot(slot("gemini-01", endpoint="https://generativelanguage.googleapis.com/v1beta/openai"))

    def test_workers_ai_and_azure_need_their_endpoint(self) -> None:
        with self.assertRaises(ConfigValidationError):
            validate_slot(slot("cf-01", "workers_ai", endpoint=""))
        with self.assertRaises(ConfigValidationError):
            validate_slot(slot("cf-01", "workers_ai", endpoint="https://api.cloudflare.com/other/path"))
        with self.assertRaises(ConfigValidationError):
            validate_slot(slot("az-01", "azure_openai", endpoint=""))
        validate_slot(slot("az-01", "azure_openai", api_version="2024-06-01"))

    def test_numeric_ranges_and_workloads(self) -> None:
        for kw in ({"priority": 100}, {"weight": 0}, {"daily_token_cap": -1}, {"workloads": ()},
                   {"workloads": ("general", "hacking")}, {"priority": True}):
            with self.assertRaises(ConfigValidationError, msg=str(kw)):
                validate_slot(slot("gemini-01", **kw))

    def test_profile_steps_must_exist_and_not_repeat(self) -> None:
        slots = {"gemini-01": slot("gemini-01")}
        validate_profile(RoutingProfile("FREE_FIRST", ("gemini", "gemini-01")), slots)
        for steps in (("gemini", "gemini"), ("ghost-slot",), ("gemini",) * 13):
            with self.assertRaises(ConfigValidationError, msg=str(steps)):
                validate_profile(RoutingProfile("FREE_FIRST", steps), slots)
        with self.assertRaises(ConfigValidationError):
            validate_profile(RoutingProfile("NOT_A_PROFILE", ()), slots)

    def test_slot_from_dict_rejects_wrong_types(self) -> None:
        with self.assertRaises(ConfigValidationError):
            validate_slot(slot_from_dict({"slot_id": "g-1", "provider_type": "gemini", "label": "x",
                                          "secret_ref": "G_1", "model": "m", "priority": "high"}))
        with self.assertRaises(ConfigValidationError, msg='"false" must not become True'):
            slot_from_dict({"slot_id": "g-1", "provider_type": "gemini", "enabled": "false"})

    def test_slot_id_fits_the_usage_document_id(self) -> None:
        """Usage rows are ``{slot_id}_{yyyymmdd}``; Appwrite ids are <= 36 chars."""
        longest = "g" * 27
        validate_slot(slot(longest))
        self.assertLessEqual(len(f"{longest}_{today_utc()}"), 36)
        with self.assertRaises(ConfigValidationError):
            validate_slot(slot("g" * 28))

    def test_secret_ref_is_bound_to_its_provider_type(self) -> None:
        validate_slot(slot("az-01", "azure_openai", secret_ref="AZURE_OPENAI_MAIN"))
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_slot(slot("az-01", "azure_openai", secret_ref="GEMINI_PROJECT_01"))
        self.assertEqual(ctx.exception.errors[0]["field"], "secret_ref")

    def test_model_cannot_walk_the_path(self) -> None:
        validate_slot(slot("or-01", "openrouter", model="meta-llama/llama-3.1-8b-instruct"))
        for ptype, model in (("openrouter", "../../admin"), ("azure_openai", "gpt4o/../../x"), ("azure_openai", "a/b")):
            with self.assertRaises(ConfigValidationError, msg=model):
                validate_slot(slot("x-01", ptype, model=model))

    def test_malformed_or_long_endpoint_is_a_validation_error(self) -> None:
        for bad in ("https://api.groq.com:abc/v1", "https://api.groq.com/" + "a" * 300):
            with self.assertRaises(ConfigValidationError, msg=bad[:40]):
                validate_slot(slot("groq-01", "groq", endpoint=bad))

    def test_mode_profiles_must_be_an_object(self) -> None:
        from server.ai_assistant.control.model import controls_with
        for bad in ("abc", 5, ["FREE_FIRST"], {"general": 1}):
            with self.assertRaises(ConfigValidationError, msg=repr(bad)):
                controls_with(GlobalControls(), {"mode_profiles": bad})


# ============================================================ secrets


class TestSecrets(unittest.TestCase):
    def test_resolve_and_masked_status(self) -> None:
        r = SecretResolver({"FAS_AI_SECRET_GEMINI_PROJECT_01": FAKE_KEY})
        self.assertEqual(r.resolve("GEMINI_PROJECT_01"), FAKE_KEY)
        st = r.status("GEMINI_PROJECT_01")
        self.assertTrue(st.present)
        self.assertEqual(st.env_name, "FAS_AI_SECRET_GEMINI_PROJECT_01")
        self.assertTrue(st.fingerprint.startswith("sha256:") and len(st.fingerprint) == 15)
        self.assertNotIn(FAKE_KEY, repr(st))
        self.assertNotEqual(st.fingerprint, SecretResolver({"FAS_AI_SECRET_GEMINI_PROJECT_01": FAKE_KEY_2})
                            .status("GEMINI_PROJECT_01").fingerprint, "rotation must change the fingerprint")

    def test_missing_or_invalid_ref(self) -> None:
        r = SecretResolver({})
        self.assertIsNone(r.resolve("GEMINI_PROJECT_01"))
        self.assertFalse(r.status("GEMINI_PROJECT_01").present)
        self.assertIsNone(r.resolve("../etc/passwd"))
        self.assertFalse(r.status("lower_case").present)


# ============================================================ routing


class TestRouting(unittest.TestCase):
    def test_priority_then_weighted_order_is_seed_deterministic(self) -> None:
        pool = [slot("g-a", priority=10, weight=1), slot("g-b", priority=10, weight=1),
                slot("g-c", priority=5, weight=1), slot("g-d", priority=20, weight=1)]
        o1 = [s.slot_id for s in weighted_order(pool, random.Random(42))]
        o2 = [s.slot_id for s in weighted_order(pool, random.Random(42))]
        self.assertEqual(o1, o2, "same seed -> same order")
        self.assertEqual(o1[0], "g-c")
        self.assertEqual(o1[-1], "g-d")
        self.assertEqual(set(o1[1:3]), {"g-a", "g-b"})

    def test_weights_shape_the_distribution(self) -> None:
        pool = [slot("g-heavy", weight=90), slot("g-light", weight=10)]
        rng = random.Random(1)
        first = Counter(weighted_order(pool, rng)[0].slot_id for _ in range(2000))
        self.assertGreater(first["g-heavy"], 1600)
        self.assertGreater(first["g-light"], 100)

    def test_profile_order_and_fallback_on_failure(self) -> None:
        a, b = slot("gemini-01"), slot("groq-01", "groq")
        prov = {"gemini-01": Scripted("gemini-01", fail=ProviderError("x", code="provider_http_500")),
                "groq-01": Scripted("groq-01")}
        p = plane_with([a, b], providers=prov)
        ev = run(p)
        self.assertEqual([e for e in ev if isinstance(e, ProviderServed)], [ProviderServed("groq-01", "groq-model")])
        self.assertEqual((prov["gemini-01"].calls, prov["groq-01"].calls), (1, 1), "each slot tried exactly once")

    def test_429_cools_down_the_slot_for_retry_after(self) -> None:
        clk = Clock()
        a, b = slot("gemini-01"), slot("gemini-02")
        prov = {"gemini-01": Scripted("gemini-01", fail=ProviderError("429", code="provider_http_429", retry_after_s=90)),
                "gemini-02": Scripted("gemini-02")}
        p = plane_with([a, b], providers=prov, clock=clk,
                       profiles={"FREE_FIRST": RoutingProfile("FREE_FIRST", ("gemini-01", "gemini-02"))})
        run(p)
        self.assertEqual(p.skip_reason(a, "general", 0), SKIP_COOLDOWN)
        self.assertEqual(p.recent_429("gemini-01"), 1)
        run(p)
        self.assertEqual(prov["gemini-01"].calls, 1, "cooling slot is skipped")
        clk.t += 91
        run(p)
        self.assertEqual(prov["gemini-01"].calls, 2, "cooldown ends on time")
        health = p.slot_health(a, p.snapshot(), p.usage_today())
        self.assertEqual(health["usage_today"]["rate_limited"], 2)

    def test_no_fallback_after_first_delta(self) -> None:
        a, b = slot("gemini-01"), slot("groq-01", "groq")
        prov = {"gemini-01": Scripted("gemini-01", fail=ProviderError("cut", code="provider_http_500"),
                                      fail_after_delta=True),
                "groq-01": Scripted("groq-01")}
        ev = run(plane_with([a, b], providers=prov))
        self.assertIsInstance(ev[-1], ErrorEvent)
        self.assertEqual(ev[-1].code, "ai_provider_interrupted")
        self.assertEqual(prov["groq-01"].calls, 0)

    def test_skip_reasons(self) -> None:
        clk = Clock()
        s_dis = slot("g-dis", enabled=False)
        s_noref = slot("g-noref")
        s_wl = slot("g-wl", workloads=("writer",))
        s_req = slot("g-req", daily_request_cap=1)
        s_tok = slot("g-tok", daily_token_cap=10)
        s_rpm = slot("g-rpm", rpm_soft_cap=1)
        s_tpm = slot("g-tpm", tpm_soft_cap=50)
        s_type = slot("q-1", "qwen")
        slots = [s_dis, s_noref, s_wl, s_req, s_tok, s_rpm, s_tpm, s_type]
        env = env_for(*[s for s in slots if s is not s_noref])
        types = {t: True for t in ("gemini", "groq", "workers_ai", "qwen", "azure_openai", "openrouter")}
        types["qwen"] = False
        p = plane_with(slots, env=env, clock=clk,
                       controls=GlobalControls(ai_enabled=True, provider_types=types, version=1))
        p.store.add_usage("g-req", today_utc(), requests=1)
        p.store.add_usage("g-tok", today_utc(), input_tokens=8, output_tokens=5)
        p.note_attempt(s_rpm, 1)
        got = {s.slot_id: p.skip_reason(s, "general", 60) for s in slots}
        self.assertEqual(got, {"g-dis": SKIP_SLOT_DISABLED, "g-noref": SKIP_MISSING_SECRET, "g-wl": SKIP_WORKLOAD,
                               "g-req": SKIP_REQUEST_CAP, "g-tok": SKIP_TOKEN_CAP, "g-rpm": SKIP_RPM,
                               "g-tpm": SKIP_TPM, "q-1": SKIP_TYPE_DISABLED})
        clk.t += 61
        self.assertIsNone(p.skip_reason(s_rpm, "general", 0), "soft RPM window slides")

    def test_global_kill_switch_routes_nothing(self) -> None:
        a = slot("gemini-01")
        p = plane_with([a], controls=GlobalControls(ai_enabled=False, provider_types={"gemini": True, "groq": True,
                       "workers_ai": True, "qwen": True, "azure_openai": True, "openrouter": True}))
        ev = run(p)
        self.assertEqual(ev[-1].code, "ai_no_provider")
        self.assertEqual(p.store.slots["gemini-01"].slot_id, "gemini-01")
        self.assertEqual(p.admission("u1").code, "ai_not_enabled")

    def test_all_capped_gives_friendly_quota_error(self) -> None:
        a = slot("gemini-01", daily_request_cap=1)
        p = plane_with([a])
        p.store.add_usage("gemini-01", today_utc(), requests=1)
        ev = run(p)
        self.assertEqual(ev[-1].code, "ai_budget_exhausted")

    def test_workload_routes_to_its_profile_and_model(self) -> None:
        g, q = slot("gemini-01", model="gemini-2.0-flash"), slot("qwen-01", "qwen", model="qwen-max")
        prov = {"gemini-01": Scripted("gemini-01"), "qwen-01": Scripted("qwen-01")}
        # `qwen` is retired from the DEFAULT profiles: a mode routes to it only when the owner sets the step (the documented
        # rollback path, `LEGACY_QWEN_PROFILE_STEPS`), and then the slot's own model is the one sent.
        legacy_writer = {"WRITER": RoutingProfile("WRITER", LEGACY_QWEN_PROFILE_STEPS["WRITER"])}
        p = plane_with([g, q], providers=prov, profiles=legacy_writer)
        served = [e for e in run(p, mode="writer") if isinstance(e, ProviderServed)]
        self.assertEqual(served[0].provider_name, "qwen-01", "the explicit legacy WRITER profile starts with qwen")
        self.assertEqual(prov["qwen-01"].models, ["qwen-max"])
        # …and with the DEFAULT profile the same slots never reach qwen.
        prov2 = {"gemini-01": Scripted("gemini-01"), "qwen-01": Scripted("qwen-01")}
        served = [e for e in run(plane_with([g, q], providers=prov2), mode="writer") if isinstance(e, ProviderServed)]
        self.assertEqual(served[0].provider_name, "gemini-01", "default WRITER = azure_openai > gemini, no qwen")
        self.assertEqual(prov2["qwen-01"].calls, 0)
        served = [e for e in run(p, workload="web_search") if isinstance(e, ProviderServed)]
        self.assertEqual(served[0].provider_name, "gemini-01", "WEB_SEARCH starts with gemini")

    def test_output_and_context_caps_apply(self) -> None:
        cap = GlobalControls(ai_enabled=True, provider_types={t: True for t in ("gemini", "groq", "workers_ai", "qwen",
                             "azure_openai", "openrouter")}, max_output_tokens=100, version=1)
        seen = {}

        class Capture(Scripted):
            def stream(self, req):
                seen["max"] = req.max_output_tokens
                yield from super().stream(req)
        a = slot("gemini-01")
        run(plane_with([a], controls=cap, providers={"gemini-01": Capture("gemini-01")}))
        self.assertEqual(seen["max"], 100)


# ============================================================ fail-closed config


class TestFailClosed(unittest.TestCase):
    def test_empty_store_means_ai_off(self) -> None:
        p = ControlPlane(InMemoryControlStore(), secrets=SecretResolver({}))
        self.assertFalse(p.enabled())
        self.assertEqual(p.state, "empty")

    def test_corrupt_config_fails_closed_even_after_a_good_load(self) -> None:
        clk = Clock()
        a = slot("gemini-01")
        p = plane_with([a], clock=clk)
        self.assertTrue(p.enabled())
        p.store.corrupt = True
        clk.t += 60
        self.assertFalse(p.enabled())
        self.assertEqual(p.state, "corrupt")
        self.assertEqual(run(p)[-1].code, "ai_no_provider")

    def test_invalid_stored_values_count_as_corrupt(self) -> None:
        a = slot("gemini-01")
        p = plane_with([a])
        p.store.slots["gemini-01"] = replace(a, endpoint="https://evil.example.com/v1")
        p.invalidate()
        self.assertFalse(p.enabled())
        self.assertEqual(p.state, "corrupt")

    def test_unreachable_store_uses_last_good_then_closes(self) -> None:
        clk = Clock()
        p = plane_with([slot("gemini-01")], clock=clk)
        self.assertTrue(p.enabled())

        def boom():
            raise ControlStoreUnavailable("down")
        p.store.load = boom  # type: ignore[assignment]
        clk.t += 20
        self.assertTrue(p.enabled(), "short outage keeps the last validated config")
        self.assertEqual(p.state, "stale")
        clk.t += 700
        self.assertFalse(p.enabled(), "long outage closes")
        self.assertEqual(p.state, "unavailable")


# ============================================================ quotas / usage


class TestQuotas(unittest.TestCase):
    def _types(self) -> Dict[str, bool]:
        return {t: True for t in ("gemini", "groq", "workers_ai", "qwen", "azure_openai", "openrouter")}

    def test_global_request_token_and_cost_caps(self) -> None:
        for kw, usage in (({"global_daily_request_cap": 2}, {"requests": 2}),
                          ({"global_daily_token_cap": 100}, {"input_tokens": 60, "output_tokens": 40}),
                          ({"daily_cost_cap_micro_usd": 500}, {"cost_micro_usd": 500})):
            p = plane_with([slot("gemini-01")], controls=GlobalControls(ai_enabled=True, provider_types=self._types(),
                                                                        version=1, **kw))
            p.store.add_usage("gemini-01", today_utc(), **usage)
            d = p.admission("u1")
            self.assertEqual((d.status, d.code), (429, "ai_budget_exhausted"), kw)
            self.assertTrue(d.reset_at)

    def test_per_user_caps(self) -> None:
        p = plane_with([slot("gemini-01")], user_usage=lambda uid, day: (50, 10) if uid == "heavy" else (0, 0))
        self.assertIsNone(p.admission("light"))
        self.assertEqual(p.admission("heavy").code, "ai_budget_exhausted")

    def test_record_turn_counts_usage_cost_and_success(self) -> None:
        a = slot("gemini-01", price_in_micro_per_mtok=100_000, price_out_micro_per_mtok=400_000)
        p = plane_with([a])
        p.record_turn("gemini-01", 10_000, 5_000, "complete")
        u = p.store.usage_for_day(today_utc())["gemini-01"]
        self.assertEqual((u.requests, u.input_tokens, u.output_tokens), (1, 10_000, 5_000))
        self.assertEqual(u.cost_micro_usd, 3000)  # 10k*0.1$/M + 5k*0.4$/M = 0.003 $
        self.assertTrue(u.last_success_at)
        ov = p.overview()
        self.assertEqual((ov["requests"], ov["est_cost_micro_usd"]), (1, 3000))

    def test_health_statuses(self) -> None:
        clk = Clock()
        slots = [slot("g-ok"), slot("g-off", enabled=False), slot("g-nokey"), slot("g-cap", daily_request_cap=1),
                 slot("g-cool")]
        p = plane_with(slots, env=env_for(*[s for s in slots if s.slot_id != "g-nokey"]), clock=clk)
        p.store.add_usage("g-cap", today_utc(), requests=1)
        p.breaker.cool_down("g-cool", 30)
        cfg, usage = p.snapshot(), p.usage_today()
        got = {s.slot_id: p.slot_health(s, cfg, usage)["status"] for s in slots}
        self.assertEqual(got, {"g-ok": "HEALTHY", "g-off": "DISABLED", "g-nokey": "MISSING_SECRET",
                               "g-cap": "OVER_CAP", "g-cool": "COOLDOWN"})


# ============================================================ mutations + audit


class TestMutationsAndAudit(unittest.TestCase):
    def test_create_update_delete_slot_with_audit(self) -> None:
        p = plane_with([])
        body = {"slot_id": "gemini-01", "provider_type": "gemini", "label": "Project 01", "secret_ref": "GEMINI_PROJECT_01",
                "model": "gemini-2.0-flash", "workloads": ["general"], "enabled": True}
        p.create_slot("owner1", body)
        with self.assertRaises(ControlConflict):
            p.create_slot("owner1", body)
        p.update_slot("owner1", "gemini-01", {"priority": 3, "weight": 50})
        with self.assertRaises(ConfigValidationError):
            p.update_slot("owner1", "gemini-01", {"provider_type": "groq"})
        with self.assertRaises(ConfigValidationError):
            p.update_slot("owner1", "gemini-01", {"endpoint": "https://evil.example.com"})
        p.update_profile("owner1", "FREE_FIRST", ["gemini-01", "groq"], True)
        with self.assertRaises(ControlConflict):
            p.delete_slot("owner1", "gemini-01")
        p.update_profile("owner1", "FREE_FIRST", ["gemini", "groq"], True)
        p.delete_slot("owner1", "gemini-01")
        audit = p.audit(100)
        fields = {(a["entity"], a["field"]) for a in audit}
        self.assertIn(("slot:gemini-01", "priority"), fields)
        self.assertIn(("slot:gemini-01", "weight"), fields)
        self.assertIn(("profile:FREE_FIRST", "steps"), fields)
        prio = next(a for a in audit if a["field"] == "priority" and a["new_value"] == "3")
        self.assertEqual((prio["old_value"], prio["admin_id"]), ("50", "owner1"))
        deleted = next(a for a in audit if a["field"] == "priority" and a["old_value"] == "3")
        self.assertEqual(deleted["new_value"], "null", "delete is audited with the old values")
        self.assertTrue(all(a["at"] for a in audit))

    def test_global_controls_kill_switch_and_version_conflict(self) -> None:
        p = plane_with([slot("gemini-01")])
        v = p.snapshot().controls.version
        p.update_controls("owner1", {"ai_enabled": False}, expected_version=v)
        self.assertFalse(p.enabled())
        with self.assertRaises(ControlConflict):
            p.update_controls("owner1", {"ai_enabled": True}, expected_version=v)
        with self.assertRaises(ConfigValidationError):
            p.update_controls("owner1", {"max_output_tokens": 999_999})
        with self.assertRaises(ConfigValidationError):
            p.update_controls("owner1", {"version": 99})
        p.set_provider_type("owner1", "gemini", False)
        self.assertFalse(p.snapshot().controls.provider_types["gemini"])
        kill = [a for a in p.audit() if a["field"] == "ai_enabled"]
        self.assertEqual((kill[0]["old_value"], kill[0]["new_value"]), ("true", "false"))

    def test_audit_never_contains_a_secret_value(self) -> None:
        a = slot("gemini-01")
        p = plane_with([a])
        p.update_slot("owner1", "gemini-01", {"secret_ref": "GEMINI_PROJECT_09"})
        p.reset_cooldown("owner1", "gemini-01")
        blob = repr(p.store.audit)
        self.assertNotIn(FAKE_KEY, blob)
        self.assertIn("GEMINI_PROJECT_09", blob, "the reference NAME is fine to log")

    def test_mutations_refuse_to_build_on_a_corrupt_store(self) -> None:
        p = plane_with([slot("gemini-01")])
        p.store.corrupt = True
        with self.assertRaises(ControlConflict):
            p.update_controls("owner1", {"ai_enabled": True})

    def test_the_41st_slot_is_refused_instead_of_locking_the_config(self) -> None:
        from server.ai_assistant.control.model import MAX_SLOTS
        p = plane_with([slot(f"gemini-{i:02d}") for i in range(MAX_SLOTS)])
        with self.assertRaises(ConfigValidationError):
            p.create_slot("owner1", {"slot_id": "gemini-99", "provider_type": "gemini", "label": "x",
                                     "secret_ref": "GEMINI_99", "model": "m", "workloads": ["general"],
                                     "enabled": True})
        self.assertEqual(len(p.store.slots), MAX_SLOTS)
        self.assertTrue(p.enabled(), "config stays valid")

    def test_invalid_config_can_still_be_repaired_from_the_ui(self) -> None:
        a = slot("gemini-01")
        p = plane_with([a], profiles={"FREE_FIRST": RoutingProfile("FREE_FIRST", ("gemini-01", "gemini"))})
        # Another instance deleted the slot while the profile still points at it.
        del p.store.slots["gemini-01"]
        p.invalidate()
        self.assertFalse(p.enabled())
        self.assertEqual(p.state, "corrupt")
        with self.assertRaises(ControlConflict, msg="growing a broken config is refused"):
            p.create_slot("owner1", {"slot_id": "gemini-02", "provider_type": "gemini", "label": "x",
                                     "secret_ref": "GEMINI_02", "model": "m", "workloads": ["general"], "enabled": True})
        with self.assertRaises(ConfigValidationError, msg="the repair edit itself is still validated"):
            p.update_profile("owner1", "FREE_FIRST", ["gemini-01"], True)
        p.update_profile("owner1", "FREE_FIRST", ["gemini"], True)
        self.assertTrue(p.enabled(), "valid again after the repair")
        self.assertEqual(p.state, "ok")

    def test_emergency_off_wins_over_a_stale_version(self) -> None:
        p = plane_with([slot("gemini-01")])
        stale = p.snapshot().controls.version
        p.set_provider_type("owner1", "groq", False)  # someone else bumped the version
        p.update_controls("owner1", {"ai_enabled": False}, expected_version=stale)
        self.assertFalse(p.enabled(), "OFF must never fail on a stale version")
        with self.assertRaises(ControlConflict, msg="turning ON needs a current view"):
            p.update_controls("owner1", {"ai_enabled": True}, expected_version=stale)
        with self.assertRaises(ControlConflict):
            p.set_provider_type("owner1", "groq", True, expected_version=stale)
        p.set_provider_type("owner1", "gemini", False, expected_version=stale)
        self.assertFalse(p.snapshot().controls.provider_types["gemini"])

    def test_audit_write_failure_does_not_fail_an_applied_change(self) -> None:
        p = plane_with([slot("gemini-01")])

        def down(entries):
            raise ControlStoreUnavailable("audit down")
        p.store.add_audit = down  # type: ignore[assignment]
        with self.assertLogs("fanfic.ai_assistant", level="ERROR") as logs:
            p.update_controls("owner1", {"ai_enabled": False})
        self.assertFalse(p.enabled(), "applied, and the cache was refreshed")
        self.assertIn("field=ai_enabled", "\n".join(logs.output))
        self.assertNotIn(FAKE_KEY, "\n".join(logs.output))

    def test_unknown_usage_is_refused_not_read_as_zero(self) -> None:
        p = plane_with([slot("gemini-01")], controls=GlobalControls(
            ai_enabled=True, provider_types={t: True for t in ("gemini", "groq", "workers_ai", "qwen",
                                                               "azure_openai", "openrouter")},
            version=1, global_daily_request_cap=10))

        def down(day):
            raise ControlStoreUnavailable("usage down")
        p.store.usage_for_day = down  # type: ignore[assignment]
        d = p.admission("u1")
        self.assertEqual((d.status, d.code), (503, "ai_storage_unavailable"))

    def test_per_user_usage_failure_is_a_503(self) -> None:
        def boom(uid, day):
            raise RuntimeError("ledger down")
        p = plane_with([slot("gemini-01")], user_usage=boom)
        d = p.admission("u1")
        self.assertEqual((d.status, d.code), (503, "ai_storage_unavailable"))


# ============================================================ Appwrite store


class _FakeAppwrite:
    """Minimal documents API: GET/POST/PATCH/DELETE + equal/orderDesc/limit."""

    def __init__(self) -> None:
        self.cols: Dict[str, Dict[str, Dict]] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        import json
        import re
        m = re.search(r"/collections/([^/]+)/documents(?:/([^/?]+))?$", request.url.path)
        coll, doc_id = m.group(1), m.group(2)
        store = self.cols.setdefault(coll, {})
        if request.method == "POST":
            b = json.loads(request.content)
            store[b["documentId"]] = {**b["data"], "$id": b["documentId"]}
            return httpx.Response(201, json=store[b["documentId"]])
        if request.method == "PATCH":
            if doc_id not in store:
                return httpx.Response(404, json={"message": "nf"})
            store[doc_id].update(json.loads(request.content)["data"])
            return httpx.Response(200, json=store[doc_id])
        if request.method == "DELETE":
            store.pop(doc_id, None)
            return httpx.Response(204)
        if doc_id:
            return httpx.Response(200, json=store[doc_id]) if doc_id in store else httpx.Response(404, json={})
        docs = list(store.values())
        for q in (json.loads(x) for x in request.url.params.get_list("queries[]")):
            if q["method"] == "equal":
                docs = [d for d in docs if d.get(q["attribute"]) in q["values"]]
            elif q["method"] == "orderDesc":
                docs = sorted(docs, key=lambda d, a=q["attribute"]: d.get(a) or "", reverse=True)
            elif q["method"] == "limit":
                docs = docs[: q["values"][0]]
        return httpx.Response(200, json={"documents": docs, "total": len(docs)})


class TestAppwriteStore(unittest.TestCase):
    def _store(self):
        from server.config import AppwriteSettings
        fake = _FakeAppwrite()
        aw = AppwriteSettings(endpoint="https://appwrite.example/v1", project_id="p", api_key="k", database_id="db")
        return AppwriteControlStore(aw, client=httpx.Client(transport=httpx.MockTransport(fake))), fake

    def test_round_trip_config_usage_and_audit(self) -> None:
        from server.ai_assistant.control.store import AuditEntry
        st, fake = self._store()
        cfg0 = st.load()
        self.assertFalse(cfg0.controls.ai_enabled, "no settings row -> AI off")
        c = replace(GlobalControls(), ai_enabled=True, version=3)
        st.save_controls(c)
        st.save_slot(slot("gemini-01"))
        st.save_profile(RoutingProfile("WRITER", ("qwen", "gemini-01")))
        cfg = st.load()
        self.assertTrue(cfg.controls.ai_enabled)
        self.assertEqual(cfg.controls.version, 3)
        self.assertEqual(cfg.slots["gemini-01"].workloads, slot("gemini-01").workloads)
        self.assertEqual(cfg.profiles["WRITER"].steps, ("qwen", "gemini-01"))
        self.assertIn("FREE_FIRST", cfg.profiles, "missing profiles fall back to defaults")
        st.add_usage("gemini-01", "20260930", requests=1, input_tokens=5)
        st.add_usage("gemini-01", "20260930", requests=1, output_tokens=7, success_at="2026-09-30T01:00:00+00:00")
        u = st.usage_for_day("20260930")["gemini-01"]
        self.assertEqual((u.requests, u.input_tokens, u.output_tokens), (2, 5, 7))
        st.add_audit([AuditEntry("o1", "global", "ai_enabled", "false", "true", at="2026-09-30T01:00:00+00:00"),
                      AuditEntry("o1", "global", "max_output_tokens", "800", "600", at="2026-09-30T02:00:00+00:00")])
        self.assertEqual([a.field for a in st.list_audit(10)], ["max_output_tokens", "ai_enabled"])
        rows = repr(fake.cols)
        self.assertNotIn(FAKE_KEY, rows)
        self.assertIn("GEMINI_01", rows, "only the reference name is stored")

    def test_every_written_field_exists_in_the_schema(self) -> None:
        """Contract with scripts/setup_appwrite.py: an attribute missing from
        the schema makes Appwrite reject the write in production."""
        import importlib.util
        from pathlib import Path

        from server.ai_assistant.control.store import AuditEntry
        path = Path(__file__).resolve().parents[2] / "scripts" / "setup_appwrite.py"
        spec = importlib.util.spec_from_file_location("setup_appwrite_contract", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        st, fake = self._store()
        st.save_controls(GlobalControls())
        st.save_slot(slot("az-01", "azure_openai", api_version="2024-06-01"))
        st.save_profile(RoutingProfile("WRITER", ("qwen",)))
        st.add_usage("az-01", "20260930", requests=1, success_at="2026-09-30T00:00:00+00:00")
        st.add_audit([AuditEntry("o1", "global", "ai_enabled", "false", "true")])
        for coll, docs in fake.cols.items():
            attrs = {a[0] for a in mod.SCHEMA[coll]["attributes"]}
            for d in docs.values():
                extra = set(d) - {"$id"} - attrs
                self.assertFalse(extra, f"{coll}: fields not in schema: {extra}")

    def test_corrupt_row_raises(self) -> None:
        from server.ai_assistant.control.store import ControlConfigCorrupt
        st, fake = self._store()
        st.save_slot(slot("gemini-01"))
        fake.cols["ai_provider_slots"]["gemini-01"]["workloads_json"] = "{not json"
        with self.assertRaises(ControlConfigCorrupt):
            st.load()


if __name__ == "__main__":
    unittest.main()
