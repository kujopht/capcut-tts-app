"""
Capability/cost routing — Fanfic AI Chat V1 Phase 7.

Cheap/simple work goes to a cheaper model; complex grounded reasoning
(citing multiple retrieved chapters, resolving character relationships)
goes to a stronger one; translation is its OWN route - and in practice the
translation-helper feature (mission Phase 6E) calls the EXISTING
`server/translation_provider_registry.py` infrastructure directly rather
than through this gateway at all ("Translation may call the existing
translation infrastructure where appropriate", per the mission brief) -
`TaskKind.TRANSLATION` exists here for completeness/documentation, not
because this gateway implements translation itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class TaskKind(str, Enum):
    CHEAP_SIMPLE = "cheap_simple"
    COMPLEX_GROUNDED = "complex_grounded"
    TRANSLATION = "translation"


@dataclass(frozen=True)
class RouteTarget:
    provider_name: str
    model: str


@dataclass
class GatewayRouter:
    """`routes[task_kind]` is an ORDERED fallback chain - `gateway.py`
    tries each target in order, skipping any whose provider has an open
    circuit breaker or produced an error, until one succeeds."""

    routes: Dict[TaskKind, List[RouteTarget]] = field(default_factory=dict)

    def targets_for(self, task_kind: TaskKind) -> List[RouteTarget]:
        targets = self.routes.get(task_kind)
        if not targets:
            raise ValueError(f"Khong co route nao cau hinh cho '{task_kind.value}'.")
        return targets
