"""
Kiem tra chat luong TAT DINH (khong goi AI/LLM) cho MOT `NormalizedChapter`
truoc khi dua vao hang doi duyet — xem docstring `pipeline.py` cho vi tri
buoc nay trong luong nhap truyen: `StoryIngestionPipeline.run()` tao ra
`ReviewItem` cho tung chuong, module NAY la buoc SANG LOC THEM truoc khi
mot chuong duoc coi la dang tin cay de operator xem xet — KHONG duoc goi
tu ben trong `run()` (tach rieng de test doc lap va de noi goi tu quyet
dinh khi nao chay, xem NEXT ACTION trong bao cao trien khai).

CO Y khong dung AI: moi dau hieu loi o day (nav-text lan vao, doan van lap,
van ban bi cat cut, encoding hong, kich thuoc bat thuong) deu la LOI CO CHE
trong buoc trich xuat HTML — mot quy tac code re, tat dinh la du de bat,
khong can suy luan ngu nghia ton kem.

Trien khai duoc thuc hien sau MOT lan canary that (dem 2026-08-25) phat
hien hai loi co che that: (1) trang Wikipedia lam vi du — cum dieu huong
"Jump to content" lot vao noi dung trich xuat, va (2) mot chuong tu Project
Gutenberg tra ve ~718.000 ky tu cho MOT lan fetch (CA CUON SACH, khong phai
mot chuong) — ca hai deu la dong luc truc tiep cho `check_nav_leakage` va
`check_text_length_maximum` ben duoi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence
from urllib.parse import urlsplit

from server.scraper.contract import NormalizedChapter


class Severity(Enum):
    """
    Muc do nghiem trong cua MOT check that bai — quyet dinh chuong co bi
    CHAN khoi hang doi duyet hay chi bi HA DIEM TIN CAY.

    BLOCK: dau hieu HONG CO CHE, gan nhu chac chan la loi trich xuat (van
    ban rong/qua ngan, encoding hong, nav-text lan vao, doan van lap, kich
    thuoc bat thuong, thieu URL/domain nguon). Duyet vien se chi mat cong
    vo ich neu xem thu nay — KHONG dua vao hang doi o dang hien tai.

    WARN: tin hieu ĐÁNG NGỜ nhung VAN CO THE hop le — thieu so chuong (mot
    so trang khong danh so), khong dau tieng Viet (chuong chi co tua de/rat
    ngan), ket thuc khong co dau cau (chuong ngan hop le co that), so chuong
    nhay hoac trung (co the do ngu canh sibling khong day du). Ha do tin
    cay nhung KHONG chan — duyet vien van thay duoc, chi duoc canh bao them.
    """

    BLOCK = "block"
    WARN = "warn"


@dataclass
class CheckResult:
    """Ket qua MOT check don le — `reason` la tieng Viet, giai thich TAI SAO
    fail (khong chi WHAT), `None` khi `passed=True`."""

    name: str
    passed: bool
    severity: Severity
    reason: Optional[str] = None


@dataclass
class QualityReport:
    """Ket qua CHAY HET moi check cho mot chuong — xem `assess_chapter_quality`."""

    checks: List[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Chuong DU DIEU KIEN vao hang doi duyet khi KHONG co check BLOCK
        nao that bai — check WARN khong bao gio chan, chi ha `score`."""
        return not any(not c.passed and c.severity is Severity.BLOCK for c in self.checks)

    @property
    def score(self) -> float:
        """Diem [0.0, 1.0] = ty le check DAT tren tong so check da chay —
        dung de SAP XEP thu tu trong hang doi duyet (chuong diem thap can
        xem truoc/sau tuy chinh sach operator), KHONG dung de quyet dinh
        chap nhan/tu choi (xem `passed` cho quyet dinh nhi phan that su)."""
        if not self.checks:
            return 1.0
        return sum(1 for c in self.checks if c.passed) / len(self.checks)

    @property
    def block_reasons(self) -> List[str]:
        return [c.reason for c in self.checks
                if not c.passed and c.severity is Severity.BLOCK and c.reason]

    @property
    def warn_reasons(self) -> List[str]:
        return [c.reason for c in self.checks
                if not c.passed and c.severity is Severity.WARN and c.reason]


# ---------------------------------------------------------------------------
# 1. Tieu de
# ---------------------------------------------------------------------------

#: Duoi nguong nay tieu de gan nhu chac chan khong phai mot tieu de chuong
#: that (vi du chi con lai mot ky tu rac sau khi loc).
_DO_DAI_TIEU_DE_TOI_THIEU = 2
#: Tren nguong nay rat co kha nang buoc trich xuat lay nham mot doan van/
#: phan tu khac lam tieu de — tieu de chuong that (ke ca ban tieng Viet dai
#: dong "Chuong X: Ten Chuong Rat Dai...") hiem khi vuot qua muc nay.
_DO_DAI_TIEU_DE_TOI_DA = 300


def check_title(chapter: NormalizedChapter) -> CheckResult:
    tieu_de = (chapter.chapter_title or "").strip()
    if not tieu_de:
        return CheckResult(
            name="title", passed=False, severity=Severity.BLOCK,
            reason=("Tieu de chuong rong hoac chi co khoang trang — buoc "
                    "trich xuat co the khong tim thay dung phan tu tieu de "
                    "tren trang nguon."))
    if len(tieu_de) < _DO_DAI_TIEU_DE_TOI_THIEU:
        return CheckResult(
            name="title", passed=False, severity=Severity.BLOCK,
            reason=(f"Tieu de qua ngan bat thuong ('{tieu_de}', "
                    f"{len(tieu_de)} ky tu) — kho co the la mot tieu de "
                    "chuong that."))
    if len(tieu_de) > _DO_DAI_TIEU_DE_TOI_DA:
        return CheckResult(
            name="title", passed=False, severity=Severity.BLOCK,
            reason=(f"Tieu de qua dai bat thuong ({len(tieu_de)} ky tu, "
                    f"vuot nguong {_DO_DAI_TIEU_DE_TOI_DA}) — nhieu kha nang "
                    "buoc trich xuat lay nham mot doan van/phan tu khac lam "
                    "tieu de."))
    return CheckResult(name="title", passed=True, severity=Severity.BLOCK)


# ---------------------------------------------------------------------------
# 2. So chuong / thu tu
# ---------------------------------------------------------------------------

#: So chuong tren nguong nay gan nhu chac chan khong phai so chuong that
#: (vi du trich nham nam xuat ban, luot xem) — nhung KHONG the loai tru hoan
#: toan (truyen rat dai/gop nhieu phan) nen chi WARN, khong BLOCK.
_SO_CHUONG_LON_BAT_THUONG = 100_000
#: Khoang cach toi da HOP LY so voi so chuong lon nhat da biet trong series
#: truoc khi coi la "nhay so bat thuong" — du rong de chua truong hop bo sot
#: vai chuong ngoai truyen/interlude, nhung van bat duoc loi trich so ro rang
#: (vd trich nham so trang, so ID URL).
_KHOANG_CACH_NHAY_SO_BAT_THUONG = 50


def check_chapter_number(chapter: NormalizedChapter) -> CheckResult:
    so = chapter.chapter_number
    if so is None:
        return CheckResult(
            name="chapter_number", passed=False, severity=Severity.WARN,
            reason=("Khong trich duoc so chuong — tin hieu do tin cay thap "
                    "hon khi sap xep/doi chieu thu tu, nhung mot so trang "
                    "khong danh so chuong ro rang nen KHONG bi chan vi ly "
                    "do nay."))
    if so <= 0:
        return CheckResult(
            name="chapter_number", passed=False, severity=Severity.BLOCK,
            reason=(f"So chuong trich duoc ({so}) khong hop le (phai la so "
                    "nguyen duong) — day la loi co che trong buoc trich "
                    "xuat/parse, khong phai du lieu that."))
    if so > _SO_CHUONG_LON_BAT_THUONG:
        return CheckResult(
            name="chapter_number", passed=False, severity=Severity.WARN,
            reason=(f"So chuong lon bat thuong ({so}) — kiem tra lai thu "
                    "cong xem co trich nham tu mot con so khac tren trang "
                    "(vd nam xuat ban, luot xem, ID URL) khong."))
    return CheckResult(name="chapter_number", passed=True, severity=Severity.WARN)


def check_chapter_order(
    chapter: NormalizedChapter, sibling_chapter_numbers: Sequence[int],
) -> CheckResult:
    """`sibling_chapter_numbers`: so chuong cua CAC chuong KHAC da biet
    trong CUNG series (khong gom chinh chuong nay). Rong/None -> khong du
    ngu canh de xet, coi nhu DAT (khong phai loi cua chuong nay)."""
    so = chapter.chapter_number
    if so is None or not sibling_chapter_numbers:
        return CheckResult(name="chapter_order", passed=True, severity=Severity.WARN)
    if so in sibling_chapter_numbers:
        return CheckResult(
            name="chapter_order", passed=False, severity=Severity.WARN,
            reason=(f"So chuong {so} TRUNG voi so chuong cua (it nhat) mot "
                    "chuong khac da biet trong series — co the trich nham "
                    "so, hoac hai URL khac nhau cung tro ve mot chuong."))
    lon_nhat = max(sibling_chapter_numbers)
    if so > lon_nhat + _KHOANG_CACH_NHAY_SO_BAT_THUONG:
        return CheckResult(
            name="chapter_order", passed=False, severity=Severity.WARN,
            reason=(f"So chuong {so} nhay qua xa so voi so chuong lon nhat "
                    f"da biet trong series ({lon_nhat}) — kiem tra lai xem "
                    "co trich nham so khong."))
    return CheckResult(name="chapter_order", passed=True, severity=Severity.WARN)


# ---------------------------------------------------------------------------
# 3. Encoding
# ---------------------------------------------------------------------------

#: Chuoi hai/ba ky tu dac trung cua mojibake khi UTF-8 bi doc nham la
#: Latin-1/CP1252 roi ma hoa lai (vd "é" UTF-8 (C3 A9) doc nham thanh "Ã©";
#: dau nhay thong minh U+2019 UTF-8 (E2 80 99) doc nham thanh "â€™"). Day
#: KHONG phai chuoi xuat hien trong van ban tieng Viet NFC that (cac ky tu
#: co dau tieng Viet la MOT codepoint don, khong roi vao dang nay).
_MOJIBAKE_RE = re.compile(r"[ÃÂ][-¿]|â€[-]")
#: Ky tu dieu khien NGOAI tab/xuong dong — khong bao gio xuat hien trong
#: van ban hien thi that, thuong la dau hieu du lieu nhi phan/bang ma bi
#: doc nham thanh van ban.
_DIEU_KHIEN_BAT_THUONG_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def check_encoding(chapter: NormalizedChapter) -> CheckResult:
    text = chapter.clean_text
    ly_do: List[str] = []
    if "�" in text:
        ly_do.append(
            "chua ky tu thay the U+FFFD (REPLACEMENT CHARACTER) — dau hieu "
            "kinh dien cua giai ma sai bang ma khi tai trang")
    if _DIEU_KHIEN_BAT_THUONG_RE.search(text):
        ly_do.append(
            "chua ky tu dieu khien bat thuong (khong phai tab/xuong dong) — "
            "thuong la du lieu nhi phan/bang ma bi doc nham thanh van ban")
    khop_mojibake = _MOJIBAKE_RE.search(text)
    if khop_mojibake:
        ly_do.append(
            f"chua chuoi giong mojibake ('{khop_mojibake.group()}') — dau "
            "hieu trang duoc giai ma UTF-8 sai bang ma trung gian (vd UTF-8 "
            "bi doc nham la Latin-1/CP1252 roi ma hoa lai)")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        ly_do.append(
            "chua ky tu surrogate khong hop le (khong the ma hoa lai UTF-8) "
            "— loi giai ma o buoc tai trang")
    if ly_do:
        return CheckResult(
            name="encoding", passed=False, severity=Severity.BLOCK,
            reason="Van ban co dau hieu loi encoding: " + "; ".join(ly_do) + ".")
    return CheckResult(name="encoding", passed=True, severity=Severity.BLOCK)


# ---------------------------------------------------------------------------
# 4. Tinh ven Unicode tieng Viet
# ---------------------------------------------------------------------------

_VIET_DAU_CHARS_THUONG = set(
    "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợ"
    "ùúủũụưừứửữựỳýỷỹỵđ"
)
_VIET_DAU_CHARS = _VIET_DAU_CHARS_THUONG | {c.upper() for c in _VIET_DAU_CHARS_THUONG}
#: Duoi nguong nay mot chuong "vi" khong dau van co the hop le (vd chuong
#: chi co tua de/rat ngan, hoac audio-title-only) — chi kiem tra chuong DU
#: DAI moi coi thieu dau la tin hieu dang ngo.
_NGUONG_DAI_DE_KIEM_TRA_DAU_TIENG_VIET = 200


def check_vietnamese_diacritics(chapter: NormalizedChapter) -> CheckResult:
    text = chapter.clean_text
    if len(text) < _NGUONG_DAI_DE_KIEM_TRA_DAU_TIENG_VIET:
        return CheckResult(name="vietnamese_diacritics", passed=True, severity=Severity.WARN)
    if any(c in _VIET_DAU_CHARS for c in text):
        return CheckResult(name="vietnamese_diacritics", passed=True, severity=Severity.WARN)
    return CheckResult(
        name="vietnamese_diacritics", passed=False, severity=Severity.WARN,
        reason=(f"Chuong danh dau language='vi' dai {len(text)} ky tu nhung "
                "KHONG co bat ky dau tieng Viet nao (ă â ê ô ơ ư đ va cac "
                "dau thanh) — dau hieu dau bi mat khi trich xuat (vd sai "
                "bang ma) hoac noi dung thuc su khong phai tieng Viet."))


# ---------------------------------------------------------------------------
# 5. Rac dieu huong/UI-chrome lan vao noi dung
# ---------------------------------------------------------------------------

#: Cum tu dieu huong/UI-chrome PHO BIEN tren NHIEU trang khac nhau (khong
#: rieng mot site cu the) — CO Y thien ve mot danh sach NGAN cac cum "chac
#: chan la nav" hon la co gang doan MOI dang nav co the co, de tranh flag
#: nham hoi thoai ngan hop le trong truyen (vd '"Không!"', '"Đi thôi!"').
#: "jump to content" la dau hieu THAT bat duoc trong mot canary dem qua
#: nham vao Wikipedia (trang MediaWiki dien hinh co cum nay dau moi trang).
_NAV_PHRASES = {
    "jump to content", "skip to content", "back to top", "home",
    "menu", "search", "next page", "previous page",
    "privacy policy", "terms of service", "copyright",
    "trang chủ", "đăng nhập", "đăng ký", "bình luận", "danh mục",
    "tìm kiếm", "chia sẻ", "về đầu trang", "trang sau", "trang trước",
    "liên hệ", "giới thiệu", "bản quyền", "điều khoản sử dụng",
    "chính sách bảo mật",
}
#: Ky tu bien thuong bam theo cum nav trong HTML that (dau phan cach
#: breadcrumb, gach dau dong, ...) — cat truoc khi so khop CHINH XAC ca
#: dong, tranh bo lo "Trang chủ »" chi vi con dau » dinh kem.
_DEM_NAV_THUA = " \t:»›|·-–—"


def check_nav_leakage(chapter: NormalizedChapter) -> CheckResult:
    khop: List[str] = []
    for dong in chapter.clean_text.split("\n"):
        goc = dong.strip()
        chuan_hoa = goc.strip(_DEM_NAV_THUA).lower()
        if chuan_hoa and chuan_hoa in _NAV_PHRASES:
            khop.append(goc)
    if khop:
        vi_du = ", ".join(f"'{d}'" for d in khop[:3])
        return CheckResult(
            name="nav_leakage", passed=False, severity=Severity.BLOCK,
            reason=(f"Phat hien {len(khop)} dong khop CHINH XAC cum tu dieu "
                    f"huong/UI-chrome pho bien ({vi_du}) lan vao noi dung "
                    "chuong — dau hieu buoc trich xuat chua loc het thanh "
                    "dieu huong/chan trang cua trang nguon."))
    return CheckResult(name="nav_leakage", passed=True, severity=Severity.BLOCK)


# ---------------------------------------------------------------------------
# 6. Doan van lap
# ---------------------------------------------------------------------------

#: Duoi nguong nay mot dong lap lai (vd "..." hoac mot cau thoai ngan kieu
#: "Không!") van co the la van phong THAT trong truyen — chi coi la dau hieu
#: hong khi doan LAP DU DAI de khong the la trung hop ngau nhien.
_NGUONG_DOAN_VAN_TOI_THIEU = 60


def check_duplicate_paragraphs(chapter: NormalizedChapter) -> CheckResult:
    dem: Dict[str, int] = {}
    for dong in chapter.clean_text.split("\n"):
        doan = dong.strip()
        if len(doan) >= _NGUONG_DOAN_VAN_TOI_THIEU:
            dem[doan] = dem.get(doan, 0) + 1
    lap = {doan: n for doan, n in dem.items() if n > 1}
    if lap:
        doan_vi_du, so_lan = next(iter(lap.items()))
        snippet = doan_vi_du[:80] + ("..." if len(doan_vi_du) > 80 else "")
        return CheckResult(
            name="duplicate_paragraphs", passed=False, severity=Severity.BLOCK,
            reason=(f"Doan van lap lai {so_lan} lan trong cung chuong (vi "
                    f"du: \"{snippet}\") — dau hieu template noi dung bi lap "
                    "hoac trang nguon bi loi, khong phai van phong lap co "
                    "chu y (doan van that thuong khong lap y het tung chu)."))
    return CheckResult(name="duplicate_paragraphs", passed=True, severity=Severity.BLOCK)


# ---------------------------------------------------------------------------
# 7. Noi dung bi cat cut
# ---------------------------------------------------------------------------

#: Dau cau HOP LE de mot chuong ket thuc — gom dau cau tieng Anh/Viet
#: thuong gap va cac dau ngoac/trich dan dong.
_KET_THUC_HOP_LE = set('.!?…"\'”’)]»›')
#: Duoi nguong nay ma khong ket thuc bang dau cau ket -> dang ngo (chuong
#: that thuong dai hon nhieu). Chuong NGAN HON nguong nay VAN duoc chap
#: nhan neu ket thuc dung dau cau (vi du mot chuong ngan hop le).
_NGUONG_DO_DAI_BINH_THUONG = 800
#: Duoi nguong nay MA ket thuc bang "..."/"…" -> giong bi cat ngang hon la
#: mot cau van co chu y dung lai giua chung (dau "..." co chu y thuong xuat
#: hien sau MOT doan van kha day du, khong phai ngay tu dau).
_NGUONG_CAT_NGAN_SAU_CHAM_LUNG = 300


def check_truncation(chapter: NormalizedChapter) -> CheckResult:
    text = chapter.clean_text.rstrip()
    if not text:
        # Van ban rong da duoc `check_text_length_minimum` bat rieng —
        # tranh bao trung mot loi.
        return CheckResult(name="truncation", passed=True, severity=Severity.WARN)

    if (text.endswith("...") or text.endswith("…")) \
            and len(text) < _NGUONG_CAT_NGAN_SAU_CHAM_LUNG:
        return CheckResult(
            name="truncation", passed=False, severity=Severity.WARN,
            reason=(f"Ket thuc bang dau '...'/'…' ngay sau rat it noi dung "
                    f"({len(text)} ky tu, duoi nguong "
                    f"{_NGUONG_CAT_NGAN_SAU_CHAM_LUNG}) — giong bi cat ngang "
                    "giua chung hon la mot cau van co chu y dung lai."))

    ky_tu_cuoi = text[-1]
    if ky_tu_cuoi not in _KET_THUC_HOP_LE and len(text) < _NGUONG_DO_DAI_BINH_THUONG:
        return CheckResult(
            name="truncation", passed=False, severity=Severity.WARN,
            reason=(f"Khong ket thuc bang dau cau ket (ky tu cuoi la "
                    f"'{ky_tu_cuoi}') VA do dai duoi muc binh thuong cua "
                    f"mot chuong ({len(text)} < {_NGUONG_DO_DAI_BINH_THUONG} "
                    "ky tu) — co the noi dung bi cat giua chung khi trich "
                    "xuat."))
    return CheckResult(name="truncation", passed=True, severity=Severity.WARN)


# ---------------------------------------------------------------------------
# 8. Kich thuoc van ban
# ---------------------------------------------------------------------------

#: Duoi nguong nay chuong qua ngan de la mot chuong that — rat co kha nang
#: buoc trich xuat lay nham mot phan tu rong/placeholder. 200 ky tu chi du
#: vai cau, du de phan biet voi "chuong that nhung ngan" (thuong van vuot
#: qua nguong nay du la chuong ngan nhat).
_DO_DAI_TOI_THIEU = 200
#: Tren nguong nay rat co kha nang buoc trich xuat lay nham CA MOT TRANG/
#: CUON SACH thay vi MOT chuong — canary Project Gutenberg dem qua tra ve
#: ~718.000 ky tu cho MOT lan fetch (ca cuon sach), gap hang chuc lan mot
#: chuong truyen thong thuong (thuong vai nghin ky tu). 200.000 duoc chon
#: la nguong AN TOAN: rong hon nhieu so voi chuong dai nhat thuc te tung
#: thay, nhung van chan duoc truong hop "ca cuon sach" ro rang.
_DO_DAI_TOI_DA_MOT_CHUONG = 200_000


def check_text_length_minimum(chapter: NormalizedChapter) -> CheckResult:
    n = len(chapter.clean_text.strip())
    if n < _DO_DAI_TOI_THIEU:
        return CheckResult(
            name="text_length_min", passed=False, severity=Severity.BLOCK,
            reason=(f"Noi dung qua ngan ({n} ky tu, duoi nguong "
                    f"{_DO_DAI_TOI_THIEU}) — nhieu kha nang buoc trich xuat "
                    "khong lay duoc noi dung that (vd lay nham mot phan tu "
                    "rong hoac chi con placeholder)."))
    return CheckResult(name="text_length_min", passed=True, severity=Severity.BLOCK)


def check_text_length_maximum(chapter: NormalizedChapter) -> CheckResult:
    n = len(chapter.clean_text)
    if n > _DO_DAI_TOI_DA_MOT_CHUONG:
        return CheckResult(
            name="text_length_max", passed=False, severity=Severity.BLOCK,
            reason=(f"Noi dung qua lon bat thuong ({n:,} ky tu, vuot nguong "
                    f"{_DO_DAI_TOI_DA_MOT_CHUONG:,}) — giong nhu buoc trich "
                    "xuat lay nham CA MOT TRANG/CUON SACH thay vi MOT chuong "
                    "(vi du canary Gutenberg thuc te tra ve ~718.000 ky tu "
                    "cho mot lan fetch)."))
    return CheckResult(name="text_length_max", passed=True, severity=Severity.BLOCK)


# ---------------------------------------------------------------------------
# 9-10. URL/domain nguon
# ---------------------------------------------------------------------------


def check_source_url(chapter: NormalizedChapter) -> CheckResult:
    van_de: List[str] = []
    for ten_truong, gia_tri in (
        ("source_url", chapter.source_url), ("canonical_url", chapter.canonical_url),
    ):
        if not gia_tri or not gia_tri.strip():
            van_de.append(f"{ten_truong} rong")
            continue
        parts = urlsplit(gia_tri)
        if not parts.scheme or not parts.netloc:
            van_de.append(f"{ten_truong} khong co scheme/host hop le ('{gia_tri}')")
    if van_de:
        return CheckResult(
            name="source_url", passed=False, severity=Severity.BLOCK,
            reason=("URL nguon khong hop le: " + "; ".join(van_de) +
                    " — khong the truy vet lai chuong nay tren trang goc."))
    return CheckResult(name="source_url", passed=True, severity=Severity.BLOCK)


def check_source_domain(chapter: NormalizedChapter) -> CheckResult:
    if not chapter.source_domain or not chapter.source_domain.strip():
        return CheckResult(
            name="source_domain", passed=False, severity=Severity.BLOCK,
            reason=("source_domain rong — mat tin hieu quy thuoc nguon "
                    "(khong biet chuong nay tu website nao)."))
    domain = chapter.source_domain.strip().lower()
    netloc = urlsplit(chapter.canonical_url or "").netloc.lower()
    # So khop LONG (chua nhau ca hai chieu) thay vi bang chinh xac —
    # `source_domain` co the la domain rut gon (vd "example.com") trong khi
    # netloc thuc te co tien to "www." hoac cong (":8080").
    if netloc and domain not in netloc and netloc not in domain:
        return CheckResult(
            name="source_domain", passed=False, severity=Severity.WARN,
            reason=(f"source_domain ('{chapter.source_domain}') khong khop "
                    f"voi host trong canonical_url ('{netloc}') — kiem tra "
                    "lai xem co bi gan nham nguon khong."))
    return CheckResult(name="source_domain", passed=True, severity=Severity.BLOCK)


# ---------------------------------------------------------------------------
# Ham gop
# ---------------------------------------------------------------------------


def assess_chapter_quality(
    chapter: NormalizedChapter, *, sibling_chapter_numbers: Optional[Sequence[int]] = None,
) -> QualityReport:
    """
    Diem vao DUY NHAT de goi khi can biet "chuong nay co dang tin cay de dua
    vao hang doi duyet khong" — chay TOAN BO check tat dinh o file nay, tra
    ve `QualityReport`. Xem docstring `Severity` cho triet ly BLOCK/WARN.

    `sibling_chapter_numbers`: so chuong cua CAC chuong KHAC da biet trong
    CUNG series (khong gom chinh chuong nay) — tuy chon, chi anh huong
    `check_chapter_order`. Bo qua (None/rong) khi chua co ngu canh series
    (vd dang kiem tra mot chuong don le) — check do se tu coi la DAT.
    """
    checks: List[CheckResult] = [
        check_title(chapter),
        check_chapter_number(chapter),
        check_chapter_order(chapter, sibling_chapter_numbers or ()),
        check_encoding(chapter),
        check_nav_leakage(chapter),
        check_duplicate_paragraphs(chapter),
        check_truncation(chapter),
        check_text_length_minimum(chapter),
        check_text_length_maximum(chapter),
        check_source_url(chapter),
        check_source_domain(chapter),
    ]
    if chapter.language == "vi":
        checks.append(check_vietnamese_diacritics(chapter))
    return QualityReport(checks=checks)
