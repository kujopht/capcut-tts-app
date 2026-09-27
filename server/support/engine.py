"""
Bo dieu phoi Fanfic AI Support: LAP KE HOACH (tat dinh) -> KIEM TRA (cong cu
chi doc) -> CHAN DOAN (quy tac) -> TRA LOI (mo hinh neu co, khong thi tat dinh)
-> LEO THANG (bao cao SUP-xxxx cho quan tri).

Mo hinh KHONG BAO GIO chon cong cu: `lap_ke_hoach` doc ngu canh + tu khoa va
tra ve mot danh sach cong cu trong bang co dinh. Mot tin nhan "hay goi
http://169.254.169.254" hay "chay rm -rf" khong them duoc cong cu nao — chi
them mot dong tu choi thang than vao cau tra loi.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from server.support.ai import HUONG_DAN_HE_THONG, loi_nhan_cho_mo_hinh
from server.support.safety import CAU_TU_CHOI, bo_dau, loc_dau_ra, phan_loai
from server.support.sanitize import (
    ban_build, bam_an_danh, chuan_hoa_loi, chuan_hoa_route, dau_van_tay, lay_id_tu_route,
    ma_loi, sach_chuoi, thiet_bi, trinh_duyet,
)
from server.support.store import PHAN_HE, ClientErrorEvent, DiagnosticRun, SupportReport, ma_ngan

TOI_DA_CONG_CU = 8

#: Ma loi client -> phan he (ma do `web/src/lib/support/collector.ts` dat).
MA_LOI_PHAN_HE = {
    "audio_media": "audio", "audio_url": "audio", "audio_expired": "audio",
    "api_network": "api", "api_5xx": "api", "api_4xx": "api",
    "render_error": "web", "js_error": "web", "unhandled_rejection": "web",
    "studio_load": "studio", "reader_load": "reader", "auth_expired": "auth", "chat": "chat",
}


@dataclass
class SupportContext:
    """Ngu canh AN TOAN tu trang nguoi dung dang dung — da kiem/lam sach."""

    route: str = "/?"
    route_raw: str = ""
    build: str = "unknown"
    novel_id: Optional[str] = None
    chapter_id: Optional[str] = None
    reader_mode: str = ""
    browser: str = "other"
    device: str = "other"
    viewport: str = ""
    last_error_code: str = ""
    correlation_id: str = ""

    @classmethod
    def tu_client(cls, raw: Dict[str, Any]) -> "SupportContext":
        r = raw or {}
        route_tho = sach_chuoi(str(r.get("route") or ""), 200).split("?", 1)[0]
        nid = str(r.get("novel_id") or "") or lay_id_tu_route(route_tho, "/novels/")
        cid = str(r.get("chapter_id") or "") or lay_id_tu_route(route_tho, "/chapters/")
        ok_id = lambda v: v if v and len(v) <= 64 and all(c.isalnum() or c in "_-" for c in v) else None  # noqa: E731
        vp = str(r.get("viewport") or "")
        return cls(
            route=chuan_hoa_route(route_tho), route_raw=route_tho if chuan_hoa_route(route_tho) != "/?" else "",
            build=ban_build(r.get("build")), novel_id=ok_id(nid), chapter_id=ok_id(cid),
            reader_mode=str(r.get("reader_mode") or "")[:20] if str(r.get("reader_mode") or "") in ("read", "listen", "read_listen", "") else "",
            browser=trinh_duyet(r.get("browser")), device=thiet_bi(r.get("device")),
            viewport=vp if vp.replace("x", "").isdigit() and len(vp) <= 11 else "",
            last_error_code=ma_loi(r.get("last_error_code")),
            correlation_id=ma_loi(r.get("correlation_id")),
        )

    def an_toan(self) -> Dict[str, Any]:
        return {"route": self.route, "build": self.build, "novel_id": self.novel_id, "chapter_id": self.chapter_id,
                "reader_mode": self.reader_mode, "browser": self.browser, "device": self.device,
                "viewport": self.viewport, "last_error_code": self.last_error_code}


def _co(t: str, *tu: str) -> bool:
    return any(x in t for x in tu)


def lap_ke_hoach(tin_nhan: str, ctx: SupportContext) -> List[Tuple[str, Dict[str, Any]]]:
    """Danh sach (cong cu, tham so) — TAT DINH, tu ngu canh + tu khoa (da bo dau)."""
    t = bo_dau(tin_nhan)
    ke: List[Tuple[str, Dict[str, Any]]] = [("check_api_health", {}), ("check_current_build", {})]
    am_thanh = _co(t, "audio", "nghe", "am thanh", "khong phat", "khong chay", "giong doc", "tua", "loa") \
        or ctx.last_error_code.startswith("audio")
    if ctx.route and ctx.route != "/?":
        ke.append(("check_route", {"route": ctx.route_raw or ctx.route}))
    if ctx.chapter_id:
        ke.append(("check_chapter", {"chapter_id": ctx.chapter_id}))
        if am_thanh or ctx.reader_mode in ("listen", "read_listen"):
            ke.append(("check_audio_track", {"chapter_id": ctx.chapter_id}))
            if _co(t, "tua", "seek", "nhay", "tiep tuc"):
                ke.append(("check_audio_range", {"chapter_id": ctx.chapter_id}))
    if ctx.novel_id:
        ke.append(("check_novel", {"novel_id": ctx.novel_id}))
    if _co(t, "studio", "viet truyen", "tao audio", "dich truyen") or ctx.route.startswith("/studio"):
        ke.append(("check_feature_status", {"feature": "studio"}))
        if not any(k == "check_route" for k, _ in ke):
            ke.append(("check_route", {"route": "/studio"}))
    if am_thanh:
        ke.append(("check_feature_status", {"feature": "tts_worker"}))
    if _co(t, "dang nhap", "login", "dang xuat", "het han", "phien"):
        ke.append(("check_feature_status", {"feature": "login"}))
    ke.append(("get_recent_public_incidents", {}))
    ke.append(("get_sanitized_client_errors", {}))
    # Bo trung, giu thu tu, cat tran.
    thay, ra = set(), []
    for ten, a in ke:
        k = (ten, tuple(sorted(a.items())))
        if k not in thay:
            thay.add(k)
            ra.append((ten, a))
    return ra[:TOI_DA_CONG_CU]


def chan_doan(ket_qua: List[Dict[str, Any]], ctx: SupportContext) -> List[Dict[str, Any]]:
    """Quy tac -> phat hien. Moi phat hien: code, subsystem, severity, text (cho
    nguoi dung), next (buoc tiep theo), confident (du chac de coi la 'AI da chan
    doan'), owner_needed (can chu du an xu ly)."""
    theo = {r["tool"]: r for r in ket_qua}
    ph: List[Dict[str, Any]] = []

    def them(code, subsystem, severity, text, nxt, *, confident=True, owner=False):
        ph.append({"code": code, "subsystem": subsystem, "severity": severity, "text": text,
                   "next": nxt, "confident": confident, "owner_needed": owner})

    api = theo.get("check_api_health")
    if api and api["status"] == "fail":
        hong = [k for k in ("metadata", "storage") if api["data"].get(k) is False]
        them("dependency_down", "storage" if "storage" in hong else "api", "high",
             "Máy chủ đang gặp sự cố ở " + (" và ".join({"metadata": "kho dữ liệu", "storage": "kho audio"}[k] for k in hong) or "một phụ thuộc") + ".",
             "Đây không phải lỗi của bạn. Hãy thử lại sau ít phút; mình có thể gửi báo cáo cho quản trị viên.",
             owner=True)
    r = theo.get("check_route")
    if r and r["data"].get("requires_login") and not r["data"].get("logged_in"):
        them("login_required", "auth", "low", "Trang này cần đăng nhập mà bạn đang chưa đăng nhập.",
             "Bấm Đăng nhập ở góc trên, rồi mở lại trang.")
    ch = theo.get("check_chapter")
    if ch and ch["status"] == "fail":
        them("chapter_missing", "reader", "medium", "Không tìm thấy chương này, hoặc chương chưa được xuất bản.",
             "Mở lại truyện từ Thư viện; nếu là truyện của bạn, kiểm tra trạng thái xuất bản trong Studio.")
    elif ch and not ch["data"].get("has_text", True):
        them("chapter_empty", "reader", "low", "Chương này chưa có nội dung chữ.", "Tác giả cần thêm nội dung trong Studio.")
    au = theo.get("check_audio_track")
    if au:
        d = au["data"]
        if d.get("has_track") is False and d.get("job_status") in ("pending", "running"):
            them("audio_generating", "audio", "low", "Audio của chương đang được tạo.", "Chờ vài phút rồi tải lại trang.")
        elif d.get("has_track") is False and au["status"] != "fail":
            them("audio_missing", "audio", "low", "Chương này chưa có audio.",
                 "Bạn vẫn đọc được chữ. Nếu là truyện của bạn, tạo audio trong Studio → Audio.")
        elif d.get("has_track") and d.get("object_present") is False:
            them("audio_object_missing", "storage", "high", "Chương có bản ghi audio nhưng tệp audio không còn trong kho.",
                 "Đây là lỗi phía máy chủ — mình sẽ gửi cho quản trị viên.", owner=True)
        elif d.get("has_track") and ctx.last_error_code in ("audio_media", "audio_url", "audio_expired"):
            them("audio_link_expired", "audio", "low",
                 "Tệp audio còn nguyên; lỗi phát thường là do liên kết nghe đã hết hạn sau khi để trang mở lâu.",
                 "Tải lại trang rồi bấm nghe lại. Nếu vẫn lỗi, gửi báo cáo để quản trị viên kiểm tra.", confident=False)
    rg = theo.get("check_audio_range")
    if rg and rg["data"].get("range_supported") is False:
        them("range_unsupported", "audio", "low", "Môi trường này không hỗ trợ tua giữa chừng.", "Trên fanfic.world bản chính thức tua được bình thường.")
    nv = theo.get("check_novel")
    if nv and nv["status"] == "fail":
        them("novel_missing", "reader", "medium", "Không tìm thấy truyện này (có thể đã bị gỡ hoặc chưa xuất bản).", "Tìm lại truyện trong Thư viện.")
    tw = [x for x in ket_qua if x["tool"] == "check_feature_status" and x["data"].get("feature") == "tts_worker"]
    if tw and tw[0]["data"].get("enabled") is False and au and au["data"].get("job_status") in ("pending", "running"):
        them("tts_worker_off", "audio", "medium", "Hàng đợi tạo audio đang chờ bộ xử lý.", "Quản trị viên cần kiểm tra bộ xử lý TTS.", owner=True, confident=False)
    inc = theo.get("get_recent_public_incidents")
    if inc and inc["data"].get("incidents"):
        cua_he = [i for i in inc["data"]["incidents"] if i["subsystem"] in {f["subsystem"] for f in ph} or not ph]
        if cua_he:
            them("known_incident", cua_he[0]["subsystem"], cua_he[0]["severity"],
                 "Quản trị viên đã ghi nhận một sự cố đang mở có thể liên quan.", "Đội ngũ đang xử lý; bạn không cần báo lại.", confident=False)
    return ph


def cau_tra_loi_tat_dinh(phat_hien: List[Dict[str, Any]], tu_choi: List[str]) -> str:
    dong: List[str] = [CAU_TU_CHOI[t] for t in tu_choi if t in CAU_TU_CHOI]
    if phat_hien:
        for f in phat_hien[:3]:
            dong.append(f"{f['text']} {f['next']}")
    elif not tu_choi:
        dong.append("Mình đã kiểm tra máy chủ, trang bạn đang mở và các sự cố đang biết — chưa thấy lỗi nào phía hệ thống. "
                    "Nếu vấn đề vẫn còn, hãy tả thêm bạn đã bấm gì, hoặc gửi báo cáo để quản trị viên xem.")
    return "\n".join(dong)


def phan_he_chinh(phat_hien: List[Dict[str, Any]], ctx: SupportContext) -> str:
    if phat_hien:
        return phat_hien[0]["subsystem"]
    if ctx.last_error_code in MA_LOI_PHAN_HE:
        return MA_LOI_PHAN_HE[ctx.last_error_code]
    if ctx.route.startswith("/studio"):
        return "studio"
    if ctx.route.startswith(("/chapters", "/novels")):
        return "reader"
    return "unknown"


class SupportEngine:
    def __init__(self, toolbox, store, *, gateway=None, muoi: str, clock=time.time) -> None:
        self.tb = toolbox
        self.store = store
        self.gateway = gateway
        self._muoi = muoi
        self._clock = clock

    @property
    def ai_available(self) -> bool:
        return self.gateway is not None

    def owner_key(self, viewer: Any, session_id: str) -> str:
        """Nguoi dang nhap -> theo user_id; khach -> bam cua session ngau nhien
        phia client. May chu tinh, client KHONG chon duoc owner cua nguoi khac."""
        if viewer is not None:
            return "u:" + bam_an_danh(viewer.user_id, self._muoi)
        return "g:" + bam_an_danh(session_id, self._muoi)

    # ------------------------------------------------------------ hoi
    def hoi(self, *, viewer: Any, session_id: str, message: str, context: Dict[str, Any], mode: str) -> Dict[str, Any]:
        ctx = SupportContext.tu_client(context)
        cau = sach_chuoi(message, 1000)
        # CO Y phan loai tren chuoi THO (van bi chan 1000 ky tu boi pydantic):
        # lam sach xoa query/URL la lam mat dau hieu "goi URL" can nhan dien.
        # Chuoi tho KHONG di dau khac — mo hinh, kho va phan hoi chi thay `cau`.
        tu_choi = phan_loai(message)
        ok = self.owner_key(viewer, session_id)
        ke = lap_ke_hoach(cau, ctx)
        ket_qua = [self.tb.chay(ten, a, viewer=viewer, owner_key=ok) for ten, a in ke]
        ph = chan_doan(ket_qua, ctx)
        tra_loi, che_do_ai = cau_tra_loi_tat_dinh(ph, tu_choi), "diagnostic_only"
        if self.gateway is not None:
            du_kien = {"checks": [{"tool": r["tool"], "status": r["status"], "summary": r["summary"]} for r in ket_qua],
                       "findings": [{k: f[k] for k in ("code", "subsystem", "text", "next")} for f in ph],
                       "refused_requests": [CAU_TU_CHOI[t] for t in tu_choi], "page": ctx.an_toan()}
            try:
                from server.llm_gateway.routing import TaskKind
                ra = self.gateway.complete(HUONG_DAN_HE_THONG, loi_nhan_cho_mo_hinh(cau, mode, du_kien),
                                           task_kind=TaskKind.CHEAP_SIMPLE)
                sach = loc_dau_ra(ra, 1500)
                if sach:
                    # Tu choi luon dung DAU va do MAY CHU viet — khong phu thuoc mo hinh co nghe loi hay khong.
                    dau = "\n".join(CAU_TU_CHOI[t] for t in tu_choi)
                    tra_loi, che_do_ai = (dau + "\n" + sach).strip(), "ai"
            except Exception:  # noqa: BLE001 — mo hinh hong -> van tra loi tat dinh
                che_do_ai = "diagnostic_only"
        run = DiagnosticRun(diagnostic_id=ma_ngan("DG-", 10), owner_key=ok, context=ctx.an_toan(),
                            checks=ket_qua, findings=ph, subsystem=phan_he_chinh(ph, ctx), denied=tu_choi,
                            ai_mode=che_do_ai)
        self.store.save_diagnostic(run)
        return {
            "answer": tra_loi, "mode": mode, "ai_mode": che_do_ai, "ai_available": self.ai_available,
            "diagnostic_id": run.diagnostic_id,
            "checks": [{"tool": r["tool"], "status": r["status"], "summary": r["summary"]} for r in ket_qua],
            "findings": [{k: f[k] for k in ("code", "subsystem", "severity", "text", "next", "owner_needed")} for f in ph],
            "denied": tu_choi,
            "can_escalate": True,
            "suggest_escalate": (not ph) or any(f["owner_needed"] for f in ph) or not any(f["confident"] for f in ph),
        }

    # ------------------------------------------------------------ bao cao
    def bao_cao(self, *, viewer: Any, session_id: str, summary: str, context: Dict[str, Any],
                diagnostic_id: Optional[str]) -> SupportReport:
        ctx = SupportContext.tu_client(context)
        ok = self.owner_key(viewer, session_id)
        run = self.store.get_diagnostic(diagnostic_id, ok) if diagnostic_id else None
        if run is None:
            # Khong co (hoac khong phai CUA MINH) -> may chu tu kiem lai; KHONG tin
            # bang chung client tu gui.
            ke = lap_ke_hoach(summary, ctx)
            ket_qua = [self.tb.chay(ten, a, viewer=viewer, owner_key=ok) for ten, a in ke]
            ph = chan_doan(ket_qua, ctx)
            run = DiagnosticRun(diagnostic_id="", owner_key=ok, context=ctx.an_toan(), checks=ket_qua,
                                findings=ph, subsystem=phan_he_chinh(ph, ctx), denied=phan_loai(summary),
                                ai_mode="diagnostic_only")
        he = run.subsystem if run.subsystem in PHAN_HE else "unknown"
        loi_goc = ctx.last_error_code or (run.findings[0]["code"] if run.findings else "user_report")
        chu_ky = chuan_hoa_loi(loi_goc)
        van_tay = dau_van_tay(ctx.route, chu_ky, he)
        bang_chung = [f"{r['tool']}: {r['status']} — {r['summary']}" for r in run.checks]
        tai_hien = [f"Trang: {ctx.route}", f"Trình duyệt/thiết bị: {ctx.browser}/{ctx.device}"
                    + (f" ({ctx.viewport})" if ctx.viewport else ""), f"Build web: {ctx.build}"]
        if ctx.reader_mode:
            tai_hien.append(f"Chế độ đọc: {ctx.reader_mode}")
        if ctx.last_error_code:
            tai_hien.append(f"Mã lỗi cuối: {ctx.last_error_code}")
        rep = SupportReport(
            report_id=ma_ngan("SUP-"), summary=sach_chuoi(summary, 1000) or "(không mô tả)", route=ctx.route,
            build=ctx.build, browser=ctx.browser, device=ctx.device, error_signature=chu_ky, fingerprint=van_tay,
            subsystem=he, severity="medium", checks=run.checks, findings=run.findings, evidence=bang_chung[:12],
            reproduction=tai_hien, owner_key=ok, reporter_user_id=getattr(viewer, "user_id", None),
            diagnostic_id=run.diagnostic_id or None, ai_mode=run.ai_mode)
        return self.store.create_report(rep)

    # ------------------------------------------------------------ loi client
    def nhan_loi_client(self, *, viewer: Any, session_id: str, events: List[Dict[str, Any]]) -> int:
        ok = self.owner_key(viewer, session_id)
        sach: List[ClientErrorEvent] = []
        thay = set()
        for e in events[:10]:
            kind = e.get("kind") if e.get("kind") in ("js_error", "unhandled_rejection", "api_error", "media_error", "render_error") else "js_error"
            code = ma_loi(e.get("code")) or kind
            route = chuan_hoa_route(sach_chuoi(str(e.get("route") or ""), 200))
            he = MA_LOI_PHAN_HE.get(code, "web")
            loi = chuan_hoa_loi(e.get("message") or code)
            van_tay = dau_van_tay(route, loi, he)
            if van_tay in thay:
                continue
            thay.add(van_tay)
            sach.append(ClientErrorEvent(kind=kind, route=route, message=loi, code=code, subsystem=he,
                                         build=ban_build(e.get("build")), browser=trinh_duyet(e.get("browser")),
                                         device=thiet_bi(e.get("device")), owner_key=ok, fingerprint=van_tay))
        self.store.add_client_events(sach)
        return len(sach)


__all__ = ["SupportEngine", "SupportContext", "lap_ke_hoach", "chan_doan"]
