"""
`GET /api/ai/access` — cong HIEN THI cua Tro ly AI (nut noi, muc menu, loi vao trang
truyen). Frontend chi ve loi vao khi may chu tra `eligible: true`.

Ba dieu duoc khoa o day:
1. `eligible` doc tu DUNG nguon cua route that (`AiRuntime.access_state`, ma availability
   cung dung; `allows()` la cong cua moi route khac) — khong co luat thu hai.
2. Phan hoi chi co MOT bit: khong ly do, khan gia, danh sach ID, han muc hay provider.
3. Cong UI sai thi backend van chan: moi route `/api/ai/*` tu kiem o moi request.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import replace
from typing import Dict

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.ai_assistant.control.router import ControlledGateway
from server.ai_assistant.routes import build_ai_router
from server.ai_assistant.runtime import AiRuntime, build_ai_runtime
from server.config import AiAssistantSettings, Settings
from server.tests.test_ai_admin_api import make_plane
from server.tests.test_ai_audience import _resolve_profile, _runtime
from server.tests.test_ai_control_plane import slot

OWNER = "owner_1"
CANARY = "user_canary"
TESTER = "tester_01"
STRANGER = "user_stranger"


def _client(rt: AiRuntime) -> TestClient:
    app = FastAPI()
    app.include_router(build_ai_router(rt, resolve_profile=_resolve_profile))
    return TestClient(app)


def _auth(user_id: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {user_id}"}


def _settings(**ai) -> Settings:
    base = AiAssistantSettings(enabled=True, providers=("mock",))
    return replace(Settings(), owner_user_ids=(OWNER,), ai_assistant=replace(base, **ai))


def _beta_runtime() -> AiRuntime:
    return build_ai_runtime(_settings(audience="beta", canary_users=(CANARY,), beta_users=(TESTER,)))


def _eligible(c: TestClient, who: str) -> bool:
    r = c.get("/api/ai/access", headers=_auth(who))
    assert r.status_code == 200, r.text
    return r.json()["eligible"]


class TestAccessByRole(unittest.TestCase):
    def test_owner_is_eligible_in_canary(self) -> None:
        c = _client(build_ai_runtime(_settings(audience="canary")))
        self.assertTrue(_eligible(c, OWNER))

    def test_beta_tester_is_eligible_only_in_beta(self) -> None:
        self.assertTrue(_eligible(_client(_beta_runtime()), TESTER))
        self.assertTrue(_eligible(_client(_beta_runtime()), OWNER))
        self.assertTrue(_eligible(_client(_beta_runtime()), CANARY))
        # Cung tester, khan gia canary (production hien tai): KHONG thay loi vao.
        canary = build_ai_runtime(_settings(audience="canary", beta_users=(TESTER,)))
        self.assertFalse(_eligible(_client(canary), TESTER))

    def test_logged_in_non_beta_user_is_not_eligible_and_routes_stay_403(self) -> None:
        c = _client(_beta_runtime())
        self.assertFalse(_eligible(c, STRANGER))
        # Cong UI khong phai rao chan: route that van tu chan nguoi ngoai khan gia.
        r = c.post("/api/ai/conversations", json={"mode": "general"}, headers=_auth(STRANGER))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"]["code"], "ai_not_enabled")

    def test_anonymous_is_401(self) -> None:
        c = _client(_beta_runtime())
        self.assertEqual(c.get("/api/ai/access").status_code, 401)
        self.assertEqual(c.get("/api/ai/access", headers={"Authorization": "Basic x"}).status_code, 401)

    def test_flag_off_is_not_eligible_even_for_owner(self) -> None:
        off = build_ai_runtime(_settings(enabled=False, audience="canary"))
        self.assertFalse(off.enabled)
        self.assertFalse(_eligible(_client(off), OWNER))
        # Khan gia sai (gia tri la / beta qua 50 ID) cung la AI TAT -> khong ai thay loi vao.
        bad = build_ai_runtime(_settings(audience="everyone"))
        self.assertFalse(_eligible(_client(bad), OWNER))

    def test_emergency_switch_hides_entry_points_and_backend_still_refuses(self) -> None:
        rt = _runtime("canary", {OWNER})
        plane = make_plane([slot("gemini-01")], ai_enabled=False)
        rt.gateway, rt.control = ControlledGateway(plane), plane
        c = _client(rt)
        self.assertFalse(_eligible(c, OWNER))
        cid = c.post("/api/ai/conversations", json={"mode": "general"}, headers=_auth(OWNER)).json()["conversation_id"]
        sent = c.post(f"/api/ai/conversations/{cid}/messages", json={"content": "hi", "client_id": "c1"},
                      headers=_auth(OWNER))
        self.assertEqual(sent.status_code, 503)
        self.assertEqual(sent.json()["detail"]["code"], "ai_not_enabled")
        # Bat lai: lan doc sau thay ngay (khong cache phia may chu ngoai cache cau hinh cua control plane).
        plane.update_controls("owner", {"ai_enabled": True})
        self.assertTrue(_eligible(c, OWNER))


class TestResponseShape(unittest.TestCase):
    def test_one_bit_no_ids_no_reason_no_provider(self) -> None:
        rt = _beta_runtime()
        c = _client(rt)
        for who in (OWNER, TESTER, STRANGER):
            with self.subTest(who=who):
                r = c.get("/api/ai/access", headers=_auth(who))
                self.assertEqual(set(r.json()), {"eligible"})
                self.assertIsInstance(r.json()["eligible"], bool)
                blob = r.text.lower()
                for leak in (TESTER, CANARY, OWNER, "beta", "canary", "audience", "reason",
                             "mock", "gemini", "provider", "limit"):
                    self.assertNotIn(leak.lower(), blob)
                self.assertIn("no-store", r.headers["cache-control"])
                self.assertIn("private", r.headers["cache-control"])
                self.assertIn("authorization", r.headers.get("vary", "").lower())


class TestSameSourceOfTruth(unittest.TestCase):
    def test_access_matches_availability_and_the_route_gate(self) -> None:
        """Ma tran runtime x nguoi dung: `eligible` == availability `enabled` == `access_state()=="ok"`,
        va nguoi ngoai khan gia (`allows()` sai) luon bi route that tra 403."""
        killed = _runtime("canary", {OWNER})
        plane = make_plane([slot("gemini-01")], ai_enabled=False)
        killed.gateway, killed.control = ControlledGateway(plane), plane
        runtimes = {
            "canary": build_ai_runtime(_settings(audience="canary", canary_users=(CANARY,), beta_users=(TESTER,))),
            "beta": _beta_runtime(),
            "all": build_ai_runtime(_settings(audience="all")),
            "off": AiRuntime(False, reason="FAS_AI_ASSISTANT_V1 chưa bật"),
            "killed": killed,
        }
        for name, rt in runtimes.items():
            c = _client(rt)
            for who in (OWNER, CANARY, TESTER, STRANGER):
                with self.subTest(runtime=name, who=who):
                    eligible = _eligible(c, who)
                    av = c.get("/api/ai/availability", headers=_auth(who)).json()
                    self.assertEqual(eligible, av["enabled"])
                    self.assertEqual(eligible, rt.access_state(who) == "ok")
                    if rt.serving() and not rt.allows(who):
                        r = c.get("/api/ai/conversations", headers=_auth(who))
                        self.assertEqual(r.status_code, 403)

    def test_both_endpoints_share_one_helper(self) -> None:
        import inspect
        import re as _re
        import server.ai_assistant.routes as routes_mod
        src = inspect.getsource(routes_mod.build_ai_router)
        for fn in ("access", "availability"):
            body = src.split(f"def {fn}(", 1)[1].split("\n    @r.", 1)[0]
            with self.subTest(fn=fn):
                self.assertRegex(body, r"_access\(authorization\)")
                self.assertNotRegex(body, r"\.allows\(|control\.enabled\(", "khong duoc tu ghep luat rieng")
        self.assertEqual(len(_re.findall(r"rt\.access_state\(", src)), 1)

    def test_availability_reasons_unchanged(self) -> None:
        """Refactor sang `access_state` khong doi hop dong availability da co."""
        c = _client(_runtime("canary", {OWNER}))
        self.assertEqual(c.get("/api/ai/availability", headers=_auth(STRANGER)).json()["reason"], "not_in_audience")
        off = _client(AiRuntime(False, reason="FAS_AI_ASSISTANT_V1 chưa bật", owner_users=frozenset({OWNER})))
        # Chi tiết cấu hình (tên biến môi trường) chỉ dành cho Owner; mọi tài khoản khác nhận mã ổn định "off".
        self.assertEqual(off.get("/api/ai/availability", headers=_auth(OWNER)).json()["reason"],
                         "FAS_AI_ASSISTANT_V1 chưa bật")
        for who in (STRANGER, CANARY, TESTER):
            self.assertEqual(off.get("/api/ai/availability", headers=_auth(who)).json()["reason"], "off", who)
        ok = c.get("/api/ai/availability", headers=_auth(OWNER)).json()
        self.assertTrue(ok["enabled"])
        self.assertIn("limits", ok)
        self.assertIsNone(json.loads(json.dumps(ok))["reason"])

    def test_runtimes_built_while_disabled_still_know_the_owner_so_the_owner_keeps_the_diagnosis(self) -> None:
        """`reason` chi tiết chỉ dành cho Owner; nếu runtime tắt không mang danh sách Owner thì chính Owner cũng chỉ
        còn thấy "off" và mất khả năng chẩn đoán vì sao AI tắt."""
        for label, ai in (("flag tắt", {"enabled": False}), ("khán giả hỏng", {"audience": "khong-hop-le"})):
            with self.subTest(label):
                rt = build_ai_runtime(_settings(**ai))
                self.assertFalse(rt.serving())
                self.assertTrue(rt.is_owner(OWNER))
                c = _client(rt)
                self.assertNotEqual(c.get("/api/ai/availability", headers=_auth(OWNER)).json()["reason"], "off")
                self.assertEqual(c.get("/api/ai/availability", headers=_auth(STRANGER)).json()["reason"], "off")


if __name__ == "__main__":
    unittest.main()
