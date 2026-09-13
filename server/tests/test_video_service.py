"""
Video Composer — quyen so huu va vong doi render.

Hai cau hoi bo kiem nay ton tai de tra loi:
  1. Nguoi A co dung duoc tep cua nguoi B khong? (khong)
  2. Bam Render hai lan co chen duoc vao ban dang chay khong? (khong)
"""

from __future__ import annotations

import unittest

from server.adapters import (MockMediaAssetStore, MockMetadataStore,
                             NotFoundError)
from server.domain import (AudioTrack, MediaAsset, MediaType, Profile,
                           StorageTier)
from server.video_domain import VideoRenderState
from server.video_service import VideoService
from server.video_validate import VideoValidationError


def _nguoi(uid: str) -> Profile:
    return Profile(user_id=uid, email=f"{uid}@x.test", display_name=uid)


class Nen(unittest.TestCase):
    def setUp(self):
        self.store = MockMetadataStore()
        self.media = MockMediaAssetStore()
        self.svc = VideoService(self.store, media_store=self.media)
        self.an = _nguoi("an")
        self.binh = _nguoi("binh")

    def _video(self, owner: str, *, dai: float = 60.0) -> MediaAsset:
        return self.media.create_asset(MediaAsset(
            owner_id=owner, media_type=MediaType.VIDEO,
            storage_tier=StorageTier.HOT, object_key=f"video/{owner}.mp4",
            content_hash="h", duration_seconds=dai, size_bytes=1024))

    def _audio(self, owner: str) -> AudioTrack:
        return self.store.create_track(AudioTrack(
            chapter_id="ch1", owner_id=owner, voice_id="v",
            object_key=f"audio/{owner}.mp3", content_hash=f"h-{owner}",
            duration_seconds=30.0))


class QuyenSoHuuTest(Nen):
    def test_khong_dung_duoc_VIDEO_cua_nguoi_khac(self):
        cua_binh = self._video("binh")
        da = self.svc.tao(self.an, title="Dự án")
        with self.assertRaises(NotFoundError):
            self.svc.sua(self.an, da.project_id,
                         {"video_asset_id": cua_binh.asset_id})

    def test_khong_dung_duoc_AUDIO_cua_nguoi_khac(self):
        cua_binh = self._audio("binh")
        da = self.svc.tao(self.an, title="Dự án")
        with self.assertRaises(NotFoundError):
            self.svc.sua(self.an, da.project_id,
                         {"audio_track_id": cua_binh.track_id})

    def test_vang_mat_va_khong_phai_cua_ban_tra_CUNG_mot_loi(self):
        """Phan biet hai cai do la mot kenh do xem id nao ton tai."""
        cua_binh = self._audio("binh")
        da = self.svc.tao(self.an, title="Dự án")
        loi_ton_tai = loi_khong = ""
        try:
            self.svc.sua(self.an, da.project_id,
                         {"audio_track_id": cua_binh.track_id})
        except NotFoundError as e:
            loi_ton_tai = str(e)
        try:
            self.svc.sua(self.an, da.project_id,
                         {"audio_track_id": "trk_khong_co_that"})
        except NotFoundError as e:
            loi_khong = str(e)
        self.assertEqual(loi_ton_tai, loi_khong)

    def test_khong_doc_duoc_du_an_cua_nguoi_khac(self):
        cua_binh = self.svc.tao(self.binh, title="Của Bình")
        with self.assertRaises(NotFoundError):
            self.svc.lay(self.an, cua_binh.project_id)

    def test_khong_sua_duoc_du_an_cua_nguoi_khac(self):
        cua_binh = self.svc.tao(self.binh, title="Của Bình")
        with self.assertRaises(NotFoundError):
            self.svc.sua(self.an, cua_binh.project_id, {"title": "Cướp"})

    def test_khong_xoa_duoc_du_an_cua_nguoi_khac(self):
        cua_binh = self.svc.tao(self.binh, title="Của Bình")
        self.assertFalse(self.svc.xoa(self.an, cua_binh.project_id))
        self.assertIsNotNone(self.svc.lay(self.binh, cua_binh.project_id))

    def test_danh_sach_chi_thay_du_an_cua_minh(self):
        self.svc.tao(self.an, title="A")
        self.svc.tao(self.binh, title="B")
        self.assertEqual([d.title for d in self.svc.danh_sach(self.an)], ["A"])

    def test_quyen_duoc_kiem_LAI_luc_render_chu_khong_chi_luc_gan(self):
        """Mot ban ghi co the doi chu SAU khi da duoc gan vao du an."""
        video = self._video("an")
        da = self.svc.tao(self.an, title="Dự án")
        self.svc.sua(self.an, da.project_id, {"video_asset_id": video.asset_id})
        # Tep doi chu sau lung du an.
        video.owner_id = "binh"
        self.media.create_asset(video)
        with self.assertRaises(NotFoundError):
            self.svc.xin_render(self.an, da.project_id)

    def test_asset_SAI_LOAI_bi_tu_choi(self):
        anh = self.media.create_asset(MediaAsset(
            owner_id="an", media_type=MediaType.IMAGE,
            storage_tier=StorageTier.HOT, object_key="img/a.png",
            content_hash="h"))
        da = self.svc.tao(self.an, title="Dự án")
        with self.assertRaises(VideoValidationError):
            self.svc.sua(self.an, da.project_id, {"video_asset_id": anh.asset_id})


class VongDoiRenderTest(Nen):
    def _san_sang(self):
        video = self._video("an")
        audio = self._audio("an")
        da = self.svc.tao(self.an, title="Dự án", audio_track_id=audio.track_id)
        return self.svc.sua(self.an, da.project_id,
                            {"video_asset_id": video.asset_id})

    def test_khong_render_duoc_khi_chua_chon_video(self):
        da = self.svc.tao(self.an, title="Dự án")
        with self.assertRaises(VideoValidationError):
            self.svc.xin_render(self.an, da.project_id)

    def test_xin_render_dua_vao_hang_doi(self):
        da = self._san_sang()
        ra = self.svc.xin_render(self.an, da.project_id)
        self.assertIs(ra.render_state, VideoRenderState.QUEUED)

    def test_bam_hai_lan_KHONG_chen_vao_ban_dang_chay(self):
        da = self._san_sang()
        self.svc.xin_render(self.an, da.project_id)
        self.svc.danh_dau("an", da.project_id, VideoRenderState.RENDERING)
        with self.assertRaises(VideoValidationError):
            self.svc.xin_render(self.an, da.project_id)

    def test_render_lai_duoc_sau_khi_HONG(self):
        da = self._san_sang()
        self.svc.xin_render(self.an, da.project_id)
        self.svc.danh_dau("an", da.project_id, VideoRenderState.RENDERING)
        self.svc.danh_dau("an", da.project_id, VideoRenderState.FAILED,
                          loi="hỏng")
        ra = self.svc.xin_render(self.an, da.project_id)
        self.assertIs(ra.render_state, VideoRenderState.QUEUED)
        self.assertEqual(ra.render_error, "")

    def test_READY_phai_kem_tep_ket_qua(self):
        da = self._san_sang()
        self.svc.xin_render(self.an, da.project_id)
        self.svc.danh_dau("an", da.project_id, VideoRenderState.RENDERING)
        with self.assertRaises(VideoValidationError):
            self.svc.danh_dau("an", da.project_id, VideoRenderState.READY)

    def test_khong_sua_duoc_trong_luc_dang_render(self):
        da = self._san_sang()
        self.svc.xin_render(self.an, da.project_id)
        self.svc.danh_dau("an", da.project_id, VideoRenderState.RENDERING)
        with self.assertRaises(VideoValidationError):
            self.svc.sua(self.an, da.project_id, {"audio_volume": 0.5})

    def test_sua_sau_khi_READY_lam_ban_render_cu_het_hieu_luc(self):
        """Ban MP4 cu khong con mo ta du an nay nua — de no la `READY` thi
        nguoi dung tai ve mot thu khac cai ho vua sua."""
        da = self._san_sang()
        self.svc.xin_render(self.an, da.project_id)
        self.svc.danh_dau("an", da.project_id, VideoRenderState.RENDERING)
        self.svc.danh_dau("an", da.project_id, VideoRenderState.READY,
                          output_object_key="out/a.mp4")
        ra = self.svc.sua(self.an, da.project_id, {"audio_volume": 0.4})
        self.assertIs(ra.render_state, VideoRenderState.DRAFT)
        self.assertEqual(ra.output_object_key, "")

    def test_khoa_doi_tuong_KHONG_lo_ra_ngoai(self):
        """`output_object_key` la chi tiet kho luu tru, khong phai du lieu
        cua giao dien."""
        da = self._san_sang()
        self.svc.xin_render(self.an, da.project_id)
        self.svc.danh_dau("an", da.project_id, VideoRenderState.RENDERING)
        ra = self.svc.danh_dau("an", da.project_id, VideoRenderState.READY,
                               output_object_key="out/bi-mat.mp4")
        d = ra.to_dict()
        self.assertNotIn("output_object_key", d)
        self.assertTrue(d["has_output"])


class TaoVaSuaTest(Nen):
    def test_tao_kem_audio_la_duong_cua_nut_Dung_trong_Video(self):
        audio = self._audio("an")
        da = self.svc.tao(self.an, title="Từ audio", audio_track_id=audio.track_id)
        self.assertEqual(da.audio_track_id, audio.track_id)

    def test_tao_kem_audio_cua_NGUOI_KHAC_bi_tu_choi(self):
        audio = self._audio("binh")
        with self.assertRaises(NotFoundError):
            self.svc.tao(self.an, title="Cướp", audio_track_id=audio.track_id)

    def test_tieu_de_rong_bi_tu_choi(self):
        with self.assertRaises(VideoValidationError):
            self.svc.tao(self.an, title="   ")

    def test_diem_cat_ngoai_do_dai_video_bi_tu_choi(self):
        video = self._video("an", dai=30.0)
        da = self.svc.tao(self.an, title="D")
        self.svc.sua(self.an, da.project_id, {"video_asset_id": video.asset_id})
        with self.assertRaises(VideoValidationError):
            self.svc.sua(self.an, da.project_id, {"video_trim_start": 99.0})


if __name__ == "__main__":
    unittest.main()
