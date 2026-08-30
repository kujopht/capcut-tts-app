"""Hợp đồng worker trung lập nhà cung cấp — Router LTS, Phase 1 + 2.

VÌ SAO: mỗi provider cho tới nay (native `agy`, cầu nối AG02) được lắp
thẳng vào `Scheduler` qua một hàm `Executor` tự do — hoạt động, nhưng
không có RANH GIỚI rõ giữa "việc của core" và "việc của một provider cụ
thể". Thêm OpenCode/Grok/Kiro theo kiểu đó nghĩa là core phải biết hình
dạng riêng của từng CLI. `WorkerAdapter` là ranh giới đó: core (DAG,
Scheduler, WorktreeManager) chỉ nói chuyện qua chín phương thức dưới đây và
qua `TaskPacket`/`TaskResult` — không bao giờ đọc trực tiếp JSON/stdout của
một provider. Gỡ một adapter ra khỏi hệ thống không đụng gì tới ba module
core đó.

`TaskResult` (trong `packet.py`) chính LÀ `WorkerResult` của hợp đồng này —
xem docstring của nó để biết vì sao không có lớp thứ hai trùng lặp.

KHÔNG BAO GIỜ ĐƯỢC: một adapter cầm credential nhà cung cấp thay vì để CLI/
client gốc tự giữ. Xem `registry.py` — bất biến đó áp dụng y hệt ở đây.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Optional

from scripts.router_v3.packet import TaskPacket, TaskResult
from scripts.router_v3.registry import Health, WorkerSpec


class TransportKind(str, Enum):
    """Router LTS Phase 2 — thứ tự ƯU TIÊN khi tích hợp một provider MỚI,
    không phải một lựa chọn tự do: chuẩn càng ổn định thì càng ít mã riêng
    của Router phải hiểu hình dạng của provider đó.

    1. ACP           — giao thức chuẩn, nhiều client/server cùng nói được.
    2. HTTP_SERVER    — server thường trực (`opencode serve`, OpenAPI...).
    3. STRUCTURED_CLI — CLI headless có JSON vào/ra ổn định (agy, `--print`).
    4. NATIVE_BRIDGE  — chỉ khi KHÔNG có chuẩn nào ở trên (đảo chiều quyền
                        sở hữu cho một phiên đã xác thực sẵn — xem bridge.py).
    """

    ACP = "acp"
    HTTP_SERVER = "http_server"
    STRUCTURED_CLI = "structured_cli"
    NATIVE_BRIDGE = "native_bridge"


@dataclass
class HealthReport:
    """Trạng thái tại một thời điểm — KHÔNG bao giờ chứa token/cookie."""

    state: Health
    detail: str = ""


class WorkerAdapter(ABC):
    """Một provider PHẢI hiện thực đúng chín phương thức này.

    `provider` là nhãn cố định (vd "antigravity", "opencode") — dùng để
    gắn vào `TaskResult.provider` mà không phải đoán từ hình dạng phản hồi.
    """

    provider: str = ""
    transport: TransportKind = TransportKind.STRUCTURED_CLI

    @abstractmethod
    def register(self) -> WorkerSpec:
        """Mô tả TĨNH của worker này — không chạm mạng/tiến trình."""

    @abstractmethod
    def health(self) -> HealthReport:
        """Trạng thái NGAY BÂY GIỜ. Gọi được cả khi chưa `start_session`."""

    @abstractmethod
    def capabilities(self) -> FrozenSet[str]:
        """Tập năng lực — phải là tập con của `registry.CAPABILITIES`."""

    @abstractmethod
    def start_session(self, *, workspace: Optional[str] = None) -> bool:
        """Dựng phiên làm việc (tiến trình ấm, kết nối cầu nối, ...).

        `workspace` là worktree CÔ LẬP của việc sắp giao — bắt buộc với mọi
        adapter CÓ GHI. Trả `False` nếu dựng hỏng, KHÔNG được ném lỗi cho
        một thứ có thể đoán trước (chưa cài, chưa đăng nhập) — đó là việc
        của `health()` báo trước khi gọi đến đây.

        CẢNH BÁO CHO NGƯỜI HIỆN THỰC (review độc lập, 2026-08-30): với một
        WORKER THƯỜNG TRỰC đã khởi động TRƯỚC bằng phạm vi thư mục CỐ ĐỊNH
        (`AntigravityBridgeAdapter`, `OpenCodeAdapter`) — `workspace` KHÔNG
        đổi được phạm vi đó theo từng lệnh gọi. Trả `True` trong trường hợp
        đó là ĐÚNG cho tình trạng "phiên khoẻ", nhưng KHÔNG chứng minh
        `workspace` yêu cầu thực sự nằm trong phạm vi mà worker có thể ghi
        vào — bên gọi PHẢI tự đảm bảo `workspace` là thư mục con của phạm
        vi cố định đó (xem cách `dispatch_phase7_phase8.py` của Story
        Harvester V4 làm: cấp `--add-dir` là thư mục CHA chung, rồi mọi
        worktree việc sau đều là thư mục con của nó). Trả `True` mà im lặng
        bỏ qua `workspace` không kiểm được là nguồn của một lớp lỗi ĐẶC BIỆT
        khó chẩn đoán: việc "thành công" nhưng ghi nhầm chỗ.
        """

    @abstractmethod
    def send_task(self, packet: TaskPacket) -> TaskResult:
        """Gửi MỘT việc, chờ kết quả. Luôn trả `TaskResult` — không bao giờ
        để lộ hình dạng JSON/stdout riêng của provider ra ngoài hàm này."""

    @abstractmethod
    def cancel(self) -> None:
        """Huỷ việc đang chạy nếu giao thức cho phép. Một số giao thức
        (vd cầu nối đồng bộ hoàn toàn) không huỷ được việc ĐANG bay giữa
        chừng — khi đó phải NÓI RÕ trong docstring của lớp con thay vì giả
        vờ đã huỷ; không có adapter nào được coi `cancel()` là no-op câm
        lặng nếu nó không thực sự làm gì."""

    @abstractmethod
    def result(self) -> Optional[TaskResult]:
        """Kết quả của lượt `send_task` gần nhất, hoặc `None` nếu chưa từng
        gọi. Dùng cho kiểu polling thay vì chỉ đọc giá trị trả về trực tiếp."""

    @abstractmethod
    def reset_context(self) -> None:
        """Bỏ hội thoại/ngữ cảnh cũ, giữ nguyên tiến trình/kết nối nếu có
        thể (rẻ hơn `shutdown()` rồi `start_session()` lại)."""

    @abstractmethod
    def shutdown(self) -> None:
        """Đóng hẳn phiên. An toàn khi gọi nhiều lần hoặc chưa từng mở."""


def adapter_executor(adapters: dict):
    """Cầu nối `WorkerAdapter` -> `Executor` mà `Scheduler` đã biết dùng.

    `Scheduler` không đổi: nó chỉ cần một hàm `(packet, spec) ->
    (raw_text, seconds)`. Hàm này tra `adapters[spec.worker_id]`, gọi
    `send_task`, rồi trả (JSON của TaskResult, thời lượng) — `parse_result`
    phía Scheduler đọc lại được y hệt một Executor kiểu cũ, nên KHÔNG cần
    sửa `scheduler.py` để dùng adapter mới.
    """
    import json
    import time

    def _thuc_thi(packet: TaskPacket, spec: WorkerSpec):
        adapter = adapters.get(spec.worker_id)
        if adapter is None:
            return json.dumps({"status": "failed",
                               "summary": f"không có adapter cho {spec.worker_id}"}), 0.0
        t0 = time.perf_counter()
        kq = adapter.send_task(packet)
        giay = time.perf_counter() - t0
        return json.dumps({
            "status": kq.status, "summary": kq.summary, "commit": kq.commit,
            "files_changed": kq.files_changed, "tests": kq.tests,
            "findings": kq.findings, "blockers": kq.blockers,
            "integration_notes": kq.integration_notes,
        }, ensure_ascii=False), (kq.duration_seconds or giay)

    return _thuc_thi
