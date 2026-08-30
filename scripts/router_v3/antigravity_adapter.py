"""Adapter Antigravity thật cho hợp đồng `WorkerAdapter` — Router LTS Phase 2.

Bọc lại `WarmAgyWorker` (native, cùng tài khoản Router) và `BridgeClient`
(cross-account, qua cầu nối localhost) — hai thứ ĐÃ được chứng minh thật
(AG01 Phase 7, AG02 Phase 8 của Story Harvester V4, commit b79e0c2/370826f).
Không viết lại logic của chúng — chỉ khoác lên hợp đồng chín phương thức.

GIỚI HẠN THẬT, không che giấu:
- `AntigravityBridgeAdapter.cancel()`: giao thức cầu nối (`bridge.py`) hoàn
  toàn ĐỒNG BỘ — client gửi "run" rồi CHẶN tới khi có kết quả trên CÙNG một
  kết nối. Không có kênh riêng để ngắt giữa chừng. `cancel()` chỉ đánh dấu
  cục bộ để `result()` báo đã huỷ SAU KHI việc từ xa tự xong — nó KHÔNG dừng
  việc đang chạy bên kia. Đây là hạn chế thật của giao thức, không phải lỗi.
"""
from __future__ import annotations

import time
from typing import FrozenSet, Optional

from scripts.router_v3.bridge import BridgeClient
from scripts.router_v3.packet import TaskPacket, TaskResult, parse_result
from scripts.router_v3.registry import ExecutionType, Health, WorkerSpec
from scripts.router_v3.warm_pool import WarmAgyWorker, WarmState, RecyclePolicy
from scripts.router_v3.worker_adapter import HealthReport, TransportKind, WorkerAdapter

_TRANG_THAI_WARM_SANG_HEALTH = {
    WarmState.COLD: Health.UNKNOWN,
    WarmState.WARM_IDLE: Health.HEALTHY,
    WarmState.WARM_BUSY: Health.HEALTHY,
    WarmState.FAILED: Health.FAILED,
}


class AntigravityNativeAdapter(WorkerAdapter):
    """AG01-kiểu: tiến trình `agy` do chính Router sinh ra, cùng tài khoản."""

    provider = "antigravity"
    transport = TransportKind.STRUCTURED_CLI

    def __init__(self, worker_id: str, *, model: str,
                 allow_edits: bool = True,
                 dangerously_skip_permissions: bool = False,
                 turn_timeout: float = 1200.0):
        self._worker_id = worker_id
        self._model = model
        self._allow_edits = allow_edits
        self._dsp = dangerously_skip_permissions
        self._turn_timeout = turn_timeout
        self._worker: Optional[WarmAgyWorker] = None
        self._last: Optional[TaskResult] = None
        self._cancelled = False

    def register(self) -> WorkerSpec:
        return WorkerSpec(
            worker_id=self._worker_id, provider_family=self.provider,
            execution_type=ExecutionType.LOCAL_CLI, pool="GEMINI_FLASH",
            capabilities=frozenset({"recon", "implement", "tests",
                                    "frontend", "review", "challenger"}),
            max_concurrent=1,
            notes="native, cung tai khoan Router")

    def health(self) -> HealthReport:
        if self._worker is None:
            return HealthReport(Health.UNKNOWN, "chưa start_session")
        st = self._worker.state
        return HealthReport(_TRANG_THAI_WARM_SANG_HEALTH.get(st, Health.UNKNOWN),
                            st.value)

    def capabilities(self) -> FrozenSet[str]:
        return self.register().capabilities

    def start_session(self, *, workspace: Optional[str] = None) -> bool:
        if self._worker is not None:
            self.shutdown()
        self._cancelled = False
        self._worker = WarmAgyWorker(
            self._worker_id, model=self._model, workspace=workspace,
            allow_edits=self._allow_edits,
            dangerously_skip_permissions=self._dsp,
            policy=RecyclePolicy(), turn_timeout=self._turn_timeout)
        return self._worker.start()

    def send_task(self, packet: TaskPacket) -> TaskResult:
        if self._worker is None:
            return TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                              status="failed", provider=self.provider,
                              summary="chưa start_session")
        t0 = time.perf_counter()
        t = self._worker.send(packet.render(), family=_ho_viec(packet))
        giay = time.perf_counter() - t0
        if self._cancelled:
            kq = TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                            status="blocked", provider=self.provider,
                            model=self._model, summary="đã huỷ",
                            duration_seconds=round(giay, 2))
        elif not t.ok:
            kq = TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                            status="failed", provider=self.provider,
                            model=self._model, summary=(t.error or "hỏng")[:300],
                            duration_seconds=round(giay, 2))
        else:
            kq = parse_result(packet.task_id, self._worker_id, t.response, giay)
            kq.provider, kq.model = self.provider, self._model
        self._last = kq
        return kq

    def cancel(self) -> None:
        # Cach THAT duy nhat de ngat mot luot dang bay: giet tien trinh. Ket
        # qua cua no thi mat, nhung khong con gi CHAY NGAM sau khi goi xong.
        self._cancelled = True
        if self._worker is not None:
            self._worker.close()

    def result(self) -> Optional[TaskResult]:
        return self._last

    def reset_context(self) -> None:
        if self._worker is not None:
            self._worker.recycle("reset_context thủ công")

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.close()
            self._worker = None


class AntigravityBridgeAdapter(WorkerAdapter):
    """AG02-kiểu: cầu nối localhost tới một phiên `agy` đã xác thực trong
    một hồ sơ Windows KHÁC. Xem `bridge.py` cho ranh giới credential."""

    provider = "antigravity"
    transport = TransportKind.NATIVE_BRIDGE

    def __init__(self, worker_id: str, *, host: str, port: int, token: str,
                model: str = "", timeout: float = 1800.0):
        self._worker_id = worker_id
        self._model = model
        self._client = BridgeClient(port, token, host=host, timeout=timeout)
        self._last: Optional[TaskResult] = None
        self._cancelled = False

    def register(self) -> WorkerSpec:
        return WorkerSpec(
            worker_id=self._worker_id, provider_family=self.provider,
            execution_type=ExecutionType.LOCAL_CLI, pool="GEMINI_FLASH",
            capabilities=frozenset({"recon", "implement", "tests",
                                    "frontend", "review", "challenger"}),
            max_concurrent=1,
            notes="qua cầu nối cross-account, xem bridge.py")

    def health(self) -> HealthReport:
        r = self._client.health()
        if r.get("status") != "ok":
            return HealthReport(Health.UNAVAILABLE, str(r.get("error") or r))
        if not r.get("healthy"):
            return HealthReport(Health.FAILED, r.get("state", ""))
        trang_thai = r.get("state")
        if trang_thai == "warm_busy":
            return HealthReport(Health.HEALTHY, trang_thai)
        return HealthReport(Health.HEALTHY, trang_thai or "healthy")

    def capabilities(self) -> FrozenSet[str]:
        return self.register().capabilities

    def start_session(self, *, workspace: Optional[str] = None) -> bool:
        # Tien trinh am da duoc dung san boi nguoi van hanh AG0x truoc do
        # (run_bridge.py) — workspace da co san qua --add-dir luc do, KHONG
        # doi duoc tu xa. "start_session" o day chi la kiem tra con song.
        self._cancelled = False
        return self.health().state in (Health.HEALTHY,)

    def send_task(self, packet: TaskPacket) -> TaskResult:
        t0 = time.perf_counter()
        r = self._client.run(packet.render(), family=_ho_viec(packet))
        giay = time.perf_counter() - t0
        if self._cancelled:
            kq = TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                            status="blocked", provider=self.provider,
                            model=self._model, summary="đã đánh dấu huỷ cục "
                            "bộ — việc từ xa KHÔNG bị dừng (giao thức đồng bộ)",
                            duration_seconds=round(giay, 2))
        elif r.get("status") != "ok":
            kq = TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                            status="failed", provider=self.provider,
                            model=self._model,
                            summary=(r.get("error") or "lỗi cầu nối")[:300],
                            duration_seconds=round(giay, 2))
        else:
            kq = parse_result(packet.task_id, self._worker_id,
                              r.get("response", ""), giay)
            kq.provider, kq.model = self.provider, self._model
        self._last = kq
        return kq

    def cancel(self) -> None:
        self._cancelled = True

    def result(self) -> Optional[TaskResult]:
        return self._last

    def reset_context(self) -> None:
        # Khong co op "reset" trong giao thuc cau noi hien tai — worker AM
        # phia AG0x tu tai tao theo RecyclePolicy cua chinh no khi doi ho
        # viec. Ghi lai la GIOI HAN THAT, khong gia vo lam duoc.
        pass

    def shutdown(self) -> None:
        # Router khong so huu tien trinh phia AG0x — khong co gi de dong o
        # day. Nguoi van hanh AG0x tu dung bang Ctrl+C tren cua so cua ho.
        pass


def _ho_viec(packet: TaskPacket) -> str:
    duong = list(packet.write_scope) or list(packet.read_scope)
    if not duong:
        return ""
    phan = [p for p in duong[0].replace("\\", "/").strip("/").split("/") if p]
    return "/".join(phan[:2]) if phan else ""
