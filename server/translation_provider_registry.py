"""
Dang ky NHIEU provider dich MIEN PHI (Part Q, mo rong da model o Part R —
overnight Phase 3, V5.2).

MUC TIEU THIET KE (theo dung yeu cau goc):
- Suy luan tu xa MIEN PHI TRUOC. Khong yeu cau LLM cuc bo, khong yeu cau GPU
  rieng, KHONG BAO GIO tu dong chuyen sang provider TRA PHI.
- Moi nha cung cap duoc cau hinh qua BIEN MOI TRUONG RIENG cua no, khong dung
  chung mot blob JSON — moi bi mat co the thu hoi doc lap:
    GROQ_API_KEY (+ GROQ_MODEL tuy chon, chi de THEM mot model ngoai danh
      sach curated — xem `translation_model_profiles.py`)
    CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, CLOUDFLARE_WORKERS_AI_MODEL
    TRANSLATION_BASE_URL, TRANSLATION_API_KEY, TRANSLATION_MODEL
      (provider "tuy chinh" — bat ky endpoint tuong thich OpenAI nao, da co
      tu Vong 2 cua V5)
- Part R (overnight Phase 3): MOT `GROQ_API_KEY` gio dua VAO BA muc catalog
  rieng (`groq_qwen`/`groq_gpt_oss_120b`/`groq_gpt_oss_20b`), moi muc mang
  tham so RIENG cua model do (`ModelProfile.extra_payload`) — khong con MOT
  model duy nhat cho ca credential. `ProviderRegistry` dinh tuyen AUTO theo
  (quality_mode, vai_tro) qua `_sap_theo_vai_tro`/`route_order` truoc khi ap
  dung thu tu AUTO/MANUAL cu cua Part Q3 — xem
  `translation_model_profiles.ROLE_ROUTING`.
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
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

import httpx

from server.translation_usage import usage_recorder
from server.translation_model_profiles import (
    CEREBRAS_MODEL_PROFILES,
    GROQ_MODEL_PROFILES,
    POLLINATIONS_MODEL_PROFILES,
    ModelProfile,
    route_order,
)
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
    #: True = ket qua nay lay tu cache trong tien trinh
    #: (`TranslationService._TranslationSegmentCache`), KHONG PHAI mot lan
    #: goi model that — tach RIENG khoi `credential_source` (van giu gia tri
    #: GOC tu lan dich THAT dau tien) de khong lam sai lech thong ke "ai da
    #: dich" trong lich su phien ban, dong thoi van biet duoc lan nay khong
    #: ton chi phi/token nao.
    from_cache: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "pass_type": self.pass_type,
            "success": self.success,
            "attempted_at": self.attempted_at,
            "error": self.error,
            "credential_source": self.credential_source,
            "from_cache": self.from_cache,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: Giay — cooldown MAC DINH khi mot provider bao 429/het han muc nhung
#: KHONG kem header `Retry-After` (Groq da tung tra ve dang nay that su, xem
#: `test_429_khong_header_van_la_rate_limited_nhung_khong_bia_moc`). TRUOC
#: V6 cerebras-groq-translation, `_reset_at` bi de RONG trong truong hop
#: nay -> `is_available_now()` coi provider la KHONG DUNG DUOC MAI MAI (rong
#: khong co moc reset nao de so sanh) TRONG SUOT vong doi tien trinh — vua
#: khong dat duoc "cooldown" (khong bao gio thu lai) vua khong dat duoc
#: "khong hammer lien tuc" theo dung nghia (no cham lien tuc VE MOT PHIA:
#: khong bao gio goi lai NHUNG cung khong bao gio bao cho ai biet no co the
#: da hoi phuc). Cho mot cooldown CO HAN thay vi RONG-nghia-la-mai-mai sua
#: CA HAI: provider duoc NGHI mot khoang hop ly (khong hammer), roi TU DONG
#: duoc thu lai (khong "chet" vinh vien trong tien trinh dang chay).
DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 60


def _reset_at_mac_dinh(retry_at: str) -> str:
    """`retry_at` (tu header `Retry-After`, co the RONG) -> moc ISO CHAC
    CHAN co gia tri — dung cooldown mac dinh khi nha cung cap khong bao moc
    cu the nao ca."""
    if retry_at:
        return retry_at
    return (datetime.now(timezone.utc)
            + timedelta(seconds=DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS)
            ).isoformat(timespec="seconds")


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

    #: Tham so THEM vao than request MAC DINH cho lop con — Phan 3C (overnight
    #: Phase 3): tu day tro di, MOI model nen truyen `extra_payload` RIENG qua
    #: `__init__` (xem `GroqProvider`) thay vi ghi de thuoc tinh lop nay, vi
    #: MOT lop provider (`GroqProvider`) gio phuc vu NHIEU model khac nhau
    #: (Qwen/GPT-OSS), moi model can dung MOT tap tham so cua rieng no — ghi
    #: de o CAP LOP se khien moi instance dung CHUNG mot tham so sai cho model
    #: khac. Giu lai thuoc tinh lop de tuong thich nguoc voi ban ghi de cu.
    EXTRA_PAYLOAD: Dict[str, object] = {}

    def __init__(self, *, base_url: str, api_key: str, model: str,
                client: Optional[httpx.Client] = None,
                extra_payload: Optional[Dict[str, object]] = None):
        self._model = model
        self._extra_payload = (
            extra_payload if extra_payload is not None else self.EXTRA_PAYLOAD)
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=self.TIMEOUT_SECONDS,
        )
        #: So token input/output CUA LAN GOI THANH CONG GAN NHAT — `None` cho
        #: den lan goi dau tien, hoac neu phan hoi khong kem `usage` (khong
        #: phai tat ca provider tuong thich OpenAI deu tra truong nay). Doc boi
        #: `ConfiguredProvider.translate_segment` NGAY SAU khi goi xong de ghi
        #: vao `UsageEvent` — KHONG BAO GIO chua noi dung dich/bi mat, chi hai
        #: con so dem token (yeu cau goc muc Usage/Quota: "input/output tokens
        #: when returned").
        self.last_usage: Optional[Dict[str, int]] = None

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
            **self._extra_payload,
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

        # Ghi lai so token NEU phan hoi co kem `usage` (OpenAI-compat chuan) —
        # rong/thieu truong nao thi bo qua truong do, KHONG bia so.
        usage = du_lieu.get("usage") if isinstance(du_lieu, dict) else None
        if isinstance(usage, dict):
            vao = usage.get("prompt_tokens")
            ra = usage.get("completion_tokens")
            self.last_usage = {
                "input_tokens": int(vao) if isinstance(vao, (int, float)) else None,
                "output_tokens": int(ra) if isinstance(ra, (int, float)) else None,
            }
        else:
            self.last_usage = None
        return ket_qua


class GroqProvider(_OpenAICompatFreeProvider):
    """
    Groq — REST tuong thich OpenAI, endpoint mien phi cho Qwen/GPT-OSS.

    Overnight Phase 3 (Part R): MOT lop nay gio phuc vu BA model khac nhau
    (Qwen 3.6 27B, GPT-OSS 120B, GPT-OSS 20B — xem
    `translation_model_profiles.GROQ_MODEL_PROFILES`), moi model mang
    `extra_payload` cua RIENG no (Phan 3C — khong gui tham so cua model nay
    cho model khac). Ban truoc CHI biet MOT model (Qwen) nen `EXTRA_PAYLOAD`
    la thuoc tinh LOP co dinh; gio no la THAM SO qua `profile`.

    Lich su tim thay hai dieu chinh sau tu kiem thu SONG voi API that (khong
    doan duoc tu tai lieu), van giu lai trong ho so Qwen:

    1. `reasoning_format: "hidden"` — Qwen 3.6 27B mac dinh tra ve khoi
       `<think>...</think>` NGAY TRONG `message.content`. `_bo_khoi_nghi`
       (lop cha) van loc lai LAN NUA cho chac. THAM SO NAY KHONG duoc gui
       cho GPT-OSS — tai lieu Groq ghi ro no "not supported" tren hai model
       do, xem `translation_model_profiles`.
    2. `max_completion_tokens: 4096` — tham so HIEN HANH cua Groq cho gioi
       han token dau ra (thay `max_tokens` cu). Ly do can gioi han nay tu
       dau: mot model "reasoning" co the danh gan het ngan sach cho suy luan
       noi bo truoc khi kip viet cau tra loi (do THAT tren Qwen: 3793/4096
       token suy luan, chi con ~30 token cho ban dich) — nhung Phan 3A da
       tat `reasoning_effort` cho Qwen NGAY TU DAU nen rui ro nay giam han;
       gioi han van giu lai phong GPT-OSS (van co reasoning_effort=low) roi
       vao tinh trang tuong tu.
    """

    name = "groq"

    def __init__(self, *, api_key: str, profile: ModelProfile,
                client: Optional[httpx.Client] = None):
        if not (api_key and profile.model_id):
            raise TranslationProviderError(
                "Thiếu GROQ_API_KEY hoặc model_id.")
        self.profile = profile
        super().__init__(base_url="https://api.groq.com/openai/v1",
                         api_key=api_key, model=profile.model_id,
                         client=client, extra_payload=profile.extra_payload)


class CerebrasProvider(_OpenAICompatFreeProvider):
    """
    Cerebras Cloud — REST tuong thich OpenAI, dung lam nha cung cap CHINH cho
    chien luoc san xuat tam thoi (`CEREBRAS_MODEL_PROFILES`: hien CHI GPT-OSS
    120B — `zai-glm-4.7` da bi go vi Cerebras danh dau Preview/sap ngung ho
    tro, xem docstring `translation_model_profiles.py`). Cung nen
    `_OpenAICompatFreeProvider` voi Groq — endpoint/than request giong het,
    chi khac `base_url`/model/tham so rieng qua `profile`.
    """

    name = "cerebras"

    #: `inference-docs.cerebras.ai` — xac nhan 2026-08-15.
    BASE_URL = "https://api.cerebras.ai/v1"

    def __init__(self, *, api_key: str, profile: ModelProfile,
                client: Optional[httpx.Client] = None):
        if not (api_key and profile.model_id):
            raise TranslationProviderError(
                "Thiếu CEREBRAS_API_KEY hoặc model_id.")
        self.profile = profile
        super().__init__(base_url=self.BASE_URL, api_key=api_key,
                         model=profile.model_id, client=client,
                         extra_payload=profile.extra_payload)


class PollinationsProvider(_OpenAICompatFreeProvider):
    """
    Pollinations.ai — REST tuong thich OpenAI chat completions. MOT the hien
    phuc vu MOT model; `build_provider_registry` tao mot `ConfiguredProvider`
    cho MOI model trong `POLLINATIONS_MODEL_PROFILES`, dung mau voi
    `GroqProvider`/`CerebrasProvider`.

    PHUC HOI + VIET LAI: cong viec goc (commit 5137ec0/8672550/2ed65fe,
    2026-08-15) nam tren mot nhanh dung tren `feature/animation-v6` va KHONG
    the merge thang vao main — main da tien hoa DOC LAP file nay (800 -> 1013
    dong). Ban nay giu NGUYEN kien truc main hien tai va chi THEM mot lop con
    nho, thay vi chep lai ~1000 dong lich su.

    TRA PHI THEO MAC DINH — day la diem quan trong nhat. Pollinations dung
    API key dang `sk_...`, va khong the phan loai mien-phi/tra-phi mot cach
    dang tin cay tu ben ngoai. Vi vay `build_provider_registry` KHONG dua
    provider nay vao registry tru khi `POLLINATIONS_FREE_TIER=true` duoc dat
    TUONG MINH (hoac rao chan chung `TRANSLATION_ALLOW_PAID_PROVIDER=true`) —
    cung dung mau voi provider "custom" da co san. Khong dat gi thi provider
    nay IM LANG khong ton tai: khong goi mang, khong rui ro tinh phi.

    THU LAI CUC BO — CHI cho `ProviderRateLimited` (429), co gioi han
    (`retry_count`, mac dinh 0 = tat). Het luot van 429 thi de loi LAN LEN cho
    `ProviderRegistry` chuyen sang nha cung cap DOC LAP tiep theo, KHONG thu
    model Pollinations khac: gioi han toc do cua ho nay la theo TAI KHOAN nen
    doi model cung nha cung cap la vo nghia.

    KHONG thu lai cac loi khac (401/402 sai credential, JSON sai hinh dang,
    noi dung rong): cung mot yeu cau se that bai giong het, thu lai chi lam
    cham chuoi fallback. GIOI HAN DA BIET: lop cha `_OpenAICompatFreeProvider`
    goi ca loi mang (`httpx.HTTPError`) thanh `TranslationProviderError`
    chung, nen o day KHONG phan biet duoc "mang chap chon" (dang thu lai) voi
    "credential sai" (khong dang thu lai). Ban goc giai quyet bang cach THEM
    mot bo phan loai loi moi (`ProviderTransientError`/`ProviderAccountError`)
    vao lop cha — day CHINH LA phan gay xung dot voi main, nen CO Y khong port
    sang. Neu can retry loi mang sau nay: mo rong lop cha mot cach co chu dich
    trong MOT PR rieng, dung nhet vao day.
    """

    name = "pollinations"

    #: Cho ghi de qua `POLLINATIONS_BASE_URL` de kiem thu/trien khai rieng.
    DEFAULT_BASE_URL = "https://gen.pollinations.ai/v1"

    #: Khoang nghi GIUA hai lan thu cuc bo. NHO co y: day la worker chay trong
    #: vong lap, khong phai request nguoi dung dang cho, nen thu lai nhanh hon
    #: la bat nguoi dung cho mot backoff day du.
    RETRY_DELAY_SECONDS = 0.2

    def __init__(self, *, api_key: str, profile: ModelProfile,
                base_url: str = "",
                client: Optional[httpx.Client] = None,
                retry_count: int = 0):
        if not (api_key and profile.model_id):
            raise TranslationProviderError(
                "Thiếu POLLINATIONS_API_KEY hoặc model_id.")
        self.profile = profile
        self._retry_count = max(0, int(retry_count))
        super().__init__(base_url=base_url or self.DEFAULT_BASE_URL,
                         api_key=api_key, model=profile.model_id,
                         client=client, extra_payload=profile.extra_payload)

    def translate_segment(self, text: str, *,
                          context: TranslationContext) -> str:
        loi_cuoi: Optional[ProviderRateLimited] = None
        for lan in range(self._retry_count + 1):
            try:
                return super().translate_segment(text, context=context)
            except ProviderRateLimited as exc:
                loi_cuoi = exc
                if lan < self._retry_count:
                    time.sleep(self.RETRY_DELAY_SECONDS)
                    continue
                raise
        # Khong the toi day (vong lap luon return hoac raise) — giu lai cho
        # ro rang thay vi de ham roi ra `None` neu ai sua vong lap sau nay.
        raise loi_cuoi if loi_cuoi else TranslationProviderError(
            "Pollinations: không dịch được và không rõ lý do.")


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
        bat_dau = time.monotonic()

        def _do_do_tre_ms() -> int:
            return round((time.monotonic() - bat_dau) * 1000)

        try:
            ket_qua = self.provider.translate_segment(text, context=context)
        except ProviderRateLimited as exc:
            with self._lock:
                self._status = ProviderStatus.RATE_LIMITED
                self._reset_at = _reset_at_mac_dinh(exc.retry_at)
            usage_recorder().ghi(
                provider_id=self.provider_id, model_id=self.model_id,
                credential_source=self.credential_source,
                pass_type=context.vai_tro, outcome="rate_limited",
                latency_ms=_do_do_tre_ms())
            raise
        except ProviderQuotaExhausted as exc:
            with self._lock:
                self._status = ProviderStatus.QUOTA_EXHAUSTED
                self._reset_at = _reset_at_mac_dinh(exc.retry_at)
            usage_recorder().ghi(
                provider_id=self.provider_id, model_id=self.model_id,
                credential_source=self.credential_source,
                pass_type=context.vai_tro, outcome="quota_exhausted",
                latency_ms=_do_do_tre_ms())
            raise
        except TranslationProviderError:
            with self._lock:
                self._status = ProviderStatus.UNAVAILABLE
                self._reset_at = ""
            usage_recorder().ghi(
                provider_id=self.provider_id, model_id=self.model_id,
                credential_source=self.credential_source,
                pass_type=context.vai_tro, outcome="error",
                latency_ms=_do_do_tre_ms())
            raise
        with self._lock:
            self._status = ProviderStatus.AVAILABLE
            self._reset_at = ""
        #: `last_usage` la thuoc tinh TUY CHON (duck-typed) — chi cac provider
        #: tuong thich OpenAI qua `_OpenAICompatFreeProvider` (Groq, Cerebras)
        #: co no. Provider khac (mock, Cloudflare, tuy chinh) khong co thuoc
        #: tinh nay -> `getattr` tra `None`, khong ghi token (KHONG bia so).
        su_dung = getattr(self.provider, "last_usage", None)
        usage_recorder().ghi(
            provider_id=self.provider_id, model_id=self.model_id,
            credential_source=self.credential_source,
            pass_type=context.vai_tro, outcome="success",
            latency_ms=_do_do_tre_ms(),
            input_tokens=(su_dung or {}).get("input_tokens"),
            output_tokens=(su_dung or {}).get("output_tokens"))
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
    def _groq_model_key(provider_id: str) -> Optional[str]:
        """`"groq_qwen"` -> `"qwen"`; provider KHONG phai Groq curated (vd
        `"cloudflare"`, `"custom"`, `"groq"` legacy) -> `None`."""
        tien_to = "groq_"
        if provider_id.startswith(tien_to):
            return provider_id[len(tien_to):]
        return None

    @staticmethod
    def _ho_provider(provider_id: str) -> str:
        """
        "Ho" (family) cua MOT provider_id — dung DE GIOI HAN fallback BYOK
        tuong minh (xem `translate_segment_with_personal`): mot ket noi Groq
        ca nhan duoc phep tu dong chuyen giua CAC MODEL CUA CHINH NO
        (`groq_qwen` <-> `groq_gpt_oss_120b` <-> `groq_gpt_oss_20b`, cung MOT
        api key), NHUNG khong bao gio duoc phep "tràn" sang provider dung
        chung/ho khac — dung y voi yeu cau goc "do NOT silently fall back to
        shared credentials". Ho "cerebras" hien CHI co MOT model curated
        (`gpt_oss_120b`, xem `translation_model_profiles.py`) nen khong co
        fallback noi bo nao xay ra trong thuc te — co che nay VAN giu nguyen
        cho tuong lai neu Cerebras them model curated thu hai.

        Provider da-model curated (groq_*, cerebras_*) tra ve TEN HO chung
        ("groq"/"cerebras"); provider don (vd "cloudflare", "custom",
        "groq" legacy) tra ve CHINH provider_id — moi provider don la ho CUA
        RIENG NO, khong gop voi ai.
        """
        for tien_to in ("groq_", "cerebras_"):
            if provider_id.startswith(tien_to):
                return tien_to.rstrip("_")
        return provider_id

    @classmethod
    def _sap_theo_vai_tro(cls, providers: List[ConfiguredProvider],
                          context: TranslationContext
                          ) -> List[ConfiguredProvider]:
        """
        Sap lai NHOM model Groq curated theo (quality_mode, vai_tro) — Phan
        3D. Provider KHAC (Cloudflare, tuy chinh, Groq legacy, Cerebras, ca
        nhan BYOK) GIU NGUYEN vi tri tuong doi — nhom Groq da sap duoc CHEN
        LAI dung tai vi tri no chiem trong danh sach dau vao, KHONG bi day
        len dau mot cach vo dieu kien. Dieu nay quan trong tu khi Cerebras
        tro thanh nha cung cap CHIA SE duoc uu tien HON Groq (chien luoc san
        xuat tam thoi: Cerebras GPT-OSS 120B -> Groq Qwen) —
        `build_provider_registry` dang ky Cerebras TRUOC Groq trong danh sach
        dau vao chinh xac de dua vao hanh vi "giu nguyen vi tri" nay; neu ham
        nay vo dieu kien day nhom Groq len dau (nhu ban truoc Phan R), Groq se
        luon bi thu TRUOC Cerebras bat cu khi nao `quality_mode`/`vai_tro`
        khop mot muc trong `ROLE_ROUTING` — sai hoan toan thu tu san xuat
        mong muon. Vi du mau Phan 3F "Qwen -> GPT-OSS 120B -> GPT-OSS 20B ->
        Cloudflare -> ca nhan" (khi Groq dung truoc trong danh sach dau vao)
        van dung y het cach ghep nay — chi la truong hop rieng khi khong co
        provider nao dung TRUOC nhom Groq.

        Khong dinh tuyen duoc (thieu `quality_mode`, hoac to hop la) thi
        TRA NGUYEN thu tu dau vao — an toan mac dinh, khong lam gi ca.
        """
        thu_tu_khoa = route_order(context.quality_mode, context.vai_tro)
        if not thu_tu_khoa:
            return providers

        vi_tri_nhom_groq: Optional[int] = None
        theo_khoa: Dict[str, ConfiguredProvider] = {}
        khac: List[ConfiguredProvider] = []
        for p in providers:
            khoa = cls._groq_model_key(p.provider_id)
            if khoa is not None and khoa not in theo_khoa:
                theo_khoa[khoa] = p
                if vi_tri_nhom_groq is None:
                    # Vi tri nhom Groq se duoc CHEN VAO trong `khac` — chinh
                    # la do dai cua `khac` NGAY LUC gap phan tu Groq DAU TIEN
                    # (moi phan tu KHAC Groq truoc do da nam trong `khac`).
                    vi_tri_nhom_groq = len(khac)
            else:
                khac.append(p)

        if vi_tri_nhom_groq is None:
            return providers  # khong co provider Groq nao trong danh sach

        da_dinh_tuyen = [theo_khoa[k] for k in thu_tu_khoa if k in theo_khoa]
        # Model Groq curated nhung KHONG nam trong bang dinh tuyen (khong nen
        # xay ra voi ba model hien co, nhung an toan cho tuong lai) — giu lai,
        # noi vao CUOI nhom Groq thay vi am tham bi rot.
        con_lai_groq = [p for k, p in theo_khoa.items() if k not in thu_tu_khoa]
        nhom_groq = da_dinh_tuyen + con_lai_groq
        return khac[:vi_tri_nhom_groq] + nhom_groq + khac[vi_tri_nhom_groq:]

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
            # AUTO: sap theo vai tro/che do (Phan 3D) TRUOC khi thu — MANUAL
            # giu nguyen (nguoi dung da chon ro, khong tu doi y ho).
            thu_tu = self._sap_theo_vai_tro(list(self._providers), context)

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
            # Provider CA NHAN dung CHINH provider_id voi provider DUNG CHUNG
            # tuong ung (vd ca hai deu la "groq_qwen" — xem
            # `translation_byok_service.build_all_model_providers`) — CO CHU
            # DICH, giu nguyen API cu (AUTO + `prefer_personal_provider` chi
            # can NOI, khong can PHAN BIET id). Khi MANUAL chon dung id nay,
            # `tat_ca` PHAI tim ben nao TRUOC quyet dinh ben nao duoc chon
            # neu ca hai deu khop: `prefer_personal=True` (nguoi dung tuong
            # minh chon "API key cua toi") tim ca nhan TRUOC — dam bao ho
            # nhan DUNG ket noi cua chinh ho, khong phai kho dung chung co
            # cung ten model.
            tat_ca = (ca_nhan + dung_chung) if prefer_personal else (dung_chung + ca_nhan)
            chon = next((p for p in tat_ca if p.provider_id == selected_provider_id), None)
            thu_tu = [chon] if chon else []
            if allow_fallback and chon is not None:
                if chon.credential_source == "personal":
                    # BYOK CHON TUONG MINH (yeu cau goc: "use that user's
                    # provider directly... do not silently fall back to
                    # shared credentials"): CHI duoc phep chuyen sang MODEL
                    # KHAC CUNG HO ca nhan (vd Groq Qwen -> Groq GPT-OSS
                    # 120B, CUNG mot api key nguoi dung) — khong bao gio cham
                    # toi `dung_chung` hay ca nhan cua ho KHAC.
                    ho = self._ho_provider(chon.provider_id)
                    thu_tu += [p for p in ca_nhan
                              if p is not chon and self._ho_provider(p.provider_id) == ho]
                else:
                    thu_tu += [p for p in tat_ca if p is not chon]
        else:
            # AUTO: sap THEO NHOM (Phan 3D) — dung chung va ca nhan la HAI
            # nhom Groq doc lap (ca nhan la mot API key rieng), moi nhom sap
            # rieng theo vai tro/che do roi moi ghep theo thu tu uu tien
            # dung-chung-truoc/ca-nhan-truoc da co (Part F).
            dung_chung = self._sap_theo_vai_tro(dung_chung, context)
            ca_nhan = self._sap_theo_vai_tro(ca_nhan, context)
            thu_tu = (ca_nhan + dung_chung) if prefer_personal else (dung_chung + ca_nhan)

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


def kiem_tra_ket_noi_cerebras(api_key: str, model: str, *,
                              client: Optional[httpx.Client] = None) -> None:
    """
    Xac thuc MOT api key Cerebras CA NHAN + kiem tra model co san — cung
    khuon voi `kiem_tra_ket_noi_groq` (`GET /models`, khong dich thu, khong
    ton han muc cua nguoi dung).
    """
    c = client or httpx.Client(
        base_url=CerebrasProvider.BASE_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=_KIEM_TRA_TIMEOUT_SECONDS)
    try:
        resp = c.get("/models")
    except httpx.HTTPError as exc:
        raise ConnectionCheckError(
            "PROVIDER_UNAVAILABLE", "Không kết nối được Cerebras.") from exc

    if resp.status_code == 401:
        raise ConnectionCheckError("INVALID_KEY", "API key không hợp lệ.")
    if resp.status_code == 429:
        raise ConnectionCheckError(
            "RATE_LIMITED", "Đang bị giới hạn tốc độ, thử lại sau.")
    if resp.status_code != 200:
        raise ConnectionCheckError(
            "PROVIDER_UNAVAILABLE", "Cerebras hiện không phản hồi đúng.")

    try:
        du_lieu = resp.json()
        cac_model = {m.get("id") for m in (du_lieu.get("data") or [])}
    except Exception as exc:
        raise ConnectionCheckError(
            "PROVIDER_UNAVAILABLE",
            "Phản hồi từ Cerebras không đúng định dạng mong đợi.") from exc
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

    # Chien luoc san xuat TAM THOI (yeu cau goc): Cerebras la nha cung cap
    # CHIA SE CHINH — dang ky TRUOC Groq trong danh sach nay de thu tu AUTO
    # (`_sap_theo_vai_tro`, giu nguyen vi tri cac provider khong phai Groq)
    # la Cerebras GPT-OSS 120B -> Groq Qwen -> ... dung y yeu cau "Default
    # server-managed translation route" (`zai-glm-4.7` da bi go — xem
    # `translation_model_profiles.py`). `free_tier=True`:
    # Cerebras Cloud co hang mien phi (rate-limited) tuong tu Groq — cung
    # tien de voi `TRANSLATION_ALLOW_PAID_PROVIDER` (rao chan CHUA CAN bat
    # de dung nha cung cap nay).
    cerebras_key = e.get("CEREBRAS_API_KEY", "").strip()
    if cerebras_key:
        for profile_key, profile in CEREBRAS_MODEL_PROFILES.items():
            providers.append(ConfiguredProvider(
                provider_id=f"cerebras_{profile_key}", model_id=profile.model_id,
                display_name=f"Cerebras · {profile.display_name}",
                quality_hint=profile.quality_hint,
                provider=CerebrasProvider(api_key=cerebras_key, profile=profile),
                free_tier=True))

    groq_key = e.get("GROQ_API_KEY", "").strip()
    if groq_key:
        # Phan 3B (overnight Phase 3): MOT credential Groq, BA model curated
        # — KHONG can nhieu API key. Danh sach hien qua
        # `GET /api/translate/providers` (Phan 3H) noi ro tung model/trang
        # thai rieng (Phan 3E), khong gop chung mot dong "Groq".
        for profile_key, profile in GROQ_MODEL_PROFILES.items():
            providers.append(ConfiguredProvider(
                provider_id=f"groq_{profile_key}", model_id=profile.model_id,
                display_name=f"Groq · {profile.display_name}",
                quality_hint=profile.quality_hint,
                provider=GroqProvider(api_key=groq_key, profile=profile),
                free_tier=True))

        # `GROQ_MODEL` (cu, tu Vong 2) — TUONG THICH NGUOC: ai da cau hinh
        # mot model KHONG nam trong ba model curated o tren (vi du mot model
        # Groq moi ra sau nay) van duoc dua vao registry, CONG THEM ba model
        # curated chu khong THAY THE chung.
        legacy_model = e.get("GROQ_MODEL", "").strip()
        curated_ids = {p.model_id for p in GROQ_MODEL_PROFILES.values()}
        if legacy_model and legacy_model not in curated_ids:
            providers.append(ConfiguredProvider(
                provider_id="groq", model_id=legacy_model,
                display_name="Groq · tuỳ chỉnh (GROQ_MODEL)",
                quality_hint="theo cấu hình cũ",
                provider=GroqProvider(
                    api_key=groq_key,
                    profile=ModelProfile(
                        key="legacy", model_id=legacy_model,
                        display_name=legacy_model, quality_hint="")),
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

    # Pollinations.ai — dang ky SAU Cloudflare de thu tu AUTO khong bi doi:
    # Cerebras -> Groq -> Cloudflare -> Pollinations. Thu tu la thu tu CAU
    # HINH nay, nen viec them provider o CUOI khong lam thay doi lua chon cua
    # bat ky (che_do, vai_tro) nao dang co (`ROLE_ROUTING` chi chua khoa model
    # Groq) — khong hoi quy provider cu.
    #
    # RAO CHAN TINH PHI, giong het mau "custom" ngay duoi: Pollinations dung
    # API key `sk_...` va khong the phan loai mien-phi/tra-phi tu ben ngoai
    # mot cach dang tin cay, nen coi la TRA PHI theo mac dinh.
    #
    # HAI LOP CHAN DOC LAP, va lop thu hai manh hon ve tuong: dieu kien duoi
    # day quyet dinh co TAO `ConfiguredProvider` khong, nhung
    # `ProviderRegistry.__init__` con loc `free_tier` VO DIEU KIEN. Hau qua
    # THAT (da kiem o `test_rao_chan_chung_MOT_MINH_van_KHONG_du`):
    # `TRANSLATION_ALLOW_PAID_PROVIDER=true` MOT MINH KHONG du de dung
    # Pollinations — duong duy nhat la `POLLINATIONS_FREE_TIER=true`, tuc la
    # tuyen bo RO rang tai khoan nay o hang mien phi. Khong dat gi thi
    # provider nay im lang khong ton tai: khong goi mang, khong rui ro phi.
    poll_key = e.get("POLLINATIONS_API_KEY", "").strip()
    poll_free = e.get("POLLINATIONS_FREE_TIER", "false").strip().lower() == "true"
    poll_base = e.get("POLLINATIONS_BASE_URL", "").strip()
    try:
        poll_retry = int(e.get("POLLINATIONS_RETRY_COUNT", "0").strip() or "0")
    except ValueError:
        # Cau hinh sai KHONG duoc lam sap ca registry — bo qua im lang giong
        # cach cac provider thieu bien bi bo qua (xem docstring ham nay).
        poll_retry = 0
    if poll_key and (poll_free or cho_phep_tra_phi):
        for profile_key, profile in POLLINATIONS_MODEL_PROFILES.items():
            providers.append(ConfiguredProvider(
                provider_id=f"pollinations_{profile_key}",
                model_id=profile.model_id,
                display_name=f"Pollinations · {profile.display_name}",
                quality_hint=profile.quality_hint,
                provider=PollinationsProvider(
                    api_key=poll_key, profile=profile,
                    base_url=poll_base, retry_count=poll_retry),
                free_tier=poll_free))

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

        # Mission "Hy-MT2 1.8B translation production readiness" (Track B):
        # TUY CHON — cho phep nguoi van hanh ghi de tham so sinh (temperature/
        # top_p/top_k/repetition_penalty/max_tokens...) cho RIENG endpoint
        # "custom" nay, vd de ap dung dung khuyen nghi model-card cua Hy-MT2
        # (huggingface.co/tencent/Hy-MT2-1.8B, fetched 2026-09-01: temperature
        # 0.7, top_p 0.6, top_k 20, repetition_penalty 1.05, max_tokens 4096)
        # SAU KHI co bang chung that tu benchmark that. Rong/khong dat/JSON
        # sai dang -> `{}`, tuc hanh vi Y HET truoc mission nay (temperature=0.3
        # co dinh, khong tham so them) — mot bien cau hinh sai KHONG duoc lam
        # sap ca registry, cung nguyen tac voi cach `poll_retry` duoc doc o
        # tren trong ham nay.
        custom_extra_payload: Dict[str, object] = {}
        raw_generation_params = e.get("TRANSLATION_CUSTOM_GENERATION_PARAMS", "").strip()
        if raw_generation_params:
            try:
                import json as _json
                parsed = _json.loads(raw_generation_params)
                if isinstance(parsed, dict):
                    custom_extra_payload = parsed
            except ValueError:
                custom_extra_payload = {}

        providers.append(ConfiguredProvider(
            provider_id="custom", model_id=custom_model,
            display_name="Tuỳ chỉnh", quality_hint="theo cấu hình riêng",
            provider=DocuTranslateProvider(
                base_url=custom_url, api_key=custom_key, model=custom_model,
                extra_payload=custom_extra_payload),
            free_tier=custom_free))

    if not cho_phep_tra_phi:
        providers = [p for p in providers if p.free_tier]
    return ProviderRegistry(providers)
