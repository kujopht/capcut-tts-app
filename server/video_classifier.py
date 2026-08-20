"""
Cham diem do tin cay cho MOT video da phat hien, doi voi MOI anh xa series
cua nguon tin cay chua no (Phase 5, Trusted Video Sources).

TAT DINH, KHONG dung LLM: cung dau vao LUON ra cung diem so, va MOI diem so
di kem DANH SACH TIN HIEU de quan tri hieu VI SAO — xem
`ClassificationResult.signals`. Day la yeu cau ro rang cua giai doan nay
("This makes admin review explainable").

Diem cong (tin hieu duong) va diem tru (tin hieu am) CO TRONG SO, cong don
roi gioi han [0.0, 1.0] — xem `_TRONG_SO`/`_PHAT`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from server.episode_parser import EpisodeSpan, EpisodeSpanKind, parse_episode_span
from server.trusted_source_domain import SeriesMapping, TrustedSource

#: Tu khoa PHU DINH mac dinh — video co MOT trong cac tu nay (nguyen tu,
#: xem `_CHUA_TU`) rat co the KHONG PHAI mot tap phim chinh thuc.
NEGATIVE_KEYWORDS: Sequence[str] = (
    "trailer", "teaser", "pv", "preview", "ost", "op", "ed",
    "opening", "ending", "short", "shorts", "highlight", "reaction",
    "announcement", "livestream",
)

#: Trong so cho TUNG tin hieu DUONG, cong don roi gioi han [0, 1].
_TRONG_SO = {
    "kenh_khop": 0.15,
    "alias_khop": 0.35,
    "phat_hien_tap": 0.25,
    "tu_khoa_bao_gom": 0.10,
    "tap_lan_can": 0.15,
}
#: Phat cho tin hieu AM — TRU thang vao tong, khong nhan.
_PHAT = {
    "tu_khoa_loai_tru_rieng": 0.60,   # exclude_keywords cua CHINH anh xa nay
    "tu_khoa_am_mac_dinh": 0.50,      # NEGATIVE_KEYWORDS dung san
}


@dataclass
class ClassificationResult:
    mapping_id: str = ""
    series_id: str = ""
    #: CHI dien khi video la MOT tap don le (`episode_span.kind is SINGLE`).
    #: Mot video la DAI nhieu tap (`RANGE`) hoac ban "tong hop ca series"
    #: (`COMPILATION`) KHONG the tu dong thanh MOT `AnimationEpisode` —
    #: truong nay o day de `None`, KHONG BAO GIO ghi tam so dau dai (xem
    #: `episode_span` de biet dai that phat hien duoc). `_quyet_dinh_trang_thai`
    #: (trusted_source_service.py) da coi `episode_number is None` la
    #: "chua du de tu dong nhap" — hanh vi PENDING nay AP DUNG DUNG cho ca
    #: RANGE/COMPILATION ma khong can sua gi them o do.
    episode_number: Optional[int] = None
    #: Dai tap DAY DU phat hien duoc tu tieu de (SINGLE/RANGE/COMPILATION),
    #: hoac `None` neu khong doc duoc gi — xem `server.episode_parser.EpisodeSpan`.
    episode_span: Optional[EpisodeSpan] = None
    confidence: float = 0.0
    signals: List[str] = field(default_factory=list)
    #: True neu mot tu khoa loai tru (rieng cua anh xa HOAC mac dinh) khop —
    #: nguoi goi (service quet) dung co nay de quyet dinh trang thai IGNORED
    #: NGAY, bat ke diem con lai bao nhieu.
    excluded: bool = False


def _bo_dau(text: str) -> str:
    """Bo dau tieng Viet (VA moi dau to hop Unicode khac) — dung NFKD roi
    loai ky tu ket hop, KHONG dung de HIEN THI, chi de SO SANH."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def chuan_hoa(text: str) -> str:
    """Chuoi SO SANH: thuong, bo dau, cat khoang trang hai dau. Dung cho MOI
    phep khop alias/tu khoa trong module nay — mot alias "Tiên Nghịch" phai
    khop ca tieu de khong dau "Tien Nghich"."""
    return _bo_dau((text or "").lower()).strip()


def _co_tu(text_chuan_hoa: str, tu: str) -> bool:
    """`tu` xuat hien nhu MOT TU RIENG (co ranh gioi tu ca hai phia) trong
    `text_chuan_hoa` — tranh khop nham "op" ben trong "operation"."""
    tu = chuan_hoa(tu)
    if not tu:
        return False
    return re.search(rf"\b{re.escape(tu)}\b", text_chuan_hoa) is not None


def _tap_lan_can(so_tap: int, cac_tap_da_co: Sequence[int]) -> bool:
    """Series da co tap NGAY TRUOC hoac NGAY SAU so tap phat hien — mot tin
    hieu manh rang day dung la MOT tap trong cung mach (khong phai video le
    tinh co trung ten)."""
    return (so_tap - 1) in cac_tap_da_co or (so_tap + 1) in cac_tap_da_co


def _cham_mot_anh_xa(
    *, title_chuan_hoa: str, mapping: SeriesMapping,
    so_tap_span: Optional[EpisodeSpan], kenh_khop: bool,
    cac_tap_da_co: Sequence[int],
) -> Optional[ClassificationResult]:
    """Tra `None` neu KHONG co bat ky tin hieu dinh danh duong nao khop.

    `aliases` va `include_keywords` deu la gia tri quan tri nhap de nhan dien
    series. Alias la tin hieu manh hon, nhung tu khoa mong doi PHAI co the tu
    minh mo mot ung vien — UI cho phep de alias rong, va truoc day kho van luu
    dung `include_keywords` nhung ham nay tra `None` truoc khi doc chung.
    """
    alias_khop = next(
        (a for a in mapping.aliases if a.strip() and chuan_hoa(a) in title_chuan_hoa),
        None,
    )
    tu_khop = [k for k in mapping.include_keywords if _co_tu(title_chuan_hoa, k)]
    if alias_khop is None and not tu_khop:
        return None

    #: `so_tap` (dung cho diem/tin hieu "phat hien tap") CHI dien khi day la
    #: MOT tap don le — mot DAI (RANGE) hoac ban tong hop (COMPILATION)
    #: KHONG duoc phep tu xung la "tap dau tien", xem docstring
    #: `ClassificationResult.episode_number`.
    so_tap = (so_tap_span.start
              if so_tap_span is not None and so_tap_span.kind is EpisodeSpanKind.SINGLE
              else None)

    tin_hieu: List[str] = []
    diem = 0.0
    if alias_khop is not None:
        diem += _TRONG_SO["alias_khop"]
        tin_hieu.append(f"khớp alias “{alias_khop}”")

    if tu_khop:
        diem += _TRONG_SO["tu_khoa_bao_gom"]
        tin_hieu.append(f"chứa từ khoá mong đợi: {', '.join(tu_khop)}")

    if kenh_khop:
        diem += _TRONG_SO["kenh_khop"]
        tin_hieu.append("kênh khớp nguồn tin cậy")

    if so_tap is not None:
        diem += _TRONG_SO["phat_hien_tap"]
        tin_hieu.append(f"phát hiện tập {so_tap}")
        if _tap_lan_can(so_tap, cac_tap_da_co):
            diem += _TRONG_SO["tap_lan_can"]
            tin_hieu.append("khớp mạch tập liền kề đã có")
    elif so_tap_span is not None and so_tap_span.kind is EpisodeSpanKind.RANGE:
        tin_hieu.append(
            f"phát hiện dải tập {so_tap_span.start}-{so_tap_span.end} trong một "
            "video — không tự động nhập, cần quản trị xử lý thủ công")
    elif so_tap_span is not None and so_tap_span.kind is EpisodeSpanKind.COMPILATION:
        tin_hieu.append(
            "có vẻ là video tổng hợp cả series (\"" + so_tap_span.raw_text + "\") — "
            "không tự động nhập, cần quản trị xử lý thủ công")

    loai_rieng = [k for k in mapping.exclude_keywords if _co_tu(title_chuan_hoa, k)]
    bi_loai = False
    if loai_rieng:
        diem -= _PHAT["tu_khoa_loai_tru_rieng"]
        tin_hieu.append(f"chứa từ khoá loại trừ (riêng): {', '.join(loai_rieng)}")
        bi_loai = True

    tu_am_mac_dinh = [k for k in NEGATIVE_KEYWORDS if _co_tu(title_chuan_hoa, k)]
    if tu_am_mac_dinh:
        diem -= _PHAT["tu_khoa_am_mac_dinh"]
        tin_hieu.append(f"chứa từ khoá loại trừ (mặc định): {', '.join(tu_am_mac_dinh)}")
        bi_loai = True

    return ClassificationResult(
        mapping_id=mapping.mapping_id,
        series_id=mapping.animation_series_id,
        episode_number=so_tap,
        episode_span=so_tap_span,
        confidence=max(0.0, min(1.0, diem)),
        signals=tin_hieu,
        excluded=bi_loai,
    )


def classify_video(
    *, title: str, channel_id: str, trusted_source: TrustedSource,
    mappings: Sequence[SeriesMapping],
    episodes_by_series: Optional[Dict[str, Sequence[int]]] = None,
) -> ClassificationResult:
    """
    Cham diem MOT video doi voi TUNG anh xa cua nguon, tra ve anh xa DIEM
    CAO NHAT. Khong anh xa nao co alias HOAC tu khoa mong doi khop -> tra ve ket qua RONG
    (`mapping_id=""`, `confidence=0.0`) — video "moi" (`ImportStatus.NEW`),
    can quan tri tu gan series bang tay.

    `episodes_by_series`: `{series_id: [order_index da co, ...]}` — TUY
    CHON, dung cho tin hieu "tap lan can" (xem `_tap_lan_can`). Bo trong neu
    nguoi goi khong muon tra cuu tap da co (vi du luc chi xem truoc, chua
    can chinh xac tuyet doi).
    """
    title_chuan_hoa = chuan_hoa(title)
    so_tap_span = parse_episode_span(title)
    kenh_khop = bool(channel_id) and channel_id == trusted_source.youtube_channel_id
    episodes_by_series = episodes_by_series or {}

    ung_vien: List[ClassificationResult] = []
    for mapping in mappings:
        ket_qua = _cham_mot_anh_xa(
            title_chuan_hoa=title_chuan_hoa, mapping=mapping, so_tap_span=so_tap_span,
            kenh_khop=kenh_khop,
            cac_tap_da_co=episodes_by_series.get(mapping.animation_series_id, ()),
        )
        if ket_qua is not None:
            ung_vien.append(ket_qua)

    if not ung_vien:
        so_tap = (so_tap_span.start
                  if so_tap_span is not None and so_tap_span.kind is EpisodeSpanKind.SINGLE
                  else None)
        return ClassificationResult(episode_number=so_tap, episode_span=so_tap_span)

    return max(ung_vien, key=lambda r: r.confidence)
