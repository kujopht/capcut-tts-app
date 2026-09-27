"""
Kho du lieu Fanfic AI Support — su kien loi client, bao cao, su co gom nhom.

`InMemorySupportStore` la hien thuc DUY NHAT o V1: bo nho tien trinh, CO GIOI
HAN (so su co/su kien/bao cao toi da) va CO HAN LUU (mac dinh 14 ngay, don
theo lan ghi). Mat khi khoi dong lai — chap nhan duoc cho V1 vi day la du
lieu van hanh, khong phai du lieu nguoi dung; schema Appwrite de xuat o
`docs/support/SUPPORT_STORAGE_PROPOSAL.md`, KHONG migrate trong PR nay.

GOM NHOM: moi su kien/bao cao mang mot `fingerprint` (`sanitize.dau_van_tay`:
trang + loi chuan + phan he). Cung fingerprint -> CUNG mot su co; 50 bao cao
giong nhau la 1 su co voi `event_count = 50`, khong phai 50 su co.
"""
from __future__ import annotations

import secrets
import threading
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Deque, Dict, Iterable, List, Optional, Set

TRANG_THAI = ("new", "open", "ai_diagnosed", "needs_owner", "resolved")
MUC_DO = ("low", "medium", "high", "critical")
PHAN_HE = ("audio", "reader", "studio", "api", "storage", "auth", "chat", "support", "web", "unknown")

_BANG_CHU = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # khong co 0/O/1/I de doc qua dien thoai


def ma_ngan(tien_to: str, do_dai: int = 6) -> str:
    return tien_to + "".join(secrets.choice(_BANG_CHU) for _ in range(do_dai))


@dataclass
class ClientErrorEvent:
    kind: str
    route: str
    message: str
    code: str
    subsystem: str
    build: str
    browser: str
    device: str
    owner_key: str
    fingerprint: str
    at: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: ma_ngan("EV-", 8))


@dataclass
class SupportReport:
    report_id: str
    summary: str
    route: str
    build: str
    browser: str
    device: str
    error_signature: str
    fingerprint: str
    subsystem: str
    severity: str
    checks: List[Dict[str, Any]]
    findings: List[Dict[str, Any]]
    evidence: List[str]
    reproduction: List[str]
    owner_key: str
    reporter_user_id: Optional[str]
    diagnostic_id: Optional[str]
    ai_mode: str
    status: str = "new"
    incident_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def cong_khai(self) -> Dict[str, Any]:
        """Phan nguoi GUI bao cao duoc xem lai (khong co owner_key/ban noi bo)."""
        return {"report_id": self.report_id, "status": self.status, "summary": self.summary,
                "route": self.route, "created_at": self.created_at, "subsystem": self.subsystem}


@dataclass
class Incident:
    incident_id: str
    fingerprint: str
    title: str
    subsystem: str
    route: str
    error_signature: str
    severity: str = "low"
    status: str = "new"
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    event_count: int = 0
    report_ids: List[str] = field(default_factory=list)
    affected: Set[str] = field(default_factory=set)
    routes: Counter = field(default_factory=Counter)
    builds: Counter = field(default_factory=Counter)
    browsers: Counter = field(default_factory=Counter)
    devices: Counter = field(default_factory=Counter)
    kinds: Counter = field(default_factory=Counter)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    last_checks: List[Dict[str, Any]] = field(default_factory=list)
    last_findings: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    reproduction: List[str] = field(default_factory=list)
    ai_diagnosed: bool = False
    owner_needed: bool = False

    def tom_tat(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id, "fingerprint": self.fingerprint, "title": self.title,
            "subsystem": self.subsystem, "route": self.route, "severity": self.severity,
            "status": self.status, "first_seen": self.first_seen, "last_seen": self.last_seen,
            "event_count": self.event_count, "report_count": len(self.report_ids),
            "affected_count": len(self.affected), "builds": [b for b, _ in self.builds.most_common(5)],
            "browsers": dict(self.browsers.most_common(5)), "devices": dict(self.devices.most_common(4)),
            "ai_diagnosed": self.ai_diagnosed, "owner_needed": self.owner_needed,
            "error_signature": self.error_signature,
        }

    def chi_tiet(self) -> Dict[str, Any]:
        return {**self.tom_tat(), "routes": dict(self.routes.most_common(10)),
                "builds_all": dict(self.builds.most_common(20)), "kinds": dict(self.kinds),
                "timeline": list(self.timeline[-100:]), "report_ids": list(self.report_ids[-50:]),
                "checks": self.last_checks, "findings": self.last_findings,
                "evidence": self.evidence[-20:], "reproduction": self.reproduction[-10:]}


@dataclass
class DiagnosticRun:
    diagnostic_id: str
    owner_key: str
    context: Dict[str, Any]
    checks: List[Dict[str, Any]]
    findings: List[Dict[str, Any]]
    subsystem: str
    denied: List[str]
    ai_mode: str
    created_at: float = field(default_factory=time.time)


def muc_do_cho(inc: Incident) -> str:
    """Muc do TAT DINH — so nguoi bi anh huong + loai loi + phan he."""
    n = len(inc.affected)
    ha_tang = inc.subsystem in ("api", "storage")
    if ha_tang and n >= 10:
        return "critical"
    if inc.kinds.get("render_error") or n >= 3 or ha_tang:
        return "high"
    if inc.report_ids:
        return "medium"
    return "low"


class InMemorySupportStore:
    """Xem docstring module. Moi phuong thuc lay khoa — goi an toan tu nhieu luong."""

    def __init__(self, *, max_incidents: int = 500, max_events: int = 5000, max_reports: int = 2000,
                 max_diagnostics: int = 2000, retention_seconds: float = 14 * 86400,
                 diagnostic_ttl_seconds: float = 1800, clock=time.time) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self._max_inc, self._max_ev, self._max_rep, self._max_diag = max_incidents, max_events, max_reports, max_diagnostics
        self._han_luu, self._han_diag = retention_seconds, diagnostic_ttl_seconds
        self._incidents: Dict[str, Incident] = {}
        self._theo_van_tay: Dict[str, str] = {}
        self._events: Deque[ClientErrorEvent] = deque()
        self._reports: Dict[str, SupportReport] = {}
        self._diag: Dict[str, DiagnosticRun] = {}

    # ------------------------------------------------------------ noi bo
    def _don(self) -> None:
        bay = self._clock()
        while self._events and (bay - self._events[0].at > self._han_luu or len(self._events) > self._max_ev):
            self._events.popleft()
        for rid in [r for r, x in self._reports.items() if bay - x.created_at > self._han_luu]:
            del self._reports[rid]
        while len(self._reports) > self._max_rep:
            del self._reports[min(self._reports, key=lambda k: self._reports[k].created_at)]
        for iid in [i for i, x in self._incidents.items() if bay - x.last_seen > self._han_luu]:
            self._theo_van_tay.pop(self._incidents[iid].fingerprint, None)
            del self._incidents[iid]
        while len(self._incidents) > self._max_inc:
            cu = min(self._incidents, key=lambda k: self._incidents[k].last_seen)
            self._theo_van_tay.pop(self._incidents[cu].fingerprint, None)
            del self._incidents[cu]
        for did in [d for d, x in self._diag.items() if bay - x.created_at > self._han_diag]:
            del self._diag[did]
        while len(self._diag) > self._max_diag:
            del self._diag[min(self._diag, key=lambda k: self._diag[k].created_at)]

    def _su_co(self, fingerprint: str, *, title: str, subsystem: str, route: str, signature: str) -> Incident:
        iid = self._theo_van_tay.get(fingerprint)
        if iid and iid in self._incidents:
            return self._incidents[iid]
        inc = Incident(incident_id=ma_ngan("INC-"), fingerprint=fingerprint, title=title,
                       subsystem=subsystem, route=route, error_signature=signature,
                       first_seen=self._clock(), last_seen=self._clock())
        inc.timeline.append({"at": inc.first_seen, "kind": "created", "text": "Ghi nhận lần đầu."})
        self._incidents[inc.incident_id] = inc
        self._theo_van_tay[fingerprint] = inc.incident_id
        return inc

    @staticmethod
    def _dong_thoi_gian(inc: Incident, at: float, kind: str, text: str) -> None:
        inc.timeline.append({"at": at, "kind": kind, "text": text})
        if len(inc.timeline) > 100:
            del inc.timeline[: len(inc.timeline) - 100]

    # ------------------------------------------------------------ su kien client
    def add_client_events(self, events: Iterable[ClientErrorEvent]) -> List[str]:
        ra: List[str] = []
        with self._lock:
            for ev in events:
                ev.at = self._clock()
                self._events.append(ev)
                inc = self._su_co(ev.fingerprint, title=ev.message, subsystem=ev.subsystem,
                                  route=ev.route, signature=ev.message)
                moi = inc.event_count == 0
                inc.event_count += 1
                inc.last_seen = ev.at
                if len(inc.affected) < 1000:
                    inc.affected.add(ev.owner_key)
                inc.routes[ev.route] += 1
                inc.builds[ev.build] += 1
                inc.browsers[ev.browser] += 1
                inc.devices[ev.device] += 1
                inc.kinds[ev.kind] += 1
                if inc.status == "resolved":
                    inc.status = "open"
                    self._dong_thoi_gian(inc, ev.at, "reopened", f"Lỗi xuất hiện lại sau khi đã đóng (build {ev.build}).")
                elif moi:
                    self._dong_thoi_gian(inc, ev.at, "event", f"Lỗi {ev.kind} đầu tiên từ client ({ev.browser}/{ev.device}).")
                inc.severity = muc_do_cho(inc)
                ra.append(inc.incident_id)
            self._don()
        return ra

    def events_for_owner(self, owner_key: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            ds = [e for e in self._events if e.owner_key == owner_key][-limit:]
        return [{"kind": e.kind, "route": e.route, "message": e.message, "code": e.code,
                 "subsystem": e.subsystem, "at": e.at} for e in ds]

    # ------------------------------------------------------------ chan doan
    def save_diagnostic(self, run: DiagnosticRun) -> None:
        with self._lock:
            run.created_at = self._clock()
            self._diag[run.diagnostic_id] = run
            self._don()

    def get_diagnostic(self, diagnostic_id: str, owner_key: str) -> Optional[DiagnosticRun]:
        """CHI cua dung chu — id doan trung cua nguoi khac cung tra None."""
        with self._lock:
            run = self._diag.get(diagnostic_id)
            if run is None or run.owner_key != owner_key or self._clock() - run.created_at > self._han_diag:
                return None
            return run

    # ------------------------------------------------------------ bao cao
    def create_report(self, rep: SupportReport) -> SupportReport:
        with self._lock:
            rep.created_at = self._clock()
            inc = self._su_co(rep.fingerprint, title=rep.error_signature or rep.summary[:120],
                              subsystem=rep.subsystem, route=rep.route, signature=rep.error_signature)
            rep.incident_id = inc.incident_id
            self._reports[rep.report_id] = rep
            inc.report_ids.append(rep.report_id)
            if len(inc.report_ids) > 200:
                del inc.report_ids[: len(inc.report_ids) - 200]
            inc.event_count += 1
            inc.last_seen = rep.created_at
            if len(inc.affected) < 1000:
                inc.affected.add(rep.owner_key)
            inc.routes[rep.route] += 1
            inc.builds[rep.build] += 1
            inc.browsers[rep.browser] += 1
            inc.devices[rep.device] += 1
            inc.kinds["report"] += 1
            inc.last_checks, inc.last_findings = rep.checks, rep.findings
            inc.evidence = (inc.evidence + rep.evidence)[-20:]
            inc.reproduction = (inc.reproduction + rep.reproduction)[-10:]
            if any(f.get("owner_needed") for f in rep.findings):
                inc.owner_needed = True
            if any(f.get("confident") for f in rep.findings):
                inc.ai_diagnosed = True
            if inc.status in ("new", "resolved"):
                inc.status = "needs_owner" if inc.owner_needed else ("ai_diagnosed" if inc.ai_diagnosed else "open")
            self._dong_thoi_gian(inc, rep.created_at, "report", f"Báo cáo {rep.report_id} từ người dùng.")
            inc.severity = muc_do_cho(inc)
            self._don()
            return rep

    def get_report(self, report_id: str) -> Optional[SupportReport]:
        with self._lock:
            return self._reports.get(report_id)

    def list_reports(self, *, limit: int = 50, status: str = "") -> List[SupportReport]:
        with self._lock:
            ds = sorted(self._reports.values(), key=lambda r: r.created_at, reverse=True)
        if status:
            ds = [r for r in ds if r.status == status]
        return ds[:limit]

    # ------------------------------------------------------------ su co
    def list_incidents(self, *, status: str = "", subsystem: str = "", severity: str = "", build: str = "",
                       route: str = "", unresolved: bool = False, q: str = "",
                       limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        with self._lock:
            ds = list(self._incidents.values())
        if status:
            ds = [i for i in ds if i.status == status]
        if unresolved:
            ds = [i for i in ds if i.status != "resolved"]
        if subsystem:
            ds = [i for i in ds if i.subsystem == subsystem]
        if severity:
            ds = [i for i in ds if i.severity == severity]
        if build:
            ds = [i for i in ds if build in i.builds]
        if route:
            ds = [i for i in ds if route in i.routes or i.route == route]
        if q:
            ql = q.lower()
            ds = [i for i in ds if ql in i.title.lower() or ql in i.route.lower() or ql in i.incident_id.lower()]
        hang = {m: k for k, m in enumerate(MUC_DO)}
        ds.sort(key=lambda i: (i.status == "resolved", -hang.get(i.severity, 0), -i.last_seen))
        return {"total": len(ds), "items": [i.tom_tat() for i in ds[offset:offset + limit]]}

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        with self._lock:
            return self._incidents.get(incident_id)

    def set_incident_status(self, incident_id: str, status: str, *, actor: str, note: str = "") -> Optional[Incident]:
        if status not in TRANG_THAI:
            raise ValueError("Trạng thái không hợp lệ.")
        with self._lock:
            inc = self._incidents.get(incident_id)
            if inc is None:
                return None
            cu = inc.status
            inc.status = status
            if status == "needs_owner":
                inc.owner_needed = True
            ghi_chu = f" — {note}" if note else ""
            self._dong_thoi_gian(inc, self._clock(), "status", f"{actor}: {cu} → {status}{ghi_chu}")
            for rid in inc.report_ids:
                rep = self._reports.get(rid)
                if rep is not None and status == "resolved":
                    rep.status = "resolved"
            return inc

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            ds = list(self._incidents.values())
            reps = list(self._reports.values())
        dem = Counter(i.status for i in ds)
        return {
            "open_incidents": sum(1 for i in ds if i.status != "resolved"),
            "new_reports": sum(1 for r in reps if r.status == "new"),
            "resolved": dem.get("resolved", 0),
            "ai_diagnosed": sum(1 for i in ds if i.ai_diagnosed and i.status != "resolved"),
            "needs_owner": dem.get("needs_owner", 0),
            "by_status": dict(dem),
            "by_severity": dict(Counter(i.severity for i in ds if i.status != "resolved")),
            "by_subsystem": dict(Counter(i.subsystem for i in ds if i.status != "resolved")),
            "affected_users": len(set().union(*[i.affected for i in ds if i.status != "resolved"])) if ds else 0,
            "persistence": "memory",
        }

    def recent_public_incidents(self, limit: int = 5, max_age_seconds: float = 86400) -> List[Dict[str, Any]]:
        """Su co DANG MO, tu muc 'high' tro len, 24 gio qua — CHI tieu de da lam
        sach + phan he + muc do. Khong nguoi dung, khong route cu the."""
        bay = self._clock()
        with self._lock:
            ds = [i for i in self._incidents.values() if i.status != "resolved"
                  and i.severity in ("high", "critical") and bay - i.last_seen < max_age_seconds]
        ds.sort(key=lambda i: -i.last_seen)
        return [{"subsystem": i.subsystem, "severity": i.severity, "status": i.status,
                 "title": i.title[:120], "last_seen": i.last_seen} for i in ds[:limit]]


def ban_ghi(obj: Any) -> Dict[str, Any]:
    """dataclass -> dict (cho test/debug)."""
    return asdict(obj)
