"""Anime Fanfic Production Canary — chinh sach nguon da khao sat that."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from server.scraper.run_state import MockScrapeRunStore
from server.scraper.site_registry import SiteConfig
from server.scraper.source_policy import (
    SourcePolicyBlockedError,
    SourcePolicyClass,
    assert_source_not_blocked,
    check_source_policy,
)
from server.scraper_ops_service import ScraperOpsService


class CheckSourcePolicyTest(unittest.TestCase):
    def test_domain_chua_khao_sat_tra_ve_none(self):
        self.assertIsNone(check_source_policy("https://mot-domain-la.example/x"))

    def test_ao3_la_author_opt_in_required(self):
        record = check_source_policy("https://archiveofourown.org/works/123")
        self.assertEqual(record.policy_class, SourcePolicyClass.AUTHOR_OPT_IN_REQUIRED)

    def test_wattpad_la_policy_blocked(self):
        record = check_source_policy("https://www.wattpad.com/story/123")
        self.assertEqual(record.policy_class, SourcePolicyClass.POLICY_BLOCKED)

    def test_fanfiction_net_la_technically_unstable(self):
        record = check_source_policy("https://www.fanfiction.net/s/123/1/T")
        self.assertEqual(record.policy_class, SourcePolicyClass.TECHNICALLY_UNSTABLE)

    def test_khop_ca_www_prefix(self):
        record = check_source_policy("https://www.archiveofourown.org/works/123")
        self.assertIsNotNone(record)


class AssertSourceNotBlockedTest(unittest.TestCase):
    def test_domain_chan_nem_loi_ro_rang(self):
        with self.assertRaises(SourcePolicyBlockedError):
            assert_source_not_blocked("https://www.wattpad.com/story/123")

    def test_domain_chua_biet_khong_nem_loi(self):
        assert_source_not_blocked("https://mot-domain-la.example/x")  # khong nem gi


class ScraperOpsServiceRejectsBlockedSourceTest(unittest.TestCase):
    def test_discover_tu_choi_domain_da_biet_chan_truoc_khi_fetch(self):
        svc = ScraperOpsService(MockScrapeRunStore())
        with self.assertRaises(SourcePolicyBlockedError):
            svc.discover("https://www.wattpad.com/story/123")

    def test_confirm_unknown_source_tu_choi_domain_da_biet_chan(self):
        svc = ScraperOpsService(MockScrapeRunStore())
        with self.assertRaises(SourcePolicyBlockedError):
            svc.confirm_unknown_source("https://archiveofourown.org/works/123")

    def test_domain_hop_le_van_di_qua_binh_thuong(self):
        fake_cfg = {"nguon-hop-le.example": SiteConfig(
            domain="nguon-hop-le.example", chapter_href_pattern=r"/ch-\d+")}
        svc = ScraperOpsService(MockScrapeRunStore())
        with patch.dict("server.scraper.site_registry._REGISTRY", fake_cfg):
            # Khong nem SourcePolicyBlockedError — co the that bai vi ly do
            # khac (khong fetch that duoc trong test), nhung KHONG phai vi
            # bi chan chinh sach.
            try:
                svc.discover("https://nguon-hop-le.example/truyen/x")
            except SourcePolicyBlockedError:
                self.fail("domain hop le khong duoc bi chan boi source_policy")
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
