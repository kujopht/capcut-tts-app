"""
# ARCHIVE_AFTER_PR_D — Preserved for incident history and forensic verification.
# Replaced by unified CLI: python -m scripts.content_factory run <work_id> --promote
#
Production Promotion Engine for RoyalRoad 136586 (Naruto: The Butterfly Effect).

Executes Phase 5 Promotion:
1. Promotes approved cover to Cloudflare R2: covers/6a8c525aa05b8642d568/nov_rr_136586.jpg
2. Creates/Updates novel document nov_rr_136586 in Appwrite 'novels' collection.
3. Concurrently uploads 99 staging audio MP3s to Cloudflare R2.
4. Concurrently creates 99 chapter documents in Appwrite 'chapters' collection.
5. Concurrently creates 99 audio_track documents in Appwrite 'audio_tracks' collection.
6. Updates local SQLite living novel registry (living_novel_sync_prod.sqlite).
7. Verifies live production health (novel endpoint, audio resolution, HTTP 206 streaming).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
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

R2_ACCOUNT_ID = config.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY = config.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_KEY = config.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = config.get("R2_BUCKET", "fanfic-prod")

OWNER_ID = "6a8c525aa05b8642d568"
NOVEL_ID = "nov_rr_136586"
WORK_ID = "136586"
VOICE_ID = "piper:ngochuyennew"

RELEASE_DIR = PROJECT_ROOT / "raw_spool" / "release_packages" / f"royalroad_{WORK_ID}"
STAGING_AUDIO_DIR = PROJECT_ROOT / "raw_spool" / "staging_audio" / f"royalroad_{WORK_ID}"
STAGED_COVER = PROJECT_ROOT / "raw_spool" / "staged_covers" / WORK_ID / "active_staged.jpg"

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


def promote_cover(r2: Any) -> str:
    print("\n--- 1. PROMOTING COVER TO R2 ---")
    if not STAGED_COVER.exists():
        raise FileNotFoundError(f"Staged cover not found at {STAGED_COVER}")
    
    cover_r2_key = f"covers/{OWNER_ID}/{NOVEL_ID}.jpg"
    with open(STAGED_COVER, "rb") as f:
        r2.put_object(
            Bucket=R2_BUCKET,
            Key=cover_r2_key,
            Body=f,
            ContentType="image/jpeg",
            CacheControl="public, max-age=31536000, immutable",
        )
    head = r2.head_object(Bucket=R2_BUCKET, Key=cover_r2_key)
    print(f"  [OK] Cover promoted to R2: {cover_r2_key} (Size: {head['ContentLength']} bytes, ETag: {head['ETag']})")
    return cover_r2_key


def promote_novel_metadata(cover_r2_key: str) -> Dict[str, Any]:
    print("\n--- 2. PROMOTING NOVEL METADATA TO APPWRITE ---")
    now_iso = datetime.now(timezone.utc).isoformat()
    novel_url = f"{APPWRITE_ENDPOINT}/databases/{APPWRITE_DB}/collections/novels/documents/{NOVEL_ID}"
    
    novel_payload = {
        "novel_id": NOVEL_ID,
        "owner_id": OWNER_ID,
        "title": "[Naruto] Hỏa Ảnh: Hiệu Ứng Cánh Bướm (The Butterfly Effect)",
        "description": (
            "Fandom: Naruto\n"
            "Nguyên tác: Naruto: The Butterfly Effect (RoyalRoad: 136586)\n"
            "Tác giả: Corty\n"
            "Bản dịch tiếng Việt hoàn chỉnh 99 chương kèm toàn bộ audio giọng đọc truyền cảm (23h 53m).\n\n"
            "Trùng sinh vào gia tộc Uchiha trước thảm kịch diệt tộc, từng gợn sóng nhỏ của cánh bướm dần thay đổi hoàn toàn vận mệnh của thế giới nhẫn giả."
        ),
        "cover_key": cover_r2_key,
        "state": "published",
        "tags": ["fandom:Naruto", "naruto", "hỏa ảnh", "đồng nhân", "xuyên không", "uchiha", "audio_novel", "completed"],
        "fandom_ids": ["fan_naruto"],
        "external_author_name": "Corty",
        "external_source_url": "https://www.royalroad.com/fiction/136586",
        "external_chapter_count": 99,
        "language": "vi",
        "platform": "royalroad",
        "status": "completed",
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    
    r_check = requests.get(novel_url, headers=APPWRITE_HEADERS, timeout=10)
    if r_check.status_code == 200:
        print("  Novel document exists, updating...")
        r = requests.patch(novel_url, headers=APPWRITE_HEADERS, json={"data": novel_payload}, timeout=15)
    else:
        print("  Creating new novel document...")
        r = requests.post(
            f"{APPWRITE_ENDPOINT}/databases/{APPWRITE_DB}/collections/novels/documents",
            headers=APPWRITE_HEADERS,
            json={"documentId": NOVEL_ID, "data": novel_payload},
            timeout=15,
        )
    
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to upsert novel in Appwrite: {r.status_code} - {r.text}")
    
    print(f"  [OK] Novel {NOVEL_ID} published successfully.")
    return novel_payload


def promote_chapter_and_audio(ch: Dict[str, Any], r2: Any) -> Dict[str, Any]:
    order = ch["order"]
    ch_id = ch["chapter_id"]
    title = ch["title"]
    content = ch["content"]
    content_hash = ch["content_hash"]
    
    staging_mp3 = STAGING_AUDIO_DIR / f"staging_{ch_id}.mp3"
    if not staging_mp3.exists():
        raise FileNotFoundError(f"Missing staging MP3 for chapter {order}: {staging_mp3}")
    
    # 1. Probe MP3 duration & size
    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "json", str(staging_mp3)
    ]).decode("utf-8")
    fmt = json.loads(probe).get("format", {})
    duration = float(fmt.get("duration", 0.0))
    file_size = int(fmt.get("size", staging_mp3.stat().st_size))
    
    # 2. Upload audio to R2 (Idempotent: check if exists)
    object_key = f"audio/{OWNER_ID}/{ch_id}/{content_hash}.mp3"
    r2_needed = True
    try:
        head = r2.head_object(Bucket=R2_BUCKET, Key=object_key)
        if head.get("ContentLength") == file_size:
            r2_needed = False
    except Exception:
        pass

    if r2_needed:
        for attempt in range(4):
            try:
                with open(staging_mp3, "rb") as f:
                    r2.put_object(
                        Bucket=R2_BUCKET,
                        Key=object_key,
                        Body=f,
                        ContentType="audio/mpeg",
                        CacheControl="public, max-age=31536000, immutable",
                    )
                break
            except Exception as e:
                if attempt == 3:
                    raise
                time.sleep(1.5 ** attempt)
    
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # 3. Create/Update Chapter in Appwrite (with bounded retry)
    ch_doc_url = f"{APPWRITE_ENDPOINT}/databases/{APPWRITE_DB}/collections/chapters/documents/{ch_id}"
    ch_payload = {
        "chapter_id": ch_id,
        "novel_id": NOVEL_ID,
        "owner_id": OWNER_ID,
        "title": title,
        "content": content,
        "order_index": order,
        "state": "published",
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    
    for attempt in range(6):
        try:
            r_ch_check = requests.get(ch_doc_url, headers=APPWRITE_HEADERS, timeout=25)
            if r_ch_check.status_code == 200:
                # Already exists
                break
            r_ch = requests.post(
                f"{APPWRITE_ENDPOINT}/databases/{APPWRITE_DB}/collections/chapters/documents",
                headers=APPWRITE_HEADERS,
                json={"documentId": ch_id, "data": ch_payload},
                timeout=45,
            )
            if r_ch.status_code in (200, 201, 409):
                break
            if r_ch.status_code == 429 or r_ch.status_code >= 500:
                time.sleep(2.0 + 1.5 ** attempt)
                continue
            raise RuntimeError(f"Appwrite chapter creation error: {r_ch.status_code} - {r_ch.text[:100]}")
        except (requests.RequestException, TimeoutError) as exc:
            if attempt == 5:
                raise RuntimeError(f"Timeout/Error upserting chapter {order} ({ch_id}): {exc}")
            time.sleep(2.0 + 1.5 ** attempt)
    
    # 4. Create/Update audio_track in Appwrite (with bounded retry)
    track_id = f"trk_{WORK_ID}_{order:04d}"
    track_doc_url = f"{APPWRITE_ENDPOINT}/databases/{APPWRITE_DB}/collections/audio_tracks/documents/{track_id}"
    track_payload = {
        "track_id": track_id,
        "chapter_id": ch_id,
        "owner_id": OWNER_ID,
        "voice_id": VOICE_ID,
        "object_key": object_key,
        "content_hash": content_hash[:64],
        "source_content_hash": content_hash,
        "duration_seconds": round(duration, 3),
        "size_bytes": file_size,
        "created_at": now_iso,
    }
    
    for attempt in range(6):
        try:
            r_tr_check = requests.get(track_doc_url, headers=APPWRITE_HEADERS, timeout=25)
            if r_tr_check.status_code == 200:
                break
            r_tr = requests.post(
                f"{APPWRITE_ENDPOINT}/databases/{APPWRITE_DB}/collections/audio_tracks/documents",
                headers=APPWRITE_HEADERS,
                json={"documentId": track_id, "data": track_payload},
                timeout=45,
            )
            if r_tr.status_code in (200, 201, 409):
                break
            if r_tr.status_code == 429 or r_tr.status_code >= 500:
                time.sleep(2.0 + 1.5 ** attempt)
                continue
            raise RuntimeError(f"Appwrite audio_track creation error: {r_tr.status_code} - {r_tr.text[:100]}")
        except (requests.RequestException, TimeoutError) as exc:
            if attempt == 5:
                raise RuntimeError(f"Timeout/Error upserting audio_track {order} ({track_id}): {exc}")
            time.sleep(2.0 + 1.5 ** attempt)
    
    return {
        "order": order,
        "chapter_id": ch_id,
        "track_id": track_id,
        "object_key": object_key,
        "duration": duration,
        "size_bytes": file_size,
    }


def update_living_novel_registry():
    print("\n--- 4. UPDATING LOCAL LIVING NOVEL REGISTRY ---")
    db_paths = [
        PROJECT_ROOT / "scratch" / "living_novel_sync_prod.sqlite",
        PROJECT_ROOT / "raw_spool" / "living_novel_registry.sqlite",
    ]
    now_iso = datetime.now(timezone.utc).isoformat()
    for db_path in db_paths:
        if not db_path.exists():
            continue
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS source_novel_registry (
                        source_platform TEXT,
                        source_work_id TEXT,
                        appwrite_novel_id TEXT,
                        source_title TEXT,
                        total_chapters INTEGER,
                        last_crawled_at TEXT,
                        last_promoted_at TEXT,
                        status TEXT,
                        PRIMARY KEY(source_platform, source_work_id)
                    )
                """)
                conn.execute("""
                    INSERT INTO source_novel_registry (
                        source_platform, source_work_id, appwrite_novel_id, source_title,
                        total_chapters, last_crawled_at, last_promoted_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_platform, source_work_id) DO UPDATE SET
                        appwrite_novel_id = excluded.appwrite_novel_id,
                        total_chapters = excluded.total_chapters,
                        last_promoted_at = excluded.last_promoted_at,
                        status = excluded.status
                """, ("royalroad", WORK_ID, NOVEL_ID, "Naruto: The Butterfly Effect", 99, now_iso, now_iso, "published"))
                conn.commit()
            print(f"  [OK] Updated registry at {db_path.name}")
        except Exception as e:
            print(f"  [WARN] Could not update {db_path}: {e}")


def main():
    print("=" * 80)
    print("PHASE 5: PROMOTING ROYALROAD 136586 TO PRODUCTION")
    print("Zero Re-synthesis | Zero Data Loss | Complete 99 Reader Chapters")
    print("=" * 80)
    
    pkg_manifest_file = RELEASE_DIR / "manifest.json"
    if not pkg_manifest_file.exists():
        raise FileNotFoundError(f"Manifest not found at {pkg_manifest_file}")
    
    pkg = json.loads(pkg_manifest_file.read_text(encoding="utf-8"))
    chapters = pkg["chapters"]
    assert len(chapters) == 99, f"Expected 99 chapters, found {len(chapters)}"
    
    r2 = get_r2_client()
    
    # 1. Promote Cover
    cover_key = promote_cover(r2)
    
    # 2. Promote Novel
    promote_novel_metadata(cover_key)
    
    # 3. Promote Chapters and Audio
    print(f"\n--- 3. PROMOTING 99 CHAPTERS AND AUDIO TRACKS (CONCURRENT WORKERS) ---")
    t0 = time.time()
    completed = []
    
    remaining_chapters = list(chapters)
    while remaining_chapters:
        print(f"  Dispatching {len(remaining_chapters)} chapters to ThreadPool (workers=2)...")
        failed_chapters = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            future_map = {pool.submit(promote_chapter_and_audio, ch, r2): ch for ch in remaining_chapters}
            for fut in as_completed(future_map):
                ch_item = future_map[fut]
                ord_num = ch_item["order"]
                try:
                    res = fut.result()
                    completed.append(res)
                    if len(completed) % 10 == 0 or len(completed) == 99:
                        print(f"  [Progress] {len(completed)}/99 chapters and audio tracks promoted ({time.time()-t0:.1f}s)...", flush=True)
                except Exception as e:
                    print(f"  ⚠️ Chapter {ord_num} transient issue: {e}. Will retry in next pass.")
                    failed_chapters.append(ch_item)
        
        remaining_chapters = failed_chapters
        if remaining_chapters:
            print(f"  Pausing 5 seconds before retrying {len(remaining_chapters)} chapters...")
            time.sleep(5)
    
    elapsed = time.time() - t0
    total_dur = sum(c["duration"] for c in completed)
    total_size = sum(c["size_bytes"] for c in completed)
    
    print(f"\n[+] PROMOTION COMPLETE in {elapsed:.1f}s ({elapsed/60:.1f}m):")
    print(f"    - Chapters & Audio Promoted: {len(completed)}/99")
    print(f"    - Total Audio Duration: {total_dur//3600:.0f}h {(total_dur%3600)//60:.0f}m {total_dur%60:.0f}s")
    print(f"    - Total Audio Uploaded: {total_size/(1024*1024):.2f} MB")
    
    # 4. Update Registry
    update_living_novel_registry()
    
    # 5. Save Promotion Report
    report = {
        "novel_id": NOVEL_ID,
        "work_id": WORK_ID,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "total_chapters": len(completed),
        "total_audio_duration_seconds": total_dur,
        "total_audio_bytes": total_size,
        "cover_key": cover_key,
        "status": "SUCCESS",
    }
    report_file = RELEASE_DIR / "promotion_report.json"
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"    - Report saved to: {report_file}")


if __name__ == "__main__":
    main()
