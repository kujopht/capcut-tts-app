"""
Trich van ban THO tu tung dinh dang tai len — TXT/HTML/EPUB/DOCX. Chuong
duoc tach RIENG o `chapter_split.py` tu van ban da trich; module nay chi
chiu trach nhiem "byte tho -> van ban doc duoc", khong biet gi ve chuong.

AN TOAN: EPUB/DOCX deu la file ZIP chua XML — parse bang
`defusedxml.ElementTree` (da la dependency cua backend, dung cho
`server/youtube_websub.py`), KHONG bao gio `xml.etree.ElementTree` truc
tiep tren du lieu nguoi dung tai len. Lop ZIP di qua `safe_zip.py` (gioi han
kich thuoc/ty le nen, chan duong dan dang ngo) TRUOC khi doc bat ky muc nao.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from defusedxml import ElementTree as DefusedET

from server.import_pipeline.safe_zip import UnsafeZipError, read_all_safe
from server.scraper.html_extract import extract as extract_html_page


class UnsupportedImportFormatError(Exception):
    pass


class CorruptImportFileError(Exception):
    """File tuyen bo la mot dinh dang nhung khong doc duoc nhu the — vd EPUB
    thieu `META-INF/container.xml`, DOCX thieu `word/document.xml`."""


def extract_text_txt(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_text_html(data: bytes) -> str:
    html = extract_text_txt(data)  # cung logic doan encoding voi TXT
    page = extract_html_page(html)
    return page.visible_text()


#: Namespace THAT cua OPF/container.xml (EPUB la chuan IDPF/W3C) — khai bao
#: tuong minh, KHONG doan tu tien to trong file (mot EPUB dung tien to khac
#: "opf"/"ns0" van phai khop dung URI nay).
_NS_CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
_NS_OPF = "http://www.idpf.org/2007/opf"


def extract_chapters_epub(data: bytes) -> List[Tuple[str, str]]:
    """Tra ve danh sach (tieu_de, van_ban) THEO DUNG THU TU `<spine>` cua
    EPUB — moi phan tu spine la MOT file XHTML that trong `<manifest>`.
    Tieu de lay tu the `<title>`/the tieu de dau tien cua chinh file XHTML
    do (EPUB thuong khong dat ten chuong trong OPF)."""
    try:
        muc = read_all_safe(data)
    except UnsafeZipError as exc:
        raise CorruptImportFileError(f"EPUB không an toàn để đọc: {exc}") from exc

    if "META-INF/container.xml" not in muc:
        raise CorruptImportFileError(
            "Thiếu META-INF/container.xml — không phải EPUB hợp lệ.")
    container = DefusedET.fromstring(muc["META-INF/container.xml"])
    rootfile = container.find(f".//{{{_NS_CONTAINER}}}rootfile")
    if rootfile is None or not rootfile.get("full-path"):
        raise CorruptImportFileError("Không tìm thấy rootfile OPF trong container.xml.")
    opf_path = rootfile.get("full-path")
    if opf_path not in muc:
        raise CorruptImportFileError(f"Rootfile khai báo nhưng không tồn tại: {opf_path!r}")
    opf_dir = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""

    opf = DefusedET.fromstring(muc[opf_path])
    manifest = {
        item.get("id"): item.get("href")
        for item in opf.findall(f".//{{{_NS_OPF}}}manifest/{{{_NS_OPF}}}item")
        if item.get("id") and item.get("href")
    }
    spine_ids = [
        itemref.get("idref")
        for itemref in opf.findall(f".//{{{_NS_OPF}}}spine/{{{_NS_OPF}}}itemref")
        if itemref.get("idref")
    ]

    ra = []
    for idref in spine_ids:
        href = manifest.get(idref)
        if not href:
            continue
        full_path = opf_dir + href
        if full_path not in muc:
            continue  # muc spine tro toi file khong ton tai — bo qua, khong nem loi
        page = extract_html_page(extract_text_txt(muc[full_path]))
        tieu_de = page.title or f"Chương {len(ra) + 1}"
        noi_dung = page.visible_text()
        if noi_dung:
            ra.append((tieu_de, noi_dung))
    return ra


_NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def extract_text_docx(data: bytes) -> str:
    """DOCX la mot file ZIP, noi dung that o `word/document.xml`. Ghep cac
    the `<w:p>` (doan van) thanh cac dong, moi `<w:t>` (chuoi van ban that)
    trong do noi truc tiep — DOCX co the tach mot cau thanh nhieu `<w:r>`/
    `<w:t>` do lich su chinh sua, nen PHAI noi trong cung doan truoc khi
    xuong dong, khong duoc xuong dong theo tung `<w:t>`."""
    try:
        muc = read_all_safe(data)
    except UnsafeZipError as exc:
        raise CorruptImportFileError(f"DOCX không an toàn để đọc: {exc}") from exc

    if "word/document.xml" not in muc:
        raise CorruptImportFileError(
            "Thiếu word/document.xml — không phải DOCX hợp lệ.")
    root = DefusedET.fromstring(muc["word/document.xml"])

    dong: List[str] = []
    for p in root.iter(f"{{{_NS_W}}}p"):
        phan: List[str] = []
        for t in p.iter(f"{{{_NS_W}}}t"):
            phan.append(t.text or "")
        dong.append("".join(phan))
    return "\n".join(dong)


def guess_format_from_filename(filename: str) -> Optional[str]:
    ten = (filename or "").lower()
    for ext in ("epub", "docx", "html", "htm", "txt", "zip"):
        if ten.endswith("." + ext):
            return "html" if ext == "htm" else ext
    return None
