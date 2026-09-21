"""Content Factory v2 — Novel Cover Resolver & Lifecycle Manager.

Deterministic, gated novel cover pipeline:
1. Candidate ingestion -> Metadata extraction -> Cover Resolver
2. Local isolated staging: raw_spool/staged_covers/<work_id>/
   (Never writes directly to production).
3. Case A: Source cover reuse (download, validate, stage, attribute).
4. Case B: Beam Cloud Animagine XL serverless generation (2:3 vertical book art).
   Fallback to high-resolution procedural cover if Beam is unavailable/offline.
5. Strict prompt rules:
   - Canonical 2:3 aspect ratio (832x1216);
   - Clear central composition with focal subject;
   - Safe, text-free artwork (unless typography mode explicitly requested);
   - No watermarks, no artist signatures, no copyright marks;
   - Genre-appropriate style and lighting derived from tags/fandom/synopsis.
6. Explicit approval gating:
   - Promotion to approved/production only on explicit operator confirmation;
   - Mandatory confirmation when replacing an existing cover;
   - Persistent `previous_cover` metadata for instant zero-loss rollback.
7. Guardrails:
   - Never log or leak BEAM_TOKEN or production credentials into UI or logs.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
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
STAGED_COVERS_DIR = PROJECT_ROOT / "raw_spool" / "staged_covers"
APPROVED_COVERS_DIR = PROJECT_ROOT / "raw_spool" / "approved_covers"

# Status Constants
STATUS_PENDING = "pending"
STATUS_GENERATING = "generating"
STATUS_STAGED = "staged"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

# Provider Constants
PROVIDER_SOURCE = "source_original"
PROVIDER_BEAM = "beam_animagine_xl"
PROVIDER_PROCEDURAL = "procedural_fallback"

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
    f = (fandom or "").strip().lower()
    for k, v in FANDOM_COLOR_MAP.items():
        if k in f:
            return v
    return FANDOM_COLOR_MAP["default"]


def build_cover_prompt(
    title: str,
    fandom: str,
    genres: Optional[List[str]] = None,
    synopsis: str = "",
    character_cues: str = "",
    aspect_ratio: str = "2:3",
    typography_mode: bool = False,
) -> Tuple[str, str]:
    """Constructs prompt and negative prompt adhering to strict production rules:
    - Vertical book cover orientation (2:3 aspect ratio)
    - Clear central composition
    - Text-free artwork by default (no typography / badges / words)
    - No watermarks, no artist signatures, no copyright marks
    - Genre-appropriate style and lighting
    """
    genres = genres or []
    f_low = (fandom or "").lower()

    # Core quality & style tags
    pos_parts: List[str] = [
        "masterpiece",
        "best quality",
        "light novel cover visual",
        "vertical book cover composition",
        "centered focal character",
        "clear central composition",
        "dramatic cinematic lighting",
        "high contrast depth of field",
        "8k resolution, crisp clean digital anime painting",
    ]

    # Fandom universe
    if fandom:
        pos_parts.append(f"{fandom} universe aesthetic")

    # Character and visual cues
    if character_cues:
        pos_parts.append(character_cues)
    else:
        if "naruto" in f_low:
            pos_parts.append("1boy, young shinobi ninja warrior, hidden leaf headband, focused intense gaze, swirling blue chakra aura, kunai pouch, dramatic ninja action stance")
        elif "one piece" in f_low:
            pos_parts.append("1boy, pirate captain, billowing dark cape, confident determined smirk, roaring ocean waves, dramatic storm clouds")
        elif "conan" in f_low:
            pos_parts.append("1boy, sharp detective in tailored suit, keen analytical gaze, nocturnal metropolitan lights, mysterious shadows")
        elif "genshin" in f_low:
            pos_parts.append("1girl, elegant fantasy adventurer, intricate glowing garments, elemental crystal starlight, celestial night sky")
        elif "fairy tail" in f_low:
            pos_parts.append("1boy, fiery dragon slayer warrior, blazing flame aura, triumphant battle stance, arcane magic circles")
        else:
            pos_parts.append("1heroic protagonist, dynamic light novel protagonist, adventurer cloak, mystical ambient glow, confident pose")

    # Genre cues
    if genres:
        top_genres = [g.strip().lower() for g in genres[:3] if g.strip()]
        if top_genres:
            pos_parts.append(", ".join(top_genres))

    # Textless composition rule
    if not typography_mode:
        pos_parts.append("pure artwork without text, textless, clean composition, blank upper space reserved for typography layout")
    else:
        pos_parts.append("bold typography title integrated into book cover header")

    positive_prompt = ", ".join(pos_parts)

    negative_prompt = (
        "worst quality, low quality, normal quality, blurry, deformed, bad anatomy, bad hands, "
        "missing fingers, extra limbs, mutated, disfigured, text, title, words, letters, signature, "
        "watermark, artist name, logo, copyright notice, banner border, grey side gutters, letterbox, "
        "split screen, multiple views, frame, ugly, poorly drawn face"
    )

    return positive_prompt, negative_prompt


def generate_procedural_fallback_cover(
    title: str,
    fandom: str,
    output_path: Path,
    width: int = 832,
    height: int = 1216,
) -> bool:
    """Generates an elegant, honest procedural 2:3 portrait book cover with typography."""
    if Image is None:
        return False

    bg_dark, bg_accent, _ = get_fandom_palette(fandom)

    img = Image.new("RGBA", (width, height), bg_dark)
    draw = ImageDraw.Draw(img)

    # Vertical gradient
    for y in range(height):
        ratio = y / float(height)
        r1, g1, b1 = int(bg_dark[1:3], 16), int(bg_dark[3:5], 16), int(bg_dark[5:7], 16)
        r2, g2, b2 = int(bg_accent[1:3], 16), int(bg_accent[3:5], 16), int(bg_accent[5:7], 16)
        r = int(r1 + (r2 - r1) * ratio * 0.45)
        g = int(g1 + (g2 - g1) * ratio * 0.45)
        b = int(b1 + (b2 - b1) * ratio * 0.45)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # Inner borders
    draw.rectangle([(24, 24), (width - 24, height - 24)], outline=(255, 255, 255, 45), width=2)
    draw.rectangle([(32, 32), (width - 32, height - 32)], outline=(255, 255, 255, 25), width=1)

    # Fandom pill
    fandom_label = (fandom.upper() if fandom else "FANFIC WORLD").strip()
    try:
        font_fandom = ImageFont.truetype("arialbd.ttf", 26)
        font_title = ImageFont.truetype("arialbd.ttf", 44)
        font_sub = ImageFont.truetype("arial.ttf", 22)
    except Exception:
        font_fandom = ImageFont.load_default()
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    f_bbox = draw.textbbox((0, 0), fandom_label, font=font_fandom)
    fw = f_bbox[2] - f_bbox[0]
    fx = (width - fw) // 2
    fy = 90
    draw.rounded_rectangle([(fx - 24, fy - 8), (fx + fw + 24, fy + 36)], radius=14, fill=(0, 0, 0, 160), outline=(255, 255, 255, 60))
    draw.text((fx, fy), fandom_label, font=font_fandom, fill=(240, 245, 255, 240))

    # Wrapped title in middle
    words = title.split()
    lines = []
    curr = []
    for w in words:
        if len(" ".join(curr + [w])) <= 22:
            curr.append(w)
        else:
            lines.append(" ".join(curr))
            curr = [w]
    if curr:
        lines.append(" ".join(curr))

    ty = int(height * 0.42)
    for line in lines[:4]:
        t_bbox = draw.textbbox((0, 0), line, font=font_title)
        tw = t_bbox[2] - t_bbox[0]
        tx = (width - tw) // 2
        for ox, oy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1)]:
            draw.text((tx + ox, ty + oy), line, font=font_title, fill=(0, 0, 0, 230))
        draw.text((tx, ty), line, font=font_title, fill=(255, 255, 255, 255))
        ty += 58

    # Bottom branding
    brand_text = "FANFIC WORLD · EDITORIAL EDITION"
    b_bbox = draw.textbbox((0, 0), brand_text, font=font_sub)
    bw = b_bbox[2] - b_bbox[0]
    draw.text(((width - bw) // 2, height - 90), brand_text, font=font_sub, fill=(180, 205, 230, 200))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rgb = img.convert("RGB")
    rgb.save(str(output_path), "JPEG", quality=90)
    return True


def stage_source_cover(
    work_id: str,
    source_url: str,
    title: str,
    fandom: str = "",
    attribution: str = "",
    timeout_seconds: float = 30.0,
) -> Tuple[bool, Dict[str, Any], str]:
    """Downloads an approved source cover from RoyalRoad/source and stages it locally."""
    import httpx

    staged_dir = STAGED_COVERS_DIR / work_id
    staged_dir.mkdir(parents=True, exist_ok=True)

    ext = ".jpg"
    if ".png" in source_url.lower():
        ext = ".png"
    elif ".webp" in source_url.lower():
        ext = ".webp"

    dest_file = staged_dir / f"source_cover{ext}"
    active_file = staged_dir / "active_staged.jpg"

    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            resp = client.get(source_url)
            if resp.status_code != 200:
                return False, {}, f"HTTP error {resp.status_code} fetching source cover"
            dest_file.write_bytes(resp.content)

        # Standardize active_staged as JPEG
        if Image is not None:
            with Image.open(dest_file) as im:
                rgb_im = im.convert("RGB")
                rgb_im.save(active_file, "JPEG", quality=92)
        else:
            shutil.copyfile(dest_file, active_file)

        meta = {
            "work_id": work_id,
            "title": title,
            "fandom": fandom,
            "provider": PROVIDER_SOURCE,
            "status": STATUS_STAGED,
            "source_url": source_url,
            "source_attribution": attribution or "Original source cover",
            "aspect_ratio": "2:3",
            "file_size": active_file.stat().st_size,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Check existing metadata for rollback info
        meta_path = staged_dir / "metadata.json"
        if meta_path.exists():
            try:
                old_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if old_meta.get("status") == STATUS_APPROVED:
                    meta["previous_cover"] = old_meta
            except Exception:
                pass

        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return True, meta, f"Source cover staged successfully at {active_file}"
    except Exception as exc:
        return False, {}, f"Failed to stage source cover: {exc}"


def stage_beam_cover(
    work_id: str,
    title: str,
    fandom: str = "",
    genres: Optional[List[str]] = None,
    synopsis: str = "",
    character_cues: str = "",
    seed: Optional[int] = None,
    aspect_ratio: str = "2:3",
    typography_mode: bool = False,
    timeout_seconds: float = 120.0,
    fallback_procedural: bool = True,
) -> Tuple[bool, Dict[str, Any], str]:
    """Generates cover candidate via Beam Cloud Animagine XL with procedural fallback.
    Writes strictly to raw_spool/staged_covers/<work_id>/ without touching production.
    """
    genres = genres or []
    staged_dir = STAGED_COVERS_DIR / work_id
    staged_dir.mkdir(parents=True, exist_ok=True)

    chosen_seed = seed if seed and seed > 0 else random.randint(100000, 9999999)
    candidate_file = staged_dir / f"candidate_{chosen_seed}.jpg"
    active_file = staged_dir / "active_staged.jpg"

    pos_prompt, neg_prompt = build_cover_prompt(
        title=title,
        fandom=fandom,
        genres=genres,
        synopsis=synopsis,
        character_cues=character_cues,
        aspect_ratio=aspect_ratio,
        typography_mode=typography_mode,
    )

    meta: Dict[str, Any] = {
        "work_id": work_id,
        "title": title,
        "fandom": fandom,
        "seed": chosen_seed,
        "aspect_ratio": aspect_ratio,
        "prompt": pos_prompt,
        "negative_prompt": neg_prompt,
        "typography_mode": typography_mode,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": STATUS_GENERATING,
    }

    token = resolve_beam_token()
    beam_success = False
    wall_seconds = 0.0

    if token:
        import httpx
        # 2:3 vertical aspect ratio (832x1216)
        w, h = (832, 1216) if aspect_ratio == "2:3" else (1216, 832)

        payload = {
            "prompt": pos_prompt,
            "negative_prompt": neg_prompt,
            "width": w,
            "height": h,
            "seed": chosen_seed,
            "steps": 28,
        }

        t0 = time.monotonic()
        try:
            with httpx.Client(
                base_url=BEAM_COVER_ENDPOINT,
                headers={"Authorization": f"Bearer {token}"},
                timeout=timeout_seconds,
            ) as client:
                resp = client.post("", json=payload)
                wall_seconds = time.monotonic() - t0

                if resp.status_code == 200:
                    body = resp.json()
                    raw_b64 = body.get("image_base64")
                    if raw_b64:
                        img_bytes = base64.b64decode(raw_b64)
                        candidate_file.write_bytes(img_bytes)
                        shutil.copyfile(candidate_file, active_file)
                        beam_success = True
                        meta["provider"] = PROVIDER_BEAM
                        meta["wall_seconds"] = wall_seconds
                        meta["file_size"] = len(img_bytes)
                        meta["status"] = STATUS_STAGED
        except Exception as exc:
            wall_seconds = time.monotonic() - t0
            meta["beam_error"] = str(exc)

    if not beam_success:
        if not fallback_procedural:
            meta["status"] = STATUS_REJECTED
            return False, meta, f"Beam Cloud failed ({wall_seconds:.1f}s) and procedural fallback disabled"

        # Generate high-res procedural fallback
        gen_ok = generate_procedural_fallback_cover(
            title=title,
            fandom=fandom,
            output_path=candidate_file,
            width=832,
            height=1216,
        )
        if gen_ok and candidate_file.exists():
            shutil.copyfile(candidate_file, active_file)
            meta["provider"] = PROVIDER_PROCEDURAL
            meta["status"] = STATUS_STAGED
            meta["file_size"] = candidate_file.stat().st_size
            meta["wall_seconds"] = wall_seconds
        else:
            meta["status"] = STATUS_REJECTED
            return False, meta, "Failed to generate both Beam and procedural covers"

    # Preserve rollback info if there was a previous approved cover
    meta_path = staged_dir / "metadata.json"
    if meta_path.exists():
        try:
            old_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if old_meta.get("status") == STATUS_APPROVED:
                meta["previous_cover"] = old_meta
        except Exception:
            pass

    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    provider_name = "Beam Cloud Animagine XL" if meta["provider"] == PROVIDER_BEAM else "Procedural Fallback"
    return True, meta, f"Cover candidate staged via {provider_name} ({meta.get('file_size', 0):,} bytes) at {active_file}"


def approve_cover(
    work_id: str,
    upload_r2: bool = False,
    update_appwrite: bool = False,
    confirm_replace: bool = False,
    operator: str = "operator",
) -> Tuple[bool, str, Dict[str, Any]]:
    """Promotes staged cover to approved status.
    Guards:
    - Must have an active staged cover.
    - If replacing an existing approved cover, requires confirm_replace=True.
    - Saves previous cover info in rollback history.
    - Never uploads to R2 or writes to Appwrite unless explicitly instructed.
    """
    staged_dir = STAGED_COVERS_DIR / work_id
    active_file = staged_dir / "active_staged.jpg"
    meta_path = staged_dir / "metadata.json"

    if not active_file.exists() or not meta_path.exists():
        return False, f"No active staged cover found for {work_id}", {}

    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    approved_dir = APPROVED_COVERS_DIR / work_id
    approved_file = approved_dir / "cover.jpg"
    history_file = approved_dir / "history.json"

    # Safety check: existing approved cover
    if approved_file.exists() and not confirm_replace:
        return False, "Confirmation required: An approved cover already exists. Pass confirm_replace=True to overwrite.", meta

    approved_dir.mkdir(parents=True, exist_ok=True)

    # Rollback metadata history
    history: List[Dict[str, Any]] = []
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text(encoding="utf-8"))
        except Exception:
            history = []

    if approved_file.exists():
        old_backup = approved_dir / f"cover_backup_{int(time.time())}.jpg"
        shutil.copyfile(approved_file, old_backup)
        meta["previous_cover"] = {
            "backup_file": str(old_backup),
            "replaced_at": datetime.now(timezone.utc).isoformat(),
        }

    # Copy staged file to approved directory
    shutil.copyfile(active_file, approved_file)

    meta["status"] = STATUS_APPROVED
    meta["approved_at"] = datetime.now(timezone.utc).isoformat()
    meta["approved_by"] = operator

    # Append to history
    history.append({
        "approved_at": meta["approved_at"],
        "provider": meta.get("provider"),
        "seed": meta.get("seed"),
        "approved_by": operator,
    })
    history_file.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")

    # Optional production upload
    if upload_r2:
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
            r2_key_name = f"covers/{owner_id}/{work_id}/cover.jpg"
            client.upload_file(str(approved_file), bucket, r2_key_name, ExtraArgs={"ContentType": "image/jpeg"})
            meta["r2_key"] = r2_key_name

            if update_appwrite:
                import requests
                ap_endpoint = cfg.get("APPWRITE_ENDPOINT", "").rstrip("/")
                ap_proj = cfg.get("APPWRITE_PROJECT_ID", "")
                ap_key = cfg.get("APPWRITE_API_KEY", "")
                ap_db = cfg.get("APPWRITE_DATABASE_ID", "")
                if ap_endpoint and ap_key:
                    url = f"{ap_endpoint}/databases/{ap_db}/collections/novels/documents/{work_id}"
                    resp = requests.patch(
                        url,
                        headers={
                            "X-Appwrite-Project": ap_proj,
                            "X-Appwrite-Key": ap_key,
                            "Content-Type": "application/json",
                        },
                        json={"cover_key": r2_key_name},
                        timeout=15,
                    )
                    meta["appwrite_updated"] = (resp.status_code in (200, 201))

    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return True, f"Cover approved successfully for {work_id}", meta


def reject_cover(work_id: str, reason: str = "") -> Tuple[bool, str]:
    """Marks the active staged cover as rejected."""
    staged_dir = STAGED_COVERS_DIR / work_id
    meta_path = staged_dir / "metadata.json"
    if not meta_path.exists():
        return False, f"No metadata found for {work_id}"

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["status"] = STATUS_REJECTED
        meta["rejected_at"] = datetime.now(timezone.utc).isoformat()
        meta["rejection_reason"] = reason or "Rejected by operator"
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return True, f"Cover rejected for {work_id}: {meta['rejection_reason']}"
    except Exception as exc:
        return False, f"Failed to reject cover: {exc}"


def get_cover_state(work_id: str) -> Dict[str, Any]:
    """Inspects the current cover state for a work (staged vs approved, rollback, provider)."""
    staged_dir = STAGED_COVERS_DIR / work_id
    meta_path = staged_dir / "metadata.json"
    active_staged = staged_dir / "active_staged.jpg"

    approved_dir = APPROVED_COVERS_DIR / work_id
    approved_file = approved_dir / "cover.jpg"

    state: Dict[str, Any] = {
        "work_id": work_id,
        "has_staged": active_staged.exists(),
        "staged_path": str(active_staged) if active_staged.exists() else None,
        "has_approved": approved_file.exists(),
        "approved_path": str(approved_file) if approved_file.exists() else None,
        "status": STATUS_PENDING,
        "provider": None,
        "seed": None,
        "prompt": None,
        "has_rollback": False,
    }

    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            state.update({
                "status": meta.get("status", STATUS_PENDING),
                "provider": meta.get("provider"),
                "seed": meta.get("seed"),
                "prompt": meta.get("prompt"),
                "negative_prompt": meta.get("negative_prompt"),
                "has_rollback": bool(meta.get("previous_cover")),
                "previous_cover": meta.get("previous_cover"),
                "metadata": meta,
            })
        except Exception:
            pass

    return state
