"""
Fanfic Ingestion Pipeline v1 — State Machine & Local Checkpoint Store.

Manages explicit per-work and per-chapter state transitions.
Persists pipeline progression locally (SQLite / JSON spool) with ZERO
schema alterations to production Appwrite.

State Invariants:
1. Text is canonical: PUBLISHED means text is live and readable in Fanfic World.
2. Async TTS: TTS errors do NOT demote or unpublish text chapters.
3. Resumability: Restarting reuses existing translated text and existing audio.
4. Deduplication: Content hash matching prevents duplicate LLM or TTS calls.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkState(str, Enum):
    CRAWLED = "CRAWLED"
    NORMALIZED = "NORMALIZED"
    TRANSLATING = "TRANSLATING"
    TEXT_READY = "TEXT_READY"
    PUBLISHED = "PUBLISHED"
    TTS_PENDING = "TTS_PENDING"
    TTS_RUNNING = "TTS_RUNNING"
    AUDIO_PARTIAL = "AUDIO_PARTIAL"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class ChapterState(str, Enum):
    CRAWLED = "CRAWLED"
    NORMALIZED = "NORMALIZED"
    TRANSLATING = "TRANSLATING"
    TEXT_READY = "TEXT_READY"
    PUBLISHED = "PUBLISHED"
    TTS_PENDING = "TTS_PENDING"
    TTS_RUNNING = "TTS_RUNNING"
    AUDIO_READY = "AUDIO_READY"
    TTS_FAILED = "TTS_FAILED"
    FAILED = "FAILED"


class AudioLifecycleState(str, Enum):
    NONE = "none"
    PENDING = "pending"
    PROCESSING = "processing"
    PARTIAL = "partial"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class ChapterCheckpoint:
    source_order: int
    source_title: str
    source_text_hash: str
    source_text: str
    state: ChapterState = ChapterState.CRAWLED
    source_chapter_id: Optional[str] = None
    translated_title: Optional[str] = None
    translated_text: Optional[str] = None
    translated_text_hash: Optional[str] = None
    published_chapter_id: Optional[str] = None
    audio_state: AudioLifecycleState = AudioLifecycleState.NONE
    audio_track_id: Optional[str] = None
    audio_object_key: Optional[str] = None
    audio_duration: float = 0.0
    audio_size: int = 0
    audio_voice_id: Optional[str] = None
    error_message: Optional[str] = None
    translation_attempts: int = 0
    tts_attempts: int = 0
    last_translation_account: Optional[str] = None
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value if isinstance(self.state, ChapterState) else self.state
        d["audio_state"] = (
            self.audio_state.value
            if isinstance(self.audio_state, AudioLifecycleState)
            else self.audio_state
        )
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ChapterCheckpoint:
        d = dict(data)
        if "state" in d and isinstance(d["state"], str):
            d["state"] = ChapterState(d["state"])
        if "audio_state" in d and isinstance(d["audio_state"], str):
            d["audio_state"] = AudioLifecycleState(d["audio_state"])
        return cls(**d)


@dataclass
class WorkCheckpoint:
    work_id: str
    source_id: str
    source_url: str
    title_original: str
    state: WorkState = WorkState.CRAWLED
    title_vi: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None
    fandom: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    cover_url: Optional[str] = None
    published_novel_id: Optional[str] = None
    total_chapters: int = 0
    chapters: Dict[int, ChapterCheckpoint] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "work_id": self.work_id,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "title_original": self.title_original,
            "title_vi": self.title_vi,
            "author": self.author,
            "description": self.description,
            "fandom": self.fandom,
            "tags": list(self.tags),
            "cover_url": self.cover_url,
            "state": self.state.value if isinstance(self.state, WorkState) else self.state,
            "published_novel_id": self.published_novel_id,
            "total_chapters": self.total_chapters,
            "chapters": {str(k): v.to_dict() for k, v in self.chapters.items()},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkCheckpoint:
        d = dict(data)
        if "state" in d and isinstance(d["state"], str):
            d["state"] = WorkState(d["state"])
        raw_chapters = d.pop("chapters", {})
        chapters = {}
        for k, v in raw_chapters.items():
            chapters[int(k)] = ChapterCheckpoint.from_dict(v)
        return cls(chapters=chapters, **d)

    def refresh_work_state(self) -> WorkState:
        """Recalculate overall work state based on chapter progression."""
        if not self.chapters:
            return self.state

        states = [ch.state for ch in self.chapters.values()]
        audio_states = [ch.audio_state for ch in self.chapters.values()]

        all_published = all(
            st in (ChapterState.PUBLISHED, ChapterState.AUDIO_READY, ChapterState.TTS_RUNNING, ChapterState.TTS_PENDING, ChapterState.TTS_FAILED)
            for st in states
        )
        all_audio_done = all(ast == AudioLifecycleState.COMPLETE for ast in audio_states)
        any_audio_done = any(ast == AudioLifecycleState.COMPLETE for ast in audio_states)
        all_text_ready = all(
            st in (ChapterState.TEXT_READY, ChapterState.PUBLISHED, ChapterState.AUDIO_READY)
            for st in states
        )

        if all_published and all_audio_done:
            self.state = WorkState.COMPLETE
        elif all_published and any_audio_done:
            self.state = WorkState.AUDIO_PARTIAL
        elif all_published:
            self.state = WorkState.PUBLISHED
        elif all_text_ready:
            self.state = WorkState.TEXT_READY
        elif any(st == ChapterState.TRANSLATING for st in states):
            self.state = WorkState.TRANSLATING
        self.updated_at = now_iso()
        return self.state


class LocalStateStore:
    """
    Thread-safe SQLite-backed local state store for ingestion pipeline checkpointing.
    Guarantees persistence across process crashes, halts, or worker reboots.
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            base_dir = Path("raw_spool") / "pipeline_state"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = base_dir / "ingestion_state.sqlite"
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS works (
                    work_id TEXT PRIMARY KEY,
                    source_id TEXT,
                    source_url TEXT UNIQUE,
                    title_original TEXT,
                    state TEXT,
                    payload_json TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chapters (
                    work_id TEXT,
                    source_order INTEGER,
                    source_text_hash TEXT,
                    state TEXT,
                    audio_state TEXT,
                    chapter_json TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (work_id, source_order)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_works_url ON works(source_url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chp_hash ON chapters(work_id, source_text_hash)")
            conn.commit()

    def save_work(self, work: WorkCheckpoint) -> None:
        work.refresh_work_state()
        work.updated_at = now_iso()
        payload = json.dumps(work.to_dict(), ensure_ascii=False)

        with self._lock, self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO works (work_id, source_id, source_url, title_original, state, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(work_id) DO UPDATE SET
                    title_original=excluded.title_original,
                    state=excluded.state,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    work.work_id,
                    work.source_id,
                    work.source_url,
                    work.title_original,
                    work.state.value,
                    payload,
                    work.created_at,
                    work.updated_at,
                )
            )
            for ch in work.chapters.values():
                ch_json = json.dumps(ch.to_dict(), ensure_ascii=False)
                conn.execute(
                    """
                    INSERT INTO chapters (work_id, source_order, source_text_hash, state, audio_state, chapter_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(work_id, source_order) DO UPDATE SET
                        source_text_hash=excluded.source_text_hash,
                        state=excluded.state,
                        audio_state=excluded.audio_state,
                        chapter_json=excluded.chapter_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        work.work_id,
                        ch.source_order,
                        ch.source_text_hash,
                        ch.state.value if isinstance(ch.state, ChapterState) else ch.state,
                        ch.audio_state.value if isinstance(ch.audio_state, AudioLifecycleState) else ch.audio_state,
                        ch_json,
                        ch.updated_at,
                    )
                )
            conn.commit()

    def load_work(self, work_id: str) -> Optional[WorkCheckpoint]:
        with self._lock, self._get_conn() as conn:
            row = conn.execute("SELECT payload_json FROM works WHERE work_id = ?", (work_id,)).fetchone()
            if not row:
                return None
            data = json.loads(row["payload_json"])
            return WorkCheckpoint.from_dict(data)

    def find_by_source_url(self, source_url: str) -> Optional[WorkCheckpoint]:
        with self._lock, self._get_conn() as conn:
            row = conn.execute("SELECT payload_json FROM works WHERE source_url = ?", (source_url.strip(),)).fetchone()
            if not row:
                return None
            data = json.loads(row["payload_json"])
            return WorkCheckpoint.from_dict(data)

    def has_translated_chapter(self, work_id: str, source_order: int, source_text_hash: str) -> bool:
        """Returns True if chapter already has a valid translation for the exact source text hash."""
        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT chapter_json FROM chapters
                WHERE work_id = ? AND source_order = ? AND source_text_hash = ?
                """,
                (work_id, source_order, source_text_hash)
            ).fetchone()
            if not row:
                return False
            data = json.loads(row["chapter_json"])
            return bool(data.get("translated_text") and data.get("state") in (
                ChapterState.TEXT_READY.value,
                ChapterState.PUBLISHED.value,
                ChapterState.AUDIO_READY.value,
                ChapterState.TTS_PENDING.value,
                ChapterState.TTS_RUNNING.value,
                ChapterState.TTS_FAILED.value,
            ))

    def has_audio_chapter(self, work_id: str, source_order: int) -> bool:
        """Returns True if chapter already has completed audio."""
        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT audio_state FROM chapters
                WHERE work_id = ? AND source_order = ?
                """,
                (work_id, source_order)
            ).fetchone()
            if not row:
                return False
            return row["audio_state"] == AudioLifecycleState.COMPLETE.value
