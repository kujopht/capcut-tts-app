"""
Regression cho cac loi do luot E2E day du phat hien ra.

Moi test o day bat nguon tu mot hien tuong quan sat duoc khi chay that, khong
phai tu suy doan. Docstring ghi lai buoc tai hien.
"""

from __future__ import annotations

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
    KHONG phai loi, nhung phai khoa lai hanh vi: giong khong ton tai lam job
    THAT BAI voi `voice_not_found`, TUYET DOI khong tu doi sang giong khac.

    Da xac minh tren backend that: job `failed`, `error_kind='voice_not_found'`,
    `voice_id` giu nguyen, khong sinh audio.
    """

    def test_a_missing_voice_fails_the_job_without_substituting(self):
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
        self.assertIn(r.status_code, (200, 201, 202), r.text[:200])
        job_id = r.json()["job"]["job_id"]

        # Job chay o thread nen. Doi CHINH thread do ket thuc — khong sleep bua.
        luong = server_main._job_threads.get(job_id)
        if luong is not None:
            luong.join(timeout=30)
            self.assertFalse(luong.is_alive(), "job treo qua lau")

        sau = self.client.get(f"/api/jobs/{job_id}", headers=self.head).json()["job"]
        self.assertEqual(sau["status"], "failed")
        self.assertEqual(sau["error_kind"], "voice_not_found")
        self.assertEqual(sau["voice_id"], "khong:ton-tai",
                         "khong duoc thay bang giong khac")
        self.assertIsNone(sau["output_key"])

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
