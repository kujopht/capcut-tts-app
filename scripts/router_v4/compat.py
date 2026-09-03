"""Cầu tương thích Router V3 -> V4 — mission #23.

"Existing Router V3/OpenCode workflows must continue working where possible.
Prefer V3 -> compatibility adapter -> new registry/scheduler rather than
deleting working code."

Module này là cái cầu đó. Nó KHÔNG sửa gì trong V3; nó dịch xuôi:

    TaskNode  (V3)  ->  TaskContract (V4)
    TaskDag   (V3)  ->  MissionDag   (V4)
    WorkerSpec(V3)  ->  (runtime, model) (V4)

KHÔNG CÓ THAY ĐỔI PHÁ VỠ nào ở V3: `scripts/router_v3/**` chạy y như trước,
kể cả `scheduler.py` đồng bộ và `pool/` bất đồng bộ. V4 là một tầng SONG
SONG, dùng chung các nguyên thuỷ đã kiểm chứng.

ĐIỂM DỊCH KHÓ NHẤT, ghi rõ vì nó là chỗ dễ mất thông tin:

    V3 mô tả nhu cầu bằng NHÃN tự do (`required_capabilities=("implement",)`).
    V4 mô tả bằng CỜ NĂNG LỰC (`coding=True, repo_write=True, ...`).

Ánh xạ dưới đây là SUY DIỄN, không phải sự thật — một nút V3 gắn nhãn
"implement" không nói được nó có cần đọc ảnh hay không. Nên bản dịch chọn
tập năng lực TỐI THIỂU hợp lý và ghi lại điều đó trong `notes`. Suy diễn
rộng tay hơn sẽ tạo ra rào cứng mà không ai yêu cầu, và loại sạch ứng viên.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.router_v3.dag import RiskClass, TaskDag, TaskNode
from scripts.router_v3.registry import WorkerSpec
from scripts.router_v4.capabilities import Priority, Reasoning, Requirements
from scripts.router_v4.contract import Execution, TaskContract, Verification
from scripts.router_v4.mission import MissionDag
from scripts.router_v4.runtime import Placement

#: Nhan nang luc V3 -> co nang luc V4. Chi nhung suy dien AN TOAN.
_NHAN_V3 = {
    "recon":            {"repo_read": True, "structured_output": True},
    "implement":        {"coding": True, "repo_read": True,
                         "structured_output": True},
    "tests":            {"coding": True, "repo_read": True,
                         "structured_output": True},
    "review":           {"coding": True, "repo_read": True,
                         "structured_output": True},
    "security_review":  {"coding": True, "repo_read": True,
                         "structured_output": True},
    "frontend":         {"coding": True, "repo_read": True,
                         "structured_output": True},
    "architecture":     {"repo_read": True, "long_context": True,
                         "structured_output": True},
    "integration":      {"coding": True, "repo_read": True,
                         "structured_output": True},
    "challenger":       {"repo_read": True, "structured_output": True},
    "media_agent":      {"multimodal": True, "structured_output": True},
    "research_agent":   {"repo_read": True, "long_context": True,
                         "structured_output": True},
    "scraping_agent":   {"coding": True, "repo_read": True,
                         "structured_output": True},
    "test_generator":   {"coding": True, "repo_read": True,
                         "structured_output": True},
    "frontend_prototyper": {"coding": True, "structured_output": True},
    "security_reviewer": {"coding": True, "repo_read": True,
                          "structured_output": True},
}

#: Muc rui ro V3 -> (reasoning, impact). Viec rui ro cao doi suy luan cao
#: VA duoc danh `impact` cao, nen `modes.py` tu leo thang len PRIMARY+CRITIC.
_RUI_RO = {
    RiskClass.LOW:    (Reasoning.MEDIUM, 0.2),
    RiskClass.MEDIUM: (Reasoning.MEDIUM, 0.5),
    RiskClass.HIGH:   (Reasoning.HIGH, 0.85),
}


def node_to_contract(n: TaskNode, *, mission_id: str = "",
                     tests: Sequence[Sequence[str]] = ()) -> TaskContract:
    """Dịch một `TaskNode` V3 thành `TaskContract` V4."""
    co: Dict[str, bool] = {}
    for nhan in n.required_capabilities:
        co.update(_NHAN_V3.get(nhan, {}))
    if n.is_write:
        co["repo_write"] = True
        co["repo_read"] = True
    if not co:
        # Khong nhan nao -> chi doc kho. Day la tap TOI THIEU an toan; doan
        # rong hon se tao rao cung ma nut V3 khong he yeu cau.
        co = {"repo_read": True, "structured_output": True}

    suy_luan, anh_huong = _RUI_RO.get(n.risk_class, (Reasoning.MEDIUM, 0.3))
    can_review = n.risk_class is RiskClass.HIGH

    return TaskContract(
        task_id=n.id, mission_id=mission_id, objective=n.objective,
        type="/".join(n.required_capabilities) or "generic",
        allowed_scope=tuple(n.write_scope),
        inputs=tuple(n.read_scope),
        expected_outputs=((n.expected_output,) if n.expected_output else ()),
        requirements=Requirements(
            **co, reasoning_level=suy_luan,
            pin_provider=n.preferred_provider or None),
        execution=Execution(
            expected_duration=n.estimated_seconds,
            max_wall_time=max(300.0, n.estimated_seconds * 6),
            destructive_actions_allowed=False,
            worktree_required=n.is_write),
        verification=Verification(
            tests=tuple(tuple(t) for t in tests),
            independent_review_required=can_review),
        dependencies=tuple(n.dependencies),
        impact=anh_huong,
        uncertainty=0.4 if n.risk_class is RiskClass.HIGH else 0.25)


def dag_to_mission(dag: TaskDag, *, mission_id: str = "",
                   tests: Sequence[Sequence[str]] = ()) -> MissionDag:
    """Dịch cả một `TaskDag` V3 thành `MissionDag` V4.

    `allow_overlapping_writes=True` vì `TaskDag` gốc ĐÃ kiểm điều đó lúc
    dựng; kiểm lại sẽ từ chối một DAG vốn đã được chấp nhận có ý thức (V3
    cho phép bật cờ đó).
    """
    return MissionDag(
        [node_to_contract(n, mission_id=mission_id, tests=tests)
         for n in dag.nodes()],
        mission_id=mission_id, allow_overlapping_writes=True)


def spec_to_placement(spec: WorkerSpec) -> Optional[Placement]:
    """`WorkerSpec` V3 -> `Placement` V4, nếu spec có khai model.

    `None` khi spec không có `model`: V3 cho phép một worker không khai
    model (chỉ có `pool`), và bịa ra một model để cho đủ hình dạng sẽ tạo
    một placement trỏ vào hư không.
    """
    if not spec.model:
        return None
    return Placement(spec.worker_id, spec.model)


def contract_to_node(c: TaskContract) -> TaskNode:
    """Chiều ngược: `TaskContract` V4 -> `TaskNode` V3.

    Dùng khi muốn chạy một mission V4 qua `Scheduler` đồng bộ của V3 (ví dụ
    một script cũ). MẤT MÁT có chủ đích và ghi rõ: khối `requirements` chi
    tiết của V4 không có chỗ trong V3, nên nó bị rút gọn về nhãn. Đừng dùng
    chiều này cho việc cần định tuyến theo năng lực.
    """
    nhan: List[str] = []
    r = c.requirements
    if r.repo_write:
        nhan.append("implement")
    elif r.coding:
        nhan.append("review")
    else:
        nhan.append("recon")
    if r.multimodal or r.image or r.video or r.audio:
        nhan.append("media_agent")
    return TaskNode(
        id=c.task_id, objective=c.objective, dependencies=tuple(c.dependencies),
        write_scope=tuple(c.allowed_scope), read_scope=tuple(c.inputs),
        required_capabilities=tuple(nhan),
        risk_class=(RiskClass.HIGH if c.impact >= 0.7 else
                    RiskClass.MEDIUM if c.impact >= 0.4 else RiskClass.LOW),
        expected_output="; ".join(c.expected_outputs)[:400],
        estimated_seconds=c.execution.expected_duration)
