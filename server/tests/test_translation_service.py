"""
Tang dich vu — `server/translation_service.py`. Chay tren kho MOCK va
`MockTranslationProvider` (khong goi mang).
"""

from __future__ import annotations

import threading
import time
import unittest

from server.adapters import (
    MockIdentityAdapter,
    MockMetadataStore,
    NotFoundError,
    PermissionDenied,
)
from server.translation import (
    TERMINAL_STATUSES,
    QuotaExceeded,
    TranslationError,
    TranslationJobStatus,
)
from server.translation_providers import (
    MockTranslationProvider,
    TranslationProviderError,
)
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


def cho_job_xong(svc, job_id, owner_id, timeout=5.0):
    """
    Cho job chay xong (`create_job`/`retry_job` TRA VE NGAY, khong con chay
    dong bo trong request — xem Part K). Voi `MockTranslationProvider` (khong
    do tre mang), thread nen thuong xong trong vai mili-giay; deadline 5s chi
    de bat that su treo (bug), khong phai do tre binh thuong.

    Dung y voi idiom cua `test_worker_split.py` (TTS): poll trang thai qua
    chinh giao dien cong khai, KHONG cham vao noi bo thread.
    """
    han = time.time() + timeout
    while time.time() < han:
        job = svc.get_job(job_id, owner_id)
        if job.status in TERMINAL_STATUSES:
            return job
        time.sleep(0.005)
    raise AssertionError(f"job {job_id} không xong sau {timeout}s")


class Nen(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.novels = MockMetadataStore()
        self.store = MockTranslationStore()
        self.svc = TranslationService(self.store, self.novels)
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")
        self.binh = self.identity.register("binh@vidu.vn", "MatKhau123", "Bình")

    def _cho_xong(self, job_id, owner_id=None, timeout=5.0):
        return cho_job_xong(self.svc, job_id, owner_id or self.an.user_id,
                            timeout=timeout)


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

    def test_tao_job_tra_ve_NGAY_o_trang_thai_queued(self):
        """
        Part K: `POST .../jobs` KHONG duoc chay ca chuong trong request —
        `create_job()` phai tra ve object o dung trang thai `queued` MA NO
        duoc tao ra (`_start_job_thread` chi doc bien `vua_tao` da chup SAN,
        khong doi cho thread chay). `stop_accepting_new_jobs()` o day chi la
        cach kiem CHAC CHAN khong co race voi thread nen cuc nhanh cua mock —
        gia tri tra ve khong phu thuoc gi vao co cho thread chay hay khong,
        nen day la mot phep kiem dung dan bat ke co bat worker hay khong.
        """
        self.svc.stop_accepting_new_jobs()
        job = self.svc.create_job(self.p.project_id, self.an.user_id)
        self.assertEqual(job.status, TranslationJobStatus.QUEUED)
        self.assertFalse(job.finished_at)
        self.assertEqual(job.total_chapters, 2)

    def test_tao_job_chay_toi_completed_voi_mock(self):
        job = self.svc.create_job(self.p.project_id, self.an.user_id)
        job = self._cho_xong(job.job_id)
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
        job = self.svc.create_job(self.p.project_id, self.an.user_id)
        self._cho_xong(job.job_id)
        p = self.svc.get_project(self.p.project_id, self.an.user_id)
        self.assertEqual(len(p.translated_chapters), 2)
        self.assertTrue(p.translated_chapters[0].startswith("[MOCK-VI]"))
        self.assertIn("萧炎看向药老", p.translated_chapters[0])
        self.assertIn("他继续前进", p.translated_chapters[1])

    def test_goi_lai_khi_dang_hoat_dong_tra_ve_CUNG_job(self):
        """
        IDEMPOTENT — mo phong F5: goi `create_job` lan hai trong khi job dau
        VAN CON hoat dong (chua ket thuc) KHONG duoc tao job thu hai.

        `stop_accepting_new_jobs()` giu job o `queued` MAI MAI (khong thread
        nao nhan) — deterministic, khong phai dua vao thoi diem may man truoc
        khi thread nen (rat nhanh voi mock) kip chay xong.
        """
        self.svc.stop_accepting_new_jobs()
        j1 = self.svc.create_job(self.p.project_id, self.an.user_id)
        self.assertEqual(j1.status, TranslationJobStatus.QUEUED)
        j2 = self.svc.create_job(self.p.project_id, self.an.user_id)
        self.assertEqual(j1.job_id, j2.job_id)
        self.assertEqual(
            len(self.store.jobs_for_project(self.p.project_id)), 1)

    def test_khong_so_huu_khong_tao_duoc_job(self):
        with self.assertRaises(PermissionDenied):
            self.svc.create_job(self.p.project_id, self.binh.user_id)

    def test_qua_tran_job_dong_thoi_bi_chan(self):
        # `stop_accepting_new_jobs()`: moi job tao ra deu nam nguyen o
        # `queued` — deterministic, khong dua vao viec "chua kip chay xong".
        self.svc.stop_accepting_new_jobs()
        for i in range(MAX_CONCURRENT_JOBS_PER_USER):
            p = self.svc.create_project(self.an.user_id, title=f"p{i}",
                                        source_text="một đoạn.")
            self.svc.create_job(p.project_id, self.an.user_id)
        p_moi = self.svc.create_project(self.an.user_id, title="thêm",
                                        source_text="một đoạn khác.")
        with self.assertRaises(QuotaExceeded):
            self.svc.create_job(p_moi.project_id, self.an.user_id)

    def test_huy_job_da_xong_khong_loi_idempotent(self):
        job = self.svc.create_job(self.p.project_id, self.an.user_id)
        job = self._cho_xong(job.job_id)
        self.assertEqual(job.status, TranslationJobStatus.COMPLETED)
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
        job = self.svc.create_job(p.project_id, self.an.user_id)
        cho_job_xong(self.svc, job.job_id, self.an.user_id)
        return list(self.provider.lich_su_vai_tro)

    def test_nhanh_chi_dich_mot_luot(self):
        self.assertEqual(self._chay("nhanh"), ["translator"])

    def test_can_bang_dich_roi_qa_khong_bien_tap_rieng(self):
        self.assertEqual(self._chay("can_bang"), ["translator", "qa"])

    def test_van_hoc_du_ba_pass_dung_thu_tu(self):
        self.assertEqual(self._chay("van_hoc"),
                         ["translator", "editor", "qa"])


class _LoiOLanGoi(MockTranslationProvider):
    """Spy: nem `TranslationProviderError` o dung LAN GOI thu N (dem TU 1,
    tren TOAN BO doi tuong — ke ca qua nhieu job/nhieu lan retry), con lai uy
    thac cho Mock. Dung de gia lap "worker chet giua chuong K" mot cach
    DETERMINISTIC, khong dua vao do tre thoi gian."""

    def __init__(self, that_bai_o_lan: int):
        self._that_bai_o_lan = that_bai_o_lan
        self.so_lan_goi = 0

    def translate_segment(self, text, *, context):
        self.so_lan_goi += 1
        if self.so_lan_goi == self._that_bai_o_lan:
            raise TranslationProviderError("Lỗi giả lập để kiểm thử retry.")
        return super().translate_segment(text, context=context)


VB_BA_CHUONG_MOI_CHUONG_MOT_CAU = (
    "第1章 Một\n甲。\n第2章 Hai\n乙。\n第3章 Ba\n丙。"
)


class KhongCoCompletedGiaGiuaTruyenTest(unittest.TestCase):
    """
    Rao chan hoi quy CU THE cho mot loi THAT tim thay qua
    `test_translation_job_recovery.py`: may trang thai CUA RIENG MOT CHUONG
    dung CHUNG gia tri enum `TranslationJobStatus.COMPLETED` voi may trang
    thai CUA CA JOB — buoc chuyen "pipeline chuong nay xong" tung ghi thang
    `job.status = COMPLETED` vao kho, du con nhieu chuong nua chua dich. Mot
    lan poll dung luc do se thay `status=completed, progress=100` cho mot
    job moi xong CHUONG DAU trong mot tieu thuyet 5 chuong — mot loi that
    nghiem trong cho giao dien chi doc trang thai qua polling.
    """

    def test_completed_chi_xuat_hien_dung_mot_lan_o_cuoi(self):
        identity = MockIdentityAdapter()
        novels = MockMetadataStore()
        store = MockTranslationStore()
        svc = TranslationService(store, novels)
        an = identity.register("an@vidu.vn", "MatKhau123", "An")

        van_ban = "\n".join(f"第{i}章 X\n{'甲'*i}。" for i in range(1, 6))
        p = svc.create_project(an.user_id, title="x", source_text=van_ban,
                               quality_mode="nhanh")

        lan_thay_completed = []

        goc = store.save_job_fenced

        def theo_doi(j, fence, worker_id):
            ok = goc(j, fence, worker_id)
            if ok and j.status is TranslationJobStatus.COMPLETED:
                lan_thay_completed.append(j.current_chapter)
            return ok

        store.save_job_fenced = theo_doi
        try:
            job = svc.create_job(p.project_id, an.user_id)
            cho_job_xong(svc, job.job_id, an.user_id)
        finally:
            store.save_job_fenced = goc

        self.assertEqual(
            len(lan_thay_completed), 1,
            f"COMPLETED bị ghi xuống kho {len(lan_thay_completed)} lần, "
            "phải đúng MỘT lần duy nhất ở cuối")
        self.assertEqual(
            lan_thay_completed[0], 5,
            "lần COMPLETED duy nhất phải ở đúng chương cuối (5), không phải "
            "giữa truyện")


class RetryJobTest(unittest.TestCase):
    """
    Part K — "retry một chương đã thất bại". Trong một pipeline TUẦN TỰ,
    chương "thất bại" LUÔN là chương đầu tiên CHƯA nằm trong
    `translated_chapters` (không có trường hợp chương N lỗi mà N+1 đã xong) —
    nên retry và resume LÀ CÙNG MỘT hành động, xem
    `TranslationService.retry_job`.
    """

    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.novels = MockMetadataStore()
        self.store = MockTranslationStore()
        # Che do NHANH + moi chuong dung MOT cau ngan -> DUNG MOT lan goi
        # provider cho MOI chuong, nen dem lan goi = dem chuong, deterministic
        # tuyet doi (khong phu thuoc do dai doan van).
        self.provider = _LoiOLanGoi(that_bai_o_lan=2)
        self.svc = TranslationService(self.store, self.novels,
                                      provider=self.provider)
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")

    def test_retry_tiep_tuc_dung_cho_khong_dich_lai_chuong_da_xong(self):
        p = self.svc.create_project(
            self.an.user_id, title="x",
            source_text=VB_BA_CHUONG_MOI_CHUONG_MOT_CAU, quality_mode="nhanh")
        job = self.svc.create_job(p.project_id, self.an.user_id)
        job = cho_job_xong(self.svc, job.job_id, self.an.user_id)

        self.assertEqual(job.status, TranslationJobStatus.FAILED)
        self.assertTrue(job.error)
        p_sau_loi = self.svc.get_project(p.project_id, self.an.user_id)
        self.assertEqual(len(p_sau_loi.translated_chapters), 1,
                         "chỉ chương 1 phải xong trước khi chương 2 thất bại")

        job2 = self.svc.retry_job(job.job_id, self.an.user_id)
        self.assertEqual(job2.job_id, job.job_id,
                         "retry la CUNG mot job, khong tao job moi")
        job2 = cho_job_xong(self.svc, job2.job_id, self.an.user_id)

        self.assertEqual(job2.status, TranslationJobStatus.COMPLETED)
        p_cuoi = self.svc.get_project(p.project_id, self.an.user_id)
        self.assertEqual(len(p_cuoi.translated_chapters), 3,
                         "phai co DU 3 chuong sau khi retry xong")
        # 4 lan goi TONG CONG (chuong1, chuong2-that-bai, chuong2-retry,
        # chuong3) — NEU la 5 thi tuc la chuong 1 bi dich lai oan.
        self.assertEqual(self.provider.so_lan_goi, 4)

    def test_retry_job_chua_that_bai_bi_tu_choi(self):
        p = self.svc.create_project(
            self.an.user_id, title="x", source_text="một câu.",
            quality_mode="nhanh")
        job = self.svc.create_job(p.project_id, self.an.user_id)
        job = cho_job_xong(self.svc, job.job_id, self.an.user_id)
        self.assertEqual(job.status, TranslationJobStatus.COMPLETED)
        with self.assertRaises(TranslationError):
            self.svc.retry_job(job.job_id, self.an.user_id)


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
        job = self.svc.create_job(p.project_id, self.an.user_id)
        self._cho_xong(job.job_id)
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
        job = self.svc.create_job(self.p.project_id, self.an.user_id)
        self._cho_xong(job.job_id)

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


class _ChanODiemDinh(MockTranslationProvider):
    """
    Spy: DUNG LAI (block that su tren mot `threading.Event`) o dung lan goi
    thu N, cho toi khi test cho phep tiep tuc. Dung de kiem "huy giua cac
    pass/chuong" MOT CACH DETERMINISTIC — khong dua vao may man ve tocdo,
    thread nen chay THAT SU dung o giua chuong cho toi khi test bam Huy VA
    chu dong tha no ra.
    """

    def __init__(self, dung_o_lan: int):
        self._dung_o_lan = dung_o_lan
        self.so_lan_goi = 0
        self.da_toi_diem_dung = threading.Event()
        self.duoc_tiep_tuc = threading.Event()

    def translate_segment(self, text, *, context):
        self.so_lan_goi += 1
        if self.so_lan_goi == self._dung_o_lan:
            self.da_toi_diem_dung.set()
            self.duoc_tiep_tuc.wait(timeout=5)
        return super().translate_segment(text, context=context)


class CancelGiuaChungTest(unittest.TestCase):
    """Part K/M: "test cancellation between passes" — huy PHAI co hieu luc
    truoc khi chuong DANG DICH duoc luu vao `translated_chapters`, du provider
    van hoan tat LUOT GOI dang block (khong the ngat ngang mot cuoc goi mang
    dang cho, chi dam bao KET QUA cua no bi bo di dung luc)."""

    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.novels = MockMetadataStore()
        self.store = MockTranslationStore()
        # Dung o lan goi thu 2 — dung luc dang dich CHUONG 2 (che do NHANH +
        # moi chuong mot cau -> 1 lan goi/chuong, dem lan goi = dem chuong).
        self.provider = _ChanODiemDinh(dung_o_lan=2)
        self.svc = TranslationService(self.store, self.novels,
                                      provider=self.provider)
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")

    def test_huy_giua_chuong_khong_luu_chuong_dang_dich(self):
        p = self.svc.create_project(
            self.an.user_id, title="x",
            source_text=VB_BA_CHUONG_MOI_CHUONG_MOT_CAU, quality_mode="nhanh")
        job = self.svc.create_job(p.project_id, self.an.user_id)

        # Cho toi khi thread nen THAT SU dang o giua chuong 2 (khong doan mo).
        self.assertTrue(self.provider.da_toi_diem_dung.wait(timeout=5),
                        "provider không tới điểm dừng kịp trong 5s")
        self.svc.cancel_job(job.job_id, self.an.user_id)
        self.provider.duoc_tiep_tuc.set()  # tha luot goi dang block ra

        job2 = cho_job_xong(self.svc, job.job_id, self.an.user_id)
        self.assertEqual(job2.status, TranslationJobStatus.CANCELLED)

        p2 = self.svc.get_project(p.project_id, self.an.user_id)
        self.assertEqual(len(p2.translated_chapters), 1,
                         "chương 2 (đang dịch lúc huỷ) không được lưu")


if __name__ == "__main__":
    unittest.main(verbosity=2)
