"""
Xac dinh THU TU chuong dung — Phase 3 cua Story Harvester V3.

UU TIEN (tu manh nhat xuong yeu nhat, dung DUY NHAT MOT tang cho ca series
— khong tron nhieu tang cho cac chuong khac nhau trong CUNG mot lan quyet
dinh, tranh thu tu "vam" nua theo nguon nay nua theo nguon khac):

    1. EXPLICIT_NUMBER — so chuong RO RANG trich tu van ban lien ket tren
       trang muc luc (vd "Chương 12: ..."). CHI dung khi TAT CA (hoac gan
       tat ca, xem `_TY_LE_TOI_THIEU_CO_SO`) chuong deu co so PHAN BIET —
       mot vai chuong thieu so giua mot day chuong co so van CHAP NHAN
       duoc (vd "Ngoại truyện" xen giua), nhung QUA NHIEU chuong thieu so
       thi tin hieu nay khong du manh de thay index-sequence.
    2. STRUCTURED_METADATA — vi tri tu du lieu co cau truc (vd JSON-LD
       `position`). CHUA co adapter Tier 0 nao trong du an nay cung cap tin
       hieu nay — GIU CHO tang nay o day la co y (kien truc san sang, chua
       co nguon du lieu — ghi lai trung thuc, KHONG gia lap).
    3. INDEX_SEQUENCE — thu tu XUAT HIEN tren trang muc luc — LUON co san
       cho adapter co trang muc luc (GenericIndexAdapter), day la fallback
       AN TOAN NHAT (khong bao gio "khong xac dinh duoc").
    4. NAVIGATION_SEQUENCE — thu tu suy tu VIEC THEO DOI lien ket next/prev
       tuan tu (dung khi KHONG co trang muc luc — xem
       `adapters/navigation_only_adapter.py`).
    5. PUBLISH_TIMESTAMP — fallback CUOI CUNG, CHI dung khi CA index-
       sequence LAN navigation-sequence deu khong co (hiem gap voi cac
       adapter hien co — chu yeu de kien truc san sang cho nguon tuong lai
       KHONG co trang muc luc lan khong theo doi next/prev tuan tu duoc,
       vd danh sach tra ve tu mot API khong dam bao thu tu). Ngay dang
       KHONG luon phan anh dung thu tu doc (chuong sua/dang bu sau co the
       co ngay moi hon chuong ke tiep) — day la tin hieu YEU NHAT co chu y.

KHONG BAO GIO bia dat so chuong con thieu — mot chuong THIEU tin hieu manh
hon van GIU nguyen vi tri o tang duoc CHON, danh dau ro trong evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class OrderingSource(Enum):
    EXPLICIT_NUMBER = "explicit_number"
    STRUCTURED_METADATA = "structured_metadata"
    INDEX_SEQUENCE = "index_sequence"
    NAVIGATION_SEQUENCE = "navigation_sequence"
    PUBLISH_TIMESTAMP = "publish_timestamp"


@dataclass
class ChapterOrderingSignal:
    """Moi tin hieu da biet cho MOT chuong — cac truong `Optional` la
    RONG khi nguon do khong co/khong ap dung cho adapter dang dung, KHONG
    BAO GIO duoc dien bang gia tri doan."""

    url: str
    #: Vi tri XUAT HIEN tren trang muc luc (0-based) — `None` CHI khi
    #: adapter khong co khai niem trang muc luc (vd theo doi next/prev).
    index_position: Optional[int] = None
    #: So chuong trich tu VAN BAN LIEN KET tren trang muc luc (KHAC
    #: `NormalizedChapter.chapter_number`, do trich tu TIEU DE trang
    #: chuong sau khi tai — tin hieu nay co SOM HON, ngay luc kham pha,
    #: truoc khi tai bat ky chuong nao).
    explicit_number: Optional[int] = None
    structured_position: Optional[int] = None
    navigation_position: Optional[int] = None
    published_at: Optional[str] = None


@dataclass
class OrderingResult:
    ordered_urls: List[str]
    source: OrderingSource
    evidence: str
    #: `True` neu thu tu KET QUA khac voi thu tu index-sequence GOC (vd
    #: phat hien va sua thu tu dao nguoc — "reverse chronological TOC").
    reordered_from_index: bool = False
    #: URL CHUA co tin hieu o tang da CHON (vi tri cua chung o KET QUA la
    #: vi tri index-sequence GOC cua chung, khong bi dich chuyen) — bang
    #: chung "khong bia dat" cho operator xem.
    urls_missing_signal: List[str] = field(default_factory=list)


#: Ty le TOI THIEU chuong PHAI co `explicit_number` PHAN BIET de tang nay
#: duoc dung thay INDEX_SEQUENCE — duoi nguong nay, qua nhieu chuong se
#: phai "doan" vi tri (khong chap nhan duoc), lui ve index-sequence THAY
#: VI tron thu tu tu hai nguon khac nhau.
_TY_LE_TOI_THIEU_CO_SO = 0.9


def _explicit_numbers_hop_le(signals: List[ChapterOrderingSignal]
                             ) -> Optional[List[int]]:
    so_list = [s.explicit_number for s in signals if s.explicit_number is not None]
    if len(signals) == 0:
        return None
    if len(so_list) / len(signals) < _TY_LE_TOI_THIEU_CO_SO:
        return None
    if len(set(so_list)) != len(so_list):
        return None  # co so TRUNG — tin hieu khong dang tin, lui ve index.
    return so_list


def determine_order(signals: List[ChapterOrderingSignal]) -> OrderingResult:
    """Diem vao DUY NHAT — ap dung PHAN CAP uu tien (xem docstring module)
    tren toan bo `signals` cua MOT series, tra ve MOT `OrderingResult`
    DUY NHAT (khong tron nhieu tang cho cac chuong khac nhau)."""
    if not signals:
        return OrderingResult(ordered_urls=[], source=OrderingSource.INDEX_SEQUENCE,
                              evidence="Không có chương nào để sắp xếp.")

    # 1. EXPLICIT_NUMBER
    so_hop_le = _explicit_numbers_hop_le(signals)
    if so_hop_le is not None:
        co_so = [s for s in signals if s.explicit_number is not None]
        thieu_so = [s for s in signals if s.explicit_number is None]
        co_so_sap_xep = sorted(co_so, key=lambda s: s.explicit_number)
        # Chuong THIEU so: giu nguyen vi tri index-sequence TUONG DOI cua
        # chung, chen vao cuoi (KHONG bia dat so cho chung) — an toan hon
        # loai han chung khoi ket qua.
        thieu_so_sap_xep = sorted(
            thieu_so, key=lambda s: s.index_position if s.index_position is not None else 0)
        ordered = [s.url for s in co_so_sap_xep] + [s.url for s in thieu_so_sap_xep]

        vi_tri_index_goc = [s.url for s in sorted(
            signals, key=lambda s: s.index_position if s.index_position is not None else 0)]
        dao_nguoc = ordered != vi_tri_index_goc

        ghi_chu = (
            f"Sắp xếp theo số chương rõ ràng trích từ văn bản liên kết "
            f"trên trang mục lục ({len(co_so)}/{len(signals)} chương có số "
            f"phân biệt).")
        if dao_nguoc:
            ghi_chu += (" Thứ tự KHÁC với thứ tự xuất hiện trên trang mục "
                       "lục — có thể trang liệt kê chương mới nhất trước "
                       "(reverse chronological), đã sửa lại theo số chương.")
        return OrderingResult(
            ordered_urls=ordered, source=OrderingSource.EXPLICIT_NUMBER,
            evidence=ghi_chu, reordered_from_index=dao_nguoc,
            urls_missing_signal=[s.url for s in thieu_so])

    # 2. STRUCTURED_METADATA — chua co nguon du lieu nao cung cap (xem
    # docstring module) — nhanh nay LUON bi bo qua o day cho den khi mot
    # adapter that dien `structured_position`.
    co_cau_truc = [s for s in signals if s.structured_position is not None]
    if len(co_cau_truc) == len(signals) and signals:
        sap_xep = sorted(signals, key=lambda s: s.structured_position)
        return OrderingResult(
            ordered_urls=[s.url for s in sap_xep],
            source=OrderingSource.STRUCTURED_METADATA,
            evidence="Sắp xếp theo vị trí trong dữ liệu có cấu trúc (JSON-LD).",
            reordered_from_index=[s.url for s in sap_xep] != [s.url for s in signals])

    # 3. INDEX_SEQUENCE
    co_index = [s for s in signals if s.index_position is not None]
    if len(co_index) == len(signals) and signals:
        sap_xep = sorted(signals, key=lambda s: s.index_position)
        return OrderingResult(
            ordered_urls=[s.url for s in sap_xep], source=OrderingSource.INDEX_SEQUENCE,
            evidence=("Sắp xếp theo thứ tự xuất hiện trên trang mục lục — "
                    "không có tín hiệu số chương rõ ràng/dữ liệu cấu trúc "
                    "đáng tin cậy hơn."))

    # 4. NAVIGATION_SEQUENCE
    co_nav = [s for s in signals if s.navigation_position is not None]
    if len(co_nav) == len(signals) and signals:
        sap_xep = sorted(signals, key=lambda s: s.navigation_position)
        return OrderingResult(
            ordered_urls=[s.url for s in sap_xep],
            source=OrderingSource.NAVIGATION_SEQUENCE,
            evidence=("Sắp xếp theo thứ tự theo dõi liên kết chương "
                    "tiếp/trước — nguồn này không có trang mục lục."))

    # 5. PUBLISH_TIMESTAMP — fallback CUOI CUNG.
    co_ngay = [s for s in signals if s.published_at]
    thieu_ngay = [s for s in signals if not s.published_at]
    sap_xep = sorted(co_ngay, key=lambda s: s.published_at)
    ordered = [s.url for s in sap_xep] + [s.url for s in thieu_ngay]
    return OrderingResult(
        ordered_urls=ordered, source=OrderingSource.PUBLISH_TIMESTAMP,
        evidence=(f"KHÔNG có tín hiệu thứ tự đáng tin cậy nào khác — sắp "
                f"xếp theo thời gian đăng ({len(co_ngay)}/{len(signals)} "
                "chương có ngày đăng). Đây là tín hiệu YẾU NHẤT: ngày đăng "
                "không luôn phản ánh đúng thứ tự đọc."),
        urls_missing_signal=[s.url for s in thieu_ngay])
