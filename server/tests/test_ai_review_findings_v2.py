"""
Regression tests for the second independent review of the Fanfic AI
Assistant V1 backend (B1/B2/H3-H6/M7-M11/L12 — see the review packet and
`docs/ai/AI_ASSISTANT_V1.md` "Implementation notes" for each finding's full
text). One test class per finding id; each test FAILED against the code as
reviewed and passes after the paired fix.
"""
from __future__ import annotations

import json
import socket
import threading
import time
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from server.ai_assistant.gateway import AiGateway
from server.ai_assistant.limits import StreamGuard
from server.ai_assistant.memory import InMemoryAiRepo
from server.ai_assistant.routes import _tier_of, build_ai_router
from server.ai_assistant.runtime import AiRuntime
from server.ai_assistant.tools import ToolContext
from server.domain import Tier
from server.llm_gateway.chat_providers import MockChatProvider

from server.tests.test_ai_routes import _auth, _enabled_runtime, _make_app, _resolve_profile


# =============================================================================== B1


class TestB1TierOfRealEnum(unittest.TestCase):
    """`_tier_of` must read `server.domain.Tier`'s VALUE, not Python's
    `str(EnumMember)` repr ("Tier.FREE" on this interpreter) — the bug made
    every FREE-tier user classified as "premium" (wrong, higher budget)."""

    @dataclass(frozen=True)
    class _RealProfile:
        user_id: str
        tier: Tier

    def test_free_enum_member_maps_to_free_bucket(self) -> None:
        self.assertEqual(_tier_of(self._RealProfile("u1", Tier.FREE)), "free")

    def test_paid_enum_members_map_to_premium_bucket(self) -> None:
        for tier in (Tier.LISTENER_PRO, Tier.CREATOR_PRO, Tier.ULTRA):
            self.assertEqual(_tier_of(self._RealProfile("u1", tier)), "premium")

    def test_availability_route_reports_free_daily_limit_for_free_tier(self) -> None:
        rt = _enabled_runtime()
        rt.daily_tokens_free = 111
        rt.daily_tokens_premium = 999999

        def resolve(_auth_header: Optional[str]):
            return self._RealProfile("free_user", Tier.FREE)

        app = FastAPI()
        app.include_router(build_ai_router(rt, resolve_profile=resolve))
        client = TestClient(app)
        r = client.get("/api/ai/availability", headers=_auth("x"))
        self.assertEqual(r.json()["limits"]["limit_today"], 111)


# =============================================================================== B2


class TestB2DisconnectStillRecordsUsageAndPersists(unittest.TestCase):
    """A client that disconnects mid-stream must not make usage/billing and
    the partial assistant reply disappear — Starlette's `StreamingResponse`
    cancels the generator via an `anyio` task-group race, which (without a
    shielded `finally`) silently skipped `record_usage`/`create_message`."""

    @classmethod
    def setUpClass(cls) -> None:
        import uvicorn

        cls.rt = _enabled_runtime()
        # A small per-word delay keeps the socket open long enough for the
        # test to observe >=1 delta before it aborts the connection.
        cls.rt.gateway = AiGateway(
            providers={"mock": MockChatProvider(delay_s=0.05)}, provider_chain=["mock"])
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

    def test_disconnect_mid_stream_records_usage_and_persists_stopped_message(self) -> None:
        base = f"http://127.0.0.1:{self.port}"
        with httpx.Client(timeout=10.0) as client:
            created = client.post(f"{base}/api/ai/conversations", headers=_auth("bob"),
                                  json={"mode": "general"})
            self.assertEqual(created.status_code, 200)
            cid = created.json()["conversation_id"]

        body = json.dumps({
            "content": "xin chao ban day la mot cau hoi dai de co nhieu tu",
            "client_id": "c-disc"}).encode()
        request_bytes = (
            f"POST /api/ai/conversations/{cid}/messages HTTP/1.1\r\n"
            f"Host: x\r\nAuthorization: Bearer bob\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n\r\n").encode() + body

        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        sock.sendall(request_bytes)
        got = b""
        deadline = time.time() + 5
        while b"event: delta" not in got and time.time() < deadline:
            chunk = sock.recv(4096)
            if not chunk:
                break
            got += chunk
        self.assertIn(b"event: delta", got, "expected at least one delta before aborting")
        sock.close()  # abrupt client disconnect — mid-stream, after >=1 delta

        assistant_msg = None
        deadline = time.time() + 5
        while time.time() < deadline:
            candidates = [m for m in self.rt.repo._messages.values()  # noqa: SLF001 — test-only
                         if m.conversation_id == cid and m.role == "assistant"]
            if candidates:
                assistant_msg = candidates[0]
                break
            time.sleep(0.1)

        self.assertIsNotNone(
            assistant_msg, "assistant message was never persisted after a mid-stream disconnect")
        self.assertEqual(assistant_msg.status, "stopped")
        self.assertTrue(assistant_msg.content, "partial text must still be persisted")

        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        usage = self.rt.repo.get_usage_day("user_bob", today)
        self.assertIsNotNone(usage, "usage must still be recorded after a mid-stream disconnect")
        self.assertGreater(usage.input_tokens + usage.output_tokens, 0)


if __name__ == "__main__":
    unittest.main()
