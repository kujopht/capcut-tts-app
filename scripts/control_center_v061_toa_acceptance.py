"""Nghiệm thu TOẢ trên BẢN EXE ĐÓNG GÓI — "gọi N agent…" phải ra N việc con.

    python scripts/control_center_v061_toa_acceptance.py \
        --exe "dist-v061/Router Control Center/Router Control Center.exe" \
        --so 4 --max-parallel 3

Việc con là việc AN TOÀN, RẺ: mỗi agent chỉ trả lời một dòng "agent i sẵn
sàng" — không đọc tệp, không chạy lệnh — nhưng là `agy` THẬT trên tài khoản
Antigravity THẬT, vì điều cần chứng minh là ">1 tài khoản AG được chọn" và
"sức chứa/hàng đợi đúng". `--max-parallel 3` với 4 agent cố ý tạo ra một con
phải CHỜ: câu trả lời phải nói "3 chạy ngay, 1 chờ slot", và con thứ tư chỉ
chạy khi một khe rảnh ra.
"""
from __future__ import annotations

import json
import shutil
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
from scripts.control_center_v06_acceptance import (  # noqa: E402
    _api, _chon_du_an, _dong_nhe, _gui_chat, _so_ky_uc, _tat)
from scripts.giam_sat_cua_so import (GiamSatCuaSo,  # noqa: E402
                                     vi_pham_cua_app)

ghi = GhiUTF8()
NL = chr(10)


def _cau(so: int) -> str:
    return (f"gọi {so} agent gemini 3.8, mỗi đứa trả lời đúng một dòng "
            f"'agent i sẵn sàng' với i là số thứ tự của mình trong nhóm; không đọc "
            f"tệp nào, không chạy lệnh nào, không làm gì khác.")


#: Cau NGUYEN VAN cua nguoi dung o nghiem thu tay (kich ban `--kich-ban fanfic`).
CAU_FANFIC = "gọi 8 agent gemini 3.8 và phân mỗi đứa đi lục cho t 1 bộ fanfic audio"
#: Cau NGUYEN VAN cua khuyet tat #2 (kich ban `--kich-ban kiem-tra`): bon con
#: CHI DOC bon pham vi khac nhau — phai chay DONG THOI, khoa READ song chung.
CAU_KIEM_TRA = ("gọi 4 agent gemini 3.8, mỗi agent kiểm tra một phần khác nhau của repo này:\n"
                "1. README/docs\n2. tests\n3. source architecture\n4. git history\n"
                "không được trùng phạm vi nhau")
#: Kich ban GHI (`--kich-ban ghi`): hai con sua CUNG mot tep -> phai TUAN TU
#: (khoa WRITE doc quyen khong duoc noi). Tep nam trong kho tam; agent ghi
#: trong worktree co lap — goc kho tam khong doi.
CAU_GHI = ("gọi 2 agent gemini 3.8, mỗi agent thêm đúng một dòng ghi chú mới vào cuối tệp "
           "docs/ghi_chu_nghiem_thu.md (dòng có số thứ tự agent của mình), không sửa gì khác.")


def _gieo_fanfic_audio(goc: Path, so_bo: int = 12) -> None:
    """Gieo `so_bo` bộ fanfic audio TỔNG HỢP vào kho git tạm — việc của agent là
    ĐỌC kho và mỗi đứa chọn một bộ; dữ liệu giả, không tệp âm thanh thật, không
    kho thật. Commit để `git status` sạch và bước 'không sửa gì' đo được."""
    import subprocess
    d = goc / "fanfic_audio"
    d.mkdir(exist_ok=True)
    for i in range(1, so_bo + 1):
        b = d / f"bo_{i:02d}"
        b.mkdir(exist_ok=True)
        (b / "README.md").write_text(
            f"# Bộ fanfic audio {i:02d}\n\nTruyện: Fanfic số {i}. Giọng đọc: mẫu {i}.\n"
            f"Chương: {3 + i % 4}. Định dạng: mp3 (giả, không có tệp âm thanh trong kho).\n",
            encoding="utf-8")
    for c in (["git", "add", "-A"], ["git", "commit", "-q", "-m", "gieo fanfic audio gia"]):
        subprocess.run(c, cwd=goc, check=True, capture_output=True)


def _git_sach(goc: Path) -> str:
    """`git status --porcelain` của kho tạm, BỎ `.router/` — đó là sổ của chính
    Control Center (harness dùng kho tạm làm gốc app), không phải agent ghi."""
    import subprocess
    p = subprocess.run(["git", "status", "--porcelain"], cwd=goc, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    dong = [d for d in p.stdout.splitlines()
            if d.strip() and not d.split(None, 1)[-1].startswith(".router")]
    return "\n".join(dong).strip()


def _mo(p_exe: Path, goc: Path, cong: int, gs, them: str):
    ph = _mo_qua_explorer(p_exe, goc, cong, them)
    gs.theo(ph.pid)
    cdp = CDP(cong)
    cdp.cho("return !!document.querySelector('#o-soan')", han=60)
    # Bat loi JS chua bat cua trang, de mot bang rong co the noi vi sao.
    cdp.js("window.__loi=[];window.addEventListener('error',e=>window.__loi.push("
           "String(e.message)+' @'+String(e.filename).split('/').pop()+':'+e.lineno));return 1;")
    cdp.dua_len_truoc()
    return ph, cdp


def _state(cdp, pid: str) -> dict:
    return _api(cdp, f"/api/state?project={pid}")


def main(argv=None) -> int:
    ap = BoDocUTF8(prog="control_center_v061_toa_acceptance.py", ghi=ghi)
    ap.add_argument("--exe", required=True)
    ap.add_argument("--cdp", type=int, default=9731)
    ap.add_argument("--so", type=int, default=4, help="số agent xin")
    ap.add_argument("--max-parallel", type=int, default=3,
                    help="trần song song truyền cho EXE (nhỏ hơn --so để có con phải chờ)")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--kich-ban", default="dong", choices=("dong", "fanfic", "kiem-tra", "ghi"),
                    help=("`dong`: mỗi agent trả một dòng (mặc định); `fanfic`: câu "
                          "NGUYÊN VĂN 8 agent trên kho tạm có 12 bộ fanfic audio tổng hợp; "
                          "`kiem-tra`: câu NGUYÊN VĂN khuyết tật #2 — 4 con CHỈ ĐỌC 4 phạm "
                          "vi (phải song song); `ghi`: 2 con GHI cùng một tệp (phải tuần tự)"))
    a = ap.parse_args(argv)
    kich_ban = a.kich_ban
    so = {"fanfic": 8, "kiem-tra": 4, "ghi": 2}.get(kich_ban, int(a.so))
    mp = int(a.max_parallel)
    chay_ngay = min(so, mp)
    if kich_ban == "ghi":
        chay_ngay = min(chay_ngay, 1)          # GHI cung tep: bao lap lich chi cho 1 chay
    cau = {"fanfic": CAU_FANFIC, "kiem-tra": CAU_KIEM_TRA, "ghi": CAU_GHI}.get(kich_ban) or _cau(so)

    bd = Bang()
    goc = kho_git_tam()
    _gieo(goc)
    if kich_ban == "fanfic":
        _gieo_fanfic_audio(goc)
    if kich_ban == "ghi":
        import subprocess
        (goc / "docs" / "ghi_chu_nghiem_thu.md").write_text("# Ghi chú nghiệm thu\n",
                                                           encoding="utf-8")
        for c in (["git", "add", "-A"], ["git", "commit", "-q", "-m", "gieo tep ghi chu"]):
            subprocess.run(c, cwd=goc, check=True, capture_output=True)
    dau_git = _git_sach(goc)
    p_exe = Path(a.exe)
    if not p_exe.is_absolute():
        p_exe = (GOC / a.exe).resolve()

    ghi("=" * 78)
    ghi(f"NGHIỆM THU TOẢ — {so} agent, trần song song {mp}, kịch bản {kich_ban}, "
        f"trên BẢN EXE ĐÓNG GÓI")
    ghi(f"  exe : {p_exe}")
    ghi(f"  gốc : {goc}")
    ghi(f"  câu : {cau}")
    ghi("=" * 78)

    gs = GiamSatCuaSo(); gs.__enter__()
    ph = None
    try:
        gs.dat_pha("mở app")
        ph, cdp = _mo(p_exe, goc, a.cdp, gs, f"--max-parallel {mp}")
        bd.ghi("1. mở EXE (--max-parallel %d) và chọn dự án Router" % mp,
               _chon_du_an(cdp, "router"), f"pid {ph.pid}")

        # -- 2. cau "goi N agent" qua o chat ----------------------------------
        gs.dat_pha("chat: gọi N agent")
        t0 = time.time()
        tl = _gui_chat(cdp, cau, han=420)
        st = _state(cdp, "router")
        ts = st.get("tasks") or []
        cha = [t for t in ts if ((t.get("contract") or {}).get("_toa") or {}).get("cha")]
        con = [t for t in ts if t.get("parent_id") and cha and t["parent_id"] == cha[0]["task_id"]]
        toa_cha = ((cha[0].get("contract") or {}).get("_toa") or {}) if cha else {}
        bd.ghi(f"2. cardinality: {so} agent -> 1 việc cha + {so} việc con (không việc 'to')",
               len(cha) == 1 and len(con) == so and len(ts) == so + 1
               and toa_cha.get("so") == so
               and (toa_cha.get("yeu_cau") or {}).get("so_agent") == so
               and (toa_cha.get("suc_chua") or {}).get("yeu_cau") == so,
               f"cha={len(cha)} · con={len(con)} · tổng việc={len(ts)} · yêu cầu giữ nguyên="
               f"{(toa_cha.get('yeu_cau') or {}).get('so_agent')} · {time.time() - t0:.0f}s")
        chi_so = sorted(((t.get("contract") or {}).get("_toa") or {}).get("chi_so") for t in con)
        bd.ghi("2b. mỗi con một chỉ số i/N và ràng buộc KHÔNG TRÙNG",
               chi_so == list(range(1, so + 1))
               and all("KHÔNG TRÙNG" in (t.get("objective") or "") for t in con),
               f"chỉ số={chi_so}")
        # Cau tra loi phai noi DUNG so (do engine viet tu fabric). Doc tin
        # nhan tu API (tin `delegation` cuoi), khong doc o chat da cat 1500 ky
        # tu — loi Leader dai co the day dong cua engine ra ngoai lat cat.
        tin_dg = [m for m in (st.get("chat") or [])
                  if (m.get("meta") or {}).get("loai") == "delegation"]
        tll = (tin_dg[-1].get("text") if tin_dg else tl) or ""
        k_slot = min(so, mp)                    # suc chua theo KHE (khoa khong tinh o day)
        mong = (f"{k_slot}/{so} worker slots khả dụng" if k_slot < so
                else f"dispatch {so} worker song song")
        bd.ghi("2c. câu trả lời nói đúng số: tách N việc + K chạy ngay / N−K chờ",
               f"Đã tách thành {so} tác vụ" in tll and mong in tll
               and (k_slot >= so or f"{so - k_slot} chờ slot" in tll),
               " ".join(tll.split())[:420])
        # Tai nguyen + che do cua tung con — de loi khoa doc ra ngay tren bang.
        tn = {t["task_id"]: list(t.get("resources") or []) for t in con}
        moi_doc = all(all(str(r).upper().startswith("READ:") for r in v) and v for v in tn.values())
        moi_ghi = all(all(str(r).upper().startswith("WRITE:") for r in v) and v for v in tn.values())
        rieng = len({tuple(v) for v in tn.values()})
        if kich_ban == "kiem-tra":
            bd.ghi("2e. 4 con CHỈ ĐỌC: 4 tài nguyên READ riêng (docs/tests/gốc/git-history), không worktree",
                   moi_doc and rieng == 4
                   and all(not ((t.get("contract") or {}).get("execution") or {}).get("worktree_required")
                           for t in con),
                   " | ".join(f"[{((t.get('contract') or {}).get('_toa') or {}).get('chi_so')}] "
                              + ", ".join(tn[t['task_id']]) for t in con))
        elif kich_ban == "ghi":
            bd.ghi("2e. 2 con GHI cùng một tệp: cùng một khoá WRITE", moi_ghi and rieng == 1,
                   " | ".join(", ".join(v) for v in tn.values()))
        bd.ghi("2d. không dùng 'MAX' thay cho số agent", "MAX" not in tll.split("Đã tách")[0].upper()
               or f"{so} " in tll, "")

        # -- 3. dispatch nhieu tai khoan, dung suc chua ----------------------------
        gs.dat_pha("dispatch")
        def _dang():
            s = _state(cdp, "router")
            ts2 = [t for t in (s.get("tasks") or []) if t.get("parent_id")]
            return s, ts2
        nhieu_nhat = 0
        rts_thay = set()
        cho_thay = False
        cha_running_thay = False
        het = time.time() + 150
        while time.time() < het:
            s, ts2 = _dang()
            dang = [t for t in ts2 if t["state"] == "RUNNING"]
            cho = [t for t in ts2 if t["state"] in ("QUEUED", "WAITING")]
            if any(t["task_id"] == cha[0]["task_id"] and t["state"] == "RUNNING"
                   for t in (s.get("tasks") or [])):
                cha_running_thay = True
            ss = {x["session_id"]: x for x in (s.get("sessions") or [])}
            for t in dang:
                sx = ss.get(t.get("owner_session") or "")
                if sx and sx.get("runtime_id"):
                    rts_thay.add(sx["runtime_id"])
            nhieu_nhat = max(nhieu_nhat, len(dang))
            if len(dang) >= chay_ngay and cho and chay_ngay < so:
                cho_thay = True
            if len(dang) >= min(2, chay_ngay) and len(rts_thay) >= 2:
                break
            if all(t["state"] in ("DONE", "FAILED") for t in ts2):
                break
            time.sleep(1.0)
        if kich_ban == "ghi":
            # GHI cung tep -> tuan tu; con thu hai DUNG LAI phien ranh cua con
            # thu nhat (REUSE theo pham vi) la dung, khong phai loi — "nhieu
            # tai khoan" la thuoc do cua kich ban SONG SONG.
            bd.ghi("3. tài khoản AG THẬT được chọn (tuần tự → dùng lại 1 phiên là đúng)",
                   len(rts_thay) >= 1 and all(r.startswith("AG") for r in rts_thay),
                   f"runtime thấy={sorted(rts_thay)} · đang chạy nhiều nhất={nhieu_nhat}")
        else:
            bd.ghi("3. >1 tài khoản AG THẬT được chọn cho các con",
                   len(rts_thay) >= 2 and all(r.startswith("AG") for r in rts_thay),
                   f"runtime thấy={sorted(rts_thay)} · đang chạy nhiều nhất={nhieu_nhat}")
        bd.ghi(f"3b. đúng sức chứa: không bao giờ quá {chay_ngay} con chạy cùng lúc",
               nhieu_nhat <= chay_ngay, f"nhiều nhất={nhieu_nhat}")
        if chay_ngay < so:
            bd.ghi(f"3c. hàng đợi: có lúc {chay_ngay} chạy + {so - chay_ngay} chờ",
                   cho_thay, "")
        bd.ghi("3d. cha RUNNING trong khi con chạy", cha_running_thay, "")
        su_kien = _state(cdp, "router").get("events") or []
        tranh = [e for e in su_kien if "tranh chấp" in (e.get("detail") or "")
                 and (e.get("task_id") or "") in tn]
        if kich_ban == "kiem-tra":
            bd.ghi("3e. không con nào bị khoá READ chặn (0 sự kiện tranh chấp)", not tranh,
                   f"tranh chấp={len(tranh)}" + (f" · {tranh[0].get('detail', '')[:160]}" if tranh else ""))
            bd.ghi(f"3f. {so} con giao nhau THỰC (đang chạy cùng lúc ≥ {min(so, chay_ngay)})",
                   nhieu_nhat >= min(so, chay_ngay), f"nhiều nhất cùng lúc={nhieu_nhat}")
        elif kich_ban == "ghi":
            bd.ghi("3e. khoá WRITE ĐỘC QUYỀN: con thứ hai chờ với sự kiện tranh chấp WRITE",
                   bool(tranh) and any("WRITE" in (e.get("detail") or "") for e in tranh) and nhieu_nhat <= 1,
                   f"tranh chấp={len(tranh)} · nhiều nhất cùng lúc={nhieu_nhat}")

        # -- 4. UI: bang viec co cha + con thut vao; Agents co tung worker -----------
        gs.dat_pha("UI")
        cdp.js("document.querySelector('.tab[data-khung=\"tasks\"]').click(); return 1;")
        co_bang = cdp.cho("const r=[...document.querySelectorAll('#bang-tasks tbody tr')];"
                          + NL + "return r.some(x=>x.classList.contains('viec-cha')) && "
                          + f"r.filter(x=>x.classList.contains('viec-con')).length>={so};", han=30)
        chu = cdp.js("const r=[...document.querySelectorAll('#bang-tasks tbody tr')];"
                     + NL + "return r.map(x=>x.children[0].textContent.trim().slice(0,60)).join(' | ');") or ""
        bd.ghi(f"4. UI Tasks: 1 dòng cha (đếm con) + {so} dòng con thụt vào", bool(co_bang),
               " ".join(str(chu).split())[:260])
        cdp.js("document.querySelector('.tab[data-khung=\"agents\"]').click(); return 1;")
        # Bang Agents ve theo nhip WebSocket (1 s) — cho toi khi co >= 2 dong AG
        # (kich ban GHI tuan tu: con 2 dung lai phien con 1 -> 1 dong la dung).
        toi_thieu = 1 if kich_ban == "ghi" else 2
        cdp.cho("return [...document.querySelectorAll('#bang-agents tbody tr')]"
                + f".filter(r=>/AG\\d\\d/.test(r.children[0].textContent)).length>={toi_thieu};", han=20)
        ag = cdp.js("return [...document.querySelectorAll('#bang-agents tbody tr')]"
                    + ".map(r=>r.children[0].textContent.trim()).join(' | ');") or ""
        ss_api = [(x.get("runtime_id"), x.get("state")) for x in
                  (_state(cdp, "router").get("sessions") or [])]
        loi_js = cdp.js("return JSON.stringify(window.__loi||[]);") or "[]"
        bd.ghi("4b. UI Agents: từng worker (runtime) hiện riêng",
               sum(1 for r in sorted(rts_thay) if r in str(ag)) >= toi_thieu,
               f"bảng={str(ag)[:160] or '(rỗng)'} · API sessions={ss_api} · lỗi JS={loi_js[:200]}")
        cdp.js("document.querySelector('.tab[data-khung=\"chat\"]').click(); return 1;")

        # -- 5. cho tat ca con xong -> cha tong hop ---------------------------------------
        gs.dat_pha("chờ xong")
        het = time.time() + (600 if so > 4 else 480)
        cha_x = None
        while time.time() < het:
            s = _state(cdp, "router")
            cha_x = next((t for t in (s.get("tasks") or []) if t["task_id"] == cha[0]["task_id"]), None)
            if cha_x and cha_x["state"] in ("DONE", "FAILED"):
                break
            time.sleep(3.0)
        th = ((cha_x or {}).get("result") or {}).get("toa") or {}
        bd.ghi(f"5. mọi con kết thúc -> cha DONE với tổng hợp {so} con",
               bool(cha_x) and cha_x["state"] == "DONE" and th.get("so_con") == so
               and th.get("xong", 0) >= 1,
               f"cha={(cha_x or {}).get('state')} · xong={th.get('xong')}/{th.get('so_con')} · "
               f"hỏng={th.get('hong')} · ứng viên={len(th.get('ung_vien') or [])} · "
               f"khử trùng={th.get('trung_da_bo')} · song song thực đo={th.get('song_song_toi_da')}")
        if kich_ban == "kiem-tra":
            bd.ghi(f"5d. không con nào hỏng bất thường: {so}/{so} xong", th.get("xong") == so,
                   " | ".join(f"[{c.get('chi_so')}] {c.get('state')} {c.get('failure_reason') or ''}"
                              for c in (th.get("con") or [])))
            bd.ghi(f"5e. SONG SONG THỰC: khoảng chạy của ≥{min(so, chay_ngay)} con giao nhau (đo mốc thời gian)",
                   int(th.get("song_song_toi_da") or 0) >= min(so, chay_ngay),
                   f"song_song_toi_da={th.get('song_song_toi_da')} · khoảng="
                   + "; ".join(f"[{time.strftime('%H:%M:%S', time.localtime(k['bat_dau']))}–"
                               f"{time.strftime('%H:%M:%S', time.localtime(k['ket_thuc']))} {k.get('runtime')}]"
                               for k in (th.get("khoang_chay") or [])))
        elif kich_ban == "ghi":
            bd.ghi("5e. GHI cùng tệp: khoảng chạy KHÔNG giao nhau (song song thực đo = 1)",
                   int(th.get("song_song_toi_da") or 0) <= 1 and th.get("so_con") == so,
                   f"song_song_toi_da={th.get('song_song_toi_da')} · "
                   + " | ".join(f"[{c.get('chi_so')}] {c.get('state')} {c.get('failure_reason') or ''}"
                                for c in (th.get("con") or [])))
        # Khoa cua con CUOI duoc nha trong `finally` cua luong con — vai ms
        # SAU khi cha DONE. Cho toi da 10 s roi moi ket luan "ro khoa".
        het_khoa = time.time() + 10
        while True:
            khoa_con = _state(cdp, "router").get("locks") or []
            if not khoa_con or time.time() > het_khoa:
                break
            time.sleep(0.5)
        bd.ghi("5f. không rò khoá sau khi xong", not khoa_con,
               "khoá còn giữ=" + "; ".join(
                   f"{l.get('kind')} {l.get('resource')} {l.get('mode')} giữ bởi {l.get('holder_task')} "
                   f"(id={l.get('lock_id')}, cấp {time.strftime('%H:%M:%S', time.localtime(l.get('acquired_at') or 0))})"
                   for l in khoa_con))
        rts_con = sorted({c.get("runtime") for c in (th.get("con") or []) if c.get("runtime")})
        bd.ghi("5b. nguồn gốc từng con: runtime/model/việc được giữ trong tổng hợp",
               all(c.get("runtime") and c.get("task_id") for c in (th.get("con") or [])),
               f"runtime={rts_con}")
        chat = _state(cdp, "router").get("chat") or []
        tong = [m for m in chat if (m.get("meta") or {}).get("loai") == "ket_qua"
                and (m.get("meta") or {}).get("task_id") == cha[0]["task_id"]]
        rai = [m for m in chat if (m.get("meta") or {}).get("loai") == "ket_qua"
               and (m.get("meta") or {}).get("task_id") != cha[0]["task_id"]]
        tom = [m for m in chat if (m.get("meta") or {}).get("loai") == "toa_tom_tat"]
        bd.ghi("5c. chat: MỘT tin tổng hợp của cha, không rải N tin con; Leader tóm tắt",
               len(tong) == 1 and not rai and "Tổng hợp" in tong[0].get("text", ""),
               f"tổng hợp={len(tong)} · tin con rải={len(rai)} · Leader tóm tắt={len(tom)}"
               + (" · " + " ".join((tom[0].get("text") or "").split())[:160] if tom else ""))

        kq = gs.ket_qua
        bd.ghi("6. không cửa sổ console nào DO APP nhấp lên",
               not vi_pham_cua_app(kq.vi_pham),
               kq.tom_tat() + (NL + "      " + _ta_vi_pham(kq.vi_pham) if kq.vi_pham else ""))
        sau = _dem_so(goc)
        bd.ghi("7. sổ lành", sau["nguyen_ven"] == "ok", f"control.db={sau['nguyen_ven']}")
        cuoi_git = _git_sach(goc)
        bd.ghi("8. không sửa gì: kho git tạm sạch trước và sau (việc CHỈ ĐỌC), không kho thật nào bị chạm",
               dau_git == "" and cuoi_git == "",
               f"git status trước={dau_git or '(sạch)'} · sau={cuoi_git or '(sạch)'}")
        cdp.dong()
    finally:
        gs.dung()
        if ph is not None:
            _dong_nhe(ph)
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
