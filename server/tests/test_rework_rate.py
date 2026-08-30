import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts/router_v3')))
from rework_rate import rework_rate

class TestReworkRate(unittest.TestCase):
    def test_empty_list(self):
        self.assertEqual(rework_rate([]), 0.0)

    def test_all_true(self):
        records = [
            {"rework_required": True},
            {"rework_required": True},
            {"rework_required": True},
        ]
        self.assertEqual(rework_rate(records), 1.0)

    def test_mixed_records(self):
        records = [
            {"rework_required": True},
            {"rework_required": False},
            {"other_key": 123},
            {"rework_required": True},
        ]
        self.assertEqual(rework_rate(records), 0.5)

if __name__ == '__main__':
    unittest.main()
