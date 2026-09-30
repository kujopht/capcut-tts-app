"""
`/api/admin/ai/*` over HTTP + the chat routes running on the control plane.
Access matrix, 422 validation, no secret in any response or log line,
kill switch / per-user cap through the real chat route, per-slot usage.
"""
from __future__ import annotations

import json
import logging
import random
import unittest
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.testclient import TestClient

from server.ai_assistant.control.admin_routes import build_ai_admin_router
from server.ai_assistant.control.model import GlobalControls, ProviderSlot
from server.ai_assistant.control.providers import ProviderFactory
from server.ai_assistant.control.router import ControlledGateway
from server.ai_assistant.control.secrets import SecretResolver
from server.ai_assistant.control.service import ControlPlane, today_utc
from server.ai_assistant.control.store import InMemoryControlStore
from server.ai_assistant.routes import build_ai_router
from server.llm_gateway.chat_provider import ProviderError
from server.llm_gateway.usage_limits import CircuitBreaker

from server.tests.test_ai_control_plane import FAKE_KEY, Clock, Scripted, slot
from server.tests.test_ai_routes import _auth, _enabled_runtime, _resolve_profile

ROLES = {"owner": "OWNER", "admin": "ADMIN", "mod": "MODERATOR", "user": "NONE"}


class _P:
    def __init__(self, uid: str) -> None:
        self.user_id = uid


def _who(authorization: Optional[str]) -> _P:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cần đăng nhập.")
    return _P(authorization.split(" ", 1)[1])


def reader(authorization: Optional[str] = Header(default=None)) -> _P:
    p = _who(authorization)
    if ROLES.get(p.user_id) not in ("ADMIN", "OWNER"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cần quyền Admin trở lên.")
    return p


def owner(authorization: Optional[str] = Header(default=None)) -> _P:
    p = _who(authorization)
    if ROLES.get(p.user_id) != "OWNER":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Khu vực chỉ dành cho Owner.")
    return p


def make_plane(slots=(), *, env=None, providers=None, ai_enabled=True) -> ControlPlane:
    store = InMemoryControlStore()
    store.controls = GlobalControls(ai_enabled=ai_enabled, provider_types={t: True for t in (
        "gemini", "groq", "workers_ai", "qwen", "azure_openai", "openrouter")}, version=1)
    for s in slots:
        store.slots[s.slot_id] = s
    env = env if env is not None else {f"FAS_AI_SECRET_{s.secret_ref}": FAKE_KEY for s in slots}
    providers = providers or {s.slot_id: Scripted(s.slot_id) for s in slots}
    clk = Clock()
    return ControlPlane(store, secrets=SecretResolver(env), clock=clk, breaker=CircuitBreaker(clock_fn=clk),
                        factory=ProviderFactory(builder=lambda s, k: providers[s.slot_id]), rng=random.Random(3))


def admin_client(plane: Optional[ControlPlane]) -> TestClient:
    app = FastAPI()
    app.include_router(build_ai_admin_router(plane, reader=reader, owner=owner))
    return TestClient(app)


def auth(who: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {who}"}


class TestAccessMatrix(unittest.TestCase):
    def setUp(self) -> None:
        self.plane = make_plane([slot("gemini-01")])
        self.c = admin_client(self.plane)

    def test_reads(self) -> None:
        for path in ("/api/admin/ai/overview", "/api/admin/ai/config", "/api/admin/ai/audit"):
            self.assertEqual(self.c.get(path).status_code, 401, path)
            self.assertEqual(self.c.get(path, headers=auth("user")).status_code, 403, path)
            self.assertEqual(self.c.get(path, headers=auth("mod")).status_code, 403, path)
            self.assertEqual(self.c.get(path, headers=auth("admin")).status_code, 200, path)
            self.assertEqual(self.c.get(path, headers=auth("owner")).status_code, 200, path)

    def test_writes_are_owner_only(self) -> None:
        writes = [("put", "/api/admin/ai/global", {"ai_enabled": False}),
                  ("put", "/api/admin/ai/provider-types/gemini", {"enabled": False}),
                  ("post", "/api/admin/ai/slots", {"slot_id": "groq-01", "provider_type": "groq", "label": "Groq",
                                                   "secret_ref": "GROQ_01", "model": "llama-3.1-8b-instant",
                                                   "workloads": ["general"]}),
                  ("put", "/api/admin/ai/slots/gemini-01", {"weight": 20}),
                  ("put", "/api/admin/ai/profiles/FREE_FIRST", {"steps": ["gemini", "groq"], "enabled": True}),
                  ("post", "/api/admin/ai/slots/gemini-01/reset-cooldown", None)]
        for method, path, body in writes:
            kw = {"json": body} if body is not None else {}
            for who, want in (("user", 403), ("mod", 403), ("admin", 403)):
                r = getattr(self.c, method)(path, headers=auth(who), **kw)
                self.assertEqual(r.status_code, want, f"{who} {method} {path}")
            r = getattr(self.c, method)(path, headers=auth("owner"), **kw)
            self.assertEqual(r.status_code, 200, f"owner {method} {path}: {r.text[:200]}")
        self.assertEqual(self.c.delete("/api/admin/ai/slots/groq-01", headers=auth("admin")).status_code, 403)
        self.assertEqual(self.c.delete("/api/admin/ai/slots/groq-01", headers=auth("owner")).status_code, 200)

    def test_flag_off_is_503_after_auth(self) -> None:
        c = admin_client(None)
        self.assertEqual(c.get("/api/admin/ai/config").status_code, 401)
        r = c.get("/api/admin/ai/config", headers=auth("owner"))
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "ai_admin_not_enabled")


class TestValidationAndConflicts(unittest.TestCase):
    def setUp(self) -> None:
        self.c = admin_client(make_plane([slot("gemini-01")]))

    def test_422_lists_fields(self) -> None:
        r = self.c.post("/api/admin/ai/slots", headers=auth("owner"), json={
            "slot_id": "Bad Id", "provider_type": "gemini", "label": "x", "secret_ref": "AIzaREALKEYlookalike-1",
            "model": "m", "endpoint": "https://evil.example.com", "workloads": ["general"]})
        self.assertEqual(r.status_code, 422)
        fields = {e["field"] for e in r.json()["detail"]["errors"]}
        self.assertTrue({"slot_id", "secret_ref", "endpoint"} <= fields)
        r = self.c.put("/api/admin/ai/global", headers=auth("owner"), json={"max_output_tokens": "lots"})
        self.assertEqual(r.status_code, 422)
        r = self.c.put("/api/admin/ai/global", headers=auth("owner"), json=["not", "an", "object"])
        self.assertEqual(r.status_code, 422)

    def test_409_and_404(self) -> None:
        self.c.put("/api/admin/ai/profiles/WRITER", headers=auth("owner"), json={"steps": ["gemini-01"], "enabled": True})
        r = self.c.delete("/api/admin/ai/slots/gemini-01", headers=auth("owner"))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.c.put("/api/admin/ai/slots/ghost", headers=auth("owner"), json={}).status_code, 404)
        r = self.c.put("/api/admin/ai/global", headers=auth("owner"), json={"ai_enabled": True, "expected_version": 999})
        self.assertEqual(r.status_code, 409)


class TestNoSecretLeak(unittest.TestCase):
    def test_no_secret_in_responses_or_logs(self) -> None:
        records = []

        class Grab(logging.Handler):
            def emit(self, rec):
                records.append(self.format(rec))

        h = Grab(level=logging.DEBUG)
        root = logging.getLogger()
        old_level = root.level
        root.addHandler(h)
        root.setLevel(logging.DEBUG)
        try:
            a = slot("gemini-01")
            bad = Scripted("gemini-01", fail=ProviderError(f"upstream said no for key {FAKE_KEY[:6]}…",
                                                          code="provider_http_401"))
            plane = make_plane([a], providers={"gemini-01": bad})
            c = admin_client(plane)
            texts = [c.get(p, headers=auth("owner")).text
                     for p in ("/api/admin/ai/config", "/api/admin/ai/overview", "/api/admin/ai/audit")]
            c.put("/api/admin/ai/slots/gemini-01", headers=auth("owner"), json={"secret_ref": "GEMINI_PROJECT_02"})
            texts.append(c.get("/api/admin/ai/audit", headers=auth("owner")).text)
            list(ControlledGateway(plane).stream([], mode="general"))
        finally:
            root.removeHandler(h)
            root.setLevel(old_level)
        blob = "\n".join(texts + records)
        self.assertNotIn(FAKE_KEY, blob)
        cfg = json.loads(texts[0])
        sec = cfg["slots"][0]["health"]["secret"]
        self.assertEqual(sec["env_name"], "FAS_AI_SECRET_GEMINI_01")
        self.assertTrue(sec["present"])
        self.assertTrue(sec["fingerprint"].startswith("sha256:"))


class TestChatOnControlPlane(unittest.TestCase):
    def _app(self, plane: ControlPlane):
        rt = _enabled_runtime()
        rt.gateway = ControlledGateway(plane)
        rt.control = plane

        def usage(uid: str, day: str):
            u = rt.repo.get_usage_day(uid, day)
            return (u.requests, u.input_tokens + u.output_tokens) if u else (0, 0)
        plane.attach_usage_sources(active_users_fn=rt.repo.count_usage_users, user_usage_fn=usage)
        app = FastAPI()
        app.include_router(build_ai_router(rt, resolve_profile=_resolve_profile))
        return rt, TestClient(app)

    def _ask(self, c: TestClient, who: str = "alice"):
        cid = c.post("/api/ai/conversations", headers=_auth(who), json={"mode": "general"}).json()["conversation_id"]
        return cid, c.post(f"/api/ai/conversations/{cid}/messages", headers=_auth(who),
                           json={"content": "xin chào", "client_id": f"c-{who}"})

    def test_served_by_slot_with_usage_recorded(self) -> None:
        plane = make_plane([slot("gemini-01", price_in_micro_per_mtok=1_000_000)])
        rt, c = self._app(plane)
        cid, r = self._ask(c)
        self.assertEqual(r.status_code, 200)
        self.assertIn("từ gemini-01", r.text)
        self.assertNotIn("gemini-model", r.text, "model/slot never sent to the client")
        u = plane.store.usage_for_day(today_utc())["gemini-01"]
        self.assertEqual(u.requests, 1)
        self.assertGreater(u.cost_micro_usd, 0)
        msg = [m for m in rt.repo._messages.values() if m.conversation_id == cid and m.role == "assistant"][0]  # noqa: SLF001
        self.assertEqual(msg.provider_name, "gemini-01")
        self.assertEqual(plane.overview()["active_users"], 1)

    def test_kill_switch_and_per_user_cap_through_the_real_route(self) -> None:
        plane = make_plane([slot("gemini-01")], ai_enabled=False)
        _, c = self._app(plane)
        av = c.get("/api/ai/availability", headers=_auth("bob")).json()
        self.assertEqual((av["enabled"], av["reason"]), (False, "disabled_by_admin"))
        _, r = self._ask(c, "bob")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "ai_not_enabled")

        plane2 = make_plane([slot("gemini-01")])
        plane2.update_controls("owner", {"per_user_daily_request_cap": 1})
        _, c2 = self._app(plane2)
        _, first = self._ask(c2, "carol")
        self.assertEqual(first.status_code, 200)
        _, second = self._ask(c2, "carol")
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["detail"]["code"], "ai_budget_exhausted")

    def test_no_eligible_provider_is_a_friendly_error_event(self) -> None:
        plane = make_plane([slot("gemini-01")], env={})  # secret missing
        _, c = self._app(plane)
        _, r = self._ask(c)
        self.assertEqual(r.status_code, 200)
        self.assertIn("event: error", r.text)
        self.assertIn("ai_no_provider", r.text)


class TestMainWiring(unittest.TestCase):
    def test_flag_off_by_default_and_admin_routes_mounted(self) -> None:
        import server.main as server_main
        self.assertIsNone(server_main.ai_control_plane, "FAS_AI_ADMIN_V1 is off by default")
        c = TestClient(server_main.app)
        self.assertEqual(c.get("/api/admin/ai/config").status_code, 401)
        health = c.get("/api/health").json()
        self.assertEqual(health["ai_assistant"], {"enabled": False, "admin_v1": False})


if __name__ == "__main__":
    unittest.main()
