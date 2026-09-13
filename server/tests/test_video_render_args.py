"""
Dong lenh FFmpeg — sinh ra dung, va KHONG BAO GIO chay qua shell.

Bo kiem nay khong can FFmpeg tren may: `dung_dong_lenh` la mot ham thuan,
va do chinh la ly do no duoc tach ra.
"""

from __future__ import annotations

import unittest

from server.video_domain import VideoProject, VideoRenderState, chuyen_duoc
from server.video_render import NguonRender, dung_dong_lenh, mo_ta_loi


def _du_an(**kw) -> VideoProject:
    goc = dict(owner_id="u1", title="Thử")
    goc.update(kw)
    return VideoProject(**goc)


class DongLenhTest(unittest.TestCase):
    def test_tra_ve_MANG_tham_so_chu_khong_phai_chuoi(self):
        """Mot chuoi lenh la mot lan tiem lenh dang cho xay ra."""
        argv = dung_dong_lenh(_du_an(), NguonRender(video_path="/v.mp4"),
                              dich="/ra.mp4")
        self.assertIsInstance(argv, list)
        self.assertTrue(all(isinstance(x, str) for x in argv))

    def test_ten_tep_DOC_HAI_chi_la_MOT_doi_so(self):
        """`;rm -rf` trong ten tep phai o nguyen trong mot phan tu.

        Voi `argv` thi no khong the thoat ra thanh mot lenh — day la bai kiem
        ghi lai chinh dieu do, de khong ai doi sang `shell=True` ma khong lam
        no do.
        """
        ac = "/tmp/a; rm -rf / #.mp4"
        argv = dung_dong_lenh(_du_an(), NguonRender(video_path=ac), dich="/ra.mp4")
        self.assertIn(ac, argv)
        # Khong mot phan tu nao duoc la mot dong lenh ghep.
        self.assertFalse(any(" && " in x or x.startswith("rm ") for x in argv))

    def test_cat_video_dat_TRUOC_dau_vao(self):
        """`-ss` sau `-i` bat FFmpeg giai ma tu dau roi vut bo — cham hon nhieu."""
        argv = dung_dong_lenh(_du_an(video_trim_start=12.5, video_trim_end=40.0),
                              NguonRender(video_path="/v.mp4"), dich="/ra.mp4")
        self.assertLess(argv.index("-ss"), argv.index("-i"))
        self.assertLess(argv.index("-to"), argv.index("-i"))
        self.assertEqual(argv[argv.index("-ss") + 1], "12.5000")
        self.assertEqual(argv[argv.index("-to") + 1], "40.0000")

    def test_khong_cat_thi_KHONG_co_ss_hay_to(self):
        argv = dung_dong_lenh(_du_an(), NguonRender(video_path="/v.mp4"),
                              dich="/ra.mp4")
        self.assertNotIn("-ss", argv)
        self.assertNotIn("-to", argv)

    def test_chi_tieng_goc_khi_chua_chon_loi_doc(self):
        argv = dung_dong_lenh(_du_an(video_volume=0.5),
                              NguonRender(video_path="/v.mp4"), dich="/ra.mp4")
        loc = argv[argv.index("-filter_complex") + 1]
        self.assertIn("[0:a]volume=0.5000[va]", loc)
        self.assertNotIn("amix", loc)

    def test_tron_hai_nguon_khi_co_loi_doc(self):
        argv = dung_dong_lenh(
            _du_an(audio_track_id="trk1", audio_volume=1.5, audio_offset=2.0),
            NguonRender(video_path="/v.mp4", audio_path="/a.mp3"), dich="/ra.mp4")
        loc = argv[argv.index("-filter_complex") + 1]
        self.assertIn("amix=inputs=2", loc)
        self.assertIn("volume=1.5000", loc)
        # `adelay` nhan MILI-giay, va can mot gia tri cho MOI kenh.
        self.assertIn("adelay=2000|2000", loc)

    def test_amix_KHONG_tu_chuan_hoa_am_luong(self):
        """`normalize=1` (mac dinh) ha am luong khi mot nguon het.

        Hau qua nghe duoc: loi doc to dan len o doan cuoi video. Ta da dat am
        luong tuong minh, nen FFmpeg khong duoc chinh them.
        """
        argv = dung_dong_lenh(_du_an(audio_track_id="t"),
                              NguonRender(video_path="/v.mp4", audio_path="/a.mp3"),
                              dich="/ra.mp4")
        loc = argv[argv.index("-filter_complex") + 1]
        self.assertIn("normalize=0", loc)
        self.assertIn("dropout_transition=0", loc)

    def test_lech_AM_cat_dau_loi_doc_chu_khong_day_video(self):
        """Day video di se lam lech ca HINH, khong chi tieng."""
        argv = dung_dong_lenh(_du_an(audio_track_id="t", audio_offset=-3.0),
                              NguonRender(video_path="/v.mp4", audio_path="/a.mp3"),
                              dich="/ra.mp4")
        loc = argv[argv.index("-filter_complex") + 1]
        self.assertIn("atrim=start=3.0000", loc)
        self.assertNotIn("adelay", loc)

    def test_audio_trim_end_cat_bot_CUOI_loi_doc(self):
        """`audio_trim_end` la mep PHAI cua clip tren trinh soan Media Studio."""
        argv = dung_dong_lenh(
            _du_an(audio_track_id="t", audio_trim_end=12.5),
            NguonRender(video_path="/v.mp4", audio_path="/a.mp3"),
            dich="/ra.mp4")
        loc = argv[argv.index("-filter_complex") + 1]
        self.assertIn("atrim=end=12.5000", loc)
        self.assertNotIn("adelay", loc)

    def test_audio_trim_end_KHONG_ap_dung_khi_bang_0(self):
        """`0` nghia la "dung het" — khong phai "dai 0 giay"."""
        argv = dung_dong_lenh(
            _du_an(audio_track_id="t", audio_trim_end=0.0),
            NguonRender(video_path="/v.mp4", audio_path="/a.mp3"),
            dich="/ra.mp4")
        loc = argv[argv.index("-filter_complex") + 1]
        self.assertNotIn("atrim", loc)

    def test_cat_dau_VA_cat_cuoi_gop_thanh_MOT_atrim(self):
        """Ca hai deu tinh tren truc thoi gian cua TEP NGUON — noi chuoi hai
        lan se lam lan hai tinh tren truc da bi dich boi lan dau."""
        argv = dung_dong_lenh(
            _du_an(audio_track_id="t", audio_offset=-3.0, audio_trim_end=20.0),
            NguonRender(video_path="/v.mp4", audio_path="/a.mp3"),
            dich="/ra.mp4")
        loc = argv[argv.index("-filter_complex") + 1]
        self.assertIn("atrim=start=3.0000:end=20.0000", loc)
        # Khong duoc co HAI khoi `atrim` rieng cho cung mot clip.
        self.assertEqual(loc.count("atrim"), 1)
        self.assertNotIn("adelay", loc)

    def test_cat_cuoi_VA_tre_dau_cung_co_thi_cat_TRUOC_roi_moi_tre(self):
        """`atrim` phai dung TRUOC `adelay` trong chuoi bo loc — tre truoc se
        day ca doan bi cat sang phai, lam diem cat sai vi tri."""
        argv = dung_dong_lenh(
            _du_an(audio_track_id="t", audio_offset=2.0, audio_trim_end=15.0),
            NguonRender(video_path="/v.mp4", audio_path="/a.mp3"),
            dich="/ra.mp4")
        loc = argv[argv.index("-filter_complex") + 1]
        self.assertIn("atrim=end=15.0000", loc)
        self.assertIn("adelay=2000|2000", loc)
        self.assertLess(loc.index("atrim"), loc.index("adelay"))

    def test_tat_tieng_goc_thi_chi_con_loi_doc(self):
        argv = dung_dong_lenh(_du_an(audio_track_id="t", mute_original_audio=True),
                              NguonRender(video_path="/v.mp4", audio_path="/a.mp3"),
                              dich="/ra.mp4")
        loc = argv[argv.index("-filter_complex") + 1]
        self.assertNotIn("[0:a]", loc)
        self.assertIn("[na]anull[aout]", loc)

    def test_tat_tieng_goc_va_KHONG_loi_doc_thi_tep_chi_hinh(self):
        """Noi ro bang `-an` thay vi de FFmpeg tu doan."""
        argv = dung_dong_lenh(_du_an(mute_original_audio=True),
                              NguonRender(video_path="/v.mp4"), dich="/ra.mp4")
        self.assertIn("-an", argv)
        self.assertNotIn("-filter_complex", argv)

    def test_phu_de_duoc_THOAT_dung_tren_duong_dan_Windows(self):
        """`C:\\x` co ca dau hai cham lan gach cheo — deu la ky tu dac biet
        cua ngon ngu bo loc."""
        argv = dung_dong_lenh(
            _du_an(), NguonRender(video_path="/v.mp4",
                                  subtitle_path=r"C:\Users\a b\phu de.srt"),
            dich="/ra.mp4")
        vf = argv[argv.index("-vf") + 1]
        self.assertTrue(vf.startswith("subtitles="))
        self.assertIn(r"C\:/Users/a b/phu de.srt", vf)

    def test_dinh_dang_ra_phat_duoc_tren_trinh_duyet_va_dien_thoai(self):
        argv = dung_dong_lenh(_du_an(), NguonRender(video_path="/v.mp4"),
                              dich="/ra.mp4")
        # `yuv420p`: thieu no thi mot so may phat chi hien khung den.
        self.assertEqual(argv[argv.index("-pix_fmt") + 1], "yuv420p")
        # `+faststart`: thieu no thi trinh duyet phai tai het tep moi phat.
        self.assertEqual(argv[argv.index("-movflags") + 1], "+faststart")
        self.assertEqual(argv[argv.index("-c:v") + 1], "libx264")
        self.assertEqual(argv[argv.index("-c:a") + 1], "aac")

    def test_dich_nam_o_CUOI(self):
        argv = dung_dong_lenh(_du_an(), NguonRender(video_path="/v.mp4"),
                              dich="/ra.mp4")
        self.assertEqual(argv[-1], "/ra.mp4")

    def test_khong_hoi_gi_tu_ban_phim(self):
        """`-nostdin`/`-y`: mot lan render treo cho nguoi go Y la mot job treo."""
        argv = dung_dong_lenh(_du_an(), NguonRender(video_path="/v.mp4"),
                              dich="/ra.mp4")
        self.assertIn("-nostdin", argv)
        self.assertIn("-y", argv)


class TrangThaiTest(unittest.TestCase):
    def test_duong_di_binh_thuong(self):
        self.assertTrue(chuyen_duoc(VideoRenderState.DRAFT, VideoRenderState.QUEUED))
        self.assertTrue(chuyen_duoc(VideoRenderState.QUEUED,
                                    VideoRenderState.RENDERING))
        self.assertTrue(chuyen_duoc(VideoRenderState.RENDERING,
                                    VideoRenderState.READY))

    def test_KHONG_nhay_thang_tu_DRAFT_sang_RENDERING(self):
        self.assertFalse(chuyen_duoc(VideoRenderState.DRAFT,
                                     VideoRenderState.RENDERING))

    def test_bam_Render_hai_lan_KHONG_chen_duoc_vao_ban_dang_chay(self):
        self.assertFalse(chuyen_duoc(VideoRenderState.RENDERING,
                                     VideoRenderState.QUEUED))

    def test_render_lai_duoc_sau_khi_xong_hoac_hong(self):
        self.assertTrue(chuyen_duoc(VideoRenderState.READY, VideoRenderState.QUEUED))
        self.assertTrue(chuyen_duoc(VideoRenderState.FAILED, VideoRenderState.QUEUED))


class MoTaLoiTest(unittest.TestCase):
    def test_KHONG_lo_stderr_tho_ra_giao_dien(self):
        """`stderr` chua duong dan tuyet doi tren may chu va ca dong lenh."""
        tho = ("ffmpeg version 6.0\n/srv/fanfic/secret/path/v.mp4: "
               "No such file or directory")
        ra = mo_ta_loi(1, tho)
        self.assertNotIn("/srv/fanfic", ra)
        self.assertNotIn("ffmpeg version", ra)
        self.assertIn("Không tìm thấy tệp nguồn", ra)

    def test_tep_hong_duoc_goi_dung_ten(self):
        self.assertIn("hỏng", mo_ta_loi(1, "moov atom not found"))

    def test_bi_giet_vi_qua_nang(self):
        self.assertIn("quá nặng", mo_ta_loi(137, "Killed"))


if __name__ == "__main__":
    unittest.main()
