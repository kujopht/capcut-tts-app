#!/usr/bin/env python3
"""
Fanfic Audio Studio — entry point ung dung desktop Windows (PySide6).

Ung dung nay CHAY THUAN DESKTOP: khong mo web server, khong mo trinh duyet,
khong can URL localhost.

Ban Gradio cua giai doan truoc duoc giu lam phuong an du phong:
    python legacy_gradio_app.py      (hoac nhap dup run_gradio.bat)

Chay:  python app.py                 (hoac nhap dup run_app.bat)
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


def resource_path(*parts: str) -> Path:
    """
    Duong dan tai nguyen, dung ca khi chay tu source va khi da dong goi
    bang PyInstaller (--onedir: tai nguyen nam trong sys._MEIPASS).
    """
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else PROJECT_DIR
    return root.joinpath(*parts)


def app_icon_path() -> Path | None:
    for candidate in (
        resource_path("assets", "app_icon.ico"),
        PROJECT_DIR / "assets" / "app_icon.ico",
    ):
        if candidate.is_file():
            return candidate
    return None


def _set_windows_taskbar_identity() -> None:
    """
    Dat AppUserModelID rieng de Windows hien dung icon cua app tren Taskbar
    (neu khong, Windows se gop vao icon cua python.exe).
    """
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "FanficAudioStudio.DesktopApp.2"
        )
    except Exception:
        pass


def main() -> int:
    _set_windows_taskbar_identity()

    try:
        from PySide6.QtGui import QIcon
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

    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationDisplayName(APP_NAME)
    QApplication.setOrganizationName(APP_ORG)
    QApplication.setApplicationVersion(APP_VERSION)

    app = QApplication(sys.argv)

    icon = None
    icon_file = app_icon_path()
    if icon_file is not None:
        icon = QIcon(str(icon_file))
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
