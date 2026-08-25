"""
Test cho phan PHAN TICH CHUOI cua `server/youtube_client.py` — khong goi
mang. Xem `test_youtube_client_live.py` (BI BO QUA mac dinh) cho phan goi
YouTube Data API that.
"""

from __future__ import annotations

import unittest
from unittest import mock

from server.youtube_client import (
    YouTubeApiError,
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


class _FakeResponse:
    """Gia lap `httpx.Response` — CHI ba thu `_goi()` doc: `status_code`,
    `.json()`, `.headers`."""

    def __init__(self, status_code: int, json_data=None, headers=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._json


class _FakeHttpClient:
    """Thay `httpx.Client` — tra ve LAN LUOT cac `_FakeResponse` da xep san,
    dem so lan `.get()` duoc goi (de kiem tra co retry hay khong)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def get(self, url, params=None):
        self.calls += 1
        if not self._responses:
            raise AssertionError("Goi HTTP nhieu hon so response da xep san.")
        return self._responses.pop(0)


def _quota_exceeded_body():
    return {"error": {"errors": [{"reason": "quotaExceeded"}]}}


class YouTubeClientRetryTest(unittest.TestCase):
    """`_goi()` phai thu lai voi backoff cho 429/5xx (loi TAM THOI), nhung
    that bai NGAY cho 4xx (loi VINH VIEN, dac biet `quotaExceeded`) — xem
    docstring `YouTubeClient.RETRY_STATUS_CODES`."""

    def setUp(self):
        # Khong cho THAT trong bo kiem thu — mock `time.sleep` thay vi giam
        # `RETRY_BASE_DELAY_SECONDS` (giu hang so mac dinh nguyen ven, dung
        # nhu san xuat), xem docstring hang so do.
        self._sleep_patch = mock.patch("server.youtube_client.time.sleep")
        self.mock_sleep = self._sleep_patch.start()
        self.addCleanup(self._sleep_patch.stop)

    def _client_voi(self, responses) -> tuple:
        client = YouTubeClient("fake-key")
        http = _FakeHttpClient(responses)
        client._client = http  # type: ignore[attr-defined]
        return client, http

    def test_429_roi_thanh_cong_khong_nem_loi(self):
        client, http = self._client_voi([
            _FakeResponse(429, headers={"Retry-After": "0"}),
            _FakeResponse(200, {"items": [{
                "id": "UCabc", "snippet": {"title": "Kenh"},
                "contentDetails": {"relatedPlaylists": {"uploads": "UUabc"}},
            }]}),
        ])
        kenh = client.get_channel("UCabc")
        self.assertIsNotNone(kenh)
        self.assertEqual(kenh.uploads_playlist_id, "UUabc")
        self.assertEqual(http.calls, 2, "phai thu lai dung MOT lan roi thanh cong")
        self.mock_sleep.assert_called_once()

    def test_5xx_lien_tuc_het_luot_thu_van_nem_loi_ro_rang(self):
        client, http = self._client_voi([
            _FakeResponse(500), _FakeResponse(502), _FakeResponse(503),
        ])
        with self.assertRaises(YouTubeApiError):
            client.get_channel("UCabc")
        self.assertEqual(http.calls, client.RETRY_MAX_ATTEMPTS,
                         "phai dung LAI o dung so lan thu toi da, khong lap vo han")

    def test_403_quota_exceeded_khong_thu_lai(self):
        client, http = self._client_voi([
            _FakeResponse(403, _quota_exceeded_body()),
        ])
        with self.assertRaises(YouTubeApiError) as ctx:
            client.get_channel("UCabc")
        self.assertEqual(ctx.exception.reason, "quotaExceeded")
        self.assertEqual(http.calls, 1, "loi han muc KHONG duoc thu lai")
        self.mock_sleep.assert_not_called()

    def test_400_thong_thuong_khong_thu_lai(self):
        """4xx KHAC quotaExceeded (vd sai tham so) cung la loi VINH VIEN —
        khong nam trong `RETRY_STATUS_CODES`, that bai ngay tu lan dau."""
        client, http = self._client_voi([_FakeResponse(400)])
        with self.assertRaises(YouTubeApiError):
            client.get_channel("UCabc")
        self.assertEqual(http.calls, 1)
        self.mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
