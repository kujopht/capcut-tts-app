"""Danh tinh dich vu CANARY — thay cho Bearer phien cua mot admin nguoi that.

Trong tam cua tep nay KHONG phai "canary goi duoc route scraper" (de), ma la
"canary KHONG voi toi duoc bat cu thu gi khac" (kho, va la ly do ton tai cua
thiet ke nay). Mot nang luc hep chi co gia tri neu bien cua no duoc kiem thu
truc tiep, nen phan lon test o day la test PHU DINH.
"""
from __future__ import annotations

import unittest

from server.config import Settings
from server.domain import AdminRole

TOKEN = "canary-service-token-dung-cho-test-khong-phai-that"


def _settings(**kw) -> Settings:
    return Settings(canary_service_token=TOKEN, **kw)


class CanaryTokenMatchingTest(unittest.TestCase):
    def test_token_dung_thi_khop(self):
        self.assertTrue(_settings().is_canary_service_token(TOKEN))

    def test_token_sai_thi_khong_khop(self):
        self.assertFalse(_settings().is_canary_service_token(TOKEN + "x"))
        self.assertFalse(_settings().is_canary_service_token("hoan-toan-khac"))

    def test_token_rong_gui_len_khong_bao_gio_khop(self):
        self.assertFalse(_settings().is_canary_service_token(""))

    def test_deployment_chua_cau_hinh_khong_tu_mo_cua(self):
        """Truong hop nguy hiem nhat: server CHUA dat FAS_CANARY_SERVICE_TOKEN.

        Neu so sanh duoc thuc hien ngay, mot request gui chuoi rong se khop voi
        cau hinh rong va tu cap cho minh quyen canary. Phai luon False.
        """
        chua_cau_hinh = Settings(canary_service_token="")
        self.assertFalse(chua_cau_hinh.is_canary_service_token(""))
        self.assertFalse(chua_cau_hinh.is_canary_service_token("bat-ky-gi"))

    def test_khoang_trang_khong_bi_cat_ngam(self):
        """Token khac nhau o khoang trang la token KHAC, khong phai token dung."""
        self.assertFalse(_settings().is_canary_service_token(" " + TOKEN))
        self.assertFalse(_settings().is_canary_service_token(TOKEN + " "))


class CanaryKhongPhaiVaiTroQuanTriTest(unittest.TestCase):
    """Canary KHONG duoc xuat hien trong thang quyen quan tri.

    Neu `admin_role_of` tra ve bat ky thu gi khac NONE cho `canary_user_id`,
    thi moi route dung `admin_profile`/`admin_or_owner_profile` — quan ly nguoi
    dung, kiem duyet, phan tich — se lang le mo ra cho CI. Do chinh la dieu
    thiet ke nay ton tai de ngan.
    """

    def test_canary_user_id_khong_co_vai_tro_quan_tri_nao(self):
        s = _settings()
        self.assertEqual(s.admin_role_of(s.canary_user_id), AdminRole.NONE)

    def test_canary_khong_thanh_admin_du_co_admin_khac_ton_tai(self):
        s = _settings(admin_user_ids=("usr_nguoi_that",),
                      owner_user_ids=("usr_chu_so_huu",))
        self.assertEqual(s.admin_role_of(s.canary_user_id), AdminRole.NONE)
        # ...trong khi nguoi that van giu nguyen quyen cua ho.
        self.assertEqual(s.admin_role_of("usr_nguoi_that"), AdminRole.ADMIN)
        self.assertEqual(s.admin_role_of("usr_chu_so_huu"), AdminRole.OWNER)

    def test_canary_khong_phai_moderator(self):
        s = _settings(moderator_user_ids=("usr_kiem_duyet",))
        self.assertEqual(s.admin_role_of(s.canary_user_id), AdminRole.NONE)


class CanaryIdTrungDacQuyenTest(unittest.TestCase):
    """Cau hinh sai: `canary_user_id` trung voi mot nguoi CO DAC QUYEN.

    Phat hien qua review bao mat doc lap (Antigravity Claude Opus). Neu de
    nguyen, principal canary vua la dich vu vua mang vai tro quan tri that:
    `admin_role_of` tra ve vai tro co dac quyen, va co che "chi xoa cai minh
    vua tao" cua Phase 15 mat y nghia vi hai ben cung chu so huu.
    """

    def test_trung_admin_thi_tu_choi_xac_thuc(self):
        s = Settings(canary_service_token=TOKEN, canary_user_id="usr_x",
                     admin_user_ids=("usr_x",))
        self.assertEqual(s.canary_id_collision(), "FAS_ADMIN_USER_IDS")
        self.assertFalse(s.is_canary_service_token(TOKEN),
                         "cau hinh sai phai fail-closed, khong duoc cap quyen")

    def test_trung_owner_thi_tu_choi_xac_thuc(self):
        s = Settings(canary_service_token=TOKEN, canary_user_id="usr_x",
                     owner_user_ids=("usr_x",))
        self.assertEqual(s.canary_id_collision(), "FAS_OWNER_USER_IDS")
        self.assertFalse(s.is_canary_service_token(TOKEN))

    def test_trung_moderator_thi_tu_choi_xac_thuc(self):
        s = Settings(canary_service_token=TOKEN, canary_user_id="usr_x",
                     moderator_user_ids=("usr_x",))
        self.assertEqual(s.canary_id_collision(), "FAS_MODERATOR_USER_IDS")
        self.assertFalse(s.is_canary_service_token(TOKEN))

    def test_khong_trung_thi_van_hoat_dong_binh_thuong(self):
        s = Settings(canary_service_token=TOKEN, canary_user_id="svc_canary",
                     admin_user_ids=("usr_nguoi_that",))
        self.assertEqual(s.canary_id_collision(), "")
        self.assertTrue(s.is_canary_service_token(TOKEN))


class CanaryUserIdOnDinhTest(unittest.TestCase):
    """Phase 15 don dep bang cach "chi xoa cai minh vua tao" — co che do can
    mot chu so huu ON DINH, nen `canary_user_id` phai co mac dinh chac chan."""

    def test_co_mac_dinh_khong_rong(self):
        self.assertTrue(Settings().canary_user_id)

    def test_mac_dinh_khong_trung_voi_user_that(self):
        s = Settings(admin_user_ids=("usr_nguoi_that",))
        self.assertNotIn(s.canary_user_id, s.admin_user_ids)


if __name__ == "__main__":
    unittest.main()
