import unittest

from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.universal.acquisition import (
    AcquisitionMethod, AcquisitionResult, AcquisitionStatus, SourceClass,
)
from server.scraper.universal.document_plugin import (
    NotConfiguredDocumentPlugin, sniff_document_kind,
)
from server.scraper.universal.router import AcquisitionRouter, AcquisitionTier

_URL = "https://example.com/files/doc.pdf"


class NotConfiguredDocumentPluginTest(unittest.TestCase):
    def test_available_is_false(self):
        self.assertFalse(NotConfiguredDocumentPlugin().available())

    def test_plugin_reports_correct_tier_and_name(self):
        plugin = NotConfiguredDocumentPlugin()
        self.assertEqual(plugin.tier, AcquisitionTier.T4_DOCUMENT)
        self.assertEqual(plugin.name, "not_configured_document")

    def test_acquire_returns_failed_result_never_raises(self):
        plugin = NotConfiguredDocumentPlugin()
        result = plugin.acquire(_URL)
        self.assertIsInstance(result, AcquisitionResult)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, AcquisitionStatus.FAILED)
        self.assertEqual(result.acquisition_method, AcquisitionMethod.DOCUMENT)
        self.assertTrue(result.errors)
        self.assertEqual(result.final_url, _URL)

    def test_acquire_honors_source_hint(self):
        plugin = NotConfiguredDocumentPlugin()
        result = plugin.acquire(_URL, source_hint=SourceClass.DOCUMENT)
        self.assertEqual(result.source_type, SourceClass.DOCUMENT)


class RouterIntegrationTest(unittest.TestCase):
    def test_router_skips_unavailable_document_plugin(self):
        fetcher = FixtureFetcher({})
        plugin = NotConfiguredDocumentPlugin()
        router = AcquisitionRouter(http_fetcher=fetcher, plugins=[plugin])
        result = router.acquire(_URL)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, AcquisitionStatus.FAILED)
        self.assertEqual(result.acquisition_method, AcquisitionMethod.DIRECT_HTTP)


class SniffDocumentKindTest(unittest.TestCase):
    def test_pdf_magic_bytes(self):
        self.assertEqual(
            sniff_document_kind("", b"%PDF-1.4\n%\xe2\xe3\xcf\xd3"),
            "pdf")

    def test_html_content_type(self):
        self.assertEqual(
            sniff_document_kind("text/html; charset=utf-8", b"<!DOCTYPE html>"),
            "html")

    def test_html_leading_angle_bracket_without_content_type(self):
        self.assertEqual(sniff_document_kind("", b"<html>"), "html")

    def test_plain_text_content_type(self):
        self.assertEqual(
            sniff_document_kind("text/plain; charset=utf-8", b"hello world"),
            "plain_text")

    def test_unknown_otherwise(self):
        self.assertEqual(sniff_document_kind("", b"\x00\x01\x02"), "unknown")
        self.assertEqual(sniff_document_kind("", b""), "unknown")


if __name__ == "__main__":
    unittest.main()
