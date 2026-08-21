#!/usr/bin/env python3
"""
Smoke test THAT cho Auto-Ingestion Phase 5 pre-merge hardening — chay tren
Appwrite tu luu tru (dev) THAT, chung minh cac hanh vi CU THE yeu cau boi
dot rieng hoa nay (khac `smoke_test_selfhost_channel_discovery.py`, ban goc,
van con nguyen):

    FAS_ENV_FILE=server/.env.selfhost python -m scripts.smoke_test_selfhost_channel_discovery_hardening

Phan 1 (YouTube Data API THAT, kenh cong khai on dinh it video): video DON
LE khong co tin hieu tap -> KHONG con tu tao series (chinh sach tin cay,
truoc day se tu tao).

Phan 2 (Appwrite THAT, YouTube Data API GIA co kiem soat qua client thay
the — noi dung video khong the kiem soat tren mot kenh that, nhung Appwrite
la HE THONG THAT dang duoc kiem chung o day): cum 2 tap mach lac tao DUNG
MOT series nhap; chay lai KHONG tao trung; PENDING duoc phan loai lai
thanh cong khi mapping xuat hien; quyet dinh CUOI CUNG (REJECTED) khong
bao gio doi.

AN TOAN: moi ban ghi tao ra deu bi XOA sau khi chay (ke ca khi that bai,
qua try/finally). KHONG BAO GIO in secret.
"""

from __future__ import annotations

import sys
from typing import List, Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

CHANNEL_ID_ON_DINH = "UC4QobU6STFB0P71PMvOGN5A"


class BoKetQua:
    def __init__(self) -> None:
        self.items: List[tuple] = []

    def kiem(self, ten: str, dat: bool, chi_tiet: str = "") -> None:
        self.items.append((ten, dat, chi_tiet))
        bieu_tuong = "OK  " if dat else "FAIL"
        print(f"[{bieu_tuong}] {ten}" + (f" — {chi_tiet}" if chi_tiet else ""))

    @property
    def tat_ca_dat(self) -> bool:
        return all(dat for _, dat, _ in self.items)


class _FakeYouTubeClient:
    """Client GIA toi thieu — CHI dung de kiem soat noi dung video trong
    Phan 2, khong the lam duoc voi kenh THAT (noi dung ngoai tam kiem soat).
    Appwrite (he thong THAT dang kiem chung) khong bi anh huong boi lua chon
    nay — moi ghi/doc van la Appwrite dev that."""

    def __init__(self, *, channels=None, playlist_items=None, videos=None):
        self._channels = channels or {}
        self._playlist_items = playlist_items or {}
        self._videos = videos or {}

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


def _video_item(video_id: str) -> dict:
    return {"contentDetails": {"videoId": video_id}}


def chay() -> int:
    from server.animation_domain import AnimationSeries
    from server.appwrite_animation_store import AppwriteAnimationStore
    from server.appwrite_store import AppwriteMetadataStore
    from server.appwrite_trusted_source_store import AppwriteTrustedSourceStore, COL_IMPORTS
    from server.config import load_settings
    from server.domain import Profile
    from server.trusted_source_domain import ImportStatus, video_import_id
    from server.trusted_source_service import TrustedSourceService
    from server.youtube_client import ChannelInfo, VideoInfo

    settings = load_settings()
    if not settings.appwrite.configured:
        print("LỖI: thiếu cấu hình Appwrite — chạy với "
             "FAS_ENV_FILE=server/.env.selfhost.")
        return 1
    if not settings.youtube_api_key:
        print("LỖI: thiếu YOUTUBE_API_KEY.")
        return 1
    if "fanfic.world" not in settings.appwrite.endpoint or "dev" not in settings.appwrite.database_id:
        print("LỖI: endpoint/database không trông như môi trường DEV tự lưu "
             f"trữ ({settings.appwrite.endpoint}, db={settings.appwrite.database_id}). Dừng lại.")
        return 1

    trusted_store = AppwriteTrustedSourceStore(settings.appwrite)
    animation_store = AppwriteAnimationStore(settings.appwrite)
    metadata_store = AppwriteMetadataStore(settings.appwrite)
    svc = TrustedSourceService(
        trusted_store, animation_store, metadata_store,
        youtube_api_key=settings.youtube_api_key)
    admin = Profile(user_id="smoke_test_admin", email="smoke-test@fanfic.world")

    ket_qua = BoKetQua()
    source_ids: List[str] = []
    series_ids: List[str] = []
    video_ids_phat_hien: List[str] = []

    try:
        # ============================================ Phan 1: kenh THAT ====
        source1 = svc.create_source(
            admin, source_type="youtube_channel", youtube_channel_id=CHANNEL_ID_ON_DINH,
            display_name="[smoke-test-hardening] kênh thật, video đơn không tập",
            auto_import=True, auto_publish=False, minimum_confidence=0.1,
            actor_role="owner")
        source_ids.append(source1["source_id"])

        lan_1 = svc.discover_channel(admin, source1["source_id"], max_pages=1, actor_role="owner")
        video_ids_phat_hien += (
            list(lan_1.confident_imports) + list(lan_1.pending_review)
            + list(lan_1.duplicates) + list(lan_1.conflicts) + list(lan_1.excluded))
        series_ids += [g.series_id for g in lan_1.groups if g.series_id]

        ket_qua.kiem(
            "Phần 1 (kênh thật): video đơn lẻ không tín hiệu tập KHÔNG tự "
            "tạo series mới (chính sách tin cậy)",
            lan_1.new_series_created == 0,
            f"new_series_created={lan_1.new_series_created} "
            f"groups={[(g.confidence_tier, g.series_id) for g in lan_1.groups]}")

        # ============================================ Phan 2: Appwrite THAT,
        # YouTube GIA co kiem soat ================================================
        cid = "UCsmoketest0000000002"
        playlist_id = "UUsmoketest0002"
        v1, v2 = "vidHardenSm01", "vidHardenSm02"
        client = _FakeYouTubeClient(
            channels={cid: ChannelInfo(
                channel_id=cid, title="Kênh smoke test hardening", thumbnail_url="",
                uploads_playlist_id=playlist_id)},
            playlist_items={playlist_id: (
                [_video_item(v1), _video_item(v2)], "")},
            videos={
                v1: VideoInfo(video_id=v1, title="Tiên Nghịch Tập 1", channel_id=cid,
                             channel_title="Kênh smoke test hardening", thumbnail_url="",
                             published_at="2026-01-01", duration_seconds=1000.0),
                v2: VideoInfo(video_id=v2, title="Tiên Nghịch Tập 2", channel_id=cid,
                             channel_title="Kênh smoke test hardening", thumbnail_url="",
                             published_at="2026-01-02", duration_seconds=1000.0),
            },
        )
        svc._youtube = lambda: client  # type: ignore[method-assign]

        source2 = svc.create_source(
            admin, source_type="youtube_channel", youtube_channel_id=cid,
            display_name="[smoke-test-hardening] cụm 2 tập mạch lạc",
            auto_import=True, auto_publish=False, minimum_confidence=0.1,
            actor_role="owner")
        source_ids.append(source2["source_id"])

        lan_2 = svc.discover_channel(admin, source2["source_id"], max_pages=1, actor_role="owner")
        video_ids_phat_hien += [v1, v2]
        series_ids += [g.series_id for g in lan_2.groups if g.series_id]
        ket_qua.kiem(
            "Phần 2: cụm 2 tập mạch lạc tạo ĐÚNG MỘT series nháp mới",
            lan_2.new_series_created == 1 and lan_2.candidate_groups == 1,
            f"new_series_created={lan_2.new_series_created} "
            f"candidate_groups={lan_2.candidate_groups}")
        if lan_2.groups:
            series_that = animation_store.get_series(lan_2.groups[0].series_id)
            ket_qua.kiem(
                "Phần 2: series mới tạo ở trạng thái DRAFT (thật, Appwrite dev)",
                series_that.state.value == "draft", series_that.state.value)

        lan_3 = svc.discover_channel(admin, source2["source_id"], max_pages=1, actor_role="owner")
        ket_qua.kiem(
            "Phần 2: chạy lại KHÔNG tạo series/mapping/import trùng",
            lan_3.new_series_created == 0 and lan_3.already_tracked == 2,
            f"new_series_created={lan_3.new_series_created} "
            f"already_tracked={lan_3.already_tracked}")
        _rows, total_sau_2_lan = trusted_store.find_imports(
            trusted_source_id=source2["source_id"])
        ket_qua.kiem(
            "Appwrite: đúng 2 video_imports sau hai lần chạy (không trùng)",
            total_sau_2_lan == 2, f"total={total_sau_2_lan}")

        # -- PENDING duoc phan loai lai khi mapping xuat hien --------------
        cid_p, playlist_id_p = "UCsmoketest0000000003", "UUsmoketest0003"
        v_pending = "vidHardenPend01"
        client_pending = _FakeYouTubeClient(
            channels={cid_p: ChannelInfo(
                channel_id=cid_p, title="Kênh smoke test pending", thumbnail_url="",
                uploads_playlist_id=playlist_id_p)},
            playlist_items={playlist_id_p: ([_video_item(v_pending)], "")},
            videos={v_pending: VideoInfo(
                video_id=v_pending, title="Đấu Phá Thương Khung Tập 5", channel_id=cid_p,
                channel_title="Kênh smoke test pending", thumbnail_url="",
                published_at="2026-01-01", duration_seconds=1000.0)},
        )
        svc._youtube = lambda: client_pending  # type: ignore[method-assign]
        source3 = svc.create_source(
            admin, source_type="youtube_channel", youtube_channel_id=cid_p,
            display_name="[smoke-test-hardening] PENDING -> reclassify",
            auto_import=True, minimum_confidence=0.9, actor_role="owner")
        source_ids.append(source3["source_id"])
        series3 = animation_store.create_series(AnimationSeries(
            owner_id=admin.user_id, title="[smoke-test-hardening] Đấu Phá Thương Khung"))
        series_ids.append(series3.series_id)
        svc.create_mapping(
            admin, source3["source_id"], animation_series_id=series3.series_id,
            aliases=["đấu phá thương khung"], include_keywords=[], exclude_keywords=[],
            actor_role="owner")

        lan_pending_1 = svc.discover_channel(admin, source3["source_id"], actor_role="owner")
        video_ids_phat_hien.append(v_pending)
        import_pending = trusted_store.get_import_by_video_id(v_pending)
        ket_qua.kiem(
            "Phần 2 (PENDING): độ tin cậy dưới ngưỡng (0.9) -> PENDING lúc đầu",
            import_pending is not None and import_pending.status.value == "pending",
            import_pending.status.value if import_pending else "None")

        svc.update_source(
            admin, source3["source_id"], {"minimum_confidence": 0.1}, actor_role="owner")
        lan_pending_2 = svc.discover_channel(admin, source3["source_id"], actor_role="owner")
        import_pending_sau = trusted_store.get_import_by_video_id(v_pending)
        ket_qua.kiem(
            "Phần 2 (PENDING): sau khi giảm ngưỡng, quét lại RECLASSIFY "
            "thành auto_imported (không kẹt PENDING vĩnh viễn)",
            import_pending_sau is not None
            and import_pending_sau.status.value == "auto_imported",
            import_pending_sau.status.value if import_pending_sau else "None")
        ket_qua.kiem(
            "Phần 2 (PENDING): cùng import_id (không tạo bản ghi thứ hai)",
            import_pending_sau.import_id == import_pending.import_id)

        # -- Quyet dinh CUOI CUNG (REJECTED) khong bao gio doi --------------
        svc.reject_import(admin, import_pending_sau.import_id, reason="smoke-test hardening")
        lan_pending_3 = svc.discover_channel(admin, source3["source_id"], actor_role="owner")
        import_pending_cuoi = trusted_store.get_import_by_video_id(v_pending)
        ket_qua.kiem(
            "Phần 2: quyết định CUỐI CÙNG (REJECTED) không bao giờ đổi dù "
            "quét lại nhiều lần",
            import_pending_cuoi.status.value == "rejected"
            and lan_pending_3.already_tracked == 1,
            f"status={import_pending_cuoi.status.value} "
            f"already_tracked={lan_pending_3.already_tracked}")

    finally:
        for sid in source_ids:
            try:
                svc.remove_source(admin, sid, actor_role="owner")
            except Exception as exc:
                print(f"[CẢNH BÁO] không xoá được trusted source tạm {sid}: {exc}")
        for sid in series_ids:
            try:
                for ep in animation_store.list_episodes(sid, include_removed=True):
                    animation_store.delete_episode(ep.episode_id, admin.user_id)
                animation_store.delete_series(sid, admin.user_id)
            except Exception as exc:
                print(f"[CẢNH BÁO] không xoá được series tạm {sid}: {exc}")
        for vid in video_ids_phat_hien:
            try:
                trusted_store._delete(COL_IMPORTS, video_import_id(vid))
            except Exception as exc:
                print(f"[CẢNH BÁO] không xoá được video_import tạm {vid}: {exc}")

    print()
    print(f"TỔNG: {sum(1 for _, d, _ in ket_qua.items if d)}/{len(ket_qua.items)} kiểm tra đạt.")
    return 0 if ket_qua.tat_ca_dat else 1


if __name__ == "__main__":
    sys.exit(chay())
