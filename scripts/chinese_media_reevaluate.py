#!/usr/bin/env python3
"""Danh gia lai do dai cho cac muc DA nam trong `content_queue`.

Cong dieu kien o `chinese_media_watcher.py` chi chan duoc muc MOI. Cac muc da
vao hang doi truoc do van dang `PENDING` va van se bi orchestrator nhat len —
mot nguon 31 gio se chiem ban tieu thu DUY NHAT ca ngay.

Cong cu nay do lai do dai that cua tung muc va, voi muc vuot nguong, danh dau
moi cong doan `SKIPPED` kem ly do nguyen van trong `last_error`.

KHONG XOA GI. Ban ghi hang doi, sieu du lieu, `source_url`, `episode_ref` deu
giu nguyen — chi trang thai cong doan doi. Mot muc bi loai hom nay van tra cuu
duoc, va se chay duoc ngay khi co bo cat nho video dai (muc backlog rieng).

    python -m scripts.chinese_media_reevaluate --dry-run
    python -m scripts.chinese_media_reevaluate
    python -m scripts.chinese_media_reevaluate --max-seconds 1800
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from server.domain import QUEUE_STAGE_STATES  # noqa: E402
from server.scraper import media_eligibility  # noqa: E402

from chinese_media_watcher import probe_duration_seconds  # noqa: E402

STAGES = ("transcript", "translation", "subtitle", "dub", "draft", "render")


def all_items(store, cap: int = 500) -> List:
    """Moi muc dung MOT lan: moi muc co dung mot `transcript_state`."""
    out, seen = [], set()
    for state in QUEUE_STAGE_STATES:
        offset = 0
        while len(out) < cap:
            page = store.list_queue_items_by_state(
                stage="transcript_state", state=state, limit=100, offset=offset)
            if not page:
                break
            for it in page:
                if it.item_id not in seen:
                    seen.add(it.item_id)
                    out.append(it)
            if len(page) < 100:
                break
            offset += 100
    return out


def already_ineligible(item) -> bool:
    return (media_eligibility.is_ineligible_marker(item.last_error)
            and all(getattr(item, f"{s}_state") == "SKIPPED" for s in STAGES))


def has_real_progress(item) -> bool:
    """Muc da lam duoc viec that thi KHONG dong bang.

    Danh dau `SKIPPED` de len mot muc da co transcript/ban dich/draft se vut
    di cong viec da tra tien roi — va lam `last_error` mat dau vet that.
    """
    if item.transcript_key or item.novel_id:
        return True
    return any(getattr(item, f"{s}_state") == "DONE" for s in STAGES)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--max-seconds", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="do va bao cao, khong ghi gi")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--recheck-ineligible", action="store_true",
                    help="do lai ca nhung muc DA bi hoan — dung sau khi nang "
                         "--max-seconds de khoi phuc chung, hoac de cap nhat "
                         "ly do cho chinh xac")
    args = ap.parse_args(argv)

    from server.config import load_settings
    from server.appwrite_store import AppwriteMetadataStore

    store = AppwriteMetadataStore(load_settings().appwrite)
    cap = args.max_seconds or media_eligibility.max_source_seconds()

    rows: List[Dict] = []
    changed = 0
    restored = 0
    for item in all_items(store, args.limit):
        if already_ineligible(item) and not args.recheck_ineligible:
            rows.append({"item_id": item.item_id, "action": "da danh dau truoc do"})
            continue
        if has_real_progress(item):
            rows.append({"item_id": item.item_id,
                         "action": "BO QUA — da co tien do that, khong dong bang"})
            continue

        probed = probe_duration_seconds(item.episode_ref)
        if probed.state == "unavailable":
            verdict = media_eligibility.evaluate_unavailable(cap)
        else:
            verdict = media_eligibility.evaluate(probed.seconds, cap)
        row = {"item_id": item.item_id, "episode_ref": item.episode_ref,
               "duration_seconds": probed.seconds, "probe_state": probed.state,
               "eligible": verdict.eligible,
               "reason": verdict.reason, "title": (item.title or "")[:40]}

        was_deferred = already_ineligible(item)

        if verdict.eligible and was_deferred:
            # HOAN LAI, khong phai xoa vinh vien. Muc bi hoan vi nguong cu
            # phai quay lai duoc khi nguong doi — neu khong thi "deferred" chi
            # la mot cach noi giam cua "vut di".
            if args.dry_run:
                row["action"] = "SE khoi phuc ve PENDING (nay du dieu kien)"
            else:
                fields = {f"{s}_state": "PENDING" for s in STAGES}
                fields["last_error"] = ""
                fields["attempts"] = 0
                store.update_queue_item(item.item_id, **fields)
                row["action"] = "da khoi phuc ve PENDING"
                restored += 1
        elif verdict.eligible:
            row["action"] = "giu nguyen — du dieu kien"
        elif args.dry_run:
            row["action"] = ("SE cap nhat ly do" if was_deferred
                             else "SE danh dau khong du dieu kien")
        else:
            fields = {f"{s}_state": "SKIPPED" for s in STAGES}
            fields["last_error"] = verdict.as_last_error()[:1000]
            store.update_queue_item(item.item_id, **fields)
            row["action"] = ("da cap nhat ly do" if was_deferred
                             else "da danh dau khong du dieu kien")
            if not was_deferred:
                changed += 1
        rows.append(row)

    eligible = [r for r in rows if r.get("eligible")]
    print(json.dumps({
        "status": "PASS", "dry_run": args.dry_run,
        "max_source_seconds": cap,
        "examined": len(rows), "marked_ineligible": changed,
        "restored_to_pending": restored,
        "eligible_remaining": len(eligible),
        "rows": rows,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
