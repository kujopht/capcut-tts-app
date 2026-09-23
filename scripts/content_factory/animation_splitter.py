"""Animation Splitter Engine: Slices Long AI Animation Movies into 10-Minute Episodes.

Features:
1. Slices marathon AI animation videos (> 11 min) into ~10-minute (600s) sequential episodes.
2. Re-bases ASS and SRT subtitle timestamps back to 00:00:00 for each episode.
3. In-memory PyAV zero-drift audio timeline assembly:
   - Absolute sample-accurate positioning (0.000s cumulative drift).
   - Dynamic auto-speedup (FFmpeg atempo) whenever speech exceeds subtitle window.
   - 100% audio-video duration match down to the millisecond.
4. Aesthetic soft blur (boxblur=5:2 on bottom 12% Chinese subtitle zone, NO solid black box).
5. Fast lossless video slicing (-c copy) and high-quality AAC/H.264 rendering.
6. 16:9 Landscape Fantasy cover art with custom episode badges (Tập 01, Tập 02...).
7. Metadata generation and optional auto-sync to Google Drive.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Enforce silent subprocess execution (zero flashing console windows)
import scripts.content_factory.silent_subprocess

import av
import numpy as np

from capcut_tts_api.client import CapCutClient
from scripts.content_factory.cover_generator import generate_landscape_animation_cover
from scripts.content_factory.naming import make_production_name, make_production_slug

DRIVE_TARGET_BASE = "fanfic-gdrive:FanficWorld/production/works/ai-animation"
LOCAL_ANIMATION_DIR = PROJECT_ROOT / "raw_spool" / "ai_animation"

SAMPLE_RATE = 24000
TARGET_EP_SECONDS = 600.0  # 10 minutes per episode
MIN_SPLIT_THRESHOLD = 660.0  # 11 minutes: only split if longer than 11 min
MIN_LAST_CHUNK_SECONDS = 180.0  # 3 minutes: don't create stubs < 3 min

VOICE_MALE = "BV075_streaming"
VOICE_FEMALE = "BV421_vivn_streaming"


def probe_duration(path: Path) -> float:
    """Gets media duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(proc.stdout.strip())
    except Exception:
        return 0.0


def probe_video_dimensions(path: Path) -> Tuple[int, int]:
    """Gets video width and height."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        w, h = proc.stdout.strip().split("x")
        return int(w), int(h)
    except Exception:
        return 640, 360


def ass_time_to_seconds(t_str: str) -> float:
    """Converts ASS timestamp H:MM:SS.cs to seconds."""
    parts = t_str.strip().split(":")
    h = float(parts[0])
    m = float(parts[1])
    s = float(parts[2])
    return h * 3600.0 + m * 60.0 + s


def seconds_to_ass_time(s: float) -> str:
    """Converts seconds to ASS timestamp H:MM:SS.cs."""
    cs = round(s * 100)
    hh, rem = divmod(cs, 360_000)
    mm, rem = divmod(rem, 6000)
    ss, cs = divmod(rem, 100)
    return f"{hh:d}:{mm:02d}:{ss:02d}.{cs:02d}"


def seconds_to_srt_time(s: float) -> str:
    """Converts seconds to SRT timestamp HH:MM:SS,mmm."""
    ms = round(s * 1000)
    hh, rem = divmod(ms, 3_600_000)
    mm, rem = divmod(rem, 60_000)
    ss, ms = divmod(rem, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def decode_audio_to_pcm(audio_path: Path, target_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Decodes MP3/WAV/AAC directly into 16-bit mono numpy array in memory via PyAV (zero subprocess)."""
    try:
        container = av.open(str(audio_path))
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="s16", layout="mono", rate=target_rate)
        frames = []
        for packet in container.demux(stream):
            for frame in packet.decode():
                for rf in resampler.resample(frame):
                    frames.append(rf.to_ndarray())
        container.close()
        if frames:
            return np.concatenate(frames, axis=1).squeeze()
    except Exception:
        pass
    return np.array([], dtype=np.int16)


def extract_base_series_title(folder_name: str) -> str:
    """Strips episode suffixes like '- Tập 01', 'Trọn Bộ' to get clean series title."""
    cleaned = re.sub(
        r"[\s\-_–|]+(?:Tập|Tap|Part|Chương|Chuong|Hồi|Phần|Vol|Ep|Episode|#)\s*\d+.*$",
        "",
        folder_name,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[\s\-_–|]+(?:Trọn Bộ|Full|Full HD|Tập Cuối).*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def calculate_episode_windows(total_duration: float, target_sec: float = TARGET_EP_SECONDS) -> List[Tuple[float, float]]:
    """Calculates non-overlapping [start, end] windows for 10-minute episodes."""
    if total_duration <= MIN_SPLIT_THRESHOLD:
        return [(0.0, total_duration)]

    num_eps = max(1, round(total_duration / target_sec))
    windows: List[Tuple[float, float]] = []

    for i in range(num_eps):
        start = i * target_sec
        if i == num_eps - 1:
            end = total_duration
        else:
            end = (i + 1) * target_sec

        # If the remaining time after this episode would be < 3 minutes, absorb it
        remaining_after = total_duration - end
        if 0 < remaining_after < MIN_LAST_CHUNK_SECONDS:
            end = total_duration
            windows.append((start, end))
            break
        windows.append((start, end))

    return windows


def slice_ass_and_srt(
    src_ass_or_content: Union[Path, str],
    dest_ass: Path,
    dest_srt: Path,
    t_start: float,
    t_end: float,
) -> List[Dict[str, Any]]:
    """Slices ASS events within [t_start, t_end] and rebases timestamps to 00:00:00."""
    if isinstance(src_ass_or_content, Path):
        content = src_ass_or_content.read_text(encoding="utf-8", errors="replace")
    else:
        content = str(src_ass_or_content)
    lines = content.splitlines()

    header: List[str] = []
    events_started = False
    extracted_dialogues: List[Dict[str, Any]] = []

    for l in lines:
        if l.strip() == "[Events]":
            events_started = True
            header.append(l)
            continue
        if not events_started:
            header.append(l)
        else:
            if l.startswith("Format:"):
                header.append(l)
            elif l.startswith("Dialogue:"):
                parts = l.split(",", 9)
                if len(parts) >= 10:
                    s = ass_time_to_seconds(parts[1])
                    e = ass_time_to_seconds(parts[2])
                    if s >= t_start and s < t_end:
                        rebased_s = max(0.0, s - t_start)
                        rebased_e = min(t_end - t_start, max(rebased_s + 0.3, e - t_start))
                        parts[1] = seconds_to_ass_time(rebased_s)
                        parts[2] = seconds_to_ass_time(rebased_e)
                        style = parts[3].strip()
                        gender = "female" if style == "FemaleVoice" else "male"
                        raw_text = parts[9].strip()
                        clean_text = re.sub(r"\{.*?\}", "", raw_text).replace(r"\N", " ").strip()

                        extracted_dialogues.append({
                            "orig_start": s,
                            "orig_end": e,
                            "s": rebased_s,
                            "e": rebased_e,
                            "gender": gender,
                            "style": style,
                            "text": clean_text,
                            "ass_line": ",".join(parts),
                        })

    # Write rebased ASS
    rebased_ass_content = "\n".join(header) + "\n" + "\n".join([d["ass_line"] for d in extracted_dialogues]) + "\n"
    dest_ass.write_text(rebased_ass_content, encoding="utf-8")

    # Write rebased SRT
    srt_blocks = []
    for idx, d in enumerate(extracted_dialogues, 1):
        t_str = f"{seconds_to_srt_time(d['s'])} --> {seconds_to_srt_time(d['e'])}"
        srt_blocks.append(f"{idx}\n{t_str}\n{d['text']}\n")
    dest_srt.write_text("\n".join(srt_blocks), encoding="utf-8")

    return extracted_dialogues



def build_episode_dub_audio(
    dialogues: List[Dict[str, Any]],
    cache_dir: Path,
    episode_duration: float,
    output_audio_path: Path,
    speed_cap: float = 1.85,
    src_master_dub: Optional[Path] = None,
    ws: float = 0.0,
    we: float = 0.0,
    force_synth: bool = False,
) -> Path:
    """Assembles zero-drift audio track for an episode using in-memory PyAV & numpy timeline."""
    total_samples = int(episode_duration * SAMPLE_RATE)

    # 1. Fast path: If master dubbed audio exists, not forcing new synth, and covers this episode window, slice it directly
    if not force_synth and src_master_dub and src_master_dub.exists():
        try:
            m_dur = probe_duration(src_master_dub)
            if m_dur >= ws + 10.0:
                print(f"    [3/5] Trích xuất audio_dub từ bản master ({ws:.1f}s -> {we:.1f}s)...", flush=True)
                temp_slice = output_audio_path.parent / "temp_dub_slice.mp3"
                cmd_slice = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", f"{ws:.3f}", "-to", f"{we:.3f}",
                    "-i", str(src_master_dub.resolve()),
                    "-c:a", "libmp3lame", "-b:a", "192k",
                    str(temp_slice.resolve()),
                ]
                subprocess.run(cmd_slice, check=True)
                # Ensure exact sample alignment to episode_duration
                samples = decode_audio_to_pcm(temp_slice, target_rate=SAMPLE_RATE)
                temp_slice.unlink(missing_ok=True)
                if len(samples) > 0:
                    timeline = np.zeros(total_samples, dtype=np.int16)
                    copy_len = min(len(samples), total_samples)
                    timeline[:copy_len] = samples[:copy_len]
                    temp_wav = output_audio_path.parent / "temp_timeline.wav"
                    with wave.open(str(temp_wav), "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(SAMPLE_RATE)
                        wf.writeframes(timeline.tobytes())
                    subprocess.run([
                        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-i", str(temp_wav),
                        "-c:a", "libmp3lame", "-b:a", "192k",
                        str(output_audio_path)
                    ], check=True)
                    temp_wav.unlink(missing_ok=True)
                    return output_audio_path
        except Exception as e:
            print(f"    [!] Cảnh báo cắt master dub: {e}. Chuyển sang tổng hợp trực tiếp...")

    # 2. Parallel synthesis for missing dialogue clips
    missing_dialogues = []
    for d in dialogues:
        line_idx = d.get("index")
        gender = d.get("gender", "male")
        voice = VOICE_MALE if gender == "male" else VOICE_FEMALE
        clip_p = cache_dir / f"line_{line_idx or 0:04d}_{gender}.mp3" if line_idx else None
        if not clip_p or not (clip_p.exists() and clip_p.stat().st_size > 100):
            missing_dialogues.append(d)

    if missing_dialogues:
        print(f"    [TTS] Đang tổng hợp song song {len(missing_dialogues)} câu thoại qua CapCut API (8 luồng)...", flush=True)
        def _synth_one(d_item):
            line_idx = d_item.get("index")
            gender = d_item.get("gender", "male")
            voice = VOICE_MALE if gender == "male" else VOICE_FEMALE
            clip_p = cache_dir / f"line_{line_idx or 0:04d}_{gender}.mp3"
            if clip_p.exists() and clip_p.stat().st_size > 100:
                return
            cl = CapCutClient()
            for _ in range(3):
                try:
                    res = cl.generate_speech([d_item["text"]], voice=voice, timeout=25.0)
                    payload = json.loads(res["data"]["tasks"][0]["payload"])
                    url = payload["audio_subtitles"][0].get("speech_url")
                    if url:
                        r = requests.get(url, timeout=15)
                        if r.status_code == 200 and len(r.content) > 100:
                            clip_p.write_bytes(r.content)
                            return
                except Exception:
                    time.sleep(0.3)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(_synth_one, missing_dialogues))

    timeline = np.zeros(total_samples, dtype=np.int16)
    temp_speed_dir = cache_dir / "temp_speed"
    temp_speed_dir.mkdir(parents=True, exist_ok=True)

    client = CapCutClient()
    sped_count = 0

    for i, d in enumerate(dialogues):
        clip_p = None
        line_idx = d.get("index")
        gender = d.get("gender", "male")
        if line_idx:
            target_clip = cache_dir / f"line_{line_idx:04d}_{gender}.mp3"
            if target_clip.exists() and target_clip.stat().st_size > 100:
                clip_p = target_clip

        if not clip_p or not clip_p.exists():
            voice = VOICE_MALE if gender == "male" else VOICE_FEMALE
            clip_p = cache_dir / f"line_{line_idx or (i+1):04d}_{gender}.mp3"
            if not (clip_p.exists() and clip_p.stat().st_size > 100):
                try:
                    res = client.generate_speech([d["text"]], voice=voice, timeout=30.0)
                    payload = json.loads(res["data"]["tasks"][0]["payload"])
                    url = payload["audio_subtitles"][0].get("speech_url")
                    if url:
                        r = requests.get(url, timeout=20)
                        if r.status_code == 200:
                            clip_p.write_bytes(r.content)
                except Exception:
                    pass

        if not clip_p or not clip_p.exists() or clip_p.stat().st_size < 100:
            continue

        # Check if pre-accelerated sped file exists in cache
        sped_p = cache_dir / f"sped_{line_idx or i:04d}.mp3"
        if sped_p.exists() and sped_p.stat().st_size > 100:
            samples = decode_audio_to_pcm(sped_p)
            start_sample = int(d["s"] * SAMPLE_RATE)
            end_sample = min(start_sample + len(samples), total_samples)
            actual_len = end_sample - start_sample
            if actual_len > 0:
                timeline[start_sample:end_sample] = samples[:actual_len]
            continue

        # Decode clip directly via PyAV
        samples = decode_audio_to_pcm(clip_p)
        if len(samples) == 0:
            continue
        dur = len(samples) / SAMPLE_RATE

        # Window & next start check
        next_s = dialogues[i + 1]["s"] if i + 1 < len(dialogues) else episode_duration
        window = d["e"] - d["s"]
        max_allow = max(0.4, min(next_s - d["s"] - 0.04, window + 0.6))

        # Dynamic Speedup (atempo) if speech exceeds window
        if dur > max_allow:
            spd = min(dur / max_allow, speed_cap)
            if spd > 1.05:
                sped_count += 1
                sped_p = temp_speed_dir / f"sped_{i:04d}.mp3"
                af = f"atempo=2.0,atempo={spd/2.0:.3f}" if spd > 2.0 else f"atempo={spd:.3f}"
                cmd = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(clip_p),
                    "-filter:a", af,
                    "-c:a", "libmp3lame", "-b:a", "160k",
                    str(sped_p)
                ]
                try:
                    subprocess.run(cmd, check=True)
                    sped_samples = decode_audio_to_pcm(sped_p)
                    if len(sped_samples) > 0:
                        samples = sped_samples
                except Exception:
                    pass

        # Absolute timeline placement: Snap strictly to start sample
        start_sample = int(d["s"] * SAMPLE_RATE)
        end_sample = min(start_sample + len(samples), total_samples)
        actual_len = end_sample - start_sample
        if actual_len > 0:
            timeline[start_sample:end_sample] = samples[:actual_len]

    # Write out master WAV then convert to MP3
    temp_wav = output_audio_path.parent / "temp_timeline.wav"
    with wave.open(str(temp_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(timeline.tobytes())

    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(temp_wav),
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(output_audio_path)
    ], check=True)
    temp_wav.unlink(missing_ok=True)
    try:
        shutil.rmtree(temp_speed_dir)
    except OSError:
        pass

    return output_audio_path


def render_episode_videos(
    raw_video: Path,
    dub_audio: Optional[Path],
    ass_path: Path,
    output_dir: Path,
    width: int,
    height: int,
    src_vietsub_v: Optional[Path] = None,
    ws: float = 0.0,
    we: float = 0.0,
) -> Tuple[Path, Optional[Path]]:
    """Renders Vietsub video (soft blur, NO black box) and dubbed video (audio ducking)."""
    vietsub_v = output_dir / "video_vietsub.mp4"
    dubbed_v = output_dir / "video_dubbed.mp4"

    used_fast_slice = False
    if src_vietsub_v and src_vietsub_v.exists():
        try:
            v_dur = probe_duration(src_vietsub_v)
            if v_dur >= we - 5.0:
                print(f"[+] Cắt video_vietsub.mp4 trực tiếp từ bản nguồn (-c copy, ~1s)...", flush=True)
                cmd_slice_vsub = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", f"{ws:.3f}", "-to", f"{we:.3f}",
                    "-i", str(src_vietsub_v.resolve()),
                    "-c", "copy",
                    str(vietsub_v.resolve()),
                ]
                subprocess.run(cmd_slice_vsub, check=True)
                used_fast_slice = True
        except Exception:
            used_fast_slice = False

    if not used_fast_slice:
        blur_h = max(24, int(height * 0.12))
        blur_y = height - blur_h

        # Safe subtitle file for ffmpeg filtergraph
        clean_ass = output_dir / "subtitles.ass"
        clean_ass.write_text(ass_path.read_text(encoding="utf-8"), encoding="utf-8")

        v_blur_filter = f"[0:v]split[v0][v1];[v1]crop=iw:{blur_h}:0:{blur_y},boxblur=5:2[b];[v0][b]overlay=0:{blur_y},subtitles=subtitles.ass"

        print(f"[+] Render video_vietsub.mp4 (Làm mờ phụ đề gốc thẩm mỹ, không khung đen)...", flush=True)
        cmd_vietsub = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(raw_video.resolve()),
            "-filter_complex", f"{v_blur_filter}[v_out]",
            "-map", "[v_out]",
            "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "copy",
            str(vietsub_v.resolve()),
        ]
        subprocess.run(cmd_vietsub, cwd=str(output_dir.resolve()), check=True)
        clean_ass.unlink(missing_ok=True)

    # 2. Render Video Dubbed (Audio ducking BGM -18dB)
    if dub_audio and dub_audio.exists():
        print(f"[+] Muxing video_dubbed.mp4 (Lồng tiếng đa giọng + BGM ducking)...", flush=True)
        cmd_dubbed = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(vietsub_v.resolve()),
            "-i", str(dub_audio.resolve()),
            "-filter_complex",
            "[0:a]volume=0.16[a_bg];[1:a]volume=1.05[a_fg];[a_bg][a_fg]amix=inputs=2:duration=first[a_out]",
            "-map", "0:v",
            "-map", "[a_out]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            str(dubbed_v.resolve()),
        ]
        subprocess.run(cmd_dubbed, cwd=str(output_dir.resolve()), check=True)
    else:
        dubbed_v = None

    return vietsub_v, dubbed_v


def slice_production_to_10m_episodes(
    src_folder: Path,
    target_sec: float = TARGET_EP_SECONDS,
    sync_drive: bool = False,
    force_synth: bool = False,
) -> List[Path]:
    """Takes a full marathon AI animation folder and splits into 10-minute episodes."""
    print("\n" + "=" * 80)
    print(f"[*] KHỞI CHẠY BỘ CHIA TẬP 10 PHÚT (10-MINUTE EPISODE SLICER)")
    print(f"[*] Tác phẩm: {src_folder.name}")
    print("=" * 80, flush=True)

    base_title = extract_base_series_title(src_folder.name)
    marathon_base = LOCAL_ANIMATION_DIR / "_source_marathons"
    marathon_base.mkdir(parents=True, exist_ok=True)
    marathon_dir = marathon_base / f"{base_title} - Trọn Bộ"

    # Automatically archive marathon if src_folder is directly in LOCAL_ANIMATION_DIR
    if src_folder.resolve() != marathon_dir.resolve() and src_folder.parent.resolve() == LOCAL_ANIMATION_DIR.resolve():
        print(f"[*] Đang chuyển marathon vào thư mục lưu trữ: {marathon_dir.name}...")
        if marathon_dir.exists():
            for item in src_folder.iterdir():
                dest_item = marathon_dir / item.name
                if not dest_item.exists():
                    shutil.move(str(item), str(dest_item))
            try:
                shutil.rmtree(src_folder)
            except Exception:
                pass
        else:
            shutil.move(str(src_folder), str(marathon_dir))
        src_folder = marathon_dir

    raw_video = src_folder / "raw_video.mp4"
    if not raw_video.exists():
        for alt in ["video_dubbed.mp4", "video_vietsub.mp4"]:
            if (src_folder / alt).exists():
                raw_video = src_folder / alt
                break

    if not raw_video.exists():
        print(f"[!] Lỗi: Không tìm thấy video nguồn trong {src_folder}")
        return []

    src_ass = src_folder / "subtitle_vi.ass"
    if not src_ass.exists():
        print(f"[!] Lỗi: Không tìm thấy subtitle_vi.ass trong {src_folder}")
        return []

    cache_dir = src_folder / ".dub_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    total_dur = probe_duration(raw_video)
    width, height = probe_video_dimensions(raw_video)

    src_vietsub_v = src_folder / "video_vietsub.mp4" if (src_folder / "video_vietsub.mp4").exists() else None
    src_audio_dub = src_folder / "audio_dub.mp3" if (src_folder / "audio_dub.mp3").exists() else None

    print(f"[+] Thông số: {width}x{height}, thời lượng tổng {total_dur:.1f}s ({total_dur/60:.1f} phút)")
    windows = calculate_episode_windows(total_dur, target_sec=target_sec)
    print(f"[+] Chia thành {len(windows)} tập (~10 phút/tập):")
    for idx, (ws, we) in enumerate(windows, 1):
        print(f"    - Tập {idx:02d}: {ws/60:.1f}m -> {we/60:.1f}m ({we - ws:.1f}s)")

    episode_folders: List[Path] = []

    # Read the full source ASS into memory ONCE
    full_ass_content = src_ass.read_text(encoding="utf-8")
    all_lines = [l for l in full_ass_content.splitlines() if l.startswith("Dialogue:")]
    dialogue_index_map: Dict[int, float] = {}
    for idx, l in enumerate(all_lines, 1):
        parts = l.split(",", 9)
        if len(parts) >= 10:
            dialogue_index_map[idx] = ass_time_to_seconds(parts[1])

    for ep_num, (ws, we) in enumerate(windows, 1):
        ep_duration = we - ws
        ep_label = f"Tập {ep_num:02d}"
        ep_folder_name = f"{base_title} - {ep_label}"
        ep_dir = LOCAL_ANIMATION_DIR / ep_folder_name
        ep_dir.mkdir(parents=True, exist_ok=True)
        episode_folders.append(ep_dir)

        print(f"\n--- [ĐANG XỬ LÝ {ep_label}] {ep_folder_name[:60]} ---")
        print(f"    Khoảng thời gian: {ws:.1f}s -> {we:.1f}s ({ep_duration:.1f}s)")

        # 1. Lossless slice raw_video.mp4 (-c copy, ~1s!)
        ep_raw_v = ep_dir / "raw_video.mp4"
        if not (ep_raw_v.exists() and ep_raw_v.stat().st_size > 1000 and abs(probe_duration(ep_raw_v) - ep_duration) < 2.0):
            print(f"    [1/5] Cắt video không giảm chất lượng ({ws:.1f}s -> {we:.1f}s)...")
            cmd_slice_v = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{ws:.3f}", "-to", f"{we:.3f}",
                "-i", str(raw_video.resolve()),
                "-c", "copy",
                str(ep_raw_v.resolve()),
            ]
            subprocess.run(cmd_slice_v, check=True)
            print(f"    [✓] Đã tạo video tập: {ep_raw_v.stat().st_size / (1024*1024):.1f} MB")

        # 2. Slice & rebase subtitles from memory
        print(f"    [2/5] Cắt và đồng bộ lại mốc phụ đề về 00:00:00...")
        ep_ass = ep_dir / "subtitle_vi.ass"
        ep_srt = ep_dir / "subtitle_vi.srt"
        ep_dialogues = slice_ass_and_srt(full_ass_content, ep_ass, ep_srt, ws, we)
        print(f"    [✓] Đã trích xuất {len(ep_dialogues)} câu thoại cho {ep_label}")

        # Map global line index to ep_dialogues for dub cache lookup
        for d in ep_dialogues:
            orig_s = d["orig_start"]
            best_idx = None
            min_diff = 9999.0
            for g_idx, g_start in dialogue_index_map.items():
                diff = abs(g_start - orig_s)
                if diff < min_diff:
                    min_diff = diff
                    best_idx = g_idx
            d["index"] = best_idx

        # 3. Assemble zero-drift audio track
        print(f"    [3/5] Khớp trục âm thanh PyAV (Khớp 100%, Sai lệch = 0.000s)...")
        ep_dub_audio = ep_dir / "audio_dub.mp3"
        build_episode_dub_audio(
            ep_dialogues,
            cache_dir=cache_dir,
            episode_duration=ep_duration,
            output_audio_path=ep_dub_audio,
            src_master_dub=src_audio_dub,
            ws=ws,
            we=we,
            force_synth=force_synth,
        )
        actual_audio_dur = probe_duration(ep_dub_audio)
        print(f"    [✓] Đã tạo audio_dub.mp3: {actual_audio_dur:.3f}s (Mục tiêu: {ep_duration:.3f}s, Lệch: {abs(actual_audio_dur - ep_duration):.3f}s)")

        # 4. Render final videos (Soft blur Chinese subs + Dubbing ducked)
        print(f"    [4/5] Render Video Vietsub & Lồng tiếng (Không khung đen)...")
        render_episode_videos(
            ep_raw_v, ep_dub_audio, ep_ass, ep_dir, width, height,
            src_vietsub_v=src_vietsub_v, ws=ws, we=we,
        )

        # 5. Generate 16:9 Landscape Cover Art
        print(f"    [5/5] Tạo ảnh bìa 16:9 ngang cho {ep_label}...")
        ep_cover = ep_dir / "cover.jpg"
        try:
            generate_landscape_animation_cover(
                video_cover_path=ep_raw_v,
                title=base_title,
                episode_label=ep_label,
                caption_line=f"{ep_label} • Vietsub & Lồng Tiếng AI",
                output_path=ep_cover,
                series_art_dir=src_folder,
            )
        except Exception as cov_exc:
            print(f"    [!] Cảnh báo tạo bìa: {cov_exc}")

        # Write metadata.json
        meta_file = ep_dir / "metadata.json"
        metadata = {
            "title": f"{base_title} - {ep_label}",
            "series_title": base_title,
            "episode_label": ep_label,
            "episode_number": ep_num,
            "total_episodes": len(windows),
            "duration_seconds": ep_duration,
            "resolution": f"{width}x{height}",
            "voices_used": {
                "male": f"{VOICE_MALE} (Thanh Niên Tự Tin)",
                "female": f"{VOICE_FEMALE} (Nhỏ Ngọt Ngào)",
            },
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        meta_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        # Optional Google Drive sync
        if sync_drive:
            print(f"    [*] Đang đồng bộ {ep_label} lên Google Drive...")
            remote_path = f"{DRIVE_TARGET_BASE}/{base_title}/{ep_label}"
            subprocess.run(["rclone", "copy", str(ep_dir), remote_path], check=True)
            print(f"    [✓] Đồng bộ Drive hoàn tất: {remote_path}")

    print("\n" + "=" * 80)
    print(f"[✓] HOÀN TẤT CHIA TẬP VÀ SẢN XUẤT {len(windows)} TẬP CHO: {base_title}")
    print("=" * 80 + "\n")
    return episode_folders



def main():
    parser = argparse.ArgumentParser(description="AI Animation 10-Minute Episode Slicer & Zero-Drift Aligner")
    parser.add_argument("--folder", type=str, help="Specific production folder to slice into 10m episodes")
    parser.add_argument("--all", action="store_true", help="Slice all productions in raw_spool/ai_animation")
    parser.add_argument("--target-sec", type=float, default=TARGET_EP_SECONDS, help="Episode duration in seconds (default 600s)")
    parser.add_argument("--sync-drive", action="store_true", help="Auto-sync generated episodes to Google Drive")
    parser.add_argument("--force-synth", action="store_true", help="Force re-synthesis of dialogue audio track with CapCut voices")
    args = parser.parse_args()

    if args.folder:
        target = Path(args.folder)
        if not target.exists():
            target = LOCAL_ANIMATION_DIR / args.folder
        if not target.exists():
            target = PROJECT_ROOT / args.folder
        slice_production_to_10m_episodes(target.resolve(), target_sec=args.target_sec, sync_drive=args.sync_drive, force_synth=args.force_synth)
    elif args.all:
        for d in sorted(LOCAL_ANIMATION_DIR.iterdir()):
            if d.is_dir() and not d.name.startswith("temp_") and (d / "subtitle_vi.ass").exists():
                dur = 0.0
                for vf in ["raw_video.mp4", "video_dubbed.mp4", "video_vietsub.mp4"]:
                    if (d / vf).exists():
                        dur = probe_duration(d / vf)
                        break
                if dur > MIN_SPLIT_THRESHOLD:
                    print(f"\n[+] Phát hiện bộ phim dài ({dur/60:.1f} phút): {d.name}")
                    slice_production_to_10m_episodes(d, target_sec=args.target_sec, sync_drive=args.sync_drive, force_synth=args.force_synth)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
