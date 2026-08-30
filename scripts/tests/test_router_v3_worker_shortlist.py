"""Bang xep hang worker theo ty le thanh cong — Router LTS Phase 10."""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.worker_shortlist import top_by_success_rate


class XepHangThanhCongTest(unittest.TestCase):
    def test_xep_theo_ty_le_giam_dan(self):
        rows = [
            {"worker_id": "codex", "success_rate": 0.4},
            {"worker_id": "gemini", "success_rate": 0.9},
            {"worker_id": "claude", "success_rate": 0.7},
        ]
        self.assertEqual(top_by_success_rate(rows),
                         ["gemini", "claude", "codex"])

    def test_hai_chang_ty_le_bang_thi_theo_worker_id(self):
        rows = [
            {"worker_id": "zeta", "success_rate": 0.8},
            {"worker_id": "alpha", "success_rate": 0.8},
            {"worker_id": "mid", "success_rate": 0.6},
        ]
        self.assertEqual(top_by_success_rate(rows),
                         ["alpha", "zeta", "mid"])

    def test_n_lon_hon_so_dong_thi_lay_het(self):
        rows = [
            {"worker_id": "a", "success_rate": 0.9},
            {"worker_id": "b", "success_rate": 0.8},
        ]
        self.assertEqual(len(top_by_success_rate(rows, n=5)), 2)

    def test_rong_tra_ve_rong(self):
        self.assertEqual(top_by_success_rate([]), [])


if __name__ == "__main__":
    unittest.main()