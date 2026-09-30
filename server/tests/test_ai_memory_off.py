"""
Tests for `memory_enabled=false` — Fanfic AI Assistant V1 §5. Proves the
privacy guarantee is REAL, not just documented: zero durable writes while
memory is off, no saved preferences/summary injected into context, the
in-process cache actually expires, and turning memory back on resumes
durable persistence for new messages.
"""
from __future__ import annotations

import time
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.ai_assistant.context_builder import build_context
from server.ai_assistant.ephemeral import EphemeralConversationStore
from server.ai_assistant.gateway import AiGateway
from server.ai_assistant.limits import StreamGuard
from server.ai_assistant.memory import (
    AiConversation, AiMessage, AiPreferences, AiSummary, InMemoryAiRepo,
)
from server.ai_assistant.routes import build_ai_router
from server.ai_assistant.runtime import AiRuntime
from server.ai_assistant.tools import ToolContext
from server.llm_gateway.chat_providers import MockChatProvider
from server.tests.test_ai_routes import _auth, _resolve_profile


class _SpyRepo(InMemoryAiRepo):
    """Records every write so a test can assert ZERO durable writes
    happened, not just that the *response* looked right."""

    def __init__(self) -> None:
        super().__init__()
        self.conversation_writes = 0
        self.message_writes = 0

    def create_conversation(self, c: AiConversation) -> AiConversation:
        self.conversation_writes += 1
        return super().create_conversation(c)

    def create_message(self, m: AiMessage) -> AiMessage:
        self.message_writes += 1
        return super().create_message(m)


def _runtime(repo: InMemoryAiRepo) -> AiRuntime:
    gateway = AiGateway(providers={"mock": MockChatProvider()}, provider_chain=["mock"])
    return AiRuntime(True, repo=repo, gateway=gateway, tool_ctx=ToolContext(),
                     assistant_name="T", rpm=1000,
                     stream_guard=StreamGuard(max_streams_per_instance=4))


def _client(rt: AiRuntime) -> TestClient:
    app = FastAPI()
    app.include_router(build_ai_router(rt, resolve_profile=_resolve_profile))
    return TestClient(app)


class TestZeroDurableWritesWhenOff(unittest.TestCase):
    def test_conversation_and_messages_never_reach_the_repo(self) -> None:
        repo = _SpyRepo()
        rt = _runtime(repo)
        client = _client(rt)

        client.put("/api/ai/preferences", headers=_auth("alice"),
                   json={"memory_enabled": False, "preferences": {}})
        created = client.post("/api/ai/conversations", headers=_auth("alice"),
                              json={"mode": "general"})
        self.assertTrue(created.json()["ephemeral"])
        cid = created.json()["conversation_id"]

        with client.stream("POST", f"/api/ai/conversations/{cid}/messages", headers=_auth("alice"),
                           json={"content": "câu hỏi bí mật", "client_id": "c1"}) as resp:
            list(resp.iter_text())

        # 1 write happened: `put_preferences` — NOT counted here. Zero
        # conversation/message writes reached the durable spy repo.
        self.assertEqual(repo.conversation_writes, 0)
        self.assertEqual(repo.message_writes, 0)
        # ...but the turn genuinely happened, in the ephemeral cache:
        cached = rt.ephemeral.list_messages(cid, limit=10)
        self.assertEqual(len(cached), 2)  # user + assistant
        self.assertEqual(cached[0].role, "user")
        self.assertEqual(cached[0].content, "câu hỏi bí mật")

    def test_get_and_list_flag_ephemeral_conversations(self) -> None:
        repo = _SpyRepo()
        rt = _runtime(repo)
        client = _client(rt)
        client.put("/api/ai/preferences", headers=_auth("alice"),
                   json={"memory_enabled": False, "preferences": {}})
        created = client.post("/api/ai/conversations", headers=_auth("alice"),
                              json={"mode": "general"})
        cid = created.json()["conversation_id"]

        got = client.get(f"/api/ai/conversations/{cid}", headers=_auth("alice"))
        self.assertTrue(got.json()["ephemeral"])

        listed = client.get("/api/ai/conversations", headers=_auth("alice"))
        items = listed.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["ephemeral"])
        self.assertEqual(repo.conversation_writes, 0)


class TestNoSummaryOrPreferencesInjectedWhenOff(unittest.TestCase):
    def test_saved_preferences_and_summary_are_excluded_when_memory_off(self) -> None:
        repo = InMemoryAiRepo()
        repo.put_preferences(AiPreferences(
            user_id="u1", memory_enabled=False, preferences_json='{"lang": "vi"}'))
        repo.put_summary(AiSummary(conversation_id="c1", user_id="u1", summary="TÓM TẮT BÍ MẬT"))

        turns_off = build_context(
            mode="general", assistant_name="T", repo=repo, user_id="u1", conversation_id="c1",
            memory_enabled=False, max_context_tokens=6000, pending_recent_messages=[])
        blob_off = " ".join(t.content for t in turns_off)
        self.assertNotIn("lang", blob_off)
        self.assertNotIn("TÓM TẮT BÍ MẬT", blob_off)

        turns_on = build_context(
            mode="general", assistant_name="T", repo=repo, user_id="u1", conversation_id="c1",
            memory_enabled=True, max_context_tokens=6000, pending_recent_messages=[])
        blob_on = " ".join(t.content for t in turns_on)
        self.assertIn("lang", blob_on)
        self.assertIn("TÓM TẮT BÍ MẬT", blob_on)

    def test_no_summary_is_ever_generated_or_persisted(self) -> None:
        """V1 has no summarization pipeline at all yet (see docs/ai/
        AI_ASSISTANT_V1.md "Implementation notes") — this locks in that a
        full conversation turn, memory on OR off, never calls
        `AiRepo.put_summary`."""
        class _SpySummaryRepo(InMemoryAiRepo):
            def __init__(self) -> None:
                super().__init__()
                self.summary_writes = 0

            def put_summary(self, s):
                self.summary_writes += 1
                return super().put_summary(s)

        repo = _SpySummaryRepo()
        rt = _runtime(repo)
        client = _client(rt)
        created = client.post("/api/ai/conversations", headers=_auth("alice"), json={"mode": "general"})
        cid = created.json()["conversation_id"]
        with client.stream("POST", f"/api/ai/conversations/{cid}/messages", headers=_auth("alice"),
                           json={"content": "hi", "client_id": "c1"}) as resp:
            list(resp.iter_text())
        self.assertEqual(repo.summary_writes, 0)


class TestTtlExpiry(unittest.TestCase):
    def test_conversation_disappears_after_ttl(self) -> None:
        clock = {"t": 0.0}
        store = EphemeralConversationStore(ttl_seconds=10.0, clock=lambda: clock["t"])
        store.create_conversation(AiConversation(conversation_id="c1", user_id="u1", mode="general"))
        self.assertIsNotNone(store.get_conversation("c1"))
        clock["t"] += 11.0
        self.assertIsNone(store.get_conversation("c1"))

    def test_reading_refreshes_ttl(self) -> None:
        clock = {"t": 0.0}
        store = EphemeralConversationStore(ttl_seconds=10.0, clock=lambda: clock["t"])
        store.create_conversation(AiConversation(conversation_id="c1", user_id="u1", mode="general"))
        clock["t"] += 8.0
        self.assertIsNotNone(store.get_conversation("c1"))  # touched, TTL renewed
        clock["t"] += 8.0
        self.assertIsNotNone(store.get_conversation("c1"))  # still alive (8 < 10 since last touch)

    def test_bounded_message_count_per_conversation(self) -> None:
        store = EphemeralConversationStore(max_messages=3)
        store.create_conversation(AiConversation(conversation_id="c1", user_id="u1", mode="general"))
        for i in range(10):
            store.create_message(AiMessage(
                message_id=f"m{i}", conversation_id="c1", user_id="u1", role="user",
                content=f"msg {i}"))
        kept = store.list_messages("c1", limit=100)
        self.assertEqual(len(kept), 3)
        self.assertEqual(kept[-1].content, "msg 9")

    def test_bounded_total_conversation_count(self) -> None:
        store = EphemeralConversationStore(max_conversations=2)
        for i in range(5):
            store.create_conversation(AiConversation(
                conversation_id=f"c{i}", user_id="u1", mode="general"))
        self.assertLessEqual(store.size(), 2)
        # the most recently created ones survive, oldest evicted first
        self.assertIsNotNone(store.get_conversation("c4"))
        self.assertIsNone(store.get_conversation("c0"))


class TestTurningOnResumesPersistence(unittest.TestCase):
    def test_switching_memory_on_persists_new_messages_durably(self) -> None:
        repo = _SpyRepo()
        rt = _runtime(repo)
        client = _client(rt)

        client.put("/api/ai/preferences", headers=_auth("alice"),
                   json={"memory_enabled": False, "preferences": {}})
        created = client.post("/api/ai/conversations", headers=_auth("alice"), json={"mode": "general"})
        cid = created.json()["conversation_id"]
        with client.stream("POST", f"/api/ai/conversations/{cid}/messages", headers=_auth("alice"),
                           json={"content": "off turn", "client_id": "c1"}) as resp:
            list(resp.iter_text())
        self.assertEqual(repo.message_writes, 0)

        client.put("/api/ai/preferences", headers=_auth("alice"),
                   json={"memory_enabled": True, "preferences": {}})
        with client.stream("POST", f"/api/ai/conversations/{cid}/messages", headers=_auth("alice"),
                           json={"content": "on turn", "client_id": "c2"}) as resp:
            list(resp.iter_text())

        # Now writes resumed: the second turn's user+assistant messages
        # landed in the durable spy repo (auto-registered a shadow
        # ephemeral->durable... no: this conversation was CREATED while
        # off, so it lives in the ephemeral store; once memory is back on,
        # new messages for it go to `rt.repo` regardless of where the
        # conversation container itself lives — see routes.py's
        # `_prepare` docstring on this exact re-evaluation-per-call rule).
        self.assertGreater(repo.message_writes, 0)


if __name__ == "__main__":
    unittest.main()
