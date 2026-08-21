"""
Provider sinh anh — Image Studio V1 (overnight build), PHASE 4.

Hai provider HTTP that:

- `QuickFreeImageProvider` — endpoint legacy an danh `image.pollinations.ai`,
  KHONG key. Cuoc do o `chore/pollinations-anonymous-probe`
  (`docs/reports/pollinations-anonymous-probe-summary.md`) da CHUNG MINH
  tham so `model=` bi bo qua/chuan hoa o che do an danh — vi vay class nay
  TUYET DOI khong nhan tham so chon model tu nguoi goi, va nhan/gan cua no
  LUON la "Quick Free" / "Auto model", khong bao gio ten mot model cu the.

- `SharedPremiumImageProvider` — Pollinations Unified API
  (`gen.pollinations.ai`), dung `POLLINATIONS_API_KEY` server-side (KHONG
  bao gio gui xuong trinh duyet). Day la duong pha tien Fanfic Credit.

CA HAI: khong bao giờ gui `Authorization`/`?key=` cho endpoint legacy; khong
bao gio thieu timeout; loi tra ve la BAN SACH (khong dump nguyen van body
provider — tranh ro ri prompt/chi tiet noi bo qua thong diep loi, xem PHASE
10).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import quote

import httpx

LEGACY_BASE = "https://image.pollinations.ai/prompt"
UNIFIED_IMAGE_URL = "https://gen.pollinations.ai/v1/images/generations"

#: Nhan CO Y duy nhat duoc phep hien thi cho Quick Free — xem canh bao dau file.
QUICK_FREE_LABEL = "Quick Free"
QUICK_FREE_MODEL_LABEL = "Auto model"

DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 60


class ImageProviderError(Exception):
    """Loi co ban — thong diep o day PHAI an toan de hien thi truc tiep cho
    nguoi dung (da lam sach o `_thong_diep_loi_an_toan`)."""


class ImageProviderRateLimited(ImageProviderError):
    def __init__(self, message: str, *, retry_after_seconds: Optional[int] = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ImageProviderUnavailable(ImageProviderError):
    """Dich vu legacy/unified dang khong phan hoi — PHASE 4A: hien trang thai
    KHONG kha dung co kiem soat, KHONG am tham tieu Pollen tra phi."""


class ImageProviderTimeout(ImageProviderError):
    pass


class InvalidImageResponse(ImageProviderError):
    """HTTP 200 nhung KHONG phai anh hop le — dung tieu chi thanh cong CHAT
    tu cuoc do tham (200 + Content-Type bat dau bang image/ + than khong rong)."""


@dataclass(frozen=True)
class GeneratedImage:
    content: bytes
    content_type: str
    byte_size: int
    provider_id: str
    #: Chi Shared Premium moi co gia tri (Quick Free khong tra chi phi that).
    actual_cost_usd: Optional[float] = None


def _danh_gia_anh_hop_le(resp: httpx.Response) -> bool:
    """CUNG tieu chi voi cuoc do tham: HTTP 200 VA Content-Type bat dau
    bang image/ VA than khong rong — xem
    `scripts/probe_pollinations_anonymous.py::_danh_gia_thanh_cong`."""
    ct = resp.headers.get("content-type", "")
    return resp.status_code == 200 and ct.startswith("image/") and len(resp.content) > 0


def _thong_diep_loi_an_toan(resp: httpx.Response) -> str:
    """KHONG dump nguyen van body provider (co the chua chi tiet noi bo/
    prompt nguoi dung goi lai trong loi) — chi ma trang thai + mot cau chung."""
    if resp.status_code in (401, 403):
        return "Nhà cung cấp từ chối xác thực."
    if resp.status_code == 402:
        return "Nhà cung cấp báo hết hạn mức thanh toán."
    if resp.status_code == 429:
        return "Nhà cung cấp đang giới hạn tần suất."
    if resp.status_code >= 500:
        return "Nhà cung cấp đang gặp sự cố."
    return f"Nhà cung cấp từ chối yêu cầu (mã {resp.status_code})."


class _BoDemNguoiKiem:
    """Cooldown dung chung cho ca hai provider — theo dung tinh than
    `DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS`/`_reset_at_mac_dinh` cua
    `server/translation_provider_registry.py`: `Retry-After` RONG khong duoc
    phep nghia la "khoa vinh vien", luon co mot cooldown mac dinh time-boxed."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._khoa_den: Dict[str, float] = {}

    def dang_cooldown(self, key: str) -> Optional[float]:
        with self._lock:
            den = self._khoa_den.get(key)
            if den is None:
                return None
            if time.monotonic() >= den:
                del self._khoa_den[key]
                return None
            return den - time.monotonic()

    def dat_cooldown(self, key: str, seconds: Optional[int]) -> None:
        giay = seconds if seconds and seconds > 0 else DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS
        with self._lock:
            self._khoa_den[key] = time.monotonic() + giay


class _GioiHanMoiIp:
    """Cooldown CUC BO, don gian cho Quick Free an danh — theo IP.

    GIOI HAN DA BIET: bo dem trong tien trinh, nen chay nhieu tien trinh
    (vd uvicorn nhieu worker) se khong chia se han muc — CHAP NHAN DUOC cho
    MVP overnight vi day la luong AN TOAN nhat (khong tra tien that), va ghi
    lai o day de nang cap len kho dung chung (Redis/Appwrite) sau nay khi can
    chinh xac hon."""

    def __init__(self, *, so_lan: int, cua_so_giay: float) -> None:
        self._so_lan = so_lan
        self._cua_so = cua_so_giay
        self._lock = threading.Lock()
        self._lich_su: Dict[str, list] = {}

    def cho_phep(self, ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            lan = [t for t in self._lich_su.get(ip, []) if now - t < self._cua_so]
            if len(lan) >= self._so_lan:
                self._lich_su[ip] = lan
                return False
            lan.append(now)
            self._lich_su[ip] = lan
            return True


class QuickFreeImageProvider:
    """Endpoint legacy an danh — KHONG key, KHONG chon model.

    KHONG BAO GIO nhan tham so `model` tu nguoi goi ham `sinh_anh` — day la
    CO Y, khong phai thieu sot: cho phep truyen model se moi ra lai chinh cai
    bay ma cuoc do tham da phat hien (nhan model rieng le trong khi backend
    hoan toan bo qua no).
    """

    provider_id = "quick_free"

    def __init__(
        self, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        rate_limiter: Optional[_GioiHanMoiIp] = None,
        cooldown: Optional[_BoDemNguoiKiem] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._rate_limiter = rate_limiter or _GioiHanMoiIp(so_lan=6, cua_so_giay=60.0)
        self._cooldown = cooldown or _BoDemNguoiKiem()
        self._client = client

    def _http_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        # `trust_env=False`: KHONG doc bien moi truong nao (ke ca proxy) —
        # cung nguyen tac an toan voi cuoc do tham goc.
        return httpx.Client(timeout=self._timeout, trust_env=False, headers={})

    def sinh_anh(self, *, prompt: str, aspect_ratio_seed: int, client_ip: str) -> GeneratedImage:
        con_lai = self._cooldown.dang_cooldown("quick_free")
        if con_lai is not None:
            raise ImageProviderUnavailable(
                "Quick Free đang tạm nghỉ do lỗi liên tiếp từ nhà cung cấp — "
                "vui lòng thử lại sau ít phút."
            )
        if not self._rate_limiter.cho_phep(client_ip):
            raise ImageProviderRateLimited(
                "Bạn đã tạo ảnh Quick Free khá nhiều trong một phút qua — "
                "vui lòng chờ một chút."
            )

        url = f"{LEGACY_BASE}/{quote(prompt)}"
        tham_so = {"seed": aspect_ratio_seed, "nologo": "true"}
        client = self._http_client()
        try:
            resp = client.get(url, params=tham_so)
        except httpx.TimeoutException as exc:
            self._cooldown.dat_cooldown("quick_free", None)
            raise ImageProviderTimeout("Quick Free phản hồi quá chậm.") from exc
        except httpx.HTTPError as exc:
            self._cooldown.dat_cooldown("quick_free", None)
            raise ImageProviderUnavailable("Quick Free hiện không phản hồi.") from exc
        finally:
            if self._client is None:
                client.close()

        if resp.status_code == 429:
            retry_after = _doc_retry_after(resp)
            self._cooldown.dat_cooldown("quick_free", retry_after)
            raise ImageProviderRateLimited(
                "Quick Free đang bị giới hạn tần suất, vui lòng thử lại sau.",
                retry_after_seconds=retry_after,
            )
        if resp.status_code >= 500:
            self._cooldown.dat_cooldown("quick_free", None)
            raise ImageProviderUnavailable(_thong_diep_loi_an_toan(resp))
        if not _danh_gia_anh_hop_le(resp):
            raise InvalidImageResponse(_thong_diep_loi_an_toan(resp))

        return GeneratedImage(
            content=resp.content,
            content_type=resp.headers.get("content-type", ""),
            byte_size=len(resp.content),
            provider_id=self.provider_id,
        )


class SharedPremiumImageProvider:
    """Pollinations Unified API qua khoa server (`POLLINATIONS_API_KEY`) —
    KHONG BAO GIO gui khoa nay xuong trinh duyet; chi ton tai trong tien
    trinh backend, doc mot lan luc khoi tao."""

    provider_id = "pollinations_shared"

    def __init__(
        self, *, api_key: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        cooldown: Optional[_BoDemNguoiKiem] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        if not api_key:
            raise ImageProviderError(
                "Thiếu POLLINATIONS_API_KEY — Shared Premium chưa được cấu hình."
            )
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._cooldown = cooldown or _BoDemNguoiKiem()
        self._client = client
        # Header gan o TUNG REQUEST (khong bake vao client luc khoi tao) — vi
        # `_client` co the la mot client tiem san cho test (MockTransport),
        # noi ta van muon header Authorization THAT xuat hien tren request de
        # kiem tra duoc dung hanh vi production.
        self._headers = {"Authorization": f"Bearer {self._api_key}"}

    def _http_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(timeout=self._timeout, trust_env=False)

    def sinh_anh(
        self, *, prompt: str, negative_prompt: str, model: str,
        width: int, height: int, quality: str,
    ) -> GeneratedImage:
        con_lai = self._cooldown.dang_cooldown(f"shared:{model}")
        if con_lai is not None:
            raise ImageProviderUnavailable(
                f"Model {model!r} đang tạm nghỉ do lỗi liên tiếp — thử model "
                "khác hoặc chờ ít phút."
            )

        than = {
            "prompt": prompt, "model": model, "width": width, "height": height,
            "quality": quality, "n": 1,
        }
        if negative_prompt:
            than["negative_prompt"] = negative_prompt

        client = self._http_client()
        try:
            resp = client.post(UNIFIED_IMAGE_URL, json=than, headers=self._headers)
        except httpx.TimeoutException as exc:
            self._cooldown.dat_cooldown(f"shared:{model}", None)
            raise ImageProviderTimeout("Shared Premium phản hồi quá chậm.") from exc
        except httpx.HTTPError as exc:
            self._cooldown.dat_cooldown(f"shared:{model}", None)
            raise ImageProviderUnavailable("Shared Premium hiện không phản hồi.") from exc
        finally:
            if self._client is None:
                client.close()

        if resp.status_code == 429:
            retry_after = _doc_retry_after(resp)
            self._cooldown.dat_cooldown(f"shared:{model}", retry_after)
            raise ImageProviderRateLimited(
                "Nhà cung cấp đang giới hạn tần suất cho model này.",
                retry_after_seconds=retry_after,
            )
        if resp.status_code >= 500:
            self._cooldown.dat_cooldown(f"shared:{model}", None)
            raise ImageProviderUnavailable(_thong_diep_loi_an_toan(resp))
        if resp.status_code in (401, 402, 403):
            raise ImageProviderError(_thong_diep_loi_an_toan(resp))
        if not _danh_gia_anh_hop_le(resp):
            raise InvalidImageResponse(_thong_diep_loi_an_toan(resp))

        return GeneratedImage(
            content=resp.content,
            content_type=resp.headers.get("content-type", ""),
            byte_size=len(resp.content),
            provider_id=self.provider_id,
        )


def _doc_retry_after(resp: httpx.Response) -> Optional[int]:
    raw = (resp.headers.get("retry-after") or "").strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def aspect_ratio_to_dimensions(aspect_ratio: str, *, base: int = 1024) -> tuple:
    """PHASE 3 yeu cau 5 ty le: 1:1, 16:9, 9:16, 3:4, 4:3."""
    ti_le = {
        "1:1": (1024, 1024),
        "16:9": (1344, 768),
        "9:16": (768, 1344),
        "3:4": (896, 1152),
        "4:3": (1152, 896),
    }
    return ti_le.get(aspect_ratio, (base, base))


def seed_ngau_nhien() -> int:
    """MOI lan sinh anh (ke ca 'Thu lai' cung noi dung) can mot seed KHAC —
    dung seed on dinh se khien 'Thu lai' tra ve dung 1 anh cu (xem phat hien
    trung lap noi dung tu cuoc do tham). Khong dung `random` (khong an toan
    cho muc dich khac, va o day khong can bao mat) — chi can du khac nhau
    giua cac lan goi, `secrets` la lua chon re va an toan san co."""
    import secrets
    return secrets.randbelow(2**32)
