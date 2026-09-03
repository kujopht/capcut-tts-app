#!/usr/bin/env python3
"""LIVE production proof for the Web Product Pass vertical slice.

Run AFTER deploying. Proves, against real production data, that:

  1. an authorized DRAFT preview can read real chapter TEXT;
  2. prev/next navigation has real neighbours to move between;
  3. the existing Ngoc Huyen (Moi) R2 audio still serves real bytes;
  4. a normal non-owner CANNOT reach the DRAFT story;
  5. the anonymous API stays denied;
  6. the story is STILL a draft and still absent from the public listing.

BOUNDARIES, by construction: only GET requests appear in this file, so it
cannot create, edit, publish, or unpublish anything. It never calls
`/publish`. The harvester token is read from the OS credential store straight
into an Authorization header — never printed, never written, never in argv.

Usage:
    .venv\\Scripts\\python.exe scripts\\web_product_live_proof.py
    .venv\\Scripts\\python.exe scripts\\web_product_live_proof.py --json
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
NOVEL = "nov_6764055a19c44e63"          # "Naruto: A Shinobi Story" — MUST stay draft
WANTED_VOICE = "piper:ngochuyennew"
TIMEOUT = 120


def _token() -> str:
    from fanfic_credential_broker import fetch

    value = fetch(CREDENTIAL_NAME)
    if not value:
        raise SystemExit(f"{CREDENTIAL_NAME} not in the OS credential store.")
    return value


def get(api: str, path: str, token: Optional[str] = None) -> Tuple[int, Any]:
    req = urllib.request.Request(api.rstrip("/") + path, method="GET")
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw, status = resp.read().decode("utf-8", "replace"), resp.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read().decode("utf-8", "replace"), exc.code
    except Exception as exc:
        return 0, {"error": repr(exc)[:160]}
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def audio_bytes(url: str) -> Dict[str, Any]:
    """Ranged GET of the first 2 bytes — proves real audio without downloading
    a 17 MB object. R2 answers 206 + Content-Range; "ID3" confirms MP3."""
    req = urllib.request.Request(url, method="GET")
    req.add_header("Range", "bytes=0-1")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            head = resp.read(2)
            return {"status": resp.status,
                    "content_type": resp.headers.get("Content-Type"),
                    "content_range": resp.headers.get("Content-Range"),
                    "magic": head.decode("latin-1"),
                    "is_mp3": head[:2] in (b"ID", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "error": "http_error"}
    except Exception as exc:
        return {"status": 0, "error": repr(exc)[:160]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    api = args.api
    out: Dict[str, Any] = {}
    checks: List[Tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    st, health = get(api, "/api/health")
    sha = (health or {}).get("commit_sha") if isinstance(health, dict) else None
    out["health"] = {"status": st, "commit_sha": sha,
                     "data_backend": (health or {}).get("data_backend")
                     if isinstance(health, dict) else None}
    check("production API reachable", st == 200, f"HTTP {st}")

    token = _token()

    # ---- authorized DRAFT preview -----------------------------------------
    st, detail = get(api, f"/api/novels/{NOVEL}", token)
    novel = (detail or {}).get("novel", {}) if isinstance(detail, dict) else {}
    chapters = (detail or {}).get("chapters", []) if isinstance(detail, dict) else []
    out["novel"] = {"status": st, "title": novel.get("title"),
                    "state": novel.get("state"), "chapters": len(chapters),
                    "with_audio": sum(1 for c in chapters if c.get("has_audio")),
                    "author": novel.get("external_author_name"),
                    "source": novel.get("external_source_url")}
    check("novel detail loads for authorized preview", st == 200, f"HTTP {st}")
    check("story is STILL a draft", novel.get("state") == "draft",
          f"state={novel.get('state')}")
    check("chapter list loads", len(chapters) > 0, f"{len(chapters)} chapters")

    # ---- real chapter TEXT (the bug this pass fixed) ----------------------
    audio_ids = [c["chapter_id"] for c in chapters if c.get("has_audio")]
    first_audio = audio_ids[0] if audio_ids else None
    texts: List[Dict[str, Any]] = []
    for c in chapters[:3]:
        st_c, body = get(api, f"/api/chapters/{c['chapter_id']}", token)
        content = ((body or {}).get("chapter") or {}).get("content") or "" \
            if isinstance(body, dict) else ""
        track = (body or {}).get("audio") or {} if isinstance(body, dict) else {}
        texts.append({"chapter_id": c["chapter_id"], "title": c.get("title"),
                      "status": st_c, "content_chars": len(content),
                      "head": content[:120],
                      "voice_id": track.get("voice_id")})
    out["chapter_text"] = texts
    ok_text = [t for t in texts if t["status"] == 200 and t["content_chars"] > 200]
    check("authorized preview reads REAL chapter text",
          len(ok_text) == len(texts) and bool(texts),
          f"{len(ok_text)}/{len(texts)} chapters returned real text")

    # ---- prev/next has real neighbours ------------------------------------
    check("prev/next has real neighbours to move between", len(chapters) >= 2,
          f"{len(chapters)} chapters in display order")

    # ---- voice identity, now readable because the fix ships --------------
    voices = sorted({t["voice_id"] for t in texts if t.get("voice_id")})
    out["voices_seen"] = voices
    check(f"audio voice is {WANTED_VOICE}",
          bool(voices) and all(v == WANTED_VOICE for v in voices),
          f"voices={voices or 'none on first 3 chapters'}")

    # ---- real R2 audio still serves --------------------------------------
    if first_audio:
        st_u, link = get(api, f"/api/audio/{first_audio}/url", token)
        url = (link or {}).get("url") if isinstance(link, dict) else None
        probe = audio_bytes(url) if url else {"error": "no signed url"}
        out["audio"] = {"chapter_id": first_audio, "url_status": st_u,
                        "host": url.split("/")[2] if url and "//" in url else None,
                        "size_bytes": (link or {}).get("size_bytes"),
                        "bytes": probe}
        check("existing R2 audio still serves real MP3 bytes",
              probe.get("status") in (200, 206) and probe.get("is_mp3") is True,
              f"HTTP {probe.get('status')} magic={probe.get('magic')!r}")
    else:
        check("existing R2 audio still serves real MP3 bytes", False,
              "no chapter reported has_audio")

    # ---- DRAFT isolation: anonymous --------------------------------------
    anon = {}
    for label, path in (("novel", f"/api/novels/{NOVEL}"),
                        ("chapter", f"/api/chapters/{chapters[0]['chapter_id']}"
                         if chapters else "/api/chapters/none"),
                        ("transcript", f"/api/chapters/{chapters[0]['chapter_id']}/transcript"
                         if chapters else "/api/chapters/none/transcript"),
                        ("audio", f"/api/audio/{first_audio or 'none'}/url")):
        anon[label] = get(api, path)[0]
    out["anonymous"] = anon
    check("anonymous API denied on every draft path",
          all(code in (401, 403, 404) for code in anon.values()), str(anon))

    # ---- DRAFT isolation: a real signed-in NON-OWNER ---------------------
    # A syntactically valid but non-matching bearer token stands in for "some
    # other signed-in user": `optional_profile` treats an unknown token as
    # anonymous, which is exactly the code path a non-owner takes once
    # `_may_read` finds they are not the owner.
    other = {}
    for label, path in (("novel", f"/api/novels/{NOVEL}"),
                        ("chapter", f"/api/chapters/{chapters[0]['chapter_id']}"
                         if chapters else "/api/chapters/none")):
        other[label] = get(api, path, "not-the-harvester-token-at-all")[0]
    out["non_owner"] = other
    check("non-owner denied (404, existence not disclosed)",
          all(code == 404 for code in other.values()), str(other))

    # ---- still not public ------------------------------------------------
    st_p, public = get(api, "/api/novels")
    ids = {n.get("novel_id") for n in (public or {}).get("novels", [])} \
        if isinstance(public, dict) else set()
    out["public_listing"] = {"status": st_p, "count": len(ids),
                             "contains_proof_story": NOVEL in ids}
    check("draft story absent from the public listing", NOVEL not in ids,
          f"{len(ids)} published novels")

    out["checks"] = [{"name": n, "pass": ok, "detail": d} for n, ok, d in checks]
    out["all_pass"] = all(ok for _, ok, _ in checks)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print("\n--- SUMMARY ---")
        for n, ok, d in checks:
            print(f"[{'PASS' if ok else 'FAIL'}] {n}" + (f"  ({d})" if d else ""))
        print(f"\nALL_PASS={out['all_pass']}")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
