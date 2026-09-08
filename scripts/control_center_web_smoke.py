"""Smoke THẬT của giao diện web: Chrome cục bộ + CDP, không mô phỏng.

Vì sao tệp này tồn tại và vì sao nó dùng CDP:

Bộ kiểm `scripts/tests/test_control_center_webapi.py` gọi ASGI app trực
tiếp — nó chứng minh ranh giới an toàn của server, nhưng **không chạy một
dòng JavaScript nào**. Còn phần dễ sai nhất của một frontend web lại nằm ở
đó: xử lý `paste`, `drop`, và việc không cướp Ctrl+V.

Nên kịch bản này khởi động một **Chrome THẬT trên máy này** (headless mới),
nối vào bằng **DevTools Protocol**, rồi bắn những sự kiện mà trình duyệt
bắn khi người dùng dán/thả tệp — `ClipboardEvent('paste')` và
`DragEvent('drop')` với `DataTransfer` mang `File` thật. Sau đó đối chiếu
với server: đúng số tệp, đúng `sha256`, đúng byte.

NÓI THẲNG VỀ GIỚI HẠN: kịch bản không tự bấm được **Win+Shift+S** (Snipping
Tool đòi người kéo chuột chọn vùng), và cũng không tự bấm được **Ctrl+V**
của hệ điều hành để trình duyệt tự đọc clipboard hệ thống. Thứ nó chứng
minh là *mã của ta* xử lý đúng sự kiện dán mà trình duyệt giao cho — không
phải là chuỗi phím Windows. Bước đó cần một cú bấm của con người; xem
`--cho-nguoi` để làm nốt.

    python scripts/control_center_web_smoke.py
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

CHROME = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Users\%s\AppData\Local\Google\Chrome\Application\chrome.exe"
    % os.environ.get("USERNAME", ""),
]
DAT, HONG = "[ĐẠT ]", "[HỎNG]"


class Bang:
    def __init__(self):
        self.hang = []

    def ghi(self, b, ok, ct=""):
        self.hang.append(ok)
        print(f"  {DAT if ok else HONG} {b}" + (f"  — {ct}" if ct else ""))

    def hong(self):
        return sum(1 for x in self.hang if not x)


def tim_chrome() -> str:
    for p in CHROME:
        if Path(p).is_file():
            return p
    raise SystemExit("không tìm thấy chrome.exe trên máy này")


def cong_rong() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class CDP:
    """Nói chuyện với Chrome bằng DevTools Protocol. Đủ dùng, không hơn."""

    def __init__(self, ws_url: str):
        from websockets.sync.client import connect
        self.ws = connect(ws_url, max_size=32 * 1024 * 1024)
        self.n = 0

    def goi(self, method: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method,
                                 "params": params}))
        while True:
            goi = json.loads(self.ws.recv(timeout=30))
            if goi.get("id") == self.n:
                if "error" in goi:
                    raise RuntimeError(goi["error"])
                return goi.get("result", {})

    def js(self, ma: str):
        """Bọc mọi đoạn trong IIFE.

        `Runtime.evaluate` chạy trong CÙNG một scope toàn cục cho mọi lần
        gọi, nên `const dt` ở đoạn thứ hai sẽ đụng `const dt` của đoạn thứ
        nhất và ném `SyntaxError: Identifier 'dt' has already been
        declared`. Bọc IIFE thì mỗi đoạn có scope riêng, và cũng cho phép
        `return` bên trong.
        """
        # Boc trong IIFE de moi doan co scope RIENG. Mot doan CHI LA
        # BIEU THUC (khong `;`, khong xuong dong) duoc them `return`
        # tu dong — neu khong, IIFE tra `undefined` va moi phep kiem
        # se so `None` voi ky vong roi bao hong ma khong noi vi sao.
        t = ma.strip()
        if "return" not in t and ";" not in t and chr(10) not in t:
            t = "return (" + t + ")"
        boc = "(async () => {" + chr(10) + t + chr(10) + "})()"
        r = self.goi("Runtime.evaluate", expression=boc, awaitPromise=True,
                     returnByValue=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(json.dumps(r["exceptionDetails"])[:400])
        return r.get("result", {}).get("value")

    def dong(self):
        try:
            self.ws.close()
        except Exception:                                   # noqa: BLE001
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)

    from scripts.control_center.bootstrap import khoi_tao
    from scripts.control_center.engine import ControlCenter
    from scripts.control_center.model import Project
    from scripts.control_center.webapi import PhienWeb, dung_app
    import uvicorn

    bd = Bang()
    kho = Path(tempfile.mkdtemp(prefix="cc-websmoke-"))
    (kho / "docs").mkdir(parents=True)
    (kho / "docs" / "seed.md").write_text("seed\n", encoding="utf-8")
    for c in (["git", "init", "-q"],
              ["git", "config", "user.email", "t@l"],
              ["git", "config", "user.name", "t"],
              ["git", "add", "-A"], ["git", "commit", "-q", "-m", "seed"]):
        subprocess.run(c, cwd=kho, check=True, capture_output=True)

    cc = ControlCenter(root=kho, probe=False)
    khoi_tao(cc.store, root=kho)
    cc.them_project(Project(project_id="p", name="Duan", repo_path=str(kho)))
    cong = cong_rong()
    phien = PhienWeb(cc, token="TOK-WEBSMOKE", cong=cong)
    sv = uvicorn.Server(uvicorn.Config(dung_app(phien), host="127.0.0.1",
                                       port=cong, log_level="error",
                                       access_log=False))
    th = threading.Thread(target=sv.run, daemon=True)
    th.start()
    for _ in range(200):
        if sv.started:
            break
        time.sleep(0.05)

    print("=" * 76)
    print("SMOKE GIAO DIỆN WEB — Chrome THẬT trên máy này, qua CDP")
    print(f"server: http://127.0.0.1:{cong}  (started={sv.started})")
    print("=" * 76)

    cong_cdp = cong_rong()
    prof = Path(tempfile.mkdtemp(prefix="cc-chromeprof-"))
    ch = subprocess.Popen(
        [tim_chrome(), "--headless=new", "--disable-gpu", "--no-first-run",
         "--no-default-browser-check", f"--user-data-dir={prof}",
         f"--remote-debugging-port={cong_cdp}",
         f"http://127.0.0.1:{cong}/?t={phien.token}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cdp = None
    try:
        ws_url = ""
        het = time.time() + 30
        while time.time() < het and not ws_url:
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{cong_cdp}/json/list",
                        timeout=2) as f:
                    for t in json.load(f):
                        if t.get("type") == "page" and t.get(
                                "webSocketDebuggerUrl"):
                            ws_url = t["webSocketDebuggerUrl"]
                            break
            except Exception:                               # noqa: BLE001
                pass
            if not ws_url:
                time.sleep(0.4)
        bd.ghi("1. Chrome cục bộ mở được trang", bool(ws_url),
               "CDP đã nối" if ws_url else "không nối được CDP")
        if not ws_url:
            raise SystemExit(1)

        cdp = CDP(ws_url)
        cdp.goi("Runtime.enable")
        cdp.goi("Page.enable")

        # Doi frontend nap trang thai xong.
        for _ in range(60):
            if cdp.js("!!document.querySelector('#ds-project li')"):
                break
            time.sleep(0.25)

        du_an = cdp.js("[...document.querySelectorAll('#ds-project li')]"
                       ".map(x=>x.dataset.pid)")
        bd.ghi("2. sidebar liệt kê dự án (state qua HTTP)",
               bool(du_an) and "p" in du_an, f"{du_an}")
        bd.ghi("3. token đã bị XOÁ khỏi URL",
               "t=" not in (cdp.js("location.search") or ""),
               f"search={cdp.js('location.search')!r}")
        bd.ghi("4. WebSocket nối được (trạng thái sống)",
               "kết nối" in (cdp.js("document.querySelector('#tt-noi')"
                                    ".textContent") or ""),
               cdp.js("document.querySelector('#tt-noi').textContent"))

        # -- DAN VAN BAN NHIEU DONG: Ctrl+V phai KHONG bi cuop -------------
        cdp.js("""
          const o = document.querySelector('#o-soan');
          o.focus();
          const dt = new DataTransfer();
          dt.setData('text/plain', 'dòng 1\\ndòng 2\\ndòng 3 ăn ổn đ');
          o.dispatchEvent(new ClipboardEvent('paste',
            {clipboardData: dt, bubbles: true, cancelable: true}));
          return 'xong';
        """)
        time.sleep(0.4)
        # `ClipboardEvent` tong hop KHONG tu chen van ban (trinh duyet chi
        # chen o duong that), nen kiem dieu QUAN TRONG: handler cua ta
        # KHONG `preventDefault()` khi chi co van ban.
        bd.ghi("5. dán văn bản thuần KHÔNG bị handler chặn",
               cdp.js("""return (() => {
                 const o = document.querySelector('#o-soan');
                 const dt = new DataTransfer();
                 dt.setData('text/plain', 'chi la van ban');
                 const e = new ClipboardEvent('paste',
                   {clipboardData: dt, bubbles: true, cancelable: true});
                 o.dispatchEvent(e);
                 return !e.defaultPrevented;
               })()"""),
               "handler để trình duyệt tự chèn — đúng")

        # -- DAN MOT ANH (nhu Win+Shift+S -> Ctrl+V) -----------------------
        PNG = (b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 24)
        b64 = base64.b64encode(PNG).decode()
        cdp.js(f"""
          const bin = Uint8Array.from(atob('{b64}'), c => c.charCodeAt(0));
          const f = new File([bin], 'image.png', {{type: 'image/png'}});
          const dt = new DataTransfer();
          dt.items.add(f);
          const o = document.querySelector('#o-soan');
          o.focus();
          o.dispatchEvent(new ClipboardEvent('paste',
            {{clipboardData: dt, bubbles: true, cancelable: true}}));
          return 'xong';
        """)
        for _ in range(80):
            if cdp.js("document.querySelectorAll('#dai-the .the-dk').length"):
                break
            time.sleep(0.25)
        n = cdp.js("document.querySelectorAll('#dai-the .the-dk').length")
        bd.ghi("6. dán ẢNH → thẻ đính kèm hiện trong dải", n == 1,
               f"{n} thẻ")
        bd.ghi("7. thumbnail thật (thẻ có <img> trỏ /api/.../blob)",
               bool(cdp.js("!!document.querySelector('#dai-the .the-dk img')")),
               cdp.js("(document.querySelector('#dai-the .the-dk img')||{})"
                      ".getAttribute?.('src') || ''")[:52] + "…")

        ds = cc.dinh_kem.cua_project("p")
        anh = [x for x in ds if x.media_type == "image"]
        bd.ghi("8. server nhận đúng byte (sha256 khớp)",
               bool(anh) and anh[0].sha256 == hashlib.sha256(PNG).hexdigest(),
               f"{anh[0].sha256[:16]}… · {anh[0].size_bytes} byte"
               if anh else "không có ảnh nào ở server")

        # -- KEO-THA mot PDF va mot tep MA NGUON ---------------------------
        PDF = b"%PDF-1.7\n" + b"noi dung " * 200
        MA = b"def f():\n    return 1\n"
        cdp.js(f"""
          const mk = (b64, ten, mime) => new File(
            [Uint8Array.from(atob(b64), c => c.charCodeAt(0))], ten,
            {{type: mime}});
          const dt = new DataTransfer();
          dt.items.add(mk('{base64.b64encode(PDF).decode()}',
                          'bao cao.pdf', 'application/pdf'));
          dt.items.add(mk('{base64.b64encode(MA).decode()}',
                          'loop.py', 'text/plain'));
          const o = document.querySelector('#o-soan');
          o.dispatchEvent(new DragEvent('drop',
            {{dataTransfer: dt, bubbles: true, cancelable: true}}));
          return 'xong';
        """)
        for _ in range(80):
            if cdp.js("document.querySelectorAll('#dai-the .the-dk').length") >= 3:
                break
            time.sleep(0.25)
        n2 = cdp.js("document.querySelectorAll('#dai-the .the-dk').length")
        bd.ghi("9. kéo-thả PDF + tệp mã nguồn vào ô soạn", n2 == 3,
               f"{n2} thẻ")
        ten = sorted(x.filename for x in cc.dinh_kem.cua_project("p"))
        bd.ghi("9b. server nhận đủ ba tệp", len(ten) == 3, f"{ten}")

        # -- BO MOT DINH KEM TRUOC KHI GUI ---------------------------------
        cdp.js("document.querySelector('#dai-the .the-dk .dk-bo').click(); return 1;")
        time.sleep(0.8)
        n3 = cdp.js("document.querySelectorAll('#dai-the .the-dk').length")
        bd.ghi("10. bỏ một đính kèm trước khi gửi", n3 == 2,
               f"{n3} thẻ còn lại")
        bd.ghi("10b. server cũng bỏ bản ghi đó",
               len(cc.dinh_kem.cua_project("p")) == 2,
               f"{len(cc.dinh_kem.cua_project('p'))} bản ghi")

        # -- GUI TIN kem dinh kem ------------------------------------------
        cdp.js("""
          const o = document.querySelector('#o-soan');
          o.value = 'update docs/seed.md with one line';
          document.querySelector('#nut-gui').click();
          return 1;
        """)
        het = time.time() + 40
        while time.time() < het and not cc.store.tasks("p"):
            time.sleep(0.2)
        viec = cc.store.tasks("p")
        bd.ghi("11. gửi tin → Router tạo việc", bool(viec),
               f"{len(viec)} việc")
        con = cc.dinh_kem.cua_project("p")
        cap = all(
            sorted(x.attachment_id for x in cc.dinh_kem.cho_agent(t.task_id))
            == sorted(x.attachment_id for x in con) for t in viec) if viec else False
        bd.ghi("12. agent được cấp đúng các đính kèm của tin đó", cap,
               f"{len(con)} đính kèm cấp cho {len(viec)} việc")
        bd.ghi("13. việc không liên quan thấy 0",
               cc.dinh_kem.cho_agent("p.khac") == [], "")
        bd.ghi("14. dải đính kèm được dọn sau khi gửi",
               cdp.js("document.querySelectorAll('#dai-the .the-dk').length") == 0
               and cdp.js("document.querySelector('#dai-dinh-kem').hidden"),
               "")

        # -- HOP THOAI: co X va dong bang Esc ------------------------------
        cdp.js("document.querySelector('#nut-tro-giup').click(); return 1;")
        time.sleep(0.3)
        mo = cdp.js("document.querySelector('#hop-thoai').open")
        co_x = cdp.js("!!document.querySelector('#ht-dong')")
        cdp.js("document.querySelector('#ht-dong').click(); return 1;")
        time.sleep(0.3)
        dong_x = not cdp.js("document.querySelector('#hop-thoai').open")
        cdp.js("document.querySelector('#nut-tro-giup').click(); return 1;")
        time.sleep(0.3)
        cdp.goi("Input.dispatchKeyEvent", type="keyDown", key="Escape",
                code="Escape", windowsVirtualKeyCode=27,
                nativeVirtualKeyCode=27)
        cdp.goi("Input.dispatchKeyEvent", type="keyUp", key="Escape",
                code="Escape", windowsVirtualKeyCode=27,
                nativeVirtualKeyCode=27)
        time.sleep(0.4)
        dong_esc = not cdp.js("document.querySelector('#hop-thoai').open")
        bd.ghi("15. hộp thoại: mở được, có nút ×, đóng bằng × và Esc",
               mo and co_x and dong_x and dong_esc,
               f"mở={mo} X={co_x} đóng-X={dong_x} đóng-Esc={dong_esc}")

        # -- KHONG loi JS nao ----------------------------------------------
        loi = cdp.js("window.__loi_js || []")
        bd.ghi("16. không lỗi JavaScript nào trên trang",
               not loi, f"{len(loi or [])} lỗi")

    finally:
        if cdp:
            cdp.dong()
        ch.terminate()
        try:
            ch.wait(timeout=10)
        except Exception:                                   # noqa: BLE001
            ch.kill()
        sv.should_exit = True
        th.join(timeout=10)
        cc.shutdown()
        if not a.keep:
            shutil.rmtree(kho, ignore_errors=True)
            shutil.rmtree(prof, ignore_errors=True)
        else:
            print(f"\n  (giữ lại {kho})")

    print("\n" + "=" * 76)
    hong = bd.hong()
    print(f"KẾT LUẬN: {len(bd.hang) - hong}/{len(bd.hang)} bước ĐẠT")
    print("  Lưu ý: kịch bản KHÔNG tự bấm được Win+Shift+S hay Ctrl+V của hệ")
    print("  điều hành. Nó chứng minh mã của ta xử lý đúng sự kiện dán/thả mà")
    print("  trình duyệt giao cho — bước bấm phím thật cần một cú bấm của người.")
    print("=" * 76)
    return 1 if hong else 0


if __name__ == "__main__":
    sys.exit(main())
