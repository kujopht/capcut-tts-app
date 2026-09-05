"""Quản lý worktree cô lập — Router V3, Phase 4 (+ gốc dùng chung, V3.2).

Hai worker ghi cùng một cây làm việc là hỏng chắc chắn: cái này `git add` đè
lên thay đổi dở dang của cái kia, và không ai dựng lại được chuyện gì đã xảy ra.
Mỗi nút CÓ GHI vì thế nhận một `git worktree` riêng trên một nhánh riêng.

KHÔNG TỰ XOÁ. Một worktree hỏng là bằng chứng để điều tra, và xoá tự động
đúng lúc đang gỡ lỗi là cách nhanh nhất để mất manh mối. `stale()` đánh dấu
thứ dọn được; việc xoá là do người quyết định.

GỐC DÙNG CHUNG (V3.2) — vì sao KHÔNG chỉ đổi đường dẫn là xong:

Worker AG02 chạy trong một hồ sơ Windows KHÁC và **không** có quyền đọc
`C:\\Users\\nguye`. Chuyển worktree sang một thư mục dùng chung nghe có vẻ
đủ, nhưng KHÔNG: một `git worktree` chỉ chứa một tệp `.git` trỏ NGƯỢC về
`.git/worktrees/<tên>` của kho mẹ. Đã đo:

    gitdir: C:/Users/nguye/Documents/CapCut-TTS-App/.git/worktrees/_probe

AG02 đọc được thư mục làm việc nhưng không đọc được con trỏ đó, nên mọi
lệnh git đều hỏng.

Cách giải: một **bản sao bare** nằm NGAY TRONG gốc dùng chung. Worktree
tạo từ bản sao đó tự chứa hoàn toàn:

    gitdir: C:/FanficWorkers/repo.git/worktrees/probe

Router đẩy commit nền sang bản sao; worker làm việc trong worktree của
bản sao; Router kéo kết quả về. Hồ sơ chính KHÔNG hề mở quyền cho ai.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

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


def resolve_worktree_metadata_dir(git_common_dir: Path, worktree_name: str) -> Path:
    """Xác định và kiểm tra an toàn thư mục metadata của một worktree cụ thể.

    Đảm bảo thư mục metadata nằm CHÍNH XÁC là con trực tiếp của
    `<git_common_dir>/worktrees/`. Chặn mọi hành vi directory traversal (`..`),
    phân cách đường dẫn, hoặc trỏ ra ngoài.
    """
    if not worktree_name or not isinstance(worktree_name, str):
        raise WorktreeError("worktree_name không được để trống và phải là chuỗi")

    # Chặn ký tự phân cách đường dẫn và traversal
    if "/" in worktree_name or "\\" in worktree_name or ".." in worktree_name:
        raise WorktreeError(
            f"worktree_name không hợp lệ: {worktree_name!r} — không được chứa ký tự phân cách đường dẫn hoặc '..'")

    wt_meta_root = (Path(git_common_dir) / "worktrees").resolve()
    target = (wt_meta_root / worktree_name).resolve()

    # Kiểm tra target phải là con trực tiếp của wt_meta_root
    try:
        rel = target.relative_to(wt_meta_root)
        if len(rel.parts) != 1 or rel.parts[0] != worktree_name:
            raise ValueError()
    except (ValueError, RuntimeError):
        raise WorktreeError(
            f"Đường dẫn metadata {target} nằm ngoài phạm vi cho phép: {wt_meta_root}")

    return target


def normalize_worktree_metadata_attributes(
    meta_dir: Path,
    *,
    _platform: Optional[str] = None,
    _setter=None
) -> None:
    """Xoá thuộc tính READONLY (Windows) của thư mục metadata worktree cụ thể.

    Trên Windows NTFS, nếu thư mục `.git/worktrees/<tên>` hoặc các thư mục con
    như `logs/`, `refs/` có cờ `FILE_ATTRIBUTE_READONLY` (0x01), lệnh gọi
    `RemoveDirectoryW()` của Git/C-runtime sẽ thất bại với `ERROR_ACCESS_DENIED`
    (Permission denied), để lại tệp/thư mục rác mồ côi không thể prune.

    Hàm này CHỈ tác động lên đúng cây thư mục `meta_dir` được chỉ định.
    Không bao giờ đụng đến thư mục cha `.git/worktrees` hay các worktree khác.
    Trên hệ điều hành phi-Windows, hàm này là no-op an toàn.
    """
    plat = _platform if _platform is not None else sys.platform
    if plat != "win32":
        return

    target = Path(meta_dir)
    if not target.exists():
        return

    if _setter is None:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        def _default_setter(path_str: str, attrs: int) -> bool:
            res = kernel32.SetFileAttributesW(path_str, attrs)
            if not res:
                err = ctypes.get_last_error()
                raise WorktreeError(
                    f"không thể gỡ thuộc tính ReadOnly của {path_str}: lỗi Win32 {err}")
            return True

        setter = _default_setter
    else:
        setter = _setter

    FILE_ATTRIBUTE_NORMAL = 0x80

    for root, dirs, files in os.walk(target, topdown=False):
        for f in files:
            p = os.path.join(root, f)
            setter(p, FILE_ATTRIBUTE_NORMAL)
        for d in dirs:
            p = os.path.join(root, d)
            setter(p, FILE_ATTRIBUTE_NORMAL)

    setter(str(target), FILE_ATTRIBUTE_NORMAL)


class WorktreeManager:
    def __init__(self, repo_root: Path, *,
                 runner=subprocess.run,
                 git_dir: Optional[Path] = None,
                 worktree_root: Optional[Path] = None):
        """
        :param repo_root: kho làm việc chính (mặc định là nơi chạy git).
        :param git_dir: kho **bare** để tạo worktree từ đó. Đặt khi worker
            chạy dưới một tài khoản không đọc được `repo_root` — xem docstring
            module. `None` = dùng chính `repo_root` (hành vi cũ).
        :param worktree_root: nơi đặt worktree. `None` = `repo_root/.router/
            worktrees` như cũ. Đặt một thư mục dùng chung đã siết ACL khi cần
            chia sẻ với tài khoản khác.
        """
        self._root = Path(repo_root)
        self._run = runner
        # Moi lenh git deu chay tren KHO NAO: bare neu co, khong thi kho chinh.
        self._git_root = Path(git_dir) if git_dir else self._root
        self._wt_root = (Path(worktree_root) if worktree_root
                         else self._root / ROOT_DIR)
        self._cap: Dict[str, WorktreeHandle] = {}

    @property
    def worktree_root(self) -> Path:
        return self._wt_root

    @property
    def git_root(self) -> Path:
        return self._git_root

    @property
    def git_common_dir(self) -> Path:
        """Đường dẫn đến thư mục git chung (thường là .git hoặc bare repo)."""
        raw = self._git("rev-parse", "--git-common-dir").stdout.strip()
        p = Path(raw)
        if not p.is_absolute():
            p = (self._git_root / p).resolve()
        return p

    def _git(self, *args: str, check: bool = True):
        p = self._run(["git", "-C", str(self._git_root), *args],
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

        duong = self._wt_root / worker_id / task_id
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
        goc = self._wt_root.resolve()
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

        `-uall` liệt kê TỪNG tệp chưa theo dõi thay vì gộp thành một dòng thư
        mục (`?? pkg/`). Bản gộp làm phép so phạm vi kém chính xác: nó so
        `pkg/` với danh sách cho phép thay vì so từng tệp thật bên trong.
        """
        p = self._run(["git", "-C", str(handle.path), "status", "--porcelain",
                       "-uall"],
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

    def find_metadata_dir(self, target: Union[WorktreeHandle, Path, str]) -> Optional[Path]:
        """Tìm thư mục metadata của worktree trong `<git_common_dir>/worktrees/`.

        Hỗ trợ nhận diện qua:
        - `WorktreeHandle`: thông qua tệp `.git` của cây làm việc hoặc tên `task_id`
        - `Path` / `str` (đường dẫn cây làm việc): thông qua tệp `.git` hoặc duyệt `gitdir`
        - `str` (tên metadata đơn thuần): như `agy-story-meta`

        Chặn mọi hành vi directory traversal. Trả về `None` nếu metadata không tồn tại.
        """
        if isinstance(target, str) and ".." in target:
            raise WorktreeError(f"đường dẫn worktree không hợp lệ: {target!r}")
        if isinstance(target, Path) and ".." in str(target):
            raise WorktreeError(f"đường dẫn worktree không hợp lệ: {target!r}")

        try:
            wt_meta_root = (self.git_common_dir / "worktrees").resolve()
        except Exception:
            return None

        if not wt_meta_root.is_dir():
            return None

        # 1. Neu target la WorktreeHandle
        if isinstance(target, WorktreeHandle):
            git_file = target.path / ".git"
            if git_file.is_file():
                try:
                    content = git_file.read_text(encoding="utf-8", errors="replace").strip()
                    if content.startswith("gitdir:"):
                        cand = Path(content[len("gitdir:"):].strip())
                        if not cand.is_absolute():
                            cand = (target.path / cand).resolve()
                        rel = cand.relative_to(wt_meta_root)
                        if len(rel.parts) == 1 and cand.is_dir():
                            return cand
                except (ValueError, OSError):
                    pass

            try:
                cand = resolve_worktree_metadata_dir(self.git_common_dir, target.task_id)
                if cand.is_dir():
                    return cand
            except WorktreeError:
                pass

            target_path_resolved = target.path.resolve()
            for entry in wt_meta_root.iterdir():
                if not entry.is_dir():
                    continue
                gd = entry / "gitdir"
                if gd.is_file():
                    try:
                        c = gd.read_text(encoding="utf-8", errors="replace").strip()
                        cp = Path(c)
                        if cp.name == ".git":
                            cp = cp.parent
                        if cp.resolve() == target_path_resolved:
                            return entry
                    except (ValueError, OSError):
                        pass
            return None

        # 2. Neu target la chuoi ky tu
        if isinstance(target, str):
            if target in self._cap:
                return self.find_metadata_dir(self._cap[target])

            if ".." in target:
                raise WorktreeError(f"đường dẫn worktree không hợp lệ: {target!r}")

            if "/" not in target and "\\" not in target:
                try:
                    cand = resolve_worktree_metadata_dir(self.git_common_dir, target)
                    if cand.is_dir():
                        return cand
                except WorktreeError:
                    raise
                except Exception:
                    pass

            target_path = Path(target)
        else:
            target_path = target

        # 3. Target la Path
        if target_path.is_file() and target_path.name == ".git":
            target_path = target_path.parent

        git_file = target_path / ".git"
        if git_file.is_file():
            try:
                content = git_file.read_text(encoding="utf-8", errors="replace").strip()
                if content.startswith("gitdir:"):
                    cand = Path(content[len("gitdir:"):].strip())
                    if not cand.is_absolute():
                        cand = (target_path / cand).resolve()
                    rel = cand.relative_to(wt_meta_root)
                    if len(rel.parts) == 1 and cand.is_dir():
                        return cand
            except (ValueError, OSError):
                pass

        target_res = target_path.resolve()
        for entry in wt_meta_root.iterdir():
            if not entry.is_dir():
                continue
            gd = entry / "gitdir"
            if gd.is_file():
                try:
                    c = gd.read_text(encoding="utf-8", errors="replace").strip()
                    cp = Path(c)
                    if cp.name == ".git":
                        cp = cp.parent
                    if cp.resolve() == target_res:
                        return entry
                except (ValueError, OSError):
                    pass

        try:
            cand = resolve_worktree_metadata_dir(self.git_common_dir, target_path.name)
            if cand.is_dir():
                return cand
        except WorktreeError:
            pass

        return None

    def remove(self, target: Union[WorktreeHandle, Path, str], *,
               force: bool = True) -> None:
        """Gỡ bỏ worktree và dọn dẹp metadata an toàn theo chuẩn Git.

        Thứ tự thực hiện:
        1. Tìm thư mục metadata của worktree trong `.git/worktrees/`.
        2. Nếu tìm thấy metadata: gọi `normalize_worktree_metadata_attributes`
           để gỡ cờ READONLY trên Windows trước khi Git xoá/prune.
        3. Nếu cây làm việc vật lý còn tồn tại:
           gọi `git worktree remove [--force] <path>`.
        4. Nếu cây làm việc vật lý đã mất (stale):
           gọi `git worktree prune --expire now`.
        5. Nếu cả cây làm việc lẫn metadata đều đã biến mất: kết thúc an toàn (idempotent).
        6. Thu hồi handle khỏi cache quản lý nội bộ.
        """
        wt_path: Optional[Path] = None
        cap_key: Optional[str] = None

        if isinstance(target, WorktreeHandle):
            wt_path = target.path
            cap_key = f"{target.worker_id}/{target.task_id}"
        elif isinstance(target, str) and target in self._cap:
            handle = self._cap[target]
            wt_path = handle.path
            cap_key = target
        elif isinstance(target, Path):
            wt_path = target
            for k, h in list(self._cap.items()):
                if h.path.resolve() == target.resolve():
                    cap_key = k
                    break
        elif isinstance(target, str):
            if "/" in target or "\\" in target:
                p = Path(target)
                wt_path = p
                for k, h in list(self._cap.items()):
                    if h.path.resolve() == p.resolve():
                        cap_key = k
                        break
            else:
                for k, h in list(self._cap.items()):
                    if h.task_id == target or h.path.name == target:
                        wt_path = h.path
                        cap_key = k
                        break

        meta_dir = self.find_metadata_dir(target if wt_path is None else wt_path)

        if meta_dir and wt_path is None:
            gitdir_file = meta_dir / "gitdir"
            if gitdir_file.is_file():
                try:
                    raw_gd = gitdir_file.read_text(encoding="utf-8", errors="replace").strip()
                    p = Path(raw_gd)
                    if p.name == ".git":
                        p = p.parent
                    wt_path = p
                except Exception:
                    pass

        wt_exists = wt_path is not None and wt_path.exists()
        meta_exists = meta_dir is not None and meta_dir.is_dir()

        if not wt_exists and not meta_exists:
            if cap_key:
                self._cap.pop(cap_key, None)
            return

        if meta_exists and meta_dir is not None:
            normalize_worktree_metadata_attributes(meta_dir)

        if wt_exists and wt_path is not None:
            cmd = ["worktree", "remove"]
            if force:
                cmd.append("--force")
            cmd.append(str(wt_path))
            self._git(*cmd)
        else:
            self._git("worktree", "prune", "--expire", "now")

        if cap_key:
            self._cap.pop(cap_key, None)

    def prune_stale(self, *, worktree_name: Optional[str] = None) -> None:
        """Dọn dẹp các metadata worktree cũ/mồ côi bằng git worktree prune.

        Nếu `worktree_name` được chỉ định, chuẩn hoá thuộc tính cho đúng thư mục
        metadata đó trước khi gọi `git worktree prune`.
        Nếu `worktree_name` là None, quét các worktree prunable hoặc mồ côi
        (không có cây làm việc vật lý) và chuẩn hoá thuộc tính cho các thư mục
        đó trước khi prune.

        TUYỆT ĐỐI KHÔNG can thiệp vào các worktree đang hoạt động bình thường.
        """
        wt_meta_root = (self.git_common_dir / "worktrees").resolve()

        if worktree_name is not None:
            meta_dir = resolve_worktree_metadata_dir(self.git_common_dir, worktree_name)
            if meta_dir.is_dir():
                normalize_worktree_metadata_attributes(meta_dir)
            self._git("worktree", "prune", "--expire", "now")
            return

        if not wt_meta_root.is_dir():
            self._git("worktree", "prune", "--expire", "now")
            return

        list_wt = self.list_worktrees()
        prunable_paths = set()
        for w in list_wt:
            if "prunable" in w:
                prunable_paths.add(w.get("worktree", ""))
            elif w.get("worktree") and not Path(w["worktree"]).exists():
                prunable_paths.add(w.get("worktree", ""))

        for entry in wt_meta_root.iterdir():
            if not entry.is_dir():
                continue
            is_stale = False
            gitdir_file = entry / "gitdir"
            if not gitdir_file.is_file():
                # Thư mục metadata mất tệp gitdir (như trường hợp agy-story-meta)
                is_stale = True
            else:
                try:
                    raw_gd = gitdir_file.read_text(encoding="utf-8", errors="replace").strip()
                    p = Path(raw_gd)
                    if p.name == ".git":
                        p = p.parent
                    if str(p) in prunable_paths or not p.exists():
                        is_stale = True
                except Exception:
                    is_stale = True

            if is_stale:
                normalize_worktree_metadata_attributes(entry)

        self._git("worktree", "prune", "--expire", "now")

