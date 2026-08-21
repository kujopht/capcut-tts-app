"""Kiem thu `server/youtube_websub.py` — THUAN, khong goi mang. Xem
docstring dau module do de biet vi sao moi thu o day phai coi du lieu vao
la THU DICH."""

import unittest

from server.youtube_websub import (
    DEFAULT_LEASE_SECONDS_REQUEST,
    MAX_NOTIFICATION_BYTES,
    WebSubParseError,
    build_callback_url,
    build_topic_url,
    compute_signature,
    new_secret,
    parse_notification,
    verify_signature,
)

_ATOM_VIDEO = """<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
             xmlns="http://www.w3.org/2005/Atom">
  <link rel="hub" href="https://pubsubhubbub.appspot.com"/>
  <link rel="self" href="https://www.youtube.com/xml/feeds/videos.xml?channel_id=UCuAXFkgsw1L7xaCfnd5JJOw"/>
  <title>YouTube video feed</title>
  <updated>2015-04-01T19:05:24.552394234+00:00</updated>
  <entry>
    <id>yt:video:jNQXAC9IVRw</id>
    <yt:videoId>jNQXAC9IVRw</yt:videoId>
    <yt:channelId>UCuAXFkgsw1L7xaCfnd5JJOw</yt:channelId>
    <title>Video title</title>
    <link rel="alternate" href="http://www.youtube.com/watch?v=jNQXAC9IVRw"/>
    <author>
     <name>Channel title</name>
     <uri>http://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw</uri>
    </author>
    <published>2015-03-06T21:40:57+00:00</published>
    <updated>2015-03-09T19:05:24.552394234+00:00</updated>
  </entry>
</feed>""".encode("utf-8")

_ATOM_DELETED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:at="http://purl.org/atompub/tombstones/1.0" xmlns="http://www.w3.org/2005/Atom">
  <at:deleted-entry ref="yt:video:jNQXAC9IVRw" when="2020-01-01T00:00:00+00:00">
    <link href="https://www.youtube.com/watch?v=jNQXAC9IVRw"/>
    <at:by>
      <name>chan</name>
      <uri>https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw</uri>
    </at:by>
  </at:deleted-entry>
</feed>""".encode("utf-8")

_BILLION_LAUGHS = (
    b'<?xml version="1.0"?>'
    b'<!DOCTYPE lolz [<!ENTITY lol "lol">'
    b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
    b"<feed>&lol2;</feed>"
)

_XXE = (
    b'<?xml version="1.0"?>'
    b'<!DOCTYPE feed [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
    b"<feed>&xxe;</feed>"
)


class BuildersTest(unittest.TestCase):
    def test_topic_url_dung_dinh_dang_chinh_thuc(self):
        self.assertEqual(
            build_topic_url("UCuAXFkgsw1L7xaCfnd5JJOw"),
            "https://www.youtube.com/feeds/videos.xml?channel_id=UCuAXFkgsw1L7xaCfnd5JJOw")

    def test_callback_url_kem_source_id_rieng(self):
        url = build_callback_url("https://api.fanfic.world/", "tsrc_abc")
        self.assertEqual(url, "https://api.fanfic.world/api/youtube/websub?source_id=tsrc_abc")

    def test_secret_moi_lan_khac_nhau(self):
        self.assertNotEqual(new_secret(), new_secret())
        self.assertGreaterEqual(len(new_secret()), 32)


class ParseNotificationTest(unittest.TestCase):
    def test_video_that_doc_dung(self):
        ket_qua = parse_notification(_ATOM_VIDEO)
        self.assertEqual(len(ket_qua.entries), 1)
        entry = ket_qua.entries[0]
        self.assertEqual(entry.video_id, "jNQXAC9IVRw")
        self.assertEqual(entry.channel_id, "UCuAXFkgsw1L7xaCfnd5JJOw")
        self.assertEqual(entry.title, "Video title")
        self.assertTrue(entry.published_at)
        self.assertEqual(len(ket_qua.deleted), 0)

    def test_deleted_entry_doc_dung(self):
        ket_qua = parse_notification(_ATOM_DELETED)
        self.assertEqual(len(ket_qua.entries), 0)
        self.assertEqual(len(ket_qua.deleted), 1)
        xoa = ket_qua.deleted[0]
        self.assertEqual(xoa.video_id, "jNQXAC9IVRw")
        self.assertEqual(xoa.channel_id, "UCuAXFkgsw1L7xaCfnd5JJOw")

    def test_xml_khong_hop_le_nem_loi(self):
        with self.assertRaises(WebSubParseError):
            parse_notification(b"<feed><entry></feed>")  # thieu dong the

    def test_khong_phai_xml_nem_loi(self):
        with self.assertRaises(WebSubParseError):
            parse_notification(b"khong phai xml")

    def test_billion_laughs_bi_chan(self):
        with self.assertRaises(WebSubParseError):
            parse_notification(_BILLION_LAUGHS)

    def test_xxe_bi_chan(self):
        with self.assertRaises(WebSubParseError):
            parse_notification(_XXE)

    def test_than_qua_lon_bi_chan_TRUOC_khi_phan_tich(self):
        qua_lon = b"x" * (MAX_NOTIFICATION_BYTES + 1)
        with self.assertRaises(WebSubParseError):
            parse_notification(qua_lon)

    def test_thieu_yt_videoId_hoac_channelId_bi_bo_qua_khong_doan(self):
        xml = b"""<feed xmlns="http://www.w3.org/2005/Atom"
                        xmlns:yt="http://www.youtube.com/xml/schemas/2015">
          <entry><title>khong co videoId</title></entry>
        </feed>"""
        ket_qua = parse_notification(xml)
        self.assertEqual(ket_qua.entries, [])

    def test_channel_id_sai_dinh_dang_bi_bo_qua(self):
        xml = b"""<feed xmlns="http://www.w3.org/2005/Atom"
                        xmlns:yt="http://www.youtube.com/xml/schemas/2015">
          <entry>
            <yt:videoId>jNQXAC9IVRw</yt:videoId>
            <yt:channelId>khong-phai-id-kenh</yt:channelId>
          </entry>
        </feed>"""
        ket_qua = parse_notification(xml)
        self.assertEqual(ket_qua.entries, [])

    def test_rong_khong_co_entry_nao_van_hop_le(self):
        xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><title>x</title></feed>'
        ket_qua = parse_notification(xml)
        self.assertEqual(ket_qua.entries, [])
        self.assertEqual(ket_qua.deleted, [])


class SignatureTest(unittest.TestCase):
    def test_ky_va_xac_minh_khop(self):
        chu_ky = compute_signature("bi-mat", _ATOM_VIDEO, algo="sha256")
        self.assertTrue(chu_ky.startswith("sha256="))
        self.assertTrue(verify_signature("bi-mat", _ATOM_VIDEO, chu_ky))

    def test_sha1_mac_dinh_cua_dac_ta_cu_van_chay(self):
        chu_ky = compute_signature("bi-mat", _ATOM_VIDEO)
        self.assertTrue(chu_ky.startswith("sha1="))
        self.assertTrue(verify_signature("bi-mat", _ATOM_VIDEO, chu_ky))

    def test_sai_bi_mat_tra_false(self):
        chu_ky = compute_signature("bi-mat", _ATOM_VIDEO)
        self.assertFalse(verify_signature("sai-roi", _ATOM_VIDEO, chu_ky))

    def test_than_bi_sua_tra_false(self):
        chu_ky = compute_signature("bi-mat", _ATOM_VIDEO)
        self.assertFalse(verify_signature("bi-mat", _ATOM_VIDEO + b"x", chu_ky))

    def test_thieu_header_tra_false_khong_nem_loi(self):
        self.assertFalse(verify_signature("bi-mat", _ATOM_VIDEO, ""))

    def test_thuat_toan_la_tra_false(self):
        self.assertFalse(verify_signature("bi-mat", _ATOM_VIDEO, "md5=abcd1234"))

    def test_dinh_dang_sai_khong_co_dau_bang_tra_false(self):
        self.assertFalse(verify_signature("bi-mat", _ATOM_VIDEO, "sha256"))

    def test_thieu_bi_mat_tra_false(self):
        chu_ky = compute_signature("bi-mat", _ATOM_VIDEO)
        self.assertFalse(verify_signature("", _ATOM_VIDEO, chu_ky))


if __name__ == "__main__":
    unittest.main()
