#!/usr/bin/env python3
"""
Fanfic Audio Studio — entry point cho ban dong lenh (headless).

Dung khi muon tao audio ma khong mo giao dien, vi du de Claude Code tu chay sau
khi nguoi dung xac nhan mot arc da hoan tat:

    python cli.py generate-arc --input arc-01.arc.json --output D:\\audio \\
        --voice "Ngọc Huyền"

Ban dong goi tuong ung la `FanficAudioStudioCLI.exe` (console that, nen chuyen
huong `>` va ma tra ve luon hoat dong dung). Ngoai ra
`FanficAudioStudio.exe generate-arc ...` cung chay duoc cung cac lenh nay — xem
`app.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Cho phep chay truc tiep `python cli.py` tu bat ky thu muc
PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


def main() -> int:
    from desktop_app.arc_cli import main as cli_main

    return cli_main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
