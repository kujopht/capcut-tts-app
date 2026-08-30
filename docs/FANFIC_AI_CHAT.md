# Fanfic AI Chat V1

A RAG-based chatbot integrated into the reader (`server/chat/`,
`server/llm_gateway/`, `web/src/components/AskAiPanel.tsx`). Consumes
Story Harvester V5's normalized-content infrastructure
(`server/scraper/universal/semantic.py`) and this repo's own native
`Chapter`/`NovelBrief` content — built as a genuinely new, user-facing
product surface, not a developer/engineering tool.

## Architecture

```
question --[classify_intent]--> ChatScope
        --[retrieve]--> vector store query (novel/chapter-index hints)
        --[spoiler_gate.apply_retrieval_gates]--> filtered RetrievalResult[]
        --[assemble_bounded_context]--> capped chunk list
        --[prompt_builder.build_prompt]--> (system, user) messages
        --[LLMGateway.complete]--> answer text
        --[citation.build_citations]--> Citation[]
```

`server/chat/pipeline.py::answer_question` ties every stage together. It
takes an injected `llm_complete: (system, user) -> str` callable rather
than importing `server/llm_gateway/` directly — the route handler
(`server/main.py::chat_ask` → `server/chat_service.py::ChatService`)
wires the two together via `LLMGateway.as_llm_complete_fn()`.

## Domain model (Phase 1)

`server/chat/domain.py`: `ChatConversation`, `ChatMessage`, `ChatContext`,
`RetrievalResult`, `Citation`, `UserReadingContext`, `ChatScope` (GENERAL/
THIS_CHAPTER/THIS_STORY/CHARACTER/SEARCH/RECOMMENDATION). Uses this repo's
own `novel_id`/`chapter_id`/`chapter_index` vocabulary — `chapter_index`
maps to `Chapter.order_index` (`server/domain.py`) at the integration
layer, kept as a distinct chat-domain name since it represents reading
*progress*, not a chapter's own position field, even though the numeric
value is the same for the chapter a user has most recently read.

## Anti-spoiler hard invariant (Phase 2)

`server/chat/spoiler_gate.py` — enforced on the **retrieval candidate
list**, never as an instruction inside the LLM prompt:

- `enforce_spoiler_boundary`: drops any candidate from the user's active
  novel whose `chapter_index` exceeds `current_chapter_index`, unless the
  user explicitly disabled spoiler protection.
- `enforce_scope_boundary`: for novel-scoped chat modes (THIS_CHAPTER/
  THIS_STORY/CHARACTER), drops any candidate from a *different* novel —
  prevents cross-story retrieval leakage regardless of spoiler settings.

`VectorStore.query()`'s `novel_id`/`max_chapter_index` parameters are
**optimization hints only** a real backend can push down as a metadata
filter — `retrieval.py` always re-applies both gates on whatever comes
back, so the hard invariant never depends on trusting a specific vector
store implementation's filter support.

Note on `current_chapter_index` itself: this repo has **no existing
reading-progress tracking feature**. V1 has the reader page supply its
own already-known chapter position in the request. This is a UX safeguard
against accidental self-spoiling, **not an access-control boundary** —
every chapter of a published novel is already publicly readable by
scrolling ahead; there is no real confidentiality being enforced here,
only a courtesy default. A future version could add real server-tracked
reading progress without changing anything in `spoiler_gate.py` itself.

## RAG pipeline / chunking (Phase 3/4)

`server/chat/chunking.py::build_chunk_records` works over either native
`Chapter.content` or a Story-Harvester-V5 `NormalizedChapter.clean_text` —
both are "chapter text + identifying metadata" from this module's view.
Reuses `server.scraper.universal.semantic.chunk_text` and
`server.scraper.dedupe.content_hash`, not reimplemented.
`chunking.needs_reembedding` avoids re-embedding unchanged content
(compares both `content_hash` and `chunking_version`).

`server/chat/vector_store.py` — abstract `VectorStore` + a real
`InMemoryVectorStore` reference implementation (brute-force cosine
similarity). Kept abstract per the mission brief: no vendor is chosen.

`server/chat/embedding_provider.py` — abstract `EmbeddingProvider` +
`HashEmbeddingProvider`, a real deterministic (sha256-based, **not**
Python's randomized `hash()`) dependency-free implementation for dev/
tests without any API key.

`server/chat/retrieval.py` — never sends an entire story to the LLM:
`assemble_bounded_context` caps both chunk count and total character
budget.

## Citations (Phase 5)

`server/chat/citation.py::build_citations` — built only from
`RetrievalResult`s that actually contributed to an answer, never
fabricated. A citation is a pointer (`chapter_id`/`chapter_index`/
`chunk_order` + a short bounded excerpt), not a content mirror.

## Core user features (Phase 6)

| Feature | How |
|---|---|
| A. Ask this chapter | `scope=this_chapter`, `active_chapter_id` set |
| B. Ask this story | `scope=this_story` |
| C. Anti-spoiler | Always on by default — see Phase 2 |
| D. Search | `scope=search` — exact chapter-lookup questions |
| E. Translation helper | Calls the **existing** `translation_provider_registry.py` infrastructure directly, not this gateway (per the mission brief) |

## Provider-neutral LLM Gateway (Phase 7)

```
AI_ROUTER_LTS  = developer/engineering agents (scripts/router_v3/) - frozen
LLM_GATEWAY    = user-facing Fanfic World inference (server/llm_gateway/)
```

Nothing in `server/llm_gateway/` imports `scripts.router_v3.*` or shells
out to `agy`/`claude`/`grok`/`opencode`. `server/llm_gateway/provider.py`
defines one method (`complete`), same shape/rationale as this repo's
existing `TranslationProvider`. `providers.py` has real, correctly-shaped
HTTP clients for `OpenAICompatProvider` (covers OpenAI/OpenRouter/self-
hosted — all speak the same wire format), `GeminiProvider`, and
`AnthropicProvider` — **not exercised against a live API key** in this
environment; `MockLLMProvider` is what every test and the current backend
wiring actually uses.

`routing.py::GatewayRouter` holds an ordered fallback chain per
`TaskKind` (CHEAP_SIMPLE/COMPLEX_GROUNDED/TRANSLATION).
`gateway.py::LLMGateway.complete` tries each target in order, skipping any
whose circuit is open.

Provider keys live in `server/config.py::LlmGatewaySettings` (env vars
only, e.g. `LLM_OPENAI_API_KEY`) — same pattern as
`AppwriteSettings`/`ImageStudioSettings`, never sent to the browser.

## Usage/cost controls (Phase 8)

`server/llm_gateway/usage_limits.py`:
- `MessageQuota`/`enforce_quota` — same shape as `server/social.py`'s
  `HanMuc`/`kiem_han_muc` (a pure decision function; counting is the
  store layer's job). `DEFAULT_MESSAGE_QUOTA` has `free`/`premium` tiers
  already shaped for later tiering — **no payment enforcement is
  implemented**, per the mission brief.
- `RetrievalBudget`/`enforce_output_budget` — output-size backstop,
  truncates visibly rather than silently dropping content.
- `CircuitBreaker` — per-provider-name, independent of (and NOT reusing)
  `scripts/router_v3/registry.py`'s own circuit breaker, which governs a
  completely separate concern (developer-agent workers, not inference
  providers).

Timeouts are each provider's own `httpx.Client(timeout=...)` — not a
second, redundant gateway-level knob.

**Not yet wired into the live route** (`POST /api/chat/ask` in
`server/main.py`): rate limiting/quota enforcement — explicitly deferred
this pass so the backend-integration and evaluation-harness work could
proceed in parallel against a stable contract. The pieces exist
(`usage_limits.py`) and are unit-tested; wiring `enforce_quota` into
`ChatService.ask()` is the natural next step before any real user traffic.

## Chat UI (Phase 9)

`web/src/components/AskAiPanel.tsx`, integrated into
`web/src/app/chapters/[id]/page.tsx`. No Tailwind, no new component
library — matches this repo's existing `ConfirmDialog`/`SearchOverlay`
conventions (portal via `createPortal`, hand-written CSS design tokens).
Side panel on wide viewports, bottom sheet on narrow ones. Quick actions
for each Phase 6 feature, a visible "Chống spoiler: BẬT — Đến chương N"
indicator, reader-text-selection support for the translation-helper
action.

## Security / prompt injection (Phase 10)

`server/chat/prompt_builder.py` keeps three channels strictly separate:
system policy (fixed, never contains retrieved/user content), the user's
own question, and retrieved/selected text (always explicitly labeled
untrusted data the model must never treat as instructions). Proven with
an adversarial test embedding a fake `"SYSTEM: ..."` message inside
retrieved chapter text and confirming it never reaches the system
channel. Real chat-completion APIs only have system/user/assistant roles
— bundling retrieved content into the user message with clear delimiters
is the same pattern this repo's own
`translation_providers.py::_nguoi_dung_prompt` already uses.

Additional adversarial coverage
(`server/tests/test_chat_security_adversarial_extra.py`): HTML/script
content in a retrieved chunk stays an inert string (no rendering/eval
path exists anywhere in `server/chat/`), massive chunks respect the
context character budget, Unicode control characters don't crash the
pipeline, no secret sentinel value leaks into a built prompt through any
code path.

## Privacy (Phase 11)

`server/chat/privacy.py`: `RetentionPolicy`/`is_expired` (30-day default,
a pure decision function — deletion is the store layer's job) and
`redact_for_logging` (strips control characters, bounds length — same
discipline as `change_detection._an_toan`). Secrets never reaching a
prompt is enforced **by construction**: `prompt_builder.build_prompt`
only ever accepts a question string, retrieval results, and optional
selected text — no code path in `server/chat/` constructs a prompt from a
user/profile object, so there is nothing to redact there in the first
place.

## Evaluation (Phase 12)

`server/chat/evaluation.py::run_evaluation_cases` — all 8 deterministic
cases from the mission brief, against a real fixture corpus and the real
pipeline (only the LLM's own prose uses `MockLLMProvider`). Measures
retrieval hit rate, citation correctness, spoiler violations (must be
zero), average context size, average latency, and provider cost estimate
(honestly `0.0` for a mock provider — never fabricated).

## E2E (Phase 14)

`server/chat/e2e_reader_scenario.py` — the exact scenario from the
mission brief: a 10-chapter fixture story, user at chapter 7, early-
chapter evidence correctly cited, later-chapter-only evidence never
leaked, a reader-selected-paragraph explanation, and an exact chapter-
lookup search question.

## Remaining work before production

- Wire a real LLM provider (`LLM_GEMINI_API_KEY`/`LLM_OPENAI_API_KEY`/...)
  through `server/config.py::LlmGatewaySettings` and
  `server/chat_service.py::ChatService`'s gateway construction — today it
  is hard-wired to `MockLLMProvider` only.
- Wire `usage_limits.enforce_quota`/rate limiting into the live
  `POST /api/chat/ask` route (the pieces exist, unit-tested, not yet
  called from `ChatService.ask()`).
- Persist chat history to Appwrite (a real collection + store
  implementation satisfying the existing `ChatStore` protocol) — today
  `InMemoryChatStore` is foundation-only, matching how several other
  features in this repo start before their Appwrite schema lands.
- A real embedding provider (replacing `HashEmbeddingProvider` for
  production-quality semantic retrieval) and a production-scale vector
  store (replacing `InMemoryVectorStore`) — both are swap-in changes
  behind their existing abstract interfaces, no pipeline code changes
  needed.
- Real reading-progress tracking, if ever wanted as more than a client-
  supplied UX default — see the Phase 2 note above; `spoiler_gate.py`
  itself would not need to change.
