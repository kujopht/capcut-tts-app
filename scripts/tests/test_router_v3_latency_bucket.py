"""Phân loại độ trễ theo bucket — Router LTS.

Kiểm tra phân loại dùng `latency_bucket.bucket`: ba bucket rõ ràng và
đúng các giá trị biên 30 và 120.
"""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.latency_bucket import bucket


class LatencyBucketTest(unittest.TestCase):
    def test_duoi_30_la_fast(self):
        self.assertEqual(bucket(0), "fast")
        self.assertEqual(bucket(10.5), "fast")
        self.assertEqual(bucket(29.999), "fast")

    def test_tu_30_den_duoi_120_la_normal(self):
        self.assertEqual(bucket(30), "normal")
        self.assertEqual(bucket(75), "normal")
        self.assertEqual(bucket(119.999), "normal")

    def test_tu_120_tro_len_la_slow(self):
        self.assertEqual(bucket(120.5), "slow")
        self.assertEqual(bucket(300), "slow")

    def test_bien_30_la_normal(self):
        self.assertEqual(bucket(30), "normal")

    def test_bien_120_la_slow(self):
        self.assertEqual(bucket(120), "slow")


if __name__ == "__main__":
    unittest.main()
