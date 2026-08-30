"""Điểm kiểm tra của agent dẫn dắt — Router LTS Phase 10 + 14.

VÌ SAO: `packet.py` đã giữ ngữ cảnh của MỘT worker gọn (gói việc/kết quả có
cấu trúc thay vì hội thoại đầy đủ) — nhưng khi agent dẫn dắt tự tổng kết
một lượt chạy DAG để tiếp tục sau (crash/resume, hoặc chỉ để báo cáo), nó
dễ bị cám dỗ chép lại nguyên văn `raw_excerpt`/`summary` của mọi nút. Đây
là hình dạng CỐ Ý HẸP để chặn điều đó: chỉ bảy trường, không có chỗ nào
cho hội thoại đầy đủ của worker.

`Checkpoint` là thứ **cần và đủ** để agent dẫn dắt tiếp tục: nút nào xong,
commit nào đã có, test nào đã chạy, phát hiện gì, bất biến nào phải giữ,
gì đang chặn, và bước tiếp theo. KHÔNG có nội dung việc, KHÔNG có
`raw_excerpt` của worker.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence

from scripts.router_v3.packet import scan_for_secrets

if TYPE_CHECKING:
    from scripts.router_v3.dag import TaskDag
    from scripts.router_v3.scheduler import RunReport

TEN_TAP_MAC_DINH = ".router/checkpoints/latest.json"


@dataclass
class Checkpoint:
    dag_state: Dict[str, str] = field(default_factory=dict)   # node_id -> ok|failed|blocked|skipped|pending
    commits: List[str] = field(default_factory=list)
    tests: Dict[str, str] = field(default_factory=dict)       # node_id -> tom tat test
    findings: List[str] = field(default_factory=list)
    invariants: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)
    base_sha: str = ""

    @property
    def con_lai(self) -> List[str]:
        """Nút CHƯA XONG — đây là danh sách cần làm lại khi resume."""
        return [n for n, s in self.dag_state.items() if s not in ("ok",)]


def tu_run_report(dag: "TaskDag", report: "RunReport", *,
                  invariants: Sequence[str] = (),
                  next_actions: Sequence[str] = (),
                  base_sha: str = "") -> Checkpoint:
    trang_thai: Dict[str, str] = {}
    for n in dag.nodes():
        if n.id in report.results:
            trang_thai[n.id] = report.results[n.id].status
        elif n.id in report.skipped:
            trang_thai[n.id] = "skipped"
        else:
            trang_thai[n.id] = "pending"

    commits = [r.commit for r in report.results.values() if r.commit]
    tests = {tid: r.tests for tid, r in report.results.items() if r.tests}
    findings = [f for r in report.results.values() for f in r.findings]
    blockers = [b for r in report.results.values() for b in r.blockers]
    for tid, vp in report.scope_violations.items():
        blockers.append(f"{tid}: ghi ngoài write_scope — {vp}")

    return Checkpoint(dag_state=trang_thai, commits=commits, tests=tests,
                      findings=findings, invariants=list(invariants),
                      blockers=blockers, next_actions=list(next_actions),
                      base_sha=base_sha)


def luu(cp: Checkpoint, *, duong: Optional[Path] = None) -> Path:
    p = duong or Path.cwd() / TEN_TAP_MAC_DINH
    noi_dung = json.dumps(asdict(cp), ensure_ascii=False, indent=2)
    ro_ri = scan_for_secrets(noi_dung)
    if ro_ri:
        raise ValueError(
            f"checkpoint chứa thứ giống credential (mẫu {ro_ri!r}) — TỪ CHỐI lưu.")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(noi_dung, encoding="utf-8")
    return p


def doc(duong: Optional[Path] = None) -> Optional[Checkpoint]:
    p = duong or Path.cwd() / TEN_TAP_MAC_DINH
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    truong_hop_le = {f for f in Checkpoint.__dataclass_fields__}
    return Checkpoint(**{k: v for k, v in d.items() if k in truong_hop_le})
