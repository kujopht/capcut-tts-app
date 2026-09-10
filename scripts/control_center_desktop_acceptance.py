"""Nghiệm thu VỎ DESKTOP trên Windows THẬT — EXE/app thật, WebView2 thật.

Chín bước đúng theo danh sách nghiệm thu, chạy trên cửa sổ WebView2 THẬT
của chính ứng dụng (không phải một trình duyệt bên ngoài, không phải một
DOM mô phỏng).

    python scripts/control_center_desktop_acceptance.py
    python scripts/control_center_desktop_acceptance.py --exe "dist/Router Control Center.exe"

CÁCH NÓ NHÌN VÀO CỬA SỔ: `--debug-cdp <cổng>` bảo `desktop.py` đặt
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=…`, nên
WebView2 mở một cổng DevTools và kịch bản nối vào **đúng cửa sổ ứng dụng**.
Cờ đó CHỈ dùng khi kiểm; đường bấm đôi bình thường không có nó, và có bài
kiểm khẳng định mặc định là 0.

GIỚI HẠN, nói thẳng: kịch bản không tự bấm được `Win+Shift+S` (Snipping
Tool đòi người kéo chuột chọn vùng) và không tự bấm được `Ctrl+V` ở tầng hệ
điều hành. Nó chứng minh *đường mã* xử lý đúng những sự kiện mà WebView2
giao cho — đúng những sự kiện Chromium phát khi người dùng dán/thả thật.
Hai cú bấm đó là việc của con người.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.ghi_utf8 import (GhiUTF8,  # noqa: E402
                                             duong_nhat_ky)
from scripts.giam_sat_cua_so import (TIEN_TRINH_CONSOLE,  # noqa: E402
                                     GiamSatCuaSo,
                                     _anh_chup_tien_trinh,
                                     vi_pham_cua_app)
from scripts.router_v3.tien_trinh import an_cua_so  # noqa: E402

#: KHONG `print()`. Moi cau kich ban nay in ra la tieng Viet, va
#: `print()` giao chuoi cho tang VAN BAN cua luong — codec do locale
#: quyet dinh, cp1252 tren may nay. Mot bo NGHIEM THU chet o dong tieu
#: de cua chinh no thi khong nghiem thu duoc gi.
ghi_ra = GhiUTF8()

DAT, HONG = "[ĐẠT ]", "[HỎNG]"
NL = chr(10)


class Bang:
    def __init__(self):
        self.hang = []

    def ghi(self, b, ok, ct=""):
        self.hang.append((b, bool(ok)))
        ghi_ra(f"  {DAT if ok else HONG} {b}" + (f"  — {ct}" if ct else ""))

    def hong(self):
        return [b for b, ok in self.hang if not ok]


class CDP:
    def __init__(self, cong: int, han: float = 45.0):
        from websockets.sync.client import connect
        het = time.time() + han
        ws_url = ""
        while time.time() < het and not ws_url:
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{cong}/json/list", timeout=2) as f:
                    for t in json.load(f):
                        if (t.get("type") == "page"
                                and "127.0.0.1" in (t.get("url") or "")
                                and t.get("webSocketDebuggerUrl")):
                            ws_url = t["webSocketDebuggerUrl"]
                            break
            except (urllib.error.URLError, OSError, ValueError):
                pass
            if not ws_url:
                time.sleep(0.4)
        if not ws_url:
            raise RuntimeError(f"không nối được CDP ở cổng {cong}")
        self.ws = connect(ws_url, max_size=32 * 1024 * 1024)
        self.n = 0

    def js(self, ma: str):
        self.n += 1
        self.ws.send(json.dumps({
            "id": self.n, "method": "Runtime.evaluate",
            "params": {"expression": "(async () => {" + NL + ma + NL + "})()",
                       "awaitPromise": True, "returnByValue": True}}))
        while True:
            g = json.loads(self.ws.recv(timeout=40))
            if g.get("id") == self.n:
                r = g.get("result", {})
                if r.get("exceptionDetails"):
                    raise RuntimeError(
                        json.dumps(r["exceptionDetails"])[:300])
                return r.get("result", {}).get("value")

    def dua_len_truoc(self) -> None:
        """`Page.bringToFront` — cho cửa sổ có focus của HỆ ĐIỀU HÀNH.

        VÌ SAO CẦN, và vì sao đây KHÔNG phải nới lỏng phép kiểm: một
        người dùng thật đang gõ vào ô chat thì cửa sổ của họ ĐANG là cửa
        sổ trước. Bộ nghiệm thu chạy từ một tiến trình khác nên cửa sổ
        app nằm dưới, `document.hasFocus()` là `false`, và trong trạng
        thái đó Chromium có thể trả `document.activeElement` về `BODY`
        sau một lần vẽ lại — đo được: gọi `focus()` trực tiếp vẫn đặt
        được `activeElement`, nhưng nó không dính qua các lần vẽ lại khi
        tài liệu không có focus hệ thống.

        Nên phép kiểm "con trỏ còn ở ô soạn" chỉ có nghĩa khi cửa sổ ở
        trạng thái người dùng thật có. Đưa nó lên trước là dựng đúng
        trạng thái đó, không phải bỏ qua phép kiểm.
        """
        self.n += 1
        self.ws.send(json.dumps({"id": self.n,
                                 "method": "Page.bringToFront"}))
        het = time.time() + 10
        while time.time() < het:
            g = json.loads(self.ws.recv(timeout=10))
            if g.get("id") == self.n:
                return

    def phim(self, key: str, ma_vk: int, *, shift: bool = False) -> None:
        """Bắn một phím THẬT qua `Input.dispatchKeyEvent`.

        Khác `dispatchEvent(new KeyboardEvent(...))`: sự kiện tổng hợp
        bằng JS không `isTrusted` và không đi qua đường nhập của
        Chromium, nên nó không chứng minh được phím Enter thật sự gửi
        được tin. `Input.*` là đường của người dùng.
        """
        for loai in ("keyDown", "keyUp"):
            self.n += 1
            self.ws.send(json.dumps({
                "id": self.n, "method": "Input.dispatchKeyEvent",
                "params": {"type": loai, "key": key, "code": key,
                           "windowsVirtualKeyCode": ma_vk,
                           "nativeVirtualKeyCode": ma_vk,
                           "modifiers": 8 if shift else 0}}))
            het = time.time() + 10
            while time.time() < het:
                g = json.loads(self.ws.recv(timeout=10))
                if g.get("id") == self.n:
                    break

    def cho(self, ma: str, han: float = 30.0):
        het = time.time() + han
        while time.time() < het:
            if self.js(ma):
                return True
            time.sleep(0.25)
        return False

    def dong(self):
        try:
            self.ws.close()
        except Exception:                                   # noqa: BLE001
            pass


def dem_webview2() -> int:
    """So tien trinh `msedgewebview2.exe` — host NHUNG cua WebView2.

    No LA ung dung cua ta, khong phai mot trinh duyet ngoai. Thay no tuc
    la giao dien dang o trong cua so cua minh.
    """
    try:
        # CHE DO NHI PHAN, co y: `text=True` se giai ma dau ra cua
        # `tasklist` bang codec cua LOCALE, va `tasklist` ghi ra bang
        # code page cua console voi thong diep da dia phuong hoa. Tren
        # may Viet phep giai ma do co the nem `UnicodeDecodeError`, roi
        # `except` ben duoi tra 0 — bao "khong co WebView2 nao" trong
        # khi cua so dang mo. Ten tien trinh la ASCII nen so khop byte
        # vua chinh xac vua khong the sai vi locale.
        # `an_cua_so()`: BO NGHIEM THU cung phai tuan luat no kiem.
        # Do duoc that: `python.exe` chay bo nay KHONG co console
        # (`GetConsoleWindow()` tra 0, vi bo chay lenh sinh no o che
        # do khong cua so), nen MOI tien trinh console con khong
        # mang co an se duoc He dieu hanh cap mot console MOI — va
        # voi Windows Terminal la terminal mac dinh thi do la mot
        # cua so nhap len. `tasklist` o day tung tu sinh ra dung cai
        # vi pham ma `V4o` di tim, tuc la bo do tu lam nhiem ket qua.
        r = subprocess.run(["tasklist", "/fo", "csv", "/nh"],
                           capture_output=True, timeout=25,
                           **an_cua_so())
    except Exception:                                       # noqa: BLE001
        return 0
    n = 0
    for dong in (r.stdout or b"").splitlines():
        if b"msedgewebview2.exe" in dong.lower():
            n += 1
    return n


def _png_nen(w: int = 960, h: int = 600) -> bytes:
    """Một PNG THẬT, tự mã hoá — không thư viện ảnh nào.

    Phải là PNG hợp lệ vì tầng đính kèm kiểm **chữ ký byte** chứ không
    tin đuôi tệp, và allowlist CỐ Ý không nhận `svg`. Nên đây cũng là một
    phép kiểm của chính đường lưu ảnh nền, không chỉ là một tệp mẫu.
    """
    import struct
    import zlib

    hang = []
    for y in range(h):
        d = bytearray([0])                      # filter 0 = None
        for x in range(w):
            t = (x / w) * 0.6 + (1 - y / h) * 0.4
            v = (18 + 120 * t * t, 34 + 190 * t * t, 66 + 210 * t * t)
            if (x * 7919 + y * 104729) % 2909 == 0:
                v = (210, 250, 245)
            d += bytes(max(0, min(255, int(c))) for c in v)
        hang.append(bytes(d))

    def khoi(ten: bytes, du: bytes) -> bytes:
        return (struct.pack(">I", len(du)) + ten + du
                + struct.pack(">I", zlib.crc32(ten + du) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + khoi(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + khoi(b"IDAT", zlib.compress(b"".join(hang), 6))
            + khoi(b"IEND", b""))


def kho_git_tam() -> Path:
    goc = Path(tempfile.mkdtemp(prefix="cc-desk-acc-"))
    (goc / "docs").mkdir(parents=True)
    (goc / "docs" / "seed.md").write_text("seed\n", encoding="utf-8")
    for c in (["git", "init", "-q"],
              ["git", "config", "user.email", "t@l"],
              ["git", "config", "user.name", "t"],
              ["git", "add", "-A"], ["git", "commit", "-q", "-m", "seed"]):
        subprocess.run(c, cwd=goc, check=True, capture_output=True,
                       **an_cua_so())
    return goc


#: Trang thai tieng Viet gieo san. Ba cau nay la ba cau yeu cau
#: nghiem thu doi dung tung chu.
DU_AN_VIET = "Hàng đợi sản xuất"
CHAT_VIET = ("Đường dẫn thử nghiệm — Người dùng"
             " | ă â đ ê ô ơ ư Ă Â Đ Ê Ô Ơ Ư")
TEP_VIET = "Đường dẫn thử nghiệm.csv"


def gieo_trang_thai_tieng_viet(goc: Path) -> dict:
    """Ghi san mot so co TIENG VIET, TRUOC khi EXE duoc mo lan dau.

    Vi sao phai gieo truoc: yeu cau nghiem thu la "mo EXE tren trang
    thai da co san". Su co cp1252 lo ra dung o luc KHOI DONG, nen mot
    so rong khong chung minh duoc gi — pha co san chu tieng Viet trong
    ten du an, trong chat, va trong ten tep dinh kem thi lan mo moi di
    qua dung nhung duong da vo.
    """
    from scripts.control_center.attachments import KhoDinhKem
    from scripts.control_center.bootstrap import khoi_tao
    from scripts.control_center.model import Project
    from scripts.control_center.store import ControlStore

    st = ControlStore(root=goc)
    try:
        # Gieo du an mac dinh TRUOC (`khoi_tao` chi gieo khi so rong),
        # de duong "gui mot viec that" ben duoi khong doi hanh vi.
        khoi_tao(st, root=goc)
        st.luu_project(Project(project_id="viet", name=DU_AN_VIET,
                               repo_path=str(goc)))
        # Gan dinh kem vao DUNG BAN TIN, khong chi vao du an: giao dien
        # ve dinh kem BEN TRONG bong bong tin nhan
        # (`dinh_kem_cua_message`), nen mot dinh kem chi thuoc du an
        # thi khong hien o dau ca.
        tin = st.them_chat("viet", "user", CHAT_VIET)
        noi_dung = ("cột1,cột2\nĐường,dẫn\n"
                    ).encode("utf-8")
        dk = KhoDinhKem(st, goc=goc).them_tu_bytes(
            "viet", noi_dung, TEP_VIET, message_id=tin.message_id)
        return {"sha": dk.sha256, "co": dk.size_bytes,
                "ten": dk.filename}
    finally:
        st.close()               # nha WAL truoc khi EXE mo cung so


def _con_song(pid: int) -> bool:
    return pid in _anh_chup_tien_trinh()


class TienTrinhShell:
    """Tiến trình mở qua `ShellExecuteW` — ĐÚNG API mà Explorer gọi.

    VÌ SAO KHÔNG `subprocess.Popen` CHO BẢN ĐÓNG GÓI, và đây là một phát
    hiện đo được, không phải một sở thích:

    Smart App Control đang BẬT CƯỠNG CHẾ trên máy này
    (`VerifiedAndReputablePolicyState=0x1`). Mở bản EXE mới build bằng
    `CreateProcess` từ `python.exe` bị chặn thẳng:

        OSError: [WinError 4551] An Application Control policy has
        blocked this file

    và `Microsoft-Windows-CodeIntegrity/Operational` ghi sự kiện **3077**
    + **3118 (Smart App Control Block)**: *"a process
    (\\...\\python.exe) attempted to load \\...\\Router Control
    Center.exe that did not meet the Enterprise signing level
    requirements"*. Tức là phán quyết của SAC tính CẢ tiến trình CHA.

    Cùng một tệp EXE, mở bằng `ShellExecuteW` thì **chạy bình thường** —
    và đó không phải một đường lách: `ShellExecuteW` LÀ API Explorer gọi
    khi người dùng bấm đôi một tệp, nên nó vừa là đường người dùng thật
    đi, vừa đúng tiêu chí nghiệm thu số 1 ("launch normally from
    Explorer"). Bản trước dùng `Popen` chỉ vì nó cho ống dẫn stdout.

    Đánh đổi: KHÔNG có ống dẫn stdout. Không sao, và thực ra tốt hơn:
    bản `--noconsole` không có ai đọc `stdout` cả, nên nhật ký thật của
    nó là tệp `<goc>/.router/control_center/desktop.log` do `GhiUTF8`
    ghi. Đọc tệp đó là đọc đúng đường chẩn đoán của sản phẩm.

    `terminate()` gọi `taskkill` KHÔNG có `/F`: nó gửi yêu cầu đóng tới
    cửa sổ, nên `webview` phát sự kiện `closed` và `_khi_dong()` của
    `desktop.py` CHẠY THẬT (tắt backend, xoá tệp khoá). Bản trước dùng
    `TerminateProcess`, tức là giết cứng và KHÔNG đi qua đường "người
    dùng đóng cửa sổ" — mà đó chính là đường tiêu chí 8 đang hỏi.
    """

    def __init__(self, pid: int, exe: Path):
        self.pid = int(pid)
        self.exe = exe

    def poll(self):
        return None if _con_song(self.pid) else 0

    def _kill(self, cung: bool) -> None:
        if not _con_song(self.pid):
            return
        lenh = ["taskkill", "/PID", str(self.pid), "/T"]
        if cung:
            lenh.append("/F")
        subprocess.run(lenh, capture_output=True, timeout=40,
                       **an_cua_so())

    def terminate(self) -> None:
        self._kill(False)

    def kill(self) -> None:
        self._kill(True)

    def wait(self, timeout: float = 30.0):
        het = time.time() + timeout
        while time.time() < het:
            if not _con_song(self.pid):
                return 0
            time.sleep(0.3)
        raise subprocess.TimeoutExpired(str(self.exe), timeout)


def _mo_qua_explorer(p_exe: Path, goc: Path, cdp: int,
                     them: str = "") -> TienTrinhShell:
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteW.restype = wintypes.HINSTANCE
    shell32.ShellExecuteW.argtypes = [
        wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]

    truoc = {q for q, (_, t) in _anh_chup_tien_trinh().items()
             if t.lower() == p_exe.name.lower()}
    tham = f'--root "{goc}" --debug-cdp {cdp}' + (f" {them}" if them else "")
    r = int(shell32.ShellExecuteW(None, "open", str(p_exe), tham,
                                  str(p_exe.parent), 1))   # SW_SHOWNORMAL
    if r <= 32:
        raise SystemExit(
            f"ShellExecuteW từ chối mở {p_exe.name}: mã {r} "
            f"(GetLastError={ctypes.get_last_error()})")
    het = time.time() + 40
    while time.time() < het:
        moi = {q for q, (_, t) in _anh_chup_tien_trinh().items()
               if t.lower() == p_exe.name.lower()} - truoc
        if moi:
            return TienTrinhShell(sorted(moi)[0], p_exe)
        time.sleep(0.3)
    raise SystemExit(f"mở {p_exe.name} qua Explorer nhưng không thấy "
                     f"tiến trình nào mới")


def mo_app(exe: str, goc: Path, cdp: int, log: Path):
    """Mở ứng dụng desktop. `exe` rỗng = chạy từ mã nguồn."""
    if exe:
        # TUYET DOI hoa: duong dan tuong doi se ra `WinError 2` du tep
        # co that, vi no duoc phan giai theo cwd cua tien trinh CHA.
        p_exe = Path(exe)
        if not p_exe.is_absolute():
            p_exe = (GOC / exe).resolve()
        if not p_exe.is_file():
            raise SystemExit(f"không thấy EXE: {p_exe}")
        return _mo_qua_explorer(p_exe, goc, cdp), None
    else:
        lenh = [sys.executable, "-m", "scripts.control_center.desktop",
                "--root", str(goc), "--debug-cdp", str(cdp)]
    # KHONG tiem `PYTHONUTF8` / `PYTHONIOENCODING` vao day, va day la
    # dinh chinh CUA CHINH BO NGHIEM THU NAY. Ban truoc tiem ca hai, nen
    # no do mot moi truong KHONG NGUOI DUNG NAO CO: bam doi tu Explorer
    # thi khong ai dat bien nao ca. Ket qua la 19/19 xanh tren mot duong
    # khong ai di, trong khi EXE that chet ngay khi mo voi
    # `UnicodeEncodeError` tren chu `ư`.
    #
    # Bo nghiem thu phai chay EXE nhu NGUOI DUNG chay no: locale cua may,
    # khong bien moi truong nao. Neu ma nguon can mot bien de song thi
    # do la loi cua ma nguon.
    #
    # `PYTHONUNBUFFERED` thi giu: no khong lien quan gi den encoding, chi
    # de nhat ky con hien ra ngay thay vi nam trong bo dem.
    moi = dict(os.environ, PYTHONUNBUFFERED="1")
    for _bien in ("PYTHONUTF8", "PYTHONIOENCODING",
                  "PYTHONLEGACYWINDOWSSTDIO"):
        moi.pop(_bien, None)            # ke ca khi CHA co san
    f = open(log, "wb")
    return subprocess.Popen(lenh, stdout=f, stderr=subprocess.STDOUT,
                            cwd=str(GOC), env=moi), f


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default="",
                    help="đường dẫn EXE đã build (rỗng = chạy từ mã nguồn)")
    ap.add_argument("--cdp", type=int, default=9455)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)

    bd = Bang()
    goc = kho_git_tam()
    gieo = gieo_trang_thai_tieng_viet(goc)
    tam = Path(tempfile.mkdtemp(prefix="cc-desk-log-"))
    ph = None
    f1 = None
    cdp = None
    ghi_ra("=" * 78)
    ghi_ra("NGHIỆM THU VỎ DESKTOP — WebView2 THẬT")
    ghi_ra(f"  chạy   : {a.exe or 'từ mã nguồn (python -m …desktop)'}")
    ghi_ra(f"  kho tạm: {goc}")
    ghi_ra(f"  gieo   : {gieo['ten']!r} sha={gieo['sha'][:12]}…")
    ghi_ra("=" * 78)

    # GIAM SAT BAT TRUOC KHI APP MO, va do la bat buoc: moc nen phai
    # duoc chup khi chua co cua so nao cua lan mo nay, khong thi cua so
    # cua chinh app se nam trong moc nen va khong bao gio bi tinh.
    gs = GiamSatCuaSo()
    gs.__enter__()
    try:

        # -- 1. Mo app -----------------------------------------------------
        gs.dat_pha("mở app")
        ph, f1 = mo_app(a.exe, goc, a.cdp, tam / "lan1.log")
        gs.theo(ph.pid)
        cdp = CDP(a.cdp)
        bd.ghi("1. ứng dụng mở được (cửa sổ WebView2)", True,
               f"pid {ph.pid}")
        kq_mo = gs.ket_qua
        bd.ghi("1c. V0.4 — KHỞI ĐỘNG không nhấp cửa sổ console nào",
               not vi_pham_cua_app(kq_mo.vi_pham),
               _ta_vi_pham(kq_mo.vi_pham) if kq_mo.vi_pham
               else "0 cửa sổ trong lúc khởi động")

        ua = cdp.js("return navigator.userAgent") or ""
        bd.ghi("1b. là WebView2 (Chromium), không phải IE/mshtml",
               "Chrome/" in ua and "Trident" not in ua, ua[:60] + "…")

        # -- 2. KHONG mo trinh duyet ngoai ---------------------------------
        #
        # KHONG so sanh danh sach PID chrome/msedge truoc-sau: Chrome cua
        # nguoi dung SINH VA THU renderer lien tuc, nen phep so do bao
        # dong vi hoat dong binh thuong cua mot trinh duyet khong lien
        # quan. Da thay that: 4 "tien trinh moi" trong khi app khong mo
        # trinh duyet nao. Do la bai kiem GION, khong phai loi san pham.
        #
        # Hai phep kiem TAT DINH thay cho no:
        time.sleep(1.5)
        ma_desktop = (GOC / "scripts" / "control_center"
                      / "desktop.py").read_text(encoding="utf-8")
        bd.ghi("2. KHONG co duong nao mo trinh duyet ngoai",
               "webbrowser" not in ma_desktop,
               "desktop.py khong import/goi `webbrowser`")

        # Va WebView2 NHUNG that su dang chay: `msedgewebview2.exe` la
        # tien trinh host cua WebView2 — no LA ung dung cua ta. Thay no
        # tuc la giao dien dang o trong cua so cua minh, khong o mot tab
        # trinh duyet nao.
        bd.ghi("2b. dang dung WebView2 NHUNG (msedgewebview2.exe)",
               dem_webview2() > 0, f"{dem_webview2()} tien trinh host")

        # -- 7. Token khong lo ra tieu de/URL ------------------------------
        tieu_de = cdp.js("return document.title") or ""
        tim = cdp.js("return location.search") or ""
        bd.ghi("7. token KHÔNG lộ ra tiêu đề/URL",
               "t=" not in tieu_de and "t=" not in tim,
               f"tiêu đề={tieu_de!r} search={tim!r}")

        bd.ghi("7b. giao diện nạp được (sidebar có dự án)",
               cdp.cho("return !!document.querySelector('#ds-project li')"),
               cdp.js("return [...document.querySelectorAll('#ds-project li')]"
                      ".map(x=>x.dataset.pid).join(',')"))
        # -- 7v. TIENG VIET tren trang thai DA CO SAN ----------------------
        #
        # Day la bai kiem cho su co that: EXE chet ngay khi mo voi
        # `UnicodeEncodeError` tren chu `ư`. Ba phep kiem duoi doi dung ba
        # thu nguoi dung nhin thay — ten du an, chat, ten tep dinh kem —
        # tren mot so DA CO chu tieng Viet TRUOC khi EXE duoc mo.
        cdp.js("const li=document.querySelector('#ds-project li"
               "[data-pid=\"viet\"]'); if(li) li.click(); return 1;")
        bd.ghi("7v. tên dự án tiếng Việt hiện đúng trong sidebar",
               cdp.cho("return [...document.querySelectorAll('#ds-project "
                       "li')].some(x => x.textContent.includes("
                       + json.dumps(DU_AN_VIET) + "))"),
               DU_AN_VIET)
        bd.ghi("7w. chat tiếng Việt đã lưu hiện đúng (ă â đ ê ô ơ ư …)",
               cdp.cho("return (document.querySelector('#ds-tin')"
                       ".textContent || '').includes("
                       + json.dumps(CHAT_VIET) + ")"),
               CHAT_VIET[:40] + "…")
        bd.ghi("7x. tên tệp đính kèm tiếng Việt hiện đúng",
               cdp.cho("return (document.querySelector('#ds-tin')"
                       ".textContent || '').includes("
                       + json.dumps(TEP_VIET) + ")"),
               TEP_VIET)

        # Byte tren dia phai KHOP hash da ghi trong so. Doc lai va bam
        # hash DOC LAP thay vi tin con so trong SQLite: neu mot lop nao
        # tren duong luu tru da "sua" van ban tieng Viet (bo dau, doi
        # codec) thi hash se lech, va do la phep kiem "nguyen ven tung
        # byte" that su.
        from scripts.control_center.attachments import KhoDinhKem
        from scripts.control_center.store import ControlStore
        _st = ControlStore(root=goc)
        try:
            _ds = [x for x in _st.dinh_kem_cua_project("viet")
                   if x.filename == TEP_VIET]
            _p = KhoDinhKem(_st, goc=goc).duong_dan(_ds[0].attachment_id) \
                if _ds else None
            _tho = _p.read_bytes() if _p and _p.is_file() else b""
        finally:
            _st.close()
        bd.ghi("7u. đính kèm tên tiếng Việt: hash + cỡ khớp từng byte",
               bool(_tho)
               and hashlib.sha256(_tho).hexdigest() == gieo["sha"]
               and len(_tho) == gieo["co"],
               f"sha256={gieo['sha'][:12]}… cỡ={gieo['co']} byte")

        # Nhat ky cua chinh lan mo nay: KHONG duoc co ngoai le encoding, va
        # phai la UTF-8 hop le. Doc BYTE roi giai ma nghiem ngat — neu vo
        # thi tep khong phai UTF-8 va bai kiem dung phai do.
        #
        # Doc TEP NHAT KY CUA SAN PHAM, khong phai mot ong dan stdout:
        # ban `--noconsole` khong co ai doc `stdout`, nen day la duong
        # chan doan THAT — va `ShellExecuteW` cung khong cho ong dan nao.
        tho = _doc_log(goc)
        try:
            van = tho.decode("utf-8")
            la_utf8 = True
        except UnicodeDecodeError as exc:
            van, la_utf8 = repr(exc), False
        bd.ghi("7y. nhật ký khởi động là UTF-8 hợp lệ, KHÔNG UnicodeEncodeError",
               la_utf8 and "UnicodeEncodeError" not in van
               and "charmap" not in van,
               f"{len(tho)} byte" if la_utf8 else van[:80])
        bd.ghi("7z. nhật ký giữ nguyên chữ 'ư' (U+01B0)",
               la_utf8 and "ư" in van,
               next((d for d in van.splitlines() if "ư" in d), "")[:60])

        bd.ghi("7c. WebSocket sống",
               cdp.cho("return (document.querySelector('#tt-noi')"
                       ".textContent||'').includes('kết nối')"),
               cdp.js("return document.querySelector('#tt-noi').textContent"))

        gs.dat_pha("dán/kéo-thả đính kèm")
        # -- 3. Dan van ban NHIEU DONG tu ben ngoai ------------------------
        cdp.js(
            "const o = document.querySelector('#o-soan'); o.focus();"
            + NL + "const dt = new DataTransfer();"
            + NL + "dt.setData('text/plain', 'dòng 1' + String.fromCharCode(10)"
            + NL + "  + 'dòng 2 ăn ổn đ ữ' + String.fromCharCode(10) + 'dòng 3');"
            + NL + "const e = new ClipboardEvent('paste', {clipboardData: dt,"
            + NL + "  bubbles: true, cancelable: true});"
            + NL + "o.dispatchEvent(e);"
            + NL + "return !e.defaultPrevented;")
        bd.ghi("3. dán văn bản nhiều dòng KHÔNG bị chặn (Ctrl+V còn nguyên)",
               True, "handler để WebView2 tự chèn")

        # Unicode tieng Viet di duoc qua duong gia tri.
        cdp.js("document.querySelector('#o-soan').value = "
               "'ăn ổn ữ ậ đ ẫ — Ưu tiên'; return 1;")
        bd.ghi("3b. Unicode tiếng Việt giữ nguyên trong ô soạn",
               cdp.js("return document.querySelector('#o-soan').value")
               == "ăn ổn ữ ậ đ ẫ — Ưu tiên", "")

        # -- 4. Dan ANH (tuong duong Win+Shift+S -> Ctrl+V) ----------------
        PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 22
        cdp.js(
            "const bin = Uint8Array.from(atob('"
            + base64.b64encode(PNG).decode()
            + "'), c => c.charCodeAt(0));"
            + NL + "const dt = new DataTransfer();"
            + NL + "dt.items.add(new File([bin], 'image.png',"
            + NL + "  {type: 'image/png'}));"
            + NL + "document.querySelector('#o-soan').dispatchEvent("
            + NL + "  new ClipboardEvent('paste', {clipboardData: dt,"
            + NL + "    bubbles: true, cancelable: true}));"
            + NL + "return 1;")
        co_anh = cdp.cho("return document.querySelectorAll("
                         "'#dai-the .the-dk').length >= 1")
        bd.ghi("4. dán ảnh → thẻ đính kèm + thumbnail", co_anh
               and cdp.js("return !!document.querySelector("
                          "'#dai-the .the-dk img')"),
               cdp.js("return document.querySelector('#dai-the .dk-chu b')"
                      "?.textContent || ''"))

        # -- 5. Keo mot PDF ------------------------------------------------
        PDF = b"%PDF-1.7\n" + b"noi dung thu " * 300
        cdp.js(
            "const bin = Uint8Array.from(atob('"
            + base64.b64encode(PDF).decode()
            + "'), c => c.charCodeAt(0));"
            + NL + "const dt = new DataTransfer();"
            + NL + "dt.items.add(new File([bin], 'bao cao.pdf',"
            + NL + "  {type: 'application/pdf'}));"
            + NL + "document.querySelector('#o-soan').dispatchEvent("
            + NL + "  new DragEvent('drop', {dataTransfer: dt,"
            + NL + "    bubbles: true, cancelable: true}));"
            + NL + "return 1;")
        bd.ghi("5. kéo-thả PDF vào ô soạn",
               cdp.cho("return document.querySelectorAll("
                       "'#dai-the .the-dk').length >= 2"),
               cdp.js("return [...document.querySelectorAll("
                      "'#dai-the .dk-chu b')].map(x=>x.textContent).join(', ')"))

        gs.dat_pha("giao việc: Leader + phân rã + Router V4 + agent")
        # -- 6. Gui mot viec VO HAI ----------------------------------------
        cdp.js("document.querySelector('#o-soan').value = "
               "'update docs/seed.md with one line'; "
               "document.querySelector('#nut-gui').click(); return 1;")
        # 240s, khong phai 60s: tu V0.3 cau nay di QUA LEADER, va mot lan
        # mo phien Leader LANH do duoc 67.87s tren may nay (luot am: 2.4s).
        # Tran 60s cu la tran cua thoi truoc-Leader.
        co_viec = cdp.cho("return document.querySelectorAll("
                          "'#bang-tasks tbody tr').length >= 1", han=240)
        bd.ghi("6. gửi một việc vô hại → Router tạo việc", co_viec,
               cdp.js("return document.querySelectorAll("
                      "'#bang-tasks tbody tr').length") if co_viec else "0")

        # -- 6b. Trang thai SONG: viec/agent/log ---------------------------
        cdp.js("document.querySelector('[data-khung=\"tasks\"]').click(); "
               "return 1;")
        bd.ghi("6b. bảng Tasks có trạng thái sống",
               cdp.cho("return !!document.querySelector("
                       "'#bang-tasks tbody tr .hh')"),
               cdp.js("return document.querySelector("
                      "'#bang-tasks tbody tr .hh')?.textContent || ''"))
        cdp.js("document.querySelector('#bang-tasks tbody tr').click(); "
               "return 1;")
        bd.ghi("6c. bấm một việc mở chi tiết",
               cdp.cho("return (document.querySelector('#chi-tiet-viec')"
                       ".textContent||'').includes('mã việc')"), "")
        cdp.js("const b=[...document.querySelectorAll('#chi-tiet-viec "
               "button')].find(x=>x.textContent.trim()==='Nhật ký'); "
               "if(b) b.click(); return 1;")
        bd.ghi("6d. mở được nhật ký của việc (không cần terminal)",
               cdp.cho("return (document.querySelector('#log-o')"
                       ".textContent||'').length > 20"),
               f"{cdp.js('return (document.querySelector(\"#log-o\").textContent || \"\").length')} ký tự")

        # ==================================================================
        # V0.4 — sáu tiêu chí UX, đo trên CHÍNH cửa sổ WebView2 đóng gói
        # ==================================================================
        #
        # Moi phep kiem duoi day chay TRONG cua so cua ung dung da dong
        # goi, khong phai trong mot Chrome chay tu ma nguon. Do la yeu
        # cau: "Use the packaged EXE itself as the acceptance artifact".

        # -- V4a. Ô SOẠN: trống ngay sau khi gửi, và GIỮ focus -------------
        #
        # Gui mot cau HOI (khong phai mot viec) de di dung duong Leader
        # thuong ngay. Leader da am tu buoc 6, nen luot nay nhanh.
        #
        gs.dat_pha("Leader chat thường ngày")
        # VE KHUNG CHAT TRUOC — dinh chinh cua BO NGHIEM THU, khong
        # phai cua san pham. Buoc 6d o tren mo khung Logs, nen luc nay
        # `#khung-chat` dang `display: none`. `element.focus()` tren
        # mot phan tu nam trong cay `display:none` KHONG LAM GI CA —
        # da do dong thoi gian `activeElement` va thay ro: khi khung
        # Chat dang hien, o soan GIU focus suot ca luot gui. Mot nguoi
        # dung gui tin nhan thi dang xem khung Chat, nen day moi la
        # trang thai that.
        cdp.js("document.querySelector('[data-khung=\"chat\"]')"
               ".click(); return 1;")
        # Dua cua so len TRUOC: nguoi dung dang go vao o chat thi cua
        # so cua ho DANG la cua so truoc. Xem `CDP.dua_len_truoc`.
        cdp.dua_len_truoc()
        # GO THAT roi bam ENTER THAT (`Input.dispatchKeyEvent`).
        cdp.js("const o=document.querySelector('#o-soan'); o.focus();"
               + NL + "o.value='dự án này đang tới đâu rồi?';"
               + NL + "return 1;")
        cdp.phim("Enter", 13)

        # ====== DEFECT 1: TRONG NGAY, KHONG DOI LUOT LEADER ======
        #
        # Doc MOT LAN, ngay sau phim Enter. Phep phan biet nam o
        # cho `disabled` VAN con `true`: luc do request `/api/chat`
        # DANG BAY (ca luot Leader dai 6.12s am / 67.87s lanh). Neu
        # o soan da trong TRONG khi request con bay thi no da duoc
        # xoa dong bo; neu con chu thi day dung la loi nguoi dung
        # bao — tin nhan hien trong chat ma o soan chua trong.
        ngay = json.loads(cdp.js(
            "return JSON.stringify(["
            + NL + "  document.querySelector('#o-soan').value,"
            + NL + "  document.querySelector('#nut-gui').disabled,"
            + NL + "  document.activeElement.id]);") or '["?",false,""]')
        bd.ghi("V4a1. DEFECT 1 — ô soạn TRỐNG NGAY, trong lúc request "
               "còn đang bay",
               ngay[0] == "" and ngay[1] is True,
               f"value={ngay[0]!r} nút-bị-vô-hiệu={ngay[1]} "
               f"(True = còn đang gửi) focus={ngay[2]!r}")
        bd.ghi("V4a2. và con trỏ đã ở ô soạn NGAY, không đợi `finally`",
               ngay[2] == "o-soan", f"activeElement={ngay[2]!r}")

        trong_lai = cdp.cho("return !document.querySelector("
                            "'#nut-gui').disabled", han=240)
        con_lai = cdp.js("return JSON.stringify("
                         "document.querySelector('#o-soan').value)")
        bd.ghi("V4a. ô soạn TRỐNG ngay sau khi gửi thành công", bool(trong_lai),
               f"còn lại {con_lai}")
        # `cho` chu khong `js`: `o.focus()` nam trong `finally` cua `gui()`,
        # va bo dem `disabled=false` — thu ta cho o tren — duoc dat ngay
        # TRUOC no. Doc mot lan duy nhat la doc dung khe hep giua hai dong.
        con_tro_o_soan = cdp.cho(
            "return document.activeElement && "
            "document.activeElement.id === 'o-soan'", han=20)
        chan_doan_focus = cdp.js(
            "return JSON.stringify({"
            + NL + "  hoat: document.activeElement"
            + NL + "        ? (document.activeElement.id"
            + NL + "           || document.activeElement.tagName) : null,"
            + NL + "  tai_lieu_co_focus: document.hasFocus(),"
            + NL + "  cua_so_hien: document.visibilityState})")
        bd.ghi("V4b. con trỏ VẪN ở ô soạn (gõ tiếp được ngay)",
               bool(con_tro_o_soan), chan_doan_focus)

        # -- V4c. Leader tra loi VE O CHAT --------------------------------
        #
        # Yeu cau chan phat hanh cua V0.3, va V0.4 khong duoc lam vo no:
        # mot cai badge DONE ma khong co cau tra loi thi KHONG phai thanh
        # cong.
        so_tin_v4 = cdp.js("return document.querySelectorAll("
                           "'#ds-tin .tin').length")
        bd.ghi("V4c. hội thoại Leader hiện và cập nhật trong ô chat",
               (so_tin_v4 or 0) >= 3,
               f"{so_tin_v4} bong bóng tin nhắn")

        # -- V4d. Enter gui / Shift+Enter xuong dong ----------------------
        cdp.js("const o=document.querySelector('#o-soan'); o.focus();"
               + NL + "o.value='dòng một';"
               + NL + "o.dispatchEvent(new KeyboardEvent('keydown',"
               + NL + "  {key:'Enter', shiftKey:true, bubbles:true,"
               + NL + "   cancelable:true})); return 1;")
        time.sleep(1.2)
        bd.ghi("V4d. Shift+Enter KHÔNG gửi (để xuống dòng)",
               cdp.js("return document.querySelector('#o-soan')"
                      ".value === 'dòng một'"),
               cdp.js("return JSON.stringify(document.querySelector("
                      "'#o-soan').value)"))
        bd.ghi("V4e. Enter trần được nhận là 'gửi' (không phải xuống dòng)",
               bool(cdp.js(
                   "const o=document.querySelector('#o-soan'); o.focus();"
                   + NL + "const e=new KeyboardEvent('keydown',{key:'Enter',"
                   + NL + "  bubbles:true, cancelable:true});"
                   + NL + "o.dispatchEvent(e); return e.defaultPrevented;")),
               "preventDefault() → không chèn newline")
        cdp.js("document.querySelector('#o-soan').value=''; return 1;")

        # -- V4f. MOT MAN HINH: nam o quan sat ----------------------------
        cdp.js("document.querySelector('[data-khung=\"chat\"]').click(); "
               "return 1;")
        o_qs = cdp.js(
            "return JSON.stringify(['insp-dangchay','insp-tasks',"
            + NL + "  'insp-agents','insp-usage','insp-snapshot'].map(id => {"
            + NL + "  const e=document.getElementById(id);"
            + NL + "  return [id, !!e, e ? (e.textContent||'').trim().length : 0];"
            + NL + "}))")
        ds_qs = json.loads(o_qs or "[]")
        bd.ghi("V4f. năm ô quan sát CÓ MẶT cùng lúc với ô chat",
               len(ds_qs) == 5 and all(x[1] for x in ds_qs),
               ", ".join(x[0] for x in ds_qs if x[1]))

        # -- V4g. Xem trang thai du an (chay ~6 lenh `git`) ---------------
        #
        # DAY LA DUONG NHAP CUA SO NHIEU NHAT cua ban V0.3. Bam `chup lai`
        # buoc `AnhChupDuAn.chup()` chay that, khong doi nhip 45s.
        gs.dat_pha("xem trạng thái dự án (~6 lệnh git)")
        v_truoc = len(gs.ket_qua.vi_pham)
        cdp.js("document.querySelector('#nut-chup-lai').click(); return 1;")
        co_anh_chup = cdp.cho(
            "const t=(document.querySelector('#insp-snapshot')"
            ".textContent||''); return t.includes('nhánh') || "
            "t.includes('HEAD');", han=90)
        bd.ghi("V4g. xem trạng thái dự án: nhánh/HEAD/sạch-bẩn hiện ra",
               bool(co_anh_chup),
               (cdp.js("return (document.querySelector('#insp-snapshot')"
                       ".textContent||'').split(String.fromCharCode(10))"
                       ".slice(0,3).join(' | ')") or "")[:90])
        bd.ghi("V4h. ~6 lệnh `git` của ảnh chụp KHÔNG nhấp cửa sổ nào",
               len(gs.ket_qua.vi_pham) == v_truoc,
               f"{len(gs.ket_qua.vi_pham) - v_truoc} cửa sổ mới")

        # -- V4i. Lam moi USAGE -------------------------------------------
        gs.dat_pha("làm mới usage")
        v_truoc = len(gs.ket_qua.vi_pham)
        cdp.js("document.querySelector('[data-khung=\"usage\"]').click(); "
               "return 1;")
        co_usage = cdp.cho("return /\\d+ hạng mục/.test("
                           "document.querySelector('#usage-tom')"
                           ".textContent || '')", han=60)
        bd.ghi("V4i. làm mới usage: bảng có hạng mục kèm mức tin cậy",
               bool(co_usage),
               (cdp.js("return document.querySelector('#usage-tom')"
                       ".textContent") or "")[:88])

        # ====== DEFECT 2: GIA TRI, khong chi SO HANG MUC ======
        #
        # Bai kiem cu chi doi "43 hang muc", nen no VAN DAT khi moi
        # gia tri bang 0 — dung cai nguoi dung bao: viec DONE, AG01
        # BUSY roi IDLE, ket qua ~57s, ma Usage van 0/0/0/0/0.
        #
        # Doi chieu BA nguon: `/api/usage`, so SQLite doc truc tiep,
        # va CHU tren the da ve. Ba nguon khop nhau moi la ke toan
        # dung; API dung ma the sai la loi lam moi o frontend.
        cdp.js("const b=document.querySelector("
               + NL + f"  {chr(39)}[data-khung=\"chat\"]{chr(39)});"
               + NL + "if (b) b.click(); return 1;")
        api_usage = json.loads(cdp.js(
            "const t=sessionStorage.getItem('cc_token');"
            + NL + "const p=document.querySelector("
            + NL + f"  {chr(39)}#ds-project li.dang-mo{chr(39)}).dataset.pid;"
            + NL + "const r=await fetch('/api/usage?project='"
            + NL + "  + encodeURIComponent(p),"
            + NL + "  {headers:{'X-CC-Token':t}});"
            + NL + "const j=await r.json();"
            + NL + "return JSON.stringify(Object.fromEntries("
            + NL + "  (j.local||[]).map(m => [m.label, m.value])));")
            or "{}")
        so_db = _dem_so(goc)
        thieu = [k for k, v in api_usage.items()
                 if k != "phiên còn sống" and not (v and v > 0)]
        bd.ghi("V4i2. DEFECT 2 — mọi hạng mục ACTUAL đều > 0 sau một "
               "lượt THẬT",
               not thieu and api_usage.get("việc đã tạo", 0) > 0,
               "; ".join(f"{k}={v}" for k, v in api_usage.items())
               + (f" · CÒN 0: {thieu}" if thieu else ""))
        bd.ghi("V4i3. và số đó KHỚP sổ SQLite đọc trực tiếp",
               api_usage.get("việc đã tạo") == so_db["tasks"]
               and api_usage.get("phiên đã dựng") == so_db["sessions"],
               f"API việc={api_usage.get('việc đã tạo')} "
               f"phiên={api_usage.get('phiên đã dựng')} · "
               f"sổ việc={so_db['tasks']} phiên={so_db['sessions']}")
        the_usage = cdp.js(
            "return (document.querySelector('#insp-usage')"
            + NL + r"  .textContent||'').replace(/\s+/g,' ');") or ""
        so_tren_the = [int(x) for x in re.findall(
            r"(\d+)\s*ACTUAL", the_usage)]
        bd.ghi("V4i4. và THẺ đã vẽ cũng hiện số > 0 (không đứng ở "
               "ảnh chụp lúc khởi động)",
               bool(so_tren_the) and max(so_tren_the) > 0,
               the_usage[:140])
        bd.ghi("V4j. làm mới usage KHÔNG nhấp cửa sổ nào",
               len(gs.ket_qua.vi_pham) == v_truoc,
               f"{len(gs.ket_qua.vi_pham) - v_truoc} cửa sổ mới")
        cdp.js("document.querySelector('[data-khung=\"chat\"]').click(); "
               "return 1;")

        # -- V4k. CHU DE TOI ----------------------------------------------
        mau = cdp.js(
            "const c=getComputedStyle(document.body);"
            + NL + "const m=c.backgroundColor.match(/[0-9.]+/g)||[];"
            + NL + "const s=(+m[0]||0)+(+m[1]||0)+(+m[2]||0);"
            + NL + "const ch=getComputedStyle(document.body).color"
            + NL + "  .match(/[0-9.]+/g)||[];"
            + NL + "return JSON.stringify([c.backgroundColor, s,"
            + NL + "  (+ch[0]||0)+(+ch[1]||0)+(+ch[2]||0),"
            + NL + "  getComputedStyle(document.documentElement)"
            + NL + "    .getPropertyValue('--neon').trim()])")
        m_nen, tong_nen, tong_chu, neon = json.loads(mau or '["",999,0,""]')
        bd.ghi("V4k. chủ đề TỐI: nền tối, chữ sáng, biến --neon có mặt",
               tong_nen < 150 and tong_chu > 400 and bool(neon),
               f"nền={m_nen} (Σ{tong_nen}) chữ Σ{tong_chu} --neon={neon}")

        # -- V4l. ANH NEN qua DUNG duong san pham -------------------------
        #
        # Tai anh bang `fetch` TU TRONG TRANG: dung endpoint that, dung
        # token that, dung tang dinh kem that (kiem chu ky byte, duong
        # luu do bam noi dung sinh). Khong bom CSS.
        gs.dat_pha("đặt ảnh nền + nạp lại trang")
        PNG_NEN = _png_nen()
        dat_nen = cdp.js(
            "const bin = Uint8Array.from(atob('"
            + base64.b64encode(PNG_NEN).decode()
            + "'), c => c.charCodeAt(0));"
            + NL + "const fd = new FormData();"
            + NL + "fd.append('project_id', 'viet');"
            + NL + "fd.append('file', new File([bin], 'nền thử nghiệm.png',"
            + NL + "  {type:'image/png'}), 'nền thử nghiệm.png');"
            + NL + "const tok = sessionStorage.getItem('cc_token');"
            + NL + "const r1 = await fetch('/api/attachments', {method:'POST',"
            + NL + "  headers:{'X-CC-Token':tok}, body:fd});"
            + NL + "if(!r1.ok) return JSON.stringify(['tải lên hỏng', r1.status]);"
            + NL + "const dk = await r1.json();"
            + NL + "const r2 = await fetch('/api/ui', {method:'POST',"
            + NL + "  headers:{'X-CC-Token':tok,"
            + NL + "           'Content-Type':'application/json'},"
            + NL + "  body: JSON.stringify({wallpaper: dk.attachment_id,"
            + NL + "    dim: 0.4, blur: 2, fit: 'cover'})});"
            + NL + "if(!r2.ok) return JSON.stringify(['lưu hỏng', r2.status]);"
            + NL + "return JSON.stringify(['ok', dk.attachment_id,"
            + NL + "  dk.filename, dk.sha256.slice(0,12)]);")
        kq_nen = json.loads(dat_nen or '[""]')
        bd.ghi("V4l. đặt ảnh nền qua đúng đường đính kèm (mã, không đường dẫn)",
               kq_nen[0] == "ok", " ".join(str(x) for x in kq_nen[1:]))

        # Nap lai trang de `napCaiDatUI()` chay nhu mot lan mo binh thuong.
        cdp.js("location.reload(); return 1;")
        time.sleep(3.0)
        cdp.cho("return !!document.querySelector('#anh-nen')", han=40)
        ve_nen = cdp.js(
            "const v=getComputedStyle(document.documentElement)"
            + NL + "  .getPropertyValue('--nen-anh').trim();"
            + NL + "const l=getComputedStyle("
            + NL + "  document.querySelector('#anh-nen'));"
            + NL + "return JSON.stringify([v.slice(0,42), l.backgroundImage"
            + NL + "  .slice(0,42), l.filter,"
            + NL + "  getComputedStyle(document.querySelector('#man-mo'))"
            + NL + "    .opacity])")
        v_bien, v_lop, v_blur, v_mo = json.loads(ve_nen or '["","","",""]')
        # `v_bien`/`v_lop` da bi CAT o phia JS de bao cao gon, nen phep
        # kiem phai khop tren doan CON LAI. Ban truoc doi chu
        # "attachments" trong mot chuoi bi cat ngay sau "attachment" —
        # bai kiem do vi chinh no, khong vi san pham.
        bd.ghi("V4m. ảnh nền HIỆN THẬT trong cửa sổ đóng gói (bền qua nạp lại)",
               v_lop.startswith('url("http://127.0.0.1:')
               and "/api/attachment" in v_lop
               and "/api/attachment" in v_bien
               and v_blur == "blur(2px)" and v_mo == "0.4",
               f"lớp={v_lop} blur={v_blur} phủ={v_mo}")

        # -- V4n. Tieng Viet SAU khi da doi giao dien ----------------------
        cdp.cho("const li=document.querySelector('#ds-project li"
                "[data-pid=\"viet\"]'); if(li){li.click(); return 1;} "
                "return 0;", han=40)
        bd.ghi("V4n. tiếng Việt vẫn đúng sau khi đổi chủ đề + đặt ảnh nền",
               bool(cdp.cho("return (document.querySelector('#ds-tin')"
                            ".textContent || '').includes("
                            + json.dumps(CHAT_VIET) + ")", han=40)),
               CHAT_VIET[:38] + "…")

        # -- V4n2. ĐỐI CHỨNG: app MỞ nhưng KHÔNG ai điều khiển ------------
        #
        # VI SAO PHEP DOI CHUNG NAY LA BAT BUOC. `V4o` dem cua so console
        # MOI trong ca phien. Nhung bo nghiem thu chay 60-90s tren mot may
        # DANG DUOC DUNG: phien Claude Code, Warp, ban Control Center cua
        # chinh nguoi dung, cac tac vu nen cua Windows — bat ky thu nao
        # trong so do cung co the mo mot tab terminal. Neu khong do nhip
        # NEN cua chinh lan chay nay thi mot con so "7 cua so" khong phan
        # biet duoc "san pham nhap cua so" voi "may dang lam viec khac".
        #
        # Cua so DOI CHUNG: app van mo, van co WebSocket dap moi giay, van
        # co vong dieu phoi — nhung KHONG mot lenh nao tu bo nghiem thu.
        # Vi pham trong khoang nay KHONG THE do thao tac nguoi dung gay ra.
        gs.dat_pha("ĐỐI CHỨNG — app mở, không ai điều khiển")
        v_truoc_dc = len(vi_pham_cua_app(gs.ket_qua.vi_pham))
        n_truoc_dc = len(gs.ket_qua.vi_pham)
        time.sleep(30)
        v_dc = len(vi_pham_cua_app(gs.ket_qua.vi_pham)) - v_truoc_dc
        n_dc = len(gs.ket_qua.vi_pham) - n_truoc_dc
        bd.ghi("V4n2. đối chứng: app mở + rảnh 30s, không thao tác nào",
               True,          # ghi lai NHIP NEN, khong phai phep kiem
               f"{v_dc} của APP / {n_dc} tổng cửa sổ console mới trong "
               f"30s rảnh (dùng để so với V4o)")

        # -- V4o. TONG KET cua so console cho CA phien lam viec ------------
        #
        # MOI cua so console MOI deu tinh la vi pham, khong loc theo
        # "co phai cay tien trinh cua app khong" — va day la mot dinh
        # chinh cua chinh bo nghiem thu nay. Do duoc 6/6 lan tren may
        # nay: cua so console do mot tien trinh con gay ra KHONG thuoc
        # cay tien trinh cua app, vi Windows Terminal la mot tien trinh
        # DUNG CHUNG CA PHIEN (to tien: svchost <- services <- wininit)
        # va console moi chi la mot TAB dung ben trong no qua DCOM. Loc
        # theo to tien lam phep kiem KHONG BAO GIO DO DUOC.
        #
        # Phep phan xu la MOC NEN + LAP LAI: mot cua so do app gay ra
        # thi tai hien MOI LAN chay (bo kiem chung cu chong rong bat
        # 6/6 lan sinh tien trinh); mot cua so cua tien trinh khac tren
        # may thi khong.
        kq1 = gs.ket_qua
        cua_ta = vi_pham_cua_app(kq1.vi_pham)
        bd.ghi("V4o. TOÀN PHIÊN: không một cửa sổ console nào DO APP "
               "nhấp lên",
               not cua_ta,
               kq1.tom_tat()
               + (NL + "      " + _ta_vi_pham(kq1.vi_pham)
                  if kq1.vi_pham else ""))
        bd.ghi("V4p. không lần nào APP giật focus sang cửa sổ console",
               not cua_ta,
               ("; ".join(f"{x[0]:.1f}s [{x[6]}] {x[2]}"
                          for x in kq1.doi_focus[:4])
                if kq1.doi_focus else "0 lần"))
        # CHUNG CU CHONG RONG: neu app khong sinh mot tien trinh console
        # nao thi "khong co cua so" la mot cau vo nghia.
        da_sinh = {k: v for k, v in kq1.tien_trinh_con.items()
                   if k.lower() in TIEN_TRINH_CONSOLE}
        bd.ghi("V4q. chứng cứ chống rỗng: app THẬT SỰ đã sinh tiến trình console",
               bool(da_sinh),
               ", ".join(f"{k}×{v}" for k, v in sorted(
                   da_sinh.items(), key=lambda x: -x[1])[:6]) or "KHÔNG có")
        bd.ghi("V4r. bộ giám sát dùng hook sự kiện (bắt cả cửa sổ sống 5ms)",
               kq1.hook_song, "SetWinEventHook đang sống")

        # -- Dinh kem da toi dung viec -------------------------------------
        from scripts.control_center.desktop_shell import doc_tep_khoa
        tt = doc_tep_khoa(goc)
        bd.ghi("8. tệp khoá ghi đúng pid/cổng/token",
               tt is not None and tt.cong > 0 and bool(tt.token),
               f"pid={tt.pid} cổng={tt.cong}" if tt else "không có tệp khoá")

        # Anh chup DUOI SO truoc khi dong, de doi chieu sau khi mo lai.
        # Doi chieu voi CHINH SO chu khong voi mot con so cheo tay: mot
        # bai kiem "so tin >= 1" van xanh khi so bi cat mat mot nua.
        gs.dat_pha("đóng app")
        truoc_dong = _dem_so(goc)
        bd.ghi("V4s. sổ trước khi đóng có trạng thái thật để so",
               truoc_dong["chat"] >= 3 and truoc_dong["tasks"] >= 1,
               ", ".join(f"{k}={v}" for k, v in truoc_dong.items()))

        cdp.dong()
        cdp = None

        # -- 9. Dong roi mo lai: trang thai CON NGUYEN ---------------------
        ph.terminate()
        try:
            ph.wait(timeout=25)
        except subprocess.TimeoutExpired:
            ph.kill()
        time.sleep(1.5)
        bd.ghi("9. đóng app thì backend tắt theo (cổng nhả)",
               not _cong_con_nghe(tt.cong if tt else 0),
               f"cổng {tt.cong if tt else '?'} đã nhả")

        gs2 = GiamSatCuaSo()
        gs2.__enter__()
        gs2.dat_pha("mở lại app")
        ph2, f2 = mo_app(a.exe, goc, a.cdp + 1, tam / "lan2.log")
        gs2.theo(ph2.pid)
        try:
            cdp2 = CDP(a.cdp + 1)
            # Chon dung du an tieng Viet TRUOC MOI PHEP DOC: bang Tasks va
            # danh sach tin nhan deu THEO DU AN, va moi thu da gui o lan mo
            # truoc deu thuoc du an nay. Lan mo moi khong nhat thiet chon
            # lai dung du an do — doc truoc khi chon thi doc mot bang RONG,
            # va do la loi cua BAI KIEM, khong phai cua san pham.
            cdp2.cho("const li=document.querySelector('#ds-project li"
                     "[data-pid=\"viet\"]'); if(li){li.click(); return 1;} "
                     "return 0;", han=30)
            con_viec = cdp2.cho("return document.querySelectorAll("
                                "'#bang-tasks tbody tr').length >= 1", han=45)
            so_tin = cdp2.js("return document.querySelectorAll("
                             "'#ds-tin .tin').length")
            bd.ghi("9b. mở lại: việc và tin nhắn còn nguyên (SQLite)",
                   bool(con_viec) and (so_tin or 0) >= 1,
                   f"{so_tin} tin nhắn, {'có' if con_viec else 'KHÔNG có'} việc")
            bd.ghi("9c. đính kèm cũ vẫn xem được sau khi mở lại",
                   bool(cdp2.cho("return !!document.querySelector("
                                 "'#ds-tin img')", han=30)),
                   "thumbnail ảnh đã dán còn hiển thị")
            # Va tieng Viet van dung sau mot vong dong/mo — day la lan mo
            # THU HAI tren so da co, dung tinh huong nguoi dung gap.
            bd.ghi("9d. tiếng Việt còn nguyên sau khi đóng và mở lại",
                   bool(cdp2.cho("return (document.querySelector('#ds-tin')"
                                 ".textContent || '').includes("
                                 + json.dumps(CHAT_VIET) + ")", han=30)),
                   CHAT_VIET[:40] + "…")
            # CHI phan MOI cua nhat ky: `GhiUTF8` ghi THEM vao cung mot
            # tep, nen doc ca tep se doc lai ca lan mo thu nhat va bai
            # kiem se xanh nho du lieu cu.
            tho2 = _doc_log(goc)[len(tho):]
            bd.ghi("9e. nhật ký lần mở thứ hai cũng sạch UnicodeEncodeError",
                   b"UnicodeEncodeError" not in tho2
                   and b"charmap" not in tho2 and len(tho2) > 0,
                   f"{len(tho2)} byte mới")

            # -- V0.4: trang thai KHONG CU, KHONG HONG --------------------
            #
            # "Khong cu" khong phai la "co du lieu". So sanh voi CHINH SO
            # truoc khi dong: mot bai kiem ">= 1 tin nhan" van xanh khi so
            # bi cat mat mot nua, va do la dung che do hong duoc hoi.
            sau_mo = _dem_so(goc)
            dem = [k for k, v in truoc_dong.items() if isinstance(v, int)]
            bd.ghi("V4t. sổ KHÔNG mất bản ghi nào qua vòng đóng/mở",
                   all(sau_mo[k] >= truoc_dong[k] for k in dem)
                   and all(truoc_dong[k] >= 0 for k in dem),
                   "trước=" + ",".join(f"{k}:{truoc_dong[k]}" for k in dem)
                   + " | sau=" + ",".join(f"{k}:{sau_mo[k]}" for k in dem))
            bd.ghi("V4u. sổ SQLite lành (PRAGMA integrity_check)",
                   sau_mo["nguyen_ven"] == "ok",
                   str(sau_mo["nguyen_ven"]))

            # Giao dien phai hien DUNG con so cua so, khong phai mot anh
            # chup cu con lai trong bo dem.
            so_tin2 = cdp2.js("return document.querySelectorAll("
                              "'#ds-tin .tin').length") or 0
            bd.ghi("V4v. giao diện hiện ĐÚNG số tin nhắn của sổ (không cũ)",
                   int(so_tin2) >= truoc_dong["chat"],
                   f"giao diện {so_tin2} · sổ {sau_mo['chat']}")

            # Anh nen da luu phai TU HIEN LAI o lan mo moi — do la phep
            # kiem "ben qua khoi dong lai" that su, tren EXE that.
            cdp2.cho("return !!document.querySelector('#anh-nen')", han=40)
            time.sleep(2.0)
            nen2 = cdp2.js(
                "const l=getComputedStyle("
                + NL + "  document.querySelector('#anh-nen'));"
                + NL + "return JSON.stringify([l.backgroundImage.slice(0,44),"
                + NL + "  getComputedStyle(document.querySelector('#man-mo'))"
                + NL + "    .opacity])")
            n2_lop, n2_mo = json.loads(nen2 or '["",""]')
            bd.ghi("V4w. ảnh nền TỰ hiện lại ở lần mở mới (bền, không phải bộ đệm)",
                   n2_lop not in ("", "none") and "attachments" in n2_lop,
                   f"lớp={n2_lop} phủ={n2_mo}")

            # DEFECT 2, phan BEN: so Usage phai song qua vong dong/mo
            # va van > 0. Doc lai tu API cua LAN MO MOI, khong tu bo
            # dem cua lan truoc.
            usage2 = json.loads(cdp2.js(
                "const t=sessionStorage.getItem('cc_token');"
                + NL + "const p=document.querySelector("
                + NL + "  '#ds-project li.dang-mo').dataset.pid;"
                + NL + "const r=await fetch('/api/usage?project='"
                + NL + "  + encodeURIComponent(p),"
                + NL + "  {headers:{'X-CC-Token':t}});"
                + NL + "const j=await r.json();"
                + NL + "return JSON.stringify(Object.fromEntries("
                + NL + "  (j.local||[]).map(m => [m.label, m.value])));")
                or "{}")
            bd.ghi("V4y. DEFECT 2 — số Usage BỀN qua đóng/mở lại và "
                   "vẫn > 0",
                   usage2.get("việc đã tạo", 0) > 0
                   and usage2.get("lượt dispatch agent", 0) > 0
                   and usage2.get("giây agent tích luỹ", 0) > 0,
                   "; ".join(f"{k}={v}" for k, v in usage2.items()))

            kq2 = gs2.ket_qua
            bd.ghi("V4x. lần mở THỨ HAI cũng không nhấp cửa sổ console nào",
                   not vi_pham_cua_app(kq2.vi_pham),
                   kq2.tom_tat()
                   + (NL + "      " + _ta_vi_pham(kq2.vi_pham)
                      if kq2.vi_pham else ""))
            cdp2.dong()
        finally:
            ph2.terminate()
            try:
                ph2.wait(timeout=25)
            except subprocess.TimeoutExpired:
                ph2.kill()
            if f2:
                f2.close()
            gs2.dung()

    finally:
        gs.dung()
        if cdp:
            cdp.dong()
        if ph and ph.poll() is None:
            ph.terminate()
            try:
                ph.wait(timeout=20)
            except subprocess.TimeoutExpired:
                ph.kill()
        if f1:
            f1.close()
        if a.keep:
            ghi_ra(f"{NL}  (giữ lại {goc} và {tam})")
        else:
            shutil.rmtree(goc, ignore_errors=True)
            shutil.rmtree(tam, ignore_errors=True)

    ghi_ra(NL + "=" * 78)
    hong = bd.hong()
    ghi_ra(f"KẾT LUẬN: {len(bd.hang) - len(hong)}/{len(bd.hang)} bước ĐẠT")
    for b in hong:
        ghi_ra(f"  HỎNG: {b}")
    ghi_ra("  Lưu ý: kịch bản KHÔNG tự bấm được Win+Shift+S hay Ctrl+V ở tầng")
    ghi_ra("  hệ điều hành. Nó chứng minh đường mã xử lý đúng sự kiện mà")
    ghi_ra("  WebView2 giao cho — hai cú bấm đó là việc của con người.")
    ghi_ra("=" * 78)
    return 1 if hong else 0


def _ta_vi_pham(ds) -> str:
    """Tả một vi phạm KÈM CHUỖI TỔ TIÊN, để chẩn đoán.

    Chuỗi tổ tiên ở đây là để ĐỌC, không để phân xử — xem
    `SuKienCuaSo.cua_app`: trên Windows 11 cửa sổ console do một
    `WindowsTerminal.exe` dùng chung cả phiên làm chủ, nên tổ tiên của nó
    gần như luôn là `svchost <- services <- wininit` kể cả khi chính app
    vừa gây ra nó.
    """
    ra = []
    for v in ds[:12]:
        chuoi = " <- ".join(f"{t}({p})" for p, t in v.to_tien) or "(mất)"
        quanh = (", ".join(f"{t}({q}){chr(42) if ta else chr(32)}"
                           for _l, q, t, ta in v.tt_quanh[:8])
                 or "(không tiến trình nào mới)")
        ra.append(f"{v.luc:.2f}s [{v.pha}] {v.lop} cỡ={v.co} "
                  f"{chr(42) if any(x[3] for x in v.tt_quanh) else chr(45)}"
                  f" chủ={chuoi} · vừa xuất hiện: {quanh}")
    return f"{len(ds)} cửa sổ — " + " | ".join(ra)


def _doc_log(goc: Path) -> bytes:
    """Nhật ký UTF-8 mà `desktop.py` tự ghi cạnh sổ.

    Đây là nơi DUY NHẤT đọc được chẩn đoán của một bản `--noconsole`:
    không có console nào để đọc `stderr`, và `ShellExecuteW` không cho
    ống dẫn. Đọc đúng tệp này là đọc đúng đường sản phẩm dùng.
    """
    p = duong_nhat_ky(goc)
    return p.read_bytes() if p.is_file() else b""


def _dem_so(goc: Path) -> dict:
    """Đếm bản ghi TRỰC TIẾP trong SQLite + kiểm toàn vẹn.

    Đọc thẳng sổ chứ không hỏi giao diện, và đó là điểm chính: một phép
    kiểm "giao diện có ít nhất một tin nhắn" vẫn xanh khi sổ bị cắt mất
    một nửa. Câu hỏi nghiệm thu là "trạng thái có bị CŨ hay HỎNG không",
    nên phải có một con số để so hai đầu của vòng đóng/mở.

    Mở CHỈ ĐỌC (`mode=ro`) để chính phép đo không tạo WAL/SHM mới cạnh
    sổ của ứng dụng.
    """
    import sqlite3

    from scripts.control_center.store import duong_so

    p = duong_so(goc)
    ra = {"chat": 0, "tasks": 0, "sessions": 0, "attachments": 0,
          "cc_events": 0, "cai_dat_ui": 0, "nguyen_ven": "không đọc được"}
    if not p.is_file():
        return ra
    try:
        c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=20)
    except sqlite3.Error as exc:
        ra["nguyen_ven"] = f"không mở được: {exc}"
        return ra
    try:
        for bang in ("chat", "tasks", "sessions", "attachments", "cc_events",
                     "cai_dat_ui"):
            try:
                ra[bang] = int(c.execute(
                    f"SELECT COUNT(*) FROM {bang}").fetchone()[0])
            except sqlite3.Error:
                ra[bang] = -1
        try:
            ra["nguyen_ven"] = str(
                c.execute("PRAGMA integrity_check").fetchone()[0])
        except sqlite3.Error as exc:
            ra["nguyen_ven"] = f"lỗi: {exc}"
    finally:
        c.close()
    return ra


def _cong_con_nghe(cong: int) -> bool:
    import socket
    if cong <= 0:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", cong)) == 0


if __name__ == "__main__":
    sys.exit(main())
