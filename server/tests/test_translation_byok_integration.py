"""
Tich hop BYOK (V5.1) trong `TranslationService` — shared/personal fallback,
waiting_for_provider reason/action, resume-on-connect, cach ly nguoi dung.

Provider gia (khong goi mang that) boc qua `ConfiguredProvider` — kich ban
thanh cong/loi dieu khien duoc, giong mau `test_translation_editor.py`.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.translation import TranslationJobStatus
from server.translation_byok_crypto import ByokCrypto, sinh_master_key_moi
from server.translation_byok_service import ProviderConnectionService
from server.translation_provider_registry import ConfiguredProvider, ProviderRegistry
from server.translation_providers import TranslationProviderError
from server.translation_service import TranslationService
from server.translation_store import MockTranslationStore
from server.tests.test_translation_service import cho_job_xong

KHOA_TEST = sinh_master_key_moi()
VB_MOT_CHUONG = "第1章 Khởi đầu\n萧炎看向药老。他继续前进。第一句。\n\n第二句đoạn hai。"


class _LuonThatBaiProvider:
    name = "shared-het-han-muc"

    def translate_segment(self, text, *, context):
        raise TranslationProviderError("Hết hạn mức miễn phí.")


class _LuonThanhCongProvider:
    def __init__(self, name="ok"):
        self.name = name
        self.so_lan_goi = 0

    def translate_segment(self, text, *, context):
        self.so_lan_goi += 1
        return f"[{self.name}] {text}"


def _moi_truong(shared_ok: bool):
    identity = MockIdentityAdapter()
    novels = MockMetadataStore()
    store = MockTranslationStore()
    shared_provider = (_LuonThanhCongProvider("shared")
                      if shared_ok else _LuonThatBaiProvider())
    shared_cp = ConfiguredProvider(
        provider_id="shared-groq", model_id="m", display_name="x",
        quality_hint="x", provider=shared_provider)
    registry = ProviderRegistry([shared_cp])
    crypto = ByokCrypto.tu_moi_truong(KHOA_TEST)
    byok = ProviderConnectionService(store, crypto=crypto)
    svc = TranslationService(store, novels, registry=registry, byok=byok)
    an = identity.register("an@vidu.vn", "MatKhau123", "An")
    return svc, byok, store, an


class SharedExhaustedNoPersonalTest(unittest.TestCase):
    def test_waiting_reason_la_shared_exhausted_va_action_ket_noi_ca_nhan(self):
        svc, byok, store, an = _moi_truong(shared_ok=False)
        p = svc.create_project(an.user_id, title="x", source_text=VB_MOT_CHUONG,
                               quality_mode="nhanh")
        job = svc.create_job(p.project_id, an.user_id)
        han = time.time() + 5
        while time.time() < han:
            job = svc.get_job(job.job_id, an.user_id)
            if job.status is TranslationJobStatus.WAITING_FOR_PROVIDER:
                break
            time.sleep(0.005)
        self.assertEqual(job.status, TranslationJobStatus.WAITING_FOR_PROVIDER)
        self.assertEqual(job.waiting_reason, "shared_free_quota_exhausted")
        self.assertEqual(job.waiting_action, "connect_personal_provider")


class SharedExhaustedWithPersonalTest(unittest.TestCase):
    """
    CHU Y: `ProviderConnectionService.build_all_configured_providers` xay
    dung mot `GroqProvider` THAT (httpx that, khong client gia) tu key da
    ket noi — dung y THIET KE (production khong the tiem client gia vao mot
    ham chi nhan api_key). O day PATCH chinh ham do de tra ve mot
    `ConfiguredProvider` GIA khi kiem tra duong dich qua job — dung mau voi
    `test_ca_shared_va_personal_that_bai...`/`ResumeOnConnectTest` da lam.
    Rieng `connect()` (validate + luu) van goi that qua `kiem_tra_ket_noi_groq`
    duoc patch — kiem duoc duong luu/ma hoa THAT ma khong goi mang.
    """

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_fallback_sang_personal_thanh_cong(self, kiem_tra):
        svc, byok, store, an = _moi_truong(shared_ok=False)
        byok.connect(an.user_id, "groq", "gsk_ca_nhan_00000AB42",
                    selected_model="qwen-test")
        thanh_cong_cp = ConfiguredProvider(
            provider_id="groq", model_id="qwen-test", display_name="x",
            quality_hint="x", provider=_LuonThanhCongProvider("personal"),
            credential_source="personal")
        p = svc.create_project(an.user_id, title="x", source_text=VB_MOT_CHUONG,
                               quality_mode="nhanh")
        with patch.object(byok, "build_all_configured_providers",
                          return_value=[thanh_cong_cp]):
            job = cho_job_xong(
                svc, svc.create_job(p.project_id, an.user_id).job_id, an.user_id)
        self.assertEqual(job.status, TranslationJobStatus.COMPLETED)
        project = svc.get_project(p.project_id, an.user_id)
        self.assertTrue(project.translated_chapters[0])
        lich_su = svc.list_versions(p.project_id, an.user_id)
        nguon_dung = {v.provider_id for v in lich_su if v.operation == "auto_translate"}
        self.assertIn("groq", nguon_dung)

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_provenance_ghi_dung_provider_ca_nhan(self, kiem_tra):
        svc, byok, store, an = _moi_truong(shared_ok=False)
        byok.connect(an.user_id, "groq", "gsk_ca_nhan_00000AB42")
        thanh_cong_cp = ConfiguredProvider(
            provider_id="groq", model_id="qwen/qwen3.6-27b", display_name="x",
            quality_hint="x", provider=_LuonThanhCongProvider("personal"),
            credential_source="personal")
        p = svc.create_project(an.user_id, title="x", source_text=VB_MOT_CHUONG,
                               quality_mode="nhanh")
        with patch.object(byok, "build_all_configured_providers",
                          return_value=[thanh_cong_cp]):
            cho_job_xong(
                svc, svc.create_job(p.project_id, an.user_id).job_id, an.user_id)
        # provider_id/model_id THAT trong lich su phai la cua Groq ca nhan.
        lich_su = svc.list_versions(p.project_id, an.user_id)
        self.assertTrue(any(v.provider_id == "groq" and v.model_id == "qwen/qwen3.6-27b"
                           for v in lich_su))

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_ca_shared_va_personal_that_bai_van_waiting_voi_ly_do_personal(self, kiem_tra):
        svc, byok, store, an = _moi_truong(shared_ok=False)
        byok.connect(an.user_id, "groq", "gsk_ca_nhan_00000AB42")
        # Lam personal CUNG that bai bang cach thay the provider da ket noi
        # bang mot provider gia luon loi — mo phong qua patch build de tra
        # ve mot ConfiguredProvider that bai.
        that_bai_cp = ConfiguredProvider(
            provider_id="groq", model_id="m", display_name="x",
            quality_hint="x", provider=_LuonThatBaiProvider())
        with patch.object(byok, "build_all_configured_providers",
                          return_value=[that_bai_cp]):
            p = svc.create_project(an.user_id, title="x", source_text=VB_MOT_CHUONG,
                                   quality_mode="nhanh")
            job = svc.create_job(p.project_id, an.user_id)
            han = time.time() + 5
            while time.time() < han:
                job = svc.get_job(job.job_id, an.user_id)
                if job.status is TranslationJobStatus.WAITING_FOR_PROVIDER:
                    break
                time.sleep(0.005)
        self.assertEqual(job.status, TranslationJobStatus.WAITING_FOR_PROVIDER)
        self.assertEqual(job.waiting_reason, "personal_quota_exhausted")
        self.assertEqual(job.waiting_action, "")


class PreferPersonalTest(unittest.TestCase):
    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_prefer_personal_thu_ca_nhan_truoc_ca_khi_shared_dung_duoc(self, kiem_tra):
        svc, byok, store, an = _moi_truong(shared_ok=True)
        byok.connect(an.user_id, "groq", "gsk_ca_nhan_00000AB42")
        p = svc.create_project(an.user_id, title="x", source_text=VB_MOT_CHUONG,
                               quality_mode="nhanh")
        # prefer_personal_provider khong co route rieng trong test nay —
        # chinh truc tiep qua project (mo phong da PATCH qua route o Phan L).
        project = svc.get_project(p.project_id, an.user_id)
        project.prefer_personal_provider = True
        store.save_project(project)

        thanh_cong_cp = ConfiguredProvider(
            provider_id="groq", model_id="m", display_name="x",
            quality_hint="x", provider=_LuonThanhCongProvider("personal"),
            credential_source="personal")
        with patch.object(byok, "build_all_configured_providers",
                          return_value=[thanh_cong_cp]):
            job = cho_job_xong(
                svc, svc.create_job(p.project_id, an.user_id).job_id, an.user_id)
        self.assertEqual(job.status, TranslationJobStatus.COMPLETED)
        lich_su = svc.list_versions(p.project_id, an.user_id)
        # Ca nhan (provider_id="groq") duoc dung, KHONG phai shared-groq —
        # du shared_ok=True (san sang dung duoc), prefer_personal PHAI thu
        # ca nhan TRUOC.
        self.assertTrue(all(v.provider_id != "shared-groq"
                           for v in lich_su if v.operation == "auto_translate"))


class ResumeOnConnectTest(unittest.TestCase):
    def test_ket_noi_ca_nhan_lam_job_dang_cho_tiep_tuc_ngay(self):
        svc, byok, store, an = _moi_truong(shared_ok=False)
        p = svc.create_project(an.user_id, title="x", source_text=VB_MOT_CHUONG,
                               quality_mode="nhanh")
        job_ban_dau = svc.create_job(p.project_id, an.user_id)
        han = time.time() + 5
        while time.time() < han:
            job = svc.get_job(job_ban_dau.job_id, an.user_id)
            if job.status is TranslationJobStatus.WAITING_FOR_PROVIDER:
                break
            time.sleep(0.005)
        self.assertEqual(job.status, TranslationJobStatus.WAITING_FOR_PROVIDER)

        # Bay gio "ket noi" mot provider ca nhan LUON THANH CONG (thay the
        # registry cua shared van that bai — ca nhan la duong cuu).
        thanh_cong_cp = ConfiguredProvider(
            provider_id="groq", model_id="m", display_name="x",
            quality_hint="x", provider=_LuonThanhCongProvider("personal"))
        with patch.object(byok, "build_all_configured_providers",
                          return_value=[thanh_cong_cp]):
            so_job_thu = svc.try_resume_user_jobs(an.user_id)
            self.assertEqual(so_job_thu, 1)
            job_cuoi = None
            han = time.time() + 5
            while time.time() < han:
                job_cuoi = svc.get_job(job_ban_dau.job_id, an.user_id)
                if job_cuoi.status is TranslationJobStatus.COMPLETED:
                    break
                time.sleep(0.005)

        self.assertEqual(job_cuoi.status, TranslationJobStatus.COMPLETED)
        # VAN LA CHINH job cu — khong tao job thu hai.
        self.assertEqual(job_cuoi.job_id, job_ban_dau.job_id)
        du_an = svc.list_projects(an.user_id)
        self.assertEqual(len(du_an), 1)  # khong co du an/job trung lap nao khac


class OwnershipTest(unittest.TestCase):
    """Cot loi Part D o tang tich hop: du an cua nguoi dung A KHONG BAO GIO
    dung provider ca nhan cua nguoi dung B."""

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_nguoi_dung_b_khong_dung_duoc_key_cua_a(self, kiem_tra):
        svc, byok, store, an = _moi_truong(shared_ok=False)
        binh = MockIdentityAdapter().register("binh@vidu.vn", "MatKhau123", "Bình")
        # DK: binh dang ky qua identity RIENG trong test nay khong dung
        # chung voi `an` — nhung du an van thuoc ve `an`, chi ket noi ca
        # nhan duoc tao cho "user-b-gia" de kiem tra AN KHONG THAY duoc no.
        byok.connect("user-b-gia", "groq", "gsk_cua_b_00000CCCC")

        p = svc.create_project(an.user_id, title="x", source_text=VB_MOT_CHUONG,
                               quality_mode="nhanh")
        job = svc.create_job(p.project_id, an.user_id)
        han = time.time() + 5
        while time.time() < han:
            job = svc.get_job(job.job_id, an.user_id)
            if job.status is TranslationJobStatus.WAITING_FOR_PROVIDER:
                break
            time.sleep(0.005)
        # "an" KHONG co ket noi rieng -> van roi vao waiting, KHONG dung
        # duoc key cua "user-b-gia" du no ton tai trong CUNG mot store.
        self.assertEqual(job.status, TranslationJobStatus.WAITING_FOR_PROVIDER)
        self.assertEqual(job.waiting_reason, "shared_free_quota_exhausted")


if __name__ == "__main__":
    unittest.main()
