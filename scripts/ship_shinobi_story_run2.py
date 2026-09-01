#!/usr/bin/env python3
"""Mission "SHIP AUDIO + KEEP CONTENT FACTORY MOVING" (2026-09-01) — Track B
continuation. Ships 4 more chapters (8, 9, 10, 11) of "Naruto: A Shinobi
Story" into the SAME novel created by `ship_shinobi_story_runner.py`,
bringing the total to 10 real chapters. Same source/license/pipeline as
that script — see its own docstring for full context.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fanfic_credential_broker as broker  # noqa: E402
from mission_g_rezero_draft_runner import DEFAULT_API, goi, kt  # noqa: E402

SCRATCH = Path(
    r"C:\Users\nguye\AppData\Local\Temp\claude\C--Users-nguye-Documents-CapCut-TTS-App"
    r"\9f89efae-a482-4002-af29-02601ce86985\scratchpad")
SOURCE_URL = "https://narutofanon.fandom.com/wiki/Chapter_1:_Uzumaki_Naruto!!"
CHARACTERS_TO_CHECK = ["Naruto"]
MIN_PARAGRAPH_CHARS_FOR_DUPE_CHECK = 40

CHAPTERS: List[tuple] = [
    ("shinobi_ch08_vi.txt", "Chuong 8: Bai Kiem Tra Genin", 8),
    ("shinobi_ch09_vi.txt", "Chuong 9: Y Chi Cua Lua", 9),
    ("shinobi_ch10_vi.txt", "Chuong 10: Huan Luyen Va Nhiem Vu Cua Doi", 10),
    ("shinobi_ch11_vi.txt", "Chuong 11: Vi Khach Hang Te Nhat", 11),
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
        reasons.append(f"missing: {[n for n, ok in names_present.items() if not ok]}")
    if ascii_only_run:
        reasons.append("untranslated ASCII block")
    if len(text) < 500:
        reasons.append(f"too short: {len(text)} chars")
    return {"passed": not reasons, "reasons": reasons}


def main() -> int:
    token = broker.fetch("FAS_HARVESTER_SERVICE_TOKEN")
    if not token:
        print(json.dumps({"status": "BLOCKED", "reason": "no token"}))
        return 2

    ma, r = goi(DEFAULT_API, "GET", "/api/novels?mine=true&limit=200", token=token)
    if not kt("GET /api/novels?mine=true -> 200", ma == 200, f"HTTP {ma}"):
        return 1
    novel = next((n for n in r.get("novels", [])
                 if n.get("external_source_url") == SOURCE_URL), None)
    if not kt("found existing Naruto novel", novel is not None):
        return 1
    novel_id = novel["novel_id"]

    ma, r = goi(DEFAULT_API, "GET", f"/api/novels/{novel_id}", token=token)
    existing_titles = {c["title"] for c in (r.get("chapters") or [])}

    chapter_ids = []
    for fname, title, order in CHAPTERS:
        text = (SCRATCH / fname).read_text(encoding="utf-8")
        qa = qa_check(text)
        kt(f"QA: {fname}", qa["passed"], json.dumps(qa["reasons"], ensure_ascii=False))
        if title in existing_titles:
            kt(f"already exists: {title}", True)
            continue
        ma, r = goi(DEFAULT_API, "POST", "/api/chapters", {
            "novel_id": novel_id, "title": title, "content": text, "order_index": order,
        }, token=token)
        if not kt(f"POST /api/chapters ({fname}) -> 201", ma == 201, f"HTTP {ma}: {r}"):
            continue
        chapter_ids.append((r.get("chapter") or r)["chapter_id"])

    ma, r = goi(DEFAULT_API, "GET", f"/api/novels/{novel_id}", token=token)
    chapters_view = r.get("chapters") or []
    kt("total chapter count >= 10", len(chapters_view) >= 10, f"got {len(chapters_view)}")
    kt("state still draft", (r.get("novel") or {}).get("state") == "draft")

    from mission_g_rezero_draft_runner import KET_QUA  # noqa: E402
    so_dat = sum(1 for _, ok, _ in KET_QUA if ok)
    so_tong = len(KET_QUA)
    print(f"\n=== SUMMARY: {so_dat}/{so_tong} PASS ===")
    print(json.dumps({"novel_id": novel_id, "new_chapter_ids": chapter_ids,
                      "total_chapters": len(chapters_view)}, indent=2))
    return 0 if so_dat == so_tong else 1


if __name__ == "__main__":
    sys.exit(main())
