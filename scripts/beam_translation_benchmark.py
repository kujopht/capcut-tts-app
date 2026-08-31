#!/usr/bin/env python3
"""Real Beam Cloud Hy-MT2 translation benchmark - a NON-Vietnamese sample,
never the already-Vietnamese Re:Zero DRAFT content.

Reads BEAM_TOKEN from this process's own environment at execution time.
Never printed/logged. Run after deploying (see beam_apps/translation_hymt2_app.py
docstring) and after `scripts/beam_setup_check.py` reports clean:

    .venv\\Scripts\\python.exe scripts\\beam_translation_benchmark.py \\
        --endpoint-url <beam vllm endpoint url> --model tencent/Hy-MT2-7B

Uses the ALREADY-BUILT, ALREADY-TESTED TranslationService end to end
(create_project -> create_job -> poll -> read translated_chapters) with a
REAL provider registry pointed at the deployed Hy-MT2 endpoint via the
EXISTING TRANSLATION_BASE_URL/TRANSLATION_API_KEY/TRANSLATION_MODEL
mechanism (confirmed working via a fixture test in
docs/reports/self-hosted-translation-provider-2026-08-31.md) - no new
translation code, only real env-var wiring plus measurement.

Sample text is a SHORT, SELF-AUTHORED (not scraped, not copyrighted)
English paragraph written in an anime-fanfic style, deliberately
containing: a named character, a pronoun-heavy exchange, one line of
dialogue, and one piece of setting/terminology - enough surface area to
evaluate faithfulness/naturalness/name-and-pronoun consistency/dialogue
quality per Mission G's own evaluation checklist, without depending on
any acquired/rights-sensitive content for a purely technical benchmark.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.adapters import MockMetadataStore  # noqa: E402
from server.translation_domain import detect_source_language  # noqa: E402
from server.translation_provider_registry import build_provider_registry  # noqa: E402
from server.translation_service import TranslationService  # noqa: E402
from server.translation_store import MockTranslationStore  # noqa: E402

TOKEN_ENV_VAR = "BEAM_TOKEN"

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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint-url", required=True,
                   help="Beam vLLM endpoint URL from `beam deploy` output, "
                        "WITHOUT trailing /v1 (this script appends it)")
    p.add_argument("--model", required=True,
                   choices=["tencent/Hy-MT2-1.8B", "tencent/Hy-MT2-7B"])
    p.add_argument("--poll-timeout-seconds", type=int, default=600)
    a = p.parse_args()

    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        print(f"BLOCKED: {TOKEN_ENV_VAR} is not set in this process's environment.",
              file=sys.stderr)
        return 2

    detected = detect_source_language(BENCHMARK_SAMPLE_EN)
    print(f"detect_source_language() on the real benchmark sample -> {detected!r} "
          f"(expected 'en')")

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
    svc = TranslationService(
        store=MockTranslationStore(), novel_store=MockMetadataStore(),
        registry=registry)

    t0 = time.monotonic()
    project = svc.create_project(
        owner_id="beam_benchmark", title="Beam Hy-MT2 benchmark (non-VN sample)",
        source_text=BENCHMARK_SAMPLE_EN, quality_mode="can_bang")
    print(f"project_id={project.project_id} "
          f"detected_source_language={project.source_language!r} "
          f"source_text_hash={project.source_text_hash[:16]}")

    job = svc.create_job(project.project_id, "beam_benchmark")
    print(f"job_id={job.job_id} - polling...")

    deadline = time.time() + a.poll_timeout_seconds
    final_job = job
    while time.time() < deadline:
        final_job = svc.get_job(job.job_id, "beam_benchmark")
        print(f"  status={final_job.status.value}")
        if final_job.status.value in ("completed", "failed"):
            break
        time.sleep(5)
    t1 = time.monotonic()

    if final_job.status.value != "completed":
        print(f"\nNOT completed after {a.poll_timeout_seconds}s "
              f"(status={final_job.status.value}) - real error, not estimated:")
        print(f"  {getattr(final_job, 'error_message', '')}")
        return 1

    project = svc.get_project(project.project_id, "beam_benchmark")
    translated = project.translated_chapters[0] if project.translated_chapters else ""

    print(f"\n=== RESULT (real measurement, not an estimate) ===")
    print(f"end_to_end_seconds: {t1 - t0:.2f}")
    print(f"model: {a.model}")
    print(f"source_chars: {len(BENCHMARK_SAMPLE_EN)}")
    print(f"translated_chars: {len(translated)}")
    print(f"\n--- SOURCE (English) ---\n{BENCHMARK_SAMPLE_EN}")
    print(f"--- TRANSLATED (Vietnamese) ---\n{translated}")
    print("\nManually evaluate against the checklist: faithfulness, omissions, "
          "hallucinations, naturalness, name consistency (Kaito/Mei kept as "
          "names, not translated), pronoun consistency, dialogue quality, "
          "terminology (\"Ashfall Blade\").")
    return 0


if __name__ == "__main__":
    sys.exit(main())
