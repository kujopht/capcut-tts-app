"""Adapter Kiro CLI — Router LTS Phase 5.

KHÔNG cài trên máy này (`where kiro-cli` không thấy gì) và KHÔNG bắt buộc
cho Router LTS — mục tiêu của mission rõ ràng: "nếu giới hạn tài
khoản/miễn phí cản trở việc chạy không giám sát hữu ích thì GHI LẠI và để
Kiro tuỳ chọn." Đây là mức đó.

Kiro công bố ACP THẬT (`kiro-cli acp` — JSON-RPC qua stdin/stdout, xem
kiro.dev/docs/cli/acp), nhưng KHÔNG có tài liệu công khai xác nhận được
một cờ prompt-một-lần/JSON đơn giản kiểu `grok -p`/`agy --print` lúc viết
module này. Bịa cờ dòng lệnh mà chưa có gì xác nhận là đúng thứ mission
này cấm ("không giả vờ tích hợp thành công") — nên `send_task()` ở đây
KHÔNG gọi subprocess nào cả, nó trả `status="blocked"` kèm lý do rõ ràng
thay vì một lời gọi có thể âm thầm sai cờ.

Khi có `kiro-cli` cài thật để thử, việc cần làm là dựng một client JSON-RPC
qua stdio nói chuyện với `kiro-cli acp` (session/new, session/prompt,
session/update) — KHÔNG phải sửa module này để đoán thêm cờ CLI.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import FrozenSet, Optional

from scripts.router_v3.packet import TaskPacket, TaskResult
from scripts.router_v3.registry import ExecutionType, Health, WorkerSpec
from scripts.router_v3.worker_adapter import HealthReport, TransportKind, WorkerAdapter

DEFAULT_KIRO = Path(__import__("os").environ.get("LOCALAPPDATA", "")) / "kiro-cli" / "bin" / "kiro-cli.exe"


def find_kiro_cli() -> Optional[str]:
    tren_path = shutil.which("kiro-cli") or shutil.which("kiro")
    if tren_path:
        return tren_path
    for ung_vien in (DEFAULT_KIRO, DEFAULT_KIRO.with_suffix("")):
        if ung_vien.exists():
            return str(ung_vien)
    return None


class KiroAdapter(WorkerAdapter):
    provider = "kiro"
    transport = TransportKind.ACP

    def __init__(self, worker_id: str, *, binary: Optional[str] = None):
        self._worker_id = worker_id
        self._binary = binary
        self._last: Optional[TaskResult] = None

    def register(self) -> WorkerSpec:
        return WorkerSpec(
            worker_id=self._worker_id, provider_family=self.provider,
            execution_type=ExecutionType.LOCAL_CLI, pool="KIRO",
            capabilities=frozenset({"implement", "review"}),
            max_concurrent=1,
            notes="kiro-cli acp (ACP) — TUỲ CHỌN, KHÔNG bắt buộc cho LTS; "
                 "chưa cài trên máy này, chưa dựng client ACP")

    def health(self) -> HealthReport:
        exe = self._binary or find_kiro_cli()
        if not exe:
            return HealthReport(Health.UNAVAILABLE,
                                "không tìm thấy kiro-cli — tuỳ chọn, không chặn LTS")
        return HealthReport(
            Health.UNAVAILABLE,
            f"tìm thấy {exe} nhưng chưa dựng client ACP (kiro-cli acp) — "
            "xem docstring module")

    def capabilities(self) -> FrozenSet[str]:
        return self.register().capabilities

    def start_session(self, *, workspace: Optional[str] = None) -> bool:
        return False

    def send_task(self, packet: TaskPacket) -> TaskResult:
        kq = TaskResult(
            task_id=packet.task_id, worker_id=self._worker_id,
            status="blocked", provider=self.provider,
            summary="KiroAdapter chưa có client ACP thật — không gọi "
                    "subprocess với cờ chưa xác nhận. Xem docstring module.")
        self._last = kq
        return kq

    def cancel(self) -> None:
        pass

    def result(self) -> Optional[TaskResult]:
        return self._last

    def reset_context(self) -> None:
        pass

    def shutdown(self) -> None:
        pass
