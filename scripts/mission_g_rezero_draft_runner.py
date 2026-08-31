#!/usr/bin/env python3
"""Mission G — one-shot production DRAFT runner, scoped to EXACTLY one
already-acquired, already-eligibility-gated, already-Drive-archived work:

    docln.net #28046 — "Re: Zero - Hai Vi Sao Bi Quen Lang" (Chuong 1-2)

Reads `FAS_HARVESTER_TOKEN` from this process's OWN environment at
execution time. NEVER prints, logs, or writes the token anywhere — the
`goi()` HTTP helper puts it straight into an Authorization header and
nothing in this script ever touches `sys.argv`, a log line, or a file
with that value. Run it FROM the shell that already holds the token:

    $env:FAS_HARVESTER_TOKEN | Out-Null   # (already set in your session)
    .venv\\Scripts\\python.exe scripts\\mission_g_rezero_draft_runner.py

    # preview only, writes nothing:
    .venv\\Scripts\\python.exe scripts\\mission_g_rezero_draft_runner.py --dry-run

Boundaries, enforced by construction, not by convention:
  - Only POST (create) calls against /api/novels and /api/chapters — never
    PUT/PATCH/DELETE on anything, so a pre-existing Novel/Chapter can never
    be touched by this script, by construction (no such call exists here).
  - NEVER calls .../publish - the created Novel stays in its default
    `draft` state (server/domain.py::Novel.state default), matching
    Mission G's "Do NOT publish" boundary.
  - Idempotent re-run: before creating, checks `GET /api/novels?mine=true`
    (owner-scoped, needs the token) for an existing Novel with the exact
    same `external_source_url` and reuses it instead of creating a
    duplicate DRAFT on accidental re-run.
  - Ends with two REAL verification reads: `GET /api/novels/{id}` (owner
    auth - proves persistence + the 2 chapters are attached) and
    `GET /api/novels` (no auth, the real public/published listing - proves
    the new Novel is NOT in it, i.e. still unpublished).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_API = "https://fas-prod-api.onrender.com"
TOKEN_ENV_VAR = "FAS_HARVESTER_TOKEN"

SOURCE_URL = "https://docln.net/truyen/28046-re-zero-hai-vi-sao-bi-quen-lang"
NOVEL_TITLE = "Re: Zero - Hai Vi Sao Bi Quen Lang"
NOVEL_DESCRIPTION = (
    "Fanfic Re:Zero (nguon: docln.net, dich tu AO3 voi su cho phep cua tac "
    "gia/hoa si) - Anastasia Hoshin va Natsuki Subaru, ca hai deu bi Pham "
    "An cuop mat ten tuoi sau tran chien Priestella, tinh co gap nhau va "
    "lap mot moi quan he doi tac tren duong toi Kararagi."
)
FANDOM_NAMES = ["Re:Zero"]
CHARACTERS = ["Natsuki Subaru", "Anastasia Hoshin", "Felix Argyle"]
PAIRINGS = ["Natsuki Subaru/Anastasia Hoshin"]

SCRATCH = Path(
    r"C:\Users\nguye\AppData\Local\Temp\claude\C--Users-nguye-Documents-CapCut-TTS-App"
    r"\9f89efae-a482-4002-af29-02601ce86985\scratchpad"
)
CHAPTERS: List[Tuple[str, str, int]] = [
    # (local filename, chapter title, order_index)
    ("rezero_ch01.txt", "Chuong 1: Mo Dau: Cuoc Dam Phan Gay Gat", 1),
    ("rezero_ch02.txt", "Chuong 2: Nhung Tieng Vong", 2),
]

KET_QUA: List[Tuple[str, bool, str]] = []


def kt(ten: str, dieu_kien: Any, ghi_chu: str = "") -> bool:
    ok = bool(dieu_kien)
    KET_QUA.append((ten, ok, ghi_chu))
    print(f"  [{'PASS' if ok else 'FAIL'}] {ten}" + (f" -- {ghi_chu}" if ghi_chu else ""),
          flush=True)
    return ok


def goi(api: str, method: str, path: str, payload: Any = None,
        token: Optional[str] = None, timeout: int = 60) -> Tuple[int, Any]:
    """The ONLY place the token is touched: put straight into a header
    object that is never logged, never echoed. Callers pass `token` in,
    nothing here persists it beyond this one request."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(api.rstrip("/") + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "mission-g-rezero-draft-runner/1.0")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8")
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except Exception:
            return exc.code, {"raw": body[:500]}
    except Exception as exc:
        return 0, {"error": type(exc).__name__, "detail": str(exc)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--api", default=DEFAULT_API)
    p.add_argument("--dry-run", action="store_true",
                   help="Read the token and preview the payloads; write nothing.")
    a = p.parse_args(argv)

    print(f"Mission G production DRAFT runner\n  api={a.api}\n  source={SOURCE_URL}\n"
          f"  dry_run={a.dry_run}")

    print("\n=== 1. Health check (real, no auth needed) ===")
    ma, r = goi(a.api, "GET", "/api/health")
    if not kt("GET /api/health -> 200", ma == 200, f"HTTP {ma}"):
        return 1
    kt("data_backend == appwrite (real store, not mock)",
       r.get("data_backend") == "appwrite", f"data_backend={r.get('data_backend')}")

    print("\n=== 2. Load already-acquired chapter text (local, already Drive-archived) ===")
    chapters_text: List[str] = []
    for fname, title, order in CHAPTERS:
        path = SCRATCH / fname
        if not kt(f"chapter file exists: {fname}", path.exists()):
            return 1
        text = path.read_text(encoding="utf-8")
        chapters_text.append(text)
        print(f"    {fname}: {len(text)} chars, order_index={order}")

    if a.dry_run:
        print("\n--dry-run: would create 1 Novel + 2 Chapters as DRAFT. Payload preview:")
        print(json.dumps({
            "novel": {"title": NOVEL_TITLE, "fandom_names": FANDOM_NAMES,
                     "external_source_url": SOURCE_URL, "publication_mode": "full_text",
                     "status": "ongoing", "characters": CHARACTERS, "pairings": PAIRINGS},
            "chapters": [{"title": t, "order_index": o, "chars": len(c)}
                        for (_, t, o), c in zip(CHAPTERS, chapters_text)],
        }, ensure_ascii=False, indent=2))
        return 0

    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        print(f"\nBLOCKED: {TOKEN_ENV_VAR} is not set in this process's environment.",
              file=sys.stderr)
        return 2
    # `token` is used only inside goi() from here on -- never printed,
    # never put in a dict that gets json.dumps'd to stdout, never written
    # to a file.

    print("\n=== 3. Check for an existing Novel from a prior run (idempotency) ===")
    ma, r = goi(a.api, "GET", "/api/novels?mine=true&limit=200", token=token)
    if not kt("GET /api/novels?mine=true -> 200", ma == 200, f"HTTP {ma}"):
        return 1
    existing = next(
        (n for n in r.get("novels", []) if n.get("external_source_url") == SOURCE_URL),
        None)

    if existing:
        novel_id = existing["novel_id"]
        kt("reusing existing Novel from a prior run (no duplicate created)",
           True, f"novel_id={novel_id}")
    else:
        print("\n=== 4. Create the Novel (state=draft by default, never published) ===")
        ma, r = goi(a.api, "POST", "/api/novels", {
            "title": NOVEL_TITLE,
            "description": NOVEL_DESCRIPTION,
            "tags": ["Fanfiction", "Isekai", "Re:Zero"],
            "fandom_names": FANDOM_NAMES,
            "publication_mode": "full_text",
            "external_author_name": "Nonemone (goc AO3) / Yuumeo (dich)",
            "external_source_url": SOURCE_URL,
            "external_chapter_count": 21,
            "language": "vi",
            "characters": CHARACTERS,
            "pairings": PAIRINGS,
            "status": "ongoing",
        }, token=token)
        if not kt("POST /api/novels -> 201", ma == 201, f"HTTP {ma}: {r}"):
            return 1
        novel = r.get("novel") or r
        novel_id = novel.get("novel_id", "")
        if not kt("received novel_id", bool(novel_id)):
            return 1
        kt("Novel created in draft state (not published)",
           novel.get("state", "draft") == "draft", f"state={novel.get('state')}")

        print("\n=== 5. Create the 2 already-acquired Chapters ===")
        chapter_ids: List[str] = []
        for (fname, title, order), text in zip(CHAPTERS, chapters_text):
            ma, r = goi(a.api, "POST", "/api/chapters", {
                "novel_id": novel_id, "title": title, "content": text,
                "order_index": order,
            }, token=token)
            if not kt(f"POST /api/chapters ({fname}) -> 201", ma == 201, f"HTTP {ma}"):
                return 1
            chapter = r.get("chapter") or r
            chapter_ids.append(chapter.get("chapter_id", ""))
        kt("received 2 chapter_ids", len(chapter_ids) == 2 and all(chapter_ids),
           f"{chapter_ids}")

    print("\n=== 6. Verify persistence: fresh GET /api/novels/{id} (owner auth) ===")
    ma, r = goi(a.api, "GET", f"/api/novels/{novel_id}", token=token)
    if not kt("GET /api/novels/{id} -> 200", ma == 200, f"HTTP {ma}"):
        return 1
    novel_view = r.get("novel") or {}
    chapters_view = r.get("chapters") or []
    kt("title matches what was written", novel_view.get("title") == NOVEL_TITLE)
    kt("state is draft (not published)", novel_view.get("state") == "draft",
       f"state={novel_view.get('state')}")
    kt("exactly 2 chapters attached", len(chapters_view) == 2, f"got {len(chapters_view)}")
    chapter_ids_final = [c.get("chapter_id", "") for c in chapters_view]

    print("\n=== 7. Verify NOT in the public/published listing (no auth) ===")
    ma, r = goi(a.api, "GET", "/api/novels?limit=500")
    if not kt("GET /api/novels (public) -> 200", ma == 200, f"HTTP {ma}"):
        return 1
    public_ids = {n.get("novel_id") for n in r.get("novels", [])}
    kt("novel_id absent from public listing", novel_id not in public_ids)

    so_dat = sum(1 for _, ok, _ in KET_QUA if ok)
    so_tong = len(KET_QUA)
    print(f"\n=== SUMMARY: {so_dat}/{so_tong} checks PASS ===")
    print(f"novel_id: {novel_id}")
    print(f"chapter_ids: {chapter_ids_final}")
    for ten, ok, ghi_chu in KET_QUA:
        if not ok:
            print(f"  FAIL: {ten} -- {ghi_chu}")

    return 0 if so_dat == so_tong else 1


if __name__ == "__main__":
    sys.exit(main())
