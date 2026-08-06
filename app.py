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


def main() -> int:
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
