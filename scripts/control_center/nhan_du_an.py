# -*- coding: utf-8 -*-
"""NHẬN DỰ ÁN HIỆN CÓ (adopt existing project) — CHỈ ĐỌC, V0.7.

Router tới giờ chỉ biết "tạo dự án mới". Muốn nó quản một dự án THẬT đã sống
nhiều tháng (fanfic.world / CapCut-TTS-App) thì phải có đường NHẬN: chỉ vào một
thư mục đã có, rồi Router tự dò xem nó là gì, đã biết gì về nó, và còn thiếu gì.

BA LUẬT CỦA TỆP NÀY

1. **CHỈ ĐỌC kho đích.** Không `git init`, không commit, không chỉnh tệp, không
   copy/di chuyển kho. Mọi lệnh git ở đây là lệnh ĐỌC với tham số cố định, có
   `timeout`, có `**an_cua_so()`. Nhận một dự án KHÔNG được để lại dấu vết nào
   trong kho của người ta.
2. **KHÔNG TẠO BẢN THỨ HAI.** Nếu Router đã có một dự án trỏ vào ĐÚNG thư mục
   làm việc đó thì NHẬN = LIÊN KẾT LẠI bản đã có, không sinh `fanfic-2`. Khoá
   để so là **gốc worktree đã phân giải**, không phải `--git-common-dir`: kho
   này có nhiều worktree (`router-control-center` và `CapCut-TTS-App` dùng CHUNG
   một `.git`) và chúng là HAI dự án khác nhau trong Router.
3. **Danh tính không đến từ nhánh.** `project_id` là chuỗi bền, giữ trong
   `control.db`; namespace ký ức suy từ nó (xem `memory/model.khong_gian_ten`).
   Đổi nhánh, đổi HEAD, dựng lại app, đổi worktree Router — dự án vẫn là nó.

Không bí mật: URL remote được LỌC trước khi vào bản ghi (một remote dạng
`https://user:token@host/...` là chuyện thường), và không đọc `.env`/khoá.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.router_v3.tien_trinh import an_cua_so

#: Tệp/thư mục mang Ý NGHĨA DỰ ÁN mà ta đi tìm (chỉ kiểm tồn tại, không đọc hết).
DAU_HIEU_TAI_LIEU = ("docs", "README.md", "CLAUDE.md", "docs/HANDOFF.md",
                     "docs/reports", "docs/ADMIN.md", "pyproject.toml",
                     "package.json", "requirements.txt")

#: Thư mục KHÔNG bao giờ đọc (bí mật / rác / nặng).
BO_QUA = {".git", "node_modules", ".venv", "venv", "__pycache__", ".router",
          "dist", "build", "installer_output", ".next", ".claude"}

_CRED_URL = re.compile(r"(?<=://)[^/@\s]+:[^/@\s]+@")


def _git(repo: Path, *args: str, han: float = 30.0) -> Optional[subprocess.CompletedProcess]:
    """MỘT lệnh git CHỈ ĐỌC. `None` nếu không chạy được. Không cửa sổ."""
    try:
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=han, **an_cua_so())
    except (OSError, subprocess.SubprocessError):
        return None


def _ra(p: Optional[subprocess.CompletedProcess]) -> str:
    return (p.stdout or "").strip() if (p is not None and p.returncode == 0) else ""


def loc_url(url: str) -> str:
    """Bỏ `user:pass@` khỏi URL remote — không bao giờ ghi credential vào sổ."""
    return _CRED_URL.sub("", str(url or "").strip())


# --------------------------------------------------------------- dau hieu ---

@dataclass
class DauHieuKho:
    """Nhận dạng kho — thứ ổn định, không phụ thuộc nhánh."""
    duong: str = ""                 # đường người dùng chỉ vào
    goc_worktree: str = ""          # gốc worktree đã phân giải (KHOÁ so trùng)
    goc_git_chung: str = ""         # --git-common-dir (nhiều worktree dùng chung)
    la_git: bool = False
    ly_do_khong_git: str = ""
    nhanh: str = ""
    head: str = ""
    remote: str = ""
    remote_url: str = ""            # ĐÃ LỌC credential
    so_commit: int = 0
    commit_dau_tien: str = ""       # mốc "tuổi" dự án
    sach: bool = True               # working tree sạch?

    def to_dict(self) -> Dict:
        return {"duong": self.duong, "goc_worktree": self.goc_worktree,
                "goc_git_chung": self.goc_git_chung, "la_git": self.la_git,
                "ly_do_khong_git": self.ly_do_khong_git, "nhanh": self.nhanh,
                "head": self.head, "remote": self.remote,
                "remote_url": self.remote_url, "so_commit": self.so_commit,
                "commit_dau_tien": self.commit_dau_tien, "sach": self.sach}


def kham_pha_kho(duong: object) -> DauHieuKho:
    """Dò nhận dạng kho. CHỈ ĐỌC, không bao giờ ném."""
    p = Path(str(duong)).expanduser()
    d = DauHieuKho(duong=str(p))
    if not p.is_dir():
        d.ly_do_khong_git = f"không có thư mục: {p}"
        return d
    top = _ra(_git(p, "rev-parse", "--show-toplevel"))
    if not top:
        d.ly_do_khong_git = "không phải kho git (hoặc git không chạy được)"
        try:
            d.goc_worktree = str(p.resolve())
        except OSError:
            d.goc_worktree = str(p)
        return d
    d.la_git = True
    try:
        d.goc_worktree = str(Path(top).resolve())
    except OSError:
        d.goc_worktree = top
    cd = _ra(_git(p, "rev-parse", "--git-common-dir"))
    if cd:
        try:
            d.goc_git_chung = str((Path(top) / cd).resolve()) if not Path(cd).is_absolute() \
                else str(Path(cd).resolve())
        except OSError:
            d.goc_git_chung = cd
    d.nhanh = _ra(_git(p, "rev-parse", "--abbrev-ref", "HEAD"))
    d.head = _ra(_git(p, "rev-parse", "HEAD"))
    r = _ra(_git(p, "remote"))
    d.remote = (r.splitlines() or [""])[0].strip()
    if d.remote:
        d.remote_url = loc_url(_ra(_git(p, "remote", "get-url", d.remote)))
    try:
        d.so_commit = int(_ra(_git(p, "rev-list", "--count", "HEAD")) or 0)
    except ValueError:
        d.so_commit = 0
    # COMMIT GOC (tuoi du an). `log --reverse -n1` KHONG cho commit dau tien:
    # git ap dung gioi han TRUOC khi dao thu tu, nen no tra ve commit MOI NHAT
    # (do duoc: tra ve dung HEAD). Dung `rev-list --max-parents=0`.
    goc_c = (_ra(_git(p, "rev-list", "--max-parents=0", "HEAD", han=60.0))
             .splitlines() or [""])[-1].strip()
    if goc_c:
        d.commit_dau_tien = _ra(_git(p, "log", "-1", "--format=%h %ad %s",
                                     "--date=short", goc_c))[:160]
    d.sach = not _ra(_git(p, "status", "--porcelain"))
    return d


# ------------------------------------------------------------ nguon du an ---

def kham_pha_nguon(cc, duong: object, project_id: str = "") -> Dict:
    """Những NGUỒN HIỂU BIẾT Router có cho dự án này. CHỈ ĐỌC, không ghi gì.

    Không đọc nội dung hàng trăm tệp — chỉ ĐẾM và LIỆT KÊ đường dẫn, để phần
    dựng Viên nang quyết định đọc cái nào.
    """
    p = Path(str(duong)).expanduser()
    ra: Dict = {"tai_lieu": {}, "ky_uc": {}, "so_router": {}, "phien_claude": {},
                "quan_sat": {}, "provider": {}, "duong_quan_trong": []}

    # 1. Tai lieu / HANDOFF / bao cao / kien truc.
    td: Dict = {"co": [], "so_doc": 0, "so_bao_cao": 0, "handoff": ""}
    for ten in DAU_HIEU_TAI_LIEU:
        if (p / ten).exists():
            td["co"].append(ten)
    d_docs = p / "docs"
    if d_docs.is_dir():
        try:
            td["so_doc"] = sum(1 for x in d_docs.rglob("*.md") if x.is_file())
        except OSError:
            pass
    d_rep = p / "docs" / "reports"
    if d_rep.is_dir():
        try:
            td["so_bao_cao"] = sum(1 for x in d_rep.glob("*.md") if x.is_file())
        except OSError:
            pass
    for ung in ("docs/HANDOFF.md", "HANDOFF.md", "docs/handoffs"):
        if (p / ung).exists():
            td["handoff"] = ung
            break
    ra["tai_lieu"] = td

    # 2. Ky uc du an da co (so CHINH TAC, khong tao moi).
    if project_id:
        kc = getattr(cc, "ky_uc", None)
        if kc is not None:
            try:
                tk = kc.thong_ke(project_id)
                dem = tk.get("dem") or {}
                ra["ky_uc"] = {"san_sang": bool(tk.get("san_sang", True)),
                               "ns": (kc.san_sang(project_id) or {}).get("ns", ""),
                               "su_kien": dem.get("su_kien", 0),
                               "ky_uc": dem.get("ky_uc", 0),
                               "quyet_dinh": dem.get("quyet_dinh", 0),
                               "su_co": dem.get("ky_uc_incident", 0),
                               "rang_buoc": dem.get("ky_uc_constraint", 0),
                               "bang_chung": dem.get("bang_chung", 0),
                               "vien_nang": dem.get("vien_nang", 0),
                               "diem_dung": dem.get("diem_dung", 0)}
            except Exception as exc:                        # noqa: BLE001
                ra["ky_uc"] = {"loi": f"{type(exc).__name__}: {exc}"[:160]}
        # 3. So Router (viec/phien/su kien) cua dung du an.
        try:
            ts = cc.store.tasks(project_id, limit=2000)
            ra["so_router"] = {
                "viec": len(ts),
                "viec_xong": sum(1 for t in ts if t.state.value == "DONE"),
                "viec_hong": sum(1 for t in ts if t.state.value == "FAILED"),
                "phien": len(cc.store.sessions(project_id)),
                "tin_chat": len(cc.store.chat(project_id, limit=5000))}
        except Exception as exc:                            # noqa: BLE001
            ra["so_router"] = {"loi": f"{type(exc).__name__}: {exc}"[:160]}

    # 4. Phien Claude KHOP KHO (theo `git worktree list`) — chi dem, khong doc.
    try:
        from scripts.control_center.memory.nhap_khau import PhienClaudeAdapter
        n = PhienClaudeAdapter(str(p))
        slugs = n.worktrees()
        thu_muc = n.thu_muc()
        ra["phien_claude"] = {"slug": list(slugs)[:6], "so_slug": len(slugs),
                              "thu_muc_co_that": len(thu_muc),
                              "so_tep": sum(1 for d in thu_muc
                                            for _ in d.glob("*.jsonl"))}
    except Exception as exc:                                # noqa: BLE001
        ra["phien_claude"] = {"loi": f"{type(exc).__name__}: {exc}"[:120]}

    # 5. Quan sat SONG — provider nao KHAI cho dung du an nay. Chi doc KHAI
    # BAO (loai/id/host/unit), khong bao gio doc khoa: lược đồ đã cấm nội dung
    # bí mật, chỉ cho `key_path`.
    try:
        from scripts.control_center.observability import config as ocf
        c = ocf.nap()
        nhom = ((c.get("projects") or {}).get(project_id) or {}) if project_id else {}
        prov = nhom.get("providers") or []
        ra["quan_sat"] = {
            "co_cau_hinh": bool(prov), "so_probe": len(prov),
            "probe": [{"loai": x.get("type", ""), "id": x.get("id", ""),
                       "unit": x.get("unit", ""),
                       "host": ("(đã khai)" if x.get("host") else "")}
                      for x in prov][:8]}
    except Exception as exc:                                # noqa: BLE001
        ra["quan_sat"] = {"loi": f"{type(exc).__name__}: {exc}"[:120]}

    # 6. Tai nguyen agent/provider — tu fabric dang song.
    try:
        f = getattr(cc, "fabric", None)
        if f is not None:
            rts = list(getattr(f, "runtimes", {}).values())
            ag = [r for r in rts if getattr(r, "provider", "") == "antigravity"]
            ra["provider"] = {
                "runtime": len(rts),
                "antigravity": len(ag),
                "tai_khoan_ag": sorted({getattr(r, "account_id", "") for r in ag} - {""}),
                "provider": sorted({getattr(r, "provider", "") for r in rts} - {""})}
    except Exception as exc:                                # noqa: BLE001
        ra["provider"] = {"loi": f"{type(exc).__name__}: {exc}"[:120]}

    # 7. Duong quan trong (thu muc cap 1 co y nghia).
    try:
        for x in sorted(p.iterdir()):
            if x.is_dir() and x.name not in BO_QUA and not x.name.startswith("."):
                ra["duong_quan_trong"].append(x.name)
    except OSError:
        pass
    ra["duong_quan_trong"] = ra["duong_quan_trong"][:24]
    return ra


# ----------------------------------------------------------------- nhan -----

@dataclass
class KetQuaNhan:
    """Kết quả một lần nhận dự án."""
    ok: bool = False
    project_id: str = ""
    ten: str = ""
    moi: bool = False              # có ĐĂNG KÝ mới không
    lien_ket_lai: bool = False     # đã có -> chỉ liên kết/đối chiếu
    ly_do: str = ""
    kho: Optional[DauHieuKho] = None
    nguon: Dict = field(default_factory=dict)
    ghi_chu: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {"ok": self.ok, "project_id": self.project_id, "ten": self.ten,
                "moi": self.moi, "lien_ket_lai": self.lien_ket_lai,
                "ly_do": self.ly_do,
                "kho": self.kho.to_dict() if self.kho else None,
                "nguon": self.nguon, "ghi_chu": list(self.ghi_chu)}


def _cung_mot_cho(a: str, b: str) -> bool:
    """Hai đường có trỏ CÙNG một thư mục làm việc? (Windows: không phân biệt
    hoa thường; so sau khi phân giải)."""
    if not a or not b:
        return False
    try:
        pa, pb = Path(a).resolve(), Path(b).resolve()
    except OSError:
        pa, pb = Path(a), Path(b)
    if os.name == "nt":
        return str(pa).lower() == str(pb).lower()
    return pa == pb


def tim_du_an_trung(store, goc_worktree: str) -> Optional[str]:
    """`project_id` của dự án ĐÃ CÓ trỏ vào đúng thư mục đó, hoặc `None`.

    So theo GỐC WORKTREE, không theo `.git` chung: hai worktree của cùng một
    kho là hai dự án khác nhau trong Router (Fanfic vs Router Control Center).
    """
    try:
        ds = store.projects()
    except Exception:                                       # noqa: BLE001
        return None
    for pj in ds:
        rp = getattr(pj, "repo_path", "") or ""
        if _cung_mot_cho(rp, goc_worktree):
            return pj.project_id
        # `repo_path` co the tro vao mot thu muc CON cua worktree.
        d = kham_pha_kho(rp) if rp else None
        if d is not None and d.la_git and _cung_mot_cho(d.goc_worktree, goc_worktree):
            return pj.project_id
    return None


def nhan_du_an(cc, duong: object, *, ten: str = "", project_id: str = "",
               ghi_su_kien: bool = True) -> KetQuaNhan:
    """NHẬN một dự án hiện có. CHỈ ĐỌC kho đích. Idempotent.

    Đã có dự án trỏ đúng thư mục đó -> LIÊN KẾT LẠI (`lien_ket_lai=True`),
    không bao giờ sinh bản thứ hai. Chưa có -> đăng ký với `project_id` ổn
    định (người dùng đặt, hoặc suy từ tên thư mục) và KHÔNG đổi về sau.
    """
    kq = KetQuaNhan()
    d = kham_pha_kho(duong)
    kq.kho = d
    if not d.goc_worktree:
        kq.ly_do = d.ly_do_khong_git or "đường dẫn không dùng được"
        return kq
    if not d.la_git:
        # Van nhan duoc: mot du an co the khong dung git. Noi ro de nguoi biet
        # phan lich su git se THIEU, thay vi im lang.
        kq.ghi_chu.append(f"không phải kho git — {d.ly_do_khong_git}; "
                          "phần lịch sử/nhánh sẽ là UNKNOWN")

    da_co = tim_du_an_trung(cc.store, d.goc_worktree)
    if da_co:
        kq.ok, kq.project_id, kq.lien_ket_lai = True, da_co, True
        try:
            pj = cc.store.project(da_co)
            kq.ten = getattr(pj, "name", "") or da_co
        except Exception:                                   # noqa: BLE001
            kq.ten = da_co
        kq.ly_do = (f"dự án {da_co!r} đã trỏ vào đúng thư mục này — LIÊN KẾT "
                    f"LẠI, không tạo bản thứ hai")
        kq.nguon = kham_pha_nguon(cc, d.goc_worktree, da_co)
    else:
        pid = (project_id or "").strip() or _suy_project_id(d.goc_worktree)
        # `project_id` phai chua tung dung cho MOT CHO KHAC.
        try:
            cu = cc.store.project(pid)
        except Exception:                                   # noqa: BLE001
            cu = None
        if cu is not None and not _cung_mot_cho(getattr(cu, "repo_path", ""),
                                                d.goc_worktree):
            kq.ly_do = (f"project_id {pid!r} đã dùng cho kho khác "
                        f"({getattr(cu, 'repo_path', '')}) — hãy đặt tên khác")
            return kq
        from scripts.control_center.model import Project
        cc.them_project(Project(project_id=pid,
                                name=(ten or "").strip() or Path(d.goc_worktree).name,
                                repo_path=d.goc_worktree))
        kq.ok, kq.project_id, kq.moi = True, pid, True
        kq.ten = (ten or "").strip() or Path(d.goc_worktree).name
        kq.ly_do = f"đăng ký dự án mới {pid!r} trỏ vào {d.goc_worktree}"
        kq.nguon = kham_pha_nguon(cc, d.goc_worktree, pid)

    if ghi_su_kien:
        try:
            cc.store.ghi_su_kien(
                "PROJECT_ADOPTED", project_id=kq.project_id,
                detail=(f"nhận dự án hiện có: {d.goc_worktree} · nhánh "
                        f"{d.nhanh or '?'} · {d.so_commit} commit · "
                        f"{'liên kết lại' if kq.lien_ket_lai else 'đăng ký mới'}")[:400],
                meta={"kho": d.to_dict(), "nguon": kq.nguon,
                      "lien_ket_lai": kq.lien_ket_lai, "moi": kq.moi})
        except Exception:                                   # noqa: BLE001
            pass
    return kq


def _suy_project_id(goc: str) -> str:
    """`project_id` suy từ TÊN THƯ MỤC (ổn định), làm sạch về `[a-z0-9_-]`."""
    ten = Path(goc).name or "du-an"
    s = re.sub(r"[^a-z0-9_-]+", "-", ten.lower()).strip("-")
    return s[:40] or "du-an"
