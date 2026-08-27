"""
Overnight mega task, Phase 3 ("profile poisoning red team") — tan cong co
chu dich vao SiteProfile/self-healing bang cac fixture A-H theo dung yeu
cau. Muc tieu: ung vien GIA phai luon bi TU CHOI, khong bao gio am tham
duoc "hoc" thanh SiteProfile/chuong hop le.

Dung TRUC TIEP `content_extraction.extract_content_v3` (Phase 6, bo diem
cau truc) + `self_healing.validate_relocated_content` (THEM kiem tra
dang-nhap/loi + trung-chuong-truoc) — day la HAI lop phong ve THAT su
duoc dung tren duong san xuat (`GenericIndexAdapter.normalize_chapter`,
`ScraperOpsService.confirm_unknown_source`).

Fixture D va G da tim ra hai loi THAT (da sua, xem git log): D xac nhan
`_LOGIN_OR_ERROR_HINT_RE` bat dung trang dang nhap; G phat hien hint đó
ban dau THIEU cum tu loi may chu/xin loi chung chung, da duoc mo rong.
Fixture E (widget de xuat lam sai chapter_count_estimate) duoc kiem thu
rieng trong `test_scraper_discovery.py` (thay doi o `html_extract.py`,
khong phai self_healing/content_extraction).
"""
from __future__ import annotations

import unittest

from server.scraper.content_extraction import ExtractionConfidence, extract_content_v3
from server.scraper.self_healing import RelocationConfidence, validate_relocated_content

_REAL_CHAPTER = (
    "Chương thật sự bắt đầu với một buổi sáng mùa thu, khi nhân vật chính "
    "bước ra khỏi căn nhà nhỏ để đi tìm kiếm sự thật về quá khứ của mình. "
    "Con đường phía trước đầy chông gai nhưng anh vẫn quyết tâm tiến bước."
)


class FixtureA_AdvertisementDenserThanStoryTest(unittest.TestCase):
    def test_quang_cao_mat_do_lien_ket_cao_khong_thang_noi_dung_that(self):
        html = f"""
        <html><body>
        <div class="promo-zone">
        {"".join(f'<p><a href="/deal{i}">Ưu đãi cực sốc số {i} giảm giá năm mươi phần trăm hôm nay</a></p>' for i in range(1, 30))}
        </div>
        <article><h1>Chương 5</h1><p>{_REAL_CHAPTER}</p></article>
        </body></html>
        """
        r = extract_content_v3(html, chapter_title="Chương 5")
        self.assertEqual(r.container_signature, "article")
        self.assertIn(_REAL_CHAPTER[:30], r.clean_text)


class FixtureB_CommentsResembleChapterTest(unittest.TestCase):
    def test_binh_luan_nhieu_khong_thang_noi_dung_that(self):
        html = f"""
        <html><body>
        <article><h1>Chương 5</h1><p>{_REAL_CHAPTER}</p></article>
        <div class="feedback-zone">
        {"".join(f'<div class="fb-item"><p>Bình luận độc giả số {i}: Truyện hay quá, tôi rất thích đoạn này, mong tác giả ra chương mới sớm nhé cảm ơn nhiều.</p></div>' for i in range(1, 20))}
        </div>
        </body></html>
        """
        r = extract_content_v3(html, chapter_title="Chương 5")
        self.assertEqual(r.container_signature, "article")
        self.assertIn(_REAL_CHAPTER[:30], r.clean_text)


class FixtureC_RecommendationCardsTest(unittest.TestCase):
    def test_the_de_xuat_nhieu_doan_van_khong_thang_noi_dung_that(self):
        html = f"""
        <html><body>
        <div class="you-might-like">
        {"".join(f'<div class="card"><h3>Truyện gợi ý {i}</h3><p>Đây là một câu chuyện tuyệt vời về cuộc phiêu lưu kỳ thú của nhân vật chính số {i}, đầy hấp dẫn và lôi cuốn người đọc từ trang đầu.</p></div>' for i in range(1, 15))}
        </div>
        <article><h1>Chương 5</h1><p>{_REAL_CHAPTER}</p></article>
        </body></html>
        """
        r = extract_content_v3(html, chapter_title="Chương 5")
        self.assertEqual(r.container_signature, "article")
        self.assertIn(_REAL_CHAPTER[:30], r.clean_text)


class FixtureD_LoginPageReusesOldClassTest(unittest.TestCase):
    def test_trang_dang_nhap_dung_lai_class_chuong_cu_bi_ha_confidence(self):
        html = (
            '<html><body><div class="chapter-content">'
            "<p>Vui lòng đăng nhập để tiếp tục đọc chương này của bộ truyện "
            "yêu thích, cảm ơn bạn đã đồng hành cùng chúng tôi trong thời "
            "gian qua.</p></div></body></html>")
        v = validate_relocated_content(html, chapter_title="Chương 5")
        self.assertEqual(v.confidence, RelocationConfidence.LOW)
        self.assertTrue(v.looks_like_login_or_error_page)


class FixtureF_RedirectToHomepageTest(unittest.TestCase):
    def test_trang_chu_khong_dat_HIGH_confidence(self):
        html = "".join(
            f'<div class="teaser"><h3>Truyện hot {i}</h3><p>Giới thiệu ngắn '
            f"về truyện số {i}, một tác phẩm đang được nhiều độc giả yêu "
            "thích và theo dõi hàng ngày trên trang web của chúng tôi.</p>"
            "</div>" for i in range(1, 15))
        html = f"<html><body><div class=\"homepage-grid\">{html}</div></body></html>"
        r = extract_content_v3(html, chapter_title="Chương 5")
        self.assertNotEqual(r.confidence, ExtractionConfidence.HIGH)


class FixtureG_LongErrorPageTest(unittest.TestCase):
    def test_trang_loi_dai_giong_bai_viet_that_bi_tu_choi(self):
        html = """
        <html><body><article>
        <h1>Không thể hiển thị nội dung</h1>
        <p>Rất tiếc, có vẻ như đã xảy ra một sự cố ngoài ý muốn trong quá
        trình xử lý yêu cầu của bạn trên hệ thống máy chủ của chúng tôi
        hôm nay.</p>
        <p>Đội ngũ kỹ thuật đã được thông báo và đang tích cực khắc phục sự
        cố này, chúng tôi rất xin lỗi vì sự bất tiện đã gây ra cho quý độc
        giả thân mến.</p>
        <p>Trong lúc chờ đợi, quý vị có thể thử tải lại trang sau vài phút
        hoặc liên hệ với bộ phận hỗ trợ khách hàng của chúng tôi để được
        giúp đỡ thêm.</p>
        </article></body></html>
        """
        # content_extraction_v3 KHONG biet ve ngu nghia loi/dang nhap — no
        # van dat HIGH vi cau truc (article, nhieu doan van) hop le. Lop
        # BAO VE THAT SU la self_healing (dung o duong drive that).
        v = validate_relocated_content(html, chapter_title="Chương 5")
        self.assertEqual(v.confidence, RelocationConfidence.LOW)
        self.assertTrue(v.looks_like_login_or_error_page)

    def test_van_ban_tu_su_binh_thuong_nhac_toi_loi_su_co_khong_bi_nham(self):
        """Doi chung: mot chuong THAT co the tu nhien nhac den "lỗi"/"sự
        cố" (vd nhan vat gap su co mat dien) — KHONG duoc bi nham voi trang
        loi ky thuat."""
        html = (
            '<html><body><div class="chapter-content">'
            "<p>Sự cố mất điện đêm qua khiến cả làng chìm trong bóng tối "
            "suốt nhiều giờ liền, nhưng không ai trong nhóm bạn cảm thấy "
            "lo sợ vì họ đã quen với những đêm tối như vậy từ lâu rồi.</p>"
            "</div></body></html>")
        v = validate_relocated_content(html, chapter_title="Chương 5")
        self.assertFalse(v.looks_like_login_or_error_page)


class FixtureH_MalformedHtmlDeceptiveStructureTest(unittest.TestCase):
    def test_html_hong_co_chu_dich_khong_lam_lech_ket_qua(self):
        html = f"""
        <html><body>
        <div class="chapter-content"
        <p>Đoạn văn bị hỏng do thẻ mở không đóng đúng cách gây nhầm lẫn cho trình phân tích.
        <div class="ad-injection"><p>{"Quảng cáo chèn vào giữa do lỗi cấu trúc HTML cố ý tạo ra để đánh lừa. " * 10}</p></div>
        <article><h1>Chương 5</h1><p>{_REAL_CHAPTER}</p></article>
        </body></html>
        """
        r = extract_content_v3(html, chapter_title="Chương 5")
        self.assertEqual(r.container_signature, "article")
        self.assertIn(_REAL_CHAPTER[:30], r.clean_text)


if __name__ == "__main__":
    unittest.main()
