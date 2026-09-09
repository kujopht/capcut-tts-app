"""Quản lý worktree ở tầng Control Center — yêu cầu #5.

DÙNG LẠI, KHÔNG VIẾT LẠI. `router_v3/worktree.py` đã giải xong phần khó và
đã bị đập thật trên máy này: tạo worktree từ một bản sao bare cho tài khoản
Windows khác đọc được, chặn `../` trong `task_id`, gỡ cờ READONLY của NTFS,
kiểm phạm vi bằng `git status --porcelain -uall`. Lớp này KHÔNG chạm vào
những thứ đó. Nó thêm đúng ba thứ V3 không có, vì V3 không có khái niệm
"phiên sống lâu":

    1. LIÊN KẾT BỀN  việc <-> nhánh <-> worktree, sống qua khởi động lại.
    2. DÙNG LẠI AN TOÀN  một phiên sở hữu MỘT worktree; việc tiếp theo của
       chính phiên đó dùng lại nó thay vì đẻ ra cây thứ hai.
    3. LOẠI TRỪ  hai phiên KHÔNG BAO GIỜ cùng ghi một worktree.

KHÔNG TỰ XOÁ — nhắc lại luật của V3 và của đề bài V0.1. `danh_dau_stale()`
chỉ ĐÁNH DẤU. Một worktree hỏng là bằng chứng; xoá tự động lúc đang gỡ lỗi
là cách nhanh nhất để mất manh mối, và ở đây còn tệ hơn vì nó có thể chứa
công việc chưa commit của một agent vừa chết.

LUẬT DÙNG LẠI, và vì sao nó hẹp có chủ đích:

Chỉ dùng lại worktree khi **cùng một phiên** xin nó. Không dùng lại giữa
hai phiên, kể cả khi phạm vi trông có vẻ rời nhau. Lý do: "phạm vi rời nhau"
là lời khai của hợp đồng, còn thứ thật sự nằm trên đĩa là `git status` —
một agent đi lệch phạm vi (chuyện đã xảy ra thật, xem cổng `contract_scope`
của V4) sẽ biến hai phạm vi "rời nhau" thành hai agent giẫm lên nhau trong
cùng một cây. Một worktree thừa tốn vài trăm MB; một lần trộn công việc của
hai agent tốn cả buổi để gỡ.
"""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.router_v3.worktree import (WorktreeError, WorktreeHandle,
                                        WorktreeManager)
from scripts.control_center.store import ControlStore
from scripts.router_v3.tien_trinh import an_cua_so

#: Trang thai mot worktree theo goc nhin Control Center.
WT_ACTIVE = "ACTIVE"      # co phien dang so huu
WT_IDLE = "IDLE"          # con nguyen, khong ai so huu, sach
WT_DIRTY = "DIRTY"        # co thay doi chua commit — KHONG dung lai
WT_STALE = "STALE"        # khong con tren dia, hoac chu da chet

_TEN_HOP_LE = re.compile(r"[^A-Za-z0-9._-]+")


def ten_an_toan(s: str, *, max_len: int = 40) -> str:
    """Ép một chuỗi tuỳ ý thành tên dùng được cho nhánh/thư mục.

    `WorktreeManager._kiem_ten` sẽ TỪ CHỐI ký tự lạ (đúng như thiết kế), nên
    việc làm sạch phải xảy ra TRƯỚC khi gọi nó — không phải bằng cách nới
    lỏng bộ kiểm ở tầng dưới.
    """
    sach = _TEN_HOP_LE.sub("-", str(s or "")).strip("-._")
    return (sach or "task")[:max_len]


@dataclass(frozen=True)
class WorktreeLease:
    """Một worktree đã gán cho một phiên, kèm cách nó tới được đây."""

    path: str
    branch: str
    base_sha: str
    session_id: str
    created: bool                # True = vua tao, False = dung lai
    reason: str = ""

    def to_dict(self) -> Dict:
        return {"path": self.path, "branch": self.branch,
                "base_sha": self.base_sha, "session_id": self.session_id,
                "created": self.created, "reason": self.reason}


class WorktreeCoordinator:
    """Tầng phối hợp worktree cho MỘT dự án."""

    def __init__(self, project_id: str, repo_root: Path, store: ControlStore, *,
                 manager: Optional[WorktreeManager] = None):
        self.project_id = project_id
        self.repo_root = Path(repo_root)
        self.store = store
        self.manager = manager if manager is not None else \
            WorktreeManager(self.repo_root)

    # -- truy van -----------------------------------------------------------

    def base_sha(self) -> str:
        return self.manager.base_sha()

    def is_dirty(self, path: str) -> bool:
        """Worktree có thay đổi chưa commit không.

        Hỏi `git` chứ không hỏi sổ: sổ chỉ biết thứ Control Center đã làm,
        còn một agent (hoặc chính người dùng) có thể đã sửa tệp trong đó
        giữa hai lần khởi động.
        """
        p = Path(path)
        if not p.exists():
            return False
        try:
            kq = subprocess.run(
                ["git", "-C", str(p), "status", "--porcelain", "-uall"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60, **an_cua_so())
        except (OSError, subprocess.SubprocessError):
            # Khong hoi duoc git thi coi nhu BAN. Doan "sach" o day nghia la
            # cho mot agent khac vao ghi de len cong viec chua luu cua agent
            # truoc — sai lam khong hoan tac duoc.
            return True
        if kq.returncode != 0:
            return True
        return bool((kq.stdout or "").strip())

    def duong_dan_da_doi(self, path: str) -> Optional[List[str]]:
        """Đường dẫn CHƯA COMMIT trong một worktree. `None` = không hỏi được.

        `-uall` liệt kê TỪNG tệp chưa theo dõi thay vì gộp thành một dòng
        thư mục (`?? pkg/`) — cùng lý do như `WorktreeManager.verify_scope`:
        bản gộp so phạm vi kém chính xác.

        Phân biệt `None` (không hỏi được) với `[]` (sạch) là bắt buộc: gộp
        hai thứ đó lại thì một lần `git` hỏng sẽ đọc thành "cây sạch".
        """
        p = Path(path)
        if not p.exists():
            return None
        try:
            kq = subprocess.run(
                ["git", "-C", str(p), "status", "--porcelain", "-uall"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60, **an_cua_so())
        except (OSError, subprocess.SubprocessError):
            return None
        if kq.returncode != 0:
            return None
        ra: List[str] = []
        for dong in (kq.stdout or "").splitlines():
            tep = dong[3:].strip().strip('"').replace("\\", "/")
            if " -> " in tep:                 # doi ten
                tep = tep.split(" -> ", 1)[1]
            if tep:
                ra.append(tep.strip("/"))
        return sorted(set(ra))

    @staticmethod
    def _trong_pham_vi(duong: Sequence[str], scope: Sequence[str]) -> bool:
        """Mọi đường dẫn có nằm trong phạm vi phiên sở hữu không."""
        if not duong:
            return True
        if not scope:
            return False
        pv = [str(x).replace("\\", "/").strip("/").lower() for x in scope if x]
        for d in duong:
            dd = str(d).replace("\\", "/").strip("/").lower()
            if not any(dd == q or dd.startswith(q + "/") for q in pv):
                return False
        return True

    def owner_of(self, path: str) -> str:
        h = self.store.worktree(str(path))
        return (h or {}).get("owner_session", "") or ""

    def worktrees(self) -> List[Dict]:
        return self.store.worktrees(self.project_id)

    # -- cap phat -----------------------------------------------------------

    def ensure_for(self, *, session_id: str, task_id: str,
                   base_sha: str = "", runtime_id: str = "",
                   scope: Sequence[str] = ()) -> WorktreeLease:
        """Cấp worktree cho một việc của một phiên. Dùng lại nếu AN TOÀN.

        AN TOÀN = phiên này đã sở hữu một cây, cây đó CÒN trên đĩa, và mọi
        thay đổi chưa commit trong đó đều NẰM TRONG `scope` phiên sở hữu.

        Vế cuối là điểm tinh tế, và bản đầu tiên làm sai nó: chỉ cần "cây
        bẩn" là từ chối dùng lại. Nghe an toàn, nhưng một phiên giữ ấm qua
        nhiều việc gần như LUÔN để lại thay đổi chưa commit từ việc trước —
        đó là công việc của chính nó. Kết quả là không bao giờ dùng lại được
        worktree, và cả ý tưởng "một phiên sở hữu một cây" mất sạch ý nghĩa.

        Cái THẬT SỰ đáng ngờ là thay đổi NGOÀI phạm vi: dấu hiệu có thứ khác
        đang ghi vào cây này, hoặc việc trước đã đi lạc. Lúc đó mới cấp cây
        mới — và cây cũ chỉ bị ĐÁNH DẤU `DIRTY`, không bao giờ bị xoá.
        """
        cu = self._worktree_cua_phien(session_id)
        if cu:
            duong = cu["path"]
            if not Path(duong).exists():
                self.danh_dau(duong, WT_STALE,
                              note="thư mục không còn trên đĩa")
            elif not self._ban_theo_cach_la(duong, scope):
                # BAN KHONG PHAI LA LY DO DU DE TU CHOI DUNG LAI.
                #
                # Mot phien giu am qua nhieu viec gan nhu LUON de lai thay
                # doi chua commit tu viec truoc — do la cong viec cua chinh
                # no, khong phai rac cua nguoi la. Tu choi moi cay ban nghia
                # la KHONG BAO GIO dung lai duoc worktree, va ca y tuong
                # "mot phien so huu mot cay" mat sach y nghia (da vap that:
                # bai kiem dung lai worktree hong vi dung ly do nay).
                #
                # Cai THAT SU nguy hiem la thay doi NGOAI pham vi phien so
                # huu — do la dau hieu co thu khac dang ghi vao cay nay,
                # hoac viec truoc da di lac. Chi luc do moi cap cay moi.
                self.store.luu_worktree(
                    path=duong, project_id=self.project_id,
                    branch=cu.get("branch", ""),
                    base_sha=cu.get("base_sha", ""), owner_session=session_id,
                    state=WT_ACTIVE, note=f"dùng lại cho {task_id}")
                self.store.ghi_su_kien(
                    "WORKTREE_REUSED", project_id=self.project_id,
                    task_id=task_id, session_id=session_id, detail=duong)
                return WorktreeLease(
                    path=duong, branch=cu.get("branch", ""),
                    base_sha=cu.get("base_sha", ""), session_id=session_id,
                    created=False,
                    reason="phiên đã sở hữu cây này; mọi thay đổi chưa commit "
                           "đều nằm trong phạm vi nó sở hữu")
            else:
                self.danh_dau(duong, WT_DIRTY,
                              note=f"thay đổi NGOÀI phạm vi khi {task_id} xin")
                self.store.ghi_su_kien(
                    "WORKTREE_DIRTY", project_id=self.project_id,
                    task_id=task_id, session_id=session_id, level="WARNING",
                    detail=(f"không dùng lại {duong} — có thay đổi chưa commit "
                            f"NGOÀI phạm vi phiên sở hữu ({list(scope)}). Cấp "
                            f"cây mới; KHÔNG xoá cây cũ."))
        return self.tao_moi(session_id=session_id, task_id=task_id,
                            base_sha=base_sha, runtime_id=runtime_id)

    def _ban_theo_cach_la(self, path: str, scope: Sequence[str]) -> bool:
        """Cây này bẩn theo cách ĐÁNG NGỜ không?

        `False` = dùng lại được: cây sạch, hoặc chỉ có thay đổi chưa commit
        NẰM TRONG phạm vi phiên sở hữu (đó là công việc của chính phiên).
        `True` = cấp cây mới: có thay đổi ngoài phạm vi, hoặc không hỏi được
        `git`.

        Không hỏi được `git` thì trả `True` (đáng ngờ). Đoán "sạch" ở đây
        nghĩa là cho một agent ghi đè lên công việc chưa lưu của agent
        trước — sai lầm không hoàn tác được.
        """
        duong = self.duong_dan_da_doi(path)
        if duong is None:
            return True
        if not duong:
            return False
        return not self._trong_pham_vi(duong, scope)

    def tao_moi(self, *, session_id: str, task_id: str, base_sha: str = "",
                runtime_id: str = "") -> WorktreeLease:
        """Tạo worktree cô lập mới. Tên mang cả phiên lẫn việc.

        Nhét `session_id` vào tên là cách chống trùng đã học được từ V4:
        `WorktreeManager.create` TỪ CHỐI ghi đè (đúng), nên chạy lại cùng
        một `task_id` mà không có phần phân biệt sẽ hỏng ngay từ nút đầu.
        """
        goc = base_sha or self.base_sha()
        chu = ten_an_toan(runtime_id or session_id, max_len=24)
        ten = ten_an_toan(f"{task_id}-{session_id[-6:]}")
        try:
            h: WorktreeHandle = self.manager.create(chu, ten, base_sha=goc)
        except WorktreeError as exc:
            self.store.ghi_su_kien(
                "WORKTREE_FAILED", project_id=self.project_id, task_id=task_id,
                session_id=session_id, level="ERROR", detail=str(exc)[:400])
            raise

        duong = str(h.path)
        self.store.luu_worktree(
            path=duong, project_id=self.project_id, branch=h.branch,
            base_sha=h.base_sha, owner_session=session_id, state=WT_ACTIVE,
            note=f"tạo cho {task_id}")
        self.store.ghi_su_kien(
            "WORKTREE_CREATED", project_id=self.project_id, task_id=task_id,
            session_id=session_id, detail=f"{duong} @ {h.branch}",
            meta={"branch": h.branch, "base_sha": h.base_sha})
        return WorktreeLease(path=duong, branch=h.branch, base_sha=h.base_sha,
                             session_id=session_id, created=True,
                             reason="chưa có worktree dùng lại được")

    # -- loai tru -----------------------------------------------------------

    def assert_exclusive(self, path: str, session_id: str) -> None:
        """Chặn hai phiên cùng ghi một worktree. Ném thay vì cảnh báo.

        Đây là bất biến trung tâm của cả module. Một cảnh báo ở đây sẽ bị
        nuốt trong log lúc 3 giờ sáng và hai agent vẫn giẫm lên nhau; một
        `WorktreeError` thì dừng việc lại ngay và hiện lên bảng điều khiển.
        """
        chu = self.owner_of(path)
        if chu and chu != session_id:
            raise WorktreeError(
                f"worktree {path} đang do phiên {chu} sở hữu — phiên "
                f"{session_id} KHÔNG được ghi vào đó. Hai agent cùng ghi một "
                f"cây làm việc là hỏng không dựng lại được; cấp cây riêng.")

    def danh_dau(self, path: str, state: str, *, note: str = "") -> None:
        h = self.store.worktree(str(path)) or {}
        self.store.luu_worktree(
            path=str(path), project_id=self.project_id,
            branch=h.get("branch", ""), base_sha=h.get("base_sha", ""),
            owner_session=("" if state in (WT_STALE, WT_IDLE)
                           else h.get("owner_session", "")),
            state=state, note=note)

    def nha(self, session_id: str, *, note: str = "") -> None:
        """Phiên nhả worktree của nó. KHÔNG xoá — chỉ đổi chủ về rỗng."""
        for h in self.worktrees():
            if h.get("owner_session") != session_id:
                continue
            ban = self.is_dirty(h["path"])
            self.danh_dau(h["path"], WT_DIRTY if ban else WT_IDLE,
                          note=note or ("còn thay đổi chưa commit"
                                        if ban else "phiên đã nhả"))

    # -- doi soat -----------------------------------------------------------

    def go_bo(self, path: str, *, xac_nhan: bool = False,
              ly_do: str = "") -> Dict[str, object]:
        """Gỡ MỘT worktree khỏi đĩa. CHỈ khi người vận hành yêu cầu.

        Luật "KHÔNG TỰ XOÁ WORKTREE" của V0.1 không đổi: không đường tự động
        nào gọi hàm này. Nó tồn tại cho đúng một việc — dọn cây làm việc của
        các lượt chứng minh sau khi bằng chứng đã được ghi lại — và mọi lần
        gọi đều phải nói rõ `xac_nhan=True` cùng một lý do.

        BỐN RÀO, tất cả fail-closed:

          1. đường dẫn phải nằm TRONG `.router/worktrees/` của kho này. Ngoài
             ra: từ chối. (`resolve()` trước khi so, nên junction không lách
             được — đã kiểm bằng bài kiểm.)
          2. phải là một worktree Router BIẾT — có hàng trong sổ. Một thư mục
             lạ nằm trong đó không phải thứ ta được phép xoá.
          3. KHÔNG được có phiên nào còn sống đang sở hữu nó.
          4. `xac_nhan=True` tường minh.

        Trả về mô tả việc đã làm; `git worktree remove` lo phần metadata.
        """
        if not xac_nhan:
            raise WorktreeError(
                f"gỡ worktree {path!r} là thao tác không hoàn tác được — "
                f"truyền `xac_nhan=True` nếu thật sự muốn.")
        goc = self.manager.worktree_root.resolve()
        try:
            duong = Path(path).resolve()
            duong.relative_to(goc)
        except (ValueError, OSError) as exc:
            raise WorktreeError(
                f"TỪ CHỐI: {path!r} nằm ngoài {goc} — chỉ gỡ được worktree "
                f"do Router quản lý.") from exc

        hang = self.store.worktree(str(path)) or self.store.worktree(str(duong))
        if hang is None:
            raise WorktreeError(
                f"TỪ CHỐI: {path!r} không có trong sổ Control Center. Một thư "
                f"mục lạ nằm trong `.router/worktrees/` không phải thứ công "
                f"cụ này được phép xoá.")

        chu = (hang.get("owner_session") or "").strip()
        if chu:
            s = self.store.session(chu)
            if s is not None and s.state.alive:
                raise WorktreeError(
                    f"TỪ CHỐI: phiên {chu} ({s.state.value}) vẫn còn sống và "
                    f"đang sở hữu cây này. Dừng phiên trước đã.")

        ban = self.is_dirty(str(duong))
        self.manager.remove(duong, force=True)
        self.store.luu_worktree(
            path=str(path), project_id=self.project_id,
            branch=hang.get("branch", ""), owner_session="", state=WT_STALE,
            note=f"đã gỡ khỏi đĩa: {ly_do}"[:300])
        self.store.ghi_su_kien(
            "WORKTREE_REMOVED", project_id=self.project_id, level="WARNING",
            detail=(f"gỡ {path} khỏi đĩa (bẩn={ban}) — {ly_do}"),
            meta={"path": str(path), "branch": hang.get("branch", ""),
                  "dirty": ban, "reason": ly_do})
        return {"path": str(path), "branch": hang.get("branch", ""),
                "was_dirty": ban}

    def doi_soat(self) -> Dict[str, List[str]]:
        """Đối soát sổ với thực tế trên đĩa. Chạy lúc khởi động.

        Ba nhóm lệch, và cả ba đều chỉ ĐÁNH DẤU, không xoá:

            `missing`  — sổ có, đĩa không còn.
            `dirty`    — còn thay đổi chưa commit.
            `untracked`— git biết, sổ không biết (ai đó tạo tay, hoặc một
                         lượt chạy Router V4 trực tiếp không qua đây).

        Nhóm thứ ba quan trọng hơn vẻ ngoài của nó: Router V4 vẫn chạy
        được độc lập với Control Center, và những worktree nó tạo là THẬT.
        Coi chúng như không tồn tại rồi cấp đè lên là cách làm hỏng một
        lượt chạy đang diễn ra.
        """
        thieu: List[str] = []
        ban: List[str] = []
        la: List[str] = []

        biet = {h["path"] for h in self.worktrees()}
        for h in self.worktrees():
            p = h["path"]
            if not Path(p).exists():
                thieu.append(p)
                self.danh_dau(p, WT_STALE, note="đối soát: không còn trên đĩa")
            elif self.is_dirty(p):
                ban.append(p)
                self.danh_dau(p, WT_DIRTY, note="đối soát: chưa commit")

        try:
            tren_git = self.manager.list_worktrees()
        except WorktreeError:
            tren_git = []
        goc_wt = str(self.manager.worktree_root.resolve()).replace("\\", "/")
        for w in tren_git:
            p = w.get("worktree", "")
            if not p:
                continue
            chuan = str(Path(p).resolve())
            if not chuan.replace("\\", "/").startswith(goc_wt):
                continue                      # khong phai worktree cua router
            if chuan in biet or p in biet:
                continue
            la.append(chuan)
            self.store.luu_worktree(
                path=chuan, project_id=self.project_id,
                branch=w.get("branch", ""), owner_session="", state=WT_IDLE,
                note="phát hiện lúc đối soát; không do Control Center tạo")

        if thieu or ban or la:
            self.store.ghi_su_kien(
                "WORKTREE_RECONCILE", project_id=self.project_id,
                level="WARNING",
                detail=(f"thiếu={len(thieu)} bẩn={len(ban)} lạ={len(la)} — "
                        f"chỉ đánh dấu, KHÔNG xoá gì"),
                meta={"missing": thieu, "dirty": ban, "untracked": la})
        return {"missing": thieu, "dirty": ban, "untracked": la}

    # -- noi bo -------------------------------------------------------------

    def _worktree_cua_phien(self, session_id: str) -> Optional[Dict]:
        for h in self.worktrees():
            if h.get("owner_session") == session_id and \
                    h.get("state") in (WT_ACTIVE, WT_IDLE):
                return h
        return None
