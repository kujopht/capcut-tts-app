"""In trạng thái một cầu nối đã ghép — Router V3.2, Phase 5.

Đọc token từ nơi `pair_bridge.py` đã lưu cục bộ và tự dùng nó để gọi
"health" — KHÔNG BAO GIỜ in lại giá trị token, chỉ in trạng thái.

    python -m scripts.router_v3.bridge_status --worker-id AG02
"""
from __future__ import annotations

import argparse
import sys

from scripts.router_v3.bridge import BridgeClient
from scripts.router_v3.bridge_store import doc


def main(argv=None) -> int:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--worker-id", required=True)
    ap.add_argument("--timeout", type=float, default=10.0)
    a = ap.parse_args(argv)

    cfg = doc(a.worker_id)
    if cfg is None:
        print(f"{a.worker_id} = CHƯA GHÉP (chạy pair_bridge.py trước)")
        return 2

    r = BridgeClient(cfg["port"], cfg["token"], host=cfg["host"],
                     timeout=a.timeout).health()
    if r.get("status") != "ok":
        print(f"{a.worker_id} = KHÔNG LIÊN LẠC ĐƯỢC — {r.get('error') or r}")
        return 1
    if not r.get("healthy"):
        trang_thai = r.get("state", "")
        print(f"{a.worker_id} = HỎNG" + (f" ({trang_thai})" if trang_thai else ""))
        return 1

    trang_thai = r.get("state")
    if trang_thai:
        print(f"{a.worker_id} = HEALTHY / {trang_thai.upper().replace('_', '-')}")
    else:
        print(f"{a.worker_id} = HEALTHY (cầu nối cũ, chưa báo state chi tiết)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
