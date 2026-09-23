import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("raw_spool/web_ready_catalog.json", encoding="utf-8") as f:
    data = json.load(f)

for b_key, b_name in [
    ("youtube_audio", "NHÁNH 1: AUDIOBOOK YOUTUBE (ALBUMS & TÁC PHẨM ĐÃ TỔNG HỢP)"),
    ("fanfic_tts", "NHÁNH 2: TRUYỆN CHỮ FANFIC/NOVEL TTS (FULL CHƯƠNG)"),
    ("ai_animation", "NHÁNH 3: PHIM HOẠT HÌNH AI 2D (VIDEO 1080P VIETSUB & THUYẾT MINH)")
]:
    print(f"\n{'='*20} {b_name} {'='*20}")
    series_list = data["branches"].get(b_key, [])
    valid = [s for s in series_list if any(e.get("has_audio") or e.get("has_video") for e in s["episodes"]) and s["total_duration_hours"] > 0]
    total_eps = 0
    total_time = 0.0
    for idx, s in enumerate(valid, 1):
        eps = [e for e in s["episodes"] if e.get("has_audio") or e.get("has_video")]
        total_eps += len(eps)
        total_time += s["total_duration_hours"]
        print(f"{idx:02d}. {s['series_title']}")
        print(f"    - Fandom: {s['fandom']} | {len(eps)} tập/chương | {s['total_duration_formatted']} | Điểm: {s['quality_score']}/10")
    print(f"\n--> TỔNG CỘNG: {len(valid)} bộ | {total_eps} tập | {total_time:.1f} tiếng")
