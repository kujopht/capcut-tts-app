"""
Regression cho cac loi do luot E2E day du phat hien ra.

Moi test o day bat nguon tu mot hien tuong quan sat duoc khi chay that, khong
phai tu suy doan. Docstring ghi lai buoc tai hien.
"""

from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore


class Base(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self._real_storage = server_main.storage
        server_main.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.client = TestClient(server_main.app)
        self.token = self.client.post(
            "/api/auth/register",
            json={"email": "tacgia@example.com", "password": "matkhau123"},
        ).json()["token"]
        self.head = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self) -> None:
        server_main.storage = self._real_storage


class TestTitleIsTrimmedBeforeItIsMeasured(Base):
    """
    LOI — tieu de chi gom khoang trang tao ra ban ghi co tieu de RONG.

    Tai hien: `POST /api/novels {"title": "   "}` tra ve 201, va `title` doc lai
    la `""`. Trong khi `{"title": ""}` bi tu choi 422. Cung mot gia tri hieu
    dung, hai ket qua khac nhau — va thu nam trong kho la mot the trang tren
    `/fanfic` va `/write`.

    Nguyen nhan: `Field(min_length=1)` do do dai chuoi THO, con viec cat khoang
    trang xay ra sau do khi luu.
    """

    KHOANG_TRANG = ["   ", "\t", "\n", " \t\n ", " "]

    def test_a_whitespace_only_novel_title_is_refused(self):
        for gia_tri in self.KHOANG_TRANG:
            with self.subTest(gia_tri=repr(gia_tri)):
                r = self.client.post("/api/novels", json={"title": gia_tri},
                                     headers=self.head)
                self.assertEqual(r.status_code, 422, r.text[:200])

    def test_an_empty_novel_title_is_still_refused(self):
        r = self.client.post("/api/novels", json={"title": ""}, headers=self.head)
        self.assertEqual(r.status_code, 422)

    def test_no_novel_ends_up_with_a_blank_title(self):
        for gia_tri in self.KHOANG_TRANG + [""]:
            self.client.post("/api/novels", json={"title": gia_tri}, headers=self.head)
        r = self.client.get("/api/novels?mine=true", headers=self.head)
        trang = [n for n in r.json()["novels"] if not n["title"].strip()]
        self.assertEqual(trang, [], "khong duoc co truyen nao tieu de trang")

    def test_a_real_title_keeps_working_and_is_trimmed(self):
        r = self.client.post("/api/novels", json={"title": "  Hải Tặc Mũ Rơm  "},
                             headers=self.head)
        self.assertEqual(r.status_code, 201, r.text[:200])
        self.assertEqual(r.json()["novel"]["title"], "Hải Tặc Mũ Rơm",
                         "khoang trang hai ben phai bi cat")

    def test_the_same_rule_applies_to_chapter_titles(self):
        nid = self.client.post("/api/novels", json={"title": "T"},
                               headers=self.head).json()["novel"]["novel_id"]
        for gia_tri in self.KHOANG_TRANG:
            with self.subTest(gia_tri=repr(gia_tri)):
                r = self.client.post(
                    "/api/chapters",
                    json={"novel_id": nid, "title": gia_tri, "content": "N",
                          "order_index": 1},
                    headers=self.head)
                self.assertEqual(r.status_code, 422, r.text[:200])

    def test_the_same_rule_applies_when_editing(self):
        nid = self.client.post("/api/novels", json={"title": "T"},
                               headers=self.head).json()["novel"]["novel_id"]
        cid = self.client.post(
            "/api/chapters",
            json={"novel_id": nid, "title": "C", "content": "N", "order_index": 1},
            headers=self.head).json()["chapter"]["chapter_id"]
        self.assertEqual(
            self.client.patch(f"/api/novels/{nid}", json={"title": "  "},
                              headers=self.head).status_code, 422)
        self.assertEqual(
            self.client.patch(f"/api/chapters/{cid}", json={"title": "  "},
                              headers=self.head).status_code, 422)
        # Ban ghi cu khong bi hong sau mot lan sua bi tu choi.
        self.assertEqual(
            self.client.get(f"/api/novels/{nid}",
                            headers=self.head).json()["novel"]["title"], "T")

    def test_the_title_limit_is_measured_after_trimming(self):
        """200 ky tu that kem khoang trang hai ben van phai duoc nhan."""
        r = self.client.post("/api/novels", json={"title": "  " + "x" * 200 + "  "},
                             headers=self.head)
        self.assertEqual(r.status_code, 201, r.text[:200])
        r = self.client.post("/api/novels", json={"title": "x" * 201},
                             headers=self.head)
        self.assertEqual(r.status_code, 422)


class TestTheInvalidVoicePathIsSafe(Base):
    """
    Giong khong dung duoc thi TUYET DOI khong duoc thay bang giong khac.

    Y DO GIU NGUYEN, CHO CHAN DOI SOM HON. Truoc day route tao job khong he
    xem `voice_id`: job duoc ghi xuong kho, chay o thread nen, roi that bai voi
    `error_kind='voice_not_found'`. Nay pham vi giong duoc cuong che NGAY o
    route (`ensure_voice_public`), nen mot id khong dung duoc bi tu choi 400
    truoc khi co job nao ton tai.

    Ca hai deu khong doi giong. Nhung tra loi ngay tai cho la thu nguoi dung
    doc duoc, con mot job `failed` vai giay sau thi khong.
    """

    def test_a_missing_voice_is_rejected_and_creates_no_job(self):
        nid = self.client.post("/api/novels", json={"title": "T"},
                               headers=self.head).json()["novel"]["novel_id"]
        cid = self.client.post(
            "/api/chapters",
            json={"novel_id": nid, "title": "C", "content": "Nội dung.",
                  "order_index": 1},
            headers=self.head).json()["chapter"]["chapter_id"]
        r = self.client.post("/api/jobs",
                             json={"chapter_id": cid, "voice_id": "khong:ton-tai"},
                             headers=self.head)

        self.assertEqual(r.status_code, 400, r.text[:200])
        self.assertIn("khong:ton-tai", r.json()["detail"],
                      "thông báo phải nói rõ id nào bị từ chối")

        # KHONG co job nao duoc tao — va do la diem chinh. Mot job rac nam lai
        # o trang thai `failed` cho mot id bia dat la thu khong ai can.
        con_lai = self.client.get("/api/jobs", headers=self.head).json()
        self.assertEqual(con_lai["count"], 0, con_lai)

    def test_no_substitute_voice_is_ever_chosen(self):
        """Tu choi thi phai tu choi han, khong duoc lang le doi sang giong khac."""
        nguon = inspect.getsource(server_main.create_job)
        vi_tri = nguon.index("ensure_voice_public")
        # Doan ngay sau lan kiem tra: chi duoc nem HTTPException, khong duoc gan
        # lai `payload.voice_id` thanh mot giong nao khac.
        sau = nguon[vi_tri:vi_tri + 400]
        self.assertIn("HTTPException", sau)
        self.assertNotIn("voice_id =", sau)

    def test_a_chapter_with_no_content_cannot_start_a_job(self):
        nid = self.client.post("/api/novels", json={"title": "T"},
                               headers=self.head).json()["novel"]["novel_id"]
        cid = self.client.post(
            "/api/chapters",
            json={"novel_id": nid, "title": "C", "content": "", "order_index": 1},
            headers=self.head).json()["chapter"]["chapter_id"]
        r = self.client.post("/api/jobs",
                             json={"chapter_id": cid, "voice_id": "mock:v1"},
                             headers=self.head)
        self.assertEqual(r.status_code, 400, r.text[:200])
        self.assertIn("chưa có nội dung", r.json()["detail"])


class TestTheLoserCleansUpNothing(Base):
    """
    LOI — worker THUA claim don dep do cua worker THANG.

    Tai hien (tat dinh, khong dua vao timing): dat mot tep tam va mot ban ghi
    `_job_threads` nhu the worker THANG dang giu, roi cho worker THUA chay
    `_run_job` tren job co lease con han cua nguoi khac.

    Hien tuong: duong `return` khi thua claim nam TRONG `try`, nen `finally` van
    chay — no `dest.unlink()` va `_job_threads.pop(job_id)`. Worker thang sau do
    upload mot tep khong con ton tai: job thanh `failed`, khong sinh track nao.

    Do la ly do `TestOnlyOneSynthesisPerJob` do duoc tren Linux CI (0 track, job
    `failed`) trong khi tren Windows thi worker thua thoat nhanh hon nen cua so
    hep hon va thuong khong lo ra.
    """

    def a_job_owned_by_someone_else(self):
        from datetime import datetime, timedelta, timezone

        from server.domain import JobStatus, TtsJob, job_fingerprint

        con_han = (datetime.now(timezone.utc)
                   + timedelta(seconds=300)).isoformat(timespec="seconds")
        nid = self.client.post("/api/novels", json={"title": "T"},
                               headers=self.head).json()["novel"]["novel_id"]
        cid = self.client.post(
            "/api/chapters",
            json={"novel_id": nid, "title": "C", "content": "Nội dung.",
                  "order_index": 1},
            headers=self.head).json()["chapter"]["chapter_id"]
        owner = self.client.get("/api/auth/me",
                                headers=self.head).json()["profile"]["user_id"]
        return server_main.store.create_job(TtsJob(
            owner_id=owner, chapter_id=cid, voice_id="mock:v1",
            content_hash=job_fingerprint("Nội dung.", "mock:v1", "1.0", 2000),
            status=JobStatus.RUNNING, lease_expires_at=con_han,
            lease_owner="worker-thang", attempts=1))

    def test_the_loser_does_not_delete_the_winner_temp_file(self):
        import threading
        from dataclasses import replace

        job = self.a_job_owned_by_someone_else()
        # Moi ten tep tam ma worker thang co the dang dung.
        thu_muc = server_main.settings.var_dir / "tts"
        thu_muc.mkdir(parents=True, exist_ok=True)
        cua_thang = [
            thu_muc / f"{job.job_id}.mp3",
            thu_muc / f"{job.job_id}-worker-thang-1.mp3",
        ]
        for p in cua_thang:
            p.write_bytes(b"tep tam cua worker thang")

        server_main._run_job(replace(job, lease_owner=None), "Nội dung.")

        for p in cua_thang:
            self.assertTrue(p.exists(),
                            f"worker thua da xoa {p.name} cua worker thang")
            p.unlink(missing_ok=True)

    def test_the_loser_does_not_unregister_the_winner_thread(self):
        import threading
        from dataclasses import replace

        job = self.a_job_owned_by_someone_else()
        canh = threading.current_thread()
        with server_main._job_lock:
            server_main._job_threads[job.job_id] = canh
        try:
            server_main._run_job(replace(job, lease_owner=None), "Nội dung.")
            self.assertIs(server_main._job_threads.get(job.job_id), canh,
                          "worker thua da go ban ghi thread cua worker thang")
        finally:
            with server_main._job_lock:
                server_main._job_threads.pop(job.job_id, None)

    def test_the_winner_still_cleans_up_after_itself(self):
        """Sua xong khong duoc lam ro ri: nguoi thang van phai don cua minh."""
        import threading
        from dataclasses import replace

        from server.domain import JobStatus, TtsJob, job_fingerprint

        nid = self.client.post("/api/novels", json={"title": "T"},
                               headers=self.head).json()["novel"]["novel_id"]
        cid = self.client.post(
            "/api/chapters",
            json={"novel_id": nid, "title": "C", "content": "Nội dung.",
                  "order_index": 1},
            headers=self.head).json()["chapter"]["chapter_id"]
        owner = self.client.get("/api/auth/me",
                                headers=self.head).json()["profile"]["user_id"]
        job = server_main.store.create_job(TtsJob(
            owner_id=owner, chapter_id=cid, voice_id="mock:v1",
            content_hash=job_fingerprint("Nội dung.", "mock:v1", "1.0", 2000),
            status=JobStatus.PENDING, attempts=0))

        with server_main._job_lock:
            server_main._job_threads[job.job_id] = threading.current_thread()
        server_main._run_job(replace(job), "Nội dung.")

        self.assertNotIn(job.job_id, server_main._job_threads,
                         "nguoi thang phai go ban ghi cua chinh minh")
        con_lai = list((server_main.settings.var_dir / "tts").glob(
            f"{job.job_id}*"))
        self.assertEqual(con_lai, [], "nguoi thang phai xoa tep tam cua minh")

    def test_the_temp_path_is_unique_per_worker_and_attempt(self):
        import inspect

        nguon = inspect.getsource(server_main._run_job)
        self.assertIn('f"{job.job_id}-{WORKER_ID}-{fence}.mp3"', nguon,
                      "ten tep tam phai kem worker va lan thu, khong chi job_id")

    def test_the_claim_happens_before_the_try_block(self):
        import inspect

        nguon = inspect.getsource(server_main._run_job)
        vi_tri_claim = nguon.find("store.claim_job(")
        vi_tri_try = nguon.find("\n    try:")
        self.assertGreater(vi_tri_claim, 0)
        self.assertGreater(vi_tri_try, 0)
        self.assertLess(vi_tri_claim, vi_tri_try,
                        "claim phai xay ra TRUOC `try`, neu khong duong return "
                        "khi thua se di qua `finally` va don do cua nguoi khac")


class TestTheStaleTransactionClaimIsGone(unittest.TestCase):
    """
    Chu thich trong `server/main.py` tung khang dinh "Appwrite khong co
    compare-and-swap". Dieu do SAI — Appwrite Cloud 1.9.6 co transaction, va
    `claim_job` dang dung. Ghi chu sai lam nguoi doc sau nay ket luan sai.
    """

    def test_no_source_file_claims_appwrite_lacks_cas(self):
        import inspect

        from server import appwrite_store

        # Chi bat cac cau noi ve CAS/transaction. "Appwrite khong co PATCH nhieu
        # document" la mot phat bieu KHAC va van dung — khong duoc bat oan no.
        sai = (
            "appwrite khong co compare-and-swap",
            "khong co compare-and-swap",
            "khong phai cas",
            "khong ho tro transaction",
            "appwrite khong co transaction",
        )
        for mo_dun in (server_main, appwrite_store):
            thap = inspect.getsource(mo_dun).lower()
            for cau in sai:
                self.assertNotIn(cau, thap,
                                 f"{mo_dun.__name__}: ghi chu da loi thoi")

    def test_the_restart_requirement_is_written_down(self):
        import inspect

        nguon = inspect.getsource(server_main)
        self.assertIn("_supported_fields", nguon,
                      "phai ghi ro cache theo vong doi tien trinh")
        self.assertIn("RESTART", nguon.upper(),
                      "doi schema xong phai restart — phai noi ro trong ma nguon")


if __name__ == "__main__":
    unittest.main()
