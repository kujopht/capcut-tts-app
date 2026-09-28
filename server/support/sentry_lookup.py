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
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Dict, List, Mapping, Optional, Tuple

from server.support.sanitize import sach_chuoi

GOC_CHO_PHEP = ("https://sentry.io", "https://us.sentry.io", "https://de.sentry.io")
# Tong thoi gian cua MOT lan doi chieu — PHAI nho hon `tools.THOI_GIAN_TOI_DA_GIAY` (3.0 s), neu khong
# hop cong cu cat ngang va buoc nay LUON ra "qua thoi gian". Do that 2026-09-28 (VN -> sentry.io): moi
# GET mot ket noi moi ~1.3-1.5 s, ba GET tuan tu ~4.2 s. Nen: dung lai ket noi, tra cac project SONG SONG,
# va chi goi "su kien moi nhat" khi con du thoi gian.
NGAN_SACH_GIAY = 2.6
_CON_TOI_THIEU_GIAY = 0.25
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
        self._khoa = threading.Lock()

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

    def _ket_noi(self) -> Any:
        """MOT `httpx.Client` dung chung (giu ket noi) — tao luoi, an toan luong."""
        if self._http is None:
            import httpx

            with self._khoa:
                if self._http is None:
                    self._http = httpx.Client(follow_redirects=False)
        return self._http

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None, *,
             timeout: Optional[float] = None) -> Tuple[int, Any]:
        """(ma HTTP, JSON). Loi mang/qua han -> (0, None): nguoi goi KHONG duoc coi do la "khong co loi"."""
        params = dict(params or {})
        self._kiem("GET", path, params)  # truoc MOI ket noi — ngoai danh sach trang thi khong gui gi
        import httpx

        try:
            r = self._ket_noi().get(self.goc + path, params=params, follow_redirects=False,
                                    timeout=self._timeout if timeout is None else timeout, headers=self._headers())
        except httpx.HTTPError:
            return 0, None
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
        han = time.monotonic() + NGAN_SACH_GIAY

        def con() -> float:
            return han - time.monotonic()

        def tim(proj: str) -> Tuple[str, int, Any]:
            st, ds = self._get(f"/api/0/projects/{self.org}/{proj}/issues/",
                               {"query": f'is:unresolved "{tu}"', "statsPeriod": "24h", "limit": 5},
                               timeout=max(_CON_TOI_THIEU_GIAY, min(self._timeout, con())))
            return proj, st, ds

        # SONG SONG: tong thoi gian ~ project cham nhat, khong phai tong cac project. Han chot CUNG bang
        # `wait(timeout=)` — timeout cua httpx tinh theo TUNG PHA (ket noi/doc...), khong phai tong, nen
        # rieng no khong giu duoc ngan sach (do that: 3.3 s voi ngan sach 2.6 s). Luong tre bi BO LAI
        # (khong cho), tu ket thuc theo timeout cua chinh no.
        ex = ThreadPoolExecutor(max_workers=min(4, len(self.projects)) + 1, thread_name_prefix="sentry-ro")
        try:
            tuong_lai = [ex.submit(tim, p) for p in self.projects]
            xong, _ = wait(tuong_lai, timeout=max(0.0, con()))
            tra_ve = [f.result() if f in xong else (p, 0, None) for p, f in zip(self.projects, tuong_lai)]
            ket_qua = self._tong_hop(tu, build, tra_ve, ex, con)
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        if chi_tiet and ket_qua.get("trang_thai") == "ok":  # CHI quan tri — van da qua sach_chuoi
            ket_qua["van_de"] = [{k: v for k, v in d.items() if k != "id"} for d in ket_qua["_van_de"]]
        ket_qua.pop("_van_de", None)
        return ket_qua

    def _tong_hop(self, tu: str, build: str, tra_ve: List[Tuple[str, int, Any]], ex: ThreadPoolExecutor,
                  con: Any) -> Dict[str, Any]:
        van_de: List[Dict[str, Any]] = []
        hong = 0
        for proj, st, ds in tra_ve:
            if st != 200 or not isinstance(ds, list):
                hong += 1
                continue
            for it in ds[:5]:
                if not isinstance(it, dict):
                    continue
                van_de.append({"project": proj, "id": str(it.get("id") or ""), "level": sach_chuoi(str(it.get("level") or ""), 16),
                               "count": _so(it.get("count")), "users": _so(it.get("userCount")),
                               "last_seen": sach_chuoi(str(it.get("lastSeen") or ""), 40),
                               "title": sach_chuoi(str(it.get("title") or ""), 160),
                               "culprit": sach_chuoi(str(it.get("culprit") or ""), 120)})
        # Mot project KHONG tra loi ma cung khong thay van de nao -> KHONG duoc noi "chua ghi nhan"
        # (truoc day loi 401/qua han bi dem thanh 0 van de — mot cau tra loi SAI nghe rat chac chan).
        if hong and not van_de:
            return {"trang_thai": "khong_tra_duoc", "tu_khoa": tu, "so_project_loi": hong}
        van_de.sort(key=lambda v: v["last_seen"], reverse=True)
        cung_build = None  # None = chua biet (khong du thoi gian / khong co the build) — khong phai "khac build"
        if van_de and build and build != "unknown" and van_de[0]["id"].isdigit() and con() >= 2 * _CON_TOI_THIEU_GIAY:
            f = ex.submit(self._get, f"/api/0/issues/{van_de[0]['id']}/events/latest/",
                          timeout=max(_CON_TOI_THIEU_GIAY, min(self._timeout, con())))
            xong, _ = wait([f], timeout=max(0.0, con()))
            st, ev = f.result() if xong else (0, None)
            if st == 200 and isinstance(ev, dict):
                tags = {t.get("key"): str(t.get("value") or "") for t in ev.get("tags") or [] if isinstance(t, dict)}
                cung_build = tags.get("build", "")[:10] == build[:10] if tags.get("build") else None
        return {"trang_thai": "ok", "tu_khoa": tu, "so_van_de": len(van_de), "tong_su_kien": sum(v["count"] for v in van_de),
                "lan_cuoi": van_de[0]["last_seen"] if van_de else "", "cung_build": cung_build,
                "day_du": not hong, "_van_de": van_de}


def _so(x: Any) -> int:
    try:
        return max(0, int(str(x)))
    except (TypeError, ValueError):
        return 0
