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
import shutil
import subprocess
import sys
from collections import namedtuple
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from server.domain import ChineseMediaQueueItem  # noqa: E402
from server.scraper.chinese_media_sources import (  # noqa: E402
    ChineseMediaSource, actionable_sources, classify_rights, source_by_id,
)
from server.scraper import media_eligibility  # noqa: E402
from chinese_media_pipeline import find_source_captions  # noqa: E402

ATOM_NS = "{http://www.w3.org/2005/Atom}"
MEDIA_NS = "{http://search.yahoo.com/mrss/}"
YT_NS = "{http://www.youtube.com/xml/schemas/2015}"

RSS_TIMEOUT = 15


#: Ket qua do do dai. `state` phan biet ba tinh huong KHAC NHAU ve tuong lai:
#:   "ok"          — do duoc
#:   "unavailable" — video da bi go/rieng tu/chan vung; se KHONG BAO GIO do duoc
#:   "unprobeable" — khong do duoc lan nay; co the do duoc lan sau
#: Gop hai cai cuoi lai se lam nguoi van hanh di tim mot loi cong cu khong
#: ton tai.
DurationProbe = namedtuple("DurationProbe", "seconds state detail")

#: yt-dlp bao video khong con truy cap duoc bang nhung cum nay tren stderr.
_UNAVAILABLE_MARKERS = (
    "video unavailable", "private video", "removed by the uploader",
    "account associated with this video has been terminated",
    "video has been removed", "not available in your country",
    "members-only", "sign in to confirm your age",
)


def probe_duration_seconds(video_id: str, timeout: int = 60) -> DurationProbe:
    """Do dai THAT cua mot video, chi doc SIEU DU LIEU.

    RSS cua YouTube khong mang do dai, nen phai hoi rieng. Dung
    `yt-dlp --skip-download` — dung cong cu va dung cach nguoi van hanh da
    dung o cac lan san xuat truoc (xem
    `docs/reports/production-output-run-2026-09-02.md`). KHONG tai mot byte
    media nao: day van la buoc sieu du lieu, khong phai buoc thu thap.

    Khong do duoc thi ben goi phai coi la "khong du dieu kien" chu khong phai
    "cho qua" — xem `media_eligibility.evaluate`.
    """
    binary = shutil.which("yt-dlp")
    if not binary:
        return DurationProbe(None, "unprobeable", "khong tim thay yt-dlp")
    try:
        proc = subprocess.run(
            [binary, "--skip-download", "--print",
             "%(duration)s", f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace")
    except Exception as exc:
        return DurationProbe(None, "unprobeable", f"{type(exc).__name__}")

    err = (proc.stderr or "").lower()
    if any(m in err for m in _UNAVAILABLE_MARKERS):
        return DurationProbe(None, "unavailable", "yt-dlp: video unavailable")

    raw = (proc.stdout or "").strip().splitlines()
    if not raw:
        return DurationProbe(None, "unprobeable", "yt-dlp khong in gi")
    try:
        return DurationProbe(int(float(raw[0].strip())), "ok", "")
    except ValueError:
        return DurationProbe(None, "unprobeable",
                             f"khong doc duoc: {raw[0][:40]!r}")


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


#: Moi cong doan cua mot muc KHONG DU DIEU KIEN. `SKIPPED` la cach dien dat
#: "co chu dich bo qua" da co san trong schema — khac han `DONE` (khong lam
#: gia la da xong) va khac han `FAILED` (khong co gi hong ca).
#:
#: Mot muc nhu vay VAN duoc ghi lai kem toan bo sieu du lieu, nhung khong bao
#: gio vao hang doi THUC THI: `collect_work` chi lay `PENDING`/`FAILED`, va
#: `content_queue_service.requeue_stage` tu choi xep lai mot cong doan
#: `SKIPPED`. Day la ly do khong can them gia tri enum moi (khong migration).
_INELIGIBLE_STAGES = {f"{s}_state": "SKIPPED" for s in (
    "transcript", "translation", "subtitle", "dub", "draft", "render")}


def poll_source(source: ChineseMediaSource, store, *,
                max_seconds: Optional[int] = None,
                probe: bool = True) -> dict:
    report = {"source_id": source.source_id, "found": 0, "new": 0,
              "new_ineligible": 0, "errors": []}
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

        # CONG DIEU KIEN — chay TRUOC khi muc thanh viec chay duoc.
        # Do dai duoc do mot lan, o day, luc phat hien: de toi luc
        # orchestrator nhat len thi no da chiem mat ban tieu thu duy nhat.
        probed = (probe_duration_seconds(video_id) if probe
                  else DurationProbe(None, "unprobeable", "probe tat"))
        if probed.state == "unavailable":
            verdict = media_eligibility.evaluate_unavailable(max_seconds)
        else:
            verdict = media_eligibility.evaluate(probed.seconds, max_seconds)
        duration = probed.seconds

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
        if not verdict.eligible:
            # Ghi lai DAY DU sieu du lieu, nhung moi cong doan `SKIPPED` va ly
            # do duoc giu nguyen van — khong xoa, khong im lang bo qua.
            for field_name, state in _INELIGIBLE_STAGES.items():
                setattr(item, field_name, state)
            item.last_error = verdict.as_last_error()[:1000]

        _, was_new = store.create_queue_item_once(item)
        if was_new:
            if verdict.eligible:
                report["new"] += 1
                print(f"  [NEW] {source.display_name}: {e['title']!r} "
                      f"({video_id}) rights_mode={rights_mode} "
                      f"duration={duration}s")
            else:
                report["new_ineligible"] += 1
                print(f"  [BO QUA] {source.display_name}: {e['title'][:40]!r} "
                      f"({video_id}) — {verdict.reason}")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", default="", help="chi poll MOT source_id (mac dinh: tat ca)")
    ap.add_argument("--max-seconds", type=int, default=None,
                    help="nguong do dai nguon; mac dinh lay tu "
                         f"${media_eligibility.MAX_SOURCE_SECONDS_ENV} hoac "
                         f"{media_eligibility.DEFAULT_MAX_SOURCE_SECONDS}s")
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

    cap = args.max_seconds or media_eligibility.max_source_seconds()
    reports = []
    for src in targets:
        print(f"=== polling {src.display_name} ({src.source_id}) ===")
        reports.append(poll_source(src, store, max_seconds=cap))

    total_found = sum(r["found"] for r in reports)
    total_new = sum(r["new"] for r in reports)
    total_ineligible = sum(r["new_ineligible"] for r in reports)
    print(json.dumps({
        "status": "PASS", "sources_polled": len(reports),
        "max_source_seconds": cap,
        "episodes_found": total_found, "new_items": total_new,
        "new_ineligible": total_ineligible,
        "reports": reports,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
