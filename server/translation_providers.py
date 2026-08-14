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

import httpx

from server.translation import XUNG_HO_CAN_NGU_CANH


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
    #: Che do chat luong cua DU AN ("nhanh"/"can_bang"/"van_hoc") — Phan 3D
    #: (overnight Phase 3): `ProviderRegistry` dung gia tri nay CUNG
    #: `vai_tro` de chon THU TU model Groq nen thu, xem
    #: `translation_model_profiles.route_order`. Rong = khong dinh tuyen dac
    #: biet (vi du goi tu noi chua biet che do, nhu mot so test cu).
    quality_mode: str = ""
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


#: Nhan tieng Viet, VIET RIENG cho prompt (khac `GENRE_LABELS` o
#: `server/translation.py` — nhan do ngan, dung cho GIAO DIEN; o day can mo
#: ta DAI hon de LLM hieu dung boi canh the loai). `XUNG_HO_CAN_NGU_CANH`
#: thi dung chung THAT (import thang) vi day la danh sach du lieu, khong
#: phai van ban hien thi — dung chung tranh lech danh sach giua hai noi.
_NHAN_THE_LOAI: Dict[str, str] = {
    "tien_hiep": "tiên hiệp (tu luyện, cảnh giới, tông môn)",
    "huyen_huyen": "huyền huyễn (dị năng, đại lục, chủng tộc)",
    "vo_hiep": "võ hiệp (võ công, giang hồ, môn phái)",
    "do_thi": "đô thị hiện đại",
    "ngon_tinh": "ngôn tình (tâm lý nhân vật, tình cảm)",
    "lich_su": "lịch sử/dã sử",
    "he_thong": "hệ thống (game hoá, bảng trạng thái, nâng cấp)",
    "dong_nhan": "đồng nhân (dựa trên tác phẩm gốc có sẵn)",
    "kinh_di": "kinh dị/rùng rợn",
    "auto": "chưa xác định — tự nhận diện từ văn bản",
}

_NHAN_DAT_TEN: Dict[str, str] = {
    "han_viet": "phiên âm Hán Việt (ví dụ: 萧炎 → Tiêu Viêm)",
    "pinyin": "giữ nguyên bính âm/phiên âm La-tinh (ví dụ: 萧炎 → Xiao Yan)",
    "thuan_viet": "Việt hoá theo NGHĨA thay vì âm đọc khi hợp lý",
    "fandom": "dùng đúng thuật ngữ cộng đồng fandom Việt đã quen dùng",
    "auto": "tự chọn cách phù hợp nhất với thể loại",
}

#: Xem `server/translation.py::XUNG_HO_CAN_NGU_CANH` — cung mot danh sach,
#: dua thang vao prompt de LLM tu QUYET DINH tu xung ho tieng Viet phu hop
#: THEO NGU CANH (gioi tinh, quan he, vai ve) — chu KHONG anh xa tinh mot
#: dai tu Viet co dinh cho moi tu Trung. Day la diem khac biet voi mot tu
#: dien tinh: cung mot ky tu "你" co the la "ngươi"/"cậu"/"con"/"ngài" tuy
#: nguoi noi la ai, dang noi voi ai — chi mot LLM doc hieu van canh moi
#: quyet dinh dung, khong co bang tra cuu nao lam thay duoc.
_XUNG_HO_GHI_CHU = (
    "Các đại từ/danh xưng tiếng Trung sau đây KHÔNG có một bản dịch cố định "
    "— hãy chọn từ xưng hô tiếng Việt phù hợp dựa trên giới tính, quan hệ "
    "và vai vế của người nói/người nghe trong NGỮ CẢNH đoạn văn, không dịch "
    "máy móc theo một từ điển tĩnh: " + "、".join(XUNG_HO_CAN_NGU_CANH)
)


def _he_thong_prompt(context: TranslationContext) -> str:
    """
    Xay prompt he thong theo VAI TRO — day la noi ba-pass (dich/bien tap/QA)
    THUC SU khac nhau ve NOI DUNG chi dan, dung y voi docstring dau file.
    """
    the_loai = _NHAN_THE_LOAI.get(context.genre, context.genre)
    dat_ten = _NHAN_DAT_TEN.get(context.naming_mode, context.naming_mode)

    goc = (
        "Bạn là một dịch giả tiểu thuyết mạng Trung Quốc sang tiếng Việt, "
        f"chuyên thể loại {the_loai}. Quy ước đặt tên riêng: {dat_ten}. "
        f"{_XUNG_HO_GHI_CHU}"
    )

    if context.vai_tro == "translator":
        return (
            goc + " Dịch đoạn văn được đưa vào sang tiếng Việt tự nhiên, "
            "đúng văn phong tiểu thuyết mạng (không dịch từng chữ máy móc). "
            "CHỈ trả về đoạn văn đã dịch, không thêm lời giải thích, không "
            "thêm ký hiệu markdown hay chú thích."
        )
    if context.vai_tro == "editor":
        return (
            goc + " Đoạn văn đưa vào ĐÃ được dịch sang tiếng Việt ở bước "
            "trước. Nhiệm vụ của bạn là biên tập văn học: câu văn mượt hơn, "
            "tự nhiên hơn, đúng giọng văn thể loại — KHÔNG đổi nghĩa, KHÔNG "
            "thêm/bớt tình tiết, KHÔNG đổi tên riêng đã dùng. Nếu đoạn văn "
            "đã tốt, trả về nguyên văn. CHỈ trả về đoạn văn kết quả."
        )
    # "qa"
    return (
        goc + " Đoạn văn đưa vào là bản dịch đã qua biên tập. Kiểm tra lỗi "
        "sai nghĩa, thiếu câu, xưng hô mâu thuẫn với ngữ cảnh, hoặc lỗi "
        "chính tả — rồi SỬA CỤC BỘ đúng chỗ sai (patch tại chỗ), KHÔNG viết "
        "lại toàn bộ đoạn văn nếu phần còn lại đã ổn. Nếu không có lỗi, trả "
        "về nguyên văn không đổi. CHỈ trả về đoạn văn kết quả."
    )


def _nguoi_dung_prompt(text: str, context: TranslationContext) -> str:
    phan = [f"Đoạn văn cần xử lý:\n{text}"]
    if context.tom_tat_truoc.strip():
        phan.append(f"Tóm tắt các chương trước (để giữ mạch truyện):\n"
                    f"{context.tom_tat_truoc}")
    if context.glossary:
        muc = "\n".join(f"- {g}: {v}" for g, v in context.glossary.items())
        phan.append(f"Thuật ngữ ĐÃ CHỐT cho tác phẩm này (dùng đúng, không "
                    f"đổi):\n{muc}")
    if context.custom_instruction.strip():
        phan.append(f"Yêu cầu thêm từ người dùng:\n{context.custom_instruction}")
    return "\n\n".join(phan)


class DocuTranslateProvider(TranslationProvider):
    """
    Provider dich that qua endpoint tuong thich OpenAI chat completions.

    KHONG import goi PyPI `docutranslate` (github.com/xunbu/docutranslate,
    MPL-2.0): API cong khai cua no la file-vao/file-ra
    (`Client.translate(duong_dan_tep)`) — dieu phoi VA GOI mot LLM ben trong
    theo cach RIENG cua no, khong cho phep kiem soat prompt tung doan/tung
    vai-tro nhu he thong nay can (glossary khoa, tom tat chuong truoc, ba
    vai tro dich/bien-tap/QA). Dung endpoint OpenAI-compatible truc tiep qua
    `httpx` (da la phu thuoc khai bao san — xem `server/requirements.txt`)
    la lua chon dung: cung MOT hinh dang cau hinh (`base_url`/`api_key`/
    `model`) ma mot backend kieu DocuTranslate se dung, nhung van giu duoc
    toan bo prompt engineering (Novel Bible, xung ho theo ngu canh, 3-pass)
    da xay o tang tren. Ghi ro quyet dinh nay o day de phien sau khong
    tuong nham la chua tich hop vi "thieu import goi docutranslate".
    """

    name = "docutranslate"

    #: Giay — timeout MOI request. Doan van dich co the dai, LLM tra loi
    #: cham hon TTS thong thuong.
    TIMEOUT_SECONDS = 60.0

    def __init__(self, *, base_url: str, api_key: str, model: str,
                client: Optional[httpx.Client] = None):
        if not (base_url and api_key and model):
            raise TranslationProviderError(
                "Thiếu cấu hình TRANSLATION_BASE_URL/API_KEY/MODEL — "
                "chưa thể dùng DocuTranslateProvider.")
        self._model = model
        # `client` tiem duoc de test dung `httpx.MockTransport` — khong bao
        # gio goi mang that trong bo test (xem test_translation_providers.py).
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=self.TIMEOUT_SECONDS,
        )

    def translate_segment(self, text: str, *,
                          context: TranslationContext) -> str:
        sach = (text or "").strip()
        if not sach:
            raise TranslationProviderError("Đoạn văn rỗng, không có gì để dịch.")

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _he_thong_prompt(context)},
                {"role": "user", "content": _nguoi_dung_prompt(sach, context)},
            ],
            "temperature": 0.3,
        }
        try:
            resp = self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise TranslationProviderError(
                f"Không gọi được dịch vụ dịch: {exc}") from exc

        if resp.status_code != 200:
            raise TranslationProviderError(
                f"Dịch vụ dịch trả lỗi {resp.status_code}: "
                f"{resp.text[:300]}")

        try:
            du_lieu = resp.json()
            noi_dung = du_lieu["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise TranslationProviderError(
                "Phản hồi dịch vụ dịch không đúng định dạng mong đợi.") from exc

        ket_qua = (noi_dung or "").strip()
        if not ket_qua:
            raise TranslationProviderError(
                "Dịch vụ dịch trả về nội dung rỗng.")
        return ket_qua


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
