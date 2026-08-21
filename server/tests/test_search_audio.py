"""V4 visual completion, vong 2, Phan F/11 — `GET /api/search/audio`."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.domain import AudioTrack, Chapter, Novel, PublishState


class SearchAudioTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self.client = TestClient(server_main.app)


class SearchAudioTest(SearchAudioTestCase):
    def test_duoi_hai_ky_tu_tra_rong(self):
        resp = self.client.get("/api/search/audio", params={"q": "a"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["novels"], [])

    def test_truyen_khong_audio_khong_xuat_hien(self):
        server_main.store.create_novel(Novel(
            owner_id="u1", title="Không Có Âm Thanh", state=PublishState.PUBLISHED))
        body = self.client.get("/api/search/audio", params={"q": "Âm Thanh"}).json()
        self.assertEqual(body["novels"], [])

    def test_truyen_co_audio_xuat_hien(self):
        novel = server_main.store.create_novel(Novel(
            owner_id="u1", title="One Piece Fanfic", state=PublishState.PUBLISHED))
        chapter = server_main.store.create_chapter(Chapter(
            novel_id=novel.novel_id, owner_id="u1", title="Tập 1"))
        server_main.store.create_track(AudioTrack(
            chapter_id=chapter.chapter_id, owner_id="u1", voice_id="v",
            object_key="k", content_hash="h", duration_seconds=60.0))

        body = self.client.get("/api/search/audio", params={"q": "One Piece"}).json()
        self.assertEqual(len(body["novels"]), 1)
        self.assertEqual(body["novels"][0]["novel_id"], novel.novel_id)
        self.assertEqual(body["novels"][0]["audio_chapter_count"], 1)

    def test_truyen_nhap_khong_xuat_hien_du_co_audio(self):
        novel = server_main.store.create_novel(Novel(
            owner_id="u1", title="Truyện Nháp Có Audio", state=PublishState.DRAFT))
        chapter = server_main.store.create_chapter(Chapter(
            novel_id=novel.novel_id, owner_id="u1", title="C1"))
        server_main.store.create_track(AudioTrack(
            chapter_id=chapter.chapter_id, owner_id="u1", voice_id="v",
            object_key="k", content_hash="h", duration_seconds=60.0))

        body = self.client.get("/api/search/audio", params={"q": "Nháp"}).json()
        self.assertEqual(body["novels"], [])

    def test_khong_can_dang_nhap(self):
        resp = self.client.get("/api/search/audio", params={"q": "gi do"})
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
