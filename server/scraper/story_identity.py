"""
Nhan dang tac pham + phat hien mirror — Phase 7 cua Story Harvester V3.

MUC TIEU: cho HAI bo tin hieu tu HAI nguon (co the CUNG domain — vd URL
muc luc thay doi slug — hoac KHAC domain hoan toan — vd mot truyen duoc
dang lai tren nhieu site), tra loi "day co phai CUNG MOT tac pham hay
khong" — dung khi operator dan mot URL MOI ma he thong nghi la mot ban
sao/mirror cua mot series DA CO trong kho, tranh tao trung mot tac pham.

CO Y TAT DINH, KHONG dung LLM — cung triet ly voi `discovery.py`. "Do NOT
merge stories based on fuzzy title alone" la nguyen tac CUNG LOI: mot
minh tieu de KHOP (du khop CHINH XAC) khong bao gio du de tra ve HIGH —
luon can THEM it nhat MOT tin hieu doc lap khac dong y.

TIN HIEU (tu manh nhat xuong yeu nhat):
    - content_hash TRUNG: hai chuong co CUNG sha256(clean_text) — GAN NHU
      CHAC CHAN la cung noi dung THAT (mirror sao chep nguyen van), tin
      hieu MANH NHAT co the co (tuong duong "van tay" cua chinh van ban).
    - canonical_url CUNG domain (sau khi chuan hoa m./www., xem
      `contract.domain_of`) — hai URL tro ve CUNG mot vi tri vat ly, day
      KHONG con la cau hoi "co phai mirror" nua ma la CUNG MOT nguon.
    - author KHOP (sau chuan hoa khoang trang/vien thuong) — tin hieu manh
      (hai tac gia TRUNG TEN hiem khi ngau nhien, dac biet voi ten tieng
      Viet ba-bon chu).
    - title KHOP (sau chuan hoa) — tin hieu YEU MOT MINH (nhieu truyen
      trung ten thuc su, dac biet the loai pho bien) — CHI dung nhu MOT
      trong nhieu tin hieu, khong bao gio du rieng no.
    - so chuong GAN BANG NHAU (trong khoang dung sai nho) — tin hieu YEU,
      chi cung co cac tin hieu khac.
    - mo ta CO CHUNG tu khoa dang ke — tin hieu YEU NHAT, de bi nhieu.

KHONG xu ly "tim ung vien mirror" (do la viec cua mot tang tim kiem/chi
muc rieng, ngoai pham vi module nay) — module nay CHI so sanh HAI bo tin
hieu DA CHO, tra ve confidence + bang chung.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set

from server.scraper.contract import domain_of


class SameWorkConfidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class IdentitySignals:
    """Tin hieu nhan dang cua MOT nguon (series) — thu thap tu
    `SeriesInfo`/cac chuong da quet, KHONG phai mot kieu du lieu ben vung
    rieng (goi truc tiep tu noi can so sanh, vd mot route "kiem tra mirror"
    trong tuong lai)."""

    canonical_url: str
    title: str
    author: Optional[str] = None
    description: Optional[str] = None
    #: So chuong DA BIET (uoc luong hoac chinh xac) — dung de so sanh "gan
    #: bang nhau", KHONG can chinh xac tuyet doi.
    chapter_count: Optional[int] = None
    #: sha256(clean_text) cua MOT VAI chuong MAU (khong can toan bo) — xem
    #: `dedupe.content_hash`. Cang nhieu mau, cang de phat hien trung.
    sample_content_hashes: Set[str] = field(default_factory=set)


@dataclass
class IdentityComparisonResult:
    confidence: SameWorkConfidence
    evidence: List[str] = field(default_factory=list)
    #: Ten cac tin hieu DA KHOP (vd "content_hash", "author", "title") —
    #: bang chung co cau truc cho noi goi (vd hien UI), tach voi `evidence`
    #: (van ban NGUOI DOC duoc).
    matched_signals: List[str] = field(default_factory=list)


def _chuan_hoa_van_ban(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip().lower()


def _tu_khoa_dang_ke(text: Optional[str]) -> Set[str]:
    """Tap tu CO Y NGHIA (>= 3 ky tu) trong `text` da chuan hoa — dung so
    sanh mo ta THO, KHONG phai NLP that (chi tach khoang trang/dau cau)."""
    chuan_hoa = _chuan_hoa_van_ban(text)
    return {t for t in re.split(r"[^\w]+", chuan_hoa, flags=re.UNICODE) if len(t) >= 3}


def compare_identity(a: IdentitySignals, b: IdentitySignals) -> IdentityComparisonResult:
    """So sanh HAI bo tin hieu, tra ve `SAME_WORK_CONFIDENCE`. KHONG BAO
    GIO tra HIGH chi tu title (du khop chinh xac) — xem docstring module."""
    evidence: List[str] = []
    matched: List[str] = []

    # -- Tin hieu 0: CUNG domain (sau chuan hoa m./www.) — khong con la
    # cau hoi mirror, CUNG mot nguon vat ly.
    if a.canonical_url and b.canonical_url and domain_of(a.canonical_url) == domain_of(b.canonical_url):
        evidence.append(
            f"Hai URL cùng domain ({domain_of(a.canonical_url)}) sau khi "
            "chuẩn hóa — đây là CÙNG một nguồn, không phải câu hỏi mirror.")
        matched.append("same_domain")
        return IdentityComparisonResult(
            confidence=SameWorkConfidence.HIGH, evidence=evidence, matched_signals=matched)

    # -- Tin hieu 1: content_hash TRUNG — manh nhat.
    trung_hash = a.sample_content_hashes & b.sample_content_hashes
    if trung_hash:
        evidence.append(
            f"Tìm thấy {len(trung_hash)} chương có NỘI DUNG GIỐNG HỆT "
            "(cùng content_hash) giữa hai nguồn — bằng chứng mạnh nhất có "
            "thể có cho việc đây là bản sao (mirror).")
        matched.append("content_hash")

    # -- Tin hieu 2: author khop.
    tac_gia_a, tac_gia_b = _chuan_hoa_van_ban(a.author), _chuan_hoa_van_ban(b.author)
    if tac_gia_a and tac_gia_b and tac_gia_a == tac_gia_b:
        evidence.append(f"Tên tác giả khớp ('{a.author}').")
        matched.append("author")

    # -- Tin hieu 3: title khop — CHI la MOT tin hieu, khong bao gio du
    # rieng no (xem docstring module).
    tieu_de_a, tieu_de_b = _chuan_hoa_van_ban(a.title), _chuan_hoa_van_ban(b.title)
    if tieu_de_a and tieu_de_b and tieu_de_a == tieu_de_b:
        evidence.append(f"Tiêu đề khớp ('{a.title}').")
        matched.append("title")

    # -- Tin hieu 4: so chuong gan bang nhau (dung sai nho).
    if a.chapter_count is not None and b.chapter_count is not None:
        lon_hon = max(a.chapter_count, b.chapter_count, 1)
        chenh_lech = abs(a.chapter_count - b.chapter_count)
        if chenh_lech / lon_hon <= 0.1:
            evidence.append(
                f"Số chương gần bằng nhau ({a.chapter_count} so với "
                f"{b.chapter_count}).")
            matched.append("chapter_count")

    # -- Tin hieu 5: mo ta co chung tu khoa dang ke (yeu nhat).
    tu_a, tu_b = _tu_khoa_dang_ke(a.description), _tu_khoa_dang_ke(b.description)
    if tu_a and tu_b:
        giao = tu_a & tu_b
        hop = tu_a | tu_b
        ty_le = len(giao) / len(hop) if hop else 0.0
        if ty_le >= 0.4:
            evidence.append(
                f"Mô tả có {ty_le:.0%} từ khóa đáng kể trùng nhau.")
            matched.append("description")

    if not evidence:
        evidence.append(
            "Không tìm thấy tín hiệu nào khớp giữa hai nguồn — coi là hai "
            "tác phẩm khác nhau.")

    # -- Quyet dinh confidence: KHONG BAO GIO HIGH chi tu "title" (co the
    # dung MOT MINH hoac cung "description", ca hai deu la tin hieu yeu).
    tin_hieu_manh = {"content_hash"}
    tin_hieu_trung_binh = {"author", "chapter_count"}
    co_tin_hieu_manh = bool(set(matched) & tin_hieu_manh)
    so_tin_hieu_trung_binh_tro_len = len(set(matched) & (tin_hieu_trung_binh | {"title"}))

    if co_tin_hieu_manh:
        confidence = SameWorkConfidence.HIGH
    elif "title" in matched and so_tin_hieu_trung_binh_tro_len >= 2:
        # title + IT NHAT mot tin hieu trung binh khac (author/chapter_count)
        # — nhieu tin hieu doc lap cung dong y, khong chi mot minh title.
        confidence = SameWorkConfidence.MEDIUM
    elif "author" in matched and "chapter_count" in matched:
        # Trung author + so chuong nhung KHONG trung title (vd doi ten
        # ban dich) — van la hai tin hieu doc lap, du MEDIUM.
        confidence = SameWorkConfidence.MEDIUM
    elif matched:
        # Chi MOT tin hieu yeu (title mot minh, hoac chi description) —
        # KHONG du, xem docstring module.
        confidence = SameWorkConfidence.LOW
    else:
        confidence = SameWorkConfidence.LOW

    return IdentityComparisonResult(
        confidence=confidence, evidence=evidence, matched_signals=matched)
