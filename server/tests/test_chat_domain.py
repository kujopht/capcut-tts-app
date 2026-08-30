import unittest

from server.chat.domain import (
    ChatContext, ChatConversation, ChatMessage, ChatScope, Citation,
    RetrievalResult, UserReadingContext,
)


class UserReadingContextTest(unittest.TestCase):
    def test_defaults_spoiler_protection_on(self):
        ctx = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=87)
        self.assertTrue(ctx.spoiler_protection_enabled)

    def test_immutable(self):
        ctx = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=87)
        with self.assertRaises(Exception):
            ctx.current_chapter_index = 100


class ChatContextTest(unittest.TestCase):
    def test_minimal_construction(self):
        reading = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=5)
        ctx = ChatContext(user_reading_context=reading, scope=ChatScope.THIS_CHAPTER)
        self.assertIsNone(ctx.selected_text)
        self.assertIsNone(ctx.active_chapter_id)


class RetrievalResultAndCitationTest(unittest.TestCase):
    def test_retrieval_result_construction(self):
        r = RetrievalResult(
            novel_id="n1", chapter_id="c1", chapter_index=4, chapter_title="Ch4",
            chunk_text="something happened", chunk_order=0, similarity_score=0.9,
            content_hash="abc123")
        self.assertEqual(r.language, "")

    def test_citation_construction(self):
        c = Citation(novel_id="n1", chapter_id="c1", chapter_index=4,
                     chapter_title="Ch4", excerpt="something happened", chunk_order=0)
        self.assertEqual(c.chapter_index, 4)


class ChatMessageAndConversationTest(unittest.TestCase):
    def test_message_defaults_no_citations(self):
        msg = ChatMessage(message_id="m1", conversation_id="conv1", role="user",
                          content="hello")
        self.assertEqual(msg.citations, [])
        self.assertTrue(msg.created_at)

    def test_conversation_defaults(self):
        conv = ChatConversation(conversation_id="conv1", user_id="u1",
                               scope=ChatScope.GENERAL)
        self.assertIsNone(conv.novel_id)
        self.assertTrue(conv.created_at)


if __name__ == "__main__":
    unittest.main()
