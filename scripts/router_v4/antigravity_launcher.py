"""Bọc launcher đa-tài-khoản Antigravity CÓ SẴN — Router V4.

KHÔNG phải một bộ quản lý tài khoản thứ hai. Bộ quản lý là
`C:\\Users\\nguye\\agy-profiles\\agy_profile.py` do người vận hành tạo; module
này chỉ **gọi** nó và bọc kết quả vào hợp đồng `WorkerAdapter`.

    AG01 -> acc1 ... AG08 -> acc8

Router **không bao giờ** tự CredRead/CredWrite. Nó chạy
`agy_profile.py switch accN` rồi sinh `agy.exe` với `USERPROFILE`/`HOME` trỏ
vào `.agy-sessions/accN`. Toàn bộ việc chạm credential nằm trong launcher.

--------------------------------------------------------------------------
BẰNG CHỨNG ĐO ĐƯỢC (2026-09-03) — vì sao module này trông như thế này
--------------------------------------------------------------------------

Cơ chế: **MỘT** khoá Windows Credential Manager (`gemini:antigravity`) được
ghi đè trước mỗi lần khởi động. `.agy-sessions/accN` chỉ cô lập
`USERPROFILE`/`HOME` (chat/cache/SQLite), **không** cô lập credential.

Đo được:

1. **Tiến trình đọc credential MỘT LẦN lúc khởi động, không đọc lại.**
   Xoá hẳn credential khỏi Windows rồi bảo hai tiến trình đang chạy làm
   việc → **cả hai vẫn làm được**. Token nằm trong bộ nhớ tiến trình.
2. **8/8 danh tính chạy đồng thời thật.** Khởi động lần lượt acc1..acc8,
   giữ cả 8 sống, rồi cho cả 8 gọi model **sau khi** slot đã bị ghi đè 7
   lần → 8/8 trả lời đúng, 0 trôi danh tính.
3. **Khởi động lại một tiến trình không ảnh hưởng tiến trình khác.**
4. **NHƯNG: `agy` GHI NGƯỢC token đã làm mới vào slot dùng chung.** Lặp lại
   được: acc1 (token cũ ~3.5h) khởi động → slot **không còn khớp**
   `acc1.bin`; acc8 (token mới) khởi động → slot không đổi.

Hệ quả của (4), và đó là lý do có `KhoaLauncher` dưới đây:

    Chuỗi "switch accN → sinh tiến trình" **PHẢI nguyên tử**.

Nếu hai luồng đan nhau (`switch acc1`, `switch acc2`, spawn, spawn) thì
**cả hai** tiến trình đọc được acc2 — hai worker mang cùng một danh tính mà
sổ đăng ký vẫn tưởng là hai tài khoản. Và vì bất kỳ tiến trình ĐANG CHẠY
nào cũng có thể làm mới token rồi ghi vào slot, cửa sổ rủi ro không chỉ nằm
giữa hai lệnh switch. Khoá được giữ cho tới khi tiến trình con phát ra
`init` — mốc chứng minh nó đã đọc xong credential.

Đây là khoá **liên tiến trình** (tệp khoá trên đĩa), không phải
`threading.Lock`: nhiều tiến trình Router có thể cùng chạy trên một máy.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional

from scripts.router_v3.packet import TaskPacket, TaskResult, parse_result
from scripts.router_v3.registry import ExecutionType, Health, WorkerSpec
from scripts.router_v3.warm_pool import RecyclePolicy, WarmAgyWorker, WarmState
from scripts.router_v3.worker_adapter import (HealthReport, TransportKind,
                                              WorkerAdapter)

#: Bo quan ly tai khoan CO SAN. Router goi nó, khong thay the nó.
LAUNCHER = Path(r"C:\Users\nguye\agy-profiles\agy_profile.py")
PROFILES_DIR = Path(r"C:\Users\nguye\agy-profiles\saved_profiles")
SESSIONS_DIR = Path(r"C:\Users\nguye\.agy-sessions")

#: AG01..AG08 -> acc1..acc8. Anh xa CO DINH, khong bao gio xoay.
ACC_CUA_RUNTIME: Dict[str, str] = {f"AG{i:02d}": f"acc{i}" for i in range(1, 9)}

#: Bao lau moi coi mot khoa la BO HOANG (chu so huu chet giua chung).
#: Phai LON HON thoi gian khoi dong nguoi agy do duoc (~5-12s) cong bien an
#: toan; nho hon se cuop khoa cua mot lan khoi dong binh thuong.
KHOA_TTL = 120.0


def duong_khoa() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or ".")
    return base / "FanficAudioStudio" / "router" / "agy_switch.lock"


class KhoaLauncher:
    """Khoá LIÊN TIẾN TRÌNH quanh chuỗi `switch → spawn`.

    Dùng `O_CREAT|O_EXCL` — nguyên tử ở mức hệ điều hành. Không dùng
    `msvcrt.locking` vì nó gắn với handle của tiến trình và khó dò khoá bỏ
    hoang; ở đây một khoá bỏ hoang phải **tự** hết hiệu lực, vì tiến trình
    giữ nó có thể đã bị `taskkill`.
    """

    def __init__(self, path: Optional[Path] = None, ttl: float = KHOA_TTL):
        self.path = Path(path) if path else duong_khoa()
        self.ttl = ttl
        self._fd: Optional[int] = None

    def _cu_qua(self) -> bool:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            return (time.time() - float(d.get("at") or 0)) > self.ttl
        except (OSError, ValueError, json.JSONDecodeError):
            # Khoa hong/doc khong duoc -> coi la bo hoang. Giu mot khoa
            # khong doc duoc mai mai se treo ca be worker.
            return True

    def acquire(self, *, timeout: float = 180.0, poll: float = 0.25) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        het = time.time() + timeout
        while time.time() < het:
            try:
                fd = os.open(str(self.path),
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._cu_qua():
                    # Doi chu: xoa roi thu lai. Neu hai ben cung xoa thi chi
                    # mot ben tao duoc o vong sau — `O_EXCL` lo phan do.
                    try:
                        self.path.unlink()
                    except OSError:
                        pass
                time.sleep(poll)
                continue
            except OSError:
                time.sleep(poll)
                continue
            os.write(fd, json.dumps({"pid": os.getpid(),
                                     "at": time.time()}).encode("utf-8"))
            self._fd = fd
            return True
        return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        try:
            self.path.unlink()
        except OSError:
            pass

    def __enter__(self) -> "KhoaLauncher":
        if not self.acquire():
            raise TimeoutError(
                f"không giành được khoá launcher trong 180s ({self.path}). "
                f"Một lần `switch → spawn` khác đang giữ, hoặc khoá bỏ hoang "
                f"chưa hết TTL {self.ttl:.0f}s.")
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def acc_cua(runtime_id: str) -> Optional[str]:
    return ACC_CUA_RUNTIME.get(runtime_id)


def profile_ton_tai(acc: str) -> bool:
    return (PROFILES_DIR / f"{acc}.bin").is_file()


def cac_acc_da_luu() -> List[str]:
    """Tài khoản launcher ĐÃ lưu, theo đĩa — không theo lời khai."""
    return sorted((p.stem for p in PROFILES_DIR.glob("*.bin")),
                  key=lambda s: (len(s), s))


def switch(acc: str, *, timeout: float = 60.0) -> tuple[bool, str]:
    """Gọi launcher CÓ SẴN để nạp credential của `acc`.

    Router **không** tự CredWrite. Nếu launcher vắng mặt thì thất bại rõ
    ràng thay vì lặng lẽ rơi về tự chạm credential.
    """
    if not LAUNCHER.is_file():
        return False, f"không tìm thấy launcher {LAUNCHER}"
    try:
        p = subprocess.run([sys.executable, str(LAUNCHER), "switch", acc],
                           capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{type(exc).__name__}: {exc}"[:200]
    ra = ((p.stdout or "") + (p.stderr or "")).strip()
    # Launcher in "[+] Da nap token cho [accN] thanh cong!" khi duoc.
    ok = p.returncode == 0 and "[-]" not in ra
    return ok, ra[-200:]


class AntigravityLauncherAdapter(WorkerAdapter):
    """Một danh tính Antigravity chạy qua launcher đa-tài-khoản.

    `cancel()` giết tiến trình con — cách huỷ THẬT duy nhất ở đây; kết quả
    lượt đang chạy bị mất, và điều đó được ghi rõ chứ không giả vờ huỷ mềm.

    **KHÔNG BAO GIỜ** `--dangerously-skip-permissions`. Việc có ghi dùng
    `--mode accept-edits` + `--add-dir <worktree>`; việc chỉ đọc không xin
    quyền gì.
    """

    provider = "antigravity"
    transport = TransportKind.STRUCTURED_CLI

    def __init__(self, runtime_id: str, *, model: str,
                 turn_timeout: float = 1200.0,
                 khoa: Optional[KhoaLauncher] = None):
        self._runtime_id = runtime_id
        self._acc = acc_cua(runtime_id) or runtime_id
        self._model = model
        self._turn_timeout = turn_timeout
        self._khoa = khoa or KhoaLauncher()
        self._worker: Optional[WarmAgyWorker] = None
        self._last: Optional[TaskResult] = None
        self._cancelled = False
        self._cho_ghi = False

    # -- hop dong chin phuong thuc -----------------------------------------

    def register(self) -> WorkerSpec:
        return WorkerSpec(
            worker_id=self._runtime_id, provider_family=self.provider,
            execution_type=ExecutionType.LOCAL_CLI, pool="ANTIGRAVITY",
            capabilities=frozenset({"recon", "implement", "tests", "frontend",
                                    "review", "integration"}),
            max_concurrent=1, model=self._model,
            auth_realm=f"agy-launcher:{self._acc}",
            workspace=str(SESSIONS_DIR / self._acc),
            notes=f"launcher da-tai-khoan, profile {self._acc}")

    def health(self) -> HealthReport:
        if not LAUNCHER.is_file():
            return HealthReport(Health.UNAVAILABLE,
                                f"thiếu launcher {LAUNCHER.name}")
        if not profile_ton_tai(self._acc):
            return HealthReport(
                Health.AUTH_REQUIRED,
                f"chưa lưu profile {self._acc} — chạy `acc login "
                f"{self._acc[3:]}` một lần")
        if self._worker is not None:
            st = self._worker.state
            if st is WarmState.FAILED:
                return HealthReport(Health.FAILED, st.value)
            return HealthReport(Health.HEALTHY, st.value)
        return HealthReport(Health.HEALTHY, f"profile {self._acc} đã lưu")

    def capabilities(self) -> FrozenSet[str]:
        return self.register().capabilities

    def set_write_mode(self, cho_ghi: bool) -> None:
        self._cho_ghi = bool(cho_ghi)

    def start_session(self, *, workspace: Optional[str] = None) -> bool:
        """Nạp đúng credential rồi sinh tiến trình — DƯỚI MỘT KHOÁ.

        Khoá được giữ cho tới khi tiến trình con phát ra `init`, tức là nó
        đã đọc xong credential. Nhả sớm hơn sẽ để một lần `switch` khác ghi
        đè slot trước khi tiến trình này kịp đọc, và cả hai worker sẽ mang
        cùng một danh tính — xem docstring module, bằng chứng (4).
        """
        if not profile_ton_tai(self._acc):
            return False
        if self._worker is not None:
            self.shutdown()
        self._cancelled = False

        sess = SESSIONS_DIR / self._acc
        sess.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["USERPROFILE"] = str(sess)
        env["HOME"] = str(sess)

        try:
            with self._khoa:
                ok, chi_tiet = switch(self._acc)
                if not ok:
                    return False
                self._worker = WarmAgyWorker(
                    self._runtime_id, model=self._model,
                    workspace=workspace, cwd=workspace or str(sess),
                    allow_edits=bool(workspace) and self._cho_ghi,
                    dangerously_skip_permissions=False,
                    policy=RecyclePolicy(), turn_timeout=self._turn_timeout,
                    env=env)
                # `start()` cho tin `init` -> khoa duoc giu dung tron cua so
                # nguy hiem, khong hon.
                return self._worker.start()
        except TimeoutError:
            return False

    def send_task(self, packet: TaskPacket) -> TaskResult:
        if self._worker is None:
            return TaskResult(task_id=packet.task_id,
                              worker_id=self._runtime_id, status="failed",
                              provider=self.provider, model=self._model,
                              failure_reason="no_session",
                              summary="chưa start_session")
        t0 = time.perf_counter()
        t = self._worker.send(packet.render(), family=self._acc)
        giay = time.perf_counter() - t0
        if self._cancelled:
            kq = TaskResult(task_id=packet.task_id, worker_id=self._runtime_id,
                            status="cancelled", provider=self.provider,
                            model=self._model, failure_reason="cancelled",
                            summary="đã huỷ", duration_seconds=round(giay, 2))
        elif not t.ok:
            kq = TaskResult(task_id=packet.task_id, worker_id=self._runtime_id,
                            status="failed", provider=self.provider,
                            model=self._model, failure_reason="turn_failed",
                            summary=(t.error or "hỏng")[:300],
                            duration_seconds=round(giay, 2))
        else:
            kq = parse_result(packet.task_id, self._runtime_id, t.response, giay)
            kq.provider, kq.model = self.provider, self._model
        self._last = kq
        return kq

    def cancel(self) -> None:
        self._cancelled = True
        if self._worker is not None:
            self._worker.close()

    def result(self) -> Optional[TaskResult]:
        return self._last

    def reset_context(self) -> None:
        # Tai tao = khoi dong lai tien trinh, nen no PHAI di qua lai khoa
        # switch: mot lan khoi dong lai cung doc credential tu slot dung chung.
        if self._worker is not None:
            ws = self._worker._workspace
            self.start_session(workspace=ws)

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.close()
            self._worker = None


def runtimes_kha_dung() -> Dict[str, str]:
    """`{runtime_id: acc}` cho mọi khe CÓ profile đã lưu trên đĩa.

    Đọc ĐĨA, không đọc cấu hình: một khe chỉ được coi là cấp phát khi
    `saved_profiles/accN.bin` thật sự tồn tại.
    """
    return {rid: acc for rid, acc in ACC_CUA_RUNTIME.items()
            if profile_ton_tai(acc)}
