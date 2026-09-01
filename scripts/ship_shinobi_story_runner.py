#!/usr/bin/env python3
"""Mission "STORY SOURCE EXPANSION + SHIP CHAPTERS" (2026-09-01).

Ships 6 real chapters of "Naruto: A Shinobi Story" (English fan fiction,
narutofanon.fandom.com — a MediaWiki-backed Fandom wiki, CC-BY-SA licensed,
robots.txt-permitting, accessed via the official public MediaWiki Action
API, not scraped). Content was fetched+cleaned+archived by
`fetch_shinobi_chapters.py` (scratch), translated EN->VI via Antigravity
(no Tencent credential exists locally; this is the first already-working
free/subsidized path per the mission's own routing fallback), then QA'd
and shipped here.

Author attribution: RW109 (wiki username Rowan109), per the page's own
`{{Property|RW109}}` template and category tag.

Reads FAS_HARVESTER_SERVICE_TOKEN from the credential broker. Never
publishes: only POST /api/novels, POST /api/chapters, POST /api/jobs, and
GET verification calls.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fanfic_credential_broker as broker  # noqa: E402
from mission_g_rezero_draft_runner import DEFAULT_API, goi, kt  # noqa: E402

SCRATCH = Path(
    r"C:\Users\nguye\AppData\Local\Temp\claude\C--Users-nguye-Documents-CapCut-TTS-App"
    r"\9f89efae-a482-4002-af29-02601ce86985\scratchpad")

SOURCE_URL = "https://narutofanon.fandom.com/wiki/Chapter_1:_Uzumaki_Naruto!!"
NOVEL_TITLE = "Naruto: A Shinobi Story"
CHARACTERS_TO_CHECK = ["Naruto", "Sasuke"]
VOICE_ID = "piper:ngochuyennew"
JOB_POLL_SECONDS = 10
JOB_MAX_WAIT_SECONDS = 600
MIN_PARAGRAPH_CHARS_FOR_DUPE_CHECK = 40

#: (vi filename, chapter title, order_index)
CHAPTERS: List[tuple] = [
    ("shinobi_ch01_vi.txt", "Chuong 1: Uzumaki Naruto!!", 1),
    ("shinobi_ch02_vi.txt", "Chuong 2: Uchiha Sasuke!!", 2),
    ("shinobi_ch03_vi.txt", "Chuong 3: Haruno Sakura!!", 3),
    ("shinobi_ch05_vi.txt", "Chuong 5: Tu That Bai Den Genin", 5),
    ("shinobi_ch06_vi.txt", "Chuong 6: Chon Doi Genin", 6),
    ("shinobi_ch07_vi.txt", "Chuong 7: Hatake Kakashi!!", 7),
]


def qa_check(text: str) -> Dict[str, Any]:
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
    if ascii_only_run:
        reasons.append("long untranslated-looking ASCII block detected")
    if len(text) < 500:
        reasons.append(f"suspiciously short: {len(text)} chars")
    return {"passed": not reasons, "reasons": reasons, "char_count": len(text)}


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

    chapters_text = [SCRATCH.joinpath(fname).read_text(encoding="utf-8")
                      for fname, _, _ in CHAPTERS]

    print("\n=== 2. QA (cheap deterministic) ===")
    qa_results = []
    for (fname, title, order), text in zip(CHAPTERS, chapters_text):
        qa = qa_check(text)
        qa_results.append({"fname": fname, **qa})
        kt(f"QA PASS: {fname}", qa["passed"], json.dumps(qa["reasons"], ensure_ascii=False))

    print("\n=== 3. Idempotent Novel + Chapter creation ===")
    ma, r = goi(DEFAULT_API, "GET", "/api/novels?mine=true&limit=200", token=token)
    if not kt("GET /api/novels?mine=true -> 200", ma == 200, f"HTTP {ma}"):
        return 1
    existing = next(
        (n for n in r.get("novels", []) if n.get("external_source_url") == SOURCE_URL), None)

    if existing:
        novel_id = existing["novel_id"]
        kt("reusing existing Novel (idempotent)", True, f"novel_id={novel_id}")
        ma, r = goi(DEFAULT_API, "GET", f"/api/novels/{novel_id}", token=token)
        existing_chapters = {c["title"]: c["chapter_id"] for c in (r.get("chapters") or [])}
    else:
        ma, r = goi(DEFAULT_API, "POST", "/api/novels", {
            "title": NOVEL_TITLE,
            "description": (
                "Naruto fanfic (nguon: narutofanon.fandom.com, MediaWiki API "
                "cong khai, giay phep CC-BY-SA) - tac gia RW109 (Rowan109). "
                "Dich EN->VI qua Antigravity."),
            "tags": ["Fanfiction", "Shonen"],
            "fandom_names": ["Naruto"],
            "publication_mode": "full_text",
            "external_author_name": "RW109 (Rowan109)",
            "external_source_url": SOURCE_URL,
            "external_chapter_count": 32,
            "language": "vi",
            "characters": ["Naruto Uzumaki", "Sasuke Uchiha", "Sakura Haruno", "Kakashi Hatake"],
            "status": "ongoing",
        }, token=token)
        if not kt("POST /api/novels -> 201", ma == 201, f"HTTP {ma}: {r}"):
            return 1
        novel = r.get("novel") or r
        novel_id = novel["novel_id"]
        kt("Novel created in draft state", novel.get("state", "draft") == "draft",
           f"state={novel.get('state')}")
        existing_chapters = {}

    chapter_ids: List[str] = []
    for (fname, title, order), text in zip(CHAPTERS, chapters_text):
        if title in existing_chapters:
            chapter_ids.append(existing_chapters[title])
            kt(f"reusing existing chapter: {title}", True)
            continue
        ma, r = goi(DEFAULT_API, "POST", "/api/chapters", {
            "novel_id": novel_id, "title": title, "content": text, "order_index": order,
        }, token=token)
        if not kt(f"POST /api/chapters ({fname}) -> 201", ma == 201, f"HTTP {ma}: {r}"):
            continue
        chapter_ids.append((r.get("chapter") or r)["chapter_id"])

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

    print("\n=== 5. TTS chapter 1 ===")
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

    if audio_url:
        import urllib.request
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
        "qa_results": [{"fname": q["fname"], "passed": q["passed"]} for q in qa_results],
    }, ensure_ascii=False, indent=2))
    return 0 if so_dat == so_tong else 1


if __name__ == "__main__":
    sys.exit(main())
