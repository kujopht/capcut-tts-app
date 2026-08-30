"""
Unit tests for the end-to-end V5 Web Fiction pipeline scenario.
"""
from __future__ import annotations

import unittest

from server.scraper.universal.change_detection import UnitChangeKind
from server.scraper.universal.e2e_web_fiction import run_scenario


class TestUniversalE2EWebFiction(unittest.TestCase):
    def test_run_scenario_two_rounds(self):
        result = run_scenario()

        # Round 1 assertions
        r1 = result["round1"]
        self.assertIn("round1", result)
        self.assertIn("round2", result)

        self.assertEqual(len(r1["unit_urls"]), 2)
        chuong1_url = "https://example.com/truyen/test-story/chuong-1"
        chuong2_url = "https://example.com/truyen/test-story/chuong-2"
        chuong3_url = "https://example.com/truyen/test-story/chuong-3"

        self.assertEqual(r1["kinds_by_url"][chuong1_url], UnitChangeKind.NEW_UNIT.value)
        self.assertEqual(r1["kinds_by_url"][chuong2_url], UnitChangeKind.NEW_UNIT.value)
        self.assertEqual(r1["counts"][UnitChangeKind.NEW_UNIT.value], 2)

        # Round 2 assertions
        r2 = result["round2"]
        self.assertEqual(len(r2["unit_urls"]), 3)

        # chuong-1 text is unchanged -> UNCHANGED
        self.assertEqual(r2["kinds_by_url"][chuong1_url], UnitChangeKind.UNCHANGED.value)

        # chuong-2 text is modified -> UPDATED_UNIT
        self.assertEqual(r2["kinds_by_url"][chuong2_url], UnitChangeKind.UPDATED_UNIT.value)

        # chuong-3 is newly added -> NEW_UNIT
        self.assertEqual(r2["kinds_by_url"][chuong3_url], UnitChangeKind.NEW_UNIT.value)

        self.assertEqual(r2["counts"][UnitChangeKind.UNCHANGED.value], 1)
        self.assertEqual(r2["counts"][UnitChangeKind.UPDATED_UNIT.value], 1)
        self.assertEqual(r2["counts"][UnitChangeKind.NEW_UNIT.value], 1)


if __name__ == "__main__":
    unittest.main()
