#!/usr/bin/env python3
"""
Smoke test THAT cho Trusted Video Sources (Phase 5) tren Appwrite tu luu tru
(dev) VA YouTube Data API that — xem `docs/DEV_SELFHOST_APPWRITE.md`.

    FAS_ENV_FILE=server/.env.selfhost python -m scripts.smoke_test_selfhost_trusted_sources

Goi THANG cac lop kho/dich vu (khong qua HTTP/FastAPI) — tranh phai dung
mot tai khoan ADMIN that qua dang nhap/token, van la kiem tra THAT voi
Appwrite tu luu tru va YouTube Data API that.

AN TOAN:
- CHI doc (`get_video`/`get_channel`/`list_playlist_items`) tren MOT video
  cong khai, on dinh, noi tieng ("Me at the zoo" — video YouTube dau tien,
  se khong bi go) — ID kenh/playlist doc THAT tu ket qua tra ve, KHONG bao
  gio doan truoc.
- KHONG BAO GIO in `YOUTUBE_API_KEY`/`APPWRITE_API_KEY` hay bat ky loi nao
  co the chua chung.
- Moi ban ghi tao ra (TrustedSource/SeriesMapping/AnimationSeries/VideoImport)
  deu danh dau "smoke-test" va bi XOA sau khi chay (kể cả khi that bai giua
  chung, qua try/finally) — KHONG de rac lai tren Appwrite dev.
"""

from __future__ import annotations

import sys
from typing import List, Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

#: Video YouTube dau tien tung dang — cong khai, on dinh, se khong bi go.
VIDEO_ID_ON_DINH = "jNQXAC9IVRw"


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


def _xoa_video_import_con_lai(trusted_store, video_id: str) -> None:
    """
    `VideoImport` DUY NHAT theo `youtube_video_id` TREN TOAN HE THONG (khong
    theo tung nguon) — kho KHONG co `delete_import` cong khai (khong can cho
    nghiep vu that), nen script nay cham THANG vao `_delete()` noi bo de dep
    sach ban ghi con lai tu lan chay TRUOC (vi du sau mot lan that bai giua
    chung), tranh script bao "already_tracked" gia luc chay lai.
    """
    from server.appwrite_trusted_source_store import COL_IMPORTS
    from server.trusted_source_domain import video_import_id

    trusted_store._delete(COL_IMPORTS, video_import_id(video_id))


def chay() -> int:
    from server.animation_domain import AnimationSeries
    from server.appwrite_animation_store import AppwriteAnimationStore
    from server.appwrite_store import AppwriteMetadataStore
    from server.appwrite_trusted_source_store import AppwriteTrustedSourceStore
    from server.config import load_settings
    from server.domain import Profile
    from server.trusted_source_service import TrustedSourceService

    settings = load_settings()
    if not settings.appwrite.configured:
        print("LỖI: thiếu cấu hình Appwrite (APPWRITE_ENDPOINT/PROJECT_ID/"
             "API_KEY/DATABASE_ID) — chạy với FAS_ENV_FILE=server/.env.selfhost.")
        return 1
    if not settings.youtube_api_key:
        print("LỖI: thiếu YOUTUBE_API_KEY.")
        return 1
    # AN TOAN TUYET DOI: khong bao gio chay script nay nham vao production.
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
    series_id: Optional[str] = None
    source_id: Optional[str] = None
    # Don rac tu lan chay TRUOC (vi du sau mot lan that bai giua chung) —
    # `VideoImport` la DUY NHAT theo video toan he thong, khong theo nguon.
    _xoa_video_import_con_lai(trusted_store, VIDEO_ID_ON_DINH)

    try:
        # -- YouTube Data API THAT ------------------------------------------
        video = svc._youtube().get_video(VIDEO_ID_ON_DINH)
        ket_qua.kiem("YouTube: get_video (video ổn định)", video is not None,
                    f"title={video.title!r}" if video else "")
        if video is None:
            return 1 if not ket_qua.tat_ca_dat else 0

        channel = svc._youtube().get_channel(video.channel_id)
        ket_qua.kiem("YouTube: get_channel (kênh thật của video)",
                    channel is not None,
                    f"uploads_playlist_id={channel.uploads_playlist_id!r}" if channel else "")

        if channel and channel.uploads_playlist_id:
            items, _next = svc._youtube().list_playlist_items(
                channel.uploads_playlist_id, max_results=5)
            ket_qua.kiem("YouTube: list_playlist_items (playlist tải lên thật)",
                        isinstance(items, list),
                        f"{len(items)} video")

        # -- preview_source_url (dung ca YouTube API LAN service) -----------
        preview = svc.preview_source_url(VIDEO_ID_ON_DINH)
        ket_qua.kiem("Service: preview_source_url", preview.get("youtube_channel_id") == video.channel_id)

        # -- Appwrite THAT: series tam de anh xa vao -------------------------
        series = animation_store.create_series(AnimationSeries(
            owner_id="smoke_test_owner",
            title="[smoke-test] Trusted Video Sources"))
        series_id = series.series_id
        ket_qua.kiem("Appwrite: create_series (animation_series thật)", bool(series.series_id))

        # -- Trusted Source CRUD that ----------------------------------------
        source = svc.create_source(
            admin, source_type="youtube_video", youtube_video_id=VIDEO_ID_ON_DINH,
            display_name="[smoke-test] Me at the zoo",
            auto_import=True, auto_publish=False, minimum_confidence=0.1,
            actor_role="owner")
        source_id = source["source_id"]
        ket_qua.kiem("Appwrite: create_source (trusted_sources thật)", bool(source_id))

        trung_lap = False
        try:
            svc.create_source(
                admin, source_type="youtube_video", youtube_video_id=VIDEO_ID_ON_DINH,
                display_name="[smoke-test] trùng lặp", actor_role="owner")
        except Exception:
            trung_lap = True
        ket_qua.kiem("Service: chặn tạo trùng cùng youtube_video_id", trung_lap)

        detail = svc.admin_source_detail(source_id)
        ket_qua.kiem("Appwrite: admin_source_detail đọc lại được", detail is not None)

        mapping = svc.create_mapping(
            admin, source_id, animation_series_id=series_id,
            aliases=["zoo", "me at the zoo"], include_keywords=[], exclude_keywords=[],
            actor_role="owner")
        ket_qua.kiem("Appwrite: create_mapping (series_mappings thật)", bool(mapping["mapping_id"]))

        # -- Quet THAT (nguon la video don le) -------------------------------
        scan = svc.scan_source(admin, source_id, actor_role="owner")
        ket_qua.kiem("Service: scan_source chạy được trên nguồn video đơn lẻ",
                    scan["detected"] == 1, str(scan))

        rows, total = trusted_store.find_imports(trusted_source_id=source_id)
        ket_qua.kiem("Appwrite: video_imports ghi được đúng 1 dòng", total == 1)
        if rows:
            video_import = rows[0]
            # "Me at the zoo" khong co so tap trong tieu de -> PENDING la
            # dung (khong tu nhap khi thieu so tap, xem `_quyet_dinh_trang_thai`).
            ket_qua.kiem(
                "Service: video không có số tập trong tiêu đề -> PENDING (không tự nhập mù)",
                video_import.status.value == "pending", video_import.status.value)

            # Quet LAI — phai IDEMPOTENT, khong tao them dong nao.
            scan_2 = svc.scan_source(admin, source_id, actor_role="owner")
            ket_qua.kiem("Service: quét lại idempotent (already_tracked=1)",
                        scan_2["already_tracked"] == 1, str(scan_2))
            _rows2, total_2 = trusted_store.find_imports(trusted_source_id=source_id)
            ket_qua.kiem("Appwrite: quét lại KHÔNG tạo dòng video_imports thứ hai",
                        total_2 == 1)

            # Quan tri tu gan series+so tap (giong hang doi nhap that) roi nhap.
            gan = svc.set_import_series(
                admin, video_import.import_id, series_id=series_id, episode_number=1)
            ket_qua.kiem("Appwrite: set_import_series ghi lại được (video_imports thật)",
                        gan is not None and gan["detected_episode_number"] == 1)

            nhap = svc.import_video(admin, video_import.import_id, publish=False)
            ket_qua.kiem("Service: import_video (thủ công) -> IMPORTED",
                        nhap["status"] == "imported", nhap.get("reason", ""))
            if nhap.get("created_episode_id"):
                episode = animation_store.get_episode(nhap["created_episode_id"])
                ket_qua.kiem("Appwrite: episode thật được tạo (animation_episodes)",
                            episode.external_id == VIDEO_ID_ON_DINH)

            # Trung lap: video DA la episode -> nhap lai phai bao DUPLICATE,
            # KHONG tao ban thu hai.
            nhap_lai = svc.import_video(admin, video_import.import_id, publish=False)
            ket_qua.kiem("Service: import_video một video đã nhập -> DUPLICATE",
                        nhap_lai["status"] == "duplicate", nhap_lai.get("reason", ""))

        # -- Nhat ky kiem duyet THAT ------------------------------------------
        events, _total_events = metadata_store.list_events(
            target_type="trusted_source", target_id=source_id)
        co_them_nguon = any(e.action == "trusted_source_add" for e in events)
        ket_qua.kiem("Appwrite: nhật ký kiểm duyệt ghi trusted_source_add thật",
                    co_them_nguon)

    finally:
        # -- Don dep: KHONG de rac lai tren Appwrite dev ----------------------
        if source_id:
            try:
                svc.remove_source(admin, source_id, actor_role="owner")
            except Exception as exc:
                print(f"[CẢNH BÁO] không xoá được trusted source tạm: {exc}")
        if series_id:
            try:
                for ep in animation_store.list_episodes(series_id, include_removed=True):
                    animation_store.delete_episode(ep.episode_id, "smoke_test_owner")
                animation_store.delete_series(series_id, "smoke_test_owner")
            except Exception as exc:
                print(f"[CẢNH BÁO] không xoá được series tạm: {exc}")
        try:
            _xoa_video_import_con_lai(trusted_store, VIDEO_ID_ON_DINH)
        except Exception as exc:
            print(f"[CẢNH BÁO] không xoá được video_import tạm: {exc}")

    print()
    print(f"TỔNG: {sum(1 for _, d, _ in ket_qua.items if d)}/{len(ket_qua.items)} kiểm tra đạt.")
    return 0 if ket_qua.tat_ca_dat else 1


if __name__ == "__main__":
    sys.exit(chay())
