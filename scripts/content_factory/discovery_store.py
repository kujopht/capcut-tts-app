"""
Discovery Persistent Store — Content Factory v2.

SQLite-backed persistent store for discovered candidates, rejection history,
watchlists, and configurable filter thresholds.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.content_factory.discovery_models import (
    CandidateState,
    DeterministicFilterConfig,
    DiscoveredCandidate,
    GeminiCandidateEvaluation,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DISCOVERY_DB = PROJECT_ROOT / "raw_spool" / "discovery_store.sqlite"


class DiscoveryStore:
    """Manages persistent candidate discovery queue and rejection state."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DISCOVERY_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS discovered_candidates (
                    source_platform TEXT NOT NULL,
                    source_work_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT,
                    description TEXT,
                    status TEXT,
                    chapter_count INTEGER,
                    estimated_word_count INTEGER,
                    last_update TEXT,
                    tags TEXT,
                    fandom TEXT,
                    rating REAL,
                    followers INTEGER,
                    views INTEGER,
                    pages INTEGER,
                    avg_chapter_words INTEGER,
                    crawlability_status TEXT,
                    cover_url TEXT,
                    state TEXT NOT NULL,
                    rejection_reasons TEXT,
                    deterministic_passed INTEGER,
                    overall_score REAL,
                    gemini_eval_json TEXT,
                    discovered_at TEXT,
                    evaluated_at TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (source_platform, source_work_id)
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS discovery_config (
                    config_key TEXT PRIMARY KEY,
                    config_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            conn.commit()

    def upsert_candidate(self, cand: DiscoveredCandidate):
        cand.calculate_estimates()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        disc_at = cand.discovered_at or now

        eval_json = None
        if cand.gemini_eval:
            eval_json = cand.gemini_eval.model_dump_json()

        tags_json = json.dumps(cand.tags, ensure_ascii=False)
        rej_json = json.dumps(cand.rejection_reasons, ensure_ascii=False)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO discovered_candidates (
                    source_platform, source_work_id, url, title, author, description,
                    status, chapter_count, estimated_word_count, last_update, tags,
                    fandom, rating, followers, views, pages, avg_chapter_words,
                    crawlability_status, cover_url, state, rejection_reasons,
                    deterministic_passed, overall_score, gemini_eval_json,
                    discovered_at, evaluated_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_platform, source_work_id) DO UPDATE SET
                    url = excluded.url,
                    title = excluded.title,
                    author = excluded.author,
                    description = excluded.description,
                    status = excluded.status,
                    chapter_count = excluded.chapter_count,
                    estimated_word_count = excluded.estimated_word_count,
                    last_update = excluded.last_update,
                    tags = excluded.tags,
                    fandom = excluded.fandom,
                    rating = excluded.rating,
                    followers = excluded.followers,
                    views = excluded.views,
                    pages = excluded.pages,
                    avg_chapter_words = excluded.avg_chapter_words,
                    crawlability_status = excluded.crawlability_status,
                    cover_url = excluded.cover_url,
                    state = excluded.state,
                    rejection_reasons = excluded.rejection_reasons,
                    deterministic_passed = excluded.deterministic_passed,
                    overall_score = excluded.overall_score,
                    gemini_eval_json = COALESCE(excluded.gemini_eval_json, discovered_candidates.gemini_eval_json),
                    evaluated_at = COALESCE(excluded.evaluated_at, discovered_candidates.evaluated_at),
                    updated_at = excluded.updated_at;
            """, (
                cand.source_platform,
                cand.source_work_id,
                cand.url,
                cand.title,
                cand.author,
                cand.description,
                cand.status,
                cand.chapter_count,
                cand.estimated_word_count,
                cand.last_update,
                tags_json,
                cand.fandom,
                cand.rating,
                cand.followers,
                cand.views,
                cand.pages,
                cand.avg_chapter_words,
                cand.crawlability_status,
                cand.cover_url,
                cand.state.value if isinstance(cand.state, CandidateState) else cand.state,
                rej_json,
                1 if cand.deterministic_passed else 0,
                cand.overall_score,
                eval_json,
                disc_at,
                cand.evaluated_at,
                now,
            ))
            conn.commit()

    def get_candidate(self, platform: str, work_id: str) -> Optional[DiscoveredCandidate]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM discovered_candidates WHERE source_platform = ? AND source_work_id = ?",
                (platform, work_id)
            ).fetchone()
            if not row:
                return None
            return self._row_to_candidate(dict(row))

    def list_candidates(
        self,
        state: Optional[CandidateState] = None,
        fandom: Optional[str] = None,
        min_score: Optional[float] = None,
        search: Optional[str] = None,
        limit: int = 100,
    ) -> List[DiscoveredCandidate]:
        query = "SELECT * FROM discovered_candidates WHERE 1=1"
        params: List[Any] = []

        if state:
            query += " AND state = ?"
            params.append(state.value if isinstance(state, CandidateState) else state)
        if fandom and fandom.lower() != "all":
            query += " AND fandom LIKE ?"
            params.append(f"%{fandom}%")
        if min_score is not None:
            query += " AND overall_score >= ?"
            params.append(min_score)
        if search:
            query += " AND (title LIKE ? OR author LIKE ? OR description LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s])

        query += " ORDER BY overall_score DESC, followers DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_candidate(dict(r)) for r in rows]

    def update_candidate_state(
        self,
        platform: str,
        work_id: str,
        state: CandidateState,
        rejection_reasons: Optional[List[str]] = None,
    ):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rej_json = json.dumps(rejection_reasons or [], ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE discovered_candidates SET
                    state = ?,
                    rejection_reasons = CASE WHEN ? != '[]' THEN ? ELSE rejection_reasons END,
                    updated_at = ?
                WHERE source_platform = ? AND source_work_id = ?
            """, (state.value, rej_json, rej_json, now, platform, work_id))
            conn.commit()

    def is_work_rejected(self, platform: str, work_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT state FROM discovered_candidates WHERE source_platform = ? AND source_work_id = ?",
                (platform, work_id)
            ).fetchone()
            return bool(row and row[0] == CandidateState.REJECTED.value)

    def is_work_known(self, platform: str, work_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM discovered_candidates WHERE source_platform = ? AND source_work_id = ?",
                (platform, work_id)
            ).fetchone()
            return bool(row)

    def load_filter_config(self) -> DeterministicFilterConfig:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT config_json FROM discovery_config WHERE config_key = 'deterministic_filters'"
            ).fetchone()
            if row:
                try:
                    return DeterministicFilterConfig.model_validate_json(row[0])
                except Exception:
                    pass
        return DeterministicFilterConfig()

    def save_filter_config(self, config: DeterministicFilterConfig):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO discovery_config (config_key, config_json, updated_at)
                VALUES ('deterministic_filters', ?, ?)
                ON CONFLICT(config_key) DO UPDATE SET
                    config_json = excluded.config_json,
                    updated_at = excluded.updated_at
            """, (config.model_dump_json(), now))
            conn.commit()

    def _row_to_candidate(self, row: Dict[str, Any]) -> DiscoveredCandidate:
        tags = []
        if row.get("tags"):
            try:
                tags = json.loads(row["tags"])
            except Exception:
                tags = []

        rejection_reasons = []
        if row.get("rejection_reasons"):
            try:
                rejection_reasons = json.loads(row["rejection_reasons"])
            except Exception:
                rejection_reasons = []

        gemini_eval = None
        if row.get("gemini_eval_json"):
            try:
                gemini_eval = GeminiCandidateEvaluation.model_validate_json(row["gemini_eval_json"])
            except Exception:
                pass

        state_str = row.get("state", CandidateState.DISCOVERED.value)
        try:
            state = CandidateState(state_str)
        except ValueError:
            state = CandidateState.DISCOVERED

        cand = DiscoveredCandidate(
            source_platform=row.get("source_platform", "royalroad"),
            source_work_id=row.get("source_work_id", ""),
            url=row.get("url", ""),
            title=row.get("title", ""),
            author=row.get("author") or "Unknown",
            description=row.get("description") or "",
            status=row.get("status") or "ongoing",
            chapter_count=row.get("chapter_count") or 0,
            estimated_word_count=row.get("estimated_word_count") or 0,
            last_update=row.get("last_update") or "",
            tags=tags,
            fandom=row.get("fandom") or "Fanfiction",
            rating=row.get("rating") or 0.0,
            followers=row.get("followers") or 0,
            views=row.get("views") or 0,
            pages=row.get("pages") or 0,
            avg_chapter_words=row.get("avg_chapter_words") or 0,
            crawlability_status=row.get("crawlability_status") or "OK",
            cover_url=row.get("cover_url") or "",
            state=state,
            rejection_reasons=rejection_reasons,
            deterministic_passed=bool(row.get("deterministic_passed", 1)),
            overall_score=row.get("overall_score") or 0.0,
            gemini_eval=gemini_eval,
            discovered_at=row.get("discovered_at") or "",
            evaluated_at=row.get("evaluated_at"),
        )
        cand.calculate_estimates()
        return cand
