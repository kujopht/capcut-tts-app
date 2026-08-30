"""
Anti-spoiler hard invariant tests — the single most important test file in
Fanfic AI Chat V1. Every scenario here is a real security/product
requirement, not an edge case: a failure here means a real user gets
spoiled.
"""
import unittest

from server.chat.domain import ChatContext, ChatScope, RetrievalResult, UserReadingContext
from server.chat.spoiler_gate import (
    apply_retrieval_gates, enforce_scope_boundary, enforce_spoiler_boundary,
)


def _result(novel_id, chapter_index, chunk_order=0):
    return RetrievalResult(
        novel_id=novel_id, chapter_id=f"{novel_id}-c{chapter_index}",
        chapter_index=chapter_index, chapter_title=f"Chapter {chapter_index}",
        chunk_text=f"content of chapter {chapter_index}", chunk_order=chunk_order,
        similarity_score=0.9, content_hash="hash")


class EnforceSpoilerBoundaryTest(unittest.TestCase):
    def test_chapter_at_or_before_progress_allowed(self):
        ctx = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=87)
        candidates = [_result("n1", 4), _result("n1", 87)]
        result = enforce_spoiler_boundary(candidates, reading_context=ctx)
        self.assertEqual(len(result), 2)

    def test_chapter_beyond_progress_blocked(self):
        """THE core requirement: chapter_index=88 must never reach a user
        whose current_chapter_index=87, evidence only in chapter 88."""
        ctx = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=87)
        candidates = [_result("n1", 4), _result("n1", 88)]
        result = enforce_spoiler_boundary(candidates, reading_context=ctx)
        indices = [r.chapter_index for r in result]
        self.assertEqual(indices, [4])
        self.assertNotIn(88, indices)

    def test_explicit_opt_out_disables_the_gate(self):
        ctx = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=7,
                                 spoiler_protection_enabled=False)
        candidates = [_result("n1", 4), _result("n1", 99)]
        result = enforce_spoiler_boundary(candidates, reading_context=ctx)
        self.assertEqual(len(result), 2)

    def test_other_novel_candidates_untouched_by_this_gate(self):
        """This function's ONLY concern is reading_context.novel_id -
        candidates from a different novel pass through unfiltered here
        (enforce_scope_boundary is what constrains cross-novel leakage)."""
        ctx = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=5)
        candidates = [_result("OTHER_NOVEL", 999)]
        result = enforce_spoiler_boundary(candidates, reading_context=ctx)
        self.assertEqual(len(result), 1)

    def test_empty_candidates_returns_empty(self):
        ctx = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=5)
        self.assertEqual(enforce_spoiler_boundary([], reading_context=ctx), [])

    def test_exact_boundary_chapter_is_allowed_not_off_by_one(self):
        ctx = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=10)
        result = enforce_spoiler_boundary([_result("n1", 10)], reading_context=ctx)
        self.assertEqual(len(result), 1)

    def test_immediately_next_chapter_is_blocked(self):
        ctx = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=10)
        result = enforce_spoiler_boundary([_result("n1", 11)], reading_context=ctx)
        self.assertEqual(result, [])


class EnforceScopeBoundaryTest(unittest.TestCase):
    def test_this_story_scope_blocks_cross_novel_leakage(self):
        candidates = [_result("n1", 1), _result("OTHER_NOVEL", 1)]
        result = enforce_scope_boundary(candidates, novel_id="n1", scope=ChatScope.THIS_STORY)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].novel_id, "n1")

    def test_this_chapter_scope_blocks_cross_novel_leakage(self):
        candidates = [_result("n1", 1), _result("OTHER_NOVEL", 1)]
        result = enforce_scope_boundary(candidates, novel_id="n1", scope=ChatScope.THIS_CHAPTER)
        self.assertEqual(len(result), 1)

    def test_character_scope_blocks_cross_novel_leakage(self):
        candidates = [_result("n1", 1), _result("OTHER_NOVEL", 1)]
        result = enforce_scope_boundary(candidates, novel_id="n1", scope=ChatScope.CHARACTER)
        self.assertEqual(len(result), 1)

    def test_general_scope_allows_cross_novel(self):
        candidates = [_result("n1", 1), _result("OTHER_NOVEL", 1)]
        result = enforce_scope_boundary(candidates, novel_id="n1", scope=ChatScope.GENERAL)
        self.assertEqual(len(result), 2)

    def test_search_scope_allows_cross_novel(self):
        candidates = [_result("n1", 1), _result("OTHER_NOVEL", 1)]
        result = enforce_scope_boundary(candidates, novel_id="n1", scope=ChatScope.SEARCH)
        self.assertEqual(len(result), 2)

    def test_recommendation_scope_allows_cross_novel(self):
        candidates = [_result("n1", 1), _result("OTHER_NOVEL", 1)]
        result = enforce_scope_boundary(candidates, novel_id="n1", scope=ChatScope.RECOMMENDATION)
        self.assertEqual(len(result), 2)


class ApplyRetrievalGatesTest(unittest.TestCase):
    def test_combined_gates_block_both_cross_novel_and_future_chapter(self):
        ctx = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=7)
        chat_ctx = ChatContext(user_reading_context=ctx, scope=ChatScope.THIS_STORY)
        candidates = [
            _result("n1", 4),           # allowed: same novel, read
            _result("n1", 9),           # blocked: same novel, unread (spoiler)
            _result("OTHER_NOVEL", 1),  # blocked: different novel (scope, THIS_STORY)
        ]
        result = apply_retrieval_gates(candidates, context=chat_ctx)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].chapter_index, 4)

    def test_general_scope_with_spoiler_protection_still_blocks_future_chapter_of_active_novel(self):
        """A GENERAL-scope query can span novels, but if a candidate
        happens to be from the SAME novel_id the user is actively reading,
        the spoiler boundary for THAT novel still applies - scope being
        cross-novel doesn't mean spoiler protection is off."""
        ctx = UserReadingContext(user_id="u1", novel_id="n1", current_chapter_index=7)
        chat_ctx = ChatContext(user_reading_context=ctx, scope=ChatScope.GENERAL)
        candidates = [_result("n1", 4), _result("n1", 50), _result("OTHER_NOVEL", 1)]
        result = apply_retrieval_gates(candidates, context=chat_ctx)
        novel_chapters = {(r.novel_id, r.chapter_index) for r in result}
        self.assertIn(("n1", 4), novel_chapters)
        self.assertNotIn(("n1", 50), novel_chapters)
        self.assertIn(("OTHER_NOVEL", 1), novel_chapters)


if __name__ == "__main__":
    unittest.main()
