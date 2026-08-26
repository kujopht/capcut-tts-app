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


if __name__ == "__main__":
    unittest.main()
