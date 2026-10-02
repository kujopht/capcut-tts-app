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
_QUOTA_WORDS = ("freetieronly", "free tier", "free_tier", "allocationquota", "allocation quota", "allocated quota",
                "insufficient_quota", "insufficient quota", "arrearage", "overdue", "good standing",
                "insufficient balance", "insufficient_balance")
_FILTER_WORDS = ("inspection", "inappropriate", "content_filter", "content filter", "sensitive", "safety")
_LENGTH_WORDS = ("range of input length", "too long", "context_length", "maximum context", "input length",
                 "exceeds the maximum")
_MODEL_WORDS = ("model_not_found", "modelnotfound", "model not exist", "model does not exist", "model_not_exist")
_RATE_WORDS = ("throttl", "limit_requests", "limit_burst", "rate limit", "rate_limit", "ratequota")
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


def _error_text(raw: bytes) -> str:
    """Lower-cased concatenation of the vendor's error code/type/message. In memory only — NEVER returned or logged."""
    try:
        data = json.loads((raw or b"")[:ERROR_BODY_PEEK_BYTES].decode("utf-8", errors="replace"))
    except ValueError:
        return ""
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return ""
    parts: List[str] = []
    err = data.get("error")
    for src in (err if isinstance(err, dict) else {}, data):
        for k in ("code", "type", "message", "error_code"):
            v = src.get(k)
            if isinstance(v, str):
                parts.append(v)
    return " ".join(parts).lower()[:_MAX_TOKENS_SCANNED]


def classify_error(status: int, raw: bytes = b"") -> str:
    """Our closed category for an upstream failure: HTTP status first, vendor code/type/message second."""
    text = _error_text(raw)
    has = lambda words: any(w in text for w in words)  # noqa: E731
    if status == 401 or has(_AUTH_WORDS):
        return "AUTH_FAILED"
    if status in (0, 400, 402, 403, 429) and has(_QUOTA_WORDS):  # 0 = an error frame inside a 200 stream
        return "QUOTA_EXHAUSTED"
    if status == 402:
        return "QUOTA_EXHAUSTED"
    if status == 429 or (status == 0 and has(_RATE_WORDS)):
        return "RATE_LIMITED"
    if status == 403:
        return "PERMISSION_DENIED"
    if status == 404 or has(_MODEL_WORDS):
        return "MODEL_NOT_FOUND"
    if status in (400, 413, 422) and has(_FILTER_WORDS):
        return "CONTENT_FILTERED"
    if status in (400, 413, 422) and has(_LENGTH_WORDS):
        return "CONTEXT_TOO_LONG"
    if status in (408, 504):
        return "TIMEOUT"
    if status == 503:
        return "UNAVAILABLE"
    if 400 <= status < 500:
        return "BAD_REQUEST"
    return "SERVER_ERROR"


def _provider_error(message: str, *, code: str, category: str, retry_after_s: Optional[float] = None) -> ProviderError:
    return ProviderError(message, transient=category in _TRANSIENT, code=code, retry_after_s=retry_after_s, category=category)


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
                for line in resp.iter_lines():
                    now = self._clock()
                    if now - started_at > self._total_timeout_s:
                        raise TimeoutError("total")
                    if not got_content and now - started_at > self._first_token_timeout_s:
                        raise TimeoutError("first-token")
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
                        in_tok = int(usage.get("prompt_tokens", 0) or 0)
                        out_tok = int(usage.get("completion_tokens", 0) or 0)
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
        except TimeoutError as exc:
            self._counters.errors += 1
            raise _provider_error(f"'{self.name}' quá thời gian chờ ({exc}).", code="provider_timeout",
                                  category="TIMEOUT") from None
        except httpx.TimeoutException:
            self._counters.errors += 1
            raise _provider_error(f"'{self.name}' quá thời gian chờ.", code="provider_timeout", category="TIMEOUT") from None
        except httpx.HTTPError as exc:
            self._counters.errors += 1
            # Class name only: an exception text can carry URLs/headers.
            raise _provider_error(f"Không gọi được '{self.name}' ({type(exc).__name__}).", code="provider_network_error",
                                  category="NETWORK_ERROR") from None
