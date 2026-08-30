import unittest

from server.chat.e2e_reader_scenario import run_scenario


class E2EReaderScenarioTest(unittest.TestCase):
    """Fanfic AI Chat V1 Phase 14 - the exact scenario from the mission
    brief: >=10 chapters, user at chapter 7, early-evidence citation,
    future-evidence spoiler block, paragraph explanation, chapter lookup.
    """

    def setUp(self):
        self.result = run_scenario()

    def test_early_evidence_chapter_4_is_cited(self):
        self.assertTrue(self.result["early_evidence"]["chapter_4_cited"])

    def test_future_evidence_chapter_9_never_leaked(self):
        """THE core spoiler-safety assertion of this whole feature."""
        self.assertFalse(self.result["future_evidence_blocked"]["chapter_9_leaked"])
        for chapter in self.result["future_evidence_blocked"]["cited_chapters"]:
            self.assertLessEqual(chapter, 7)

    def test_future_evidence_falls_back_to_in_range_chapters_not_empty(self):
        """The pipeline does NOT need to go empty-handed just because the
        single best-matching chapter (9) is blocked - it correctly falls
        back to the next-most-relevant chapters the user HAS read (2-7),
        which is better UX than a flat refusal. The one thing that must
        never happen is chapter 9 itself appearing - already covered by
        test_future_evidence_chapter_9_never_leaked."""
        self.assertTrue(self.result["future_evidence_blocked"]["cited_chapters"])

    def test_explain_paragraph_returns_an_answer(self):
        self.assertTrue(self.result["explain_paragraph"]["answer_text"])

    def test_search_lookup_finds_correct_chapter(self):
        self.assertTrue(self.result["search_lookup"]["correct"])
        self.assertEqual(self.result["search_lookup"]["top_cited_chapter"], 7)


if __name__ == "__main__":
    unittest.main()
