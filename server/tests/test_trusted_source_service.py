"""Kiem thu `TrustedSourceService` — tang dieu phoi Phase 5 (Trusted Video
Sources). Dung MOT client YouTube GIA (khong mang) de kiem soat hoan toan
du lieu tra ve, tap trung vao NGHIEP VU: quyet dinh trang thai, trung
lap/xung dot, idempotent, nhat ky kiem duyet."""

import unittest
from typing import Dict, List, Tuple
from unittest import mock

from server.adapters import MockMetadataStore
from server.animation_domain import AnimationEpisode, AnimationSeries, AnimationSource
from server.animation_store import MockAnimationStore
from server.domain import Profile, PublishState
from server.trusted_source_domain import ImportStatus, TrustedSourceType
from server.trusted_source_service import TrustedSourceError, TrustedSourceService
from server.trusted_source_store import MockTrustedSourceStore
from server.youtube_client import (
    ChannelInfo,
    PlaylistInfo,
    VideoInfo,
    YouTubeApiError,
    YouTubeConfigError,
)


class FakeYouTubeClient:
    """Thay `YouTubeClient` that — moi phuong thuc tra ve du lieu DA SAP
    SAN qua constructor, khong goi mang."""

    def __init__(self, *, channels=None, playlists=None, videos=None,
                playlist_items=None):
        self._channels: Dict[str, ChannelInfo] = channels or {}
        self._playlists: Dict[str, PlaylistInfo] = playlists or {}
        self._videos: Dict[str, VideoInfo] = videos or {}
        #: playlist_id -> (items_tho, next_token)
        self._playlist_items: Dict[str, Tuple[List[dict], str]] = playlist_items or {}

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
        return self._playlists.get(playlist_id)

    def list_playlist_items(self, playlist_id, *, page_token="", max_results=50):
        return self._playlist_items.get(playlist_id, ([], ""))


def _video_item(video_id: str) -> dict:
    return {"contentDetails": {"videoId": video_id}}


class TrustedSourceServiceTest(unittest.TestCase):
    def setUp(self):
        self.store = MockTrustedSourceStore()
        self.animation = MockAnimationStore()
        self.metadata = MockMetadataStore()
        self.svc = TrustedSourceService(
            self.store, self.animation, self.metadata, youtube_api_key="fake-key")
        self.admin = Profile(user_id="admin_1", email="admin@fanfic.world")
        self.series = self.animation.create_series(
            AnimationSeries(owner_id="author_1", title="Tiên Nghịch"))

    def _dat_client_gia(self, client: FakeYouTubeClient):
        self.svc._youtube = lambda: client  # type: ignore[method-assign]

    # -- cau hinh thieu key ---------------------------------------------------

    def test_khong_co_key_bao_loi_ro_rang(self):
        svc = TrustedSourceService(self.store, self.animation, self.metadata,
                                   youtube_api_key="")
        self.assertFalse(svc.youtube_configured())
        with self.assertRaises(YouTubeConfigError):
            svc.preview_source_url("https://youtube.com/channel/UC" + "a" * 22)

    # -- preview url ---------------------------------------------------------

    def test_preview_kenh_tu_channel_id(self):
        cid = "UC" + "a" * 22
        self._dat_client_gia(FakeYouTubeClient(channels={
            cid: ChannelInfo(channel_id=cid, title="Kenh A",
                             thumbnail_url="http://x/a.jpg",
                             uploads_playlist_id="UUaaa"),
        }))
        preview = self.svc.preview_source_url(f"https://youtube.com/channel/{cid}")
        self.assertEqual(preview["source_type"], TrustedSourceType.YOUTUBE_CHANNEL.value)
        self.assertEqual(preview["youtube_channel_id"], cid)

    def test_preview_video_tra_ve_video_id(self):
        self._dat_client_gia(FakeYouTubeClient(videos={
            "vidZ0000001": VideoInfo(
                video_id="vidZ0000001", title="Tap 1", channel_id="UC" + "b" * 22,
                channel_title="Kenh B", thumbnail_url="", published_at="",
                duration_seconds=100.0),
        }))
        preview = self.svc.preview_source_url("vidZ0000001")
        self.assertEqual(preview["source_type"], TrustedSourceType.YOUTUBE_VIDEO.value)
        self.assertEqual(preview["youtube_video_id"], "vidZ0000001")

    def test_preview_url_khong_doc_duoc_bao_loi_nghiep_vu(self):
        self._dat_client_gia(FakeYouTubeClient())
        with self.assertRaises(TrustedSourceError):
            self.svc.preview_source_url("khong phai url gi ca")

    # -- CRUD nguon ------------------------------------------------------------

    def test_tao_nguon_va_chong_trung_lap(self):
        cid = "UC" + "c" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh C")
        self.assertTrue(source["enabled"])
        with self.assertRaises(TrustedSourceError):
            self.svc.create_source(
                self.admin, source_type="youtube_channel", youtube_channel_id=cid,
                display_name="Kenh C (lai)")
        rows, _ = self.metadata.list_events(action="trusted_source_add")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].target_id, source["source_id"])

    def test_tao_nguon_direct_hls_bi_tu_choi(self):
        with self.assertRaises(TrustedSourceError):
            self.svc.create_source(
                self.admin, source_type="direct_hls", display_name="x")

    def test_danh_sach_nguon_kem_so_anh_xa(self):
        cid = "UC" + "d" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh D")
        self.svc.create_mapping(
            self.admin, source["source_id"],
            animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])
        ket_qua = self.svc.admin_list_sources()
        row = next(r for r in ket_qua["sources"] if r["source_id"] == source["source_id"])
        self.assertEqual(row["mapping_count"], 1)

    def test_danh_sach_nguon_kem_so_nhap_va_so_xuat_ban(self):
        """Cot 'Đã nhập'/'Đã xuất bản' o danh sach quan tri — MOT tap draft
        (khong tinh xuat ban) VA mot tap published (tinh CA hai)."""
        cid = "UC" + "z" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh Z", auto_import=True, minimum_confidence=0.5)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])

        upload_playlist = "UUzzz"
        v1, v2 = "vidZ0000001", "vidZ0000002"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh Z",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(v1), _video_item(v2)], "")},
            videos={
                v1: VideoInfo(video_id=v1, title="Tiên Nghịch Tập 1", channel_id=cid,
                              channel_title="Kenh Z", thumbnail_url="",
                              published_at="2026-01-01", duration_seconds=100.0),
                v2: VideoInfo(video_id=v2, title="Tiên Nghịch Tập 2", channel_id=cid,
                              channel_title="Kenh Z", thumbnail_url="",
                              published_at="2026-01-02", duration_seconds=100.0),
            },
        )
        self._dat_client_gia(client)
        # auto_import=True nhung auto_publish=False (mac dinh) -> ca hai tap
        # deu thanh AUTO_IMPORTED (draft), khong tu xuat ban.
        self.svc.scan_source(self.admin, source["source_id"])

        ket_qua = self.svc.admin_list_sources()
        row = next(r for r in ket_qua["sources"] if r["source_id"] == source["source_id"])
        self.assertEqual(row["imported_count"], 2)
        self.assertEqual(row["published_count"], 0, "cả hai tập đều là draft")

        # Xuat ban thu cong MOT trong hai tap -> published_count phai tang.
        # Ghi thang qua kho (khong qua mot route xuat ban thuc su nao — o day
        # chi can MOT tap that co state=published de kiem cot dem, tuong tu
        # cach cac test khac trong file nay thao tac truc tiep kho Mock).
        from dataclasses import replace
        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        episode = self.animation.get_episode(rows[0].created_episode_id)
        self.animation.episodes[episode.episode_id] = replace(
            episode, state=PublishState.PUBLISHED)

        ket_qua_2 = self.svc.admin_list_sources()
        row_2 = next(r for r in ket_qua_2["sources"] if r["source_id"] == source["source_id"])
        self.assertEqual(row_2["imported_count"], 2, "tổng số nhập không đổi")
        self.assertEqual(row_2["published_count"], 1, "chỉ đúng MỘT tập vừa xuất bản")

    def test_tat_bat_nguon_ghi_nhat_ky_dung_hanh_dong(self):
        cid = "UC" + "e" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh E")
        self.svc.set_source_enabled(self.admin, source["source_id"], False)
        rows, _ = self.metadata.list_events(action="trusted_source_disable")
        self.assertEqual(len(rows), 1)

    def test_xoa_nguon_xoa_ca_anh_xa(self):
        cid = "UC" + "f" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh F")
        mapping = self.svc.create_mapping(
            self.admin, source["source_id"],
            animation_series_id=self.series.series_id,
            aliases=["x"], include_keywords=[], exclude_keywords=[])
        self.svc.remove_source(self.admin, source["source_id"])
        with self.assertRaises(Exception):
            self.store.get_mapping(mapping["mapping_id"])

    # -- mapping ---------------------------------------------------------------

    def test_them_anh_xa_series_khong_ton_tai_bao_loi(self):
        cid = "UC" + "g" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh G")
        with self.assertRaises(TrustedSourceError):
            self.svc.create_mapping(
                self.admin, source["source_id"], animation_series_id="ani_khong_ton_tai",
                aliases=["x"], include_keywords=[], exclude_keywords=[])

    # -- quet: nhap tu dong khi du dieu kien -----------------------------------

    def test_quet_tu_dong_nhap_va_xuat_ban_khi_du_dieu_kien(self):
        cid = "UC" + "h" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh H", auto_import=True, auto_publish=True,
            minimum_confidence=0.5)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])

        upload_playlist = "UUhhh"
        video_id = "vidA0000001"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh H",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Tiên Nghịch Tập 12", channel_id=cid,
                channel_title="Kenh H", thumbnail_url="", published_at="2026-01-01",
                duration_seconds=1200.0)},
        )
        self._dat_client_gia(client)

        ket_qua = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(ket_qua["auto_published"], 1)
        self.assertEqual(ket_qua["detected"], 1)

        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.status, ImportStatus.AUTO_PUBLISHED)
        self.assertEqual(row.detected_episode_number, 12)
        self.assertTrue(row.created_episode_id)

        episode = self.animation.get_episode(row.created_episode_id)
        self.assertEqual(episode.state, PublishState.PUBLISHED)
        self.assertEqual(episode.external_id, video_id)

        # Quet lai — IDEMPOTENT: khong tao them tap thu hai, khong doi ban ghi.
        ket_qua_2 = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(ket_qua_2["already_tracked"], 1)
        rows_2, total_2 = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total_2, 1)

    def test_quet_video_khong_khop_alias_nao_thanh_new(self):
        cid = "UC" + "i" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh I")
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])

        upload_playlist = "UUiii"
        video_id = "vidB0000002"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh I",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Video khong lien quan", channel_id=cid,
                channel_title="Kenh I", thumbnail_url="", published_at="",
                duration_seconds=60.0)},
        )
        self._dat_client_gia(client)
        ket_qua = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(ket_qua["detected"], 1)
        self.assertEqual(ket_qua["matched"], 0)
        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(rows[0].status, ImportStatus.NEW)

    def test_quet_tu_khoa_loai_tru_thanh_ignored(self):
        cid = "UC" + "j" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh J", auto_import=True, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])

        upload_playlist = "UUjjj"
        video_id = "vidC0000003"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh J",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Tiên Nghịch Trailer Tập 3", channel_id=cid,
                channel_title="Kenh J", thumbnail_url="", published_at="",
                duration_seconds=30.0)},
        )
        self._dat_client_gia(client)
        self.svc.scan_source(self.admin, source["source_id"])
        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(rows[0].status, ImportStatus.IGNORED)

    def test_quet_video_da_la_tap_thanh_duplicate(self):
        cid = "UC" + "k" * 22
        video_id = "vidD0000004"
        # Video nay DA la mot episode that (o series khac hoac cung series).
        self.animation.create_episode(AnimationEpisode(
            series_id=self.series.series_id, owner_id="author_1", title="Cu",
            source=AnimationSource.YOUTUBE, external_id=video_id, order_index=1))

        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh K", auto_import=True, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])

        upload_playlist = "UUkkk"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh K",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Tiên Nghịch Tập 1", channel_id=cid,
                channel_title="Kenh K", thumbnail_url="", published_at="",
                duration_seconds=100.0)},
        )
        self._dat_client_gia(client)
        ket_qua = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(ket_qua["duplicates"], 1)
        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(rows[0].status, ImportStatus.DUPLICATE)

    def test_quet_trung_so_tap_thanh_conflict(self):
        cid = "UC" + "l" * 22
        # Series DA co tap so 5 (tu mot video khac).
        self.animation.create_episode(AnimationEpisode(
            series_id=self.series.series_id, owner_id="author_1", title="Cu",
            source=AnimationSource.YOUTUBE, external_id="video_khac_00", order_index=5))

        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh L", auto_import=True, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])

        upload_playlist = "UUlll"
        video_id = "vidE0000005"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh L",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Tiên Nghịch Tập 5", channel_id=cid,
                channel_title="Kenh L", thumbnail_url="", published_at="",
                duration_seconds=100.0)},
        )
        self._dat_client_gia(client)
        ket_qua = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(ket_qua["conflicts"], 1)
        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(rows[0].status, ImportStatus.CONFLICT)

    def test_quet_du_tin_cay_nhung_khong_bat_auto_import_thi_pending(self):
        cid = "UC" + "m" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh M", auto_import=False, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])

        upload_playlist = "UUmmm"
        video_id = "vidF0000006"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh M",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Tiên Nghịch Tập 9", channel_id=cid,
                channel_title="Kenh M", thumbnail_url="", published_at="",
                duration_seconds=100.0)},
        )
        self._dat_client_gia(client)
        self.svc.scan_source(self.admin, source["source_id"])
        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(rows[0].status, ImportStatus.PENDING)

    def test_quet_nguon_video_don_le(self):
        video_id = "vidG0000007"
        source = self.svc.create_source(
            self.admin, source_type="youtube_video", youtube_video_id=video_id,
            display_name="Video rieng", auto_import=True, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])
        client = FakeYouTubeClient(videos={video_id: VideoInfo(
            video_id=video_id, title="Tiên Nghịch Tập 20", channel_id="UCx",
            channel_title="Kenh X", thumbnail_url="", published_at="",
            duration_seconds=100.0)})
        self._dat_client_gia(client)
        ket_qua = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(ket_qua["detected"], 1)
        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(rows[0].status, ImportStatus.AUTO_IMPORTED)
        # Tap tu dong nhap PHAI mang theo thuoc tinh kenh nguon (dung de hien
        # "Nguồn: ..." o trang xem).
        episode = self.animation.get_episode(rows[0].created_episode_id)
        self.assertEqual(episode.source_channel_id, "UCx")
        self.assertEqual(episode.source_channel_title, "Kenh X")

    def test_quet_loi_youtube_ghi_lai_last_error(self):
        cid = "UC" + "n" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh N")
        self._dat_client_gia(FakeYouTubeClient())  # khong co kenh nao -> loi.
        with self.assertRaises(YouTubeApiError):
            self.svc.scan_source(self.admin, source["source_id"])
        updated = self.store.get_source(source["source_id"])
        self.assertTrue(updated.last_error_at)
        self.assertTrue(updated.last_error_message)

    # -- Phase 7: video khong con truy cap duoc (bi go/rieng tu) -------------

    def test_quet_nguon_video_don_le_khong_con_truy_cap_bao_loi_ro_rang(self):
        """Nguon kieu `youtube_video` (mot video DON LE) ma video do bi go/
        chuyen rieng tu truoc luc quet lai: `get_video` tra `None` ->
        `YouTubeApiError` voi thong diep RO RANG (khong am tham tra danh
        sach rong), VA `last_error_at`/`last_error_message` duoc ghi lai
        giong moi loi YouTube khac (xem `_lay_ung_vien`)."""
        video_id = "vidUNAVAIL01"
        source = self.svc.create_source(
            self.admin, source_type="youtube_video", youtube_video_id=video_id,
            display_name="Video mat tich", auto_import=True, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])
        # FakeYouTubeClient KHONG co video nay trong `videos={}` -> get_video None.
        self._dat_client_gia(FakeYouTubeClient())
        with self.assertRaises(YouTubeApiError) as ctx:
            self.svc.scan_source(self.admin, source["source_id"])
        self.assertIn("Không còn truy cập", str(ctx.exception))
        updated = self.store.get_source(source["source_id"])
        self.assertTrue(updated.last_error_at)
        self.assertTrue(updated.last_error_message)
        # KHONG tao ban ghi VideoImport rac nao ca — that bai DUNG luc lay
        # ung vien, truoc khi co gi de phan loai/luu.
        rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total, 0)

    def test_quet_kenh_bo_qua_video_rieng_tu_trong_playlist_khong_lam_sap_ca_lan_quet(self):
        """Quet mot KENH/playlist co NHIEU video, trong do MOT video da bi
        go/chuyen rieng tu (con trong danh sach playlist nhung `get_videos`
        khong tra ve thong tin no nua — dung mo phong 404/403 tu YouTube
        Data API that). Ky vong: video do bi BO QUA am tham (khong bia du
        lieu), CAC video CON LAI van duoc phan loai/nhap binh thuong — mot
        video loi KHONG duoc lam hong ca luot quet (xem `_lay_ung_vien`,
        dong "video rieng tu/da bi go — bo qua, khong bia du lieu")."""
        cid = "UC" + "p" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh P", auto_import=True, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])

        upload_playlist = "UUppp"
        video_con = "vidCONOK0001"
        video_mat = "vidMATTICH01"  # co trong playlist nhung KHONG co trong `videos=`.
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh P",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: (
                [_video_item(video_mat), _video_item(video_con)], "")},
            videos={video_con: VideoInfo(
                video_id=video_con, title="Tiên Nghịch Tập 7", channel_id=cid,
                channel_title="Kenh P", thumbnail_url="", published_at="",
                duration_seconds=100.0)},
            # `video_mat` CO CHU DICH khong co trong `videos` — mo phong
            # 404/403 luc goi `videos.list` cho ID do.
        )
        self._dat_client_gia(client)
        ket_qua = self.svc.scan_source(self.admin, source["source_id"])
        # `detected` CHI dem video CON tra cuu duoc — video mat tich khong
        # bao gio tro thanh "ung vien" ca, khong phai mot loai loi rieng.
        self.assertEqual(ket_qua["detected"], 1)
        rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total, 1)
        self.assertEqual(rows[0].youtube_video_id, video_con)
        self.assertEqual(rows[0].status, ImportStatus.AUTO_IMPORTED)
        # Lan quet KHONG bi coi la that bai — nguon van duoc ghi last_success.
        updated = self.store.get_source(source["source_id"])
        self.assertTrue(updated.last_success_at)
        self.assertFalse(updated.last_error_message)

    # -- hang doi nhap thu cong --------------------------------------------------

    def test_nhap_thu_cong_thanh_cong(self):
        cid = "UC" + "o" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh O", minimum_confidence=0.99)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])
        upload_playlist = "UUooo"
        video_id = "vidH0000008"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh O",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Tiên Nghịch Tập 30", channel_id=cid,
                channel_title="Kenh O", thumbnail_url="", published_at="",
                duration_seconds=100.0)},
        )
        self._dat_client_gia(client)
        self.svc.scan_source(self.admin, source["source_id"])
        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        pending = rows[0]
        self.assertEqual(pending.status, ImportStatus.PENDING)  # duoi nguong 0.99

        updated = self.svc.import_video(self.admin, pending.import_id, publish=True)
        self.assertEqual(updated["status"], ImportStatus.IMPORTED.value)
        self.assertTrue(updated["created_episode_id"])
        episode = self.animation.get_episode(updated["created_episode_id"])
        self.assertEqual(episode.state, PublishState.PUBLISHED)
        # Nhap THU CONG cung phai mang theo thuoc tinh kenh nguon, khong chi
        # rieng duong tu dong.
        self.assertEqual(episode.source_channel_id, cid)
        self.assertEqual(episode.source_channel_title, "Kenh O")

    def test_nhap_thu_cong_thieu_series_bao_loi(self):
        cid = "UC" + "p" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh P")
        upload_playlist = "UUppp"
        video_id = "vidI0000009"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh P",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Video la", channel_id=cid,
                channel_title="Kenh P", thumbnail_url="", published_at="",
                duration_seconds=100.0)},
        )
        self._dat_client_gia(client)
        self.svc.scan_source(self.admin, source["source_id"])
        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        new_row = rows[0]
        self.assertEqual(new_row.status, ImportStatus.NEW)
        with self.assertRaises(TrustedSourceError):
            self.svc.import_video(self.admin, new_row.import_id, publish=False)

        self.svc.set_import_series(
            self.admin, new_row.import_id, series_id=self.series.series_id,
            episode_number=7)
        updated = self.svc.import_video(self.admin, new_row.import_id, publish=False)
        self.assertEqual(updated["status"], ImportStatus.IMPORTED.value)
        episode = self.animation.get_episode(updated["created_episode_id"])
        self.assertEqual(episode.state, PublishState.DRAFT)

    def test_bulk_import_videos_loi_mot_item_khong_lam_hong_ca_lo(self):
        """`bulk_import_videos` la vo mong quanh `import_video()` — loi cua
        MOT item (`TrustedSourceError`/`NotFoundError`) phai duoc bat lai
        thanh mot ket qua `ok: False`, KHONG duoc nem ra ngoai lam hong ca
        loi goi ham (item con lai van phai thanh cong binh thuong)."""
        cid = "UC" + "r" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh R")
        upload_playlist = "UUrrr"
        v_ok, v_thieu_series = "vidR0000001", "vidR0000002"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh R",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: (
                [_video_item(v_ok), _video_item(v_thieu_series)], "")},
            videos={
                v_ok: VideoInfo(video_id=v_ok, title="Video R1", channel_id=cid,
                                channel_title="Kenh R", thumbnail_url="",
                                published_at="", duration_seconds=100.0),
                v_thieu_series: VideoInfo(
                    video_id=v_thieu_series, title="Video R2", channel_id=cid,
                    channel_title="Kenh R", thumbnail_url="", published_at="",
                    duration_seconds=100.0),
            },
        )
        self._dat_client_gia(client)
        self.svc.scan_source(self.admin, source["source_id"])
        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        theo_video = {r.youtube_video_id: r for r in rows}
        row_ok, row_loi = theo_video[v_ok], theo_video[v_thieu_series]
        self.svc.set_import_series(
            self.admin, row_ok.import_id, series_id=self.series.series_id,
            episode_number=8)
        # row_loi CO Y de trong — chua gan series, se gay TrustedSourceError.

        ket_qua = self.svc.bulk_import_videos(self.admin, [
            {"import_id": row_ok.import_id, "publish": False},
            {"import_id": row_loi.import_id, "publish": False},
            {"import_id": "khong_ton_tai", "publish": False},
        ])
        theo_id = {r["import_id"]: r for r in ket_qua["results"]}
        self.assertTrue(theo_id[row_ok.import_id]["ok"])
        self.assertEqual(theo_id[row_ok.import_id]["import"]["status"],
                         ImportStatus.IMPORTED.value)
        self.assertFalse(theo_id[row_loi.import_id]["ok"])
        self.assertTrue(theo_id[row_loi.import_id]["error"])
        self.assertFalse(theo_id["khong_ton_tai"]["ok"])

    def test_tu_choi_va_bo_qua_ghi_nhat_ky(self):
        cid = "UC" + "q" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh Q")
        upload_playlist = "UUqqq"
        video_id = "vidJ0000010"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh Q",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Video la", channel_id=cid,
                channel_title="Kenh Q", thumbnail_url="", published_at="",
                duration_seconds=100.0)},
        )
        self._dat_client_gia(client)
        self.svc.scan_source(self.admin, source["source_id"])
        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        row = rows[0]

        rejected = self.svc.reject_import(self.admin, row.import_id, reason="sai series")
        self.assertEqual(rejected["status"], ImportStatus.REJECTED.value)
        events, _ = self.metadata.list_events(action="video_reject")
        self.assertEqual(len(events), 1)

    def test_danh_sach_hang_doi_nhap_kem_ten_nguon_va_series(self):
        cid = "UC" + "r" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh R", auto_import=True, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])
        upload_playlist = "UUrrr"
        video_id = "vidK0000011"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh R",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Tiên Nghịch Tập 40", channel_id=cid,
                channel_title="Kenh R", thumbnail_url="", published_at="",
                duration_seconds=100.0)},
        )
        self._dat_client_gia(client)
        self.svc.scan_source(self.admin, source["source_id"])
        ket_qua = self.svc.admin_list_imports()
        row = ket_qua["imports"][0]
        self.assertEqual(row["source_display_name"], "Kenh R")
        self.assertEqual(row["series_title"], "Tiên Nghịch")


if __name__ == "__main__":
    unittest.main()
