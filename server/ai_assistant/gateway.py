"""
AI Assistant gateway — Fanfic AI Assistant V1 §3.

Mode -> ordered provider fallback chain, reusing
`server.llm_gateway.usage_limits.CircuitBreaker` VERBATIM (same class, own
instance — this package's providers are a disjoint namespace from the
reader-AI's `LLMGateway`, so sharing ONE `CircuitBreaker` instance across
both would let an outage on one feature spuriously open a breaker for the
other; two separate instances of the same class is the correct reuse,
not a new implementation).

Fallback policy (THE safety-relevant rule in this module): a provider may
only be swapped for the next one in the chain if it fails BEFORE its first
`Delta` ever reached the caller. Once even one `Delta` has been yielded,
any further provider failure becomes an `ErrorEvent(code="ai_provider_
interrupted")` and the stream ends — two providers are never silently
stitched into one answer.

Admin readiness (release gate, `/admin/ai` later): `provider_chain` (order
= priority, absence = disabled) and `model_overrides` are read on EVERY
`stream()` call, so a future policy source can swap them atomically at
runtime; a 429 cools the provider down for its `Retry-After`
(`CircuitBreaker.cool_down`); `health()` is the server-side read model; the
serving provider/model of each turn is reported to the ROUTE (never the
client) via `ProviderServed`, so usage can be counted per provider.
Per-provider daily request/token caps and weights are NOT built — they
need a per-provider ledger (additive: a new collection), see
`docs/ai/AI_ASSISTANT_V1.md` "Release gate / Admin AI".
"""
from __future__ import annotations

import contextlib
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional

from server.ai_assistant.config import MODE_LIMITS, estimate_tokens
from server.llm_gateway.chat_provider import (
    ChatProvider, ChatTurn, Delta, GenerateRequest, ProviderError, StreamEvent,
)
from server.llm_gateway.usage_limits import CircuitBreaker


@dataclass(frozen=True)
class ErrorEvent:
    code: str
    message: str


@dataclass(frozen=True)
class ProviderServed:
    """Internal, SERVER-ONLY event: yielded once, right before the first
    `Delta` of the provider that actually answers. The route records it on
    the persisted message and never forwards it over SSE (§0.3: provider and
    model names never reach the client)."""
    provider_name: str
    model: str


#: Cooldown when a 429 carries no usable `Retry-After`.
DEFAULT_429_COOLDOWN_S = 30.0


def trim_context(messages: List[ChatTurn], *, max_tokens: int) -> List[ChatTurn]:
    """Backstop trim (contract §3: "cắt ngữ cảnh theo max_context_tokens của
    mode") — keeps every `system` turn (prompt/preferences/summary/
    retrieval block), then keeps as many of the most RECENT non-system
    turns as fit the remaining budget. `context_builder.py` already keeps
    its own output near budget; this is a second, independent backstop so
    the gateway never trusts a caller's trimming alone."""
    system_turns = [t for t in messages if t.role == "system"]
    other_turns = [t for t in messages if t.role != "system"]
    used = sum(estimate_tokens(t.content) for t in system_turns)
    kept: List[ChatTurn] = []
    for t in reversed(other_turns):
        cost = estimate_tokens(t.content)
        if used + cost > max_tokens and kept:
            break
        used += cost
        kept.append(t)
    kept.reverse()
    return system_turns + kept


@dataclass
class AiGateway:
    providers: Dict[str, ChatProvider]
    provider_chain: List[str]
    #: mode -> provider_name -> model override (falls back to the
    #: provider's own default model when absent).
    model_overrides: Dict[str, Dict[str, str]] = field(default_factory=dict)
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    def _model_for(self, mode: str, provider_name: str, provider: ChatProvider) -> str:
        override = self.model_overrides.get(mode, {}).get(provider_name)
        if override:
            return override
        return getattr(provider, "_default_model", provider_name)

    def health(self) -> Dict[str, Dict[str, Any]]:
        """Server-side read model for a future `/admin/ai` (NOT exposed by
        any route yet): per configured provider — in chain (enabled), chain
        position (priority), cooldown/failure state, process-local usage
        counters. Contains no key, URL or secret."""
        breaker = self.circuit_breaker.snapshot()
        out: Dict[str, Dict[str, Any]] = {}
        for name, provider in self.providers.items():
            b = breaker.get(name, {"consecutive_failures": 0, "open_for_s": 0.0})
            out[name] = {
                "enabled": name in self.provider_chain,
                "priority": self.provider_chain.index(name) if name in self.provider_chain else None,
                "cooling_down_s": round(b["open_for_s"], 1),
                "consecutive_failures": b["consecutive_failures"],
                "usage": asdict(provider.usage()),
            }
        return out

    def stream(self, messages: List[ChatTurn], *, mode: str,
              user_ref: str = "", workload: Optional[str] = None,
              cancel: Optional[Callable[[], bool]] = None,
              on_attempt: Optional[Callable[[str, str], None]] = None) -> Iterator[StreamEvent]:
        # `workload` exists for signature parity with the control plane's
        # `ControlledGateway`; the env-configured chain has one route only.
        # `cancel()` -> True: nobody is reading any more (client gone) — start no further provider call.
        limits = MODE_LIMITS.get(mode, MODE_LIMITS["general"])
        trimmed = trim_context(messages, max_tokens=limits["max_context_tokens"])
        tried_any = False
        # Snapshot: a runtime policy change mid-stream affects the NEXT turn only.
        for name in list(self.provider_chain):
            if cancel is not None and cancel():
                return
            if self.circuit_breaker.is_open(name):
                continue
            provider = self.providers.get(name)
            if provider is None:
                continue
            tried_any = True
            model = self._model_for(mode, name, provider)
            if on_attempt is not None:
                try:
                    on_attempt(name, model)
                except Exception:  # noqa: BLE001 — phép đo phụ, không bao giờ làm hỏng lượt
                    pass
            if cancel is not None and cancel():
                # Xem `ControlledGateway.stream`: kiểm lại SAU `on_attempt` để một lời gọi không còn ai đếm không được phát đi.
                return
            req = GenerateRequest(
                messages=trimmed, model=model, max_output_tokens=limits["max_output_tokens"],
                user_ref=user_ref)
            started = False
            try:
                # R3 (review finding): `contextlib.closing` ensures the
                # provider's own generator (holding its httpx streaming
                # context manager / socket open) is closed the moment we
                # stop iterating it here — whether that's a normal
                # `return`, a `ProviderError`, or the CALLER of THIS
                # generator closing/abandoning it (e.g. a client
                # disconnect in `server/ai_assistant/routes.py`, which
                # propagates as `GeneratorExit` at this exact suspension
                # point) — never left to eventual GC.
                with contextlib.closing(provider.stream(req)) as provider_events:
                    for ev in provider_events:
                        if isinstance(ev, Delta) and not started:
                            started = True
                            yield ProviderServed(provider_name=name, model=model)
                        yield ev
                self.circuit_breaker.record_success(name)
                return
            except ProviderError as exc:
                if exc.code == "provider_http_429" or exc.retry_after_s is not None:
                    self.circuit_breaker.cool_down(
                        name, exc.retry_after_s if exc.retry_after_s is not None else DEFAULT_429_COOLDOWN_S)
                else:
                    self.circuit_breaker.record_failure(name)
                if started:
                    # M9 (review finding): `str(exc)` here used to leak the
                    # provider's own error text verbatim over SSE —
                    # `OpenAICompatChatProvider`'s messages embed the
                    # provider NAME and, for a transport failure (e.g. an
                    # `httpx.ReadError` mid-stream), the raw exception text
                    # too (`f"Không gọi được '{self.name}': {exc}"`). Every
                    # user-facing error after the first `Delta` now gets the
                    # SAME fixed, provider-agnostic message regardless of
                    # `exc` — `exc` still reaches the logs (below, via
                    # `record_failure`'s own caller conventions), never the
                    # SSE payload.
                    yield ErrorEvent(
                        code="ai_provider_interrupted",
                        message="Kết nối tới nhà cung cấp AI bị gián đoạn giữa chừng — thử lại sau.")
                    return
                continue  # not started yet -> try next provider in chain
            except Exception:
                # R1 (review finding): a provider bug that raises something
                # OTHER than `ProviderError` must still be treated as a
                # provider failure for circuit-breaker/fallback purposes —
                # and must NEVER leak raw exception text to the client
                # (every `ChatProvider` implementation in this repo already
                # converts its own internals to `ProviderError`; this is a
                # defense-in-depth backstop for a THIRD-PARTY/future
                # provider that doesn't).
                self.circuit_breaker.record_failure(name)
                if started:
                    yield ErrorEvent(code="ai_provider_interrupted",
                                     message="Nhà cung cấp AI gặp sự cố không mong đợi.")
                    return
                continue
        if tried_any:
            yield ErrorEvent(
                code="ai_provider_unavailable",
                message="Tất cả nhà cung cấp AI đều đang gặp sự cố — thử lại sau.")
        else:
            yield ErrorEvent(
                code="ai_no_provider", message="Chưa có nhà cung cấp AI nào khả dụng.")
