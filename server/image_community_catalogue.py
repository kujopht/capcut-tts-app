"""
Cong Free — kham pha model anh cong dong (community) mien phi that su.

BO SUNG sau ADDENDUM overnight: KHONG duoc nham "Cong Free" (mot model cong
dong Pollinations bao gia 0 pollen) voi "Quick Free" (endpoint legacy an
danh, khong can biet gia — xem `image_provider_registry.py`). Hai thu HOAN
TOAN khac nhau:

- Quick Free: KHONG key, KHONG bao gio biet/chon model — luon la "Auto model".
- Cong Free: CAN biet dung model nao (de hien thi + de goi dung endpoint
  Unified khi sinh anh那), va viec SINH ANH van di qua Unified API co xac
  thuc server-side (`POLLINATIONS_API_KEY`) — CHI viec XEM DANH SACH la
  khong can khoa (xac minh that o duoi).

NGUON DU LIEU THAT (xac minh bang goi that 2026-08-15, KHONG doan URL):

    GET https://gen.pollinations.ai/image/models

tra ve 200 anonymous (khong can Authorization/khoa), moi phan tu dang:

    {"name": "...", "category": "image", "brand": "...",
     "pricing": {"currency": "pollen", "completionImageTokens": "0.004", ...},
     "output_modalities": ["image"], "input_modalities": [...],
     "capabilities": [...], "description": "...", ...,
     "per_user_rpm": <int|null>  # co mat tren it nhat mot muc community}

QUET THAT luc viet module nay: 55 model co "image" trong output_modalities,
KHONG model nao co moi truong `pricing` bang 0 — nen danh sach "Cong Free"
hop le HIEN TAI la RONG. Day la trang thai THAT, khong phai loi — xem yeu
cau ADDENDUM #3/#7: "Do not hard-code the current screenshots as permanent
truth" / hien thi trang thai khong-kha-dung mot cach co kiem soat.

KHONG suy dien "mien phi" tu thieu truong `pricing` — thieu gia la KHONG XAC
DINH duoc gia, khong phai bang chung gia la 0. Chi model co pricing RO RANG
bang 0 (moi truong numeric deu == 0.0) moi duoc coi la Cong Free.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import List, Optional

import httpx

CATALOGUE_URL = "https://gen.pollinations.ai/image/models"
DEFAULT_TIMEOUT_SECONDS = 15.0
#: Cache TTL — "dynamic" theo yeu cau ADDENDUM #12 (model bien mat/xuat hien
#: phai tu dong phan anh), nhung khong goi API o MOI request trang.
CACHE_TTL_SECONDS = 300.0


class CommunityCatalogueError(Exception):
    """Khong lay duoc danh sach — thong diep AN TOAN de hien thi truc tiep."""


@dataclass(frozen=True)
class CommunityImageModel:
    model_id: str
    display_name: str
    #: "vendouple", "Catniti", ... — phan truoc dau "/" trong id, hoac rong
    #: neu la model chinh thuc cua Pollinations (khong phai community).
    provider_badge: str
    #: Model CHINH THUC cua Pollinations (khong co dau "/") hay do CONG DONG
    #: dua len (`brand/model-name`) — chi anh huong hien thi, khong anh
    #: huong gia/dieu kien loc.
    is_official: bool
    per_user_rpm: Optional[int]
    capabilities: tuple
    description: str
    #: Model cong dong THUONG duoc ghi ro "co the bi go bat cu luc nao" — cac
    #: thong diep nhu vay duoc gan co "Alpha" o UI, KHONG suy dien tu dau
    #: khac. Rong neu khong co dau hieu nao.
    alpha_hint: str = ""


def _tach_provider_badge(model_id: str) -> tuple:
    if "/" in model_id:
        provider, _, _ = model_id.partition("/")
        return provider, False
    return "", True


def _alpha_hint_tu_mo_ta(description: str) -> str:
    mo_ta_thap = (description or "").lower()
    tu_khoa = ("self hosted", "self-hosted", "might get removed", "may get removed",
              "high traffic", "not popular enough")
    if any(k in mo_ta_thap for k in tu_khoa):
        return "Cộng đồng tự lưu trữ — có thể bị gỡ bất kỳ lúc nào nếu ít người dùng."
    return ""


def _gia_bang_khong(pricing: dict) -> bool:
    """`True` CHI KHI co it nhat mot truong gia dang so VA TAT CA deu bang 0.
    Thieu hoan toan truong `pricing`, hoac gia tri khong doc duoc dang so,
    coi la KHONG XAC DINH — khong duoc tinh la mien phi."""
    if not isinstance(pricing, dict):
        return False
    gia_tri = []
    for key, value in pricing.items():
        if key == "currency":
            continue
        try:
            gia_tri.append(float(value))
        except (TypeError, ValueError):
            return False  # gia tri khong doc duoc -> KHONG XAC DINH, loai
    if not gia_tri:
        return False  # khong co truong gia nao -> KHONG XAC DINH, loai
    return all(v == 0.0 for v in gia_tri)


def _loc_mien_phi(raw_entries: list) -> List[CommunityImageModel]:
    ra: List[CommunityImageModel] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        output_modalities = entry.get("output_modalities") or []
        if "image" not in output_modalities:
            continue  # PHASE addendum #5: chi model co OUTPUT la anh
        if not _gia_bang_khong(entry.get("pricing") or {}):
            continue
        model_id = entry.get("name") or ""
        if not model_id:
            continue
        provider_badge, is_official = _tach_provider_badge(model_id)
        mo_ta = entry.get("description") or ""
        ra.append(CommunityImageModel(
            model_id=model_id,
            display_name=entry.get("title") or model_id,
            provider_badge=provider_badge,
            is_official=is_official,
            per_user_rpm=entry.get("per_user_rpm"),
            capabilities=tuple(entry.get("capabilities") or ()),
            description=mo_ta,
            alpha_hint=_alpha_hint_tu_mo_ta(mo_ta),
        ))
    return ra


class CommunityCatalogueCache:
    """Cache TTL don gian, MOT tien trinh — cung tinh than voi cac cache khac
    cua Image Studio (vd `_CACHE_ANH_TAM_MAX` trong `image_service.py`)."""

    def __init__(
        self, *, ttl_seconds: float = CACHE_TTL_SECONDS,
        http_client: Optional[httpx.Client] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._ttl = ttl_seconds
        self._client = http_client
        self._timeout = timeout_seconds
        self._lock = threading.Lock()
        self._cache: Optional[List[CommunityImageModel]] = None
        self._cached_at: float = 0.0
        self._loi_gan_nhat: str = ""

    def lay_danh_sach(self, *, force_refresh: bool = False) -> List[CommunityImageModel]:
        with self._lock:
            now = time.monotonic()
            if (not force_refresh and self._cache is not None
                    and now - self._cached_at < self._ttl):
                return self._cache
            try:
                moi = self._fetch()
            except CommunityCatalogueError as exc:
                self._loi_gan_nhat = str(exc)
                # Loi mang: giu du lieu CU (neu co) hon la xoa trang danh sach
                # dang dung duoc — nhung KHONG bao gio bia them model moi.
                # KHONG co cache cu -> nem loi that de goi bi phan biet duoc
                # "khong kha dung" voi "kha dung nhung dang rong" (yeu cau
                # ADDENDUM #7: hien trang thai unavailable/degraded rieng).
                if self._cache is not None:
                    return self._cache
                raise
            self._cache = moi
            self._cached_at = now
            self._loi_gan_nhat = ""
            return moi

    def loi_gan_nhat(self) -> str:
        with self._lock:
            return self._loi_gan_nhat

    def _fetch(self) -> List[CommunityImageModel]:
        client = self._client or httpx.Client(timeout=self._timeout, trust_env=False)
        try:
            resp = client.get(CATALOGUE_URL)
        except httpx.HTTPError as exc:
            raise CommunityCatalogueError(
                "Không lấy được danh sách model cộng đồng — Pollinations hiện "
                "không phản hồi."
            ) from exc
        finally:
            if self._client is None:
                client.close()

        if resp.status_code != 200:
            raise CommunityCatalogueError(
                f"Danh sách model cộng đồng tạm thời không khả dụng (mã "
                f"{resp.status_code})."
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise CommunityCatalogueError(
                "Phản hồi danh sách model cộng đồng không hợp lệ."
            ) from exc
        if not isinstance(data, list):
            raise CommunityCatalogueError(
                "Phản hồi danh sách model cộng đồng có định dạng không mong đợi."
            )
        return _loc_mien_phi(data)
