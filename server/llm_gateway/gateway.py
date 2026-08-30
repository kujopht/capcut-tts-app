"""
LLM Gateway entrypoint — Fanfic AI Chat V1 Phase 7/8.

The single object `server/chat/pipeline.py` calls through (via a plain
`(system, user) -> str` callable, never a direct import of this class -
see `pipeline.py`'s own docstring for why). Ties together: provider
fallback chain (`routing.GatewayRouter`), per-provider circuit breaker
(`usage_limits.CircuitBreaker`), and an output-size backstop
(`usage_limits.enforce_output_budget`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from server.llm_gateway.provider import LLMProvider, LLMProviderError
from server.llm_gateway.routing import GatewayRouter, TaskKind
from server.llm_gateway.usage_limits import (
    ChatProviderUnavailable, CircuitBreaker, RetrievalBudget, enforce_output_budget,
)


@dataclass
class LLMGateway:
    providers: Dict[str, LLMProvider]
    router: GatewayRouter
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    budget: RetrievalBudget = field(default_factory=RetrievalBudget)

    def complete(self, system: str, user: str, *, task_kind: TaskKind) -> str:
        """Tries each route target for `task_kind` in order, skipping any
        whose circuit is open, until one succeeds. Raises
        `ChatProviderUnavailable` only when EVERY target was skipped or
        failed - never silently returns an empty/placeholder answer."""
        last_error: Optional[Exception] = None
        tried_any = False
        for target in self.router.targets_for(task_kind):
            if self.circuit_breaker.is_open(target.provider_name):
                continue
            provider = self.providers.get(target.provider_name)
            if provider is None:
                continue
            tried_any = True
            try:
                result = provider.complete(
                    system=system, user=user, model=target.model,
                    max_output_tokens=self.budget.max_output_tokens)
            except LLMProviderError as exc:
                self.circuit_breaker.record_failure(target.provider_name)
                last_error = exc
                continue
            self.circuit_breaker.record_success(target.provider_name)
            return enforce_output_budget(result.text, budget=self.budget)

        if last_error is not None:
            raise ChatProviderUnavailable(
                f"Tất cả nhà cung cấp cho '{task_kind.value}' đều thất bại: {last_error}"
            ) from last_error
        detail = "mọi mạch đều đang mở" if tried_any else "không có nhà cung cấp nào khả dụng"
        raise ChatProviderUnavailable(f"Không có route khả dụng cho '{task_kind.value}' ({detail}).")

    def as_llm_complete_fn(self, *, task_kind: TaskKind = TaskKind.COMPLEX_GROUNDED):
        """Returns a plain `(system, user) -> str` closure matching
        `server.chat.pipeline.LlmCompleteFn` - the actual injection point
        a route handler passes into `pipeline.answer_question`."""
        def _fn(system: str, user: str) -> str:
            return self.complete(system, user, task_kind=task_kind)
        return _fn
