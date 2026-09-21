"""Content Factory v2 — Novel Cover Generation & Lifecycle CLI.

Unified CLI wrapping scripts.content_factory.cover_resolver:
1. Generation: Beam Cloud Animagine XL 4.0 serverless generation (2:3 vertical book art).
2. Fallback: High-resolution procedural typography & fandom emblem cover generation.
3. Source Reuse: Download and stage original RoyalRoad/source cover with attribution.
4. Staging & Gating: Strictly isolates output to raw_spool/staged_covers/<work_id>/
5. Approval & Rollback: Explicit operator confirmation, rollback backup, optional R2/Appwrite promotion.

Usage:
  # 1. Generate candidate cover (2:3 vertical book art)
  python scripts/content_factory/novel_cover_cli.py generate --work-id 136586 --title "Naruto: The Butterfly Effect" --fandom "Naruto" --seed 42

  # 2. Check cover status
  python scripts/content_factory/novel_cover_cli.py status --work-id 136586

  # 3. Approve staged candidate
  python scripts/content_factory/novel_cover_cli.py approve --work-id 136586

  # 4. Reject candidate
  python scripts/content_factory/novel_cover_cli.py reject --work-id 136586 --reason "Subject not matching synopsis"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import List

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from scripts.content_factory.cover_resolver import (
    STAGED_COVERS_DIR,
    APPROVED_COVERS_DIR,
    stage_beam_cover,
    stage_source_cover,
    approve_cover,
    reject_cover,
    get_cover_state,
    build_cover_prompt,
)


def cmd_generate(args: argparse.Namespace) -> int:
    work_id = args.work_id.strip()
    title = args.title.strip()
    fandom = (args.fandom or "").strip()
    genres = [g.strip() for g in args.genres.split(",") if g.strip()] if args.genres else []

    if args.source_url:
        print(f"[CoverCLI] Staging source cover from URL: {args.source_url}")
        ok, meta, msg = stage_source_cover(
            work_id=work_id,
            source_url=args.source_url.strip(),
            title=title,
            fandom=fandom,
            attribution=args.source_attribution or "Source cover",
        )
    else:
        print(f"[CoverCLI] Generating cover via Cover Resolver (Beam Cloud / Procedural fallback)...")
        print(f"[CoverCLI] Title: {title} | Fandom: {fandom} | Seed: {args.seed or 'Random'}")
        ok, meta, msg = stage_beam_cover(
            work_id=work_id,
            title=title,
            fandom=fandom,
            genres=genres,
            synopsis=args.synopsis or "",
            character_cues=args.character_cues or "",
            seed=args.seed if args.seed and args.seed > 0 else None,
            aspect_ratio=args.aspect_ratio or "2:3",
            typography_mode=args.typography_mode,
            timeout_seconds=args.timeout or 120.0,
        )

    if ok:
        print(f"[CoverCLI] ✅ {msg}")
        print(f"[CoverCLI] Provider: {meta.get('provider')} | Seed: {meta.get('seed')}")
        return 0
    else:
        print(f"[CoverCLI] ❌ Failed to stage cover: {msg}")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    work_id = args.work_id.strip()
    state = get_cover_state(work_id)
    print(f"\n=== COVER STATUS: {work_id} ===")
    print(f"  Status:         {state['status']}")
    print(f"  Has Staged:     {state['has_staged']} ({state.get('staged_path')})")
    print(f"  Has Approved:   {state['has_approved']} ({state.get('approved_path')})")
    print(f"  Provider:       {state.get('provider')}")
    print(f"  Seed:           {state.get('seed')}")
    print(f"  Has Rollback:   {state.get('has_rollback')}")
    if state.get("prompt"):
        print(f"  Prompt:         {state['prompt'][:100]}...")
    print("===============================\n")
    return 0


def cmd_list_staged(args: argparse.Namespace) -> int:
    work_id = args.work_id.strip()
    staged_dir = STAGED_COVERS_DIR / work_id
    if not staged_dir.exists():
        print(f"[CoverCLI] No staged directory found for work {work_id}")
        return 0

    candidates = sorted(list(staged_dir.glob("candidate_*.jpg")))
    active = staged_dir / "active_staged.jpg"
    print(f"[CoverCLI] Found {len(candidates)} candidate(s) for {work_id}:")
    for c in candidates:
        print(f"  - {c.name} ({c.stat().st_size // 1024} KB)")
    if active.exists():
        print(f"  * active_staged.jpg ({active.stat().st_size // 1024} KB)")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    work_id = args.work_id.strip()
    ok, msg, meta = approve_cover(
        work_id=work_id,
        upload_r2=args.upload_r2,
        update_appwrite=args.update_appwrite,
        confirm_replace=args.confirm_replace,
        operator=args.operator or "operator",
    )
    if ok:
        print(f"[CoverCLI] ✅ {msg}")
        return 0
    else:
        print(f"[CoverCLI] ⚠️ {msg}")
        return 1


def cmd_reject(args: argparse.Namespace) -> int:
    work_id = args.work_id.strip()
    ok, msg = reject_cover(work_id=work_id, reason=args.reason or "Rejected via CLI")
    if ok:
        print(f"[CoverCLI] ✅ {msg}")
        return 0
    else:
        print(f"[CoverCLI] ❌ {msg}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Content Factory v2 Cover Resolver CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate
    p_gen = subparsers.add_parser("generate", help="Generate or stage a novel cover")
    p_gen.add_argument("--work-id", required=True, help="Work or Novel ID (e.g. 136586 or nov_rr_156206)")
    p_gen.add_argument("--title", required=True, help="Novel title")
    p_gen.add_argument("--fandom", default="Fanfic", help="Novel fandom (e.g. Naruto)")
    p_gen.add_argument("--genres", default="", help="Comma-separated genres")
    p_gen.add_argument("--synopsis", default="", help="Short synopsis")
    p_gen.add_argument("--character-cues", default="", help="Visual character cues")
    p_gen.add_argument("--aspect-ratio", choices=["2:3", "16:9"], default="2:3", help="Aspect ratio")
    p_gen.add_argument("--seed", type=int, default=0, help="Random seed")
    p_gen.add_argument("--source-url", default="", help="Optional source cover URL to download")
    p_gen.add_argument("--source-attribution", default="", help="Source cover attribution note")
    p_gen.add_argument("--typography-mode", action="store_true", help="Enable title typography rendering")
    p_gen.add_argument("--timeout", type=float, default=120.0, help="Beam Cloud timeout in seconds")

    # status
    p_stat = subparsers.add_parser("status", help="Get cover status for a work")
    p_stat.add_argument("--work-id", required=True, help="Work or Novel ID")

    # list-staged
    p_list = subparsers.add_parser("list-staged", help="List staged cover files")
    p_list.add_argument("--work-id", required=True, help="Work or Novel ID")

    # approve
    p_app = subparsers.add_parser("approve", help="Approve active staged cover")
    p_app.add_argument("--work-id", required=True, help="Work or Novel ID")
    p_app.add_argument("--confirm-replace", action="store_true", help="Confirm overwriting an existing approved cover")
    p_app.add_argument("--upload-r2", action="store_true", help="Upload to Cloudflare R2")
    p_app.add_argument("--update-appwrite", action="store_true", help="Update Appwrite document")
    p_app.add_argument("--operator", default="operator", help="Operator name")

    # reject
    p_rej = subparsers.add_parser("reject", help="Reject active staged cover")
    p_rej.add_argument("--work-id", required=True, help="Work or Novel ID")
    p_rej.add_argument("--reason", default="", help="Rejection reason")

    args = parser.parse_args()
    if args.command == "generate":
        return cmd_generate(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "list-staged":
        return cmd_list_staged(args)
    elif args.command == "approve":
        return cmd_approve(args)
    elif args.command == "reject":
        return cmd_reject(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
