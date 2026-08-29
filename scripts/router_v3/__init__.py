"""Router V3 — điều phối song song, có nhận biết phụ thuộc.

Router V2 chạy đúng một worker mỗi lượt. Nút thắt không phải tốc độ worker mà
là chỗ mọi việc xếp hàng sau nhau dù phần lớn chúng độc lập.

ĐO TRƯỚC KHI XÂY (2026-08-30): ba lần gọi `agy` tuần tự mất 18.62s; chạy song
song mất 6.66s, và tổng song song ≈ việc chậm nhất (6.65s). Tức là song song
THẬT — không bị tuần tự hoá ở phía CLI hay phía máy chủ. Nếu phép đo cho kết
quả ngược lại thì cả gói này vô nghĩa, nên nó được đo đầu tiên.

Các tầng, mỗi tầng kiểm thử được riêng:

    dag        — mô tả công việc, bắt chu trình/phạm vi ghi giẫm nhau
    registry   — worker là dữ liệu (sức khoẻ, tải, lịch sử)
    policy     — chấm điểm chọn worker; ranh giới rủi ro cao là CỨNG
    packet     — hợp đồng task/kết quả; giữ ngữ cảnh agent dẫn dắt nhỏ
    scheduler  — chạy song song thật, mở khoá theo từng nút
    worktree   — cô lập cây làm việc cho mỗi worker có ghi

RANH GIỚI CREDENTIAL: Router không bao giờ cầm credential của nhà cung cấp.
Mỗi CLI native tự giữ phiên đăng nhập của nó; Router chỉ trao đổi task/kết quả.
"""
from scripts.router_v3.dag import DagError, RiskClass, TaskDag, TaskNode
from scripts.router_v3.packet import (PacketRefused, TaskPacket, TaskResult,
                                      packet_for, parse_result)
from scripts.router_v3.policy import (NoWorkerAvailable, PROFILES, SpeedMode,
                                      choose_worker, plan_parallelism)
from scripts.router_v3.registry import (AG_SLOTS, ExecutionType, Health,
                                        WorkerRegistry, WorkerSpec,
                                        default_registry)
from scripts.router_v3.scheduler import RunReport, Scheduler

__all__ = [
    "AG_SLOTS", "DagError", "ExecutionType", "Health", "NoWorkerAvailable",
    "PROFILES", "PacketRefused", "RiskClass", "RunReport", "Scheduler",
    "SpeedMode", "TaskDag", "TaskNode", "TaskPacket", "TaskResult",
    "WorkerRegistry", "WorkerSpec", "choose_worker", "default_registry",
    "packet_for", "parse_result", "plan_parallelism",
]
