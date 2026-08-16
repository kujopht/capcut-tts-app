"""
Tang dich vu cho Trusted Video Sources (Phase 5, Admin Control Center V2 /
Animation Phan B).

MOI duong ghi (them nguon, sua cai dat, anh xa series, quet video, nhap/tu
choi/bo qua) di qua day — cung nguyen tac voi `SocialService`/
`CreatorService`: MOT tang, khong route nao cham thang kho.

BA phu thuoc ngoai chinh:
- `self._store` (`MockTrustedSourceStore`/`AppwriteTrustedSourceStore`) —
  nguon/anh xa/hang doi nhap.
- `self._animation_store` — DOC LAP, de doc/tao `AnimationSeries`/
  `AnimationEpisode` that (xem docstring dau `animation_domain.py`).
- `self._metadata_store` — CHI de ghi nhat ky kiem duyet
  (`record_event`/`list_events`), dung CHUNG voi Phase 1-4.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from server.adapters import NotFoundError
from server.animation_domain import AnimationEpisode, AnimationSource
from server.domain import ModerationEvent, Profile, PublishState, now_iso
from server.trusted_source_domain import (
    ImportStatus,
    SeriesMapping,
    SubscriptionStatus,
    TrustedSource,
    TrustedSourceType,
    VideoImport,
)
from server.video_classifier import classify_video
from server.youtube_client import (
    SourceUrlRef,
    YouTubeApiError,
    YouTubeClient,
    YouTubeConfigError,
    parse_source_url,
)
from server.youtube_websub import (
    WebSubClient,
    WebSubConfigError,
    WebSubError,
    WebSubParseError,
    build_callback_url,
    build_topic_url,
    new_secret as new_websub_secret,
    parse_notification,
    verify_signature,
)

#: So trang toi da MOI LAN QUET (moi trang 50 video) — "bounded YouTube API
#: calls", xem yeu cau hieu nang Phase 5. Quet tiep bang cach goi lai voi
#: `page_token` tra ve.
MAX_SCAN_PAGES = 5
DEFAULT_SCAN_PAGES = 2

#: Doi chieu dinh ky (Phase 6) chi quet MOT trang/nguon — day la du phong
#: cho video BO LO, khong phai mot lan quet lich su day du (nguoi quan tri
#: dung "Quet video co san" thu cong cho viec do).
RECONCILIATION_MAX_PAGES = 1
#: Tu dong gia han dang ky khi con duoi nguong nay truoc han het — WebSub
#: KHONG BAO GIO cap thoi han vinh vien (xem `server/youtube_websub.py`).
RENEWAL_WINDOW = timedelta(hours=24)


class TrustedSourceError(Exception):
    """Loi dau vao/nghiep vu (URL khong doc duoc, series khong ton tai,
    trang thai khong hop le...) — tang route doi thanh HTTP 400."""


class TrustedSourceService:
    def __init__(self, store: Any, animation_store: Any, metadata_store: Any,
                youtube_api_key: str = "", websub_callback_base_url: str = ""):
        self._store = store
        self._animation_store = animation_store
        self._metadata_store = metadata_store
        self._youtube_api_key = youtube_api_key
        self._websub_callback_base_url = (websub_callback_base_url or "").rstrip("/")

    def _youtube(self) -> YouTubeClient:
        """Nem `YouTubeConfigError` NGAY o day neu chua cau hinh — tang tren
        (route) doi thanh trang thai "chưa cấu hình" ro rang, KHONG bao gio
        am tham tra ket qua rong."""
        return YouTubeClient(self._youtube_api_key)

    def youtube_configured(self) -> bool:
        return bool(self._youtube_api_key)

    def _websub(self) -> WebSubClient:
        return WebSubClient()

    def websub_configured(self) -> bool:
        """`False` khi CHUA co URL callback cong khai — Phase 6 dang phat
        trien tren backend cuc bo, YouTube khong the goi toi duoc (xem
        docstring dau `server/youtube_websub.py`). Frontend hien "Chưa cấu
        hình" thay vi mot trang thai dang ky bia dat."""
        return bool(self._websub_callback_base_url)

    # ==================================================== them nguon (preview)

    def preview_source_url(self, raw_url: str) -> Dict[str, Any]:
        """
        Doc mot URL/ID nguoi dung dan vao, GOI YouTube Data API de lay
        thong tin xem truoc — KHONG tao gi ca. Day la buoc BAT BUOC truoc
        "Add as Trusted Source" (xem dac ta Phase 5, muc 5): quan tri PHAI
        thay ten kenh/playlist THAT truoc khi xac nhan tin cay.
        """
        ref = parse_source_url(raw_url)
        if ref is None:
            raise TrustedSourceError(
                "Không đọc được đây là video, kênh hay playlist YouTube nào. "
                "Dán URL đầy đủ, hoặc ID kênh/playlist.")
        yt = self._youtube()
        return self._giai_quyet_preview(yt, ref)

    def _giai_quyet_preview(self, yt: YouTubeClient, ref: SourceUrlRef) -> Dict[str, Any]:
        if ref.kind == "video":
            video = yt.get_video(ref.value)
            if video is None:
                raise TrustedSourceError("Không tìm thấy video này trên YouTube.")
            kenh = yt.get_channel(video.channel_id)
            return {
                "source_type": TrustedSourceType.YOUTUBE_VIDEO.value,
                "youtube_channel_id": video.channel_id,
                "youtube_playlist_id": "",
                "youtube_video_id": video.video_id,
                "display_name": video.title,
                "thumbnail_url": video.thumbnail_url,
                "channel_title": video.channel_title,
                "channel_thumbnail_url": kenh.thumbnail_url if kenh else "",
            }

        if ref.kind == "playlist":
            playlist = yt.get_playlist(ref.value)
            if playlist is None:
                raise TrustedSourceError("Không tìm thấy playlist này trên YouTube.")
            return {
                "source_type": TrustedSourceType.YOUTUBE_PLAYLIST.value,
                "youtube_channel_id": playlist.channel_id,
                "youtube_playlist_id": playlist.playlist_id,
                "display_name": playlist.title,
                "thumbnail_url": playlist.thumbnail_url,
                "channel_title": playlist.channel_title,
                "item_count": playlist.item_count,
            }

        # BA dang con lai deu la KENH — chi khac cach tra cuu.
        if ref.kind == "channel_id":
            kenh = yt.get_channel(ref.value)
        elif ref.kind == "channel_handle":
            kenh = yt.get_channel_by_handle(ref.value)
        else:  # channel_username
            kenh = yt.get_channel_by_username(ref.value)
        if kenh is None:
            raise TrustedSourceError(
                "Không tìm thấy kênh này trên YouTube. Nếu đây là URL dạng "
                "/c/tên-tuỳ-chỉnh, hãy thử dán URL /channel/UC... hoặc /@handle.")
        return {
            "source_type": TrustedSourceType.YOUTUBE_CHANNEL.value,
            "youtube_channel_id": kenh.channel_id,
            "youtube_playlist_id": "",
            "display_name": kenh.title,
            "thumbnail_url": kenh.thumbnail_url,
            "channel_title": kenh.title,
        }

    # ==================================================== trusted source CRUD

    #: Voi tung loai nguon, truong nao la DINH DANH duy nhat can kiem trung
    #: lap truoc khi them (xem `_dinh_danh_da_ton_tai`).
    _TRUONG_DINH_DANH = {
        TrustedSourceType.YOUTUBE_CHANNEL: "youtube_channel_id",
        TrustedSourceType.YOUTUBE_PLAYLIST: "youtube_playlist_id",
        TrustedSourceType.YOUTUBE_VIDEO: "youtube_video_id",
    }

    def create_source(self, admin: Profile, *, source_type: str,
                      youtube_channel_id: str = "", youtube_playlist_id: str = "",
                      youtube_video_id: str = "",
                      display_name: str, thumbnail_url: str = "",
                      auto_discover: bool = False, auto_import: bool = False,
                      auto_publish: bool = False, minimum_confidence: float = 0.9,
                      actor_role: str = "") -> Dict[str, Any]:
        try:
            loai = TrustedSourceType(source_type)
        except ValueError:
            raise TrustedSourceError("source_type không hợp lệ.")
        if loai in (TrustedSourceType.DIRECT_HLS, TrustedSourceType.DIRECT_MP4):
            raise TrustedSourceError(
                "Loại nguồn này chưa được triển khai (chỉ YouTube ở Phase 5).")

        moi = TrustedSource(
            source_type=loai,
            youtube_channel_id=youtube_channel_id.strip(),
            youtube_playlist_id=youtube_playlist_id.strip(),
            youtube_video_id=youtube_video_id.strip(),
            display_name=display_name.strip(),
            thumbnail_url=thumbnail_url,
            auto_discover=auto_discover, auto_import=auto_import,
            auto_publish=auto_publish,
            minimum_confidence=max(0.0, min(1.0, minimum_confidence)),
            created_by=admin.user_id,
        )
        if self._dinh_danh_da_ton_tai(moi):
            raise TrustedSourceError("Nguồn này đã được thêm làm nguồn tin cậy trước đó.")

        source = self._store.create_source(moi)
        self._ghi_nhat_ky(
            "trusted_source_add", target_id=source.source_id,
            actor_id=admin.user_id, actor_role=actor_role,
            note=f"Thêm nguồn tin cậy: {source.display_name}")
        return source.to_dict()

    def _dinh_danh_da_ton_tai(self, moi: TrustedSource) -> bool:
        """So nguon tin cay du kien khong lon (hang chuc, khong phai hang
        nghin) — quet toan bo o day CHAP NHAN DUOC, khong phai duong nong
        tai trang danh sach thuong."""
        truong = self._TRUONG_DINH_DANH.get(moi.source_type)
        gia_tri = getattr(moi, truong, "") if truong else ""
        if not gia_tri:
            return False
        items, _ = self._store.find_sources(limit=None)
        return any(
            s.source_type == moi.source_type and getattr(s, truong, "") == gia_tri
            for s in items)

    def admin_list_sources(self, *, query: str = "", enabled: Optional[bool] = None,
                           limit: int = 25, offset: int = 0) -> Dict[str, Any]:
        items, total = self._store.find_sources(
            query=query, enabled=enabled, limit=limit, offset=offset)
        dem = self._store.mapping_counts([s.source_id for s in items])
        rows = []
        for s in items:
            d = s.to_dict()
            d["mapping_count"] = dem.get(s.source_id, 0)
            rows.append(d)
        return {"sources": rows, "total": total, "limit": limit, "offset": offset}

    def admin_source_detail(self, source_id: str) -> Optional[Dict[str, Any]]:
        try:
            source = self._store.get_source(source_id)
        except NotFoundError:
            return None
        mappings = self._store.list_mappings(source_id)
        series_ids = [m.animation_series_id for m in mappings]
        ten_series = self._ten_series_theo_id(series_ids)
        anh_xa_ra = []
        for m in mappings:
            d = m.to_dict()
            d["series_title"] = ten_series.get(m.animation_series_id, "")
            anh_xa_ra.append(d)
        gan_day, _ = self._store.find_imports(trusted_source_id=source_id, limit=10)
        return {
            "source": source.to_dict(),
            "mappings": anh_xa_ra,
            "recent_imports": [i.to_dict() for i in gan_day],
            # Phase 6 — su that TOAN CUC (khong phai theo tung nguon): frontend
            # can biet WebSub co the dung duoc o MOI TRUONG nay hay khong de
            # hien "Chưa cấu hình" thay vi mot trang thai dang ky bia dat.
            "websub_configured": self.websub_configured(),
        }

    def _ten_series_theo_id(self, series_ids: Sequence[str]) -> Dict[str, str]:
        """Phase 5 (performance audit) — TRUOC DAY goi `get_series` RIENG LE
        cho tung ID phan biet (N+1: mot trang Import Queue 100 dong co the
        keo toi 100 truy van rieng). Gio doc MOT LAN qua
        `get_series_by_ids` (theo lo, xem cac kho Animation) roi tra ve
        tieu de rong cho ID khong tim thay — CUNG hanh vi voi truoc day."""
        ds = [s for s in series_ids if s]
        theo_id = self._animation_store.get_series_by_ids(ds)
        return {sid: theo_id[sid].title if sid in theo_id else ""
                for sid in dict.fromkeys(ds)}

    def update_source(self, admin: Profile, source_id: str, fields: Dict[str, Any],
                      *, actor_role: str = "") -> Optional[Dict[str, Any]]:
        try:
            source = self._store.update_source(source_id, fields)
        except NotFoundError:
            return None
        self._ghi_nhat_ky(
            "trusted_source_update", target_id=source_id, actor_id=admin.user_id,
            actor_role=actor_role, note=f"Sửa cài đặt: {', '.join(fields.keys())}")
        return source.to_dict()

    def set_source_enabled(self, admin: Profile, source_id: str, enabled: bool,
                           *, actor_role: str = "") -> Optional[Dict[str, Any]]:
        try:
            source = self._store.update_source(source_id, {"enabled": enabled})
        except NotFoundError:
            return None
        self._ghi_nhat_ky(
            "trusted_source_enable" if enabled else "trusted_source_disable",
            target_id=source_id, actor_id=admin.user_id, actor_role=actor_role)
        return source.to_dict()

    def remove_source(self, admin: Profile, source_id: str, *,
                      actor_role: str = "") -> bool:
        try:
            source = self._store.get_source(source_id)
        except NotFoundError:
            return False
        # Huy dang ky WebSub TRUOC khi xoa (Phase 6) — CO GANG HET SUC, khong
        # chan viec xoa neu hub khong phan hoi (nguon sap bien mat khoi kho
        # cua ta, con thue bao "ma" o phia hub khong con y nghia gi voi
        # nghiep vu, ghi loi de quan tri biet neu can tu don don sau).
        if (self.websub_configured()
                and source.subscription_status is not SubscriptionStatus.NONE):
            try:
                self._thuc_hien_huy_dang_ky(source)
            except WebSubError as exc:
                self._ghi_nhat_ky(
                    "websub_failure", target_id=source_id, actor_id=admin.user_id,
                    actor_role=actor_role, note=str(exc))
        self._store.delete_source(source_id)
        self._ghi_nhat_ky(
            "trusted_source_remove", target_id=source_id, actor_id=admin.user_id,
            actor_role=actor_role, note=f"Bỏ tin cậy: {source.display_name}")
        return True

    # ==================================================== series mapping

    def create_mapping(self, admin: Profile, source_id: str, *,
                       animation_series_id: str, aliases: List[str],
                       include_keywords: List[str], exclude_keywords: List[str],
                       minimum_confidence: Optional[float] = None,
                       auto_import: Optional[bool] = None,
                       auto_publish: Optional[bool] = None,
                       actor_role: str = "") -> Dict[str, Any]:
        self._store.get_source(source_id)  # 404 neu khong ton tai
        try:
            self._animation_store.get_series(animation_series_id)
        except NotFoundError:
            raise TrustedSourceError("Không tìm thấy series animation này.")
        mapping = self._store.create_mapping(SeriesMapping(
            trusted_source_id=source_id, animation_series_id=animation_series_id,
            aliases=[a.strip() for a in aliases if a.strip()],
            include_keywords=[k.strip() for k in include_keywords if k.strip()],
            exclude_keywords=[k.strip() for k in exclude_keywords if k.strip()],
            minimum_confidence=minimum_confidence, auto_import=auto_import,
            auto_publish=auto_publish,
        ))
        self._ghi_nhat_ky(
            "youtube_mapping_create", target_id=mapping.mapping_id,
            actor_id=admin.user_id, actor_role=actor_role,
            note=f"Ánh xạ nguồn tới series {animation_series_id}")
        return mapping.to_dict()

    def update_mapping(self, admin: Profile, mapping_id: str, fields: Dict[str, Any],
                       *, actor_role: str = "") -> Optional[Dict[str, Any]]:
        try:
            mapping = self._store.update_mapping(mapping_id, fields)
        except NotFoundError:
            return None
        self._ghi_nhat_ky(
            "youtube_mapping_update", target_id=mapping_id, actor_id=admin.user_id,
            actor_role=actor_role)
        return mapping.to_dict()

    def remove_mapping(self, admin: Profile, mapping_id: str, *,
                       actor_role: str = "") -> bool:
        try:
            self._store.get_mapping(mapping_id)
        except NotFoundError:
            return False
        self._store.delete_mapping(mapping_id)
        self._ghi_nhat_ky(
            "youtube_mapping_remove", target_id=mapping_id, actor_id=admin.user_id,
            actor_role=actor_role)
        return True

    # ==================================================== quet video co san

    def scan_source(self, admin: Profile, source_id: str, *,
                    page_token: str = "", max_pages: int = DEFAULT_SCAN_PAGES,
                    actor_role: str = "") -> Dict[str, Any]:
        """
        Quet video CO SAN cua mot nguon — xem dac ta Phase 5 muc 11 (Historical
        Backfill). BI CHAN theo `max_pages` (moi trang 50 video) — muon quet
        tiep thi goi lai voi `next_page_token` tra ve.

        IDEMPOTENT: video DA CO ban ghi `VideoImport` tu truoc (bat ke trang
        thai) KHONG bi phan loai lai/ghi de — mot quyet dinh quan tri da co
        (vi du da Tu choi) khong tu nhien doi khi quet lai. Video DA la mot
        `AnimationEpisode` that (o BAT KY series nao) duoc danh dau DUPLICATE
        ngay, khong phan loai.
        """
        source = self._store.get_source(source_id)
        self._ghi_nhat_ky(
            "video_scan_start", target_id=source_id, actor_id=admin.user_id,
            actor_role=actor_role)

        try:
            yt = self._youtube()
            ung_vien, next_token = self._lay_ung_vien(yt, source, page_token, max_pages)
        except (YouTubeConfigError, YouTubeApiError) as exc:
            self._store.record_scan_result(source_id, success=False,
                                           error_message=str(exc))
            raise

        mappings = self._store.list_mappings(source_id)
        episodes_by_series = self._tap_da_co_theo_series(
            [m.animation_series_id for m in mappings])

        video_ids = [v["video_id"] for v in ung_vien]
        da_la_tap = self._animation_store.episodes_by_external_ids(video_ids)
        da_theo_doi = self._store.imports_by_video_ids(video_ids)

        dem = {"detected": len(ung_vien), "matched": 0, "pending": 0,
              "auto_imported": 0, "auto_published": 0, "excluded": 0,
              "conflicts": 0, "duplicates": 0, "already_tracked": 0}

        for v in ung_vien:
            vid = v["video_id"]
            if vid in da_theo_doi:
                dem["already_tracked"] += 1
                continue  # DA CO ban ghi — KHONG phan loai lai (idempotent).

            trang_thai, matched = self._phan_loai_va_ghi_mot_video(
                source=source, mappings=mappings, episodes_by_series=episodes_by_series,
                video=v, da_la_tap=da_la_tap)

            if trang_thai in (ImportStatus.AUTO_IMPORTED, ImportStatus.AUTO_PUBLISHED):
                dem["auto_imported" if trang_thai is ImportStatus.AUTO_IMPORTED
                    else "auto_published"] += 1
            elif trang_thai is ImportStatus.PENDING:
                dem["pending"] += 1
            elif trang_thai is ImportStatus.IGNORED:
                dem["excluded"] += 1
            elif trang_thai is ImportStatus.CONFLICT:
                dem["conflicts"] += 1
            elif trang_thai is ImportStatus.DUPLICATE:
                dem["duplicates"] += 1
            if matched:
                dem["matched"] += 1

        self._store.record_scan_result(source_id, success=True)
        dem["next_page_token"] = next_token
        return dem

    def _phan_loai_va_ghi_mot_video(
        self, *, source: TrustedSource, mappings: List[SeriesMapping],
        episodes_by_series: Dict[str, Sequence[int]], video: Dict[str, Any],
        da_la_tap: Dict[str, AnimationEpisode],
    ) -> tuple:
        """
        Phan loai + luu MOT video — dung CHUNG boi `scan_source` (quet thu
        cong/doi chieu dinh ky) VA pipeline WebSub (Phase 6,
        `_xu_ly_mot_video_websub`). MOT duong quyet dinh DUY NHAT: hai kenh
        phat hien (quet thu cong vs thong bao tu dong) khong duoc phep dua
        ra ket qua KHAC NHAU cho cung mot video.

        Tra `(status, matched: bool)` — `matched` la co `ket_qua.series_id`
        hay khong (dung de dem "Khớp series", KHONG tinh cho nhanh DUPLICATE
        vi video do chua tung duoc phan loai).
        """
        vid = video["video_id"]
        if vid in da_la_tap:
            self._store.create_import_once(VideoImport(
                trusted_source_id=source.source_id, youtube_video_id=vid,
                title=video["title"], channel_id=video["channel_id"],
                channel_title=video["channel_title"], thumbnail_url=video["thumbnail_url"],
                published_at=video["published_at"], duration_seconds=video["duration_seconds"],
                status=ImportStatus.DUPLICATE,
                reason=f"Đã là tập {da_la_tap[vid].episode_id} trong series khác."))
            return ImportStatus.DUPLICATE, False

        ket_qua = classify_video(
            title=video["title"], channel_id=video["channel_id"],
            trusted_source=source, mappings=mappings,
            episodes_by_series=episodes_by_series)

        trang_thai, ly_do, episode_id = self._quyet_dinh_trang_thai(
            source=source, mappings_by_id={m.mapping_id: m for m in mappings},
            ket_qua=ket_qua, video=video, episodes_by_series=episodes_by_series)

        self._store.create_import_once(VideoImport(
            trusted_source_id=source.source_id, youtube_video_id=vid,
            title=video["title"], channel_id=video["channel_id"],
            channel_title=video["channel_title"], thumbnail_url=video["thumbnail_url"],
            published_at=video["published_at"], duration_seconds=video["duration_seconds"],
            detected_mapping_id=ket_qua.mapping_id,
            detected_series_id=ket_qua.series_id,
            detected_episode_number=ket_qua.episode_number,
            confidence=ket_qua.confidence, signals=list(ket_qua.signals),
            status=trang_thai, reason=ly_do, created_episode_id=episode_id,
        ))
        return trang_thai, bool(ket_qua.series_id)

    def _lay_ung_vien(self, yt: YouTubeClient, source: TrustedSource,
                      page_token: str, max_pages: int) -> tuple:
        """Tra `([{video_id, title, channel_id, channel_title, thumbnail_url,
        published_at, duration_seconds}, ...], next_page_token)`."""
        if source.source_type is TrustedSourceType.YOUTUBE_VIDEO:
            # Nguon la MOT video don le — khong co gi de phan trang, "quet"
            # o day chi la phan loai lai chinh video do (idempotent nhu moi
            # nguon khac, xem vong lap chinh trong `scan_source`).
            info = yt.get_video(source.youtube_video_id)
            if info is None:
                raise YouTubeApiError(
                    "Không còn truy cập được video này qua YouTube Data API "
                    "(có thể đã bị gỡ hoặc chuyển riêng tư).")
            return [{
                "video_id": info.video_id, "title": info.title,
                "channel_id": info.channel_id, "channel_title": info.channel_title,
                "thumbnail_url": info.thumbnail_url,
                "published_at": info.published_at,
                "duration_seconds": info.duration_seconds,
            }], ""

        if source.source_type is TrustedSourceType.YOUTUBE_PLAYLIST:
            playlist_id = source.youtube_playlist_id
        else:
            kenh = yt.get_channel(source.youtube_channel_id)
            if kenh is None or not kenh.uploads_playlist_id:
                raise YouTubeApiError("Không đọc được danh sách video của kênh này.")
            playlist_id = kenh.uploads_playlist_id

        items: List[Dict[str, Any]] = []
        token = page_token
        for _ in range(max(1, min(MAX_SCAN_PAGES, max_pages))):
            trang, token = yt.list_playlist_items(playlist_id, page_token=token)
            items.extend(trang)
            if not token:
                break

        video_ids = [
            str((it.get("contentDetails") or {}).get("videoId") or "")
            for it in items
        ]
        video_ids = [v for v in video_ids if v]
        chi_tiet = yt.get_videos(video_ids) if video_ids else {}

        ung_vien = []
        for it in items:
            vid = str((it.get("contentDetails") or {}).get("videoId") or "")
            info = chi_tiet.get(vid)
            if info is None:
                continue  # video rieng tu/da bi go — bo qua, khong bia du lieu.
            ung_vien.append({
                "video_id": info.video_id, "title": info.title,
                "channel_id": info.channel_id, "channel_title": info.channel_title,
                "thumbnail_url": info.thumbnail_url,
                "published_at": info.published_at,
                "duration_seconds": info.duration_seconds,
            })
        return ung_vien, token

    def _tap_da_co_theo_series(
        self, series_ids: Sequence[str]) -> Dict[str, Sequence[int]]:
        ra: Dict[str, Sequence[int]] = {}
        for sid in dict.fromkeys(s for s in series_ids if s):
            eps = self._animation_store.list_episodes(sid, include_removed=True)
            ra[sid] = [e.order_index for e in eps]
        return ra

    def _quyet_dinh_trang_thai(
        self, *, source: TrustedSource, mappings_by_id: Dict[str, SeriesMapping],
        ket_qua, video: Dict[str, Any],
        episodes_by_series: Dict[str, Sequence[int]],
    ) -> tuple:
        """Tra `(status, reason, created_episode_id)`. KHONG tu tao episode
        khi thieu so tap hoac khi CONFLICT — chi tao khi that su du dieu
        kien auto_import/auto_publish VA khong xung dot."""
        if ket_qua.excluded:
            ly_do = "; ".join(s for s in ket_qua.signals if "loại trừ" in s)
            return ImportStatus.IGNORED, ly_do or "Khớp từ khoá loại trừ.", ""

        if not ket_qua.series_id:
            return ImportStatus.NEW, "", ""

        mapping = mappings_by_id.get(ket_qua.mapping_id)
        nguong = (
            (mapping.minimum_confidence if mapping and mapping.minimum_confidence is not None
             else source.minimum_confidence))
        if ket_qua.confidence < nguong:
            return ImportStatus.PENDING, (
                f"Độ tin cậy {ket_qua.confidence:.2f} dưới ngưỡng {nguong:.2f}."), ""

        auto_import = (mapping.auto_import if mapping and mapping.auto_import is not None
                       else source.auto_import)
        if not auto_import:
            return ImportStatus.PENDING, "Đủ độ tin cậy, chờ quản trị nhập bằng tay.", ""

        if ket_qua.episode_number is None:
            return ImportStatus.PENDING, "Chưa phát hiện được số tập.", ""

        da_co = episodes_by_series.get(ket_qua.series_id, ())
        # `da_co` chi luu SO — can biet VIDEO nao dang chiem de bao CONFLICT
        # dung nghia (trung so voi mot video KHAC, khong phai chinh no).
        if ket_qua.episode_number in da_co:
            return ImportStatus.CONFLICT, (
                f"Series đã có tập {ket_qua.episode_number} từ video khác."), ""

        auto_publish = (mapping.auto_publish if mapping and mapping.auto_publish is not None
                        else source.auto_publish)
        try:
            series = self._animation_store.get_series(ket_qua.series_id)
        except NotFoundError:
            return ImportStatus.PENDING, "Không tìm thấy series đã ánh xạ.", ""

        episode = self._animation_store.create_episode(AnimationEpisode(
            series_id=ket_qua.series_id, owner_id=series.owner_id,
            title=video["title"], source=AnimationSource.YOUTUBE,
            external_id=video["video_id"], order_index=ket_qua.episode_number,
            state=PublishState.PUBLISHED if auto_publish else PublishState.DRAFT,
            duration_seconds=video["duration_seconds"],
        ))
        trang_thai = (ImportStatus.AUTO_PUBLISHED if auto_publish
                     else ImportStatus.AUTO_IMPORTED)
        return trang_thai, "Tự động nhập theo cài đặt nguồn/ánh xạ.", episode.episode_id

    # ==================================================== hang doi nhap (thu cong)

    def admin_list_imports(self, *, status: str = "", trusted_source_id: str = "",
                           series_id: str = "", limit: int = 25,
                           offset: int = 0) -> Dict[str, Any]:
        """
        Phase 5 (performance audit) — lam giau MOT TRANG hang doi nhap bang
        SO LUONG truy van CO DINH khong phu thuoc so dong: 1 (trang) + 1
        (nguon hang loat) + 1 (series hang loat, ben trong `_ten_series_theo_id`).
        TRUOC DAY `ten_nguon` goi `get_source` RIENG LE cho tung ID nguon
        phan biet (N+1: trang toi da 100 dong co the toi 100 truy van rieng
        chi de lay `display_name`) — gio dung `get_sources_by_ids` (theo lo),
        cung idiom voi `mapping_counts`.
        """
        items, total = self._store.find_imports(
            status=status, trusted_source_id=trusted_source_id,
            series_id=series_id, limit=limit, offset=offset)
        nguon_ids = [i.trusted_source_id for i in items if i.trusted_source_id]
        ten_series = self._ten_series_theo_id([i.detected_series_id for i in items])
        nguon_theo_id = self._store.get_sources_by_ids(nguon_ids)
        ten_nguon = {sid: (nguon_theo_id[sid].display_name if sid in nguon_theo_id else "")
                    for sid in dict.fromkeys(nguon_ids)}
        rows = []
        for i in items:
            d = i.to_dict()
            d["source_display_name"] = ten_nguon.get(i.trusted_source_id, "")
            d["series_title"] = ten_series.get(i.detected_series_id, "")
            rows.append(d)
        return {"imports": rows, "total": total, "limit": limit, "offset": offset}

    def set_import_series(self, admin: Profile, import_id: str, *,
                          series_id: str, episode_number: Optional[int],
                          actor_role: str = "") -> Optional[Dict[str, Any]]:
        """Quan tri TU gan/sua series+so tap truoc khi nhap — dac ta Phase 5
        muc 9 ("choose/change series", "set/change episode number")."""
        try:
            self._store.get_import(import_id)
        except NotFoundError:
            return None
        if series_id:
            try:
                self._animation_store.get_series(series_id)
            except NotFoundError:
                raise TrustedSourceError("Không tìm thấy series animation này.")
        updated = self._store.update_import(import_id, {
            "detected_series_id": series_id,
            "detected_episode_number": episode_number,
        })
        return updated.to_dict()

    def import_video(self, admin: Profile, import_id: str, *, publish: bool,
                     actor_role: str = "") -> Dict[str, Any]:
        """
        Nhap THU CONG (nut "Nhap"/"Nhap + Xuat ban"). KIEM LAI trung lap/xung
        dot NGAY LUC NAY (khong chi tin ket qua quet cu — trang thai co the
        da doi giua luc quet va luc bam nut), KHONG BAO GIO ghi de am tham.
        """
        video = self._store.get_import(import_id)
        if not video.detected_series_id:
            raise TrustedSourceError("Chưa gán series cho video này.")
        if video.detected_episode_number is None:
            raise TrustedSourceError("Chưa có số tập cho video này.")

        da_la_tap = self._animation_store.episodes_by_external_ids(
            [video.youtube_video_id])
        if video.youtube_video_id in da_la_tap:
            updated = self._store.update_import(import_id, {
                "status": ImportStatus.DUPLICATE,
                "reason": f"Đã là tập {da_la_tap[video.youtube_video_id].episode_id}.",
            })
            return updated.to_dict()

        try:
            series = self._animation_store.get_series(video.detected_series_id)
        except NotFoundError:
            raise TrustedSourceError("Không tìm thấy series đã gán.")

        da_co = self._animation_store.list_episodes(
            video.detected_series_id, include_removed=True)
        xung_dot = next(
            (e for e in da_co if e.order_index == video.detected_episode_number
             and e.external_id != video.youtube_video_id), None)
        if xung_dot is not None:
            updated = self._store.update_import(import_id, {
                "status": ImportStatus.CONFLICT,
                "reason": f"Tập {video.detected_episode_number} đã có video khác.",
            })
            return updated.to_dict()

        episode = self._animation_store.create_episode(AnimationEpisode(
            series_id=video.detected_series_id, owner_id=series.owner_id,
            title=video.title, source=AnimationSource.YOUTUBE,
            external_id=video.youtube_video_id,
            order_index=video.detected_episode_number,
            state=PublishState.PUBLISHED if publish else PublishState.DRAFT,
            duration_seconds=video.duration_seconds,
        ))
        # `IMPORTED` du khi co publish=True — cac gia tri AUTO_* chi danh
        # cho video HE THONG tu nhap luc quet (xem docstring `ImportStatus`),
        # day la hanh dong THU CONG cua quan tri.
        updated = self._store.update_import(import_id, {
            "status": ImportStatus.IMPORTED,
            "created_episode_id": episode.episode_id,
            "reviewed_by": admin.user_id, "reviewed_at": _now(),
        })
        self._ghi_nhat_ky(
            "video_import_publish" if publish else "video_import",
            target_id=import_id, actor_id=admin.user_id, actor_role=actor_role,
            note=f"episode={episode.episode_id}")
        return updated.to_dict()

    def reject_import(self, admin: Profile, import_id: str, *, reason: str = "",
                      actor_role: str = "") -> Optional[Dict[str, Any]]:
        try:
            updated = self._store.update_import(import_id, {
                "status": ImportStatus.REJECTED, "reason": reason,
                "reviewed_by": admin.user_id, "reviewed_at": _now(),
            })
        except NotFoundError:
            return None
        self._ghi_nhat_ky(
            "video_reject", target_id=import_id, actor_id=admin.user_id,
            actor_role=actor_role, note=reason)
        return updated.to_dict()

    def ignore_import(self, admin: Profile, import_id: str, *,
                      actor_role: str = "") -> Optional[Dict[str, Any]]:
        try:
            updated = self._store.update_import(import_id, {
                "status": ImportStatus.IGNORED,
                "reviewed_by": admin.user_id, "reviewed_at": _now(),
            })
        except NotFoundError:
            return None
        self._ghi_nhat_ky(
            "video_ignore", target_id=import_id, actor_id=admin.user_id,
            actor_role=actor_role)
        return updated.to_dict()

    # ==================================================== WebSub (Phase 6)
    #
    # Ba manh: (1) dang ky/huy dang ky/gia han qua hub PubSubHubbub, (2) hai
    # route CONG KHAI (`/api/youtube/websub`) doi thoai voi hub — xac minh
    # (GET) va thong bao (POST), (3) doi chieu dinh ky du phong. CHI nguon
    # kieu `youtube_channel` co feed WebSub — playlist/video don le KHONG
    # dang ky duoc.

    def _thuc_hien_dang_ky(self, source: TrustedSource) -> TrustedSource:
        """Goi hub THAT + ghi lai ket qua — dung CHUNG boi hanh dong dang ky
        cua quan tri (`subscribe_source`) VA gia han tu dong luc doi chieu
        dinh ky (`_gia_han_neu_sap_het_han`). Nem `WebSubError` (thong diep
        AN TOAN) neu hub tu choi — nguoi goi tu quyet dinh xu ly tiep."""
        if not self.websub_configured():
            raise WebSubConfigError(
                "Chưa cấu hình URL callback công khai "
                "(YOUTUBE_WEBSUB_CALLBACK_BASE_URL) — WebSub cần một backend "
                "công khai qua HTTPS, xem tài liệu Phase 6.")
        secret = new_websub_secret()
        callback_url = build_callback_url(self._websub_callback_base_url, source.source_id)
        try:
            self._websub().subscribe(
                channel_id=source.youtube_channel_id, callback_url=callback_url,
                secret=secret)
        except WebSubError as exc:
            self._store.record_websub_subscription(
                source.source_id, status=SubscriptionStatus.FAILED)
            self._store.record_websub_failure(source.source_id, error_message=str(exc))
            raise
        return self._store.record_websub_subscription(
            source.source_id, status=SubscriptionStatus.PENDING, secret=secret)

    def _thuc_hien_huy_dang_ky(self, source: TrustedSource) -> TrustedSource:
        callback_url = build_callback_url(self._websub_callback_base_url, source.source_id)
        try:
            self._websub().unsubscribe(
                channel_id=source.youtube_channel_id, callback_url=callback_url)
        except WebSubError as exc:
            self._store.record_websub_failure(source.source_id, error_message=str(exc))
            raise
        return self._store.record_websub_subscription(
            source.source_id, status=SubscriptionStatus.NONE, secret="")

    def subscribe_source(self, admin: Profile, source_id: str, *,
                         actor_role: str = "") -> Dict[str, Any]:
        """Dang ky (hoac gia han — WebSub cho phep dang ky lai truoc han de
        gia han) mot nguon kieu kenh voi hub PubSubHubbub — nut "Đăng ký"/
        "Đăng ký lại" tren trang chi tiet nguon."""
        source = self._store.get_source(source_id)
        if source.source_type is not TrustedSourceType.YOUTUBE_CHANNEL:
            raise TrustedSourceError(
                "Chỉ nguồn kiểu kênh YouTube mới đăng ký WebSub được.")
        try:
            updated = self._thuc_hien_dang_ky(source)
        except WebSubError as exc:
            self._ghi_nhat_ky(
                "websub_failure", target_id=source_id, actor_id=admin.user_id,
                actor_role=actor_role, note=str(exc))
            raise TrustedSourceError(str(exc)) from exc
        self._ghi_nhat_ky(
            "websub_subscribe", target_id=source_id, actor_id=admin.user_id,
            actor_role=actor_role)
        return updated.to_dict()

    def unsubscribe_source(self, admin: Profile, source_id: str, *,
                           actor_role: str = "") -> Dict[str, Any]:
        source = self._store.get_source(source_id)
        if source.subscription_status is SubscriptionStatus.NONE:
            return source.to_dict()  # khong co gi de huy — khong goi hub vo ich.
        try:
            updated = self._thuc_hien_huy_dang_ky(source)
        except WebSubError as exc:
            self._ghi_nhat_ky(
                "websub_failure", target_id=source_id, actor_id=admin.user_id,
                actor_role=actor_role, note=str(exc))
            raise TrustedSourceError(str(exc)) from exc
        self._ghi_nhat_ky(
            "websub_unsubscribe", target_id=source_id, actor_id=admin.user_id,
            actor_role=actor_role)
        return updated.to_dict()

    def _gia_han_neu_sap_het_han(self, source: TrustedSource) -> None:
        """Tu dong dang ky lai khi con duoi `RENEWAL_WINDOW` truoc han het —
        goi tu `run_reconciliation`, KHONG can quan tri bam gi ca. Loi o day
        CHI ghi lai, khong lam hong ca luot doi chieu."""
        if source.subscription_status not in (
                SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED):
            return
        if not source.subscription_expires_at:
            return
        try:
            han = datetime.fromisoformat(source.subscription_expires_at)
        except ValueError:
            return
        if han.tzinfo is None:
            han = han.replace(tzinfo=timezone.utc)
        if han - datetime.now(timezone.utc) > RENEWAL_WINDOW:
            return
        try:
            self._thuc_hien_dang_ky(source)
        except WebSubError as exc:
            self._ghi_nhat_ky(
                "websub_failure", target_id=source.source_id, actor_id="",
                actor_role="system", note=str(exc))
            return
        self._ghi_nhat_ky(
            "websub_renew", target_id=source.source_id, actor_id="",
            actor_role="system")

    def handle_websub_verification(
        self, *, source_id: str, mode: str, topic: str, challenge: str,
        lease_seconds: str,
    ) -> Optional[str]:
        """
        GET tu hub de xac minh mot yeu cau dang ky/huy dang ky (dac ta
        WebSub, xem `server/youtube_websub.py`). Tra chuoi `challenge` DE
        ROUTE ECHO NGUYEN VEN neu chap nhan, `None` neu tu choi (route tra
        404 — dac ta: "return HTTP 404 if subscriber doesn't agree").
        """
        try:
            source = self._store.get_source(source_id)
        except NotFoundError:
            return None
        if mode != "denied" and topic != build_topic_url(source.youtube_channel_id):
            return None  # topic khong khop nguon nay — tu choi, khong doan.

        if mode == "subscribe":
            het_han = ""
            try:
                giay = int(lease_seconds)
                het_han = (datetime.now(timezone.utc) + timedelta(seconds=max(0, giay))) \
                    .isoformat(timespec="seconds")
            except (TypeError, ValueError):
                pass
            self._store.record_websub_subscription(
                source_id, status=SubscriptionStatus.ACTIVE, expires_at=het_han)
        elif mode == "unsubscribe":
            self._store.record_websub_subscription(
                source_id, status=SubscriptionStatus.NONE, secret="")
        elif mode == "denied":
            self._store.record_websub_subscription(
                source_id, status=SubscriptionStatus.FAILED)
            self._store.record_websub_failure(
                source_id, error_message="Hub từ chối đăng ký (denied).")
            self._ghi_nhat_ky(
                "websub_failure", target_id=source_id, actor_id="",
                actor_role="system", note="Hub từ chối đăng ký.")
        else:
            return None
        return challenge

    def handle_websub_notification(
        self, *, source_id: str, body: bytes, signature_header: str,
    ) -> Optional[bool]:
        """
        POST tu hub bao video moi/cap nhat/da xoa. Tra `None` neu `source_id`
        KHONG TON TAI (route doi thanh 404, cung mau voi
        `handle_websub_verification` — day khong phai mot lan giao that,
        chi la mot URL callback ta chua tung dang ky). Tra `True`/`False`
        khi nguon TON TAI (route LUON tra 200 cho ca hai — dac ta WebSub: ma
        thanh cong CHI co nghia DA NHAN, khong phai da xu ly xong THANH
        CONG; `False` (chu ky sai/XML hong) chi anh huong nhat ky noi bo).
        """
        try:
            source = self._store.get_source(source_id)
        except NotFoundError:
            return None

        if not verify_signature(source.websub_secret, body, signature_header):
            self._store.record_websub_failure(
                source_id, error_message="Chữ ký X-Hub-Signature không hợp lệ.")
            self._ghi_nhat_ky(
                "websub_failure", target_id=source_id, actor_id="",
                actor_role="system", note="Chữ ký không hợp lệ.")
            return False

        self._store.record_websub_notification(source_id)
        self._ghi_nhat_ky(
            "websub_notification", target_id=source_id, actor_id="",
            actor_role="system")

        try:
            parsed = parse_notification(body)
        except WebSubParseError as exc:
            self._store.record_websub_failure(source_id, error_message=str(exc))
            return False

        if not source.enabled or not source.auto_discover:
            return True  # da nhan, nhung auto_discover tat — khong lam gi them.

        for entry in parsed.entries:
            if entry.channel_id != source.youtube_channel_id:
                continue  # thong bao khong dung kenh nguon nay — khong tin, bo qua.
            try:
                self._xu_ly_mot_video_websub(source, entry.video_id)
            except (YouTubeConfigError, YouTubeApiError) as exc:
                self._store.record_websub_failure(source_id, error_message=str(exc))

        for xoa in parsed.deleted:
            if xoa.channel_id and xoa.channel_id != source.youtube_channel_id:
                continue
            self._danh_dau_video_khong_con_truy_cap(xoa.video_id)

        return True

    def _xu_ly_mot_video_websub(self, source: TrustedSource, video_id: str) -> None:
        """
        Xu ly MOT video ID tu mot thong bao WebSub (hoac doi chieu dinh ky
        goi lai qua `scan_source`, xem `run_reconciliation`) — LUON tra cuu
        AUTHORITATIVE qua YouTube Data API TRUOC khi tin bat cu dieu gi tu
        thong bao (dac ta Phase 6, muc 5: "Do NOT trust notification
        metadata as final authority").

        Co the nem `YouTubeConfigError`/`YouTubeApiError` — nguoi goi
        (`handle_websub_notification`) bat rieng cho TUNG video, mot video
        loi khong duoc lam hong ca lo thong bao.
        """
        da_theo_doi = self._store.get_import_by_video_id(video_id)
        if da_theo_doi is not None:
            self._lam_moi_metadata_neu_can(da_theo_doi, video_id)
            return  # DA CO ban ghi — KHONG phan loai lai (idempotent, cung
                     # nguyen tac voi `scan_source`).

        video = self._youtube().get_video(video_id)
        if video is None:
            return  # khong (con) truy cap duoc — bo qua, doi chieu dinh ky
                     # se bat lai neu that su con ton tai sau nay.
        if video.channel_id != source.youtube_channel_id:
            return  # tra cuu THAT khong khop kenh nguon — khong tin thong
                     # bao, bo qua (phong thu sau, khac voi kiem tra tho o
                     # `handle_websub_notification`).

        da_la_tap = self._animation_store.episodes_by_external_ids([video_id])
        mappings = self._store.list_mappings(source.source_id)
        episodes_by_series = self._tap_da_co_theo_series(
            [m.animation_series_id for m in mappings])
        video_dict = {
            "video_id": video.video_id, "title": video.title,
            "channel_id": video.channel_id, "channel_title": video.channel_title,
            "thumbnail_url": video.thumbnail_url, "published_at": video.published_at,
            "duration_seconds": video.duration_seconds,
        }
        trang_thai, _matched = self._phan_loai_va_ghi_mot_video(
            source=source, mappings=mappings, episodes_by_series=episodes_by_series,
            video=video_dict, da_la_tap=da_la_tap)

        ban_ghi = self._store.get_import_by_video_id(video_id)
        muc_tieu = ban_ghi.import_id if ban_ghi else source.source_id
        self._ghi_nhat_ky(
            "auto_video_discover", target_id=muc_tieu, actor_id="",
            actor_role="system", note=f"video={video_id} trạng thái={trang_thai.value}")
        if trang_thai in (ImportStatus.AUTO_IMPORTED, ImportStatus.AUTO_PUBLISHED):
            self._ghi_nhat_ky(
                "auto_video_import", target_id=muc_tieu, actor_id="", actor_role="system")
            if trang_thai is ImportStatus.AUTO_PUBLISHED:
                self._ghi_nhat_ky(
                    "auto_video_publish", target_id=muc_tieu, actor_id="",
                    actor_role="system")

    def _lam_moi_metadata_neu_can(self, hien_tai: VideoImport, video_id: str) -> None:
        """Lam moi tieu de/anh dai dien tren MOT `VideoImport` DA CO — CHI
        khi con o trang thai "cho quyet dinh" (`NEW`/`PENDING`/`CONFLICT`),
        KHONG BAO GIO dong toi ban ghi DA la quyet dinh cuoi cung — mot
        thong bao WebSub bao "video vua duoc cap nhat" khong duoc phep doi
        gi tren mot tap DA nhap/tu choi/bo qua (dac ta Phase 6 muc 6)."""
        if hien_tai.status not in (
                ImportStatus.NEW, ImportStatus.PENDING, ImportStatus.CONFLICT):
            return
        try:
            video = self._youtube().get_video(video_id)
        except (YouTubeConfigError, YouTubeApiError):
            return  # lam moi la "tot thi lam", khong quan trong bang xu ly chinh.
        if video is None:
            return
        self._store.update_import(hien_tai.import_id, {
            "title": video.title, "thumbnail_url": video.thumbnail_url,
        })

    def _danh_dau_video_khong_con_truy_cap(self, video_id: str) -> None:
        """`at:deleted-entry` (WebSub bao video da bi go/rieng tu) — CHI doi
        mot ban ghi CON CHO QUYET DINH thanh `UNAVAILABLE`, giu nguyen mot
        ban ghi DA la quyet dinh cuoi cung."""
        ban_ghi = self._store.get_import_by_video_id(video_id)
        if ban_ghi is None:
            return
        if ban_ghi.status not in (
                ImportStatus.NEW, ImportStatus.PENDING, ImportStatus.CONFLICT):
            return
        self._store.update_import(ban_ghi.import_id, {
            "status": ImportStatus.UNAVAILABLE,
            "reason": "YouTube báo video này không còn truy cập được (đã gỡ/riêng tư).",
        })

    def run_reconciliation(self, *, source_id: str = "", actor_id: str = "",
                          actor_role: str = "") -> Dict[str, Any]:
        """
        Doi chieu dinh ky (Phase 6, du phong khi WebSub bo lo do gian doan
        webhook/dang ky het han/callback tam thoi khong truy cap duoc) —
        quet lai CAC nguon BAT + `auto_discover` voi so trang THAP
        (`RECONCILIATION_MAX_PAGES`), dung LAI `scan_source` (idempotent
        qua CUNG mot pipeline voi WebSub, khong phai duong rieng). Cung tien
        the gia han dang ky sap het han (xem `_gia_han_neu_sap_het_han`).

        `source_id` rong = chay cho MOI nguon phu hop (nut toan cuc/kich
        boi script ben ngoai, xem `scripts/run_websub_reconciliation.py`);
        truyen vao = CHI mot nguon (nut "Chạy đối chiếu ngay" tren trang chi
        tiet nguon). `actor_id` rong = he thong (kich hoat tu dong/script),
        khac voi hanh dong quan tri bam nut that.
        """
        if source_id:
            nguon = [self._store.get_source(source_id)]
        else:
            tat_ca, _total = self._store.find_sources(enabled=True, limit=None)
            nguon = [s for s in tat_ca if s.auto_discover]

        tong = {"sources_checked": 0, "sources_failed": 0, "videos_detected": 0}
        for s in nguon:
            tong["sources_checked"] += 1
            try:
                ket_qua = self.scan_source(
                    Profile(user_id=actor_id or "system", email=""), s.source_id,
                    max_pages=RECONCILIATION_MAX_PAGES, actor_role=actor_role)
                tong["videos_detected"] += ket_qua["detected"]
                self._store.record_reconciliation_sync(s.source_id)
            except (YouTubeConfigError, YouTubeApiError):
                tong["sources_failed"] += 1
            if self.websub_configured() and s.source_type is TrustedSourceType.YOUTUBE_CHANNEL:
                self._gia_han_neu_sap_het_han(s)

        self._ghi_nhat_ky(
            "reconciliation_run", target_id=source_id, actor_id=actor_id,
            actor_role=actor_role,
            note=(f"{tong['sources_checked']} nguồn, "
                 f"{tong['videos_detected']} video, {tong['sources_failed']} lỗi"))
        return tong

    # ==================================================== ha tang

    def _ghi_nhat_ky(self, action: str, *, target_id: str, actor_id: str,
                     actor_role: str = "", note: str = "") -> None:
        #: `websub_*`/`reconciliation_run` nham vao MOT `TrustedSource`
        #: (`target_id` la `source_id`) — CUNG nhom voi `trusted_source_*`/
        #: `youtube_mapping_*`, KHAC voi `auto_video_*` (nham vao MOT
        #: `VideoImport`, `target_id` la `import_id`).
        if action.startswith(("trusted_source", "youtube_mapping", "websub_")) \
                or action == "reconciliation_run":
            target_type = "trusted_source"
        else:
            target_type = "video_import"
        self._metadata_store.record_event(ModerationEvent(
            action=action, target_user_id="", target_type=target_type,
            target_id=target_id, actor_id=actor_id, actor_role=actor_role,
            note=note[:1000]))


def _now() -> str:
    return now_iso()
