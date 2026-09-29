"""
Per-user cost/abuse controls — Fanfic AI Assistant V1 §9.

Reuses `server.rate_limit.SlidingWindowRateLimiter` (the SAME class
`server/messaging/routes.py` uses) for RPM, key namespaced `ai:{user_id}` per
the contract. Concurrent-stream and daily-token-budget enforcement are
this module's own small, focused pieces — same "one error hierarchy per
feature" convention as `server/llm_gateway/usage_limits.py`'s
`ChatUsageError`.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from server.ai_assistant.memory import AiRepo
from server.rate_limit import SlidingWindowRateLimiter


class AiUsageError(Exception):
    """Base for every usage-control refusal — a route maps any of these to
    a stable HTTP status/code (contract §10)."""

    code = "ai_usage_error"


class AiRateLimited(AiUsageError):
    code = "ai_rate_limited"


class AiBudgetExceeded(AiUsageError):
    code = "ai_budget_exhausted"

    def __init__(self, message: str, *, reset_at: str):
        super().__init__(message)
        self.reset_at = reset_at


class AiBusy(AiUsageError):
    code = "ai_busy"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _reset_at_iso() -> str:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return tomorrow.isoformat(timespec="seconds")


class RpmLimiter:
    """Wraps `SlidingWindowRateLimiter` with the contract's own key shape
    (`ai:{user_id}`) and RPM window (60s)."""

    def __init__(self, *, limiter: Optional[SlidingWindowRateLimiter] = None):
        self._limiter = limiter or SlidingWindowRateLimiter()

    def check(self, user_id: str, *, rpm: int) -> None:
        ok, _, retry_after = self._limiter.check(f"ai:{user_id}", rpm, window=60.0)
        if not ok:
            raise AiRateLimited(f"Bạn thao tác hơi nhanh — thử lại sau {retry_after}s.")

    def reset(self) -> None:
        self._limiter.reset()


class StreamGuard:
    """Enforces BOTH "1 active stream per user" and `FAS_AI_MAX_STREAMS`
    (concurrent streams per INSTANCE, across all users) — contract §9.
    A context manager so a route can `with guard.reserve(user_id):` and
    have release happen automatically even on an exception/disconnect."""

    def __init__(self, *, max_streams_per_instance: int):
        self._max = max_streams_per_instance
        self._lock = threading.Lock()
        self._per_user: Dict[str, int] = {}
        self._total = 0

    def acquire(self, user_id: str) -> None:
        with self._lock:
            if self._per_user.get(user_id, 0) >= 1:
                raise AiBusy("Bạn đang có một cuộc trò chuyện đang chạy — vui lòng đợi.")
            if self._total >= self._max:
                raise AiBusy("Máy chủ đang bận — vui lòng thử lại sau ít giây.")
            self._per_user[user_id] = self._per_user.get(user_id, 0) + 1
            self._total += 1

    def release(self, user_id: str) -> None:
        with self._lock:
            remaining = self._per_user.get(user_id, 1) - 1
            if remaining > 0:
                self._per_user[user_id] = remaining
            else:
                self._per_user.pop(user_id, None)
            self._total = max(0, self._total - 1)


@dataclass(frozen=True)
class BudgetStatus:
    used_today: int
    limit_today: int
    reset_at: str


def budget_status(repo: AiRepo, *, user_id: str, daily_limit: int) -> BudgetStatus:
    day = _today()
    usage = repo.get_usage_day(user_id, day)
    used = (usage.input_tokens + usage.output_tokens) if usage else 0
    return BudgetStatus(used_today=used, limit_today=daily_limit, reset_at=_reset_at_iso())


def enforce_budget(repo: AiRepo, *, user_id: str, daily_limit: int) -> BudgetStatus:
    status = budget_status(repo, user_id=user_id, daily_limit=daily_limit)
    if status.used_today >= status.limit_today:
        raise AiBudgetExceeded(
            f"Đã dùng hết {status.limit_today} token hôm nay.", reset_at=status.reset_at)
    return status


def record_usage(repo: AiRepo, *, user_id: str, input_tokens: int, output_tokens: int) -> BudgetStatus:
    day = _today()
    u = repo.increment_usage(user_id, day, input_tokens=input_tokens, output_tokens=output_tokens)
    return BudgetStatus(used_today=u.input_tokens + u.output_tokens, limit_today=0,
                        reset_at=_reset_at_iso())
