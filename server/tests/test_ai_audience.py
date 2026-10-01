"""
Khan gia `/api/ai/*` (`FAS_AI_AUDIENCE`, `FAS_AI_CANARY_USERS`) — cung mau
`FAS_CHAT_V1_AUDIENCE`. Truoc ban nay bat `FAS_AI_ASSISTANT_V1=1` la MOI nguoi
da dang nhap goi duoc API AI (khong co UI nhung van goi thang duoc), nen mot
canary "chi Owner" tren production khong the chung minh duoc la chi Owner.
"""
from __future__ import annotations

import os
import unittest
from dataclasses import dataclass, replace
from typing import Dict, Optional
from unittest import mock

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from server.ai_assistant.gateway import AiGateway
from server.ai_assistant.limits import StreamGuard
from server.ai_assistant.memory import InMemoryAiRepo
from server.ai_assistant.routes import build_ai_router
from server.ai_assistant.runtime import AiRuntime, build_ai_runtime
from server.ai_assistant.tools import ToolContext
from server.config import AiAssistantSettings, Settings, _ai_assistant_settings
from server.llm_gateway.chat_providers import MockChatProvider

OWNER = "owner_1"
CANARY = "user_canary"
STRANGER = "user_stranger"


@dataclass(frozen=True)
class _Profile:
    user_id: str
    tier: str = "free"


def _resolve_profile(authorization: Optional[str]) -> _Profile:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cần đăng nhập.")
    return _Profile(user_id=authorization.split(" ", 1)[1].strip())


def _runtime(audience: str, users=frozenset()) -> AiRuntime:
    return AiRuntime(True, repo=InMemoryAiRepo(),
                     gateway=AiGateway(providers={"mock": MockChatProvider()}, provider_chain=["mock"]),
                     tool_ctx=ToolContext(), rpm=1000, stream_guard=StreamGuard(max_streams_per_instance=4),
                     audience=audience, audience_users=frozenset(users))


def _client(rt: AiRuntime) -> TestClient:
    app = FastAPI()
    app.include_router(build_ai_router(rt, resolve_profile=_resolve_profile))
    return TestClient(app)


def _auth(user_id: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {user_id}"}


class TestResolvedAudience(unittest.TestCase):
    def test_empty_means_canary_on_appwrite_and_all_elsewhere(self) -> None:
        s = AiAssistantSettings()
        self.assertEqual(s.resolved_audience("appwrite"), "canary")
        self.assertEqual(s.resolved_audience("APPWRITE"), "canary")
        self.assertEqual(s.resolved_audience("mock"), "all")

    def test_explicit_values_and_unknown_is_empty(self) -> None:
        self.assertEqual(AiAssistantSettings(audience="all").resolved_audience("appwrite"), "all")
        self.assertEqual(AiAssistantSettings(audience=" Canary ").resolved_audience("mock"), "canary")
        self.assertEqual(AiAssistantSettings(audience="everyone").resolved_audience("appwrite"), "")

    def test_env_parsing_drops_non_ids(self) -> None:
        env = {"FAS_AI_AUDIENCE": "CANARY", "FAS_AI_CANARY_USERS": "abc123, ,bad id!,6a88165cc7a5,x" * 1}
        with mock.patch.dict(os.environ, env, clear=False):
            s = _ai_assistant_settings()
        self.assertEqual(s.audience, "canary")
        self.assertEqual(s.canary_users, ("abc123", "6a88165cc7a5", "x"))

    def test_health_shows_audience_but_never_ids(self) -> None:
        s = Settings(data_backend="appwrite",
                     ai_assistant=AiAssistantSettings(canary_users=("secret_looking_id",)))
        info = s.ai_assistant.describe()
        self.assertEqual(info["audience"], "auto")
        self.assertEqual(info["canary_users"], 1)
        self.assertNotIn("secret_looking_id", repr(info))
        self.assertEqual(s.ai_assistant.resolved_audience(s.data_backend), "canary")


class TestBuildRuntime(unittest.TestCase):
    def _settings(self, **ai) -> Settings:
        base = AiAssistantSettings(enabled=True, providers=("mock",))
        return replace(Settings(), owner_user_ids=(OWNER,), ai_assistant=replace(base, **ai))

    def test_owner_and_canary_users_form_the_audience(self) -> None:
        rt = build_ai_runtime(self._settings(audience="canary", canary_users=(CANARY,)))
        self.assertTrue(rt.enabled)
        self.assertEqual(rt.audience, "canary")
        self.assertTrue(rt.allows(OWNER))
        self.assertTrue(rt.allows(CANARY))
        self.assertFalse(rt.allows(STRANGER))
        self.assertFalse(rt.allows(""))

    def test_mock_backend_default_is_all(self) -> None:
        rt = build_ai_runtime(self._settings())
        self.assertEqual(rt.audience, "all")
        self.assertTrue(rt.allows(STRANGER))

    def test_unknown_audience_turns_ai_off(self) -> None:
        rt = build_ai_runtime(self._settings(audience="everyone"))
        self.assertFalse(rt.enabled)
        self.assertIn("FAS_AI_AUDIENCE", rt.reason)

    def test_beta_cohort_sits_between_canary_and_all(self) -> None:
        tester = "tester_01"
        rt = build_ai_runtime(self._settings(audience="beta", canary_users=(CANARY,), beta_users=(tester,)))
        self.assertTrue(rt.enabled)
        self.assertEqual(rt.audience, "beta")
        for uid in (OWNER, CANARY, tester):
            self.assertTrue(rt.allows(uid), uid)
        self.assertFalse(rt.allows(STRANGER))
        self.assertFalse(rt.allows(""))
        # canary KHONG mo cho tester beta (danh sach beta chi co hieu luc o khan gia beta)
        rt_c = build_ai_runtime(self._settings(audience="canary", beta_users=(tester,)))
        self.assertFalse(rt_c.allows(tester))

    def test_beta_with_empty_list_warns_and_stays_owner_only(self) -> None:
        with self.assertLogs("fanfic.ai_assistant", level="WARNING") as cm:
            rt = build_ai_runtime(self._settings(audience="beta"))
        self.assertTrue(any("FAS_AI_BETA_USERS" in m for m in cm.output))
        self.assertTrue(rt.allows(OWNER))
        self.assertFalse(rt.allows(STRANGER))

    def test_invalid_audience_reason_never_echoes_the_value(self) -> None:
        rt = build_ai_runtime(self._settings(audience="secret-looking-value"))
        self.assertFalse(rt.enabled)
        self.assertNotIn("secret-looking-value", rt.reason)

    def test_beta_over_cap_fails_closed(self) -> None:
        from server.config import AI_BETA_MAX_USERS
        many = tuple(f"t{i:03d}" for i in range(AI_BETA_MAX_USERS + 1))
        rt = build_ai_runtime(self._settings(audience="beta", beta_users=many))
        self.assertFalse(rt.enabled)
        self.assertIn("50", rt.reason)
        ok = build_ai_runtime(self._settings(audience="beta", beta_users=many[:AI_BETA_MAX_USERS]))
        self.assertTrue(ok.enabled)

    def test_beta_env_parsing_and_health_count_only(self) -> None:
        env = {"FAS_AI_AUDIENCE": "beta", "FAS_AI_BETA_USERS": "u1,u2, u2 ,bad id!,u3"}
        with mock.patch.dict(os.environ, env, clear=False):
            s = _ai_assistant_settings()
        self.assertEqual(s.beta_users, ("u1", "u2", "u3"), "khu trung + bo muc khong giong ID")
        st = replace(Settings(), data_backend="appwrite", ai_assistant=s)
        h = st._ai_health()
        self.assertEqual((h["audience"], h["beta_users"]), ("beta", 3))
        self.assertNotIn("u1", repr(h))
        self.assertNotIn("beta_users", replace(st, ai_assistant=replace(s, audience=""))._ai_health())

    def test_settings_without_audience_support_fail_closed(self) -> None:
        """Review (Antigravity Claude Opus, LOW #1): mot settings khong co `resolved_audience`
        khong duoc roi ve "all"."""
        from types import SimpleNamespace
        fake_ai = SimpleNamespace(enabled=True, providers=("mock",))
        rt = build_ai_runtime(SimpleNamespace(ai_assistant=fake_ai, data_backend="appwrite", environment="production"))
        self.assertFalse(rt.enabled)


class TestRoutesCanary(unittest.TestCase):
    def setUp(self) -> None:
        self.c = _client(_runtime("canary", {OWNER}))

    def test_stranger_sees_ai_as_off_and_every_other_route_is_403(self) -> None:
        a = self.c.get("/api/ai/availability", headers=_auth(STRANGER))
        self.assertEqual(a.status_code, 200)
        self.assertEqual(a.json()["enabled"], False)
        self.assertEqual(a.json()["reason"], "not_in_audience")
        self.assertNotIn("limits", a.json())
        calls = [
            ("get", "/api/ai/conversations", None),
            ("post", "/api/ai/conversations", {"mode": "general"}),
            ("get", "/api/ai/conversations/abc", None),
            ("delete", "/api/ai/conversations/abc", None),
            ("post", "/api/ai/conversations/abc/messages", {"content": "hi", "client_id": "c1"}),
            ("get", "/api/ai/preferences", None),
            ("put", "/api/ai/preferences", {"memory_enabled": True}),
            ("delete", "/api/ai/memory", None),
            ("get", "/api/ai/projects", None),
            ("post", "/api/ai/projects", {"title": "t"}),
            ("get", "/api/ai/projects/p1", None),
            ("put", "/api/ai/projects/p1", {"title": "t"}),
            ("delete", "/api/ai/projects/p1", None),
            ("post", "/api/ai/support/escalations", {"summary": "s"}),
        ]
        for method, path, body in calls:
            with self.subTest(path=path, method=method):
                kw = {"headers": _auth(STRANGER)}
                if body is not None:
                    kw["json"] = body
                r = getattr(self.c, method)(path, **kw)
                self.assertEqual(r.status_code, 403, r.text)
                self.assertEqual(r.json()["detail"]["code"], "ai_not_enabled")

    def test_owner_uses_ai_normally(self) -> None:
        a = self.c.get("/api/ai/availability", headers=_auth(OWNER)).json()
        self.assertTrue(a["enabled"])
        created = self.c.post("/api/ai/conversations", json={"mode": "general"}, headers=_auth(OWNER))
        self.assertEqual(created.status_code, 200, created.text)
        cid = created.json()["conversation_id"]
        with self.c.stream("POST", f"/api/ai/conversations/{cid}/messages",
                           json={"content": "xin chào", "client_id": "c1"}, headers=_auth(OWNER)) as r:
            body = "".join(r.iter_text())
        self.assertEqual(r.status_code, 200)
        self.assertIn("event: done", body)

    def test_anonymous_is_still_401_before_the_audience_check(self) -> None:
        self.assertEqual(self.c.get("/api/ai/conversations").status_code, 401)


class TestEveryRouteIsGated(unittest.TestCase):
    def test_raw_resolver_only_in_the_gate_and_availability(self) -> None:
        """Route moi phai di qua `_profile` — goi thang `resolve_profile` (ke ca
        qua `run_in_threadpool(resolve_profile, …)`, dung cho da lot o ban nhap
        dau) la bo qua khan gia."""
        import inspect
        import re as _re
        import server.ai_assistant.routes as routes_mod
        src = inspect.getsource(routes_mod.build_ai_router)
        # Goi `resolve_profile(` hoac truyen nhu ham `resolve_profile,` — khong dem chu thich.
        uses = _re.findall(r"\bresolve_profile\s*[(,]", src)
        self.assertEqual(len(uses), 2, "chi `_profile` va availability duoc dung resolve_profile tho")


class TestFlagOffUnchanged(unittest.TestCase):
    def test_disabled_runtime_still_503_for_everyone(self) -> None:
        c = _client(AiRuntime(False, reason="FAS_AI_ASSISTANT_V1 chưa bật"))
        r = c.get("/api/ai/conversations", headers=_auth(STRANGER))
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "ai_not_enabled")


if __name__ == "__main__":
    unittest.main()
