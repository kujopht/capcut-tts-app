"""Tests for server/ai_assistant/memory.py — InMemoryAiRepo semantics,
AppwriteAiRepo (httpx.MockTransport, no network), secret redaction before
persist, delete-all-memory.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass

import httpx

from server.ai_assistant.memory import (
    AiConversation, AiMessage, AiPreferences, AiProject, AiUnavailable, AppwriteAiRepo,
    InMemoryAiRepo, RepoConflict, redact,
)
from server.config import AppwriteSettings

# Bi mat GIA ghep LUC CHAY (quy uoc .gitleaks.toml sau su co 2026-08-16): nguon khong chua chuoi lien tuc giong
# khoa/JWT that, nen gitleaks khong can allowlist nao cho tep nay.
KHOA_GIA = "sk-" + "abcdefgh" * 3
JWT_GIA = ".".join(["eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiIxMjM0NTY3ODkwIn0", "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"])


class TestRedact(unittest.TestCase):
    def test_bearer_token_is_redacted(self) -> None:
        text = f"here is my token: Bearer {KHOA_GIA}"
        self.assertNotIn(KHOA_GIA, redact(text))

    def test_jwt_is_redacted(self) -> None:
        jwt = JWT_GIA
        self.assertNotIn(jwt, redact(f"leaked: {jwt}"))

    def test_ordinary_text_untouched(self) -> None:
        text = "Xin chào, đây là câu hỏi bình thường."
        self.assertEqual(redact(text), text)


class TestInMemoryAiRepo(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryAiRepo()

    def test_create_conversation_conflict(self) -> None:
        c = AiConversation(conversation_id="c1", user_id="u1", mode="general")
        self.repo.create_conversation(c)
        with self.assertRaises(RepoConflict):
            self.repo.create_conversation(c)

    def test_list_conversations_excludes_archived_and_orders_by_updated(self) -> None:
        self.repo.create_conversation(AiConversation(
            conversation_id="c1", user_id="u1", mode="general", updated_at="2026-01-01T00:00:00"))
        self.repo.create_conversation(AiConversation(
            conversation_id="c2", user_id="u1", mode="general", updated_at="2026-01-02T00:00:00"))
        self.repo.create_conversation(AiConversation(
            conversation_id="c3", user_id="u1", mode="general", archived=True,
            updated_at="2026-01-03T00:00:00"))
        items = self.repo.list_conversations("u1")
        self.assertEqual([c.conversation_id for c in items], ["c2", "c1"])

    def test_message_count_increments_on_conversation(self) -> None:
        self.repo.create_conversation(AiConversation(conversation_id="c1", user_id="u1", mode="general"))
        self.repo.create_message(AiMessage(
            message_id="m1", conversation_id="c1", user_id="u1", role="user", content="hi"))
        conv = self.repo.get_conversation("c1")
        self.assertEqual(conv.message_count, 1)

    def test_delete_conversation_cascades_messages_and_summary(self) -> None:
        self.repo.create_conversation(AiConversation(conversation_id="c1", user_id="u1", mode="general"))
        self.repo.create_message(AiMessage(
            message_id="m1", conversation_id="c1", user_id="u1", role="user", content="hi"))
        self.repo.delete_conversation("c1")
        self.assertIsNone(self.repo.get_conversation("c1"))
        self.assertEqual(self.repo.list_messages("c1"), [])

    def test_delete_all_memory_keeps_projects_by_default(self) -> None:
        self.repo.create_conversation(AiConversation(conversation_id="c1", user_id="u1", mode="general"))
        self.repo.create_project(AiProject(project_id="p1", user_id="u1"))
        self.repo.put_preferences(AiPreferences(user_id="u1", memory_enabled=False))
        self.repo.delete_all_memory("u1")
        self.assertIsNone(self.repo.get_conversation("c1"))
        self.assertIsNone(self.repo.get_preferences("u1"))
        self.assertIsNotNone(self.repo.get_project("p1"))

    def test_delete_all_memory_include_projects(self) -> None:
        self.repo.create_project(AiProject(project_id="p1", user_id="u1"))
        self.repo.delete_all_memory("u1", include_projects=True)
        self.assertIsNone(self.repo.get_project("p1"))


def _fake_appwrite(**overrides) -> AppwriteSettings:
    base = dict(endpoint="https://appwrite.example/v1", project_id="proj", api_key="key",
               database_id="db")
    base.update(overrides)
    return AppwriteSettings(**base)


@dataclass
class _FakeSettings:
    appwrite: AppwriteSettings


class TestAppwriteAiRepo(unittest.TestCase):
    def _repo(self, handler):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        return AppwriteAiRepo(_FakeSettings(appwrite=_fake_appwrite()), client=client)

    def test_raises_ai_unavailable_when_not_configured(self) -> None:
        with self.assertRaises(AiUnavailable):
            AppwriteAiRepo(_FakeSettings(appwrite=_fake_appwrite(endpoint="")))

    def test_create_conversation_posts_document_with_no_permissions(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["path"] = request.url.path
            import json as _json
            seen["body"] = _json.loads(request.content)
            return httpx.Response(201, json={"$id": "c1"})

        repo = self._repo(handler)
        conv = AiConversation(conversation_id="c1", user_id="u1", mode="general")
        repo.create_conversation(conv)
        self.assertEqual(seen["method"], "POST")
        self.assertTrue(seen["path"].endswith("/ai_conversations/documents"))
        self.assertEqual(seen["body"]["permissions"], [])
        self.assertEqual(seen["body"]["documentId"], "c1")

    def test_create_conversation_409_raises_repo_conflict(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(409, json={"message": "exists"})

        repo = self._repo(handler)
        with self.assertRaises(RepoConflict):
            repo.create_conversation(AiConversation(conversation_id="c1", user_id="u1", mode="general"))

    def test_5xx_raises_ai_unavailable_not_repo_conflict(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"message": "boom"})

        repo = self._repo(handler)
        with self.assertRaises(AiUnavailable):
            repo.create_conversation(AiConversation(conversation_id="c1", user_id="u1", mode="general"))

    def test_message_content_is_redacted_before_being_sent(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(404, json={"message": "not found"})
            import json as _json
            body = _json.loads(request.content)
            if "content" in body.get("data", {}):
                seen["content"] = body["data"]["content"]
            return httpx.Response(201, json={"$id": "m1", "message_count": 0})

        repo = self._repo(handler)
        secret_text = f"token của tôi là Bearer {KHOA_GIA} nhé"
        repo.create_message(AiMessage(
            message_id="m1", conversation_id="c1", user_id="u1", role="user", content=secret_text))
        self.assertNotIn(KHOA_GIA, seen["content"])

    def test_increment_usage_read_modify_write(self) -> None:
        state = {"exists": False, "requests": 0, "input_tokens": 0, "output_tokens": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                if not state["exists"]:
                    return httpx.Response(404, json={"message": "not found"})
                return httpx.Response(200, json={
                    "requests": state["requests"], "input_tokens": state["input_tokens"],
                    "output_tokens": state["output_tokens"]})
            if request.method == "POST":
                state["exists"] = True
                state["requests"] = 1
                state["input_tokens"] = 10
                state["output_tokens"] = 5
                return httpx.Response(201, json={})
            if request.method == "PATCH":
                import json as _json
                body = _json.loads(request.content)["data"]
                state.update(body)
                return httpx.Response(200, json={})
            raise AssertionError("unexpected method")

        repo = self._repo(handler)
        u1 = repo.increment_usage("u1", "20260101", input_tokens=10, output_tokens=5)
        self.assertEqual(u1.requests, 1)
        u2 = repo.increment_usage("u1", "20260101", input_tokens=3, output_tokens=2)
        self.assertEqual(u2.requests, 2)
        self.assertEqual(u2.input_tokens, 13)
        self.assertEqual(u2.output_tokens, 7)


if __name__ == "__main__":
    unittest.main()
