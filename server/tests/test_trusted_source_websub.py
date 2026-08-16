"""
Kiem thu tang dich vu WebSub (Phase 6, Trusted Video Sources) —
`TrustedSourceService.subscribe_source`/`unsubscribe_source`/
`handle_websub_verification`/`handle_websub_notification`/
`run_reconciliation`. Dung MOT client WebSub GIA (khong goi hub that) va
MOT client YouTube GIA (khong goi mang that), cung phong cach voi
`test_trusted_source_service.py`.
"""

import unittest
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from server.adapters import MockMetadataStore
from server.animation_domain import AnimationSeries
from server.animation_store import MockAnimationStore
from server.domain import Profile, PublishState
from server.trusted_source_domain import (
    ImportStatus,
    SubscriptionStatus,
    TrustedSourceType,
)
from server.trusted_source_service import TrustedSourceError, TrustedSourceService
from server.trusted_source_store import MockTrustedSourceStore
from server.youtube_client import ChannelInfo, VideoInfo
from server.youtube_websub import WebSubConfigError, WebSubError, compute_signature


class FakeYouTubeClient:
    def __init__(self, *, channels=None, videos=None, playlist_items=None):
        self._channels: Dict[str, ChannelInfo] = channels or {}
        self._videos: Dict[str, VideoInfo] = videos or {}
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
        return None

    def list_playlist_items(self, playlist_id, *, page_token="", max_results=50):
        return self._playlist_items.get(page_token or playlist_id, ([], ""))


class FakeWebSubClient:
    def __init__(self, *, subscribe_fails=False, unsubscribe_fails=False):
        self.subscribe_calls: List[dict] = []
        self.unsubscribe_calls: List[dict] = []
        self._subscribe_fails = subscribe_fails
        self._unsubscribe_fails = unsubscribe_fails

    def subscribe(self, *, channel_id, callback_url, secret, lease_seconds=432000):
        self.subscribe_calls.append({
            "channel_id": channel_id, "callback_url": callback_url,
            "secret": secret, "lease_seconds": lease_seconds})
        if self._subscribe_fails:
            raise WebSubError("Hub từ chối yêu cầu (HTTP 500).")

    def unsubscribe(self, *, channel_id, callback_url):
        self.unsubscribe_calls.append(
            {"channel_id": channel_id, "callback_url": callback_url})
        if self._unsubscribe_fails:
            raise WebSubError("Hub từ chối yêu cầu (HTTP 500).")


def _video_item(video_id: str) -> dict:
    return {"contentDetails": {"videoId": video_id}}


class WebSubServiceTest(unittest.TestCase):
    def setUp(self):
        self.store = MockTrustedSourceStore()
        self.animation = MockAnimationStore()
        self.metadata = MockMetadataStore()
        self.svc = TrustedSourceService(
            self.store, self.animation, self.metadata, youtube_api_key="fake-key",
            websub_callback_base_url="https://api.fanfic.world")
        self.admin = Profile(user_id="admin_1", email="admin@fanfic.world")
        self.series = self.animation.create_series(
            AnimationSeries(owner_id="author_1", title="Tiên Nghịch"))
        self.cid = "UC" + "w" * 22
        self.source = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id=self.cid,
            display_name="Kênh W", auto_import=True, minimum_confidence=0.1,
            actor_role="owner")

    def _dat_youtube_gia(self, client: FakeYouTubeClient):
        self.svc._youtube = lambda: client  # type: ignore[method-assign]

    def _dat_websub_gia(self, client: FakeWebSubClient):
        self.svc._websub = lambda: client  # type: ignore[method-assign]

    def _bat_auto_discover(self):
        self.svc.update_source(
            self.admin, self.source["source_id"], {"auto_discover": True},
            actor_role="owner")

    # ==================================================== subscribe/unsubscribe

    def test_chua_cau_hinh_callback_bao_loi_ro_rang(self):
        svc = TrustedSourceService(
            self.store, self.animation, self.metadata, youtube_api_key="fake-key")
        self.assertFalse(svc.websub_configured())
        with self.assertRaises(WebSubConfigError):
            svc.subscribe_source(self.admin, self.source["source_id"], actor_role="owner")

    def test_nguon_kieu_video_don_le_khong_dang_ky_duoc(self):
        video_source = self.svc.create_source(
            self.admin, source_type="youtube_video", youtube_video_id="vidZ0000009",
            display_name="Video lẻ", actor_role="owner")
        with self.assertRaises(TrustedSourceError):
            self.svc.subscribe_source(self.admin, video_source["source_id"], actor_role="owner")

    def test_dang_ky_thanh_cong(self):
        fake = FakeWebSubClient()
        self._dat_websub_gia(fake)
        ket_qua = self.svc.subscribe_source(self.admin, self.source["source_id"], actor_role="owner")
        self.assertEqual(ket_qua["subscription_status"], "pending")
        self.assertNotIn("websub_secret", ket_qua)  # KHONG BAO GIO ra API.

        # Bi mat CO duoc luu that trong kho (kiem qua doi tuong noi bo).
        luu = self.store.get_source(self.source["source_id"])
        self.assertTrue(luu.websub_secret)

        self.assertEqual(len(fake.subscribe_calls), 1)
        goi = fake.subscribe_calls[0]
        self.assertEqual(goi["channel_id"], self.cid)
        self.assertIn(self.source["source_id"], goi["callback_url"])
        self.assertEqual(goi["secret"], luu.websub_secret)

        events, _ = self.metadata.list_events(action="websub_subscribe")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].target_id, self.source["source_id"])
        self.assertEqual(events[0].target_type, "trusted_source")

    def test_dang_ky_that_bai_ghi_loi(self):
        fake = FakeWebSubClient(subscribe_fails=True)
        self._dat_websub_gia(fake)
        with self.assertRaises(TrustedSourceError):
            self.svc.subscribe_source(self.admin, self.source["source_id"], actor_role="owner")
        luu = self.store.get_source(self.source["source_id"])
        self.assertEqual(luu.subscription_status, SubscriptionStatus.FAILED)
        self.assertTrue(luu.last_websub_error)
        events, _ = self.metadata.list_events(action="websub_failure")
        self.assertEqual(len(events), 1)

    def test_huy_dang_ky_khi_chua_dang_ky_khong_goi_hub(self):
        fake = FakeWebSubClient()
        self._dat_websub_gia(fake)
        self.svc.unsubscribe_source(self.admin, self.source["source_id"], actor_role="owner")
        self.assertEqual(len(fake.unsubscribe_calls), 0)

    def test_huy_dang_ky_thanh_cong(self):
        fake = FakeWebSubClient()
        self._dat_websub_gia(fake)
        self.svc.subscribe_source(self.admin, self.source["source_id"], actor_role="owner")
        ket_qua = self.svc.unsubscribe_source(self.admin, self.source["source_id"], actor_role="owner")
        self.assertEqual(ket_qua["subscription_status"], "none")
        self.assertEqual(len(fake.unsubscribe_calls), 1)
        luu = self.store.get_source(self.source["source_id"])
        self.assertEqual(luu.websub_secret, "")
        events, _ = self.metadata.list_events(action="websub_unsubscribe")
        self.assertEqual(len(events), 1)

    def test_xoa_nguon_tu_huy_dang_ky_truoc(self):
        fake = FakeWebSubClient()
        self._dat_websub_gia(fake)
        self.svc.subscribe_source(self.admin, self.source["source_id"], actor_role="owner")
        self.svc.remove_source(self.admin, self.source["source_id"], actor_role="owner")
        self.assertEqual(len(fake.unsubscribe_calls), 1)

    # ==================================================== xac minh (GET)

    def test_xac_minh_nguon_khong_ton_tai_tra_none(self):
        ket_qua = self.svc.handle_websub_verification(
            source_id="khong_ton_tai", mode="subscribe",
            topic="https://www.youtube.com/feeds/videos.xml?channel_id=x",
            challenge="abc", lease_seconds="432000")
        self.assertIsNone(ket_qua)

    def test_xac_minh_topic_khong_khop_tra_none(self):
        ket_qua = self.svc.handle_websub_verification(
            source_id=self.source["source_id"], mode="subscribe",
            topic="https://www.youtube.com/feeds/videos.xml?channel_id=KHAC",
            challenge="abc", lease_seconds="432000")
        self.assertIsNone(ket_qua)

    def test_xac_minh_subscribe_thanh_cong(self):
        topic = f"https://www.youtube.com/feeds/videos.xml?channel_id={self.cid}"
        ket_qua = self.svc.handle_websub_verification(
            source_id=self.source["source_id"], mode="subscribe", topic=topic,
            challenge="thu-thach-123", lease_seconds="432000")
        self.assertEqual(ket_qua, "thu-thach-123")
        luu = self.store.get_source(self.source["source_id"])
        self.assertEqual(luu.subscription_status, SubscriptionStatus.ACTIVE)
        self.assertTrue(luu.subscription_expires_at)

    def test_xac_minh_lease_seconds_khong_hop_le_van_active_nhung_khong_co_han(self):
        topic = f"https://www.youtube.com/feeds/videos.xml?channel_id={self.cid}"
        self.svc.handle_websub_verification(
            source_id=self.source["source_id"], mode="subscribe", topic=topic,
            challenge="c", lease_seconds="khong-phai-so")
        luu = self.store.get_source(self.source["source_id"])
        self.assertEqual(luu.subscription_status, SubscriptionStatus.ACTIVE)

    def test_xac_minh_unsubscribe(self):
        topic = f"https://www.youtube.com/feeds/videos.xml?channel_id={self.cid}"
        ket_qua = self.svc.handle_websub_verification(
            source_id=self.source["source_id"], mode="unsubscribe", topic=topic,
            challenge="c2", lease_seconds="")
        self.assertEqual(ket_qua, "c2")
        luu = self.store.get_source(self.source["source_id"])
        self.assertEqual(luu.subscription_status, SubscriptionStatus.NONE)

    def test_xac_minh_denied_ghi_loi(self):
        topic = f"https://www.youtube.com/feeds/videos.xml?channel_id={self.cid}"
        ket_qua = self.svc.handle_websub_verification(
            source_id=self.source["source_id"], mode="denied", topic=topic,
            challenge="", lease_seconds="")
        self.assertEqual(ket_qua, "")
        luu = self.store.get_source(self.source["source_id"])
        self.assertEqual(luu.subscription_status, SubscriptionStatus.FAILED)
        events, _ = self.metadata.list_events(action="websub_failure")
        self.assertEqual(len(events), 1)

    def test_xac_minh_mode_la_tra_none(self):
        topic = f"https://www.youtube.com/feeds/videos.xml?channel_id={self.cid}"
        ket_qua = self.svc.handle_websub_verification(
            source_id=self.source["source_id"], mode="something-else", topic=topic,
            challenge="c", lease_seconds="")
        self.assertIsNone(ket_qua)

    # ==================================================== thong bao (POST)

    def _dang_ky_va_lay_secret(self) -> str:
        self._dat_websub_gia(FakeWebSubClient())
        self.svc.subscribe_source(self.admin, self.source["source_id"], actor_role="owner")
        return self.store.get_source(self.source["source_id"]).websub_secret

    def test_thong_bao_nguon_khong_ton_tai_tra_none(self):
        ket_qua = self.svc.handle_websub_notification(
            source_id="khong_ton_tai", body=b"<feed/>", signature_header="")
        self.assertIsNone(ket_qua)

    def test_thong_bao_chu_ky_sai_tra_false(self):
        self._dang_ky_va_lay_secret()
        ket_qua = self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=b"<feed/>",
            signature_header="sha256=" + "0" * 64)
        self.assertFalse(ket_qua)
        events, _ = self.metadata.list_events(action="websub_failure")
        self.assertEqual(len(events), 1)
        # KHONG ghi nhan la da nhan thong bao thanh cong.
        luu = self.store.get_source(self.source["source_id"])
        self.assertEqual(luu.last_notification_at, "")

    def test_thong_bao_chu_ky_khong_phai_hex_tra_false_khong_sap(self):
        """Header `X-Hub-Signature` tu INTERNET co the chua BAT KY gi — mot
        chuoi khong phai hex (vd ky tu ngoai ASCII) KHONG duoc lam sap tien
        trinh (`hmac.compare_digest` nem `TypeError` cho chuoi non-ASCII neu
        khong duoc loc truoc, xem `verify_signature`)."""
        self._dang_ky_va_lay_secret()
        ket_qua = self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=b"<feed/>",
            signature_header="sha256=không-phải-hex-tí-nào")
        self.assertFalse(ket_qua)

    def test_thong_bao_xml_hong_ghi_loi_nhung_van_ghi_nhan_da_nhan(self):
        secret = self._dang_ky_va_lay_secret()
        body = b"khong phai xml"
        sig = compute_signature(secret, body)
        ket_qua = self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=body, signature_header=sig)
        self.assertFalse(ket_qua)
        luu = self.store.get_source(self.source["source_id"])
        self.assertTrue(luu.last_notification_at)  # chu ky dung -> DA nhan.
        self.assertTrue(luu.last_websub_error)

    def _atom(self, video_id: str, channel_id: str, title: str = "Tiên Nghịch Tập 5") -> bytes:
        return f"""<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
                         xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <yt:videoId>{video_id}</yt:videoId>
            <yt:channelId>{channel_id}</yt:channelId>
            <title>{title}</title>
            <published>2026-01-01T00:00:00+00:00</published>
            <updated>2026-01-01T00:00:00+00:00</updated>
          </entry>
        </feed>""".encode("utf-8")

    def test_thong_bao_auto_discover_tat_khong_lam_gi_ca(self):
        secret = self._dang_ky_va_lay_secret()
        vid = "vidW0000001"
        body = self._atom(vid, self.cid)
        sig = compute_signature(secret, body)
        ket_qua = self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=body, signature_header=sig)
        self.assertTrue(ket_qua)  # DA nhan.
        self.assertIsNone(self.store.get_import_by_video_id(vid))  # nhung KHONG xu ly.

    def test_thong_bao_nguon_tat_khong_lam_gi_ca(self):
        self._bat_auto_discover()
        self.svc.set_source_enabled(self.admin, self.source["source_id"], False, actor_role="owner")
        secret = self._dang_ky_va_lay_secret()
        vid = "vidW0000002"
        body = self._atom(vid, self.cid)
        sig = compute_signature(secret, body)
        ket_qua = self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=body, signature_header=sig)
        self.assertTrue(ket_qua)
        self.assertIsNone(self.store.get_import_by_video_id(vid))

    def test_thong_bao_sai_kenh_bi_bo_qua(self):
        self._bat_auto_discover()
        secret = self._dang_ky_va_lay_secret()
        vid = "vidW0000003"
        body = self._atom(vid, "UC" + "z" * 22)  # kenh KHAC nguon nay.
        sig = compute_signature(secret, body)
        self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=body, signature_header=sig)
        self.assertIsNone(self.store.get_import_by_video_id(vid))

    def test_thong_bao_dung_pipeline_phan_loai_that(self):
        self._bat_auto_discover()
        self.svc.create_mapping(
            self.admin, self.source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tiên nghịch"], include_keywords=[], exclude_keywords=[],
            actor_role="owner")
        secret = self._dang_ky_va_lay_secret()
        vid = "vidW0000004"
        self._dat_youtube_gia(FakeYouTubeClient(videos={
            vid: VideoInfo(video_id=vid, title="Tiên Nghịch Tập 5", channel_id=self.cid,
                          channel_title="Kênh W", thumbnail_url="", published_at="",
                          duration_seconds=100.0)}))
        body = self._atom(vid, self.cid)
        sig = compute_signature(secret, body)
        ket_qua = self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=body, signature_header=sig)
        self.assertTrue(ket_qua)

        ban_ghi = self.store.get_import_by_video_id(vid)
        self.assertIsNotNone(ban_ghi)
        self.assertEqual(ban_ghi.status, ImportStatus.AUTO_IMPORTED)
        self.assertTrue(ban_ghi.created_episode_id)
        tap = self.animation.get_episode(ban_ghi.created_episode_id)
        self.assertEqual(tap.state, PublishState.DRAFT)  # auto_publish tat.

        discover, _ = self.metadata.list_events(action="auto_video_discover")
        self.assertEqual(len(discover), 1)
        nhap, _ = self.metadata.list_events(action="auto_video_import")
        self.assertEqual(len(nhap), 1)
        xuat_ban, _ = self.metadata.list_events(action="auto_video_publish")
        self.assertEqual(len(xuat_ban), 0)

    def test_thong_bao_trung_lap_khong_phan_loai_lai(self):
        self._bat_auto_discover()
        self.svc.create_mapping(
            self.admin, self.source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tiên nghịch"], include_keywords=[], exclude_keywords=[],
            actor_role="owner")
        secret = self._dang_ky_va_lay_secret()
        vid = "vidW0000005"
        self._dat_youtube_gia(FakeYouTubeClient(videos={
            vid: VideoInfo(video_id=vid, title="Tiên Nghịch Tập 6", channel_id=self.cid,
                          channel_title="Kênh W", thumbnail_url="", published_at="",
                          duration_seconds=100.0)}))
        body = self._atom(vid, self.cid)
        sig = compute_signature(secret, body)
        self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=body, signature_header=sig)
        self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=body, signature_header=sig)

        _rows, total = self.store.find_imports(trusted_source_id=self.source["source_id"])
        self.assertEqual(total, 1)  # KHONG tao ban thu hai.
        discover, _ = self.metadata.list_events(action="auto_video_discover")
        self.assertEqual(len(discover), 1)  # chi log MOT lan (lan dau).

    def test_thong_bao_cap_nhat_tieu_de_lam_moi_khi_con_cho_duyet(self):
        # auto_import TAT tren nguon nay de video roi vao PENDING (con "cho
        # quyet dinh"), sau do gui THEM mot thong bao voi tieu de MOI.
        self.svc.update_source(
            self.admin, self.source["source_id"], {"auto_import": False}, actor_role="owner")
        self._bat_auto_discover()
        self.svc.create_mapping(
            self.admin, self.source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tiên nghịch"], include_keywords=[], exclude_keywords=[],
            actor_role="owner")
        secret = self._dang_ky_va_lay_secret()
        vid = "vidW0000006"
        yt = FakeYouTubeClient(videos={
            vid: VideoInfo(video_id=vid, title="Tiên Nghịch Tập 7", channel_id=self.cid,
                          channel_title="Kênh W", thumbnail_url="", published_at="",
                          duration_seconds=100.0)})
        self._dat_youtube_gia(yt)
        body = self._atom(vid, self.cid)
        sig = compute_signature(secret, body)
        self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=body, signature_header=sig)
        ban_ghi = self.store.get_import_by_video_id(vid)
        self.assertEqual(ban_ghi.status, ImportStatus.PENDING)

        # YouTube "sua" tieu de — gia lap qua client gia CAP NHAT.
        yt._videos[vid] = VideoInfo(
            video_id=vid, title="Tiên Nghịch Tập 7 (đã sửa)", channel_id=self.cid,
            channel_title="Kênh W", thumbnail_url="", published_at="", duration_seconds=100.0)
        body2 = self._atom(vid, self.cid, title="Tiên Nghịch Tập 7 (đã sửa)")
        sig2 = compute_signature(secret, body2)
        self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=body2, signature_header=sig2)

        ban_ghi_2 = self.store.get_import_by_video_id(vid)
        self.assertEqual(ban_ghi_2.title, "Tiên Nghịch Tập 7 (đã sửa)")
        _rows, total = self.store.find_imports(trusted_source_id=self.source["source_id"])
        self.assertEqual(total, 1)  # van chi MOT dong.

    def test_thong_bao_khong_lam_moi_ban_ghi_da_la_quyet_dinh_cuoi(self):
        self._bat_auto_discover()
        self.svc.create_mapping(
            self.admin, self.source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tiên nghịch"], include_keywords=[], exclude_keywords=[],
            actor_role="owner")
        secret = self._dang_ky_va_lay_secret()
        vid = "vidW0000007"
        yt = FakeYouTubeClient(videos={
            vid: VideoInfo(video_id=vid, title="Tiên Nghịch Tập 8", channel_id=self.cid,
                          channel_title="Kênh W", thumbnail_url="", published_at="",
                          duration_seconds=100.0)})
        self._dat_youtube_gia(yt)
        body = self._atom(vid, self.cid)
        sig = compute_signature(secret, body)
        self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=body, signature_header=sig)
        ban_ghi = self.store.get_import_by_video_id(vid)
        self.assertEqual(ban_ghi.status, ImportStatus.AUTO_IMPORTED)  # quyet dinh CUOI.

        yt._videos[vid] = VideoInfo(
            video_id=vid, title="TIÊU ĐỀ GIẢ MẠO SAU KHI ĐÃ NHẬP", channel_id=self.cid,
            channel_title="Kênh W", thumbnail_url="", published_at="", duration_seconds=100.0)
        body2 = self._atom(vid, self.cid, title="TIÊU ĐỀ GIẢ MẠO SAU KHI ĐÃ NHẬP")
        sig2 = compute_signature(secret, body2)
        self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=body2, signature_header=sig2)

        ban_ghi_2 = self.store.get_import_by_video_id(vid)
        self.assertEqual(ban_ghi_2.title, "Tiên Nghịch Tập 8")  # KHONG doi.
        self.assertEqual(ban_ghi_2.status, ImportStatus.AUTO_IMPORTED)

    def _deleted_atom(self, video_id: str, channel_id: str) -> bytes:
        return f"""<feed xmlns:at="http://purl.org/atompub/tombstones/1.0"
                         xmlns="http://www.w3.org/2005/Atom">
          <at:deleted-entry ref="yt:video:{video_id}" when="2026-01-01T00:00:00+00:00">
            <at:by><uri>https://www.youtube.com/channel/{channel_id}</uri></at:by>
          </at:deleted-entry>
        </feed>""".encode("utf-8")

    def test_video_bi_xoa_danh_dau_unavailable_neu_dang_cho_duyet(self):
        self.svc.update_source(
            self.admin, self.source["source_id"], {"auto_import": False}, actor_role="owner")
        self._bat_auto_discover()
        self.svc.create_mapping(
            self.admin, self.source["source_id"], animation_series_id=self.series.series_id,
            aliases=["tiên nghịch"], include_keywords=[], exclude_keywords=[],
            actor_role="owner")
        secret = self._dang_ky_va_lay_secret()
        vid = "vidW0000008"
        self._dat_youtube_gia(FakeYouTubeClient(videos={
            vid: VideoInfo(video_id=vid, title="Tiên Nghịch Tập 9", channel_id=self.cid,
                          channel_title="Kênh W", thumbnail_url="", published_at="",
                          duration_seconds=100.0)}))
        body = self._atom(vid, self.cid)
        sig = compute_signature(secret, body)
        self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=body, signature_header=sig)
        self.assertEqual(self.store.get_import_by_video_id(vid).status, ImportStatus.PENDING)

        xoa_body = self._deleted_atom(vid, self.cid)
        xoa_sig = compute_signature(secret, xoa_body)
        self.svc.handle_websub_notification(
            source_id=self.source["source_id"], body=xoa_body, signature_header=xoa_sig)
        self.assertEqual(
            self.store.get_import_by_video_id(vid).status, ImportStatus.UNAVAILABLE)

    # ==================================================== doi chieu dinh ky

    def test_doi_chieu_chi_quet_nguon_bat_va_auto_discover(self):
        self._bat_auto_discover()
        nguon_tat = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id="UC" + "q" * 22,
            display_name="Kênh tắt", auto_discover=False, actor_role="owner")

        self._dat_youtube_gia(FakeYouTubeClient(
            channels={self.cid: ChannelInfo(channel_id=self.cid, title="Kênh W",
                                            thumbnail_url="", uploads_playlist_id="UUw")},
            playlist_items={"UUw": ([_video_item("vidW0000010")], "")},
            videos={"vidW0000010": VideoInfo(
                video_id="vidW0000010", title="Video lạ", channel_id=self.cid,
                channel_title="Kênh W", thumbnail_url="", published_at="",
                duration_seconds=10.0)},
        ))
        ket_qua = self.svc.run_reconciliation(actor_id="", actor_role="system")
        self.assertEqual(ket_qua["sources_checked"], 1)  # CHI nguon bat+auto_discover.
        luu = self.store.get_source(self.source["source_id"])
        self.assertTrue(luu.last_successful_sync_at)
        luu_tat = self.store.get_source(nguon_tat["source_id"])
        self.assertEqual(luu_tat.last_successful_sync_at, "")

        events, _ = self.metadata.list_events(action="reconciliation_run")
        self.assertEqual(len(events), 1)

    def test_doi_chieu_bi_chan_mot_trang(self):
        self._bat_auto_discover()
        self._dat_youtube_gia(FakeYouTubeClient(
            channels={self.cid: ChannelInfo(channel_id=self.cid, title="Kênh W",
                                            thumbnail_url="", uploads_playlist_id="UUw")},
            playlist_items={
                "UUw": ([_video_item("vidW0000011")], "trang_2"),
                "trang_2": ([_video_item("vidW0000012")], ""),
            },
            videos={
                "vidW0000011": VideoInfo(
                    video_id="vidW0000011", title="Video trang 1", channel_id=self.cid,
                    channel_title="Kênh W", thumbnail_url="", published_at="",
                    duration_seconds=10.0),
                "vidW0000012": VideoInfo(
                    video_id="vidW0000012", title="Video trang 2", channel_id=self.cid,
                    channel_title="Kênh W", thumbnail_url="", published_at="",
                    duration_seconds=10.0),
            },
        ))
        self.svc.run_reconciliation(source_id=self.source["source_id"],
                                    actor_id="", actor_role="system")
        # Chi trang 1 duoc quet (RECONCILIATION_MAX_PAGES=1) — video o trang
        # 2 KHONG duoc xu ly (khong co VideoImport nao cho no).
        self.assertIsNotNone(self.store.get_import_by_video_id("vidW0000011"))
        self.assertIsNone(self.store.get_import_by_video_id("vidW0000012"))

    def test_doi_chieu_mot_nguon_cu_the(self):
        self._bat_auto_discover()
        khac = self.svc.create_source(
            self.admin, source_type="youtube_channel", youtube_channel_id="UC" + "r" * 22,
            display_name="Kênh khác", auto_discover=True, actor_role="owner")
        self._dat_youtube_gia(FakeYouTubeClient())
        ket_qua = self.svc.run_reconciliation(
            source_id=self.source["source_id"], actor_id="", actor_role="system")
        self.assertEqual(ket_qua["sources_checked"], 1)
        self.assertEqual(self.store.get_source(khac["source_id"]).last_successful_sync_at, "")

    def test_doi_chieu_tu_dong_gia_han_khi_sap_het_han(self):
        self._bat_auto_discover()
        han_gan = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
        self.store.record_websub_subscription(
            self.source["source_id"], status=SubscriptionStatus.ACTIVE,
            expires_at=han_gan, secret="bi-mat-cu")
        fake_websub = FakeWebSubClient()
        self._dat_websub_gia(fake_websub)
        self._dat_youtube_gia(FakeYouTubeClient(
            channels={self.cid: ChannelInfo(channel_id=self.cid, title="Kênh W",
                                            thumbnail_url="", uploads_playlist_id="UUw")},
            playlist_items={"UUw": ([], "")}))
        self.svc.run_reconciliation(source_id=self.source["source_id"],
                                    actor_id="", actor_role="system")
        self.assertEqual(len(fake_websub.subscribe_calls), 1)
        events, _ = self.metadata.list_events(action="websub_renew")
        self.assertEqual(len(events), 1)

    def test_doi_chieu_khong_gia_han_khi_con_xa_han(self):
        self._bat_auto_discover()
        han_xa = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(timespec="seconds")
        self.store.record_websub_subscription(
            self.source["source_id"], status=SubscriptionStatus.ACTIVE,
            expires_at=han_xa, secret="bi-mat-cu")
        fake_websub = FakeWebSubClient()
        self._dat_websub_gia(fake_websub)
        self._dat_youtube_gia(FakeYouTubeClient(
            channels={self.cid: ChannelInfo(channel_id=self.cid, title="Kênh W",
                                            thumbnail_url="", uploads_playlist_id="UUw")},
            playlist_items={"UUw": ([], "")}))
        self.svc.run_reconciliation(source_id=self.source["source_id"],
                                    actor_id="", actor_role="system")
        self.assertEqual(len(fake_websub.subscribe_calls), 0)


if __name__ == "__main__":
    unittest.main()
