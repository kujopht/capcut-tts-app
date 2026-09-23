"""Audio Splitter Engine: Slices Long-form Audiobooks (> 4h) into 3-4h Sequential Episodes.

Key Features:
1. Target episode duration: 3.0 to 4.0 hours (default 3.5h / 12,600s).
2. Lossless MP3 stream slicing using ffmpeg (-c copy) in 1-2 seconds per episode.
3. Subtitle timestamp rebasing: .srt and .json timestamps are sliced and shifted back to 00:00:00.
4. 16:9 Landscape Fantasy Cover art per episode via Beam Cloud AI (Tập 01, Tập 02, Tập 03...).
5. Sequential metadata & source attribution per episode.
6. Optional auto-sync to Google Drive.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.content_factory.silent_subprocess

from scripts.content_factory.cover_generator import generate_landscape_audio_cover
from scripts.content_factory.naming import make_production_name, make_production_slug

DRIVE_TARGET_BASE = "fanfic-gdrive:FanficWorld/production/works/existing-audio"
LOCAL_YOUTUBE_DIR = PROJECT_ROOT / "raw_spool" / "youtube_audio"

# Split parameters
MIN_DURATION_TO_SPLIT = 16200  # 4.5 hours: Only split if longer than 4.5h
TARGET_EPISODE_SECONDS = 12600  # 3.5 hours
MIN_EPISODE_SECONDS = 10800    # 3.0 hours
MAX_EPISODE_SECONDS = 14400    # 4.0 hours


def probe_media_duration(media_path: Path) -> float:
    """Gets duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(proc.stdout.strip())
    except Exception:
        return 0.0


def _parse_srt_timestamp(ts: str) -> float:
    """Converts 00:01:23,456 to seconds."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(ts)


def _format_srt_timestamp(seconds: float) -> str:
    """Converts seconds to 00:01:23,456."""
    ms = round(seconds * 1000)
    hh, rem = divmod(ms, 3_600_000)
    mm, rem = divmod(rem, 60_000)
    ss, ms_rem = divmod(rem, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms_rem:03d}"


def slice_srt_file(src_srt: Path, dest_srt: Path, start_s: float, end_s: float) -> int:
    """Slices and rebases an SRT subtitle file to the given window."""
    if not src_srt.exists():
        return 0

    content = src_srt.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n\s*\n", content.strip())

    sliced_blocks = []
    idx = 1

    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue

        # Check for timestamp line
        time_line = lines[1] if "-->" in lines[1] else (lines[0] if "-->" in lines[0] else None)
        if not time_line or "-->" not in time_line:
            continue

        parts = time_line.split("-->")
        cue_start = _parse_srt_timestamp(parts[0])
        cue_end = _parse_srt_timestamp(parts[1])

        # Check if cue overlaps with current slice window
        if cue_end <= start_s or cue_start >= end_s:
            continue

        # Rebase timestamps
        new_start = max(0.0, cue_start - start_s)
        new_end = max(new_start + 0.1, cue_end - start_s)

        text_lines = lines[2:] if "-->" in lines[1] else lines[1:]
        text = "\n".join(text_lines)

        sliced_blocks.append(
            f"{idx}\n{_format_srt_timestamp(new_start)} --> {_format_srt_timestamp(new_end)}\n{text}"
        )
        idx += 1

    dest_srt.write_text("\n\n".join(sliced_blocks), encoding="utf-8")
    return len(sliced_blocks)


def slice_json_transcript(src_json: Path, dest_json: Path, start_s: float, end_s: float) -> int:
    """Slices and rebases structured JSON cues."""
    if not src_json.exists():
        return 0

    try:
        data = json.loads(src_json.read_text(encoding="utf-8", errors="replace"))
        cues = data if isinstance(data, list) else data.get("cues", [])
    except Exception:
        return 0

    sliced_cues = []
    idx = 1
    def _to_sec(val: Any) -> float:
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            try:
                return _parse_srt_timestamp(val)
            except Exception:
                pass
        return 0.0

    for cue in cues:
        c_start = _to_sec(cue.get("start", cue.get("start_time", 0)))
        c_end = _to_sec(cue.get("end", cue.get("end_time", c_start + 1.0)))

        if c_end <= start_s or c_start >= end_s:
            continue

        new_start = round(max(0.0, c_start - start_s), 3)
        new_end = round(max(new_start + 0.1, c_end - start_s), 3)

        sliced_cues.append({
            "index": idx,
            "start": new_start,
            "end": new_end,
            "text": cue.get("text", "").strip(),
            "speaker": cue.get("speaker", ""),
        })
        idx += 1

    dest_json.write_text(json.dumps(sliced_cues, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(sliced_cues)


def calculate_optimal_slices(total_seconds: float) -> List[Tuple[float, float]]:
    """Calculates optimal [start, end] intervals of ~3.0 - 4.0 hours each."""
    num_episodes = max(2, round(total_seconds / TARGET_EPISODE_SECONDS))
    ep_duration = total_seconds / num_episodes

    slices = []
    curr = 0.0
    for i in range(num_episodes):
        end = total_seconds if i == num_episodes - 1 else curr + ep_duration
        slices.append((round(curr, 2), round(end, 2)))
        curr = end
    return slices


def split_audio_work_directory(
    work_dir: Path,
    auto_sync: bool = True,
    use_beam_covers: bool = True,
) -> List[Dict[str, Any]]:
    """Inspects an existing audio work directory and splits it if duration > 4.5h."""
    work_dir = Path(work_dir)
    audio_file = work_dir / "audio.mp3"
    if not audio_file.exists():
        for f in work_dir.glob("*.mp3"):
            audio_file = f
            break

    if not audio_file.exists():
        print(f"[Splitter] Không tìm thấy file audio.mp3 trong {work_dir.name}")
        return []

    total_dur = probe_media_duration(audio_file)
    if total_dur < MIN_DURATION_TO_SPLIT:
        print(f"[Splitter] Bỏ qua {work_dir.name}: Thời lượng {total_dur/3600:.2f}h < 4.5h (không cần cắt).")
        return []

    # Read existing metadata
    meta_file = work_dir / "metadata.json"
    meta = {}
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass

    fandom = meta.get("fandom_hint") or meta.get("fandom") or "Fanfic"
    base_title = meta.get("title_original") or meta.get("title_vi") or work_dir.name
    clean_base_title = re.sub(r"\b(?:tập|tap|part|phần|phan|chương|chuong)\s*\d+\b", "", base_title, flags=re.IGNORECASE).strip(" -:")

    slices = calculate_optimal_slices(total_dur)
    total_eps = len(slices)
    print(f"\n[Splitter] ✂️ Đang phân chia tác phẩm '{clean_base_title}' ({total_dur/3600:.2f}h) thành {total_eps} tập (mỗi tập ~{total_dur/total_eps/3600:.2f}h)...")

    srt_file = work_dir / "transcript.srt"
    json_file = work_dir / "transcript.json"
    source_txt_file = work_dir / "source.txt"
    raw_cover = work_dir / "cover.jpg"

    created_episodes = []

    # Determine Series Album Name and directories
    album_name = make_production_name(fandom=fandom, title=clean_base_title, part_num=None)
    album_dir = LOCAL_YOUTUBE_DIR / album_name
    album_dir.mkdir(parents=True, exist_ok=True)

    # Put album-level cover if available
    album_cover = album_dir / "cover.jpg"
    if raw_cover.exists() and not album_cover.exists():
        try:
            shutil.copy(str(raw_cover), str(album_cover))
        except Exception:
            pass

    for ep_idx, (start_s, end_s) in enumerate(slices, start=1):
        ep_dur = end_s - start_s
        ep_label = f"Tập {ep_idx:02d}"
        ep_name = f"{album_name} - {ep_label}"
        ep_slug = make_production_slug(fandom=fandom, title=clean_base_title, default_part_type="ep")
        ep_slug = f"{ep_slug}-tap-{ep_idx:02d}"

        ep_dir = album_dir / ep_label
        ep_dir.mkdir(parents=True, exist_ok=True)

        ep_audio = ep_dir / "audio.mp3"
        print(f"[Splitter] -> Cắt {ep_label}/{total_eps:02d}: {start_s/3600:.2f}h -> {end_s/3600:.2f}h ({ep_dur/3600:.2f}h) -> {album_name}/{ep_label}...")

        # 1. Lossless stream copy via ffmpeg (-c copy) to a temporary slice file first
        temp_ep_audio = ep_dir / f"_temp_slice_{ep_idx}.mp3"
        slice_cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(start_s),
            "-i", str(audio_file),
            "-to", str(ep_dur),
            "-c", "copy",
            str(temp_ep_audio),
        ]
        subprocess.run(slice_cmd, check=True)
        if ep_audio.exists():
            try:
                ep_audio.unlink()
            except OSError:
                pass
        temp_ep_audio.replace(ep_audio)

        # 2. Slice and rebase subtitles
        if srt_file.exists():
            slice_srt_file(srt_file, ep_dir / "transcript.srt", start_s, end_s)
        if json_file.exists():
            slice_json_transcript(json_file, ep_dir / "transcript.json", start_s, end_s)

        # 3. Generate 16:9 Landscape Cover (Beam Cloud AI Anime or cleaned)
        ep_cover = ep_dir / "cover.jpg"
        try:
            generate_landscape_audio_cover(
                youtube_cover_path=raw_cover if raw_cover.exists() else ep_cover,
                title=clean_base_title,
                fandom=fandom,
                episode_label=ep_label,
                author=meta.get("author") or meta.get("channel") or "Fanfic.World",
                output_path=ep_cover,
                use_beam_ai=use_beam_covers,
            )
        except Exception as exc:
            print(f"[Splitter] Cảnh báo tạo bìa Tập {ep_idx}: {exc}")
            if raw_cover.exists():
                shutil.copy(raw_cover, ep_cover)

        if not album_cover.exists() and ep_cover.exists():
            try:
                shutil.copy(str(ep_cover), str(album_cover))
            except Exception:
                pass

        # 4. Generate metadata.json
        ep_meta = dict(meta)
        ep_meta.update({
            "folder_name": f"{album_name}/{ep_label}",
            "album_name": album_name,
            "slug": ep_slug,
            "title_vi": f"{clean_base_title} - {ep_label}",
            "series_index": ep_idx,
            "series_total": total_eps,
            "duration_seconds": round(ep_dur, 1),
            "duration_hours": round(ep_dur / 3600, 2),
            "slice_start_seconds": start_s,
            "slice_end_seconds": end_s,
            "total_work_duration_hours": round(total_dur / 3600, 2),
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        (ep_dir / "metadata.json").write_text(json.dumps(ep_meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # 5. Source.txt
        if source_txt_file.exists():
            source_content = source_txt_file.read_text(encoding="utf-8", errors="replace")
            source_content += f"\nPhân đoạn tập: {ep_label}/{total_eps:02d} (Thời lượng: {ep_dur/3600:.2f} giờ)\n"
            (ep_dir / "source.txt").write_text(source_content, encoding="utf-8")

        # 6. Optional Drive sync
        drive_path = None
        if auto_sync:
            remote = f"{DRIVE_TARGET_BASE}/{album_name}/{ep_label}"
            print(f"[Splitter] Đồng bộ {ep_label} lên Google Drive: {remote}...")
            subprocess.run(["rclone", "copy", str(ep_dir), remote], check=True)
            if album_cover.exists():
                subprocess.run(["rclone", "copyto", str(album_cover), f"{DRIVE_TARGET_BASE}/{album_name}/cover.jpg"], check=False)
            drive_path = remote

        try:
            from scripts.content_factory.processed_tracker import get_processed_registry
            vid_id = ep_meta.get("id") or ep_meta.get("video_id", "")
            get_processed_registry().mark_processed(vid_id, clean_base_title, f"{album_name}/{ep_label}", "youtube_audio")
        except Exception:
            pass

        created_episodes.append({
            "part": ep_idx,
            "folder_name": f"{album_name}/{ep_label}",
            "slug": ep_slug,
            "duration_hours": round(ep_dur / 3600, 2),
            "drive_path": drive_path,
        })

    # Archive or remove original unsliced work folder to save local disk
    try:
        archive_dir = LOCAL_YOUTUBE_DIR / "_unsliced_archive"
        archive_dir.mkdir(exist_ok=True)
        shutil.move(str(work_dir), str(archive_dir / work_dir.name))
        print(f"[Splitter] Đã chuyển thư mục gốc chưa cắt vào lưu trữ: {archive_dir / work_dir.name}")
    except Exception as m_exc:
        print(f"[Splitter] Lưu ý: Không thể di chuyển thư mục gốc ({m_exc})")

    return created_episodes


def process_all_existing_audio_works(auto_sync: bool = True, use_beam_covers: bool = True) -> List[Dict[str, Any]]:
    """Retroactively slices all previously harvested YouTube audiobooks > 4.5h."""
    results = []
    if not LOCAL_YOUTUBE_DIR.exists():
        return results

    candidates = [p for p in sorted(LOCAL_YOUTUBE_DIR.iterdir()) if p.is_dir() and not p.name.startswith(("_", "."))]
    print(f"\n[Splitter] 🔍 Bắt đầu rà soát {len(candidates)} bộ audio cũ trong kho sản xuất...")

    for cand in candidates:
        mp3 = cand / "audio.mp3"
        if not mp3.exists():
            continue
        dur = probe_media_duration(mp3)
        if dur >= MIN_DURATION_TO_SPLIT:
            print(f"\n========================================================")
            print(f"[*] PHÁT HIỆN BỘ TRUYỆN DÀI CẦN CHIA NHỎ: {cand.name}")
            print(f"[*] Tổng thời lượng: {dur/3600:.2f} giờ ({dur:.0f}s)")
            print(f"========================================================")
            episodes = split_audio_work_directory(cand, auto_sync=auto_sync, use_beam_covers=use_beam_covers)
            results.extend(episodes)

    print(f"\n[Splitter] ✅ Hoàn tất phân chia kho audio cũ! Đã tạo thành công {len(results)} tập mới chuẩn 3-4 tiếng.")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split Audio Works into 3-4h Episodes")
    parser.add_argument("--all", action="store_true", help="Process all existing audio works in raw_spool/youtube_audio")
    parser.add_argument("--dir", type=str, help="Specific folder path to split")
    parser.add_argument("--no-sync", action="store_true", help="Skip Google Drive sync")
    parser.add_argument("--no-beam", action="store_true", help="Skip Beam Cloud cover generation, use source art")
    args = parser.parse_args()

    if args.all:
        process_all_existing_audio_works(auto_sync=not args.no_sync, use_beam_covers=not args.no_beam)
    elif args.dir:
        split_audio_work_directory(Path(args.dir), auto_sync=not args.no_sync, use_beam_covers=not args.no_beam)
    else:
        print("Usage: python audio_splitter.py --all   OR   python audio_splitter.py --dir <path>")
