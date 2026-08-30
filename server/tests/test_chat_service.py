import unittest

from server.chat.chunking import ChunkRecord
from server.chat.domain import ChatMessage
from server.chat_service import ChatService, InMemoryChatStore, get_chat_service


class TestChatService(unittest.TestCase):
    def test_in_memory_chat_store_roundtrip(self):
        store = InMemoryChatStore()
        conv_id = "conv-123"
        self.assertEqual(store.list_messages(conv_id), [])

        msg1 = ChatMessage(
            message_id="msg-1",
            conversation_id=conv_id,
            role="user",
            content="Hello world",
        )
        msg2 = ChatMessage(
            message_id="msg-2",
            conversation_id=conv_id,
            role="assistant",
            content="Hi there",
        )
        store.save_message(conv_id, msg1)
        store.save_message(conv_id, msg2)

        messages = store.list_messages(conv_id)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].message_id, "msg-1")
        self.assertEqual(messages[0].content, "Hello world")
        self.assertEqual(messages[1].message_id, "msg-2")
        self.assertEqual(messages[1].content, "Hi there")

    def test_chat_service_ask_and_spoiler_boundary(self):
        service = ChatService()

        # Seed 3 chunks across 3 chapters
        c1 = ChunkRecord(
            novel_id="novel-1",
            chapter_id="ch-1",
            chapter_index=1,
            chapter_title="Chapter 1: The Beginning",
            chunk_order=0,
            chunk_text="In the beginning, Alice met Bob in the secret forest.",
            content_hash="h1",
            chunk_hash="ch1",
        )
        c2 = ChunkRecord(
            novel_id="novel-1",
            chapter_id="ch-2",
            chapter_index=2,
            chapter_title="Chapter 2: The Journey",
            chunk_order=0,
            chunk_text="Alice and Bob traveled together through the stormy mountains.",
            content_hash="h2",
            chunk_hash="ch2",
        )
        c3 = ChunkRecord(
            novel_id="novel-1",
            chapter_id="ch-3",
            chapter_index=3,
            chapter_title="Chapter 3: The Secret Reveal",
            chunk_order=0,
            chunk_text="Alice discovered that Bob was secretly a magical dragon.",
            content_hash="h3",
            chunk_hash="ch3",
        )

        records = [
            (c1, service.embedding_provider.embed([c1.chunk_text])[0]),
            (c2, service.embedding_provider.embed([c2.chunk_text])[0]),
            (c3, service.embedding_provider.embed([c3.chunk_text])[0]),
        ]
        service.vector_store.upsert(records)

        # 1. Ask question with current_chapter_index=2 (spoiler boundary protects chapter 3)
        res = service.ask(
            "Who did Alice meet in the forest and what happened?",
            novel_id="novel-1",
            current_chapter_index=2,
            spoiler_protection_enabled=True,
        )

        self.assertIn("answer", res)
        self.assertIn("citations", res)
        self.assertIn("evidence_insufficient", res)
        self.assertIsInstance(res["answer"], str)
        self.assertIsInstance(res["citations"], list)
        self.assertIsInstance(res["evidence_insufficient"], bool)

        # Verify spoiler protection: citations must only be for chapter <= 2
        for cit in res["citations"]:
            self.assertLessEqual(
                cit["chapter_index"],
                2,
                f"Spoiler boundary violated: cited chapter {cit['chapter_index']} > 2",
            )

        # 2. Ask with current_chapter_index=3 (chapter 3 is now accessible)
        res_full = service.ask(
            "Is Bob secretly a dragon?",
            novel_id="novel-1",
            current_chapter_index=3,
            spoiler_protection_enabled=True,
        )
        self.assertIn("answer", res_full)
        self.assertIsInstance(res_full["citations"], list)
        if res_full["citations"]:
            for cit in res_full["citations"]:
                self.assertLessEqual(cit["chapter_index"], 3)

    def test_get_chat_service_singleton(self):
        s1 = get_chat_service()
        s2 = get_chat_service()
        self.assertIs(s1, s2)


if __name__ == "__main__":
    unittest.main()
