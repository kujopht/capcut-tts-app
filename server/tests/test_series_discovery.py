"""
Test cho `TrustedSourceService.discover_series_from_seed` (Auto-Ingestion
Phase 1 — "Seed Video -> Series Discovery -> Backfill"). Dung lai FakeYouTubeClient
tu `test_trusted_source_service.py` — cung triet ly: mot client YouTube GIA
de kiem soat hoan toan du lieu, tap trung vao NGHIEP VU.
"""

from __future__ import annotations

import unittest

from server.adapters import MockMetadataStore
from server.animation_domain import AnimationSeries
from server.animation_store import MockAnimationStore
from server.domain import Profile, PublishState
from server.trusted_source_domain import ImportStatus
from server.trusted_source_service import TrustedSourceService
from server.trusted_source_store import MockTrustedSourceStore
from server.tests.test_trusted_source_service import FakeYouTubeClient, _video_item
from server.youtube_client import ChannelInfo, VideoInfo


class SeriesDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.store = MockTrustedSourceStore()
        self.animation = MockAnimationStore()
        self.metadata = MockMetadataStore()
        self.svc = TrustedSourceService(
            self.store, self.animation, self.metadata, youtube_api_key="fake-key")
        self.admin = Profile(user_id="admin_1", email="admin@fanfic.world")

    def _dat_client_gia(self, client: FakeYouTubeClient):
        self.svc._youtube = lambda: client  # type: ignore[method-assign]

    def _tao_nguon(self, **kw):
        mac_dinh = {"source_type": "youtube_video", "display_name": "Nguồn seed"}
        mac_dinh.update(kw)
        return self.svc.create_source(self.admin, **mac_dinh)

    # -- existing-series match ------------------------------------------------

    def test_seed_khop_series_da_co(self):
        series = self.animation.create_series(
            AnimationSeries(owner_id="author_1", title="Reincarnation no Kaben"))
        cid = "UC" + "e" * 22
        source = self._tao_nguon(youtube_video_id="vidSeed000A", auto_import=True,
                                 minimum_confidence=0.1)
        self.svc.create_mapping(
            self.admin, source["source_id"], animation_series_id=series.series_id,
            aliases=["reincarnation no kaben"], include_keywords=[], exclude_keywords=[])

        client = FakeYouTubeClient(videos={
            "vidSeed000A": VideoInfo(
                video_id="vidSeed000A", title="Reincarnation no Kaben Tập 5",
                channel_id=cid, channel_title="Kênh E", thumbnail_url="",
                published_at="2026-01-01", duration_seconds=1000.0),
        })
        self._dat_client_gia(client)

        ket_qua = self.svc.discover_series_from_seed(
            self.admin, source["source_id"], youtube_video_id="vidSeed000A")

        self.assertTrue(ket_qua.resolution.matched)
        self.assertEqual(ket_qua.series_id, series.series_id)
        self.assertFalse(ket_qua.created_new_series)
        self.assertEqual(ket_qua.candidates_scanned, 1)
        self.assertIn("vidSeed000A", ket_qua.confident_imports)

    # -- new-series discovery + backfill --------------------------------------

    def test_seed_khong_khop_tao_series_moi_va_backfill(self):
        cid = "UC" + "f" * 22
        upload_playlist = "UUfff"
        source = self._tao_nguon(youtube_video_id="vidNew0001", auto_import=True,
                                 minimum_confidence=0.1)

        v1, v2, v3 = "vidNew0001", "vidNew0002", "vidNew0003"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh F",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: (
                [_video_item(v1), _video_item(v2), _video_item(v3)], "")},
            videos={
                v1: VideoInfo(video_id=v1, title="Reincarnation no Kaben Tập 1",
                             channel_id=cid, channel_title="Kênh F", thumbnail_url="",
                             published_at="2026-01-01", duration_seconds=1000.0),
                v2: VideoInfo(video_id=v2, title="Reincarnation no Kaben Tập 2",
                             channel_id=cid, channel_title="Kênh F", thumbnail_url="",
                             published_at="2026-01-02", duration_seconds=1000.0),
                v3: VideoInfo(video_id=v3, title="ALL IN ONE | Reincarnation no Kaben "
                              "Tập 1-13 | Sức Mạnh | Kênh F", channel_id=cid,
                             channel_title="Kênh F", thumbnail_url="",
                             published_at="2026-01-03", duration_seconds=36000.0),
            },
        )
        self._dat_client_gia(client)

        ket_qua = self.svc.discover_series_from_seed(
            self.admin, source["source_id"], youtube_video_id=v1)

        self.assertFalse(ket_qua.resolution.matched)
        self.assertTrue(ket_qua.created_new_series)
        self.assertTrue(ket_qua.series_id)
        self.assertTrue(ket_qua.mapping_id)
        self.assertEqual(ket_qua.candidates_scanned, 3)

        series = self.animation.get_series(ket_qua.series_id)
        self.assertEqual(series.title, "Reincarnation no Kaben")

        # v1 (seed) + v2 (tap don, cung series) -> confident (auto_import=True).
        self.assertIn(v1, ket_qua.confident_imports)
        self.assertIn(v2, ket_qua.confident_imports)
        # v3 la DAI tap (Tập 1-13) — KHONG BAO GIO tu dong nhap, xem
        # `video_classifier`/`episode_parser`.
        self.assertIn(v3, ket_qua.pending_review)

        rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total, 3)

    def test_video_khong_lien_quan_bi_loai_hoan_toan(self):
        cid = "UC" + "g" * 22
        upload_playlist = "UUggg"
        source = self._tao_nguon(youtube_video_id="vidRel00001", auto_import=True,
                                 minimum_confidence=0.1)

        seed, khac = "vidRel00001", "vidUnrelated"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh G",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(seed), _video_item(khac)], "")},
            videos={
                seed: VideoInfo(video_id=seed, title="Reincarnation no Kaben Tập 1",
                                channel_id=cid, channel_title="Kênh G", thumbnail_url="",
                                published_at="2026-01-01", duration_seconds=1000.0),
                khac: VideoInfo(video_id=khac, title="Tiên Nghịch Tập 1", channel_id=cid,
                               channel_title="Kênh G", thumbnail_url="",
                               published_at="2026-01-02", duration_seconds=1000.0),
            },
        )
        self._dat_client_gia(client)

        ket_qua = self.svc.discover_series_from_seed(
            self.admin, source["source_id"], youtube_video_id=seed)

        self.assertIn(seed, ket_qua.confident_imports)
        # Video khong lien quan KHONG duoc tao VideoImport nao ca.
        self.assertNotIn(khac, ket_qua.confident_imports)
        self.assertNotIn(khac, ket_qua.pending_review)
        rows, total = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(total, 1)
        loai_trong_bao_cao = [c for c in ket_qua.candidates if c.video_id == khac]
        self.assertEqual(len(loai_trong_bao_cao), 1)
        self.assertTrue(loai_trong_bao_cao[0].excluded)

    # -- idempotency: discover lai TREN CUNG seed -----------------------------

    def test_kham_pha_lai_tren_cung_seed_idempotent(self):
        cid = "UC" + "h" * 22
        upload_playlist = "UUhhh2"
        source = self._tao_nguon(youtube_video_id="vidIdem0001", auto_import=True,
                                 minimum_confidence=0.1)
        v1 = "vidIdem0001"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh H2",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(v1)], "")},
            videos={v1: VideoInfo(
                video_id=v1, title="Reincarnation no Kaben Tập 1", channel_id=cid,
                channel_title="Kênh H2", thumbnail_url="", published_at="2026-01-01",
                duration_seconds=1000.0)},
        )
        self._dat_client_gia(client)

        lan_1 = self.svc.discover_series_from_seed(
            self.admin, source["source_id"], youtube_video_id=v1)
        self.assertTrue(lan_1.created_new_series)

        lan_2 = self.svc.discover_series_from_seed(
            self.admin, source["source_id"], youtube_video_id=v1)
        # Lan 2: mapping/series VUA TAO gio da khop qua alias -> resolver
        # nhan la "series da co", KHONG tao them series/mapping thu hai.
        self.assertTrue(lan_2.resolution.matched)
        self.assertFalse(lan_2.created_new_series)
        self.assertEqual(lan_2.series_id, lan_1.series_id)

        _, tong_series = self.animation.find_series(include_removed=True)
        self.assertEqual(tong_series, 1)
        _, tong_import = self.store.find_imports(trusted_source_id=source["source_id"])
        self.assertEqual(tong_import, 1)

    def test_kham_pha_lai_tren_seed_diem_thap_van_khong_tao_series_trung(self):
        """Bug thuc te tim thay qua real DEV E2E: nguon kieu `youtube_video`
        (khong co `youtube_channel_id` cau hinh san -> khong bao gio co tin
        hieu "kênh khớp") VA seed la mot DAI tap (khong doc duoc so tap ->
        khong co tin hieu "phát hiện tập") CHI dat confidence 0.35 (alias
        don thuan). Truoc khi sua, existing-series resolver doi confidence
        >= 0.5 nen KHONG BAO GIO nhan la "da khop", va MOI lan discover lai
        deu tao mot series+mapping MOI — chinh alias da khop la bang chung
        DU, khong can them nguong confidence tong hop."""
        cid = "UC" + "m" * 22
        upload_playlist = "UUmmm2"
        source = self._tao_nguon(youtube_video_id="vidLowC0001", auto_import=True,
                                 minimum_confidence=0.1)
        v1 = "vidLowC0001"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh M2",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(v1)], "")},
            videos={v1: VideoInfo(
                video_id=v1, title="Reincarnation no Kaben Tập 1-13", channel_id=cid,
                channel_title="Kênh M2", thumbnail_url="", published_at="2026-01-01",
                duration_seconds=36000.0)},
        )
        self._dat_client_gia(client)

        lan_1 = self.svc.discover_series_from_seed(
            self.admin, source["source_id"], youtube_video_id=v1)
        self.assertTrue(lan_1.created_new_series)
        self.assertLess(lan_1.resolution.confidence, 0.5, "kịch bản phải thật sự ở vùng điểm thấp")

        lan_2 = self.svc.discover_series_from_seed(
            self.admin, source["source_id"], youtube_video_id=v1)
        self.assertTrue(lan_2.resolution.matched)
        self.assertFalse(lan_2.created_new_series)
        self.assertEqual(lan_2.series_id, lan_1.series_id)

        _, tong_series = self.animation.find_series(include_removed=True)
        self.assertEqual(tong_series, 1)
        _, tong_mapping_1 = 0, len(self.store.list_mappings(source["source_id"]))
        self.assertEqual(tong_mapping_1, 1)

    # -- quyet dinh quan tri duoc giu (khong bi doi khi discover lai) --------

    def test_quyet_dinh_quan_tri_duoc_giu_khi_kham_pha_lai(self):
        """Discover lan 2 tren CUNG seed (sau khi da khop series co san qua
        lan 1) CHI xu ly lai chinh seed (khong quet lai ca kenh — dac ta chi
        yeu cau quet kenh khi "does NOT match an existing series"). Day la
        noi RO RANG nhat de kiem tra "existing admin decisions must win":
        seed bi quan tri TU CHOI thu cong, roi discover lai — quyet dinh
        REJECTED phai duoc giu nguyen, KHONG quay lai pending/confident."""
        cid = "UC" + "i" * 22
        upload_playlist = "UUiii2"
        source = self._tao_nguon(youtube_video_id="vidKeep0001", auto_import=True,
                                 minimum_confidence=0.1)
        seed = "vidKeep0001"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh I2",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(seed)], "")},
            videos={seed: VideoInfo(
                video_id=seed, title="Reincarnation no Kaben Tập 1", channel_id=cid,
                channel_title="Kênh I2", thumbnail_url="", published_at="2026-01-01",
                duration_seconds=1000.0)},
        )
        self._dat_client_gia(client)

        lan_1 = self.svc.discover_series_from_seed(
            self.admin, source["source_id"], youtube_video_id=seed)
        self.assertIn(seed, lan_1.confident_imports)

        # Quan tri TU CHOI thu cong seed sau khi discovery lan dau nhap no.
        import_seed = self.store.get_import_by_video_id(seed)
        self.svc.reject_import(self.admin, import_seed.import_id, reason="sai chất lượng")

        lan_2 = self.svc.discover_series_from_seed(
            self.admin, source["source_id"], youtube_video_id=seed)
        # Quyet dinh REJECTED phai duoc GIU NGUYEN — khong quay lai PENDING/
        # confident_imports.
        self.assertIn(seed, lan_2.excluded)
        self.assertNotIn(seed, lan_2.confident_imports)
        import_sau = self.store.get_import_by_video_id(seed)
        self.assertEqual(import_sau.status, ImportStatus.REJECTED)
        self.assertIn("sai chất lượng", import_sau.reason)

    # -- xung dot so tap khi backfill ------------------------------------------

    def test_xung_dot_so_tap_trong_khi_backfill(self):
        """Hai video CUNG so tap trong MOT lan backfill — `episodes_by_series`
        phai duoc cap nhat NGAY sau video dau (khong doi lan goi sau), de
        video thu hai bi bao CONFLICT thay vi tao them mot tap trung so."""
        cid = "UC" + "j" * 22
        upload_playlist = "UUjjj2"
        source = self._tao_nguon(youtube_video_id="vidConf0001", auto_import=True,
                                 minimum_confidence=0.1)
        seed, trung = "vidConf0001", "vidConflict1"
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh J2",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: (
                [_video_item(seed), _video_item(trung)], "")},
            videos={
                seed: VideoInfo(video_id=seed, title="Reincarnation no Kaben Tập 1",
                                channel_id=cid, channel_title="Kênh J2", thumbnail_url="",
                                published_at="2026-01-01", duration_seconds=1000.0),
                # Cung so tap 1 nhung video KHAC — phai bi bao CONFLICT, khong
                # ghi de tap dau.
                trung: VideoInfo(video_id=trung, title="Reincarnation no Kaben Tập 1",
                                 channel_id=cid, channel_title="Kênh J2", thumbnail_url="",
                                 published_at="2026-01-02", duration_seconds=1000.0),
            },
        )
        self._dat_client_gia(client)

        ket_qua = self.svc.discover_series_from_seed(
            self.admin, source["source_id"], youtube_video_id=seed)

        self.assertIn(seed, ket_qua.confident_imports)
        self.assertIn(trung, ket_qua.conflicts)
        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        con_lai = next(r for r in rows if r.youtube_video_id == trung)
        self.assertEqual(con_lai.status, ImportStatus.CONFLICT)

    # -- provenance duoc bao toan khi backfill ---------------------------------

    def test_provenance_duoc_luu_khi_backfill(self):
        cid = "UC" + "k" * 22
        upload_playlist = "UUkkk2"
        source = self._tao_nguon(youtube_video_id="vidProv0001", auto_import=True,
                                 minimum_confidence=0.1)
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh Thật K",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item("vidProv0001")], "")},
            videos={"vidProv0001": VideoInfo(
                video_id="vidProv0001", title="Reincarnation no Kaben Tập 1",
                channel_id=cid, channel_title="Kênh Thật K", thumbnail_url="",
                published_at="2026-01-01", duration_seconds=1000.0)},
        )
        self._dat_client_gia(client)

        ket_qua = self.svc.discover_series_from_seed(
            self.admin, source["source_id"], youtube_video_id="vidProv0001")

        rows, _ = self.store.find_imports(trusted_source_id=source["source_id"])
        episode = self.animation.get_episode(rows[0].created_episode_id)
        self.assertEqual(episode.source_channel_id, cid)
        self.assertEqual(episode.source_channel_title, "Kênh Thật K")

    # -- thu tu ket qua on dinh -------------------------------------------------

    def test_thu_tu_ket_qua_on_dinh(self):
        cid = "UC" + "l" * 22
        upload_playlist = "UUlll2"
        source = self._tao_nguon(youtube_video_id="vidOrd0001", auto_import=True,
                                 minimum_confidence=0.1)
        ids = ["vidOrd0001", "vidOrd0002", "vidOrd0003"]
        client = FakeYouTubeClient(
            channels={cid: ChannelInfo(channel_id=cid, title="Kênh L2",
                                       thumbnail_url="", uploads_playlist_id=upload_playlist)},
            playlist_items={upload_playlist: ([_video_item(v) for v in ids], "")},
            videos={
                v: VideoInfo(video_id=v, title=f"Reincarnation no Kaben Tập {i + 1}",
                            channel_id=cid, channel_title="Kênh L2", thumbnail_url="",
                            published_at=f"2026-01-0{i + 1}", duration_seconds=1000.0)
                for i, v in enumerate(ids)
            },
        )
        self._dat_client_gia(client)

        ket_qua_1 = self.svc.discover_series_from_seed(
            self.admin, source["source_id"], youtube_video_id=ids[0])
        thu_tu_1 = [c.video_id for c in ket_qua_1.candidates]

        # Xoa het du lieu vua tao, chay lai TU DAU voi CUNG dau vao — thu tu
        # phai giong het lan truoc (khong phu thuoc thoi diem/ngau nhien).
        self.store = MockTrustedSourceStore()
        self.animation = MockAnimationStore()
        self.svc = TrustedSourceService(
            self.store, self.animation, self.metadata, youtube_api_key="fake-key")
        source_2 = self._tao_nguon(youtube_video_id="vidOrd0001", auto_import=True,
                                   minimum_confidence=0.1)
        self._dat_client_gia(client)
        ket_qua_2 = self.svc.discover_series_from_seed(
            self.admin, source_2["source_id"], youtube_video_id=ids[0])
        thu_tu_2 = [c.video_id for c in ket_qua_2.candidates]

        self.assertEqual(thu_tu_1, thu_tu_2)


if __name__ == "__main__":
    unittest.main()
