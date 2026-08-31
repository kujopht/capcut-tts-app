#!/usr/bin/env python3
"""Real Beam Cloud cover-generation benchmark - Illustrious/Animagine-XL,
ONE representative cover for the Re:Zero DRAFT (nov_1e38f5532fab4681).

Reads BEAM_TOKEN from this process's own environment at execution time.
Never printed/logged. Run from the shell that has it, after
`scripts/beam_setup_check.py` reports clean:

    .venv\\Scripts\\python.exe scripts\\beam_deploy.py cover     # one-time deploy
    .venv\\Scripts\\python.exe scripts\\beam_cover_benchmark.py --endpoint-url <url>

Uses the ALREADY-BUILT, ALREADY-TESTED
server.cover_pipeline.HttpImageCoverProvider(api_style="simple") - the
Beam endpoint (beam_apps/cover_illustrious_app.py) returns EXACTLY the
{"image_base64": ...} shape that provider expects. No new provider code
needed - this script only wires real inputs into the existing pipeline.

Real inputs used: the ACTUAL Re:Zero DRAFT's metadata (title, fandom,
characters), run through the ALREADY-BUILT, ALREADY-TESTED
CoverPromptBuilder.build_prompt() - not a hand-typed prompt.

COLD vs WARM (this script makes exactly TWO real GPU calls, once each -
no more, no less, so re-running it means two more billed images):
beam_apps/cover_illustrious_app.py now loads the model ONCE per container
via Beam's on_start hook (see that file's own docstring for the real bug
this fixes - two pre-fix benchmark runs measured 241.14s and 267.48s,
proving the model was reloaded every request). This script calls the
deployed endpoint TWICE, back to back in one execution: call 1 is
whatever state the container is actually in (cold if no recent traffic,
warm if it is), call 2 happens immediately after and should hit the SAME
still-warm container. Both calls' real model_load_seconds/
inference_seconds (returned by the endpoint itself, not estimated here)
are reported separately, plus a wall-clock total and an APPROXIMATE
container/queueing overhead (wall_clock - model_load - inference) for
each - approximate because container provisioning before the process
starts cannot be measured from inside Python.

The endpoint is called directly via httpx (not through
HttpImageCoverProvider) so this script can read the full response JSON
(model_load_seconds/inference_seconds/size_bytes), which
HttpImageCoverProvider deliberately discards for production callers (its
contract is bytes-only). The already-fetched bytes are then run through
the real CoverPipelineService.run_job() pipeline via a pass-through
provider - so the full production-representative path (title overlay,
SVG wrap, storage) is still exercised for each call, WITHOUT triggering a
second real GPU call.
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from server.adapters import MockMediaAssetStore  # noqa: E402
from server.cover_pipeline import (  # noqa: E402
    CoverGenerationRequest, CoverJob, CoverJobStatus, CoverPipelineService,
    CoverProviderError, CoverPromptBuilder,
)

TOKEN_ENV_VAR = "BEAM_TOKEN"

# Real values from Beam's published on-demand rate for RTX 4090 - see
# https://www.beam.cloud/pricing (checked 2026-08-31). This is a published
# RATE, not a benchmark measurement - the script prints both the rate and
# the real measured seconds separately, never conflates them.
RTX4090_PER_SECOND_USD = 0.000191667


class _PrecomputedProvider:
    """Pass-through provider that returns bytes ALREADY fetched from a real
    Beam call - never makes its own HTTP call, so wiring the result through
    CoverPipelineService.run_job() (for a real, full pipeline exercise)
    never triggers a second billed GPU inference."""

    provider_name = "http_image"

    def __init__(self, png_bytes: bytes):
        self._png_bytes = png_bytes

    def generate(self, request: CoverGenerationRequest) -> bytes:
        return self._png_bytes


def _call_beam_endpoint_directly(
    endpoint_url: str, token: str, prompt: str, timeout_seconds: float,
) -> tuple[dict, float]:
    """POST thang vao GOC URL deploy (khong /generate - xem
    HttpImageCoverProvider's docstring). Tra ve (response_json, wall_seconds)."""
    client = httpx.Client(
        base_url=endpoint_url.rstrip("/"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout_seconds,
    )
    t0 = time.monotonic()
    try:
        resp = client.post("", json={"prompt": prompt})
    except httpx.HTTPError as exc:
        raise CoverProviderError(f"Loi goi Beam endpoint: {exc}") from exc
    wall_seconds = time.monotonic() - t0
    if resp.status_code != 200:
        raise CoverProviderError(
            f"Beam endpoint tra loi {resp.status_code}: {resp.text[:300]}")
    return resp.json(), wall_seconds


def _run_one_call(
    label: str, endpoint_url: str, token: str, req: CoverGenerationRequest,
    prompt: str, out_path: Path, timeout_seconds: float,
) -> dict:
    print(f"\n--- Calling {endpoint_url} ({label}) ---")
    data, wall_seconds = _call_beam_endpoint_directly(
        endpoint_url, token, prompt, timeout_seconds)

    png_bytes = base64.b64decode(data["image_base64"])
    model_load_seconds = float(data.get("model_load_seconds", 0.0))
    inference_seconds = float(data.get("inference_seconds", 0.0))
    size_bytes = int(data.get("size_bytes", len(png_bytes)))
    container_overhead_seconds = max(
        0.0, wall_seconds - model_load_seconds - inference_seconds)

    out_path.write_bytes(png_bytes)
    print(f"raw AI-generated art (before overlay) saved: {out_path}")

    # Real, full, already-tested pipeline (run_job) exercised on the
    # already-fetched bytes - no additional GPU call.
    service = CoverPipelineService(
        media_asset_store=MockMediaAssetStore(),
        provider=_PrecomputedProvider(png_bytes))
    job = service.run_job(CoverJob(novel_id=req.novel_id, request=req))
    if job.status != CoverJobStatus.DONE:
        print(f"WARNING: pipeline run_job() did not complete: "
              f"{job.error_message}", file=sys.stderr)

    est_cost = wall_seconds * RTX4090_PER_SECOND_USD
    result = {
        "label": label,
        "container_overhead_seconds_approx": round(container_overhead_seconds, 2),
        "model_load_seconds": round(model_load_seconds, 3),
        "inference_seconds": round(inference_seconds, 3),
        "wall_clock_seconds": round(wall_seconds, 2),
        "size_bytes": size_bytes,
        "approx_cost_usd": round(est_cost, 4),
    }
    print(f"container_overhead_seconds (approx, wall - load - inference): "
          f"{result['container_overhead_seconds_approx']}")
    print(f"model_load_seconds (from endpoint, real): "
          f"{result['model_load_seconds']}")
    print(f"inference_seconds (from endpoint, real): "
          f"{result['inference_seconds']}")
    print(f"wall_clock_seconds (measured here, real): "
          f"{result['wall_clock_seconds']}")
    print(f"size_bytes: {result['size_bytes']}")
    print(f"approx_cost_usd (RTX4090 @ ${RTX4090_PER_SECOND_USD}/s published "
          f"rate): ${result['approx_cost_usd']}")
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint-url", required=True,
                   help="Beam endpoint URL from `beam deploy` output "
                        "(...cover-illustrious...)")
    p.add_argument("--out-prefix", default="rezero_cover_illustrious",
                   help="Prefix for saved raw art: <prefix>_cold.png / "
                        "<prefix>_warm.png")
    p.add_argument("--timeout-seconds", type=float, default=300.0)
    a = p.parse_args()

    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        print(f"BLOCKED: {TOKEN_ENV_VAR} is not set in this process's environment.",
              file=sys.stderr)
        return 2

    req = CoverGenerationRequest(
        novel_id="nov_1e38f5532fab4681",
        title="Re: Zero - Hai Vi Sao Bi Quen Lang",
        fandom="Re:Zero",
        summary=(
            "Anastasia Hoshin va Natsuki Subaru, ca hai bi Pham An cuop mat "
            "ten tuoi sau tran chien Priestella, tinh co gap nhau va lap "
            "mot moi quan he doi tac tren duong toi Kararagi."
        ),
        characters=["Natsuki Subaru", "Anastasia Hoshin", "Felix Argyle"],
        genres=["Isekai", "Fantasy", "Drama"],
        mood="bittersweet",
    )
    prompt = CoverPromptBuilder.build_prompt(req)
    print("Prompt (deterministic, from real Novel metadata):")
    print(f"  {prompt}")
    print("\nThis script makes exactly TWO real GPU calls (cold, then an "
          "immediate warm call on the same deployment) - re-running it "
          "means two MORE billed images.")

    cold = _run_one_call(
        "cold (or already-warm, whatever state the container is actually in)",
        a.endpoint_url, token, req, prompt,
        Path(f"{a.out_prefix}_cold.png"), a.timeout_seconds)
    warm = _run_one_call(
        "warm (immediate second call, same deployment)",
        a.endpoint_url, token, req, prompt,
        Path(f"{a.out_prefix}_warm.png"), a.timeout_seconds)

    print("\n=== SUMMARY (real measurements, not estimates - cost is the "
          "only derived/published-rate figure) ===")
    for r in (cold, warm):
        print(f"[{r['label']}] wall={r['wall_clock_seconds']}s "
              f"load={r['model_load_seconds']}s "
              f"infer={r['inference_seconds']}s "
              f"overhead~={r['container_overhead_seconds_approx']}s "
              f"cost=${r['approx_cost_usd']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
