"""
Production Story + Audio Harvester Launch — FastAPI route-level test cho
`POST /api/admin/scraper/runs/{run_id}/publish` trong `server/main.py`.

Kiem tra:
1. Happy path: drive dot quet ve REVIEW_READY, POST /publish tao Novel/Chapter that o DRAFT.
2. Auth: khong token (401), nguoi dung thuong (403), chi admin/owner moi duoc phep.
3. Idempotency: goi lai lan hai tra ve published_count=0, khong duplicate Novel/Chapter.
4. Filtering: truyen `item_ids` va `max_items` qua HTTP body payload.
5. Error handling: 404 khi run_id khong ton tai.
"""
from __future__ import annotations

import dataclasses
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATA_BACKEND", "mock")
os.environ.setdefault("STORAGE_BACKEND", "local")

from fastapi.testclient import TestClient       # noqa: E402

from server import main                          # noqa: E402
from server.adapters import MockIdentityAdapter, MockMetadataStore  # noqa: E402
from server.domain import PublishState           # noqa: E402
from server.scraper.http_fetcher import FixtureFetcher  # noqa: E402
from server.scraper.run_state import MockScrapeRunStore  # noqa: E402
from server.scraper.site_registry import SiteConfig  # noqa: E402
from server.scraper_ops_service import ScraperOpsService  # noqa: E402

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "scraper")


def _doc_fixture(ten: str) -> str:
    with open(os.path.join(_FIXTURES, ten), encoding="utf-8") as f:
        return f.read()


_BASE = "https://publish-route-test.example"
_PAGES = {
    f"{_BASE}/truyen/thu-nghiem": _doc_fixture("index.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-1": _doc_fixture("chuong-1.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-2": _doc_fixture("chuong-2.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-3": _doc_fixture("chuong-3.html"),
}

_FAKE_CFG = {
    "publish-route-test.example": SiteConfig(
        domain="publish-route-test.example",
        chapter_href_pattern=r"/chuong-\d+",
        title_suffix_to_strip=" - Trang Web Giả",
    ),
}


def _fixture_fetcher_factory(**_kwargs):
    return FixtureFetcher(dict(_PAGES))


class ScraperPublishRouteTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

        main.identity = MockIdentityAdapter()
        main.store = MockMetadataStore()

        self._scrape_run_store_cu = main.scrape_run_store
        self._scraper_ops_cu = main.scraper_ops
        main.scrape_run_store = MockScrapeRunStore()
        main.scraper_ops = ScraperOpsService(
            main.scrape_run_store,
            fetcher_factory=_fixture_fetcher_factory,
            metadata_store=main.store,
        )

        self.user, self.tk_user = self._nguoi("user@publish.vn", "Người Dùng")
        self.admin, self.tk_admin = self._nguoi("admin@publish.vn", "Quản Trị Viên")

        self._cau_hinh_cu = (
            main.settings.admin_user_ids,
            main.settings.owner_user_ids,
            main.settings.moderator_user_ids,
        )
        main.settings = dataclasses.replace(
            main.settings,
            admin_user_ids=(self.admin.user_id,),
        )

        self._registry_patch = patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG)
        self._registry_patch.start()

    def tearDown(self) -> None:
        self._registry_patch.stop()
        admin_ids, owner_ids, mod_ids = self._cau_hinh_cu
        main.settings = dataclasses.replace(
            main.settings,
            admin_user_ids=admin_ids,
            owner_user_ids=owner_ids,
            moderator_user_ids=mod_ids,
        )
        main.scrape_run_store = self._scrape_run_store_cu
        main.scraper_ops = self._scraper_ops_cu

    def _nguoi(self, email: str, ten: str):
        ho_so = main.identity.register(email, "MatKhau123", ten)
        token = main.identity.login(email, "MatKhau123")
        return ho_so, {"Authorization": f"Bearer {token}"}

    def _tao_run_review_ready(self) -> str:
        """Helper HTTP: khoi tao run va drive den REVIEW_READY qua API."""
        start_resp = self.client.post(
            "/api/admin/scraper/runs",
            headers=self.tk_admin,
            json={"url": f"{_BASE}/truyen/thu-nghiem"},
        )
        self.assertEqual(start_resp.status_code, 200)
        run_id = start_resp.json()["run"]["run_id"]

        drive_resp = self.client.post(
            f"/api/admin/scraper/runs/{run_id}/drive",
            headers=self.tk_admin,
            json={"max_chapters": 10},
        )
        self.assertEqual(drive_resp.status_code, 200)
        return run_id


class ScraperPublishAuthTest(ScraperPublishRouteTestBase):
    def test_publish_khong_token_bi_tu_choi_401(self):
        resp = self.client.post(
            "/api/admin/scraper/runs/scr_fake/publish",
            json={},
        )
        self.assertEqual(resp.status_code, 401)

    def test_publish_nguoi_dung_thuong_bi_tu_choi_403(self):
        resp = self.client.post(
            "/api/admin/scraper/runs/scr_fake/publish",
            headers=self.tk_user,
            json={},
        )
        self.assertEqual(resp.status_code, 403)


class ScraperPublishFlowTest(ScraperPublishRouteTestBase):
    def test_publish_run_khong_ton_tai_tra_404(self):
        resp = self.client.post(
            "/api/admin/scraper/runs/scr_khong_ton_tai/publish",
            headers=self.tk_admin,
            json={},
        )
        self.assertEqual(resp.status_code, 404)

    def test_publish_happy_path_tao_novel_va_chapter_draft(self):
        run_id = self._tao_run_review_ready()

        resp = self.client.post(
            f"/api/admin/scraper/runs/{run_id}/publish",
            headers=self.tk_admin,
            json={},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["run_id"], run_id)
        self.assertEqual(data["published_count"], 3)
        self.assertEqual(data["error_count"], 0)
        self.assertEqual(len(data["published_chapter_ids"]), 3)
        self.assertTrue(data["novel_id"])

        novel = main.store.get_novel(data["novel_id"])
        self.assertIsNotNone(novel)
        self.assertEqual(novel.state, PublishState.DRAFT)
        self.assertEqual(novel.owner_id, main.settings.harvester_owner_user_id)

        for chapter_id in data["published_chapter_ids"]:
            chapter = main.store.get_chapter(chapter_id)
            self.assertIsNotNone(chapter)
            self.assertEqual(chapter.novel_id, data["novel_id"])
            self.assertEqual(chapter.state, PublishState.DRAFT)
            self.assertTrue(chapter.content)

    def test_publish_idempotent_lan_hai_tra_ve_published_count_zero(self):
        run_id = self._tao_run_review_ready()

        resp1 = self.client.post(
            f"/api/admin/scraper/runs/{run_id}/publish",
            headers=self.tk_admin,
            json={},
        )
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertEqual(data1["published_count"], 3)

        resp2 = self.client.post(
            f"/api/admin/scraper/runs/{run_id}/publish",
            headers=self.tk_admin,
            json={},
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(data2["published_count"], 0)
        self.assertEqual(data2["novel_id"], data1["novel_id"])

    def test_publish_voi_item_ids_loc_chinh_xac(self):
        run_id = self._tao_run_review_ready()

        view_resp = self.client.get(
            f"/api/admin/scraper/runs/{run_id}",
            headers=self.tk_admin,
        )
        items = view_resp.json()["items"]
        first_item_id = items[0]["item_id"]

        resp = self.client.post(
            f"/api/admin/scraper/runs/{run_id}/publish",
            headers=self.tk_admin,
            json={"item_ids": [first_item_id]},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["published_count"], 1)
        self.assertEqual(len(data["published_chapter_ids"]), 1)

    def test_publish_voi_max_items_gioi_han_so_luong(self):
        run_id = self._tao_run_review_ready()

        resp = self.client.post(
            f"/api/admin/scraper/runs/{run_id}/publish",
            headers=self.tk_admin,
            json={"max_items": 2},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["published_count"], 2)
        self.assertEqual(len(data["published_chapter_ids"]), 2)


if __name__ == "__main__":
    unittest.main()