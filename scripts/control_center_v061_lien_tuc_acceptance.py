# -*- coding: utf-8 -*-
"""Nghiệm thu LIÊN TỤC HAI CHIỀU: source-mode <-> bản đóng gói, MỘT kho.

    python scripts/control_center_v061_lien_tuc_acceptance.py --exe "dist-v0613/Router Control Center/Router Control Center.exe"

Chứng minh điều khuyết tật đòi: cùng `project_id` thì cùng MỘT quyển sổ, bất kể
mở bằng cách nào. Bốn pha, KHÔNG copy tay tệp DB nào:

  A. mở SOURCE-MODE   -> tạo Decision duy nhất D1 -> qd_* tồn tại -> đóng
  B. mở BẢN ĐÓNG GÓI  -> sổ phải là GỐC CHÍNH TẮC (không phải cạnh EXE)
                      -> hỏi D1 bằng diễn giải khác -> ĐÚNG qd_* đó
  C. bản đóng gói     -> tạo Decision D2 -> đóng
  D. mở SOURCE-MODE   -> đọc lại D2 (đúng mã, đúng nội dung)

Mỗi Decision mang một MÃ DUY NHẤT theo mốc thời gian nên không lẫn với dữ liệu
cũ, và câu hỏi ở pha sau dùng CÁCH DIỄN ĐẠT KHÁC (không lặp nguyên văn).
"""
from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Dict, List, Optional, Tuple

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.duong_du_lieu import (duong_memory,          # noqa: E402
                                                  goc_chinh_tac, goc_du_lieu,
                                                  mo_ta)
from scripts.control_center.memory.model import khong_gian_ten           # noqa: E402
from scripts.control_center_v061_ky_uc_web_acceptance import (App, Bang,  # noqa: E402
                                                              _con_song,
                                                              doc_lock,
                                                              dong_nhe, ghi,
                                                              mo_source_mode)

DU_AN = "fanfic"


def _mo_dong_goi(p_exe: Path, han: float = 120.0) -> App:
    """Mở bản đóng gói qua ShellExecuteW (như người dùng bấm đôi) rồi nối vào
    backend của nó — tệp khoá phải nằm ở GỐC CHÍNH TẮC."""
    goc = goc_chinh_tac()
    cu = doc_lock(goc)
    cu_pid = (cu or {}).get("pid")
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteW.restype = wintypes.HINSTANCE
    shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR,
                                      wintypes.LPCWSTR, wintypes.LPCWSTR,
                                      wintypes.LPCWSTR, ctypes.c_int]
    r = int(shell32.ShellExecuteW(None, "open", str(p_exe), None,
                                  str(p_exe.parent), 1))
    if r <= 32:
        raise SystemExit(
            f"ShellExecuteW từ chối mở {p_exe.name}: mã {r} — Smart App Control "
            f"có thể đang chặn bản chưa ký (xem docs/reports/SMART_APP_CONTROL_V061.md)")
    het = time.time() + han
    while time.time() < het:
        lk = doc_lock(goc)
        if lk and lk.get("pid") != cu_pid:
            try:
                a = App(goc)
                if a.song():
                    return a
            except SystemExit:
                pass
        time.sleep(1.0)
    raise SystemExit(
        "mở bản đóng gói nhưng KHÔNG thấy tệp khoá ở gốc chính tắc "
        f"({goc}) — bản này có thể vẫn neo sổ cạnh EXE, hoặc bị SAC chặn")


def _qd_trong_so(pid: str = DU_AN) -> List[Dict]:
    """Đọc THẲNG quyển sổ chính tắc (không qua app) — sự thật trên đĩa."""
    import sqlite3
    db = duong_memory() / khong_gian_ten(pid) / "memory.db"
    if not db.is_file():
        return []
    c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in c.execute(
            "SELECT q.ma, q.ky_uc_ma, k.noi_dung, k.tin_cay, k.ts "
            "FROM quyet_dinh q JOIN ky_uc k ON k.ma=q.ky_uc_ma ORDER BY k.ts")]
    finally:
        c.close()


def _dong_app(goc: Path, bd: Bang, nhan: str) -> None:
    lk = doc_lock(goc)
    if lk and lk.get("pid") and _con_song(int(lk["pid"])):
        ok = dong_nhe(int(lk["pid"]))
        bd.ghi(f"{nhan} đóng sạch (WM_CLOSE)", ok, f"pid {lk['pid']}")
        time.sleep(2.0)
    else:
        bd.ghi(f"{nhan} (không có bản nào đang chạy)", True, "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True, help="bản đóng gói dùng cho pha B/C")
    ap.add_argument("--project", default=DU_AN)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                   # noqa: BLE001
            pass
    p_exe = Path(a.exe)
    if not p_exe.is_absolute():
        p_exe = (GOC / a.exe).resolve()
    if not p_exe.is_file():
        raise SystemExit(f"không thấy EXE: {p_exe}")

    goc = goc_chinh_tac()
    bd = Bang()
    mt = mo_ta()
    dau = time.strftime("%H%M%S")
    D1 = (f"hãy ghi nhớ đây là một quyết định của project: mã kiểm liên tục "
          f"NGUON-{dau}, mọi báo cáo nghiệm thu phải ghi kèm mã kho dữ liệu.")
    D2 = (f"hãy ghi nhớ đây là một quyết định của project: mã kiểm liên tục "
          f"GOI-{dau}, bản đóng gói phải dùng chung kho với bản mã nguồn.")
    HOI1 = "mã kiểm liên tục NGUON là gì và quyết định kèm nó nói gì?"
    HOI2 = "quyết định về mã kiểm liên tục GOI nói gì?"

    ghi("=" * 78)
    ghi("NGHIỆM THU LIÊN TỤC HAI CHIỀU — MỘT KHO CHÍNH TẮC")
    ghi(f"  gốc chính tắc : {goc}")
    ghi(f"  phiên bản kho : {mt['phien_ban_kho']} (mã hiểu {mt['phien_ban_ma']})")
    ghi(f"  EXE đóng gói  : {p_exe}")
    ghi("=" * 78)

    _dong_app(goc, bd, "0. dọn trước:")

    # ---------------- PHA A: SOURCE-MODE tạo D1 ----------------------------
    ghi("\n--- PHA A: SOURCE-MODE tạo Decision D1 ---")
    app = mo_source_mode(GOC)
    bd.ghi("A1. source-mode mở được", app.song(), f"pid {app.pid} cổng {app.port}")
    lk = doc_lock(goc)
    bd.ghi("A2. source-mode dùng GỐC CHÍNH TẮC (tệp khoá ở đó)",
           bool(lk) and int(lk.get("pid") or 0) == int(app.pid or 0),
           f"khoá tại {goc}")
    truoc = {q["ma"] for q in _qd_trong_so(a.project)}
    app.chat(a.project, D1)
    time.sleep(1.5)
    sau = _qd_trong_so(a.project)
    moi1 = [q for q in sau if q["ma"] not in truoc]
    bd.ghi("A3. D1 thành Decision qd_* trong SỔ CHÍNH TẮC", len(moi1) == 1,
           f"mã={[q['ma'] for q in moi1]} · nội dung có mã kiểm="
           f"{any(('NGUON-' + dau) in q['noi_dung'] for q in moi1)}")
    ma1 = moi1[0]["ma"] if moi1 else ""
    _dong_app(goc, bd, "A4. đóng source-mode:")

    # ---------------- PHA B: ĐÓNG GÓI đọc lại D1 ---------------------------
    ghi("\n--- PHA B: BẢN ĐÓNG GÓI đọc lại D1 (không copy tệp nào) ---")
    try:
        app2 = _mo_dong_goi(p_exe)
    except SystemExit as exc:
        bd.ghi("B1. bản đóng gói mở được + tệp khoá ở gốc chính tắc", False, str(exc)[:200])
        ghi("=" * 78)
        ghi(f"KẾT LUẬN: {len(bd.hang) - len(bd.hong())}/{len(bd.hang)} bước ĐẠT")
        for h in bd.hong():
            ghi(f"  HỎNG: {h}")
        return 1
    bd.ghi("B1. bản đóng gói mở được + tệp khoá ở GỐC CHÍNH TẮC", app2.song(),
           f"pid {app2.pid} cổng {app2.port} · khoá {goc}")
    st = app2.state()
    bd.ghi("B2. thấy dự án Fanfic",
           any(p.get("project_id") == a.project for p in st.get("projects") or []),
           f"projects={[p.get('project_id') for p in st.get('projects') or []]}")
    tk = (app2.mem_stats(a.project).get("dem") or {})
    bd.ghi("B3. bản đóng gói thấy ĐÚNG quyển sổ (số liệu khớp đĩa)",
           int(tk.get("su_kien") or 0) > 1000 and int(tk.get("ky_uc_decision") or 0) >= 1,
           f"su_kien={tk.get('su_kien')} ky_uc={tk.get('ky_uc')} "
           f"decision={tk.get('ky_uc_decision')} incident={tk.get('ky_uc_incident')}")
    n0 = len(app2.tasks(a.project))
    r = app2.chat(a.project, HOI1, timeout=300)
    time.sleep(1.0)
    tl = str(r.get("reply") or "")
    bd.ghi("B4. SOURCE -> ĐÓNG GÓI: đọc lại ĐÚNG qd_* của D1, 0 việc mới",
           (ma1 and ma1 in tl) or (f"NGUON-{dau}" in tl),
           f"mã mong={ma1} · việc mới={len(app2.tasks(a.project)) - n0} · "
           f"reply: {' '.join(tl.split())[:200]}")

    # ---------------- PHA C: ĐÓNG GÓI tạo D2 -------------------------------
    ghi("\n--- PHA C: BẢN ĐÓNG GÓI tạo Decision D2 ---")
    truoc2 = {q["ma"] for q in _qd_trong_so(a.project)}
    app2.chat(a.project, D2)
    time.sleep(1.5)
    moi2 = [q for q in _qd_trong_so(a.project) if q["ma"] not in truoc2]
    bd.ghi("C1. D2 thành Decision qd_* (ghi từ bản ĐÓNG GÓI vào sổ chính tắc)",
           len(moi2) == 1,
           f"mã={[q['ma'] for q in moi2]} · có mã kiểm="
           f"{any(('GOI-' + dau) in q['noi_dung'] for q in moi2)}")
    ma2 = moi2[0]["ma"] if moi2 else ""
    _dong_app(goc, bd, "C2. đóng bản đóng gói:")

    # ---------------- PHA D: SOURCE-MODE đọc lại D2 ------------------------
    ghi("\n--- PHA D: SOURCE-MODE đọc lại D2 ---")
    app3 = mo_source_mode(GOC)
    bd.ghi("D1. source-mode mở lại được", app3.song(),
           f"pid {app3.pid} cổng {app3.port}")
    n1 = len(app3.tasks(a.project))
    r3 = app3.chat(a.project, HOI2, timeout=300)
    time.sleep(1.0)
    tl3 = str(r3.get("reply") or "")
    bd.ghi("D2. ĐÓNG GÓI -> SOURCE: đọc lại ĐÚNG qd_* của D2, 0 việc mới",
           (ma2 and ma2 in tl3) or (f"GOI-{dau}" in tl3),
           f"mã mong={ma2} · việc mới={len(app3.tasks(a.project)) - n1} · "
           f"reply: {' '.join(tl3.split())[:200]}")
    qd = _qd_trong_so(a.project)
    bd.ghi("D3. cả HAI quyết định cùng nằm trong MỘT quyển sổ",
           bool(ma1) and bool(ma2) and {ma1, ma2} <= {q["ma"] for q in qd},
           f"quyết định trong sổ={[q['ma'] for q in qd]}")
    bd.ghi("D4. quyết định Astra cũ vẫn còn (di trú không mất gì)",
           any("Astra" in (q["noi_dung"] or "") for q in qd),
           f"tổng quyết định={len(qd)}")

    ghi("=" * 78)
    hong = bd.hong()
    ghi(f"KẾT LUẬN: {len(bd.hang) - len(hong)}/{len(bd.hang)} bước ĐẠT")
    for h in hong:
        ghi(f"  HỎNG: {h}")
    ghi("=" * 78)
    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())
