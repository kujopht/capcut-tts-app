"""
Provider-neutral context assembly — Fanfic AI Assistant V1 §5/§7.

Builds the `ChatTurn` list for one turn: system(mode) + explicit
preferences + running summary (if memory enabled) + N most recent messages
(bounded by token estimate) + retrieval/web block (if any). ALWAYS rebuilt
from the Fanfic store each turn (contract §0.4: "context belongs to
Fanfic, not the provider") — switching providers mid-conversation never
loses context, because nothing provider-specific is ever stored here.
"""
from __future__ import annotations

from typing import List, Optional

from server.ai_assistant.config import estimate_tokens
from server.ai_assistant.memory import AiMessage, AiRepo
from server.ai_assistant.prompts import system_prompt
from server.llm_gateway.chat_provider import ChatTurn


def build_context(
        *, mode: str, assistant_name: str, repo: AiRepo, user_id: str, conversation_id: str,
        memory_enabled: bool, max_context_tokens: int,
        retrieval_block_text: str = "", pending_recent_messages: Optional[List[AiMessage]] = None,
) -> List[ChatTurn]:
    """`pending_recent_messages` lets a caller pass an in-process-only
    message list when `memory_enabled=False` (nothing was persisted to
    query back) — when omitted, recent history is read from `repo`."""
    turns: List[ChatTurn] = [ChatTurn(role="system", content=system_prompt(
        mode, assistant_name=assistant_name))]

    if memory_enabled:
        prefs = repo.get_preferences(user_id)
        if prefs and prefs.preferences_json and prefs.preferences_json != "{}":
            turns.append(ChatTurn(
                role="system",
                content=f"Sở thích người dùng đã lưu (tuân theo nếu phù hợp): {prefs.preferences_json}"))
        summary = repo.get_summary(conversation_id)
        if summary and summary.summary:
            turns.append(ChatTurn(
                role="system", content=f"Tóm tắt hội thoại trước đó: {summary.summary}"))

    recent = pending_recent_messages if pending_recent_messages is not None else \
        repo.list_messages(conversation_id, limit=50)

    budget = max_context_tokens
    used = sum(estimate_tokens(t.content) for t in turns)
    picked: List[AiMessage] = []
    # Walk from most recent backwards, keep while inside budget - then
    # restore chronological order for the final turn list.
    for m in reversed(recent):
        cost = estimate_tokens(m.content)
        if used + cost > budget and picked:
            break
        used += cost
        picked.append(m)
    picked.reverse()

    for m in picked:
        role = "assistant" if m.role == "assistant" else "user"
        turns.append(ChatTurn(role=role, content=m.content))

    if retrieval_block_text:
        turns.append(ChatTurn(role="system", content=retrieval_block_text))

    return turns
