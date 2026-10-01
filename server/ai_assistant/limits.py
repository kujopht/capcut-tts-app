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

import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from server.ai_assistant.memory import AiRepo
from server.ai_assistant.scopes import SCOPE_GLOBAL, SCOPE_QA, SCOPE_USER  # noqa: F401 — re-export cho route/test
from server.rate_limit import SlidingWindowRateLimiter

#: Lần QA của Owner ghi vào CÙNG sổ `ai_usage_daily` nhưng dưới một khoá tổng hợp (`qa-` + 16 hex của
#: băm), nên: (1) không cần cột Appwrite mới, (2) không bao giờ cộng vào hạn mức người dùng thường,
#: (3) vừa đủ ngắn cho `user_id` (64) và mã tài liệu `{khoá}_{yyyymmdd}` (<= 36 ký tự) dù user id dài tới 36.
QA_LEDGER_PREFIX = "qa-"


def qa_ledger_user(user_id: str) -> str:
    return QA_LEDGER_PREFIX + hashlib.sha256(("fanfic-ai-qa:" + user_id).encode("utf-8")).hexdigest()[:16]


class AiUsageError(Exception):
    """Base for every usage-control refusal — a route maps any of these to
    a stable HTTP status/code (contract §10)."""

    code = "ai_usage_error"


class AiRateLimited(AiUsageError):
    code = "ai_rate_limited"


class AiBudgetExceeded(AiUsageError):
    code = "ai_budget_exhausted"

    def __init__(self, message: str, *, reset_at: str, scope: str = SCOPE_USER):
        super().__init__(message)
        self.reset_at = reset_at
        self.scope = scope


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

    def check(self, user_id: str, *, rpm: int, scope: str = "ai") -> None:
        """`scope` tách các bộ đếm: lượt chat dùng `ai:` (mặc định, đúng khoá hợp đồng), các route ghi không gọi LLM dùng
        khoá riêng để một người lưu dự án liên tục không bị tính vào nhịp gửi tin."""
        ok, _, retry_after = self._limiter.check(f"{scope}:{user_id}", rpm, window=60.0)
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

    def snapshot(self) -> Tuple[int, int]:
        """(luồng đang chạy, tối đa) của instance này — chỉ để HIỂN THỊ ở `/admin/ai` (không có ID người dùng nào)."""
        with self._lock:
            return self._total, self._max


class StreamTicket:
    """Một lần giữ khoá luồng (`StreamGuard.acquire`), nhả ĐÚNG MỘT LẦN dù được gọi từ nhiều đường: `finally` của
    generator SSE, một `BackgroundTask` của response (phòng generator chưa bao giờ được chạy vì client ngắt trước khi
    stream bắt đầu), hay lỗi ở bước chuẩn bị. Không có vé thì một lần nhả thừa có thể trừ nhầm luồng KẾ TIẾP của cùng
    người dùng; thiếu lần nhả thì khoá rò vĩnh viễn (người đó, rồi sau vài lần cả instance, nhận `ai_busy`)."""

    def __init__(self, guard: StreamGuard, user_id: str) -> None:
        self._guard = guard
        self._user_id = user_id
        self._released = False
        self._lock = threading.Lock()

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
        self._guard.release(self._user_id)


@dataclass(frozen=True)
class BudgetStatus:
    used_today: int
    limit_today: int
    reset_at: str
    #: Số lượt đã ghi sổ hôm nay (cùng bản ghi với `used_today`, không tốn thêm lần đọc).
    requests_used: int = 0


@dataclass(frozen=True)
class Allowance:
    """Hạn mức RIÊNG của một người trong ngày — đúng thứ `ControlPlane.admission` + ngân sách token cũ sẽ
    thực thi, và KHÔNG chứa gì về công suất toàn site / nhà cung cấp (phần đó chỉ ở `/admin/ai`)."""

    requests_used: int
    #: `None` = không đặt trần số lượt (chỉ còn trần token) — giao diện không có "x/y lượt" để hiện.
    requests_limit: Optional[int]
    requests_remaining: Optional[int]
    exhausted: bool
    reset_at: str

    def to_public(self) -> Dict[str, Any]:
        return {"requests_used": self.requests_used, "requests_limit": self.requests_limit,
                "requests_remaining": self.requests_remaining, "exhausted": self.exhausted,
                "reset_at": self.reset_at}


def compute_allowance(*, requests_used: int, tokens_used: int, request_cap: int, token_cap: int,
                      legacy_token_limit: Optional[int] = None, reset_at: Optional[str] = None) -> Allowance:
    """Gộp ĐÚNG ba phép kiểm mà một lượt gửi sẽ gặp: trần số lượt và trần token của control plane
    (`0` = không đặt trần) và ngân sách token theo hạng tài khoản cũ (`enforce_budget`, `None` = không áp)."""
    req_cap = request_cap if request_cap and request_cap > 0 else None
    exhausted = bool(
        (req_cap is not None and requests_used >= req_cap)
        or (token_cap and tokens_used >= token_cap)
        or (legacy_token_limit is not None and tokens_used >= legacy_token_limit))
    remaining = None if req_cap is None else (0 if exhausted else max(0, req_cap - requests_used))
    return Allowance(requests_used=requests_used, requests_limit=req_cap, requests_remaining=remaining,
                     exhausted=exhausted, reset_at=reset_at or _reset_at_iso())


def qa_allowance(*, requests_used: int, daily_cap: int, reset_at: Optional[str] = None) -> Allowance:
    """Lần QA của Owner: CHỈ trần số lượt, và `0` nghĩa là ĐÓNG (khác trần người dùng, nơi 0 = không trần)."""
    return Allowance(requests_used=requests_used, requests_limit=daily_cap,
                     requests_remaining=max(0, daily_cap - requests_used), exhausted=requests_used >= daily_cap,
                     reset_at=reset_at or _reset_at_iso())


def budget_status(repo: AiRepo, *, user_id: str, daily_limit: int) -> BudgetStatus:
    day = _today()
    usage = repo.get_usage_day(user_id, day)
    used = (usage.input_tokens + usage.output_tokens) if usage else 0
    return BudgetStatus(used_today=used, limit_today=daily_limit, reset_at=_reset_at_iso(),
                        requests_used=usage.requests if usage else 0)


def enforce_budget(repo: AiRepo, *, user_id: str, daily_limit: int) -> BudgetStatus:
    status = budget_status(repo, user_id=user_id, daily_limit=daily_limit)
    if status.used_today >= status.limit_today:
        raise AiBudgetExceeded(
            f"Đã dùng hết {status.limit_today} token hôm nay.", reset_at=status.reset_at)
    return status


def record_usage(repo: AiRepo, *, user_id: str, input_tokens: int, output_tokens: int,
                 daily_limit: int) -> BudgetStatus:
    """`daily_limit` is REQUIRED (not optional/defaulted to 0) — a previous
    version of this function hard-coded `limit_today=0` in its return
    value, which meant the `usage` SSE event and any caller relying on
    THIS return value (rather than a separate `budget_status` call) always
    reported a bogus, always-exhausted-looking limit. Fixed per review
    finding R2 (`docs/ai/AI_ASSISTANT_V1.md` "Implementation notes")."""
    day = _today()
    u = repo.increment_usage(user_id, day, input_tokens=input_tokens, output_tokens=output_tokens)
    return BudgetStatus(used_today=u.input_tokens + u.output_tokens, limit_today=daily_limit,
                        reset_at=_reset_at_iso(), requests_used=u.requests)
