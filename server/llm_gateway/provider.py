"""
LLM provider contract — Fanfic AI Chat V1 Phase 7.

One method, same shape/rationale as `server/translation_providers.py`'s
`TranslationProvider`: every real call is "system policy + user message
in, one text response out" — the difference between a cheap model and a
strong reasoning model is WHICH model answers, not the shape of the call.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class LLMProviderError(Exception):
    """Provider-side failure (timeout, rate limit, malformed response,
    content refused) - the gateway maps this to a fallback/circuit-breaker
    decision, never a raw 500 to the end user."""


@dataclass(frozen=True)
class LLMCompletion:
    text: str
    #: Provider's own name, for telemetry/cost tracking - never used for
    #: branching logic (mirrors `TranslationProvider.name`'s own rule).
    provider_name: str
    model: str
    #: Best-effort token counts, when the provider's response includes
    #: them - 0 when unknown, never fabricated.
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(ABC):
    name: str = "unknown"

    @abstractmethod
    def complete(self, *, system: str, user: str, model: str,
                max_output_tokens: int) -> LLMCompletion:
        """Raises `LLMProviderError` on failure - never returns an empty
        string as if it were a successful, contentless answer (same rule
        as `TranslationProvider.translate_segment`)."""


class MockLLMProvider(LLMProvider):
    """Deterministic, no network - for tests and for development without
    any provider API key configured. Echoes a fixed, recognizable
    response so a test can assert real pipeline wiring without needing a
    live model."""

    name = "mock"

    def complete(self, *, system: str, user: str, model: str,
                max_output_tokens: int) -> LLMCompletion:
        if not user.strip():
            raise LLMProviderError("Tin nhan nguoi dung rong, khong co gi de tra loi.")
        return LLMCompletion(
            text=f"[MOCK-LLM] Đã nhận câu hỏi, {len(user)} ký tự ngữ cảnh/câu hỏi.",
            provider_name=self.name, model=model or "mock-model")
