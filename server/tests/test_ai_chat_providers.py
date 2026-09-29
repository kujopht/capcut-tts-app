"""Tests for server/llm_gateway/chat_provider(s).py — SSE parsing, usage,
Azure URL/header shape, provider exclusion on missing key, Mock stream.
No network: every HTTP-shaped provider uses `httpx.MockTransport`.
"""
from __future__ import annotations

import json
import os
import unittest

import httpx

from server.ai_assistant.config import resolve_provider_chain
from server.config import AiAssistantSettings
from server.llm_gateway.chat_provider import (
    ChatTurn, Delta, Done, GenerateRequest, ProviderError, UsageEvent,
)
from server.llm_gateway.chat_providers import (
    AzureOpenAIProvider, MockChatProvider, OpenAICompatChatProvider, QwenDashScopeProvider,
)


class TestAssertWorktree(unittest.TestCase):
    def test_server_module_is_from_this_worktree(self) -> None:
        import server
        self.assertIn("ai-assistant-backend", server.__file__.replace("\\", "/"))


def _sse_body(chunks):
    lines = []
    for c in chunks:
        lines.append(f"data: {json.dumps(c)}")
    lines.append("data: [DONE]")
    return "\n\n".join(lines) + "\n\n"


class TestOpenAICompatStreaming(unittest.TestCase):
    def _provider(self, handler):
        # Build the provider normally (so it wires its OWN client with the
        # real base_url/Authorization header), then swap only the
        # transport — this exercises the actual header-setting code path,
        # not a test double that bypasses it.
        provider = OpenAICompatChatProvider(
            name="test", base_url="https://example.invalid/v1", api_key="sk-test")
        provider._client._transport = httpx.MockTransport(handler)
        return provider

    def test_stream_parses_deltas_and_usage_and_done(self) -> None:
        body = _sse_body([
            {"choices": [{"delta": {"content": "Xin"}}]},
            {"choices": [{"delta": {"content": " chào"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 10, "completion_tokens": 2}},
        ])

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertTrue(request.url.path.endswith("/chat/completions"))
            self.assertEqual(request.headers.get("authorization"), "Bearer sk-test")
            return httpx.Response(200, content=body.encode("utf-8"),
                                  headers={"content-type": "text/event-stream"})

        provider = self._provider(handler)
        req = GenerateRequest(messages=[ChatTurn(role="user", content="hi")],
                              model="test-model", max_output_tokens=100)
        events = list(provider.stream(req))
        deltas = [e for e in events if isinstance(e, Delta)]
        usages = [e for e in events if isinstance(e, UsageEvent)]
        dones = [e for e in events if isinstance(e, Done)]
        self.assertEqual("".join(d.text for d in deltas), "Xin chào")
        self.assertEqual(len(usages), 1)
        self.assertEqual(usages[0].input_tokens, 10)
        self.assertEqual(usages[0].output_tokens, 2)
        self.assertEqual(len(dones), 1)
        self.assertEqual(dones[0].finish_reason, "stop")

    def test_generate_non_streaming_usage(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "Xin chào"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3}})

        provider = self._provider(handler)
        req = GenerateRequest(messages=[ChatTurn(role="user", content="hi")],
                              model="test-model", max_output_tokens=100)
        result = provider.generate(req)
        self.assertEqual(result.text, "Xin chào")
        self.assertEqual(result.input_tokens, 5)
        self.assertEqual(result.output_tokens, 3)

    def test_http_error_before_any_delta_raises_provider_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, content=b"boom")

        provider = self._provider(handler)
        req = GenerateRequest(messages=[ChatTurn(role="user", content="hi")],
                              model="test-model", max_output_tokens=100)
        with self.assertRaises(ProviderError) as ctx:
            list(provider.stream(req))
        self.assertTrue(ctx.exception.transient)

    def test_empty_response_raises_on_generate(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

        provider = self._provider(handler)
        req = GenerateRequest(messages=[ChatTurn(role="user", content="hi")],
                              model="m", max_output_tokens=10)
        with self.assertRaises(ProviderError):
            provider.generate(req)


class TestAzureOpenAIProvider(unittest.TestCase):
    def test_url_shape_and_api_key_header(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["query"] = str(request.url.query, "utf-8")
            seen["api_key_header"] = request.headers.get("api-key")
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "ok"}}], "usage": {}})

        provider = AzureOpenAIProvider(
            endpoint="https://myres.openai.azure.com", api_key="azkey",
            deployment="gpt-4o-mini", api_version="2024-06-01")
        provider._client._transport = httpx.MockTransport(handler)
        req = GenerateRequest(messages=[ChatTurn(role="user", content="hi")],
                              model="gpt-4o-mini", max_output_tokens=10)
        provider.generate(req)
        self.assertIn("/openai/deployments/gpt-4o-mini/chat/completions", seen["path"])
        self.assertEqual(seen["query"], "api-version=2024-06-01")
        self.assertEqual(seen["api_key_header"], "azkey")

    def test_missing_config_raises_not_configured(self) -> None:
        with self.assertRaises(ProviderError):
            AzureOpenAIProvider(endpoint="", api_key="", deployment="")


class TestProviderExclusion(unittest.TestCase):
    def test_missing_key_excludes_provider_with_reason_logged(self) -> None:
        settings = AiAssistantSettings(providers=("qwen", "azure_openai", "mock"))
        chain = resolve_provider_chain(settings, environment="development")
        # qwen/azure_openai have no keys configured -> excluded; mock always usable.
        self.assertEqual(chain, ["mock"])

    def test_configured_qwen_is_kept(self) -> None:
        settings = AiAssistantSettings(providers=("qwen", "mock"), qwen_api_key="sk-qwen")
        chain = resolve_provider_chain(settings, environment="development")
        self.assertEqual(chain, ["qwen", "mock"])

    def test_production_with_nothing_configured_is_empty_not_mock(self) -> None:
        settings = AiAssistantSettings(providers=("qwen",))
        chain = resolve_provider_chain(settings, environment="production")
        self.assertEqual(chain, [])


class TestQwenDashScopeProvider(unittest.TestCase):
    def test_default_base_url_used_when_not_overridden(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertIn("dashscope", str(request.url))
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        provider = QwenDashScopeProvider(api_key="sk")
        provider._client._transport = httpx.MockTransport(handler)
        req = GenerateRequest(messages=[ChatTurn(role="user", content="hi")],
                              model="qwen-plus", max_output_tokens=10)
        result = provider.generate(req)
        self.assertEqual(result.text, "ok")


class TestMockChatProvider(unittest.TestCase):
    def test_stream_is_deterministic_word_by_word(self) -> None:
        provider = MockChatProvider()
        req = GenerateRequest(messages=[ChatTurn(role="user", content="Xin chào")],
                              model="mock-model", max_output_tokens=100)
        events1 = [e for e in provider.stream(req) if isinstance(e, Delta)]
        events2 = [e for e in provider.stream(req) if isinstance(e, Delta)]
        self.assertEqual([e.text for e in events1], [e.text for e in events2])
        self.assertGreater(len(events1), 1)

    def test_empty_input_raises(self) -> None:
        provider = MockChatProvider()
        req = GenerateRequest(messages=[ChatTurn(role="user", content="   ")],
                              model="m", max_output_tokens=10)
        with self.assertRaises(ProviderError):
            list(provider.stream(req))


if __name__ == "__main__":
    unittest.main()
