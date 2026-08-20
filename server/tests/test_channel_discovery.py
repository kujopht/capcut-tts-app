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
from server.trusted_source_service import (
    MAX_SCAN_PAGES,
    TrustedSourceError,
    TrustedSourceService,
)
from server.trusted_source_store import MockTrustedSourceStore
from server.tests.test_trusted_source_service import FakeYouTubeClient, _video_item
from server.youtube_client import YouTubeApiError
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
        # vidD1 la MOT video DUY NHAT (singleton) — theo chinh sach tin cay
        # (pre-merge hardening), MOT video don le KHONG DU bang chung de tu
        # dong tao mot series MOI ("a single arbitrary unmatched video from a
        # channel must NOT automatically become a new series"). No van co so
        # tap don le doc duoc nen la MEDIUM (khong phai LOW), duoc giu lai de
        # quan tri xem (pending_review), KHONG tu dong nhap.
        self.assertEqual(ket_qua.new_series_created, 0)
        self.assertNotIn("vidD1", ket_qua.confident_imports)
        self.assertIn("vidD1", ket_qua.pending_review)
        self.assertNotIn("vidD2", ket_qua.confident_imports)
        cum = ket_qua.groups[0]
        self.assertEqual(cum.confidence_tier, "medium")
        self.assertFalse(cum.created_new_series)
        self.assertEqual(cum.series_id, "")
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
        # Hai video (khong phai mot minh) de cum dat tin cay HIGH va thuc su
        # tao series/nhap — mot singleton se KHONG con tu tao series theo
        # chinh sach tin cay (xem cac test rieng cho MEDIUM/LOW).
        videos = {
            "vidJ1": VideoInfo(video_id="vidJ1", title="Tiên Nghịch Tập 1",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-01",
                               duration_seconds=1000.0),
            "vidJ2": VideoInfo(video_id="vidJ2", title="Tiên Nghịch Tập 2",
                               channel_id=cid, channel_title="Kênh nhiều series",
                               thumbnail_url="", published_at="2026-01-02",
                               duration_seconds=1000.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        lan_1 = self.svc.discover_channel(self.admin, source["source_id"])
        self.assertIn("vidJ1", lan_1.confident_imports)
        self.assertIn("vidJ2", lan_1.confident_imports)

        import_j1 = self.store.get_import_by_video_id("vidJ1")
        self.svc.reject_import(self.admin, import_j1.import_id, reason="trùng bản dịch khác")

        lan_2 = self.svc.discover_channel(self.admin, source["source_id"])
        # Ca hai video da co quyet dinh CUOI CUNG (REJECTED/AUTO_IMPORTED) —
        # khong con gi de gom nhom/tao lai.
        self.assertEqual(lan_2.already_tracked, 2)
        self.assertEqual(lan_2.candidate_groups, 0)
        import_sau = self.store.get_import_by_video_id("vidJ1")
        self.assertEqual(import_sau.status, ImportStatus.REJECTED)
        self.assertIn("trùng bản dịch khác", import_sau.reason)
        import_j2 = self.store.get_import_by_video_id("vidJ2")
        self.assertEqual(import_j2.status, ImportStatus.AUTO_IMPORTED)

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


class ChannelDiscoveryConfidencePolicyTest(unittest.TestCase):
    """Auto-Ingestion Phase 5 pre-merge hardening — chinh sach tin cay BA
    HANG cho cum ung vien series MOI (`group_confidence`). CHI hang HIGH
    duoc phep tao `AnimationSeries`/`SeriesMapping` MOI; MEDIUM/LOW giu lai
    la ung vien cho quan tri xem, KHONG BAO GIO tu tao series."""

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

    def test_cum_3_tap_manh_duoc_tao_series_nhap(self):
        cid, playlist_id = "UC" + "p1" * 11, "UUp1"
        source = self._tao_nguon_kenh(cid)
        videos = {
            f"vidStrong300{i}": VideoInfo(
                video_id=f"vidStrong300{i}", title=f"Phàm Nhân Tu Tiên Tập {i}",
                channel_id=cid, channel_title="Kênh nhiều series", thumbnail_url="",
                published_at=f"2026-01-0{i}", duration_seconds=1000.0)
            for i in range(1, 4)
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])

        self.assertEqual(ket_qua.candidate_groups, 1)
        self.assertEqual(ket_qua.new_series_created, 1)
        cum = ket_qua.groups[0]
        self.assertEqual(cum.confidence_tier, "high")
        self.assertTrue(cum.created_new_series)
        self.assertTrue(cum.series_id)
        series = self.animation.get_series(cum.series_id)
        self.assertEqual(series.state, PublishState.DRAFT)
        for vid in videos:
            self.assertIn(vid, ket_qua.confident_imports)

    def test_cum_2_tap_manh_duoc_tao_series_nhap(self):
        cid, playlist_id = "UC" + "p2" * 11, "UUp2"
        source = self._tao_nguon_kenh(cid)
        videos = {
            "vidStrong2001": VideoInfo(
                video_id="vidStrong2001", title="Đấu La Đại Lục Tập 1",
                channel_id=cid, channel_title="Kênh nhiều series", thumbnail_url="",
                published_at="2026-01-01", duration_seconds=1000.0),
            "vidStrong2002": VideoInfo(
                video_id="vidStrong2002", title="Đấu La Đại Lục Tập 2",
                channel_id=cid, channel_title="Kênh nhiều series", thumbnail_url="",
                published_at="2026-01-02", duration_seconds=1000.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])

        self.assertEqual(ket_qua.new_series_created, 1)
        cum = ket_qua.groups[0]
        self.assertEqual(cum.confidence_tier, "high")
        self.assertIn("vidStrong2001", ket_qua.confident_imports)
        self.assertIn("vidStrong2002", ket_qua.confident_imports)

    def test_singleton_ngau_nhien_khong_lien_quan_khong_tao_series(self):
        """MOT video DUY NHAT, KHONG co tin hieu tap/dai tap gi ca (tieu de
        "ngau nhien") — LOW, khong du dieu kien de tu tao series."""
        cid, playlist_id = "UC" + "p3" * 11, "UUp3"
        source = self._tao_nguon_kenh(cid)
        videos = {
            "vidRandom001": VideoInfo(
                video_id="vidRandom001", title="Vlog ngày cuối tuần của tôi",
                channel_id=cid, channel_title="Kênh nhiều series", thumbnail_url="",
                published_at="2026-01-01", duration_seconds=500.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])

        self.assertEqual(ket_qua.new_series_created, 0)
        cum = ket_qua.groups[0]
        self.assertEqual(cum.confidence_tier, "low")
        self.assertEqual(cum.series_id, "")
        self.assertNotIn("vidRandom001", ket_qua.confident_imports)
        self.assertIn("vidRandom001", ket_qua.pending_review)
        _rows, tong_series = self.animation.find_series(include_removed=True)
        self.assertEqual(tong_series, 0)

    def test_singleton_mo_ho_khong_tao_series(self):
        """MOT video DUY NHAT voi tin hieu YEU/mo ho (khong co tu khoa tap
        ro rang, tieu de chung chung) — van KHONG du de tu tao series."""
        cid, playlist_id = "UC" + "p4" * 11, "UUp4"
        source = self._tao_nguon_kenh(cid)
        videos = {
            "vidAmbig001": VideoInfo(
                video_id="vidAmbig001", title="Cập nhật mới nhất từ kênh",
                channel_id=cid, channel_title="Kênh nhiều series", thumbnail_url="",
                published_at="2026-01-01", duration_seconds=300.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])

        self.assertEqual(ket_qua.new_series_created, 0)
        self.assertEqual(ket_qua.groups[0].series_id, "")
        self.assertIn("vidAmbig001", ket_qua.pending_review)

    def test_singleton_chi_la_ban_tong_hop_khong_tao_series(self):
        """MOT video DUY NHAT la ban TONG HOP CA SERIES (khong co tap don
        le nao) — KHONG du dieu kien tu tao series, du co tin hieu dai tap."""
        cid, playlist_id = "UC" + "p5" * 11, "UUp5"
        source = self._tao_nguon_kenh(cid)
        videos = {
            "vidComp001": VideoInfo(
                video_id="vidComp001", title="Toàn Chức Pháp Sư Trọn Bộ Full",
                channel_id=cid, channel_title="Kênh nhiều series", thumbnail_url="",
                published_at="2026-01-01", duration_seconds=36000.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])

        self.assertEqual(ket_qua.new_series_created, 0)
        cum = ket_qua.groups[0]
        self.assertIn(cum.confidence_tier, ("low", "medium"))
        self.assertEqual(cum.series_id, "")
        self.assertIn("vidComp001", ket_qua.pending_review)

    def test_kenh_nhieu_nhiu_series_that_lan_video_khong_lien_quan(self):
        """Kenh "on ao": MOT series that (2 tap mach lac) + MOT video don
        le khong lien quan — CHI series that duoc tao, video le KHONG tao
        series rieng cho no."""
        cid, playlist_id = "UC" + "p6" * 11, "UUp6"
        source = self._tao_nguon_kenh(cid)
        videos = {
            "vidReal001": VideoInfo(
                video_id="vidReal001", title="Thần Ấn Vương Tọa Tập 1",
                channel_id=cid, channel_title="Kênh nhiều series", thumbnail_url="",
                published_at="2026-01-01", duration_seconds=1000.0),
            "vidReal002": VideoInfo(
                video_id="vidReal002", title="Thần Ấn Vương Tọa Tập 2",
                channel_id=cid, channel_title="Kênh nhiều series", thumbnail_url="",
                published_at="2026-01-02", duration_seconds=1000.0),
            "vidNoise001": VideoInfo(
                video_id="vidNoise001", title="Cảm ơn 1 triệu subscriber!",
                channel_id=cid, channel_title="Kênh nhiều series", thumbnail_url="",
                published_at="2026-01-03", duration_seconds=200.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])

        self.assertEqual(ket_qua.candidate_groups, 2)
        self.assertEqual(ket_qua.new_series_created, 1)
        nhom_that = next(g for g in ket_qua.groups if "vidReal001" in g.video_ids)
        nhom_le = next(g for g in ket_qua.groups if "vidNoise001" in g.video_ids)
        self.assertEqual(nhom_that.confidence_tier, "high")
        self.assertTrue(nhom_that.created_new_series)
        self.assertEqual(nhom_le.series_id, "")
        self.assertIn("vidReal001", ket_qua.confident_imports)
        self.assertIn("vidReal002", ket_qua.confident_imports)
        self.assertIn("vidNoise001", ket_qua.pending_review)
        _rows, tong_series = self.animation.find_series(include_removed=True)
        self.assertEqual(tong_series, 1)

    def test_gom_nhom_khong_bac_cau_qua_mot_video_cau_noi_mo_ho(self):
        """`_gom_nhom_ung_vien` KHONG duoc phep gop A-B-C thanh MOT cum chi
        vi A~B va B~C (single-linkage bac cau) khi A VA C thuc su KHONG
        tuong dong nhau — fix pre-merge hardening (grouping robustness).
        Ba tieu de duoc dung sao cho A~B >= 0.6 (Jaccard), B~C >= 0.6, nhung
        A~C < 0.6, chi khac nhau boi CANONICAL NAME (khong phai boi so tap)
        de kiem tra dung logic gom nhom, khong phai logic tap."""
        cid, playlist_id = "UC" + "p7" * 11, "UUp7"
        source = self._tao_nguon_kenh(cid)
        videos = {
            "vidChainA": VideoInfo(
                video_id="vidChainA", title="a b c d | Tập 1",
                channel_id=cid, channel_title="Kênh nhiều series", thumbnail_url="",
                published_at="2026-01-01", duration_seconds=1000.0),
            "vidChainB": VideoInfo(
                video_id="vidChainB", title="a b c e | Tập 1",
                channel_id=cid, channel_title="Kênh nhiều series", thumbnail_url="",
                published_at="2026-01-02", duration_seconds=1000.0),
            "vidChainC": VideoInfo(
                video_id="vidChainC", title="a b e f | Tập 1",
                channel_id=cid, channel_title="Kênh nhiều series", thumbnail_url="",
                published_at="2026-01-03", duration_seconds=1000.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        # Xac nhan tien de: A~B va B~C tren nguong CU (Jaccard single-linkage
        # se gop chung), nhung A~C duoi nguong — chinh xac tinh huong "cau
        # noi mo ho" dac ta canh bao.
        from server.series_fingerprint import extract_fingerprint, similarity
        fp_a = extract_fingerprint("a b c d | Tập 1", channel_id=cid)
        fp_b = extract_fingerprint("a b c e | Tập 1", channel_id=cid)
        fp_c = extract_fingerprint("a b e f | Tập 1", channel_id=cid)
        self.assertGreaterEqual(similarity(fp_a, fp_b), 0.6)
        self.assertGreaterEqual(similarity(fp_b, fp_c), 0.6)
        self.assertLess(similarity(fp_a, fp_c), 0.6)

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])

        # KHONG duoc gop ca ba thanh MOT cum — moi video la mot cum RIENG
        # (canonical_name khac nhau tuyet doi: "a b c d", "a b c e", "a b e f").
        self.assertEqual(ket_qua.candidate_groups, 3)
        for g in ket_qua.groups:
            self.assertEqual(len(g.video_ids), 1)
        _rows, tong_series = self.animation.find_series(include_removed=True)
        self.assertEqual(tong_series, 0, "khong cum nao du 2+ video de dat HIGH")


class ChannelDiscoveryConcurrencyTest(unittest.TestCase):
    """Auto-Ingestion Phase 5 pre-merge hardening — cac be mat dua nhau RIENG
    cua `discover_channel` (khac voi cac test dua nhau da co cua Phase 3 tren
    `scan_source`/`_phan_loai_va_ghi_mot_video`, van con nguyen, khong sua).
    KHONG dung thread that (MockTrustedSourceStore da co `threading.Lock`
    rieng, khong phai diem can kiem tra o day) — mo phong dua nhau bang cach
    goi LAI CUNG dieu kien dau vao nhieu lan/xen ke, kiem tra ket qua CUOI
    CUNG tat dinh (create-once qua ID tat dinh), dung nguyen tac voi cac
    test dua nhau da co (`test_hai_video_khac_nhau_dong_thoi...`)."""

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

    # -- A + D + E: hai lan goi discover_channel/_giai_quyet_hoac_tao_series ---
    # dong thoi (hoac gan nhu dong thoi) cho CUNG mot cum -> CHI mot series/
    # mapping duoc tao, khong bao gio hai.

    def test_hai_lan_goi_giai_quyet_hoac_tao_series_dong_thoi_chi_tao_mot_series(self):
        """Mo phong TRUC TIEP be mat dua nhau D/E: hai "worker" (hai lan goi
        _giai_quyet_hoac_tao_series) cung ket luan "series nay chua ton tai,
        tao moi" cho CUNG mot fingerprint/nguon — CHI mot series/mapping
        song sot, ben thua tu don rac series mo coi cua no."""
        cid = "UC" + "cc1" * 7
        source = self._tao_nguon_kenh(cid)
        from server.series_fingerprint import extract_fingerprint
        from server.video_classifier import classify_video

        fp = extract_fingerprint("Tiên Nghịch Tập 1", channel_id=cid, channel_title="Kênh")
        src = self.store.get_source(source["source_id"])
        ket_qua_rong = classify_video(
            title="Tiên Nghịch Tập 1", channel_id=cid, trusted_source=src, mappings=[])

        series_id_1, mapping_id_1, tao_moi_1, _ = self.svc._giai_quyet_hoac_tao_series(
            self.admin, source["source_id"], ket_qua=ket_qua_rong, fingerprint=fp, mappings=[])
        series_id_2, mapping_id_2, tao_moi_2, _ = self.svc._giai_quyet_hoac_tao_series(
            self.admin, source["source_id"], ket_qua=ket_qua_rong, fingerprint=fp,
            mappings=self.store.list_mappings(source["source_id"]))

        self.assertTrue(tao_moi_1)
        self.assertFalse(tao_moi_2, "lan goi thu hai PHAI nhan la da co, khong tao them")
        self.assertEqual(series_id_1, series_id_2)
        self.assertEqual(mapping_id_1, mapping_id_2)
        _rows, tong_series = self.animation.find_series(include_removed=True)
        self.assertEqual(tong_series, 1, "khong duoc de lai series mo coi cua ben thua")
        self.assertEqual(len(self.store.list_mappings(source["source_id"])), 1)

    def test_hai_lan_goi_discover_channel_dong_thoi_tren_cung_nguon_khong_trung(self):
        """A: goi discover_channel HAI LAN lien tiep (mo phong hai request
        gan nhu dong thoi tren cung nguon) — lan hai phai idempotent, khong
        tao them series/mapping/import nao."""
        cid, playlist_id = "UC" + "cc2" * 7, "UUcc2"
        source = self._tao_nguon_kenh(cid)
        videos = {
            "vidCc2001": VideoInfo(video_id="vidCc2001", title="Tiên Nghịch Tập 1",
                                   channel_id=cid, channel_title="Kênh nhiều series",
                                   thumbnail_url="", published_at="2026-01-01",
                                   duration_seconds=1000.0),
            "vidCc2002": VideoInfo(video_id="vidCc2002", title="Tiên Nghịch Tập 2",
                                   channel_id=cid, channel_title="Kênh nhiều series",
                                   thumbnail_url="", published_at="2026-01-02",
                                   duration_seconds=1000.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        lan_1 = self.svc.discover_channel(self.admin, source["source_id"])
        lan_2 = self.svc.discover_channel(self.admin, source["source_id"])

        self.assertEqual(lan_1.new_series_created, 1)
        self.assertEqual(lan_2.new_series_created, 0)
        self.assertEqual(lan_2.already_tracked, 2)
        _rows, tong_series = self.animation.find_series(include_removed=True)
        self.assertEqual(tong_series, 1)

    # -- B: discover_channel xen ke voi WebSub ---------------------------------

    def test_discover_channel_xen_ke_voi_websub_tren_cung_video(self):
        """B: WebSub xu ly TRUOC mot video (chua co mapping nao -> NEW),
        sau do discover_channel chay tren CA kenh (gom video do vao mot cum
        HIGH, tao mapping moi) — video da duoc WebSub tao ban ghi truoc do
        PHAI duoc phan loai lai DUNG (AUTO_IMPORTED qua mapping vua tao),
        khong tao ban ghi thu hai."""
        cid, playlist_id = "UC" + "cc3" * 7, "UUcc3"
        source = self._tao_nguon_kenh(cid, auto_discover=True)
        v1, v2 = "vidCc3001", "vidCc3002"
        videos = {
            v1: VideoInfo(video_id=v1, title="Tiên Nghịch Tập 1", channel_id=cid,
                         channel_title="Kênh nhiều series", thumbnail_url="",
                         published_at="2026-01-01", duration_seconds=1000.0),
            v2: VideoInfo(video_id=v2, title="Tiên Nghịch Tập 2", channel_id=cid,
                         channel_title="Kênh nhiều series", thumbnail_url="",
                         published_at="2026-01-02", duration_seconds=1000.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        # WebSub "den truoc" cho v1 — chua co mapping nao luc nay -> NEW.
        self.svc._xu_ly_mot_video_websub(self.store.get_source(source["source_id"]), v1)
        ban_ghi_truoc = self.store.get_import_by_video_id(v1)
        self.assertEqual(ban_ghi_truoc.status, ImportStatus.NEW)
        import_id_truoc = ban_ghi_truoc.import_id

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])

        self.assertEqual(ket_qua.new_series_created, 1)
        ban_ghi_sau = self.store.get_import_by_video_id(v1)
        self.assertEqual(ban_ghi_sau.status, ImportStatus.AUTO_IMPORTED)
        self.assertEqual(ban_ghi_sau.import_id, import_id_truoc, "khong tao ban ghi thu hai")
        _rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total, 2)

    # -- C: discover_channel xen ke voi doi chieu dinh ky (reconciliation) ----

    def test_discover_channel_xen_ke_voi_doi_chieu_dinh_ky(self):
        """C: discover_channel tao mapping/nhap MOT video trong cum, sau do
        doi chieu dinh ky (goi lai `scan_source` cho CUNG nguon) chay tren
        CA hai video — video da nhap phai la already_tracked, KHONG phan
        loai lai/tao trung."""
        cid, playlist_id = "UC" + "cc4" * 7, "UUcc4"
        source = self._tao_nguon_kenh(cid, auto_discover=True)
        videos = {
            "vidCc4001": VideoInfo(video_id="vidCc4001", title="Tiên Nghịch Tập 1",
                                   channel_id=cid, channel_title="Kênh nhiều series",
                                   thumbnail_url="", published_at="2026-01-01",
                                   duration_seconds=1000.0),
            "vidCc4002": VideoInfo(video_id="vidCc4002", title="Tiên Nghịch Tập 2",
                                   channel_id=cid, channel_title="Kênh nhiều series",
                                   thumbnail_url="", published_at="2026-01-02",
                                   duration_seconds=1000.0),
        }
        self._dat_client_gia(self._client_don_gian(cid, playlist_id, videos))

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])
        self.assertEqual(ket_qua.new_series_created, 1)

        doi_chieu = self.svc.run_reconciliation(source_id=source["source_id"])
        self.assertEqual(doi_chieu["sources_checked"], 1)
        self.assertEqual(doi_chieu["sources_failed"], 0)
        # "videos_detected" = so video THAY trong trang quet (ca video da
        # theo doi tu truoc), KHONG phai so video MOI — bang chung idempotent
        # THAT nam o cho KHONG co ban ghi/series nao bi tao them ben duoi.
        self.assertEqual(doi_chieu["videos_detected"], 2)
        _rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total, 2)
        _rows2, tong_series = self.animation.find_series(include_removed=True)
        self.assertEqual(tong_series, 1)

    # -- F: kham pha toan kenh dua voi nhap thu cong cung slot tap -------------

    def test_discover_channel_dua_voi_nhap_thu_cong_cung_slot_tap(self):
        """F: mot video KHAC trong CUNG series da duoc quan tri nhap THU
        CONG (qua import_video, gan cung so tap) TRUOC khi discover_channel
        chay — discover_channel PHAI bao CONFLICT cho video con lai (cung so
        tap), KHONG ghi de tap thu cong da co."""
        cid, playlist_id = "UC" + "cc5" * 7, "UUcc5"
        source = self._tao_nguon_kenh(cid)
        series = self.animation.create_series(
            AnimationSeries(owner_id="author_1", title="Tiên Nghịch"))
        v_thu_cong, v_tu_dong = "vidCc5Manual", "vidCc5Auto"
        videos = {
            v_thu_cong: VideoInfo(video_id=v_thu_cong, title="Tiên Nghịch (bản thủ công)",
                                  channel_id=cid, channel_title="Kênh nhiều series",
                                  thumbnail_url="", published_at="2026-01-01",
                                  duration_seconds=1000.0),
            v_tu_dong: VideoInfo(video_id=v_tu_dong, title="Tiên Nghịch Tập 9",
                                 channel_id=cid, channel_title="Kênh nhiều series",
                                 thumbnail_url="", published_at="2026-01-02",
                                 duration_seconds=1000.0),
        }
        # Giai doan 1: kenh CHI co video_thu_cong (v_tu_dong CHUA xuat hien
        # trong playlist) — tranh scan_source tu dong chiem slot 9 truoc
        # khi ta gan thu cong (video_thu_cong khong co so tap trong tieu de
        # nen luon PENDING sau quet, bat ke auto_import).
        client = self._client_don_gian(cid, playlist_id, {v_thu_cong: videos[v_thu_cong]})
        self._dat_client_gia(client)

        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=series.series_id,
            aliases=["tiên nghịch"], include_keywords=[], exclude_keywords=[])
        self.svc.scan_source(self.admin, source["source_id"])
        import_thu_cong = self.store.get_import_by_video_id(v_thu_cong)
        self.svc.set_import_series(
            self.admin, import_thu_cong.import_id, series_id=series.series_id,
            episode_number=9)
        nhap = self.svc.import_video(self.admin, import_thu_cong.import_id, publish=False)
        self.assertEqual(nhap["status"], "imported")

        # Giai doan 2: v_tu_dong gio "xuat hien" tren kenh (mo phong video
        # duoc dang SAU, hoac discover_channel la lan quet DAU tien thay no).
        client._videos[v_tu_dong] = videos[v_tu_dong]
        client._playlist_items[playlist_id] = (
            [_video_item(v_thu_cong), _video_item(v_tu_dong)], "")

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])

        # v_tu_dong cung suy ra so tap 9 (da bi chiem) -> CONFLICT, khong
        # ghi de tap thu cong.
        import_tu_dong = self.store.get_import_by_video_id(v_tu_dong)
        self.assertEqual(import_tu_dong.status, ImportStatus.CONFLICT)
        tap_9 = [e for e in self.animation.list_episodes(series.series_id)
                if e.order_index == 9]
        self.assertEqual(len(tap_9), 1)
        self.assertEqual(tap_9[0].external_id, v_thu_cong)


class _FakeYouTubeClientLoiSauTrangDau(FakeYouTubeClient):
    """Mo phong loi quota/timeout xay ra o TRANG THU HAI cua phan trang
    playlist (trang dau thanh cong) — dung cho test "partial page failure"."""

    def __init__(self, *, so_trang_thanh_cong: int = 1, **kw):
        super().__init__(**kw)
        self._so_trang_thanh_cong = so_trang_thanh_cong
        self._so_lan_goi = 0

    def list_playlist_items(self, playlist_id, *, page_token="", max_results=50):
        self._so_lan_goi += 1
        if self._so_lan_goi > self._so_trang_thanh_cong:
            raise YouTubeApiError("Đã vượt hạn mức YouTube Data API (quota exceeded).")
        return super().list_playlist_items(playlist_id, page_token=page_token,
                                           max_results=max_results)


class ChannelDiscoveryYouTubeFailureTest(unittest.TestCase):
    """Auto-Ingestion Phase 5 pre-merge hardening — chiu loi/han muc YouTube
    Data API cua `discover_channel` (bounded, khong giao dich mot nua, an
    toan de thu lai — dac ta muc 5)."""

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

    def test_loi_youtube_ghi_lai_last_error_khong_tao_gi_ca(self):
        """Kenh khong doc duoc (khong co trong FakeYouTubeClient) -> nem
        YouTubeApiError, ghi lai last_error_at/last_error_message (cung
        chinh sach voi scan_source), KHONG tao VideoImport/series nao."""
        cid = "UC" + "e1" * 11
        source = self._tao_nguon_kenh(cid)
        self._dat_client_gia(FakeYouTubeClient())  # khong co kenh nao -> loi.

        with self.assertRaises(YouTubeApiError):
            self.svc.discover_channel(self.admin, source["source_id"])

        updated = self.store.get_source(source["source_id"])
        self.assertTrue(updated.last_error_at)
        self.assertTrue(updated.last_error_message)
        _rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total, 0)
        _rows2, tong_series = self.animation.find_series(include_removed=True)
        self.assertEqual(tong_series, 0)

    def test_video_rieng_tu_trong_playlist_khong_lam_sap_ca_lan_kham_pha(self):
        """Mot video trong playlist da bi go/chuyen rieng tu (co trong
        danh sach nhung khong doc duoc chi tiet) — bi bo qua am tham, cac
        video CON LAI van duoc kham pha/nhap binh thuong."""
        cid, playlist_id = "UC" + "e2" * 11, "UUe2"
        source = self._tao_nguon_kenh(cid)
        video_con_1 = "vidE2Ok0001"
        video_con_2 = "vidE2Ok0002"
        video_mat = "vidE2Mat0001"  # co trong playlist nhung KHONG co trong `videos=`.
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh nhiều series",
                                       thumbnail_url="", uploads_playlist_id=playlist_id)},
            playlist_items={playlist_id: (
                [_video_item(video_mat), _video_item(video_con_1),
                 _video_item(video_con_2)], "")},
            videos={
                video_con_1: VideoInfo(
                    video_id=video_con_1, title="Tiên Nghịch Tập 1", channel_id=cid,
                    channel_title="Kênh nhiều series", thumbnail_url="",
                    published_at="2026-01-01", duration_seconds=1000.0),
                video_con_2: VideoInfo(
                    video_id=video_con_2, title="Tiên Nghịch Tập 2", channel_id=cid,
                    channel_title="Kênh nhiều series", thumbnail_url="",
                    published_at="2026-01-02", duration_seconds=1000.0),
            },
        )
        self._dat_client_gia(client)

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])

        self.assertEqual(ket_qua.videos_discovered, 2, "video mat bi bo qua am tham")
        self.assertEqual(ket_qua.new_series_created, 1)
        self.assertIn(video_con_1, ket_qua.confident_imports)
        self.assertIn(video_con_2, ket_qua.confident_imports)

    def test_loi_o_trang_hai_khong_tao_video_import_nao_ca(self):
        """Loi xay ra o TRANG THU HAI cua phan trang playlist (quota het
        giua chung) — toan bo lan goi phai nem loi SACH, KHONG duoc ghi mot
        phan VideoImport/series nao ca (khong "giao dich mot nua"), an toan
        de thu lai nguyen ven."""
        cid, playlist_id = "UC" + "e3" * 11, "UUe3"
        source = self._tao_nguon_kenh(cid)
        video_id = "vidE3Ok0001"
        client = _FakeYouTubeClientLoiSauTrangDau(
            so_trang_thanh_cong=0,  # loi NGAY tu trang dau tien.
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh nhiều series",
                                       thumbnail_url="", uploads_playlist_id=playlist_id)},
            playlist_items={playlist_id: (
                [_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Tiên Nghịch Tập 1", channel_id=cid,
                channel_title="Kênh nhiều series", thumbnail_url="",
                published_at="2026-01-01", duration_seconds=1000.0)},
        )
        self._dat_client_gia(client)

        with self.assertRaises(YouTubeApiError):
            self.svc.discover_channel(self.admin, source["source_id"], max_pages=2)

        _rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total, 0)

    def test_thu_lai_sau_loi_thanh_cong_khong_de_lai_rac(self):
        """Chay lai discover_channel SAU mot lan that bai (nguon tam thoi
        khong doc duoc) — lan thu hai (khi YouTube da hoat dong lai) phai
        thanh cong SACH, khong bi anh huong boi lan that bai truoc."""
        cid, playlist_id = "UC" + "e4" * 11, "UUe4"
        source = self._tao_nguon_kenh(cid)
        self._dat_client_gia(FakeYouTubeClient())  # loi lan dau.
        with self.assertRaises(YouTubeApiError):
            self.svc.discover_channel(self.admin, source["source_id"])

        video_id = "vidE4Ok0001"
        client_tot = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh nhiều series",
                                       thumbnail_url="", uploads_playlist_id=playlist_id)},
            playlist_items={playlist_id: ([_video_item(video_id)], "")},
            videos={video_id: VideoInfo(
                video_id=video_id, title="Tiên Nghịch Tập 1", channel_id=cid,
                channel_title="Kênh nhiều series", thumbnail_url="",
                published_at="2026-01-01", duration_seconds=1000.0)},
        )
        self._dat_client_gia(client_tot)

        ket_qua = self.svc.discover_channel(self.admin, source["source_id"])
        self.assertEqual(ket_qua.videos_discovered, 1)
        _rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total, 1)

    def test_max_pages_bi_chan_theo_MAX_SCAN_PAGES(self):
        """`discover_channel` tu no khong tu chan `max_pages` (dac ta chan o
        tang route HTTP, xem `main.py::admin_discover_channel`, cung mo hinh
        voi `/scan`) — kiem tra ham `_lay_video_theo_playlist` dung LAI
        (tai su dung, khong ma rieng) tuan thu gioi han neu goi truc tiep
        voi mot gia tri vuot `MAX_SCAN_PAGES`."""
        cid, playlist_id = "UC" + "e5" * 11, "UUe5"
        source = self._tao_nguon_kenh(cid)
        ids = [f"vidE5_{i:03d}" for i in range(MAX_SCAN_PAGES + 3)]
        # Moi "trang" gia lap CHINH XAC MOT video, de dem so trang thuc su
        # duoc doc qua so lan `list_playlist_items` duoc goi.
        playlist_items = {}
        token_truoc = ""
        for i, vid in enumerate(ids):
            token_ke = f"tok{i}" if i < len(ids) - 1 else ""
            playlist_items[token_truoc or playlist_id] = ([_video_item(vid)], token_ke)
            token_truoc = token_ke
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh nhiều series",
                                       thumbnail_url="", uploads_playlist_id=playlist_id)},
            playlist_items=playlist_items,
            videos={vid: VideoInfo(
                video_id=vid, title=f"Tiên Nghịch Tập {i + 1}", channel_id=cid,
                channel_title="Kênh nhiều series", thumbnail_url="",
                published_at=f"2026-01-{i + 1:02d}", duration_seconds=1000.0)
                for i, vid in enumerate(ids)},
        )
        self._dat_client_gia(client)

        # Goi voi max_pages VUOT gioi han — ham noi bo tu gioi han lai dung
        # MAX_SCAN_PAGES trang (mot video/trang trong fixture nay).
        ket_qua = self.svc.discover_channel(
            self.admin, source["source_id"], max_pages=MAX_SCAN_PAGES + 100)
        self.assertEqual(ket_qua.videos_discovered, MAX_SCAN_PAGES)


if __name__ == "__main__":
    unittest.main()
