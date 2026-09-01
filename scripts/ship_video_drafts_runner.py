#!/usr/bin/env python3
"""Mission "SHIP 3 CHINESE AI-ANIMATION VIDEO DRAFTS" (2026-09-01).

Creates 3 real DRAFT `Novel` entries (state=draft, publication_mode=
metadata_only) representing 3 real, verified-live AI-animation videos —
reuses Novel/METADATA_ONLY rather than a new collection (see
`server/domain.py::Novel`'s own docstring: METADATA_ONLY already means "we
don't own the content, just metadata + a link to source", exactly what a
video draft needs). The 4 new video-specific fields (platform, rights_mode,
subtitle_status, embed_ref) were added to the Novel schema in this same
commit, migrated onto the live production `novels` collection via
`scripts/setup_appwrite.py --only novels` (purely additive).

RIGHTS DECISION (explicit, from the operator, 2026-09-01): all 3 candidates
are unofficial fan-repost/compilation channels with no verifiable
distribution rights, and a real check of YouTube's public timedtext
caption-track list (no auth, no download) returned EMPTY for every one —
their "MULTI SUB" claim is subtitles burned into the video image, not real
caption tracks. Per the operator's explicit decision: rights_mode=
EMBED_ONLY, subtitle_status=PENDING_SOURCE, NO media bytes copied, NO audio
downloaded, NO ASR run. A bounded parallel search for an officially-
captioned/rights-clear source continues separately; if found, subtitles get
attached to these same draft entries later (idempotent reuse below, keyed
on external_source_url, exactly matches mission_g_rezero_draft_runner.py's
own pattern).

Reads FAS_HARVESTER_TOKEN from the credential broker — never the shell env,
never argv, never printed/logged.

Never publishes: only POST /api/novels and GET verification calls. No
PUT/PATCH/DELETE/publish call exists in this file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fanfic_credential_broker as broker  # noqa: E402
from mission_g_rezero_draft_runner import DEFAULT_API, goi, kt  # noqa: E402

#: Each verified live via the real YouTubeAdapter (public oEmbed, no
#: download) on 2026-09-01 — see scratch probe results this session.
VIDEOS: List[Dict[str, Any]] = [
    {
        "title": "七十二环书津门卫疆 (AI国漫)",
        "creator": "破界动漫局 Anime Club",
        "platform": "youtube",
        "video_id": "jBj06aw67f0",
        "source_url": "https://www.youtube.com/watch?v=jBj06aw67f0",
        "channel_url": "https://www.youtube.com/@PJAnimation01-j1r",
    },
    {
        "title": "瘦下来惊艳全校 EP1~38 (AI漫剧)",
        "creator": "吞噬动漫DevourAnime",
        "platform": "youtube",
        "video_id": "f8qAWvpT-LQ",
        "source_url": "https://www.youtube.com/watch?v=f8qAWvpT-LQ",
        "channel_url": "https://www.youtube.com/@DevourAnime",
    },
    {
        "title": "天命神算 Ep01-30 (AI动漫)",
        "creator": "AI动漫频道",
        "platform": "youtube",
        "video_id": "I8pBeykLauA",
        "source_url": "https://www.youtube.com/watch?v=I8pBeykLauA",
        "channel_url": "https://www.youtube.com/@AI%E5%8A%A8%E6%BC%AB%E9%A2%91%E9%81%93",
    },
]


def main() -> int:
    token = broker.fetch("FAS_HARVESTER_TOKEN")
    if not token:
        print(json.dumps({"status": "BLOCKED", "reason": "FAS_HARVESTER_TOKEN not stored"}))
        return 2

    print("=== 1. Health check ===")
    ma, r = goi(DEFAULT_API, "GET", "/api/health")
    if not kt("GET /api/health -> 200", ma == 200, f"HTTP {ma}"):
        return 1

    print("\n=== 2. Idempotent lookup of existing drafts (mine) ===")
    ma, r = goi(DEFAULT_API, "GET", "/api/novels?mine=true&limit=200", token=token)
    if not kt("GET /api/novels?mine=true -> 200", ma == 200, f"HTTP {ma}"):
        return 1
    existing_by_url = {n.get("external_source_url"): n for n in r.get("novels", [])}

    created_ids: List[str] = []
    for v in VIDEOS:
        existing = existing_by_url.get(v["source_url"])
        if existing:
            novel_id = existing["novel_id"]
            kt(f"reusing existing draft (idempotent): {v['title']}", True,
               f"novel_id={novel_id}")
            created_ids.append(novel_id)
            continue

        ma, r = goi(DEFAULT_API, "POST", "/api/novels", {
            "title": v["title"],
            "description": (
                f"AI-animation video draft. Source: {v['channel_url']} "
                f"(YouTube). Attribution: {v['creator']}. Rights unclear "
                f"(unofficial repost channel) -> EMBED_ONLY, no media bytes "
                f"copied."),
            "tags": ["AI-Animation", "Video-Draft"],
            "publication_mode": "metadata_only",
            "external_author_name": v["creator"],
            "external_source_url": v["source_url"],
            "language": "zh",
            "status": "ongoing",
            "platform": v["platform"],
            "rights_mode": "EMBED_ONLY",
            "subtitle_status": "PENDING_SOURCE",
            "embed_ref": v["video_id"],
        }, token=token)
        if not kt(f"POST /api/novels: {v['title']} -> 201", ma == 201, f"HTTP {ma}: {r}"):
            return 1
        novel = r.get("novel") or r
        novel_id = novel["novel_id"]
        kt(f"created in draft state: {v['title']}", novel.get("state") == "draft",
           f"state={novel.get('state')}")
        created_ids.append(novel_id)

    print("\n=== 3. Verify DRAFT state + not publicly listed ===")
    ma, r = goi(DEFAULT_API, "GET", "/api/novels?limit=500")
    public_ids = {n.get("novel_id") for n in r.get("novels", [])}
    for novel_id in created_ids:
        ma, r = goi(DEFAULT_API, "GET", f"/api/novels/{novel_id}", token=token)
        novel_view = r.get("novel") or {}
        kt(f"state is draft: {novel_id}", novel_view.get("state") == "draft",
           f"state={novel_view.get('state')}")
        kt(f"rights_mode == EMBED_ONLY: {novel_id}",
           novel_view.get("rights_mode") == "EMBED_ONLY",
           f"rights_mode={novel_view.get('rights_mode')}")
        kt(f"NOT in public listing: {novel_id}", novel_id not in public_ids)

    from mission_g_rezero_draft_runner import KET_QUA  # noqa: E402
    so_dat = sum(1 for _, ok, _ in KET_QUA if ok)
    so_tong = len(KET_QUA)
    print(f"\n=== SUMMARY: {so_dat}/{so_tong} checks PASS ===")
    print(json.dumps({"video_draft_ids": created_ids}, ensure_ascii=False, indent=2))
    return 0 if so_dat == so_tong else 1


if __name__ == "__main__":
    sys.exit(main())
