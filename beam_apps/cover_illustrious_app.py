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
- IMAGE ENCODER (real bug, real fix): the first real proof call raised
  `RuntimeError: mat1 and mat2 shapes cannot be multiplied (1028x1664 and
  1280x1280)`. Root cause: `load_ip_adapter(subfolder="sdxl_models", ...)`
  defaults `image_encoder_folder="image_encoder"`, JOINED with
  `subfolder` - resolving to "h94/IP-Adapter/sdxl_models/image_encoder",
  which is OpenCLIP ViT-bigG (hidden_size=1664), not the ViT-H encoder
  (hidden_size=1280) the `*_vit-h` checkpoint actually expects. Fixed by
  explicitly loading `CLIPVisionModelWithProjection.from_pretrained(
  IP_ADAPTER_REPO, subfolder="models/image_encoder", ...)` (the TOP-LEVEL
  path, matching the official diffusers guide's own "Model variants"
  example for `*_vit-h` checkpoints exactly) and passing it to the
  pipeline CONSTRUCTOR before `load_ip_adapter()` runs - diffusers does
  not override an already-set, non-None `image_encoder`. `load_pipeline()`
  also asserts `hidden_size == 1280` at startup (see
  `assert_ip_adapter_encoder_compatible()` in cover_illustrious_logic.py)
  so a future mismatch fails loudly at container start, not mid-inference.
- DEVICE PLACEMENT (real bug, real fix): the NEXT real proof call raised
  `RuntimeError: Expected all tensors to be on the same device, but got
  index is on cpu, different from other tensors on cuda:0`. Root cause:
  the explicitly-loaded ViT-H image encoder above was constructed via
  `.from_pretrained()` but never moved to CUDA, while everything else
  (shared from the base `pipe`, already `.to("cuda")`'d) was on cuda:0.
  Fixed by chaining `.to("cuda")` on the encoder itself, on the
  constructed `ip_adapter_pipe` (official diffusers pattern: construct
  with the explicit `image_encoder=`, then `.to("cuda")` the whole
  pipeline), and AGAIN after `load_ip_adapter()` (which installs new
  adapter/image-projection modules into the UNet that also need moving -
  `.to("cuda")` is idempotent and version-agnostic, so this is the real
  guarantee rather than depending on a specific, version-sensitive
  internal attribute name). `load_pipeline()` also asserts the encoder,
  the UNet, and (when present) the UNet's `encoder_hid_proj` are all on
  CUDA at startup (see `assert_component_on_cuda()` in
  cover_illustrious_logic.py) so a future device mismatch fails loudly
  at container start, not mid-inference.
- Two independent identities without blending: diffusers documents a
  real, exact mechanism for this - ONE IP-Adapter checkpoint loaded once,
  invoked with `ip_adapter_image=[[img1, img2]]` (nested list) plus
  `cross_attention_kwargs={"ip_adapter_masks": masks}` built via
  `diffusers.image_processor.IPAdapterMaskProcessor`, so each reference
  image only conditions its OWN masked region of the output - this is
  the real answer to "is masked/independent conditioning needed to avoid
  blending" (yes, and this is the documented way to do it, not a guess).
  The masks themselves (deterministic left/right split, matching the
  "waist-up shot, on left/on right" text composition) are built by
  `cover_illustrious_logic.build_left_right_masks()` - real-unit-tested
  there since it only needs Pillow (already a transitive diffusers
  dependency), not torch/diffusers/beam. REAL FIX (mission "Final
  IP-Adapter Regional Composition"): a real v10 proof showed exactly the
  failure mode overlapping masks risk - an unwanted extra/background
  character plus a text-like artifact, alongside a badly-cropped primary
  face and a secondary character facing away. The masks are now
  NON-OVERLAPPING (a small dead-zone gap at the center instead of a
  deliberately-shared band) so neither identity's reference conditions
  the other's pixels.
- REFERENCE STRENGTH lowered 0.6 -> 0.5 (mission "Final IP-Adapter
  Regional Composition"): the v10 proof's identity signal was real and
  recognizable (Subaru's tracksuit, Anastasia's hair/fur) but composition
  control was weak (cropping, wrong facing direction, extra person) - a
  more conservative scale trades a little identity strength for more
  headroom for the text prompt's composition instructions to actually
  govern framing/pose, per diffusers' own documented guidance that lower
  IP-Adapter scale values (0.5-0.8 typical) balance image and text
  conditioning rather than letting the image reference dominate.
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

MULTI-IMAGE PER CHARACTER (schema-level only, "V1" mission): each side
accepts a LIST of reference images (`primary_reference_images_base64`/
`secondary_reference_images_base64`, matching
server/character_identity.py::CharacterVisualIdentity.reference_images) -
diffusers DOES support averaging multiple images for one adapter slot
(`ip_adapter_image=[img1, img2]` when only one adapter is loaded), but
combining that with the masked-dual-identity path below would be a
SECOND unverified API-combination stacked on the first (`.components`
sharing + `load_ip_adapter()`). To avoid compounding unverified
diffusers-API assumptions in one deploy, `generate()` currently uses only
the FIRST image in each list for actual conditioning - the schema accepts
more for forward-compatibility, but only the first is read for now (see
inline comment at the point images are selected).

TIMEOUT: `@endpoint(timeout=900, ...)` - real bug, real fix. A real
reference-proof call ended in the Beam dashboard as task
status=Cancelled with Started="-"/Duration="-" (never actually ran).
Beam's own `timeout` default is 180s (confirmed via
docs.beam.cloud/v2/reference/py-sdk.md), and a cold container running
on_start (base SDXL weights + the separate IP-Adapter pipeline's weights,
all first-time downloads if the Volume cache is empty) plus real GPU
inference can plausibly exceed that. See the `@endpoint(...)` call's own
comment for the full citation. `keep_warm_seconds` (the scale-to-zero
knob) is untouched - this only changes how long a single task is allowed
to run, not container idle lifecycle.
"""
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from beam import Image, Volume, endpoint  # noqa: E402

from cover_illustrious_logic import (  # noqa: E402
    IP_ADAPTER_IMAGE_ENCODER_SUBFOLDER, assert_component_on_cuda,
    assert_ip_adapter_encoder_compatible, build_left_right_masks,
    build_reference_conditioning_metadata, build_response_payload,
    resolve_negative_prompt,
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
    pha vo duong dan prompt-only cu (xem docstring module).

    Real bug fix: image encoder cho IP-Adapter duoc nap TUONG MINH tu
    `IP_ADAPTER_IMAGE_ENCODER_SUBFOLDER` ("models/image_encoder" - dung
    ViT-H) va truyen vao HAM DUNG cua `ip_adapter_pipe`, thay vi de
    `load_ip_adapter()` tu suy ra duong dan (mac dinh
    "sdxl_models/image_encoder" khi `subfolder="sdxl_models"` - do la
    ViT-bigG SAI, xem IP_ADAPTER_IMAGE_ENCODER_SUBFOLDER's own docstring
    trong cover_illustrious_logic.py cho bang chung that). Mau nay khop
    CHINH XAC vi du chinh thuc cua diffusers cho cac bien the "*_vit-h"
    (docs.huggingface.co/diffusers/using-diffusers/ip_adapter, muc "Model
    variants"): nap CLIPVisionModelWithProjection tuong minh, truyen vao
    constructor cua pipeline (KHONG phai load_ip_adapter()) - diffusers
    KHONG ghi de mot `image_encoder` da duoc gan san, khac None, tren
    pipeline object."""
    import time

    import torch
    from diffusers import StableDiffusionXLPipeline
    from transformers import CLIPVisionModelWithProjection

    t0 = time.monotonic()
    pipe = StableDiffusionXLPipeline.from_pretrained(
        MODEL_ID, torch_dtype=torch.float16, use_safetensors=True,
        cache_dir=CACHE_PATH,
    ).to("cuda")

    # Real bug fix: this encoder is constructed fresh (not inherited from
    # `pipe.components`, which is already CUDA-resident since `pipe` was
    # `.to("cuda")`'d above) - `.from_pretrained()` defaults to CPU, and
    # nothing else moves a constructor-supplied `image_encoder=` kwarg
    # for you. Real evidence: RuntimeError "Expected all tensors to be
    # on the same device, but got index is on cpu, different from other
    # tensors on cuda:0" on a real Beam GPU call - this exact `.to("cuda")`
    # was missing.
    ip_adapter_image_encoder = CLIPVisionModelWithProjection.from_pretrained(
        IP_ADAPTER_REPO, subfolder=IP_ADAPTER_IMAGE_ENCODER_SUBFOLDER,
        torch_dtype=torch.float16, cache_dir=CACHE_PATH,
    ).to("cuda")
    # Fail LOUDLY here (on_start/container startup) instead of a cryptic
    # matmul RuntimeError mid-inference (Requirement 3, prior incident).
    assert_ip_adapter_encoder_compatible(
        ip_adapter_image_encoder.config.hidden_size, IP_ADAPTER_WEIGHT_NAME)

    # pipe.components may include an `image_encoder: None` entry (plain
    # SDXL checkpoints have none) - drop it so the explicit real encoder
    # below is not shadowed by a duplicate/conflicting kwarg.
    ip_adapter_components = dict(pipe.components)
    ip_adapter_components.pop("image_encoder", None)
    # Official diffusers pattern: construct with the explicit image
    # encoder, THEN .to("cuda") the whole pipeline - idempotent for the
    # components already on CUDA (shared from `pipe`), and the real fix
    # for the encoder itself (redundant with the .to("cuda") above, kept
    # anyway to match the documented pattern exactly and as defense in
    # depth if a future edit ever constructs the encoder without it).
    ip_adapter_pipe = StableDiffusionXLPipeline(
        **ip_adapter_components, image_encoder=ip_adapter_image_encoder,
    ).to("cuda")
    ip_adapter_pipe.load_ip_adapter(
        IP_ADAPTER_REPO, subfolder="sdxl_models",
        weight_name=[IP_ADAPTER_WEIGHT_NAME], cache_dir=CACHE_PATH,
    )
    # load_ip_adapter() installs NEW adapter/image-projection modules
    # into the UNet (Requirement 3) - re-assert full-CUDA placement
    # afterward. .to("cuda") is idempotent and moves everything currently
    # registered on the pipeline, without needing to know the exact
    # internal attribute name diffusers uses for the newly-installed
    # projection layer (version-sensitive - ImageProjection/Resampler
    # depending on the IP-Adapter variant).
    ip_adapter_pipe.to("cuda")

    # Requirement 4 - fail loudly at startup if any critical component
    # ended up on the wrong device, instead of a cryptic mid-inference
    # "Expected all tensors to be on the same device" error.
    assert_component_on_cuda(
        "ip_adapter_image_encoder",
        str(next(ip_adapter_image_encoder.parameters()).device))
    assert_component_on_cuda(
        "ip_adapter_pipe.unet", str(next(ip_adapter_pipe.unet.parameters()).device))
    # The IP-Adapter image-projection layer lives on unet.encoder_hid_proj
    # once load_ip_adapter() has run, for every IP-Adapter variant this
    # code supports today - checked when present. The unconditional
    # .to("cuda") calls above are the real, version-agnostic guarantee;
    # this is an extra, more specific confirmation on top of that.
    encoder_hid_proj = getattr(ip_adapter_pipe.unet, "encoder_hid_proj", None)
    if encoder_hid_proj is not None:
        proj_params = list(encoder_hid_proj.parameters())
        if proj_params:
            assert_component_on_cuda(
                "ip_adapter_pipe.unet.encoder_hid_proj", str(proj_params[0].device))

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
    timeout=900,
    # Real bug (user-reported): a real reference-proof call ended with the
    # Beam dashboard showing task status=Cancelled, Started="-",
    # Duration="-" - i.e. the task never got to actually run before being
    # killed. Beam's @endpoint `timeout` defaults to 180 SECONDS (confirmed
    # via docs.beam.cloud/v2/reference/py-sdk.md's own decorator signature:
    # `timeout: float = 180` - "maximum number of seconds a task can run
    # before it times out"), and "Endpoints are RESTful APIs, designed for
    # synchronous tasks that can complete in 180 seconds or less"
    # (docs.beam.cloud/v2/endpoint/overview). A genuinely cold container
    # running on_start (base SDXL weights + the SEPARATE IP-Adapter
    # pipeline's CLIP image encoder + adapter weights, all first-time
    # downloads if the Volume cache is empty) can plausibly exceed that,
    # especially combined with actual GPU inference on the same request.
    # 900s (15 min) gives generous headroom for a fully-cold first call
    # without disabling the timeout entirely (`timeout=-1` would remove
    # crash/hang protection - not done here).
    # keep_warm_seconds is DELIBERATELY left at its default (300s) - this
    # is the scale-to-zero/idle-shutdown knob, a DIFFERENT setting from
    # `timeout` above. Do not confuse the two: raising `timeout` makes a
    # single task allowed to run longer; it does not keep the container
    # warm between requests. Real GPU-hours only bill while a request is
    # in flight (Beam scale-to-zero, confirmed via
    # docs.beam.cloud/v2/resources/pricing-and-billing: "You are only
    # charged when your containers are running" - no charge while idle,
    # no charge for cold-start machine spin-up).
)
def generate(context, prompt: str, negative_prompt: str = "", steps: int = 28,
            width: int = 1024, height: int = 1536, seed: int = -1,
            primary_reference_images_base64: Optional[List[str]] = None,
            secondary_reference_images_base64: Optional[List[str]] = None,
            reference_strength: float = 0.5) -> dict:
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

    primary_refs = primary_reference_images_base64 or []
    secondary_refs = secondary_reference_images_base64 or []
    has_primary_ref = bool(primary_refs)
    has_secondary_ref = bool(secondary_refs)
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

        # Only the FIRST image per side is used for actual conditioning -
        # see module docstring "MULTI-IMAGE PER CHARACTER": averaging
        # multiple images for one identity AND masking two identities at
        # once would stack two unverified diffusers-API combinations in
        # one deploy. The schema accepts a list for forward-compat; this
        # code deliberately only reads index 0 for now.
        if has_primary_ref and has_secondary_ref:
            from diffusers.image_processor import IPAdapterMaskProcessor

            primary_img = _decode(primary_refs[0])
            secondary_img = _decode(secondary_refs[0])
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
            # Exactly one side supplied - no masking needed, applies
            # globally (see Requirement 4: "at least one primary, one
            # secondary" - each slot is supported independently too).
            single_b64 = (primary_refs or secondary_refs)[0]
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
