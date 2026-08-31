"""
Pure, beam-SDK-independent helper logic for cover_illustrious_app.py.

Split out so this logic can be real-unit-tested: `beam`/`torch`/`diffusers`
are remote-deploy-only dependencies (see cover_illustrious_app.py's own
docstring) and are NOT installed in this repo's own venv, so any module
that imports them at top level cannot be imported locally at all, let
alone tested. This file imports NONE of those three at module level.

PIL/Pillow is ALSO imported LAZILY (inside build_left_right_masks()
itself, not here) - real fix for a real bug: `beam deploy
beam_apps/cover_illustrious_app.py:generate` failed BEFORE reaching the
remote container build, at a module-level `from PIL import Image,
ImageDraw` that used to live here. Root cause: `beam deploy`'s
DISCOVERY step imports this file locally (in whatever environment runs
the `beam` CLI, e.g. a bare Cloud Shell python3) to introspect the
`@endpoint`-decorated function - a completely separate environment from
the REMOTE container that `Image().add_python_packages([...])` builds in
cover_illustrious_app.py. That local discovery environment has never
been guaranteed to have Pillow installed (it runs no inference), so the
module-level import broke deploy discovery entirely, before any GPU
container was even built. Pillow genuinely IS installed in THIS repo's
own venv (desktop app dependency) and is ALSO an explicit remote
container package (see cover_illustrious_app.py's `Image().add_python_packages`
list) - so lazy-importing it here costs nothing on either side, it only
removes the assumption that the LOCAL DEPLOY-DISCOVERY environment has it.
"""
from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from PIL import Image as PILImageModule

#: Ban goc chi co cac tag chat luong chung. Them cac tag chong "bia dong
#: nguoi" sau khi ban Re:Zero dau tien thuc te tro thanh poster ensemble
#: dong duc/nhan vat trung lap - khong dung lam bia san xuat duoc (xem
#: CoverPromptBuilder's docstring trong server/cover_pipeline.py). Them
#: LAN 2 (mission "Final IP-Adapter Regional Composition") sau mot proof
#: that (v10) that bai bo cuc theo dung 3 kieu: mat/dau nhan vat chinh bi
#: cat xen, nhan vat phu quay lung/khong thay mat, va mot glyph/artifact
#: giong chu viet lon xuat hien khong mong muon - moi kieu duoc them tag
#: rieng thay vi chi dua vao cac tag chung da co ("cropped", "text").
DEFAULT_NEGATIVE_PROMPT = (
    "lowres, bad anatomy, bad hands, text, error, missing fingers, "
    "extra digit, fewer digits, cropped, worst quality, low quality, "
    "normal quality, jpeg artifacts, signature, watermark, blurry, "
    "crowd, group, ensemble cast, extra person, background character, "
    "duplicate character, cloned face, multiple girls, multiple boys, "
    "collage, character sheet, "
    "third person, cropped face, cut-off head, back facing viewer, "
    "rear view, letters, symbols, logo"
)


def resolve_negative_prompt(negative_prompt: str) -> str:
    """Neu caller khong truyen negative_prompt (chuoi rong), dung mac dinh."""
    return negative_prompt or DEFAULT_NEGATIVE_PROMPT


def build_response_payload(
    png_bytes: bytes,
    *,
    model_load_seconds: float,
    inference_seconds: float,
    width: int,
    height: int,
    seed: int = -1,
) -> dict:
    """
    Lap rap dung response contract cua endpoint (xem
    server/cover_pipeline.py::HttpImageCoverProvider._call_simple, doc du
    lieu {"image_base64": ...} tu day).

    `model_load_seconds` la thoi gian load model DUY NHAT MOT LAN (tu
    on_start, xem load_pipeline() trong cover_illustrious_app.py) - moi
    request tren CUNG mot container se bao cung gia tri nay, KHONG phai 0,
    vi day la so lieu that cua lan load that su, khong phai "khong load
    lai" bi bao sai thanh 0.

    `seed` la seed THAT SU duoc dung de sinh anh (-1 nghia la khong duoc
    yeu cau seed cu the, model tu chon ngau nhien) - tra ve de caller ghi
    lai, phuc vu so sanh nhieu candidate (xem
    scripts/beam_cover_refinement.py).
    """
    return {
        "image_base64": base64.b64encode(png_bytes).decode("ascii"),
        "model_load_seconds": round(model_load_seconds, 3),
        "inference_seconds": round(inference_seconds, 3),
        "width": width,
        "height": height,
        "size_bytes": len(png_bytes),
        "seed": seed,
    }


#: Real bug fix: h94/IP-Adapter's `load_ip_adapter(subfolder="sdxl_models",
#: ...)` default `image_encoder_folder="image_encoder"` is JOINED with
#: `subfolder`, silently resolving to "sdxl_models/image_encoder" - that
#: is OpenCLIP ViT-bigG (hidden_size=1664), NOT the ViT-H encoder
#: (hidden_size=1280) the "*_vit-h" checkpoint actually needs. Real
#: evidence: RuntimeError "mat1 and mat2 shapes cannot be multiplied
#: (1028x1664 and 1280x1280)" on a real Beam GPU call. The OFFICIAL
#: diffusers IP-Adapter guide's own "Model variants" example loads the
#: correct encoder from this TOP-LEVEL path instead (confirmed via
#: docs.huggingface.co/diffusers/using-diffusers/ip_adapter, fetched
#: 2026-08-31/09-01 - not assumed).
IP_ADAPTER_IMAGE_ENCODER_SUBFOLDER = "models/image_encoder"
#: ViT-H/14's real hidden_size (LAION OpenCLIP) - what the "*_vit-h"
#: IP-Adapter checkpoint's cross-attention weights actually expect.
IP_ADAPTER_EXPECTED_HIDDEN_SIZE = 1280


class IPAdapterEncoderMismatchError(Exception):
    """Loaded IP-Adapter image encoder does not match what the selected
    checkpoint expects - raised at on_start (container startup) instead
    of surfacing as a cryptic mid-inference matmul RuntimeError."""


def assert_ip_adapter_encoder_compatible(hidden_size: int, weight_name: str) -> None:
    """Real regression guard for a real incident (see
    IP_ADAPTER_IMAGE_ENCODER_SUBFOLDER's own docstring for the full
    citation). Raises `IPAdapterEncoderMismatchError` with an actionable
    message if the checkpoint/encoder pairing is wrong; does nothing if
    it's correct. Only understands "*_vit-h" checkpoints today - any
    other checkpoint name is rejected rather than silently assumed
    compatible, since compatibility hasn't been verified for it."""
    if "vit-h" not in weight_name.lower():
        raise IPAdapterEncoderMismatchError(
            f"IP-Adapter checkpoint {weight_name!r} is not a recognized "
            f"*_vit-h variant, but the image encoder explicitly loaded "
            f"here is specifically the ViT-H one "
            f"(hidden_size={IP_ADAPTER_EXPECTED_HIDDEN_SIZE}) - "
            f"checkpoint/encoder pairing is unverified for this name.")
    if hidden_size != IP_ADAPTER_EXPECTED_HIDDEN_SIZE:
        raise IPAdapterEncoderMismatchError(
            f"IP-Adapter image encoder hidden_size mismatch: got "
            f"{hidden_size}, expected {IP_ADAPTER_EXPECTED_HIDDEN_SIZE} "
            f"(ViT-H) for checkpoint {weight_name!r}. Real prior incident: "
            f"RuntimeError 'mat1 and mat2 shapes cannot be multiplied "
            f"(1028x1664 and 1280x1280)' - hidden_size=1664 is OpenCLIP "
            f"ViT-bigG, loaded from the WRONG subfolder "
            f"('sdxl_models/image_encoder' instead of "
            f"{IP_ADAPTER_IMAGE_ENCODER_SUBFOLDER!r}).")


class DeviceMismatchError(Exception):
    """A component required for reference-conditioned inference ended up
    on the wrong torch device (e.g. CPU while the rest of the pipeline is
    on CUDA) - raised at on_start (container startup) instead of
    surfacing as a cryptic mid-inference RuntimeError."""


def assert_component_on_cuda(component_name: str, device_str: str) -> None:
    """Real regression guard for a real incident: RuntimeError "Expected
    all tensors to be on the same device, but got index is on cpu,
    different from other tensors on cuda:0". Root cause: the explicitly-
    loaded IP-Adapter image encoder (added to fix the earlier ViT-bigG/
    ViT-H mismatch) was constructed via `.from_pretrained()` but never
    moved to CUDA, while the REST of the pipeline's tensors (shared from
    the base pipe, already `.to("cuda")`'d) were on cuda:0.

    Pure string check (no torch import needed) so this is real-unit-
    testable without a GPU/CUDA runtime - `load_pipeline()` calls this
    with `str(some_param.device)` from REAL loaded torch modules."""
    if not device_str.startswith("cuda"):
        raise DeviceMismatchError(
            f"{component_name} is on device {device_str!r}, expected a "
            f"CUDA device. Real prior incident: RuntimeError 'Expected "
            f"all tensors to be on the same device, but got index is on "
            f"cpu, different from other tensors on cuda:0'.")


def build_reference_conditioning_metadata(*, used: bool, strength: float = 0.0) -> dict:
    """Metadata rieng VE VIEC reference-conditioning (IP-Adapter) co duoc
    dung cho request nay hay khong - TACH KHOI `build_response_payload()`
    de KHONG doi hop dong response cua duong dan prompt-only cu (xem
    test_shape_and_keys trong server/tests/test_cover_pipeline.py va
    "Requirement 9" cua mission Reference-Conditioned Cover Proof:
    khong tham chieu -> hanh vi/response GIONG HET truoc day). generate()
    chi .update() ket qua nay vao response KHI used=True."""
    return {
        "reference_conditioned": used,
        "reference_strength_used": strength if used else 0.0,
    }


def build_left_right_masks(
    width: int, height: int, *,
    split_fraction: float = 0.5, gap_fraction: float = 0.04,
) -> Tuple[PILImageModule.Image, PILImageModule.Image]:
    """
    Mat na nhi phan (che do "L", trang=vung anh huong) chia TRAI/PHAI cho
    2 nhan vat - dung voi `diffusers.image_processor.IPAdapterMaskProcessor`
    de reference-conditioning cua nhan vat CHINH (primary, ben trai) va
    nhan vat PHU (secondary, ben phai) KHONG bi tron lan vao nhau (xem
    "Requirement 6" cua mission goc - da xac nhan qua tai lieu diffusers
    that la co che dung cho truong hop nay: nhieu ip_adapter_image + mask
    rieng, khong phai doan).

    Real bug fix (mission "Final IP-Adapter Regional Composition Proof"):
    ban truoc CHU DINH cho 2 mask CHONG LAN mot dai o giua
    (`overlap_fraction`, mac dinh 0.08) de tranh duong ranh gioi cung -
    nhung mot proof that (v10) cho thay dung 2 loai loi thuong gap voi
    mask chong lan: nhan vat phu (Anastasia) quay lung/mat khuat, va mot
    nhan vat NGOAI Y MUON xuat hien - ca hai phu hop voi viec 2 tin hieu
    IP-Adapter cung anh huong len CUNG mot vung pixel o giua. Fix: 2 mask
    gio KHONG CHONG LAN — `gap_fraction` (mac dinh 0.04, ~4% chieu rong)
    la mot VUNG CHET (khong thuoc ve nhan vat nao) o giua thay vi mot
    vung CHONG LAN, dam bao ZERO pixel chung ke ca khi
    IPAdapterMaskProcessor.preprocess() co resize/noi suy o ranh gioi.
    `gap_fraction=0.0` van hop le (2 vung ke sat nhau, van khong chong
    lan - chi khac o cho khong co vung chet).

    `split_fraction` mac dinh doi tu 0.55 (primary lon hon, khop khung
    van ban cu "in foreground") sang 0.5 (chia deu) - khop voi khung
    van ban MOI ("waist-up/medium shot", "both faces fully visible",
    khong con nhan manh mot nhan vat lon hon nhan vat kia).

    Tra ve (mask_primary, mask_secondary) — hai doi tuong `PIL.Image`
    che do "L", CHUA qua IPAdapterMaskProcessor.preprocess() (buoc do
    thuoc ve cover_illustrious_app.py, module do co diffusers that).

    PIL duoc import O DAY (khong o dau file) - day la HAM DUY NHAT trong
    module nay thuc su dung PIL, nen day cung la NOI DUY NHAT can import
    no. Import o dau file (module-level) tung la nguyen nhan that khien
    `beam deploy` that bai o buoc discovery (import cuc bo de doc
    @endpoint) truoc ca khi build container that.
    """
    from PIL import Image, ImageDraw

    split_px = int(width * split_fraction)
    half_gap_px = max(0, int(width * gap_fraction)) // 2

    primary_end_px = split_px - half_gap_px          # exclusive
    secondary_start_px = split_px + half_gap_px       # inclusive

    mask_primary = Image.new("L", (width, height), 0)
    if primary_end_px > 0:
        ImageDraw.Draw(mask_primary).rectangle(
            [0, 0, primary_end_px - 1, height], fill=255)

    mask_secondary = Image.new("L", (width, height), 0)
    if secondary_start_px < width:
        ImageDraw.Draw(mask_secondary).rectangle(
            [secondary_start_px, 0, width, height], fill=255)

    return mask_primary, mask_secondary
