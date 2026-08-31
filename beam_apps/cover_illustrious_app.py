"""
Beam Cloud GPU endpoint — Illustrious/Animagine-class anime cover model.

Deployed TO Beam (not run locally, not part of this repo's own dependency
graph — Image() below declares packages for the REMOTE container only,
server/requirements.txt is untouched). Deploy with:

    beam deploy beam_apps/cover_illustrious_app.py:generate

Response shape matches server/cover_pipeline.py::HttpImageCoverProvider's
"simple" api_style EXACTLY ({"prompt": str} in, {"image_base64": str} out)
so the already-built, already-tested HttpImageCoverProvider(api_style="simple")
works against this endpoint with zero code changes on the repo side —
only the base_url/api_key/simple_path (root, no /generate — see
HttpImageCoverProvider's own docstring) need pointing at the real deployed
URL.

Model: cagliostrolab/animagine-xl-4.0 (open weights, HuggingFace) — a real,
purpose-built anime SDXL fine-tune, ~8GB VRAM at fp16, confirmed via real
research (docs/reports/ from Mission G Track 3). Not FLUX: FLUX's anime
LoRA/style ecosystem is weaker than SDXL/Illustrious today, and FLUX.2 is
64GB at full precision - impractical for a bounded benchmark.

MODEL LOADING: `load_pipeline()` runs via Beam's `on_start` hook — exactly
ONCE per container lifetime, not on every request. This is a real fix for
a real bug: the original version called
`StableDiffusionXLPipeline.from_pretrained(...)` directly inside
`generate()`, so EVERY request (including two back-to-back calls in the
same still-warm container) reloaded the full model from scratch. Real
evidence from the pre-fix deployment: two real Cloud Shell benchmark runs
measured 241.14s and 267.48s wall time each — the second run, made
immediately after the first, was NOT meaningfully faster, proving the
model was reloaded rather than reused. `context.on_start_value` now holds
the already-loaded pipeline (plus the one-time load duration) so
`generate()` only ever performs inference.

MODEL WEIGHT CACHE: a Beam `Volume` mounted at `CACHE_PATH` is passed as
`cache_dir` to `from_pretrained()` so the ~8GB of downloaded HuggingFace
weights persist across container restarts too, not just within one
container's lifetime — a cold container after this change still needs to
run `on_start` once, but skips re-downloading weights it already fetched
in an earlier container.

SEED: `generate()` accepts an optional `seed` (default -1 = unseeded,
unchanged prior behavior). seed >= 0 builds a `torch.Generator` for
deterministic output, and the ACTUAL seed used is echoed back in the
response so multiple prompt-refinement candidates
(scripts/beam_cover_refinement.py) can be recorded and compared 1:1
against the image that produced them.

REFERENCE CONDITIONING (IP-Adapter): real problem - even with the
character-identity descriptor layer (hair/eyes/outfit tags in the text
prompt, see server/character_identity.py), a real proof run still
produced wrong character counts and incorrect identity. Prompt-only
text conditioning was declared insufficient; this adds an OPTIONAL image-
reference-conditioned mode, chosen and researched for real (not assumed):

- Mechanism: IP-Adapter (docs.beam.cloud-independent, a diffusers/
  h94/IP-Adapter feature) via `ip-adapter-plus-face_sdxl_vit-h` - the
  FACE-cropped-trained SDXL variant, confirmed real via
  huggingface.co/h94/IP-Adapter (sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors)
  and docs.huggingface.co/diffusers/using-diffusers/ip_adapter (fetched
  2026-08-31, not assumed). Chosen over the non-face "plus"/plain SDXL
  variants because the goal is FACIAL identity fidelity for a cover
  where pose/background must stay prompt-controlled, not copied from the
  reference photo - a whole-image adapter would drag in unwanted
  pose/background from the reference. Trade-off: this variant targets
  FACE identity specifically; OUTFIT consistency still relies on the
  text-prompt descriptor tags already in place (CoverPromptBuilder), not
  on the reference image.
- SDXL-compatibility: IP-Adapter's cross-attention branch attaches to any
  SDXL-architecture UNet regardless of fine-tune checkpoint (this is the
  documented, community-standard property of IP-Adapter - it does not
  require retraining per checkpoint). cagliostrolab/animagine-xl-4.0 is
  itself an SDXL fine-tune, so this SHOULD attach cleanly - NOT yet
  verified against a real GPU call from here (see Requirement 11 - one
  real proof call is prepared but not executed by this codebase).
- Two independent identities without blending: diffusers documents a
  real, exact mechanism for this - ONE IP-Adapter checkpoint loaded once,
  invoked with `ip_adapter_image=[[img1, img2]]` (nested list) plus
  `cross_attention_kwargs={"ip_adapter_masks": masks}` built via
  `diffusers.image_processor.IPAdapterMaskProcessor`, so each reference
  image only conditions its OWN masked region of the output - this is
  the real answer to "is masked/independent conditioning needed to avoid
  blending" (yes, and this is the documented way to do it, not a guess).
  The masks themselves (deterministic left/right split, matching the
  existing "primary foreground / secondary beside" text composition) are
  built by `cover_illustrious_logic.build_left_right_masks()` - real-
  unit-tested there since it only needs Pillow (already a transitive
  diffusers dependency), not torch/diffusers/beam.
- Fallback preservation (no references -> unchanged): calling
  `load_ip_adapter()` on a diffusers pipeline object makes
  `ip_adapter_image`/`ip_adapter_image_embeds` effectively REQUIRED on
  every future call to THAT object - it cannot be "turned off" per-call
  without still paying an extra CLIP image-encode cost. So a SEPARATE
  pipeline object (`ip_adapter_pipe`) is built in `load_pipeline()`,
  sharing the SAME already-loaded unet/vae/text_encoders as the plain
  `pipe` via `StableDiffusionXLPipeline(**pipe.components)` (a real,
  documented diffusers pattern for reusing loaded submodules across
  pipeline instances) - `load_ip_adapter()` is called ONLY on
  `ip_adapter_pipe`, so `pipe` (used whenever no reference images are
  supplied) is NEVER touched and behaves byte-for-byte as before this
  change. NOTE: this specific combination (`.components` sharing +
  `load_ip_adapter()` on the derived instance) is MY synthesis of two
  independently-documented diffusers features, not a single verified
  official example - it is the highest-risk unverified part of this
  design and should be watched closely on first real deploy.
- VRAM/cost: ESTIMATES only, not measurements (no real GPU call made from
  here) - incremental VRAM ~1.5-2GB (CLIP ViT-H image encoder ~1.2GB fp16
  + adapter weights ~100-300MB) on top of the existing ~8GB Animagine
  usage, comfortable within RTX4090's 24GB. Cold start: one-time download
  of the new weights (~1.5-2GB) adds an estimated 10-40s to the already-
  measured 39.749s cold load, cached in the same Beam Volume thereafter.
  Warm inference: estimated +0.5-2s over the measured 5.211s baseline for
  the added CLIP image-embedding forward pass(es).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from beam import Image, Volume, endpoint  # noqa: E402

from cover_illustrious_logic import (  # noqa: E402
    build_left_right_masks, build_reference_conditioning_metadata,
    build_response_payload, resolve_negative_prompt,
)

MODEL_ID = "cagliostrolab/animagine-xl-4.0"
CACHE_PATH = "./sdxl-weights"
IP_ADAPTER_REPO = "h94/IP-Adapter"
IP_ADAPTER_WEIGHT_NAME = "ip-adapter-plus-face_sdxl_vit-h.safetensors"

image = Image(python_version="python3.11").add_python_packages([
    "diffusers>=0.31,<1.0",
    "torch>=2.4,<3.0",
    "transformers>=4.44,<5.0",
    "accelerate>=0.33,<1.0",
    "safetensors>=0.4,<1.0",
    "pillow>=10.0,<12.0",
])


def load_pipeline():
    """on_start hook - chay DUY NHAT MOT LAN moi container, KHONG chay lai
    tren moi request (xem docstring module o tren de biet bang chung that
    ve loi cu). Tra ve (pipe_thuong, pipe_ip_adapter, thoi_gian_load_giay).

    `pipe_ip_adapter` la MOT INSTANCE RIENG chia se cung unet/vae/
    text_encoders voi `pipe_thuong` (qua `StableDiffusionXLPipeline(**pipe.components)`)
    - KHONG goi load_ip_adapter() truc tiep tren `pipe_thuong`, vi lam vay
    se buoc MOI request sau nay tren pipe do phai truyen ip_adapter_image,
    pha vo duong dan prompt-only cu (xem docstring module)."""
    import time

    import torch
    from diffusers import StableDiffusionXLPipeline

    t0 = time.monotonic()
    pipe = StableDiffusionXLPipeline.from_pretrained(
        MODEL_ID, torch_dtype=torch.float16, use_safetensors=True,
        cache_dir=CACHE_PATH,
    ).to("cuda")

    ip_adapter_pipe = StableDiffusionXLPipeline(**pipe.components)
    ip_adapter_pipe.load_ip_adapter(
        IP_ADAPTER_REPO, subfolder="sdxl_models",
        weight_name=[IP_ADAPTER_WEIGHT_NAME], cache_dir=CACHE_PATH,
    )

    load_seconds = time.monotonic() - t0
    return pipe, ip_adapter_pipe, load_seconds


@endpoint(
    name="cover-illustrious",
    image=image,
    on_start=load_pipeline,
    volumes=[Volume(name="sdxl-weights", mount_path=CACHE_PATH)],
    gpu="RTX4090",  # 24GB VRAM - comfortable headroom over Animagine XL's ~8GB
    cpu=4,
    memory="16Gi",
    # Real GPU-hours only bill while a request is in flight (Beam scale-to-zero,
    # confirmed via docs.beam.cloud/v2/resources/pricing-and-billing: "You are
    # only charged when your containers are running" - no charge while idle,
    # no charge for cold-start machine spin-up).
)
def generate(context, prompt: str, negative_prompt: str = "", steps: int = 28,
            width: int = 1024, height: int = 1536, seed: int = -1,
            primary_reference_image_base64: str = "",
            secondary_reference_image_base64: str = "",
            reference_strength: float = 0.6) -> dict:
    import base64
    import io
    import time

    import torch

    # Both already built by on_start - generate() ONLY does inference.
    pipe, ip_adapter_pipe, model_load_seconds = context.on_start_value

    # seed >= 0 -> deterministic (torch.Generator), so multiple refinement
    # candidates (scripts/beam_cover_refinement.py) can be recorded and
    # compared by seed. seed < 0 (default) -> model's own randomness,
    # unchanged from before this parameter existed.
    generator = None
    if seed >= 0:
        generator = torch.Generator(device="cuda").manual_seed(seed)

    has_primary_ref = bool(primary_reference_image_base64)
    has_secondary_ref = bool(secondary_reference_image_base64)
    used_references = has_primary_ref or has_secondary_ref

    t_infer_start = time.monotonic()
    if not used_references:
        # UNCHANGED prompt-only path - `pipe` never has load_ip_adapter()
        # called on it, so this is byte-for-byte the pre-existing code.
        result = pipe(
            prompt=prompt,
            negative_prompt=resolve_negative_prompt(negative_prompt),
            num_inference_steps=steps,
            width=width,
            height=height,
            generator=generator,
        )
    else:
        from PIL import Image as PILImage

        def _decode(b64: str):
            return PILImage.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")

        if has_primary_ref and has_secondary_ref:
            from diffusers.image_processor import IPAdapterMaskProcessor

            primary_img = _decode(primary_reference_image_base64)
            secondary_img = _decode(secondary_reference_image_base64)
            mask_primary, mask_secondary = build_left_right_masks(width, height)
            processed = IPAdapterMaskProcessor().preprocess(
                [mask_primary, mask_secondary], height=height, width=width)
            masks = [processed.reshape(
                1, processed.shape[0], processed.shape[2], processed.shape[3])]

            ip_adapter_pipe.set_ip_adapter_scale(
                [[reference_strength, reference_strength]])
            result = ip_adapter_pipe(
                prompt=prompt,
                negative_prompt=resolve_negative_prompt(negative_prompt),
                num_inference_steps=steps,
                width=width,
                height=height,
                generator=generator,
                ip_adapter_image=[[primary_img, secondary_img]],
                cross_attention_kwargs={"ip_adapter_masks": masks},
            )
        else:
            # Exactly one reference supplied - no masking needed, applies
            # globally (see Requirement 5: "at least one primary, one
            # secondary" - each slot is supported independently too).
            single_b64 = primary_reference_image_base64 or secondary_reference_image_base64
            single_img = _decode(single_b64)
            ip_adapter_pipe.set_ip_adapter_scale(reference_strength)
            result = ip_adapter_pipe(
                prompt=prompt,
                negative_prompt=resolve_negative_prompt(negative_prompt),
                num_inference_steps=steps,
                width=width,
                height=height,
                generator=generator,
                ip_adapter_image=single_img,
            )
    inference_seconds = time.monotonic() - t_infer_start

    img = result.images[0]
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    payload = build_response_payload(
        png_bytes,
        model_load_seconds=model_load_seconds,
        inference_seconds=inference_seconds,
        width=width,
        height=height,
        seed=seed,
    )
    if used_references:
        payload.update(build_reference_conditioning_metadata(
            used=True, strength=reference_strength))
    return payload
