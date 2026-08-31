import unittest

from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.universal.acquisition import (
    AcquisitionMethod, AcquisitionResult, AcquisitionStatus, SourceClass,
)
from server.scraper.universal.router import (
    AcquisitionPlugin, AcquisitionRouter, AcquisitionTier, TierAttempt,
    _order_from,
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
            if self.tier == AcquisitionTier.T2_BROWSER_RENDERED
            else AcquisitionMethod.STRUCTURED_API,
            provenance=self.name)


class T0OnlyTest(unittest.TestCase):
    def test_t0_succeeds_with_no_plugins_registered(self):
        fetcher = FixtureFetcher({_URL: "<html><body>hi</body></html>"})
        router = AcquisitionRouter(http_fetcher=fetcher)
        result = router.acquire(_URL, source_hint=SourceClass.WEB_FICTION)
        self.assertTrue(result.ok)
        self.assertEqual(result.acquisition_method, AcquisitionMethod.DIRECT_HTTP)

    def test_t0_failure_with_no_plugins_returns_failed_not_exception(self):
        fetcher = FixtureFetcher({})
        router = AcquisitionRouter(http_fetcher=fetcher)
        result = router.acquire(_URL)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, AcquisitionStatus.FAILED)
        self.assertTrue(result.errors)


class PluginFallbackTest(unittest.TestCase):
    def test_falls_back_to_t2_plugin_when_t0_fails(self):
        fetcher = FixtureFetcher({})
        plugin = _FakePlugin(AcquisitionTier.T2_BROWSER_RENDERED)
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])
        result = router.acquire(_URL)
        self.assertTrue(result.ok)
        self.assertEqual(plugin.calls, 1)

    def test_unavailable_plugin_is_skipped(self):
        fetcher = FixtureFetcher({})
        plugin = _FakePlugin(AcquisitionTier.T2_BROWSER_RENDERED, is_available=False)
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])
        result = router.acquire(_URL)
        self.assertFalse(result.ok)
        self.assertEqual(plugin.calls, 0)

    def test_all_tiers_fail_returns_last_failure_not_generic_error(self):
        fetcher = FixtureFetcher({})
        plugin = _FakePlugin(AcquisitionTier.T2_BROWSER_RENDERED, succeeds=False)
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])
        result = router.acquire(_URL)
        self.assertFalse(result.ok)
        self.assertEqual(result.provenance, "fake")


class HistoryDrivenSelectionTest(unittest.TestCase):
    def test_successful_tier_is_remembered_and_preferred_next_time(self):
        fetcher = FixtureFetcher({})
        plugin = _FakePlugin(AcquisitionTier.T3_PUBLIC_NETWORK)
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])

        router.acquire(_URL)
        self.assertEqual(router.preferred_tier(_URL), AcquisitionTier.T3_PUBLIC_NETWORK)

        router.acquire(_URL)
        self.assertEqual(plugin.calls, 2)

    def test_record_observation_ignores_failed_attempts(self):
        router = AcquisitionRouter(http_fetcher=FixtureFetcher({}))
        router.record_observation(_URL, AcquisitionTier.T2_BROWSER_RENDERED, success=False)
        self.assertEqual(router.preferred_tier(_URL), AcquisitionTier.T0_DIRECT)

    def test_default_preferred_tier_is_t0(self):
        router = AcquisitionRouter(http_fetcher=FixtureFetcher({}))
        self.assertEqual(router.preferred_tier(_URL), AcquisitionTier.T0_DIRECT)


class TierOrderGenerationTest(unittest.TestCase):
    """Universal Acquisition Engine Hardening (2026-08-31): thay danh sach
    hoan vi liet ke tay bang mot ham sinh thu tu tu `_CANONICAL_ORDER` -
    xac nhan ca 6 tang deu co mat, dung mot lan, va tang uu tien luon dung dau."""

    def test_ca_sau_tang_co_mat_dung_mot_lan_voi_moi_tang_uu_tien(self):
        for preferred in AcquisitionTier:
            with self.subTest(preferred=preferred):
                order = _order_from(preferred)
                self.assertEqual(len(order), 6)
                self.assertEqual(set(order), set(AcquisitionTier))
                self.assertEqual(order[0], preferred)

    def test_thu_tu_mac_dinh_re_nhat_truoc_khi_khong_co_lich_su(self):
        order = _order_from(AcquisitionTier.T0_DIRECT)
        self.assertEqual(order, (
            AcquisitionTier.T0_DIRECT, AcquisitionTier.T1_STRUCTURED,
            AcquisitionTier.T2_BROWSER_RENDERED, AcquisitionTier.T3_PUBLIC_NETWORK,
            AcquisitionTier.T4_DOCUMENT, AcquisitionTier.T5_MANAGED_PROVIDER,
        ))


class AcquireWithAttemptsTest(unittest.TestCase):
    """Universal Acquisition Engine Hardening (2026-08-31): `acquire()`'s
    escalation loop, but with a per-tier `TierAttempt` trail for
    observability (`universal/report.py` builds on this)."""

    def test_t0_success_records_exactly_one_attempt(self):
        fetcher = FixtureFetcher({_URL: "<html><body>hi</body></html>"})
        router = AcquisitionRouter(http_fetcher=fetcher)
        result, attempts = router.acquire_with_attempts(_URL)
        self.assertTrue(result.ok)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].tier, AcquisitionTier.T0_DIRECT)
        self.assertTrue(attempts[0].success)
        self.assertGreaterEqual(attempts[0].latency_seconds, 0.0)

    def test_t0_fail_then_t2_success_records_both_attempts_in_order(self):
        fetcher = FixtureFetcher({})
        plugin = _FakePlugin(AcquisitionTier.T2_BROWSER_RENDERED)
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])
        result, attempts = router.acquire_with_attempts(_URL)
        self.assertTrue(result.ok)
        self.assertEqual([a.tier for a in attempts],
                        [AcquisitionTier.T0_DIRECT, AcquisitionTier.T2_BROWSER_RENDERED])
        self.assertFalse(attempts[0].success)
        self.assertTrue(attempts[1].success)

    def test_skipped_tier_no_plugin_gets_no_attempt_record(self):
        fetcher = FixtureFetcher({})
        plugin = _FakePlugin(AcquisitionTier.T3_PUBLIC_NETWORK, succeeds=False)
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])
        _result, attempts = router.acquire_with_attempts(_URL)
        tiers_seen = {a.tier for a in attempts}
        self.assertIn(AcquisitionTier.T0_DIRECT, tiers_seen)
        self.assertIn(AcquisitionTier.T3_PUBLIC_NETWORK, tiers_seen)
        self.assertNotIn(AcquisitionTier.T1_STRUCTURED, tiers_seen)
        self.assertNotIn(AcquisitionTier.T2_BROWSER_RENDERED, tiers_seen)

    def test_acquire_and_acquire_with_attempts_agree_on_final_result(self):
        fetcher = FixtureFetcher({_URL: "<html><body>hi</body></html>"})
        router_a = AcquisitionRouter(http_fetcher=fetcher)
        router_b = AcquisitionRouter(http_fetcher=fetcher)
        plain_result = router_a.acquire(_URL)
        verbose_result, _attempts = router_b.acquire_with_attempts(_URL)
        self.assertEqual(plain_result.status, verbose_result.status)
        self.assertEqual(plain_result.acquisition_method, verbose_result.acquisition_method)


if __name__ == "__main__":
    unittest.main()
