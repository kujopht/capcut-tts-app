"""
Real `ChatProvider` implementations — Fanfic AI Assistant V1.

Same honesty note as `server/llm_gateway/providers.py`: these are real,
correctly-shaped HTTP clients against each vendor's PUBLICLY DOCUMENTED wire
format, built and tested only via `httpx.MockTransport` — none has been
exercised against a real, authenticated endpoint in this environment.

    OpenAICompatChatProvider   base class: any OpenAI chat-completions-SHAPED
                               endpoint (`/chat/completions`, SSE `data: {...}`
                               frames terminated by `data: [DONE]`).
    QwenDashScopeProvider      OpenAICompatChatProvider with DashScope's
                               "compatible mode" defaults.
    AzureOpenAIProvider       distinct URL shape (`.../deployments/{d}/chat/
                               completions?api-version=...`) and header
                               (`api-key`, not `Authorization: Bearer`) —
                               everything else (SSE frame parsing) is shared
                               via the same private helper.
    TencentCompatProvider      OpenAI-compatible skeleton, explicitly marked
                               untested against a real Tencent endpoint.
    MockChatProvider           deterministic word-by-word stream, no network —
                               dev/test/QA-UI without any provider key.
    LegacyCompletionAdapter    wraps a `ChatProvider` as the OLD `LLMProvider`
                               (`server/llm_gateway/provider.py`) shape, for
                               future reuse by the reader AI — NOT wired into
                               `/api/chat/ask` in V1.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterator, List, Optional

import httpx

from server.llm_gateway.chat_provider import (
    ChatProvider,
    ChatTurn,
    Delta,
    Done,
    GenerateRequest,
    GenerateResult,
    ProviderCapabilities,
    ProviderError,
    ProviderUsageSnapshot,
    StreamEvent,
    ToolCall,
    ToolCallEvent,
    UsageEvent,
)
from server.llm_gateway.provider import LLMCompletion, LLMProvider, LLMProviderError

DEFAULT_TIMEOUT_SECONDS = 60.0


def _turn_to_openai_message(turn: ChatTurn) -> Dict[str, Any]:
    role = turn.role if turn.role in ("system", "user", "assistant", "tool") else "user"
    msg: Dict[str, Any] = {"role": role, "content": turn.content}
    if turn.name:
        msg["name"] = turn.name
    return msg


class _Counters:
    """Process-local usage counters — see `ProviderUsageSnapshot`'s own
    docstring for why this is intentionally NOT durable storage."""

    def __init__(self) -> None:
        self.requests = 0
        self.errors = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def snapshot(self) -> ProviderUsageSnapshot:
        return ProviderUsageSnapshot(
            requests=self.requests, errors=self.errors,
            input_tokens=self.input_tokens, output_tokens=self.output_tokens)


class OpenAICompatChatProvider(ChatProvider):
    """Any OpenAI chat-completions-SHAPED endpoint. Distinguished from one
    another only by `base_url`/`api_key`/`model`/headers at construction
    time — same reasoning as this repo's `OpenAICompatProvider` (the older,
    non-streaming contract in `providers.py`)."""

    def __init__(self, *, name: str, base_url: str, api_key: str,
                extra_headers: Optional[Dict[str, str]] = None,
                capabilities: Optional[ProviderCapabilities] = None,
                client: Optional[httpx.Client] = None,
                timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
        if not (base_url and api_key):
            raise ProviderError(
                f"Thiếu base_url/api_key cho provider '{name}' - chưa thể dùng.",
                transient=False, code="provider_not_configured")
        self.name = name
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        headers.update(extra_headers or {})
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_seconds)
        self._caps = capabilities or ProviderCapabilities(
            streaming=True, tools=True, web_search=False, vision=False, max_context_tokens=32000)
        self._counters = _Counters()
        self._completions_path = "/chat/completions"

    def capabilities(self) -> ProviderCapabilities:
        return self._caps

    def usage(self) -> ProviderUsageSnapshot:
        return self._counters.snapshot()

    def _payload(self, req: GenerateRequest, *, stream: bool) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": req.model,
            "messages": [_turn_to_openai_message(t) for t in req.messages],
            "max_tokens": req.max_output_tokens,
            "temperature": req.temperature,
            "stream": stream,
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        if req.user_ref:
            payload["user"] = req.user_ref
        if req.tools:
            payload["tools"] = [
                {"type": "function", "function": {
                    "name": t.name, "description": t.description, "parameters": t.parameters}}
                for t in req.tools]
        return payload

    def generate(self, req: GenerateRequest) -> GenerateResult:
        # R1 (review finding, docs/ai/AI_ASSISTANT_V1.md "Implementation
        # notes"): NOTHING but `ProviderError` may escape this method — an
        # unhandled httpx/ValueError/etc reaching the gateway would bypass
        # its circuit-breaker/fallback bookkeeping AND could leak raw
        # exception internals to an HTTP client. The outer try/except below
        # is a catch-all safety net on TOP of the specific handlers already
        # inside it (which give better error codes/messages when possible).
        try:
            return self._generate_inner(req)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 — intentional catch-all, see above
            self._counters.errors += 1
            raise ProviderError(
                f"'{self.name}' gặp lỗi không mong đợi.", transient=False,
                code="provider_unexpected_error") from exc

    def _generate_inner(self, req: GenerateRequest) -> GenerateResult:
        self._counters.requests += 1
        try:
            resp = self._client.post(
                self._completions_path, json=self._payload(req, stream=False),
                timeout=req.timeout_s)
        except httpx.HTTPError as exc:
            self._counters.errors += 1
            raise ProviderError(
                f"Không gọi được '{self.name}': {exc}", transient=True,
                code="provider_network_error") from exc
        if resp.status_code != 200:
            self._counters.errors += 1
            raise ProviderError(
                f"'{self.name}' trả lỗi {resp.status_code}.",
                transient=resp.status_code >= 500 or resp.status_code == 429,
                code=f"provider_http_{resp.status_code}")
        try:
            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"].get("content") or ""
            finish_reason = choice.get("finish_reason") or "stop"
            usage = data.get("usage") or {}
        except (KeyError, IndexError, ValueError) as exc:
            self._counters.errors += 1
            raise ProviderError(
                f"Phản hồi '{self.name}' không đúng định dạng mong đợi.",
                transient=False, code="provider_bad_response") from exc
        text = (content or "").strip()
        if not text:
            self._counters.errors += 1
            raise ProviderError(
                f"'{self.name}' trả về nội dung rỗng.", transient=True, code="provider_empty")
        in_tok = int(usage.get("prompt_tokens", 0) or 0)
        out_tok = int(usage.get("completion_tokens", 0) or 0)
        self._counters.input_tokens += in_tok
        self._counters.output_tokens += out_tok
        return GenerateResult(
            text=text, provider_name=self.name, model=req.model,
            input_tokens=in_tok, output_tokens=out_tok, finish_reason=finish_reason)

    def stream(self, req: GenerateRequest) -> Iterator[StreamEvent]:
        # Same catch-all discipline as `generate()` above (R1) — a
        # generator's `except Exception` around its whole body still works
        # normally across `yield` suspension points (it is one function
        # frame), so this also converts an unexpected failure raised while
        # resuming after a `yield` (mid-stream) into a `ProviderError`,
        # never a raw exception reaching the gateway/route layer.
        got_any_delta = False
        try:
            for ev in self._stream_inner(req):
                if isinstance(ev, Delta):
                    got_any_delta = True
                yield ev
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 — intentional catch-all, see above
            self._counters.errors += 1
            raise ProviderError(
                f"'{self.name}' gặp lỗi không mong đợi.", transient=not got_any_delta,
                code="provider_unexpected_error") from exc

    def _stream_inner(self, req: GenerateRequest) -> Iterator[StreamEvent]:
        self._counters.requests += 1
        try:
            with self._client.stream(
                    "POST", self._completions_path, json=self._payload(req, stream=True),
                    timeout=req.timeout_s) as resp:
                if resp.status_code != 200:
                    self._counters.errors += 1
                    raise ProviderError(
                        f"'{self.name}' trả lỗi {resp.status_code}.",
                        transient=resp.status_code >= 500 or resp.status_code == 429,
                        code=f"provider_http_{resp.status_code}")
                finish_reason = "stop"
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    raw = line[len("data:"):].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                    except ValueError:
                        continue
                    usage = chunk.get("usage")
                    if usage:
                        in_tok = int(usage.get("prompt_tokens", 0) or 0)
                        out_tok = int(usage.get("completion_tokens", 0) or 0)
                        self._counters.input_tokens += in_tok
                        self._counters.output_tokens += out_tok
                        yield UsageEvent(input_tokens=in_tok, output_tokens=out_tok)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    text = delta.get("content")
                    if text:
                        yield Delta(text=text)
                    fr = choice.get("finish_reason")
                    if fr:
                        finish_reason = fr
                yield Done(finish_reason=finish_reason)
        except httpx.HTTPError as exc:
            self._counters.errors += 1
            # Raised BEFORE any Delta ever left this generator (an exception
            # inside a generator, before its first successful `yield`, always
            # propagates to the FIRST `next()` call the caller makes) — the
            # caller (`server/ai_assistant/gateway.py`) relies on exactly
            # this to decide "fall back" vs "already streamed, must not
            # silently switch providers mid-answer".
            raise ProviderError(
                f"Không gọi được '{self.name}': {exc}", transient=True,
                code="provider_network_error") from exc


class QwenDashScopeProvider(OpenAICompatChatProvider):
    """Alibaba DashScope, OpenAI-compatible mode (international endpoint).
    Tool calling: supported, per DashScope's own compatible-mode docs."""

    DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    def __init__(self, *, api_key: str, base_url: str = "", model: str = "qwen-plus",
                client: Optional[httpx.Client] = None,
                timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
        super().__init__(
            name="qwen", base_url=base_url or self.DEFAULT_BASE_URL, api_key=api_key,
            capabilities=ProviderCapabilities(
                streaming=True, tools=True, web_search=False, vision=False,
                max_context_tokens=32000),
            client=client, timeout_seconds=timeout_seconds)
        self._default_model = model


class AzureOpenAIProvider(OpenAICompatChatProvider):
    """Azure OpenAI: `api-key` header (NOT `Authorization: Bearer`), and a
    deployment-scoped URL with an explicit `api-version` query parameter —
    both genuinely distinct from vanilla OpenAI-compatible, hence
    overriding the request path/headers here rather than reusing the base
    class's `_completions_path` untouched."""

    def __init__(self, *, endpoint: str, api_key: str, deployment: str,
                api_version: str = "2024-06-01",
                client: Optional[httpx.Client] = None,
                timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
        if not (endpoint and api_key and deployment):
            raise ProviderError(
                "Thiếu endpoint/api_key/deployment cho Azure OpenAI - chưa thể dùng.",
                transient=False, code="provider_not_configured")
        base = endpoint.rstrip("/")
        super().__init__(
            name="azure_openai", base_url=base, api_key=api_key,
            extra_headers={"api-key": api_key, "Content-Type": "application/json"},
            capabilities=ProviderCapabilities(
                streaming=True, tools=True, web_search=False, vision=False,
                max_context_tokens=32000),
            client=client, timeout_seconds=timeout_seconds)
        # Azure's `Authorization: Bearer <api_key>` header is meaningless to
        # it (it reads `api-key` instead) but harmless to also send; kept
        # simple by not stripping it from the base class's default headers.
        self._completions_path = (
            f"/openai/deployments/{deployment}/chat/completions"
            f"?api-version={api_version}")


class TencentCompatProvider(OpenAICompatChatProvider):
    """Tencent Hunyuan's OpenAI-compatible endpoint shape — SKELETON ONLY.
    Built against the publicly documented wire format; explicitly NOT
    exercised against a real Tencent endpoint (no key available in this
    environment). Treat as untested until proven otherwise against a live
    account."""

    UNTESTED = True

    def __init__(self, *, api_key: str, base_url: str, model: str = "hunyuan-turbo",
                client: Optional[httpx.Client] = None,
                timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
        super().__init__(
            name="tencent", base_url=base_url, api_key=api_key,
            capabilities=ProviderCapabilities(
                streaming=True, tools=False, web_search=False, vision=False,
                max_context_tokens=16000),
            client=client, timeout_seconds=timeout_seconds)
        self._default_model = model


class MockChatProvider(ChatProvider):
    """Deterministic, no network — word-by-word stream. Used for dev without
    any provider key configured, and for every test that doesn't
    specifically exercise a real adapter's HTTP shape."""

    name = "mock"

    def __init__(self, *, delay_s: float = 0.0):
        self._delay_s = delay_s
        self._counters = _Counters()

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            streaming=True, tools=False, web_search=False, vision=False,
            max_context_tokens=8000)

    def usage(self) -> ProviderUsageSnapshot:
        return self._counters.snapshot()

    def _reply_text(self, req: GenerateRequest) -> str:
        last_user = next((t.content for t in reversed(req.messages) if t.role == "user"), "")
        if not last_user.strip():
            raise ProviderError(
                "Tin nhắn người dùng rỗng, không có gì để trả lời.",
                transient=False, code="provider_empty_input")
        return f"[MOCK] Đã nhận câu hỏi ({len(last_user)} ký tự). Đây là câu trả lời mô phỏng."

    def generate(self, req: GenerateRequest) -> GenerateResult:
        self._counters.requests += 1
        text = self._reply_text(req)
        self._counters.output_tokens += len(text.split())
        return GenerateResult(text=text, provider_name=self.name, model=req.model or "mock-model",
                              output_tokens=len(text.split()))

    def stream(self, req: GenerateRequest) -> Iterator[StreamEvent]:
        self._counters.requests += 1
        text = self._reply_text(req)
        words = text.split(" ")
        out_tok = 0
        for i, word in enumerate(words):
            piece = word if i == 0 else " " + word
            yield Delta(text=piece)
            out_tok += 1
            if self._delay_s:
                time.sleep(self._delay_s)
        self._counters.output_tokens += out_tok
        yield UsageEvent(input_tokens=0, output_tokens=out_tok)
        yield Done(finish_reason="stop")


class LegacyCompletionAdapter(LLMProvider):
    """Bridges a `ChatProvider` back into the OLD `LLMProvider.complete`
    shape (`server/llm_gateway/provider.py`) — lets the reader AI
    (`/api/chat/ask`) reuse a V1-Assistant provider LATER without any
    change to its own code. NOT wired into `/api/chat/ask` in this
    mission — see `docs/ai/AI_ASSISTANT_V1.md`'s "Implementation notes"."""

    def __init__(self, provider: ChatProvider):
        self._provider = provider
        self.name = provider.name

    def complete(self, *, system: str, user: str, model: str,
                max_output_tokens: int) -> LLMCompletion:
        req = GenerateRequest(
            messages=[ChatTurn(role="system", content=system), ChatTurn(role="user", content=user)],
            model=model, max_output_tokens=max_output_tokens)
        try:
            result = self._provider.generate(req)
        except ProviderError as exc:
            raise LLMProviderError(str(exc)) from exc
        return LLMCompletion(
            text=result.text, provider_name=result.provider_name, model=result.model,
            input_tokens=result.input_tokens, output_tokens=result.output_tokens)
