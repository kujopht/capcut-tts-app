"""
Part M — kiem thu phuc hoi job THAT: mot tieu thuyet 8 chuong, dich VAN_HOC
(3-pass), worker "chet" giua chung, mot instance `TranslationService` MOI
(mo phong tien trinh moi thay the) nhan lai va hoan tat DUNG MOT LAN.

Day la bai kiem TICH HOP — dung THAT `TranslationService`/`MockTranslationStore`
(khong mock tang service), chi mo phong "cai chet cua worker" bang cach:
mot provider CHAN LAI (block that su tren threading.Event) dung o cuoc goi
DAU TIEN cua mot chuong sau, roi tu tay het han lease trong kho — dung y voi
mot worker thuc su bi giet (khong kip don dep gi, lease chi tu troi qua han).
"""

from __future__ import annotations

import threading
import time
import unittest
from dataclasses import replace

from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.translation import GlossaryCategory, TranslationJobStatus
from server.translation_providers import MockTranslationProvider
from server.translation_service import TranslationService
from server.translation_store import MockTranslationStore

#: 8 chuong THAT (Trung van tong hop, khong ban quyen), moi chuong MOT cau
#: ngan -> DUNG MOT DOAN/chuong, nen so lan goi provider = so_chuong * so_pass
#: (van_hoc = 3 pass) — deterministic tuyet doi, khong phu thuoc do dai doan.
TIEU_THUYET_8_CHUONG = "\n".join(
    f"第{i}章 Chương {i}\n{cau}。"
    for i, cau in enumerate(
        ["甲登场", "乙相遇", "丙决斗", "丁离别",
         "戊归来", "己重逢", "庚试炼", "辛终章"],
        start=1,
    )
)

SO_CHUONG = 8
SO_PASS_VAN_HOC = 3  # translator + editor + qa


def cho_job_xong(svc, job_id, owner_id, timeout=5.0):
    han = time.time() + timeout
    while time.time() < han:
        job = svc.get_job(job_id, owner_id)
        if job.status.value in ("completed", "failed", "cancelled"):
            return job
        time.sleep(0.005)
    raise AssertionError(f"job {job_id} không xong sau {timeout}s")


class _DemLanGoi(MockTranslationProvider):
    """Spy: chi dem so lan goi, khong chan gi ca."""

    def __init__(self):
        self.so_lan_goi = 0

    def translate_segment(self, text, *, context):
        self.so_lan_goi += 1
        return super().translate_segment(text, context=context)


class _ChanOCuocGoiThu(MockTranslationProvider):
    """Chan (block that su) dung o cuoc goi thu N — mo phong worker dang
    THAT SU xu ly do (khong phai gia vo) khi "chet". Ghi lai MOI lan goi de
    kiem tra sau: khong duoc dich lai chuong da xong."""

    def __init__(self, chan_o_lan: int):
        self._chan_o_lan = chan_o_lan
        self.so_lan_goi = 0
        self.da_toi_diem_chan = threading.Event()
        self.duoc_tha = threading.Event()
        self._khoa = threading.Lock()

    def translate_segment(self, text, *, context):
        with self._khoa:
            self.so_lan_goi += 1
            lan = self.so_lan_goi
        if lan == self._chan_o_lan:
            self.da_toi_diem_chan.set()
            self.duoc_tha.wait(timeout=10)
        return super().translate_segment(text, context=context)


class KhoiPhucJobSauKhiWorkerChetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.novels = MockMetadataStore()
        self.store = MockTranslationStore()
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")

    def test_worker_chet_giua_truyen_worker_moi_hoan_tat_dung_mot_lan(self):
        # ---- 1. Tao du an: tieu thuyet 8 chuong, che do VAN_HOC -----------
        CHUONG_CHET = 4  # worker "chet" dung o cuoc goi DAU TIEN cua chuong nay
        chan_o_lan = (CHUONG_CHET - 1) * SO_PASS_VAN_HOC + 1  # = 10
        provider_a = _ChanOCuocGoiThu(chan_o_lan=chan_o_lan)
        worker_a = TranslationService(self.store, self.novels, provider=provider_a)
        p = worker_a.create_project(
            self.an.user_id, title="Tiểu thuyết thử",
            source_text=TIEU_THUYET_8_CHUONG, quality_mode="van_hoc")
        self.assertEqual(p.to_dict()["chapter_count"], SO_CHUONG)

        # Novel Bible / glossary — PHAI on dinh xuyen suot ca qua trinh.
        term = worker_a.add_glossary_entry(
            p.project_id, self.an.user_id, category="character",
            original="甲", translated="Giáp")
        worker_a.update_glossary_entry(p.project_id, self.an.user_id,
                                       term.term_id, locked=True)

        # ---- 2. Bat dau dich VAN_HOC (worker_a chay inline) ---------------
        job = worker_a.create_job(p.project_id, self.an.user_id)

        # Ghi lai progress_percent() tai MOI LAN THAT SU ghi job xuong kho
        # (khong doan bang polling theo thoi gian — voi mock chay gan nhu tuc
        # thi, mot bo lay mau theo dong ho se bo lo hau het). Boc CA HAI
        # phuong thuc ghi (`save_job`/`save_job_fenced`) tren CHINH
        # `self.store` — ca worker_a lan worker_b deu ghi vao day.
        mau_progress = []
        goc_save_job = self.store.save_job
        goc_save_job_fenced = self.store.save_job_fenced

        def save_job_theo_doi(j):
            mau_progress.append(j.progress_percent())
            return goc_save_job(j)

        def save_job_fenced_theo_doi(j, fence, worker_id):
            ok = goc_save_job_fenced(j, fence, worker_id)
            if ok:
                mau_progress.append(j.progress_percent())
            return ok

        self.store.save_job = save_job_theo_doi
        self.store.save_job_fenced = save_job_fenced_theo_doi

        # Cho toi khi THAT SU dang o dau chuong 4 (khong doan mo).
        self.assertTrue(provider_a.da_toi_diem_chan.wait(timeout=5),
                        "worker_a không tới điểm chết kịp trong 5s")

        # ---- 3. Ghi nhan tien do TRUOC khi "chet" — dung de kiem monotonic
        truoc_khi_chet = worker_a.get_job(job.job_id, self.an.user_id)
        self.assertEqual(truoc_khi_chet.current_chapter, 4)
        p_truoc = worker_a.get_project(p.project_id, self.an.user_id)
        self.assertEqual(len(p_truoc.translated_chapters), 3,
                         "đúng 3 chương (1-3) phải xong trước khi chương 4 bắt đầu")

        # ---- 4. MO PHONG WORKER CHET: lease tu troi qua han, KHONG don dep
        # gi (dung y voi mot tien trinh bi kill -9, khong kip ghi gi them).
        hien_tai = self.store.get_job(job.job_id)
        self.store._jobs[job.job_id] = replace(
            hien_tai, lease_expires_at="2020-01-01T00:00:00+00:00")

        # ---- 5. TAO INSTANCE SERVICE MOI (mo phong tien trinh moi) --------
        # Provider MOI khong chan gi — chuong con lai dich troi chay.
        provider_b = _DemLanGoi()
        worker_b = TranslationService(self.store, self.novels, provider=provider_b)

        bao_cao = worker_b.recover_stale_jobs()
        self.assertEqual(bao_cao["chay_lai"], 1,
                         "worker_b phải nhận lại được job đã hết lease")

        # ---- 6. Tha worker_a ra — no PHAI phat hien da mat quyen va KHONG
        # ghi de len ket qua cua worker_b (dong nay chi la don dep, khong anh
        # huong ket qua vi worker_a se tu buong khi kiem tra lai job).
        provider_a.duoc_tha.set()

        job_cuoi = cho_job_xong(worker_b, job.job_id, self.an.user_id)
        self.store.save_job = goc_save_job
        self.store.save_job_fenced = goc_save_job_fenced

        # ---- 7. XAC MINH -----------------------------------------------
        self.assertEqual(job_cuoi.status, TranslationJobStatus.COMPLETED,
                         f"lỗi: {job_cuoi.error}")
        self.assertEqual(job_cuoi.progress_percent(), 100)

        # Tien do KHONG BAO GIO lui — ke ca luc worker "chet" va worker_b
        # nhan lai (chuong dang do bi lam lai tu dau, nhung vi diem chet la
        # NGAY DAU chuong 4 (0/N doan da xong luc do), lam lai tu dau KHONG
        # tao mot buoc lui thuc su nao ca — day la ly do chon diem chet nay
        # thay vi mot diem giua chung mot chuong nhieu doan).
        self.assertTrue(len(mau_progress) > 5, "ghi lại quá ít để kiểm tra")
        self.assertEqual(mau_progress, sorted(mau_progress),
                         f"tiến độ bị lùi: {mau_progress}")

        p_cuoi = worker_b.get_project(p.project_id, self.an.user_id)

        # (a) so chuong CUOI CUNG khop CHINH XAC voi nguon — khong thieu,
        #     khong du (trung lap se lam mang dai hon SO_CHUONG).
        self.assertEqual(len(p_cuoi.translated_chapters), SO_CHUONG)
        self.assertEqual(len(p_cuoi.chapter_summaries), SO_CHUONG,
                         "chapter memory (tóm tắt) phải còn đủ")

        # (b) chuong 1-3 KHONG bi dich lai boi provider_a: dung 3 chuong * 3
        #     pass = 9 lan goi cho chung. Kiem tra mat quyen nam GIUA CAC
        #     DOAN (`_nen_dung_lai` truoc moi doan trong `_dich_mot_chuong`),
        #     KHONG nam giua ba vai-tro CUA CUNG mot doan — nen mot khi da
        #     bi chan o vai-tro dau tien cua chuong 4, worker_a van di NOT
        #     ca ba vai tro (translator/editor/qa) cho DOAN DUY NHAT do
        #     truoc khi kiem tra lai va phat hien mat quyen. Tong dung
        #     9 + 3 = 12 — KHONG duoc goi them lan nao nua sau moc nay (vi
        #     du neu la 13+ thi tuc la no da lo sang chuong 5, mot loi that).
        self.assertEqual(provider_a.so_lan_goi, chan_o_lan + SO_PASS_VAN_HOC - 1)

        # (c) provider_b phai TU LAM LAI chuong 4 tu dau (ca 3 pass, khong
        #     tiep tuc tu giua), roi 4 chuong con lai (5-8) — tong dung
        #     (SO_CHUONG - CHUONG_CHET + 1) * 3 pass = 5 chuong * 3 = 15 lan.
        self.assertEqual(provider_b.so_lan_goi,
                         (SO_CHUONG - CHUONG_CHET + 1) * SO_PASS_VAN_HOC)

        # (c) glossary KHONG doi — van khoa, van dung ban dich cu.
        ds_glossary = worker_b.list_glossary(p.project_id, self.an.user_id)
        self.assertEqual(len(ds_glossary), 1)
        self.assertTrue(ds_glossary[0].locked)
        self.assertEqual(ds_glossary[0].translated, "Giáp")

        # (d) DUY NHAT MOT job cho ca qua trinh "chết" + nhận lại — không có
        # job thứ hai nào được tạo ra ở bất kỳ bước nào (F5/reconnect trong
        # LÚC job còn chạy không tạo job mới — xem test riêng
        # `test_goi_lai_khi_dang_hoat_dong_tra_ve_CUNG_job` cho hợp đồng đó;
        # ở đây job đã sang trạng thái kết thúc nên tạo job MỚI lúc này là
        # đúng, không phải một lỗi trùng lặp).
        self.assertEqual(
            len(self.store.jobs_for_project(p.project_id)), 1,
            "chỉ một job duy nhất cho cả dự án, dù đã 'chết' và được nhận lại")

    def test_huy_giua_cac_pass_van_hoc(self):
        """Part M: "test cancellation between passes" — voi CHINH che do
        VAN_HOC (3 pass), khong chi NHANH nhu o test_translation_service.py."""
        # Chan o pass thu 2 (editor) cua chuong 1 — dung "giua cac pass".
        provider = _ChanOCuocGoiThu(chan_o_lan=2)
        svc = TranslationService(self.store, self.novels, provider=provider)
        p = svc.create_project(
            self.an.user_id, title="x", source_text=TIEU_THUYET_8_CHUONG,
            quality_mode="van_hoc")
        job = svc.create_job(p.project_id, self.an.user_id)

        self.assertTrue(provider.da_toi_diem_chan.wait(timeout=5))
        svc.cancel_job(job.job_id, self.an.user_id)
        provider.duoc_tha.set()

        job_cuoi = cho_job_xong(svc, job.job_id, self.an.user_id)
        self.assertEqual(job_cuoi.status, TranslationJobStatus.CANCELLED)
        p_cuoi = svc.get_project(p.project_id, self.an.user_id)
        self.assertEqual(len(p_cuoi.translated_chapters), 0,
                         "chương đang dịch dở (chưa qua đủ 3 pass) không được lưu")


if __name__ == "__main__":
    unittest.main(verbosity=2)
