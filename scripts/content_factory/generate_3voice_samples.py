"""Generate ~3 minute samples of Hatake Clan Chapter 1 in 3 CapCut voices:
1. Nhỏ Ngọt Ngào (BV421_vivn_streaming)
2. Cô Gái Hoạt Ngôn (BV074_streaming)
3. Gái Mới Lớn (multi_female_peiqi_uranus_bigtts)
"""
import os
import sys
import json
import time
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(r"C:\Users\nguye\Documents\CapCut-TTS-App")
sys.path.insert(0, str(PROJECT_ROOT))

import requests
from capcut_tts_api.client import CapCutClient
from scripts.content_factory.re_tts_hatake_capcut import STORY_FILE, split_into_tts_sentences

USER_DOWNLOADS = Path(os.environ.get("USERPROFILE", r"C:\Users\nguye")) / "Downloads"

VOICES_TO_TEST = [
    {
        "id": "BV421_vivn_streaming",
        "name": "Nhỏ Ngọt Ngào",
        "out_file": USER_DOWNLOADS / "Hatake_C01_1_NhoNgotNgao.mp3",
    },
    {
        "id": "BV074_streaming",
        "name": "Cô Gái Hoạt Ngôn",
        "out_file": USER_DOWNLOADS / "Hatake_C01_2_CoGaiHoatNgon.mp3",
    },
    {
        "id": "multi_female_peiqi_uranus_bigtts",
        "name": "Gái Mới Lớn",
        "out_file": USER_DOWNLOADS / "Hatake_C01_3_GaiMoiLon.mp3",
    },
]

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

def synthesize_sample_voice(client: CapCutClient, voice_info: dict, sentences: list[str]):
    v_id = voice_info["id"]
    v_name = voice_info["name"]
    out_file = voice_info["out_file"]
    
    print(f"\n---> Đang tạo mẫu giọng: {v_name} ({v_id})...")
    tmp_dir = PROJECT_ROOT / "raw_spool" / f"temp_sample_{v_id}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 38 sentences in 2 batches of 19
    BATCH_SIZE = 19
    batches = [sentences[i:i+BATCH_SIZE] for i in range(0, len(sentences), BATCH_SIZE)]
    audio_items = []

    for b_idx, batch in enumerate(batches, 1):
        for attempt in range(3):
            try:
                res = client.generate_speech(batch, voice=v_id, timeout=40.0)
                payload = json.loads(res["data"]["tasks"][0]["payload"])
                subs = payload.get("audio_subtitles", [])
                for sub in subs:
                    audio_items.append({
                        "url": sub.get("speech_url", ""),
                        "duration": sub.get("duration", 0),
                    })
                print(f"     Batch {b_idx}/{len(batches)} xong ({len(subs)} câu)")
                break
            except Exception as e:
                print(f"     Batch {b_idx} lỗi ({e}), thử lại...")
                time.sleep(2)

    # Download
    session = requests.Session()
    downloaded_paths = []
    
    for i, item in enumerate(audio_items):
        part_p = tmp_dir / f"p_{i:03d}.mp3"
        url = item.get("url")
        if url:
            try:
                resp = session.get(url, timeout=20)
                if resp.status_code == 200:
                    part_p.write_bytes(resp.content)
                    downloaded_paths.append(part_p)
            except Exception as exc:
                print(f"     Lỗi tải part {i}: {exc}")

    # Concat
    concat_txt = tmp_dir / "concat.txt"
    concat_txt.write_text("\n".join(f"file '{p.as_posix()}'" for p in downloaded_paths), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c", "copy", str(out_file)]
    subprocess.run(cmd, check=True)

    dur = get_duration(out_file)
    sz_mb = out_file.stat().st_size / (1024 * 1024)
    print(f"  [✓] Hoàn thành {v_name}: {out_file.name}")
    print(f"      Thời lượng: {int(dur//60)}m{int(dur%60)}s | Dung lượng: {sz_mb:.2f} MB")
    
    # Cleanup temp mp3s
    for p in downloaded_paths:
        try: p.unlink()
        except: pass

    return {
        "name": v_name,
        "voice_id": v_id,
        "path": out_file,
        "duration": dur,
        "size_mb": sz_mb
    }

def main():
    print("=" * 60)
    print("  TẠO MẪU 3 PHÚT ĐẦU CHƯƠNG 1 VỚI 3 GIỌNG NỮ CAPCUT")
    print("=" * 60)

    raw_text = STORY_FILE.read_text(encoding="utf-8")
    all_sentences = [s for s in split_into_tts_sentences(raw_text) if s != "."]
    sample_sentences = all_sentences[:38] # ~38 câu, ~4000 ký tự -> ~3-3.5 phút
    print(f"[*] Trích xuất {len(sample_sentences)} câu đầu tiên (~{sum(len(s) for s in sample_sentences)} ký tự)")

    client = CapCutClient()
    results = []

    for v in VOICES_TO_TEST:
        res = synthesize_sample_voice(client, v, sample_sentences)
        results.append(res)

    print("\n" + "=" * 60)
    print("  🎉 TẤT CẢ 3 BẢN MẪU ĐÃ XUẤT THÀNH CÔNG VÀO DOWNLOADS:")
    for r in results:
        m = int(r["duration"] // 60)
        s = int(r["duration"] % 60)
        print(f"  * {r['name']}: {r['path']}")
        print(f"    -> Thời lượng: {m}p{s}s | {r['size_mb']:.2f} MB")
    print("=" * 60)

if __name__ == "__main__":
    main()
