"""Giao thức gói việc / kết quả — Router V3, Phase 5.

Mục đích thật của module này là **giữ ngữ cảnh của agent dẫn dắt nhỏ lại**.
Router V2 kéo nguyên văn đầu ra của worker về phiên dẫn dắt; sau vài lần review
là ngữ cảnh phình tới hàng chục nghìn token và mọi lượt sau đều chậm và đắt hơn.

Ở đây worker nhận một gói **gọn, tự chứa** và phải trả về một **đối tượng có
cấu trúc**. Agent dẫn dắt đọc bản tóm tắt đó chứ không đọc lại toàn bộ hội thoại.

Gói việc cũng là nơi ghi ranh giới: `WRITE_SCOPE` và `DO_NOT_TOUCH` là hợp đồng
với worker, và `TaskDag` đã kiểm là hai worker chạy song song không giẫm phạm vi.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from scripts.router_v3.dag import RiskClass, TaskNode

#: Mẫu trông giống credential. Gói việc bị TỪ CHỐI nếu khớp — worker ngoài
#: không bao giờ được nhận bí mật, kể cả do vô ý dán vào mục tiêu.
_MAU_BI_MAT = (
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bstandard_[A-Za-z0-9]{40,}"),      # khoa API Appwrite
    re.compile(r"\brnd_[A-Za-z0-9]{20,}"),           # khoa API Render
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\."),  # JWT
)


class PacketRefused(RuntimeError):
    """Gói việc không được phép gửi đi. Fail closed."""


def scan_for_secrets(text: str) -> Optional[str]:
    for mau in _MAU_BI_MAT:
        if mau.search(text or ""):
            return mau.pattern
    return None


#: Thay cho moi thu giong credential tren DUONG VE.
REDACTED = "[DA-LOC]"


def redact(text: str) -> str:
    """Loc thu giong credential ra khoi van ban do WORKER tra ve.

    Truoc ban sua nay, `scan_for_secrets` CHI quet goi DI. Duong VE hoan toan
    mo: mot worker doc phai `.env`, mot thong bao loi cua nha cung cap, hay
    mot dong log co token deu di thang vao `summary`/`integration_notes` roi
    vao trang thai va log cua Router. Neu ra qua review bao mat doc lap
    (Antigravity Claude Opus) — no bac bo dung khang dinh "khong credential
    nao vao duoc trang thai Router".

    Loc chu KHONG tu choi: mot ket qua co ich khong nen bi vut di ca, va
    worker khong phai lc nao cung kiem soat duoc thu no doc phai.
    """
    ra = str(text or "")
    for mau in _MAU_BI_MAT:
        ra = mau.sub(REDACTED, ra)
    return ra


@dataclass(frozen=True)
class TaskPacket:
    """Thứ worker thực sự nhận được."""

    task_id: str
    base_sha: str
    objective: str
    dependencies: Sequence[str] = ()
    read_scope: Sequence[str] = ()
    write_scope: Sequence[str] = ()
    do_not_touch: Sequence[str] = ()
    expected_output: str = ""
    tests_required: Sequence[str] = ()
    risk_class: RiskClass = RiskClass.LOW
    #: Tóm tắt kết quả các nút phụ thuộc — KHÔNG phải hội thoại của chúng.
    dependency_summaries: Dict[str, str] = field(default_factory=dict)
    #: Worktree CÔ LẬP của nút này. Rỗng với việc chỉ đọc (chúng dùng chung
    #: kho vì không sửa được gì). Worker PHẢI làm việc ở đây, không phải ở
    #: cây làm việc chính — hai worker ghi chung một cây là hỏng chắc chắn.
    workspace: str = ""
    branch: str = ""

    def render(self) -> str:
        """Chuỗi gửi cho worker. Cố ý là văn bản thuần: mọi CLI đều đọc được."""
        dong = [
            f"TASK_ID: {self.task_id}",
            f"BASE_SHA: {self.base_sha}",
            f"RISK_CLASS: {self.risk_class.value}",
            "",
            "OBJECTIVE:",
            self.objective.strip(),
        ]
        if self.dependency_summaries:
            dong += ["", "DEPENDENCY_RESULTS (tóm tắt, không phải hội thoại):"]
            for k, v in sorted(self.dependency_summaries.items()):
                dong.append(f"  - {k}: {v.strip()[:400]}")
        if self.read_scope:
            dong += ["", "READ_SCOPE:"] + [f"  {p}" for p in self.read_scope]
        if self.write_scope:
            dong += ["", "WRITE_SCOPE (chỉ được ghi vào đây):"] + \
                    [f"  {p}" for p in self.write_scope]
        else:
            dong += ["", "WRITE_SCOPE: (không) — đây là việc CHỈ ĐỌC."]
        if self.do_not_touch:
            dong += ["", "DO_NOT_TOUCH:"] + [f"  {p}" for p in self.do_not_touch]
        if self.tests_required:
            dong += ["", "TESTS_REQUIRED:"] + [f"  {t}" for t in self.tests_required]
        if self.expected_output:
            dong += ["", "EXPECTED_OUTPUT:", self.expected_output.strip()]
        dong += [
            "",
            "TRẢ VỀ một khối JSON DUY NHẤT, không kèm giải thích ngoài khối:",
            '{"status":"ok|failed|blocked","summary":"...","files_changed":[],'
            '"tests":"...","findings":[],"blockers":[],"integration_notes":"..."}',
        ]
        return "\n".join(dong)

    def validate(self) -> None:
        if not self.task_id.strip():
            raise PacketRefused("gói việc thiếu task_id")
        if not self.base_sha.strip():
            # Khong co SHA goc thi ket qua khong gan duoc vao dau — mot worker
            # co the da lam viec tren mot cay khac han.
            raise PacketRefused(f"{self.task_id}: thiếu base_sha")
        ro_ri = scan_for_secrets(self.render())
        if ro_ri:
            raise PacketRefused(
                f"{self.task_id}: gói việc chứa thứ giống credential "
                f"(mẫu {ro_ri!r}) — TỪ CHỐI gửi ra worker ngoài.")


def packet_for(node: TaskNode, *, base_sha: str,
               dependency_summaries: Optional[Dict[str, str]] = None,
               do_not_touch: Sequence[str] = (),
               tests_required: Sequence[str] = (),
               workspace: str = "", branch: str = "") -> TaskPacket:
    p = TaskPacket(
        workspace=workspace, branch=branch,
        task_id=node.id, base_sha=base_sha, objective=node.objective,
        dependencies=tuple(node.dependencies), read_scope=tuple(node.read_scope),
        write_scope=tuple(node.write_scope), do_not_touch=tuple(do_not_touch),
        expected_output=node.expected_output, tests_required=tuple(tests_required),
        risk_class=node.risk_class,
        dependency_summaries=dict(dependency_summaries or {}))
    p.validate()
    return p


@dataclass
class TaskResult:
    """Thứ agent dẫn dắt thực sự tiêu thụ."""

    task_id: str
    worker_id: str
    status: str = "failed"           # ok | failed | blocked | timeout
    summary: str = ""
    commit: str = ""
    files_changed: List[str] = field(default_factory=list)
    tests: str = ""
    duration_seconds: float = 0.0
    findings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    integration_notes: str = ""
    raw_excerpt: str = ""            # chi de chan doan, da cat ngan

    @property
    def ok(self) -> bool:
        return self.status == "ok"


_KHOI_JSON = re.compile(r"\{.*\}", re.DOTALL)


def parse_result(task_id: str, worker_id: str, raw: str,
                 seconds: float) -> TaskResult:
    """Đọc đầu ra worker thành kết quả có cấu trúc.

    Worker là một mô hình ngôn ngữ: nó có thể bọc JSON trong ```json, thêm lời
    dẫn, hoặc trả về văn bản thuần. Nên phép đọc này **khoan dung ở đầu vào**
    nhưng **nghiêm ngặt ở đầu ra** — không đọc được JSON thì đó là `failed`
    kèm trích đoạn để chẩn đoán, KHÔNG BAO GIỜ là `ok` với dữ liệu bịa.
    """
    kq = TaskResult(task_id=task_id, worker_id=worker_id,
                    duration_seconds=round(seconds, 2),
                    # Trich doan chan doan cung phai loc: no la van ban THO
                    # tu worker va se di vao log/bao cao.
                    raw_excerpt=redact((raw or "").strip())[:400])
    khoi = _KHOI_JSON.search(raw or "")
    if not khoi:
        kq.status = "failed"
        kq.summary = "worker không trả về khối JSON nào"
        return kq
    try:
        d = json.loads(khoi.group(0))
    except json.JSONDecodeError as exc:
        kq.status = "failed"
        kq.summary = f"JSON hỏng: {type(exc).__name__}"
        return kq
    if not isinstance(d, dict):
        kq.status = "failed"
        kq.summary = "JSON không phải đối tượng"
        return kq

    trang_thai = str(d.get("status") or "").lower()
    kq.status = trang_thai if trang_thai in ("ok", "failed", "blocked") else "failed"
    # MOI truong den tu worker deu qua `redact` — xem docstring cua no.
    kq.summary = redact(d.get("summary"))[:600]
    kq.commit = redact(d.get("commit"))[:64]
    kq.tests = redact(d.get("tests"))[:300]
    kq.integration_notes = redact(d.get("integration_notes"))[:600]
    for ten, dich in (("files_changed", kq.files_changed),
                      ("findings", kq.findings), ("blockers", kq.blockers)):
        gt = d.get(ten)
        if isinstance(gt, list):
            dich.extend(redact(x)[:200] for x in gt[:50])
    # Mot worker bao "ok" nhung liet ke blocker la mau thuan — tin blocker.
    if kq.status == "ok" and kq.blockers:
        kq.status = "blocked"
    return kq
