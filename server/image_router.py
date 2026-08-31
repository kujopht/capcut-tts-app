"""
Bo dinh tuyen (router) chon PROVIDER sinh anh bia phu hop cho mot yeu cau,
DOC LAP voi bat ky provider/GPU cu the nao (khong import beam/torch/
diffusers/httpx/PIL - xem test_image_router.py::TestImageRouterModuleIsProviderNeutral,
cung ky thuat AST voi
server/tests/test_character_identity.py::TestCharacterIdentityModuleIsProviderNeutral).

VI SAO CAN FILE NAY: hom nay chi co MOT provider sinh anh bia that (Beam
RTX4090, xem server/cover_pipeline.py::HttpImageCoverProvider goi
beam_apps/cover_illustrious_app.py) - nhung mission "Media AI Production
Foundation" (Track D) yeu cau nen tang SAN SANG cho tuong lai da-provider
(vd them mot GPU provider re/mien phi hon nhu Vast.ai, hoac mot chien luoc
sinh anh moi nhu character-LoRA) MA KHONG phai doi code goi (caller) moi
lan them provider - chi can them mot `ImageProviderProfile` moi vao danh
sach candidates truyen vao `ImageRouter.select_provider()`.

THIET KE CHINH SACH DINH TUYEN (tat dinh, khong ngau nhien, de test):
  1. Loc candidates: phai HO TRO capability yeu cau, phai DU VRAM, phai
     DANG SAN SANG (`is_available=True`). Khong con candidate nao qua
     buoc nay -> `NoCapableProviderError`.
  2. Neu `requirements.prefer_free_or_subsidized_compute` (mac dinh True,
     khop nguyen tac san xuat cua mission "Free/current development
     compute should be preferred now"): trong so con lai, UU TIEN nhom
     `is_free_or_subsidized=True` truoc - CHI xet nhom tra phi neu KHONG
     co candidate mien phi/duoc tro gia nao qua duoc buoc loc.
  3. Trong nhom da chon (mien phi hoac tra phi, tuy buoc 2), chon
     `cost_per_second_usd` THAP NHAT. Hoa (bang gia) -> giu thu tu xuat
     hien dau tien trong danh sach candidates (sort on dinh - khong dao
     lon danh sach dau vao).

KHONG CAN DOI CODE UNG DUNG DE DOI UU TIEN PROVIDER: toan bo chinh sach o
tren chi doc DU LIEU trong danh sach `candidates` truyen vao - them mot
`ImageProviderProfile` gia (vd "vast", is_free_or_subsidized=True) vao
danh sach la du de thay doi provider duoc chon, KHONG can sua
`ImageRouter`, khong can sua `select_provider()`, khong can sua bat ky
noi goi ham nay. Xem server/tests/test_image_router.py cho bang chung
that: cung mot loi goi `select_provider()`, hai danh sach candidates khac
nhau -> hai ket qua khac nhau.

FALLBACK SAU LOI TAM THOI: khong tu dong/an - mau ro rang, 2 buoc, do
caller kiem soat (xem `mark_provider_unavailable`'s own docstring).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class ImageGenerationCapability(str, Enum):
    """Cac chien luoc/kha nang sinh anh bia ma mot yeu cau co the can, va
    mot provider co the ho tro.

    PROMPT_ONLY va REFERENCE_CONDITIONED da hoat dong THAT hom nay (xem
    CoverPromptBuilder va reference-conditioning IP-Adapter trong
    beam_apps/cover_illustrious_app.py). CHARACTER_LORA la kha nang
    TUONG LAI - CHUA co provider/backend nao ho tro (chua train/tai LoRA
    nhan vat rieng nao, xem CharacterVisualIdentity.lora_reference_id's
    own docstring) - van la mot gia tri enum HOP LE (yeu cau mission:
    thiet ke "future-ready") de mot yeu cau co the KHAI BAO can no, va
    ImageRouter se raise NoCapableProviderError mot cach RO RANG (khong
    am tham ha cap xuong PROMPT_ONLY) khi khong co provider nao ho tro.
    """

    PROMPT_ONLY = "prompt_only"
    REFERENCE_CONDITIONED = "reference_conditioned"
    CHARACTER_LORA = "character_lora"


class LatencyClass(str, Enum):
    """Uoc luong do tre THO (khong phai giay chinh xac) - du de dinh
    tuyen/hien thi ky vong cho nguoi dung, khong can chinh xac giay vi thoi
    gian goi GPU scale-to-zero (Beam) bien thien manh theo cold-start.
    Chon Literal-nhu-enum (thay vi so giay uoc luong) vi ly do THAT: cac
    con so giay do duoc hom nay (xem scripts/beam_cover_benchmark.py) la
    KET QUA DO, khong phai tham so cau hinh on dinh de dua vao logic dinh
    tuyen - dinh tuyen theo "hang" (FAST/MEDIUM/SLOW) on dinh hon truoc
    bien dong do."""

    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"


@dataclass
class ImageGenerationRequirements:
    """Dau vao cho `ImageRouter.select_provider()` - mo ta MOT yeu cau sinh
    anh can gi, khong biet gi ve provider cu the se phuc vu no."""

    required_capability: ImageGenerationCapability
    reference_conditioning_needed: bool = False
    vram_requirement_gb: float = 0.0
    estimated_latency_class: LatencyClass = LatencyClass.MEDIUM
    estimated_cost_usd: float = 0.0
    #: Mac dinh True - khop nguyen tac san xuat cua mission: "Free/current
    #: development compute should be preferred now". Mot yeu cau co the
    #: tat no (vd uu tien do tre thap hon chi phi) bang cach dat False.
    prefer_free_or_subsidized_compute: bool = True


@dataclass
class ImageProviderProfile:
    """Mo ta MOT provider (+ cau hinh cu the, vd mot GPU/model nhat dinh
    cua provider do) co the lam gi - hoan toan la DU LIEU, khong goi bat
    ky API/SDK nao. `provider_name` la CHUOI THUAN (vd "beam") - KHONG
    phai mot import/class provider that (xem CoverProvider Protocol trong
    server/cover_pipeline.py cho lop goi HTTP that, tach biet khoi ho so
    dinh tuyen nay)."""

    provider_name: str
    supported_capabilities: List[ImageGenerationCapability] = field(
        default_factory=list)
    gpu_vram_gb: float = 0.0
    is_free_or_subsidized: bool = False
    #: Co the bi caller doi thanh False sau mot loi tam thoi that (xem
    #: `mark_provider_unavailable`) - KHONG phai truong tinh, la trang
    #: thai runtime don gian nhat co the co.
    is_available: bool = True
    cost_per_second_usd: float = 0.0


class NoCapableProviderError(Exception):
    """Khong co `ImageProviderProfile` nao trong danh sach candidates vua
    ho tro dung capability, vua du VRAM, vua dang san sang. Loi TYPED ro
    rang - caller khong duoc am tham ha cap sang mot capability khac (vd
    CHARACTER_LORA khong ai ho tro thi KHONG duoc lang le tra ve mot
    provider chi biet PROMPT_ONLY)."""


class ImageRouter:
    """Chinh sach dinh tuyen chon provider - xem docstring dau file cho
    toan bo 3 buoc va ly do "khong can doi code ung dung"."""

    def select_provider(
        self,
        requirements: ImageGenerationRequirements,
        candidates: List[ImageProviderProfile],
    ) -> ImageProviderProfile:
        eligible = [
            profile for profile in candidates
            if profile.is_available
            and profile.gpu_vram_gb >= requirements.vram_requirement_gb
            and requirements.required_capability in profile.supported_capabilities
        ]
        if not eligible:
            raise NoCapableProviderError(
                f"Khong co provider nao dang san sang, du VRAM "
                f"(>= {requirements.vram_requirement_gb} GB) va ho tro "
                f"capability {requirements.required_capability.value!r} "
                f"trong danh sach {len(candidates)} candidate(s)."
            )

        pool = eligible
        if requirements.prefer_free_or_subsidized_compute:
            free_pool = [p for p in eligible if p.is_free_or_subsidized]
            if free_pool:
                pool = free_pool

        # min() tren list la ON DINH (stable) - hoa gia thi giu candidate
        # xuat hien TRUOC trong danh sach dau vao, khong dao lon thu tu.
        return min(pool, key=lambda p: p.cost_per_second_usd)

    def mark_provider_unavailable(
        self,
        profile: ImageProviderProfile,
        providers: List[ImageProviderProfile],
    ) -> None:
        """Mau FALLBACK sau mot loi tam thoi - RO RANG, KHONG an/tu dong:

            try:
                image_bytes = call_provider(chosen)
            except TransientProviderError:
                router.mark_provider_unavailable(chosen, candidates)
                chosen = router.select_provider(requirements, candidates)
                image_bytes = call_provider(chosen)

        Sua `is_available` NGAY TREN doi tuong trong danh sach `providers`
        (so khop theo `provider_name` - khong dua vao identity doi tuong,
        vi mot caller co the xay danh sach candidates moi moi lan goi).
        Khong tu dong retry/goi lai provider - do la trach nhiem cua
        caller, foundation nay chi cung cap thao tac danh dau + chinh sach
        chon lai, giu luong xu ly de doc/de test."""
        for candidate in providers:
            if candidate.provider_name == profile.provider_name:
                candidate.is_available = False


#: Gia tri THAT, da CONG BO tu Beam cho RTX4090 on-demand - CUNG hang so
#: da dung trong scripts/beam_cover_benchmark.py, scripts/beam_cover_identity_proof.py,
#: scripts/beam_cover_reference_proof.py, scripts/beam_cover_refinement.py
#: (nguon: https://www.beam.cloud/pricing, doi chieu 2026-08-31) - KHONG
#: bia so moi, tai su dung DUNG con so da xac minh o noi khac trong repo.
BEAM_RTX4090_PER_SECOND_USD = 0.000191667

#: Ho so THAT DUY NHAT hom nay - Beam RTX4090 chay
#: beam_apps/cover_illustrious_app.py qua server/cover_pipeline.py::HttpImageCoverProvider.
#: Ho tro PROMPT_ONLY + REFERENCE_CONDITIONED (IP-Adapter, da hoat dong
#: that) - CHUA ho tro CHARACTER_LORA (chua train/tai LoRA nao, xem
#: CharacterVisualIdentity.lora_reference_id). `is_free_or_subsidized=False`
#: vi day la GPU tinh phi THAT theo giay (RTX4090 on-demand cua Beam),
#: khong phai bac free-tier - KHONG duoc doi thanh True chi vi la lua chon
#: hien tai.
BEAM_RTX4090_PROFILE = ImageProviderProfile(
    provider_name="beam",
    supported_capabilities=[
        ImageGenerationCapability.PROMPT_ONLY,
        ImageGenerationCapability.REFERENCE_CONDITIONED,
    ],
    gpu_vram_gb=24.0,
    is_free_or_subsidized=False,
    is_available=True,
    cost_per_second_usd=BEAM_RTX4090_PER_SECOND_USD,
)
