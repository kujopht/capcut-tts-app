"""
Alibaba Model Studio adapter (`server/llm_gateway/alibaba.py`) — wire format, host allowlist, timeouts, cancellation, sanitised
error classification, secret hygiene. Everything runs on `httpx.MockTransport`: NO network, NO real key, NO Alibaba quota.
Fake secrets are built at runtime (repo gitleaks convention).
"""
from __future__ import annotations

import json
import unittest
from typing import Any, Callable, Dict, Iterable, List, Optional

import httpx

from server.llm_gateway.alibaba import (
    CATEGORIES, AlibabaModelStudioProvider, alibaba_endpoint_error, alibaba_host_allowed, classify_error,
)
from server.llm_gateway.chat_provider import ChatTurn, Delta, Done, GenerateRequest, ProviderError, UsageEvent

BASE = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
KEY = "sk-" + "alibabatest" * 3
LEAK = "LEAKMARKER-" + "z9q" * 4


def sse(*frames: Any, done: bool = True) -> bytes:
    out = "".join(f"data: {json.dumps(f)}\n\n" for f in frames)
    return (out + ("data: [DONE]\n\n" if done else "")).encode()


def chunk(text: Optional[str] = None, *, finish: Optional[str] = None, reasoning: Optional[str] = None) -> Dict[str, Any]:
    delta: Dict[str, Any] = {}
    if text is not None:
        delta["content"] = text
    if reasoning is not None:
        delta["reasoning_content"] = reasoning
    return {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


USAGE = {"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15}}


def req(**kw: Any) -> GenerateRequest:
    return GenerateRequest(messages=[ChatTurn(role="user", content="xin chào")], model="model-from-slot",
                           max_output_tokens=64, user_ref="hashed-user", **kw)


class Seen:
    """Records what the adapter sent."""

    def __init__(self) -> None:
        self.requests: List[httpx.Request] = []

    @property
    def payloads(self) -> List[Dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests]


def make(handler: Callable[[httpx.Request], httpx.Response], seen: Optional[Seen] = None, **kw: Any) -> AlibabaModelStudioProvider:
    """A provider on a mock transport (injecting the client skips the ~0.5 s SSL-context build of a real `httpx.Client`; the
    adapter's OWN client — headers, no redirects — is asserted in `test_redirects_are_never_followed_…`)."""

    def wrapped(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.requests.append(request)
        return handler(request)

    client = httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                          transport=httpx.MockTransport(wrapped))
    return AlibabaModelStudioProvider(name="alibaba-01", base_url=BASE, api_key=KEY, client=client, **kw)


def ok_handler(body: bytes) -> Callable[[httpx.Request], httpx.Response]:
    return lambda r: httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})


def stream_events(p: AlibabaModelStudioProvider, **kw: Any) -> List[Any]:
    return list(p.stream(req(**kw)))


class ClosableStream(httpx.SyncByteStream):
    def __init__(self, chunks: Iterable[bytes], on_chunk: Optional[Callable[[], None]] = None) -> None:
        self._chunks = list(chunks)
        self._on_chunk = on_chunk
        self.closed = False

    def __iter__(self):
        for c in self._chunks:
            if self._on_chunk:
                self._on_chunk()
            yield c

    def close(self) -> None:
        self.closed = True


class Tick:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


# ====================================================================== host allowlist (the key must never leave Alibaba)


class TestHostAllowlist(unittest.TestCase):
    def test_documented_dashscope_hosts_pass_and_everything_else_fails(self) -> None:
        good = ["dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com", "dashscope-us.aliyuncs.com",
                "cn-hongkong.dashscope.aliyuncs.com", "DashScope-Intl.AliYunCS.com"]
        bad = ["evil.aliyuncs.com", "dashscope.aliyuncs.com.evil.com", "xdashscope.aliyuncs.com", "dashscope-.aliyuncs.com",
               "a.b.dashscope.aliyuncs.com", "my-bucket.oss-cn-hangzhou.aliyuncs.com", "dashscope.example.com",
               "dashscope.aliyuncs.com:8443", "127.0.0.1", "169.254.169.254", "localhost", "", "dashscope-intl.aliyuncs.com."]
        for h in good:
            with self.subTest(good=h):
                self.assertTrue(alibaba_host_allowed(h))
        for h in bad:
            with self.subTest(bad=h):
                self.assertFalse(alibaba_host_allowed(h))

    def test_endpoint_rules(self) -> None:
        self.assertIsNone(alibaba_endpoint_error(BASE))
        self.assertIsNone(alibaba_endpoint_error("https://cn-hongkong.dashscope.aliyuncs.com/compatible-mode/v1"))
        for url in ("http://dashscope.aliyuncs.com/compatible-mode/v1", "https://dashscope.aliyuncs.com",
                    "https://dashscope.aliyuncs.com/", "https://user:pw@dashscope.aliyuncs.com/v1",
                    "https://dashscope.aliyuncs.com:8443/v1", "https://dashscope.aliyuncs.com/v1?key=x",
                    "https://dashscope.aliyuncs.com/v1#f", "https://dashscope.aliyuncs.com/../v1",
                    "https://dashscope.aliyuncs.com//v1", "https://evil.example.com/compatible-mode/v1",
                    "https://dashscope.aliyuncs.com/v1 space", "not a url", ""):
            with self.subTest(url=url):
                self.assertIsNotNone(alibaba_endpoint_error(url))

    def test_a_foreign_host_never_gets_a_provider_or_a_request(self) -> None:
        calls: List[int] = []
        for url in ("https://evil.example.com/compatible-mode/v1", "http://dashscope.aliyuncs.com/compatible-mode/v1"):
            with self.assertRaises(ProviderError) as ctx:
                AlibabaModelStudioProvider(name="a", base_url=url, api_key=KEY,
                                           client=httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(1))))
            self.assertEqual(ctx.exception.code, "provider_not_configured")
            self.assertNotIn(KEY, str(ctx.exception))
        self.assertEqual(calls, [])

    def test_redirects_are_never_followed_and_the_key_only_lives_in_the_auth_header(self) -> None:
        p = AlibabaModelStudioProvider(name="alibaba-01", base_url=BASE, api_key=KEY)
        self.assertFalse(p._client.follow_redirects)  # noqa: SLF001
        self.assertEqual(p._client.headers["authorization"], f"Bearer {KEY}")  # noqa: SLF001
        self.assertNotIn(KEY, repr(p))
        self.assertNotIn(KEY, str(p.capabilities()))
        self.assertNotIn(KEY, str(p.usage()))


# ====================================================================== wire format + accounting


class TestStreaming(unittest.TestCase):
    def test_deltas_usage_and_done_in_order_with_the_right_payload(self) -> None:
        seen = Seen()
        p = make(ok_handler(sse(chunk("Xin "), chunk("chào"), chunk(None, finish="stop"), USAGE)), seen)
        events = stream_events(p)
        self.assertEqual([e.text for e in events if isinstance(e, Delta)], ["Xin ", "chào"])
        usage = [e for e in events if isinstance(e, UsageEvent)]
        self.assertEqual((usage[0].input_tokens, usage[0].output_tokens), (11, 4))
        self.assertIsInstance(events[-1], Done)
        self.assertEqual(events[-1].finish_reason, "stop")
        payload = seen.payloads[0]
        self.assertEqual(payload["model"], "model-from-slot", "the model always comes from the slot")
        self.assertIs(payload["stream"], True)
        self.assertEqual(payload["stream_options"], {"include_usage": True})
        self.assertNotIn("user", payload, "no user reference (even hashed) is sent to this vendor")
        self.assertEqual(seen.requests[0].url.path, "/compatible-mode/v1/chat/completions")
        self.assertEqual(seen.requests[0].headers["authorization"], f"Bearer {KEY}")
        snap = p.usage()
        self.assertEqual((snap.requests, snap.input_tokens, snap.output_tokens, snap.errors), (1, 11, 4, 0))

    def test_reasoning_content_is_never_shown_or_forwarded(self) -> None:
        p = make(ok_handler(sse(chunk(reasoning="suy nghĩ riêng"), chunk(reasoning="tiếp"), chunk("Đáp án"),
                                chunk(None, finish="stop"))))
        events = stream_events(p)
        self.assertEqual([e.text for e in events if isinstance(e, Delta)], ["Đáp án"])
        self.assertNotIn("suy nghĩ", repr(events))

    def test_finish_reason_alone_is_a_complete_stream_even_without_done(self) -> None:
        p = make(ok_handler(sse(chunk("a"), chunk(None, finish="length"), done=False)))
        events = stream_events(p)
        self.assertEqual(events[-1].finish_reason, "length")

    def test_a_stream_cut_without_done_or_finish_reason_is_a_truncation_not_a_success(self) -> None:
        p = make(ok_handler(sse(chunk("nửa chừng"), done=False)))
        gen = p.stream(req())
        self.assertEqual(next(gen).text, "nửa chừng")
        with self.assertRaises(ProviderError) as ctx:
            next(gen)
        self.assertEqual((ctx.exception.code, ctx.exception.category), ("provider_truncated", "BAD_RESPONSE"))
        self.assertEqual(p.usage().errors, 1)

    def test_an_error_frame_inside_a_200_stream_is_classified_not_forwarded(self) -> None:
        frame = {"error": {"code": "Throttling.RateQuota", "message": LEAK}}
        p = make(ok_handler(sse(chunk("a"), frame, done=False)))
        gen = p.stream(req())
        next(gen)
        with self.assertRaises(ProviderError) as ctx:
            next(gen)
        self.assertEqual((ctx.exception.code, ctx.exception.category), ("provider_stream_error", "RATE_LIMITED"))
        self.assertNotIn(LEAK, repr(ctx.exception) + str(vars(ctx.exception)))

    def test_generate_streams_internally_and_returns_text_and_usage(self) -> None:
        seen = Seen()
        p = make(ok_handler(sse(chunk("OK"), chunk(None, finish="stop"), USAGE)), seen)
        res = p.generate(req())
        self.assertEqual((res.text, res.input_tokens, res.output_tokens, res.provider_name, res.model),
                         ("OK", 11, 4, "alibaba-01", "model-from-slot"))
        self.assertIs(seen.payloads[0]["stream"], True, "never a non-streaming call (some models refuse it)")

    def test_generate_with_an_empty_answer_is_a_provider_error(self) -> None:
        p = make(ok_handler(sse(chunk(None, finish="stop"), USAGE)))
        with self.assertRaises(ProviderError) as ctx:
            p.generate(req())
        self.assertEqual((ctx.exception.code, ctx.exception.category), ("provider_empty", "EMPTY_RESPONSE"))

    def test_the_control_plane_probes_this_provider_through_stream(self) -> None:
        self.assertTrue(AlibabaModelStudioProvider.probe_via_stream)


# ====================================================================== cancellation + timeouts


class TestCancellationAndTimeouts(unittest.TestCase):
    def test_closing_the_generator_closes_the_upstream_connection(self) -> None:
        stream = ClosableStream([sse(chunk("a"), chunk("b"), done=False)])
        p = make(lambda r: httpx.Response(200, stream=stream, headers={"content-type": "text/event-stream"}))
        gen = p.stream(req())
        self.assertEqual(next(gen).text, "a")
        self.assertFalse(stream.closed)
        gen.close()  # what StreamPump / contextlib.closing does on a client stop or disconnect
        self.assertTrue(stream.closed)

    def test_no_content_token_before_the_ttft_deadline_aborts_with_a_timeout(self) -> None:
        clock = Tick()
        frames = [sse(chunk(reasoning="nghĩ"), done=False), sse(chunk(reasoning="nghĩ tiếp"), done=False),
                  sse(chunk("quá muộn"), done=False)]
        stream = ClosableStream(frames, on_chunk=lambda: setattr(clock, "t", clock.t + 20))
        p = make(lambda r: httpx.Response(200, stream=stream), clock=clock, first_token_timeout_s=30.0)
        with self.assertRaises(ProviderError) as ctx:
            list(p.stream(req()))
        self.assertEqual((ctx.exception.code, ctx.exception.category), ("provider_timeout", "TIMEOUT"))
        self.assertTrue(ctx.exception.transient)
        self.assertTrue(stream.closed, "the connection is released")

    def test_total_deadline_aborts_a_stream_that_keeps_talking(self) -> None:
        clock = Tick()
        frames = [sse(chunk(f"t{i} "), done=False) for i in range(10)]
        p = make(lambda r: httpx.Response(200, stream=ClosableStream(frames, on_chunk=lambda: setattr(clock, "t", clock.t + 5))),
                 clock=clock, total_timeout_s=12.0, first_token_timeout_s=30.0)
        gen = p.stream(req())
        got = []
        with self.assertRaises(ProviderError) as ctx:
            for ev in gen:
                got.append(ev)
        self.assertGreaterEqual(len(got), 1, "it had started: the caller reports an interrupted answer")
        self.assertEqual(ctx.exception.code, "provider_timeout")

    def test_a_trickle_of_bytes_without_a_newline_cannot_hold_the_slot_past_the_deadline(self) -> None:
        """Deadlines are checked per received chunk, not per completed SSE line (cross-family review finding)."""
        clock = Tick()
        stream = ClosableStream([b"d"] * 200, on_chunk=lambda: setattr(clock, "t", clock.t + 5))
        p = make(lambda r: httpx.Response(200, stream=stream), clock=clock, total_timeout_s=12.0, first_token_timeout_s=60.0)
        with self.assertRaises(ProviderError) as ctx:
            list(p.stream(req()))
        self.assertEqual((ctx.exception.code, ctx.exception.category), ("provider_timeout", "TIMEOUT"))
        self.assertLessEqual(clock.t - 100, 20, "it stopped after a handful of chunks, not after 200")
        self.assertTrue(stream.closed)

    def test_line_framing_handles_split_multibyte_text_crlf_and_runaway_lines(self) -> None:
        text = "Chào bạn, đây là tiếng Việt ✓ 你好"
        raw = ("data: " + json.dumps(chunk(text), ensure_ascii=False) + "\r\n\r\ndata: " +
               json.dumps(chunk(None, finish="stop")) + "\r\n\r\ndata: [DONE]\r\n\r\n").encode("utf-8")
        for size in (1, 2, 3, 7):  # cuts land in the middle of multibyte characters
            chunks = [raw[i:i + size] for i in range(0, len(raw), size)]
            p = make(lambda r, c=chunks: httpx.Response(200, stream=ClosableStream(c)))
            self.assertEqual("".join(e.text for e in stream_events(p) if isinstance(e, Delta)), text, f"chunk size {size}")
        runaway = [b"x" * 100_000] * 12  # > 1 000 000 chars and no newline
        p = make(lambda r: httpx.Response(200, stream=ClosableStream(runaway)))
        with self.assertRaises(ProviderError) as ctx:
            stream_events(p)
        self.assertEqual((ctx.exception.code, ctx.exception.category), ("provider_bad_response", "BAD_RESPONSE"))

    def test_httpx_timeouts_and_network_errors_become_sanitised_provider_errors(self) -> None:
        def boom(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
            def handler(r: httpx.Request) -> httpx.Response:
                raise exc
            return handler

        cases = [(httpx.ReadTimeout("slow"), "provider_timeout", "TIMEOUT"),
                 (httpx.ConnectTimeout("slow"), "provider_timeout", "TIMEOUT"),
                 (httpx.ConnectError(f"cannot reach https://x/?key={LEAK}"), "provider_network_error", "NETWORK_ERROR"),
                 (httpx.RemoteProtocolError(f"peer closed {LEAK}"), "provider_network_error", "NETWORK_ERROR")]
        for exc, code, category in cases:
            with self.subTest(exc=type(exc).__name__):
                p = make(boom(exc))
                with self.assertRaises(ProviderError) as ctx:
                    stream_events(p)
                self.assertEqual((ctx.exception.code, ctx.exception.category), (code, category))
                self.assertNotIn(LEAK, str(ctx.exception) + repr(ctx.exception.__dict__))
                self.assertIsNone(ctx.exception.__cause__, "the raw exception (URL, headers) is not chained")

    def test_the_per_request_timeout_is_explicit_and_bounded(self) -> None:
        seen: List[httpx.Request] = []

        def handler(r: httpx.Request) -> httpx.Response:
            seen.append(r)
            return httpx.Response(200, content=sse(chunk("x"), chunk(None, finish="stop")))

        p = make(handler, read_timeout_s=20.0, connect_timeout_s=10.0)
        stream_events(p, timeout_s=60.0)
        t = seen[0].extensions["timeout"]
        self.assertEqual((t["connect"], t["read"]), (10.0, 20.0))
        seen.clear()
        stream_events(p, timeout_s=5.0)  # a shorter request budget wins
        t = seen[0].extensions["timeout"]
        self.assertEqual((t["connect"], t["read"]), (5.0, 5.0))


# ====================================================================== error classification


def err_response(status: int, body: Any, headers: Optional[Dict[str, str]] = None) -> httpx.Response:
    content = json.dumps(body).encode() if not isinstance(body, bytes) else body
    return httpx.Response(status, content=content, headers=headers or {})


class TestErrorClassification(unittest.TestCase):
    #: (status, body, expected category) — status first, vendor code/type/message second, tolerant keywords.
    MATRIX = [
        (401, {"error": {"code": "invalid_api_key", "message": "Incorrect API key"}}, "AUTH_FAILED"),
        (401, {"code": "InvalidApiKey", "message": "Invalid API-key provided."}, "AUTH_FAILED"),
        (403, {"code": "AccessDenied", "message": "no access"}, "PERMISSION_DENIED"),
        (403, {"code": "AllocationQuota.FreeTierOnly", "message": "free tier exhausted"}, "QUOTA_EXHAUSTED"),
        (400, {"code": "Arrearage", "message": "Access denied, please make sure your account is in good standing."},
         "QUOTA_EXHAUSTED"),
        # `Throttling.AllocationQuota` is ambiguous (allocation / rate ceilings too): a rate limit, NOT a day-long park.
        (429, {"code": "Throttling.AllocationQuota", "message": "Allocated quota exceeded"}, "RATE_LIMITED"),
        (429, {"code": "AllocationQuota.FreeTierOnly", "message": "free tier exhausted"}, "QUOTA_EXHAUSTED"),
        (429, {"error": {"code": "insufficient_quota", "message": "x"}}, "QUOTA_EXHAUSTED"),
        (429, {"message": "Your free tier is exhausted"}, "QUOTA_EXHAUSTED"),  # no vendor code at all: message is the only signal
        (429, {"code": "Throttling.RateQuota", "message": "Requests rate limit exceeded"}, "RATE_LIMITED"),
        (429, {"error": {"code": "limit_requests"}}, "RATE_LIMITED"),
        (429, b"not json at all", "RATE_LIMITED"),
        (404, {"error": {"code": "model_not_found"}}, "MODEL_NOT_FOUND"),
        (400, {"code": "ModelNotFound", "message": "Model not exist."}, "MODEL_NOT_FOUND"),
        (400, {"code": "DataInspectionFailed", "message": "Input data may contain inappropriate content."},
         "CONTENT_FILTERED"),
        (400, {"error": {"code": "context_length_exceeded"}}, "CONTEXT_TOO_LONG"),
        (400, {"code": "InvalidParameter", "message": "Range of input length should be [1, 30720]"}, "CONTEXT_TOO_LONG"),
        (400, {"code": "InvalidParameter", "message": "bad param"}, "BAD_REQUEST"),
        (408, b"", "TIMEOUT"),
        (504, b"", "TIMEOUT"),
        (503, b"", "UNAVAILABLE"),
        (500, {"code": "InternalError"}, "SERVER_ERROR"),
        (502, b"<html>bad gateway</html>", "SERVER_ERROR"),
        (418, b"", "BAD_REQUEST"),
    ]

    def test_matrix(self) -> None:
        for status, body, expected in self.MATRIX:
            with self.subTest(status=status, body=str(body)[:60]):
                p = make(lambda r, s=status, b=body: err_response(s, b))
                with self.assertRaises(ProviderError) as ctx:
                    stream_events(p)
                e = ctx.exception
                self.assertEqual(e.category, expected)
                self.assertEqual(e.code, f"provider_http_{status}")
                self.assertIn(e.category, CATEGORIES)
                self.assertEqual(p.usage().errors, 1)

    def test_every_category_passes_the_control_plane_sanitiser(self) -> None:
        from server.ai_assistant.control.service import _ERROR_CATEGORY_RE, _ERROR_CODE_RE
        for c in CATEGORIES:
            self.assertRegex(c, _ERROR_CATEGORY_RE.pattern)
        for code in ("provider_http_429", "provider_timeout", "provider_network_error", "provider_truncated",
                     "provider_stream_error", "provider_empty", "provider_not_configured", "provider_gate_closed"):
            self.assertRegex(code, _ERROR_CODE_RE.pattern)

    def test_vendor_text_never_reaches_the_exception(self) -> None:
        bodies = [{"error": {"code": "invalid_api_key", "message": f"Incorrect API key provided: {LEAK}"}},
                  {"code": "Throttling", "message": f"request {LEAK} account 1234567890", "request_id": LEAK},
                  {"error": {"message": LEAK, "type": LEAK, "code": LEAK}}]
        for body in bodies:
            for status in (400, 401, 403, 404, 429, 500):
                p = make(lambda r, s=status, b=body: err_response(s, b))
                with self.assertRaises(ProviderError) as ctx:
                    stream_events(p)
                e = ctx.exception
                blob = " ".join([str(e), repr(e), str(e.code), str(e.category), repr(e.__dict__), repr(e.args)])
                self.assertNotIn(LEAK, blob)
                self.assertNotIn(KEY, blob)
                self.assertNotIn("1234567890", blob)

    def test_user_text_echoed_inside_a_400_message_cannot_change_a_slots_state(self) -> None:
        """Validation errors often echo the offending input. If a user's message contains 'free tier', 'unauthorized' or
        'model not exist', the vendor's 400 must not be read as quota exhaustion / bad key / missing model — that would let
        anyone park or break a healthy slot. Only the vendor CODE can do that on a 400."""
        echo = "free tier arrearage overdue unauthorized invalid_api_key model not exist throttling rate limit"
        for body in ({"code": "InvalidParameter", "message": f"bad input: {echo}"},
                     {"error": {"code": "invalid_request_error", "message": f"input {echo}"}},
                     {"message": echo}):
            with self.subTest(body=str(body)[:50]):
                p = make(lambda r, b=body: err_response(400, b))
                with self.assertRaises(ProviderError) as ctx:
                    stream_events(p)
                self.assertEqual(ctx.exception.category, "BAD_REQUEST")
        self.assertIn(classify_error(400, json.dumps({"code": "Arrearage", "message": "x"}).encode()), {"QUOTA_EXHAUSTED"})
        self.assertEqual(classify_error(400, json.dumps({"code": "DataInspectionFailed"}).encode()), "CONTENT_FILTERED")
        self.assertEqual(classify_error(400, json.dumps({"message": "Range of input length should be [1, 30720]"}).encode()),
                         "CONTEXT_TOO_LONG")

    def test_the_vendor_code_wins_over_the_message_and_a_message_is_only_a_fallback_when_there_is_no_code(self) -> None:
        # a code is present -> a quota-sounding message cannot override it
        self.assertEqual(classify_error(429, json.dumps({"code": "Throttling.RateQuota", "message": "free tier overdue"}).encode()),
                         "RATE_LIMITED")
        self.assertEqual(classify_error(403, json.dumps({"code": "AccessDenied", "message": "free tier arrearage"}).encode()),
                         "PERMISSION_DENIED")
        # no code, not a 400 -> the message may speak
        self.assertEqual(classify_error(403, json.dumps({"message": "account overdue"}).encode()), "QUOTA_EXHAUSTED")
        self.assertEqual(classify_error(400, json.dumps({"message": "account overdue"}).encode()), "BAD_REQUEST")

    def test_an_output_moderation_frame_inside_a_200_stream_is_a_request_fault_not_a_slot_fault(self) -> None:
        for frame in ({"error": {"code": "data_inspection_failed", "message": "x"}},
                      {"error": {"code": "DataInspectionFailed"}},
                      {"error": {"code": "invalid_parameter", "message": "Range of input length should be [1, 8]"}}):
            p = make(ok_handler(sse(chunk("a"), frame, done=False)))
            gen = p.stream(req())
            next(gen)
            with self.assertRaises(ProviderError) as ctx:
                next(gen)
            self.assertEqual(ctx.exception.code, "provider_stream_error")
            self.assertIn(ctx.exception.category, {"CONTENT_FILTERED", "CONTEXT_TOO_LONG"})

    def test_garbage_usage_figures_are_zero_not_an_exception(self) -> None:
        for usage in ({"prompt_tokens": "lots", "completion_tokens": None}, {"prompt_tokens": -5, "completion_tokens": float("nan")},
                      {"prompt_tokens": 10 ** 12, "completion_tokens": True}, {"prompt_tokens": 7.9, "completion_tokens": 2}):
            p = make(ok_handler(sse(chunk("x"), {"choices": [], "usage": usage}, chunk(None, finish="stop"))))
            events = stream_events(p)
            u = [e for e in events if isinstance(e, UsageEvent)][0]
            self.assertGreaterEqual(u.input_tokens, 0)
            self.assertGreaterEqual(u.output_tokens, 0)
        p = make(ok_handler(sse(chunk("x"), {"choices": [], "usage": {"prompt_tokens": 7.9, "completion_tokens": 2}},
                                chunk(None, finish="stop"))))
        u = [e for e in stream_events(p) if isinstance(e, UsageEvent)][0]
        self.assertEqual((u.input_tokens, u.output_tokens), (7, 2))

    def test_a_foreign_timeout_exception_never_puts_its_text_in_the_error(self) -> None:
        def handler(r: httpx.Request) -> httpx.Response:
            raise TimeoutError(f"deadline for https://x/?key={LEAK}")

        p = make(handler)
        with self.assertRaises(ProviderError) as ctx:
            stream_events(p)
        self.assertEqual(ctx.exception.code, "provider_unexpected_error")
        self.assertNotIn(LEAK, str(ctx.exception) + repr(ctx.exception.args))

    def test_request_fault_categories_are_the_three_that_blame_the_request_not_the_slot(self) -> None:
        from server.llm_gateway.alibaba import REQUEST_FAULT_CATEGORIES
        self.assertEqual(REQUEST_FAULT_CATEGORIES, frozenset({"CONTENT_FILTERED", "CONTEXT_TOO_LONG", "BAD_REQUEST"}))
        self.assertLessEqual(REQUEST_FAULT_CATEGORIES, CATEGORIES)

    def test_rate_limit_keeps_a_clamped_retry_after_but_quota_exhaustion_does_not(self) -> None:
        cases = [({"Retry-After": "7"}, 7.0), ({"Retry-After": "0"}, 1.0), ({"Retry-After": "86400"}, 600.0),
                 ({"Retry-After": "abc"}, None), ({}, None)]
        for headers, expected in cases:
            with self.subTest(headers=headers):
                p = make(lambda r, h=headers: err_response(429, {"code": "Throttling.RateQuota"}, h))
                with self.assertRaises(ProviderError) as ctx:
                    stream_events(p)
                self.assertEqual(ctx.exception.retry_after_s, expected)
                self.assertTrue(ctx.exception.transient)
        p = make(lambda r: err_response(429, {"code": "AllocationQuota.FreeTierOnly"}, {"Retry-After": "30"}))
        with self.assertRaises(ProviderError) as ctx:
            stream_events(p)
        self.assertEqual(ctx.exception.category, "QUOTA_EXHAUSTED")
        self.assertIsNone(ctx.exception.retry_after_s, "a quota wall is parked until midnight, not retried in 30 s")
        self.assertFalse(ctx.exception.transient)

    def test_classify_error_is_pure_and_total(self) -> None:
        for status in (0, 100, 200, 301, 400, 499, 500, 599, 999):
            self.assertIn(classify_error(status, b"\xff\xfe not json"), CATEGORIES)
        self.assertEqual(classify_error(0, b'{"error": {"code": "Arrearage"}}'), "QUOTA_EXHAUSTED")
        self.assertEqual(classify_error(0, b'{"error": {"code": "Throttling"}}'), "RATE_LIMITED")
        self.assertEqual(classify_error(0, b"{}"), "SERVER_ERROR")


if __name__ == "__main__":
    unittest.main()
