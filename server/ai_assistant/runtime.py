"""
Assembles the AI Assistant runtime from `Settings` — same role as
`server/messaging/runtime.py::build_runtime`: the ONE place that picks
storage backend + provider set for the environment actually running.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

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
    gateway: Optional[AiGateway] = None
    tool_ctx: ToolContext = field(default_factory=ToolContext)
    rpm_limiter: RpmLimiter = field(default_factory=RpmLimiter)
    stream_guard: StreamGuard = field(default_factory=lambda: StreamGuard(max_streams_per_instance=4))
    assistant_name: str = "Fanfic AI"
    daily_tokens_free: int = 30000
    daily_tokens_premium: int = 200000
    rpm: int = 8
    web_search_enabled: bool = False
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

    def describe(self) -> dict:
        return {"enabled": self.enabled, "reason": self.reason or None,
                "name": self.assistant_name, "web_search": self.web_search_enabled}


def _build_provider(name: str, settings: Any) -> Optional[ChatProvider]:
    ai = settings.ai_assistant
    try:
        if name == "mock":
            return MockChatProvider()
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


def build_ai_runtime(settings: Any, *, tool_ctx: Optional[ToolContext] = None) -> AiRuntime:
    ai = settings.ai_assistant
    if not ai.enabled:
        return AiRuntime(False, reason="FAS_AI_ASSISTANT_V1 chưa bật")

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

    data_backend = str(getattr(settings, "data_backend", "mock")).lower()
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

    return AiRuntime(
        True, repo=repo, gateway=gateway, tool_ctx=tool_ctx or ToolContext(),
        assistant_name=ai.assistant_name,
        daily_tokens_free=ai.daily_tokens_free, daily_tokens_premium=ai.daily_tokens_premium,
        rpm=ai.rpm, web_search_enabled=(ai.web_search_provider or "off") != "off",
        stream_guard=StreamGuard(max_streams_per_instance=ai.max_streams), **kwargs)
