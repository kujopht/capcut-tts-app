"""Tests for server/scraper/universal/structured_data.py (T1 helpers)."""
from __future__ import annotations

import json
import unittest

from server.scraper.universal.structured_data import (
    _CONTENT_MIN_LENGTH,
    _CONTENT_SEARCH_MAX_DEPTH,
    _EMBEDDED_JSON_MAX_SIZE,
    _SITEMAP_MAX_URLS,
    extract_embedded_json_blobs,
    find_content_in_json_blob,
    parse_feed,
    parse_sitemap,
)


class TestExtractEmbeddedJsonBlobs(unittest.TestCase):
    def test_finds_next_data(self):
        payload = {"props": {"pageProps": {"title": "Hello"}}}
        html = (
            '<html><head>'
            f'<script id="__NEXT_DATA__" type="application/json">'
            f"{json.dumps(payload)}"
            f"</script></head><body></body></html>"
        )
        blobs = extract_embedded_json_blobs(html)
        self.assertEqual(len(blobs), 1)
        self.assertEqual(blobs[0]["props"]["pageProps"]["title"], "Hello")

    def test_skips_malformed_next_data(self):
        html = (
            '<script id="__NEXT_DATA__" type="application/json">'
            '{"props": { TRUNCATED'
            "</script>"
        )
        blobs = extract_embedded_json_blobs(html)
        self.assertEqual(blobs, [])

    def test_ignores_ld_json(self):
        html = (
            '<script type="application/ld+json">'
            '{"@type": "Article", "headline": "Test"}'
            "</script>"
        )
        blobs = extract_embedded_json_blobs(html)
        self.assertEqual(blobs, [])

    def test_finds_generic_json_script(self):
        payload = {"config": {"apiUrl": "https://example.com"}}
        html = (
            '<script type="application/json">'
            f"{json.dumps(payload)}"
            "</script>"
        )
        blobs = extract_embedded_json_blobs(html)
        self.assertEqual(len(blobs), 1)
        self.assertEqual(blobs[0]["config"]["apiUrl"], "https://example.com")

    def test_returns_empty_for_no_json(self):
        html = "<html><body><p>No JSON here</p></body></html>"
        self.assertEqual(extract_embedded_json_blobs(html), [])

    def test_skips_oversized_blob(self):
        big_value = "x" * (_EMBEDDED_JSON_MAX_SIZE + 1000)
        payload = json.dumps({"data": big_value})
        html = f'<script id="__NEXT_DATA__" type="application/json">{payload}</script>'
        blobs = extract_embedded_json_blobs(html)
        self.assertEqual(blobs, [])

    def test_nuxt_valid_json(self):
        payload = {"state": {"count": 42}}
        html = (
            "<script>"
            f"window.__NUXT__={json.dumps(payload)};"
            "</script>"
        )
        blobs = extract_embedded_json_blobs(html)
        self.assertEqual(len(blobs), 1)
        self.assertEqual(blobs[0]["state"]["count"], 42)

    def test_nuxt_js_expression_skipped(self):
        # Nuxt sometimes uses JS expressions, not valid JSON
        html = "<script>window.__NUXT__={state: Date.now()}</script>"
        blobs = extract_embedded_json_blobs(html)
        self.assertEqual(blobs, [])


class TestFindContentInJsonBlob(unittest.TestCase):
    def test_finds_deeply_nested_content(self):
        long_text = "word " * 50  # 250 chars
        blob = {
            "props": {
                "pageProps": {
                    "article": {
                        "body": long_text,
                    }
                }
            }
        }
        result = find_content_in_json_blob(blob)
        self.assertEqual(result, long_text)

    def test_returns_none_when_no_match(self):
        blob = {"props": {"pageProps": {"title": "Short"}}}
        self.assertIsNone(find_content_in_json_blob(blob))

    def test_returns_none_for_short_string(self):
        blob = {"content": "too short"}
        self.assertIsNone(find_content_in_json_blob(blob))

    def test_respects_max_depth(self):
        # Build a dict nested deeper than _CONTENT_SEARCH_MAX_DEPTH
        long_text = "word " * 50
        inner: dict = {"content": long_text}
        current = inner
        for _ in range(_CONTENT_SEARCH_MAX_DEPTH + 5):
            current = {"nested": current}
        # The content is now at depth > MAX_DEPTH, so should not be found
        result = find_content_in_json_blob(current)
        self.assertIsNone(result)

    def test_finds_in_list(self):
        long_text = "body text " * 30
        blob = {"items": [{"data": [{"articleBody": long_text}]}]}
        result = find_content_in_json_blob(blob)
        self.assertEqual(result, long_text)

    def test_custom_hint_keys(self):
        long_text = "description " * 25
        blob = {"meta": {"summary": long_text}}
        result = find_content_in_json_blob(blob, hint_keys=["summary"])
        self.assertEqual(result, long_text)

    def test_case_insensitive_key(self):
        long_text = "text " * 50
        blob = {"page": {"Content": long_text}}
        result = find_content_in_json_blob(blob)
        self.assertEqual(result, long_text)


class TestParseFeed(unittest.TestCase):
    RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Chapter 1</title>
      <link>https://example.com/ch1</link>
      <description>First chapter description with enough words to be meaningful.</description>
      <pubDate>Mon, 01 Jan 2026 00:00:00 GMT</pubDate>
      <guid>ch1-uuid</guid>
    </item>
    <item>
      <title>Chapter 2</title>
      <link>https://example.com/ch2</link>
      <description>Second chapter description also with enough words to pass as real content.</description>
      <pubDate>Tue, 02 Jan 2026 00:00:00 GMT</pubDate>
      <guid>ch2-uuid</guid>
    </item>
  </channel>
</rss>"""

    ATOM_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Feed</title>
  <entry>
    <title>Entry One</title>
    <link href="https://example.com/e1"/>
    <summary>Summary of entry one with sufficient length to be meaningful for testing.</summary>
    <published>2026-01-01T00:00:00Z</published>
    <id>entry-1-id</id>
  </entry>
  <entry>
    <title>Entry Two</title>
    <link href="https://example.com/e2"/>
    <summary>Summary of entry two also with sufficient length to be meaningful for testing.</summary>
    <updated>2026-01-02T00:00:00Z</updated>
    <id>entry-2-id</id>
  </entry>
</feed>"""

    def test_parse_rss(self):
        items = parse_feed(self.RSS_FIXTURE)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "Chapter 1")
        self.assertEqual(items[0]["link"], "https://example.com/ch1")
        self.assertEqual(items[0]["guid_or_id"], "ch1-uuid")
        self.assertEqual(items[0]["published"], "Mon, 01 Jan 2026 00:00:00 GMT")
        self.assertEqual(items[1]["title"], "Chapter 2")
        self.assertEqual(items[1]["guid_or_id"], "ch2-uuid")

    def test_parse_atom(self):
        items = parse_feed(self.ATOM_FIXTURE)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "Entry One")
        self.assertEqual(items[0]["link"], "https://example.com/e1")
        self.assertEqual(items[0]["guid_or_id"], "entry-1-id")
        self.assertIn("2026-01-01", items[0]["published"])
        self.assertEqual(items[1]["title"], "Entry Two")
        self.assertEqual(items[1]["guid_or_id"], "entry-2-id")

    def test_returns_empty_for_malformed_xml(self):
        self.assertEqual(parse_feed("<not valid xml"), [])

    def test_returns_empty_for_non_feed_xml(self):
        html = "<html><body><p>Not a feed</p></body></html>"
        self.assertEqual(parse_feed(html), [])


class TestParseSitemap(unittest.TestCase):
    URLSET_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
  <url><loc>https://example.com/page3</loc></url>
</urlset>"""

    INDEX_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap1.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap2.xml</loc></sitemap>
</sitemapindex>"""

    def test_parse_urlset(self):
        urls = parse_sitemap(self.URLSET_FIXTURE)
        self.assertEqual(urls, [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3",
        ])

    def test_parse_sitemap_index(self):
        urls = parse_sitemap(self.INDEX_FIXTURE)
        self.assertEqual(urls, [
            "https://example.com/sitemap1.xml",
            "https://example.com/sitemap2.xml",
        ])

    def test_returns_empty_for_malformed_xml(self):
        self.assertEqual(parse_sitemap("<broken xml"), [])

    def test_returns_empty_for_non_sitemap_xml(self):
        xml = "<html><body>Not a sitemap</body></html>"
        self.assertEqual(parse_sitemap(xml), [])


if __name__ == "__main__":
    unittest.main()
