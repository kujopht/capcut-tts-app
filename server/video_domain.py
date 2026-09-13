"""
Video Composer V1 — mo hinh mien.

MOT du an = MOT video + MOT loi doc + (tuy chon) MOT phu de. Khong hon.

Vi sao hep den the: cai gia cua mot trinh dung video nhieu track khong nam o
giao dien ma o RENDER — moi track them vao la mot nhanh moi trong bieu do
loc FFmpeg, va moi nhanh la mot cho co the sai im lang. V1 giai dung bai
toan nguoi dung dang co: ho vua tao mot ban doc bang TTS va muon ghep no vao
mot doan video.

KHONG luu nhi phan o day. `MediaAsset.object_key` / `AudioTrack.object_key`
tro toi kho doi tuong da co (`StorageBackend`), giong het moi tang khac cua
he — xem `server/image_library_store.py` cho cung nguyen tac.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict

from server.domain import new_id, now_iso


class VideoRenderState(str, Enum):
    """Vong doi mot lan render.

    `DRAFT` khac `QUEUED`: mot du an vua sua xong CHUA phai mot yeu cau
    render. Gop hai trang thai do lam mot nghia la moi lan bam Luu deu trong
    nhu mot lan xuat ban dang cho.
    """

    DRAFT = "draft"
    QUEUED = "queued"
    RENDERING = "rendering"
    READY = "ready"
    FAILED = "failed"

    @property
    def dang_chay(self) -> bool:
        return self in (VideoRenderState.QUEUED, VideoRenderState.RENDERING)

    @property
    def ket_thuc(self) -> bool:
        return self in (VideoRenderState.READY, VideoRenderState.FAILED)


#: Chuyen trang thai HOP LE. Mot bang tuong minh chu khong phai vai cau `if`
#: rai rac: cai sai hay gap la `READY -> RENDERING` (bam Render hai lan) va
#: `RENDERING -> QUEUED` (thu lai trong khi ban cu con chay).
CHUYEN_HOP_LE: Dict[VideoRenderState, frozenset] = {
    VideoRenderState.DRAFT: frozenset({VideoRenderState.QUEUED}),
    VideoRenderState.QUEUED: frozenset({
        VideoRenderState.RENDERING, VideoRenderState.FAILED}),
    VideoRenderState.RENDERING: frozenset({
        VideoRenderState.READY, VideoRenderState.FAILED}),
    # Da xong roi van render lai duoc — nhung phai di qua `QUEUED`, khong
    # nhay thang vao `RENDERING`.
    VideoRenderState.READY: frozenset({VideoRenderState.QUEUED}),
    VideoRenderState.FAILED: frozenset({VideoRenderState.QUEUED}),
}


def chuyen_duoc(tu: VideoRenderState, sang: VideoRenderState) -> bool:
    return sang in CHUYEN_HOP_LE.get(tu, frozenset())


#: Tran am luong. 2.0 chu khong phai vo han: khuech dai qua nguong nay thi
#: gan nhu chac chan vo tieng (clipping), va mot so 50 lot vao day se sinh ra
#: mot tep khong nghe duoc chu khong phai mot loi.
AM_LUONG_TOI_DA = 2.0
#: Do lech loi doc, tinh bang giay. Am = loi doc bat dau TRUOC video.
LECH_TOI_DA = 3600.0
#: Do dai toi da mot lan render V1 — mot chot an toan, khong phai mot con so
#: ky thuat. Render dai hon thi nen di duong hang doi rieng.
DAI_TOI_DA = 2 * 60 * 60.0


@dataclass
class VideoProject:
    """Mot du an Video Composer.

    Moi truong `*_asset_id` la MOT THAM CHIEU, khong phai du lieu nhung:
    `video_asset_id` -> `MediaAsset.asset_id`, `audio_track_id` ->
    `AudioTrack.track_id`, `subtitle_asset_id` -> `MediaAsset.asset_id`.
    Quyen so huu cua tung thu duoc kiem o tang dich vu MOI LAN dung, chu
    khong chi luc gan — nguoi ta co the go chia se mot tep sau khi da gan no
    vao du an.
    """

    owner_id: str
    title: str
    video_asset_id: str = ""
    audio_track_id: str = ""
    subtitle_asset_id: str = ""

    #: Cat video, tinh bang giay tu dau nguon. `video_trim_end == 0` nghia la
    #: "toi het" — khong phai "dai 0 giay".
    video_trim_start: float = 0.0
    video_trim_end: float = 0.0

    #: Loi doc bat dau o giay thu may cua video. Am = bat dau truoc.
    audio_offset: float = 0.0

    video_volume: float = 1.0
    audio_volume: float = 1.0
    mute_original_audio: bool = False

    render_state: VideoRenderState = VideoRenderState.DRAFT
    #: Khoa doi tuong cua ban MP4 da render — rong cho toi khi `READY`.
    output_object_key: str = ""
    #: Loi cua lan render gan nhat, dang van ban cho NGUOI DUNG doc. Khong
    #: bao gio chua duong dan tuyet doi hay dong lenh — xem `video_render`.
    render_error: str = ""

    project_id: str = field(default_factory=lambda: new_id("vpr"))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "owner_id": self.owner_id,
            "title": self.title,
            "video_asset_id": self.video_asset_id,
            "audio_track_id": self.audio_track_id,
            "subtitle_asset_id": self.subtitle_asset_id,
            "video_trim_start": self.video_trim_start,
            "video_trim_end": self.video_trim_end,
            "audio_offset": self.audio_offset,
            "video_volume": self.video_volume,
            "audio_volume": self.audio_volume,
            "mute_original_audio": self.mute_original_audio,
            "render_state": self.render_state.value,
            "render_error": self.render_error,
            #: KHONG tra `output_object_key` ra ngoai: khoa doi tuong la chi
            #: tiet kho luu tru. Giao dien xin URL co han qua duong rieng,
            #: giong het `audioLink` cua chuong.
            "has_output": bool(self.output_object_key),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
