"""Kiem thu `server/scraper/content_extraction.py` (Phase 6 Story Harvester
V3) — 10 fixture ten rieng theo yeu cau: trang sach, day rac, wrapper long
nhau, tieu de lap, sidebar, binh luan sau truyen, dieu huong trong than
bai, chuong ngan hop le, Unicode/Vietnamese, trang rong/dang nhap."""
from __future__ import annotations

import unittest

from server.scraper.content_extraction import (
    ExtractionConfidence, extract_content_v3,
)

_DOAN_DAI = (
    "Đây là một đoạn văn bản đủ dài để mô phỏng nội dung chương thật, có "
    "đủ số ký tự cần thiết để vượt qua các ngưỡng kiểm tra tối thiểu trong "
    "bộ kiểm thử này, viết thêm cho chắc chắn."
)


class CleanArticleTest(unittest.TestCase):
    def test_trang_sach_article_semantic_duoc_nhan_dien_HIGH(self):
        html = f"""
        <html><body>
        <nav><a href="/">Trang chủ</a><a href="/list">Danh sách</a></nav>
        <article>
          <h1>Chương 1: Khởi Đầu</h1>
          <p>{_DOAN_DAI}</p>
          <p>{_DOAN_DAI}</p>
          <p>{_DOAN_DAI}</p>
        </article>
        <footer>Bản quyền © trang web</footer>
        </body></html>
        """
        result = extract_content_v3(html, chapter_title="Chương 1: Khởi Đầu")
        self.assertEqual(result.confidence, ExtractionConfidence.HIGH)
        self.assertIn(_DOAN_DAI, result.clean_text)
        self.assertNotIn("Trang chủ", result.clean_text)
        self.assertNotIn("Bản quyền", result.clean_text)


class JunkHeavyPageTest(unittest.TestCase):
    def test_noi_dung_that_thang_du_bi_bao_vay_boi_rac(self):
        rac = "".join(
            f'<div class="ad-slot">Quảng cáo số {i} mua ngay giảm giá sốc</div>'
            for i in range(1, 10)
        )
        html = f"""
        <html><body>
        {rac}
        <div class="sidebar-related">
          <a href="/x">Truyện đề xuất 1</a><a href="/y">Truyện đề xuất 2</a>
        </div>
        <div class="chapter-content">
          <p>{_DOAN_DAI}</p>
          <p>{_DOAN_DAI}</p>
          <p>{_DOAN_DAI}</p>
        </div>
        {rac}
        </body></html>
        """
        result = extract_content_v3(html, chapter_title="Chương")
        self.assertIn(_DOAN_DAI, result.clean_text)
        self.assertNotIn("Quảng cáo", result.clean_text)
        self.assertNotIn("đề xuất", result.clean_text)


class NestedWrapperTest(unittest.TestCase):
    def test_wrapper_long_nhau_ba_lop_van_tim_dung_noi_dung(self):
        html = f"""
        <html><body>
        <div class="page"><div class="container"><div class="inner">
          <div class="chapter-content">
            <p>{_DOAN_DAI}</p>
            <p>{_DOAN_DAI}</p>
          </div>
        </div></div></div>
        </body></html>
        """
        result = extract_content_v3(html)
        self.assertIn(_DOAN_DAI, result.clean_text)
        self.assertEqual(result.container_signature, "div.chapter-content")


class DuplicateTitleTest(unittest.TestCase):
    def test_tieu_de_lap_o_menu_khong_lam_nhieu_ket_qua(self):
        html = f"""
        <html><body>
        <div class="chapter-list"><a href="/c1">Chương 1: Khởi Đầu</a>
        <a href="/c2">Chương 2: Khởi Đầu</a></div>
        <article>
          <h1>Chương 1: Khởi Đầu</h1>
          <p>{_DOAN_DAI}</p>
        </article>
        </body></html>
        """
        result = extract_content_v3(html, chapter_title="Chương 1: Khởi Đầu")
        self.assertEqual(result.clean_text.count(_DOAN_DAI), 1)
        self.assertNotIn("Chương 2", result.clean_text)


class SidebarContaminationTest(unittest.TestCase):
    def test_sidebar_khong_lan_vao_noi_dung_thang(self):
        html = f"""
        <html><body>
        <div class="layout">
          <div class="sidebar">
            <p>Tác giả nổi bật: Ai đó</p>
            <p>Thể loại: Huyền huyễn, Tiên hiệp, Đô thị</p>
          </div>
          <article>
            <p>{_DOAN_DAI}</p>
            <p>{_DOAN_DAI}</p>
            <p>{_DOAN_DAI}</p>
          </article>
        </div>
        </body></html>
        """
        result = extract_content_v3(html)
        self.assertIn(_DOAN_DAI, result.clean_text)
        self.assertNotIn("Tác giả nổi bật", result.clean_text)


class CommentsAfterStoryTest(unittest.TestCase):
    def test_binh_luan_sau_truyen_bi_loai_du_nam_trong_ung_vien_thang(self):
        html = f"""
        <html><body>
        <div class="chapter-content">
          <p>{_DOAN_DAI}</p>
          <p>{_DOAN_DAI}</p>
          <div class="comment-section">
            <p>Bình luận: hay quá, chương sau đâu rồi tác giả ơi</p>
            <p>Bình luận: mong chương mới sớm nhé bạn</p>
          </div>
        </div>
        </body></html>
        """
        result = extract_content_v3(html)
        self.assertIn(_DOAN_DAI, result.clean_text)
        self.assertNotIn("Bình luận", result.clean_text)
        self.assertGreaterEqual(result.rejected_zone_count, 1)


class ChapterNavInsideBodyTest(unittest.TestCase):
    def test_dieu_huong_chuong_truoc_sau_trong_than_bai_bi_loai(self):
        html = f"""
        <html><body>
        <div class="chapter-content">
          <p>{_DOAN_DAI}</p>
          <div class="chapter-nav">
            <a href="/c/prev">Chương trước</a><a href="/c/next">Chương sau</a>
          </div>
          <p>{_DOAN_DAI}</p>
        </div>
        </body></html>
        """
        result = extract_content_v3(html)
        self.assertIn(_DOAN_DAI, result.clean_text)
        self.assertNotIn("Chương trước", result.clean_text)
        self.assertNotIn("Chương sau", result.clean_text)


class VeryShortLegitimateChapterTest(unittest.TestCase):
    def test_chuong_that_su_ngan_van_duoc_lay_ra_khong_bi_bo_trong(self):
        html = """
        <html><body>
        <article><h1>Vĩ Thanh</h1><p>Hết rồi. Cảm ơn đã đọc.</p></article>
        </body></html>
        """
        result = extract_content_v3(html, chapter_title="Vĩ Thanh")
        self.assertIn("Hết rồi", result.clean_text)
        # Ngan hon MIN_CONFIDENT_TOTAL_TEXT_LEN -> LOW, nhung KHONG rong.
        self.assertEqual(result.confidence, ExtractionConfidence.LOW)
        self.assertTrue(result.clean_text)


class UnicodeVietnameseTest(unittest.TestCase):
    def test_dau_thanh_va_ky_tu_dac_biet_duoc_giu_nguyen(self):
        doan = (
            "“Ngươi… ngươi dám?” — nàng quát lớn, giọng run run xen lẫn "
            "phẫn nộ. Một luồng chân khí — hay đúng hơn là… một thứ gì đó "
            "kỳ lạ — bùng lên dữ dội, đủ dài để vượt ngưỡng kiểm tra."
        )
        html = f'<html><body><article><p>{doan}</p></article></body></html>'
        result = extract_content_v3(html)
        self.assertIn(doan, result.clean_text)
        self.assertIn("“Ngươi", result.clean_text)
        self.assertIn("kỳ lạ", result.clean_text)


class EmptyLoginPlaceholderTest(unittest.TestCase):
    def test_trang_dang_nhap_ra_LOW_va_van_ban_gan_nhu_rong(self):
        html = """
        <html><body>
        <div class="login-box">
          <p>Vui lòng đăng nhập để tiếp tục đọc.</p>
        </div>
        </body></html>
        """
        result = extract_content_v3(html)
        self.assertEqual(result.confidence, ExtractionConfidence.LOW)
        self.assertNotIn("đăng nhập", result.clean_text)

    def test_trang_hoan_toan_rong(self):
        html = "<html><body></body></html>"
        result = extract_content_v3(html)
        self.assertEqual(result.confidence, ExtractionConfidence.LOW)
        self.assertEqual(result.clean_text, "")
        self.assertIsNone(result.container_signature)


class BoilerplateAcrossPagesTest(unittest.TestCase):
    def test_doan_trung_boilerplate_da_biet_bi_loai(self):
        doan_boilerplate = "Ủng hộ website bằng cách chia sẻ cho bạn bè nhé."
        html = f"""
        <html><body><article>
          <p>{_DOAN_DAI}</p>
          <p>{doan_boilerplate}</p>
        </article></body></html>
        """
        from server.scraper.content_extraction import _paragraph_hash

        known = {_paragraph_hash(doan_boilerplate)}
        result = extract_content_v3(html, known_boilerplate_hashes=known)

        self.assertIn(_DOAN_DAI, result.clean_text)
        self.assertNotIn(doan_boilerplate, result.clean_text)
        self.assertEqual(result.boilerplate_paragraph_count, 1)


class DeeplyNestedHtmlTest(unittest.TestCase):
    """Tai hien phat hien tu review doc lap (Codex): HTML long RAT sau
    (vd wrapper `<div>` lap lai hang nghin lan) tung lam de quy vuot gioi
    han mac dinh cua Python (~1000), nem `RecursionError` KHONG duoc
    `pipeline.py` bat rieng, lam dung CA DOT quet vi MOT trang loi. Cay
    duyet gio la LAP (khong de quy) — xem `_collect_all`/`_dem_vung_bi_loai`."""

    def test_ba_nghin_the_div_long_nhau_khong_nem_RecursionError(self):
        do_sau = 3000
        html = ("<html><body>" + "<div>" * do_sau
               + f"<p>{_DOAN_DAI}</p>"
               + "</div>" * do_sau + "</body></html>")

        result = extract_content_v3(html)  # KHONG duoc nem RecursionError.
        self.assertIn(_DOAN_DAI, result.clean_text)


class SiblingLeakageTest(unittest.TestCase):
    def test_wrapper_ngu_nghia_co_vung_khong_lien_quan_canh_ung_vien_that(self):
        """Tai hien phat hien tu review doc lap (Codex): mot <article> bao
        CA vung noi dung THAT (div.chapter-content) LAN mot vung khac
        khong khop reject-hint (vd "giới thiệu tác giả") nam CANH nhau —
        <article> co the thang diem TONG (tu khoa tieu de trung voi <h1>
        nam truc tiep trong no) nhung van ban cua no se lan ca vung khong
        lien quan. Phai uu tien con cu the hon (chiem da so van ban)."""
        gioi_thieu = (
            "Giới thiệu tác giả: một người viết truyện lâu năm với nhiều "
            "tác phẩm nổi tiếng trong cộng đồng, đã xuất bản hơn mười đầu "
            "sách và nhận được nhiều giải thưởng văn học trong nước.")
        html = f"""
        <html><body>
        <article>
          <h1>Chương 1</h1>
          <div class="chapter-content">
            <p>{_DOAN_DAI}</p>
            <p>Một đoạn văn thứ hai để tăng thêm điểm số cho ứng viên này.</p>
          </div>
          <div class="author-bio"><p>{gioi_thieu}</p></div>
        </article>
        </body></html>
        """
        result = extract_content_v3(html, chapter_title="Chương 1")
        self.assertEqual(result.container_signature, "div.chapter-content")
        self.assertIn(_DOAN_DAI, result.clean_text)
        self.assertNotIn("Giới thiệu tác giả", result.clean_text)
