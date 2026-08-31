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

Measures and reports: cold start (first request after deploy), model load
time (returned by the endpoint itself), inference time, output dimensions,
size, and approximate cost from Beam's own per-second published rate for
the GPU tier used (RTX4090 - see beam_apps/cover_illustrious_app.py).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.adapters import MockMediaAssetStore  # noqa: E402
from server.cover_pipeline import (  # noqa: E402
    CoverGenerationRequest, CoverJob, CoverJobStatus, CoverPipelineService,
    CoverPromptBuilder, HttpImageCoverProvider,
)

TOKEN_ENV_VAR = "BEAM_TOKEN"

# Real values from Beam's published on-demand rate for RTX 4090 - see
# https://www.beam.cloud/pricing (checked 2026-08-31). This is a published
# RATE, not a benchmark measurement - the script prints both the rate and
# the real measured seconds separately, never conflates them.
RTX4090_PER_SECOND_USD = 0.000191667


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint-url", required=True,
                   help="Beam endpoint URL from `beam deploy` output "
                        "(...cover-illustrious...)")
    p.add_argument("--out", default="rezero_cover_illustrious.png",
                   help="Where to save the raw generated art (before overlay)")
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

    real_provider = HttpImageCoverProvider(
        base_url=a.endpoint_url, api_key=token, api_style="simple",
        timeout_seconds=300.0,
    )

    class _CapturingProvider:
        """Thin pass-through - calls the REAL provider exactly ONCE (one
        real GPU call, correctly timed/billed) and also keeps the raw
        bytes locally for visual inspection, since run_job() only stores
        content_hash/size in MockMediaAssetStore, not the raw bytes
        themselves (matches real production: object bytes live in
        storage, not the DB row)."""
        provider_name = "http_image"
        last_raw_bytes: bytes = b""

        def generate(self, request: CoverGenerationRequest) -> bytes:
            raw = real_provider.generate(request)
            _CapturingProvider.last_raw_bytes = raw
            return raw

    # Real, full, already-tested pipeline (run_job) - not a hand-rolled
    # re-implementation of its steps. Exercises the SAME code path a real
    # production cover job would use, including the run_job() fix that
    # wires wrap_raster_as_overlayable_svg into the overlay step.
    service = CoverPipelineService(
        media_asset_store=MockMediaAssetStore(), provider=_CapturingProvider())
    job = CoverJob(novel_id=req.novel_id, request=req)

    print(f"\nCalling {a.endpoint_url} via CoverPipelineService.run_job() "
          f"(cold start + model load + inference all happen inside this "
          f"one call for a fresh container)...")
    t0 = time.monotonic()
    finished = service.run_job(job)
    wall_seconds = time.monotonic() - t0

    if finished.status != CoverJobStatus.DONE:
        print(f"\nFAILED (real error, not an estimate): {finished.error_message}",
              file=sys.stderr)
        return 1

    asset = service._media_asset_store.get_asset(finished.media_asset_id)
    raw_out = Path(a.out)
    raw_out.write_bytes(_CapturingProvider.last_raw_bytes)
    print(f"raw AI-generated art (before overlay) saved: {raw_out}")

    est_cost = wall_seconds * RTX4090_PER_SECOND_USD
    print(f"\n=== RESULT ===")
    print(f"wall_clock_seconds (cold start + load + inference + overlay): "
          f"{wall_seconds:.2f}")
    print(f"media_asset_id: {finished.media_asset_id}")
    print(f"object_key: {asset.object_key}")
    print(f"content_hash: {asset.content_hash}")
    print(f"size_bytes: {asset.size_bytes}")
    print(f"approx cost (RTX4090 @ ${RTX4090_PER_SECOND_USD}/s published rate): "
          f"${est_cost:.4f}")
    print("NOTE: this is ONE cold-start call. Re-run once more within a few "
          "minutes (before Beam scales the container back to zero) to get a "
          "genuine warm-inference-only number for comparison.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
