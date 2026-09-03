"""Hợp đồng việc chuẩn hoá — Router V4.

Mọi việc giao đi đều đi qua đúng một hình dạng này. Ba khối tách bạch:

    requirements — CẦN GÌ (năng lực). Bộ lập lịch đọc khối này.
    execution    — CHẠY THẾ NÀO (trần thời gian, worktree, quyền phá huỷ).
    verification — CHỨNG MINH THẾ NÀO (test, review độc lập, kiểm hiện vật).

VÌ SAO TÁCH: Router V3 để `TaskNode` gộp mục tiêu, phạm vi và ước lượng vào
một chỗ, và bộ lập lịch phải đoán năng lực từ một danh sách nhãn tự do
(`required_capabilities=("implement",)`). Đoán được với ba nhãn; không đoán
được khi việc cần "đọc video + trả JSON đúng lược đồ + ngữ cảnh dài".

PHẠM VI KHÔNG PHẢI LỜI KHUYÊN. `allowed_scope`/`forbidden_scope` là hợp
đồng, và `verification` ở tầng trên kiểm bằng `git`, không bằng lời khai
của worker. Một worker KHÔNG được tự mở rộng phạm vi: `forbidden_scope`
thắng `allowed_scope` khi hai bên chồng nhau, và mặc định
`destructive_actions_allowed=False`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.router_v4.capabilities import Priority, Reasoning, Requirements

#: Duong CAM tuyet doi, khong hop dong nao mo duoc. Trung voi
#: `router_v3/pool/validation.DUONG_CAM` co chu dich: hai tang cung chan,
#: mot o luc DUNG hop dong, mot o luc KIEM ket qua.
FORBIDDEN_ALWAYS: Tuple[str, ...] = (
    ".git/", ".github/workflows/", ".claude/settings.json",
    ".claude/settings.local.json", ".claude/hooks/", ".env",
)


class ContractError(ValueError):
    """Hợp đồng sai. Ném lúc DỰNG, không bao giờ lúc giao việc."""


class TaskType(str):
    """Nhãn tự do cho loại việc — dùng cho lịch sử/benchmark, KHÔNG dùng để
    định tuyến. Định tuyến chỉ đọc `requirements`. Giữ nó là `str` thay vì
    `Enum` có chủ đích: một `Enum` ở đây sẽ cám dỗ người ta viết
    `if type == REVIEW: dùng Codex` — đúng thứ V4 bỏ."""


@dataclass(frozen=True)
class Execution:
    expected_duration: float = 120.0
    max_wall_time: float = 1800.0
    #: Tran chi phi NGOAI (USD) neu uoc luong duoc. 0 = khong rang buoc.
    max_external_cost: float = 0.0
    destructive_actions_allowed: bool = False
    worktree_required: bool = False

    def validate(self, task_id: str) -> None:
        if self.max_wall_time <= 0:
            raise ContractError(f"{task_id}: max_wall_time phải > 0")
        if self.expected_duration > self.max_wall_time:
            raise ContractError(
                f"{task_id}: expected_duration ({self.expected_duration}s) > "
                f"max_wall_time ({self.max_wall_time}s) — trần sẽ cắt việc "
                f"trước cả khi nó chạy xong theo kỳ vọng.")

    def to_dict(self) -> Dict:
        return {"expected_duration": self.expected_duration,
                "max_wall_time": self.max_wall_time,
                "max_external_cost": self.max_external_cost,
                "destructive_actions_allowed": self.destructive_actions_allowed,
                "worktree_required": self.worktree_required}

    @staticmethod
    def from_dict(d: Optional[Dict]) -> "Execution":
        d = dict(d or {})
        return Execution(
            expected_duration=float(d.get("expected_duration") or 120.0),
            max_wall_time=float(d.get("max_wall_time") or 1800.0),
            max_external_cost=float(d.get("max_external_cost") or 0.0),
            destructive_actions_allowed=bool(
                d.get("destructive_actions_allowed")),
            worktree_required=bool(d.get("worktree_required")))


@dataclass(frozen=True)
class Verification:
    """Cách CHỨNG MINH việc đã xong. Không có khối này thì "xong" chỉ là lời
    khai của worker — xem `router_v3/pool/validation.py`."""

    #: Lenh test chay THAT sau khi worker xong. Moi lenh la mot DANH SACH
    #: (khong phai chuoi shell) — khong co `shell=True` o bat ky dau.
    tests: Tuple[Tuple[str, ...], ...] = ()
    independent_review_required: bool = False
    #: Duong dan hien vat PHAI ton tai sau khi viec xong.
    artifact_checks: Tuple[str, ...] = ()

    def to_dict(self) -> Dict:
        return {"tests": [list(t) for t in self.tests],
                "independent_review_required": self.independent_review_required,
                "artifact_checks": list(self.artifact_checks)}

    @staticmethod
    def from_dict(d: Optional[Dict]) -> "Verification":
        d = dict(d or {})
        return Verification(
            tests=tuple(tuple(str(x) for x in t) for t in (d.get("tests") or ())),
            independent_review_required=bool(
                d.get("independent_review_required")),
            artifact_checks=tuple(str(x) for x in
                                  (d.get("artifact_checks") or ())))


def _chuan_hoa(p: str) -> str:
    return str(p).strip().replace("\\", "/").strip("/")


@dataclass(frozen=True)
class TaskContract:
    """Thứ một worker THỰC SỰ nhận, và thứ bộ lập lịch THỰC SỰ đọc."""

    task_id: str
    objective: str
    mission_id: str = ""
    type: str = "generic"

    allowed_scope: Tuple[str, ...] = ()
    forbidden_scope: Tuple[str, ...] = ()

    inputs: Tuple[str, ...] = ()
    expected_outputs: Tuple[str, ...] = ()

    requirements: Requirements = field(default_factory=Requirements)
    execution: Execution = field(default_factory=Execution)
    verification: Verification = field(default_factory=Verification)

    #: Dieu kien DUNG SOM — worker phai bao `blocked` thay vi doan tiep.
    stop_conditions: Tuple[str, ...] = ()

    dependencies: Tuple[str, ...] = ()
    #: Anh huong va do bat dinh trong [0,1] — dieu khien che do thuc thi
    #: (SOLO / PRIMARY+CRITIC / PARALLEL HYPOTHESES), xem `modes.py`.
    impact: float = 0.3
    uncertainty: float = 0.3

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_scope",
                           tuple(_chuan_hoa(p) for p in self.allowed_scope))
        object.__setattr__(
            self, "forbidden_scope",
            tuple(dict.fromkeys([_chuan_hoa(p) for p in self.forbidden_scope]
                                + [_chuan_hoa(p) for p in FORBIDDEN_ALWAYS])))

    @property
    def is_write(self) -> bool:
        return bool(self.allowed_scope) and self.requirements.repo_write

    def validate(self) -> None:
        if not self.task_id.strip():
            raise ContractError("hợp đồng thiếu task_id")
        if not re.match(r"^[A-Za-z0-9._-]+$", self.task_id):
            raise ContractError(
                f"task_id {self.task_id!r} chứa ký tự lạ — nó thành tên nhánh "
                f"và tên thư mục worktree, nên chỉ cho phép chữ/số/._-")
        if not self.objective.strip():
            raise ContractError(f"{self.task_id}: thiếu `objective`")
        self.execution.validate(self.task_id)

        if self.requirements.repo_write and not self.allowed_scope:
            raise ContractError(
                f"{self.task_id}: đòi `repo_write` nhưng `allowed_scope` rỗng "
                f"— một việc được ghi mà không nói được ghi ở ĐÂU thì không "
                f"kiểm phạm vi được, và lưới cuối cùng mất tác dụng.")
        if self.requirements.repo_write and not self.execution.worktree_required:
            raise ContractError(
                f"{self.task_id}: đòi `repo_write` nhưng không đặt "
                f"`worktree_required` — việc có ghi PHẢI chạy trong cây làm "
                f"việc cô lập, không bao giờ trên cây chung.")
        if self.allowed_scope and not self.requirements.repo_write:
            raise ContractError(
                f"{self.task_id}: có `allowed_scope` nhưng không đòi "
                f"`repo_write` — mâu thuẫn; việc chỉ đọc không cần phạm vi ghi.")

        # `forbidden_scope` THANG `allowed_scope`. Chan o day thay vi de hai
        # danh sach mau thuan roi ai doc truoc thi thang.
        for a in self.allowed_scope:
            for f in self.forbidden_scope:
                if a == f or a.startswith(f + "/") or f.startswith(a + "/"):
                    raise ContractError(
                        f"{self.task_id}: allowed_scope {a!r} chồng lên "
                        f"forbidden_scope {f!r}. Cấm luôn thắng — sửa hợp "
                        f"đồng thay vì để hai danh sách mâu thuẫn.")
        if self.requirements.shell and not self.execution.destructive_actions_allowed:
            # Khong phai loi: chi ghi ro rang shell KHONG duoc cap tu dong.
            pass
        if not 0.0 <= self.impact <= 1.0:
            raise ContractError(f"{self.task_id}: impact ngoài [0,1]")
        if not 0.0 <= self.uncertainty <= 1.0:
            raise ContractError(f"{self.task_id}: uncertainty ngoài [0,1]")

    def scope_violations(self, changed: Sequence[str]) -> List[str]:
        """Tệp đổi NGOÀI phạm vi cho phép, hoặc chạm phạm vi cấm.

        Đây là hàm THUẦN, kiểm được tất định. Việc lấy `changed` từ `git` là
        chuyện của tầng kiểm định.
        """
        ra: List[str] = []
        for t in changed:
            n = _chuan_hoa(t)
            if not n:
                continue
            if any(n == f or n.startswith(f + "/") for f in self.forbidden_scope):
                ra.append(n)
                continue
            if not self.allowed_scope:
                ra.append(n)
                continue
            if not any(n == a or n.startswith(a + "/") for a in self.allowed_scope):
                ra.append(n)
        return sorted(set(ra))

    def render(self, *, workspace: str = "", branch: str = "",
               dependency_summaries: Optional[Dict[str, str]] = None) -> str:
        """Văn bản gửi worker. Thuần văn bản: mọi CLI đều đọc được."""
        d = ["TASK_ID: " + self.task_id,
             "TYPE: " + self.type,
             "MISSION: " + (self.mission_id or "(none)"),
             "",
             "OBJECTIVE:", self.objective.strip()]
        if dependency_summaries:
            d += ["", "DEPENDENCY_RESULTS (tóm tắt, không phải hội thoại):"]
            for k, v in sorted(dependency_summaries.items()):
                d.append(f"  - {k}: {str(v).strip()[:400]}")
        if self.inputs:
            d += ["", "INPUTS:"] + [f"  {x}" for x in self.inputs]
        if workspace:
            d += ["", f"WORKSPACE (làm việc ở đây, không nơi khác): {workspace}"]
        if self.allowed_scope:
            d += ["", "ALLOWED_SCOPE (chỉ được ghi vào đây):"] + \
                 [f"  {p}" for p in self.allowed_scope]
        else:
            d += ["", "ALLOWED_SCOPE: (không) — đây là việc CHỈ ĐỌC."]
        d += ["", "FORBIDDEN_SCOPE (không bao giờ chạm):"] + \
             [f"  {p}" for p in self.forbidden_scope]
        if self.expected_outputs:
            d += ["", "EXPECTED_OUTPUTS:"] + [f"  {x}" for x in self.expected_outputs]
        if self.verification.tests:
            d += ["", "TESTS_THAT_WILL_BE_RUN_ON_YOUR_RESULT:"] + \
                 [f"  {' '.join(t)}" for t in self.verification.tests]
        if self.stop_conditions:
            d += ["", "STOP_CONDITIONS (gặp thì trả `blocked`, ĐỪNG đoán tiếp):"] + \
                 [f"  {x}" for x in self.stop_conditions]
        if not self.execution.destructive_actions_allowed:
            d += ["", "KHÔNG được thực hiện thao tác phá huỷ (xoá, reset, "
                  "push, deploy, đổi cấu hình hệ thống)."]
        d += ["",
              f"Trần thời gian: {self.execution.max_wall_time:.0f}s.",
              "",
              "TRẢ VỀ một khối JSON DUY NHẤT, không kèm giải thích ngoài khối:",
              '{"status":"ok|failed|blocked","summary":"...","changes":[],'
              '"tests":{"passed":0,"failed":0},"artifacts":[],"findings":[],'
              '"risks":[],"followups":[],"requires_decision":false,'
              '"decision_request":"","failure_reason":""}']
        return "\n".join(d)

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id, "mission_id": self.mission_id,
            "type": self.type, "objective": self.objective,
            "allowed_scope": list(self.allowed_scope),
            "forbidden_scope": list(self.forbidden_scope),
            "inputs": list(self.inputs),
            "expected_outputs": list(self.expected_outputs),
            "requirements": self.requirements.to_dict(),
            "execution": self.execution.to_dict(),
            "verification": self.verification.to_dict(),
            "stop_conditions": list(self.stop_conditions),
            "dependencies": list(self.dependencies),
            "impact": self.impact, "uncertainty": self.uncertainty,
        }

    @staticmethod
    def from_dict(d: Dict) -> "TaskContract":
        c = TaskContract(
            task_id=str(d["task_id"]), objective=str(d.get("objective") or ""),
            mission_id=str(d.get("mission_id") or ""),
            type=str(d.get("type") or "generic"),
            allowed_scope=tuple(d.get("allowed_scope") or ()),
            forbidden_scope=tuple(d.get("forbidden_scope") or ()),
            inputs=tuple(d.get("inputs") or ()),
            expected_outputs=tuple(d.get("expected_outputs") or ()),
            requirements=Requirements.from_dict(d.get("requirements")),
            execution=Execution.from_dict(d.get("execution")),
            verification=Verification.from_dict(d.get("verification")),
            stop_conditions=tuple(d.get("stop_conditions") or ()),
            dependencies=tuple(d.get("dependencies") or ()),
            impact=float(d.get("impact") if d.get("impact") is not None else 0.3),
            uncertainty=float(d.get("uncertainty")
                              if d.get("uncertainty") is not None else 0.3))
        c.validate()
        return c
