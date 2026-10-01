"""
Trần kích thước thân yêu cầu cho `/api/ai/*` (`server/body_limit.py`): thân khổng lồ bị cắt Ở RÌA, trước khi FastAPI đọc
nó vào RAM, kể cả với client KHÔNG đăng nhập; thân hợp lệ không bị ảnh hưởng.
"""
from __future__ import annotations

import socket
import threading
import time
import unittest
from typing import Any, Dict, Iterator, List

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from server.body_limit import AI_MAX_BODY_BYTES, AI_PREFIX, BODY_LIMIT_RULES, MaxBodyMiddleware


class _Msg(BaseModel):
    content: str = ""


def _app(limit: int = 1000) -> tuple:
    seen: List[int] = []
    app = FastAPI()
    app.add_middleware(MaxBodyMiddleware, rules=(("/api/ai/", limit),))

    @app.post("/api/ai/echo")
    def echo(m: _Msg) -> Dict[str, Any]:
        seen.append(len(m.content))
        return {"n": len(m.content)}

    @app.put("/api/ai/put")
    def put(m: _Msg) -> Dict[str, Any]:
        seen.append(len(m.content))
        return {"n": len(m.content)}

    @app.post("/api/other/echo")
    def other(m: _Msg) -> Dict[str, Any]:
        return {"n": len(m.content)}

    @app.get("/api/ai/get")
    def get() -> Dict[str, bool]:
        return {"ok": True}

    return app, seen


class TestBodyLimitUnit(unittest.TestCase):
    def setUp(self) -> None:
        self.app, self.seen = _app(1000)
        self.c = TestClient(self.app)

    def test_declared_oversize_is_rejected_without_the_handler_running(self) -> None:
        r = self.c.post("/api/ai/echo", json={"content": "x" * 5000})
        self.assertEqual(r.status_code, 413)
        self.assertEqual(r.json()["detail"]["code"], "request_too_large")
        self.assertEqual(self.seen, [], "handler (và việc phân tích JSON) không được chạy")
        self.assertEqual(r.headers.get("connection"), "close")

    def test_valid_bodies_pass_including_exactly_at_the_limit(self) -> None:
        self.assertEqual(self.c.post("/api/ai/echo", json={"content": "xin chào"}).json(), {"n": 8})
        pad = len('{"content":""}')
        ok = ('{"content":"' + "a" * (1000 - pad) + '"}').encode()
        self.assertEqual(len(ok), 1000)
        r = self.c.post("/api/ai/echo", content=ok, headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 200, r.text)
        over = ('{"content":"' + "a" * (1000 - pad + 1) + '"}').encode()
        r = self.c.post("/api/ai/echo", content=over, headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 413)

    def test_every_body_method_is_covered_and_reads_and_other_prefixes_are_not(self) -> None:
        self.assertEqual(self.c.put("/api/ai/put", json={"content": "x" * 5000}).status_code, 413)
        self.assertEqual(self.c.post("/api/other/echo", json={"content": "x" * 50_000}).json()["n"], 50_000)
        self.assertEqual(self.c.get("/api/ai/get").json(), {"ok": True})
        self.assertEqual(self.c.get("/api/ai/get", headers={"X-Big": "y" * 5000}).status_code, 200)

    def test_chunked_body_without_content_length_is_counted_and_cut(self) -> None:
        consumed = {"n": 0}

        def chunks() -> Iterator[bytes]:
            yield b'{"content":"'
            for _ in range(2000):
                consumed["n"] += 64
                yield b"a" * 64
            yield b'"}'

        r = self.c.post("/api/ai/echo", content=chunks(), headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 413, r.text)
        self.assertEqual(r.json()["detail"]["code"], "request_too_large")
        self.assertEqual(self.seen, [], "thân vượt trần không bao giờ tới handler")

    def test_a_small_chunked_body_still_works(self) -> None:
        def chunks() -> Iterator[bytes]:
            yield b'{"content":"'
            yield b"hello"
            yield b'"}'

        r = self.c.post("/api/ai/echo", content=chunks(), headers={"Content-Type": "application/json"})
        self.assertEqual((r.status_code, r.json()), (200, {"n": 5}))

    def test_invalid_content_length_header_does_not_crash_and_falls_back_to_counting(self) -> None:
        r = self.c.post("/api/ai/echo", content=b'{"content":"abc"}',
                        headers={"Content-Type": "application/json", "Content-Length": "abc"})
        self.assertIn(r.status_code, (200, 400, 413, 422))

    def test_defaults_cover_the_ai_prefix_with_room_for_the_largest_legitimate_body(self) -> None:
        self.assertEqual(BODY_LIMIT_RULES, ((AI_PREFIX, AI_MAX_BODY_BYTES),))
        self.assertEqual(AI_PREFIX, "/api/ai/")
        # Dự án lớn nhất hợp lệ: 120 + 4000 + 4000 + 3 x 8000 ký tự, mỗi ký tự tối đa 6 byte (\uXXXX).
        self.assertGreater(AI_MAX_BODY_BYTES, (120 + 4000 + 4000 + 3 * 8000) * 6 // 2)
        self.assertLessEqual(AI_MAX_BODY_BYTES, 1024 * 1024, "trần phải nhỏ hơn nhiều so với RAM của instance")


class TestAppThatStartsRespondingBeforeTheBodyIsFullyRead(unittest.TestCase):
    """Reviewer: nếu ứng dụng đã gửi `http.response.start` TRƯỚC khi thân vượt trần thì không được cắt ngang phản hồi dở
    dang của nó (không còn đổi được mã trạng thái nữa); chỉ việc ĐỌC thân dừng lại."""

    @staticmethod
    def _drive(app: Any, chunks: List[bytes], *, limit: int = 100) -> List[Dict[str, Any]]:
        import asyncio
        sent: List[Dict[str, Any]] = []
        queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]

        async def receive() -> Dict[str, Any]:
            return queue.pop(0) if queue else {"type": "http.disconnect"}

        async def send(m: Dict[str, Any]) -> None:
            sent.append(m)

        scope = {"type": "http", "method": "POST", "path": "/api/ai/x", "headers": []}
        asyncio.run(MaxBodyMiddleware(app, rules=(("/api/ai/", limit),))(scope, receive, send))
        return sent

    def test_an_early_response_is_left_intact_when_the_body_then_exceeds_the_limit(self) -> None:
        async def early(scope: Any, receive: Any, send: Any) -> None:
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
            n = 0
            while True:
                m = await receive()
                if m["type"] != "http.request":
                    break
                n += len(m.get("body") or b"")
                if not m.get("more_body"):
                    break
            await send({"type": "http.response.body", "body": f"read:{n}".encode()})

        sent = self._drive(early, [b"a" * 60, b"b" * 60, b"c" * 60])
        self.assertEqual([m["type"] for m in sent], ["http.response.start", "http.response.body"])
        self.assertEqual(sent[0]["status"], 200, "không được đổi thành 413 giữa chừng")
        self.assertEqual(sent[1]["body"], b"read:60", "việc đọc thân dừng ở khối vượt trần")

    def test_a_late_responder_still_gets_the_single_413(self) -> None:
        async def late(scope: Any, receive: Any, send: Any) -> None:
            while True:
                m = await receive()
                if m["type"] != "http.request" or not m.get("more_body"):
                    break
            await send({"type": "http.response.start", "status": 400, "headers": []})
            await send({"type": "http.response.body", "body": b"loi"})

        sent = self._drive(late, [b"a" * 60, b"b" * 60, b"c" * 60])
        self.assertEqual([m["type"] for m in sent], ["http.response.start", "http.response.body"])
        self.assertEqual(sent[0]["status"], 413)
        self.assertIn(b"request_too_large", sent[1]["body"])

    def test_an_app_that_raises_after_the_cut_still_gets_a_413(self) -> None:
        async def raising(scope: Any, receive: Any, send: Any) -> None:
            while True:
                m = await receive()
                if m["type"] == "http.disconnect":
                    raise ConnectionError("client disconnect")

        sent = self._drive(raising, [b"a" * 200])
        self.assertEqual(sent[0]["status"], 413)

    def test_an_exception_unrelated_to_the_cut_is_not_swallowed(self) -> None:
        async def broken(scope: Any, receive: Any, send: Any) -> None:
            raise ValueError("lỗi thật của ứng dụng")

        with self.assertRaises(ValueError):
            self._drive(broken, [b"small"])


class TestBodyLimitOnARealServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import uvicorn
        cls.app, cls.seen = _app(1000)
        cls.server = uvicorn.Server(uvicorn.Config(cls.app, host="127.0.0.1", port=0, log_level="critical"))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        for _ in range(300):
            if getattr(cls.server, "started", False):
                break
            time.sleep(0.02)
        cls.port = cls.server.servers[0].sockets[0].getsockname()[1]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.should_exit = True
        cls.thread.join(timeout=5)

    def _status_line(self, raw: bytes) -> str:
        return raw.split(b"\r\n", 1)[0].decode("latin-1")

    def test_a_declared_fifty_megabyte_body_is_refused_before_any_of_it_is_sent(self) -> None:
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        try:
            s.sendall(b"POST /api/ai/echo HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
                      b"Content-Length: 50000000\r\n\r\n")  # chỉ tiêu đề, KHÔNG gửi thân
            got = b""
            end = time.time() + 5
            while b"\r\n\r\n" not in got and time.time() < end:
                chunk = s.recv(4096)
                if not chunk:
                    break
                got += chunk
        finally:
            s.close()
        self.assertIn("413", self._status_line(got), got[:200])
        self.assertEqual(self.seen, [])

    def test_an_endless_chunked_body_is_cut_off_early(self) -> None:
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        sent = 0
        status = b""
        try:
            s.sendall(b"POST /api/ai/echo HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
                      b"Transfer-Encoding: chunked\r\n\r\n")
            piece = b"a" * 4096
            frame = b"%x\r\n%s\r\n" % (len(piece), piece)
            s.settimeout(0.05)
            for _ in range(400):  # ~1,6 MB nếu máy chủ không cắt; thất bại cũng kết thúc trong vài giây
                try:
                    s.sendall(frame)
                    sent += len(piece)
                except OSError:
                    break
                try:
                    status = s.recv(4096)
                    if status:
                        break
                except socket.timeout:
                    continue
                except OSError:
                    break
        finally:
            s.close()
        self.assertTrue(status, "máy chủ phải trả lời 413 trước khi nhận hết thân")
        self.assertIn(b"413", status.split(b"\r\n", 1)[0])
        self.assertLess(sent, 1_000_000, f"đã gửi {sent} byte trước khi bị cắt")


class TestWiredIntoTheRealApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from server.main import app
        cls.app = app
        cls.c = TestClient(app)

    def test_main_registers_the_middleware_innermost_so_a_413_still_gets_cors_and_rate_limit(self) -> None:
        names = [m.cls.__name__ for m in self.app.user_middleware]  # ngoài cùng trước
        self.assertIn("MaxBodyMiddleware", names)
        self.assertLess(names.index("RateLimitMiddleware"), names.index("CORSMiddleware"))
        self.assertLess(names.index("CORSMiddleware"), names.index("MaxBodyMiddleware"))

    def test_an_anonymous_oversize_post_to_any_ai_route_is_413_before_auth(self) -> None:
        big = {"content": "x" * (AI_MAX_BODY_BYTES + 10), "client_id": "c"}
        for method, path in (("post", "/api/ai/conversations/abc/messages"), ("post", "/api/ai/projects"),
                             ("put", "/api/ai/preferences"), ("post", "/api/ai/support/escalations"),
                             ("post", "/api/ai/conversations")):
            with self.subTest(path=path):
                r = getattr(self.c, method)(path, json=big)
                self.assertEqual(r.status_code, 413, r.text)
                self.assertEqual(r.json()["detail"]["code"], "request_too_large")

    def test_a_413_carries_cors_headers_for_the_site_origin(self) -> None:
        origin = (self.app.user_middleware and "http://localhost:3000")
        r = self.c.post("/api/ai/conversations", json={"x": "y" * (AI_MAX_BODY_BYTES + 10)}, headers={"Origin": origin})
        self.assertEqual(r.status_code, 413)
        self.assertEqual(r.headers.get("access-control-allow-origin"), origin)

    def test_normal_sized_requests_are_not_affected(self) -> None:
        r = self.c.post("/api/ai/conversations/abc/messages", json={"content": "xin chào", "client_id": "c"})
        self.assertNotEqual(r.status_code, 413)
        self.assertIn(r.status_code, (401, 403, 503), "chưa đăng nhập / AI tắt trong test, nhưng không phải 413")

    def test_the_rest_of_the_api_has_no_new_limit(self) -> None:
        self.assertEqual([p for p, _ in BODY_LIMIT_RULES], ["/api/ai/"])


if __name__ == "__main__":
    unittest.main()
