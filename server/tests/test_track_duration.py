"""
Thoi luong audio THAT phai duoc do (ffprobe) va luu vao `audio_tracks`.

Vi sao co bo test nay: production tung sinh track voi `duration_seconds=0`
— khong ai do thoi luong o diem hoan tat job. Hau qua khong nam o track ma o
moi phep kiem dua tren thoi luong: moc binh luan audio lui ve tran du phong
12 gio thay vi do dai that, va luot-nghe-hop-le khong co mau so.

Hai bat bien duoc ghim:
  1. Do DUOC thi ket qua tong hop mang thoi luong that, va track luu dung no.
  2. KHONG do duoc thi job van hoan tat, track van sinh ra voi 0 — thieu
     thoi luong khong bao gio duoc lam hong mot ban audio da tong hop xong.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict
from unittest import mock

from fastapi.testclient import TestClient

from server import main as server_main
from server import tts_bridge
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.domain import JobStatus
from server.tests.voice_stub import dung_registry_gia


class CauTtsDoThoiLuongTest(unittest.TestCase):
    """`synthesize_chapter` phai do thoi luong file vua ghep."""

    def setUp(self) -> None:
        dung_registry_gia(self)
        # Registry gia cua bo test khong biet tong hop — day cho no mot ban
        # ghi vai byte ra dest, du de duong ghep/doi ten chay that.
        tts_bridge._registry.synthesize = (
            lambda text, voice, dest, cancel=None, rate="1.0":
            Path(dest).write_bytes(b"\x00" * 128))

    def test_do_duoc_thi_ket_qua_mang_thoi_luong_that(self):
        with TemporaryDirectory() as tmp, \
             mock.patch.object(tts_bridge, "probe_duration_seconds",
                               return_value=7.5) as do:
            ket = tts_bridge.synthesize_chapter(
                text="xin chào thế giới", voice_id="mock:v1",
                dest=Path(tmp) / "ra.mp3")
        self.assertEqual(ket["duration_seconds"], 7.5)
        # Do tren file KET QUA (da ghep), khong phai tren part trung gian.
        do.assert_called_once_with(Path(tmp) / "ra.mp3")

    def test_khong_do_duoc_thi_none_va_khong_nem(self):
        with TemporaryDirectory() as tmp, \
             mock.patch.object(tts_bridge, "probe_duration_seconds",
                               return_value=None):
            ket = tts_bridge.synthesize_chapter(
                text="xin chào", voice_id="mock:v1",
                dest=Path(tmp) / "ra.mp3")
        self.assertIsNone(ket["duration_seconds"])
        self.assertGreater(ket["size_bytes"], 0)


def _synth_gia(duration: Any):
    """Ban gia lap `synthesize_chapter` voi thoi luong tuy chon."""

    def _chay(text, voice_id, dest, rate="1.0", chunk_chars=2000,
              on_progress=None, cancel=None) -> Dict[str, Any]:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00" * 2048)
        if on_progress:
            on_progress(1, 1)
        ket = {"size_bytes": 2048, "total_parts": 1,
               "voice_id": voice_id, "provider": "mock"}
        if duration != "vang_mat":
            ket["duration_seconds"] = duration
        return ket

    return _chay


class TrackLuuThoiLuongTest(unittest.TestCase):
    """Diem hoan tat job (`_run_job`) phai chuyen thoi luong vao track."""

    def setUp(self) -> None:
        dung_registry_gia(self)
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self._synth_cu = tts_bridge.synthesize_chapter
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        tts_bridge.synthesize_chapter = self._synth_cu

    def _job_xong(self, duration) -> str:
        tts_bridge.synthesize_chapter = _synth_gia(duration)
        r = self.client.post("/api/auth/register", json={
            "email": "duration@example.com", "password": "matkhau123"})
        head = {"Authorization": f"Bearer {r.json()['token']}"}
        novel = self.client.post("/api/novels", json={"title": "Đo thời lượng"},
                                 headers=head).json()["novel"]
        chapter = self.client.post("/api/chapters", json={
            "novel_id": novel["novel_id"], "title": "Chương",
            "content": "Nội dung."}, headers=head).json()["chapter"]
        job_id = self.client.post("/api/jobs", json={
            "chapter_id": chapter["chapter_id"], "voice_id": "mock:v1"},
            headers=head).json()["job"]["job_id"]
        import time
        moc = time.monotonic() + 10
        while time.monotonic() < moc:
            job = self.client.get(f"/api/jobs/{job_id}",
                                  headers=head).json()["job"]
            if job["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)
        self.assertEqual(job["status"], JobStatus.COMPLETED.value)
        return chapter["chapter_id"]

    def test_thoi_luong_that_duoc_luu_vao_track(self):
        chapter_id = self._job_xong(12.5)
        track = server_main.store.track_for_chapter(chapter_id)
        self.assertEqual(track.duration_seconds, 12.5)

    def test_khong_do_duoc_van_hoan_tat_voi_0(self):
        """None -> 0, job van completed: thieu thoi luong khong hong track."""
        chapter_id = self._job_xong(None)
        track = server_main.store.track_for_chapter(chapter_id)
        self.assertEqual(track.duration_seconds, 0.0)

    def test_ban_tong_hop_cu_khong_co_khoa_van_chay(self):
        """Ket qua kieu cu (thieu han khoa) — track 0, khong KeyError."""
        chapter_id = self._job_xong("vang_mat")
        track = server_main.store.track_for_chapter(chapter_id)
        self.assertEqual(track.duration_seconds, 0.0)


class KhongKeoGuiTest(unittest.TestCase):
    def test_duong_do_thoi_luong_khong_keo_pyside(self):
        """
        `tts_bridge` gio import `desktop_app.output_manager` (noi o cua
        `probe_duration_seconds`). Ranh gioi "backend khong keo GUI" phai
        song sot qua thay doi nay.
        """
        import desktop_app.output_manager  # noqa: F401
        import server.tts_bridge  # noqa: F401

        self.assertNotIn("PySide6", sys.modules)


if __name__ == "__main__":
    unittest.main(verbosity=2)
