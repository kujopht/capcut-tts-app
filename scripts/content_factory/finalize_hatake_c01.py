"""Finalize and merge all 446 parts of Hatake Clan Chapter 1 into Downloads."""
import os
import sys
import json
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(r"C:\Users\nguye\Documents\CapCut-TTS-App")
CACHE_DIR = PROJECT_ROOT / "raw_spool" / "temp_hatake_c01_capcut"
USER_DOWNLOADS = Path(os.environ.get("USERPROFILE", r"C:\Users\nguye")) / "Downloads"
OUT_MP3 = USER_DOWNLOADS / "[Naruto] SI - Reborn in the Hatake Clan - Chuong 01 (Giong Nu Pho Thong).mp3"
OUT_SRT = USER_DOWNLOADS / "[Naruto] SI - Reborn in the Hatake Clan - Chuong 01 (Giong Nu Pho Thong).srt"

# Also save to raw_spool for production
SPOOL_DIR = PROJECT_ROOT / "raw_spool" / "fanfic_tts" / "[Naruto] SI - Reborn in the Hatake Clan - Chuong 01"
SPOOL_DIR.mkdir(parents=True, exist_ok=True)
SPOOL_MP3 = SPOOL_DIR / "audio_capcut_nu_phothong.mp3"

sys.path.insert(0, str(PROJECT_ROOT))
from scripts.content_factory.re_tts_hatake_capcut import STORY_FILE, split_into_tts_sentences

def format_srt_time(seconds: float) -> str:
    total_sec = int(seconds)
    millis = int(round((seconds - total_sec) * 1000))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def get_duration(mp3_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(mp3_path)
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except Exception:
        return 0.0

def main():
    print("=" * 60)
    print("  ĐANG GHÉP TOÀN BỘ CHƯƠNG 1 (446 CÂU) - GIỌNG NỮ PHỔ THÔNG")
    print("=" * 60)

    sentences = split_into_tts_sentences(STORY_FILE.read_text(encoding="utf-8"))
    parts = sorted([p for p in CACHE_DIR.glob("part_*.mp3") if p.stem.startswith("part_")])
    print(f"[*] Tìm thấy {len(parts)} file MP3 từng câu.")

    concat_file = CACHE_DIR / "concat_final.txt"
    concat_lines = []
    srt_cues = []
    cur_time = 0.0

    print("[*] Đang chuẩn bị danh sách ghép...")
    for idx, part_path in enumerate(parts):
        concat_lines.append(f"file '{part_path.as_posix()}'")

    concat_file.write_text("\n".join(concat_lines), encoding="utf-8")

    print(f"[*] Đang xuất MP3 ghép liền mạch bằng FFmpeg...")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(OUT_MP3)
    ]
    subprocess.run(cmd, check=True)

    dur_sec = get_duration(OUT_MP3)
    cur_time = dur_sec

    # Also copy to SPOOL
    import shutil
    shutil.copyfile(OUT_MP3, SPOOL_MP3)
    shutil.copyfile(OUT_SRT, SPOOL_DIR / "transcript_capcut.srt")

    size_mb = OUT_MP3.stat().st_size / (1024 * 1024)
    total_min = int(cur_time // 60)
    total_sec = int(cur_time % 60)

    print("\n" + "=" * 60)
    print("  🎉 HOÀN THÀNH 100%!")
    print(f"  File MP3 tại Downloads: {OUT_MP3}")
    print(f"  File SRT tại Downloads: {OUT_SRT}")
    print(f"  Dung lượng: {size_mb:.2f} MB")
    print(f"  Tổng thời lượng: {total_min} phút {total_sec} giây")
    print("=" * 60)

if __name__ == "__main__":
    main()
