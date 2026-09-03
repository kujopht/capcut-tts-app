"""Router V4 — kết cấu thực thi AI đa nhà cung cấp, định tuyến theo NĂNG LỰC.

DỰNG TRÊN Router V3, KHÔNG THAY NÓ. Những gì V3 đã làm tốt được dùng lại
nguyên vẹn: `dag.py` (bắt chu trình/đường tới hạn), `worktree.py` (cô lập
cây làm việc), `worker_adapter.py` + các adapter provider, `pool/validation.py`
(không tin worker tự khai PASS), `pool/store.py` (sổ việc bền).

Cái V4 THÊM là mô hình dữ liệu mà V3 thiếu:

    runtime.py    WorkerRuntime / ModelCapability / QuotaPool
                  — tài khoản là VẬT CHỨA, model là NĂNG LỰC, quota DÙNG CHUNG
    contract.py   hợp đồng việc chuẩn hoá (requirements/execution/verification)
    capabilities. từ vựng năng lực + rào cứng vs thang đo
    mission.py    Task DAG mang hợp đồng, không mang tên worker
    scheduler.py  chọn placement (runtime, model) — GIẢI THÍCH ĐƯỢC
    modes.py      SOLO / PRIMARY+CRITIC / PARALLEL HYPOTHESES + leo thang
    leases.py     lease có hạn + nhịp tim (chặn giao trùng / BUSY bỏ hoang)
    envelope.py   phong bì kết quả gọn + nhật ký thô để ngoài ngữ cảnh
    history.py    kho benchmark — tiên nghiệm nhường chỗ cho số thực đo
    compat.py     cầu V3 -> V4, để luồng cũ vẫn chạy

QUY TẮC KIẾN TRÚC KHÔNG ĐƯỢC PHÁ:

    Định tuyến theo YÊU CẦU của việc, không theo vai trò model đóng cứng.

Không nơi nào trong gói này (hay trong `config/fabric.json`) được viết
"AG01 làm code, AG02 làm review". Việc mô tả nhu cầu; model khai năng lực;
bộ lập lịch ghép chúng lại và giải thích vì sao.
"""
from scripts.router_v4.capabilities import (HARD_CAPABILITIES, Priority,
                                            Reasoning, Requirements)
from scripts.router_v4.contract import (ContractError, Execution, TaskContract,
                                        Verification)
from scripts.router_v4.mission import MissionDag, MissionPlan, plan
from scripts.router_v4.modes import EscalationPolicy, Mode, chon_che_do
from scripts.router_v4.runtime import (Fabric, FabricError, ModelCapability,
                                       Placement, QuotaPool, RuntimeStatus,
                                       Source, WorkerRuntime)
from scripts.router_v4.scheduler import (Decision, Demand, NoEligiblePlacement,
                                         Scheduler, Weights)

__all__ = [
    "HARD_CAPABILITIES", "ContractError", "Decision", "Demand",
    "EscalationPolicy", "Execution", "Fabric", "FabricError", "Mode",
    "MissionDag", "MissionPlan", "ModelCapability", "NoEligiblePlacement",
    "Placement", "Priority", "QuotaPool", "Reasoning", "Requirements",
    "RuntimeStatus", "Scheduler", "Source", "TaskContract", "Verification",
    "WorkerRuntime", "Weights", "chon_che_do", "plan",
]
