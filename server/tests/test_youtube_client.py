"""
Test cho phan PHAN TICH CHUOI cua `server/youtube_client.py` — khong goi
mang. Xem `test_youtube_client_live.py` (BI BO QUA mac dinh) cho phan goi
YouTube Data API that.
"""

from __future__ import annotations

import unittest

from server.youtube_client import (
    YouTubeClient,
    YouTubeConfigError,
    _parse_iso8601_duration,
    parse_source_url,
)


class ParseSourceUrlTest(unittest.TestCase):
    def test_video_watch_url(self):
        ref = parse_source_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual((ref.kind, ref.value), ("video", "dQw4w9WgXcQ"))

    def test_video_youtu_be(self):
        ref = parse_source_url("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual((ref.kind, ref.value), ("video", "dQw4w9WgXcQ"))

    def test_video_uu_tien_hon_playlist_khi_ca_hai_co_mat(self):
        ref = parse_source_url(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabcdefghijklmno1234567890")
        self.assertEqual((ref.kind, ref.value), ("video", "dQw4w9WgXcQ"))

    def test_playlist_url(self):
        ref = parse_source_url(
            "https://www.youtube.com/playlist?list=PLabcdefghijklmno1234567890")
        self.assertEqual((ref.kind, ref.value), ("playlist", "PLabcdefghijklmno1234567890"))

    def test_playlist_id_tran(self):
        ref = parse_source_url("PLabcdefghijklmno1234567890")
        self.assertEqual((ref.kind, ref.value), ("playlist", "PLabcdefghijklmno1234567890"))

    def test_channel_id_url(self):
        cid = "UC" + "a" * 22
        ref = parse_source_url(f"https://www.youtube.com/channel/{cid}")
        self.assertEqual((ref.kind, ref.value), ("channel_id", cid))

    def test_channel_id_tran(self):
        cid = "UC" + "b" * 22
        ref = parse_source_url(cid)
        self.assertEqual((ref.kind, ref.value), ("channel_id", cid))

    def test_channel_handle_url(self):
        ref = parse_source_url("https://www.youtube.com/@somechannel")
        self.assertEqual((ref.kind, ref.value), ("channel_handle", "@somechannel"))

    def test_channel_username_url(self):
        ref = parse_source_url("https://www.youtube.com/user/legacyname")
        self.assertEqual((ref.kind, ref.value), ("channel_username", "legacyname"))

    def test_channel_custom_c_url_thu_nhu_handle(self):
        ref = parse_source_url("https://www.youtube.com/c/CustomName")
        self.assertEqual((ref.kind, ref.value), ("channel_handle", "@CustomName"))

    def test_chuoi_rong_tra_none(self):
        self.assertIsNone(parse_source_url(""))

    def test_url_khong_lien_quan_tra_none(self):
        self.assertIsNone(parse_source_url("https://vimeo.com/12345678"))

    def test_khong_co_schema_van_doc_duoc(self):
        ref = parse_source_url("youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual((ref.kind, ref.value), ("video", "dQw4w9WgXcQ"))


class ParseIso8601DurationTest(unittest.TestCase):
    def test_gio_phut_giay(self):
        self.assertEqual(_parse_iso8601_duration("PT1H2M3S"), 3723.0)

    def test_chi_phut_giay(self):
        self.assertEqual(_parse_iso8601_duration("PT23M15S"), 1395.0)

    def test_chi_giay(self):
        self.assertEqual(_parse_iso8601_duration("PT45S"), 45.0)

    def test_chuoi_sai_dang_tra_0(self):
        self.assertEqual(_parse_iso8601_duration("khong hop le"), 0.0)

    def test_chuoi_rong_tra_0(self):
        self.assertEqual(_parse_iso8601_duration(""), 0.0)


class YouTubeClientConfigTest(unittest.TestCase):
    def test_thieu_api_key_nem_loi_ro_rang(self):
        with self.assertRaises(YouTubeConfigError):
            YouTubeClient("")


if __name__ == "__main__":
    unittest.main()
