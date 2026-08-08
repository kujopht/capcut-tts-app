"""
Truy cap tai nguyen (icon, asset) theo mot duong dan thong nhat.

Module nay la NGUON DUY NHAT de tim file trong assets/, dung ca khi:
    - chay tu source          -> goc du an
    - dong goi PyInstaller    -> sys._MEIPASS (onedir: thu muc _internal)

Khong duoc dung duong dan tuyet doi cua may ca nhan va khong tai icon tu
Internet: moi tai nguyen deu nam trong repo/ban build.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# desktop_app/resources.py -> goc du an la thu muc cha cua package
PROJECT_DIR = Path(__file__).resolve().parent.parent

ICON_PNG = ("assets", "app_icon.png")
ICON_ICO = ("assets", "app_icon.ico")


def resource_path(*parts: str) -> Path:
    """
    Duong dan toi mot tai nguyen di kem ung dung.

    Uu tien thu muc giai nen cua PyInstaller (sys._MEIPASS) neu co, neu khong
    thi lay theo goc du an.
    """
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else PROJECT_DIR
    return root.joinpath(*parts)


def find_resource(*parts: str) -> Optional[Path]:
    """Tra ve duong dan dau tien thuc su ton tai, hoac None."""
    candidates = [resource_path(*parts)]
    fallback = PROJECT_DIR.joinpath(*parts)
    if fallback not in candidates:
        candidates.append(fallback)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def app_icon_png() -> Optional[Path]:
    """PNG dung lam logo hien thi trong giao dien."""
    return find_resource(*ICON_PNG)


def app_icon_ico() -> Optional[Path]:
    """ICO nhieu kich thuoc, dung cho title bar / taskbar / EXE."""
    return find_resource(*ICON_ICO)


def load_app_icon():
    """
    QIcon cua ung dung, gop ca .ico (nhieu size cho Windows) va .png.

    Tra ve None neu khong tim thay file nao hoac khong import duoc Qt.
    """
    try:
        from PySide6.QtGui import QIcon
    except ImportError:  # pragma: no cover - moi truong khong co Qt
        return None

    icon = QIcon()
    found = False
    for path in (app_icon_ico(), app_icon_png()):
        if path is not None:
            icon.addFile(str(path))
            found = True
    if not found or icon.isNull():
        return None
    return icon
