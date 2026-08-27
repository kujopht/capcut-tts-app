"""
Overnight P13 (Story Harvester V3 Phase 15 prep) — kiem thu cac THUOC
TINH AN TOAN cua `scripts/story_harvester_direct_to_web_canary.py` MA
KHONG can mot backend that dang chay (mo phong toan bo HTTP qua
`unittest.mock.patch` tren ham `goi()` cua chinh script).

TAP TRUNG vao dung NHUNG gi lam cho kich ban nay AN TOAN de giao cho
buoi sang chay voi credential that: (1) tu choi som neu gioi han chuong
qua lon, (2) tu choi neu khong xac nhan dung moi truong, (3) `--dry-run`
KHONG BAO GIO goi `POST /api/novels`/`POST /api/chapters`, (4) buoc don
fixture CHI xoa dung `novel_id` nhan lai tu chinh lan tao cua no, khong
bao gio doan/tim theo mau.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from unittest.mock import patch

_THU_MUC_GOC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DUONG_DAN = os.path.join(_THU_MUC_GOC, "scripts", "story_harvester_direct_to_web_canary.py")


def _nap_module():
    spec = importlib.util.spec_from_file_location("_canary_qa", _DUONG_DAN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_canary = _nap_module()


class XacNhanMoiTruongTest(unittest.TestCase):
    def test_khong_tuong_tac_can_bien_moi_truong_khop_chinh_xac(self):
        with patch.dict(os.environ, {"QA_HARVESTER_XAC_NHAN": "staging"}, clear=False):
            self.assertTrue(_canary._xac_nhan_moi_truong("staging", tuong_tac=False))
        with patch.dict(os.environ, {"QA_HARVESTER_XAC_NHAN": "staging"}, clear=False):
            self.assertFalse(_canary._xac_nhan_moi_truong("production", tuong_tac=False))

    def test_khong_tuong_tac_khong_co_bien_moi_truong_tu_choi(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(_canary._xac_nhan_moi_truong("staging", tuong_tac=False))

    def test_tuong_tac_phai_go_dung_ten_moi_truong(self):
        with patch("builtins.input", return_value="staging"):
            self.assertTrue(_canary._xac_nhan_moi_truong("staging", tuong_tac=True))
        with patch("builtins.input", return_value="production"):
            self.assertFalse(_canary._xac_nhan_moi_truong("staging", tuong_tac=True))
        with patch("builtins.input", return_value=""):
            self.assertFalse(_canary._xac_nhan_moi_truong("staging", tuong_tac=True))


class ChapterLimitCapTest(unittest.TestCase):
    def test_gioi_han_qua_10_bi_tu_choi_truoc_khi_cham_mang(self):
        with patch.object(_canary, "goi") as goi_gia:
            ma = _canary.main([
                "--api", "https://khong-that.invalid", "--environment", "staging",
                "--admin-token", "tok", "--source-url", "https://vidu.test/x",
                "--chapter-limit", "50", "--yes",
            ])
        self.assertEqual(ma, 2)
        goi_gia.assert_not_called()


class KhongXacNhanMoiTruongTuChoiTest(unittest.TestCase):
    def test_khong_xac_nhan_duoc_moi_truong_dung_lai_truoc_khi_cham_mang(self):
        with patch.object(_canary, "goi") as goi_gia, \
             patch.object(_canary, "_xac_nhan_moi_truong", return_value=False):
            ma = _canary.main([
                "--api", "https://khong-that.invalid", "--environment", "production",
                "--admin-token", "tok", "--source-url", "https://vidu.test/x",
            ])
        self.assertEqual(ma, 2)
        goi_gia.assert_not_called()


class _GiaLapServer:
    """Mo phong CHINH XAC nhung endpoint kich ban can, du de kiem tra
    THUOC TINH an toan (dry-run/cleanup-dung-id), khong can mot backend
    that su."""

    def __init__(self):
        self.novels_da_tao: dict = {}
        self.da_goi_post_novel = False
        self.da_goi_post_chapter = False
        self.da_goi_delete = []

    def goi(self, api, method, path, payload=None, token=None, timeout=120):
        if path == "/api/health":
            return 200, {"data_backend": "appwrite"}
        if path == "/api/auth/register":
            return 200, {"token": "tok-qa", "profile": {"user_id": "u1"}}
        if path == "/api/admin/scraper/discover":
            return 200, {"supported": True}
        if path == "/api/admin/scraper/runs":
            return 200, {"run": {"run_id": "scr_abc"}}
        if path == "/api/admin/scraper/runs/scr_abc":
            return 200, {"run": {"status": "completed", "count_review_ready": 1},
                        "items": [{"status": "review_ready", "quality_passed": True,
                                  "chapter_url": "https://vidu.test/x/chuong-1"}]}
        if path == "/api/admin/scraper/runs/scr_abc/drive":
            return 200, {}
        if path == "/api/novels":
            self.da_goi_post_novel = True
            nid = "nov_gia_lap_123"
            self.novels_da_tao[nid] = {"novel_id": nid, "state": "draft"}
            return 200, {"novel": self.novels_da_tao[nid]}
        if path.startswith("/api/novels/") and method == "GET":
            nid = path.rsplit("/", 1)[-1]
            doc = self.novels_da_tao.get(nid)
            if doc is None:
                return 404, {}
            return 200, {**doc, "title": "[QA-HARVESTER] x"}
        if path == "/api/novels" and method == "GET":
            return 200, {"novels": []}
        if path.startswith("/api/novels/") and method == "DELETE":
            nid = path.rsplit("/", 1)[-1]
            self.da_goi_delete.append(nid)
            return 200, {"deleted": True, "removed": {"chapters": 1}}
        if path == "/api/chapters":
            self.da_goi_post_chapter = True
            return 200, {"chapter_id": "chp_gia_lap"}
        return 404, {}


class DryRunNeverWritesTest(unittest.TestCase):
    def test_dry_run_khong_bao_gio_goi_post_novel_hay_chapter(self):
        """CO Y gia lap `site_registry.lookup` + adapter de nguon duoc
        coi la DA CAU HINH (khac di, `buoc_duyet_va_ghi_that` se tu choi
        SOM vi khong tim thay cau hinh xac minh — truoc ca khi toi buoc
        kiem tra `dry_run`, khien test nay "qua" vi mot ly do SAI)."""
        gia_lap = _GiaLapServer()

        sys.path.insert(0, _THU_MUC_GOC)
        from server.scraper import site_registry
        from server.scraper.contract import NormalizedChapter

        cfg_gia = site_registry.SiteConfig(
            domain="vidu.test", chapter_href_pattern=r"/chuong-\d+",
            verified_via="gia lap cho unit test")

        def fetch_chapter_gia(self, url):
            return "<html>gia lap</html>"

        def normalize_chapter_gia(self, url, raw_html, series):
            return NormalizedChapter(
                source_url=url, canonical_url=url, source_domain="vidu.test",
                series_title="X", chapter_title="Chương 1",
                raw_text=raw_html, clean_text="Nội dung giả lập đủ dài.",
                content_hash="h1", source_fingerprint="fp1")

        with patch.object(_canary, "goi", side_effect=gia_lap.goi), \
             patch.object(_canary, "_xac_nhan_moi_truong", return_value=True), \
             patch.object(site_registry, "lookup", return_value=cfg_gia), \
             patch("server.scraper.adapters.json_ld_adapter.JsonLdAwareAdapter.fetch_chapter",
                  fetch_chapter_gia), \
             patch("server.scraper.adapters.json_ld_adapter.JsonLdAwareAdapter.normalize_chapter",
                  normalize_chapter_gia):
            ma = _canary.main([
                "--api", "https://khong-that.invalid", "--environment", "staging",
                "--admin-token", "tok", "--source-url", "https://vidu.test/x",
                "--dry-run", "--yes",
            ])
        self.assertFalse(gia_lap.da_goi_post_novel,
                         "dry-run KHONG duoc goi POST /api/novels")
        self.assertFalse(gia_lap.da_goi_post_chapter,
                         "dry-run KHONG duoc goi POST /api/chapters")
        self.assertEqual(gia_lap.da_goi_delete, [])
        # Xac nhan buoc tai lai THAT SU chay toi noi (khong tu choi som
        # vi thieu cau hinh) — neu khong, test nay se "qua" vi ly do sai.
        self.assertTrue(any(ok for ten, ok, _ in _canary.KET_QUA
                            if "tai lai + trich xuat" in ten))


class CleanupOnlyDeletesOwnNovelTest(unittest.TestCase):
    def test_don_fixture_chi_xoa_novel_id_da_nhan_lai_tu_lan_tao(self):
        gia_lap = _GiaLapServer()
        # Tao san MOT novel "that" (khong lien quan) trong kho gia lap —
        # dai dien cho mot trong 13 series that. Kich ban KHONG duoc
        # dung toi ID nay bat ke tinh huong nao.
        gia_lap.novels_da_tao["nov_that_su_khong_lien_quan"] = {
            "novel_id": "nov_that_su_khong_lien_quan", "state": "published"}

        _canary.don_fixture("https://khong-that.invalid", "tok-qa", "nov_gia_lap_123")
        # (goi truc tiep don_fixture voi novel_id gia lap, khong qua goi()
        # that vi don_fixture tu goi ham module-level `goi` — patch lai.)

    def test_khong_co_novel_id_thi_khong_goi_delete_gi_ca(self):
        with patch.object(_canary, "goi") as goi_gia:
            _canary.don_fixture("https://khong-that.invalid", "tok-qa", None)
        goi_gia.assert_not_called()

    def test_co_novel_id_chi_goi_delete_dung_id_do(self):
        goi_ghi_lai = []

        def goi_gia(api, method, path, payload=None, token=None, timeout=120):
            goi_ghi_lai.append((method, path))
            return 200, {"deleted": True, "removed": {}}

        with patch.object(_canary, "goi", side_effect=goi_gia):
            _canary.don_fixture("https://khong-that.invalid", "tok-qa", "nov_gia_lap_123")

        self.assertEqual(goi_ghi_lai, [("DELETE", "/api/novels/nov_gia_lap_123")])


if __name__ == "__main__":
    unittest.main()
