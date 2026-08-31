"""Anime Fanfic source policy — mo hinh hai truc (Owner Policy Update 2026-08-31):
`TechnicalAccess` la cong that, `RightsRisk` chi la sieu du lieu."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from server.scraper.run_state import MockScrapeRunStore
from server.scraper.site_registry import SiteConfig
from server.scraper.source_policy import (
    RightsRisk,
    SourcePolicyBlockedError,
    TechnicalAccess,
    assert_source_not_blocked,
    check_source_policy,
)
from server.scraper_ops_service import ScraperOpsService


class CheckSourcePolicyTest(unittest.TestCase):
    def test_domain_chua_khao_sat_tra_ve_none(self):
        self.assertIsNone(check_source_policy("https://mot-domain-la.example/x"))

    def test_khop_ca_www_prefix(self):
        record = check_source_policy("https://www.archiveofourown.org/works/123")
        self.assertIsNotNone(record)


class TosProhibitsAutomationGateTest(unittest.TestCase):
    """Co nay CHAN BAT KE RightsRisk — day la ranh gioi truy cap cua BEN
    THU BA, khong phai cau hoi quyen noi dung Owner Policy Update dieu
    chinh."""

    def test_wattpad_tos_cam_tu_dong_hoa_van_chan(self):
        with self.assertRaises(SourcePolicyBlockedError):
            assert_source_not_blocked("https://www.wattpad.com/story/123")

    def test_royalroad_tos_cam_van_chan_du_technical_access_la_public_direct(self):
        record = check_source_policy("https://www.royalroad.com/fiction/1/x")
        self.assertEqual(record.technical_access, TechnicalAccess.PUBLIC_DIRECT)
        self.assertTrue(record.tos_prohibits_automation)
        with self.assertRaises(SourcePolicyBlockedError):
            assert_source_not_blocked("https://www.royalroad.com/fiction/1/x")

    def test_questionable_questing_reachable_nhung_van_chan_vi_tos(self):
        """Nguon XenForo DUY NHAT tai duoc that (PUBLIC_DIRECT) — nhung ToS
        cam ro rang 'spidering, crawling, or scraping' nen VAN chan."""
        record = check_source_policy(
            "https://forum.questionablequesting.com/forums/creative-writing.5/")
        self.assertEqual(record.technical_access, TechnicalAccess.PUBLIC_DIRECT)
        self.assertTrue(record.tos_prohibits_automation)
        with self.assertRaises(SourcePolicyBlockedError):
            assert_source_not_blocked(
                "https://forum.questionablequesting.com/forums/creative-writing.5/")

    def test_narou_api_chinh_thuc_cam_van_chan_du_reachable(self):
        record = check_source_policy("https://syosetu.com/")
        self.assertEqual(record.technical_access, TechnicalAccess.PUBLIC_DIRECT)
        self.assertTrue(record.tos_prohibits_automation)
        with self.assertRaises(SourcePolicyBlockedError):
            assert_source_not_blocked("https://syosetu.com/")


class TechnicalAccessGateTest(unittest.TestCase):
    """Cong nay CHAN theo kha nang tiep can KY THUAT — doc lap voi
    RightsRisk (khong bao gio la dieu kien o day nua)."""

    def test_access_denied_van_chan(self):
        with self.assertRaises(SourcePolicyBlockedError):
            assert_source_not_blocked("https://archiveofourown.org/works/123")

    def test_ffn_access_denied_du_tos_khong_cam(self):
        record = check_source_policy("https://www.fanfiction.net/s/123/1/T")
        self.assertFalse(record.tos_prohibits_automation)
        self.assertEqual(record.technical_access, TechnicalAccess.ACCESS_DENIED)
        with self.assertRaises(SourcePolicyBlockedError):
            assert_source_not_blocked("https://www.fanfiction.net/s/123/1/T")

    def test_cac_nguon_access_denied_mo_rong(self):
        for domain in (
            "scribblehub.com", "quotev.com", "forums.spacebattles.com",
            "syosetu.org", "forums.sufficientvelocity.com", "metruyenchu.com",
            "truyenfull.today", "truyen.tangthuvien.vn", "kakuyomu.jp",
        ):
            with self.subTest(domain=domain):
                record = check_source_policy(f"https://{domain}/")
                self.assertEqual(record.technical_access, TechnicalAccess.ACCESS_DENIED)


class DoclnPublicBrowserRenderedTest(unittest.TestCase):
    """docln.net: SUA LAI LAN HAI (2026-08-31) sau khi thuc hien mot phien
    trinh duyet THAT (mcp__claude-in-chrome__*, duong di khach vang lai
    thong thuong, khong dang nhap, khong chen ma giai ma/bo qua CAPTCHA).
    Ket qua: JS GOC cua chinh site tu giai ma noi dung XOR-shuffle vao DOM
    cho MOI khach, KHONG co thu thach/CAPTCHA nao xuat hien — day la Case 1
    (trinh duyet thuong render JS cong khai, hop le), khong phai Case 2.
    Phan loai CAPTCHA_OR_BOT_CHALLENGE truoc do la mot loi phan loai that,
    da nham 'noi dung bi bien doi trong HTML ban dau' voi 'thu thach bot'
    — xem evidence trong source_policy.py de biet chi tiet."""

    def test_docln_khong_con_bi_chan_sau_khi_xac_minh_browser_that(self):
        record = check_source_policy("https://docln.net/truyen/14376-thien-su-nha-ben")
        self.assertEqual(record.technical_access, TechnicalAccess.PUBLIC_BROWSER_RENDERED)
        self.assertFalse(record.tos_prohibits_automation)
        self.assertEqual(record.rights_risk, RightsRisk.OWNER_ACCEPTED_UNVERIFIED)
        # Khong raise nua - PUBLIC_BROWSER_RENDERED khong nam trong
        # _BLOCKED_TECHNICAL_ACCESS.
        assert_source_not_blocked("https://docln.net/truyen/14376-thien-su-nha-ben")


class ScraperOpsServiceGateCoverageTest(unittest.TestCase):
    def test_discover_tu_choi_domain_chan_truoc_khi_fetch(self):
        svc = ScraperOpsService(MockScrapeRunStore())
        with self.assertRaises(SourcePolicyBlockedError):
            svc.discover("https://www.wattpad.com/story/123")

    def test_confirm_unknown_source_tu_choi_domain_chan(self):
        svc = ScraperOpsService(MockScrapeRunStore())
        with self.assertRaises(SourcePolicyBlockedError):
            svc.confirm_unknown_source("https://archiveofourown.org/works/123")

    def test_start_or_continue_tu_choi_royalroad_du_da_co_trong_site_registry(self):
        svc = ScraperOpsService(MockScrapeRunStore())
        with self.assertRaises(SourcePolicyBlockedError):
            svc.start_or_continue("https://royalroad.com/fiction/12345/mot-truyen")

    def test_domain_hop_le_van_di_qua_binh_thuong(self):
        fake_cfg = {"nguon-hop-le.example": SiteConfig(
            domain="nguon-hop-le.example", chapter_href_pattern=r"/ch-\d+")}
        svc = ScraperOpsService(MockScrapeRunStore())
        with patch.dict("server.scraper.site_registry._REGISTRY", fake_cfg):
            try:
                svc.discover("https://nguon-hop-le.example/truyen/x")
            except SourcePolicyBlockedError:
                self.fail("domain hop le khong duoc bi chan boi source_policy")
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
