"""Ảnh chụp màn hình THẬT của giao diện web — TRƯỚC và SAU bản V0.4.

Vì sao có tệp này thay vì chụp bằng tay:

Yêu cầu nghiệm thu V0.4 đòi ảnh "trước/sau". Chụp bằng tay thì hai ảnh
khác nhau ở CẢ dữ liệu (số việc, tên phiên, giờ) lẫn ở giao diện, nên
không đọc ra được cái gì đã đổi. Kịch bản này gieo **cùng một bộ dữ liệu**
vào **cùng một sổ**, rồi phục vụ hai bộ tài sản web khác nhau:

    TRƯỚC : ba tệp `web/` lấy từ `git show <ref>:...` (mặc định `HEAD`)
    SAU   : ba tệp `web/` trong cây làm việc hiện tại

Cùng dữ liệu, cùng cỡ cửa sổ, chỉ khác giao diện — đó mới là một phép so.

Chrome thật, headless mới, qua DevTools Protocol; `Page.captureScreenshot`
chứ không phải một bộ dựng ảnh mô phỏng. Dùng lại đúng cách nối CDP của
`control_center_web_smoke.py`.

    python scripts/control_center_web_anh.py
    python scripts/control_center_web_anh.py --ra docs/reports/anh
"""
from __future__ import annotations

import argparse
import base64
import json
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

from scripts.control_center.ghi_utf8 import GhiUTF8  # noqa: E402
from scripts.control_center_web_smoke import CDP, tim_chrome  # noqa: E402
from scripts.router_v3.tien_trinh import an_cua_so  # noqa: E402

#: KHONG `print()`. Mọi câu dưới đây là tiếng Việt, và `print()` giao
#: chuỗi cho tầng VĂN BẢN của luồng — codec do locale quyết định, cp1252
#: trên máy này. Chính kịch bản này đã chết ở dòng tiêu đề của nó ngay lần
#: chạy đầu (`UnicodeEncodeError: 'charmap' ... 'Ả'` = chữ **Ả**),
#: nên nó ở đây làm bằng chứng chứ không phải một lời khuyên.
ghi = GhiUTF8()

#: Cua so du rong de thay ca ba cot — day la mot app desktop, khong phai
#: mot trang di dong. Chup o `deviceScaleFactor=2` cho anh net.
RONG, CAO = 1680, 1000

#: Ba tep tao nen giao dien. Chi ba — khong co buoc build nao.
TEP_WEB = ("index.html", "app.js", "style.css")


def cong_rong() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def gieo(kho: Path):
    """Một dự án có thật: kho git thật, việc ở nhiều trạng thái, phiên
    agent, và một đoạn hội thoại Leader đã có kết quả trả về.

    Dữ liệu tiếng Việt CÓ DẤU ở mọi trường người dùng thấy — ảnh chụp cũng
    là một phép kiểm hiển thị, và một ảnh toàn ASCII sẽ không chứng minh
    được gì về đúng thứ đã từng làm EXE chết.
    """
    from scripts.control_center.bootstrap import khoi_tao
    from scripts.control_center.engine import ControlCenter
    from scripts.control_center.model import (Project, Session, SessionState,
                                              Task, TaskState)

    (kho / "docs").mkdir(parents=True, exist_ok=True)
    (kho / "docs" / "HANDOFF.md").write_text("bàn giao\n", encoding="utf-8")
    (kho / "README.md").write_text("Hàng đợi sản xuất\n", encoding="utf-8")
    for c in (["git", "init", "-q", "-b", "main"],
              ["git", "config", "user.email", "t@l"],
              ["git", "config", "user.name", "Người dùng"],
              ["git", "add", "-A"],
              ["git", "commit", "-q", "-m", "seed: Đường dẫn thử nghiệm"]):
        subprocess.run(c, cwd=kho, check=True, capture_output=True,
                       **an_cua_so())
    # Mot tep chua commit -> cay "CO THAY DOI", de o anh chup du an thay
    # duoc nhanh sach-ban that su hoat dong.
    (kho / "docs" / "ghi_chu.md").write_text("đang sửa\n", encoding="utf-8")

    cc = ControlCenter(root=kho, probe=False)
    khoi_tao(cc.store, root=kho)
    cc.them_project(Project(project_id="fanfic", name="Fanfic Audio Studio",
                            repo_path=str(kho)))
    cc.them_project(Project(project_id="router", name="Router Control Center",
                            repo_path=str(kho)))
    now = time.time()
    wt = str(kho / ".router" / "worktrees" / "fanfic-ta268-1")
    viec = [
        ("fanfic.ta268-1", "Sửa hàng đợi sản xuất bị nghẽn",
         TaskState.RUNNING, "s-2755e598", now - 214, 0.0, "AUTO", ""),
        ("fanfic.ta268-2", "Viết bài kiểm cho bộ chia đoạn",
         TaskState.QUEUED, "", 0.0, 0.0, "AUTO", ""),
        ("fanfic.ta268-3", "Deploy production fanfic.world",
         TaskState.BLOCKED, "", 0.0, 0.0, "GATED",
         "Việc này chạm lớp GATED (deploy production). Bạn có cho phép?"),
        ("fanfic.ta268-4", "Dọn cache preview cũ",
         TaskState.DONE, "s-91ab77c1", now - 900, now - 640, "AUTO", ""),
        ("fanfic.ta268-5", "Đổi giọng đọc mặc định",
         TaskState.FAILED, "s-91ab77c1", now - 1800, now - 1710, "AUTO", ""),
    ]
    for tid, ten, tt, phien, bd, kt, quyen, chan in viec:
        cc.store.luu_task(Task(
            task_id=tid, project_id="fanfic", title=ten,
            objective=f"{ten} — mục tiêu do Leader giao.",
            state=tt, owner_session=phien, permission=quyen,
            blocked_reason=chan, gate_reason=chan,
            worktree=wt if phien else "", branch="router/ta268",
            priority=40, attempts=1 if tt == TaskState.FAILED else 0,
            started_at=bd, ended_at=kt,
            updated_at=kt or bd or now, created_at=now - 2000))
    cc.store.luu_session(Session(
        session_id="s-2755e598", project_id="fanfic", provider="antigravity",
        runtime_id="AG01", model_id="gemini-3.8-flash-high",
        state=SessionState.BUSY, worktree=wt, branch="router/ta268",
        current_task="fanfic.ta268-1", task_count=3,
        created_at=now - 260, last_activity=now - 4))
    cc.store.luu_session(Session(
        session_id="s-91ab77c1", project_id="fanfic", provider="codex",
        runtime_id="", model_id="gpt-5.6-sol", state=SessionState.IDLE,
        task_count=2, created_at=now - 2400, last_activity=now - 600))

    cc.store.them_chat("fanfic", "user", "ê bro, hàng đợi sản xuất nghẽn rồi")
    cc.store.them_chat(
        "fanfic", "assistant",
        "Đã xem sổ: hàng đợi có 1 việc đang chạy và 1 việc chờ bạn duyệt.\n\n"
        "Tôi giao việc sửa nghẽn cho AG01 trong worktree riêng, và giữ việc "
        "deploy production ở BLOCKED để bạn quyết.",
        meta={"loai": "delegation",
              "task_ids": ["fanfic.ta268-1", "fanfic.ta268-3"],
              "plan": {"tasks": [
                  {"task_id": "ta268-1", "title": "Sửa hàng đợi sản xuất bị nghẽn"},
                  {"task_id": "ta268-3", "title": "Deploy production fanfic.world"}]}})
    cc.store.them_chat(
        "fanfic", "assistant",
        "Xong «Dọn cache preview cũ». Đã xoá 1.284 tệp preview quá 30 ngày, "
        "giải phóng 2,1 GB. Không tệp nào của người dùng bị chạm.",
        meta={"loai": "ket_qua", "task_id": "fanfic.ta268-4", "state": "DONE",
              "worker": "codex", "model": "gpt-5.6-sol"})
    return cc


def tai_san(ref: str, ra: Path) -> Path:
    """Ba tệp web của một `ref` git -> một thư mục. `""` = cây hiện tại."""
    ra.mkdir(parents=True, exist_ok=True)
    for t in TEP_WEB:
        nguon = f"scripts/control_center/web/{t}"
        if ref:
            p = subprocess.run(["git", "show", f"{ref}:{nguon}"], cwd=GOC,
                               capture_output=True, timeout=60, **an_cua_so())
            if p.returncode != 0:
                raise SystemExit(f"không lấy được {ref}:{nguon}")
            (ra / t).write_bytes(p.stdout)
        else:
            shutil.copyfile(GOC / nguon, ra / t)
    return ra


def chup_mot(nhan: str, web: Path, cc, ra_thu_muc: Path,
             truoc_khi_chup: str = "") -> Path:
    """Dựng server trỏ vào `web`, mở Chrome, chụp, tắt. Trả đường ảnh.

    `truoc_khi_chup`: một đoạn JS chạy sau khi trang đã tải xong, trước
    khi chụp — dùng để mở hộp thoại hoặc đổi tab. Nó KHÔNG được dùng để
    giả lập một tính năng: ảnh phải chụp thứ mã sản phẩm thật vẽ ra.
    """
    from scripts.control_center import webapi
    from scripts.control_center.webapi import PhienWeb, dung_app
    import uvicorn

    # `dung_app()` doc `webapi.WEB` LUC GOI (ca cho `/` va cho `/static`),
    # nen thay o day la du — khong phai sua ma san pham de chup duoc anh.
    cu = webapi.WEB
    webapi.WEB = web
    try:
        cong = cong_rong()
        phien = PhienWeb(cc, token="TOK-ANH", cong=cong)
        sv = uvicorn.Server(uvicorn.Config(
            dung_app(phien), host="127.0.0.1", port=cong,
            log_level="error", access_log=False))
        th = threading.Thread(target=sv.run, daemon=True)
        th.start()
        for _ in range(300):
            if sv.started:
                break
            time.sleep(0.05)
        if not sv.started:
            raise SystemExit("server không lên")

        cong_cdp = cong_rong()
        prof = Path(tempfile.mkdtemp(prefix="cc-anhprof-"))
        ch = subprocess.Popen(
            [tim_chrome(), "--headless=new", "--disable-gpu", "--no-first-run",
             "--no-default-browser-check", "--hide-scrollbars",
             f"--window-size={RONG},{CAO}",
             f"--user-data-dir={prof}",
             f"--remote-debugging-port={cong_cdp}",
             f"http://127.0.0.1:{cong}/?t={phien.token}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            **an_cua_so())
        cdp = None
        try:
            ws = ""
            het = time.time() + 40
            while time.time() < het and not ws:
                try:
                    with urllib.request.urlopen(
                            f"http://127.0.0.1:{cong_cdp}/json/list",
                            timeout=2) as f:
                        for t in json.load(f):
                            if t.get("type") == "page" and t.get(
                                    "webSocketDebuggerUrl"):
                                ws = t["webSocketDebuggerUrl"]
                                break
                except Exception:                          # noqa: BLE001
                    pass
                if not ws:
                    time.sleep(0.4)
            if not ws:
                raise SystemExit("không nối được CDP")
            cdp = CDP(ws)
            cdp.goi("Page.enable")
            cdp.goi("Runtime.enable")
            cdp.goi("Emulation.setDeviceMetricsOverride",
                    width=RONG, height=CAO, deviceScaleFactor=2,
                    mobile=False)
            # Cho tan: token duoc doc, `/api/state` ve, WebSocket noi, va
            # o quan sat cham (usage + anh chup git) da ve xong.
            het = time.time() + 30
            while time.time() < het:
                xong = cdp.js(
                    "document.querySelectorAll('#ds-tin .tin').length > 0")
                if xong:
                    break
                time.sleep(0.3)
            time.sleep(2.5)
            if truoc_khi_chup:
                cdp.js(truoc_khi_chup)
                time.sleep(1.6)
            r = cdp.goi("Page.captureScreenshot", format="png",
                        captureBeyondViewport=False)
            ra_thu_muc.mkdir(parents=True, exist_ok=True)
            duong = ra_thu_muc / f"{nhan}.png"
            duong.write_bytes(base64.b64decode(r["data"]))
            ghi(f"  [ẢNH ] {duong}  ({duong.stat().st_size // 1024} KB)")
            return duong
        finally:
            if cdp is not None:
                cdp.dong()
            ch.terminate()
            try:
                ch.wait(timeout=10)
            except Exception:                              # noqa: BLE001
                ch.kill()
            sv.should_exit = True
            th.join(timeout=10)
    finally:
        webapi.WEB = cu


def png_mau(duong: Path, w: int = 1280, h: int = 800) -> Path:
    """Một PNG thật, tự mã hoá — KHÔNG dùng thư viện ảnh nào.

    Vì sao không SVG: allowlist đính kèm CỐ Ý không nhận `svg` (SVG chạy
    được script), và tầng đính kèm kiểm CHỮ KÝ BYTE chứ không tin đuôi
    tệp. Nên ảnh nền mẫu phải là một PNG hợp lệ thật — đúng thứ người
    dùng sẽ chọn.

    Vì sao không Pillow: kịch bản chẩn đoán không được thêm phụ thuộc mới
    vào kho. `zlib` + `struct` là thư viện chuẩn.
    """
    import struct
    import zlib

    hang = []
    for y in range(h):
        d = bytearray([0])                  # filter 0 = None
        for x in range(w):
            # Mot vung sang cheo + it "sao" — du de thay anh nen that su
            # nam duoi lop kinh, khong phai mot mang mau phang.
            t = (x / w) * 0.6 + (1 - y / h) * 0.4
            r = 18 + 120 * t * t
            g = 34 + 190 * t * t
            b = 66 + 210 * t * t
            if (x * 7919 + y * 104729) % 2909 == 0:
                r, g, b = 210, 250, 245
            d += bytes(max(0, min(255, int(v))) for v in (r, g, b))
        hang.append(bytes(d))
    tho = zlib.compress(b"".join(hang), 6)

    def khoi(ten: bytes, du_lieu: bytes) -> bytes:
        return (struct.pack(">I", len(du_lieu)) + ten + du_lieu
                + struct.pack(">I", zlib.crc32(ten + du_lieu) & 0xFFFFFFFF))

    duong.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + khoi(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + khoi(b"IDAT", tho)
        + khoi(b"IEND", b""))
    return duong


def dat_anh_nen_that(cc, tep: Path) -> str:
    """Đi ĐÚNG đường sản phẩm: đính kèm -> `cai_dat_ui`. Trả mã đính kèm.

    Không đặt CSS trực tiếp, và đó là điểm chính của bước này: ảnh phải
    qua kiểm chữ ký byte của `attachments.py`, được lưu ở đường dẫn do
    băm nội dung sinh, rồi đọc lại CHỈ qua `attachment_id`. Nếu đường đó
    hỏng thì ảnh chụp phải hỏng theo — một ảnh đẹp nhờ bơm CSS sẽ che mất
    đúng cái cần chứng minh.
    """
    with open(tep, "rb") as f:
        dk = cc.dinh_kem.them_tu_luong("fanfic", f, tep.name, owner="anh")
    cc.store.luu_cai_dat_ui({"wallpaper": dk.attachment_id,
                             "dim": 0.34, "blur": 2, "fit": "cover"})
    ghi(f"  [NỀN ] đính kèm {dk.attachment_id} · {dk.filename} · "
        f"{dk.size_bytes // 1024} KB · sha256 {dk.sha256[:12]}")
    return dk.attachment_id


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ra", default="docs/reports/anh/control_center_v04")
    ap.add_argument("--truoc-ref", default="HEAD",
                    help="ref git cho ảnh TRƯỚC (mặc định HEAD)")
    a = ap.parse_args(argv)

    ra = (GOC / a.ra) if not Path(a.ra).is_absolute() else Path(a.ra)
    kho = Path(tempfile.mkdtemp(prefix="cc-anh-"))
    tmp = Path(tempfile.mkdtemp(prefix="cc-anh-web-"))

    ghi("=" * 76)
    ghi("ẢNH CHỤP GIAO DIỆN WEB — TRƯỚC / SAU (Chrome thật, CDP)")
    ghi(f"cùng một sổ, cùng cỡ {RONG}x{CAO}@2x; chỉ khác tài sản web")
    ghi("=" * 76)

    cc = gieo(kho)
    try:
        ghi(f"TRƯỚC (git {a.truoc_ref}):")
        chup_mot("truoc", tai_san(a.truoc_ref, tmp / "truoc"), cc, ra)
        ghi("TRƯỚC — khung Tasks:")
        chup_mot("truoc_tasks", tai_san(a.truoc_ref, tmp / "truoc"), cc, ra,
                 truoc_khi_chup="document.querySelector"
                                "('[data-khung=tasks]').click(); return 1;")

        sau = tai_san("", tmp / "sau")
        ghi("SAU (cây làm việc):")
        chup_mot("sau", sau, cc, ra)
        ghi("SAU — khung Usage (bảng theo nguồn):")
        chup_mot("sau_usage", sau, cc, ra,
                 truoc_khi_chup="document.querySelector"
                                "('[data-khung=usage]').click(); return 1;")
        ghi("SAU — hộp thoại Cài đặt (ảnh nền):")
        chup_mot("sau_cai_dat", sau, cc, ra,
                 truoc_khi_chup="document.querySelector"
                                "('#nut-cai-dat').click(); return 1;")

        ghi("SAU + ảnh nền (đi ĐÚNG đường đính kèm -> cai_dat_ui):")
        dat_anh_nen_that(cc, png_mau(tmp / "nen-thu-nghiem.png"))
        chup_mot("sau_anh_nen", sau, cc, ra)
    finally:
        cc.store.close()
    ghi("=" * 76)
    ghi(f"xong — ảnh ở {ra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
