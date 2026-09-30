"""
Fanfic AI Assistant V1 — backend foundation, behind `FAS_AI_ASSISTANT_V1`
(default OFF). See `docs/ai/AI_ASSISTANT_V1.md` for the full design
contract this package implements.

Layout:
    config.py           — flags/limits (`AiAssistantSettings`, read from env
                          via `server/config.py`).
    prompts.py           — per-mode system prompts + display name.
    memory.py            — `AiRepo` ABC + `InMemoryAiRepo` + `AppwriteAiRepo`
                          for the 7 `ai_*` collections.
    context_builder.py   — provider-neutral `ChatTurn` list assembly.
    tools.py             — read-only model tools (search_library,
                          retrieve_story_chunks, get_safe_diagnostics,
                          web_search).
    web_search.py         — `WebSearchTool` ABC + Null/Mock implementations.
    limits.py             — rate limit / concurrent-stream / daily budget.
    gateway.py             — mode -> provider chain, fallback-before-first-
                          token policy, context trimming.
    routes.py              — FastAPI router for every `/api/ai/*` endpoint.

Nothing here changes `/api/chat/ask` or `server/messaging/**` — this is an
ADDITIVE package, mounted (but gated) from `server/main.py`.
"""
