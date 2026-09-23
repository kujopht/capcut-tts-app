"""Automatic Silent Subprocess Patcher for Windows.

Enforces CREATE_NO_WINDOW and STARTF_USESHOWWINDOW (SW_HIDE) on all subprocess executions
(Popen, run, call, check_output, check_call) to permanently prevent any flashing black
console / conhost windows on the user's desktop.
"""

from __future__ import annotations

import os
import subprocess
import sys

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
STARTF_USESHOWWINDOW = getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
SW_HIDE = getattr(subprocess, "SW_HIDE", 0)

_orig_popen_init = subprocess.Popen.__init__
_IS_PATCHED = False


def _silent_popen_init(self, *args, **kwargs):
    if os.name == "nt":
        # 1. Enforce CREATE_NO_WINDOW flag
        flags = kwargs.get("creationflags", 0)
        flags |= NO_WINDOW
        kwargs["creationflags"] = flags

        # 2. Enforce STARTUPINFO with SW_HIDE
        si = kwargs.get("startupinfo")
        if si is None:
            si = subprocess.STARTUPINFO()
        si.dwFlags |= STARTF_USESHOWWINDOW
        si.wShowWindow = SW_HIDE
        kwargs["startupinfo"] = si

    _orig_popen_init(self, *args, **kwargs)


def apply_silent_subprocess():
    """Patches subprocess.Popen.__init__ globally."""
    global _IS_PATCHED
    if not _IS_PATCHED and os.name == "nt":
        subprocess.Popen.__init__ = _silent_popen_init
        _IS_PATCHED = True


# Auto-apply on import
apply_silent_subprocess()
