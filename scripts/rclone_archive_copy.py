"""Day MOT thu muc spool THO len kho archive lanh qua rclone.

CHI dung `rclone copy` — khong bao gio sync/move/delete/purge. Day la co
chu dich, khong phai boi vi thieu tinh nang: kho archive KHONG duoc coi la
CDN cong khai va cung KHONG duoc phep tu dong xoa gi o phia Drive chi vi
local spool thay doi (xem mission brief "RAW ARCHIVE gate" — Drive luon
la ban sao THEM VAO, khong bao gio la nguon dong bo hai chieu). Verb "copy"
duoc HARDCODE trong `subprocess.run(...)`, khong nhan tham so de doi verb —
mot loi goi sai cua nguoi dung KHONG the bien no thanh sync/delete.

    python -m scripts.rclone_archive_copy \
        --local-dir <thu_muc_spool> \
        --remote-path fanfic-gdrive:FanficWorld/archive/scraping/raw/<ten>

Khong doi cau hinh rclone/OAuth o day — script nay CHI goi rclone da
duoc xac thuc san tren may, giong nguyen tac "adapter khong tu giu
credential" da ap dung cho agy/codex trong `scripts/ai_router_dispatch.py`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Dict


def rclone_copy(local_dir: str, remote_path: str, *, rclone_bin: str = "rclone",
                 timeout: int = 300) -> Dict:
    proc = subprocess.run(
        [rclone_bin, "copy", local_dir, remote_path, "--checksum"],
        capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def rclone_verify(local_dir: str, remote_path: str, *, rclone_bin: str = "rclone",
                   timeout: int = 180) -> Dict:
    """Doi soat DOC LAP sau khi copy — khong suy tu exit code cua `copy`."""
    check = subprocess.run(
        [rclone_bin, "check", local_dir, remote_path, "--one-way"],
        capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    lsjson = subprocess.run(
        [rclone_bin, "lsjson", remote_path, "--recursive"],
        capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    size = subprocess.run(
        [rclone_bin, "size", remote_path, "--json"],
        capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    return {
        "check_exit_code": check.returncode,
        "check_stdout": check.stdout,
        "check_stderr_tail": (check.stderr or "")[-2000:],
        "lsjson_exit_code": lsjson.returncode,
        "lsjson": lsjson.stdout,
        "size_exit_code": size.returncode,
        "size": size.stdout,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--local-dir", required=True)
    ap.add_argument("--remote-path", required=True)
    ap.add_argument("--rclone-bin", default="rclone")
    a = ap.parse_args(argv)

    copy_result = rclone_copy(a.local_dir, a.remote_path, rclone_bin=a.rclone_bin)
    verify_result = rclone_verify(a.local_dir, a.remote_path, rclone_bin=a.rclone_bin)

    report = {"copy": copy_result, "verify": verify_result}
    print(json.dumps(report, ensure_ascii=False, indent=2))

    ok = copy_result["exit_code"] == 0 and verify_result["check_exit_code"] == 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
