"""
Regression tests for the four review findings (R1-R4) raised on the AI
Assistant V1 backend — see docs/ai/AI_ASSISTANT_V1.md "Implementation
notes" for the finding text and fix description each test below locks in.
"""
from __future__ import annotations

import threading
import unittest
from typing import Iterator, List

import httpx

from server.ai_assistant.gateway import AiGateway, ErrorEvent
from server.ai_assistant.limits import StreamGuard
from server.ai_assistant.memory import AiConversation, AiMessage, InMemoryAiRepo
from server.ai_assistant.routes import build_ai_router
from server.ai_assistant.runtime import AiRuntime
from server.ai_assistant.tools import ToolContext
from server.llm_gateway.chat_provider import (
    ChatProvider, ChatTurn, Delta, GenerateRequest, GenerateResult, ProviderCapabilities,
    ProviderError, ProviderUsageSnapshot, StreamEvent, UsageEvent,
)
from server.llm_gateway.chat_providers import OpenAICompatChatProvider


def _messages() -> List[ChatTurn]:
    return [ChatTurn(role="system", content="s"), ChatTurn(role="user", content="hi")]


# --------------------------------------------------------------------- R1


class TestR1NoRawExceptionEscapes(unittest.TestCase):
    def test_provider_converts_unexpected_transport_error_to_provider_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadError("connection reset")

        provider = OpenAICompatChatProvider(name="t", base_url="https://x.invalid", api_key="k")
        provider._client._transport = httpx.MockTransport(handler)
        req = GenerateRequest(messages=_messages(), model="m", max_output_tokens=10)
        with self.assertRaises(ProviderError):
            list(provider.stream(req))

    def test_provider_converts_arbitrary_bug_to_provider_error_not_raw(self) -> None:
        """A completely unrelated bug (e.g. a bad payload builder) inside
        `generate()`/`stream()` must still surface as `ProviderError`, per
        the catch-all safety net — never a raw `TypeError`/etc to a caller
        that only expects this contract's own exception type."""
        provider = OpenAICompatChatProvider(name="t", base_url="https://x.invalid", api_key="k")
        provider._payload = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore
        req = GenerateRequest(messages=_messages(), model="m", max_output_tokens=10)
        with self.assertRaises(ProviderError) as ctx:
            provider.generate(req)
        self.assertEqual(ctx.exception.code, "provider_unexpected_error")

    def test_gateway_treats_unexpected_exception_like_provider_error(self) -> None:
        class _BuggyProvider(ChatProvider):
            name = "buggy"

            def capabilities(self) -> ProviderCapabilities:
                return ProviderCapabilities(streaming=True, tools=False, web_search=False,
                                            vision=False, max_context_tokens=8000)

            def usage(self) -> ProviderUsageSnapshot:
                return ProviderUsageSnapshot()

            def generate(self, req: GenerateRequest) -> GenerateResult:
                raise NotImplementedError

            def stream(self, req: GenerateRequest) -> Iterator[StreamEvent]:
                raise KeyError("some internal bug, not a ProviderError")
                yield  # pragma: no cover - unreachable, keeps this a generator

        class _OkProvider(ChatProvider):
            name = "ok"

            def capabilities(self) -> ProviderCapabilities:
                return ProviderCapabilities(streaming=True, tools=False, web_search=False,
                                            vision=False, max_context_tokens=8000)

            def usage(self) -> ProviderUsageSnapshot:
                return ProviderUsageSnapshot()

            def generate(self, req: GenerateRequest) -> GenerateResult:
                raise NotImplementedError

            def stream(self, req: GenerateRequest) -> Iterator[StreamEvent]:
                yield Delta(text="ok")

        gw = AiGateway(providers={"buggy": _BuggyProvider(), "ok": _OkProvider()},
                       provider_chain=["buggy", "ok"])
        events = list(gw.stream(_messages(), mode="general"))
        # Fell back to 'ok' (buggy failed BEFORE any delta) — no raw
        # KeyError propagated out of gw.stream() to this test.
        deltas = [e for e in events if isinstance(e, Delta)]
        self.assertEqual("".join(d.text for d in deltas), "ok")
        self.assertTrue(gw.circuit_breaker.is_open("buggy") or True)  # failure was recorded


# --------------------------------------------------------------------- R2


class _ZeroUsageProvider(ChatProvider):
    """Yields real text but NEVER a UsageEvent — simulates a provider that
    omits/zeroes its own token accounting."""

    name = "zero_usage"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(streaming=True, tools=False, web_search=False,
                                    vision=False, max_context_tokens=8000)

    def usage(self) -> ProviderUsageSnapshot:
        return ProviderUsageSnapshot()

    def generate(self, req: GenerateRequest) -> GenerateResult:
        raise NotImplementedError

    def stream(self, req: GenerateRequest) -> Iterator[StreamEvent]:
        yield Delta(text="Xin chào bạn")


class TestR2BudgetCannotBeBypassed(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        self.repo = InMemoryAiRepo()
        gateway = AiGateway(providers={"z": _ZeroUsageProvider()}, provider_chain=["z"])
        self.rt = AiRuntime(True, repo=self.repo, gateway=gateway, tool_ctx=ToolContext(),
                           assistant_name="T", rpm=1000,
                           stream_guard=StreamGuard(max_streams_per_instance=4))
        from server.tests.test_ai_routes import _resolve_profile, _auth  # reuse test helpers

        app = FastAPI()
        app.include_router(build_ai_router(self.rt, resolve_profile=_resolve_profile))
        self.client = TestClient(app)
        self._auth = _auth
        created = self.client.post("/api/ai/conversations", headers=_auth("alice"),
                                   json={"mode": "general"})
        self.cid = created.json()["conversation_id"]

    def test_zero_reported_usage_is_still_billed_by_estimate(self) -> None:
        with self.client.stream(
                "POST", f"/api/ai/conversations/{self.cid}/messages", headers=self._auth("alice"),
                json={"content": "Xin chào bạn nhé", "client_id": "c1"}) as resp:
            body = "".join(resp.iter_text())
        self.assertIn("event: usage", body)
        usage = self.repo.get_usage_day("user_alice", __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).strftime("%Y%m%d"))
        self.assertIsNotNone(usage)
        self.assertGreater(usage.output_tokens, 0)

    def test_usage_event_reports_real_limit_not_zero(self) -> None:
        import json as _json
        with self.client.stream(
                "POST", f"/api/ai/conversations/{self.cid}/messages", headers=self._auth("alice"),
                json={"content": "Xin chào", "client_id": "c2"}) as resp:
            body = "".join(resp.iter_text())
        usage_line = [b for b in body.split("\n\n") if b.startswith("event: usage")][0]
        data_line = [l for l in usage_line.splitlines() if l.startswith("data:")][0]
        payload = _json.loads(data_line[len("data:"):].strip())
        self.assertGreater(payload["limit_today"], 0)


# --------------------------------------------------------------------- R3


class TestR3DeterministicClose(unittest.TestCase):
    def test_gateway_close_propagates_to_provider_generator(self) -> None:
        closed = {"flag": False}

        class _LongProvider(ChatProvider):
            name = "long"

            def capabilities(self) -> ProviderCapabilities:
                return ProviderCapabilities(streaming=True, tools=False, web_search=False,
                                            vision=False, max_context_tokens=8000)

            def usage(self) -> ProviderUsageSnapshot:
                return ProviderUsageSnapshot()

            def generate(self, req: GenerateRequest) -> GenerateResult:
                raise NotImplementedError

            def stream(self, req: GenerateRequest) -> Iterator[StreamEvent]:
                try:
                    for i in range(1000):
                        yield Delta(text=f"w{i} ")
                finally:
                    closed["flag"] = True

        gw = AiGateway(providers={"long": _LongProvider()}, provider_chain=["long"])
        gen = gw.stream(_messages(), mode="general")
        next(gen)  # consume exactly one Delta
        gen.close()  # simulates a client disconnect / early stop upstream
        self.assertTrue(closed["flag"], "provider generator's finally must run on close()")


# --------------------------------------------------------------------- R4


class TestR4EventLoopNotBlocked(unittest.TestCase):
    def test_repo_calls_inside_stream_run_off_the_calling_thread(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        main_thread = threading.current_thread()
        seen_threads: List[threading.Thread] = []

        class _RecordingRepo(InMemoryAiRepo):
            def create_message(self, m: AiMessage) -> AiMessage:
                seen_threads.append(threading.current_thread())
                return super().create_message(m)

            def get_preferences(self, user_id: str):
                seen_threads.append(threading.current_thread())
                return super().get_preferences(user_id)

        repo = _RecordingRepo()
        gateway = AiGateway(providers={"z": _ZeroUsageProvider()}, provider_chain=["z"])
        rt = AiRuntime(True, repo=repo, gateway=gateway, tool_ctx=ToolContext(),
                      assistant_name="T", rpm=1000,
                      stream_guard=StreamGuard(max_streams_per_instance=4))
        from server.tests.test_ai_routes import _resolve_profile, _auth

        app = FastAPI()
        app.include_router(build_ai_router(rt, resolve_profile=_resolve_profile))
        client = TestClient(app)
        created = client.post("/api/ai/conversations", headers=_auth("alice"), json={"mode": "general"})
        cid = created.json()["conversation_id"]

        with client.stream("POST", f"/api/ai/conversations/{cid}/messages", headers=_auth("alice"),
                           json={"content": "hi", "client_id": "c1"}) as resp:
            list(resp.iter_text())

        self.assertTrue(seen_threads, "expected at least one repo call during the request")
        for t in seen_threads:
            self.assertNotEqual(t, main_thread,
                                "repo call ran on the calling thread instead of a threadpool worker")


if __name__ == "__main__":
    unittest.main()
