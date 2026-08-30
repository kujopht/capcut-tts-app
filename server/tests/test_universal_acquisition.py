import unittest

from server.scraper.universal.acquisition import (
    AcquisitionError, AcquisitionMethod, AcquisitionResult, AcquisitionStatus,
    NetworkEndpointCandidate, SourceClass,
)


class AcquisitionResultTest(unittest.TestCase):
    def test_minimal_construction_defaults_are_empty_not_none_for_collections(self):
        r = AcquisitionResult(
            final_url="https://example.com/x", source_type=SourceClass.GENERIC_WEB,
            status=AcquisitionStatus.OK, acquisition_method=AcquisitionMethod.DIRECT_HTTP)
        self.assertEqual(r.metadata, {})
        self.assertEqual(r.links, [])
        self.assertEqual(r.media_references, [])
        self.assertEqual(r.network_endpoints, [])
        self.assertEqual(r.errors, [])
        self.assertIsNone(r.html)
        self.assertIsNone(r.structured_json)
        self.assertIsNone(r.text_markdown)

    def test_ok_property_true_for_ok_and_not_modified(self):
        for status in (AcquisitionStatus.OK, AcquisitionStatus.NOT_MODIFIED):
            r = AcquisitionResult(final_url="u", source_type=SourceClass.UNKNOWN,
                                  status=status, acquisition_method=AcquisitionMethod.PLUGIN)
            self.assertTrue(r.ok)

    def test_ok_property_false_for_failed_blocked_partial(self):
        for status in (AcquisitionStatus.FAILED, AcquisitionStatus.BLOCKED,
                      AcquisitionStatus.PARTIAL):
            r = AcquisitionResult(final_url="u", source_type=SourceClass.UNKNOWN,
                                  status=status, acquisition_method=AcquisitionMethod.PLUGIN)
            self.assertFalse(r.ok)

    def test_does_not_force_html_can_be_pure_structured_json(self):
        r = AcquisitionResult(
            final_url="https://api.example.com/v", source_type=SourceClass.YOUTUBE,
            status=AcquisitionStatus.OK, acquisition_method=AcquisitionMethod.STRUCTURED_API,
            structured_json={"title": "x"})
        self.assertIsNone(r.html)
        self.assertEqual(r.structured_json, {"title": "x"})

    def test_network_endpoint_candidate_and_error_are_plain_dataclasses(self):
        cand = NetworkEndpointCandidate(url="https://example.com/api/v1", discovered_via="xhr")
        err = AcquisitionError(stage="fetch", message="timeout")
        r = AcquisitionResult(
            final_url="u", source_type=SourceClass.GENERIC_WEB,
            status=AcquisitionStatus.PARTIAL, acquisition_method=AcquisitionMethod.BROWSER_RENDER,
            network_endpoints=[cand], errors=[err])
        self.assertEqual(r.network_endpoints[0].url, "https://example.com/api/v1")
        self.assertTrue(r.errors[0].recoverable)


if __name__ == "__main__":
    unittest.main()
