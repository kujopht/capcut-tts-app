"""
Trich xuat sieu du lieu/van ban tu HTML bang `html.parser` co san cua
Python — CO Y khong them BeautifulSoup/lxml: quy mo hien tai (meta tags,
JSON-LD, danh sach lien ket, van ban hien thi) khong can mot bo parser DOM
day du. Xem docstring `server/scraper/__init__.py` cho ly do chon Tier 0
truoc Tier 1 (Scrapling).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

#: The KHONG BAO GIO dong gop van ban hien thi — noi dung cua chung (script,
#: style) khong phai la van ban doc duoc, va (nav/header/footer/aside)
#: thuong la dieu huong/quang cao lap lai tren moi trang, khong phai noi
#: dung chuong.
_NOISE_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside"}


@dataclass
class ExtractedPage:
    title: Optional[str] = None
    #: Khoa la thuoc tinh `name` HOAC `property` cua the meta (og:title,
    #: article:author, description, ...).
    meta: Dict[str, str] = field(default_factory=dict)
    #: Moi khoi JSON-LD da parse THANH CONG — khoi loi duoc bo qua am tham
    #: (mot so trang nhung JSON-LD hong khong lam hong ca trang).
    json_ld: List[Any] = field(default_factory=list)
    #: (href, van_ban_lien_ket) THEO DUNG THU TU xuat hien trong HTML.
    links: List[Tuple[str, str]] = field(default_factory=list)
    #: Van ban hien thi DA loai noise-tag, CHUA lam sach khoang trang —
    #: xem `visible_text()` cho ban da lam sach.
    _text_parts: List[str] = field(default_factory=list, repr=False)

    def visible_text(self) -> str:
        """Noi cac doan van ban hien thi, gop nhieu khoang trang/dong trong
        lien tiep thanh mot — buoc lam sach CHUNG cho moi adapter, tranh
        moi adapter tu viet lai logic nay theo cach khac nhau."""
        raw = "\n".join(p for p in self._text_parts if p.strip())
        # Gop nhieu dong trong lien tiep thanh toi da hai (giu ranh gioi
        # doan van), gop khoang trang ngang thanh mot.
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page = ExtractedPage()
        self._skip_depth = 0
        self._in_title = False
        self._in_json_ld = False
        self._json_ld_buffer: List[str] = []
        self._current_href: Optional[str] = None
        self._current_link_text: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_d = {k: v for k, v in attrs if v is not None}
        # JSON-LD PHAI duoc kiem TRUOC quy tac noise-tag chung: `<script>` la
        # mot noise tag (khong dong gop van ban hien thi), nhung mot khoi
        # `<script type="application/ld+json">` van can duoc DOC (chi khong
        # duoc dong gop vao van ban hien thi) — hai muc dich khac nhau tren
        # cung mot the.
        if tag == "script" and attrs_d.get("type") == "application/ld+json":
            self._in_json_ld = True
            self._json_ld_buffer = []
            return
        if tag in _NOISE_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = attrs_d.get("property") or attrs_d.get("name")
            content = attrs_d.get("content")
            if key and content is not None:
                self.page.meta[key] = content
        elif tag == "a" and "href" in attrs_d:
            self._current_href = attrs_d["href"]
            self._current_link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld:
            self._in_json_ld = False
            raw = "".join(self._json_ld_buffer).strip()
            if raw:
                try:
                    self.page.json_ld.append(json.loads(raw))
                except (json.JSONDecodeError, ValueError):
                    pass  # khoi JSON-LD hong — bo qua, khong lam hong ca trang.
            return
        if tag in _NOISE_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._current_href is not None:
            text = "".join(self._current_link_text).strip()
            self.page.links.append((self._current_href, text))
            self._current_href = None
            self._current_link_text = []

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._json_ld_buffer.append(data)
            return
        if self._skip_depth > 0:
            return
        if self._in_title:
            self.page.title = (self.page.title or "") + data
            return
        if self._current_href is not None:
            self._current_link_text.append(data)
        if data.strip():
            self.page._text_parts.append(data)


def extract(html: str) -> ExtractedPage:
    """Diem vao duy nhat cua module nay — parse mot chuoi HTML, tra ve
    `ExtractedPage`. KHONG nem loi tren HTML mo/khong hop le: `html.parser`
    da khoan dung san, va mot trang that thuong khong bao gio la XHTML
    chuan."""
    parser = _Parser()
    parser.feed(html)
    parser.close()
    page = parser.page
    if page.title:
        page.title = re.sub(r"\s+", " ", page.title).strip()
    return page
