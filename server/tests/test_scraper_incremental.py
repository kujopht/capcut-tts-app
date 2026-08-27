"""Kiem thu `server/scraper/incremental.py` (Phase 9 Story Harvester V3) —
engine cap nhat gia tang: so sanh danh sach URL chuong TUOI voi
`ScrapeState` da luu, KHONG tai lai chuong nao."""
from __future__ import annotations

import unittest

from server.scraper.dedupe import ScrapeState
from server.scraper.incremental import diff_toc


def _state_voi(*, ok_urls=(), failed_urls=(), skipped_urls=()) -> ScrapeState:
    state = ScrapeState()
    for url in ok_urls:
        state.record_success(url, content_hash_value="h")
    for url in failed_urls:
        state.record_failure(url)
    for url in skipped_urls:
        state.record_skip(url)
    return state


class KnownUrlsTest(unittest.TestCase):
    def test_khong_loc_tra_ve_tat_ca(self):
        state = _state_voi(ok_urls=["https://x/1"], failed_urls=["https://x/2"])
        self.assertEqual(set(state.known_urls()), {"https://x/1", "https://x/2"})

    def test_loc_theo_status_ok(self):
        state = _state_voi(ok_urls=["https://x/1"], failed_urls=["https://x/2"])
        self.assertEqual(state.known_urls(status="ok"), ["https://x/1"])


class DiffTocTest(unittest.TestCase):
    def test_chuong_moi_hoan_toan_deu_la_NEW(self):
        state = ScrapeState()
        diff = diff_toc(state, ["https://x/1", "https://x/2"])

        self.assertEqual(diff.new_urls, ["https://x/1", "https://x/2"])
        self.assertEqual(diff.removed_urls, [])
        self.assertEqual(diff.unchanged_count, 0)
        self.assertTrue(diff.has_changes)

    def test_chuong_da_ok_va_van_con_la_UNCHANGED(self):
        state = _state_voi(ok_urls=["https://x/1", "https://x/2"])
        diff = diff_toc(state, ["https://x/1", "https://x/2"])

        self.assertEqual(diff.new_urls, [])
        self.assertEqual(diff.removed_urls, [])
        self.assertEqual(diff.unchanged_count, 2)
        self.assertFalse(diff.has_changes)

    def test_chuong_ok_khong_con_trong_muc_luc_moi_la_REMOVED(self):
        state = _state_voi(ok_urls=["https://x/1", "https://x/2"])
        diff = diff_toc(state, ["https://x/1"])

        self.assertEqual(diff.removed_urls, ["https://x/2"])
        self.assertEqual(diff.unchanged_count, 1)
        self.assertTrue(diff.has_changes)

    def test_chuong_FAILED_khong_con_tren_muc_luc_KHONG_tinh_la_REMOVED(self):
        """Chi chuong TUNG THANH CONG ("ok") moi tinh la REMOVED khi bien
        mat — mot chuong dang loi (chua bao gio tai duoc) khong con tren
        muc luc chi la "khong con can thu lai nua", khong phai mot tin
        hieu "nguon da xoa noi dung da co"."""
        state = _state_voi(failed_urls=["https://x/1"])
        diff = diff_toc(state, [])

        self.assertEqual(diff.removed_urls, [])
        self.assertEqual(diff.unchanged_count, 0)

    def test_hon_hop_moi_con_va_mat(self):
        state = _state_voi(ok_urls=["https://x/1", "https://x/2", "https://x/3"])
        # x/2 bien mat, x/4 la chuong moi, x/1 va x/3 van con.
        diff = diff_toc(state, ["https://x/1", "https://x/3", "https://x/4"])

        self.assertEqual(diff.new_urls, ["https://x/4"])
        self.assertEqual(diff.removed_urls, ["https://x/2"])
        self.assertEqual(diff.unchanged_count, 2)

    def test_bien_the_url_khong_tracking_param_van_khop_qua_canonical(self):
        state = _state_voi(ok_urls=["https://x/1"])
        diff = diff_toc(state, ["https://x/1?utm_source=fb"])

        self.assertEqual(diff.new_urls, [])
        self.assertEqual(diff.removed_urls, [])
        self.assertEqual(diff.unchanged_count, 1)
