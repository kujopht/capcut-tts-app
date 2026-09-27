"""
Route QUAN TRI cua Fanfic AI Support — Trung tam ho tro (`/admin/support`).

  GET  /api/admin/support/summary                  so lieu tong: dang mo, bao cao moi, can chu du an...
  GET  /api/admin/support/incidents                su co GOM NHOM (loc: status/subsystem/severity/build/route/unresolved/q)
  GET  /api/admin/support/incidents/{id}           chi tiet: dong thoi gian, bang chung da lam sach, kiem tra, tai hien
  POST /api/admin/support/incidents/{id}/status    doi trang thai (new/open/ai_diagnosed/needs_owner/resolved) + ghi chu
  GET  /api/admin/support/incidents/{id}/issue-draft   BAN NHAP issue GitHub (Markdown) — CHI CHUAN BI
  GET  /api/admin/support/reports                  bao cao moi nhat

QUYEN: moi route qua `admin_dep` do `main.py` tiem (`admin_profile`: OWNER/ADMIN/
MODERATOR). Doi trang thai duoc ghi vao DONG THOI GIAN cua su co kem ma
nguoi thao tac — KHONG ghi vao nhat ky kiem duyet Appwrite (do la du lieu
production; su co Support V1 van nam trong bo nho).

KHONG co route nao tao issue GitHub, deploy, hay sua loi tu dong: "issue-draft"
tra ve Markdown de quan tri SAO CHEP; neu co `FAS_SUPPORT_GITHUB_REPO` thi kem
mot duong dan "issues/new" dien san — quan tri van phai tu bam tao tren GitHub.
"""
import os
import re
from typing import Annotated, Any, Callable, Dict, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, StringConstraints

from server.support.routes import SupportRuntime
from server.support.sanitize import sach_chuoi
from server.support.store import MUC_DO, PHAN_HE, TRANG_THAI


class StatusIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: Annotated[str, StringConstraints(max_length=20)]
    note: Annotated[str, StringConstraints(max_length=500)] = ""


def _repo(env=None) -> Optional[str]:
    v = ((os.environ if env is None else env).get("FAS_SUPPORT_GITHUB_REPO") or "").strip()
    return v if re.match(r"^[A-Za-z0-9_.-]{1,39}/[A-Za-z0-9_.-]{1,100}$", v) else None


def ban_nhap_issue(chi_tiet: Dict[str, Any], env=None) -> Dict[str, Any]:
    """Markdown issue tu su co — moi truong da lam sach tu luc ghi, lam sach
    them mot lan nua o day (khong bao gio tin mot lop duy nhat)."""
    c = chi_tiet
    tieu_de = sach_chuoi(f"[Support {c['incident_id']}] {c['subsystem']}: {c['title']}", 120)
    phat_hien = [f"- {f.get('text')} → {f.get('next')}" for f in (c.get("findings") or [])] or ["- (chưa có)"]
    tai_hien = [f"- {r}" for r in (c.get("reproduction") or [])] or ["- (chưa có)"]
    dong = [
        f"**Sự cố:** `{c['incident_id']}` · mức độ **{c['severity']}** · trạng thái `{c['status']}`",
        f"**Phân hệ:** {c['subsystem']} · **Trang:** `{c['route']}`",
        f"**Người bị ảnh hưởng:** {c['affected_count']} · **Số lần:** {c['event_count']} · **Báo cáo:** {c['report_count']}",
        f"**Build:** {', '.join(c.get('builds') or []) or 'unknown'}",
        f"**Trình duyệt:** {', '.join(f'{k} ({v})' for k, v in (c.get('browsers') or {}).items()) or '—'}",
        f"**Thiết bị:** {', '.join(f'{k} ({v})' for k, v in (c.get('devices') or {}).items()) or '—'}",
        "", "### Chữ ký lỗi (đã chuẩn hoá)", f"`{c['error_signature']}`",
        "", "### Kiểm tra đã chạy (chỉ đọc)",
        *[f"- **{k.get('tool')}** — {k.get('status')}: {k.get('summary')}" for k in (c.get("checks") or [])],
        "", "### Phát hiện", *phat_hien,
        "", "### Tái hiện", *tai_hien,
        "", "_Bản nháp do Trung tâm hỗ trợ Fanfic World tạo — đã làm sạch, không chứa token/email/URL ký. "
        "Kiểm tra lại trước khi đăng._",
    ]
    than = "\n".join(sach_chuoi(d, 600) if d and not d.startswith(("#", "`")) else d for d in dong)
    ra: Dict[str, Any] = {"title": tieu_de, "body": than, "labels": ["support", c["subsystem"], c["severity"]]}
    repo = _repo(env)
    if repo:
        # Cat than cho vua URL (GitHub gioi han ~8KB); du lieu day du o "body".
        ra["new_issue_url"] = (f"https://github.com/{repo}/issues/new?title={quote(tieu_de)}"
                               f"&body={quote(than[:5000])}&labels={quote(','.join(ra['labels']))}")
    return ra


def build_support_admin_router(rt: SupportRuntime, *, admin_dep: Callable[..., Any]) -> APIRouter:
    r = APIRouter()

    def _su_co(incident_id: str):
        inc = rt.store.get_incident(incident_id) if re.match(r"^INC-[A-Z2-9]{6}$", incident_id or "") else None
        if inc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy sự cố.")
        return inc

    @r.get("/api/admin/support/summary")
    def support_summary(admin=Depends(admin_dep)) -> dict:
        return {**rt.store.summary(), "ai_available": rt.engine.ai_available}

    @r.get("/api/admin/support/incidents")
    def support_incidents(status_filter: str = "", subsystem: str = "", severity: str = "", build: str = "",
                          route: str = "", unresolved: bool = False, q: str = "", limit: int = 50, offset: int = 0,
                          admin=Depends(admin_dep)) -> dict:
        if status_filter and status_filter not in TRANG_THAI:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Trạng thái lọc không hợp lệ.")
        if subsystem and subsystem not in PHAN_HE:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Phân hệ lọc không hợp lệ.")
        if severity and severity not in MUC_DO:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mức độ lọc không hợp lệ.")
        return rt.store.list_incidents(status=status_filter, subsystem=subsystem, severity=severity,
                                       build=build[:40], route=route[:120], unresolved=unresolved, q=q[:80],
                                       limit=max(1, min(100, limit)), offset=max(0, offset))

    @r.get("/api/admin/support/incidents/{incident_id}")
    def support_incident(incident_id: str, admin=Depends(admin_dep)) -> dict:
        inc = _su_co(incident_id)
        ct = inc.chi_tiet()
        bao_cao = [rt.store.get_report(i) for i in inc.report_ids[-20:]]
        ct["reports"] = [{"report_id": b.report_id, "summary": b.summary, "created_at": b.created_at,
                          "status": b.status, "browser": b.browser, "device": b.device, "build": b.build,
                          "reporter": "user" if b.reporter_user_id else "guest",
                          "reporter_user_id": b.reporter_user_id} for b in bao_cao if b is not None]
        return ct

    @r.post("/api/admin/support/incidents/{incident_id}/status")
    def support_incident_status(incident_id: str, payload: StatusIn, admin=Depends(admin_dep)) -> dict:
        _su_co(incident_id)
        if payload.status not in TRANG_THAI:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Trạng thái không hợp lệ.")
        inc = rt.store.set_incident_status(incident_id, payload.status, actor=f"admin:{admin.user_id[:12]}",
                                           note=sach_chuoi(payload.note, 300))
        return inc.tom_tat()

    @r.get("/api/admin/support/incidents/{incident_id}/issue-draft")
    def support_issue_draft(incident_id: str, admin=Depends(admin_dep)) -> dict:
        inc = _su_co(incident_id)
        return ban_nhap_issue(inc.chi_tiet())

    @r.get("/api/admin/support/reports")
    def support_reports(limit: int = 30, status_filter: str = "", admin=Depends(admin_dep)) -> dict:
        ds = rt.store.list_reports(limit=max(1, min(100, limit)), status=status_filter if status_filter in ("new", "resolved") else "")
        return {"items": [{"report_id": b.report_id, "summary": b.summary, "route": b.route, "subsystem": b.subsystem,
                           "status": b.status, "created_at": b.created_at, "incident_id": b.incident_id,
                           "browser": b.browser, "device": b.device, "build": b.build,
                           "reporter": "user" if b.reporter_user_id else "guest"} for b in ds]}

    return r
