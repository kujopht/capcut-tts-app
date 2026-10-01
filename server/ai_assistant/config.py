"""
Fanfic AI Assistant V1 — flags/limits derived from `server.config.Settings.
ai_assistant` (`AiAssistantSettings`). This module holds business-level
constants (per-mode limits, provider-chain resolution) — the raw env-var
reads live in `server/config.py`, matching this repo's existing split
between "settings" (env) and feature-level constant modules elsewhere
(e.g. `server/llm_gateway/usage_limits.py` vs `server/config.py`).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple

from server.config import AiAssistantSettings

log = logging.getLogger("fanfic.ai_assistant")

MODES: Tuple[str, ...] = ("general", "story", "support", "writer")

#: (max_context_tokens_estimate, default_max_output_tokens) per mode — §9.
#: `writer` gets a larger context/output budget for `draft_chapter`.
MODE_LIMITS: Dict[str, Dict[str, int]] = {
    "general": {"max_context_tokens": 6000, "max_output_tokens": 800},
    "story": {"max_context_tokens": 6000, "max_output_tokens": 800},
    "support": {"max_context_tokens": 6000, "max_output_tokens": 800},
    "writer": {"max_context_tokens": 8000, "max_output_tokens": 1500},
}

MAX_USER_MESSAGE_CHARS = 4000
MAX_CONVERSATIONS_PER_USER = 200
#: Khớp `AppwriteAiRepo.list_projects` (limit 100): dự án thứ 101 sẽ vô hình trong danh sách nên không cho tạo.
MAX_PROJECTS_PER_USER = 100
#: Các route GHI không gọi LLM (dự án, sở thích, xoá ký ức, yêu cầu hỗ trợ) không tốn hạn mức lượt, nên cần trần tốc
#: độ riêng: trước đây một vòng lặp tạo dự án/escalation không bị giới hạn gì ngoài kích thước từng dòng.
WRITE_RPM = 30
ESCALATION_RPM = 3
#: Trần độ dài API cho dự án — khớp `AppwriteAiRepo._PROJECT_TEXT_LIMITS` (repo vẫn cắt, nhưng API giờ từ chối rõ ràng).
PROJECT_TITLE_MAX = 120
PROJECT_TEXT_MAX = 4000
#: Kẹp tham số `limit` của các route danh sách (0 làm `[-0:]` trả TOÀN BỘ, số âm làm Appwrite 400 -> 503).
LIST_LIMIT_MAX = 100
#: Conservative chars-per-token estimate (never exact) — §3.
CHARS_PER_TOKEN_ESTIMATE = 3.5


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / CHARS_PER_TOKEN_ESTIMATE))


@dataclass(frozen=True)
class ResolvedProvider:
    name: str
    #: Only ever "why excluded" text for LOGS — never the missing key's
    #: value (there IS none to leak; only the env var NAME is mentioned).
    exclusion_reason: str = ""


def resolve_provider_chain(settings: AiAssistantSettings, *, environment: str) -> List[str]:
    """Returns the ORDERED list of provider names actually usable given
    configured keys — a provider named in `FAS_AI_PROVIDERS` but missing
    its key is skipped with a log line naming the env var, never its
    value. Falls back to `["mock"]` only outside production; production
    with nothing configured returns an empty list (caller reports
    `enabled=false, reason=no_provider` — never silently uses mock in
    prod)."""
    usable: List[str] = []
    for name in settings.providers:
        name = name.strip().lower()
        if not name:
            continue
        if name == "mock":
            usable.append(name)
        elif name == "qwen":
            if settings.qwen_api_key:
                usable.append(name)
            else:
                log.info("ai_assistant: provider 'qwen' bị loại — thiếu AI_QWEN_API_KEY.")
        elif name == "azure_openai":
            if settings.azure_openai_endpoint and settings.azure_openai_api_key \
                    and settings.azure_openai_deployment:
                usable.append(name)
            else:
                log.info(
                    "ai_assistant: provider 'azure_openai' bị loại — thiếu "
                    "AI_AZURE_OPENAI_ENDPOINT/AI_AZURE_OPENAI_API_KEY/AI_AZURE_OPENAI_DEPLOYMENT.")
        elif name == "tencent":
            if settings.tencent_api_key and settings.tencent_base_url:
                usable.append(name)
            else:
                log.info(
                    "ai_assistant: provider 'tencent' bị loại — thiếu "
                    "AI_TENCENT_API_KEY/AI_TENCENT_BASE_URL.")
        else:
            log.info("ai_assistant: provider '%s' không rõ, bị bỏ qua.", name)

    if not usable and environment.lower() not in ("production", "prod"):
        usable = ["mock"]
    return usable


def daily_token_limit(settings: AiAssistantSettings, *, tier: str) -> int:
    return settings.daily_tokens_premium if tier == "premium" else settings.daily_tokens_free
