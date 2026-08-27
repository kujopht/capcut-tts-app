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

from server.scraper.http_fetcher import FetchError, FixtureFetcher
from server.scraper.run_state import MockScrapeRunStore, ScrapeRunStatus
from server.scraper.site_profile import MockSiteProfileStore, ProfileStatus
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

#: Domain CHUA cau hinh nhung CO NOI DUNG that de UnknownSiteDiscoveryEngine
#: (Phase 2) kham pha — khac voi "khong-ho-tro.example" (khong co trang
#: fixture nao, mo phong URL SAI/khong phan hoi).
_UNKNOWN_BASE = "https://chua-biet.example"
_UNKNOWN_INDEX = f"""
<html><head><title>Truyện Chưa Biết</title>
<meta property="og:title" content="Truyện Chưa Biết">
</head><body>
<ul>
{''.join(f'<li><a href="/truyen/x/chuong-{i}">Chương {i}</a></li>' for i in range(1, 6))}
</ul>
</body></html>
"""
_UNKNOWN_CHAPTER = """
<html><head><title>Chương 1</title></head>
<body><div class="chapter-content">
<p>Đoạn văn bản đầu tiên của chương một, đủ dài để vượt ngưỡng tối thiểu
cho một vùng nội dung hợp lệ trong bộ kiểm tra tích hợp này.</p>
<p>Đoạn văn bản thứ hai để tăng thêm độ dài, tránh bị coi là quá ngắn so
với ngưỡng tối thiểu đã đặt ra cho vùng nội dung.</p>
</div></body></html>
"""
_UNKNOWN_PAGES = {
    f"{_UNKNOWN_BASE}/truyen/x": _UNKNOWN_INDEX,
    f"{_UNKNOWN_BASE}/truyen/x/chuong-1": _UNKNOWN_CHAPTER,
    f"{_UNKNOWN_BASE}/truyen/x/chuong-2": _UNKNOWN_CHAPTER,
    f"{_UNKNOWN_BASE}/truyen/x/chuong-3": _UNKNOWN_CHAPTER,
    f"{_UNKNOWN_BASE}/truyen/x/chuong-4": _UNKNOWN_CHAPTER,
    f"{_UNKNOWN_BASE}/truyen/x/chuong-5": _UNKNOWN_CHAPTER,
}


def _fixture_fetcher_factory():
    return FixtureFetcher({**_PAGES, **_UNKNOWN_PAGES})


def _svc(store=None, profile_store=None) -> ScraperOpsService:
    return ScraperOpsService(store or MockScrapeRunStore(),
                             fetcher_factory=_fixture_fetcher_factory,
                             profile_store=profile_store)


class UnsupportedSiteTest(unittest.TestCase):
    def test_url_khong_tai_duoc_nem_FetchError(self):
        """URL SAI/khong phan hoi (khong co trong fixture) — khac voi domain
        CHUA cau hinh nhung CO noi dung that (xem UnknownSiteDiscoveryTest
        duoi day, hanh vi Phase 2 moi: tra ve de xuat thay vi loi)."""
        svc = _svc()
        with self.assertRaises(FetchError):
            svc.discover("https://khong-ho-tro.example/x")

    def test_start_or_continue_tren_domain_chua_xac_nhan_van_bi_tu_choi(self):
        """`discover()` co the tra ve de xuat cho domain la, nhung
        `start_or_continue()` PHAI van tu choi cho den khi operator xac
        nhan qua `confirm_unknown_source()` — khong duoc bo qua buoc duyet."""
        svc = _svc()
        with self.assertRaises(UnsupportedSiteError):
            svc.start_or_continue(f"{_UNKNOWN_BASE}/truyen/x")


class UnknownSiteDiscoveryTest(unittest.TestCase):
    def test_discover_tren_domain_chua_biet_tra_ve_de_xuat_khong_bao_loi(self):
        svc = _svc()
        result = svc.discover(f"{_UNKNOWN_BASE}/truyen/x")

        self.assertFalse(result["supported"])
        self.assertTrue(result["new_source_detected"])
        self.assertEqual(result["proposal"].chapter_count_estimate, 5)
        self.assertIsNotNone(result["proposal"].chapter_url_pattern)


class ConfirmUnknownSourceTest(unittest.TestCase):
    def test_xac_nhan_luu_SiteProfile_va_start_or_continue_hoat_dong(self):
        profile_store = MockSiteProfileStore()
        svc = _svc(profile_store=profile_store)

        confirmed = svc.confirm_unknown_source(f"{_UNKNOWN_BASE}/truyen/x")
        self.assertEqual(confirmed["profile"].status, ProfileStatus.LEARNING)
        self.assertEqual(profile_store.get("chua-biet.example").status,
                         ProfileStatus.LEARNING)

        started = svc.start_or_continue(f"{_UNKNOWN_BASE}/truyen/x")
        self.assertEqual(started["progress"]["estimated_total"], 5)

    def test_domain_da_co_site_config_tu_choi_xac_nhan(self):
        profile_store = MockSiteProfileStore()
        svc = _svc(profile_store=profile_store)
        with patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG):
            with self.assertRaises(ValueError):
                svc.confirm_unknown_source(f"{_BASE}/truyen/thu-nghiem")


class CheckForUpdatesTest(unittest.TestCase):
    """Phase 9: `check_for_updates` — MOT lan tai trang muc luc, so sanh
    voi state da luu, KHONG tai lai chuong nao da xong."""

    _UPDATE_BASE = "https://cap-nhat.example"
    _CFG = {
        "cap-nhat.example": SiteConfig(
            domain="cap-nhat.example", chapter_href_pattern=r"/chuong-\d+"),
    }

    def _chapter_html(self, so: int) -> str:
        return f"<html><head><title>Chương {so}</title></head><body>nội dung {so}</body></html>"

    def _index_html(self, *so_chuong: int) -> str:
        links = "".join(
            f'<li><a href="/truyen/z/chuong-{i}">Chương {i}</a></li>' for i in so_chuong)
        return f"<html><head><title>Truyện Cập Nhật</title></head><body><ul>{links}</ul></body></html>"

    def _pages(self, *so_chuong: int) -> dict:
        pages = {f"{self._UPDATE_BASE}/truyen/z": self._index_html(*so_chuong)}
        for i in so_chuong:
            pages[f"{self._UPDATE_BASE}/truyen/z/chuong-{i}"] = self._chapter_html(i)
        return pages

    def test_khong_gi_doi_thi_khong_co_thay_doi(self):
        pages = self._pages(1, 2, 3)
        store = MockScrapeRunStore()
        with patch.dict("server.scraper.site_registry._REGISTRY", self._CFG):
            svc = ScraperOpsService(store, fetcher_factory=lambda: FixtureFetcher(dict(pages)))
            started = svc.start_or_continue(f"{self._UPDATE_BASE}/truyen/z")
            run_id = started["run"].run_id
            svc.drive(run_id)

            result = svc.check_for_updates(run_id)

        self.assertFalse(result["has_changes"])
        self.assertEqual(result["new_count"], 0)
        self.assertEqual(result["removed_count"], 0)
        self.assertEqual(result["unchanged_count"], 3)

    def test_phat_hien_chuong_moi_va_chuong_bien_mat(self):
        pages = self._pages(1, 2, 3)
        store = MockScrapeRunStore()
        with patch.dict("server.scraper.site_registry._REGISTRY", self._CFG):
            svc = ScraperOpsService(store, fetcher_factory=lambda: FixtureFetcher(dict(pages)))
            started = svc.start_or_continue(f"{self._UPDATE_BASE}/truyen/z")
            run_id = started["run"].run_id
            svc.drive(run_id)

            # Nguon doi: chuong 2 bien mat, chuong 4 la chuong moi.
            pages.clear()
            pages.update(self._pages(1, 3, 4))

            result = svc.check_for_updates(run_id)

        self.assertTrue(result["has_changes"])
        self.assertEqual(result["new_count"], 1)
        self.assertEqual(result["removed_count"], 1)
        self.assertEqual(result["unchanged_count"], 2)
        self.assertIn(f"{self._UPDATE_BASE}/truyen/z/chuong-2", result["removed_urls"])

    def test_check_for_updates_KHONG_tao_muc_moi_nao(self):
        pages = self._pages(1, 2, 3)
        store = MockScrapeRunStore()
        with patch.dict("server.scraper.site_registry._REGISTRY", self._CFG):
            svc = ScraperOpsService(store, fetcher_factory=lambda: FixtureFetcher(dict(pages)))
            started = svc.start_or_continue(f"{self._UPDATE_BASE}/truyen/z")
            run_id = started["run"].run_id
            svc.drive(run_id)
            so_muc_truoc = len(store.list_items(run_id, limit=None))

            pages.clear()
            pages.update(self._pages(1, 2, 3, 4))
            svc.check_for_updates(run_id)

            so_muc_sau = len(store.list_items(run_id, limit=None))
        self.assertEqual(so_muc_truoc, so_muc_sau, "check_for_updates() không được ghi ScrapeRunItem nào")

    def test_run_khong_ton_tai_nem_ScrapeRunNotFoundError(self):
        svc = _svc()
        with self.assertRaises(ScrapeRunNotFoundError):
            svc.check_for_updates("scr_khong-ton-tai")


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
