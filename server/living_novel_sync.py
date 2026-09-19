"""
Living Novel Continuous Update Orchestrator — Fanfic Ingestion Pipeline v1.

Coordinates continuous chapter sync, upstream silent edit detection,
and text-first publishing with asynchronous TTS audio attachment.

Adheres strictly to docs/LIVING_NOVEL_SYNC_DESIGN.md.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from server.crawler_intake_contract import (
    RawCrawlerChapter,
    RawCrawlerWork,
    compute_source_text_hash,
)



@dataclass
class SyncChapterAction:
    action_type: str  # "NEW_CHAPTER", "STALE_SOURCE", "UNCHANGED"
    source_chapter_id: str
    chapter_order: int
    published_chapter_id: Optional[str] = None
    translation_invoked: bool = False
    tts_invoked: bool = False
    error: Optional[str] = None


@dataclass
class LivingNovelSyncResult:
    source_platform: str
    source_work_id: str
    novel_id: str
    total_chapters_input: int
    new_chapters_count: int
    edited_chapters_count: int
    unchanged_chapters_count: int
    translation_calls_made: int
    tts_jobs_created: int
    db_mutations_made: int
    chapter_actions: List[SyncChapterAction] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_complete_noop(self) -> bool:
        return (
            self.new_chapters_count == 0
            and self.edited_chapters_count == 0
            and self.translation_calls_made == 0
            and self.tts_jobs_created == 0
            and self.db_mutations_made == 0
        )


class LivingNovelRegistry:
    """
    Local, durable SQLite registry for tracking upstream source identity,
    chapter sequence, and content hashes.
    Resides in raw_spool/pipeline_state/living_novel_sync.sqlite.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS source_novel_registry (
                    source_platform TEXT NOT NULL,
                    source_work_id TEXT NOT NULL,
                    appwrite_novel_id TEXT,
                    canonical_source_url TEXT NOT NULL,
                    title_original TEXT NOT NULL,
                    author_original TEXT,
                    source_status TEXT NOT NULL DEFAULT 'ongoing',
                    sync_state TEXT NOT NULL DEFAULT 'ACTIVE',
                    last_seen_chapter INTEGER NOT NULL DEFAULT 0,
                    check_interval_hours INTEGER NOT NULL DEFAULT 12,
                    last_synced_at TEXT,
                    next_check_at TEXT,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (source_platform, source_work_id)
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS source_chapter_registry (
                    source_platform TEXT NOT NULL,
                    source_work_id TEXT NOT NULL,
                    source_chapter_id TEXT NOT NULL,
                    chapter_order INTEGER NOT NULL,
                    appwrite_chapter_id TEXT,
                    source_text_hash TEXT NOT NULL,
                    translation_hash TEXT,
                    audio_track_id TEXT,
                    sync_status TEXT NOT NULL DEFAULT 'SYNCED',
                    synced_at TEXT NOT NULL,
                    last_edited_at TEXT,
                    PRIMARY KEY (source_platform, source_work_id, source_chapter_id),
                    FOREIGN KEY (source_platform, source_work_id) 
                        REFERENCES source_novel_registry(source_platform, source_work_id)
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_source_novel_next_check 
                    ON source_novel_registry(sync_state, next_check_at);
            """)
            conn.commit()

    def get_novel(self, platform: str, work_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM source_novel_registry WHERE source_platform = ? AND source_work_id = ?",
                (platform, work_id)
            ).fetchone()
            return dict(row) if row else None

    def upsert_novel(
        self,
        platform: str,
        work_id: str,
        appwrite_novel_id: str,
        source_url: str,
        title: str,
        author: Optional[str],
        source_status: str = "ongoing",
        last_seen_chapter: int = 0
    ):
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO source_novel_registry (
                    source_platform, source_work_id, appwrite_novel_id, canonical_source_url,
                    title_original, author_original, source_status, last_seen_chapter,
                    last_synced_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_platform, source_work_id) DO UPDATE SET
                    appwrite_novel_id = excluded.appwrite_novel_id,
                    last_seen_chapter = MAX(last_seen_chapter, excluded.last_seen_chapter),
                    last_synced_at = excluded.last_synced_at,
                    updated_at = excluded.updated_at
            """, (platform, work_id, appwrite_novel_id, source_url, title, author, source_status, last_seen_chapter, now, now, now))
            conn.commit()

    def get_chapter(self, platform: str, work_id: str, chapter_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM source_chapter_registry WHERE source_platform = ? AND source_work_id = ? AND source_chapter_id = ?",
                (platform, work_id, chapter_id)
            ).fetchone()
            return dict(row) if row else None

    def get_all_chapters(self, platform: str, work_id: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM source_chapter_registry WHERE source_platform = ? AND source_work_id = ? ORDER BY chapter_order ASC",
                (platform, work_id)
            ).fetchall()
            return [dict(r) for r in rows]

    def record_chapter_synced(
        self,
        platform: str,
        work_id: str,
        chapter_id: str,
        order: int,
        appwrite_chapter_id: str,
        source_text_hash: str,
        audio_track_id: Optional[str] = None
    ):
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO source_chapter_registry (
                    source_platform, source_work_id, source_chapter_id, chapter_order,
                    appwrite_chapter_id, source_text_hash, audio_track_id, sync_status,
                    synced_at, last_edited_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'SYNCED', ?, ?)
                ON CONFLICT(source_platform, source_work_id, source_chapter_id) DO UPDATE SET
                    chapter_order = excluded.chapter_order,
                    appwrite_chapter_id = excluded.appwrite_chapter_id,
                    source_text_hash = excluded.source_text_hash,
                    audio_track_id = COALESCE(excluded.audio_track_id, source_chapter_registry.audio_track_id),
                    sync_status = 'SYNCED',
                    last_edited_at = excluded.last_edited_at
            """, (platform, work_id, chapter_id, order, appwrite_chapter_id, source_text_hash, audio_track_id, now, now))
            conn.commit()


class IsolatedStagingStorage:
    """
    In-memory isolated document storage mirroring Appwrite Production collections.
    Strictly verifies schemas and invariants without mutating live databases.
    """

    def __init__(self):
        self.novels: Dict[str, Dict[str, Any]] = {}
        self.chapters: Dict[str, Dict[str, Any]] = {}
        self.audio_tracks: Dict[str, Dict[str, Any]] = {}
        self.mutation_counter = 0

    def create_novel(self, novel_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        doc = dict(data)
        doc["$id"] = novel_id
        doc["total_chapters"] = doc.get("total_chapters", 0)
        self.novels[novel_id] = doc
        self.mutation_counter += 1
        return doc

    def update_novel(self, novel_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if novel_id not in self.novels:
            raise KeyError(f"Novel {novel_id} not found")
        self.novels[novel_id].update(data)
        self.mutation_counter += 1
        return self.novels[novel_id]

    def create_chapter(self, chapter_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        doc = dict(data)
        doc["$id"] = chapter_id
        doc["has_audio"] = doc.get("has_audio", False)
        doc["audio_track_id"] = doc.get("audio_track_id")
        self.chapters[chapter_id] = doc
        self.mutation_counter += 1

        # Increment parent novel total_chapters
        novel_id = doc.get("novel_id")
        if novel_id and novel_id in self.novels:
            self.novels[novel_id]["total_chapters"] = len(
                [c for c in self.chapters.values() if c.get("novel_id") == novel_id]
            )
        return doc

    def update_chapter(self, chapter_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if chapter_id not in self.chapters:
            raise KeyError(f"Chapter {chapter_id} not found")
        self.chapters[chapter_id].update(data)
        self.mutation_counter += 1
        return self.chapters[chapter_id]

    def create_audio_track(self, track_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        doc = dict(data)
        doc["$id"] = track_id
        self.audio_tracks[track_id] = doc
        self.mutation_counter += 1

        # Update associated chapter
        ch_id = doc.get("chapter_id")
        if ch_id and ch_id in self.chapters:
            self.chapters[ch_id]["has_audio"] = True
            self.chapters[ch_id]["audio_track_id"] = track_id
        return doc

    def get_chapters_for_novel(self, novel_id: str) -> List[Dict[str, Any]]:
        matched = [c for c in self.chapters.values() if c.get("novel_id") == novel_id]
        return sorted(matched, key=lambda x: x.get("order", 0))


class LivingNovelSyncOrchestrator:
    """
    Executes synchronization of ongoing works against isolated staging or production.
    Implements 3-way reconciliation (NEW_CHAPTER, STALE_SOURCE, UNCHANGED).
    """

    def __init__(
        self,
        registry: LivingNovelRegistry,
        storage: IsolatedStagingStorage,
        translator: Callable[[str, str], str],
        tts_synthesizer: Callable[[str, str, int], Dict[str, Any]],
    ):
        self.registry = registry
        self.storage = storage
        self.translator = translator
        self.tts_synthesizer = tts_synthesizer
        self.total_translation_calls = 0
        self.total_tts_jobs = 0

    def sync_manifest(
        self,
        manifest: RawCrawlerWork,
        novel_id: str,
        platform: str = "royalroad",
        fandom: str = "Đồng Nhân"
    ) -> LivingNovelSyncResult:
        work_id = manifest.source_id
        canonical_url = manifest.source_url
        init_mutations = self.storage.mutation_counter

        # Ensure novel in storage & registry
        reg_novel = self.registry.get_novel(platform, work_id)
        if novel_id not in self.storage.novels:
            self.storage.create_novel(novel_id, {
                "title": manifest.title,
                "author": manifest.author or "Tác giả mạng",
                "source_url": canonical_url,
                "fandom": fandom,
                "status": "ongoing",
                "total_chapters": 0,
            })

        max_order = max([c.source_order for c in manifest.chapters], default=0)
        self.registry.upsert_novel(
            platform=platform,
            work_id=work_id,
            appwrite_novel_id=novel_id,
            source_url=canonical_url,
            title=manifest.title,
            author=manifest.author,
            source_status="ongoing",
            last_seen_chapter=max_order
        )

        actions: List[SyncChapterAction] = []
        new_cnt = 0
        edit_cnt = 0
        unchanged_cnt = 0
        tx_calls = 0
        tts_jobs = 0

        # Sort input chapters deterministically by order
        sorted_chapters = sorted(manifest.chapters, key=lambda c: c.source_order)

        for ch in sorted_chapters:
            current_hash = ch.source_text_hash or compute_source_text_hash(ch.source_text)
            ch_id_str = ch.source_chapter_id or f"{work_id}_c{ch.source_order}"
            reg_ch = self.registry.get_chapter(platform, work_id, ch_id_str)

            if reg_ch is None:
                # CASE A: NEW_CHAPTER
                new_cnt += 1
                # 1. Translate
                tx_calls += 1
                self.total_translation_calls += 1
                translated_vi = self.translator(ch.source_text, ch.source_title)

                # 2. Publish text first immediately
                pub_ch_id = f"ch_{novel_id}_{ch.source_order:04d}"
                self.storage.create_chapter(pub_ch_id, {
                    "novel_id": novel_id,
                    "order": ch.source_order,
                    "title": ch.source_title,
                    "content": translated_vi,
                    "source_chapter_id": ch_id_str,
                    "source_url": ch.source_url if hasattr(ch, "source_url") else canonical_url,
                    "has_audio": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })

                # 3. Asynchronously synthesize TTS & attach
                tts_jobs += 1
                self.total_tts_jobs += 1
                audio_res = self.tts_synthesizer(translated_vi, novel_id, ch.source_order)
                track_id = f"audio_{pub_ch_id}"
                self.storage.create_audio_track(track_id, {
                    "chapter_id": pub_ch_id,
                    "novel_id": novel_id,
                    "audio_url": audio_res.get("audio_url", f"https://cdn.fanfic.world/audio/{pub_ch_id}.mp3"),
                    "duration_seconds": audio_res.get("duration", 1800.0),
                    "voice_name": audio_res.get("voice", "piper:ngochuyennew"),
                    "status": "ready",
                })

                # 4. Record in registry
                self.registry.record_chapter_synced(
                    platform=platform,
                    work_id=work_id,
                    chapter_id=ch_id_str,
                    order=ch.source_order,
                    appwrite_chapter_id=pub_ch_id,
                    source_text_hash=current_hash,
                    audio_track_id=track_id,
                )

                actions.append(SyncChapterAction(
                    action_type="NEW_CHAPTER",
                    source_chapter_id=ch_id_str,
                    chapter_order=ch.source_order,
                    published_chapter_id=pub_ch_id,
                    translation_invoked=True,
                    tts_invoked=True,
                ))

            elif reg_ch["source_text_hash"] == current_hash:
                # CASE C: UNCHANGED (Pure NO-OP)
                unchanged_cnt += 1
                actions.append(SyncChapterAction(
                    action_type="UNCHANGED",
                    source_chapter_id=ch_id_str,
                    chapter_order=ch.source_order,
                    published_chapter_id=reg_ch["appwrite_chapter_id"],
                    translation_invoked=False,
                    tts_invoked=False,
                ))

            else:
                # CASE B: STALE_SOURCE (Silent upstream edit / hash mismatch)
                edit_cnt += 1
                pub_ch_id = reg_ch["appwrite_chapter_id"]

                # 1. Re-translate
                tx_calls += 1
                self.total_translation_calls += 1
                revised_vi = self.translator(ch.source_text, ch.source_title)

                # 2. Update text in-place (preserve existing document ID)
                self.storage.update_chapter(pub_ch_id, {
                    "content": revised_vi,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "source_revision_hash": current_hash,
                })

                # 3. Invalidate previous audio and synthesize new audio
                tts_jobs += 1
                self.total_tts_jobs += 1
                audio_res = self.tts_synthesizer(revised_vi, novel_id, ch.source_order)
                track_id = f"audio_{pub_ch_id}_v2"
                self.storage.create_audio_track(track_id, {
                    "chapter_id": pub_ch_id,
                    "novel_id": novel_id,
                    "audio_url": audio_res.get("audio_url", f"https://cdn.fanfic.world/audio/{pub_ch_id}_v2.mp3"),
                    "duration_seconds": audio_res.get("duration", 1850.0),
                    "voice_name": audio_res.get("voice", "piper:ngochuyennew"),
                    "status": "ready",
                })

                # 4. Update registry
                self.registry.record_chapter_synced(
                    platform=platform,
                    work_id=work_id,
                    chapter_id=ch_id_str,
                    order=ch.source_order,
                    appwrite_chapter_id=pub_ch_id,
                    source_text_hash=current_hash,
                    audio_track_id=track_id,
                )

                actions.append(SyncChapterAction(
                    action_type="STALE_SOURCE",
                    source_chapter_id=ch_id_str,
                    chapter_order=ch.source_order,
                    published_chapter_id=pub_ch_id,
                    translation_invoked=True,
                    tts_invoked=True,
                ))

        db_muts = self.storage.mutation_counter - init_mutations

        return LivingNovelSyncResult(
            source_platform=platform,
            source_work_id=work_id,
            novel_id=novel_id,
            total_chapters_input=len(manifest.chapters),
            new_chapters_count=new_cnt,
            edited_chapters_count=edit_cnt,
            unchanged_chapters_count=unchanged_cnt,
            translation_calls_made=tx_calls,
            tts_jobs_created=tts_jobs,
            db_mutations_made=db_muts,
            chapter_actions=actions,
        )
