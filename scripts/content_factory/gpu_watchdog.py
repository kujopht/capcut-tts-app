"""Lightning AI L4 GPU Idle Watchdog Daemon.

Monitors GPU activity and automatically stops the L4 GPU Studio if idle for >= 60 seconds.
Runs completely silent in background without any console windows.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Ensure silent execution
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.content_factory.lightning_helper import stop_gpu_worker_studio

TIMESTAMP_FILE = PROJECT_ROOT / "raw_spool" / "gpu_activity.timestamp"
PID_FILE = PROJECT_ROOT / "raw_spool" / "gpu_watchdog.pid"


def get_last_activity() -> float:
    if TIMESTAMP_FILE.exists():
        try:
            return float(TIMESTAMP_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            pass
    return time.time()


def main():
    parser = argparse.ArgumentParser(description="L4 GPU Idle Watchdog")
    parser.add_argument("--delay", type=int, default=60, help="Idle timeout in seconds (default: 60)")
    args = parser.parse_args()

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")

    try:
        while True:
            time.sleep(4)
            last_active = get_last_activity()
            idle_seconds = time.time() - last_active

            if idle_seconds >= args.delay:
                # Idle threshold reached! Stop GPU Studio to prevent credit waste
                stop_gpu_worker_studio()
                break
    finally:
        try:
            if PID_FILE.exists():
                PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
