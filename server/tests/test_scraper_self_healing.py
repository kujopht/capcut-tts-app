"""Kiem thu `server/scraper/self_healing.py` (Phase 5 Story Harvester V3)
— kiem tra cau truc mot ung vien "tu-chua" selector: khong bao gio tang
confidence, chi co the ha (trung chuong truoc/trang dang nhap)."""
from __future__ import annotations

import unittest

from server.scraper.dedupe import content_hash
from server.scraper.self_healing import RelocationConfidence, validate_relocated_content

_NOI_DUNG_HOP_LE = (
    '<html><body><article><h1>Chương 5</h1><div class="chapter-content">'
    "<p>Đây là nội dung chương thật sự, đủ dài để vượt ngưỡng tối thiểu "
    "cho một vùng nội dung hợp lệ trong bộ kiểm thử tự-chữa selector.</p>"
    "<p>Một đoạn văn thứ hai để tăng thêm độ dài cho ứng viên này.</p>"
    "</div></article></body></html>"
)


class HighConfidenceAcceptedTest(unittest.TestCase):
    def test_ung_vien_hop_le_khong_trung_khong_dang_nhap_giu_HIGH(self):
        result = validate_relocated_content(_NOI_DUNG_HOP_LE, chapter_title="Chương 5")
        self.assertEqual(result.confidence, RelocationConfidence.HIGH)
        self.assertFalse(result.is_duplicate_of_previous_chapter)
        self.assertFalse(result.looks_like_login_or_error_page)


class DuplicateOfPreviousChapterTest(unittest.TestCase):
    def test_trung_het_chuong_truoc_bi_ha_ve_LOW(self):
        # Tinh truoc content_hash SE co cho noi dung nay, mo phong "chuong
        # truoc do" da co CUNG hash — selector dang lay lai noi dung cu.
        du_doan = validate_relocated_content(_NOI_DUNG_HOP_LE)
        hash_chuong_truoc = content_hash(du_doan.clean_text)

        result = validate_relocated_content(
            _NOI_DUNG_HOP_LE, previous_chapter_content_hash=hash_chuong_truoc)

        self.assertEqual(result.confidence, RelocationConfidence.LOW)
        self.assertTrue(result.is_duplicate_of_previous_chapter)

    def test_noi_dung_khac_chuong_truoc_khong_bi_anh_huong(self):
        result = validate_relocated_content(
            _NOI_DUNG_HOP_LE, chapter_title="Chương 5",
            previous_chapter_content_hash="hash_hoan_toan_khac")
        self.assertEqual(result.confidence, RelocationConfidence.HIGH)
        self.assertFalse(result.is_duplicate_of_previous_chapter)


class LoginOrErrorPageTest(unittest.TestCase):
    def test_trang_dang_nhap_bi_ha_ve_LOW(self):
        html = (
            '<html><body><div class="chapter-content">'
            "<p>Vui lòng đăng nhập để đọc tiếp nội dung chương này, cảm "
            "ơn bạn đã quan tâm theo dõi câu chuyện của chúng tôi.</p>"
            "</div></body></html>"
        )
        result = validate_relocated_content(html)
        self.assertEqual(result.confidence, RelocationConfidence.LOW)
        self.assertTrue(result.looks_like_login_or_error_page)

    def test_trang_loi_404_bi_ha_ve_LOW(self):
        html = (
            '<html><body><div class="chapter-content">'
            "<p>404 Not Found — trang không tồn tại hoặc đã bị gỡ bỏ khỏi "
            "hệ thống, vui lòng kiểm tra lại đường dẫn truy cập.</p>"
            "</div></body></html>"
        )
        result = validate_relocated_content(html)
        self.assertEqual(result.confidence, RelocationConfidence.LOW)
        self.assertTrue(result.looks_like_login_or_error_page)


class WeakContentStaysMediumOrLowTest(unittest.TestCase):
    def test_noi_dung_yeu_khong_duoc_tu_nang_len_HIGH(self):
        html = "<html><body><div>Quá ngắn.</div></body></html>"
        result = validate_relocated_content(html)
        self.assertNotEqual(result.confidence, RelocationConfidence.HIGH)
