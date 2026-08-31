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
only the base_url/api_key need pointing at the real deployed URL.

Model: cagliostrolab/animagine-xl-4.0 (open weights, HuggingFace) — a real,
purpose-built anime SDXL fine-tune, ~8GB VRAM at fp16, confirmed via real
research (docs/reports/ from Mission G Track 3). Not FLUX: FLUX's anime
LoRA/style ecosystem is weaker than SDXL/Illustrious today, and FLUX.2 is
64GB at full precision - impractical for a bounded benchmark.
"""
from beam import Image, endpoint

MODEL_ID = "cagliostrolab/animagine-xl-4.0"

image = Image(python_version="python3.11").add_python_packages([
    "diffusers>=0.31,<1.0",
    "torch>=2.4,<3.0",
    "transformers>=4.44,<5.0",
    "accelerate>=0.33,<1.0",
    "safetensors>=0.4,<1.0",
])


@endpoint(
    name="cover-illustrious",
    image=image,
    gpu="RTX4090",  # 24GB VRAM - comfortable headroom over Animagine XL's ~8GB
    cpu=4,
    memory="16Gi",
    # Real GPU-hours only bill while a request is in flight (Beam scale-to-zero,
    # confirmed via docs.beam.cloud/v2/resources/pricing-and-billing: "You are
    # only charged when your containers are running" - no charge while idle,
    # no charge for cold-start machine spin-up).
)
def generate(prompt: str, negative_prompt: str = "", steps: int = 28,
            width: int = 1024, height: int = 1536) -> dict:
    import base64
    import io
    import time

    import torch
    from diffusers import StableDiffusionXLPipeline

    t_load_start = time.monotonic()
    # Loaded on EVERY cold container start - Beam caches the container image
    # layer but not necessarily the downloaded HF weights across restarts
    # unless a Beam Volume is configured (out of scope for this bounded
    # benchmark - real cold-start time INCLUDING weight download is exactly
    # one of the measurements Mission G asked for, not something to hide).
    pipe = StableDiffusionXLPipeline.from_pretrained(
        MODEL_ID, torch_dtype=torch.float16, use_safetensors=True,
    ).to("cuda")
    t_load_done = time.monotonic()

    default_negative = (
        "lowres, bad anatomy, bad hands, text, error, missing fingers, "
        "extra digit, fewer digits, cropped, worst quality, low quality, "
        "normal quality, jpeg artifacts, signature, watermark, blurry"
    )

    t_infer_start = time.monotonic()
    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt or default_negative,
        num_inference_steps=steps,
        width=width,
        height=height,
    )
    t_infer_done = time.monotonic()

    img = result.images[0]
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    return {
        "image_base64": base64.b64encode(png_bytes).decode("ascii"),
        "model_load_seconds": round(t_load_done - t_load_start, 3),
        "inference_seconds": round(t_infer_done - t_infer_start, 3),
        "width": width,
        "height": height,
        "size_bytes": len(png_bytes),
    }
