"""
Kiem thu `server/scraper/site_registry.py` — dac biet co che thu hep pham
vi theo tung truyen (`scope_id_pattern`/`resolved()`), phat hien qua
review doc lap (Codex) tren cau hinh Royal Road: mot regex dung chung
KHONG thu hep theo truyen co the bat NHAM lien ket sang truyen khac.
"""
from __future__ import annotations

import re
import unittest

from server.scraper.site_registry import ScopeExtractionError, lookup, supported_domains


class WikisourceLookupTest(unittest.TestCase):
    def test_domain_khong_can_thu_hep_pham_vi_van_hoat_dong(self):
        cfg = lookup("https://vi.wikisource.org/wiki/L%E1%BB%81u_ch%C3%B5ng")
        self.assertIsNotNone(cfg)
        self.assertNotIn("{scope_id}", cfg.chapter_href_pattern)


class RoyalRoadScopingTest(unittest.TestCase):
    def test_scope_id_duoc_dien_dung_tu_url(self):
        cfg = lookup("https://www.royalroad.com/fiction/36780/regis-and-charlotte")
        self.assertIn("36780", cfg.chapter_href_pattern)
        self.assertNotIn("{scope_id}", cfg.chapter_href_pattern)

    def test_khong_bat_nham_lien_ket_sang_truyen_khac(self):
        """Ly do THAT SU can co che nay — phat hien qua review Codex."""
        cfg = lookup("https://www.royalroad.com/fiction/36780/regis-and-charlotte")
        pattern = re.compile(cfg.chapter_href_pattern)
        self.assertIsNotNone(
            pattern.search("/fiction/36780/regis-and-charlotte/chapter/570280/chapter-1/"))
        self.assertIsNone(
            pattern.search("/fiction/99999/mot-truyen-khac/chapter/123456/chapter-1/"),
            "regex khong duoc bat lien ket sang truyen co ID khac")

    def test_url_khong_khop_hinh_dang_bao_loi_ro_rang(self):
        """URL dung domain nhung khong phai trang mot truyen cu the (vd
        trang danh sach) — PHAI bao loi ro, khong am tham lui ve pattern
        khong thu hep (se tai hien lai loi bat-nham-truyen-khac)."""
        with self.assertRaises(ScopeExtractionError):
            lookup("https://www.royalroad.com/fictions/complete")


class SupportedDomainsTest(unittest.TestCase):
    def test_danh_sach_domain_ho_tro_khong_rong(self):
        domains = supported_domains()
        self.assertIn("vi.wikisource.org", domains)
        self.assertIn("royalroad.com", domains)


if __name__ == "__main__":
    unittest.main()
