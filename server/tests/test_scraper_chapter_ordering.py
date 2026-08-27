"""Kiem thu `server/scraper/chapter_ordering.py` (Phase 3 Story Harvester
V3) — phan cap uu tien: so chuong ro rang > metadata co cau truc > thu tu
muc luc > thu tu theo doi next/prev > ngay dang (fallback cuoi cung)."""
from __future__ import annotations

import unittest

from server.scraper.chapter_ordering import (
    ChapterOrderingSignal, OrderingSource, determine_order,
)


def _tin_hieu(url: str, *, index=None, so=None, cau_truc=None, nav=None, ngay=None):
    return ChapterOrderingSignal(
        url=url, index_position=index, explicit_number=so,
        structured_position=cau_truc, navigation_position=nav, published_at=ngay)


class ExplicitNumberTest(unittest.TestCase):
    def test_tat_ca_co_so_sap_xep_theo_so(self):
        signals = [
            _tin_hieu("u1", index=0, so=2),
            _tin_hieu("u2", index=1, so=1),
            _tin_hieu("u3", index=2, so=3),
        ]
        result = determine_order(signals)
        self.assertEqual(result.source, OrderingSource.EXPLICIT_NUMBER)
        self.assertEqual(result.ordered_urls, ["u2", "u1", "u3"])
        self.assertTrue(result.reordered_from_index)

    def test_da_dung_thu_tu_khong_bao_gio_reordered(self):
        signals = [_tin_hieu("u1", index=0, so=1), _tin_hieu("u2", index=1, so=2)]
        result = determine_order(signals)
        self.assertFalse(result.reordered_from_index)


class ReverseChronologicalTest(unittest.TestCase):
    def test_muc_luc_liet_ke_moi_nhat_truoc_duoc_sua_lai(self):
        """Tai hien "reverse chronological TOC" — trang liet ke chuong 5,
        4, 3, 2, 1 (moi nhat truoc), phai duoc sua ve thu tu doc 1..5."""
        signals = [
            _tin_hieu("u5", index=0, so=5), _tin_hieu("u4", index=1, so=4),
            _tin_hieu("u3", index=2, so=3), _tin_hieu("u2", index=3, so=2),
            _tin_hieu("u1", index=4, so=1),
        ]
        result = determine_order(signals)
        self.assertEqual(result.ordered_urls, ["u1", "u2", "u3", "u4", "u5"])
        self.assertTrue(result.reordered_from_index)
        self.assertIn("reverse chronological", result.evidence.lower())


class MissingNumbersTest(unittest.TestCase):
    def test_it_chuong_thieu_so_van_dung_tang_explicit_giu_vi_tri_index(self):
        signals = [
            _tin_hieu("u1", index=0, so=1), _tin_hieu("u2", index=1, so=2),
            _tin_hieu("u3", index=2, so=3), _tin_hieu("u4", index=3, so=4),
            _tin_hieu("u5", index=4, so=5), _tin_hieu("u6", index=5, so=6),
            _tin_hieu("u7", index=6, so=7), _tin_hieu("u8", index=7, so=8),
            _tin_hieu("u9", index=8, so=9),
            _tin_hieu("ngoai-truyen", index=9, so=None),  # 1/10 thieu = 90% co so.
        ]
        result = determine_order(signals)
        self.assertEqual(result.source, OrderingSource.EXPLICIT_NUMBER)
        self.assertEqual(result.ordered_urls[-1], "ngoai-truyen")
        self.assertEqual(result.urls_missing_signal, ["ngoai-truyen"])

    def test_qua_nhieu_chuong_thieu_so_lui_ve_index_sequence(self):
        signals = [
            _tin_hieu("u1", index=0, so=1), _tin_hieu("u2", index=1, so=None),
            _tin_hieu("u3", index=2, so=None),
        ]
        result = determine_order(signals)
        self.assertEqual(result.source, OrderingSource.INDEX_SEQUENCE)
        self.assertEqual(result.ordered_urls, ["u1", "u2", "u3"])

    def test_so_trung_nhau_khong_dang_tin_lui_ve_index_sequence(self):
        signals = [_tin_hieu("u1", index=0, so=1), _tin_hieu("u2", index=1, so=1)]
        result = determine_order(signals)
        self.assertEqual(result.source, OrderingSource.INDEX_SEQUENCE)


class StructuredMetadataTest(unittest.TestCase):
    def test_dung_khi_khong_co_so_ro_rang_nhung_co_vi_tri_cau_truc(self):
        signals = [
            _tin_hieu("u1", index=0, cau_truc=2),
            _tin_hieu("u2", index=1, cau_truc=1),
        ]
        result = determine_order(signals)
        self.assertEqual(result.source, OrderingSource.STRUCTURED_METADATA)
        self.assertEqual(result.ordered_urls, ["u2", "u1"])


class IndexSequenceTest(unittest.TestCase):
    def test_fallback_mac_dinh_khi_khong_co_tin_hieu_manh_hon(self):
        signals = [_tin_hieu("u1", index=0), _tin_hieu("u2", index=1)]
        result = determine_order(signals)
        self.assertEqual(result.source, OrderingSource.INDEX_SEQUENCE)
        self.assertEqual(result.ordered_urls, ["u1", "u2"])


class NavigationSequenceTest(unittest.TestCase):
    def test_dung_khi_khong_co_trang_muc_luc(self):
        signals = [
            ChapterOrderingSignal(url="u2", navigation_position=1),
            ChapterOrderingSignal(url="u1", navigation_position=0),
        ]
        result = determine_order(signals)
        self.assertEqual(result.source, OrderingSource.NAVIGATION_SEQUENCE)
        self.assertEqual(result.ordered_urls, ["u1", "u2"])


class PublishTimestampFallbackTest(unittest.TestCase):
    def test_dung_khi_khong_con_tin_hieu_nao_khac(self):
        signals = [
            ChapterOrderingSignal(url="u2", published_at="2026-02-01"),
            ChapterOrderingSignal(url="u1", published_at="2026-01-01"),
        ]
        result = determine_order(signals)
        self.assertEqual(result.source, OrderingSource.PUBLISH_TIMESTAMP)
        self.assertEqual(result.ordered_urls, ["u1", "u2"])
        self.assertIn("YẾU NHẤT", result.evidence)

    def test_chuong_khong_co_ngay_giu_o_cuoi_khong_bia_dat(self):
        signals = [
            ChapterOrderingSignal(url="u1", published_at="2026-01-01"),
            ChapterOrderingSignal(url="u2", published_at=None),
        ]
        result = determine_order(signals)
        self.assertEqual(result.ordered_urls, ["u1", "u2"])
        self.assertEqual(result.urls_missing_signal, ["u2"])


class EmptyInputTest(unittest.TestCase):
    def test_danh_sach_rong_khong_loi(self):
        result = determine_order([])
        self.assertEqual(result.ordered_urls, [])
