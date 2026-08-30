import unittest

from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.universal.acquisition import NetworkEndpointCandidate
from server.scraper.universal.network_intelligence import (
    discover_embedded_json_endpoints, validate_candidates,
    validate_endpoint_candidate,
)

_PAGE_URL = "https://example.com/story/1"


class DiscoverEmbeddedJsonEndpointsTest(unittest.TestCase):
    def test_finds_api_shaped_url_in_next_data_script(self):
        html = (
            '<html><body>'
            '<script type="application/json" id="__NEXT_DATA__">'
            '{"props": {"apiUrl": "https://example.com/api/v1/chapters/1"}}'
            '</script></body></html>'
        )
        candidates = discover_embedded_json_endpoints(html, _PAGE_URL)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].url, "https://example.com/api/v1/chapters/1")
        self.assertEqual(candidates[0].discovered_via, "embedded_json_script")

    def test_no_script_blocks_returns_empty(self):
        html = "<html><body><p>plain page</p></body></html>"
        self.assertEqual(discover_embedded_json_endpoints(html, _PAGE_URL), [])

    def test_relative_endpoint_resolved_against_page_url(self):
        html = ('<script type="application/ld+json">'
               '{"url": "https://example.com/graphql?query=x"}</script>')
        candidates = discover_embedded_json_endpoints(html, _PAGE_URL)
        self.assertTrue(any("graphql" in c.url for c in candidates))

    def test_dedupes_repeated_urls(self):
        html = ('<script type="application/json">'
               '["https://example.com/api/v1/a", "https://example.com/api/v1/a"]'
               '</script>')
        candidates = discover_embedded_json_endpoints(html, _PAGE_URL)
        self.assertEqual(len(candidates), 1)


class ValidateEndpointCandidateTest(unittest.TestCase):
    def test_cross_origin_candidate_never_trusted(self):
        cand = NetworkEndpointCandidate(url="https://attacker.example/api/v1/x")
        fetcher = FixtureFetcher({})
        result = validate_endpoint_candidate(cand, page_url=_PAGE_URL, fetcher=fetcher)
        self.assertFalse(result.trusted)
        self.assertIn("khac origin", result.reasons[0])

    def test_same_origin_stable_json_is_trusted(self):
        url = "https://example.com/api/v1/chapters/1"
        cand = NetworkEndpointCandidate(url=url)
        fetcher = FixtureFetcher({url: '{"title": "Ch 1", "number": 1}'})
        result = validate_endpoint_candidate(cand, page_url=_PAGE_URL, fetcher=fetcher)
        self.assertTrue(result.trusted, result.reasons)

    def test_unfetchable_candidate_not_trusted_no_exception(self):
        cand = NetworkEndpointCandidate(url="https://example.com/api/v1/missing")
        fetcher = FixtureFetcher({})
        result = validate_endpoint_candidate(cand, page_url=_PAGE_URL, fetcher=fetcher)
        self.assertFalse(result.trusted)

    def test_oversized_response_not_trusted(self):
        url = "https://example.com/api/v1/huge"
        cand = NetworkEndpointCandidate(url=url)
        huge = '{"data": "' + ("x" * (3 * 1024 * 1024)) + '"}'
        fetcher = FixtureFetcher({url: huge})
        result = validate_endpoint_candidate(cand, page_url=_PAGE_URL, fetcher=fetcher)
        self.assertFalse(result.trusted)
        self.assertTrue(any("kich thuoc" in r for r in result.reasons))

    def test_reproducibility_check_can_be_disabled(self):
        url = "https://example.com/api/v1/x"
        cand = NetworkEndpointCandidate(url=url)
        fetcher = FixtureFetcher({url: '{"a": 1}'})
        result = validate_endpoint_candidate(
            cand, page_url=_PAGE_URL, fetcher=fetcher, check_reproducibility=False)
        self.assertTrue(result.trusted)

    def test_validate_candidates_runs_all(self):
        url1 = "https://example.com/api/v1/a"
        url2 = "https://attacker.example/api/v1/b"
        fetcher = FixtureFetcher({url1: '{"a": 1}'})
        results = validate_candidates(
            [NetworkEndpointCandidate(url=url1), NetworkEndpointCandidate(url=url2)],
            page_url=_PAGE_URL, fetcher=fetcher)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].trusted)
        self.assertFalse(results[1].trusted)


if __name__ == "__main__":
    unittest.main()
