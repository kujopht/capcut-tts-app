import unittest

from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.universal.acquisition import (
    AcquisitionMethod, AcquisitionResult, AcquisitionStatus, SourceClass,
)
from server.scraper.universal.router import (
    AcquisitionPlugin, AcquisitionRouter, AcquisitionTier,
)

_URL = "https://example.com/story/1"


class _FakePlugin(AcquisitionPlugin):
    def __init__(self, tier, *, is_available=True, succeeds=True, name="fake"):
        self.tier = tier
        self.name = name
        self._available = is_available
        self._succeeds = succeeds
        self.calls = 0

    def available(self):
        return self._available

    def acquire(self, url, *, source_hint=SourceClass.UNKNOWN):
        self.calls += 1
        status = AcquisitionStatus.OK if self._succeeds else AcquisitionStatus.FAILED
        return AcquisitionResult(
            final_url=url, source_type=source_hint, status=status,
            acquisition_method=AcquisitionMethod.BROWSER_RENDER
            if self.tier == AcquisitionTier.TIER2_BROWSER
            else AcquisitionMethod.STRUCTURED_API,
            provenance=self.name)


class Tier1OnlyTest(unittest.TestCase):
    def test_tier1_succeeds_with_no_plugins_registered(self):
        fetcher = FixtureFetcher({_URL: "<html><body>hi</body></html>"})
        router = AcquisitionRouter(http_fetcher=fetcher)
        result = router.acquire(_URL, source_hint=SourceClass.WEB_FICTION)
        self.assertTrue(result.ok)
        self.assertEqual(result.acquisition_method, AcquisitionMethod.DIRECT_HTTP)

    def test_tier1_failure_with_no_plugins_returns_failed_not_exception(self):
        fetcher = FixtureFetcher({})
        router = AcquisitionRouter(http_fetcher=fetcher)
        result = router.acquire(_URL)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, AcquisitionStatus.FAILED)
        self.assertTrue(result.errors)


class PluginFallbackTest(unittest.TestCase):
    def test_falls_back_to_tier2_plugin_when_tier1_fails(self):
        fetcher = FixtureFetcher({})
        plugin = _FakePlugin(AcquisitionTier.TIER2_BROWSER)
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])
        result = router.acquire(_URL)
        self.assertTrue(result.ok)
        self.assertEqual(plugin.calls, 1)

    def test_unavailable_plugin_is_skipped(self):
        fetcher = FixtureFetcher({})
        plugin = _FakePlugin(AcquisitionTier.TIER2_BROWSER, is_available=False)
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])
        result = router.acquire(_URL)
        self.assertFalse(result.ok)
        self.assertEqual(plugin.calls, 0)

    def test_all_tiers_fail_returns_last_failure_not_generic_error(self):
        fetcher = FixtureFetcher({})
        plugin = _FakePlugin(AcquisitionTier.TIER2_BROWSER, succeeds=False)
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])
        result = router.acquire(_URL)
        self.assertFalse(result.ok)
        self.assertEqual(result.provenance, "fake")


class HistoryDrivenSelectionTest(unittest.TestCase):
    def test_successful_tier_is_remembered_and_preferred_next_time(self):
        fetcher = FixtureFetcher({})
        plugin = _FakePlugin(AcquisitionTier.TIER3_STRUCTURED)
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])

        router.acquire(_URL)
        self.assertEqual(router.preferred_tier(_URL), AcquisitionTier.TIER3_STRUCTURED)

        router.acquire(_URL)
        self.assertEqual(plugin.calls, 2)

    def test_record_observation_ignores_failed_attempts(self):
        router = AcquisitionRouter(http_fetcher=FixtureFetcher({}))
        router.record_observation(_URL, AcquisitionTier.TIER2_BROWSER, success=False)
        self.assertEqual(router.preferred_tier(_URL), AcquisitionTier.TIER1_DIRECT_HTTP)

    def test_default_preferred_tier_is_tier1(self):
        router = AcquisitionRouter(http_fetcher=FixtureFetcher({}))
        self.assertEqual(router.preferred_tier(_URL), AcquisitionTier.TIER1_DIRECT_HTTP)


if __name__ == "__main__":
    unittest.main()
