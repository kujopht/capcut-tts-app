"""
AI control plane — the service object shared by the chat routes (admission,
routing, usage) and the admin routes (views, validated mutations, audit).

FAIL-CLOSED rules (the whole point of this module):
  * No stored settings -> `GlobalControls()` defaults: ai_enabled=False, every
    provider type off. Nothing routes until an owner turns things on.
  * A stored row that cannot be parsed, or a config that fails validation ->
    `state="corrupt"`, effective config = AI off. Never "defaults that route".
  * Store unreachable -> the last GOOD config (already validated) for up to
    `STALE_OK_S`, then AI off. Never an unrestricted provider.
  * A slot without its secret, over a cap, cooling down, disabled, or whose
    provider type is off is skipped; if nothing remains the user gets a
    friendly error — the loop never retries a slot twice in one request.
"""
from __future__ import annotations

import functools
import json
import logging
import random
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Mapping, Optional, Tuple

from server.ai_assistant.control.model import (
    DEFAULT_ENDPOINTS, ENDPOINT_HOSTS, MAX_SLOTS, MODES, PROFILES, PROVIDER_LABELS, PROVIDER_TYPES, WORKLOADS,
    ConfigValidationError, ControlConfig, GlobalControls, ProviderSlot, RoutingProfile, controls_to_dict,
    controls_with, slot_from_dict, slot_to_dict, validate_config, validate_controls, validate_profile,
    validate_slot,
)
from server.ai_assistant.control.providers import ProviderFactory
from server.ai_assistant.control.router import (
    SKIP_COOLDOWN, SKIP_MISSING_SECRET, SKIP_REQUEST_CAP, SKIP_RPM, SKIP_SLOT_DISABLED, SKIP_TOKEN_CAP,
    SKIP_TPM, SKIP_TYPE_DISABLED, SKIP_WORKLOAD, plan as _plan,
)
from server.ai_assistant.control.secrets import SecretResolver
from server.ai_assistant.control.store import (
    AuditEntry, ControlConfigCorrupt, ControlStore, ControlStoreUnavailable, UsageCounters, now_iso,
)
from server.ai_assistant.gateway import DEFAULT_429_COOLDOWN_S
from server.llm_gateway.chat_provider import ChatProvider, ChatTurn, GenerateRequest, ProviderError
from server.llm_gateway.usage_limits import CircuitBreaker

log = logging.getLogger("fanfic.ai_assistant")


def _serialized(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Run one admin mutation at a time in this process. Appwrite has no
    conditional write, so without this two tabs (e.g. a provider toggle and the
    emergency OFF) could each rewrite the whole `global` row from a stale read
    and one change would be lost. Across instances the race remains (documented)."""
    @functools.wraps(fn)
    def wrapper(self: "ControlPlane", *a: Any, **kw: Any) -> Any:
        with self._mut_lock:
            return fn(self, *a, **kw)
    return wrapper

CACHE_TTL_S = 15.0
STALE_OK_S = 600.0
USAGE_TTL_S = 10.0
#: `provider_http_404`, `provider_network_error` … (see chat_providers).
_ERROR_CODE_RE = re.compile(r"^provider_[a-z0-9_]{1,40}$")
#: Vendor enums only: upper/lower letters, underscore, one optional ':' joiner. No digits.
_ERROR_CATEGORY_RE = re.compile(r"^[A-Za-z_]{3,48}(:[A-Z_]{3,48})?$")
#: Balancing (`ControlPlane.balance_factor`): weight multiplier for a slot that is failing
#: or was rate-limited in the last RECENT_429_WINDOW_S.
BALANCE_PENALTY = 0.25
RECENT_429_WINDOW_S = 600.0
#: Owner probe (`ControlPlane.probe`): one real minimal request per slot at most this often.
PROBE_MIN_INTERVAL_S = 20.0
PROBE_MAX_OUTPUT_TOKENS = 64


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _reset_at_iso() -> str:
    d = datetime.now(timezone.utc)
    nxt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() + 86400
    return datetime.fromtimestamp(nxt, tz=timezone.utc).isoformat(timespec="seconds")


class ControlConflict(Exception):
    """A mutation that cannot apply as asked (duplicate id, referenced slot,
    stale version, config currently corrupt)."""


@dataclass(frozen=True)
class AdmissionError:
    status: int
    code: str
    message: str
    reset_at: Optional[str] = None


class _Window:
    """Last-60-seconds request/token counts for one slot (soft RPM/TPM caps)."""

    def __init__(self) -> None:
        self.events: Deque[Tuple[float, int]] = deque()

    def prune(self, now: float) -> None:
        while self.events and now - self.events[0][0] > 60.0:
            self.events.popleft()

    def counts(self, now: float) -> Tuple[int, int]:
        self.prune(now)
        return len(self.events), sum(t for _, t in self.events)


class ControlPlane:
    def __init__(self, store: ControlStore, *, secrets: Optional[SecretResolver] = None,
                 factory: Optional[ProviderFactory] = None, breaker: Optional[CircuitBreaker] = None,
                 clock: Callable[[], float] = time.monotonic, rng: Optional[random.Random] = None,
                 active_users_fn: Optional[Callable[[str], Optional[int]]] = None,
                 user_usage_fn: Optional[Callable[[str, str], Tuple[int, int]]] = None) -> None:
        self.store = store
        self.secrets = secrets or SecretResolver()
        self.factory = factory or ProviderFactory()
        self.breaker = breaker or CircuitBreaker(clock_fn=clock)
        self._clock = clock
        self._rng = rng or random.Random()
        self._active_users_fn = active_users_fn
        self._user_usage_fn = user_usage_fn
        self._lock = threading.Lock()
        self._mut_lock = threading.RLock()
        self._cfg: Optional[ControlConfig] = None
        self._cfg_at = 0.0
        self._good_at = 0.0
        self.state = "empty"
        self._usage: Dict[str, UsageCounters] = {}
        self._usage_day = ""
        self._usage_at = -1e9
        self._windows: Dict[str, _Window] = {}
        self._recent_429: Dict[str, Deque[float]] = {}
        #: slot_id -> (code, category, at_iso) of the LAST provider failure. In-process like
        #: the breaker (a restart clears it); only sanitized enums, never a vendor message.
        self._last_error: Dict[str, Tuple[str, Optional[str], str]] = {}
        #: slot_id -> monotonic time of the last owner probe (rate limit, in-process).
        self._probe_at: Dict[str, float] = {}

    def attach_usage_sources(self, *, active_users_fn: Optional[Callable[[str], Optional[int]]] = None,
                             user_usage_fn: Optional[Callable[[str, str], Tuple[int, int]]] = None) -> None:
        """Wired by `build_ai_runtime` once the AI repo exists (the plane itself
        is built earlier so `/admin/ai` works even while the assistant is off)."""
        if active_users_fn is not None:
            self._active_users_fn = active_users_fn
        if user_usage_fn is not None:
            self._user_usage_fn = user_usage_fn

    # ------------------------------------------------------------ config
    def invalidate(self) -> None:
        with self._lock:
            self._cfg_at = -1e9

    def snapshot(self) -> ControlConfig:
        now = self._clock()
        with self._lock:
            if self._cfg is not None and now - self._cfg_at < CACHE_TTL_S:
                return self._cfg
        try:
            cfg = self.store.load()
            validate_config(cfg)
            state = "ok" if (cfg.controls.version or cfg.slots) else "empty"
            with self._lock:
                self._cfg, self._cfg_at, self._good_at, self.state = cfg, now, now, state
            return cfg
        except (ControlConfigCorrupt, ConfigValidationError, ValueError, TypeError):
            log.error("ai_control: stored configuration is corrupt — AI is fail-closed until it is repaired")
            closed = self._closed()
            with self._lock:
                self._cfg, self._cfg_at, self.state = closed, now, "corrupt"
            return closed
        except ControlStoreUnavailable:
            with self._lock:
                last_good = self._cfg if self.state in ("ok", "empty", "stale") else None
                if last_good is not None and now - self._good_at < STALE_OK_S:
                    self.state, self._cfg_at = "stale", now
                    return last_good
                closed = self._closed()
                self._cfg, self._cfg_at, self.state = closed, now, "unavailable"
                return closed

    @staticmethod
    def _closed() -> ControlConfig:
        from server.ai_assistant.control.model import empty_config
        return empty_config()

    # ------------------------------------------------------------ usage (today)
    def usage_today(self) -> Dict[str, UsageCounters]:
        return self._usage_state()[0]

    def _usage_state(self) -> Tuple[Dict[str, UsageCounters], bool]:
        """Today's per-slot counters and whether they are KNOWN. Unknown (store
        unreachable and nothing cached for today) must not read as 0: admission
        refuses instead. A failed read keeps the last numbers and waits a full
        TTL before retrying, so an outage does not add a store timeout to every turn."""
        day, now = today_utc(), self._clock()
        with self._lock:
            if day == self._usage_day and now - self._usage_at < USAGE_TTL_S:
                return {k: replace(v) for k, v in self._usage.items()}, True
        try:
            usage = self.store.usage_for_day(day)
        except ControlStoreUnavailable:
            with self._lock:
                if day == self._usage_day:
                    self._usage_at = now
                    return {k: replace(v) for k, v in self._usage.items()}, True
                return {}, False
        with self._lock:
            self._usage, self._usage_day, self._usage_at = usage, day, now
            return {k: replace(v) for k, v in usage.items()}, True

    def _bump_local(self, slot_id: str, **delta: int) -> None:
        with self._lock:
            if self._usage_day != today_utc():
                return
            u = self._usage.setdefault(slot_id, UsageCounters())
            for k, v in delta.items():
                setattr(u, k, getattr(u, k) + v)

    @staticmethod
    def cost_micro(slot: ProviderSlot, input_tokens: int, output_tokens: int) -> int:
        return (input_tokens * slot.price_in_micro_per_mtok + output_tokens * slot.price_out_micro_per_mtok) // 1_000_000

    # ------------------------------------------------------------ routing hooks
    def skip_reason(self, slot: ProviderSlot, workload: str, est_tokens: int,
                    cfg: Optional[ControlConfig] = None, usage: Optional[Dict[str, UsageCounters]] = None) -> Optional[str]:
        cfg = cfg or self.snapshot()
        if not slot.enabled:
            return SKIP_SLOT_DISABLED
        if not cfg.controls.provider_types.get(slot.provider_type, False):
            return SKIP_TYPE_DISABLED
        if workload not in slot.workloads:
            return SKIP_WORKLOAD
        if not self.secrets.status(slot.secret_ref).present:
            return SKIP_MISSING_SECRET
        if self.breaker.is_open(slot.slot_id):
            return SKIP_COOLDOWN
        u = (usage if usage is not None else self.usage_today()).get(slot.slot_id, UsageCounters())
        if slot.daily_request_cap and u.requests >= slot.daily_request_cap:
            return SKIP_REQUEST_CAP
        if slot.daily_token_cap and u.tokens >= slot.daily_token_cap:
            return SKIP_TOKEN_CAP
        now = self._clock()
        with self._lock:
            n, tok = self._windows.setdefault(slot.slot_id, _Window()).counts(now)
        if slot.rpm_soft_cap and n >= slot.rpm_soft_cap:
            return SKIP_RPM
        if slot.tpm_soft_cap and tok + est_tokens > slot.tpm_soft_cap:
            return SKIP_TPM
        return None

    def balance_factor(self, slot: ProviderSlot, usage: Optional[Dict[str, UsageCounters]] = None) -> float:
        """How much of this slot is left, in (0, 1] — the multiplier on its routing weight.

        headroom = 1 - max(requests/day cap, tokens/day cap, last-minute requests/RPM cap,
        last-minute tokens/TPM cap) (a 0 cap = unlimited, ignored), squared so a nearly
        full project is picked far less than a fresh one. Then x0.25 if the slot is
        currently failing (breaker counting) and x0.25 if it hit a 429 in the last
        RECENT_429_WINDOW_S. Cooldown / cap / disabled still skip the slot outright in
        `skip_reason`; this only orders the eligible ones."""
        u = (usage if usage is not None else self.usage_today()).get(slot.slot_id, UsageCounters())
        now = self._clock()
        with self._lock:
            n, tok = self._windows.setdefault(slot.slot_id, _Window()).counts(now)
        util = 0.0
        for used, cap in ((u.requests, slot.daily_request_cap), (u.tokens, slot.daily_token_cap),
                          (n, slot.rpm_soft_cap), (tok, slot.tpm_soft_cap)):
            if cap:
                util = max(util, used / cap)
        factor = max(0.0, 1.0 - min(1.0, util)) ** 2
        if self.breaker.snapshot().get(slot.slot_id, {}).get("consecutive_failures", 0) > 0:
            factor *= BALANCE_PENALTY
        if self.recent_429(slot.slot_id, RECENT_429_WINDOW_S) > 0:
            factor *= BALANCE_PENALTY
        return factor

    def plan(self, cfg: ControlConfig, *, mode: str, workload: str, est_tokens: int = 0):
        usage = self.usage_today()
        return _plan(cfg, mode=mode, workload=workload, rng=self._rng, est_tokens=est_tokens,
                     skip_reason=lambda s, w, e: self.skip_reason(s, w, e, cfg=cfg, usage=usage),
                     balance=lambda s: self.balance_factor(s, usage))

    def secret_for(self, slot: ProviderSlot) -> Optional[str]:
        return self.secrets.resolve(slot.secret_ref)

    def provider_for(self, slot: ProviderSlot, key: str) -> ChatProvider:
        return self.factory.get(slot, key)

    def note_attempt(self, slot: ProviderSlot, est_tokens: int) -> None:
        with self._lock:
            self._windows.setdefault(slot.slot_id, _Window()).events.append((self._clock(), est_tokens))

    def note_failure(self, slot: ProviderSlot, code: Optional[str], category: Optional[str] = None) -> None:
        """Remember the sanitized classification of a slot's latest failure (any phase,
        including mid-stream). `code` must look like `provider_*`, `category` like a vendor
        enum (`NOT_FOUND`, `PERMISSION_DENIED:SERVICE_DISABLED`, `model_not_found`) —
        anything else is replaced, so free text can never reach the admin API."""
        c = code if isinstance(code, str) and _ERROR_CODE_RE.match(code) else "provider_error"
        cat = category if isinstance(category, str) and _ERROR_CATEGORY_RE.match(category) else None
        with self._lock:
            self._last_error[slot.slot_id] = (c, cat, now_iso())

    def last_error(self, slot_id: str) -> Optional[Dict[str, Optional[str]]]:
        with self._lock:
            e = self._last_error.get(slot_id)
        return {"code": e[0], "category": e[1], "at": e[2]} if e else None

    def note_rate_limited(self, slot: ProviderSlot, code: Optional[str] = "provider_http_429",
                          category: Optional[str] = None) -> None:
        with self._lock:
            dq = self._recent_429.setdefault(slot.slot_id, deque())
            dq.append(self._clock())
        self.note_failure(slot, code, category)
        self._bump_local(slot.slot_id, rate_limited=1)
        self._safe_usage(slot.slot_id, rate_limited=1)

    def note_error(self, slot: ProviderSlot, code: Optional[str] = "provider_error",
                   category: Optional[str] = None) -> None:
        self.note_failure(slot, code, category)
        self._bump_local(slot.slot_id, errors=1)
        self._safe_usage(slot.slot_id, errors=1)

    def record_turn(self, slot_id: str, input_tokens: int, output_tokens: int, status: str) -> None:
        """Called once per turn for the slot that SERVED it (route finalize)."""
        cfg = self.snapshot()
        slot = cfg.slots.get(slot_id)
        cost = self.cost_micro(slot, input_tokens, output_tokens) if slot else 0
        err = 1 if status == "error" else 0
        ok_at = now_iso() if status in ("complete", "stopped") else ""
        self._bump_local(slot_id, requests=1, input_tokens=input_tokens, output_tokens=output_tokens,
                         errors=err, cost_micro_usd=cost)
        self._safe_usage(slot_id, requests=1, input_tokens=input_tokens, output_tokens=output_tokens,
                         errors=err, cost_micro_usd=cost, success_at=ok_at)

    def _safe_usage(self, slot_id: str, **kw: Any) -> None:
        try:
            self.store.add_usage(slot_id, today_utc(), **kw)
        except ControlStoreUnavailable:
            log.warning("ai_control: usage counter write skipped (store unavailable)")

    def recent_429(self, slot_id: str, window_s: float = 3600.0) -> int:
        now = self._clock()
        with self._lock:
            dq = self._recent_429.get(slot_id)
            if not dq:
                return 0
            while dq and now - dq[0] > window_s:
                dq.popleft()
            return len(dq)

    # ------------------------------------------------------------ admission (chat route)
    def enabled(self) -> bool:
        return self.snapshot().controls.ai_enabled

    def admission(self, user_id: str) -> Optional[AdmissionError]:
        cfg = self.snapshot()
        c = cfg.controls
        if not c.ai_enabled:
            return AdmissionError(503, "ai_not_enabled", "Trợ lý AI đang tạm tắt.")
        usage, known = self._usage_state()
        if not known and (c.global_daily_request_cap or c.global_daily_token_cap or c.daily_cost_cap_micro_usd):
            return AdmissionError(503, "ai_storage_unavailable", "Chưa đọc được hạn mức AI — thử lại sau ít phút.")
        req = sum(u.requests for u in usage.values())
        tok = sum(u.tokens for u in usage.values())
        cost = sum(u.cost_micro_usd for u in usage.values())
        if (c.global_daily_request_cap and req >= c.global_daily_request_cap) or \
                (c.global_daily_token_cap and tok >= c.global_daily_token_cap) or \
                (c.daily_cost_cap_micro_usd and cost >= c.daily_cost_cap_micro_usd):
            return AdmissionError(429, "ai_budget_exhausted", "Trợ lý AI đã dùng hết hạn mức hôm nay.", _reset_at_iso())
        if self._user_usage_fn is not None:
            try:
                ureq, utok = self._user_usage_fn(user_id, today_utc())
            except Exception:  # noqa: BLE001 — unknown usage never means "under the cap"
                log.warning("ai_control: per-user usage unavailable — refusing the turn")
                return AdmissionError(503, "ai_storage_unavailable", "Chưa đọc được hạn mức AI — thử lại sau ít phút.")
            if (c.per_user_daily_request_cap and ureq >= c.per_user_daily_request_cap) or \
                    (c.per_user_daily_token_cap and utok >= c.per_user_daily_token_cap):
                return AdmissionError(429, "ai_budget_exhausted", "Bạn đã dùng hết lượt hỏi hôm nay.", _reset_at_iso())
        return None

    # ------------------------------------------------------------ admin views
    def slot_health(self, slot: ProviderSlot, cfg: ControlConfig, usage: Dict[str, UsageCounters]) -> Dict[str, Any]:
        snap = self.breaker.snapshot().get(slot.slot_id, {"consecutive_failures": 0, "open_for_s": 0.0})
        sec = self.secrets.status(slot.secret_ref)
        u = usage.get(slot.slot_id, UsageCounters())
        if not slot.enabled or not cfg.controls.provider_types.get(slot.provider_type, False):
            status = "DISABLED"
        elif not sec.present:
            status = "MISSING_SECRET"
        elif snap["open_for_s"] > 0:
            status = "COOLDOWN"
        elif (slot.daily_request_cap and u.requests >= slot.daily_request_cap) or \
                (slot.daily_token_cap and u.tokens >= slot.daily_token_cap):
            status = "OVER_CAP"
        elif snap["consecutive_failures"] > 0:
            status = "DEGRADED"
        else:
            status = "HEALTHY"
        return {"status": status, "cooldown_s": round(snap["open_for_s"], 1),
                "consecutive_failures": int(snap["consecutive_failures"]),
                "recent_429": max(self.recent_429(slot.slot_id), 0),
                "secret": {"ref": sec.secret_ref, "env_name": sec.env_name, "present": sec.present,
                           "fingerprint": sec.fingerprint},
                "usage_today": {"requests": u.requests, "input_tokens": u.input_tokens,
                                "output_tokens": u.output_tokens, "errors": u.errors,
                                "rate_limited": u.rate_limited, "cost_micro_usd": u.cost_micro_usd},
                "last_success_at": u.last_success_at or None,
                **self._last_error_fields(slot.slot_id)}

    def _last_error_fields(self, slot_id: str) -> Dict[str, Optional[str]]:
        e = self.last_error(slot_id) or {}
        return {"last_error_code": e.get("code"), "last_error_category": e.get("category"),
                "last_error_at": e.get("at")}

    def config_view(self) -> Dict[str, Any]:
        cfg = self.snapshot()
        usage = self.usage_today()
        slots = []
        for s in sorted(cfg.slots.values(), key=lambda x: (x.provider_type, x.priority, x.slot_id)):
            slots.append({**slot_to_dict(s), "effective_endpoint": s.effective_endpoint(),
                          "health": self.slot_health(s, cfg, usage)})
        return {
            "state": self.state,
            "controls": controls_to_dict(cfg.controls),
            "provider_types": [{"type": t, "label": PROVIDER_LABELS[t],
                                "enabled": bool(cfg.controls.provider_types.get(t, False)),
                                "slot_count": sum(1 for s in cfg.slots.values() if s.provider_type == t)}
                               for t in PROVIDER_TYPES],
            "slots": slots,
            "profiles": [{"name": p.name, "steps": list(p.steps), "enabled": p.enabled}
                         for p in (cfg.profiles[n] for n in PROFILES if n in cfg.profiles)],
            "meta": {"provider_types": list(PROVIDER_TYPES), "workloads": list(WORKLOADS),
                     "profiles": list(PROFILES), "modes": list(MODES),
                     "default_endpoints": dict(DEFAULT_ENDPOINTS),
                     "endpoint_hosts": {k: list(v) for k, v in ENDPOINT_HOSTS.items()},
                     # The admin UI renders from these instead of hard-coding
                     # provider names/rules into the (publicly fetchable) JS chunk.
                     "requires_endpoint": [t for t in PROVIDER_TYPES if t not in DEFAULT_ENDPOINTS],
                     "uses_api_version": ["azure_openai"],
                     "endpoint_hints": {
                         "workers_ai": "https://api.cloudflare.com/client/v4/accounts/<account_id>/ai/v1",
                         "azure_openai": "https://<resource>.openai.azure.com hoặc https://<resource>.cognitiveservices.azure.com",
                     },
                     "secret_env_prefix": "FAS_AI_SECRET_"},
        }

    def overview(self) -> Dict[str, Any]:
        cfg = self.snapshot()
        usage = self.usage_today()
        statuses: Dict[str, int] = {}
        for s in cfg.slots.values():
            st = self.slot_health(s, cfg, usage)["status"]
            statuses[st] = statuses.get(st, 0) + 1
        active: Optional[int] = None
        if self._active_users_fn is not None:
            try:
                active = self._active_users_fn(today_utc())
            except Exception:  # noqa: BLE001 — a metric, never a failure
                active = None
        c = cfg.controls
        tot = UsageCounters()
        for u in usage.values():
            tot.requests += u.requests
            tot.input_tokens += u.input_tokens
            tot.output_tokens += u.output_tokens
            tot.errors += u.errors
            tot.rate_limited += u.rate_limited
            tot.cost_micro_usd += u.cost_micro_usd
        return {
            "state": self.state, "day": today_utc(), "ai_enabled": c.ai_enabled,
            "requests": tot.requests, "input_tokens": tot.input_tokens, "output_tokens": tot.output_tokens,
            "errors": tot.errors, "rate_limited": tot.rate_limited, "est_cost_micro_usd": tot.cost_micro_usd,
            "active_users": active,
            "caps": {"global_daily_request_cap": c.global_daily_request_cap,
                     "global_daily_token_cap": c.global_daily_token_cap,
                     "daily_cost_cap_micro_usd": c.daily_cost_cap_micro_usd},
            "slots_by_status": statuses,
            "providers": [{"type": t, "label": PROVIDER_LABELS[t], "enabled": bool(c.provider_types.get(t)),
                           "healthy_slots": sum(1 for s in cfg.slots.values() if s.provider_type == t
                                                and self.slot_health(s, cfg, usage)["status"] == "HEALTHY"),
                           "slots": sum(1 for s in cfg.slots.values() if s.provider_type == t)}
                          for t in PROVIDER_TYPES],
        }

    def audit(self, limit: int = 50) -> List[Dict[str, str]]:
        return [{"admin_id": e.admin_id, "at": e.at, "entity": e.entity, "field": e.field,
                 "old_value": e.old_value, "new_value": e.new_value} for e in self.store.list_audit(limit)]

    # ------------------------------------------------------------ admin mutations (owner)
    def _fresh(self, *, repair: bool = False) -> ControlConfig:
        """The CURRENT stored config for a mutation — uncached, and refusing to
        build on top of a corrupt/unreachable store.

        `repair=True` (delete a slot, edit a profile, reset a cooldown) still
        works when every row parses but the WHOLE config fails validation — e.g.
        a profile left pointing at a slot another instance just deleted. Those
        edits are how the owner gets out of that state from /admin/ai; the edit
        itself is still validated and AI stays fail-closed until the whole
        config is valid again."""
        try:
            cfg = self.store.load()
        except ControlConfigCorrupt as exc:
            raise ControlConflict("Cấu hình AI đang hỏng — cần sửa trực tiếp ở kho trước khi chỉnh qua giao diện.") from exc
        except ControlStoreUnavailable as exc:
            raise ControlConflict("Không đọc được kho cấu hình AI — thử lại sau.") from exc
        try:
            validate_config(cfg)
        except (ConfigValidationError, ValueError, TypeError) as exc:
            if not repair:
                raise ControlConflict("Cấu hình AI đang không hợp lệ — chỉ xoá slot hoặc sửa hồ sơ định tuyến được "
                                      "cho tới khi hợp lệ trở lại.") from exc
        return cfg

    @staticmethod
    def _val(v: Any) -> str:
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)

    def _diff(self, actor: str, entity: str, old: Mapping[str, Any], new: Mapping[str, Any]) -> List[AuditEntry]:
        return [AuditEntry(admin_id=actor, entity=entity, field=k, old_value=self._val(old.get(k))[:500],
                           new_value=self._val(new.get(k))[:500])
                for k in sorted(set(old) | set(new)) if old.get(k) != new.get(k)]

    def _commit(self, entries: List[AuditEntry]) -> None:
        """The change is already saved: refresh caches first, then audit. If the
        audit write fails the entries go to the error log instead (they carry
        no secret by construction) — never a 503 for a change that did apply."""
        self.invalidate()
        if not entries:
            return
        try:
            self.store.add_audit(entries)
        except ControlStoreUnavailable:
            for e in entries:
                log.error("ai_control audit (store write failed): admin=%s entity=%s field=%s old=%s new=%s at=%s",
                          e.admin_id, e.entity, e.field, e.old_value, e.new_value, e.at)

    @_serialized
    def update_controls(self, actor: str, patch: Mapping[str, Any], expected_version: Optional[int] = None) -> Dict[str, Any]:
        cfg = self._fresh()
        # The emergency OFF always wins: it must never fail on a stale version.
        emergency_off = dict(patch) == {"ai_enabled": False}
        if expected_version is not None and expected_version != cfg.controls.version and not emergency_off:
            raise ControlConflict("Cấu hình vừa được người khác đổi — tải lại rồi thử lại.")
        new = controls_with(cfg.controls, patch)
        validate_controls(new)
        for m, prof in new.mode_profiles.items():
            if prof not in cfg.profiles:
                raise ConfigValidationError([{"field": "mode_profiles", "message": f"{m}: hồ sơ không tồn tại"}])
        new = replace(new, version=cfg.controls.version + 1, updated_by=actor, updated_at=now_iso())
        self.store.save_controls(new)
        old_d, new_d = controls_to_dict(cfg.controls), controls_to_dict(new)
        for k in ("version", "updated_by", "updated_at"):
            old_d.pop(k), new_d.pop(k)
        self._commit(self._diff(actor, "global", old_d, new_d))
        return controls_to_dict(new)

    @_serialized
    def set_provider_type(self, actor: str, provider_type: str, enabled: bool,
                          expected_version: Optional[int] = None) -> None:
        if provider_type not in PROVIDER_TYPES:
            raise ConfigValidationError([{"field": "provider_type", "message": "loại provider không hỗ trợ"}])
        if not isinstance(enabled, bool):
            raise ConfigValidationError([{"field": "enabled", "message": "phải là true/false"}])
        cfg = self._fresh()
        # Turning a type OFF is always allowed; turning one ON needs a current view.
        if expected_version is not None and expected_version != cfg.controls.version and enabled:
            raise ControlConflict("Cấu hình vừa được người khác đổi — tải lại rồi thử lại.")
        types = dict(cfg.controls.provider_types)
        old = types.get(provider_type, False)
        types[provider_type] = enabled
        new = replace(cfg.controls, provider_types=types, version=cfg.controls.version + 1,
                      updated_by=actor, updated_at=now_iso())
        self.store.save_controls(new)
        self._commit(self._diff(actor, f"provider_type:{provider_type}", {"enabled": old}, {"enabled": enabled}))

    @_serialized
    def create_slot(self, actor: str, body: Mapping[str, Any]) -> Dict[str, Any]:
        cfg = self._fresh()
        slot = slot_from_dict(body)
        validate_slot(slot)
        if slot.slot_id in cfg.slots:
            raise ControlConflict(f"Slot '{slot.slot_id}' đã tồn tại.")
        # More than MAX_SLOTS makes the whole config invalid on the next load
        # (AI fail-closed), so refuse the slot that would cross the line.
        if len(cfg.slots) >= MAX_SLOTS:
            raise ConfigValidationError([{"field": "slots", "message": f"tối đa {MAX_SLOTS} slot — xoá bớt slot không dùng"}])
        self.store.save_slot(slot)
        self._commit(self._diff(actor, f"slot:{slot.slot_id}", {}, slot_to_dict(slot)))
        return slot_to_dict(slot)

    @_serialized
    def update_slot(self, actor: str, slot_id: str, body: Mapping[str, Any]) -> Dict[str, Any]:
        cfg = self._fresh()
        old = cfg.slots.get(slot_id)
        if old is None:
            raise KeyError(slot_id)
        merged = {**slot_to_dict(old), **{k: v for k, v in body.items() if k != "slot_id"}, "slot_id": slot_id}
        if merged.get("provider_type") != old.provider_type:
            raise ConfigValidationError([{"field": "provider_type", "message": "không đổi được loại của slot đã tạo"}])
        slot = slot_from_dict(merged)
        validate_slot(slot)
        self.store.save_slot(slot)
        self._commit(self._diff(actor, f"slot:{slot_id}", slot_to_dict(old), slot_to_dict(slot)))
        return slot_to_dict(slot)

    @_serialized
    def delete_slot(self, actor: str, slot_id: str) -> None:
        cfg = self._fresh(repair=True)
        old = cfg.slots.get(slot_id)
        if old is None:
            raise KeyError(slot_id)
        using = [p.name for p in cfg.profiles.values() if slot_id in p.steps]
        if using:
            raise ControlConflict("Slot đang được dùng trong hồ sơ: " + ", ".join(sorted(using)))
        self.store.delete_slot(slot_id)
        self._commit(self._diff(actor, f"slot:{slot_id}", slot_to_dict(old), {}))

    @_serialized
    def update_profile(self, actor: str, name: str, steps: List[str], enabled: bool) -> Dict[str, Any]:
        cfg = self._fresh(repair=True)
        if not isinstance(steps, list) or any(not isinstance(s, str) for s in steps) or not isinstance(enabled, bool):
            raise ConfigValidationError([{"field": "steps", "message": "danh sách bước không hợp lệ"}])
        p = RoutingProfile(name=name, steps=tuple(steps), enabled=enabled)
        validate_profile(p, cfg.slots)
        old = cfg.profiles.get(name)
        self.store.save_profile(p)
        self._commit(self._diff(actor, f"profile:{name}",
                                {"steps": list(old.steps), "enabled": old.enabled} if old else {},
                                {"steps": list(p.steps), "enabled": p.enabled}))
        return {"name": p.name, "steps": list(p.steps), "enabled": p.enabled}

    @_serialized
    def reset_cooldown(self, actor: str, slot_id: str) -> None:
        cfg = self._fresh(repair=True)
        if slot_id not in cfg.slots:
            raise KeyError(slot_id)
        before = self.breaker.snapshot().get(slot_id, {}).get("open_for_s", 0.0)
        self.breaker.record_success(slot_id)
        self._commit([AuditEntry(admin_id=actor, entity=f"slot:{slot_id}", field="cooldown",
                                 old_value=f"{round(before, 1)}s", new_value="0s (reset)")])

    def probe(self, actor: str, slot_id: str) -> Dict[str, Any]:
        """Owner health check: ONE real minimal request through this slot's own key, endpoint
        and model — works while the slot is disabled and the global switch is off, so a new
        project can be verified before it ever serves a user.

        Not `_serialized` (it waits on the network); rate-limited per slot instead. The call
        is real, so it is accounted like any turn: success -> slot usage + breaker success;
        failure -> sanitized last_error, breaker failure / 429 cooldown, slot error counter.
        The provider's text is never returned — only ok, latency and the sanitized enums.
        Audited as `slot:<id>.probe`."""
        cfg = self._fresh(repair=True)
        slot = cfg.slots.get(slot_id)
        if slot is None:
            raise KeyError(slot_id)
        now = self._clock()
        with self._lock:
            if now - self._probe_at.get(slot_id, -1e9) < PROBE_MIN_INTERVAL_S:
                raise ControlConflict(f"Vừa kiểm slot {slot_id} — đợi {int(PROBE_MIN_INTERVAL_S)} giây rồi thử lại.")
            self._probe_at[slot_id] = now
        out: Dict[str, Any] = {"slot_id": slot_id, "model": slot.model, "ok": False, "latency_ms": None,
                               "code": None, "category": None}
        key = self.secret_for(slot)
        if not key:
            out["code"] = "missing_secret"
        else:
            req = GenerateRequest(messages=[ChatTurn(role="user", content="Reply with the single word: OK")],
                                  model=slot.model, max_output_tokens=PROBE_MAX_OUTPUT_TOKENS, user_ref="admin_probe",
                                  timeout_s=30.0)
            t0 = time.monotonic()
            try:
                res = self.provider_for(slot, key).generate(req)
                out.update(ok=True, latency_ms=int((time.monotonic() - t0) * 1000))
                self.breaker.record_success(slot_id)
                self.record_turn(slot_id, res.input_tokens, res.output_tokens, "complete")
            except ProviderError as exc:
                cat = getattr(exc, "category", None)
                out["latency_ms"] = int((time.monotonic() - t0) * 1000)
                if exc.code == "provider_http_429" or exc.retry_after_s is not None:
                    self.breaker.cool_down(slot_id, exc.retry_after_s if exc.retry_after_s is not None
                                           else DEFAULT_429_COOLDOWN_S)
                    self.note_rate_limited(slot, exc.code, cat)
                else:
                    self.breaker.record_failure(slot_id)
                    self.note_error(slot, exc.code, cat)
                e = self.last_error(slot_id) or {}
                out.update(code=e.get("code"), category=e.get("category"))
            except Exception:  # noqa: BLE001 — same R1 backstop as the router
                log.warning("ai_control: probe of slot %s raised an unexpected error", slot_id, exc_info=True)
                self.breaker.record_failure(slot_id)
                self.note_error(slot, "provider_unexpected_error")
                out.update(code="provider_unexpected_error")
        result = (f"ok {out['latency_ms']}ms" if out["ok"]
                  else f"{out['code']}" + (f"/{out['category']}" if out["category"] else ""))
        self._commit([AuditEntry(admin_id=actor, entity=f"slot:{slot_id}", field="probe",
                                 old_value=slot.model[:120], new_value=result[:200])])
        cur = self.snapshot()
        out["health"] = self.slot_health(cur.slots.get(slot_id, slot), cur, self.usage_today())
        return out
