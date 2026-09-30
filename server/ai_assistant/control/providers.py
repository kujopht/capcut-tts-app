"""
Build a `ChatProvider` for one control-plane slot.

Gemini, Groq, Workers AI, Qwen (DashScope compatible mode) and OpenRouter all
speak the OpenAI chat-completions wire format at their `effective_endpoint()`
(Gemini via its documented `/v1beta/openai` surface, Workers AI via
`/client/v4/accounts/<id>/ai/v1`). Azure OpenAI keeps its own class
(deployment-scoped URL + `api-key` header). The provider's `name` is the
SLOT id, so circuit breakers, usage counters and `ProviderServed` are all
per slot — two Gemini projects never share a cooldown.

Clients are cached per (slot, endpoint, model, api_version, key fingerprint):
a key rotation (new fingerprint) builds a fresh client; the raw key is held
only inside the httpx client headers, never on a config object.
"""
from __future__ import annotations

import hashlib
import threading
from typing import Callable, Dict, Optional, Tuple

from server.ai_assistant.control.model import ProviderSlot
from server.llm_gateway.chat_provider import ChatProvider
from server.llm_gateway.chat_providers import AzureOpenAIProvider, OpenAICompatChatProvider

ProviderBuilder = Callable[[ProviderSlot, str], ChatProvider]


def default_builder(slot: ProviderSlot, api_key: str) -> ChatProvider:
    if slot.provider_type == "azure_openai":
        p: ChatProvider = AzureOpenAIProvider(endpoint=slot.effective_endpoint(), api_key=api_key,
                                              deployment=slot.model, api_version=slot.api_version or "2024-06-01")
    else:
        headers = {"X-Title": "Fanfic World"} if slot.provider_type == "openrouter" else None
        p = OpenAICompatChatProvider(name=slot.slot_id, base_url=slot.effective_endpoint(), api_key=api_key,
                                     extra_headers=headers)
    p.name = slot.slot_id
    setattr(p, "_default_model", slot.model)
    return p


class ProviderFactory:
    def __init__(self, builder: ProviderBuilder = default_builder) -> None:
        self._builder = builder
        self._lock = threading.Lock()
        self._cache: Dict[str, Tuple[Tuple[str, ...], ChatProvider]] = {}

    def get(self, slot: ProviderSlot, api_key: str) -> ChatProvider:
        fp = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
        key = (slot.provider_type, slot.effective_endpoint(), slot.model, slot.api_version, fp)
        with self._lock:
            hit = self._cache.get(slot.slot_id)
            if hit and hit[0] == key:
                return hit[1]
            provider = self._builder(slot, api_key)
            self._cache[slot.slot_id] = (key, provider)
            return provider

    def cached(self, slot_id: str) -> Optional[ChatProvider]:
        with self._lock:
            hit = self._cache.get(slot_id)
            return hit[1] if hit else None
