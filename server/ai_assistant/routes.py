"""
Routes — Fanfic AI Assistant V1 §10. `FAS_AI_ASSISTANT_V1=0` (default) ->
every route except `GET /api/ai/availability` returns 503 `ai_not_enabled`.
Streaming (`POST /api/ai/conversations/{id}/messages`) never blocks the
event loop: the gateway's provider iterator is a plain sync generator
(httpx sync streaming under the hood) iterated on a dedicated pump thread
(`stream_pump.py`) — never on the asyncio loop (contract §0.2's explicit
lesson: "a Render process starved of threads hangs even /api/health"). The
route waits on the pump with a timeout and sends an SSE comment heartbeat
(`SSE_HEARTBEAT`) every `AiRuntime.heartbeat_s` seconds of provider silence.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

import anyio
from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, StringConstraints
from typing_extensions import Annotated

from server.ai_assistant.config import (
    MAX_CONVERSATIONS_PER_USER, MAX_USER_MESSAGE_CHARS, MODES, estimate_tokens,
)
from server.ai_assistant.context_builder import build_context
from server.ai_assistant.gateway import ErrorEvent, ProviderServed
from server.ai_assistant.limits import (
    AiBudgetExceeded, AiBusy, AiRateLimited, budget_status, compute_allowance, enforce_budget, qa_allowance,
    qa_ledger_user, record_usage,
)
from server.ai_assistant.scopes import SCOPE_GLOBAL
from server.ai_assistant.memory import (
    AiConversation, AiEscalation, AiMessage, AiPreferences, AiProject, AiUnavailable, RepoConflict,
    now_iso, redact,
)
from server.ai_assistant.runtime import AiRuntime
from server.ai_assistant.stream_pump import END, SILENCE, PumpError, StreamPump
from server.ai_assistant.prompts import STORY_NO_CHAPTER_NOTE
from server.ai_assistant.tools import (
    UNTRUSTED_DATA_PREAMBLE, citations_for, current_chapter_excerpt,
    format_web_results_for_prompt, retrieve_story_chunks, search_library, web_search,
)
from server.llm_gateway.chat_provider import Delta, Done, UsageEvent

log = logging.getLogger("fanfic.ai_assistant")

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
    #: Lần QA của Owner (smoke test): chỉ có hiệu lực khi người gọi là Owner VÀ control plane đang bật; với
    #: người khác cờ bị BỎ QUA (lượt tính như lượt thường, không báo lỗi). Lượt QA ghi vào sổ QA riêng, không
    #: ăn vào hạn mức người dùng thường, nhưng VẪN bị công tắc khẩn cấp và trần toàn cục chặn.
    qa: bool = False


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


#: SSE COMMENT line (spec: a line starting with ":" is ignored by every
#: EventSource/parser) — keeps idle proxies from closing the response while a
#: provider is silent, and can never be mistaken for assistant content: it
#: has no `event:`/`data:` field at all. The web client's parser
#: (`web/src/lib/ai/sse.ts::tachKhungSse`) drops ":" lines before framing.
SSE_HEARTBEAT = ": ping\n\n"

#: A failure ABOVE the provider layer (the gateway converts every provider
#: failure itself) — reuses a stable §10 code rather than inventing one the
#: client doesn't know; the real exception stays in the server log only.
_INTERNAL_ERROR = {"code": "ai_provider_unavailable",
                   "message": "Trợ lý AI đang tạm gián đoạn — thử lại sau."}


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


def _hashed_user_ref(rt: AiRuntime, user_id: str) -> str:
    """M8 (review finding): `GenerateRequest.user_ref`'s own contract is
    "HASH of the real user id, never the raw id" — this call previously
    passed `profile.user_id` straight through, handing every real user id
    to whichever LLM provider is in the fallback chain. HMAC-SHA256 keyed
    on a server-side salt (never the raw id, never reversible without that
    salt) — see `AiRuntime.user_ref_salt`'s own docstring for the salt's
    source/fallback."""
    return hmac.new(rt.user_ref_salt.encode("utf-8"), user_id.encode("utf-8"),
                    hashlib.sha256).hexdigest()


def build_ai_router(rt: AiRuntime, *, resolve_profile: Callable[[Optional[str]], Any]) -> APIRouter:
    r = APIRouter()

    def _bat() -> AiRuntime:
        if not rt.serving():
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                {"code": "ai_not_enabled",
                                 "message": "Trợ lý AI chưa được bật trên máy chủ."})
        return rt

    def _profile(authorization: Optional[str]) -> Any:
        """Ho so nguoi goi (401 neu chua dang nhap), VA nguoi do phai trong khan gia
        (`FAS_AI_AUDIENCE`) — ngoai khan gia: 403 `ai_not_enabled` (ma on dinh client da
        biet). Moi route tru availability di qua day; kiem o MOI request nen go mot
        ID khoi `FAS_AI_CANARY_USERS` co hieu luc o lan deploy ke tiep."""
        profile = resolve_profile(authorization)
        if not rt.allows(getattr(profile, "user_id", "") or ""):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                {"code": "ai_not_enabled",
                                 "message": "Trợ lý AI chưa mở cho tài khoản này."})
        return profile

    def _run(f: Callable[[], Any]) -> Any:
        try:
            return f()
        except AiRateLimited as exc:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                {"code": "ai_rate_limited", "message": str(exc)}) from exc
        except AiBudgetExceeded as exc:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                {"code": "ai_budget_exhausted", "message": str(exc),
                                 "reset_at": exc.reset_at, "scope": exc.scope}) from exc
        except AiBusy as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                {"code": "ai_busy", "message": str(exc)}) from exc
        except AiUnavailable as exc:
            # H5/L12 (review finding): the repo layer (Appwrite down, a
            # bounded field rejected with a 400 the caller never validated,
            # ...) raises `AiUnavailable` — previously uncaught here, so it
            # fell through to FastAPI's default handler as an opaque 500.
            # Every `rt.repo.*`/`rt.ephemeral.*` call site in this router
            # now goes through `_run()` specifically so this is the ONE
            # place that maps it to a stable 503.
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                {"code": "ai_storage_unavailable", "message": str(exc)}) from exc

    def _memory_enabled(user_id: str) -> bool:
        prefs = _run(lambda: rt.repo.get_preferences(user_id))
        return prefs.memory_enabled if prefs else True

    def _find_conversation(conversation_id: str):
        """Checks BOTH the durable repo and the ephemeral (`memory_enabled
        =false`) store — a conversation lives in exactly one of the two at
        any moment, decided at `create_conversation` time. Returns
        `(conversation, is_ephemeral)`."""
        conv = _run(lambda: rt.repo.get_conversation(conversation_id))
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
        durable = _run(lambda: rt.repo.list_messages(conversation_id, limit=limit))
        ephemeral = rt.ephemeral.list_messages(conversation_id, limit=limit)
        by_id = {m.message_id: m for m in durable}
        for m in ephemeral:
            by_id[m.message_id] = m
        merged = sorted(by_id.values(), key=lambda m: m.created_at)
        return merged[-limit:]

    def _own_project(user_id: str, project_id: str) -> AiProject:
        proj = _run(lambda: rt.repo.get_project(project_id))
        if proj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                {"code": "ai_not_found", "message": "Không tìm thấy dự án."})
        if proj.user_id != user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                {"code": "ai_forbidden", "message": "Dự án này không thuộc về bạn."})
        return proj

    def _user_allowance(status_: Any) -> Any:
        """Hạn mức riêng của người gọi từ MỘT bản ghi sổ đã đọc (không tốn thêm lần đọc): trần lượt/token của
        control plane (nếu bật) + ngân sách token hạng tài khoản cũ. Không chứa số liệu toàn cục."""
        req_cap, tok_cap = rt.control.user_caps() if rt.control is not None else (0, 0)
        return compute_allowance(requests_used=status_.requests_used, tokens_used=status_.used_today,
                                 request_cap=req_cap, token_cap=tok_cap, legacy_token_limit=status_.limit_today,
                                 reset_at=status_.reset_at)

    def _access(authorization: Optional[str]) -> Tuple[Any, str]:
        """Ho so (401 neu chua dang nhap) + `AiRuntime.access_state` — CUNG mot phan quyet cho
        availability va `/api/ai/access`, de nut mo tro ly khong bao gio hien theo mot luat khac
        luat cua route that."""
        profile = resolve_profile(authorization)
        return profile, rt.access_state(getattr(profile, "user_id", "") or "")

    # ---------------------------------------------------------------- access (cong UI)
    @r.get("/api/ai/access")
    def access(response: Response,
               authorization: Optional[str] = Header(default=None)) -> Dict[str, bool]:
        """MOT bit cho frontend: co ve loi vao Tro ly AI cho nguoi dang dang nhap khong.
        Co y KHONG tra ly do, khan gia, danh sach, han muc hay provider — chi `eligible`.
        Day chi la cong HIEN THI: moi route `/api/ai/*` van tu chan o moi request."""
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Vary"] = "Authorization"
        _, state = _access(authorization)
        return {"eligible": state == "ok"}

    # ---------------------------------------------------------------- availability
    @r.get("/api/ai/availability")
    def availability(response: Response,
                     authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        profile, state = _access(authorization)
        if state == "off":
            return {"enabled": False, "reason": rt.reason or "off", "name": rt.assistant_name,
                    "modes": [], "web_search": False}
        # Ngoai khan gia, hoac tat khan cap (`/admin/ai`, fail-closed): nhu AI tat — khong lo
        # han muc/cau hinh.
        if state != "ok":
            return {"enabled": False, "reason": state, "name": rt.assistant_name,
                    "modes": [], "web_search": False}
        tier = _tier_of(profile)
        status_ = budget_status(rt.repo, user_id=profile.user_id, daily_limit=_daily_limit(rt, tier))
        # `memory_enabled` here is informational (same source as GET
        # /api/ai/preferences) — usage limits below are ALWAYS from the
        # durable ai_usage_daily ledger regardless of this flag (contract
        # §5/§9: usage metering keeps recording, content does not).
        #
        # `limits` = hạn mức RIÊNG của người gọi, đúng thứ `post_message` sẽ thực thi: `requests_*` +
        # `exhausted` + `reset_at`. KHÔNG có mức dùng toàn site hay công suất nhà cung cấp (chỉ ở /admin/ai).
        # `used_today`/`limit_today` (token, ngân sách hạng tài khoản cũ) giữ lại để bản giao diện cũ trong
        # bộ nhớ đệm không vỡ; giao diện mới không dùng chúng.
        out: Dict[str, Any] = {
            "enabled": True, "reason": None, "name": rt.assistant_name, "modes": list(MODES),
            "web_search": rt.web_search_enabled, "memory_enabled": _memory_enabled(profile.user_id),
            "limits": {"used_today": status_.used_today, "limit_today": status_.limit_today,
                       **_user_allowance(status_).to_public()}}
        if rt.control is not None and rt.is_owner(profile.user_id):
            # Chỉ Owner thấy hạn mức QA của mình (để smoke test biết còn bao nhiêu lượt QA). Lỗi đọc sổ QA
            # không bao giờ làm hỏng availability.
            try:
                qa_status = budget_status(rt.repo, user_id=qa_ledger_user(profile.user_id), daily_limit=0)
                out["qa"] = qa_allowance(requests_used=qa_status.requests_used,
                                         daily_cap=rt.owner_qa_daily_requests, reset_at=qa_status.reset_at).to_public()
            except AiUnavailable:
                pass
        return out

    # ---------------------------------------------------------------- conversations
    @r.get("/api/ai/conversations")
    def list_conversations(limit: int = 30, cursor: Optional[str] = None,
                           authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = _profile(authorization)
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
        profile = _profile(authorization)
        # M11 (review finding): creating a conversation previously had NO
        # rate limit at all (every other write route enforces `rt.rpm`)
        # and only counted DURABLE conversations against
        # `MAX_CONVERSATIONS_PER_USER` — a memory-off user could open
        # unlimited ephemeral conversations (bounded only by the
        # ephemeral store's own GLOBAL, cross-user cap, see
        # `ephemeral.py`), which also meant one heavy memory-off user
        # could crowd out another user's ephemeral history.
        _run(lambda: rt.rpm_limiter.check(profile.user_id, rpm=rt.rpm))
        mode = payload.mode if payload.mode in MODES else "general"
        durable_count = _run(lambda: rt.repo.count_conversations(profile.user_id))
        ephemeral_count = len(rt.ephemeral.list_conversations(profile.user_id))
        if durable_count + ephemeral_count >= MAX_CONVERSATIONS_PER_USER:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                {"code": "ai_context_too_large",
                                 "message": f"Đã đạt tối đa {MAX_CONVERSATIONS_PER_USER} hội thoại."})
        ctx = payload.context or ContextIn()
        conv = AiConversation(
            conversation_id=_new_id(), user_id=profile.user_id, mode=mode,
            title=(payload.title or "")[:120], context_novel_id=(ctx.novel_id or "")[:64],
            context_chapter_id=(ctx.chapter_id or "")[:64], context_project_id=(ctx.project_id or "")[:64],
            context_chapter_index=max(1, int(ctx.current_chapter_index or 1)))
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
        profile = _profile(authorization)
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
        profile = _profile(authorization)
        _own_conversation(profile.user_id, conversation_id)
        # Harmless no-op on whichever store the conversation ISN'T in.
        _run(lambda: rt.repo.delete_conversation(conversation_id))
        rt.ephemeral.delete_conversation(conversation_id)
        return {"deleted": True}

    # ---------------------------------------------------------------- messages (SSE)
    @r.post("/api/ai/conversations/{conversation_id}/messages")
    async def post_message(conversation_id: ConvId, payload: MessageIn, request: Request,
                           authorization: Optional[str] = Header(default=None)):
        _bat()
        # H3 (review finding): `resolve_profile` and `_own_conversation` can
        # each make a real Appwrite HTTP call (session lookup, conversation
        # read) — calling them directly on THIS coroutine (the only truly
        # `async def` route in this router; every `def` route is already
        # offloaded to a threadpool by Starlette itself) blocks the asyncio
        # event loop for the duration of that round-trip, stalling every
        # OTHER concurrent request this worker is serving (same lesson as
        # the streaming path itself, contract §0.2). `run_in_threadpool`
        # moves both off the loop.
        profile = await run_in_threadpool(_profile, authorization)
        conv, _ = await run_in_threadpool(_own_conversation, profile.user_id, conversation_id)
        _run(lambda: rt.rpm_limiter.check(profile.user_id, rpm=rt.rpm))
        # Lối QA của Owner: cờ `qa` chỉ có hiệu lực với Owner + control plane bật (xem `AiRuntime.qa_lane`).
        # Lượt QA đếm vào sổ QA riêng (`ledger_user`), KHÔNG vào sổ người dùng thường; mọi thứ khác (công tắc
        # khẩn cấp, trần toàn cục, slot, RPM) áp y hệt lượt thường.
        qa = rt.qa_lane(profile.user_id, payload.qa)
        ledger_user = qa_ledger_user(profile.user_id) if qa else profile.user_id
        if rt.control is not None:
            # Kill switch + global/per-user daily ceilings from the control
            # plane (reads the store -> off the event loop).
            denied = await run_in_threadpool(
                lambda: rt.control.admission(profile.user_id, qa_ledger_user=ledger_user if qa else "",
                                             qa_daily_cap=rt.owner_qa_daily_requests))
            if denied is not None:
                detail: Dict[str, Any] = {"code": denied.code, "message": denied.message}
                if denied.reset_at:
                    detail["reset_at"] = denied.reset_at
                if denied.scope:
                    detail["scope"] = denied.scope
                raise HTTPException(denied.status, detail)
        tier = _tier_of(profile)
        daily_limit = _daily_limit(rt, tier)
        # R4 (review finding): `enforce_budget`/`get_preferences`/`create_message`/
        # `build_context` all touch `rt.repo`, which for `AppwriteAiRepo` means
        # real HTTP calls — every one of them runs via `run_in_threadpool`
        # below so a slow Appwrite round-trip never blocks the asyncio loop
        # (same lesson as the streaming path itself, contract §0.2).
        if not qa:  # lối QA bị chặn bởi hạn mức QA ở `admission`, không phải ngân sách token hạng tài khoản
            await run_in_threadpool(
                lambda: _run(lambda: enforce_budget(rt.repo, user_id=profile.user_id, daily_limit=daily_limit)))
        _run(lambda: rt.stream_guard.acquire(profile.user_id))

        def _prepare():
            memory_enabled = _memory_enabled(profile.user_id)

            # M7 (review finding): secrets must be redacted BEFORE anything
            # reaches a provider — the ONLY existing redaction
            # (`AppwriteAiRepo.create_message`) ran on write for the
            # DURABLE repo alone, so `InMemoryAiRepo`, the ephemeral
            # (memory-off) store, AND every retrieval/web-search QUERY
            # built from the raw `payload.content` all carried secret-
            # shaped substrings straight through to the model. Redacting
            # ONCE here, before it's used for anything, fixes persistence
            # (both stores) and every downstream use in one place — the
            # redacted copy is also what a LATER turn's context/history
            # reads back (`_recent_messages_combined` -> `build_context`),
            # since it's the exact object stored below.
            redacted_content = redact(payload.content)

            user_message = AiMessage(
                message_id=_new_id(), conversation_id=conversation_id, user_id=profile.user_id,
                role="user", content=redacted_content, client_id=payload.client_id)
            # contract §5: while memory is OFF, this write goes ONLY to the
            # in-process TTL cache — NEVER to `rt.repo`/Appwrite. Toggling
            # memory back ON immediately resumes durable writes for any
            # NEW message (this decision is re-evaluated on every call,
            # not cached for the conversation's lifetime).
            if memory_enabled:
                _run(lambda: rt.repo.create_message(user_message))
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
            if conv.mode == "story":
                # Story mode V1 (release gate B): the ONLY story text is a
                # capped excerpt of the chapter the user has open, and only
                # if they may read it (checked per turn). No excerpt -> an
                # explicit "you have no chapter text" note, so the model says
                # so instead of inventing plot.
                excerpt = current_chapter_excerpt(
                    rt.tool_ctx, novel_id=conv.context_novel_id,
                    chapter_id=conv.context_chapter_id, user_id=profile.user_id)
                if excerpt is not None:
                    tieu_de = redact(excerpt.chapter_title) or "(không tên)"
                    cat = f", đã cắt còn {len(excerpt.text)} ký tự đầu" if excerpt.truncated else ""
                    # The chapter is fixed when the conversation is created
                    # (the reader's "Hỏi về chương này" button) — say so, with
                    # its title, so a later "this chapter" about ANOTHER
                    # chapter gets an honest answer.
                    retrieval_block = (
                        UNTRUSTED_DATA_PREAMBLE
                        + f"\nCHƯƠNG CỦA HỘI THOẠI NÀY (người dùng mở khi bắt đầu hội thoại) — «{tieu_de}»{cat}:\n"
                        + redact(excerpt.text))
                else:
                    retrieval_block = STORY_NO_CHAPTER_NOTE
            if conv.mode == "story" and conv.context_novel_id:
                # L12/M10 (review finding): honor the conversation's ACTUAL
                # `current_chapter_index` (was hard-coded to `1` regardless
                # of what the client sent, defeating spoiler protection past
                # chapter 1) — read permission on `context_novel_id` is
                # enforced INSIDE `retrieve_story_chunks` itself (fails
                # closed when unwired; see `ToolContext.may_read_novel_fn`).
                results = retrieve_story_chunks(
                    rt.tool_ctx, redacted_content, novel_id=conv.context_novel_id,
                    current_chapter_index=conv.context_chapter_index,
                    user_id=profile.user_id)
                if results:
                    citations = citations_for(results)
                    # M10 (review finding): retrieved story text is
                    # UNTRUSTED (chapter content a THIRD PARTY may have
                    # authored, not the operator) — wrap with the same
                    # preamble already used for web results (contract §8),
                    # and redact it too (M7) before it ever reaches a turn.
                    # Appended AFTER the current-chapter block: this path
                    # stays fail-closed until a vector index is wired.
                    retrieved = UNTRUSTED_DATA_PREAMBLE + "\nDỮ LIỆU TRUYỆN TRUY XUẤT ĐƯỢC:\n" + \
                        "\n---\n".join(redact(r.chunk_text) for r in results)
                    retrieval_block = retrieval_block + "\n\n" + retrieved
            if payload.use_library:
                hits = search_library(rt.tool_ctx, redacted_content)
                if hits:
                    retrieval_block_extra = "\n\n" + UNTRUSTED_DATA_PREAMBLE + "\nKẾT QUẢ THƯ VIỆN:\n" + \
                        "\n".join(redact(f"- {h.title} ({h.author})") for h in hits)
                    retrieval_block = retrieval_block + retrieval_block_extra
            if payload.use_web_search and rt.web_search_enabled:
                web_hits = web_search(rt.tool_ctx, redacted_content)
                block = format_web_results_for_prompt(web_hits)  # already carries its own preamble
                if block:
                    retrieval_block = retrieval_block + "\n\n" + redact(block)

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
            finalize_result: Dict[str, Any] = {}
            served: Dict[str, str] = {"provider_name": "", "model": ""}

            async def _finalize() -> None:
                """Records usage + persists the assistant message — MUST run
                exactly once per turn, on every exit path (normal
                completion, provider error, AND client disconnect). Called
                from `finally` below under a shielded cancel scope (B2
                review finding): on a client disconnect, Starlette's
                `StreamingResponse` races `stream_response()` against
                `listen_for_disconnect()` in one `anyio` task group and
                cancels the loser — that cancellation lands as a
                `CancelledError` at whatever `await` this coroutine is
                suspended on, unwinds the `async for` below, and (without
                the shield) would ALSO cancel any further `await` made
                while handling it, silently dropping billed usage and the
                partial assistant reply on the floor. `anyio.CancelScope
                (shield=True)` makes this block immune to that outer
                cancellation so the repo/ephemeral writes below always
                complete."""
                final_text = "".join(text_parts)
                # R2 (review finding, kept): budget must never be bypassed
                # just because a provider omitted/zeroed its own usage
                # report — an interrupted/stopped/error stream that still
                # produced text is billed on an ESTIMATE (contract §3's own
                # conservative chars/3.5 estimator) covering the prompt
                # actually sent plus whatever text was actually generated.
                # Nothing is charged for a turn that produced NEITHER real
                # usage NOR any text (a pure before-first-delta failure).
                estimated_in = estimate_tokens(prompt_text)
                estimated_out = estimate_tokens(final_text)
                counted_in = in_tok or estimated_in
                counted_out = out_tok or estimated_out
                if final_text or in_tok or out_tok:
                    budget = await run_in_threadpool(
                        lambda: record_usage(
                            rt.repo, user_id=ledger_user, input_tokens=counted_in,
                            output_tokens=counted_out, daily_limit=daily_limit))
                else:
                    counted_in = counted_out = 0
                    budget = await run_in_threadpool(
                        lambda: budget_status(rt.repo, user_id=ledger_user, daily_limit=daily_limit))

                if final_text:
                    citations_json = json.dumps([
                        {"novel_id": c.novel_id, "chapter_id": c.chapter_id} for c in citations],
                        ensure_ascii=False)
                    assistant_message = AiMessage(
                        message_id=assistant_message_id, conversation_id=conversation_id,
                        user_id=profile.user_id, role="assistant", content=final_text,
                        status=final_status, citations_json=citations_json,
                        # Caps = `ai_messages` attribute sizes in scripts/setup_appwrite.py.
                        provider_name=served["provider_name"][:40], model=served["model"][:80],
                        input_tokens=counted_in,
                        output_tokens=counted_out)
                    # Same store as the user turn above (contract §5): durable
                    # when memory is on, TTL-bounded in-process cache when off
                    # — an assistant reply is exactly as much "memory" as the
                    # question it answers, so it follows the identical rule.
                    if memory_enabled:
                        await run_in_threadpool(rt.repo.create_message, assistant_message)
                    else:
                        await run_in_threadpool(rt.ephemeral.create_message, assistant_message)

                finalize_result["counted_in"] = counted_in
                finalize_result["counted_out"] = counted_out
                finalize_result["budget"] = budget
                # Hạn mức RIÊNG sau lượt này (cho sự kiện `usage`): lối QA báo hạn mức QA, lối thường báo hạn
                # mức người dùng. Không bao giờ làm hỏng lượt: lỗi thì bỏ trường `allowance`.
                try:
                    finalize_result["allowance"] = (
                        qa_allowance(requests_used=budget.requests_used, daily_cap=rt.owner_qa_daily_requests,
                                     reset_at=budget.reset_at) if qa
                        else await run_in_threadpool(_user_allowance, budget))
                except Exception:  # noqa: BLE001
                    log.warning("ai_assistant: allowance for the usage event failed", exc_info=True)
                if rt.control is not None and served["provider_name"]:
                    # Per-SLOT usage/cost for the control plane (provider_name
                    # is the slot id there). Never allowed to fail the turn.
                    try:
                        await run_in_threadpool(rt.control.record_turn, served["provider_name"],
                                                counted_in, counted_out, final_status)
                    except Exception:  # noqa: BLE001
                        log.warning("ai_assistant: control-plane usage record failed", exc_info=True)

            yield _sse("meta", {"message_id": assistant_message_id, "conversation_id": conversation_id})
            pump: Optional[StreamPump] = None
            try:
                # Web-search turns route through their own profile (control
                # plane `web_search_profile`); `AiGateway` ignores `workload`.
                workload = "web_search" if (payload.use_web_search and rt.web_search_enabled) else None
                gen = rt.gateway.stream(turns, mode=conv.mode,
                                       user_ref=_hashed_user_ref(rt, profile.user_id), workload=workload)
                # The provider generator runs on the pump's own thread
                # (never on the event loop, contract §0.2) and is closed
                # THERE under `contextlib.closing` (R3) the moment
                # iteration stops — see `stream_pump.py`. Waiting with a
                # timeout is what makes the heartbeat possible: a silent
                # provider yields `SILENCE` every `rt.heartbeat_s` seconds
                # instead of one opaque, unbounded `await`.
                pump = StreamPump(gen).start()
                while True:
                    ev = await pump.next(rt.heartbeat_s)
                    if ev is SILENCE:
                        if await request.is_disconnected():
                            final_status = "stopped"
                            break
                        yield SSE_HEARTBEAT
                        continue
                    if ev is END:
                        break
                    if await request.is_disconnected():
                        final_status = "stopped"
                        break
                    if isinstance(ev, PumpError):
                        # The gateway already converts every provider
                        # failure into an `ErrorEvent`; reaching this means a
                        # bug above the provider layer. Fixed message only —
                        # the exception text stays in the server log.
                        log.error("ai_assistant: stream pump failed: %s", type(ev.exc).__name__,
                                  exc_info=ev.exc)
                        final_status = "error"
                        error_payload = dict(_INTERNAL_ERROR)
                        break
                    if isinstance(ev, Delta):
                        text_parts.append(ev.text)
                        yield _sse("delta", {"text": ev.text})
                    elif isinstance(ev, ProviderServed):
                        # Server-side only (persisted for per-provider usage
                        # counting); NEVER forwarded over SSE (§0.3).
                        served["provider_name"], served["model"] = ev.provider_name, ev.model
                    elif isinstance(ev, UsageEvent):
                        in_tok, out_tok = ev.input_tokens, ev.output_tokens
                    elif isinstance(ev, ErrorEvent):
                        final_status = "error"
                        error_payload = {"code": ev.code, "message": ev.message}
                        break
                    elif isinstance(ev, Done):
                        pass
            except BaseException:
                # B2 (review finding): reached on a real client disconnect —
                # the task group above cancels this coroutine mid-`async
                # for`, which surfaces here as a `CancelledError` (never a
                # normal `return`). Treat it exactly like an
                # `is_disconnected()`-observed stop for billing/persistence
                # purposes, run `_finalize()` in `finally` below, then
                # re-raise so Starlette's own cancellation bookkeeping still
                # completes correctly.
                final_status = "stopped"
                raise
            finally:
                if pump is not None:
                    # Every exit path (end, error, disconnect/cancel): the
                    # pump thread exits at the provider's next event and
                    # closes the generator itself (no leaked worker).
                    pump.stop()
                try:
                    with anyio.CancelScope(shield=True):
                        await _finalize()
                finally:
                    rt.stream_guard.release(profile.user_id)

            # Everything below is unreachable when the `except BaseException`
            # branch above re-raised (i.e. on a real disconnect) — Starlette
            # has already stopped reading from this generator by then, so
            # there is nothing left to send it anyway.
            if citations:
                yield _sse("citations", {"items": [
                    {"novel_id": c.novel_id, "chapter_id": c.chapter_id,
                     "chapter_title": c.chapter_title, "excerpt": c.excerpt}
                    for c in citations]})

            usage_event: Dict[str, Any] = {
                "input_tokens": finalize_result["counted_in"], "output_tokens": finalize_result["counted_out"],
                "used_today": finalize_result["budget"].used_today,
                "limit_today": finalize_result["budget"].limit_today,
                "lane": "qa" if qa else "user"}
            if finalize_result.get("allowance") is not None:
                usage_event["allowance"] = finalize_result["allowance"].to_public()
            yield _sse("usage", usage_event)

            if error_payload is not None:
                if error_payload.get("code") == "ai_budget_exhausted":
                    # Các slot đều chạm trần giữa chừng = công suất CHUNG hết, không phải lượt của người này.
                    error_payload.setdefault("scope", SCOPE_GLOBAL)
                    error_payload.setdefault("reset_at", finalize_result["budget"].reset_at)
                yield _sse("error", error_payload)
            else:
                yield _sse("done", {"status": final_status})

        return StreamingResponse(_generate(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    # ---------------------------------------------------------------- preferences
    @r.get("/api/ai/preferences")
    def get_preferences(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = _profile(authorization)
        prefs = _run(lambda: rt.repo.get_preferences(profile.user_id))
        if prefs is None:
            return {"memory_enabled": True, "preferences": {}}
        return {"memory_enabled": prefs.memory_enabled,
                "preferences": json.loads(prefs.preferences_json or "{}")}

    @r.put("/api/ai/preferences")
    def put_preferences(payload: PreferencesIn,
                        authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = _profile(authorization)
        # L12/M7 (review finding): this used to silently `[:2000]`-truncate
        # the serialized JSON — truncating a JSON string mid-structure
        # produces INVALID JSON, so `get_preferences`'s own
        # `json.loads(prefs.preferences_json or "{}")` would then raise on
        # the very next read (a write-time bug surfacing as a read-time
        # 500). Reject oversized input with a clean 400 instead of writing
        # something the reader can't parse back; redact BEFORE persisting
        # (matches the AppwriteAiRepo-only redaction this used to skip for
        # InMemoryAiRepo).
        prefs_json = redact(json.dumps(payload.preferences, ensure_ascii=False))
        if len(prefs_json) > 2000:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                {"code": "ai_context_too_large",
                                 "message": "Sở thích đã lưu quá lớn (tối đa 2000 ký tự)."})
        prefs = AiPreferences(
            user_id=profile.user_id, memory_enabled=payload.memory_enabled,
            preferences_json=prefs_json)
        _run(lambda: rt.repo.put_preferences(prefs))
        return {"memory_enabled": prefs.memory_enabled,
                "preferences": json.loads(prefs.preferences_json)}

    @r.delete("/api/ai/memory")
    def delete_memory(include_projects: bool = False,
                      authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = _profile(authorization)
        _run(lambda: rt.repo.delete_all_memory(profile.user_id, include_projects=include_projects))
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
        profile = _profile(authorization)
        items = _run(lambda: rt.repo.list_projects(profile.user_id))
        return {"items": [{"project_id": p.project_id, "title": p.title, "updated_at": p.updated_at}
                          for p in items]}

    def _bounded_json(value: Dict[str, Any], *, limit: int, field_name: str) -> str:
        """L12 (review finding): `outline`/`characters`/`world` are
        arbitrary user dicts serialized to a size-bounded Appwrite
        attribute — silently `[:N]`-truncating the serialized JSON (as
        `preferences_json` used to) can produce INVALID JSON, corrupting
        the field for every future read. Reject oversized input with a
        clean 400 instead."""
        s = json.dumps(value, ensure_ascii=False)
        if len(s) > limit:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                {"code": "ai_context_too_large",
                                 "message": f"Trường '{field_name}' quá lớn (tối đa {limit} ký tự)."})
        return s

    @r.post("/api/ai/projects")
    def create_project(payload: ProjectIn,
                       authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = _profile(authorization)
        proj = AiProject(
            project_id=_new_id(), user_id=profile.user_id, title=payload.title,
            premise=payload.premise,
            outline_json=_bounded_json(payload.outline, limit=8000, field_name="outline"),
            characters_json=_bounded_json(payload.characters, limit=8000, field_name="characters"),
            world_json=_bounded_json(payload.world, limit=8000, field_name="world"), notes=payload.notes)
        proj = _run(lambda: rt.repo.create_project(proj))
        return {"project_id": proj.project_id}

    @r.get("/api/ai/projects/{project_id}")
    def get_project(project_id: ProjectId,
                    authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = _profile(authorization)
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
        profile = _profile(authorization)
        _own_project(profile.user_id, project_id)
        p = _run(lambda: rt.repo.update_project(project_id, {
            "title": payload.title, "premise": payload.premise,
            "outline_json": _bounded_json(payload.outline, limit=8000, field_name="outline"),
            "characters_json": _bounded_json(payload.characters, limit=8000, field_name="characters"),
            "world_json": _bounded_json(payload.world, limit=8000, field_name="world"),
            "notes": payload.notes}))
        return {"project_id": p.project_id, "updated_at": p.updated_at}

    @r.delete("/api/ai/projects/{project_id}")
    def delete_project(project_id: ProjectId,
                       authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = _profile(authorization)
        _own_project(profile.user_id, project_id)
        _run(lambda: rt.repo.delete_project(project_id))
        return {"deleted": True}

    # ---------------------------------------------------------------- support
    @r.post("/api/ai/support/escalations")
    def create_escalation(payload: EscalationIn,
                          authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        _bat()
        profile = _profile(authorization)
        esc = AiEscalation(
            escalation_id=_new_id(), user_id=profile.user_id,
            conversation_id=payload.conversation_id or "", summary=payload.summary)
        esc = _run(lambda: rt.repo.create_escalation(esc))
        return {"escalation_id": esc.escalation_id, "status": esc.status}

    return r
