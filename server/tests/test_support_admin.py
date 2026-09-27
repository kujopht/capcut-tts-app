"""
Fanfic AI Support V1 — Trung tam ho tro cho quan tri (`/api/admin/support/*`).

Tao nguoi dung qua ADAPTER va xoa bo dem Tier o setUp (xem ghi chu o
`test_support_v1.py`). Quyen admin cap bang cach them user_id vao
`settings.admin_user_ids` CUA TIEN TRINH TEST, tra lai nguyen trang khi xong.
"""
from __future__ import annotations

import json
import os
import unittest
from typing import Dict
from unittest.mock import patch

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.rate_limit import limiter as tier_limiter
from server.support.admin_routes import ban_nhap_issue
from server.support.store import InMemorySupportStore

DUONG = ["/api/admin/support/summary", "/api/admin/support/incidents", "/api/admin/support/reports"]
# Chuoi HINH DANG token (gia) cho bai lam sach ban nhap issue — ghep luc chay de
# tep nguon khong chua literal khop luat gitleaks (xem test_support_v1.py).
TOK_GIA = "eyJabc" + ".def.ghi"


class _Co(unittest.TestCase):
    def setUp(self) -> None:
        tier_limiter.reset()
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        rt = server_main.support_runtime
        s = InMemorySupportStore()
        rt.store, rt.toolbox.store, rt.engine.store = s, s, s
        rt.limiter.reset()
        self.rt = rt
        self.client = TestClient(server_main.app)
        env = patch.dict(os.environ, {"FAS_SUPPORT_V1": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.tok_ad, uid_ad = self.user("admin@example.com")
        cu = server_main.settings.admin_user_ids
        object.__setattr__(server_main.settings, "admin_user_ids", tuple(cu) + (uid_ad,))
        self.addCleanup(object.__setattr__, server_main.settings, "admin_user_ids", cu)
        self.tok_th, _ = self.user("thuong@example.com")

    def user(self, email: str):
        p = server_main.identity.register(email, "matkhau123", email.split("@")[0])
        return server_main.identity.login(email, "matkhau123"), p.user_id

    @staticmethod
    def auth(tok: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {tok}"}

    def loi(self, sid: str, cid: str, msg: str = "GET /api/chapters/{c} failed 503"):
        return self.client.post("/api/support/client-errors", json={"session_id": sid, "events": [
            {"kind": "api_error", "code": "api_5xx", "route": f"/chapters/{cid}", "message": msg.format(c=cid),
             "build": "abc1234", "browser": "chrome", "device": "mobile"}]})


class TestQuyen(_Co):
    def test_khach_401_nguoi_thuong_403(self):
        for d in DUONG:
            self.assertEqual(self.client.get(d).status_code, 401, d)
            self.assertEqual(self.client.get(d, headers=self.auth(self.tok_th)).status_code, 403, d)
        self.assertEqual(self.client.post("/api/admin/support/incidents/INC-AAAAAA/status", json={"status": "resolved"},
                                          headers=self.auth(self.tok_th)).status_code, 403)


class TestTrungTam(_Co):
    def test_gom_nhom_va_so_lieu_tong(self):
        for i, sid in enumerate(["phienkhachAAAA0000", "phienkhachBBBB1111", "phienkhachCCCC2222"]):
            self.assertEqual(self.loi(sid, f"chp_{i}aaaa1111bbbb").status_code, 202)
        self.client.post("/api/support/reports", json={"summary": "Không nghe được", "session_id": "phienkhachAAAA0000",
                                                       "context": {"route": "/chapters/chp_x", "last_error_code": "audio_media"}})
        tong = self.client.get("/api/admin/support/summary", headers=self.auth(self.tok_ad)).json()
        self.assertEqual((tong["open_incidents"], tong["new_reports"]), (2, 1))
        ds = self.client.get("/api/admin/support/incidents", headers=self.auth(self.tok_ad)).json()
        api = [i for i in ds["items"] if i["subsystem"] == "api"]
        self.assertEqual(len(api), 1, "3 loi giong nhau o 3 chuong -> MOT su co")
        self.assertEqual((api[0]["event_count"], api[0]["affected_count"], api[0]["severity"]), (3, 3, "high"))

    def test_loc_va_tu_choi_bo_loc_la(self):
        self.loi("phienkhachAAAA0000", "chp_1aaaa1111bbbb")
        h = self.auth(self.tok_ad)
        self.assertEqual(self.client.get("/api/admin/support/incidents?subsystem=api", headers=h).json()["total"], 1)
        self.assertEqual(self.client.get("/api/admin/support/incidents?subsystem=audio", headers=h).json()["total"], 0)
        self.assertEqual(self.client.get("/api/admin/support/incidents?build=abc1234", headers=h).json()["total"], 1)
        self.assertEqual(self.client.get("/api/admin/support/incidents?route=/chapters/[id]", headers=h).json()["total"], 1)
        self.assertEqual(self.client.get("/api/admin/support/incidents?status_filter=xoa-het", headers=h).status_code, 400)
        self.assertEqual(self.client.get("/api/admin/support/incidents?severity=apocalypse", headers=h).status_code, 400)

    def test_doi_trang_thai_ghi_dong_thoi_gian(self):
        self.loi("phienkhachAAAA0000", "chp_1aaaa1111bbbb")
        h = self.auth(self.tok_ad)
        iid = self.client.get("/api/admin/support/incidents", headers=h).json()["items"][0]["incident_id"]
        r = self.client.post(f"/api/admin/support/incidents/{iid}/status", json={"status": "resolved", "note": "đã sửa ở #999"}, headers=h)
        self.assertEqual((r.status_code, r.json()["status"]), (200, "resolved"))
        ct = self.client.get(f"/api/admin/support/incidents/{iid}", headers=h).json()
        self.assertEqual(ct["timeline"][-1]["kind"], "status")
        self.assertIn("→ resolved — đã sửa ở #999", ct["timeline"][-1]["text"])
        self.assertEqual(self.client.post(f"/api/admin/support/incidents/{iid}/status", json={"status": "deleted"}, headers=h).status_code, 400)
        self.assertEqual(self.client.get("/api/admin/support/incidents/INC-KHONGCO", headers=h).status_code, 404)
        self.assertEqual(self.client.get("/api/admin/support/incidents/../../etc", headers=h).status_code, 404)

    def test_ban_nhap_issue_da_lam_sach_va_chi_chuan_bi(self):
        self.loi("phienkhachAAAA0000", "chp_1aaaa1111bbbb", "failed token=" + TOK_GIA + " user me@x.com {c}")
        h = self.auth(self.tok_ad)
        iid = self.client.get("/api/admin/support/incidents", headers=h).json()["items"][0]["incident_id"]
        with patch.dict(os.environ, {"FAS_SUPPORT_GITHUB_REPO": ""}):
            d = self.client.get(f"/api/admin/support/incidents/{iid}/issue-draft", headers=h).json()
        self.assertNotIn("new_issue_url", d)
        than = json.dumps(d, ensure_ascii=False)
        for lo in ("eyJabc", "me@x.com"):
            self.assertNotIn(lo, than)
        self.assertIn(iid, d["title"])
        self.assertIn("support", d["labels"])
        with patch.dict(os.environ, {"FAS_SUPPORT_GITHUB_REPO": "kujopht/capcut-tts-app"}):
            d2 = self.client.get(f"/api/admin/support/incidents/{iid}/issue-draft", headers=h).json()
        self.assertTrue(d2["new_issue_url"].startswith("https://github.com/kujopht/capcut-tts-app/issues/new?title="))
        self.assertIsNone(ban_nhap_issue(self.rt.store.get_incident(iid).chi_tiet(),
                                         {"FAS_SUPPORT_GITHUB_REPO": "evil.example/x/y?z"}).get("new_issue_url"))

    def test_danh_sach_bao_cao(self):
        self.client.post("/api/support/reports", headers=self.auth(self.tok_th),
                         json={"summary": "Studio không mở", "session_id": "phienkhachAAAA0000", "context": {"route": "/studio"}})
        ds = self.client.get("/api/admin/support/reports", headers=self.auth(self.tok_ad)).json()["items"]
        self.assertEqual(len(ds), 1)
        self.assertEqual((ds[0]["reporter"], ds[0]["subsystem"]), ("user", "studio"))


if __name__ == "__main__":
    unittest.main()
