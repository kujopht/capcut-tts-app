#!/usr/bin/env python3
"""
Smoke test THAT cho Auto-Ingestion Phase 5 ("Autonomous Multi-Series Channel
Ingestion") tren Appwrite tu luu tru (dev) VA YouTube Data API that — cung
triet ly voi `smoke_test_selfhost_trusted_sources.py` (Phase 5 goc).

    FAS_ENV_FILE=server/.env.selfhost python -m scripts.smoke_test_selfhost_channel_discovery

Goi THANG `TrustedSourceService.discover_channel` (khong qua HTTP/FastAPI) —
tranh phai dung mot tai khoan ADMIN that qua dang nhap/token, van la kiem
tra THAT voi Appwrite tu luu tru va YouTube Data API that tren MOT kenh
cong khai, on dinh, it video (kenh ca nhan cua Jawed Karim — "Me at the
zoo" — dung LAI id da dung o smoke test Phase 5 goc, tranh dung mot kenh
MOI chua duoc xac minh la on dinh).

AN TOAN:
- CHI doc metadata cong khai qua YouTube Data API tren kenh da biet on dinh.
- KHONG BAO GIO in `YOUTUBE_API_KEY`/`APPWRITE_API_KEY`.
- Moi ban ghi tao ra (TrustedSource/SeriesMapping/AnimationSeries/
  AnimationEpisode/VideoImport) deu bi XOA sau khi chay (ke ca khi that bai
  giua chung, qua try/finally) — KHONG de rac lai tren Appwrite dev.
"""

from __future__ import annotations

import sys
from typing import List, Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

#: Kenh ca nhan cua Jawed Karim — cong khai, on dinh, it video (dung LAI id
#: da xac minh o `smoke_test_selfhost_websub.py`/`smoke_test_selfhost_trusted_sources.py`).
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


def chay() -> int:
    from server.animation_domain import AnimationSeries
    from server.appwrite_animation_store import AppwriteAnimationStore
    from server.appwrite_store import AppwriteMetadataStore
    from server.appwrite_trusted_source_store import AppwriteTrustedSourceStore
    from server.config import load_settings
    from server.domain import Profile
    from server.trusted_source_service import TrustedSourceError, TrustedSourceService

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
    source_id: Optional[str] = None
    series_ids: List[str] = []
    video_ids_phat_hien: List[str] = []

    try:
        # -- Nguon kieu VIDEO DON LE phai bi tu choi ------------------------
        source_video = svc.create_source(
            admin, source_type="youtube_video", youtube_video_id="jNQXAC9IVRw",
            display_name="[smoke-test] video đơn (phải bị từ chối)",
            actor_role="owner")
        try:
            svc.discover_channel(admin, source_video["source_id"])
            ket_qua.kiem("Service: discover_channel từ chối nguồn video đơn lẻ", False)
        except TrustedSourceError:
            ket_qua.kiem("Service: discover_channel từ chối nguồn video đơn lẻ", True)
        finally:
            svc.remove_source(admin, source_video["source_id"], actor_role="owner")

        # -- Nguon kieu KENH that -------------------------------------------
        source = svc.create_source(
            admin, source_type="youtube_channel", youtube_channel_id=CHANNEL_ID_ON_DINH,
            display_name="[smoke-test] Phase 5 discover_channel",
            auto_import=True, auto_publish=False, minimum_confidence=0.1,
            actor_role="owner")
        source_id = source["source_id"]
        ket_qua.kiem("Appwrite: create_source (kênh thật)", bool(source_id))

        lan_1 = svc.discover_channel(admin, source_id, max_pages=1, actor_role="owner")
        video_ids_phat_hien = list(lan_1.confident_imports) + list(lan_1.pending_review) + \
            list(lan_1.duplicates) + list(lan_1.conflicts) + list(lan_1.excluded)
        series_ids = [g.series_id for g in lan_1.groups if g.series_id]

        ket_qua.kiem(
            "Service: discover_channel chạy được trên kênh thật (bounded 1 trang)",
            lan_1.videos_discovered > 0, f"videos_discovered={lan_1.videos_discovered}")
        tong_da_xu_ly = (
            lan_1.already_tracked + lan_1.matched_existing_mapping
            + sum(len(g.video_ids) for g in lan_1.groups))
        ket_qua.kiem(
            "Service: mọi video phát hiện đều được xử lý (đã theo dõi + khớp "
            "mapping + thuộc một cụm)",
            tong_da_xu_ly == lan_1.videos_discovered,
            f"tong_da_xu_ly={tong_da_xu_ly} videos_discovered={lan_1.videos_discovered}")

        rows, total = trusted_store.find_imports(trusted_source_id=source_id)
        ket_qua.kiem(
            "Appwrite: video_imports thật được ghi (trừ video bị loại tu khoá âm)",
            total == lan_1.videos_discovered - lan_1.excluded_negative_keyword,
            f"total={total} excluded_negative_keyword={lan_1.excluded_negative_keyword}")

        for sid in series_ids:
            series = animation_store.get_series(sid)
            ket_qua.kiem(
                f"Appwrite: series mới tạo ở trạng thái DRAFT ({sid})",
                series.state.value == "draft", series.state.value)

        # -- Idempotency: chay lai LAN 2 tren CUNG nguon ---------------------
        #
        # LUU Y: `candidate_groups` KHONG duoc phep dung de kiem idempotent —
        # mot video con o trang thai `NEW` (chua khop mapping/series nao, do
        # do van nam trong `TRANG_THAI_CHO_QUYET_DINH`) CO CHU DICH duoc gom
        # nhom/dem lai o MOI lan quet, de no van "cho quyet dinh" neu sau nay
        # admin tao mapping moi khop no (xem docstring `discover_channel`,
        # muc "existing admin decisions must win" — CHI quyet dinh CUOI CUNG
        # (khong con trong TRANG_THAI_CHO_QUYET_DINH) moi bi bo qua vinh vien
        # o lan quet sau). Vi vay `candidate_groups` o lan 2 CO THE > 0 mot
        # cach dung dan neu con video NEW — bat da xac nhan that qua thu
        # cong 2026-08-21: kenh test co dung MOT video khong khop gi (confidence
        # thap), nen no VAN duoc gom nhom lai o lan 2 (candidate_groups=1),
        # dung y thiet ke, khong phai loi.
        #
        # Bat idempotent THAT can kiem la: KHONG tao series/mapping MOI, VA
        # KHONG tao video_import trung — hai dieu do da duoc kiem rieng ben
        # duoi (tong_series/total khong doi).
        _series_list_1, tong_series_1 = animation_store.find_series(include_removed=True)
        lan_2 = svc.discover_channel(admin, source_id, max_pages=1, actor_role="owner")
        ket_qua.kiem(
            "Service: khám phá lại idempotent — không series MỚI nào được "
            "tạo (video còn NEW vẫn có thể được gom nhóm lại có chủ đích)",
            lan_2.new_series_created == 0,
            f"candidate_groups={lan_2.candidate_groups} "
            f"new_series_created={lan_2.new_series_created}")
        _rows_2, total_2 = trusted_store.find_imports(trusted_source_id=source_id)
        ket_qua.kiem(
            "Appwrite: khám phá lại KHÔNG tạo thêm video_imports",
            total_2 == total, f"total={total} total_2={total_2}")
        _series_list_2, tong_series_2 = animation_store.find_series(include_removed=True)
        ket_qua.kiem(
            "Appwrite: khám phá lại KHÔNG tạo thêm series (tổng series không đổi)",
            tong_series_2 == tong_series_1,
            f"tong_series_1={tong_series_1} tong_series_2={tong_series_2}")

    finally:
        # -- Don dep: KHONG de rac lai tren Appwrite dev ----------------------
        if source_id:
            try:
                svc.remove_source(admin, source_id, actor_role="owner")
            except Exception as exc:
                print(f"[CẢNH BÁO] không xoá được trusted source tạm: {exc}")
        for sid in series_ids:
            try:
                for ep in animation_store.list_episodes(sid, include_removed=True):
                    animation_store.delete_episode(ep.episode_id, admin.user_id)
                animation_store.delete_series(sid, admin.user_id)
            except Exception as exc:
                print(f"[CẢNH BÁO] không xoá được series tạm {sid}: {exc}")
        from server.appwrite_trusted_source_store import COL_IMPORTS
        from server.trusted_source_domain import video_import_id
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
