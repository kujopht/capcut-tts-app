"""
Tang HTTP cua Universal Story Scraper admin API — `server/main.py`.

Tang dich vu da duoc kiem ky o `test_scraper_ops_service.py`. Bo nay CHI
kiem nhung thu tang HTTP quyet dinh: ma trang thai (401/403/404/400), AI
la quan tri, va hinh dang JSON tra ve — cung phong cach voi
`test_trusted_source_routes.py`.
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
from server.scraper.http_fetcher import FixtureFetcher  # noqa: E402
from server.scraper.run_state import MockScrapeRunStore  # noqa: E402
from server.scraper.site_registry import SiteConfig  # noqa: E402
from server.scraper_ops_service import ScraperOpsService  # noqa: E402

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "scraper")


def _doc_fixture(ten: str) -> str:
    with open(os.path.join(_FIXTURES, ten), encoding="utf-8") as f:
        return f.read()


_BASE = "https://routes-test.example"
_PAGES = {
    f"{_BASE}/truyen/thu-nghiem": _doc_fixture("index.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-1": _doc_fixture("chuong-1.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-2": _doc_fixture("chuong-2.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-3": _doc_fixture("chuong-3.html"),
}

_FAKE_CFG = {
    "routes-test.example": SiteConfig(
        domain="routes-test.example", chapter_href_pattern=r"/chuong-\d+",
        title_suffix_to_strip=" - Trang Web Giả"),
}


def _fixture_fetcher_factory():
    return FixtureFetcher(dict(_PAGES))


class Nen(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)
        from server.adapters import MockIdentityAdapter, MockMetadataStore

        main.identity = MockIdentityAdapter()
        main.store = MockMetadataStore()

        self._scrape_run_store_cu = main.scrape_run_store
        self._scraper_ops_cu = main.scraper_ops
        main.scrape_run_store = MockScrapeRunStore()
        main.scraper_ops = ScraperOpsService(
            main.scrape_run_store, fetcher_factory=_fixture_fetcher_factory)

        self.an, self.tk_an = self._nguoi("an@vidu.vn", "An")
        self.admin, self.tk_admin = self._nguoi("admin@vidu.vn", "Quản trị")

        self._cau_hinh_cu = (main.settings.admin_user_ids, main.settings.owner_user_ids,
                             main.settings.moderator_user_ids)
        main.settings = dataclasses.replace(
            main.settings, admin_user_ids=(self.admin.user_id,))

        self._registry_patch = patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG)
        self._registry_patch.start()

    def tearDown(self) -> None:
        self._registry_patch.stop()
        admin_ids, owner_ids, mod_ids = self._cau_hinh_cu
        main.settings = dataclasses.replace(
            main.settings, admin_user_ids=admin_ids, owner_user_ids=owner_ids,
            moderator_user_ids=mod_ids)
        main.scrape_run_store = self._scrape_run_store_cu
        main.scraper_ops = self._scraper_ops_cu

    def _nguoi(self, email: str, ten: str):
        ho_so = main.identity.register(email, "MatKhau123", ten)
        token = main.identity.login(email, "MatKhau123")
        return ho_so, {"Authorization": f"Bearer {token}"}


class AuthTest(Nen):
    def test_anon_bi_tu_choi_401(self):
        resp = self.client.post("/api/admin/scraper/discover", json={"url": f"{_BASE}/x"})
        self.assertEqual(resp.status_code, 401)

    def test_nguoi_thuong_bi_tu_choi_403(self):
        resp = self.client.post(
            "/api/admin/scraper/discover", headers=self.tk_an, json={"url": f"{_BASE}/x"})
        self.assertEqual(resp.status_code, 403)


class ScraperFlowTest(Nen):
    def test_domain_chua_ho_tro_tra_400(self):
        resp = self.client.post(
            "/api/admin/scraper/discover", headers=self.tk_admin,
            json={"url": "https://khong-ho-tro.example/x"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("chưa được cấu hình", resp.json()["detail"])

    def test_discover_khong_ghi_gi(self):
        resp = self.client.post(
            "/api/admin/scraper/discover", headers=self.tk_admin,
            json={"url": f"{_BASE}/truyen/thu-nghiem"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["supported"])
        self.assertEqual(body["run"]["estimated_total"], 3)
        self.assertEqual(len(main.scrape_run_store.runs), 0)

    def test_start_drive_view_full_flow(self):
        started = self.client.post(
            "/api/admin/scraper/runs", headers=self.tk_admin,
            json={"url": f"{_BASE}/truyen/thu-nghiem"}).json()
        run_id = started["run"]["run_id"]
        self.assertEqual(started["progress"]["estimated_total"], 3)

        driven = self.client.post(
            f"/api/admin/scraper/runs/{run_id}/drive", headers=self.tk_admin, json={}).json()
        self.assertEqual(driven["run"]["status"], "completed")
        self.assertEqual(driven["counts"]["review_ready"], 3)

        viewed = self.client.get(
            f"/api/admin/scraper/runs/{run_id}", headers=self.tk_admin).json()
        self.assertEqual(len(viewed["items"]), 3)

        listed = self.client.get("/api/admin/scraper/runs", headers=self.tk_admin).json()
        self.assertEqual(len(listed["runs"]), 1)

    def test_view_run_khong_ton_tai_tra_404(self):
        resp = self.client.get(
            "/api/admin/scraper/runs/scr_khong_ton_tai", headers=self.tk_admin)
        self.assertEqual(resp.status_code, 404)

    def test_cancel_va_skip_va_retry(self):
        started = self.client.post(
            "/api/admin/scraper/runs", headers=self.tk_admin,
            json={"url": f"{_BASE}/truyen/thu-nghiem"}).json()
        run_id = started["run"]["run_id"]

        cancelled = self.client.post(
            f"/api/admin/scraper/runs/{run_id}/cancel", headers=self.tk_admin).json()
        self.assertEqual(cancelled["run"]["status"], "cancel_requested")

        # `CANCEL_REQUESTED` KHONG phai trang thai KET (chi CANCELLED/
        # COMPLETED/PARTIAL/FAILED moi la) — huy lan hai luc nay VAN duoc
        # phep (idempotent-ish), dung hanh vi that cua ScrapeRunService.
        resp2 = self.client.post(f"/api/admin/scraper/runs/{run_id}/cancel", headers=self.tk_admin)
        self.assertEqual(resp2.status_code, 200)

        # Dua dot ve trang thai KET that su (drive_once se thay CANCEL_REQUESTED
        # va chuyen sang CANCELLED) — TU DAY huy lan nua phai bi tu choi 400.
        self.client.post(f"/api/admin/scraper/runs/{run_id}/drive", headers=self.tk_admin, json={})
        resp3 = self.client.post(f"/api/admin/scraper/runs/{run_id}/cancel", headers=self.tk_admin)
        self.assertEqual(resp3.status_code, 400)


if __name__ == "__main__":
    unittest.main()
