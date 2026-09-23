"""Router V4 Content Factory Master Orchestrator.

Coordinates 3 specialized content production pipelines for fanfic.world:
  - Branch 1 (YouTube Audio): Harvest, Gemini 3.8 Flash quality gate, transcript, metadata, sync to Drive.
  - Branch 2 (Fanfic Novel): FanFicFare / Gemini curation, translation, Ngoc Huyen (NghiTTS), synchronized transcript, sync to Drive.
  - Branch 3 (AI Animation): Video harvest, 100% Chinese subtitle & watermark masking, SubVid ASS captions, multi-voice dubbing (Thanh Niên Tự Tin + Nhẹ Ngọt Ngào), sync to Drive.

Usage:
  python -m scripts.content_factory.router_v4_orchestrator --worker youtube --query "naruto audiobook fanfic"
  python -m scripts.content_factory.router_v4_orchestrator --worker fanfic --source "https://archiveofourown.org/works/..."
  python -m scripts.content_factory.router_v4_orchestrator --worker fanfic --source "Chủ đề: Naruto xuyên không thành Uchiha Obito cứu Rin"
  python -m scripts.content_factory.router_v4_orchestrator --worker animation --source "https://www.bilibili.com/video/..."
  python -m scripts.content_factory.router_v4_orchestrator --status
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.content_factory.silent_subprocess


from scripts.content_factory.worker1_youtube_audio import process_youtube_audio
from scripts.content_factory.worker2_text_fanfic import process_text_fanfic
from scripts.content_factory.worker3_ai_animation import (
    process_ai_animation,
    process_ai_animation_series,
)

DRIVE_PRODUCTION_ROOT = "fanfic-gdrive:FanficWorld/production/works"


def get_drive_production_status() -> Dict[str, Any]:
    """Queries Google Drive to summarize works produced across all 3 branches."""
    branches = {
        "existing-audio": f"{DRIVE_PRODUCTION_ROOT}/existing-audio",
        "fanfic-tts": f"{DRIVE_PRODUCTION_ROOT}/fanfic-tts",
        "ai-animation": f"{DRIVE_PRODUCTION_ROOT}/ai-animation",
    }
    status = {}
    for branch_name, remote_path in branches.items():
        cmd = ["rclone", "lsf", "--dirs-only", remote_path]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        dirs = [d.rstrip("/") for d in proc.stdout.splitlines() if d.strip()]
        status[branch_name] = {
            "remote": remote_path,
            "count": len(dirs),
            "items": dirs,
        }
    return status


def run_orchestrator(
    worker: str,
    target: Optional[str] = None,
    min_score: float = 7.5,
    no_sync: bool = False,
    extra_args: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Dispatches job to the appropriate worker branch."""
    worker_clean = worker.lower().strip()
    auto_sync = not no_sync
    extra = extra_args or {}

    print("=" * 70)
    print(f"[*] ROUTER V4 CONTENT FACTORY - ĐIỀU PHỐI SẢN XUẤT")
    print(f"[*] Nhánh: {worker_clean.upper()} | Ngưỡng điểm Gemini: {min_score}")
    print(f"[*] Mục tiêu: {target}")
    print("=" * 70)

    start_time = datetime.datetime.now()

    try:
        if worker_clean in ("youtube", "audio", "worker1"):
            if not target:
                raise ValueError("Thiếu từ khóa hoặc URL cho Worker 1 (--query / --target).")
            max_ep = extra.get("max_episodes", 30)
            res = process_youtube_audio(query_or_url=target, min_score=min_score, auto_sync=auto_sync, max_episodes=max_ep)

        elif worker_clean in ("fanfic", "text", "worker2", "novel"):
            if not target:
                raise ValueError("Thiếu nguồn URL, file, hoặc prompt cho Worker 2 (--source / --target).")
            rate = extra.get("rate", "1.0")
            ch_count = extra.get("chapters", 2)
            res = process_text_fanfic(source=target, min_score=min_score, auto_sync=auto_sync, tts_rate=rate, chapters_per_series=ch_count)

        elif worker_clean in ("animation", "video", "worker3", "anime"):
            if not target:
                raise ValueError("Thiếu URL hoặc đường dẫn video cho Worker 3 (--source / --target).")
            enable_dub = not extra.get("no_dub", False)
            max_ep = extra.get("max_episodes", 15)
            res = process_ai_animation_series(
                query_or_url=target,
                min_score=min_score,
                auto_sync=auto_sync,
                enable_dub=enable_dub,
                max_episodes=max_ep,
            )

        elif worker_clean in ("status", "audit"):
            status_report = get_drive_production_status()
            print("\n[+] Báo cáo trạng thái kho sản xuất Google Drive (FanficWorld):")
            print(json.dumps(status_report, ensure_ascii=False, indent=2))
            return {"status": "SUCCESS", "report": status_report}

        else:
            raise ValueError(f"Không nhận diện được worker '{worker}'. Hỗ trợ: 'youtube', 'fanfic', 'animation', 'status'.")

        duration = (datetime.datetime.now() - start_time).total_seconds()
        res["execution_time_seconds"] = round(duration, 2)
        print("\n" + "=" * 70)
        print(f"[✓] HOÀN TẤT TÁC VỤ SAU {duration:.1f} GIÂY")
        print(f"    - Tiêu đề: {res.get('title_vi', 'N/A')}")
        print(f"    - Điểm chất lượng: {res.get('score', 'N/A')}")
        print(f"    - Slug: {res.get('slug', 'N/A')}")
        print(f"    - Google Drive: {res.get('drive_path', 'Chưa đồng bộ')}")
        print("=" * 70)
        return res

    except Exception as exc:
        print("\n" + "!" * 70)
        print(f"[✗] LỖI QUÁ TRÌNH THỰC THI ({worker_clean}): {exc}")
        print("!" * 70)
        return {
            "status": "FAILED",
            "worker": worker_clean,
            "target": target,
            "error": str(exc),
        }


def main():
    parser = argparse.ArgumentParser(description="Router V4 Content Factory Orchestrator")
    parser.add_argument("--worker", "-w", choices=["youtube", "fanfic", "animation", "status"], required=True,
                        help="Select pipeline worker branch or check status")
    parser.add_argument("--target", "--source", "--query", "-s", "-q", "-t", type=str, default=None,
                        help="Input target: YouTube query/URL, Fanfic URL/prompt, or Animation URL/file")
    parser.add_argument("--min-score", type=float, default=7.5, help="Minimum Gemini 3.8 Flash score (default 7.5)")
    parser.add_argument("--no-sync", action="store_true", help="Do not sync to Google Drive")
    parser.add_argument("--no-dub", action="store_true", help="Disable dubbing for animation")
    parser.add_argument("--rate", type=str, default="1.0", help="TTS speech rate for fanfic")
    parser.add_argument("--max-episodes", type=int, default=15, help="Maximum sequential episodes to process for audio/animation")

    args = parser.parse_args()

    extra = {
        "no_dub": args.no_dub,
        "rate": args.rate,
        "max_episodes": args.max_episodes,
    }

    result = run_orchestrator(
        worker=args.worker,
        target=args.target,
        min_score=args.min_score,
        no_sync=args.no_sync,
        extra_args=extra,
    )
    # Print clean JSON at the end for programmatic consumers
    if args.worker != "status":
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
