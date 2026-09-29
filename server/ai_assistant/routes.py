"""
Routes — Fanfic AI Assistant V1 §10. `FAS_AI_ASSISTANT_V1=0` (default) ->
every route except `GET /api/ai/availability` returns 503 `ai_not_enabled`.
Streaming (`POST /api/ai/conversations/{id}/messages`) never blocks the
event loop: the gateway's provider iterator is a plain sync generator
(httpx sync streaming under the hood) consumed via
`starlette.concurrency.iterate_in_threadpool` — each `next()` call runs in
the threadpool, not on the asyncio loop (contract §0.2's explicit lesson:
"a Render process starved of threads hangs even /api/health").
"""
from __future__ import annotations

import contextlib
import json
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.concurrency import iterate_in_threadpool, run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, StringConstraints
from typing_extensions import Annotated

from server.ai_assistant.config import (
    MAX_CONVERSATIONS_PER_USER, MAX_USER_MESSAGE_CHARS, MODES, estimate_tokens,
)
from server.ai_assistant.context_builder import build_context
from server.ai_assistant.gateway import ErrorEvent
from server.ai_assistant.limits import (
    AiBudgetExceeded, AiBusy, AiRateLimited, budget_status, enforce_budget, record_usage,
)
from server.ai_assistant.memory import (
    AiConversation, AiEscalation, AiMessage, AiPreferences, AiProject, RepoConflict, now_iso,
)
from server.ai_assistant.runtime import AiRuntime
from server.ai_assistant.tools import (
    citations_for, format_web_results_for_prompt, retrieve_story_chunks, search_library, web_search,
)
from server.llm_gateway.chat_provider import Delta, Done, UsageEvent

ConvId = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
ProjectId = ConvId
UserContent = Annotated[str, StringConstraints(max_length=MAX_USER_MESSAGE_CHARS)]


class ContextIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    novel_id: Optional[str] = None
    chapter_id: Optional[str] = None
    current_chapter_index: int = 1
    project_id: Optional[str] = None


class ConversationCreateIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    mode: str = "general"
    title: Optional[Annotated[str, StringConstraints(max_length=120)]] = None
    context: Optional[ContextIn] = None


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: UserContent
    client_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    regenerate_of: Optional[str] = None
    use_web_search: bool = False
    use_library: bool = False


class PreferencesIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    memory_enabled: bool = True
    preferences: Dict[str, Any] = {}


class ProjectIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = ""
    premise: str = ""
    outline: Dict[str, Any] = {}
    characters: Dict[str, Any] = {}
    world: Dict[str, Any] = {}
    notes: str = ""


class EscalationIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    conversation_id: Optional[str] = None
    summary: Annotated[str, StringConstraints(max_length=2000)]


def _new_id() -> str:
    return uuid.uuid4().hex


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _tier_of(profile: Any) -> str:
    raw = getattr(profile, "tier", "free") or "free"
    # `raw` may be a `str`-mixin `Enum` member (e.g. `server.domain.Tier`) —
    # `str(Tier.FREE)` is `"Tier.FREE"` on Python < 3.13 (the mixin's
    # `__str__` is NOT used for `str()`/f-strings until 3.12's Enum
    # rewrite, and even 3.12 only fixes `format()`/f-strings, not the
    # plain `str()` call — see bpo-40066), so a bare `str(...)` here
    # silently classified every FREE-tier user as "premium" (wrong,
    # higher budget). `.value` is the actual member value ("free",
    # "listener_pro", ...); non-Enum inputs (plain strings, tests) fall
    # back to the value itself unchanged.
    tier = str(getattr(raw, "value", raw) or "free").lower()
    return "free" if tier in ("free", "") else "premium"


def _daily_limit(rt: AiRuntime, tier: str) -> int:
    return rt.daily_tokens_premium if tier == "premium" else rt.daily_tokens_free


def build_ai_router(rt: AiRuntime, *, resolve_profile: Callable[[Optional[str]], Any]) -> APIRouter:
    r = APIRouter()

    def _bat() -> AiRuntime:
        if not rt.enabled or rt.repo is None or rt.gateway is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                {"code": "ai_not_enabled",
                                 "message": "Trợ lý AI chưa được bật trên máy chủ."})
        return rt

    def _run(f: Callable[[], Any]) -> Any:
        try:
            return f()
        except AiRateLimited as exc:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                {"code": "ai_rate_limited", "message": str(exc)}) from exc
        except AiBudgetExceeded as exc:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                {"code": "ai_budget_exhausted", "message": str(exc),
                                 "reset_at": exc.reset_at}) from exc
        except AiBusy as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                {"code": "ai_busy", "message": str(exc)}) from exc

    def _memory_enabled(user_id: str) -> bool:
        prefs = rt.repo.get_preferences(user_id)
        return prefs.memory_enabled if prefs else True

    def _find_conversation(conversation_id: str):
        """Checks BOTH the durable repo and the ephemeral (`memory_enabled
        =false`) store — a conversation lives in exactly one of the two at
        any moment, decided at `create_conversation` time. Returns
        `(conversation, is_ephemeral)`."""
        conv = rt.repo.get_conversation(conversation_id)
        if conv is not None:
            return conv, False
        conv = rt.ephemeral.get_conversation(conversation_id)
        return conv, True

    def _own_conversation(user_id: str, conversation_id: str):
        conv, is_ephemeral = _find_conversation(conversation_id)
        if conv is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                {"code": "ai_not_found", "message": "Không tìm thấy hội thoại."})
        if conv.user_id != user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                {"code": "ai_forbidden", "message": "Hội thoại này không thuộc về bạn."})
        return conv, is_ephemeral

    def _recent_messages_combined(conversation_id: str, *, limit: int) -> List[AiMessage]:
        """Merges durable + ephemeral history for one conversation — a
        conversation can legitimately have messages in BOTH (memory was
        toggled mid-conversation): durable ones from while it was on,
        ephemeral ones from while it was off. Deduped by `message_id`,
        sorted by `created_at`, capped to `limit` most recent. Both
        `list_messages` calls already return their own results in
        chronological (insertion) order — a STABLE sort on `created_at`
        alone (no secondary key) preserves that relative order for any
        same-second tie, which a secondary key like `message_id` (a random
        hex, unrelated to time) would scramble."""
        durable = rt.repo.list_messages(conversation_id, limit=limit)
        ephemeral = rt.ephemeral.list_messages(conversation_id, limit=limit)
        by_id = {m.message_id: m for m in durable}
        for m in ephemeral:
            by_id[m.message_id] = m
        merged = sorted(by_id.values(), key=lambda m: m.created_at)
        return merged[-limit:]

    def _own_project(user_id: str, project_id: str) -> AiProject:
        proj = rt.repo.get_project(project_id)
        if proj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                {"code": "ai_not_found", "message": "Không tìm thấy dự án."})
        if proj.user_id != user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                {"code": "ai_forbidden", "message": "Dự án này không thuộc về bạn."})
        return proj

    # ---------------------------------------------------------------- availability
    @r.get("/api/ai/availability")
    def availability(response: Response,
                     authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        profile = resolve_profile(authorization)
        if not rt.enabled or rt.repo is None or rt.gateway is None:
            return {"enabled": False, "reason": rt.reason or "off", "name": rt.assistant_name,
                    "modes": [], "web_search": False}
        tier = _tier_of(profile)
        status_ = budget_status(rt.repo, user_id=profile.user_id, daily_limit=_daily_limit(rt, tier))
        # `memory_enabled` here is informational (same source as GET
        # /api/ai/preferences) — usage limits below are ALWAYS from the
        # durable ai_usage_daily ledger regardless of this flag (contract
        # §5/§9: usage metering keeps recording, content does not).
        return {"enabled": True, "reason": None, "name": rt.assistant_name, "modes": list(MODES),
                "web_search": rt.web_search_enabled, "memory_enabled": _memory_enabled(profile.user_id),
                "limits": {"used_today": status_.used_today, "limit_today": status_.limit_today,
                          "reset_at": status_.reset_at}}

    # ---------------------------------------------------------------- conversations
    @r.get("/api/ai/conversations")
    def list_conversations(limit: int = 30, cursor: Optional[str] = None,
                           authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = resolve_profile(authorization)
        durable = _run(lambda: rt.repo.list_conversations(profile.user_id, limit=limit, cursor=cursor))
        # Ephemeral (memory-off) conversations are ALWAYS flagged
        # `ephemeral: true` — the UI must be able to tell a user this
        # history disappears in ≤1h and was never written to storage.
        ephemeral = rt.ephemeral.list_conversations(profile.user_id)
        items = (
            [{"conversation_id": c.conversation_id, "mode": c.mode, "title": c.title,
             "created_at": c.created_at, "updated_at": c.updated_at,
             "message_count": c.message_count, "ephemeral": False} for c in durable]
            + [{"conversation_id": c.conversation_id, "mode": c.mode, "title": c.title,
               "created_at": c.created_at, "updated_at": c.updated_at,
               "message_count": c.message_count, "ephemeral": True} for c in ephemeral])
        items.sort(key=lambda i: i["updated_at"], reverse=True)
        return {"items": items[:limit]}

    @r.post("/api/ai/conversations")
    def create_conversation(payload: ConversationCreateIn,
                            authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = resolve_profile(authorization)
        mode = payload.mode if payload.mode in MODES else "general"
        if rt.repo.count_conversations(profile.user_id) >= MAX_CONVERSATIONS_PER_USER:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                {"code": "ai_context_too_large",
                                 "message": f"Đã đạt tối đa {MAX_CONVERSATIONS_PER_USER} hội thoại."})
        ctx = payload.context or ContextIn()
        conv = AiConversation(
            conversation_id=_new_id(), user_id=profile.user_id, mode=mode,
            title=payload.title or "", context_novel_id=ctx.novel_id or "",
            context_chapter_id=ctx.chapter_id or "", context_project_id=ctx.project_id or "")
        memory_enabled = _memory_enabled(profile.user_id)
        if memory_enabled:
            conv = _run(lambda: rt.repo.create_conversation(conv))
        else:
            # contract §5: "hội thoại mới không được lưu quá phiên" — NEVER
            # reaches `rt.repo`/Appwrite while memory is off.
            conv = rt.ephemeral.create_conversation(conv)
        return {"conversation_id": conv.conversation_id, "mode": conv.mode, "title": conv.title,
                "created_at": conv.created_at, "ephemeral": not memory_enabled}

    @r.get("/api/ai/conversations/{conversation_id}")
    def get_conversation(conversation_id: ConvId, limit: int = 50,
                         authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = resolve_profile(authorization)
        conv, is_ephemeral = _own_conversation(profile.user_id, conversation_id)
        msgs = _recent_messages_combined(conversation_id, limit=limit)
        return {
            "conversation_id": conv.conversation_id, "mode": conv.mode, "title": conv.title,
            "ephemeral": is_ephemeral,
            "messages": [
                {"message_id": m.message_id, "role": m.role, "content": m.content,
                 "status": m.status, "citations": json.loads(m.citations_json or "[]"),
                 "created_at": m.created_at} for m in msgs]}

    @r.delete("/api/ai/conversations/{conversation_id}")
    def delete_conversation(conversation_id: ConvId,
                            authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = resolve_profile(authorization)
        _own_conversation(profile.user_id, conversation_id)
        # Harmless no-op on whichever store the conversation ISN'T in.
        rt.repo.delete_conversation(conversation_id)
        rt.ephemeral.delete_conversation(conversation_id)
        return {"deleted": True}

    # ---------------------------------------------------------------- messages (SSE)
    @r.post("/api/ai/conversations/{conversation_id}/messages")
    async def post_message(conversation_id: ConvId, payload: MessageIn, request: Request,
                           authorization: Optional[str] = Header(default=None)):
        _bat()
        profile = resolve_profile(authorization)
        conv, _ = _own_conversation(profile.user_id, conversation_id)
        _run(lambda: rt.rpm_limiter.check(profile.user_id, rpm=rt.rpm))
        tier = _tier_of(profile)
        daily_limit = _daily_limit(rt, tier)
        # R4 (review finding): `enforce_budget`/`get_preferences`/`create_message`/
        # `build_context` all touch `rt.repo`, which for `AppwriteAiRepo` means
        # real HTTP calls — every one of them runs via `run_in_threadpool`
        # below so a slow Appwrite round-trip never blocks the asyncio loop
        # (same lesson as the streaming path itself, contract §0.2).
        await run_in_threadpool(
            lambda: _run(lambda: enforce_budget(rt.repo, user_id=profile.user_id, daily_limit=daily_limit)))
        _run(lambda: rt.stream_guard.acquire(profile.user_id))

        def _prepare():
            memory_enabled = _memory_enabled(profile.user_id)

            user_message = AiMessage(
                message_id=_new_id(), conversation_id=conversation_id, user_id=profile.user_id,
                role="user", content=payload.content, client_id=payload.client_id)
            # contract §5: while memory is OFF, this write goes ONLY to the
            # in-process TTL cache — NEVER to `rt.repo`/Appwrite. Toggling
            # memory back ON immediately resumes durable writes for any
            # NEW message (this decision is re-evaluated on every call,
            # not cached for the conversation's lifetime).
            if memory_enabled:
                rt.repo.create_message(user_message)
            else:
                # The conversation itself may have been created DURABLY
                # (memory was on at the time) and only turned off later
                # mid-conversation — register a shadow ephemeral entry so
                # this turn's messages aren't silently dropped for lack of
                # a container to attach to.
                if rt.ephemeral.get_conversation(conversation_id) is None:
                    rt.ephemeral.create_conversation(conv)
                rt.ephemeral.create_message(user_message)

            retrieval_block = ""
            citations: List[Any] = []
            if conv.mode == "story" and conv.context_novel_id:
                results = retrieve_story_chunks(
                    rt.tool_ctx, payload.content, novel_id=conv.context_novel_id,
                    current_chapter_index=int((conv.context_chapter_id and 1) or 1),
                    user_id=profile.user_id)
                if results:
                    citations = citations_for(results)
                    retrieval_block = "DỮ LIỆU TRUYỆN TRUY XUẤT ĐƯỢC:\n" + "\n---\n".join(
                        r.chunk_text for r in results)
            if payload.use_library:
                hits = search_library(rt.tool_ctx, payload.content)
                if hits:
                    retrieval_block_extra = "\n\nKẾT QUẢ THƯ VIỆN:\n" + "\n".join(
                        f"- {h.title} ({h.author})" for h in hits)
                    retrieval_block = retrieval_block + retrieval_block_extra
            if payload.use_web_search and rt.web_search_enabled:
                web_hits = web_search(rt.tool_ctx, payload.content)
                block = format_web_results_for_prompt(web_hits)
                if block:
                    retrieval_block = retrieval_block + "\n\n" + block

            # Always pass the COMBINED (durable + ephemeral) recent-message
            # list explicitly — this is what makes the CURRENT user turn
            # (just written above, to whichever store) visible to the
            # model even when memory is off (it would otherwise be
            # invisible to `repo.list_messages`, which never sees the
            # ephemeral store). `memory_enabled=False` still correctly
            # skips injecting saved preferences/summary (`build_context`'s
            # own gate), and no summary is ever generated in this feature
            # yet regardless of the flag.
            recent = _recent_messages_combined(conversation_id, limit=50)
            turns = build_context(
                mode=conv.mode, assistant_name=rt.assistant_name, repo=rt.repo,
                user_id=profile.user_id, conversation_id=conversation_id,
                memory_enabled=memory_enabled,
                max_context_tokens=8000 if conv.mode == "writer" else 6000,
                retrieval_block_text=retrieval_block, pending_recent_messages=recent)
            return turns, citations, memory_enabled

        try:
            turns, citations, memory_enabled = await run_in_threadpool(_prepare)
        except Exception:
            rt.stream_guard.release(profile.user_id)
            raise

        assistant_message_id = _new_id()
        prompt_text = "\n".join(t.content for t in turns)

        async def _generate():
            text_parts: List[str] = []
            in_tok = out_tok = 0
            final_status = "complete"
            error_payload: Optional[Dict[str, Any]] = None
            yield _sse("meta", {"message_id": assistant_message_id, "conversation_id": conversation_id})
            try:
                gen = rt.gateway.stream(turns, mode=conv.mode, user_ref=profile.user_id)
                # R3 (review finding): `contextlib.closing` guarantees the
                # provider's underlying generator (which holds the httpx
                # streaming context manager / upstream connection open) is
                # closed DETERMINISTICALLY the moment we stop iterating —
                # on a client disconnect (`break` below) or on any
                # exception — rather than relying on eventual GC.
                with contextlib.closing(gen):
                    async for ev in iterate_in_threadpool(gen):
                        if await request.is_disconnected():
                            final_status = "stopped"
                            break
                        if isinstance(ev, Delta):
                            text_parts.append(ev.text)
                            yield _sse("delta", {"text": ev.text})
                        elif isinstance(ev, UsageEvent):
                            in_tok, out_tok = ev.input_tokens, ev.output_tokens
                        elif isinstance(ev, ErrorEvent):
                            final_status = "error"
                            error_payload = {"code": ev.code, "message": ev.message}
                            break
                        elif isinstance(ev, Done):
                            pass
            finally:
                rt.stream_guard.release(profile.user_id)

            final_text = "".join(text_parts)
            if citations:
                yield _sse("citations", {"items": [
                    {"novel_id": c.novel_id, "chapter_id": c.chapter_id,
                     "chapter_title": c.chapter_title, "excerpt": c.excerpt}
                    for c in citations]})

            # R2 (review finding): budget must never be bypassed just
            # because a provider omitted/zeroed its own usage report — an
            # interrupted/stopped/error stream that still produced text is
            # billed on an ESTIMATE (contract §3's own conservative
            # chars/3.5 estimator) covering the prompt actually sent plus
            # whatever text was actually generated. Nothing is charged for
            # a turn that produced NEITHER real usage NOR any text (a pure
            # before-first-delta failure) — see docs/ai/AI_ASSISTANT_V1.md
            # "Implementation notes".
            estimated_in = estimate_tokens(prompt_text)
            estimated_out = estimate_tokens(final_text)
            counted_in = in_tok or estimated_in
            counted_out = out_tok or estimated_out
            if final_text or in_tok or out_tok:
                budget = await run_in_threadpool(
                    lambda: record_usage(
                        rt.repo, user_id=profile.user_id, input_tokens=counted_in,
                        output_tokens=counted_out, daily_limit=daily_limit))
            else:
                counted_in = counted_out = 0
                budget = await run_in_threadpool(
                    lambda: budget_status(rt.repo, user_id=profile.user_id, daily_limit=daily_limit))
            yield _sse("usage", {"input_tokens": counted_in, "output_tokens": counted_out,
                                 "used_today": budget.used_today, "limit_today": budget.limit_today})

            if final_text:
                citations_json = json.dumps([
                    {"novel_id": c.novel_id, "chapter_id": c.chapter_id} for c in citations],
                    ensure_ascii=False)
                assistant_message = AiMessage(
                    message_id=assistant_message_id, conversation_id=conversation_id,
                    user_id=profile.user_id, role="assistant", content=final_text,
                    status=final_status, citations_json=citations_json,
                    provider_name="", model="", input_tokens=counted_in,
                    output_tokens=counted_out)
                # Same store as the user turn above (contract §5): durable
                # when memory is on, TTL-bounded in-process cache when off
                # — an assistant reply is exactly as much "memory" as the
                # question it answers, so it follows the identical rule.
                if memory_enabled:
                    await run_in_threadpool(rt.repo.create_message, assistant_message)
                else:
                    await run_in_threadpool(rt.ephemeral.create_message, assistant_message)

            if error_payload is not None:
                yield _sse("error", error_payload)
            else:
                yield _sse("done", {"status": final_status})

        return StreamingResponse(_generate(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    # ---------------------------------------------------------------- preferences
    @r.get("/api/ai/preferences")
    def get_preferences(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = resolve_profile(authorization)
        prefs = rt.repo.get_preferences(profile.user_id)
        if prefs is None:
            return {"memory_enabled": True, "preferences": {}}
        return {"memory_enabled": prefs.memory_enabled,
                "preferences": json.loads(prefs.preferences_json or "{}")}

    @r.put("/api/ai/preferences")
    def put_preferences(payload: PreferencesIn,
                        authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = resolve_profile(authorization)
        prefs = AiPreferences(
            user_id=profile.user_id, memory_enabled=payload.memory_enabled,
            preferences_json=json.dumps(payload.preferences, ensure_ascii=False)[:2000])
        rt.repo.put_preferences(prefs)
        return {"memory_enabled": prefs.memory_enabled,
                "preferences": json.loads(prefs.preferences_json)}

    @r.delete("/api/ai/memory")
    def delete_memory(include_projects: bool = False,
                      authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = resolve_profile(authorization)
        rt.repo.delete_all_memory(profile.user_id, include_projects=include_projects)
        # Also clears any live ephemeral (memory-off) entries for this
        # user — a superset of the ≤1h TTL guarantee, not a requirement of
        # it, but "xoá toàn bộ ký ức AI" should mean exactly that from the
        # user's point of view, not "except whatever's still in the
        # in-process cache for the next little while".
        rt.ephemeral.delete_all_for_user(profile.user_id)
        return {"deleted": True}

    # ---------------------------------------------------------------- projects
    @r.get("/api/ai/projects")
    def list_projects(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = resolve_profile(authorization)
        items = rt.repo.list_projects(profile.user_id)
        return {"items": [{"project_id": p.project_id, "title": p.title, "updated_at": p.updated_at}
                          for p in items]}

    @r.post("/api/ai/projects")
    def create_project(payload: ProjectIn,
                       authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = resolve_profile(authorization)
        proj = AiProject(
            project_id=_new_id(), user_id=profile.user_id, title=payload.title,
            premise=payload.premise, outline_json=json.dumps(payload.outline, ensure_ascii=False),
            characters_json=json.dumps(payload.characters, ensure_ascii=False),
            world_json=json.dumps(payload.world, ensure_ascii=False), notes=payload.notes)
        proj = _run(lambda: rt.repo.create_project(proj))
        return {"project_id": proj.project_id}

    @r.get("/api/ai/projects/{project_id}")
    def get_project(project_id: ProjectId,
                    authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = resolve_profile(authorization)
        p = _own_project(profile.user_id, project_id)
        return {"project_id": p.project_id, "title": p.title, "premise": p.premise,
                "outline": json.loads(p.outline_json or "{}"),
                "characters": json.loads(p.characters_json or "{}"),
                "world": json.loads(p.world_json or "{}"), "notes": p.notes,
                "updated_at": p.updated_at}

    @r.put("/api/ai/projects/{project_id}")
    def update_project(project_id: ProjectId, payload: ProjectIn,
                       authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = resolve_profile(authorization)
        _own_project(profile.user_id, project_id)
        p = rt.repo.update_project(project_id, {
            "title": payload.title, "premise": payload.premise,
            "outline_json": json.dumps(payload.outline, ensure_ascii=False),
            "characters_json": json.dumps(payload.characters, ensure_ascii=False),
            "world_json": json.dumps(payload.world, ensure_ascii=False), "notes": payload.notes})
        return {"project_id": p.project_id, "updated_at": p.updated_at}

    @r.delete("/api/ai/projects/{project_id}")
    def delete_project(project_id: ProjectId,
                       authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = resolve_profile(authorization)
        _own_project(profile.user_id, project_id)
        rt.repo.delete_project(project_id)
        return {"deleted": True}

    # ---------------------------------------------------------------- support
    @r.post("/api/ai/support/escalations")
    def create_escalation(payload: EscalationIn,
                          authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = resolve_profile(authorization)
        esc = AiEscalation(
            escalation_id=_new_id(), user_id=profile.user_id,
            conversation_id=payload.conversation_id or "", summary=payload.summary)
        esc = _run(lambda: rt.repo.create_escalation(esc))
        return {"escalation_id": esc.escalation_id, "status": esc.status}

    return r
