"""
`server/translation_import.py` — trich van ban tho tu txt/epub/docx.

EPUB/DOCX duoc GIA LAP that trong test bang cach tu dung goi zip hop le
(khong can tep mau tren dia, khong can ebooklib/python-docx) — nen day la
kiem tra THAT su doc duoc cau truc file, khong phai mock ham `extract_text`.
"""

from __future__ import annotations

import unittest
import zipfile
from io import BytesIO

from server.translation import UnsupportedFormat
from server.translation_import import MAX_UPLOAD_BYTES, extract_text


def _epub_gia(*trang_html: str) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        for i, html in enumerate(trang_html):
            zf.writestr(f"OEBPS/chuong{i:03d}.xhtml", html)
        zf.writestr("META-INF/container.xml", "<container/>")
    return buf.getvalue()


def _docx_gia(*doan_van: str) -> bytes:
    NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"')
    than = "".join(
        f'<w:p><w:r><w:t>{d}</w:t></w:r></w:p>' for d in doan_van)
    xml = (f'<?xml version="1.0"?><w:document {NS}><w:body>{than}'
          f'</w:body></w:document>')
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
        zf.writestr("[Content_Types].xml", "<Types/>")
    return buf.getvalue()


class TxtTest(unittest.TestCase):
    def test_utf8(self):
        self.assertEqual(
            extract_text("chuong1.txt", "萧炎看向药老。".encode("utf-8")),
            "萧炎看向药老。")

    def test_gb18030_van_doc_duoc(self):
        goc = "萧炎看向药老。"
        self.assertEqual(
            extract_text("gb.txt", goc.encode("gb18030")), goc)

    def test_duoi_tep_khong_phan_biet_hoa_thuong(self):
        self.assertEqual(extract_text("A.TXT", b"abc"), "abc")


class EpubTest(unittest.TestCase):
    def test_trich_mot_trang(self):
        data = _epub_gia("<html><body><p>Xin chào thế giới.</p></body></html>")
        self.assertIn("Xin chào thế giới.", extract_text("truyen.epub", data))

    def test_trich_nhieu_trang_theo_thu_tu(self):
        data = _epub_gia(
            "<p>Chương một.</p>", "<p>Chương hai.</p>", "<p>Chương ba.</p>")
        ra = extract_text("truyen.epub", data)
        self.assertLess(ra.index("Chương một"), ra.index("Chương hai"))
        self.assertLess(ra.index("Chương hai"), ra.index("Chương ba"))

    def test_bo_the_html_giu_lai_van_ban(self):
        data = _epub_gia(
            "<html><body><h1>Tiêu đề</h1><p>Đoạn <b>in đậm</b> ở đây.</p>"
            "</body></html>")
        ra = extract_text("t.epub", data)
        self.assertIn("Tiêu đề", ra)
        self.assertIn("Đoạn", ra)
        self.assertIn("in đậm", ra)
        self.assertNotIn("<b>", ra)
        self.assertNotIn("<p>", ra)

    def test_zip_hong_bao_loi_ro_rang(self):
        with self.assertRaises(UnsupportedFormat):
            extract_text("hong.epub", b"khong-phai-zip")

    def test_khong_co_trang_noi_dung_nao(self):
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
        with self.assertRaises(UnsupportedFormat):
            extract_text("rong.epub", buf.getvalue())


class DocxTest(unittest.TestCase):
    def test_trich_van_ban_theo_thu_tu(self):
        data = _docx_gia("Đoạn một.", "Đoạn hai.", "Đoạn ba.")
        ra = extract_text("truyen.docx", data)
        self.assertLess(ra.index("Đoạn một"), ra.index("Đoạn hai"))
        self.assertLess(ra.index("Đoạn hai"), ra.index("Đoạn ba"))

    def test_thieu_document_xml_bao_loi_ro_rang(self):
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types/>")
        with self.assertRaises(UnsupportedFormat):
            extract_text("thieu.docx", buf.getvalue())

    def test_zip_hong_bao_loi_ro_rang(self):
        with self.assertRaises(UnsupportedFormat):
            extract_text("hong.docx", b"khong-phai-zip")

    def test_xml_hong_bao_loi_ro_rang(self):
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/document.xml", b"<khong dong the>")
        with self.assertRaises(UnsupportedFormat):
            extract_text("hong-xml.docx", buf.getvalue())


class DinhDangKhongHoTroTest(unittest.TestCase):
    def test_pdf_bi_tu_choi_ro_rang(self):
        with self.assertRaises(UnsupportedFormat):
            extract_text("truyen.pdf", b"%PDF-1.4")

    def test_tep_qua_lon_bi_tu_choi_truoc_khi_giai_nen(self):
        with self.assertRaises(UnsupportedFormat):
            extract_text("to.txt", b"x" * (MAX_UPLOAD_BYTES + 1))

    def test_ten_tep_co_duong_dan_khong_gay_loi(self):
        """Path traversal trong TEN TEP khong duoc lam sap ham — chi anh
        huong phan doan duoi de chon nhanh xu ly."""
        self.assertEqual(
            extract_text("../../../etc/passwd.txt", b"noi dung"), "noi dung")


if __name__ == "__main__":
    unittest.main(verbosity=2)
