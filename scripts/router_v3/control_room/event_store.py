"""Kho lưu trữ sự kiện điều phối — Router V4 Control Room.

Lưu trữ sự kiện cục bộ, nhẹ, bất biến và an toàn đồng thời:
- SQLite chế độ WAL + busy_timeout chống khoá tệp trên Windows.
- Tệp nhật ký nối đuôi (append-only JSONL) phụ trợ.
- Tự động lọc sạch bí mật (redact) trước khi lưu.
- Hỗ trợ lọc theo danh mục: ALL, WARNINGS, FAILURES, ROUTING, WORKERS.
- Tự động giới hạn số lượng bản ghi (bounded retention).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from scripts.router_v3.packet import redact as router_redact

_EXTRA_SECRET_PATTERNS = (
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bstandard_[A-Za-z0-9]{40,}"),
    re.compile(r"\brnd_[A-Za-z0-9]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{15,}"),
    re.compile(r"\bAIza[0-9A-Za-z-_]{35}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\."),
)


def safe_redact(text: str) -> str:
    """Lọc sạch toàn diện bí mật trước khi đưa vào kho lưu trữ hoặc hiển thị."""
    out = router_redact(text or "")
    for pat in _EXTRA_SECRET_PATTERNS:
        out = pat.sub("[DA-LOC]", out)
    return out


class EventKind(str, Enum):
    MISSION_STARTED = "MISSION_STARTED"
    MISSION_COMPLETED = "MISSION_COMPLETED"
    TASK_CREATED = "TASK_CREATED"
    TASK_READY = "TASK_READY"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_STARTED = "TASK_STARTED"
    TASK_PROGRESS = "TASK_PROGRESS"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_RETRY = "TASK_RETRY"
    WORKER_ONLINE = "WORKER_ONLINE"
    WORKER_OFFLINE = "WORKER_OFFLINE"
    WORKER_DEGRADED = "WORKER_DEGRADED"
    ROUTING_DECISION = "ROUTING_DECISION"
    ARTIFACT_CREATED = "ARTIFACT_CREATED"
    TEST_RESULT = "TEST_RESULT"
    ALERT = "ALERT"
    ORCHESTRATOR_STATE = "ORCHESTRATOR_STATE"


class EventLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    ALERT = "ALERT"


@dataclass
class ControlRoomEvent:
    id: int = 0
    ts: float = 0.0
    kind: str = EventKind.TASK_PROGRESS.value
    level: str = EventLevel.INFO.value
    run_id: str = ""
    task_id: str = ""
    worker_id: str = ""
    provider: str = ""
    model: str = ""
    detail: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "kind": self.kind,
            "level": self.level,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "provider": self.provider,
            "model": self.model,
            "detail": self.detail,
            "meta": self.meta,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ControlRoomEvent:
        meta_dict = {}
        if "meta_json" in row.keys() and row["meta_json"]:
            try:
                meta_dict = json.loads(row["meta_json"])
            except Exception:
                meta_dict = {}
        return cls(
            id=int(row["id"]),
            ts=float(row["ts"]),
            kind=str(row["kind"]),
            level=str(row["level"] if "level" in row.keys() else "INFO"),
            run_id=str(row["run_id"] or ""),
            task_id=str(row["task_id"] if "task_id" in row.keys() else (row["job_id"] if "job_id" in row.keys() else "")),
            worker_id=str(row["worker_id"] if "worker_id" in row.keys() else ""),
            provider=str(row["provider"] if "provider" in row.keys() else ""),
            model=str(row["model"] if "model" in row.keys() else ""),
            detail=str(row["detail"] or ""),
            meta=meta_dict,
        )


SCHEMA = """
CREATE TABLE IF NOT EXISTS control_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    kind        TEXT NOT NULL,
    level       TEXT NOT NULL DEFAULT 'INFO',
    run_id      TEXT NOT NULL DEFAULT '',
    task_id     TEXT NOT NULL DEFAULT '',
    worker_id   TEXT NOT NULL DEFAULT '',
    provider    TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    detail      TEXT NOT NULL DEFAULT '',
    meta_json   TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_ce_ts ON control_events(ts DESC);
CREATE INDEX IF NOT EXISTS ix_ce_run ON control_events(run_id, id DESC);
CREATE INDEX IF NOT EXISTS ix_ce_kind ON control_events(kind);
CREATE INDEX IF NOT EXISTS ix_ce_level ON control_events(level);
"""


class EventStore:
    """Quản lý lưu trữ sự kiện điều phối bền vững và bất đồng bộ."""

    MAX_RETENTION = 5000

    def __init__(self, db_path: Optional[Path] = None, *, root: Optional[Path] = None):
        goc = Path(root) if root else Path.cwd()
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = goc / ".router" / "control_room" / "events.db"

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.db_path.parent / "events.jsonl"
        self._local = threading.local()
        self._lock = threading.Lock()

        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def record(
        self,
        kind: Union[EventKind, str],
        *,
        level: Union[EventLevel, str] = EventLevel.INFO,
        run_id: str = "",
        task_id: str = "",
        worker_id: str = "",
        provider: str = "",
        model: str = "",
        detail: str = "",
        meta: Optional[Dict[str, Any]] = None,
        ts: Optional[float] = None,
    ) -> ControlRoomEvent:
        """Ghi nhận sự kiện mới, tự động lọc sạch thông tin nhạy cảm."""
        kind_str = kind.value if isinstance(kind, EventKind) else str(kind)
        level_str = level.value if isinstance(level, EventLevel) else str(level)
        clean_detail = safe_redact(detail or "")
        clean_meta = meta or {}
        now = ts if ts is not None else time.time()

        try:
            meta_json = json.dumps(clean_meta, ensure_ascii=False)
            meta_json = safe_redact(meta_json)
        except Exception:
            meta_json = "{}"

        conn = self._connect()
        cur = conn.execute(
            "INSERT INTO control_events (ts, kind, level, run_id, task_id, worker_id, provider, model, detail, meta_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now, kind_str, level_str, run_id, task_id, worker_id, provider, model, clean_detail[:2000], meta_json),
        )
        event_id = cur.lastrowid or 0

        ev = ControlRoomEvent(
            id=event_id,
            ts=now,
            kind=kind_str,
            level=level_str,
            run_id=run_id,
            task_id=task_id,
            worker_id=worker_id,
            provider=provider,
            model=model,
            detail=clean_detail,
            meta=clean_meta,
        )

        try:
            with self._lock:
                with open(self.jsonl_path, "a", encoding="utf-8") as fp:
                    fp.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass

        if event_id % 500 == 0:
            self._prune()

        return ev

    def _prune(self) -> None:
        try:
            conn = self._connect()
            conn.execute(
                f"DELETE FROM control_events WHERE id NOT IN (SELECT id FROM control_events ORDER BY id DESC LIMIT {self.MAX_RETENTION})"
            )
        except Exception:
            pass

    def get_events(
        self,
        *,
        run_id: str = "",
        category: str = "ALL",
        limit: int = 100,
    ) -> List[ControlRoomEvent]:
        """Truy vấn sự kiện có hỗ trợ phân nhóm (ALL, WARNINGS, FAILURES, ROUTING, WORKERS)."""
        conn = self._connect()
        where_clauses = []
        params: List[Any] = []

        if run_id:
            where_clauses.append("run_id = ?")
            params.append(run_id)

        cat = category.upper()
        if cat == "WARNINGS":
            where_clauses.append("(level IN ('WARNING', 'ALERT') OR kind IN ('ALERT', 'TASK_RETRY', 'WORKER_DEGRADED'))")
        elif cat == "FAILURES":
            where_clauses.append("(level = 'ERROR' OR kind IN ('TASK_FAILED', 'WORKER_OFFLINE', 'TEST_FAILURE', 'SCOPE_VIOLATION'))")
        elif cat == "ROUTING":
            where_clauses.append("kind IN ('ROUTING_DECISION', 'TASK_ASSIGNED', 'TASK_READY')")
        elif cat == "WORKERS":
            where_clauses.append("kind IN ('WORKER_ONLINE', 'WORKER_OFFLINE', 'WORKER_DEGRADED', 'TASK_ASSIGNED')")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        sql = f"SELECT * FROM control_events {where_sql} ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [ControlRoomEvent.from_row(r) for r in rows]
