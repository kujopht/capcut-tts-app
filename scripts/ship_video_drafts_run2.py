#!/usr/bin/env python3
"""Mission "CONTENT FACTORY RUN #1" (2026-09-01), Track B continuation —
10 additional real, oEmbed-verified AI-animation video drafts beyond the
first 3 created by `ship_video_drafts_runner.py`.

Same rights decision as the first run (still valid — unchanged since):
all candidate channels are unofficial fan/aggregator uploads with no
verifiable distribution rights, and every one of them (17/17 checked
across both runs) returns an EMPTY caption-track list via YouTube's
public timedtext API — their "MULTI SUB"/"ENG SUB" claims are subtitles
burned into the video image, not real caption tracks. rights_mode=
EMBED_ONLY, subtitle_status=PENDING_SOURCE, no media bytes copied.

Reads FAS_HARVESTER_SERVICE_TOKEN from the credential broker. Never
publishes: only POST /api/novels and GET verification calls.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fanfic_credential_broker as broker  # noqa: E402
from mission_g_rezero_draft_runner import DEFAULT_API, goi, kt  # noqa: E402

VIDEOS: List[Dict[str, Any]] = [
    {"title": "侯母换子：真嫡女重生回来了 (AI动漫)", "creator": "TePi动漫推荐",
     "video_id": "EBwsgB1rRBo", "channel_url": "https://www.youtube.com/@TePi%E5%8A%A8%E6%BC%AB%E6%8E%A8%E8%8D%90"},
    {"title": "胖妞农女 第1集 (AI漫剧)", "creator": "A爱漫剧社",
     "video_id": "emuWAbvnzZk", "channel_url": "https://www.youtube.com/@jayloke8120"},
    {"title": "妈妈的人情账 (50集, AI漫剧)", "creator": "KK爱看",
     "video_id": "K4w5dFVJjvU", "channel_url": "https://www.youtube.com/@KKAIKAN"},
    {"title": "第一门客 (AI漫剧)", "creator": "KK爱看",
     "video_id": "8ctlvFSfKMI", "channel_url": "https://www.youtube.com/@KKAIKAN"},
    {"title": "好女婿，先下手为强 (1~63集, AI漫剧)", "creator": "KK爱看",
     "video_id": "rGCI6Uj1Wew", "channel_url": "https://www.youtube.com/@KKAIKAN"},
    {"title": "一代战神 (1-26集, AI漫剧)", "creator": "关关漫剧",
     "video_id": "KQ51ZcA7uGQ", "channel_url": "https://www.youtube.com/@%E5%85%B3%E5%85%B3%E8%A7%A3%E8%AF%B4"},
    {"title": "2026爆火新番全集已完结 (AI漫剧)", "creator": "擇天紀行",
     "video_id": "t3zsgPWKmJg", "channel_url": "https://www.youtube.com/@chenchangsheng3d"},
    {"title": "天启再临 (1-28集, AI漫剧)", "creator": "关关漫剧",
     "video_id": "xfYpRg86S8c", "channel_url": "https://www.youtube.com/@%E5%85%B3%E5%85%B3%E8%A7%A3%E8%AF%B4"},
    {"title": "不入轮回后，我靠功德系统一路逆袭 (86集, AI漫剧)", "creator": "KK爱看",
     "video_id": "1LyvITAOhdM", "channel_url": "https://www.youtube.com/@KKAIKAN"},
    {"title": "爹爹二婚我享福 (AI短剧)", "creator": "盛世短剧",
     "video_id": "t5QObpNP-CU", "channel_url": "https://www.youtube.com/@ShengshiDrama"},
]


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

    print("\n=== 2. Idempotent lookup of existing drafts (mine) ===")
    ma, r = goi(DEFAULT_API, "GET", "/api/novels?mine=true&limit=200", token=token)
    if not kt("GET /api/novels?mine=true -> 200", ma == 200, f"HTTP {ma}"):
        return 1
    existing_by_url = {n.get("external_source_url"): n for n in r.get("novels", [])}

    created_ids: List[str] = []
    for v in VIDEOS:
        source_url = f"https://www.youtube.com/watch?v={v['video_id']}"
        existing = existing_by_url.get(source_url)
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
                f"(unofficial repost/aggregator channel) -> EMBED_ONLY, no "
                f"media bytes copied."),
            "tags": ["AI-Animation", "Video-Draft"],
            "publication_mode": "metadata_only",
            "external_author_name": v["creator"],
            "external_source_url": source_url,
            "language": "zh",
            "status": "ongoing",
            "platform": "youtube",
            "rights_mode": "EMBED_ONLY",
            "subtitle_status": "PENDING_SOURCE",
            "embed_ref": v["video_id"],
        }, token=token)
        if not kt(f"POST /api/novels: {v['title']} -> 201", ma == 201, f"HTTP {ma}: {r}"):
            continue
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
        kt(f"NOT in public listing: {novel_id}", novel_id not in public_ids)

    from mission_g_rezero_draft_runner import KET_QUA  # noqa: E402
    so_dat = sum(1 for _, ok, _ in KET_QUA if ok)
    so_tong = len(KET_QUA)
    print(f"\n=== SUMMARY: {so_dat}/{so_tong} checks PASS ===")
    print(json.dumps({"video_draft_ids": created_ids}, ensure_ascii=False, indent=2))
    return 0 if so_dat == so_tong else 1


if __name__ == "__main__":
    sys.exit(main())
