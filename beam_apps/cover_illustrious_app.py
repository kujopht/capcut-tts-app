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
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from beam import Image, Volume, endpoint  # noqa: E402

from cover_illustrious_logic import (  # noqa: E402
    build_response_payload, resolve_negative_prompt,
)

MODEL_ID = "cagliostrolab/animagine-xl-4.0"
CACHE_PATH = "./sdxl-weights"

image = Image(python_version="python3.11").add_python_packages([
    "diffusers>=0.31,<1.0",
    "torch>=2.4,<3.0",
    "transformers>=4.44,<5.0",
    "accelerate>=0.33,<1.0",
    "safetensors>=0.4,<1.0",
])


def load_pipeline():
    """on_start hook - chay DUY NHAT MOT LAN moi container, KHONG chay lai
    tren moi request (xem docstring module o tren de biet bang chung that
    ve loi cu). Tra ve (pipeline, thoi_gian_load_giay) de generate() bao
    cao dung thoi gian load that cua container nay, khong phai 0 gia."""
    import time

    import torch
    from diffusers import StableDiffusionXLPipeline

    t0 = time.monotonic()
    pipe = StableDiffusionXLPipeline.from_pretrained(
        MODEL_ID, torch_dtype=torch.float16, use_safetensors=True,
        cache_dir=CACHE_PATH,
    ).to("cuda")
    load_seconds = time.monotonic() - t0
    return pipe, load_seconds


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
            width: int = 1024, height: int = 1536) -> dict:
    import io
    import time

    # Model already loaded by on_start - generate() ONLY does inference.
    pipe, model_load_seconds = context.on_start_value

    t_infer_start = time.monotonic()
    result = pipe(
        prompt=prompt,
        negative_prompt=resolve_negative_prompt(negative_prompt),
        num_inference_steps=steps,
        width=width,
        height=height,
    )
    inference_seconds = time.monotonic() - t_infer_start

    img = result.images[0]
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    return build_response_payload(
        png_bytes,
        model_load_seconds=model_load_seconds,
        inference_seconds=inference_seconds,
        width=width,
        height=height,
    )
