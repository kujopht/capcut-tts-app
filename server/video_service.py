"""
Video Composer V1 — tang dich vu.

TRACH NHIEM: quyen so huu, kiem tham so, vong doi render. Khong dung dong
lenh (xem `video_render`), khong chay tien trinh (xem `video_renderer`).

NGUYEN TAC QUYEN SO HUU o day, va no khac mot chut so voi phan con lai cua
he: quyen cua TUNG tham chieu duoc kiem MOI LAN DUNG, khong chi luc gan.
Ly do rat cu the — mot ban ghi co the doi chu, bi go chia se, hoac bi xoa
SAU khi da duoc gan vao du an. Kiem mot lan luc gan nghia la du an giu mai
mot cai quyen da het hieu luc.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from server.adapters import NotFoundError, PermissionDenied
from server.domain import MediaType, Profile, now_iso
from server.video_domain import (VideoProject, VideoRenderState, chuyen_duoc)
from server.video_project_store import MockVideoProjectStore
from server.video_validate import VideoValidationError, kiem_ban_va, kiem_tieu_de

#: Tran so du an moi nguoi. Khong phai mot gioi han thuong mai — chi la mot
#: cai chot chong mot vong lap hong tao ra mot trieu ban ghi.
TRAN_DU_AN = 200


class VideoService:
    def __init__(self, store, project_store: Optional[MockVideoProjectStore] = None,
                 media_store=None) -> None:
        #: Kho metadata chung (novels/chapters/tracks) — de tra `AudioTrack`.
        self._store = store
        self._du_an = project_store or MockVideoProjectStore()
        #: Kho `MediaAsset` (video/phu de). Tuy chon de bo kiem dung duoc
        #: mot ban gia don gian.
        self._media = media_store

    # -- tham chieu + quyen ---------------------------------------------------

    def _track_cua_toi(self, actor: Profile, track_id: str):
        """`AudioTrack` NEU no thuoc ve nguoi goi. Nguoc lai: nem."""
        if not track_id:
            return None
        track = self._store.track_by_id(track_id)
        # Vang mat va khong-phai-cua-ban tra CUNG mot loi: phan biet hai cai
        # do la mot kenh do xem id nao ton tai.
        if track is None or track.owner_id != actor.user_id:
            raise NotFoundError("Không tìm thấy bản audio này.")
        return track

    def _asset_cua_toi(self, actor: Profile, asset_id: str,
                       loai: MediaType):
        if not asset_id:
            return None
        if self._media is None:
            raise NotFoundError("Không tìm thấy tệp.")
        try:
            asset = self._media.get_asset(asset_id)
        except NotFoundError:
            asset = None
        # Vang mat va khong-phai-cua-ban tra CUNG mot loi, cung ly do voi
        # `_track_cua_toi`.
        if asset is None or asset.owner_id != actor.user_id:
            raise NotFoundError("Không tìm thấy tệp.")
        if asset.media_type is not loai:
            raise VideoValidationError(
                f"Tệp {asset_id} không phải {loai.value}.")
        return asset

    def _kiem_moi_tham_chieu(self, actor: Profile, du_an: VideoProject) -> None:
        """Moi tham chieu phai con hop le VA con thuoc ve nguoi nay."""
        self._asset_cua_toi(actor, du_an.video_asset_id, MediaType.VIDEO)
        self._track_cua_toi(actor, du_an.audio_track_id)
        self._asset_cua_toi(actor, du_an.subtitle_asset_id, MediaType.SUBTITLES)

    # -- CRUD -----------------------------------------------------------------

    def tao(self, actor: Profile, *, title: str,
            audio_track_id: str = "") -> VideoProject:
        if self._du_an.dem(actor.user_id) >= TRAN_DU_AN:
            raise VideoValidationError(
                f"Đã đạt trần {TRAN_DU_AN} dự án — xoá bớt dự án cũ.")
        du_an = VideoProject(owner_id=actor.user_id, title=kiem_tieu_de(title))
        if audio_track_id:
            # Gan ngay tu luc tao la duong di cua nut "Dùng trong Video".
            self._track_cua_toi(actor, audio_track_id)
            du_an.audio_track_id = audio_track_id
        return self._du_an.luu(du_an)

    def danh_sach(self, actor: Profile) -> List[VideoProject]:
        return self._du_an.liet_ke(actor.user_id)

    def lay(self, actor: Profile, project_id: str) -> VideoProject:
        return self._du_an.lay(actor.user_id, project_id)

    def sua(self, actor: Profile, project_id: str,
            ban_va: Dict[str, Any]) -> VideoProject:
        du_an = self._du_an.lay(actor.user_id, project_id)
        if du_an.render_state.dang_chay:
            raise VideoValidationError(
                "Bản render đang chạy — đợi xong rồi sửa tiếp.")

        dai = 0.0
        nguon_moi = ban_va.get("video_asset_id", du_an.video_asset_id)
        if nguon_moi and self._media is not None:
            try:
                dai = self._media.get_asset(nguon_moi).duration_seconds
            except NotFoundError:
                # Quyen/ton tai duoc kiem ky o `_kiem_moi_tham_chieu` ben
                # duoi; o day chi la lay do dai de kiem diem cat.
                dai = 0.0

        sach = kiem_ban_va(ban_va, dai_nguon=dai)
        for k, v in sach.items():
            setattr(du_an, k, v)
        # Kiem quyen SAU khi ap: ban va co the vua gan mot tham chieu moi.
        self._kiem_moi_tham_chieu(actor, du_an)

        # Sua xong thi ban render cu khong con mo ta du an nay nua.
        if du_an.render_state is VideoRenderState.READY:
            du_an.render_state = VideoRenderState.DRAFT
            du_an.output_object_key = ""
        du_an.render_error = ""
        du_an.updated_at = now_iso()
        return self._du_an.luu(du_an)

    def xoa(self, actor: Profile, project_id: str) -> bool:
        return self._du_an.xoa(actor.user_id, project_id)

    # -- render ---------------------------------------------------------------

    def xin_render(self, actor: Profile, project_id: str) -> VideoProject:
        """Dua du an vao hang doi render.

        KHONG chay render o day — day chi la mot lan doi trang thai. Ai chay
        va chay o dau la chuyen cua `video_renderer`, va o production no se
        la mot tien trinh khac han.
        """
        du_an = self._du_an.lay(actor.user_id, project_id)
        if not du_an.video_asset_id:
            raise VideoValidationError("Chọn một video trước đã.")
        self._kiem_moi_tham_chieu(actor, du_an)

        if not chuyen_duoc(du_an.render_state, VideoRenderState.QUEUED):
            raise VideoValidationError(
                "Bản render đang chạy — đợi xong rồi thử lại.")

        du_an.render_state = VideoRenderState.QUEUED
        du_an.render_error = ""
        du_an.updated_at = now_iso()
        return self._du_an.luu(du_an)

    def danh_dau(self, owner_id: str, project_id: str,
                 trang_thai: VideoRenderState, *,
                 output_object_key: str = "",
                 loi: str = "") -> VideoProject:
        """Bo chay render bao ket qua ve.

        Nhan `owner_id` chu khong nhan `Profile`: duong goi nay den tu mot bo
        chay nen, khong tu mot yeu cau HTTP co nguoi dung.
        """
        du_an = self._du_an.lay(owner_id, project_id)
        if not chuyen_duoc(du_an.render_state, trang_thai):
            raise VideoValidationError(
                f"Không chuyển được {du_an.render_state.value} -> "
                f"{trang_thai.value}.")
        du_an.render_state = trang_thai
        if trang_thai is VideoRenderState.READY:
            if not output_object_key:
                raise VideoValidationError("READY phải kèm tệp kết quả.")
            du_an.output_object_key = output_object_key
            du_an.render_error = ""
        if trang_thai is VideoRenderState.FAILED:
            du_an.render_error = loi or "Render thất bại."
        du_an.updated_at = now_iso()
        return self._du_an.luu(du_an)
