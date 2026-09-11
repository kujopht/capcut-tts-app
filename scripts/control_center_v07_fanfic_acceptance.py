# -*- coding: utf-8 -*-
"""Nghiệm thu THẬT V0.7 Phase 1 — NHẬN Fanfic + Viên nang + Liên tục.

    python scripts/control_center_v07_fanfic_acceptance.py --mo-lai
    python scripts/control_center_v07_fanfic_acceptance.py --chi hoi

Chạy trên GỐC DỮ LIỆU CHÍNH TẮC mà app thật của người dùng dùng (không phải sổ
tạm), qua API cục bộ của chính app mở bằng đường source-mode.

Đo đúng những gì Phần O đòi: kết quả nhận, mục viên nang, phủ bằng chứng, điểm
liên tục, cỡ ngữ cảnh, SỐ LẦN DISPATCH WORKER cho câu hỏi lịch sử (phải 0),
phép đo SỐNG cho câu hỏi hiện tại, và số lần sửa production (phải 0).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.duong_du_lieu import goc_du_lieu           # noqa: E402
from scripts.control_center_v061_ky_uc_web_acceptance import (App, Bang,  # noqa: E402
                                                              _con_song,
                                                              doc_lock,
                                                              dong_nhe, ghi,
                                                              mo_source_mode)

KHO_FANFIC = r"C:\Users\nguye\Documents\CapCut-TTS-App"
DU_AN = "fanfic"

#: 12 câu Phần G — TẤT CẢ là câu hỏi lịch sử/bối cảnh dự án: phải trả từ
#: Viên nang + Ký ức, KHÔNG được dispatch worker đi khám phá lại.
CAU_HOI: Tuple[Tuple[str, str], ...] = (
    ("tien_do",     "project fanfic.world hiện làm tới đâu?"),
    ("kien_truc",   "kiến trúc hiện tại của project này ra sao?"),
    ("farmer_o_dau", "production farmer chạy ở đâu?"),
    ("router_0",    "tại sao Router task bằng 0 không có nghĩa production đã dừng?"),
    ("r2_drive",    "R2 và Google Drive đang có vai trò khác nhau thế nào?"),
    ("legacy",      "legacy archive tại sao không được tự động đụng vào?"),
    ("ssh",         "vụ SSH key fanficappwrite trước đây là gì?"),
    ("gioi_han",    "bug / limitation >100k chapter hiện tại là gì?"),
    ("ag_account",  "hiện Router có bao nhiêu Antigravity account cho project?"),
    ("validated",   "những work production nào trước đây đã được validate?"),
    ("issue",       "những issue quan trọng hiện tại là gì?"),
    ("buoc_tiep",   "theo trạng thái hiện tại thì bước phát triển tiếp theo hợp lý là gì?"),
)

#: Câu HIỆN TẠI — phải đi ĐO SỐNG, không trả từ ký ức.
CAU_SONG = "production farmer hiện đang chạy không?"

#: Dấu hiệu câu trả lời CÓ CĂN CỨ: nêu mã bản ghi / đường dẫn tài liệu, HOẶC
#: nói thẳng là chưa có trong hồ sơ. Cả hai đều TRUNG THỰC; bịa thì không.
_CAN_CU = ("qd_", "ku_", "sk#", "dd_", "doc:", ".md", "viên nang", "vien nang")
_THANH_THAT = ("chưa có", "không có", "unknown", "chưa được ghi", "không tìm thấy",
               "chưa rõ", "chưa ghi nhận", "không đủ bằng chứng", "chưa xác minh")


def bam_kho(goc: Path) -> Dict[str, str]:
    """Băm mọi tệp theo dõi được + git status — để chứng minh KHÔNG sửa kho."""
    ra: Dict[str, str] = {}
    p = subprocess.run(["git", "-C", str(goc), "ls-files"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    for rel in (p.stdout or "").splitlines():
        rel = rel.strip()
        if not rel:
            continue
        f = goc / rel
        try:
            ra[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
        except OSError:
            ra[rel] = "(không đọc được)"
    st = subprocess.run(["git", "-C", str(goc), "status", "--porcelain"],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace")
    ra["__status__"] = st.stdout or ""
    hd = subprocess.run(["git", "-C", str(goc), "rev-parse", "HEAD"],
                        capture_output=True, text=True)
    ra["__head__"] = (hd.stdout or "").strip()
    return ra


def anh_chup_router(goc: Path) -> Dict[str, float]:
    """Ảnh chụp cây `.router` của kho đích (tên + mtime + cỡ).

    `.router` bị gitignore nên `git status` KHÔNG thấy nó — mà đúng chỗ đó là
    nơi một lần "nhận" cẩu thả sẽ để lại sổ mới. Ở kho Fanfic thư mục này ĐÃ
    CÓ TRƯỚC (di sản thời gốc dữ liệu suy từ `cwd`, trước v0.6.1), nên phép
    kiểm đúng là "KHÔNG ĐỔI", không phải "không tồn tại".
    """
    r = goc / ".router"
    ra: Dict[str, float] = {}
    if not r.exists():
        return ra
    try:
        for f in r.rglob("*"):
            try:
                st = f.stat()
                ra[str(f.relative_to(r))] = (round(st.st_mtime, 3)
                                             if f.is_file() else -1.0)
            except OSError:
                pass
    except OSError:
        pass
    return ra


def _so_viec(app: App, pid: str) -> int:
    return len(app.tasks(pid))


def _probe_moi(app: App, pid: str, tu: float) -> int:
    n = 0
    for e in app.events(pid, limit=400):
        if float(e.get("ts") or 0) < tu - 1:
            continue
        if (e.get("kind") or "") in ("LIVE_PROBE", "LIVE_PROBE_FAILED"):
            n += 1
    return n


def pha_nhan(app: App, bd: Bang) -> str:
    ghi("\n--- PHẦN A/B: NHẬN DỰ ÁN HIỆN CÓ (chỉ đọc) ---")
    kho = Path(KHO_FANFIC)
    truoc = bam_kho(kho)
    rt_truoc = anh_chup_router(kho)
    r = app.call("GET", "/api/project/adopt/preview?duong="
                 + __import__("urllib.parse", fromlist=["quote"]).quote(str(kho)))
    k = r.get("kho") or {}
    bd.ghi("A1. dò được kho Fanfic (git, nhánh, HEAD, remote đã lọc)",
           bool(k.get("la_git")) and bool(k.get("head")),
           f"nhánh={k.get('nhanh')} · {k.get('so_commit')} commit · "
           f"remote={k.get('remote_url') or '—'}")
    bd.ghi("A2. Router ĐÃ có dự án trỏ vào kho này (chống trùng)",
           bool(r.get("da_co")), f"da_co={r.get('da_co') or '(không)'}")
    n_du_an_truoc = len((app.state().get("projects") or []))
    kq = app.call("POST", "/api/project/adopt", {"duong": str(kho)})
    bd.ghi("A3. NHẬN = LIÊN KẾT LẠI, không tạo Fanfic-2",
           bool(kq.get("ok")) and bool(kq.get("lien_ket_lai"))
           and not kq.get("moi"),
           f"project_id={kq.get('project_id')} · lien_ket_lai={kq.get('lien_ket_lai')}"
           f" · moi={kq.get('moi')}")
    n_sau = len((app.state().get("projects") or []))
    bd.ghi("A4. số dự án KHÔNG tăng", n_sau == n_du_an_truoc,
           f"{n_du_an_truoc} -> {n_sau}")
    ng = kq.get("nguon") or {}
    tl, ky, sr = ng.get("tai_lieu") or {}, ng.get("ky_uc") or {}, ng.get("so_router") or {}
    bd.ghi("A5. dò được NGUỒN HIỂU BIẾT (tài liệu/ký ức/sổ Router/phiên Claude)",
           int(tl.get("so_doc") or 0) > 0 and int(ky.get("su_kien") or 0) > 0,
           f"docs={tl.get('so_doc')} reports={tl.get('so_bao_cao')} "
           f"handoff={tl.get('handoff')} · L0={ky.get('su_kien')} ky_uc={ky.get('ky_uc')} "
           f"· viec={sr.get('viec')} · slug Claude={(ng.get('phien_claude') or {}).get('so_slug')}")
    # KHONG SUA KHO.
    sau = bam_kho(kho)
    khac = [k2 for k2 in set(truoc) | set(sau) if truoc.get(k2) != sau.get(k2)]
    bd.ghi("A6. KHO FANFIC KHÔNG BỊ SỬA MỘT BYTE NÀO (băm mọi tệp + git status)",
           not khac, f"khác={khac[:5]}" if khac else "0 tệp đổi, HEAD/status giữ nguyên")
    rt_sau = anh_chup_router(kho)
    rt_khac = (sorted(set(rt_truoc) ^ set(rt_sau))
               + [k2 for k2 in (set(rt_truoc) & set(rt_sau))
                  if rt_truoc[k2] != rt_sau[k2]])
    bd.ghi("A7. cây .router của kho Fanfic KHÔNG BỊ TẠO/ĐỔI bởi lần nhận "
           "(nó là di sản trước v0.6.1, không phải sổ mới)",
           not rt_khac,
           (f"đổi={rt_khac[:5]}" if rt_khac
            else f"{len(rt_sau)} mục, không mục nào đổi"
                 + (" · (thư mục không tồn tại)" if not rt_sau else "")))
    bd.ghi("A8. KHÔNG có quyển ký ức nào bị tạo trong kho Fanfic "
           "(sổ Fanfic chỉ ở gốc chính tắc)",
           not (kho / ".router" / "memory").exists(),
           str(kho / ".router" / "memory"))
    return str(kq.get("project_id") or DU_AN)


def pha_nang(app: App, pid: str, bd: Bang) -> Dict:
    ghi("\n--- PHẦN C/D/E/F: VIÊN NANG + KIỂM LIÊN TỤC ---")
    r = app.call("POST", "/api/capsule/rebuild",
                 {"project": pid, "ly_do": "nghiệm thu v0.7 phase 1"}, timeout=600)
    vn = app.call("GET", f"/api/capsule?project={pid}")
    bd.ghi("C1. Viên nang tồn tại và CÓ PHIÊN BẢN", int(vn.get("phien_ban") or 0) >= 1,
           f"v{vn.get('phien_ban')} · dựng lại lần này: luu={r.get('luu')} "
           f"đổi={len(r.get('doi') or [])}")
    bd.ghi("C2. đa số mục có nội dung, phần thiếu là UNKNOWN (không bịa)",
           int(vn.get("so_muc_co") or 0) >= 12
           and int(vn.get("so_muc_co") or 0) + int(vn.get("so_khong_ro") or 0)
           + int(vn.get("so_cu") or 0) == int(vn.get("so_muc") or 0),
           f"có={vn.get('so_muc_co')} unknown={vn.get('so_khong_ro')} "
           f"cũ={vn.get('so_cu')} / {vn.get('so_muc')}")
    muc = vn.get("muc") or {}
    co = [k for k, m in muc.items() if m.get("trang_thai") in ("co", "cu")]
    co_bc = [k for k in co if m_bc(muc, k)]
    bd.ghi("C3. mọi mục CÓ nội dung đều mang BẰNG CHỨNG lần về được",
           len(co_bc) == len(co), f"{len(co_bc)}/{len(co)} mục có bằng chứng")
    bd.ghi("C4. giá trị SỐNG không bị đóng băng: mục 'Tham chiếu trạng thái SỐNG' "
           "chỉ nói ĐO BẰNG GÌ", _khong_dong_bang(muc),
           str((muc.get("tham_chieu_song") or {}).get("gia_tri"))[:140])
    bd.ghi("C5. Viên nang BOUNDED cho Leader (bản gọn nhỏ hơn hẳn bản đầy)",
           0 < int(vn.get("token_gon") or 0) <= 1100
           and int(vn.get("token_gon") or 0) < int(vn.get("token_day") or 0),
           f"gọn={vn.get('token_gon')} đầy={vn.get('token_day')} token")
    pbs = app.call("GET", f"/api/capsule/versions?project={pid}&limit=10")
    bd.ghi("E1. lịch sử phiên bản giữ được (không ghi đè)",
           len(pbs.get("ket_qua") or []) >= 2,
           f"{len(pbs.get('ket_qua') or [])} phiên bản trong sổ")
    lt = app.call("GET", f"/api/continuity?project={pid}")
    ghi("")
    from scripts.control_center import kiem_lien_tuc as KL
    for dong in KL.bang_chu(lt).splitlines():
        ghi("    " + dong)
    ghi("")
    bd.ghi("F1. Kiểm liên tục cho kết quả TRUNG THỰC (mọi hạng mục có lý do)",
           all(h.get("ly_do") for h in (lt.get("hang") or []))
           and lt.get("san_sang") in ("YES", "PARTIAL", "NO"),
           f"đạt={lt.get('dat')} một phần={lt.get('mot_phan')} hỏng={lt.get('hong')}"
           f" · phủ={lt.get('phu_bang_chung_phan_tram')}% · READY={lt.get('san_sang')}")
    return {"vn": vn, "lt": lt}


def m_bc(muc: Dict, k: str) -> bool:
    return bool((muc.get(k) or {}).get("bang_chung"))


def _khong_dong_bang(muc: Dict) -> bool:
    """Mục tham chiếu sống KHÔNG được chứa phán quyết trạng thái."""
    v = str((muc.get("tham_chieu_song") or {}).get("gia_tri") or "").lower()
    xau = ("active", "đang chạy", "dang chay", "healthy", "down", "đã dừng")
    return not any(x in v for x in xau)


def pha_hoi(app: App, pid: str, bd: Bang) -> Dict:
    ghi("\n--- PHẦN G: 12 CÂU HỎI THẬT (lịch sử/bối cảnh -> 0 DISPATCH) ---")
    tong_dispatch = 0
    chi_tiet: List[Dict] = []
    for ma, cau in CAU_HOI:
        n0 = _so_viec(app, pid)
        t0 = time.time()
        try:
            r = app.chat(pid, cau, timeout=420)
            tl = str(r.get("reply") or "")
        except Exception as exc:                            # noqa: BLE001
            tl = f"(lỗi: {type(exc).__name__})"
        them = _so_viec(app, pid) - n0
        tong_dispatch += max(0, them)
        low = tl.lower()
        can_cu = any(x in low for x in _CAN_CU)
        that = any(x in low for x in _THANH_THAT)
        ok = (them == 0) and (can_cu or that) and len(tl) > 40
        bd.ghi(f"G[{ma}] 0 dispatch + trả lời có căn cứ hoặc nói thẳng chưa có",
               ok, f"việc mới={them} · căn cứ={can_cu} · thành thật={that} · "
                   f"{time.time()-t0:.0f}s · {' '.join(tl.split())[:150]}")
        chi_tiet.append({"ma": ma, "cau": cau, "viec_moi": them,
                         "can_cu": can_cu, "thanh_that": that,
                         "tra_loi": " ".join(tl.split())[:400]})
    bd.ghi("G-TỔNG. 12 câu hỏi lịch sử -> TỔNG dispatch = 0", tong_dispatch == 0,
           f"tổng việc mới={tong_dispatch}")

    ghi("\n--- PHẦN D: câu hỏi HIỆN TẠI vẫn phải ĐO SỐNG ---")
    n0 = _so_viec(app, pid)
    t0 = time.time()
    r = app.chat(pid, CAU_SONG, timeout=420)
    tl = str(r.get("reply") or "")
    pr = _probe_moi(app, pid, t0)
    bd.ghi("D1. câu hỏi hiện tại -> có phép ĐO SỐNG (live > ký ức)", pr >= 1,
           f"probe mới={pr} · việc mới={_so_viec(app, pid) - n0} · "
           f"{' '.join(tl.split())[:160]}")
    return {"dispatch": tong_dispatch, "chi_tiet": chi_tiet, "song": pr}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mo-lai", action="store_true")
    ap.add_argument("--chi", default="", choices=("", "nhan", "nang", "hoi"))
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                   # noqa: BLE001
            pass
    g = goc_du_lieu()
    bd = Bang()
    ghi("=" * 78)
    ghi("NGHIỆM THU V0.7 PHASE 1 — NHẬN FANFIC + VIÊN NANG + LIÊN TỤC")
    ghi(f"  gốc dữ liệu : {g}")
    ghi(f"  kho Fanfic  : {KHO_FANFIC}")
    ghi("=" * 78)

    if a.mo_lai:
        lk = doc_lock(g)
        if lk and lk.get("pid") and _con_song(int(lk["pid"])):
            bd.ghi("0. đóng app đang chạy", dong_nhe(int(lk["pid"])), f"pid {lk['pid']}")
            time.sleep(2)
        app = mo_source_mode(GOC, goc_kho=g)
        bd.ghi("0b. mở SOURCE-MODE (router-cc-desktop.cmd path) + backend sẵn sàng",
               app.song(), f"pid {app.pid} cổng {app.port}")
    else:
        app = App(g)
        bd.ghi("0. dùng app source-mode đang chạy", app.song(),
               f"pid {app.pid} cổng {app.port}")

    pid = DU_AN
    if a.chi in ("", "nhan"):
        pid = pha_nhan(app, bd)
    if a.chi in ("", "nang"):
        pha_nang(app, pid, bd)
    if a.chi in ("", "hoi"):
        pha_hoi(app, pid, bd)

    # PRODUCTION MUTATION = 0 (kho Fanfic khong co tep tracked nao doi).
    st = subprocess.run(["git", "-C", KHO_FANFIC, "status", "--porcelain"],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace")
    doi = [x for x in (st.stdout or "").splitlines() if x and not x.startswith("??")]
    bd.ghi("Z. SỐ LẦN SỬA PRODUCTION = 0 (không tệp tracked nào đổi)",
           not doi, f"đổi={doi[:4]}" if doi else "kho Fanfic sạch")

    ghi("=" * 78)
    hong = bd.hong()
    ghi(f"KẾT LUẬN: {len(bd.hang) - len(hong)}/{len(bd.hang)} bước ĐẠT")
    for h in hong:
        ghi(f"  HỎNG: {h}")
    ghi("=" * 78)
    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())
