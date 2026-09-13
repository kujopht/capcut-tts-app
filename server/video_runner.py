"""
Chay cac lan render DA XEP HANG, o mot luong nen.

Day la ban V1 CO Y don gian: mot luong cho moi lan render, ngay trong tien
trinh web. No du cho phat trien va cho mot vai nguoi dung, va KHONG du cho
production — xem `RenderProvider` o `video_renderer.py` cho duong di ra mot
may rieng.

Ba dieu duoc lam dung ngay tu V1, vi sua sau thi dat hon nhieu:

  * tep nguon duoc TAI VE mot thu muc tam roi moi render — FFmpeg khong doc
    thang tu kho doi tuong, va mot URL ky han se het han giua chung;
  * thu muc tam LUON duoc don, ke ca khi render hong;
  * moi ket qua deu di qua `VideoService.danh_dau`, nen may trang thai la
    NOI DUY NHAT quyet dinh mot du an dang o dau.
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

from server.video_domain import VideoRenderState
from server.video_render import NguonRender
from server.video_renderer import RenderProvider, thu_muc_tam


class VideoRenderRunner:
    def __init__(self, service, store, media_store, storage,
                 provider: RenderProvider) -> None:
        self._svc = service
        self._store = store
        self._media = media_store
        self._storage = storage
        self._provider = provider

    def chay_nen(self, owner_id: str, project_id: str) -> threading.Thread:
        t = threading.Thread(target=self._chay, args=(owner_id, project_id),
                             daemon=True,
                             name=f"video-render-{project_id}")
        t.start()
        return t

    # -- than ----------------------------------------------------------------

    def _tai_ve(self, thu_muc: Path, ten: str, object_key: str) -> str:
        """Tai mot doi tuong ve dia cuc bo.

        Dung `StorageAdapter.get()` — mot giao dien CHUNG cho ca ban cuc bo
        lan R2, va no tra ve BYTE nen khong phai lo chuyen URL ky han het
        han giua chung mot lan render dai.
        """
        dich = thu_muc / ten
        dich.write_bytes(self._storage.get(object_key))
        return str(dich)

    def _chay(self, owner_id: str, project_id: str) -> None:
        goc = Path(thu_muc_tam()) / project_id
        try:
            self._svc.danh_dau(owner_id, project_id, VideoRenderState.RENDERING)
        except Exception:                                      # noqa: BLE001
            # Du an bien mat hoac da doi trang thai — khong co gi de chay.
            return

        try:
            goc.mkdir(parents=True, exist_ok=True)
            du_an = self._svc._du_an.lay(owner_id, project_id)   # noqa: SLF001

            asset = self._media.get_asset(du_an.video_asset_id)
            nguon = NguonRender(
                video_path=self._tai_ve(goc, "nguon.mp4", asset.object_key),
                video_duration=asset.duration_seconds)

            if du_an.audio_track_id:
                t = self._store.track_by_id(du_an.audio_track_id)
                if t is not None:
                    nguon = NguonRender(
                        video_path=nguon.video_path,
                        audio_path=self._tai_ve(goc, "loi-doc.mp3", t.object_key),
                        video_duration=nguon.video_duration)

            if du_an.subtitle_asset_id:
                s = self._media.get_asset(du_an.subtitle_asset_id)
                nguon = NguonRender(
                    video_path=nguon.video_path,
                    audio_path=nguon.audio_path,
                    subtitle_path=self._tai_ve(goc, "phu-de.srt", s.object_key),
                    video_duration=nguon.video_duration)

            kq = self._provider.render(du_an, nguon, thu_muc_ra=str(goc))
            if not kq.thanh_cong:
                self._svc.danh_dau(owner_id, project_id,
                                   VideoRenderState.FAILED, loi=kq.loi)
                return

            khoa = f"video-studio/{owner_id}/{project_id}.mp4"
            with open(kq.duong_dan, "rb") as f:
                self._storage.put(khoa, f.read(), content_type="video/mp4")
            self._svc.danh_dau(owner_id, project_id, VideoRenderState.READY,
                               output_object_key=khoa)
        except Exception as exc:                                # noqa: BLE001
            # KHONG de ngoai le chet lang trong mot luong nen: du an se ket o
            # `RENDERING` vinh vien va nguoi dung nhin mot cai quay mai mai.
            try:
                self._svc.danh_dau(owner_id, project_id,
                                   VideoRenderState.FAILED,
                                   loi="Render thất bại — thử lại sau.")
            except Exception:                                   # noqa: BLE001
                pass
        finally:
            shutil.rmtree(goc, ignore_errors=True)
