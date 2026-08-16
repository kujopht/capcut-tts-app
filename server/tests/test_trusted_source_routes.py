"""
Tang HTTP cua Trusted Video Sources (Phase 5) — `server/main.py`.

Tang dich vu da duoc kiem ky o `test_trusted_source_service.py`. Bo nay CHI
kiem nhung thu tang HTTP quyet dinh: ma trang thai (401/403/404/400), AI la
quan tri (tu token, khong tu body), va CONG quyen dung dac ta (GET cho
MODERATOR tro len, MUTATE chi ADMIN/OWNER).
"""

from __future__ import annotations

import dataclasses
import os
import unittest

os.environ.setdefault("DATA_BACKEND", "mock")
os.environ.setdefault("STORAGE_BACKEND", "local")

from fastapi.testclient import TestClient       # noqa: E402

from server import main                          # noqa: E402
from server.animation_domain import AnimationSeries  # noqa: E402
from server.youtube_client import ChannelInfo, VideoInfo  # noqa: E402


class FakeYouTubeClient:
    def __init__(self, *, channels=None, videos=None, playlist_items=None):
        self._channels = channels or {}
        self._videos = videos or {}
        self._playlist_items = playlist_items or {}

    def get_video(self, video_id):
        return self._videos.get(video_id)

    def get_videos(self, video_ids):
        return {v: self._videos[v] for v in video_ids if v in self._videos}

    def get_channel(self, channel_id):
        return self._channels.get(channel_id)

    def get_channel_by_handle(self, handle):
        return self._channels.get(handle)

    def get_channel_by_username(self, username):
        return self._channels.get(username)

    def get_playlist(self, playlist_id):
        return None

    def list_playlist_items(self, playlist_id, *, page_token="", max_results=50):
        return self._playlist_items.get(playlist_id, ([], ""))


class Nen(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)
        from server.adapters import MockIdentityAdapter, MockMetadataStore
        from server.animation_store import MockAnimationStore
        from server.creator_service import CreatorService
        from server.social_service import SocialService
        from server.trusted_source_service import TrustedSourceService
        from server.trusted_source_store import MockTrustedSourceStore

        main.identity = MockIdentityAdapter()
        main.store = MockMetadataStore()
        main.animation_store = MockAnimationStore()
        main.social = SocialService(main.identity, main.store, main.storage,
                                    animation_store=main.animation_store)
        main.creators = CreatorService(main.identity, main.store)
        main.creators.on_decision = main.social.notify_author_decision
        main.trusted_source_store = MockTrustedSourceStore()
        main.trusted_sources = TrustedSourceService(
            main.trusted_source_store, main.animation_store, main.store,
            youtube_api_key="fake-key")

        self.an, self.tk_an = self._nguoi("an@vidu.vn", "An")
        self.kt, self.tk_kt = self._nguoi("kt@vidu.vn", "Kiểm duyệt")
        self.admin, self.tk_admin = self._nguoi("admin@vidu.vn", "Quản trị")
        self.owner, self.tk_owner = self._nguoi("owner@vidu.vn", "Chủ sở hữu")

        self._cau_hinh_cu = (main.settings.admin_user_ids,
                             main.settings.owner_user_ids,
                             main.settings.moderator_user_ids)
        main.settings = dataclasses.replace(
            main.settings,
            admin_user_ids=(self.admin.user_id,),
            owner_user_ids=(self.owner.user_id,),
            moderator_user_ids=(self.kt.user_id,))

        self.series = main.animation_store.create_series(
            AnimationSeries(owner_id=self.an.user_id, title="Tiên Nghịch"))

    def tearDown(self) -> None:
        admin_ids, owner_ids, mod_ids = self._cau_hinh_cu
        main.settings = dataclasses.replace(
            main.settings, admin_user_ids=admin_ids, owner_user_ids=owner_ids,
            moderator_user_ids=mod_ids)

    def _nguoi(self, email: str, ten: str):
        ho_so = main.identity.register(email, "MatKhau123", ten)
        token = main.identity.login(email, "MatKhau123")
        return ho_so, {"Authorization": f"Bearer {token}"}

    def _dat_client_gia(self, client: FakeYouTubeClient):
        main.trusted_sources._youtube = lambda: client


class TrustedSourceRoutesTest(Nen):
    def test_anon_bi_tu_choi_401(self):
        resp = self.client.get("/api/admin/animation/sources")
        self.assertEqual(resp.status_code, 401)

    def test_nguoi_thuong_bi_tu_choi_403(self):
        resp = self.client.get("/api/admin/animation/sources", headers=self.tk_an)
        self.assertEqual(resp.status_code, 403)

    def test_kiem_duyet_duoc_xem_danh_sach(self):
        resp = self.client.get("/api/admin/animation/sources", headers=self.tk_kt)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["sources"], [])

    def test_kiem_duyet_KHONG_duoc_tao_nguon(self):
        resp = self.client.post(
            "/api/admin/animation/sources", headers=self.tk_kt,
            json={"source_type": "youtube_channel",
                 "youtube_channel_id": "UC" + "a" * 22, "display_name": "X"})
        self.assertEqual(resp.status_code, 403)

    def test_admin_tao_nguon_thanh_cong(self):
        cid = "UC" + "b" * 22
        resp = self.client.post(
            "/api/admin/animation/sources", headers=self.tk_admin,
            json={"source_type": "youtube_channel", "youtube_channel_id": cid,
                 "display_name": "Kenh B"})
        self.assertEqual(resp.status_code, 200)
        source = resp.json()["source"]
        self.assertEqual(source["youtube_channel_id"], cid)
        self.assertEqual(source["created_by"], self.admin.user_id)

    def test_owner_cung_tao_duoc_nguon(self):
        cid = "UC" + "c" * 22
        resp = self.client.post(
            "/api/admin/animation/sources", headers=self.tk_owner,
            json={"source_type": "youtube_channel", "youtube_channel_id": cid,
                 "display_name": "Kenh C"})
        self.assertEqual(resp.status_code, 200)

    def test_tao_nguon_trung_lap_tra_400(self):
        cid = "UC" + "d" * 22
        body = {"source_type": "youtube_channel", "youtube_channel_id": cid,
               "display_name": "Kenh D"}
        self.client.post("/api/admin/animation/sources", headers=self.tk_admin, json=body)
        resp = self.client.post("/api/admin/animation/sources", headers=self.tk_admin, json=body)
        self.assertEqual(resp.status_code, 400)

    def test_chi_tiet_nguon_khong_ton_tai_404(self):
        resp = self.client.get(
            "/api/admin/animation/sources/khong_ton_tai", headers=self.tk_admin)
        self.assertEqual(resp.status_code, 404)

    def test_luong_tao_sua_tat_xoa_nguon(self):
        cid = "UC" + "e" * 22
        source = self.client.post(
            "/api/admin/animation/sources", headers=self.tk_admin,
            json={"source_type": "youtube_channel", "youtube_channel_id": cid,
                 "display_name": "Kenh E"}).json()["source"]
        sid = source["source_id"]

        resp = self.client.patch(
            f"/api/admin/animation/sources/{sid}", headers=self.tk_admin,
            json={"display_name": "Kenh E moi"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["source"]["display_name"], "Kenh E moi")

        resp = self.client.patch(
            f"/api/admin/animation/sources/{sid}", headers=self.tk_admin, json={})
        self.assertEqual(resp.status_code, 400)

        resp = self.client.post(
            f"/api/admin/animation/sources/{sid}/enabled", headers=self.tk_admin,
            json={"enabled": False})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["source"]["enabled"])

        resp = self.client.delete(
            f"/api/admin/animation/sources/{sid}", headers=self.tk_admin)
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(
            f"/api/admin/animation/sources/{sid}", headers=self.tk_admin)
        self.assertEqual(resp.status_code, 404)

    def test_preview_url_tra_ve_thong_tin(self):
        cid = "UC" + "f" * 22
        self._dat_client_gia(FakeYouTubeClient(channels={
            cid: ChannelInfo(channel_id=cid, title="Kenh F", thumbnail_url="",
                             uploads_playlist_id="UUfff"),
        }))
        resp = self.client.post(
            "/api/admin/animation/sources/preview", headers=self.tk_admin,
            json={"url": f"https://youtube.com/channel/{cid}"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["youtube_channel_id"], cid)

    def test_preview_url_khong_doc_duoc_tra_400(self):
        self._dat_client_gia(FakeYouTubeClient())
        resp = self.client.post(
            "/api/admin/animation/sources/preview", headers=self.tk_admin,
            json={"url": "khong phai url"})
        self.assertEqual(resp.status_code, 400)

    def test_mapping_them_sua_xoa(self):
        cid = "UC" + "g" * 22
        source = self.client.post(
            "/api/admin/animation/sources", headers=self.tk_admin,
            json={"source_type": "youtube_channel", "youtube_channel_id": cid,
                 "display_name": "Kenh G"}).json()["source"]

        resp = self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/mappings",
            headers=self.tk_admin,
            json={"animation_series_id": self.series.series_id,
                 "aliases": ["tien nghich"]})
        self.assertEqual(resp.status_code, 200)
        mapping = resp.json()["mapping"]

        resp = self.client.patch(
            f"/api/admin/animation/mappings/{mapping['mapping_id']}",
            headers=self.tk_admin, json={"auto_import": True})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["mapping"]["auto_import"])

        resp = self.client.delete(
            f"/api/admin/animation/mappings/{mapping['mapping_id']}",
            headers=self.tk_admin)
        self.assertEqual(resp.status_code, 200)

    def test_mapping_series_khong_ton_tai_tra_400(self):
        cid = "UC" + "h" * 22
        source = self.client.post(
            "/api/admin/animation/sources", headers=self.tk_admin,
            json={"source_type": "youtube_channel", "youtube_channel_id": cid,
                 "display_name": "Kenh H"}).json()["source"]
        resp = self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/mappings",
            headers=self.tk_admin,
            json={"animation_series_id": "khong_ton_tai", "aliases": ["x"]})
        self.assertEqual(resp.status_code, 400)

    def test_quet_va_hang_doi_nhap(self):
        cid = "UC" + "i" * 22
        source = self.client.post(
            "/api/admin/animation/sources", headers=self.tk_admin,
            json={"source_type": "youtube_channel", "youtube_channel_id": cid,
                 "display_name": "Kenh I", "auto_import": True,
                 "minimum_confidence": 0.1}).json()["source"]
        self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/mappings",
            headers=self.tk_admin,
            json={"animation_series_id": self.series.series_id,
                 "aliases": ["tien nghich"]})

        upload_playlist = "UUiii"
        video_id = "vidZ0000001"
        self._dat_client_gia(FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh I",
                                       thumbnail_url="",
                                       uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: (
                [{"contentDetails": {"videoId": video_id}}], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Tiên Nghịch Tập 3", channel_id=cid,
                channel_title="Kenh I", thumbnail_url="", published_at="",
                duration_seconds=100.0)},
        ))
        resp = self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/scan",
            headers=self.tk_admin, json={})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["auto_imported"], 1)

        resp = self.client.get("/api/admin/animation/imports", headers=self.tk_kt)
        self.assertEqual(resp.status_code, 200)
        imports = resp.json()["imports"]
        self.assertEqual(len(imports), 1)
        self.assertEqual(imports[0]["status"], "auto_imported")

    def test_reject_va_ignore_import(self):
        cid = "UC" + "j" * 22
        source = self.client.post(
            "/api/admin/animation/sources", headers=self.tk_admin,
            json={"source_type": "youtube_channel", "youtube_channel_id": cid,
                 "display_name": "Kenh J"}).json()["source"]
        upload_playlist = "UUjjj"
        video_id = "vidZ0000002"
        self._dat_client_gia(FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh J",
                                       thumbnail_url="",
                                       uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: (
                [{"contentDetails": {"videoId": video_id}}], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Video la", channel_id=cid,
                channel_title="Kenh J", thumbnail_url="", published_at="",
                duration_seconds=100.0)},
        ))
        self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/scan",
            headers=self.tk_admin, json={})
        row = self.client.get(
            "/api/admin/animation/imports", headers=self.tk_admin
        ).json()["imports"][0]

        resp = self.client.post(
            f"/api/admin/animation/imports/{row['import_id']}/reject",
            headers=self.tk_admin, json={"reason": "sai series"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["import"]["status"], "rejected")

    def test_import_thieu_series_tra_400(self):
        cid = "UC" + "k" * 22
        source = self.client.post(
            "/api/admin/animation/sources", headers=self.tk_admin,
            json={"source_type": "youtube_channel", "youtube_channel_id": cid,
                 "display_name": "Kenh K"}).json()["source"]
        upload_playlist = "UUkkk"
        video_id = "vidZ0000003"
        self._dat_client_gia(FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh K",
                                       thumbnail_url="",
                                       uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: (
                [{"contentDetails": {"videoId": video_id}}], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Video la", channel_id=cid,
                channel_title="Kenh K", thumbnail_url="", published_at="",
                duration_seconds=100.0)},
        ))
        self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/scan",
            headers=self.tk_admin, json={})
        row = self.client.get(
            "/api/admin/animation/imports", headers=self.tk_admin
        ).json()["imports"][0]

        resp = self.client.post(
            f"/api/admin/animation/imports/{row['import_id']}/import",
            headers=self.tk_admin, json={"publish": False})
        self.assertEqual(resp.status_code, 400)

        resp = self.client.patch(
            f"/api/admin/animation/imports/{row['import_id']}/series",
            headers=self.tk_admin,
            json={"series_id": self.series.series_id, "episode_number": 4})
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post(
            f"/api/admin/animation/imports/{row['import_id']}/import",
            headers=self.tk_admin, json={"publish": True})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["import"]["status"], "imported")

    def test_khong_cau_hinh_key_tra_503(self):
        main.trusted_sources._youtube_api_key = ""
        resp = self.client.post(
            "/api/admin/animation/sources/preview", headers=self.tk_admin,
            json={"url": "UC" + "z" * 22})
        self.assertEqual(resp.status_code, 503)
        main.trusted_sources._youtube_api_key = "fake-key"


if __name__ == "__main__":
    unittest.main()
