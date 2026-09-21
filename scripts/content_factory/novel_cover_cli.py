"""Content Factory v2 — Novel Cover Generation & Curation Tool.

Supports:
1. Generation: Beam Cloud GPU (Animagine XL 4.0) serverless generation for 2:3 vertical novel covers and 16:9 banners.
2. Fallback: High-resolution procedural typography & fandom emblem cover generation if Beam Cloud is offline or cold.
3. Staging & Approval: Generates candidates into staging before any canonical R2 upload or Appwrite DB update.

Usage:
  # 1. Generate candidate cover (2:3 vertical or 16:9)
  python scripts/content_factory/novel_cover_cli.py generate --novel-id nov_rr_156206 --title "The Cold Between Wars" --fandom "Naruto" --seed 42

  # 2. Preview staged candidates
  python scripts/content_factory/novel_cover_cli.py list-staged --novel-id nov_rr_156206

  # 3. Approve a candidate (local approved staging, optional R2 upload)
  python scripts/content_factory/novel_cover_cli.py approve --novel-id nov_rr_156206 --candidate-file raw_spool/staging_covers/nov_rr_156206/candidate_42.jpg
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from scripts.beam_credential import resolve_beam_token

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    Image = None  # type: ignore

BEAM_COVER_ENDPOINT = "https://cover-illustrious-chartest-994d9f3-v1.app.beam.cloud"
STAGING_DIR = PROJECT_ROOT / "raw_spool" / "staging_covers"
APPROVED_DIR = PROJECT_ROOT / "raw_spool" / "approved_covers"

FANDOM_COLOR_MAP = {
    "naruto": ("#0f172a", "#ea580c", "#38bdf8"),
    "one piece": ("#022c22", "#0284c7", "#f59e0b"),
    "detective conan": ("#1e1b4b", "#4338ca", "#fbbf24"),
    "conan": ("#1e1b4b", "#4338ca", "#fbbf24"),
    "genshin impact": ("#042f2e", "#0d9488", "#a78bfa"),
    "fairy tail": ("#450a0a", "#dc2626", "#fbbf24"),
    "scifi": ("#030712", "#2563eb", "#67e8f9"),
    "warhammer": ("#18181b", "#7f1d1d", "#d97706"),
    "default": ("#0b0f19", "#4f46e5", "#38bdf8"),
}


def get_fandom_palette(fandom: str) -> Tuple[str, str, str]:
    f = fandom.strip().lower()
    for k, v in FANDOM_COLOR_MAP.items():
        if k in f:
            return v
    return FANDOM_COLOR_MAP["default"]


def build_cover_prompt(
    title: str,
    fandom: str,
    genres: List[str],
    synopsis: str = "",
    character_cues: str = "",
    aspect_ratio: str = "2:3",
) -> str:
    """Constructs anime key visual prompt optimized for Animagine XL 4.0."""
    parts: List[str] = [
        "masterpiece",
        "best quality",
        "light novel cover",
        "anime key visual",
        "dramatic cinematic lighting",
        "vibrant detailed anime digital painting",
    ]

    if fandom:
        parts.append(f"{fandom} universe")

    if character_cues:
        parts.append(character_cues)
    else:
        f_low = fandom.lower()
        if "naruto" in f_low:
            parts.append("1boy, young shinobi ninja, dark headband, determined intense gaze, chakra aura")
        elif "one piece" in f_low:
            parts.append("1boy, pirate swordsman, black coat, confident smirk, stormy ocean")
        elif "conan" in f_low:
            parts.append("1boy, detective suit, sharp analytical gaze, nocturnal city lights")
        elif "genshin" in f_low:
            parts.append("1girl, elegant fantasy adventurer, ornate fantasy garments, mystical starlight")
        else:
            parts.append("1boy, heroic protagonist, adventurer cloak, mystical energy glow")

    if genres:
        parts.append(", ".join(genres[:3]))

    parts.append("clear focal composition")
    parts.append("blank upper space reserved for title typography")
    parts.append("8k resolution, crisp lineart")

    return ", ".join(parts)


def generate_procedural_placeholder(
    title: str,
    fandom: str,
    output_path: Path,
    width: int = 800,
    height: int = 1200,
) -> bool:
    """Generates an elegant, honest procedural cover with typography and fandom badge."""
    if Image is None:
        print("[CoverGen] Pillow is not installed.")
        return False

    bg_dark, bg_accent, glow_accent = get_fandom_palette(fandom)

    # Base image with gradient
    img = Image.new("RGBA", (width, height), bg_dark)
    draw = ImageDraw.Draw(img)

    # Gradient overlay
    for y in range(height):
        ratio = y / float(height)
        # Interpolate between dark and accent
        r1, g1, b1 = int(bg_dark[1:3], 16), int(bg_dark[3:5], 16), int(bg_dark[5:7], 16)
        r2, g2, b2 = int(bg_accent[1:3], 16), int(bg_accent[3:5], 16), int(bg_accent[5:7], 16)
        r = int(r1 + (r2 - r1) * ratio * 0.4)
        g = int(g1 + (g2 - g1) * ratio * 0.4)
        b = int(b1 + (b2 - b1) * ratio * 0.4)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # Border vignette
    draw.rectangle([(20, 20), (width - 20, height - 20)], outline=(255, 255, 255, 40), width=2)
    draw.rectangle([(26, 26), (width - 26, height - 26)], outline=(255, 255, 255, 20), width=1)

    # Fandom tag header
    fandom_label = (fandom.upper() if fandom else "FANFIC WORLD").strip()
    try:
        font_fandom = ImageFont.truetype("arialbd.ttf", 28)
        font_title = ImageFont.truetype("arialbd.ttf", 46)
        font_sub = ImageFont.truetype("arial.ttf", 24)
    except Exception:
        font_fandom = ImageFont.load_default()
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    # Draw Fandom pill
    f_bbox = draw.textbbox((0, 0), fandom_label, font=font_fandom)
    fw = f_bbox[2] - f_bbox[0]
    fx = (width - fw) // 2
    fy = 80
    draw.rounded_rectangle([(fx - 24, fy - 8), (fx + fw + 24, fy + 38)], radius=16, fill=(0, 0, 0, 160), outline=(255, 255, 255, 60))
    draw.text((fx, fy), fandom_label, font=font_fandom, fill=(240, 240, 255, 240))

    # Wrap title lines
    words = title.split()
    lines = []
    curr = []
    for w in words:
        if len(" ".join(curr + [w])) <= 20:
            curr.append(w)
        else:
            lines.append(" ".join(curr))
            curr = [w]
    if curr:
        lines.append(" ".join(curr))

    # Center title in middle third
    ty = int(height * 0.42)
    for line in lines[:4]:
        t_bbox = draw.textbbox((0, 0), line, font=font_title)
        tw = t_bbox[2] - t_bbox[0]
        tx = (width - tw) // 2
        # Glow
        for ox, oy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1)]:
            draw.text((tx + ox, ty + oy), line, font=font_title, fill=(0, 0, 0, 220))
        draw.text((tx, ty), line, font=font_title, fill=(255, 255, 255, 255))
        ty += 60

    # Subtitle / Studio footer
    brand_text = "FANFIC WORLD · AUDIO & NOVEL"
    b_bbox = draw.textbbox((0, 0), brand_text, font=font_sub)
    bw = b_bbox[2] - b_bbox[0]
    draw.text(((width - bw) // 2, height - 90), brand_text, font=font_sub, fill=(180, 200, 220, 200))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rgb_img = img.convert("RGB")
    rgb_img.save(str(output_path), "JPEG", quality=90)
    return True


def generate_cover_via_beam(
    prompt: str,
    output_path: Path,
    seed: int,
    aspect_ratio: str = "2:3",
    timeout_seconds: float = 120.0,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Calls the active Beam Cloud cover model."""
    token = resolve_beam_token()
    if not token:
        print("[CoverGen] BEAM_TOKEN not found via Windows Credential Manager.")
        return False, None

    import httpx

    # Animagine XL SDXL aspect ratios
    if aspect_ratio == "16:9":
        w, h = 1216, 832
    else:  # 2:3 vertical
        w, h = 832, 1216

    payload = {
        "prompt": prompt,
        "negative_prompt": "worst quality, low quality, blurry, deformed, bad anatomy, bad hands, text, watermark, logo, extra limbs",
        "width": w,
        "height": h,
        "seed": seed,
        "steps": 28,
    }

    print(f"[CoverGen] Calling Beam Cloud endpoint: {BEAM_COVER_ENDPOINT}")
    print(f"[CoverGen] Dimensions: {w}x{h} ({aspect_ratio}), Seed: {seed}")
    t0 = time.monotonic()
    try:
        client = httpx.Client(
            base_url=BEAM_COVER_ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_seconds,
        )
        resp = client.post("", json=payload)
        wall = time.monotonic() - t0
        if resp.status_code != 200:
            print(f"[CoverGen] Beam error HTTP {resp.status_code}: {resp.text[:300]}")
            return False, {"error": f"HTTP {resp.status_code}", "wall_seconds": wall}

        body = resp.json()
        raw_b64 = body.get("image_base64")
        if not raw_b64:
            print("[CoverGen] Beam response missing image_base64")
            return False, {"error": "Missing image_base64", "wall_seconds": wall}

        img_bytes = base64.b64decode(raw_b64)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(img_bytes)
        print(f"[CoverGen] ✅ Cover generated via Beam Cloud in {wall:.1f}s ({len(img_bytes):,} bytes)")
        return True, {
            "wall_seconds": wall,
            "seed": body.get("seed", seed),
            "size_bytes": len(img_bytes),
            "provider": "beam_animagine_xl",
        }
    except Exception as exc:
        wall = time.monotonic() - t0
        print(f"[CoverGen] Beam request failed ({wall:.1f}s): {exc}")
        return False, {"error": str(exc), "wall_seconds": wall}


def cmd_generate(args: argparse.Namespace) -> int:
    novel_id = args.novel_id.strip()
    title = args.title.strip()
    fandom = args.fandom.strip()
    genres = [g.strip() for g in args.genres.split(",") if g.strip()] if args.genres else []
    aspect = args.aspect_ratio or "2:3"
    seed = args.seed if args.seed and args.seed > 0 else random.randint(100000, 9999999)

    staged_dir = STAGING_DIR / novel_id
    staged_dir.mkdir(parents=True, exist_ok=True)

    out_file = staged_dir / f"candidate_{seed}.jpg"
    meta_file = staged_dir / f"candidate_{seed}.json"

    prompt = build_cover_prompt(
        title=title,
        fandom=fandom,
        genres=genres,
        synopsis=args.synopsis or "",
        character_cues=args.character_cues or "",
        aspect_ratio=aspect,
    )

    success = False
    meta: Dict[str, Any] = {
        "novel_id": novel_id,
        "title": title,
        "fandom": fandom,
        "seed": seed,
        "aspect_ratio": aspect,
        "prompt": prompt,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if args.mode in ("beam", "auto"):
        success, beam_meta = generate_cover_via_beam(
            prompt=prompt,
            output_path=out_file,
            seed=seed,
            aspect_ratio=aspect,
            timeout_seconds=args.timeout or 120.0,
        )
        if beam_meta:
            meta.update(beam_meta)

    if not success:
        print("[CoverGen] Generating procedural high-res fallback cover...")
        w, h = (1200, 675) if aspect == "16:9" else (800, 1200)
        success = generate_procedural_placeholder(
            title=title,
            fandom=fandom,
            output_path=out_file,
            width=w,
            height=h,
        )
        meta["provider"] = "procedural_fallback"
        meta["size_bytes"] = out_file.stat().st_size if out_file.exists() else 0

    if success and out_file.exists():
        meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[CoverGen] Candidate staged at: {out_file}")
        print(f"[CoverGen] Meta saved at: {meta_file}")
        return 0
    else:
        print("[CoverGen] ❌ Failed to produce cover.")
        return 1


def cmd_list_staged(args: argparse.Namespace) -> int:
    novel_id = args.novel_id.strip()
    staged_dir = STAGING_DIR / novel_id
    if not staged_dir.exists():
        print(f"[CoverGen] No staging directory found for novel {novel_id}")
        return 0

    candidates = list(staged_dir.glob("candidate_*.jpg"))
    print(f"[CoverGen] Found {len(candidates)} candidate(s) for {novel_id}:")
    for c in candidates:
        meta_f = c.with_suffix(".json")
        meta = json.loads(meta_f.read_text(encoding="utf-8")) if meta_f.exists() else {}
        print(f"  - {c.name} ({c.stat().st_size // 1024} KB) | Provider: {meta.get('provider')} | Seed: {meta.get('seed')}")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    novel_id = args.novel_id.strip()
    candidate_path = Path(args.candidate_file)
    if not candidate_path.exists():
        print(f"[CoverGen] Candidate file does not exist: {candidate_path}")
        return 1

    appr_dir = APPROVED_DIR / novel_id
    appr_dir.mkdir(parents=True, exist_ok=True)
    dest_path = appr_dir / "cover.jpg"

    # Copy to approved directory
    dest_path.write_bytes(candidate_path.read_bytes())
    print(f"[CoverGen] Approved cover saved locally at: {dest_path}")

    # Optional R2 upload
    if args.upload_r2:
        from dotenv import dotenv_values
        import boto3
        from botocore.config import Config

        cfg = dotenv_values(PROJECT_ROOT / "server" / ".env.production")
        r2_acc = cfg.get("R2_ACCOUNT_ID")
        r2_key = cfg.get("R2_ACCESS_KEY_ID")
        r2_sec = cfg.get("R2_SECRET_ACCESS_KEY")
        bucket = cfg.get("R2_BUCKET", "fanfic-prod")
        owner_id = cfg.get("OWNER_ID", "6a8c525aa05b8642d568")

        if r2_acc and r2_key and r2_sec:
            client = boto3.client(
                "s3",
                endpoint_url=f"https://{r2_acc}.r2.cloudflarestorage.com",
                aws_access_key_id=r2_key,
                aws_secret_access_key=r2_sec,
                config=Config(signature_version="s3v4"),
                region_name="auto",
            )
            r2_object_key = f"covers/{owner_id}/{novel_id}/cover.jpg"
            print(f"[CoverGen] Uploading to Cloudflare R2: s3://{bucket}/{r2_object_key}")
            client.upload_file(str(dest_path), bucket, r2_object_key, ExtraArgs={"ContentType": "image/jpeg"})
            print("[CoverGen] ✅ Uploaded to R2 successfully.")

            if args.update_appwrite:
                import requests
                ap_endpoint = cfg.get("APPWRITE_ENDPOINT", "").rstrip("/")
                ap_proj = cfg.get("APPWRITE_PROJECT_ID", "")
                ap_key = cfg.get("APPWRITE_API_KEY", "")
                ap_db = cfg.get("APPWRITE_DATABASE_ID", "")
                if ap_endpoint and ap_key:
                    url = f"{ap_endpoint}/databases/{ap_db}/collections/novels/documents/{novel_id}"
                    resp = requests.patch(
                        url,
                        headers={
                            "X-Appwrite-Project": ap_proj,
                            "X-Appwrite-Key": ap_key,
                            "Content-Type": "application/json",
                        },
                        json={"cover_key": r2_object_key},
                        timeout=15,
                    )
                    if resp.status_code in (200, 201):
                        print(f"[CoverGen] ✅ Updated Appwrite novel document {novel_id} with cover_key: {r2_object_key}")
                    else:
                        print(f"[CoverGen] ⚠️ Appwrite update failed ({resp.status_code}): {resp.text[:300]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Content Factory v2 Cover Generation CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Generate
    p_gen = subparsers.add_parser("generate", help="Generate a cover candidate")
    p_gen.add_argument("--novel-id", required=True, help="Novel ID (e.g. nov_rr_156206)")
    p_gen.add_argument("--title", required=True, help="Novel title")
    p_gen.add_argument("--fandom", default="Fanfic", help="Novel fandom (e.g. Naruto)")
    p_gen.add_argument("--genres", default="", help="Comma-separated genres")
    p_gen.add_argument("--synopsis", default="", help="Short synopsis")
    p_gen.add_argument("--character-cues", default="", help="Visual character cues")
    p_gen.add_argument("--aspect-ratio", choices=["2:3", "16:9"], default="2:3", help="Aspect ratio")
    p_gen.add_argument("--seed", type=int, default=0, help="Random seed")
    p_gen.add_argument("--mode", choices=["auto", "beam", "placeholder"], default="auto", help="Generation mode")
    p_gen.add_argument("--timeout", type=float, default=120.0, help="HTTP timeout seconds")

    # List
    p_list = subparsers.add_parser("list-staged", help="List staged candidates for a novel")
    p_list.add_argument("--novel-id", required=True, help="Novel ID")

    # Approve
    p_app = subparsers.add_parser("approve", help="Approve candidate cover")
    p_app.add_argument("--novel-id", required=True, help="Novel ID")
    p_app.add_argument("--candidate-file", required=True, help="Path to candidate image")
    p_app.add_argument("--upload-r2", action="store_true", help="Upload approved cover to R2")
    p_app.add_argument("--update-appwrite", action="store_true", help="Update Appwrite database document")

    args = parser.parse_args()
    if args.command == "generate":
        return cmd_generate(args)
    elif args.command == "list-staged":
        return cmd_list_staged(args)
    elif args.command == "approve":
        return cmd_approve(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
