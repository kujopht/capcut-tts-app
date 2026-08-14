"""
Dang ky NHIEU provider dich MIEN PHI (Part Q).

MUC TIEU THIET KE (theo dung yeu cau goc):
- Suy luan tu xa MIEN PHI TRUOC. Khong yeu cau LLM cuc bo, khong yeu cau GPU
  rieng, KHONG BAO GIO tu dong chuyen sang provider TRA PHI.
- Moi nha cung cap duoc cau hinh qua BIEN MOI TRUONG RIENG cua no, khong dung
  chung mot blob JSON — moi bi mat co the thu hoi doc lap:
    GROQ_API_KEY, GROQ_MODEL
    CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, CLOUDFLARE_WORKERS_AI_MODEL
    TRANSLATION_BASE_URL, TRANSLATION_API_KEY, TRANSLATION_MODEL
      (provider "tuy chinh" — bat ky endpoint tuong thich OpenAI nao, da co
      tu Vong 2 cua V5)
- `TRANSLATION_ALLOW_PAID_PROVIDER` (mac dinh "false") la HANG RAO BAO VE:
  khi false, `build_provider_registry` se KHONG dua bat ky provider nao
  duoc danh dau `free_tier=False` vao registry, du bien moi truong cua no
  co day du. Hien tai CA HAI provider cu the o day deu la mien phi (Groq,
  Cloudflare Workers AI free tier) nen co nay chua chan gi — no ton tai de
  bao ve TUONG LAI, phong khi ai do them mot provider tra phi ma quen kiem
  tra co nay.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

import httpx

from server.translation_providers import (
    TranslationContext,
    TranslationProvider,
    TranslationProviderError,
    _he_thong_prompt,
    _nguoi_dung_prompt,
)


class ProviderStatus(str, Enum):
    AVAILABLE = "available"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class ProviderRateLimited(TranslationProviderError):
    """429 hoac tuong duong — TAM THOI, co the co `retry_at` (ISO) neu nha
    cung cap co bao (vd header `Retry-After`)."""

    def __init__(self, message: str, retry_at: str = ""):
        super().__init__(message)
        self.retry_at = retry_at


class ProviderQuotaExhausted(TranslationProviderError):
    """Het han muc mien phi trong chu ky hien tai — co the co `retry_at`."""

    def __init__(self, message: str, retry_at: str = ""):
        super().__init__(message)
        self.retry_at = retry_at


class AllProvidersUnavailable(TranslationProviderError):
    """
    TAT CA provider (mien phi) da cau hinh hien khong dung duoc.

    KHONG PHAI mot loi that theo nghia "job hong" — tang service phai doi
    trang thai job thanh `waiting_for_provider`, KHONG PHAI `failed` (xem
    `TranslationService._thuc_thi_job`, Part Q4). `retry_not_before` la moc
    SOM NHAT trong cac moc reset ma provider da bao (rong neu khong provider
    nao bao — khi do dung backoff mac dinh o tang service, KHONG bia so).
    """

    def __init__(self, retry_not_before: str = ""):
        self.retry_not_before = retry_not_before
        super().__init__(
            "Tất cả model dịch miễn phí đã cấu hình hiện đều không dùng "
            "được (hết hạn mức hoặc đang gặp lỗi).")


@dataclass
class ProviderCatalogEntry:
    """
    Thong tin AN TOAN de dua ra ngoai qua `GET /api/translate/providers`.

    KHONG BAO GIO chua api key/secret url/thong tin xac thuc noi bo — chi
    nhung gi nguoi dung CAN THAY de chon model.
    """

    provider_id: str
    model_id: str
    display_name: str
    quality_hint: str
    free_tier: bool
    status: ProviderStatus
    reset_at: str = ""  # ISO, RONG neu khong biet — KHONG BAO GIO bia so

    def to_dict(self) -> Dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "display_name": self.display_name,
            "quality_hint": self.quality_hint,
            "free_tier": self.free_tier,
            "status": self.status.value,
            "reset_at": self.reset_at,
        }


@dataclass
class ProviderProvenance:
    """
    Provider/model THAT tao ra MOT pass — luu kem `TranslationVersion`
    (Part O/Q5) de sau nay so sanh cac model dich Trung -> Viet.
    """

    provider_id: str
    model_id: str
    pass_type: str
    success: bool
    attempted_at: str = ""
    error: str = ""
    #: V5.1 BYOK — "shared" (kho Fanfic dung chung) hoac "personal" (API key
    #: rieng cua nguoi dung). KHONG BAO GIO chua bi mat — chi mot nhan cho
    #: biet AI TRA TIEN cho lan goi nay (Part I: "biet nguon credential ma
    #: khong luu bi mat").
    credential_source: str = "shared"

    def to_dict(self) -> Dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "pass_type": self.pass_type,
            "success": self.success,
            "attempted_at": self.attempted_at,
            "error": self.error,
            "credential_source": self.credential_source,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: Mot so model "reasoning" (vd Qwen3 tren Groq) tra ve khoi
#: `<think>...</think>` NGAY TRONG `message.content` — neu khong loc, toan bo
#: chuoi suy luan noi bo se bi coi la "ban dich". Loc o day la RAO CHAN CUOI,
#: doc lap voi viec co tat duoc bang tham so rieng cua tung nha cung cap hay
#: khong (xem `GroqProvider.EXTRA_PAYLOAD` — da yeu cau Groq an no o nguon,
#: nhung mot so model/phien ban co the khong tuan thu tham so do).
_MAU_KHOI_NGHI = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def _bo_khoi_nghi(noi_dung: str) -> str:
    return _MAU_KHOI_NGHI.sub("", noi_dung or "").strip()


def _retry_after_to_iso(resp: httpx.Response) -> str:
    """Doc header `Retry-After` (giay, hoac ngay thang HTTP) -> ISO tuyet
    doi. Tra rong neu khong doc duoc — KHONG BAO GIO bia mot con so."""
    gia_tri = resp.headers.get("retry-after", "")
    if not gia_tri:
        return ""
    try:
        giay = int(gia_tri.strip())
        return (datetime.now(timezone.utc) + timedelta(seconds=giay)).isoformat(
            timespec="seconds")
    except ValueError:
        return ""  # dang ngay-thang HTTP hiem gap — khong co gia tri du de doan


class _OpenAICompatFreeProvider(TranslationProvider):
    """
    Nen dung chung cho cac provider MIEN PHI co REST tuong thich OpenAI chat
    completions (Groq) — khac `DocuTranslateProvider` (tuy chinh, Vong 2) o
    cho lop nay NHAN DIEN rieng loi 429/het han muc thanh
    `ProviderRateLimited`/`ProviderQuotaExhausted` de `ConfiguredProvider`
    (duoi day) cap nhat trang thai CHINH XAC thay vi mot `TranslationProviderError`
    chung chung.
    """

    TIMEOUT_SECONDS = 60.0

    #: Tham so THEM vao than request, ghi de o lop con cho tung nha cung cap
    #: cu the (vd Groq dung `reasoning_format` de tat khoi suy luan cua cac
    #: model "reasoning" — xem `GroqProvider`). Rong o day: mot endpoint
    #: OpenAI-compatible bat ky khong chac hieu tham so rieng cua Groq.
    EXTRA_PAYLOAD: Dict[str, object] = {}

    def __init__(self, *, base_url: str, api_key: str, model: str,
                client: Optional[httpx.Client] = None):
        self._model = model
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
            **self.EXTRA_PAYLOAD,
        }
        try:
            resp = self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise TranslationProviderError(
                f"Không gọi được dịch vụ dịch: {exc}") from exc

        if resp.status_code == 429:
            retry_at = _retry_after_to_iso(resp)
            thap = resp.text.lower()
            if "quota" in thap:
                raise ProviderQuotaExhausted(
                    f"Model đã hết hạn mức miễn phí: {resp.text[:200]}",
                    retry_at=retry_at)
            raise ProviderRateLimited(
                f"Model đang bị giới hạn tốc độ: {resp.text[:200]}",
                retry_at=retry_at)
        if resp.status_code != 200:
            raise TranslationProviderError(
                f"Dịch vụ dịch trả lỗi {resp.status_code}: {resp.text[:300]}")

        try:
            du_lieu = resp.json()
            noi_dung = du_lieu["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise TranslationProviderError(
                "Phản hồi dịch vụ dịch không đúng định dạng mong đợi.") from exc

        ket_qua = _bo_khoi_nghi((noi_dung or "").strip())
        if not ket_qua:
            raise TranslationProviderError("Dịch vụ dịch trả về nội dung rỗng.")
        return ket_qua


class GroqProvider(_OpenAICompatFreeProvider):
    """
    Groq — REST tuong thich OpenAI, endpoint mien phi cho cac model Qwen.

    HAI dieu chinh CHI THAT SU can thiet den tu kiem thu SONG voi API that
    (khong doan duoc tu tai lieu):

    1. `reasoning_format: "hidden"` — cac model "reasoning" (vd
       `qwen/qwen3.6-27b`) mac dinh tra ve khoi `<think>...</think>` NGAY
       TRONG `message.content`. `_bo_khoi_nghi` (lop cha) van loc lai LAN
       NUA cho chac — phong khi mot model/phien ban khong tuan thu tham so
       nay.
    2. `max_tokens: 4096` — model nay danh GAN NHU TOAN BO ngan sach token
       cho suy luan noi bo (do THAT: mot cau ngan don gian da dung toi 3793/
       4096 token suy luan, chi con ~30 token cho cau tra loi that). KHONG
       dat gioi han nay, mot doan van tuong doi dai se bi CAT NGANG GIUA
       CHUNG SUY LUAN — API van tra 200 nhung `message.content` RONG (khong
       phai loi, khong phai rate limit, chi la het cho truoc khi kip viet
       cau tra loi) — tung xay ra THAT va gay `TranslationProviderError`
       "nội dung rỗng" o moi doan van dai vua phai.
    """

    name = "groq"
    EXTRA_PAYLOAD: Dict[str, object] = {
        "reasoning_format": "hidden",
        "max_tokens": 4096,
    }

    def __init__(self, *, api_key: str, model: str,
                client: Optional[httpx.Client] = None):
        if not (api_key and model):
            raise TranslationProviderError(
                "Thiếu GROQ_API_KEY/GROQ_MODEL.")
        super().__init__(base_url="https://api.groq.com/openai/v1",
                         api_key=api_key, model=model, client=client)


class CloudflareWorkersAIProvider(TranslationProvider):
    """
    Cloudflare Workers AI — REST RIENG (khac hinh dang OpenAI chat
    completions): `POST /accounts/{account_id}/ai/run/{model}` voi than
    `{"messages": [...]}`, ket qua o `result.response`.
    """

    name = "cloudflare"
    TIMEOUT_SECONDS = 60.0

    def __init__(self, *, account_id: str, api_token: str, model: str,
                client: Optional[httpx.Client] = None):
        if not (account_id and api_token and model):
            raise TranslationProviderError(
                "Thiếu CLOUDFLARE_ACCOUNT_ID/CLOUDFLARE_API_TOKEN/"
                "CLOUDFLARE_WORKERS_AI_MODEL.")
        self._model = model
        self._client = client or httpx.Client(
            base_url="https://api.cloudflare.com/client/v4",
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=self.TIMEOUT_SECONDS,
        )
        self._path = f"/accounts/{account_id}/ai/run/{model}"

    def translate_segment(self, text: str, *,
                          context: TranslationContext) -> str:
        sach = (text or "").strip()
        if not sach:
            raise TranslationProviderError("Đoạn văn rỗng, không có gì để dịch.")
        payload = {
            "messages": [
                {"role": "system", "content": _he_thong_prompt(context)},
                {"role": "user", "content": _nguoi_dung_prompt(sach, context)},
            ],
        }
        try:
            resp = self._client.post(self._path, json=payload)
        except httpx.HTTPError as exc:
            raise TranslationProviderError(
                f"Không gọi được dịch vụ dịch: {exc}") from exc

        if resp.status_code == 429:
            retry_at = _retry_after_to_iso(resp)
            raise ProviderRateLimited(
                f"Model đang bị giới hạn tốc độ: {resp.text[:200]}",
                retry_at=retry_at)
        if resp.status_code != 200:
            raise TranslationProviderError(
                f"Dịch vụ dịch trả lỗi {resp.status_code}: {resp.text[:300]}")

        try:
            du_lieu = resp.json()
            if not du_lieu.get("success", True):
                raise TranslationProviderError(
                    f"Dịch vụ dịch báo lỗi: {du_lieu.get('errors')}")
            noi_dung = du_lieu["result"]["response"]
        except (KeyError, ValueError) as exc:
            raise TranslationProviderError(
                "Phản hồi dịch vụ dịch không đúng định dạng mong đợi.") from exc

        # Cung rao chan voi Groq — mot so model "reasoning" (kha nang co tren
        # Workers AI trong tuong lai) co the tra `<think>` ngay trong content.
        ket_qua = _bo_khoi_nghi((noi_dung or "").strip())
        if not ket_qua:
            raise TranslationProviderError("Dịch vụ dịch trả về nội dung rỗng.")
        return ket_qua


@dataclass
class ConfiguredProvider:
    """Boc mot `TranslationProvider` cu the kem sieu du lieu catalog VA
    trang thai SONG (trong tien trinh, mat khi restart — chap nhan duoc vi
    day chi la goi y hien thi, khong phai nguon su that; nguon su that van
    la phan hoi THAT tu lan goi ke tiep)."""

    provider_id: str
    model_id: str
    display_name: str
    quality_hint: str
    provider: TranslationProvider
    free_tier: bool = True
    #: V5.1 BYOK — "shared" (mac dinh, kho Fanfic dung chung, xay dung o
    #: `build_provider_registry`) hoac "personal" (API key rieng cua MOT
    #: nguoi dung, xay dung o `translation_byok_service.py`).
    credential_source: str = "shared"
    _status: ProviderStatus = field(default=ProviderStatus.UNKNOWN, repr=False)
    _reset_at: str = field(default="", repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def catalog_entry(self) -> ProviderCatalogEntry:
        with self._lock:
            return ProviderCatalogEntry(
                provider_id=self.provider_id, model_id=self.model_id,
                display_name=self.display_name, quality_hint=self.quality_hint,
                free_tier=self.free_tier, status=self._status,
                reset_at=self._reset_at)

    def is_available_now(self) -> bool:
        with self._lock:
            if self._status in (ProviderStatus.AVAILABLE, ProviderStatus.UNKNOWN):
                return True
            if not self._reset_at:
                return False
            try:
                moc = datetime.fromisoformat(self._reset_at)
            except ValueError:
                return False
            if moc.tzinfo is None:
                moc = moc.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) >= moc

    def translate_segment(self, text: str, *,
                          context: TranslationContext) -> str:
        try:
            ket_qua = self.provider.translate_segment(text, context=context)
        except ProviderRateLimited as exc:
            with self._lock:
                self._status = ProviderStatus.RATE_LIMITED
                self._reset_at = exc.retry_at
            raise
        except ProviderQuotaExhausted as exc:
            with self._lock:
                self._status = ProviderStatus.QUOTA_EXHAUSTED
                self._reset_at = exc.retry_at
            raise
        except TranslationProviderError:
            with self._lock:
                self._status = ProviderStatus.UNAVAILABLE
                self._reset_at = ""
            raise
        with self._lock:
            self._status = ProviderStatus.AVAILABLE
            self._reset_at = ""
        return ket_qua


class ProviderRegistry:
    """
    Chon provider theo Part Q3:
      - AUTO: thu LAN LUOT theo thu tu cau hinh, dung o provider DAU TIEN
        con dung duoc.
      - MANUAL + fallback TAT: CHI thu provider da chon; het han muc bao
        `AllProvidersUnavailable` NGAY, KHONG thu provider khac.
      - MANUAL + fallback BAT: thu provider da chon TRUOC, roi cac provider
        MIEN PHI con lai theo thu tu cau hinh.

    KHONG BAO GIO tu dua mot provider `free_tier=False` vao duong thu —
    registry nay hien chi chua provider mien phi (kiem tra o
    `build_provider_registry`), nhung diem chan nay giu lai o day de an toan
    kep neu danh sach provider mo rong sau nay.
    """

    def __init__(self, providers: List[ConfiguredProvider]):
        self._providers = [p for p in providers if p.free_tier]

    def __bool__(self) -> bool:
        return bool(self._providers)

    def catalog(self) -> List[ProviderCatalogEntry]:
        return [p.catalog_entry() for p in self._providers]

    def get(self, provider_id: str) -> Optional[ConfiguredProvider]:
        for p in self._providers:
            if p.provider_id == provider_id:
                return p
        return None

    def as_list(self) -> List[ConfiguredProvider]:
        """Ban sao danh sach provider DUNG CHUNG, theo dung thu tu cau hinh —
        dung o tang service khi can GHEP them provider CA NHAN (Part F,
        `translate_segment_with_personal`)."""
        return list(self._providers)

    @staticmethod
    def _thu_theo_thu_tu(thu_tu: List[ConfiguredProvider], text: str, *,
                         context: TranslationContext
                         ) -> Tuple[str, ProviderProvenance]:
        """Vong lap LOI CHUNG — thu LAN LUOT dung thu tu da quyet dinh san
        (boi `translate_segment`/`translate_segment_with_personal`), dung o
        provider DAU TIEN con dung duoc. Tach rieng de CA HAI ham goi cung
        MOT logic, khong lap lai."""
        som_nhat_reset = ""
        for cp in thu_tu:
            if cp is None:
                continue
            if not cp.is_available_now():
                entry = cp.catalog_entry()
                if entry.reset_at and (not som_nhat_reset
                                       or entry.reset_at < som_nhat_reset):
                    som_nhat_reset = entry.reset_at
                continue
            try:
                ket_qua = cp.translate_segment(text, context=context)
            except TranslationProviderError:
                entry = cp.catalog_entry()
                if entry.reset_at and (not som_nhat_reset
                                       or entry.reset_at < som_nhat_reset):
                    som_nhat_reset = entry.reset_at
                continue
            return ket_qua, ProviderProvenance(
                provider_id=cp.provider_id, model_id=cp.model_id,
                pass_type=context.vai_tro, success=True,
                attempted_at=_now_iso(),
                credential_source=cp.credential_source)
        raise AllProvidersUnavailable(retry_not_before=som_nhat_reset)

    def translate_segment(self, text: str, *, context: TranslationContext,
                          mode: str = "auto",
                          selected_provider_id: str = "",
                          allow_fallback: bool = True
                          ) -> Tuple[str, ProviderProvenance]:
        if not self._providers:
            raise AllProvidersUnavailable()

        if mode == "manual" and selected_provider_id:
            chon = self.get(selected_provider_id)
            thu_tu = [chon] if chon else []
            if allow_fallback:
                thu_tu += [p for p in self._providers if p is not chon]
        else:
            thu_tu = list(self._providers)

        return self._thu_theo_thu_tu(thu_tu, text, context=context)

    def translate_segment_with_personal(
        self, text: str, *, context: TranslationContext,
        mode: str = "auto", selected_provider_id: str = "",
        allow_fallback: bool = True,
        personal_providers: Optional[List[ConfiguredProvider]] = None,
        prefer_personal: bool = False,
    ) -> Tuple[str, ProviderProvenance]:
        """
        Bien the CO tich hop provider CA NHAN cua MOT nguoi dung (V5.1 Part
        F) — `personal_providers` PHAI da duoc giai ma DUNG cho DUNG nguoi
        dung nay (xay boi tang service, xem
        `translation_byok_service.ProviderConnectionService`); ham nay KHONG
        BAO GIO tu tra cuu/giai ma — chi nhan danh sach da san sang de dung.

        Thu tu (Part F):
          - `prefer_personal=False` (mac dinh): Fanfic dung chung TRUOC, ca
            nhan la du phong.
          - `prefer_personal=True`: ca nhan TRUOC, Fanfic dung chung la du
            phong.
          - `mode="manual"`: `selected_provider_id` co the tro toi CA
            provider dung chung LAN provider ca nhan (tim trong CA HAI danh
            sach) — dung y "provider_id nhu 'groq' dung chung giua shared va
            personal, phan biet boi credential_source".

        KHONG co danh sach ca nhan (`personal_providers` rong/None) thi hanh
        vi Y HET `translate_segment` — dam bao khong pha vo bat ky luong
        khong dung BYOK nao.
        """
        ca_nhan = list(personal_providers or [])
        dung_chung = list(self._providers)

        if mode == "manual" and selected_provider_id:
            tat_ca = dung_chung + ca_nhan
            chon = next((p for p in tat_ca if p.provider_id == selected_provider_id), None)
            thu_tu = [chon] if chon else []
            if allow_fallback:
                thu_tu += [p for p in tat_ca if p is not chon]
        elif prefer_personal:
            thu_tu = ca_nhan + dung_chung
        else:
            thu_tu = dung_chung + ca_nhan

        return self._thu_theo_thu_tu(thu_tu, text, context=context)


class ConnectionCheckError(TranslationProviderError):
    """
    Loi kiem tra ket noi CA NHAN (V5.1 Part E) — `code` la MOT trong bon gia
    tri SACH quy dinh o yeu cau goc, KHONG BAO GIO kem theo header/response
    goc cua nha cung cap (`str(exc)` van la thong diep tieng Viet an toan
    cho nguoi dung, `code` la thong diep MAY doc duoc cho frontend re nhanh
    UI theo dung loai loi).
    """

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


#: Timeout NGAN cho kiem tra ket noi — day la mot lenh GET nhe, khong phai
#: mot lan dich, khong can du 60s nhu `_OpenAICompatFreeProvider`.
_KIEM_TRA_TIMEOUT_SECONDS = 15.0


def kiem_tra_ket_noi_groq(api_key: str, model: str, *,
                         client: Optional[httpx.Client] = None) -> None:
    """
    Xac thuc MOT api key Groq CA NHAN + kiem tra model co san — dung
    `GET /models` (liet ke model), KHONG dich thu bat ky doan van nao, nen
    KHONG TON HAN MUC DICH cua nguoi dung (dung y "does not waste
    translation quota" cua yeu cau goc).

    Khong nem gi = thanh cong. Nem `ConnectionCheckError` voi `code` la MOT
    trong "INVALID_KEY"/"RATE_LIMITED"/"PROVIDER_UNAVAILABLE"/
    "MODEL_UNAVAILABLE" — KHONG BAO GIO kem response/header goc cua Groq.
    """
    c = client or httpx.Client(
        base_url="https://api.groq.com/openai/v1",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=_KIEM_TRA_TIMEOUT_SECONDS)
    try:
        resp = c.get("/models")
    except httpx.HTTPError as exc:
        raise ConnectionCheckError(
            "PROVIDER_UNAVAILABLE", "Không kết nối được Groq.") from exc

    if resp.status_code == 401:
        raise ConnectionCheckError("INVALID_KEY", "API key không hợp lệ.")
    if resp.status_code == 429:
        raise ConnectionCheckError(
            "RATE_LIMITED", "Đang bị giới hạn tốc độ, thử lại sau.")
    if resp.status_code != 200:
        raise ConnectionCheckError(
            "PROVIDER_UNAVAILABLE", "Groq hiện không phản hồi đúng.")

    try:
        du_lieu = resp.json()
        cac_model = {m.get("id") for m in (du_lieu.get("data") or [])}
    except Exception as exc:
        raise ConnectionCheckError(
            "PROVIDER_UNAVAILABLE",
            "Phản hồi từ Groq không đúng định dạng mong đợi.") from exc
    if model not in cac_model:
        raise ConnectionCheckError(
            "MODEL_UNAVAILABLE",
            f"Model {model} không khả dụng với API key này.")


def build_provider_registry(env: Optional[Dict[str, str]] = None
                            ) -> ProviderRegistry:
    """
    Doc bien moi truong (mac dinh `os.environ`) va dung cac provider
    MIEN PHI da cau hinh du. Provider thieu bien -> BO QUA IM LANG (khong
    nem loi) — dung y voi `build_provider` (Vong 2): moi truong dev/test
    khong co credential van phai chay duoc, chi la registry se RONG.
    """
    e = env if env is not None else os.environ
    cho_phep_tra_phi = e.get("TRANSLATION_ALLOW_PAID_PROVIDER", "false").strip().lower() == "true"

    providers: List[ConfiguredProvider] = []

    groq_key = e.get("GROQ_API_KEY", "").strip()
    groq_model = e.get("GROQ_MODEL", "").strip()
    if groq_key and groq_model:
        providers.append(ConfiguredProvider(
            provider_id="groq", model_id=groq_model,
            display_name=f"Qwen · Groq", quality_hint="nhanh, miễn phí",
            provider=GroqProvider(api_key=groq_key, model=groq_model),
            free_tier=True))

    cf_account = e.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    cf_token = e.get("CLOUDFLARE_API_TOKEN", "").strip()
    cf_model = e.get("CLOUDFLARE_WORKERS_AI_MODEL", "").strip()
    if cf_account and cf_token and cf_model:
        providers.append(ConfiguredProvider(
            provider_id="cloudflare", model_id=cf_model,
            display_name=f"Qwen · Cloudflare", quality_hint="miễn phí",
            provider=CloudflareWorkersAIProvider(
                account_id=cf_account, api_token=cf_token, model=cf_model),
            free_tier=True))

    # Provider "tuy chinh" (Vong 2) — CHI dua vao registry neu duoc danh dau
    # mien phi qua bien rieng, tranh vo tinh coi mot endpoint tra phi la
    # "mien phi tu dong thu". Mac dinh AN (khong bat buoc dat) vi day thuong
    # la endpoint tu quan ly cua nguoi dung, khong phai mot dich vu cong khai
    # co the phan loai mien-phi/tra-phi mot cach dang tin cay tu ben ngoai.
    custom_url = e.get("TRANSLATION_BASE_URL", "").strip()
    custom_key = e.get("TRANSLATION_API_KEY", "").strip()
    custom_model = e.get("TRANSLATION_MODEL", "").strip()
    custom_free = e.get("TRANSLATION_CUSTOM_PROVIDER_FREE", "false").strip().lower() == "true"
    if custom_url and custom_key and custom_model and (custom_free or cho_phep_tra_phi):
        from server.translation_providers import DocuTranslateProvider

        providers.append(ConfiguredProvider(
            provider_id="custom", model_id=custom_model,
            display_name="Tuỳ chỉnh", quality_hint="theo cấu hình riêng",
            provider=DocuTranslateProvider(
                base_url=custom_url, api_key=custom_key, model=custom_model),
            free_tier=custom_free))

    if not cho_phep_tra_phi:
        providers = [p for p in providers if p.free_tier]
    return ProviderRegistry(providers)
