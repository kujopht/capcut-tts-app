"""Bể worker ẤM — Router V3.2, Phase 1 + 2 + 3.

VÌ SAO: đo được (10 việc nhỏ, 10/10 thành công cả hai cách) —

    sinh một tiến trình `agy` cho MỖI việc : 59.10s  (5.91s/việc, 77% overhead)
    MỘT tiến trình ấm cho cả lô            : 16.31s  (1.63s/việc)
    => nhanh hơn 3.62 lần

Khoản đó LỚN HƠN cả song song hoá (2.19x ở 6 worker) và hai thứ cộng dồn được.

TIẾN TRÌNH ẤM ≠ HỘI THOẠI VÔ HẠN. Mỗi lượt trong một tiến trình ấm dùng chung
một hội thoại, nên ngữ cảnh tích luỹ. Với các việc **liên quan** đó là điều
tốt (worker đã đọc module rồi thì sửa nó rẻ hơn). Với các việc **không liên
quan** đó là token lãng phí và là đường để nhiễu chéo. `WarmSession` vì thế
theo dõi họ việc, số lượt và độ phình ngữ cảnh, rồi TÁI TẠO khi vượt ngưỡng.

RANH GIỚI CREDENTIAL: `agy` tự giữ phiên đăng nhập trong hồ sơ người dùng của
nó. Lớp này chỉ ghi/đọc ống stdin/stdout của một tiến trình con — không đọc
token, không sao chép keyring, không xoay tài khoản.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from queue import Empty, Queue
from typing import Callable, List, Optional

from scripts.router_v3.native_worker import find_agy


class WarmState(str, Enum):
    COLD = "cold"                # chua khoi dong
    WARM_IDLE = "warm_idle"      # tien trinh song, khong lam gi
    WARM_BUSY = "warm_busy"
    FAILED = "failed"            # tien trinh chet / khong dung duoc


@dataclass
class WarmTurn:
    ok: bool = False
    response: str = ""
    error: str = ""
    seconds: float = 0.0


@dataclass
class SessionStats:
    """Đủ để quyết định khi nào tái tạo. KHÔNG chứa nội dung việc."""

    turns: int = 0
    #: Xấp xỉ độ phình ngữ cảnh bằng ký tự đã trao đổi. Đây là số ĐO ĐƯỢC
    #: cục bộ; `agy` không phát ra token count cho từng lượt ở chế độ stream.
    chars: int = 0
    family: str = ""
    started_at: float = field(default_factory=time.perf_counter)
    failures: int = 0

    @property
    def age_seconds(self) -> float:
        return round(time.perf_counter() - self.started_at, 2)


@dataclass(frozen=True)
class RecyclePolicy:
    """Khi nào bỏ hội thoại cũ và bắt đầu lại.

    Mặc định thận trọng: giữ ấm trong một mạch việc, cắt khi đổi mạch. Ngưỡng
    ký tự cố ý thấp hơn nhiều so với cửa sổ ngữ cảnh thật — mục đích không
    phải tránh tràn mà là tránh **kéo lê** ngữ cảnh không liên quan qua các
    lượt sau, thứ vừa tốn token vừa làm nhiễu.
    """

    max_turns: int = 8
    max_chars: int = 60_000
    max_age_seconds: float = 900.0
    max_failures: int = 2

    def should_recycle(self, s: SessionStats, family: str) -> Optional[str]:
        """Trả về LÝ DO nếu cần tái tạo, `None` nếu còn dùng được."""
        if s.turns and family and s.family and family != s.family:
            return f"đổi họ việc: {s.family!r} -> {family!r}"
        if s.turns >= self.max_turns:
            return f"đủ {s.turns} lượt (trần {self.max_turns})"
        if s.chars >= self.max_chars:
            return f"ngữ cảnh ~{s.chars} ký tự (trần {self.max_chars})"
        if s.age_seconds >= self.max_age_seconds:
            return f"phiên già {s.age_seconds:.0f}s (trần {self.max_age_seconds:.0f}s)"
        if s.failures >= self.max_failures:
            return f"{s.failures} lần hỏng liên tiếp"
        return None


def _ban_tin(prompt: str) -> bytes:
    """Bản tin NDJSON cho `--input-format stream-json`.

    PHẢI có `event` (không phải `type`) và, với `event="user"`, phải có
    `message`. Đã dò từng dạng: `"type"` bị từ chối với lỗi rõ ràng.
    """
    return (json.dumps({"event": "user",
                        "message": {"role": "user", "content": prompt}})
            + "\n").encode("utf-8")


class WarmAgyWorker:
    """Một tiến trình `agy` sống lâu, nhận nhiều lượt.

    Ống được mở ở chế độ NHỊ PHÂN và tự mã hoá UTF-8. Dùng `text=True` kèm
    `bufsize=1` trên Windows làm lần ghi stdin thứ hai hỏng với
    `OSError: [Errno 22] Invalid argument` — đã vấp thật, và đó là lý do
    phép đo worker ấm đầu tiên không chạy được.
    """

    def __init__(self, worker_id: str, *, model: str,
                 cwd: Optional[str] = None, workspace: Optional[str] = None,
                 allow_edits: bool = False,
                 dangerously_skip_permissions: bool = False,
                 policy: Optional[RecyclePolicy] = None,
                 binary: Optional[str] = None,
                 turn_timeout: float = 240.0):
        """
        :param dangerously_skip_permissions: bật `--dangerously-skip-permissions`.
            MẶC ĐỊNH TẮT — nó tự duyệt MỌI quyền, gồm cả chạy lệnh shell, rộng
            hơn hẳn `accept-edits` (chỉ ghi tệp). Chỉ bật khi việc chạy trong
            một worktree cô lập, có `write_scope`/`DO_NOT_TOUCH` và
            `verify_scope()` chặn sau — xem CLAUDE.md mục "Known real CLI
            quirks". Bằng chứng thật (2026-08-30): một mô hình chọn công cụ
            lệnh-shell để tạo MỘT tệp thay vì công cụ ghi tệp; `accept-edits`
            không phủ trường hợp đó, chỉ `--dangerously-skip-permissions` mới.
        """
        self.worker_id = worker_id
        self._model = model
        self._cwd = cwd
        self._workspace = workspace
        self._allow_edits = allow_edits
        self._dangerously_skip_permissions = dangerously_skip_permissions
        self._policy = policy or RecyclePolicy()
        self._binary = binary
        self._turn_timeout = turn_timeout

        self._p: Optional[subprocess.Popen] = None
        self._q: "Queue[str]" = Queue()
        # Truoc ban sua nay stderr cua agy khong ai doc: PIPE ma khong drain
        # nghia la mot loi tu choi quyen/permission bi NUOT im lang, va ca
        # nguoi van hanh lan Router deu khong thay duoc VI SAO mot luot tra
        # ve rong. Giu 200 dong cuoi — du de chan doan, khong giu ca output.
        self._stderr_tail: List[str] = []
        self._state = WarmState.COLD
        self.stats = SessionStats()
        self.cold_starts = 0
        self.cold_start_seconds = 0.0
        self.recycles: List[str] = []

    # -- vong doi -----------------------------------------------------------

    @property
    def state(self) -> WarmState:
        if self._p is not None and self._p.poll() is not None:
            # Tien trinh da chet ma khong ai bao — coi la hong, khong phai ranh.
            self._state = WarmState.FAILED
        return self._state

    def start(self) -> bool:
        exe = self._binary or find_agy()
        if not exe:
            self._state = WarmState.FAILED
            return False
        argv = [exe, "--model", self._model,
                "--input-format", "stream-json",
                "--output-format", "stream-json",
                "--print-timeout", f"{int(self._turn_timeout * 4)}s"]
        if self._workspace:
            argv += ["--add-dir", str(self._workspace)]
        if self._allow_edits:
            argv += ["--mode", "accept-edits"]
        if self._dangerously_skip_permissions:
            argv += ["--dangerously-skip-permissions"]

        t0 = time.perf_counter()
        try:
            self._p = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=self._cwd, bufsize=0)
        except OSError as exc:
            self._state = WarmState.FAILED
            return False
        self._stderr_tail = []
        threading.Thread(target=self._doc_stdout, daemon=True).start()
        threading.Thread(target=self._doc_stderr, daemon=True).start()
        d = self._cho("init", timeout=self._turn_timeout)
        self.cold_start_seconds += time.perf_counter() - t0
        self.cold_starts += 1
        if d is None:
            self._state = WarmState.FAILED
            return False
        self._state = WarmState.WARM_IDLE
        self.stats = SessionStats()
        return True

    def _doc_stdout(self) -> None:
        p = self._p
        if p is None or p.stdout is None:
            return
        for raw in iter(p.stdout.readline, b""):
            try:
                self._q.put(raw.decode("utf-8", "replace").strip())
            except Exception:
                break

    def _doc_stderr(self) -> None:
        p = self._p
        if p is None or p.stderr is None:
            return
        for raw in iter(p.stderr.readline, b""):
            try:
                dong = raw.decode("utf-8", "replace").rstrip()
            except Exception:
                break
            if not dong:
                continue
            self._stderr_tail.append(dong)
            del self._stderr_tail[:-200]

    @property
    def stderr_tail(self) -> str:
        """200 dong stderr GẦN NHẤT của `agy` — để chẩn đoán khi một lượt trả
        về "ok" nhưng rỗng/vô lý. Không phải log toàn bộ, chỉ đủ để thấy một
        lời từ chối quyền hay một traceback."""
        return "\n".join(self._stderr_tail[-200:])

    def _cho(self, event: str, timeout: float):
        het = time.time() + timeout
        while time.time() < het:
            try:
                dong = self._q.get(timeout=0.5)
            except Empty:
                if self._p is not None and self._p.poll() is not None:
                    return None          # tien trinh chet -> khong cho vo ich
                continue
            if not dong.startswith("{"):
                continue
            try:
                o = json.loads(dong)
            except json.JSONDecodeError:
                continue
            if o.get("event") == event:
                return o
        return None

    def close(self) -> None:
        p, self._p = self._p, None
        self._state = WarmState.COLD
        if p is None:
            return
        try:
            if p.stdin:
                p.stdin.close()
            p.wait(timeout=15)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass

    def recycle(self, reason: str) -> bool:
        """Bỏ hội thoại cũ, bắt đầu lại sạch.

        `agy` không có cách xoá hội thoại giữa chừng qua stdin ở chế độ này,
        nên tái tạo = khởi động lại tiến trình. Chi phí đúng bằng một lần khởi
        động lạnh (đo được ~4s) — vẫn rẻ hơn nhiều so với kéo lê ngữ cảnh
        không liên quan qua mọi lượt còn lại.
        """
        self.recycles.append(reason)
        self.close()
        return self.start()

    # -- chay mot luot ------------------------------------------------------

    def send(self, prompt: str, *, family: str = "") -> WarmTurn:
        ly_do = self._policy.should_recycle(self.stats, family)
        if ly_do and self.state is not WarmState.COLD:
            if not self.recycle(ly_do):
                return WarmTurn(ok=False, error=f"tái tạo hỏng sau: {ly_do}")
        if self.state in (WarmState.COLD, WarmState.FAILED):
            if not self.start():
                return WarmTurn(ok=False, error="không khởi động được worker")

        self._state = WarmState.WARM_BUSY
        t0 = time.perf_counter()
        try:
            assert self._p is not None and self._p.stdin is not None
            self._p.stdin.write(_ban_tin(prompt))
            self._p.stdin.flush()
        except (OSError, AssertionError) as exc:
            self._state = WarmState.FAILED
            self.stats.failures += 1
            return WarmTurn(ok=False, seconds=time.perf_counter() - t0,
                            error=f"ghi stdin hỏng: {type(exc).__name__}")

        o = self._cho("result", timeout=self._turn_timeout)
        giay = time.perf_counter() - t0
        if o is None:
            self._state = WarmState.FAILED
            self.stats.failures += 1
            return WarmTurn(ok=False, seconds=giay,
                            error="không nhận được kết quả (hết giờ/chết)")

        r = o.get("result") or {}
        ok = str(r.get("status") or "").upper() == "SUCCESS"
        resp = str(r.get("response") or "")
        self.stats.turns += 1
        self.stats.chars += len(prompt) + len(resp)
        if family:
            self.stats.family = family
        self.stats.failures = 0 if ok else self.stats.failures + 1
        self._state = WarmState.WARM_IDLE
        return WarmTurn(ok=ok, response=resp, seconds=giay,
                        error="" if ok else str(r.get("error") or "ERROR"))


class WarmPool:
    """Vài worker ấm, chọn theo trạng thái.

    Thứ tự ưu tiên (Phase 3): WARM-IDLE hợp lệ > worker có thể làm ấm >
    sinh lạnh. Nhưng "đang ấm" KHÔNG bao giờ thắng "hợp năng lực": chọn một
    worker ấm sai việc chỉ để tiết kiệm 4 giây khởi động là đổi sai lấy nhanh.
    """

    def __init__(self, workers: Optional[List[WarmAgyWorker]] = None):
        self._w: List[WarmAgyWorker] = list(workers or [])

    def add(self, w: WarmAgyWorker) -> None:
        self._w.append(w)

    def all(self) -> List[WarmAgyWorker]:
        return list(self._w)

    def pick(self, *, family: str = "") -> Optional[WarmAgyWorker]:
        # 1) dang AM va KHONG phai tai tao (cung ho viec)
        for w in self._w:
            if w.state is WarmState.WARM_IDLE and not w._policy.should_recycle(
                    w.stats, family):
                return w
        # 2) dang AM nhung phai tai tao — van re hon mot worker lanh chua chay
        for w in self._w:
            if w.state is WarmState.WARM_IDLE:
                return w
        # 3) lanh
        for w in self._w:
            if w.state is WarmState.COLD:
                return w
        return None

    def snapshot(self) -> List[dict]:
        ra = []
        for w in self._w:
            ra.append({
                "worker_id": w.worker_id,
                "state": w.state.value,
                "turns": w.stats.turns,
                "context_chars": w.stats.chars,
                "family": w.stats.family,
                "age_s": w.stats.age_seconds,
                "cold_starts": w.cold_starts,
                "recycles": len(w.recycles),
            })
        return ra

    def close(self) -> None:
        for w in self._w:
            w.close()
