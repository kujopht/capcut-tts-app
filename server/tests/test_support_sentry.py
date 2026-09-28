"""
AI Support <-> Sentry (`server/support/sentry_lookup.py` + cong cu `get_recent_sentry_issues`).

KHONG goi mang: client HTTP GIA ghi lai MOI request. Canh ba rao:
  1. danh sach trang endpoint (chi GET, hai mau duong, goc Sentry co dinh, org/project da cau hinh);
  2. tu khoa do MAY CHU chon (khong bao gio la tin nhan nguoi dung);
  3. token KHONG BAO GIO nam trong ket qua cong cu, repr, phan hoi API hay loi nhan gui mo hinh AI.
"""

from __future__ import annotations

import json
import os
import unittest
from typing import Any, Dict, List
from unittest.mock import patch

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.rate_limit import limiter as tier_limiter
from server.support.engine import SupportContext, lap_ke_hoach
from server.support.sentry_lookup import SentryBiTuChoi, SentryChiDoc
from server.support.store import InMemorySupportStore

# Token GIA — ghep luc chay (xem .gitleaksignore muc 7/8 ve vi sao).
TOKEN = "cd" * 16 + "ef" * 16
ORG, PROJ = "university-of-information-t-lp", ("fanfic-web", "python-fastapi")


class _Resp:
    def __init__(self, status: int, body: Any):
        self.status_code, self._b, self.content = status, body, b"x"

    def json(self):
        return self._b


class _HttpGia:
    def __init__(self, issues=None, tags=None):
        self.goi: List[Dict[str, Any]] = []
        self.issues = issues if issues is not None else [
            {"id": "123", "title": "RuntimeError: audio_media nguoi.dung@vidu.vn", "culprit": "play()",
             "level": "error", "count": "7", "userCount": 3, "lastSeen": "2026-09-28T07:00:00Z"}]
        self.tags = tags if tags is not None else [{"key": "build", "value": "a1b2c3d4e5"}]

    def get(self, url, *, params=None, timeout=None, follow_redirects=None, headers=None):
        self.goi.append({"url": url, "params": dict(params or {}), "follow_redirects": follow_redirects,
                         "auth": (headers or {}).get("Authorization", "")})
        if url.endswith("/issues/"):
            return _Resp(200, self.issues if "fanfic-web" in url else [])
        if url.endswith("/events/latest/"):
            return _Resp(200, {"tags": self.tags})
        return _Resp(404, {})


def _sentry(http=None):
    return SentryChiDoc(TOKEN, ORG, PROJ, http=http or _HttpGia())


class DanhSachTrangTest(unittest.TestCase):
    def test_tat_khi_thieu_cau_hinh(self):
        self.assertIsNone(SentryChiDoc.tu_moi_truong({}))
        self.assertIsNone(SentryChiDoc.tu_moi_truong({"FAS_SUPPORT_SENTRY_TOKEN": TOKEN}))
        s = SentryChiDoc.tu_moi_truong({"FAS_SUPPORT_SENTRY_TOKEN": TOKEN, "FAS_SUPPORT_SENTRY_ORG": ORG,
                                        "FAS_SUPPORT_SENTRY_PROJECTS": "fanfic-web, python-fastapi"})
        self.assertEqual(s.projects, PROJ)

    def test_goc_va_slug_ngoai_danh_sach_bi_tu_choi(self):
        for goc in ("http://sentry.io", "https://sentry.io.evil.example", "https://evil.example", "https://169.254.169.254"):
            with self.subTest(goc=goc), self.assertRaises(SentryBiTuChoi):
                SentryChiDoc(TOKEN, ORG, PROJ, goc)
        with self.assertRaises(SentryBiTuChoi):
            SentryChiDoc(TOKEN, "Org Co Dau Cach", PROJ)
        with self.assertRaises(SentryBiTuChoi):
            SentryChiDoc(TOKEN, ORG, ("../x",))

    def test_chi_get_chi_hai_mau_duong_chi_org_project_cua_fanfic(self):
        s = _sentry()
        sai = [("POST", f"/api/0/projects/{ORG}/fanfic-web/issues/", {}),
               ("DELETE", "/api/0/issues/123/events/latest/", {}),
               ("GET", f"/api/0/organizations/{ORG}/members/", {}),
               ("GET", f"/api/0/projects/org-khac/fanfic-web/issues/", {}),
               ("GET", f"/api/0/projects/{ORG}/project-khac/issues/", {}),
               ("GET", "/api/0/issues/abc/events/latest/", {}),
               ("GET", f"/api/0/projects/{ORG}/fanfic-web/issues/../../../", {}),
               ("GET", f"/api/0/projects/{ORG}/fanfic-web/issues/", {"cursor": "x"})]
        for m, p, q in sai:
            with self.subTest(m=m, p=p, q=q), self.assertRaises(SentryBiTuChoi):
                s._kiem(m, p, q)
        s._kiem("GET", f"/api/0/projects/{ORG}/fanfic-web/issues/", {"query": "x", "statsPeriod": "24h", "limit": 5})
        s._kiem("GET", "/api/0/issues/123/events/latest/", {})

    def test_repr_khong_lo_token(self):
        self.assertNotIn(TOKEN, repr(_sentry()))
        self.assertNotIn(TOKEN, str(vars(_sentry())))  # ca khi soi thuoc tinh cong khai


class TuKhoaVaKetQuaTest(unittest.TestCase):
    def test_tu_khoa_chi_tu_ma_loi_hoac_mau_route(self):
        self.assertEqual(SentryChiDoc.tu_truy_van("audio_media", "/chapters/[id]"), "audio_media")
        self.assertEqual(SentryChiDoc.tu_truy_van("", "/chapters/[id]"), "/chapters/[id]")
        for xau in ('x" OR is:resolved', "https://evil.example", "a b", "", "/?"):
            self.assertIsNone(SentryChiDoc.tu_truy_van(xau, ""), xau)

    def test_ket_qua_toi_thieu_va_tuong_quan_build(self):
        http = _HttpGia()
        kq = _sentry(http).loi_gan_day(ma_loi="audio_media", build="a1b2c3d4e5")
        self.assertEqual((kq["so_van_de"], kq["tong_su_kien"], kq["cung_build"]), (1, 7, True))
        self.assertNotIn("van_de", kq, "người dùng thường không được thấy tiêu đề lỗi")
        # Moi request: GET, dung goc, khong theo chuyen huong, query do MAY CHU dung.
        for g in http.goi:
            self.assertTrue(g["url"].startswith("https://sentry.io/api/0/"), g["url"])
            self.assertIs(g["follow_redirects"], False)
        self.assertEqual(http.goi[0]["params"]["query"], 'is:unresolved "audio_media"')
        chi_tiet = _sentry(_HttpGia()).loi_gan_day(ma_loi="audio_media", chi_tiet=True)
        self.assertNotIn("nguoi.dung@vidu.vn", json.dumps(chi_tiet, ensure_ascii=False))

    def test_khong_du_ngu_canh_thi_khong_goi_mang(self):
        http = _HttpGia()
        self.assertEqual(_sentry(http).loi_gan_day(ma_loi="", route_mau="/?")["trang_thai"], "khong_du_ngu_canh")
        self.assertEqual(http.goi, [])


class KeHoachTest(unittest.TestCase):
    def test_chi_doi_chieu_khi_co_ma_loi_that(self):
        co = lap_ke_hoach("trang bị lỗi", SupportContext(route="/chapters/[id]", last_error_code="audio_media"))
        self.assertIn("get_recent_sentry_issues", [t for t, _ in co])
        khong = lap_ke_hoach("trang bị lỗi", SupportContext(route="/chapters/[id]"))
        self.assertNotIn("get_recent_sentry_issues", [t for t, _ in khong])


class QuaApiTest(unittest.TestCase):
    """Duong THAT: /api/support/ask -> cong cu -> (tuy chon) mo hinh — token khong lot o dau."""

    def setUp(self) -> None:
        tier_limiter.reset()
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self.rt = server_main.support_runtime
        s = InMemorySupportStore()
        self.rt.store, self.rt.toolbox.store, self.rt.engine.store = s, s, s
        self.rt.limiter.reset()
        self.http = _HttpGia()
        self._cu_sentry, self._cu_gw = self.rt.toolbox.sentry, self.rt.engine.gateway
        self.rt.toolbox.sentry = _sentry(self.http)
        self.client = TestClient(server_main.app)
        self._env = patch.dict(os.environ, {"FAS_SUPPORT_V1": "1"})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self.rt.toolbox.sentry, self.rt.engine.gateway = self._cu_sentry, self._cu_gw

    def _hoi(self):
        return self.client.post("/api/support/ask", json={
            "message": "audio không phát được, lỗi gì vậy?", "session_id": "phienkhachSENTRY01",
            "context": {"route": "/chapters/chp_abc", "last_error_code": "audio_media", "build": "a1b2c3d4e5"}})

    def test_ket_qua_co_doi_chieu_va_khong_lo_token_hay_tieu_de(self):
        r = self._hoi()
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        ck = [c for c in d["checks"] if c["tool"] == "get_recent_sentry_issues"]
        self.assertEqual(len(ck), 1)
        self.assertEqual(ck[0]["status"], "warn")
        self.assertIn("1 lỗi tương tự", ck[0]["summary"])
        self.assertIn("error_tracked", [f["code"] for f in d["findings"]])
        than = r.text
        self.assertNotIn(TOKEN, than)
        self.assertNotIn("RuntimeError", than, "tiêu đề lỗi Sentry không được tới người dùng")
        self.assertTrue(self.http.goi and all(g["auth"] == f"Bearer {TOKEN}" for g in self.http.goi))

    def test_loi_nhan_gui_mo_hinh_khong_co_token(self):
        class Gw:
            def __init__(self):
                self.goi = []

            def complete(self, system, user, *, task_kind):
                self.goi.append(system + "\n" + user)
                return "Thử tải lại trang."

        gw = Gw()
        self.rt.engine.gateway = gw
        self.assertEqual(self._hoi().status_code, 200)
        self.assertTrue(gw.goi, "mô hình phải được gọi trong bài này")
        for p in gw.goi:
            self.assertNotIn(TOKEN, p)
            self.assertNotIn("RuntimeError", p)


if __name__ == "__main__":
    unittest.main()
