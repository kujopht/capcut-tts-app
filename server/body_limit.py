"""
Trần kích thước thân yêu cầu (request body) theo tiền tố đường dẫn — ASGI thuần, KHÔNG đọc/đệm thân trước.

Vì sao cần: FastAPI đọc TOÀN BỘ thân JSON vào bộ nhớ rồi mới kiểm hợp lệ (422) và rồi mới tới xác thực trong thân route,
nên trước đây một client (kể cả KHÔNG đăng nhập) gửi vài trăm MB tới `/api/ai/*` vẫn bắt máy chủ đọc hết vào RAM — trên
instance 512 MB chỉ vài kết nối như vậy là OOM, kéo sập cả site. Giới hạn ở rìa, trước khi ai đó đọc thân:

* có `Content-Length` lớn hơn trần  -> 413 NGAY, thân không bị đọc;
* không có / khai sai `Content-Length` (chunked)  -> đếm byte thật khi ứng dụng đọc; vượt trần thì ứng dụng nhận
  `http.disconnect` (dừng đọc) và phản hồi của nó, dù là gì, bị THAY bằng 413.

Chỉ áp cho các phương thức có thân (POST/PUT/PATCH); GET/DELETE/OPTIONS đi thẳng.
"""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

Scope = Dict[str, Any]
Message = Dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})

#: `/api/ai/*`: tin nhắn <= 4000 ký tự, dự án <= ~28k ký tự (title/premise/notes + 3 object JSON <= 8000 ký tự mỗi cái).
#: Tiếng Việt UTF-8 tối đa 3 byte/ký tự, `\uXXXX` 6 byte/ký tự -> 256 KB là trần rộng rãi cho mọi thân hợp lệ.
AI_PREFIX = "/api/ai/"
AI_MAX_BODY_BYTES = 256 * 1024
BODY_LIMIT_RULES: Tuple[Tuple[str, int], ...] = ((AI_PREFIX, AI_MAX_BODY_BYTES),)


def _declared_length(scope: Scope) -> Optional[int]:
    for name, value in scope.get("headers") or ():
        if name == b"content-length":
            try:
                n = int(value.decode("latin-1").strip())
            except ValueError:
                return None
            return n if n >= 0 else None
    return None


def _too_large_body(limit: int) -> bytes:
    return json.dumps({"detail": {"code": "request_too_large",
                                  "message": f"Yêu cầu quá lớn (tối đa {limit // 1024} KB)."}},
                      ensure_ascii=False).encode("utf-8")


async def _send_413(send: Send, limit: int) -> None:
    body = _too_large_body(limit)
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                            (b"cache-control", b"no-store"),
                            # Phần thân còn lại (nếu có) chưa được đọc: đóng kết nối thay vì tái sử dụng.
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})


class MaxBodyMiddleware:
    def __init__(self, app: Any, *, rules: Sequence[Tuple[str, int]] = BODY_LIMIT_RULES) -> None:
        self.app = app
        self.rules: List[Tuple[str, int]] = list(rules)

    def _limit_for(self, path: str) -> Optional[int]:
        for prefix, limit in self.rules:
            if path.startswith(prefix):
                return limit
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("method", "").upper() not in BODY_METHODS:
            await self.app(scope, receive, send)
            return
        limit = self._limit_for(scope.get("path", ""))
        if limit is None:
            await self.app(scope, receive, send)
            return
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await _send_413(send, limit)
            return

        seen = 0
        exceeded = False
        app_started = False  # ứng dụng đã bắt đầu phản hồi CỦA NÓ (không còn đổi được mã trạng thái nữa)
        replied = False  # ta đã gửi 413

        async def counting_receive() -> Message:
            nonlocal seen, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message.get("type") == "http.request":
                seen += len(message.get("body") or b"")
                if seen > limit:
                    exceeded = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal app_started, replied
            if replied:
                return  # đã trả lời 413: nuốt phần còn lại của ứng dụng
            if exceeded and not app_started:
                # Ứng dụng phản ứng với `disconnect` bằng 400/lỗi nào đó: thay bằng 413 một lần.
                replied = True
                await _send_413(send, limit)
                return
            # Ứng dụng đã tự bắt đầu phản hồi TRƯỚC khi thân vượt trần (vd. một route phát ngay rồi mới đọc tiếp): không
            # được cắt ngang giữa chừng một phản hồi dở dang — để nó chạy hết; ta chỉ đã ngừng đọc thân.
            if message.get("type") == "http.response.start":
                app_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:  # noqa: BLE001 — một ứng dụng thuần Starlette có thể ném ClientDisconnect khi ta cắt thân
            if not exceeded:
                raise
        if exceeded and not app_started and not replied:
            # Ứng dụng kết thúc mà không phản hồi gì (vd. coi là client đã ngắt): vẫn báo 413 cho client thật.
            await _send_413(send, limit)
