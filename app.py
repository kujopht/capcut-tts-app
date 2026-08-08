#!/usr/bin/env python3
"""
Fanfic Audio Studio — entry point ung dung desktop Windows (PySide6).

Ung dung nay CHAY THUAN DESKTOP: khong mo web server, khong mo trinh duyet,
khong can URL localhost.

Ban Gradio cua giai doan truoc duoc giu lam phuong an du phong:
    python legacy_gradio_app.py      (hoac nhap dup run_gradio.bat)

Chay:  python app.py                 (hoac nhap dup run_app.bat)

Ngoai ra file nay con la cua ngo cho ban DONG LENH: neu tham so dau tien la mot
lenh con (vi du `generate-arc`), ung dung KHONG mo cua so nao ma chay o che do
headless. Nho vay Claude Code tao duoc audio cho mot arc da hoan tat bang dung
mot lenh:

    FanficAudioStudio.exe generate-arc --input arc-01.arc.json ^
        --output D:\\audio --voice "Ngọc Huyền"

Ban EXE rieng cho dong lenh (`FanficAudioStudioCLI.exe`, sinh tu `cli.py`) co
console that nen dang tin cay hon khi can chuyen huong dau ra.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

# Cho phep chay truc tiep `python app.py` tu bat ky thu muc
PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


# AppUserModelID on dinh: Windows dua vao chuoi nay de gom cua so va shortcut
# vao dung mot icon tren Taskbar.
APP_USER_MODEL_ID = "kujopht.FanficAudioStudio"


def _set_windows_taskbar_identity() -> None:
    """
    Dat AppUserModelID rieng de Windows hien dung icon cua app tren Taskbar
    (neu khong, Windows se gop vao icon cua python.exe).

    Phai goi TRUOC khi tao QApplication. Tren he dieu hanh khac (hoac neu
    ctypes/shell32 khong dung duoc) thi bo qua, khong lam app loi.
    """
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def _requested_cli_command(argv: list[str]) -> str:
    """
    Tham so dong lenh co phai mot lenh con cua ban headless khong.

    Chi nhan dung ten lenh o vi tri dau tien. Moi tham so khac (vi du duong dan
    file do Windows truyen vao khi mo bang "Open with") deu duoc coi la khong
    phai, va ung dung mo giao dien nhu binh thuong.
    """
    if len(argv) < 2:
        return ""
    from desktop_app.arc_cli import COMMANDS

    candidate = argv[1].strip()
    return candidate if candidate in COMMANDS else ""


def _run_cli(argv: list[str]) -> int:
    """Chay ban dong lenh, khong tao QApplication va khong mo cua so nao."""
    from desktop_app.console_bridge import ensure_std_streams

    ensure_std_streams()
    from desktop_app.arc_cli import main as cli_main

    return cli_main(argv[1:])


def main() -> int:
    command = _requested_cli_command(sys.argv)
    if command:
        return _run_cli(sys.argv)

    _set_windows_taskbar_identity()

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError as exc:
        sys.stderr.write(
            "Thieu PySide6 nen khong chay duoc ung dung desktop.\n"
            f"Chi tiet: {exc}\n\n"
            "Hay chay trong PowerShell tai thu muc du an:\n"
            "    .\\.venv\\Scripts\\Activate.ps1\n"
            "    pip install -r requirements-gui.txt\n"
        )
        return 2

    from desktop_app import APP_NAME, APP_ORG, APP_VERSION
    from desktop_app.resources import load_app_icon

    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationDisplayName(APP_NAME)
    QApplication.setOrganizationName(APP_ORG)
    QApplication.setApplicationVersion(APP_VERSION)

    app = QApplication(sys.argv)

    # Dat icon cho toan bo ung dung ngay sau khi co QApplication, truoc khi
    # tao cua so -> title bar / Alt+Tab / Taskbar deu dung icon nay.
    icon = load_app_icon()
    if icon is not None:
        app.setWindowIcon(icon)

    try:
        from desktop_app.main_window import MainWindow

        window = MainWindow(app_icon=icon)
        window.show()
    except Exception:
        detail = traceback.format_exc()
        sys.stderr.write(detail)
        try:
            QMessageBox.critical(
                None,
                f"{APP_NAME} — không khởi động được",
                "Ứng dụng gặp lỗi khi khởi động:\n\n"
                f"{detail[-1200:]}\n\n"
                "Hãy kiểm tra lại cài đặt hoặc chạy lại 'pip install -r requirements-gui.txt'.",
            )
        except Exception:
            pass
        return 1

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
