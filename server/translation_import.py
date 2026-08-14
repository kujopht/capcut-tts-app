"""
Trich van ban tho tu tep tai len — CHI dung thu vien CHUAN cua Python.

VI SAO KHONG DUNG `python-docx`/`ebooklib`: `python-docx` chi khai bao o
`requirements-gui.txt` (desktop), va them mot phu thuoc moi vao backend web
la mot quyet dinh can duoc yeu cau ro rang, khong phai tu quyet trong luc
viet tinh nang khac (xem CLAUDE.md — "Không cài gói nào bằng tay"). May
man la CA HAI dinh dang deu chi la mot file ZIP chua XML/(X)HTML ben trong,
nen trich THO bang `zipfile` + regex bo the la du cho MVP.

HAN CHE DA BIET (ghi trong bao cao V5, khong gia vo hoan hao):
  - EPUB: doc theo THU TU TEP trong zip (khong doc file .opf de lay dung thu
    tu spine) — voi hau het epub xuat ban gon gang thi thu tu file da dung,
    nhung khong dam bao 100%.
  - DOCX: mat toan bo dinh dang (in dam, in nghieng...) — chi lay VAN BAN
    THO, dung dung muc dich (dua vao dich, khong phai dua vao xuat ban lai
    nguyen dinh dang).
  - Khong ho tro anh nhung/bang bieu trong ca hai dinh dang.
"""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from typing import Tuple
from xml.etree import ElementTree as ET

from server.translation import UnsupportedFormat

#: Duoi tep ho tro Phase 1 — xem yeu cau goc muc 3.
DINH_DANG_HO_TRO: Tuple[str, ...] = (".txt", ".epub", ".docx")

#: Tran kich thuoc tep tho (truoc khi giai nen/giai ma) — chan mot zip-bomb
#: hay mot tep khong lo lam nghen tien trinh.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _an_toan_ten_tep(filename: str) -> str:
    """Chi lay PHAN DUOI, bo moi duong dan — chong path traversal khi log."""
    sach = (filename or "").replace("\\", "/").split("/")[-1]
    return sach[-200:] or "tep"


def _duoi_tep(filename: str) -> str:
    ten = _an_toan_ten_tep(filename).lower()
    if "." not in ten:
        return ""
    return "." + ten.rsplit(".", 1)[-1]


_THE_HTML = re.compile(r"<[^>]+>")
_KHOANG_TRANG_THUA = re.compile(r"[ \t]+\n")
_NHIEU_DONG_TRONG = re.compile(r"\n{3,}")


def _bo_the_html(doan: str) -> str:
    """The -> xuong dong (giu ranh gioi doan), thuc the HTML pho bien -> ky tu."""
    sach = re.sub(r"(?i)<br\s*/?>", "\n", doan)
    sach = re.sub(r"(?i)</p>", "\n\n", sach)
    sach = _THE_HTML.sub("", sach)
    sach = (sach.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&#39;", "'"))
    sach = _KHOANG_TRANG_THUA.sub("\n", sach)
    return _NHIEU_DONG_TRONG.sub("\n\n", sach).strip()


def _tu_txt(data: bytes) -> str:
    """
    Doan encoding — KHONG co `chardet` (chua khai bao trong
    `server/requirements.txt`), nen tu lam mot phep doan don gian nhung AN
    TOAN: kiem BOM truoc, roi thu cac encoding THEO DO NGHIEM NGAT giam dan.

    BAY DA VAP: `utf-16` (khong BOM) chap nhan GAN NHU MOI chuoi byte co do
    dai chan va tra ve ket qua "thanh cong" — chi la rac, khong nem loi. Thu
    no som trong danh sach se NUOT mat co hoi thu gb18030/big5 that su dung
    cho van ban Trung khong BOM (truong hop pho bien nhat cua tinh nang nay).
    Vi vay `utf-16` mu (khong BOM) KHONG nam trong danh sach — chi dung khi
    co BOM ro rang.
    """
    if data[:3] == b"\xef\xbb\xbf":
        return data.decode("utf-8-sig")
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    for ma in ("utf-8", "gb18030", "big5"):
        try:
            return data.decode(ma)
        except (UnicodeDecodeError, LookupError):
            continue
    # Khong con encoding nao thu duoc chinh xac — giai ma THO, thay ky tu
    # hong bang U+FFFD thay vi nem loi: mot tep .txt bat thuong van dang cho
    # nguoi dung xem, con hon mot loi 400 vo ich.
    return data.decode("utf-8", errors="replace")


def _tu_epub(data: bytes) -> str:
    """
    EPUB = zip chua cac tep `.xhtml`/`.html`/`.htm` (noi dung) + `.opf`/`.ncx`
    (sieu du lieu, bo qua). Doc THEO THU TU TEN TEP trong zip — han che da
    biet, xem docstring dau file.
    """
    try:
        zf = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsupportedFormat("Tệp EPUB không hợp lệ (không mở được).") from exc
    with zf:
        ten_noi_dung = sorted(
            n for n in zf.namelist()
            if n.lower().endswith((".xhtml", ".html", ".htm"))
            and "meta-inf" not in n.lower())
        if not ten_noi_dung:
            raise UnsupportedFormat(
                "Không tìm thấy nội dung đọc được trong tệp EPUB.")
        phan = []
        for ten in ten_noi_dung:
            try:
                tho = zf.read(ten).decode("utf-8", errors="replace")
            except KeyError:
                continue
            sach = _bo_the_html(tho)
            if sach:
                phan.append(sach)
    return "\n\n".join(phan)


def _tu_docx(data: bytes) -> str:
    """
    DOCX = zip chua `word/document.xml` (OOXML). Doc CHI cac the `<w:t>`
    (van ban hien thi) theo THU TU XUAT HIEN trong XML — thu tu do CHINH LA
    thu tu doc, khac EPUB (khong can doan thu tu).
    """
    try:
        zf = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsupportedFormat("Tệp DOCX không hợp lệ (không mở được).") from exc
    with zf:
        try:
            xml_tho = zf.read("word/document.xml")
        except KeyError as exc:
            raise UnsupportedFormat(
                "Không tìm thấy nội dung trong tệp DOCX "
                "(word/document.xml)."
            ) from exc
    try:
        goc = ET.fromstring(xml_tho)
    except ET.ParseError as exc:
        raise UnsupportedFormat("Không đọc được cấu trúc XML của tệp DOCX.") from exc

    NS_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    doan_van = []
    for doan in goc.iter(f"{NS_W}p"):
        chu = "".join(node.text or "" for node in doan.iter(f"{NS_W}t"))
        doan_van.append(chu)
    return "\n\n".join(d for d in doan_van if d.strip())


def extract_text(filename: str, data: bytes) -> str:
    """
    Trich van ban THO tu mot tep da tai len. Nem `UnsupportedFormat` neu duoi
    tep khong nam trong `DINH_DANG_HO_TRO`, hoac noi dung hong.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise UnsupportedFormat(f"Tệp vượt quá {mb} MB.")
    duoi = _duoi_tep(filename)
    if duoi == ".txt":
        return _tu_txt(data)
    if duoi == ".epub":
        return _tu_epub(data)
    if duoi == ".docx":
        return _tu_docx(data)
    raise UnsupportedFormat(
        f"Định dạng '{duoi or '(không rõ)'}' chưa được hỗ trợ. "
        f"Chấp nhận: {', '.join(DINH_DANG_HO_TRO)}.")
