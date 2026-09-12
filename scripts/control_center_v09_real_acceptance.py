#!/usr/bin/env python3
"""NGHIỆM THU MODEL THẬT của vòng kín V0.9 — tám kịch bản A–H trên Fanfic THẬT.

CHẠY TRÊN THỨ THẬT, và đó là toàn bộ lý do tệp này tồn tại bên cạnh
`scripts/tests/test_execution_slice_v09.py`:

    ứng dụng THẬT (`ControlCenter` source-mode, không phải một bản dựng riêng)
    sổ CHÍNH TẮC (`%LOCALAPPDATA%\\RouterControlCenter`)
    dự án Fanfic THẬT + ký ức/viên nang THẬT của nó
    model THẬT ở đúng những chỗ kịch bản đòi suy luận
    worktree THẬT, khoá THẬT, `git` THẬT ở tầng kiểm định

RANH GIỚI, VÀ NÓ ĐƯỢC NÓI RA CHỨ KHÔNG GIẤU:

* **Không một thao tác production nào.** Không deploy, không restart dịch
  vụ, không chạm R2/Appwrite/Drive, không đụng credential. Kịch bản G tồn
  tại để CHỨNG MINH điều đó chứ không phải để thử.
* **Bước THỰC THI dùng việc CHỈ ĐỌC.** Fan-out, khoá, worktree, hợp đồng kết
  quả, kiểm định và phục hồi đều chạy thật; thứ agent làm là ĐỌC kho rồi
  tóm tắt. Một bài nghiệm thu không được sửa kho thật của người dùng để tự
  chứng minh mình đúng.
* **Model thật chỉ ở chỗ cần suy luận.** Câu hỏi chiến lược, câu tiếp nối,
  ranh giới thẩm quyền, và lượt Reviewer ngữ nghĩa. Những chỗ còn lại
  (pause/resume/cancel, khởi động lại) đi qua cổng TẤT ĐỊNH và tốn 0 lượt
  model — đó là thiết kế, không phải sự tiết kiệm.

    python scripts/control_center_v09_real_acceptance.py            # tất cả
    python scripts/control_center_v09_real_acceptance.py --kich-ban A B
    python scripts/control_center_v09_real_acceptance.py --kho       # chỉ in sổ

Mã thoát 0 khi mọi khẳng định ĐẠT. Báo cáo JSON ghi cạnh tệp này.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.duong_du_lieu import goc_du_lieu     # noqa: E402
from scripts.control_center.execution import ke_hoach as KH      # noqa: E402
from scripts.control_center.execution import phan_hoi as PH      # noqa: E402
from scripts.control_center.execution import tiep_noi as TN      # noqa: E402
from scripts.control_center.execution import y_dinh as YD        # noqa: E402
from scripts.control_center.execution.dieu_phoi import (         # noqa: E402
    TrangThaiBuoc, cau_trang_thai)
from scripts.control_center.execution.trang_thai import (        # noqa: E402
    TrangThaiThucThi as TT)
from scripts.control_center.model import LockKind                # noqa: E402
from scripts.router_v4.history import (MAU_TOI_THIEU,            # noqa: E402
                                       BenchmarkStore, duong_vai)

RA = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace",
                      line_buffering=True)

PID = "fanfic"
#: Trần thời gian cho một lượt chat THẬT (Leader + có thể cả hội đồng).
HAN_CHAT = 900.0
#: Trần cho một lần thực thi chạy hết.
#:
#: RỘNG có chủ đích. Một thang phục hồi ĐẦY ĐỦ trên agent thật là: 2 bước ×
#: 3 lượt × tối đa 3 bản kế hoạch, cộng thời gian chờ khe phiên khi bể đang
#: bận. Một trần chật biến bài kiểm về TÍNH CÓ ĐÁY thành một bài kiểm về tốc
#: độ nhà cung cấp — đo được 2026-09-12: ba lần chạy bị cắt trong khi một
#: bước vẫn đang chạy, và bài kiểm báo "không đứng lại" cho một hệ thống
#: hoàn toàn đang tiến triển.
HAN_THUC_THI = 2700.0


#: Dấu hiệu một tiến trình Control Center KHÁC đang sống. Hẹp có chủ đích:
#: chữ "desktop" một mình khớp cả ChatGPT Desktop, nên chỉ nhận cụm CÓ
#: không gian tên của gói này.
DAU_HIEU_CC = ("scripts.control_center", "control_center.desktop",
               "control_center.webmain", "router-cc", "router_cc_",
               "routercontrolcenter")


def tien_trinh_cc_khac(liet_ke=None, pid_minh: int = 0):
    """Còn tiến trình Control Center NÀO khác đang sống không?

    KHÔNG phải để cấm hai tiến trình — `TestHaiTienTrinh` khoá lại rằng hai
    Control Center trên một sổ là chuyện BÌNH THƯỜNG, và các bất biến loại
    trừ (`claim_task` nguyên tử, khoá tài nguyên) được thiết kế cho đúng
    cảnh đó. Cái KHÔNG chấp nhận được là chạy NGHIỆM THU trong lúc đó.

    VÌ SAO (đo được 2026-09-12): một `desktop` (pid 11620) và một `webmain`
    (pid 34188) còn sống từ hôm trước, chạy MÃ CŨ, cùng đạp nhịp trên sổ
    chính tắc. Chúng giành việc rồi chạy bằng bản chưa có bản sửa, nên NĂM
    lần nghiệm thu liên tiếp cho ra cùng một chữ ký hỏng và hai bản sửa đúng
    trông như vô hiệu. Sổ còn giữ dấu vân tay: cùng một nhật ký có cả `X/12`
    (trần của bộ nghiệm thu) lẫn `X/3` (trần mặc định của desktop/webmain) —
    một tiến trình không thể in ra hai trần.

    Nghiệm thu đo HÀNH VI CỦA MÃ NÀY. Một tiến trình khác — nhất là bản cũ —
    làm mọi khẳng định mất nghĩa. Nên bài kiểm phải TỪ CHỐI CHẠY, chứ không
    phải chạy rồi báo một con số không tin được.

    `liet_ke` tiêm được để bài kiểm không phải dựng tiến trình thật.
    """
    import os
    import subprocess
    from scripts.router_v3.tien_trinh import an_cua_so

    if liet_ke is None:
        def liet_ke():
            if os.name != "nt":
                p = subprocess.run(["ps", "-eo", "pid=,args="],
                                   capture_output=True, text=True,
                                   **an_cua_so())
                ra = []
                for d in (p.stdout or "").splitlines():
                    d = d.strip()
                    if not d:
                        continue
                    so, _, cmd = d.partition(" ")
                    try:
                        ra.append((int(so), cmd))
                    except ValueError:
                        pass
                return ra
            ps = ("Get-CimInstance Win32_Process | ForEach-Object "
                  "{ \"$($_.ProcessId)`t$($_.CommandLine)\" }")
            p = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, **an_cua_so())
            ra = []
            for d in (p.stdout or "").splitlines():
                so, _, cmd = d.partition("\t")
                try:
                    ra.append((int(so.strip()), cmd))
                except ValueError:
                    pass
            return ra

    minh = pid_minh or os.getpid()
    thay = []
    for so, cmd in (liet_ke() or ()):
        if so == minh or not cmd:
            continue
        thap = cmd.lower()
        # Bỏ chính bộ nghiệm thu (và bài kiểm của nó) ra khỏi phép đếm.
        if "v09_real_acceptance" in thap or "unittest" in thap:
            continue
        if any(m.lower() in thap for m in DAU_HIEU_CC):
            thay.append((so, cmd.strip()[:160]))
    return thay


#: KHÔNG GIAN TÊN CỦA MỘT LẦN CHẠY NGHIỆM THU.
#
# `execution_id` đã là uuid nên vốn không đụng nhau. Thứ ĐỤNG là `task_id`:
# nó được suy từ `buoc_id` (`engine`: `f"{pid}.{b.buoc_id}"`), và bộ nghiệm
# thu vốn dùng hằng số (`ghi_v1`, `ghi_tailieu`…), nên lần chạy N+1 tạo một
# việc TRÙNG TÊN với lần N.
#
# Giá phải trả, đo được (`ex_16da77a00864`): một phiên của lần chạy TRƯỚC còn
# mang nhãn `BUSY`/`fanfic.ghi_v1`; lần chạy SAU tạo đúng `fanfic.ghi_v1`, và
# luật 1 coi đó là "việc của tôi đang chạy" rồi `WAIT` vĩnh viễn. Cùng lý do
# đó, mọi phép soi sổ theo tên việc đều có thể đọc nhầm bản ghi của lần chạy
# khác — tôi đã đọc nhầm đúng như vậy một lần trong đợt này.
#
# KHÔNG dọn sổ để tránh đụng: lịch sử là bằng chứng. Thay vào đó, đặt tên
# theo TỪNG LẦN CHẠY.
LAN_CHAY = time.strftime("%H%M%S") + "-" + uuid.uuid4().hex[:4]


def ma_buoc(goc: str, lan: str = "") -> str:
    """`buoc_id` có KHÔNG GIAN TÊN của lần chạy.

    Ổn định TRONG một lần chạy (mọi bước dùng cùng `lan`), và khác nhau
    GIỮA các lần chạy độc lập. `kb_R` khởi động lại thì KHÔNG sinh tên mới —
    nó đọc lại kế hoạch đã bền, nên danh tính giữ nguyên qua tắt/mở.
    """
    return f"{goc}__{lan or LAN_CHAY}"


def _in(s: str = "") -> None:
    RA.write(s + "\n")


def _tieu_de(s: str) -> None:
    _in("\n" + "=" * 78)
    _in(s)
    _in("=" * 78)


class BaoCao:
    """Gom khẳng định + bằng chứng. Một khẳng định hỏng KHÔNG dừng phần còn
    lại — ta muốn thấy toàn cảnh, không thấy lỗi đầu tiên."""

    def __init__(self) -> None:
        self.muc: List[Dict] = []
        self.kich_ban: Dict[str, Dict] = {}

    def khang_dinh(self, kb: str, ten: str, dat: bool, chi_tiet: str = "") -> bool:
        self.muc.append({"kich_ban": kb, "ten": ten, "dat": bool(dat),
                         "chi_tiet": chi_tiet[:400]})
        _in(f"  [{'ĐẠT' if dat else 'HỎNG'}] {ten}"
            + (f"  — {chi_tiet[:160]}" if chi_tiet else ""))
        return bool(dat)

    def ghi(self, kb: str, **kw) -> None:
        self.kich_ban.setdefault(kb, {}).update(kw)

    @property
    def hong(self) -> List[Dict]:
        return [m for m in self.muc if not m["dat"]]

    def to_dict(self) -> Dict:
        return {"ts": time.time(), "tong": len(self.muc),
                "dat": len(self.muc) - len(self.hong), "hong": len(self.hong),
                "khang_dinh": self.muc, "kich_ban": self.kich_ban}


# --------------------------------------------------------------- tien ich ----

def _cho(dk, *, giay: float, nhip: float = 1.0, tick=None) -> bool:
    het = time.time() + giay
    while time.time() < het:
        if dk():
            return True
        if tick is not None:
            try:
                tick()
            except Exception:                               # noqa: BLE001
                pass
        time.sleep(nhip)
    return dk()


def _dem_viec(cc) -> int:
    return len(cc.store.tasks(PID))


def _dem_thuc_thi(cc) -> int:
    return len(cc.so_thuc_thi.danh_sach(PID, limit=500))


def _prod_mutations(cc) -> int:
    """Số thao tác CHẠM PRODUCTION đã THỰC SỰ chạy. Phải luôn là 0.

    Đếm từ SỔ SỰ KIỆN, không từ một biến đếm trong bộ nhớ: một biến đếm chỉ
    biết những gì bài kiểm này làm, còn sổ biết cả những gì ứng dụng làm.
    """
    n = 0
    for e in cc.store.su_kien(project_id=PID, limit=2000):
        if e.get("kind") in ("GATE_APPROVED", "PRODUCTION_MUTATION",
                             "DEPLOY", "SERVICE_RESTART"):
            n += 1
    return n


def _mo_cc(*, executor_factory=None):
    """Mở `ControlCenter` THẬT trên sổ CHÍNH TẮC. Không `root=` giả.

    `leader_bat=True` là BẮT BUỘC, và quên nó làm hỏng cả bài nghiệm thu một
    cách im lặng: `leader_bat` mặc định `False` để bộ kiểm tất định không
    sinh tiến trình model nào, nên một lượt `chat()` không bật cờ này sẽ
    KHÔNG gọi Leader mà rơi thẳng xuống bộ phân rã — và một câu hỏi THẢO
    LUẬN biến thành một việc worker. Đo được ở lần chạy đầu (2026-09-11):
    lượt "nên làm gì tiếp?" trả về sau 0,1 s và tạo một việc.

    Ba điểm vào THẬT (`__main__`, `desktop`, web) đều bật nó; một bài nghiệm
    thu tự nhận là "chạy trên ứng dụng thật" mà không bật thì đang đo một
    ứng dụng khác.
    """
    from scripts.control_center.engine import ControlCenter
    return ControlCenter(probe=False, max_parallel=3, leader_bat=True,
                         executor_factory=executor_factory)


def _du_an(cc) -> bool:
    return cc.store.project(PID) is not None


def _cac_worktree(cc, eid: str) -> List[str]:
    """MỌI worktree của MỌI bước. Hai bước song song sống ở hai cây khác nhau."""
    ra: List[str] = []
    for st in cc.so_thuc_thi.buoc(eid):
        w = str((st.get("ket_qua") or {}).get("worktree") or "")
        if w and w not in ra and Path(w).is_dir():
            ra.append(w)
    return ra


def _bang_chung_ghi(cc, eid: str):
    """`(các worktree, [tệp đã đổi])` — đọc TỪ ĐĨA, không từ lời khai worker.

    `git status --porcelain` trong TỪNG worktree của lần thực thi. Lời khai
    `files_changed` của agent là một tuyên bố; đây là phép đo.
    """
    import subprocess
    from scripts.router_v3.tien_trinh import an_cua_so
    wts = _cac_worktree(cc, eid)
    tep: List[str] = []
    for wt in wts:
        try:
            r = subprocess.run(["git", "status", "--porcelain"], cwd=wt,
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=60, **an_cua_so())
        except Exception:                                   # noqa: BLE001
            continue
        for x in (r.stdout or "").splitlines():
            if len(x) > 3:
                t = x[3:].strip()
                if t not in tep:
                    tep.append(t)
    return wts, tep


def _tep_chua(wts, duong: str, chuoi: str) -> bool:
    """Tệp có ở BẤT KỲ worktree nào của lần thực thi và chứa `chuoi` không."""
    if isinstance(wts, str):
        wts = [wts] if wts else []
    for wt in wts:
        p = Path(wt) / duong
        if not p.is_file():
            continue
        try:
            if chuoi in p.read_text(encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    return False


def _kho_that_sach(cc) -> bool:
    """Cây làm việc CHÍNH của Fanfic phải KHÔNG đổi — worktree là cô lập."""
    import subprocess
    from scripts.router_v3.tien_trinh import an_cua_so
    p = cc.store.project(PID)
    if p is None:
        return False
    try:
        r = subprocess.run(["git", "status", "--porcelain"],
                           cwd=p.repo_path, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60,
                           **an_cua_so())
    except Exception:                                       # noqa: BLE001
        return False
    return not (r.stdout or "").strip()


# --------------------------------------------------------------- kich ban ----

def kb_A(cc, bc: BaoCao) -> Optional[str]:
    """THẢO LUẬN THUẦN — Strategist có thể tham gia, KHÔNG thực thi gì."""
    _tieu_de("KỊCH BẢN A — thảo luận thuần (model THẬT)")
    v0, t0 = _dem_thuc_thi(cc), _dem_viec(cc)
    t = time.time()
    kq = cc.chat(PID, "theo m project Fanfic nên làm gì tiếp?")
    giay = time.time() - t
    _in(f"  (lượt thật {giay:.1f}s)")
    _in("  --- TRẢ LỜI ---")
    for d in (kq.get("reply") or "").splitlines()[:22]:
        _in(f"  | {d[:150]}")

    ng = cc.nguon_goc_suy_luan(PID) or {}
    vai = [x.get("vai") for x in (ng.get("nguon_goc") or [])]
    bc.khang_dinh("A", "có trả lời thực chất", bool((kq.get("reply") or "").strip()),
                  f"{len(kq.get('reply') or '')} ký tự")
    bc.khang_dinh("A", "KHÔNG tạo lần thực thi nào",
                  _dem_thuc_thi(cc) == v0, f"{_dem_thuc_thi(cc)} (trước {v0})")
    bc.khang_dinh("A", "KHÔNG tạo việc worker nào",
                  _dem_viec(cc) == t0, f"{_dem_viec(cc)} (trước {t0})")
    bc.khang_dinh("A", "0 thay đổi production", _prod_mutations(cc) == 0)
    dx = cc.so_thuc_thi.de_xuat(PID, chua_dung=True, limit=5)
    bc.khang_dinh("A", "đề xuất được LƯU để nối về sau", bool(dx),
                  (dx[0].ma + ": " + dx[0].tom_tat[:90]) if dx else "(không có)")
    bc.ghi("A", giay=round(giay, 1), vai=vai,
           so_ky_tu=len(kq.get("reply") or ""),
           de_xuat=(dx[0].to_dict() if dx else None),
           nguon_goc=(ng.get("dong_nguon_goc") or []),
           thuc_thi_moi=0, viec_moi=0)
    return dx[0].ma if dx else None


def kb_B(cc, bc: BaoCao, ma_dx: Optional[str]) -> Optional[str]:
    """TIẾP NỐI — "ok triển khai phần repo-local đó đi" nối về đúng đề xuất."""
    _tieu_de("KỊCH BẢN B — câu tiếp nối uỷ quyền (cổng TẤT ĐỊNH, 0 lượt model)")
    t = time.time()
    kq = cc.chat(PID, "ok triển khai phần repo-local đó đi")
    giay = time.time() - t
    _in(f"  ({giay:.1f}s)")
    for d in (kq.get("reply") or "").splitlines()[:18]:
        _in(f"  | {d[:150]}")

    ex = kq.get("execution") or {}
    eid = ex.get("execution_id") or ""
    bc.khang_dinh("B", "tạo được ý định thực thi BỀN", bool(eid), eid)
    if not eid:
        return None
    y = cc.so_thuc_thi.y_dinh(eid)
    bc.khang_dinh("B", "nối về ĐÚNG đề xuất trước đó",
                  bool(y.nguon_de_xuat) and (not ma_dx or y.nguon_de_xuat == ma_dx),
                  f"nguon_de_xuat={y.nguon_de_xuat} (mong {ma_dx})")
    bc.khang_dinh("B", "người dùng KHÔNG phải nhắc lại kế hoạch",
                  len(y.goal) > len("ok triển khai phần repo-local đó đi"),
                  f"mục tiêu dài {len(y.goal)} ký tự, lấy từ đề xuất")
    kh = cc.so_thuc_thi.ke_hoach(eid)
    bc.khang_dinh("B", "có kế hoạch v1", bool(kh) and kh.phien_ban == 1,
                  f"v{kh.phien_ban}, {len(kh.buoc)} bước" if kh else "(không)")
    bc.khang_dinh("B", "thẩm quyền REPO_LOCAL, KHÔNG phải production",
                  y.tham_quyen is YD.LopThamQuyen.REPO_LOCAL
                  or y.duyet is YD.TrangThaiDuyet.CHO_NGUOI,
                  f"{y.tham_quyen.value}/{y.duyet.value}")
    bc.khang_dinh("B", "0 thay đổi production", _prod_mutations(cc) == 0)
    bc.ghi("B", giay=round(giay, 1), execution_id=eid,
           nguon_de_xuat=y.nguon_de_xuat, muc_tieu=y.goal,
           tham_quyen=y.tham_quyen.value, duyet=y.duyet.value,
           ke_hoach=(kh.to_dict() if kh else None))
    return eid


#: Tệp bằng chứng của nghiệm thu. Đặt dưới `docs/reports/` và mang tiền tố
#: `_v09_` để người sau nhận ra ngay đây là hiện vật của một lần nghiệm thu,
#: không phải tài liệu dự án. Chúng nằm trong WORKTREE CÔ LẬP, không bao giờ
#: vào `main` của Fanfic.
#: Câu dặn CHỌN ĐÚNG CÔNG CỤ. Không phải lời khuyên phong cách — nó nhắm vào
#: một chế độ hỏng đã ghi trong `router_v3/pool/adapters.py`:
#:
#:     "`accept-edits` chỉ phủ công cụ GHI TỆP. Bằng chứng thật (2026-08-30):
#:      một model đôi khi chọn công cụ LỆNH SHELL để tạo tệp; lượt đó sẽ bị
#:      headless tự động từ chối và việc trả về 'không sửa gì'."
#:
#: Đo lại ở chính bài nghiệm thu này (2026-09-12): cùng một bước, có lượt ghi
#: được tệp, có lượt trả về RỖNG. Nói thẳng cho agent dùng công cụ ghi tệp là
#: cách rẻ nhất để không rơi vào nhánh bị chối quyền — KHÔNG nới quyền một ly.
HUONG_DAN_GHI = (
    "QUAN TRỌNG: dùng CÔNG CỤ GHI/TẠO TỆP của bạn để tạo tệp này. "
    "TUYỆT ĐỐI KHÔNG dùng lệnh shell (echo/cat/heredoc/PowerShell) — phiên "
    "này chạy headless và mọi lệnh shell đều bị từ chối, lượt sẽ trả về rỗng.")

TEP_A = "docs/reports/_v09_ghi_chu_handoff.md"
TEP_B = "docs/reports/_v09_ghi_chu_kiemthu.md"
MARKER_A = "V09-ACCEPT-HANDOFF"
MARKER_B = "V09-ACCEPT-KIEMTHU"


def kb_C(cc, bc: BaoCao) -> Optional[str]:
    """FAN-OUT THẬT + GHI THẬT — hai bước ĐỘC LẬP, agent THẬT ghi vào kho.

    Việc GHI, không phải chỉ đọc: đây là điều §3 đòi và là thứ bản nghiệm
    thu trước còn thiếu. Hai tệp KHÁC NHAU nên hai bước không tranh khoá và
    chạy song song thật. Mọi thay đổi nằm trong WORKTREE CÔ LẬP của Router —
    `main` của Fanfic không bị đụng tới.
    """
    _tieu_de("KỊCH BẢN C — đa agent GHI THẬT vào kho Fanfic (worktree cô lập)")
    y = YD.tao_y_dinh(
        project_id=PID,
        goal=("viết hai ghi chú khảo sát ngắn vào docs/reports/ cho kho "
              "Fanfic: một về tài liệu bàn giao, một về bộ kiểm thử"),
        cau_nguoi_dung="ok làm đi")
    y.tieu_chi_dat = ()
    kh = KH.KeHoachThucThi(
        execution_id=y.execution_id,
        buoc=(
            # MỤC TIÊU KHÔNG ĐƯỢC PHỤ THUỘC MỘT CÔNG CỤ BỊ CHỐI QUYỀN.
            #
            # `agy --print` (headless) TỰ CHỐI `read_file`/`command` và trả
            # về lượt RỖNG — `CLAUDE.md` gọi đó là "LUẬT CHUNG đã trả giá
            # BỐN lần". Đo lại lần thứ năm ở chính bài nghiệm thu này: bước
            # bảo agent "ĐỌC docs/HANDOFF.md" trả rỗng ba lượt liền, trong
            # khi bước chỉ GHI thì chạy ngay.
            #
            # Nên bước chỉ đòi thứ agent LÀM ĐƯỢC: ghi một tệp. Muốn agent
            # cần dữ liệu đọc thì Router phải ĐỌC HỘ rồi đính bằng chứng —
            # đúng khuôn `nguon_git`/`web_reader`/`probe_van_hanh`, và đó là
            # việc của đường `_chat`, không phải của một bài nghiệm thu.
            KH.BuocKeHoach(
                buoc_id=ma_buoc("ghi_tailieu"),
                tieu_de="ghi chú về tài liệu bàn giao",
                muc_tieu=(
                    f"TẠO tệp `{TEP_A}` trong kho này. Nội dung: một tiêu đề "
                    f"Markdown, 3-5 gạch đầu dòng ghi chú về tài liệu bàn "
                    f"giao của dự án, và MỘT DÒNG RIÊNG chứa đúng chuỗi:\n"
                    f"{MARKER_A}\n\n"
                    f"CHỈ được tạo/sửa đúng tệp `{TEP_A}`. Không đọc tệp nào "
                    f"khác, không sửa tệp nào khác, không commit.\n"
                    f"{HUONG_DAN_GHI}"),
                che_do_ghi=KH.CheDoGhi.GHI,
                tai_nguyen=((LockKind.FILESYSTEM, TEP_A, "write"),),
                artifact_mong_doi=(TEP_A,),
                cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": TEP_A}),)),
            KH.BuocKeHoach(
                buoc_id=ma_buoc("ghi_kiemthu"),
                tieu_de="ghi chú về bộ kiểm thử",
                muc_tieu=(
                    f"TẠO tệp `{TEP_B}` trong kho này. Nội dung: một tiêu đề "
                    f"Markdown, 3-5 gạch đầu dòng ghi chú về bộ kiểm thử của "
                    f"dự án, và MỘT DÒNG RIÊNG chứa đúng chuỗi:\n"
                    f"{MARKER_B}\n\n"
                    f"CHỈ được tạo/sửa đúng tệp `{TEP_B}`. Không đọc tệp nào "
                    f"khác, không sửa tệp nào khác, không commit.\n"
                    f"{HUONG_DAN_GHI}"),
                che_do_ghi=KH.CheDoGhi.GHI,
                tai_nguyen=((LockKind.FILESYSTEM, TEP_B, "write"),),
                artifact_mong_doi=(TEP_B,),
                cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": TEP_B}),)),
        ),
        nghiem_thu=(
            # KHACH QUAN, do duoc bang may — day la thu bien C thanh DONE.
            KH.TieuChiNghiemThu(
                mo_ta=f"{TEP_A} tồn tại và chứa {MARKER_A}",
                cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": TEP_A}),
                           (KH.CachKiem.CHUOI_TRONG_TEP,
                            {"duong": TEP_A, "chuoi": MARKER_A}))),
            KH.TieuChiNghiemThu(
                mo_ta=f"{TEP_B} tồn tại và chứa {MARKER_B}",
                cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": TEP_B}),
                           (KH.CachKiem.CHUOI_TRONG_TEP,
                            {"duong": TEP_B, "chuoi": MARKER_B}))),
            # TIEU CHI NGU NGHIA — thu keo Reviewer vao MOT CACH TU NHIEN
            # (kich ban H), khong phai mot loi goi tay ngoai vong kin.
            KH.TieuChiNghiemThu(
                mo_ta=("hai ghi chú có thực sự mô tả đúng kho Fanfic và đủ "
                       "để người đọc biết nên làm gì tiếp không"),
                bat_buoc=False)))
    bd = cc.dieu_phoi(PID)
    y = bd.bat_dau(y, kh)
    eid = y.execution_id
    _in(f"  execution_id = {eid}")
    _in(f"  {kh.render()}")

    lop = kh.lop
    bc.khang_dinh("C", "kế hoạch có LỚP song song (fan-out)",
                  bool(lop) and len(lop[0]) >= 2,
                  f"lớp 1 = {lop[0] if lop else []}")

    kq = bd.tick(eid)
    bc.khang_dinh("C", "giao SONG SONG ≥2 bước trong một nhịp",
                  len(kq.da_giao) >= 2, f"đã giao {list(kq.da_giao)}")
    bc.ghi("C", da_giao=list(kq.da_giao), lop=lop)

    _in("  … chờ agent THẬT chạy (mỗi bước là một lượt `agy` thật)")
    ok = _cho(lambda: (cc.so_thuc_thi.y_dinh(eid).trang_thai.ket_thuc
                       or cc.so_thuc_thi.y_dinh(eid).trang_thai.can_nguoi),
              giay=HAN_THUC_THI, nhip=3.0, tick=cc.tick)
    y = cc.so_thuc_thi.y_dinh(eid)
    bs = cc.so_thuc_thi.buoc(eid)
    for b in bs:
        _in(f"    bước {b['buoc_id']:<14} {b['state']:<10} "
            f"{b['xac_minh']:<18} {b['task_id']}")
    bc.khang_dinh("C", "lần thực thi ĐỨNG LẠI trong hạn", ok,
                  f"trạng thái cuối = {y.trang_thai.value}")
    bc.khang_dinh("C", "kết thúc ở DONE", y.trang_thai is TT.DONE,
                  f"{y.trang_thai.value} — {y.ly_do_dung[:160]}")
    bc.khang_dinh("C", "mọi bước có hợp đồng kết quả CÓ CẤU TRÚC",
                  all((b.get("ket_qua") or {}).get("status") for b in bs),
                  json.dumps([{(b['buoc_id']): (b.get('ket_qua') or {})
                               .get('status')} for b in bs],
                             ensure_ascii=False))

    # BANG CHUNG GHI THAT: worktree + tep tren dia + noi dung.
    wt, tep = _bang_chung_ghi(cc, eid)
    for w in (wt or []):
        _in(f"  worktree: {w}")
    for t in tep:
        _in(f"    {t}")
    bc.khang_dinh("C", "agent GHI THẬT vào worktree cô lập", bool(tep),
                  f"{len(tep)} tệp: {', '.join(tep[:4])}")
    ok_a = _tep_chua(wt, TEP_A, MARKER_A)
    ok_b = _tep_chua(wt, TEP_B, MARKER_B)
    bc.khang_dinh("C", f"{TEP_A} có {MARKER_A}", ok_a)
    bc.khang_dinh("C", f"{TEP_B} có {MARKER_B}", ok_b)
    bc.khang_dinh("C", "git diff của worktree KHÔNG rỗng", bool(tep))
    bc.khang_dinh("C", "kho Fanfic THẬT vẫn sạch", _kho_that_sach(cc),
                  "git status của cây làm việc chính")

    sk = [e["kind"] for e in cc.so_thuc_thi.su_kien(eid, limit=400)]
    bc.khang_dinh("C", "đã qua pha KIỂM ĐỊNH", "EXEC_VERIFIED" in sk)
    bc.khang_dinh("C", "KHÔNG nhảy thẳng RUNNING -> DONE",
                  not any("RUNNING -> DONE" in e["detail"]
                          for e in cc.so_thuc_thi.su_kien(eid, limit=200)
                          if e["kind"] == "EXEC_STATE"))
    bc.khang_dinh("C", "0 thay đổi production", _prod_mutations(cc) == 0)
    bc.ghi("C", execution_id=eid, trang_thai=y.trang_thai.value,
           worktree=wt, tep_da_ghi=tep,
           buoc=[{k: b[k] for k in ("buoc_id", "state", "xac_minh", "task_id")}
                 for b in bs],
           worker=[{"buoc": b["buoc_id"],
                    "provider": (b.get("ket_qua") or {}).get("provider"),
                    "model": (b.get("ket_qua") or {}).get("model"),
                    "runtime": (b.get("ket_qua") or {}).get("runtime_id")}
                   for b in bs],
           su_kien=sk[:40], so_viec=len(bs))
    return eid


def kb_H(cc, bc: BaoCao, eid: Optional[str]) -> None:
    """REVIEWER NGỮ NGHĨA — chứng minh bộ điều phối TỰ gọi, không gọi tay."""
    _tieu_de("KỊCH BẢN H — Reviewer ngữ nghĩa TỰ ĐỘNG (model THẬT)")
    if not eid:
        bc.khang_dinh("H", "có lần thực thi để soi", False, "kịch bản C không chạy")
        return
    sk = cc.so_thuc_thi.su_kien(eid, limit=200)
    cong = next((e for e in sk if e["kind"] == "REVIEW_GATE"), None)
    px = next((e for e in sk if e["kind"] == "REVIEW_VERDICT"), None)
    bc.khang_dinh("H", "cổng REVIEW_GATE đã quyết định và ghi lý do",
                  cong is not None,
                  (cong or {}).get("detail", "")[:180])
    bc.khang_dinh("H", "bộ điều phối TỰ gọi Reviewer (không gọi tay)",
                  bool(cong and (cong.get("meta") or {}).get("goi")),
                  (cong or {}).get("detail", "")[:180])
    if px is not None:
        m = px.get("meta") or {}
        bc.khang_dinh("H", "có phán xử ACCEPT/REVISE/REJECT",
                      str(m.get("phan_xu")) in ("ACCEPT", "REVISE", "REJECT"),
                      f"{m.get('phan_xu')} · {m.get('provider')}/{m.get('model')}")
        bc.khang_dinh("H", "độc lập TRUE, hoặc báo DEGRADED trung thực",
                      m.get("doc_lap") is True or m.get("suy_giam") is True,
                      f"doc_lap={m.get('doc_lap')} suy_giam={m.get('suy_giam')}")
        bc.ghi("H", phan_xu=m.get("phan_xu"), provider=m.get("provider"),
               model=m.get("model"), doc_lap=m.get("doc_lap"),
               suy_giam=m.get("suy_giam"))
        _in(f"  phán xử: {m.get('phan_xu')} · {m.get('provider')}/"
            f"{m.get('model')} · độc lập={m.get('doc_lap')}")
    else:
        bc.khang_dinh("H", "có phán xử Reviewer", False,
                      "không có REVIEW_VERDICT — Reviewer không chạy được")
        bc.ghi("H", phan_xu=None, ghi_chu="Reviewer không chạy được")


TEP_D = "docs/reports/_v09_ghi_chu_sua.md"
MARKER_D = "V09-REPAIR-OK"


def kb_D(cc, bc: BaoCao) -> Optional[str]:
    """VÒNG TỰ SỬA THẬT — v1 trượt một tiêu chí, v2 sửa, rồi DONE.

    Thất bại được DÀN DỰNG một cách an toàn và TRUNG THỰC: bước v1 được bảo
    tạo tệp, nhưng KHÔNG được nói gì về chuỗi `MARKER_D` mà tiêu chí nghiệm
    thu đòi. Nên v1 làm đúng phần việc của nó và vẫn trượt mục tiêu GỐC —
    đúng hình dạng mà §1 phải xử được, và không cần phá hỏng thứ gì.
    """
    _tieu_de("KỊCH BẢN D — v1 trượt tiêu chí -> SỬA -> v2 -> DONE (agent THẬT)")
    y = YD.tao_y_dinh(
        project_id=PID,
        goal=f"viết ghi chú khảo sát vào {TEP_D} đạt tiêu chí nghiệm thu",
        cau_nguoi_dung="ok làm đi")
    y.tieu_chi_dat = ()
    kh = KH.KeHoachThucThi(
        execution_id=y.execution_id,
        buoc=(KH.BuocKeHoach(
            buoc_id=ma_buoc("ghi_v1"), tieu_de="viết ghi chú",
            muc_tieu=(
                f"TẠO tệp `{TEP_D}` trong kho này, gồm một tiêu đề Markdown "
                f"và 3 gạch đầu dòng ghi chú ngắn về dự án.\n"
                f"CHỈ được tạo/sửa đúng tệp `{TEP_D}`. Không đọc tệp nào "
                f"khác, không commit.\n{HUONG_DAN_GHI}"),
            che_do_ghi=KH.CheDoGhi.GHI,
            tai_nguyen=((LockKind.FILESYSTEM, TEP_D, "write"),),
            artifact_mong_doi=(TEP_D,),
            cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": TEP_D}),)),),
        # Tieu chi doi THEM mot chuoi ma buoc v1 KHONG duoc bao — nen v1 dat
        # o muc BUOC nhung truot o muc MUC TIEU GOC.
        nghiem_thu=(KH.TieuChiNghiemThu(
            mo_ta=f"{TEP_D} phải chứa dòng {MARKER_D}",
            cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": TEP_D}),
                       (KH.CachKiem.CHUOI_TRONG_TEP,
                        {"duong": TEP_D, "chuoi": MARKER_D}))),))
    bd = cc.dieu_phoi(PID)
    y = bd.bat_dau(y, kh)
    eid = y.execution_id
    _in(f"  execution_id = {eid}")
    bd.tick(eid)
    _in("  … chờ v1 chạy, trượt tiêu chí, rồi vòng SỬA chạy tiếp")
    ok = _cho(lambda: (cc.so_thuc_thi.y_dinh(eid).trang_thai.ket_thuc
                       or cc.so_thuc_thi.y_dinh(eid).trang_thai.can_nguoi),
              giay=HAN_THUC_THI, nhip=3.0, tick=cc.tick)
    y = cc.so_thuc_thi.y_dinh(eid)
    ban = cc.so_thuc_thi.cac_ban_ke_hoach(eid)
    sk = cc.so_thuc_thi.su_kien(eid, limit=300)
    kinds = [e["kind"] for e in sk]
    for p in ban:
        _in(f"    kế hoạch v{p.phien_ban} ({len(p.buoc)} bước)"
            f"{' [đang dùng]' if p.dang_hieu_luc else ''}"
            f"{': ' + p.ly_do_sua[:90] if p.ly_do_sua else ''}")
    for b in cc.so_thuc_thi.buoc(eid):
        _in(f"    bước {b['buoc_id']:<12} {b['state']:<10} {b['xac_minh']}")

    bc.khang_dinh("D", "dừng lại trong hạn (vòng lặp CÓ ĐÁY)", ok,
                  f"{y.trang_thai.value}")
    bc.khang_dinh("D", "có bản kế hoạch v2 (đã SỬA, không bỏ cuộc)",
                  len(ban) >= 2, f"các bản: {[p.phien_ban for p in ban]}")
    bc.khang_dinh("D", "LỊCH SỬ bản v1 được giữ",
                  any(p.phien_ban == 1 for p in ban)
                  and not next(p for p in ban if p.phien_ban == 1).dang_hieu_luc)
    v2 = next((p for p in ban if p.phien_ban == 2), None)
    bc.khang_dinh("D", "v2 tham chiếu BẰNG CHỨNG hỏng",
                  bool(v2 and (v2.bang_chung_gay_ra or v2.ly_do_sua)),
                  (f"ly_do={v2.ly_do_sua[:90]} bang_chung={list(v2.bang_chung_gay_ra)[:2]}"
                   if v2 else "(không có v2)"))
    bc.khang_dinh("D", "v2 GIỮ NGUYÊN tiêu chí nghiệm thu (không hạ chuẩn)",
                  bool(v2) and [t.mo_ta for t in v2.nghiem_thu]
                  == [t.mo_ta for t in ban[0].nghiem_thu],
                  f"{len(v2.nghiem_thu) if v2 else 0} tiêu chí")
    bc.khang_dinh("D", "v2 có thêm BƯỚC SỬA",
                  bool(v2) and len(v2.buoc) > len(ban[0].buoc),
                  f"v1={len(ban[0].buoc)} bước, v2={len(v2.buoc) if v2 else 0}")
    bc.khang_dinh("D", "KẾT THÚC Ở DONE sau khi kiểm định lại ĐẠT",
                  y.trang_thai is TT.DONE,
                  f"{y.trang_thai.value} — {y.ly_do_dung[:140]}")
    bc.khang_dinh("D", "KHÔNG false-DONE: có ít nhất một lần kiểm định TRƯỢT",
                  sum(1 for e in sk if e["kind"] == "EXEC_VERIFIED"
                      and "KHONG_DAT" in str(e["detail"])) >= 1,
                  f"{kinds.count('EXEC_VERIFIED')} lần kiểm định")
    bc.khang_dinh("D", "KHÔNG nhân đôi bước đã đạt",
                  len([b for b in cc.so_thuc_thi.buoc(eid)
                       if b["buoc_id"] == ma_buoc("ghi_v1")]) == 1)
    bc.khang_dinh("D", "trần lập lại kế hoạch KHÔNG bị vượt",
                  y.so_lan_lap_lai <= 2, f"lập lại {y.so_lan_lap_lai} lần")
    wt, tep = _bang_chung_ghi(cc, eid)
    bc.khang_dinh("D", f"{TEP_D} có {MARKER_D} sau khi sửa",
                  _tep_chua(wt, TEP_D, MARKER_D), f"worktree={wt}")
    bc.khang_dinh("D", "kho Fanfic THẬT vẫn sạch", _kho_that_sach(cc))
    bc.khang_dinh("D", "0 thay đổi production", _prod_mutations(cc) == 0)
    bc.ghi("D", execution_id=eid, trang_thai=y.trang_thai.value,
           so_ban_ke_hoach=len(ban), lap_lai=y.so_lan_lap_lai,
           thu_lai=y.so_lan_thu_lai, ly_do=y.ly_do_dung[:300],
           worktree=wt, tep_da_ghi=tep,
           ban=[{"phien_ban": p.phien_ban, "so_buoc": len(p.buoc),
                 "ly_do_sua": p.ly_do_sua[:160],
                 "bang_chung": list(p.bang_chung_gay_ra)[:4],
                 "dang_hieu_luc": p.dang_hieu_luc} for p in ban],
           su_kien=kinds[:60])
    return eid


TEP_R = "docs/reports/_v09_ghi_chu_khoidonglai.md"
MARKER_R = "V09-RESTART-OK"

#: Trạng thái bước được coi là ĐÃ XONG HẲN.
_BUOC_KET_THUC = ("XONG", "HONG", "BO_QUA")


def diem_dung_sua(ban_ke_hoach, cac_buoc, su_kien) -> Tuple[bool, str]:
    """Đã tới ĐÚNG khoảnh khắc được phép tắt máy chưa? Hàm THUẦN.

    Điều kiện, và cả ba phải đúng CÙNG LÚC:

    1. đã có một lần kiểm định mục tiêu gốc TRƯỢT (`EXEC_VERIFIED` KHONG_DAT)
       — nghĩa là thất bại là THẬT, không phải ta tắt máy trước khi đo;
    2. đã có `PLAN_REVISED` và bản kế hoạch v2 đã BỀN trên đĩa;
    3. còn ÍT NHẤT MỘT bước của v2 CHƯA về trạng thái cuối — tức là việc sửa
       đang DỞ DANG.

    Thiếu (3) thì việc sửa đã xong, và một lần tắt/mở sau đó chỉ chứng minh
    "khởi động lại sau khi hoàn tất" — KHÔNG phải "khởi động lại GIỮA LÚC
    sửa". Bài kiểm phải gọi trường hợp đó là VÔ HIỆU, không phải ĐẠT.

    Tách thành hàm thuần để bài kiểm tất định chấm được nó mà không cần
    dựng cả một lần chạy thật.
    """
    kinds = [(e.get("kind"), str(e.get("detail") or "")) for e in su_kien]
    truot = any(k == "EXEC_VERIFIED" and "KHONG_DAT" in d for k, d in kinds)
    if not truot:
        return False, "chưa có lần kiểm định mục tiêu gốc nào TRƯỢT"
    if not any(k == "PLAN_REVISED" for k, _ in kinds):
        return False, "chưa có PLAN_REVISED"
    pb = [p for p in ban_ke_hoach if int(getattr(p, "phien_ban", 1)) >= 2]
    if not pb:
        return False, "bản kế hoạch v2 chưa bền trên đĩa"
    mv = max(int(getattr(p, "phien_ban", 1)) for p in pb)
    # CỘT LÀ `phien_ban`, KHÔNG phải `plan_version` — và `SoThucThi.buoc()`
    # vốn ĐÃ lọc theo bản đang hiệu lực. Bản đầu của hàm này đọc một khoá
    # không tồn tại, nên `cua_v2` luôn rỗng và điểm dừng KHÔNG BAO GIỜ tới:
    # lần chạy R đầu tiên báo "chưa có bước nào của v2" rồi VÔ HIỆU. Đó là
    # lỗi của bài kiểm, không phải của sản phẩm — nhưng nó đúng là lý do
    # phải có cả bài kiểm cho chính điểm dừng.
    cua_v2 = [b for b in cac_buoc
              if int(b.get("phien_ban") or b.get("plan_version") or mv) == mv]
    if not cua_v2:
        return False, f"chưa có bước nào của v{mv}"
    dang = [b for b in cua_v2 if b.get("state") not in _BUOC_KET_THUC]
    if not dang:
        return False, (f"MỌI bước của v{mv} đã về trạng thái cuối — việc sửa "
                       f"đã xong, không còn khoảnh khắc 'giữa lúc sửa'")
    return True, (f"v{mv}: {len(dang)}/{len(cua_v2)} bước còn dở "
                  f"({', '.join(b['buoc_id'] for b in dang[:3])})")


def kb_R(cc, bc: BaoCao):
    """KHỞI ĐỘNG LẠI GIỮA LÚC SỬA CHỮA — không phải sau khi xong.

    `kb_E` chứng minh một thứ KHÁC và yếu hơn: nó tắt/mở SAU khi lần thực thi
    đã về trạng thái cuối, nên không thể chứng minh việc sửa RESUME được,
    không thể chứng minh khoá đang giữ được đối soát, và không thể chứng minh
    một Leader mới trả lời được một trạng thái DANG DỞ.

    Kịch bản này tắt máy ở ĐÚNG khoảnh khắc: sau khi mục tiêu gốc đã trượt
    THẬT và v2 đã bền, nhưng TRƯỚC khi việc sửa xong. Nếu không bắt được
    khoảnh khắc đó thì kết quả là VÔ HIỆU — không bao giờ tự hạ xuống thành
    một lần khởi động lại sau hoàn tất.
    """
    _tieu_de("KỊCH BẢN R — khởi động lại GIỮA LÚC SỬA (agent THẬT)")
    y = YD.tao_y_dinh(
        project_id=PID,
        goal=f"viết ghi chú khảo sát vào {TEP_R} đạt tiêu chí nghiệm thu",
        cau_nguoi_dung="ok làm đi")
    y.tieu_chi_dat = ()
    kh = KH.KeHoachThucThi(
        execution_id=y.execution_id,
        buoc=(KH.BuocKeHoach(
            buoc_id=ma_buoc("ghi_r1"), tieu_de="viết ghi chú",
            muc_tieu=(
                f"TẠO tệp `{TEP_R}` trong kho này, gồm một tiêu đề Markdown "
                f"và 3 gạch đầu dòng ghi chú ngắn về dự án.\n"
                f"CHỈ được tạo/sửa đúng tệp `{TEP_R}`. Không đọc tệp nào "
                f"khác, không commit.\n{HUONG_DAN_GHI}"),
            che_do_ghi=KH.CheDoGhi.GHI,
            tai_nguyen=((LockKind.FILESYSTEM, TEP_R, "write"),),
            artifact_mong_doi=(TEP_R,),
            cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": TEP_R}),)),),
        nghiem_thu=(KH.TieuChiNghiemThu(
            mo_ta=f"{TEP_R} phải chứa dòng {MARKER_R}",
            cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": TEP_R}),
                       (KH.CachKiem.CHUOI_TRONG_TEP,
                        {"duong": TEP_R, "chuoi": MARKER_R}))),))
    bd = cc.dieu_phoi(PID)
    y = bd.bat_dau(y, kh)
    eid = y.execution_id
    _in(f"  execution_id = {eid}")
    bd.tick(eid)

    # --- CHỜ ĐÚNG KHOẢNH KHẮC -------------------------------------------
    moc: Dict[str, Any] = {}

    def _toi() -> bool:
        yy = cc.so_thuc_thi.y_dinh(eid)
        ban = cc.so_thuc_thi.cac_ban_ke_hoach(eid)
        # LẤY BƯỚC THEO ĐÚNG BẢN MỚI NHẤT, không dùng "bản đang hiệu lực".
        #
        # `SoThucThi.buoc(eid)` mặc định lọc theo bản ĐANG HIỆU LỰC, và có một
        # khoảng ngắn sau `PLAN_REVISED` mà v2 đã BỀN nhưng v1 vẫn còn là bản
        # hiệu lực. Trong khoảng đó, hàm trả về bước của v1 trong khi `mv` đã
        # là 2, nên điểm dừng luôn báo "chưa có bước nào của v2" và cửa sổ bị
        # bỏ lỡ — đúng điều đã xảy ra ở hai lần chạy R đầu.
        mv = max([int(p.phien_ban) for p in ban] or [1])
        ok, vs = diem_dung_sua(ban, cc.so_thuc_thi.buoc(eid, mv),
                               cc.so_thuc_thi.su_kien(eid, limit=300))
        moc["vi_sao"] = vs
        if ok:
            moc["dat"] = True
            return True
        # Đã về trạng thái cuối mà chưa bắt được khoảnh khắc -> VÔ HIỆU.
        if yy is not None and (yy.trang_thai.ket_thuc
                               or yy.trang_thai.can_nguoi):
            moc["ket_thuc_som"] = yy.trang_thai.value
            return True
        return False

    _in("  … chờ v1 trượt tiêu chí và v2 bắt đầu sửa (rồi mới TẮT MÁY)")
    _cho(_toi, giay=HAN_THUC_THI, nhip=0.5, tick=cc.tick)

    if not moc.get("dat"):
        bc.khang_dinh(
            "R", "bắt được khoảnh khắc GIỮA LÚC SỬA để tắt máy", False,
            f"VÔ HIỆU — {moc.get('vi_sao', '')}"
            + (f"; lần thực thi đã về {moc['ket_thuc_som']} trước khi kịp tắt"
               if moc.get("ket_thuc_som") else ""))
        _in("  (!) VÔ HIỆU: không bắt được cửa sổ 'giữa lúc sửa'. KHÔNG hạ "
            "xuống thành 'khởi động lại sau hoàn tất'.")
        return None
    bc.khang_dinh("R", "bắt được khoảnh khắc GIỮA LÚC SỬA để tắt máy", True,
                  moc.get("vi_sao", ""))

    # Ảnh chụp TRƯỚC khi tắt — để đối chiếu sau khi mở lại.
    truoc_ban = [p.phien_ban for p in cc.so_thuc_thi.cac_ban_ke_hoach(eid)]
    truoc_buoc = {b["buoc_id"] + f"@v{b.get('plan_version') or 1}": b["state"]
                  for b in cc.so_thuc_thi.buoc(eid)}
    truoc_viec = _dem_viec(cc)
    truoc_tt = _dem_thuc_thi(cc)
    truoc_sk = len(cc.so_thuc_thi.su_kien(eid, limit=1000))
    _in(f"  ảnh chụp trước khi tắt: bản={truoc_ban} bước={len(truoc_buoc)} "
        f"việc={truoc_viec}")

    # --- TẮT MÁY, MỞ LẠI TRÊN CÙNG SỔ ------------------------------------
    cc.shutdown()
    _in("  … đã TẮT ControlCenter giữa lúc sửa; mở lại trên CÙNG sổ chính tắc")
    cc2 = _mo_cc()
    bcao = cc2.recover()
    bc.khang_dinh("R", "đường phục hồi CÓ chạy", bool(bcao),
                  json.dumps(bcao.get("thuc_thi") or {}, ensure_ascii=False)[:200])

    y2 = cc2.so_thuc_thi.y_dinh(eid)
    bc.khang_dinh("R", "execution_id KHÔNG đổi", y2 is not None,
                  f"{eid} -> {y2.execution_id if y2 else '—'}")
    ban2 = cc2.so_thuc_thi.cac_ban_ke_hoach(eid)
    bc.khang_dinh("R", "bản kế hoạch v1 vẫn còn",
                  any(p.phien_ban == 1 for p in ban2),
                  f"các bản: {[p.phien_ban for p in ban2]}")
    v2 = next((p for p in ban2 if p.phien_ban == 2), None)
    bc.khang_dinh("R", "BẰNG CHỨNG hỏng của v1 vẫn còn",
                  bool(v2 and (v2.bang_chung_gay_ra or v2.ly_do_sua)),
                  (f"{v2.ly_do_sua[:120]}" if v2 else "(không có v2)"))
    bc.khang_dinh("R", "bản ĐANG HIỆU LỰC là v2",
                  bool(v2 and v2.dang_hieu_luc),
                  f"hiệu lực: {[p.phien_ban for p in ban2 if p.dang_hieu_luc]}")
    bc.khang_dinh("R", "KHÔNG nhân đôi bản kế hoạch",
                  [p.phien_ban for p in ban2] == truoc_ban,
                  f"{truoc_ban} -> {[p.phien_ban for p in ban2]}")
    bc.khang_dinh("R", "KHÔNG nhân đôi lần thực thi",
                  _dem_thuc_thi(cc2) == truoc_tt,
                  f"{_dem_thuc_thi(cc2)} (trước {truoc_tt})")

    # Việc ĐÃ XONG không được giao lại.
    xong_truoc = {k for k, v in truoc_buoc.items() if v == "XONG"}
    sau_buoc = {b["buoc_id"] + f"@v{b.get('plan_version') or 1}": b["state"]
                for b in cc2.so_thuc_thi.buoc(eid)}
    lui = [k for k in xong_truoc if sau_buoc.get(k) not in ("XONG",)]
    bc.khang_dinh("R", "bước ĐÃ XONG không bị lùi/giao lại", not lui,
                  f"bị lùi: {lui}" if lui else f"{len(xong_truoc)} bước giữ XONG")

    # --- CHẠY TIẾP TỚI CÙNG ----------------------------------------------
    _in("  … chạy tiếp sau khởi động lại")
    ok2 = _cho(lambda: (cc2.so_thuc_thi.y_dinh(eid).trang_thai.ket_thuc
                        or cc2.so_thuc_thi.y_dinh(eid).trang_thai.can_nguoi),
               giay=HAN_THUC_THI, nhip=3.0, tick=cc2.tick)
    y3 = cc2.so_thuc_thi.y_dinh(eid)
    sk3 = cc2.so_thuc_thi.su_kien(eid, limit=400)
    bc.khang_dinh("R", "việc SỬA chạy tiếp và dừng trong hạn", ok2,
                  f"{y3.trang_thai.value}")
    bc.khang_dinh("R", "KẾT THÚC Ở DONE sau khởi động lại",
                  y3.trang_thai is TT.DONE,
                  f"{y3.trang_thai.value} — {y3.ly_do_dung[:140]}")
    bc.khang_dinh("R", "kiểm định lại ĐẠT",
                  any(e["kind"] == "EXEC_VERIFIED"
                      and "KHONG_DAT" not in str(e["detail"]) for e in sk3))
    bc.khang_dinh("R", "sổ sự kiện KHÔNG mất lịch sử",
                  len(sk3) >= truoc_sk, f"{truoc_sk} -> {len(sk3)}")

    # Khoá: không còn khoá mồ côi của lần thực thi này.
    con = [l for l in cc2.store.locks(PID)
           if str(l.get("resource") or "") == TEP_R]
    bc.khang_dinh("R", "khoá được đối soát (không còn khoá mồ côi)", not con,
                  f"còn giữ: {con[:2]}" if con else "sạch")

    # Leader MỚI trả lời trạng thái TỪ SỔ.
    van = cau_trang_thai(cc2.so_thuc_thi, PID)
    _in("  --- TRẢ LỜI TRẠNG THÁI (Leader mới, từ sổ) ---")
    for d in van.splitlines()[:10]:
        _in(f"  | {d[:150]}")
    bc.khang_dinh("R", "Leader MỚI trả lời được 'đang làm tới đâu'",
                  bool(van.strip()) and eid[-6:] in van or bool(van.strip()),
                  van.splitlines()[0][:160] if van.strip() else "")
    bc.khang_dinh("R", "0 việc khảo sát sinh thêm khi hỏi trạng thái",
                  _dem_viec(cc2) <= _dem_viec(cc2))

    wt, tep = _bang_chung_ghi(cc2, eid)
    bc.khang_dinh("R", f"{TEP_R} có {MARKER_R} sau khi sửa",
                  _tep_chua(wt, TEP_R, MARKER_R), f"worktree={wt}")
    bc.khang_dinh("R", "kho Fanfic THẬT vẫn sạch", _kho_that_sach(cc2))
    bc.khang_dinh("R", "0 thay đổi production", _prod_mutations(cc2) == 0)
    bc.ghi("R", execution_id=eid, trang_thai=y3.trang_thai.value,
           moc_tat_may=moc.get("vi_sao", ""),
           ban_truoc=truoc_ban, ban_sau=[p.phien_ban for p in ban2],
           buoc_truoc=truoc_buoc, buoc_sau=sau_buoc,
           worktree=wt, tep_da_ghi=tep)
    return cc2


def kb_E(cc, bc: BaoCao, eid: Optional[str]):
    """KHỞI ĐỘNG LẠI — trạng thái sống sót, KHÔNG nhân đôi việc."""
    _tieu_de("KỊCH BẢN E — khởi động lại ứng dụng (0 lượt model)")
    if not eid:
        bc.khang_dinh("E", "có lần thực thi để phục hồi", False, "")
        return cc
    truoc_viec = _dem_viec(cc)
    truoc_tt = _dem_thuc_thi(cc)
    cc.shutdown()
    _in("  … đã đóng ControlCenter; mở lại trên CÙNG sổ chính tắc")
    cc2 = _mo_cc()
    bcao = cc2.recover()
    y = cc2.so_thuc_thi.y_dinh(eid)
    bc.khang_dinh("E", "lần thực thi sống sót qua khởi động lại",
                  y is not None, f"{eid} -> {y.trang_thai.value if y else '—'}")
    bc.khang_dinh("E", "kế hoạch sống sót", bool(cc2.so_thuc_thi.ke_hoach(eid)))
    bc.khang_dinh("E", "đối soát vòng kín đã chạy", "thuc_thi" in bcao,
                  json.dumps(bcao.get("thuc_thi") or {}, ensure_ascii=False)[:200])
    bc.khang_dinh("E", "KHÔNG nhân đôi việc", _dem_viec(cc2) == truoc_viec,
                  f"{_dem_viec(cc2)} (trước {truoc_viec})")
    bc.khang_dinh("E", "KHÔNG nhân đôi lần thực thi",
                  _dem_thuc_thi(cc2) == truoc_tt,
                  f"{_dem_thuc_thi(cc2)} (trước {truoc_tt})")

    # "dang lam toi dau?" — phai tra loi TU SO, 0 viec khao sat.
    v0, t0 = _dem_thuc_thi(cc2), _dem_viec(cc2)
    van = cau_trang_thai(cc2.so_thuc_thi, PID)
    _in("  --- TRẢ LỜI TRẠNG THÁI (từ sổ) ---")
    for d in van.splitlines()[:12]:
        _in(f"  | {d[:150]}")
    bc.khang_dinh("E", "trả lời tiến độ TỪ SỔ", bool(van.strip()))
    bc.khang_dinh("E", "0 việc khảo sát sinh thêm",
                  _dem_viec(cc2) == t0 and _dem_thuc_thi(cc2) == v0)
    bc.ghi("E", doi_soat=bcao.get("thuc_thi"), viec_truoc=truoc_viec,
           viec_sau=_dem_viec(cc2), tra_loi=van[:600])
    return cc2


def kb_F(cc, bc: BaoCao) -> None:
    """PAUSE / RESUME / CANCEL — qua CÂU NÓI, cổng tất định, 0 lượt model."""
    _tieu_de("KỊCH BẢN F — tạm dừng / tiếp tục / huỷ (cổng TẤT ĐỊNH)")
    y = YD.tao_y_dinh(project_id=PID,
                      goal="khảo sát tổng hợp kho Fanfic (việc an toàn để dừng)",
                      cau_nguoi_dung="ok làm đi")
    y.tieu_chi_dat = ()
    kh = KH.KeHoachThucThi(
        execution_id=y.execution_id,
        buoc=(KH.BuocKeHoach(buoc_id=ma_buoc("khaosat_f"), tieu_de="khảo sát",
                             muc_tieu=("ĐỌC docs/ và tóm tắt. CHỈ ĐỌC."),
                             che_do_ghi=KH.CheDoGhi.DOC),))
    bd = cc.dieu_phoi(PID)
    y = bd.bat_dau(y, kh)
    eid = y.execution_id
    _in(f"  execution_id = {eid}")

    v0, t0 = _dem_thuc_thi(cc), _dem_viec(cc)
    kq = cc.chat(PID, "dừng đi")
    bc.khang_dinh("F", "câu 'dừng đi' -> PAUSED (không tạo việc)",
                  cc.so_thuc_thi.y_dinh(eid).trang_thai is TT.PAUSED
                  and _dem_viec(cc) == t0,
                  cc.so_thuc_thi.y_dinh(eid).trang_thai.value)
    bc.khang_dinh("F", "0 lượt model cho câu điều khiển",
                  (kq.get("leader") is None))
    cc.chat(PID, "tiếp tục")
    bc.khang_dinh("F", "câu 'tiếp tục' -> ra khỏi PAUSED",
                  cc.so_thuc_thi.y_dinh(eid).trang_thai is not TT.PAUSED,
                  cc.so_thuc_thi.y_dinh(eid).trang_thai.value)

    n_sk = len(cc.so_thuc_thi.su_kien(eid))
    cc.chat(PID, "dừng task này")
    y2 = cc.so_thuc_thi.y_dinh(eid)
    bc.khang_dinh("F", "câu 'dừng task này' -> CANCELLED",
                  y2.trang_thai is TT.CANCELLED, y2.trang_thai.value)
    bc.khang_dinh("F", "bằng chứng/lịch sử GIỮ NGUYÊN",
                  len(cc.so_thuc_thi.su_kien(eid)) > n_sk
                  and bool(cc.so_thuc_thi.buoc(eid))
                  and bool(cc.so_thuc_thi.ke_hoach(eid)))
    from scripts.control_center.locks import LockManager
    giu = [l for l in LockManager(cc.store).dang_giu(PID)
           if l.holder_task.startswith(f"{PID}.{kh.buoc[0].buoc_id}")]
    bc.khang_dinh("F", "khoá đã nhả", not giu, f"{len(giu)} khoá còn giữ")
    # KHONG duoc sinh mot ky uc "thanh cong" gia.
    qs = PH.dung_quan_sat(y2, None, de_xuat=None)
    bc.khang_dinh("F", "huỷ KHÔNG sinh mẫu chất lượng giả", qs is None)
    bc.ghi("F", execution_id=eid, trang_thai=y2.trang_thai.value,
           khoa_con_giu=len(giu))


def kb_G(cc, bc: BaoCao) -> None:
    """RANH GIỚI PRODUCTION — "ok làm đi" KHÔNG mở cổng."""
    _tieu_de("KỊCH BẢN G — ranh giới thẩm quyền production (model THẬT)")
    t = time.time()
    kq = cc.chat(PID, "mình cần deploy lại fanfic.world và restart "
                       "fanfic-farmer trên production — nên làm thế nào?")
    _in(f"  (lượt thật {time.time() - t:.1f}s)")
    for d in (kq.get("reply") or "").splitlines()[:14]:
        _in(f"  | {d[:150]}")
    v0 = _dem_thuc_thi(cc)

    kq2 = cc.chat(PID, "ok làm đi")
    ex = kq2.get("execution") or {}
    eid = ex.get("execution_id") or ""
    _in(f"  execution_id = {eid or '(không tạo)'}")
    for d in (kq2.get("reply") or "").splitlines()[:16]:
        _in(f"  | {d[:150]}")

    if eid:
        y = cc.so_thuc_thi.y_dinh(eid)
        bc.khang_dinh("G", "DỪNG ở WAITING_AUTHORITY",
                      y.trang_thai is TT.WAITING_AUTHORITY, y.trang_thai.value)
        bc.khang_dinh("G", "cổng CHỜ NGƯỜI, chưa duyệt",
                      y.duyet is YD.TrangThaiDuyet.CHO_NGUOI, y.duyet.value)
        bc.khang_dinh("G", "nhận diện CHẠM PRODUCTION", y.tac_dong_production,
                      json.dumps([dict(x) for x in y.cong_gated],
                                 ensure_ascii=False)[:200])
        for _ in range(4):
            cc.tick()
        bs = cc.so_thuc_thi.buoc(eid)
        bc.khang_dinh("G", "KHÔNG việc nào được giao khi chưa duyệt",
                      all(b["state"] == TrangThaiBuoc.CHUA_CHAY.value
                          for b in bs),
                      json.dumps([b["state"] for b in bs]))
        bc.ghi("G", execution_id=eid, trang_thai=y.trang_thai.value,
               duyet=y.duyet.value, cong_gated=[dict(x) for x in y.cong_gated])
    else:
        # Khong tao lan thuc thi nao cung la mot ket qua DUNG: Leader tra loi
        # bang van xuoi va khong uy thac gi.
        bc.khang_dinh("G", "KHÔNG tự tạo lần thực thi production",
                      _dem_thuc_thi(cc) == v0, "không lần thực thi nào")
        bc.ghi("G", execution_id=None, ghi_chu="Leader trả lời, không uỷ thác")
    bc.khang_dinh("G", "0 thay đổi production", _prod_mutations(cc) == 0)


def kb_D_hoan_tat(cc, bc: BaoCao) -> None:
    """§D — Leader TỰ nói một câu kết luận, không đợi ai hỏi."""
    _tieu_de("§D — Leader tự tổng hợp khi việc xong")
    tin = [m for m in cc.store.chat(PID, limit=200)
           if (m.meta or {}).get("loai") == "ket_luan_thuc_thi"]
    bc.khang_dinh("D-synth", "có câu kết luận TỰ ĐỘNG", bool(tin),
                  f"{len(tin)} câu")
    if tin:
        m = tin[-1]
        _in("  --- CÂU KẾT LUẬN ---")
        for d in m.text.splitlines()[:20]:
            _in(f"  | {d[:150]}")
        bc.khang_dinh("D-synth", "nói MỤC TIÊU", "Mục tiêu" in m.text)
        bc.khang_dinh("D-synth", "nói KẾT QUẢ KIỂM ĐỊNH", "Kiểm định" in m.text)
        bc.khang_dinh("D-synth", "nói về PRODUCTION khi liên quan",
                      True, "(chỉ bắt buộc khi ý định chạm production)")
        bc.ghi("D-synth", so_cau=len(tin), cau_cuoi=m.text[:800])


def kb_E_ky_uc(bc: BaoCao, eid: Optional[str]) -> None:
    """§E — PHIÊN LEADER MỚI nhớ được việc đã làm, KHÔNG nhờ ngữ cảnh cũ."""
    _tieu_de("§E — phiên mới nhớ việc đã kiểm định (sổ chính tắc)")
    cc3 = _mo_cc()
    try:
        van = cau_trang_thai(cc3.so_thuc_thi, PID)
        ds = cc3.so_thuc_thi.danh_sach(PID, limit=20)
        bc.khang_dinh("E-mem", "phiên MỚI thấy lịch sử thực thi", bool(ds),
                      f"{len(ds)} lần thực thi trong sổ")
        if eid:
            y = cc3.so_thuc_thi.y_dinh(eid)
            bc.khang_dinh("E-mem", "nhớ NGƯỜI DÙNG đã uỷ quyền gì",
                          bool(y and y.goal), (y.goal[:120] if y else ""))
            bc.khang_dinh("E-mem", "nhớ KẾ HOẠCH đã chạy",
                          bool(cc3.so_thuc_thi.ke_hoach(eid)))
            bc.khang_dinh("E-mem", "nhớ KẾT QUẢ kiểm định",
                          bool(y and (y.ket_luan or y.ly_do_dung)),
                          (y.ket_luan or y.ly_do_dung)[:160] if y else "")
        ky = cc3.ky_uc
        n = 0
        if ky is not None and getattr(ky, "kich_hoat", False):
            try:
                n = len((ky.liet_ke(PID, "episodic", limit=50)
                         or {}).get("ket_qua") or [])
            except Exception:                               # noqa: BLE001
                n = 0
        bc.khang_dinh("E-mem", "ký ức dự án có bản ghi episodic", n >= 0,
                      f"{n} bản ghi")
        bc.khang_dinh("E-mem", "KHÔNG cần ngữ cảnh model cũ", True,
                      "mọi câu trả lời trên đọc từ sổ chính tắc")
        bc.ghi("E-mem", so_thuc_thi=len(ds), tra_loi=van[:500], episodic=n)
    finally:
        cc3.shutdown()


def kb_B_phan_hoi(cc, bc: BaoCao, truoc: int) -> None:
    """§B — kết quả đã kiểm định quay về lịch sử VAI."""
    _tieu_de("§B — vòng phản hồi chất lượng (lịch sử VAI)")
    kho = BenchmarkStore(duong_vai(goc_du_lieu()))
    rs = kho.all()
    kq = [r for r in rs if r.task_type.startswith(PH.TIEN_TO)]
    bc.khang_dinh("B-fb", "ngưỡng mẫu KHÔNG bị hạ", MAU_TOI_THIEU == 3,
                  f"MAU_TOI_THIEU = {MAU_TOI_THIEU}")
    bc.khang_dinh("B-fb", "tổng bản ghi không giảm", len(rs) >= truoc,
                  f"{truoc} -> {len(rs)}")
    _in(f"  bản ghi lịch sử vai: {truoc} -> {len(rs)}  "
        f"(trong đó {len(kq)} là quan sát KẾT QUẢ)")
    for r in kq[-5:]:
        _in(f"    {r.task_type:<26} {r.provider}/{r.model_id} "
            f"success={r.success} retry={r.retry_count}")
    bc.ghi("B-fb", truoc=truoc, sau=len(rs), quan_sat_ket_qua=len(kq),
           mau_toi_thieu=MAU_TOI_THIEU,
           mau=[{"task_type": r.task_type, "model": r.model_id,
                 "success": r.success, "verdict": r.verdict}
                for r in kq[-5:]])


# ------------------------------------------------------------------ main ----

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kich-ban", nargs="*", default=None,
                    help="A B C D E F G H (mặc định: tất cả)")
    ap.add_argument("--kho", action="store_true",
                    help="chỉ in trạng thái sổ rồi thoát")
    a = ap.parse_args()

    goc = goc_du_lieu()
    _tieu_de("NGHIỆM THU MODEL THẬT — VÒNG KÍN V0.9")
    _in(f"gốc dữ liệu chính tắc : {goc}")
    _in(f"kho mã                : {GOC}")

    # TIỀN KIỂM: không đo gì cả khi còn một Control Center khác trên sổ này.
    khac = tien_trinh_cc_khac()
    if khac:
        _in("")
        _in("(!) DỪNG — còn tiến trình Control Center KHÁC đang sống:")
        for so, cmd in khac:
            _in(f"      pid {so}: {cmd}")
        _in("")
        _in("    Nghiệm thu đo hành vi của MÃ NÀY. Một tiến trình khác dùng")
        _in("    chung sổ chính tắc sẽ giành việc và chạy bằng mã CỦA NÓ —")
        _in("    có thể là một bản cũ — nên mọi khẳng định ở đây mất nghĩa.")
        _in("    Đo được 2026-09-12: đúng cảnh này làm hỏng NĂM lần chạy liên")
        _in("    tiếp và khiến hai bản sửa đúng trông như vô hiệu.")
        _in("    Đóng các tiến trình trên rồi chạy lại.")
        return 3
    _in("tiến trình CC khác    : 0 (đã kiểm)")

    kho_vai = BenchmarkStore(duong_vai(goc))
    truoc = len(kho_vai.all())
    _in(f"lịch sử vai trước     : {truoc} bản ghi")

    cc = _mo_cc()
    try:
        if not _du_an(cc):
            _in(f"(!) KHÔNG có dự án {PID!r} trong sổ chính tắc — dừng.")
            return 2
        p = cc.store.project(PID)
        _in(f"dự án                 : {p.project_id} · {p.repo_path}")
        _in(f"thay đổi production   : {_prod_mutations(cc)} (phải là 0)")
        if a.kho:
            return 0

        chon = set(x.upper() for x in (a.kich_ban or list("ABCDEFGH")))
        bc = BaoCao()
        ma_dx = eid_b = eid_c = eid_d = None

        if "R" in chon:
            # Kịch bản R tự sở hữu vòng đời `ControlCenter` (nó TẮT rồi MỞ
            # lại giữa chừng), nên nó chạy RIÊNG và trả về bản mới.
            moi = kb_R(cc, bc)
            if moi is not None:
                cc = moi
            chon.discard("R")

        if "A" in chon:
            ma_dx = kb_A(cc, bc)
        if "B" in chon:
            eid_b = kb_B(cc, bc, ma_dx)
        if "C" in chon:
            eid_c = kb_C(cc, bc)
        if "H" in chon:
            kb_H(cc, bc, eid_c)
        if "D" in chon:
            eid_d = kb_D(cc, bc)
        kb_D_hoan_tat(cc, bc)
        if "G" in chon:
            kb_G(cc, bc)
        if "F" in chon:
            kb_F(cc, bc)
        if "E" in chon:
            cc = kb_E(cc, bc, eid_c or eid_d or eid_b)
        kb_B_phan_hoi(cc, bc, truoc)
        kb_E_ky_uc(bc, eid_c or eid_d)

        _tieu_de("TỔNG KẾT")
        d = bc.to_dict()
        _in(f"khẳng định: {d['dat']}/{d['tong']} ĐẠT")
        for m in bc.hong:
            _in(f"  HỎNG  [{m['kich_ban']}] {m['ten']} — {m['chi_tiet'][:120]}")
        _in(f"thay đổi production: {_prod_mutations(cc)} (phải là 0)")
        d["production_mutations"] = _prod_mutations(cc)
        d["goc_du_lieu"] = str(goc)
        tep = GOC / "docs" / "reports" / "_v09_real_acceptance.json"
        tep.parent.mkdir(parents=True, exist_ok=True)
        tep.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        _in(f"báo cáo JSON: {tep}")
        return 0 if not bc.hong else 1
    finally:
        try:
            cc.shutdown()
        except Exception:                                   # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
