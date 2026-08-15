"""
Gia Fanfic Credit cho Image Studio V1 (overnight build) — PHASE 8.

NGUYEN TAC: chi phi PROVIDER (uoc tinh Pollinations tinh phi bao nhieu) va gia
NGUOI DUNG THAY (bao nhieu Fanfic Credit) la HAI SO TACH BIET. Markup/quy doi
la cau hinh, khong hard-code "model X luon gia Y" trong logic nghiep vu.

Moi generation ghi lai `pricing_snapshot_version` dung LUC UOC TINH — doi
markup sau nay KHONG duoc lam thay doi gia tri cua giao dich DA hoan tat (xem
`server/image_domain.py::GenerationReservation.pricing_snapshot_version`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict

from server.image_domain import MICRO_PER_CREDIT, ImageModelInfo

#: Tang phien ban nay MOI KHI thay doi cong thuc/markup — khong sua gia tri
#: cu, chi doi mac dinh cho generation MOI.
PRICING_SNAPSHOT_VERSION = "img-pricing-v1"

#: He so nhan theo kich thuoc/chat luong — 1024x1024 standard = 1.0.
QUALITY_MULTIPLIER: Dict[str, float] = {
    "standard": 1.0,
    "hd": 1.6,
}

#: Danh sach TRANG (allowlist) ban dau cho Shared Premium — PHASE 4B. CHI liet
#: ke model DA XAC NHAN Pollinations Unified API tra ve va hieu ro nang luc
#: (khong suy dien tu ten). estimated_credit_cost la gia HIEN THI ban dau, co
#: the dieu chinh qua bien moi truong IMAGE_MARKUP_MULTIPLIER ben duoi — day
#: KHONG phai chi phi provider that (Phase 8 yeu cau tach biet), chi la con so
#: khoi dong hop ly cho MVP, se thay bang catalogue/pricing that cua
#: Pollinations khi co the fetch dinh ky (xem `image_provider_registry.py`
#: docstring `PollinationsSharedPremiumProvider.lay_catalogue`).
DEFAULT_MODEL_ALLOWLIST: Dict[str, ImageModelInfo] = {
    "flux": ImageModelInfo(
        model_id="flux", display_name="Flux",
        estimated_credit_cost=2.0, provider_reports_paid_only=True,
    ),
    "zimage": ImageModelInfo(
        model_id="zimage", display_name="Z-Image",
        estimated_credit_cost=2.0, provider_reports_paid_only=True,
    ),
    "gpt-image-2": ImageModelInfo(
        model_id="gpt-image-2", display_name="GPT Image 2",
        quality_levels=("standard", "hd"),
        estimated_credit_cost=6.0, provider_reports_paid_only=True,
    ),
    "gptimage": ImageModelInfo(
        model_id="gptimage", display_name="GPT Image",
        quality_levels=("standard", "hd"),
        estimated_credit_cost=5.0, provider_reports_paid_only=True,
    ),
    "gptimage-large": ImageModelInfo(
        model_id="gptimage-large", display_name="GPT Image (Large)",
        quality_levels=("standard", "hd"),
        estimated_credit_cost=9.0, provider_reports_paid_only=True,
    ),
    "nanobanana-pro": ImageModelInfo(
        model_id="nanobanana-pro", display_name="Nano Banana Pro",
        estimated_credit_cost=4.0, provider_reports_paid_only=True,
    ),
}

#: Muc thap nhat co the tinh phi cho MOT lan sinh anh, ke ca sau markup/khuyen
#: mai — tranh gia tri lam tron ve 0 credit ma van goi provider tra phi that.
MINIMUM_CHARGE_MICRO = 1 * MICRO_PER_CREDIT // 10  # 0.10 credit


@dataclass(frozen=True)
class PricingConfig:
    markup_multiplier: float = 1.0
    minimum_charge_micro: int = MINIMUM_CHARGE_MICRO

    @classmethod
    def tu_moi_truong(cls) -> "PricingConfig":
        raw = (os.environ.get("IMAGE_MARKUP_MULTIPLIER") or "").strip()
        try:
            markup = float(raw) if raw else 1.0
        except ValueError:
            markup = 1.0
        if markup <= 0:
            markup = 1.0
        return cls(markup_multiplier=markup)


def uoc_tinh_chi_phi_micro(
    model: ImageModelInfo, *, quality: str = "standard",
    pricing: PricingConfig = PricingConfig(),
) -> int:
    """Tra ve chi phi HIEN THI (micro-credit) cho MOT lan sinh — theo he so
    chat luong va markup cau hinh, khong bao gio thap hon minimum_charge."""
    he_so_chat_luong = QUALITY_MULTIPLIER.get(quality, 1.0)
    co_ban = model.estimated_credit_cost * MICRO_PER_CREDIT
    tong = round(co_ban * he_so_chat_luong * pricing.markup_multiplier)
    return max(tong, pricing.minimum_charge_micro)


def model_allowlist() -> Dict[str, ImageModelInfo]:
    """Danh sach model dang bat — cho phep tat TAM THOI qua
    `IMAGE_DISABLED_MODELS` (ngan cach dau phay) ma khong can sua ma nguon,
    dung cho cong tac quan tri PHASE 11/PHASE 7 (kill-switch theo tung model)."""
    disabled = {
        m.strip() for m in (os.environ.get("IMAGE_DISABLED_MODELS") or "").split(",")
        if m.strip()
    }
    return {
        model_id: (info if model_id not in disabled else _tat(info))
        for model_id, info in DEFAULT_MODEL_ALLOWLIST.items()
    }


def _tat(info: ImageModelInfo) -> ImageModelInfo:
    return ImageModelInfo(**{**info.__dict__, "enabled": False})


#: UOC TINH tho chi phi THAT (USD) Pollinations tinh cho MOT lan sinh, CHI
#: dung noi bo de tinh ngan sach chia se (PHASE 7 spending guard) — KHONG
#: BAO GIO hien thi cho nguoi dung (ho chi thay gia Fanfic Credit). Day la
#: con so KHOI DONG hop ly, CAN hieu chinh lai theo hoa don Pollinations
#: that khi site-owner bat Shared Premium that (xem docs/reports).
PROVIDER_COST_USD_ESTIMATE: Dict[str, float] = {
    "flux": 0.003,
    "zimage": 0.003,
    "gpt-image-2": 0.02,
    "gptimage": 0.015,
    "gptimage-large": 0.03,
    "nanobanana-pro": 0.01,
}
DEFAULT_PROVIDER_COST_USD_ESTIMATE = 0.02


def uoc_tinh_chi_phi_provider_usd(model_id: str) -> float:
    return PROVIDER_COST_USD_ESTIMATE.get(model_id, DEFAULT_PROVIDER_COST_USD_ESTIMATE)
