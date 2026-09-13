"""
Studio Project — quyen so huu tren SAU kho, va tien do KHONG BIA.

Hai cau hoi bo kiem nay ton tai de tra loi:
  1. Nguoi A co gan duoc tai san cua nguoi B vao du an cua minh khong? (khong)
  2. Tien do co bao gio bia ra mot mau so khong? (khong)
"""

from __future__ import annotations

import unittest

from server.adapters import (MockMediaAssetStore, MockIdentityAdapter,
                             MockMetadataStore, NotFoundError)
from server.domain import (AudioTrack, Chapter, MediaAsset, MediaType, Novel,
                           Profile, StorageTier)
from server.image_domain import GenerationMode, SavedImage
from server.image_library_store import MockImageLibraryStore
from server.studio_project import StudioStage
from server.studio_project_store import MockStudioProjectStore
from server.studio_service import StudioProjectError, StudioService
from server.video_domain import VideoProject
from server.video_project_store import MockVideoProjectStore


def _nguoi(uid: str) -> Profile:
    return Profile(user_id=uid, email=f"{uid}@x.test", display_name=uid)


class Nen(unittest.TestCase):
    def setUp(self):
        self.store = MockMetadataStore()
        self.anh = MockImageLibraryStore()
        self.media = MockMediaAssetStore()
        self.video = MockVideoProjectStore()
        self.svc = StudioService(
            self.store, project_store=MockStudioProjectStore(),
            image_store=self.anh, media_store=self.media,
            video_project_store=self.video)
        self.an = _nguoi("an")
        self.binh = _nguoi("binh")

    def _truyen(self, owner: str, so_chuong: int = 0) -> Novel:
        n = self.store.create_novel(Novel(owner_id=owner, title="Truyện"))
        for i in range(so_chuong):
            self.store.create_chapter(Chapter(
                novel_id=n.novel_id, owner_id=owner,
                title=f"Chương {i + 1}", order_index=i + 1))
        return n

    def _audio(self, owner: str, ten: str = "ch1") -> AudioTrack:
        """MOT chuong THAT + audio cua no.

        Bo chon tai san di tu chuong sang track (`chapters_for_owner` ->
        `tracks_for_chapter`), giong het `/api/video/audio-library`. Mot track
        mo coi — khong chuong nao tro toi — la vo hinh voi ca hai duong, va do
        la hanh vi dung: no khong con thuoc ve tac pham nao.
        """
        n = self.store.create_novel(Novel(owner_id=owner, title=f"T-{ten}"))
        ch = self.store.create_chapter(Chapter(
            novel_id=n.novel_id, owner_id=owner, title=ten, order_index=1))
        return self.store.create_track(AudioTrack(
            chapter_id=ch.chapter_id, owner_id=owner, voice_id="v",
            object_key=f"audio/{owner}/{ch.chapter_id}.mp3",
            content_hash=f"h-{owner}-{ten}", duration_seconds=30.0))

    def _hinh(self, owner: str) -> SavedImage:
        return self.anh.luu(SavedImage(
            image_id=f"img-{owner}-{self.anh.dem(owner) if hasattr(self.anh, 'dem') else len(self.anh.liet_ke(owner))}",
            owner_user_id=owner, generation_id="g", prompt="một cảnh",
            negative_prompt="", model="m", mode=GenerationMode.QUICK_FREE,
            aspect_ratio="16:9", storage_key=f"img/{owner}.jpg"))

    def _phu_de(self, owner: str) -> MediaAsset:
        return self.media.create_asset(MediaAsset(
            owner_id=owner, media_type=MediaType.SUBTITLES,
            storage_tier=StorageTier.HOT, object_key=f"sub/{owner}.srt",
            content_hash="h", size_bytes=100))

    def _video(self, owner: str) -> VideoProject:
        return self.video.luu(VideoProject(owner_id=owner, title="Video"))


class QuyenSoHuuTest(Nen):
    def test_khong_gan_duoc_AUDIO_cua_nguoi_khac(self):
        cua_binh = self._audio("binh")
        d = self.svc.tao(self.an, title="Dự án")
        with self.assertRaises(NotFoundError):
            self.svc.gan(self.an, d.project_id, StudioStage.AUDIO,
                         cua_binh.track_id)

    def test_khong_gan_duoc_HINH_ANH_cua_nguoi_khac(self):
        cua_binh = self._hinh("binh")
        d = self.svc.tao(self.an, title="Dự án")
        with self.assertRaises(NotFoundError):
            self.svc.gan(self.an, d.project_id, StudioStage.HINH_ANH,
                         cua_binh.image_id)

    def test_khong_gan_duoc_PHU_DE_cua_nguoi_khac(self):
        cua_binh = self._phu_de("binh")
        d = self.svc.tao(self.an, title="Dự án")
        with self.assertRaises(NotFoundError):
            self.svc.gan(self.an, d.project_id, StudioStage.PHU_DE,
                         cua_binh.asset_id)

    def test_khong_gan_duoc_VIDEO_cua_nguoi_khac(self):
        cua_binh = self._video("binh")
        d = self.svc.tao(self.an, title="Dự án")
        with self.assertRaises(NotFoundError):
            self.svc.gan(self.an, d.project_id, StudioStage.VIDEO,
                         cua_binh.project_id)

    def test_khong_gan_duoc_TRUYEN_cua_nguoi_khac(self):
        cua_binh = self._truyen("binh")
        with self.assertRaises(NotFoundError):
            self.svc.tao(self.an, title="Cướp", novel_id=cua_binh.novel_id)

    def test_vang_mat_va_khong_phai_cua_ban_tra_CUNG_mot_loi(self):
        """Phan biet hai cai do la mot kenh do xem id nao ton tai."""
        cua_binh = self._audio("binh")
        d = self.svc.tao(self.an, title="Dự án")
        a = b = ""
        try:
            self.svc.gan(self.an, d.project_id, StudioStage.AUDIO,
                         cua_binh.track_id)
        except NotFoundError as e:
            a = str(e)
        try:
            self.svc.gan(self.an, d.project_id, StudioStage.AUDIO, "khong-co")
        except NotFoundError as e:
            b = str(e)
        self.assertEqual(a, b)

    def test_khong_doc_duoc_du_an_cua_nguoi_khac(self):
        cua_binh = self.svc.tao(self.binh, title="Của Bình")
        with self.assertRaises(NotFoundError):
            self.svc.lay(self.an, cua_binh.project_id)

    def test_danh_sach_chi_thay_du_an_cua_minh(self):
        self.svc.tao(self.an, title="A")
        self.svc.tao(self.binh, title="B")
        self.assertEqual([d.title for d in self.svc.danh_sach(self.an)], ["A"])

    def test_bo_chon_tai_san_KHONG_lo_tai_san_nguoi_khac(self):
        self._audio("binh", "ch-binh")
        self._audio("an", "ch-an")
        ds = self.svc.tai_san_cua_toi(self.an, StudioStage.AUDIO)
        self.assertEqual(len(ds), 1, "chỉ được thấy đúng bản audio của mình")
        self.assertEqual(ds[0]["label"], "ch-an")

    def test_MediaAsset_sai_loai_KHONG_gan_duoc_vao_o_phu_de(self):
        """Mot tep video gan vao o phu de se di thang toi FFmpeg duoi danh
        nghia mot tep .srt."""
        vid = self.media.create_asset(MediaAsset(
            owner_id="an", media_type=MediaType.VIDEO,
            storage_tier=StorageTier.HOT, object_key="v/a.mp4",
            content_hash="h"))
        d = self.svc.tao(self.an, title="Dự án")
        with self.assertRaises(StudioProjectError):
            self.svc.gan(self.an, d.project_id, StudioStage.PHU_DE, vid.asset_id)


class GanGoTest(Nen):
    def test_gan_hai_lan_la_vo_hai(self):
        t = self._audio("an")
        d = self.svc.tao(self.an, title="Dự án")
        self.svc.gan(self.an, d.project_id, StudioStage.AUDIO, t.track_id)
        d = self.svc.gan(self.an, d.project_id, StudioStage.AUDIO, t.track_id)
        self.assertEqual(d.audio_track_ids, [t.track_id])

    def test_go_tham_chieu_KHONG_xoa_tai_san(self):
        """Du an la mot CACH NHIN, khong phai mot cai thung."""
        t = self._audio("an")
        d = self.svc.tao(self.an, title="Dự án")
        self.svc.gan(self.an, d.project_id, StudioStage.AUDIO, t.track_id)
        self.svc.go(self.an, d.project_id, StudioStage.AUDIO, t.track_id)
        self.assertIsNotNone(self.store.track_by_id(t.track_id))

    def test_xoa_du_an_KHONG_xoa_tai_san(self):
        t = self._audio("an")
        d = self.svc.tao(self.an, title="Dự án")
        self.svc.gan(self.an, d.project_id, StudioStage.AUDIO, t.track_id)
        self.svc.xoa(self.an, d.project_id)
        self.assertIsNotNone(self.store.track_by_id(t.track_id))

    def test_mot_tai_san_dung_duoc_o_NHIEU_du_an(self):
        t = self._audio("an")
        a = self.svc.tao(self.an, title="A")
        b = self.svc.tao(self.an, title="B")
        self.svc.gan(self.an, a.project_id, StudioStage.AUDIO, t.track_id)
        self.svc.gan(self.an, b.project_id, StudioStage.AUDIO, t.track_id)
        self.assertIn(t.track_id,
                      self.svc.lay(self.an, b.project_id).audio_track_ids)


class TienDoTest(Nen):
    def test_KHONG_bia_mau_so_khi_chua_gan_truyen(self):
        """"8/10 chuong co audio" dem duoc; "80% hoan thanh" thi khong."""
        d = self.svc.tao(self.an, title="Dự án")
        self.svc.gan(self.an, d.project_id, StudioStage.AUDIO,
                     self._audio("an").track_id)
        td = {t.chang: t for t in self.svc.tien_do(self.an,
                                                   self.svc.lay(self.an, d.project_id))}
        self.assertEqual(td[StudioStage.AUDIO].so, 1)
        self.assertEqual(td[StudioStage.AUDIO].tong, 0)
        self.assertFalse(td[StudioStage.AUDIO].co_mau_so)
        self.assertIsNone(td[StudioStage.AUDIO].to_dict()["total"])

    def test_co_mau_so_THAT_khi_da_gan_truyen(self):
        n = self._truyen("an", so_chuong=10)
        d = self.svc.tao(self.an, title="Dự án", novel_id=n.novel_id)
        for i in range(3):
            self.svc.gan(self.an, d.project_id, StudioStage.AUDIO,
                         self._audio("an", f"ch{i}").track_id)
        td = {t.chang: t for t in self.svc.tien_do(self.an,
                                                   self.svc.lay(self.an, d.project_id))}
        self.assertEqual((td[StudioStage.AUDIO].so, td[StudioStage.AUDIO].tong),
                         (3, 10))
        self.assertFalse(td[StudioStage.AUDIO].xong)

    def test_xong_chi_dung_khi_CO_mau_so_va_da_day(self):
        n = self._truyen("an", so_chuong=2)
        d = self.svc.tao(self.an, title="Dự án", novel_id=n.novel_id)
        for i in range(2):
            self.svc.gan(self.an, d.project_id, StudioStage.AUDIO,
                         self._audio("an", f"ch{i}").track_id)
        td = {t.chang: t for t in self.svc.tien_do(self.an,
                                                   self.svc.lay(self.an, d.project_id))}
        self.assertTrue(td[StudioStage.AUDIO].xong)

    def test_noi_dung_la_0_hoac_1(self):
        d = self.svc.tao(self.an, title="Dự án")
        td = {t.chang: t for t in self.svc.tien_do(self.an, d)}
        self.assertEqual((td[StudioStage.NOI_DUNG].so,
                          td[StudioStage.NOI_DUNG].tong), (0, 1))
        n = self._truyen("an")
        d = self.svc.sua(self.an, d.project_id, novel_id=n.novel_id)
        td = {t.chang: t for t in self.svc.tien_do(self.an, d)}
        self.assertTrue(td[StudioStage.NOI_DUNG].xong)

    def test_du_sau_chang_luon_co_mat(self):
        d = self.svc.tao(self.an, title="Dự án")
        self.assertEqual([t.chang for t in self.svc.tien_do(self.an, d)],
                         list(StudioStage))


class ChonTruyenTest(Nen):
    """Nội dung phai CHON duoc, khong chi PATCH duoc.

    Truoc ban nay `novel_id` chi dat duoc bang `PATCH` va khong man hinh nao
    goi no, nen chang dau tien cua sau chang khong co duong nao o giao dien —
    va mau so cua Audio/Phu de (SO CHUONG cua truyen da gan) vi the khong bao
    gio hien ra duoc.
    """

    def test_bo_chon_liet_ke_truyen_cua_minh_ke_ca_ban_nhap(self):
        n = self._truyen("an", so_chuong=4)
        ds = self.svc.tai_san_cua_toi(self.an, StudioStage.NOI_DUNG)
        self.assertEqual([x["id"] for x in ds], [n.novel_id])
        self.assertEqual(ds[0]["detail"], "4 chương")

    def test_bo_chon_KHONG_lo_truyen_nguoi_khac(self):
        self._truyen("binh", so_chuong=2)
        self.assertEqual(self.svc.tai_san_cua_toi(self.an, StudioStage.NOI_DUNG), [])

    def test_truyen_da_gan_duoc_danh_dau_in_project(self):
        n = self._truyen("an")
        d = self.svc.tao(self.an, title="Dự án", novel_id=n.novel_id)
        ds = self.svc.tai_san_cua_toi(self.an, StudioStage.NOI_DUNG,
                                      project_id=d.project_id)
        self.assertTrue(ds[0]["in_project"])

    def test_chon_truyen_mo_ra_mau_so_cua_audio(self):
        """Day la ly do that su cua chang nay: mau so den tu truyen."""
        n = self._truyen("an", so_chuong=4)
        d = self.svc.tao(self.an, title="Dự án")
        self.svc.gan(self.an, d.project_id, StudioStage.AUDIO,
                     self._audio("an").track_id)
        truoc = {t.chang: t for t in self.svc.tien_do(self.an, d)}
        self.assertIsNone(truoc[StudioStage.AUDIO].to_dict()["total"])

        d = self.svc.sua(self.an, d.project_id, novel_id=n.novel_id)
        sau = {t.chang: t for t in self.svc.tien_do(self.an, d)}
        self.assertEqual(sau[StudioStage.AUDIO].to_dict()["total"], 4)


class TenTepTest(Nen):
    """Khoa do MAY CHU sinh, nen phan ten trong khoa luon la hex."""

    def _sub(self, khoa: str) -> MediaAsset:
        return self.media.create_asset(MediaAsset(
            owner_id="an", media_type=MediaType.SUBTITLES,
            storage_tier=StorageTier.HOT, object_key=khoa,
            content_hash="h", size_bytes=46))

    def test_ten_hex_KHONG_duoc_hien_nguyen(self):
        self._sub("studio/an/subtitles/e6e2772c92184aba92804e62f16ef041.srt")
        nhan = self.svc.tai_san_cua_toi(self.an, StudioStage.PHU_DE)[0]["label"]
        self.assertNotIn("e6e2772c", nhan)
        self.assertTrue(nhan.startswith("Phụ đề"), nhan)

    def test_ten_THAT_thi_giu_nguyen(self):
        self._sub("studio/an/subtitles/tap-3-vietsub.srt")
        self.assertEqual(
            self.svc.tai_san_cua_toi(self.an, StudioStage.PHU_DE)[0]["label"],
            "tap-3-vietsub.srt")

    def test_hai_tep_hex_van_phan_biet_duoc(self):
        """Mot chuoi hex khong phan biet duoc; mot cai nhan theo ngay thi co."""
        a = self._sub("studio/an/subtitles/" + "a" * 32 + ".srt")
        b = self._sub("studio/an/subtitles/" + "b" * 32 + ".srt")
        a.created_at, b.created_at = "2026-09-13T01:00:00", "2026-09-13T09:30:00"
        nhan = [x["label"]
                for x in self.svc.tai_san_cua_toi(self.an, StudioStage.PHU_DE)]
        self.assertEqual(len(set(nhan)), 2, nhan)


class NhanThamChieuTest(Nen):
    def test_nhan_doc_duoc_thay_cho_ma(self):
        t = self._audio("an", "Chương mở đầu")
        d = self.svc.tao(self.an, title="Dự án")
        d = self.svc.gan(self.an, d.project_id, StudioStage.AUDIO, t.track_id)
        nhan = self.svc.nhan_tham_chieu(self.an, d)["audio"]
        self.assertEqual(nhan[0]["id"], t.track_id)
        self.assertEqual(nhan[0]["label"], "Chương mở đầu")
        self.assertFalse(nhan[0]["missing"])

    def test_noi_dung_cung_co_nhan(self):
        n = self._truyen("an", so_chuong=3)
        d = self.svc.tao(self.an, title="Dự án", novel_id=n.novel_id)
        nhan = self.svc.nhan_tham_chieu(self.an, d)["noi_dung"]
        self.assertEqual([x["label"] for x in nhan], ["Truyện"])

    def test_tai_san_da_xoa_van_HIEN_RA_kem_co_missing(self):
        """Mot muc nguoi dung khong thay la mot muc nguoi dung khong go duoc."""
        t = self._audio("an")
        d = self.svc.tao(self.an, title="Dự án")
        d = self.svc.gan(self.an, d.project_id, StudioStage.AUDIO, t.track_id)
        self.store.delete_track(t.track_id)
        nhan = self.svc.nhan_tham_chieu(self.an, d)["audio"]
        self.assertEqual(len(nhan), 1)
        self.assertTrue(nhan[0]["missing"])
        self.assertEqual(nhan[0]["id"], t.track_id)

    def test_du_sau_chang_luon_co_khoa(self):
        d = self.svc.tao(self.an, title="Dự án")
        self.assertEqual(sorted(self.svc.nhan_tham_chieu(self.an, d)),
                         sorted(c.value for c in StudioStage))


class TaoSuaTest(Nen):
    def test_ten_rong_bi_tu_choi(self):
        with self.assertRaises(StudioProjectError):
            self.svc.tao(self.an, title="   ")

    def test_sua_ten_va_mo_ta(self):
        d = self.svc.tao(self.an, title="A")
        d = self.svc.sua(self.an, d.project_id, title="B", description="mô tả")
        self.assertEqual((d.title, d.description), ("B", "mô tả"))

    def test_khong_sua_duoc_du_an_cua_nguoi_khac(self):
        cua_binh = self.svc.tao(self.binh, title="Của Bình")
        with self.assertRaises(NotFoundError):
            self.svc.sua(self.an, cua_binh.project_id, title="Cướp")


if __name__ == "__main__":
    unittest.main()
