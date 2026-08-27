"""Kiem thu `server/scraper/dedupe.py::ScrapeState.find_canonical_urls_by_content_hash`
(Phase 8 Story Harvester V3, "POSSIBLE_DUPLICATE")."""
from __future__ import annotations

import unittest

from server.scraper.dedupe import ScrapeState


class FindByContentHashTest(unittest.TestCase):
    def test_tim_thay_chuong_khac_trung_content_hash(self):
        state = ScrapeState()
        state.record_success("https://x/c1", content_hash_value="h1")
        state.record_success("https://x/c2", content_hash_value="h1")

        ket_qua = state.find_canonical_urls_by_content_hash(
            "h1", exclude_canonical="https://x/c2")
        self.assertEqual(ket_qua, ["https://x/c1"])

    def test_loai_tru_chinh_no(self):
        state = ScrapeState()
        state.record_success("https://x/c1", content_hash_value="h1")

        ket_qua = state.find_canonical_urls_by_content_hash(
            "h1", exclude_canonical="https://x/c1")
        self.assertEqual(ket_qua, [])

    def test_khong_co_trung_tra_ve_rong(self):
        state = ScrapeState()
        state.record_success("https://x/c1", content_hash_value="h1")
        state.record_success("https://x/c2", content_hash_value="h2")

        ket_qua = state.find_canonical_urls_by_content_hash(
            "h_khong_ton_tai", exclude_canonical="https://x/c3")
        self.assertEqual(ket_qua, [])

    def test_chuong_that_bai_khong_tinh_la_trung(self):
        state = ScrapeState()
        state.record_success("https://x/c1", content_hash_value="h1")
        state.record_failure("https://x/c2")
        # Gia lap: c2 CO the co content_hash "h1" trong mot lan thu truoc
        # (khong xay ra that trong code hien tai, nhung kiem tra CO Y de
        # dam bao `status == "ok"` luon duoc kiem, khong chi content_hash).
        state._rows[list(state._rows.keys())[1]]["content_hash"] = "h1"

        ket_qua = state.find_canonical_urls_by_content_hash(
            "h1", exclude_canonical="https://x/c1")
        self.assertEqual(ket_qua, [], "chuong 'failed' khong duoc tinh la trung")

    def test_ba_chuong_cung_trung_tra_ve_ca_hai_con_lai(self):
        state = ScrapeState()
        state.record_success("https://x/c1", content_hash_value="h1")
        state.record_success("https://x/c2", content_hash_value="h1")
        state.record_success("https://x/c3", content_hash_value="h1")

        ket_qua = state.find_canonical_urls_by_content_hash(
            "h1", exclude_canonical="https://x/c3")
        self.assertEqual(set(ket_qua), {"https://x/c1", "https://x/c2"})
