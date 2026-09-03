"""Danh tinh dich vu HARVESTER — mission "PIVOT AUTH — CREATE FIRST-CLASS
HARVESTER SERVICE CREDENTIAL" (2026-09-01).

Cung tinh than voi `test_canary_service_identity.py`/`test_canary_api_surface.py`:
phan lon o day la test PHU DINH. "Harvester tao duoc chuong draft" thi de;
dieu can chung minh la harvester KHONG voi toi duoc publish/delete/user/
schema/billing — va rang canary KHONG the tu leo len thanh harvester.
"""
from __future__ import annotations

import dataclasses
import unittest
from unittest import mock

from fastapi.testclient import TestClient  # noqa: E402

import server.main as server_main  # noqa: E402
from server import tts_bridge  # noqa: E402
from server.config import Settings  # noqa: E402
from server.domain import AdminRole, PublishState  # noqa: E402
from server.tests.voice_stub import dung_registry_gia  # noqa: E402

TOKEN = "harvester-service-token-chi-dung-trong-test"


def _settings(**kw) -> Settings:
    return Settings(harvester_service_token=TOKEN, **kw)


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------
# Muc cau hinh (khong can HTTP) — y het CanaryTokenMatchingTest/
# CanaryKhongPhaiVaiTroQuanTriTest/CanaryIdTrungDacQuyenTest.
# --------------------------------------------------------------------------


class HarvesterTokenMatchingTest(unittest.TestCase):
    def test_token_dung_thi_khop(self):
        self.assertTrue(_settings().is_harvester_service_token(TOKEN))

    def test_token_sai_thi_khong_khop(self):
        self.assertFalse(_settings().is_harvester_service_token(TOKEN + "x"))
        self.assertFalse(_settings().is_harvester_service_token("hoan-toan-khac"))

    def test_token_rong_gui_len_khong_bao_gio_khop(self):
        self.assertFalse(_settings().is_harvester_service_token(""))

    def test_deployment_chua_cau_hinh_khong_tu_mo_cua(self):
        chua_cau_hinh = Settings(harvester_service_token="")
        self.assertFalse(chua_cau_hinh.is_harvester_service_token(""))
        self.assertFalse(chua_cau_hinh.is_harvester_service_token("bat-ky-gi"))

    def test_khoang_trang_khong_bi_cat_ngam(self):
        self.assertFalse(_settings().is_harvester_service_token(" " + TOKEN))
        self.assertFalse(_settings().is_harvester_service_token(TOKEN + " "))

    def test_canary_token_khong_lam_harvester_token(self):
        """Hai token RIENG — token canary khong duoc khop voi kiem tra harvester,
        du ca hai co the cung ton tai trong mot deployment that."""
        s = Settings(harvester_service_token=TOKEN, canary_service_token="canary-xyz")
        self.assertFalse(s.is_harvester_service_token("canary-xyz"))
        self.assertFalse(s.is_canary_service_token(TOKEN))


class HarvesterKhongPhaiVaiTroQuanTriTest(unittest.TestCase):
    def test_harvester_user_id_khong_co_vai_tro_quan_tri_nao(self):
        s = _settings()
        self.assertEqual(s.admin_role_of(s.harvester_owner_user_id), AdminRole.NONE)

    def test_harvester_khong_thanh_admin_du_co_admin_khac_ton_tai(self):
        s = _settings(admin_user_ids=("usr_nguoi_that",),
                      owner_user_ids=("usr_chu_so_huu",))
        self.assertEqual(s.admin_role_of(s.harvester_owner_user_id), AdminRole.NONE)
        self.assertEqual(s.admin_role_of("usr_nguoi_that"), AdminRole.ADMIN)
        self.assertEqual(s.admin_role_of("usr_chu_so_huu"), AdminRole.OWNER)


class HarvesterIdTrungDacQuyenTest(unittest.TestCase):
    def test_trung_admin_thi_tu_choi_xac_thuc(self):
        s = Settings(harvester_service_token=TOKEN, harvester_owner_user_id="usr_x",
                     admin_user_ids=("usr_x",))
        self.assertEqual(s.harvester_id_collision(), "FAS_ADMIN_USER_IDS")
        self.assertFalse(s.is_harvester_service_token(TOKEN))

    def test_trung_owner_thi_tu_choi_xac_thuc(self):
        s = Settings(harvester_service_token=TOKEN, harvester_owner_user_id="usr_x",
                     owner_user_ids=("usr_x",))
        self.assertEqual(s.harvester_id_collision(), "FAS_OWNER_USER_IDS")
        self.assertFalse(s.is_harvester_service_token(TOKEN))

    def test_trung_moderator_thi_tu_choi_xac_thuc(self):
        s = Settings(harvester_service_token=TOKEN, harvester_owner_user_id="usr_x",
                     moderator_user_ids=("usr_x",))
        self.assertEqual(s.harvester_id_collision(), "FAS_MODERATOR_USER_IDS")
        self.assertFalse(s.is_harvester_service_token(TOKEN))

    def test_khong_trung_thi_van_hoat_dong_binh_thuong(self):
        s = Settings(harvester_service_token=TOKEN, harvester_owner_user_id="svc_harvester",
                     admin_user_ids=("usr_nguoi_that",))
        self.assertEqual(s.harvester_id_collision(), "")
        self.assertTrue(s.is_harvester_service_token(TOKEN))


# --------------------------------------------------------------------------
# Muc HTTP that — ALLOW/DENY matrix theo dung yeu cau mission.
# --------------------------------------------------------------------------


class HarvesterApiAllowTest(unittest.TestCase):
    """Nhung viec harvester CAN lam duoc de van hanh duong ong that."""

    def setUp(self) -> None:
        dung_registry_gia(self)
        cau_hinh = dataclasses.replace(server_main.settings,
                                       harvester_service_token=TOKEN)
        vá = mock.patch.object(server_main, "settings", cau_hinh)
        vá.start()
        self.addCleanup(vá.stop)

        real_synth = tts_bridge.synthesize_chapter

        def _fake_synth(text, voice_id, dest, rate="1.0", chunk_chars=2000,
                        on_progress=None, cancel=None):
            from pathlib import Path
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(b"\x00" * 4096)
            if on_progress:
                on_progress(1, 1)
            return {"size_bytes": 4096, "total_parts": 1,
                   "voice_id": voice_id, "provider": "mock"}

        tts_bridge.synthesize_chapter = _fake_synth
        self.addCleanup(lambda: setattr(tts_bridge, "synthesize_chapter", real_synth))

        self.client = TestClient(server_main.app)

    def _tao_novel(self, **overrides):
        payload = {"title": "Harvester draft novel", "external_source_url": "https://x.test/1"}
        payload.update(overrides)
        return self.client.post("/api/novels", json=payload, headers=_h(TOKEN))

    def test_tao_novel_draft_duoc_phep(self):
        r = self._tao_novel()
        self.assertEqual(r.status_code, 201, r.text)
        novel = r.json()["novel"]
        self.assertEqual(novel["state"], PublishState.DRAFT.value)
        self.assertEqual(novel["owner_id"], server_main.settings.harvester_owner_user_id)

    def test_tao_video_draft_voi_truong_moi_duoc_phep(self):
        r = self._tao_novel(publication_mode="metadata_only", platform="youtube",
                            rights_mode="EMBED_ONLY", subtitle_status="PENDING_SOURCE",
                            embed_ref="abc123")
        self.assertEqual(r.status_code, 201, r.text)
        novel = r.json()["novel"]
        self.assertEqual(novel["rights_mode"], "EMBED_ONLY")
        self.assertEqual(novel["subtitle_status"], "PENDING_SOURCE")

    def test_sua_novel_draft_duoc_phep(self):
        novel_id = self._tao_novel().json()["novel"]["novel_id"]
        r = self.client.patch(f"/api/novels/{novel_id}",
                              json={"description": "cap nhat"}, headers=_h(TOKEN))
        self.assertEqual(r.status_code, 200, r.text)

    def test_doc_novel_cua_chinh_minh_duoc_phep(self):
        novel_id = self._tao_novel().json()["novel"]["novel_id"]
        r = self.client.get(f"/api/novels/{novel_id}", headers=_h(TOKEN))
        self.assertEqual(r.status_code, 200, r.text)

    def test_liet_ke_novel_cua_minh_duoc_phep(self):
        self._tao_novel()
        r = self.client.get("/api/novels", params={"mine": "true"}, headers=_h(TOKEN))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertGreaterEqual(len(r.json()["novels"]), 1)

    def test_tao_chuong_draft_duoc_phep(self):
        novel_id = self._tao_novel().json()["novel"]["novel_id"]
        r = self.client.post("/api/chapters",
                             json={"novel_id": novel_id, "title": "Ch1",
                                   "content": "noi dung that", "order_index": 1},
                             headers=_h(TOKEN))
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["chapter"]["state"], PublishState.DRAFT.value)

    def test_sua_chuong_draft_duoc_phep(self):
        novel_id = self._tao_novel().json()["novel"]["novel_id"]
        chapter_id = self.client.post(
            "/api/chapters", json={"novel_id": novel_id, "title": "Ch1",
                                   "content": "noi dung", "order_index": 1},
            headers=_h(TOKEN)).json()["chapter"]["chapter_id"]
        r = self.client.patch(f"/api/chapters/{chapter_id}",
                              json={"title": "Ch1 moi"}, headers=_h(TOKEN))
        self.assertEqual(r.status_code, 200, r.text)

    def test_tao_tts_job_duoc_phep(self):
        novel_id = self._tao_novel().json()["novel"]["novel_id"]
        chapter_id = self.client.post(
            "/api/chapters", json={"novel_id": novel_id, "title": "Ch1",
                                   "content": "noi dung that de tao am thanh",
                                   "order_index": 1},
            headers=_h(TOKEN)).json()["chapter"]["chapter_id"]
        r = self.client.post("/api/jobs",
                             json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
                             headers=_h(TOKEN))
        self.assertEqual(r.status_code, 201, r.text)

    def test_doc_tts_job_duoc_phep(self):
        novel_id = self._tao_novel().json()["novel"]["novel_id"]
        chapter_id = self.client.post(
            "/api/chapters", json={"novel_id": novel_id, "title": "Ch1",
                                   "content": "noi dung", "order_index": 1},
            headers=_h(TOKEN)).json()["chapter"]["chapter_id"]
        job_id = self.client.post(
            "/api/jobs", json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
            headers=_h(TOKEN)).json()["job"]["job_id"]
        r = self.client.get(f"/api/jobs/{job_id}", headers=_h(TOKEN))
        self.assertEqual(r.status_code, 200, r.text)

    # ----------------------------------------------------------------------
    # DOC LAI CHUONG cua chinh minh — lo hong that tren san xuat (2026-09-03).
    #
    # `test_doc_novel_cua_chinh_minh_duoc_phep` o tren da co san, nhung KHONG co
    # cai tuong duong cho CHUONG — va do dung la khe ma loi di qua: tren san
    # xuat, voi truyen nhap `nov_6764055a19c44e63` (harvester so huu),
    # `GET /api/novels/{id}` tra 200 kem ca 15 chuong va `GET /api/audio/{id}/url`
    # tra 200 kem URL R2 ky, nhung `GET /api/chapters/{id}` tra 404. Nguoi xem
    # truoc duoc phep thay muc luc va NGHE duoc audio, ma trang doc thi 404.
    #
    # Ba test duoi day khoa CA HAI chieu: doc duoc (allow), va van kin voi nguoi
    # khac (deny) — mot ban va chi mo dung danh tinh harvester thi moi dung.
    # ----------------------------------------------------------------------

    def _novel_va_chuong(self):
        novel_id = self._tao_novel().json()["novel"]["novel_id"]
        chapter_id = self.client.post(
            "/api/chapters", json={"novel_id": novel_id, "title": "Ch1",
                                   "content": "noi dung that cua chuong",
                                   "order_index": 1},
            headers=_h(TOKEN)).json()["chapter"]["chapter_id"]
        return novel_id, chapter_id

    def test_doc_chuong_cua_chinh_minh_duoc_phep(self):
        """Va phai tra ve CHU that, khong chi 200 rong."""
        _, chapter_id = self._novel_va_chuong()
        r = self.client.get(f"/api/chapters/{chapter_id}", headers=_h(TOKEN))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["chapter"]["content"], "noi dung that cua chuong")

    def test_doc_phu_de_chuong_cua_chinh_minh_khong_bi_404(self):
        """Chua co audio thi `{"available": false}` — trang thai HOP LE. Dieu
        can chung minh la khong con bi 404 vi DANH TINH."""
        _, chapter_id = self._novel_va_chuong()
        r = self.client.get(f"/api/chapters/{chapter_id}/transcript",
                            headers=_h(TOKEN))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("available", r.json())

    def test_optional_profile_mot_minh_khong_du_cho_harvester(self):
        """VI SAO hai test tren can ban va — chot lai chinh co che gay loi.

        `optional_profile` phan giai token qua PHIEN Appwrite; harvester khong co
        phien nao, nen no tra None, va `_may_read(ban_nhap, None)` la False ->
        404. Chi `_optional_harvester_or_user` nhan ra danh tinh nay.

        Giu test nay de mot lan "don dep" gop hai ham lai se lam do o day, chu
        khong am tham lam trang doc 404 tren san xuat lan nua.
        """
        header = f"Bearer {TOKEN}"
        self.assertIsNone(server_main.optional_profile(header))
        ho_so = server_main._optional_harvester_or_user(header)
        self.assertIsNotNone(ho_so)
        self.assertEqual(ho_so.user_id, server_main.settings.harvester_owner_user_id)

    def test_ban_nhap_van_kin_voi_khach_va_token_sai(self):
        """Mo cho harvester KHONG duoc keo theo mo cho bat ky ai khac."""
        _, chapter_id = self._novel_va_chuong()
        for headers in ({}, _h("token-hoan-toan-sai")):
            for duong_dan in (f"/api/chapters/{chapter_id}",
                              f"/api/chapters/{chapter_id}/transcript"):
                r = self.client.get(duong_dan, headers=headers)
                self.assertEqual(r.status_code, 404, f"{duong_dan} {headers}: {r.text}")


class HarvesterApiDenyTest(unittest.TestCase):
    """Nhung viec harvester KHONG duoc lam — trong tam that su cua thiet ke."""

    def setUp(self) -> None:
        cau_hinh = dataclasses.replace(server_main.settings,
                                       harvester_service_token=TOKEN)
        vá = mock.patch.object(server_main, "settings", cau_hinh)
        vá.start()
        self.addCleanup(vá.stop)
        self.client = TestClient(server_main.app)
        novel = self.client.post(
            "/api/novels", json={"title": "Deny-matrix novel"},
            headers=_h(TOKEN)).json()["novel"]
        self.novel_id = novel["novel_id"]

    def test_publish_bi_tu_choi(self):
        r = self.client.post(f"/api/novels/{self.novel_id}/publish", headers=_h(TOKEN))
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_unpublish_bi_tu_choi(self):
        r = self.client.post(f"/api/novels/{self.novel_id}/unpublish", headers=_h(TOKEN))
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_xoa_novel_bi_tu_choi(self):
        r = self.client.delete(f"/api/novels/{self.novel_id}", headers=_h(TOKEN))
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_sua_nguoi_dung_khac_bi_tu_choi(self):
        """Khong co endpoint quan ly user nao chap nhan token dich vu — thu
        be mat gan nhat (ho so nguoi dung) van phai tu choi."""
        r = self.client.patch("/api/account/profile", json={"display_name": "x"},
                              headers=_h(TOKEN))
        self.assertIn(r.status_code, (401, 403, 404, 405), r.text)

    def test_be_mat_schema_canary_khong_mo_qua_harvester(self):
        """Harvester khong duoc coi la canary — be mat rieng cua canary van
        tu choi token harvester."""
        r = self.client.post("/api/admin/canary/novels",
                             json={"title": "x", "canary_run_id": "run-x"},
                             headers=_h(TOKEN))
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_canary_token_khong_leo_len_thanh_harvester(self):
        """Chieu nguoc lai: mot token CANARY that khong duoc chap nhan tren
        cac route cua harvester (POST /api/novels)."""
        canary_token = "canary-token-that-trong-test-nay"
        cau_hinh = dataclasses.replace(server_main.settings,
                                       harvester_service_token=TOKEN,
                                       canary_service_token=canary_token)
        with mock.patch.object(server_main, "settings", cau_hinh):
            client = TestClient(server_main.app)
            r = client.post("/api/novels", json={"title": "x"},
                            headers=_h(canary_token))
            self.assertIn(r.status_code, (401, 403), r.text)


class HarvesterInvalidTokenTest(unittest.TestCase):
    def setUp(self) -> None:
        cau_hinh = dataclasses.replace(server_main.settings,
                                       harvester_service_token=TOKEN)
        vá = mock.patch.object(server_main, "settings", cau_hinh)
        vá.start()
        self.addCleanup(vá.stop)
        self.client = TestClient(server_main.app)

    def test_token_sai_bi_tu_choi(self):
        r = self.client.post("/api/novels", json={"title": "x"},
                             headers=_h("token-hoan-toan-sai"))
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_khong_co_token_bi_tu_choi(self):
        r = self.client.post("/api/novels", json={"title": "x"})
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_deployment_chua_cau_hinh_token_khong_ai_vao_duoc(self):
        cau_hinh = dataclasses.replace(server_main.settings, harvester_service_token="")
        with mock.patch.object(server_main, "settings", cau_hinh):
            client = TestClient(server_main.app)
            r = client.post("/api/novels", json={"title": "x"}, headers=_h(""))
            self.assertIn(r.status_code, (401, 403), r.text)

    def test_loi_khong_bao_gio_lo_gia_tri_token(self):
        r = self.client.post("/api/novels", json={"title": "x"},
                             headers=_h("token-hoan-toan-sai"))
        self.assertNotIn(TOKEN, r.text)
        self.assertNotIn("token-hoan-toan-sai", r.text)


if __name__ == "__main__":
    unittest.main()
