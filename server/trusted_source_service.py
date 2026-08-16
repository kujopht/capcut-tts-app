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

from typing import Any, Dict, List, Optional, Sequence

from server.adapters import NotFoundError
from server.animation_domain import AnimationEpisode, AnimationSource
from server.domain import ModerationEvent, Profile, PublishState, now_iso
from server.trusted_source_domain import (
    ImportStatus,
    SeriesMapping,
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

#: So trang toi da MOI LAN QUET (moi trang 50 video) — "bounded YouTube API
#: calls", xem yeu cau hieu nang Phase 5. Quet tiep bang cach goi lai voi
#: `page_token` tra ve.
MAX_SCAN_PAGES = 5
DEFAULT_SCAN_PAGES = 2


class TrustedSourceError(Exception):
    """Loi dau vao/nghiep vu (URL khong doc duoc, series khong ton tai,
    trang thai khong hop le...) — tang route doi thanh HTTP 400."""


class TrustedSourceService:
    def __init__(self, store: Any, animation_store: Any, metadata_store: Any,
                youtube_api_key: str = ""):
        self._store = store
        self._animation_store = animation_store
        self._metadata_store = metadata_store
        self._youtube_api_key = youtube_api_key

    def _youtube(self) -> YouTubeClient:
        """Nem `YouTubeConfigError` NGAY o day neu chua cau hinh — tang tren
        (route) doi thanh trang thai "chưa cấu hình" ro rang, KHONG bao gio
        am tham tra ket qua rong."""
        return YouTubeClient(self._youtube_api_key)

    def youtube_configured(self) -> bool:
        return bool(self._youtube_api_key)

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
        }

    def _ten_series_theo_id(self, series_ids: Sequence[str]) -> Dict[str, str]:
        ra: Dict[str, str] = {}
        for sid in dict.fromkeys(s for s in series_ids if s):
            try:
                ra[sid] = self._animation_store.get_series(sid).title
            except NotFoundError:
                ra[sid] = ""
        return ra

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

            if vid in da_la_tap:
                self._store.create_import_once(VideoImport(
                    trusted_source_id=source_id, youtube_video_id=vid,
                    title=v["title"], channel_id=v["channel_id"],
                    channel_title=v["channel_title"], thumbnail_url=v["thumbnail_url"],
                    published_at=v["published_at"], duration_seconds=v["duration_seconds"],
                    status=ImportStatus.DUPLICATE,
                    reason=f"Đã là tập {da_la_tap[vid].episode_id} trong series khác."))
                dem["duplicates"] += 1
                continue

            ket_qua = classify_video(
                title=v["title"], channel_id=v["channel_id"],
                trusted_source=source, mappings=mappings,
                episodes_by_series=episodes_by_series)

            trang_thai, ly_do, episode_id = self._quyet_dinh_trang_thai(
                source=source, mappings_by_id={m.mapping_id: m for m in mappings},
                ket_qua=ket_qua, video=v, episodes_by_series=episodes_by_series)

            if trang_thai in (ImportStatus.AUTO_IMPORTED, ImportStatus.AUTO_PUBLISHED):
                dem["auto_imported" if trang_thai is ImportStatus.AUTO_IMPORTED
                    else "auto_published"] += 1
            elif trang_thai is ImportStatus.PENDING:
                dem["pending"] += 1
            elif trang_thai is ImportStatus.IGNORED:
                dem["excluded"] += 1
            elif trang_thai is ImportStatus.CONFLICT:
                dem["conflicts"] += 1
            if ket_qua.series_id:
                dem["matched"] += 1

            self._store.create_import_once(VideoImport(
                trusted_source_id=source_id, youtube_video_id=vid,
                title=v["title"], channel_id=v["channel_id"],
                channel_title=v["channel_title"], thumbnail_url=v["thumbnail_url"],
                published_at=v["published_at"], duration_seconds=v["duration_seconds"],
                detected_mapping_id=ket_qua.mapping_id,
                detected_series_id=ket_qua.series_id,
                detected_episode_number=ket_qua.episode_number,
                confidence=ket_qua.confidence, signals=list(ket_qua.signals),
                status=trang_thai, reason=ly_do, created_episode_id=episode_id,
            ))

        self._store.record_scan_result(source_id, success=True)
        dem["next_page_token"] = next_token
        return dem

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
        items, total = self._store.find_imports(
            status=status, trusted_source_id=trusted_source_id,
            series_id=series_id, limit=limit, offset=offset)
        nguon_ids = [i.trusted_source_id for i in items if i.trusted_source_id]
        ten_series = self._ten_series_theo_id([i.detected_series_id for i in items])
        ten_nguon: Dict[str, str] = {}
        for sid in dict.fromkeys(nguon_ids):
            try:
                ten_nguon[sid] = self._store.get_source(sid).display_name
            except NotFoundError:
                ten_nguon[sid] = ""
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

    # ==================================================== ha tang

    def _ghi_nhat_ky(self, action: str, *, target_id: str, actor_id: str,
                     actor_role: str = "", note: str = "") -> None:
        self._metadata_store.record_event(ModerationEvent(
            action=action, target_user_id="",
            target_type="trusted_source" if action.startswith(
                ("trusted_source", "youtube_mapping")) else "video_import",
            target_id=target_id, actor_id=actor_id, actor_role=actor_role,
            note=note[:1000]))


def _now() -> str:
    return now_iso()
