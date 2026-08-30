"""Chạy cầu nối worker AG0x — Router V3.2, Phase 5.

CHẠY LỆNH NÀY TRONG PHIÊN WINDOWS CỦA CHÍNH TÀI KHOẢN ĐÓ, sau khi đã đăng
nhập `agy` một lần bằng tài khoản Google riêng của nó.

    python -m scripts.router_v3.run_bridge --worker-id AG02

Nó in ra CỔNG và TOKEN. Chép hai giá trị đó sang phiên Router chính. Token
này chỉ cho phép **gửi việc** tới cầu nối; nó không mở được gì thuộc về
Google, và Router không bao giờ thấy credential của tài khoản.

Cầu nối chỉ nghe trên 127.0.0.1.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.router_v3.bridge import BridgeConfig, WorkerBridge
from scripts.router_v3.native_worker import find_agy
from scripts.router_v3.warm_pool import RecyclePolicy, WarmAgyWorker


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worker-id", default="AG02")
    ap.add_argument("--model", default="gemini-3.7-flash-low")
    ap.add_argument("--port", type=int, default=0, help="0 = HĐH tự chọn")
    ap.add_argument("--workspace", default="", help="thư mục cho --add-dir")
    ap.add_argument("--allow-edits", action="store_true")
    a = ap.parse_args(argv)

    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    exe = find_agy()
    if not exe:
        print("KHÔNG tìm thấy `agy` trong hồ sơ người dùng này.")
        print("Cài/kiểm tra Antigravity CLI rồi chạy lại.")
        return 2

    worker = WarmAgyWorker(
        a.worker_id, model=a.model,
        workspace=a.workspace or None, allow_edits=a.allow_edits,
        policy=RecyclePolicy())

    print(f"agy      : {exe}")
    print(f"worker   : {a.worker_id}  model={a.model}")
    print("Đang khởi động tiến trình ấm...", flush=True)
    if not worker.start():
        print("KHỞI ĐỘNG HỎNG. Nhiều khả năng tài khoản này CHƯA đăng nhập.")
        print("Chạy `agy` một lần ở chế độ tương tác và đăng nhập, rồi thử lại.")
        return 3
    print(f"tiến trình ấm SẴN SÀNG (khởi động {worker.cold_start_seconds:.2f}s)\n")

    def chay(prompt: str, family: str) -> dict:
        t = worker.send(prompt, family=family)
        return {"ok": t.ok, "response": t.response, "error": t.error,
                "seconds": round(t.seconds, 2), "turns": worker.stats.turns}

    bridge = WorkerBridge(BridgeConfig(worker_id=a.worker_id, port=a.port),
                          chay, health_fn=lambda: worker.state.value != "failed")
    bridge.start()

    print("=" * 58)
    print(f"  CẦU NỐI {a.worker_id} ĐÃ SẴN SÀNG")
    print(f"  cổng  : {bridge.port}")
    print(f"  token : {bridge.token}")
    print("=" * 58)
    print("\nChép CỔNG và TOKEN sang phiên Router chính.")
    print("Cầu nối chỉ nghe trên 127.0.0.1. Ctrl+C để dừng.\n")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nĐang dừng...")
    finally:
        bridge.stop()
        worker.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
