"""Adapter Grok Build qua CLI headless có cấu trúc — Router LTS Phase 4.

Ban đầu viết khi CHƯA cài `grok` (2026-08-30), chỉ theo tài liệu chính
thức. Đã kiểm chứng THẬT với `grok` 1.0.13 đã cài+đăng nhập (2026-08-30):

    grok -p "<prompt>" --output-format json --always-approve -m <model>
    grok agent stdio          # ACP thật, JSON-RPC qua stdin/stdout

Grok Build công bố ACP THẬT (ưu tiên #1 của `TransportKind`) qua
`grok agent stdio`, nhưng đó là một client JSON-RPC phiên dài (session/
prompt, session/update dạng stream). Module này dùng CLI headless có cấu
trúc (ưu tiên #3) có chủ đích — hình dạng đơn giản hơn, đã chứng minh thật
qua 3 lệnh gọi thật (trinh sát repo, cài đặt thật trong worktree cô lập,
sinh test), không cần kiến trúc JSON-RPC mới cho lần xác thực này. Nâng
lên ACP vẫn là việc CÓ THỂ làm sau, không phải làm lại.

ĐÃ KIỂM CHỨNG THẬT (2026-08-30, không còn là suy đoán):
- Nhị phân thật nằm ở `~/.grok/bin/grok.exe` (thư mục home người dùng),
  KHÔNG phải `%LOCALAPPDATA%\\grok\\bin\\grok.exe` như suy đoán ban đầu —
  `find_grok()` đã sửa để tìm đúng cả hai, ưu tiên vị trí thật.
- Hình dạng JSON thật của `--output-format json`: đối tượng phẳng với khoá
  `text` (câu trả lời), `stopReason`, `sessionId`, `usage`, `total_cost_usd`,
  `modelUsage`, ... — khoá `text` NẰM TRONG danh sách đã đoán ở
  `_rut_van_ban_grok`, nên hàm đó ĐÚNG với API thật mà không cần sửa.
- `--always-approve` xác nhận ghi tệp không tương tác được (task B: sinh
  file thật trong worktree cô lập, không bị chặn xin quyền).
- `--cwd`/`cwd=` (subprocess) đặt đúng thư mục làm việc cho từng worktree —
  KHÔNG có lỗi phạm vi làm việc kiểu OpenCode (`start_session`
  `workspace=` không tự áp `cwd`; adapter dựa vào cwd của
  `subprocess.run`, được set đúng qua `self._workspace`).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import FrozenSet, Optional

from scripts.router_v3.packet import TaskPacket, TaskResult, parse_result
from scripts.router_v3.registry import ExecutionType, Health, WorkerSpec
from scripts.router_v3.worker_adapter import HealthReport, TransportKind, WorkerAdapter

_LOCALAPPDATA = __import__("os").environ.get("LOCALAPPDATA", "")

_UNG_VIEN_GROK = (
    Path.home() / ".grok" / "bin" / "grok.exe",
    Path.home() / ".grok" / "bin" / "grok",
) + ((Path(_LOCALAPPDATA) / "grok" / "bin" / "grok.exe",) if _LOCALAPPDATA else ())


def find_grok() -> Optional[str]:
    tren_path = shutil.which("grok")
    if tren_path:
        return tren_path
    for ung_vien in _UNG_VIEN_GROK:
        if ung_vien.exists():
            return str(ung_vien)
    return None


class GrokBuildAdapter(WorkerAdapter):
    provider = "grok"
    transport = TransportKind.STRUCTURED_CLI

    def __init__(self, worker_id: str, *, model: str = "",
                timeout: float = 1200.0, binary: Optional[str] = None):
        self._worker_id = worker_id
        self._model = model
        self._timeout = timeout
        self._binary = binary
        self._workspace: Optional[str] = None
        self._last: Optional[TaskResult] = None
        self._cancelled = False

    def register(self) -> WorkerSpec:
        return WorkerSpec(
            worker_id=self._worker_id, provider_family=self.provider,
            execution_type=ExecutionType.LOCAL_CLI, pool="GROK",
            capabilities=frozenset({"implement", "tests", "review", "challenger"}),
            max_concurrent=1,
            notes="grok -p --output-format json --always-approve, đã cài+đăng nhập, đã kiểm chứng thật 2026-08-30")

    def health(self) -> HealthReport:
        exe = self._binary or find_grok()
        if not exe:
            return HealthReport(Health.UNAVAILABLE, "không tìm thấy `grok` trên máy này")
        try:
            p = subprocess.run([exe, "models"], capture_output=True, text=True,
                               timeout=15, encoding="utf-8", errors="replace")
        except (subprocess.TimeoutExpired, OSError) as exc:
            return HealthReport(Health.UNAVAILABLE, f"{type(exc).__name__}: {exc}"[:200])
        ra = (p.stdout or "") + (p.stderr or "")
        if p.returncode != 0 or "logged in" not in ra.lower():
            return HealthReport(Health.AUTH_REQUIRED, ra.strip()[:200] or "chưa đăng nhập")
        return HealthReport(Health.HEALTHY, ra.strip().splitlines()[0] if ra.strip() else "healthy")

    def capabilities(self) -> FrozenSet[str]:
        return self.register().capabilities

    def start_session(self, *, workspace: Optional[str] = None) -> bool:
        exe = self._binary or find_grok()
        if not exe:
            return False
        self._workspace = workspace
        self._cancelled = False
        return True

    def send_task(self, packet: TaskPacket) -> TaskResult:
        exe = self._binary or find_grok()
        if not exe:
            return TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                              status="failed", provider=self.provider,
                              summary="không tìm thấy `grok`")
        argv = [exe, "-p", packet.render(), "--output-format", "json",
               "--always-approve"]
        if self._model:
            argv += ["-m", self._model]

        t0 = time.perf_counter()
        try:
            p = subprocess.run(argv, capture_output=True, text=True,
                               timeout=self._timeout + 30, cwd=self._workspace,
                               encoding="utf-8", errors="replace")
            giay = time.perf_counter() - t0
        except subprocess.TimeoutExpired:
            giay = time.perf_counter() - t0
            kq = TaskResult(task_id=packet.task_id, worker_id=self._worker_id,
                            status="timeout", provider=self.provider,
                            model=self._model, summary=f"vượt {self._timeout}s",
                            duration_seconds=round(giay, 2))
            self._last = kq
            return kq
        except OSError as exc:
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
            van_ban = _rut_van_ban_grok((p.stdout or "").strip())
            kq = parse_result(packet.task_id, self._worker_id, van_ban, giay)
            kq.provider, kq.model = self.provider, self._model
        self._last = kq
        return kq

    def cancel(self) -> None:
        # `grok -p` la mot lan goi subprocess.run CHAN — khong co tay cam de
        # ngat giua chung tu luong khac qua API nay. Danh dau cuc bo, giong
        # ranh gioi da ghi cho AntigravityBridgeAdapter/OpenCodeAdapter.
        self._cancelled = True

    def result(self) -> Optional[TaskResult]:
        return self._last

    def reset_context(self) -> None:
        # Moi loi goi la mot tien trinh MOI (khong co phien am duoc giu) —
        # khong co ngu canh nao de bo ca.
        pass

    def shutdown(self) -> None:
        pass


def _rut_van_ban_grok(stdout_tho: str) -> str:
    """Suy đoán hình dạng `--output-format json` — CHƯA kiểm chứng với
    `grok` thật. Trả rỗng thay vì đoán bừa khi không nhận ra hình dạng."""
    if not stdout_tho:
        return ""
    try:
        d = json.loads(stdout_tho)
    except json.JSONDecodeError:
        return stdout_tho          # co the ban than no da la van ban thuan
    if not isinstance(d, dict):
        return ""
    for khoa in ("result", "text", "response", "content"):
        if isinstance(d.get(khoa), str):
            return d[khoa]
    return ""
