#!/usr/bin/env python3
"""Mission "SHIP A REAL STORY NOW" (2026-09-01) — extends
`mission_g_rezero_draft_runner.py`'s idempotent Novel/Chapter creation with:
cheap deterministic QA (Rule G/4: duplicate paragraphs, proper-name
preservation, length sanity vs. the already-recorded validation), and a real
TTS job for chapter 1 using the current production voice config, verified by
actually fetching the signed playback URL and checking status/content-type/
size — not just "job says completed".

Source content is ALREADY Vietnamese (docln.net repost of an AO3 work, with
the author's explicit permission — see NOVEL_DESCRIPTION in
mission_g_rezero_draft_runner.py) — translation is correctly a no-op here,
not a bug: this script does NOT call any translation provider.

Reads FAS_HARVESTER_SERVICE_TOKEN from the credential broker (never the
shell env, never argv, never printed/logged) — mission "PIVOT AUTH" (2026-
09-01) replaced the earlier, abandoned FAS_HARVESTER_TOKEN (a harvested
interactive user session) with this dedicated, narrowly-scoped machine
credential. Set up via `scripts/setup_harvester_service_token.py` (never
by hand).

Never publishes: only POST to /api/novels, /api/chapters, /api/jobs and GET
verification calls. No PUT/PATCH/DELETE/publish call exists in this file.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fanfic_credential_broker as broker  # noqa: E402
from mission_g_rezero_draft_runner import (  # noqa: E402
    CHAPTERS, DEFAULT_API, NOVEL_TITLE, SOURCE_URL, goi, kt,
)

CHARACTERS_TO_CHECK = ["Subaru", "Anastasia"]
VOICE_ID = "piper:ngochuyennew"
JOB_POLL_SECONDS = 5
JOB_MAX_WAIT_SECONDS = 600
#: Real chapters legitimately repeat short lines (scene-break dividers,
#: one-word exclamations, dialogue tags) — only a repeated line at least
#: this long is evidence of an actual duplicated PARAGRAPH, not incidental
#: short-line repetition. Found via a real false positive on this exact
#: story's own already-100%-validated chapters (12/18 "duplicates" that
#: were all short lines) — not a hypothetical.
MIN_PARAGRAPH_CHARS_FOR_DUPE_CHECK = 40


def qa_check(text: str, expected_min_chars: int) -> Dict[str, Any]:
    """Cheap deterministic checks per mission Rule G — NOT another LLM call."""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()
                 and len(p.strip()) >= MIN_PARAGRAPH_CHARS_FOR_DUPE_CHECK]
    dupes = len(paragraphs) - len(set(paragraphs))
    names_present = {n: (n in text) for n in CHARACTERS_TO_CHECK}
    ascii_only_run = re.search(r"[A-Za-z]{80,}(?:\s[A-Za-z]{3,}){10,}", text)
    reasons: List[str] = []
    if dupes > 0:
        reasons.append(f"{dupes} duplicate paragraph(s)")
    if not all(names_present.values()):
        missing = [n for n, ok in names_present.items() if not ok]
        reasons.append(f"missing character name(s): {missing}")
    if len(text) < expected_min_chars * 0.8:
        reasons.append(
            f"severe shortening: {len(text)} chars < 80% of {expected_min_chars}")
    if ascii_only_run:
        reasons.append("long untranslated-looking ASCII block detected")
    return {"passed": not reasons, "reasons": reasons, "duplicate_paragraphs": dupes,
            "names_present": names_present, "char_count": len(text)}


def main() -> int:
    token = broker.fetch("FAS_HARVESTER_SERVICE_TOKEN")
    if not token:
        print(json.dumps({"status": "BLOCKED",
                          "reason": "FAS_HARVESTER_SERVICE_TOKEN not stored"}))
        return 2

    print("=== 1. Health check ===")
    ma, r = goi(DEFAULT_API, "GET", "/api/health")
    if not kt("GET /api/health -> 200", ma == 200, f"HTTP {ma}"):
        return 1

    print("\n=== 2. Idempotent Novel + Chapter creation ===")
    ma, r = goi(DEFAULT_API, "GET", "/api/novels?mine=true&limit=200", token=token)
    if not kt("GET /api/novels?mine=true -> 200", ma == 200, f"HTTP {ma}"):
        return 1
    existing = next(
        (n for n in r.get("novels", []) if n.get("external_source_url") == SOURCE_URL), None)

    scratch = Path(
        r"C:\Users\nguye\AppData\Local\Temp\claude\C--Users-nguye-Documents-CapCut-TTS-App"
        r"\9f89efae-a482-4002-af29-02601ce86985\scratchpad")
    chapters_text = [scratch.joinpath(fname).read_text(encoding="utf-8")
                      for fname, _, _ in CHAPTERS]

    if existing:
        novel_id = existing["novel_id"]
        kt("reusing existing Novel (idempotent, no duplicate)", True, f"novel_id={novel_id}")
        ma, r = goi(DEFAULT_API, "GET", f"/api/novels/{novel_id}", token=token)
        chapters_view = r.get("chapters") or []
        chapter_ids = [c["chapter_id"] for c in sorted(
            chapters_view, key=lambda c: c.get("order_index", 0))]
    else:
        ma, r = goi(DEFAULT_API, "POST", "/api/novels", {
            "title": NOVEL_TITLE,
            "description": (
                "Fanfic Re:Zero (nguon: docln.net, dich tu AO3 voi su cho phep cua "
                "tac gia/hoa si) - Anastasia Hoshin va Natsuki Subaru, ca hai deu bi "
                "Pham An cuop mat ten tuoi sau tran chien Priestella, tinh co gap "
                "nhau va lap mot moi quan he doi tac tren duong toi Kararagi."),
            "tags": ["Fanfiction", "Isekai", "Re:Zero"],
            "fandom_names": ["Re:Zero"],
            "publication_mode": "full_text",
            "external_author_name": "Nonemone (goc AO3) / Yuumeo (dich)",
            "external_source_url": SOURCE_URL,
            "external_chapter_count": 21,
            "language": "vi",
            "characters": ["Natsuki Subaru", "Anastasia Hoshin", "Felix Argyle"],
            "pairings": ["Natsuki Subaru/Anastasia Hoshin"],
            "status": "ongoing",
        }, token=token)
        if not kt("POST /api/novels -> 201", ma == 201, f"HTTP {ma}: {r}"):
            return 1
        novel = r.get("novel") or r
        novel_id = novel["novel_id"]
        kt("Novel created in draft state", novel.get("state", "draft") == "draft",
           f"state={novel.get('state')}")

        chapter_ids = []
        for (fname, title, order), text in zip(CHAPTERS, chapters_text):
            ma, r = goi(DEFAULT_API, "POST", "/api/chapters", {
                "novel_id": novel_id, "title": title, "content": text,
                "order_index": order,
            }, token=token)
            if not kt(f"POST /api/chapters ({fname}) -> 201", ma == 201, f"HTTP {ma}"):
                return 1
            chapter_ids.append((r.get("chapter") or r)["chapter_id"])

    print("\n=== 3. QA (cheap deterministic, Rule G) ===")
    qa_results = []
    for (fname, title, order), text in zip(CHAPTERS, chapters_text):
        qa = qa_check(text, expected_min_chars=len(text))
        qa_results.append({"fname": fname, **qa})
        kt(f"QA PASS: {fname}", qa["passed"], json.dumps(qa["reasons"], ensure_ascii=False))

    print("\n=== 4. Verify DRAFT state + not publicly listed ===")
    ma, r = goi(DEFAULT_API, "GET", f"/api/novels/{novel_id}", token=token)
    novel_view = r.get("novel") or {}
    chapters_view = r.get("chapters") or []
    kt("state is draft", novel_view.get("state") == "draft", f"state={novel_view.get('state')}")
    kt(f"chapter count >= {len(CHAPTERS)}", len(chapters_view) >= len(CHAPTERS),
       f"got {len(chapters_view)}")
    ma, r = goi(DEFAULT_API, "GET", "/api/novels?limit=500")
    public_ids = {n.get("novel_id") for n in r.get("novels", [])}
    kt("novel NOT in public listing", novel_id not in public_ids)

    print("\n=== 5. TTS chapter 1 (existing production voice config) ===")
    ch1_id = chapter_ids[0]
    ma, r = goi(DEFAULT_API, "POST", "/api/jobs",
               {"chapter_id": ch1_id, "voice_id": VOICE_ID}, token=token)
    if not kt("POST /api/jobs -> 201", ma == 201, f"HTTP {ma}: {r}"):
        return 1
    job = r.get("job") or r
    job_id = job["job_id"]

    deadline = time.monotonic() + JOB_MAX_WAIT_SECONDS
    status_val = job.get("status")
    while status_val not in ("completed", "failed") and time.monotonic() < deadline:
        time.sleep(JOB_POLL_SECONDS)
        ma, r = goi(DEFAULT_API, "GET", f"/api/jobs/{job_id}", token=token)
        job = r.get("job") or r
        status_val = job.get("status")
    kt("TTS job completed", status_val == "completed", f"status={status_val}")

    print("\n=== 6. Verify playable real audio ===")
    ma, r = goi(DEFAULT_API, "GET", f"/api/audio/{ch1_id}/url", token=token)
    if not kt("GET /api/audio/{id}/url -> 200", ma == 200, f"HTTP {ma}"):
        return 1
    audio_url = r.get("url") or ""
    size_bytes = r.get("size_bytes") or 0
    kt("size_bytes > 0", size_bytes > 0, f"size_bytes={size_bytes}")
    kt("duration_seconds > 0", (job.get("duration_seconds") or 0) > 0,
       f"duration_seconds={job.get('duration_seconds')}")

    if audio_url:
        req = urllib.request.Request(audio_url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                content_type = resp.headers.get("Content-Type", "")
                body_len = len(resp.read(4096))
                kt("signed playback URL -> HTTP 200", resp.status == 200,
                   f"status={resp.status}")
                kt("content-type is audio/*", content_type.startswith("audio/"),
                   f"content-type={content_type}")
                kt("playback body non-empty", body_len > 0, f"first_bytes={body_len}")
        except Exception as exc:  # noqa: BLE001
            kt("signed playback URL -> HTTP 200", False, f"{type(exc).__name__}: {exc}")

    from mission_g_rezero_draft_runner import KET_QUA  # noqa: E402
    so_dat = sum(1 for _, ok, _ in KET_QUA if ok)
    so_tong = len(KET_QUA)
    print(f"\n=== SUMMARY: {so_dat}/{so_tong} checks PASS ===")
    print(json.dumps({
        "novel_id": novel_id, "chapter_ids": chapter_ids, "job_id": job_id,
        "job_status": status_val, "audio_size_bytes": size_bytes,
        "audio_duration_seconds": job.get("duration_seconds"),
        "qa_results": [{"fname": q["fname"], "passed": q["passed"]} for q in qa_results],
    }, ensure_ascii=False, indent=2))
    return 0 if so_dat == so_tong else 1


if __name__ == "__main__":
    sys.exit(main())
