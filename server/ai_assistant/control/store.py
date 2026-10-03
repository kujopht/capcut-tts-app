"""
AI control plane — persistence (CONFIG + usage counters + audit; never secrets).

`ControlStore` has two implementations:
  * `InMemoryControlStore` — tests and the mock data backend;
  * `AppwriteControlStore` — Appwrite 1.9.6 Legacy documents API, same
    plumbing conventions as `server/ai_assistant/memory.py::AppwriteAiRepo`
    (collection permissions `[]`, `documentSecurity=true`: only the server,
    with its API key, reads or writes these rows).

Additive schema (scripts/setup_appwrite.py, "AI control plane" section):
  ai_control_settings      one row, id "global"
  ai_provider_slots        one row per slot, id = slot_id
  ai_routing_profiles      one row per profile, id = profile name
  ai_provider_usage_daily  id "{slot_id}_{yyyymmdd}" — counters only
  ai_admin_audit           append-only change log (non-secret old/new values)
  ai_alibaba_config        the ISOLATED PARTITION (see below): one row per Alibaba slot / per Alibaba routing overlay

A row that cannot be parsed raises `ControlConfigCorrupt`; the service layer
turns that into a FAIL-CLOSED config (AI off), never into defaults that
might route traffic.

THE ISOLATED PARTITION (`EXT_PROVIDER_TYPES`). Everything Alibaba Model Studio adds to the stored configuration lives in its
OWN collection and nowhere else. The previous release (and any earlier one) validates every row of `ai_provider_slots` and
`ai_routing_profiles` and treats a row it does not understand as a CORRUPT configuration — AI off for everyone. So a persisted
`provider_type = alibaba` row in `ai_provider_slots`, or an `alibaba` step in `ai_routing_profiles.steps_json`, would turn a
code rollback into a global outage. A collection the old code never reads cannot. Consequences, all enforced here:
  * `save_slot` REFUSES an `EXT_PROVIDER_TYPES` slot — it can never reach `ai_provider_slots`;
  * `save_profile` is handed only the legacy-visible steps (the service projects them), the Alibaba steps go to `save_ext_route`;
  * `load_ext()` NEVER raises for a data problem: a bad, missing or unreachable partition yields a status, not an exception, so
    it can never make `load()` fail — Gemini's configuration is read and validated exactly as before.
"""
from __future__ import annotations

import json
import logging
import secrets as _pysecrets
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Tuple
from urllib.parse import quote

import httpx

from server.ai_assistant.control.model import (
    CANARY_PROFILES, EXT_PROVIDER_TYPES, MAX_STEPS, PROFILES, PROVIDER_TYPES, ConfigValidationError, ControlConfig, ExtRoute,
    GlobalControls, ProviderSlot, RoutingProfile, default_profiles, slot_from_dict, slot_meta, slot_to_dict, slot_with_meta,
    validate_slot,
)

T_SETTINGS, T_SLOTS, T_PROFILES, T_USAGE, T_AUDIT = (
    "ai_control_settings", "ai_provider_slots", "ai_routing_profiles",
    "ai_provider_usage_daily", "ai_admin_audit")
#: Vùng lưu trữ tách biệt của các loại `EXT_PROVIDER_TYPES` (docstring đầu tệp). Id dòng: `s-<slot_id>` / `r-<hồ sơ>`.
T_EXT = "ai_alibaba_config"
EXT_SLOT_PREFIX, EXT_ROUTE_PREFIX, EXT_CANARY_PREFIX = "s-", "r-", "c-"
SETTINGS_ID = "global"


class ControlConfigCorrupt(Exception):
    """A stored config row exists but cannot be understood."""


class ControlStoreUnavailable(Exception):
    """The store cannot be reached right now (network, 5xx, 429) or refused a request (`status`)."""

    def __init__(self, message: str = "", *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class ControlSchemaOutdated(ControlStoreUnavailable):
    """The store REJECTED a write because the production schema lacks something this release writes (the optional `meta_json`
    attribute of a legacy slot, or the `ai_alibaba_config` collection of the isolated partition). Nothing was stored; every
    other write is unaffected."""


#: Loại provider đã có trong enum `provider_type` của production — và là TẤT CẢ những gì `ai_provider_slots` được phép chứa.
LEGACY_SLOT_TYPES = ("gemini", "groq", "workers_ai", "qwen", "azure_openai", "openrouter")
log = logging.getLogger("fanfic.ai_assistant")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class UsageCounters:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    errors: int = 0
    rate_limited: int = 0
    cost_micro_usd: int = 0
    last_success_at: str = ""

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class AuditEntry:
    admin_id: str
    entity: str
    field: str
    old_value: str
    new_value: str
    at: str = field(default_factory=now_iso)


@dataclass(frozen=True)
class ExtPartition:
    """What the isolated partition holds, already parsed. `routes` = profile name -> the FULL step list (Alibaba steps included)
    the owner saved; the service decides whether it still matches the legacy-visible profile (`model.compose_profile`)."""
    slots: Dict[str, ProviderSlot] = field(default_factory=dict)
    routes: Dict[str, ExtRoute] = field(default_factory=dict)
    state: str = "empty"
    #: Rows that could not be used at all (bad JSON, wrong shape, duplicate/mismatched id, a non-Alibaba slot): counted only.
    unreadable: int = 0
    #: Owner-only canary routes (`model.CANARY_PROFILES`): name -> slot ids. Rows `c-<NAME>`; no legacy counterpart, no stamp.
    canaries: Dict[str, Tuple[str, ...]] = field(default_factory=dict)


#: `data_json` attribute size in `ai_alibaba_config` (scripts/setup_appwrite.py): a slot is < 1.2 KB, a route < 0.5 KB.
EXT_DATA_MAX = 4000
#: One read page of the partition. MAX_EXT_SLOTS + 6 routes is far below it, so a FULL page means something is wrong.
EXT_PAGE = 100


def parse_ext_rows(rows: List[Dict[str, Any]]) -> ExtPartition:
    """Rows of the isolated partition -> `ExtPartition`. Shared by the in-memory and the Appwrite store so tests of malformed
    data exercise the real parser. NEVER raises: one bad row costs that row (counted), never the others and never Gemini."""
    slots: Dict[str, ProviderSlot] = {}
    routes: Dict[str, ExtRoute] = {}
    canaries: Dict[str, Tuple[str, ...]] = {}
    bad = 0
    for r in rows:
        try:
            kind, key = str(r.get("kind") or ""), str(r.get("key") or "")
            # The document id MUST be the one the writers derive from (kind, key): a row whose id disagrees with its own key is a
            # shadow (`delete_ext_slot(y)` removes `s-y`, never the `s-x` row that claims key `y`), so it is never trusted.
            expected = {"slot": EXT_SLOT_PREFIX, "route": EXT_ROUTE_PREFIX, "canary": EXT_CANARY_PREFIX}.get(kind, "\0") + key
            if str(r.get("$id") or "") != expected:
                raise ValueError("document id does not match kind/key")
            data = json.loads(r.get("data_json") or "")
            if not isinstance(data, dict):
                raise ValueError("payload is not an object")
            if kind == "slot":
                slot = slot_from_dict(data)
                # A slot id equal to a provider-TYPE name is refused (the router resolves a step as a type first, so such a slot
                # could never be addressed by id and would confuse the step split) — create_slot refuses it too.
                if slot.slot_id != key or slot.provider_type not in EXT_PROVIDER_TYPES or key in slots \
                        or key in PROVIDER_TYPES:
                    raise ValueError("slot row does not belong here")
                try:
                    validate_slot(slot)
                except ConfigValidationError:
                    # Readable but unusable (e.g. an endpoint outside the DashScope allowlist): parked, never routed, never probed.
                    slot = replace(slot, meta_corrupt=True)
                slots[key] = slot
            elif kind == "route":
                steps, stamp = data.get("steps"), data.get("stamp", "")
                if key not in PROFILES or key in routes or not isinstance(steps, list) or len(steps) > MAX_STEPS \
                        or any(not isinstance(s, str) for s in steps) or not isinstance(stamp, str):
                    raise ValueError("route row does not belong here")
                routes[key] = ExtRoute(tuple(steps), stamp)
            elif kind == "canary":
                steps = data.get("steps")
                if key not in CANARY_PROFILES or key in canaries or not isinstance(steps, list) or len(steps) > MAX_STEPS \
                        or any(not isinstance(s, str) for s in steps):
                    raise ValueError("canary row does not belong here")
                canaries[key] = tuple(steps)
            else:
                raise ValueError("unknown kind")
        except Exception:  # noqa: BLE001 — the contract is NEVER raises: whatever one row does (even OverflowError…) costs that row
            bad += 1
    return ExtPartition(slots, routes, "ok" if (slots or routes or canaries or bad) else "empty", bad, canaries)


def _ext_payload(data: Dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    if len(payload) > EXT_DATA_MAX:
        raise ValueError(f"ext row payload exceeds {EXT_DATA_MAX} characters")
    return payload


class ControlStore(Protocol):
    def load(self) -> ControlConfig: ...
    def load_ext(self) -> ExtPartition: ...
    def save_controls(self, c: GlobalControls) -> None: ...
    def save_slot(self, s: ProviderSlot, *, clear_meta: bool = False) -> None: ...
    def delete_slot(self, slot_id: str) -> None: ...
    def save_ext_slot(self, s: ProviderSlot) -> None: ...
    def delete_ext_slot(self, slot_id: str) -> None: ...
    def save_ext_route(self, profile: str, steps: Tuple[str, ...], *, stamp: str) -> None: ...
    def delete_ext_route(self, profile: str) -> None: ...
    def save_ext_canary(self, name: str, steps: Tuple[str, ...]) -> None: ...
    def delete_ext_canary(self, name: str) -> None: ...
    def save_profile(self, p: RoutingProfile, *, stamp: str = "") -> None: ...
    def add_audit(self, entries: List[AuditEntry]) -> None: ...
    def list_audit(self, limit: int = 50) -> List[AuditEntry]: ...
    def add_usage(self, slot_id: str, day: str, *, requests: int = 0, input_tokens: int = 0,
                  output_tokens: int = 0, errors: int = 0, rate_limited: int = 0,
                  cost_micro_usd: int = 0, success_at: str = "") -> None: ...
    def usage_for_day(self, day: str) -> Dict[str, UsageCounters]: ...


def _refuse_ext_slot(s: ProviderSlot) -> None:
    """A slot of an isolated type must NEVER be written to the legacy collection: the previous release reads that collection and
    would treat the row as a corrupt configuration (AI off for everyone). Programming error -> loud, nothing stored."""
    if s.provider_type in EXT_PROVIDER_TYPES:
        raise ValueError(f"provider type {s.provider_type!r} is stored in the isolated partition (save_ext_slot), "
                         "never in ai_provider_slots")


def _refuse_ext_profile(p: RoutingProfile) -> None:
    """Same rule for routing: an `alibaba` step in `ai_routing_profiles.steps_json` would make the previous release reject the
    profile. (A step that is the id of an Alibaba SLOT is the service's to project away — the store cannot know slot types.)"""
    if any(s in EXT_PROVIDER_TYPES for s in p.steps):
        raise ValueError("Alibaba routing steps are stored in the isolated partition (save_ext_route), never in ai_routing_profiles")


def _require_ext_slot(s: ProviderSlot) -> None:
    if s.provider_type not in EXT_PROVIDER_TYPES:
        raise ValueError(f"provider type {s.provider_type!r} does not belong in the isolated partition")


def _merge_profiles(stored: Dict[str, RoutingProfile]) -> Dict[str, RoutingProfile]:
    out = default_profiles()
    out.update({k: v for k, v in stored.items() if k in PROFILES})
    return out


# ---------------------------------------------------------------- in-memory


class InMemoryControlStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.controls: Optional[GlobalControls] = None
        self.slots: Dict[str, ProviderSlot] = {}
        self.profiles: Dict[str, RoutingProfile] = {}
        self.audit: List[AuditEntry] = []
        self.usage: Dict[str, Dict[str, UsageCounters]] = {}
        #: Test hook: make load() fail like a corrupt row would.
        self.corrupt: bool = False
        #: The isolated partition, in the SAME row format the Appwrite store keeps (so malformed rows can be injected).
        self.ext_rows: Dict[str, Dict[str, Any]] = {}
        #: Test hook: `"unavailable"` | `"schema_missing"` makes the partition behave like a down store / a missing collection.
        self.ext_fault: str = ""

    def load(self) -> ControlConfig:
        with self._lock:
            if self.corrupt:
                raise ControlConfigCorrupt("test: corrupt config")
            return ControlConfig(self.controls or GlobalControls(), dict(self.slots),
                                 _merge_profiles(dict(self.profiles)))

    def save_controls(self, c: GlobalControls) -> None:
        with self._lock:
            self.controls = c

    def save_slot(self, s: ProviderSlot, *, clear_meta: bool = False) -> None:
        _refuse_ext_slot(s)
        with self._lock:
            self.slots[s.slot_id] = s

    def delete_slot(self, slot_id: str) -> None:
        with self._lock:
            self.slots.pop(slot_id, None)

    def load_ext(self) -> ExtPartition:
        with self._lock:
            if self.ext_fault:
                return ExtPartition(state=self.ext_fault)
            rows = [dict(r) for r in self.ext_rows.values()]
        return parse_ext_rows(rows)

    def _ext_put(self, doc_id: str, kind: str, key: str, data: Dict[str, Any]) -> None:
        payload = _ext_payload(data)
        with self._lock:
            if self.ext_fault == "schema_missing":
                raise ControlSchemaOutdated("collection ai_alibaba_config chưa có — chạy migration trước.", status=404)
            if self.ext_fault:
                raise ControlStoreUnavailable("Kho cấu hình AI đang bận.", status=503)
            self.ext_rows[doc_id] = {"$id": doc_id, "kind": kind, "key": key, "data_json": payload, "updated_at": now_iso()}

    def _ext_drop(self, doc_id: str) -> None:
        with self._lock:
            if self.ext_fault and self.ext_fault != "schema_missing":
                raise ControlStoreUnavailable("Kho cấu hình AI đang bận.", status=503)
            self.ext_rows.pop(doc_id, None)

    def save_ext_slot(self, s: ProviderSlot) -> None:
        _require_ext_slot(s)
        self._ext_put(EXT_SLOT_PREFIX + s.slot_id, "slot", s.slot_id, slot_to_dict(s))

    def delete_ext_slot(self, slot_id: str) -> None:
        self._ext_drop(EXT_SLOT_PREFIX + slot_id)

    def save_ext_route(self, profile: str, steps: Tuple[str, ...], *, stamp: str) -> None:
        self._ext_put(EXT_ROUTE_PREFIX + profile, "route", profile, {"steps": list(steps), "stamp": stamp})

    def delete_ext_route(self, profile: str) -> None:
        self._ext_drop(EXT_ROUTE_PREFIX + profile)

    def save_ext_canary(self, name: str, steps: Tuple[str, ...]) -> None:
        self._ext_put(EXT_CANARY_PREFIX + name, "canary", name, {"steps": list(steps)})

    def delete_ext_canary(self, name: str) -> None:
        self._ext_drop(EXT_CANARY_PREFIX + name)

    def save_profile(self, p: RoutingProfile, *, stamp: str = "") -> None:
        _refuse_ext_profile(p)
        with self._lock:
            self.profiles[p.name] = replace(p, updated_at=stamp or now_iso())

    def add_audit(self, entries: List[AuditEntry]) -> None:
        with self._lock:
            self.audit.extend(entries)

    def list_audit(self, limit: int = 50) -> List[AuditEntry]:
        with self._lock:
            return list(reversed(self.audit))[:limit]

    def add_usage(self, slot_id: str, day: str, *, requests: int = 0, input_tokens: int = 0,
                  output_tokens: int = 0, errors: int = 0, rate_limited: int = 0,
                  cost_micro_usd: int = 0, success_at: str = "") -> None:
        with self._lock:
            u = self.usage.setdefault(day, {}).setdefault(slot_id, UsageCounters())
            u.requests += requests
            u.input_tokens += input_tokens
            u.output_tokens += output_tokens
            u.errors += errors
            u.rate_limited += rate_limited
            u.cost_micro_usd += cost_micro_usd
            if success_at:
                u.last_success_at = success_at

    def usage_for_day(self, day: str) -> Dict[str, UsageCounters]:
        with self._lock:
            return {k: replace(v) for k, v in self.usage.get(day, {}).items()}


# ---------------------------------------------------------------- Appwrite

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _json_list(raw: Any, name: str) -> List[Any]:
    try:
        v = json.loads(raw) if isinstance(raw, str) and raw else []
    except ValueError as exc:
        raise ControlConfigCorrupt(f"{name}: invalid JSON") from exc
    if not isinstance(v, list):
        raise ControlConfigCorrupt(f"{name}: not a list")
    return v


def _json_dict(raw: Any, name: str) -> Dict[str, Any]:
    try:
        v = json.loads(raw) if isinstance(raw, str) and raw else {}
    except ValueError as exc:
        raise ControlConfigCorrupt(f"{name}: invalid JSON") from exc
    if not isinstance(v, dict):
        raise ControlConfigCorrupt(f"{name}: not an object")
    return v


class AppwriteControlStore:
    def __init__(self, settings: Any, *, client: Optional[httpx.Client] = None) -> None:
        aw = settings.appwrite if hasattr(settings, "appwrite") else settings
        if not (aw.endpoint and aw.project_id and aw.api_key and aw.database_id):
            raise ControlStoreUnavailable("Appwrite chưa cấu hình đủ cho control plane AI.")
        self._base = aw.api_base
        self._db = aw.database_id
        self._headers = {"X-Appwrite-Project": aw.project_id, "X-Appwrite-Key": aw.api_key,
                         "Content-Type": "application/json"}
        self._client = client or httpx.Client(timeout=_TIMEOUT)
        #: Mỗi (slot, ngày) một khoá: `add_usage` là đọc-rồi-ghi hai lần gọi mạng, nên hai lượt cùng slot kết thúc cùng lúc
        #: (tối đa 4 luồng SSE/instance) mất một lần đếm — và bộ đếm này CHÍNH là trần toàn cục 150/ngày.
        self._usage_guard = threading.Lock()
        self._usage_locks: Dict[str, threading.Lock] = {}

    def _usage_lock(self, doc_id: str) -> threading.Lock:
        with self._usage_guard:
            return self._usage_locks.setdefault(doc_id, threading.Lock())

    # ---- plumbing (same shape as AppwriteAiRepo) ----
    def _call(self, method: str, path: str, *, body: Any = None, queries: Optional[List[str]] = None) -> Any:
        url = f"{self._base}{path}"
        if queries:
            url += "?" + "&".join("queries[]=" + quote(q) for q in queries)
        try:
            r = self._client.request(method, url, json=body, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ControlStoreUnavailable("Không kết nối được kho cấu hình AI.") from exc
        if r.status_code == 404:
            return None
        if r.status_code == 429 or r.status_code >= 500:
            raise ControlStoreUnavailable("Kho cấu hình AI đang bận.", status=r.status_code)
        if r.status_code >= 400:
            raise ControlStoreUnavailable(f"Kho cấu hình AI từ chối yêu cầu ({r.status_code}).", status=r.status_code)
        return r.json() if r.content else {}

    @staticmethod
    def _q(method: str, attribute: Optional[str] = None, values: Optional[List[Any]] = None) -> str:
        d: Dict[str, Any] = {"method": method}
        if attribute is not None:
            d["attribute"] = attribute
        if values is not None:
            d["values"] = values
        return json.dumps(d, separators=(",", ":"))

    def _docs(self, t: str) -> str:
        return f"/v1/databases/{self._db}/collections/{t}/documents"

    def _get(self, t: str, doc_id: str) -> Optional[Dict[str, Any]]:
        return self._call("GET", f"{self._docs(t)}/{quote(doc_id)}")

    def _put(self, t: str, doc_id: str, data: Dict[str, Any]) -> None:
        """Create-or-update (Legacy API has no upsert): PATCH, then POST on 404."""
        if self._call("PATCH", f"{self._docs(t)}/{quote(doc_id)}", body={"data": data}) is None:
            self._call("POST", self._docs(t), body={"documentId": doc_id, "data": data, "permissions": []})

    def _list(self, t: str, queries: List[str]) -> List[Dict[str, Any]]:
        b = self._call("GET", self._docs(t), queries=queries) or {}
        return b.get("documents") or []

    # ---- config ----
    def load(self) -> ControlConfig:
        row = self._get(T_SETTINGS, SETTINGS_ID)
        controls = self._controls_from_row(row) if row else GlobalControls()
        slots = {}
        for r in self._list(T_SLOTS, [self._q("limit", values=[100])]):
            s = self._slot_from_row(r)
            slots[s.slot_id] = s
        profiles = {}
        for r in self._list(T_PROFILES, [self._q("limit", values=[50])]):
            p = self._profile_from_row(r)
            profiles[p.name] = p
        return ControlConfig(controls, slots, _merge_profiles(profiles))

    @staticmethod
    def _controls_from_row(r: Dict[str, Any]) -> GlobalControls:
        try:
            types = _json_dict(r.get("provider_types_json"), "provider_types_json")
            modes = _json_dict(r.get("mode_profiles_json"), "mode_profiles_json")
            base = GlobalControls()
            return GlobalControls(
                ai_enabled=bool(r.get("ai_enabled", False)),
                provider_types={t: bool(types.get(t, False)) for t in PROVIDER_TYPES},
                global_daily_request_cap=int(r.get("global_daily_request_cap", base.global_daily_request_cap)),
                global_daily_token_cap=int(r.get("global_daily_token_cap", base.global_daily_token_cap)),
                per_user_daily_request_cap=int(r.get("per_user_daily_request_cap", base.per_user_daily_request_cap)),
                per_user_daily_token_cap=int(r.get("per_user_daily_token_cap", base.per_user_daily_token_cap)),
                daily_cost_cap_micro_usd=int(r.get("daily_cost_cap_micro_usd", 0) or 0),
                max_output_tokens=int(r.get("max_output_tokens", base.max_output_tokens)),
                max_context_tokens=int(r.get("max_context_tokens", base.max_context_tokens)),
                mode_profiles={k: str(v) for k, v in modes.items()} or dict(base.mode_profiles),
                web_search_profile=str(r.get("web_search_profile") or base.web_search_profile),
                web_search_tool=str(r.get("web_search_tool") or "off"),
                version=int(r.get("version", 0) or 0), updated_by=str(r.get("updated_by") or ""),
                updated_at=str(r.get("updated_at") or ""))
        except (TypeError, ValueError) as exc:
            raise ControlConfigCorrupt("ai_control_settings: bad field type") from exc

    @staticmethod
    def _slot_from_row(r: Dict[str, Any]) -> ProviderSlot:
        try:
            slot = ProviderSlot(
                slot_id=str(r["slot_id"]), provider_type=str(r["provider_type"]), label=str(r.get("label") or ""),
                secret_ref=str(r.get("secret_ref") or ""), model=str(r.get("model") or ""),
                enabled=bool(r.get("enabled", False)), endpoint=str(r.get("endpoint") or ""),
                api_version=str(r.get("api_version") or ""), priority=int(r.get("priority", 50)),
                weight=int(r.get("weight", 10)), daily_request_cap=int(r.get("daily_request_cap", 0) or 0),
                daily_token_cap=int(r.get("daily_token_cap", 0) or 0), rpm_soft_cap=int(r.get("rpm_soft_cap", 0) or 0),
                tpm_soft_cap=int(r.get("tpm_soft_cap", 0) or 0),
                workloads=tuple(str(w) for w in _json_list(r.get("workloads_json"), "workloads_json")),
                price_in_micro_per_mtok=int(r.get("price_in_micro_per_mtok", 0) or 0),
                price_out_micro_per_mtok=int(r.get("price_out_micro_per_mtok", 0) or 0))
        except (KeyError, TypeError, ValueError) as exc:
            raise ControlConfigCorrupt("ai_provider_slots: bad row") from exc
        # Siêu dữ liệu tuỳ chọn (tầng năng lực, hạn mức miễn phí): hỏng/sai chỉ làm RIÊNG slot này bị bỏ qua (`meta_corrupt`),
        # không bao giờ làm cả cấu hình hỏng — nếu không một dòng Alibaba hỏng sẽ tắt luôn AI của Gemini.
        raw = r.get("meta_json")
        if isinstance(raw, str) and raw.strip():
            try:
                slot = slot_with_meta(slot, json.loads(raw))
            except (ValueError, TypeError):
                slot = replace(slot, meta_corrupt=True)
        return slot

    @staticmethod
    def _profile_from_row(r: Dict[str, Any]) -> RoutingProfile:
        try:
            return RoutingProfile(name=str(r["name"]),
                                  steps=tuple(str(s) for s in _json_list(r.get("steps_json"), "steps_json")),
                                  enabled=bool(r.get("enabled", True)), updated_at=str(r.get("updated_at") or ""))
        except (KeyError, TypeError, ValueError) as exc:
            raise ControlConfigCorrupt("ai_routing_profiles: bad row") from exc

    def save_controls(self, c: GlobalControls) -> None:
        self._put(T_SETTINGS, SETTINGS_ID, {
            "ai_enabled": c.ai_enabled, "provider_types_json": json.dumps(c.provider_types, sort_keys=True),
            "global_daily_request_cap": c.global_daily_request_cap, "global_daily_token_cap": c.global_daily_token_cap,
            "per_user_daily_request_cap": c.per_user_daily_request_cap,
            "per_user_daily_token_cap": c.per_user_daily_token_cap,
            "daily_cost_cap_micro_usd": c.daily_cost_cap_micro_usd, "max_output_tokens": c.max_output_tokens,
            "max_context_tokens": c.max_context_tokens,
            "mode_profiles_json": json.dumps(c.mode_profiles, sort_keys=True),
            "web_search_profile": c.web_search_profile, "web_search_tool": c.web_search_tool,
            "version": c.version, "updated_by": c.updated_by[:64], "updated_at": c.updated_at or now_iso()})

    def save_slot(self, s: ProviderSlot, *, clear_meta: bool = False) -> None:
        _refuse_ext_slot(s)
        data = {
            "slot_id": s.slot_id, "provider_type": s.provider_type, "label": s.label, "secret_ref": s.secret_ref,
            "model": s.model, "enabled": s.enabled, "endpoint": s.endpoint, "api_version": s.api_version,
            "priority": s.priority, "weight": s.weight, "daily_request_cap": s.daily_request_cap,
            "daily_token_cap": s.daily_token_cap, "rpm_soft_cap": s.rpm_soft_cap, "tpm_soft_cap": s.tpm_soft_cap,
            "workloads_json": json.dumps(list(s.workloads)),
            "price_in_micro_per_mtok": s.price_in_micro_per_mtok,
            "price_out_micro_per_mtok": s.price_out_micro_per_mtok, "updated_at": now_iso()}
        # `meta_json` CHỈ được gửi khi có siêu dữ liệu (hoặc khi cần XOÁ cái đã lưu): một slot thường gửi đúng bộ thuộc tính
        # như trước, nên production chưa có thuộc tính này vẫn ghi slot bình thường (kể cả tắt khẩn cấp một slot).
        meta = slot_meta(s)
        if meta:
            data["meta_json"] = json.dumps(meta, sort_keys=True, separators=(",", ":"))
        elif clear_meta:
            data["meta_json"] = ""
        try:
            self._put(T_SLOTS, s.slot_id, data)
        except ControlStoreUnavailable as exc:
            if exc.status == 400 and (meta or clear_meta):
                raise ControlSchemaOutdated(
                    "Schema Appwrite chưa có thuộc tính `meta_json` mà bản này ghi cho slot có tầng/hạn mức — "
                    "chạy migration trước (docs/ai/ALIBABA_PROVIDER.md, mục Migration schema).", status=400) from exc
            raise

    def delete_slot(self, slot_id: str) -> None:
        self._call("DELETE", f"{self._docs(T_SLOTS)}/{quote(slot_id)}")

    def save_profile(self, p: RoutingProfile, *, stamp: str = "") -> None:
        """`stamp` (optional) is the `updated_at` to write — the service passes the same value to the Alibaba route row so the
        route is valid only for THIS write of the legacy row. Same attribute, same format as before: nothing new for production."""
        _refuse_ext_profile(p)
        self._put(T_PROFILES, p.name, {"name": p.name, "steps_json": json.dumps(list(p.steps)),
                                       "enabled": p.enabled, "updated_at": stamp or now_iso()})

    # ---- the isolated partition (module docstring) ----
    def load_ext(self) -> ExtPartition:
        """NEVER raises: a missing collection, an unreachable store or a bad row is a STATUS, so this call can never be the
        reason `load()` — and with it Gemini's configuration — fails."""
        try:
            body = self._call("GET", self._docs(T_EXT), queries=[self._q("limit", values=[EXT_PAGE])])
        except ControlStoreUnavailable:
            return ExtPartition(state="unavailable")
        if body is None:  # 404: the collection does not exist yet (migration not run)
            return ExtPartition(state="schema_missing")
        try:
            rows = body.get("documents") if isinstance(body, dict) else None
            rows = rows if isinstance(rows, list) else []
            if len(rows) >= EXT_PAGE:
                # A full page can never be legitimate (≤ MAX_EXT_SLOTS slots + 6 routes) and may hide real rows behind junk:
                # degraded, so no Alibaba slot is used rather than half of them.
                log.error("ai_control: isolated partition returned a full page — treated as unavailable")
                return ExtPartition(state="unavailable")
            return parse_ext_rows(rows)
        except Exception:  # noqa: BLE001 — a parser bug must never reach the legacy configuration
            log.error("ai_control: isolated partition could not be parsed — treated as unavailable")
            return ExtPartition(state="unavailable")

    def _ext_put(self, doc_id: str, kind: str, key: str, data: Dict[str, Any]) -> None:
        body = {"kind": kind, "key": key, "data_json": _ext_payload(data), "updated_at": now_iso()}
        outdated = ("Schema Appwrite chưa có collection/thuộc tính của vùng Alibaba (ai_alibaba_config) — chạy migration "
                    "trước (docs/ai/ALIBABA_PROVIDER.md, mục Migration schema).")
        path = f"{self._docs(T_EXT)}/{quote(doc_id)}"
        try:
            for _attempt in range(2):  # a second pass only after a create race (409): another instance made/removed the row
                if self._call("PATCH", path, body={"data": body}) is not None:
                    return
                try:
                    if self._call("POST", self._docs(T_EXT), body={"documentId": doc_id, "data": body, "permissions": []}) is not None:
                        return
                except ControlStoreUnavailable as exc:
                    if exc.status != 409:
                        raise
                    continue  # created by someone else between our PATCH (404) and POST: update it instead of failing
                # PATCH and POST both 404: the COLLECTION is missing. Without this a write would "succeed" and store nothing.
                raise ControlSchemaOutdated(outdated, status=404)
            raise ControlStoreUnavailable("Kho cấu hình AI đang bận (xung đột khi tạo dòng).", status=409)
        except ControlSchemaOutdated:
            raise
        except ControlStoreUnavailable as exc:
            if exc.status == 400:
                raise ControlSchemaOutdated(outdated, status=400) from exc
            raise

    def save_ext_slot(self, s: ProviderSlot) -> None:
        _require_ext_slot(s)
        self._ext_put(EXT_SLOT_PREFIX + s.slot_id, "slot", s.slot_id, slot_to_dict(s))

    def delete_ext_slot(self, slot_id: str) -> None:
        self._call("DELETE", f"{self._docs(T_EXT)}/{quote(EXT_SLOT_PREFIX + slot_id)}")

    def save_ext_route(self, profile: str, steps: Tuple[str, ...], *, stamp: str) -> None:
        self._ext_put(EXT_ROUTE_PREFIX + profile, "route", profile, {"steps": list(steps), "stamp": stamp})

    def delete_ext_route(self, profile: str) -> None:
        self._call("DELETE", f"{self._docs(T_EXT)}/{quote(EXT_ROUTE_PREFIX + profile)}")

    def save_ext_canary(self, name: str, steps: Tuple[str, ...]) -> None:
        self._ext_put(EXT_CANARY_PREFIX + name, "canary", name, {"steps": list(steps)})

    def delete_ext_canary(self, name: str) -> None:
        self._call("DELETE", f"{self._docs(T_EXT)}/{quote(EXT_CANARY_PREFIX + name)}")

    # ---- audit ----
    def add_audit(self, entries: List[AuditEntry]) -> None:
        for e in entries:
            self._call("POST", self._docs(T_AUDIT), body={
                "documentId": "aud_" + _pysecrets.token_hex(10), "permissions": [],
                "data": {"admin_id": e.admin_id[:64], "at": e.at, "entity": e.entity[:80],
                         "field": e.field[:60], "old_value": e.old_value[:500], "new_value": e.new_value[:500]}})

    def list_audit(self, limit: int = 50) -> List[AuditEntry]:
        rows = self._list(T_AUDIT, [self._q("orderDesc", "at"), self._q("limit", values=[max(1, min(limit, 100))])])
        return [AuditEntry(admin_id=str(r.get("admin_id") or ""), entity=str(r.get("entity") or ""),
                           field=str(r.get("field") or ""), old_value=str(r.get("old_value") or ""),
                           new_value=str(r.get("new_value") or ""), at=str(r.get("at") or "")) for r in rows]

    # ---- usage (read-modify-write; serialized per slot-day inside this process) ----
    def add_usage(self, slot_id: str, day: str, *, requests: int = 0, input_tokens: int = 0,
                  output_tokens: int = 0, errors: int = 0, rate_limited: int = 0,
                  cost_micro_usd: int = 0, success_at: str = "") -> None:
        doc_id = f"{slot_id}_{day}"
        with self._usage_lock(doc_id):
            cur = self._get(T_USAGE, doc_id) or {}
            data = {"slot_id": slot_id, "day": day,
                    "requests": int(cur.get("requests") or 0) + requests,
                    "input_tokens": int(cur.get("input_tokens") or 0) + input_tokens,
                    "output_tokens": int(cur.get("output_tokens") or 0) + output_tokens,
                    "errors": int(cur.get("errors") or 0) + errors,
                    "rate_limited": int(cur.get("rate_limited") or 0) + rate_limited,
                    "cost_micro_usd": int(cur.get("cost_micro_usd") or 0) + cost_micro_usd,
                    "updated_at": now_iso()}
            if success_at:
                data["last_success_at"] = success_at
            self._put(T_USAGE, doc_id, data)

    def usage_for_day(self, day: str) -> Dict[str, UsageCounters]:
        out: Dict[str, UsageCounters] = {}
        for r in self._list(T_USAGE, [self._q("equal", "day", [day]), self._q("limit", values=[100])]):
            out[str(r.get("slot_id") or "")] = UsageCounters(
                requests=int(r.get("requests") or 0), input_tokens=int(r.get("input_tokens") or 0),
                output_tokens=int(r.get("output_tokens") or 0), errors=int(r.get("errors") or 0),
                rate_limited=int(r.get("rate_limited") or 0), cost_micro_usd=int(r.get("cost_micro_usd") or 0),
                last_success_at=str(r.get("last_success_at") or ""))
        return out
