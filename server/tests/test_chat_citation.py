import unittest

from server.chat.citation import MAX_EXCERPT_CHARS, build_citations
from server.chat.domain import RetrievalResult


def _result(chapter_index, chunk_order, text="content"):
    return RetrievalResult(
        novel_id="n1", chapter_id=f"c{chapter_index}", chapter_index=chapter_index,
        chapter_title=f"Chapter {chapter_index}", chunk_text=text, chunk_order=chunk_order,
        similarity_score=0.9, content_hash="hash")


class BuildCitationsTest(unittest.TestCase):
    def test_one_citation_per_result(self):
        results = [_result(4, 0), _result(12, 1)]
        citations = build_citations(results)
        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0].chapter_index, 4)
        self.assertEqual(citations[1].chapter_index, 12)

    def test_duplicate_chunk_collapsed(self):
        results = [_result(4, 0), _result(4, 0)]
        citations = build_citations(results)
        self.assertEqual(len(citations), 1)

    def test_excerpt_bounded_length(self):
        long_text = "x" * 1000
        citations = build_citations([_result(1, 0, text=long_text)])
        self.assertLessEqual(len(citations[0].excerpt), MAX_EXCERPT_CHARS)

    def test_empty_results_no_citations(self):
        self.assertEqual(build_citations([]), [])

    def test_never_fabricates_citation_not_in_input(self):
        results = [_result(4, 0)]
        citations = build_citations(results)
        self.assertTrue(all(c.chapter_index == 4 for c in citations))


if __name__ == "__main__":
    unittest.main()
