"""server/import_pipeline/formats.py + safe_zip.py — dinh dang tai len."""
from __future__ import annotations

import io
import unittest
import zipfile

from server.import_pipeline import formats
from server.import_pipeline.safe_zip import UnsafeZipError, inspect_zip


def _tao_epub(chapters):
    """chapters: List[(id, href, html_noi_dung)] — tra ve byte EPUB toi
    gian nhung THAT (container.xml -> OPF -> spine -> XHTML), du de
    `extract_chapters_epub` doc dung."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""")
        manifest_items = "\n".join(
            f'<item id="{cid}" href="{href}" media-type="application/xhtml+xml"/>'
            for cid, href, _ in chapters)
        spine_items = "\n".join(f'<itemref idref="{cid}"/>' for cid, _, _ in chapters)
        zf.writestr("OEBPS/content.opf", f"""<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <manifest>{manifest_items}</manifest>
  <spine>{spine_items}</spine>
</package>""")
        for _, href, html in chapters:
            zf.writestr(f"OEBPS/{href}", html)
    return buf.getvalue()


def _tao_docx(paragraphs):
    """paragraphs: List[str] — tra ve byte DOCX toi gian voi
    word/document.xml that."""
    buf = io.BytesIO()
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join(f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>' for p in paragraphs)
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml",
                    f'<w:document {ns}><w:body>{body}</w:body></w:document>')
    return buf.getvalue()


class ExtractTextTxtTest(unittest.TestCase):
    def test_doc_duoc_utf8(self):
        self.assertEqual(formats.extract_text_txt("Xin chào".encode("utf-8")), "Xin chào")


class ExtractTextHtmlTest(unittest.TestCase):
    def test_lay_van_ban_hien_thi(self):
        html = b"<html><body><p>Noi dung chuong.</p></body></html>"
        self.assertIn("Noi dung chuong.", formats.extract_text_html(html))


class ExtractChaptersEpubTest(unittest.TestCase):
    def test_doc_dung_thu_tu_spine(self):
        data = _tao_epub([
            ("c1", "chuong1.xhtml", "<html><body><h1>Chương 1</h1><p>Nội dung một.</p></body></html>"),
            ("c2", "chuong2.xhtml", "<html><body><h1>Chương 2</h1><p>Nội dung hai.</p></body></html>"),
        ])
        ket_qua = formats.extract_chapters_epub(data)
        self.assertEqual(len(ket_qua), 2)
        self.assertIn("Nội dung một.", ket_qua[0][1])
        self.assertIn("Nội dung hai.", ket_qua[1][1])

    def test_thieu_container_xml_nem_loi_ro_rang(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("random.txt", "not an epub")
        with self.assertRaises(formats.CorruptImportFileError):
            formats.extract_chapters_epub(buf.getvalue())


class ExtractTextDocxTest(unittest.TestCase):
    def test_noi_cac_doan_van(self):
        data = _tao_docx(["Đoạn một.", "Đoạn hai."])
        text = formats.extract_text_docx(data)
        self.assertIn("Đoạn một.", text)
        self.assertIn("Đoạn hai.", text)

    def test_thieu_document_xml_nem_loi_ro_rang(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("random.txt", "not a docx")
        with self.assertRaises(formats.CorruptImportFileError):
            formats.extract_text_docx(buf.getvalue())


class SafeZipTest(unittest.TestCase):
    def test_zip_binh_thuong_di_qua(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("a.txt", "noi dung")
        entries = inspect_zip(buf.getvalue())
        self.assertEqual(len(entries), 1)

    def test_duong_dan_dang_ngo_bi_tu_choi(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../etc/passwd", "noi dung doc hai")
        with self.assertRaises(UnsafeZipError):
            inspect_zip(buf.getvalue())

    def test_qua_nhieu_muc_bi_tu_choi(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for i in range(2001):
                zf.writestr(f"f{i}.txt", "x")
        with self.assertRaises(UnsafeZipError):
            inspect_zip(buf.getvalue())

    def test_ty_le_nen_bat_thuong_bi_tu_choi(self):
        """Mo phong zip bomb: mot chuoi lap lai nen RAT tot."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("bomb.txt", "A" * 10_000_000)
        with self.assertRaises(UnsafeZipError):
            inspect_zip(buf.getvalue())


class GuessFormatFromFilenameTest(unittest.TestCase):
    def test_nhan_dung_cac_duoi_ho_tro(self):
        self.assertEqual(formats.guess_format_from_filename("truyen.epub"), "epub")
        self.assertEqual(formats.guess_format_from_filename("Truyen.DOCX"), "docx")
        self.assertEqual(formats.guess_format_from_filename("a.htm"), "html")
        self.assertIsNone(formats.guess_format_from_filename("a.pdf"))


if __name__ == "__main__":
    unittest.main()
