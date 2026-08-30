"""
Fanfic AI Chat V1 — RAG-based chatbot integrated into the reader.

Layout:
    domain.py          — ChatConversation/ChatMessage/ChatContext/
                          RetrievalResult/Citation/UserReadingContext, ChatScope
    spoiler_gate.py     — the hard anti-spoiler retrieval-level invariant
    citation.py         — citation building, never fabricated
    prompt_builder.py   — system/user/retrieved-content channel separation
    chunking.py         — deterministic chunk records over V5 normalized units
    vector_store.py     — abstract VectorStore + in-memory reference impl
    retrieval.py         — intent classification -> retrieval -> ranking
    pipeline.py          — ties the above into answer_question()
    quotas.py            — per-user rate limits / daily message quota

Consumes `server/scraper/universal/` (Story Harvester V5) normalized units
and `server/scraper/contract.py`'s `NormalizedChapter`/`SeriesInfo`. Calls
out to `server/llm_gateway/` for actual model inference - never to
AI_ROUTER_LTS (developer/engineering agents only, frozen, not a
user-facing inference backend).

See `docs/FANFIC_AI_CHAT.md` for the full design + security model.
"""
