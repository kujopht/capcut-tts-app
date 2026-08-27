"""
Test cho `server/scraper/quality.py` — kiem tra chat luong TAT DINH truoc
hang doi duyet, khong goi AI. Moi nhom test dung MOT `NormalizedChapter`
hop le lam nen (`_chuong()`), roi lam hong CHINH XAC mot truong de chung
minh tung check thuc su bat duoc dung loi cua no (khong bat nham loi khac).

Hai test duoc dat ten ro rang bam theo hai su co THAT tim thay trong canary
dem 2026-08-25 (xem docstring `quality.py`): rac dieu huong kieu Wikipedia
va van ban khong lo kieu "ca cuon sach" tu Project Gutenberg.
"""
from __future__ import annotations

import unittest

from server.scraper.contract import NormalizedChapter
from server.scraper.quality import (
    Severity,
    assess_chapter_quality,
    check_chapter_number,
    check_chapter_order,
    check_duplicate_paragraphs,
    check_encoding,
    check_nav_leakage,
    check_source_domain,
    check_source_url,
    check_text_length_maximum,
    check_text_length_minimum,
    check_title,
    check_truncation,
    check_vietnamese_diacritics,
)

_VAN_BAN_HOP_LE = (
    "Ánh nắng buổi sáng len qua khung cửa sổ cũ kỹ, rọi những vệt sáng "
    "mỏng manh lên nền nhà gỗ đã bạc màu theo năm tháng. Lan ngồi lặng lẽ "
    "bên bàn, tay ôm chặt cuốn nhật ký đã sờn gáy, lòng ngổn ngang trăm "
    "mối suy tư về những gì sắp xảy đến với gia đình nhỏ của mình.\n"
    "Cô nhớ lại buổi chiều hôm qua, khi mẹ cô đứng trước cổng nhà, ánh "
    "mắt xa xăm nhìn về phía con đường làng quanh co dẫn ra thị trấn. "
    "Không ai nói với ai điều gì, nhưng dường như cả hai đều hiểu rằng "
    "một điều gì đó lớn lao đang chờ đợi phía trước.\n"
    "Con phải mạnh mẽ lên, mẹ cô thì thầm, giọng nói run run nhưng đầy "
    "kiên định. Dù chuyện gì xảy ra, gia đình mình vẫn sẽ luôn bên nhau.\n"
    "Lan gật đầu, cố nuốt xuống cục nghẹn đang chực trào nơi cổ họng. Cô "
    "biết những ngày tháng sắp tới sẽ không hề dễ dàng, nhưng cô cũng "
    "biết rằng mình không hề đơn độc trên con đường phía trước."
)


def _chuong(**overrides) -> NormalizedChapter:
    """`NormalizedChapter` HOP LE lam nen — qua tat ca check khi khong sua
    gi. Cac test lam hong CHINH XAC mot truong qua `overrides`."""
    base = dict(
        source_url="https://vd-truyen.example/truyen/thu-nghiem/chuong-1",
        canonical_url="https://vd-truyen.example/truyen/thu-nghiem/chuong-1",
        source_domain="vd-truyen.example",
        series_title="Truyện Thử Nghiệm",
        chapter_title="Chương 1: Khởi Đầu",
        raw_text="<p>...</p>",
        clean_text=_VAN_BAN_HOP_LE,
        content_hash="a" * 64,
        source_fingerprint="b" * 64,
        chapter_number=1,
        author="Tác Giả Ẩn Danh",
        published_at="2026-01-01",
        language="vi",
    )
    base.update(overrides)
    return NormalizedChapter(**base)


class ChuongHopLeTest(unittest.TestCase):
    def test_chuong_hop_le_qua_tat_ca_check_khong_fail(self):
        report = assess_chapter_quality(_chuong())
        that_bai = [c.name for c in report.checks if not c.passed]
        self.assertEqual(that_bai, [], f"Check khong nen fail: {that_bai}")
        self.assertTrue(report.passed)
        self.assertEqual(report.score, 1.0)
        self.assertEqual(report.block_reasons, [])
        self.assertEqual(report.warn_reasons, [])


class TieuDeTest(unittest.TestCase):
    def test_tieu_de_rong_bi_block(self):
        r = check_title(_chuong(chapter_title=""))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_tieu_de_chi_co_khoang_trang_bi_block(self):
        r = check_title(_chuong(chapter_title="   \t  "))
        self.assertFalse(r.passed)

    def test_tieu_de_qua_ngan_bi_block(self):
        r = check_title(_chuong(chapter_title="A"))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_tieu_de_qua_dai_bi_block(self):
        r = check_title(_chuong(chapter_title="X" * 400))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_tieu_de_binh_thuong_qua(self):
        r = check_title(_chuong())
        self.assertTrue(r.passed)


class SoChuongTest(unittest.TestCase):
    def test_thieu_so_chuong_la_warn_khong_block(self):
        r = check_chapter_number(_chuong(chapter_number=None))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.WARN)

    def test_so_chuong_am_bi_block(self):
        r = check_chapter_number(_chuong(chapter_number=-1))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_so_chuong_bang_0_bi_block(self):
        r = check_chapter_number(_chuong(chapter_number=0))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_so_chuong_lon_bat_thuong_la_warn(self):
        r = check_chapter_number(_chuong(chapter_number=999_999))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.WARN)

    def test_so_chuong_hop_le_qua(self):
        r = check_chapter_number(_chuong(chapter_number=5))
        self.assertTrue(r.passed)

    def test_trung_so_voi_chuong_khac_trong_series_bi_flag(self):
        r = check_chapter_order(_chuong(chapter_number=3), [1, 2, 3, 4])
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.WARN)

    def test_nhay_qua_xa_so_voi_cac_chuong_da_biet_bi_flag(self):
        r = check_chapter_order(_chuong(chapter_number=999), [1, 2, 3])
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.WARN)

    def test_khong_co_sibling_thi_bo_qua_khong_fail(self):
        r = check_chapter_order(_chuong(chapter_number=3), [])
        self.assertTrue(r.passed)

    def test_so_chuong_hop_ly_trong_day_sibling_qua(self):
        r = check_chapter_order(_chuong(chapter_number=4), [1, 2, 3, 5, 6])
        self.assertTrue(r.passed)


class EncodingTest(unittest.TestCase):
    def test_ky_tu_thay_the_ufffd_bi_block(self):
        r = check_encoding(_chuong(clean_text=_VAN_BAN_HOP_LE + "�"))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_mojibake_utf8_doc_nham_latin1_bi_block(self):
        # "Các bác nói chuyện với nhau" bi giai ma UTF-8 -> Latin-1 -> mojibake
        # thuc te — day la dang loi CO THAT hay gap khi trang nguon khai bao
        # sai charset.
        hong = "CÃ¡c bÃ¡c nÃ³i chuyá»‡n vá»›i nhau " * 10
        r = check_encoding(_chuong(clean_text=hong))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_ky_tu_dieu_khien_bat_thuong_bi_block(self):
        r = check_encoding(_chuong(clean_text=_VAN_BAN_HOP_LE + "\x00\x01\x02"))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_van_ban_sach_qua(self):
        r = check_encoding(_chuong())
        self.assertTrue(r.passed)

    def test_van_ban_co_tab_va_xuong_dong_khong_bi_flag_nham(self):
        r = check_encoding(_chuong(clean_text=_VAN_BAN_HOP_LE + "\tđoạn thêm\n"))
        self.assertTrue(r.passed)


class VietnameseDiacriticsTest(unittest.TestCase):
    def test_chuong_vi_dai_khong_dau_bi_flag(self):
        khong_dau = ("Khong co dau tieng Viet nao ca trong doan van nay du no "
                     "kha dai va lap lai nhieu lan de vuot qua nguong kiem tra ") * 5
        r = check_vietnamese_diacritics(_chuong(clean_text=khong_dau, language="vi"))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.WARN)

    def test_chuong_vi_co_dau_qua(self):
        r = check_vietnamese_diacritics(_chuong())
        self.assertTrue(r.passed)

    def test_chuong_vi_ngan_khong_dau_khong_bi_flag(self):
        r = check_vietnamese_diacritics(_chuong(clean_text="Ok", language="vi"))
        self.assertTrue(r.passed)

    def test_chuong_khong_phai_vi_khong_ap_dung_check_qua_ham_gop(self):
        khong_dau = "No Vietnamese accents in this whole english chapter body. " * 10
        report = assess_chapter_quality(_chuong(clean_text=khong_dau, language="en"))
        ten_check = [c.name for c in report.checks]
        self.assertNotIn("vietnamese_diacritics", ten_check)


class NavLeakageTest(unittest.TestCase):
    def test_wikipedia_style_nav_leakage_bi_block(self):
        """Dung dinh dang gan giong trang MediaWiki that — cum 'Jump to
        content' la dau hieu THAT bat duoc trong canary dem qua nham vao
        Wikipedia (xem docstring quality.py)."""
        van_ban = "Jump to content\n" + _VAN_BAN_HOP_LE + "\nTrang chủ\nĐăng nhập\n"
        r = check_nav_leakage(_chuong(clean_text=van_ban))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_van_ban_sach_khong_co_nav_qua(self):
        r = check_nav_leakage(_chuong())
        self.assertTrue(r.passed)

    def test_hoi_thoai_ngan_hop_le_khong_bi_flag_nham(self):
        van_ban = _VAN_BAN_HOP_LE + '\n"Không!" cô hét lên.\n"Đi thôi!" anh đáp.'
        r = check_nav_leakage(_chuong(clean_text=van_ban))
        self.assertTrue(r.passed, "hoi thoai ngan hop le khong duoc bi coi la nav")


class DuplicateParagraphsTest(unittest.TestCase):
    def test_doan_van_lap_bi_block(self):
        doan_dai = ("Đây là một đoạn văn khá dài được lặp lại y hệt nhiều lần "
                    "trong cùng một chương, đây chính là dấu hiệu lỗi trích "
                    "xuất template thường gặp.")
        van_ban = doan_dai + "\n" + _VAN_BAN_HOP_LE + "\n" + doan_dai
        r = check_duplicate_paragraphs(_chuong(clean_text=van_ban))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_van_ban_sach_khong_lap_qua(self):
        r = check_duplicate_paragraphs(_chuong())
        self.assertTrue(r.passed)

    def test_dong_ngan_lap_lai_khong_bi_flag_nham(self):
        van_ban = _VAN_BAN_HOP_LE + "\n...\n...\n...\n"
        r = check_duplicate_paragraphs(_chuong(clean_text=van_ban))
        self.assertTrue(r.passed, "dong ngan lap (vd '...') khong nen bi coi la loi")


class TruncationTest(unittest.TestCase):
    def test_ket_thuc_bang_cham_lung_sau_it_noi_dung_bi_flag(self):
        r = check_truncation(_chuong(clean_text="Rồi đột nhiên, cô ấy thấy..."))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.WARN)

    def test_khong_co_dau_cau_ket_va_qua_ngan_bi_flag(self):
        r = check_truncation(_chuong(clean_text="Rồi đột nhiên cô ấy thấy một cái bóng"))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.WARN)

    def test_van_ban_sach_ket_thuc_dung_cau_qua(self):
        r = check_truncation(_chuong())
        self.assertTrue(r.passed)

    def test_chuong_ngan_hop_le_ket_thuc_dung_dau_cau_qua(self):
        r = check_truncation(_chuong(clean_text="Chương này rất ngắn."))
        self.assertTrue(r.passed)


class TextLengthTest(unittest.TestCase):
    def test_qua_ngan_bi_block(self):
        r = check_text_length_minimum(_chuong(clean_text="Ngắn quá."))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_do_dai_binh_thuong_qua(self):
        r = check_text_length_minimum(_chuong())
        self.assertTrue(r.passed)

    def test_gutenberg_style_ca_cuon_sach_bi_block(self):
        """Mo phong canary Gutenberg dem qua — MOT lan fetch tra ve ~718.000
        ky tu (ca cuon sach) thay vi mot chuong don le; check nay phai bat
        duoc dang loi 'lay nham ca sach' nay."""
        ca_cuon_sach = _VAN_BAN_HOP_LE * 900  # ~ 750.000 ky tu, giong canary that (~718.000).
        self.assertGreater(len(ca_cuon_sach), 700_000)
        r = check_text_length_maximum(_chuong(clean_text=ca_cuon_sach))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_do_dai_binh_thuong_khong_bi_flag_qua_nguong_toi_da(self):
        r = check_text_length_maximum(_chuong())
        self.assertTrue(r.passed)


class SourceUrlDomainTest(unittest.TestCase):
    def test_source_url_rong_bi_block(self):
        r = check_source_url(_chuong(source_url=""))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_canonical_url_thieu_scheme_bi_block(self):
        r = check_source_url(_chuong(canonical_url="vd-truyen.example/chuong-1"))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_url_hop_le_qua(self):
        r = check_source_url(_chuong())
        self.assertTrue(r.passed)

    def test_source_domain_rong_bi_block(self):
        r = check_source_domain(_chuong(source_domain=""))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.BLOCK)

    def test_source_domain_khong_khop_canonical_url_la_warn(self):
        r = check_source_domain(_chuong(source_domain="mot-domain-khac.example"))
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, Severity.WARN)

    def test_source_domain_khop_qua(self):
        r = check_source_domain(_chuong())
        self.assertTrue(r.passed)


class AssessChapterQualityTest(unittest.TestCase):
    def test_block_that_bai_lam_report_khong_passed(self):
        report = assess_chapter_quality(_chuong(chapter_title=""))
        self.assertFalse(report.passed)
        self.assertTrue(report.block_reasons)

    def test_chi_warn_that_bai_van_passed(self):
        report = assess_chapter_quality(_chuong(chapter_number=None))
        self.assertTrue(report.passed)
        self.assertTrue(report.warn_reasons)
        self.assertLess(report.score, 1.0)

    def test_sibling_chapter_numbers_duoc_truyen_xuong_check_thu_tu(self):
        report = assess_chapter_quality(
            _chuong(chapter_number=3), sibling_chapter_numbers=[1, 2, 3])
        ten_check_fail = [c.name for c in report.checks if not c.passed]
        self.assertIn("chapter_order", ten_check_fail)


if __name__ == "__main__":
    unittest.main()
