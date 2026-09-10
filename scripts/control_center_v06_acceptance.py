"""Nghiệm thu V0.6 trên BẢN EXE ĐÓNG GÓI — 14 tình huống của mục 20.

Chạy trên CHÍNH cửa sổ WebView2 của bản đã đóng gói, mở qua `ShellExecuteW`
(đúng API Explorer gọi), giám sát cửa sổ console suốt phiên. Dùng lại hạ
tầng V0.4/V0.5.

    python scripts/control_center_v06_acceptance.py \
        --exe "dist-v06/Router Control Center/Router Control Center.exe"

HAI PHIÊN, MỘT GỐC. Phiên A: mở, chat, ghi một quyết định QUA API (không
qua chat — để nó CHỈ nằm trong ký ức, không nằm trong 14 lượt hội thoại
gần đây mà Leader vẫn được đưa), giao một việc an toàn, tắt. Phiên B: một
tiến trình MỚI, một phiên Leader MỚI — hỏi về quyết định đó mà KHÔNG dán
gì; rồi hỏi một câu HIỆN TẠI về Fanfic để chứng minh khối sống vẫn thắng
khối ký ức.

Việc an toàn ở bước 3 là một tệp ghi chú trong kho git TẠM của bài nghiệm
thu — không chạm kho thật, không chạm production.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.ghi_utf8 import BoDocUTF8, GhiUTF8  # noqa: E402
from scripts.control_center_desktop_acceptance import (  # noqa: E402
    CDP, Bang, _dem_so, _mo_qua_explorer, _ta_vi_pham, kho_git_tam)
from scripts.control_center_v05_acceptance import _gieo  # noqa: E402
from scripts.giam_sat_cua_so import (GiamSatCuaSo,  # noqa: E402
                                     vi_pham_cua_app)

ghi = GhiUTF8()
NL = chr(10)
Q = chr(39)

#: Quyet dinh CHI nam trong ky uc (ghi qua API, khong qua chat).
QUYET_DINH = ("Giữ kho lưu trữ legacy ở chế độ CHỈ ĐỌC; mọi ghi vào legacy "
              "phải đi qua một job có kiểm.")
LY_DO = ("Sự cố khoá SSH sai tên: tệp cấu hình trỏ vào tên khoá cũ, đã sửa "
         "bằng khoá canonical fanficappwrite.pem. Ghi vào legacy khi khoá "
         "lệch là cách dữ liệu lịch sử bị hỏng.")
CAU_NHO = "vì sao ta giữ kho lưu trữ legacy ở chế độ chỉ đọc? có sự cố gì với khoá SSH?"
CAU_SONG = "production farmer đang chạy không?"
CAU_VIEC = ("Tạo tệp docs/ghi_chu_nghiem_thu_v06.md trong kho này với đúng một "
            "dòng: 'nghiệm thu v0.6 — ký ức dự án'. Không làm gì khác.")


def _api(cdp: CDP, duong: str, method: str = "GET", than: dict | None = None):
    js = ("const t=sessionStorage.getItem('cc_token');"
          + NL + f"const r=await fetch({json.dumps(duong)}, {{method:{json.dumps(method)},"
          + NL + "  headers:{'X-CC-Token':t,'Content-Type':'application/json'}"
          + (NL + f"  ,body:{json.dumps(json.dumps(than, ensure_ascii=False))}"
             if than is not None else "")
          + "});"
          + NL + "return JSON.stringify(await r.json());")
    return json.loads(cdp.js(js) or "{}")


def _su_kien(cdp: CDP, pid: str, kind: str) -> list:
    d = _api(cdp, f"/api/state?project={pid}")
    return [e for e in (d.get("events") or []) if e.get("kind") == kind]


def _chon_du_an(cdp: CDP, pid: str) -> bool:
    return bool(cdp.cho(
        "const li=document.querySelector("
        + NL + f"  {Q}#ds-project li[data-pid=\"{pid}\"]{Q});"
        + NL + "if (li) li.click();"
        + NL + "const m=document.querySelector("
        + NL + f"  {Q}#ds-project li.dang-mo{Q});"
        + NL + f"return !!(m && m.dataset.pid === '{pid}');", han=40))


def _gui_chat(cdp: CDP, cau: str, han: int = 300) -> str:
    cdp.js("const o=document.querySelector('#o-soan'); o.focus();"
           + NL + f"o.value={json.dumps(cau, ensure_ascii=False)};"
           + NL + "return 1;")
    cdp.phim("Enter", 13)
    cdp.cho("return !document.querySelector('#nut-gui').disabled", han=han)
    tin = cdp.js(
        "return JSON.stringify([...document.querySelectorAll("
        + NL + f"  {Q}#ds-tin .tin{Q})].slice(-1).map("
        + NL + "  e => (e.textContent||'').slice(0,1500)));")
    ds = json.loads(tin or "[]")
    return ds[-1] if ds else ""


def _mo(p_exe: Path, goc: Path, cong: int, gs: GiamSatCuaSo):
    ph = _mo_qua_explorer(p_exe, goc, cong)
    gs.theo(ph.pid)
    cdp = CDP(cong)
    cdp.cho("return !!document.querySelector('#o-soan')", han=60)
    cdp.dua_len_truoc()
    return ph, cdp


def _tat(ph) -> None:
    ph.terminate()
    try:
        ph.wait(timeout=40)
    except subprocess.TimeoutExpired:
        ph.kill()
    time.sleep(2)


def _so_ky_uc(goc: Path) -> dict:
    """Đọc thẳng sổ ký ức trên đĩa: đếm + quick_check. Không qua app."""
    ra = {}
    kho = goc / ".router" / "memory"
    for d in sorted(kho.glob("*/memory.db")) if kho.is_dir() else []:
        c = sqlite3.connect(str(d))
        try:
            ra[d.parent.name] = {
                "su_kien": c.execute("SELECT count(*) FROM su_kien").fetchone()[0],
                "ky_uc": c.execute("SELECT count(*) FROM ky_uc").fetchone()[0],
                "quyet_dinh": c.execute("SELECT count(*) FROM quyet_dinh").fetchone()[0],
                "diem_dung": c.execute("SELECT count(*) FROM diem_dung").fetchone()[0],
                "quick_check": c.execute("PRAGMA quick_check").fetchone()[0],
            }
        finally:
            c.close()
    return ra


def main(argv=None) -> int:
    # `BoDocUTF8`, khong phai `ArgumentParser`: chuoi `help=` la tieng Viet
    # va argparse ghi thang ra tang VAN BAN cua console cp1252 — dung loai
    # loi UnicodeEncodeError da lam EXE chet o V0.4 (docs/CONTROL_CENTER.md
    # muc 14).
    ap = BoDocUTF8(prog="control_center_v06_acceptance.py", ghi=ghi)
    ap.add_argument("--exe", required=True)
    ap.add_argument("--cdp", type=int, default=9711)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--bo-viec", action="store_true",
                    help="bỏ bước giao việc thật (nhanh, không tốn lượt agent)")
    a = ap.parse_args(argv)

    bd = Bang()
    goc = kho_git_tam()
    _gieo(goc)
    p_exe = Path(a.exe)
    if not p_exe.is_absolute():
        p_exe = (GOC / a.exe).resolve()

    ghi("=" * 78)
    ghi("NGHIỆM THU V0.6 — KÝ ỨC DỰ ÁN, trên BẢN EXE ĐÓNG GÓI")
    ghi(f"  exe : {p_exe}")
    ghi(f"  gốc : {goc}")
    ghi("=" * 78)

    gs = GiamSatCuaSo(); gs.__enter__()
    ph = None
    try:
        # ================= PHIEN A =====================================
        gs.dat_pha("A: mở app, dự án Router")
        ph, cdp = _mo(p_exe, goc, a.cdp, gs)
        bd.ghi("1. mở EXE và chọn được dự án Router", _chon_du_an(cdp, "router"),
               f"pid {ph.pid}")
        tk0 = _api(cdp, "/api/memory/stats?project=router")
        bd.ghi("1b. ký ức SẴN ngay khi mở (FTS5)", bool(tk0.get("san_sang"))
               and "FTS5" in str(tk0.get("che_do_tim")),
               f"chế độ tìm={tk0.get('che_do_tim')} · ns={tk0.get('ns')}")

        # -- 2. chat vai tin ------------------------------------------------
        gs.dat_pha("A: chat")
        tl1 = _gui_chat(cdp, "Chào Leader, hôm nay ta làm việc trên Control Center.")
        tl2 = _gui_chat(cdp, "Ghi nhớ giúp: pipeline TTS dùng registry provider, "
                             "không đổi giọng khi tổng hợp thất bại.")
        bd.ghi("2. chat vài tin và có trả lời", bool(tl1) and bool(tl2),
               (tl2 or "")[:120])
        # Quyet dinh ghi QUA API — chi nam trong ky uc, khong nam trong chat.
        qd = _api(cdp, "/api/memory/decision", "POST",
                  {"project": "router", "noi_dung": QUYET_DINH, "ly_do": LY_DO,
                   "tieu_de": "legacy chỉ đọc"})
        bd.ghi("2b. ghi được một QUYẾT ĐỊNH có lý do (qua API, không qua chat)",
               str(qd.get("ma", "")).startswith("qd_") and bool(qd.get("bang_chung")
                                                              or (qd.get("ky_uc") or {}).get("bang_chung")),
               f"{qd.get('ma')} · nguồn gốc L0: {bool((qd.get('ky_uc') or {}).get('bang_chung'))}")
        chat_a = _api(cdp, "/api/state?project=router").get("chat") or []
        bd.ghi("2c. quyết định KHÔNG có trong lịch sử chat (chỉ trong ký ức)",
               not any("legacy" in (m.get("text") or "").lower() for m in chat_a),
               f"{len(chat_a)} tin trong chat")

        # -- 3. mot viec an toan ------------------------------------------
        gs.dat_pha("A: giao việc an toàn")
        if a.bo_viec:
            bd.ghi("3. tạo/chạy một việc an toàn", True, "(bỏ qua theo --bo-viec)")
        else:
            n_tc0 = len(_su_kien(cdp, "router", "TASK_CREATED"))
            _gui_chat(cdp, CAU_VIEC, han=420)
            tao = len(_su_kien(cdp, "router", "TASK_CREATED")) > n_tc0
            # Cho toi da 4 phut cho mot trang thai ket thuc; khong bat buoc.
            t0 = time.time(); trang_thai = ""
            while time.time() - t0 < 240:
                st = _api(cdp, "/api/state?project=router")
                ts = [t for t in (st.get("tasks") or []) if t.get("state")
                      in ("DONE", "FAILED", "REVIEW", "BLOCKED", "RUNNING")]
                if ts:
                    trang_thai = ts[0]["state"]
                    if trang_thai in ("DONE", "FAILED", "BLOCKED"):
                        break
                time.sleep(5)
            tk_a = _api(cdp, "/api/memory/stats?project=router")
            d_a = tk_a.get("dem") or {}
            bd.ghi("3. tạo/chạy một việc an toàn — và việc ĐI VÀO ký ức",
                   tao and d_a.get("ky_uc_episodic", 0) >= 1,
                   f"TASK_CREATED={tao} · trạng thái={trang_thai or '?'} · "
                   f"ký ức episodic={d_a.get('ky_uc_episodic')}")

        # Tab Memory hien so that.
        gs.dat_pha("A: tab Memory")
        cdp.js("document.querySelector('.tab[data-khung=\"kyuc\"]').click(); return 1;")
        chu = cdp.cho("const t=(document.querySelector('#kyuc-thongke').textContent||'');"
                      + NL + "return t.includes('Sự kiện') && /\\d/.test(t) ? t : '';",
                      han=30)
        bd.ghi("A. tab Memory hiện thống kê thật", bool(chu),
               " ".join(str(chu or "").split())[:140])
        cdp.js("document.querySelector('#kyuc-tim').value='legacy';"
               + NL + "document.querySelector('#nut-kyuc-tim').click(); return 1;")
        kq_ui = cdp.cho("const t=(document.querySelector('#kyuc-ds').textContent||'');"
                        + NL + "return t.includes('legacy') ? t : '';", han=30)
        bd.ghi("A2. tìm 'legacy' trong tab Memory ra quyết định", bool(kq_ui),
               " ".join(str(kq_ui or "").split())[:120])
        cdp.js("document.querySelector('.tab[data-khung=\"chat\"]').click(); return 1;")

        so_a = _so_ky_uc(goc)
        truoc = _dem_so(goc)
        kq = gs.ket_qua
        bd.ghi("13. phiên A: không cửa sổ console nào DO APP nhấp lên",
               not vi_pham_cua_app(kq.vi_pham),
               kq.tom_tat() + (NL + "      " + _ta_vi_pham(kq.vi_pham)
                               if kq.vi_pham else ""))
        cdp.dong()

        # -- 4. tat app ------------------------------------------------------
        gs.dat_pha("A: tắt")
        _tat(ph); ph = None
        so_tat = _so_ky_uc(goc)
        r_a = so_a.get(next(iter(so_a), ""), {}) if so_a else {}
        r_t = so_tat.get(next(iter(so_tat), ""), {}) if so_tat else {}
        bd.ghi("4. tắt app -> có ĐIỂM DỪNG 'tắt ứng dụng' trên đĩa",
               any(v.get("diem_dung", 0) > r_a.get("diem_dung", 0)
                   for v in so_tat.values()) if so_tat else False,
               f"điểm dừng: {r_a.get('diem_dung')} -> {r_t.get('diem_dung')}")

        # ================= PHIEN B =====================================
        gs2 = GiamSatCuaSo(); gs2.__enter__()
        gs2.dat_pha("B: mở lại (phiên MỚI)")
        ph, cdp2 = _mo(p_exe, goc, a.cdp + 1, gs2)
        try:
            bd.ghi("5. mở lại được", _chon_du_an(cdp2, "router"), f"pid {ph.pid}")
            # -- 7. lich su / diem dung song sot ----------------------------
            tk_b = _api(cdp2, "/api/memory/stats?project=router")
            d_b = tk_b.get("dem") or {}
            bd.ghi("7. lịch sử thô SỐNG SÓT qua khởi động lại",
                   d_b.get("su_kien", 0) >= (list(so_tat.values())[0]["su_kien"]
                                             if so_tat else 1),
                   f"sự kiện={d_b.get('su_kien')} · ký ức={d_b.get('ky_uc')} · "
                   f"quyết định={d_b.get('quyet_dinh')} · điểm dừng={d_b.get('diem_dung')}")
            tt = _api(cdp2, "/api/memory/continue?project=router")
            bd.ghi("7b. điểm dừng + quyết định hiệu lực NẠP được cho phiên mới",
                   bool(tt.get("co_gi_de_tiep_tuc"))
                   and (tt.get("diem_dung") or {}).get("ly_do") == "tắt ứng dụng"
                   and len(tt.get("quyet_dinh_hieu_luc") or []) >= 1,
                   f"điểm dừng={(tt.get('diem_dung') or {}).get('ma')} "
                   f"({(tt.get('diem_dung') or {}).get('ly_do')}) · "
                   f"qđ hiệu lực={[q.get('ma') for q in tt.get('quyet_dinh_hieu_luc') or []]}")
            rs = _su_kien(cdp2, "router", "MEMORY_RESUMED")
            bd.ghi("8. phiên MỚI tự ghi MEMORY_RESUMED (hydrat, không ai dán gì)",
                   bool(rs), (rs[0].get("detail") if rs else "")[:140])
            # -- 6. tim trong Memory ------------------------------------------
            tim = _api(cdp2, "/api/memory/search?project=router&q=legacy%20SSH")
            bd.ghi("6. tìm 'legacy SSH' ra quyết định + bằng chứng gốc",
                   any("legacy" in (r.get("noi_dung") or "").lower()
                       for r in tim.get("ket_qua") or [])
                   and bool(tim.get("su_kien")),
                   f"{len(tim.get('ket_qua') or [])} ký ức · "
                   f"{len(tim.get('su_kien') or [])} sự kiện thô · "
                   f"{tim.get('che_do_tim')}")
            ma_qd = next((r.get("ma") for r in tim.get("ket_qua") or []
                          if r.get("loai") == "decision"), "")
            if ma_qd:
                bg = _api(cdp2, f"/api/memory/record?project=router&ma={ma_qd}")
                bd.ghi("6b. 'vì sao nhớ?' — lần về được sự kiện L0 gốc",
                       bool(bg.get("bang_chung")) and
                       all(b.get("co") for b in bg.get("bang_chung") or []),
                       f"{len(bg.get('bang_chung') or [])} mắt xích · "
                       f"quyết định={(bg.get('quyet_dinh') or {}).get('ma')} "
                       f"hiệu lực={(bg.get('quyet_dinh') or {}).get('hieu_luc')}")

            # -- 9/10. Leader MOI tra loi tu ky uc -----------------------------
            gs2.dat_pha("B: Leader mới hỏi ký ức")
            chat_b = _api(cdp2, "/api/state?project=router").get("chat") or []
            n_mc0 = len(_su_kien(cdp2, "router", "MEMORY_CONTEXT"))
            tl = _gui_chat(cdp2, CAU_NHO, han=360)
            n_mc1 = len(_su_kien(cdp2, "router", "MEMORY_CONTEXT"))
            tl_l = (tl or "").lower()
            trung = sum(1 for k in ("legacy", "chỉ đọc", "ssh", "canonical",
                                    "khoá", "qd_") if k in tl_l)
            bd.ghi("9/10. Leader phiên MỚI nhớ được quyết định (từ KÝ ỨC, không dán)",
                   n_mc1 > n_mc0 and trung >= 3
                   and not any("legacy" in (m.get("text") or "").lower()
                               for m in chat_b),
                   f"MEMORY_CONTEXT {n_mc0}->{n_mc1} · khớp {trung}/6 từ khoá · "
                   + (tl or "")[:200])

            # -- 11/12. cau HIEN TAI ve Fanfic: SONG thang KY UC --------------
            gs2.dat_pha("B: câu hiện tại (Fanfic)")
            bd.ghi("11a. chọn dự án Fanfic", _chon_du_an(cdp2, "fanfic"), "")
            n_lp0 = len(_su_kien(cdp2, "fanfic", "LIVE_PROBE"))
            n_mc2 = len(_su_kien(cdp2, "fanfic", "MEMORY_CONTEXT"))
            tl_s = _gui_chat(cdp2, CAU_SONG, han=360)
            n_lp1 = len(_su_kien(cdp2, "fanfic", "LIVE_PROBE"))
            n_mc3 = len(_su_kien(cdp2, "fanfic", "MEMORY_CONTEXT"))
            tls = (tl_s or "").lower()
            song = any(k in tls for k in ("live probe", "vừa đo", "active", "đang chạy",
                                          "chạy", "ssh"))
            bd.ghi("11. câu HIỆN TẠI -> Leader đo SỐNG (LIVE_PROBE tăng)",
                   n_lp1 > n_lp0, f"LIVE_PROBE {n_lp0}->{n_lp1} · " + (tl_s or "")[:160])
            bd.ghi("12. và trả lời từ phép đo, không từ ký ức",
                   song and "down" not in tls and "không chạy" not in tls,
                   f"khối ký ức có mặt: {n_mc3 > n_mc2} · trả lời: " + (tl_s or "")[:140])

            # -- 14. khong hong ---------------------------------------------
            sau = _dem_so(goc)
            dem = [k for k, v in truoc.items() if isinstance(v, int)]
            so_b = _so_ky_uc(goc)
            bd.ghi("14. không trạng thái cũ/hỏng: sổ chính + sổ ký ức lành",
                   sau["nguyen_ven"] == "ok"
                   and all(v["quick_check"] == "ok" for v in so_b.values())
                   and all(sau[k] >= truoc[k] for k in dem),
                   f"control.db={sau['nguyen_ven']} · ký ức="
                   + ",".join(f"{k[:8]}:{v['quick_check']}/{v['su_kien']}sk"
                              for k, v in so_b.items()))
            kq2 = gs2.ket_qua
            bd.ghi("13b. phiên B: không cửa sổ console nào DO APP nhấp lên",
                   not vi_pham_cua_app(kq2.vi_pham), kq2.tom_tat())
            cdp2.dong()
        finally:
            _tat(ph); ph = None
            gs2.dung()
    finally:
        gs.dung()
        if ph is not None and ph.poll() is None:
            _tat(ph)
        if a.keep:
            ghi(f"{NL}  (giữ lại {goc})")
        else:
            shutil.rmtree(goc, ignore_errors=True)

    ghi(NL + "=" * 78)
    hong = bd.hong()
    ghi(f"KẾT LUẬN: {len(bd.hang) - len(hong)}/{len(bd.hang)} bước ĐẠT")
    for b in hong:
        ghi(f"  HỎNG: {b}")
    ghi("=" * 78)
    return 1 if hong else 0


if __name__ == "__main__":
    raise SystemExit(main())
