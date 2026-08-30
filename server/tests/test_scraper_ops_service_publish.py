"""
Production Story + Audio Harvester Launch — `ScraperOpsService.publish_reviewed_items`.

Cau noi con thieu (xem docstring ham): bien muc REVIEW_READY thanh Novel/
Chapter THAT o trang thai `draft`. Dung y het khuon fixture cua
`test_scraper_ops_service.py` (FixtureFetcher, SiteConfig gia dang ky tam
thoi vao `site_registry._REGISTRY`).
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from server.adapters import MockMetadataStore
from server.domain import PublishState
from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.run_state import MockScrapeRunStore
from server.scraper.site_registry import SiteConfig
from server.scraper_ops_service import (
    PublishNotConfiguredError,
    ScraperOpsService,
    deterministic_chapter_id,
    deterministic_novel_id,
)

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "scraper")


def _doc_fixture(ten: str) -> str:
    with open(os.path.join(_FIXTURES, ten), encoding="utf-8") as f:
        return f.read()


_BASE = "https://ops-publish-test.example"
_PAGES = {
    f"{_BASE}/truyen/thu-nghiem": _doc_fixture("index.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-1": _doc_fixture("chuong-1.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-2": _doc_fixture("chuong-2.html"),
    f"{_BASE}/truyen/thu-nghiem/chuong-3": _doc_fixture("chuong-3.html"),
}
_FAKE_CFG = {
    "ops-publish-test.example": SiteConfig(
        domain="ops-publish-test.example", chapter_href_pattern=r"/chuong-\d+",
        title_suffix_to_strip=" - Trang Web Giả"),
}


def _svc_toi_review_ready(*, metadata_store=None, pages=None):
    """Dung svc.start_or_continue + svc.drive de dua het chuong ve
    REVIEW_READY that su (khong bia trang thai) - tra ve (svc, run_id)."""
    scrape_store = MockScrapeRunStore()
    svc = ScraperOpsService(
        scrape_store, fetcher_factory=lambda **_kw: FixtureFetcher(dict(pages or _PAGES)),
        metadata_store=metadata_store)
    with patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG):
        started = svc.start_or_continue(f"{_BASE}/truyen/thu-nghiem")
        run_id = started["run"].run_id
        svc.drive(run_id, max_chapters=10)
    return svc, run_id


class PublishNotConfiguredTest(unittest.TestCase):
    def test_khong_co_metadata_store_nem_loi_ro_rang(self):
        svc, run_id = _svc_toi_review_ready()
        with self.assertRaises(PublishNotConfiguredError):
            svc.publish_reviewed_items(run_id, owner_id="svc_harvester")


class PublishReviewedItemsTest(unittest.TestCase):
    def test_publish_tao_novel_va_chapter_that_o_trang_thai_draft(self):
        meta = MockMetadataStore()
        with patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG):
            svc, run_id = _svc_toi_review_ready(metadata_store=meta)
            result = svc.publish_reviewed_items(run_id, owner_id="svc_harvester")

        self.assertEqual(result["published_count"], 3)
        self.assertEqual(result["error_count"], 0)

        novel = meta.get_novel(result["novel_id"])
        self.assertEqual(novel.owner_id, "svc_harvester")
        self.assertEqual(novel.state, PublishState.DRAFT)

        for chapter_id in result["published_chapter_ids"]:
            chapter = meta.get_chapter(chapter_id)
            self.assertEqual(chapter.novel_id, result["novel_id"])
            self.assertEqual(chapter.state, PublishState.DRAFT)
            self.assertTrue(chapter.content)

    def test_publish_lai_lan_hai_khong_tao_trung(self):
        meta = MockMetadataStore()
        with patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG):
            svc, run_id = _svc_toi_review_ready(metadata_store=meta)
            first = svc.publish_reviewed_items(run_id, owner_id="svc_harvester")
            second = svc.publish_reviewed_items(run_id, owner_id="svc_harvester")

        self.assertEqual(first["published_count"], 3)
        self.assertEqual(second["published_count"], 0)
        self.assertEqual(second["already_published_count"], 0)  # da loc truoc, khong tinh lai
        self.assertEqual(second["novel_id"], first["novel_id"])

    def test_item_ids_rong_khong_tao_novel_mo_coi(self):
        """Bai quyet dinh: ban dau tao Novel TRUOC khi loc item_ids, nen
        mot loi goi voi item_ids=[] (khong publish gi) van de lai mot
        Novel draft rong - tu review phat hien qua chinh bai test nay,
        sua lai thanh chi tao Novel khi THAT SU co it nhat mot muc de
        publish."""
        meta = MockMetadataStore()
        with patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG):
            svc, run_id = _svc_toi_review_ready(metadata_store=meta)
            result_rong = svc.publish_reviewed_items(
                run_id, owner_id="svc_harvester", item_ids=[])
            run = svc._store.get_run(run_id)
            self.assertEqual(run.published_novel_id, "")
            self.assertEqual(result_rong["novel_id"], "")

    def test_publish_tai_su_dung_novel_da_tao_khong_tao_novel_thu_hai(self):
        meta = MockMetadataStore()
        with patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG):
            svc, run_id = _svc_toi_review_ready(metadata_store=meta)
            items = svc._store.list_items(run_id, limit=None)
            first = svc.publish_reviewed_items(
                run_id, owner_id="svc_harvester", item_ids=[items[0].item_id])
            second = svc.publish_reviewed_items(
                run_id, owner_id="svc_harvester", item_ids=[items[1].item_id])

        self.assertEqual(first["novel_id"], second["novel_id"])
        run_sau = svc._store.get_run(run_id)
        self.assertEqual(run_sau.published_novel_id, first["novel_id"])

    def test_deterministic_ids_on_dinh_qua_nhieu_lan_goi(self):
        self.assertEqual(deterministic_novel_id("scr_abc"), deterministic_novel_id("scr_abc"))
        self.assertNotEqual(deterministic_novel_id("scr_abc"), deterministic_novel_id("scr_xyz"))
        self.assertEqual(deterministic_chapter_id("item1"), deterministic_chapter_id("item1"))
        self.assertNotEqual(deterministic_chapter_id("item1"), deterministic_chapter_id("item2"))
        # Trong gioi han $id 36 ky tu cua Appwrite.
        self.assertLessEqual(len(deterministic_novel_id("scr_abc")), 36)
        self.assertLessEqual(len(deterministic_chapter_id("item1")), 36)

    def test_content_mismatch_bi_tu_choi_khong_publish(self):
        meta = MockMetadataStore()
        with patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG):
            svc, run_id = _svc_toi_review_ready(metadata_store=meta)
            # Gia mao content_hash da luu cho MOT muc de mo phong "noi dung
            # nguon da doi ke tu luc duyet".
            items = svc._store.list_items(run_id, limit=None)
            svc._store.save_item(items[0].item_id, content_hash="da-doi-roi-khong-khop")
            result = svc.publish_reviewed_items(run_id, owner_id="svc_harvester")

        self.assertEqual(result["published_count"], 2)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["errors"][0]["stage"], "content_mismatch")

    def test_item_ids_loc_dung_chi_publish_muc_duoc_chon(self):
        meta = MockMetadataStore()
        with patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG):
            svc, run_id = _svc_toi_review_ready(metadata_store=meta)
            items = svc._store.list_items(run_id, limit=None)
            result = svc.publish_reviewed_items(
                run_id, owner_id="svc_harvester", item_ids=[items[0].item_id])

        self.assertEqual(result["published_count"], 1)

    def test_max_items_gioi_han_so_luot_publish_mot_lan(self):
        meta = MockMetadataStore()
        with patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG):
            svc, run_id = _svc_toi_review_ready(metadata_store=meta)
            result = svc.publish_reviewed_items(run_id, owner_id="svc_harvester", max_items=1)

        self.assertEqual(result["published_count"], 1)

    def test_fetch_loi_mot_chuong_khong_dung_ca_dot_publish(self):
        """Cung nguyen tac voi bulk.py::drive_once - mot muc loi khong duoc
        dung viec publish cac muc con lai."""
        meta = MockMetadataStore()
        pages_thieu = dict(_PAGES)
        del pages_thieu[f"{_BASE}/truyen/thu-nghiem/chuong-2"]
        with patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG):
            svc, run_id = _svc_toi_review_ready(metadata_store=meta, pages=_PAGES)
            # Sau khi drive that (voi du trang), xoa trang chuong-2 KHOI
            # fixture cua CHINH adapter dang dung trong publish (mo phong
            # nguon tam thoi khong the tai lai duoc nua luc publish).
            svc2 = ScraperOpsService(
                svc._store, fetcher_factory=lambda **_kw: FixtureFetcher(pages_thieu),
                metadata_store=meta)
            result = svc2.publish_reviewed_items(run_id, owner_id="svc_harvester")

        self.assertEqual(result["published_count"], 2)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["errors"][0]["stage"], "fetch")


if __name__ == "__main__":
    unittest.main()
