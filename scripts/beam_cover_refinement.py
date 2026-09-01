#!/usr/bin/env python3
"""Real Beam Cloud cover PROMPT-REFINEMENT run - exactly THREE paid
candidates, back to back on the same (already-warm, already-proven)
cover-illustrious deployment. This is NOT another cold/warm infrastructure
benchmark - scripts/beam_cover_benchmark.py already proved the execution
path (real evidence: 74.60s cold / 16.05s warm). This script exists
because the FIRST real cover was technically fine but unsuitable for
production: it became a crowded ensemble poster (all of characters[]
rendered at once). The fix is in server/cover_pipeline.py::
CoverPromptBuilder (cast-driven prompt: primary_character/
secondary_character/tertiary_character, default max_visible_characters=2,
tag-oriented composition) and in beam_apps/cover_illustrious_app.py
(seed support, so each candidate is reproducible and comparable).

Reads BEAM_TOKEN from this process's own environment at execution time.
Never printed/logged. Requires the ALREADY-REDEPLOYED endpoint (this
script sends `seed`, which only the updated generate() understands - see
beam_apps/cover_illustrious_app.py's own docstring for the exact deploy
command). Run:

    .venv\\Scripts\\python.exe scripts\\beam_cover_refinement.py --endpoint-url <url>

HARD CAP: exactly 3 calls, no CLI flag to request more - enforced in code
(SEEDS below), not just by convention, per Mission G's explicit "generate
at most THREE paid refinement candidates" instruction.

Re:Zero cast for this refinement round (per explicit instruction):
primary = Natsuki Subaru, secondary = Anastasia Hoshin. Felix Argyle is
deliberately OMITTED from this first refinement test (default
max_visible_characters=2 already enforces this even if a tertiary_character
were set, but this script doesn't set one at all, to be unambiguous).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from beam_apps.cover_illustrious_logic import DEFAULT_NEGATIVE_PROMPT  # noqa: E402
from server.cover_pipeline import CoverGenerationRequest, CoverPromptBuilder  # noqa: E402

from scripts.beam_credential import resolve_beam_token  # noqa: E402

TOKEN_ENV_VAR = "BEAM_TOKEN"

# Real published RTX4090 on-demand rate - see beam_cover_benchmark.py for
# the same constant/citation. A rate, not a benchmark measurement.
RTX4090_PER_SECOND_USD = 0.000191667

#: Exactly 3 - hard cap, not a default. Distinct seeds so results are
#: reproducible AND visually comparable to each other.
SEEDS = (20260901, 20260902, 20260903)


def _call_beam_endpoint(
    endpoint_url: str, token: str, prompt: str, seed: int, timeout_seconds: float,
) -> tuple[dict, float]:
    client = httpx.Client(
        base_url=endpoint_url.rstrip("/"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout_seconds,
    )
    t0 = time.monotonic()
    resp = client.post("", json={"prompt": prompt, "seed": seed})
    wall_seconds = time.monotonic() - t0
    if resp.status_code != 200:
        raise RuntimeError(
            f"Beam endpoint tra loi {resp.status_code}: {resp.text[:300]}")
    return resp.json(), wall_seconds


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint-url", required=True,
                   help="Beam endpoint URL (cover-illustrious, ALREADY "
                        "redeployed with seed support)")
    p.add_argument("--out-prefix", default="rezero_cover_refinement")
    p.add_argument("--timeout-seconds", type=float, default=300.0)
    a = p.parse_args()

    token = resolve_beam_token()
    if not token:
        print(f"BLOCKED: {TOKEN_ENV_VAR} not found in process env or the "
              "credential broker. One-time setup: python "
              "scripts/fanfic_credential_broker.py store --name BEAM_TOKEN",
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
        # Metadata only - does NOT drive the prompt (see CoverPromptBuilder).
        characters=["Natsuki Subaru", "Anastasia Hoshin", "Felix Argyle"],
        genres=["Isekai", "Fantasy", "Drama"],
        mood="bittersweet",
        primary_character="Natsuki Subaru",
        secondary_character="Anastasia Hoshin",
        # tertiary_character left empty - Felix Argyle must NOT appear in
        # this first refinement test, per explicit instruction.
    )
    prompt = CoverPromptBuilder.build_prompt(req)
    print("Prompt (deterministic, cast-driven, tag-oriented):")
    print(f"  {prompt}")
    print(f"\nNegative prompt (from the deployed endpoint's own default, "
          f"unless overridden - not sent by this script):")
    print(f"  {DEFAULT_NEGATIVE_PROMPT}")
    print(f"\nThis script makes EXACTLY {len(SEEDS)} real GPU calls "
          f"(seeds: {SEEDS}) - re-running it means {len(SEEDS)} MORE "
          f"billed images.")

    manifest = []
    for i, seed in enumerate(SEEDS, start=1):
        print(f"\n--- Candidate {i}/{len(SEEDS)} (seed={seed}) ---")
        data, wall_seconds = _call_beam_endpoint(
            a.endpoint_url, token, prompt, seed, a.timeout_seconds)

        png_bytes = base64.b64decode(data["image_base64"])
        out_path = Path(f"{a.out_prefix}_candidate_{i}.png")
        out_path.write_bytes(png_bytes)

        model_load_seconds = float(data.get("model_load_seconds", 0.0))
        inference_seconds = float(data.get("inference_seconds", 0.0))
        returned_seed = data.get("seed", -1)
        size_bytes = int(data.get("size_bytes", len(png_bytes)))
        est_cost = wall_seconds * RTX4090_PER_SECOND_USD

        entry = {
            "candidate_index": i,
            "requested_seed": seed,
            "returned_seed": returned_seed,
            "prompt": prompt,
            "negative_prompt": DEFAULT_NEGATIVE_PROMPT,
            "primary_character": req.primary_character,
            "secondary_character": req.secondary_character,
            "tertiary_character": req.tertiary_character,
            "max_visible_characters": req.max_visible_characters,
            "wall_clock_seconds": round(wall_seconds, 2),
            "model_load_seconds": round(model_load_seconds, 3),
            "inference_seconds": round(inference_seconds, 3),
            "size_bytes": size_bytes,
            "approx_cost_usd": round(est_cost, 4),
            "output_file": str(out_path),
        }
        manifest.append(entry)

        if returned_seed != seed:
            print(f"WARNING: requested seed {seed} but endpoint returned "
                  f"{returned_seed!r} - endpoint may predate the seed fix, "
                  f"redeploy first.", file=sys.stderr)

        print(f"saved: {out_path}")
        print(f"seed={returned_seed} wall={entry['wall_clock_seconds']}s "
              f"load={entry['model_load_seconds']}s "
              f"infer={entry['inference_seconds']}s "
              f"size={entry['size_bytes']} cost=${entry['approx_cost_usd']}")

    manifest_path = Path(f"{a.out_prefix}_manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    total_cost = sum(m["approx_cost_usd"] for m in manifest)
    print(f"\n=== SUMMARY ===")
    print(f"{len(manifest)} candidates saved, manifest: {manifest_path}")
    print(f"total approx_cost_usd: ${round(total_cost, 4)}")
    print("\nManually compare the 3 PNGs - pick the one with correct "
          "2-person composition (Subaru foreground, Anastasia beside/"
          "behind, no crowd/duplicate characters) before using it in "
          "production. Do not publish any of them automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
