"""
Staging Trial Runner for One Real Living Novel:
[Naruto SI] Trọng Sinh Gia Tộc Hatake: Cú Sốc Của Kỹ Sư Vật Liệu

Verifies Chapters 1–11 baseline migration,
simulates Chapter 12 NEW_CHAPTER sync (text-first + async TTS),
verifies complete second-run NO-OP idempotency,
and verifies Chapter 12 silent rewrite hash-change reconciliation.
"""

from __future__ import annotations

import json
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from server.crawler_intake_contract import (
    RawCrawlerChapter,
    RawCrawlerWork,
)
from server.living_novel_sync import (
    IsolatedStagingStorage,
    LivingNovelRegistry,
    LivingNovelSyncOrchestrator,
    compute_source_text_hash,
)

SCRATCH_DIR = PROJECT_ROOT / "scratch"
REGISTRY_DB_PATH = SCRATCH_DIR / "staging_living_novel_sync.sqlite"
if REGISTRY_DB_PATH.exists():
    REGISTRY_DB_PATH.unlink()


def run_staging_trial() -> Dict[str, Any]:
    print("=" * 70)
    print("PHASE 2: LIVING NOVEL STAGING TRIAL")
    print("Novel: [Naruto SI] Trọng Sinh Gia Tộc Hatake: Cú Sốc Của Kỹ Sư Vật Liệu")
    print("Source: RoyalRoad (fiction/156690)")
    print("=" * 70)

    # 1. Initialize isolated components
    registry = LivingNovelRegistry(REGISTRY_DB_PATH)
    storage = IsolatedStagingStorage()

    translation_invocation_log: List[Dict[str, Any]] = []
    tts_invocation_log: List[Dict[str, Any]] = []

    def mock_translator(source_text: str, chapter_title: str) -> str:
        translation_invocation_log.append({
            "title": chapter_title,
            "char_count": len(source_text),
            "hash": compute_source_text_hash(source_text)
        })
        return f"[Dịch Tiếng Việt] {chapter_title}\n\nNội dung chương dịch thuật bởi Gemini Account Pool: {source_text}"

    def mock_tts_synthesizer(vi_text: str, novel_id: str, order: int) -> Dict[str, Any]:
        tts_invocation_log.append({
            "novel_id": novel_id,
            "order": order,
            "char_count": len(vi_text)
        })
        return {
            "audio_url": f"https://cdn.fanfic.world/audio/{novel_id}_c{order:04d}.mp3",
            "duration": 1820.5,
            "voice": "piper:ngochuyennew"
        }

    orchestrator = LivingNovelSyncOrchestrator(
        registry=registry,
        storage=storage,
        translator=mock_translator,
        tts_synthesizer=mock_tts_synthesizer,
    )

    staging_novel_id = "novel_naruto_si_hatake_staging_001"

    # ---------------------------------------------------------
    # STEP 1: Ingest Baseline Chapters 1–11 from Drive Archive
    # ---------------------------------------------------------
    print("\n--- STEP 1: Ingesting Baseline Chapters 1–11 from Archive ---")
    
    # Create novel metadata
    storage.create_novel(staging_novel_id, {
        "title": "[Naruto SI] Trọng Sinh Gia Tộc Hatake: Cú Sốc Của Kỹ Sư Vật Liệu",
        "author": "SoGarrulous",
        "fandom": "Naruto",
        "source_url": "https://www.royalroad.com/fiction/156690/naruto-si-reborn-in-the-hatake-clan",
        "status": "ongoing",
        "description": "Một kỹ sư khoa học vật liệu hiện đại tái sinh thành người của gia tộc Hatake trong thế giới Naruto.",
        "cover_url": "https://cdn.fanfic.world/covers/naruto-si-hatake.jpg",
        "total_chapters": 0,
    })

    registry.upsert_novel(
        platform="royalroad",
        work_id="156690",
        appwrite_novel_id=staging_novel_id,
        source_url="https://www.royalroad.com/fiction/156690/naruto-si-reborn-in-the-hatake-clan",
        title="Naruto SI : Reborn in the Hatake Clan",
        author="SoGarrulous",
        source_status="ongoing",
        last_seen_chapter=11
    )

    # Ingest chapters 1..11 as pre-existing assets from Drive
    baseline_chapters: List[Dict[str, Any]] = []
    for order in range(1, 12):
        ch_id = f"ch_{staging_novel_id}_{order:04d}"
        source_id = f"313777{order:02d}"
        source_raw = f"Original English text for Chapter {order} from RoyalRoad fiction 156690..."
        s_hash = compute_source_text_hash(source_raw)
        vi_content = f"Văn bản tiếng Việt hoàn chỉnh Chương {order} đã phục hồi từ kho Google Drive (không dịch lại)."

        storage.create_chapter(ch_id, {
            "novel_id": staging_novel_id,
            "order": order,
            "title": f"Chương {order}: Khởi đầu của Kỹ sư tại Konoha",
            "content": vi_content,
            "source_chapter_id": source_id,
            "source_url": f"https://www.royalroad.com/fiction/156690/chapter/{source_id}",
            "has_audio": True,
            "created_at": "2026-09-13T03:44:00Z",
        })

        track_id = f"audio_{ch_id}"
        storage.create_audio_track(track_id, {
            "chapter_id": ch_id,
            "novel_id": staging_novel_id,
            "audio_url": f"https://cdn.fanfic.world/audio/{ch_id}.mp3",
            "duration_seconds": 1839.8,
            "voice_name": "piper:ngochuyennew",
            "status": "ready"
        })

        registry.record_chapter_synced(
            platform="royalroad",
            work_id="156690",
            chapter_id=source_id,
            order=order,
            appwrite_chapter_id=ch_id,
            source_text_hash=s_hash,
            audio_track_id=track_id
        )

        baseline_chapters.append({
            "order": order,
            "ch_id": ch_id,
            "source_id": source_id,
            "source_text": source_raw,
            "source_hash": s_hash
        })

    # Verify Baseline Assertions
    assert len(storage.chapters) == 11, f"Expected 11 chapters, got {len(storage.chapters)}"
    assert len(storage.audio_tracks) == 11, f"Expected 11 audio tracks, got {len(storage.audio_tracks)}"
    assert len(translation_invocation_log) == 0, "Chapters 1-11 must NOT call translation scheduler"
    assert len(tts_invocation_log) == 0, "Chapters 1-11 must NOT call TTS synthesizer"
    assert storage.novels[staging_novel_id]["total_chapters"] == 11

    print(f"  [OK] Chapters 1-11 ingested into isolated staging. Total chapters: 11")
    print(f"  [OK] Translation invocations for 1-11: 0")
    print(f"  [OK] TTS synthesis jobs for 1-11: 0")
    print(f"  [OK] Audio mapping verified: 11/11 chapters have audio_track attached.")

    # ---------------------------------------------------------
    # STEP 2: Simulate External Crawler Manifest with Chapter 12
    # ---------------------------------------------------------
    print("\n--- STEP 2: Simulating Upstream Sync Manifest (Chapters 1..12) ---")
    
    crawler_chapters: List[RawCrawlerChapter] = []
    # Add existing chapters 1..11 (unchanged)
    for b in baseline_chapters:
        crawler_chapters.append(RawCrawlerChapter(
            source_chapter_id=b["source_id"],
            source_order=b["order"],
            source_title=f"Chương {b['order']}: Khởi đầu của Kỹ sư tại Konoha",
            source_text=b["source_text"],
        ))

    # Add brand-new Chapter 12
    ch12_source_id = "3137785"
    ch12_source_text = "The sudden ozone stench in the training grounds made Dante pause his chakra flow analysis. Chidori wasn't magic—it was high-frequency dielectric breakdown..."
    crawler_chapters.append(RawCrawlerChapter(
        source_chapter_id=ch12_source_id,
        source_order=12,
        source_title="Chương 12: Động lực học chất khí và Lôi Độn Chidori",
        source_text=ch12_source_text,
    ))

    manifest_sync_1 = RawCrawlerWork(
        source_id="156690",
        source_url="https://www.royalroad.com/fiction/156690/naruto-si-reborn-in-the-hatake-clan",
        title="Naruto SI : Reborn in the Hatake Clan",
        author="SoGarrulous",
        chapters=crawler_chapters,
    )

    result_sync_1 = orchestrator.sync_manifest(manifest_sync_1, staging_novel_id)

    print(f"  Sync 1 Result:")
    print(f"    - Total Chapters Evaluated: {result_sync_1.total_chapters_input}")
    print(f"    - New Chapters Detected: {result_sync_1.new_chapters_count}")
    print(f"    - Unchanged Chapters: {result_sync_1.unchanged_chapters_count}")
    print(f"    - Translation Calls: {result_sync_1.translation_calls_made}")
    print(f"    - TTS Jobs Created: {result_sync_1.tts_jobs_created}")
    print(f"    - Total Chapters in Staging: {storage.novels[staging_novel_id]['total_chapters']}")

    # Critical Assertions for Step 2
    assert result_sync_1.new_chapters_count == 1, "Must detect exactly 1 NEW_CHAPTER"
    assert result_sync_1.unchanged_chapters_count == 11, "Chapters 1-11 must be UNCHANGED"
    assert result_sync_1.translation_calls_made == 1, "Only chapter 12 must invoke translation"
    assert result_sync_1.tts_jobs_created == 1, "Only chapter 12 must invoke TTS"
    assert storage.novels[staging_novel_id]["total_chapters"] == 12

    # Verify Chapter 12 document
    ch12_doc = storage.chapters["ch_" + staging_novel_id + "_0012"]
    assert ch12_doc["order"] == 12
    assert ch12_doc["has_audio"] is True
    assert ch12_doc["audio_track_id"] == "audio_ch_" + staging_novel_id + "_0012"
    assert "dielectric breakdown" in ch12_doc["content"].lower() or "lôi độn" in ch12_doc["content"].lower()

    # ---------------------------------------------------------
    # STEP 3: Verify Second-Run Idempotency (Pure NO-OP)
    # ---------------------------------------------------------
    print("\n--- STEP 3: Verifying Second-Run Idempotency (Pure NO-OP) ---")
    mutations_before = storage.mutation_counter
    result_sync_2 = orchestrator.sync_manifest(manifest_sync_1, staging_novel_id)

    print(f"  Sync 2 (Idempotency Run) Result:")
    print(f"    - New Chapters: {result_sync_2.new_chapters_count}")
    print(f"    - Edited Chapters: {result_sync_2.edited_chapters_count}")
    print(f"    - Unchanged Chapters: {result_sync_2.unchanged_chapters_count}")
    print(f"    - Translation Calls: {result_sync_2.translation_calls_made}")
    print(f"    - TTS Jobs Created: {result_sync_2.tts_jobs_created}")
    print(f"    - DB Mutations: {result_sync_2.db_mutations_made}")
    print(f"    - Is Complete NO-OP: {result_sync_2.is_complete_noop}")

    assert result_sync_2.is_complete_noop, "Second run with identical manifest MUST be a 100% NO-OP"
    assert storage.mutation_counter == mutations_before, "Second run must perform ZERO storage mutations"
    assert len(translation_invocation_log) == 1, "Zero additional translation calls allowed"
    assert len(tts_invocation_log) == 1, "Zero additional TTS jobs allowed"

    # ---------------------------------------------------------
    # STEP 4: Simulate Upstream Silent Rewrite (Hash Change) on Chapter 12
    # ---------------------------------------------------------
    print("\n--- STEP 4: Simulating Upstream Silent Rewrite on Chapter 12 ---")
    
    # Author rewrites Chapter 12 upstream
    rewritten_ch12_text = "The sudden ozone stench in the training grounds made Dante pause his chakra flow analysis. REVISED SCENE: Kakashi Hatake appeared behind the tree, analyzing the molecular vibration with an inquisitive tilt of his masked head..."
    
    crawler_chapters_revised = list(crawler_chapters)
    crawler_chapters_revised[-1] = RawCrawlerChapter(
        source_chapter_id=ch12_source_id,
        source_order=12,
        source_title="Chương 12: Động lực học chất khí và Lôi Độn Chidori (Bản sửa đổi)",
        source_text=rewritten_ch12_text,
    )

    manifest_sync_3 = RawCrawlerWork(
        source_id=manifest_sync_1.source_id,
        source_url=manifest_sync_1.source_url,
        title=manifest_sync_1.title,
        author=manifest_sync_1.author,
        chapters=crawler_chapters_revised,
    )

    result_sync_3 = orchestrator.sync_manifest(manifest_sync_3, staging_novel_id)

    print(f"  Sync 3 (Silent Rewrite Run) Result:")
    print(f"    - New Chapters: {result_sync_3.new_chapters_count}")
    print(f"    - Edited Chapters: {result_sync_3.edited_chapters_count}")
    print(f"    - Unchanged Chapters: {result_sync_3.unchanged_chapters_count}")
    print(f"    - Translation Calls: {result_sync_3.translation_calls_made}")
    print(f"    - TTS Jobs Created: {result_sync_3.tts_jobs_created}")

    assert result_sync_3.new_chapters_count == 0, "No new chapters should be created"
    assert result_sync_3.edited_chapters_count == 1, "Must detect exactly 1 STALE_SOURCE edit"
    assert result_sync_3.unchanged_chapters_count == 11, "Chapters 1-11 must remain UNCHANGED"
    assert result_sync_3.translation_calls_made == 1, "Only the edited chapter must be re-translated"
    assert result_sync_3.tts_jobs_created == 1, "Only the edited chapter must regenerate TTS"

    # Verify Chapter 12 preserves its ID and updates content in-place
    ch12_after = storage.chapters["ch_" + staging_novel_id + "_0012"]
    assert "Kakashi Hatake appeared behind the tree" in ch12_after["content"]
    assert ch12_after["audio_track_id"] == "audio_ch_" + staging_novel_id + "_0012_v2"
    assert ch12_after["order"] == 12

    # Verify chapter sequence
    all_chaps = storage.get_chapters_for_novel(staging_novel_id)
    orders = [c["order"] for c in all_chaps]
    assert orders == list(range(1, 13)), f"Chapter ordering must be strictly 1..12: {orders}"

    print("\n" + "=" * 70)
    print("STAGING TRIAL COMPLETED SUCCESSFULLY (ALL ASSERTIONS VERIFIED)")
    print("=" * 70)

    return {
        "staging_novel_id": staging_novel_id,
        "title": storage.novels[staging_novel_id]["title"],
        "total_chapters": len(all_chaps),
        "chapter_orders": orders,
        "baseline_reused_text_count": 11,
        "baseline_reused_audio_count": 11,
        "new_chapter_synced": 12,
        "total_translation_calls_made": orchestrator.total_translation_calls,
        "total_tts_jobs_created": orchestrator.total_tts_jobs,
        "sync_1_new_chapters": result_sync_1.new_chapters_count,
        "sync_2_noop_confirmed": result_sync_2.is_complete_noop,
        "sync_3_edited_chapters": result_sync_3.edited_chapters_count,
        "zero_production_db_mutations": True,
    }


if __name__ == "__main__":
    report = run_staging_trial()
    print("\nSummary Data:")
    print(json.dumps(report, indent=2, ensure_ascii=False))
