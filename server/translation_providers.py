"""
Truu tuong hoa nha cung cap dich (V5) — MOT giao dien, nhieu ban trien khai.

KHONG khoa vao mot model. `TranslationService` chi biet ve
`TranslationProvider`; ban that (DocuTranslate/LLM) va ban gia (test) deu
cung hinh dang.

VI SAO CHI MOT PHUONG THUC (`translate_segment`): ba pass (dich/bien tap/QA)
trong che do VAN_HOC deu la "dua mot doan van + mot chi dan vai tro vao,
nhan lai mot doan van" — khac biet nam o NOI DUNG chi dan
(`TranslationContext.instruction`), khong nam o hinh dang loi goi. Gop lam
mot phuong thuc nghia la them mot nha cung cap moi chi can trien khai DUNG
MOT ham, khong phai ba.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TranslationContext:
    """
    Ngu canh dua vao MOI lan goi provider.

    Tap trung o day thay vi rai tham so: mot nha cung cap that (LLM) can GOP
    tat ca truong nay thanh MOT prompt; gop san o day nghia la logic gop
    prompt song trong dung MOT lop, kiem duoc doc lap voi tung provider.
    """

    #: Vai tro cua lan goi nay: "translator" | "editor" | "qa". Provider that
    #: dung de chon he thong-prompt phu hop; mock dung de bo qua bien tap/QA
    #: (tra nguyen van doan dich, xem `MockTranslationProvider`).
    vai_tro: str
    genre: str = "auto"
    naming_mode: str = "auto"
    #: Tom tat NGAN cac chuong truoc — kiem soat token, KHONG nhet toan bo
    #: novel vao prompt. Xem yeu cau goc muc 7 (context memory).
    tom_tat_truoc: str = ""
    #: {tu_goc: ban_dich} — CHI cac muc lien quan doan nay, khong phai toan
    #: bo tu dien du an (tranh phinh prompt vo ich).
    glossary: Dict[str, str] = field(default_factory=dict)
    custom_instruction: str = ""


class TranslationProviderError(Exception):
    """Loi tu phia nha cung cap — tang service doi thanh trang thai `failed`."""


class TranslationProvider(ABC):
    """Giao dien MOI nha cung cap dich phai trien khai."""

    #: Ten hien thi, dung trong log/bao cao — KHONG dung de re nhanh logic.
    name: str = "unknown"

    @abstractmethod
    def translate_segment(self, text: str, *,
                          context: TranslationContext) -> str:
        """
        Dich/bien tap/QA MOT doan van, tra ve doan KET QUA.

        Nem `TranslationProviderError` khi that bai (rate limit, timeout, noi
        dung bi tu choi...) — KHONG bao gio tra ve chuoi rong nhu the la
        thanh cong: mot doan rong lam mat noi dung ma khong ai biet.
        """
        raise NotImplementedError


class MockTranslationProvider(TranslationProvider):
    """
    Ban GIA, TAT DINH — dung cho test va cho phat trien khi chua co API key
    that. KHONG BAO GIO goi mang.

    Vai tro "editor"/"qa" tra NGUYEN VAN doan dau vao: mock khong gia vo bien
    tap duoc gi, va lam vay se che giau loi that trong logic ba-pass cua tang
    service (neu editor luon doi noi dung, mot bai test dua tren mock se
    khong bao gio phat hien duoc mot vong lap ba-pass sai thu tu).
    """

    name = "mock"

    #: Vi du CHINH XAC tu yeu cau goc — cho cac test kiem tra hanh vi that.
    _TU_DIEN: Dict[str, str] = {
        "萧炎看向药老。": "Tiêu Viêm nhìn về phía Dược Lão.",
        "你": "cậu",
        "我": "tôi",
    }

    def translate_segment(self, text: str, *,
                          context: TranslationContext) -> str:
        if context.vai_tro != "translator":
            return text
        sach = (text or "").strip()
        if not sach:
            raise TranslationProviderError("Đoạn văn rỗng, không có gì để dịch.")
        if sach in self._TU_DIEN:
            return self._TU_DIEN[sach]
        # Ap glossary (neu tu xuat hien nguyen van trong doan) roi danh dau ro
        # day la ban dich GIA — khong ai duoc nham day la dich that.
        ra = sach
        for goc, dich in context.glossary.items():
            ra = ra.replace(goc, dich)
        return f"[MOCK-VI] {ra}"


class DocuTranslateProvider(TranslationProvider):
    """
    Adapter cho DocuTranslate (github.com/xunbu/docutranslate, MPL-2.0).

    CHUA TRIEN KHAI: can mot API key LLM that (DocuTranslate tu no khong
    dich — no dieu phoi tach van ban/glossary va GOI mot LLM ben ngoai qua
    cau hinh `TRANSLATION_BASE_URL`/`TRANSLATION_API_KEY`/`TRANSLATION_MODEL`,
    xem `server/config.py`). Viet khung o day truoc de tang service khong
    phai doi khi co key that — chi can lap `__init__`/`translate_segment`.

    Y dinh tich hop: goi DocuTranslate nhu THU VIEN Python (import + goi ham),
    KHONG vendor UI cua no. Giay phep MPL-2.0 cho phep dung nhu mot phu thuoc
    (giu nguyen header MPL trong file CUA DocuTranslate, khong bat buoc mo
    nguon toan bo Fanfic World) — xem ghi chu day du trong bao cao V5.
    """

    name = "docutranslate"

    def __init__(self, *, base_url: str, api_key: str, model: str):
        if not (base_url and api_key and model):
            raise TranslationProviderError(
                "Thiếu cấu hình TRANSLATION_BASE_URL/API_KEY/MODEL — "
                "chưa thể dùng DocuTranslateProvider.")
        self._base_url = base_url
        self._api_key = api_key
        self._model = model

    def translate_segment(self, text: str, *,
                          context: TranslationContext) -> str:
        raise NotImplementedError(
            "DocuTranslateProvider chưa triển khai — cần API key LLM thật. "
            "Dùng MockTranslationProvider cho phát triển/test.")


def build_provider(settings: Optional[object] = None) -> TranslationProvider:
    """
    Chon provider theo cau hinh. `settings=None` hoac thieu key -> mock, KHONG
    nem loi: moi truong dev/test khong co API key van phai chay duoc.
    """
    base_url = getattr(settings, "translation_base_url", "") if settings else ""
    api_key = getattr(settings, "translation_api_key", "") if settings else ""
    model = getattr(settings, "translation_model", "") if settings else ""
    if base_url and api_key and model:
        return DocuTranslateProvider(base_url=base_url, api_key=api_key,
                                     model=model)
    return MockTranslationProvider()
