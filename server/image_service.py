"""
Tang dieu phoi Image Studio V1 — ket noi vi (image_wallet_store), provider
(image_provider_registry), gia (image_pricing), bao ve ngan sach
(image_spending_guard) va BYOP (image_byop_service) thanh MOT luong duy nhat
cho tung che do, dung UNG nguyen van PHASE 5:

    estimate -> verify balance -> reserve -> goi Pollinations
        -> thanh cong: settle
        -> provider that bai: refund (giai phong TRUOC khi goi provider dung
           `giai_phong`, provider that bai SAU khi goi dung `hoan_tien`)

`generation_id` == `idempotency_key` do CALLER truyen vao (vd hash cua yeu
cau hoac mot UUID phia client) — don gian hoa viec chan trung: khong can
tra cuu hai chieu, chi mot khoa DUY NHAT xuyen suot vi + reservation.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from server.image_byop_service import ByopError, PollinationsByopService
from server.image_community_catalogue import (
    CommunityCatalogueCache,
    CommunityCatalogueError,
    CommunityImageModel,
)
from server.image_domain import GenerationMode, GenerationReservation, ImageModelInfo
from server.image_pricing import (
    PricingConfig,
    PRICING_SNAPSHOT_VERSION,
    model_allowlist,
    uoc_tinh_chi_phi_micro,
    uoc_tinh_chi_phi_provider_usd,
)
from server.image_provider_registry import (
    GeneratedImage,
    ImageProviderError,
    QuickFreeImageProvider,
    SharedPremiumImageProvider,
    aspect_ratio_to_dimensions,
    seed_ngau_nhien,
)
from server.image_spending_guard import SharedPremiumSpendingGuard
from server.image_wallet_store import MockWalletStore


class UnknownOrDisabledModel(ImageProviderError):
    pass


class ByopNotConnected(ImageProviderError):
    pass


class GenerationAlreadyProcessed(ImageProviderError):
    """`idempotency_key` da duoc xu ly xong (settled/refunded) TRUOC do va anh
    tam thoi (xem `_CACHE_ANH_TAM_MAX`) da bi don — client nen kiem tra trang
    thai qua generation_id thay vi coi day la mot loi that."""


class CommunityModelNoLongerFree(ImageProviderError):
    """Model duoc yeu cau KHONG (con) nam trong danh sach Cong Free HIEN TAI —
    ADDENDUM yeu cau tuyet doi: 'Never silently fall back from a free
    community model to a paid model.' Loi nay CHAN generation lai, KHONG tu
    dong chuyen sang Shared Premium/tru Fanfic Credit."""


#: So luong anh Shared Premium GAN NHAT giu tam trong tien trinh de MOT request
#: bi client goi lai (vd het timeout HTTP, bam nut hai lan) trong luc van
#: dang xu ly/vua xong van nhan lai DUNG anh do thay vi mat trang. KHONG phai
#: luu tru vinh vien (xem PHASE 9 — chi anh nguoi dung chu dong 'Luu' moi qua
#: storage that).
_CACHE_ANH_TAM_MAX = 256


@dataclass(frozen=True)
class SharedPremiumResult:
    image: GeneratedImage
    reservation: GenerationReservation


class ImageStudioService:
    def __init__(
        self, *,
        wallet_store: MockWalletStore,
        quick_free_provider: QuickFreeImageProvider,
        shared_premium_provider: Optional[SharedPremiumImageProvider],
        byop_service: PollinationsByopService,
        spending_guard: SharedPremiumSpendingGuard,
        pricing: Optional[PricingConfig] = None,
        byop_http_client=None,
        community_catalogue: Optional[CommunityCatalogueCache] = None,
    ) -> None:
        self._wallet = wallet_store
        self._quick_free = quick_free_provider
        self._shared_premium = shared_premium_provider
        self._byop = byop_service
        self._guard = spending_guard
        self._pricing = pricing or PricingConfig.tu_moi_truong()
        self._anh_tam: "OrderedDict[str, GeneratedImage]" = OrderedDict()
        #: CHI dung de tiem `httpx.MockTransport` trong test — production
        #: luon None (provider BYOP tu tao client that cho tung request).
        self._byop_http_client = byop_http_client
        self._community = community_catalogue or CommunityCatalogueCache()

    # ============================================================ catalogue

    def catalogue(self) -> list:
        return [m for m in model_allowlist().values() if m.enabled]

    def _model_hop_le(self, model_id: str) -> ImageModelInfo:
        allowlist = model_allowlist()
        model = allowlist.get(model_id)
        if model is None or not model.enabled:
            raise UnknownOrDisabledModel(
                f"Model {model_id!r} không khả dụng cho Shared Premium."
            )
        return model

    def uoc_tinh_shared_premium(self, *, model_id: str, quality: str = "standard") -> int:
        model = self._model_hop_le(model_id)
        return uoc_tinh_chi_phi_micro(model, quality=quality, pricing=self._pricing)

    # ============================================================ Quick Free

    def sinh_anh_quick_free(
        self, *, prompt: str, aspect_ratio: str, client_ip: str,
    ) -> GeneratedImage:
        """KHONG cham vi, KHONG cham spending guard — hoan toan mien phi va
        doc lap. Loi provider truyen thang len (khong am tham fallback sang
        Shared Premium — nguoi dung khong yeu cau tra tien)."""
        return self._quick_free.sinh_anh(
            prompt=prompt, aspect_ratio_seed=seed_ngau_nhien(), client_ip=client_ip,
        )

    # ======================================================= Shared Premium

    def sinh_anh_shared_premium(
        self, *, user_id: str, prompt: str, negative_prompt: str, model_id: str,
        aspect_ratio: str, quality: str, idempotency_key: str,
    ) -> SharedPremiumResult:
        if self._shared_premium is None:
            raise ImageProviderError(
                "Shared Premium chưa được cấu hình (thiếu POLLINATIONS_API_KEY)."
            )
        model = self._model_hop_le(model_id)
        estimated_micro = uoc_tinh_chi_phi_micro(model, quality=quality, pricing=self._pricing)
        generation_id = idempotency_key

        # 1. Bao ve ngan sach TRUOC KHI giu vi — khong giu tien cua nguoi
        #    dung neu Shared Premium da bi khoa toan cuc.
        self._guard.bat_dau_request()
        try:
            # 2. Giu vi (co the nem InsufficientBalance/DuplicateReservation).
            reservation = self._wallet.dat_cho(
                user_id=user_id, generation_id=generation_id,
                mode=GenerationMode.SHARED_PREMIUM,
                provider_id=self._shared_premium.provider_id, model=model_id,
                estimated_cost_micro=estimated_micro, idempotency_key=idempotency_key,
                pricing_snapshot_version=PRICING_SNAPSHOT_VERSION,
            )
        except Exception:
            self._guard.ket_thuc_request(actual_cost_usd=0.0)
            raise

        # Da tung dat_cho voi CUNG idempotency_key -> tra ve reservation cu
        # (co the DA settled/refunded o mot request truoc) — khong goi lai
        # provider mot lan nua.
        if reservation.status.value != "reserved":
            self._guard.ket_thuc_request(actual_cost_usd=0.0)
            anh_cu = self._anh_tam.get(generation_id)
            if anh_cu is None:
                raise GenerationAlreadyProcessed(
                    f"Yêu cầu {generation_id!r} đã xử lý xong trước đó "
                    f"(trạng thái: {reservation.status.value}) nhưng ảnh tạm "
                    "đã bị dọn khỏi bộ nhớ — vui lòng tạo lại nếu cần ảnh mới."
                )
            return SharedPremiumResult(image=anh_cu, reservation=reservation)

        w, h = aspect_ratio_to_dimensions(aspect_ratio)
        try:
            image = self._shared_premium.sinh_anh(
                prompt=prompt, negative_prompt=negative_prompt, model=model_id,
                width=w, height=h, quality=quality,
            )
        except Exception as exc:
            self._wallet.hoan_tien(generation_id, ly_do=str(exc))
            self._guard.ket_thuc_request(actual_cost_usd=0.0)
            raise
        else:
            settled = self._wallet.tat_toan(generation_id)
            self._guard.ket_thuc_request(
                actual_cost_usd=uoc_tinh_chi_phi_provider_usd(model_id))
            self._luu_anh_tam(generation_id, image)
            return SharedPremiumResult(image=image, reservation=settled)

    # ============================================================ Cong Free

    def catalogue_cong_dong(self) -> dict:
        """Danh sach model cong dong Pollinations bao gia 0 pollen NGAY BAY
        GIO — dynamic, KHONG hard-code (ADDENDUM #12). `available=False`
        nghia la KHONG lay duoc danh sach (loi mang/API), khac voi danh sach
        RONG hop le (lay duoc, nhung dang khong co model nao dat dieu kien)."""
        try:
            models = self._community.lay_danh_sach()
        except CommunityCatalogueError as exc:
            return {"available": False, "models": [], "error": str(exc)}
        return {"available": True, "models": models, "error": ""}

    def sinh_anh_cong_dong(
        self, *, user_id: str, prompt: str, negative_prompt: str, model_id: str,
        aspect_ratio: str, quality: str, idempotency_key: str,
    ) -> SharedPremiumResult:
        """Sinh anh qua mot model CONG DONG dang mien phi THAT SU (gia 0).

        VAN can Unified API co xac thuc server-side (ADDENDUM: 'Unified/
        community generation may still require Pollinations authentication')
        — KHAC voi Quick Free (an danh hoan toan). KHONG tru Fanfic Credit
        (chi phi uoc tinh la 0), nhung VAN ghi mot ban ghi reservation/settle
        0-dong de co dau vet kiem toan nhat quan voi Shared Premium.

        Kiem tra LAI danh sach cong dong TRUOC MOI lan goi (khong dung cache
        cu qua han) — model co the da bi ru khoi danh sach mien phi giua hai
        lan nguoi dung bam nut; ADDENDUM: 'Never silently fall back from a
        free community model to a paid model.' Loi o day CHAN han, khong tu
        chuyen sang Shared Premium.
        """
        if self._shared_premium is None:
            raise ImageProviderError(
                "Cộng Free chưa sẵn sàng (thiếu POLLINATIONS_API_KEY server-side)."
            )
        trang_thai = self.catalogue_cong_dong()
        if not trang_thai["available"]:
            raise CommunityModelNoLongerFree(
                "Không lấy được danh sách model Cộng Free hiện tại — vui lòng "
                "thử lại sau, không tự động chuyển sang Fanfic Credits."
            )
        con_mien_phi = any(m.model_id == model_id for m in trang_thai["models"])
        if not con_mien_phi:
            raise CommunityModelNoLongerFree(
                f"Model {model_id!r} không còn trong danh sách Cộng Free hiện "
                "tại — vui lòng chọn model khác hoặc dùng Fanfic Credits/My "
                "Pollinations."
            )

        generation_id = idempotency_key
        reservation = self._wallet.dat_cho(
            user_id=user_id, generation_id=generation_id,
            mode=GenerationMode.COMMUNITY_FREE,
            provider_id="pollinations_community_free", model=model_id,
            estimated_cost_micro=0, idempotency_key=idempotency_key,
            pricing_snapshot_version=PRICING_SNAPSHOT_VERSION,
        )
        if reservation.status.value != "reserved":
            anh_cu = self._anh_tam.get(generation_id)
            if anh_cu is None:
                raise GenerationAlreadyProcessed(
                    f"Yêu cầu {generation_id!r} đã xử lý xong trước đó."
                )
            return SharedPremiumResult(image=anh_cu, reservation=reservation)

        w, h = aspect_ratio_to_dimensions(aspect_ratio)
        try:
            image = self._shared_premium.sinh_anh(
                prompt=prompt, negative_prompt=negative_prompt, model=model_id,
                width=w, height=h, quality=quality,
            )
        except Exception as exc:
            self._wallet.hoan_tien(generation_id, ly_do=str(exc))
            raise
        else:
            settled = self._wallet.tat_toan(generation_id, actual_cost_micro=0)
            self._luu_anh_tam(generation_id, image)
            return SharedPremiumResult(image=image, reservation=settled)

    def _luu_anh_tam(self, generation_id: str, image: GeneratedImage) -> None:
        self._anh_tam[generation_id] = image
        self._anh_tam.move_to_end(generation_id)
        while len(self._anh_tam) > _CACHE_ANH_TAM_MAX:
            self._anh_tam.popitem(last=False)

    # ==================================================================== BYOP

    def sinh_anh_byop(
        self, *, user_id: str, prompt: str, negative_prompt: str, model_id: str,
        aspect_ratio: str, quality: str,
    ) -> GeneratedImage:
        """Dung Pollen CA NHAN cua nguoi dung — KHONG BAO GIO cham vi Fanfic
        Credit, KHONG BAO GIO tu dong fallback sang khoa dung chung khi loi
        (yeu cau bat buoc PHASE 4C)."""
        connection = self._byop.trang_thai(user_id)
        if connection is None or not connection.active:
            raise ByopNotConnected(
                "Chưa kết nối Pollinations cá nhân — hãy kết nối ở mục "
                "'My Pollinations' trước."
            )
        try:
            access_token = self._byop.giai_ma_access_token(connection)
        except ByopError as exc:
            raise ByopNotConnected(str(exc)) from exc

        w, h = aspect_ratio_to_dimensions(aspect_ratio)
        # Provider RIENG cho lan goi nay, dung token CA NHAN — khong tai su
        # dung instance Shared Premium (tranh nham lan credential).
        byop_provider = SharedPremiumImageProvider(
            api_key=access_token, client=self._byop_http_client)
        return byop_provider.sinh_anh(
            prompt=prompt, negative_prompt=negative_prompt, model=model_id,
            width=w, height=h, quality=quality,
        )
