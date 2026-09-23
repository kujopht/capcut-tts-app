"""Re-TTS Chapter 1 of [Naruto] SI - Reborn in the Hatake Clan with CapCut 'vi_female_huong' (Giọng Nữ Phổ Thông)."""
import os
import sys
import re
import json
import time
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(r"C:\Users\nguye\Documents\CapCut-TTS-App")
sys.path.insert(0, str(PROJECT_ROOT))

import requests
from capcut_tts_api.client import CapCutClient

VOICE_TYPE = "vi_female_huong"  # Giọng Nữ Phổ Thông
STORY_FILE = PROJECT_ROOT / "raw_spool" / "fanfic_tts" / "story_vi_hatake_c01.txt"
USER_DOWNLOADS = Path(os.environ.get("USERPROFILE", r"C:\Users\nguye")) / "Downloads"
OUT_MP3_USER = USER_DOWNLOADS / "[Naruto] SI - Reborn in the Hatake Clan - Chuong 01 (Giong Nu Pho Thong).mp3"
CACHE_DIR = PROJECT_ROOT / "raw_spool" / "temp_hatake_c01_capcut"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def clean_sentence_for_tts(text: str) -> str:
    # Remove markdown emphasis asterisks: *word* -> word
    text = re.sub(r"\*+([^*]+)\*+", r"\1", text)
    # Replace long dashes with commas or pauses
    text = re.sub(r"[\u2014\u2013—–]+", ", ", text)
    # Normalize multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text

def split_into_tts_sentences(raw_text: str) -> list[str]:
    paras = [p.strip() for p in raw_text.splitlines() if p.strip()]
    sentences = []
    for p in paras:
        p_clean = clean_sentence_for_tts(p)
        if not p_clean:
            continue
        # Split on sentence boundaries
        raw_s = re.split(r"(?<=[.!?…])\s+", p_clean)
        for s in raw_s:
            s = s.strip()
            if not s:
                continue
            # If a single sentence is overly long (> 400 chars), split on comma or semicolon
            if len(s) > 400:
                sub_parts = re.split(r"(?<=[,;:…])\s+", s)
                buf = ""
                for part in sub_parts:
                    if len(buf) + len(part) < 380:
                        buf = f"{buf} {part}".strip()
                    else:
                        if buf:
                            sentences.append(buf)
                        buf = part
                if buf:
                    sentences.append(buf)
            else:
                sentences.append(s)
    return sentences

def format_srt_time(ms: float) -> str:
    total_sec = int(ms // 1000)
    millis = int(ms % 1000)
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    seconds = total_sec % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

def main():
    print("=" * 60)
    print("  TTS CHƯƠNG 1: [Naruto] SI - Reborn in the Hatake Clan")
    print(f"  Giọng: {VOICE_TYPE} (CapCut - Giọng Nữ Phổ Thông)")
    print(f"  File nguồn: {STORY_FILE}")
    print(f"  Đích tải: {OUT_MP3_USER}")
    print("=" * 60)

    if not STORY_FILE.exists():
        raise FileNotFoundError(f"Không tìm thấy file nguồn tại {STORY_FILE}")

    raw_text = STORY_FILE.read_text(encoding="utf-8")
    sentences = split_into_tts_sentences(raw_text)
    print(f"[*] Tổng số câu sau khi chuẩn hóa: {len(sentences)} câu")

    client = CapCutClient()

    # Batch sentences: 20 sentences per request
    BATCH_SIZE = 20
    batches = [sentences[i:i+BATCH_SIZE] for i in range(0, len(sentences), BATCH_SIZE)]
    print(f"[*] Chia thành {len(batches)} batches (mỗi batch ~{BATCH_SIZE} câu)")

    all_audio_items = [] # list of (global_index, text, audio_url, duration_ms)
    t_start = time.time()

    for b_idx, batch in enumerate(batches, 1):
        retries = 3
        success = False
        while retries > 0 and not success:
            try:
                t0 = time.time()
                res = client.generate_speech(batch, voice=VOICE_TYPE, timeout=45.0)
                payload = json.loads(res["data"]["tasks"][0]["payload"])
                subs = payload.get("audio_subtitles", [])
                if len(subs) != len(batch):
                    print(f"  [!] Batch {b_idx}: Nhận {len(subs)}/{len(batch)} items. Chấp nhận.")
                for sub in subs:
                    all_audio_items.append({
                        "text": sub.get("text", ""),
                        "url": sub.get("speech_url", ""),
                        "duration": sub.get("duration", 0),
                    })
                elapsed = time.time() - t0
                pct = int((b_idx / len(batches)) * 100)
                print(f"  [{pct:3d}%] Batch {b_idx:02d}/{len(batches):02d} thành công ({elapsed:.1f}s) - Tổng audio: {len(all_audio_items)} câu")
                success = True
            except Exception as e:
                retries -= 1
                print(f"  [!] Lỗi Batch {b_idx} ({e}). Thử lại ({3 - retries}/3)...")
                time.sleep(2)

        if not success:
            print(f"  [X] Batch {b_idx} thất bại sau 3 lần thử! Bỏ qua batch này.")

    tts_elapsed = time.time() - t_start
    print(f"\n[✓] Tổng hợp API TTS hoàn tất trong {tts_elapsed:.1f} giây! ({len(all_audio_items)} phân đoạn âm thanh)")

    # Download all audio segments concurrently
    print(f"[*] Đang tải {len(all_audio_items)} file âm thanh...")
    session = requests.Session()

    def download_segment(idx: int, item: dict):
        url = item["url"]
        part_path = CACHE_DIR / f"part_{idx:05d}.mp3"
        if not part_path.exists() or part_path.stat().st_size == 0:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            part_path.write_bytes(resp.content)
        return idx, part_path, item["duration"], item["text"]

    downloaded = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(download_segment, i, item) for i, item in enumerate(all_audio_items)]
        for f in as_completed(futures):
            downloaded.append(f.result())

    # Sort in sequential order
    downloaded.sort(key=lambda x: x[0])
    print(f"[✓] Đã tải về toàn bộ {len(downloaded)} đoạn âm thanh.")

    # Concat using FFmpeg concat demuxer
    concat_list_file = CACHE_DIR / "concat_list.txt"
    concat_lines = []
    srt_cues = []
    cur_time_ms = 0.0

    for cue_idx, (idx, path, dur_ms, txt) in enumerate(downloaded, 1):
        concat_lines.append(f"file '{path.as_posix()}'")
        start_t = format_srt_time(cur_time_ms)
        end_t = format_srt_time(cur_time_ms + dur_ms)
        srt_cues.append(f"{cue_idx}\n{start_t} --> {end_t}\n{txt}\n")
        cur_time_ms += dur_ms

    concat_list_file.write_text("\n".join(concat_lines), encoding="utf-8")

    # Generate SRT
    srt_file = OUT_MP3_USER.with_suffix(".srt")
    srt_file.write_text("\n".join(srt_cues), encoding="utf-8")

    print(f"[*] Đang ghép file âm thanh liền mạch bằng FFmpeg vào:")
    print(f"    -> {OUT_MP3_USER}")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list_file),
        "-c", "copy",
        str(OUT_MP3_USER)
    ]
    subprocess.run(cmd, check=True)

    final_size_mb = OUT_MP3_USER.stat().st_size / (1024 * 1024)
    total_min = int(cur_time_ms // 60000)
    total_sec = int((cur_time_ms % 60000) // 1000)

    print("\n" + "=" * 60)
    print("  🎉 HOÀN TẤT XUẤT AUDIO BẰNG GIỌNG NỮ PHỔ THÔNG CAPCUT!")
    print(f"  Đường dẫn: {OUT_MP3_USER}")
    print(f"  Phụ đề SRT: {srt_file}")
    print(f"  Dung lượng: {final_size_mb:.2f} MB")
    print(f"  Thời lượng: {total_min} phút {total_sec} giây ({cur_time_ms / 1000:.1f}s)")
    print("=" * 60)

if __name__ == "__main__":
    main()
