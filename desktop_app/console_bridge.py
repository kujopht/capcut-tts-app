"""
Noi lai stdout/stderr khi ban EXE dang o che do "windowed".

Van de that: `FanficAudioStudio.exe` duoc dong goi voi `console=False` de mo giao
dien ma khong nhay cua so console. Nhung ban EXE do khong co console, nen Python
khoi tao voi `sys.stdout is None` — moi lenh `print` cua CLI se roi vao hu khong.

Module nay khoi phuc lai luong ra khi ung dung duoc goi voi lenh con:

1. Neu tien trinh cha da cap san handle (vi du bi chuyen huong `> log.txt`),
   dung DUNG handle do — nho vay chuyen huong ra file van hoat dong.
2. Neu khong, gan vao console cua tien trinh cha (`AttachConsole`) va mo
   `CONOUT$` / `CONIN$`.
3. Neu ca hai deu khong duoc (chay bang dup chuot, khong co console nao), thay
   bang mot luong rong de `print` khong nem exception.

Chay tu ma nguon (`python app.py generate-arc ...`) thi stdout da san sang, nen
ham nay khong lam gi ca.
"""

from __future__ import annotations

import io
import os
import sys
from typing import Optional

#: Tham so cua AttachConsole: gan vao console cua tien trinh cha.
ATTACH_PARENT_PROCESS = -1

_STD_HANDLES = {"stdout": -11, "stderr": -12}


class _NullStream(io.TextIOBase):
    """Luong rong: nhan moi thu va bo di, de CLI khong sap khi khong co console."""

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        return len(text or "")

    def flush(self) -> None:
        return None


def _stream_is_usable(stream) -> bool:
    """Luong nay co that su ghi duoc khong."""
    if stream is None:
        return False
    try:
        if getattr(stream, "closed", False):
            return False
        stream.write("")
        stream.flush()
        return True
    except Exception:
        return False


def _from_std_handle(name: str) -> Optional[io.TextIOWrapper]:
    """
    Mo lai luong tu handle chuan cua Windows.

    Day la duong duy nhat ton trong chuyen huong cua tien trinh cha: neu nguoi
    dung goi `... generate-arc > out.txt`, handle nay tro tro tiep den file do.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        import msvcrt

        handle = ctypes.windll.kernel32.GetStdHandle(_STD_HANDLES[name])
        if not handle or handle == -1 or handle == ctypes.c_void_p(-1).value:
            return None
        fd = msvcrt.open_osfhandle(handle, os.O_WRONLY)
        if fd < 0:
            return None
        raw = os.fdopen(fd, "wb", buffering=0)
        return io.TextIOWrapper(raw, encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        return None


def _from_conout() -> Optional[io.TextIOWrapper]:
    """Mo `CONOUT$` sau khi da gan vao console cua tien trinh cha."""
    if os.name != "nt":
        return None
    try:
        return open(  # noqa: SIM115 - luong nay song het doi tien trinh
            "CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1
        )
    except Exception:
        return None


def _attach_parent_console() -> bool:
    """Gan tien trinh vao console cua tien trinh cha. Tra True neu da co console."""
    if os.name != "nt":
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        if kernel32.GetConsoleWindow():
            return True
        return bool(kernel32.AttachConsole(ATTACH_PARENT_PROCESS))
    except Exception:
        return False


def ensure_std_streams() -> bool:
    """
    Bao dam `sys.stdout` / `sys.stderr` ghi duoc.

    Tra True neu luong ra thuc su den duoc nguoi dung, False neu phai dung luong
    rong (khi do CLI van chay dung va ma tra ve van chinh xac, chi la khong ai
    doc duoc thong bao).
    """
    needs_stdout = not _stream_is_usable(sys.stdout)
    needs_stderr = not _stream_is_usable(sys.stderr)
    if not needs_stdout and not needs_stderr:
        return True

    # 1. Handle do tien trinh cha cap (ton trong chuyen huong ra file)
    replacements = {
        name: _from_std_handle(name)
        for name, needed in (("stdout", needs_stdout), ("stderr", needs_stderr))
        if needed
    }

    # 2. Chua duoc thi gan vao console cua cha roi mo CONOUT$
    if any(value is None for value in replacements.values()):
        attached = _attach_parent_console()
        for name, value in list(replacements.items()):
            if value is None and attached:
                replacements[name] = _from_conout()

    reachable = True
    for name, value in replacements.items():
        if value is None:
            value = _NullStream()
            reachable = False
        setattr(sys, name, value)

    return reachable
