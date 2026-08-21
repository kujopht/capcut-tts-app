"""
HOP DONG giua kho mock va kho Appwrite cho Novel Translation Studio (V5).

Cung ly do ton tai voi `test_social_contract.py`/`test_appwrite_v2_contract.py`:
`test_translation_service.py` chay tren `MockTranslationStore`. Neu ban Appwrite
(`server/appwrite_translation_store.py`) lech ngu nghia du mot cho — genre/
naming_mode/quality_mode/status doc sai enum, mang (`chapter_summaries`/
`translated_chapters`/`aliases`) tra ve rong, sap xep nguoc, khong loc dung
`owner_id`/`project_id` — thi TOAN BO test kia van xanh va he thong van hong
o production ngay khi ap schema that.

Dung lai `FakeAppwrite`/`_bo_client` cua `test_appwrite_v2_contract.py`: cung
MOT ban gia lap REST trong bo nho, khong can xay lai tu dau.
"""

from __future__ import annotations

import unittest

from server.appwrite_translation_store import AppwriteTranslationStore
from server.config import AppwriteSettings
from server.translation import GlossaryCategory, TranslationJobStatus
from server.translation_domain import TranslationJob, TranslationProject
from server.translation_store import MockTranslationStore
from server.translation import GlossaryEntry
from server.tests.test_appwrite_v2_contract import FakeAppwrite, _bo_client


def _kho_appwrite(fake: FakeAppwrite) -> AppwriteTranslationStore:
    cfg = AppwriteSettings(endpoint="https://x.invalid/v1", project_id="p",
                           api_key="k", database_id="db")
    kho = AppwriteTranslationStore(cfg, client=_bo_client(fake))
    # Bo qua buoc hoi schema — ban gia lap khong co endpoint metadata, va
    # `_supported_fields` tra None nghia la "gui het", dung nhu ta muon o day
    # (cung quy uoc voi `_kho_appwrite` trong test_appwrite_v2_contract.py).
    kho._attrs_cache = {}
    return kho


class HopDongDich(unittest.TestCase):
    """Moi bai duoi day chay tren CA HAI kho — `ten` bao ro ban nao lech."""

    def _cac_kho(self):
        return [("mock", MockTranslationStore()),
                ("appwrite", _kho_appwrite(FakeAppwrite()))]

    # ===================================================== DU AN

    def test_du_an_ton_tai_dung_truong(self):
        from server.translation import GenrePreset, NamingMode, QualityMode

        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                p = TranslationProject(
                    owner_id="u1", title="Đấu Phá Thương Khung",
                    source_text="萧炎看向药老。",
                    genre=GenrePreset.TIEN_HIEP,
                    naming_mode=NamingMode.HAN_VIET,
                    quality_mode=QualityMode.VAN_HOC,
                    custom_instruction="Giữ giọng văn cổ trang.",
                    source_filename="dau-pha.txt",
                    chapter_summaries=["Chương 1: mở đầu."],
                    translated_chapters=["Tiêu Viêm nhìn về phía Dược Lão."],
                    created_at="2026-08-14T00:00:00+00:00",
                    updated_at="2026-08-14T00:00:00+00:00",
                )
                kho.create_project(p)
                lai = kho.get_project(p.project_id)
                self.assertEqual(lai.owner_id, "u1", ten)
                self.assertEqual(lai.title, "Đấu Phá Thương Khung", ten)
                self.assertEqual(lai.source_text, "萧炎看向药老。", ten)
                self.assertIs(lai.genre, GenrePreset.TIEN_HIEP, ten)
                self.assertIs(lai.naming_mode, NamingMode.HAN_VIET, ten)
                self.assertIs(lai.quality_mode, QualityMode.VAN_HOC, ten)
                self.assertEqual(lai.custom_instruction,
                                 "Giữ giọng văn cổ trang.", ten)
                self.assertEqual(lai.source_filename, "dau-pha.txt", ten)
                self.assertEqual(lai.chapter_summaries,
                                 ["Chương 1: mở đầu."], ten)
                self.assertEqual(lai.translated_chapters,
                                 ["Tiêu Viêm nhìn về phía Dược Lão."], ten)

    def test_owned_project_tu_choi_nguoi_khong_so_huu(self):
        from server.adapters import PermissionDenied

        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                p = TranslationProject(owner_id="u1", title="x",
                                       source_text="một câu.",
                                       created_at="2026-08-14T00:00:00+00:00")
                kho.create_project(p)
                with self.assertRaises(PermissionDenied):
                    kho.owned_project(p.project_id, "u2")

    def test_project_khong_ton_tai_nem_NotFoundError(self):
        from server.adapters import NotFoundError

        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                with self.assertRaises(NotFoundError):
                    kho.get_project("khong-ton-tai")

    def test_save_project_ghi_de_khong_tao_ban_thu_hai(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                p = TranslationProject(owner_id="u1", title="Bản gốc",
                                       source_text="một câu.",
                                       created_at="2026-08-14T00:00:00+00:00")
                kho.create_project(p)
                p.title = "Bản đã sửa"
                p.translated_chapters = ["câu đã dịch"]
                kho.save_project(p)
                lai = kho.get_project(p.project_id)
                self.assertEqual(lai.title, "Bản đã sửa", ten)
                self.assertEqual(lai.translated_chapters, ["câu đã dịch"], ten)
                self.assertEqual(len(kho.list_projects("u1")), 1, ten)

    def test_list_projects_chi_cua_dung_chu_loc_theo_owner(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i, uid in enumerate(["u1", "u2", "u1"]):
                    kho.create_project(TranslationProject(
                        owner_id=uid, title=f"p{i}", source_text="x",
                        created_at=f"2026-08-{10+i:02d}T00:00:00+00:00"))
                ds = kho.list_projects("u1")
                self.assertEqual(len(ds), 2, ten)
                self.assertTrue(all(p.owner_id == "u1" for p in ds), ten)

    def test_list_projects_sap_MOI_NHAT_TRUOC(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i, moc in enumerate(["2026-08-01T00:00:00+00:00",
                                         "2026-08-03T00:00:00+00:00",
                                         "2026-08-02T00:00:00+00:00"]):
                    kho.create_project(TranslationProject(
                        owner_id="u1", title=f"p{i}", source_text="x",
                        created_at=moc))
                ds = kho.list_projects("u1")
                self.assertEqual([p.created_at for p in ds],
                                 ["2026-08-03T00:00:00+00:00",
                                  "2026-08-02T00:00:00+00:00",
                                  "2026-08-01T00:00:00+00:00"], ten)

    # ===================================================== JOB

    def test_tao_roi_doc_job_giu_nguyen_moi_truong(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                j = TranslationJob(
                    project_id="trp_x", owner_id="u1",
                    status=TranslationJobStatus.TRANSLATING,
                    current_chapter=2, total_chapters=5,
                    current_chapter_done_segments=3,
                    current_chapter_total_segments=10,
                    attempts=1, error="",
                    created_at="2026-08-14T00:00:00+00:00",
                    updated_at="2026-08-14T00:01:00+00:00")
                kho.create_job(j)
                lai = kho.get_job(j.job_id)
                self.assertIs(lai.status, TranslationJobStatus.TRANSLATING, ten)
                self.assertEqual(lai.current_chapter, 2, ten)
                self.assertEqual(lai.total_chapters, 5, ten)
                self.assertEqual(lai.current_chapter_done_segments, 3, ten)
                self.assertEqual(lai.attempts, 1, ten)

    def test_owned_job_tu_choi_nguoi_khong_so_huu(self):
        from server.adapters import PermissionDenied

        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                j = TranslationJob(project_id="trp_x", owner_id="u1",
                                   created_at="2026-08-14T00:00:00+00:00")
                kho.create_job(j)
                with self.assertRaises(PermissionDenied):
                    kho.owned_job(j.job_id, "u2")

    def test_active_job_bo_qua_job_da_ket_thuc(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                xong = TranslationJob(project_id="trp_x", owner_id="u1",
                                      status=TranslationJobStatus.COMPLETED,
                                      created_at="2026-08-14T00:00:00+00:00")
                kho.create_job(xong)
                self.assertIsNone(kho.active_job_for_project("trp_x"), ten)

                dang_chay = TranslationJob(
                    project_id="trp_x", owner_id="u1",
                    status=TranslationJobStatus.TRANSLATING,
                    created_at="2026-08-14T00:01:00+00:00")
                kho.create_job(dang_chay)
                active = kho.active_job_for_project("trp_x")
                self.assertIsNotNone(active, ten)
                self.assertEqual(active.job_id, dang_chay.job_id, ten)

    def test_jobs_for_project_sap_MOI_NHAT_TRUOC(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i, moc in enumerate(["2026-08-01T00:00:00+00:00",
                                         "2026-08-03T00:00:00+00:00"]):
                    kho.create_job(TranslationJob(
                        project_id="trp_x", owner_id="u1", created_at=moc))
                ds = kho.jobs_for_project("trp_x")
                self.assertEqual(len(ds), 2, ten)
                self.assertEqual(ds[0].created_at,
                                 "2026-08-03T00:00:00+00:00", ten)

    def test_job_moi_tao_chua_lease_giu_rong_khong_bi_dien_gio_hien_tai(self):
        """
        Hoi quy TU dot Appwrite optional-datetime audit: `_job_to_row` tung
        gui thang `j.lease_expires_at`/`j.waiting_retry_at`/`j.finished_at`
        (mac dinh "") len Appwrite — Appwrite (tu luu tru) tu dien gio server
        HIEN TAI cho thuoc tinh datetime khong bat buoc khi nhan chuoi rong,
        thay vi null. `FakeAppwrite` KHONG mo phong duoc tat nay (chi phat
        hien qua smoke test that), nen bai nay kiem THANG payload
        `_job_to_row` sinh ra thay vi round-trip.
        """
        from server.appwrite_translation_store import _job_to_row

        j = TranslationJob(project_id="trp_x", owner_id="u1",
                           created_at="2026-08-14T00:00:00+00:00")
        row = _job_to_row(j)
        self.assertIsNone(row["lease_expires_at"])
        self.assertIsNone(row["waiting_retry_at"])
        self.assertIsNone(row["finished_at"])

    def test_job_da_co_lease_that_van_giu_nguyen_qua_writable(self):
        from server.appwrite_translation_store import _job_to_row

        j = TranslationJob(
            project_id="trp_x", owner_id="u1",
            lease_expires_at="2026-08-14T01:00:00+00:00",
            finished_at="2026-08-14T02:00:00+00:00",
            created_at="2026-08-14T00:00:00+00:00")
        row = _job_to_row(j)
        self.assertEqual(row["lease_expires_at"], "2026-08-14T01:00:00+00:00")
        self.assertEqual(row["finished_at"], "2026-08-14T02:00:00+00:00")
        self.assertIsNone(row["waiting_retry_at"])

    def test_job_moi_tao_round_trip_ca_hai_kho_giu_truong_lease_rong(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                j = TranslationJob(project_id="trp_x", owner_id="u1",
                                   created_at="2026-08-14T00:00:00+00:00")
                kho.create_job(j)
                lai = kho.get_job(j.job_id)
                self.assertEqual(lai.lease_expires_at, "", ten)
                self.assertEqual(lai.waiting_retry_at, "", ten)
                self.assertEqual(lai.finished_at, "", ten)

    def test_count_jobs_loc_theo_status_va_ngay_phase7(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.create_job(TranslationJob(
                    project_id="trp_x", owner_id="u1",
                    status=TranslationJobStatus.COMPLETED,
                    created_at="2026-01-01T00:00:00+00:00"))
                kho.create_job(TranslationJob(
                    project_id="trp_x", owner_id="u1",
                    status=TranslationJobStatus.FAILED,
                    created_at="2026-08-16T00:00:00+00:00"))
                self.assertEqual(
                    kho.count_jobs(status=TranslationJobStatus.COMPLETED), 1, ten)
                self.assertEqual(
                    kho.count_jobs(status=TranslationJobStatus.FAILED), 1, ten)
                self.assertEqual(
                    kho.count_jobs(created_after="2026-08-01T00:00:00+00:00"), 1, ten)
                self.assertEqual(kho.count_jobs(), 2, ten)

    # ===================================================== GLOSSARY

    def test_them_va_doc_lai_thuat_ngu_giu_nguyen_alias(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                e = GlossaryEntry(
                    term_id="gls_tieu_viem", project_id="trp_x",
                    category=GlossaryCategory.CHARACTER,
                    original="萧炎", translated="Tiêu Viêm",
                    aliases=["Viêm Nhi", "Tiểu Viêm"],
                    note="Nhân vật chính.", locked=True,
                    created_at="2026-08-14T00:00:00+00:00")
                kho.add_glossary_entry(e)
                lai = kho.get_glossary_entry("trp_x", e.term_id)
                self.assertEqual(lai.original, "萧炎", ten)
                self.assertEqual(lai.translated, "Tiêu Viêm", ten)
                self.assertIs(lai.category, GlossaryCategory.CHARACTER, ten)
                self.assertEqual(lai.aliases, ["Viêm Nhi", "Tiểu Viêm"], ten)
                self.assertTrue(lai.locked, ten)

    def test_get_glossary_entry_sai_project_id_nem_NotFoundError(self):
        from server.adapters import NotFoundError

        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                e = GlossaryEntry(term_id="gls_a", project_id="trp_x",
                                  category=GlossaryCategory.OTHER,
                                  original="x", translated="y",
                                  created_at="2026-08-14T00:00:00+00:00")
                kho.add_glossary_entry(e)
                with self.assertRaises(NotFoundError):
                    kho.get_glossary_entry("trp_KHAC", e.term_id)

    def test_save_glossary_entry_cap_nhat_tai_cho(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                e = GlossaryEntry(term_id="gls_b", project_id="trp_x",
                                  category=GlossaryCategory.OTHER,
                                  original="x", translated="y",
                                  locked=False,
                                  created_at="2026-08-14T00:00:00+00:00")
                kho.add_glossary_entry(e)
                e.locked = True
                e.translated = "y2"
                kho.save_glossary_entry(e)
                lai = kho.get_glossary_entry("trp_x", e.term_id)
                self.assertTrue(lai.locked, ten)
                self.assertEqual(lai.translated, "y2", ten)

    def test_delete_glossary_entry_xoa_that_va_idempotent(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                e = GlossaryEntry(term_id="gls_c", project_id="trp_x",
                                  category=GlossaryCategory.OTHER,
                                  original="x", translated="y",
                                  created_at="2026-08-14T00:00:00+00:00")
                kho.add_glossary_entry(e)
                kho.delete_glossary_entry("trp_x", e.term_id)
                self.assertEqual(kho.list_glossary("trp_x"), [], ten)
                # Xoa lan hai — KHONG duoc nem loi (idempotent).
                kho.delete_glossary_entry("trp_x", e.term_id)

    def test_list_glossary_chi_cua_dung_du_an_sap_theo_original(self):
        goc = ["乙", "甲"]
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i, orig in enumerate(goc):
                    kho.add_glossary_entry(GlossaryEntry(
                        term_id=f"gls_a{i}", project_id="trp_A",
                        category=GlossaryCategory.OTHER,
                        original=orig, translated=orig,
                        created_at="2026-08-14T00:00:00+00:00"))
                kho.add_glossary_entry(GlossaryEntry(
                    term_id="gls_b0", project_id="trp_B",
                    category=GlossaryCategory.OTHER,
                    original="丙", translated="丙",
                    created_at="2026-08-14T00:00:00+00:00"))
                ds = kho.list_glossary("trp_A")
                self.assertEqual([e.original for e in ds], sorted(goc), ten)
                self.assertEqual(len(kho.list_glossary("trp_B")), 1, ten)

    # ===================================================== PROVIDER CONNECTION (BYOK)

    def test_ket_noi_moi_round_trip_ca_hai_kho(self):
        from server.translation_domain import ProviderConnection

        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                c = ProviderConnection(
                    user_id="u1", provider_id="groq",
                    encrypted_secret="byok.v1.a.b", last4="AB42",
                    status="available", selected_model="m1",
                    created_at="2026-08-14T00:00:00+00:00",
                    updated_at="2026-08-14T00:00:00+00:00",
                    last_verified_at="2026-08-14T00:00:00+00:00")
                kho.save_connection(c)
                lai = kho.get_connection("u1", "groq")
                self.assertEqual(lai.last4, "AB42", ten)
                self.assertEqual(lai.last_verified_at,
                                 "2026-08-14T00:00:00+00:00", ten)

    def test_ket_noi_chua_xac_minh_khong_bi_dien_gio_hien_tai(self):
        """
        Hoi quy TU dot Appwrite optional-datetime audit: `_connection_to_row`
        tung gui thang `c.last_verified_at` (mac dinh "") — trong THUC TE
        `TranslationByokService.connect()` luon xac minh key TRUOC khi tao
        ket noi nen truong nay chua tung rong o duong that, nhung sua phong
        thu cho MOI duong tao khac trong tuong lai. `FakeAppwrite` khong mo
        phong duoc tat Appwrite (chi phat hien qua smoke test that), nen bai
        nay kiem THANG payload `_connection_to_row` sinh ra.
        """
        from server.appwrite_translation_store import _connection_to_row
        from server.translation_domain import ProviderConnection

        c = ProviderConnection(
            user_id="u1", provider_id="groq",
            encrypted_secret="byok.v1.a.b", last4="AB42",
            created_at="2026-08-14T00:00:00+00:00",
            updated_at="2026-08-14T00:00:00+00:00")
        row = _connection_to_row(c)
        self.assertIsNone(row["last_verified_at"])

    def test_count_connections_by_status_phase7(self):
        from server.translation_domain import ProviderConnection

        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.save_connection(ProviderConnection(
                    user_id="u1", provider_id="groq",
                    encrypted_secret="byok.v1.a.b", last4="AB42",
                    status="available"))
                kho.save_connection(ProviderConnection(
                    user_id="u2", provider_id="groq",
                    encrypted_secret="byok.v1.c.d", last4="CD99",
                    status="quota_exhausted"))
                dem = kho.count_connections_by_status()
                self.assertEqual(dem.get("available", 0), 1, ten)
                self.assertEqual(dem.get("quota_exhausted", 0), 1, ten)
                self.assertNotIn("encrypted_secret", str(dem), ten)

    # ===================================================== XOA DU AN (P2)

    def test_delete_project_xoa_ca_job_thuat_ngu_lich_su(self):
        """Phat hien qua E2E chung thuc R1 (2026-08-21): khong co duong nao
        xoa du an dich — mot du an QA bi mo coi trong production that. Xoa
        phai don sach CA job/thuat ngu/lich su phien ban, khong chi bang
        du an."""
        from server.adapters import NotFoundError
        from server.translation_domain import TranslationVersion

        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                p = TranslationProject(owner_id="u1", title="x",
                                       source_text="một câu.",
                                       created_at="2026-08-14T00:00:00+00:00")
                kho.create_project(p)
                kho.create_job(TranslationJob(project_id=p.project_id, owner_id="u1"))
                kho.add_glossary_entry(GlossaryEntry(
                    term_id="gls_test1", project_id=p.project_id,
                    category=GlossaryCategory.CHARACTER,
                    original="萧炎", translated="Tiêu Viêm"))
                kho.add_version(TranslationVersion(
                    project_id=p.project_id, chapter_index=0,
                    operation="auto_translate", pass_type="translator",
                    previous_text="", new_text="Tiêu Viêm."))

                kho.delete_project(p.project_id)

                with self.assertRaises(NotFoundError, msg=ten):
                    kho.get_project(p.project_id)
                self.assertEqual(kho.jobs_for_project(p.project_id), [], ten)
                self.assertEqual(kho.list_glossary(p.project_id), [], ten)
                self.assertEqual(kho.list_versions(p.project_id), [], ten)

    def test_delete_project_khong_anh_huong_du_an_khac(self):
        """Xoa du an A khong duoc dung tay vao du an B — kiem CA job, thuat
        ngu, VA lich su phien ban (khong chi job/tieu de nhu ban dau)."""
        from server.translation_domain import TranslationVersion

        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                p1 = TranslationProject(owner_id="u1", title="x",
                                        source_text="một câu.",
                                        created_at="2026-08-14T00:00:00+00:00")
                p2 = TranslationProject(owner_id="u1", title="y",
                                        source_text="câu khác.",
                                        created_at="2026-08-14T00:00:00+00:00")
                kho.create_project(p1)
                kho.create_project(p2)
                kho.create_job(TranslationJob(project_id=p2.project_id, owner_id="u1"))
                kho.add_glossary_entry(GlossaryEntry(
                    term_id="gls_p2", project_id=p2.project_id,
                    category=GlossaryCategory.CHARACTER,
                    original="药老", translated="Dược Lão"))
                kho.add_version(TranslationVersion(
                    project_id=p2.project_id, chapter_index=0,
                    operation="auto_translate", pass_type="translator",
                    previous_text="", new_text="Dược Lão."))

                kho.delete_project(p1.project_id)

                self.assertEqual(kho.get_project(p2.project_id).title, "y", ten)
                self.assertEqual(len(kho.jobs_for_project(p2.project_id)), 1, ten)
                self.assertEqual(len(kho.list_glossary(p2.project_id)), 1, ten)
                self.assertEqual(len(kho.list_versions(p2.project_id)), 1, ten)


if __name__ == "__main__":
    unittest.main(verbosity=2)
