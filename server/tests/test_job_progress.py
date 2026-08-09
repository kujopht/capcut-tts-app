"""
Tien do job phai SONG SOT qua mot lan tai lai trang.

Truoc day tien do chi song trong bo nho cua tien trinh worker. O production,
worker o mot may khac han tien trinh web, va `GET /api/jobs/{id}` doc tu kho
ben vung — nen thanh tien trinh dung im o 0% suot ca job. Tai lai trang thi te
hon: `/write` giu `job_id` trong state cua React, mat sach khi tai lai, va cach
duy nhat de "thay lai tien trinh" la bam tao lai — tuc la xep them mot job nua
cho mot viec dang chay.

HAI DIEU BO TEST NAY BAO VE:

  1. **Tien do duoc luu, nhung co TIET CHE.** Ghi moi tick se dam nat Appwrite
     vi mot con so ma nguoi dung khong kip doc. Khong ghi gi ca thi thanh tien
     trinh vo dung.

  2. **Tai lai trang KHONG tao them job.** Kho la nguon su that; giao dien
     phai tim lai DUNG job cu chu khong tao cai moi.
"""

from __future__ import annotations

import unittest
import uuid
from typing import List

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockMetadataStore
from server.domain import JobStatus, TtsJob
from server.tests.voice_stub import dung_registry_gia


class Nen(unittest.TestCase):
    """Kho gia + mot nguoi dung + mot truyen + mot chuong."""

    def setUp(self) -> None:
        # `POST /api/jobs` cuong che pham vi giong that; `mock:v1` khong co
        # trong registry that nen se bi 400 truoc khi kip kiem thu ta quan tam.
        dung_registry_gia(self)
        self.store = MockMetadataStore()
        cu_store = server_main.store
        server_main.store = self.store
        self.addCleanup(lambda: setattr(server_main, "store", cu_store))

        self.c = TestClient(server_main.app)
        # Email DUY NHAT moi lan: `server_main.identity` la mot doi tuong toan
        # cuc dung chung giua cac module test, nen mot dia chi co dinh se bi
        # "Email này đã được đăng ký" ngay khi mot module khac dung truoc.
        email = f"tacgia-{uuid.uuid4().hex[:12]}@vi-du.test"
        r = self.c.post("/api/auth/register",
                        json={"email": email,
                              "password": "matkhaudai123", "display_name": "Tác giả"})
        self.assertEqual(r.status_code, 201, r.text[:200])
        self.token = r.json()["token"]
        self.uid = r.json()["profile"]["user_id"]
        self.head = {"Authorization": f"Bearer {self.token}"}

        self.nid = self.c.post("/api/novels", headers=self.head,
                               json={"title": "Truyện", "description": "",
                                     "tags": []}).json()["novel"]["novel_id"]
        self.cid = self.c.post("/api/chapters", headers=self.head,
                               json={"novel_id": self.nid, "title": "Chương 1",
                                     "content": "Nội dung chương một." * 40,
                                     "order_index": 1}).json()["chapter"]["chapter_id"]

    def _job_dang_chay(self, done: int = 0, total: int = 0) -> TtsJob:
        """Mot job `running` da duoc nhan, de co fence va lease that."""
        job = TtsJob(owner_id=self.uid, chapter_id=self.cid, voice_id="mock:v1",
                     content_hash="h1", status=JobStatus.RUNNING,
                     done_parts=done, total_parts=total,
                     attempts=1, lease_owner=server_main.WORKER_ID,
                     lease_expires_at="2099-01-01T00:00:00+00:00")
        self.store.save_job(job)
        return job


# ------------------------------------------------------------- luu tien do


class LuuTienDo(Nen):

    def test_save_progress_chi_ghi_hai_truong(self) -> None:
        """
        Cung ly do voi `renew_lease`: worker khong nam giu trang thai moi nhat
        cua ca hang, nen moi truong thua no gui deu co the lui nguoc du lieu.
        """
        job = self._job_dang_chay()
        # Mot duong khac vua ghi `output_key` — `save_progress` khong duoc xoa no.
        from dataclasses import replace

        self.store.save_job(replace(self.store.get_job(job.job_id),
                                    output_key="audio/da-co.mp3"))

        self.assertTrue(self.store.save_progress(job.job_id, 1,
                                                 server_main.WORKER_ID, 7, 20))
        sau = self.store.get_job(job.job_id)
        self.assertEqual((sau.done_parts, sau.total_parts), (7, 20))
        self.assertEqual(sau.output_key, "audio/da-co.mp3")
        self.assertEqual(sau.status, JobStatus.RUNNING)

    def test_progress_la_dan_xuat_chu_khong_luu_rieng(self) -> None:
        """Mot con so phan tram luu rieng thi co the troi khoi hai truong nguon."""
        job = self._job_dang_chay()
        self.store.save_progress(job.job_id, 1, server_main.WORKER_ID, 5, 20)
        self.assertEqual(self.store.get_job(job.job_id).progress_percent, 25)

    def test_mat_lease_thi_KHONG_ghi(self) -> None:
        """Worker cu bi treo khong duoc de len ket qua cua worker moi."""
        job = self._job_dang_chay()
        self.assertFalse(self.store.save_progress(job.job_id, 1, "worker-khac", 9, 20))
        self.assertFalse(self.store.save_progress(job.job_id, 99,
                                                  server_main.WORKER_ID, 9, 20))
        self.assertEqual(self.store.get_job(job.job_id).done_parts, 0)

    def test_job_khong_ton_tai_thi_tra_False_chu_khong_nem(self) -> None:
        self.assertFalse(self.store.save_progress("khong-co", 1,
                                                  server_main.WORKER_ID, 1, 2))


class TietCheGhi(Nen):
    """
    Callback chay MOI DOAN. Mot chuong 100.000 ky tu la hon 50 doan, va moi lan
    ghi Appwrite la mot transaction ba luot goi.
    """

    def setUp(self) -> None:
        super().setUp()
        self.so_lan = 0
        that = self.store.save_progress

        def dem(*a, **k):
            self.so_lan += 1
            return that(*a, **k)

        self.store.save_progress = dem          # type: ignore[method-assign]

    def test_lan_dau_biet_tong_LUON_duoc_ghi(self) -> None:
        """
        Giao dien can `total_parts` NGAY de chuyen tu thanh chay vo dinh sang
        thanh co ty le. Doi 3 giay cho con so nay la de nguoi dung nhin mot
        thanh vo nghia trong ba giay dau.
        """
        job = self._job_dang_chay()
        sink = server_main._progress_sink(job, 1)
        sink(0, 40)
        self.assertEqual(self.so_lan, 1)
        self.assertEqual(self.store.get_job(job.job_id).total_parts, 40)

    def test_cac_tick_lien_tiep_bi_go_bot(self) -> None:
        """40 doan lien tiep KHONG duoc thanh 40 lan ghi."""
        job = self._job_dang_chay()
        sink = server_main._progress_sink(job, 1)
        for i in range(41):
            sink(i, 400)        # 400 doan -> moi doan chi 0.25%, duoi nguong 5%
        self.assertLess(self.so_lan, 10,
                        f"ghi {self.so_lan} lần cho 41 tick — chưa tiết chế")

    def test_nhich_du_phan_tram_thi_ghi_ngay_du_chua_du_thoi_gian(self) -> None:
        """
        Chuong ngan: 4 doan thi moi doan la 25%. Cho du 3 giay se lam thanh
        tien trinh nhay giat.
        """
        job = self._job_dang_chay()
        sink = server_main._progress_sink(job, 1)
        sink(0, 4)              # lan dau: biet tong
        truoc = self.so_lan
        sink(1, 4)              # +25% -> phai ghi ngay
        self.assertEqual(self.so_lan, truoc + 1)

    def test_bo_nho_LUON_duoc_cap_nhat_du_khong_ghi_kho(self) -> None:
        """
        Khi web va worker cung tien trinh, `/api/jobs` doc tu doi tuong trong
        bo nho — no phai luon moi.
        """
        job = self._job_dang_chay()
        sink = server_main._progress_sink(job, 1)
        sink(0, 400)
        sink(1, 400)            # bi tiet che, khong ghi kho
        self.assertEqual((job.done_parts, job.total_parts), (1, 400))

    def test_ghi_hong_KHONG_lam_job_that_bai(self) -> None:
        """Tien do la thong tin phu; ket qua that do cac transition quyet dinh."""
        def no(*a, **k):
            raise RuntimeError("mạng chập")

        self.store.save_progress = no           # type: ignore[method-assign]
        job = self._job_dang_chay()
        sink = server_main._progress_sink(job, 1)
        sink(3, 10)             # khong duoc nem ra ngoai
        self.assertEqual(job.done_parts, 3)


# --------------------------------------------------- tim lai job sau reload


class TimLaiJob(Nen):

    def _tao_job(self, status: JobStatus, tao_luc: str,
                 chapter_id: str = "") -> TtsJob:
        job = TtsJob(owner_id=self.uid, chapter_id=chapter_id or self.cid,
                     voice_id="mock:v1", content_hash=f"h-{tao_luc}",
                     status=status, created_at=tao_luc)
        self.store.save_job(job)
        return job

    def test_chuong_chua_co_job_tra_ve_null(self) -> None:
        r = self.c.get(f"/api/chapters/{self.cid}/jobs/latest", headers=self.head)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["job"])

    def test_tra_ve_job_DANG_CHAY_chu_khong_phai_ban_hoan_tat_moi_hon(self) -> None:
        """
        Sau khi tai lai trang, cai nguoi dung can thay la thanh tien trinh,
        khong phai mot ket qua cu.
        """
        self._tao_job(JobStatus.COMPLETED, "2026-08-09T10:00:00+00:00")
        dang_chay = self._tao_job(JobStatus.RUNNING, "2026-08-09T09:00:00+00:00")
        r = self.c.get(f"/api/chapters/{self.cid}/jobs/latest", headers=self.head)
        self.assertEqual(r.json()["job"]["job_id"], dang_chay.job_id)

    def test_cung_trang_thai_thi_lay_cai_moi_hon(self) -> None:
        self._tao_job(JobStatus.COMPLETED, "2026-08-09T08:00:00+00:00")
        moi = self._tao_job(JobStatus.COMPLETED, "2026-08-09T11:00:00+00:00")
        r = self.c.get(f"/api/chapters/{self.cid}/jobs/latest", headers=self.head)
        self.assertEqual(r.json()["job"]["job_id"], moi.job_id)

    def test_job_that_bai_van_duoc_tra_ve(self) -> None:
        """Nguoi dung phai thay that bai that, khong phai mot man hinh trong."""
        hong = self._tao_job(JobStatus.FAILED, "2026-08-09T10:00:00+00:00")
        r = self.c.get(f"/api/chapters/{self.cid}/jobs/latest", headers=self.head)
        self.assertEqual(r.json()["job"]["job_id"], hong.job_id)
        self.assertEqual(r.json()["job"]["status"], "failed")

    def test_can_dang_nhap(self) -> None:
        r = self.c.get(f"/api/chapters/{self.cid}/jobs/latest")
        self.assertEqual(r.status_code, 401)

    def test_KHONG_lo_job_cua_nguoi_khac(self) -> None:
        self._tao_job(JobStatus.RUNNING, "2026-08-09T10:00:00+00:00")
        nguoi_khac = self.c.post(
            "/api/auth/register",
            json={"email": f"nguoila-{uuid.uuid4().hex[:12]}@vi-du.test",
                  "password": "matkhaudai123"}).json()["token"]
        r = self.c.get(f"/api/chapters/{self.cid}/jobs/latest",
                       headers={"Authorization": f"Bearer {nguoi_khac}"})
        # 404 chu khong phai 403: nguoi la khong duoc biet chuong nay ton tai.
        self.assertEqual(r.status_code, 404)

    def test_chuong_khong_ton_tai_tra_404(self) -> None:
        r = self.c.get("/api/chapters/khong-co/jobs/latest", headers=self.head)
        self.assertEqual(r.status_code, 404)


class TaiLaiTrangKhongTaoThemJob(Nen):
    """
    Dieu quan trong nhat cua ca tinh nang: mot lan F5 khong duoc tra tien them
    mot lan tong hop TTS.
    """

    def setUp(self) -> None:
        super().setUp()
        # Mo phong PRODUCTION: tien trinh web KHONG tu chay job
        # (`FAS_INLINE_WORKER=false`), job nam `pending` cho worker nhan.
        #
        # Neu de che do inline, giong gia se tong hop that bai ngay lap tuc va
        # job thanh `failed`. Job `failed` CO Y nha khoa de nguoi dung thu lai
        # duoc, nen moi lan bam se tao mot job moi — dung hanh vi mong muon,
        # nhung khong phai kich ban dang kiem o day.
        cu = server_main._CAN_RUN_JOBS
        server_main._CAN_RUN_JOBS = False
        self.addCleanup(lambda: setattr(server_main, "_CAN_RUN_JOBS", cu))

    def _tao(self) -> dict:
        return self.c.post("/api/jobs", headers=self.head,
                           json={"chapter_id": self.cid,
                                 "voice_id": "mock:v1"}).json()

    def test_goi_lai_createJob_dung_lai_job_cu(self) -> None:
        dau = self._tao()
        lai = self._tao()
        self.assertEqual(lai["job"]["job_id"], dau["job"]["job_id"])
        self.assertTrue(lai["reused"])

    def test_chi_co_DUNG_MOT_job_trong_kho(self) -> None:
        self._tao()
        self._tao()
        self._tao()
        r = self.c.get(f"/api/jobs?chapter_id={self.cid}", headers=self.head)
        self.assertEqual(r.json()["count"], 1)

    def test_job_tim_lai_duoc_la_DUNG_job_da_tao(self) -> None:
        """Kich ban that: tao job -> tai lai trang -> tim lai."""
        dau = self._tao()["job"]
        tim_lai = self.c.get(f"/api/chapters/{self.cid}/jobs/latest",
                             headers=self.head).json()["job"]
        self.assertEqual(tim_lai["job_id"], dau["job_id"])

    def test_NAM_request_DONG_THOI_chi_tao_MOT_job(self) -> None:
        """
        Tai hien DUNG loi da xay ra tren production.

        Bang chung trong kho production: nam hang `tts_jobs` cung fingerprint,
        cung chuong, tao trong 2 giay — nguoi dung bam nut nhieu lan. Idempotency
        cu la doc-roi-ghi khong nguyen tu, nen ca nam request deu doc thay
        "chua co" va deu tao mot job. TTS chay nam lan.

        Bam nut nhanh KHONG duoc chan bang cach vo hieu hoa nut o trinh duyet:
        hai tab, hai thiet bi, hoac mot lan mat mang roi thu lai deu di vong
        qua no.
        """
        import threading

        ket_qua: List[dict] = []
        khoa = threading.Lock()

        def bam():
            r = self.c.post("/api/jobs", headers=self.head,
                            json={"chapter_id": self.cid, "voice_id": "mock:v1"})
            with khoa:
                ket_qua.append(r.json())

        luong = [threading.Thread(target=bam) for _ in range(5)]
        for t in luong:
            t.start()
        for t in luong:
            t.join()

        self.assertEqual(len(ket_qua), 5)
        ids = {r["job"]["job_id"] for r in ket_qua}
        self.assertEqual(len(ids), 1,
                         f"5 request đồng thời tạo ra {len(ids)} job khác nhau")

        # Va trong KHO cung chi co dung mot.
        trong_kho = self.c.get(f"/api/jobs?chapter_id={self.cid}",
                               headers=self.head).json()
        self.assertEqual(trong_kho["count"], 1)

        # Dung MOT request duoc bao la vua tao; bon cai con lai la dung lai.
        self.assertEqual(sum(1 for r in ket_qua if not r["reused"]), 1)

    def test_hai_giong_khac_nhau_VAN_la_hai_job(self) -> None:
        """
        Khoa khong duoc chat qua muc: doi giong la mot yeu cau THAT SU khac, va
        nguoi dung phai tao duoc ban thu hai.
        """
        a = self.c.post("/api/jobs", headers=self.head,
                        json={"chapter_id": self.cid, "voice_id": "mock:v1"}).json()
        b = self.c.post("/api/jobs", headers=self.head,
                        json={"chapter_id": self.cid, "voice_id": "mock:v2"}).json()
        self.assertNotEqual(a["job"]["job_id"], b["job"]["job_id"])
        self.assertFalse(b["reused"])

    def test_listJobs_du_de_khoi_phuc_CA_TRANG_bang_MOT_request(self) -> None:
        """
        Giao dien khoi phuc bang `listJobs()`, khong goi
        `/jobs/latest` cho tung chuong — do la N+1.
        """
        self._tao()
        r = self.c.get("/api/jobs", headers=self.head)
        self.assertEqual(r.status_code, 200)
        theo_chuong = {j["chapter_id"] for j in r.json()["jobs"]}
        self.assertIn(self.cid, theo_chuong)


if __name__ == "__main__":
    unittest.main()
