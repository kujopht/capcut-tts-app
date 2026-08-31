"""
Pure, beam-SDK-independent helper logic for cover_illustrious_app.py.

Split out so this logic can be real-unit-tested: `beam`/`torch`/`diffusers`
are remote-deploy-only dependencies (see cover_illustrious_app.py's own
docstring) and are NOT installed in this repo's own venv, so any module
that imports them at top level cannot be imported locally at all, let
alone tested. This file imports NONE of those three - only stdlib plus
Pillow (`PIL`), which genuinely IS installed in this repo's venv already
(desktop app dependency) and is ALSO a transitive dependency of
`diffusers` on the remote side (cover_illustrious_app.py already calls
`img.save(buf, format="PNG")` on a PIL Image returned by the pipeline) -
so using it here adds no new dependency on either side.
"""
from __future__ import annotations

import base64

from PIL import Image, ImageDraw

#: Ban goc chi co cac tag chat luong chung. Them cac tag chong "bia dong
#: nguoi" sau khi ban Re:Zero dau tien thuc te tro thanh poster ensemble
#: dong duc/nhan vat trung lap - khong dung lam bia san xuat duoc (xem
#: CoverPromptBuilder's docstring trong server/cover_pipeline.py).
DEFAULT_NEGATIVE_PROMPT = (
    "lowres, bad anatomy, bad hands, text, error, missing fingers, "
    "extra digit, fewer digits, cropped, worst quality, low quality, "
    "normal quality, jpeg artifacts, signature, watermark, blurry, "
    "crowd, group, ensemble cast, extra person, background character, "
    "duplicate character, cloned face, multiple girls, multiple boys, "
    "collage, character sheet"
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
    split_fraction: float = 0.55, overlap_fraction: float = 0.08,
):
    """
    Mat na nhi phan (che do "L", trang=vung anh huong) chia TRAI/PHAI cho
    2 nhan vat - dung voi `diffusers.image_processor.IPAdapterMaskProcessor`
    de reference-conditioning cua nhan vat CHINH (primary, ben trai) va
    nhan vat PHU (secondary, ben phai) KHONG bi tron lan vao nhau (xem
    "Requirement 6" cua mission - da xac nhan qua tai lieu diffusers that
    la co che dung cho truong hop nay: nhieu ip_adapter_image + mask
    rieng, khong phai doan).

    Mac dinh khop voi ngu nghia bo cuc van ban da co trong
    server/cover_pipeline.py::CoverPromptBuilder ("primary in foreground,
    focal point" / "secondary positioned beside/behind primary") - primary
    chiem phan lon hon (`split_fraction` mac dinh 0.55) va CHUNG LAN mot
    dai o giua (`overlap_fraction`) de tranh duong ranh gioi cung/gay
    "ghep 2 nua anh" thay vi mot bo cuc lien mach.

    Tra ve (mask_primary, mask_secondary) — hai doi tuong `PIL.Image`
    che do "L", CHUA qua IPAdapterMaskProcessor.preprocess() (buoc do
    thuoc ve cover_illustrious_app.py, module do co diffusers that).
    """
    split_px = int(width * split_fraction)
    overlap_px = int(width * overlap_fraction)

    mask_primary = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask_primary).rectangle(
        [0, 0, min(width, split_px + overlap_px), height], fill=255)

    mask_secondary = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask_secondary).rectangle(
        [max(0, split_px - overlap_px), 0, width, height], fill=255)

    return mask_primary, mask_secondary
