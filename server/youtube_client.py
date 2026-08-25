"""
Client MONG cho YouTube Data API v3 (Phase 5, Trusted Video Sources).

NGUYEN TAC:
- CHI goi Data API chinh thuc — KHONG scrape HTML, KHONG tai/luu lai video
  (xem docstring dau `trusted_source_domain.py`).
- Uu tien tra cuu TRUC TIEP theo ID (`videos.list`/`channels.list`/
  `playlists.list`/`playlistItems.list`) — TRANH `search.list` vi no ton
  quota gap boi (100 don vi/lan, so voi 1 don vi cua cac lenh list o tren)
  VA tra ve ket qua MO (khong chinh xac bang tra thang theo ID).
- API key CHI nam o day, luon la QUERY PARAM `key=`, KHONG BAO GIO ghi vao
  log/loi/response tra ve frontend. `_goi()` bat loi va DUNG
  `thong_diep_loi_an_toan` giong `appwrite_adapter.py` — thong diep loi
  KHONG BAO GIO chua URL day du (URL luon co `key=` trong query).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import httpx

from server.animation_domain import parse_youtube_id

_API_BASE = "https://www.googleapis.com/youtube/v3"
REQUEST_TIMEOUT = 15.0

#: ID playlist YouTube: chu/so, thuong bat dau PL/UU/LL/FL/RD, dai ~13-42 ky tu.
_PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,42}$")
_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")


class YouTubeConfigError(RuntimeError):
    """Thieu `YOUTUBE_API_KEY` — bao ro thay vi am tham tra ve rong."""


class YouTubeApiError(RuntimeError):
    """
    YouTube Data API tra loi >= 400, hoac loi mang.

    Thong diep AN TOAN — khong bao gio chua `key=` hay URL day du. Loi quota
    (`quotaExceeded`) duoc GIU LAI nguyen dang trong `reason` de tang tren
    hien thi rieng ("Đã hết hạn mức API hôm nay") thay vi mot loi chung
    chung.
    """

    def __init__(self, message: str, *, reason: str = ""):
        super().__init__(message)
        self.reason = reason


@dataclass
class ChannelInfo:
    channel_id: str
    title: str
    thumbnail_url: str
    uploads_playlist_id: str


@dataclass
class PlaylistInfo:
    playlist_id: str
    title: str
    thumbnail_url: str
    channel_id: str
    channel_title: str
    item_count: int


@dataclass
class VideoInfo:
    video_id: str
    title: str
    channel_id: str
    channel_title: str
    thumbnail_url: str
    published_at: str
    duration_seconds: float


@dataclass
class SourceUrlRef:
    """Ket qua phan tich MOT url/chuoi nguoi dung dan vao — CHI la phan tich
    CHUOI, KHONG goi mang. Xem `parse_source_url`."""

    #: "video" | "playlist" | "channel_id" | "channel_handle" | "channel_username"
    kind: str
    value: str


_YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "youtube-nocookie.com", "www.youtube-nocookie.com",
    "youtu.be", "www.youtu.be",
}


def parse_source_url(raw: str) -> Optional[SourceUrlRef]:
    """
    Doc mot URL YouTube (video/kenh/playlist) HOAC mot ID tran, tra ve LOAI
    va GIA TRI tuong ung — thuan phan tich chuoi, KHONG goi mang.

    Uu tien: VIDEO truoc (ke ca khi URL co ca `list=`, vi nguoi dung dan mot
    video CU THE thi y dinh ro rang la them video do, khong phai ca
    playlist chua no) — roi PLAYLIST — roi KENH.
    """
    candidate = (raw or "").strip()
    if not candidate:
        return None

    video_id = parse_youtube_id(candidate)
    if video_id and "list=" not in candidate and "/channel/" not in candidate \
            and "/@" not in candidate and "/c/" not in candidate and "/user/" not in candidate:
        return SourceUrlRef("video", video_id)

    try:
        parsed = urlparse(candidate if "//" in candidate else f"//{candidate}")
    except ValueError:
        parsed = None
    host = (parsed.hostname or "").lower() if parsed else ""
    is_youtube_url = host in _YOUTUBE_HOSTS

    if is_youtube_url:
        query = parse_qs(parsed.query or "")
        v_list = query.get("v") or []
        if v_list and parse_youtube_id(v_list[0]):
            return SourceUrlRef("video", v_list[0])

        list_vals = query.get("list") or []
        if list_vals and _PLAYLIST_ID_RE.match(list_vals[0]):
            return SourceUrlRef("playlist", list_vals[0])

        path_parts = [p for p in (parsed.path or "").split("/") if p]
        if len(path_parts) >= 2 and path_parts[0] == "channel":
            cid = path_parts[1]
            if _CHANNEL_ID_RE.match(cid):
                return SourceUrlRef("channel_id", cid)
        if path_parts and path_parts[0].startswith("@"):
            return SourceUrlRef("channel_handle", path_parts[0])
        if len(path_parts) >= 2 and path_parts[0] == "user":
            return SourceUrlRef("channel_username", path_parts[1])
        if len(path_parts) >= 2 and path_parts[0] == "c":
            # `/c/TenTuyChinh` KHONG the tra cuu truc tiep qua channels.list
            # (can `search.list`, ma dac ta yeu cau TRANH) — thu nhu MOT
            # handle (nhieu kenh /c/ cu gio da trung voi @handle that), goi
            # noi that bai o tang tren se bao ro cho nguoi dung dan lai
            # duong /channel/... hoac /@handle.
            return SourceUrlRef("channel_handle", f"@{path_parts[1]}")
        return None

    # Khong phai URL YouTube — co the la MOT ID tran (playlist hoac kenh).
    if _CHANNEL_ID_RE.match(candidate):
        return SourceUrlRef("channel_id", candidate)
    if _PLAYLIST_ID_RE.match(candidate) and candidate[:2] in ("PL", "UU", "LL", "FL", "RD", "OL"):
        return SourceUrlRef("playlist", candidate)
    return None


def _parse_iso8601_duration(raw: str) -> float:
    """`PT1H2M3S` -> giay. Tra `0.0` neu khong doc duoc (KHONG doan)."""
    m = re.match(
        r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$", raw or "")
    if not m:
        return 0.0
    gio, phut, giay = m.groups()
    return (int(gio or 0) * 3600) + (int(phut or 0) * 60) + float(giay or 0)


class YouTubeClient:
    """MOT client dung lai cho toan bo request trong mot lan quet — xem
    ghi chu ve `httpx.Client` tai su dung o `appwrite_adapter.py`."""

    #: Pre-merge hardening (2026-08) — 429 (rate limit tam thoi, KHAC
    #: `quotaExceeded` — do la het HAN MUC NGAY, thu lai vo ich) va 5xx
    #: (loi TAM THOI phia YouTube) deu dang thu lai duoc; 4xx con lai
    #: (400/403/404...) la loi VINH VIEN — thu lai khong lam gi khac di, chi
    #: ton them thoi gian/quota. TOI DA 3 lan thu (1 goc + 2 thu lai).
    RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
    RETRY_MAX_ATTEMPTS = 3
    #: Giay — CAP LOP hang so de test ghi de/mock (vd
    #: `mock.patch.object(YouTubeClient, "RETRY_BASE_DELAY_SECONDS", 0)`)
    #: tranh cho THAT trong bo kiem thu. Backoff mu (0.5s, 1s, ...).
    RETRY_BASE_DELAY_SECONDS = 0.5

    def __init__(self, api_key: str):
        if not api_key:
            raise YouTubeConfigError(
                "Chưa cấu hình YOUTUBE_API_KEY — không thể gọi YouTube Data API.")
        self._api_key = api_key
        self._client: Optional[httpx.Client] = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=REQUEST_TIMEOUT)
        return self._client

    def _cho_truoc_khi_thu_lai(self, attempt: int, resp: httpx.Response) -> None:
        """`attempt` la SO THU TU lan goi VUA THAT BAI (1-based) — backoff mu
        theo `RETRY_BASE_DELAY_SECONDS * 2**(attempt-1)` (0.5s, 1s, 2s, ...).
        429 CO THE kem `Retry-After` (giay) tu YouTube — TON TRONG gia tri do
        thay vi backoff cua rieng ta neu co mat va doc duoc."""
        delay = self.RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    pass
        time.sleep(delay)

    def _goi(self, resource: str, params: Dict[str, Any]) -> Dict[str, Any]:
        gui = dict(params)
        gui["key"] = self._api_key
        for attempt in range(1, self.RETRY_MAX_ATTEMPTS + 1):
            try:
                resp = self._http().get(f"{_API_BASE}/{resource}", params=gui)
            except httpx.HTTPError as exc:
                # KHONG dua `exc` (co the chua URL kem key) thang vao thong diep.
                raise YouTubeApiError("Không kết nối được YouTube Data API.") from exc
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                except Exception:
                    body = None
                errors = ((body or {}).get("error") or {}).get("errors") or []
                reason = str(errors[0].get("reason") or "") if errors else ""
                if reason == "quotaExceeded":
                    # Het HAN MUC NGAY — thu lai KHONG BAO GIO giup ich, chi
                    # ton them lan goi vo ich. That bai NGAY, khac 429/5xx.
                    raise YouTubeApiError(
                        "Đã hết hạn mức gọi YouTube Data API hôm nay.", reason=reason)
                if (resp.status_code in self.RETRY_STATUS_CODES
                        and attempt < self.RETRY_MAX_ATTEMPTS):
                    self._cho_truoc_khi_thu_lai(attempt, resp)
                    continue
                raise YouTubeApiError(
                    f"YouTube Data API từ chối yêu cầu (HTTP {resp.status_code}).",
                    reason=reason)
            return resp.json()
        # Khong bao gio toi day that su (vong lap luon `return` hoac `raise`
        # o lan thu CUOI CUNG) — chi de type-checker/an toan doc code yen tam.
        raise YouTubeApiError("YouTube Data API từ chối yêu cầu nhiều lần liên tiếp.")

    # -- video ----------------------------------------------------------------

    def get_videos(self, video_ids: List[str]) -> Dict[str, VideoInfo]:
        """Toi da 50 ID/lan (gioi han cua chinh YouTube Data API) — nguoi
        goi tu chia lo neu can hon."""
        ds = [v for v in dict.fromkeys(video_ids) if v][:50]
        if not ds:
            return {}
        data = self._goi("videos", {
            "part": "snippet,contentDetails", "id": ",".join(ds),
        })
        ra: Dict[str, VideoInfo] = {}
        for item in data.get("items") or []:
            sn = item.get("snippet") or {}
            cd = item.get("contentDetails") or {}
            vid = str(item.get("id") or "")
            if not vid:
                continue
            ra[vid] = VideoInfo(
                video_id=vid,
                title=str(sn.get("title") or ""),
                channel_id=str(sn.get("channelId") or ""),
                channel_title=str(sn.get("channelTitle") or ""),
                thumbnail_url=_anh_dai_dien(sn),
                published_at=str(sn.get("publishedAt") or ""),
                duration_seconds=_parse_iso8601_duration(str(cd.get("duration") or "")),
            )
        return ra

    def get_video(self, video_id: str) -> Optional[VideoInfo]:
        return self.get_videos([video_id]).get(video_id)

    # -- kenh -------------------------------------------------------------

    def _kenh_tu_items(self, data: Dict[str, Any]) -> Optional[ChannelInfo]:
        items = data.get("items") or []
        if not items:
            return None
        item = items[0]
        sn = item.get("snippet") or {}
        cd = item.get("contentDetails") or {}
        uploads = str(
            ((cd.get("relatedPlaylists") or {}).get("uploads")) or "")
        return ChannelInfo(
            channel_id=str(item.get("id") or ""),
            title=str(sn.get("title") or ""),
            thumbnail_url=_anh_dai_dien(sn),
            uploads_playlist_id=uploads,
        )

    def get_channel(self, channel_id: str) -> Optional[ChannelInfo]:
        return self._kenh_tu_items(self._goi(
            "channels", {"part": "snippet,contentDetails", "id": channel_id}))

    def get_channel_by_handle(self, handle: str) -> Optional[ChannelInfo]:
        handle = handle if handle.startswith("@") else f"@{handle}"
        return self._kenh_tu_items(self._goi(
            "channels", {"part": "snippet,contentDetails", "forHandle": handle}))

    def get_channel_by_username(self, username: str) -> Optional[ChannelInfo]:
        return self._kenh_tu_items(self._goi(
            "channels", {"part": "snippet,contentDetails", "forUsername": username}))

    # -- playlist ---------------------------------------------------------

    def get_playlist(self, playlist_id: str) -> Optional[PlaylistInfo]:
        data = self._goi(
            "playlists", {"part": "snippet,contentDetails", "id": playlist_id})
        items = data.get("items") or []
        if not items:
            return None
        item = items[0]
        sn = item.get("snippet") or {}
        cd = item.get("contentDetails") or {}
        return PlaylistInfo(
            playlist_id=str(item.get("id") or ""),
            title=str(sn.get("title") or ""),
            thumbnail_url=_anh_dai_dien(sn),
            channel_id=str(sn.get("channelId") or ""),
            channel_title=str(sn.get("channelTitle") or ""),
            item_count=int(cd.get("itemCount") or 0),
        )

    def list_playlist_items(
        self, playlist_id: str, *, page_token: str = "", max_results: int = 50,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Tra `(items, next_page_token)`. MOI item la dict THO tu
        `playlistItems.list` (chua `videoId`/`title`/`publishedAt`, KHONG co
        `duration` — goi THEM `get_videos()` de lam giau neu can, xem
        `TrustedSourceService._quet_ung_vien`).
        """
        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": max(1, min(50, max_results)),
        }
        if page_token:
            params["pageToken"] = page_token
        data = self._goi("playlistItems", params)
        return list(data.get("items") or []), str(data.get("nextPageToken") or "")


def _anh_dai_dien(snippet: Dict[str, Any]) -> str:
    thumbs = snippet.get("thumbnails") or {}
    for kich in ("medium", "high", "default"):
        url = (thumbs.get(kich) or {}).get("url")
        if url:
            return str(url)
    return ""
