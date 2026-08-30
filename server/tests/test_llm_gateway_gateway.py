import unittest

from server.llm_gateway.gateway import LLMGateway
from server.llm_gateway.provider import LLMCompletion, LLMProvider, LLMProviderError
from server.llm_gateway.routing import GatewayRouter, RouteTarget, TaskKind
from server.llm_gateway.usage_limits import ChatProviderUnavailable, CircuitBreaker, RetrievalBudget


class _FakeProvider(LLMProvider):
    def __init__(self, name, *, always_fails=False, response_text="ok"):
        self.name = name
        self._always_fails = always_fails
        self._response_text = response_text
        self.calls = 0

    def complete(self, *, system, user, model, max_output_tokens):
        self.calls += 1
        if self._always_fails:
            raise LLMProviderError(f"{self.name} luon that bai")
        return LLMCompletion(text=self._response_text, provider_name=self.name, model=model)


class LLMGatewayTest(unittest.TestCase):
    def test_first_provider_success_used_directly(self):
        primary = _FakeProvider("primary", response_text="primary answer")
        router = GatewayRouter(routes={TaskKind.COMPLEX_GROUNDED: [RouteTarget("primary", "m")]})
        gateway = LLMGateway(providers={"primary": primary}, router=router)
        result = gateway.complete("sys", "usr", task_kind=TaskKind.COMPLEX_GROUNDED)
        self.assertEqual(result, "primary answer")

    def test_falls_back_to_second_provider_on_first_failure(self):
        primary = _FakeProvider("primary", always_fails=True)
        fallback = _FakeProvider("fallback", response_text="fallback answer")
        router = GatewayRouter(routes={TaskKind.COMPLEX_GROUNDED: [
            RouteTarget("primary", "m"), RouteTarget("fallback", "m")]})
        gateway = LLMGateway(providers={"primary": primary, "fallback": fallback}, router=router)
        result = gateway.complete("sys", "usr", task_kind=TaskKind.COMPLEX_GROUNDED)
        self.assertEqual(result, "fallback answer")
        self.assertEqual(primary.calls, 1)
        self.assertEqual(fallback.calls, 1)

    def test_all_providers_failing_raises_provider_unavailable(self):
        primary = _FakeProvider("primary", always_fails=True)
        router = GatewayRouter(routes={TaskKind.COMPLEX_GROUNDED: [RouteTarget("primary", "m")]})
        gateway = LLMGateway(providers={"primary": primary}, router=router)
        with self.assertRaises(ChatProviderUnavailable):
            gateway.complete("sys", "usr", task_kind=TaskKind.COMPLEX_GROUNDED)

    def test_open_circuit_skips_provider_without_calling_it(self):
        primary = _FakeProvider("primary", response_text="should not be reached")
        fallback = _FakeProvider("fallback", response_text="fallback answer")
        router = GatewayRouter(routes={TaskKind.COMPLEX_GROUNDED: [
            RouteTarget("primary", "m"), RouteTarget("fallback", "m")]})
        breaker = CircuitBreaker(failure_threshold=1, clock_fn=lambda: 0.0)
        breaker.record_failure("primary")  # circuit now open for "primary"
        gateway = LLMGateway(providers={"primary": primary, "fallback": fallback},
                             router=router, circuit_breaker=breaker)
        result = gateway.complete("sys", "usr", task_kind=TaskKind.COMPLEX_GROUNDED)
        self.assertEqual(result, "fallback answer")
        self.assertEqual(primary.calls, 0)

    def test_repeated_failures_open_the_circuit_for_next_call(self):
        primary = _FakeProvider("primary", always_fails=True)
        fallback = _FakeProvider("fallback", response_text="fallback answer")
        router = GatewayRouter(routes={TaskKind.COMPLEX_GROUNDED: [
            RouteTarget("primary", "m"), RouteTarget("fallback", "m")]})
        breaker = CircuitBreaker(failure_threshold=1, clock_fn=lambda: 0.0)
        gateway = LLMGateway(providers={"primary": primary, "fallback": fallback},
                             router=router, circuit_breaker=breaker)
        gateway.complete("sys", "usr", task_kind=TaskKind.COMPLEX_GROUNDED)
        self.assertEqual(primary.calls, 1)
        gateway.complete("sys", "usr", task_kind=TaskKind.COMPLEX_GROUNDED)
        # Second call: circuit for "primary" should now be open, so it is
        # skipped entirely rather than called (and failed) again.
        self.assertEqual(primary.calls, 1)

    def test_output_budget_enforced_on_final_answer(self):
        primary = _FakeProvider("primary", response_text="x" * 100)
        router = GatewayRouter(routes={TaskKind.COMPLEX_GROUNDED: [RouteTarget("primary", "m")]})
        gateway = LLMGateway(providers={"primary": primary}, router=router,
                             budget=RetrievalBudget(max_output_chars=10))
        result = gateway.complete("sys", "usr", task_kind=TaskKind.COMPLEX_GROUNDED)
        self.assertLessEqual(len(result), 11)

    def test_as_llm_complete_fn_matches_pipeline_shape(self):
        primary = _FakeProvider("primary", response_text="answer")
        router = GatewayRouter(routes={TaskKind.COMPLEX_GROUNDED: [RouteTarget("primary", "m")]})
        gateway = LLMGateway(providers={"primary": primary}, router=router)
        fn = gateway.as_llm_complete_fn()
        self.assertEqual(fn("sys", "usr"), "answer")


if __name__ == "__main__":
    unittest.main()
