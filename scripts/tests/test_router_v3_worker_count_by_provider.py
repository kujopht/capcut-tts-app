"""Đếm worker theo nhà cung cấp từ snapshot — Router V3."""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.worker_count_by_provider import count_by_provider


class CountByProviderTest(unittest.TestCase):
    def test_nhieu_hang_hai_nha_cung_cap_dem_dung(self):
        rows = [
            {"provider": "antigravity", "worker_id": "AG01"},
            {"provider": "antigravity", "worker_id": "AG02"},
            {"provider": "antigravity", "worker_id": "AG03"},
            {"provider": "codex", "worker_id": "CX01"},
            {"provider": "codex", "worker_id": "CX02"},
        ]
        self.assertEqual(
            count_by_provider(rows),
            {"antigravity": 3, "codex": 2},
        )

    def test_danh_sach_rong_tra_dict_rong(self):
        self.assertEqual(count_by_provider([]), {})


if __name__ == "__main__":
    unittest.main()
