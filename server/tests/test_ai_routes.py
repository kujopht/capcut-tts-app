"""
Tests for server/ai_assistant/routes.py — flag off -> 503 ai_not_enabled,
auth required, availability shape, conversation CRUD, and SSE stream event
order (read via TestClient's own httpx transport, which does NOT need to
buffer the whole body before returning individual lines here — the classic
"TestClient buffers SSE" pitfall applies to `starlette.testclient` built on
`requests`; this repo's FastAPI TestClient is httpx-based and `.stream()`
enumerates lines as-produced). ONE additional test spins up a real
`uvicorn` server on a random 127.0.0.1 port to prove the endpoint also
works over a real socket, not just the ASGI test transport.
"""
from __future__ import annotations

import json
import threading
import time
import unittest
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from server.ai_assistant.memory import InMemoryAiRepo
from server.ai_assistant.gateway import AiGateway
from server.ai_assistant.routes import build_ai_router
from server.ai_assistant.runtime import AiRuntime
from server.ai_assistant.tools import ToolContext
from server.llm_gateway.chat_providers import MockChatProvider


@dataclass(frozen=True)
class _Profile:
    user_id: str
    tier: str = "free"


def _resolve_profile(authorization: Optional[str]) -> _Profile:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cần đăng nhập.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cần đăng nhập.")
    return _Profile(user_id=f"user_{token}")


def _enabled_runtime(*, max_streams: int = 4) -> AiRuntime:
    repo = InMemoryAiRepo()
    gateway = AiGateway(providers={"mock": MockChatProvider()}, provider_chain=["mock"])
    from server.ai_assistant.limits import StreamGuard
    return AiRuntime(True, repo=repo, gateway=gateway, tool_ctx=ToolContext(),
                     assistant_name="Fanfic AI Test", rpm=1000,
                     stream_guard=StreamGuard(max_streams_per_instance=max_streams))


def _make_app(rt: AiRuntime) -> FastAPI:
    app = FastAPI()
    app.include_router(build_ai_router(rt, resolve_profile=_resolve_profile))
    return app


def _auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _parse_sse_events(body: str):
    events = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        event_name, data = "message", None
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:"):].strip())
        if data is not None:
            events.append((event_name, data))
    return events


class TestFlagOff(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(_make_app(AiRuntime(False, reason="FAS_AI_ASSISTANT_V1 chưa bật")))

    def test_availability_is_200_even_when_off(self) -> None:
        r = self.client.get("/api/ai/availability", headers=_auth("u1"))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["enabled"])
        # Người dùng thường chỉ nhận mã ổn định "off" — chi tiết cấu hình (tên biến môi trường) chỉ dành cho Owner
        # (xem `test_ai_access.py`), để mọi tài khoản đã đăng nhập không đọc được cấu hình máy chủ.
        self.assertEqual(body["reason"], "off")
        self.assertNotIn("FAS_AI", json.dumps(body))

    def test_conversations_list_returns_503_ai_not_enabled(self) -> None:
        r = self.client.get("/api/ai/conversations", headers=_auth("u1"))
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "ai_not_enabled")

    def test_post_message_returns_503_ai_not_enabled(self) -> None:
        r = self.client.post("/api/ai/conversations/x/messages", headers=_auth("u1"),
                             json={"content": "hi", "client_id": "c1"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "ai_not_enabled")


class TestAuthRequired(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(_make_app(_enabled_runtime()))

    def test_missing_authorization_is_401(self) -> None:
        r = self.client.get("/api/ai/availability")
        self.assertEqual(r.status_code, 401)

    def test_conversations_requires_auth(self) -> None:
        r = self.client.get("/api/ai/conversations")
        self.assertEqual(r.status_code, 401)


class TestAvailabilityShape(unittest.TestCase):
    def test_shape_when_enabled(self) -> None:
        client = TestClient(_make_app(_enabled_runtime()))
        r = client.get("/api/ai/availability", headers=_auth("u1"))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        for key in ("enabled", "reason", "name", "modes", "web_search", "limits"):
            self.assertIn(key, body)
        self.assertTrue(body["enabled"])
        self.assertEqual(body["name"], "Fanfic AI Test")
        self.assertIn("general", body["modes"])
        for key in ("used_today", "limit_today", "reset_at"):
            self.assertIn(key, body["limits"])


class TestConversationCrud(unittest.TestCase):
    def setUp(self) -> None:
        self.rt = _enabled_runtime()
        self.client = TestClient(_make_app(self.rt))

    def test_create_list_get_delete(self) -> None:
        created = self.client.post("/api/ai/conversations", headers=_auth("alice"),
                                   json={"mode": "general"})
        self.assertEqual(created.status_code, 200)
        cid = created.json()["conversation_id"]

        listed = self.client.get("/api/ai/conversations", headers=_auth("alice"))
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["items"]), 1)

        got = self.client.get(f"/api/ai/conversations/{cid}", headers=_auth("alice"))
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["conversation_id"], cid)

        deleted = self.client.delete(f"/api/ai/conversations/{cid}", headers=_auth("alice"))
        self.assertEqual(deleted.status_code, 200)
        gone = self.client.get(f"/api/ai/conversations/{cid}", headers=_auth("alice"))
        self.assertEqual(gone.status_code, 404)
        self.assertEqual(gone.json()["detail"]["code"], "ai_not_found")

    def test_ownership_is_enforced(self) -> None:
        created = self.client.post("/api/ai/conversations", headers=_auth("alice"),
                                   json={"mode": "general"})
        cid = created.json()["conversation_id"]
        r = self.client.get(f"/api/ai/conversations/{cid}", headers=_auth("bob"))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"]["code"], "ai_forbidden")

    def test_invalid_mode_falls_back_to_general(self) -> None:
        created = self.client.post("/api/ai/conversations", headers=_auth("alice"),
                                   json={"mode": "not_a_real_mode"})
        self.assertEqual(created.json()["mode"], "general")


class TestPreferencesAndMemory(unittest.TestCase):
    def setUp(self) -> None:
        self.rt = _enabled_runtime()
        self.client = TestClient(_make_app(self.rt))

    def test_default_preferences(self) -> None:
        r = self.client.get("/api/ai/preferences", headers=_auth("alice"))
        self.assertEqual(r.json(), {"memory_enabled": True, "preferences": {}})

    def test_put_then_get_preferences(self) -> None:
        self.client.put("/api/ai/preferences", headers=_auth("alice"),
                        json={"memory_enabled": False, "preferences": {"lang": "vi"}})
        r = self.client.get("/api/ai/preferences", headers=_auth("alice"))
        body = r.json()
        self.assertFalse(body["memory_enabled"])
        self.assertEqual(body["preferences"], {"lang": "vi"})

    def test_delete_memory_removes_conversations(self) -> None:
        self.client.post("/api/ai/conversations", headers=_auth("alice"), json={"mode": "general"})
        self.client.delete("/api/ai/memory", headers=_auth("alice"))
        listed = self.client.get("/api/ai/conversations", headers=_auth("alice"))
        self.assertEqual(listed.json()["items"], [])


class TestStreamEventOrder(unittest.TestCase):
    def setUp(self) -> None:
        self.rt = _enabled_runtime()
        self.client = TestClient(_make_app(self.rt))
        created = self.client.post("/api/ai/conversations", headers=_auth("alice"),
                                   json={"mode": "general"})
        self.conversation_id = created.json()["conversation_id"]

    def test_event_order_meta_delta_usage_done(self) -> None:
        with self.client.stream(
                "POST", f"/api/ai/conversations/{self.conversation_id}/messages",
                headers=_auth("alice"), json={"content": "Xin chào bạn", "client_id": "c1"}) as resp:
            self.assertEqual(resp.status_code, 200)
            body = "".join(resp.iter_text())
        events = _parse_sse_events(body)
        names = [name for name, _ in events]
        self.assertEqual(names[0], "meta")
        self.assertEqual(names[-1], "done")
        self.assertIn("delta", names)
        self.assertIn("usage", names)
        # every delta must come before usage/done
        first_usage = names.index("usage")
        last_delta = max(i for i, n in enumerate(names) if n == "delta")
        self.assertLess(last_delta, first_usage)

    def test_stream_persists_assistant_message(self) -> None:
        with self.client.stream(
                "POST", f"/api/ai/conversations/{self.conversation_id}/messages",
                headers=_auth("alice"), json={"content": "Xin chào bạn", "client_id": "c2"}) as resp:
            list(resp.iter_text())
        got = self.client.get(f"/api/ai/conversations/{self.conversation_id}", headers=_auth("alice"))
        roles = [m["role"] for m in got.json()["messages"]]
        self.assertEqual(roles, ["user", "assistant"])


class TestRealUvicornStream(unittest.TestCase):
    """One genuine socket-level test — proves the SSE route also works over
    a real HTTP connection (not just the ASGI test transport), per the
    mission brief's explicit ask for at least one such test."""

    @classmethod
    def setUpClass(cls) -> None:
        import uvicorn

        cls.rt = _enabled_runtime()
        app = _make_app(cls.rt)
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="critical")
        cls.server = uvicorn.Server(config)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        for _ in range(200):
            if getattr(cls.server, "started", False):
                break
            time.sleep(0.02)
        cls.port = cls.server.servers[0].sockets[0].getsockname()[1]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.should_exit = True
        cls.thread.join(timeout=5)

    def test_stream_over_real_socket(self) -> None:
        base = f"http://127.0.0.1:{self.port}"
        with httpx.Client(timeout=10.0) as client:
            created = client.post(f"{base}/api/ai/conversations", headers=_auth("alice"),
                                  json={"mode": "general"})
            cid = created.json()["conversation_id"]
            lines = []
            with client.stream(
                    "POST", f"{base}/api/ai/conversations/{cid}/messages", headers=_auth("alice"),
                    json={"content": "chào", "client_id": "real1"}) as resp:
                self.assertEqual(resp.status_code, 200)
                for line in resp.iter_lines():
                    lines.append(line)
        body = "\n".join(lines) + "\n\n"
        events = _parse_sse_events(body)
        self.assertGreaterEqual(len(events), 3)
        self.assertEqual(events[0][0], "meta")


if __name__ == "__main__":
    unittest.main()
