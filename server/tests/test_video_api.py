"""
Video Composer — cac ROUTE HTTP that.

Vi sao bo kiem nay ton tai RIENG khoi `test_video_service`: tang dich vu da
duoc kiem ky, nhung mot route van hong duoc vi nhung ly do tang do khong
thay — thieu mot `import`, sai ten tham so, quen mot `Depends`. Da vap dung
the: `hashlib` khong duoc import trong `main.py`, va ca bo kiem dich vu
xanh muot trong khi duong tai len tra 500.
"""

from __future__ import annotations

import base64
import unittest
from typing import Dict

from fastapi.testclient import TestClient

import server.main as server_main
from server.adapters import (MockMediaAssetStore, MockIdentityAdapter,
                             MockMetadataStore)
from server.video_project_store import MockVideoProjectStore
from server.video_service import VideoService

#: MP4 rong — du de di qua kiem MIME/kich thuoc. Bo kiem nay khong render gi.
MP4_GIA = base64.b64encode(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512).decode()
SRT_GIA = base64.b64encode(
    b"1\n00:00:00,000 --> 00:00:02,000\nXin chao\n").decode()


class VideoApiTest(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.media_asset_store = MockMediaAssetStore()
        server_main.video_project_store = MockVideoProjectStore()
        server_main.video_svc = VideoService(
            server_main.store,
            project_store=server_main.video_project_store,
            media_store=server_main.media_asset_store)
        self.client = TestClient(server_main.app)

    def _auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _user(self, email: str) -> str:
        r = self.client.post("/api/auth/register",
                             json={"email": email, "password": "matkhau123"})
        return r.json()["token"]

    def _du_an(self, token: str, ten: str = "Dự án") -> str:
        r = self.client.post("/api/video/projects", json={"title": ten},
                             headers=self._auth(token))
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["project"]["project_id"]

    # -- khach vang lai -------------------------------------------------

    def test_khach_vang_lai_KHONG_lam_gi_duoc(self):
        """Mot du an video la thu rieng — ke ca doc cung phai dang nhap."""
        for duong in ("/api/video/projects", "/api/video/assets",
                      "/api/video/audio-library"):
            r = self.client.get(duong)
            self.assertIn(r.status_code, (401, 403),
                          f"GET {duong} cho khách vào được")
        for duong in ("/api/video/projects", "/api/video/assets"):
            r = self.client.post(duong, json={})
            self.assertIn(r.status_code, (401, 403, 422),
                          f"POST {duong} cho khách vào được")

    # -- tai len --------------------------------------------------------

    def test_tai_video_len_roi_gan_vao_du_an(self):
        """Duong di THAT — chinh duong da tung tra 500 vi thieu `hashlib`."""
        tok = self._user("a@x.test")
        r = self.client.post("/api/video/assets", headers=self._auth(tok), json={
            "filename": "a.mp4", "mime": "video/mp4",
            "base64": MP4_GIA, "duration_seconds": 12.5})
        self.assertEqual(r.status_code, 201, r.text)
        asset = r.json()["asset"]
        self.assertEqual(asset["media_type"], "video")
        self.assertEqual(asset["duration_seconds"], 12.5)

        pid = self._du_an(tok)
        r = self.client.patch(f"/api/video/projects/{pid}",
                              headers=self._auth(tok),
                              json={"video_asset_id": asset["asset_id"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["project"]["video_asset_id"], asset["asset_id"])

    def test_tai_phu_de_len_duoc_nhan_dung_loai(self):
        tok = self._user("b@x.test")
        r = self.client.post("/api/video/assets", headers=self._auth(tok), json={
            "filename": "a.srt", "mime": "application/x-subrip",
            "base64": SRT_GIA})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["asset"]["media_type"], "subtitles")

    def test_dinh_dang_KHONG_duoc_ho_tro_bi_tu_choi(self):
        tok = self._user("c@x.test")
        r = self.client.post("/api/video/assets", headers=self._auth(tok), json={
            "filename": "a.exe", "mime": "application/x-msdownload",
            "base64": MP4_GIA})
        self.assertEqual(r.status_code, 400)

    # -- quyen so huu ---------------------------------------------------

    def test_KHONG_doc_duoc_du_an_cua_nguoi_khac(self):
        a, b = self._user("d@x.test"), self._user("e@x.test")
        pid = self._du_an(a)
        r = self.client.get(f"/api/video/projects/{pid}", headers=self._auth(b))
        self.assertEqual(r.status_code, 404)

    def test_KHONG_sua_duoc_du_an_cua_nguoi_khac(self):
        a, b = self._user("f@x.test"), self._user("g@x.test")
        pid = self._du_an(a)
        r = self.client.patch(f"/api/video/projects/{pid}",
                              headers=self._auth(b), json={"title": "Cướp"})
        self.assertEqual(r.status_code, 404)

    def test_KHONG_dung_duoc_video_cua_nguoi_khac(self):
        a, b = self._user("h@x.test"), self._user("i@x.test")
        asset = self.client.post(
            "/api/video/assets", headers=self._auth(a),
            json={"filename": "a.mp4", "mime": "video/mp4",
                  "base64": MP4_GIA}).json()["asset"]
        pid = self._du_an(b)
        r = self.client.patch(f"/api/video/projects/{pid}", headers=self._auth(b),
                              json={"video_asset_id": asset["asset_id"]})
        self.assertEqual(r.status_code, 404, r.text)

    def test_danh_sach_chi_thay_cua_minh(self):
        a, b = self._user("j@x.test"), self._user("k@x.test")
        self._du_an(a, "Của A")
        self._du_an(b, "Của B")
        ra = self.client.get("/api/video/projects", headers=self._auth(a)).json()
        self.assertEqual([p["title"] for p in ra["projects"]], ["Của A"])

    # -- kiem tham so ---------------------------------------------------

    def test_tham_so_sai_tra_400_chu_khong_phai_500(self):
        tok = self._user("l@x.test")
        pid = self._du_an(tok)
        for xau in ({"audio_volume": 99}, {"audio_offset": 999999},
                    {"video_trim_start": -5}):
            r = self.client.patch(f"/api/video/projects/{pid}",
                                  headers=self._auth(tok), json=xau)
            self.assertEqual(r.status_code, 400, f"{xau} -> {r.status_code}")

    def test_ban_va_CHI_doi_truong_duoc_gui(self):
        """`exclude_unset` — thieu no thi mot lan doi am luong se dat lai ca
        diem cat ve 0."""
        tok = self._user("m@x.test")
        pid = self._du_an(tok)
        self.client.patch(f"/api/video/projects/{pid}", headers=self._auth(tok),
                          json={"audio_offset": 2.5})
        r = self.client.patch(f"/api/video/projects/{pid}",
                              headers=self._auth(tok), json={"audio_volume": 0.8})
        d = r.json()["project"]
        self.assertEqual(d["audio_offset"], 2.5)
        self.assertEqual(d["audio_volume"], 0.8)

    def test_render_khi_chua_co_video_tra_400(self):
        tok = self._user("n@x.test")
        pid = self._du_an(tok)
        r = self.client.post(f"/api/video/projects/{pid}/render",
                             headers=self._auth(tok))
        self.assertEqual(r.status_code, 400)

    def test_xin_ban_render_khi_chua_co_tra_404(self):
        tok = self._user("o@x.test")
        pid = self._du_an(tok)
        r = self.client.get(f"/api/video/projects/{pid}/output",
                            headers=self._auth(tok))
        self.assertEqual(r.status_code, 404)

    def test_khoa_doi_tuong_KHONG_ra_khoi_backend(self):
        tok = self._user("p@x.test")
        pid = self._du_an(tok)
        d = self.client.get(f"/api/video/projects/{pid}",
                            headers=self._auth(tok)).json()["project"]
        self.assertNotIn("output_object_key", d)
        self.assertIn("has_output", d)

    def test_xoa_du_an(self):
        tok = self._user("q@x.test")
        pid = self._du_an(tok)
        r = self.client.delete(f"/api/video/projects/{pid}",
                               headers=self._auth(tok))
        self.assertTrue(r.json()["deleted"])
        self.assertEqual(
            self.client.get(f"/api/video/projects/{pid}",
                            headers=self._auth(tok)).status_code, 404)


if __name__ == "__main__":
    unittest.main()
