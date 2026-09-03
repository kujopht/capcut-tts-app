"""Phong bì kết quả — Router V4, mission #14.

NGỮ CẢNH CỦA CLAUDE LEAD CŨNG LÀ TÀI NGUYÊN CÓ HẠN. Router V2 kéo nguyên
văn đầu ra worker về phiên dẫn dắt; sau vài lượt review là ngữ cảnh phình
tới hàng chục nghìn token và mọi lượt sau đều chậm và đắt hơn.

Ở đây worker trả về một **phong bì gọn**, và nhật ký thô nằm TRÊN ĐĨA sau
một `raw_log_ref`. Claude lead đọc phong bì; nó chỉ đi lấy nhật ký thô khi
thật sự cần chẩn đoán.

    UNDERSTAND / DECOMPOSE / DELEGATE / INTEGRATE / DECIDE   <- Claude lead
    think / code / test / debug / đọc từng dòng terminal      <- worker

`requires_decision` + `decision_request` là kênh CHÍNH THỨC để worker hỏi
ngược. Không có nó, một worker gặp ngã ba sẽ hoặc đoán bừa (hỏng im lặng)
hoặc nhét câu hỏi vào `summary` (Claude lead phải đọc đoán). Một trường
`bool` đọc được bằng máy làm việc đó thành một nhánh điều khiển rõ ràng.

CẮT NGẮN LÀ MỘT TÍNH NĂNG, không phải mất mát: `from_worker_output` cắt mọi
trường theo trần cứng và ghi lại số byte đã bỏ, để không một worker nào —
dù vô ý hay do lỗi — làm phình ngữ cảnh của bộ điều phối.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.router_v3.packet import redact, scan_for_secrets

#: Tran CUNG cho tung truong. Con so co y nho: phong bi la BAN TOM TAT.
MAX_SUMMARY = 800
MAX_ITEM = 240
MAX_LIST = 40
MAX_DECISION = 800


@dataclass
class Tests:
    passed: int = 0
    failed: int = 0
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> Dict:
        return {"passed": self.passed, "failed": self.failed,
                "detail": self.detail[:MAX_ITEM]}


@dataclass
class ResourceUsage:
    """Thứ ĐO ĐƯỢC, không phải thứ đoán. Trường nào không quan sát được thì
    để `None` — số 0 sẽ bị đọc nhầm thành "đã đo và bằng không"."""

    wall_seconds: float = 0.0
    tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    retries: int = 0

    def to_dict(self) -> Dict:
        return {"wall_seconds": round(self.wall_seconds, 2),
                "tokens": self.tokens, "cost_usd": self.cost_usd,
                "retries": self.retries}


def _cat(x: Any, n: int) -> str:
    return redact(str(x or ""))[:n]


def _cat_list(xs: Any, n: int = MAX_ITEM) -> List[str]:
    if not isinstance(xs, (list, tuple)):
        return []
    return [_cat(x, n) for x in list(xs)[:MAX_LIST]]


@dataclass
class ResultEnvelope:
    """Thứ Claude lead THỰC SỰ tiêu thụ."""

    task_id: str
    status: str = "failed"          # ok | failed | blocked | timeout | cancelled
    summary: str = ""

    changes: List[str] = field(default_factory=list)
    tests: Tests = field(default_factory=Tests)

    artifacts: List[str] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    followups: List[str] = field(default_factory=list)
    #: Ghi chu KHONG chan viec gop. Tach khoi `risks` (thu can nguoi tich
    #: hop can nhac) va `findings` (phat hien ve MA NGUON): mot canh bao
    #: nhu "worker khong tra ve van ban nhung bang chung tren dia deu dat"
    #: la thong tin ve LUOT CHAY, khong phai ve ma nguon. Truong nay cung
    #: co trong `TaskResult` cua V3 — giu cung hinh dang de hai tang khong
    #: lech nhau.
    warnings: List[str] = field(default_factory=list)

    requires_decision: bool = False
    decision_request: str = ""

    raw_log_ref: str = ""
    worker: str = ""                # runtime_id
    model: str = ""
    provider: str = ""
    duration: float = 0.0
    resource_usage: ResourceUsage = field(default_factory=ResourceUsage)

    #: Ngoai hop dong toi thieu nhung ben tich hop can:
    branch: str = ""
    commit: str = ""
    failure_reason: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    #: So byte da bo khi cat ngan — de biet phong bi co che mat gi khong.
    truncated_bytes: int = 0

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id, "status": self.status,
            "summary": self.summary,
            "changes": list(self.changes), "tests": self.tests.to_dict(),
            "artifacts": list(self.artifacts), "findings": list(self.findings),
            "risks": list(self.risks), "followups": list(self.followups),
            "warnings": list(self.warnings),
            "requires_decision": self.requires_decision,
            "decision_request": self.decision_request,
            "raw_log_ref": self.raw_log_ref, "worker": self.worker,
            "model": self.model, "provider": self.provider,
            "duration": round(self.duration, 2),
            "resource_usage": self.resource_usage.to_dict(),
            "branch": self.branch, "commit": self.commit,
            "failure_reason": self.failure_reason,
            "timing": {"started_at": self.started_at, "ended_at": self.ended_at,
                       "duration_seconds": round(self.duration, 2)},
            "truncated_bytes": self.truncated_bytes,
        }

    @staticmethod
    def from_dict(d: Dict) -> "ResultEnvelope":
        t = d.get("tests") or {}
        ru = d.get("resource_usage") or {}
        return ResultEnvelope(
            task_id=str(d.get("task_id") or ""), status=str(d.get("status") or "failed"),
            summary=str(d.get("summary") or ""),
            changes=list(d.get("changes") or []),
            tests=Tests(passed=int(t.get("passed") or 0),
                        failed=int(t.get("failed") or 0),
                        detail=str(t.get("detail") or "")),
            artifacts=list(d.get("artifacts") or []),
            findings=list(d.get("findings") or []),
            risks=list(d.get("risks") or []),
            followups=list(d.get("followups") or []),
            warnings=list(d.get("warnings") or []),
            requires_decision=bool(d.get("requires_decision")),
            decision_request=str(d.get("decision_request") or ""),
            raw_log_ref=str(d.get("raw_log_ref") or ""),
            worker=str(d.get("worker") or ""), model=str(d.get("model") or ""),
            provider=str(d.get("provider") or ""),
            duration=float(d.get("duration") or 0.0),
            resource_usage=ResourceUsage(
                wall_seconds=float(ru.get("wall_seconds") or 0.0),
                tokens=ru.get("tokens"), cost_usd=ru.get("cost_usd"),
                retries=int(ru.get("retries") or 0)),
            branch=str(d.get("branch") or ""), commit=str(d.get("commit") or ""),
            failure_reason=str(d.get("failure_reason") or ""),
            started_at=float(d.get("started_at") or 0.0),
            ended_at=float(d.get("ended_at") or 0.0),
            truncated_bytes=int(d.get("truncated_bytes") or 0))


class RawLogStore:
    """Nhật ký THÔ trên đĩa. Phong bì chỉ mang một tham chiếu tới đây.

    Ghi qua `packet.redact` TRƯỚC khi chạm đĩa: một worker đọc phải `.env`
    hay một thông báo lỗi có token sẽ đẩy thứ đó vào log, và log thì được
    đọc lại, sao chép, đính kèm báo cáo.
    """

    def __init__(self, root: Optional[Path] = None):
        goc = Path(root) if root else Path.cwd()
        self.dir = goc / ".router" / "v4" / "logs"

    def write(self, task_id: str, raw: str) -> str:
        self.dir.mkdir(parents=True, exist_ok=True)
        ref = f"{task_id}-{uuid.uuid4().hex[:8]}.log"
        (self.dir / ref).write_text(redact(raw or ""), encoding="utf-8",
                                    errors="replace")
        return ref

    def read(self, ref: str) -> Optional[str]:
        # Chan di ngang thu muc: `ref` den tu phong bi, va mot phong bi co
        # the do worker anh huong. `../../..` se doc duoc tep ngoai kho.
        ten = Path(ref).name
        if not ten or ten != ref:
            return None
        p = self.dir / ten
        if not p.exists():
            return None
        return p.read_text(encoding="utf-8", errors="replace")


_KHOI_JSON = __import__("re").compile(r"\{.*\}", __import__("re").DOTALL)


def from_worker_output(task_id: str, raw: str, *, worker: str = "",
                       model: str = "", provider: str = "",
                       seconds: float = 0.0,
                       log_store: Optional[RawLogStore] = None
                       ) -> ResultEnvelope:
    """Đọc đầu ra worker thành phong bì gọn.

    KHOAN DUNG ở đầu vào (worker là mô hình ngôn ngữ: nó bọc JSON trong
    ```json, thêm lời dẫn, hoặc trả văn bản thuần), NGHIÊM NGẶT ở đầu ra —
    không đọc được JSON là `failed` kèm tham chiếu nhật ký, KHÔNG BAO GIỜ là
    `ok` với dữ liệu bịa.
    """
    pb = ResultEnvelope(task_id=task_id, worker=worker, model=model,
                        provider=provider, duration=seconds)
    pb.resource_usage.wall_seconds = seconds
    tho = raw or ""
    if log_store is not None:
        pb.raw_log_ref = log_store.write(task_id, tho)

    khoi = _KHOI_JSON.search(tho)
    if not khoi:
        pb.status = "failed"
        pb.failure_reason = "no_json_block"
        pb.summary = _cat("worker không trả về khối JSON nào: " + tho.strip(),
                          MAX_SUMMARY)
        pb.truncated_bytes = max(0, len(tho) - MAX_SUMMARY)
        return pb
    try:
        d = json.loads(khoi.group(0))
    except json.JSONDecodeError as exc:
        pb.status = "failed"
        pb.failure_reason = "bad_json"
        pb.summary = f"JSON hỏng: {type(exc).__name__}"
        return pb
    if not isinstance(d, dict):
        pb.status = "failed"
        pb.failure_reason = "json_not_object"
        pb.summary = "JSON không phải đối tượng"
        return pb

    tt = str(d.get("status") or "").lower()
    pb.status = tt if tt in ("ok", "failed", "blocked") else "failed"
    pb.summary = _cat(d.get("summary"), MAX_SUMMARY)
    # `changes` la ten V4; chap nhan `files_changed` cua V3 de mot worker
    # (hoac mot gói việc) theo hop dong cu van doc duoc.
    pb.changes = _cat_list(d.get("changes") or d.get("files_changed"))
    pb.artifacts = _cat_list(d.get("artifacts"))
    pb.findings = _cat_list(d.get("findings"))
    pb.risks = _cat_list(d.get("risks") or d.get("blockers"))
    pb.followups = _cat_list(d.get("followups"))
    pb.warnings = _cat_list(d.get("warnings"))
    pb.branch = _cat(d.get("branch"), MAX_ITEM)
    pb.commit = _cat(d.get("commit"), 64)
    pb.failure_reason = _cat(d.get("failure_reason"), 120)
    pb.requires_decision = bool(d.get("requires_decision"))
    pb.decision_request = _cat(d.get("decision_request"), MAX_DECISION)

    t = d.get("tests")
    if isinstance(t, dict):
        pb.tests = Tests(passed=int(t.get("passed") or 0),
                         failed=int(t.get("failed") or 0),
                         detail=_cat(t.get("detail"), MAX_ITEM))
    elif t:
        pb.tests = Tests(detail=_cat(t, MAX_ITEM))

    # Mot worker bao "ok" nhung liet ke rui ro CHAN thi la mau thuan — o
    # V4 `risks` khong tu dong chan (khac `blockers` cua V3), nhung mot
    # yeu cau QUYET DINH thi co: viec chua xong khi con cho tra loi.
    if pb.status == "ok" and pb.requires_decision:
        pb.status = "blocked"
        pb.failure_reason = pb.failure_reason or "requires_decision"
    if pb.status != "ok" and not pb.failure_reason:
        pb.failure_reason = "worker_reported_" + pb.status

    pb.truncated_bytes = max(0, len(tho) - len(json.dumps(pb.to_dict())))
    return pb
