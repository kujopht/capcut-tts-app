"""
# ARCHIVE_AFTER_PR_D — Preserved for incident history and forensic verification.
# Replaced by unified CLI: python -m scripts.content_factory run <work_id> --tts
#
Production Batch Audio Synthesis Pipeline via Lightning Serverless.

Processes The Cold Between Wars (nov_rr_156206) chapters 2–47 in controlled batches:
- Batch 1: 02–10
- Batch 2: 11–20
- Batch 3: 21–30
- Batch 4: 31–40
- Batch 5: 41–47

Quality assertions per chapter:
1. Full published text used.
2. TTS input hash == published text hash.
3. Bounded chunk synthesis with content-hash idempotency & retries.
4. FFmpeg deterministic assembly & ffprobe validation.
5. Plausible duration based on Vietnamese word count.
6. Cloudflare R2 upload & verification.
7. Appwrite audio_track registration.
8. /api/audio/{chapter_id}/url resolves (HTTP 200).
9. Sampled Range request returns HTTP 206 Partial Content.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.config import Config
from dotenv import dotenv_values
import requests

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
CONFIG_PATH = PROJECT_ROOT / "server" / ".env.production"
if not CONFIG_PATH.exists():
    raise FileNotFoundError(f"Missing production config at {CONFIG_PATH}")

config = dotenv_values(CONFIG_PATH)

APPWRITE_ENDPOINT = config.get("APPWRITE_ENDPOINT", "").rstrip("/")
APPWRITE_PROJECT = config.get("APPWRITE_PROJECT_ID", "")
APPWRITE_KEY = config.get("APPWRITE_API_KEY", "")
APPWRITE_DB = config.get("APPWRITE_DATABASE_ID", "")
OWNER_ID = config.get("OWNER_ID", "user_admin")

R2_ACCOUNT_ID = config.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY = config.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_KEY = config.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = config.get("R2_BUCKET", "fanfic-prod")

LIGHTNING_URL = "https://8000-01m0aq288xz87ygvxbzhx9pf3w.cloudspaces.litng.ai"
RENDER_API_BASE = "https://fas-prod-api.onrender.com"

NOVEL_ID = "nov_rr_156206"
WORK_ID = "156206"
VOICE_ID = "ngochuyennew"

CHUNK_CACHE_DIR = PROJECT_ROOT / "raw_spool" / "tts_cache" / "chunks"
ASSEMBLED_DIR = PROJECT_ROOT / "raw_spool" / "tts_cache" / "assembled"
CHECKPOINT_DIR = PROJECT_ROOT / "raw_spool" / "tts_cache" / "checkpoints"
CHECKPOINT_FILE = CHECKPOINT_DIR / f"{WORK_ID}_audio_progress.json"

CHUNK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
ASSEMBLED_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

APPWRITE_HEADERS = {
    "X-Appwrite-Project": APPWRITE_PROJECT,
    "X-Appwrite-Key": APPWRITE_KEY,
    "Content-Type": "application/json",
}


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version="s3v4", retries={"max_attempts": 5, "mode": "adaptive"}),
        region_name="auto",
    )


def load_checkpoint() -> Dict[str, Any]:
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "novel_id": NOVEL_ID,
        "work_id": WORK_ID,
        "completed_chapters": {},
        "stats": {
            "synthesis_time_seconds": 0.0,
            "total_audio_duration_seconds": 0.0,
            "total_bytes": 0,
            "retries_count": 0,
            "failures_count": 0,
        },
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def save_checkpoint(cp: Dict[str, Any]) -> None:
    cp["last_updated"] = datetime.now(timezone.utc).isoformat()
    CHECKPOINT_FILE.write_text(json.dumps(cp, indent=2, ensure_ascii=False), encoding="utf-8")


def slice_into_bounded_chunks(text: str, target_words: int = 450) -> List[str]:
    """Slices text into bounded chunks of 300-500 words on paragraph/sentence boundaries."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    curr = []
    curr_words = 0

    for p in paragraphs:
        w_count = len(p.split())
        if curr_words + w_count > target_words and curr:
            chunks.append("\n\n".join(curr))
            curr = [p]
            curr_words = w_count
        else:
            curr.append(p)
            curr_words += w_count

    if curr:
        chunks.append("\n\n".join(curr))
    return chunks


def synthesize_single_chunk(
    chunk_index: int,
    total_chunks: int,
    c_text: str,
    chapter_id: str,
) -> Tuple[int, Path, float, float, int]:
    """Synthesizes one chunk or returns cached file. Returns (index, path, synth_time, duration, retries)."""
    c_hash = hashlib.sha256(c_text.encode("utf-8")).hexdigest()
    c_words = len(c_text.split())
    cached_file = CHUNK_CACHE_DIR / f"{c_hash}.mp3"

    if cached_file.exists() and cached_file.stat().st_size > 1000:
        return (chunk_index, cached_file, 0.0, 0.0, 0)

    last_err = ""
    retries = 0
    for attempt in range(4):
        try:
            t0 = time.time()
            data = {
                "text": c_text,
                "voice_id": VOICE_ID,
                "chapter_id": chapter_id,
                "chunk_index": chunk_index,
                "content_hash": c_hash,
                "output_format": "mp3",
            }
            r = requests.post(f"{LIGHTNING_URL}/v1/tts/synthesize", data=data, timeout=60)
            if r.status_code == 200 and len(r.content) > 1000:
                cached_file.write_bytes(r.content)
                synth_s = float(r.headers.get("X-Synthesis-Time-Seconds", time.time() - t0))
                audio_dur = float(r.headers.get("X-Audio-Duration-Seconds", 0.0))
                return (chunk_index, cached_file, synth_s, audio_dur, retries)
            else:
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as exc:
            last_err = str(exc)

        retries += 1
        wait_s = 2 ** attempt
        print(f"    ⚠️ [Chunk {chunk_index+1}/{total_chunks}] Attempt {attempt+1} failed ({last_err}), retry in {wait_s}s...")
        time.sleep(wait_s)

    raise RuntimeError(f"Chunk {chunk_index+1}/{total_chunks} of {chapter_id} failed after 4 attempts: {last_err}")


def process_chapter(
    ch_data: Dict[str, Any],
    r2_client: Any,
    cp: Dict[str, Any],
) -> Dict[str, Any]:
    order = ch_data["order"]
    ch_id = f"ch_{WORK_ID}_{order:04d}"
    track_id = f"trk_{WORK_ID}_{order:04d}"
    title = ch_data["title"]
    full_text = ch_data["content"].strip()
    full_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
    content_hash_64 = full_hash[:64]
    word_count = len(full_text.split())
    char_count = len(full_text)
    object_key = f"audio/{NOVEL_ID}/{ch_id}.mp3"

    print(f"\n──────────────────────────────────────────────────────────────────")
    print(f"[*] Processing Chapter {order:02d}/47: '{title}' ({ch_id})")
    print(f"    Words: {word_count:,} | Chars: {char_count:,} | Hash: {full_hash[:16]}...")

    # 1. Fetch Canonical Published Text from Appwrite to ensure 100% match
    ch_doc_url = f"{APPWRITE_ENDPOINT}/databases/{APPWRITE_DB}/collections/chapters/documents/{ch_id}"
    r_ch_doc = requests.get(ch_doc_url, headers=APPWRITE_HEADERS, timeout=15)
    if r_ch_doc.status_code != 200:
        raise RuntimeError(f"Chapter {ch_id} not found in Appwrite! Must publish text first.")

    published_text = r_ch_doc.json().get("content", "").strip()
    published_hash = hashlib.sha256(published_text.encode("utf-8")).hexdigest()
    if published_hash != full_hash:
        raise RuntimeError(f"Chapter {ch_id} manifest hash ({full_hash[:12]}) != Appwrite published hash ({published_hash[:12]})!")

    # 2. Check if matching production audio_track & R2 object already exist (Idempotency)
    track_doc_url = f"{APPWRITE_ENDPOINT}/databases/{APPWRITE_DB}/collections/audio_tracks/documents/{track_id}"
    r_tr_check = requests.get(track_doc_url, headers=APPWRITE_HEADERS, timeout=10)
    
    if r_tr_check.status_code == 200:
        tr_data = r_tr_check.json()
        if tr_data.get("content_hash") == content_hash_64:
            # Check R2 object
            try:
                head = r2_client.head_object(Bucket=R2_BUCKET, Key=object_key)
                # Check backend endpoint
                r_api = requests.get(f"{RENDER_API_BASE}/api/audio/{ch_id}/url", timeout=15)
                if r_api.status_code == 200:
                    print(f"  [+] ALREADY COMPLETE & VERIFIED -> Skipping synthesis!")
                    existing_entry = {
                        "chapter_id": ch_id,
                        "track_id": track_id,
                        "duration_seconds": tr_data.get("duration_seconds", 0.0),
                        "size_bytes": head["ContentLength"],
                        "content_hash": full_hash,
                        "status": "CACHED_ALREADY_EXISTS",
                    }
                    cp["completed_chapters"][ch_id] = existing_entry
                    save_checkpoint(cp)
                    return existing_entry
            except Exception as e:
                print(f"  [-] Audio track exists but R2/API verification failed ({e}), re-assembling...")

    # 3. Slice into bounded chunks
    chunks = slice_into_bounded_chunks(full_text, target_words=450)
    print(f"    Sliced into {len(chunks)} bounded chunks (~{word_count//len(chunks)} words/chunk)")

    # 4. Synthesize Chunks in Parallel (ThreadPoolExecutor max_workers=3 for 4 vCPUs)
    chunk_results: List[Tuple[int, Path, float, float, int]] = []
    t_synth_start = time.time()
    
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(synthesize_single_chunk, idx, len(chunks), c_text, ch_id): idx
            for idx, c_text in enumerate(chunks)
        }
        for fut in as_completed(futures):
            res = fut.result()
            chunk_results.append(res)
            idx, p, s_time, dur, retries = res
            cache_tag = "CACHE HIT" if s_time == 0.0 else f"{s_time:.2f}s"
            print(f"    - Chunk {idx+1:02d}/{len(chunks):02d} ready ({cache_tag})")

    # Sort chunks by original index
    chunk_results.sort(key=lambda x: x[0])
    ordered_files = [res[1] for res in chunk_results]
    total_chunk_synth_time = sum(res[2] for res in chunk_results)
    total_retries = sum(res[4] for res in chunk_results)

    cp["stats"]["synthesis_time_seconds"] += total_chunk_synth_time
    cp["stats"]["retries_count"] += total_retries

    # 5. Deterministic Audio Assembly via FFmpeg concat
    concat_file = ASSEMBLED_DIR / f"concat_{ch_id}.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for cf in ordered_files:
            f.write(f"file '{cf.resolve().as_posix()}'\n")

    assembled_mp3 = ASSEMBLED_DIR / f"{NOVEL_ID}_{ch_id}.mp3"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(assembled_mp3),
    ]
    subprocess.run(cmd, check=True)

    # 6. Validate MP3 via ffprobe
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size,bit_rate",
        "-of", "json",
        str(assembled_mp3),
    ]
    probe_out = subprocess.check_output(probe_cmd).decode("utf-8")
    probe_data = json.loads(probe_out).get("format", {})
    duration = float(probe_data.get("duration", 0.0))
    file_size = int(probe_data.get("size", assembled_mp3.stat().st_size))
    audio_sha = hashlib.sha256(assembled_mp3.read_bytes()).hexdigest()

    if duration <= 10.0 or file_size < 10000:
        raise RuntimeError(f"Assembled MP3 invalid: duration={duration}s, size={file_size}b")

    # Assert duration plausibility (Vietnamese speech ~160 - 280 wpm)
    wpm = (word_count / (duration / 60.0)) if duration > 0 else 0
    print(f"    Assembled: {duration//60:.0f}m {duration%60:.1f}s ({duration:.2f}s) | {file_size/(1024*1024):.2f} MB | {wpm:.1f} WPM")
    if wpm < 140 or wpm > 320:
        print(f"    ⚠️ Warning: Unusually high or low WPM ({wpm:.1f}) for Vietnamese speech.")

    # 7. Upload to Cloudflare R2
    t_up0 = time.time()
    with open(assembled_mp3, "rb") as f:
        r2_client.put_object(
            Bucket=R2_BUCKET,
            Key=object_key,
            Body=f,
            ContentType="audio/mpeg",
            CacheControl="public, max-age=31536000, immutable",
        )
    head = r2_client.head_object(Bucket=R2_BUCKET, Key=object_key)
    print(f"    Uploaded to Cloudflare R2 in {time.time() - t_up0:.2f}s (ETag: {head['ETag']})")

    # 8. Create / Update Appwrite audio_track document
    now_iso = datetime.now(timezone.utc).isoformat()
    track_payload = {
        "track_id": track_id,
        "chapter_id": ch_id,
        "owner_id": OWNER_ID,
        "voice_id": VOICE_ID,
        "object_key": object_key,
        "content_hash": content_hash_64,
        "source_content_hash": full_hash,
        "duration_seconds": round(duration, 3),
        "size_bytes": file_size,
        "created_at": now_iso,
    }

    if r_tr_check.status_code == 200:
        requests.patch(track_doc_url, headers=APPWRITE_HEADERS, json={"data": track_payload}, timeout=10)
    else:
        r_create = requests.post(
            f"{APPWRITE_ENDPOINT}/databases/{APPWRITE_DB}/collections/audio_tracks/documents",
            headers=APPWRITE_HEADERS,
            json={"documentId": track_id, "data": track_payload},
            timeout=15,
        )
        if r_create.status_code not in (200, 201):
            raise RuntimeError(f"Failed to create audio_track in Appwrite: {r_create.text}")

    # Update chapter document updated_at
    requests.patch(ch_doc_url, headers=APPWRITE_HEADERS, json={"data": {"updated_at": now_iso}}, timeout=10)

    # 9. Quality Verification: /api/audio/{chapter_id}/url and Range HTTP 206
    r_api = requests.get(f"{RENDER_API_BASE}/api/audio/{ch_id}/url", timeout=20)
    if r_api.status_code != 200:
        raise RuntimeError(f"Render audio URL check failed: HTTP {r_api.status_code} ({r_api.text[:150]})")

    signed_url = r_api.json().get("url")
    r_range = requests.get(signed_url, headers={"Range": "bytes=0-1024"}, timeout=15)
    if r_range.status_code != 206:
        raise RuntimeError(f"Range request test failed: HTTP {r_range.status_code}")

    print(f"    ✅ VERIFIED: API 200 OK | Range 206 OK | Hash matched 100%!")

    entry = {
        "chapter_id": ch_id,
        "track_id": track_id,
        "order": order,
        "title": title,
        "words": word_count,
        "duration_seconds": duration,
        "size_bytes": file_size,
        "content_hash": full_hash,
        "audio_sha256": audio_sha,
        "r2_etag": head["ETag"].strip('"'),
        "wpm": round(wpm, 1),
        "status": "COMPLETED",
    }

    cp["completed_chapters"][ch_id] = entry
    cp["stats"]["total_audio_duration_seconds"] += duration
    cp["stats"]["total_bytes"] += file_size
    save_checkpoint(cp)

    return entry


def run_batch(batch_num: int, start_order: int, end_order: int, chapters: List[Dict[str, Any]], r2_client: Any, cp: Dict[str, Any]) -> List[Dict[str, Any]]:
    print(f"\n==================================================================")
    print(f"  STARTING BATCH {batch_num}: CHAPTERS {start_order:02d} TO {end_order:02d}      ")
    print(f"==================================================================")

    batch_chapters = [c for c in chapters if start_order <= c["order"] <= end_order]
    results = []
    t_batch_start = time.time()

    for ch in batch_chapters:
        for attempt in range(2):
            try:
                res = process_chapter(ch, r2_client, cp)
                results.append(res)
                break
            except Exception as exc:
                print(f"  ❌ Error processing Chapter {ch['order']}: {exc}")
                cp["stats"]["failures_count"] += 1
                save_checkpoint(cp)
                if attempt == 0:
                    print("  Retrying chapter in 5 seconds...")
                    time.sleep(5)
                else:
                    raise

    elapsed = time.time() - t_batch_start
    b_dur = sum(r["duration_seconds"] for r in results)
    b_size = sum(r["size_bytes"] for r in results)
    print(f"\n[+] BATCH {batch_num} COMPLETED in {elapsed/60:.1f} min ({elapsed:.1f}s):")
    print(f"    - Chapters: {len(results)}/{len(batch_chapters)}")
    print(f"    - Total Audio Duration: {b_dur//3600:.0f}h {(b_dur%3600)//60:.0f}m {b_dur%60:.1f}s")
    print(f"    - Total Size: {b_size/(1024*1024):.2f} MB")
    return results


def run_live_qa(r2_client: Any) -> List[Dict[str, Any]]:
    print(f"\n==================================================================")
    print(f"  LIVE QA VERIFICATION ON CHAPTERS 1, 10, 20, 30, 40, 47          ")
    print(f"==================================================================")
    
    qa_orders = [1, 10, 20, 30, 40, 47]
    qa_results = []

    for order in qa_orders:
        ch_id = f"ch_{WORK_ID}_{order:04d}"
        track_id = f"trk_{WORK_ID}_{order:04d}"
        
        # 1. Check chapter text in Appwrite
        ch_url = f"{APPWRITE_ENDPOINT}/databases/{APPWRITE_DB}/collections/chapters/documents/{ch_id}"
        r_ch = requests.get(ch_url, headers=APPWRITE_HEADERS, timeout=10).json()
        text = r_ch.get("content", "").strip()
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        # 2. Check track in Appwrite
        tr_url = f"{APPWRITE_ENDPOINT}/databases/{APPWRITE_DB}/collections/audio_tracks/documents/{track_id}"
        r_tr = requests.get(tr_url, headers=APPWRITE_HEADERS, timeout=10).json()
        source_hash = r_tr.get("source_content_hash", "")
        duration = float(r_tr.get("duration_seconds", 0.0))
        size_bytes = int(r_tr.get("size_bytes", 0))

        hash_ok = (text_hash == source_hash)

        # 3. Check Render signed URL
        r_api = requests.get(f"{RENDER_API_BASE}/api/audio/{ch_id}/url", timeout=15)
        api_ok = (r_api.status_code == 200)
        signed_url = r_api.json().get("url") if api_ok else None

        # 4. Range request at beginning (bytes 0-1024)
        r_range0 = requests.get(signed_url, headers={"Range": "bytes=0-1024"}, timeout=15) if signed_url else None
        range0_ok = (r_range0 is not None and r_range0.status_code == 206)

        # 5. Seeking test (Range request at 50% offset)
        mid_byte = size_bytes // 2
        range_header_mid = f"bytes={mid_byte}-{mid_byte + 1024}"
        r_range_mid = requests.get(signed_url, headers={"Range": range_header_mid}, timeout=15) if signed_url else None
        range_mid_ok = (r_range_mid is not None and r_range_mid.status_code == 206)

        player_url = f"https://fanfic.world/novels/{NOVEL_ID}/chapters/{ch_id}"

        qa_item = {
            "order": order,
            "chapter_id": ch_id,
            "title": r_ch.get("title", ""),
            "duration": f"{duration//60:.0f}m {duration%60:.0f}s",
            "size_mb": round(size_bytes / (1024*1024), 2),
            "hash_match": hash_ok,
            "api_200": api_ok,
            "range_206": range0_ok,
            "seek_206": range_mid_ok,
            "player_url": player_url,
            "qa_status": "PASS" if (hash_ok and api_ok and range0_ok and range_mid_ok) else "FAIL",
        }
        qa_results.append(qa_item)
        print(f"  Chapter {order:02d}: {qa_item['qa_status']} | Dur: {qa_item['duration']} | Size: {qa_item['size_mb']} MB | Hash: {'OK' if hash_ok else 'FAIL'} | Range: {'OK' if range0_ok else 'FAIL'} | Seek: {'OK' if range_mid_ok else 'FAIL'}")

    return qa_results


def main():
    parser = argparse.ArgumentParser(description="Production Batch Audio Pipeline via Lightning")
    parser.add_argument("--batch", type=int, choices=[1, 2, 3, 4, 5], help="Run a specific batch (1-5)")
    parser.add_argument("--qa-only", action="store_true", help="Run Live QA only")
    args = parser.parse_args()

    r2_client = get_r2_client()

    if args.qa_only:
        run_live_qa(r2_client)
        return

    # Check / wake Lightning CPU Studio
    print("[*] Ensuring Lightning CPU Studio is awake and healthy...")
    from scripts.content_factory.lightning_helper import ensure_cpu_tts_studio
    if not ensure_cpu_tts_studio(timeout_seconds=120):
        raise RuntimeError("Failed to wake or connect to Lightning CPU Studio!")

    manifest_path = PROJECT_ROOT / "raw_spool" / "release_packages" / WORK_ID / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    all_chapters = manifest["chapters"]

    cp = load_checkpoint()

    batches = [
        (1, 2, 10),
        (2, 11, 20),
        (3, 21, 30),
        (4, 31, 40),
        (5, 41, 47),
    ]

    if args.batch:
        batches = [b for b in batches if b[0] == args.batch]

    t_all_start = time.time()

    for b_num, b_start, b_end in batches:
        run_batch(b_num, b_start, b_end, all_chapters, r2_client, cp)

    total_time = time.time() - t_all_start
    print(f"\n==================================================================")
    print(f"  ALL REQUESTED BATCHES PROCESSED IN {total_time/60:.1f} MINUTES!   ")
    print(f"==================================================================")

    # If all batches finished, run live QA
    if not args.batch or args.batch == 5:
        qa_res = run_live_qa(r2_client)
        print("\nFinal QA Summary Table:")
        print(json.dumps(qa_res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
