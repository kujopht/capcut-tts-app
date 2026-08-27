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

#: The rong (void elements) trong HTML5 khong co the dong — tranh lam lech
#: stack the khi theo doi ranh gioi vung noi dung.
_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

#: Heuristic ranh gioi noi dung duong tinh (positive content-boundary) —
#: DANH SACH nhieu site, khong rieng MediaWiki (ten bien da tong quat hoa
#: sau khi them Royal Road, xem lich su sua doi). Neu HTML co mot the voi
#: class/id trong danh sach nay, CHI trich xuat van ban BEN TRONG the do,
#: loai bo UI-chrome (nav/sidebar/breadcrumb/tim kiem/footer/quang cao) bi
#: boc trong <div> thay vi the ngu nghia ma `_NOISE_TAGS` khong bat duoc.
#:
#: - `mw-parser-output`: MediaWiki (Wikipedia, Wikisource, ...) — uu tien
#:   nhat vi chi gom wikitext da parse, loai bo ca printfooter/catlinks.
#: - `chapter-content`: Royal Road — xac minh qua canary that (xem
#:   `site_registry.py`, domain `royalroad.com`).
_CONTENT_BOUNDARY_CLASSES = {"mw-parser-output", "chapter-content"}
#: `mw-content-text`: MediaWiki skin cu, fallback khi khong co
#: `mw-parser-output`.
_CONTENT_BOUNDARY_IDS = {"mw-content-text"}

#: Phase 3 Story Harvester V3 ("profile poisoning red team", fixture E):
#: lien ket TRONG cac vung nay KHONG duoc dua vao `page.links` — mot
#: trang muc luc that co the co khung "co the ban quan tam"/"binh
#: luan"/quang cao VOI lien ket dung CHINH XAC hinh dang URL voi chuong
#: that (vd `/chuong/{id}` toan cuc, khong rieng theo truyen), khien
#: `discovery.py::_find_link_clusters` GOP NHAM lien ket cua MOT TRUYEN
#: KHAC vao cum chuong — tai hien duoc that qua fixture (widget "de
#: xuat" 3 lien ket lam `chapter_count_estimate` sai tu 5 thanh 8).
#:
#: CO Y HEP hon `content_extraction._REJECT_HINT_RE`: KHONG bao gom
#: "chapter-list"/"chapter-nav"/"pagination"/"sidebar"/"widget"/"popup"/
#: "modal"/"banner"/"cookie"/"breadcrumb" — nhung tu do hoac la noi
#: CHUA lien ket chuong THAT su (vd chinh `class="chapter-list"`, xuat
#: hien trong hau het fixture chuong that cua bo test nay), hoac qua
#: chung chung/rui ro cao neu dung de LOAI BO lien ket hoan toan (khac
#: voi chi dung lam "goi y uu tien" nhu trong content_extraction.py).
#: CHI loai cac danh muc CO DO CHAC CHAN CAO la "chac chan khong phai
#: chuong" — quang cao/binh luan/de xuat/mang xa hoi/dang nhap.
_LINK_REJECT_HINT_RE = re.compile(
    r"(comment|binh.?luan|advert|\bads?\b|sponsor|"
    r"related|recommend|de.?xuat|goi.?y|"
    r"social|share|chia.?se|"
    r"login|signup|sign.?up|subscribe|newsletter)",
    re.IGNORECASE,
)


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
    #: `True` neu trang co mot the KHOP `_CONTENT_BOUNDARY_CLASSES`/
    #: `_CONTENT_BOUNDARY_IDS` da xac minh tay (Wikisource/Royal Road) —
    #: `visible_text()` khi do la KET QUA DA XAC MINH, khong can qua
    #: `content_extraction.py` (Phase 6 Story Harvester V3). `False` nghia
    #: la `visible_text()` la "lay het van ban con lai" (tho), va noi goi
    #: (vd `GenericIndexAdapter.normalize_chapter`) NEN dung
    #: `content_extraction_v3` thay vi tin thang gia tri nay cho cac nguon
    #: chua xac minh.
    boundary_matched: bool = False

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
        #: Phase 3 ("profile poisoning red team") — dem long nhau O(1)/the,
        #: CUNG phong cach voi `_skip_depth`: > 0 nghia la dang o TRONG mot
        #: vung quang cao/binh luan/de xuat/dang nhap, cac lien ket <a> gap
        #: trong luc nay KHONG duoc them vao `page.links` (xem
        #: `_LINK_REJECT_HINT_RE`).
        self._link_skip_depth = 0
        self._in_title = False
        self._in_json_ld = False
        self._json_ld_buffer: List[str] = []
        self._current_href: Optional[str] = None
        self._current_link_text: List[str] = []

        #: (is_primary, is_secondary) day cho MOI the mo khong-rong, pop VO
        #: DIEU KIEN (khong tim ten khop) tren MOI the dong — O(1) moi the,
        #: tranh do thi O(n^2) tren HTML hong/doi thu voi nhieu the mo khong
        #: dong (xem review Codex). Cung phong cach voi `_skip_depth` co san
        #: (dem long nhau don gian, khong khop ten) — HTML that thuong khong
        #: bao gio dong the dung, du lech nho vi qua tren HTML hong la danh
        #: doi chap nhan duoc, giong triet ly khoan dung cua module nay.
        self._tag_stack: List[Tuple[bool, bool, bool]] = []
        self._primary_boundary_depth = 0
        self._secondary_boundary_depth = 0
        #: Da TUNG thay ranh gioi nay hay chua (khac voi "co van ban ben
        #: trong hay khong") — phan biet "trang that su rong/chi co anh" (van
        #: phai tra ve RONG, khong fallback ve toan trang) voi "khong co
        #: ranh gioi nay tren trang" (fallback dung).
        self._primary_boundary_seen = False
        self._secondary_boundary_seen = False
        self._all_text_parts: List[str] = []
        self._primary_boundary_parts: List[str] = []
        self._secondary_boundary_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_d = {k: v for k, v in attrs if v is not None}
        classes = set(attrs_d.get("class", "").split())
        tag_id = attrs_d.get("id", "")

        is_primary = bool(_CONTENT_BOUNDARY_CLASSES.intersection(classes))
        is_secondary = tag_id in _CONTENT_BOUNDARY_IDS
        is_link_reject = bool(_LINK_REJECT_HINT_RE.search(
            " ".join(classes) + " " + tag_id))

        if is_primary:
            self._primary_boundary_depth += 1
            self._primary_boundary_seen = True
        if is_secondary:
            self._secondary_boundary_depth += 1
            self._secondary_boundary_seen = True
        if is_link_reject:
            self._link_skip_depth += 1

        # JSON-LD PHAI duoc kiem TRUOC quy tac noise-tag chung: `<script>` la
        # mot noise tag (khong dong gop van ban hien thi), nhung mot khoi
        # `<script type="application/ld+json">` van can duoc DOC (chi khong
        # duoc dong gop vao van ban hien thi) — hai muc dich khac nhau tren
        # cung mot the.
        if tag not in _VOID_TAGS:
            self._tag_stack.append((is_primary, is_secondary, is_link_reject))

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
                except (json.JSONDecodeError, ValueError, RecursionError):
                    # Khoi JSON-LD hong/qua long nhau (vd tan cong co chu
                    # dich, mang so nguyen long hang nghin cap — phat hien
                    # qua review doc lap, Codex: `RecursionError` la
                    # `RuntimeError`, KHONG PHAI `ValueError`, nen truoc
                    # ban sua nay se thoat ra NGOAI `extract()` khong bat —
                    # cung lop loi voi RecursionError da sua trong
                    # `content_extraction.py`, commit 04410fe) — bo qua, KHONG
                    # lam hong ca trang.
                    pass
        elif tag in _NOISE_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._current_href is not None:
            text = "".join(self._current_link_text).strip()
            if self._link_skip_depth <= 0:
                self.page.links.append((self._current_href, text))
            self._current_href = None
            self._current_link_text = []

        if tag not in _VOID_TAGS and self._tag_stack:
            is_primary, is_secondary, is_link_reject = self._tag_stack.pop()
            if is_link_reject:
                self._link_skip_depth = max(0, self._link_skip_depth - 1)
            if is_primary:
                self._primary_boundary_depth = max(0, self._primary_boundary_depth - 1)
            if is_secondary:
                self._secondary_boundary_depth = max(0, self._secondary_boundary_depth - 1)

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
            self._all_text_parts.append(data)
            if self._primary_boundary_depth > 0:
                self._primary_boundary_parts.append(data)
            if self._secondary_boundary_depth > 0:
                self._secondary_boundary_parts.append(data)


def extract(html: str) -> ExtractedPage:
    """Diem vao duy nhat cua module nay — parse mot chuoi HTML, tra ve
    `ExtractedPage`. KHONG nem loi tren HTML mo/khong hop le: `html.parser`
    da khoan dung san, va mot trang that thuong khong bao gio la XHTML
    chuan."""
    parser = _Parser()
    parser.feed(html)
    parser.close()
    page = parser.page
    if parser._primary_boundary_seen:
        # Ranh gioi CO ton tai — du RONG (vd trang chi co anh) van phai tra
        # ve RONG, KHONG fallback ve toan trang (se keo lai UI-chrome).
        page._text_parts = parser._primary_boundary_parts
        page.boundary_matched = True
    elif parser._secondary_boundary_seen:
        page._text_parts = parser._secondary_boundary_parts
        page.boundary_matched = True
    else:
        page._text_parts = parser._all_text_parts
    if page.title:
        page.title = re.sub(r"\s+", " ", page.title).strip()
    return page
