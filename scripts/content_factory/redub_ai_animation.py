"""Re-dubs existing AI animation productions with authentic CapCut voices:
- Male dialogue: BV075_streaming (Thanh Niên Tự Tin)
- Female dialogue: BV421_vivn_streaming (Nhỏ Ngọt Ngào)

Reads exact timestamps and roles from subtitle_vi.ass, synthesizes via CapCutClient,
builds synchronized ducked audio track, and re-muxes video_dubbed.mp4 with audio ducking.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from capcut_tts_api.client import CapCutClient
import requests

from scripts.content_factory.worker3_ai_animation import (
    DialogueLine,
    VOICE_FEMALE,
    VOICE_MALE,
    _probe_duration,
)


def ass_time_to_seconds(t_str: str) -> float:
    """Converts ASS timestamp H:MM:SS.cs to seconds float."""
    parts = t_str.strip().split(":")
    h = float(parts[0])
    m = float(parts[1])
    s = float(parts[2])
    return h * 3600.0 + m * 60.0 + s


def parse_ass_dialogue_lines(ass_path: Path) -> List[DialogueLine]:
    """Parses ASS file into timestamped DialogueLine objects with speaker_gender."""
    content = ass_path.read_text(encoding="utf-8", errors="replace")
    lines: List[DialogueLine] = []
    idx = 1
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("Dialogue:"):
            continue
        # Dialogue: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        start_sec = ass_time_to_seconds(parts[1])
        end_sec = ass_time_to_seconds(parts[2])
        style = parts[3].strip()
        gender = "female" if style == "FemaleVoice" else "male"
        text = parts[9].strip()
        # Clean any remaining ASS formatting tags like {\k...} or \N
        text = re.sub(r"\{.*?\}", "", text)
        text = text.replace(r"\N", " ").replace(r"\n", " ").strip()
        if not text:
            continue
        lines.append(
            DialogueLine(
                index=idx,
                start=start_sec,
                end=end_sec,
                original_text=text,
                vi_text=text,
                speaker_gender=gender,
            )
        )
        idx += 1
    return lines


def redub_production(folder: Path) -> bool:
    """Re-synthesizes dub audio and re-muxes video_dubbed.mp4 for a production folder."""
    print(f"\n{'='*70}")
    print(f"[*] BẮT ĐẦU LỒNG TIẾNG LẠI (AUTHENTIC CAPCUT VOICES): {folder.name[:60]}")
    print(f"{'='*70}")

    ass_path = folder / "subtitle_vi.ass"
    if not ass_path.exists():
        print(f"[!] Không tìm thấy subtitle_vi.ass trong {folder}")
        return False

    lines = parse_ass_dialogue_lines(ass_path)
    print(f"[+] Đã đọc {len(lines)} câu thoại từ ASS:")
    male_count = sum(1 for l in lines if l.speaker_gender == "male")
    female_count = sum(1 for l in lines if l.speaker_gender == "female")
    print(f"    - Giọng Nam (BV075_streaming - Thanh Niên Tự Tin): {male_count} câu")
    print(f"    - Giọng Nữ (BV421_vivn_streaming - Nhỏ Ngọt Ngào): {female_count} câu")

    # Probe total duration from video_vietsub.mp4 or audio_dub.mp3
    vietsub_v = folder / "video_vietsub.mp4"
    if vietsub_v.exists():
        total_duration = _probe_duration(vietsub_v)
    else:
        dub_old = folder / "audio_dub.mp3"
        total_duration = _probe_duration(dub_old)
    print(f"[+] Thời lượng video: {total_duration:.1f}s ({total_duration/60:.1f} phút)")

    temp_dir = Path(tempfile.mkdtemp(prefix="redub_"))

    # 1. Parallel TTS synthesis with local CapCutClient
    line_parts: Dict[int, Path] = {}
    valid_lines = [l for l in lines if l.vi_text.strip() and not re.search(r"[\u4e00-\u9fff]", l.vi_text)]
    print(f"[+] Tổng hợp song song {len(valid_lines)} câu thoại qua CapCut Client (4 luồng)...")

    def _synth_worker(l: DialogueLine):
        voice_id = VOICE_FEMALE if l.speaker_gender == "female" else VOICE_MALE
        part_mp3 = temp_dir / f"dub_{l.index}.mp3"
        client = CapCutClient()
        for retry in range(3):
            try:
                res = client.generate_speech([l.vi_text], voice=voice_id, timeout=30.0)
                payload = json.loads(res["data"]["tasks"][0]["payload"])
                sub = payload["audio_subtitles"][0]
                url = sub.get("speech_url")
                if url:
                    r = requests.get(url, timeout=20)
                    if r.status_code == 200 and len(r.content) > 100:
                        part_mp3.write_bytes(r.content)
                        return l.index, part_mp3
            except Exception:
                time.sleep(0.5)
        print(f"    [!] Cảnh báo: Câu {l.index} thất bại sau 3 lần thử: '{l.vi_text[:40]}'")
        return l.index, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futs = [pool.submit(_synth_worker, l) for l in valid_lines]
        done_cnt = 0
        for f in concurrent.futures.as_completed(futs):
            idx, p = f.result()
            if p and p.exists() and p.stat().st_size > 100:
                line_parts[idx] = p
            done_cnt += 1
            if done_cnt % 50 == 0 or done_cnt == len(valid_lines):
                print(f"    Tiến độ lồng tiếng CapCut: {done_cnt}/{len(valid_lines)} câu hoàn tất...")

    # 2. Chronological assembly with silence gaps
    print(f"[+] Sắp xếp {len(line_parts)} phân đoạn lồng tiếng vào trục thời gian...")
    entries: List[Path] = []
    cursor = 0.0

    for l in valid_lines:
        part_mp3 = line_parts.get(l.index)
        if not part_mp3:
            continue

        gap = max(0.0, l.start - cursor)
        if gap > 0.03:
            silence_mp3 = temp_dir / f"silence_{l.index}.mp3"
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-c:a", "libmp3lame", "-b:a", "192k",
                "-t", f"{gap:.3f}", str(silence_mp3)
            ], check=True)
            entries.append(silence_mp3)
            cursor += gap

        dur = _probe_duration(part_mp3)
        entries.append(part_mp3)
        cursor += dur

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

    if not entries:
        print("[!] Lỗi: Không có phân đoạn audio nào được tạo.")
        return False

    concat_list = temp_dir / "dub_concat.txt"
    concat_list.write_text("\n".join([f"file '{p.resolve().as_posix()}'" for p in entries]), encoding="utf-8")

    out_dub_audio = folder / "audio_dub.mp3"
    print(f"[+] Đang xuất file lồng tiếng hoàn chỉnh: {out_dub_audio.name}...")
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(out_dub_audio),
    ], check=True)
    print(f"[✓] Đã tạo file audio_dub.mp3 mới ({out_dub_audio.stat().st_size:,} bytes)!")

    # 3. Fast re-mux video_dubbed.mp4 from video_vietsub.mp4 (stream copy video, ducked audio)
    dubbed_v = folder / "video_dubbed.mp4"
    if vietsub_v.exists():
        print(f"[+] Mux lại video_dubbed.mp4 với âm thanh mới (Video stream copy siêu tốc)...")
        temp_dubbed_v = folder / "video_dubbed_temp.mp4"
        cmd_remux = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(vietsub_v.resolve()),
            "-i", str(out_dub_audio.resolve()),
            "-filter_complex",
            "[0:a]volume=0.16[a_bg];[1:a]volume=1.05[a_fg];[a_bg][a_fg]amix=inputs=2:duration=first[a_out]",
            "-map", "0:v",
            "-map", "[a_out]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            str(temp_dubbed_v.resolve()),
        ]
        subprocess.run(cmd_remux, check=True)
        if temp_dubbed_v.exists() and temp_dubbed_v.stat().st_size > 100000:
            if dubbed_v.exists():
                dubbed_v.unlink()
            temp_dubbed_v.rename(dubbed_v)
            print(f"[✓] Đã tạo video_dubbed.mp4 mới ({dubbed_v.stat().st_size:,} bytes)!")
    else:
        print("[!] Không tìm thấy video_vietsub.mp4, bỏ qua re-mux video")

    # 4. Clean up temp dir
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass

    return True


def sync_folder_to_drive(folder: Path):
    """Syncs folder to Google Drive."""
    remote_dir = f"fanfic-gdrive:FanficWorld/production/works/ai-animation/{folder.name}"
    print(f"\n[*] Đang đồng bộ lên Google Drive: {remote_dir}...")
    subprocess.run([
        "rclone", "copy", str(folder), remote_dir,
        "--include", "audio_dub.mp3",
        "--include", "video_dubbed.mp4",
        "--include", "metadata.json",
        "--progress"
    ], check=True)
    print(f"[✓] Đồng bộ Drive hoàn tất: {remote_dir}")


def main():
    ai_dir = Path("raw_spool/ai_animation")

    # Targets to redub
    targets = [
        ai_dir / "[Original - Ngôn Tình Đô Thị Hệ Thống] MULTISUB📢新番上线《被四个病娇盯上，盲女她杀疯了！》第1~14集丨贫穷少女独入贵族男校，伪装失明避财阀恶少，却渐渐",
        ai_dir / "[Điềm Điềm Tiểu Tuyết (甜甜小雪) - Ngôn Tình Thanh Xuân] 【全集FULL】【甜甜小雪第二季番外】青梅竹马意外同居青春日常藏满温柔心动热播漫剧 推薦 面包",
    ]

    # Clean up unfinished duplicate folder
    dup = ai_dir / "[Đô Thị Hệ Thống - Ngôn Tình Học Đường] MULTISUB📢新番上线《被四个病娇盯上，盲女她杀疯了！》第1~14集丨贫穷少女独入贵族男校，伪装失明避财阀恶少，却渐"
    if dup.exists():
        print(f"[*] Dọn dẹp thư mục trùng lặp chưa hoàn thành: {dup.name[:60]}")
        shutil.rmtree(dup, ignore_errors=True)

    for folder in targets:
        if folder.exists():
            ok = redub_production(folder)
            if ok:
                sync_folder_to_drive(folder)

    print("\n[✓] TẤT CẢ CÁC BỘ PHIM AI ĐÃ ĐƯỢC LỒNG TIẾNG LẠI HOÀN TOÀN BẰNG GIỌNG CAPCUT CHUẨN!")


if __name__ == "__main__":
    main()
