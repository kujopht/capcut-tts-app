"""
AI control plane — routing.

`plan()` turns (config, mode, workload) into an ORDERED candidate list, each
with a skip reason or None (eligible):

  profile = web_search_profile if workload == "web_search" else mode_profiles[mode]
  for step in profile.steps:
      provider type -> that type's slots, by priority (lower first), and within
                       one priority a weighted random order (rng injectable ->
                       deterministic in tests)
      slot id       -> that slot

`ControlledGateway.stream()` then tries eligible slots IN ORDER, each at most
once per request (never an infinite retry loop), with the same fallback rule
as `AiGateway`: switching slots is only allowed before the first `Delta`.
A 429 cools that slot down for its Retry-After; other failures feed the
per-slot circuit breaker. No eligible slot -> a friendly error event.
"""
from __future__ import annotations

import contextlib
import logging
import random
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple

from server.ai_assistant.config import MODE_LIMITS, estimate_tokens
from server.ai_assistant.control.model import PROVIDER_TYPES, ControlConfig, ProviderSlot
from server.ai_assistant.gateway import DEFAULT_429_COOLDOWN_S, ErrorEvent, ProviderServed, trim_context
from server.llm_gateway.chat_provider import ChatTurn, Delta, GenerateRequest, ProviderError, StreamEvent

log = logging.getLogger("fanfic.ai_assistant")

#: Skip reasons (stable strings — shown in the admin UI and asserted in tests).
SKIP_SLOT_DISABLED = "slot_disabled"
SKIP_TYPE_DISABLED = "type_disabled"
SKIP_WORKLOAD = "workload_not_allowed"
SKIP_MISSING_SECRET = "missing_secret"
SKIP_COOLDOWN = "cooldown"
SKIP_REQUEST_CAP = "request_cap"
SKIP_TOKEN_CAP = "token_cap"
SKIP_RPM = "rpm_soft_cap"
SKIP_TPM = "tpm_soft_cap"
CAP_REASONS = frozenset({SKIP_REQUEST_CAP, SKIP_TOKEN_CAP, SKIP_RPM, SKIP_TPM})


def weighted_order(slots: Sequence[ProviderSlot], rng: random.Random) -> List[ProviderSlot]:
    """Priority ascending; inside one priority, a weighted random permutation
    (each pick proportional to `weight`). Stable input order breaks ties so a
    seeded rng gives the same answer every run."""
    out: List[ProviderSlot] = []
    by_prio: Dict[int, List[ProviderSlot]] = {}
    for s in sorted(slots, key=lambda x: (x.priority, x.slot_id)):
        by_prio.setdefault(s.priority, []).append(s)
    for prio in sorted(by_prio):
        pool = list(by_prio[prio])
        while pool:
            total = sum(max(1, s.weight) for s in pool)
            r = rng.uniform(0, total)
            acc = 0.0
            for i, s in enumerate(pool):
                acc += max(1, s.weight)
                if r <= acc:
                    out.append(pool.pop(i))
                    break
            else:  # float edge: take the last
                out.append(pool.pop())
    return out


SkipFn = Callable[[ProviderSlot, str, int], Optional[str]]


def plan(cfg: ControlConfig, *, mode: str, workload: str, rng: random.Random,
         skip_reason: SkipFn, est_tokens: int = 0) -> List[Tuple[ProviderSlot, Optional[str]]]:
    c = cfg.controls
    if not c.ai_enabled:
        return []
    name = c.web_search_profile if workload == "web_search" else c.mode_profiles.get(mode, "")
    profile = cfg.profiles.get(name)
    if profile is None or not profile.enabled:
        return []
    seen = set()
    out: List[Tuple[ProviderSlot, Optional[str]]] = []
    for step in profile.steps:
        if step in PROVIDER_TYPES:
            group = weighted_order([s for s in cfg.slots.values() if s.provider_type == step], rng)
        else:
            group = [cfg.slots[step]] if step in cfg.slots else []
        for s in group:
            if s.slot_id in seen:
                continue
            seen.add(s.slot_id)
            out.append((s, skip_reason(s, workload, est_tokens)))
    return out


class ControlledGateway:
    """Drop-in for `AiGateway.stream()` backed by the control plane."""

    def __init__(self, plane: "object") -> None:
        self._plane = plane

    def stream(self, messages: List[ChatTurn], *, mode: str, user_ref: str = "",
               workload: Optional[str] = None) -> Iterator[StreamEvent]:
        plane = self._plane
        cfg = plane.snapshot()  # type: ignore[attr-defined]
        limits = MODE_LIMITS.get(mode, MODE_LIMITS["general"])
        max_ctx = min(limits["max_context_tokens"], cfg.controls.max_context_tokens)
        max_out = min(limits["max_output_tokens"], cfg.controls.max_output_tokens)
        trimmed = trim_context(messages, max_tokens=max_ctx)
        est = sum(estimate_tokens(t.content) for t in trimmed) + max_out
        wl = workload or mode
        candidates = plane.plan(cfg, mode=mode, workload=wl, est_tokens=est)  # type: ignore[attr-defined]
        tried_any = False
        for slot, reason in candidates:
            if reason is not None:
                continue
            key = plane.secret_for(slot)  # type: ignore[attr-defined]
            if not key:
                continue
            provider = plane.provider_for(slot, key)  # type: ignore[attr-defined]
            tried_any = True
            plane.note_attempt(slot, est)  # type: ignore[attr-defined]
            req = GenerateRequest(messages=trimmed, model=slot.model, max_output_tokens=max_out, user_ref=user_ref)
            started = False
            try:
                with contextlib.closing(provider.stream(req)) as events:
                    for ev in events:
                        if isinstance(ev, Delta) and not started:
                            started = True
                            yield ProviderServed(provider_name=slot.slot_id, model=slot.model)
                        yield ev
                plane.breaker.record_success(slot.slot_id)  # type: ignore[attr-defined]
                return
            except ProviderError as exc:
                if exc.code == "provider_http_429" or exc.retry_after_s is not None:
                    plane.breaker.cool_down(  # type: ignore[attr-defined]
                        slot.slot_id, exc.retry_after_s if exc.retry_after_s is not None else DEFAULT_429_COOLDOWN_S)
                    plane.note_rate_limited(slot)  # type: ignore[attr-defined]
                else:
                    plane.breaker.record_failure(slot.slot_id)  # type: ignore[attr-defined]
                    if not started:
                        plane.note_error(slot)  # type: ignore[attr-defined]
                if started:
                    yield ErrorEvent(code="ai_provider_interrupted",
                                     message="Kết nối tới nhà cung cấp AI bị gián đoạn giữa chừng — thử lại sau.")
                    return
                continue
            except Exception:  # noqa: BLE001 — same R1 backstop as AiGateway
                log.warning("ai_control: slot %s raised an unexpected error", slot.slot_id, exc_info=True)
                plane.breaker.record_failure(slot.slot_id)  # type: ignore[attr-defined]
                if started:
                    yield ErrorEvent(code="ai_provider_interrupted", message="Nhà cung cấp AI gặp sự cố không mong đợi.")
                    return
                plane.note_error(slot)  # type: ignore[attr-defined]
                continue
        if tried_any:
            yield ErrorEvent(code="ai_provider_unavailable",
                             message="Tất cả nhà cung cấp AI đều đang gặp sự cố — thử lại sau.")
        elif any(r in CAP_REASONS for _, r in candidates):
            yield ErrorEvent(code="ai_budget_exhausted", message="Trợ lý AI đã dùng hết hạn mức hiện có — thử lại sau.")
        else:
            yield ErrorEvent(code="ai_no_provider", message="Chưa có nhà cung cấp AI nào khả dụng.")
