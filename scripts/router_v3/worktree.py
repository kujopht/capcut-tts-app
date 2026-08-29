"""Quản lý worktree cô lập — Router V3, Phase 4.

Hai worker ghi cùng một cây làm việc là hỏng chắc chắn: cái này `git add` đè
lên thay đổi dở dang của cái kia, và không ai dựng lại được chuyện gì đã xảy ra.
Mỗi nút CÓ GHI vì thế nhận một `git worktree` riêng trên một nhánh riêng.

KHÔNG TỰ XOÁ. Một worktree hỏng là bằng chứng để điều tra, và xoá tự động
đúng lúc đang gỡ lỗi là cách nhanh nhất để mất manh mối. `stale()` đánh dấu
thứ dọn được; việc xoá là do người quyết định.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

#: Nơi chứa worktree. Trong kho nhưng bị `.gitignore` bỏ qua — cùng chỗ với
#: các thư mục tạm khác để người vận hành biết tìm ở đâu.
ROOT_DIR = ".router/worktrees"

_HOP_LE = re.compile(r"^[A-Za-z0-9._-]+$")


class WorktreeError(RuntimeError):
    """Thao tác worktree thất bại. Không bao giờ nuốt — mất cô lập là mất tất cả."""


@dataclass(frozen=True)
class WorktreeHandle:
    worker_id: str
    task_id: str
    path: Path
    branch: str
    base_sha: str


def _kiem_ten(ten: str, nhan: str) -> None:
    """Chặn ký tự lạ trước khi chúng thành đường dẫn hay tên nhánh.

    `../` trong một `task_id` sẽ tạo worktree NGOÀI thư mục dự định; dấu cách
    và `~` làm hỏng lệnh git. Chặn ở cổng vào rẻ hơn nhiều so với dọn sau.
    """
    if not ten or not _HOP_LE.match(ten):
        raise WorktreeError(
            f"{nhan} không hợp lệ: {ten!r} — chỉ cho phép chữ, số, `.`, `_`, `-`.")


def branch_name(worker_id: str, task_id: str) -> str:
    _kiem_ten(worker_id, "worker_id")
    _kiem_ten(task_id, "task_id")
    return f"router/{worker_id}/{task_id}"


class WorktreeManager:
    def __init__(self, repo_root: Path, *,
                 runner=subprocess.run):
        self._root = Path(repo_root)
        self._run = runner
        self._cap: Dict[str, WorktreeHandle] = {}

    def _git(self, *args: str, check: bool = True):
        p = self._run(["git", "-C", str(self._root), *args],
                      capture_output=True, text=True, encoding="utf-8",
                      errors="replace")
        if check and p.returncode != 0:
            raise WorktreeError(
                f"git {' '.join(args[:2])} thất bại: "
                f"{(p.stderr or p.stdout or '').strip()[:300]}")
        return p

    def base_sha(self) -> str:
        return self._git("rev-parse", "HEAD").stdout.strip()

    def is_dirty(self) -> bool:
        return bool(self._git("status", "--porcelain").stdout.strip())

    def create(self, worker_id: str, task_id: str, *,
               base_sha: Optional[str] = None) -> WorktreeHandle:
        """Tạo worktree cô lập trên một nhánh mới.

        Đòi SHA gốc TƯỜNG MINH và xác minh nó tồn tại: một worker làm việc
        trên một điểm xuất phát khác với điều người điều phối tưởng là loại
        lỗi chỉ lộ ra lúc gộp, khi đã muộn.
        """
        nhanh = branch_name(worker_id, task_id)
        goc = base_sha or self.base_sha()
        kiem = self._git("cat-file", "-e", f"{goc}^{{commit}}", check=False)
        if kiem.returncode != 0:
            raise WorktreeError(f"base_sha {goc!r} không phải một commit hợp lệ")

        duong = self._root / ROOT_DIR / worker_id / task_id
        if duong.exists():
            raise WorktreeError(
                f"đã có worktree ở {duong} — KHÔNG ghi đè. Dọn tay nếu chắc "
                f"chắn nó không còn cần (xem `stale()`).")
        duong.parent.mkdir(parents=True, exist_ok=True)
        self._git("worktree", "add", "-b", nhanh, str(duong), goc)

        h = WorktreeHandle(worker_id=worker_id, task_id=task_id, path=duong,
                           branch=nhanh, base_sha=goc)
        self._cap[f"{worker_id}/{task_id}"] = h
        return h

    def list_worktrees(self) -> List[Dict[str, str]]:
        ra: List[Dict[str, str]] = []
        hien: Dict[str, str] = {}
        for dong in self._git("worktree", "list", "--porcelain").stdout.splitlines():
            if not dong.strip():
                if hien:
                    ra.append(hien)
                    hien = {}
                continue
            if " " in dong:
                k, v = dong.split(" ", 1)
                hien[k] = v.strip()
            else:
                hien[dong.strip()] = ""
        if hien:
            ra.append(hien)
        return ra

    def stale(self) -> List[str]:
        """Worktree của router mà lượt chạy này KHÔNG tạo ra.

        Chỉ ĐÁNH DẤU. Một worktree hỏng là bằng chứng để điều tra, và xoá tự
        động đúng lúc đang gỡ lỗi là cách nhanh nhất để mất manh mối.
        """
        dang_dung = {str(h.path.resolve()) for h in self._cap.values()}
        goc = (self._root / ROOT_DIR).resolve()
        ra = []
        for w in self.list_worktrees():
            p = w.get("worktree", "")
            if not p:
                continue
            rp = Path(p).resolve()
            try:
                rp.relative_to(goc)
            except ValueError:
                continue                    # khong phai worktree cua router
            if str(rp) not in dang_dung:
                ra.append(str(rp))
        return sorted(ra)

    def verify_scope(self, handle: WorktreeHandle,
                     write_scope: Sequence[str]) -> List[str]:
        """Tệp bị đổi NGOÀI phạm vi ghi đã cho phép.

        Đây là lưới cuối: `write_scope` trong gói việc là một hợp đồng, và một
        worker có thể phá hợp đồng đó. Rỗng = tuân thủ.
        """
        p = self._run(["git", "-C", str(handle.path), "status", "--porcelain"],
                      capture_output=True, text=True, encoding="utf-8",
                      errors="replace")
        if p.returncode != 0:
            raise WorktreeError(f"không đọc được trạng thái worktree: {p.stderr[:200]}")
        cho_phep = [s.replace("\\", "/").strip("/") for s in write_scope]
        vi_pham = []
        for dong in (p.stdout or "").splitlines():
            tep = dong[3:].strip().strip('"').replace("\\", "/")
            if " -> " in tep:               # doi ten
                tep = tep.split(" -> ", 1)[1]
            if not tep:
                continue
            if not any(tep == c or tep.startswith(c + "/") for c in cho_phep):
                vi_pham.append(tep)
        return sorted(vi_pham)
