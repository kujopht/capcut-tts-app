"""Điểm khởi chạy chính — python -m scripts.router_v3.control_room."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Đảm bảo đường dẫn gốc kho nằm trong sys.path
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.router_v3.control_room.app import ControlRoomApp


def main() -> int:
    parser = argparse.ArgumentParser(description="Fanfic World Warp Control Room TUI")
    parser.add_argument("--root", type=str, default="", help="Đường dẫn thư mục gốc kho (mặc định: thư mục hiện tại)")
    parser.add_argument("--run-id", type=str, default="", help="Mã lượt chạy (run_id) cụ thể cần quan sát")
    parser.add_argument("--refresh-interval", type=float, default=1.0, help="Chu kỳ làm mới (giây, mặc định: 1.0)")

    args = parser.parse_args()
    root_path = Path(args.root).resolve() if args.root else Path.cwd()

    app = ControlRoomApp(
        root=root_path,
        run_id=args.run_id or None,
        refresh_interval=max(0.5, args.refresh_interval),
    )
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
