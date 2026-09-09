"""API HTTP/WebSocket CHỈ TRÊN 127.0.0.1 cho giao diện web của Control Center.

Đây là ranh giới mới của V0.2: trước đây giao diện gọi thẳng `ControlCenter`
trong cùng tiến trình (Qt), giờ nó đi qua HTTP. Một ranh giới HTTP cục bộ
mang theo một lớp rủi ro mà app desktop không có, nên phần lớn tệp này là
về đúng chuyện đó.

MỘT LOCALHOST SERVER KHÔNG PHẢI LÀ RIÊNG TƯ. Ba điều phải nói thẳng:

1. **Mọi trang web bạn đang mở đều gọi được `http://127.0.0.1:<cổng>`.**
   Trình duyệt cho phép gửi request cross-origin; nó chỉ ngăn *đọc* phản
   hồi. Nghĩa là nếu không có gì chặn, một quảng cáo trên một tab khác có
   thể `POST /api/chat` và điều khiển Router của bạn. Nên **mỗi request
   phải mang token của phiên** — không có token thì 401, kể cả `GET`.

2. **DNS rebinding đi vòng qua phép kiểm origin.** Một tên miền của kẻ tấn
   công có thể trỏ về 127.0.0.1; lúc đó `Origin` là của họ nhưng request
   tới đúng server này. Nên `Host` được kiểm tường minh: chỉ nhận
   `127.0.0.1:<cổng>` hoặc `localhost:<cổng>`.

3. **Không có CORS.** Cố ý không đặt `Access-Control-Allow-Origin` gì cả.
   Frontend là same-origin (server tự phục vụ nó), nên nó không cần CORS,
   và thêm CORS chỉ mở cửa cho người khác.

Token là bí mật CỤC BỘ giữa trang và server của chính nó — nó không phải
credential của nhà cung cấp. Ranh giới "không rò bí mật ra frontend" vẫn
giữ nguyên: mọi payload đi ra đều qua `packet.redact`, và có bài kiểm đòi
API không bao giờ phát ra thứ giống credential.

BIND: `127.0.0.1`. Không bao giờ `0.0.0.0` — có bài kiểm khoá lại, vì đó
là một ký tự khác biệt giữa "công cụ cá nhân" và "mở cổng ra mạng LAN".
"""
from __future__ import annotations

import asyncio
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import (Depends, FastAPI, Form, HTTPException, Request,
                     UploadFile, WebSocket, WebSocketDisconnect)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from scripts.control_center.attachments import DinhKemLoi
from scripts.control_center.engine import ControlCenter
from scripts.control_center.model import Project
from scripts.router_v3.packet import redact

#: Chi nhan Host nay. Chan DNS rebinding.
HOST_CHO_PHEP = ("127.0.0.1", "localhost", "[::1]")

#: Nhip day trang thai qua WebSocket. Trung nhip cua giao dien Qt.
NHIP = 1.0

WEB = Path(__file__).parent / "web"


class PhienWeb:
    """Trạng thái của một lần chạy server: token + `ControlCenter`."""

    def __init__(self, cc: ControlCenter, *, token: str = "",
                 cong: int = 0):
        self.cc = cc
        self.token = token or secrets.token_urlsafe(32)
        self.cong = cong
        self.bat_dau_luc = time.time()

    def kiem_token(self, dua: str) -> bool:
        """So sánh theo THỜI GIAN HẰNG. Token là bí mật, dù là bí mật cục bộ."""
        return bool(dua) and hmac.compare_digest(dua, self.token)


def _ma_loi(ma: int, thong_diep: str) -> JSONResponse:
    return JSONResponse({"error": thong_diep}, status_code=ma)


def dung_app(phien: PhienWeb) -> FastAPI:
    app = FastAPI(title="Router Control Center", docs_url=None,
                  redoc_url=None, openapi_url=None)
    # `docs_url=None`: trang /docs cua FastAPI liet ke toan bo API. Voi mot
    # cong cu ca nhan thi no chi la be mat tan cong them, khong loi gi.

    # -- lop bao ve ----------------------------------------------------------

    @app.middleware("http")
    async def canh_cong(request: Request, call_next):
        """Kiểm `Host` rồi kiểm token. Thứ tự này quan trọng.

        `Host` trước: nếu request tới qua một tên miền lạ (DNS rebinding)
        thì từ chối ngay, không cần biết token đúng hay sai — vì chính việc
        token *có thể* đúng là điều ta đang phòng.
        """
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host not in HOST_CHO_PHEP:
            return _ma_loi(
                400, f"Host {host!r} không được phép — API này chỉ phục vụ "
                     f"127.0.0.1")

        duong = request.url.path
        # Trang goc + tai nguyen tinh: khong doi token, vi trinh duyet phai
        # tai duoc HTML/JS/CSS TRUOC khi no biet token la gi. Chung khong
        # chua du lieu nao.
        if duong == "/" or duong.startswith("/static/"):
            return await call_next(request)

        if duong.startswith("/api/"):
            dua = (request.headers.get("x-cc-token")
                   or request.query_params.get("t") or "")
            if not phien.kiem_token(dua):
                return _ma_loi(401, "thiếu hoặc sai token phiên")
        return await call_next(request)

    # -- trang -------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def trang_goc():
        p = WEB / "index.html"
        if not p.is_file():
            return HTMLResponse("<h1>thiếu giao diện web</h1>", status_code=500)
        return HTMLResponse(p.read_text(encoding="utf-8"))

    if WEB.is_dir():
        app.mount("/static", StaticFiles(directory=str(WEB)), name="static")

    # -- doc ---------------------------------------------------------------

    def _sach(d):
        """Mọi payload đi ra đều qua bộ lọc bí mật. Không ngoại lệ."""
        return json.loads(redact(json.dumps(d, ensure_ascii=False,
                                            default=str)))

    @app.get("/api/state")
    async def state(project: str = ""):
        pid = project or ""
        d = phien.cc.snapshot(pid)
        d["attachments_by_message"] = {}
        for m in (d.get("chat") or []):
            ds = phien.cc.dinh_kem.cua_message(
                d.get("selected") or pid, int(m.get("message_id") or 0))
            if ds:
                d["attachments_by_message"][str(m.get("message_id"))] = [
                    x.to_dict() for x in ds]
        return _sach(d)

    @app.get("/api/usage")
    async def usage(project: str = ""):
        return _sach(phien.cc.usage.report(project or ""))

    @app.get("/api/task/{task_id}/log")
    async def log_viec(task_id: str):
        return {"task_id": task_id,
                "text": redact(phien.cc.log_cua_viec(task_id))}

    @app.get("/api/snapshot")
    async def anh_chup(project: str = ""):
        """`AnhChupDuAn` — nhánh/HEAD/sạch-bẩn/commit gần đây.

        RIÊNG một endpoint, KHÔNG nhập vào `/api/state`, và đó là điểm
        chính: hàm này chạy ~6 lệnh `git`, còn `/api/state` bị WebSocket
        gọi mỗi nhịp. Trộn vào nhau là biến một ô quan sát thành ~6 tiến
        trình con mỗi giây — chỗ nhấp cửa sổ nhiều nhất của bản V0.3.
        Frontend gọi cái này khi ĐỔI DỰ ÁN và theo nhịp chậm.
        """
        if not project:
            return _ma_loi(400, "thiếu project")
        try:
            a = await asyncio.to_thread(phien.cc.anh_chup_du_an, project)
        except Exception as exc:                          # noqa: BLE001
            return _ma_loi(400, f"{type(exc).__name__}: {exc}")
        return _sach(a.to_dict())

    # -- cai dat giao dien -------------------------------------------------

    @app.get("/api/ui")
    async def doc_ui():
        return _sach(await asyncio.to_thread(phien.cc.store.cai_dat_ui))

    @app.post("/api/ui")
    async def ghi_ui(payload: Dict):
        """Ảnh nền / độ tối / độ nhoè. CHỈ nhận những khoá đã biết.

        `wallpaper` là một **mã đính kèm**, KHÔNG phải đường dẫn tệp — và
        đó là quyết định an toàn quan trọng nhất của tính năng này. Nhận
        đường dẫn thì phải mở một endpoint đọc tệp tuỳ ý trên đĩa để vẽ
        được nó, tức là dựng lại đúng lỗ mà `attachments.py` đã bịt.
        Ảnh nền đi qua CÙNG đường tải lên như mọi đính kèm khác: kiểm
        chữ ký byte, đường dẫn do băm nội dung sinh, đọc lại chỉ qua
        `attachment_id` với phép kiểm containment sau `resolve()`.
        """
        d = payload or {}
        ra: Dict = {}
        if "wallpaper" in d:
            aid = str(d.get("wallpaper") or "")
            if aid:
                dk = await asyncio.to_thread(phien.cc.dinh_kem.lay, aid)
                if dk is None:
                    return _ma_loi(400, "không có đính kèm đó")
                if not dk.la_anh:
                    return _ma_loi(400, "ảnh nền phải là một tệp ảnh")
            ra["wallpaper"] = aid
        for k, tran in (("dim", 1.0), ("blur", 40.0)):
            if k in d:
                try:
                    v = float(d[k])
                except (TypeError, ValueError):
                    return _ma_loi(400, f"{k} phải là số")
                ra[k] = max(0.0, min(tran, v))
        for k in ("fit", "theme"):
            if k in d:
                ra[k] = str(d[k])[:32]
        if not ra:
            return _ma_loi(400, "không có khoá nào hợp lệ")
        return _sach(await asyncio.to_thread(
            phien.cc.store.luu_cai_dat_ui, ra))

    # -- ghi ---------------------------------------------------------------

    @app.post("/api/chat")
    async def chat(payload: Dict):
        pid = (payload or {}).get("project_id") or ""
        text = (payload or {}).get("text") or ""
        ids = list((payload or {}).get("attachment_ids") or [])
        if not pid:
            return _ma_loi(400, "thiếu project_id")
        if not text.strip() and not ids:
            return _ma_loi(400, "tin nhắn rỗng và không có đính kèm")
        kq = await asyncio.to_thread(
            phien.cc.chat, pid, text, attachment_ids=ids)
        return _sach(kq)

    def _viec(ham, task_id: str):
        try:
            ham(task_id)
        except Exception as exc:                          # noqa: BLE001
            return _ma_loi(400, f"{type(exc).__name__}: {exc}")
        return {"ok": True, "task_id": task_id}

    @app.post("/api/task/{task_id}/pause")
    async def pause(task_id: str):
        return await asyncio.to_thread(_viec, phien.cc.pause, task_id)

    @app.post("/api/task/{task_id}/resume")
    async def resume(task_id: str):
        return await asyncio.to_thread(_viec, phien.cc.resume, task_id)

    @app.post("/api/task/{task_id}/stop")
    async def stop(task_id: str):
        return await asyncio.to_thread(_viec, phien.cc.stop, task_id)

    @app.post("/api/task/{task_id}/approve")
    async def approve(task_id: str):
        """Mở cổng GATED. Vẫn là hành động của NGƯỜI — frontend phải hỏi
        xác nhận trước khi gọi, và việc này được ghi vào sổ kiểm toán."""
        return await asyncio.to_thread(_viec, phien.cc.mo_khoa_gated, task_id)

    @app.post("/api/project")
    async def them_project(payload: Dict):
        pid = (payload or {}).get("project_id") or ""
        ten = (payload or {}).get("name") or pid
        duong = (payload or {}).get("repo_path") or ""
        if not pid or not duong:
            return _ma_loi(400, "thiếu project_id hoặc repo_path")
        if not Path(duong).is_dir():
            return _ma_loi(400, f"không phải thư mục: {duong}")
        # Cung mot cong voi buoc gieo: Router lam viec tren KHO GIT. Nhan
        # mot thu muc thuong o day chi doi cho luc hong sang viec dau tien,
        # va luc do thong diep la `WorktreeError: not a git repository` —
        # o mot cho khong ai noi duoc no lien quan gi toi o nhap nay.
        from scripts.control_center.bootstrap import la_kho_git
        if not await asyncio.to_thread(la_kho_git, duong):
            return _ma_loi(400, f"không phải kho git: {duong} — Router làm "
                                f"việc trên kho git (cần có .git)")
        p = Project(project_id=pid, name=ten, repo_path=duong)
        return _sach(await asyncio.to_thread(
            lambda: phien.cc.them_project(p).to_dict()))

    # -- dinh kem ----------------------------------------------------------

    @app.post("/api/attachments")
    async def tai_len(project_id: str = Form(...),
                      file: UploadFile = None):
        """Nhận MỘT tệp. Dùng cho cả bốn đường vào của frontend.

        Dán ảnh, kéo-thả, hộp chọn tệp, dán tệp từ Explorer — trình duyệt
        biến tất cả thành cùng một `multipart/form-data`, nên phía server
        chỉ có một đường và một chỗ để kiểm.

        LUỒNG được chuyển thẳng xuống kho: không `await file.read()`, vì
        nó nạp cả tệp vào RAM và phá đúng bất biến dòng chảy.
        """
        if file is None:
            return _ma_loi(400, "thiếu tệp")
        try:
            dk = await asyncio.to_thread(
                phien.cc.dinh_kem.them_tu_luong, project_id, file.file,
                file.filename or "khong_ten", owner="web")
        except DinhKemLoi as exc:
            return _ma_loi(400, str(exc))
        except Exception as exc:                          # noqa: BLE001
            return _ma_loi(400, f"{type(exc).__name__}: {exc}")
        return _sach(dk.to_dict())

    @app.delete("/api/attachments/{attachment_id}")
    async def bo_dinh_kem(attachment_id: str):
        ok = await asyncio.to_thread(phien.cc.dinh_kem.xoa, attachment_id)
        if not ok:
            return _ma_loi(404, "không có đính kèm đó")
        return {"ok": True}

    @app.get("/api/attachments/{attachment_id}/blob")
    async def blob(attachment_id: str):
        """Trả byte của một đính kèm — CHỈ qua `attachment_id`.

        Không có tham số đường dẫn nào ở đây, và cũng không thể có: đường
        dẫn thật do `KhoDinhKem.duong_dan()` sinh, và nó kiểm lại rằng kết
        quả nằm trong kho sau khi `resolve()`. Đó là lý do endpoint này
        không cần tự kiểm path traversal — phép kiểm nằm ở tầng dưới, một
        chỗ duy nhất, và có bài kiểm riêng.
        """
        dk = phien.cc.dinh_kem.lay(attachment_id)
        if dk is None:
            return _ma_loi(404, "không có đính kèm đó")
        try:
            p = phien.cc.dinh_kem.duong_dan(attachment_id)
        except DinhKemLoi as exc:
            return _ma_loi(400, str(exc))
        return FileResponse(
            str(p), filename=dk.filename,
            media_type=("image/" + dk.filename.rsplit(".", 1)[-1].lower()
                        if dk.la_anh else "application/octet-stream"),
            headers={
                # Xem TRONG trang voi anh; con lai thi tai ve. `nosniff` de
                # trinh duyet khong tu doan mot .txt thanh HTML roi chay no.
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition":
                    ("inline" if dk.la_anh else "attachment")
                    + f'; filename="{dk.filename}"',
            })

    # -- WebSocket: trang thai SONG ----------------------------------------

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        """Đẩy ảnh chụp khi CÓ THAY ĐỔI, không đẩy mỗi giây vô điều kiện.

        Đẩy vô điều kiện làm frontend vẽ lại liên tục và giết mất vùng
        người dùng đang bôi đen — đúng lỗi đã gặp ở giao diện Qt (review
        đối kháng #1/#2). Nên so dấu vân tay trước khi gửi.
        """
        host = (sock.headers.get("host") or "").split(":")[0].lower()
        dua = sock.query_params.get("t") or ""
        if host not in HOST_CHO_PHEP or not phien.kiem_token(dua):
            await sock.close(code=1008)
            return
        await sock.accept()
        pid = sock.query_params.get("project") or ""
        dau = ""
        try:
            while True:
                d = await asyncio.to_thread(phien.cc.snapshot, pid)
                gon = json.dumps(
                    {"tasks": [(t.get("task_id"), t.get("state"),
                                t.get("owner_session"))
                               for t in (d.get("tasks") or [])],
                     "sessions": [(s.get("session_id"), s.get("state"))
                                  for s in (d.get("sessions") or [])],
                     "chat": [m.get("message_id")
                              for m in (d.get("chat") or [])],
                     "locks": len(d.get("locks") or []),
                     # BUOC phai nam trong van tay, khong thi tien do
                     # SONG khong bao gio duoc day di: mot lan `chat()`
                     # dai khong doi task/session/chat nao ca.
                     "buoc": (d.get("buoc") or {}).get("nhan", "")},
                    sort_keys=True)
                if gon != dau:
                    dau = gon
                    await sock.send_text(json.dumps(
                        {"kind": "state", "data": _sach(d)},
                        ensure_ascii=False))
                await asyncio.sleep(NHIP)
        except (WebSocketDisconnect, asyncio.CancelledError):
            return
        except Exception:                                 # noqa: BLE001
            try:
                await sock.close(code=1011)
            except Exception:                             # noqa: BLE001
                pass

    return app
