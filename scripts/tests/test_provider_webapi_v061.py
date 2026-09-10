# -*- coding: utf-8 -*-
"""V0.6.1 — API provider qua tầng web cục bộ: token bắt buộc, không endpoint
nào trả giá trị credential, xoá cần xác nhận, thử kết nối chạy bằng HTTP giả."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

try:
    from fastapi.testclient import TestClient
    CO_FASTAPI = True
except ModuleNotFoundError:                                 # pragma: no cover
    CO_FASTAPI = False

KHOA = "sk-" + "Zz9yY8xX" * 5


def _kho_git(goc: Path) -> None:
    (goc / "docs").mkdir(parents=True, exist_ok=True)
    (goc / "docs" / "seed.md").write_text("seed\n", encoding="utf-8")
    for c in (["git", "init", "-q"], ["git", "config", "user.email", "t@local"],
              ["git", "config", "user.name", "t"], ["git", "add", "-A"],
              ["git", "commit", "-q", "-m", "seed"]):
        subprocess.run(c, cwd=goc, check=True, capture_output=True)


def _http_gia(method, url, headers, body):
    if url.endswith("/models"):
        return 200, json.dumps({"data": [{"id": "qwen-plus"}]}).encode()
    return 200, json.dumps({"choices": [{"message": {"content": "pong"}}]}).encode()


@unittest.skipUnless(CO_FASTAPI, "chưa cài fastapi")
class TestProviderAPI(unittest.TestCase):
    def setUp(self):
        from scripts.control_center.engine import ControlCenter
        from scripts.control_center.model import Project
        from scripts.control_center.providers.adapter import HttpGia
        from scripts.control_center.providers.kho_bi_mat import KhoBiMatBoNho
        from scripts.control_center.webapi import PhienWeb, dung_app
        self.goc = Path(tempfile.mkdtemp(prefix="cc-web-pv-"))
        _kho_git(self.goc)
        self.cc = ControlCenter(root=self.goc, probe=False, kho_bi_mat=KhoBiMatBoNho())
        self.cc.them_project(Project(project_id="p", name="P", repo_path=str(self.goc)))
        self.cc.providers.http = HttpGia(_http_gia)
        self.phien = PhienWeb(self.cc, token="TOKEN-THU-NGHIEM", cong=8765)
        self.cl = TestClient(dung_app(self.phien), base_url="http://127.0.0.1:8765")

    def tearDown(self):
        try:
            self.cc.shutdown()
        except Exception:                                   # noqa: BLE001
            pass
        shutil.rmtree(self.goc, ignore_errors=True)

    @property
    def h(self):
        return {"X-CC-Token": self.phien.token}

    def test_token_bat_buoc(self):
        self.assertEqual(self.cl.get("/api/providers").status_code, 401)
        self.assertEqual(self.cl.post("/api/providers", json={}).status_code, 401)

    def test_vong_doi_va_khong_lo_khoa(self):
        r = self.cl.get("/api/providers", headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertIn("kho_bi_mat", d)
        self.assertEqual(d["kho_bi_mat"]["kieu"], "bo-nho")
        self.assertEqual({p["ma"] for p in d["presets"]},
                         {"openai_compatible", "alibaba_dashscope", "tencent_hunyuan"})
        self.assertFalse(d["chinh_sach"]["auto_routing"])

        r = self.cl.post("/api/providers", headers=self.h,
                         json={"provider_id": "ali", "preset": "alibaba_dashscope"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["base_url"].startswith("https://dashscope"))

        r = self.cl.post("/api/providers/ali/accounts", headers=self.h,
                         json={"alias": "Prod", "gia_tri": KHOA, "project": "p"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn(KHOA, r.text)
        ref = r.json()["credential_ref"]
        acc = r.json()["account_id"]
        self.assertTrue(ref.startswith("ali.prod."))

        r = self.cl.post(f"/api/providers/accounts/{acc}/test", headers=self.h, json={"project": "p"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["ket_qua"]["ok"])
        self.assertNotIn(KHOA, r.text)
        # Fabric DANG SONG (dung truoc khi them provider) phai thay runtime EXT
        # ngay — khong cho khoi dong lai. Fabric cua bo kiem: dung lanh, khong do.
        self.assertIn("EXT_ALI_PROD", self.cc.fabric.runtimes)
        self.assertFalse(self.cc.fabric.runtimes["EXT_ALI_PROD"].dispatchable)
        us = self.cl.get("/api/usage?project=p", headers=self.h).json()
        self.assertIn("EXT_ALI_PROD", [x["runtime_id"] for x in us["runtimes"]])

        r = self.cl.post(f"/api/providers/accounts/{acc}/ask", headers=self.h,
                         json={"model": "qwen-plus", "cau": "ping", "project": "p"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["noi_dung"], "pong")

        r = self.cl.get("/api/providers", headers=self.h)
        self.assertNotIn(KHOA, r.text)
        self.assertEqual(r.json()["tai_khoan"][0]["trang_thai"], "ok")
        self.assertTrue(any(m["nguon"] == "probed" for m in r.json()["models"]["ali"]))

        # Trang thai + usage + su kien: khong dau co khoa.
        for duong in ("/api/state?project=p", "/api/usage?project=p"):
            r = self.cl.get(duong, headers=self.h)
            self.assertEqual(r.status_code, 200)
            self.assertNotIn(KHOA, r.text)

        r = self.cl.post(f"/api/providers/accounts/{acc}/toggle", headers=self.h, json={"bat": False})
        self.assertFalse(r.json()["bat"])

        r = self.cl.delete(f"/api/providers/accounts/{acc}", headers=self.h)
        self.assertEqual(r.status_code, 400)                # can xac_nhan
        r = self.cl.delete(f"/api/providers/accounts/{acc}?xac_nhan=true", headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["credential_da_xoa"])
        r = self.cl.delete("/api/providers/ali?xac_nhan=true", headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.cl.get("/api/providers", headers=self.h).json()["providers"], [])

    def test_gia_tri_hong_tra_400_khong_lap_lai_gia_tri(self):
        self.cl.post("/api/providers", headers=self.h,
                     json={"provider_id": "ali", "preset": "alibaba_dashscope"})
        r = self.cl.post("/api/providers/ali/accounts", headers=self.h,
                         json={"alias": "x", "gia_tri": KHOA + "\nxuong-dong"})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn(KHOA, r.text)
        r = self.cl.post("/api/providers/ali/accounts", headers=self.h,
                         json={"alias": "", "gia_tri": KHOA})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn(KHOA, r.text)


if __name__ == "__main__":
    unittest.main()
