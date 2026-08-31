#!/usr/bin/env python3
"""Real Beam Cloud Hy-MT2 translation benchmark - a NON-Vietnamese sample,
never the already-Vietnamese Re:Zero DRAFT content.

Reads BEAM_TOKEN from this process's own environment at execution time.
Never printed/logged. Run after deploying (see beam_apps/translation_hymt2_app.py
docstring) and after `scripts/beam_setup_check.py` reports clean:

    .venv\\Scripts\\python.exe scripts\\beam_translation_benchmark.py \\
        --endpoint-url <beam vllm endpoint url> --model tencent/Hy-MT2-1.8B

7B IS GATED, NOT DEFAULT: `--model` has NO default and REQUIRES an
explicit `tencent/Hy-MT2-7B` value - nothing here silently prefers or
falls back to the bigger model. Per this mission's own instruction, 7B is
ONLY the next real benchmark to try if a real 1.8B run shows the smaller
model's quality is insufficient - see beam_apps/translation_hymt2_app.py's
own "7B IS GATED" docstring section.

Uses the ALREADY-BUILT, ALREADY-TESTED `TranslationService` end to end
(create_project -> create_job -> poll -> read translated_chapters) with a
REAL provider registry pointed at the deployed Hy-MT2 endpoint via the
EXISTING TRANSLATION_BASE_URL/TRANSLATION_API_KEY/TRANSLATION_MODEL
mechanism (confirmed working via a fixture test in
docs/reports/self-hosted-translation-provider-2026-08-31.md) - no new
translation code, only real env-var wiring plus measurement.
`quality_mode="nhanh"` is used deliberately (translator pass ONLY, no
editor/QA passes - see `_VAI_TRO_THEO_CHE_DO` in server/translation_service.py)
so EXACTLY ONE real provider call happens per job, keeping the token-usage
reading below (`registry.get("custom").provider.last_usage`) unambiguous.

COLD vs WARM (this script makes exactly TWO real GPU calls, once each - no
more, no less, mirroring scripts/beam_cover_benchmark.py's cold-then-warm
design exactly): Beam's `VLLM` integration serves the model as a
persistent OpenAI-compatible chat-completions server process per
container (confirmed real via docs.beam.cloud/v2/reference/py-sdk.md - see
beam_apps/translation_hymt2_app.py's own docstring for the full citation),
so call 1 is whatever state the container is actually in (cold if no
recent traffic, warm if it is) and call 2 happens immediately after and
should hit the SAME still-warm container. Each call runs through the
FULL real TranslationService pipeline (project create -> job -> chunking
-> provider call -> store) as two INDEPENDENT projects with the same
sample text, so the real end-to-end path (not just the raw HTTP call) is
exercised twice.

METADATA DIFFERENCE FROM scripts/beam_cover_benchmark.py (real, not an
oversight): `beam_apps/cover_illustrious_app.py` is a hand-rolled
`@endpoint` that returns a CUSTOM JSON payload including
`model_load_seconds`/`inference_seconds` it measures itself.
`beam_apps/translation_hymt2_app.py` instead uses Beam's generic `VLLM`
integration, which serves a STANDARD OpenAI-compatible
`/v1/chat/completions` response - there is no per-request
load/inference-time breakdown in that response shape, only a standard
`usage` object (prompt_tokens/completion_tokens). This script therefore
reports real wall_seconds (measured here) and real token counts (from
`usage`, where the endpoint returns it), but leaves
model_load_seconds/inference_seconds as `None` rather than inventing
numbers that don't exist in this response shape - see
`server/translation_domain.py::TranslationRunMetrics` for the same
Optional-field convention.

COST ESTIMATE - REAL RESEARCH FINDING (fetched 2026-09-01): unlike
`scripts/beam_cover_benchmark.py`'s RTX4090 rate (confirmed directly on
beam.cloud/pricing), Beam's OWN current public pricing page does NOT
publish a per-second rate for EITHER "T4" or "A10G" - cross-checked
against beam.cloud/pricing itself plus two independent third-party
aggregators (computestacker.com, cloudgpuprices.com), all agreeing T4/A10G
are absent from the current serverless rate table. A third aggregator
(gputracker.dev) does list numbers, but they don't match Beam's own
precise per-second billing pattern seen elsewhere and could not be
confirmed on Beam's own site - printed below, but labeled UNVERIFIED,
THIRD-PARTY, NOT a Beam-published rate. The real, authoritative cost is
whatever Beam's own dashboard/invoice reports after this run - check that,
don't trust this number.

Sample text is a SHORT, SELF-AUTHORED (not scraped, not copyrighted)
English paragraph written in an anime-fanfic style, deliberately
containing: a named character, a pronoun-heavy exchange, one line of
dialogue, and one piece of setting/terminology - enough surface area to
evaluate faithfulness/naturalness/name-and-pronoun consistency/dialogue
quality per Mission G's own evaluation checklist, without depending on
any acquired/rights-sensitive content for a purely technical benchmark.
(Additional fanfic-style samples - dialogue-heavy, named-character-with-
honorific, idiom, longer-passage-near-context-boundary - exist for
LOCAL/MOCKED unit testing ONLY, see server/tests/test_translation_domain.py;
they are deliberately NOT sent to a real model here.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.adapters import MockMetadataStore  # noqa: E402
from server.translation_domain import (  # noqa: E402
    TranslationRunMetrics, build_translation_run_metrics, detect_source_language,
)
from server.translation_provider_registry import build_provider_registry  # noqa: E402
from server.translation_service import TranslationService  # noqa: E402
from server.translation_store import MockTranslationStore  # noqa: E402

TOKEN_ENV_VAR = "BEAM_TOKEN"

#: gpu= tier each model is actually deployed on
#: (beam_apps/translation_hymt2_app.py) - used ONLY to pick which
#: (unverified) rate to print below, not for any deploy/config decision.
MODEL_TO_GPU_TIER = {
    "tencent/Hy-MT2-1.8B": "T4",
    "tencent/Hy-MT2-7B": "A10G",
}

# UNVERIFIED, THIRD-PARTY rates (gputracker.dev, fetched 2026-09-01) - NOT
# confirmed on beam.cloud/pricing itself, which currently does not list a
# T4/A10G rate at all (see module docstring "COST ESTIMATE" section for
# the full citation). Kept ONLY so the printed report has a rough order-
# of-magnitude figure; the real charge is whatever Beam's own
# dashboard/invoice shows for this run.
GPU_HOURLY_RATE_USD_UNVERIFIED_THIRD_PARTY = {
    "T4": 0.310,
    "A10G": 1.10,
}

BENCHMARK_SAMPLE_EN = """\
Kaito had never liked the sound of rain against a dormitory window, but \
tonight it felt almost deliberate, like the sky itself was stalling for \
time.

"You're not actually going to fight him tomorrow, are you?" Mei asked, \
arms crossed, refusing to look away from him.

"I don't have a choice," he said. "If I don't accept the duel, the whole \
academy will think the Ashfall Blade chose a coward to carry it."

She flinched at the name of the sword - everyone did. Three centuries of \
half-true legend had a way of doing that to people.

"Then I'm coming with you," Mei said, and for once her voice didn't shake \
at all.
"""


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _run_one_translation(
    label: str, svc: TranslationService, registry, model: str,
    poll_timeout_seconds: int,
) -> Optional[TranslationRunMetrics]:
    """Chay MOT lan dich THAT (mot project doc lap) qua toan bo pipeline
    TranslationService that - tra ve None neu job khong hoan thanh (loi
    that, khong phai uoc luong)."""
    print(f"\n--- {label} call ---")
    custom = registry.get("custom")

    t0 = time.monotonic()
    project = svc.create_project(
        owner_id="beam_benchmark",
        title=f"Beam Hy-MT2 benchmark ({label}, non-VN sample)",
        source_text=BENCHMARK_SAMPLE_EN, quality_mode="nhanh")
    print(f"project_id={project.project_id} "
          f"detected_source_language={project.source_language!r} "
          f"source_text_hash={project.source_text_hash[:16]}")

    job = svc.create_job(project.project_id, "beam_benchmark")
    print(f"job_id={job.job_id} - polling...")

    deadline = time.time() + poll_timeout_seconds
    final_job = job
    while time.time() < deadline:
        final_job = svc.get_job(job.job_id, "beam_benchmark")
        print(f"  status={final_job.status.value}")
        if final_job.status.value in ("completed", "failed"):
            break
        time.sleep(5)
    wall_seconds = time.monotonic() - t0

    if final_job.status.value != "completed":
        print(f"\nNOT completed after {poll_timeout_seconds}s "
              f"(status={final_job.status.value}) - real error, not estimated:",
              file=sys.stderr)
        print(f"  {getattr(final_job, 'error_message', '') or final_job.error}",
              file=sys.stderr)
        return None

    project = svc.get_project(project.project_id, "beam_benchmark")
    translated = project.translated_chapters[0] if project.translated_chapters else ""

    #: Doc duoc VI quality_mode="nhanh" -> DUNG MOT lan goi provider ("custom")
    #: cho toan bo job nay (1 chuong, 1 pass "translator") - gia tri con lai
    #: tren `custom.provider` NGAY SAU KHI job hoan thanh chinh la usage cua
    #: LAN GOI DUY NHAT do, khong bi lan voi bat ky lan goi nao khac.
    usage = getattr(custom.provider, "last_usage", None) if custom else None
    source_tokens = (usage or {}).get("input_tokens")
    translated_tokens = (usage or {}).get("output_tokens")

    metrics = build_translation_run_metrics(
        source_text=BENCHMARK_SAMPLE_EN, translated_text=translated,
        source_language=project.source_language, target_language="vi",
        model_id=model, wall_seconds=wall_seconds,
        source_tokens=source_tokens, translated_tokens=translated_tokens)

    print(f"wall_seconds: {metrics.wall_seconds:.2f}")
    print(f"source_chars: {metrics.source_chars}  "
          f"translated_chars: {metrics.translated_chars}")
    if source_tokens is not None or translated_tokens is not None:
        print(f"source_tokens: {source_tokens}  translated_tokens: {translated_tokens}")
    else:
        print("tokens: not returned by this endpoint response (usage absent)")
    cps = metrics.chars_per_second()
    if cps is not None:
        print(f"generation_speed: {cps:.1f} chars/sec")
    print(f"possibly_truncated: {metrics.possibly_truncated}")
    print(f"\n--- {label} TRANSLATED (Vietnamese, full) ---\n{translated}")
    return metrics


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint-url", required=True,
                   help="Beam vLLM endpoint URL from `beam deploy` output, "
                        "WITHOUT trailing /v1 (this script appends it)")
    p.add_argument("--model", required=True,
                   choices=["tencent/Hy-MT2-1.8B", "tencent/Hy-MT2-7B"],
                   help="NO default on purpose - 7B must be requested "
                        "explicitly, never silently used (see module "
                        "docstring '7B IS GATED')")
    p.add_argument("--poll-timeout-seconds", type=int, default=600)
    p.add_argument("--out-prefix", default="beam_translation_hymt2_benchmark",
                   help="Manifest saved to <prefix>_manifest.json")
    a = p.parse_args()

    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        print(f"BLOCKED: {TOKEN_ENV_VAR} is not set in this process's environment.",
              file=sys.stderr)
        return 2

    detected = detect_source_language(BENCHMARK_SAMPLE_EN)
    print(f"detect_source_language() on the real benchmark sample -> {detected!r} "
          f"(expected 'en')")
    print(f"\nSOURCE (English, full):\n{BENCHMARK_SAMPLE_EN}")
    print(f"source_sha256: {_sha256(BENCHMARK_SAMPLE_EN)}")

    # Real provider registry pointed at the REAL deployed endpoint - env vars
    # only, the token never touches argv/logs. TRANSLATION_ALLOW_PAID_PROVIDER
    # stays default (only matters for provider entries NOT marked free_tier;
    # TRANSLATION_CUSTOM_PROVIDER_FREE opts this self-hosted one in - see
    # translation_provider_registry.py for that gate's real logic).
    os.environ["TRANSLATION_BASE_URL"] = a.endpoint_url.rstrip("/") + "/v1"
    os.environ["TRANSLATION_API_KEY"] = token
    os.environ["TRANSLATION_MODEL"] = a.model
    os.environ.setdefault("TRANSLATION_CUSTOM_PROVIDER_FREE", "true")

    registry = build_provider_registry()
    if not registry.get("custom"):
        print("BLOCKED: registry has no 'custom' provider - check "
              "TRANSLATION_BASE_URL/API_KEY/MODEL/CUSTOM_PROVIDER_FREE env "
              "wiring above.", file=sys.stderr)
        return 2
    svc = TranslationService(
        store=MockTranslationStore(), novel_store=MockMetadataStore(),
        registry=registry)

    print("\nThis script makes exactly TWO real GPU calls (cold, then an "
          "immediate warm call against the same deployment) - re-running "
          "it means two MORE billed translation calls.")

    cold = _run_one_translation("COLD", svc, registry, a.model, a.poll_timeout_seconds)
    warm = _run_one_translation("WARM", svc, registry, a.model, a.poll_timeout_seconds)

    if cold is None or warm is None:
        print("\nAt least one call did not complete - see errors above. "
              "Not printing a summary for a failed run.", file=sys.stderr)
        return 1

    gpu_tier = MODEL_TO_GPU_TIER.get(a.model, "")
    rate = GPU_HOURLY_RATE_USD_UNVERIFIED_THIRD_PARTY.get(gpu_tier)
    manifest = {
        "model": a.model,
        "endpoint_url": a.endpoint_url,
        "detected_source_language": detected,
        "source_sha256": _sha256(BENCHMARK_SAMPLE_EN),
        "cold": cold.to_dict(),
        "warm": warm.to_dict(),
        "cost_estimate_usd": {
            "gpu_tier": gpu_tier,
            "rate_usd_per_hour": rate,
            "rate_source": (
                "UNVERIFIED THIRD-PARTY (gputracker.dev, fetched 2026-09-01) "
                "- Beam's own beam.cloud/pricing page does NOT currently "
                "list a T4/A10G rate; this is a rough estimate only, not a "
                "Beam-published figure. See module docstring."),
            "cold_estimate": (
                round(cold.wall_seconds * rate / 3600, 5) if rate else None),
            "warm_estimate": (
                round(warm.wall_seconds * rate / 3600, 5) if rate else None),
            "authoritative_source": (
                "Check Beam's own dashboard/invoice for the real charge "
                "of this run - do not trust the estimate above."),
        },
    }
    manifest_path = Path(f"{a.out_prefix}_manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n=== SUMMARY (real measurements; cost is an UNVERIFIED "
          f"third-party rate estimate, never treat as measured) ===")
    print(f"manifest saved: {manifest_path}")
    for label, m in (("cold", cold), ("warm", warm)):
        cps = m.chars_per_second()
        est = (manifest["cost_estimate_usd"]["cold_estimate"] if label == "cold"
               else manifest["cost_estimate_usd"]["warm_estimate"])
        print(f"[{label}] wall={m.wall_seconds:.2f}s "
              f"chars_in={m.source_chars} chars_out={m.translated_chars} "
              f"speed={f'{cps:.1f}' if cps else 'n/a'} chars/s "
              f"possibly_truncated={m.possibly_truncated} "
              f"cost_est=${est if est is not None else 'n/a'}")

    print("\n=== MANUAL EVALUATION CHECKLIST (this script cannot judge "
          "translation quality itself - a human must read both texts "
          "above/in the manifest and check each item) ===")
    print("  [ ] Proper noun preservation: 'Kaito', 'Mei', and 'Ashfall "
          "Blade' should read as names/a title, not be translated as "
          "common words or altered between the two runs.")
    print("  [ ] Dialogue preservation: all THREE quoted lines of dialogue "
          "must be present and clearly rendered as dialogue in the "
          "Vietnamese output (not merged into narration or dropped).")
    print("  [ ] Obvious omissions/repetitions: compare translated_chars "
          "against source_chars above and possibly_truncated - also "
          "visually scan for repeated phrases/looping text, a common "
          "small-model failure mode not caught by length alone.")
    print("  [ ] Faithfulness/naturalness: does the Vietnamese read as "
          "natural prose, not a word-for-word gloss of the English?")
    print("  [ ] Cold vs warm consistency: cold and warm outputs above "
          "should be substantively similar in meaning (temperature=0.3 "
          "means near-deterministic, not byte-identical).")
    print("\nDo not publish this output anywhere - it is a technical "
          "benchmark only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
