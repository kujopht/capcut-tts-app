"""Lớp năng lực chuyên biệt — Router LTS Phase 12."""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.registry import CAPABILITIES
from scripts.router_v3.specialist_capabilities import CAC_LOP, tra_cuu


class LopChuyenBietTest(unittest.TestCase):
    def test_moi_lop_co_nang_luc_hop_le_trong_CAPABILITIES(self):
        for lop in CAC_LOP:
            self.assertIn(lop.nang_luc, CAPABILITIES)

    def test_tra_cuu_dung(self):
        self.assertEqual(tra_cuu("security_reviewer").nang_luc, "security_reviewer")

    def test_tra_cuu_sai_ten_nem_KeyError(self):
        with self.assertRaises(KeyError):
            tra_cuu("khong_ton_tai")

    def test_du_sau_lop_theo_mission(self):
        ten = {lop.ten for lop in CAC_LOP}
        self.assertEqual(ten, {"frontend_prototyper", "research_agent",
                              "scraping_agent", "security_reviewer",
                              "test_generator", "media_agent"})

    def test_lovable_KHONG_phai_worker_bat_buoc(self):
        """Lovable chi la mot NHAN tuy chon (frontend_prototyper), khong co
        adapter/lop rieng ten "lovable" nao trong module nay."""
        ten = {lop.ten for lop in CAC_LOP}
        self.assertNotIn("lovable", ten)


if __name__ == "__main__":
    unittest.main()
