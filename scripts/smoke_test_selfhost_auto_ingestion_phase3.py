#!/usr/bin/env python3
"""
Smoke test THAT cho Auto-Ingestion Phase 3 (concurrency-safe episode slot,
policy engine, resilience) tren Appwrite tu luu tru (dev) that — xem
`docs/handoffs/admin-trusted-video-v2-handoff.md` muc 4e/4d va commit Phase 3.

    FAS_ENV_FILE=server/.env.selfhost python -m scripts.smoke_test_selfhost_auto_ingestion_phase3

Goi THANG `TrustedSourceService` (khong qua HTTP), CUNG mau voi
`smoke_test_selfhost_trusted_sources.py`/`smoke_test_selfhost_websub.py`.

AN TOAN:
- CASE 1/2/5/6 dung "Me at the zoo" (video YouTube dau tien, cong khai, on
  dinh vinh vien) qua YouTube Data API THAT — video nay KHONG co so tap
  trong tieu de, nen la vi du THAT cho "PENDING vi khong the tu dong an
  toan" (CASE 3).
- CASE 4 (tu dong nhap tao dung MOT tap draft) can MOT video that co so tap
  parse duoc trong tieu de VA do tin cay du nguong — khong co kenh YouTube
  nao do chung ta kiem soat de dam bao dieu nay (dung theo dac ta: "a
  genuine newly-published video is NOT required... business pipeline can be
  tested independently"), nen CASE 4/5 dung MOT `FakeYouTubeClient` (ghi de
  `svc._youtube`, cung ky thuat voi unit test) DUNG NGAY TREN Appwrite dev
  THAT — nghia la classify/policy/ghi episode deu la code that chay tren
  du lieu that, chi rieng phan goi mang YouTube duoc thay bang du lieu co
  dinh de kiem soat duoc tieu de video.
- Moi ban ghi tao ra deu danh dau "smoke-test-p3" va bi XOA sau khi chay
  (ke ca that bai giua chung, qua try/finally).
"""

from __future__ import annotations

import sys
from typing import List, Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

VIDEO_ID_ON_DINH = "jNQXAC9IVRw"  # "Me at the zoo" — khong co so tap trong tieu de.


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


def chay() -> int:
    from server.animation_domain import AnimationSeries
    from server.appwrite_animation_store import AppwriteAnimationStore
    from server.appwrite_store import AppwriteMetadataStore
    from server.appwrite_trusted_source_store import COL_IMPORTS, AppwriteTrustedSourceStore
    from server.config import load_settings
    from server.domain import Profile
    from server.trusted_source_domain import video_import_id
    from server.trusted_source_service import TrustedSourceService
    from server.youtube_client import ChannelInfo, VideoInfo

    settings = load_settings()
    if not settings.appwrite.configured:
        print("LỖI: thiếu cấu hình Appwrite — chạy với FAS_ENV_FILE=server/.env.selfhost.")
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
    admin = Profile(user_id="smoke_test_p3_admin", email="smoke-test-p3@fanfic.world")

    ket_qua = BoKetQua()
    series_id: Optional[str] = None
    source_id: Optional[str] = None
    series_id_2: Optional[str] = None
    source_id_2: Optional[str] = None

    def don_video_import(video_id: str) -> None:
        try:
            trusted_store._delete(COL_IMPORTS, video_import_id(video_id))
        except Exception:
            pass

    don_video_import(VIDEO_ID_ON_DINH)
    don_video_import("vidP3fake001")

    try:
        # ================================================= CASE 1/2/3: that
        video = svc._youtube().get_video(VIDEO_ID_ON_DINH)
        ket_qua.kiem("CASE1: YouTube get_video thật (Me at the zoo)", video is not None)
        if video is None:
            return 1

        series = animation_store.create_series(AnimationSeries(
            owner_id="smoke_test_p3_owner", title="[smoke-test-p3] Series A"))
        series_id = series.series_id

        source = svc.create_source(
            admin, source_type="youtube_video", youtube_video_id=VIDEO_ID_ON_DINH,
            display_name="[smoke-test-p3] Me at the zoo",
            auto_import=True, auto_publish=False, minimum_confidence=0.1,
            actor_role="owner")
        source_id = source["source_id"]
        svc.create_mapping(
            admin, source_id, animation_series_id=series_id,
            aliases=["zoo"], include_keywords=[], exclude_keywords=[], actor_role="owner")

        # CASE 1 — ung vien moi di qua pipeline CHINH THUC dung MOT lan.
        scan_1 = svc.scan_source(admin, source_id, actor_role="owner")
        ket_qua.kiem("CASE1: scan_source (reconciliation/manual) chạy pipeline thật",
                    scan_1["detected"] == 1, str(scan_1))
        rows, total = trusted_store.find_imports(trusted_source_id=source_id)
        ket_qua.kiem("CASE1: đúng 1 VideoImport thật được tạo", total == 1)

        # CASE 3 — tu dong khong the an toan hanh dong (thieu so tap trong
        # tieu de that) -> PENDING, KHONG tu bia so tap.
        if rows:
            ket_qua.kiem(
                "CASE3: video thật không có số tập -> PENDING (đúng chính sách tự động)",
                rows[0].status.value == "pending", rows[0].status.value)

        # CASE 2 — ung vien LAP LAI (quet lai) KHONG tao ban trung.
        scan_2 = svc.scan_source(admin, source_id, actor_role="owner")
        ket_qua.kiem("CASE2: quét lại — already_tracked, không phân loại lại",
                    scan_2["already_tracked"] == 1, str(scan_2))
        _rows2, total_2 = trusted_store.find_imports(trusted_source_id=source_id)
        ket_qua.kiem("CASE2: vẫn đúng 1 VideoImport (không nhân đôi)", total_2 == 1)

        # ================================== CASE 4/5: tu dong nhap + provenance
        # Khong co kenh YouTube nao ta kiem soat de co video THAT vua co so
        # tap trong tieu de VUA du tin cay — dung FakeYouTubeClient CHI de
        # cung cap metadata video (tieu de/kenh), TOAN BO logic phan loai/
        # chinh sach/ghi Appwrite deu la code that chay tren du lieu that.
        class _FakeYT:
            def get_video(self, vid):
                return VideoInfo(
                    video_id=vid, title="Series Beta Tập 7", channel_id="UCfakep3channel00",
                    channel_title="[smoke-test-p3] Kênh Beta", thumbnail_url="",
                    published_at="2026-01-01T00:00:00Z", duration_seconds=600.0)

            def get_videos(self, vids):
                return {v: self.get_video(v) for v in vids}

            def get_channel(self, cid):
                return ChannelInfo(channel_id=cid, title="[smoke-test-p3] Kênh Beta",
                                  thumbnail_url="", uploads_playlist_id="UUfakep3")

            def list_playlist_items(self, playlist_id, *, page_token="", max_results=50):
                return ([{"contentDetails": {"videoId": "vidP3fake001"}}], "")

        series_2 = animation_store.create_series(AnimationSeries(
            owner_id="smoke_test_p3_owner", title="[smoke-test-p3] Series Beta"))
        series_id_2 = series_2.series_id
        source_2 = svc.create_source(
            admin, source_type="youtube_channel", youtube_channel_id="UCfakep3channel00",
            display_name="[smoke-test-p3] Kênh Beta",
            auto_import=True, auto_publish=False, minimum_confidence=0.1,
            actor_role="owner")
        source_id_2 = source_2["source_id"]
        svc.create_mapping(
            admin, source_id_2, animation_series_id=series_id_2,
            aliases=["series beta"], include_keywords=[], exclude_keywords=[],
            actor_role="owner")

        svc._youtube = lambda: _FakeYT()  # type: ignore[method-assign]
        scan_beta = svc.scan_source(admin, source_id_2, actor_role="owner")
        ket_qua.kiem("CASE4: tự động nhập tạo ĐÚNG một tập draft",
                    scan_beta["auto_imported"] == 1, str(scan_beta))

        rows_beta, _t = trusted_store.find_imports(trusted_source_id=source_id_2)
        if rows_beta and rows_beta[0].created_episode_id:
            episode = animation_store.get_episode(rows_beta[0].created_episode_id)
            ket_qua.kiem("CASE5: episode thật đọc lại được (provenance)",
                        episode.external_id == "vidP3fake001")
            ket_qua.kiem("CASE5: provenance channel_id đúng",
                        episode.source_channel_id == "UCfakep3channel00")
            ket_qua.kiem("CASE5: provenance channel_title đúng",
                        episode.source_channel_title == "[smoke-test-p3] Kênh Beta")
            ket_qua.kiem("CASE5: số tập suy ra đúng từ tiêu đề", episode.order_index == 7)
            from server.domain import PublishState
            ket_qua.kiem("CASE4: tập tạo ở trạng thái DRAFT (auto_publish=False)",
                        episode.state == PublishState.DRAFT)
        else:
            ket_qua.kiem("CASE5: episode thật đọc lại được (provenance)", False, "không có created_episode_id")

        # Quet lai nguon Beta — phai idempotent, khong tao tap thu hai.
        scan_beta_2 = svc.scan_source(admin, source_id_2, actor_role="owner")
        ket_qua.kiem("CASE2(beta): quét lại tự động cũng idempotent",
                    scan_beta_2["already_tracked"] == 1, str(scan_beta_2))

    finally:
        # ============================================= CASE 6: don dep sach
        for sid, sname in ((source_id, "A"), (source_id_2, "Beta")):
            if sid:
                try:
                    svc.remove_source(admin, sid, actor_role="owner")
                except Exception as exc:
                    print(f"[CẢNH BÁO] không xoá được trusted source {sname}: {exc}")
        for sid, sname in ((series_id, "A"), (series_id_2, "Beta")):
            if sid:
                try:
                    for ep in animation_store.list_episodes(sid, include_removed=True):
                        animation_store.delete_episode(ep.episode_id, "smoke_test_p3_owner")
                    animation_store.delete_series(sid, "smoke_test_p3_owner")
                except Exception as exc:
                    print(f"[CẢNH BÁO] không xoá được series {sname}: {exc}")
        don_video_import(VIDEO_ID_ON_DINH)
        don_video_import("vidP3fake001")

    print()
    print(f"TỔNG: {sum(1 for _, d, _ in ket_qua.items if d)}/{len(ket_qua.items)} kiểm tra đạt.")
    return 0 if ket_qua.tat_ca_dat else 1


if __name__ == "__main__":
    sys.exit(chay())
