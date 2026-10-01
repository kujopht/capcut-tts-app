"""
AI control plane — routing.

`plan()` turns (config, mode, workload) into an ORDERED candidate list, each
with a skip reason or None (eligible):

  profile = web_search_profile if workload == "web_search" else mode_profiles[mode]
  for step in profile.steps:
      provider type -> that type's slots, by priority (lower first), and within
                       one priority a BALANCED weighted random order: weight x
                       the plane's balance factor (remaining daily/minute
                       headroom, penalised after recent 429s / failures) — so a
                       pool of equal-priority slots drains evenly instead of one
                       project being exhausted first (rng injectable ->
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
import time
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
#: Hết MỖI NGÀY: chỉ sang ngày mới (UTC) mới có lại -> báo `ai_budget_exhausted` kèm giờ reset.
DAILY_CAP_REASONS = frozenset({SKIP_REQUEST_CAP, SKIP_TOKEN_CAP})
#: Tạm thời: hết trong vài giây (cửa sổ RPM/TPM trượt 60 s) hoặc vài phút (cooldown) -> KHÔNG được báo như hết hạn ngày,
#: nếu không giao diện nói "công suất chung đã hết, chờ tới ngày mai" cho một tình trạng tự hết sau một phút.
WINDOW_REASONS = frozenset({SKIP_RPM, SKIP_TPM})
TRANSIENT_REASONS = WINDOW_REASONS | {SKIP_COOLDOWN}

#: Tổng thời gian tối đa (giây) cho CHUỖI thử slot trước token đầu tiên của một lượt: sau mức này không bắt đầu thêm
#: lần thử nào. Mỗi slot vẫn chỉ thử tối đa một lần, nhưng trước đây 8 slot cùng treo là 8 x 60 s giữ một luồng SSE (1 trong
#: 4 luồng của instance) hàng chục phút; lúc đó chính người dùng đã bỏ đi từ lâu.
FAILOVER_BUDGET_S = 45.0
#: `Retry-After` do nhà cung cấp gửi bị kẹp lại ở đây (provider đã kẹp, đây là lớp phòng thủ thứ hai cho provider tương lai).
COOLDOWN_MIN_S = 1.0
COOLDOWN_MAX_S = 600.0


def _clamp_cooldown(seconds: Optional[float]) -> float:
    if seconds is None:
        return DEFAULT_429_COOLDOWN_S
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return DEFAULT_429_COOLDOWN_S
    if value != value:  # NaN
        return DEFAULT_429_COOLDOWN_S
    return max(COOLDOWN_MIN_S, min(COOLDOWN_MAX_S, value))


def exhausted_event(candidates: Sequence[Tuple[ProviderSlot, Optional[str]]]) -> ErrorEvent:
    """Lỗi cuối cùng khi KHÔNG slot nào được thử. Chọn mã theo nguyên nhân THẬT để giao diện nói đúng điều gì sắp xảy ra:
    tạm thời (RPM/TPM/cooldown) -> thử lại sau ít giây/phút; hết hạn ngày -> chờ reset; không có gì cấu hình -> không có nhà
    cung cấp. Có bất kỳ slot nào chỉ TẠM bị chặn thì tình trạng sẽ tự hết, nên ưu tiên báo tạm thời."""
    reasons = {r for _, r in candidates if r}
    transient = reasons & TRANSIENT_REASONS
    if transient:
        if transient <= WINDOW_REASONS:
            return ErrorEvent(code="ai_busy", message="Trợ lý AI đang bận — thử lại sau ít giây.")
        return ErrorEvent(code="ai_provider_unavailable",
                          message="Các nhà cung cấp AI đang tạm nghỉ — thử lại sau ít phút.")
    if reasons & DAILY_CAP_REASONS:
        return ErrorEvent(code="ai_budget_exhausted", message="Trợ lý AI đã dùng hết hạn mức hiện có — thử lại sau.")
    return ErrorEvent(code="ai_no_provider", message="Chưa có nhà cung cấp AI nào khả dụng.")


BalanceFn = Callable[[ProviderSlot], float]
#: A factor never reaches 0: a nearly-full or penalised slot stays reachable
#: as a late fallback (caps/cooldown skip it outright when they apply).
MIN_BALANCE_FACTOR = 0.01


def weighted_order(slots: Sequence[ProviderSlot], rng: random.Random,
                   balance: Optional[BalanceFn] = None) -> List[ProviderSlot]:
    """Priority ascending; inside one priority, a weighted random permutation
    (each pick proportional to `weight` x `balance(slot)`, the factor in
    (0, 1] that the control plane derives from live headroom). Stable input
    order breaks ties so a seeded rng gives the same answer every run."""
    out: List[ProviderSlot] = []
    by_prio: Dict[int, List[ProviderSlot]] = {}
    for s in sorted(slots, key=lambda x: (x.priority, x.slot_id)):
        by_prio.setdefault(s.priority, []).append(s)

    def eff(s: ProviderSlot) -> float:
        f = 1.0 if balance is None else balance(s)
        return max(1, s.weight) * min(1.0, max(MIN_BALANCE_FACTOR, f))

    for prio in sorted(by_prio):
        pool = [(s, eff(s)) for s in by_prio[prio]]
        while pool:
            total = sum(w for _, w in pool)
            r = rng.uniform(0, total)
            acc = 0.0
            for i, (s, w) in enumerate(pool):
                acc += w
                if r <= acc:
                    out.append(pool.pop(i)[0])
                    break
            else:  # float edge: take the last
                out.append(pool.pop()[0])
    return out


SkipFn = Callable[[ProviderSlot, str, int], Optional[str]]


def plan(cfg: ControlConfig, *, mode: str, workload: str, rng: random.Random,
         skip_reason: SkipFn, est_tokens: int = 0,
         balance: Optional[BalanceFn] = None) -> List[Tuple[ProviderSlot, Optional[str]]]:
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
            group = weighted_order([s for s in cfg.slots.values() if s.provider_type == step], rng, balance)
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
               workload: Optional[str] = None, cancel: Optional[Callable[[], bool]] = None,
               on_attempt: Optional[Callable[[str, str], None]] = None) -> Iterator[StreamEvent]:
        """`cancel()` -> True nghĩa là không còn ai đọc kết quả (client đã ngắt/dừng): không được BẮT ĐẦU thêm lời gọi nhà
        cung cấp nào nữa. Nó chỉ chặn được lần thử KẾ TIẾP — một lần thử đang chờ mạng thì tự hết hạn theo timeout của chính
        nó — nhưng đủ để một lượt bị bỏ không đi hết cả chuỗi slot, mỗi slot tốn một lượt quota thật.

        `on_attempt(slot_id, model)` được gọi NGAY TRƯỚC mỗi lời gọi nhà cung cấp (trên luồng bơm). `ProviderServed` chỉ phát ra
        khi đã có token đầu, nên một lượt bị client bỏ ngang LÚC nhà cung cấp còn đang xử lý trước đây không để lại dấu vết slot
        nào: nhà cung cấp đã bị gọi thật nhưng trần toàn cục không đếm — N tài khoản x 5 lượt "gửi rồi ngắt" né được trần 150."""
        plane = self._plane
        clock = getattr(plane, "_clock", None) or time.monotonic
        cfg = plane.snapshot()  # type: ignore[attr-defined]
        limits = MODE_LIMITS.get(mode, MODE_LIMITS["general"])
        max_ctx = min(limits["max_context_tokens"], cfg.controls.max_context_tokens)
        max_out = min(limits["max_output_tokens"], cfg.controls.max_output_tokens)
        trimmed = trim_context(messages, max_tokens=max_ctx)
        est = sum(estimate_tokens(t.content) for t in trimmed) + max_out
        wl = workload or mode
        candidates = plane.plan(cfg, mode=mode, workload=wl, est_tokens=est)  # type: ignore[attr-defined]
        tried_any = False
        first_attempt_at = 0.0
        for slot, reason in candidates:
            if reason is not None:
                continue
            if cancel is not None and cancel():
                return
            if tried_any and clock() - first_attempt_at >= FAILOVER_BUDGET_S:
                log.warning("ai_control: failover budget (%ss) spent — not trying further slots", FAILOVER_BUDGET_S)
                break
            key = plane.secret_for(slot)  # type: ignore[attr-defined]
            if not key:
                continue
            provider = plane.provider_for(slot, key)  # type: ignore[attr-defined]
            if not tried_any:
                first_attempt_at = clock()
            tried_any = True
            plane.note_attempt(slot, est)  # type: ignore[attr-defined]
            if on_attempt is not None:
                try:
                    on_attempt(slot.slot_id, slot.model)
                except Exception:  # noqa: BLE001 — phép đo phụ, không bao giờ làm hỏng lượt
                    log.warning("ai_control: on_attempt callback failed", exc_info=True)
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
                category = getattr(exc, "category", None)
                if exc.code == "provider_http_429" or exc.retry_after_s is not None:
                    plane.breaker.cool_down(  # type: ignore[attr-defined]
                        slot.slot_id, _clamp_cooldown(exc.retry_after_s))
                    plane.note_rate_limited(slot, exc.code, category)  # type: ignore[attr-defined]
                else:
                    plane.breaker.record_failure(slot.slot_id)  # type: ignore[attr-defined]
                    if not started:
                        plane.note_error(slot, exc.code, category)  # type: ignore[attr-defined]
                    else:
                        # Mid-stream: not counted as a request error (usage is billed), but
                        # the slot's health still shows WHY the stream broke.
                        plane.note_failure(slot, exc.code, category)  # type: ignore[attr-defined]
                if started:
                    yield ErrorEvent(code="ai_provider_interrupted",
                                     message="Kết nối tới nhà cung cấp AI bị gián đoạn giữa chừng — thử lại sau.")
                    return
                continue
            except Exception:  # noqa: BLE001 — same R1 backstop as AiGateway
                log.warning("ai_control: slot %s raised an unexpected error", slot.slot_id, exc_info=True)
                plane.breaker.record_failure(slot.slot_id)  # type: ignore[attr-defined]
                if started:
                    plane.note_failure(slot, "provider_unexpected_error")  # type: ignore[attr-defined]
                    yield ErrorEvent(code="ai_provider_interrupted", message="Nhà cung cấp AI gặp sự cố không mong đợi.")
                    return
                plane.note_error(slot, "provider_unexpected_error")  # type: ignore[attr-defined]
                continue
        if tried_any:
            yield ErrorEvent(code="ai_provider_unavailable",
                             message="Tất cả nhà cung cấp AI đều đang gặp sự cố — thử lại sau.")
        else:
            yield exhausted_event(candidates)
