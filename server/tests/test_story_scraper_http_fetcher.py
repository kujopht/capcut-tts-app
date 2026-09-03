"""
`HttpFetcher` — ba hanh vi "cong dan tot" khi quet trang cua nguoi khac:
gioi han toc do moi host, thu lai co backoff cho loi TAM THOI, va kiem tra
`robots.txt` truoc khi tai. Ca ba deu KHONG duoc kiem qua `FixtureFetcher`
(no khong goi mang that), nen can bo test rieng o day, dung
`httpx.MockTransport` (cung mau voi `test_image_provider_registry.py`).

`sleep_fn`/`clock_fn` deu duoc tiem gia trong moi test — KHONG test nao o
day thuc su ngu, dam bao bo test chay nhanh du dang kiem hanh vi backoff/
gioi han toc do dua tren SO LAN goi va gia tri truyen vao, khong dua tren
thoi gian tuong that troi qua.
"""
import unittest

import httpx

from server.scraper.http_fetcher import (
    DEFAULT_BACKOFF_BASE_SECONDS,
    FetchError,
    HttpFetcher,
    RobotsDisallowedError,
)

_BASE = "https://vd-truyen.example"


class _DongHoGia:
    """Dong ho gia: `now()` tang 0 moi lan goi tru khi `sleep()` duoc goi —
    mo phong dung "thoi gian troi qua ĐUNG BANG so giay da ngu", khong hon
    khong kem, de test gioi han toc do doc duoc chinh xac."""

    def __init__(self):
        self.t = 0.0
        self.slept = []

    def now(self) -> float:
        return self.t

    def sleep(self, giay: float) -> None:
        self.slept.append(giay)
        self.t += giay


def _tao_fetcher(handler, **kw):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    dh = _DongHoGia()
    kw.setdefault("sleep_fn", dh.sleep)
    kw.setdefault("clock_fn", dh.now)
    kw.setdefault("respect_robots", False)
    fetcher = HttpFetcher(client=client, **kw)
    return fetcher, dh


class RetryBackoffTest(unittest.TestCase):
    def test_loi_mang_tam_thoi_duoc_thu_lai_va_cuoi_cung_thanh_cong(self):
        so_lan_goi = []

        def handler(request: httpx.Request) -> httpx.Response:
            so_lan_goi.append(1)
            if len(so_lan_goi) < 3:
                raise httpx.ConnectTimeout("timeout", request=request)
            return httpx.Response(200, text="noi dung that")

        fetcher, dh = _tao_fetcher(handler, max_retries=2, min_delay_seconds=0)
        ket_qua = fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertEqual(ket_qua.text, "noi dung that")
        self.assertEqual(len(so_lan_goi), 3, "phai goi du 3 lan (1 goc + 2 thu lai)")

    def test_backoff_MU_khong_phai_tuyen_tinh(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timeout", request=request)

        fetcher, dh = _tao_fetcher(handler, max_retries=2, min_delay_seconds=0,
                                    backoff_base_seconds=1.0)
        with self.assertRaises(FetchError):
            fetcher.fetch(f"{_BASE}/chuong-1")
        # lan 1: doi base*2^0=1s, lan 2: doi base*2^1=2s — MU, khong phai 1,1.
        self.assertEqual(dh.slept, [1.0, 2.0])

    def test_qua_so_lan_thu_lai_thi_nem_loi_that(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timeout", request=request)

        fetcher, dh = _tao_fetcher(handler, max_retries=1, min_delay_seconds=0)
        with self.assertRaises(FetchError):
            fetcher.fetch(f"{_BASE}/chuong-1")

    def test_loi_4xx_KHONG_duoc_thu_lai(self):
        """404 se KHONG tu khac di neu goi lai y het — thu lai chi lam
        cham va lam phien server nguon vo ich."""
        so_lan_goi = []

        def handler(request: httpx.Request) -> httpx.Response:
            so_lan_goi.append(1)
            return httpx.Response(404, text="not found")

        fetcher, dh = _tao_fetcher(handler, max_retries=2, min_delay_seconds=0)
        with self.assertRaises(FetchError):
            fetcher.fetch(f"{_BASE}/khong-ton-tai")
        self.assertEqual(len(so_lan_goi), 1, "4xx khong duoc thu lai")

    def test_loi_5xx_duoc_thu_lai_nhu_loi_mang(self):
        so_lan_goi = []

        def handler(request: httpx.Request) -> httpx.Response:
            so_lan_goi.append(1)
            if len(so_lan_goi) < 2:
                return httpx.Response(503, text="tam thoi qua tai")
            return httpx.Response(200, text="ok")

        fetcher, dh = _tao_fetcher(handler, max_retries=1, min_delay_seconds=0)
        ket_qua = fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertEqual(ket_qua.text, "ok")
        self.assertEqual(len(so_lan_goi), 2)


class RateLimitTest(unittest.TestCase):
    def test_hai_lan_goi_lien_tiep_cung_host_bi_gian_cach(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="ok")

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=2.0, max_retries=0)
        fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertEqual(dh.slept, [], "lan goi DAU tien khong can cho")
        fetcher.fetch(f"{_BASE}/chuong-2")
        self.assertEqual(dh.slept, [2.0], "lan goi THU HAI phai cho du khoang cach toi thieu")

    def test_khac_host_thi_KHONG_bi_gian_cach_chung(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="ok")

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=2.0, max_retries=0)
        fetcher.fetch(f"{_BASE}/chuong-1")
        fetcher.fetch("https://mot-trang-khac.example/chuong-1")
        self.assertEqual(dh.slept, [], "gioi han toc do la MOI HOST, khong dung chung")

    def test_da_du_thoi_gian_thi_khong_can_cho_them(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="ok")

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=1.0, max_retries=0)
        fetcher.fetch(f"{_BASE}/chuong-1")
        dh.t += 5.0  # gia lap 5s da troi qua giua hai lan goi (vd xu ly HTML lau)
        fetcher.fetch(f"{_BASE}/chuong-2")
        self.assertEqual(dh.slept, [], "da qua khoang cach toi thieu roi, khong can ngu them")

    def test_gioi_han_toc_do_tat_duoc_khi_min_delay_bang_0(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="ok")

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=0, max_retries=0)
        fetcher.fetch(f"{_BASE}/chuong-1")
        fetcher.fetch(f"{_BASE}/chuong-2")
        self.assertEqual(dh.slept, [])


class RobotsTest(unittest.TestCase):
    def test_duong_dan_bi_robots_txt_tu_choi_nem_RobotsDisallowedError(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
            return httpx.Response(200, text="khong duoc doc toi day")

        fetcher, dh = _tao_fetcher(handler, respect_robots=True, min_delay_seconds=0, max_retries=0)
        with self.assertRaises(RobotsDisallowedError):
            fetcher.fetch(f"{_BASE}/private/chuong-1")

    def test_duong_dan_duoc_phep_van_tai_binh_thuong(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
            return httpx.Response(200, text="noi dung cong khai")

        fetcher, dh = _tao_fetcher(handler, respect_robots=True, min_delay_seconds=0, max_retries=0)
        ket_qua = fetcher.fetch(f"{_BASE}/truyen/thu-nghiem")
        self.assertEqual(ket_qua.text, "noi dung cong khai")

    def test_khong_co_robots_txt_thi_coi_nhu_cho_phep(self):
        """404 o robots.txt la truong hop PHO BIEN NHAT (site khong cong bo
        gioi han nao) — KHONG duoc coi la loi/tu choi."""
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(404, text="not found")
            return httpx.Response(200, text="noi dung")

        fetcher, dh = _tao_fetcher(handler, respect_robots=True, min_delay_seconds=0, max_retries=0)
        ket_qua = fetcher.fetch(f"{_BASE}/truyen/thu-nghiem")
        self.assertEqual(ket_qua.text, "noi dung")

    def test_robots_txt_duoc_cache_chi_tai_MOT_LAN_cho_ca_host(self):
        so_lan_tai_robots = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                so_lan_tai_robots.append(1)
                return httpx.Response(200, text="User-agent: *\nAllow: /\n")
            return httpx.Response(200, text="noi dung")

        fetcher, dh = _tao_fetcher(handler, respect_robots=True, min_delay_seconds=0, max_retries=0)
        fetcher.fetch(f"{_BASE}/chuong-1")
        fetcher.fetch(f"{_BASE}/chuong-2")
        fetcher.fetch(f"{_BASE}/chuong-3")
        self.assertEqual(len(so_lan_tai_robots), 1, "robots.txt chi tai MOT LAN, cache cho cac lan sau")

    def test_tat_duoc_kiem_tra_robots(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
            return httpx.Response(200, text="van doc duoc vi da tat kiem tra")

        fetcher, dh = _tao_fetcher(handler, respect_robots=False, min_delay_seconds=0, max_retries=0)
        ket_qua = fetcher.fetch(f"{_BASE}/private/chuong-1")
        self.assertEqual(ket_qua.text, "van doc duoc vi da tat kiem tra")


class ConditionalGetTest(unittest.TestCase):
    """Story Harvester V3 Phase 9: `If-None-Match`/`If-Modified-Since` —
    engine cap nhat gia tang dung day de tranh tai lai toan bo noi dung mot
    chuong da biet KHI nguon xac nhan (304) van la noi dung cu."""

    def test_lan_dau_khong_gui_header_dieu_kien_va_luu_lai_etag(self):
        nhan_headers = []

        def handler(request: httpx.Request) -> httpx.Response:
            nhan_headers.append(dict(request.headers))
            return httpx.Response(200, text="noi dung", headers={"ETag": '"v1"'})

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=0, max_retries=0)
        ket_qua = fetcher.fetch(f"{_BASE}/chuong-1")

        self.assertNotIn("if-none-match", nhan_headers[0])
        self.assertEqual(ket_qua.etag, '"v1"')
        self.assertFalse(ket_qua.not_modified)
        self.assertEqual(ket_qua.text, "noi dung")

    def test_gui_if_none_match_khi_duoc_tiem(self):
        nhan_headers = []

        def handler(request: httpx.Request) -> httpx.Response:
            nhan_headers.append(dict(request.headers))
            return httpx.Response(304, headers={"ETag": '"v1"'})

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=0, max_retries=0)
        ket_qua = fetcher.fetch(f"{_BASE}/chuong-1", if_none_match='"v1"')

        self.assertEqual(nhan_headers[0].get("if-none-match"), '"v1"')
        self.assertTrue(ket_qua.not_modified)
        self.assertEqual(ket_qua.text, "", "thân 304 luôn rỗng, không phải lỗi parse")
        self.assertEqual(ket_qua.status_code, 304)

    def test_304_khong_bi_thu_lai_nhu_loi(self):
        so_lan_goi = []

        def handler(request: httpx.Request) -> httpx.Response:
            so_lan_goi.append(1)
            return httpx.Response(304)

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=0, max_retries=2)
        fetcher.fetch(f"{_BASE}/chuong-1", if_none_match='"v1"')
        self.assertEqual(len(so_lan_goi), 1, "304 la thanh cong, khong duoc thu lai")

    def test_noi_dung_doi_tra_ve_200_voi_etag_moi(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="nội dung MỚI", headers={"ETag": '"v2"'})

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=0, max_retries=0)
        ket_qua = fetcher.fetch(f"{_BASE}/chuong-1", if_none_match='"v1"')

        self.assertFalse(ket_qua.not_modified)
        self.assertEqual(ket_qua.etag, '"v2"')
        self.assertEqual(ket_qua.text, "nội dung MỚI")


class SsrfProtectionTest(unittest.TestCase):
    """Phat hien qua review doc lap (Codex): (1) `httpx.Client(follow_redirects=True)`
    cu tu dong theo redirect ma KHONG kiem tra lai host dich, (2) URL o
    TANG CAO NHAT (operator/admin dua vao truc tiep) chua bao gio duoc
    kiem tra IP-rieng-tu o dau ca. Ca hai deu dong lai qua `SsrfBlockedError` +
    kiem tra TUNG chang (`_theo_redirect_an_toan`)."""

    def test_url_goc_toi_dia_chi_loopback_bi_tu_choi_ngay(self):
        so_lan_goi = []

        def handler(request: httpx.Request) -> httpx.Response:
            so_lan_goi.append(1)
            return httpx.Response(200, text="không bao giờ tới đây")

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=0)
        with self.assertRaises(FetchError) as ctx:
            fetcher.fetch("http://127.0.0.1:6379/")
        self.assertIn("IP riêng tư", str(ctx.exception))
        self.assertEqual(so_lan_goi, [], "KHÔNG được kết nối gì cả — từ chối trước khi gọi")

    def test_url_goc_toi_link_local_bi_tu_choi(self):
        fetcher, dh = _tao_fetcher(lambda r: httpx.Response(200), min_delay_seconds=0)
        with self.assertRaises(FetchError):
            fetcher.fetch("http://169.254.169.254/latest/meta-data/")

    def test_redirect_toi_dia_chi_noi_bo_bi_chan_du_host_dau_an_toan(self):
        """Tai hien CHINH XAC phat hien cua review: host DAU TIEN an toan
        (vidu.test, qua MockTransport nen "phan giai" duoc binh thuong),
        nhung no 302 sang mot dia chi loopback — PHAI bi chan o chang
        THU HAI, khong duoc am tham theo."""
        so_lan_goi = []

        def handler(request: httpx.Request) -> httpx.Response:
            so_lan_goi.append(str(request.url))
            if "vd-truyen.example" in str(request.url):
                return httpx.Response(
                    302, headers={"Location": "http://127.0.0.1:8080/internal-admin"})
            return httpx.Response(200, text="KHONG DUOC THAY NOI DUNG NAY")

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=0)
        with self.assertRaises(FetchError) as ctx:
            fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertIn("IP riêng tư", str(ctx.exception))
        self.assertEqual(len(so_lan_goi), 1,
                         "chang thu hai (loopback) KHÔNG được thực sự gọi tới")

    def test_chuoi_redirect_hop_le_van_hoat_dong_binh_thuong(self):
        """Doi chung: mot chuoi redirect toi host CONG KHAI (khong phai
        IP rieng tu) van phai duoc theo va tra ve dung noi dung — sua SSRF
        khong duoc lam vo hanh vi redirect hop phap."""
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/chuong-1":
                return httpx.Response(301, headers={"Location": "/chuong-1-moi"})
            if path == "/chuong-1-moi":
                return httpx.Response(200, text="nội dung chương thật",
                                      headers={"ETag": '"abc"'})
            return httpx.Response(404)

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=0)
        ket_qua = fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertEqual(ket_qua.text, "nội dung chương thật")
        self.assertIn("/chuong-1-moi", ket_qua.final_url)

    def test_qua_nhieu_redirect_nem_loi_ro_rang(self):
        so_lan = []

        def handler(request: httpx.Request) -> httpx.Response:
            so_lan.append(1)
            n = len(so_lan)
            return httpx.Response(302, headers={"Location": f"/vong-{n}"})

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=0, max_retries=0)
        with self.assertRaises(FetchError) as ctx:
            fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertIn("chuyển hướng", str(ctx.exception))

    def test_ssrf_khong_duoc_thu_lai_nhu_loi_mang_tam_thoi(self):
        so_lan_goi = []

        def handler(request: httpx.Request) -> httpx.Response:
            so_lan_goi.append(1)
            return httpx.Response(200)

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=0, max_retries=3)
        with self.assertRaises(FetchError):
            fetcher.fetch("http://127.0.0.1/")
        self.assertEqual(so_lan_goi, [], "từ chối SSRF không cần/không nên thử lại")


class ResponseSizeCapTest(unittest.TestCase):
    """Phat hien qua review doc lap (Codex, "gzip bomb"): httpx tu dong
    giai nen `Content-Encoding: gzip` TRUOC khi dua du lieu ra — kiem tra
    `Content-Length` (kich thuoc TREN DAY) khong bat duoc mot than phan
    hoi NHO nhung giai nen thanh HANG TRAM MB. Kiem tra o day dung
    streaming, dem byte DA GIAI NEN THAT SU."""

    def test_than_qua_lon_bi_tu_choi_du_khong_nen(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"x" * (2 * 1024 * 1024))

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=0, max_retries=0,
                                    max_response_bytes=1024 * 1024)
        with self.assertRaises(FetchError) as ctx:
            fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertIn("giới hạn kích thước", str(ctx.exception))

    def test_gzip_bomb_bi_chan_theo_kich_thuoc_GIAI_NEN_khong_phai_tren_day(self):
        import gzip

        noi_dung_giai_nen = b"A" * (5 * 1024 * 1024)  # 5MB giai nen
        nen = gzip.compress(noi_dung_giai_nen)
        self.assertLess(len(nen), 1024 * 1024, "phai nen NHO hon tran de kiem tra co y nghia")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=nen, headers={"Content-Encoding": "gzip"})

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=0, max_retries=0,
                                    max_response_bytes=1024 * 1024)
        with self.assertRaises(FetchError) as ctx:
            fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertIn("giới hạn kích thước", str(ctx.exception))

    def test_than_duoi_tran_van_tai_binh_thuong(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="nội dung chương bình thường")

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=0, max_retries=0,
                                    max_response_bytes=1024 * 1024)
        ket_qua = fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertEqual(ket_qua.text, "nội dung chương bình thường")

    def test_than_redirect_qua_lon_cung_bi_tu_choi(self):
        """Phat hien qua review doc lap (Codex, verify pass): nhanh xu ly
        redirect (3xx) ban dau GOI `resp.read()` KHONG GIOI HAN — mot chang
        redirect TRUNG GIAN (khong phai phan hoi cuoi cung) do ke tan cong
        dieu khien co the tra ve than KHONG LO GIOI HAN, tai dien chinh
        loi "gzip bomb" tren mot nhanh khac. PHAI ap tran cho CA redirect."""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                302, content=b"x" * (2 * 1024 * 1024),
                headers={"Location": "/noi-den"})

        fetcher, dh = _tao_fetcher(handler, min_delay_seconds=0, max_retries=0,
                                    max_response_bytes=1024 * 1024)
        with self.assertRaises(FetchError) as ctx:
            fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertIn("giới hạn kích thước", str(ctx.exception))


class RobotsRedirectHostMismatchTest(unittest.TestCase):
    """Phat hien qua review doc lap (Codex, verify pass): `_robots_cache`
    luu ket qua duoi khoa host GOC, nhung neu robots.txt cua host GOC
    redirect sang MOT HOST KHAC, noi dung do la CUA HOST KIA — ap dung cho
    host goc se ap SAI chinh sach (qua long hoac qua chat mot cach ngoai
    y muon)."""

    def test_robots_txt_redirect_sang_host_khac_khong_duoc_tin_dung(self):
        """Dung mot chinh sach HAN CHE (`Disallow: /`) o host-khac.example
        — neu loi CU con (cache dua tren host goc nhung noi dung tu host
        khac) van con, fetch binh thuong toi `vd-truyen.example` se bi
        CHAN OAN (`RobotsDisallowedError`). Sau ban sua: host goc duoc coi
        la "khong co robots.txt rieng" (an toan mac dinh la cho phep),
        KHONG "thua huong" chinh sach han che cua host khac."""
        def handler(request: httpx.Request) -> httpx.Response:
            if "vd-truyen.example" in str(request.url) and request.url.path == "/robots.txt":
                return httpx.Response(
                    302, headers={"Location": "https://host-khac.example/robots.txt"})
            if "host-khac.example" in str(request.url):
                return httpx.Response(200, text="User-agent: *\nDisallow: /")
            return httpx.Response(200, text="nội dung bình thường")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        dh = _DongHoGia()
        fetcher = HttpFetcher(client=client, sleep_fn=dh.sleep, clock_fn=dh.now,
                              min_delay_seconds=0, respect_robots=True)

        ket_qua = fetcher.fetch(f"{_BASE}/duong-binh-thuong")
        self.assertEqual(ket_qua.status_code, 200)


class RetryAfterAndTooManyRequestsTest(unittest.TestCase):
    """Overnight ("network resilience"): 429 (Too Many Requests) la loi
    TAM THOI (gioi han toc do), KHONG PHAI loi 4xx vinh vien nhu 404 —
    truoc ban sua nay bi coi nhu 404 va KHONG BAO GIO duoc thu lai. Khi
    server co header `Retry-After`, PHAI cho DUNG khoang do thay vi
    backoff mu."""

    def test_429_duoc_thu_lai_khong_bi_coi_nhu_loi_client_vinh_vien(self):
        so_lan_goi = []

        def handler(request: httpx.Request) -> httpx.Response:
            so_lan_goi.append(1)
            if len(so_lan_goi) < 3:
                return httpx.Response(429, text="rate limited")
            return httpx.Response(200, text="nội dung thật")

        fetcher, dh = _tao_fetcher(handler, max_retries=2, min_delay_seconds=0)
        ket_qua = fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertEqual(ket_qua.text, "nội dung thật")
        self.assertEqual(len(so_lan_goi), 3)

    def test_429_qua_so_lan_thu_lai_van_nem_loi_ro_rang(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="rate limited")

        fetcher, dh = _tao_fetcher(handler, max_retries=1, min_delay_seconds=0)
        with self.assertRaises(FetchError) as ctx:
            fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertIn("429", str(ctx.exception))

    def test_retry_after_so_giay_duoc_ton_trong_thay_vi_backoff_mu(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "17"})

        fetcher, dh = _tao_fetcher(handler, max_retries=1, min_delay_seconds=0,
                                    backoff_base_seconds=1.0)
        with self.assertRaises(FetchError):
            fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertEqual(dh.slept, [17.0], "phải chờ đúng Retry-After, không phải backoff mũ")

    def test_retry_after_dang_http_date_duoc_doc_dung(self):
        from email.utils import format_datetime
        from datetime import datetime, timedelta, timezone

        khi = datetime.now(timezone.utc) + timedelta(seconds=10)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": format_datetime(khi, usegmt=True)})

        fetcher, dh = _tao_fetcher(handler, max_retries=1, min_delay_seconds=0)
        with self.assertRaises(FetchError):
            fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertEqual(len(dh.slept), 1)
        # `Retry-After` dang HTTP-date chi co do phan giai MOT GIAY
        # (`format_datetime` bo phan le), va giua luc tinh `khi` o tren va
        # luc ma nguon goi `now()` con mot khoang thuc thi that. Hai sai so
        # nay CONG lai, nen `delta=1.0` bang dung sai so luong tu cua chinh
        # header — khong con bien nao cho thoi gian chay. Bai test vi vay
        # flaky NGAY TU THIET KE, khong phai do may cham.
        #
        # Da do that tren CI (run 33762888831): `8.983369 != 10.0 within 1.0
        # delta (1.0166 difference)`. Tep nay khong doi mot byte nao so voi
        # main — day la loi co san, khong phai do lan hop nhat Router V4.
        #
        # `delta=2.0` van phan biet duoc dung dieu bai test NAY ton tai de
        # phan biet: doc HTTP-date thanh MOC TUYET DOI (~10s) so voi lui ve
        # backoff mu (~1s, lech 9.0 -> van do). Khong lam yeu phep thu.
        self.assertAlmostEqual(dh.slept[0], 10.0, delta=2.0)

    def test_retry_after_khong_hop_le_lui_ve_backoff_mu(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "not-a-valid-value"})

        fetcher, dh = _tao_fetcher(handler, max_retries=1, min_delay_seconds=0,
                                    backoff_base_seconds=1.0)
        with self.assertRaises(FetchError):
            fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertEqual(dh.slept, [1.0])

    def test_retry_after_qua_lon_bi_gioi_han_hop_ly(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "999999999"})

        fetcher, dh = _tao_fetcher(handler, max_retries=1, min_delay_seconds=0)
        with self.assertRaises(FetchError):
            fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertEqual(dh.slept, [300.0], "phải bị chặn ở trần hợp lý, không tin tuyệt đối server")

    def test_503_co_retry_after_cung_duoc_ton_trong(self):
        so_lan_goi = []

        def handler(request: httpx.Request) -> httpx.Response:
            so_lan_goi.append(1)
            if len(so_lan_goi) < 2:
                return httpx.Response(503, headers={"Retry-After": "5"})
            return httpx.Response(200, text="ok")

        fetcher, dh = _tao_fetcher(handler, max_retries=1, min_delay_seconds=0,
                                    backoff_base_seconds=1.0)
        ket_qua = fetcher.fetch(f"{_BASE}/chuong-1")
        self.assertEqual(ket_qua.text, "ok")
        self.assertEqual(dh.slept, [5.0])


if __name__ == "__main__":
    unittest.main()
