"""RAW ARCHIVE gate — `server/scraper/raw_archive.py`."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.raw_archive import (
    SensitiveContentDetected,
    fetch_and_spool_raw,
    scan_for_sensitive_data,
)
from server.scraper.site_registry import SiteConfig

_FAKE_CFG = {
    "raw-archive-test.example": SiteConfig(
        domain="raw-archive-test.example",
        chapter_href_pattern=r"/chuong-\d+",
        verified_via="unit test fixture"),
}


class ScanForSensitiveDataTest(unittest.TestCase):
    def test_noi_dung_sach_tra_ve_none(self):
        self.assertIsNone(scan_for_sensitive_data("Mot doan van ban binh thuong."))

    def test_phat_hien_email(self):
        self.assertEqual(scan_for_sensitive_data("lien he: a@b.com"), "dia chi email")

    def test_phat_hien_github_token(self):
        self.assertEqual(
            scan_for_sensitive_data("ghp_" + "a" * 36), "GitHub token")

    def test_phat_hien_so_dien_thoai_dung_token_doc_lap(self):
        self.assertEqual(
            scan_for_sensitive_data("goi cho toi: 0912345678 nhe"), "so dien thoai VN")

    def test_khong_bao_dong_gia_voi_timestamp_cache_mediawiki(self):
        """Phat hien that qua lan chay dau tien tren vi.wikisource.org:
        footer parser-cache cua MediaWiki co timestamp 14 chu so (vd
        "Cached time: 20260827145508") — mot doan con cua no khop dung
        hinh dang "so dien thoai VN" neu pattern khong doi hoi ranh gioi
        chu so o CA HAI dau."""
        self.assertIsNone(scan_for_sensitive_data(
            "Cached time: 20260827145508\nCache expiry: 2592000"))


class FetchAndSpoolRawTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.spool_root = Path(self._tmp.name)

    def test_tao_manifest_va_raw_file_that(self):
        url = "https://raw-archive-test.example/truyen/thu-nghiem"
        fetcher = FixtureFetcher({url: "<html><body>Noi dung sach.</body></html>"})

        with patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG):
            result = fetch_and_spool_raw(url, spool_root=self.spool_root, fetcher=fetcher)

        self.assertTrue(result.raw_path.exists())
        self.assertTrue(result.manifest_path.exists())
        self.assertEqual(
            result.raw_path.read_text(encoding="utf-8"),
            "<html><body>Noi dung sach.</body></html>")

        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["requested_url"], url)
        self.assertEqual(manifest["final_url"], url)
        self.assertEqual(manifest["source_domain"], "raw-archive-test.example")
        self.assertEqual(manifest["status_code"], 200)
        self.assertEqual(manifest["raw_bytes"], len(
            "<html><body>Noi dung sach.</body></html>".encode("utf-8")))
        self.assertTrue(manifest["raw_sha256"])
        self.assertEqual(manifest["sensitive_scan"]["status"], "clean")

    def test_goi_lai_cung_url_ra_cung_thu_muc_con(self):
        url = "https://raw-archive-test.example/truyen/thu-nghiem"
        fetcher = FixtureFetcher({url: "<html>A</html>"})
        with patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG):
            first = fetch_and_spool_raw(url, spool_root=self.spool_root, fetcher=fetcher)
            second = fetch_and_spool_raw(url, spool_root=self.spool_root, fetcher=fetcher)
        self.assertEqual(first.local_dir, second.local_dir)

    def test_du_lieu_nhay_cam_bi_chan_khong_ghi_gi(self):
        url = "https://raw-archive-test.example/truyen/lo"
        fetcher = FixtureFetcher({url: "lien he admin: contact@example.com"})

        with patch.dict("server.scraper.site_registry._REGISTRY", _FAKE_CFG):
            with self.assertRaises(SensitiveContentDetected):
                fetch_and_spool_raw(url, spool_root=self.spool_root, fetcher=fetcher)

        self.assertEqual(list(self.spool_root.rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
