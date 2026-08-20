"""
Test cho `TrustedSourceService.discover_channel` (Auto-Ingestion Phase 5 —
"Autonomous Multi-Series Channel Ingestion"). Dung lai FakeYouTubeClient tu
`test_trusted_source_service.py`, cung triet ly voi `test_series_discovery.py`
(Phase 1) — tap trung vao NGHIEP VU gom nhom/resolve-hoac-tao nhieu series
cung luc tu MOT kenh/playlist, khong phai MOT seed do quan tri chon.
"""

from __future__ import annotations

import unittest

from server.adapters import MockMetadataStore
from server.animation_domain import AnimationSeries
from server.animation_store import MockAnimationStore
from server.domain import Profile, PublishState
from server.trusted_source_domain import ImportStatus
from server.trusted_source_service import TrustedSourceError, TrustedSourceService
from server.trusted_source_store import MockTrustedSourceStore
from server.tests.test_trusted_source_service import FakeYouTubeClient, _video_item
from server.youtube_client import ChannelInfo, VideoInfo


class ChannelDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.store = MockTrustedSourceStore()
        self.animation = MockAnimationStore()
        self.metadata = MockMetadataStore()
        self.svc = TrustedSourceService(
            self.store, self.animation, self.metadata, youtube_api_key="fake-key")
        self.admin = Profile(user_id="admin_1", email="admin@fanfic.world")

    def _dat_client_gia(self, client: FakeYouTubeClient):
        self.svc._youtube = lambda: client  # type: ignore[method-assign]

    def _tao_nguon_kenh(self, cid: str, **kw):
        mac_dinh = {
            "source_type": "youtube_channel", "youtube_channel_id": cid,
            "display_name": "Kênh nhiều series", "auto_import": True,
            "minimum_confidence": 0.1,
        }
        mac_dinh.update(kw)
        return self.svc.create_source(self.admin, **mac_dinh)

    def _client_don_gian(self, cid: str, playlist_id: str, videos: dict):
        return FakeYouTubeClient(
            channels={cid: ChannelInfo(
                channel_id=cid, title="Kênh nhiều series", thumbnail_url="",
                uploads_playlist_id=playlist_id)},
            playlist_items={playlist_id: (
                [_video_item(v) for v in videos], "")},
            videos=videos)

    # -- gom nhieu series khac nhau tu MOT kenh --------------------------------

    def test_gom_hai_series_khac_nhau_tu_mot_kenh(self):
        cid, playlist_id = "UC" + "a" * 22, "UUaaa"
        source = self._tao_nguon_kenh(cid)
        videos = {
            "vidA1": VideoInfo(video_id="vidA1", title="Tiên Nghịch Tập 1",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-01",
                               duration_seconds=1000.0),
            "vidA2": VideoInfo(video_id="vidA2", title="Tiên Nghịch Tập 2",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-02",
                               duration_seconds=1000.0),
            "vidB1": VideoInfo(video_id="vidB1", title="Đấu Phá Thương Khung Tập 1",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-03",
                               duration_seconds=1000.0),
            "vidB2": VideoInfo(video_id="vidB2", title="Đấu Phá Thương Khung Tập 2",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-04",
                               duration_seconds=1000.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])

        self.assertEqual(ket_qua.videos_discovered, 4)
        self.assertEqual(ket_qua.candidate_groups, 2)
        self.assertEqual(ket_qua.new_series_created, 2)
        for vid in videos:
            self.assertIn(vid, ket_qua.confident_imports)

        self.assertEqual(
            {self.animation.get_series(g.series_id).title for g in ket_qua.groups},
            {"Tiên Nghịch", "Đấu Phá Thương Khung"})
        self.assertEqual(
            {g.canonical_name for g in ket_qua.groups},
            {"Tiên Nghịch", "Đấu Phá Thương Khung"})

    # -- video khop mapping DA CO khong can gom nhom ---------------------------

    def test_video_khop_mapping_da_co_khong_can_gom_nhom(self):
        cid, playlist_id = "UC" + "b" * 22, "UUbbb"
        source = self._tao_nguon_kenh(cid)
        series = self.animation.create_series(
            AnimationSeries(owner_id="author_1", title="Tiên Nghịch"))
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=series.series_id,
            aliases=["tiên nghịch"], include_keywords=[], exclude_keywords=[])

        videos = {
            "vidC1": VideoInfo(video_id="vidC1", title="Tiên Nghịch Tập 9",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-01",
                               duration_seconds=1000.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])

        self.assertEqual(ket_qua.matched_existing_mapping, 1)
        self.assertEqual(ket_qua.candidate_groups, 0)
        self.assertEqual(ket_qua.new_series_created, 0)
        self.assertIn("vidC1", ket_qua.confident_imports)
        _, tong_series = self.animation.find_series(include_removed=True)
        self.assertEqual(tong_series, 1)

    # -- trailer/OST bi loai hoan toan khoi gom nhom ---------------------------

    def test_trailer_bi_loai_hoan_toan_khong_tao_series_rieng(self):
        cid, playlist_id = "UC" + "c" * 22, "UUccc"
        source = self._tao_nguon_kenh(cid)
        videos = {
            "vidD1": VideoInfo(video_id="vidD1", title="Tiên Nghịch Tập 1",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-01",
                               duration_seconds=1000.0),
            "vidD2": VideoInfo(video_id="vidD2", title="Tiên Nghịch Official Trailer",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-02",
                               duration_seconds=60.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])

        self.assertEqual(ket_qua.candidate_groups, 1)
        self.assertEqual(ket_qua.excluded_negative_keyword, 1)
        self.assertIn("vidD1", ket_qua.confident_imports)
        self.assertNotIn("vidD2", ket_qua.confident_imports)
        rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total, 1)  # KHONG tao VideoImport cho trailer.

    # -- dai tap/compilation duoc gom dung series nhung KHONG tu dong nhap -----

    def test_dai_tap_gom_dung_series_nhung_cho_duyet(self):
        cid, playlist_id = "UC" + "e" * 22, "UUeee"
        source = self._tao_nguon_kenh(cid)
        videos = {
            "vidF1": VideoInfo(video_id="vidF1", title="Tiên Nghịch Tập 1",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-01",
                               duration_seconds=1000.0),
            "vidF2": VideoInfo(video_id="vidF2", title="Tiên Nghịch Tập 1-13 Trọn Bộ",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-02",
                               duration_seconds=36000.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])

        self.assertEqual(ket_qua.candidate_groups, 1)
        cum = ket_qua.groups[0]
        self.assertIn("vidF1", cum.video_ids)
        self.assertIn("vidF2", cum.video_ids)
        # Dai dien PHAI la vidF1 (co so tap don le), khong phai ban Tron Bo.
        self.assertEqual(cum.representative_video_id, "vidF1")
        self.assertIn("vidF1", ket_qua.confident_imports)
        self.assertIn("vidF2", ket_qua.pending_review)

    # -- idempotency: chay lai discover_channel tren cung nguon ----------------

    def test_kham_pha_lai_toan_kenh_idempotent(self):
        cid, playlist_id = "UC" + "g" * 22, "UUggg"
        source = self._tao_nguon_kenh(cid)
        videos = {
            "vidH1": VideoInfo(video_id="vidH1", title="Tiên Nghịch Tập 1",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-01",
                               duration_seconds=1000.0),
            "vidH2": VideoInfo(video_id="vidH2", title="Tiên Nghịch Tập 2",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-02",
                               duration_seconds=1000.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        lan_1 = self.svc.discover_channel(self.admin, source["source_id"])
        self.assertEqual(lan_1.new_series_created, 1)

        lan_2 = self.svc.discover_channel(self.admin, source["source_id"])
        # Lan 2: ca hai video da co quyet dinh quan tri (AUTO_IMPORTED) truoc
        # do -> "existing admin decisions must win", khong gom nhom/tao lai.
        self.assertEqual(lan_2.already_tracked, 2)
        self.assertEqual(lan_2.candidate_groups, 0)
        self.assertEqual(lan_2.new_series_created, 0)

        _, tong_series = self.animation.find_series(include_removed=True)
        self.assertEqual(tong_series, 1)
        _, tong_import = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(tong_import, 2)

    # -- quyet dinh quan tri (rejected) duoc giu khi kham pha lai --------------

    def test_quyet_dinh_quan_tri_duoc_giu_khi_kham_pha_lai_toan_kenh(self):
        cid, playlist_id = "UC" + "i" * 22, "UUiii"
        source = self._tao_nguon_kenh(cid)
        videos = {
            "vidJ1": VideoInfo(video_id="vidJ1", title="Tiên Nghịch Tập 1",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-01",
                               duration_seconds=1000.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        lan_1 = self.svc.discover_channel(self.admin, source["source_id"])
        self.assertIn("vidJ1", lan_1.confident_imports)

        import_j1 = self.store.get_import_by_video_id("vidJ1")
        self.svc.reject_import(self.admin, import_j1.import_id, reason="trùng bản dịch khác")

        lan_2 = self.svc.discover_channel(self.admin, source["source_id"])
        self.assertEqual(lan_2.already_tracked, 1)
        self.assertEqual(lan_2.candidate_groups, 0)
        import_sau = self.store.get_import_by_video_id("vidJ1")
        self.assertEqual(import_sau.status, ImportStatus.REJECTED)

    # -- nguon video don le khong duoc kham pha toan nguon ---------------------

    def test_nguon_video_don_bi_tu_choi(self):
        source = self.svc.create_source(
            self.admin, source_type="youtube_video", youtube_video_id="vidSolo001",
            display_name="Video đơn lẻ")
        with self.assertRaises(TrustedSourceError):
            self.svc.discover_channel(self.admin, source["source_id"])

    # -- thu tu ket qua on dinh (khong phu thuoc thu tu duyet) -----------------

    def test_gom_nhom_on_dinh_khong_phu_thuoc_thu_tu(self):
        cid, playlist_id = "UC" + "k" * 22, "UUkkk"
        source = self._tao_nguon_kenh(cid)
        videos = {
            "vidL1": VideoInfo(video_id="vidL1", title="Tiên Nghịch Tập 1",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-01",
                               duration_seconds=1000.0),
            "vidL2": VideoInfo(video_id="vidL2", title="Đấu Phá Thương Khung Tập 1",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-02",
                               duration_seconds=1000.0),
            "vidL3": VideoInfo(video_id="vidL3", title="Tiên Nghịch Tập 2",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-03",
                               duration_seconds=1000.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))
        ket_qua_1 = self.svc.discover_channel(self.admin, source["source_id"])
        nhom_1 = sorted(tuple(sorted(g.video_ids)) for g in ket_qua_1.groups)

        self.store = MockTrustedSourceStore()
        self.animation = MockAnimationStore()
        self.svc = TrustedSourceService(
            self.store, self.animation, self.metadata, youtube_api_key="fake-key")
        source_2 = self._tao_nguon_kenh(cid)
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))
        ket_qua_2 = self.svc.discover_channel(self.admin, source_2["source_id"])
        nhom_2 = sorted(tuple(sorted(g.video_ids)) for g in ket_qua_2.groups)

        self.assertEqual(nhom_1, nhom_2)


if __name__ == "__main__":
    unittest.main()
