"""Test cho `server/animation_domain.py` — chu yeu la `parse_youtube_id`."""

from __future__ import annotations

import unittest

from server.animation_domain import (
    AnimationEpisode,
    AnimationSeries,
    AnimationSource,
    parse_youtube_id,
)
from server.domain import PublishState


class ParseYoutubeIdTest(unittest.TestCase):
    ID = "dQw4w9WgXcQ"

    def test_id_tran(self):
        self.assertEqual(parse_youtube_id(self.ID), self.ID)

    def test_watch_url(self):
        self.assertEqual(
            parse_youtube_id(f"https://www.youtube.com/watch?v={self.ID}"), self.ID)

    def test_watch_url_kem_tham_so_playlist(self):
        self.assertEqual(
            parse_youtube_id(
                f"https://www.youtube.com/watch?v={self.ID}&list=PL123&index=2"),
            self.ID)

    def test_youtu_be(self):
        self.assertEqual(
            parse_youtube_id(f"https://youtu.be/{self.ID}"), self.ID)

    def test_youtu_be_kem_query(self):
        self.assertEqual(
            parse_youtube_id(f"https://youtu.be/{self.ID}?t=42"), self.ID)

    def test_embed_url(self):
        self.assertEqual(
            parse_youtube_id(f"https://www.youtube.com/embed/{self.ID}"), self.ID)

    def test_nocookie_embed_url(self):
        self.assertEqual(
            parse_youtube_id(
                f"https://www.youtube-nocookie.com/embed/{self.ID}"), self.ID)

    def test_shorts_url(self):
        self.assertEqual(
            parse_youtube_id(f"https://www.youtube.com/shorts/{self.ID}"), self.ID)

    def test_khong_co_schema(self):
        """Nguoi dung dan `youtube.com/watch?v=...` khong go `https://`."""
        self.assertEqual(
            parse_youtube_id(f"youtube.com/watch?v={self.ID}"), self.ID)

    def test_rong_tra_none(self):
        self.assertIsNone(parse_youtube_id(""))

    def test_url_khong_phai_youtube_tra_none(self):
        self.assertIsNone(parse_youtube_id("https://vimeo.com/12345678"))

    def test_id_sai_do_dai_tra_none(self):
        self.assertIsNone(parse_youtube_id("abc"))

    def test_watch_url_thieu_tham_so_v_tra_none(self):
        self.assertIsNone(parse_youtube_id("https://www.youtube.com/watch"))

    def test_khong_bia_id_tu_url_khong_khop(self):
        """URL hop le nhung KHONG khop dang nao da biet — tra None, khong
        doan mot phan chuoi bat ky lam ID."""
        self.assertIsNone(
            parse_youtube_id("https://www.youtube.com/channel/UC1234567890"))


class AnimationSeriesTest(unittest.TestCase):
    def test_mac_dinh(self):
        s = AnimationSeries(owner_id="u1", title="Truyen tranh dong")
        self.assertEqual(s.state, PublishState.DRAFT)
        self.assertEqual(s.related_novel_id, "")
        self.assertTrue(s.series_id.startswith("ani_"))

    def test_to_dict(self):
        s = AnimationSeries(owner_id="u1", title="T", tags=["hanh_dong"])
        d = s.to_dict()
        self.assertEqual(d["title"], "T")
        self.assertEqual(d["tags"], ["hanh_dong"])
        self.assertEqual(d["state"], "draft")


class AnimationEpisodeTest(unittest.TestCase):
    def test_mac_dinh(self):
        e = AnimationEpisode(series_id="ani_1", owner_id="u1", title="Tap 1",
                             external_id="dQw4w9WgXcQ")
        self.assertEqual(e.source, AnimationSource.YOUTUBE)
        self.assertEqual(e.order_index, 1)
        self.assertTrue(e.episode_id.startswith("anep_"))

    def test_to_dict(self):
        e = AnimationEpisode(series_id="ani_1", owner_id="u1", title="Tap 1",
                             external_id="dQw4w9WgXcQ", duration_seconds=1425.0)
        d = e.to_dict()
        self.assertEqual(d["source"], "youtube")
        self.assertEqual(d["external_id"], "dQw4w9WgXcQ")
        self.assertEqual(d["duration_seconds"], 1425.0)


if __name__ == "__main__":
    unittest.main()
