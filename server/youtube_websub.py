"""
Client + phan tich thong bao cho YouTube WebSub (PubSubHubbub) — Phase 6,
Trusted Video Sources.

GIAO THUC: xem https://developers.google.com/youtube/v3/guides/push_notifications
va dac ta WebSub chinh thuc (https://www.w3.org/TR/websub/). YouTube dung hub
dung chung `pubsubhubbub.appspot.com`, topic URL la
`https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID` — CHI kenh
(`youtube_channel`) moi dang ky duoc, playlist/video don le KHONG co feed
tuong duong.

AN TOAN — MOI du lieu trong module nay DEN TU INTERNET, coi la THU DICH:
- `parse_notification()` dung `defusedxml` (KHONG dung `xml.etree.
  ElementTree` truc tiep — thu vien do KHONG chan duoc "billion laughs"/
  quadratic blowup, xem `server/requirements.txt`), GIOI HAN kich thuoc
  THAN TRUOC KHI phan tich.
- `verify_signature()` so sanh HMAC bang `hmac.compare_digest` (chong
  timing attack), KHONG BAO GIO tu viet mot phep so sanh chuoi thuong.
- KHONG BAO GIO log/tra ve `hub.secret`/gia tri `X-Hub-Signature` — xem
  `secret_redaction.py::SECRET_KEY_NAMES`.
"""

from __future__ import annotations

import hmac
import re
import secrets
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import quote

import httpx
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from server.animation_domain import parse_youtube_id

HUB_URL = "https://pubsubhubbub.appspot.com/subscribe"
#: YouTube thuong cap ~5 ngay bat ke gia tri xin — van gui de "xin" theo
#: dung dac ta, hub co quyen bo qua/tu dat lai (xem `hub.lease_seconds`
#: trong phan hoi xac minh, LUON la nguon su that, khong phai gia tri xin).
DEFAULT_LEASE_SECONDS_REQUEST = 432000
REQUEST_TIMEOUT = 15.0
#: Gioi han THAN thong bao POST — mot thong bao that chi vai video, vai KB
#: la du du dai. Chan truoc khi phan tich de tranh DoS qua payload khong lo.
MAX_NOTIFICATION_BYTES = 256 * 1024

_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")

_NS_ATOM = "http://www.w3.org/2005/Atom"
_NS_YT = "http://www.youtube.com/xml/schemas/2015"
_NS_TOMBSTONE = "http://purl.org/atompub/tombstones/1.0"


class WebSubConfigError(RuntimeError):
    """Chua cau hinh `YOUTUBE_WEBSUB_CALLBACK_BASE_URL` — tang tren (route)
    doi thanh 503 "chưa cấu hình", cung mau voi `YouTubeConfigError`."""


class WebSubError(RuntimeError):
    """Loi goi hub (subscribe/unsubscribe that bai) — thong diep AN TOAN,
    khong bao gio chua `hub.secret`."""


class WebSubParseError(RuntimeError):
    """Than thong bao qua lon, khong phai XML, hoac XML mang du hieu tan
    cong (entity/DTD/external reference) — tu choi TRUOC khi xu ly gi ca."""


def build_topic_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={quote(channel_id)}"


def build_callback_url(base_url: str, source_id: str) -> str:
    """
    URL callback RIENG cho TUNG nguon (khuyen nghi cua dac ta WebSub: callback
    nen "kho doan", khong dung chung mot URL cho moi dang ky) — `source_id`
    trong query giup route `/api/youtube/websub` biet NGAY thong bao/xac minh
    nay thuoc nguon nao ma khong can doan tu noi dung (xem
    `TrustedSourceService.handle_websub_notification`).
    """
    return f"{base_url.rstrip('/')}/api/youtube/websub?source_id={quote(source_id)}"


def new_secret() -> str:
    """Bi mat HMAC ngau nhien cho MOT dang ky — sinh MOI moi lan dang ky/gia
    han, khong bao gio tai su dung giua cac nguon."""
    return secrets.token_urlsafe(32)


class WebSubClient:
    """Mot client dung lai cho MOI request subscribe/unsubscribe."""

    def __init__(self, hub_url: str = HUB_URL):
        self._hub_url = hub_url
        self._client: Optional[httpx.Client] = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=REQUEST_TIMEOUT)
        return self._client

    def _goi(self, data: dict) -> None:
        try:
            resp = self._http().post(self._hub_url, data=data)
        except httpx.HTTPError as exc:
            raise WebSubError("Không kết nối được hub PubSubHubbub.") from exc
        # Hub tra 202/204/200 khi CHAP NHAN yeu cau — xac minh THAT xay ra
        # KHONG DONG BO qua mot GET rieng toi callback (xem
        # `TrustedSourceService.handle_websub_verification`), 2xx o day
        # KHONG dong nghia "da dang ky xong".
        if resp.status_code >= 300:
            raise WebSubError(
                f"Hub từ chối yêu cầu (HTTP {resp.status_code}).")

    def subscribe(self, *, channel_id: str, callback_url: str, secret: str,
                 lease_seconds: int = DEFAULT_LEASE_SECONDS_REQUEST) -> None:
        self._goi({
            "hub.mode": "subscribe",
            "hub.topic": build_topic_url(channel_id),
            "hub.callback": callback_url,
            "hub.secret": secret,
            "hub.lease_seconds": str(max(1, lease_seconds)),
        })

    def unsubscribe(self, *, channel_id: str, callback_url: str) -> None:
        self._goi({
            "hub.mode": "unsubscribe",
            "hub.topic": build_topic_url(channel_id),
            "hub.callback": callback_url,
        })


@dataclass
class NotificationEntry:
    """Mot video MOI/DA CAP NHAT trong thong bao — CHI la GOI Y de tra cuu
    THAT qua YouTube Data API, KHONG BAO GIO tin day la du lieu cuoi cung
    (xem `TrustedSourceService._xu_ly_mot_video_websub`)."""

    video_id: str
    channel_id: str
    title: str = ""
    published_at: str = ""
    updated_at: str = ""


@dataclass
class DeletedEntry:
    """Mot video da bi go/rieng tu, bao qua `at:deleted-entry` (dinh dang
    AtomPub Tombstones)."""

    video_id: str
    channel_id: str = ""


@dataclass
class ParsedNotification:
    entries: List[NotificationEntry] = field(default_factory=list)
    deleted: List[DeletedEntry] = field(default_factory=list)


def _van_ban_con(el, tag: str) -> str:
    con = el.find(tag)
    return (con.text or "").strip() if con is not None else ""


def parse_notification(body: bytes) -> ParsedNotification:
    """
    Phan tich AN TOAN mot than thong bao POST tu hub. Nem `WebSubParseError`
    voi thong diep AN TOAN (khong lap lai noi dung tho) neu qua lon, khong
    phai XML hop le, hoac XML mang dau hieu tan cong.
    """
    if len(body) > MAX_NOTIFICATION_BYTES:
        raise WebSubParseError(
            f"Thân thông báo vượt giới hạn {MAX_NOTIFICATION_BYTES} byte.")
    try:
        root = SafeET.fromstring(body)
    except DefusedXmlException as exc:
        raise WebSubParseError(
            "XML bị từ chối vì có dấu hiệu tấn công (entity/DTD/tham chiếu ngoài).") from exc
    except Exception as exc:  # bao gom ET.ParseError va cac loi cu phap khac
        raise WebSubParseError("Không đọc được XML — tài liệu không hợp lệ.") from exc

    ket_qua = ParsedNotification()
    for entry in root.findall(f"{{{_NS_ATOM}}}entry"):
        video_id_tho = _van_ban_con(entry, f"{{{_NS_YT}}}videoId")
        channel_id_tho = _van_ban_con(entry, f"{{{_NS_YT}}}channelId")
        video_id = parse_youtube_id(video_id_tho)
        if not video_id or not _CHANNEL_ID_RE.match(channel_id_tho):
            continue  # khong dung dinh dang mong doi — bo qua, khong doan.
        ket_qua.entries.append(NotificationEntry(
            video_id=video_id, channel_id=channel_id_tho,
            title=_van_ban_con(entry, f"{{{_NS_ATOM}}}title"),
            published_at=_van_ban_con(entry, f"{{{_NS_ATOM}}}published"),
            updated_at=_van_ban_con(entry, f"{{{_NS_ATOM}}}updated"),
        ))

    for xoa in root.findall(f"{{{_NS_TOMBSTONE}}}deleted-entry"):
        ref = str(xoa.get("ref") or "")
        # Dang "yt:video:VIDEO_ID".
        video_id_tho = ref.rsplit(":", 1)[-1] if ":" in ref else ref
        video_id = parse_youtube_id(video_id_tho)
        if not video_id:
            continue
        by = xoa.find(f"{{{_NS_TOMBSTONE}}}by")
        channel_uri = _van_ban_con(by, f"{{{_NS_ATOM}}}uri") if by is not None else ""
        channel_id = channel_uri.rstrip("/").rsplit("/", 1)[-1] if channel_uri else ""
        ket_qua.deleted.append(DeletedEntry(
            video_id=video_id,
            channel_id=channel_id if _CHANNEL_ID_RE.match(channel_id) else ""))

    return ket_qua


def compute_signature(secret: str, body: bytes, *, algo: str = "sha1") -> str:
    """`algo=hexdigest` — dinh dang `X-Hub-Signature` theo dac ta WebSub."""
    return f"{algo}={hmac.new(secret.encode('utf-8'), body, algo).hexdigest()}"


def verify_signature(secret: str, body: bytes, header_value: str) -> bool:
    """
    Xac minh `X-Hub-Signature`. KHONG BAO GIO nem loi — tra `False` cho MOI
    truong hop khong hop le (thieu header, sai dinh dang, thuat toan la,
    khong khop) de tang tren luon co the xu ly dong nhat (tu choi am tham,
    xem `TrustedSourceService.handle_websub_notification`).
    """
    if not secret or not header_value or "=" not in header_value:
        return False
    algo, _, chu_ky = header_value.partition("=")
    algo = algo.strip().lower()
    if algo not in ("sha1", "sha256", "sha384", "sha512"):
        return False
    chu_ky = chu_ky.strip().lower()
    # `hmac.compare_digest` NEM `TypeError` neu MOT trong hai chuoi co ky tu
    # ngoai ASCII — mot header tu INTERNET co the chua bat ky gi. Kiem dinh
    # dang hex TRUOC (ASCII, chi 0-9a-f) de dam bao `compare_digest` luon
    # nhan duoc dau vao hop le, giu dung loi hua "khong bao gio nem loi".
    if not re.fullmatch(r"[0-9a-f]+", chu_ky):
        return False
    try:
        ky_vong = hmac.new(secret.encode("utf-8"), body, algo).hexdigest()
    except ValueError:
        return False
    return hmac.compare_digest(ky_vong, chu_ky)
