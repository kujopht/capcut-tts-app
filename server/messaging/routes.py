"""
Route nhan tin — `/api/chat/*`. Moi route CHI cho nguoi da dang nhap, moi route theo NGUOI KIA.

    GET  /api/chat/conversations                   hop thu (moi nhat truoc) + tong chua doc (tru tat tieng)
    GET  /api/chat/dm/{peer}/messages?before=&after=&limit=
    POST /api/chat/dm/{peer}/messages              {client_id, text} — idempotent theo client_id
    POST /api/chat/dm/{peer}/read                  {up_to?}
    POST /api/chat/dm/{peer}/mute                  {muted}
    POST /api/chat/dm/{peer}/block                 {blocked}
    GET  /api/chat/blocks
    GET  /api/chat/stream                          SSE qua fetch (Authorization), xem `realtime.py`

Tat (`FAS_CHAT_V1`) -> 503 `chat_not_configured`. Loi nghiep vu -> `{code, message}` on dinh.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated

from server.messaging.domain import ChatError
from server.messaging.runtime import MessagingRuntime
from server.rate_limit import SlidingWindowRateLimiter

HAN_MUC = {  # (so lan, cua so giay) theo NGUOI
    "send": (30, 60.0),
    "read": (120, 60.0),
    "write": (60, 60.0),
    "stream": (12, 60.0),
}
#: Luong DONG THOI toi da moi nguoi (moi instance). Moi luong giu MOT WebSocket toi Appwrite toi 25 phut —
#: han muc "12 lan mo/phut" mot minh van cho mot nguoi tich ~300 ket noi upstream. Du cho nhieu tab that.
LUONG_DONG_THOI_TOI_DA = 8
PeerId = Annotated[str, StringConstraints(min_length=4, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")]
MsgId = Annotated[str, StringConstraints(min_length=4, max_length=36, pattern=r"^[A-Za-z0-9_-]+$")]


class SendIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    client_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9]{16,32}$")]
    text: Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class ReadIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    up_to: Optional[MsgId] = None


class MuteIn(BaseModel):
    muted: bool = True


class BlockIn(BaseModel):
    blocked: bool = True


def build_messaging_router(rt: MessagingRuntime, *, resolve_profile: Callable[[Optional[str]], Any],
                           limiter: Optional[SlidingWindowRateLimiter] = None) -> APIRouter:
    r = APIRouter()
    lim = limiter or SlidingWindowRateLimiter()
    dang_mo: Dict[str, int] = {}
    khoa_luong = threading.Lock()

    def _bat():
        if not rt.enabled or rt.service is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                {"code": "chat_not_configured", "message": "Tin nhắn chưa được bật trên máy chủ."})
        return rt.service

    def _han_muc(loai: str, uid: str) -> None:
        toi_da, cua_so = HAN_MUC[loai]
        ok, _, cho = lim.check(f"chat_{loai}:{uid}", toi_da, cua_so)
        if not ok:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                {"code": "chat_rate_limited", "message": "Bạn thao tác hơi nhanh — thử lại sau ít giây."},
                                headers={"Retry-After": str(max(1, int(cho)))})

    def _chay(f: Callable[[], Any]) -> Any:
        try:
            return f()
        except ChatError as exc:
            raise HTTPException(exc.http_status, {"code": exc.code, "message": str(exc)}) from exc

    @r.get("/api/chat/conversations")
    def conversations(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        sv = _bat()
        p = resolve_profile(authorization)
        _han_muc("read", p.user_id)
        ds, tong = _chay(lambda: sv.conversations(p.user_id))
        return {"items": [sv.member_dto(m) for m in ds], "unread_total": tong}

    @r.get("/api/chat/dm/{peer}/messages")
    def history(peer: PeerId, before: Optional[MsgId] = None, after: Optional[MsgId] = None, limit: int = 30,
                authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        sv = _bat()
        p = resolve_profile(authorization)
        _han_muc("read", p.user_id)
        if before and after:
            raise HTTPException(400, {"code": "chat_invalid", "message": "Chỉ dùng một trong before/after."})
        trang = _chay(lambda: sv.history(p.user_id, peer, before=before, after=after, limit=limit))
        return {"messages": [sv.message_dto(p.user_id, m) for m in trang.messages], "cursor": trang.cursor}

    @r.post("/api/chat/dm/{peer}/messages")
    def send(peer: PeerId, payload: SendIn, background: BackgroundTasks, response: Response,
             authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        sv = _bat()
        t0 = time.perf_counter()
        p = resolve_profile(authorization)
        do: Dict[str, float] = {"xac_thuc": round((time.perf_counter() - t0) * 1000, 1)}
        _han_muc("send", p.user_id)
        # Ban xem truoc hop thu cap nhat SAU khi tra loi (idempotent, tu sua) — nguoi gui khong phai cho.
        tin, moi = _chay(lambda: sv.send(p.user_id, peer, payload.client_id, payload.text,
                                         defer=background.add_task, timing=do))
        do["tong"] = round((time.perf_counter() - t0) * 1000, 1)
        # `Server-Timing` (chuan W3C): CHI ten buoc + mili-giay — khong du lieu nguoi dung nao.
        response.headers["Server-Timing"] = ", ".join(f"{k};dur={v}" for k, v in do.items())
        return {"message": sv.message_dto(p.user_id, tin), "created": moi}

    @r.post("/api/chat/dm/{peer}/read")
    def read(peer: PeerId, payload: ReadIn, authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        sv = _bat()
        p = resolve_profile(authorization)
        _han_muc("write", p.user_id)
        m = _chay(lambda: sv.mark_read(p.user_id, peer, payload.up_to))
        return {"conversation": sv.member_dto(m) if m and m.last_message_id else None}

    @r.post("/api/chat/dm/{peer}/mute")
    def mute(peer: PeerId, payload: MuteIn, authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        sv = _bat()
        p = resolve_profile(authorization)
        _han_muc("write", p.user_id)
        m = _chay(lambda: sv.set_muted(p.user_id, peer, payload.muted))
        return {"muted": m.muted}

    @r.post("/api/chat/dm/{peer}/block")
    def block(peer: PeerId, payload: BlockIn, authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        sv = _bat()
        p = resolve_profile(authorization)
        _han_muc("write", p.user_id)
        return {"blocked": _chay(lambda: sv.set_blocked(p.user_id, peer, payload.blocked))}

    @r.get("/api/chat/blocks")
    def blocks(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        sv = _bat()
        p = resolve_profile(authorization)
        _han_muc("read", p.user_id)
        return {"items": _chay(lambda: sv.blocked_chat_ids(p.user_id))}

    @r.get("/api/chat/stream")
    async def stream(request: Request, authorization: Optional[str] = Header(default=None)):
        sv = _bat()
        p = await run_in_threadpool(resolve_profile, authorization)
        # Tach credential PHONG THU (khong dua vao viec resolve_profile da kiem dinh dang).
        phan = (authorization or "").split(" ", 1)
        credential = phan[1].strip() if len(phan) == 2 and phan[0].lower() == "bearer" else ""
        if not credential:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cần đăng nhập.")
        _han_muc("stream", p.user_id)
        with khoa_luong:
            if dang_mo.get(p.user_id, 0) >= LUONG_DONG_THOI_TOI_DA:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                    {"code": "chat_too_many_streams", "message": "Đang mở quá nhiều tab tin nhắn."},
                                    headers={"Retry-After": "30"})
            dang_mo[p.user_id] = dang_mo.get(p.user_id, 0) + 1
        # `credential` = CHINH session cua nguoi goi (da xac minh o tren) — de Appwrite tu loc theo quyen
        # doc. Khong bao gio ghi ra log / tra lai trinh duyet.

        def tra_cho():
            with khoa_luong:
                con = dang_mo.get(p.user_id, 1) - 1
                if con > 0:
                    dang_mo[p.user_id] = con
                else:
                    dang_mo.pop(p.user_id, None)

        async def luong():
            bat_dau = time.monotonic()
            nguon = rt.events.subscribe(p.user_id, credential, heartbeat_s=rt.heartbeat_s)
            da_san_sang = False
            try:
                async for ev in nguon:
                    if ev is None:
                        if not da_san_sang:
                            da_san_sang = True
                            yield "event: ready\ndata: {}\n\n"
                        else:
                            yield ": ping\n\n"
                    else:
                        dto = sv.event_dto(p.user_id, ev)
                        if dto is not None:
                            yield "data: " + json.dumps(dto, ensure_ascii=False) + "\n\n"
                    if time.monotonic() - bat_dau > rt.max_stream_s:
                        yield "event: bye\ndata: {}\n\n"
                        return
            except ChatError as exc:
                yield "event: error\ndata: " + json.dumps({"code": exc.code}) + "\n\n"
            finally:
                tra_cho()
                await nguon.aclose()

        return StreamingResponse(luong(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    return r
