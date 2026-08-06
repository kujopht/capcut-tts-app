"""
Danh sach giong DE XUAT cho audio fanfic.

Day la NGUON DUY NHAT khai bao danh sach nay - giao dien khong duoc rai literal
ma giong o bat ky cho nao khac.

Nguyen tac:
- Doi chieu bang MA GIONG on dinh `(provider, engine_voice_id)`, TUYET DOI khong
  so khop bang ten hien thi (ten co the doi giua cac ban catalog).
- Day la danh sach TINH do nguoi dung chon san: khong co thuat toan de xuat,
  khong goi API de tim them giong.
- Doc lap hoan toan voi muc "Yeu thich": loc theo danh sach nay KHONG bao gio
  them/bot dau sao cua nguoi dung.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from desktop_app.providers.base import (
    PROVIDER_CAPCUT,
    PROVIDER_EDGE,
    PROVIDER_PIPER,
    Voice,
)

#: Bay giong de xuat, THEO DUNG THU TU hien thi.
#:
#: Moi muc: (provider, engine_voice_id, ten_tham_khao)
#: `ten_tham_khao` CHI de doc code cho de hieu - viec doi chieu chi dung
#: (provider, engine_voice_id).
#:
#: LUU Y ve "Nhỏ Ngọt Ngào": yeu cau ban dau ghi ma `BV421_yinv_streaming`,
#: nhung Voice.json thuc te KHONG co ma do (khong co ma nao chua "yinv").
#: Ma that cua dung giong nay la `BV421_vivn_streaming` - da doi chieu truc tiep
#: trong Voice.json. Dung ma that de danh sach du bay giong.
RECOMMENDED_FANFIC_VOICES: Tuple[Tuple[str, str, str], ...] = (
    (PROVIDER_CAPCUT, "BV074_streaming", "Cô Gái Hoạt Ngôn"),
    (PROVIDER_CAPCUT, "BV074_streaming_dsp", "Giọng Bé"),
    (PROVIDER_CAPCUT, "vi_female_huong", "Giọng Nữ Phổ Thông"),
    (PROVIDER_CAPCUT, "BV562_streaming", "Mai"),
    (PROVIDER_CAPCUT, "BV421_vivn_streaming", "Nhỏ Ngọt Ngào"),
    (PROVIDER_EDGE, "vi-VN-HoaiMyNeural", "Hoài My"),
    (PROVIDER_PIPER, "ngochuyen", "Ngọc Huyền (mới)"),
)

#: Chi (provider, engine_voice_id) - dung de doi chieu.
RECOMMENDED_CODES: Tuple[Tuple[str, str], ...] = tuple(
    (provider, code) for provider, code, _ in RECOMMENDED_FANFIC_VOICES
)

#: So giong de xuat, dung cho nhan tren giao dien.
RECOMMENDED_COUNT = len(RECOMMENDED_FANFIC_VOICES)

#: Cau dung chung khi nghe thu cac giong de xuat.
PREVIEW_SENTENCE = (
    "Trên boong tàu, gió biển đang đưa chúng ta đến một cuộc phiêu lưu mới."
)

#: Nhan hien thi cua muc nay.
RECOMMENDED_LABEL = f"Đề xuất Audio Fanfic ({RECOMMENDED_COUNT})"


def voice_code(voice: Voice) -> Tuple[str, str]:
    """Ma on dinh cua mot giong: (provider, engine_voice_id)."""
    return (voice.provider, voice.engine_voice_id)


def is_recommended(voice: Voice) -> bool:
    return voice_code(voice) in set(RECOMMENDED_CODES)


def filter_recommended(voices: List[Any]) -> List[Voice]:
    """
    Loc ra dung cac giong de xuat, THEO THU TU khai bao va KHONG trung lap.

    Voice.json co the co nhieu ban ghi cung voice_type; chi lay ban ghi dau tien
    khop moi ma de danh sach khong bi nhan doi.

    Giong chua kiem tra hoac chua kha dung VAN duoc giu lai - viec hien thi
    trang thai la viec cua bang, khong phai cua bo loc nay.
    """
    by_code: Dict[Tuple[str, str], Voice] = {}
    for voice in voices:
        code = voice_code(voice)
        if code in by_code:
            continue        # da co roi -> bo qua ban trung
        by_code[code] = voice

    result: List[Voice] = []
    for code in RECOMMENDED_CODES:
        voice = by_code.get(code)
        if voice is not None:
            result.append(voice)
    return result


def missing_codes(voices: List[Any]) -> List[Tuple[str, str]]:
    """Cac ma de xuat KHONG tim thay trong catalog - de bao cho nguoi dung biet."""
    present = {voice_code(v) for v in voices}
    return [code for code in RECOMMENDED_CODES if code not in present]
