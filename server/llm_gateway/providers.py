"""
Real LLM provider implementations — Fanfic AI Chat V1 Phase 7.

Same pattern as `server/translation_providers.py::DocuTranslateProvider`:
an injectable `httpx.Client` (tests use `httpx.MockTransport`, never a real
network call), explicit timeout, `LLMProviderError` on any failure
(network, non-200, malformed response, empty content).

Honest scope note: these are real, correctly-shaped HTTP clients against
each vendor's PUBLICLY DOCUMENTED API surface, built without a live API
key in this environment - none has been exercised against a real,
authenticated endpoint. `build_provider`/`MockLLMProvider` exist precisely
so the rest of this feature works and is testable without one.
"""
from __future__ import annotations

from typing import Optional

import httpx

from server.llm_gateway.provider import LLMCompletion, LLMProvider, LLMProviderError

DEFAULT_TIMEOUT_SECONDS = 60.0


class OpenAICompatProvider(LLMProvider):
    """OpenAI chat-completions-SHAPED endpoint — covers OpenAI itself,
    OpenRouter, and most self-hosted model servers (vLLM, Ollama's OpenAI-
    compatible mode, ...) since they all speak this same wire format.
    Distinguished from one another only by `base_url`/`api_key`/`model` at
    construction time, matching this repo's existing
    `DocuTranslateProvider`'s exact reasoning for the translation feature.
    """

    def __init__(self, *, name: str, base_url: str, api_key: str,
                client: Optional[httpx.Client] = None,
                timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
        if not (base_url and api_key):
            raise LLMProviderError(
                f"Thiếu base_url/api_key cho provider '{name}' - chưa thể dùng.")
        self.name = name
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
        )

    def complete(self, *, system: str, user: str, model: str,
                max_output_tokens: int) -> LLMCompletion:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_output_tokens,
            "temperature": 0.3,
        }
        try:
            resp = self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Không gọi được '{self.name}': {exc}") from exc
        if resp.status_code != 200:
            raise LLMProviderError(
                f"'{self.name}' trả lỗi {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMProviderError(
                f"Phản hồi '{self.name}' không đúng định dạng mong đợi.") from exc
        text = (content or "").strip()
        if not text:
            raise LLMProviderError(f"'{self.name}' trả về nội dung rỗng.")
        return LLMCompletion(
            text=text, provider_name=self.name, model=model,
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0))


class GeminiProvider(LLMProvider):
    """Google Gemini's own REST shape (`generateContent`) - not OpenAI-
    compatible, hence a separate class rather than reusing
    `OpenAICompatProvider`."""

    name = "gemini"

    def __init__(self, *, api_key: str,
                base_url: str = "https://generativelanguage.googleapis.com",
                client: Optional[httpx.Client] = None,
                timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
        if not api_key:
            raise LLMProviderError("Thiếu api_key cho Gemini - chưa thể dùng.")
        self._api_key = api_key
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"), timeout=timeout_seconds)

    def complete(self, *, system: str, user: str, model: str,
                max_output_tokens: int) -> LLMCompletion:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {"maxOutputTokens": max_output_tokens, "temperature": 0.3},
        }
        try:
            resp = self._client.post(
                f"/v1beta/models/{model}:generateContent",
                params={"key": self._api_key}, json=payload)
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Không gọi được Gemini: {exc}") from exc
        if resp.status_code != 200:
            raise LLMProviderError(f"Gemini trả lỗi {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
            usage = data.get("usageMetadata") or {}
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMProviderError("Phản hồi Gemini không đúng định dạng mong đợi.") from exc
        if not text:
            raise LLMProviderError("Gemini trả về nội dung rỗng.")
        return LLMCompletion(
            text=text, provider_name=self.name, model=model,
            input_tokens=int(usage.get("promptTokenCount", 0) or 0),
            output_tokens=int(usage.get("candidatesTokenCount", 0) or 0))


class AnthropicProvider(LLMProvider):
    """Anthropic's Messages API - `x-api-key`/`anthropic-version` headers,
    `system` as a top-level field (not a message role, unlike OpenAI's
    shape) - another genuinely distinct wire format."""

    name = "anthropic"
    API_VERSION = "2023-06-01"

    def __init__(self, *, api_key: str, base_url: str = "https://api.anthropic.com",
                client: Optional[httpx.Client] = None,
                timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
        if not api_key:
            raise LLMProviderError("Thiếu api_key cho Anthropic - chưa thể dùng.")
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"x-api-key": api_key, "anthropic-version": self.API_VERSION},
            timeout=timeout_seconds,
        )

    def complete(self, *, system: str, user: str, model: str,
                max_output_tokens: int) -> LLMCompletion:
        payload = {
            "model": model, "max_tokens": max_output_tokens, "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        try:
            resp = self._client.post("/v1/messages", json=payload)
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Không gọi được Anthropic: {exc}") from exc
        if resp.status_code != 200:
            raise LLMProviderError(f"Anthropic trả lỗi {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
            text = "".join(
                block.get("text", "") for block in data["content"]
                if block.get("type") == "text").strip()
            usage = data.get("usage") or {}
        except (KeyError, ValueError) as exc:
            raise LLMProviderError("Phản hồi Anthropic không đúng định dạng mong đợi.") from exc
        if not text:
            raise LLMProviderError("Anthropic trả về nội dung rỗng.")
        return LLMCompletion(
            text=text, provider_name=self.name, model=model,
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0))
