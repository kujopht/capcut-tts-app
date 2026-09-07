"""Dự án mặc định + khởi tạo lần đầu — Control Center V0.1, yêu cầu #1.

Thanh bên dự án phải có sẵn thứ gì đó ở lần mở đầu tiên; một danh sách rỗng
kèm nút "thêm dự án" là bắt người dùng làm việc của công cụ.

KHÔNG ĐÓNG CỨNG ĐƯỜNG DẪN NGƯỜI DÙNG. Đường dẫn kho được DÒ từ máy thật:
`git worktree list` của kho hiện tại đã biết cả kho chính lẫn mọi worktree,
nên không cần ai gõ `C:\\Users\\...` vào mã. Một đường dẫn đóng cứng sẽ sai
ngay khi kho được clone ở chỗ khác — và nó cũng là thứ không được phép nằm
trong mã dùng chung.

`resources` của một dự án khai HAI loại thứ, phân biệt bằng tiền tố:

    `write:<đường dẫn>`  phạm vi ghi mặc định khi câu người dùng không nói
                         rõ ghi vào đâu. Không khai = bộ lập kế hoạch KHÔNG
                         đoán, và hạ việc xuống chỉ đọc.
    `<tên dịch vụ>`      tài nguyên khoá được. Tên bắt đầu bằng `prod` thành
                         khoá PRODUCTION (không tự thu hồi).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scripts.control_center.model import Project
from scripts.control_center.store import ControlStore


def goc_kho_chinh(start: Optional[Path] = None) -> Path:
    """Kho CHÍNH của worktree hiện tại (không phải worktree đang đứng).

    `git worktree list` in kho chính ở dòng đầu. Dùng nó thay vì đoán từ
    đường dẫn: một worktree nằm ở `C:\\FanficWorkers\\...` trong khi kho
    chính ở `Documents\\...`, và không quy tắc chuỗi nào suy ra được điều đó.
    """
    goc = Path(start) if start else Path.cwd()
    try:
        p = subprocess.run(["git", "-C", str(goc), "worktree", "list",
                            "--porcelain"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30)
        if p.returncode == 0:
            for dong in (p.stdout or "").splitlines():
                if dong.startswith("worktree "):
                    return Path(dong.split(" ", 1)[1].strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return goc


def worktree_hien_tai(start: Optional[Path] = None) -> Path:
    goc = Path(start) if start else Path.cwd()
    try:
        p = subprocess.run(["git", "-C", str(goc), "rev-parse",
                            "--show-toplevel"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30)
        if p.returncode == 0 and (p.stdout or "").strip():
            return Path(p.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return goc


def du_an_mac_dinh(*, root: Optional[Path] = None) -> List[Project]:
    """Hai dự án mặc định: Fanfic (sản phẩm) và Router (chính hạ tầng này).

    Cả hai trỏ vào kho THẬT trên máy này, dò lúc chạy. Dự án tương lai được
    thêm qua `ControlCenter.them_project` — không cần sửa tệp này.
    """
    chinh = goc_kho_chinh(root)
    day = worktree_hien_tai(root)
    return [
        Project(
            project_id="fanfic",
            name="Fanfic",
            repo_path=str(chinh),
            default_branch="main",
            resources=(
                "write:web",
                "write:server",
                "prod:fanfic.world",
                "prod:appwrite",
                "prod:r2-bucket",
                "cloudflare-worker",
                "tts-worker-queue",
                "appwrite-schema",
            ),
            note=("Sản phẩm: web Next.js + backend FastAPI + app desktop. "
                  "KHÔNG đụng kho farmer sản xuất từ đây.")),
        Project(
            project_id="router",
            name="Router",
            repo_path=str(day),
            default_branch="main",
            resources=(
                "write:scripts/control_center",
                "write:scripts/router_v4",
                "router-fabric-config",
                "antigravity-account-pool",
            ),
            note=("Chính hạ tầng điều phối: Router V3/V4 + Control Center. "
                  "Chạy trong worktree cô lập của chính nó.")),
    ]


def khoi_tao(store: ControlStore, *, root: Optional[Path] = None,
             projects: Optional[List[Project]] = None) -> List[Project]:
    """Nạp dự án mặc định NẾU sổ còn rỗng.

    Chỉ khi rỗng: chạy lại không được ghi đè `repo_path` người dùng đã sửa,
    và cũng không được hồi sinh một dự án đã lưu trữ.
    """
    da_co = store.projects(include_archived=True)
    if da_co:
        return [p for p in da_co if not p.archived]
    ra = []
    for p in (projects if projects is not None else du_an_mac_dinh(root=root)):
        store.luu_project(p)
        store.ghi_su_kien("PROJECT_SEEDED", project_id=p.project_id,
                          detail=f"{p.name} @ {p.repo_path}")
        ra.append(p)
    return ra
