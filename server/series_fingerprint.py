"""
Rut ten series CANONICAL tu tieu de video YouTube (Auto-Ingestion Phase 1,
"Seed Video -> Series Discovery").

TAT DINH, KHONG dung LLM — cung nguyen tac voi `video_classifier.py`/
`episode_parser.py`: cung dau vao LUON ra cung ket qua. Day la buoc DAU
TIEN cua discovery (truoc ca goi YouTube them lan nao) nen phai re, nhanh,
va giai thich duoc.

Chien luoc: mot tieu de video "tong hop nhieu tin hieu" — ten series, so
tap/dai tap, ten kenh, tagline quang cao — thuong duoc TAC GIA tu tach thanh
CAC DOAN bang dau `|` (vi du thuc te: "ALL IN ONE | Reincarnation no Kaben
Tập 1-13 | Sức Mạnh Luân Hồi Được Thức Tỉnh | Cung Điện Anime"). Doan CHINH
XAC chua ten series LUON la doan co mot tin hieu tap/dai tap
(`episode_parser.parse_episode_span`) — day la tin hieu ĐÁNG TIN hon "chon
doan dai nhat" (tagline quang cao thuong DAI HON ten series that).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from server.episode_parser import parse_episode_span
from server.video_classifier import chuan_hoa

#: Cac ky tu phan cach doan trong tieu de — CHI `|` duoc dac ta ro rang qua
#: vi du thuc te; cac dau khac (- , :: , –) de rieng cho tuong lai neu can,
#: tranh tach nham mot ten series co gach ngang THAT trong ten (vi du
#: "Spy x Family" khong co dau `|` nen khong bi anh huong).
_DOAN_PHAN_CACH = "|"

#: Ky tu bien/dau cau con sot lai o hai dau sau khi cat doan tap/dai tap —
#: vi du "Reincarnation no Kaben -" hoac ": Reincarnation no Kaben".
_DEM_THUA = " \t-–—:·.,"


@dataclass
class SeriesFingerprint:
    """
    Dinh danh series RUT RA duoc tu MOT tieu de video — dau vao cho buoc
    "existing-series resolver" (so sanh voi cac `SeriesMapping`/`AnimationEpisode`
    da co) VA buoc "new series discovery" (dat ten cho series moi, gom nhom
    cac video ung vien cung series trong luc quet kenh/playlist).
    """

    raw_title: str
    #: Ten series RUT RA, dang doc duoc (giu hoa/thuong/dau nguyen goc) — vi
    #: du "Reincarnation no Kaben". Co the trung voi `raw_title` neu khong
    #: tach doan duoc (tieu de khong co tin hieu tap/dai tap nao ca).
    canonical_name: str
    #: Chuoi SO SANH (thuong, bo dau, cat khoang trang) — dung `chuan_hoa()`
    #: cung ham voi `video_classifier.py` de nhat quan mot cach so sanh
    #: alias/tieu de duy nhat trong toan bo pipeline Trusted Channels.
    normalized_key: str
    channel_id: str = ""
    channel_title: str = ""


def _cat_doan_tap(doan: str) -> str:
    """Tra phan van ban NAM TRUOC tin hieu tap/dai tap/ban tong hop trong
    `doan` (neu co) — quy uoc tieu de thuong la "<tên series> <phân cách>
    <tập/dải tập> [nhãn phụ]", nen phan TRUOC tin hieu la ten series, phan
    SAU (ke ca nhan phu nhu "[Vietsub]") bi bo qua thay vi co ghep lai."""
    span = parse_episode_span(doan)
    if span is None or not span.raw_text:
        return doan.strip(_DEM_THUA).strip()
    vi_tri = doan.find(span.raw_text)
    con_lai = doan[:vi_tri] if vi_tri > 0 else ""
    return con_lai.strip(_DEM_THUA).strip()


def extract_fingerprint(
    title: str, *, channel_id: str = "", channel_title: str = "",
) -> SeriesFingerprint:
    """
    Rut `SeriesFingerprint` tu MOT tieu de video (seed hoac ung vien).

    1. Tach tieu de thanh cac doan theo `|`.
    2. Doan "ung vien chinh" la doan DAU TIEN vua co tin hieu tap/dai tap
       (`parse_episode_span` khac `None`) VUA con lai van ban KHONG RONG sau
       khi cat tin hieu do di — mot doan CHI la "ALL IN ONE" (khong con gi
       sau khi cat) khong du dieu kien, du no CUNG co tin hieu, vi day la
       nhan quang cao thuan tuy, khong phai ten series.
    3. Neu KHONG doan nao du dieu kien (vi du tieu de khong co dau `|`, hoac
       khong tim thay tin hieu tap/dai tap nao trong tung doan rieng le) —
       roi ve xu ly CA TIEU DE nhu MOT doan duy nhat, cung logic cat tin
       hieu o buoc 2.
    4. Neu con lai van RONG (tieu de CHI gom tin hieu tap/kenh, khong con gi
       khac) — dung nguyen tieu de goc lam ten (khong bao gio tra ten rong).
    5. Cat doan trung ten kenh (neu ten kenh xuat hien y het lam MOT doan
       rieng, vi du doan cuoi cung "Cung Điện Anime") KHOI danh sach doan
       truoc khi xet — ten kenh khong bao gio la ten series.
    """
    text = unicodedata.normalize("NFC", title or "")
    kenh_chuan_hoa = chuan_hoa(channel_title) if channel_title else ""

    doan_list = [d.strip() for d in text.split(_DOAN_PHAN_CACH)]
    doan_list = [d for d in doan_list if d and chuan_hoa(d) != kenh_chuan_hoa]

    ten: str = ""
    for doan in doan_list:
        if parse_episode_span(doan) is None:
            continue
        con_lai = _cat_doan_tap(doan)
        if con_lai:
            ten = con_lai
            break

    if not ten and len(doan_list) <= 1:
        # Khong tach doan duoc (khong co `|`) — thu cat tin hieu tap/dai tap
        # tren CA tieu de truoc khi danh dau la "khong rut duoc gi".
        ten = _cat_doan_tap(text)

    if not ten:
        ten = text.strip()

    return SeriesFingerprint(
        raw_title=title, canonical_name=ten, normalized_key=chuan_hoa(ten),
        channel_id=channel_id, channel_title=channel_title,
    )


def similarity(a: SeriesFingerprint, b: SeriesFingerprint) -> float:
    """
    Do TUONG DONG [0.0, 1.0] giua hai fingerprint — dung de gom nhom ung
    vien trong luc quet kenh/playlist (`SeriesDiscoveryCandidate`) VA de so
    sanh seed voi tieu de cac tap DA CO trong mot series (tin hieu "previously
    accepted videos" cho existing-series resolver).

    TAT DINH: so khop CHINH XAC (sau chuan hoa) -> 1.0; mot chuoi la TIEN TO
    THAT SU cua chuoi kia (vi du ten rut gon dan) -> 0.85; nguoc lai dung ty
    le token dung chung kieu Jaccard tren tap TU (khong dung fuzzy/edit
    distance — de giu tinh giai thich duoc, cung triet ly voi `video_classifier`).
    """
    ka, kb = a.normalized_key, b.normalized_key
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    if ka.startswith(kb) or kb.startswith(ka):
        return 0.85

    tu_a, tu_b = set(ka.split()), set(kb.split())
    if not tu_a or not tu_b:
        return 0.0
    giao = tu_a & tu_b
    hop = tu_a | tu_b
    return len(giao) / len(hop) if hop else 0.0
