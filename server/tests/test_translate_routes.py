"""
Duong API `/api/translate/*` (V5) — qua `TestClient`, cung phong cach voi
`test_cover.py`/`test_admin.py`.
"""

from __future__ import annotations

import base64
import unittest
import zipfile
from io import BytesIO
from typing import Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.translation_service import TranslationService
from server.translation_store import MockTranslationStore

VB_HAI_CHUONG = (
    "第1章 Khởi đầu\n萧炎看向药老。\n第2章 Tiếp theo\n他继续前进。"
)


class TranslateRouteTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.translation_store = MockTranslationStore()
        server_main.translation_svc = TranslationService(
            server_main.translation_store, server_main.store)
        self.client = TestClient(server_main.app)

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str = "chu@example.com") -> str:
        return self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"}
        ).json()["token"]


class UocLuongTest(TranslateRouteTestCase):
    def test_uoc_luong_khong_can_dang_nhap(self):
        r = self.client.post("/api/translate/estimate",
                             json={"source_text": VB_HAI_CHUONG})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["chapters"], 2)


class TaoDuAnQuaApiTest(TranslateRouteTestCase):
    def test_tao_bang_dan_van_ban(self):
        token = self.user()
        r = self.client.post("/api/translate/projects", headers=self.auth(token),
                             json={"title": "Đấu Phá", "source_text": VB_HAI_CHUONG})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["project"]["chapter_count"], 2)

    def test_chua_dang_nhap_bi_401(self):
        r = self.client.post("/api/translate/projects",
                             json={"title": "x", "source_text": "một đoạn."})
        self.assertEqual(r.status_code, 401)

    def test_thieu_noi_dung_tra_400(self):
        token = self.user()
        r = self.client.post("/api/translate/projects", headers=self.auth(token),
                             json={"title": "x", "source_text": "   "})
        self.assertEqual(r.status_code, 400)

    def test_tao_bang_tai_len_tep_txt(self):
        token = self.user()
        b64 = base64.b64encode(VB_HAI_CHUONG.encode("utf-8")).decode()
        r = self.client.post(
            "/api/translate/projects/upload", headers=self.auth(token),
            json={"filename": "truyen.txt", "base64": b64})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["project"]["source_filename"], "truyen.txt")
        self.assertEqual(r.json()["project"]["chapter_count"], 2)

    def test_tai_len_dinh_dang_khong_ho_tro_tra_400(self):
        token = self.user()
        b64 = base64.b64encode(b"%PDF-1.4").decode()
        r = self.client.post(
            "/api/translate/projects/upload", headers=self.auth(token),
            json={"filename": "truyen.pdf", "base64": b64})
        self.assertEqual(r.status_code, 400)

    def test_tai_len_epub_that(self):
        token = self.user()
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("OEBPS/c1.xhtml", "<p>第一章内容。</p>")
        b64 = base64.b64encode(buf.getvalue()).decode()
        r = self.client.post(
            "/api/translate/projects/upload", headers=self.auth(token),
            json={"filename": "truyen.epub", "base64": b64})
        self.assertEqual(r.status_code, 201, r.text)

    def test_base64_hong_tra_400_khong_phai_500(self):
        token = self.user()
        r = self.client.post(
            "/api/translate/projects/upload", headers=self.auth(token),
            json={"filename": "a.txt", "base64": "***khong-phai-base64***"})
        self.assertEqual(r.status_code, 400)

    def test_khong_so_huu_khong_doc_duoc_du_an(self):
        chu = self.user("chu@example.com")
        khac = self.user("khac@example.com")
        p = self.client.post(
            "/api/translate/projects", headers=self.auth(chu),
            json={"title": "x", "source_text": "một đoạn."}).json()["project"]
        r = self.client.get(f"/api/translate/projects/{p['project_id']}",
                            headers=self.auth(khac))
        self.assertEqual(r.status_code, 403)

    def test_du_an_khong_ton_tai_tra_404(self):
        token = self.user()
        r = self.client.get("/api/translate/projects/khong-ton-tai",
                            headers=self.auth(token))
        self.assertEqual(r.status_code, 404)


class JobQuaApiTest(TranslateRouteTestCase):
    def _du_an(self, token: str, vb: str = VB_HAI_CHUONG) -> str:
        r = self.client.post("/api/translate/projects", headers=self.auth(token),
                             json={"title": "x", "source_text": vb})
        return r.json()["project"]["project_id"]

    def test_tao_job_va_doc_lai_qua_reload(self):
        token = self.user()
        pid = self._du_an(token)
        r = self.client.post(f"/api/translate/projects/{pid}/jobs",
                            headers=self.auth(token))
        self.assertEqual(r.status_code, 201, r.text)
        job_id = r.json()["job"]["job_id"]
        self.assertEqual(r.json()["job"]["status"], "completed")

        # "F5": doc lai job bang MOT request GET doc lap — trang thai phai
        # con nguyen, khong phu thuoc tien trinh nao dang giu no trong bo nho.
        r2 = self.client.get(f"/api/translate/jobs/{job_id}",
                             headers=self.auth(token))
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["job"]["status"], "completed")
        self.assertEqual(r2.json()["job"]["progress"], 100)

    def test_goi_lai_khi_job_con_dang_chay_khong_tao_ban_sao(self):
        """
        Mock KHONG co do tre mang nen job dau xong TRUOC KHI request thu hai
        kip goi toi — luc do "khong con job active" la SU THAT, va tao job
        moi la DUNG, khong phai loi idempotent. De kiem dung kich ban F5 (job
        con dang chay), ep trang thai qua kho ngay sau khi tao — cung ky
        thuat voi `test_translation_service.py`, chi khac o day di qua HTTP.
        """
        token = self.user()
        pid = self._du_an(token)
        r1 = self.client.post(f"/api/translate/projects/{pid}/jobs",
                              headers=self.auth(token))
        job_id = r1.json()["job"]["job_id"]
        from server.translation import TranslationJobStatus

        server_main.translation_store._jobs[job_id].status = (
            TranslationJobStatus.TRANSLATING)

        r2 = self.client.post(f"/api/translate/projects/{pid}/jobs",
                              headers=self.auth(token))
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(job_id, r2.json()["job"]["job_id"])

    def test_project_detail_kem_danh_sach_job(self):
        token = self.user()
        pid = self._du_an(token)
        self.client.post(f"/api/translate/projects/{pid}/jobs",
                         headers=self.auth(token))
        r = self.client.get(f"/api/translate/projects/{pid}",
                            headers=self.auth(token))
        self.assertEqual(len(r.json()["jobs"]), 1)
        self.assertEqual(len(r.json()["chapters"]), 2)

    def test_khong_so_huu_khong_huy_duoc_job(self):
        chu = self.user("chu@example.com")
        khac = self.user("khac@example.com")
        pid = self._du_an(chu)
        job = self.client.post(f"/api/translate/projects/{pid}/jobs",
                               headers=self.auth(chu)).json()["job"]
        r = self.client.post(f"/api/translate/jobs/{job['job_id']}/cancel",
                             headers=self.auth(khac))
        self.assertEqual(r.status_code, 403)


class GlossaryQuaApiTest(TranslateRouteTestCase):
    def test_them_sua_khoa_xoa(self):
        token = self.user()
        pid = self.client.post(
            "/api/translate/projects", headers=self.auth(token),
            json={"title": "x", "source_text": "một đoạn."}
        ).json()["project"]["project_id"]

        r = self.client.post(f"/api/translate/projects/{pid}/glossary",
                             headers=self.auth(token),
                             json={"category": "character", "original": "萧炎",
                                   "translated": "Tiêu Viêm"})
        self.assertEqual(r.status_code, 201, r.text)
        term_id = r.json()["term_id"]

        r = self.client.get(f"/api/translate/projects/{pid}/glossary",
                            headers=self.auth(token))
        self.assertEqual(r.json()["total"], 1)

        r = self.client.patch(
            f"/api/translate/projects/{pid}/glossary/{term_id}",
            headers=self.auth(token), json={"locked": True})
        self.assertTrue(r.json()["locked"])

        r = self.client.delete(
            f"/api/translate/projects/{pid}/glossary/{term_id}",
            headers=self.auth(token))
        self.assertEqual(r.status_code, 400)  # dang khoa

        self.client.patch(f"/api/translate/projects/{pid}/glossary/{term_id}",
                          headers=self.auth(token), json={"locked": False})
        r = self.client.delete(
            f"/api/translate/projects/{pid}/glossary/{term_id}",
            headers=self.auth(token))
        self.assertEqual(r.status_code, 200)


class NhapVaoTruyenQuaApiTest(TranslateRouteTestCase):
    def test_nhap_thanh_cong_va_goi_lai_khong_tao_ban_sao(self):
        token = self.user()
        pid = self.client.post(
            "/api/translate/projects", headers=self.auth(token),
            json={"title": "x", "source_text": VB_HAI_CHUONG}
        ).json()["project"]["project_id"]
        self.client.post(f"/api/translate/projects/{pid}/jobs",
                         headers=self.auth(token))

        r1 = self.client.post(f"/api/translate/projects/{pid}/import",
                              headers=self.auth(token), json={})
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertEqual(r1.json()["chapters_created"], 2)
        novel_id = r1.json()["novel_id"]

        # Novel THAT da duoc tao trong store novel chinh — kiem qua API cu.
        r_novel = self.client.get(f"/api/novels/{novel_id}",
                                  headers=self.auth(token))
        self.assertEqual(r_novel.status_code, 200)
        self.assertEqual(len(r_novel.json()["chapters"]), 2)

        r2 = self.client.post(f"/api/translate/projects/{pid}/import",
                              headers=self.auth(token), json={})
        self.assertTrue(r2.json()["already_imported"])
        self.assertEqual(r2.json()["novel_id"], novel_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
