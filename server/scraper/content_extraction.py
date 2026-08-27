"""
Trich xuat noi dung chuong V3 — Phase 6 cua Story Harvester V3.

VI SAO CAN FILE NAY (khac `html_extract.py`): `html_extract.extract()` chi
biet trich "sach" khi trang co MOT the khop `_CONTENT_BOUNDARY_CLASSES`/
`_CONTENT_BOUNDARY_IDS} DA XAC MINH TAY (hien tai: MediaWiki, Royal Road) —
neu khong khop, no lui ve "lay HET van ban con lai tren trang" (tho, dinh
UI-chrome). Module nay la mot bo CHAM DIEM UNG VIEN tong quat, dung cho
MOI nguon CHUA duoc xac minh tay (SiteProfile hoc duoc, trang chuong mau
luc kham pha) — KHONG BAO GIO thay the co che boundary DA XAC MINH cua
`html_extract.py` (xem `ExtractedPage.boundary_matched`: `True` thi dung
thang `visible_text()`, `False` thi qua module nay).

THUAT TOAN (lay cam hung tu Mozilla Readability, don gian hoa cho quy mo
truyen chu — khong can mot bo DOM day du):

    1. Dung `_TreeBuilder` (MOT lan quet HTMLParser) xay CAY nhe cac the
       "khoi" (div/article/section/main/td/body) — moi nut tich luy do dai
       van ban RIENG, do dai van ban trong <a> (mat do lien ket), so doan
       <p>, van ban tieu de h1-h6 BEN TRONG no.
    2. MOT nut co class/id khop `_REJECT_HINT_RE` (binh luan, chia se,
       quang cao, sidebar, "de xuat", breadcrumb, phan trang, dieu huong
       chuong, dang nhap, ...) bi LOAI KHOI cay TRUOC KHI tich luy — van
       ban cua no KHONG duoc cong vao bat ky to tien nao (loai bo "vung rac
       long trong mot ung vien tot" — vd binh luan nam SAU noi dung chuong
       nhung CUNG the cha voi no).
    3. Cham diem MOI ung vien con lai: thuong ngu nghia (article/main),
       tinh lien tuc doan van (so <p> co van ban), do dai hop ly, PHAT mat
       do lien ket cao (trang dieu huong), THUONG lien quan tieu de (co
       h1-h6 khop tieu de chuong da biet), PHAT do sau DOM qua lon (widget
       nho nam sau).
    4. Ung vien diem CAO NHAT thang — CONFIDENCE HIGH/MEDIUM/LOW theo diem
       tuyet doi VA khoang cach voi ung vien thu hai (chien thang khong ro
       rang = tin cay thap hon). Diem qua thap: KHONG tra ve mot phong doan
       te, tra ve LOW + van ban rong — noi goi (xem
       `MIN_CONFIDENT_TOTAL_TEXT_LEN`) tu quyet dinh co dua chuong nay vao
       hang doi duyet voi canh bao hay khong (KHONG am tham chap nhan trich
       xuat yeu, dung theo yeu cau Phase 6).

BOILERPLATE LAP LAI QUA NHIEU TRANG: `known_boilerplate_hashes` (tuy chon)
la tap sha256 CAC DOAN VAN (khoi <p>) da thay o NHUNG CHUONG TRUOC cua
CUNG series — mot doan xuat hien Y HET (vd loi keu goi ung ho co dinh tren
moi trang) bi loai KHOI ket qua ngay ca khi nam BEN TRONG ung vien thang.
Ham tra ve ca `paragraph_hashes` cua KET QUA CUOI CUNG de noi goi (xem
`adapters/generic_index_adapter.py`) tich luy dan qua tung chuong.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Tuple

_NOISE_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside"}
_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
#: The "khoi" duoc xet lam UNG VIEN vung noi dung — the inline (span, a,
#: em, ...) khong bao gio la ung vien (qua nho/khong co y nghia cau truc).
_CANDIDATE_TAGS = {"div", "article", "section", "main", "td", "body"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_PARAGRAPH_LIKE_TAGS = {"p"}

#: The/class/id khop CAI NAY bi loai KHOI cay TRUOC KHI cham diem — van
#: ban cua no (VA moi con no) KHONG duoc cong vao bat ky to tien nao. Danh
#: sach RONG RAI CO CHU DICH (nhieu bien the ten class thuc te) nhung CHI
#: la GOI Y loai tru, khong phai danh sach dong cung — site dung ten hoan
#: toan khac se khong bi anh huong (tot, khong bi loai oan) nhung cung
#: khong duoc loai junk tuong ung (dung dan, module nay KHONG doan bua).
_REJECT_HINT_RE = re.compile(
    r"(comment|binh.?luan|share|chia.?se|social|sponsor|advert|\bads?\b|"
    r"sidebar|related|recommend|de.?xuat|breadcrumb|pagination|page.?nav|"
    r"chapter.?list|chapter.?nav|chap.?nav|next.?chap|prev.?chap|"
    r"login|signup|sign.?up|subscribe|newsletter|cookie|popup|modal|"
    r"site.?description|tagline|banner|widget)",
    re.IGNORECASE,
)
#: The/class/id khop CAI NAY duoc UU TIEN khi cham diem (khong bat buoc)
#: — cung tu khoa voi `discovery.py::_CONTAINER_HINT_RE` nhung dung o day
#: cho TUNG CHUONG cu the (khac discovery, chi dung MOT LAN luc kham pha
#: site chua biet).
_CONTAINER_HINT_RE = re.compile(
    r"(content|chapter|chuong|article|entry|post|story|truyen|reading|"
    r"noi.?dung|main.?text)",
    re.IGNORECASE,
)
_SEMANTIC_TAG_BONUS = {"article": 30, "main": 25, "section": 8}
#: Diem toi thieu de duoc coi la trich xuat CO CO SO (khong phai doan bua)
#: — duoi nguong nay, tra ve LOW du van co "ung vien thang" nao do.
_MIN_SCORE_FOR_MEDIUM = 15
_MIN_SCORE_FOR_HIGH = 40
#: Chenh lech diem TOI THIEU voi ung vien THU HAI de duoc coi la HIGH — hai
#: ung vien diem gan bang nhau nghia la thuat toan KHONG chac chan, du ung
#: vien thang co diem tuyet doi cao.
_MIN_MARGIN_FOR_HIGH = 10
#: So ky tu van ban toi thieu (SAU khi loai reject-hint) de mot chuong
#: duoc coi la co noi dung THAT SU, khong phai trang loi/placeholder rong.
MIN_CONFIDENT_TOTAL_TEXT_LEN = 80


class ExtractionConfidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ExtractionResult:
    clean_text: str
    confidence: ExtractionConfidence
    #: Mo ta ung vien thang (vd "div.chapter-body") — `None` neu khong ung
    #: vien nao co van ban (trang rong/loi).
    container_signature: Optional[str]
    #: sha256 cac DOAN <p> (van ban da chuan hoa khoang trang) co mat trong
    #: `clean_text` cuoi cung — dung cho noi goi tich luy qua nhieu chuong
    #: (xem docstring module, "BOILERPLATE LAP LAI").
    paragraph_hashes: Set[str] = field(default_factory=set)
    #: So vung con bi loai vi khop `_REJECT_HINT_RE` — bang chung cho
    #: operator/log, khong anh huong logic.
    rejected_zone_count: int = 0
    #: So doan bi loai vi TRUNG voi `known_boilerplate_hashes` da truyen
    #: vao (xem tham so cung ten cua `extract_content_v3`).
    boilerplate_paragraph_count: int = 0


def _normalize_for_compare(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _paragraph_hash(text: str) -> str:
    return hashlib.sha256(_normalize_for_compare(text).encode("utf-8")).hexdigest()


class _Node:
    __slots__ = (
        "tag", "sig", "depth", "children", "own_text_parts",
        "own_link_text_len", "heading_texts", "is_paragraph", "rejected",
    )

    def __init__(self, tag: str, sig: Optional[str], depth: int) -> None:
        self.tag = tag
        self.sig = sig
        self.depth = depth
        self.children: List["_Node"] = []
        self.own_text_parts: List[str] = []
        self.own_link_text_len = 0
        self.heading_texts: List[str] = []
        self.is_paragraph = tag in _PARAGRAPH_LIKE_TAGS
        self.rejected = False


class _TreeBuilder(HTMLParser):
    """MOT lan quet xay cay nhe cac the "khoi" (xem `_CANDIDATE_TAGS`) —
    the KHONG phai khoi (span, em, a, ...) KHONG tao nut rieng, van ban cua
    chung duoc gan cho nut khoi GAN NHAT (cha) — du de cham diem, khong can
    mo phong toan bo DOM."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", None, 0)
        self._block_stack: List[_Node] = [self.root]
        self._skip_depth = 0
        self._in_heading = False
        self._heading_buffer: List[str] = []
        self._in_link = False
        self._link_buffer: List[str] = []
        #: (tag, la_khoi) day cho MOI the khong-rong — O(1)/the, cung
        #: phong cach voi `html_extract._Parser`/`discovery._ContainerScanner`.
        self._tag_stack: List[Tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_d = {k: v for k, v in attrs if v is not None}
        la_khoi = False

        if tag in _NOISE_TAGS:
            self._skip_depth += 1
        elif tag in _HEADING_TAGS:
            self._in_heading = True
            self._heading_buffer = []
        elif tag == "a":
            self._in_link = True
            self._link_buffer = []

        if tag in _CANDIDATE_TAGS or tag in _PARAGRAPH_LIKE_TAGS:
            la_khoi = True
            classes = attrs_d.get("class", "")
            tag_id = attrs_d.get("id", "")
            sig = None
            for cls in classes.split():
                sig = f"{tag}.{cls}"
                break
            if sig is None and tag_id:
                sig = f"{tag}#{tag_id}"

            cha = self._block_stack[-1]
            node = _Node(tag, sig, cha.depth + 1)
            if _REJECT_HINT_RE.search(classes) or _REJECT_HINT_RE.search(tag_id):
                node.rejected = True
            cha.children.append(node)
            self._block_stack.append(node)

        if tag not in _VOID_TAGS:
            self._tag_stack.append((tag, la_khoi))

    def handle_endtag(self, tag: str) -> None:
        if tag in _NOISE_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _HEADING_TAGS and self._in_heading:
            self._in_heading = False
            text = "".join(self._heading_buffer).strip()
            if text and len(self._block_stack) > 0:
                self._block_stack[-1].heading_texts.append(text)
        elif tag == "a" and self._in_link:
            self._in_link = False
            text_len = len("".join(self._link_buffer))
            if self._block_stack:
                self._block_stack[-1].own_link_text_len += text_len

        if tag in _VOID_TAGS:
            return
        if self._tag_stack:
            popped_tag, la_khoi = self._tag_stack.pop()
            if la_khoi and len(self._block_stack) > 1:
                self._block_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_heading:
            self._heading_buffer.append(data)
        if self._in_link:
            self._link_buffer.append(data)
        if data.strip() and self._block_stack:
            self._block_stack[-1].own_text_parts.append(data)


def _own_text(node: _Node) -> str:
    return "".join(node.own_text_parts)


def _collect_all(root: "_Node") -> Dict[int, Tuple[str, int, int, int, List[str]]]:
    """Tra ve `{id(node): (van_ban_gop, tong_do_dai, do_dai_lien_ket,
    so_doan_van_co_chu, tieu_de_gop)}` cho MOI nut trong cay (BO QUA con
    `rejected` khi cong don vao cha) — duyet POST-ORDER LAP (KHONG DE QUY):
    mot trang HTML that co the long sau hang nghin cap the (vd wrapper
    lap lai nhieu lan), va ban de quy ban dau (mot ham/nut) tung tran gioi
    han de quy mac dinh cua Python (~1000) tren HTML nhu vay, nem
    `RecursionError` khong duoc `pipeline.py` bat rieng, lam DUNG CA DOT
    quet vi MOT trang loi — phat hien qua review doc lap (Codex, tai hien
    that voi ~999 the `<div>` long nhau)."""
    ket_qua: Dict[int, Tuple[str, int, int, int, List[str]]] = {}
    #: (nut, DA_day_con_chua) — lan dau gap MOT nut: day lai no (danh dau DA
    #: xu ly) roi day TAT CA con hop le; lan hai gap LAI (sau khi moi con da
    #: co ket qua trong `ket_qua`): tinh toan that su cho no.
    ngan_xep: List[Tuple["_Node", bool]] = [(root, False)]
    while ngan_xep:
        node, da_day_con = ngan_xep.pop()
        if not da_day_con:
            ngan_xep.append((node, True))
            for con in node.children:
                if not con.rejected:
                    ngan_xep.append((con, False))
            continue

        text_parts = [_own_text(node)]
        total_len = len(_own_text(node).strip())
        link_len = node.own_link_text_len
        para_count = 1 if (node.is_paragraph and total_len > 0) else 0
        headings = list(node.heading_texts)
        for con in node.children:
            if con.rejected:
                continue
            con_text, con_len, con_link, con_para, con_headings = ket_qua[id(con)]
            text_parts.append(con_text)
            total_len += con_len
            link_len += con_link
            para_count += con_para
            headings.extend(con_headings)

        ket_qua[id(node)] = (
            "\n".join(t for t in text_parts if t.strip()), total_len, link_len,
            para_count, headings)
    return ket_qua


#: So ky tu TOI THIEU de mot con-ung-vien duoc coi la "dang ke" khi dem
#: `so_con_ung_vien_dang_ke` (xem `_score`) — duoi nguong nay coi nhu
#: khong dang, tranh phat oan mot wrapper co MOT con that su + vai the
#: khoi rong/trang trai xung quanh.
_NGUONG_CON_UNG_VIEN_DANG_KE = 100
#: Phat MOI con-ung-vien dang ke THEM (tinh tu con thu HAI tro di) — mot
#: nut bao boc NHIEU khoi noi dung dang ke RIENG BIET (vd "than chuong" +
#: "tieu su tac gia" + "muc luc" deu la <div> con truc tiep) nhieu kha nang
#: la MOT WRAPPER THO, khong phai vung noi dung chuong that su — uu tien
#: mot con CU THE HON thay vi ca khoi cha gom tat ca — phat hien qua review
#: doc lap (Codex): mot <article> bao mot div.chapter-content that VA mot
#: khoi "gioi thieu tac gia"/"danh gia" khong khop reject-hint co the
#: thang nho diem tong cao hon, ke ca noi dung khong lien quan cua khoi kia.
_PHAT_MOI_CON_UNG_VIEN_THEM = 25


def _score(node: _Node, total_len: int, link_len: int, para_count: int,
          headings: List[str], chapter_title: Optional[str],
          so_con_ung_vien_dang_ke: int = 0) -> float:
    if total_len <= 0:
        return -1e9

    score = 0.0
    score += _SEMANTIC_TAG_BONUS.get(node.tag, 0)
    if node.sig and _CONTAINER_HINT_RE.search(node.sig):
        score += 12
    score += min(para_count * 3, 30)
    score += min(total_len // 100, 20)

    link_density = link_len / total_len if total_len else 1.0
    score -= link_density * 40
    score -= _PHAT_MOI_CON_UNG_VIEN_THEM * max(0, so_con_ung_vien_dang_ke - 1)

    if chapter_title:
        chuan_hoa_tieu_de = _normalize_for_compare(chapter_title)
        if chuan_hoa_tieu_de and any(
                chuan_hoa_tieu_de in _normalize_for_compare(h)
                or _normalize_for_compare(h) in chuan_hoa_tieu_de
                for h in headings if h):
            score += 15

    if node.depth > 12:
        score -= 10
    if node.tag == "body":
        # `body` la ung vien DU PHONG cuoi cung — luon co the "thang" vi
        # gom TAT CA van ban, nhung do chinh la van de (khong loc duoc UI-
        # chrome con lai ngoai NOISE_TAGS/reject-hint). Phat de cac ung
        # vien CU THE HON duoc uu tien khi co.
        score -= 20

    return score


#: Ty le TOI THIEU van ban cua con SO VOI cha de duoc uu tien thay cha —
#: con phai chiem DA SO ro rang (khong chi vai phan tram), tranh uu tien
#: nham mot con chi TINH CO co ten khop tu khoa nhung thuc ra rat nho.
_TY_LE_TOI_THIEU_UU_TIEN_CON = 0.5


def _uu_tien_con_cu_the_hon(
        thang: _Node, van_ban_cha: str,
        tat_ca_ket_qua: Dict[int, Tuple[str, int, int, int, List[str]]],
) -> Tuple[str, Optional[str]]:
    """Xem comment goi ham (`extract_content_v3`) — tra ve `(van_ban,
    chu_ky_ghi_de_hoac_None)`. CHI uu tien khi CHINH XAC MOT con truc tiep
    khop tu khoa noi dung VA con do chiem >= `_TY_LE_TOI_THIEU_UU_TIEN_CON`
    van ban cua cha — nhieu con khop cung luc (mo ho ung vien nao that su
    cu the hon) hoac ty le thap (con qua nho de la ca vung noi dung) thi
    GIU NGUYEN cha, KHONG doan."""
    ung_vien_con = [
        c for c in thang.children
        if not c.rejected and c.tag in _CANDIDATE_TAGS and c.sig
        and _CONTAINER_HINT_RE.search(c.sig)
    ]
    if len(ung_vien_con) != 1:
        return van_ban_cha, None
    con = ung_vien_con[0]
    con_text, con_len, _link, _para, _headings = tat_ca_ket_qua[id(con)]
    cha_len = len(van_ban_cha.strip())
    if cha_len <= 0 or con_len / cha_len < _TY_LE_TOI_THIEU_UU_TIEN_CON:
        return van_ban_cha, None
    return con_text, con.sig


def extract_content_v3(html: str, *, chapter_title: Optional[str] = None,
                        known_boilerplate_hashes: Optional[Set[str]] = None
                       ) -> ExtractionResult:
    """Diem vao Phase 6 — dung khi `html_extract.extract(html).boundary_matched`
    la `False` (khong co the boundary DA XAC MINH tay nao khop). KHONG BAO
    GIO goi cho nguon DA co boundary xac minh — se lam viec thua VA co the
    cho ket qua khac (kem tin cay hon) ket qua da chung minh dung."""
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()

    known_hashes = known_boilerplate_hashes or set()
    tat_ca_ket_qua = _collect_all(builder.root)

    # Danh sach ung vien: MOI nut "khoi" (tru root gia) co the la vung noi
    # dung — duyet LAP (khong de quy, cung ly do voi `_collect_all`).
    ung_vien: List[Tuple[_Node, str, int, int, int, List[str], int]] = []
    ngan_xep: List[_Node] = [builder.root]
    while ngan_xep:
        node = ngan_xep.pop()
        for con in node.children:
            if con.rejected:
                continue
            if con.tag in _CANDIDATE_TAGS:
                text, total_len, link_len, para_count, headings = tat_ca_ket_qua[id(con)]
                so_con_dang_ke = sum(
                    1 for chau in con.children
                    if not chau.rejected and chau.tag in _CANDIDATE_TAGS
                    and tat_ca_ket_qua[id(chau)][1] >= _NGUONG_CON_UNG_VIEN_DANG_KE)
                ung_vien.append((con, text, total_len, link_len, para_count,
                                headings, so_con_dang_ke))
            ngan_xep.append(con)

    if not ung_vien:
        return ExtractionResult(
            clean_text="", confidence=ExtractionConfidence.LOW,
            container_signature=None)

    da_cham_diem = [
        (node, text, _score(node, total_len, link_len, para_count, headings,
                            chapter_title, so_con_dang_ke))
        for node, text, total_len, link_len, para_count, headings, so_con_dang_ke in ung_vien
    ]
    da_cham_diem.sort(key=lambda item: item[2], reverse=True)
    thang, van_ban_tho, diem_thang = da_cham_diem[0]
    diem_nhi = da_cham_diem[1][2] if len(da_cham_diem) > 1 else float("-inf")
    khoang_cach = diem_thang - diem_nhi

    # Uu tien MOT con truc tiep CU THE HON (khop tu khoa noi dung, xem
    # `_CONTAINER_HINT_RE`) khi no chiem DA SO van ban cua ung vien thang —
    # ung vien thang co the la mot wrapper NGU NGHIA (vd <article>) gom CA
    # vung noi dung THAT LAN mot vung khac khong khop reject-hint (vd
    # "gioi thieu tac gia") nam CANH nhau — mot con cu the hon, chiem da so
    # van ban, la tin hieu manh hon "day chinh la vung noi dung That",
    # ngay ca khi wrapper cha thang diem TONG (vd nho tu khoa tieu de trung
    # voi mot <h1> nam TRUC TIEP trong wrapper). Diem/khoang cach (o tren)
    # KHONG doi theo buoc nay — van phan anh do tin cay TONG THE cua LUOT
    # cham diem ban dau. Phat hien qua review doc lap (Codex).
    van_ban_tho, sig_ghi_de = _uu_tien_con_cu_the_hon(thang, van_ban_tho, tat_ca_ket_qua)

    # Loai bo doan TRUNG boilerplate DA BIET (Phase 6: "boilerplate lap lai
    # qua nhieu trang") — tach theo dong (moi phan tu cua `text_parts` la
    # MOT khoi <p>/khoi van ban, xem `_collect`).
    dong = [d for d in van_ban_tho.split("\n") if d.strip()]
    giu_lai: List[str] = []
    boilerplate_count = 0
    paragraph_hashes: Set[str] = set()
    for d in dong:
        h = _paragraph_hash(d)
        if h in known_hashes:
            boilerplate_count += 1
            continue
        giu_lai.append(d)
        paragraph_hashes.add(h)

    clean_text = "\n\n".join(giu_lai)
    clean_text = re.sub(r"[ \t]+", " ", clean_text)
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()

    if len(clean_text) < MIN_CONFIDENT_TOTAL_TEXT_LEN:
        confidence = ExtractionConfidence.LOW
    elif diem_thang >= _MIN_SCORE_FOR_HIGH and khoang_cach >= _MIN_MARGIN_FOR_HIGH:
        confidence = ExtractionConfidence.HIGH
    elif diem_thang >= _MIN_SCORE_FOR_MEDIUM:
        confidence = ExtractionConfidence.MEDIUM
    else:
        confidence = ExtractionConfidence.LOW

    return ExtractionResult(
        clean_text=clean_text,
        confidence=confidence,
        # `None` khi khong con van ban nao sau khi loc — mot chu ky tro toi
        # mot the RONG (vd "body" cua mot trang trong) khong phai thong tin
        # huu ich, du no ky thuat la "ung vien" duy nhat tim thay.
        container_signature=(sig_ghi_de or thang.sig or thang.tag) if clean_text else None,
        paragraph_hashes=paragraph_hashes,
        rejected_zone_count=_dem_vung_bi_loai(builder.root),
        boilerplate_paragraph_count=boilerplate_count,
    )


def _dem_vung_bi_loai(root: "_Node") -> int:
    """Dem so nut `rejected` trong cay — duyet LAP (khong de quy), cung ly
    do voi `_collect_all`."""
    dem = 0
    ngan_xep: List[_Node] = [root]
    while ngan_xep:
        node = ngan_xep.pop()
        for con in node.children:
            if con.rejected:
                dem += 1
            else:
                ngan_xep.append(con)
    return dem
