#!/usr/bin/env python3
"""Chinese Media Watcher — discovery poll (mission "autonomous content
factory", 2026-09-02).

Polls every actionable source's YouTube RSS feed (public, no auth, no
scraping — https://www.youtube.com/feeds/videos.xml?channel_id=... is
YouTube's own documented per-channel upload feed), finds episodes not
already in the content_queue, classifies their rights, and writes a
DISCOVERED queue entry (all processing stages PENDING) for each new one.

Idempotent: re-running finds the same episodes and no-ops on all of them
(store.create_queue_item_once dedupes permanently by item_id, which is
derived deterministically from (platform, episode_ref)).

Does not process anything — that is chinese_media_orchestrator.py's job.
This script only discovers and records.

    python -m scripts.chinese_media_watcher
    python -m scripts.chinese_media_watcher --source bobo_manju
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from server.domain import ChineseMediaQueueItem  # noqa: E402
from server.scraper.chinese_media_sources import (  # noqa: E402
    ChineseMediaSource, actionable_sources, classify_rights, source_by_id,
)
from chinese_media_pipeline import find_source_captions  # noqa: E402

ATOM_NS = "{http://www.w3.org/2005/Atom}"
MEDIA_NS = "{http://search.yahoo.com/mrss/}"
YT_NS = "{http://www.youtube.com/xml/schemas/2015}"

RSS_TIMEOUT = 15


def queue_item_id(platform: str, episode_ref: str) -> str:
    """Tat dinh tu (platform, episode_ref) — day la toan bo co che dedup
    vinh vien: cung mot video luon sinh ra CUNG mot item_id, nen
    `create_queue_item_once` (409 tren Appwrite) tu no chan trung lap."""
    digest = hashlib.sha256(f"{platform}:{episode_ref}".encode("utf-8")).hexdigest()
    return f"cmq_{digest[:16]}"


def fetch_channel_feed(channel_id: str) -> List[dict]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "FanficWorld-ChineseMediaWatcher/1.0"})
    with urllib.request.urlopen(req, timeout=RSS_TIMEOUT) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    entries = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        video_id_el = entry.find(f"{YT_NS}videoId")
        title_el = entry.find(f"{ATOM_NS}title")
        published_el = entry.find(f"{ATOM_NS}published")
        group_el = entry.find(f"{MEDIA_NS}group")
        desc = ""
        if group_el is not None:
            desc_el = group_el.find(f"{MEDIA_NS}description")
            desc = (desc_el.text or "") if desc_el is not None else ""
        entries.append({
            "video_id": video_id_el.text if video_id_el is not None else "",
            "title": title_el.text if title_el is not None else "",
            "published": published_el.text if published_el is not None else "",
            "description": desc,
        })
    return entries


def poll_source(source: ChineseMediaSource, store) -> dict:
    report = {"source_id": source.source_id, "found": 0, "new": 0, "errors": []}
    try:
        entries = fetch_channel_feed(source.channel_id)
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        return report
    report["found"] = len(entries)

    for e in entries:
        video_id = e["video_id"]
        if not video_id:
            continue
        item_id = queue_item_id(source.platform, video_id)

        has_captions = False
        try:
            has_captions = find_source_captions(source.platform, video_id) is not None
        except Exception:
            pass  # caption check is best-effort; missing != unsafe
        rights_mode = classify_rights(description=e["description"],
                                      has_real_captions=has_captions)

        item = ChineseMediaQueueItem(
            item_id=item_id,
            source_id=source.source_id,
            platform=source.platform,
            series_slug=source.source_id,
            episode_ref=video_id,
            title=e["title"],
            source_url=f"https://www.youtube.com/watch?v={video_id}",
            rights_mode=rights_mode,
        )
        _, was_new = store.create_queue_item_once(item)
        if was_new:
            report["new"] += 1
            print(f"  [NEW] {source.display_name}: {e['title']!r} "
                  f"({video_id}) rights_mode={rights_mode}")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", default="", help="chi poll MOT source_id (mac dinh: tat ca)")
    args = ap.parse_args(argv)

    from server.config import load_settings
    from server.appwrite_store import AppwriteMetadataStore

    settings = load_settings()
    store = AppwriteMetadataStore(settings.appwrite)

    if args.source:
        src = source_by_id(args.source)
        if src is None:
            print(json.dumps({"status": "FAIL", "reason": f"unknown source_id: {args.source}"}))
            return 2
        if not src.channel_id:
            print(json.dumps({"status": "FAIL",
                              "reason": f"{args.source} has no resolved channel_id yet"}))
            return 2
        targets = (src,)
    else:
        targets = actionable_sources()

    reports = []
    for src in targets:
        print(f"=== polling {src.display_name} ({src.source_id}) ===")
        reports.append(poll_source(src, store))

    total_found = sum(r["found"] for r in reports)
    total_new = sum(r["new"] for r in reports)
    print(json.dumps({
        "status": "PASS", "sources_polled": len(reports),
        "episodes_found": total_found, "new_items": total_new,
        "reports": reports,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
