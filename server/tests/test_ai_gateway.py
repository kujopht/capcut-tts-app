"""Tests for server/ai_assistant/gateway.py — fallback-before-first-delta
policy, ai_provider_interrupted after a delta, circuit breaker reuse,
context trimming.
"""
from __future__ import annotations

import unittest
from typing import Iterator, List

from server.ai_assistant.gateway import AiGateway, ErrorEvent, trim_context
from server.llm_gateway.chat_provider import (
    ChatProvider, ChatTurn, Delta, Done, GenerateRequest, GenerateResult, ProviderCapabilities,
    ProviderError, ProviderUsageSnapshot, StreamEvent,
)
from server.llm_gateway.usage_limits import CircuitBreaker


class _StubProvider(ChatProvider):
    """Deterministic stub: `behavior` controls what `stream()` does."""

    def __init__(self, name: str, behavior: str):
        self.name = name
        self.behavior = behavior
        self.calls = 0

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(streaming=True, tools=False, web_search=False,
                                    vision=False, max_context_tokens=8000)

    def usage(self) -> ProviderUsageSnapshot:
        return ProviderUsageSnapshot()

    def generate(self, req: GenerateRequest) -> GenerateResult:
        raise NotImplementedError

    def stream(self, req: GenerateRequest) -> Iterator[StreamEvent]:
        self.calls += 1
        if self.behavior == "fail_before_first_delta":
            raise ProviderError("boom before any delta", transient=True, code="provider_network_error")
        if self.behavior == "fail_after_first_delta":
            yield Delta(text="Xin ")
            raise ProviderError("boom mid-stream", transient=True, code="provider_network_error")
        if self.behavior == "ok":
            yield Delta(text="Xin ")
            yield Delta(text="chào")
            yield Done(finish_reason="stop")
            return
        raise AssertionError(f"unknown behavior {self.behavior}")


def _messages() -> List[ChatTurn]:
    return [ChatTurn(role="system", content="you are helpful"),
            ChatTurn(role="user", content="hi")]


class TestFallbackPolicy(unittest.TestCase):
    def test_falls_back_to_next_provider_before_any_delta(self) -> None:
        a = _StubProvider("a", "fail_before_first_delta")
        b = _StubProvider("b", "ok")
        gw = AiGateway(providers={"a": a, "b": b}, provider_chain=["a", "b"])
        events = list(gw.stream(_messages(), mode="general"))
        deltas = [e for e in events if isinstance(e, Delta)]
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        self.assertEqual("".join(d.text for d in deltas), "Xin chào")
        self.assertEqual(errors, [])
        self.assertEqual(a.calls, 1)
        self.assertEqual(b.calls, 1)

    def test_does_not_fall_back_after_first_delta_emits_interrupted(self) -> None:
        a = _StubProvider("a", "fail_after_first_delta")
        b = _StubProvider("b", "ok")
        gw = AiGateway(providers={"a": a, "b": b}, provider_chain=["a", "b"])
        events = list(gw.stream(_messages(), mode="general"))
        deltas = [e for e in events if isinstance(e, Delta)]
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        self.assertEqual("".join(d.text for d in deltas), "Xin ")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].code, "ai_provider_interrupted")
        # b was NEVER called — two providers must not be silently stitched.
        self.assertEqual(b.calls, 0)

    def test_no_provider_configured_reports_no_provider(self) -> None:
        gw = AiGateway(providers={}, provider_chain=[])
        events = list(gw.stream(_messages(), mode="general"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].code, "ai_no_provider")

    def test_all_providers_fail_reports_provider_unavailable(self) -> None:
        a = _StubProvider("a", "fail_before_first_delta")
        b = _StubProvider("b", "fail_before_first_delta")
        gw = AiGateway(providers={"a": a, "b": b}, provider_chain=["a", "b"])
        events = list(gw.stream(_messages(), mode="general"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].code, "ai_provider_unavailable")


class TestCircuitBreakerReuse(unittest.TestCase):
    def test_open_circuit_skips_provider(self) -> None:
        a = _StubProvider("a", "fail_before_first_delta")
        b = _StubProvider("b", "ok")
        breaker = CircuitBreaker(failure_threshold=1, open_seconds=999.0)
        gw = AiGateway(providers={"a": a, "b": b}, provider_chain=["a", "b"], circuit_breaker=breaker)
        # First call opens the breaker for 'a' after one failure.
        list(gw.stream(_messages(), mode="general"))
        self.assertTrue(breaker.is_open("a"))
        a.calls = 0
        # Second call must skip 'a' entirely (breaker open) and go straight to 'b'.
        events = list(gw.stream(_messages(), mode="general"))
        self.assertEqual(a.calls, 0)
        self.assertEqual(b.calls, 2)
        deltas = [e for e in events if isinstance(e, Delta)]
        self.assertEqual("".join(d.text for d in deltas), "Xin chào")


class TestTrimContext(unittest.TestCase):
    def test_keeps_system_turns_and_most_recent_others(self) -> None:
        system = ChatTurn(role="system", content="s" * 10)
        old = ChatTurn(role="user", content="o" * 4000)
        recent = ChatTurn(role="user", content="r" * 10)
        trimmed = trim_context([system, old, recent], max_tokens=50)
        self.assertIn(system, trimmed)
        self.assertIn(recent, trimmed)
        self.assertNotIn(old, trimmed)

    def test_always_keeps_at_least_one_non_system_turn(self) -> None:
        system = ChatTurn(role="system", content="s")
        huge = ChatTurn(role="user", content="x" * 100000)
        trimmed = trim_context([system, huge], max_tokens=1)
        self.assertIn(huge, trimmed)


if __name__ == "__main__":
    unittest.main()
