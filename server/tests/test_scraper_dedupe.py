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


class HashIndexMaintenanceTest(unittest.TestCase):
    """Overnight ("memory/CPU characterization", O(N^2) hunt): sau khi
    chuyen `find_canonical_urls_by_content_hash` sang doc mot CHI SO
    NGUOC duy tri TANG DAN (thay vi quet `_rows` moi lan goi), kiem tra
    chi so do duoc CAP NHAT DUNG qua moi loai chuyen doi trang thai —
    khong de lai THAM CHIEU CU/"ma" sau khi mot ban ghi doi hash/trang
    thai."""

    def test_revision_doi_hash_cap_nhat_dung_chi_so(self):
        state = ScrapeState()
        state.record_success("https://x/c1", content_hash_value="h_cu")
        state.record_success("https://x/c2", content_hash_value="h_cu")
        # c1 duoc quet LAI voi noi dung MOI (REVISION) — hash doi tu h_cu
        # sang h_moi. Chi so PHAI phan anh dung: c1 khong con o h_cu nua.
        ban_ghi = state.record_success("https://x/c1", content_hash_value="h_moi")
        self.assertTrue(ban_ghi["is_revision"])

        self.assertEqual(
            state.find_canonical_urls_by_content_hash("h_cu", exclude_canonical="https://x/c2"),
            [], "c1 phải biến mất khỏi chỉ số của hash CŨ sau revision")
        self.assertEqual(
            state.find_canonical_urls_by_content_hash("h_moi", exclude_canonical="https://x/c1"),
            [], "hash MỚI của c1 chưa trùng với ai (chỉ có một mình c1)")

    def test_record_failure_sau_khi_da_ok_go_khoi_chi_so(self):
        state = ScrapeState()
        state.record_success("https://x/c1", content_hash_value="h1")
        state.record_success("https://x/c2", content_hash_value="h1")
        # c1 sau do (gia dinh) duoc coi la that bai — KHONG con hop le de
        # bao "trung" voi c2 nua.
        state.record_failure("https://x/c1")

        self.assertEqual(
            state.find_canonical_urls_by_content_hash("h1", exclude_canonical="https://x/c2"),
            [], "c1 đã 'failed' không được tính là trùng với c2 nữa")

    def test_record_skip_sau_khi_da_ok_go_khoi_chi_so(self):
        state = ScrapeState()
        state.record_success("https://x/c1", content_hash_value="h1")
        state.record_success("https://x/c2", content_hash_value="h1")
        state.record_skip("https://x/c1")

        self.assertEqual(
            state.find_canonical_urls_by_content_hash("h1", exclude_canonical="https://x/c2"),
            [], "c1 đã bị skip không được tính là trùng với c2 nữa")

    def test_chi_so_khong_giu_hash_rong_sau_khi_muc_cuoi_cung_roi_di(self):
        state = ScrapeState()
        state.record_success("https://x/c1", content_hash_value="h1")
        state.record_failure("https://x/c1")
        # Hash "h1" khong con AI ca — chi so noi bo phai TU DON (khong
        # giu mot khoa voi tap rong mai mai, tranh ro ri bo nho tren dot
        # rat dai voi nhieu revision/failure).
        self.assertNotIn("h1", state._chi_so_theo_hash)
