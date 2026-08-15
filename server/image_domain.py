"""
Kieu du lieu cho Image Studio V1 (fanfic-image-studio, overnight build).

Theo dung khuon cua `server/domain.py` + `server/gamification_domain.py`:
dataclass thuan, khong phu thuoc Appwrite/FastAPI, dung chung cho ca
Mock/Appwrite store va cho test.

DON VI TIEN: moi so du/gia deu la SO NGUYEN, don vi nho nhat (`MICRO_PER_CREDIT`
micro = 1 Fanfic Credit hien thi). KHONG dung float cho tien — sai so lam tron
cua float se lech dan qua hang nghin giao dich.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from server.domain import new_id, now_iso

#: 1 Fanfic Credit hien thi = 100 micro-credit noi bo. Chia nho de sau nay co
#: the tinh gia le (vd 0.05 credit) ma van la so nguyen ben trong.
MICRO_PER_CREDIT = 100


def credits_to_micro(credits: float) -> int:
    """Chi dung o BIEN he thong (nhap gia tri cau hinh dang so thap phan tu
    .env) — KHONG dung trong duong di tinh tien noi bo, o do luon la int."""
    return round(credits * MICRO_PER_CREDIT)


def micro_to_display(micro: int) -> str:
    """Chuoi hien thi 2 chu so thap phan, vd 125 -> '1.25'."""
    nguyen, le = divmod(abs(micro), MICRO_PER_CREDIT)
    dau = "-" if micro < 0 else ""
    return f"{dau}{nguyen}.{le:02d}"


class GenerationMode(str, Enum):
    """Ba che do sinh anh — xem PHASE 4 cua dac ta overnight."""

    QUICK_FREE = "quick_free"
    SHARED_PREMIUM = "shared_premium"
    BYOP = "byop"
    #: Model CONG DONG Pollinations bao gia dung 0 pollen — xem ADDENDUM
    #: "FREE POLLINATIONS COMMUNITY IMAGE MODELS". KHAC voi QUICK_FREE: van
    #: can biet dung model nao va van goi Unified API co xac thuc server-side
    #: (xem `image_community_catalogue.py` va `ImageStudioService.sinh_anh_cong_dong`).
    COMMUNITY_FREE = "community_free"


class GenerationStatus(str, Enum):
    PENDING = "pending"
    RESERVED = "reserved"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class LedgerEntryType(str, Enum):
    """Ngu nghia SO CAI (khong phai mot con so bi tru truc tiep)."""

    TOP_UP = "top_up"
    RESERVE = "reserve"
    SETTLE = "settle"
    RELEASE = "release"  # hoan tra do KHONG bao gio goi provider (vd het han muc)
    REFUND = "refund"    # hoan tra do provider that bai SAU khi da goi
    PROMOTIONAL = "promotional"


@dataclass(frozen=True)
class WalletBalance:
    user_id: str
    #: So du KHA DUNG (da tru phan dang RESERVED cho cac generation chua settle).
    available_micro: int = 0
    #: Tong dang bi giu cho cac reservation con hieu luc — hien thi rieng de
    #: nguoi dung khong thay "mat tien" oan khi generation dang chay.
    reserved_micro: int = 0
    updated_at: str = field(default_factory=now_iso)

    @property
    def total_micro(self) -> int:
        return self.available_micro + self.reserved_micro


@dataclass(frozen=True)
class WalletTransaction:
    """MOT dong so cai — bat bien sau khi ghi (khong UPDATE, chi INSERT).

    `idempotency_key` la diem chan trung: kho PHAI tu choi ghi hai ban ghi
    cung khoa nay (xem `MockWalletStore.ghi_giao_dich`), giong het co che
    `record_xp_event`/`entry_id` cua gamification.
    """

    transaction_id: str
    user_id: str
    generation_id: str
    entry_type: LedgerEntryType
    #: Am = tru so du kha dung (RESERVE), duong = tra lai/nap them.
    amount_micro: int
    idempotency_key: str
    created_at: str = field(default_factory=now_iso)
    note: str = ""

    @staticmethod
    def moi(
        *,
        user_id: str,
        generation_id: str,
        entry_type: LedgerEntryType,
        amount_micro: int,
        idempotency_key: str,
        note: str = "",
    ) -> "WalletTransaction":
        return WalletTransaction(
            transaction_id=new_id("wtx"),
            user_id=user_id,
            generation_id=generation_id,
            entry_type=entry_type,
            amount_micro=amount_micro,
            idempotency_key=idempotency_key,
            note=note,
        )


@dataclass(frozen=True)
class GenerationReservation:
    """Trang thai giu cho MOT lan sinh anh — vong doi:

        estimate -> reserve (RESERVED) -> goi provider
            -> thanh cong: settle (SUCCEEDED)
            -> provider loi: refund (REFUNDED)
    """

    generation_id: str
    user_id: str
    mode: GenerationMode
    provider_id: str
    model: str
    estimated_cost_micro: int
    status: GenerationStatus
    idempotency_key: str
    #: Chi dien khi status == SUCCEEDED va provider tra chi phi that.
    actual_cost_micro: Optional[int] = None
    #: Phien ban bang gia dung luc uoc tinh — xem `server/image_pricing.py`.
    pricing_snapshot_version: str = ""
    created_at: str = field(default_factory=now_iso)
    settled_at: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class ImageModelInfo:
    """Mot dong trong catalogue model — hien thi cho nguoi dung TRUOC khi
    sinh anh, KHONG bao gio tu nhan mien phi chi vi provider bao `paidOnly=false`
    (xem PHASE 8: chi phi provider tach BIET voi gia hien thi)."""

    model_id: str
    display_name: str
    supports_text_to_image: bool = True
    supports_image_edit: bool = False
    quality_levels: tuple = ("standard",)
    #: Uoc tinh chi phi Fanfic Credit HIEN THI cho anh 1024x1024 quality tieu
    #: chuan — cac kich thuoc/quality khac tinh theo he so trong image_pricing.py.
    estimated_credit_cost: float = 0.0
    #: Provider co goi la mien phi hay khong (metadata THO, khong phai ket luan
    #: "mien phi that" — xem canh bao PHASE 8).
    provider_reports_paid_only: bool = True
    enabled: bool = True


@dataclass(frozen=True)
class PollinationsConnection:
    """Ket noi BYOP (Bring-Your-Own-Pollinations) cua MOT nguoi dung.

    `encrypted_access_token`/`encrypted_refresh_token` dung dinh dang cua
    `server/translation_byok_crypto.py::ByokCrypto` (AAD rang buoc theo
    user_id + provider_id="pollinations_byop") — xem `image_byop_crypto.py`.
    """

    user_id: str
    provider_id: str = "pollinations_byop"
    encrypted_access_token: str = ""
    encrypted_refresh_token: str = ""
    scope: str = ""
    #: ISO 8601 — token het han luc nao (uoc tinh tu `expires_in` OAuth tra ve).
    expires_at: str = ""
    #: Ngan sach nguoi dung TU CHON cho lan ket noi nay — chi de hien thi/canh
    #: bao phia Fanfic World, KHONG phai gioi han that (Pollinations tu quan ly
    #: Pollen cua ho).
    user_budget_micro: int = 0
    connected_at: str = field(default_factory=now_iso)
    revoked_at: str = ""

    @property
    def active(self) -> bool:
        return bool(self.encrypted_access_token) and not self.revoked_at


@dataclass(frozen=True)
class SavedImage:
    """MOT anh nguoi dung chon 'Luu' — CHI anh da luu moi qua storage that
    (xem PHASE 9: khong luu moi ung vien tam)."""

    image_id: str
    owner_user_id: str
    generation_id: str
    prompt: str
    negative_prompt: str
    model: str
    mode: GenerationMode
    aspect_ratio: str
    storage_key: str
    created_at: str = field(default_factory=now_iso)
    #: Nhan an toan tho (vd tu response header/metadata cua provider, neu co) —
    #: khong tu suy dien them.
    safety_status: str = "unknown"
