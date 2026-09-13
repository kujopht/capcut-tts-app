"""
Studio Project + tai thang len — cac ROUTE HTTP that.

Cung ly do ton tai voi `test_video_api.py`: tang dich vu co the xanh muot
trong khi mot route hong vi thieu mot `import` hay sai mot `Depends`. Da vap
dung the o #202.
"""

from __future__ import annotations

import unittest
from typing import Dict

from fastapi.testclient import TestClient

import server.main as server_main
from server.adapters import (MockMediaAssetStore, MockIdentityAdapter,
                             MockMetadataStore)
from server.image_library_store import MockImageLibraryStore
from server.render_queue import MockRenderQueue
from server.studio_project_store import MockStudioProjectStore
from server.studio_service import StudioService
from server.upload_session import MockUploadSessionStore
from server.video_project_store import MockVideoProjectStore
from server.video_service import VideoService


class StudioApiTest(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.media_asset_store = MockMediaAssetStore()
        server_main.image_library_store = MockImageLibraryStore()
        server_main.video_project_store = MockVideoProjectStore()
        server_main.studio_project_store = MockStudioProjectStore()
        server_main.upload_session_store = MockUploadSessionStore()
        server_main.render_queue = MockRenderQueue()
        server_main.video_svc = VideoService(
            server_main.store, project_store=server_main.video_project_store,
            media_store=server_main.media_asset_store)
        server_main.studio_svc = StudioService(
            server_main.store, project_store=server_main.studio_project_store,
            image_store=server_main.image_library_store,
            media_store=server_main.media_asset_store,
            video_project_store=server_main.video_project_store)
        self.client = TestClient(server_main.app)

    def _auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _user(self, email: str) -> str:
        return self.client.post("/api/auth/register",
                                json={"email": email,
                                      "password": "matkhau123"}).json()["token"]

    def _du_an(self, tok: str, ten: str = "Dự án") -> str:
        r = self.client.post("/api/studio/projects", json={"title": ten},
                             headers=self._auth(tok))
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["project"]["project_id"]

    # -- khach vang lai -------------------------------------------------

    def test_khach_vang_lai_KHONG_vao_duoc(self):
        for duong in ("/api/studio/projects", "/api/studio/assets/audio"):
            r = self.client.get(duong)
            self.assertIn(r.status_code, (401, 403), duong)
        r = self.client.post("/api/studio/projects", json={"title": "x"})
        self.assertIn(r.status_code, (401, 403))
        r = self.client.post("/api/studio/uploads",
                             json={"media_type": "video", "mime": "video/mp4",
                                   "size_bytes": 10})
        self.assertIn(r.status_code, (401, 403))

    # -- du an ----------------------------------------------------------

    def test_tao_va_doc_lai_kem_TIEN_DO(self):
        tok = self._user("a@x.test")
        pid = self._du_an(tok, "Naruto AU")
        r = self.client.get(f"/api/studio/projects/{pid}", headers=self._auth(tok))
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["project"]["title"], "Naruto AU")
        self.assertEqual(len(d["progress"]), 6)
        self.assertEqual(d["progress"][0]["stage"], "noi_dung")

    def test_tien_do_KHONG_bia_mau_so(self):
        """Chang khong co mau so THAT phai tra `total: null`."""
        tok = self._user("b@x.test")
        pid = self._du_an(tok)
        d = self.client.get(f"/api/studio/projects/{pid}",
                            headers=self._auth(tok)).json()
        bac = {p["stage"]: p for p in d["progress"]}
        self.assertIsNone(bac["hinh_anh"]["total"])
        self.assertIsNone(bac["audio"]["total"])

    def test_KHONG_doc_duoc_du_an_cua_nguoi_khac(self):
        a, b = self._user("c@x.test"), self._user("d@x.test")
        pid = self._du_an(a)
        self.assertEqual(
            self.client.get(f"/api/studio/projects/{pid}",
                            headers=self._auth(b)).status_code, 404)

    def test_KHONG_sua_duoc_du_an_cua_nguoi_khac(self):
        a, b = self._user("e@x.test"), self._user("f@x.test")
        pid = self._du_an(a)
        r = self.client.patch(f"/api/studio/projects/{pid}",
                              headers=self._auth(b), json={"title": "Cướp"})
        self.assertEqual(r.status_code, 404)

    def test_chang_khong_hop_le_tra_400(self):
        tok = self._user("g@x.test")
        pid = self._du_an(tok)
        r = self.client.post(f"/api/studio/projects/{pid}/refs",
                             headers=self._auth(tok),
                             json={"stage": "khong-co", "ref_id": "x"})
        self.assertEqual(r.status_code, 400)

    def test_gan_tham_chieu_KHONG_CO_THAT_tra_404(self):
        tok = self._user("h@x.test")
        pid = self._du_an(tok)
        r = self.client.post(f"/api/studio/projects/{pid}/refs",
                             headers=self._auth(tok),
                             json={"stage": "audio", "ref_id": "trk_khong_co"})
        self.assertEqual(r.status_code, 404)

    def test_bo_chon_tai_san_khong_lo_cua_nguoi_khac(self):
        a, b = self._user("i@x.test"), self._user("j@x.test")
        # b tao mot truyen + chuong; a khong duoc thay gi cua b.
        nid = self.client.post("/api/novels", json={"title": "Của B"},
                               headers=self._auth(b)).json()["novel"]["novel_id"]
        self.client.post(f"/api/novels/{nid}/chapters",
                         json={"title": "C1", "content": "x"},
                         headers=self._auth(b))
        r = self.client.get("/api/studio/assets/audio", headers=self._auth(a))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["assets"], [])

    # -- chon truyen + nhan tham chieu -----------------------------------

    def test_chon_TRUYEN_qua_API_roi_doc_lai(self):
        """Chang dau tien phai CHON duoc: bo chon liet ke, PATCH gan."""
        tok = self._user("l@x.test")
        pid = self._du_an(tok)
        nid = self.client.post("/api/novels", json={"title": "Của tôi"},
                               headers=self._auth(tok)).json()["novel"]["novel_id"]
        r = self.client.post("/api/chapters", headers=self._auth(tok),
                             json={"novel_id": nid, "title": "C1",
                                   "content": "x", "order_index": 1})
        self.assertEqual(r.status_code, 201, r.text)

        r = self.client.get(f"/api/studio/assets/noi_dung?project_id={pid}",
                            headers=self._auth(tok))
        self.assertEqual(r.status_code, 200, r.text)
        ds = r.json()["assets"]
        self.assertEqual([x["id"] for x in ds], [nid])
        self.assertEqual(ds[0]["detail"], "1 chương")
        self.assertFalse(ds[0]["in_project"])

        r = self.client.patch(f"/api/studio/projects/{pid}",
                              headers=self._auth(tok), json={"novel_id": nid})
        self.assertEqual(r.status_code, 200, r.text)
        bac = {p["stage"]: p for p in r.json()["progress"]}
        self.assertTrue(bac["noi_dung"]["done"])
        # Va mau so cua Audio mo ra — day la ly do that su cua chang nay.
        self.assertEqual(bac["audio"]["total"], 1)

        ds = self.client.get(f"/api/studio/assets/noi_dung?project_id={pid}",
                             headers=self._auth(tok)).json()["assets"]
        self.assertTrue(ds[0]["in_project"])

    def test_bo_chon_noi_dung_KHONG_lo_truyen_nguoi_khac(self):
        a, b = self._user("m@x.test"), self._user("n@x.test")
        self.client.post("/api/novels", json={"title": "Của B"},
                         headers=self._auth(b))
        r = self.client.get("/api/studio/assets/noi_dung", headers=self._auth(a))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["assets"], [])

    def test_duong_MOT_du_an_kem_NHAN_doc_duoc(self):
        tok = self._user("o@x.test")
        pid = self._du_an(tok)
        nid = self.client.post("/api/novels", json={"title": "Có tên hẳn hoi"},
                               headers=self._auth(tok)).json()["novel"]["novel_id"]
        self.client.patch(f"/api/studio/projects/{pid}",
                          headers=self._auth(tok), json={"novel_id": nid})
        d = self.client.get(f"/api/studio/projects/{pid}",
                            headers=self._auth(tok)).json()
        self.assertEqual(sorted(d["refs"]),
                         ["audio", "dich", "hinh_anh", "noi_dung", "phu_de",
                          "video"])
        self.assertEqual(d["refs"]["noi_dung"][0]["label"], "Có tên hẳn hoi")
        self.assertFalse(d["refs"]["noi_dung"][0]["missing"])

    def test_DANH_SACH_du_an_KHONG_keo_theo_nhan(self):
        """Nhan quet ca sau kho — danh sach se tra gia theo SO DU AN nhan SAU."""
        tok = self._user("p@x.test")
        self._du_an(tok)
        d = self.client.get("/api/studio/projects", headers=self._auth(tok)).json()
        self.assertNotIn("refs", d["projects"][0])

    # -- tai thang len ---------------------------------------------------

    def test_xin_phien_roi_tai_len_roi_chot(self):
        tok = self._user("k@x.test")
        r = self.client.post("/api/studio/uploads", headers=self._auth(tok),
                             json={"media_type": "subtitles",
                                   "mime": "application/x-subrip",
                                   "size_bytes": 40,
                                   "filename": "a.srt"})
        self.assertEqual(r.status_code, 201, r.text)
        p = r.json()
        # Kho cuc bo khong ky duoc URL -> phai co duong PUT qua backend.
        self.assertTrue(p["put_via_api"])
        self.assertTrue(p["object_key"].startswith("studio/"))

        du_lieu = b"1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"
        r = self.client.put(p["put_via_api"], headers=self._auth(tok),
                            content=du_lieu)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post(
            f"/api/studio/uploads/{p['session_id']}/finalize",
            headers=self._auth(tok))
        self.assertEqual(r.status_code, 200, r.text)
        asset = r.json()["asset"]
        self.assertEqual(asset["media_type"], "subtitles")
        # Kich thuoc lay TU KHO, khong phai con so client khai (40).
        self.assertEqual(asset["size_bytes"], len(du_lieu))

    def test_KHOA_do_may_chu_sinh_va_mang_chu_so_huu(self):
        tok = self._user("l@x.test")
        p = self.client.post("/api/studio/uploads", headers=self._auth(tok),
                             json={"media_type": "video", "mime": "video/mp4",
                                   "size_bytes": 100,
                                   "filename": "../../hiem.exe"}).json()
        self.assertNotIn("..", p["object_key"])
        self.assertNotIn("hiem", p["object_key"])
        self.assertTrue(p["object_key"].endswith(".mp4"))

    def test_MIME_ngoai_danh_sach_bi_tu_choi(self):
        tok = self._user("m@x.test")
        r = self.client.post("/api/studio/uploads", headers=self._auth(tok),
                             json={"media_type": "video",
                                   "mime": "application/x-msdownload",
                                   "size_bytes": 100})
        self.assertEqual(r.status_code, 400)

    def test_KHONG_chot_duoc_phien_cua_nguoi_khac(self):
        a, b = self._user("n@x.test"), self._user("o@x.test")
        p = self.client.post("/api/studio/uploads", headers=self._auth(a),
                             json={"media_type": "subtitles",
                                   "mime": "text/vtt",
                                   "size_bytes": 10}).json()
        r = self.client.post(f"/api/studio/uploads/{p['session_id']}/finalize",
                             headers=self._auth(b))
        self.assertEqual(r.status_code, 404)

    def test_KHONG_PUT_duoc_vao_phien_cua_nguoi_khac(self):
        a, b = self._user("p@x.test"), self._user("q@x.test")
        p = self.client.post("/api/studio/uploads", headers=self._auth(a),
                             json={"media_type": "subtitles",
                                   "mime": "text/vtt",
                                   "size_bytes": 10}).json()
        r = self.client.put(p["put_via_api"], headers=self._auth(b),
                            content=b"x")
        self.assertEqual(r.status_code, 404)

    def test_chot_khi_CHUA_tai_gi_len_tra_400(self):
        tok = self._user("r@x.test")
        p = self.client.post("/api/studio/uploads", headers=self._auth(tok),
                             json={"media_type": "subtitles",
                                   "mime": "text/vtt",
                                   "size_bytes": 10}).json()
        r = self.client.post(f"/api/studio/uploads/{p['session_id']}/finalize",
                             headers=self._auth(tok))
        self.assertEqual(r.status_code, 400)

    def test_chot_HAI_LAN_tra_409(self):
        tok = self._user("s@x.test")
        p = self.client.post("/api/studio/uploads", headers=self._auth(tok),
                             json={"media_type": "subtitles",
                                   "mime": "text/vtt",
                                   "size_bytes": 10}).json()
        self.client.put(p["put_via_api"], headers=self._auth(tok), content=b"xx")
        self.client.post(f"/api/studio/uploads/{p['session_id']}/finalize",
                         headers=self._auth(tok))
        r = self.client.post(f"/api/studio/uploads/{p['session_id']}/finalize",
                             headers=self._auth(tok))
        self.assertEqual(r.status_code, 409)


if __name__ == "__main__":
    unittest.main()
