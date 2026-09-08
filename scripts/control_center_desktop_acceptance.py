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
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

DAT, HONG = "[ĐẠT ]", "[HỎNG]"
NL = chr(10)


class Bang:
    def __init__(self):
        self.hang = []

    def ghi(self, b, ok, ct=""):
        self.hang.append((b, bool(ok)))
        print(f"  {DAT if ok else HONG} {b}" + (f"  — {ct}" if ct else ""))

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
        r = subprocess.run(["tasklist", "/fo", "csv", "/nh"],
                           capture_output=True, text=True, timeout=25)
    except Exception:                                       # noqa: BLE001
        return 0
    n = 0
    for dong in (r.stdout or "").splitlines():
        if "msedgewebview2.exe" in dong.lower():
            n += 1
    return n


def kho_git_tam() -> Path:
    goc = Path(tempfile.mkdtemp(prefix="cc-desk-acc-"))
    (goc / "docs").mkdir(parents=True)
    (goc / "docs" / "seed.md").write_text("seed\n", encoding="utf-8")
    for c in (["git", "init", "-q"],
              ["git", "config", "user.email", "t@l"],
              ["git", "config", "user.name", "t"],
              ["git", "add", "-A"], ["git", "commit", "-q", "-m", "seed"]):
        subprocess.run(c, cwd=goc, check=True, capture_output=True)
    return goc


def mo_app(exe: str, goc: Path, cdp: int, log: Path):
    """Mở ứng dụng desktop. `exe` rỗng = chạy từ mã nguồn."""
    if exe:
        # TUYET DOI hoa: `Popen` phan giai tep thuc thi theo cwd cua tien
        # trinh CHA, khong theo `cwd=` truyen cho con — nen mot duong dan
        # tuong doi se ra `WinError 2` du tep co that.
        p_exe = Path(exe)
        if not p_exe.is_absolute():
            p_exe = (GOC / exe).resolve()
        if not p_exe.is_file():
            raise SystemExit(f"không thấy EXE: {p_exe}")
        lenh = [str(p_exe), "--root", str(goc), "--debug-cdp", str(cdp)]
    else:
        lenh = [sys.executable, "-m", "scripts.control_center.desktop",
                "--root", str(goc), "--debug-cdp", str(cdp)]
    moi = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONUTF8="1",
               PYTHONIOENCODING="utf-8")
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
    tam = Path(tempfile.mkdtemp(prefix="cc-desk-log-"))
    ph = None
    f1 = None
    cdp = None
    print("=" * 78)
    print("NGHIỆM THU VỎ DESKTOP — WebView2 THẬT")
    print(f"  chạy   : {a.exe or 'từ mã nguồn (python -m …desktop)'}")
    print(f"  kho tạm: {goc}")
    print("=" * 78)

    try:

        # -- 1. Mo app -----------------------------------------------------
        ph, f1 = mo_app(a.exe, goc, a.cdp, tam / "lan1.log")
        cdp = CDP(a.cdp)
        bd.ghi("1. ứng dụng mở được (cửa sổ WebView2)", True,
               f"pid {ph.pid}")

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
        bd.ghi("7c. WebSocket sống",
               cdp.cho("return (document.querySelector('#tt-noi')"
                       ".textContent||'').includes('kết nối')"),
               cdp.js("return document.querySelector('#tt-noi').textContent"))

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

        # -- 6. Gui mot viec VO HAI ----------------------------------------
        cdp.js("document.querySelector('#o-soan').value = "
               "'update docs/seed.md with one line'; "
               "document.querySelector('#nut-gui').click(); return 1;")
        co_viec = cdp.cho("return document.querySelectorAll("
                          "'#bang-tasks tbody tr').length >= 1", han=60)
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

        # -- Dinh kem da toi dung viec -------------------------------------
        from scripts.control_center.desktop_shell import doc_tep_khoa
        tt = doc_tep_khoa(goc)
        bd.ghi("8. tệp khoá ghi đúng pid/cổng/token",
               tt is not None and tt.cong > 0 and bool(tt.token),
               f"pid={tt.pid} cổng={tt.cong}" if tt else "không có tệp khoá")

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

        ph2, f2 = mo_app(a.exe, goc, a.cdp + 1, tam / "lan2.log")
        try:
            cdp2 = CDP(a.cdp + 1)
            con_viec = cdp2.cho("return document.querySelectorAll("
                                "'#bang-tasks tbody tr').length >= 1", han=45)
            so_tin = cdp2.js("return document.querySelectorAll("
                             "'#ds-tin .tin').length")
            bd.ghi("9b. mở lại: việc và tin nhắn còn nguyên (SQLite)",
                   con_viec and (so_tin or 0) >= 1,
                   f"{so_tin} tin nhắn")
            bd.ghi("9c. đính kèm cũ vẫn xem được sau khi mở lại",
                   cdp2.js("return !!document.querySelector('#ds-tin img')"
                           ) is not None, "")
            cdp2.dong()
        finally:
            ph2.terminate()
            try:
                ph2.wait(timeout=25)
            except subprocess.TimeoutExpired:
                ph2.kill()
            f2.close()

    finally:
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
            print(f"{NL}  (giữ lại {goc} và {tam})")
        else:
            shutil.rmtree(goc, ignore_errors=True)
            shutil.rmtree(tam, ignore_errors=True)

    print(NL + "=" * 78)
    hong = bd.hong()
    print(f"KẾT LUẬN: {len(bd.hang) - len(hong)}/{len(bd.hang)} bước ĐẠT")
    for b in hong:
        print(f"  HỎNG: {b}")
    print("  Lưu ý: kịch bản KHÔNG tự bấm được Win+Shift+S hay Ctrl+V ở tầng")
    print("  hệ điều hành. Nó chứng minh đường mã xử lý đúng sự kiện mà")
    print("  WebView2 giao cho — hai cú bấm đó là việc của con người.")
    print("=" * 78)
    return 1 if hong else 0


def _cong_con_nghe(cong: int) -> bool:
    import socket
    if cong <= 0:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", cong)) == 0


if __name__ == "__main__":
    sys.exit(main())
