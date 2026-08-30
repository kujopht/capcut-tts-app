"""Adapter OpenCode qua HTTP server chính thức — Router LTS Phase 3.

KHÔNG cài trên máy này lúc viết module này (2026-08-30) — `health()` vì
thế sẽ báo `UNAVAILABLE` THẬT, không phải giả định. Module viết theo tài
liệu chính thức (opencode.ai/docs/server, tra cứu trực tiếp lúc viết):

    opencode serve [--port 4096] [--hostname 127.0.0.1]
    GET  /global/health          -> {"healthy": bool, "version": str}
    POST /session                -> tạo phiên {parentID?, title?}
    GET  /session/:id            -> chi tiết phiên
    POST /session/:id/message    -> gửi tin nhắn, CHỜ phản hồi
    GET  /provider               -> danh sách provider + trạng thái kết nối

Đây là lựa chọn ưu tiên #2 trong `TransportKind` (HTTP/OpenAPI thường trực)
— OpenCode không công bố ACP tại thời điểm viết, nên HTTP server chính
thức là chuẩn ổn định nhất sẵn có, đúng thứ tự ưu tiên của Phase 2.

GIỚI HẠN CHƯA KIỂM CHỨNG ĐƯỢC (không có server thật để thử):
- Hình dạng CHÍNH XÁC của phần thân phản hồi `POST /session/:id/message`
  (đoạn text cuối cùng nằm ở trường nào) suy từ tài liệu, chưa chạy thật.
- Không có endpoint xoá phiên được xác nhận trong tài liệu đã tra —
  `shutdown()` vì thế chỉ dọn tham chiếu cục bộ, KHÔNG xoá phiên phía xa.
- `start_session(workspace=...)` không đổi được thư mục làm việc của một
  `opencode serve` ĐANG CHẠY — y hệt giới hạn cầu nối AG02 (workspace cố
  định lúc server khởi động, không đổi được theo từng việc).
Ghi rõ ở đây để lần tích hợp thật đầu tiên biết chính xác cái gì cần xác
minh lại, thay vì phải đọc lại toàn bộ mã nguồn.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import FrozenSet, Optional

from scripts.router_v3.packet import TaskPacket, TaskResult, parse_result
from scripts.router_v3.registry import ExecutionType, Health, WorkerSpec
from scripts.router_v3.worker_adapter import HealthReport, TransportKind, WorkerAdapter

MAC_DINH_PORT = 4096
HET_GIO_NGAN = 3.0    # kiem tra con song — that bai phai NHANH, khong treo


class OpenCodeAdapter(WorkerAdapter):
    provider = "opencode"
    transport = TransportKind.HTTP_SERVER

    def __init__(self, worker_id: str, *, host: str = "127.0.0.1",
                port: int = MAC_DINH_PORT, model: str = "",
                timeout: float = 1200.0):
        self._worker_id = worker_id
        self._base = f"http://{host}:{port}"
        self._model = model
        self._timeout = timeout
        self._session_id: Optional[str] = None
        self._last: Optional[TaskResult] = None
        self._cancelled = False

    def register(self) -> WorkerSpec:
        return WorkerSpec(
            worker_id=self._worker_id, provider_family=self.provider,
            execution_type=ExecutionType.LOCAL_CLI, pool="OPENCODE",
            capabilities=frozenset({"implement", "tests", "recon", "review"}),
            max_concurrent=1,
            notes="opencode serve, HTTP OpenAPI — xem docstring module")

    def _goi(self, method: str, path: str, body: Optional[dict] = None,
             timeout: Optional[float] = None) -> dict:
        du_lieu = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            self._base + path, data=du_lieu, method=method,
            headers={"Content-Type": "application/json"} if du_lieu else {})
        with urllib.request.urlopen(req, timeout=timeout or self._timeout) as r:
            raw = r.read().decode("utf-8", "replace")
        return json.loads(raw) if raw.strip() else {}

    def health(self) -> HealthReport:
        try:
            r = self._goi("GET", "/global/health", timeout=HET_GIO_NGAN)
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
            return HealthReport(Health.UNAVAILABLE,
                                f"opencode serve không chạy trên {self._base}: "
                                f"{type(exc).__name__}")
        except json.JSONDecodeError:
            return HealthReport(Health.UNAVAILABLE, "phản hồi không phải JSON")
        if not r.get("healthy"):
            return HealthReport(Health.FAILED, f"version={r.get('version', '?')}")
        try:
            nha_cc = self._goi("GET", "/provider", timeout=HET_GIO_NGAN)
        except Exception:                                       # noqa: BLE001
            return HealthReport(Health.HEALTHY, f"version={r.get('version', '?')}")
        ds = nha_cc if isinstance(nha_cc, list) else nha_cc.get("providers", [])
        da_xac_thuc = any(
            isinstance(p, dict) and p.get("connected") for p in ds)
        if ds and not da_xac_thuc:
            return HealthReport(Health.AUTH_REQUIRED,
                                "server chạy nhưng chưa provider nào xác thực")
        return HealthReport(Health.HEALTHY, f"version={r.get('version', '?')}")

    def capabilities(self) -> FrozenSet[str]:
        return self.register().capabilities

    def start_session(self, *, workspace: Optional[str] = None) -> bool:
        if self.health().state not in (Health.HEALTHY,):
            return False
        try:
            r = self._goi("POST", "/session", {"title": f"router:{self._worker_id}"},
                          timeout=HET_GIO_NGAN)
        except Exception:                                        # noqa: BLE001
            return False
        sid = r.get("id") or r.get("sessionID")
        if not sid:
            return False
        self._session_id = sid
        self._cancelled = False
        return True

    def send_task(self, packet: TaskPacket) -> TaskResult:
        if not self._session_id:
            return TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                              status="failed", provider=self.provider,
                              summary="chưa start_session")
        t0 = time.perf_counter()
        try:
            r = self._goi("POST", f"/session/{self._session_id}/message",
                          {"parts": [{"type": "text", "text": packet.render()}]})
            giay = time.perf_counter() - t0
        except Exception as exc:                                 # noqa: BLE001
            giay = time.perf_counter() - t0
            kq = TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                            status="failed", provider=self.provider,
                            model=self._model,
                            summary=f"{type(exc).__name__}: {exc}"[:300],
                            duration_seconds=round(giay, 2))
            self._last = kq
            return kq

        if self._cancelled:
            kq = TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                            status="blocked", provider=self.provider,
                            model=self._model, summary="đã huỷ",
                            duration_seconds=round(giay, 2))
        else:
            van_ban = _rut_van_ban(r)
            kq = parse_result(packet.task_id, self._worker_id, van_ban, giay)
            kq.provider, kq.model = self.provider, self._model
        self._last = kq
        return kq

    def cancel(self) -> None:
        # Chua xac nhan endpoint huy trong tai lieu da tra — chi danh dau
        # cuc bo, giong ranh gioi that cua AntigravityBridgeAdapter.
        self._cancelled = True

    def result(self) -> Optional[TaskResult]:
        return self._last

    def reset_context(self) -> None:
        # Phien OpenCode la don vi hoi thoai — "reset" tu nhien nhat la tao
        # phien MOI, bo phien cu (khong xoa duoc no phia xa, xem gioi han
        # trong docstring module).
        self._session_id = None

    def shutdown(self) -> None:
        self._session_id = None


def _rut_van_ban(phan_hoi: dict) -> str:
    """Suy đoán từ tài liệu — CHƯA xác minh với server thật.

    Thử vài hình dạng hợp lý (`parts[].text`, `content`, `text`) trước khi
    trả rỗng — `parse_result` phía Router coi rỗng là "failed", nên rỗng
    không lặng lẽ biến thành "ok" giả.
    """
    if not isinstance(phan_hoi, dict):
        return ""
    for khoa in ("text", "content"):
        if isinstance(phan_hoi.get(khoa), str):
            return phan_hoi[khoa]
    parts = phan_hoi.get("parts")
    if isinstance(parts, list):
        doan = [p.get("text", "") for p in parts
               if isinstance(p, dict) and p.get("type") == "text"]
        if doan:
            return "\n".join(doan)
    tin_nhan = phan_hoi.get("message")
    if isinstance(tin_nhan, dict):
        return _rut_van_ban(tin_nhan)
    return ""
