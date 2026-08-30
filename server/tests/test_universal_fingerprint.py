import unittest

from server.scraper.universal.fingerprint import build_fingerprint

_URL = "https://example.com/unknown-page"


class BuildFingerprintTest(unittest.TestCase):
    def test_dom_tag_histogram_counts_real_tags(self):
        html = "<html><body><p>a</p><p>b</p><div>c</div></body></html>"
        fp = build_fingerprint(html, _URL)
        self.assertEqual(fp.dom_tag_histogram.get("p"), 2)
        self.assertEqual(fp.dom_tag_histogram.get("div"), 1)

    def test_json_ld_type_extracted(self):
        html = (
            '<script type="application/ld+json">'
            '{"@context": "https://schema.org", "@type": "Article", "name": "x"}'
            '</script>'
        )
        fp = build_fingerprint(html, _URL)
        self.assertIn("Article", fp.json_ld_types)

    def test_json_ld_list_form_extracted(self):
        html = (
            '<script type="application/ld+json">'
            '[{"@type": "BreadcrumbList"}, {"@type": "Article"}]'
            '</script>'
        )
        fp = build_fingerprint(html, _URL)
        self.assertIn("BreadcrumbList", fp.json_ld_types)
        self.assertIn("Article", fp.json_ld_types)

    def test_embedded_json_top_level_keys(self):
        html = '<script type="application/json">{"props": {}, "page": "x"}</script>'
        fp = build_fingerprint(html, _URL)
        self.assertIn("props", fp.embedded_json_top_level_keys)
        self.assertIn("page", fp.embedded_json_top_level_keys)

    def test_internal_links_kept_external_links_dropped(self):
        html = (
            '<a href="https://example.com/a">a</a>'
            '<a href="https://other.example/b">b</a>'
            '<a href="/relative">c</a>'
        )
        fp = build_fingerprint(html, _URL)
        self.assertTrue(any("example.com/a" in link for link in fp.link_graph_sample))
        self.assertTrue(any("example.com/relative" in link for link in fp.link_graph_sample))
        self.assertFalse(any("other.example" in link for link in fp.link_graph_sample))

    def test_network_endpoint_candidates_discovered(self):
        html = (
            '<script type="application/json">'
            '{"apiUrl": "https://example.com/api/v1/data"}</script>'
        )
        fp = build_fingerprint(html, _URL)
        self.assertTrue(any("api/v1" in c.url for c in fp.network_endpoint_candidates))

    def test_malformed_html_does_not_crash(self):
        html = "<html><body><div><p>unclosed"
        fp = build_fingerprint(html, _URL)
        self.assertIsNotNone(fp)

    def test_content_signature_stable_for_same_shape(self):
        html_a = "<html><body><p>first content</p></body></html>"
        html_b = "<html><body><p>completely different content here</p></body></html>"
        fp_a = build_fingerprint(html_a, _URL)
        fp_b = build_fingerprint(html_b, _URL)
        self.assertEqual(fp_a.content_signature(), fp_b.content_signature())

    def test_content_signature_differs_for_different_shape(self):
        html_a = "<html><body><p>x</p></body></html>"
        html_b = "<html><body><article>x</article></body></html>"
        fp_a = build_fingerprint(html_a, _URL)
        fp_b = build_fingerprint(html_b, _URL)
        self.assertNotEqual(fp_a.content_signature(), fp_b.content_signature())


if __name__ == "__main__":
    unittest.main()
