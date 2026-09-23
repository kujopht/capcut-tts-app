"""Worker 3: AI Animation Novel Harvester, Watermark Masker & SubVid Dubber.

Pipeline:
1. Ingest/download AI animation video from Bilibili, Douyin, or YouTube via yt-dlp.
2. Transcribe dialogue timestamps using faster-whisper / audio ASR.
3. Translate Chinese/source dialogue to Vietnamese using Gemini 3.8 Flash.
4. Synthesize multi-voice dubbing via CapCut TTS:
   - Male Protagonist: Thanh Niên Tự Tin (BV075_streaming)
   - Female Lead: Nhẹ Ngọt Ngào (BV421_vivn_streaming)
5. Audio ducking: original BGM lowered during speech, crisp voiceover overlay.
6. 100% Chinese subtitle masking (solid black bounding box) + watermark masking.
7. Burn SubVid-style ASS captions (Yellow for male, White for female).
8. Package & auto-sync to Google Drive `FanficWorld/production/works/ai-animation/<slug>`.
"""

from __future__ import annotations

import argparse
import datetime
import gc
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
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.content_factory.silent_subprocess


from scripts.content_factory.cloud_tts_client import synthesize_cloud_tts

from desktop_app.models import VoiceEntry
from desktop_app.tts_service import CancelToken, TtsService
from scripts.content_factory.gemini_evaluator import (
    DEFAULT_MODEL,
    FALLBACK_MODEL,
    QUALITY_THRESHOLD,
    call_gemini,
    evaluate_content,
    extract_json,
    generate_fanfic_world_metadata,
)
from scripts.content_factory.naming import make_production_name, make_production_slug

DRIVE_TARGET_BASE = "fanfic-gdrive:FanficWorld/production/works/ai-animation"
LOCAL_SPOOL_DIR = PROJECT_ROOT / "raw_spool" / "ai_animation"

_VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
YTDLP_BIN: List[str] = [
    str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable,
    "-m", "yt_dlp",
    "--extractor-args", "youtube:player_client=android,web",
]


# Confirmed user voices
VOICE_MALE = "BV075_streaming"       # Thanh Niên Tự Tin
VOICE_FEMALE = "BV421_vivn_streaming"  # Nhẹ Ngọt Ngào


def _slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:60].strip("-") or "ai-animation"


def _format_srt_time(seconds: float) -> str:
    ms_total = round(seconds * 1000)
    hh, rem = divmod(ms_total, 3_600_000)
    mm, rem = divmod(rem, 60_000)
    ss, ms = divmod(rem, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def _format_ass_time(seconds: float) -> str:
    cs_total = round(seconds * 100)
    hh, rem = divmod(cs_total, 360_000)
    mm, rem = divmod(rem, 6000)
    ss, cs = divmod(rem, 100)
    return f"{hh:d}:{mm:02d}:{ss:02d}.{cs:02d}"


def _probe_video_dimensions(video_path: Path) -> Tuple[int, int]:
    """Gets video width and height using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        str(video_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    w, h = proc.stdout.strip().split("x")
    return int(w), int(h)


def _probe_duration(media_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(proc.stdout.strip())


SERIES_REGEX = re.compile(
    r"\b(?:tập|tap|part|chương|chuong|hồi|hoi|phần|phan|vol|ep|episode|#)\s*0*(\d+)\b",
    re.IGNORECASE,
)


def _clean_series_title(title: str) -> str:
    """Extracts clean base title for finding sibling episodes."""
    cleaned = re.sub(r"#\w+", "", title)
    cleaned = re.sub(r"\[.*?\]|\(.*?\)", " ", cleaned)
    cleaned = re.sub(r"\b(?:tập|tap|part|chương|chuong|hồi|hoi|phần|phan|vol|ep|episode|#)\s*\d+\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:full|hd|vietsub|thuyết minh|multi sub|eng sub|anime|official|short)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\s\-_:–|]+", " ", cleaned).strip()
    return cleaned


BOY_LOVE_REGEX = re.compile(
    r"\b(bl|yaoi|danmei|đam\s*mỹ|dam\s*my|boy\s*love|boys\s*love|shounen\s*ai|fujoshi|y-series|blseries|bl_series|bl_anime|blanime)\b|#(?:bl|yaoi|blseries|blanime|boylove|yaoilove)\b",
    re.IGNORECASE,
)


def search_ai_animation_candidates(query: str, max_results: int = 25) -> List[Dict[str, Any]]:
    """Searches YouTube for AI animation candidates and extracts metadata, prioritizing viral videos."""
    clean_query = f"{query} -bl -yaoi -\"boy love\" -\"đam mỹ\""
    print(f"[Worker3] Tìm kiếm phim hoạt hình AI: '{clean_query}' (quét {max_results} ứng viên)...")
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
            dur = item.get("duration", 0) or 0
            views = item.get("view_count", 0) or 0
            raw_title = item.get("title", "")
            raw_desc = item.get("description", "") or ""

            # Strict Blacklist: Exclude all Boy Love / Yaoi / Đam mỹ
            if BOY_LOVE_REGEX.search(raw_title) or BOY_LOVE_REGEX.search(raw_desc):
                print(f"[Worker3] 🚫 Loại bỏ ứng viên vì thuộc thể loại Đam Mỹ / Boy Love: {raw_title[:60]}")
                continue

            # Exclude compilation marathons (e.g., "Full 01-50", "Full 1-100", "All-in-One")
            if re.search(r"\b(full\s*0?1\s*-\s*\d+|all[\s\-_]*in[\s\-_]*one)\b", raw_title, re.IGNORECASE):
                continue

            # Exclude vertical videos and YouTube Shorts (Strict 16:9 Landscape requirement)
            if any(k in raw_title.lower() for k in ("#shorts", "#short", "shorts", "tiktok")):
                continue

            # Target Chinese AI novel animation / Manga drama (AI漫剧 / 动漫 / 动画 / 沙雕动画 / 漫改 / Anime Novel)
            is_anime_manga = any(k in raw_title.lower() or k in raw_desc.lower() for k in (
                "漫剧", "动漫", "动画", "沙雕", "漫改", "anime", "manga", "hoạt hình", "motion comic", "ai短剧", "ai漫剧", "ai动漫", "推文"
            ))
            if not is_anime_manga:
                continue

            # Exclude pure human live-action reviews that are not novel anime adaptations
            if any(k in raw_title.lower() for k in ("review phim", "tóm tắt phim")) and not any(k in raw_title.lower() for k in ("漫剧", "ai漫剧", "ai动漫", "tiểu thuyết")):
                continue

            # Golden duration window: Between 3 minutes (180s) and 120 minutes (7200s)
            if dur > 0 and (dur < 180 or dur > 7200):
                continue

            # Deduplication: Check ProcessedRegistry to prevent re-processing identical video/topic
            from scripts.content_factory.processed_tracker import get_processed_registry
            vid_id = item.get("id", "")
            if get_processed_registry().is_processed(vid_id, raw_title):
                print(f"[Worker3] ⏭️ Đã có trong kho sản xuất (Bỏ qua trùng lặp): '{raw_title[:50]}'")
                continue

            candidates.append({
                "id": vid_id,
                "title": raw_title,
                "description": raw_desc,
                "duration": dur,
                "uploader": item.get("uploader", "Unknown"),
                "view_count": views,
                "url": item.get("url") or f"https://www.youtube.com/watch?v={item.get('id')}",
                "playlist_id": item.get("playlist_id"),
            })
        except json.JSONDecodeError:
            continue

    # Sort candidates by view count descending to prioritize viral hits
    candidates.sort(key=lambda c: c.get("view_count", 0) or 0, reverse=True)
    print(f"[Worker3] Đã tìm thấy {len(candidates)} ứng viên (đã xếp hạng ưu tiên video VIRAL triệu view).")
    return candidates


def inspect_ai_animation_url(url: str) -> Dict[str, Any]:
    """Inspects a single URL and extracts metadata without full download."""
    print(f"[Worker3] Đang kiểm tra URL hoạt hình AI: {url}...")
    cmd = [*YTDLP_BIN, "--dump-json", "--no-warnings", url]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        return {"title": "AI Animation Video", "url": url}
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


def find_all_animation_episodes(candidate: Dict[str, Any], max_episodes: int = 15) -> List[Dict[str, Any]]:
    """Discovers all available sequential sibling episodes for an AI animation series.
    
    Supports:
    1. YouTube Playlists (playlist_id or list=)
    2. Sibling episodes by uploader + base title pattern (Tập 1 -> Tập 2 -> ...)
    """
    url = candidate.get("url", "")
    playlist_id = candidate.get("playlist_id")

    # 1. Playlist extraction
    if "list=" in url or playlist_id:
        p_url = url if "list=" in url else f"https://www.youtube.com/playlist?list={playlist_id}"
        print(f"[Worker3] Phát hiện danh sách phát (Playlist). Đang trích xuất toàn bộ các tập...")
        cmd = [*YTDLP_BIN, "--flat-playlist", "--dump-json", "--no-warnings", p_url]

        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        p_items: List[Dict[str, Any]] = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                dur = item.get("duration", 0) or 0
                if dur > 7200.0 or (0 < dur < 180.0):
                    continue  # Filter out compilations > 120m or teasers < 3m
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
            print(f"[Worker3] Đã tìm thấy {len(p_items)} tập trong Playlist.")
            return p_items

    # 2. Sibling episode detection by title pattern
    title = candidate.get("title", "")
    m_part = SERIES_REGEX.search(title)
    if m_part:
        uploader = candidate.get("uploader", "").strip()
        base_clean = _clean_series_title(title)
        if len(base_clean) < 3:
            base_clean = title[:m_part.start()].strip(" -:–|[]()")

        search_query = f"{uploader} {base_clean}".strip() if uploader and uploader != "Unknown" else f"{base_clean}".strip()
        print(f"[Worker3] Đang quét toàn bộ các tập của bộ phim hoạt hình AI: '{search_query}'...")
        siblings = search_ai_animation_candidates(search_query, max_results=25)

        found_dict: Dict[int, Dict[str, Any]] = {}
        cand_ep_num = int(m_part.group(1))
        found_dict[cand_ep_num] = candidate

        base_words = set(re.findall(r"\w+", base_clean.lower())) - {
            "anime", "ai", "animation", "full", "hd", "sub", "vietsub", "official", "series"
        }

        for sib in siblings:
            sib_title = sib.get("title", "")
            m_sib = SERIES_REGEX.search(sib_title)
            if not m_sib:
                continue
            sib_ep_num = int(m_sib.group(1))
            sib_dur = sib.get("duration", 0) or 0
            if sib_dur > 3600.0 or (0 < sib_dur < 180.0):
                continue  # Filter out compilations > 60m or teasers < 3m

            sib_words = set(re.findall(r"\w+", sib_title.lower()))
            uploader_match = bool(uploader and uploader.lower() in sib.get("uploader", "").lower())
            overlap_ok = len(base_words & sib_words) >= min(1, len(base_words)) if base_words else True

            if uploader_match or overlap_ok:
                if sib_ep_num not in found_dict:
                    found_dict[sib_ep_num] = sib

        sorted_eps = [found_dict[k] for k in sorted(found_dict.keys())]
        if len(sorted_eps) >= 1:
            ep_labels = [f"Tập {k:02d}" for k in sorted(found_dict.keys())]
            print(f"[Worker3] Đã phát hiện {len(sorted_eps)} tập thuộc bộ phim: {ep_labels}")
            return sorted_eps[:max_episodes]

    return [candidate]


@dataclass
class DialogueLine:
    index: int
    start: float
    end: float
    original_text: str
    vi_text: str = ""
    speaker_gender: str = "male"  # "male" or "female"


def download_video(url: str, output_dir: Path) -> Tuple[Path, Optional[Path], Dict[str, Any]]:
    """Downloads highest quality MP4 video and thumbnail using yt-dlp.

    Tries Cloud CPU Studio (/download_and_sync → Google Drive) first for speed.
    Falls back to local yt-dlp if cloud unavailable.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[Worker3] Đang tải video hoạt hình AI từ: {url}...")

    # First get metadata (always local — fast, just JSON)
    dump_cmd = [*YTDLP_BIN, "--dump-json", "--extractor-args", "youtube:player_client=android,web", "--no-warnings", url]
    dump_p = subprocess.run(dump_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    info = json.loads(dump_p.stdout.strip()) if dump_p.returncode == 0 else {"title": "AI Animation Episode"}

    video_path = output_dir / "raw_video.mp4"
    cover_path = output_dir / "cover.jpg"

    # ── Cloud-first path ───────────────────────────────────────────────────────
    cloud_ok = False
    try:
        from scripts.content_factory.lightning_helper import CPU_TTS_URL, ensure_cpu_tts_studio
        import requests as _req
        base_url = CPU_TTS_URL.rstrip("/")
        health = _req.get(f"{base_url}/health", timeout=10)
        if health.status_code != 200:
            ensure_cpu_tts_studio()
        dest_slug = output_dir.name
        resp = _req.post(
            f"{base_url}/download_and_sync",
            data={
                "url": url,
                "branch": "ai_animation",
                "dest_slug": dest_slug,
                "drive_remote": "fanfic-gdrive:FanficWorld/production/works/ai-animation",
            },
            timeout=660,
        )
        if resp.status_code == 200 and resp.json().get("status") == "SUCCESS":
            data = resp.json()
            print(
                f"[Worker3] ☁️ Cloud tải+upload Drive: {data.get('title')} "
                f"({data.get('time_download_sec')}s tải + {data.get('time_upload_sec')}s upload)"
            )
            # Sync back video from Drive to local for GPU processing
            drive_path = data.get("drive_path", "")
            if drive_path:
                sync_cmd = ["rclone", "copy", drive_path, str(output_dir), "--no-traverse"]
                subprocess.run(sync_cmd, check=True, timeout=600)
                print(f"[Worker3] Drive→Local sync: {drive_path} → {output_dir}")
            # Rename if needed
            for f in output_dir.glob("video*.mp4"):
                if f != video_path:
                    f.replace(video_path)
                break
            cloud_ok = video_path.exists()
    except Exception as exc:
        print(f"[Worker3] Cloud Download thất bại ({exc}). Chuyển sang tải local...")

    # ── Local fallback path ────────────────────────────────────────────────────
    if not cloud_ok:
        dl_cmd = [
            *YTDLP_BIN,
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--extractor-args", "youtube:player_client=android,web",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
            "-o", str(video_path),
            "-o", f"thumbnail:{output_dir}/cover.%(ext)s",
            "--no-warnings",
            url,
        ]
        subprocess.run(dl_cmd, check=True)

    actual_cover = None
    for f in output_dir.glob("cover*.jpg"):
        actual_cover = f
        break

    return video_path, actual_cover, info



DEFAULT_BEAM_ANIMATION_URL = "https://animation-worker-39debc4-v4.app.beam.cloud"
DEFAULT_LIGHTNING_WHISPER_URL = "https://8000-01m2cvchyakxz65erd7j1vkcna.cloudspaces.litng.ai"


def transcribe_dialogue(audio_path: Path) -> List[DialogueLine]:
    """Transcribes audio with exact timestamps using Beam Cloud RTX 4090 GPU, Lightning AI, or local CPU."""
    # 1. Prioritize Beam Cloud RTX 4090 GPU
    beam_url = os.environ.get("BEAM_ANIMATION_URL", DEFAULT_BEAM_ANIMATION_URL).rstrip("/")
    if beam_url:
        try:
            from scripts.beam_credential import resolve_beam_token
            beam_token = resolve_beam_token()
            headers = {"Authorization": f"Bearer {beam_token}"} if beam_token else {}
            print(f"[Worker3] 🚀 Đang gửi audio sang Beam Cloud RTX 4090 GPU ({beam_url})...")
            with open(audio_path, "rb") as af:
                resp = requests.post(f"{beam_url}/transcribe", headers=headers, files={"file": af}, timeout=450)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "SUCCESS":
                    lines = [
                        DialogueLine(
                            index=item["index"],
                            start=float(item["start"]),
                            end=float(item["end"]),
                            original_text=item["original_text"],
                        )
                        for item in data.get("lines", [])
                    ]
                    print(f"[Worker3] ⚡ Nhận diện thành công {len(lines)} câu qua Beam Cloud RTX 4090 (Thời gian: {data.get('elapsed_seconds')}s)!")
                    return lines
                else:
                    print(f"[Worker3] Cảnh báo từ Beam Cloud: {data.get('detail', data)}. Fallback...")
            else:
                print(f"[Worker3] Beam Cloud server trả HTTP {resp.status_code}. Fallback...")
        except Exception as exc:
            print(f"[Worker3] Không thể kết nối Beam Cloud GPU ({exc}). Fallback...")

    # 2. Try Lightning AI GPU
    remote_url = os.environ.get("LIGHTNING_WHISPER_URL", DEFAULT_LIGHTNING_WHISPER_URL).rstrip("/")
    if remote_url:
        for attempt in range(2):
            try:
                print(f"[Worker3] 🚀 Đang gửi audio sang Lightning AI L4 GPU ({remote_url})...")
                with open(audio_path, "rb") as af:
                    resp = requests.post(f"{remote_url}/transcribe", files={"file": af}, timeout=300)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "SUCCESS":
                        lines = [
                            DialogueLine(
                                index=item["index"],
                                start=float(item["start"]),
                                end=float(item["end"]),
                                original_text=item["original_text"],
                            )
                            for item in data.get("lines", [])
                        ]
                        print(f"[Worker3] ⚡ Nhận diện thành công {len(lines)} câu qua Lightning AI L4 GPU!")
                        return lines
                    else:
                        print(f"[Worker3] Cảnh báo từ Lightning GPU: {data.get('error')}. Fallback cục bộ...")
                        break
                else:
                    print(f"[Worker3] Lightning server trả HTTP {resp.status_code}.")
            except Exception as exc:
                print(f"[Worker3] Không thể kết nối Lightning GPU ({exc}).")

            if attempt == 0:
                try:
                    from scripts.content_factory.lightning_helper import ensure_gpu_worker_studio
                    print("[Worker3] 💤 Đang thử tự động đánh thức L4 GPU Studio (On-Demand Wake)...")
                    if not ensure_gpu_worker_studio():
                        break
                except Exception as e:
                    print(f"[Worker3] Không thể tự động đánh thức GPU: {e}")
                    break


    print("[Worker3] Đang nhận diện khẩu hình và phụ đề qua faster-whisper (CPU)...")
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments_iter, info = model.transcribe(str(audio_path), vad_filter=True)
    
    lines: List[DialogueLine] = []
    for i, seg in enumerate(segments_iter, start=1):
        txt = seg.text.strip()
        if txt:
            lines.append(DialogueLine(index=i, start=seg.start, end=seg.end, original_text=txt))
            if len(lines) % 50 == 0:
                print(f"[Worker3] Tiến độ Whisper CPU: đã nhận diện {len(lines)} câu thoại (mốc {seg.end:.1f}s)...")
    print(f"[Worker3] Đã phát hiện tổng cộng {len(lines)} câu đối thoại.")
    del model
    gc.collect()
    return lines


def translate_and_assign_speakers(lines: List[DialogueLine]) -> None:
    """Translates dialogue into Vietnamese and assigns male/female speaker roles via Gemini 3.8 Flash."""
    if not lines:
        return
    print(f"[Worker3] Gemini 3.8 Flash đang dịch và phân vai nhân vật cho {len(lines)} câu thoại...")
    
    chunk_size = 50
    for chunk_start in range(0, len(lines), chunk_size):
        chunk = lines[chunk_start:chunk_start + chunk_size]
        payload = [{"index": l.index, "text": l.original_text} for l in chunk]

        prompt = f"""Dưới đây là các câu thoại của video hoạt hình anime/tiểu thuyết 2D (Chibi/Puppet/Manga) thể loại Học Đường & Đô Thị Ngọt Sủng (Campus Romance):
{json.dumps(payload, ensure_ascii=False, indent=2)}

Nhiệm vụ của bạn:
1. Dịch từng câu sang tiếng Việt tự nhiên, trẻ trung, giàu cảm xúc chuẩn phong cách ngôn tình học đường / thanh xuân vườn trường:
   - Xưng hô phù hợp bối cảnh học đường/đô thị: anh - em, cậu - tớ, bạn học, hoa khôi, học tỷ/học muội, học trưởng, tiền bối - hậu bối...
2. Dựa vào ngữ cảnh câu chuyện, xưng hô và nội dung, phân định CHÍNH XÁC vai nhân vật là "female" (nữ) hay "male" (nam):
   - Nữ chính / Hoa khôi trường / Nữ sinh / Học tỷ / Bạn nữ / Bạn gái / Mẹ / Giọng nữ hệ thống -> BẮT BUỘC là "female".
   - ĐẶC BIỆT CHÚ Ý: Nếu tác phẩm kể từ góc nhìn của nữ chính (xưng tôi/em/mình/nữ chủ, hoặc độc thoại suy nghĩ của nhân vật nữ), lời dẫn và suy nghĩ này BẮT BUỘC PHẢI LÀ "female".
   - Nam chính / Bạn nam / Học trưởng / Thầy giáo / Bạn cùng phòng nam / Lời dẫn nam chủ -> là "male".
   - Hãy cân bằng và phân vai rõ ràng giữa nhân vật nam và nữ, TUYỆT ĐỐI KHÔNG để dồn hết câu thoại về một giọng đơn điệu!

BẮT BUỘC trả về ĐÚNG MỘT JSON ARRAY chứa các đối tượng:
```json
[
  {{"index": {chunk[0].index}, "vi_text": "...", "speaker_gender": "male hoặc female"}}
]
```
Chỉ trả về JSON array, không kèm giải thích.
"""
        parsed_ok = False
        for retry in range(2):
            try:
                raw = call_gemini(prompt, model=DEFAULT_MODEL, timeout_seconds=120)
                arr = extract_json(raw)
                if isinstance(arr, list):
                    mapping = {item["index"]: item for item in arr if isinstance(item, dict) and "index" in item}
                    for line in chunk:
                        if line.index in mapping:
                            line.vi_text = str(mapping[line.index].get("vi_text", line.original_text)).strip()
                            raw_g = str(mapping[line.index].get("speaker_gender", "male")).strip().lower()
                            if raw_g in ["female", "nữ", "nu", "f", "girl", "woman"]:
                                line.speaker_gender = "female"
                            else:
                                line.speaker_gender = "male"
                    parsed_ok = True
                    break
            except Exception as exc:
                print(f"[Worker3] Thử lại dịch batch {chunk_start + 1}-{chunk_start + len(chunk)} (lần {retry + 1}): {exc}")

        curr_done = min(chunk_start + len(chunk), len(lines))
        print(f"[Worker3] Tiến độ dịch & phân vai: {curr_done}/{len(lines)} câu thoại...")

        if not parsed_ok:
            print(f"[Worker3] Cảnh báo: Không parse được JSON batch {chunk_start + 1}-{chunk_start + len(chunk)}.")
            for line in chunk:
                if not line.vi_text:
                    line.vi_text = line.original_text


def build_subvid_ass(lines: List[DialogueLine], ass_path: Path, width: int = 1280, height: int = 720) -> None:
    """Generates SubVid-style ASS subtitles with distinct colors for Male and Female characters."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: MaleVoice,Arial,32,&H002BF7FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.5,1,2,20,20,20,1
Style: FemaleVoice,Arial,32,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.5,1,2,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for l in lines:
        if not l.vi_text.strip():
            continue
        style_name = "FemaleVoice" if l.speaker_gender == "female" else "MaleVoice"
        start_ass = _format_ass_time(l.start)
        end_ass = _format_ass_time(l.end)
        events.append(f"Dialogue: 0,{start_ass},{end_ass},{style_name},,0,0,20,,{l.vi_text}")

    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    print(f"[Worker3] Đã tạo tệp phụ đề ASS phong cách SubVid: {ass_path.name}")


def build_srt(lines: List[DialogueLine], srt_path: Path) -> None:
    cues = []
    for l in lines:
        if not l.vi_text.strip():
            continue
        cues.append(f"{l.index}\n{_format_srt_time(l.start)} --> {_format_srt_time(l.end)}\n{l.vi_text}\n")
    srt_path.write_text("\n".join(cues), encoding="utf-8")


def synthesize_multivoice_dubbing(
    lines: List[DialogueLine],
    total_duration: float,
    output_audio_path: Path,
) -> Path:
    """Synthesizes dialogue with CapCut TTS (Thanh Niên Tự Tin + Nhẹ Ngọt Ngào) and builds ducked track."""
    service = TtsService()
    temp_dir = Path(tempfile.mkdtemp(prefix="worker3_dub_"))
    
    entries = []
    cursor = 0.0

    # 1. Parallel TTS synthesis for all dialogue lines
    valid_lines = [
        l for l in lines 
        if l.vi_text.strip() and not re.search(r"[\u4e00-\u9fff]", l.vi_text)
    ]
    print(f"[Worker3] Bắt đầu tổng hợp song song {len(valid_lines)} câu thoại qua CapCut TTS trực tiếp (4 luồng: Nam=BV075_streaming, Nữ=BV421_vivn_streaming)...")
    
    line_parts: Dict[int, Path] = {}
    from capcut_tts_api.client import CapCutClient
    
    def _synth_one(l: DialogueLine):
        voice_id = VOICE_FEMALE if l.speaker_gender == "female" else VOICE_MALE
        part_mp3 = temp_dir / f"dub_{l.index}.mp3"
        c = CapCutClient()
        for retry in range(3):
            try:
                res = c.generate_speech([l.vi_text], voice=voice_id, timeout=30.0)
                import json as _json, requests as _req
                payload = _json.loads(res["data"]["tasks"][0]["payload"])
                sub = payload["audio_subtitles"][0]
                url = sub.get("speech_url")
                if url:
                    r = _req.get(url, timeout=20)
                    if r.status_code == 200 and len(r.content) > 100:
                        part_mp3.write_bytes(r.content)
                        return l.index, part_mp3
            except Exception as exc:
                time.sleep(0.5)
        print(f"[Worker3] ⚠️ Cảnh báo lỗi tổng hợp câu {l.index} sau 3 lần thử: {l.vi_text[:40]}")
        return l.index, None

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(_synth_one, l) for l in valid_lines]
        done_cnt = 0
        for f in concurrent.futures.as_completed(futs):
            idx, p = f.result()
            if p and p.exists() and p.stat().st_size > 100:
                line_parts[idx] = p
            done_cnt += 1
            if done_cnt % 25 == 0 or done_cnt == len(valid_lines):
                print(f"[Worker3] Tiến độ lồng tiếng CapCut: {done_cnt}/{len(valid_lines)} câu hoàn tất...")

    # 2. Chronological assembly with dynamic time-stretching (atempo) and zero cumulative drift
    print(f"[Worker3] Đang sắp xếp {len(line_parts)} phân đoạn lồng tiếng vào trục thời gian (Auto-Speedup & Khớp SubVid 100%)...")
    num_lines = len(valid_lines)
    for i, l in enumerate(valid_lines):
        part_mp3 = line_parts.get(l.index)
        if not part_mp3:
            continue

        next_start = valid_lines[i + 1].start if i + 1 < num_lines else total_duration
        window_dur = max(0.3, l.end - l.start)
        gap_to_next = max(0.0, next_start - l.end)
        # Allowed duration: finish before next line begins, with slight breathing room if gap exists
        max_allowed = max(0.4, min(next_start - l.start - 0.04, window_dur + min(gap_to_next * 0.7, 0.8)))

        raw_dur = _probe_duration(part_mp3)
        final_part = part_mp3
        final_dur = raw_dur

        # Dynamic speedup: if TTS speech exceeds the subtitle window, accelerate it with atempo
        if raw_dur > max_allowed:
            speed = raw_dur / max_allowed
            speed = min(speed, 1.85)  # Cap at 1.85x to maintain voice clarity and naturalness
            if speed > 1.03:
                sped_mp3 = temp_dir / f"sped_{l.index}.mp3"
                af_filter = f"atempo=2.0,atempo={speed/2.0:.3f}" if speed > 2.0 else f"atempo={speed:.3f}"
                subprocess.run([
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(part_mp3),
                    "-filter:a", af_filter,
                    "-c:a", "libmp3lame", "-b:a", "192k",
                    str(sped_mp3)
                ], check=True)
                final_part = sped_mp3
                final_dur = _probe_duration(sped_mp3)

        # Absolute Timeline Placement: Snap precisely to subtitle start timestamp
        target_start = l.start
        if cursor < target_start:
            gap = target_start - cursor
            if gap > 0.02:
                silence_mp3 = temp_dir / f"silence_{l.index}.mp3"
                subprocess.run([
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-c:a", "libmp3lame", "-b:a", "192k",
                    "-t", f"{gap:.3f}", str(silence_mp3)
                ], check=True)
                entries.append(silence_mp3)
                cursor += gap

        entries.append(final_part)
        cursor += final_dur

    # Tail silence to end of video
    tail_gap = max(0.0, total_duration - cursor)
    if tail_gap > 0.03:
        tail_silence = temp_dir / "tail_silence.mp3"
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-c:a", "libmp3lame", "-b:a", "192k",
            "-t", f"{tail_gap:.3f}", str(tail_silence)
        ], check=True)
        entries.append(tail_silence)

    # Concat dub parts
    if not entries:
        print("[Worker3] Cảnh báo: Không có đoạn lồng tiếng nào được tạo thành công.")
        return None

    concat_list = temp_dir / "dub_concat.txt"
    concat_list.write_text("\n".join([f"file '{p.resolve().as_posix()}'" for p in entries]), encoding="utf-8")

    print("[Worker3] Đang ghép nối các phân đoạn lồng tiếng...")
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(output_audio_path),
    ], check=True)

    try:
        shutil.rmtree(temp_dir)
    except OSError:
        pass

    return output_audio_path


def render_video_remote_l4(
    raw_video: Path,
    ass_path: Path,
    dub_audio: Optional[Path],
    dest_path: Path,
    mask_y: int,
    mask_h: int,
) -> bool:
    """Attempts to render video on Beam Cloud RTX 4090 GPU or Lightning AI L4 GPU."""
    # 1. Prioritize Beam Cloud RTX 4090 GPU
    beam_url = os.environ.get("BEAM_ANIMATION_URL", DEFAULT_BEAM_ANIMATION_URL).rstrip("/")
    if beam_url:
        try:
            from scripts.beam_credential import resolve_beam_token
            beam_token = resolve_beam_token()
            headers = {"Authorization": f"Bearer {beam_token}"} if beam_token else {}
            print(f"[Worker3] 🚀 Đang gửi video sang Beam Cloud RTX 4090 GPU để render ({beam_url})...")
            files = {
                "video": open(raw_video, "rb"),
                "subtitles": open(ass_path, "rb"),
            }
            if dub_audio and dub_audio.exists():
                files["dub_audio"] = open(dub_audio, "rb")

            data = {
                "mask_y": mask_y,
                "mask_h": mask_h,
            }

            resp = requests.post(f"{beam_url}/render_video", headers=headers, files=files, data=data, timeout=900)
            for f in files.values():
                try:
                    f.close()
                except Exception:
                    pass

            if resp.status_code == 200 and len(resp.content) > 1000:
                dest_path.write_bytes(resp.content)
                print(f"[Worker3] ⚡ Render thành công trên Beam Cloud RTX 4090 GPU: {dest_path.name} ({len(resp.content)/(1024*1024):.1f} MB)!")
                return True
            else:
                print(f"[Worker3] Beam Cloud server trả mã {resp.status_code}. Fallback...")
        except Exception as exc:
            print(f"[Worker3] Không thể render qua Beam Cloud GPU ({exc}). Fallback...")

    # 2. Try Lightning AI
    remote_url = os.environ.get("LIGHTNING_WHISPER_URL", DEFAULT_LIGHTNING_WHISPER_URL).rstrip("/")
    if not remote_url:
        return False

    try:
        print(f"[Worker3] 🚀 Đang gửi video sang Lightning AI L4 GPU để render NVENC ({remote_url})...")
        files = {
            "video": open(raw_video, "rb"),
            "subtitles": open(ass_path, "rb"),
        }
        if dub_audio and dub_audio.exists():
            files["dub_audio"] = open(dub_audio, "rb")

        data = {
            "mask_y": mask_y,
            "mask_h": mask_h,
        }

        resp = requests.post(f"{remote_url}/render_video", files=files, data=data, timeout=600)
        for f in files.values():
            try:
                f.close()
            except Exception:
                pass

        if resp.status_code == 200 and len(resp.content) > 1000:
            dest_path.write_bytes(resp.content)
            print(f"[Worker3] ⚡ Render NVENC thành công trên GPU L4: {dest_path.name} ({len(resp.content)/(1024*1024):.1f} MB)!")
            return True
        else:
            print(f"[Worker3] GPU server trả mã {resp.status_code}. Chuyển sang render cục bộ...")
            return False
    except Exception as exc:
        print(f"[Worker3] Không thể render qua GPU ({exc}). Chuyển sang render cục bộ...")
        return False


def render_final_videos(
    raw_video: Path,
    dub_audio: Optional[Path],
    ass_path: Path,
    output_dir: Path,
    width: int,
    height: int,
) -> Tuple[Path, Optional[Path]]:
    """Renders Vietsub video and Dubbed video with 100% Chinese subtitle masking."""
    # Subtitle blur zone: gentle soft blur on bottom 12% so video remains visible, no black box
    blur_h = max(24, int(height * 0.12))
    blur_y = height - blur_h
    
    # Copy subtitle file into output_dir with safe filename to eliminate any ffmpeg filtergraph escaping issues
    clean_ass_file = output_dir / "subtitles.ass"
    if ass_path.resolve() != clean_ass_file.resolve():
        shutil.copy(ass_path, clean_ass_file)

    v_blur_filter = f"[0:v]split[v0][v1];[v1]crop=iw:{blur_h}:0:{blur_y},boxblur=5:2[b];[v0][b]overlay=0:{blur_y},subtitles=subtitles.ass"

    # 1. Render Vietsub Video (Soft blur bottom original text + ASS Vietsub)
    vietsub_video_path = output_dir / "video_vietsub.mp4"
    print("[Worker3] Đang render Video Vietsub (Làm mờ phụ đề gốc thẩm mỹ, không khung đen)...", flush=True)
    cmd_vietsub = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(raw_video.resolve()),
        "-filter_complex",
        f"{v_blur_filter}[v_out]",
        "-map", "[v_out]",
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "copy",
        str(vietsub_video_path.resolve()),
    ]
    subprocess.run(cmd_vietsub, cwd=str(output_dir.resolve()), check=True)
    print(f"[Worker3] Hoàn thành render video Vietsub: {vietsub_video_path.name}", flush=True)

    # 2. Render Dubbed Video (Lossless stream copy video from Vietsub + Audio ducking BGM -18dB)
    dubbed_video_path = output_dir / "video_dubbed.mp4"
    if dub_audio and dub_audio.exists():
        print("[Worker3] Đang xuất Video Lồng Tiếng Đa Giọng (Muxing tức thì từ Vietsub + BGM ducking)...", flush=True)
        # Audio ducking filter: original audio volume at 0.16, dub audio at 1.05
        cmd_dubbed = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(vietsub_video_path.resolve()),
            "-i", str(dub_audio.resolve()),
            "-filter_complex",
            "[0:a]volume=0.16[a_bg];[1:a]volume=1.05[a_fg];[a_bg][a_fg]amix=inputs=2:duration=first[a_out]",
            "-map", "0:v",
            "-map", "[a_out]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            str(dubbed_video_path.resolve()),
        ]
        subprocess.run(cmd_dubbed, cwd=str(output_dir.resolve()), check=True)
        print(f"[Worker3] Hoàn thành render video lồng tiếng: {dubbed_video_path.name}", flush=True)
    else:
        dubbed_video_path = None

    if clean_ass_file.exists() and clean_ass_file.resolve() != ass_path.resolve():
        try:
            clean_ass_file.unlink()
        except OSError:
            pass

    return vietsub_video_path, dubbed_video_path


def sync_to_google_drive(local_dir: Path, slug: str) -> str:
    remote_path = f"{DRIVE_TARGET_BASE}/{slug}"
    print(f"[Worker3] Đang đồng bộ sản phẩm lên Google Drive: {remote_path}...")
    cmd = ["rclone", "copy", str(local_dir), remote_path]
    subprocess.run(cmd, check=True)
    print(f"[Worker3] Đồng bộ Drive hoàn tất: {remote_path}")
    return remote_path


def process_ai_animation(
    source_url_or_file: str,
    min_score: float = QUALITY_THRESHOLD,
    auto_sync: bool = True,
    enable_dub: bool = True,
    part_num: Optional[int] = None,
) -> Dict[str, Any]:
    """Full execution pipeline for Worker 3."""
    temp_slug = _slugify(Path(source_url_or_file).stem if not source_url_or_file.startswith("http") else "dl")[:15]
    temp_work = LOCAL_SPOOL_DIR / f"temp_{temp_slug}_{int(time.time() * 1000) % 1000000}"
    temp_work.mkdir(parents=True, exist_ok=True)

    # 1. Download or locate video
    if source_url_or_file.startswith("http://") or source_url_or_file.startswith("https://"):
        raw_video, cover_img, info = download_video(source_url_or_file, temp_work)
        title = info.get("title", "AI Animation Episode")
        author = info.get("uploader", "Animation Studio")
        source_url = source_url_or_file
    else:
        raw_video = Path(source_url_or_file)
        cover_img = None
        title = raw_video.stem
        author = "Local Studio"
        source_url = str(raw_video)

    width, height = _probe_video_dimensions(raw_video)
    duration = _probe_duration(raw_video)
    print(f"[Worker3] Thông số video: {width}x{height}, thời lượng {duration:.1f}s")

    # Skip rule: Vertical video (9:16 Shorts/TikTok) - User strictly requires 16:9 Landscape format
    if height > 0 and (width < height or (width / height) < 1.2):
        print(f"[Worker3] Bỏ qua: Video định dạng dọc/vuông ({width}x{height}). Nhánh AI Animation chỉ nhận video định dạng ngang 16:9!")
        try:
            shutil.rmtree(temp_work)
        except OSError:
            pass
        return {
            "status": "SKIPPED",
            "title_vi": title,
            "reason": f"Video định dạng dọc ({width}x{height}), yêu cầu 16:9 ngang.",
        }

    # Skip rule: Teaser / clip too short (< 180 seconds / 3 mins)
    if duration < 180.0:
        print(f"[Worker3] Bỏ qua: Video quá ngắn ({duration:.1f}s < 180s), chỉ là teaser/shorts/clip lướt không đạt chuẩn tập phim.")
        try:
            shutil.rmtree(temp_work)
        except OSError:
            pass
        return {
            "status": "SKIPPED",
            "title_vi": title,
            "reason": f"Video quá ngắn ({duration:.1f}s < 180s), chỉ là teaser/clip ngắn.",
        }

    # Skip rule: Video excessively long (> 7200 seconds / 120 mins)
    if duration > 7200.0:
        print(f"[Worker3] Bỏ qua: Video quá dài ({duration:.1f}s > 7200s / 120 phút), vượt quá giới hạn tập phim vừa phải.")
        try:
            shutil.rmtree(temp_work)
        except OSError:
            pass
        return {
            "status": "SKIPPED",
            "title_vi": title,
            "reason": f"Video quá dài ({duration:.1f}s > 7200s), giới hạn tối đa 120 phút.",
        }

    # 2. Extract Audio for ASR
    extracted_audio = temp_work / "extracted_audio.wav"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(raw_video), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(extracted_audio)
    ], check=True)

    # 3. Transcribe dialogue
    dialogue_lines = transcribe_dialogue(extracted_audio)
    if not dialogue_lines:
        print(f"[Worker3] Bỏ qua: Không phát hiện câu thoại nào để lồng tiếng hoặc làm vietsub.")
        try:
            shutil.rmtree(temp_work)
        except OSError:
            pass
        return {
            "status": "SKIPPED",
            "title_vi": title,
            "reason": "Không phát hiện câu thoại nào trong video.",
        }

    # 4. Translate and assign speakers
    translate_and_assign_speakers(dialogue_lines)

    # 5. Quality evaluation with Gemini 3.8 Flash
    sample_dialogue = "\n".join([f"[{l.speaker_gender}] {l.vi_text}" for l in dialogue_lines[:15]])
    eval_res = evaluate_content(
        title=title,
        description_or_snippet=sample_dialogue,
        source_type="ai_animation_video",
        threshold=min_score,
    )
    print(f"[Worker3] Thẩm định chất lượng phim hoạt hình AI: {eval_res.score}/10")

    # 6. Setup Final Package Directory
    fandom = eval_res.fandom or "Anime"
    prod_name = make_production_name(fandom=fandom, title=title, part_num=part_num, default_part_type="Tập")
    prod_name = re.sub(r'[\\/:*?"<>|]', ' - ', prod_name)
    prod_name = re.sub(r'\s+', ' ', prod_name).strip(' .')
    if len(prod_name) > 100:
        prod_name = prod_name[:100].strip(' .')
    slug = make_production_slug(fandom=fandom, title=title, default_part_type="ep")
    work_dir = LOCAL_SPOOL_DIR / prod_name
    work_dir.mkdir(parents=True, exist_ok=True)

    # 7. Generate Subtitles (ASS SubVid + SRT)
    ass_path = work_dir / "subtitle_vi.ass"
    srt_path = work_dir / "subtitle_vi.srt"
    build_subvid_ass(dialogue_lines, ass_path, width=width, height=height)
    build_srt(dialogue_lines, srt_path)

    # 8. Synthesize Multi-Voice Dubbing if enabled
    dub_audio_path = None
    if enable_dub:
        dub_audio_path = work_dir / "audio_dub.mp3"
        synthesize_multivoice_dubbing(dialogue_lines, duration, dub_audio_path)

    # 9. Render Final Videos (Mask Chinese subs 100% + SubVid Captions + Ducked Audio)
    vietsub_v, dubbed_v = render_final_videos(
        raw_video, dub_audio_path, ass_path, work_dir, width, height
    )

    # 10. Generate 16:9 Landscape Cover with Fantasy Typography
    final_cover = work_dir / "cover.jpg"
    try:
        from scripts.content_factory.cover_generator import generate_landscape_animation_cover
        src_cover = cover_img if (cover_img and cover_img.exists()) else raw_video
        generate_landscape_animation_cover(
            video_cover_path=src_cover,
            title=title,
            episode_label=f"Tập {part_num:02d}" if part_num else "Trọn Bộ Full HD",
            caption_line=f"Tập {part_num:02d} • Vietsub & Lồng Tiếng AI" if part_num else "Vietsub & Lồng Tiếng AI Chuẩn Khẩu Hình",
            output_path=final_cover,
        )
        print(f"[Worker3] Đã tạo bìa 16:9 ngang phong cách Fantasy cho phim AI: {final_cover.name}")
    except Exception as c_exc:
        print(f"[Worker3] Cảnh báo tạo bìa 16:9: {c_exc}")
        if cover_img and cover_img.exists():
            shutil.copy(cover_img, final_cover)
        else:
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", "00:00:02", "-i", str(raw_video),
                "-vframes", "1", str(final_cover)
            ], check=True)

    # 11. Generate rich metadata for fanfic.world
    metadata = generate_fanfic_world_metadata(
        title=title,
        text_context=sample_dialogue,
        author=author,
        source_url=source_url,
        fandom_hint=eval_res.fandom,
    )
    metadata.update({
        "folder_name": prod_name,
        "slug": slug,
        "title_original": title,
        "quality_score": eval_res.score,
        "evaluation_reasoning": eval_res.reasoning,
        "voices_used": {
            "male": "BV075_streaming (Thanh Niên Tự Tin)",
            "female": "BV421_vivn_streaming (Nhẹ Ngọt Ngào)",
        },
        "resolution": f"{width}x{height}",
        "duration_seconds": duration,
        "dialogue_lines_count": len(dialogue_lines),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })

    meta_file = work_dir / "metadata.json"
    meta_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    # Clean up temp ingest
    try:
        shutil.rmtree(temp_work)
    except OSError:
        pass

    # 12. Auto-Slice to 10-minute sequential episodes if video > 11 minutes
    if duration > 660.0:
        try:
            from scripts.content_factory.animation_splitter import slice_production_to_10m_episodes
            print(f"[Worker3] ✂️ Video dài ({duration/60:.1f} phút > 11 phút). Tự động chia nhỏ thành các tập 10 phút chuẩn...")
            ep_folders = slice_production_to_10m_episodes(work_dir, target_sec=600.0, sync_drive=auto_sync)
            if ep_folders:
                print(f"[Worker3] [✓] Đã tạo thành công {len(ep_folders)} tập phim 10 phút!")
        except Exception as slice_exc:
            print(f"[Worker3] [!] Cảnh báo khi chia tập: {slice_exc}")

    # 13. Sync to Google Drive
    drive_path = None
    if auto_sync:
        drive_path = sync_to_google_drive(work_dir, prod_name)

    # 13. Register into ProcessedRegistry to prevent any future duplicate processing
    try:
        from scripts.content_factory.processed_tracker import get_processed_registry
        vid_id_val = ""
        if "v=" in source_url_or_file:
            m_v = re.search(r"v=([a-zA-Z0-9_-]+)", source_url_or_file)
            if m_v:
                vid_id_val = m_v.group(1)
        if not vid_id_val:
            vid_id_val = slug
        get_processed_registry().mark_processed(
            video_id=vid_id_val,
            title=title,
            folder_name=prod_name,
            branch="ai_animation",
        )
    except Exception:
        pass

    return {
        "status": "SUCCESS",
        "folder_name": prod_name,
        "slug": slug,
        "title_vi": metadata["title_vi"],
        "description_vi": metadata["description_vi"],
        "score": eval_res.score,
        "duration_seconds": duration,
        "local_dir": str(work_dir),
        "drive_path": drive_path,
        "files": [f.name for f in work_dir.iterdir()],
    }


def process_ai_animation_series(
    query_or_url: str,
    min_score: float = QUALITY_THRESHOLD,
    auto_sync: bool = True,
    enable_dub: bool = True,
    max_episodes: int = 15,
) -> Dict[str, Any]:
    """Processes AI animation by series/playlist sequentially.
    
    Discovers all available sequential sibling episodes (Tập 1 -> Tập 2 -> ...) and processes them in order,
    ensuring no episodes are skipped and deduplicating against existing works.
    """
    if query_or_url.startswith("http://") or query_or_url.startswith("https://"):
        cand = inspect_ai_animation_url(query_or_url)
        episodes = find_all_animation_episodes(cand, max_episodes=max_episodes)
    else:
        candidates = search_ai_animation_candidates(query_or_url, max_results=25)
        if not candidates:
            raise RuntimeError(f"Không tìm thấy video hoạt hình AI nào với từ khóa: {query_or_url}")

        # Duration window: 180s (3 mins) -> 7200s (120 mins)
        valid_duration_candidates = [
            c for c in candidates 
            if c.get("playlist_id") or (180.0 <= (c.get("duration") or 0) <= 7200.0) or not c.get("duration")
        ]
        pool = valid_duration_candidates if valid_duration_candidates else candidates

        # Score candidates: View count weight (viral) + Series/Playlist bonus + Sweet-spot duration multiplier
        def _candidate_rank(c: Dict[str, Any]) -> float:
            views = float(c.get("view_count", 0) or 0)
            is_series = bool(SERIES_REGEX.search(c.get("title", "")) or c.get("playlist_id"))
            dur = float(c.get("duration", 0) or 0)
            sweet_spot = 1.3 if (600.0 <= dur <= 3600.0) else 1.0
            return (views + (100000.0 if is_series else 0.0)) * sweet_spot

        pool.sort(key=_candidate_rank, reverse=True)
        chosen_cand = pool[0]

        top_views = chosen_cand.get("view_count", 0) or 0
        top_dur = (chosen_cand.get("duration", 0) or 0) // 60
        print(f"[Worker3] ⭐ Chọn tác phẩm VIRAL hàng đầu: '{chosen_cand.get('title')}' ({top_views:,} lượt xem | ~{top_dur} phút)")
        episodes = find_all_animation_episodes(chosen_cand, max_episodes=max_episodes)

    if not episodes:
        raise RuntimeError(f"Không tìm thấy tập phim hoạt hình AI nào cho: {query_or_url}")

    print(f"\n[Worker3] === Bắt đầu sản xuất bộ phim hoạt hình AI ({len(episodes)} tập) ===")

    completed_episodes: List[Dict[str, Any]] = []
    existing_local_folders = {p.name.lower() for p in LOCAL_SPOOL_DIR.iterdir() if p.is_dir()} if LOCAL_SPOOL_DIR.exists() else set()

    for idx, ep_item in enumerate(episodes, start=1):
        ep_title = ep_item.get("title", f"Tập {idx}")
        ep_url = ep_item.get("url") or f"https://www.youtube.com/watch?v={ep_item.get('id')}"

        m_num = SERIES_REGEX.search(ep_title)
        p_num = int(m_num.group(1)) if m_num else (idx if len(episodes) > 1 else None)

        # Deduplication check
        from scripts.content_factory.processed_tracker import get_processed_registry
        ep_id = ep_item.get("id", "")
        registry = get_processed_registry()
        is_already_done = registry.is_processed(ep_id, ep_title) or any(
            (ep_id and ep_id in f) or 
            (p_num is not None and f"tập {p_num:02d}".lower() in f and _clean_series_title(ep_title).lower()[:15] in f)
            for f in existing_local_folders
        )
        if is_already_done:
            print(f"[Worker3] Bỏ qua Tập {p_num or idx:02d} ('{ep_title[:40]}...'): Đã có trong kho sản xuất.")
            continue

        print(f"\n[Worker3] >>> Đang xử lý Tập {idx}/{len(episodes)}: '{ep_title}' <<<")
        try:
            res_ep = process_ai_animation(
                source_url_or_file=ep_url,
                min_score=min_score,
                auto_sync=auto_sync,
                enable_dub=enable_dub,
                part_num=p_num,
            )
            if res_ep.get("status") == "SUCCESS":
                completed_episodes.append(res_ep)
                if res_ep.get("folder_name"):
                    existing_local_folders.add(res_ep["folder_name"].lower())
            else:
                print(f"[Worker3] Tập {p_num or idx:02d} bị bỏ qua: {res_ep.get('reason')}")
        except Exception as exc:
            print(f"[Worker3] Lỗi khi xử lý tập {p_num or idx:02d}: {exc}")

        if len(completed_episodes) >= max_episodes:
            break

    if not completed_episodes:
        return {
            "status": "SKIPPED",
            "reason": f"Không có tập nào trong bộ ({len(episodes)} tập) đạt tiêu chuẩn chất lượng hoặc tất cả đã hoàn thành trước đó.",
            "total_episodes_found": len(episodes),
        }

    last_ep = completed_episodes[-1]
    return {
        "status": "SUCCESS",
        "series_title": episodes[0].get("title", "AI Animation Series"),
        "episodes_count": len(completed_episodes),
        "total_episodes_found": len(episodes),
        "folder_name": last_ep.get("folder_name"),
        "slug": last_ep.get("slug"),
        "title_vi": last_ep.get("title_vi"),
        "description_vi": last_ep.get("description_vi"),
        "score": last_ep.get("score"),
        "drive_path": last_ep.get("drive_path"),
        "episodes": completed_episodes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Worker 3: AI Animation Harvester, Masker & Dubber")
    parser.add_argument("--source", "-s", "--query", "-q", type=str, help="Video URL, search query, or local MP4 path", required=True)
    parser.add_argument("--min-score", type=float, default=QUALITY_THRESHOLD, help="Minimum quality score")
    parser.add_argument("--max-episodes", type=int, default=15, help="Maximum sequential episodes to process")
    parser.add_argument("--no-dub", action="store_true", help="Disable multi-voice dubbing, only generate Vietsub")
    parser.add_argument("--no-sync", action="store_true", help="Skip Google Drive sync")
    args = parser.parse_args()

    try:
        res = process_ai_animation_series(
            args.source,
            min_score=args.min_score,
            auto_sync=not args.no_sync,
            enable_dub=not args.no_dub,
            max_episodes=args.max_episodes,
        )
        print("\n" + "=" * 60)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    finally:
        try:
            from scripts.content_factory.lightning_helper import schedule_gpu_idle_shutdown
            schedule_gpu_idle_shutdown(delay_seconds=60)
        except Exception:
            pass

