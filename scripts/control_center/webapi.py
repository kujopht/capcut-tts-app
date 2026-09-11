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

    @app.get("/api/live")
    async def trang_thai_song(project: str = "", refresh: int = 0):
        """`ProjectLiveSnapshot` — trạng thái SỐNG của dự án (V0.5).

        CHỈ ĐỌC. Không một tham số nào ở đây chọn được một hành động: cả
        gói `observability` không có đường tác động (xem
        `observability/provider.py::KHONG_DUOC_CO` và bài kiểm quét cả
        gói). `refresh=1` chỉ bỏ qua bộ đệm, không đổi gì ở hệ thống
        được quan sát.

        RIÊNG một endpoint, KHÔNG nhập vào `/api/state`: probe SSH mất
        vài giây, còn `/api/state` bị WebSocket gọi mỗi nhịp. Trộn vào
        nhau là biến một ô quan sát thành một trận spam SSH vào máy
        production.
        """
        if not project:
            return _ma_loi(400, "thiếu project")
        try:
            a = await asyncio.to_thread(
                phien.cc.quan_sat.anh_chup, project,
                buoc_moi=bool(refresh))
        except Exception as exc:                          # noqa: BLE001
            return _ma_loi(400, f"{type(exc).__name__}: {exc}")
        return _sach(a.to_dict())

    @app.get("/api/live/capabilities")
    async def kha_nang_song(project: str = ""):
        if not project:
            return _ma_loi(400, "thiếu project")
        return _sach(await asyncio.to_thread(
            phien.cc.quan_sat.kha_nang, project))

    # -- ky uc du an (V0.6) --------------------------------------------------
    #
    # Moi duong DOC la GET va di qua `_sach`. Duong GHI (POST) chi ghi vao
    # SO KY UC cua chinh Control Center — khong mot cai nao cham production,
    # cham kho git, hay xoa lich su L0 (khong co endpoint xoa; xem
    # `memory/provider.py::KHONG_DUOC_CO`). `project` la tham so bat buoc:
    # ky uc la theo du an, va khong co duong "moi du an".

    def _ky_uc():
        kc = getattr(phien.cc, "ky_uc", None)
        if kc is None:
            return None
        return kc

    @app.get("/api/memory/stats")
    async def ky_uc_thong_ke(project: str = ""):
        kc = _ky_uc()
        if kc is None:
            return _sach({"san_sang": False,
                          "ly_do": getattr(phien.cc, "_ky_uc_loi", "") or
                          "ký ức không mở được"})
        if not project:
            return _sach(await asyncio.to_thread(kc.thong_ke_toan_cuc))
        return _sach(await asyncio.to_thread(kc.thong_ke, project))

    @app.get("/api/memory/search")
    async def ky_uc_tim(project: str = "", q: str = "", loai: str = "",
                        limit: int = 30):
        kc = _ky_uc()
        if kc is None or not project:
            return _ma_loi(400, "thiếu project hoặc ký ức không sẵn")
        return _sach(await asyncio.to_thread(
            kc.tim, project, q or "", loai=loai, limit=max(1, min(int(limit), 100))))

    @app.get("/api/memory/timeline")
    async def ky_uc_dong_thoi_gian(project: str = "", limit: int = 80,
                                   truoc_id: int = 0, loai: str = ""):
        kc = _ky_uc()
        if kc is None or not project:
            return _ma_loi(400, "thiếu project hoặc ký ức không sẵn")
        return _sach(await asyncio.to_thread(
            kc.dong_thoi_gian, project, limit=max(1, min(int(limit), 300)),
            truoc_id=int(truoc_id or 0), loai=loai))

    @app.get("/api/memory/list")
    async def ky_uc_liet_ke(project: str = "", loai: str = "", limit: int = 100):
        kc = _ky_uc()
        if kc is None or not project:
            return _ma_loi(400, "thiếu project hoặc ký ức không sẵn")
        return _sach(await asyncio.to_thread(
            kc.liet_ke, project, loai, limit=max(1, min(int(limit), 300))))

    @app.get("/api/memory/record")
    async def ky_uc_ban_ghi(project: str = "", ma: str = ""):
        kc = _ky_uc()
        if kc is None or not project or not ma:
            return _ma_loi(400, "thiếu project/ma hoặc ký ức không sẵn")
        return _sach(await asyncio.to_thread(kc.ban_ghi, project, ma))

    @app.get("/api/memory/evidence")
    async def ky_uc_bang_chung(project: str = "", su_kien_id: int = 0,
                               blob_sha: str = ""):
        kc = _ky_uc()
        if kc is None or not project:
            return _ma_loi(400, "thiếu project hoặc ký ức không sẵn")
        return _sach(await asyncio.to_thread(
            kc.bang_chung, project, su_kien_id=int(su_kien_id or 0),
            blob_sha=blob_sha or ""))

    @app.get("/api/memory/continue")
    async def ky_uc_tiep_tuc(project: str = ""):
        kc = _ky_uc()
        if kc is None or not project:
            return _ma_loi(400, "thiếu project hoặc ký ức không sẵn")
        return _sach(await asyncio.to_thread(kc.tiep_tuc, project))

    @app.get("/api/memory/context")
    async def ky_uc_goi(project: str = "", q: str = ""):
        """Xem trước GÓI NGỮ CẢNH đúng như Leader sẽ nhận — để soi ngân sách."""
        kc = _ky_uc()
        if kc is None or not project:
            return _ma_loi(400, "thiếu project hoặc ký ức không sẵn")

        def _lam():
            g = kc.goi_ngu_canh(project, q or "")
            if g is None:
                return {"san_sang": False}
            d = g.to_dict()
            d["van"] = kc.khoi_cho_leader(project, q or "")
            return d
        return _sach(await asyncio.to_thread(_lam))

    @app.post("/api/memory/checkpoint")
    async def ky_uc_diem_dung(payload: Dict):
        kc = _ky_uc()
        pid = str((payload or {}).get("project") or "")
        if kc is None or not pid:
            return _ma_loi(400, "thiếu project hoặc ký ức không sẵn")
        dd = await asyncio.to_thread(
            kc.diem_dung_tuong_minh, pid,
            str((payload or {}).get("ly_do") or "handoff"),
            dict((payload or {}).get("noi_dung") or {}))
        return _sach(dd.to_dict() if dd else {"loi": "không ghi được điểm dừng"})

    @app.post("/api/memory/decision")
    async def ky_uc_quyet_dinh(payload: Dict):
        kc = _ky_uc()
        p = payload or {}
        pid = str(p.get("project") or "")
        if kc is None or not pid or not str(p.get("noi_dung") or "").strip():
            return _ma_loi(400, "thiếu project/noi_dung hoặc ký ức không sẵn")
        r = await asyncio.to_thread(
            kc.ghi_quyet_dinh, pid, str(p.get("noi_dung")),
            ly_do=str(p.get("ly_do") or ""), tieu_de=str(p.get("tieu_de") or ""),
            thay_the_cho=[str(x) for x in (p.get("thay_the_cho") or [])],
            ai="web")
        return _sach(r or {"loi": "không ghi được"})

    @app.post("/api/memory/record")
    async def ky_uc_ghi(payload: Dict):
        kc = _ky_uc()
        p = payload or {}
        pid = str(p.get("project") or "")
        if kc is None or not pid or not str(p.get("noi_dung") or "").strip():
            return _ma_loi(400, "thiếu project/noi_dung hoặc ký ức không sẵn")
        r = await asyncio.to_thread(
            kc.ghi_ky_uc, pid, str(p.get("loai") or "semantic"),
            str(p.get("noi_dung")), tieu_de=str(p.get("tieu_de") or ""),
            quan_trong=int(p.get("quan_trong") or 6),
            the=[str(x) for x in (p.get("the") or [])], ai="web")
        return _sach(r or {"loi": "không ghi được"})

    @app.post("/api/memory/capsule")
    async def ky_uc_vien_nang(payload: Dict):
        kc = _ky_uc()
        p = payload or {}
        pid = str(p.get("project") or "")
        if kc is None or not pid:
            return _ma_loi(400, "thiếu project hoặc ký ức không sẵn")
        r = await asyncio.to_thread(
            kc.cap_nhat_vien_nang, pid, dict(p.get("thay_doi") or {}),
            ly_do=str(p.get("ly_do") or "cập nhật từ giao diện"))
        return _sach(r or {"loi": "không ghi được"})

    # -- nhap khau lich su (V0.6.1) -------------------------------------------
    # CHI DOC nguon (so, git log, tai lieu, phien Claude cua dung kho nay);
    # ghi vao SO KY UC cua chinh Control Center. Khong sua tep nguon nao.

    @app.get("/api/memory/backfill/sources")
    async def ky_uc_nguon_nhap(project: str = ""):
        kc = _ky_uc()
        if kc is None or not project:
            return _ma_loi(400, "thiếu project hoặc ký ức không sẵn")
        return _sach(await asyncio.to_thread(kc.nguon_nhap_khau, project))

    @app.post("/api/memory/backfill")
    async def ky_uc_nhap_khau(payload: Dict):
        kc = _ky_uc()
        p = payload or {}
        pid = str(p.get("project") or "")
        if kc is None or not pid:
            return _ma_loi(400, "thiếu project hoặc ký ức không sẵn")
        chi = [str(x) for x in (p.get("chi") or [])] or None
        return _sach(await asyncio.to_thread(
            kc.nhap_khau, pid, thu_kho=bool(p.get("thu_kho", True)), chi=chi))

    # -- V0.7: nhan du an + vien nang + kiem lien tuc ----------------------

    @app.post("/api/project/adopt")
    async def nhan_du_an_api(payload: Dict):
        """NHẬN một dự án hiện có. CHỈ ĐỌC kho đích, idempotent."""
        p = payload or {}
        duong = str(p.get("duong") or p.get("path") or "").strip()
        if not duong:
            return _ma_loi(400, "thiếu `duong` (thư mục dự án)")
        from scripts.control_center.nhan_du_an import nhan_du_an

        def _chay():
            return nhan_du_an(phien.cc, duong,
                              ten=str(p.get("ten") or ""),
                              project_id=str(p.get("project_id") or "")).to_dict()
        return _sach(await asyncio.to_thread(_chay))

    @app.get("/api/project/adopt/preview")
    async def nhan_xem_truoc(duong: str = ""):
        """Dò một thư mục TRƯỚC khi nhận — không ghi gì, không đăng ký gì."""
        if not duong:
            return _ma_loi(400, "thiếu `duong`")
        from scripts.control_center.nhan_du_an import (kham_pha_kho,
                                                       tim_du_an_trung)

        def _chay():
            d = kham_pha_kho(duong)
            return {"kho": d.to_dict(),
                    "da_co": tim_du_an_trung(phien.cc.store, d.goc_worktree) or ""}
        return _sach(await asyncio.to_thread(_chay))

    @app.get("/api/capsule")
    async def doc_vien_nang(project: str = ""):
        """Viên nang ĐANG LƯU + nhãn mục CŨ. Không dựng lại (rẻ)."""
        if not project:
            return _ma_loi(400, "thiếu project")
        from scripts.control_center import vien_nang_du_an as VN

        def _chay():
            muc, pb = VN.nap(phien.cc, project)
            return {"project_id": project, "phien_ban": pb, "muc": muc,
                    "so_muc": len(VN.KHOA_MUC),
                    "so_muc_co": sum(1 for k in VN.KHOA_MUC
                                     if (muc.get(k) or {}).get("trang_thai") == VN.CO),
                    "so_khong_ro": sum(1 for k in VN.KHOA_MUC
                                       if (muc.get(k) or {}).get("trang_thai") == VN.KHONG_RO),
                    "so_cu": sum(1 for k in VN.KHOA_MUC
                                 if (muc.get(k) or {}).get("trang_thai") == VN.CU),
                    "token_day": (VN.uoc_token(muc) if muc else 0),
                    "token_gon": (VN._ut_gon(muc) if muc else 0),
                    "nhan": VN.NHAN_MUC, "nhom": VN.NHOM_MUC,
                    "thu_tu": list(VN.KHOA_MUC)}
        return _sach(await asyncio.to_thread(_chay))

    @app.post("/api/capsule/rebuild")
    async def dung_lai_vien_nang(payload: Dict):
        """Dựng lại viên nang từ nguồn; chỉ sinh phiên bản khi có mục ĐỔI."""
        p = payload or {}
        pid = str(p.get("project") or "")
        if not pid:
            return _ma_loi(400, "thiếu project")
        from scripts.control_center import vien_nang_du_an as VN

        def _chay():
            kq = VN.dung_va_luu(phien.cc, pid, ly_do=str(p.get("ly_do") or ""))
            kq.pop("muc", None)          # tra ban gon; UI doc /api/capsule
            return kq
        return _sach(await asyncio.to_thread(_chay))

    @app.get("/api/capsule/versions")
    async def cac_phien_ban_nang(project: str = "", limit: int = 20):
        """Lịch sử phiên bản viên nang — trả lời "đổi gì, khi nào, vì sao"."""
        kc = _ky_uc()
        if kc is None or not project:
            return _ma_loi(400, "thiếu project hoặc ký ức không sẵn")

        def _chay():
            p = kc.provider(project)
            if p is None:
                return {"ket_qua": []}
            return {"ket_qua": p.cac_phien_ban_vien_nang(int(limit))}
        return _sach(await asyncio.to_thread(_chay))

    @app.get("/api/continuity")
    async def kiem_lien_tuc_api(project: str = ""):
        """Kiểm liên tục — Router hiểu dự án này tới đâu."""
        if not project:
            return _ma_loi(400, "thiếu project")
        from scripts.control_center import kiem_lien_tuc as KL
        return _sach(await asyncio.to_thread(KL.kiem, phien.cc, project))

    # -- V0.7: probe van hanh (CHI DOC) ------------------------------------

    @app.get("/api/probe/capabilities")
    async def probe_kha_nang(project: str = ""):
        """Thao tác probe nào dùng được cho dự án này, cái nào KHÔNG và vì sao.

        Chỉ liệt kê năng lực — không chạy phép đo nào.
        """
        if not project:
            return _ma_loi(400, "thiếu project")
        from scripts.control_center import probe_van_hanh as PV

        def _chay():
            mg = PV.tu_du_an(project)
            d = mg.kha_dung()
            d["ops"] = list(mg.ops())
            return d
        return _sach(await asyncio.to_thread(_chay))

    @app.post("/api/probe/audit")
    async def probe_kiem_toan(payload: Dict):
        """Kiểm toán đường ống production — CHỈ ĐỌC, phân loại A–F.

        Không nhận chuỗi lệnh: thân yêu cầu chỉ có `project` và cửa sổ giờ.
        """
        p = payload or {}
        project = str(p.get("project") or "").strip()
        if not project:
            return _ma_loi(400, "thiếu project")
        try:
            gio = max(1, min(168, int(p.get("gio") or 24)))
        except (TypeError, ValueError):
            return _ma_loi(400, "`gio` phải là số nguyên")
        from scripts.control_center import probe_van_hanh as PV

        def _chay():
            return PV.kiem_duong_ong(PV.tu_du_an(project), gio=gio).to_dict()
        return _sach(await asyncio.to_thread(_chay))

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

    # -- provider ngoai + kho bi mat (V0.6.1) ----------------------------------
    # Gia tri credential di vao DUY NHAT qua POST .../accounts (mot lan, tren
    # 127.0.0.1, co token) va vao thang KhoBiMat. Khong endpoint nao tra no ra.

    def _providers():
        try:
            return phien.cc.providers
        except Exception:                                   # noqa: BLE001
            return None

    def _loi_provider(exc: Exception) -> JSONResponse:
        from scripts.control_center.providers.kho_bi_mat import LoiKhoBiMat
        from scripts.control_center.providers.so import LoiSoProvider
        ma = 400 if isinstance(exc, (ValueError, LoiKhoBiMat, LoiSoProvider, KeyError)) else 500
        return _ma_loi(ma, redact(f"{type(exc).__name__}: {exc}"[:300]))

    @app.get("/api/providers")
    async def providers_doc():
        dv = _providers()
        if dv is None:
            return _ma_loi(503, "dịch vụ provider không sẵn")
        return _sach(await asyncio.to_thread(dv.trang_thai))

    @app.post("/api/providers")
    async def providers_them(payload: Dict):
        dv = _providers()
        if dv is None:
            return _ma_loi(503, "dịch vụ provider không sẵn")
        p = payload or {}
        try:
            return _sach(await asyncio.to_thread(
                dv.them_provider, str(p.get("provider_id") or ""), str(p.get("preset") or ""),
                base_url=str(p.get("base_url") or ""), ten=str(p.get("ten") or "")))
        except Exception as exc:                            # noqa: BLE001
            return _loi_provider(exc)

    @app.delete("/api/providers/{provider_id}")
    async def providers_xoa(provider_id: str, xac_nhan: bool = False):
        dv = _providers()
        if dv is None:
            return _ma_loi(503, "dịch vụ provider không sẵn")
        try:
            return _sach(await asyncio.to_thread(dv.xoa_provider, provider_id,
                                                 xac_nhan=bool(xac_nhan)))
        except Exception as exc:                            # noqa: BLE001
            return _loi_provider(exc)

    @app.post("/api/providers/{provider_id}/accounts")
    async def providers_them_tai_khoan(provider_id: str, payload: Dict):
        dv = _providers()
        if dv is None:
            return _ma_loi(503, "dịch vụ provider không sẵn")
        p = payload or {}
        gia_tri = p.pop("gia_tri", None)
        try:
            return _sach(await asyncio.to_thread(
                dv.them_tai_khoan, provider_id, str(p.get("alias") or ""), gia_tri,
                project_id=str(p.get("project") or "")))
        except Exception as exc:                            # noqa: BLE001
            return _loi_provider(exc)
        finally:
            del gia_tri

    @app.delete("/api/providers/accounts/{account_id}")
    async def providers_xoa_tai_khoan(account_id: str, xac_nhan: bool = False):
        dv = _providers()
        if dv is None:
            return _ma_loi(503, "dịch vụ provider không sẵn")
        try:
            return _sach(await asyncio.to_thread(dv.xoa_tai_khoan, account_id,
                                                 xac_nhan=bool(xac_nhan)))
        except Exception as exc:                            # noqa: BLE001
            return _loi_provider(exc)

    @app.post("/api/providers/accounts/{account_id}/toggle")
    async def providers_bat_tat(account_id: str, payload: Dict):
        dv = _providers()
        if dv is None:
            return _ma_loi(503, "dịch vụ provider không sẵn")
        try:
            return _sach(await asyncio.to_thread(dv.bat_tat_tai_khoan, account_id,
                                                 bool((payload or {}).get("bat", True))))
        except Exception as exc:                            # noqa: BLE001
            return _loi_provider(exc)

    @app.post("/api/providers/accounts/{account_id}/test")
    async def providers_thu(account_id: str, payload: Optional[Dict] = None):
        dv = _providers()
        if dv is None:
            return _ma_loi(503, "dịch vụ provider không sẵn")
        try:
            return _sach(await asyncio.to_thread(
                dv.thu_ket_noi, account_id, project_id=str((payload or {}).get("project") or "")))
        except Exception as exc:                            # noqa: BLE001
            return _loi_provider(exc)

    @app.post("/api/providers/accounts/{account_id}/ask")
    async def providers_hoi_thu(account_id: str, payload: Dict):
        """ĐỊNH TUYẾN THỦ CÔNG: một lượt, người bấm. Không phải đường AUTO."""
        dv = _providers()
        if dv is None:
            return _ma_loi(503, "dịch vụ provider không sẵn")
        p = payload or {}
        try:
            return _sach(await asyncio.to_thread(
                dv.hoi_thu, account_id, model=str(p.get("model") or ""),
                cau=str(p.get("cau") or ""), project_id=str(p.get("project") or ""),
                max_tokens=int(p.get("max_tokens") or 128)))
        except Exception as exc:                            # noqa: BLE001
            return _loi_provider(exc)

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
