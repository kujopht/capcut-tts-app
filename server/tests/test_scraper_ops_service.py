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


def _fixture_fetcher_factory(**_kwargs):
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


class ProfileOutcomeSyncTest(unittest.TestCase):
    """Tai hien phat hien tu review doc lap (Codex): mot chu ky drive co CA
    thanh cong LAN loi phai goi `record_success`/`record_failure` DUNG MOT
    LAN (uu tien thanh cong), khong lap N lan theo so chuong — lap rieng
    hai vong "tat ca thanh cong" roi "tat ca loi" co the tinh SAI
    `consecutive_failures` so voi thu tu that su xay ra trong chu ky."""

    _BASE2 = "https://dong-bo-profile.example"
    _CFG = {}

    def test_chu_ky_co_ca_thanh_cong_va_loi_uu_tien_thanh_cong(self):
        html_chuong_ok = (
            '<html><body><div class="chapter-content">'
            'Nội dung chương hợp lệ đủ dài để vượt ngưỡng tối thiểu cho '
            'vùng nội dung trong bộ kiểm tra tích hợp đồng bộ hồ sơ.'
            '</div></body></html>')
        index_html = (
            '<html><head><title>Đồng Bộ Hồ Sơ</title></head><body><ul>'
            '<li><a href="/truyen/d/chuong-1">Chương 1</a></li>'
            '<li><a href="/truyen/d/chuong-2">Chương 2</a></li>'
            '<li><a href="/truyen/d/chuong-3">Chương 3</a></li>'
            '</ul></body></html>')
        pages = {
            f"{self._BASE2}/truyen/d": index_html,
            f"{self._BASE2}/truyen/d/chuong-1": html_chuong_ok,
            f"{self._BASE2}/truyen/d/chuong-2": html_chuong_ok,
            # chuong-3 CO Y KHONG co trong fixture -> FetchError -> loi.
        }
        profile_store = MockSiteProfileStore()
        svc = ScraperOpsService(
            MockScrapeRunStore(), fetcher_factory=lambda **_kwargs: FixtureFetcher(dict(pages)),
            profile_store=profile_store)

        svc.confirm_unknown_source(f"{self._BASE2}/truyen/d")
        started = svc.start_or_continue(f"{self._BASE2}/truyen/d")
        run_id = started["run"].run_id
        svc.drive(run_id)  # 1 chu ky, xu ly ca 3 muc: 2 thanh cong + 1 loi.

        profile = profile_store.get("dong-bo-profile.example")
        self.assertEqual(profile.status, ProfileStatus.VERIFIED)
        self.assertEqual(profile.success_count, 1,
                         "Phải gọi record_success ĐÚNG MỘT LẦN mỗi chu kỳ, không lặp theo số chương")
        self.assertEqual(profile.consecutive_failures, 0)


class WwwMismatchTest(unittest.TestCase):
    """Tai hien phat hien tu review doc lap (Codex): profile xac nhan tu
    mot url co "www." phai TIM LAI DUOC ngay sau do — truoc sua loi,
    `profile_from_proposal` tu tach domain (khong bo "www.") trong khi
    `_adapter_for_url` tra cuu qua `domain_of()` (co bo "www."), khien mot
    profile vua xac nhan xong "hong" ngay lap tuc."""

    _WWW_BASE = "https://www.co-www.example"
    _CFG = {}

    def _pages(self) -> dict:
        links = "".join(
            f'<li><a href="/truyen/w/chuong-{i}">Chương {i}</a></li>' for i in range(1, 4))
        index = f"<html><head><title>Truyện WWW</title></head><body><ul>{links}</ul></body></html>"
        pages = {f"{self._WWW_BASE}/truyen/w": index}
        for i in range(1, 4):
            pages[f"{self._WWW_BASE}/truyen/w/chuong-{i}"] = (
                f"<html><body><div class=\"chapter-content\">"
                f"Nội dung chương {i} đủ dài để vượt ngưỡng tối thiểu cho vùng "
                f"nội dung hợp lệ trong bộ kiểm tra tích hợp này thật sự."
                f"</div></body></html>")
        return pages

    def test_xac_nhan_tu_url_co_www_van_dung_duoc_ngay(self):
        pages = self._pages()
        profile_store = MockSiteProfileStore()
        svc = ScraperOpsService(
            MockScrapeRunStore(), fetcher_factory=lambda **_kwargs: FixtureFetcher(dict(pages)),
            profile_store=profile_store)

        svc.confirm_unknown_source(f"{self._WWW_BASE}/truyen/w")
        # PHAI tim thay ngay — truoc sua loi, day nem `UnsupportedSiteError`.
        started = svc.start_or_continue(f"{self._WWW_BASE}/truyen/w")
        self.assertEqual(started["progress"]["estimated_total"], 3)


class LearnedRateLimitAndPaginationTest(unittest.TestCase):
    def test_min_delay_hoc_duoc_duoc_dua_cho_fetcher_factory(self):
        """Tai hien phat hien tu review doc lap (Codex): `rate_limit_seconds`
        da hoc PHAI duoc dua cho fetcher, khong duoc bo qua de dung mac
        dinh cua `HttpFetcher`."""
        goi_voi_kwargs = []

        def factory(**kwargs):
            goi_voi_kwargs.append(kwargs)
            return FixtureFetcher(dict(_UNKNOWN_PAGES))

        profile_store = MockSiteProfileStore()
        svc = ScraperOpsService(MockScrapeRunStore(), fetcher_factory=factory,
                                profile_store=profile_store)
        svc.confirm_unknown_source(f"{_UNKNOWN_BASE}/truyen/x")
        profile_store.save("chua-biet.example", rate_limit_seconds=9.5)
        goi_voi_kwargs.clear()

        svc.start_or_continue(f"{_UNKNOWN_BASE}/truyen/x")

        self.assertTrue(any(kw.get("min_delay_seconds") == 9.5 for kw in goi_voi_kwargs),
                        f"Không thấy min_delay_seconds=9.5 trong các lần gọi: {goi_voi_kwargs}")

    def test_next_page_pattern_hoc_duoc_duoc_dung_de_theo_phan_trang(self):
        """Tai hien phat hien tu review doc lap (Codex): mot nguon hoc duoc
        co `pagination_strategy == numbered_pages` PHAI thuc su theo duoc
        trang tiep theo khi quet that, khong chi dung lai o trang dau."""
        base = "https://phan-trang.example"
        # Khung phan trang LIET KE nhieu so trang cung luc (page 2 VA page
        # 3 tu chinh trang 1) — thuc te pho bien, va can >=2 lien ket CUNG
        # hinh dang de duoc coi la mot cum (xem `_detect_pagination`, mot
        # lien ket "trang tiep theo" DUY NHAT khong du de phan biet voi
        # NEXT_PREV).
        trang_1 = (
            '<html><head><title>Truyện Phân Trang</title></head><body>'
            '<ul><li><a href="/truyen/p/chuong-1">Chương 1</a></li>'
            '<li><a href="/truyen/p/chuong-2">Chương 2</a></li>'
            '<li><a href="/truyen/p/chuong-3">Chương 3</a></li></ul>'
            '<a href="/truyen/p?page=2">2</a><a href="/truyen/p?page=3">3</a>'
            '</body></html>'
        )
        trang_2 = (
            '<html><head><title>Truyện Phân Trang</title></head><body>'
            '<ul><li><a href="/truyen/p/chuong-4">Chương 4</a></li>'
            '<li><a href="/truyen/p/chuong-5">Chương 5</a></li></ul>'
            '</body></html>'
        )
        chuong_html = (
            '<html><body><div class="chapter-content">'
            'Nội dung chương đủ dài để vượt ngưỡng tối thiểu cho vùng nội '
            'dung hợp lệ trong bộ kiểm tra tích hợp phân trang này.'
            '</div></body></html>')
        pages = {
            f"{base}/truyen/p": trang_1,
            f"{base}/truyen/p?page=2": trang_2,
        }
        for i in range(1, 6):
            pages[f"{base}/truyen/p/chuong-{i}"] = chuong_html

        profile_store = MockSiteProfileStore()
        svc = ScraperOpsService(
            MockScrapeRunStore(), fetcher_factory=lambda **_kwargs: FixtureFetcher(dict(pages)),
            profile_store=profile_store)

        proposal = svc.discover(f"{base}/truyen/p")["proposal"]
        self.assertEqual(proposal.pagination_strategy.value, "numbered_pages")
        self.assertIsNotNone(proposal.next_page_url_pattern)

        svc.confirm_unknown_source(f"{base}/truyen/p")
        started = svc.start_or_continue(f"{base}/truyen/p")
        # 5 chuong TREN CA HAI trang — truoc sua loi (next_page_pattern
        # khong duoc dua cho adapter), chi 3 chuong cua trang dau se duoc
        # thay.
        self.assertEqual(started["progress"]["estimated_total"], 5)


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
            svc = ScraperOpsService(store, fetcher_factory=lambda **_kwargs: FixtureFetcher(dict(pages)))
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
            svc = ScraperOpsService(store, fetcher_factory=lambda **_kwargs: FixtureFetcher(dict(pages)))
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
            svc = ScraperOpsService(store, fetcher_factory=lambda **_kwargs: FixtureFetcher(dict(pages)))
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


class NavigationOnlyAdapterDispatchTest(unittest.TestCase):
    """Tai hien phat hien tu review doc lap (Codex): `NavigationOnlyAdapter`
    (Phase 3) CHUA TUNG duoc tao qua duong that (`_adapter_for_url`/
    `_adapter_from_config`) — chi test truc tiep goi no. Kiem tra o day
    di qua DUNG duong operator that (SiteConfig -> discover -> start)."""

    _NAV_BASE = "https://dieu-huong.example"
    _CFG = {
        "dieu-huong.example": SiteConfig(
            domain="dieu-huong.example", chapter_href_pattern=r"/c/\d+",
            adapter_kind="navigation_only"),
    }

    def _pages(self, so_chuong: int) -> dict:
        def trang(so):
            tiep = (f'<a href="/c/{so + 1}">Tiếp theo</a>' if so < so_chuong else "")
            return (f'<html><head><title>Chương {so}</title></head><body>'
                   f'<div class="chapter-content"><p>Nội dung chương {so} đủ '
                   "dài để vượt ngưỡng tối thiểu cho vùng nội dung hợp lệ "
                   f"trong bộ kiểm thử điều phối adapter điều hướng.</p></div>"
                   f"{tiep}</body></html>")
        return {f"{self._NAV_BASE}/c/{i}": trang(i) for i in range(1, so_chuong + 1)}

    def test_discover_va_start_qua_SiteConfig_navigation_only(self):
        pages = self._pages(4)
        with patch.dict("server.scraper.site_registry._REGISTRY", self._CFG):
            svc = ScraperOpsService(
                MockScrapeRunStore(),
                fetcher_factory=lambda **_kw: FixtureFetcher(dict(pages)))
            preview = svc.discover(f"{self._NAV_BASE}/c/1")
            self.assertTrue(preview["supported"])
            self.assertEqual(preview["run"].estimated_total, 4)

            started = svc.start_or_continue(f"{self._NAV_BASE}/c/1")
            run_id = started["run"].run_id
            driven = svc.drive(run_id)
            self.assertEqual(driven["run"].status, ScrapeRunStatus.COMPLETED)
            self.assertEqual(driven["counts"]["review_ready"], 4)


class CheckPossibleMirrorTest(unittest.TestCase):
    """Phase 7: `check_possible_mirror` — kham pha nguon MOI (khong ghi
    gi), so sanh voi cac dot da co trong kho, tra ve nhung dot co
    confidence >= MEDIUM."""

    _MIRROR_BASE = "https://mirror-cua-x.example"

    def _mirror_pages(self, title: str, tac_gia: str) -> dict:
        index = f"""<html><head><title>{title}</title>
        <meta property="og:title" content="{title}">
        <meta name="author" content="{tac_gia}"></head>
        <body><ul>
        <li><a href="/m/chuong-1">Chương 1</a></li>
        <li><a href="/m/chuong-2">Chương 2</a></li>
        <li><a href="/m/chuong-3">Chương 3</a></li>
        </ul></body></html>"""
        ch = ('<html><body><div class="chapter-content"><p>Nội dung đủ '
             "dài để vượt ngưỡng tối thiểu cho vùng nội dung hợp lệ trong "
             "bộ kiểm tra tích hợp mirror này thật sự.</p></div></body></html>")
        return {
            f"{self._MIRROR_BASE}/m": index,
            f"{self._MIRROR_BASE}/m/chuong-1": ch,
            f"{self._MIRROR_BASE}/m/chuong-2": ch,
            f"{self._MIRROR_BASE}/m/chuong-3": ch,
        }

    @patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG)
    def test_khong_co_dot_nao_trung_tra_ve_danh_sach_rong(self):
        store = MockScrapeRunStore()
        svc = _svc(store)
        svc.start_or_continue(f"{_BASE}/truyen/thu-nghiem")

        pages = self._mirror_pages("Truyện Hoàn Toàn Khác", "Người Khác")
        svc2 = ScraperOpsService(
            store, fetcher_factory=lambda **_kw: FixtureFetcher(dict(pages)))
        result = svc2.check_possible_mirror(f"{self._MIRROR_BASE}/m")
        self.assertEqual(result["possible_mirrors"], [])

    @patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG)
    def test_title_va_author_khop_bao_MEDIUM(self):
        store = MockScrapeRunStore()
        svc = _svc(store)
        svc.start_or_continue(f"{_BASE}/truyen/thu-nghiem")

        # Fixture goc: title "Truyện Thử Nghiệm", author "Tác Giả Ẩn Danh"
        # (xem index.html) — dung LAI CA HAI de mo phong mirror THAT.
        pages = self._mirror_pages("Truyện Thử Nghiệm", "Tác Giả Ẩn Danh")
        svc2 = ScraperOpsService(
            store, fetcher_factory=lambda **_kw: FixtureFetcher(dict(pages)))
        result = svc2.check_possible_mirror(f"{self._MIRROR_BASE}/m")

        self.assertEqual(len(result["possible_mirrors"]), 1)
        mirror = result["possible_mirrors"][0]
        self.assertEqual(mirror["confidence"], "medium")
        self.assertIn("title", mirror["matched_signals"])
        self.assertIn("author", mirror["matched_signals"])

    @patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG)
    def test_khong_ghi_gi_du_tim_thay_mirror(self):
        store = MockScrapeRunStore()
        svc = _svc(store)
        svc.start_or_continue(f"{_BASE}/truyen/thu-nghiem")
        so_dot_truoc = len(store.runs)

        pages = self._mirror_pages("Truyện Thử Nghiệm", "Tác Giả Ẩn Danh")
        svc2 = ScraperOpsService(
            store, fetcher_factory=lambda **_kw: FixtureFetcher(dict(pages)))
        svc2.check_possible_mirror(f"{self._MIRROR_BASE}/m")

        self.assertEqual(len(store.runs), so_dot_truoc,
                         "check_possible_mirror() không được tạo/ghi bất kỳ dot nào")


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
