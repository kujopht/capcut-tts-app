"""Re-classifies character roles for 'Giả Mù Ở Trường Nam Sinh' using Gemini 3.8 Flash,
and re-synthesizes multi-voice dubbing via CapCut TTS with zero cumulative drift.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from scripts.content_factory.animation_splitter import (
    LOCAL_ANIMATION_DIR,
    slice_production_to_10m_episodes,
)
from scripts.content_factory.gemini_evaluator import call_gemini, extract_json

MARATHON_DIR = (
    LOCAL_ANIMATION_DIR
    / "_source_marathons"
    / "[Đô Thị Hệ Thống] Giả Mù Ở Trường Nam Sinh - Ta Dùng Ác Ý Khiến Tứ Đại Thiếu Gia Phát Điên - Trọn Bộ"
)


def reclassify_marathon_subtitles(marathon_folder: Path) -> Path:
    ass_path = marathon_folder / "subtitle_vi.ass"
    if not ass_path.exists():
        raise FileNotFoundError(f"Missing subtitle_vi.ass in {marathon_folder}")

    raw_ass = ass_path.read_text(encoding="utf-8")
    lines = raw_ass.splitlines()

    dialogue_indices: List[Tuple[int, str, str, str, str]] = []  # (line_num, start, end, style, text)
    for i, line in enumerate(lines):
        if line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            if len(parts) >= 10:
                s_time = parts[1].strip()
                e_time = parts[2].strip()
                style = parts[3].strip()
                text = parts[9].strip()
                dialogue_indices.append((i, s_time, e_time, style, text))

    total_dialogues = len(dialogue_indices)
    print(f"[*] Tìm thấy {total_dialogues} câu thoại trong {ass_path.name}.")

    old_male = sum(1 for d in dialogue_indices if d[3] == "MaleVoice")
    old_female = sum(1 for d in dialogue_indices if d[3] == "FemaleVoice")
    print(f"    - Trước khi phân vai lại: Nam={old_male} ({old_male/total_dialogues*100:.1f}%), Nữ={old_female} ({old_female/total_dialogues*100:.1f}%)")

    # Chunk into batches of 40 lines
    chunk_size = 40
    chunks = []
    for k in range(0, total_dialogues, chunk_size):
        chunk_items = dialogue_indices[k : k + chunk_size]
        chunks.append((k + 1, chunk_items))

    print(f"[*] Gửi {len(chunks)} batch sang Gemini 3.8 Flash để phân định nhân vật...")

    gender_map: Dict[int, str] = {}  # 1-indexed dialogue -> 'male' / 'female'

    def _process_chunk(chunk_tuple):
        start_idx, items = chunk_tuple
        payload = []
        for offset, (_, _, _, _, txt) in enumerate(items):
            d_idx = start_idx + offset
            payload.append({"index": d_idx, "text": txt})

        prompt = f"""Bạn là đạo diễn lồng tiếng phim anime/novel chuyên nghiệp.
Tác phẩm: [Đô Thị Hệ Thống] Giả Mù Ở Trường Nam Sinh - Ta Dùng Ác Ý Khiến Tứ Đại Thiếu Gia Phát Điên.
Bối cảnh & Cốt truyện:
- NỮ CHÍNH là một cô gái nghèo (thiếu nữ, manh nữ), sở hữu Hệ Thống thu thập điểm ác ý để kiếm tiền trả nợ. Cô giả mù để nhập học vào một trường quý tộc toàn nam sinh (Trường Nam Sinh). Tại đây cô liên tục chọc tức 4 thiếu gia nhà giàu (Tứ Đại Thiếu Gia) cùng các nam sinh hống hách để cày điểm ác ý.
Quy tắc phân vai tuyệt đối chính xác:
- "female": Mọi câu thoại, độc thoại nội tâm suy nghĩ trong đầu của NỮ CHÍNH (xưng Tôi, Mình, Em, tính toán điểm hệ thống, đắc ý vì kiếm được tiền, giả vờ mù yếu đuối, than thở...), giọng thông báo của Hệ thống AI (hệ thống giọng nữ), và bất kỳ nhân vật nữ nào (mẹ, nữ phục vụ...).
- "male": Các câu thoại, quát tháo, đe dọa, bàn tán của Tứ Đại Thiếu Gia, các nam sinh trong trường, hiệu trưởng, thầy giáo, hoặc nhân vật nam.

Dưới đây là các câu thoại cần phân vai:
{json.dumps(payload, ensure_ascii=False, indent=2)}

BẮT BUỘC trả về ĐÚNG MỘT JSON ARRAY:
[
  {{"index": {start_idx}, "gender": "male" hoặc "female"}}
]
Chỉ trả về JSON array, không kèm bất kỳ giải thích nào.
"""
        for retry in range(3):
            try:
                res_raw = call_gemini(prompt, timeout_seconds=90)
                parsed = extract_json(res_raw)
                if isinstance(parsed, list):
                    res_dict = {}
                    for it in parsed:
                        if isinstance(it, dict) and "index" in it:
                            g = str(it.get("gender", "male")).strip().lower()
                            res_dict[int(it["index"])] = "female" if g in ["female", "nữ", "nu", "f", "girl"] else "male"
                    return res_dict
            except Exception as e:
                time.sleep(1.0)
        # Fallback to male if failed
        return {start_idx + off: "male" for off in range(len(items))}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        future_map = {pool.submit(_process_chunk, c): c for c in chunks}
        done_cnt = 0
        for fut in concurrent.futures.as_completed(future_map):
            res_dict = fut.result()
            gender_map.update(res_dict)
            done_cnt += 1
            if done_cnt % 5 == 0 or done_cnt == len(chunks):
                print(f"    Tiến độ phân vai: {done_cnt}/{len(chunks)} batch ({len(gender_map)}/{total_dialogues} câu)...")

    # Reconstruct ASS content with updated styles
    new_lines = []
    d_counter = 1
    new_male = 0
    new_female = 0

    for i, line in enumerate(lines):
        if line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            if len(parts) >= 10:
                g = gender_map.get(d_counter, "male")
                if g == "female":
                    parts[3] = "FemaleVoice"
                    new_female += 1
                else:
                    parts[3] = "MaleVoice"
                    new_male += 1
                line = ",".join(parts)
                d_counter += 1
        new_lines.append(line)

    print(f"\n[✓] HOÀN TẤT PHÂN VAI GEMINI 3.8 FLASH:")
    print(f"    - Trước: Nam={old_male}, Nữ={old_female}")
    print(f"    - Sau:   Nam={new_male} ({new_male/total_dialogues*100:.1f}%), Nữ={new_female} ({new_female/total_dialogues*100:.1f}%)")

    # Backup old ASS
    bak_ass = marathon_folder / "subtitle_vi.ass.bak"
    if not bak_ass.exists():
        shutil.copy(ass_path, bak_ass)

    ass_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"[✓] Đã ghi đè tệp ASS cập nhật phong cách phân vai mới: {ass_path.name}")
    return ass_path


def main():
    print("=" * 80)
    print("[*] BẮT ĐẦU RE-CLASSIFY & RE-DUB 'GIẢ MÙ Ở TRƯỜNG NAM SINH'")
    print("=" * 80)

    if not MARATHON_DIR.exists():
        print(f"[!] Không tìm thấy thư mục marathon: {MARATHON_DIR}")
        return

    # 1. Re-classify subtitle styles with Gemini
    reclassify_marathon_subtitles(MARATHON_DIR)

    # 2. Slice and Re-synthesize 10-minute episodes with multi-voice CapCut
    print("\n" + "=" * 80)
    print("[*] BẮT ĐẦU TỔNG HỢP LẠI ÂM THANH ĐA GIỌNG CAPCUT CHO TỪNG TẬP 10 PHÚT...")
    print("=" * 80)
    slice_production_to_10m_episodes(MARATHON_DIR, target_sec=600.0, force_synth=True)

    print("\n" + "=" * 80)
    print("[✓] ĐÃ HOÀN TẤT RE-DUB TOÀN BỘ CÁC TẬP CHO BỘ 'GIẢ MÙ Ở TRƯỜNG NAM SINH'!")
    print("=" * 80)


if __name__ == "__main__":
    main()
