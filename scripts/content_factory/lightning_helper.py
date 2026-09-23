"""Lightning AI On-Demand Auto-Wake & Lifecycle Manager.

Provides zero-touch auto-start for Lightning AI Studios:
- CPU Studio: 'scratch-studio-devbox' (TTS server on port 8000)
- L4 GPU Studio: 'animation-worker' (Whisper + FFmpeg video rendering on port 8000)

When a worker calls Cloud TTS or GPU Render, if the target Studio is sleeping (Stopped),
this module automatically triggers `Studio.start()`, spins up the background service,
and ensures healthy status before dispatching the payload.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Optional
import requests

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

import json
from typing import Dict, Any

CPU_STUDIO_NAME = "scratch-studio-devbox"
CPU_TTS_URL = "https://8000-01m0aq288xz87ygvxbzhx9pf3w.cloudspaces.litng.ai"

GPU_STUDIO_NAME = "animation-worker"
GPU_WORKER_URL = "https://8000-01m2cvchyakxz65erd7j1vkcna.cloudspaces.litng.ai"


def redact_secret(val: Optional[str]) -> str:
    """Safely redacts secrets for logging, showing only prefix and suffix."""
    if not val:
        return "[EMPTY]"
    s = str(val).strip()
    if len(s) <= 8:
        return "[REDACTED]"
    return f"{s[:3]}...{s[-3:]}"


def _get_keyring_credential() -> Optional[Dict[str, str]]:
    """Attempts to read Lightning AI credentials from Windows Credential Manager."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        advapi32 = ctypes.windll.advapi32

        class _CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        p = ctypes.POINTER(_CREDENTIAL)()
        for target in ("lightning_ai:credentials", "lightning_ai", "lightning:credentials"):
            if advapi32.CredReadW(target, 1, 0, ctypes.byref(p)):
                try:
                    raw = ctypes.string_at(p.contents.CredentialBlob, p.contents.CredentialBlobSize).decode("utf-8")
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        return data
                finally:
                    advapi32.CredFree(p)
    except Exception:
        pass
    return None


def resolve_lightning_credentials() -> Dict[str, str]:
    """Resolves Lightning AI credentials only from approved secure sources.

    Order of priority:
    1. Environment variables (LIGHTNING_API_KEY, LIGHTNING_USER_ID, etc.)
    2. Windows Credential Manager (lightning_ai:credentials)

    Fails closed if credentials are absent. NEVER provides hardcoded fallback credentials.
    """
    api_key = os.environ.get("LIGHTNING_API_KEY")
    user_id = os.environ.get("LIGHTNING_USER_ID")
    user = os.environ.get("LIGHTNING_USER")
    teamspace = os.environ.get("LIGHTNING_TEAMSPACE")

    # If missing from environment, attempt to resolve from Windows Keyring
    if not (api_key and user_id):
        keyring_data = _get_keyring_credential()
        if keyring_data:
            api_key = api_key or keyring_data.get("api_key")
            user_id = user_id or keyring_data.get("user_id")
            user = user or keyring_data.get("user")
            teamspace = teamspace or keyring_data.get("teamspace")

    if not api_key or not user_id:
        raise RuntimeError(
            "Missing required Lightning AI credentials (LIGHTNING_API_KEY and LIGHTNING_USER_ID). "
            "Configure environment variables or store in Windows Credential Manager."
        )

    # Sync to os.environ for SDK consumption
    os.environ["LIGHTNING_API_KEY"] = api_key
    os.environ["LIGHTNING_USER_ID"] = user_id
    if user:
        os.environ["LIGHTNING_USER"] = user
    if teamspace:
        os.environ["LIGHTNING_TEAMSPACE"] = teamspace

    return {
        "api_key": api_key,
        "user_id": user_id,
        "user": user or "",
        "teamspace": teamspace or "",
    }


def is_service_healthy(base_url: str, timeout: float = 3.0) -> bool:
    """Fast check if the studio endpoint responds with 200 OK and piper supported."""
    try:
        r = requests.get(f"{base_url.rstrip('/')}/health", timeout=timeout)
        return r.status_code == 200 and r.json().get("piper_supported", False) is True
    except Exception:
        return False


def ensure_cpu_tts_studio(timeout_seconds: int = 120) -> bool:
    """Ensures the CPU Studio (scratch-studio-devbox) is running and TTS server is ready."""
    if is_service_healthy(CPU_TTS_URL):
        return True

    print(f"[LightningAI] ⏳ CPU Studio TTS server chưa sẵn sàng. Đang kiểm tra & kích hoạt tự động...")
    try:
        creds = resolve_lightning_credentials()
    except Exception as exc:
        print(f"[LightningAI] ❌ Không thể xác thực Lightning AI: {exc}")
        return False

    try:
        from lightning_sdk import Studio
        studio_kwargs = {"name": CPU_STUDIO_NAME}
        if creds.get("teamspace"):
            studio_kwargs["teamspace"] = creds["teamspace"]
        if creds.get("user"):
            studio_kwargs["user"] = creds["user"]
        s = Studio(**studio_kwargs)
        s.show_progress = False

        status_str = str(s.status).lower()
        if "running" not in status_str:
            print(f"[LightningAI] 💤 CPU Studio đang ở trạng thái '{s.status}'. Đang gửi tín hiệu On-Demand Wake-up...")
            s.start()
            print(f"[LightningAI] ⚡ CPU Studio đã khởi động thành công (Status: {s.status})!")

        # Ensure lightning_tts_server.py is running
        check_proc = s.run("pgrep -f 'lightning_tts_server.py' || echo 'NOT_RUNNING'")
        if "NOT_RUNNING" in check_proc:
            print("[LightningAI] 🚀 Khởi chạy lightning_tts_server.py trên CPU Studio...", flush=True)
            s.run_and_detach("python3 /content/lightning_tts_server.py || python3 /teamspace/studios/this_studio/lightning_tts_server.py")
            time.sleep(3)

        # Wait for health endpoint
        t_start = time.time()
        while time.time() - t_start < timeout_seconds:
            if is_service_healthy(CPU_TTS_URL):
                print(f"[LightningAI] ✅ CPU TTS Server đã sẵn sàng phục vụ (port 8000)!")
                return True
            time.sleep(2)

        print(f"[LightningAI] ⚠️ Hết thời gian chờ CPU TTS Server khởi động.")
        return False

    except Exception as exc:
        print(f"[LightningAI] ❌ Lỗi khi tự động đánh thức CPU Studio: {exc}")
        return False


def ensure_gpu_worker_studio(timeout_seconds: int = 180) -> bool:
    """Ensures the L4 GPU Studio (animation-worker) is running and rendering service is ready."""
    if is_service_healthy(GPU_WORKER_URL):
        return True

    print(f"[LightningAI] ⏳ L4 GPU Studio chưa phản hồi. Đang kiểm tra & kích hoạt On-Demand...")
    try:
        creds = resolve_lightning_credentials()
    except Exception as exc:
        print(f"[LightningAI] ❌ Không thể xác thực Lightning AI: {exc}")
        return False

    try:
        from lightning_sdk import Machine, Studio
        studio_kwargs = {"name": GPU_STUDIO_NAME}
        if creds.get("teamspace"):
            studio_kwargs["teamspace"] = creds["teamspace"]
        if creds.get("user"):
            studio_kwargs["user"] = creds["user"]
        s = Studio(**studio_kwargs)
        s.show_progress = False

        status_str = str(s.status).lower()
        if "running" not in status_str:
            print(f"[LightningAI] 💤 T4 GPU Studio đang ở trạng thái '{s.status}'. Đang đánh thức...")
            s.start(machine=Machine.T4)
            print(f"[LightningAI] ⚡ T4 GPU Studio đã khởi động thành công (Status: {s.status})!")
        elif str(s.machine) != str(Machine.T4):
            print(f"[LightningAI] 🔄 Studio đang ở {s.machine}. Đang chuyển sang NVIDIA T4 GPU...")
            s.switch_machine(Machine.T4)
            print(f"[LightningAI] ⚡ Đã chuyển thành công sang NVIDIA T4 GPU!")

        start_gpu_cmd = (
            "pgrep -f 'server.py' || "
            "nohup /home/zeus/miniconda3/envs/cloudspace/bin/python /teamspace/studios/this_studio/server.py "
            "</dev/null >/teamspace/studios/this_studio/server.log 2>&1 &"
        )
        s.run(start_gpu_cmd)

        t_start = time.time()
        while time.time() - t_start < timeout_seconds:
            if is_service_healthy(GPU_WORKER_URL):
                print(f"[LightningAI] ✅ L4 GPU Service (Whisper + Video) đã sẵn sàng!")
                return True
            time.sleep(3)

        print(f"[LightningAI] ⚠️ Hết thời gian chờ L4 GPU Service khởi động.")
        return False

    except Exception as exc:
        print(f"[LightningAI] ❌ Lỗi khi tự động đánh thức GPU Studio: {exc}")
        return False


def stop_gpu_worker_studio() -> bool:
    """Immediately shuts down the L4 GPU Studio to stop billing credits."""
    _configure_credentials()
    try:
        from lightning_sdk import Studio
        s = Studio(
            name=GPU_STUDIO_NAME,
            teamspace=os.environ.get("LIGHTNING_TEAMSPACE", DEFAULT_TEAMSPACE),
            user=os.environ.get("LIGHTNING_USER", DEFAULT_USER),
        )
        if s.status != "Stopped":
            print(f"[LightningAI] 🛑 Đang tắt L4 GPU Studio ({GPU_STUDIO_NAME}) ngay lập tức để ngưng trừ credit...")
            s.stop()
            print(f"[LightningAI] 💤 L4 GPU Studio đã dừng hoàn toàn (Status: Stopped)!")
        return True
    except Exception as exc:
        print(f"[LightningAI] Lỗi khi tắt GPU Studio: {exc}")
        return False


def touch_gpu_activity() -> None:
    """Records active GPU usage timestamp and cancels idle shutdown."""
    try:
        from pathlib import Path
        project_root = Path(__file__).resolve().parents[2]
        ts_file = project_root / "raw_spool" / "gpu_activity.timestamp"
        ts_file.parent.mkdir(parents=True, exist_ok=True)
        ts_file.write_text(str(time.time()), encoding="utf-8")
        print("[LightningAI] ⚡ GPU Activity touched: Kích hoạt/reset bộ đếm giữ ấm GPU!")
    except Exception:
        pass


def schedule_gpu_idle_shutdown(delay_seconds: int = 60) -> None:
    """Schedules automatic L4 GPU Studio shutdown after delay_seconds of inactivity.
    If a new job calls touch_gpu_activity(), the countdown resets automatically."""
    try:
        touch_gpu_activity()
        from pathlib import Path
        import subprocess

        project_root = Path(__file__).resolve().parents[2]
        watchdog_pid_file = project_root / "raw_spool" / "gpu_watchdog.pid"

        # Check if watchdog already running
        if watchdog_pid_file.exists():
            try:
                pid = int(watchdog_pid_file.read_text(encoding="utf-8").strip())
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if h:
                    exit_code = ctypes.c_ulong()
                    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
                    ctypes.windll.kernel32.CloseHandle(h)
                    if exit_code.value == 259: # STILL_ACTIVE
                        # Watchdog is already running and will read the updated timestamp
                        return
            except Exception:
                pass

        # Spawn detached watchdog
        pythonw = project_root / ".venv" / "Scripts" / "pythonw.exe"
        if not pythonw.exists():
            pythonw = Path(sys.executable)

        watchdog_script = project_root / "scripts" / "content_factory" / "gpu_watchdog.py"
        no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        subprocess.Popen(
            [str(pythonw), str(watchdog_script), "--delay", str(delay_seconds)],
            cwd=str(project_root),
            creationflags=no_window,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"[LightningAI] 🕒 Đã kích hoạt bộ đếm giữ ấm GPU ({delay_seconds}s). Nếu không có tập mới, GPU sẽ tự động tắt!")
    except Exception as exc:
        print(f"[LightningAI] Không thể kích hoạt watchdog tắt GPU: {exc}")


