"""Tests for server/ai_assistant/web_search.py — sanitizer, Null/Mock adapters."""
from __future__ import annotations

import unittest

from server.ai_assistant.tools import ToolContext, format_web_results_for_prompt, web_search
from server.ai_assistant.web_search import MockWebSearch, NullWebSearch, WebResult


class TestNullWebSearch(unittest.TestCase):
    def test_always_returns_empty(self) -> None:
        tool = NullWebSearch()
        self.assertEqual(tool.search("anything"), [])
        self.assertEqual(tool.name, "off")


class TestMockWebSearch(unittest.TestCase):
    def test_empty_query_returns_empty(self) -> None:
        tool = MockWebSearch()
        self.assertEqual(tool.search(""), [])

    def test_strips_non_http_urls(self) -> None:
        tool = MockWebSearch(fixed_results=[
            WebResult(title="bad", url="javascript:alert(1)", snippet="x", source="mock"),
            WebResult(title="good", url="https://example.invalid/a", snippet="ok", source="mock"),
        ])
        results = tool.search("q")
        self.assertEqual([r.url for r in results], ["https://example.invalid/a"])

    def test_strips_html_and_caps_snippet(self) -> None:
        long_snippet = "<b>" + ("a" * 500) + "</b>"
        tool = MockWebSearch(fixed_results=[
            WebResult(title="<i>t</i>", url="https://example.invalid/x", snippet=long_snippet,
                     source="mock")])
        [result] = tool.search("q")
        self.assertNotIn("<", result.snippet)
        self.assertLessEqual(len(result.snippet), 300)

    def test_max_results_respected(self) -> None:
        results = [WebResult(title=f"t{i}", url=f"https://example.invalid/{i}", snippet="s",
                             source="mock") for i in range(10)]
        tool = MockWebSearch(fixed_results=results)
        self.assertEqual(len(tool.search("q", max_results=3)), 3)


class TestFormatForPrompt(unittest.TestCase):
    def test_wraps_results_in_untrusted_data_marker(self) -> None:
        ctx = ToolContext(web_search=MockWebSearch())
        results = web_search(ctx, "câu hỏi")
        text = format_web_results_for_prompt(results)
        self.assertIn("DỮ LIỆU KHÔNG ĐÁNG TIN", text)

    def test_empty_results_produce_empty_string(self) -> None:
        self.assertEqual(format_web_results_for_prompt([]), "")

    def test_no_web_search_configured_returns_empty(self) -> None:
        ctx = ToolContext()
        self.assertEqual(web_search(ctx, "q"), [])


if __name__ == "__main__":
    unittest.main()
