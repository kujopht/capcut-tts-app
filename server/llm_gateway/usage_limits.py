"""
Usage/cost controls — Fanfic AI Chat V1 Phase 8.

`MessageQuota`/`enforce_quota` mirror `server/social.py`'s `HanMuc`/
`kiem_han_muc` shape exactly (a pure decision function taking an
already-counted usage number, not a counter itself - counting belongs to
the store layer, kept separate for testability, same reasoning as
`social.py`'s own module docstring). Deliberately NOT importing
`server.social`'s types directly: chat's error domain stays self-contained
(`ChatUsageError` hierarchy), matching how `translation_providers.py` has
its own `TranslationProviderError` rather than reusing anything from
`social.py`.

Free/premium tiers: `DEFAULT_MESSAGE_QUOTA` is architected so premium
tiers can be given a materially higher quota later - no payment
enforcement is implemented here (mission brief: "Do not implement payment
if it is not already ready").
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable, Dict, Optional


class ChatUsageError(Exception):
    """Base for every usage-control refusal - a caller can catch this one
    type to map any of them to an HTTP 429/503, same convention as
    `server/social.py::SocialError`."""


class ChatRateLimited(ChatUsageError):
    pass


class ChatBudgetExceeded(ChatUsageError):
    pass


class ChatProviderUnavailable(ChatUsageError):
    """Every route target for a task kind is either circuit-broken or
    failed - see `gateway.LLMGateway.complete`."""


@dataclass(frozen=True)
class MessageQuota:
    so_lan: int
    phut: int

    @property
    def cua_so(self) -> timedelta:
        return timedelta(minutes=self.phut)


#: Daily message quota per tier - "1440" = 24h in minutes. Free tier is
#: intentionally modest; premium is architected to raise this (and route
#: to stronger models via `routing.py`) without any code change, once
#: payment/tiering is wired up elsewhere.
DEFAULT_MESSAGE_QUOTA: Dict[str, MessageQuota] = {
    "free": MessageQuota(so_lan=20, phut=1440),
    "premium": MessageQuota(so_lan=200, phut=1440),
}


def enforce_quota(tier: str, messages_used: int,
                  quotas: Optional[Dict[str, MessageQuota]] = None) -> None:
    """Raises `ChatRateLimited` if `messages_used` has reached the quota
    for `tier`. An unknown tier is NOT rate-limited here (fail toward
    availability for a config gap, not toward silently blocking every
    user of a newly-added tier no one wired a quota for yet) - callers
    should validate `tier` is a real, known value upstream of this."""
    quota = (quotas or DEFAULT_MESSAGE_QUOTA).get(tier)
    if quota is None:
        return
    if messages_used >= quota.so_lan:
        raise ChatRateLimited(
            f"Đã đạt hạn mức {quota.so_lan} tin nhắn/{quota.phut} phút cho hạng '{tier}'.")


@dataclass(frozen=True)
class RetrievalBudget:
    max_retrieval_chunks: int = 6
    max_context_chars: int = 6000
    max_output_tokens: int = 800
    #: Bounds the FINAL text shown to the user - independent of
    #: `max_output_tokens` (a provider-side generation cap); this is a
    #: last-resort backstop against a provider ignoring its own token cap.
    max_output_chars: int = 4000


def enforce_output_budget(text: str, *, budget: RetrievalBudget) -> str:
    """Never silently drops content past the cap - truncates with a
    visible marker so a UI/caller can tell truncation happened."""
    if len(text) <= budget.max_output_chars:
        return text
    return text[:budget.max_output_chars].rstrip() + "…"


@dataclass
class _BreakerState:
    consecutive_failures: int = 0
    open_until: Optional[float] = None


class CircuitBreaker:
    """Per-provider-name circuit breaker - independent of and NOT reusing
    `scripts/router_v3/registry.py`'s circuit breaker (that one governs
    AI_ROUTER_LTS developer-agent workers, a completely separate concern
    from user-facing inference providers; see this package's own
    `__init__.py` docstring for why the two must never be conflated).
    """

    def __init__(self, *, failure_threshold: int = 3, open_seconds: float = 60.0,
                clock_fn: Callable[[], float] = time.monotonic):
        self._threshold = failure_threshold
        self._open_seconds = open_seconds
        self._clock = clock_fn
        self._state: Dict[str, _BreakerState] = {}

    def is_open(self, provider_name: str) -> bool:
        state = self._state.get(provider_name)
        if state is None or state.open_until is None:
            return False
        return self._clock() < state.open_until

    def record_success(self, provider_name: str) -> None:
        self._state[provider_name] = _BreakerState()

    def record_failure(self, provider_name: str) -> None:
        state = self._state.setdefault(provider_name, _BreakerState())
        state.consecutive_failures += 1
        if state.consecutive_failures >= self._threshold:
            state.open_until = self._clock() + self._open_seconds
