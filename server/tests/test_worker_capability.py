"""
Worker chi duoc NHAN job ma may no chay duoc.

Boi canh that (production 13/08/2026): hai worker cung quet mot hang doi —
GCE giu du bo model NghiTTS, laptop chi co mot. Worker khong co model ma nhan
job giong cuc bo thi synthesis that bai va job bi danh dau `failed` VINH VIEN,
du worker kia lam duoc. Bo test nay ghim rao chan: worker chuyen trach NHUONG
job thieu model; che do inline (dev, mot tien trinh) van nhan-va-that-bai de
loi "chua tai model" hien ra ro rang thay vi job treo pending vo han.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from fastapi.testclient import TestClient

from server import main as server_main
from server import tts_bridge
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.domain import JobStatus, TtsJob
from server.tests.voice_stub import dung_registry_gia


class MayNayChayDuocTest(unittest.TestCase):
    def setUp(self) -> None:
        dung_registry_gia(self, "piper:co-model", "piper:thieu-model",
                          "capcut:v1")
        for v in tts_bridge._registry.voices:
            v.installed = (v.id != "piper:thieu-model")

    def test_giong_khong_cuc_bo_luon_chay_duoc(self):
        self.assertTrue(
            tts_bridge.voice_runnable_on_this_machine("capcut:v1"))

    def test_giong_cuc_bo_co_model(self):
        self.assertTrue(
            tts_bridge.voice_runnable_on_this_machine("piper:co-model"))

    def test_giong_cuc_bo_thieu_model(self):
        self.assertFalse(
            tts_bridge.voice_runnable_on_this_machine("piper:thieu-model"))

    def test_giong_la_khong_bi_chan(self):
        """Id khong co trong registry -> de duong cu xu ly (nhan -> loi ro)."""
        self.assertTrue(
            tts_bridge.voice_runnable_on_this_machine("piper:khong-ton-tai"))


class BoQuetNhuongJobThieuModelTest(unittest.TestCase):
    def setUp(self) -> None:
        dung_registry_gia(self, "piper:thieu-model")
        tts_bridge._registry.voices[0].installed = False
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self._settings_cu = server_main.settings
        self._can_cu = server_main._CAN_RUN_JOBS
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.settings = self._settings_cu
        server_main._CAN_RUN_JOBS = self._can_cu

    def _job_piper_pending(self) -> TtsJob:
        job = TtsJob(owner_id="u1", chapter_id="ch-khong-can-co",
                     voice_id="piper:thieu-model", content_hash="bam-gia")
        return server_main.store.create_job(job)

    def test_worker_chuyen_trach_nhuong(self):
        """inline TAT (worker rieng): khong nhan, job con nguyen `pending`."""
        server_main.settings = replace(server_main.settings,
                                       inline_worker=False)
        server_main._CAN_RUN_JOBS = True  # worker goi enable_job_execution()
        job = self._job_piper_pending()

        report = server_main.recover_stale_jobs(pending_min_age_seconds=0)

        self.assertEqual(report.get("bo_qua_thieu_model"), 1)
        self.assertIs(server_main.store.get_job(job.job_id).status,
                      JobStatus.PENDING)

    def test_che_do_inline_van_nhan_va_bao_loi(self):
        """
        inline BAT (dev, mot tien trinh): khong co ai de nhuong — job phai
        ket thuc voi loi doc duoc, khong duoc treo pending vo han.
        """
        job = self._job_piper_pending()

        report = server_main.recover_stale_jobs(pending_min_age_seconds=0)

        self.assertNotIn("bo_qua_thieu_model", report)
        # Job da duoc nhan (chapter khong ton tai -> failed ngay trong vong
        # quet, khong can doi thread): dieu quan trong la no KHONG con pending.
        self.assertIsNot(server_main.store.get_job(job.job_id).status,
                         JobStatus.PENDING)


if __name__ == "__main__":
    unittest.main(verbosity=2)
