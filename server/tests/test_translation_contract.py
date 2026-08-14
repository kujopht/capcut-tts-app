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


if __name__ == "__main__":
    unittest.main(verbosity=2)
