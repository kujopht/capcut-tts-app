"""Đọc `git` CHỈ-ĐỌC cho nguồn lịch sử — nằm NGOÀI gói `memory/` có chủ ý.

Gói `memory/` có một rào (bài kiểm `TestRaoGoi.test_khong_subprocess_khong_mang`):
không `subprocess`, không mạng — ký ức không được có đường tác động ra ngoài.
Nhập lịch sử cần `git log` và `git worktree list`, nên hai lệnh đó sống ở đây:
đúng ba lệnh đọc, tham số cố định, có `timeout`, có `**an_cua_so()` (không cửa
sổ console nào được nhấp lên — §14b), và không nhận chuỗi lệnh từ dữ liệu.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional

from scripts.router_v3.tien_trinh import an_cua_so


def _git(repo: Path, *args: str, han: float) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=han, **an_cua_so())
    except (OSError, subprocess.SubprocessError):
        return None


def ly_do_khong_phai_kho(repo: Path) -> str:
    """`""` nếu là kho git đọc được; ngược lại lý do (đọc được)."""
    if not Path(repo).is_dir():
        return f"không có thư mục kho: {repo}"
    p = _git(Path(repo), "rev-parse", "--is-inside-work-tree", han=30)
    if p is None:
        return "git không chạy được"
    return "" if (p.returncode == 0 and p.stdout.strip() == "true") else "không phải kho git"


def git_log_tho(repo: Path, *, gioi_han: int = 3000, han: float = 120.0) -> str:
    """`git log` dạng máy đọc: `%H\\x1f%at\\x1f%an\\x1f%s\\x1f%b\\x1e`. Rỗng nếu hỏng."""
    p = _git(Path(repo), "log", f"-n{int(gioi_han)}", "--date=raw",
             "--format=%H%x1f%at%x1f%an%x1f%s%x1f%b%x1e", han=han)
    if p is None or p.returncode != 0:
        return ""
    return p.stdout


def git_worktrees(repo: Path, *, han: float = 60.0) -> List[str]:
    """Đường dẫn các worktree của kho (`git worktree list --porcelain`). Rỗng nếu hỏng."""
    p = _git(Path(repo), "worktree", "list", "--porcelain", han=han)
    if p is None or p.returncode != 0:
        return []
    ra: List[str] = []
    for line in p.stdout.splitlines():
        if line.startswith("worktree "):
            ra.append(line[len("worktree "):].strip())
    return ra
