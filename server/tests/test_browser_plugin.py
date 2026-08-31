import unittest

from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.universal.acquisition import (
    AcquisitionMethod, AcquisitionStatus, SourceClass,
)
from server.scraper.universal.browser_plugin import (
    BrowserRenderedPlugin, BrowserRenderResult, NotConfiguredBrowserRenderer,
)
from server.scraper.universal.router import AcquisitionRouter, AcquisitionTier

_URL = "https://example.com/chuong-1"


class _FakeRenderer:
    def __init__(self, result: BrowserRenderResult, *, raise_exc: bool = False) -> None:
        self._result = result
        self._raise_exc = raise_exc
        self.calls = 0

    def render(self, url: str) -> BrowserRenderResult:
        self.calls += 1
        if self._raise_exc:
            raise RuntimeError("renderer crashed")
        return self._result


class NotConfiguredRendererTest(unittest.TestCase):
    def test_plugin_unavailable_by_default(self):
        plugin = BrowserRenderedPlugin()
        self.assertFalse(plugin.available())

    def test_default_renderer_reports_empty_not_challenge(self):
        renderer = NotConfiguredBrowserRenderer()
        result = renderer.render(_URL)
        self.assertEqual(result.html, "")
        self.assertFalse(result.challenge_detected)


class BrowserRenderedPluginSuccessTest(unittest.TestCase):
    def test_real_content_returns_ok(self):
        renderer = _FakeRenderer(BrowserRenderResult(
            final_url=_URL, html="<html>noi dung that</html>",
            visible_text="noi dung that", status_code=200))
        plugin = BrowserRenderedPlugin(renderer=renderer)
        self.assertTrue(plugin.available())
        result = plugin.acquire(_URL, source_hint=SourceClass.WEB_FICTION)
        self.assertTrue(result.ok)
        self.assertEqual(result.acquisition_method, AcquisitionMethod.BROWSER_RENDER)
        self.assertEqual(result.text_markdown, "noi dung that")
        self.assertEqual(renderer.calls, 1)


class BrowserRenderedPluginChallengeTest(unittest.TestCase):
    def test_challenge_detected_returns_blocked_not_ok(self):
        renderer = _FakeRenderer(BrowserRenderResult(
            final_url=_URL, html="<html>captcha page</html>", visible_text="",
            status_code=403, challenge_detected=True))
        plugin = BrowserRenderedPlugin(renderer=renderer)
        result = plugin.acquire(_URL)
        self.assertEqual(result.status, AcquisitionStatus.BLOCKED)
        self.assertFalse(result.ok)
        self.assertTrue(result.errors)


class BrowserRenderedPluginEmptyResultTest(unittest.TestCase):
    def test_empty_html_and_text_returns_failed(self):
        renderer = _FakeRenderer(BrowserRenderResult(
            final_url=_URL, html="", visible_text="", status_code=200))
        plugin = BrowserRenderedPlugin(renderer=renderer)
        result = plugin.acquire(_URL)
        self.assertEqual(result.status, AcquisitionStatus.FAILED)


class BrowserRenderedPluginRendererCrashTest(unittest.TestCase):
    def test_renderer_exception_never_propagates_as_raise(self):
        renderer = _FakeRenderer(
            BrowserRenderResult(final_url=_URL, html="", visible_text=""),
            raise_exc=True)
        plugin = BrowserRenderedPlugin(renderer=renderer)
        result = plugin.acquire(_URL)
        self.assertEqual(result.status, AcquisitionStatus.FAILED)
        self.assertIn("renderer crashed", result.errors[0].message)


class RouterIntegrationTest(unittest.TestCase):
    """A real (no mocking of the router itself) integration proof:
    AcquisitionRouter falls through T0 (which fails via an empty
    FixtureFetcher) to a T2 plugin backed by a fake-but-realistic renderer,
    and the router's own success-tracking/history records T2 as the
    winning tier for this host — exactly the escalation behaviour the
    mission requires."""

    def test_router_falls_through_t0_to_t2_and_succeeds(self):
        fetcher = FixtureFetcher({})  # T0 has nothing -> fails
        renderer = _FakeRenderer(BrowserRenderResult(
            final_url=_URL, html="<html>chuong that</html>",
            visible_text="chuong that", status_code=200))
        plugin = BrowserRenderedPlugin(renderer=renderer)
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])

        result = router.acquire(_URL, source_hint=SourceClass.WEB_FICTION)

        self.assertTrue(result.ok)
        self.assertEqual(result.acquisition_method, AcquisitionMethod.BROWSER_RENDER)
        self.assertEqual(router.preferred_tier(_URL), AcquisitionTier.T2_BROWSER_RENDERED)

    def test_router_reports_blocked_challenge_not_ok_even_as_only_tier(self):
        fetcher = FixtureFetcher({})
        renderer = _FakeRenderer(BrowserRenderResult(
            final_url=_URL, html="", visible_text="", challenge_detected=True))
        plugin = BrowserRenderedPlugin(renderer=renderer)
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])

        result = router.acquire(_URL)

        self.assertFalse(result.ok)
        self.assertEqual(result.status, AcquisitionStatus.BLOCKED)


if __name__ == "__main__":
    unittest.main()
