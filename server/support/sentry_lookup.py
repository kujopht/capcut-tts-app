"""
Tra Sentry CHI DOC cho Fanfic AI Support — TAT khi khong co `FAS_SUPPORT_SENTRY_TOKEN`.

Token (read-only: `event:read`, `org:read`, `project:read`) chi song TRONG doi tuong `SentryChiDoc`:
khong bao gio nam trong ket qua cong cu, trong log, hay trong loi nhan gui mo hinh AI (`__repr__`
khong in no). Ba rao, moi rao co bai test canh:

1. DANH SACH TRANG endpoint: CHI `GET`, CHI hai mau duong co dinh (danh sach issue cua mot project
   da cau hinh; su kien moi nhat cua mot issue id so), CHI goc `https://sentry.io|us.|de.`. Khong co
   duong nao nhan URL, ten may hay duong dan tu nguoi dung — khong SSRF, khong fetch tuy y.
2. MAY CHU dung cau truy van: chi tu ma loi / mau route da lam sach (`[a-z0-9_/[\\].-]`), khong bao
   gio dua thang tin nhan nguoi dung vao Sentry.
3. KET QUA DA LAM SACH + TOI THIEU: chi so dem, thoi diem, muc do, co trung build/route khong.
   Tieu de/culprit (van la thong diep loi) chi tra cho QUAN TRI (`chi_tiet=True`), va cung qua
   `sach_chuoi`. Nguoi dung thuong va mo hinh AI chi thay "co N loi tuong tu, lan cuoi luc nao".
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from server.support.sanitize import sach_chuoi

GOC_CHO_PHEP = ("https://sentry.io", "https://us.sentry.io", "https://de.sentry.io")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_MAU_DUONG = (
    re.compile(r"^/api/0/projects/(?P<org>[a-z0-9-]{1,64})/(?P<proj>[a-z0-9-]{1,64})/issues/$"),
    re.compile(r"^/api/0/issues/(?P<id>\d{1,20})/events/latest/$"),
)
_THAM_SO_CHO_PHEP = frozenset({"query", "statsPeriod", "limit"})
_TU_TRUY_VAN = re.compile(r"^[A-Za-z0-9_/\[\].-]{1,80}$")


class SentryBiTuChoi(RuntimeError):
    """Mot yeu cau ngoai danh sach trang — KHONG BAO GIO duoc gui di."""


class SentryChiDoc:
    def __init__(self, token: str, org: str, projects: Tuple[str, ...], goc: str = "https://sentry.io",
                 *, http: Any = None, timeout: float = 2.5) -> None:
        if goc not in GOC_CHO_PHEP:
            raise SentryBiTuChoi(f"Gốc Sentry không nằm trong danh sách cho phép: {goc!r}")
        if not _SLUG.match(org or "") or not projects or not all(_SLUG.match(p) for p in projects):
            raise SentryBiTuChoi("Slug org/project Sentry không hợp lệ.")
        # Token nam trong CLOSURE, khong phai thuoc tinh: `vars()`/log doi tuong khong bao gio thay no
        # (thuoc tinh name-mangled `__token` VAN hien trong `vars()` — do bang bai test).
        def _headers(tk: str = token) -> Dict[str, str]:
            return {"Authorization": f"Bearer {tk}", "Accept": "application/json"}

        self._headers = _headers
        self.org, self.projects, self.goc = org, tuple(projects), goc
        self._http, self._timeout = http, timeout

    def __repr__(self) -> str:  # KHONG BAO GIO in token
        return f"SentryChiDoc(org={self.org!r}, projects={self.projects!r}, goc={self.goc!r})"

    @classmethod
    def tu_moi_truong(cls, env: Optional[Mapping[str, str]] = None) -> Optional["SentryChiDoc"]:
        env = os.environ if env is None else env
        token = (env.get("FAS_SUPPORT_SENTRY_TOKEN") or "").strip()
        org = (env.get("FAS_SUPPORT_SENTRY_ORG") or "").strip()
        projects = tuple(p.strip() for p in (env.get("FAS_SUPPORT_SENTRY_PROJECTS") or "").split(",") if p.strip())
        if not (token and org and projects):
            return None
        return cls(token, org, projects, (env.get("FAS_SUPPORT_SENTRY_BASE") or "https://sentry.io").strip().rstrip("/"))

    # ------------------------------------------------------------ rao 1
    def _kiem(self, method: str, path: str, params: Dict[str, Any]) -> None:
        if method != "GET":
            raise SentryBiTuChoi("Chỉ GET.")
        khop = next((m.match(path) for m in _MAU_DUONG if m.match(path)), None)
        if khop is None:
            raise SentryBiTuChoi("Đường dẫn Sentry ngoài danh sách trắng.")
        g = khop.groupdict()
        if "org" in g and (g["org"] != self.org or g["proj"] not in self.projects):
            raise SentryBiTuChoi("Org/project không phải của Fanfic.")
        if set(params) - _THAM_SO_CHO_PHEP:
            raise SentryBiTuChoi("Tham số ngoài danh sách trắng.")

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Any]:
        params = dict(params or {})
        self._kiem("GET", path, params)
        import httpx

        c = self._http or httpx
        r = c.get(self.goc + path, params=params, timeout=self._timeout, follow_redirects=False,
                  headers=self._headers())
        try:
            return r.status_code, (r.json() if r.content else None)
        except ValueError:
            return r.status_code, None

    # ------------------------------------------------------------ rao 2 + 3
    @staticmethod
    def tu_truy_van(ma_loi: str = "", route_mau: str = "") -> Optional[str]:
        """Tu khoa tim kiem do MAY CHU chon: ma loi da lam sach, hoac mau route (`/chapters/[id]`)."""
        for t in (ma_loi, route_mau):
            t = (t or "").strip()
            if t and t not in ("/", "/?") and _TU_TRUY_VAN.match(t):
                return t
        return None

    def loi_gan_day(self, *, ma_loi: str = "", route_mau: str = "", build: str = "",
                    chi_tiet: bool = False) -> Dict[str, Any]:
        tu = self.tu_truy_van(ma_loi, route_mau)
        if tu is None:
            return {"trang_thai": "khong_du_ngu_canh"}
        van_de: List[Dict[str, Any]] = []
        for proj in self.projects:
            st, ds = self._get(f"/api/0/projects/{self.org}/{proj}/issues/",
                               {"query": f'is:unresolved "{tu}"', "statsPeriod": "24h", "limit": 5})
            if st != 200 or not isinstance(ds, list):
                continue
            for it in ds[:5]:
                van_de.append({"project": proj, "id": str(it.get("id") or ""), "level": sach_chuoi(str(it.get("level") or ""), 16),
                               "count": _so(it.get("count")), "users": _so(it.get("userCount")),
                               "last_seen": sach_chuoi(str(it.get("lastSeen") or ""), 40),
                               "title": sach_chuoi(str(it.get("title") or ""), 160),
                               "culprit": sach_chuoi(str(it.get("culprit") or ""), 120)})
        van_de.sort(key=lambda v: v["last_seen"], reverse=True)
        cung_build = None
        if van_de and build and build != "unknown" and van_de[0]["id"].isdigit():
            st, ev = self._get(f"/api/0/issues/{van_de[0]['id']}/events/latest/")
            if st == 200 and isinstance(ev, dict):
                tags = {t.get("key"): str(t.get("value") or "") for t in ev.get("tags") or [] if isinstance(t, dict)}
                cung_build = tags.get("build", "")[:10] == build[:10] if tags.get("build") else None
        ra = {"trang_thai": "ok", "tu_khoa": tu, "so_van_de": len(van_de), "tong_su_kien": sum(v["count"] for v in van_de),
              "lan_cuoi": van_de[0]["last_seen"] if van_de else "", "cung_build": cung_build}
        if chi_tiet:  # CHI quan tri — van da qua sach_chuoi
            ra["van_de"] = [{k: v for k, v in d.items() if k != "id"} for d in van_de]
        return ra


def _so(x: Any) -> int:
    try:
        return max(0, int(str(x)))
    except (TypeError, ValueError):
        return 0
