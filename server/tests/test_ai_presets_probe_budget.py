"""
Preset rollout (canary/beta) + ngan sach probe TACH RIENG khoi ngan sach nguoi dung + duong kiem lai an toan
(lich su probe, `probe_stable`). Khoa gia dung luc chay (quy uoc gitleaks cua kho).
"""
from __future__ import annotations

import unittest

from server.ai_assistant.control.model import GlobalControls, ROLLOUT_PRESETS, preset_matching
from server.ai_assistant.control.service import (
    PROBE_DAILY_CAP_PER_SLOT, PROBE_MIN_INTERVAL_S, PROBE_STABLE_MAX_MS, ControlConflict,
)
from server.llm_gateway.chat_provider import ProviderError
from server.tests.test_ai_admin_api import admin_client, auth, make_plane
from server.tests.test_ai_balancing_probe import TYPES, Gen
from server.tests.test_ai_control_plane import Clock, plane_with, slot


class TestPresets(unittest.TestCase):
    def test_beta_proposal_values(self) -> None:
        b = ROLLOUT_PRESETS["beta"]
        self.assertEqual((b["per_user_daily_request_cap"], b["global_daily_request_cap"]), (5, 150))

    def test_apply_sets_caps_only_never_the_kill_switch(self) -> None:
        for on in (False, True):
            plane = plane_with([slot("gemini-01")], controls=GlobalControls(ai_enabled=on, provider_types=TYPES, version=3))
            out = plane.apply_preset("owner", "beta", expected_version=3)
            self.assertEqual(out["ai_enabled"], on)
            self.assertEqual(out["version"], 4, "one logical action = one version bump (review LOW #2)")
            for k, v in ROLLOUT_PRESETS["beta"].items():
                self.assertEqual(out[k], v, k)
            self.assertEqual(plane.config_view()["rollout"]["active_preset"], "beta")
            fields = {(a["entity"], a["field"]) for a in plane.audit(50)}
            self.assertIn(("global", "rollout_preset"), fields)
            self.assertIn(("global", "global_daily_request_cap"), fields)

    def test_emergency_off_still_wins_after_a_preset(self) -> None:
        plane = plane_with([slot("gemini-01")], controls=GlobalControls(ai_enabled=True, provider_types=TYPES, version=1))
        plane.apply_preset("owner", "beta", expected_version=1)
        out = plane.update_controls("owner", {"ai_enabled": False}, expected_version=0)  # stale on purpose
        self.assertFalse(out["ai_enabled"])

    def test_stale_version_and_unknown_name(self) -> None:
        plane = plane_with([slot("gemini-01")], controls=GlobalControls(ai_enabled=False, provider_types=TYPES, version=5))
        with self.assertRaises(ControlConflict):
            plane.apply_preset("owner", "beta", expected_version=4)
        with self.assertRaises(KeyError):
            plane.apply_preset("owner", "everyone")

    def test_custom_when_no_preset_matches(self) -> None:
        self.assertEqual(preset_matching(GlobalControls()), "custom")
        c = GlobalControls(**{**GlobalControls().__dict__, **ROLLOUT_PRESETS["canary"]})
        self.assertEqual(preset_matching(c), "canary")

    def test_route_owner_only_and_404(self) -> None:
        plane = make_plane([slot("gemini-01")], ai_enabled=False)
        c = admin_client(plane)
        self.assertEqual(c.put("/api/admin/ai/presets/beta", json={}).status_code, 401)
        self.assertEqual(c.put("/api/admin/ai/presets/beta", json={}, headers=auth("admin")).status_code, 403)
        r = c.put("/api/admin/ai/presets/beta", json={"expected_version": 1}, headers=auth("owner"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["controls"]["per_user_daily_request_cap"], 5)
        self.assertEqual(c.put("/api/admin/ai/presets/nope", json={}, headers=auth("owner")).status_code, 404)


class TestProbeBudgetIsSeparate(unittest.TestCase):
    def _plane(self, provider, clock):
        s = slot("gemini-01", enabled=True)
        ctl = GlobalControls(ai_enabled=True, provider_types=TYPES, version=1, global_daily_request_cap=1,
                             per_user_daily_request_cap=1)
        return plane_with([s], controls=ctl, providers={"gemini-01": provider}, clock=clock,
                          user_usage=lambda uid, day: (0, 0))

    def test_probes_never_consume_the_user_or_global_budget(self) -> None:
        clk = Clock()
        plane = self._plane(Gen("gemini-01"), clk)
        for _ in range(5):
            self.assertTrue(plane.probe("owner", "gemini-01")["ok"])
            clk.t += PROBE_MIN_INTERVAL_S + 1
        self.assertIsNone(plane.admission("someone"), "global cap 1 still open after 5 probes")
        ov = plane.overview()
        self.assertEqual(ov["requests"], 0)
        self.assertEqual(ov["probes_today"]["count"], 5)
        h = plane.config_view()["slots"][0]["health"]
        self.assertEqual((h["usage_today"]["requests"], h["probes_today"]["count"], h["probes_today"]["ok"]), (0, 5, 5))

    def test_probe_daily_cap(self) -> None:
        clk = Clock()
        plane = self._plane(Gen("gemini-01"), clk)
        for _ in range(PROBE_DAILY_CAP_PER_SLOT):
            plane.probe("owner", "gemini-01")
            clk.t += PROBE_MIN_INTERVAL_S + 1
        with self.assertRaises(ControlConflict):
            plane.probe("owner", "gemini-01")


class TestSafeReprobe(unittest.TestCase):
    def test_stable_only_after_three_fast_successes(self) -> None:
        clk = Clock()
        flaky = Gen("gemini-05", fail=ProviderError("503", code="provider_http_503", category="UNAVAILABLE"))
        s = slot("gemini-05", enabled=False)
        plane = plane_with([s], controls=GlobalControls(ai_enabled=False, provider_types=TYPES, version=1),
                           providers={"gemini-05": flaky}, clock=clk)

        def health():
            return plane.config_view()["slots"][0]["health"]

        plane.probe("owner", "gemini-05")
        self.assertFalse(health()["probe_stable"])
        flaky.fail = None
        for i in range(3):
            clk.t += PROBE_MIN_INTERVAL_S + 1
            plane.probe("owner", "gemini-05")
            self.assertEqual(health()["probe_stable"], i == 2)
        h = health()
        self.assertEqual([p["ok"] for p in h["probe_history"]], [True, True, True, False])
        self.assertEqual(h["status"], "DISABLED", "a probe never enables a slot by itself")

    def test_slow_success_is_not_stable(self) -> None:
        import server.ai_assistant.control.service as svc
        clk = Clock()
        s = slot("gemini-05", enabled=False)
        plane = plane_with([s], controls=GlobalControls(ai_enabled=False, provider_types=TYPES, version=1),
                           providers={"gemini-05": Gen("gemini-05")}, clock=clk)
        orig = svc.time.monotonic
        t = [0.0]

        def slow() -> float:  # consecutive calls 6 s apart -> each probe measures 6000 ms > PROBE_STABLE_MAX_MS
            t[0] += (PROBE_STABLE_MAX_MS + 1000) / 1000
            return t[0]
        svc.time.monotonic = slow
        try:
            for _ in range(3):
                plane.probe("owner", "gemini-05")
                clk.t += PROBE_MIN_INTERVAL_S + 1
        finally:
            svc.time.monotonic = orig
        self.assertFalse(plane.config_view()["slots"][0]["health"]["probe_stable"])


if __name__ == "__main__":
    unittest.main()
