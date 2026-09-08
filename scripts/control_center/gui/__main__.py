"""Điểm vào giao diện đồ hoạ: `python -m scripts.control_center.gui`.

Thiếu PySide6 thì báo ĐÚNG câu lệnh cần chạy rồi thoát 2 — không đổ một
traceback vào mặt người dùng. Cùng cách xử lý như `__main__.py` của TUI khi
thiếu `textual`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

#: Ngat dong, khai bang ten de khong lan voi escape trong f-string.
NL = "\n"


def _bao_thieu_goi(ten: str) -> None:
    """Báo thiếu gói theo đường NGƯỜI DÙNG THẬT SỰ THẤY.

    `router-cc-gui.cmd` chạy bằng `pythonw.exe` de khong nhay ra cua so
    console — nhung duoi `pythonw` thi KHONG CO stderr nao de doc. Ban dau
    chi ghi stderr, nen tren mot may chua cai PySide6, bam doi vao launcher
    la HOAN TOAN IM LANG: khong cua so, khong thong bao, khong gi ca.

    Nen: ghi stderr (cho ai chay tu terminal) VA bat mot hop thoai cua
    Windows qua `ctypes` (cho ai bam doi). `ctypes` la thu vien chuan nen
    duong nay khong phu thuoc vao chinh cai goi dang thieu.
    """
    loi = (f"Thiếu gói {ten!r} — chưa có phụ thuộc giao diện." + NL + NL
           + "Cài đặt:" + NL
           + "    python -m pip install -r "
             "requirements-control-center-gui.txt" + NL + NL
           + "Hoặc dùng giao diện terminal:" + NL
           + "    router-cc")
    try:
        sys.stderr.write("control-center-gui: " + loi + NL)
    except Exception:                                   # noqa: BLE001
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, loi, "Router Control Center", 0x10)
        except Exception:                               # noqa: BLE001
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="control-center-gui",
        description="Router Control Center V0.1.1 — giao diện đồ hoạ")
    ap.add_argument("--root", default="", help="thư mục gốc giữ sổ .router/")
    ap.add_argument("--project", default="", help="dự án mở sẵn")
    ap.add_argument("--max-parallel", type=int, default=3,
                    help="trần việc chạy song song (mặc định 3)")
    ap.add_argument("--check", action="store_true",
                    help=("chỉ kiểm phụ thuộc rồi thoát (0 = đủ, 2 = thiếu). "
                          "Launcher gọi cờ này bằng python CÓ console nên "
                          "thông báo còn đọc được."))
    a = ap.parse_args(argv)

    if a.check:
        try:
            import PySide6                              # noqa: F401
        except ModuleNotFoundError as e:
            _bao_thieu_goi(str(e.name))
            return 2
        print("phụ thuộc giao diện: đủ")
        return 0

    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as e:                    # pragma: no cover
        if not str(e.name or "").startswith("PySide6"):
            raise
        _bao_thieu_goi(str(e.name))
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
