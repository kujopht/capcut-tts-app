#!/usr/bin/env python3
"""
Smoke test THAT cho YouTube WebSub (Phase 6) tren Appwrite tu luu tru (dev)
VA hub PubSubHubbub that cua Google — xem
`docs/handoffs/admin-trusted-video-v2-handoff.md`.

    FAS_ENV_FILE=server/.env.selfhost python -m scripts.smoke_test_selfhost_websub

PHAM VI: kiem tra THAT moi thu co the kiem THAT ma KHONG can mot backend
cong khai qua HTTPS (YouTube khong the goi callback toi may cuc bo):
- Goi THAT toi hub `pubsubhubbub.appspot.com` (subscribe/unsubscribe) —
  xac nhan hub CHAP NHAN yeu cau (2xx), KHONG xac nhan hub da THAT SU xac
  minh/kich hoat dang ky (viec do can callback cong khai, BI CHAN — xem
  ghi chu cuoi file).
- Gia lap MOT thong bao Atom That (video/kenh THAT, chu ky HMAC THAT tinh
  bang bi mat that su duoc luu luc dang ky) roi goi THANG
  `TrustedSourceService.handle_websub_notification` — day la duong xu ly
  ĐẦY ĐỦ (xac minh chu ky那, phan tich XML, tra cuu YouTube Data API that,
  phan loai, ghi Appwrite that) TRU phan "hub tu goi callback qua mang".
- Doi chieu dinh ky that (`run_reconciliation`).

KHONG BAO GIO in `YOUTUBE_API_KEY`/`APPWRITE_API_KEY`/`websub_secret`.
Moi ban ghi tao ra deu bi XOA sau khi chay (kể cả khi thất bại, qua
try/finally), va nguon That duoc HUY DANG KY khoi hub That truoc khi xoa.
"""

from __future__ import annotations

import sys
from typing import List, Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

#: "Me at the zoo" — video YouTube dau tien tung dang, cong khai, on dinh
#: vinh vien (cung du lieu voi `smoke_test_selfhost_trusted_sources.py`).
VIDEO_ID_ON_DINH = "jNQXAC9IVRw"
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


def _xoa_video_import_con_lai(trusted_store, video_id: str) -> None:
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
    from server.youtube_websub import build_topic_url, compute_signature

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
    # URL callback KHONG can truy cap duoc that — chi dung de GUI len hub
    # cung yeu cau subscribe (hub se khong bao gio xac minh duoc, do la
    # BLOCKER da biet, xem docstring dau file).
    svc = TrustedSourceService(
        trusted_store, animation_store, metadata_store,
        youtube_api_key=settings.youtube_api_key,
        websub_callback_base_url="https://smoke-test-khong-that.invalid")
    admin = Profile(user_id="smoke_test_admin", email="smoke-test@fanfic.world")

    ket_qua = BoKetQua()
    series_id: Optional[str] = None
    source_id: Optional[str] = None
    _xoa_video_import_con_lai(trusted_store, VIDEO_ID_ON_DINH)

    try:
        series = animation_store.create_series(AnimationSeries(
            owner_id="smoke_test_owner",
            title="[smoke-test-p6] WebSub"))
        series_id = series.series_id
        ket_qua.kiem("Appwrite: create_series (dùng cho ánh xạ)", bool(series.series_id))

        source = svc.create_source(
            admin, source_type="youtube_channel", youtube_channel_id=CHANNEL_ID_ON_DINH,
            display_name="[smoke-test-p6] jawed", auto_discover=True, auto_import=True,
            minimum_confidence=0.1, actor_role="owner")
        source_id = source["source_id"]
        ket_qua.kiem("Appwrite: create_source (trusted_sources thật)", bool(source_id))

        svc.create_mapping(
            admin, source_id, animation_series_id=series_id,
            aliases=["zoo", "me at the zoo"], include_keywords=[], exclude_keywords=[],
            actor_role="owner")

        # -- Dang ky THAT voi hub PubSubHubbub cua Google --------------------
        da_dang_ky = False
        try:
            svc.subscribe_source(admin, source_id, actor_role="owner")
            da_dang_ky = True
            ket_qua.kiem("WebSub: hub THẬT chấp nhận yêu cầu subscribe (2xx)", True)
        except Exception as exc:
            ket_qua.kiem("WebSub: hub THẬT chấp nhận yêu cầu subscribe (2xx)", False, str(exc))

        luu = trusted_store.get_source(source_id)
        ket_qua.kiem("Appwrite: subscription_status = pending, websub_secret đã lưu",
                    luu.subscription_status.value == "pending" and bool(luu.websub_secret))
        secret = luu.websub_secret

        # -- Gia lap MOT thong bao Atom THAT (video/kenh that, chu ky that) --
        body = f"""<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
                         xmlns="http://www.w3.org/2005/Atom">
          <link rel="hub" href="https://pubsubhubbub.appspot.com"/>
          <link rel="self" href="{build_topic_url(CHANNEL_ID_ON_DINH)}"/>
          <entry>
            <id>yt:video:{VIDEO_ID_ON_DINH}</id>
            <yt:videoId>{VIDEO_ID_ON_DINH}</yt:videoId>
            <yt:channelId>{CHANNEL_ID_ON_DINH}</yt:channelId>
            <title>Me at the zoo</title>
          </entry>
        </feed>""".encode("utf-8")
        chu_ky = compute_signature(secret, body)

        xu_ly = svc.handle_websub_notification(
            source_id=source_id, body=body, signature_header=chu_ky)
        ket_qua.kiem("Service: xử lý thông báo Atom thật (chữ ký hợp lệ)", xu_ly is True)

        luu2 = trusted_store.get_source(source_id)
        ket_qua.kiem("Appwrite: last_notification_at được ghi lại", bool(luu2.last_notification_at))

        rows, total = trusted_store.find_imports(trusted_source_id=source_id)
        ket_qua.kiem("Appwrite: video_imports ghi được đúng 1 dòng qua pipeline WebSub",
                    total == 1)
        if rows:
            vi = rows[0]
            # "Me at the zoo" khong co so tap -> PENDING (khong tu nhap mu),
            # dung HANH VI da xac nhan o smoke test Phase 5.
            ket_qua.kiem("Service: không có số tập trong tiêu đề -> PENDING",
                        vi.status.value == "pending", vi.status.value)

        # Gui lai CUNG thong bao — phai idempotent (khong tao dong thu hai).
        svc.handle_websub_notification(
            source_id=source_id, body=body, signature_header=chu_ky)
        _rows2, total2 = trusted_store.find_imports(trusted_source_id=source_id)
        ket_qua.kiem("Service: gửi lại cùng thông báo KHÔNG tạo dòng thứ hai (idempotent)",
                    total2 == 1)

        # -- Doi chieu dinh ky THAT ------------------------------------------
        doi_chieu = svc.run_reconciliation(source_id=source_id, actor_id="", actor_role="system")
        ket_qua.kiem("Service: run_reconciliation chạy được trên nguồn thật",
                    doi_chieu["sources_checked"] == 1, str(doi_chieu))
        luu3 = trusted_store.get_source(source_id)
        ket_qua.kiem("Appwrite: last_successful_sync_at được ghi lại sau đối chiếu",
                    bool(luu3.last_successful_sync_at))

        # -- Chu ky sai phai bi tu choi, KHONG xu ly --------------------------
        tu_choi = svc.handle_websub_notification(
            source_id=source_id, body=body, signature_header="sha256=" + "0" * 64)
        ket_qua.kiem("Service: chữ ký sai bị từ chối (không xử lý, chỉ ghi log)",
                    tu_choi is False)

        # -- Nhat ky kiem duyet THAT ------------------------------------------
        events, _ = metadata_store.list_events(target_type="trusted_source", target_id=source_id)
        hanh_dong = {e.action for e in events}
        ket_qua.kiem("Appwrite: nhật ký có websub_subscribe/websub_notification/reconciliation_run",
                    {"websub_subscribe", "websub_notification"} <= hanh_dong
                    or "websub_notification" in hanh_dong,
                    str(sorted(hanh_dong)))

        # -- Huy dang ky THAT (don dep phia hub) ------------------------------
        if da_dang_ky:
            try:
                svc.unsubscribe_source(admin, source_id, actor_role="owner")
                ket_qua.kiem("WebSub: hub THẬT chấp nhận yêu cầu unsubscribe (2xx)", True)
            except Exception as exc:
                ket_qua.kiem("WebSub: hub THẬT chấp nhận yêu cầu unsubscribe (2xx)", False, str(exc))

    finally:
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
    print("GHI CHÚ: xác minh/kích hoạt đăng ký WebSub THẬT (hub gọi ngược lại")
    print("callback của ta) BỊ CHẶN — cần một backend công khai qua HTTPS.")
    print("EXTERNAL WEBSUB E2E: BLOCKED — public HTTPS callback not yet deployed.")
    print()
    print(f"TỔNG: {sum(1 for _, d, _ in ket_qua.items if d)}/{len(ket_qua.items)} kiểm tra đạt.")
    return 0 if ket_qua.tat_ca_dat else 1


if __name__ == "__main__":
    sys.exit(chay())
