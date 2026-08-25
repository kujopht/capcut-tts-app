"""Kiem thu `TrustedSourceService` — tang dieu phoi Phase 5 (Trusted Video
Sources). Dung MOT client YouTube GIA (khong mang) de kiem soat hoan toan
du lieu tra ve, tap trung vao NGHIEP VU: quyet dinh trang thai, trung
lap/xung dot, idempotent, nhat ky kiem duyet."""

import unittest
from typing import Dict, List, Tuple
from unittest import mock

from server.adapters import MockMetadataStore, NotFoundError
from server.animation_domain import AnimationEpisode, AnimationSeries, AnimationSource
from server.animation_store import MockAnimationStore
from server.domain import Novel, Profile, PublishState
from server.trusted_source_domain import ImportStatus, TrustedSourceType, VideoImport
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

    def test_quet_dai_tap_hoac_video_tong_hop_khong_bao_gio_tu_dong_nhap(self):
        """Auto-Ingestion Phase 1: mot video la DAI nhieu tap ("Tập 1-13")
        hoac ban tong hop ca series ("ALL IN ONE") KHONG duoc phep tu dong
        thanh MOT `AnimationEpisode` — du nguon bat auto_import/auto_publish
        VA do tin cay (tru phan tap) co the vuot nguong, `episode_number`
        van la `None` (xem `video_classifier.ClassificationResult`), va
        `_quyet_dinh_trang_thai` (khong doi) da coi day la PENDING."""
        cid = "UC" + "r" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh R", auto_import=True, auto_publish=True,
            minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])

        upload_playlist = "UUrrr"
        v_dai, v_tong_hop = "vidRange0001", "vidAllInOne1"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh R",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: (
                [_video_item(v_dai), _video_item(v_tong_hop)], "")},
            videos={
                v_dai: VideoInfo(
                    video_id=v_dai, title="Tiên Nghịch Tập 1-13", channel_id=cid,
                    channel_title="Kenh R", thumbnail_url="", published_at="2026-01-01",
                    duration_seconds=1200.0),
                v_tong_hop: VideoInfo(
                    video_id=v_tong_hop, title="Tiên Nghịch ALL IN ONE", channel_id=cid,
                    channel_title="Kenh R", thumbnail_url="", published_at="2026-01-02",
                    duration_seconds=36000.0),
            },
        )
        self._dat_client_gia(client)

        ket_qua = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(ket_qua["detected"], 2)
        self.assertEqual(ket_qua.get("auto_imported", 0), 0)
        self.assertEqual(ket_qua.get("auto_published", 0), 0)

        rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total, 2)
        for row in rows:
            with self.subTest(video_id=row.youtube_video_id):
                self.assertEqual(row.status, ImportStatus.PENDING)
                self.assertIsNone(row.detected_episode_number)
                self.assertFalse(row.created_episode_id)
                self.assertTrue(
                    any("không tự động nhập" in s for s in row.signals),
                    row.signals)

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

    def test_tao_mapping_keyword_roi_quet_lai_cap_nhat_import_new(self):
        """Dung luong staging: video duoc quet truoc mapping, sau do admin
        tao expected keyword va quet lai. Keyword phai song qua reload,
        matcher phai dung no, va import cu duoc cap nhat thay vi tao ban sao.
        """
        cid = "UC" + "q" * 22
        video_id = "vidKEYWORD1"
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh Keyword")
        upload_playlist = "UUqqq"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh Keyword",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Reincarnation no Kaben Tập 1",
                channel_id=cid, channel_title="Kenh Keyword", thumbnail_url="",
                published_at="", duration_seconds=1200.0)},
        )
        self._dat_client_gia(client)

        first = self.svc.scan_source(self.admin, source["source_id"])
        rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(first["matched"], 0)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0].status, ImportStatus.NEW)
        import_id = rows[0].import_id

        created = self.svc.create_mapping(
            self.admin, source["source_id"],
            animation_series_id=self.series.series_id, aliases=[],
            include_keywords=["Reincarnation no Kaben"], exclude_keywords=[])
        reloaded = self.svc.admin_source_detail(source["source_id"])["mappings"][0]
        self.assertEqual(created["include_keywords"], ["Reincarnation no Kaben"])
        self.assertEqual(reloaded["include_keywords"], ["Reincarnation no Kaben"])

        second = self.svc.scan_source(self.admin, source["source_id"])
        rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total, 1)
        self.assertEqual(rows[0].import_id, import_id)
        self.assertEqual(rows[0].detected_mapping_id, created["mapping_id"])
        self.assertEqual(rows[0].detected_series_id, self.series.series_id)
        self.assertEqual(rows[0].status, ImportStatus.PENDING)
        self.assertEqual(second["matched"], 1)
        self.assertEqual(second["pending"], 1)
        self.assertEqual(second["already_tracked"], 0)

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

    # -- Auto-Ingestion Phase 3: an toan duoi tai dua nhau (concurrency) -------

    def test_hai_video_khac_nhau_dong_thoi_trung_cho_series_episode_thanh_conflict(self):
        """Hai VIDEO KHAC NHAU cung suy ra trung (series, so tap) khi xu ly
        GAN NHU DONG THOI (vi du hai thong bao WebSub gan nhu cung luc cho
        hai video khac nhau) — snapshot `episodes_by_series` (doc TRUOC khi
        ghi) KHONG bat duoc vi ca hai deu doc thay cho con trong. Chot chan
        that su la `create_episode_once`/`episode_slot_id` tat dinh: video
        thu hai PHAI la CONFLICT, KHONG duoc ghi de tap cua video thu nhat."""
        cid = "UC" + "n" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh N", auto_import=True, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])

        src = self.store.get_source(source["source_id"])
        mappings = self.store.list_mappings(source["source_id"])
        # Snapshot RONG dung chung cho "ca hai qua trinh" — mo phong dua
        # nhau that: khong ai thay cho da bi chiem luc doc.
        episodes_by_series = {self.series.series_id: ()}
        video_a = {"video_id": "vidRaceA001", "title": "Tiên Nghịch Tập 7",
                  "channel_id": cid, "channel_title": "Kenh N", "thumbnail_url": "",
                  "published_at": "2026-01-01", "duration_seconds": 100.0}
        video_b = {"video_id": "vidRaceB002", "title": "Tiên Nghịch Tập 7",
                  "channel_id": cid, "channel_title": "Kenh N", "thumbnail_url": "",
                  "published_at": "2026-01-01", "duration_seconds": 100.0}

        trang_thai_a, _ = self.svc._phan_loai_va_ghi_mot_video(
            source=src, mappings=mappings, episodes_by_series=episodes_by_series,
            video=video_a, da_la_tap={})
        trang_thai_b, _ = self.svc._phan_loai_va_ghi_mot_video(
            source=src, mappings=mappings, episodes_by_series=episodes_by_series,
            video=video_b, da_la_tap={})

        self.assertEqual(trang_thai_a, ImportStatus.AUTO_IMPORTED)
        self.assertEqual(trang_thai_b, ImportStatus.CONFLICT)
        tap_7 = [e for e in self.animation.list_episodes(self.series.series_id)
                if e.order_index == 7]
        self.assertEqual(len(tap_7), 1)
        self.assertEqual(tap_7[0].external_id, "vidRaceA001")

    def test_cung_video_xu_ly_gan_nhu_dong_thoi_hai_lan_khong_tao_tap_trung(self):
        """Cung MOT video duoc phan loai-va-ghi hai lan GAN NHU DONG THOI
        (vi du hai thong bao WebSub trung lap toi TRUOC khi lan dau kip ghi
        ban ghi VideoImport) — phai idempotent tuyet doi: chi MOT tap duoc
        tao trong store, ca hai lan goi deu tra ve DUNG mot trang thai."""
        cid = "UC" + "o" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh O", auto_import=True, auto_publish=True,
            minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])

        src = self.store.get_source(source["source_id"])
        mappings = self.store.list_mappings(source["source_id"])
        episodes_by_series = {self.series.series_id: ()}
        video = {"video_id": "vidSameRace1", "title": "Tiên Nghịch Tập 9",
                "channel_id": cid, "channel_title": "Kenh O", "thumbnail_url": "",
                "published_at": "2026-01-01", "duration_seconds": 100.0}

        trang_thai_1, _ = self.svc._phan_loai_va_ghi_mot_video(
            source=src, mappings=mappings, episodes_by_series=episodes_by_series,
            video=video, da_la_tap={})
        trang_thai_2, _ = self.svc._phan_loai_va_ghi_mot_video(
            source=src, mappings=mappings, episodes_by_series=episodes_by_series,
            video=video, da_la_tap={})

        self.assertEqual(trang_thai_1, ImportStatus.AUTO_PUBLISHED)
        self.assertEqual(trang_thai_2, ImportStatus.AUTO_PUBLISHED)
        tap_9 = [e for e in self.animation.list_episodes(self.series.series_id)
                if e.order_index == 9]
        self.assertEqual(len(tap_9), 1)
        self.assertEqual(tap_9[0].external_id, "vidSameRace1")

    def test_loi_noi_bo_tam_thoi_luc_ghi_mot_video_khong_lam_hong_ca_lo_quet(self):
        """MOT video gap loi Appwrite tam thoi luc GHI (`NotFoundError` —
        xem docstring `AppwriteAnimationStore._call` ve vi sao day la kieu
        loi CHUNG cho ca "khong tim thay" LAN "loi HTTP/mang thoang qua")
        KHONG duoc lam hong toan bo lan quet: video loi KHONG tao ban ghi
        nao (khong mac ket o trang thai sai, tu nhien duoc thu lai o lan
        quet sau), CAC video khac trong CUNG lan quet van xu ly binh
        thuong."""
        cid = "UC" + "p" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh P", auto_import=True, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])

        upload_playlist = "UUppp"
        video_loi = "vidLoi000001"
        video_ok = "vidOk0000002"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh P",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: (
                [_video_item(video_loi), _video_item(video_ok)], "")},
            videos={
                video_loi: VideoInfo(
                    video_id=video_loi, title="Tiên Nghịch Tập 20", channel_id=cid,
                    channel_title="Kenh P", thumbnail_url="", published_at="2026-01-01",
                    duration_seconds=100.0),
                video_ok: VideoInfo(
                    video_id=video_ok, title="Tiên Nghịch Tập 21", channel_id=cid,
                    channel_title="Kenh P", thumbnail_url="", published_at="2026-01-01",
                    duration_seconds=100.0),
            },
        )
        self._dat_client_gia(client)

        goc = self.animation.create_episode_once

        def gia_loi(episode):
            if episode.external_id == video_loi:
                raise NotFoundError("Appwrite trả về lỗi thoáng qua (giả lập).")
            return goc(episode)

        with mock.patch.object(self.animation, "create_episode_once", side_effect=gia_loi):
            ket_qua = self.svc.scan_source(self.admin, source["source_id"])

        self.assertEqual(ket_qua["internal_errors"], 1)
        self.assertEqual(ket_qua["auto_imported"], 1)

        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].youtube_video_id, video_ok)

        # Quet lai (khong con loi gia lap) — video loi truoc do duoc THU
        # LAI binh thuong, khong mac ket o trang thai sai vinh vien.
        ket_qua_2 = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(ket_qua_2["internal_errors"], 0)
        rows_2, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(len(rows_2), 2)

    def test_discovered_via_ghi_luc_tao_khong_doi_khi_quet_lai_trigger_khac(self):
        """Auto-Ingestion Phase 4: `discovered_via` ghi lai trigger nao TAO
        RA ban ghi lan dau — quet lai voi trigger KHAC (vi du doi chieu tu
        dong sau khi da phat hien thu cong) KHONG duoc doi lai nguon goc da
        ghi, kem ca khi ban ghi van con NEW va duoc phan loai lai."""
        cid = "UC" + "q" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh Q", auto_import=False, minimum_confidence=0.9)
        upload_playlist = "UUqqq"
        video_id = "vidTrig00001"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kenh Q",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Video lạ Tập 1", channel_id=cid,
                channel_title="Kenh Q", thumbnail_url="", published_at="2026-01-01",
                duration_seconds=100.0)},
        )
        self._dat_client_gia(client)

        # Lan dau: trigger="manual_scan" (mac dinh cua scan_source).
        self.svc.scan_source(self.admin, source["source_id"])
        row = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row.discovered_via, "manual_scan")
        self.assertEqual(row.status, ImportStatus.NEW)  # khong khop mapping nao.

        # Them mapping roi quet lai VOI TRIGGER KHAC ("reconcile") — ban ghi
        # NEW duoc phan loai lai (mapping vua co hieu luc), nhung
        # discovered_via PHAI GIU NGUYEN "manual_scan" (nguon goc that su).
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["video la"], include_keywords=[], exclude_keywords=[])
        self.svc.scan_source(self.admin, source["source_id"], trigger="reconcile")
        row_2 = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row_2.discovered_via, "manual_scan")
        self.assertEqual(row_2.status, ImportStatus.PENDING)  # gio da khop, dung tin cay chan tu dong.

    def test_nhap_thu_cong_dua_voi_tu_dong_dang_xu_ly_video_khac_cung_slot(self):
        """Auto-Ingestion Phase 4 (Stage J): quan tri bam "Nhập" THỦ CÔNG
        cho video X, DUNG LUC tu dong (WebSub/quet) dang xu ly video Y KHAC
        nhung cung suy ra (series, so tap) — nhap thu cong dung
        `create_episode_once` GIONG duong tu dong, nen ca hai KHONG THE
        cung thanh cong rieng le: ai toi truoc thang, ai toi sau la CONFLICT."""
        cid = "UC" + "r" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh R", auto_import=True, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])
        src = self.store.get_source(source["source_id"])
        mappings = self.store.list_mappings(source["source_id"])

        # Video X: da co ban ghi VideoImport (vi du quan tri da gan series/tap
        # thu cong truoc do), CHO nhap.
        video_x, _ = self.store.create_import_once(VideoImport(
            trusted_source_id=source["source_id"], youtube_video_id="vidManualX01",
            title="Tiên Nghịch Tập 15", channel_id=cid, channel_title="Kenh R",
            detected_series_id=self.series.series_id, detected_episode_number=15,
            status=ImportStatus.PENDING))

        # "Dung luc": video Y KHAC duoc TU DONG phan loai, cung suy ra tap 15.
        video_y_dict = {"video_id": "vidAutoY0002", "title": "Tiên Nghịch Tập 15",
                        "channel_id": cid, "channel_title": "Kenh R", "thumbnail_url": "",
                        "published_at": "2026-01-01", "duration_seconds": 100.0}
        trang_thai_y, _ = self.svc._phan_loai_va_ghi_mot_video(
            source=src, mappings=mappings, episodes_by_series={self.series.series_id: ()},
            video=video_y_dict, da_la_tap={})
        self.assertEqual(trang_thai_y, ImportStatus.AUTO_IMPORTED)

        # Quan tri bam "Nhap" cho video X NGAY SAU DO — da tre, phai la
        # CONFLICT, KHONG tao tap thu hai cho cung so tap.
        ket_qua_x = self.svc.import_video(self.admin, video_x.import_id, publish=False)
        self.assertEqual(ket_qua_x["status"], "conflict")

        tap_15 = [e for e in self.animation.list_episodes(self.series.series_id)
                 if e.order_index == 15]
        self.assertEqual(len(tap_15), 1)
        self.assertEqual(tap_15[0].external_id, "vidAutoY0002")

    def test_tu_dong_dua_voi_nhap_thu_cong_da_thang_truoc_thanh_conflict(self):
        """Chieu nguoc lai cua test tren: quan tri nhap THU CONG THANG
        TRUOC, tu dong (video khac, cung slot) toi SAU phai la CONFLICT."""
        cid = "UC" + "s" * 22
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kenh S", auto_import=True, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tien nghich"], include_keywords=[], exclude_keywords=[])
        src = self.store.get_source(source["source_id"])
        mappings = self.store.list_mappings(source["source_id"])

        video_x, _ = self.store.create_import_once(VideoImport(
            trusted_source_id=source["source_id"], youtube_video_id="vidManualX02",
            title="Tiên Nghịch Tập 20", channel_id=cid, channel_title="Kenh S",
            detected_series_id=self.series.series_id, detected_episode_number=20,
            status=ImportStatus.PENDING))
        ket_qua_x = self.svc.import_video(self.admin, video_x.import_id, publish=False)
        self.assertEqual(ket_qua_x["status"], "imported")

        video_y_dict = {"video_id": "vidAutoY0003", "title": "Tiên Nghịch Tập 20",
                        "channel_id": cid, "channel_title": "Kenh S", "thumbnail_url": "",
                        "published_at": "2026-01-01", "duration_seconds": 100.0}
        trang_thai_y, _ = self.svc._phan_loai_va_ghi_mot_video(
            source=src, mappings=mappings, episodes_by_series={self.series.series_id: ()},
            video=video_y_dict, da_la_tap={})
        self.assertEqual(trang_thai_y, ImportStatus.CONFLICT)

        tap_20 = [e for e in self.animation.list_episodes(self.series.series_id)
                 if e.order_index == 20]
        self.assertEqual(len(tap_20), 1)
        self.assertEqual(tap_20[0].external_id, "vidManualX02")

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


class ImportStateReclassificationPolicyTest(unittest.TestCase):
    """Auto-Ingestion Phase 5 pre-merge hardening — chinh sach "trang thai
    nao con duoc phan loai lai" (`TRANG_THAI_CHO_QUYET_DINH`), dung CHUNG boi
    `scan_source`/`_xu_ly_mot_video_discovery`/`_xu_ly_mot_video_websub`.
    NEW/PENDING/CONFLICT la QUYET DINH TAM, phai duoc phan loai lai khi dieu
    kien doi; moi trang thai khac la QUYET DINH CUOI CUNG, KHONG BAO GIO bi
    ghi de boi bat ky duong tu dong nao."""

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

    def _nguon_va_video(self, cid, video_id, title, **kw_nguon):
        upload_playlist = f"UU{cid[-4:]}"
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kênh test", **kw_nguon)
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh test",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title=title, channel_id=cid,
                channel_title="Kênh test", thumbnail_url="", published_at="2026-01-01",
                duration_seconds=100.0)},
        )
        self._dat_client_gia(client)
        return source

    def test_pending_voi_mapping_manh_hon_xuat_hien_reclassify_thanh_auto_imported(self):
        """PENDING (do tin cay duoi nguong luc dau) -> quan tri sua nguong
        thap hon -> quet lai PHAI phan loai lai thanh AUTO_IMPORTED, khong con
        ket vien PENDING vinh vien."""
        cid = "UC" + "s1" * 11
        video_id = "vidPend0001"
        source = self._nguon_va_video(
            cid, video_id, "Tiên Nghịch Tập 3", auto_import=True, minimum_confidence=0.9)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tiên nghịch"], include_keywords=[], exclude_keywords=[])

        lan_1 = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(lan_1["pending"], 1)
        row = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row.status, ImportStatus.PENDING)

        # Nguong tin cay giam -> video CU (dang PENDING) gio du dieu kien.
        self.svc.update_source(
            self.admin, source["source_id"], {"minimum_confidence": 0.1},
            actor_role="owner")

        lan_2 = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(lan_2["already_tracked"], 0, "PENDING phai duoc phan loai lai")
        self.assertEqual(lan_2["auto_imported"], 1)
        row_2 = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row_2.status, ImportStatus.AUTO_IMPORTED)
        self.assertTrue(row_2.created_episode_id)
        _rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total, 1, "khong tao them ban ghi thu hai")

    def test_conflict_duoc_giai_toa_sau_khi_video_chiem_cho_bi_tu_choi(self):
        """CONFLICT (so tap bi chiem) -> video chiem cho bi quan tri TU CHOI
        (giai phong tap that trong AnimationEpisode) -> quet lai PHAI
        reevaluate va thanh cong (khong con ket vien CONFLICT vinh vien khi
        dieu kien thuc te da doi)."""
        cid = "UC" + "s2" * 11
        video_chiem = "vidHold0001"
        video_conflict = "vidConf0002"
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kênh test", auto_import=True, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tiên nghịch"], include_keywords=[], exclude_keywords=[])
        upload_playlist = f"UU{cid[-4:]}"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh test",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_chiem)], "")},
            videos={
                video_chiem: VideoInfo(
                    video_id=video_chiem, title="Tiên Nghịch Tập 5", channel_id=cid,
                    channel_title="Kênh test", thumbnail_url="", published_at="2026-01-01",
                    duration_seconds=100.0),
                video_conflict: VideoInfo(
                    video_id=video_conflict, title="Tiên Nghịch Tập 5", channel_id=cid,
                    channel_title="Kênh test", thumbnail_url="", published_at="2026-01-02",
                    duration_seconds=100.0),
            },
        )
        self._dat_client_gia(client)
        self.svc.scan_source(self.admin, source["source_id"])
        row_chiem = self.store.get_import_by_video_id(video_chiem)
        self.assertEqual(row_chiem.status, ImportStatus.AUTO_IMPORTED)
        episode_id_chiem = row_chiem.created_episode_id

        # Video thu hai, cung so tap -> quet rieng, phai la CONFLICT.
        client._playlist_items[upload_playlist] = (
            [_video_item(video_chiem), _video_item(video_conflict)], "")
        ket_qua = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(ket_qua["conflicts"], 1)
        row_conflict = self.store.get_import_by_video_id(video_conflict)
        self.assertEqual(row_conflict.status, ImportStatus.CONFLICT)

        # Quan tri xoa tap dang chiem cho (giai phong so tap 5 that su).
        self.animation.delete_episode(episode_id_chiem, "author_1")

        # Quet lai — CONFLICT phai duoc reevaluate; nguon van auto_import,
        # nen video_conflict gio thang cho va duoc tu dong nhap.
        lan_cuoi = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(lan_cuoi["already_tracked"], 1, "video_chiem van AUTO_IMPORTED, final")
        row_conflict_2 = self.store.get_import_by_video_id(video_conflict)
        self.assertEqual(row_conflict_2.status, ImportStatus.AUTO_IMPORTED)
        self.assertTrue(row_conflict_2.created_episode_id)

    def test_rejected_khong_bao_gio_tu_doi_khi_quet_lai(self):
        cid = "UC" + "s3" * 11
        video_id = "vidRej0001"
        source = self._nguon_va_video(
            cid, video_id, "Tiên Nghịch Tập 1", auto_import=True, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tiên nghịch"], include_keywords=[], exclude_keywords=[])
        self.svc.scan_source(self.admin, source["source_id"])
        row = self.store.get_import_by_video_id(video_id)
        self.svc.reject_import(self.admin, row.import_id, reason="sai series")

        ket_qua = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(ket_qua["already_tracked"], 1)
        row_2 = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row_2.status, ImportStatus.REJECTED)
        self.assertIn("sai series", row_2.reason)

    def test_ignored_khong_bao_gio_tu_doi_khi_quet_lai(self):
        cid = "UC" + "s4" * 11
        video_id = "vidIgn0001"
        source = self._nguon_va_video(
            cid, video_id, "Tiên Nghịch Tập 1", auto_import=True, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tiên nghịch"], include_keywords=[], exclude_keywords=[])
        self.svc.scan_source(self.admin, source["source_id"])
        row = self.store.get_import_by_video_id(video_id)
        self.svc.ignore_import(self.admin, row.import_id)

        ket_qua = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(ket_qua["already_tracked"], 1)
        row_2 = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row_2.status, ImportStatus.IGNORED)

    def test_imported_khong_bao_gio_tao_them_episode_khi_quet_lai(self):
        cid = "UC" + "s5" * 11
        video_id = "vidImp0001"
        source = self._nguon_va_video(
            cid, video_id, "Tiên Nghịch Tập 1", auto_import=False, minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tiên nghịch"], include_keywords=[], exclude_keywords=[])
        self.svc.scan_source(self.admin, source["source_id"])
        row = self.store.get_import_by_video_id(video_id)
        self.svc.set_import_series(
            self.admin, row.import_id, series_id=self.series.series_id, episode_number=1)
        nhap = self.svc.import_video(self.admin, row.import_id, publish=False)
        self.assertEqual(nhap["status"], "imported")
        episode_id_dau = nhap["created_episode_id"]

        ket_qua = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(ket_qua["already_tracked"], 1)
        row_2 = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row_2.status, ImportStatus.IMPORTED)
        self.assertEqual(row_2.created_episode_id, episode_id_dau)
        self.assertEqual(len(self.animation.list_episodes(self.series.series_id)), 1)

    def test_duplicate_khong_bao_gio_tu_doi_khi_quet_lai(self):
        cid = "UC" + "s6" * 11
        video_id = "vidDup0001"
        self.animation.create_episode(AnimationEpisode(
            series_id=self.series.series_id, owner_id="author_1", title="Đã có",
            source=AnimationSource.YOUTUBE, external_id=video_id, order_index=1))
        source = self._nguon_va_video(
            cid, video_id, "Tiên Nghịch Tập 1", auto_import=True, minimum_confidence=0.1)

        self.svc.scan_source(self.admin, source["source_id"])
        row = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row.status, ImportStatus.DUPLICATE)

        ket_qua = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(ket_qua["already_tracked"], 1)
        row_2 = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row_2.status, ImportStatus.DUPLICATE)

    def test_websub_reclassify_pending_thanh_auto_imported_khi_mapping_moi_xuat_hien(self):
        """WebSub phai dung CHUNG chinh sach voi scan_source: mot video PENDING
        (chua khop mapping nao luc dau -> that ra la NEW, roi mapping xuat
        hien sau) duoc phan loai lai qua thong bao WebSub TIEP THEO, khong
        chi lam moi metadata."""
        cid = "UC" + "s7" * 11
        video_id = "vidWs0001"
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kênh WebSub", auto_import=True, minimum_confidence=0.1,
            auto_discover=True)
        client = FakeYouTubeClient(videos={video_id: VideoInfo(
            video_id=video_id, title="Tiên Nghịch Tập 2", channel_id=cid,
            channel_title="Kênh WebSub", thumbnail_url="", published_at="",
            duration_seconds=100.0)})
        self._dat_client_gia(client)

        self.svc._xu_ly_mot_video_websub(self.store.get_source(source["source_id"]), video_id)
        row = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row.status, ImportStatus.NEW)

        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tiên nghịch"], include_keywords=[], exclude_keywords=[])
        self.svc._xu_ly_mot_video_websub(self.store.get_source(source["source_id"]), video_id)
        row_2 = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row_2.status, ImportStatus.AUTO_IMPORTED)
        _rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total, 1)


class CrossDomainDuplicateAdvisoryTest(unittest.TestCase):
    """Pre-merge hardening (2026-08), Fix 1 — canh bao CHI DE THAM KHAO khi
    mot video quet duoc co ID TRUNG voi ID nhung trong `description` (van
    ban tu do) cua mot Novel co san (mien Novel/Chapter HOAN TOAN khac, xem
    `VideoImport.possible_duplicate_novel_id`)."""

    def setUp(self):
        self.store = MockTrustedSourceStore()
        self.animation = MockAnimationStore()
        self.metadata = MockMetadataStore()
        self.svc = TrustedSourceService(
            self.store, self.animation, self.metadata, youtube_api_key="fake-key")
        self.admin = Profile(user_id="admin_1", email="admin@fanfic.world")

    def _dat_client_gia(self, client: FakeYouTubeClient):
        self.svc._youtube = lambda: client  # type: ignore[method-assign]

    def _quet_mot_video(self, cid: str, video_id: str, title: str):
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kênh test")
        upload_playlist = f"UU{cid[-4:]}"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh test",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title=title, channel_id=cid,
                channel_title="Kênh test", thumbnail_url="", published_at="2026-01-01",
                duration_seconds=100.0)},
        )
        self._dat_client_gia(client)
        self.svc.scan_source(self.admin, source["source_id"])
        return source

    def test_khop_novel_gan_co_video_id_trong_mo_ta(self):
        video_id = "vidDupNov01"
        novel = self.metadata.create_novel(Novel(
            owner_id="studio_1", title="Truyện gốc",
            description=(
                f"Nguồn: https://www.youtube.com/watch?v={video_id} "
                "(kênh: vucthamaudio)")))
        cid = "UC" + "n1" * 11
        self._quet_mot_video(cid, video_id, "Video không liên quan tên gì cả")
        row = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row.possible_duplicate_novel_id, novel.novel_id)

    def test_truong_hop_that_tren_production_2026_08_26(self):
        """Khoa lai bang chung song: 2026-08-26, chay THANG
        `_phat_hien_novel_trung` (khong qua HTTP/admin) tren du lieu
        production THAT (novel nov_6b42f7954f914227, video XtJqhxbd1pY, kenh
        vucthamaudio, mot trong 13 tac pham Fanfic that nhap tu Google Drive)
        cho ket qua DUNG. Test nay tai hien CHINH XAC noi dung description
        that (chi thay novel_id gia de khong phu thuoc production) de dam
        bao logic khong bao gio regress tren dung truong hop nay — xem
        docs/reports/trusted-sources-duplicate-advisor-2026-08-26.md."""
        video_id = "XtJqhxbd1pY"
        novel = self.metadata.create_novel(Novel(
            owner_id="studio_1",
            title=("Conan Fanfic Luật Sư Ác Ma Đối Đầu Nữ Hoàng Phòng Xử Án "
                   "Kisaki Eri, Ta Thu Những Phu Nhân Cực Phẩm"),
            description=(
                "Fandom: Da Fandom Unresolved\n"
                f"Nguồn: https://www.youtube.com/watch?v={video_id} "
                "(kênh: vucthamaudio)\n\n"
                "Bản hiện tại được phát hành dưới dạng một tập audio đầy đủ "
                "và chưa được tách thành các chương riêng."),
            tags=["work:CAT-15deb7a2804f", "imported", "long_form_audio",
                  "fandom:Da Fandom Unresolved"]))
        cid = "UC" + "vt" * 11
        self._quet_mot_video(cid, video_id, "Video không liên quan tên gì cả")
        row = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row.possible_duplicate_novel_id, novel.novel_id)

    def test_khong_khop_novel_nao_giu_none(self):
        video_id = "vidNoDup001"
        self.metadata.create_novel(Novel(
            owner_id="studio_1", title="Truyện khác",
            description="Không liên quan gì tới video này cả."))
        cid = "UC" + "n2" * 11
        self._quet_mot_video(cid, video_id, "Video bình thường")
        row = self.store.get_import_by_video_id(video_id)
        self.assertIsNone(row.possible_duplicate_novel_id)

    def test_loi_kho_novel_khong_lam_sap_luong_phan_loai(self):
        """`find_novels` nem loi (kho Novel tam thoi khong san sang) —
        advisory PHAI am tham that bai, KHONG duoc phep chan viec tao
        `VideoImport` (xem docstring `_phat_hien_novel_trung`)."""
        video_id = "vidErrDup01"
        self.metadata.find_novels = mock.Mock(side_effect=RuntimeError("boom"))
        cid = "UC" + "n3" * 11
        self._quet_mot_video(cid, video_id, "Video bình thường")
        row = self.store.get_import_by_video_id(video_id)
        self.assertIsNotNone(row)
        self.assertIsNone(row.possible_duplicate_novel_id)

    def test_khop_du_novel_that_su_trung_nam_ngoai_top_5_cu(self):
        """2026-08-26 hardening — truoc day `limit=5`: neu >=5 Novel KHAC
        cung chua chuoi video_id (vi du bi nhac lai trong description cua
        nhieu Novel khong lien quan), Novel THAT SU trung co the bi day ra
        ngoai trang va bo lo trong im lang. Tao 6 Novel gia (moi cai deu chua
        chuoi video_id) SOM HON (cu hon, nen dung sau khi sap theo
        created_at giam dan) roi Novel THAT SU trung — chi qua duoc test nay
        neu cua so ung vien > 5."""
        video_id = "vidWideWindow01"
        # 6 Novel "nhieu": video_id XUAT HIEN TRONG TIEU DE (nen van duoc
        # `find_novels(query=video_id)` tra ve lam ung vien — day dung DB that
        # loc title/description CHUA chuoi) nhung KHONG co trong description,
        # nen phai bi loai o buoc kiem tra chinh xac cuoi cung.
        for i in range(6):
            self.metadata.create_novel(Novel(
                owner_id="studio_1", title=f"Video {video_id} — ban nhac lai {i}",
                description="Khong lien quan gi den nguon that ca."))
        # Novel THAT SU trung duoc tao SAU CUNG (moi hon, nen sap len dau neu
        # khong can thiep) — dat created_at CU HON thu cong de buoc no xep
        # SAU CA 6 novel gia o tren (tuc: nam ngoai top-5 neu gioi han van la
        # 5, chi qua duoc test khi cua so ung vien duoc mo rong).
        that_su_trung_novel = self.metadata.create_novel(Novel(
            owner_id="studio_1", title="Truyện gốc thật",
            description=f"Nguồn: https://www.youtube.com/watch?v={video_id} (kênh: that)"))
        that_su_trung_novel.created_at = "2000-01-01T00:00:00.000+00:00"

        cid = "UC" + "wd" * 11
        self._quet_mot_video(cid, video_id, "Video không liên quan tên gì cả")
        row = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row.possible_duplicate_novel_id, that_su_trung_novel.novel_id)

    def test_dang_url_youtube_be_van_duoc_nhan_dien(self):
        """So sanh la CHUOI CON tren `video_id`, khong phai tren URL day du —
        nen moi dang URL (youtu.be, m.youtube.com, watch?v=...) deu duoc
        nhan dien nhu nhau mien description co chua chinh ID do."""
        video_id = "vidShortUrl1"
        novel = self.metadata.create_novel(Novel(
            owner_id="studio_1", title="Truyện gốc (youtu.be)",
            description=f"Nguồn: https://youtu.be/{video_id}"))
        cid = "UC" + "yt" * 11
        self._quet_mot_video(cid, video_id, "Video không liên quan")
        row = self.store.get_import_by_video_id(video_id)
        self.assertEqual(row.possible_duplicate_novel_id, novel.novel_id)

    def test_tieu_de_giong_nhau_nhung_khac_video_khong_bi_bao_trung(self):
        """Yeu cau: khong duoc co false positive CHI vi tieu de/fandom giong
        nhau. Co che hien tai la so khop CHINH XAC theo video_id trong
        description (khong phai do tuong dong tieu de), nen dieu nay PHAI
        dung tu nhien — test nay khoa lai tinh chat do, tranh regression neu
        sau nay co ai doi sang so khop mo (fuzzy) tren tieu de."""
        self.metadata.create_novel(Novel(
            owner_id="studio_1", title="Conan Fanfic: Luật Sư Ác Ma",
            description="Nguồn: https://www.youtube.com/watch?v=DIFFERENT_VIDEO_ID"))
        video_id = "vidSimilarTitle1"
        cid = "UC" + "st" * 11
        self._quet_mot_video(cid, video_id, "Conan Fanfic: Luật Sư Ác Ma (phần 2)")
        row = self.store.get_import_by_video_id(video_id)
        self.assertIsNone(row.possible_duplicate_novel_id)


class CreateSourceRaceConditionTest(unittest.TestCase):
    """Pre-merge hardening (2026-08), Fix 2 — `create_source` phai dung
    `source_id` TAT DINH (`trusted_source_domain.trusted_source_id`) + kho
    tu choi tao trung `documentId`, KHONG chi dua vao doc-truoc-roi-so-sanh
    (`_dinh_danh_da_ton_tai`), von KHONG an toan duoi tai dua nhau THAT."""

    def setUp(self):
        self.store = MockTrustedSourceStore()
        self.animation = MockAnimationStore()
        self.metadata = MockMetadataStore()
        self.svc = TrustedSourceService(
            self.store, self.animation, self.metadata, youtube_api_key="fake-key")
        self.admin = Profile(user_id="admin_1", email="admin@fanfic.world")

    def test_hai_lan_tao_lien_tiep_cung_kenh_bao_loi_ro_rang(self):
        cid = "UC" + "r1" * 11
        self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kênh R")
        with self.assertRaises(TrustedSourceError):
            self.svc.create_source(
                self.admin, source_type="youtube_channel", youtube_channel_id=cid,
                display_name="Kênh R (lại)")
        items, total = self.store.find_sources(limit=None)
        self.assertEqual(total, 1, "KHONG duoc tao ra ban ghi trung lap thu hai")

    def test_dua_nhau_that_bo_qua_kiem_tra_truoc_van_chi_tao_MOT_ban_ghi(self):
        """Mo phong RACE THAT: ca hai yeu cau deu doc thay "chua ton tai"
        (nhu the chung chay gan nhu dong thoi TRUOC khi ben nao ghi xong) —
        vo hieu hoa `_dinh_danh_da_ton_tai` de bo qua nhanh kiem tra than
        thien, chi con `source_id` TAT DINH + kho tu choi trung `documentId`
        lam nguoi chan CUOI CUNG."""
        cid = "UC" + "r2" * 11
        self.svc._dinh_danh_da_ton_tai = lambda moi: False  # type: ignore[method-assign]

        source_1 = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kênh Đua 1")
        with self.assertRaises(TrustedSourceError):
            self.svc.create_source(
                self.admin, source_type="youtube_channel", youtube_channel_id=cid,
                display_name="Kênh Đua 2")

        items, total = self.store.find_sources(limit=None)
        self.assertEqual(total, 1, "hai yeu cau dong thoi CHI duoc tao MOT nguon")
        self.assertEqual(items[0].source_id, source_1["source_id"])
        # display_name giu NGUYEN cua ben THANG (yeu cau dau tien) — ben THUA
        # khong am tham ghi de du lieu cua ben thang.
        self.assertEqual(items[0].display_name, "Kênh Đua 1")

    def test_source_id_tat_dinh_theo_loai_va_dinh_danh(self):
        """Cung mot ID nhung KHAC loai nguon (video vs kenh) khong duoc phep
        va cham `source_id` voi nhau."""
        cung_id = "UCsameid00000000000000"
        kenh = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cung_id,
            display_name="Coi là kênh")
        video = self.svc.create_source(
            self.admin, source_type="youtube_video", youtube_video_id=cung_id,
            display_name="Coi là video")
        self.assertNotEqual(kenh["source_id"], video["source_id"])


class UploadsPlaylistIdCacheTest(unittest.TestCase):
    """Pre-merge hardening (2026-08), Fix 4 — `uploads_playlist_id` cua mot
    kenh CHI duoc resolve qua `channels.list` MOT LAN roi cache lai tren
    chinh `TrustedSource`; lan quet sau khong duoc goi lai `channels.list`."""

    def setUp(self):
        self.store = MockTrustedSourceStore()
        self.animation = MockAnimationStore()
        self.metadata = MockMetadataStore()
        self.svc = TrustedSourceService(
            self.store, self.animation, self.metadata, youtube_api_key="fake-key")
        self.admin = Profile(user_id="admin_1", email="admin@fanfic.world")

    def _dat_client_gia(self, client: FakeYouTubeClient):
        self.svc._youtube = lambda: client  # type: ignore[method-assign]

    def test_quet_lan_hai_khong_goi_lai_channels_list(self):
        cid = "UC" + "u1" * 11
        upload_playlist = "UUu1u1"
        source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="Kênh cache")

        so_lan_goi_channel = {"n": 0}

        class _CountingYouTubeClient(FakeYouTubeClient):
            def get_channel(self, channel_id):
                so_lan_goi_channel["n"] += 1
                return super().get_channel(channel_id)

        client = _CountingYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh cache",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item("vidCache001")], "")},
            videos={"vidCache001": VideoInfo(
                video_id="vidCache001", title="Video 1", channel_id=cid,
                channel_title="Kênh cache", thumbnail_url="", published_at="2026-01-01",
                duration_seconds=100.0)},
        )
        self._dat_client_gia(client)

        lan_1 = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(lan_1["detected"], 1)
        self.assertEqual(so_lan_goi_channel["n"], 1, "lan quet dau PHAI goi channels.list")
        cached = self.store.get_source(source["source_id"])
        self.assertEqual(cached.uploads_playlist_id, upload_playlist)

        lan_2 = self.svc.scan_source(self.admin, source["source_id"])
        self.assertEqual(
            so_lan_goi_channel["n"], 1,
            "lan quet thu hai KHONG duoc goi lai channels.list (dung cache)")
        # Van phai liet ke duoc video binh thuong tu playlist da biet ID
        # (khong co mapping nao nen video van o trang thai NEW, con CHO
        # QUYET DINH, duoc phan loai lai — day KHONG phai muc tieu cua test
        # nay, chi can xac nhan quet van THANH CONG binh thuong qua cache).
        self.assertEqual(lan_2["detected"], 1)


if __name__ == "__main__":
    unittest.main()
