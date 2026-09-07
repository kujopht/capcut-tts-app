"""
Bon dieu kien tien quyet cua canary Cloud Run — moi test bat nguon tu mot su
viec quan sat duoc ngay 2026-09-06, khong phai tu suy doan.

1. GHEP KHO/BUCKET. Mot worker duoc cau hinh `APPWRITE_DATABASE_ID=
   fanfic_world_prod` + `R2_BUCKET=fanfic-staging`. Khong bien nao thieu, nen
   `validate()` cho qua sach se. Neu worker do gianh duoc mot job production
   that: audio vao bucket STAGING, `audio_track` tro vao khoa do, job
   `completed`. Duong doc production tra bucket production -> khong thay gi.
   Trinh phat hong CAM LANG, metadata trong hoan toan khoe, khong log nao keu.

2. FALSE POSITIVE cua `voice_runnable_on_this_machine`. Thieu goi `piper-tts`
   thi ham tra `True`, worker NHAN ca 10 job roi chet ngay voi
   `provider_not_installed`, dot het `attempts` va giet vinh vien nhung job ma
   AWS lam duoc.

3. QUAN SAT DUOC cua vong quet. Chi ghi log khi `chay_lai`/`het_luot_thu` khac
   0, nen mot worker quet deu ma khong nhan duoc job nao thi log chi co dong
   `khoi_dong`. Da mat mot vong chan doan vi dieu nay, hai lan trong mot ngay.

4. NHUONG khi thieu model. Anh Cloud Run chi co `ngochuyennew`; mot job
   `piper:ngochuyen` phai duoc ACK va nhuong cho duong quet, khong duoc lam
   Cloud Tasks xoay vong den het `max-attempts`.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from unittest import mock

from server.config import AppwriteSettings, ConfigError, R2Settings, Settings


def _cau_hinh(database_id: str, bucket: str) -> Settings:
    """Mot `Settings` hop le o moi phuong dien TRU cap kho/bucket dang thu."""
    return Settings(
        environment="production",
        data_backend="appwrite",
        storage_backend="r2",
        inline_worker=False,
        cors_origins=("https://fanfic.world",),
        appwrite=AppwriteSettings(
            endpoint="https://appwrite-dev.fanfic.world/v1",
            project_id="fanfic-world-prod",
            api_key="k" * 40,
            database_id=database_id,
        ),
        r2=R2Settings(
            account_id="a" * 32,
            access_key_id="b" * 32,
            secret_access_key="c" * 64,
            bucket=bucket,
        ),
    )


class GhepKhoVaBucket(unittest.TestCase):

    def test_kho_production_voi_bucket_staging_bi_TU_CHOI(self):
        """Chinh cau hinh da gay su co 2026-09-06."""
        with self.assertRaises(ConfigError) as ctx:
            _cau_hinh("fanfic_world_prod", "fanfic-staging").validate()
        loi = str(ctx.exception)
        self.assertIn("fanfic_world_prod", loi)
        self.assertIn("fanfic-prod", loi)
        # Thong diep phai noi ro HAU QUA, khong chi "sai cau hinh": nguoi doc
        # log luc 2 gio sang can biet vi sao no dang can duong minh.
        self.assertIn("câm lặng", loi)

    def test_kho_production_voi_bucket_production_duoc_QUA(self):
        _cau_hinh("fanfic_world_prod", "fanfic-prod").validate()   # khong nem

    def test_kho_khong_phai_production_thi_khong_bi_rang_buoc(self):
        """Chieu nguoc lai KHONG bi chan — staging dung bucket nao la viec cua no."""
        _cau_hinh("gate_tts_tmp_20260906", "fanfic-staging").validate()
        _cau_hinh("fanfic_world_dev", "fanfic-dev").validate()

    def test_phep_kiem_nay_KHONG_de_lot_cau_hinh_da_gay_su_co(self):
        """
        Test co RANG: chay chinh phep kiem len cau hinh CU (chua co guard) phai
        that bai. Neu `GHEP_BAT_BUOC` bi lam rong thi test nay phai do ngay,
        khong duoc am tham dat vi khong con gi de kiem.
        """
        s = _cau_hinh("fanfic_world_prod", "fanfic-staging")
        with mock.patch.object(Settings, "GHEP_BAT_BUOC", {}):
            s.validate()          # khong con guard -> lot, dung nhu truoc day
        with self.assertRaises(ConfigError):
            s.validate()          # co guard -> chan


class GiongChayDuocTrenMayNay(unittest.TestCase):

    def setUp(self):
        from server import tts_bridge

        self.tts_bridge = tts_bridge
        tts_bridge.get_registry.cache_clear() if hasattr(
            tts_bridge.get_registry, "cache_clear") else None

    def test_thieu_runtime_piper_thi_NHUONG_chu_khong_nhan(self):
        """
        Day la loi da lam chet 10 job that.

        Gia lap dung tinh huong do: provider `piper` co trong registry nhung
        `installed=False` (goi `piper-tts` khong import duoc), va `voice_by_id`
        tra `None` vi khong dung duoc provider.
        """
        gia = mock.Mock()
        gia.get.return_value = mock.Mock(installed=False)
        gia.voice_by_id.return_value = None
        with mock.patch.object(self.tts_bridge, "get_registry", return_value=gia):
            self.assertFalse(
                self.tts_bridge.voice_runnable_on_this_machine("piper:ngochuyen"),
                "thieu runtime Piper thi phai NHUONG job, khong duoc nhan roi chet",
            )

    def test_co_runtime_nhung_thieu_file_model_thi_van_NHUONG(self):
        gia = mock.Mock()
        gia.get.return_value = mock.Mock(installed=True)
        gia.voice_by_id.return_value = mock.Mock(installed=False)
        with mock.patch.object(self.tts_bridge, "get_registry", return_value=gia):
            self.assertFalse(
                self.tts_bridge.voice_runnable_on_this_machine("piper:ngochuyen"))

    def test_co_du_runtime_va_model_thi_NHAN(self):
        gia = mock.Mock()
        gia.get.return_value = mock.Mock(installed=True)
        gia.voice_by_id.return_value = mock.Mock(installed=True)
        with mock.patch.object(self.tts_bridge, "get_registry", return_value=gia):
            self.assertTrue(
                self.tts_bridge.voice_runnable_on_this_machine("piper:ngochuyennew"))

    def test_giong_khong_cuc_bo_luon_chay_duoc(self):
        """CapCut/Edge khong can model — khong duoc hoi registry lam gi."""
        self.assertTrue(
            self.tts_bridge.voice_runnable_on_this_machine("edge:vi-VN-NamMinh"))

    def test_giong_la_hoan_toan_thi_de_duong_cu_xu_ly(self):
        """
        Co runtime, nhung `voice_by_id` khong biet giong nay -> tra True.

        Phan biet nay la ca diem cua ban sua: 'khong biet giong' KHAC 'thieu
        runtime'. Gop hai thu vao nhau chinh la loi cu.
        """
        gia = mock.Mock()
        gia.get.return_value = mock.Mock(installed=True)
        gia.voice_by_id.return_value = None
        with mock.patch.object(self.tts_bridge, "get_registry", return_value=gia):
            self.assertTrue(
                self.tts_bridge.voice_runnable_on_this_machine("piper:giong_la"))


class VongQuetQuanSatDuoc(unittest.TestCase):

    def setUp(self):
        from server import worker

        self.worker = worker
        worker._lan_ghi_cuoi.update(chu_ky=0, van_tay=None)

    def test_hang_doi_rong_thi_KHONG_ghi(self):
        rong = {"da_quet": 0, "bo_qua_con_lease": 0, "chay_lai": 0,
                "het_luot_thu": 0, "khong_nhan_duoc": 0, "bo_qua_con_moi": 0}
        self.assertFalse(self.worker._dang_ghi_bao_cao(rong, 1))

    def test_bo_qua_thieu_model_PHAI_duoc_ghi(self):
        """Nhanh nay truoc day im lang tuyet doi — la ca ly do co ban sua."""
        bc = {"da_quet": 10, "bo_qua_thieu_model": 10, "chay_lai": 0,
              "het_luot_thu": 0}
        self.assertTrue(self.worker._dang_ghi_bao_cao(bc, 1))

    def test_khong_nhan_duoc_PHAI_duoc_ghi(self):
        """Hang `job_claims` con sot -> claim hong -> truoc day khong log gi."""
        bc = {"da_quet": 10, "khong_nhan_duoc": 10, "chay_lai": 0}
        self.assertTrue(self.worker._dang_ghi_bao_cao(bc, 1))

    def test_bao_cao_khong_doi_thi_khong_ghi_lai_moi_chu_ky(self):
        bc = {"da_quet": 10, "bo_qua_thieu_model": 10}
        self.assertTrue(self.worker._dang_ghi_bao_cao(bc, 1))
        for chu_ky in range(2, 40):
            self.assertFalse(self.worker._dang_ghi_bao_cao(dict(bc), chu_ky),
                             f"chu ky {chu_ky} khong duoc ghi lai")

    def test_tinh_hinh_DOI_thi_ghi_ngay(self):
        self.assertTrue(self.worker._dang_ghi_bao_cao(
            {"da_quet": 10, "bo_qua_thieu_model": 10}, 1))
        self.assertTrue(self.worker._dang_ghi_bao_cao(
            {"da_quet": 10, "bo_qua_thieu_model": 9, "chay_lai": 1}, 2))

    def test_co_nhip_nhac_lai_de_biet_worker_con_quet(self):
        bc = {"da_quet": 10, "bo_qua_thieu_model": 10}
        self.assertTrue(self.worker._dang_ghi_bao_cao(bc, 1))
        self.assertFalse(self.worker._dang_ghi_bao_cao(dict(bc), 50))
        self.assertTrue(
            self.worker._dang_ghi_bao_cao(dict(bc), 1 + self.worker.NHAC_LAI_MOI),
            "phai nhac lai sau NHAC_LAI_MOI chu ky de khong im lang vo han",
        )


class NhuongKhiThieuModel(unittest.TestCase):

    def test_service_ACK_chu_khong_bat_cloud_tasks_xoay_vong(self):
        """
        Doc THANG ma nguon: nhanh thieu model phai `return`, khong `raise 409`.

        409 se lam Cloud Tasks thu lai theo backoff, nhung anh container nay se
        khong bao gio co them model — xoay vong den het `max-attempts` roi thoi.
        """
        import inspect

        from server import tts_task_service

        src = inspect.getsource(tts_task_service.chay_task)
        khoi = src[src.index("voice_runnable_on_this_machine"):]
        khoi = khoi[:khoi.index("get_chapter")]
        self.assertIn("nhuong_thieu_model", khoi)
        self.assertNotIn(
            "HTTP_409_CONFLICT", khoi,
            "nhanh thieu model khong duoc tra 409 — hang doi se xoay vong vo ich",
        )


if __name__ == "__main__":
    unittest.main()
