"""Ảnh chụp dự án TẤT ĐỊNH — thứ Leader đọc thay vì đi hỏi một agent.

VÌ SAO TỆP NÀY TỒN TẠI. Trước V0.3, mọi câu người dùng gõ đều thành một
việc Router. Hỏi "project tới đâu rồi?" cũng dựng một phiên agent, chọn
model, có khi dựng cả worktree — để trả lời một câu mà **sổ và `git` đã
biết sẵn**. Đó vừa chậm, vừa tốn quota, vừa cho ra câu trả lời kém tin cậy
hơn: một agent đoán trạng thái, còn `git rev-parse` thì biết.

Nên: mọi thứ ở đây đọc từ **sổ SQLite** và **`git`**. Không gọi model,
không sinh worker, không chạm mạng. Một lần chụp mất vài chục mili-giây.

RANH GIỚI: module này chỉ ĐỌC. Nó không tạo worktree, không đổi trạng thái
việc, không nhả khoá. Leader dùng nó để TRẢ LỜI, còn muốn LÀM gì thì phải
đi qua Router V4 như mọi việc khác.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional  # noqa: F401  (Optional dùng ở `chup`)

from scripts.router_v3.tien_trinh import an_cua_so

#: Trần cho mọi lệnh `git` ở đây. Một kho hỏng không được treo cả ô chat.
HAN_GIT = 20.0

#: Bao nhiêu commit gần đây là đủ để trả lời "đang làm tới đâu".
SO_COMMIT = 8

#: Bao nhiêu việc đã xong gần đây thì còn đáng nhắc.
SO_VIEC_XONG = 8

#: Sự kiện gần đây cho Leader. Giữ NHỎ có chủ ý: đây là ngữ cảnh cho một
#: lượt hội thoại, không phải trang nhật ký.
SO_SU_KIEN = 25


def _git(kho: str, *args: str) -> str:
    """`git` trong `kho`, trả stdout đã strip. Hỏng thì trả rỗng.

    Nuốt lỗi có chủ ý: ảnh chụp phải luôn trả về được. Một kho chưa có
    commit nào, một thư mục không phải kho, một `git` chưa cài — tất cả
    đều là "không biết", và cách nói "không biết" là để trống trường đó,
    KHÔNG phải ném ra giữa một câu hỏi hội thoại.
    """
    try:
        # `an_cua_so()`: ảnh chụp chạy ~6 lệnh `git` cho MỖI tin nhắn chat,
        # và trong bản `--noconsole` mỗi lệnh sẽ nhấp một cửa sổ console
        # rồi giành focus. Đây là chỗ nhấp nháy nhiều nhất trong app.
        p = subprocess.run(["git", "-C", kho, *args], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=HAN_GIT, **an_cua_so())
    except (OSError, subprocess.SubprocessError):
        return ""
    return (p.stdout or "").strip() if p.returncode == 0 else ""


@dataclass
class AnhChupDuAn:
    """Trạng thái dự án ở MỘT thời điểm. Thuần dữ liệu, tuần tự hoá được."""

    project_id: str = ""
    name: str = ""
    repo_path: str = ""
    la_kho_git: bool = False

    branch: str = ""
    head: str = ""
    head_ngan: str = ""
    sach: bool = True
    tep_doi: List[str] = field(default_factory=list)
    commit_gan_day: List[str] = field(default_factory=list)

    dang_chay: List[Dict] = field(default_factory=list)
    dang_cho: List[Dict] = field(default_factory=list)
    bi_chan: List[Dict] = field(default_factory=list)
    vua_xong: List[Dict] = field(default_factory=list)

    phien: List[Dict] = field(default_factory=list)
    worktree: List[Dict] = field(default_factory=list)
    khoa: List[Dict] = field(default_factory=list)
    su_kien: List[Dict] = field(default_factory=list)
    usage: Dict = field(default_factory=dict)
    tai_lieu: List[str] = field(default_factory=list)

    che_do: str = "AUTO"
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items()}

    # -- thu Leader doc ------------------------------------------------------

    def tom_tat(self) -> str:
        """Bản NGẮN cho ngữ cảnh của Leader — đọc được, không phải JSON thô.

        Cố tình ngắn: nhồi cả sổ vào mỗi lượt hội thoại vừa tốn token vừa
        làm model bỏ sót thứ quan trọng. Chi tiết nằm ở `to_dict()` cho
        những hành động thật sự cần.
        """
        d = [f"DỰ ÁN: {self.name} ({self.project_id})",
             f"kho   : {self.repo_path}"]
        if not self.la_kho_git:
            d.append("  (!) đường dẫn này KHÔNG phải kho git")
        else:
            d.append(f"nhánh : {self.branch or '(không rõ)'} @ "
                     f"{self.head_ngan or '(chưa có commit)'}")
            d.append(f"cây làm việc: {'sạch' if self.sach else 'CÓ THAY ĐỔI'}"
                     + (f" ({len(self.tep_doi)} tệp)" if self.tep_doi else ""))
            if self.commit_gan_day:
                d.append("commit gần đây:")
                d += [f"  {c}" for c in self.commit_gan_day[:5]]
        d.append(f"chế độ định tuyến: {self.che_do}")

        def _ke(nhan, ds):
            if not ds:
                return
            d.append(f"{nhan} ({len(ds)}):")
            for t in ds[:6]:
                d.append(f"  [{t.get('task_id')}] {t.get('state')} "
                         f"— {str(t.get('title'))[:70]}")

        _ke("việc ĐANG CHẠY", self.dang_chay)
        _ke("việc ĐANG CHỜ", self.dang_cho)
        _ke("việc BỊ CHẶN", self.bi_chan)
        _ke("việc VỪA XONG", self.vua_xong)
        if not (self.dang_chay or self.dang_cho or self.bi_chan
                or self.vua_xong):
            d.append("chưa có việc nào trong dự án này.")

        if self.phien:
            d.append(f"phiên agent ({len(self.phien)}):")
            for s in self.phien[:6]:
                d.append(f"  {s.get('session_id')} {s.get('provider')}/"
                         f"{s.get('runtime_id')} {s.get('model_id')} "
                         f"{s.get('state')}"
                         + (f" — việc {s['current_task']}"
                            if s.get("current_task") else ""))
        else:
            d.append("không có phiên agent nào đang sống.")

        if self.worktree:
            d.append(f"worktree đang ghi sổ: {len(self.worktree)}")
        if self.khoa:
            d.append(f"khoá đang giữ: {len(self.khoa)}")
        if self.usage:
            d.append(f"usage: {self.usage}")
        return "\n".join(d)


def chup(store, project, *, che_do: str = "AUTO",
         usage: Optional[Dict] = None) -> AnhChupDuAn:
    """Chụp một dự án. CHỈ đọc sổ + `git`; không model, không worker."""
    from scripts.control_center.bootstrap import la_kho_git

    a = AnhChupDuAn(project_id=project.project_id, name=project.name,
                    repo_path=str(project.repo_path), che_do=che_do)
    a.la_kho_git = la_kho_git(project.repo_path)

    if a.la_kho_git:
        kho = str(project.repo_path)
        a.branch = _git(kho, "rev-parse", "--abbrev-ref", "HEAD")
        a.head = _git(kho, "rev-parse", "HEAD")
        a.head_ngan = a.head[:10]
        tt = _git(kho, "status", "--porcelain")
        a.sach = not tt
        a.tep_doi = [d[3:].strip() for d in tt.splitlines()[:40] if d[3:].strip()]
        lg = _git(kho, "log", f"-{SO_COMMIT}", "--pretty=%h %s")
        a.commit_gan_day = [x for x in lg.splitlines() if x.strip()]
        # Tai lieu ban giao / bao cao — tro DUONG DAN, khong doc noi dung.
        for mau in ("docs/HANDOFF.md", "docs/CONTROL_CENTER.md"):
            if (Path(kho) / mau).is_file():
                a.tai_lieu.append(mau)
        bc = Path(kho) / "docs" / "reports"
        if bc.is_dir():
            moi = sorted(bc.glob("*.md"),
                         key=lambda p: p.stat().st_mtime, reverse=True)[:3]
            a.tai_lieu += [f"docs/reports/{p.name}" for p in moi]

    pid = project.project_id
    for t in store.tasks(pid):
        d = {"task_id": t.task_id, "title": t.title,
             "state": t.state.value if hasattr(t.state, "value") else t.state,
             "owner_session": t.owner_session, "attempts": t.attempts}
        s = d["state"]
        if s == "RUNNING":
            a.dang_chay.append(d)
        elif s in ("QUEUED", "WAITING", "REVIEW"):
            a.dang_cho.append(d)
        elif s == "BLOCKED":
            d["blocked_reason"] = t.blocked_reason
            a.bi_chan.append(d)
        elif s in ("DONE", "FAILED"):
            a.vua_xong.append(d)
    a.vua_xong = a.vua_xong[:SO_VIEC_XONG]

    a.phien = [s.to_dict() for s in store.sessions(pid)
               if (s.state.value if hasattr(s.state, "value") else s.state)
               != "STOPPED"]
    a.worktree = list(store.worktrees(pid))
    try:
        from scripts.control_center.locks import LockManager
        a.khoa = LockManager(store).snapshot(pid).get("held", []) \
            if isinstance(LockManager(store).snapshot(pid), dict) else []
    except Exception:                                       # noqa: BLE001
        a.khoa = []
    a.su_kien = [
        {"kind": e["kind"], "level": e["level"], "detail": e["detail"][:200],
         "task_id": e.get("task_id", ""), "ts": e["ts"]}
        for e in store.su_kien(project_id=pid, limit=SO_SU_KIEN)]
    # KHONG BIA SO. Khong do duoc thi de trong — cung luat voi `usage.py`.
    a.usage = dict(usage or {})
    return a
