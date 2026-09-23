"""Worker 1: YouTube Fanfic Audio Harvester & Packager.

Pipeline:
1. Search YouTube or inspect direct URL via yt-dlp.
2. Evaluate candidates with Gemini 3.8 Flash (Threshold >= 7.5).
3. Download best audio (MP3 192k) & cover image.
4. Extract subtitles or generate timestamp-synchronized transcript (.srt, .json).
5. Generate rich Vietnamese SEO title & description ready for fanfic.world.
6. Package & auto-sync to Google Drive `FanficWorld/production/works/existing-audio/<slug>`.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
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


from scripts.content_factory.gemini_evaluator import (
    DEFAULT_MODEL,
    QUALITY_THRESHOLD,
    evaluate_content,
    generate_fanfic_world_metadata,
)
from scripts.content_factory.naming import make_production_name, make_production_slug

DRIVE_TARGET_BASE = "fanfic-gdrive:FanficWorld/production/works/existing-audio"
LOCAL_SPOOL_DIR = PROJECT_ROOT / "raw_spool" / "youtube_audio"

_VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
YTDLP_BIN: List[str] = [
    str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable,
    "-m", "yt_dlp",
    "--extractor-args", "youtube:player_client=android,web",
]


MIN_SERIES_DURATION = 18000     # 5 tiếng (18,000s): Yêu cầu tối thiểu >= 5h cho toàn bộ truyện
MIN_SERIES_TOLERANCE = 17100    # 4.75 tiếng: Dung sai chấp nhận được
MAX_SERIES_DURATION = 252000    # 70 tiếng: Hỗ trợ trọn vẹn các bộ full 50-60 tiếng
SERIES_REGEX = re.compile(r"\b(?:tập|tap|part|chương|chuong|hồi|hoi|phần|phan|vol|ep|episode|#)\s*(\d+)\b", re.IGNORECASE)


def _probe_duration(media_path: Path) -> float:
    """Probe actual duration of a media file using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)],
            capture_output=True, text=True, timeout=30
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _slugify(text: str) -> str:
    """Generates a clean URL slug from text."""
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:60].strip("-") or "audio-work"


def check_candidate_series_viability(cand: Dict[str, Any]) -> Tuple[bool, str, bool, Optional[int]]:
    """Checks if candidate is a viable long-form audiobook or part of a series to inspect.
    
    Returns:
        (is_viable, reason, is_series, part_number)
    """
    dur = cand.get("duration") or 0
    title = cand.get("title", "")
    desc = cand.get("description", "")
    url = cand.get("url", "")
    
    m_series = SERIES_REGEX.search(title) or SERIES_REGEX.search(desc[:200])
    is_playlist = "list=" in url or bool(cand.get("playlist_id"))
    is_series = bool(m_series or is_playlist)
    part_num = int(m_series.group(1)) if m_series else (1 if is_playlist else None)

    # 1. Single long compilation video: duration >= 4.75h (17,100s) -> Valid long-form audiobook (>= 5h)!
    if dur >= MIN_SERIES_TOLERANCE:
        hours = dur / 3600
        return True, f"Video audio đạt chuẩn độ dài đơn lẻ: {hours:.1f} tiếng (>= 5h).", is_series, part_num

    # 2. If it's a playlist or series episode, allow it so find_all_series_episodes checks total duration of all existing episodes >= 5h
    if is_series:
        return True, "Ứng viên thuộc bộ/danh sách phát (sẽ tìm toàn bộ các tập đang có để kiểm tra tổng thời lượng >= 5h).", True, part_num

    # 3. Otherwise, if standalone short clip (< 5 hours) without series indicators -> SKIP
    hours = dur / 3600
    return False, f"Bỏ qua: Clip đơn lẻ không thuộc bộ và chưa đạt 5 tiếng ({hours:.1f}h < 5h).", False, None


BOY_LOVE_REGEX = re.compile(
    r"\b(bl|yaoi|danmei|đam\s*mỹ|dam\s*my|boy\s*love|boys\s*love|shounen\s*ai|fujoshi|y-series|blseries|bl_series)\b|#(?:bl|yaoi|blseries|boylove)\b",
    re.IGNORECASE,
)


def search_youtube_candidates(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Searches YouTube and extracts metadata without downloading media."""
    clean_query = f"{query} -bl -yaoi -\"boy love\" -\"đam mỹ\""
    print(f"[Worker1] Tìm kiếm YouTube với từ khóa: '{clean_query}' (tối đa {max_results} ứng viên)...")
    cmd = [
        *YTDLP_BIN,
        f"ytsearch{max_results}:{clean_query}",
        "--dump-json",
        "--flat-playlist",
        "--no-warnings",
        "--ignore-errors",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    candidates: List[Dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            title = item.get("title", "")
            desc = item.get("description", "") or ""
            vid_id = item.get("id", "")
            if BOY_LOVE_REGEX.search(title) or BOY_LOVE_REGEX.search(desc):
                print(f"[Worker1] 🚫 Bỏ qua ứng viên Đam Mỹ / Boy Love: {title[:60]}")
                continue

            # Deduplication: Check ProcessedRegistry
            from scripts.content_factory.processed_tracker import get_processed_registry
            if get_processed_registry().is_processed(vid_id, title):
                print(f"[Worker1] ⏭️ Đã có trong kho sản xuất (Bỏ qua trùng lặp): '{title[:50]}'")
                continue

            dur = item.get("duration", 0) or 0
            candidates.append({
                "id": vid_id,
                "title": title,
                "description": desc,
                "duration": dur,
                "uploader": item.get("uploader", "Unknown"),
                "view_count": item.get("view_count", 0),
                "url": item.get("url") or f"https://www.youtube.com/watch?v={item.get('id')}",
                "playlist_id": item.get("playlist_id"),
                "playlist_title": item.get("playlist_title"),
            })
        except json.JSONDecodeError:
            continue
    print(f"[Worker1] Đã tìm thấy {len(candidates)} ứng viên.")
    return candidates


def inspect_youtube_url(url: str) -> Dict[str, Any]:
    """Inspects a single YouTube URL and extracts detailed metadata."""
    print(f"[Worker1] Đang kiểm tra URL: {url}...")
    cmd = [*YTDLP_BIN, "--dump-json", "--no-warnings", url]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"Lỗi khi kiểm tra URL {url}: {proc.stderr}")
    item = json.loads(proc.stdout.strip())
    return {
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "description": item.get("description", "") or "",
        "duration": item.get("duration", 0) or 0,
        "uploader": item.get("uploader", "Unknown"),
        "view_count": item.get("view_count", 0),
        "url": item.get("webpage_url") or url,
        "thumbnail": item.get("thumbnail", ""),
        "playlist_id": item.get("playlist_id"),
    }


def find_all_series_episodes(candidate: Dict[str, Any], max_episodes: int = 30) -> List[Dict[str, Any]]:
    """Discovers ALL available sibling episodes for a multi-part series or playlist."""
    url = candidate.get("url", "")
    playlist_id = candidate.get("playlist_id")

    # 1. If playlist URL or playlist_id present, pull all items from the playlist
    if "list=" in url or playlist_id:
        p_url = url if "list=" in url else f"https://www.youtube.com/playlist?list={playlist_id}"
        print(f"[Worker1] Phát hiện danh sách phát (Playlist). Đang trích xuất toàn bộ các tập...")
        cmd = [*YTDLP_BIN, "--flat-playlist", "--dump-json", "--no-warnings", p_url]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        p_items = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                dur = item.get("duration", 0) or 0
                p_items.append({
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "description": item.get("description", "") or "",
                    "duration": dur,
                    "uploader": item.get("uploader", candidate.get("uploader", "Unknown")),
                    "view_count": item.get("view_count", 0),
                    "url": item.get("url") or f"https://www.youtube.com/watch?v={item.get('id')}",
                })
                if len(p_items) >= max_episodes:
                    break
            except Exception:
                continue
        if len(p_items) >= 1:
            print(f"[Worker1] Đã tìm thấy {len(p_items)} tập trong Playlist.")
            return p_items

    # 2. Sibling episode search via series pattern
    title = candidate.get("title", "")
    m_part = SERIES_REGEX.search(title)
    if m_part:
        uploader = candidate.get("uploader", "").strip()
        # Clean title to base name by removing the part indicator without eating the rest of title
        base_clean = re.sub(
            r"\b(?:tập|tap|part|chương|chuong|hồi|hoi|phần|phan|vol|ep|episode|#)\s*\d+\b\s*[:|–-]?\s*",
            "",
            title,
            flags=re.IGNORECASE,
        ).strip(" -:–|[]()")

        if len(base_clean) < 5:
            base_clean = title[:m_part.start()].strip(" -:–|[]()") or title[m_part.end():].strip(" -:–|[]()")

        search_query = f"{uploader} {base_clean}".strip() if uploader and uploader != "Unknown" else f"{base_clean} tập".strip()
        print(f"[Worker1] Đang tìm kiếm toàn bộ các tập của bộ truyện: '{search_query}'...")
        siblings = search_youtube_candidates(search_query, max_results=25)

        found_dict: Dict[int, Dict[str, Any]] = {}
        cand_ep_num = int(m_part.group(1))
        found_dict[cand_ep_num] = candidate

        base_words = set(re.findall(r"\w+", base_clean.lower())) - {
            "audiobook", "truyện", "audio", "fanfic", "đồng", "nhân", "full", "hd", "thuyết", "minh", "vietsub"
        }

        for sib in siblings:
            sib_title = sib.get("title", "")
            m_sib = SERIES_REGEX.search(sib_title)
            if not m_sib:
                continue
            sib_ep_num = int(m_sib.group(1))

            sib_words = set(re.findall(r"\w+", sib_title.lower()))
            uploader_match = bool(uploader and uploader.lower() in sib.get("uploader", "").lower())
            overlap_ok = len(base_words & sib_words) >= min(2, len(base_words)) if base_words else True

            # Strictly require same uploader if uploader is known, so we only harvest from designated channel
            if uploader:
                if not uploader_match:
                    continue
            elif not overlap_ok:
                continue

            if sib_ep_num not in found_dict:
                found_dict[sib_ep_num] = sib

        sorted_eps = [found_dict[k] for k in sorted(found_dict.keys())]
        if len(sorted_eps) >= 1:
            print(f"[Worker1] Đã tìm thấy {len(sorted_eps)} tập thuộc bộ truyện: {[f'Tập {k}' for k in sorted(found_dict.keys())]}")
            return sorted_eps[:max_episodes]

    return [candidate]


# Backward-compatible alias
find_series_episodes = find_all_series_episodes


def _try_cloud_download(url: str, dest_slug: str, branch: str = "youtube_audio") -> Optional[Dict]:
    """Attempts to download via Lightning AI CPU Studio /download_and_sync endpoint.

    Returns parsed JSON result dict on success, or None if cloud unavailable/failed.
    """
    try:
        import requests as _req
        from scripts.content_factory.lightning_helper import CPU_TTS_URL, ensure_cpu_tts_studio
        if not ensure_cpu_tts_studio(timeout_seconds=30):
            return None
        base_url = CPU_TTS_URL.rstrip("/")
        # Quick health check
        health = _req.get(f"{base_url}/health", timeout=10)
        if health.status_code != 200:
            ensure_cpu_tts_studio()
        resp = _req.post(
            f"{base_url}/download_and_sync",
            data={
                "url": url,
                "branch": branch,
                "dest_slug": dest_slug,
                "drive_remote": (
                    "fanfic-gdrive:FanficWorld/production/works/existing-audio"
                    if branch == "youtube_audio"
                    else "fanfic-gdrive:FanficWorld/production/works/ai-animation"
                ),
            },
            timeout=660,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "SUCCESS":
                print(
                    f"[Worker1] ☁️ Cloud tải+upload Drive thành công: {data.get('title')} "
                    f"({data.get('time_download_sec')}s tải + {data.get('time_upload_sec')}s upload)"
                )
                return data
            print(f"[Worker1] Cloud trả lỗi: {data}")
        else:
            print(f"[Worker1] Cloud HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        print(f"[Worker1] Không thể dùng Cloud Download ({exc}). Chuyển sang tải local...")
    return None


def download_media_and_subtitles(url: str, output_dir: Path) -> Dict[str, Path]:
    """Downloads best audio as MP3, cover image, and existing subtitles.

    Tries Cloud CPU Studio (/download_and_sync → Google Drive) first for speed.
    Falls back to local yt-dlp if cloud unavailable.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_target = output_dir / "audio.mp3"
    cover_target = output_dir / "cover.jpg"
    dest_slug = output_dir.name

    # ── Cloud-first path ───────────────────────────────────────────────────────
    cloud_result = _try_cloud_download(url, dest_slug, branch="youtube_audio")
    if cloud_result:
        # Files are already on Drive. We still need audio locally for transcript.
        # Try to sync back just this folder from Drive to local output_dir.
        drive_path = cloud_result.get("drive_path", "")
        if drive_path:
            try:
                sync_cmd = ["rclone", "copy", drive_path, str(output_dir), "--no-traverse"]
                subprocess.run(sync_cmd, check=True, timeout=300)
                print(f"[Worker1] Drive→Local sync: {drive_path} → {output_dir}")
            except Exception as sync_exc:
                print(f"[Worker1] Drive sync-back thất bại ({sync_exc}). Sẽ tải local để lấy audio...")
                # Fall through to local download below
                cloud_result = None

    # ── Local fallback path ────────────────────────────────────────────────────
    if not cloud_result or not audio_target.exists():
        print(f"[Worker1] Đang tải audio MP3 và thumbnail về {output_dir} (local)...")
        cmd = [
            *YTDLP_BIN,
            "-N", "4",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "192K",
            "--sponsorblock-remove", "sponsor,intro,outro,selfpromo",
            "--postprocessor-args", "ffmpeg:-threads 2",
            "-o", f"{output_dir}/media.%(ext)s",
            "--no-warnings",
            url,
        ]
        subprocess.run(cmd, check=True)

        # Subtitle attempt: prioritize Vietnamese auto-sub & manual sub
        try:
            sub_cmd = [
                *YTDLP_BIN,
                "--skip-download",
                "--write-sub",
                "--write-auto-sub",
                "--sub-lang", "vi,vi-orig,en",
                "--convert-subs", "srt",
                "-o", f"subtitle:{output_dir}/transcript.%(ext)s",
                "--no-warnings",
                "--ignore-errors",
                url,
            ]
            subprocess.run(sub_cmd, capture_output=True, timeout=60)
        except Exception:
            pass

        # Rename media.mp3 → audio.mp3
        for f in output_dir.glob("media*.mp3"):
            try:
                if audio_target.exists():
                    audio_target.unlink()
                f.replace(audio_target)
            except Exception as rename_err:
                print(f"[Worker1] Cảnh báo rename media→audio: {rename_err}")
                try:
                    shutil.copy2(str(f), str(audio_target))
                    f.unlink()
                except Exception:
                    pass
            break

        # Clean heavy temp files
        for raw_f in list(output_dir.glob("media.*")):
            if raw_f.suffix.lower() in (".webm", ".m4a", ".opus", ".part", ".ytdl"):
                try:
                    raw_f.unlink()
                except Exception:
                    pass

    # Look for thumbnail
    for f in output_dir.glob("cover*.jpg"):
        if f != cover_target:
            f.replace(cover_target)
        break

    # Look for transcript file (.srt or .vtt)
    sub_files = list(output_dir.glob("*.srt")) + list(output_dir.glob("*.vtt"))
    transcript_target = sub_files[0] if sub_files else None

    return {
        "audio": audio_target,
        "cover": cover_target if cover_target.exists() else None,
        "transcript": transcript_target,
    }



def _probe_audio_duration(media_path: Path) -> float:
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)]
        p = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(p.stdout.strip())
    except Exception:
        return 0.0


def ensure_transcript(audio_path: Path, srt_path: Optional[Path], output_dir: Path) -> Path:
    """Ensures a valid synchronized transcript (.srt and .json) exists.
    
    If subtitle exists from YouTube, uses it directly.
    If no subtitle and audio > 2 hours, generates structured chapter timeline markers.
    Otherwise runs faster-whisper.
    """
    final_srt = output_dir / "transcript.srt"
    final_json = output_dir / "transcript.json"

    if srt_path and srt_path.exists() and srt_path.stat().st_size > 50:
        if srt_path.suffix.lower() == ".vtt":
            # Convert simple VTT cues to SRT
            content = srt_path.read_text(encoding="utf-8", errors="replace")
            content = re.sub(r"^WEBVTT[^\n]*\n", "", content)
            content = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", content)
            final_srt.write_text(content, encoding="utf-8")
        elif srt_path != final_srt:
            shutil.copy(srt_path, final_srt)
        print(f"[Worker1] Đã tải thành công phụ đề đồng bộ từ YouTube: {final_srt.name}")
        _convert_srt_to_json(final_srt, final_json)
        return final_srt

    audio_dur = _probe_audio_duration(audio_path)

    # For massive audiobooks (> 2 hours) without YouTube subtitles:
    # generate structured chapter navigation timeline markers every 15-30 mins
    if audio_dur > 7200:
        print(f"[Worker1] Audio dung lượng lớn ({audio_dur/3600:.1f}h). Đang sinh hệ thống mục lục phân đoạn thời gian (Chapter Timeline)...")
        interval = 900.0  # 15 mins
        cues = []
        json_data = []
        cur = 0.0
        idx = 1
        while cur < audio_dur:
            end_t = min(cur + interval, audio_dur)
            s_str = _format_timestamp(cur)
            e_str = _format_timestamp(end_t)
            h_mark = int(cur // 3600)
            m_mark = int((cur % 3600) // 60)
            cue_text = f"[Phần {idx:02d}] Diễn Biến Truyện ({h_mark:02d}h{m_mark:02d}p)"
            cues.append(f"{idx}\n{s_str} --> {e_str}\n{cue_text}\n")
            json_data.append({
                "index": idx,
                "start": cur,
                "end": end_t,
                "text": cue_text,
            })
            cur = end_t
            idx += 1
        final_srt.write_text("\n".join(cues), encoding="utf-8")
        final_json.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[Worker1] Đã tạo mục lục thời gian hoàn tất ({len(json_data)} phân đoạn).")
        return final_srt

    print("[Worker1] Không có phụ đề YouTube. Đang chạy faster-whisper để tạo transcript đồng bộ...")
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(audio_path), vad_filter=True)
        
        cues = []
        json_data = []
        for i, seg in enumerate(segments, start=1):
            text = seg.text.strip()
            if not text:
                continue
            start_str = _format_timestamp(seg.start)
            end_str = _format_timestamp(seg.end)
            cues.append(f"{i}\n{start_str} --> {end_str}\n{text}\n")
            json_data.append({
                "index": i,
                "start": seg.start,
                "end": seg.end,
                "text": text,
            })

        del model
        import gc
        gc.collect()

        final_srt.write_text("\n".join(cues), encoding="utf-8")
        final_json.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[Worker1] Đã tạo transcript hoàn tất ({len(json_data)} câu).")
        return final_srt
    except Exception as exc:
        print(f"[Worker1] Cảnh báo: Lỗi khi chạy whisper ({exc}). Tạo transcript giả định.")
        final_srt.write_text("1\n00:00:00,000 --> 00:00:10,000\n[Audiobook Fanfic Production]\n", encoding="utf-8")
        return final_srt


def _format_timestamp(seconds: float) -> str:
    ms_total = round(seconds * 1000)
    hh, rem = divmod(ms_total, 3_600_000)
    mm, rem = divmod(rem, 60_000)
    ss, ms = divmod(rem, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def _convert_srt_to_json(srt_path: Path, json_path: Path) -> None:
    content = srt_path.read_text(encoding="utf-8", errors="replace")
    blocks = content.strip().split("\n\n")
    json_cues = []
    for b in blocks:
        lines = b.strip().splitlines()
        if len(lines) >= 3:
            time_line = lines[1]
            text = " ".join(lines[2:]).strip()
            parts = time_line.split("-->")
            if len(parts) == 2:
                json_cues.append({
                    "start_time": parts[0].strip(),
                    "end_time": parts[1].strip(),
                    "text": text,
                })
    json_path.write_text(json.dumps(json_cues, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_to_google_drive(local_dir: Path, slug: str) -> str:
    """Syncs completed package to Google Drive via rclone."""
    remote_path = f"{DRIVE_TARGET_BASE}/{slug}"
    print(f"[Worker1] Đang đồng bộ sản phẩm lên Google Drive: {remote_path}...")
    cmd = ["rclone", "copy", str(local_dir), remote_path]
    subprocess.run(cmd, check=True)
    print(f"[Worker1] Đồng bộ Drive hoàn tất: {remote_path}")
    return remote_path


def process_youtube_audio(
    query_or_url: str,
    min_score: float = QUALITY_THRESHOLD,
    auto_sync: bool = True,
    max_episodes: int = 2,
) -> Dict[str, Any]:
    """Full execution pipeline for Worker 1 with series multi-episode harvesting."""
    # 1. Determine whether input is URL or Search Query
    if query_or_url.startswith("http://") or query_or_url.startswith("https://"):
        candidate = inspect_youtube_url(query_or_url)
        candidates = [candidate]
    else:
        candidates = search_youtube_candidates(query_or_url, max_results=6)
        if not candidates:
            raise RuntimeError(f"Không tìm thấy video nào với từ khóa: {query_or_url}")

    # 2. Discover all existing episodes for each candidate & filter by TOTAL series duration >= 5 hours
    approved_candidate = None
    evaluation_info = None
    final_series_episodes: List[Dict[str, Any]] = []

    for cand in candidates:
        is_viable, reason, is_series, part_num = check_candidate_series_viability(cand)
        if not is_viable:
            print(f"[Worker1] Ứng viên '{cand['title'][:40]}...' -> {reason}")
            continue

        # Find ALL available episodes of this series/work
        series_eps = find_all_series_episodes(cand, max_episodes=max_episodes)
        # Check rule: If it's Episode 1 of a multi-part series, Tập 2 MUST be present, otherwise drop the series immediately
        if is_series and part_num == 1 and len(series_eps) < 2 and cand.get("duration", 0) < MIN_SERIES_TOLERANCE:
            print(f"[Worker1] Bỏ qua bộ '{cand['title'][:40]}...': Không tìm thấy tập 2 trong kênh và tập 1 chưa đủ 5 tiếng. Chuyển sang bộ khác.")
            continue

        # Check total series duration >= 5 hours (threshold 17100s = 4.75h)
        total_duration = sum(ep.get("duration", 0) or 0 for ep in series_eps)
        total_hours = total_duration / 3600.0
        if total_duration < MIN_SERIES_TOLERANCE:
            print(f"[Worker1] Bỏ qua bộ '{cand['title'][:40]}...': Tổng thời lượng các tập đang có ({len(series_eps)} tập) chỉ đạt {total_hours:.1f}h (< 5 tiếng).")
            continue

        # Evaluate content quality with Gemini 3.8 Flash
        eval_res = evaluate_content(
            title=cand["title"],
            description_or_snippet=cand.get("description", "") or cand["title"],
            source_type="youtube_audio",
            threshold=min_score,
        )
        print(f"[Worker1] Bộ truyện '{cand['title'][:40]}...' ({len(series_eps)} tập, tổng {total_hours:.1f}h) -> Điểm Gemini: {eval_res.score} (Duyệt: {eval_res.approved})")
        if eval_res.approved:
            approved_candidate = cand
            evaluation_info = eval_res
            final_series_episodes = series_eps
            break

    if not approved_candidate or not evaluation_info or not final_series_episodes:
        raise RuntimeError(f"Không có bộ truyện nào đạt chuẩn tổng thời lượng >= 5 tiếng hoặc điểm chất lượng >= {min_score} từ Gemini 3.8 Flash.")

    total_series_hours = sum(ep.get("duration", 0) or 0 for ep in final_series_episodes) / 3600
    print(f"[Worker1] Đã duyệt bộ truyện đạt chuẩn: '{approved_candidate['title']}' (Tổng {len(final_series_episodes)} tập, {total_series_hours:.1f}h, Điểm: {evaluation_info.score})")
    series_episodes = final_series_episodes

    fandom = evaluation_info.fandom or "Naruto"
    completed_episodes: List[Dict[str, Any]] = []

    last_prod_name = ""
    last_slug = ""
    last_metadata = {}
    last_work_dir = None
    last_drive_path = None

    # Series-level shared Album and artwork
    _raw_series_title = (approved_candidate.get("title") or "series")
    _clean_series_title = re.sub(r"\b(?:tập|tap|part|phần|phan|chương|chuong)\s*\d+\b", "", _raw_series_title, flags=re.IGNORECASE).strip(" -:|")
    series_album_name = make_production_name(fandom=fandom, title=_clean_series_title, part_num=None)
    series_album_dir = LOCAL_SPOOL_DIR / series_album_name
    series_album_dir.mkdir(parents=True, exist_ok=True)
    series_album_cover = series_album_dir / "cover.jpg"

    _series_art_slug = make_production_slug(fandom=fandom, title=_clean_series_title, part="art", default_part_type="art")
    series_art_dir = LOCAL_SPOOL_DIR / "_series_art" / _series_art_slug
    series_art_dir.mkdir(parents=True, exist_ok=True)

    # 4. Harvest each episode in the series
    for ep_idx, ep_item in enumerate(series_episodes, start=1):
        print(f"\n[Worker1] === Đang xử lý Tập {ep_idx}/{len(series_episodes)}: '{ep_item['title']}' ===")
        temp_work_dir = LOCAL_SPOOL_DIR / f"_temp_dl_{ep_item.get('id', ep_idx)}"
        temp_work_dir.mkdir(parents=True, exist_ok=True)

        # Download media, cover, and subtitles into temporary work dir
        media_files = download_media_and_subtitles(ep_item["url"], temp_work_dir)

        # Probe actual audio duration and scan/trim channel advertisements (intro & outro)
        master_audio = media_files["audio"]
        intro_cut = 0.0
        outro_cut = 0.0
        try:
            from scripts.content_factory.promo_cleaner import clean_audio_promo
            clean_audio, intro_cut, outro_cut = clean_audio_promo(master_audio)
            master_audio = clean_audio
        except Exception as promo_err:
            print(f"[Worker1] Bỏ qua quét quảng cáo kênh ({promo_err})")

        actual_dur = _probe_duration(master_audio)
        dur_secs = actual_dur
        dur_hours = round(dur_secs / 3600, 2)

        # ── AUTO-SPLIT LONG AUDIO (>= 5 HOURS) INTO 5-HOUR PARTS ──────────────────
        # Split into ~5.0 hour parts (18,000s) as strictly required
        SPLIT_THRESHOLD = 18000.0  # 5 hours
        SPLIT_SIZE = 18000.0       # 5 hours per split

        if actual_dur > SPLIT_THRESHOLD:
            import math
            num_splits = math.ceil(actual_dur / SPLIT_SIZE)
            print(f"[Worker1] ✂️ Video rất dài ({dur_hours:.1f} tiếng). Tự động chia nhỏ thành {num_splits} tập vào Album '{series_album_name}'...")

            # Generate consistent base series metadata & title ONCE so all parts group cleanly
            base_sub_meta = generate_fanfic_world_metadata(
                title=ep_item["title"],
                text_context=ep_item.get("description", "") + f"\nTrọn bộ audiobook thời lượng {dur_hours:.1f} tiếng.",
                author=ep_item["uploader"],
                source_url=ep_item["url"],
                fandom_hint=evaluation_info.fandom,
            )
            base_series_title = base_sub_meta.get("title_vi") or _clean_series_title

            for split_idx in range(1, num_splits + 1):
                s_start = (split_idx - 1) * SPLIT_SIZE
                s_dur = min(SPLIT_SIZE, actual_dur - s_start)
                split_label = f"Tập {split_idx:02d}"

                split_work_dir = series_album_dir / split_label
                split_work_dir.mkdir(parents=True, exist_ok=True)

                split_slug = make_production_slug(fandom=fandom, title=base_series_title, default_part_type="ep")
                split_slug = f"{split_slug}-tap-{split_idx:02d}"
                sub_meta = dict(base_sub_meta)
                split_title = f"{base_series_title} - {split_label}"

                # Cut audio segment with FFmpeg (-c copy is instant and lossless)
                split_audio_file = split_work_dir / "audio.mp3"
                print(f"[Worker1] Đang cắt {split_label} ({s_start/3600:.1f}h -> {(s_start + s_dur)/3600:.1f}h) -> {series_album_name}/{split_label}...")
                subprocess.run([
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", f"{s_start:.2f}",
                    "-i", str(master_audio.resolve()),
                    "-t", f"{s_dur:.2f}",
                    "-c", "copy",
                    str(split_audio_file.resolve()),
                ], check=True)

                # Generate high-definition 16:9 Anime artwork via Beam GPU with creative title
                split_cover_file = split_work_dir / "cover.jpg"
                try:
                    from scripts.content_factory.cover_generator import generate_landscape_audio_cover
                    generate_landscape_audio_cover(
                        youtube_cover_path="",
                        title=split_title,
                        fandom=fandom,
                        episode_label=split_label,
                        author=ep_item["uploader"],
                        output_path=split_cover_file,
                        use_beam_ai=True,
                        series_art_dir=series_art_dir,
                    )
                except Exception as c_err:
                    print(f"[Worker1] Cảnh báo tạo bìa Beam Cloud: {c_err}")

                if not series_album_cover.exists() and split_cover_file.exists():
                    try:
                        shutil.copy(str(split_cover_file), str(series_album_cover))
                    except Exception:
                        pass

                sub_meta.update({
                    "id": ep_item.get("id", ""),
                    "album_name": series_album_name,
                    "folder_name": f"{series_album_name}/{split_label}",
                    "slug": split_slug,
                    "title_original": split_title,
                    "channel": ep_item["uploader"],
                    "duration_seconds": s_dur,
                    "duration_hours": round(s_dur / 3600, 2),
                    "quality_score": evaluation_info.score,
                    "series_index": split_idx,
                    "series_total": num_splits,
                    "source_url": ep_item["url"],
                    "source_channel": ep_item["uploader"],
                    "source_platform": "YouTube",
                    "source_status": "Đang ra (Ongoing - Chờ cập nhật)" if split_idx < num_splits else "Full (Trọn bộ)",
                    "evaluation_reasoning": evaluation_info.reasoning,
                    "voice_type": "original_youtube",
                    "intro_promo_trimmed_seconds": intro_cut,
                    "outro_promo_trimmed_seconds": outro_cut,
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                })
                (split_work_dir / "metadata.json").write_text(json.dumps(sub_meta, ensure_ascii=False, indent=2), encoding="utf-8")

                # Sync this episode to Google Drive inside the Series Album
                split_drive_path = None
                if auto_sync:
                    split_remote = f"{DRIVE_TARGET_BASE}/{series_album_name}/{split_label}"
                    print(f"[Worker1] Đang đồng bộ {split_label} lên Google Drive: {split_remote}...")
                    subprocess.run(["rclone", "copy", str(split_work_dir), split_remote], check=True)
                    if series_album_cover.exists():
                        subprocess.run(["rclone", "copyto", str(series_album_cover), f"{DRIVE_TARGET_BASE}/{series_album_name}/cover.jpg"], check=False)
                    split_drive_path = split_remote

                completed_episodes.append({
                    "part": split_idx,
                    "folder_name": f"{series_album_name}/{split_label}",
                    "slug": split_slug,
                    "title_vi": sub_meta.get("title_vi", split_title),
                    "drive_path": split_drive_path,
                })
                try:
                    from scripts.content_factory.processed_tracker import get_processed_registry
                    get_processed_registry().mark_processed(ep_item.get("id", ""), ep_item.get("title", ""), f"{series_album_name}/{split_label}", "youtube_audio")
                except Exception:
                    pass
                last_prod_name = f"{series_album_name}/{split_label}"
                last_slug = split_slug
                last_metadata = sub_meta
                last_work_dir = split_work_dir
                last_drive_path = split_drive_path

            # Clean up temporary work dir
            try:
                shutil.rmtree(temp_work_dir, ignore_errors=True)
            except Exception:
                pass
            continue

        # Standard video (duration <= 5 hours): Place as episode inside Series Album
        ep_label = f"Tập {ep_idx:02d}"
        ep_work_dir = series_album_dir / ep_label
        ep_work_dir.mkdir(parents=True, exist_ok=True)

        # Move media from temp to ep_work_dir
        dest_audio = ep_work_dir / "audio.mp3"
        if master_audio.exists():
            shutil.move(str(master_audio), str(dest_audio))
        for f in temp_work_dir.iterdir():
            if f.is_file() and not (ep_work_dir / f.name).exists():
                shutil.move(str(f), str(ep_work_dir / f.name))

        # Ensure synchronized transcript (.srt & .json)
        ensure_transcript(dest_audio, ep_work_dir / "transcript.srt" if (ep_work_dir / "transcript.srt").exists() else None, ep_work_dir)

        # Generate rich metadata for fanfic.world with full source attribution
        print(f"[Worker1] Đang sinh metadata cho tập {ep_idx} bằng Gemini 3.8 Flash...")
        metadata = generate_fanfic_world_metadata(
            title=ep_item["title"],
            text_context=ep_item.get("description", "") + "\n" + evaluation_info.summary,
            author=ep_item["uploader"],
            source_url=ep_item["url"],
            fandom_hint=evaluation_info.fandom,
        )
        source_status = "Full (Trọn bộ)" if dur_secs >= 34200 else "Đang ra (Ongoing - Chờ cập nhật)"
        slug = make_production_slug(fandom=fandom, title=metadata.get("title_vi") or ep_item["title"], default_part_type="ep")
        slug = f"{slug}-tap-{ep_idx:02d}"

        metadata.update({
            "id": ep_item.get("id", ""),
            "album_name": series_album_name,
            "folder_name": f"{series_album_name}/{ep_label}",
            "slug": slug,
            "title_original": ep_item["title"],
            "channel": ep_item["uploader"],
            "duration_seconds": dur_secs,
            "duration_hours": dur_hours,
            "quality_score": evaluation_info.score,
            "series_index": ep_idx,
            "series_total": len(series_episodes),
            "source_url": ep_item["url"],
            "source_channel": ep_item["uploader"],
            "source_platform": "YouTube",
            "source_status": source_status,
            "evaluation_reasoning": evaluation_info.reasoning,
            "voice_type": "original_youtube",
            "intro_promo_trimmed_seconds": intro_cut,
            "outro_promo_trimmed_seconds": outro_cut,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })

        meta_file = ep_work_dir / "metadata.json"
        meta_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        # Write dedicated source.txt
        source_file = ep_work_dir / "source.txt"
        source_content = (
            f"=== THÔNG TIN NGUỒN GỐC TÁC PHẨM (FANFIC.WORLD) ===\n"
            f"Album: {series_album_name}\n"
            f"Tập: {ep_label}\n"
            f"Tác phẩm: {metadata['title_vi']}\n"
            f"Fandom: {fandom}\n"
            f"Kênh phát hành: {ep_item['uploader']}\n"
            f"Đường dẫn gốc (URL): {ep_item['url']}\n"
            f"Thời lượng tác phẩm: {dur_hours} giờ ({dur_secs} giây)\n"
            f"Tình trạng: {source_status}\n"
            f"Thời điểm thu thập: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Ghi chú: Lưu trữ nguồn gốc để phục vụ ghi công (attribution) khi đăng tải lên web và tự động cập nhật phần tiếp theo khi kênh phát hành thêm.\n"
        )
        source_file.write_text(source_content, encoding="utf-8")

        # Generate clean 16:9 Anime Landscape Cover with Fantasy Typography
        try:
            from scripts.content_factory.cover_generator import generate_landscape_audio_cover
            cover_file = ep_work_dir / "cover.jpg"
            generate_landscape_audio_cover(
                youtube_cover_path="",
                title=metadata["title_vi"],
                fandom=fandom,
                episode_label=ep_label,
                author=ep_item["uploader"],
                output_path=cover_file,
                use_beam_ai=True,
                series_art_dir=series_art_dir,
            )
            print(f"[Worker1] Đã sinh ảnh bìa Anime 16:9 ngang siêu nét qua Beam Cloud GPU: {cover_file.name}")
        except Exception as c_exc:
            print(f"[Worker1] Cảnh báo tạo bìa 16:9: {c_exc}")

        if not series_album_cover.exists() and (ep_work_dir / "cover.jpg").exists():
            try:
                shutil.copy(str(ep_work_dir / "cover.jpg"), str(series_album_cover))
            except Exception:
                pass

        # Sync to Google Drive inside Series Album
        drive_path = None
        if auto_sync:
            remote = f"{DRIVE_TARGET_BASE}/{series_album_name}/{ep_label}"
            print(f"[Worker1] Đang đồng bộ {ep_label} lên Google Drive: {remote}...")
            subprocess.run(["rclone", "copy", str(ep_work_dir), remote], check=True)
            if series_album_cover.exists():
                subprocess.run(["rclone", "copyto", str(series_album_cover), f"{DRIVE_TARGET_BASE}/{series_album_name}/cover.jpg"], check=False)
            drive_path = remote

        ep_result = {
            "part": ep_idx,
            "folder_name": f"{series_album_name}/{ep_label}",
            "slug": slug,
            "title_vi": metadata["title_vi"],
            "drive_path": drive_path,
        }
        completed_episodes.append(ep_result)
        try:
            from scripts.content_factory.processed_tracker import get_processed_registry
            get_processed_registry().mark_processed(ep_item.get("id", ""), ep_item.get("title", ""), f"{series_album_name}/{ep_label}", "youtube_audio")
        except Exception:
            pass

        # Clean up temporary dl dir
        try:
            shutil.rmtree(temp_work_dir, ignore_errors=True)
        except Exception:
            pass

        last_prod_name = f"{series_album_name}/{ep_label}"
        last_slug = slug
        last_metadata = metadata
        last_work_dir = ep_work_dir
        last_drive_path = drive_path

    return {
        "status": "SUCCESS",
        "folder_name": last_prod_name,
        "slug": last_slug,
        "title_vi": last_metadata.get("title_vi", approved_candidate["title"]),
        "description_vi": last_metadata.get("description_vi", ""),
        "score": evaluation_info.score,
        "episodes_count": len(completed_episodes),
        "episodes": completed_episodes,
        "local_dir": str(last_work_dir) if last_work_dir else "",
        "drive_path": last_drive_path,
        "files": [f.name for f in last_work_dir.iterdir()] if last_work_dir else [],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Worker 1: YouTube Audio Harvester & Packager")
    parser.add_argument("--query", "-q", type=str, help="YouTube search query or direct URL", required=True)
    parser.add_argument("--min-score", type=float, default=QUALITY_THRESHOLD, help="Minimum Gemini quality score")
    parser.add_argument("--episodes", "-e", type=int, default=2, help="Max episodes to harvest per series")
    parser.add_argument("--no-sync", action="store_true", help="Skip Google Drive sync")
    args = parser.parse_args()

    result = process_youtube_audio(args.query, min_score=args.min_score, auto_sync=not args.no_sync, max_episodes=args.episodes)
    print("\n" + "=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2))

