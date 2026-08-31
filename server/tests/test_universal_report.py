import unittest

from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.universal.acquisition import (
    AcquisitionMethod, AcquisitionResult, AcquisitionStatus, SourceClass,
)
from server.scraper.universal.browser_plugin import BrowserRenderedPlugin, BrowserRenderResult
from server.scraper.universal.report import build_report
from server.scraper.universal.router import (
    AcquisitionPlugin, AcquisitionRouter, AcquisitionTier,
)

_URL = "https://example.com/story/1"
_REAL_TEXT = (
    "Day la mot doan van ban that su dai va co nhieu cau van hoan chinh. "
    "No khong phai la mot danh sach dieu huong hay mot trang trong. "
    "Cau nay them do dai de vuot qua nguong toi thieu can thiet cho kiem tra."
)


class _FakeRenderer:
    def __init__(self, result: BrowserRenderResult) -> None:
        self._result = result

    def render(self, url: str) -> BrowserRenderResult:
        return self._result


class BuildReportT0SuccessTest(unittest.TestCase):
    def test_t0_success_report_has_one_attempt_and_real_hash(self):
        fetcher = FixtureFetcher({_URL: _REAL_TEXT})
        router = AcquisitionRouter(http_fetcher=fetcher)
        report = build_report(router, _URL)

        self.assertEqual(len(report.tier_attempts), 1)
        self.assertEqual(report.tier_selected, AcquisitionTier.T0_DIRECT)
        self.assertEqual(report.final_status, AcquisitionStatus.OK)
        self.assertTrue(report.content_hash)
        self.assertIsNotNone(report.validation_score)
        self.assertIn("T0", report.fallback_reason)


class BuildReportEscalationTest(unittest.TestCase):
    """The mission's explicit escalation rule: a T0 failure alone must
    never be reported as a final block - the report must show the
    escalation to T2 and its success."""

    def test_t0_fail_t2_success_narrates_escalation_not_block(self):
        fetcher = FixtureFetcher({})  # T0 has nothing -> fails
        renderer = _FakeRenderer(BrowserRenderResult(
            final_url=_URL, html="<html>noi dung</html>",
            visible_text=_REAL_TEXT, status_code=200))
        plugin = BrowserRenderedPlugin(renderer=renderer)
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])

        report = build_report(router, _URL)

        self.assertEqual(len(report.tier_attempts), 2)
        self.assertEqual(report.tier_attempts[0].tier, AcquisitionTier.T0_DIRECT)
        self.assertFalse(report.tier_attempts[0].success)
        self.assertEqual(report.tier_attempts[1].tier, AcquisitionTier.T2_BROWSER_RENDERED)
        self.assertTrue(report.tier_attempts[1].success)
        self.assertEqual(report.tier_selected, AcquisitionTier.T2_BROWSER_RENDERED)
        self.assertEqual(report.final_status, AcquisitionStatus.OK)
        self.assertIn("KHONG bi coi la", report.fallback_reason)
        self.assertIn("leo thang", report.fallback_reason)
        self.assertTrue(report.content_hash)


class BuildReportBlockedTest(unittest.TestCase):
    def test_challenge_detected_reports_blocked_not_generic_failed(self):
        fetcher = FixtureFetcher({})
        renderer = _FakeRenderer(BrowserRenderResult(
            final_url=_URL, html="", visible_text="", challenge_detected=True))
        plugin = BrowserRenderedPlugin(renderer=renderer)
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])

        report = build_report(router, _URL)

        self.assertEqual(report.final_status, AcquisitionStatus.BLOCKED)
        self.assertIsNone(report.tier_selected)
        self.assertEqual(report.content_hash, "")
        self.assertIsNone(report.validation_score)
        self.assertIn("CAPTCHA", report.fallback_reason)


class BuildReportAllFailTest(unittest.TestCase):
    def test_no_tiers_available_reports_failed_with_narrative(self):
        fetcher = FixtureFetcher({})
        router = AcquisitionRouter(http_fetcher=fetcher)
        report = build_report(router, _URL)

        self.assertEqual(report.final_status, AcquisitionStatus.FAILED)
        self.assertIsNone(report.tier_selected)
        self.assertEqual(report.content_hash, "")
        self.assertTrue(report.fallback_reason)


class BuildReportTwoDistinctPagesTest(unittest.TestCase):
    """Mission requirement: distinct pages produce distinct hashes."""

    def test_two_distinct_real_texts_get_distinct_hashes(self):
        url_a, url_b = "https://example.com/a", "https://example.com/b"
        fetcher = FixtureFetcher({
            url_a: _REAL_TEXT,
            url_b: _REAL_TEXT + " Doan van ban thu hai khac han doan dau tien ve noi dung.",
        })
        router = AcquisitionRouter(http_fetcher=fetcher)
        report_a = build_report(router, url_a)
        report_b = build_report(router, url_b)
        self.assertNotEqual(report_a.content_hash, report_b.content_hash)


if __name__ == "__main__":
    unittest.main()
