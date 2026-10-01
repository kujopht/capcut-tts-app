"""
Streaming-capable chat provider contract — Fanfic AI Assistant V1.

Distinct from `server.llm_gateway.provider.LLMProvider` (the older Fanfic AI
Chat V1 reader-AI contract: one blocking `(system, user) -> text` call, no
streaming, no tools). That contract stays UNCHANGED — `/api/chat/ask` keeps
using it. This module is a NEW, additive contract for `server/ai_assistant/*`
that needs streaming (`stream()`), multi-turn history (`ChatTurn` list rather
than a single system/user pair), tool-calling, and capability discovery
(`ProviderCapabilities`) — the reader AI has none of these needs, so rather
than bolt them onto `LLMProvider` (breaking every existing caller/test), this
is a parallel, additive contract. `LegacyCompletionAdapter` (bottom of
`chat_providers.py`) bridges a `ChatProvider` back into the OLD `LLMProvider`
shape for future reuse — not wired into `/api/chat/ask` in V1.

Every real adapter is built and shaped against each vendor's PUBLICLY
DOCUMENTED wire format, exercised only via `httpx.MockTransport` in this
environment — no live API key has been used to test any of them. This is the
same honesty convention as `server/llm_gateway/providers.py`'s own
docstring.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple


class ProviderError(Exception):
    """Raised on any provider-side failure — network, timeout, non-200,
    malformed body, refused content. `transient=True` means the SAME
    request might succeed against a different provider/route target right
    now (network blip, 5xx, rate limit) — `transient=False` means retrying
    elsewhere won't help (bad request shape, auth rejected). `code` is a
    short machine-stable label for logs/telemetry, never the raw vendor
    response body (that could contain a request echo with secrets — see
    `server/secret_redaction.py`). `retry_after_s` is the provider's own
    `Retry-After` (seconds) on a 429, when it sent a usable one — the
    gateway cools that provider down for that long (`CircuitBreaker.
    cool_down`) instead of hammering it on every request. `category` is the
    vendor's own canonical error ENUM (e.g. Google `NOT_FOUND`), taken only
    from a closed allowlist (`chat_providers.error_category`) — never a
    message, never free text."""

    def __init__(self, message: str, *, transient: bool = True, code: str = "provider_error",
                 retry_after_s: Optional[float] = None, category: Optional[str] = None):
        super().__init__(message)
        self.transient = transient
        self.code = code
        self.retry_after_s = retry_after_s
        self.category = category


@dataclass(frozen=True)
class ProviderCapabilities:
    streaming: bool
    tools: bool
    web_search: bool
    vision: bool
    max_context_tokens: int


@dataclass(frozen=True)
class ChatTurn:
    """One provider-neutral message. `role` is `"system" | "user" |
    "assistant" | "tool"`. `name` is only meaningful for `role="tool"`
    (which tool produced this turn)."""

    role: str
    content: str
    name: Optional[str] = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    call_id: str = ""


@dataclass(frozen=True)
class GenerateRequest:
    messages: List[ChatTurn]
    model: str
    max_output_tokens: int
    temperature: float = 0.7
    tools: Optional[List[ToolSpec]] = None
    #: HASH of the real user id (never the raw id) — sent to the provider
    #: as an abuse-tracking reference per its own "user" field, matching
    #: the contract's own explicit anti-abuse rationale (§2).
    user_ref: str = ""
    timeout_s: float = 60.0


@dataclass(frozen=True)
class GenerateResult:
    text: str
    provider_name: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: Tuple[ToolCall, ...] = ()
    finish_reason: str = "stop"


# --------------------------------------------------------------------- events


@dataclass(frozen=True)
class Delta:
    text: str


@dataclass(frozen=True)
class ToolCallEvent:
    call: ToolCall


@dataclass(frozen=True)
class UsageEvent:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Done:
    finish_reason: str = "stop"


StreamEvent = Any  # Delta | ToolCallEvent | UsageEvent | Done — kept loose
#: for isinstance()-based dispatch at call sites (a Union alias doesn't
#: enforce anything extra here and adds import noise at every call site).


@dataclass(frozen=True)
class ProviderUsageSnapshot:
    """Counters since process start — best-effort, in-memory only, reset on
    restart. Never persisted here (`server/ai_assistant/memory.py`'s
    `ai_usage_daily` is the durable ledger; this is process-local
    telemetry only)."""

    requests: int = 0
    errors: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class ChatProvider(ABC):
    name: str = "unknown"

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        ...

    def supports_tools(self) -> bool:
        return self.capabilities().tools

    def supports_web_search(self) -> bool:
        return self.capabilities().web_search

    def supports_vision(self) -> bool:
        return self.capabilities().vision

    @abstractmethod
    def generate(self, req: GenerateRequest) -> GenerateResult:
        """Non-streaming call. Raises `ProviderError` — never returns an
        empty string as though it were a successful, contentless answer."""

    @abstractmethod
    def stream(self, req: GenerateRequest) -> Iterator[StreamEvent]:
        """Yields `Delta`/`ToolCallEvent`/`UsageEvent` in arrival order,
        ending with exactly one `Done`. Raises `ProviderError` if the
        FIRST chunk never arrives (connection/HTTP failure before any
        content) — the caller (`server/ai_assistant/gateway.py`) treats an
        error raised before any `Delta` differently from one raised after
        (see that module's fallback policy)."""

    @abstractmethod
    def usage(self) -> ProviderUsageSnapshot:
        ...
