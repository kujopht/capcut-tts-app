"""FanFicFareProvider — fixture-based regression tests.

`fanficfare_sample.epub` (server/tests/fixtures/scraper/) is a small,
hand-built but structurally real EPUB matching exactly what the real
`fanficfare` CLI produces (same OPF/spine/manifest shape verified against
a real acquisition in docs/reports/fanficfare-real-proof-2026-09-02.md) —
2 chapters, one clean, one carrying FanFicFare's own real
"(CHAPTER ERROR)" marker (the shape a browser-cache-only partial
acquisition produces, per the fetcher-options proof report). These tests
never invoke the real `fanficfare` binary or network — they exercise the
parsing/normalization/resolver logic in isolation, so they stay green
without Java/JDK/network/the CLI installed.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from server.scraper.fanficfare_provider import (
    _DEFAULT_BLOCKED_HOSTS, normalize_fanficfare_result, parse_fanficfare_epub,
    resolve_acquisition_route,
)

FIXTURE = Path(__file__).parent / "fixtures" / "scraper" / "fanficfare_sample.epub"


class ParseEpubTest(unittest.TestCase):
    def test_metadata_va_thu_tu_chuong_dung(self):
        acq = parse_fanficfare_epub(FIXTURE)
        self.assertEqual(acq.title, "Test Story Fixture")
        self.assertEqual(acq.author, "TestAuthor")
        self.assertEqual(acq.source_url, "https://example.com/story/12345")
        self.assertEqual(acq.external_updated_at, "2026-08-01")
        self.assertIn("naruto", acq.tags)
        self.assertEqual(len(acq.chapters), 2)
        self.assertEqual(acq.chapters[0].order_index, 1)
        self.assertEqual(acq.chapters[1].order_index, 2)

    def test_title_page_khong_bi_tinh_la_chuong(self):
        acq = parse_fanficfare_epub(FIXTURE)
        titles = [c.title for c in acq.chapters]
        self.assertNotIn("Test Story Fixture", titles)

    def test_chuong_sach_giu_nguyen_noi_dung(self):
        acq = parse_fanficfare_epub(FIXTURE)
        self.assertIn("Naruto walked into the village", acq.chapters[0].content)
        self.assertIn("Hinata", acq.chapters[0].content)

    def test_chuong_loi_giu_nguyen_marker_khong_am_tham_bo_qua(self):
        """A CHAPTER ERROR marker (real behavior under browser-cache-only
        mode, see fetcher-options proof report) must survive parsing
        intact — the caller decides what to do with it, this function
        never hides a partial acquisition as if it were complete."""
        acq = parse_fanficfare_epub(FIXTURE)
        self.assertIn("CHAPTER ERROR", acq.chapters[1].title)


class NormalizeTest(unittest.TestCase):
    def test_chuyen_sang_dung_hinh_dang_novel_chapter_payload(self):
        acq = parse_fanficfare_epub(FIXTURE)
        result = normalize_fanficfare_result(
            acq, owner_id="svc_harvester", fandom_names=["Naruto"])
        self.assertEqual(result["novel"]["title"], "Test Story Fixture")
        self.assertEqual(result["novel"]["external_source_url"],
                          "https://example.com/story/12345")
        self.assertEqual(result["novel"]["external_author_name"], "TestAuthor")
        self.assertEqual(result["novel"]["fandom_names"], ["Naruto"])
        self.assertEqual(len(result["chapters"]), 2)
        self.assertEqual(result["chapters"][0]["order_index"], 1)
        self.assertTrue(result["chapters"][0]["content_hash"])
        self.assertTrue(result["source_fingerprint"])

    def test_source_fingerprint_on_dinh_cho_cung_url(self):
        acq = parse_fanficfare_epub(FIXTURE)
        r1 = normalize_fanficfare_result(acq, owner_id="x", fandom_names=[])
        r2 = normalize_fanficfare_result(acq, owner_id="x", fandom_names=[])
        self.assertEqual(r1["source_fingerprint"], r2["source_fingerprint"])


class ResolverTest(unittest.TestCase):
    def test_host_khong_ho_tro_di_ve_engine(self):
        with mock.patch(
            "server.scraper.fanficfare_provider.fanficfare_supports_hostname",
            return_value=False,
        ):
            self.assertEqual(
                resolve_acquisition_route("https://narutofanon.fandom.com/wiki/X"),
                "engine")

    def test_host_ho_tro_binh_thuong_di_thang_fanficfare(self):
        with mock.patch(
            "server.scraper.fanficfare_provider.fanficfare_supports_hostname",
            return_value=True,
        ):
            self.assertEqual(
                resolve_acquisition_route("https://www.wattpad.com/story/1"),
                "fanficfare")

    def test_ffn_ao3_bi_chan_mac_dinh_khong_co_cache(self):
        with mock.patch(
            "server.scraper.fanficfare_provider.fanficfare_supports_hostname",
            return_value=True,
        ), mock.patch(
            "server.scraper.fanficfare_provider._browser_cache_path",
            return_value=None,
        ):
            for host in _DEFAULT_BLOCKED_HOSTS:
                self.assertEqual(
                    resolve_acquisition_route(f"https://{host}/s/1"), "engine",
                    f"{host} phai roi ve engine khi khong co browser cache")

    def test_ffn_ao3_dung_browser_cache_khi_co_that(self):
        with mock.patch(
            "server.scraper.fanficfare_provider.fanficfare_supports_hostname",
            return_value=True,
        ), mock.patch(
            "server.scraper.fanficfare_provider._browser_cache_path",
            return_value=Path("."),
        ):
            for host in _DEFAULT_BLOCKED_HOSTS:
                self.assertEqual(
                    resolve_acquisition_route(f"https://{host}/s/1"),
                    "browser_cache_fallback")

    def test_browser_cache_path_rong_tra_ve_none(self):
        from server.scraper.fanficfare_provider import _browser_cache_path

        with mock.patch.dict(os.environ, {"FAS_FANFICFARE_BROWSER_CACHE_PATH": ""}):
            self.assertIsNone(_browser_cache_path())

    def test_browser_cache_path_khong_ton_tai_tra_ve_none(self):
        from server.scraper.fanficfare_provider import _browser_cache_path

        with mock.patch.dict(
            os.environ,
            {"FAS_FANFICFARE_BROWSER_CACHE_PATH": r"C:\does\not\exist\anywhere"},
        ):
            self.assertIsNone(_browser_cache_path())


class FailureClassificationTest(unittest.TestCase):
    def test_phan_loai_loi_that_tu_hai_bao_cao_proof(self):
        from server.scraper.fanficfare_provider import _classify_cli_failure

        self.assertEqual(_classify_cli_failure(
            "fanficfare.exceptions.HTTPErrorFFF: HTTP Error in FFF "
            "'403 Client Error: Forbidden for url: ...'(403)"), "blocked")
        self.assertEqual(_classify_cli_failure(
            "Login Failed on non-interactive process."), "login_required")
        self.assertEqual(_classify_cli_failure(
            "HTTP Error in FFF 'Page not found or expired in Browser Cache "
            "(see FFF setting browser_cache_age_limit)'(428)"), "cache_miss")
        self.assertEqual(_classify_cli_failure("some other traceback"), "failed")


class NoCloudscraperOrBrowserLaunchTest(unittest.TestCase):
    """Static guard: this module must never USE cloudscraper or launch a
    browser, matching the standing production policy. Checks the actual
    dangerous constructs (the `use_cloudscraper` config key, an
    `import cloudscraper`/selenium/playwright, a webdriver reference) —
    not the bare word "cloudscraper", which legitimately appears in the
    module's own docstring explaining why it is NOT used. A grep-shaped
    test rather than a runtime one on purpose — the point is to catch
    the mistake at review/commit time even if no other test happens to
    exercise the offending code path."""

    def test_khong_dung_cloudscraper_hay_selenium_trong_module(self):
        """Checks USAGE patterns, not identifier mentions — this module's
        comments legitimately name `use_cloudscraper`/selenium repeatedly
        while explaining why they are absent, so a bare substring check
        on the whole file would (and did, before this was narrowed)
        false-positive on its own documentation."""
        src = Path(__file__).parent.parent / "scraper" / "fanficfare_provider.py"
        text = src.read_text(encoding="utf-8").lower()
        self.assertNotIn("use_cloudscraper:true", text)
        self.assertNotIn("import cloudscraper", text)
        self.assertNotIn("import selenium", text)
        self.assertNotIn("webdriver.", text)
        self.assertNotIn("playwright.", text)
        self.assertNotIn("subprocess.popen", text)  # no background browser launch


if __name__ == "__main__":
    unittest.main()
