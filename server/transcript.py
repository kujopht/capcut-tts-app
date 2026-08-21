"""
Sinh phu de dong bo TU CHINH van ban da dung de tong hop TTS — V4, Phan 2F-2H.

KHONG dung ASR (nhan dien giong noi tu file audio): chung ta da BIET CHINH XAC
van ban dung de tong hop moi phan (`chunk_text()` trong
`desktop_app/text_chunker.py`), va da BIET THOI LUONG THAT cua tung phan (do
bang `ffprobe` NGAY TRUOC KHI file phan bi xoa — xem
`tts_bridge._tong_hop_cac_doan`). Doi voi audio Fanfic tu sinh, day la nguon
that hon nhieu so voi chay ASR nguoc lai tren chinh file minh vua tao ra.

TRUNG THUC VE DO CHINH XAC (yeu cau ro trong dac ta): thoi luong CUA CA PHAN
la CHINH XAC. Thoi diem cua TUNG DOAN HIEN THI (cau/doan van) BEN TRONG mot
phan la UOC LUONG — phan bo ty le theo so ky tu, vi provider TTS khong tra ve
moc thoi gian cho tung tu/cau. `timing_quality` trong ket qua ghi ro dieu do,
KHONG bao gio bao la chinh xac tung tu.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from desktop_app.text_chunker import split_display_segments

#: Tang khi CACH TINH thoi gian doi (vi du sau nay co moc thoi gian that tu
#: provider) — client CO THE dung so nay de biet transcript cu co dang tin
#: cay hon transcript moi hay khong, du hien tai chi co MOT phien ban.
TRANSCRIPT_VERSION = 1

#: Chuoi CO NGHIA, khong phai co so mo ho — doc duoc thang trong response JSON
#: ma khong can tra cuu tai lieu rieng.
TIMING_QUALITY = "part_exact_sentence_estimated"


class TranscriptBuildError(ValueError):
    pass


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    start_ms: int
    end_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "start_ms": self.start_ms, "end_ms": self.end_ms}


def build_transcript(
    chunks: Sequence[str],
    part_durations_seconds: Sequence[float],
    *,
    chapter_id: str,
    track_id: str,
    source_content_hash: str,
) -> Dict[str, Any]:
    """
    Ghep `chunks` (dung dau ra cua `chunk_text`, THEO DUNG THU TU da tong hop)
    voi `part_durations_seconds` (thoi luong THAT do duoc cua TUNG phan, CUNG
    THU TU) thanh mot transcript co moc thoi gian mili-giay.

    HOP DONG voi `tts_bridge._tong_hop_cac_doan`: hai danh sach PHAI cung do
    dai va cung thu tu — day chinh la (chunks, part_durations_seconds) ma ham
    do tra ve sau khi tong hop xong MOT chuong.
    """
    if len(chunks) != len(part_durations_seconds):
        raise TranscriptBuildError(
            "Số phần văn bản và số thời lượng đo được không khớp — "
            f"{len(chunks)} phần vs {len(part_durations_seconds)} thời lượng.")

    segments: List[TranscriptSegment] = []
    con_tro_ms = 0
    for chunk, dur_giay in zip(chunks, part_durations_seconds):
        phan_ms = max(0, round(dur_giay * 1000))
        bat_dau_phan = con_tro_ms
        doan_hien_thi = split_display_segments(chunk)

        if not doan_hien_thi:
            con_tro_ms = bat_dau_phan + phan_ms
            continue

        tong_ky_tu = sum(len(d) for d in doan_hien_thi) or 1
        vi_tri = bat_dau_phan
        for i, doan in enumerate(doan_hien_thi):
            if i == len(doan_hien_thi) - 1:
                # Doan CUOI cua phan nay: lay TRON phan con lai cua phan cha —
                # tranh sai so lam tron cong don lam hut mat vai mili-giay
                # cuoi phan so voi thoi luong that da do.
                ket_thuc = bat_dau_phan + phan_ms
            else:
                ty_le = len(doan) / tong_ky_tu
                ket_thuc = vi_tri + round(phan_ms * ty_le)
            segments.append(TranscriptSegment(
                text=doan, start_ms=vi_tri, end_ms=max(vi_tri, ket_thuc)))
            vi_tri = ket_thuc
        con_tro_ms = bat_dau_phan + phan_ms

    return {
        "version": TRANSCRIPT_VERSION,
        "track_id": track_id,
        "chapter_id": chapter_id,
        "source_content_hash": source_content_hash,
        "duration_ms": con_tro_ms,
        "timing_quality": TIMING_QUALITY,
        "segments": [s.to_dict() for s in segments],
    }
