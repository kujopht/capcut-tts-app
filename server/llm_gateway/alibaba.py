"""
Alibaba Cloud Model Studio (DashScope, OpenAI-compatible mode) chat adapter — Fanfic AI control plane.

A SUBCLASS of `OpenAICompatChatProvider`: the shared base class (which production Gemini slots use) is not touched. What this
adapter adds on top of the OpenAI-compatible wire format:

  * the endpoint host is re-validated HERE (defence in depth on top of `control.model`): the API key can only ever be sent to
    `[label.]dashscope[-x].aliyuncs.com` over https, redirects are never followed;
  * explicit timeouts: connect, inter-chunk read, first CONTENT token (TTFT) and total wall-clock — the stream aborts with
    `provider_timeout` instead of holding a slot (and one of the 4 SSE streams of the instance) open;
  * every upstream failure is turned into OUR closed set of categories (`CATEGORIES`) from the HTTP status plus the vendor's
    error code/type — vendor text (message, request echo, ids) is parsed in memory and dropped, never stored, logged or
    returned. Quota exhaustion is told apart from a plain rate limit so the control plane can park the slot until midnight
    instead of retrying it every 30 seconds;
  * a stream that ends without `[DONE]` and without a `finish_reason` is a truncation, not a completed answer;
  * `generate()` streams internally (some Model Studio models refuse non-streaming calls) so the owner probe exercises the
    same path as real traffic; `probe_via_stream` tells the control plane to time the probe through `stream()`;
  * no `user` field is sent upstream (data minimisation: no user reference, even hashed, leaves for a new vendor).

Honesty note (same convention as `chat_providers.py`): built against Alibaba's PUBLICLY DOCUMENTED wire format and exercised
only through `httpx.MockTransport` — it has not been run against a real, authenticated Model Studio endpoint. The error-code
mapping is deliberately tolerant (status first, vendor code/type second) because the exact vendor strings must be confirmed
in the canary. No model ID is baked in anywhere: the model always comes from the slot.
"""
from __future__ import annotations

import codecs
import json
import re
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from urllib.parse import urlsplit

import httpx

from server.llm_gateway.chat_provider import (
    Delta,
    Done,
    GenerateRequest,
    GenerateResult,
    ProviderCapabilities,
    ProviderError,
    StreamEvent,
    UsageEvent,
)
from server.llm_gateway.chat_providers import (
    ERROR_BODY_PEEK_BYTES,
    OpenAICompatChatProvider,
    _peek_stream_error,
    _retry_after_s,
)

#: `dashscope.aliyuncs.com`, `dashscope-intl.aliyuncs.com`, `dashscope-us.aliyuncs.com` and one optional region label in front
#: (`cn-hongkong.dashscope.aliyuncs.com`). Anchored, one label at most: no other `aliyuncs.com` service (object storage,
#: function compute …) — whose names customers can choose — can ever receive the key.
ALIBABA_HOST_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?\.)?dashscope(?:-[a-z0-9]{1,16})?\.aliyuncs\.com$")
_PATH_RE = re.compile(r"^/[A-Za-z0-9._~/-]{0,100}$")

#: The ONLY error categories this adapter reports — letters/underscore (they must pass the control plane's sanitiser).
CATEGORIES = frozenset({
    "AUTH_FAILED", "PERMISSION_DENIED", "QUOTA_EXHAUSTED", "RATE_LIMITED", "MODEL_NOT_FOUND", "CONTENT_FILTERED",
    "CONTEXT_TOO_LONG", "BAD_REQUEST", "SERVER_ERROR", "UNAVAILABLE", "TIMEOUT", "NETWORK_ERROR", "BAD_RESPONSE",
    "EMPTY_RESPONSE",
})
#: Transient = the same request may succeed elsewhere / a moment later.
_TRANSIENT = frozenset({"RATE_LIMITED", "SERVER_ERROR", "UNAVAILABLE", "TIMEOUT", "NETWORK_ERROR", "EMPTY_RESPONSE"})

# Keyword groups matched (lower-cased, in memory only) against the vendor's error code / type / message.
# Quota = UNAMBIGUOUS "no free quota / no money" only. `Throttling.AllocationQuota` ("allocated quota exceeded") is deliberately
# NOT here: the public docs use it for allocation/rate ceilings too, and parking a healthy slot for the rest of the UTC day
# because of a short TPM burst is the worse mistake — it is treated as a rate limit (cooldown) until the canary says otherwise.
_QUOTA_WORDS = ("freetieronly", "free tier", "free_tier", "insufficient_quota", "insufficient quota", "arrearage",
                "overdue", "good standing", "insufficient balance", "insufficient_balance")
_FILTER_WORDS = ("inspection", "inappropriate", "content_filter", "content filter", "sensitive", "safety")
_LENGTH_WORDS = ("range of input length", "too long", "context_length", "maximum context", "input length",
                 "exceeds the maximum")
_MODEL_WORDS = ("model_not_found", "modelnotfound", "model not exist", "model does not exist", "model_not_exist")
_RATE_WORDS = ("throttl", "limit_requests", "limit_burst", "rate limit", "rate_limit", "ratequota", "allocationquota",
               "allocation quota", "allocated quota")
_AUTH_WORDS = ("invalid_api_key", "invalidapikey", "invalid api-key", "invalid api key", "unauthorized")
_MAX_TOKENS_SCANNED = 800


def alibaba_host_allowed(host: str) -> bool:
    return bool(ALIBABA_HOST_RE.match((host or "").lower()))


def alibaba_endpoint_error(endpoint: str) -> Optional[str]:
    """None when `endpoint` is an https Model Studio URL we may send the key to; else a short Vietnamese reason."""
    try:
        u = urlsplit(endpoint or "")
        port = u.port
    except ValueError:
        return "URL không hợp lệ"
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment:
        return "chỉ nhận https://host/đường-dẫn (không user, query hay fragment)"
    if port not in (None, 443):
        return "chỉ cổng 443"
    if not alibaba_host_allowed(u.hostname):
        return "máy chủ phải là dạng dashscope[-vùng].aliyuncs.com của Alibaba Model Studio"
    if len(u.path) < 2 or not _PATH_RE.match(u.path) or ".." in u.path or "//" in u.path:
        return "đường dẫn phải bắt đầu bằng / (ví dụ /compatible-mode/v1)"
    return None


def _error_fields(raw: bytes) -> Tuple[str, str]:
    """(codes, message): lower-cased vendor error code/type fields, and the free-text message. In memory only — NEVER returned
    or logged. The message may ECHO user content (validation errors often do), so only the codes can drive decisions that
    change a slot's state; the message is used only for request-fault categories, which never touch slot health."""
    try:
        data = json.loads((raw or b"")[:ERROR_BODY_PEEK_BYTES].decode("utf-8", errors="replace"))
    except ValueError:
        return "", ""
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return "", ""
    codes: List[str] = []
    messages: List[str] = []
    err = data.get("error")
    for src in (err if isinstance(err, dict) else {}, data):
        for k in ("code", "type", "error_code"):
            v = src.get(k)
            if isinstance(v, str):
                codes.append(v)
        v = src.get("message")
        if isinstance(v, str):
            messages.append(v)
    return " ".join(codes).lower()[:_MAX_TOKENS_SCANNED], " ".join(messages).lower()[:_MAX_TOKENS_SCANNED]


#: Categories caused by the REQUEST (its content or size), not by the slot: they must never open a breaker / park a slot,
#: otherwise anyone could take the whole pool offline by sending content the vendor rejects. The control plane reads this set.
REQUEST_FAULT_CATEGORIES = frozenset({"CONTENT_FILTERED", "CONTEXT_TOO_LONG", "BAD_REQUEST"})


def classify_error(status: int, raw: bytes = b"") -> str:
    """Our closed category for an upstream failure: HTTP status first, then the vendor's error CODE/TYPE. Decisions that change
    a slot's state (auth, quota, rate limit, model) never rest on the free-text message of a 400 (it may echo user content)."""
    codes, message = _error_fields(raw)
    in_codes = lambda words: any(w in codes for w in words)  # noqa: E731
    in_all = lambda words: any(w in codes or w in message for w in words)  # noqa: E731
    if status == 401 or in_codes(_AUTH_WORDS):
        return "AUTH_FAILED"
    # The vendor CODE decides. The free-text message is consulted only when the vendor sent NO code, and never on a 400 (it may
    # echo user content). Alibaba's own arrears error is a 400 with an `Arrearage` code. 0 = an error frame inside a 200 stream.
    use_message = not codes and status != 400
    quota_seen = in_codes(_QUOTA_WORDS) or (use_message and any(w in message for w in _QUOTA_WORDS))
    if status in (0, 400, 402, 403, 429) and quota_seen:
        return "QUOTA_EXHAUSTED"
    if status == 402:
        return "QUOTA_EXHAUSTED"
    if status == 429 or (status == 0 and in_all(_RATE_WORDS)):
        return "RATE_LIMITED"
    if status == 403:
        return "PERMISSION_DENIED"
    if status == 404 or in_codes(_MODEL_WORDS):
        return "MODEL_NOT_FOUND"
    # Request faults (content refused / too long): also when the error arrives as a frame inside a 200 stream (status 0), e.g.
    # output moderation — they must never be read as a slot fault.
    if status in (0, 400, 413, 422) and in_all(_FILTER_WORDS):
        return "CONTENT_FILTERED"
    if status in (0, 400, 413, 422) and in_all(_LENGTH_WORDS):
        return "CONTEXT_TOO_LONG"
    if status in (408, 504):
        return "TIMEOUT"
    if status == 503:
        return "UNAVAILABLE"
    if 400 <= status < 500:
        return "BAD_REQUEST"
    return "SERVER_ERROR"


#: A single SSE line longer than this (no newline in sight) is not a chat stream.
MAX_LINE_CHARS = 1_000_000


def _read_lines(resp: httpx.Response, check: Callable[[], None]) -> Iterator[str]:
    """Lines of a streamed response, calling `check()` after every chunk of bytes that arrives (see the deadline note above).
    Incremental UTF-8 decoding (a multibyte character split across two chunks is not corrupted); `\\r\\n` and `\\n` both end a line."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    buf = ""
    for chunk in resp.iter_bytes():
        check()
        buf += decoder.decode(chunk)
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            yield line.rstrip("\r")
        if len(buf) > MAX_LINE_CHARS:
            raise _provider_error("Luồng trả về không đúng định dạng SSE.", code="provider_bad_response", category="BAD_RESPONSE")
    buf += decoder.decode(b"", final=True)
    if buf:
        yield buf.rstrip("\r")


def _token_count(v: Any) -> int:
    """A usage figure from the wire -> a non-negative int; anything odd is 0 (the route then estimates) — never an exception
    that would escape the adapter (and log vendor text through the gateway's generic handler)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v < 0 or v > 10 ** 9:
        return 0
    return int(v)


def _provider_error(message: str, *, code: str, category: str, retry_after_s: Optional[float] = None) -> ProviderError:
    return ProviderError(message, transient=category in _TRANSIENT, code=code, retry_after_s=retry_after_s, category=category)


class _DeadlineExceeded(Exception):
    """Raised by OUR deadline checks only (`reason` is one of our own two markers) — never a foreign exception's text."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AlibabaModelStudioProvider(OpenAICompatChatProvider):
    """One Model Studio model behind one control-plane slot (the provider `name` is the SLOT id)."""

    #: `ControlPlane.probe` times the owner probe through `stream()` (TTFT) for providers that set this.
    probe_via_stream = True

    def __init__(self, *, name: str, base_url: str, api_key: str,
                 client: Optional[httpx.Client] = None,
                 clock: Callable[[], float] = time.monotonic,
                 connect_timeout_s: float = 10.0, read_timeout_s: float = 20.0,
                 first_token_timeout_s: float = 30.0, total_timeout_s: float = 120.0) -> None:
        reason = alibaba_endpoint_error(base_url)
        if reason:
            raise ProviderError(f"Endpoint của '{name}' không hợp lệ cho Alibaba Model Studio.", transient=False,
                                code="provider_not_configured", category="BAD_REQUEST")
        self._clock = clock
        self._connect_timeout_s = connect_timeout_s
        self._read_timeout_s = read_timeout_s
        self._first_token_timeout_s = first_token_timeout_s
        self._total_timeout_s = total_timeout_s
        if client is None:
            client = httpx.Client(
                base_url=base_url.rstrip("/"), follow_redirects=False,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=httpx.Timeout(read_timeout_s, connect=connect_timeout_s))
        super().__init__(
            name=name, base_url=base_url, api_key=api_key, client=client,
            capabilities=ProviderCapabilities(streaming=True, tools=False, web_search=False, vision=False,
                                              max_context_tokens=32000))

    def __repr__(self) -> str:  # never reflect headers/keys
        return f"<AlibabaModelStudioProvider name={self.name!r}>"

    def _payload(self, req: GenerateRequest, *, stream: bool) -> Dict[str, Any]:
        payload = super()._payload(req, stream=stream)
        payload.pop("user", None)  # data minimisation: no user reference leaves for this vendor
        return payload

    # ------------------------------------------------------------------ non-streaming = streaming internally
    def generate(self, req: GenerateRequest) -> GenerateResult:
        parts: List[str] = []
        in_tok = out_tok = 0
        finish = "stop"
        for ev in self.stream(req):
            if isinstance(ev, Delta):
                parts.append(ev.text)
            elif isinstance(ev, UsageEvent):
                in_tok, out_tok = ev.input_tokens, ev.output_tokens
            elif isinstance(ev, Done):
                finish = ev.finish_reason
        text = "".join(parts).strip()
        if not text:
            self._counters.errors += 1
            raise _provider_error(f"'{self.name}' trả về nội dung rỗng.", code="provider_empty", category="EMPTY_RESPONSE")
        return GenerateResult(text=text, provider_name=self.name, model=req.model, input_tokens=in_tok,
                              output_tokens=out_tok, finish_reason=finish)

    # ------------------------------------------------------------------ streaming
    def _timeout(self, req: GenerateRequest) -> httpx.Timeout:
        read = max(1.0, min(self._read_timeout_s, req.timeout_s))
        return httpx.Timeout(read, connect=max(1.0, min(self._connect_timeout_s, req.timeout_s)))

    def _stream_inner(self, req: GenerateRequest) -> Iterator[StreamEvent]:
        self._counters.requests += 1
        started_at = self._clock()
        got_content = False
        saw_end = False
        finish_reason = "stop"
        try:
            with self._client.stream("POST", self._completions_path, json=self._payload(req, stream=True),
                                     timeout=self._timeout(req)) as resp:
                if resp.status_code != 200:
                    self._counters.errors += 1
                    category = classify_error(resp.status_code, _peek_stream_error(resp))
                    raise _provider_error(
                        f"'{self.name}' trả lỗi {resp.status_code}.", code=f"provider_http_{resp.status_code}",
                        category=category,
                        retry_after_s=_retry_after_s(resp) if category == "RATE_LIMITED" else None)
                def check_deadlines() -> None:
                    now = self._clock()
                    if now - started_at > self._total_timeout_s:
                        raise _DeadlineExceeded("total")
                    if not got_content and now - started_at > self._first_token_timeout_s:
                        raise _DeadlineExceeded("first-token")

                # Deadlines are checked on EVERY received chunk of bytes, not only when a full SSE line completes: an upstream
                # that trickles bytes (never a newline) just under the inter-chunk read timeout cannot hold the slot open.
                for line in _read_lines(resp, check_deadlines):
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[len("data:"):].strip()
                    if raw == "[DONE]":
                        saw_end = True
                        break
                    try:
                        chunk = json.loads(raw)
                    except ValueError:
                        continue
                    if not isinstance(chunk, dict):
                        continue
                    if chunk.get("error"):
                        self._counters.errors += 1
                        raise _provider_error(f"'{self.name}' báo lỗi giữa luồng.", code="provider_stream_error",
                                              category=classify_error(0, raw.encode("utf-8", errors="replace")))
                    usage = chunk.get("usage")
                    if isinstance(usage, dict) and usage:
                        in_tok, out_tok = _token_count(usage.get("prompt_tokens")), _token_count(usage.get("completion_tokens"))
                        self._counters.input_tokens += in_tok
                        self._counters.output_tokens += out_tok
                        yield UsageEvent(input_tokens=in_tok, output_tokens=out_tok)
                    choices = chunk.get("choices") or []
                    if not choices or not isinstance(choices[0], dict):
                        continue
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content") if isinstance(delta, dict) else None
                    if isinstance(text, str) and text:  # `reasoning_content` is deliberately never shown or forwarded
                        got_content = True
                        yield Delta(text=text)
                    fr = choices[0].get("finish_reason")
                    if fr:
                        finish_reason = str(fr)
                        saw_end = True
                if not saw_end:
                    self._counters.errors += 1
                    raise _provider_error(f"Luồng của '{self.name}' kết thúc dở dang.", code="provider_truncated",
                                          category="BAD_RESPONSE")
                yield Done(finish_reason=finish_reason)
        except ProviderError:
            raise
        except _DeadlineExceeded as exc:
            self._counters.errors += 1
            raise _provider_error(f"'{self.name}' quá thời gian chờ ({exc.reason}).", code="provider_timeout",
                                  category="TIMEOUT") from None
        except httpx.TimeoutException:
            self._counters.errors += 1
            raise _provider_error(f"'{self.name}' quá thời gian chờ.", code="provider_timeout", category="TIMEOUT") from None
        except httpx.HTTPError as exc:
            self._counters.errors += 1
            # Class name only: an exception text can carry URLs/headers.
            raise _provider_error(f"Không gọi được '{self.name}' ({type(exc).__name__}).", code="provider_network_error",
                                  category="NETWORK_ERROR") from None
