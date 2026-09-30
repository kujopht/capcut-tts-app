"""
Admin-AI readiness (release gate, phase 5) — the minimal hooks a future
`/admin/ai` needs, WITHOUT building that admin: 429 cooldown honouring
`Retry-After`, a server-side health read model, runtime enable/priority via
`provider_chain`, and the serving provider/model recorded server-side only.
"""
from __future__ import annotations

import json
import unittest
from typing import Iterator, List

import httpx
from fastapi.testclient import TestClient

from server.ai_assistant.gateway import DEFAULT_429_COOLDOWN_S, AiGateway, ProviderServed
from server.llm_gateway.chat_provider import (
    ChatProvider, ChatTurn, Delta, Done, GenerateRequest, GenerateResult, ProviderCapabilities,
    ProviderError, ProviderUsageSnapshot, StreamEvent,
)
from server.llm_gateway.chat_providers import (
    RETRY_AFTER_MAX_S, RETRY_AFTER_MIN_S, OpenAICompatChatProvider, _retry_after_s,
)
from server.llm_gateway.usage_limits import CircuitBreaker

from server.tests.test_ai_routes import _auth, _enabled_runtime, _make_app


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class _Scripted(ChatProvider):
    def __init__(self, name: str, *, fail: ProviderError | None = None) -> None:
        self.name = name
        self._default_model = f"{name}-model"
        self.fail = fail
        self.calls = 0

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(streaming=True, tools=False, web_search=False, vision=False,
                                    max_context_tokens=8000)

    def generate(self, req: GenerateRequest) -> GenerateResult:  # pragma: no cover
        raise NotImplementedError

    def stream(self, req: GenerateRequest) -> Iterator[StreamEvent]:
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        yield Delta(text=f"từ {self.name}")
        yield Done()

    def usage(self) -> ProviderUsageSnapshot:
        return ProviderUsageSnapshot(requests=self.calls)


def _turns() -> List[ChatTurn]:
    return [ChatTurn(role="user", content="xin chào")]


class TestRetryAfterParsing(unittest.TestCase):
    def _resp(self, status: int, value: str | None) -> httpx.Response:
        headers = {"retry-after": value} if value is not None else {}
        return httpx.Response(status, headers=headers)

    def test_seconds_form_is_clamped(self) -> None:
        self.assertEqual(_retry_after_s(self._resp(429, "7")), 7.0)
        self.assertEqual(_retry_after_s(self._resp(429, "0")), RETRY_AFTER_MIN_S)
        self.assertEqual(_retry_after_s(self._resp(429, "999999")), RETRY_AFTER_MAX_S)

    def test_missing_date_form_or_non_429_is_none(self) -> None:
        self.assertIsNone(_retry_after_s(self._resp(429, None)))
        self.assertIsNone(_retry_after_s(self._resp(429, "Wed, 21 Oct 2026 07:28:00 GMT")))
        self.assertIsNone(_retry_after_s(self._resp(503, "7")))

    def test_openai_compat_stream_429_carries_retry_after(self) -> None:
        provider = OpenAICompatChatProvider(name="t", base_url="https://example.invalid/v1",
                                            api_key="sk-test")
        provider._client._transport = httpx.MockTransport(
            lambda req: httpx.Response(429, headers={"retry-after": "12"}, content=b"slow down"))
        req = GenerateRequest(messages=_turns(), model="m", max_output_tokens=10)
        with self.assertRaises(ProviderError) as ctx:
            list(provider.stream(req))
        self.assertEqual(ctx.exception.code, "provider_http_429")
        self.assertEqual(ctx.exception.retry_after_s, 12.0)
        self.assertTrue(ctx.exception.transient)


class TestCircuitBreakerCooldown(unittest.TestCase):
    def test_cool_down_opens_immediately_and_never_shortens(self) -> None:
        clock = _Clock()
        cb = CircuitBreaker(failure_threshold=3, open_seconds=60, clock_fn=clock)
        cb.cool_down("a", 120)
        self.assertTrue(cb.is_open("a"))
        cb.cool_down("a", 5)  # a shorter later hint must not shorten the window
        self.assertAlmostEqual(cb.snapshot()["a"]["open_for_s"], 120)
        clock.t += 121
        self.assertFalse(cb.is_open("a"))
        self.assertEqual(cb.snapshot()["a"]["open_for_s"], 0.0)

    def test_concurrent_failure_never_shortens_a_429_window(self) -> None:
        """Independent review: stream B's 429 opens 600 s; stream A (already
        past is_open) then fails with a 5xx at the failure threshold —
        record_failure must not cut the window to open_seconds."""
        clock = _Clock()
        cb = CircuitBreaker(failure_threshold=2, open_seconds=60, clock_fn=clock)
        cb.cool_down("a", 600)
        cb.record_failure("a")  # consecutive_failures reaches the threshold here
        self.assertAlmostEqual(cb.snapshot()["a"]["open_for_s"], 600)


class TestGateway429AndHealth(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _Clock()
        self.cb = CircuitBreaker(clock_fn=self.clock)

    def _gw(self, *providers: _Scripted) -> AiGateway:
        return AiGateway(providers={p.name: p for p in providers},
                         provider_chain=[p.name for p in providers], circuit_breaker=self.cb)

    def test_429_before_first_delta_falls_back_and_cools_down_for_retry_after(self) -> None:
        a = _Scripted("a", fail=ProviderError("429", code="provider_http_429", retry_after_s=120))
        b = _Scripted("b")
        gw = self._gw(a, b)
        events = list(gw.stream(_turns(), mode="general"))
        self.assertEqual([e.text for e in events if isinstance(e, Delta)], ["từ b"])
        self.assertEqual(gw.health()["a"]["cooling_down_s"], 120.0)
        list(gw.stream(_turns(), mode="general"))
        self.assertEqual(a.calls, 1, "a cooled-down provider must not be hit again")
        self.clock.t += 121
        list(gw.stream(_turns(), mode="general"))
        self.assertEqual(a.calls, 2, "cooldown ends on time")

    def test_429_without_retry_after_uses_default_cooldown(self) -> None:
        a = _Scripted("a", fail=ProviderError("429", code="provider_http_429"))
        gw = self._gw(a, _Scripted("b"))
        list(gw.stream(_turns(), mode="general"))
        self.assertEqual(gw.health()["a"]["cooling_down_s"], DEFAULT_429_COOLDOWN_S)

    def test_other_failures_keep_the_threshold_policy(self) -> None:
        a = _Scripted("a", fail=ProviderError("boom", code="provider_http_500"))
        gw = self._gw(a, _Scripted("b"))
        list(gw.stream(_turns(), mode="general"))
        self.assertEqual(gw.health()["a"]["cooling_down_s"], 0.0)
        self.assertEqual(gw.health()["a"]["consecutive_failures"], 1)

    def test_provider_served_is_yielded_once_for_the_answering_provider(self) -> None:
        a = _Scripted("a", fail=ProviderError("down", code="provider_http_503"))
        gw = self._gw(a, _Scripted("b"))
        served = [e for e in gw.stream(_turns(), mode="general") if isinstance(e, ProviderServed)]
        self.assertEqual(served, [ProviderServed(provider_name="b", model="b-model")])

    def test_runtime_chain_change_disables_and_reorders(self) -> None:
        a, b = _Scripted("a"), _Scripted("b")
        gw = self._gw(a, b)
        gw.provider_chain = ["b"]  # what a future /admin/ai "disable a" does
        list(gw.stream(_turns(), mode="general"))
        self.assertEqual((a.calls, b.calls), (0, 1))
        h = gw.health()
        self.assertEqual((h["a"]["enabled"], h["a"]["priority"]), (False, None))
        self.assertEqual((h["b"]["enabled"], h["b"]["priority"]), (True, 0))

    def test_health_never_contains_key_or_url(self) -> None:
        secret = "sk-" + "healthcheck" * 3
        real = OpenAICompatChatProvider(name="q", base_url="https://secret-host.invalid/v1", api_key=secret)
        gw = AiGateway(providers={"q": real}, provider_chain=["q"])
        dumped = json.dumps(gw.health())
        self.assertNotIn(secret, dumped)
        self.assertNotIn("secret-host", dumped)


class TestServedProviderIsServerSideOnly(unittest.TestCase):
    def test_persisted_but_never_sent_to_the_client(self) -> None:
        rt = _enabled_runtime()
        rt.gateway = AiGateway(providers={"b": _Scripted("b")}, provider_chain=["b"])
        client = TestClient(_make_app(rt))
        cid = client.post("/api/ai/conversations", headers=_auth("u"),
                          json={"mode": "general"}).json()["conversation_id"]
        r = client.post(f"/api/ai/conversations/{cid}/messages", headers=_auth("u"),
                        json={"content": "xin chào", "client_id": "c1"})
        self.assertNotIn("b-model", r.text)
        detail = client.get(f"/api/ai/conversations/{cid}", headers=_auth("u")).text
        self.assertNotIn("b-model", detail)
        self.assertNotIn("provider_name", detail)
        msg = [m for m in rt.repo._messages.values()  # noqa: SLF001 — test-only
               if m.conversation_id == cid and m.role == "assistant"][0]
        self.assertEqual((msg.provider_name, msg.model), ("b", "b-model"))


if __name__ == "__main__":
    unittest.main()
