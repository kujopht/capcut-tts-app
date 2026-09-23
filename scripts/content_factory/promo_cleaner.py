"""Audio Promo & Channel Ad Cleaner: AI-driven Scanner and Trimmer for Intro & Outro Ads.

Detects and trims channel intros/promos (e.g. "Cảm Âm MMO", "Vực Thẳm Audio", "Đăng ký kênh",
"Không vòng vo nữa chúng ta hãy cùng bắt đầu...") and outro ads ("Cảm ơn các bạn...", "Nhớ like...").
Uses local Faster-Whisper on CPU (takes ~2 seconds for 30s clips) and lossless FFmpeg stream copy.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INTRO_PROMO_KEYWORDS = [
    "cảm âm",
    "camanmmo",
    "mmo",
    "vực thẳm",
    "dị giới",
    "ghé thăm",
    "kênh",
    "ủng hộ",
    "đăng ký",
    "subscribe",
    "like",
    "theo dõi",
    "bắt đầu ngay thôi nào",
    "hãy cùng bắt đầu",
    "cùng bắt đầu thôi",
    "cùng bắt đầu",
    "bắt đầu ngay",
    "bắt đầu thôi",
    "thôi nào",
    "không vòng vo",
    "thêm phút nào",
    "thêm phút nữa",
    "tâm phút",
    "chúc các bạn",
    "hy vọng các bạn",
    "nghĩ vọng",
    "thư giãn",
    "thừa dạng",
    "chào mừng",
    "xin chào các bạn",
    "chào mừng các bạn",
    "nghe truyện",
    "phần truyện",
    "xem phần",
    "quảng cáo",
]

OUTRO_PROMO_KEYWORDS = [
    "cảm ơn các bạn đã lắng nghe",
    "cảm ơn các bạn đã theo dõi",
    "hẹn gặp lại",
    "đừng quên like",
    "nhớ like",
    "nhớ đăng ký",
    "nhấn chuông",
    "ủng hộ kênh",
    "tập tiếp theo",
    "phần tiếp theo",
    "hẹn gặp các bạn",
    "tạm biệt các bạn",
]


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


def detect_intro_promo_duration(audio_path: Path, max_scan_seconds: float = 30.0) -> float:
    """Scans the beginning of audio with Faster-Whisper and returns promo cut timestamp in seconds."""
    temp_clip = audio_path.parent / f"_temp_intro_{os.getpid()}.mp3"
    try:
        # Extract first max_scan_seconds
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", "0",
            "-i", str(audio_path.resolve()),
            "-t", str(max_scan_seconds),
            "-c", "copy",
            str(temp_clip.resolve()),
        ]
        subprocess.run(cmd, check=True)

        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(temp_clip.resolve()), language="vi")

        last_promo_end = 0.0
        for seg in segments:
            if seg.start >= 25.0:
                break
            text_clean = seg.text.lower()
            if any(kw in text_clean for kw in INTRO_PROMO_KEYWORDS):
                last_promo_end = max(last_promo_end, seg.end)

        if last_promo_end > 1.5:
            print(f"[PromoCleaner] 🔍 Phát hiện quảng cáo đầu kênh ({last_promo_end:.2f}s). Sẽ cắt chính xác đoạn này.")
            return round(last_promo_end + 0.05, 2)
    except Exception as exc:
        print(f"[PromoCleaner] Lỗi khi quét intro quảng cáo: {exc}")
    finally:
        if temp_clip.exists():
            try:
                temp_clip.unlink()
            except OSError:
                pass
    return 0.0


def detect_outro_promo_duration(audio_path: Path, total_duration: float, max_scan_seconds: float = 45.0) -> float:
    """Scans the end of audio with Faster-Whisper and returns promo duration to trim from the end."""
    if total_duration <= max_scan_seconds:
        return 0.0

    start_scan = max(0.0, total_duration - max_scan_seconds)
    temp_clip = audio_path.parent / f"_temp_outro_{os.getpid()}.mp3"
    try:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{start_scan:.2f}",
            "-i", str(audio_path.resolve()),
            "-t", str(max_scan_seconds),
            "-c", "copy",
            str(temp_clip.resolve()),
        ]
        subprocess.run(cmd, check=True)

        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(temp_clip.resolve()), language="vi")

        outro_start_sec: Optional[float] = None
        for seg in segments:
            text_clean = seg.text.lower()
            is_promo = any(kw in text_clean for kw in OUTRO_PROMO_KEYWORDS)
            if is_promo:
                outro_start_sec = start_scan + seg.start
                break

        if outro_start_sec is not None:
            trim_from_end = total_duration - outro_start_sec
            if trim_from_end > 2.0:
                print(f"[PromoCleaner] 🔍 Phát hiện quảng cáo cuối kênh ({trim_from_end:.2f}s).")
                return round(trim_from_end + 0.1, 2)
    except Exception as exc:
        print(f"[PromoCleaner] Lỗi khi quét outro quảng cáo: {exc}")
    finally:
        if temp_clip.exists():
            try:
                temp_clip.unlink()
            except OSError:
                pass
    return 0.0


def clean_audio_promo(
    audio_path: Path,
    output_path: Optional[Path] = None,
) -> Tuple[Path, float, float]:
    """Scans and cuts intro and outro channel advertisements from audio file losslessly.

    Returns:
        (cleaned_audio_path, intro_trimmed_seconds, outro_trimmed_seconds)
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        return audio_path, 0.0, 0.0

    total_dur = _probe_duration(audio_path)
    if total_dur < 10.0:
        return audio_path, 0.0, 0.0

    intro_cut = detect_intro_promo_duration(audio_path, max_scan_seconds=30.0)
    outro_cut = detect_outro_promo_duration(audio_path, total_dur, max_scan_seconds=45.0)

    if intro_cut <= 0.0 and outro_cut <= 0.0:
        print("[PromoCleaner] ✅ Audio sạch, không phát hiện quảng cáo đầu/cuối kênh.")
        return audio_path, 0.0, 0.0

    target_path = output_path or audio_path
    temp_clean = audio_path.parent / f"_temp_cleaned_{os.getpid()}_{audio_path.name}"
    
    new_start = intro_cut
    new_duration = total_dur - intro_cut - outro_cut

    print(
        f"[PromoCleaner] ✂️ Đang cắt quảng cáo: Đầu clip (-{intro_cut:.2f}s), "
        f"Cuối clip (-{outro_cut:.2f}s). Thời lượng sạch: {new_duration/3600:.2f}h ({new_duration:.1f}s)..."
    )

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{new_start:.2f}",
        "-i", str(audio_path.resolve()),
        "-t", f"{new_duration:.2f}",
        "-c", "copy",
        str(temp_clean.resolve()),
    ]
    subprocess.run(cmd, check=True)

    # Replace original or save to output_path
    if temp_clean.exists() and temp_clean.stat().st_size > 1000:
        shutil.move(str(temp_clean), str(target_path))
        print(f"[PromoCleaner] ✅ Đã hoàn tất lọc quảng cáo kênh vào: {target_path.name}")
        return target_path, intro_cut, outro_cut
    else:
        if temp_clean.exists():
            temp_clean.unlink()
        return audio_path, 0.0, 0.0
