"""Exports a complete, structured catalog of all finished works ready for fanfic.world web upload.
"""

import datetime
import json
import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.content_factory.dashboard import (
    group_works_by_series,
    scan_all_completed_works,
)


def export_catalog():
    print("Collecting finished works across all 3 branches...")
    works = scan_all_completed_works()
    series_list = group_works_by_series(works)

    catalog = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_series": len(series_list),
        "total_episodes": len(works),
        "branches": {
            "youtube_audio": [],
            "fanfic_tts": [],
            "ai_animation": [],
        },
    }

    for s in series_list:
        branch = s["branch"]
        entry = {
            "series_title": s["series_title"],
            "fandom": s["fandom"],
            "total_episodes": s["total_episodes"],
            "total_duration_hours": round(s["total_duration_seconds"] / 3600, 2),
            "total_duration_formatted": s["total_duration_formatted"],
            "quality_score": s["score"],
            "description": s["description"],
            "episodes": [
                {
                    "title": ep["title"],
                    "ep_num": ep["ep_num"],
                    "ep_label": ep["ep_label"],
                    "duration_seconds": ep["duration_seconds"],
                    "duration_formatted": ep["duration_formatted"],
                    "has_audio": ep["has_audio"],
                    "has_video": ep["has_video"],
                    "has_srt": ep["has_srt"],
                    "voice_name": ep.get("voice_name"),
                }
                for ep in s["episodes"]
            ],
        }
        if branch in catalog["branches"]:
            catalog["branches"][branch].append(entry)

    out_file = PROJECT_ROOT / "raw_spool" / "web_ready_catalog.json"
    out_file.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(series_list)} series ({len(works)} episodes) to {out_file.name}!")
    return catalog


if __name__ == "__main__":
    export_catalog()
