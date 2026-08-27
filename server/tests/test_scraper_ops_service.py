"""
Kiem thu `server/scraper_ops_service.py` — tang dich vu noi site_registry,
pipeline, va `ScrapeRunService` gap nhau cho API quan tri. Dung
`FixtureFetcher` (khong cham mang that) + mot domain gia da dang ky tam
thoi vao `site_registry._REGISTRY`.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.run_state import MockScrapeRunStore, ScrapeRunStatus
from server.scraper.site_registry import SiteConfig
from server.scraper_ops_service import (
    ScraperOpsService,
    ScrapeRunNotFoundError,
    UnsupportedSiteError,
)

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "scraper")


def _doc_fixture(ten: str) -> str:
    with open(os.path.join(_FIXTURES, ten), encoding="utf-8") as f:
        return f.read()


_BASE = "https://ops-test.example"
_PAGES = {
    f"{_BASE}/truyen/thu-nghiem": _doc_fixture("index.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-1": _doc_fixture("chuong-1.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-2": _doc_fixture("chuong-2.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-3": _doc_fixture("chuong-3.html"),
}

_FAKE_CFG = {
    "ops-test.example": SiteConfig(
        domain="ops-test.example", chapter_href_pattern=r"/chuong-\d+",
        title_suffix_to_strip=" - Trang Web Giả"),
}


def _fixture_fetcher_factory():
    return FixtureFetcher(dict(_PAGES))


def _svc(store=None) -> ScraperOpsService:
    return ScraperOpsService(store or MockScrapeRunStore(),
                             fetcher_factory=_fixture_fetcher_factory)


class UnsupportedSiteTest(unittest.TestCase):
    def test_domain_chua_cau_hinh_bao_loi_ro_rang(self):
        svc = _svc()
        with self.assertRaises(UnsupportedSiteError):
            svc.discover("https://khong-ho-tro.example/x")


class DiscoverAndRunTest(unittest.TestCase):
    @patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG)
    def test_discover_xem_truoc_khong_ghi_gi(self):
        store = MockScrapeRunStore()
        svc = _svc(store)
        result = svc.discover(f"{_BASE}/truyen/thu-nghiem")
        self.assertTrue(result["supported"])
        self.assertEqual(result["run"].estimated_total, 3)
        self.assertEqual(len(store.runs), 0, "discover() là dry-run, không được tạo run")

    @patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG)
    def test_start_roi_drive_den_hoan_tat(self):
        store = MockScrapeRunStore()
        svc = _svc(store)
        started = svc.start_or_continue(f"{_BASE}/truyen/thu-nghiem")
        run_id = started["run"].run_id
        self.assertEqual(started["progress"]["estimated_total"], 3)

        driven = svc.drive(run_id)
        self.assertEqual(driven["run"].status, ScrapeRunStatus.COMPLETED)
        self.assertEqual(driven["counts"]["review_ready"], 3)

    @patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG)
    def test_view_va_list_runs(self):
        store = MockScrapeRunStore()
        svc = _svc(store)
        started = svc.start_or_continue(f"{_BASE}/truyen/thu-nghiem")
        run_id = started["run"].run_id
        svc.drive(run_id)

        view = svc.view(run_id)
        self.assertEqual(len(view["items"]), 3)

        listed = svc.list_runs()
        self.assertEqual(len(listed["runs"]), 1)
        self.assertIn("ops-test.example", listed["supported_domains"])

    @patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG)
    def test_view_run_khong_ton_tai_bao_loi_ro(self):
        svc = _svc()
        with self.assertRaises(ScrapeRunNotFoundError):
            svc.view("scr_khong_ton_tai")

    @patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG)
    def test_skip_va_cancel_hoat_dong_qua_tang_dich_vu(self):
        store = MockScrapeRunStore()
        svc = _svc(store)
        started = svc.start_or_continue(f"{_BASE}/truyen/thu-nghiem")
        run_id = started["run"].run_id

        cancelled = svc.cancel(run_id)
        self.assertEqual(cancelled["run"].status, ScrapeRunStatus.CANCEL_REQUESTED)

    @patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG)
    def test_state_duoc_nap_lai_qua_hai_lan_goi_rieng_biet(self):
        """Mo phong DUNG thuc te: moi yeu cau HTTP la MOT ScraperOpsService
        instance moi (khong co gi giu trong bo nho) — resume() van phai
        loc dung chuong da xong o LAN GOI THU HAI."""
        store = MockScrapeRunStore()
        svc1 = _svc(store)
        started = svc1.start_or_continue(f"{_BASE}/truyen/thu-nghiem")
        run_id = started["run"].run_id
        svc1.drive(run_id)

        svc2 = _svc(store)  # instance MOI, giong het request HTTP thu hai
        second_discover = svc2.discover(f"{_BASE}/truyen/thu-nghiem")
        self.assertEqual(
            second_discover["run"].already_done_count, 3,
            "state không được nạp lại đúng ở request thứ hai — resume() không thấy 3 chương đã xong")


if __name__ == "__main__":
    unittest.main()
