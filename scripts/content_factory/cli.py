"""
Content Factory Unified CLI — scripts/content_factory/cli.py (PR-D).

Usage:
  python -m scripts.content_factory run <work_id> [options]

Examples:
  python -m scripts.content_factory run 136586 --through qa
  python -m scripts.content_factory run 156206 --intake --crawl --classify --translate --qa --cover --tts
  python -m scripts.content_factory run 136586 --dry-run
  python -m scripts.content_factory run 136586 --promote (Requires explicit confirmation)

Safety:
  --promote is MANDATORY for production promotion. It NEVER happens by default.
  --dry-run guarantees zero Appwrite mutations, zero R2 writes, zero production audio registration.
  --force-stage <stage> never forces promotion.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.content_factory.unified_pipeline import (
    PipelineStage,
    PipelineState,
    STAGE_ORDER,
    UnifiedContentPipeline,
)


def parse_stage_name(name: str) -> PipelineStage:
    clean = name.strip().lower()
    for s in PipelineStage:
        if s.value == clean:
            return s
    # Map common aliases
    alias_map = {
        "trans": PipelineStage.TRANSLATE,
        "quality": PipelineStage.QA,
        "diff": PipelineStage.PACKAGE,
        "prep": PipelineStage.PACKAGE,
    }
    if clean in alias_map:
        return alias_map[clean]
    valid = ", ".join(s.value for s in STAGE_ORDER)
    raise argparse.ArgumentTypeError(f"Invalid stage '{name}'. Valid stages: {valid}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.content_factory",
        description="Unified Content Factory CLI (PR-D)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: run
    p_run = subparsers.add_parser("run", help="Run the unified pipeline for a work")
    p_run.add_argument("work_id", help="Upstream work ID (e.g. 136586, 156206) or URL")
    p_run.add_argument("--platform", default="royalroad", help="Source platform (default: royalroad)")

    # Explicit stage flags
    p_run.add_argument("--intake", action="store_true", help="Run intake stage")
    p_run.add_argument("--crawl", action="store_true", help="Run crawl stage")
    p_run.add_argument("--classify", action="store_true", help="Run classify stage")
    p_run.add_argument("--translate", action="store_true", help="Run translate stage")
    p_run.add_argument("--qa", action="store_true", help="Run QA gate stage")
    p_run.add_argument("--cover", action="store_true", help="Run cover resolution stage")
    p_run.add_argument("--tts", action="store_true", help="Run TTS staging stage")
    p_run.add_argument("--package", action="store_true", help="Run package / production diff stage")

    # Range flags
    p_run.add_argument("--from", dest="from_stage", type=parse_stage_name, default=None, help="Start pipeline from stage")
    p_run.add_argument("--through", "--to", dest="through_stage", type=parse_stage_name, default=None, help="Stop pipeline after stage")

    # Flow & Safety flags
    p_run.add_argument("--resume", action="store_true", default=True, help="Resume from last completed checkpoint (default: True)")
    p_run.add_argument("--no-resume", action="store_false", dest="resume", help="Do not resume; evaluate from beginning")
    p_run.add_argument("--force-stage", type=parse_stage_name, action="append", default=[], help="Force re-run of a specific stage")
    p_run.add_argument("--dry-run", action="store_true", default=True, help="Dry run mode (default: True, zero mutation)")
    p_run.add_argument("--no-dry-run", action="store_false", dest="dry_run", help="Disable dry run mode")
    p_run.add_argument("--promote", action="store_true", default=False, help="Promote to production (MANDATORY flag for production mutations)")

    return parser


def resolve_stages(args: argparse.Namespace) -> List[PipelineStage]:
    # Check if explicit stage flags were provided
    explicit_stages: List[PipelineStage] = []
    if args.intake:
        explicit_stages.append(PipelineStage.INTAKE)
    if args.crawl:
        explicit_stages.append(PipelineStage.CRAWL)
    if args.classify:
        explicit_stages.append(PipelineStage.CLASSIFY)
    if args.translate:
        explicit_stages.append(PipelineStage.TRANSLATE)
    if args.qa:
        explicit_stages.append(PipelineStage.QA)
    if args.cover:
        explicit_stages.append(PipelineStage.COVER)
    if args.tts:
        explicit_stages.append(PipelineStage.TTS)
    if args.package:
        explicit_stages.append(PipelineStage.PACKAGE)

    if explicit_stages:
        stages = [s for s in STAGE_ORDER if s in explicit_stages]
    else:
        # Default is all stages up to package
        stages = [s for s in STAGE_ORDER if s != PipelineStage.PROMOTE]

    # Apply --from
    if args.from_stage:
        idx_from = STAGE_ORDER.index(args.from_stage)
        stages = [s for s in stages if STAGE_ORDER.index(s) >= idx_from]

    # Apply --through
    if args.through_stage:
        idx_through = STAGE_ORDER.index(args.through_stage)
        stages = [s for s in stages if STAGE_ORDER.index(s) <= idx_through]

    # Apply --promote
    if args.promote and PipelineStage.PROMOTE not in stages:
        stages.append(PipelineStage.PROMOTE)
    elif not args.promote and PipelineStage.PROMOTE in stages:
        stages.remove(PipelineStage.PROMOTE)

    return stages


def format_cli_output(
    work_id: str,
    platform: str,
    pipeline: UnifiedContentPipeline,
    results: dict,
) -> str:
    lines = []
    platform_label = "RoyalRoad" if platform == "royalroad" else platform.capitalize()
    work_label = f"RR{work_id}" if platform == "royalroad" and not str(work_id).startswith("RR") else str(work_id)

    lines.append(f"Work: {work_label}")
    lines.append(f"Source: {platform_label}")
    lines.append("")

    stage_display_names = {
        PipelineStage.CRAWL.value: "Crawl",
        PipelineStage.CLASSIFY.value: "Classify",
        PipelineStage.TRANSLATE.value: "Translate",
        PipelineStage.QA.value: "QA",
        PipelineStage.COVER.value: "Cover",
        PipelineStage.TTS.value: "TTS",
    }

    for st_val, name in stage_display_names.items():
        if st_val in results:
            res = results[st_val]
            status = res.status_label
            summary = res.summary
            lines.append(f"{name:<12}{status:<10}{summary}")

    # Production Diff section
    pkg_res = results.get(PipelineStage.PACKAGE.value)
    if pkg_res:
        lines.append("")
        lines.append("Production diff:")
        diff_status = pkg_res.data.get("diff_status", "NO CHANGES")
        lines.append(diff_status)

    lines.append("")
    # Final state banner
    curr_state = pipeline.checkpoint.current_state
    if curr_state == PipelineState.READY_FOR_PROMOTION.value or (pkg_res and pkg_res.passed):
        lines.append("READY_FOR_PROMOTION: NO_ACTION_REQUIRED")
    elif curr_state == PipelineState.PROMOTED.value:
        lines.append("PROMOTED: SUCCESS")
    else:
        lines.append(f"STATE: {curr_state}")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        # Safety check: --promote requires --no-dry-run
        if args.promote and args.dry_run:
            print("ERROR: --promote cannot be executed in --dry-run mode.", file=sys.stderr)
            print("To actually promote to production, pass both --promote and --no-dry-run.", file=sys.stderr)
            return 2

        stages = resolve_stages(args)
        force_set = set(args.force_stage) if args.force_stage else set()

        pipeline = UnifiedContentPipeline(
            work_id=args.work_id,
            platform=args.platform,
            dry_run=args.dry_run,
            resume=args.resume,
            force_stages=force_set,
        )

        exec_res = pipeline.execute(stages=stages, promote=args.promote)
        output_text = format_cli_output(args.work_id, args.platform, pipeline, exec_res["results"])
        print(output_text)

        return 0 if exec_res["all_passed"] else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
