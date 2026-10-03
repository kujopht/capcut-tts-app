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

A row that cannot be parsed raises `ControlConfigCorrupt`; the service layer
turns that into a FAIL-CLOSED config (AI off), never into defaults that
might route traffic.
"""
from __future__ import annotations

import json
import secrets as _pysecrets
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol
from urllib.parse import quote

import httpx

from server.tests.fixtures.legacy_release_3f86706.model import (
    PROFILES, PROVIDER_TYPES, ControlConfig, GlobalControls, ProviderSlot, RoutingProfile,
    default_profiles,
)

T_SETTINGS, T_SLOTS, T_PROFILES, T_USAGE, T_AUDIT = (
    "ai_control_settings", "ai_provider_slots", "ai_routing_profiles",
    "ai_provider_usage_daily", "ai_admin_audit")
SETTINGS_ID = "global"


class ControlConfigCorrupt(Exception):
    """A stored config row exists but cannot be understood."""


class ControlStoreUnavailable(Exception):
    """The store cannot be reached right now (network, 5xx, 429)."""


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


class ControlStore(Protocol):
    def load(self) -> ControlConfig: ...
    def save_controls(self, c: GlobalControls) -> None: ...
    def save_slot(self, s: ProviderSlot) -> None: ...
    def delete_slot(self, slot_id: str) -> None: ...
    def save_profile(self, p: RoutingProfile) -> None: ...
    def add_audit(self, entries: List[AuditEntry]) -> None: ...
    def list_audit(self, limit: int = 50) -> List[AuditEntry]: ...
    def add_usage(self, slot_id: str, day: str, *, requests: int = 0, input_tokens: int = 0,
                  output_tokens: int = 0, errors: int = 0, rate_limited: int = 0,
                  cost_micro_usd: int = 0, success_at: str = "") -> None: ...
    def usage_for_day(self, day: str) -> Dict[str, UsageCounters]: ...


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

    def load(self) -> ControlConfig:
        with self._lock:
            if self.corrupt:
                raise ControlConfigCorrupt("test: corrupt config")
            return ControlConfig(self.controls or GlobalControls(), dict(self.slots),
                                 _merge_profiles(dict(self.profiles)))

    def save_controls(self, c: GlobalControls) -> None:
        with self._lock:
            self.controls = c

    def save_slot(self, s: ProviderSlot) -> None:
        with self._lock:
            self.slots[s.slot_id] = s

    def delete_slot(self, slot_id: str) -> None:
        with self._lock:
            self.slots.pop(slot_id, None)

    def save_profile(self, p: RoutingProfile) -> None:
        with self._lock:
            self.profiles[p.name] = p

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
            raise ControlStoreUnavailable("Kho cấu hình AI đang bận.")
        if r.status_code >= 400:
            raise ControlStoreUnavailable(f"Kho cấu hình AI từ chối yêu cầu ({r.status_code}).")
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
            return ProviderSlot(
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

    @staticmethod
    def _profile_from_row(r: Dict[str, Any]) -> RoutingProfile:
        try:
            return RoutingProfile(name=str(r["name"]),
                                  steps=tuple(str(s) for s in _json_list(r.get("steps_json"), "steps_json")),
                                  enabled=bool(r.get("enabled", True)))
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

    def save_slot(self, s: ProviderSlot) -> None:
        self._put(T_SLOTS, s.slot_id, {
            "slot_id": s.slot_id, "provider_type": s.provider_type, "label": s.label, "secret_ref": s.secret_ref,
            "model": s.model, "enabled": s.enabled, "endpoint": s.endpoint, "api_version": s.api_version,
            "priority": s.priority, "weight": s.weight, "daily_request_cap": s.daily_request_cap,
            "daily_token_cap": s.daily_token_cap, "rpm_soft_cap": s.rpm_soft_cap, "tpm_soft_cap": s.tpm_soft_cap,
            "workloads_json": json.dumps(list(s.workloads)),
            "price_in_micro_per_mtok": s.price_in_micro_per_mtok,
            "price_out_micro_per_mtok": s.price_out_micro_per_mtok, "updated_at": now_iso()})

    def delete_slot(self, slot_id: str) -> None:
        self._call("DELETE", f"{self._docs(T_SLOTS)}/{quote(slot_id)}")

    def save_profile(self, p: RoutingProfile) -> None:
        self._put(T_PROFILES, p.name, {"name": p.name, "steps_json": json.dumps(list(p.steps)),
                                       "enabled": p.enabled, "updated_at": now_iso()})

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
