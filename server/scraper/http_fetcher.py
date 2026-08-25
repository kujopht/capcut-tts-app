"""
Tier 0 — HTTP truc tiep. KHONG trinh duyet, KHONG JS render.

Day la lop DUY NHAT trong scraper duoc phep goi mang that. Tat ca adapter
nhan mot `Fetcher` qua constructor (dependency injection) thay vi tu tao
client rieng — cho phep test tiem mot fetcher gia doc tu fixture cuc bo
(xem `server/tests/test_story_scraper_*.py`) ma khong cham mang that.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

#: Danh tinh ro rang trong User-Agent — mot so nguon chan bot an danh, va
#: day la hanh vi lich su can co khi truy cap trang cua nguoi khac.
USER_AGENT = "FanficWorldStoryScraper/0.1 (+https://fanfic.world; contact: admin@fanfic.world)"

DEFAULT_TIMEOUT_SECONDS = 20.0


class FetchError(RuntimeError):
    """Loi mang/HTTP khi tai mot trang — phan biet voi loi PHAN TICH (noi
    dung tai duoc nhung khong doc duoc), de noi goi xu ly khac nhau (thu
    lai mang so voi bo qua trang khong dung dinh dang)."""


@dataclass
class FetchResult:
    #: URL SAU CUNG sau khi theo redirect that — day moi la canonical_url
    #: dang tin cay duoc, khac voi chuan hoa CHUOI cua `canonicalize_url`.
    final_url: str
    status_code: int
    content_type: str
    text: str


class HttpFetcher:
    """Fetcher THAT — dung httpx, theo redirect, co timeout, KHONG bao gio
    doc bien moi truong proxy ngoai y muon (`trust_env=False`, cung nguyen
    tac voi `QuickFreeImageProvider` trong `image_provider_registry.py`)."""

    def __init__(self, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
                 client: Optional[httpx.Client] = None):
        self._timeout = timeout_seconds
        self._client = client

    def _http_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(
            timeout=self._timeout, trust_env=False, follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )

    def fetch(self, url: str) -> FetchResult:
        client = self._http_client()
        try:
            resp = client.get(url)
        except httpx.TimeoutException as exc:
            raise FetchError(f"Hết thời gian tải {url}") from exc
        except httpx.HTTPError as exc:
            raise FetchError(f"Không tải được {url}: {exc}") from exc
        finally:
            if self._client is None:
                client.close()

        if resp.status_code >= 400:
            raise FetchError(f"{url} trả về HTTP {resp.status_code}")

        return FetchResult(
            final_url=str(resp.url),
            status_code=resp.status_code,
            content_type=resp.headers.get("content-type", ""),
            text=resp.text,
        )


class FixtureFetcher:
    """Fetcher GIA cho test — doc tu mot dict `{url: html}` cuc bo thay vi
    goi mang. `final_url` mac dinh CHINH LA `url` (khong mo phong redirect)
    tru khi duoc chi dinh rieng trong `redirects`."""

    def __init__(self, pages: dict, *, redirects: Optional[dict] = None):
        self._pages = pages
        self._redirects = redirects or {}

    def fetch(self, url: str) -> FetchResult:
        if url not in self._pages:
            raise FetchError(f"Fixture không có trang: {url}")
        return FetchResult(
            final_url=self._redirects.get(url, url),
            status_code=200,
            content_type="text/html; charset=utf-8",
            text=self._pages[url],
        )
