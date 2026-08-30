"""Ghép Router với cầu nối worker đã chạy — Router V3.2, Phase 5.

CHẠY LỆNH NÀY Ở PHÍA ROUTER (phiên chính), sau khi cầu nối đã in ra CỔNG
và TOKEN trong phiên của worker (`run_bridge.py`).

    python -m scripts.router_v3.pair_bridge --worker-id AG02 --port 64689

Token gõ ẨN (getpass) ngay tại đây — không phải đối số dòng lệnh (lộ trong
danh sách tiến trình), không dán vào bất kỳ đâu khác. Việc ghép được XÁC
MINH ngay bằng một lượt gọi "health" thật tới cầu nối trước khi lưu — token
sai thì không lưu gì cả. Không bao giờ in lại token sau khi đã lưu.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from scripts.router_v3.bridge import BridgeClient
from scripts.router_v3.bridge_store import luu


def main(argv=None) -> int:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worker-id", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--timeout", type=float, default=15.0)
    a = ap.parse_args(argv)

    try:
        token = getpass.getpass(f"Token cho cầu nối {a.worker_id} (gõ ẩn, Enter để xác nhận): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nHuỷ — không có gì được lưu.")
        return 2
    if not token:
        print("Token rỗng — huỷ, không lưu gì cả.")
        return 2

    client = BridgeClient(a.port, token, host=a.host, timeout=a.timeout)
    r = client.health()
    if r.get("status") != "ok" or not r.get("healthy"):
        print(f"GHÉP HỎNG — cầu nối từ chối hoặc không khoẻ: {r.get('error') or r}")
        print("Không lưu gì cả. Kiểm lại cổng/token, hoặc cầu nối đã dừng?")
        return 1

    p = luu(a.worker_id, host=a.host, port=a.port, token=token)
    print(f"GHÉP OK — {a.worker_id} trả lời khoẻ qua {a.host}:{a.port}")
    print(f"đã lưu tại {p} (không hiện lại token)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
