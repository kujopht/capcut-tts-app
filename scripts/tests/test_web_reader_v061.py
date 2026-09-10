# -*- coding: utf-8 -*-
"""V0.6.1 — WebReader (Router đọc web công khai, chỉ đọc, an toàn SSRF).

Khuyết tật nghiệm thu tay 2026-09-10: "https://github.com/.../releases/tag/v2.10.0
github này là gì?" -> worker `agy` headless cần `read_url`, bị tự chối quyền
(`tool_permission_denied`), việc FAILED ~17s. Router phải đọc HỘ.

Bài kiểm TẤT ĐỊNH, không phụ thuộc mạng: chặn SSRF là kiểm thuần; tải/chuyển
hướng/GitHub dùng monkeypatch để cố định. Một smoke mạng thật ở cuối, tự bỏ
qua khi offline.
"""
from __future__ import annotations

import json
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.control_center import web_reader as WR                    # noqa: E402
from scripts.control_center.web_reader import (KetQuaDoc, SSRFLoi,      # noqa: E402
                                               WebReader, doc_github,
                                               doc_web, kiem_url, rut_url)


class TestSSRFChan(unittest.TestCase):
    """Chặn mặc định — mỗi từ chối kèm LÝ DO cụ thể, không 'hỏng' chung."""

    def _deny(self, url: str, *tu_khoa: str):
        with self.assertRaises(SSRFLoi) as cm:
            kiem_url(url)
        ly = str(cm.exception)
        self.assertTrue(ly and len(ly) > 8, f"lý do rỗng cho {url}")
        for t in tu_khoa:
            self.assertIn(t, ly.lower(), f"{url}: lý do {ly!r} thiếu {t!r}")

    def test_scheme_khong_phai_http(self):
        self._deny("file:///etc/passwd", "scheme", "file")
        self._deny("ftp://host/x", "scheme", "ftp")
        self._deny("gopher://host/x", "scheme")
        self._deny("data:text/html,x", "scheme")
        self._deny("javascript:alert(1)", "scheme")

    def test_credential_nhung(self):
        self._deny("https://user:pass@example.com/", "đăng nhập")
        self._deny("http://admin:secret@10.0.0.1/", "đăng nhập")

    def test_loopback_va_noi_bo_theo_ten(self):
        self._deny("http://localhost/", "nội bộ")
        self._deny("http://foo.local/", "nội bộ")
        self._deny("http://metadata.google.internal/", "nội bộ")

    def test_ip_literal_noi_bo(self):
        self._deny("http://127.0.0.1/", "loopback")
        self._deny("http://[::1]/", "loopback")
        self._deny("http://10.0.0.5/", "riêng")
        self._deny("http://172.16.4.4/", "riêng")
        self._deny("http://192.168.1.1/", "riêng")
        self._deny("http://169.254.169.254/latest/", "metadata")

    def test_dns_tro_ve_ip_rieng_bi_chan(self):
        # Hostname cong khai nhung phan giai ve IP rieng (DNS rebinding tho).
        goc = socket.getaddrinfo

        def gia(host, port, *a, **k):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", port))]
        WR.socket.getaddrinfo = gia
        try:
            self._deny("http://evil.example.com/", "không công khai", "riêng")
        finally:
            WR.socket.getaddrinfo = goc

    def test_host_cong_khai_qua(self):
        goc = socket.getaddrinfo

        def gia(host, port, *a, **k):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
        WR.socket.getaddrinfo = gia
        try:
            host, scheme, port, https, ips = kiem_url("https://example.com/path")
            self.assertEqual((host, scheme, port, https), ("example.com", "https", 443, True))
            self.assertEqual(ips, ["93.184.216.34"])
        finally:
            WR.socket.getaddrinfo = goc


class TestTaiVaTrich(unittest.TestCase):
    """Tải/chuyển hướng/trích text — monkeypatch `_tai_mot` + DNS công khai."""

    def setUp(self):
        self._goc_dns = socket.getaddrinfo
        WR.socket.getaddrinfo = lambda h, p, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", p))]

    def tearDown(self):
        WR.socket.getaddrinfo = self._goc_dns

    def test_html_trich_tieu_de_va_text(self):
        html = (b"<html><head><title>Trang X</title><style>.a{}</style></head>"
                b"<body><script>bad()</script><h1>Xin chao</h1><p>Noi dung "
                b"chinh o day.</p></body></html>")
        WR._tai_mot = lambda *a, **k: (200, {"content-type": "text/html; charset=utf-8"}, html, "")
        kq = WebReader().read("https://example.com/")
        self.assertTrue(kq.ok)
        self.assertEqual(kq.trang_thai, 200)
        self.assertEqual(kq.tieu_de, "Trang X")
        self.assertIn("Xin chao", kq.van_ban)
        self.assertIn("Noi dung", kq.van_ban)
        self.assertNotIn("bad()", kq.van_ban)          # script bi bo
        self.assertEqual(len(kq.bam_noi_dung), 64)
        self.assertGreater(kq.so_byte, 0)

    def test_json_dep(self):
        body = b'{"b":2,"a":1}'
        WR._tai_mot = lambda *a, **k: (200, {"content-type": "application/json"}, body, "")
        kq = WebReader().read("https://example.com/api")
        self.assertTrue(kq.ok)
        self.assertIn('"a": 1', kq.van_ban)

    def test_chuyen_huong_giua_hai_url_cong_khai(self):
        calls = {"n": 0}

        def tai(host, ip, port, https, url, han, phuong_thuc="GET"):
            calls["n"] += 1
            if calls["n"] == 1:
                return (302, {"location": "https://example.com/final"}, b"", "https://example.com/final")
            return (200, {"content-type": "text/html"}, b"<title>F</title><p>done</p>", "")
        WR._tai_mot = tai
        kq = WebReader().read("https://example.com/start")
        self.assertTrue(kq.ok)
        self.assertEqual(kq.url_cuoi, "https://example.com/final")
        self.assertEqual(kq.chuyen_huong, ("https://example.com/final",))
        self.assertIn("done", kq.van_ban)

    def test_non_2xx_ly_do_ro(self):
        WR._tai_mot = lambda *a, **k: (404, {"content-type": "text/html"}, b"nope", "")
        kq = WebReader().read("https://example.com/missing")
        self.assertFalse(kq.ok)
        self.assertIn("404", kq.loi)

    def test_chuyen_huong_ve_ip_rieng_bi_chan(self):
        # Buoc dau cong khai, Location tro ve localhost -> vong sau chan.
        def tai(host, ip, port, https, url, han, phuong_thuc="GET"):
            return (302, {"location": "http://127.0.0.1/"}, b"", "http://127.0.0.1/")
        WR._tai_mot = tai
        kq = WebReader().read("https://example.com/redir")
        self.assertFalse(kq.ok)
        self.assertIn("từ chối an toàn", kq.loi)
        self.assertIn("loopback", kq.loi.lower())

    def test_provenance_day_du(self):
        WR._tai_mot = lambda *a, **k: (200, {"content-type": "text/plain"}, b"hi", "")
        kq = WebReader().read("https://example.com/p")
        d = kq.to_dict()
        for f in ("url_goc", "url_cuoi", "trang_thai", "content_type",
                  "bam_noi_dung", "so_byte", "ts"):
            self.assertIn(f, d)
        self.assertEqual(kq.url_goc, "https://example.com/p")
        self.assertTrue(kq.ts > 0)


class TestGitHub(unittest.TestCase):
    """Adapter GitHub công khai — đường dẫn -> đúng endpoint API, không token."""

    def setUp(self):
        self._goc = WR._gh_api

    def tearDown(self):
        WR._gh_api = self._goc

    def test_release_tag(self):
        goi = {}

        def gia(reader, duong):
            goi["duong"] = duong
            return {"name": "World Monitor v2.10.0", "tag_name": "v2.10.0",
                    "author": {"login": "bot"}, "published_at": "2026-09-08",
                    "prerelease": False, "body": "## Changes\n- x"}
        WR._gh_api = gia
        kq = doc_github(WebReader(), "https://github.com/koala73/worldmonitor/releases/tag/v2.10.0")
        self.assertIsNotNone(kq)
        self.assertEqual(kq.nguon, "github")
        self.assertIn("/repos/koala73/worldmonitor/releases/tags/v2.10.0", goi["duong"])
        self.assertIn("v2.10.0", kq.tieu_de)
        self.assertIn("Changes", kq.van_ban)
        self.assertEqual(len(kq.bam_noi_dung), 64)

    def test_issue(self):
        WR._gh_api = lambda r, d: {"number": 42, "state": "open", "title": "Bug",
                                   "user": {"login": "u"}, "created_at": "t", "body": "desc"}
        kq = doc_github(WebReader(), "https://github.com/o/r/issues/42")
        self.assertIn("#42", kq.van_ban)
        self.assertIn("Bug", kq.tieu_de)

    def test_repo_goc(self):
        def gia(r, d):
            if d.endswith("/readme"):
                import base64
                return {"content": base64.b64encode(b"# Readme noi dung").decode()}
            return {"full_name": "o/r", "description": "mo ta", "language": "Python",
                    "stargazers_count": 5, "forks_count": 1, "updated_at": "t", "topics": ["a"]}
        WR._gh_api = gia
        kq = doc_github(WebReader(), "https://github.com/o/r")
        self.assertIn("o/r", kq.tieu_de)
        self.assertIn("Readme noi dung", kq.van_ban)

    def test_khong_phai_github_tra_none(self):
        self.assertIsNone(doc_github(WebReader(), "https://example.com/x"))


class TestRutUrl(unittest.TestCase):

    def test_rut_url_tu_cau(self):
        self.assertEqual(
            rut_url("https://github.com/koala73/worldmonitor/releases/tag/v2.10.0 github này là gì v"),
            ["https://github.com/koala73/worldmonitor/releases/tag/v2.10.0"])
        self.assertEqual(rut_url("không có url ở đây"), [])
        self.assertEqual(len(rut_url("a http://x.com b https://y.com c http://z.com d", toi_da=2)), 2)

    def test_khoi_bang_chung_that_bai_noi_ro(self):
        kq = KetQuaDoc(url_goc="http://127.0.0.1/", ok=False,
                       loi="từ chối an toàn: địa chỉ loopback")
        b = kq.khoi_bang_chung()
        self.assertIn("THẤT BẠI", b)
        self.assertIn("read_url", b)


class TestMangThat(unittest.TestCase):
    """Một smoke mạng thật — tự bỏ qua khi offline (không làm CI đỏ)."""

    def test_github_release_that(self):
        try:
            socket.getaddrinfo("api.github.com", 443)
        except Exception:                                   # noqa: BLE001
            self.skipTest("offline")
        kq = doc_web("https://github.com/koala73/worldmonitor/releases/tag/v2.10.0")
        if not kq.ok:
            self.skipTest(f"mạng/API không sẵn: {kq.loi}")
        self.assertIn(kq.nguon, ("github", "web"))
        self.assertTrue(kq.van_ban)
        self.assertEqual(len(kq.bam_noi_dung), 64)


if __name__ == "__main__":
    unittest.main()
