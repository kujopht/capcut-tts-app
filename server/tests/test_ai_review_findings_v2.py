"""
Regression tests for the second independent review of the Fanfic AI
Assistant V1 backend (B1/B2/H3-H6/M7-M11/L12 — see the review packet and
`docs/ai/AI_ASSISTANT_V1.md` "Implementation notes" for each finding's full
text). One test class per finding id; each test FAILED against the code as
reviewed and passes after the paired fix.
"""
from __future__ import annotations

import json
import re
import socket
import threading
import time
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional
from unittest import mock

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from server.ai_assistant.ephemeral import EphemeralConversationStore
from server.ai_assistant.gateway import AiGateway
from server.ai_assistant.limits import StreamGuard
from server.ai_assistant.memory import (
    AiConversation, AiMessage, AiPreferences, AiProject, AppwriteAiRepo, InMemoryAiRepo,
)
from server.ai_assistant.routes import _hashed_user_ref, _tier_of, build_ai_router
from server.ai_assistant.runtime import AiRuntime
from server.ai_assistant.tools import ToolContext
from server.config import AppwriteSettings
from server.domain import Tier
from server.llm_gateway.chat_provider import (
    ChatProvider, ChatTurn, Delta, Done, GenerateRequest, GenerateResult, ProviderCapabilities,
    ProviderUsageSnapshot, StreamEvent,
)
from server.llm_gateway.chat_providers import MockChatProvider, OpenAICompatChatProvider

from server.tests.test_ai_routes import _auth, _enabled_runtime, _make_app, _resolve_profile


# --------------------------------------------------------------- fake Appwrite


def _parse_queries(request: httpx.Request) -> List[Dict[str, Any]]:
    raw = request.url.params.get_list("queries[]")
    return [json.loads(q) for q in raw]


class FakeAppwriteTransport:
    """A tiny, in-memory stand-in for the Legacy Appwrite documents API —
    enough of `equal`/`orderAsc`/`orderDesc`/`limit`/`cursorAfter` to
    exercise `AppwriteAiRepo`'s REAL query-building code (`_q`/`_list`/...)
    end-to-end, not just the python-side slicing in isolation."""

    def __init__(self) -> None:
        self.collections: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.order: Dict[str, List[str]] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        m = re.search(r"/collections/([^/]+)/documents(?:/([^/?]+))?$", request.url.path)
        if not m:
            return httpx.Response(404, json={"message": "route not found"})
        coll, doc_id = m.group(1), m.group(2)
        store = self.collections.setdefault(coll, {})
        order = self.order.setdefault(coll, [])

        if request.method == "POST":
            body = json.loads(request.content)
            did = body["documentId"]
            if did in store:
                return httpx.Response(409, json={"message": "exists"})
            data = dict(body["data"])
            data["$id"] = did
            store[did] = data
            order.append(did)
            return httpx.Response(201, json=data)

        if request.method == "GET" and doc_id:
            if doc_id not in store:
                return httpx.Response(404, json={"message": "not found"})
            return httpx.Response(200, json=store[doc_id])

        if request.method == "GET":
            docs = [store[d] for d in order if d in store]
            limit = None
            for q in _parse_queries(request):
                method = q["method"]
                if method == "equal":
                    attr = q["attribute"]
                    vals = q["values"]
                    docs = [d for d in docs if d.get(attr) in vals]
                elif method == "orderAsc":
                    attr = q["attribute"]
                    docs = sorted(docs, key=lambda d, a=attr: d.get(a))
                elif method == "orderDesc":
                    attr = q["attribute"]
                    docs = sorted(docs, key=lambda d, a=attr: d.get(a), reverse=True)
                elif method == "limit":
                    limit = q["values"][0]
                elif method == "cursorAfter":
                    cursor = q["values"][0]
                    ids = [d["$id"] for d in docs]
                    if cursor in ids:
                        docs = docs[ids.index(cursor) + 1:]
            total = len(docs)
            if limit is not None:
                docs = docs[:limit]
            return httpx.Response(200, json={"documents": docs, "total": total})

        if request.method == "PATCH":
            if doc_id not in store:
                return httpx.Response(404, json={"message": "not found"})
            body = json.loads(request.content)
            store[doc_id].update(body["data"])
            return httpx.Response(200, json=store[doc_id])

        if request.method == "DELETE":
            store.pop(doc_id, None)
            if doc_id in order:
                order.remove(doc_id)
            return httpx.Response(204)

        return httpx.Response(400, json={"message": "unsupported"})


@dataclass
class _FakeSettings:
    appwrite: AppwriteSettings


def _fake_appwrite_repo(transport: FakeAppwriteTransport) -> AppwriteAiRepo:
    client = httpx.Client(transport=httpx.MockTransport(transport))
    aw = AppwriteSettings(endpoint="https://appwrite.example/v1", project_id="proj",
                         api_key="key", database_id="db")
    return AppwriteAiRepo(_FakeSettings(appwrite=aw), client=client)


# =============================================================================== B1


class TestB1TierOfRealEnum(unittest.TestCase):
    """`_tier_of` must read `server.domain.Tier`'s VALUE, not Python's
    `str(EnumMember)` repr ("Tier.FREE" on this interpreter) — the bug made
    every FREE-tier user classified as "premium" (wrong, higher budget)."""

    @dataclass(frozen=True)
    class _RealProfile:
        user_id: str
        tier: Tier

    def test_free_enum_member_maps_to_free_bucket(self) -> None:
        self.assertEqual(_tier_of(self._RealProfile("u1", Tier.FREE)), "free")

    def test_paid_enum_members_map_to_premium_bucket(self) -> None:
        for tier in (Tier.LISTENER_PRO, Tier.CREATOR_PRO, Tier.ULTRA):
            self.assertEqual(_tier_of(self._RealProfile("u1", tier)), "premium")

    def test_availability_route_reports_free_daily_limit_for_free_tier(self) -> None:
        rt = _enabled_runtime()
        rt.daily_tokens_free = 111
        rt.daily_tokens_premium = 999999

        def resolve(_auth_header: Optional[str]):
            return self._RealProfile("free_user", Tier.FREE)

        app = FastAPI()
        app.include_router(build_ai_router(rt, resolve_profile=resolve))
        client = TestClient(app)
        r = client.get("/api/ai/availability", headers=_auth("x"))
        self.assertEqual(r.json()["limits"]["limit_today"], 111)


# =============================================================================== B2


class TestB2DisconnectStillRecordsUsageAndPersists(unittest.TestCase):
    """A client that disconnects mid-stream must not make usage/billing and
    the partial assistant reply disappear — Starlette's `StreamingResponse`
    cancels the generator via an `anyio` task-group race, which (without a
    shielded `finally`) silently skipped `record_usage`/`create_message`."""

    @classmethod
    def setUpClass(cls) -> None:
        import uvicorn

        cls.rt = _enabled_runtime()
        # A small per-word delay keeps the socket open long enough for the
        # test to observe >=1 delta before it aborts the connection.
        cls.rt.gateway = AiGateway(
            providers={"mock": MockChatProvider(delay_s=0.05)}, provider_chain=["mock"])
        app = _make_app(cls.rt)
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="critical")
        cls.server = uvicorn.Server(config)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        for _ in range(200):
            if getattr(cls.server, "started", False):
                break
            time.sleep(0.02)
        cls.port = cls.server.servers[0].sockets[0].getsockname()[1]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.should_exit = True
        cls.thread.join(timeout=5)

    def test_disconnect_mid_stream_records_usage_and_persists_stopped_message(self) -> None:
        base = f"http://127.0.0.1:{self.port}"
        with httpx.Client(timeout=10.0) as client:
            created = client.post(f"{base}/api/ai/conversations", headers=_auth("bob"),
                                  json={"mode": "general"})
            self.assertEqual(created.status_code, 200)
            cid = created.json()["conversation_id"]

        body = json.dumps({
            "content": "xin chao ban day la mot cau hoi dai de co nhieu tu",
            "client_id": "c-disc"}).encode()
        request_bytes = (
            f"POST /api/ai/conversations/{cid}/messages HTTP/1.1\r\n"
            f"Host: x\r\nAuthorization: Bearer bob\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n\r\n").encode() + body

        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        sock.sendall(request_bytes)
        got = b""
        deadline = time.time() + 5
        while b"event: delta" not in got and time.time() < deadline:
            chunk = sock.recv(4096)
            if not chunk:
                break
            got += chunk
        self.assertIn(b"event: delta", got, "expected at least one delta before aborting")
        sock.close()  # abrupt client disconnect — mid-stream, after >=1 delta

        assistant_msg = None
        deadline = time.time() + 5
        while time.time() < deadline:
            candidates = [m for m in self.rt.repo._messages.values()  # noqa: SLF001 — test-only
                         if m.conversation_id == cid and m.role == "assistant"]
            if candidates:
                assistant_msg = candidates[0]
                break
            time.sleep(0.1)

        self.assertIsNotNone(
            assistant_msg, "assistant message was never persisted after a mid-stream disconnect")
        self.assertEqual(assistant_msg.status, "stopped")
        self.assertTrue(assistant_msg.content, "partial text must still be persisted")

        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        usage = self.rt.repo.get_usage_day("user_bob", today)
        self.assertIsNotNone(usage, "usage must still be recorded after a mid-stream disconnect")
        self.assertGreater(usage.input_tokens + usage.output_tokens, 0)


# =============================================================================== H3


class _RecordingRpmLimiter:
    """Stands in for `RpmLimiter` — `.check()` is called directly on
    `post_message`'s own coroutine body (never offloaded, by design: it's
    an in-memory, no-I/O check), so recording which thread runs it gives a
    reliable fingerprint of "the asyncio loop thread this request is
    running on", independent of wall-clock timing (real elapsed-time
    measurements proved unreliable in this dev environment's own
    uvicorn+ProactorEventLoop combination — a `run_in_threadpool` call was
    empirically confirmed, via thread-name logging, to run promptly and
    concurrently even though end-to-end response latency still varied by
    machine)."""

    def __init__(self) -> None:
        self.threads: List[threading.Thread] = []

    def check(self, user_id: str, *, rpm: int) -> None:
        self.threads.append(threading.current_thread())


class TestH3ProfileAndOwnershipOffLoop(unittest.TestCase):
    """`resolve_profile`/`_own_conversation` can each make a real Appwrite
    HTTP call — `post_message` is the only `async def` route in this router
    (every `def` route is already offloaded to a threadpool by Starlette
    itself), so calling them directly blocks whatever thread is running
    THIS request's asyncio event loop. Fingerprint: `resolve_profile`'s own
    thread must differ from the thread that runs the very next, definitely
    on-loop, synchronous call (`rt.rpm_limiter.check`, right after it in
    `post_message`)."""

    def test_resolve_profile_and_ownership_check_run_off_the_calling_thread(self) -> None:
        resolve_threads: List[threading.Thread] = []

        def recording_resolve(authorization: Optional[str]):
            resolve_threads.append(threading.current_thread())
            return _resolve_profile(authorization)

        rt = _enabled_runtime()
        rpm_limiter = _RecordingRpmLimiter()
        rt.rpm_limiter = rpm_limiter  # type: ignore[assignment]

        app = FastAPI()
        app.include_router(build_ai_router(rt, resolve_profile=recording_resolve))
        client = TestClient(app)
        created = client.post("/api/ai/conversations", headers=_auth("alice"), json={"mode": "general"})
        cid = created.json()["conversation_id"]
        resolve_threads.clear()

        with client.stream(
                "POST", f"/api/ai/conversations/{cid}/messages", headers=_auth("alice"),
                json={"content": "hi", "client_id": "c1"}) as resp:
            list(resp.iter_text())

        self.assertTrue(resolve_threads, "resolve_profile was never called during post_message")
        self.assertTrue(rpm_limiter.threads, "rpm_limiter.check was never called during post_message")
        self.assertNotEqual(
            resolve_threads[0], rpm_limiter.threads[0],
            "resolve_profile() ran on the SAME thread as an always-on-loop call "
            "(rt.rpm_limiter.check) — it was not actually offloaded via run_in_threadpool")


# =============================================================================== H4


class TestH4ListMessagesReturnsNewestNotOldest(unittest.TestCase):
    """`orderAsc` + `limit` returned the OLDEST N messages of a conversation
    — for any conversation with more messages than `limit`, every caller
    (context building, the conversation-detail route) got the very START
    of the conversation instead of its most recent turns."""

    def test_list_messages_with_limit_returns_newest_in_chronological_order(self) -> None:
        transport = FakeAppwriteTransport()
        repo = _fake_appwrite_repo(transport)
        repo.create_conversation(AiConversation(conversation_id="c1", user_id="u1", mode="general"))
        for i in range(10):
            repo.create_message(AiMessage(
                message_id=f"m{i}", conversation_id="c1", user_id="u1", role="user",
                content=f"msg {i}", created_at=f"2026-01-01T00:00:{i:02d}"))

        got = repo.list_messages("c1", limit=3)

        self.assertEqual([m.message_id for m in got], ["m7", "m8", "m9"],
                         "expected the NEWEST 3 messages, in chronological order")


# =============================================================================== H5


class TestH5BoundedFieldsAndUnavailableMapping(unittest.TestCase):
    def test_repo_unavailable_maps_to_503_not_500(self) -> None:
        """A 500-class Appwrite response is `AiUnavailable` at the repo
        layer — every route now routes its `rt.repo.*` calls through
        `_run()`, which previously did not catch it at all (falling
        through to FastAPI's opaque default 500 handler)."""
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Appwrite unreachable")

        client_ = httpx.Client(transport=httpx.MockTransport(handler))
        aw = AppwriteSettings(endpoint="https://appwrite.example/v1", project_id="proj",
                             api_key="key", database_id="db")
        transport_repo = AppwriteAiRepo(_FakeSettings(appwrite=aw), client=client_)

        rt = _enabled_runtime()
        rt.repo = transport_repo
        app = FastAPI()
        app.include_router(build_ai_router(rt, resolve_profile=_resolve_profile))
        client = TestClient(app)

        r = client.get("/api/ai/preferences", headers=_auth("alice"))
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "ai_storage_unavailable")

    def test_oversized_context_ids_are_truncated_not_a_500(self) -> None:
        """`ai_messages`/`ai_conversations`' `context_*_id` attributes are
        `size=64` — a client-supplied id longer than that used to reach
        Appwrite verbatim, which would 400 -> (before H5) an uncaught
        `AiUnavailable` -> 500."""
        rt = _enabled_runtime()
        app = FastAPI()
        app.include_router(build_ai_router(rt, resolve_profile=_resolve_profile))
        client = TestClient(app)
        huge_id = "n" * 500
        r = client.post("/api/ai/conversations", headers=_auth("alice"),
                        json={"mode": "story", "context": {"novel_id": huge_id}})
        self.assertEqual(r.status_code, 200)
        cid = r.json()["conversation_id"]
        conv = rt.repo.get_conversation(cid)
        self.assertLessEqual(len(conv.context_novel_id), 64)


# =============================================================================== H6


class TestH6PaginatedDeleteAll(unittest.TestCase):
    def test_delete_conversation_removes_more_than_one_page_of_messages(self) -> None:
        transport = FakeAppwriteTransport()
        repo = _fake_appwrite_repo(transport)
        repo.create_conversation(AiConversation(conversation_id="c1", user_id="u1", mode="general"))
        for i in range(130):
            repo.create_message(AiMessage(
                message_id=f"m{i}", conversation_id="c1", user_id="u1", role="user",
                content=f"msg {i}", created_at=f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}"))

        repo.delete_conversation("c1")

        remaining = transport.collections.get("ai_messages", {})
        self.assertEqual(len(remaining), 0, "messages beyond the first page were never deleted")

    def test_delete_all_memory_removes_more_than_one_page_of_conversations(self) -> None:
        transport = FakeAppwriteTransport()
        repo = _fake_appwrite_repo(transport)
        for i in range(130):
            repo.create_conversation(AiConversation(
                conversation_id=f"c{i}", user_id="u1", mode="general"))

        repo.delete_all_memory("u1")

        remaining = transport.collections.get("ai_conversations", {})
        self.assertEqual(len(remaining), 0, "conversations beyond the first page were never deleted")


# =============================================================================== M7


class _RecordingProvider(ChatProvider):
    """Captures the exact `GenerateRequest` the gateway handed it — lets a
    test assert on what a REAL provider adapter would have sent out over
    the wire, without any network."""

    name = "rec"

    def __init__(self) -> None:
        self.received: Optional[GenerateRequest] = None

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(streaming=True, tools=False, web_search=False, vision=False,
                                    max_context_tokens=8000)

    def usage(self) -> ProviderUsageSnapshot:
        return ProviderUsageSnapshot()

    def generate(self, req: GenerateRequest) -> GenerateResult:
        raise NotImplementedError

    def stream(self, req: GenerateRequest) -> Iterator[StreamEvent]:
        self.received = req
        yield Delta(text="ok")
        yield Done()


class TestM7RedactBeforeProvider(unittest.TestCase):
    def test_secret_shaped_content_never_reaches_provider_or_storage(self) -> None:
        rt = _enabled_runtime()
        provider = _RecordingProvider()
        rt.gateway = AiGateway(providers={"rec": provider}, provider_chain=["rec"])
        app = FastAPI()
        app.include_router(build_ai_router(rt, resolve_profile=_resolve_profile))
        client = TestClient(app)
        created = client.post("/api/ai/conversations", headers=_auth("alice"), json={"mode": "general"})
        cid = created.json()["conversation_id"]

        # Ghep luc chay (quy uoc .gitleaks.toml) — nguon khong chua chuoi lien tuc giong khoa that.
        secret = "sk-" + "abcdefgh" * 3
        with client.stream(
                "POST", f"/api/ai/conversations/{cid}/messages", headers=_auth("alice"),
                json={"content": f"khoá của tôi là Bearer {secret} giúp tôi với",
                     "client_id": "c1"}) as resp:
            list(resp.iter_text())

        self.assertIsNotNone(provider.received)
        joined = "\n".join(t.content for t in provider.received.messages)
        self.assertNotIn(secret, joined, "raw secret reached the provider")

        got = client.get(f"/api/ai/conversations/{cid}", headers=_auth("alice"))
        contents = [m["content"] for m in got.json()["messages"]]
        self.assertTrue(all(secret not in c for c in contents), "raw secret was persisted")


# =============================================================================== M8


class TestM8HashedUserRef(unittest.TestCase):
    def test_user_ref_sent_to_provider_is_hmac_not_raw_user_id(self) -> None:
        rt = _enabled_runtime()
        provider = _RecordingProvider()
        rt.gateway = AiGateway(providers={"rec": provider}, provider_chain=["rec"])
        app = FastAPI()
        app.include_router(build_ai_router(rt, resolve_profile=_resolve_profile))
        client = TestClient(app)
        created = client.post("/api/ai/conversations", headers=_auth("alice"), json={"mode": "general"})
        cid = created.json()["conversation_id"]

        with client.stream(
                "POST", f"/api/ai/conversations/{cid}/messages", headers=_auth("alice"),
                json={"content": "hi", "client_id": "c1"}) as resp:
            list(resp.iter_text())

        self.assertIsNotNone(provider.received)
        self.assertNotEqual(provider.received.user_ref, "user_alice")
        self.assertEqual(provider.received.user_ref, _hashed_user_ref(rt, "user_alice"))


# =============================================================================== M9


class TestM9FixedErrorMessageNoLeakage(unittest.TestCase):
    def test_mid_stream_httpx_readerror_yields_a_fixed_generic_message(self) -> None:
        class _FlakyStream:
            def __iter__(self):
                yield b'data: {"choices":[{"delta":{"content":"Xin"}}]}\n\n'
                raise httpx.ReadError("connection reset by peer, upstream=10.0.0.7:443")

            def close(self) -> None:
                pass

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, stream=_FlakyStream())

        provider = OpenAICompatChatProvider(name="qwen_test", base_url="https://x.invalid", api_key="k")
        provider._client._transport = httpx.MockTransport(handler)  # noqa: SLF001 — test wiring

        rt = _enabled_runtime()
        rt.gateway = AiGateway(providers={"qwen_test": provider}, provider_chain=["qwen_test"])
        app = FastAPI()
        app.include_router(build_ai_router(rt, resolve_profile=_resolve_profile))
        client = TestClient(app)
        created = client.post("/api/ai/conversations", headers=_auth("alice"), json={"mode": "general"})
        cid = created.json()["conversation_id"]

        with client.stream(
                "POST", f"/api/ai/conversations/{cid}/messages", headers=_auth("alice"),
                json={"content": "hi", "client_id": "c1"}) as resp:
            body = "".join(resp.iter_text())

        self.assertIn("event: error", body)
        error_block = [b for b in body.split("\n\n") if b.startswith("event: error")][0]
        data_line = [l for l in error_block.splitlines() if l.startswith("data:")][0]
        payload = json.loads(data_line[len("data:"):].strip())
        self.assertNotIn("qwen_test", payload["message"])
        self.assertNotIn("connection reset", payload["message"])
        self.assertNotIn("10.0.0.7", payload["message"])


# =============================================================================== M10


class TestM10UntrustedPreambleAndReadPermission(unittest.TestCase):
    def test_retrieval_skipped_when_read_permission_denied(self) -> None:
        from server.chat.embedding_provider import EmbeddingProvider
        from server.chat.vector_store import VectorStore
        from server.ai_assistant.tools import retrieve_story_chunks

        class _DenyingCtx:
            pass

        ctx = ToolContext(
            vector_store=mock.Mock(spec=VectorStore), embedding_provider=mock.Mock(spec=EmbeddingProvider),
            may_read_novel_fn=lambda novel_id, user_id: False)
        ctx.embedding_provider.embed.return_value = [[0.1, 0.2]]

        results = retrieve_story_chunks(
            ctx, "what happened?", novel_id="other_users_draft", current_chapter_index=5,
            user_id="intruder")

        self.assertEqual(results, [])
        ctx.vector_store.query.assert_not_called()

    def test_retrieval_block_carries_untrusted_data_preamble(self) -> None:
        from server.ai_assistant.tools import UNTRUSTED_DATA_PREAMBLE

        rt = _enabled_runtime()
        rt.tool_ctx = ToolContext(search_library_fn=lambda q, n: [
            __import__("server.ai_assistant.tools", fromlist=["LibraryHit"]).LibraryHit(
                novel_id="n1", title="Some Title", author="Some Author")])
        provider = _RecordingProvider()
        rt.gateway = AiGateway(providers={"rec": provider}, provider_chain=["rec"])
        app = FastAPI()
        app.include_router(build_ai_router(rt, resolve_profile=_resolve_profile))
        client = TestClient(app)
        created = client.post("/api/ai/conversations", headers=_auth("alice"), json={"mode": "general"})
        cid = created.json()["conversation_id"]

        with client.stream(
                "POST", f"/api/ai/conversations/{cid}/messages", headers=_auth("alice"),
                json={"content": "tìm giúp tôi", "client_id": "c1", "use_library": True}) as resp:
            list(resp.iter_text())

        joined = "\n".join(t.content for t in provider.received.messages)
        self.assertIn(UNTRUSTED_DATA_PREAMBLE, joined)


# =============================================================================== M11


class TestM11EphemeralCapAndRpm(unittest.TestCase):
    def test_ephemeral_conversations_count_toward_the_per_user_cap(self) -> None:
        rt = _enabled_runtime()
        app = FastAPI()
        app.include_router(build_ai_router(rt, resolve_profile=_resolve_profile))
        client = TestClient(app)
        client.put("/api/ai/preferences", headers=_auth("alice"),
                   json={"memory_enabled": False, "preferences": {}})

        with mock.patch("server.ai_assistant.routes.MAX_CONVERSATIONS_PER_USER", 2):
            r1 = client.post("/api/ai/conversations", headers=_auth("alice"), json={"mode": "general"})
            r2 = client.post("/api/ai/conversations", headers=_auth("alice"), json={"mode": "general"})
            r3 = client.post("/api/ai/conversations", headers=_auth("alice"), json={"mode": "general"})

        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r3.status_code, 400)
        self.assertEqual(r3.json()["detail"]["code"], "ai_context_too_large")

    def test_create_conversation_is_rate_limited(self) -> None:
        rt = _enabled_runtime()
        rt.rpm = 1
        app = FastAPI()
        app.include_router(build_ai_router(rt, resolve_profile=_resolve_profile))
        client = TestClient(app)

        r1 = client.post("/api/ai/conversations", headers=_auth("alice"), json={"mode": "general"})
        r2 = client.post("/api/ai/conversations", headers=_auth("alice"), json={"mode": "general"})

        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 429)
        self.assertEqual(r2.json()["detail"]["code"], "ai_rate_limited")

    def test_ephemeral_eviction_prefers_the_flooding_users_own_entries(self) -> None:
        store = EphemeralConversationStore(max_conversations=2)
        store.create_conversation(AiConversation(conversation_id="a1", user_id="userA", mode="general"))
        store.create_conversation(AiConversation(conversation_id="a2", user_id="userA", mode="general"))
        # userB's first conversation pushes the GLOBAL store over capacity —
        # it must evict userA's OLDEST ("a1"), never userB's own brand-new
        # entry, and never leave userB with zero conversations.
        store.create_conversation(AiConversation(conversation_id="b1", user_id="userB", mode="general"))

        self.assertIsNone(store.get_conversation("a1"), "userA's oldest should have been evicted")
        self.assertIsNotNone(store.get_conversation("a2"))
        self.assertIsNotNone(store.get_conversation("b1"), "userB's own new conversation was evicted")


if __name__ == "__main__":
    unittest.main()
