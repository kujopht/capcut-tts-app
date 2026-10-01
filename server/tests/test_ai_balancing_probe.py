"""
Can bang slot theo muc da dung (headroom ngay/phut, phat sau 429/loi) + probe chu dong
cua Owner. Khoa gia dung luc chay (quy uoc gitleaks cua kho).
"""
from __future__ import annotations

import json
import random
import unittest
from collections import Counter

from fastapi.testclient import TestClient

from server.ai_assistant.control.model import GlobalControls
from server.ai_assistant.control.router import ControlledGateway, weighted_order
from server.ai_assistant.control.service import PROBE_MIN_INTERVAL_S, ControlConflict
from server.ai_assistant.gateway import ProviderServed
from server.llm_gateway.chat_provider import ChatTurn, GenerateResult, ProviderError
from server.tests.test_ai_admin_api import admin_client, auth, make_plane
from server.tests.test_ai_control_plane import FAKE_KEY, Clock, Scripted, plane_with, slot

TYPES = {t: True for t in ("gemini", "groq", "workers_ai", "qwen", "azure_openai", "openrouter")}


class Gen(Scripted):
    """Scripted + generate() (probe dung generate, khong stream)."""

    def __init__(self, name: str, *, fail: ProviderError = None, text: str = "OK") -> None:
        super().__init__(name, fail=fail)
        self.text = text
        self.gen_calls = 0

    def generate(self, req):  # noqa: D401
        self.gen_calls += 1
        if self.fail is not None:
            raise self.fail
        return GenerateResult(text=self.text, provider_name=self.name, model=req.model,
                              input_tokens=7, output_tokens=1, finish_reason="stop")


def pool(n: int, **kw):
    return [slot(f"gemini-{i:02d}", priority=10, daily_request_cap=30, daily_token_cap=60000, **kw) for i in range(1, n + 1)]


def serve(plane, turns: int) -> Counter:
    """Chay `turns` luot that qua ControlledGateway; cong usage cho DUNG slot da phuc vu (nhu route)."""
    got: Counter = Counter()
    for _ in range(turns):
        served = None
        for ev in ControlledGateway(plane).stream([ChatTurn(role="user", content="xin chào")], mode="general"):
            if isinstance(ev, ProviderServed):
                served = ev.provider_name
        if served:
            got[served] += 1
            plane.record_turn(served, 10, 5, "complete")
    return got


class TestWeightedOrderBalance(unittest.TestCase):
    def test_factor_multiplies_weight(self) -> None:
        a, b = slot("gemini-01", priority=10), slot("gemini-02", priority=10)
        rng = random.Random(1)
        firsts = Counter(weighted_order([a, b], rng, lambda s: 1.0 if s.slot_id == "gemini-01" else 0.05)[0].slot_id
                         for _ in range(400))
        self.assertGreater(firsts["gemini-01"], 360)

    def test_priority_tiers_still_win(self) -> None:
        a, b = slot("gemini-01", priority=10), slot("gemini-02", priority=20)
        order = weighted_order([b, a], random.Random(2), lambda s: 0.01 if s.slot_id == "gemini-01" else 1.0)
        self.assertEqual([s.slot_id for s in order], ["gemini-01", "gemini-02"])

    def test_no_balance_fn_keeps_old_behaviour(self) -> None:
        a, b = slot("gemini-01", priority=10, weight=10), slot("gemini-02", priority=10, weight=10)
        self.assertEqual(len(weighted_order([a, b], random.Random(3))), 2)


class TestPoolDrainsEvenly(unittest.TestCase):
    def test_nine_equal_slots_spread_without_exhausting_one_first(self) -> None:
        plane = plane_with(pool(9), clock=Clock())
        got = serve(plane, 200)
        self.assertEqual(sum(got.values()), 200)
        self.assertEqual(len(got), 9, got)
        self.assertLess(max(got.values()), 30, f"one project exhausted first: {got}")
        self.assertLessEqual(max(got.values()) - min(got.values()), 8, got)

    def test_a_busier_slot_is_picked_less(self) -> None:
        slots = pool(3)
        plane = plane_with(slots, clock=Clock())
        for _ in range(24):  # gemini-01 at 80% of its daily request cap
            plane.record_turn("gemini-01", 10, 5, "complete")
        got = serve(plane, 30)
        self.assertLess(got["gemini-01"], got["gemini-02"])
        self.assertLess(got["gemini-01"], got["gemini-03"])
        self.assertLessEqual(24 + got["gemini-01"], 30)

    def test_whole_pool_capacity_is_usable(self) -> None:
        plane = plane_with(pool(3), clock=Clock())
        got = serve(plane, 95)
        self.assertEqual(sum(got.values()), 90, "every slot reaches its own cap before the pool runs dry")
        self.assertEqual(set(got.values()), {30})

    def test_recent_429_and_failing_slots_are_penalised(self) -> None:
        slots = pool(2)
        plane = plane_with(slots, clock=Clock())
        self.assertAlmostEqual(plane.balance_factor(slots[0]), 1.0)
        plane.note_rate_limited(slots[0])
        self.assertAlmostEqual(plane.balance_factor(slots[0]), 0.25)
        plane.breaker.record_failure("gemini-02")
        self.assertAlmostEqual(plane.balance_factor(slots[1]), 0.25)
        plane.breaker.record_success("gemini-02")
        self.assertAlmostEqual(plane.balance_factor(slots[1]), 1.0)

    def test_minute_window_counts_toward_utilisation(self) -> None:
        s = slot("gemini-01", priority=10, rpm_soft_cap=4)
        plane = plane_with([s], clock=Clock())
        plane.note_attempt(s, 100)
        plane.note_attempt(s, 100)
        self.assertAlmostEqual(plane.balance_factor(s), 0.25)  # (1 - 2/4)^2


class TestProbe(unittest.TestCase):
    def _plane(self, provider: Gen, *, enabled=False, ai_enabled=False, env=None, clock=None):
        s = slot("gemini-03", enabled=enabled)
        return plane_with([s], controls=GlobalControls(ai_enabled=ai_enabled, provider_types=TYPES, version=1),
                          providers={"gemini-03": provider}, env=env, clock=clock or Clock()), s

    def test_success_while_slot_disabled_and_switch_off(self) -> None:
        p = Gen("gemini-03", text=f"OK {FAKE_KEY}")
        plane, _ = self._plane(p)
        out = plane.probe("owner", "gemini-03")
        self.assertTrue(out["ok"])
        self.assertEqual(p.gen_calls, 1)
        # Probe budget is SEPARATE from the user/global usage ledger (rollout presets PR).
        self.assertEqual(out["health"]["usage_today"]["requests"], 0)
        self.assertEqual(out["health"]["probes_today"]["count"], 1)
        self.assertNotIn(FAKE_KEY, json.dumps(out), "provider text is never returned")
        audit = plane.audit(10)
        self.assertEqual((audit[0]["entity"], audit[0]["field"]), ("slot:gemini-03", "probe"))
        self.assertTrue(audit[0]["new_value"].startswith("ok "))

    def test_failure_is_classified_and_audited(self) -> None:
        bad = ProviderError("x", code="provider_http_404", category="NOT_FOUND", transient=False)
        plane, _ = self._plane(Gen("gemini-03", fail=bad))
        out = plane.probe("owner", "gemini-03")
        self.assertEqual((out["ok"], out["code"], out["category"]), (False, "provider_http_404", "NOT_FOUND"))
        self.assertEqual(out["health"]["last_error_code"], "provider_http_404")
        self.assertEqual(out["health"]["usage_today"]["errors"], 0)
        self.assertEqual((out["health"]["probes_today"]["count"], out["health"]["probes_today"]["ok"]), (1, 0))
        self.assertEqual(plane.audit(10)[0]["new_value"], "provider_http_404/NOT_FOUND")

    def test_429_cools_the_slot_down(self) -> None:
        rl = ProviderError("429", code="provider_http_429", retry_after_s=45, category="RESOURCE_EXHAUSTED")
        plane, _ = self._plane(Gen("gemini-03", fail=rl), enabled=True, ai_enabled=True)
        out = plane.probe("owner", "gemini-03")
        self.assertEqual(out["health"]["status"], "COOLDOWN")
        self.assertEqual(out["health"]["usage_today"]["rate_limited"], 0)
        self.assertEqual(out["health"]["recent_429"], 1, "a probe 429 still penalises the slot in routing")

    def test_rate_limited_per_slot(self) -> None:
        clk = Clock()
        plane, _ = self._plane(Gen("gemini-03"), clock=clk)
        plane.probe("owner", "gemini-03")
        with self.assertRaises(ControlConflict):
            plane.probe("owner", "gemini-03")
        clk.t += PROBE_MIN_INTERVAL_S + 1
        self.assertTrue(plane.probe("owner", "gemini-03")["ok"])

    def test_missing_secret_never_calls_the_provider(self) -> None:
        p = Gen("gemini-03")
        plane, _ = self._plane(p, env={})
        out = plane.probe("owner", "gemini-03")
        self.assertEqual((out["ok"], out["code"]), (False, "missing_secret"))
        self.assertEqual(p.gen_calls, 0)

    def test_unknown_slot(self) -> None:
        plane, _ = self._plane(Gen("gemini-03"))
        with self.assertRaises(KeyError):
            plane.probe("owner", "gemini-99")


class TestProbeRoute(unittest.TestCase):
    def test_owner_only_and_statuses(self) -> None:
        s = slot("gemini-01")
        plane = make_plane([s], providers={"gemini-01": Gen("gemini-01")})
        c: TestClient = admin_client(plane)
        url = "/api/admin/ai/slots/gemini-01/probe"
        self.assertEqual(c.post(url).status_code, 401)
        self.assertEqual(c.post(url, headers=auth("admin")).status_code, 403)
        r = c.post(url, headers=auth("owner"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["probe"]["ok"])
        self.assertEqual(r.headers.get("cache-control"), "no-store")
        self.assertEqual(c.post(url, headers=auth("owner")).status_code, 409)
        self.assertEqual(c.post("/api/admin/ai/slots/nope-01/probe", headers=auth("owner")).status_code, 404)
        self.assertNotIn(FAKE_KEY, r.text)


if __name__ == "__main__":
    unittest.main()
