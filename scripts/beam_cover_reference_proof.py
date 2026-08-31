#!/usr/bin/env python3
"""Real Beam Cloud REFERENCE-CONDITIONED cover PROOF - EXACTLY ONE real
GPU call, testing whether IP-Adapter reference conditioning (see
beam_apps/cover_illustrious_app.py's own docstring for the real research
behind this choice) fixes character identity where prompt-only text
descriptors did not: 3 refinement candidates had good composition but
wrong character count/identity, and the identity-descriptor layer's own
proof still produced 2 males + 1 female with incorrect Anastasia
identity. STOP prompt-only iteration - this is a different mechanism.

REQUIRES the operator's OWN reference images - this script does not
fetch, embed, or assume any specific image. Place two real reference
images somewhere on disk (a face-forward or 3/4 view works best for the
face-cropped IP-Adapter variant used server-side) and pass their paths:

    .venv\\Scripts\\python.exe scripts\\beam_cover_reference_proof.py \\
        --endpoint-url <url> \\
        --primary-reference-image path\\to\\subaru.png \\
        --primary-reference-source "operator-provided, <describe where from>" \\
        --secondary-reference-image path\\to\\anastasia.png \\
        --secondary-reference-source "operator-provided, <describe where from>"

Reads BEAM_TOKEN from this process's own environment at execution time.
Never printed/logged.

REQUIRES REDEPLOY FIRST: this script sends
primary_reference_images_base64/secondary_reference_images_base64/
reference_strength - new optional kwargs on generate(). A container still
running the pre-reference-conditioning build will 500/error on these
(same class of failure as the real seed incident, task
04d22fcf-55f3-4f5e-acd3-337de6ff4432) - always confirm
`git log --oneline -1` shows the reference-conditioning commit BEFORE
`beam deploy`, matching that incident's actual root cause (a stale
container, not a code defect) rather than repeating it.

Registers the supplied images into a REAL CharacterIdentityRegistry
(server/character_identity.py) - not a side-channel - so the reference
fields (reference_images/reference_strength/reference_source) are
genuinely exercised (each as a one-element list here - the schema
supports more per character for future multi-image averaging, see
character_identity.py's own docstring, but this v1 proof uses exactly
one canonical image per character), and the SAME identity-aware
CoverPromptBuilder prompt from the prior mission is reused (reference conditioning
AUGMENTS text descriptors, it does not replace them).

This script makes EXACTLY ONE real GPU call (seed=20260905, distinct from
every other seed already used this mission), no CLI flag to raise that.

PASS criteria (manual, visual - this script cannot judge the image
itself): approximately exactly 2 visible characters, Subaru recognizable,
Anastasia recognizable, identities not blended, no duplicate Subaru,
usable cover composition. If this still fails, per instruction: STOP and
report which is the smaller next step - regional conditioning (already
attempted here via left/right masks; if masks under-separated the two
identities, tightening split_fraction/overlap_fraction in
beam_apps/cover_illustrious_logic.py::build_left_right_masks, or trying
non-overlapping masks, is the next code-level lever) vs. character LoRA
(a materially bigger lift - training/hosting a LoRA per character,
deferred by instruction so far).
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

from server.character_identity import (  # noqa: E402
    CharacterIdentityRegistry, CharacterVisualIdentity,
)
from server.cover_pipeline import CoverGenerationRequest, CoverPromptBuilder  # noqa: E402

TOKEN_ENV_VAR = "BEAM_TOKEN"

# Real published RTX4090 on-demand rate - see beam_cover_benchmark.py for
# the same constant/citation. A rate, not a benchmark measurement.
RTX4090_PER_SECOND_USD = 0.000191667

#: One fixed seed - reproducible, distinct from every other seed already
#: used this mission (20260901-903 refinement, 20260904 identity proof).
SEED = 20260905


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint-url", required=True,
                   help="Beam endpoint URL (cover-illustrious, ALREADY "
                        "redeployed with reference-conditioning support)")
    p.add_argument("--primary-reference-image", required=True,
                   help="Local path to a real reference image of Natsuki Subaru")
    p.add_argument("--primary-reference-source", default="operator-provided",
                   help="Provenance note for the primary reference image")
    p.add_argument("--secondary-reference-image", required=True,
                   help="Local path to a real reference image of Anastasia Hoshin")
    p.add_argument("--secondary-reference-source", default="operator-provided",
                   help="Provenance note for the secondary reference image")
    p.add_argument("--reference-strength", type=float, default=0.6,
                   help="IP-Adapter scale (0.5-0.8 typical per diffusers docs)")
    p.add_argument("--out-prefix", default="rezero_cover_reference_proof")
    p.add_argument("--timeout-seconds", type=float, default=300.0)
    a = p.parse_args()

    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        print(f"BLOCKED: {TOKEN_ENV_VAR} is not set in this process's environment.",
              file=sys.stderr)
        return 2

    primary_path = Path(a.primary_reference_image)
    secondary_path = Path(a.secondary_reference_image)
    if not primary_path.is_file():
        print(f"BLOCKED: --primary-reference-image not found: {primary_path}",
              file=sys.stderr)
        return 2
    if not secondary_path.is_file():
        print(f"BLOCKED: --secondary-reference-image not found: {secondary_path}",
              file=sys.stderr)
        return 2

    # Real, provider-neutral registry - reference fields are genuinely
    # used, not a side-channel (see server/character_identity.py).
    registry = CharacterIdentityRegistry()
    registry.register(CharacterVisualIdentity(
        canonical_name="Natsuki Subaru", fandom="Re:Zero",
        aliases=["Subaru Natsuki", "Subaru"], gender_presentation="male",
        hair_description="short messy black hair, swept back and unkempt",
        eye_description="sharp dark brown eyes with an intense gaze",
        outfit_description=(
            "black tracksuit jacket zipped up with stand-up collar over a "
            "black t-shirt, deep-grey tracksuit pants with an orange "
            "stripe down the side, black sneakers with orange laces"),
        distinctive_traits=["athletic build", "determined expression"],
        negative_traits=["blonde hair", "glasses", "formal suit"],
        source_provenance="rezero.fandom.com/wiki/Natsuki_Subaru",
        reference_images=[str(primary_path)], reference_strength=a.reference_strength,
        reference_source=a.primary_reference_source,
    ))
    registry.register(CharacterVisualIdentity(
        canonical_name="Anastasia Hoshin", fandom="Re:Zero",
        aliases=["Anastasia", "Hoshin Anastasia"], gender_presentation="female",
        hair_description="long wavy purple hair reaching her hips",
        eye_description="blue-green eyes, gentle relaxed expression",
        outfit_description=(
            "form-fitting ankle-length long-sleeved white dress, tall "
            "white fluffy fur ushanka-style hat, white scarf, white "
            "high-heeled boots with pale pink soles"),
        distinctive_traits=[
            "yellow star-shaped hairpin", "small teal pendant necklace",
            "petite doll-like figure"],
        negative_traits=["short hair", "armor", "modern clothing"],
        source_provenance="rezero.fandom.com/wiki/Anastasia_Hoshin",
        reference_images=[str(secondary_path)], reference_strength=a.reference_strength,
        reference_source=a.secondary_reference_source,
    ))

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
        primary_character="Natsuki Subaru",
        secondary_character="Anastasia Hoshin",
    )
    prompt = CoverPromptBuilder.build_prompt(req, registry)
    primary_identity = registry.lookup("Re:Zero", "Natsuki Subaru")
    secondary_identity = registry.lookup("Re:Zero", "Anastasia Hoshin")

    print("Prompt (text descriptors, unchanged from the identity-layer "
          "mission - reference conditioning AUGMENTS this, not replaces):")
    print(f"  {prompt}")
    print(f"\nReference images:")
    print(f"  primary:   {primary_path} (source: {primary_identity.reference_source})")
    print(f"  secondary: {secondary_path} (source: {secondary_identity.reference_source})")
    print(f"  reference_strength: {a.reference_strength}")
    print(f"\nThis script makes EXACTLY ONE real GPU call (seed={SEED}) - "
          f"re-running it means one MORE billed image.")

    primary_b64 = base64.b64encode(primary_path.read_bytes()).decode("ascii")
    secondary_b64 = base64.b64encode(secondary_path.read_bytes()).decode("ascii")

    client = httpx.Client(
        base_url=a.endpoint_url.rstrip("/"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=a.timeout_seconds,
    )
    t0 = time.monotonic()
    resp = client.post("", json={
        "prompt": prompt,
        "seed": SEED,
        "primary_reference_images_base64": [primary_b64],
        "secondary_reference_images_base64": [secondary_b64],
        "reference_strength": a.reference_strength,
    })
    wall_seconds = time.monotonic() - t0
    if resp.status_code != 200:
        print(f"FAILED (real error, not an estimate): HTTP {resp.status_code}: "
              f"{resp.text[:500]}", file=sys.stderr)
        print("\nIf this looks like an 'unexpected keyword argument' error, "
              "the container is still running a pre-reference-conditioning "
              "build - redeploy first (see this script's own docstring).",
              file=sys.stderr)
        return 1

    data = resp.json()
    png_bytes = base64.b64decode(data["image_base64"])
    out_path = Path(f"{a.out_prefix}.png")
    out_path.write_bytes(png_bytes)

    model_load_seconds = float(data.get("model_load_seconds", 0.0))
    inference_seconds = float(data.get("inference_seconds", 0.0))
    returned_seed = data.get("seed", -1)
    reference_conditioned = data.get("reference_conditioned", False)
    size_bytes = int(data.get("size_bytes", len(png_bytes)))
    est_cost = wall_seconds * RTX4090_PER_SECOND_USD

    manifest = {
        "seed": returned_seed,
        "reference_conditioned": reference_conditioned,
        "reference_strength": a.reference_strength,
        "prompt": prompt,
        "primary_reference_image": str(primary_path),
        "primary_reference_source": a.primary_reference_source,
        "secondary_reference_image": str(secondary_path),
        "secondary_reference_source": a.secondary_reference_source,
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

    if not reference_conditioned:
        print("\nWARNING: response says reference_conditioned=False - the "
              "endpoint did not actually apply reference conditioning "
              "(check that both base64 fields were non-empty and that "
              "the deployed build actually has this feature).",
              file=sys.stderr)

    print(f"\n=== RESULT ===")
    print(f"saved: {out_path}")
    print(f"manifest: {manifest_path}")
    print(f"seed={returned_seed} reference_conditioned={reference_conditioned} "
          f"wall={manifest['wall_clock_seconds']}s "
          f"load={manifest['model_load_seconds']}s "
          f"infer={manifest['inference_seconds']}s "
          f"size={manifest['size_bytes']} cost=${manifest['approx_cost_usd']}")
    print("\nManually judge PASS criteria: ~2 visible characters, Subaru "
          "recognizable, Anastasia recognizable, identities NOT blended, "
          "no duplicate Subaru, usable cover composition. If this still "
          "fails, STOP - report which is the smaller next step: tighten "
          "the regional mask split (adjust split_fraction/overlap_fraction "
          "in beam_apps/cover_illustrious_logic.py::build_left_right_masks) "
          "vs. character LoRA (a materially bigger lift). Do not publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
