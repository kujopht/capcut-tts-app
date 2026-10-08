"""
Router FastAPI `/api/quiz/*` — lop mong tren `QuizService`.

    app.include_router(build_quiz_router(runtime, resolve_profile=current_profile))

`resolve_profile(authorization) -> profile` (co `.user_id`) duoc TIEM tu noi
mount (CTO, `server/main.py`). Module nay KHONG import `server.main`.

Moi loi quiz co dang `{"detail": {"code", "message", ...}}` (`ErrorEnvelope`).
Than request duoc doc tho roi validate bang model strict cua `contracts.py`, de
JSON hong / truong la / sai kieu deu ra CUNG mot dang loi 422.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Type, TypeVar

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ValidationError

from server.quiz.contracts import (
    SHARE_ID_PATTERN, UUID_PATTERN, AdvanceRequest, CsvCommitRequest, CsvValidateRequest,
    DraftCreateRequest, DraftUpdateRequest, ErrorBody, FieldError, PublishRequest,
    SubmitRequest,
)
from server.quiz.service import QuizError, QuizService
from server.quiz.store import QuizStore, StoreUnavailable

M = TypeVar("M", bound=BaseModel)

MAX_BODY_BYTES = 1_048_576  # CSV toi da 512k ky tu; UTF-8 + escape JSON van du
_UUID = re.compile(UUID_PATTERN)
_SHARE = re.compile(SHARE_ID_PATTERN)


@dataclass
class QuizRuntime:
    service: QuizService

    @property
    def store(self) -> QuizStore:
        return self.service.store


def build_quiz_runtime(settings: Any, *, store: Optional[QuizStore] = None) -> QuizRuntime:
    """Mac dinh `LocalQuizStore` duoi `settings.var_dir/quiz`.

    `FAS_QUIZ_STORE=appwrite` chon `AppwriteQuizStore` (can collection quiz_* —
    CHUA tao tren hosted, parity chua xac minh; Phase 1 khong bat)."""
    if store is None:
        if os.environ.get("FAS_QUIZ_STORE", "local").strip().lower() == "appwrite":
            from server.quiz.appwrite_store import AppwriteQuizStore
            store = AppwriteQuizStore(settings.appwrite)
        else:
            from server.quiz.local_store import LocalQuizStore
            store = LocalQuizStore.under_var_dir(settings.var_dir)
    return QuizRuntime(service=QuizService(store))


def _error(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    body = ErrorBody(code=code, message=message[:300], **extra)
    return HTTPException(status, body.model_dump(mode="json", exclude_none=True))


def _field_errors(exc: ValidationError) -> List[FieldError]:
    out = []
    for e in exc.errors(include_input=False, include_url=False)[:100]:
        loc = [p if isinstance(p, (str, int)) else str(p) for p in e.get("loc", ())][:16]
        out.append(FieldError(loc=[str(p)[:80] if isinstance(p, str) else p for p in loc],
                              msg=str(e.get("msg", ""))[:300], type=str(e.get("type", ""))[:80]))
    return out


async def _body(request: Request, model: Type[M]) -> M:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise _error(413, "payload_too_large", "Request body is too large.")
    try:
        data = json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _error(422, "invalid_json", "Request body is not valid JSON.")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise _error(422, "invalid_request", "Request body failed validation.",
                     field_errors=_field_errors(exc))


def _json(model: BaseModel, status: int = 200) -> JSONResponse:
    return JSONResponse(model.model_dump(mode="json"), status_code=status)


def _id_or_404(value: str, kind: str) -> str:
    if not _UUID.match(value):
        raise _error(404, f"{kind}_not_found", f"{kind.capitalize()} not found.")
    return value


def _int_param(value: Optional[str], name: str, *, default: Optional[int], lo: int, hi: int) -> int:
    if value is None or value == "":
        if default is None:
            raise _error(422, "invalid_request", f"Query parameter '{name}' is required.")
        return default
    if not re.fullmatch(r"\d{1,16}", value) or not lo <= int(value) <= hi:
        raise _error(422, "invalid_request", f"Query parameter '{name}' must be an integer {lo}..{hi}.")
    return int(value)


def build_quiz_router(runtime: QuizRuntime, *,
                      resolve_profile: Callable[[Optional[str]], Any]) -> APIRouter:
    r = APIRouter(prefix="/api/quiz")
    svc = runtime.service

    def _user(authorization: Optional[str]) -> str:
        try:
            profile = resolve_profile(authorization)
        except HTTPException as exc:
            if exc.status_code == 401:
                raise _error(401, "auth_required", "Sign in to continue.") from exc
            if exc.status_code == 503:
                raise _error(503, "identity_unavailable",
                             "Sign-in service is temporarily unavailable.") from exc
            raise
        user_id = str(getattr(profile, "user_id", "") or "")
        if not user_id:
            raise _error(401, "auth_required", "Sign in to continue.")
        return user_id

    async def _run(fn: Callable[[], Any]) -> Any:
        try:
            return await run_in_threadpool(fn)
        except QuizError as exc:
            raise _error(exc.status, exc.code, exc.message, **exc.extra) from exc
        except StoreUnavailable as exc:
            raise _error(503, "store_unavailable", "Quiz storage is temporarily unavailable.") from exc

    # -- entitlements -----------------------------------------------------------------

    @r.get("/me/entitlements")
    async def my_entitlements(authorization: Optional[str] = Header(default=None)):
        user = _user(authorization)
        return _json(await _run(lambda: svc.entitlements(user)))

    # -- drafts -------------------------------------------------------------------------

    @r.get("/drafts")
    async def list_drafts(limit: Optional[str] = None, offset: Optional[str] = None,
                          authorization: Optional[str] = Header(default=None)):
        user = _user(authorization)
        lim = _int_param(limit, "limit", default=20, lo=1, hi=50)
        off = _int_param(offset, "offset", default=0, lo=0, hi=1_000_000)
        return _json(await _run(lambda: svc.list_drafts(user, limit=lim, offset=off)))

    @r.post("/drafts")
    async def create_draft(request: Request, authorization: Optional[str] = Header(default=None)):
        user = _user(authorization)
        body = await _body(request, DraftCreateRequest)
        return _json(await _run(lambda: svc.create_draft(user, body)), 201)

    @r.get("/drafts/{draft_id}")
    async def get_draft(draft_id: str, authorization: Optional[str] = Header(default=None)):
        user = _user(authorization)
        did = _id_or_404(draft_id, "draft")
        return _json(await _run(lambda: svc.get_draft(user, did)))

    @r.put("/drafts/{draft_id}")
    async def update_draft(draft_id: str, request: Request,
                           authorization: Optional[str] = Header(default=None)):
        user = _user(authorization)
        did = _id_or_404(draft_id, "draft")
        body = await _body(request, DraftUpdateRequest)
        return _json(await _run(lambda: svc.update_draft(user, did, body)))

    @r.delete("/drafts/{draft_id}")
    async def delete_draft(draft_id: str, expected_revision: Optional[str] = None,
                           authorization: Optional[str] = Header(default=None)):
        user = _user(authorization)
        did = _id_or_404(draft_id, "draft")
        rev = _int_param(expected_revision, "expected_revision", default=None, lo=1, hi=2**53 - 1)
        await _run(lambda: svc.delete_draft(user, did, rev))
        return Response(status_code=204)

    @r.post("/drafts/{draft_id}/csv/validate")
    async def csv_validate(draft_id: str, request: Request,
                           authorization: Optional[str] = Header(default=None)):
        user = _user(authorization)
        did = _id_or_404(draft_id, "draft")
        body = await _body(request, CsvValidateRequest)
        return _json(await _run(lambda: svc.csv_validate(user, did, body)))

    @r.post("/drafts/{draft_id}/csv/commit")
    async def csv_commit(draft_id: str, request: Request,
                         authorization: Optional[str] = Header(default=None)):
        user = _user(authorization)
        did = _id_or_404(draft_id, "draft")
        body = await _body(request, CsvCommitRequest)
        return _json(await _run(lambda: svc.csv_commit(user, did, body)))

    @r.post("/drafts/{draft_id}/publish")
    async def publish(draft_id: str, request: Request,
                      authorization: Optional[str] = Header(default=None)):
        user = _user(authorization)
        did = _id_or_404(draft_id, "draft")
        body = await _body(request, PublishRequest)
        result = await _run(lambda: svc.publish(user, did, body))
        return _json(result, 200 if result.replayed else 201)

    # -- share (public, khong can dang nhap) -------------------------------------------

    @r.get("/shares/{share_id}")
    async def get_share(share_id: str):
        if not _SHARE.match(share_id):
            raise _error(404, "share_not_found", "Share not found.")
        resp = _json(await _run(lambda: svc.get_share(share_id)))
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # -- sessions -----------------------------------------------------------------------

    @r.post("/shares/{share_id}/sessions")
    async def create_session(share_id: str, authorization: Optional[str] = Header(default=None)):
        user = _user(authorization)
        if not _SHARE.match(share_id):
            raise _error(404, "share_not_found", "Share not found.")
        return _json(await _run(lambda: svc.create_session(user, share_id)), 201)

    @r.get("/sessions/{session_id}")
    async def get_session(session_id: str, authorization: Optional[str] = Header(default=None)):
        user = _user(authorization)
        sid = _id_or_404(session_id, "session")
        return _json(await _run(lambda: svc.get_session(user, sid)))

    @r.post("/sessions/{session_id}/submit")
    async def submit(session_id: str, request: Request,
                     authorization: Optional[str] = Header(default=None)):
        user = _user(authorization)
        sid = _id_or_404(session_id, "session")
        body = await _body(request, SubmitRequest)
        return _json(await _run(lambda: svc.submit(user, sid, body)))

    @r.post("/sessions/{session_id}/advance")
    async def advance(session_id: str, request: Request,
                      authorization: Optional[str] = Header(default=None)):
        user = _user(authorization)
        sid = _id_or_404(session_id, "session")
        body = await _body(request, AdvanceRequest)
        return _json(await _run(lambda: svc.advance(user, sid, body)))

    return r
