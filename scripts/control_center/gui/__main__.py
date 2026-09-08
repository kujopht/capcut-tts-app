"""Điểm vào giao diện đồ hoạ: `python -m scripts.control_center.gui`.

Thiếu PySide6 thì báo ĐÚNG câu lệnh cần chạy rồi thoát 2 — không đổ một
traceback vào mặt người dùng. Cùng cách xử lý như `__main__.py` của TUI khi
thiếu `textual`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="control-center-gui",
        description="Router Control Center V0.1.1 — giao diện đồ hoạ")
    ap.add_argument("--root", default="", help="thư mục gốc giữ sổ .router/")
    ap.add_argument("--project", default="", help="dự án mở sẵn")
    ap.add_argument("--max-parallel", type=int, default=3,
                    help="trần việc chạy song song (mặc định 3)")
    a = ap.parse_args(argv)

    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as e:                    # pragma: no cover
        if not str(e.name or "").startswith("PySide6"):
            raise
        sys.stderr.write(
            "control-center-gui: thiếu PySide6 — chưa có phụ thuộc giao "
            "diện.\n"
            "  Cài đặt:  python -m pip install -r "
            "requirements-control-center-gui.txt\n"
            "  Hoặc dùng giao diện terminal:  router-cc\n")
        return 2

    from scripts.control_center.gui.app import CuaSoChinh

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Router Control Center")
    cs = CuaSoChinh(root=Path(a.root) if a.root else None)
    if a.project:
        cs.cau.chon_project(a.project)
    cs.show()
    cs.bat_dau()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
