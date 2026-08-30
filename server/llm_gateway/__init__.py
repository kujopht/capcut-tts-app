"""
LLM Gateway — Fanfic AI Chat V1 Phase 7. Production, user-facing inference,
COMPLETELY SEPARATE from AI_ROUTER_LTS (`scripts/router_v3/`).

    AI_ROUTER_LTS = developer/engineering agents (Antigravity/Claude Code/
                    Grok Build/OpenCode sessions) - frozen, dev-tooling only
    LLM_GATEWAY   = user-facing Fanfic World inference - this package

Nothing in this package imports `scripts.router_v3.*` or shells out to any
of `agy`/`claude`/`grok`/`opencode` - see `docs/FANFIC_AI_CHAT.md`'s
"Provider-neutral LLM Gateway" section for why that boundary is a hard
requirement, not a convention.

Layout:
    provider.py     — LLMProvider ABC + MockLLMProvider (no network, tests/dev)
    providers.py     — real provider implementations (OpenAI-compatible/
                       Gemini/Anthropic), same shape as
                       server/translation_providers.py's DocuTranslateProvider
    routing.py        — capability/cost routing (cheap/complex/translation)
    usage_limits.py   — rate limits, quotas, token/output budgets, circuit
                       breaker - same shape as server/social.py's HanMuc
    gateway.py         — LLMGateway, the single entrypoint server/chat/
                       calls through an injected callable (never a direct
                       import), matching this repo's dependency-injection
                       convention throughout.
"""
