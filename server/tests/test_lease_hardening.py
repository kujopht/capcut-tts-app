"""
Lease va fencing: mot job chi duoc tong hop MOT LAN, du chay lau hon lease.

Moi test o day bat nguon tu mot su viec quan sat duoc tren staging, khong phai
tu suy doan:

  Mot job TTS duy nhat ket thuc voi `attempts=2`. Khong ai bam "Tao audio" hai
  lan, khong worker thu hai nao chay, va job khong he that bai lan nao. Doc log
  ra thi thay hai lan `chay_lai` cach nhau vai giay — CUNG MOT tien trinh worker
  da nhan lai job MA CHINH NO dang chay, roi goi TTS lan thu hai.

Nguyen nhan goc gom hai manh, va phai co ca hai moi xay ra:

  1. `claim_job` chi tu choi khi lease con song VA thuoc ve worker KHAC. Lease
     cua chinh minh thi no cap fence moi.
  2. `recover_stale_jobs` quyet dinh dua tren mot ban doc danh sach job qua
     Appwrite. Ban doc do tre hon lan claim vua roi, nen no thay "chua ai giu".

Ghep lai: bo quet doc phai anh cu, hoi `claim_job`, va `claim_job` dong y vi
nguoi hoi chinh la chu lease. Hai thread cung tong hop mot chuong.

Vi sao khong ai phat hien som hon: `output_key` la tat dinh theo `content_hash`
va `create_track` la tim-hoac-tao, nen ket qua CUOI CUNG van dung — mot track,
mot object. Chi co quota va thoi gian bi doi len. Bo test nay giu lai ca hai:
tinh dung dan cua ket qua VA viec khong lam viec thua.

Chay hoan toan offline: pipeline TTS duoc thay bang ban gia lap.
"""

from __future__ import annotations

import inspect
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from server import main as server_main
from server import tts_bridge
from server.adapters import LocalStorageAdapter, MockMetadataStore
from server.appwrite_store import AppwriteMetadataStore
from server.domain import AudioTrack, Chapter, JobStatus, Novel, TtsJob


def moc(giay: float) -> str:
    """Moc thoi gian ISO cach bay gio `giay` giay. Am = da qua."""
    return (datetime.now(timezone.utc) + timedelta(seconds=giay)).isoformat(
        timespec="seconds")


class DemStore(MockMetadataStore):
    """Ban mock co dem so lan tao track, de bat viec sinh trung."""

    def __init__(self) -> None:
        super().__init__()
        self.so_lan_tao_track = 0
        self.track_moi: List[str] = []

    def create_track(self, track: AudioTrack) -> AudioTrack:
        self.so_lan_tao_track += 1
        ket_qua = super().create_track(track)
        if ket_qua.track_id == track.track_id:
            self.track_moi.append(track.track_id)
        return ket_qua


class NenTest(unittest.TestCase):
    """Nen chung: kho gia, storage tam, TTS gia lap dem so lan goi."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self.goc = Path(self._tmp)

        self.store = DemStore()
        self._store_that = server_main.store
        self._storage_that = server_main.storage
        self._synth_that = tts_bridge.synthesize_chapter
        self._lease_that = server_main._lease_until
        self._nhip_that = server_main.JOB_HEARTBEAT_SECONDS
        self._chay_duoc_that = server_main._CAN_RUN_JOBS

        server_main.store = self.store
        server_main.storage = LocalStorageAdapter(self.goc)
        server_main._CAN_RUN_JOBS = True

        #: Moi lan `synthesize_chapter` duoc goi, mot dong duoc them vao day.
        self.lan_goi_tts: List[str] = []
        self.tts_cham_giay = 0.0
        tts_bridge.synthesize_chapter = self._tts_gia()

    def tearDown(self) -> None:
        server_main.store = self._store_that
        server_main.storage = self._storage_that
        tts_bridge.synthesize_chapter = self._synth_that
        server_main._lease_until = self._lease_that
        server_main.JOB_HEARTBEAT_SECONDS = self._nhip_that
        server_main._CAN_RUN_JOBS = self._chay_duoc_that
        with server_main._job_lock:
            server_main._job_threads.clear()

    # -- tien ich -------------------------------------------------------------

    def _tts_gia(self):
        def _synth(text, voice_id, dest, rate="1.0", chunk_chars=2000,
                   on_progress=None, cancel=None) -> Dict[str, Any]:
            self.lan_goi_tts.append(threading.current_thread().name)
            if self.tts_cham_giay:
                time.sleep(self.tts_cham_giay)
            dest = Path(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\x00" * 2048)
            if on_progress:
                on_progress(1, 1)
            return {"size_bytes": 2048, "total_parts": 1,
                    "voice_id": voice_id, "provider": "gia-lap"}
        return _synth

    def _lease_ngan(self, giay: float) -> None:
        """Rut ngan lease. Phai vá `_lease_until`, khong phai hang so.

        `_lease_until(seconds=JOB_LEASE_SECONDS)` gan gia tri vao THAM SO MAC
        DINH, tuc la no duoc chot ngay luc dinh nghia ham. Doi hang so o module
        sau do khong con tac dung nao.
        """
        server_main._lease_until = lambda seconds=None: moc(giay)

    def _job(self, noi_dung: str = "Nội dung chương.") -> TtsJob:
        # Chuong phai TON TAI that trong kho. `recover_stale_jobs` doc lai chuong
        # sau khi nhan job; khong co chuong thi no ket luan "chương đã bị xoá" va
        # dung lai — mot test dua vao duong do se xanh vi ly do sai.
        self.store.create_novel(Novel(novel_id="truyen-1", owner_id="chu-1",
                                      title="Truyện"))
        self.store.create_chapter(Chapter(
            chapter_id="chuong-1", novel_id="truyen-1", owner_id="chu-1",
            title="Chương 1", content=noi_dung, order_index=1))
        return self.store.create_job(TtsJob(
            owner_id="chu-1", chapter_id="chuong-1", voice_id="gia:v1",
            content_hash="dau-van-tay-1", rate="1.0", chunk_chars=2000))

    def _so_object(self) -> int:
        return sum(1 for p in self.goc.rglob("*") if p.is_file())


# -----------------------------------------------------------------------------
# 1. Job chay lau hon lease
# -----------------------------------------------------------------------------


class JobDaiHonLease(NenTest):
    """Chuong dai hon lease van chi duoc tong hop mot lan."""

    def test_heartbeat_giu_lease_song_suot_mot_job_dai(self) -> None:
        # Cac con so o day khong tuy tien. `moc()` dung
        # `isoformat(timespec="seconds")`, tuc la CAT CUT toi giay — mot lease
        # "1 giay" cap luc t=0.9 se het han o t=1.0, chi song 0.1 giay. Bien do
        # phai du lon de phan cat cut do khong quyet dinh ket qua, neu khong
        # chinh test nay tro thanh thu chap chon (da gap: hong 2/6 lan chay).
        #
        # Lease 3s, nhip 0.5s, tong hop 5s, doc luc t=4s:
        #   * khong co heartbeat -> lease chet tu t=3 -> test do, dung y do;
        #   * co heartbeat -> gia han gan nhat truoc t=4 la t=3.5, het han t=6.5,
        #     cat cut con t=6 — van du xa moc t=4.
        self._lease_ngan(3.0)
        server_main.JOB_HEARTBEAT_SECONDS = 0.5
        self.tts_cham_giay = 5.0          # dai hon lease

        job = self._job()
        fence = self.store.claim_job(job, server_main.WORKER_ID,
                                     server_main._lease_until())
        self.assertEqual(fence, 1)

        t = threading.Thread(target=server_main._run_job,
                             args=(job, "Nội dung chương.", fence))
        t.start()

        # Giua chung, lease phai VAN con song nho heartbeat.
        time.sleep(4.0)
        giua_chung = self.store.get_job(job.job_id)
        self.assertTrue(
            giua_chung.lease_is_live(),
            "lease đã hết hạn giữa lúc worker còn đang tổng hợp — "
            "heartbeat không làm việc")
        self.assertIs(giua_chung.status, JobStatus.RUNNING,
                      "heartbeat không được kéo trạng thái lùi khỏi running")

        t.join(timeout=10)
        xong = self.store.get_job(job.job_id)
        self.assertIs(xong.status, JobStatus.COMPLETED)
        self.assertEqual(xong.attempts, 1, "job chỉ được chạy đúng một lần")
        self.assertEqual(len(self.lan_goi_tts), 1, "TTS chỉ được gọi một lần")

    def test_chuong_dai_that_van_ra_dung_mot_track(self) -> None:
        """
        Mot chuong fanfic co that (60.000 ky tu) di het duong ong.

        60.000 ky tu la co mot chuong dai thuc te, khong phai so bia: chunker
        cat ra 32 doan voi `chunk_chars=2000` mac dinh. Muc dich o day KHONG
        phai do toc do TTS (da gia lap) ma la chung minh so doan khong lam thay
        doi ket qua: van mot job, mot lan nhan, mot track, mot object.

        Gioi han cung nam o schema Appwrite: cot `content` toi da 1.000.000 ky
        tu (`scripts/setup_appwrite.py`). Xem docs/RUNBOOK-WORKER.md.
        """
        from desktop_app.text_chunker import chunk_text

        cau = ("Luffy đứng trên boong tàu Sunny nhìn ra khơi xa, gió biển thổi "
               "tung chiếc mũ rơm quen thuộc trên đầu cậu. ")
        dai = (cau * (60_000 // len(cau) + 1))[:60_000]
        self.assertEqual(len(chunk_text(dai, 2000)), 32,
                         "số đoạn đổi thì con số trong tài liệu cũng phải đổi")

        job = self._job(dai)
        fence = self.store.claim_job(job, server_main.WORKER_ID, moc(60))
        server_main._run_job(job, dai, fence)

        xong = self.store.get_job(job.job_id)
        self.assertIs(xong.status, JobStatus.COMPLETED)
        self.assertEqual(xong.attempts, 1)
        self.assertEqual(len(self.store.track_moi), 1)
        self.assertEqual(self._so_object(), 1)

    def test_heartbeat_khong_dap_de_len_ca_hang(self) -> None:
        """
        Nhip chi duoc doi hai truong lease.

        Do that tren staging: heartbeat cu goi `save_job_fenced` voi mot ban sao
        `TtsJob` chup tu luc khoi dong thread, nen no ghi de CA HANG bang trang
        thai cu — quan sat duoc canh `status` bi keo tu `running` ve `pending`.
        """
        job = self._job()
        fence = self.store.claim_job(job, "w1", moc(60))
        self.assertEqual(fence, 1)

        # `job` o day la ban sao CU: van con `pending`, chua co output_key.
        # Mot lan gia han khong duoc phep lam no thanh su that.
        self.assertTrue(server_main.store.renew_lease(job.job_id, fence, "w1",
                                                      moc(120)))
        sau = self.store.get_job(job.job_id)
        self.assertIs(sau.status, JobStatus.RUNNING,
                      "gia hạn lease không được đổi trạng thái job")
        self.assertEqual(sau.attempts, 1)
        self.assertEqual(sau.lease_owner, "w1")

    def test_gia_han_that_bai_khi_da_mat_quyen(self) -> None:
        job = self._job()
        fence = self.store.claim_job(job, "w1", moc(-1))
        self.store.claim_job(job, "w2", moc(60))      # w2 cuop duoc vi lease chet
        self.assertFalse(
            self.store.renew_lease(job.job_id, fence, "w1", moc(120)),
            "worker đã mất quyền không được gia hạn lease")


# -----------------------------------------------------------------------------
# 2. Hai worker canh tranh
# -----------------------------------------------------------------------------


class HaiWorkerCanhTranh(NenTest):

    def test_worker_khac_khong_cuop_duoc_job_con_song(self) -> None:
        job = self._job()
        self.assertEqual(self.store.claim_job(job, "w1", moc(60)), 1)
        self.assertIsNone(self.store.claim_job(job, "w2", moc(60)),
                          "job còn lease sống không được nhường cho worker khác")

    def test_chinh_chu_lease_cung_khong_duoc_nhan_lai(self) -> None:
        """
        DAY LA LOI GOC. Truoc khi sua, lan claim thu hai tra ve fence=2.

        Dieu kien cu la `lease_is_live() and lease_owner != worker_id`, tuc la
        mien la nguoi hoi chinh la chu lease thi duoc cap fence moi. Bo quet doc
        phai mot ban danh sach cu vai giay se hoi dung nhu vay.
        """
        job = self._job()
        self.assertEqual(self.store.claim_job(job, "w1", moc(60)), 1)
        self.assertIsNone(
            self.store.claim_job(job, "w1", moc(60)),
            "worker không được nhận lại job mà chính nó đang giữ lease")
        self.assertEqual(self.store.get_job(job.job_id).attempts, 1,
                         "một lần nhận hỏng không được đốt thêm attempts")

    def test_ban_appwrite_cung_theo_dung_luat_do(self) -> None:
        """Ban Appwrite khong chay duoc offline, nen doc dieu kien tu nguon."""
        nguon = inspect.getsource(AppwriteMetadataStore.claim_job)
        self.assertIn("if current.lease_is_live():", nguon)
        self.assertNotIn("lease_owner != worker_id", nguon,
                         "bản Appwrite vẫn còn ngoại lệ cho chính chủ lease")

    def test_bo_quet_bo_qua_job_tien_trinh_nay_dang_chay(self) -> None:
        """
        Mo phong dung tinh huong that: bo quet doc duoc mot BAN CU.

        `list_jobs_by_status` o day tra ve anh chup luc job chua co lease —
        chinh la thu Appwrite tra ve khi ban doc tre hon lan claim. Truoc khi
        sua, bo quet tin ban chup do, goi `claim_job`, duoc cap fence 2 va khoi
        dong thread thu hai.
        """
        self._lease_ngan(60)
        self.tts_cham_giay = 1.0

        job = self._job()
        fence = self.store.claim_job(job, server_main.WORKER_ID, moc(60))
        t = threading.Thread(target=server_main._run_job,
                             args=(job, "Nội dung chương.", fence),
                             name="tts-thread-goc")
        with server_main._job_lock:
            server_main._job_threads[job.job_id] = t
        t.start()
        time.sleep(0.1)

        cu = replace(self.store.get_job(job.job_id),
                     lease_expires_at=None, lease_owner=None)
        that = self.store.list_jobs_by_status

        def doc_tre(status):
            if status is JobStatus.RUNNING:
                return [cu]
            return that(status)

        self.store.list_jobs_by_status = doc_tre
        try:
            bao_cao = server_main.recover_stale_jobs(pending_min_age_seconds=0)
        finally:
            self.store.list_jobs_by_status = that
        t.join(timeout=10)

        self.assertEqual(bao_cao.get("chay_lai", 0), 0,
                         "không được khởi động thêm thread cho job đang chạy")
        self.assertEqual(len(self.lan_goi_tts), 1, "TTS chỉ được gọi một lần")
        self.assertEqual(self.store.get_job(job.job_id).attempts, 1)

    def test_ke_thua_khong_goi_tts(self) -> None:
        """Thua claim thi dung lai — khong tong hop, khong upload."""
        job = self._job()
        self.store.claim_job(job, "worker-khac", moc(60))
        server_main._run_job(job, "Nội dung chương.", None)   # tu nhan -> thua
        self.assertEqual(self.lan_goi_tts, [], "kẻ thua không được gọi TTS")
        self.assertEqual(self._so_object(), 0)


# -----------------------------------------------------------------------------
# 3. Worker dung giua chung
# -----------------------------------------------------------------------------


class WorkerDungGiuaChung(NenTest):

    def test_lease_chet_thi_job_duoc_nhan_lai_va_chay_xong(self) -> None:
        job = self._job()
        chet = self.store.claim_job(job, "worker-da-chet", moc(-5))
        self.assertEqual(chet, 1)

        moi = self.store.claim_job(self.store.get_job(job.job_id),
                                   server_main.WORKER_ID, moc(60))
        self.assertEqual(moi, 2, "worker mới phải nhận được job đã mất chủ")

        server_main._run_job(self.store.get_job(job.job_id),
                             "Nội dung chương.", moi)
        xong = self.store.get_job(job.job_id)
        self.assertIs(xong.status, JobStatus.COMPLETED)
        self.assertEqual(len(self.lan_goi_tts), 1)
        self.assertEqual(self.store.so_lan_tao_track, 1)
        self.assertEqual(self._so_object(), 1)

    def test_mat_quyen_giua_chung_thi_buong_truoc_khi_upload(self) -> None:
        """
        Nhip bi tu choi -> BUONG NGAY, khong upload, khong tao track.

        Truoc day co `lost` duoc dat nhung khong ai doc: worker da mat quyen van
        upload va van goi `create_track`, roi moi bi chan o lan ghi cuoi. Ket
        qua khong hong (khoa tat dinh) nhung do la ghi de len du lieu cua worker
        dang giu job.
        """
        self._lease_ngan(60)
        server_main.JOB_HEARTBEAT_SECONDS = 0.1
        self.tts_cham_giay = 1.0

        job = self._job()
        fence = self.store.claim_job(job, server_main.WORKER_ID, moc(60))

        t = threading.Thread(target=server_main._run_job,
                             args=(job, "Nội dung chương.", fence))
        t.start()
        time.sleep(0.2)
        # Mot worker khac cuop job: dat lai lease va attempts.
        with self.store._lock:
            self.store.jobs[job.job_id] = replace(
                self.store.jobs[job.job_id], attempts=fence + 1,
                lease_owner="worker-khac", lease_expires_at=moc(60))
        t.join(timeout=10)

        self.assertEqual(self.store.so_lan_tao_track, 0,
                         "worker đã mất quyền không được tạo track")
        self.assertEqual(self._so_object(), 0,
                         "worker đã mất quyền không được upload")
        self.assertIsNot(self.store.get_job(job.job_id).status,
                         JobStatus.FAILED,
                         "buông job không phải là job thất bại")

    def test_het_luot_thu_thi_bao_loi_ro_rang(self) -> None:
        job = self._job()
        for _ in range(server_main.JOB_MAX_ATTEMPTS):
            self.store.claim_job(self.store.get_job(job.job_id), "w", moc(-1))
        bao_cao = server_main.recover_stale_jobs(pending_min_age_seconds=0)
        self.assertEqual(bao_cao["het_luot_thu"], 1)
        cuoi = self.store.get_job(job.job_id)
        self.assertIs(cuoi.status, JobStatus.FAILED)
        self.assertEqual(cuoi.error_kind, "worker_lost")
        self.assertEqual(self.lan_goi_tts, [])


# -----------------------------------------------------------------------------
# 4. Thu lai SAU khi da upload
# -----------------------------------------------------------------------------


class ThuLaiSauUpload(NenTest):

    def test_chay_lai_sau_khi_da_upload_khong_sinh_ban_thu_hai(self) -> None:
        """
        Lan mot: tong hop, upload, tao track — roi chet truoc khi ghi
        `completed`. Lan hai phai ra dung mot object va dung mot track.
        """
        job = self._job()
        f1 = self.store.claim_job(job, "w1", moc(60))
        khoa = f"audio/{job.owner_id}/{job.chapter_id}/{job.content_hash}.mp3"
        tam = self.goc / "tam.mp3"
        tam.write_bytes(b"\x00" * 2048)
        server_main.storage.put_file(khoa, tam)
        tam.unlink()
        self.store.create_track(AudioTrack(
            chapter_id=job.chapter_id, owner_id=job.owner_id,
            voice_id=job.voice_id, object_key=khoa,
            content_hash=job.content_hash, size_bytes=2048))
        so_object_sau_lan_mot = self._so_object()

        # Worker chet o day: khong co lan ghi `completed` nao.
        with self.store._lock:
            self.store.jobs[job.job_id] = replace(
                self.store.jobs[job.job_id], lease_expires_at=moc(-1))

        f2 = self.store.claim_job(self.store.get_job(job.job_id), "w2", moc(60))
        self.assertEqual(f2, f1 + 1)
        server_main.WORKER_ID, cu = "w2", server_main.WORKER_ID
        try:
            server_main._run_job(self.store.get_job(job.job_id),
                                 "Nội dung chương.", f2)
        finally:
            server_main.WORKER_ID = cu

        xong = self.store.get_job(job.job_id)
        self.assertIs(xong.status, JobStatus.COMPLETED)
        self.assertEqual(xong.output_key, khoa,
                         "khoá object phải tất định theo content_hash")
        self.assertEqual(self._so_object(), so_object_sau_lan_mot,
                         "lần chạy lại không được sinh thêm object")
        self.assertEqual(len(self.store.track_moi), 1,
                         "chỉ được tồn tại đúng một track")

    def test_khoa_object_khong_phu_thuoc_lan_thu(self) -> None:
        """Doc thang tu nguon: khoa chi duoc dung `content_hash`."""
        nguon = inspect.getsource(server_main._run_job)
        # Chi lay dong GAN khoa, khong lay `job.output_key = output_key`.
        dong = [d for d in nguon.splitlines()
                if d.strip().startswith("output_key = ")]
        self.assertEqual(len(dong), 1, "chỉ được có đúng một chỗ dựng khoá")
        self.assertNotIn("fence", dong[0])
        self.assertNotIn("attempts", dong[0])
        self.assertNotIn("WORKER_ID", dong[0])


# -----------------------------------------------------------------------------
# 5. Khong sinh audio trung
# -----------------------------------------------------------------------------


class KhongSinhAudioTrung(NenTest):

    def test_hai_lan_chay_cho_dung_mot_track_va_mot_object(self) -> None:
        job = self._job()
        for chu in ("w1", "w2"):
            with self.store._lock:
                self.store.jobs[job.job_id] = replace(
                    self.store.jobs[job.job_id], status=JobStatus.RUNNING,
                    lease_expires_at=moc(-1))
            fence = self.store.claim_job(self.store.get_job(job.job_id),
                                         chu, moc(60))
            server_main.WORKER_ID, cu = chu, server_main.WORKER_ID
            try:
                server_main._run_job(self.store.get_job(job.job_id),
                                     "Nội dung chương.", fence)
            finally:
                server_main.WORKER_ID = cu

        self.assertEqual(len(self.lan_goi_tts), 2, "đề bài: đã chạy hai lượt")
        self.assertEqual(len(self.store.track_moi), 1,
                         "hai lượt chạy chỉ được để lại một track")
        self.assertEqual(self._so_object(), 1,
                         "hai lượt chạy chỉ được để lại một object")

    def test_tien_trinh_khong_chay_job_duoc_thi_khong_duoc_nhan_job(self) -> None:
        """
        Tien trinh web o staging (`FAS_INLINE_WORKER=false`) khong duoc nhan job.

        Nhan ma khong chay la vua dot mot luot `attempts` vua giu lease 90 giay
        cho mot tien trinh se khong bao gio dung den — worker that phai dung
        ngoai cho het lease.
        """
        job = self._job()
        self.store.claim_job(job, "worker-da-chet", moc(-1))
        server_main._CAN_RUN_JOBS = False
        bao_cao = server_main.recover_stale_jobs(pending_min_age_seconds=0)
        self.assertEqual(bao_cao.get("khong_duoc_phep_chay"), 1)
        self.assertEqual(self.store.get_job(job.job_id).attempts, 1,
                         "tiến trình không chạy job được đã đốt mất một attempt")

    def test_web_khong_danh_hong_mot_job_van_con_luot_thu(self) -> None:
        """
        Job ket nhung con luot thu KHONG duoc danh `failed` boi tien trinh web.

        Cai bay nam o cau truc `if/elif`: nhanh `if` con hoi `_CAN_RUN_JOBS`,
        nen neu nhanh `elif` chi kiem tra `is_stale` thi tren tien trinh web moi
        job ket deu roi thang vao do — ke ca job moi thu mot lan, von se duoc
        worker nhan lai trong vong vai giay.
        """
        job = self._job()
        self.store.claim_job(job, "worker-da-chet", moc(-1))   # attempts=1, ket
        self.assertLess(1, server_main.JOB_MAX_ATTEMPTS)

        server_main._CAN_RUN_JOBS = False
        # Chinh than cua route nam o `_tao_job_cho_chuong` (route la lop vo
        # mong) — va do la CUNG mot ham ma duong nhap chuong hang loat goi.
        nguon = inspect.getsource(server_main._tao_job_cho_chuong)
        elif_dong = [d for d in nguon.splitlines()
                     if d.strip().startswith("elif existing.is_stale")]
        self.assertEqual(len(elif_dong), 1)
        self.assertIn("JOB_MAX_ATTEMPTS", elif_dong[0],
                      "nhánh đánh hỏng phải tự kiểm tra điều kiện hết lượt thử")
        self.assertIs(self.store.get_job(job.job_id).status, JobStatus.RUNNING)

    def test_duong_tao_job_cung_hoi_truoc_khi_nhan(self) -> None:
        """Doc thang tu nguon `_tao_job_cho_chuong` (chinh than cua route tao
        job): dieu kien phai co `_CAN_RUN_JOBS`."""
        nguon = inspect.getsource(server_main._tao_job_cho_chuong)
        truoc_claim = nguon[:nguon.index("_claim_stale_job(existing)")]
        self.assertIn("_CAN_RUN_JOBS", truoc_claim,
                      "route tạo job vẫn nhận job dù không chạy được nó")


if __name__ == "__main__":
    unittest.main()
