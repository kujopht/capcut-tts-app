#!/usr/bin/env python3
"""READ-ONLY production probe — finds the best real DRAFT story to prove the
user-facing vertical slice (home -> story -> chapter -> audio) against.

Why this script exists: the web product pass has to be proven with REAL
production content, and "real" here means a DRAFT novel that already has
chapters with real translated text and at least one chapter with existing
`piper:ngochuyennew` audio in R2. Nothing in the repo answered "which novel is
that?" — the reports name novel ids but not their audio state.

BOUNDARIES, by construction, not by convention:
  - Only GET requests. No POST/PATCH/PUT/DELETE call exists in this file, so it
    cannot create, edit, or publish anything even if invoked wrongly.
  - Never calls `/publish` or `/unpublish`. Production content's PUBLIC state is
    not touched by this probe.
  - The harvester token is read from the OS credential store into this process
    and goes straight into an Authorization header. It is never printed, never
    written to a file, never placed in argv.
  - Audio is probed with a ranged GET of the first bytes only (or HEAD), so it
    proves playability without downloading whole files.

Usage:
    .venv\\Scripts\\python.exe scripts\\web_product_slice_probe.py
    .venv\\Scripts\\python.exe scripts\\web_product_slice_probe.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_API = "https://fas-prod-api.onrender.com"
CREDENTIAL_NAME = "FAS_HARVESTER_SERVICE_TOKEN"
WANTED_VOICE = "piper:ngochuyennew"
TIMEOUT = 90


def _token() -> str:
    """Harvester service token, straight from the OS credential store.

    Imported rather than shelled out to so the value never crosses a process
    boundary as text. `fetch` returns None when the credential is absent — that
    is a hard stop, not something to work around.
    """
    from fanfic_credential_broker import fetch

    value = fetch(CREDENTIAL_NAME)
    if not value:
        raise SystemExit(
            f"{CREDENTIAL_NAME} not in the credential store. Store it once with:\n"
            f"  python scripts/fanfic_credential_broker.py store --name {CREDENTIAL_NAME}"
        )
    return value


def get(api: str, path: str, token: Optional[str] = None) -> Tuple[int, Any]:
    """One GET. Returns (status, parsed-json-or-text). Never raises on 4xx."""
    req = urllib.request.Request(api.rstrip("/") + path, method="GET")
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    except Exception as exc:  # network-level
        return 0, {"error": repr(exc)}
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def probe_audio(url: str) -> Dict[str, Any]:
    """Prove the signed URL actually serves audio bytes, WITHOUT downloading the
    file. A ranged GET of the first 2 bytes is enough: R2 answers 206 with a
    Content-Range, and an MP3/ID3 magic number confirms it is really audio."""
    req = urllib.request.Request(url, method="GET")
    req.add_header("Range", "bytes=0-1")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            head = resp.read(2)
            return {
                "status": resp.status,
                "content_type": resp.headers.get("Content-Type"),
                "content_range": resp.headers.get("Content-Range"),
                "magic": head.hex(),
                # ID3 tag ("ID3") or an MPEG frame sync (0xFF 0xFB/0xF3/0xF2)
                "looks_like_mp3": head[:2] in (b"ID", b"\xff\xfb", b"\xff\xf3",
                                               b"\xff\xf2"),
            }
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "error": "http_error"}
    except Exception as exc:
        return {"status": 0, "error": repr(exc)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--novel", default="", help="inspect exactly this novel id")
    args = ap.parse_args(argv)

    api = args.api
    out: Dict[str, Any] = {"api": api}

    status, health = get(api, "/api/health")
    out["health"] = {"status": status, "data_backend": (health or {}).get("data_backend")
                     if isinstance(health, dict) else None}
    if status != 200:
        out["fatal"] = "production API not reachable"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1

    token = _token()

    # Owner-scoped listing: this is the ONLY way a DRAFT is visible, and it
    # proves the harvester identity owns the content we are about to inspect.
    status, mine = get(api, "/api/novels?mine=true", token)
    owned: List[Dict[str, Any]] = (mine or {}).get("novels", []) if isinstance(mine, dict) else []
    out["owned_count"] = len(owned)
    out["owned_status"] = status

    # The real public listing, with NO auth — the drafts must be absent here.
    status_pub, public = get(api, "/api/novels")
    public_ids = {n.get("novel_id") for n in (public or {}).get("novels", [])} \
        if isinstance(public, dict) else set()
    out["public_count"] = len(public_ids)

    candidates = [n for n in owned if n.get("novel_id") == args.novel] if args.novel else owned
    rows: List[Dict[str, Any]] = []

    for novel in candidates:
        nid = novel.get("novel_id")
        st, detail = get(api, f"/api/novels/{nid}", token)
        if st != 200 or not isinstance(detail, dict):
            rows.append({"novel_id": nid, "detail_status": st})
            continue
        chapters = detail.get("chapters", [])
        with_audio = [c for c in chapters if c.get("has_audio")]
        rows.append({
            "novel_id": nid,
            "title": novel.get("title"),
            "state": novel.get("state"),
            "status": novel.get("status"),
            "chapters": len(chapters),
            "chapters_with_audio": len(with_audio),
            "cover_url": bool(novel.get("cover_url")),
            "external_author_name": novel.get("external_author_name"),
            "external_source_url": novel.get("external_source_url"),
            "fandom_ids": novel.get("fandom_ids"),
            "tags": novel.get("tags"),
            "in_public_listing": nid in public_ids,
            "audio_chapter_ids": [c.get("chapter_id") for c in with_audio][:5],
            "first_chapter_id": chapters[0].get("chapter_id") if chapters else None,
        })

    # Best proof story: has audio, then most chapters.
    rows.sort(key=lambda r: (r.get("chapters_with_audio", 0), r.get("chapters", 0)),
              reverse=True)
    out["novels"] = rows

    best = next((r for r in rows if r.get("chapters_with_audio", 0) > 0), None)
    if best:
        chapter_id = best["audio_chapter_ids"][0]
        st, ch = get(api, f"/api/chapters/{chapter_id}", token)
        content = (ch or {}).get("chapter", {}).get("content") or "" if isinstance(ch, dict) else ""
        track = (ch or {}).get("audio") or {} if isinstance(ch, dict) else {}
        st_url, link = get(api, f"/api/audio/{chapter_id}/url", token)
        signed = (link or {}).get("url") if isinstance(link, dict) else None
        out["proof"] = {
            "novel_id": best["novel_id"],
            "novel_title": best["title"],
            "chapter_id": chapter_id,
            "chapter_status": st,
            "chapter_title": (ch or {}).get("chapter", {}).get("title") if isinstance(ch, dict) else None,
            "content_chars": len(content),
            "content_head": content[:180],
            "voice": track.get("voice_id") or track.get("voice"),
            "voice_matches_ngochuyennew": WANTED_VOICE in json.dumps(track, ensure_ascii=False),
            "track_keys": sorted(track.keys()),
            "size_bytes": track.get("size_bytes"),
            "audio_url_status": st_url,
            "signed_url_present": bool(signed),
            "signed_url_host": (signed.split("/")[2] if signed and "//" in signed else None),
            "audio_bytes": probe_audio(signed) if signed else {"error": "no signed url"},
        }
        # DRAFT must be invisible without auth.
        st_anon_ch, _ = get(api, f"/api/chapters/{chapter_id}")
        st_anon_nv, _ = get(api, f"/api/novels/{best['novel_id']}")
        st_anon_au, _ = get(api, f"/api/audio/{chapter_id}/url")
        out["draft_isolation"] = {
            "anon_chapter_status": st_anon_ch,
            "anon_novel_status": st_anon_nv,
            "anon_audio_status": st_anon_au,
            "secure": st_anon_ch in (401, 403, 404) and st_anon_nv in (401, 403, 404)
                      and st_anon_au in (401, 403, 404),
        }

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
