"""
Script to re-synthesize the 10 fanfic productions that accidentally used Hoài My
back into genuine Piper Ngọc Huyền (Mới - NghiTTS).
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Force UTF-8 and unbuffered output
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.content_factory.worker2_text_fanfic import (
    DRIVE_TARGET_BASE,
    LOCAL_SPOOL_DIR,
    _probe_duration,
    split_sentences_for_transcript,
    synthesize_with_synchronized_transcript,
)

# Exactly the 10 folders that were generated with Hoài My
HOAIMY_FOLDERS = [
    "[Naruto] Khởi Đầu Luân Hồi Nhãn, Đêm Diệt Tộc Ta Nghịch Thiên Cứu Cả Gia Tộc - Chương 01",
    "[Naruto] Mộc Diệp Chi Luân Hồi - Ta Nghịch Chuyển Đêm Diệt Tộc Uchiha - Chương 01",
    "[Naruto] Mộc Diệp Chi Luân Hồi - Ta Nghịch Chuyển Đêm Diệt Tộc Uchiha - Chương 02",
    "[Harry Potter] Hogwarts - Kẻ Thao Túng Huyết Thống Cổ Đại - Chương 01",
    "[Harry Potter] Hogwarts - Kẻ Thao Túng Huyết Thống Cổ Đại - Chương 02",
    "[One Piece (Đảo Hải Tặc)] Hải Tặc - Trảm Đoạn Vận Mệnh, Cực Đạo Kiếm Hào - Chương 01",
    "[Naruto] Đêm Trăng Máu, Ta Thức Tỉnh Luân Hồi Nhãn Cứu Vớt Uchiha - Chương 01",
    "[Naruto] Mộc Diệp - Khởi Đầu Luân Hồi Nhãn, Ta Đạp Nát Kịch Bản Diệt Tộc Uchiha! - Chương 01",
    "[Naruto] Mộc Diệp - Khởi Đầu Luân Hồi Nhãn, Ta Đạp Nát Kịch Bản Diệt Tộc Uchiha! - Chương 02",
    "[Harry Potter] Hogwarts - Huyết Thống Cổ Đại Chi Phối Vận Mệnh - Chương 01",
]


def repair_one(folder: Path, sync_drive: bool = True) -> bool:
    print(f"\n{'='*70}", flush=True)
    print(f"[*] BẮT ĐẦU SỬA: {folder.name}", flush=True)
    print(f"{'='*70}", flush=True)

    if not folder.exists():
        print(f"[!] Không tìm thấy thư mục: {folder.name}", flush=True)
        return False

    story_file = folder / "story_vi.txt"
    if not story_file.exists():
        print(f"[!] Thiếu file story_vi.txt trong {folder.name}", flush=True)
        return False

    meta_path = folder / "metadata.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("repaired_ngochuyen"):
                print(f"[✓] Đã sửa trước đó rồi, bỏ qua!", flush=True)
                return True
        except Exception:
            pass

    story_text = story_file.read_text(encoding="utf-8")
    sentences = split_sentences_for_transcript(story_text)
    print(f"[+] Kịch bản có {len(sentences)} câu. Bắt đầu tổng hợp giọng Ngọc Huyền Mới (Piper)...", flush=True)

    # Clean any stale parts
    parts_dir = folder / "audio_parts"
    if parts_dir.exists():
        import shutil
        try:
            shutil.rmtree(parts_dir)
        except Exception:
            pass

    t0 = time.time()
    master_audio, srt_path, json_path = synthesize_with_synchronized_transcript(
        sentences, folder, rate="1.0"
    )
    elapsed = time.time() - t0
    dur = _probe_duration(master_audio)
    print(f"[✓] Tổng hợp xong trong {elapsed:.1f}s! Thời lượng audio: {dur:.1f}s ({dur/60:.1f} phút)", flush=True)

    # Update metadata
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["voice"] = "piper:ngochuyennew"
            meta["voice_name"] = "Ngọc Huyền (NghiTTS)"
            meta["duration_seconds"] = round(dur, 2)
            meta["repaired_ngochuyen"] = True
            meta["repaired_at"] = datetime.now().isoformat()
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[+] Cập nhật metadata.json: Giọng Ngọc Huyền (Mới)", flush=True)
        except Exception as e:
            print(f"[!] Lỗi ghi metadata: {e}", flush=True)

    # Sync to Drive
    if sync_drive:
        drive_dest = f"{DRIVE_TARGET_BASE}/{folder.name}"
        print(f"[+] Đang đồng bộ đè lên Google Drive: {drive_dest}...", flush=True)
        rclone_cmd = [
            "rclone", "copy",
            str(folder),
            drive_dest,
            "--drive-chunk-size", "32M",
            "--transfers", "4",
            "-q",
        ]
        try:
            subprocess.run(rclone_cmd, check=True)
            print(f"[✓] Đồng bộ Google Drive thành công!", flush=True)
        except Exception as e:
            print(f"[!] Lỗi rclone: {e}", flush=True)

    return True


def main():
    print(f"[*] Tổng số tác phẩm cần chuyển sang giọng Ngọc Huyền: {len(HOAIMY_FOLDERS)}", flush=True)

    success_count = 0
    for idx, name in enumerate(HOAIMY_FOLDERS, 1):
        target = LOCAL_SPOOL_DIR / name
        print(f"\n>>> Tiến trình [{idx}/{len(HOAIMY_FOLDERS)}]", flush=True)
        ok = repair_one(target, sync_drive=True)
        if ok:
            success_count += 1

    print(f"\n{'='*70}", flush=True)
    print(f"[✓] HOÀN TẤT! Đã sửa thành công {success_count}/{len(HOAIMY_FOLDERS)} tác phẩm sang giọng Ngọc Huyền Mới!", flush=True)
    print(f"{'='*70}", flush=True)


if __name__ == "__main__":
    main()
