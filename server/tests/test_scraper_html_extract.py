"""
Kiem thu cho `server/scraper/html_extract.py` — parser Tier 0 HTML bang
`html.parser` co san cua Python, ho tro loc noise-tag va heuristic ranh
gioi noi dung duong tinh (positive content boundary) cho cac trang dang
MediaWiki (Wikipedia, Wikisource,...).
"""
from __future__ import annotations

import unittest

from server.scraper.contract import NormalizedChapter
from server.scraper.html_extract import extract
from server.scraper.quality import check_nav_leakage


class HtmlExtractBoundaryTest(unittest.TestCase):
    def test_mediawiki_mw_parser_output_loai_bo_chrome_giu_noi_dung_chinh(self):
        """Fixture dang MediaWiki that: noi dung chuong nam trong
        `class="mw-parser-output"`, bao quanh boi cac the <div> UI-chrome
        (skip to content, sidebar, breadcrumb, printfooter, catlinks,
        search box). Parser phai chi giu lai van ban trong ranh gioi va
        loai bo toan bo rac UI-chrome."""
        html = """
        <!DOCTYPE html>
        <html lang="vi">
        <head>
            <title>Lều chõng/Chương 1 - Wikisource</title>
            <meta property="og:title" content="Lều chõng - Chương 1" />
        </head>
        <body class="skin-vector">
            <div class="vector-header-container">
                <div class="vector-header">
                    <a class="vector-skip-link" href="#mw-content-text">Bước tới nội dung</a>
                    <div class="vector-search-box">Tìm kiếm</div>
                </div>
            </div>
            <div class="vector-sidebar">
                <div class="vector-menu-heading">Điều hướng</div>
                <div class="vector-menu-content">Trang chính</div>
            </div>
            <div id="content" class="mw-body">
                <div id="mw-content-text" class="mw-body-content">
                    <div class="mw-content-ltr mw-parser-output" lang="vi" dir="ltr">
                        <p>Gần nửa tháng rồi, trong làng Văn khoa, lúc nào cũng náo nức, rộn rịp như sắp kéo hội.</p>
                        <p>Đình trung điếm sở cũng như quán nước hàng quà chỉ làm chỗ hội họp của các ông già, bà già.</p>
                    </div>
                    <div class="printfooter">Lấy từ "https://vi.wikisource.org/wiki/Lều_chõng/Chương_1"</div>
                    <div id="catlinks" class="catlinks">
                        <div id="mw-normal-catlinks" class="mw-normal-catlinks">Thể loại: Văn học Việt Nam</div>
                        <div id="mw-hidden-catlinks" class="mw-hidden-catlinks">Thể loại ẩn: Trang con</div>
                    </div>
                </div>
            </div>
            <div class="mw-footer-container">
                <div class="mw-footer">
                    <div class="footer-places">Chính sách bảo mật</div>
                </div>
            </div>
        </body>
        </html>
        """
        page = extract(html)
        text = page.visible_text()

        # Noi dung truyen chinh xac phai co mat
        self.assertIn("Gần nửa tháng rồi, trong làng Văn khoa", text)
        self.assertIn("Đình trung điếm sở cũng như quán nước hàng quà", text)

        # Toan bo UI chrome o ngoai ranh gioi phai bi loai bo
        self.assertNotIn("Bước tới nội dung", text)
        self.assertNotIn("Tìm kiếm", text)
        self.assertNotIn("Điều hướng", text)
        self.assertNotIn("Trang chính", text)
        self.assertNotIn("Lấy từ", text)
        self.assertNotIn("Thể loại", text)
        self.assertNotIn("Chính sách bảo mật", text)

        # Kiem tra chat luong chong nav leakage phai dat (passed=True)
        chap = NormalizedChapter(
            source_url="https://vi.wikisource.org/wiki/L%E1%BB%81u_ch%C3%B5ng/Ch%C6%B0%C6%A1ng_1",
            canonical_url="https://vi.wikisource.org/wiki/L%E1%BB%81u_ch%C3%B5ng/Ch%C6%B0%C6%A1ng_1",
            source_domain="vi.wikisource.org",
            series_title="Lều chõng",
            chapter_title="Chương 1",
            raw_text=html,
            clean_text=text,
            content_hash="a" * 64,
            source_fingerprint="b" * 64,
            chapter_number=1,
            language="vi",
        )
        result = check_nav_leakage(chap)
        self.assertTrue(result.passed, f"nav_leakage failed: {result.reason}")

    def test_non_mediawiki_giu_nguyen_hanh_vi_trich_xuat_toan_trang(self):
        """Trang HTML khong phai MediaWiki (khong chua `mw-parser-output` hay
        `mw-content-text`) phai giu nguyen 100% hanh vi trich xuat toan bo
        trang truoc day (chi bo noise tags ngu nghia script/style/nav/header/footer)."""
        html = """
        <html>
        <head><title>Trang Truyện Thường</title></head>
        <body>
            <header>Tiêu đề website bỏ qua</header>
            <div class="intro-block">
                <p>Lời mở đầu của tác giả ngoài bài viết.</p>
            </div>
            <article class="story-body">
                <p>Nội dung chính của câu chuyện phiêu lưu.</p>
                <p>Hành trình tiếp tục qua những vùng đất mới.</p>
            </article>
            <div class="custom-bottom-box">
                <p>Ghi chú cuối trang của người đăng tải.</p>
            </div>
            <footer>Bản quyền 2026</footer>
        </body>
        </html>
        """
        page = extract(html)
        text = page.visible_text()

        # Semantic noise tags van bi bo qua
        self.assertNotIn("Tiêu đề website bỏ qua", text)
        self.assertNotIn("Bản quyền 2026", text)

        # Cac khoi div thong thuong ngoai semantic noise van duoc giu nguyen ven
        self.assertIn("Lời mở đầu của tác giả ngoài bài viết.", text)
        self.assertIn("Nội dung chính của câu chuyện phiêu lưu.", text)
        self.assertIn("Hành trình tiếp tục qua những vùng đất mới.", text)
        self.assertIn("Ghi chú cuối trang của người đăng tải.", text)

    def test_mediawiki_mw_content_text_fallback_khi_khong_co_mw_parser_output(self):
        """Kiem tra truong hop skin MediaWiki cu chi co `id="mw-content-text"`
        ma khong co `class="mw-parser-output"`: van ban trong `mw-content-text`
        duoc giu lai, UI chrome ben ngoai van bi loai bo."""
        html = """
        <html>
        <body>
            <div class="top-nav">Jump to content</div>
            <div id="mw-content-text">
                <p>Nội dung bài viết trong skin MediaWiki cũ.</p>
            </div>
            <div class="bottom-bar">Search and footer info</div>
        </body>
        </html>
        """
        page = extract(html)
        text = page.visible_text()
        self.assertIn("Nội dung bài viết trong skin MediaWiki cũ.", text)
        self.assertNotIn("Jump to content", text)
        self.assertNotIn("Search and footer info", text)

    def test_noise_tags_ben_trong_boundary_van_duoc_loai_bo(self):
        """Cac the `_NOISE_TAGS` (style, script, aside, nav,...) neu nam
        BEN TRONG `mw-parser-output` van phai duoc bo qua theo dung quy tac."""
        html = """
        <div class="mw-parser-output">
            <p>Văn bản hợp lệ đoạn 1.</p>
            <aside>Quảng cáo hoặc ghi chú bên lề</aside>
            <style>.hidden { display: none; }</style>
            <script>console.log("tracking");</script>
            <p>Văn bản hợp lệ đoạn 2.</p>
        </div>
        """
        page = extract(html)
        text = page.visible_text()
        self.assertIn("Văn bản hợp lệ đoạn 1.", text)
        self.assertIn("Văn bản hợp lệ đoạn 2.", text)
        self.assertNotIn("Quảng cáo hoặc ghi chú bên lề", text)
        self.assertNotIn("display: none", text)
        self.assertNotIn("tracking", text)


if __name__ == "__main__":
    unittest.main()
