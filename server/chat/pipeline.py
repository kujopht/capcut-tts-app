"""
Ties the RAG pipeline together — Fanfic AI Chat V1.

`answer_question` takes an injected `llm_complete` callable rather than
importing `server/llm_gateway/` directly, so this module has no hard
dependency on which gateway/provider implementation is wired up - the
caller (a route handler in `server/main.py`) supplies the actual gateway
call. This mirrors the same dependency-injection discipline already used
throughout this package (`VectorStore`/`EmbeddingProvider` are injected
too) and throughout this repo (`StoryProvider` takes an injected
`Fetcher`; `TranslationService` takes an injected `TranslationProvider`).

Builds `ChatContext` INSIDE this function, after intent classification -
NOT accepted pre-built from the caller. `ChatContext.scope` is a required
field; if a caller built one before calling `classify_intent`, that scope
would always look "explicit" to `classify_intent` and the free-text
classification path (for a plain chat-box question with no quick-action
button clicked) would never run. Keeping classification in front of
`ChatContext` construction is the only way both paths - the quick-action
button AND freeform text - genuinely produce a scope decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from server.chat.citation import build_citations
from server.chat.domain import ChatContext, Citation, RetrievalResult, UserReadingContext
from server.chat.embedding_provider import EmbeddingProvider
from server.chat.prompt_builder import PromptMessages, build_prompt
from server.chat.retrieval import classify_intent, retrieve
from server.chat.vector_store import VectorStore

#: `(system, user) -> assistant response text`. Kept as a plain callable
#: (not the `LLMProvider` ABC from `server/llm_gateway/`) so this module
#: never imports that package - the route handler wires the two together.
LlmCompleteFn = Callable[[str, str], str]


@dataclass(frozen=True)
class ChatAnswer:
    answer_text: str
    citations: List[Citation]
    retrieval: List[RetrievalResult]
    #: True when retrieval found nothing usable at all - the caller
    #: should still show `answer_text` (which will say evidence is
    #: insufficient, per the system policy), but this flag lets a UI show
    #: a distinct "no evidence found" state without string-matching the
    #: model's own response text.
    evidence_insufficient: bool


def answer_question(
        question: str, *, reading_context: UserReadingContext,
        vector_store: VectorStore, embedding_provider: EmbeddingProvider,
        llm_complete: LlmCompleteFn, explicit_scope=None,
        selected_text: Optional[str] = None, active_chapter_id: Optional[str] = None,
        character_hint: Optional[str] = None) -> ChatAnswer:
    """`explicit_scope` is the UI's own signal (a quick-action button like
    "Ask this chapter" was clicked) - pass `None` for a plain chat-box
    question with no button, which triggers keyword-based classification
    instead (see `retrieval.classify_intent`)."""
    scope = classify_intent(question, explicit_scope=explicit_scope)
    context = ChatContext(
        user_reading_context=reading_context, scope=scope,
        active_chapter_id=active_chapter_id, selected_text=selected_text,
        character_hint=character_hint)

    retrieval = retrieve(
        question, context, vector_store=vector_store, embedding_provider=embedding_provider)

    prompt: PromptMessages = build_prompt(
        question, retrieval, selected_text=context.selected_text)
    answer_text = llm_complete(prompt.system, prompt.user)

    citations = build_citations(retrieval)
    return ChatAnswer(
        answer_text=answer_text, citations=citations, retrieval=retrieval,
        evidence_insufficient=not retrieval)
