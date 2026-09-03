"""Sổ việc BỀN — Bể worker tự trị, Phase 2.

VÌ SAO SQLITE CHỨ KHÔNG PHẢI TỆP JSON: bể này có **nhiều tiến trình** cùng
ghi — một daemon nền chạy việc, một hoặc nhiều lệnh CLI do Claude gọi đọc/
huỷ/thử lại. Với tệp JSON, "đọc–sửa–ghi" của hai tiến trình sẽ nuốt mất thay
đổi của nhau, và trên Windows còn thêm lỗi chia sẻ tệp. SQLite ở chế độ WAL
cho ghi nguyên tử, nhiều bên đọc song song, và độ bền sau khi mất điện —
đúng ba thứ cần, không phải thêm phụ thuộc nào (`sqlite3` là thư viện chuẩn).

BỀN QUA PHIÊN CLAUDE (mission #12): sổ nằm ở `.router/pool/pool.db` trong
kho. Phiên Claude đóng lại không mất gì; daemon chạy tiếp, và phiên sau đọc
lại đúng trạng thái đó.

NHẬN VIỆC NGUYÊN TỬ: `claim()` dùng `UPDATE ... WHERE status='queued'` rồi
đọc `rowcount`. Đây là điểm dễ sai nhất của một hàng đợi: `SELECT` rồi
`UPDATE` thành hai câu lệnh sẽ để hai worker cùng nhận một việc. Một câu
`UPDATE` có điều kiện là nguyên tử — worker nào thấy `rowcount == 1` mới
thật sự sở hữu việc đó.

KHÔNG LƯU BÍ MẬT: sổ chứa mục tiêu việc, phạm vi, kết quả. Không token,
không credential. Mọi văn bản do worker trả về đã qua `packet.redact()`
trước khi tới đây.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

#: Trang thai mot viec. `queued` -> `running` -> ket qua cuoi.
TRANG_THAI_CUOI = ("ok", "failed", "blocked", "timeout", "cancelled", "skipped")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    status      TEXT NOT NULL,
    base_sha    TEXT NOT NULL DEFAULT '',
    mode        TEXT NOT NULL DEFAULT 'normal',
    note        TEXT NOT NULL DEFAULT '',
    dag_json    TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS jobs (
    job_id        TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL,
    node_id       TEXT NOT NULL,
    status        TEXT NOT NULL,
    worker_id     TEXT NOT NULL DEFAULT '',
    attempt       INTEGER NOT NULL DEFAULT 0,
    max_attempts  INTEGER NOT NULL DEFAULT 2,
    tried_json    TEXT NOT NULL DEFAULT '[]',
    created_at    REAL NOT NULL,
    started_at    REAL NOT NULL DEFAULT 0,
    ended_at      REAL NOT NULL DEFAULT 0,
    cancel_req    INTEGER NOT NULL DEFAULT 0,
    node_json     TEXT NOT NULL DEFAULT '{}',
    result_json   TEXT NOT NULL DEFAULT '',
    validation_json TEXT NOT NULL DEFAULT '',
    UNIQUE (run_id, node_id)
);
CREATE TABLE IF NOT EXISTS workers (
    worker_id    TEXT PRIMARY KEY,
    provider     TEXT NOT NULL DEFAULT '',
    model        TEXT NOT NULL DEFAULT '',
    capabilities TEXT NOT NULL DEFAULT '[]',
    workspace    TEXT NOT NULL DEFAULT '',
    auth_realm   TEXT NOT NULL DEFAULT '',
    state        TEXT NOT NULL DEFAULT 'OFFLINE',
    active_job   TEXT NOT NULL DEFAULT '',
    last_seen    REAL NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    cooldown_until REAL NOT NULL DEFAULT 0,
    quota_signal TEXT NOT NULL DEFAULT '',
    account_slot INTEGER NOT NULL DEFAULT 1,
    lane_of      TEXT NOT NULL DEFAULT '',
    detail       TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL NOT NULL,
    run_id  TEXT NOT NULL DEFAULT '',
    job_id  TEXT NOT NULL DEFAULT '',
    kind    TEXT NOT NULL,
    detail  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_jobs_run ON jobs(run_id, status);
CREATE INDEX IF NOT EXISTS ix_events_run ON events(run_id, id);
"""


def duong_so(root: Optional[Path] = None) -> Path:
    goc = Path(root) if root else Path.cwd()
    return goc / ".router" / "pool" / "pool.db"


@dataclass
class Job:
    job_id: str
    run_id: str
    node_id: str
    status: str
    worker_id: str = ""
    attempt: int = 0
    max_attempts: int = 2
    tried: List[str] = field(default_factory=list)
    created_at: float = 0.0
    started_at: float = 0.0
    ended_at: float = 0.0
    cancel_requested: bool = False
    node: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    validation: Optional[Dict[str, Any]] = None

    @property
    def finished(self) -> bool:
        return self.status in TRANG_THAI_CUOI

    @property
    def duration_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        ket = self.ended_at or time.time()
        return round(max(0.0, ket - self.started_at), 2)


def _job_tu_hang(h: sqlite3.Row) -> Job:
    return Job(
        job_id=h["job_id"], run_id=h["run_id"], node_id=h["node_id"],
        status=h["status"], worker_id=h["worker_id"], attempt=h["attempt"],
        max_attempts=h["max_attempts"], tried=json.loads(h["tried_json"] or "[]"),
        created_at=h["created_at"], started_at=h["started_at"],
        ended_at=h["ended_at"], cancel_requested=bool(h["cancel_req"]),
        node=json.loads(h["node_json"] or "{}"),
        result=json.loads(h["result_json"]) if h["result_json"] else None,
        validation=(json.loads(h["validation_json"])
                    if h["validation_json"] else None))


class PoolStore:
    """Sổ việc. An toàn khi nhiều tiến trình cùng dùng."""

    def __init__(self, path: Optional[Path] = None, *,
                 root: Optional[Path] = None):
        self.path = Path(path) if path else duong_so(root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self._ket_noi() as c:
            c.executescript(SCHEMA)

    def _ket_noi(self) -> sqlite3.Connection:
        """Một kết nối MỖI LUỒNG.

        `sqlite3.Connection` không an toàn khi chia sẻ giữa các luồng (mặc
        định của thư viện chuẩn cấm hẳn). Daemon chạy nhiều luồng worker nên
        dùng chung một kết nối sẽ ném `ProgrammingError` giữa chừng — bắt ở
        đây rẻ hơn nhiều so với chẩn đoán lúc chạy.
        """
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(str(self.path), timeout=30.0,
                                isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            # `NORMAL` thay vi `FULL`: WAL + NORMAL van ben qua su co tien
            # trinh (thu thuc su xay ra o day), chi mat cac giao dich cuoi
            # khi mat dien dot ngot. Doi lay do tre ghi thap hon nhieu lan.
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA busy_timeout=30000")
            self._local.conn = c
        return c

    def close(self) -> None:
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None

    # -- su kien ------------------------------------------------------------

    def ghi_su_kien(self, kind: str, *, run_id: str = "", job_id: str = "",
                    detail: str = "") -> None:
        self._ket_noi().execute(
            "INSERT INTO events (ts, run_id, job_id, kind, detail) "
            "VALUES (?,?,?,?,?)",
            (time.time(), run_id, job_id, kind, detail[:1000]))

    def su_kien(self, run_id: str = "", *, limit: int = 100) -> List[Dict]:
        c = self._ket_noi()
        if run_id:
            hs = c.execute("SELECT * FROM events WHERE run_id=? "
                           "ORDER BY id DESC LIMIT ?", (run_id, limit))
        else:
            hs = c.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?",
                           (limit,))
        return [dict(h) for h in hs]

    # -- lan chay -----------------------------------------------------------

    def tao_run(self, *, base_sha: str, mode: str = "normal", note: str = "",
                dag: Optional[Dict] = None, run_id: str = "") -> str:
        rid = run_id or f"run-{uuid.uuid4().hex[:10]}"
        now = time.time()
        self._ket_noi().execute(
            "INSERT INTO runs (run_id, created_at, updated_at, status, "
            "base_sha, mode, note, dag_json) VALUES (?,?,?,?,?,?,?,?)",
            (rid, now, now, "running", base_sha, mode, note[:500],
             json.dumps(dag or {}, ensure_ascii=False)))
        self.ghi_su_kien("run_created", run_id=rid, detail=note[:200])
        return rid

    def dat_trang_thai_run(self, run_id: str, status: str) -> None:
        self._ket_noi().execute(
            "UPDATE runs SET status=?, updated_at=? WHERE run_id=?",
            (status, time.time(), run_id))

    def run(self, run_id: str) -> Optional[Dict]:
        h = self._ket_noi().execute("SELECT * FROM runs WHERE run_id=?",
                                    (run_id,)).fetchone()
        return dict(h) if h else None

    def runs(self, *, limit: int = 20) -> List[Dict]:
        return [dict(h) for h in self._ket_noi().execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,))]

    def run_gan_nhat(self) -> Optional[str]:
        h = self._ket_noi().execute(
            "SELECT run_id FROM runs ORDER BY created_at DESC LIMIT 1").fetchone()
        return h["run_id"] if h else None

    # -- viec ---------------------------------------------------------------

    def them_job(self, *, run_id: str, node_id: str, node: Dict,
                 max_attempts: int = 2, job_id: str = "") -> str:
        jid = job_id or f"job-{node_id}-{uuid.uuid4().hex[:6]}"
        self._ket_noi().execute(
            "INSERT INTO jobs (job_id, run_id, node_id, status, max_attempts, "
            "created_at, node_json) VALUES (?,?,?,?,?,?,?)",
            (jid, run_id, node_id, "queued", max_attempts, time.time(),
             json.dumps(node, ensure_ascii=False)))
        self.ghi_su_kien("job_queued", run_id=run_id, job_id=jid, detail=node_id)
        return jid

    def job(self, job_id: str) -> Optional[Job]:
        h = self._ket_noi().execute("SELECT * FROM jobs WHERE job_id=?",
                                    (job_id,)).fetchone()
        return _job_tu_hang(h) if h else None

    def job_theo_node(self, run_id: str, node_id: str) -> Optional[Job]:
        h = self._ket_noi().execute(
            "SELECT * FROM jobs WHERE run_id=? AND node_id=?",
            (run_id, node_id)).fetchone()
        return _job_tu_hang(h) if h else None

    def jobs(self, run_id: str = "", *, status: str = "") -> List[Job]:
        c = self._ket_noi()
        dieu_kien, tham_so = [], []
        if run_id:
            dieu_kien.append("run_id=?")
            tham_so.append(run_id)
        if status:
            dieu_kien.append("status=?")
            tham_so.append(status)
        sql = "SELECT * FROM jobs"
        if dieu_kien:
            sql += " WHERE " + " AND ".join(dieu_kien)
        sql += " ORDER BY created_at"
        return [_job_tu_hang(h) for h in c.execute(sql, tham_so)]

    def claim(self, job_id: str, worker_id: str) -> bool:
        """Nhận việc — NGUYÊN TỬ. `True` nghĩa là luồng/tiến trình gọi hàm
        này sở hữu việc đó; `False` nghĩa là ai đó đã nhận trước.

        Điều kiện `status='queued'` nằm TRONG câu `UPDATE`, không phải ở một
        câu `SELECT` trước đó — đó là toàn bộ lý do hàm này an toàn.
        """
        now = time.time()
        cur = self._ket_noi().execute(
            "UPDATE jobs SET status='running', worker_id=?, started_at=?, "
            "attempt=attempt+1, "
            "tried_json=json_insert(tried_json, '$[#]', ?) "
            "WHERE job_id=? AND status='queued'",
            (worker_id, now, worker_id, job_id))
        if cur.rowcount == 1:
            self.ghi_su_kien("job_claimed", job_id=job_id, detail=worker_id)
            return True
        return False

    def hoan_thanh(self, job_id: str, *, status: str,
                   result: Optional[Dict] = None,
                   validation: Optional[Dict] = None) -> None:
        self._ket_noi().execute(
            "UPDATE jobs SET status=?, ended_at=?, result_json=?, "
            "validation_json=? WHERE job_id=?",
            (status, time.time(),
             json.dumps(result, ensure_ascii=False) if result else "",
             json.dumps(validation, ensure_ascii=False) if validation else "",
             job_id))
        self.ghi_su_kien("job_" + status, job_id=job_id,
                         detail=(result or {}).get("summary", "")[:200])

    def tra_ve_hang_doi(self, job_id: str, *, ly_do: str,
                        loai_worker: str = "") -> bool:
        """Đưa việc về `queued` để chạy lại (thử lại / đổi worker).

        Trả `False` nếu đã hết lượt thử — bên gọi PHẢI xử lý, vì trả `True`
        vô điều kiện chính là cách tạo ra vòng lặp vô hạn mà mission cấm.
        `loai_worker` được ghi vào `tried_json` bởi `claim()` ở lượt trước,
        nên bộ chọn worker sau này biết mà tránh.
        """
        j = self.job(job_id)
        if j is None:
            return False
        if j.attempt >= j.max_attempts:
            return False
        self._ket_noi().execute(
            "UPDATE jobs SET status='queued', worker_id='', started_at=0 "
            "WHERE job_id=?", (job_id,))
        self.ghi_su_kien("job_requeued", run_id=j.run_id, job_id=job_id,
                         detail=f"{ly_do} (lượt {j.attempt}/{j.max_attempts})")
        return True

    def dat_max_attempts(self, job_id: str, n: int) -> None:
        """Nới trần số lượt thử — dùng cho `retry` do người/Claude chủ động
        yêu cầu SAU KHI việc đã cạn lượt tự động. Tách khỏi đường tự động có
        chủ đích: tự động không bao giờ được tự nới trần của chính nó."""
        self._ket_noi().execute(
            "UPDATE jobs SET max_attempts=? WHERE job_id=?", (max(1, n), job_id))

    def yeu_cau_huy(self, job_id: str) -> None:
        self._ket_noi().execute(
            "UPDATE jobs SET cancel_req=1 WHERE job_id=?", (job_id,))
        self.ghi_su_kien("cancel_requested", job_id=job_id)

    def huy_neu_dang_cho(self, job_id: str) -> bool:
        """Huỷ NGAY nếu việc còn trong hàng đợi. Việc ĐANG chạy không huỷ
        được ở đây — nó chỉ được đánh dấu, và người chạy nó tự dừng."""
        cur = self._ket_noi().execute(
            "UPDATE jobs SET status='cancelled', ended_at=?, cancel_req=1 "
            "WHERE job_id=? AND status='queued'", (time.time(), job_id))
        return cur.rowcount == 1

    # -- worker -------------------------------------------------------------

    def ghi_worker(self, hang: Dict[str, Any]) -> None:
        """Ghi/cập nhật một dòng worker cho bảng quan sát."""
        self._ket_noi().execute(
            "INSERT INTO workers (worker_id, provider, model, capabilities, "
            "workspace, auth_realm, state, active_job, last_seen, "
            "failure_count, cooldown_until, quota_signal, account_slot, "
            "lane_of, detail) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(worker_id) DO UPDATE SET "
            "provider=excluded.provider, model=excluded.model, "
            "capabilities=excluded.capabilities, workspace=excluded.workspace, "
            "auth_realm=excluded.auth_realm, state=excluded.state, "
            "active_job=excluded.active_job, last_seen=excluded.last_seen, "
            "failure_count=excluded.failure_count, "
            "cooldown_until=excluded.cooldown_until, "
            "quota_signal=excluded.quota_signal, "
            "account_slot=excluded.account_slot, lane_of=excluded.lane_of, "
            "detail=excluded.detail",
            (hang["worker_id"], hang.get("provider", ""), hang.get("model", ""),
             json.dumps(sorted(hang.get("capabilities") or [])),
             hang.get("workspace", ""), hang.get("auth_realm", ""),
             hang.get("state", "OFFLINE"), hang.get("active_job") or "",
             float(hang.get("last_seen") or 0.0),
             int(hang.get("failure_count") or 0),
             float(hang.get("cooldown_until") or 0.0),
             hang.get("quota_signal", ""),
             1 if hang.get("account_slot", True) else 0,
             hang.get("lane_of", ""), (hang.get("detail") or "")[:300]))

    def workers(self) -> List[Dict]:
        return [dict(h) for h in self._ket_noi().execute(
            "SELECT * FROM workers ORDER BY worker_id")]
