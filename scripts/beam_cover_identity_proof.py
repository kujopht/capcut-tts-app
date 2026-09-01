#!/usr/bin/env python3
"""Real Beam Cloud cover PROOF call - EXACTLY ONE real GPU call, testing
whether the new character-identity layer (server/character_identity.py +
CoverPromptBuilder's identity-aware descriptors) actually fixes the real
problem: the first 3 refinement candidates had correct 2-person
composition (candidate #3 especially) but Subaru/Anastasia rendered as
generic anime characters - the prompt only had their NAMES, no visual
descriptors, so the base model (which does not reliably "know" these two
as concepts) had nothing to go on.

This script is DELIBERATELY separate from scripts/beam_cover_refinement.py
(which is for exploring N candidates/seeds) - it makes exactly ONE call,
no CLI flag to raise that, because character-IDENTITY proof only needs
one real image to evaluate, and GPU calls are billed real money.

Reads BEAM_TOKEN from this process's own environment at execution time.
Never printed/logged. Requires the endpoint ALREADY redeployed with seed
support (see beam_apps/cover_illustrious_app.py's own docstring - this
script does not require any NEWER deploy than that, since the identity
layer only changes CLIENT-side prompt construction, not the Beam
@endpoint's callable signature). Run:

    .venv\\Scripts\\python.exe scripts\\beam_cover_identity_proof.py --endpoint-url <url>

PASS criteria (manual, visual - this script cannot judge the image
itself): approximately 1 boy + 1 girl, visually recognizable as
Subaru + Anastasia (messy black hair + tracksuit vs. long purple hair +
white fur-hat dress), no crowd/duplicates, usable light-novel-cover
composition. If this single proof still fails character identity,
STOP - the next lever is LoRA or reference/IP-Adapter conditioning
(server/character_identity.py already has lora_asset_id/
reference_asset_url placeholder fields for exactly that, unwired by
design - see that file's own docstring), not more prompt iteration.
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
from server.character_identity import CharacterIdentityRegistry  # noqa: E402
from server.cover_pipeline import CoverGenerationRequest, CoverPromptBuilder  # noqa: E402

TOKEN_ENV_VAR = "BEAM_TOKEN"

# Real published RTX4090 on-demand rate - see beam_cover_benchmark.py for
# the same constant/citation. A rate, not a benchmark measurement.
RTX4090_PER_SECOND_USD = 0.000191667

#: One fixed seed - reproducible, not a CLI-configurable count. Distinct
#: from the 3 seeds already used in beam_cover_refinement.py's SEEDS
#: tuple (20260901-903) so this proof is trivially distinguishable in
#: any later comparison.
SEED = 20260904


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint-url", required=True,
                   help="Beam endpoint URL (cover-illustrious, already "
                        "deployed with seed support)")
    p.add_argument("--out-prefix", default="rezero_cover_identity_proof")
    p.add_argument("--timeout-seconds", type=float, default=300.0)
    a = p.parse_args()

    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        print(f"BLOCKED: {TOKEN_ENV_VAR} is not set in this process's environment.",
              file=sys.stderr)
        return 2

    registry = CharacterIdentityRegistry()
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
        # tertiary_character left empty - Felix Argyle excluded, same as
        # the earlier refinement round.
    )
    prompt = CoverPromptBuilder.build_prompt(req, registry)
    character_negative_traits = CoverPromptBuilder.build_character_negative_traits(
        req, registry)

    print("Identity-aware prompt (character descriptors now included, "
          "not just names):")
    print(f"  {prompt}")
    print(f"\nPrompt length: {len(prompt)} chars. Character/count tags are "
          f"front-loaded and generic quality tags (\"vibrant colors\", "
          f"\"high quality\", ...) are last, so if the model's text "
          f"encoder truncates a long prompt, the identity-critical part "
          f"survives first.")
    print(f"\nComputed per-character negative traits (NOT yet sent to the "
          f"endpoint - HttpImageCoverProvider's production payload is "
          f"still {{'prompt': ..., 'seed': ...}} only; this is printed "
          f"for visibility into what CharacterVisualIdentity.negative_traits "
          f"is aggregating, ahead of wiring it into the real request):")
    print(f"  {character_negative_traits}")
    print(f"\nDeployed endpoint's own default negative prompt (unchanged, "
          f"already anti-crowd/anti-duplicate):")
    print(f"  {DEFAULT_NEGATIVE_PROMPT}")

    print(f"\nThis script makes EXACTLY ONE real GPU call (seed={SEED}) - "
          f"re-running it means one MORE billed image.")

    client = httpx.Client(
        base_url=a.endpoint_url.rstrip("/"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=a.timeout_seconds,
    )
    t0 = time.monotonic()
    resp = client.post("", json={"prompt": prompt, "seed": SEED})
    wall_seconds = time.monotonic() - t0
    if resp.status_code != 200:
        print(f"FAILED (real error, not an estimate): HTTP {resp.status_code}: "
              f"{resp.text[:500]}", file=sys.stderr)
        return 1

    data = resp.json()
    png_bytes = base64.b64decode(data["image_base64"])
    out_path = Path(f"{a.out_prefix}.png")
    out_path.write_bytes(png_bytes)

    model_load_seconds = float(data.get("model_load_seconds", 0.0))
    inference_seconds = float(data.get("inference_seconds", 0.0))
    returned_seed = data.get("seed", -1)
    size_bytes = int(data.get("size_bytes", len(png_bytes)))
    est_cost = wall_seconds * RTX4090_PER_SECOND_USD

    manifest = {
        "seed": returned_seed,
        "prompt": prompt,
        "prompt_length_chars": len(prompt),
        "character_negative_traits_computed_not_sent": character_negative_traits,
        "primary_character": req.primary_character,
        "secondary_character": req.secondary_character,
        "wall_clock_seconds": round(wall_seconds, 2),
        "model_load_seconds": round(model_load_seconds, 3),
        "inference_seconds": round(inference_seconds, 3),
        "size_bytes": size_bytes,
        "approx_cost_usd": round(est_cost, 4),
        "output_file": str(out_path),
    }
    manifest_path = Path(f"{a.out_prefix}_manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n=== RESULT ===")
    print(f"saved: {out_path}")
    print(f"manifest: {manifest_path}")
    print(f"seed={returned_seed} wall={manifest['wall_clock_seconds']}s "
          f"load={manifest['model_load_seconds']}s "
          f"infer={manifest['inference_seconds']}s "
          f"size={manifest['size_bytes']} cost=${manifest['approx_cost_usd']}")
    print("\nManually judge PASS criteria: ~1 boy + 1 girl, visually "
          "recognizable as Subaru (messy black hair, tracksuit) + "
          "Anastasia (long purple hair, white fur-hat dress), no crowd/"
          "duplicates, usable cover composition. If it still fails "
          "character identity, STOP generating more images - the next "
          "lever is LoRA or reference/IP-Adapter conditioning, not more "
          "prompt iteration. Do not publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
