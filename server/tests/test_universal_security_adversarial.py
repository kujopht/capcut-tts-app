"""
Adversarial security tests — Story Harvester V5 Phase 13.

Scope: NEW code paths introduced by the V5 universal package. SSRF/robots/
redirect/response-size protections already proven in `http_fetcher.py`
(see `test_story_scraper_http_fetcher.py::SsrfProtectionTest` and
`ResponseSizeCapTest`) are inherited for free by `AcquisitionRouter`
(Tier 1) and `network_intelligence.validate_endpoint_candidate` - both
route every real fetch through the SAME `HttpFetcher`/injected fetcher,
never a separate unguarded request path. This file does not re-prove
those; it proves the NEW code around them behaves safely too.
"""
from __future__ import annotations

import unittest

from server.scraper.http_fetcher import FetchError, FixtureFetcher, HttpFetcher
from server.scraper.universal.acquisition import (
    AcquisitionStatus, NetworkEndpointCandidate, SourceClass,
)
from server.scraper.universal.fingerprint import build_fingerprint
from server.scraper.universal.network_intelligence import validate_endpoint_candidate
from server.scraper.universal.router import AcquisitionRouter


class RouterSurfacesSsrfAsFailedNotCrashTest(unittest.TestCase):
    """A real (no mocking) loopback-literal URL - HttpFetcher's own SSRF
    check rejects it before any connection attempt. The NEW behavior being
    proven here is that AcquisitionRouter.acquire() catches this and
    returns a FAILED AcquisitionResult, never letting SsrfBlockedError
    propagate uncaught out of the router."""

    def test_loopback_literal_returns_failed_not_raised(self):
        router = AcquisitionRouter(http_fetcher=HttpFetcher(
            max_retries=0, min_delay_seconds=0, respect_robots=False))
        result = router.acquire("http://127.0.0.1:1/x", source_hint=SourceClass.GENERIC_WEB)
        self.assertEqual(result.status, AcquisitionStatus.FAILED)
        self.assertTrue(result.errors)
        self.assertIn("riêng tư", result.errors[0].message)


class RouterSurfacesRedirectLoopAsFailedTest(unittest.TestCase):
    """Simulates the underlying fetcher reporting a redirect-loop failure
    (the real redirect-loop cap lives in HttpFetcher, already tested
    elsewhere) - proves the ROUTER's own error handling treats it as a
    normal FAILED result, not an uncaught exception or an infinite retry
    of its own."""

    def test_redirect_loop_error_from_fetcher_becomes_failed_result(self):
        class _LoopingFetcher:
            def fetch(self, url, **kwargs):
                raise FetchError(f"Quá 20 lần chuyển hướng khi tải {url}")

        router = AcquisitionRouter(http_fetcher=_LoopingFetcher())
        result = router.acquire("https://example.com/loop")
        self.assertEqual(result.status, AcquisitionStatus.FAILED)
        self.assertIn("chuyển hướng", result.errors[0].message)


class RouterDoesNotRetryBeyondOneAttemptPerTierTest(unittest.TestCase):
    """AcquisitionRouter itself must not add its own retry loop on top of
    whatever the underlying fetcher/plugin already does - a plugin that
    fails must be called exactly once per `acquire()` call, not hammered."""

    def test_failing_plugin_called_exactly_once(self):
        from server.scraper.universal.router import AcquisitionPlugin, AcquisitionTier
        from server.scraper.universal.acquisition import (
            AcquisitionMethod, AcquisitionResult,
        )

        class _CountingFailingPlugin(AcquisitionPlugin):
            tier = AcquisitionTier.TIER2_BROWSER
            name = "counting"

            def __init__(self):
                self.calls = 0

            def available(self):
                return True

            def acquire(self, url, *, source_hint=SourceClass.UNKNOWN):
                self.calls += 1
                return AcquisitionResult(
                    final_url=url, source_type=source_hint,
                    status=AcquisitionStatus.FAILED,
                    acquisition_method=AcquisitionMethod.BROWSER_RENDER)

        plugin = _CountingFailingPlugin()
        router = AcquisitionRouter(http_fetcher=FixtureFetcher({}), plugins=[plugin])
        router.acquire("https://example.com/x")
        self.assertEqual(plugin.calls, 1)


class HostConfusionSameOriginTest(unittest.TestCase):
    """A visually-similar Unicode host (Cyrillic 'а' vs Latin 'a') must
    NEVER be treated as same-origin - `domain_of` does a plain string
    compare, which correctly differs here since the raw bytes differ, but
    this is proven explicitly rather than assumed."""

    def test_cyrillic_lookalike_host_is_not_same_origin(self):
        page_url = "https://example.com/story/1"
        lookalike = "https://exаmple.com/api/v1/x"  # Cyrillic 'а' (U+0430)
        candidate = NetworkEndpointCandidate(url=lookalike)
        result = validate_endpoint_candidate(
            candidate, page_url=page_url, fetcher=FixtureFetcher({}))
        self.assertFalse(result.trusted)
        self.assertIn("khac origin", result.reasons[0])

    def test_punycode_host_is_not_same_origin_as_ascii_host(self):
        page_url = "https://example.com/story/1"
        punycode = "https://xn--example-x1a.com/api/v1/x"
        candidate = NetworkEndpointCandidate(url=punycode)
        result = validate_endpoint_candidate(
            candidate, page_url=page_url, fetcher=FixtureFetcher({}))
        self.assertFalse(result.trusted)


class CredentialRedactionInFingerprintTest(unittest.TestCase):
    """A page embedding a credential-bearing link (`https://user:secretpw@
    evil.example/callback`) must never carry that credential into a
    fingerprint - the fingerprint is later sent verbatim to an LLM."""

    def test_url_userinfo_stripped_from_link_sample(self):
        html = '<a href="https://user:secretpw@example.com/callback">click</a>'
        fp = build_fingerprint(html, "https://example.com/page")
        joined = " ".join(fp.link_graph_sample)
        self.assertNotIn("secretpw", joined)
        self.assertNotIn("user:secretpw@", joined)

    def test_link_without_credentials_unaffected(self):
        html = '<a href="https://example.com/normal-page">click</a>'
        fp = build_fingerprint(html, "https://example.com/page")
        self.assertTrue(any("example.com/normal-page" in link for link in fp.link_graph_sample))

    def test_credential_shaped_query_param_value_redacted(self):
        """Bai quyet dinh: review doc lap tim thay redaction ban dau chi
        chan URL userinfo (user:pass@host), bo sot mau hinh THAT SU pho
        bien hon: api key/token dua qua query param (?api_key=...)."""
        html = '<a href="https://example.com/api?api_key=sk-live-SECRETVALUE123">x</a>'
        fp = build_fingerprint(html, "https://example.com/page")
        joined = " ".join(fp.link_graph_sample)
        self.assertNotIn("SECRETVALUE123", joined)
        self.assertIn("api_key=", joined)

    def test_canonical_url_itself_is_clipped_and_redacted(self):
        """Bai quyet dinh: review doc lap tim thay canonical_url bo qua
        _clip() hoan toan, mang credential/do dai khong gioi han thang
        vao prompt LLM."""
        url_with_credential = "https://user:secretpw@example.com/page?token=SECRETTOKEN456"
        fp = build_fingerprint("<html></html>", url_with_credential)
        self.assertNotIn("secretpw", fp.canonical_url)
        self.assertNotIn("SECRETTOKEN456", fp.canonical_url)


class OversizedCandidateResponseTest(unittest.TestCase):
    """Reproduces the existing `ResponseSizeCapTest` intent, at the
    network_intelligence layer this time - a candidate endpoint returning
    an oversized body must never be trusted, even if everything else about
    it (origin, content-type) looks legitimate."""

    def test_oversized_json_candidate_rejected(self):
        url = "https://example.com/api/v1/huge"
        candidate = NetworkEndpointCandidate(url=url)
        huge_body = '{"data": "' + ("a" * (5 * 1024 * 1024)) + '"}'
        fetcher = FixtureFetcher({url: huge_body})
        result = validate_endpoint_candidate(
            candidate, page_url="https://example.com/page", fetcher=fetcher)
        self.assertFalse(result.trusted)


if __name__ == "__main__":
    unittest.main()
