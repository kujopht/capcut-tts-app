"""
Hai tran bao ve may worker truoc khi mo cho nguoi ngoai.

Truoc vong nay he thong khong co gioi han nao o MAY CHU:

  * `/studio` co rao 20.000 ky tu, nhung do la rao O TRINH DUYET. Goi thang
    `POST /api/chapters` la di qua, va trang `/write` khong co rao nao ca. Tran
    duy nhat la cot `content` cua Appwrite — 1.000.000 ky tu, tuc 525 doan, tuc
    vai tieng CPU tren may worker cho MOT lan bam nut.
  * Khong co gi chan mot nguoi xep hang muoi chuong lien tiep. Concurrency
    Piper la 1 va no chay tren dung mot may, nen hang doi cua mot nguoi la thoi
    gian cho cua tat ca nhung nguoi con lai.

Ca hai tran deu doi duoc bang bien moi truong: `FAS_MAX_CHAPTER_CHARS` va
`FAS_MAX_ACTIVE_JOBS`.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server import main as server_main
from server import tts_bridge
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.domain import JobStatus, TtsJob
from server.tests.voice_stub import dung_registry_gia


class Nen(unittest.TestCase):
    def setUp(self) -> None:
        dung_registry_gia(self)
        server_main.identity = MockIdentityAdapter()
        self.store = MockMetadataStore()
        server_main.store = self.store
        self._storage = server_main.storage
        server_main.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self._synth = tts_bridge.synthesize_chapter
        # Khong goi TTS that: bo test nay do RAO CHAN, khong do pipeline.
        tts_bridge.synthesize_chapter = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("không được gọi TTS trong bộ test này"))

        # Tien trinh nay KHONG chay job — dung hinh dang cua staging, va la
        # dieu kien de tran co y nghia: job phai NAM LAI o `pending` thi moi co
        # cai gi de dem. De mac dinh (inline_worker=True) thi moi job chay ngay
        # trong thread nen roi ket thuc, hang doi luon rong va tran khong bao
        # gio cham toi.
        self._chay_duoc = server_main._CAN_RUN_JOBS
        server_main._CAN_RUN_JOBS = False
        self.client = TestClient(server_main.app)
        self.tok = self.client.post(
            "/api/auth/register",
            json={"email": "chu@example.com", "password": "matkhau123"},
        ).json()["token"]
        self.head = {"Authorization": f"Bearer {self.tok}"}
        self.nid = self.client.post("/api/novels", json={"title": "T"},
                                    headers=self.head).json()["novel"]["novel_id"]

    def tearDown(self) -> None:
        server_main.storage = self._storage
        tts_bridge.synthesize_chapter = self._synth
        server_main._CAN_RUN_JOBS = self._chay_duoc

    def _tao_chuong(self, noi_dung: str, thu_tu: int = 1):
        return self.client.post(
            "/api/chapters",
            json={"novel_id": self.nid, "title": "C", "content": noi_dung,
                  "order_index": thu_tu},
            headers=self.head)


class DoDaiChuong(Nen):

    def test_chuong_dai_vua_phai_van_duoc_nhan(self) -> None:
        r = self._tao_chuong("x" * (server_main.MAX_CHAPTER_CHARS - 1))
        self.assertEqual(r.status_code, 201, r.text[:200])

    def test_dung_tran_van_duoc_nhan(self) -> None:
        r = self._tao_chuong("x" * server_main.MAX_CHAPTER_CHARS)
        self.assertEqual(r.status_code, 201, r.text[:200])

    def test_vuot_tran_bi_tu_choi(self) -> None:
        r = self._tao_chuong("x" * (server_main.MAX_CHAPTER_CHARS + 1))
        self.assertEqual(r.status_code, 422, r.text[:200])

    def test_khong_co_chuong_nao_duoc_luu_khi_bi_tu_choi(self) -> None:
        self._tao_chuong("x" * (server_main.MAX_CHAPTER_CHARS + 1))
        r = self.client.get(f"/api/novels/{self.nid}", headers=self.head)
        self.assertEqual(r.json()["chapters"], [])

    def test_khong_lach_duoc_bang_PATCH(self) -> None:
        """
        Chan luc tao ma khong chan luc sua thi chi la mot buoc vong.

        Tao chuong ngan roi PATCH mot trieu ky tu vao la di qua.
        """
        cid = self._tao_chuong("ngắn").json()["chapter"]["chapter_id"]
        r = self.client.patch(
            f"/api/chapters/{cid}",
            json={"content": "x" * (server_main.MAX_CHAPTER_CHARS + 1)},
            headers=self.head)
        self.assertEqual(r.status_code, 422, r.text[:200])

        # Ban ghi cu KHONG duoc hong sau mot lan sua bi tu choi.
        sau = self.client.get(f"/api/chapters/{cid}", headers=self.head).json()
        self.assertEqual(sau["chapter"]["content"], "ngắn")

    def test_tran_thap_hon_han_tran_cung_cua_appwrite(self) -> None:
        # Cot `content` cua Appwrite la 1.000.000 ky tu. Tran ung dung phai nam
        # DUOI han do, neu khong thi Appwrite tu choi ca document va nguoi dung
        # nhan mot loi 500 kho hieu thay vi mot thong bao doc duoc.
        self.assertLess(server_main.MAX_CHAPTER_CHARS, 1_000_000)

    def test_doi_duoc_bang_bien_moi_truong(self) -> None:
        import inspect

        nguon = inspect.getsource(server_main)
        self.assertIn('os.environ.get("FAS_MAX_CHAPTER_CHARS"', nguon)

    def test_giao_dien_va_may_chu_noi_CUNG_mot_con_so(self) -> None:
        """
        `web/src/lib/limits.ts` chep lai tran de bao truoc cho nguoi dung.

        Hai con so trong hai ngon ngu khac nhau se troi khoi nhau neu khong ai
        giu. Hau qua khong on ao: giao dien noi "còn chỗ", nguoi dung go tiep,
        roi mat ba nghin chu vao mot loi 422 — hoac nguoc lai, giao dien chan
        som mot noi dung ma may chu san sang nhan.
        """
        import re

        duong = (Path(__file__).resolve().parents[2]
                 / "web" / "src" / "lib" / "limits.ts")
        self.assertTrue(duong.is_file(), "thiếu web/src/lib/limits.ts")
        khop = re.search(r"MAX_CHAPTER_CHARS\s*=\s*(\d+)",
                         duong.read_text(encoding="utf-8"))
        self.assertIsNotNone(khop, "không đọc được MAX_CHAPTER_CHARS ở giao diện")
        self.assertEqual(
            int(khop.group(1)), server_main.MAX_CHAPTER_CHARS,
            "giới hạn ở giao diện và ở máy chủ đã lệch nhau")


class TranSoJobXepHang(Nen):

    def _chuong(self, i: int) -> str:
        return self._tao_chuong(f"Nội dung chương số {i}.",
                                thu_tu=i).json()["chapter"]["chapter_id"]

    def _job(self, cid: str):
        return self.client.post("/api/jobs",
                                json={"chapter_id": cid, "voice_id": "mock:v1"},
                                headers=self.head)

    def test_duoi_tran_thi_tao_duoc(self) -> None:
        for i in range(server_main.MAX_ACTIVE_JOBS):
            r = self._job(self._chuong(i + 1))
            self.assertEqual(r.status_code, 201, r.text[:200])

    def test_vuot_tran_bi_tu_choi_429(self) -> None:
        for i in range(server_main.MAX_ACTIVE_JOBS):
            self._job(self._chuong(i + 1))
        r = self._job(self._chuong(99))
        self.assertEqual(r.status_code, 429, r.text[:200])
        # Thong bao phai noi ro dang co bao nhieu va tran la bao nhieu.
        self.assertIn(str(server_main.MAX_ACTIVE_JOBS), r.json()["detail"])

    def test_job_da_ket_thuc_khong_tinh_vao_tran(self) -> None:
        """Tran dem viec DANG CHO, khong dem lich su."""
        ids = [self._chuong(i + 1) for i in range(server_main.MAX_ACTIVE_JOBS)]
        for cid in ids:
            self._job(cid)
        # Dua tat ca ve `completed` — hang doi nay trong.
        with self.store._lock:
            for jid, j in list(self.store.jobs.items()):
                from dataclasses import replace

                self.store.jobs[jid] = replace(j, status=JobStatus.COMPLETED)
        r = self._job(self._chuong(99))
        self.assertEqual(r.status_code, 201, r.text[:200])

    def test_tran_KHONG_chan_duong_dung_lai_job_cu(self) -> None:
        """
        Cung noi dung + giong -> tra lai job da co. Nhanh do khong tao them
        viec cho worker nao, nen chan no chi lam nguoi dung khong xem lai duoc
        audio da co.
        """
        cid = self._chuong(1)
        dau = self._job(cid)
        self.assertEqual(dau.status_code, 201)
        for i in range(2, server_main.MAX_ACTIVE_JOBS + 1):
            self._job(self._chuong(i))
        # Da day hang doi. Hoi lai CHINH job dau tien:
        lai = self._job(cid)
        self.assertEqual(lai.status_code, 201, lai.text[:200])
        self.assertTrue(lai.json()["reused"])
        self.assertEqual(lai.json()["job"]["job_id"],
                         dau.json()["job"]["job_id"])

    def test_tran_tinh_theo_TUNG_NGUOI(self) -> None:
        for i in range(server_main.MAX_ACTIVE_JOBS):
            self._job(self._chuong(i + 1))

        tok_b = self.client.post(
            "/api/auth/register",
            json={"email": "nguoikhac@example.com", "password": "matkhau123"},
        ).json()["token"]
        head_b = {"Authorization": f"Bearer {tok_b}"}
        nid_b = self.client.post("/api/novels", json={"title": "B"},
                                 headers=head_b).json()["novel"]["novel_id"]
        cid_b = self.client.post(
            "/api/chapters",
            json={"novel_id": nid_b, "title": "C", "content": "Nội dung.",
                  "order_index": 1}, headers=head_b).json()["chapter"]["chapter_id"]
        r = self.client.post("/api/jobs",
                             json={"chapter_id": cid_b, "voice_id": "mock:v1"},
                             headers=head_b)
        self.assertEqual(r.status_code, 201,
                         "hàng đợi của người này không được chặn người khác")

    def test_doi_duoc_bang_bien_moi_truong(self) -> None:
        import inspect

        self.assertIn('os.environ.get("FAS_MAX_ACTIVE_JOBS"',
                      inspect.getsource(server_main))


if __name__ == "__main__":
    unittest.main()
