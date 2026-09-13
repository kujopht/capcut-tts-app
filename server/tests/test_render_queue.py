"""
Hang doi render + phien tai len — hai hop dong phai dung TRUOC khi co
worker that.

Moi bai o day truyen `now` tuong minh: mot bo kiem hang doi ma phai NGU de
cho het han la mot bo kiem cham va hay do vu vo.
"""

from __future__ import annotations

import unittest

from server.domain import MediaType
from server.render_queue import (TRAN_THU_LAI, MockRenderQueue, RenderJobState)
from server.upload_session import (MIME_CHO_PHEP, TRAN_BYTE, UploadError,
                                   UploadState, MockUploadSessionStore,
                                   UploadSession, khoa_moi, kiem_xin_phien)


class XepHangTest(unittest.TestCase):
    def setUp(self):
        self.q = MockRenderQueue()

    def test_xep_hang_roi_nhan_viec(self):
        j = self.q.xep_hang("an", "vpr1", "k1")
        self.assertIs(j.state, RenderJobState.QUEUED)
        nhan = self.q.nhan_viec("w1", now=100.0)
        self.assertIsNotNone(nhan)
        self.assertIs(nhan.state, RenderJobState.RUNNING)
        self.assertEqual(nhan.lease_owner, "w1")

    def test_CUNG_idempotency_key_KHONG_tao_job_thu_hai(self):
        """Hai lan bam Render phai ra mot job, khong phai hai lan ma hoa."""
        a = self.q.xep_hang("an", "vpr1", "k1")
        b = self.q.xep_hang("an", "vpr1", "k1")
        self.assertEqual(a.job_id, b.job_id)

    def test_key_khac_thi_la_job_khac(self):
        a = self.q.xep_hang("an", "vpr1", "k1")
        b = self.q.xep_hang("an", "vpr1", "k2")
        self.assertNotEqual(a.job_id, b.job_id)

    def test_chong_trung_KHONG_vuot_qua_ranh_gioi_nguoi_dung(self):
        a = self.q.xep_hang("an", "vpr1", "k1")
        b = self.q.xep_hang("binh", "vpr1", "k1")
        self.assertNotEqual(a.job_id, b.job_id)

    def test_hai_worker_KHONG_cung_nhan_mot_job(self):
        self.q.xep_hang("an", "vpr1", "k1")
        self.assertIsNotNone(self.q.nhan_viec("w1", now=100.0))
        self.assertIsNone(self.q.nhan_viec("w2", now=101.0))

    def test_worker_CHET_thi_job_tu_ve_hang_doi_sau_khi_het_han(self):
        """Han giu cho la cach DUY NHAT hang doi tu phuc hoi ma khong phai
        theo doi worker."""
        self.q.xep_hang("an", "vpr1", "k1")
        self.q.nhan_viec("w1", lease_giay=60, now=100.0)
        self.assertIsNone(self.q.nhan_viec("w2", now=130.0))      # con han
        lai = self.q.nhan_viec("w2", now=200.0)                   # het han
        self.assertIsNotNone(lai)
        self.assertEqual(lai.lease_owner, "w2")
        self.assertEqual(lai.attempts, 2)

    def test_nhip_tim_gia_han_duoc_cho(self):
        self.q.xep_hang("an", "vpr1", "k1")
        j = self.q.nhan_viec("w1", lease_giay=60, now=100.0)
        self.assertTrue(self.q.nhip_tim(j.job_id, "w1", now=150.0))
        self.assertIsNone(self.q.nhan_viec("w2", now=180.0))

    def test_worker_MAT_cho_thi_nhip_tim_tra_False(self):
        """`False` la tin hieu cho worker DUNG LAI — hai worker cung ghi mot
        dau ra la cach tao ra mot tep hong."""
        self.q.xep_hang("an", "vpr1", "k1")
        j = self.q.nhan_viec("w1", lease_giay=60, now=100.0)
        self.q.nhan_viec("w2", now=200.0)
        self.assertFalse(self.q.nhip_tim(j.job_id, "w1", now=210.0))

    def test_chi_worker_dang_giu_moi_hoan_tat_duoc(self):
        self.q.xep_hang("an", "vpr1", "k1")
        j = self.q.nhan_viec("w1", now=100.0)
        self.assertFalse(self.q.hoan_tat(j.job_id, "w2",
                                         output_object_key="out.mp4"))
        self.assertTrue(self.q.hoan_tat(j.job_id, "w1",
                                        output_object_key="out.mp4"))
        self.assertIs(self.q.lay("an", j.job_id).state, RenderJobState.DONE)

    def test_hoan_tat_PHAI_kem_tep_ket_qua(self):
        self.q.xep_hang("an", "vpr1", "k1")
        j = self.q.nhan_viec("w1", now=100.0)
        with self.assertRaises(ValueError):
            self.q.hoan_tat(j.job_id, "w1", output_object_key="")

    def test_that_bai_thi_ve_lai_hang_doi_khi_con_lan_thu(self):
        self.q.xep_hang("an", "vpr1", "k1")
        j = self.q.nhan_viec("w1", now=100.0)
        self.q.that_bai(j.job_id, "w1", loi="mạng lỗi")
        self.assertIs(self.q.lay("an", j.job_id).state, RenderJobState.QUEUED)

    def test_het_lan_thu_thi_DONG_LAI_chu_khong_quay_mai(self):
        """Mot job hong vi tep nguon hong se hong MAI."""
        self.q.xep_hang("an", "vpr1", "k1")
        for i in range(TRAN_THU_LAI):
            j = self.q.nhan_viec("w1", now=100.0 + i)
            self.assertIsNotNone(j, f"vòng {i} không nhận được việc")
            self.q.that_bai(j.job_id, "w1", loi="hỏng")
        self.assertIsNone(self.q.nhan_viec("w1", now=999.0))
        ds = self.q.cho_du_an("an", "vpr1")
        self.assertIs(ds[0].state, RenderJobState.FAILED)

    def test_that_bai_KHONG_thu_lai_thi_dong_ngay(self):
        self.q.xep_hang("an", "vpr1", "k1")
        j = self.q.nhan_viec("w1", now=100.0)
        self.q.that_bai(j.job_id, "w1", loi="tệp hỏng", thu_lai=False)
        self.assertIs(self.q.lay("an", j.job_id).state, RenderJobState.FAILED)

    def test_KHONG_doc_duoc_job_cua_nguoi_khac(self):
        j = self.q.xep_hang("an", "vpr1", "k1")
        self.assertIsNone(self.q.lay("binh", j.job_id))

    def test_tien_do_KHONG_bi_bia(self):
        """`None` khi khong do duoc — khong phai 0."""
        self.q.xep_hang("an", "vpr1", "k1")
        j = self.q.nhan_viec("w1", now=100.0)
        self.assertIsNone(j.progress)
        self.q.nhip_tim(j.job_id, "w1", progress=0.4, now=110.0)
        self.assertAlmostEqual(self.q.lay("an", j.job_id).progress, 0.4)


class PhienTaiLenTest(unittest.TestCase):
    def test_khoa_do_MAY_CHU_sinh_va_mang_chu_so_huu(self):
        k = khoa_moi("an", MediaType.VIDEO)
        self.assertTrue(k.startswith("studio/an/video/"))
        self.assertTrue(k.endswith(".mp4"))

    def test_hai_lan_sinh_ra_hai_khoa_khac_nhau(self):
        self.assertNotEqual(khoa_moi("an", MediaType.VIDEO),
                            khoa_moi("an", MediaType.VIDEO))

    def test_ten_tep_doc_hai_KHONG_lot_vao_khoa(self):
        """Khoa khong lay gi tu ten nguoi dung gui — `.mp4.exe` khong the
        bien thanh mot khoa `.exe`."""
        k = khoa_moi("an", MediaType.VIDEO)
        for xau in ("..", "exe", " ", "%"):
            self.assertNotIn(xau, k)

    def test_MIME_ngoai_danh_sach_bi_tu_choi(self):
        for loai, xau in ((MediaType.VIDEO, "application/x-msdownload"),
                          (MediaType.IMAGE, "video/mp4"),
                          (MediaType.SUBTITLES, "image/png")):
            with self.assertRaises(UploadError):
                kiem_xin_phien(loai, xau, 1024)

    def test_MIME_hop_le_di_qua(self):
        for loai in MIME_CHO_PHEP:
            mime = sorted(MIME_CHO_PHEP[loai])[0]
            self.assertEqual(kiem_xin_phien(loai, mime, 1024), 1024)

    def test_qua_tran_bi_tu_choi(self):
        with self.assertRaises(UploadError):
            kiem_xin_phien(MediaType.VIDEO, "video/mp4",
                           TRAN_BYTE[MediaType.VIDEO] + 1)

    def test_kich_thuoc_vo_ly_bi_tu_choi(self):
        for xau in (0, -1, True, "1024", None):
            with self.assertRaises(UploadError):
                kiem_xin_phien(MediaType.VIDEO, "video/mp4", xau)

    def test_phien_cua_nguoi_khac_KHONG_lay_duoc(self):
        from server.adapters import NotFoundError
        kho = MockUploadSessionStore()
        p = kho.luu(UploadSession(
            owner_id="an", media_type=MediaType.VIDEO, mime="video/mp4",
            declared_bytes=10, object_key=khoa_moi("an", MediaType.VIDEO),
            expires_at=9e9))
        with self.assertRaises(NotFoundError):
            kho.lay("binh", p.session_id)

    def test_phien_qua_han_bi_danh_dau_BO_DO(self):
        kho = MockUploadSessionStore()
        kho.luu(UploadSession(
            owner_id="an", media_type=MediaType.VIDEO, mime="video/mp4",
            declared_bytes=10, object_key="k", expires_at=100.0))
        self.assertEqual(kho.don_het_han(now=200.0), 1)
        self.assertIs(kho.lay("an", kho.lay("an", list(kho._phien)[0]).session_id).state,
                      UploadState.ABANDONED)

    def test_phien_con_han_KHONG_bi_dung_toi(self):
        kho = MockUploadSessionStore()
        p = kho.luu(UploadSession(
            owner_id="an", media_type=MediaType.VIDEO, mime="video/mp4",
            declared_bytes=10, object_key="k", expires_at=1000.0))
        self.assertEqual(kho.don_het_han(now=500.0), 0)
        self.assertIs(kho.lay("an", p.session_id).state, UploadState.PENDING)


if __name__ == "__main__":
    unittest.main()
