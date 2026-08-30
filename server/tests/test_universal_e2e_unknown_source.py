import unittest

from server.scraper.universal.e2e_unknown_source import run_scenario


class E2EUnknownSourceTest(unittest.TestCase):
    def test_two_consistent_fixtures_promote_to_trusted_adapter(self):
        result = run_scenario()
        self.assertEqual(result["proposed_fields"], {"title": "h1", "author": ".author"})
        self.assertEqual(result["pages_validated"], 2)
        self.assertEqual(result["pages_fully_matched"], 2)
        self.assertTrue(result["promoted"])

    def test_mismatched_third_fixture_prevents_promotion(self):
        result = run_scenario(mismatched_third_fixture=True)
        self.assertEqual(result["pages_validated"], 3)
        self.assertEqual(result["pages_fully_matched"], 2)
        self.assertFalse(result["promoted"])

    def test_fingerprint_signature_present(self):
        result = run_scenario()
        self.assertTrue(result["fingerprint_signature"])


if __name__ == "__main__":
    unittest.main()
