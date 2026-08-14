"""
Tang dich vu — `server/translation_service.py`. Chay tren kho MOCK va
`MockTranslationProvider` (khong goi mang).
"""

from __future__ import annotations

import unittest

from server.adapters import (
    MockIdentityAdapter,
    MockMetadataStore,
    NotFoundError,
    PermissionDenied,
)
from server.translation import QuotaExceeded, TranslationError, TranslationJobStatus
from server.translation_providers import MockTranslationProvider
from server.translation_service import (
    MAX_CHAPTERS_PER_PROJECT,
    MAX_CHARS_PER_PROJECT,
    MAX_CONCURRENT_JOBS_PER_USER,
    TranslationService,
)
from server.translation_store import MockTranslationStore

VB_HAI_CHUONG = (
    "第1章 Khởi đầu\n萧炎看向药老。\n第2章 Tiếp theo\n他继续前进。"
)


class Nen(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.novels = MockMetadataStore()
        self.store = MockTranslationStore()
        self.svc = TranslationService(self.store, self.novels)
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")
        self.binh = self.identity.register("binh@vidu.vn", "MatKhau123", "Bình")


class TaoDuAnTest(Nen):
    def test_tao_du_an_hop_le(self):
        p = self.svc.create_project(self.an.user_id, title="Đấu Phá",
                                    source_text=VB_HAI_CHUONG)
        self.assertEqual(p.owner_id, self.an.user_id)
        self.assertEqual(p.to_dict()["chapter_count"], 2)

    def test_thieu_noi_dung_bi_tu_choi(self):
        with self.assertRaises(TranslationError):
            self.svc.create_project(self.an.user_id, title="x", source_text="   ")

    def test_vuot_tran_ky_tu_bi_tu_choi(self):
        with self.assertRaises(QuotaExceeded):
            self.svc.create_project(
                self.an.user_id, title="x",
                source_text="x" * (MAX_CHARS_PER_PROJECT + 1))

    def test_tieu_de_rong_co_ten_du_phong(self):
        p = self.svc.create_project(self.an.user_id, title="  ",
                                    source_text="một đoạn.")
        self.assertTrue(p.title)

    def test_khong_so_huu_khong_doc_duoc_du_an_nguoi_khac(self):
        p = self.svc.create_project(self.an.user_id, title="x",
                                    source_text="một đoạn.")
        with self.assertRaises(PermissionDenied):
            self.svc.get_project(p.project_id, self.binh.user_id)

    def test_du_an_khong_ton_tai_tra_404(self):
        with self.assertRaises(NotFoundError):
            self.svc.get_project("khong-ton-tai", self.an.user_id)


class JobTest(Nen):
    def setUp(self) -> None:
        super().setUp()
        self.p = self.svc.create_project(self.an.user_id, title="Đấu Phá",
                                         source_text=VB_HAI_CHUONG)

    def test_tao_job_chay_toi_completed_voi_mock(self):
        job = self.svc.create_job(self.p.project_id, self.an.user_id)
        self.assertEqual(job.status, TranslationJobStatus.COMPLETED)
        self.assertEqual(job.total_chapters, 2)
        self.assertEqual(job.progress_percent(), 100)
        self.assertTrue(job.finished_at)

    def test_ban_dich_di_qua_provider_that_su(self):
        """
        Chuong o day gom CA dong tieu de ("第1章 Khởi đầu") + cau, nen doan
        gui cho provider KHONG khop chinh xac muc tu dien cung cua mock (xem
        `test_translation_providers.py` cho bai kiem tu dien cung do lap).
        O day chi kiem: ket qua CO di qua provider that (danh dau [MOCK-VI]),
        khong phai van ban Trung nguyen ven khong xu ly gi.
        """
        self.svc.create_job(self.p.project_id, self.an.user_id)
        p = self.svc.get_project(self.p.project_id, self.an.user_id)
        self.assertEqual(len(p.translated_chapters), 2)
        self.assertTrue(p.translated_chapters[0].startswith("[MOCK-VI]"))
        self.assertIn("萧炎看向药老", p.translated_chapters[0])
        self.assertIn("他继续前进", p.translated_chapters[1])

    def test_goi_lai_khi_dang_hoat_dong_tra_ve_CUNG_job(self):
        """
        IDEMPOTENT — mo phong F5: goi `create_job` lan hai KHONG duoc tao
        job thu hai. Voi mock (chay xong ngay) can kiem tra o muc service
        thap hon: goi active_job_for_project TRUOC khi job ket thuc.
        """
        from unittest.mock import patch

        goc = self.svc._chay_toi_khi_xong
        job_dau = []

        def cham(job, project):
            job_dau.append(job.job_id)
            return goc(job, project)

        with patch.object(self.svc, "_chay_toi_khi_xong", side_effect=cham):
            j1 = self.svc.create_job(self.p.project_id, self.an.user_id)
        # Gia lap: job van "active" (chua ket thuc), goi lai phai tra CUNG id.
        self.store._jobs[j1.job_id].status = TranslationJobStatus.TRANSLATING
        j2 = self.svc.create_job(self.p.project_id, self.an.user_id)
        self.assertEqual(j1.job_id, j2.job_id)
        self.assertEqual(len(job_dau), 1)

    def test_khong_so_huu_khong_tao_duoc_job(self):
        with self.assertRaises(PermissionDenied):
            self.svc.create_job(self.p.project_id, self.binh.user_id)

    def test_qua_tran_job_dong_thoi_bi_chan(self):
        # Tao MAX du an rieng, moi cai giu mot job "dang chay" gia lap bang
        # cach thao tung status ve TRANSLATING sau khi mock da chay xong.
        for i in range(MAX_CONCURRENT_JOBS_PER_USER):
            p = self.svc.create_project(self.an.user_id, title=f"p{i}",
                                        source_text="một đoạn.")
            j = self.svc.create_job(p.project_id, self.an.user_id)
            self.store._jobs[j.job_id].status = TranslationJobStatus.TRANSLATING
        p_moi = self.svc.create_project(self.an.user_id, title="thêm",
                                        source_text="một đoạn khác.")
        with self.assertRaises(QuotaExceeded):
            self.svc.create_job(p_moi.project_id, self.an.user_id)

    def test_huy_job_da_xong_khong_loi_idempotent(self):
        job = self.svc.create_job(self.p.project_id, self.an.user_id)
        ra = self.svc.cancel_job(job.job_id, self.an.user_id)
        self.assertEqual(ra.status, TranslationJobStatus.COMPLETED)  # khong doi


class _GhiVaiTro(MockTranslationProvider):
    """Spy tren mock — ghi lai DUNG THU TU `vai_tro` da goi cho MOI doan, de
    kiem 3-pass THAT (khong chi may trang thai job) chay dung so luot theo
    che do chat luong. Ke thua Mock nen van tra ve hanh vi tat dinh, khong
    goi mang — chi them mot danh sach ghi am."""

    def __init__(self):
        self.lich_su_vai_tro: list = []

    def translate_segment(self, text, *, context):
        self.lich_su_vai_tro.append(context.vai_tro)
        return super().translate_segment(text, context=context)


class BaPassTest(unittest.TestCase):
    """
    Rao chan hoi quy CU THE cho lo hong da tim thay: may trang thai job DI
    QUA du buoc reviewing/qa cho CAN_BANG/VAN_HOC, nhung truoc day
    `_dich_mot_chuong` chi bao gio goi provider VOI `vai_tro="translator"` —
    cac buoc do chi la NHAN, khong that su goi bien tap/QA. Da sua trong
    `TranslationService._dich_mot_chuong` (xem `_VAI_TRO_THEO_CHE_DO`).
    """

    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.novels = MockMetadataStore()
        self.store = MockTranslationStore()
        self.provider = _GhiVaiTro()
        self.svc = TranslationService(self.store, self.novels,
                                      provider=self.provider)
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")

    def _chay(self, quality_mode: str) -> list:
        p = self.svc.create_project(
            self.an.user_id, title="x", source_text="một câu duy nhất.",
            quality_mode=quality_mode)
        self.svc.create_job(p.project_id, self.an.user_id)
        return list(self.provider.lich_su_vai_tro)

    def test_nhanh_chi_dich_mot_luot(self):
        self.assertEqual(self._chay("nhanh"), ["translator"])

    def test_can_bang_dich_roi_qa_khong_bien_tap_rieng(self):
        self.assertEqual(self._chay("can_bang"), ["translator", "qa"])

    def test_van_hoc_du_ba_pass_dung_thu_tu(self):
        self.assertEqual(self._chay("van_hoc"),
                         ["translator", "editor", "qa"])


class GlossaryTest(Nen):
    def setUp(self) -> None:
        super().setUp()
        self.p = self.svc.create_project(self.an.user_id, title="x",
                                         source_text="một đoạn.")

    def test_them_va_doc_lai_thuat_ngu(self):
        e = self.svc.add_glossary_entry(
            self.p.project_id, self.an.user_id, category="character",
            original="萧炎", translated="Tiêu Viêm")
        ds = self.svc.list_glossary(self.p.project_id, self.an.user_id)
        self.assertEqual([x.term_id for x in ds], [e.term_id])

    def test_khoa_roi_khong_xoa_duoc(self):
        e = self.svc.add_glossary_entry(
            self.p.project_id, self.an.user_id, category="character",
            original="萧炎", translated="Tiêu Viêm")
        self.svc.update_glossary_entry(self.p.project_id, self.an.user_id,
                                       e.term_id, locked=True)
        with self.assertRaises(TranslationError):
            self.svc.delete_glossary_entry(self.p.project_id, self.an.user_id,
                                           e.term_id)

    def test_mo_khoa_roi_xoa_duoc(self):
        e = self.svc.add_glossary_entry(
            self.p.project_id, self.an.user_id, category="character",
            original="萧炎", translated="Tiêu Viêm")
        self.svc.update_glossary_entry(self.p.project_id, self.an.user_id,
                                       e.term_id, locked=True)
        self.svc.update_glossary_entry(self.p.project_id, self.an.user_id,
                                       e.term_id, locked=False)
        self.svc.delete_glossary_entry(self.p.project_id, self.an.user_id,
                                       e.term_id)
        self.assertEqual(
            self.svc.list_glossary(self.p.project_id, self.an.user_id), [])

    def test_khoa_thuat_ngu_khong_bi_provider_ghi_de(self):
        """Rao chan cuoi: dich chuong co chua tu da khoa phai dung ban KHOA,
        khong phai de xuat cua (mock) provider."""
        p = self.svc.create_project(
            self.an.user_id, title="x", source_text="第1章 A\n萧炎看向药老。")
        self.svc.add_glossary_entry(
            p.project_id, self.an.user_id, category="character",
            original="萧炎", translated="TÊN_KHOA")
        self.svc.update_glossary_entry(
            p.project_id, self.an.user_id,
            self.svc.list_glossary(p.project_id, self.an.user_id)[0].term_id,
            locked=True)
        self.svc.create_job(p.project_id, self.an.user_id)
        p2 = self.svc.get_project(p.project_id, self.an.user_id)
        # Cau nay khop CHINH XAC trong tu dien mock, tra ve nguyen ban KHONG
        # qua glossary trong provider — nhung rao chan cuoi cua service phai
        # thay the "萧炎" con sot trong ket qua bang gia tri da khoa.
        self.assertNotIn("萧炎", p2.translated_chapters[0])


class NhapVaoTruyenTest(Nen):
    def setUp(self) -> None:
        super().setUp()
        self.p = self.svc.create_project(self.an.user_id, title="Đấu Phá",
                                         source_text=VB_HAI_CHUONG)
        self.svc.create_job(self.p.project_id, self.an.user_id)

    def test_nhap_tao_truyen_moi_kem_du_chuong(self):
        ra = self.svc.import_to_draft(self.p.project_id, self.an.user_id)
        self.assertFalse(ra["already_imported"])
        self.assertEqual(ra["chapters_created"], 2)
        chuong = self.novels.list_chapters(ra["novel_id"])
        self.assertEqual(len(chuong), 2)

    def test_goi_lai_khong_tao_ban_sao(self):
        ra1 = self.svc.import_to_draft(self.p.project_id, self.an.user_id)
        ra2 = self.svc.import_to_draft(self.p.project_id, self.an.user_id)
        self.assertTrue(ra2["already_imported"])
        self.assertEqual(ra2["novel_id"], ra1["novel_id"])
        self.assertEqual(ra2["chapters_created"], 0)
        self.assertEqual(len(self.novels.list_chapters(ra1["novel_id"])), 2)

    def test_chua_dich_xong_chuong_nao_thi_khong_nhap_duoc(self):
        p2 = self.svc.create_project(self.an.user_id, title="chưa dịch",
                                     source_text="một đoạn.")
        with self.assertRaises(TranslationError):
            self.svc.import_to_draft(p2.project_id, self.an.user_id)

    def test_nhap_vao_truyen_da_co_san(self):
        from server.domain import Novel

        novel = self.novels.create_novel(Novel(owner_id=self.an.user_id,
                                               title="Truyện sẵn có"))
        ra = self.svc.import_to_draft(self.p.project_id, self.an.user_id,
                                      novel_id=novel.novel_id)
        self.assertEqual(ra["novel_id"], novel.novel_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
