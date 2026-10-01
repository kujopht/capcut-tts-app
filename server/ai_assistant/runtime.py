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
from server.ai_assistant.limits import RpmLimiter, StreamGuard
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
    #: Khan gia (`AiAssistantSettings.resolved_audience`): "all" | "canary".
    #: "canary" -> CHI `audience_users` (Owner + `FAS_AI_CANARY_USERS`) dung
    #: duoc `/api/ai/*`; nguoi khac: availability `enabled:false`, route khac 403.
    audience: str = "all"
    audience_users: FrozenSet[str] = field(default_factory=frozenset)

    def allows(self, user_id: str) -> bool:
        return self.audience == "all" or (bool(user_id) and user_id in self.audience_users)

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
    if not ai.enabled:
        return AiRuntime(False, reason="FAS_AI_ASSISTANT_V1 chưa bật", control=control)

    data_backend = str(getattr(settings, "data_backend", "mock")).lower()
    resolve_audience = getattr(ai, "resolved_audience", None)
    audience = resolve_audience(data_backend) if callable(resolve_audience) else "all"
    if not audience:
        return AiRuntime(False, reason=f"FAS_AI_AUDIENCE={getattr(ai, 'audience', '')!r} không hợp lệ (canary | all)",
                         control=control)
    audience_users = (frozenset(getattr(settings, "owner_user_ids", ()) or ())
                      | frozenset(getattr(ai, "canary_users", ()) or ()))

    if control is not None:
        from server.ai_assistant.control.router import ControlledGateway
        gateway: Any = ControlledGateway(control)
    else:
        chain = resolve_provider_chain(ai, environment=settings.environment)
        if not chain:
            return AiRuntime(False, reason="no_provider")

        providers: Dict[str, ChatProvider] = {}
        for name in chain:
            p = _build_provider(name, settings)
            if p is not None:
                providers[name] = p
        usable_chain = [n for n in chain if n in providers]
        if not usable_chain:
            return AiRuntime(False, reason="no_provider")

        gateway = AiGateway(providers=providers, provider_chain=usable_chain)

    if data_backend == "appwrite":
        try:
            repo: AiRepo = AppwriteAiRepo(settings)
        except AiUnavailable as exc:
            return AiRuntime(False, reason=f"appwrite_not_configured: {exc}")
    else:
        repo = InMemoryAiRepo()

    kwargs: Dict[str, Any] = {}
    if getattr(ai, "user_ref_salt", ""):
        kwargs["user_ref_salt"] = ai.user_ref_salt

    if control is not None:
        def _user_usage(user_id: str, day: str) -> Tuple[int, int]:
            u = repo.get_usage_day(user_id, day)
            return (u.requests, u.input_tokens + u.output_tokens) if u else (0, 0)
        control.attach_usage_sources(active_users_fn=repo.count_usage_users, user_usage_fn=_user_usage)

    return AiRuntime(
        True, repo=repo, gateway=gateway, control=control, tool_ctx=tool_ctx or ToolContext(),
        assistant_name=ai.assistant_name,
        daily_tokens_free=ai.daily_tokens_free, daily_tokens_premium=ai.daily_tokens_premium,
        rpm=ai.rpm, web_search_enabled=(ai.web_search_provider or "off") != "off",
        heartbeat_s=float(getattr(ai, "heartbeat_s", 15)),
        stream_guard=StreamGuard(max_streams_per_instance=ai.max_streams),
        audience=audience, audience_users=audience_users, **kwargs)
