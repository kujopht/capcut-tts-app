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
from server.youtube_websub import (  # noqa: E402
    MAX_NOTIFICATION_BYTES, WebSubError, compute_signature,
)


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


class FakeWebSubClient:
    def __init__(self, *, subscribe_fails=False):
        self.subscribe_calls = []
        self.unsubscribe_calls = []
        self._subscribe_fails = subscribe_fails

    def subscribe(self, *, channel_id, callback_url, secret, lease_seconds=432000):
        self.subscribe_calls.append(
            {"channel_id": channel_id, "callback_url": callback_url, "secret": secret})
        if self._subscribe_fails:
            raise WebSubError("Hub từ chối yêu cầu (HTTP 500).")

    def unsubscribe(self, *, channel_id, callback_url):
        self.unsubscribe_calls.append({"channel_id": channel_id, "callback_url": callback_url})


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
        self._trusted_source_store_cu = main.trusted_source_store
        self._trusted_sources_cu = main.trusted_sources
        main.trusted_source_store = MockTrustedSourceStore()
        main.trusted_sources = TrustedSourceService(
            main.trusted_source_store, main.animation_store, main.store,
            youtube_api_key="fake-key",
            websub_callback_base_url="https://api.fanfic.world")

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
        # Khoi phuc singleton toan cuc `main.trusted_sources`/
        # `main.trusted_source_store` — thieu buoc nay lam
        # `youtube_api_key="fake-key"` RO RI sang cac file test KHAC chay
        # SAU trong CUNG tien trinh (vd `test_admin.py` doc lai
        # `youtube_data_api_configured` qua chinh singleton nay va thay
        # "da cau hinh" gia, phat hien khi chay chung mot lenh unittest).
        main.trusted_source_store = self._trusted_source_store_cu
        main.trusted_sources = self._trusted_sources_cu

    def _nguoi(self, email: str, ten: str):
        ho_so = main.identity.register(email, "MatKhau123", ten)
        token = main.identity.login(email, "MatKhau123")
        return ho_so, {"Authorization": f"Bearer {token}"}

    def _dat_client_gia(self, client: FakeYouTubeClient):
        main.trusted_sources._youtube = lambda: client

    def _dat_websub_gia(self, client: FakeWebSubClient):
        main.trusted_sources._websub = lambda: client

    def _tao_nguon_kenh(self, *, cid: str, headers=None, **kwargs) -> dict:
        body = {"source_type": "youtube_channel", "youtube_channel_id": cid,
               "display_name": "Kênh test"}
        body.update(kwargs)
        return self.client.post(
            "/api/admin/animation/sources", headers=headers or self.tk_admin,
            json=body).json()["source"]


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

    def test_discover_tao_series_moi_va_backfill(self):
        """Auto-Ingestion Phase 1 qua tang HTTP — seed khong khop series nao
        (chua co mapping) -> tao series/mapping moi, quet kenh cua seed, tra
        ve dung hinh dang `SeriesDiscoveryResult.to_dict()`."""
        cid = "UC" + "z" * 22
        source = self.client.post(
            "/api/admin/animation/sources", headers=self.tk_admin,
            json={"source_type": "youtube_video", "youtube_video_id": "vidHttp0001",
                 "display_name": "Seed HTTP", "auto_import": True,
                 "minimum_confidence": 0.1}).json()["source"]

        upload_playlist = "UUzzz"
        seed_id = "vidHttp0001"
        self._dat_client_gia(FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh Z",
                                       thumbnail_url="",
                                       uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: (
                [{"contentDetails": {"videoId": seed_id}}], "")},
            videos={seed_id: VideoInfo(
                video_id=seed_id, title="Reincarnation no Kaben Tập 1",
                channel_id=cid, channel_title="Kenh Z", thumbnail_url="",
                published_at="", duration_seconds=100.0)},
        ))

        resp = self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/discover",
            headers=self.tk_admin, json={"youtube_video_id": seed_id})
        self.assertEqual(resp.status_code, 200)
        result = resp.json()["result"]
        self.assertFalse(result["resolution"]["matched"])
        self.assertTrue(result["created_new_series"])
        self.assertTrue(result["series_id"])
        self.assertIn(seed_id, result["confident_imports"])
        self.assertEqual(result["candidates_scanned"], 1)

    def test_discover_nguon_khong_ton_tai_404(self):
        resp = self.client.post(
            "/api/admin/animation/sources/khong_ton_tai/discover",
            headers=self.tk_admin, json={"youtube_video_id": "vidAbc0000001"})
        self.assertEqual(resp.status_code, 404)

    def test_discover_nguoi_thuong_bi_tu_choi_403(self):
        cid = "UC" + "y" * 22
        source = self._tao_nguon_kenh(cid=cid)
        resp = self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/discover",
            headers=self.tk_an, json={"youtube_video_id": "vidAbc0000001"})
        self.assertEqual(resp.status_code, 403)

    def test_discover_khong_dang_nhap_bi_tu_choi_401(self):
        cid = "UC" + "x" * 22
        source = self._tao_nguon_kenh(cid=cid)
        resp = self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/discover",
            json={"youtube_video_id": "vidAbc0000001"})
        self.assertEqual(resp.status_code, 401)

    def test_discover_channel_gom_nhieu_series_qua_http(self):
        """Auto-Ingestion Phase 5 qua tang HTTP — mot kenh co HAI series khac
        nhau, khong seed nao ca, tra ve dung hinh dang
        `ChannelDiscoveryResult.to_dict()`."""
        cid = "UC" + "w" * 22
        source = self._tao_nguon_kenh(
            cid=cid, auto_import=True, minimum_confidence=0.1)
        upload_playlist = "UUwww"
        v1, v2 = "vidW0000001", "vidW0000002"
        self._dat_client_gia(FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh W",
                                       thumbnail_url="",
                                       uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: (
                [{"contentDetails": {"videoId": v1}},
                 {"contentDetails": {"videoId": v2}}], "")},
            videos={
                v1: VideoInfo(video_id=v1, title="Tiên Nghịch Tập 1", channel_id=cid,
                             channel_title="Kenh W", thumbnail_url="",
                             published_at="2026-01-01", duration_seconds=100.0),
                v2: VideoInfo(video_id=v2, title="Đấu Phá Thương Khung Tập 1",
                             channel_id=cid, channel_title="Kenh W", thumbnail_url="",
                             published_at="2026-01-02", duration_seconds=100.0),
            },
        ))

        resp = self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/discover-channel",
            headers=self.tk_admin, json={})
        self.assertEqual(resp.status_code, 200)
        result = resp.json()["result"]
        self.assertEqual(result["videos_discovered"], 2)
        self.assertEqual(result["candidate_groups"], 2)
        self.assertEqual(result["new_series_created"], 2)
        self.assertIn(v1, result["confident_imports"])
        self.assertIn(v2, result["confident_imports"])

    def test_discover_channel_nguon_video_don_tra_400(self):
        source = self.client.post(
            "/api/admin/animation/sources", headers=self.tk_admin,
            json={"source_type": "youtube_video", "youtube_video_id": "vidSolo0001",
                 "display_name": "Video đơn"}).json()["source"]
        resp = self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/discover-channel",
            headers=self.tk_admin, json={})
        self.assertEqual(resp.status_code, 400)

    def test_discover_channel_nguon_khong_ton_tai_404(self):
        resp = self.client.post(
            "/api/admin/animation/sources/khong_ton_tai/discover-channel",
            headers=self.tk_admin, json={})
        self.assertEqual(resp.status_code, 404)

    def test_discover_channel_nguoi_thuong_bi_tu_choi_403(self):
        cid = "UC" + "v" * 22
        source = self._tao_nguon_kenh(cid=cid)
        resp = self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/discover-channel",
            headers=self.tk_an, json={})
        self.assertEqual(resp.status_code, 403)

    def test_discover_channel_khong_dang_nhap_bi_tu_choi_401(self):
        cid = "UC" + "u" * 22
        source = self._tao_nguon_kenh(cid=cid)
        resp = self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/discover-channel",
            json={})
        self.assertEqual(resp.status_code, 401)

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

    # -- nhap hang loat (bulk import) ----------------------------------------

    def _quet_hai_video(self, cid: str, v1: str, v2: str) -> list:
        """Tao mot nguon, quet HAI video (chua gan series -> ca hai deu
        PENDING), tra ve danh sach import that vua tao (thu tu KHONG dam
        bao — sap xep theo youtube_video_id de test on dinh)."""
        upload_playlist = f"UU{cid[-4:]}"
        self._dat_client_gia(FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh bulk",
                                       thumbnail_url="",
                                       uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: (
                [{"contentDetails": {"videoId": v1}},
                 {"contentDetails": {"videoId": v2}}], "")},
            videos={
                v1: VideoInfo(video_id=v1, title="Video A", channel_id=cid,
                              channel_title="Kenh bulk", thumbnail_url="",
                              published_at="", duration_seconds=100.0),
                v2: VideoInfo(video_id=v2, title="Video B", channel_id=cid,
                              channel_title="Kenh bulk", thumbnail_url="",
                              published_at="", duration_seconds=100.0),
            },
        ))
        source = self.client.post(
            "/api/admin/animation/sources", headers=self.tk_admin,
            json={"source_type": "youtube_channel", "youtube_channel_id": cid,
                 "display_name": "Kenh bulk"}).json()["source"]
        self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/scan",
            headers=self.tk_admin, json={})
        rows = self.client.get(
            "/api/admin/animation/imports", headers=self.tk_admin,
            params={"trusted_source_id": source["source_id"]},
        ).json()["imports"]
        return sorted(rows, key=lambda r: r["youtube_video_id"])

    def test_bulk_import_thanh_cong_ca_lo(self):
        v1, v2 = "vidBULK00001", "vidBULK00002"
        rows = self._quet_hai_video("UC" + "u" * 22, v1, v2)
        for i, row in enumerate(rows, start=1):
            self.client.patch(
                f"/api/admin/animation/imports/{row['import_id']}/series",
                headers=self.tk_admin,
                json={"series_id": self.series.series_id, "episode_number": 10 + i})

        resp = self.client.post(
            "/api/admin/animation/imports/bulk-import", headers=self.tk_admin,
            json={"items": [
                {"import_id": rows[0]["import_id"], "publish": True},
                {"import_id": rows[1]["import_id"], "publish": False},
            ]})
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["ok"] for r in results))
        self.assertEqual(results[0]["import"]["status"], "imported")
        self.assertEqual(results[1]["import"]["status"], "imported")

    def test_bulk_import_loi_mot_item_khong_lam_hong_ca_lo(self):
        """Mot item CHUA gan series (thieu dieu kien nhap) khong duoc lam
        that bai item CON LAI trong cung mot lo — day la yeu cau cot loi cua
        bulk import: loi cua rieng mot video khong pha hong toan bo lo."""
        v1, v2 = "vidBULK00003", "vidBULK00004"
        rows = self._quet_hai_video("UC" + "v" * 22, v1, v2)
        # Chi gan series cho ĐÚNG MỘT trong hai — con lai CO Y de trong.
        self.client.patch(
            f"/api/admin/animation/imports/{rows[0]['import_id']}/series",
            headers=self.tk_admin,
            json={"series_id": self.series.series_id, "episode_number": 20})

        resp = self.client.post(
            "/api/admin/animation/imports/bulk-import", headers=self.tk_admin,
            json={"items": [
                {"import_id": rows[0]["import_id"], "publish": False},
                {"import_id": rows[1]["import_id"], "publish": False},
            ]})
        self.assertEqual(resp.status_code, 200,
                          "lỗi của MỘT item không được làm cả request 400")
        results = resp.json()["results"]
        theo_id = {r["import_id"]: r for r in results}
        self.assertTrue(theo_id[rows[0]["import_id"]]["ok"])
        self.assertFalse(theo_id[rows[1]["import_id"]]["ok"])
        self.assertIn("series", theo_id[rows[1]["import_id"]]["error"].lower())

        # Item THANH CONG that su tao ra mot episode that.
        updated = self.client.get(
            "/api/admin/animation/imports", headers=self.tk_admin,
            params={"trusted_source_id": rows[0]["trusted_source_id"]},
        ).json()["imports"]
        theo_id_2 = {r["import_id"]: r for r in updated}
        self.assertEqual(theo_id_2[rows[0]["import_id"]]["status"], "imported")
        self.assertEqual(theo_id_2[rows[1]["import_id"]]["status"], "new")

    def test_bulk_import_lap_lai_cung_lo_khong_tao_trung(self):
        """Goi lai DUNG batch da nhap thanh cong lan truoc — idempotent:
        khong nem loi, khong tao episode thu hai, tra ve status=duplicate."""
        v1, v2 = "vidBULK00005", "vidBULK00006"
        rows = self._quet_hai_video("UC" + "w" * 22, v1, v2)
        for i, row in enumerate(rows, start=1):
            self.client.patch(
                f"/api/admin/animation/imports/{row['import_id']}/series",
                headers=self.tk_admin,
                json={"series_id": self.series.series_id, "episode_number": 30 + i})
        items = [{"import_id": r["import_id"], "publish": False} for r in rows]

        resp1 = self.client.post(
            "/api/admin/animation/imports/bulk-import", headers=self.tk_admin,
            json={"items": items})
        self.assertEqual(resp1.status_code, 200)
        self.assertTrue(all(r["ok"] for r in resp1.json()["results"]))

        so_tap_truoc = len(self.client.get(
            f"/api/admin/animation/series/{self.series.series_id}", headers=self.tk_admin
        ).json()["episodes"])

        resp2 = self.client.post(
            "/api/admin/animation/imports/bulk-import", headers=self.tk_admin,
            json={"items": items})
        self.assertEqual(resp2.status_code, 200)
        for r in resp2.json()["results"]:
            self.assertTrue(r["ok"])
            self.assertEqual(r["import"]["status"], "duplicate")

        so_tap_sau = len(self.client.get(
            f"/api/admin/animation/series/{self.series.series_id}", headers=self.tk_admin
        ).json()["episodes"])
        self.assertEqual(so_tap_truoc, so_tap_sau, "không được tạo tập nào thêm")

    def test_bulk_import_rong_tra_400(self):
        resp = self.client.post(
            "/api/admin/animation/imports/bulk-import", headers=self.tk_admin,
            json={"items": []})
        self.assertEqual(resp.status_code, 400)

    def test_bulk_import_qua_gioi_han_tra_400(self):
        items = [{"import_id": f"vimp_{i}", "publish": False} for i in range(51)]
        resp = self.client.post(
            "/api/admin/animation/imports/bulk-import", headers=self.tk_admin,
            json={"items": items})
        self.assertEqual(resp.status_code, 400)

    def test_bulk_import_anon_401_nguoi_thuong_403_kiem_duyet_403(self):
        body = {"items": [{"import_id": "vimp_khong_ton_tai", "publish": False}]}
        self.assertEqual(
            self.client.post("/api/admin/animation/imports/bulk-import", json=body)
            .status_code, 401)
        self.assertEqual(
            self.client.post("/api/admin/animation/imports/bulk-import",
                             headers=self.tk_an, json=body).status_code, 403)
        self.assertEqual(
            self.client.post("/api/admin/animation/imports/bulk-import",
                             headers=self.tk_kt, json=body).status_code, 403)

    def test_khong_cau_hinh_key_tra_503(self):
        main.trusted_sources._youtube_api_key = ""
        resp = self.client.post(
            "/api/admin/animation/sources/preview", headers=self.tk_admin,
            json={"url": "UC" + "z" * 22})
        self.assertEqual(resp.status_code, 503)
        main.trusted_sources._youtube_api_key = "fake-key"


class WebSubRoutesTest(Nen):
    """Phase 6 — dang ky/huy dang ky/doi chieu (quan tri) + hai route callback
    CONG KHAI (`/api/youtube/websub`)."""

    def test_kiem_duyet_khong_dang_ky_duoc(self):
        cid = "UC" + "e" * 22
        source = self._tao_nguon_kenh(cid=cid)
        resp = self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/subscribe",
            headers=self.tk_kt, json={})
        self.assertEqual(resp.status_code, 403)

    def test_admin_dang_ky_thanh_cong(self):
        cid = "UC" + "f" * 22
        source = self._tao_nguon_kenh(cid=cid)
        self._dat_websub_gia(FakeWebSubClient())
        resp = self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/subscribe",
            headers=self.tk_admin, json={})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["source"]["subscription_status"], "pending")
        self.assertNotIn("websub_secret", resp.json()["source"])

    def test_chua_cau_hinh_callback_tra_503(self):
        cid = "UC" + "g" * 22
        source = self._tao_nguon_kenh(cid=cid)
        main.trusted_sources._websub_callback_base_url = ""
        resp = self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/subscribe",
            headers=self.tk_admin, json={})
        self.assertEqual(resp.status_code, 503)
        main.trusted_sources._websub_callback_base_url = "https://api.fanfic.world"

    def test_admin_huy_dang_ky(self):
        cid = "UC" + "h" * 22
        source = self._tao_nguon_kenh(cid=cid)
        self._dat_websub_gia(FakeWebSubClient())
        self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/subscribe",
            headers=self.tk_admin, json={})
        resp = self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/unsubscribe",
            headers=self.tk_admin, json={})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["source"]["subscription_status"], "none")

    def test_admin_chay_doi_chieu(self):
        cid = "UC" + "i" * 22
        self._tao_nguon_kenh(cid=cid, auto_discover=True)
        self._dat_client_gia(FakeYouTubeClient())
        resp = self.client.post(
            "/api/admin/animation/reconciliation/run", headers=self.tk_admin, json={})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("sources_checked", resp.json())

    def test_kiem_duyet_khong_chay_duoc_doi_chieu(self):
        resp = self.client.post(
            "/api/admin/animation/reconciliation/run", headers=self.tk_kt, json={})
        self.assertEqual(resp.status_code, 403)

    # -- callback cong khai ---------------------------------------------------

    def test_xac_minh_nguon_khong_ton_tai_tra_404(self):
        resp = self.client.get(
            "/api/youtube/websub",
            params={"source_id": "khong_ton_tai", "hub.mode": "subscribe",
                   "hub.topic": "x", "hub.challenge": "abc", "hub.lease_seconds": "1"})
        self.assertEqual(resp.status_code, 404)

    def test_xac_minh_echo_challenge_nguyen_ven(self):
        cid = "UC" + "j" * 22
        source = self._tao_nguon_kenh(cid=cid)
        topic = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
        resp = self.client.get(
            "/api/youtube/websub",
            params={"source_id": source["source_id"], "hub.mode": "subscribe",
                   "hub.topic": topic, "hub.challenge": "thu-thach-xyz",
                   "hub.lease_seconds": "432000"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.text, "thu-thach-xyz")
        self.assertEqual(resp.headers.get("x-content-type-options"), "nosniff")

    def test_thong_bao_nguon_khong_ton_tai_tra_404(self):
        resp = self.client.post(
            "/api/youtube/websub", params={"source_id": "khong_ton_tai"},
            content=b"<feed/>")
        self.assertEqual(resp.status_code, 404)

    def test_thong_bao_qua_lon_bi_chan_413_du_khong_co_content_length_dung(self):
        """
        Route nay CONG KHAI khong qua Depends nao — ke tan cong co the gia
        mao/bo qua header `Content-Length` (hoac dung chunked encoding) hi
        vong bo qua kiem tra kich thuoc. Doc than theo tung khoi qua
        `request.stream()` phai chan duoc DU trong truong hop do, khong chi
        khi header co dung.
        """
        cid = "UC" + "m" * 22
        source = self._tao_nguon_kenh(cid=cid)
        qua_lon = b"x" * (MAX_NOTIFICATION_BYTES + 1)
        resp = self.client.post(
            "/api/youtube/websub", params={"source_id": source["source_id"]},
            content=qua_lon)
        self.assertEqual(resp.status_code, 413)

    def test_thong_bao_khong_co_chu_ky_van_tra_200(self):
        cid = "UC" + "k" * 22
        source = self._tao_nguon_kenh(cid=cid)
        self._dat_websub_gia(FakeWebSubClient())
        self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/subscribe",
            headers=self.tk_admin, json={})
        resp = self.client.post(
            "/api/youtube/websub", params={"source_id": source["source_id"]},
            content=b"<feed/>")
        # Dac ta WebSub: ma thanh cong CHI co nghia DA NHAN — chu ky sai/
        # thieu van tra 200, xu ly/tu choi noi bo (xem nhat ky kiem duyet).
        self.assertEqual(resp.status_code, 200)

    def test_thong_bao_dung_chu_ky_xu_ly_thanh_cong(self):
        cid = "UC" + "l" * 22
        source = self._tao_nguon_kenh(cid=cid, auto_discover=True, auto_import=True,
                                      minimum_confidence=0.1)
        self._dat_websub_gia(FakeWebSubClient())
        self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/subscribe",
            headers=self.tk_admin, json={})
        secret = main.trusted_source_store.get_source(source["source_id"]).websub_secret

        self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/mappings",
            headers=self.tk_admin,
            json={"animation_series_id": self.series.series_id,
                 "aliases": ["tiên nghịch"]})

        vid = "vidR0000001"
        self._dat_client_gia(FakeYouTubeClient(videos={
            vid: VideoInfo(video_id=vid, title="Tiên Nghịch Tập 3", channel_id=cid,
                          channel_title="Kênh test", thumbnail_url="", published_at="",
                          duration_seconds=10.0)}))

        body = f"""<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
                         xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <yt:videoId>{vid}</yt:videoId>
            <yt:channelId>{cid}</yt:channelId>
            <title>Tiên Nghịch Tập 3</title>
          </entry>
        </feed>""".encode("utf-8")
        sig = compute_signature(secret, body)
        resp = self.client.post(
            "/api/youtube/websub", params={"source_id": source["source_id"]},
            content=body, headers={"X-Hub-Signature": sig})
        self.assertEqual(resp.status_code, 200)

        hang_doi = self.client.get(
            "/api/admin/animation/imports", headers=self.tk_admin).json()["imports"]
        self.assertEqual(len(hang_doi), 1)
        self.assertEqual(hang_doi[0]["status"], "auto_imported")

    def test_he_thong_khong_bao_healthy_khi_websub_chua_tung_xac_minh(self):
        """
        Trang He thong: "đã cấu hình URL callback" KHÔNG chứng minh hub đã
        từng xác minh gì — chỉ là một biến môi trường. Trước khi có nguồn
        nào đạt `ACTIVE` (qua GET xác minh thật từ hub), mục `youtube_websub`
        phải là `degraded` (đã cấu hình nhưng CHƯA chứng minh), không phải
        `healthy`. Sau khi MỘT nguồn đạt `ACTIVE`, mới thành `healthy`.
        """
        cid = "UC" + "n" * 22
        source = self._tao_nguon_kenh(cid=cid)
        self._dat_websub_gia(FakeWebSubClient())
        self.client.post(
            f"/api/admin/animation/sources/{source['source_id']}/subscribe",
            headers=self.tk_admin, json={})

        # Da dang ky (status "pending") nhung hub CHUA tung goi lai xac
        # minh — van phai la degraded, khong phai healthy.
        d = self.client.get("/api/admin/overview", headers=self.tk_admin).json()
        self.assertTrue(d["system"]["youtube_websub_configured"])
        self.assertEqual(d["system"]["statuses"]["youtube_websub"], "degraded")

        # Hub goi lai GET xac minh that -> nguon thanh ACTIVE.
        topic = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
        resp = self.client.get(
            "/api/youtube/websub",
            params={"source_id": source["source_id"], "hub.mode": "subscribe",
                   "hub.topic": topic, "hub.challenge": "x", "hub.lease_seconds": "432000"})
        self.assertEqual(resp.status_code, 200)

        d = self.client.get("/api/admin/overview", headers=self.tk_admin).json()
        self.assertEqual(d["system"]["statuses"]["youtube_websub"], "healthy")


if __name__ == "__main__":
    unittest.main()
