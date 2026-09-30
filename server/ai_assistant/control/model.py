"""
AI control plane — configuration model (docs/ai/AI_ADMIN_CONTROL_PLANE.md).

CONFIG only. Secrets never appear here: a provider slot names its key with
`secret_ref` (e.g. "GEMINI_PROJECT_01"), resolved at call time from the
server environment variable `FAS_AI_SECRET_<secret_ref>` (`secrets.py`).

Every value the admin API accepts is validated HERE, server-side, before it
is stored: types, ranges, identifier patterns, per-provider endpoint host
allowlist (the admin form must not become an SSRF vector), and routing
profiles that only reference things that exist. A config that fails
validation when LOADED is treated as corrupt and the control plane fails
closed (`service.py`) — it never falls back to an unrestricted provider.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit

PROVIDER_TYPES: Tuple[str, ...] = ("gemini", "groq", "workers_ai", "qwen", "azure_openai", "openrouter")
PROVIDER_LABELS: Dict[str, str] = {
    "gemini": "Google Gemini", "groq": "Groq", "workers_ai": "Cloudflare Workers AI",
    "qwen": "Alibaba Qwen (DashScope)", "azure_openai": "Azure OpenAI", "openrouter": "OpenRouter",
}
WORKLOADS: Tuple[str, ...] = ("general", "story", "support", "writer", "web_search")
PROFILES: Tuple[str, ...] = ("FREE_FIRST", "QUALITY_FIRST", "WRITER", "STORY", "SUPPORT_SAFE", "WEB_SEARCH")
MODES: Tuple[str, ...] = ("general", "story", "support", "writer")
WEB_SEARCH_TOOLS: Tuple[str, ...] = ("off",)

#: Default endpoint per provider type (OpenAI-compatible chat-completions
#: base). `workers_ai` and `azure_openai` need an account/resource-specific
#: endpoint and have none.
DEFAULT_ENDPOINTS: Dict[str, str] = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
    "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}
#: Endpoint host allowlist per type — exact hosts, or ".suffix" entries.
ENDPOINT_HOSTS: Dict[str, Tuple[str, ...]] = {
    "gemini": ("generativelanguage.googleapis.com",),
    "groq": ("api.groq.com",),
    "workers_ai": ("api.cloudflare.com",),
    "qwen": ("dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com"),
    "azure_openai": (".openai.azure.com", ".cognitiveservices.azure.com"),
    "openrouter": ("openrouter.ai",),
}

DEFAULT_PROFILE_STEPS: Dict[str, Tuple[str, ...]] = {
    "FREE_FIRST": ("gemini", "groq", "workers_ai", "qwen", "openrouter"),
    "QUALITY_FIRST": ("qwen", "azure_openai", "gemini", "openrouter"),
    "WRITER": ("qwen", "azure_openai", "gemini"),
    "STORY": ("gemini", "groq", "qwen"),
    "SUPPORT_SAFE": ("azure_openai", "qwen"),
    "WEB_SEARCH": ("gemini", "qwen"),
}
DEFAULT_MODE_PROFILES: Dict[str, str] = {
    "general": "FREE_FIRST", "story": "STORY", "writer": "WRITER", "support": "SUPPORT_SAFE",
}

SLOT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")
SECRET_REF_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9._:/@-]{1,120}$")
API_VERSION_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}(-preview)?$")
MAX_SLOTS = 40
MAX_STEPS = 12
MAX_INT = 1_000_000_000


class ConfigValidationError(ValueError):
    """One or more fields are invalid. `errors` is a list of
    {"field": ..., "message": ...} — shown to the admin as-is (Vietnamese)."""

    def __init__(self, errors: List[Dict[str, str]]):
        super().__init__("; ".join(f"{e['field']}: {e['message']}" for e in errors))
        self.errors = errors


@dataclass(frozen=True)
class ProviderSlot:
    slot_id: str
    provider_type: str
    label: str
    secret_ref: str
    model: str
    enabled: bool = False
    endpoint: str = ""
    api_version: str = ""
    priority: int = 50
    weight: int = 10
    daily_request_cap: int = 0
    daily_token_cap: int = 0
    rpm_soft_cap: int = 0
    tpm_soft_cap: int = 0
    workloads: Tuple[str, ...] = ("general",)
    #: USD per 1M tokens, stored as integer micro-USD (no float drift).
    price_in_micro_per_mtok: int = 0
    price_out_micro_per_mtok: int = 0

    def effective_endpoint(self) -> str:
        return self.endpoint or DEFAULT_ENDPOINTS.get(self.provider_type, "")


@dataclass(frozen=True)
class RoutingProfile:
    name: str
    steps: Tuple[str, ...]
    enabled: bool = True


def _default_types() -> Dict[str, bool]:
    return {t: False for t in PROVIDER_TYPES}


@dataclass(frozen=True)
class GlobalControls:
    #: The global kill switch. Defaults to OFF: an absent config never means "on".
    ai_enabled: bool = False
    provider_types: Dict[str, bool] = field(default_factory=_default_types)
    global_daily_request_cap: int = 2000
    global_daily_token_cap: int = 2_000_000
    per_user_daily_request_cap: int = 50
    per_user_daily_token_cap: int = 30_000
    #: 0 = no cost ceiling (estimates only).
    daily_cost_cap_micro_usd: int = 0
    max_output_tokens: int = 800
    max_context_tokens: int = 6000
    mode_profiles: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MODE_PROFILES))
    web_search_profile: str = "WEB_SEARCH"
    web_search_tool: str = "off"
    version: int = 0
    updated_by: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class ControlConfig:
    controls: GlobalControls
    slots: Dict[str, ProviderSlot]
    profiles: Dict[str, RoutingProfile]


def default_profiles() -> Dict[str, RoutingProfile]:
    return {n: RoutingProfile(name=n, steps=s) for n, s in DEFAULT_PROFILE_STEPS.items()}


def empty_config() -> ControlConfig:
    """What an unconfigured store looks like: AI off, every provider type off,
    no slots, default profile orders (which route to nothing until slots exist)."""
    return ControlConfig(GlobalControls(), {}, default_profiles())


# ------------------------------------------------------------------ validation


def _int_in(errors: List[Dict[str, str]], name: str, v: Any, lo: int, hi: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        errors.append({"field": name, "message": "phải là số nguyên"})
        return lo
    if not lo <= v <= hi:
        errors.append({"field": name, "message": f"phải trong khoảng {lo}–{hi}"})
    return v


def _endpoint_errors(provider_type: str, endpoint: str) -> Optional[str]:
    if not endpoint:
        if provider_type in ("workers_ai", "azure_openai"):
            return "bắt buộc với loại provider này"
        return None
    try:
        u = urlsplit(endpoint)
    except ValueError:
        return "URL không hợp lệ"
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment:
        return "chỉ nhận https://host/đường-dẫn (không user, query hay fragment)"
    if u.port not in (None, 443):
        return "chỉ cổng 443"
    host = u.hostname.lower()
    allowed = ENDPOINT_HOSTS.get(provider_type, ())
    if not any(host == a or (a.startswith(".") and host.endswith(a)) for a in allowed):
        return f"máy chủ không nằm trong danh sách cho phép của {provider_type}"
    if provider_type == "workers_ai" and not u.path.startswith("/client/v4/accounts/"):
        return "phải có dạng /client/v4/accounts/<account_id>/ai/v1"
    return None


def validate_slot(slot: ProviderSlot) -> None:
    e: List[Dict[str, str]] = []
    if not SLOT_ID_RE.match(slot.slot_id or ""):
        e.append({"field": "slot_id", "message": "2–40 ký tự a-z, 0-9, '-', '_' (bắt đầu bằng chữ/số)"})
    if slot.provider_type not in PROVIDER_TYPES:
        e.append({"field": "provider_type", "message": "loại provider không hỗ trợ"})
    if not (slot.label or "").strip() or len(slot.label) > 60:
        e.append({"field": "label", "message": "1–60 ký tự"})
    if not SECRET_REF_RE.match(slot.secret_ref or ""):
        e.append({"field": "secret_ref", "message": "TÊN tham chiếu (A-Z, 0-9, '_', 3–64 ký tự) — không phải khoá"})
    if not MODEL_RE.match(slot.model or ""):
        e.append({"field": "model", "message": "1–120 ký tự A-Z a-z 0-9 . _ : / @ -"})
    if slot.provider_type in PROVIDER_TYPES:
        msg = _endpoint_errors(slot.provider_type, slot.endpoint)
        if msg:
            e.append({"field": "endpoint", "message": msg})
    if slot.api_version and (slot.provider_type != "azure_openai" or not API_VERSION_RE.match(slot.api_version)):
        e.append({"field": "api_version", "message": "chỉ dùng cho Azure, dạng YYYY-MM-DD[-preview]"})
    _int_in(e, "priority", slot.priority, 0, 99)
    _int_in(e, "weight", slot.weight, 1, 100)
    for n in ("daily_request_cap", "daily_token_cap", "rpm_soft_cap", "tpm_soft_cap",
              "price_in_micro_per_mtok", "price_out_micro_per_mtok"):
        _int_in(e, n, getattr(slot, n), 0, MAX_INT)
    wl = tuple(slot.workloads or ())
    if not wl or any(w not in WORKLOADS for w in wl) or len(set(wl)) != len(wl):
        e.append({"field": "workloads", "message": "chọn ít nhất một, trong " + ", ".join(WORKLOADS)})
    if e:
        raise ConfigValidationError(e)


def validate_profile(profile: RoutingProfile, slots: Mapping[str, ProviderSlot]) -> None:
    e: List[Dict[str, str]] = []
    if profile.name not in PROFILES:
        e.append({"field": "name", "message": "hồ sơ định tuyến không tồn tại"})
    steps = tuple(profile.steps or ())
    if len(steps) > MAX_STEPS:
        e.append({"field": "steps", "message": f"tối đa {MAX_STEPS} bước"})
    if len(set(steps)) != len(steps):
        e.append({"field": "steps", "message": "không được lặp bước"})
    for s in steps:
        if s not in PROVIDER_TYPES and s not in slots:
            e.append({"field": "steps", "message": f"'{s}' không phải loại provider hay slot đã có"})
    if e:
        raise ConfigValidationError(e)


def validate_controls(c: GlobalControls) -> None:
    e: List[Dict[str, str]] = []
    if not isinstance(c.ai_enabled, bool):
        e.append({"field": "ai_enabled", "message": "phải là true/false"})
    if set(c.provider_types) != set(PROVIDER_TYPES) or any(not isinstance(v, bool) for v in c.provider_types.values()):
        e.append({"field": "provider_types", "message": "phải có đủ và chỉ " + ", ".join(PROVIDER_TYPES)})
    for n in ("global_daily_request_cap", "global_daily_token_cap", "per_user_daily_request_cap",
              "per_user_daily_token_cap", "daily_cost_cap_micro_usd"):
        _int_in(e, n, getattr(c, n), 0, MAX_INT)
    _int_in(e, "max_output_tokens", c.max_output_tokens, 64, 8000)
    _int_in(e, "max_context_tokens", c.max_context_tokens, 512, 32000)
    if set(c.mode_profiles) != set(MODES) or any(p not in PROFILES for p in c.mode_profiles.values()):
        e.append({"field": "mode_profiles", "message": "mỗi chế độ phải trỏ tới một hồ sơ hợp lệ"})
    if c.web_search_profile not in PROFILES:
        e.append({"field": "web_search_profile", "message": "hồ sơ định tuyến không tồn tại"})
    if c.web_search_tool not in WEB_SEARCH_TOOLS:
        e.append({"field": "web_search_tool", "message": "công cụ tìm web không hỗ trợ"})
    if e:
        raise ConfigValidationError(e)


def validate_config(cfg: ControlConfig) -> None:
    """Whole-config check used when LOADING (corrupt -> fail closed)."""
    validate_controls(cfg.controls)
    if len(cfg.slots) > MAX_SLOTS:
        raise ConfigValidationError([{"field": "slots", "message": f"tối đa {MAX_SLOTS} slot"}])
    for sid, s in cfg.slots.items():
        if sid != s.slot_id:
            raise ConfigValidationError([{"field": "slots", "message": "slot_id lệch khoá"}])
        validate_slot(s)
    for name, p in cfg.profiles.items():
        if name != p.name:
            raise ConfigValidationError([{"field": "profiles", "message": "tên hồ sơ lệch khoá"}])
        validate_profile(p, cfg.slots)


# ------------------------------------------------------------------ (de)serialisation


def slot_from_dict(d: Mapping[str, Any]) -> ProviderSlot:
    """From an API body or stored row. Unknown keys are ignored; missing keys
    take the dataclass default. Raises ConfigValidationError on bad types."""
    try:
        return ProviderSlot(
            slot_id=str(d.get("slot_id", "")), provider_type=str(d.get("provider_type", "")),
            label=str(d.get("label", "")), secret_ref=str(d.get("secret_ref", "")),
            model=str(d.get("model", "")), enabled=bool(d.get("enabled", False)),
            endpoint=str(d.get("endpoint", "") or ""), api_version=str(d.get("api_version", "") or ""),
            priority=d.get("priority", 50), weight=d.get("weight", 10),
            daily_request_cap=d.get("daily_request_cap", 0), daily_token_cap=d.get("daily_token_cap", 0),
            rpm_soft_cap=d.get("rpm_soft_cap", 0), tpm_soft_cap=d.get("tpm_soft_cap", 0),
            workloads=tuple(d.get("workloads") or ()),
            price_in_micro_per_mtok=d.get("price_in_micro_per_mtok", 0),
            price_out_micro_per_mtok=d.get("price_out_micro_per_mtok", 0),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError([{"field": "slot", "message": "dữ liệu không đúng kiểu"}]) from exc


def slot_to_dict(s: ProviderSlot) -> Dict[str, Any]:
    return {"slot_id": s.slot_id, "provider_type": s.provider_type, "label": s.label,
            "secret_ref": s.secret_ref, "model": s.model, "enabled": s.enabled, "endpoint": s.endpoint,
            "api_version": s.api_version, "priority": s.priority, "weight": s.weight,
            "daily_request_cap": s.daily_request_cap, "daily_token_cap": s.daily_token_cap,
            "rpm_soft_cap": s.rpm_soft_cap, "tpm_soft_cap": s.tpm_soft_cap, "workloads": list(s.workloads),
            "price_in_micro_per_mtok": s.price_in_micro_per_mtok,
            "price_out_micro_per_mtok": s.price_out_micro_per_mtok}


def controls_to_dict(c: GlobalControls) -> Dict[str, Any]:
    return {"ai_enabled": c.ai_enabled, "provider_types": dict(c.provider_types),
            "global_daily_request_cap": c.global_daily_request_cap,
            "global_daily_token_cap": c.global_daily_token_cap,
            "per_user_daily_request_cap": c.per_user_daily_request_cap,
            "per_user_daily_token_cap": c.per_user_daily_token_cap,
            "daily_cost_cap_micro_usd": c.daily_cost_cap_micro_usd,
            "max_output_tokens": c.max_output_tokens, "max_context_tokens": c.max_context_tokens,
            "mode_profiles": dict(c.mode_profiles), "web_search_profile": c.web_search_profile,
            "web_search_tool": c.web_search_tool, "version": c.version,
            "updated_by": c.updated_by, "updated_at": c.updated_at}


#: Fields of GlobalControls an admin may change through the API.
CONTROL_FIELDS: Tuple[str, ...] = (
    "ai_enabled", "global_daily_request_cap", "global_daily_token_cap", "per_user_daily_request_cap",
    "per_user_daily_token_cap", "daily_cost_cap_micro_usd", "max_output_tokens", "max_context_tokens",
    "mode_profiles", "web_search_profile", "web_search_tool",
)


def controls_with(c: GlobalControls, patch: Mapping[str, Any]) -> GlobalControls:
    unknown = [k for k in patch if k not in CONTROL_FIELDS]
    if unknown:
        raise ConfigValidationError([{"field": k, "message": "không được sửa qua API này"} for k in unknown])
    kw = dict(patch)
    if "mode_profiles" in kw:
        kw["mode_profiles"] = dict(kw["mode_profiles"] or {})
    return replace(c, **kw)
