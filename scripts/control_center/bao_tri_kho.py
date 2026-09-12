# -*- coding: utf-8 -*-
"""MÔI GIỚI BẢO TRÌ KHO — dọn worktree cũ + nhả xung đột tài nguyên.

VÌ SAO CÓ FILE NÀY (dogfood thật, 2026-09-12): một việc HỢP LỆ, thuần
repo-local — *"dọn worktree cũ và nhả xung đột tài nguyên"* — đi đúng đường
tới Router V4, rồi worker `BLOCKED` vì nó phải tự gọi `git worktree` /
ghi vào `.git`, mà quyền đó bị chối (đúng như thiết kế).

Cách sửa KHÔNG phải nới quyền. Đây là đúng khuôn đã trả giá ba lần trước:
`nguon_git` (đọc lịch sử), `web_reader` (đọc web), `probe_van_hanh` (đo
production) — **Router làm thao tác an toàn hộ, rồi đưa BẰNG CHỨNG**; quyền
của agent KHÔNG đổi. Khác biệt duy nhất ở đây: thao tác này có ĐỘT BIẾN, nên
mọi thứ phải fail-closed và có dấu vết kiểm toán.

Ba điều file này KHÔNG làm:

* **Không nhận chuỗi lệnh.** API có KIỂU; không có `chay(lenh)`. Cùng lý do
  `probe_van_hanh` từ chối chuỗi lệnh: một tham số chuỗi là một cửa hậu.
* **Không đụng gì ngoài `.router/worktrees/` của ĐÚNG kho này.** Không bao
  giờ chạm cây làm việc chính, không bao giờ ghi thẳng `.git`.
* **Không xoá bằng chứng.** Hàng trong sổ ở lại (đánh dấu `STALE`), sự kiện
  kiểm toán ghi cả lần CHO PHÉP lẫn lần TỪ CHỐI.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.control_center.locks import LockManager
from scripts.control_center.model import LockKind, TaskState
from scripts.control_center.store import ControlStore
from scripts.control_center.worktrees import (WT_STALE, WorktreeCoordinator,
                                              WorktreeError)
from scripts.router_v3.tien_trinh import an_cua_so

#: Trần số cây gỡ trong MỘT lần dọn. Một lệnh dọn không được biến thành một
#: cuộc xoá hàng loạt vì ai đó gõ nhầm.
TRAN_GO_MOI_LAN = 25


class BaoTriLoi(RuntimeError):
    """Thao tác bảo trì bị TỪ CHỐI. Luôn kèm lý do CHÍNH XÁC."""


@dataclass(frozen=True)
class KetQuaBaoTri:
    """MỘT thao tác bảo trì đã được phán xử. Dữ liệu, không phải log."""

    thao_tac: str
    lam_duoc: bool
    chi_tiet: str
    doi_tuong: str = ""
    bang_chung: Tuple[str, ...] = ()

    def to_dict(self) -> Dict:
        return {"thao_tac": self.thao_tac, "lam_duoc": self.lam_duoc,
                "chi_tiet": self.chi_tiet[:600], "doi_tuong": self.doi_tuong,
                "bang_chung": list(self.bang_chung)}


class MoiGioiBaoTri:
    """Thao tác bảo trì repo-local CÓ KIỂU. Không nhận chuỗi lệnh.

    `so_thuc_thi` là tuỳ chọn nhưng NÊN có: thiếu nó thì phép kiểm "còn lần
    thực thi nào đang trỏ tới cây này không" không chạy được, và lúc đó môi
    giới FAIL CLOSED — từ chối gỡ, chứ không đoán là an toàn.
    """

    def __init__(self, project_id: str, store: ControlStore, *,
                 worktrees: WorktreeCoordinator, so_thuc_thi=None) -> None:
        self.project_id = project_id
        self.store = store
        self.wt = worktrees
        self.so_thuc_thi = so_thuc_thi

    # ------------------------------------------------------------- đọc ----

    def liet_ke(self) -> List[Dict]:
        """Mọi worktree Router biết + trạng thái đối soát. CHỈ ĐỌC."""
        ds = list(self.wt.worktrees())
        lech = self.wt.doi_soat()
        mat = set(lech.get("missing") or ())
        ban = set(lech.get("dirty") or ())
        la = set(lech.get("untracked") or ())
        for d in ds:
            p = str(d.get("path") or "")
            d["tren_dia"] = p not in mat
            d["ban"] = p in ban
        for p in sorted(la):
            ds.append({"path": p, "state": "UNTRACKED", "owner_session": "",
                       "branch": "", "tren_dia": True, "ban": p in ban,
                       "ghi_chu": "git biết, sổ Control Center không biết"})
        return ds

    def _git(self, *args: str) -> Tuple[int, str]:
        """`git` trong gốc kho. `argv` DỰNG SẴN, không nội suy chuỗi lệnh."""
        goc = str(self.wt.repo_root)
        try:
            r = subprocess.run(["git", *args], cwd=goc, capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=120, **an_cua_so())
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 127, f"{type(exc).__name__}: {exc}"
        return int(r.returncode), ((r.stdout or "") + (r.stderr or "")).strip()

    # ---------------------------------------------------- phép kiểm an toàn --

    def _kiem_go_duoc(self, duong: str, *, cho_phep_ban: bool,
                      duyet_tay: bool) -> Tuple[bool, str, List[str]]:
        """`(gỡ được?, lý do CHÍNH XÁC, bằng chứng)`. FAIL CLOSED.

        Thứ tự có nghĩa: rào rẻ và tuyệt đối trước (phạm vi đường dẫn), rào
        cần tra sổ sau. Một rào không tra được KHÔNG BAO GIỜ được coi là đã
        qua.
        """
        bc: List[str] = []
        goc_wt = self.wt.manager.worktree_root.resolve()
        goc_kho = Path(self.wt.repo_root).resolve()
        try:
            p = Path(duong).resolve()
        except OSError as exc:
            return False, f"đường dẫn không phân giải được: {exc}", bc

        # 1. CÂY LÀM VIỆC CHÍNH là bất khả xâm phạm.
        if p == goc_kho:
            return False, ("đây là CÂY LÀM VIỆC CHÍNH của kho — không bao giờ "
                           "gỡ"), bc
        # 2. Phải nằm trong `.router/worktrees/` của ĐÚNG kho này.
        try:
            p.relative_to(goc_wt)
        except ValueError:
            return False, (f"nằm ngoài {goc_wt} — môi giới chỉ đụng worktree "
                           f"do Router quản lý"), bc
        bc.append(f"trong phạm vi {goc_wt}")

        # 3. Router có BIẾT cây này không (hoặc người vận hành duyệt tay).
        hang = (self.store.worktree(str(duong))
                or self.store.worktree(str(p)))
        if hang is None and not duyet_tay:
            return False, ("không có trong sổ Control Center — một thư mục lạ "
                           "trong `.router/worktrees/` KHÔNG phải thứ công cụ "
                           "này được phép xoá (cần duyệt tay)"), bc
        bc.append("Router quản lý" if hang is not None else "người vận hành duyệt tay")

        # 4. Không phiên SỐNG nào đang sở hữu.
        chu = str((hang or {}).get("owner_session") or "").strip()
        if chu:
            s = self.store.session(chu)
            if s is not None and s.state.alive:
                return False, (f"phiên {chu} ({s.state.value}) còn sống và "
                               f"đang sở hữu cây này — dừng phiên trước"), bc
        bc.append("không phiên sống nào sở hữu")

        # 5. Không LẦN THỰC THI nào đang trỏ tới nó. Thiếu sổ -> TỪ CHỐI.
        ok, vs = self._khong_con_thuc_thi_dung(p)
        if not ok:
            return False, vs, bc
        bc.append(vs)

        # 6. Thay đổi CHƯA COMMIT của người dùng.
        if self.wt.is_dirty(str(p)) and not cho_phep_ban:
            return False, ("còn thay đổi CHƯA COMMIT — cần cho phép tường "
                           "minh (`cho_phep_ban=True`) mới gỡ"), bc
        bc.append("sạch" if not self.wt.is_dirty(str(p)) else "bẩn (đã được cho phép)")
        return True, "qua mọi phép kiểm", bc

    def _khong_con_thuc_thi_dung(self, p: Path) -> Tuple[bool, str]:
        """Còn lần thực thi SỐNG nào trỏ tới cây này không?

        FAIL CLOSED: không tra được sổ thực thi thì TỪ CHỐI. Gỡ một cây mà
        một lần thực thi còn đang dùng là phá công việc đang chạy, và đó
        đúng là loại hỏng không hoàn tác được.
        """
        if self.so_thuc_thi is None:
            return False, ("không có sổ thực thi để kiểm — từ chối gỡ thay vì "
                           "đoán là an toàn")
        try:
            ds = self.so_thuc_thi.danh_sach(self.project_id, limit=200)
        except Exception as exc:                              # noqa: BLE001
            return False, f"không đọc được sổ thực thi ({exc}) — từ chối gỡ"
        for y in ds:
            tt = getattr(y, "trang_thai", None)
            if tt is None or tt.ket_thuc:
                continue
            try:
                bs = self.so_thuc_thi.buoc(y.execution_id)
            except Exception:                                 # noqa: BLE001
                return False, "không đọc được bước của lần thực thi — từ chối"
            for b in bs:
                w = str((b.get("ket_qua") or {}).get("worktree") or "")
                if not w:
                    continue
                try:
                    if Path(w).resolve() == p:
                        return False, (f"lần thực thi {y.execution_id} "
                                       f"({tt.value}) còn trỏ tới cây này")
                except OSError:
                    continue
        return True, "không lần thực thi sống nào trỏ tới"

    # ----------------------------------------------------------- đột biến --

    def tia_sieu_du_lieu(self) -> KetQuaBaoTri:
        """`git worktree prune` — CHỈ dọn siêu dữ liệu quản trị.

        An toàn nhất trong ba thao tác: nó không xoá thư mục nào, chỉ bỏ các
        bản ghi trỏ tới cây đã biến mất. Vẫn ghi kiểm toán.
        """
        ma, ra = self._git("worktree", "prune", "-v")
        kq = KetQuaBaoTri(
            thao_tac="tia_sieu_du_lieu", lam_duoc=(ma == 0),
            chi_tiet=(ra or "không còn siêu dữ liệu thừa")[:600],
            bang_chung=("git worktree prune -v",))
        self._kiem_toan(kq)
        return kq

    def go_cay_cu(self, duong: str, *, ly_do: str,
                  cho_phep_ban: bool = False,
                  duyet_tay: bool = False) -> KetQuaBaoTri:
        """Gỡ MỘT worktree Router đã cũ, sau khi qua HẾT phép kiểm."""
        ok, vs, bc = self._kiem_go_duoc(duong, cho_phep_ban=cho_phep_ban,
                                        duyet_tay=duyet_tay)
        if not ok:
            kq = KetQuaBaoTri("go_cay_cu", False, f"TỪ CHỐI: {vs}",
                              doi_tuong=str(duong), bang_chung=tuple(bc))
            self._kiem_toan(kq)
            return kq
        try:
            ra = self.wt.go_bo(duong, xac_nhan=True, ly_do=ly_do)
        except WorktreeError as exc:
            kq = KetQuaBaoTri("go_cay_cu", False, f"TỪ CHỐI: {exc}",
                              doi_tuong=str(duong), bang_chung=tuple(bc))
            self._kiem_toan(kq)
            return kq
        kq = KetQuaBaoTri(
            "go_cay_cu", True,
            f"đã gỡ (nhánh {ra.get('branch') or '—'}, bẩn={ra.get('was_dirty')})",
            doi_tuong=str(duong), bang_chung=tuple(bc))
        self._kiem_toan(kq)
        return kq

    def nha_khoa_mo_coi(self) -> KetQuaBaoTri:
        """Nhả khoá mà CHỦ của nó đã kết thúc — "xung đột tài nguyên" cũ.

        KHÔNG đụng khoá `PRODUCTION`: `LockKind.tu_thu_hoi_duoc` nói rõ một
        khoá production hết hạn KHÔNG bao giờ tự về, và luật đó không đổi ở
        đây. Cũng không đụng khoá mà chủ còn sống.
        """
        lm = LockManager(self.store)
        nha: List[str] = []
        giu: List[str] = []
        for l in lm.dang_giu(self.project_id):
            if l.kind is LockKind.PRODUCTION:
                giu.append(f"{l.resource} (PRODUCTION — không tự thu hồi)")
                continue
            ma = str(getattr(l, "holder_task", "") or "")
            if not ma:
                giu.append(f"{l.resource} (không rõ chủ — giữ)")
                continue
            t = self.store.task(ma)
            if t is None:
                lm.tra(self.project_id, ma)
                nha.append(f"{l.resource} (chủ {ma} không còn trong sổ)")
                continue
            if t.state.terminal:
                lm.tra(self.project_id, ma)
                nha.append(f"{l.resource} (chủ {ma} đã {t.state.value})")
            else:
                giu.append(f"{l.resource} (chủ {ma} đang {t.state.value})")
        kq = KetQuaBaoTri(
            "nha_khoa_mo_coi", True,
            f"nhả {len(nha)} khoá mồ côi, giữ {len(giu)}",
            bang_chung=tuple(nha[:10] + [f"GIỮ: {g}" for g in giu[:10]]))
        self._kiem_toan(kq)
        return kq

    def don_dep(self, *, ly_do: str, cho_phep_ban: bool = False,
                toi_da: int = TRAN_GO_MOI_LAN) -> List[KetQuaBaoTri]:
        """Việc "dọn worktree cũ + nhả xung đột tài nguyên", trọn gói.

        Thứ tự có nghĩa: nhả khoá TRƯỚC (rẻ, không phá gì), rồi tỉa siêu dữ
        liệu, rồi mới gỡ cây — và mỗi cây vẫn qua đủ phép kiểm riêng. Cây
        nào không qua thì bị TỪ CHỐI kèm lý do, không làm hỏng phần còn lại.
        """
        ra: List[KetQuaBaoTri] = [self.nha_khoa_mo_coi(),
                                  self.tia_sieu_du_lieu()]
        n = 0
        for d in self.liet_ke():
            if n >= max(0, int(toi_da)):
                break
            p = str(d.get("path") or "")
            if not p:
                continue
            # Chỉ nhắm cây ĐÃ CŨ: không chủ sống, và sổ nói STALE/IDLE hoặc
            # đĩa đã mất. Cây ACTIVE không phải "cũ".
            if str(d.get("state") or "") not in (WT_STALE, "IDLE"):
                continue
            if not d.get("tren_dia", True):
                continue
            ra.append(self.go_cay_cu(p, ly_do=ly_do,
                                     cho_phep_ban=cho_phep_ban))
            n += 1
        return ra

    # ---------------------------------------------------------- kiểm toán --

    def _kiem_toan(self, kq: KetQuaBaoTri) -> None:
        """GHI CẢ lần cho phép LẪN lần từ chối. Một rào im lặng là một rào
        không chứng minh được."""
        try:
            self.store.ghi_su_kien(
                "REPO_MAINTENANCE", project_id=self.project_id,
                level=("INFO" if kq.lam_duoc else "WARNING"),
                detail=f"{kq.thao_tac}: {kq.chi_tiet}"[:400],
                meta=kq.to_dict())
        except Exception:                                     # noqa: BLE001
            pass


def goi_bang_chung(ds: Sequence[KetQuaBaoTri]) -> str:
    """Khối văn bản cho Leader/worker — BẰNG CHỨNG, không phải quyền."""
    d = ["BẢO TRÌ KHO (Router tự làm bằng môi giới CÓ KIỂU — agent KHÔNG được "
         "cấp thêm quyền nào):"]
    for k in ds:
        d.append(f"  [{'OK' if k.lam_duoc else 'TỪ CHỐI'}] {k.thao_tac}"
                 + (f" · {Path(k.doi_tuong).name}" if k.doi_tuong else ""))
        d.append(f"      {k.chi_tiet[:200]}")
    return "\n".join(d)
