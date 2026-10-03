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

import contextlib
import functools
import json
import logging
import random
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Deque, Dict, List, Mapping, Optional, Tuple

from server.ai_assistant.control.capability import (
    EXPIRING_SOON_DAYS, free_quota_block_reason, free_quota_state, order_by_expiring_free_quota, serves_tier, tier_map,
)
from server.ai_assistant.control.model import (
    CAPABILITY_TIERS, CHAT_TIERS, CREATED_DISABLED_TYPES, DEFAULT_ENDPOINTS, ENDPOINT_HOSTS, EXT_PROVIDER_TYPES,
    GATED_PROVIDER_TYPES, MAX_EXT_SLOTS, MAX_SLOTS, MODES, PROFILES, PROVIDER_LABELS, PROVIDER_TYPES, ROLLOUT_PRESETS, WORKLOADS,
    ConfigValidationError, ControlConfig, ExtStatus, GlobalControls, ProviderSlot, RoutingProfile, compose_profile,
    controls_to_dict, controls_with, preset_matching, normalize_timestamp, sanitize_core, slot_from_dict, slot_meta,
    slot_to_dict, split_steps, validate_config, validate_controls, validate_profile, validate_slot,
)
from server.ai_assistant.control.providers import ProviderFactory
from server.ai_assistant.control.router import (
    SKIP_COOLDOWN, SKIP_FREE_QUOTA_EXHAUSTED, SKIP_FREE_QUOTA_EXPIRED, SKIP_FREE_QUOTA_STALE, SKIP_GATE_CLOSED,
    SKIP_META_CORRUPT, SKIP_MISSING_SECRET, SKIP_QUOTA_EXHAUSTED, SKIP_REQUEST_CAP, SKIP_RPM, SKIP_SLOT_DISABLED, SKIP_TIER,
    SKIP_TOKEN_CAP, SKIP_TPM, SKIP_TYPE_DISABLED, SKIP_WORKLOAD, plan as _plan,
)
from server.ai_assistant.control.secrets import SecretResolver
from server.ai_assistant.control.store import (
    AuditEntry, ControlConfigCorrupt, ControlStore, ControlStoreUnavailable, ExtPartition, UsageCounters, now_iso,
)
from server.ai_assistant.gateway import DEFAULT_429_COOLDOWN_S
from server.ai_assistant.scopes import SCOPE_GLOBAL, SCOPE_QA, SCOPE_USER
from server.llm_gateway.chat_provider import ChatProvider, ChatTurn, Delta, GenerateRequest, ProviderError, UsageEvent
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
#: Probe budget, SEPARATE from user traffic: at most this many probes per slot per UTC day.
PROBE_DAILY_CAP_PER_SLOT = 30
#: Safe re-probe path: health keeps the last PROBE_HISTORY probes; a slot is "probe_stable"
#: once its last PROBE_STABLE_RUN probes all succeeded within PROBE_STABLE_MAX_MS each.
PROBE_HISTORY = 5
PROBE_STABLE_RUN = 3
PROBE_STABLE_MAX_MS = 5000
#: Latency accounting (`ControlPlane.note_latency`): the last LATENCY_WINDOW calls per slot, in-process (a restart clears it,
#: like the breaker) — no Appwrite attribute is needed.
LATENCY_WINDOW = 200
#: A closed ledger day whose background read failed is not retried sooner than this (seconds).
PREFETCH_RETRY_S = 30.0


def _spawn_daemon(job: Callable[[], None]) -> None:
    threading.Thread(target=job, name="ai-quota-prefetch", daemon=True).start()


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
    #: Chỉ có ở `ai_budget_exhausted`: "user" | "global" | "qa" (xem `limits.SCOPE_*`). Để giao diện nói đúng
    #: ai hết gì, mà không phải lộ một con số công suất nào.
    scope: str = ""


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
                 user_usage_fn: Optional[Callable[[str, str], Tuple[int, int]]] = None,
                 alibaba_enabled: bool = False, prefer_free_quota: bool = False,
                 wall_now: Optional[Callable[[], datetime]] = None,
                 background: Optional[Callable[[Callable[[], None]], None]] = None,
                 qwen_legacy_enabled: bool = False) -> None:
        self.store = store
        #: Runs a no-argument job OFF the request path (cache warm-up for the free-quota lock). Tests inject an inline runner.
        self._background = background or _spawn_daemon
        #: Cổng cấp MÁY CHỦ của các loại provider trong `GATED_PROVIDER_TYPES` (biến môi trường, mặc định ĐÓNG): đóng thì
        #: không slot nào của loại đó được chọn, dựng provider, hay Kiểm tra — bất kể cấu hình trong `/admin/ai`. Mỗi loại
        #: một cổng RIÊNG: `alibaba_enabled` (Model Studio) KHÔNG mở `qwen`, và `qwen_legacy_enabled` KHÔNG mở `alibaba`.
        self._gates: Dict[str, bool] = {"alibaba": bool(alibaba_enabled), "qwen": bool(qwen_legacy_enabled)}
        #: "Ưu tiên hạn mức miễn phí sắp hết hạn" (`FAS_AI_PREFER_FREE_QUOTA`): đã cài sẵn nhưng NGỦ ĐÔNG, mặc định TẮT.
        self._prefer_free_quota = bool(prefer_free_quota)
        self._wall_now = wall_now or (lambda: datetime.now(timezone.utc))
        self.secrets = secrets or SecretResolver()
        self.factory = factory or ProviderFactory()
        self.breaker = breaker or CircuitBreaker(clock_fn=clock)
        self._clock = clock
        self._rng = rng or random.Random()
        self._active_users_fn = active_users_fn
        self._user_usage_fn = user_usage_fn
        #: day -> {"requests", "tokens", ...} của lần QA Owner (chỉ để HIỂN THỊ ở /admin/ai; không phải rào chặn).
        self._qa_overview_fn: Optional[Callable[[str], Dict[str, Any]]] = None
        #: () -> {"audience", "rpm_per_user", "streams_active", "streams_max"}: thông tin của RUNTIME (không có ID, khoá,
        #: danh sách người dùng) để Owner thấy ai đang được dùng AI và hàng đợi luồng ngay trên /admin/ai.
        self._runtime_info_fn: Optional[Callable[[], Dict[str, Any]]] = None
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
        #: Probe accounting, SEPARATE from the usage ledger (in-process; durable trail = audit).
        #: _probe_counts: slot_id -> [probes today, ok today, tokens today]; resets at UTC midnight.
        self._probe_day = ""
        self._probe_counts: Dict[str, List[int]] = {}
        #: slot_id -> last PROBE_HISTORY probes: (at_iso, ok, latency_ms, code).
        self._probe_log: Dict[str, Deque[Tuple[str, bool, Optional[int], Optional[str]]]] = {}
        #: slot_id -> last LATENCY_WINDOW calls: (at_iso, ttft_ms | None, total_ms | None, ok, from_probe). In-process.
        self._latency: Dict[str, Deque[Tuple[str, Optional[int], Optional[int], bool, bool]]] = {}
        #: slot_id -> UTC day (yyyymmdd) on which the PROVIDER said its quota is gone: the slot rests until 00:00 UTC
        #: (or until the owner resets it). In-process like the breaker.
        self._quota_out: Dict[str, str] = {}
        #: yyyymmdd (a COMPLETED UTC day) -> {slot_id: tokens served that day}, read once from the ledger and kept: a closed
        #: day never changes. Only `free_quota_only` slots (and the admin quota view) ever ask for it.
        self._past_usage: Dict[str, Dict[str, int]] = {}
        self._prefetching: set = set()  # closed days a background fill is already reading
        self._prefetch_failed: Dict[str, float] = {}  # day -> monotonic time of the last failed read

    def attach_usage_sources(self, *, active_users_fn: Optional[Callable[[str], Optional[int]]] = None,
                             user_usage_fn: Optional[Callable[[str, str], Tuple[int, int]]] = None,
                             qa_overview_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
                             runtime_info_fn: Optional[Callable[[], Dict[str, Any]]] = None) -> None:
        """Wired by `build_ai_runtime` once the AI repo exists (the plane itself
        is built earlier so `/admin/ai` works even while the assistant is off)."""
        if active_users_fn is not None:
            self._active_users_fn = active_users_fn
        if user_usage_fn is not None:
            self._user_usage_fn = user_usage_fn
        if qa_overview_fn is not None:
            self._qa_overview_fn = qa_overview_fn
        if runtime_info_fn is not None:
            self._runtime_info_fn = runtime_info_fn

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
            cfg = self._load_composed(validate=True)
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

    def _load_composed(self, *, validate: bool) -> ControlConfig:
        """The stored config as the routing/admin code sees it: the LEGACY collections (strictly validated, exactly as before
        Alibaba existed — `validate=True`; a bad row there still fails closed) plus the isolated Alibaba partition layered on
        top. The partition can only ADD slots/routes; whatever is wrong with it is a status, never a reason the legacy
        configuration is rejected."""
        core = sanitize_core(self.store.load())
        if validate:
            validate_config(core)
        return self._compose(core, self._load_ext())

    def _load_ext(self) -> ExtPartition:
        try:
            return self.store.load_ext()
        except ControlStoreUnavailable:
            return ExtPartition(state="unavailable")
        except Exception:  # noqa: BLE001 — nothing about the Alibaba partition may take Gemini's configuration down with it
            log.error("ai_control: isolated partition unreadable — Alibaba slots are off, the rest is unaffected")
            return ExtPartition(state="unavailable")

    @staticmethod
    def _compose(core: ControlConfig, ext: ExtPartition) -> ControlConfig:
        slots = dict(core.slots)
        unreadable = core.ext.unreadable + ext.unreadable
        for sid, s in ext.slots.items():
            if sid in slots:  # same id in both collections: the legacy slot wins, the Alibaba row is ignored
                unreadable += 1
                continue
            slots[sid] = s
        profiles = dict(core.profiles)
        stale: List[str] = []
        for name, route in ext.routes.items():
            base = profiles.get(name)
            effective, applied = compose_profile(base, route, slots) if base is not None else (None, False)
            if applied and effective is not None:
                profiles[name] = effective
            else:  # no longer matches the legacy-visible profile (or invalid): dropped, so it can never override a Gemini edit
                stale.append(name)
        return ControlConfig(core.controls, slots, profiles, ExtStatus(ext.state, unreadable, tuple(sorted(stale))))

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

    def _past_day_tokens(self, day: str, block: bool = True) -> Optional[Dict[str, int]]:
        """{slot_id: tokens} of a COMPLETED UTC day from the cache; with `block=True` a miss is read from the ledger (admin
        views, the background prefetch). None = not cached / cannot be read right now."""
        with self._lock:
            hit = self._past_usage.get(day)
        if hit is not None or not block:
            return hit
        try:
            rows = self.store.usage_for_day(day)
        except ControlStoreUnavailable:
            return None
        tokens = {sid: u.tokens for sid, u in rows.items()}
        with self._lock:
            self._past_usage[day] = tokens
            for old in sorted(self._past_usage)[:-70]:  # bounded: ~2 snapshot windows
                self._past_usage.pop(old, None)
        return tokens

    def _prefetch(self, days: List[str]) -> None:
        """Warm the closed-day cache OFF the request path. A failed day is not retried for PREFETCH_RETRY_S, so an unreachable
        store cannot make every request spawn a thread."""
        now = self._clock()
        with self._lock:
            todo = [d for d in days if d not in self._prefetching and now - self._prefetch_failed.get(d, -1e9) >= PREFETCH_RETRY_S]
            self._prefetching.update(todo)
        if not todo:
            return

        def fill() -> None:
            try:
                for d in todo:
                    if self._past_day_tokens(d, block=True) is None:
                        with self._lock:
                            self._prefetch_failed[d] = self._clock()
            finally:
                with self._lock:
                    self._prefetching.difference_update(todo)

        self._background(fill)

    def _consumed_since_snapshot(self, slot: ProviderSlot, usage: Dict[str, UsageCounters], block: bool = True) -> Optional[int]:
        """Tokens `slot` served since the UTC day of its server-stamped free-quota snapshot (that whole day counted — the
        conservative side). `usage` = today's live counters. None = cannot be established: no stamp, a ledger day unreadable,
        or an implausibly long window.

        `block=False` is the ROUTING path: it only ever reads the cache. A closed day that is not cached yet makes the answer
        None (the slot is skipped, fail closed) and is filled in the background — a month-old snapshot must never put dozens of
        sequential ledger reads into a user's request."""
        norm = normalize_timestamp(slot.free_quota_updated_at) if slot.free_quota_updated_at else None
        if norm is None:  # validated on write and on load, but a routing path must never raise on a bad stamp
            return None
        stamped = datetime.fromisoformat(norm)
        today = self._wall_now().astimezone(timezone.utc).date()
        first = min(stamped.astimezone(timezone.utc).date(), today)
        for attempt in (1, 2):
            total = usage.get(slot.slot_id, UsageCounters()).tokens
            missing: List[str] = []
            day, steps = first, 0
            while day < today:
                key = day.strftime("%Y%m%d")
                part = self._past_day_tokens(key, block=block)
                if part is None:
                    if block:
                        return None
                    missing.append(key)
                else:
                    total += part.get(slot.slot_id, 0)
                day += timedelta(days=1)
                steps += 1
                if steps > 400:
                    return None
            if not missing:
                return total
            if attempt == 2:
                return None
            self._prefetch(missing)  # an inline executor (tests) has filled the cache by now; a thread has not
        return None

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
    def gate_open(self, provider_type: str) -> bool:
        """Loại không có cổng máy chủ -> luôn mở; loại có cổng (`GATED_PROVIDER_TYPES`) chỉ mở khi biến môi trường bật."""
        return provider_type not in GATED_PROVIDER_TYPES or self._gates.get(provider_type, False)

    def skip_reason(self, slot: ProviderSlot, workload: str, est_tokens: int,
                    cfg: Optional[ControlConfig] = None, usage: Optional[Dict[str, UsageCounters]] = None,
                    tier: Optional[str] = None) -> Optional[str]:
        cfg = cfg or self.snapshot()
        if not slot.enabled:
            return SKIP_SLOT_DISABLED
        if not cfg.controls.provider_types.get(slot.provider_type, False):
            return SKIP_TYPE_DISABLED
        if not self.gate_open(slot.provider_type):
            return SKIP_GATE_CLOSED
        if slot.meta_corrupt:
            return SKIP_META_CORRUPT
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
        if not serves_tier(slot, tier):
            return SKIP_TIER
        with self._lock:
            quota_out = self._quota_out.get(slot.slot_id) == today_utc()
        if quota_out:
            return SKIP_QUOTA_EXHAUSTED
        if slot.free_quota_only:  # chỉ khoá an toàn mới cần đọc lượng đã dùng từ sổ; slot thường không tốn thêm gì
            consumed = self._consumed_since_snapshot(slot, usage if usage is not None else self.usage_today(), block=False)
            blocked = free_quota_block_reason(slot, self._wall_now(), est_tokens, consumed)
            if blocked == "expired":
                return SKIP_FREE_QUOTA_EXPIRED
            if blocked in ("stale", "unverifiable"):
                return SKIP_FREE_QUOTA_STALE
            if blocked == "exhausted":
                return SKIP_FREE_QUOTA_EXHAUSTED
        return None

    def balance_factor(self, slot: ProviderSlot, usage: Optional[Dict[str, UsageCounters]] = None) -> float:
        """How much of this slot is left, in [0, 1] — the multiplier on its routing weight
        (`router.weighted_order` floors it at MIN_BALANCE_FACTOR, so 0 never starves a slot).

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

    def plan(self, cfg: ControlConfig, *, mode: str, workload: str, est_tokens: int = 0, tier: Optional[str] = None):
        if tier is not None and tier not in CHAT_TIERS:
            return []  # tầng không phục vụ được bằng đường chat (vd. EMBEDDING) -> không slot nào
        usage = self.usage_today()
        order = (lambda group: order_by_expiring_free_quota(group, self._wall_now())) if self._prefer_free_quota else None
        return _plan(cfg, mode=mode, workload=workload, rng=self._rng, est_tokens=est_tokens,
                     skip_reason=lambda s, w, e: self.skip_reason(s, w, e, cfg=cfg, usage=usage, tier=tier),
                     balance=lambda s: self.balance_factor(s, usage), group_order=order)

    def secret_for(self, slot: ProviderSlot) -> Optional[str]:
        return self.secrets.resolve(slot.secret_ref)

    def provider_for(self, slot: ProviderSlot, key: str) -> ChatProvider:
        # Lớp phòng thủ cuối cùng: dù có đường nào lọt qua `skip_reason`, loại có cổng đóng KHÔNG BAO GIỜ dựng được provider
        # (nên không có request nào ra ngoài).
        if not self.gate_open(slot.provider_type):
            raise ProviderError("Loại provider này chưa được bật ở máy chủ.", transient=False,
                                code="provider_gate_closed", category="PERMISSION_DENIED")
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

    def _mark_quota_out(self, slot: ProviderSlot, code: Optional[str], category: Optional[str]) -> None:
        """The PROVIDER reported its quota gone: the slot rests until 00:00 UTC (state + sanitized last error only)."""
        with self._lock:
            self._quota_out[slot.slot_id] = today_utc()
        self.note_failure(slot, code, category)

    def note_quota_exhausted(self, slot: ProviderSlot, code: Optional[str] = "provider_http_429",
                             category: Optional[str] = "QUOTA_EXHAUSTED") -> None:
        """Live traffic hit a provider-side quota wall: not a health failure (no breaker counting, no 30 s retry) —
        park the slot and count the failed request in the ledger."""
        self._mark_quota_out(slot, code, category)
        self._bump_local(slot.slot_id, errors=1)
        self._safe_usage(slot.slot_id, errors=1)

    def note_latency(self, slot: ProviderSlot, *, ttft_ms: Optional[int], total_ms: Optional[int], ok: bool,
                     probe: bool = False) -> None:
        """One provider call's time-to-first-token and total duration (measured at the gateway, same for every provider)."""
        with self._lock:
            self._latency.setdefault(slot.slot_id, deque(maxlen=LATENCY_WINDOW)).append(
                (now_iso(), ttft_ms, total_ms, bool(ok), bool(probe)))

    def latency_view(self, slot_id: str) -> Dict[str, Any]:
        with self._lock:
            samples = list(self._latency.get(slot_id, ()))

        def stat(values: List[int]) -> Dict[str, Optional[int]]:
            if not values:
                return {"p50": None, "p95": None, "last": None}
            ordered = sorted(values)
            rank = lambda p: ordered[max(0, min(len(ordered) - 1, -(-len(ordered) * p // 100) - 1))]  # noqa: E731 nearest-rank
            return {"p50": rank(50), "p95": rank(95), "last": values[-1]}

        return {"window": LATENCY_WINDOW, "samples": len(samples), "ok": sum(1 for s in samples if s[3]),
                "probe_samples": sum(1 for s in samples if s[4]),
                "ttft_ms": stat([s[1] for s in samples if s[1] is not None]),
                "total_ms": stat([s[2] for s in samples if s[2] is not None]),
                "note": "trong tiến trình, mất khi deploy"}

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

    def user_caps(self) -> Tuple[int, int]:
        """(trần lượt/ngày, trần token/ngày) MỖI NGƯỜI hiện hành; 0 = không đặt trần. Chỉ để tính hạn mức
        riêng của người dùng — không có số liệu toàn cục nào ở đây."""
        c = self.snapshot().controls
        return c.per_user_daily_request_cap, c.per_user_daily_token_cap

    def admission(self, user_id: str, *, qa_ledger_user: str = "", qa_daily_cap: int = 0) -> Optional[AdmissionError]:
        """Cổng trước mỗi lượt gửi. Công tắc khẩn cấp và trần TOÀN CỤC áp cho MỌI lượt, kể cả lần QA của Owner
        (lần QA không thể vượt trần an toàn toàn cục). Khác nhau duy nhất: trần THEO NGƯỜI. Lượt thường bị
        chặn bởi trần riêng của người đó (scope "user"); lượt QA (`qa_ledger_user` != "") bị chặn bởi hạn mức
        QA riêng `qa_daily_cap` trên sổ QA (scope "qa") và KHÔNG chạm tới sổ của người dùng thường."""
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
            return AdmissionError(429, "ai_budget_exhausted", "Trợ lý AI đã dùng hết hạn mức hôm nay.",
                                  _reset_at_iso(), SCOPE_GLOBAL)
        if qa_ledger_user:
            # Lối QA là lối đặc quyền: không đọc được sổ thì ĐÓNG (khác lối thường, nơi thiếu nguồn đếm = bỏ qua).
            if self._user_usage_fn is None:
                return AdmissionError(503, "ai_storage_unavailable", "Chưa đọc được hạn mức AI — thử lại sau ít phút.")
            try:
                qreq, _ = self._user_usage_fn(qa_ledger_user, today_utc())
            except Exception:  # noqa: BLE001 — unknown usage never means "under the cap"
                log.warning("ai_control: QA usage unavailable — refusing the turn")
                return AdmissionError(503, "ai_storage_unavailable", "Chưa đọc được hạn mức AI — thử lại sau ít phút.")
            if qreq >= qa_daily_cap:  # cap 0 => đóng hẳn
                return AdmissionError(429, "ai_budget_exhausted", "Đã dùng hết lượt QA hôm nay.",
                                      _reset_at_iso(), SCOPE_QA)
            return None
        if self._user_usage_fn is not None:
            try:
                ureq, utok = self._user_usage_fn(user_id, today_utc())
            except Exception:  # noqa: BLE001 — unknown usage never means "under the cap"
                log.warning("ai_control: per-user usage unavailable — refusing the turn")
                return AdmissionError(503, "ai_storage_unavailable", "Chưa đọc được hạn mức AI — thử lại sau ít phút.")
            if (c.per_user_daily_request_cap and ureq >= c.per_user_daily_request_cap) or \
                    (c.per_user_daily_token_cap and utok >= c.per_user_daily_token_cap):
                return AdmissionError(429, "ai_budget_exhausted", "Bạn đã dùng hết lượt hỏi hôm nay.",
                                      _reset_at_iso(), SCOPE_USER)
        return None

    # ------------------------------------------------------------ admin views
    def slot_health(self, slot: ProviderSlot, cfg: ControlConfig, usage: Dict[str, UsageCounters]) -> Dict[str, Any]:
        snap = self.breaker.snapshot().get(slot.slot_id, {"consecutive_failures": 0, "open_for_s": 0.0})
        sec = self.secrets.status(slot.secret_ref)
        u = usage.get(slot.slot_id, UsageCounters())
        with self._lock:
            quota_out = self._quota_out.get(slot.slot_id) == today_utc()
        if not slot.enabled or not cfg.controls.provider_types.get(slot.provider_type, False):
            status = "DISABLED"
        elif not self.gate_open(slot.provider_type):
            status = "GATE_CLOSED"
        elif slot.meta_corrupt:
            status = "META_CORRUPT"
        elif not sec.present:
            status = "MISSING_SECRET"
        elif quota_out:
            status = "QUOTA_EXHAUSTED"
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
                # Siêu dữ liệu hạn mức miễn phí (ảnh chụp do Owner nhập) + cờ "nhà cung cấp báo hết hạn mức hôm nay".
                "quota": self._quota_view(slot, usage, quota_out),
                "latency": self.latency_view(slot.slot_id),
                "gate": ({"env": GATED_PROVIDER_TYPES[slot.provider_type], "open": self.gate_open(slot.provider_type)}
                         if slot.provider_type in GATED_PROVIDER_TYPES else None),
                "meta_corrupt": slot.meta_corrupt,
                **self.probe_view(slot.slot_id),
                **self._last_error_fields(slot.slot_id)}

    def _quota_view(self, slot: ProviderSlot, usage: Dict[str, UsageCounters], provider_exhausted_today: bool) -> Dict[str, Any]:
        """The admin's free-quota block: snapshot, estimated balance, and — for a `free_quota_only` slot — WHY the lock is
        blocking it right now (`lock_block`: expired | stale | unverifiable | exhausted | None)."""
        now = self._wall_now()
        consumed = self._consumed_for_view(slot, usage)
        return {**free_quota_state(slot, now, consumed), "lock_block": free_quota_block_reason(slot, now, 0, consumed),
                "provider_exhausted_today": provider_exhausted_today}

    def _consumed_for_view(self, slot: ProviderSlot, usage: Dict[str, UsageCounters]) -> Optional[int]:
        """Consumption since the snapshot for the admin view — only where a balance exists; never raises (a view must render)."""
        if slot.free_quota_remaining is None:
            return None
        try:
            return self._consumed_since_snapshot(slot, usage)
        except (ValueError, ControlStoreUnavailable):
            return None

    def _last_error_fields(self, slot_id: str) -> Dict[str, Optional[str]]:
        e = self.last_error(slot_id) or {}
        return {"last_error_code": e.get("code"), "last_error_category": e.get("category"),
                "last_error_at": e.get("at")}

    @staticmethod
    def _ext_view(cfg: ControlConfig) -> Dict[str, Any]:
        """`notices` = những câu Owner cần đọc (rỗng khi bình thường). Luôn nói rõ Gemini KHÔNG bị ảnh hưởng."""
        e = cfg.ext
        notes: List[str] = []
        if e.state == "schema_missing":
            notes.append("Chưa chạy migration collection ai_alibaba_config (xem docs/ai/ALIBABA_PROVIDER.md) — chưa tạo được "
                         "slot Alibaba. Gemini không bị ảnh hưởng.")
        elif e.state == "unavailable":
            notes.append("Không đọc được kho Alibaba lúc này — slot Alibaba tạm không dùng được. Gemini không bị ảnh hưởng.")
        if e.unreadable:
            notes.append(f"{e.unreadable} dòng trong kho Alibaba/cấu hình không đọc được (đã bỏ qua, không bao giờ được dùng). "
                         "Gemini không bị ảnh hưởng.")
        if e.stale_routes:
            notes.append("Hồ sơ " + ", ".join(e.stale_routes) + " có bước Alibaba bị bỏ vì hồ sơ đã được sửa ở nơi khác "
                         "(vd. sau khi rút mã về bản cũ). Đặt lại bước Alibaba nếu vẫn cần.")
        return {"state": e.state, "unreadable": e.unreadable, "stale_routes": list(e.stale_routes), "notices": notes,
                "title": "Kho Alibaba (vùng lưu riêng)"}

    def config_view(self) -> Dict[str, Any]:
        cfg = self.snapshot()
        usage = self.usage_today()
        slots = []
        for s in sorted(cfg.slots.values(), key=lambda x: (x.provider_type, x.priority, x.slot_id)):
            slots.append({**slot_to_dict(s), "effective_endpoint": s.effective_endpoint(),
                          "health": self.slot_health(s, cfg, usage)})
        return {
            "state": self.state,
            #: Vùng lưu trữ tách biệt của Alibaba (state | unreadable | stale_routes | notices): lỗi ở đây KHÔNG bao giờ làm
            #: `state` đổi. Tên trường trung tính + câu chữ do MÁY CHỦ cấp: JS công khai không viết cứng tên provider nào.
            "isolated_store": self._ext_view(cfg),
            "controls": controls_to_dict(cfg.controls),
            "rollout": {"active_preset": preset_matching(cfg.controls),
                        "presets": {n: dict(v) for n, v in ROLLOUT_PRESETS.items()},
                        "probe_daily_cap_per_slot": PROBE_DAILY_CAP_PER_SLOT,
                        "probe_stable_rule": {"run": PROBE_STABLE_RUN, "max_latency_ms": PROBE_STABLE_MAX_MS}},
            "provider_types": [{"type": t, "label": PROVIDER_LABELS[t],
                                "enabled": bool(cfg.controls.provider_types.get(t, False)),
                                "slot_count": sum(1 for s in cfg.slots.values() if s.provider_type == t),
                                #: Cổng cấp máy chủ (biến môi trường) của loại này, hoặc None nếu loại không có cổng.
                                "gate": ({"env": GATED_PROVIDER_TYPES[t], "open": self.gate_open(t)}
                                         if t in GATED_PROVIDER_TYPES else None)}
                               for t in PROVIDER_TYPES],
            #: Tầng năng lực -> các slot khai báo phục vụ tầng đó (Owner cấu hình; gói đăng ký chỉ ánh xạ tới TẦNG).
            "capability_map": tier_map(cfg),
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
                         "alibaba": "https://<máy chủ DashScope của tài khoản>/compatible-mode/v1 — máy chủ dạng "
                                    "dashscope[-vùng].aliyuncs.com, đúng endpoint/vùng trong trang Model Studio của bạn",
                     },
                     "secret_env_prefix": "FAS_AI_SECRET_",
                     # Tầng năng lực + quy tắc an toàn của loại có cổng: giao diện vẽ từ đây, không viết cứng tên provider.
                     "capability_tiers": list(CAPABILITY_TIERS), "chat_tiers": list(CHAT_TIERS),
                     "gated_types": {t: {"env": env, "open": self.gate_open(t)} for t, env in GATED_PROVIDER_TYPES.items()},
                     "created_disabled_types": list(CREATED_DISABLED_TYPES),
                     "free_quota": {"expiring_soon_days": EXPIRING_SOON_DAYS,
                                    "prefer_expiring_active": self._prefer_free_quota}},
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
        qa: Optional[Dict[str, Any]] = None
        if self._qa_overview_fn is not None:
            try:
                qa = self._qa_overview_fn(today_utc())
            except Exception:  # noqa: BLE001 — a metric, never a failure
                qa = None
        runtime: Optional[Dict[str, Any]] = None
        if self._runtime_info_fn is not None:
            try:
                runtime = self._runtime_info_fn()
            except Exception:  # noqa: BLE001 — a metric, never a failure
                runtime = None
        return {
            "state": self.state, "day": today_utc(), "ai_enabled": c.ai_enabled,
            "isolated_store": self._ext_view(cfg),
            #: Thông tin runtime không nằm trong kho cấu hình: khán giả (`FAS_AI_AUDIENCE`), RPM/người, số luồng đang chạy.
            "runtime": runtime,
            #: Cổng cấp máy chủ của các loại provider có cổng (đóng = không có request nào tới nhà cung cấp đó) và việc
            #: "ưu tiên hạn mức miễn phí sắp hết hạn" có đang bật không (mặc định tắt).
            "gates": {t: {"env": env, "open": self.gate_open(t)} for t, env in GATED_PROVIDER_TYPES.items()},
            "free_quota_preference": self._prefer_free_quota,
            #: Lần QA của Owner đã NẰM TRONG `requests` ở trên (đi qua cùng slot, cùng trần toàn cục); đây chỉ là
            #: phần tách riêng để Owner thấy QA đã dùng bao nhiêu so với hạn mức QA.
            "qa": qa,
            "requests": tot.requests, "input_tokens": tot.input_tokens, "output_tokens": tot.output_tokens,
            "errors": tot.errors, "rate_limited": tot.rate_limited, "est_cost_micro_usd": tot.cost_micro_usd,
            "active_users": active,
            "caps": {"global_daily_request_cap": c.global_daily_request_cap,
                     "global_daily_token_cap": c.global_daily_token_cap,
                     "daily_cost_cap_micro_usd": c.daily_cost_cap_micro_usd},
            "rollout_preset": preset_matching(c),
            # Operational probes, counted APART from the user budget above (never in `requests`).
            "probes_today": self._probes_total(),
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
            core = sanitize_core(self.store.load())
        except ControlConfigCorrupt as exc:
            raise ControlConflict("Cấu hình AI đang hỏng — cần sửa trực tiếp ở kho trước khi chỉnh qua giao diện.") from exc
        except ControlStoreUnavailable as exc:
            raise ControlConflict("Không đọc được kho cấu hình AI — thử lại sau.") from exc
        try:
            validate_config(core)
        except (ConfigValidationError, ValueError, TypeError) as exc:
            if not repair:
                raise ControlConflict("Cấu hình AI đang không hợp lệ — chỉ xoá slot hoặc sửa hồ sơ định tuyến được "
                                      "cho tới khi hợp lệ trở lại.") from exc
        return self._compose(core, self._load_ext())

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
        # `free_quota_updated_at` do MÁY CHỦ đóng dấu, client không đặt được.
        slot = slot_from_dict({k: v for k, v in body.items() if k != "free_quota_updated_at"})
        validate_slot(slot)
        if slot.provider_type in CREATED_DISABLED_TYPES and slot.enabled:
            raise ConfigValidationError([{
                "field": "enabled",
                "message": "slot loại này luôn được tạo ở trạng thái TẮT — Kiểm tra slot rồi bật bằng một thao tác riêng"}])
        if slot.free_quota_remaining is not None:
            slot = replace(slot, free_quota_updated_at=now_iso())
        if slot.slot_id in PROVIDER_TYPES:
            # A step is resolved as a provider TYPE first (`router.plan`), so a slot named like a type could never be addressed by
            # id — and would blur which steps belong to which storage. (Only NEW slots: existing ids are never re-validated.)
            raise ConfigValidationError([{"field": "slot_id", "message": "không được trùng tên một loại provider (" +
                                          ", ".join(PROVIDER_TYPES) + ")"}])
        if slot.slot_id in cfg.slots:
            raise ControlConflict(f"Slot '{slot.slot_id}' đã tồn tại.")
        ext_type = slot.provider_type in EXT_PROVIDER_TYPES
        if ext_type and cfg.ext.state == "unavailable":
            # Uniqueness cannot be checked while the partition cannot be read, and a write would PATCH-overwrite an invisible slot.
            raise ControlConflict("Không đọc được kho Alibaba lúc này — chưa thể tạo slot Alibaba (không kiểm được trùng id). "
                                  "Thử lại sau.")
        # More than MAX_SLOTS makes the whole config invalid on the next load (AI fail-closed), so refuse the slot that would
        # cross the line. The Alibaba partition has its OWN cap and neither partition's slots count against the other's.
        same_store = [s for s in cfg.slots.values() if (s.provider_type in EXT_PROVIDER_TYPES) == ext_type]
        cap = MAX_EXT_SLOTS if ext_type else MAX_SLOTS
        if len(same_store) >= cap:
            raise ConfigValidationError([{"field": "slots", "message": f"tối đa {cap} slot — xoá bớt slot không dùng"}])
        self._save_slot(slot)
        self._commit(self._diff(actor, f"slot:{slot.slot_id}", {}, slot_to_dict(slot)))
        return slot_to_dict(slot)

    def _save_slot(self, slot: ProviderSlot, *, clear_meta: bool = False) -> None:
        """Loại thuộc vùng tách biệt (`EXT_PROVIDER_TYPES`) đi vào collection RIÊNG của nó, không bao giờ vào `ai_provider_slots`
        — bản cũ đọc collection đó và coi một dòng lạ là cấu hình hỏng (xem docstring `store.py`)."""
        if slot.provider_type in EXT_PROVIDER_TYPES:
            self.store.save_ext_slot(slot)
        else:
            self.store.save_slot(slot, clear_meta=clear_meta)

    @_serialized
    def update_slot(self, actor: str, slot_id: str, body: Mapping[str, Any]) -> Dict[str, Any]:
        cfg = self._fresh()
        old = cfg.slots.get(slot_id)
        if old is None:
            raise KeyError(slot_id)
        merged = {**slot_to_dict(old),
                  **{k: v for k, v in body.items() if k not in ("slot_id", "free_quota_updated_at")}, "slot_id": slot_id}
        if merged.get("provider_type") != old.provider_type:
            raise ConfigValidationError([{"field": "provider_type", "message": "không đổi được loại của slot đã tạo"}])
        slot = slot_from_dict(merged)
        validate_slot(slot)
        if slot.free_quota_remaining != old.free_quota_remaining:  # số dư đổi -> đóng dấu ảnh chụp mới (hoặc xoá dấu)
            slot = replace(slot, free_quota_updated_at=now_iso() if slot.free_quota_remaining is not None else "")
        # Xoá `meta_json` đã lưu (khi siêu dữ liệu mới rỗng, hoặc dòng cũ bị hỏng) phải ghi tường minh; thường thì KHÔNG gửi gì.
        # (Slot ở vùng tách biệt mang toàn bộ trường trong một payload nên không có khái niệm này.)
        self._save_slot(slot, clear_meta=bool((slot_meta(old) or old.meta_corrupt) and not slot_meta(slot)))
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
        if old.provider_type in EXT_PROVIDER_TYPES:
            self.store.delete_ext_slot(slot_id)
        else:
            self.store.delete_slot(slot_id)
        self._commit(self._diff(actor, f"slot:{slot_id}", slot_to_dict(old), {}))

    @staticmethod
    def _next_stamp(previous: str) -> str:
        """Dấu của một lần ghi hồ sơ = `updated_at` của dòng hồ sơ cũ, tới giây, và LUÔN lớn hơn dấu trước (hai lần sửa trong cùng một
        giây vẫn ra hai dấu khác nhau)."""
        now = now_iso()
        prev = normalize_timestamp(previous) if previous else None
        if prev is not None and now <= prev:  # cùng định dạng UTC `+00:00` tới giây nên so chuỗi là so thời gian
            now = (datetime.fromisoformat(prev) + timedelta(seconds=1)).isoformat(timespec="seconds")
        return now

    def _restore_route(self, name: str, old: Optional[RoutingProfile], cfg: ControlConfig) -> None:
        """Ghi hồ sơ cũ thất bại SAU khi dòng Alibaba mới đã ghi: trả dòng Alibaba về như cũ (cùng dấu cũ nên hợp lệ lại) hoặc xoá nó.
        Cố gắng hết sức — thất bại ở đây vẫn an toàn (dòng mới mang dấu chưa từng được ghi cho dòng hồ sơ cũ nên bị bỏ qua)."""
        try:
            if old is not None and split_steps(old.steps, cfg.slots)[1]:
                self.store.save_ext_route(name, old.steps, stamp=old.updated_at)
            else:
                self.store.delete_ext_route(name)
        except Exception:  # noqa: BLE001
            log.warning("ai_control: could not restore the Alibaba route of %s after a failed profile write — it is ignored", name)

    @_serialized
    def update_profile(self, actor: str, name: str, steps: List[str], enabled: bool) -> Dict[str, Any]:
        cfg = self._fresh(repair=True)
        if not isinstance(steps, list) or any(not isinstance(s, str) for s in steps) or not isinstance(enabled, bool):
            raise ConfigValidationError([{"field": "steps", "message": "danh sách bước không hợp lệ"}])
        p = RoutingProfile(name=name, steps=tuple(steps), enabled=enabled)
        if cfg.ext.state in ("unavailable", "schema_missing") \
                and any(s not in PROVIDER_TYPES and s not in cfg.slots for s in p.steps):
            # A step we cannot place may be an Alibaba slot we cannot read right now: say so instead of "not a known slot".
            raise ControlConflict("Không đọc được kho Alibaba (collection ai_alibaba_config) — chưa thể kiểm tra các bước trỏ "
                                  "tới slot Alibaba. Sửa hồ sơ chỉ gồm Gemini/loại cũ vẫn được.")
        validate_profile(p, cfg.slots)
        legacy, ext_steps = split_steps(p.steps, cfg.slots)
        if ext_steps and not legacy:
            # Alibaba is never the ONLY route of a profile: rolling it back (or the gate closing) must leave Gemini serving
            # that mode instead of an empty profile.
            raise ConfigValidationError([{
                "field": "steps",
                "message": "hồ sơ có bước Alibaba phải còn ít nhất một bước loại khác (vd. Gemini) — Alibaba không được là "
                           "đường duy nhất"}])
        old = cfg.profiles.get(name)
        # Hồ sơ lưu ở collection CŨ chỉ mang phần bản cũ đọc được (không `alibaba`, không id slot Alibaba) — nếu không bản cũ
        # coi hồ sơ là hỏng và tắt AI. Phần Alibaba ghi TRƯỚC ở vùng tách biệt: kho chưa migrate/không với tới thì lỗi sạch,
        # chưa đổi gì. Cả hai dòng mang CÙNG MỘT DẤU (`updated_at` của dòng hồ sơ cũ, luôn tăng nghiêm ngặt): dòng Alibaba chỉ
        # có hiệu lực cho đúng lần ghi này. Nên nếu ghi hồ sơ thất bại sau đó, hay xoá dòng Alibaba thất bại (kho không với
        # tới), hay bản cũ/bản mới sửa hồ sơ về sau — dòng Alibaba cũ mất dấu và mồ côi vĩnh viễn, kể cả khi các bước tình cờ
        # trùng lại. Không bao giờ có trường hợp "lệnh gỡ bước Alibaba bị lờ đi".
        stamp = self._next_stamp(old.updated_at if old else "")
        wrote_route = False
        try:
            if ext_steps:
                self.store.save_ext_route(name, p.steps, stamp=stamp)
                wrote_route = True
            elif cfg.ext.state in ("ok", "unavailable"):
                try:
                    self.store.delete_ext_route(name)
                except ControlStoreUnavailable:
                    log.warning("ai_control: Alibaba route for %s not deleted — the profile gets a new stamp, so it is ignored", name)
            self.store.save_profile(replace(p, steps=legacy), stamp=stamp)
        except Exception:
            if wrote_route:
                self._restore_route(name, old, cfg)
            raise
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
        entries = [AuditEntry(admin_id=actor, entity=f"slot:{slot_id}", field="cooldown",
                              old_value=f"{round(before, 1)}s", new_value="0s (reset)")]
        with self._lock:
            parked = self._quota_out.pop(slot_id, None)
        if parked:  # Owner đã cập nhật hạn mức bên nhà cung cấp: cho slot thử lại
            entries.append(AuditEntry(admin_id=actor, entity=f"slot:{slot_id}", field="provider_quota_exhausted",
                                      old_value=f"nghỉ tới hết ngày {parked} UTC", new_value="đã gỡ (reset)"))
        self._commit(entries)

    def _roll_probe_day(self) -> None:
        """Caller holds self._lock. Probe counters are per UTC day, like the usage ledger."""
        day = today_utc()
        if day != self._probe_day:
            self._probe_day, self._probe_counts = day, {}

    def _note_probe(self, slot_id: str, out: Mapping[str, Any]) -> None:
        """Result of a probe already counted (reserved) in `probe()`. `_probe_log` is NOT
        reset at midnight on purpose: stability is about the LAST probes, whatever the day."""
        with self._lock:
            self._roll_probe_day()
            c = self._probe_counts.setdefault(slot_id, [0, 0, 0])
            if out.get("ok"):
                c[1] += 1
                c[2] += int(out.get("tokens") or 0)
            self._probe_log.setdefault(slot_id, deque(maxlen=PROBE_HISTORY)).append(
                (now_iso(), bool(out.get("ok")), out.get("latency_ms"), out.get("code")))

    def _probes_total(self) -> Dict[str, int]:
        with self._lock:
            self._roll_probe_day()
            vals = list(self._probe_counts.values())
        return {"count": sum(v[0] for v in vals), "ok": sum(v[1] for v in vals), "tokens": sum(v[2] for v in vals)}

    def probe_view(self, slot_id: str) -> Dict[str, Any]:
        """Separate, visible probe accounting + the re-probe stability verdict for one slot."""
        with self._lock:
            self._roll_probe_day()
            n, ok, tok = self._probe_counts.get(slot_id, [0, 0, 0])
            hist = list(self._probe_log.get(slot_id, ()))
        last = hist[-PROBE_STABLE_RUN:]
        stable = (len(last) == PROBE_STABLE_RUN and all(h[1] for h in last)
                  and all((h[2] or 0) <= PROBE_STABLE_MAX_MS for h in last))
        return {"probes_today": {"count": n, "ok": ok, "tokens": tok, "cap": PROBE_DAILY_CAP_PER_SLOT},
                "probe_history": [{"at": a, "ok": o, "latency_ms": ms, "code": c} for a, o, ms, c in reversed(hist)],
                "probe_stable": stable}

    @_serialized
    def apply_preset(self, actor: str, name: str, expected_version: Optional[int] = None) -> Dict[str, Any]:
        """Apply a ROLLOUT_PRESETS cap bundle in one audited, versioned step. Never touches
        `ai_enabled`: the emergency kill switch is independent and always wins."""
        if name not in ROLLOUT_PRESETS:
            raise KeyError(name)
        cfg = self._fresh()
        before = preset_matching(cfg.controls)
        out = self.update_controls(actor, dict(ROLLOUT_PRESETS[name]), expected_version)
        self._commit([AuditEntry(admin_id=actor, entity="global", field="rollout_preset",
                                 old_value=before, new_value=name)])
        return out

    @staticmethod
    def _probe_stream(provider: ChatProvider, req: GenerateRequest, t0: float) -> Tuple[Optional[int], int]:
        """Probe through `stream()`: (time-to-first-token ms, tokens). Empty text is a failure (`provider_empty`) like in
        `generate()`; the text itself is dropped here — a probe never returns provider text."""
        first: Optional[int] = None
        text_len = 0
        tokens = 0
        with contextlib.closing(provider.stream(req)) as events:
            for ev in events:
                if isinstance(ev, Delta):
                    if first is None:
                        first = int((time.monotonic() - t0) * 1000)
                    text_len += len(ev.text.strip())
                elif isinstance(ev, UsageEvent):
                    tokens = int(ev.input_tokens or 0) + int(ev.output_tokens or 0)
        if text_len == 0:
            raise ProviderError("empty probe answer", transient=True, code="provider_empty", category="EMPTY_RESPONSE")
        return first, tokens

    def probe(self, actor: str, slot_id: str) -> Dict[str, Any]:
        """Owner health check: ONE real minimal request through this slot's own key, endpoint
        and model — works while the slot is disabled and the global switch is off, so a new
        project can be verified before it ever serves a user.

        Not `_serialized` (it waits on the network); rate-limited per slot instead.

        ACCOUNTED SEPARATELY from user traffic: a probe never writes the usage ledger, so it
        can never consume the global / per-user / slot budget that admission enforces. It
        has its own visible counters (`probes_today` per slot, `probes_today` in overview),
        its own daily cap (PROBE_DAILY_CAP_PER_SLOT) and the durable audit row. It still
        feeds HEALTH like real traffic: breaker success/failure, 429 cooldown + recent-429
        penalty, sanitized last_error. The provider's text is never returned — only ok,
        latency and the sanitized enums. Audited as `slot:<id>.probe`."""
        cfg = self._fresh(repair=True)
        slot = cfg.slots.get(slot_id)
        if slot is None:
            raise KeyError(slot_id)
        if not self.gate_open(slot.provider_type):
            # Kiểm tra là một request thật tới nhà cung cấp: loại có cổng máy chủ đóng thì KHÔNG gửi gì (và không tính lượt kiểm).
            raise ControlConflict(f"Loại {PROVIDER_LABELS.get(slot.provider_type, slot.provider_type)} chưa được bật ở máy "
                                  f"chủ — đặt biến môi trường {GATED_PROVIDER_TYPES[slot.provider_type]}=1 rồi khởi động "
                                  "lại dịch vụ. Chưa có request nào được gửi.")
        if slot.meta_corrupt:
            raise ControlConflict(f"Siêu dữ liệu của slot {slot_id} bị hỏng — lưu lại slot (sửa) để ghi đè trước khi kiểm.")
        now = self._clock()
        with self._lock:
            if now - self._probe_at.get(slot_id, -1e9) < PROBE_MIN_INTERVAL_S:
                raise ControlConflict(f"Vừa kiểm slot {slot_id} — đợi {int(PROBE_MIN_INTERVAL_S)} giây rồi thử lại.")
            self._roll_probe_day()
            counts = self._probe_counts.setdefault(slot_id, [0, 0, 0])
            if counts[0] >= PROBE_DAILY_CAP_PER_SLOT:
                raise ControlConflict(f"Slot {slot_id} đã được kiểm {PROBE_DAILY_CAP_PER_SLOT} lần hôm nay "
                                      "(ngân sách kiểm riêng) — thử lại ngày mai.")
            # Reserve the probe INSIDE the lock (review): the count can never overshoot the cap.
            counts[0] += 1
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
                provider = self.provider_for(slot, key)
                if getattr(provider, "probe_via_stream", False):
                    # Cùng đường với lượt thật (stream) để đo được TTFT; các loại khác giữ nguyên `generate()`.
                    ttft, tokens = self._probe_stream(provider, req, t0)
                    out["ttft_ms"] = ttft
                else:
                    res = provider.generate(req)
                    tokens = int(res.input_tokens or 0) + int(res.output_tokens or 0)
                out.update(ok=True, latency_ms=int((time.monotonic() - t0) * 1000))
                self.breaker.record_success(slot_id)
                out["tokens"] = tokens
                self.note_latency(slot, ttft_ms=out.get("ttft_ms"), total_ms=out["latency_ms"], ok=True, probe=True)
            except ProviderError as exc:
                cat = getattr(exc, "category", None)
                out["latency_ms"] = int((time.monotonic() - t0) * 1000)
                self.note_latency(slot, ttft_ms=out.get("ttft_ms"), total_ms=out["latency_ms"], ok=False, probe=True)
                if cat == "QUOTA_EXHAUSTED":
                    # Hết hạn mức của nhà cung cấp: slot nghỉ tới 00:00 UTC; không phải lỗi sức khoẻ, không cooldown 30 s,
                    # và (như mọi lần kiểm) không chạm sổ sử dụng.
                    self._mark_quota_out(slot, exc.code, cat)
                elif exc.code == "provider_http_429" or exc.retry_after_s is not None:
                    self.breaker.cool_down(slot_id, exc.retry_after_s if exc.retry_after_s is not None
                                           else DEFAULT_429_COOLDOWN_S)
                    with self._lock:
                        self._recent_429.setdefault(slot_id, deque()).append(self._clock())
                else:
                    self.breaker.record_failure(slot_id)
                self.note_failure(slot, exc.code, cat)
                e = self.last_error(slot_id) or {}
                out.update(code=e.get("code"), category=e.get("category"))
            except Exception:  # noqa: BLE001 — same R1 backstop as the router
                log.warning("ai_control: probe of slot %s raised an unexpected error", slot_id, exc_info=True)
                self.breaker.record_failure(slot_id)
                self.note_failure(slot, "provider_unexpected_error")
                out.update(code="provider_unexpected_error")
        self._note_probe(slot_id, out)
        out.pop("tokens", None)
        result = ((f"ok {out['latency_ms']}ms" + (f" ttft {out['ttft_ms']}ms" if out.get("ttft_ms") is not None else ""))
                  if out["ok"] else f"{out['code']}" + (f"/{out['category']}" if out["category"] else ""))
        self._commit([AuditEntry(admin_id=actor, entity=f"slot:{slot_id}", field="probe",
                                 old_value=slot.model[:120], new_value=result[:200])])
        cur = self.snapshot()
        out["health"] = self.slot_health(cur.slots.get(slot_id, slot), cur, self.usage_today())
        return out
