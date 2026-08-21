"""
Phu de dong bo sinh tu chinh van ban TTS — V4, Phan 2F-2I (overnight Phase 2).

Ba lop:
  1. `build_transcript()` — ham thuan, khong cham API/kho.
  2. Duong day THAT qua `POST /api/jobs` -> `_run_job` -> track co
     `transcript_key`, va `GET /api/chapters/{id}/transcript` doc lai dung.
  3. Vong doi: xoa chuong keo theo xoa sidecar; audio cu (khong co khoa) tra
     trung thuc `available: false`.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from server import main as server_main
from server import tts_bridge
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.domain import AudioTrack
from server.tests.voice_stub import dung_registry_gia
from server.transcript import TranscriptBuildError, build_transcript
import unittest
from unittest import mock


class BuildTranscriptTest(unittest.TestCase):
    """Ham thuan — khong cham API/kho."""

    def test_mot_phan_mot_cau(self):
        ra = build_transcript(
            ["Xin chào thế giới."], [3.0],
            chapter_id="c1", track_id="t1", source_content_hash="h1")
        self.assertEqual(ra["version"], 1)
        self.assertEqual(ra["chapter_id"], "c1")
        self.assertEqual(ra["duration_ms"], 3000)
        self.assertEqual(len(ra["segments"]), 1)
        self.assertEqual(ra["segments"][0]["text"], "Xin chào thế giới.")
        self.assertEqual(ra["segments"][0]["start_ms"], 0)
        self.assertEqual(ra["segments"][0]["end_ms"], 3000)
        self.assertEqual(ra["timing_quality"], "part_exact_sentence_estimated")

    def test_nhieu_cau_trong_mot_phan_phan_bo_ty_le_theo_ky_tu(self):
        # Hai cau dai bang nhau -> chia doi thoi luong.
        ra = build_transcript(
            ["Câu một ở đây. Câu hai ở đây."], [10.0],
            chapter_id="c1", track_id="t1", source_content_hash="h1")
        self.assertEqual(len(ra["segments"]), 2)
        # Doan CUOI luon lay tron phan con lai — tong khop CHINH XAC voi
        # thoi luong that, khong lech do lam tron.
        self.assertEqual(ra["segments"][-1]["end_ms"], 10000)
        self.assertEqual(ra["duration_ms"], 10000)

    def test_nhieu_phan_cong_don_dung_thoi_diem(self):
        ra = build_transcript(
            ["Phần một.", "Phần hai."], [4.0, 6.0],
            chapter_id="c1", track_id="t1", source_content_hash="h1")
        self.assertEqual(ra["duration_ms"], 10000)
        # Doan cua PHAN HAI phai bat dau tu moc 4000ms (het phan mot), khong
        # phai tu 0 — day chinh la diem de sai neu cong don lam sai.
        cac_doan_phan_hai = [s for s in ra["segments"] if s["start_ms"] >= 4000]
        self.assertTrue(cac_doan_phan_hai)
        self.assertEqual(cac_doan_phan_hai[0]["start_ms"], 4000)
        self.assertEqual(ra["segments"][-1]["end_ms"], 10000)

    def test_do_dai_khong_khop_nem_loi(self):
        with self.assertRaises(TranscriptBuildError):
            build_transcript(["a", "b"], [1.0], chapter_id="c", track_id="t",
                             source_content_hash="h")

    def test_phan_rong_khong_sinh_doan_nhung_van_cong_thoi_luong(self):
        ra = build_transcript(["   ", "Có nội dung."], [2.0, 3.0],
                              chapter_id="c", track_id="t", source_content_hash="h")
        self.assertEqual(ra["duration_ms"], 5000)
        # Phan rong khong dong gop doan nao, nhung thoi luong cua no van duoc
        # cong don dung — doan cua phan hai phai bat dau tu 2000ms.
        self.assertEqual(ra["segments"][0]["start_ms"], 2000)


class TranscriptPipelineTest(unittest.TestCase):
    """Duong day THAT: job -> track co transcript_key -> route doc lai dung."""

    def setUp(self) -> None:
        dung_registry_gia(self)
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self.client = TestClient(server_main.app)
        # Ghi bytes gia — `_concat_mp3` chi can file ton tai va ghep duoc.
        tts_bridge._registry.synthesize = (
            lambda text, voice, dest, cancel=None, rate="1.0":
            __import__("pathlib").Path(dest).write_bytes(b"\x00" * 256))

    def _tao_chuong_va_job(self, content: str, chunk_chars: int = 20) -> tuple:
        r = self.client.post("/api/auth/register", json={
            "email": "transcript-qa@example.com", "password": "matkhau123"})
        head = {"Authorization": f"Bearer {r.json()['token']}"}
        novel = self.client.post("/api/novels", json={"title": "Truyện Phụ Đề"},
                                 headers=head).json()["novel"]
        chapter = self.client.post("/api/chapters", json={
            "novel_id": novel["novel_id"], "title": "Chương",
            "content": content}, headers=head).json()["chapter"]
        job = self.client.post("/api/jobs", json={
            "chapter_id": chapter["chapter_id"], "voice_id": "mock:v1",
            "chunk_chars": chunk_chars},
            headers=head).json()["job"]
        return head, chapter["chapter_id"], job["job_id"]

    def _cho_job_xong(self, head, job_id: str) -> None:
        moc = time.monotonic() + 10
        while time.monotonic() < moc:
            job = self.client.get(f"/api/jobs/{job_id}", headers=head).json()["job"]
            if job["status"] in ("completed", "failed"):
                self.assertEqual(job["status"], "completed", job)
                return
            time.sleep(0.05)
        self.fail("job không hoàn tất trong thời gian chờ")

    def test_job_hoan_tat_sinh_transcript_that(self):
        with mock.patch.object(tts_bridge, "probe_duration_seconds",
                               return_value=3.0):
            head, chapter_id, job_id = self._tao_chuong_va_job(
                "Câu một ở đây. Câu hai ở đây riêng biệt hẳn.", chunk_chars=20)
            self._cho_job_xong(head, job_id)

        track = server_main.store.track_for_chapter(chapter_id)
        self.assertTrue(track.transcript_key, "track phải có transcript_key")
        self.assertEqual(track.transcript_version, 1)
        self.assertTrue(track.source_content_hash)

        resp = self.client.get(f"/api/chapters/{chapter_id}/transcript",
                               headers=head)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["available"])
        self.assertGreater(body["duration_ms"], 0)
        self.assertGreater(len(body["segments"]), 0)
        self.assertEqual(body["chapter_id"], chapter_id)

    def test_ffprobe_khong_do_duoc_mot_phan_thi_khong_co_transcript(self):
        """
        Trung thuc: MOT phan khong do duoc -> KHONG dung transcript nao ca,
        thay vi dung mot timeline nua vo nua khong.

        Gia lap THANG `synthesize_chapter` (cung ky thuat voi `_synth_gia` o
        `test_track_duration.py`) thay vi di qua chunk_text that: gioi han
        chunk_chars co san `MIN_CHUNK_CHARS` (~200) nen mot van ban ngan
        trong test khong the tach thanh nhieu phan that qua duong do — cach
        nay kiem dung logic can kiem (mot phan `None` -> bo qua ca transcript)
        ma khong phu thuoc do dai van ban gia lap duoc bao nhieu phan.
        """
        cu = tts_bridge.synthesize_chapter

        def gia(text, voice_id, dest, rate="1.0", chunk_chars=2000,
               on_progress=None, cancel=None):
            from pathlib import Path
            Path(dest).write_bytes(b"\x00" * 256)
            return {
                "size_bytes": 256, "total_parts": 2,
                "duration_seconds": 8.0, "voice_id": voice_id,
                "provider": "mock",
                "chunks": ["Phần một.", "Phần hai."],
                "part_durations_seconds": [3.0, None],
            }

        tts_bridge.synthesize_chapter = gia
        self.addCleanup(setattr, tts_bridge, "synthesize_chapter", cu)

        head, chapter_id, job_id = self._tao_chuong_va_job("Nội dung bất kỳ.")
        self._cho_job_xong(head, job_id)

        track = server_main.store.track_for_chapter(chapter_id)
        self.assertEqual(track.transcript_key, "")
        self.assertEqual(track.transcript_version, 0)

        resp = self.client.get(f"/api/chapters/{chapter_id}/transcript",
                               headers=head)
        self.assertFalse(resp.json()["available"])

    def test_audio_cu_khong_co_transcript_tra_trung_thuc(self):
        """Audio tao TRUOC khi tinh nang nay ton tai — track khong co
        transcript_key. Route phai tra `available: false`, KHONG bia."""
        r = self.client.post("/api/auth/register", json={
            "email": "audio-cu-qa@example.com", "password": "matkhau123"})
        head = {"Authorization": f"Bearer {r.json()['token']}"}
        novel = self.client.post("/api/novels", json={"title": "Truyện Cũ"},
                                 headers=head).json()["novel"]
        chapter = self.client.post("/api/chapters", json={
            "novel_id": novel["novel_id"], "title": "C1",
            "content": "Nội dung."}, headers=head).json()["chapter"]
        server_main.store.create_track(AudioTrack(
            chapter_id=chapter["chapter_id"], owner_id="u-cu", voice_id="v",
            object_key="k", content_hash="h", duration_seconds=10.0))

        resp = self.client.get(f"/api/chapters/{chapter['chapter_id']}/transcript",
                               headers=head)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["available"])

    def test_chuong_khong_ton_tai_tra_404(self):
        resp = self.client.get("/api/chapters/khong-ton-tai/transcript")
        self.assertEqual(resp.status_code, 404)

    def test_truyen_nhap_nguoi_khac_khong_doc_duoc_transcript(self):
        with mock.patch.object(tts_bridge, "probe_duration_seconds",
                               return_value=3.0):
            head, chapter_id, job_id = self._tao_chuong_va_job(
                "Nội dung chương nháp.", chunk_chars=20)
            self._cho_job_xong(head, job_id)

        # Nguoi khac, chua dang nhap — truyen van con la ban nhap.
        resp = self.client.get(f"/api/chapters/{chapter_id}/transcript")
        self.assertEqual(resp.status_code, 404)


class PurgeDeletesTranscriptSidecarTest(unittest.TestCase):
    def setUp(self) -> None:
        dung_registry_gia(self)
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self.client = TestClient(server_main.app)
        tts_bridge._registry.synthesize = (
            lambda text, voice, dest, cancel=None, rate="1.0":
            __import__("pathlib").Path(dest).write_bytes(b"\x00" * 256))

    def test_xoa_chuong_xoa_ca_sidecar_transcript(self):
        with mock.patch.object(tts_bridge, "probe_duration_seconds",
                               return_value=3.0):
            r = self.client.post("/api/auth/register", json={
                "email": "purge-qa@example.com", "password": "matkhau123"})
            head = {"Authorization": f"Bearer {r.json()['token']}"}
            novel = self.client.post("/api/novels", json={"title": "Xoá QA"},
                                     headers=head).json()["novel"]
            chapter = self.client.post("/api/chapters", json={
                "novel_id": novel["novel_id"], "title": "C1",
                "content": "Nội dung để xoá."}, headers=head).json()["chapter"]
            job = self.client.post("/api/jobs", json={
                "chapter_id": chapter["chapter_id"], "voice_id": "mock:v1"},
                headers=head).json()["job"]
            moc = time.monotonic() + 10
            while time.monotonic() < moc:
                st = self.client.get(f"/api/jobs/{job['job_id']}",
                                     headers=head).json()["job"]["status"]
                if st in ("completed", "failed"):
                    break
                time.sleep(0.05)

        track = server_main.store.track_for_chapter(chapter["chapter_id"])
        self.assertTrue(track.transcript_key)
        self.assertTrue(server_main.storage.exists(track.transcript_key))

        del_resp = self.client.delete(f"/api/chapters/{chapter['chapter_id']}",
                                      headers=head)
        self.assertEqual(del_resp.status_code, 200)
        self.assertFalse(server_main.storage.exists(track.transcript_key))


if __name__ == "__main__":
    unittest.main()
