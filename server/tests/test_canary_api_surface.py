"""Be mat `/api/admin/canary/*` — kiem BIEN cua danh tinh dich vu canary.

Phan lon tep nay la test PHU DINH. "Canary tao duoc truyen vut di" thi de;
dieu dang kiem la canary KHONG cham duoc vao thu gi khac — dac biet la 13
series that dang chay tren san xuat.
"""
from __future__ import annotations

import dataclasses
import unittest
from unittest import mock

from fastapi.testclient import TestClient  # noqa: E402

import server.main as server_main  # noqa: E402
from server.domain import Novel, PublishState  # noqa: E402

TOKEN_CANARY = "canary-token-chi-dung-trong-test"
RUN_A = "run-aaaa"
RUN_B = "run-bbbb"


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class CanaryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        # `Settings` la frozen dataclass (co chu y — cau hinh khong bi sua luc
        # chay), nen ta THAY THE ca doi tuong settings thay vi gan tung truong.
        #
        # Va ta phai lam trong setUp chu KHONG dua vao bien moi truong dat o
        # dau tep: khi chay ca bo test, mot module khac co the da import
        # `server.main` truoc, luc do settings da duoc nap xong va bien moi
        # truong khong con tac dung. Test phai doc lap voi THU TU import.
        cau_hinh = dataclasses.replace(server_main.settings,
                                       canary_service_token=TOKEN_CANARY)
        vá = mock.patch.object(server_main, "settings", cau_hinh)
        vá.start()
        self.addCleanup(vá.stop)
        self.client = TestClient(server_main.app)

    def _tao(self, run_id: str = RUN_A, title: str = "QA canary novel"):
        return self.client.post(
            "/api/admin/canary/novels",
            json={"title": title, "canary_run_id": run_id},
            headers=_h(TOKEN_CANARY),
        )

    # --- duong hanh phuc -------------------------------------------------
    def test_canary_tao_duoc_truyen_vut_di(self):
        r = self._tao()
        self.assertEqual(r.status_code, 201, r.text)
        novel = r.json()["novel"]
        self.assertEqual(novel["state"], PublishState.DRAFT.value,
                         "canary khong duoc tao thu gi da xuat ban")

    def test_truyen_canary_mang_du_nhan_chung_minh_so_huu(self):
        novel_id = self._tao().json()["novel"]["novel_id"]
        got = server_main.store.get_novel(novel_id)
        self.assertEqual(got.owner_id, server_main.settings.canary_user_id)
        self.assertIn(server_main.CANARY_TAG_DISPOSABLE, got.tags)
        self.assertIn(server_main.CANARY_RUN_TAG_PREFIX + RUN_A, got.tags)

    def test_canary_don_duoc_dung_do_minh_tao(self):
        novel_id = self._tao().json()["novel"]["novel_id"]
        r = self.client.delete(
            f"/api/admin/canary/novels/{novel_id}?canary_run_id={RUN_A}",
            headers=_h(TOKEN_CANARY))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["deleted"])

    # --- xac thuc --------------------------------------------------------
    def test_token_sai_bi_tu_choi(self):
        r = self.client.post("/api/admin/canary/novels",
                             json={"title": "x", "canary_run_id": RUN_A},
                             headers=_h("token-hoan-toan-sai"))
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_khong_co_token_bi_tu_choi(self):
        r = self.client.post("/api/admin/canary/novels",
                             json={"title": "x", "canary_run_id": RUN_A})
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_header_di_dang_bi_tu_choi(self):
        for xau in ("", "Bearer", "Basic " + TOKEN_CANARY, "Bearer  "):
            r = self.client.post("/api/admin/canary/novels",
                                 json={"title": "x", "canary_run_id": RUN_A},
                                 headers={"Authorization": xau})
            self.assertIn(r.status_code, (401, 403), f"{xau!r} -> {r.status_code}")

    def test_nguoi_dung_thuong_khong_gia_mao_duoc_canary(self):
        """Token nguoi dung THUONG khong mo duoc be mat canary."""
        reg = self.client.post("/api/auth/register",
                               json={"email": "qa-user@test.local",
                                     "password": "matkhau-du-dai-123"})
        self.assertIn(reg.status_code, (200, 201), reg.text)
        token_nguoi = reg.json()["token"]
        r = self.client.post("/api/admin/canary/novels",
                             json={"title": "x", "canary_run_id": RUN_A},
                             headers=_h(token_nguoi))
        self.assertEqual(r.status_code, 403, r.text)

    # --- bien so huu (phan quan trong nhat) ------------------------------
    def test_canary_khong_xoa_duoc_truyen_that(self):
        """13 series that thuoc nguoi that — canary phai khong cham toi duoc."""
        that = server_main.store.create_novel(Novel(
            owner_id="usr_nguoi_that", title="Series thật của người dùng"))
        r = self.client.delete(
            f"/api/admin/canary/novels/{that.novel_id}?canary_run_id={RUN_A}",
            headers=_h(TOKEN_CANARY))
        self.assertIn(r.status_code, (403, 404), r.text)
        # ...va no VAN CON.
        self.assertIsNotNone(server_main.store.get_novel(that.novel_id))

    def test_canary_khong_sua_duoc_truyen_that(self):
        that = server_main.store.create_novel(Novel(
            owner_id="usr_nguoi_that", title="Series thật khác"))
        r = self.client.post(
            f"/api/admin/canary/novels/{that.novel_id}/chapters",
            json={"canary_run_id": RUN_A, "title": "chen vao", "content": "x"},
            headers=_h(TOKEN_CANARY))
        self.assertIn(r.status_code, (403, 404), r.text)

    def test_canary_khong_don_duoc_do_cua_lan_chay_khac(self):
        novel_id = self._tao(run_id=RUN_A).json()["novel"]["novel_id"]
        r = self.client.delete(
            f"/api/admin/canary/novels/{novel_id}?canary_run_id={RUN_B}",
            headers=_h(TOKEN_CANARY))
        self.assertEqual(r.status_code, 403, r.text)

    def test_thieu_canary_run_id_thi_fail_closed(self):
        novel_id = self._tao().json()["novel"]["novel_id"]
        r = self.client.delete(f"/api/admin/canary/novels/{novel_id}",
                               headers=_h(TOKEN_CANARY))
        # 422 = schema tu choi (canary_run_id bat buoc), 400 = lop kiem tra ben
        # trong tu choi. Ca hai deu la FAIL-CLOSED; dieu quan trong la KHONG xoa.
        self.assertIn(r.status_code, (400, 422), r.text)
        # Khong duoc xoa gi khi chua chung minh so huu.
        self.assertIsNotNone(server_main.store.get_novel(novel_id))

    def test_tao_thieu_canary_run_id_bi_tu_choi(self):
        r = self.client.post("/api/admin/canary/novels",
                             json={"title": "x", "canary_run_id": "   "},
                             headers=_h(TOKEN_CANARY))
        self.assertEqual(r.status_code, 400, r.text)

    # --- khong lan sang be mat chung -------------------------------------
    def test_token_canary_KHONG_mo_duoc_api_novels_chung(self):
        """Diem then chot cua thiet ke: canary khong phai mot tai khoan nguoi
        dung. No khong duoc ghi vao duong `/api/novels` chung."""
        r = self.client.post("/api/novels",
                             json={"title": "khong duoc phep"},
                             headers=_h(TOKEN_CANARY))
        self.assertIn(r.status_code, (401, 403), r.text)

    def test_token_canary_khong_xoa_duoc_qua_api_novels_chung(self):
        that = server_main.store.create_novel(Novel(
            owner_id="usr_nguoi_that", title="Series thật thứ ba"))
        r = self.client.delete(f"/api/novels/{that.novel_id}",
                               headers=_h(TOKEN_CANARY))
        self.assertIn(r.status_code, (401, 403), r.text)
        self.assertIsNotNone(server_main.store.get_novel(that.novel_id))

    def test_bearer_rong_tren_deployment_CHUA_cau_hinh_khong_thanh_canary(self):
        """Tinh huong te nhat co the co, neu so sanh token la `==` don thuan.

        Deployment chua dat token (`canary_service_token == ""`) + request gui
        `Authorization: Bearer ` (khong co gia tri) -> token rong == cau hinh
        rong -> ke go cua vo danh tro thanh canary.

        Da duoc chan o `Settings.is_canary_service_token`, no tra False ngay
        khi BAT KY ben nao rong, TRUOC khi so sanh. Bai nay khoa hanh vi do lai
        tu phia HTTP — nêu ai đó bỏ lớp guard đó, bài này đổ.
        """
        chua_cau_hinh = dataclasses.replace(server_main.settings,
                                            canary_service_token="")
        with mock.patch.object(server_main, "settings", chua_cau_hinh):
            for xau in ("Bearer ", "Bearer", "Bearer  ", "bearer "):
                r = self.client.post("/api/admin/canary/novels",
                                     json={"title": "x", "canary_run_id": RUN_A},
                                     headers={"Authorization": xau})
                self.assertIn(r.status_code, (401, 403),
                              f"{xau!r} da tro thanh canary tren deployment chua cau hinh")

    def test_khong_cau_hinh_token_thi_be_mat_dong_lai(self):
        """Deployment chua dat FAS_CANARY_SERVICE_TOKEN phai DONG, khong mo."""
        chua_cau_hinh = dataclasses.replace(server_main.settings,
                                            canary_service_token="")
        with mock.patch.object(server_main, "settings", chua_cau_hinh):
            r = self.client.post("/api/admin/canary/novels",
                                 json={"title": "x", "canary_run_id": RUN_A},
                                 headers=_h(TOKEN_CANARY))
            self.assertIn(r.status_code, (401, 403), r.text)


if __name__ == "__main__":
    unittest.main()
