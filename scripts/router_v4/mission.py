"""Mission + Task DAG trung lập nhà cung cấp — Router V4, mission #4.

DAG ở đây mang **hợp đồng việc**, không mang tên worker. Bên lập kế hoạch
(Claude lead) nói CẦN GÌ; bộ lập lịch quyết định AI LÀM.

    T0 khảo sát kho
     ├─ T1 khảo sát đường provider
     └─ T2 khảo sát điểm tích hợp
          ↓
    T3 thực thi
     ├─ T4 kiểm thử
     └─ T5 review độc lập
          ↓
    T6 tích hợp

DÙNG LẠI, KHÔNG VIẾT LẠI: phần khó của một DAG — bắt chu trình, bắt phụ
thuộc treo, chia lớp, đường tới hạn — đã có và đã được kiểm kỹ ở
`router_v3/dag.py`. `MissionDag` bọc `TaskDag` và giữ thêm bảng
`task_id -> TaskContract`. Viết lại phần đó chỉ để "cho V4 có DAG riêng" là
tạo ra một nguồn sự thật thứ hai cho cùng một thuật toán.

FAIL CLOSED: một DAG sai bị từ chối lúc DỰNG, không phải lúc chạy — lúc
chạy thì đã có worker sửa tệp rồi.

CHỒNG PHẠM VI GHI: hai việc cùng ghi một chỗ mà không có quan hệ phụ thuộc
sẽ giẫm lên nhau. `TaskDag` đã bắt chuyện này; ở đây chỉ cần ánh xạ
`allowed_scope` của hợp đồng sang `write_scope` của nút.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from scripts.router_v3.dag import DagError, RiskClass, TaskDag, TaskNode
from scripts.router_v4.contract import ContractError, TaskContract


def _nut_tu_hop_dong(c: TaskContract) -> TaskNode:
    """Ánh xạ hợp đồng V4 -> nút V3 để dùng lại cơ chế DAG đã kiểm chứng.

    `required_capabilities` của V3 cố ý để RỖNG: định tuyến V4 KHÔNG đi qua
    nhãn năng lực của V3 nữa (nó đọc `Requirements`). Điền vào đây sẽ tạo
    một đường định tuyến thứ hai, âm thầm, không ai bảo trì.
    """
    return TaskNode(
        id=c.task_id, objective=c.objective,
        dependencies=tuple(c.dependencies),
        write_scope=tuple(c.allowed_scope) if c.requirements.repo_write else (),
        read_scope=tuple(c.inputs),
        required_capabilities=(),
        risk_class=(RiskClass.HIGH if c.impact >= 0.7 else
                    RiskClass.MEDIUM if c.impact >= 0.4 else RiskClass.LOW),
        expected_output="; ".join(c.expected_outputs)[:400],
        parallelizable=True,
        estimated_seconds=c.execution.expected_duration)


class MissionDag:
    """DAG đã kiểm hợp lệ + hợp đồng của từng nút."""

    def __init__(self, contracts: Iterable[TaskContract], *,
                 mission_id: str = "",
                 allow_overlapping_writes: bool = False):
        self.mission_id = mission_id or f"m-{uuid.uuid4().hex[:8]}"
        self.contracts: Dict[str, TaskContract] = {}
        for c in contracts:
            c.validate()
            if c.task_id in self.contracts:
                raise DagError(f"trùng task_id: {c.task_id!r}")
            # Gan mission_id cho hop dong chua co — hop dong la frozen nen
            # thay bang mot ban sao thay vi sua tai cho.
            if not c.mission_id:
                c = TaskContract.from_dict({**c.to_dict(),
                                            "mission_id": self.mission_id})
            self.contracts[c.task_id] = c
        self.dag = TaskDag([_nut_tu_hop_dong(c) for c in self.contracts.values()],
                           allow_overlapping_writes=allow_overlapping_writes)

    # -- truy van -----------------------------------------------------------

    def __len__(self) -> int:
        return len(self.contracts)

    def __contains__(self, task_id: str) -> bool:
        return task_id in self.contracts

    def contract(self, task_id: str) -> TaskContract:
        return self.contracts[task_id]

    def ids(self) -> List[str]:
        return list(self.contracts)

    def ready(self, done: Iterable[str], running: Iterable[str] = ()
              ) -> List[TaskContract]:
        return [self.contracts[n.id]
                for n in self.dag.ready(done, running)]

    def waves(self) -> List[List[str]]:
        return self.dag.waves()

    def critical_path(self) -> Tuple[List[str], float]:
        return self.dag.critical_path()

    def dependents_of(self, task_id: str) -> List[str]:
        return self.dag.dependents_of(task_id)

    def ancestors(self, task_id: str) -> Set[str]:
        return self.dag.ancestors(task_id)

    def width(self, *, ceiling: int = 8) -> int:
        return self.dag.recommended_workers(ceiling=ceiling)

    def pending_contracts(self, done: Iterable[str]) -> List[TaskContract]:
        """Hợp đồng CHƯA xong — đầu vào để đo NHU CẦU sắp tới (`Demand`),
        thứ cơ chế giữ năng lực khan hiếm dựa vào."""
        xong = set(done)
        return [c for tid, c in self.contracts.items() if tid not in xong]

    def to_dict(self) -> Dict:
        return {"mission_id": self.mission_id,
                "contracts": [c.to_dict() for c in self.contracts.values()]}

    @staticmethod
    def from_dict(d: Dict, *, allow_overlapping_writes: bool = False
                  ) -> "MissionDag":
        return MissionDag(
            [TaskContract.from_dict(x) for x in (d.get("contracts") or [])],
            mission_id=str(d.get("mission_id") or ""),
            allow_overlapping_writes=allow_overlapping_writes)


@dataclass
class MissionPlan:
    """Kết quả lập kế hoạch: DAG + những gì ĐO ĐƯỢC về nó.

    `critical_seconds` là cận dưới thật của tổng thời gian — thêm worker
    không rút ngắn được nó. Đó là con số quyết định mức song song, không
    phải tổng số nút.
    """

    dag: MissionDag
    waves: List[List[str]]
    critical_path: List[str]
    critical_seconds: float
    total_estimated_seconds: float
    recommended_workers: int

    def to_dict(self) -> Dict:
        return {"mission_id": self.dag.mission_id,
                "tasks": self.dag.ids(), "waves": self.waves,
                "critical_path": self.critical_path,
                "critical_seconds": self.critical_seconds,
                "total_estimated_seconds": self.total_estimated_seconds,
                "recommended_workers": self.recommended_workers,
                "theoretical_speedup": (
                    round(self.total_estimated_seconds / self.critical_seconds, 2)
                    if self.critical_seconds else 1.0)}


def plan(contracts: Sequence[TaskContract] | Sequence[Dict], *,
         mission_id: str = "", ceiling: int = 8,
         allow_overlapping_writes: bool = False) -> MissionPlan:
    """Dựng và ĐO một mission. Ném `DagError`/`ContractError` ngay tại đây."""
    ds = [c if isinstance(c, TaskContract) else TaskContract.from_dict(c)
          for c in contracts]
    d = MissionDag(ds, mission_id=mission_id,
                   allow_overlapping_writes=allow_overlapping_writes)
    duong, giay = d.critical_path()
    return MissionPlan(
        dag=d, waves=d.waves(), critical_path=duong, critical_seconds=giay,
        total_estimated_seconds=round(
            sum(c.execution.expected_duration for c in d.contracts.values()), 2),
        recommended_workers=d.width(ceiling=ceiling))
