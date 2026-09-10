# -*- coding: utf-8 -*-
"""Nghiệm thu SOURCE-MODE thật: KÝ ỨC DỰ ÁN (memory-first) + WEBREADER.

    python scripts/control_center_v061_ky_uc_web_acceptance.py            # dùng app đang chạy
    python scripts/control_center_v061_ky_uc_web_acceptance.py --mo-lai   # đóng rồi mở lại app
    python scripts/control_center_v061_ky_uc_web_acceptance.py --goc <dir> --chi ky-uc|web

Chạy trên ĐÚNG gốc dữ liệu người dùng dùng (`router-cc-desktop.cmd` ⇒
`<checkout>/.router`), qua API cục bộ của chính app (token ở `desktop.lock`).

Kịch bản (đề bài nghiệm thu tay 2026-09-10):
  KÝ ỨC  1. tuyên bố quyết định tường minh -> Decisions +1 NGAY (không job nền)
         2. hỏi lại bằng diễn giải KHÁC -> recall trực tiếp, 0 việc mới
         3. hỏi sự cố SSH lịch sử -> recall trực tiếp, 0 việc mới
         4. "production farmer còn chạy không?" -> vẫn đo SỐNG (live > ký ức)
  WEB    5. "<URL github> … là gì?" -> Router đọc hộ, 0 việc mới, 0
            tool_permission_denied, có sự kiện WEB_READ + nguồn gốc
         6. việc NẶNG có URL -> worker headless nhận BẰNG CHỨNG WEB trong hợp
            đồng (không cần `read_url`)
Mỗi bước in ĐẠT/HỎNG kèm số đo. Không sửa production, không in bí mật.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from pathlib import Path
from typing import Dict, List, Optional, Tuple

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))          # de `import scripts.…` chay duoc
DAT, HONG = "[ĐẠT ]", "[HỎNG]"
CAU_QD = ("hãy ghi nhớ đây là một quyết định của project: GPT-6 Astra chỉ được dùng "
          "cho các task đặc biệt khó hoặc cần reasoning cao, không dùng mặc định cho "
          "task thường.")
CAU_QD_HOI = "policy GPT-6 Astra của project này là gì?"
CAU_SSH = "cái vụ SSH key fanficappwrite trước đây bị gì?"
CAU_SONG = "production farmer còn chạy không?"
URL_GH = "https://github.com/koala73/worldmonitor/releases/tag/v2.10.0"
CAU_WEB = f"{URL_GH} github này là gì v"
CAU_WEB_NANG = (f"đọc release này {URL_GH} rồi so sánh cách họ đóng gói desktop "
                "với Router và đề xuất 3 điểm tích hợp")


def ghi(s: str = "") -> None:
    sys.stdout.write(s + "\n")
    sys.stdout.flush()


class Bang:
    def __init__(self):
        self.hang: List[Tuple[str, bool, str]] = []

    def ghi(self, buoc: str, ok: bool, ct: str = "") -> None:
        self.hang.append((buoc, bool(ok), ct))
        ghi(f"  {DAT if ok else HONG} {buoc}" + (f"  — {ct}" if ct else ""))

    def hong(self) -> List[str]:
        return [b for b, ok, _ in self.hang if not ok]


# ---------------------------------------------------------------- app I/O ---

def doc_lock(goc: Path) -> Optional[Dict]:
    p = goc / ".router" / "control_center" / "desktop.lock"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        return None


class App:
    def __init__(self, goc: Path):
        self.goc = goc
        lk = doc_lock(goc)
        if not lk:
            raise SystemExit(f"không thấy desktop.lock ở {goc} — app chưa chạy?")
        self.port, self.token, self.pid = lk["cong"], lk["token"], lk.get("pid")

    def call(self, method: str, path: str, body=None, timeout: float = 300.0):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"x-cc-token": self.token, "Host": "127.0.0.1",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def song(self) -> bool:
        try:
            self.call("GET", "/api/state", timeout=10)
            return True
        except Exception:                                   # noqa: BLE001
            return False

    def state(self, project: str = "") -> Dict:
        return self.call("GET", f"/api/state?project={project}" if project else "/api/state")

    def tasks(self, project: str) -> List[Dict]:
        return self.state(project).get("tasks") or []

    def events(self, project: str, limit: int = 300) -> List[Dict]:
        st = self.state(project)
        return (st.get("events") or [])[:limit]

    def chat(self, project: str, text: str, timeout: float = 300.0) -> Dict:
        # `webapi.chat` doi khoa `project_id` (khong phai `project`).
        return self.call("POST", "/api/chat",
                         {"project_id": project, "text": text}, timeout=timeout)

    def mem_stats(self, project: str) -> Dict:
        return self.call("GET", f"/api/memory/stats?project={project}")

    def mem_list(self, project: str, loai: str, limit: int = 50) -> List[Dict]:
        r = self.call("GET", f"/api/memory/list?project={project}&loai={loai}&limit={limit}")
        return r.get("ket_qua") or []

    def mem_record(self, project: str, ma: str) -> Dict:
        return self.call("GET", f"/api/memory/record?project={project}&ma={ma}")


def dong_nhe(pid: int, han: float = 40.0) -> bool:
    """WM_CLOSE tới mọi cửa sổ của pid, chờ tiến trình thoát."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    hs: List[int] = []

    def _cb(h, _l):
        q = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(q))
        if q.value == pid and user32.IsWindowVisible(h):
            hs.append(h)
        return True
    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    for h in hs:
        user32.PostMessageW(h, 0x0010, 0, 0)
    het = time.time() + han
    while time.time() < het:
        if not _con_song(pid):
            return True
        time.sleep(0.5)
    return not _con_song(pid)


def _con_song(pid: int) -> bool:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    ma = wintypes.DWORD()
    k32.GetExitCodeProcess(h, ctypes.byref(ma))
    k32.CloseHandle(h)
    return ma.value == 259            # STILL_ACTIVE


def mo_source_mode(goc: Path, han: float = 90.0) -> App:
    """Mở app SOURCE-MODE như `router-cc-desktop.cmd` (pythonw, không --root)."""
    pyw = Path(sys.executable).with_name("pythonw.exe")
    if not pyw.is_file():
        pyw = Path(sys.executable)
    cu = doc_lock(goc)
    cu_pid = (cu or {}).get("pid")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    subprocess.Popen([str(pyw), "-m", "scripts.control_center.desktop"],
                     cwd=str(goc), env=env, close_fds=True)
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
    raise SystemExit("mở app source-mode nhưng không thấy backend sẵn sàng")


# --------------------------------------------------------------- kich ban ---

def _so_viec(app: App, pid: str) -> int:
    return len(app.tasks(pid))


def _co_su_kien(app: App, pid: str, kind: str, tu_ts: float) -> List[Dict]:
    ra = []
    for e in app.events(pid, limit=400):
        if e.get("kind") == kind and float(e.get("ts") or 0) >= tu_ts - 1:
            ra.append(e)
    return ra


def _tool_denied(app: App, pid: str, tu_ts: float) -> List[Dict]:
    ra = []
    for e in app.events(pid, limit=400):
        if float(e.get("ts") or 0) < tu_ts - 1:
            continue
        blob = json.dumps(e, ensure_ascii=False).lower()
        if "tool_permission_denied" in blob or "read_url" in blob and "permission" in blob:
            ra.append(e)
    return ra


#: Cau dem de DAY tuyen bo ra khoi cua so hoi thoai cua Leader
#: (`leader.SO_LUOT_NGU_CANH` = 14 TIN NHAN, tuc ~7 luot nguoi dung).
CAU_DEM = ("ok", "cảm ơn nha", "ừ", "được rồi", "tốt", "ok tiếp đi", "rõ", "ừ ok")


def kich_ban_tao_qd(app: App, pid: str, bd: Bang) -> None:
    """Pha A — CHỈ tạo quyết định tường minh (rồi đóng app cho pha B)."""
    ghi("\n--- PHA A: tuyên bố quyết định tường minh ---")
    truoc = len(app.mem_list(pid, "decision"))
    t0 = time.time()
    n_viec0 = _so_viec(app, pid)
    app.chat(pid, CAU_QD)
    time.sleep(1.5)
    sau = app.mem_list(pid, "decision")
    bd.ghi("1. tuyên bố tường minh -> Decision được đề bạt NGAY (đồng bộ, không job nền)",
           len(sau) > truoc, f"decisions {truoc} -> {len(sau)} · {time.time()-t0:.1f}s")
    if sau:
        qd = sorted(sau, key=lambda d: (d.get("ky_uc") or {}).get("ts") or 0)[-1]
        k = qd.get("ky_uc") or {}
        bd.ghi("1b. đủ trường: authority user_explicit / nội dung / nguồn / bằng chứng",
               k.get("tin_cay") == "user_explicit" and "Astra" in (k.get("noi_dung") or "")
               and k.get("nguon_loai") == "chat_user" and bool(k.get("bang_chung")),
               f"{qd.get('ma')} auth={k.get('tin_cay')} nguon={k.get('nguon_loai')}#"
               f"{k.get('nguon_id')} bằng chứng={len(k.get('bang_chung') or [])}")
        rec = app.mem_record(pid, qd.get("ma") or "")
        bd.ghi("1c. provenance tra được: ID + timestamp + nguồn + bằng chứng L0",
               bool(rec.get("co")) and bool(rec.get("bang_chung")),
               f"co={rec.get('co')} bằng chứng={len(rec.get('bang_chung') or [])} "
               f"ts={(rec.get('ky_uc') or {}).get('ts')}")
    bd.ghi("1d. tuyên bố KHÔNG sinh việc worker nào",
           _so_viec(app, pid) == n_viec0, f"việc {n_viec0} -> {_so_viec(app, pid)}")


def _vi_tri_tuyen_bo(app: App, pid: str) -> int:
    """Tuyên bố Astra cách CUỐI hội thoại bao nhiêu TIN NHẮN (để biết nó còn
    trong cửa sổ 14 tin của Leader hay đã bị đẩy ra)."""
    ch = app.state(pid).get("chat") or []
    for i, m in enumerate(reversed(ch)):
        if "quyết định của project" in str(m.get("text") or "") and m.get("role") == "user":
            return i
    return -1


def kich_ban_recall(app: App, pid: str, bd: Bang, *, day_lui: int = 8) -> None:
    """Pha B — phiên Leader MỚI: đẩy tuyên bố ra khỏi cửa sổ hội thoại rồi hỏi
    bằng diễn giải KHÁC. Trả lời đúng ⇒ đến TỪ KÝ ỨC, không từ transcript."""
    ghi("\n--- PHA B: phiên Leader MỚI, recall bằng diễn giải khác ---")
    from scripts.control_center.leader import SO_LUOT_NGU_CANH
    for i, c in enumerate(CAU_DEM[:day_lui]):
        app.chat(pid, c)
        time.sleep(0.3)
    kc = _vi_tri_tuyen_bo(app, pid)
    ngoai = kc < 0 or kc >= SO_LUOT_NGU_CANH
    bd.ghi(f"2a. tuyên bố ĐÃ RA KHỎI cửa sổ hội thoại của Leader ({SO_LUOT_NGU_CANH} tin)",
           ngoai, f"cách cuối {kc} tin nhắn (cần >= {SO_LUOT_NGU_CANH})")

    n1 = _so_viec(app, pid)
    r2 = app.chat(pid, CAU_QD_HOI)
    time.sleep(1.0)
    tl2 = str(r2.get("reply") or "")
    dung = ("astra" in tl2.lower() and
            any(x in tl2.lower() for x in ("khó", "reasoning", "đặc biệt", "mặc định")))
    bd.ghi("2. recall CHÉO PHIÊN bằng diễn giải khác -> trả lời đúng, 0 việc mới",
           dung and _so_viec(app, pid) == n1,
           f"việc {n1} -> {_so_viec(app, pid)} · reply: {' '.join(tl2.split())[:220]}")
    bd.ghi("2b. trả lời nêu MÃ bản ghi (qd_/ku_) — lần về được bằng chứng",
           any(x in tl2 for x in ("qd_", "ku_", "sk#")),
           f"reply: {' '.join(tl2.split())[:160]}")

    # 3. Su co SSH lich su -> recall, 0 viec moi.
    n2 = _so_viec(app, pid)
    r3 = app.chat(pid, CAU_SSH)
    time.sleep(1.0)
    tl3 = str(r3.get("reply") or "")
    them = _so_viec(app, pid) - n2
    bd.ghi("3. sự cố SSH lịch sử -> recall trực tiếp, 0 worker dispatch",
           them == 0,
           f"việc mới={them} · reply: {' '.join(tl3.split())[:200]}")
    bd.ghi("3b. câu trả lời SSH có nội dung lịch sử (nêu tên tệp/mã bản ghi)",
           any(x in tl3.lower() for x in ("fanficappw", "ku_", "sk#", ".pem", "khoá", "khóa")),
           f"reply: {' '.join(tl3.split())[:200]}")

    # 4. Cau hoi HIEN TAI -> van do song (live > ky uc).
    n3 = _so_viec(app, pid)
    t4 = time.time()
    r4 = app.chat(pid, CAU_SONG)
    time.sleep(1.0)
    tl4 = str(r4.get("reply") or "")
    probe = _co_su_kien(app, pid, "LIVE_PROBE", t4) + _co_su_kien(app, pid, "LIVE_PROBE_FAILED", t4)
    bd.ghi("4. câu hỏi HIỆN TẠI vẫn đi đo SỐNG (live > ký ức)",
           bool(probe),
           f"sự kiện probe={len(probe)} · reply: {' '.join(tl4.split())[:150]}")


def kich_ban_web(app: App, pid: str, bd: Bang) -> None:
    ghi("\n--- WEBREADER (Router đọc web công khai) ---")
    # 5. Cau hoi URL don gian -> Router doc ho, 0 viec, 0 tool_permission_denied.
    n0 = _so_viec(app, pid)
    t0 = time.time()
    r = app.chat(pid, CAU_WEB)
    time.sleep(1.5)
    tl = str(r.get("reply") or "")
    them = _so_viec(app, pid) - n0
    wr = _co_su_kien(app, pid, "WEB_READ", t0)
    denied = _tool_denied(app, pid, t0)
    bd.ghi("5. URL đơn giản: Router đọc hộ (có sự kiện WEB_READ)", bool(wr),
           " · ".join(f"{e.get('detail','')[:110]}" for e in wr[:2]) or "(không có WEB_READ)")
    bd.ghi("5b. KHÔNG tool_permission_denied", not denied,
           f"số sự kiện={len(denied)}" + (f" · {denied[0].get('detail','')[:100]}" if denied else ""))
    bd.ghi("5c. KHÔNG tốn worker cho câu hỏi đơn giản", them == 0,
           f"việc mới={them}")
    bd.ghi("5d. trả lời có nội dung THẬT của trang (grounded)",
           any(x in tl.lower() for x in ("worldmonitor", "world monitor", "v2.10.0", "release")),
           f"reply: {' '.join(tl.split())[:220]}")
    if wr:
        m = wr[0].get("meta") or {}
        bd.ghi("5e. nguồn gốc được ghi: URL + trạng thái + băm nội dung",
               bool(m.get("url")) and bool(m.get("bam")) and bool(m.get("trang_thai")),
               f"url={str(m.get('url'))[:60]} status={m.get('trang_thai')} "
               f"bam={str(m.get('bam'))[:16]} nguon={m.get('nguon')}")

    # 6. Viec NANG co URL -> worker nhan BANG CHUNG WEB trong hop dong.
    n1 = _so_viec(app, pid)
    t1 = time.time()
    r2 = app.chat(pid, CAU_WEB_NANG)
    time.sleep(2.0)
    ts = app.tasks(pid)
    moi = [t for t in ts if float(t.get("created_at") or 0) >= t1 - 1]
    co_bang_chung = []
    for t in moi:
        hd = t.get("contract") or {}
        obj = str(hd.get("objective") or "")
        if "NỘI DUNG WEB DO ROUTER CUNG CẤP" in obj or "NỘI DUNG WEB DO ROUTER ĐỌC" in obj:
            co_bang_chung.append(t.get("task_id"))
    bd.ghi("6. việc NẶNG có URL -> hợp đồng worker mang BẰNG CHỨNG WEB",
           bool(moi) and bool(co_bang_chung),
           f"việc mới={[t.get('task_id') for t in moi]} · có bằng chứng={co_bang_chung}")
    if moi:
        ghi(f"      (để worker chạy xong tự nhiên; không chờ ở bước này)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--goc", default=str(GOC), help="gốc dữ liệu (mặc định: checkout này)")
    ap.add_argument("--project", default="fanfic")
    ap.add_argument("--mo-lai", action="store_true", help="đóng app đang chạy rồi mở lại")
    ap.add_argument("--chi", default="", choices=("", "qd", "recall", "web"),
                    help="qd = pha A (tạo quyết định); recall = pha B (phiên mới); web = WebReader")
    ap.add_argument("--day-lui", type=int, default=8,
                    help="số câu đệm để đẩy tuyên bố ra khỏi cửa sổ hội thoại (pha B)")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                   # noqa: BLE001
            pass
    goc = Path(a.goc).resolve()
    bd = Bang()
    ghi("=" * 78)
    ghi("NGHIỆM THU SOURCE-MODE — KÝ ỨC DỰ ÁN + WEBREADER")
    ghi(f"  gốc dữ liệu : {goc}")
    ghi(f"  dự án       : {a.project}")
    ghi("=" * 78)

    if a.mo_lai:
        lk = doc_lock(goc)
        if lk and lk.get("pid") and _con_song(int(lk["pid"])):
            ok = dong_nhe(int(lk["pid"]))
            bd.ghi("0. đóng app đang chạy (WM_CLOSE, sạch)", ok, f"pid {lk['pid']}")
            time.sleep(2.0)
        app = mo_source_mode(goc)
        bd.ghi("0b. mở lại SOURCE-MODE (pythonw, mã mới) + backend sẵn sàng",
               app.song(), f"pid {app.pid} cổng {app.port}")
    else:
        app = App(goc)
        bd.ghi("0. dùng app source-mode đang chạy", app.song(),
               f"pid {app.pid} cổng {app.port}")

    st = app.state()
    bd.ghi("0c. dự án có trong app + sổ ký ức sẵn sàng",
           any(p.get("project_id") == a.project for p in st.get("projects") or []),
           f"projects={[p.get('project_id') for p in st.get('projects') or []]}")
    tk = app.mem_stats(a.project)
    dem = tk.get("dem") or {}
    ghi(f"  sổ ký ức: su_kien={dem.get('su_kien')} ky_uc={dem.get('ky_uc')} "
        f"decision={dem.get('ky_uc_decision')} incident={dem.get('ky_uc_incident')}")

    if a.chi in ("", "qd"):
        kich_ban_tao_qd(app, a.project, bd)
    if a.chi in ("", "recall"):
        kich_ban_recall(app, a.project, bd, day_lui=a.day_lui)
    if a.chi in ("", "web"):
        kich_ban_web(app, a.project, bd)

    tk2 = app.mem_stats(a.project)
    d2 = tk2.get("dem") or {}
    ghi("")
    ghi(f"  sổ ký ức SAU: su_kien={d2.get('su_kien')} ky_uc={d2.get('ky_uc')} "
        f"decision={d2.get('ky_uc_decision')} incident={d2.get('ky_uc_incident')}")
    bd.ghi("7. UI đếm đúng: Decisions >= 1 và Incidents >= 1",
           int(d2.get("ky_uc_decision") or 0) >= 1 and int(d2.get("ky_uc_incident") or 0) >= 1,
           f"decision={d2.get('ky_uc_decision')} incident={d2.get('ky_uc_incident')}")

    ghi("=" * 78)
    hong = bd.hong()
    ghi(f"KẾT LUẬN: {len(bd.hang) - len(hong)}/{len(bd.hang)} bước ĐẠT")
    for h in hong:
        ghi(f"  HỎNG: {h}")
    ghi("=" * 78)
    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())
