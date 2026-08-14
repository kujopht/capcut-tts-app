"""
Editor (Part N), lich su ban dich (Part O), va `waiting_for_provider`
(Part Q4) — o tang `TranslationService`.
"""

from __future__ import annotations

import time
import unittest

from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.translation import ManualEditWouldBeOverwritten, TranslationError, TranslationJobStatus
from server.translation_provider_registry import (
    AllProvidersUnavailable,
    ConfiguredProvider,
    ProviderRegistry,
)
from server.translation_providers import TranslationContext, TranslationProviderError
from server.translation_service import TRANSLATION_JOB_MAX_ATTEMPTS, TranslationService
from server.translation_store import MockTranslationStore
from server.tests.test_translation_service import cho_job_xong

VB_MOT_CHUONG = "第1章 Khởi đầu\n萧炎看向药老。他继续前进。第一句。\n\n第二句đoạn hai。"
VB_HAI_CHUONG = (
    "第1章 Khởi đầu\n萧炎看向药老。\n\n他继续前进。\n第2章 Tiếp theo\n他继续前进。"
)


class Nen(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.novels = MockMetadataStore()
        self.store = MockTranslationStore()
        self.svc = TranslationService(self.store, self.novels)
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")

    def _du_an_da_dich(self, text=VB_MOT_CHUONG):
        p = self.svc.create_project(self.an.user_id, title="Đấu Phá",
                                    source_text=text, quality_mode="van_hoc")
        job = self.svc.create_job(p.project_id, self.an.user_id)
        cho_job_xong(self.svc, job.job_id, self.an.user_id)
        return self.svc.get_project(p.project_id, self.an.user_id)


class ChapterDetailTest(Nen):
    def test_xem_duoc_chuong_chua_dich_xong(self):
        p = self.svc.create_project(self.an.user_id, title="x",
                                    source_text=VB_HAI_CHUONG)
        chi_tiet = self.svc.get_chapter_detail(p.project_id, self.an.user_id, 1)
        self.assertFalse(chi_tiet["is_translated"])
        self.assertEqual(chi_tiet["translated_text"], "")
        self.assertTrue(chi_tiet["source_text"])

    def test_chuong_khong_ton_tai_bi_tu_choi(self):
        p = self.svc.create_project(self.an.user_id, title="x",
                                    source_text=VB_MOT_CHUONG)
        with self.assertRaises(TranslationError):
            self.svc.get_chapter_detail(p.project_id, self.an.user_id, 99)

    def test_da_dich_thi_manually_edited_la_false(self):
        p = self._du_an_da_dich()
        chi_tiet = self.svc.get_chapter_detail(p.project_id, self.an.user_id, 0)
        self.assertTrue(chi_tiet["is_translated"])
        self.assertFalse(chi_tiet["manually_edited"])


class SaveChapterEditTest(Nen):
    def test_luu_sua_tay_thanh_cong_va_danh_dau(self):
        p = self._du_an_da_dich()
        chi_tiet = self.svc.save_chapter_edit(
            p.project_id, self.an.user_id, 0, "Bản dịch tôi tự sửa tay.")
        self.assertTrue(chi_tiet["manually_edited"])
        self.assertEqual(chi_tiet["translated_text"], "Bản dịch tôi tự sửa tay.")

    def test_luu_sua_tay_rong_bi_tu_choi(self):
        p = self._du_an_da_dich()
        with self.assertRaises(TranslationError):
            self.svc.save_chapter_edit(p.project_id, self.an.user_id, 0, "   ")

    def test_chuong_chua_dich_khong_luu_duoc(self):
        p = self.svc.create_project(self.an.user_id, title="x",
                                    source_text=VB_HAI_CHUONG)
        with self.assertRaises(TranslationError):
            self.svc.save_chapter_edit(p.project_id, self.an.user_id, 1, "abc")

    def test_ghi_lai_lich_su_manual_edit(self):
        p = self._du_an_da_dich()
        self.svc.save_chapter_edit(p.project_id, self.an.user_id, 0, "Sửa lần 1")
        lich_su = self.svc.list_versions(p.project_id, self.an.user_id, 0)
        self.assertEqual(lich_su[0].operation, "manual_edit")
        self.assertEqual(lich_su[0].pass_type, "manual")
        self.assertEqual(lich_su[0].new_text, "Sửa lần 1")


class WarnBeforeOverwriteTest(Nen):
    def test_regen_chuong_sau_sua_tay_bi_chan_khong_force(self):
        p = self._du_an_da_dich()
        self.svc.save_chapter_edit(p.project_id, self.an.user_id, 0, "Sửa tay")
        with self.assertRaises(ManualEditWouldBeOverwritten):
            self.svc.regenerate_chapter(p.project_id, self.an.user_id, 0)

    def test_regen_chuong_voi_force_thi_duoc_phep(self):
        p = self._du_an_da_dich()
        self.svc.save_chapter_edit(p.project_id, self.an.user_id, 0, "Sửa tay")
        chi_tiet = self.svc.regenerate_chapter(
            p.project_id, self.an.user_id, 0, force=True)
        self.assertNotEqual(chi_tiet["translated_text"], "Sửa tay")

    def test_regen_doan_sau_sua_tay_cung_bi_chan(self):
        p = self._du_an_da_dich()
        self.svc.save_chapter_edit(p.project_id, self.an.user_id, 0, "Sửa tay")
        with self.assertRaises(ManualEditWouldBeOverwritten):
            self.svc.regenerate_paragraph(p.project_id, self.an.user_id, 0, 0)

    def test_rerun_pass_sau_sua_tay_cung_bi_chan(self):
        p = self._du_an_da_dich()
        self.svc.save_chapter_edit(p.project_id, self.an.user_id, 0, "Sửa tay")
        with self.assertRaises(ManualEditWouldBeOverwritten):
            self.svc.rerun_pass(p.project_id, self.an.user_id, 0, "qa")

    def test_regen_khong_co_sua_tay_thi_khong_can_force(self):
        p = self._du_an_da_dich()
        # Chua sua tay lan nao -> khong nem loi du force=False (mac dinh).
        self.svc.regenerate_chapter(p.project_id, self.an.user_id, 0)


class RegenerateParagraphPreservesRestTest(Nen):
    def test_regen_mot_doan_giu_nguyen_doan_con_lai(self):
        p = self._du_an_da_dich()
        truoc = self.svc.get_chapter_detail(p.project_id, self.an.user_id, 0)
        so_doan = len(truoc["translated_paragraphs"])
        self.assertGreaterEqual(so_doan, 2)
        sau = self.svc.regenerate_paragraph(p.project_id, self.an.user_id, 0, 1)
        # Doan 0 (khong dong cham) phai GIU NGUYEN — cot loi cua Part N.
        self.assertEqual(sau["translated_paragraphs"][0],
                         truoc["translated_paragraphs"][0])

    def test_regen_doan_khong_ton_tai_bi_tu_choi(self):
        p = self._du_an_da_dich()
        with self.assertRaises(TranslationError):
            self.svc.regenerate_paragraph(p.project_id, self.an.user_id, 0, 99)


class RerunPassTest(Nen):
    def test_rerun_qa_ghi_lich_su_dung_pass_type(self):
        p = self._du_an_da_dich()
        self.svc.rerun_pass(p.project_id, self.an.user_id, 0, "qa")
        lich_su = self.svc.list_versions(p.project_id, self.an.user_id, 0)
        self.assertEqual(lich_su[0].operation, "rerun_pass")
        self.assertEqual(lich_su[0].pass_type, "qa")

    def test_pass_type_khong_hop_le_bi_tu_choi(self):
        p = self._du_an_da_dich()
        with self.assertRaises(TranslationError):
            self.svc.rerun_pass(p.project_id, self.an.user_id, 0, "bien-tap-gia")


class VersionHistoryTest(Nen):
    def test_moi_lan_dich_tu_dong_deu_ghi_lich_su(self):
        p = self._du_an_da_dich()
        lich_su = self.svc.list_versions(p.project_id, self.an.user_id, 0)
        # VAN_HOC = 3 pass (translator/editor/qa) -> it nhat 3 ban ghi auto.
        toan_tu_dong = [v for v in lich_su if v.operation == "auto_translate"]
        self.assertEqual(len(toan_tu_dong), 3)
        vai_tro = {v.pass_type for v in toan_tu_dong}
        self.assertEqual(vai_tro, {"translator", "editor", "qa"})

    def test_restore_ghi_them_khong_xoa_lich_su_cu(self):
        p = self._du_an_da_dich()
        goc = self.svc.get_chapter_detail(p.project_id, self.an.user_id, 0)
        so_luong_truoc = len(self.svc.list_versions(p.project_id, self.an.user_id, 0))
        self.svc.save_chapter_edit(p.project_id, self.an.user_id, 0, "Ban sua 1")
        lich_su = self.svc.list_versions(p.project_id, self.an.user_id, 0)
        version_can_khoi_phuc = lich_su[0].version_id  # ban "Ban sua 1"

        self.svc.save_chapter_edit(p.project_id, self.an.user_id, 0, "Ban sua 2")
        chi_tiet = self.svc.restore_version(
            p.project_id, self.an.user_id, version_can_khoi_phuc)
        self.assertEqual(chi_tiet["translated_text"], "Ban sua 1")

        lich_su_sau = self.svc.list_versions(p.project_id, self.an.user_id, 0)
        # them 3 ban ghi (2 sua tay + 1 restore) so voi ban dau — KHONG mat gi.
        self.assertEqual(len(lich_su_sau), so_luong_truoc + 3)
        self.assertEqual(lich_su_sau[0].operation, "restore")

    def test_khong_thay_du_an_thi_bi_tu_choi(self):
        p = self._du_an_da_dich()
        binh = self.identity.register("binh@vidu.vn", "MatKhau123", "Bình")
        with self.assertRaises(Exception):
            self.svc.list_versions(p.project_id, binh.user_id, 0)


class ProviderCatalogWithoutRegistryTest(Nen):
    def test_khong_co_registry_tra_danh_sach_rong(self):
        self.assertEqual(self.svc.provider_catalog(), [])


class UpdateProviderSettingsTest(Nen):
    def test_cap_nhat_che_do_thu_cong(self):
        p = self.svc.create_project(self.an.user_id, title="x",
                                    source_text=VB_MOT_CHUONG)
        moi = self.svc.update_provider_settings(
            p.project_id, self.an.user_id, provider_mode="manual",
            selected_provider_id="groq", allow_fallback=False)
        self.assertEqual(moi.provider_mode, "manual")
        self.assertEqual(moi.selected_provider_id, "groq")
        self.assertFalse(moi.allow_fallback)

    def test_provider_mode_sai_bi_tu_choi(self):
        p = self.svc.create_project(self.an.user_id, title="x",
                                    source_text=VB_MOT_CHUONG)
        with self.assertRaises(TranslationError):
            self.svc.update_provider_settings(
                p.project_id, self.an.user_id, provider_mode="turbo")


class _LuonHetHanMucProvider:
    """Provider gia LUON nem `TranslationProviderError` — dung trong
    `ProviderRegistry` de mo phong "tat ca provider mien phi het han muc"."""

    name = "het-han-muc"

    def translate_segment(self, text, *, context):
        raise TranslationProviderError("Hết hạn mức miễn phí hôm nay.")


class WaitingForProviderTest(unittest.TestCase):
    """Part Q4: tat ca provider mien phi het han muc -> `waiting_for_provider`,
    KHONG `failed`, cac chuong da xong van con nguyen."""

    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.novels = MockMetadataStore()
        self.store = MockTranslationStore()
        cp = ConfiguredProvider(
            provider_id="het-han-muc", model_id="m", display_name="x",
            quality_hint="x", provider=_LuonHetHanMucProvider())
        self.registry = ProviderRegistry([cp])
        self.svc = TranslationService(self.store, self.novels,
                                      registry=self.registry)
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")

    def test_job_chuyen_sang_waiting_khong_phai_failed(self):
        p = self.svc.create_project(self.an.user_id, title="x",
                                    source_text=VB_MOT_CHUONG)
        job = self.svc.create_job(p.project_id, self.an.user_id)
        han = time.time() + 5
        while time.time() < han:
            job = self.svc.get_job(job.job_id, self.an.user_id)
            if job.status is TranslationJobStatus.WAITING_FOR_PROVIDER:
                break
            time.sleep(0.005)
        self.assertEqual(job.status, TranslationJobStatus.WAITING_FOR_PROVIDER)
        self.assertTrue(job.waiting_retry_at)

    def test_khong_dot_luot_thu_du_lap_lai_nhieu_lan(self):
        """`recover_stale_jobs` KHONG duoc phep chuyen job nay thanh `failed`
        du no da bi claim lai nhieu hon `TRANSLATION_JOB_MAX_ATTEMPTS` lan —
        cho han muc la vong lap BINH THUONG, khong phai dau hieu loi."""
        p = self.svc.create_project(self.an.user_id, title="x",
                                    source_text=VB_MOT_CHUONG)
        job = self.svc.create_job(p.project_id, self.an.user_id)

        for _ in range(TRANSLATION_JOB_MAX_ATTEMPTS + 2):
            han = time.time() + 5
            while time.time() < han:
                job = self.svc.get_job(job.job_id, self.an.user_id)
                if job.status is TranslationJobStatus.WAITING_FOR_PROVIDER:
                    break
                time.sleep(0.005)
            self.assertEqual(job.status, TranslationJobStatus.WAITING_FOR_PROVIDER)
            # Gia lap thoi gian troi qua moc "khong nhan lai truoc".
            from dataclasses import replace

            hien_tai = self.store.get_job(job.job_id)
            self.store._jobs[job.job_id] = replace(  # noqa: SLF001 (test noi bo)
                hien_tai, lease_expires_at="2000-01-01T00:00:00+00:00")
            self.svc.recover_stale_jobs(pending_min_age_seconds=0)

        # Cho THREAD MOI (vua duoc `recover_stale_jobs` khoi dong) thuc su
        # chay den khi gap lai `AllProvidersUnavailable` — `claim_job` da ghi
        # `ANALYZING` NGAY LUC CLAIM (dong bo), truoc khi thread kip chay,
        # nen doc luon o day se thay gia tri TAM THOI do, khong phai ket qua
        # cuoi cung. Xem cung mau `while` o dau moi vong lap ben tren.
        han = time.time() + 5
        while time.time() < han:
            job = self.svc.get_job(job.job_id, self.an.user_id)
            if job.status is TranslationJobStatus.WAITING_FOR_PROVIDER:
                break
            time.sleep(0.005)
        self.assertEqual(job.status, TranslationJobStatus.WAITING_FOR_PROVIDER)
        self.assertNotEqual(job.status, TranslationJobStatus.FAILED)


class _ProviderTraSai:
    """Provider gia LUON tra ve mot ban dich SAI (khong dung thuat ngu da
    khoa) — dung de chung minh khoa glossary CHAN duoc dau ra SAI cua no."""

    name = "sai"

    def translate_segment(self, text, *, context):
        return "Tiêu Vẫn Dịch Sai"


class NovelBibleConsistencyAcrossProvidersTest(unittest.TestCase):
    """Part Q6: doi provider KHONG duoc phep doi thuat ngu da khoa — khoa
    glossary la mot buoc HAU XU LY, ap dung nhu nhau bat ke provider nao
    (hoac provider registry nao) da tao ra van ban."""

    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.novels = MockMetadataStore()
        self.store = MockTranslationStore()
        cp = ConfiguredProvider(
            provider_id="sai", model_id="m", display_name="x",
            quality_hint="x", provider=_ProviderTraSai())
        self.registry = ProviderRegistry([cp])
        self.svc = TranslationService(self.store, self.novels,
                                      registry=self.registry)
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")

    def test_thuat_ngu_khoa_giu_nguyen_du_provider_tra_sai(self):
        p = self.svc.create_project(self.an.user_id, title="x",
                                    source_text=VB_MOT_CHUONG,
                                    quality_mode="nhanh")
        self.svc.add_glossary_entry(
            p.project_id, self.an.user_id, category="character",
            original="Tiêu Vẫn Dịch Sai", translated="Tiêu Viêm")
        self.svc.update_glossary_entry(
            p.project_id, self.an.user_id,
            self.svc.list_glossary(p.project_id, self.an.user_id)[0].term_id,
            locked=True)

        job = self.svc.create_job(p.project_id, self.an.user_id)
        cho_job_xong(self.svc, job.job_id, self.an.user_id)
        project = self.svc.get_project(p.project_id, self.an.user_id)
        # Provider gia LUON tra "Tiêu Vẫn Dịch Sai" — khoa glossary phai
        # thay THANH thuat ngu da chot, bat ke provider nao tao ra van ban.
        self.assertIn("Tiêu Viêm", project.translated_chapters[0])
        self.assertNotIn("Tiêu Vẫn Dịch Sai", project.translated_chapters[0])


if __name__ == "__main__":
    unittest.main()
