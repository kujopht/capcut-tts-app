import json
import unittest

import httpx

from server.llm_gateway.provider import LLMProviderError, MockLLMProvider
from server.llm_gateway.providers import (
    AnthropicProvider, GeminiProvider, OpenAICompatProvider,
)


def _client(handler) -> httpx.Client:
    """`MockTransport` — NEVER calls real network, matching this repo's
    established `_client_gia` pattern in test_translation_providers.py."""
    return httpx.Client(base_url="https://vidu.test", transport=httpx.MockTransport(handler))


class MockLLMProviderTest(unittest.TestCase):
    def test_empty_user_message_raises(self):
        with self.assertRaises(LLMProviderError):
            MockLLMProvider().complete(system="s", user="", model="m", max_output_tokens=100)

    def test_returns_recognizable_response(self):
        result = MockLLMProvider().complete(system="s", user="hello", model="m",
                                            max_output_tokens=100)
        self.assertIn("MOCK-LLM", result.text)
        self.assertEqual(result.provider_name, "mock")


class OpenAICompatProviderTest(unittest.TestCase):
    def test_missing_config_raises(self):
        with self.assertRaises(LLMProviderError):
            OpenAICompatProvider(name="x", base_url="", api_key="")

    def test_client_uses_correct_auth_header(self):
        """No injected `client` - lets the provider build its own real
        `httpx.Client` (never sends a request here) so the constructed
        headers can be inspected directly. Matches the same split this
        repo already uses for DocuTranslateProvider, since a MockTransport-
        injected client bypasses that header construction entirely."""
        provider = OpenAICompatProvider(name="x", base_url="https://vidu.test", api_key="bi-mat")
        self.assertEqual(provider._client.headers["authorization"], "Bearer bi-mat")

    def test_real_call_shape_and_response_parsing(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/chat/completions")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "gpt-x")
            self.assertEqual(body["messages"][0]["role"], "system")
            self.assertEqual(body["messages"][1]["role"], "user")
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "the answer"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            })

        provider = OpenAICompatProvider(
            name="openai", base_url="https://vidu.test", api_key="k",
            client=_client(handler))
        result = provider.complete(system="sys", user="usr", model="gpt-x",
                                   max_output_tokens=100)
        self.assertEqual(result.text, "the answer")
        self.assertEqual(result.input_tokens, 10)
        self.assertEqual(result.output_tokens, 5)

    def test_non_200_raises(self):
        def handler(request):
            return httpx.Response(500, text="server error")
        provider = OpenAICompatProvider(name="x", base_url="https://vidu.test",
                                        api_key="k", client=_client(handler))
        with self.assertRaises(LLMProviderError):
            provider.complete(system="s", user="u", model="m", max_output_tokens=10)

    def test_empty_content_raises(self):
        def handler(request):
            return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})
        provider = OpenAICompatProvider(name="x", base_url="https://vidu.test",
                                        api_key="k", client=_client(handler))
        with self.assertRaises(LLMProviderError):
            provider.complete(system="s", user="u", model="m", max_output_tokens=10)

    def test_malformed_response_raises(self):
        def handler(request):
            return httpx.Response(200, json={"unexpected": "shape"})
        provider = OpenAICompatProvider(name="x", base_url="https://vidu.test",
                                        api_key="k", client=_client(handler))
        with self.assertRaises(LLMProviderError):
            provider.complete(system="s", user="u", model="m", max_output_tokens=10)


class GeminiProviderTest(unittest.TestCase):
    def test_missing_api_key_raises(self):
        with self.assertRaises(LLMProviderError):
            GeminiProvider(api_key="")

    def test_real_call_shape_and_response_parsing(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertIn("generateContent", request.url.path)
            self.assertEqual(request.url.params["key"], "k")
            body = json.loads(request.content)
            self.assertEqual(body["systemInstruction"]["parts"][0]["text"], "sys")
            self.assertEqual(body["contents"][0]["parts"][0]["text"], "usr")
            return httpx.Response(200, json={
                "candidates": [{"content": {"parts": [{"text": "the answer"}]}}],
                "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 3},
            })

        provider = GeminiProvider(api_key="k", base_url="https://vidu.test",
                                  client=_client(handler))
        result = provider.complete(system="sys", user="usr", model="gemini-x",
                                   max_output_tokens=100)
        self.assertEqual(result.text, "the answer")
        self.assertEqual(result.input_tokens, 8)

    def test_non_200_raises(self):
        def handler(request):
            return httpx.Response(400, text="bad request")
        provider = GeminiProvider(api_key="k", base_url="https://vidu.test",
                                  client=_client(handler))
        with self.assertRaises(LLMProviderError):
            provider.complete(system="s", user="u", model="m", max_output_tokens=10)


class AnthropicProviderTest(unittest.TestCase):
    def test_missing_api_key_raises(self):
        with self.assertRaises(LLMProviderError):
            AnthropicProvider(api_key="")

    def test_client_uses_correct_auth_headers(self):
        provider = AnthropicProvider(api_key="bi-mat", base_url="https://vidu.test")
        self.assertEqual(provider._client.headers["x-api-key"], "bi-mat")
        self.assertEqual(provider._client.headers["anthropic-version"], "2023-06-01")

    def test_real_call_shape_and_response_parsing(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/messages")
            body = json.loads(request.content)
            self.assertEqual(body["system"], "sys")
            self.assertEqual(body["messages"][0]["content"], "usr")
            return httpx.Response(200, json={
                "content": [{"type": "text", "text": "the answer"}],
                "usage": {"input_tokens": 12, "output_tokens": 6},
            })

        provider = AnthropicProvider(api_key="k", base_url="https://vidu.test",
                                     client=_client(handler))
        result = provider.complete(system="sys", user="usr", model="claude-x",
                                   max_output_tokens=100)
        self.assertEqual(result.text, "the answer")
        self.assertEqual(result.output_tokens, 6)

    def test_non_text_content_blocks_ignored(self):
        def handler(request):
            return httpx.Response(200, json={"content": [
                {"type": "tool_use", "text": "should be ignored"},
                {"type": "text", "text": "real answer"},
            ]})
        provider = AnthropicProvider(api_key="k", base_url="https://vidu.test",
                                     client=_client(handler))
        result = provider.complete(system="s", user="u", model="m", max_output_tokens=10)
        self.assertEqual(result.text, "real answer")


if __name__ == "__main__":
    unittest.main()
