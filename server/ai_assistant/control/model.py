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
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from server.llm_gateway.alibaba import THINKING_MODES, alibaba_endpoint_error

PROVIDER_TYPES: Tuple[str, ...] = ("gemini", "groq", "workers_ai", "qwen", "azure_openai", "openrouter", "alibaba")
PROVIDER_LABELS: Dict[str, str] = {
    "gemini": "Google Gemini", "groq": "Groq", "workers_ai": "Cloudflare Workers AI",
    "qwen": "Alibaba Qwen (DashScope, loại cũ — đã nghỉ hưu)", "azure_openai": "Azure OpenAI", "openrouter": "OpenRouter",
    "alibaba": "Alibaba Model Studio",
}
#: Loại provider chỉ chạy khi MÁY CHỦ được bật tường minh bằng biến môi trường (mặc định TẮT, đọc lỏng kiểu fail-closed:
#: gõ sai = tắt, không bao giờ làm sập khởi động). Không có cờ này thì không một request nào tới nhà cung cấp, bất kể cấu hình
#: trong `/admin/ai`: một phiên Owner bị chiếm cũng không tự bật được nó — cần đổi biến môi trường + khởi động lại.
#:
#: HAI CỔNG ĐỘC LẬP — bật cổng này KHÔNG mở cổng kia. `alibaba` (Model Studio, bộ adapter mới) và `qwen` (loại DashScope CŨ, đã
#: nghỉ hưu khỏi hồ sơ mặc định) cùng đi tới Alibaba nhưng là hai đường khác nhau; một lần canary Model Studio không được vô tình
#: đánh thức đường cũ. Đường quay về `qwen` là một thao tác tường minh: `FAS_AI_QWEN_LEGACY_ENABLED=1` rồi tự đặt bước `qwen`
#: vào hồ sơ (`LEGACY_QWEN_PROFILE_STEPS` giữ nguyên thứ tự cũ).
GATED_PROVIDER_TYPES: Dict[str, str] = {"alibaba": "FAS_AI_ALIBABA_ENABLED", "qwen": "FAS_AI_QWEN_LEGACY_ENABLED"}
#: Slot của các loại này luôn được TẠO ở trạng thái tắt; bật bằng một thao tác riêng, sau khi Kiểm tra.
CREATED_DISABLED_TYPES: Tuple[str, ...] = ("alibaba",)
#: Loại provider mà MỌI dữ liệu bền (slot + bước định tuyến) nằm ở VÙNG LƯU TRỮ TÁCH BIỆT (`store.T_EXT`), không bao giờ trong
#: `ai_provider_slots` / `ai_routing_profiles`. Đó là cách DUY NHẤT để rút mã về bản cũ mà không làm hỏng Gemini: bản cũ không
#: biết loại này và coi một dòng lạ trong các collection nó đọc là "cấu hình hỏng" → tắt AI của mọi người; collection mới thì
#: bản cũ không bao giờ đọc. Xem docs/ai/ALIBABA_PROVIDER.md, mục "Rút lui".
EXT_PROVIDER_TYPES: Tuple[str, ...] = ("alibaba",)

#: Tầng năng lực của một model (KHÔNG phải tên model, KHÔNG phải gói đăng ký của người dùng): gói/tính năng sau này ánh xạ
#: tới TẦNG, còn slot nào phục vụ tầng nào là cấu hình của Owner. `tiers` rỗng = slot cũ chưa phân loại (phục vụ lượt chat
#: thường, không bao giờ được chọn khi một tầng cụ thể được yêu cầu).
CAPABILITY_TIERS: Tuple[str, ...] = ("FAST", "SMART", "ADVANCED", "TRANSLATION", "VISION", "EMBEDDING")
#: Tầng mà đường CHAT (`/chat/completions`) phục vụ được; EMBEDDING dùng một API khác nên slot chỉ-embedding không bao giờ
#: nhận lượt chat.
CHAT_TIERS: Tuple[str, ...] = ("FAST", "SMART", "ADVANCED", "TRANSLATION", "VISION")
MAX_QUOTA = 10 ** 12
#: Loại provider có chế độ `thinking` của slot (`THINKING_MODES`: provider_default | off | on). Loại khác CHỈ nhận `provider_default`
#: (không có gì để điều khiển, và một giá trị khác sẽ im lặng không có tác dụng). Cấu hình theo LOẠI, không theo tên model:
#: model nào cần chế độ nào là lựa chọn của Owner trên từng slot.
THINKING_TYPES: Tuple[str, ...] = ("alibaba",)
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

#: Hồ sơ mặc định. Loại `qwen` (DashScope cũ) ĐÃ NGHỈ HƯU khỏi đây: không còn đường mặc định nào tới Alibaba, nên một slot
#: `qwen` lỡ được bật cũng không nhận lượt nào cho tới khi Owner tự đặt bước. Production không có slot `qwen`, nên hành vi
#: định tuyến của Gemini không đổi (có test so từng chế độ).
DEFAULT_PROFILE_STEPS: Dict[str, Tuple[str, ...]] = {
    "FREE_FIRST": ("gemini", "groq", "workers_ai", "openrouter"),
    "QUALITY_FIRST": ("azure_openai", "gemini", "openrouter"),
    "WRITER": ("azure_openai", "gemini"),
    "STORY": ("gemini", "groq"),
    # Gemini ở CUỐI: provider ưu tiên cũ vẫn đứng trước khi được bật, còn khi chỉ có pool
    # Gemini thì chế độ Hỗ trợ không bao giờ rơi vào `ai_no_provider` (beta 2026-10).
    "SUPPORT_SAFE": ("azure_openai", "gemini"),
    "WEB_SEARCH": ("gemini",),
}
#: ĐƯỜNG QUAY VỀ: đúng thứ tự mặc định TRƯỚC khi `qwen` nghỉ hưu. Không bao giờ được áp tự động — Owner đặt chúng bằng
#: `PUT /api/admin/ai/profiles/<tên>` (vẫn hợp lệ vì `qwen` còn trong `PROVIDER_TYPES`) VÀ phải mở cổng
#: `FAS_AI_QWEN_LEGACY_ENABLED=1`; thiếu một trong hai thì `qwen` không nhận request nào.
LEGACY_QWEN_PROFILE_STEPS: Dict[str, Tuple[str, ...]] = {
    "FREE_FIRST": ("gemini", "groq", "workers_ai", "qwen", "openrouter"),
    "QUALITY_FIRST": ("qwen", "azure_openai", "gemini", "openrouter"),
    "WRITER": ("qwen", "azure_openai", "gemini"),
    "STORY": ("gemini", "groq", "qwen"),
    "SUPPORT_SAFE": ("azure_openai", "qwen", "gemini"),
    "WEB_SEARCH": ("gemini", "qwen"),
}
DEFAULT_MODE_PROFILES: Dict[str, str] = {
    "general": "FREE_FIRST", "story": "STORY", "writer": "WRITER", "support": "SUPPORT_SAFE",
}

#: 2-27 chars: the daily usage document id is ``{slot_id}_{yyyymmdd}`` and an
#: Appwrite document id is at most 36 chars (27 + 1 + 8). A longer id would make
#: every usage write fail and the slot's caps silently read as 0.
SLOT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,26}$")
MAX_ENDPOINT_LEN = 300  # ai_provider_slots.endpoint attribute size
SECRET_REF_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9._:/@-]{1,120}$")
API_VERSION_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}(-preview)?$")
MAX_SLOTS = 40
#: Trần RIÊNG cho slot của vùng tách biệt (Alibaba) — không tính vào `MAX_SLOTS` của các collection cũ, để Alibaba không chặn việc
#: tạo slot Gemini (và ngược lại). 20 slot + 6 dòng route luôn nhỏ hơn một trang đọc (100 dòng).
MAX_EXT_SLOTS = 20
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
    #: Siêu dữ liệu TUỲ CHỌN (lưu chung một thuộc tính `meta_json`, chỉ ghi khi có giá trị — xem `slot_meta`).
    #: Tầng năng lực mà slot phục vụ (`CAPABILITY_TIERS`); rỗng = chưa phân loại.
    tiers: Tuple[str, ...] = ()
    #: Số dư hạn mức MIỄN PHÍ (token) do Owner nhập theo trang Model Studio — một ẢNH CHỤP, không tự cập nhật; None = không biết.
    free_quota_remaining: Optional[int] = None
    #: Hạn dùng của hạn mức miễn phí (ISO-8601 có múi giờ, chuẩn hoá về UTC); "" = không đặt.
    free_quota_expires_at: str = ""
    #: True = KHÔNG BAO GIỜ dùng slot khi hết/quá hạn/không biết hạn mức miễn phí (không để phát sinh phí).
    free_quota_only: bool = False
    #: Do MÁY CHỦ đóng dấu mỗi khi `free_quota_remaining` đổi (client không đặt được).
    free_quota_updated_at: str = ""
    #: Chế độ suy luận (thinking) của model — `THINKING_MODES`. `provider_default` = KHÔNG gửi gì (model tự quyết). Chỉ loại trong
    #: `THINKING_TYPES` mới nhận giá trị khác; với slot Alibaba nó nằm trong payload của dòng ở vùng tách biệt (bản cũ không đọc).
    thinking: str = "provider_default"
    #: Chỉ khi chạy: dòng của kho KHÔNG dùng được — `meta_json` hỏng, hoặc (loại ở vùng tách biệt) cấu hình lưu của slot không qua
    #: được kiểm tra. Không lưu, không bao giờ làm cả cấu hình hỏng — chỉ slot này bị bỏ qua (đỗ lại), Gemini không đổi.
    meta_corrupt: bool = False

    def effective_endpoint(self) -> str:
        return self.endpoint or DEFAULT_ENDPOINTS.get(self.provider_type, "")


@dataclass(frozen=True)
class RoutingProfile:
    name: str
    steps: Tuple[str, ...]
    enabled: bool = True
    #: Chỉ khi chạy: `updated_at` của dòng `ai_routing_profiles` (cột đã có sẵn ở production, mã cũ cũng ghi nó mỗi lần lưu). Dùng làm
    #: DẤU của lần ghi: một dòng Alibaba chỉ được áp khi mang đúng dấu này (xem `compose_profile`). Không bao giờ do client đặt.
    updated_at: str = ""


@dataclass(frozen=True)
class ExtRoute:
    """Dòng `r-<hồ sơ>` của vùng tách biệt: danh sách bước ĐẦY ĐỦ (kể cả bước Alibaba) + dấu của lần ghi hồ sơ mà nó đi kèm."""
    steps: Tuple[str, ...]
    stamp: str = ""


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


#: Trạng thái VÙNG LƯU TRỮ TÁCH BIỆT của các loại `EXT_PROVIDER_TYPES` (không lưu — chỉ để HIỂN THỊ ở /admin/ai):
#:   none           = chưa đọc (cấu hình rỗng/đóng) · empty = đọc được, chưa có gì · ok = có dữ liệu dùng được
#:   schema_missing = chưa chạy migration (collection chưa có) · unavailable = kho không đọc được lúc này
EXT_STATES: Tuple[str, ...] = ("none", "empty", "ok", "schema_missing", "unavailable")


@dataclass(frozen=True)
class ExtStatus:
    state: str = "none"
    #: Số dòng không đọc được hẳn (JSON hỏng, sai kiểu, trùng id…) — chỉ ĐẾM, không bao giờ kèm nội dung dòng.
    unreadable: int = 0
    #: Tên hồ sơ có bước Alibaba bị BỎ vì không còn khớp phần hồ sơ mà bản cũ đọc (xem `compose_profiles`).
    stale_routes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ControlConfig:
    controls: GlobalControls
    slots: Dict[str, ProviderSlot]
    profiles: Dict[str, RoutingProfile]
    ext: ExtStatus = field(default_factory=ExtStatus)


def is_ext_step(step: str, slots: Mapping[str, ProviderSlot]) -> bool:
    """Bước hồ sơ thuộc vùng tách biệt: một loại `EXT_PROVIDER_TYPES` hoặc id của một slot thuộc loại đó.

    PHẢI giải một chuỗi bước giống hệt `router.plan`: TÊN LOẠI thắng id slot (`step in PROVIDER_TYPES` được xét trước). Nếu không,
    một slot Alibaba tên `gemini` sẽ khiến bước `gemini` bị coi là của Alibaba và bị tách khỏi hồ sơ bản cũ đọc — Gemini mất khỏi
    hồ sơ khi vùng tách biệt không đọc được hoặc sau khi rút mã. (Id slot trùng tên loại còn bị từ chối lúc tạo.)"""
    if step in PROVIDER_TYPES:
        return step in EXT_PROVIDER_TYPES
    s = slots.get(step)
    return s is not None and s.provider_type in EXT_PROVIDER_TYPES


def split_steps(steps: Tuple[str, ...], slots: Mapping[str, ProviderSlot]) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """(phần bản CŨ đọc được, phần Alibaba) của một danh sách bước, giữ nguyên thứ tự."""
    legacy = tuple(s for s in steps if not is_ext_step(s, slots))
    return legacy, tuple(s for s in steps if is_ext_step(s, slots))


def sanitize_core(cfg: ControlConfig) -> ControlConfig:
    """Loại MỌI thứ của vùng tách biệt khỏi cấu hình đọc từ các collection CŨ (`ai_provider_slots`, `ai_routing_profiles`).

    Mã mới không bao giờ ghi chúng ở đó — nếu vẫn thấy (sửa tay, hoặc một bản nháp cũ) thì dòng bị BỎ QUA và chỉ được ĐẾM
    (`ext.unreadable`), không bao giờ định tuyến. Vừa an toàn hơn (đường tới Alibaba chỉ có MỘT) vừa không làm hỏng Gemini: một
    bước hồ sơ trỏ vào slot Alibaba đã bị loại sẽ là "slot không tồn tại" → cả cấu hình bị coi là hỏng → AI tắt cho mọi người."""
    slots = {k: v for k, v in cfg.slots.items() if v.provider_type not in EXT_PROVIDER_TYPES}
    gone = set(cfg.slots) - set(slots)
    profiles: Dict[str, RoutingProfile] = {}
    touched = len(gone)
    for n, p in cfg.profiles.items():
        steps = tuple(s for s in p.steps if s not in EXT_PROVIDER_TYPES and s not in gone)
        if steps != tuple(p.steps):
            touched += 1
            p = replace(p, steps=steps)
        profiles[n] = p
    if not touched:
        return cfg
    return replace(cfg, slots=slots, profiles=profiles, ext=replace(cfg.ext, unreadable=cfg.ext.unreadable + touched))


def same_second(a: str, b: str) -> bool:
    """Hai mốc ISO-8601 có múi giờ trùng nhau tới GIÂY (Appwrite trả `…:12.000+00:00`, ta ghi `…:12+00:00`). Rỗng/sai → False."""
    try:
        na, nb = normalize_timestamp(a) if a else None, normalize_timestamp(b) if b else None
    except Exception:  # noqa: BLE001 — defence in depth: a comparison on stored text must never raise into a config load
        return False
    return na is not None and na == nb


def compose_profile(base: RoutingProfile, route: Optional[ExtRoute], slots: Mapping[str, ProviderSlot]) -> Tuple[RoutingProfile, bool]:
    """Hồ sơ HIỆU LỰC = hồ sơ bản cũ đọc được (`base`) + bước Alibaba của vùng tách biệt (`route`, danh sách ĐẦY ĐỦ).

    Một `route` chỉ được áp khi, đồng thời: (1) mang đúng DẤU của dòng hồ sơ cũ (`route.stamp` = `base.updated_at`, tới giây) — bất
    kỳ lần ghi nào của dòng hồ sơ cũ sau đó (bản cũ sau khi rút mã, hoặc bản mới sửa hồ sơ lúc vùng tách biệt không đọc được/không
    xoá được dòng) đổi dấu và làm dòng Alibaba MỒ CÔI VĨNH VIỄN — kể cả khi các bước sau đó tình cờ trùng lại; (2) nó KHỚP đúng
    `base` (bỏ các bước Alibaba thì phải ra đúng `base.steps`); (3) mọi bước hợp lệ, không lặp, vừa trần bước. Không đạt thì `route`
    bị BỎ và hồ sơ chạy như bản cũ đọc: bước Alibaba không bao giờ ghi đè một thay đổi về Gemini. (Quy tắc "Alibaba không là đường
    DUY NHẤT của hồ sơ" được thi hành lúc GHI — `ControlPlane.update_profile` — vì API là thứ duy nhất tạo ra dòng này.)
    Trả (hồ sơ, đã áp?)."""
    if route is None or not same_second(route.stamp, base.updated_at):
        return base, False
    steps = tuple(route.steps)
    legacy, _ext = split_steps(steps, slots)
    ok = (legacy == base.steps and len(set(steps)) == len(steps) and len(steps) <= MAX_STEPS
          and all(s in PROVIDER_TYPES or s in slots for s in steps))
    return (replace(base, steps=steps), True) if ok else (base, False)


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
        if provider_type in ("workers_ai", "azure_openai", "alibaba"):
            return "bắt buộc với loại provider này"
        return None
    if len(endpoint) > MAX_ENDPOINT_LEN:
        return f"tối đa {MAX_ENDPOINT_LEN} ký tự"
    if provider_type == "alibaba":
        # Không đoán vùng/endpoint: Owner nhập đúng endpoint tài khoản dùng; chỉ kiểm họ máy chủ DashScope (không phải mọi
        # dịch vụ *.aliyuncs.com) để khoá API không bao giờ gửi tới một tên miền do khách hàng khác chọn.
        return alibaba_endpoint_error(endpoint)
    try:
        u = urlsplit(endpoint)
        port = u.port  # raises ValueError for a non-numeric port
    except ValueError:
        return "URL không hợp lệ"
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment:
        return "chỉ nhận https://host/đường-dẫn (không user, query hay fragment)"
    if port not in (None, 443):
        return "chỉ cổng 443"
    host = u.hostname.lower()
    allowed = ENDPOINT_HOSTS.get(provider_type, ())
    if not any(host == a or (a.startswith(".") and host.endswith(a)) for a in allowed):
        return f"máy chủ không nằm trong danh sách cho phép của {provider_type}"
    if provider_type == "workers_ai" and not u.path.startswith("/client/v4/accounts/"):
        return "phải có dạng /client/v4/accounts/<account_id>/ai/v1"
    return None


def secret_ref_prefix(provider_type: str) -> str:
    """`gemini` -> `GEMINI_`, `azure_openai` -> `AZURE_OPENAI_`."""
    return provider_type.upper() + "_"


def validate_slot(slot: ProviderSlot) -> None:
    e: List[Dict[str, str]] = []
    if not SLOT_ID_RE.match(slot.slot_id or ""):
        e.append({"field": "slot_id", "message": "2–27 ký tự a-z, 0-9, '-', '_' (bắt đầu bằng chữ/số)"})
    if slot.provider_type not in PROVIDER_TYPES:
        e.append({"field": "provider_type", "message": "loại provider không hỗ trợ"})
    if not (slot.label or "").strip() or len(slot.label) > 60:
        e.append({"field": "label", "message": "1–60 ký tự"})
    if not SECRET_REF_RE.match(slot.secret_ref or ""):
        e.append({"field": "secret_ref", "message": "TÊN tham chiếu (A-Z, 0-9, '_', 3–64 ký tự) — không phải khoá"})
    elif slot.provider_type in PROVIDER_TYPES and not slot.secret_ref.startswith(secret_ref_prefix(slot.provider_type)):
        # A key is bound to its provider type: a Gemini key can never be sent to
        # an Azure (or any other type's) endpoint by re-pointing a slot.
        e.append({"field": "secret_ref",
                  "message": f"phải bắt đầu bằng {secret_ref_prefix(slot.provider_type)} (khoá gắn với loại provider)"})
    if not MODEL_RE.match(slot.model or "") or ".." in (slot.model or ""):
        e.append({"field": "model", "message": "1–120 ký tự A-Z a-z 0-9 . _ : / @ - (không có '..')"})
    elif slot.provider_type == "azure_openai" and "/" in slot.model:
        e.append({"field": "model", "message": "tên deployment Azure không chứa '/'"})
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
    e.extend(_meta_errors(slot))
    if slot.thinking not in THINKING_MODES:
        e.append({"field": "thinking", "message": "chọn một trong: " + ", ".join(THINKING_MODES)})
    elif slot.thinking != "provider_default" and slot.provider_type not in THINKING_TYPES:
        e.append({"field": "thinking", "message": "loại provider này không có chế độ thinking — để provider_default"})
    if e:
        raise ConfigValidationError(e)


def _meta_errors(slot: ProviderSlot) -> List[Dict[str, str]]:
    """Lỗi của các trường siêu dữ liệu tuỳ chọn — dùng cho API (báo theo trường) VÀ khi tải từ kho (hỏng = chỉ slot đó bị bỏ qua)."""
    e: List[Dict[str, str]] = []
    tiers = tuple(slot.tiers or ())
    if any(not isinstance(t, str) or t not in CAPABILITY_TIERS for t in tiers) or len(set(tiers)) != len(tiers):
        e.append({"field": "tiers", "message": "chỉ chọn trong " + ", ".join(CAPABILITY_TIERS) + ", không lặp"})
    q = slot.free_quota_remaining
    if q is not None and (isinstance(q, bool) or not isinstance(q, int) or not 0 <= q <= MAX_QUOTA):
        e.append({"field": "free_quota_remaining", "message": f"để trống hoặc số nguyên 0–{MAX_QUOTA} (token)"})
    for name in ("free_quota_expires_at", "free_quota_updated_at"):
        raw = getattr(slot, name)
        if raw and normalize_timestamp(raw) is None:
            e.append({"field": name, "message": "thời điểm ISO-8601 có múi giờ, ví dụ 2026-12-31T00:00:00+00:00"})
    if not isinstance(slot.free_quota_only, bool):
        e.append({"field": "free_quota_only", "message": "phải là true/false"})
    elif slot.free_quota_only and q is None:
        # Khoá an toàn "chỉ dùng hạn mức miễn phí" cần có số liệu để thi hành: không biết số dư thì không được phép dùng.
        e.append({"field": "free_quota_remaining",
                  "message": "cần nhập số dư hạn mức miễn phí khi bật 'chỉ dùng hạn mức miễn phí'"})
    return e


def normalize_timestamp(raw: str) -> Optional[str]:
    """ISO-8601 CÓ múi giờ -> chuỗi UTC chuẩn (`2026-12-31T00:00:00+00:00`), hoặc None nếu không hợp lệ/không có múi giờ."""
    try:
        t = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
        if t.tzinfo is None:
            return None
        # `astimezone` raises OverflowError for an instant that is out of range once moved to UTC (e.g. `0001-01-01T00:00:00+05:00`):
        # a hostile/garbled stamp must read as "invalid", never as an exception out of a config load.
        return t.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        return None


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
    # Khoá THIẾU = tắt (một cấu hình do bản cũ ghi, chưa biết loại provider mới, vẫn hợp lệ và loại mới tự tắt); khoá LẠ = lỗi.
    if not set(c.provider_types) <= set(PROVIDER_TYPES) or any(not isinstance(v, bool) for v in c.provider_types.values()):
        e.append({"field": "provider_types", "message": "chỉ gồm các loại " + ", ".join(PROVIDER_TYPES) + " với giá trị true/false"})
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


def _strict_bool(v: Any) -> bool:
    """`bool("false")` is True — a JSON body must carry a real boolean."""
    if not isinstance(v, bool):
        raise ConfigValidationError([{"field": "enabled", "message": "phải là true/false"}])
    return v


def slot_from_dict(d: Mapping[str, Any]) -> ProviderSlot:
    """From an API body or stored row. Unknown keys are ignored; missing keys
    take the dataclass default. Raises ConfigValidationError on bad types."""
    try:
        return ProviderSlot(
            slot_id=str(d.get("slot_id", "")), provider_type=str(d.get("provider_type", "")),
            label=str(d.get("label", "")), secret_ref=str(d.get("secret_ref", "")),
            model=str(d.get("model", "")), enabled=_strict_bool(d.get("enabled", False)),
            endpoint=str(d.get("endpoint", "") or ""), api_version=str(d.get("api_version", "") or ""),
            priority=d.get("priority", 50), weight=d.get("weight", 10),
            daily_request_cap=d.get("daily_request_cap", 0), daily_token_cap=d.get("daily_token_cap", 0),
            rpm_soft_cap=d.get("rpm_soft_cap", 0), tpm_soft_cap=d.get("tpm_soft_cap", 0),
            workloads=tuple(d.get("workloads") or ()),
            price_in_micro_per_mtok=d.get("price_in_micro_per_mtok", 0),
            price_out_micro_per_mtok=d.get("price_out_micro_per_mtok", 0),
            tiers=tuple(t.strip().upper() if isinstance(t, str) else t for t in (d.get("tiers") or ())),
            free_quota_remaining=_opt_int(d.get("free_quota_remaining")),
            free_quota_expires_at=_ts(d.get("free_quota_expires_at")),
            free_quota_only=_flag(d.get("free_quota_only", False), "free_quota_only"),
            free_quota_updated_at=_ts(d.get("free_quota_updated_at")),
            thinking=_thinking(d.get("thinking")),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError([{"field": "slot", "message": "dữ liệu không đúng kiểu"}]) from exc


def _opt_int(v: Any) -> Optional[int]:
    """None / "" = không đặt; số nguyên (kể cả số trong chuỗi) = giá trị; còn lại giữ nguyên để `validate_slot` báo đúng trường."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, str) and re.fullmatch(r"-?\d{1,15}", v.strip()):
        return int(v.strip())
    return v


def _thinking(v: Any) -> str:
    """Thiếu/rỗng = `provider_default` (một dòng do bản cũ ghi chưa có trường này); chuỗi được chuẩn hoá chữ thường; kiểu khác giữ
    nguyên để `validate_slot` báo đúng trường."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return "provider_default"
    return v.strip().lower() if isinstance(v, str) else v


def _ts(v: Any) -> str:
    raw = "" if v is None else str(v).strip()
    return (normalize_timestamp(raw) or raw) if raw else ""


def _flag(v: Any, name: str) -> bool:
    if not isinstance(v, bool):
        raise ConfigValidationError([{"field": name, "message": "phải là true/false"}])
    return v


#: Các trường siêu dữ liệu tuỳ chọn (lưu chung `meta_json`) và giá trị mặc định = "không có gì để ghi".
META_FIELDS: Tuple[str, ...] = ("tiers", "free_quota_remaining", "free_quota_expires_at", "free_quota_only",
                                "free_quota_updated_at")


def slot_meta(s: ProviderSlot) -> Dict[str, Any]:
    """CHỈ các trường siêu dữ liệu khác mặc định. Rỗng ({}) = slot không mang siêu dữ liệu nào -> kho KHÔNG ghi `meta_json`,
    nên ghi một slot thường (vd. Gemini) giữ nguyên từng byte như trước khi có siêu dữ liệu — một thuộc tính mà production
    chưa có sẽ làm MỌI lần ghi slot thất bại (kể cả tắt khẩn cấp)."""
    out: Dict[str, Any] = {}
    if s.tiers:
        out["tiers"] = list(s.tiers)
    if s.free_quota_remaining is not None:
        out["free_quota_remaining"] = s.free_quota_remaining
    if s.free_quota_expires_at:
        out["free_quota_expires_at"] = s.free_quota_expires_at
    if s.free_quota_only:
        out["free_quota_only"] = True
    if s.free_quota_updated_at:
        out["free_quota_updated_at"] = s.free_quota_updated_at
    return out


def slot_with_meta(s: ProviderSlot, meta: Mapping[str, Any]) -> ProviderSlot:
    """Áp `meta_json` đã giải mã lên slot; bất kỳ kiểu sai nào ném ValueError/TypeError (người gọi đánh dấu `meta_corrupt`)."""
    if not isinstance(meta, Mapping):
        raise TypeError("meta_json is not an object")
    tiers = meta.get("tiers") or ()
    if not isinstance(tiers, (list, tuple)) or any(not isinstance(t, str) for t in tiers):
        raise TypeError("tiers")
    q = meta.get("free_quota_remaining")
    if q is not None and (isinstance(q, bool) or not isinstance(q, int)):
        raise TypeError("free_quota_remaining")
    exp, upd = meta.get("free_quota_expires_at") or "", meta.get("free_quota_updated_at") or ""
    if not isinstance(exp, str) or not isinstance(upd, str) or not isinstance(meta.get("free_quota_only", False), bool):
        raise TypeError("meta field type")
    out = replace(s, tiers=tuple(tiers), free_quota_remaining=q, free_quota_expires_at=exp,
                  free_quota_only=bool(meta.get("free_quota_only", False)), free_quota_updated_at=upd)
    if _meta_errors(out):  # giá trị sai/không nhất quán: coi như hỏng (slot bị bỏ qua), KHÔNG làm cả cấu hình hỏng
        raise ValueError("meta_json invalid")
    return out


def slot_to_dict(s: ProviderSlot) -> Dict[str, Any]:
    return {"slot_id": s.slot_id, "provider_type": s.provider_type, "label": s.label,
            "secret_ref": s.secret_ref, "model": s.model, "enabled": s.enabled, "endpoint": s.endpoint,
            "api_version": s.api_version, "priority": s.priority, "weight": s.weight,
            "daily_request_cap": s.daily_request_cap, "daily_token_cap": s.daily_token_cap,
            "rpm_soft_cap": s.rpm_soft_cap, "tpm_soft_cap": s.tpm_soft_cap, "workloads": list(s.workloads),
            "price_in_micro_per_mtok": s.price_in_micro_per_mtok,
            "price_out_micro_per_mtok": s.price_out_micro_per_mtok,
            "tiers": list(s.tiers), "free_quota_remaining": s.free_quota_remaining,
            "free_quota_expires_at": s.free_quota_expires_at, "free_quota_only": s.free_quota_only,
            "free_quota_updated_at": s.free_quota_updated_at, "thinking": s.thinking}


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


#: Rollout presets — named cap bundles the owner applies in one audited step
#: (`PUT /api/admin/ai/presets/{name}`). They set ONLY these budget fields: never
#: `ai_enabled` (the emergency kill switch stays independent and always wins),
#: never routing, profiles, slots or the audience. Every value is still editable
#: one by one afterwards; the config view reports which preset (if any) matches.
#:   canary — owner-only canary values in use since 2026-10-01
#:   beta   — public-beta proposal: 5 requests / user / day, 150 / day overall
PRESET_FIELDS: Tuple[str, ...] = (
    "per_user_daily_request_cap", "per_user_daily_token_cap", "global_daily_request_cap",
    "global_daily_token_cap", "max_output_tokens", "max_context_tokens",
)
ROLLOUT_PRESETS: Dict[str, Dict[str, int]] = {
    "canary": {"per_user_daily_request_cap": 20, "per_user_daily_token_cap": 40_000,
               "global_daily_request_cap": 40, "global_daily_token_cap": 80_000,
               "max_output_tokens": 400, "max_context_tokens": 4000},
    "beta": {"per_user_daily_request_cap": 5, "per_user_daily_token_cap": 15_000,
             "global_daily_request_cap": 150, "global_daily_token_cap": 450_000,
             "max_output_tokens": 400, "max_context_tokens": 4000},
}


def preset_matching(c: GlobalControls) -> str:
    """Name of the preset the current caps equal exactly, else "custom"."""
    for name, values in ROLLOUT_PRESETS.items():
        if all(getattr(c, k) == v for k, v in values.items()):
            return name
    return "custom"


def controls_with(c: GlobalControls, patch: Mapping[str, Any]) -> GlobalControls:
    unknown = [k for k in patch if k not in CONTROL_FIELDS]
    if unknown:
        raise ConfigValidationError([{"field": k, "message": "không được sửa qua API này"} for k in unknown])
    kw = dict(patch)
    if "mode_profiles" in kw:
        mp = kw["mode_profiles"] or {}
        if not isinstance(mp, Mapping) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in mp.items()):
            raise ConfigValidationError([{"field": "mode_profiles", "message": "phải là object {chế độ: hồ sơ}"}])
        kw["mode_profiles"] = dict(mp)
    return replace(c, **kw)
