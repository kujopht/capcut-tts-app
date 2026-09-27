"""
Route cong khai/nguoi dung cua Fanfic AI Support (`/api/support/*`).

  GET  /api/support/status              co bat khong, co AI khong (cong khai)
  POST /api/support/ask                 hoi dap / chan doan (khach hoac nguoi dung)
  POST /api/support/reports             leo thang -> bao cao SUP-xxxx
  GET  /api/support/reports/{id}        nguoi GUI xem lai trang thai (dung chu)
  POST /api/support/client-errors       bo thu loi client (da lam sach, co gioi han)

CO TINH NANG: `FAS_SUPPORT_V1=1`. Mac dinh TAT -> moi route ngoai `/status` tra
503 `support_disabled` (giong `chat_not_configured`: noi that, khong 404 gia vo).

HAN MUC rieng theo CHU (nguoi dung / phien khach) VA theo IP, cong them tang
chung cua `server/rate_limit.py` (POST = Tier B).
"""
import os
import re
import secrets
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated, Any, Callable, List, Literal, Optional

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from server.rate_limit import SlidingWindowRateLimiter
from server.support.ai import xay_gateway
from server.support.engine import SupportEngine
from server.support.store import InMemorySupportStore
from server.support.tools import DiagnosticToolbox, SupportDeps

CUA_SO_GIAY = 600.0
HAN_MUC = {
    "ask": (12, 40),          # (theo chu, theo IP) / 10 phut
    "report": (5, 20),
    "client_errors": (20, 60),
    # Review doc lap (Antigravity Claude Opus, 2026-09-28): route DOC trang thai
    # bao cao cung phai co tran, khong thi do ma SUP-xxxx ton CPU vo han.
    "report_status": (30, 60),
}
#: Toi da 4 luot chan doan chay CUNG LUC cho ca tien trinh — luot thu 5 cho
#: toi da 5 giay roi nhan 503 `support_busy` (review doc lap: tranh nghen pool
#: cong cu khi nhieu nguoi hoi cung luc).
_DONG_THOI = threading.BoundedSemaphore(4)
_SESSION = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

Session = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{16,64}$")]
S11 = Annotated[str, StringConstraints(max_length=11)]
S20 = Annotated[str, StringConstraints(max_length=20)]
S24 = Annotated[str, StringConstraints(max_length=24)]
S40 = Annotated[str, StringConstraints(max_length=40)]
S48 = Annotated[str, StringConstraints(max_length=48)]
S64 = Annotated[str, StringConstraints(max_length=64)]
S300 = Annotated[str, StringConstraints(max_length=300)]
S500 = Annotated[str, StringConstraints(max_length=500)]


def bat_support(env=None) -> bool:
    e = os.environ if env is None else env
    return (e.get("FAS_SUPPORT_V1") or "").strip() == "1"


class SupportContextIn(BaseModel):
    """CHI cac truong nay; truong la (token, cookie, header...) bi BO, khong loi."""

    model_config = ConfigDict(extra="ignore")
    route: S300 = ""
    build: S40 = ""
    novel_id: Optional[S64] = None
    chapter_id: Optional[S64] = None
    reader_mode: S20 = ""
    browser: S20 = ""
    device: S20 = ""
    viewport: S11 = ""
    last_error_code: S48 = ""
    correlation_id: S48 = ""


class AskIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    mode: Literal["qa", "report"] = "qa"
    message: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    context: SupportContextIn = Field(default_factory=SupportContextIn)
    session_id: Session


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    context: SupportContextIn = Field(default_factory=SupportContextIn)
    session_id: Session
    diagnostic_id: Optional[Annotated[str, StringConstraints(pattern=r"^DG-[A-Z2-9]{10}$")]] = None


class ClientErrorIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: S24 = "js_error"
    code: S48 = ""
    message: S500 = ""
    route: S300 = ""
    build: S40 = ""
    browser: S20 = ""
    device: S20 = ""


class ClientErrorsIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    session_id: Session
    events: List[ClientErrorIn] = Field(default_factory=list, max_length=10)


@dataclass
class SupportRuntime:
    store: InMemorySupportStore
    toolbox: DiagnosticToolbox
    engine: SupportEngine
    limiter: SlidingWindowRateLimiter


def build_support_runtime(deps: SupportDeps, llm_settings: Any, *, env=None) -> SupportRuntime:
    store = InMemorySupportStore()
    tb = DiagnosticToolbox(deps, store)
    muoi = (os.environ if env is None else env).get("FAS_SUPPORT_HASH_SALT") or secrets.token_hex(16)
    engine = SupportEngine(tb, store, gateway=xay_gateway(llm_settings, env), muoi=muoi)
    return SupportRuntime(store=store, toolbox=tb, engine=engine, limiter=SlidingWindowRateLimiter())


def _ip(request: Request) -> str:
    # `cf-connecting-ip` do Cloudflare dat (client khong gia duoc qua Cloudflare);
    # KHONG dung X-Forwarded-For o day — ai cung tu dat duoc header do. Cung
    # cach voi `server/rate_limit.py`. Ngoai Cloudflare (dev), moi request cung
    # mot proxy se chung mot o han muc theo IP — han muc THEO CHU van dung.
    return request.headers.get("cf-connecting-ip", "").strip() or (request.client.host if request.client else "unknown")


def build_support_router(rt: SupportRuntime, *, resolve_viewer: Callable[[Optional[str]], Any],
                         enabled: Callable[[], bool] = bat_support) -> APIRouter:
    r = APIRouter()

    def _bat() -> None:
        if not enabled():
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                {"code": "support_disabled", "message": "Trợ giúp AI chưa được bật trên máy chủ."})

    def _han_muc(loai: str, chu: str, ip: str) -> None:
        theo_chu, theo_ip = HAN_MUC[loai]
        for khoa, toi_da in ((f"{loai}:chu:{chu}", theo_chu), (f"{loai}:ip:{ip}", theo_ip)):
            ok, _, sau = rt.limiter.check(khoa, toi_da, window=CUA_SO_GIAY)
            if not ok:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                    {"code": "support_rate_limited", "message": "Bạn gửi hơi nhiều — thử lại sau ít phút."},
                                    headers={"Retry-After": str(max(1, int(sau)))})

    @contextmanager
    def _cho_luot():
        if not _DONG_THOI.acquire(timeout=5):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                {"code": "support_busy", "message": "Trợ lý đang bận — thử lại sau vài giây."})
        try:
            yield
        finally:
            _DONG_THOI.release()

    @r.get("/api/support/status")
    def support_status() -> dict:
        bat = enabled()
        return {"enabled": bat, "ai_available": bat and rt.engine.ai_available, "persistence": "memory",
                "modes": ["qa", "report"]}

    @r.post("/api/support/ask")
    def support_ask(payload: AskIn, request: Request,
                    authorization: Optional[str] = Header(default=None)) -> dict:
        _bat()
        viewer = resolve_viewer(authorization)
        _han_muc("ask", rt.engine.owner_key(viewer, payload.session_id), _ip(request))
        with _cho_luot():
            return rt.engine.hoi(viewer=viewer, session_id=payload.session_id, message=payload.message,
                                 context=payload.context.model_dump(), mode=payload.mode)

    @r.post("/api/support/reports", status_code=status.HTTP_201_CREATED)
    def support_report(payload: ReportIn, request: Request,
                       authorization: Optional[str] = Header(default=None)) -> dict:
        _bat()
        viewer = resolve_viewer(authorization)
        _han_muc("report", rt.engine.owner_key(viewer, payload.session_id), _ip(request))
        with _cho_luot():
            rep = rt.engine.bao_cao(viewer=viewer, session_id=payload.session_id, summary=payload.summary,
                                    context=payload.context.model_dump(), diagnostic_id=payload.diagnostic_id)
        return {"report_id": rep.report_id, "status": rep.status,
                "message": f"Đã gửi cho quản trị viên — mã {rep.report_id}."}

    @r.get("/api/support/reports/{report_id}")
    def support_report_status(report_id: str, request: Request, x_support_session: Optional[str] = Header(default=None),
                              authorization: Optional[str] = Header(default=None)) -> dict:
        _bat()
        viewer = resolve_viewer(authorization)
        # Khach PHAI co session hop le (cung mau voi luc tao bao cao) — thieu/sai
        # thi khong suy ra mot owner_key co dinh nao ca (review doc lap).
        if viewer is None and not _SESSION.match(x_support_session or ""):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo cáo.")
        chu = rt.engine.owner_key(viewer, x_support_session or "")
        _han_muc("report_status", chu, _ip(request))
        rep = rt.store.get_report(report_id)
        # 404 cho CA "khong co" lan "khong phai cua ban" — khong do duoc ma nguoi khac.
        if rep is None or rep.owner_key != chu:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy báo cáo.")
        return rep.cong_khai()

    @r.post("/api/support/client-errors", status_code=status.HTTP_202_ACCEPTED)
    def support_client_errors(payload: ClientErrorsIn, request: Request,
                              authorization: Optional[str] = Header(default=None)) -> dict:
        _bat()
        viewer = resolve_viewer(authorization)
        _han_muc("client_errors", rt.engine.owner_key(viewer, payload.session_id), _ip(request))
        n = rt.engine.nhan_loi_client(viewer=viewer, session_id=payload.session_id,
                                      events=[e.model_dump() for e in payload.events])
        return {"accepted": n}

    return r
