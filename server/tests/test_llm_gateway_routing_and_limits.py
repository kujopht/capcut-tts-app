import unittest

from server.llm_gateway.routing import GatewayRouter, RouteTarget, TaskKind
from server.llm_gateway.usage_limits import (
    ChatRateLimited, CircuitBreaker, DEFAULT_MESSAGE_QUOTA, MessageQuota,
    RetrievalBudget, enforce_output_budget, enforce_quota,
)


class GatewayRouterTest(unittest.TestCase):
    def test_missing_route_raises(self):
        router = GatewayRouter()
        with self.assertRaises(ValueError):
            router.targets_for(TaskKind.CHEAP_SIMPLE)

    def test_configured_route_returns_ordered_targets(self):
        router = GatewayRouter(routes={
            TaskKind.CHEAP_SIMPLE: [RouteTarget("a", "model-a"), RouteTarget("b", "model-b")]})
        targets = router.targets_for(TaskKind.CHEAP_SIMPLE)
        self.assertEqual([t.provider_name for t in targets], ["a", "b"])


class EnforceQuotaTest(unittest.TestCase):
    def test_under_quota_does_not_raise(self):
        enforce_quota("free", 5)

    def test_at_quota_raises(self):
        quota = DEFAULT_MESSAGE_QUOTA["free"]
        with self.assertRaises(ChatRateLimited):
            enforce_quota("free", quota.so_lan)

    def test_unknown_tier_not_limited(self):
        enforce_quota("no_such_tier", 999999)

    def test_custom_quotas_override_default(self):
        custom = {"free": MessageQuota(so_lan=1, phut=60)}
        with self.assertRaises(ChatRateLimited):
            enforce_quota("free", 1, quotas=custom)


class EnforceOutputBudgetTest(unittest.TestCase):
    def test_short_text_unaffected(self):
        budget = RetrievalBudget(max_output_chars=100)
        self.assertEqual(enforce_output_budget("short", budget=budget), "short")

    def test_long_text_truncated_with_marker(self):
        budget = RetrievalBudget(max_output_chars=10)
        result = enforce_output_budget("x" * 100, budget=budget)
        self.assertTrue(result.endswith("…"))
        self.assertLessEqual(len(result), 11)


class CircuitBreakerTest(unittest.TestCase):
    def test_closed_by_default(self):
        breaker = CircuitBreaker()
        self.assertFalse(breaker.is_open("p1"))

    def test_opens_after_threshold_failures(self):
        breaker = CircuitBreaker(failure_threshold=2, clock_fn=lambda: 0.0)
        breaker.record_failure("p1")
        self.assertFalse(breaker.is_open("p1"))
        breaker.record_failure("p1")
        self.assertTrue(breaker.is_open("p1"))

    def test_success_resets_failure_count(self):
        breaker = CircuitBreaker(failure_threshold=2, clock_fn=lambda: 0.0)
        breaker.record_failure("p1")
        breaker.record_success("p1")
        breaker.record_failure("p1")
        self.assertFalse(breaker.is_open("p1"))

    def test_closes_again_after_open_seconds_elapse(self):
        now = [0.0]
        breaker = CircuitBreaker(failure_threshold=1, open_seconds=30.0, clock_fn=lambda: now[0])
        breaker.record_failure("p1")
        self.assertTrue(breaker.is_open("p1"))
        now[0] = 31.0
        self.assertFalse(breaker.is_open("p1"))

    def test_different_providers_tracked_independently(self):
        breaker = CircuitBreaker(failure_threshold=1, clock_fn=lambda: 0.0)
        breaker.record_failure("p1")
        self.assertTrue(breaker.is_open("p1"))
        self.assertFalse(breaker.is_open("p2"))


if __name__ == "__main__":
    unittest.main()
