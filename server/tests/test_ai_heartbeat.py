"""
SSE heartbeat for `POST /api/ai/conversations/{id}/messages` (release gate
A) — `server/ai_assistant/stream_pump.py` + `routes.py`.

Deterministic by construction: the "slow provider" is gated on a
`threading.Event` the TEST releases only after it has observed the
heartbeats it expects, and `heartbeat_s` is set to 0.05 s directly on the
runtime (settings clamp production values to [15, 25] — tested separately
below). The route tests run against a REAL uvicorn server over a raw socket
because `TestClient` buffers a streaming body (it would hide whether a
heartbeat was ever flushed while the provider was silent).
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
import unittest
from typing import Any, Dict, Iterator, List, Tuple
from unittest import mock

import anyio
import httpx

from server.ai_assistant.gateway import AiGateway
from server.ai_assistant.limits import AiBusy
from server.ai_assistant.routes import SSE_HEARTBEAT
from server.ai_assistant.stream_pump import END, SILENCE, PumpError, StreamPump
from server.config import ConfigError, _ai_assistant_settings
from server.llm_gateway.chat_provider import (
    ChatProvider, Delta, Done, GenerateRequest, GenerateResult, ProviderCapabilities,
    ProviderUsageSnapshot, StreamEvent, UsageEvent,
)

from server.tests.test_ai_routes import _auth, _enabled_runtime, _make_app

PUMP_THREAD = "ai-stream-pump"


def _pump_threads() -> List[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == PUMP_THREAD and t.is_alive()]


def _wait(cond, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


# ============================================================ StreamPump (unit)


class TestStreamPump(unittest.TestCase):
    def test_events_in_order_then_end_and_thread_exits(self) -> None:
        async def main() -> Tuple[List[Any], StreamPump]:
            pump = StreamPump(iter([1, 2, 3])).start()
            got = [await pump.next(2) for _ in range(4)]
            return got, pump

        got, pump = anyio.run(main)
        self.assertEqual(got, [1, 2, 3, END])
        self.assertTrue(pump.join(2))

    def test_silence_while_generator_is_blocked_then_resumes(self) -> None:
        gate = threading.Event()

        def gen() -> Iterator[int]:
            yield 1
            gate.wait(5)
            yield 2

        async def main() -> List[Any]:
            pump = StreamPump(gen()).start()
            out = [await pump.next(2)]
            out.append(await pump.next(0.05))  # generator blocked -> SILENCE
            out.append(await pump.next(0.05))
            gate.set()
            out.append(await pump.next(2))
            out.append(await pump.next(2))
            return out

        self.assertEqual(anyio.run(main), [1, SILENCE, SILENCE, 2, END])

    def test_stop_exits_at_next_event_and_closes_generator_on_pump_thread(self) -> None:
        gate = threading.Event()
        closed_on: Dict[str, str] = {}

        def gen() -> Iterator[int]:
            try:
                yield 1
                gate.wait(5)
                yield 2
                yield 3
            finally:
                closed_on["thread"] = threading.current_thread().name

        async def main() -> StreamPump:
            pump = StreamPump(gen()).start()
            self.assertEqual(await pump.next(2), 1)
            pump.stop()
            return pump

        pump = anyio.run(main)
        gate.set()
        self.assertTrue(pump.join(2), "pump thread must exit after stop() + next event")
        self.assertEqual(closed_on.get("thread"), PUMP_THREAD,
                         "generator must be closed (finally ran) on the pump thread")

    def test_exception_is_delivered_as_pump_error_then_end(self) -> None:
        def gen() -> Iterator[int]:
            yield 1
            raise ValueError("boom")

        async def main() -> List[Any]:
            pump = StreamPump(gen()).start()
            return [await pump.next(2) for _ in range(3)]

        first, err, end = anyio.run(main)
        self.assertEqual(first, 1)
        self.assertIsInstance(err, PumpError)
        self.assertIsInstance(err.exc, ValueError)
        self.assertIs(end, END)

    def test_cancel_while_waiting_loses_nothing(self) -> None:
        gate = threading.Event()

        def gen() -> Iterator[int]:
            yield 1
            gate.wait(5)
            yield 2

        async def main() -> List[Any]:
            pump = StreamPump(gen()).start()
            out = [await pump.next(2)]
            with anyio.move_on_after(0.05):  # an OUTER cancel mid-wait
                await pump.next(10)
            gate.set()
            out.append(await pump.next(2))
            out.append(await pump.next(2))
            return out

        self.assertEqual(anyio.run(main), [1, 2, END])


# ============================================================ settings clamp


class TestHeartbeatSetting(unittest.TestCase):
    def _heartbeat(self, raw: str | None) -> int:
        env = {k: v for k, v in os.environ.items() if k != "FAS_AI_HEARTBEAT_S"}
        if raw is not None:
            env["FAS_AI_HEARTBEAT_S"] = raw
        with mock.patch.dict(os.environ, env, clear=True):
            return _ai_assistant_settings().heartbeat_s

    def test_default_is_15(self) -> None:
        self.assertEqual(self._heartbeat(None), 15)

    def test_clamped_to_15_25(self) -> None:
        self.assertEqual(self._heartbeat("1"), 15)
        self.assertEqual(self._heartbeat("20"), 20)
        self.assertEqual(self._heartbeat("300"), 25)

    def test_invalid_value_is_a_config_error_not_a_silent_default(self) -> None:
        with self.assertRaises(ConfigError):
            self._heartbeat("abc")


# ============================================================ route over real uvicorn


class _GatedProvider(ChatProvider):
    """Yields "Xin", then goes SILENT until `gate` is set, then " chào" +
    usage + done. `closed` is set when the generator's `finally` runs."""

    name = "gated"

    def __init__(self) -> None:
        self.gate = threading.Event()
        self.closed = threading.Event()

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(streaming=True, tools=False, web_search=False, vision=False,
                                    max_context_tokens=8000)

    def generate(self, req: GenerateRequest) -> GenerateResult:  # pragma: no cover — unused
        raise NotImplementedError

    def stream(self, req: GenerateRequest) -> Iterator[StreamEvent]:
        try:
            yield Delta(text="Xin")
            self.gate.wait(10)
            yield Delta(text=" chào")
            yield UsageEvent(input_tokens=5, output_tokens=2)
            yield Done()
        finally:
            self.closed.set()

    def usage(self) -> ProviderUsageSnapshot:
        return ProviderUsageSnapshot()


def _dechunk(raw: bytes) -> bytes:
    """HTTP/1.1 chunked body -> payload (headers stripped)."""
    _, _, body = raw.partition(b"\r\n\r\n")
    out = b""
    while body:
        size_line, _, rest = body.partition(b"\r\n")
        size = int(size_line.split(b";")[0] or b"0", 16)
        if size == 0:
            break
        out += rest[:size]
        body = rest[size + 2:]
    return out


def _parse_sse(payload: str) -> Tuple[List[Tuple[str, Dict[str, Any]]], int]:
    """(events, heartbeat_comment_count) — mirrors the web parser: ":" lines
    are comments and never become an event."""
    events: List[Tuple[str, Dict[str, Any]]] = []
    pings = 0
    for block in payload.split("\n\n"):
        name, data = "message", None
        for line in block.split("\n"):
            if line.startswith(":"):
                pings += 1
            elif line.startswith("event:"):
                name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:"):].strip())
        if data is not None:
            events.append((name, data))
    return events, pings


class TestHeartbeatRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import uvicorn

        cls.rt = _enabled_runtime()
        cls.rt.heartbeat_s = 0.05
        config = uvicorn.Config(_make_app(cls.rt), host="127.0.0.1", port=0, log_level="critical")
        cls.server = uvicorn.Server(config)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        for _ in range(200):
            if getattr(cls.server, "started", False):
                break
            time.sleep(0.02)
        cls.port = cls.server.servers[0].sockets[0].getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.should_exit = True
        cls.thread.join(timeout=5)

    def _use(self, provider: ChatProvider) -> None:
        self.rt.gateway = AiGateway(providers={provider.name: provider},
                                    provider_chain=[provider.name])

    def _open_stream(self, user: str) -> Tuple[socket.socket, str]:
        with httpx.Client(timeout=10.0) as client:
            created = client.post(f"{self.base}/api/ai/conversations", headers=_auth(user),
                                  json={"mode": "general"})
            self.assertEqual(created.status_code, 200)
            cid = created.json()["conversation_id"]
        body = json.dumps({"content": "xin chao", "client_id": f"c-{user}"}).encode()
        request_bytes = (
            f"POST /api/ai/conversations/{cid}/messages HTTP/1.1\r\n"
            f"Host: x\r\nAuthorization: Bearer {user}\r\nContent-Type: application/json\r\n"
            f"Connection: close\r\nContent-Length: {len(body)}\r\n\r\n").encode() + body
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        sock.sendall(request_bytes)
        return sock, cid

    @staticmethod
    def _read_until(sock: socket.socket, got: bytes, cond, timeout: float = 5.0) -> bytes:
        deadline = time.time() + timeout
        while not cond(got) and time.time() < deadline:
            chunk = sock.recv(4096)
            if not chunk:
                break
            got += chunk
        return got

    def _assistant(self, cid: str):
        found = [m for m in self.rt.repo._messages.values()  # noqa: SLF001 — test-only
                 if m.conversation_id == cid and m.role == "assistant"]
        return found[0] if found else None

    def test_silent_provider_gets_heartbeats_that_never_become_content(self) -> None:
        provider = _GatedProvider()
        self._use(provider)
        sock, cid = self._open_stream("hb1")
        try:
            got = self._read_until(sock, b"", lambda g: g.count(SSE_HEARTBEAT.encode()) >= 3)
            self.assertGreaterEqual(got.count(SSE_HEARTBEAT.encode()), 3,
                                    "no heartbeat was flushed while the provider was silent")
            self.assertLess(got.index(b"event: delta"), got.index(SSE_HEARTBEAT.encode()),
                            "the first delta must be delivered before the silence")

            # The event loop is NOT blocked while the provider is silent.
            t0 = time.time()
            r = httpx.get(f"{self.base}/api/ai/availability", headers=_auth("other"), timeout=2.0)
            self.assertEqual(r.status_code, 200)
            self.assertLess(time.time() - t0, 1.0)

            provider.gate.set()
            got = self._read_until(sock, got, lambda g: False)  # to EOF (Connection: close)
        finally:
            sock.close()

        events, pings = _parse_sse(_dechunk(got).decode("utf-8"))
        self.assertGreaterEqual(pings, 3)
        names = [n for n, _ in events]
        self.assertEqual(names[0], "meta")
        self.assertEqual(names[-1], "done")
        self.assertEqual(events[-1][1], {"status": "complete"})
        deltas = [d["text"] for n, d in events if n == "delta"]
        self.assertEqual(deltas, ["Xin", " chào"], "chunks must be preserved exactly")
        self.assertNotIn("ping", "".join(deltas))

        msg = self._assistant(cid)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.content, "Xin chào")
        self.assertEqual(msg.status, "complete")
        self.assertTrue(_wait(lambda: not _pump_threads()), "pump thread leaked after completion")

    def test_fast_provider_gets_no_heartbeat(self) -> None:
        from server.llm_gateway.chat_providers import MockChatProvider

        self._use(MockChatProvider())
        old = self.rt.heartbeat_s
        self.rt.heartbeat_s = 5.0
        try:
            sock, _ = self._open_stream("hb2")
            try:
                got = self._read_until(sock, b"", lambda g: False)
            finally:
                sock.close()
        finally:
            self.rt.heartbeat_s = old
        events, pings = _parse_sse(_dechunk(got).decode("utf-8"))
        self.assertEqual(pings, 0)
        self.assertEqual(events[-1], ("done", {"status": "complete"}))

    def test_disconnect_during_silence_stops_cleanly_without_leaks(self) -> None:
        provider = _GatedProvider()
        self._use(provider)
        sock, cid = self._open_stream("hb3")
        got = self._read_until(sock, b"", lambda g: SSE_HEARTBEAT.encode() in g)
        self.assertIn(SSE_HEARTBEAT.encode(), got)
        sock.close()  # the user closes the tab while the provider is silent

        self.assertTrue(_wait(lambda: self._assistant(cid) is not None),
                        "partial reply must still be persisted after a disconnect")
        msg = self._assistant(cid)
        self.assertEqual(msg.status, "stopped")
        self.assertEqual(msg.content, "Xin")

        # Stream slot released: the same user can start another stream.
        self.rt.stream_guard.acquire("user_hb3")
        self.rt.stream_guard.release("user_hb3")

        # Provider wakes up -> the pump sees stop(), closes the generator
        # (provider `finally` runs) and exits: no leaked worker.
        provider.gate.set()
        self.assertTrue(provider.closed.wait(3), "provider generator was never closed")
        self.assertTrue(_wait(lambda: not _pump_threads()), "pump thread leaked after disconnect")

    def test_failure_above_provider_layer_is_a_fixed_error_not_raw_text(self) -> None:
        class _BrokenGateway:
            def stream(self, *_a: Any, **_k: Any) -> Iterator[StreamEvent]:
                yield Delta(text="Xin")
                raise RuntimeError("secret-internal-detail")

        old = self.rt.gateway
        self.rt.gateway = _BrokenGateway()  # type: ignore[assignment]
        try:
            # The real exception goes to the server log (asserted here, which
            # also keeps the traceback out of the test output).
            with self.assertLogs("fanfic.ai_assistant", level="ERROR"):
                sock, cid = self._open_stream("hb5")
                try:
                    got = self._read_until(sock, b"", lambda g: False)
                finally:
                    sock.close()
        finally:
            self.rt.gateway = old
        payload = _dechunk(got).decode("utf-8")
        self.assertNotIn("secret-internal-detail", payload)
        events, _ = _parse_sse(payload)
        self.assertEqual(events[-1][0], "error")
        self.assertEqual(events[-1][1]["code"], "ai_provider_unavailable")
        self.assertTrue(_wait(lambda: self._assistant(cid) is not None))
        self.assertEqual(self._assistant(cid).status, "error")
        self.assertTrue(_wait(lambda: not _pump_threads()))

    def test_second_stream_still_rejected_while_first_is_silent(self) -> None:
        """Heartbeats must not weaken the 1-stream-per-user guard."""
        provider = _GatedProvider()
        self._use(provider)
        sock, _ = self._open_stream("hb4")
        try:
            self._read_until(sock, b"", lambda g: SSE_HEARTBEAT.encode() in g)
            with self.assertRaises(AiBusy):
                self.rt.stream_guard.acquire("user_hb4")
        finally:
            provider.gate.set()
            self._read_until(sock, b"", lambda g: False)
            sock.close()


if __name__ == "__main__":
    unittest.main()
