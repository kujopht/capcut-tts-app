"""Tests for server/ai_assistant/limits.py — RPM, concurrent-stream guard,
daily token budget.
"""
from __future__ import annotations

import unittest

from server.ai_assistant.limits import (
    AiBudgetExceeded, AiBusy, AiRateLimited, RpmLimiter, StreamGuard, budget_status,
    enforce_budget, record_usage,
)
from server.ai_assistant.memory import InMemoryAiRepo
from server.rate_limit import SlidingWindowRateLimiter


class TestRpmLimiter(unittest.TestCase):
    def test_allows_up_to_limit_then_blocks(self) -> None:
        limiter = RpmLimiter(limiter=SlidingWindowRateLimiter())
        for _ in range(3):
            limiter.check("u1", rpm=3)
        with self.assertRaises(AiRateLimited):
            limiter.check("u1", rpm=3)

    def test_keys_are_per_user(self) -> None:
        limiter = RpmLimiter(limiter=SlidingWindowRateLimiter())
        for _ in range(2):
            limiter.check("u1", rpm=2)
        limiter.check("u2", rpm=2)  # different user, not blocked


class TestStreamGuard(unittest.TestCase):
    def test_one_active_stream_per_user(self) -> None:
        guard = StreamGuard(max_streams_per_instance=10)
        guard.acquire("u1")
        with self.assertRaises(AiBusy):
            guard.acquire("u1")
        guard.release("u1")
        guard.acquire("u1")  # released, can acquire again

    def test_instance_wide_max_streams(self) -> None:
        guard = StreamGuard(max_streams_per_instance=2)
        guard.acquire("u1")
        guard.acquire("u2")
        with self.assertRaises(AiBusy):
            guard.acquire("u3")
        guard.release("u1")
        guard.acquire("u3")


class TestDailyBudget(unittest.TestCase):
    def test_enforce_raises_when_exhausted(self) -> None:
        repo = InMemoryAiRepo()
        record_usage(repo, user_id="u1", input_tokens=90, output_tokens=20)
        with self.assertRaises(AiBudgetExceeded) as ctx:
            enforce_budget(repo, user_id="u1", daily_limit=100)
        self.assertTrue(ctx.exception.reset_at)

    def test_enforce_allows_when_under_budget(self) -> None:
        repo = InMemoryAiRepo()
        status = enforce_budget(repo, user_id="u1", daily_limit=100)
        self.assertEqual(status.used_today, 0)
        self.assertEqual(status.limit_today, 100)

    def test_budget_status_reports_used_today(self) -> None:
        repo = InMemoryAiRepo()
        record_usage(repo, user_id="u1", input_tokens=10, output_tokens=5)
        status = budget_status(repo, user_id="u1", daily_limit=100)
        self.assertEqual(status.used_today, 15)

    def test_record_usage_accumulates(self) -> None:
        repo = InMemoryAiRepo()
        record_usage(repo, user_id="u1", input_tokens=10, output_tokens=5)
        record_usage(repo, user_id="u1", input_tokens=3, output_tokens=2)
        status = budget_status(repo, user_id="u1", daily_limit=100)
        self.assertEqual(status.used_today, 20)


if __name__ == "__main__":
    unittest.main()
