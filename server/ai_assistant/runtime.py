"""
Assembles the AI Assistant runtime from `Settings` — same role as
`server/messaging/runtime.py::build_runtime`: the ONE place that picks
storage backend + provider set for the environment actually running.
"""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Optional, Tuple

from server.ai_assistant.config import resolve_provider_chain
from server.ai_assistant.ephemeral import EphemeralConversationStore
from server.ai_assistant.gateway import AiGateway
from server.ai_assistant.limits import QA_LEDGER_PREFIX, RpmLimiter, StreamGuard, qa_ledger_user
from server.ai_assistant.memory import AiRepo, AiUnavailable, AppwriteAiRepo, InMemoryAiRepo
from server.ai_assistant.tools import ToolContext
from server.llm_gateway.chat_providers import (
    AzureOpenAIProvider, MockChatProvider, QwenDashScopeProvider, TencentCompatProvider,
)
from server.llm_gateway.chat_provider import ChatProvider, ProviderError

log = logging.getLogger("fanfic.ai_assistant")


@dataclass
class AiRuntime:
    enabled: bool
    reason: str = ""
    repo: Optional[AiRepo] = None
    #: `memory_enabled=false` destination (contract §5) — NEVER durable,
    #: NEVER touched when memory is on. See `ephemeral.py`'s own docstring.
    ephemeral: EphemeralConversationStore = field(default_factory=EphemeralConversationStore)
    #: `AiGateway` (env-configured chain) or `ControlledGateway` (control plane).
    gateway: Optional[Any] = None
    #: Control plane (`FAS_AI_ADMIN_V1`): admission caps, kill switch, per-slot
    #: usage. `None` = legacy env-configured behaviour.
    control: Optional[Any] = None
    tool_ctx: ToolContext = field(default_factory=ToolContext)
    rpm_limiter: RpmLimiter = field(default_factory=RpmLimiter)
    stream_guard: StreamGuard = field(default_factory=lambda: StreamGuard(max_streams_per_instance=4))
    assistant_name: str = "Fanfic AI"
    daily_tokens_free: int = 30000
    daily_tokens_premium: int = 200000
    rpm: int = 8
    web_search_enabled: bool = False
    #: Giay im lang toi da truoc khi luong SSE gui mot dong chu thich
    #: `: ping` (xem `stream_pump.py`). Settings kep vao [15, 25]; bai test
    #: dat truc tiep gia tri nho de chay nhanh va tat dinh.
    heartbeat_s: float = 15.0
    #: M8 (review finding): HMAC-SHA256 key for `routes.py::_hashed_user_ref`
    #: — never the raw user id is sent to a provider as `user_ref`. Sourced
    #: from `settings.ai_assistant.user_ref_salt` (`FAS_AI_USER_REF_SALT`)
    #: when configured; falls back to a per-process random salt (documented
    #: here, not silently — a random salt still satisfies "never the raw
    #: id", it just means the same user hashes to a DIFFERENT `user_ref` on
    #: a restart, which is fine: this value is abuse-tracking-only, never
    #: looked up by us, never persisted).
    user_ref_salt: str = field(default_factory=lambda: secrets.token_hex(32))
    #: Khan gia (`AiAssistantSettings.resolved_audience`): "all" | "beta" | "canary".
    #: "canary"/"beta" -> CHI `audience_users` (Owner + `FAS_AI_CANARY_USERS`, beta them
    #: `FAS_AI_BETA_USERS`) dung duoc `/api/ai/*`; nguoi khac: availability
    #: `enabled:false`, `/api/ai/access` `eligible:false`, route khac 403.
    audience: str = "all"
    audience_users: FrozenSet[str] = field(default_factory=frozenset)
    #: Owner (`FAS_OWNER_USER_IDS`): CHỈ họ được dùng lần QA (`qa: true` trong thân lượt gửi). Server-side,
    #: không bao giờ ra client. Người khác gửi `qa: true` thì cờ bị BỎ QUA (lượt tính như lượt thường).
    owner_users: FrozenSet[str] = field(default_factory=frozenset)
    #: Trần lượt QA mỗi ngày của MỖI Owner, tách khỏi hạn mức người dùng thường (0 = đóng lối QA).
    owner_qa_daily_requests: int = 20

    def allows(self, user_id: str) -> bool:
        # Tiền tố của khoá sổ QA (`limits.qa_ledger_user`) là của riêng sổ đó: id tài khoản thật do Appwrite sinh
        # (`unique()`) nên không bao giờ mang nó, nhưng nếu có thì KHÔNG được vào, kẻo dùng chung sổ QA của Owner.
        if user_id and user_id.startswith(QA_LEDGER_PREFIX):
            return False
        return self.audience == "all" or (bool(user_id) and user_id in self.audience_users)

    def is_owner(self, user_id: str) -> bool:
        return bool(user_id) and user_id in self.owner_users

    def qa_lane(self, user_id: str, requested: bool) -> bool:
        """Lượt này đi lối QA? Cần ĐỦ ba điều kiện: người gọi xin (`qa: true`), người gọi là Owner, và control
        plane đang bật (lối QA dùng hạn mức của control plane; ở chế độ cũ `FAS_AI_PROVIDERS` thì không có)."""
        return bool(requested) and self.control is not None and self.is_owner(user_id)

    def serving(self) -> bool:
        """Runtime dựng xong và phục vụ được (cờ bật, khán giả hợp lệ, có repo + gateway)."""
        return self.enabled and self.repo is not None and self.gateway is not None

    def access_state(self, user_id: str) -> str:
        """NGUỒN DUY NHẤT cho câu hỏi "người này dùng được Trợ lý AI LÚC NÀY không":
        `ok` | `off` | `not_in_audience` | `disabled_by_admin`. Availability và `/api/ai/access`
        đều đọc từ đây. Các route còn lại vẫn TỰ chặn ở mọi request bằng chính `serving()` +
        `allows()` (`routes._bat`/`_profile`); tắt khẩn cấp thì lượt gửi bị chặn ở admission
        của control plane. UI có sai thì backend vẫn không mở."""
        if not self.serving():
            return "off"
        if not self.allows(user_id):
            return "not_in_audience"
        if self.control is not None and not self.control.enabled():
            return "disabled_by_admin"
        return "ok"

    def describe(self) -> dict:
        return {"enabled": self.enabled, "reason": self.reason or None,
                "name": self.assistant_name, "web_search": self.web_search_enabled}


def _build_provider(name: str, settings: Any) -> Optional[ChatProvider]:
    ai = settings.ai_assistant
    try:
        if name == "mock":
            # Do tre moi tu (ms) CHI cho provider mock — de dev/QA thu duoc nut Dung giua stream. Khong
            # anh huong provider that; gia tri hong/am -> 0.
            try:
                tre_ms = max(0.0, float(os.environ.get("FAS_AI_MOCK_DELAY_MS", "0") or 0))
            except ValueError:
                tre_ms = 0.0
            return MockChatProvider(delay_s=tre_ms / 1000.0)
        if name == "qwen":
            # DashScope IS Alibaba: chuỗi env cũ (khi control plane tắt) cũng đi qua cổng máy chủ `FAS_AI_ALIBABA_ENABLED` —
            # không có đường nào tới Alibaba mà thiếu bật tường minh.
            if not getattr(ai, "alibaba_enabled", False):
                log.info("ai_assistant: provider 'qwen' bị bỏ — cổng máy chủ FAS_AI_ALIBABA_ENABLED đang đóng.")
                return None
            return QwenDashScopeProvider(
                api_key=ai.qwen_api_key, base_url=ai.qwen_base_url, model=ai.qwen_model)
        if name == "azure_openai":
            return AzureOpenAIProvider(
                endpoint=ai.azure_openai_endpoint, api_key=ai.azure_openai_api_key,
                deployment=ai.azure_openai_deployment, api_version=ai.azure_openai_api_version)
        if name == "tencent":
            return TencentCompatProvider(
                api_key=ai.tencent_api_key, base_url=ai.tencent_base_url, model=ai.tencent_model)
    except ProviderError as exc:
        log.info("ai_assistant: provider '%s' không dựng được: %s", name, exc)
        return None
    return None


def build_ai_runtime(settings: Any, *, tool_ctx: Optional[ToolContext] = None,
                     control: Optional[Any] = None) -> AiRuntime:
    """`control` (the `/admin/ai` plane, `FAS_AI_ADMIN_V1`) REPLACES the
    env-configured provider chain: routing, kill switch and caps then come
    from the stored control config, and an absent/corrupt config means AI off
    (fail-closed) — `FAS_AI_PROVIDERS` and the `AI_*` keys are ignored."""
    ai = settings.ai_assistant
    #: Cả runtime TẮT cũng mang danh sách Owner: `/api/ai/availability` chỉ trả `reason` chi tiết (tên biến môi trường…)
    #: cho Owner, nên Owner phải nhận ra mình ngay cả khi AI đang tắt — nếu không chẩn đoán "vì sao tắt" mất hẳn.
    owners = frozenset(getattr(settings, "owner_user_ids", ()) or ())
    if not ai.enabled:
        return AiRuntime(False, reason="FAS_AI_ASSISTANT_V1 chưa bật", control=control, owner_users=owners)

    data_backend = str(getattr(settings, "data_backend", "mock")).lower()
    resolve_audience = getattr(ai, "resolved_audience", None)
    # Thieu `resolved_audience` (settings gia/cu) -> "" -> AI TAT: khong bao gio mo cong vi thieu cau hinh.
    audience = resolve_audience(data_backend) if callable(resolve_audience) else ""
    if not audience:
        # KHÔNG lặp lại giá trị env: `reason` đi ra client qua /api/ai/availability (review).
        return AiRuntime(False, reason="FAS_AI_AUDIENCE không hợp lệ "
                                       "(canary | beta | all; beta tối đa 50 ID trong FAS_AI_BETA_USERS)",
                         control=control, owner_users=owners)
    audience_users = (frozenset(getattr(settings, "owner_user_ids", ()) or ())
                      | frozenset(getattr(ai, "canary_users", ()) or ()))
    if audience == "beta":
        # beta MỞ RỘNG canary: Owner + canary + nhóm tester. `allows()` coi "beta" như mọi khán giả có danh sách.
        beta = frozenset(getattr(ai, "beta_users", ()) or ())
        if not beta:
            log.warning("ai_assistant: FAS_AI_AUDIENCE=beta nhưng FAS_AI_BETA_USERS rỗng — chỉ Owner/canary dùng được")
        audience_users |= beta

    if control is not None:
        from server.ai_assistant.control.router import ControlledGateway
        gateway: Any = ControlledGateway(control)
    else:
        chain = resolve_provider_chain(ai, environment=settings.environment)
        if not chain:
            return AiRuntime(False, reason="no_provider", owner_users=owners)

        providers: Dict[str, ChatProvider] = {}
        for name in chain:
            p = _build_provider(name, settings)
            if p is not None:
                providers[name] = p
        usable_chain = [n for n in chain if n in providers]
        if not usable_chain:
            return AiRuntime(False, reason="no_provider", owner_users=owners)

        gateway = AiGateway(providers=providers, provider_chain=usable_chain)

    if data_backend == "appwrite":
        try:
            repo: AiRepo = AppwriteAiRepo(settings)
        except AiUnavailable as exc:
            return AiRuntime(False, reason=f"appwrite_not_configured: {exc}", owner_users=owners)
    else:
        repo = InMemoryAiRepo()

    kwargs: Dict[str, Any] = {}
    if getattr(ai, "user_ref_salt", ""):
        kwargs["user_ref_salt"] = ai.user_ref_salt

    owner_users = owners
    owner_qa_daily_requests = max(0, int(getattr(ai, "owner_qa_daily_requests", 20)))
    stream_guard = StreamGuard(max_streams_per_instance=ai.max_streams)

    if control is not None:
        def _user_usage(user_id: str, day: str) -> Tuple[int, int]:
            u = repo.get_usage_day(user_id, day)
            return (u.requests, u.input_tokens + u.output_tokens) if u else (0, 0)

        def _active_users(day: str) -> Optional[int]:
            """Người dùng AI hoạt động = số dòng sổ hôm nay TRỪ các dòng sổ QA (khoá tổng hợp, không phải người)."""
            total = repo.count_usage_users(day)
            if total is None:
                return None
            qa_rows = sum(1 for o in sorted(owner_users) if repo.get_usage_day(qa_ledger_user(o), day) is not None)
            return max(0, total - qa_rows)

        def _qa_overview(day: str) -> Dict[str, Any]:
            used_req = used_tok = 0
            for o in sorted(owner_users):
                u = repo.get_usage_day(qa_ledger_user(o), day)
                if u is not None:
                    used_req += u.requests
                    used_tok += u.input_tokens + u.output_tokens
            return {"requests": used_req, "tokens": used_tok, "owners": len(owner_users),
                    "per_owner_daily_cap": owner_qa_daily_requests}

        def _runtime_info() -> Dict[str, Any]:
            """Cho `/admin/ai`: khán giả đang áp, RPM/người, số luồng SSE đang chạy trên instance này. Không ID, không khoá."""
            active, cap = stream_guard.snapshot()
            return {"audience": audience, "rpm_per_user": int(ai.rpm), "streams_active": active, "streams_max": cap}

        control.attach_usage_sources(active_users_fn=_active_users, user_usage_fn=_user_usage,
                                     qa_overview_fn=_qa_overview, runtime_info_fn=_runtime_info)

    return AiRuntime(
        True, repo=repo, gateway=gateway, control=control, tool_ctx=tool_ctx or ToolContext(),
        assistant_name=ai.assistant_name,
        daily_tokens_free=ai.daily_tokens_free, daily_tokens_premium=ai.daily_tokens_premium,
        rpm=ai.rpm, web_search_enabled=(ai.web_search_provider or "off") != "off",
        heartbeat_s=float(getattr(ai, "heartbeat_s", 15)),
        stream_guard=stream_guard,
        audience=audience, audience_users=audience_users, owner_users=owner_users,
        owner_qa_daily_requests=owner_qa_daily_requests, **kwargs)
