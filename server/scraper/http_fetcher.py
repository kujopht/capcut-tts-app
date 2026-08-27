"""
Tier 0 — HTTP truc tiep. KHONG trinh duyet, KHONG JS render.

Day la lop DUY NHAT trong scraper duoc phep goi mang that. Tat ca adapter
nhan mot `Fetcher` qua constructor (dependency injection) thay vi tu tao
client rieng — cho phep test tiem mot fetcher gia doc tu fixture cuc bo
(xem `server/tests/test_story_scraper_*.py`) ma khong cham mang that.

BA hanh vi "cong dan tot" o day (retry/backoff, gioi han toc do, robots.txt)
CHI ap dung cho `HttpFetcher` — `FixtureFetcher` (dung trong toan bo test
hien co) KHONG doi, vi no khong goi mang that nen khong co gi de gioi han
hay thu lai.
"""
from __future__ import annotations

import time
import urllib.robotparser
from dataclasses import dataclass
from typing import Callable, Dict, Optional
from urllib.parse import urlsplit

import httpx

#: Danh tinh ro rang trong User-Agent — mot so nguon chan bot an danh, va
#: day la hanh vi lich su can co khi truy cap trang cua nguoi khac.
USER_AGENT = "FanficWorldStoryScraper/0.1 (+https://fanfic.world; contact: admin@fanfic.world)"

DEFAULT_TIMEOUT_SECONDS = 20.0

#: So lan THU LAI toi da cho loi TAM THOI (timeout/loi mang/5xx) — KHONG
#: tinh lan goi dau. 2 lan thu lai (3 lan goi tong cong) la muc vua du de
#: song sot mot lan nghen mang thoang qua ma khong bien mot loi that (site
#: sap that) thanh mot vong cho dai vo ich.
DEFAULT_MAX_RETRIES = 2
#: Backoff MU (khong phai tuyen tinh): lan 1 doi `base`, lan 2 doi `base*2`,
#: ... — cho nguon thoi gian phuc hoi neu day la mot lan nghen tam thoi
#: (rate-limit phia ho, khoi phuc mang), thay vi dap lien tiep cung mot nhip.
DEFAULT_BACKOFF_BASE_SECONDS = 1.0
#: KHOANG CACH TOI THIEU giua hai lan goi LIEN TIEP toi CUNG mot host — phep
#: lich su co ban khi quet mot nguon cong khai: khong dat mot host la vao
#: mot chuoi request lien tuc khong nghi. 1 giay/host la muc than thien pho
#: bien (Scrapy mac dinh `DOWNLOAD_DELAY=0`, nhung khuyen nghi cong dong cho
#: crawler lich su thuong tu 1-3s cho MOT host don le, khong phai mot farm).
DEFAULT_MIN_DELAY_SECONDS = 1.0


class FetchError(RuntimeError):
    """Loi mang/HTTP khi tai mot trang — phan biet voi loi PHAN TICH (noi
    dung tai duoc nhung khong doc duoc), de noi goi xu ly khac nhau (thu
    lai mang so voi bo qua trang khong dung dinh dang)."""


class RobotsDisallowedError(FetchError):
    """`robots.txt` cua nguon TU CHOI truy cap url nay cho user-agent cua
    ta. KHONG duoc am tham bo qua/tra rong nhu da thanh cong (cung triet ly
    voi Tier 3 "khong ho tro" o `server/scraper/__init__.py`) — nem loi ro
    de nguoi van hanh BIET day la mot gioi han co chu dinh cua nguon, khong
    phai mot loi ky thuat can sua."""


@dataclass
class FetchResult:
    #: URL SAU CUNG sau khi theo redirect that — day moi la canonical_url
    #: dang tin cay duoc, khac voi chuan hoa CHUOI cua `canonicalize_url`.
    final_url: str
    status_code: int
    content_type: str
    text: str
    #: Header `ETag`/`Last-Modified` cua PHAN HOI (rong neu nguon khong gui)
    #: — luu lai de LAN SAU goi `fetch(..., if_none_match=...)` (Story
    #: Harvester V3 Phase 9: engine cap nhat gia tang). Rong KHONG co nghia
    #: la loi, chi la nguon khong ho tro validator nay.
    etag: str = ""
    last_modified: str = ""
    #: `True` khi server tra 304 (noi dung KHONG doi so voi validator da gui
    #: qua `if_none_match`/`if_modified_since`) — `text` RONG trong truong
    #: hop nay (than 304 luon rong theo giao thuc HTTP, khong phai loi parse).
    #: Noi goi PHAI kiem co nay TRUOC khi doc `text`, khong duoc coi mot
    #: `FetchResult` rong la "trang rong that su".
    not_modified: bool = False


def _host_key(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


class HttpFetcher:
    """Fetcher THAT — dung httpx, theo redirect, co timeout, KHONG bao gio
    doc bien moi truong proxy ngoai y muon (`trust_env=False`, cung nguyen
    tac voi `QuickFreeImageProvider` trong `image_provider_registry.py`).

    Them BA lop "cong dan tot" so voi ban dau: gioi han toc do moi host,
    thu lai co backoff cho loi tam thoi, va kiem tra `robots.txt` truoc khi
    tai. Ca ba deu co the tat (`min_delay_seconds=0`, `max_retries=0`,
    `respect_robots=False`) cho truong hop test/noi bo can toc do, nhung
    mac dinh BAT — day la hanh vi PHAI co khi quet trang cua nguoi khac,
    khong phai tuy chon "tot hon neu co".
    """

    def __init__(self, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
                 client: Optional[httpx.Client] = None,
                 max_retries: int = DEFAULT_MAX_RETRIES,
                 backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
                 min_delay_seconds: float = DEFAULT_MIN_DELAY_SECONDS,
                 respect_robots: bool = True,
                 sleep_fn: Callable[[float], None] = time.sleep,
                 clock_fn: Callable[[], float] = time.monotonic):
        self._timeout = timeout_seconds
        self._client = client
        self._max_retries = max_retries
        self._backoff_base = backoff_base_seconds
        self._min_delay = min_delay_seconds
        self._respect_robots = respect_robots
        self._sleep = sleep_fn
        self._clock = clock_fn
        self._last_request_at: Dict[str, float] = {}
        self._robots_cache: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}

    def _http_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(
            timeout=self._timeout, trust_env=False, follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )

    def _cho_gioi_han_toc_do(self, url: str) -> None:
        if self._min_delay <= 0:
            return
        host = _host_key(url)
        lan_truoc = self._last_request_at.get(host)
        now = self._clock()
        if lan_truoc is not None:
            da_troi = now - lan_truoc
            if da_troi < self._min_delay:
                self._sleep(self._min_delay - da_troi)
        self._last_request_at[host] = self._clock()

    def _kiem_tra_robots(self, url: str) -> None:
        if not self._respect_robots:
            return
        host = _host_key(url)
        if host not in self._robots_cache:
            self._robots_cache[host] = self._tai_robots(host)
        parser = self._robots_cache[host]
        if parser is not None and not parser.can_fetch(USER_AGENT, url):
            raise RobotsDisallowedError(
                f"robots.txt của {host} từ chối truy cập {url} cho user-agent này."
            )

    def _tai_robots(self, host: str) -> Optional[urllib.robotparser.RobotFileParser]:
        """Tai `robots.txt` qua CHINH client httpx da tiem — KHONG dung
        `RobotFileParser.read()` cua stdlib (no tu mo ket noi rieng qua
        `urllib.request`, di vong qua `trust_env=False`/client duoc kiem
        soat o day, vi pham dung nguyen tac "day la lop DUY NHAT duoc phep
        goi mang that" o dau tep). `.parse()` chi doc tung dong VAN BAN da
        co san, khong tu I/O.
        """
        client = self._http_client()
        try:
            resp = client.get(f"{host}/robots.txt")
        except (httpx.TimeoutException, httpx.HTTPError):
            # Khong tai duoc robots.txt (mang loi, timeout...) — coi nhu
            # KHONG co gioi han, dung mac dinh "cho phep" cua da so trinh
            # thu thap khi thieu tep nay.
            return None
        finally:
            if self._client is None:
                client.close()
        if resp.status_code >= 400:
            # 404 la truong hop PHO BIEN NHAT (site khong co robots.txt) —
            # nghia la khong co gioi han nao duoc cong bo, KHONG phai loi.
            return None
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(resp.text.splitlines())
        return parser

    def _mot_lan_goi(self, client: httpx.Client, url: str,
                     headers: Dict[str, str]) -> httpx.Response:
        try:
            return client.get(url, headers=headers or None)
        except httpx.TimeoutException as exc:
            raise FetchError(f"Hết thời gian tải {url}") from exc
        except httpx.HTTPError as exc:
            raise FetchError(f"Không tải được {url}: {exc}") from exc

    def fetch(self, url: str, *, if_none_match: Optional[str] = None,
             if_modified_since: Optional[str] = None) -> FetchResult:
        """`if_none_match`/`if_modified_since`: validator luu lai tu MOT
        lan `fetch()` THANH CONG truoc do cua CUNG url (xem
        `FetchResult.etag`/`last_modified`) — khi nguon tra 304, `fetch()`
        tra ve `FetchResult(not_modified=True, text="")` NGAY, khong ne
        than trong ("Nghia La Khong Doi", Phase 9 cua Story Harvester V3:
        engine cap nhat gia tang dung dieu nay de biet MOT chuong da xong
        co can tai lai hay khong ma KHONG can tai lai toan bo noi dung)."""
        self._kiem_tra_robots(url)
        headers: Dict[str, str] = {}
        if if_none_match:
            headers["If-None-Match"] = if_none_match
        if if_modified_since:
            headers["If-Modified-Since"] = if_modified_since

        client = self._http_client()
        try:
            loi_cuoi: Optional[Exception] = None
            resp: Optional[httpx.Response] = None
            for lan in range(self._max_retries + 1):
                self._cho_gioi_han_toc_do(url)
                try:
                    resp = self._mot_lan_goi(client, url, headers)
                except FetchError as exc:
                    # Loi MANG (timeout/ket noi) — luon dang thu thu lai.
                    loi_cuoi = exc
                    resp = None
                else:
                    if resp.status_code < 500:
                        # Thanh cong (bao gom 304) HOAC loi phia CLIENT
                        # (4xx) — 4xx se KHONG tu khac di neu goi lai y het,
                        # dung thu.
                        break
                    loi_cuoi = FetchError(f"{url} trả về HTTP {resp.status_code}")
                if lan < self._max_retries:
                    self._sleep(self._backoff_base * (2 ** lan))

            if resp is None:
                assert loi_cuoi is not None
                raise loi_cuoi
            if resp.status_code >= 400:
                raise FetchError(f"{url} trả về HTTP {resp.status_code}")
        finally:
            if self._client is None:
                client.close()

        return FetchResult(
            final_url=str(resp.url),
            status_code=resp.status_code,
            content_type=resp.headers.get("content-type", ""),
            text="" if resp.status_code == 304 else resp.text,
            etag=resp.headers.get("etag", ""),
            last_modified=resp.headers.get("last-modified", ""),
            not_modified=resp.status_code == 304,
        )


class FixtureFetcher:
    """Fetcher GIA cho test — doc tu mot dict `{url: html}` cuc bo thay vi
    goi mang. `final_url` mac dinh CHINH LA `url` (khong mo phong redirect)
    tru khi duoc chi dinh rieng trong `redirects`.

    `etags`: mo phong validator `ETag` (Phase 9 cua Story Harvester V3) —
    khi `if_none_match` goi vao KHOP gia tri da khai bao cho `url` trong
    dict nay, tra ve `not_modified=True`/`text=""` (mo phong 304) thay vi
    noi dung that. RONG (mac dinh) = khong mo phong ETag nao, moi lan goi
    deu tra noi dung day du (hanh vi CU, khong doi cho test hien co)."""

    def __init__(self, pages: dict, *, redirects: Optional[dict] = None,
                 etags: Optional[dict] = None):
        self._pages = pages
        self._redirects = redirects or {}
        self._etags = etags or {}

    def fetch(self, url: str, *, if_none_match: Optional[str] = None,
             if_modified_since: Optional[str] = None) -> FetchResult:
        if url not in self._pages:
            raise FetchError(f"Fixture không có trang: {url}")
        etag = self._etags.get(url, "")
        if if_none_match and etag and if_none_match == etag:
            return FetchResult(
                final_url=self._redirects.get(url, url), status_code=304,
                content_type="", text="", etag=etag, not_modified=True)
        return FetchResult(
            final_url=self._redirects.get(url, url),
            status_code=200,
            content_type="text/html; charset=utf-8",
            text=self._pages[url],
            etag=etag,
        )
