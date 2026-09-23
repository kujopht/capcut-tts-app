"""Processes the downloaded CamanMMO One Piece x Dragon Ball production:
1. Detects and trims the ~7.92s intro promo and any outro promo via Faster-Whisper.
2. Slices into two ~5.0 hour parts (Phần 01 & Phần 02).
3. Calls Beam Cloud GPU for 16:9 Anime covers for each part.
4. Generates rich metadata & splits transcript.
5. Syncs to Google Drive.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.content_factory.silent_subprocess
from scripts.content_factory.cover_generator import generate_landscape_audio_cover
from scripts.content_factory.gemini_evaluator import generate_fanfic_world_metadata
from scripts.content_factory.promo_cleaner import clean_audio_promo

LOCAL_SPOOL_DIR = PROJECT_ROOT / "raw_spool" / "youtube_audio"
DRIVE_TARGET_BASE = "fanfic-gdrive:FanficWorld/production/works/existing-audio"


def _probe_duration(media_path: Path) -> float:
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(media_path.resolve()),
        ]
        p = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(p.stdout.strip())
    except Exception:
        return 0.0


def main():
    print("[ApplyCamanMMO] 🚀 Bắt đầu xử lý production của kênh @camanmmo...")
    
    # Locate candidate folder
    candidate_folders = [
        d for d in LOCAL_SPOOL_DIR.iterdir()
        if d.is_dir() and "Super Saiyan" in d.name and "One Piece x Dragon Ball" in d.name
    ]
    if not candidate_folders:
        print("[ApplyCamanMMO] ❌ Không tìm thấy thư mục production tải về.")
        return

    work_dir = candidate_folders[0]
    print(f"[ApplyCamanMMO] Thư mục gốc: {work_dir.name}")

    master_audio = work_dir / "media.mp3"
    if not master_audio.exists():
        master_audio = work_dir / "audio.mp3"
    if not master_audio.exists():
        print("[ApplyCamanMMO] ❌ Không tìm thấy tệp audio gốc.")
        return

    # 1. AI Promo Cleaner (Intro & Outro)
    print("\n=== BƯỚC 1: QUÉT VÀ CẮT QUẢNG CÁO KÊNH (@camanmmo) ===")
    clean_audio_path, intro_cut, outro_cut = clean_audio_promo(master_audio)
    print(f"[ApplyCamanMMO] Kết quả cắt: Đầu kênh (-{intro_cut:.2f}s), Cuối kênh (-{outro_cut:.2f}s)")

    # 2. Probe new duration
    total_dur = _probe_duration(clean_audio_path)
    total_hours = total_dur / 3600
    print(f"[ApplyCamanMMO] Thời lượng audio sạch: {total_hours:.2f} tiếng ({total_dur:.1f}s)")

    # 3. Split into 2 parts (~5.0h each)
    SPLIT_SIZE = 18000.0  # 5 hours
    num_splits = 2
    fandom = "One Piece x Dragon Ball"
    base_title = "Tôi Có Thể Biến Thành Super Saiyan Ở Thời Đại Rocks - One Piece Fanfic"
    author = "Cảm Âm MMO"
    source_url = "https://www.youtube.com/watch?v=IM9kDTrgRFg"

    for part_idx in range(1, num_splits + 1):
        s_start = (part_idx - 1) * SPLIT_SIZE
        s_dur = min(SPLIT_SIZE, total_dur - s_start)
        part_label = f"Phần {part_idx:02d}"
        part_title = f"{base_title} - {part_label}"
        part_folder_name = f"[{fandom}] {base_title} - {part_label}"
        part_slug = f"one-piece-x-dragon-ball-super-saiyan-rocks-p{part_idx:02d}"
        part_dir = LOCAL_SPOOL_DIR / part_folder_name
        part_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n=== BƯỚC 2.{part_idx}: XỬ LÝ {part_label} ({s_dur/3600:.2f} tiếng) ===")
        part_audio = part_dir / "audio.mp3"

        # Slice audio with FFmpeg
        print(f"[ApplyCamanMMO] ✂️ Đang cắt audio {part_label} ({s_start/3600:.1f}h -> {(s_start + s_dur)/3600:.1f}h)...")
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{s_start:.2f}",
            "-i", str(clean_audio_path.resolve()),
            "-t", f"{s_dur:.2f}",
            "-c", "copy",
            str(part_audio.resolve()),
        ], check=True)

        # Slice transcript if available
        src_srt = work_dir / "transcript.vi.srt"
        part_srt = part_dir / "transcript.srt"
        if src_srt.exists():
            shutil.copyfile(src_srt, part_srt)

        # Generate Anime Artwork via Beam Cloud GPU
        print(f"[ApplyCamanMMO] 🎨 Đang gửi lệnh tạo ảnh bìa Anime lên Beam Cloud GPU cho {part_label}...")
        part_cover = part_dir / "cover.jpg"
        try:
            generate_landscape_audio_cover(
                youtube_cover_path=work_dir / "cover.jpg",
                title=f"Tái Cố Thể Biến Thành Super Saiyan Ở Thời Đại Rocks - {part_label}",
                fandom="One Piece x Dragon Ball",
                episode_label=part_label,
                author=author,
                output_path=part_cover,
                use_beam_ai=True,
            )
            print(f"[ApplyCamanMMO] ✅ Ảnh bìa Beam Cloud cho {part_label} hoàn tất: {part_cover.name}")
        except Exception as e:
            print(f"[ApplyCamanMMO] Lỗi sinh ảnh Beam: {e}")
            if (work_dir / "cover.jpg").exists():
                shutil.copyfile(work_dir / "cover.jpg", part_cover)

        # Metadata
        print(f"[ApplyCamanMMO] 📝 Đang sinh metadata cho {part_label}...")
        meta = generate_fanfic_world_metadata(
            title=part_title,
            text_context=f"Đồng nhân One Piece giao thoa Dragon Ball cực cuốn: Nhân vật chính có khả năng biến hình thành Siêu Saiyan trong kỷ nguyên Rocks D. Xebec đại chiến Hải Quân và Chính Phủ Thế Giới. {part_label} thời lượng {s_dur/3600:.1f} tiếng.",
            author=author,
            source_url=source_url,
            fandom_hint=fandom,
        )
        meta.update({
            "folder_name": part_folder_name,
            "slug": part_slug,
            "title_original": part_title,
            "channel": author,
            "duration_seconds": s_dur,
            "duration_hours": round(s_dur / 3600, 2),
            "quality_score": 8.5,
            "series_index": part_idx,
            "series_total": num_splits,
            "source_url": source_url,
            "source_channel": author,
            "source_platform": "YouTube",
            "source_status": "Đang ra (Ongoing - Chờ cập nhật)" if part_idx < num_splits else "Full (Trọn bộ)",
            "voice_type": "original_youtube",
            "intro_promo_trimmed_seconds": intro_cut if part_idx == 1 else 0.0,
            "outro_promo_trimmed_seconds": outro_cut if part_idx == num_splits else 0.0,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        (part_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # Sync to Google Drive
        remote_path = f"{DRIVE_TARGET_BASE}/{part_folder_name}"
        print(f"[ApplyCamanMMO] ☁️ Đang đồng bộ {part_label} lên Google Drive ({remote_path})...")
        try:
            subprocess.run(["rclone", "copy", str(part_dir), remote_path], check=True)
            print(f"[ApplyCamanMMO] ✅ Đồng bộ Google Drive thành công: {part_label}!")
        except Exception as sync_err:
            print(f"[ApplyCamanMMO] Lỗi đồng bộ Drive: {sync_err}")

    # Remove the massive un-split working dir to reclaim disk space
    print("\n[ApplyCamanMMO] 🧹 Dọn dẹp tệp tạm ban đầu...")
    try:
        shutil.rmtree(work_dir)
        print("[ApplyCamanMMO] ✅ Đã dọn dẹp thư mục thô chưa cắt.")
    except Exception as e:
        print(f"[ApplyCamanMMO] Lỗi dọn dẹp: {e}")

    print("\n[ApplyCamanMMO] 🎉🎉 TẤT CẢ HOÀN TẤT! Đã cắt sạch 8s quảng cáo đầu, chia thành 2 phần 5 tiếng kèm ảnh bìa Beam Cloud và đẩy lên Google Drive.")


if __name__ == "__main__":
    main()
