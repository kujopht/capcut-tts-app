"""Kiem thu `server/scraper/story_identity.py` (Phase 7 Story Harvester
V3) — nhan dang tac pham/phat hien mirror. Nguyen tac cot loi: KHONG BAO
GIO tra HIGH chi tu title (du khop chinh xac)."""
from __future__ import annotations

import unittest

from server.scraper.story_identity import (
    IdentitySignals, SameWorkConfidence, compare_identity,
)


def _tin_hieu(**kwargs) -> IdentitySignals:
    base = dict(canonical_url="https://a.example/truyen/x", title="Truyện X")
    base.update(kwargs)
    return IdentitySignals(**base)


class SameDomainTest(unittest.TestCase):
    """Phat hien qua review doc lap (Codex): ban dau `compare_identity`
    tra ve HIGH NGAY LAP TUC chi vi hai URL cung domain, TRUOC CA khi xet
    tin hieu nao khac — nghia la HAI TAC PHAM HOAN TOAN KHAC NHAU tren
    CUNG mot site tong hop/dich thuat (rat pho bien: mot site luu hang
    nghin truyen khac nhau) luon bi bao "HIGH confidence: cung mot tac
    pham". Domain KHONG noi gi ve noi dung/tac gia — phai la tin hieu YEU
    NHAT, khong bao gio du rieng no (giong "description")."""

    def test_cung_domain_KHONG_du_de_len_HIGH_du_khong_co_tin_hieu_nao_khac(self):
        a = _tin_hieu(canonical_url="https://vd.example/truyen/x", title="A")
        b = _tin_hieu(canonical_url="https://vd.example/truyen/y-hoan-toan-khac", title="B hoàn toàn khác")
        result = compare_identity(a, b)
        self.assertEqual(result.confidence, SameWorkConfidence.LOW)
        self.assertIn("same_domain", result.matched_signals)

    def test_cung_domain_CONG_title_mot_minh_van_khong_du_len_HIGH_hay_MEDIUM(self):
        # same_domain + title (hai tin hieu "khop") VAN phai LOW — ca hai
        # deu la tin hieu yeu, khong duoc cong don thanh HIGH/MEDIUM gia.
        a = _tin_hieu(canonical_url="https://vd.example/truyen/x", title="Cùng Tên")
        b = _tin_hieu(canonical_url="https://vd.example/truyen/y-khac", title="Cùng Tên")
        result = compare_identity(a, b)
        self.assertEqual(result.confidence, SameWorkConfidence.LOW)

    def test_www_va_khong_www_duoc_coi_la_cung_domain_nhung_van_chi_la_tin_hieu_yeu(self):
        a = _tin_hieu(canonical_url="https://www.vd.example/truyen/x")
        b = _tin_hieu(canonical_url="https://vd.example/truyen/x-khac-slug", title="Khác hẳn")
        result = compare_identity(a, b)
        self.assertIn("same_domain", result.matched_signals)
        self.assertEqual(result.confidence, SameWorkConfidence.LOW)

    def test_cung_domain_cong_hai_tin_hieu_doc_lap_khac_van_len_duoc_MEDIUM(self):
        # same_domain khong CAN, nhung khong CHAN MEDIUM khi cac tin hieu
        # doc lap khac (author + chapter_count) da du.
        a = _tin_hieu(canonical_url="https://vd.example/truyen/x", title="A",
                     author="Nguyễn Văn A", chapter_count=50)
        b = _tin_hieu(canonical_url="https://vd.example/truyen/y-khac", title="B khác hẳn",
                     author="Nguyễn Văn A", chapter_count=51)
        result = compare_identity(a, b)
        self.assertEqual(result.confidence, SameWorkConfidence.MEDIUM)


class ContentHashOverlapTest(unittest.TestCase):
    def test_trung_content_hash_ra_HIGH_du_khac_domain(self):
        a = _tin_hieu(canonical_url="https://a.example/truyen/x", title="Truyện X Bản Gốc",
                      sample_content_hashes={"h1", "h2"})
        b = _tin_hieu(canonical_url="https://b.example/story/x", title="Truyện X (Reup)",
                      sample_content_hashes={"h2", "h3"})
        result = compare_identity(a, b)
        self.assertEqual(result.confidence, SameWorkConfidence.HIGH)
        self.assertIn("content_hash", result.matched_signals)


class TitleAloneNeverHighTest(unittest.TestCase):
    """Nguyen tac cot loi cua Phase 7 — title khop KHONG BAO GIO du."""

    def test_title_khop_chinh_xac_mot_minh_ra_LOW(self):
        a = _tin_hieu(canonical_url="https://a.example/x", title="Đấu Phá Thương Khung")
        b = _tin_hieu(canonical_url="https://b.example/y", title="Đấu Phá Thương Khung")
        result = compare_identity(a, b)
        self.assertEqual(result.confidence, SameWorkConfidence.LOW)
        self.assertEqual(result.matched_signals, ["title"])

    def test_chi_mo_ta_trung_tu_khoa_mot_minh_ra_LOW(self):
        a = _tin_hieu(canonical_url="https://a.example/x", title="Truyện A",
                      description="Một câu chuyện huyền huyễn tu tiên đầy kịch tính hấp dẫn")
        b = _tin_hieu(canonical_url="https://b.example/y", title="Truyện Khác Hoàn Toàn",
                      description="Một câu chuyện huyền huyễn tu tiên đầy kịch tính hấp dẫn khác")
        result = compare_identity(a, b)
        self.assertEqual(result.confidence, SameWorkConfidence.LOW)


class MediumConfidenceTest(unittest.TestCase):
    def test_title_va_author_khop_ra_MEDIUM(self):
        a = _tin_hieu(canonical_url="https://a.example/x", title="Truyện X", author="Nguyễn Văn A")
        b = _tin_hieu(canonical_url="https://b.example/y", title="Truyện X", author="Nguyễn Văn A")
        result = compare_identity(a, b)
        self.assertEqual(result.confidence, SameWorkConfidence.MEDIUM)
        self.assertIn("title", result.matched_signals)
        self.assertIn("author", result.matched_signals)

    def test_title_va_so_chuong_gan_bang_ra_MEDIUM(self):
        a = _tin_hieu(canonical_url="https://a.example/x", title="Truyện X", chapter_count=100)
        b = _tin_hieu(canonical_url="https://b.example/y", title="Truyện X", chapter_count=102)
        result = compare_identity(a, b)
        self.assertEqual(result.confidence, SameWorkConfidence.MEDIUM)

    def test_author_va_so_chuong_khop_nhung_khong_trung_title_van_MEDIUM(self):
        """Doi ten ban dich (title khac) nhung tac gia + so chuong trung —
        van la hai tin hieu doc lap dong y, du MEDIUM."""
        a = _tin_hieu(canonical_url="https://a.example/x", title="Tên Bản Dịch A",
                      author="Tác Giả Gốc", chapter_count=50)
        b = _tin_hieu(canonical_url="https://b.example/y", title="Tên Bản Dịch B Khác Hẳn",
                      author="Tác Giả Gốc", chapter_count=51)
        result = compare_identity(a, b)
        self.assertEqual(result.confidence, SameWorkConfidence.MEDIUM)

    def test_so_chuong_chenh_lech_qua_lon_khong_khop(self):
        a = _tin_hieu(canonical_url="https://a.example/x", title="Truyện X", chapter_count=100)
        b = _tin_hieu(canonical_url="https://b.example/y", title="Truyện X", chapter_count=10)
        result = compare_identity(a, b)
        self.assertNotIn("chapter_count", result.matched_signals)
        self.assertEqual(result.confidence, SameWorkConfidence.LOW)


class NoSignalsTest(unittest.TestCase):
    def test_khong_co_tin_hieu_nao_khop_ra_LOW(self):
        a = _tin_hieu(canonical_url="https://a.example/x", title="Truyện A", author="X")
        b = _tin_hieu(canonical_url="https://b.example/y", title="Truyện B Khác", author="Y")
        result = compare_identity(a, b)
        self.assertEqual(result.confidence, SameWorkConfidence.LOW)
        self.assertEqual(result.matched_signals, [])
        self.assertTrue(result.evidence)
