"""
Mo hinh du lieu cho Animation (V6, overnight Phase 5) — nen tang XEM, doc lap
voi Truyen (doc) va Audio (nghe).

QUAN HE VOI NOVEL: `related_novel_id` la MOT LIEN KET TUY CHON, khong phai
khoa ngoai bat buoc. Mot series animation KHONG PHAI la ban chuyen the cua
mot truyen — no la mot san pham RIENG, va lien ket chi ton tai khi tac gia
CHU DONG gan (vi du "animation nay dua tren truyen X cua toi").

NGUON VIDEO: giai doan nay CHI co `YOUTUBE` — nhung episode/duong dan phia
sau danh san cho `NATIVE`/`GOOGLE_DRIVE_PRIVATE`/`CLOUDFLARE_STREAM` (xem
`AnimationSource`) de khong phai doi lai kien truc luu tru khi cac nguon do
duoc trien khai that. KHONG tai/luu/proxy video cua ai ca — moi thu chi la
metadata tro toi noi video that su nam (YouTube).

Module nay la Python thuan, cung quy uoc voi `server/domain.py`: khong
FastAPI, khong Qt, khong mang.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from server.domain import ContentState, PublishState, new_id, now_iso


class AnimationSource(str, Enum):
    """
    Noi video that su duoc luu tru/phat.

    Chi `YOUTUBE` duoc TRIEN KHAI giai doan nay. Ba gia tri con lai la
    KIEN TRUC DANH SAN (Phan 5A) — chua co duong tao episode nao gan duoc
    chung, chung ton tai de schema/enum khong phai doi khi tinh nang that
    duoc them sau nay.
    """

    YOUTUBE = "youtube"
    #: Danh san. Upload goc len kho cua Fanfic — CHUA lam giai doan nay.
    NATIVE = "native"
    #: Danh san. Video rieng tren Google Drive cua tac gia — CHUA lam.
    GOOGLE_DRIVE_PRIVATE = "google_drive_private"
    #: Danh san. Cloudflare Stream — CHUA lam.
    CLOUDFLARE_STREAM = "cloudflare_stream"


#: ID video YouTube: 11 ky tu, chu/so/gach ngang/gach duoi. Xem `parse_youtube_id`.
_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

#: Cac ten mien YouTube hop le. `-nocookie` la dang FanFic dung de NHUNG (xem
#: `AnimationEpisode.embed_url`) nhung nguoi dung co the dan link tu dang do.
_YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "youtube-nocookie.com", "www.youtube-nocookie.com",
    "youtu.be", "www.youtu.be",
}


def parse_youtube_id(raw: str) -> Optional[str]:
    """
    Rut ID video 11 ky tu tu MOI dang URL YouTube pho bien, hoac tu chinh ID.

    Ho tro: `youtube.com/watch?v=ID`, `youtu.be/ID`, `youtube.com/embed/ID`,
    `youtube.com/shorts/ID`, `youtube-nocookie.com/embed/ID`, va ID TRAN (khi
    nguoi dung dan thang 11 ky tu). Tra `None` neu khong doc duoc — nguoi goi
    KHONG duoc doan hay cat bot mot chuoi khong khop, vi mot ID sai se nhung
    nham video cua nguoi khac.

    KHONG BAO GIO tai/goi mang toi YouTube o day — day chi la phan tich CHUOI,
    dung `urlparse`/`parse_qs` cua thu vien chuan. Video that duoc nhung o
    trinh duyet nguoi xem qua iframe (xem `AnimationEpisode.embed_url`).
    """
    if not raw:
        return None
    candidate = raw.strip()
    if _YOUTUBE_ID_RE.match(candidate):
        return candidate

    try:
        parsed = urlparse(candidate if "//" in candidate else f"//{candidate}")
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        return None

    if host in ("youtu.be", "www.youtu.be"):
        vid = parsed.path.strip("/").split("/")[0]
        return vid if _YOUTUBE_ID_RE.match(vid) else None

    path_parts = [p for p in parsed.path.split("/") if p]
    if path_parts and path_parts[0] in ("embed", "shorts", "live") and len(path_parts) > 1:
        vid = path_parts[1]
        return vid if _YOUTUBE_ID_RE.match(vid) else None

    query = parse_qs(parsed.query or "")
    vid_list = query.get("v") or []
    if vid_list and _YOUTUBE_ID_RE.match(vid_list[0]):
        return vid_list[0]
    return None


@dataclass
class AnimationSeries:
    """
    Mot series animation — tuong duong `Novel` nhung cho san pham XEM.

    `related_novel_id` RONG = khong lien ket (mac dinh). Xem docstring dau
    module ve vi sao day la lien ket TUY CHON, khong phai khoa ngoai bat buoc.
    """

    owner_id: str
    title: str
    description: str = ""
    cover_key: Optional[str] = None
    state: PublishState = PublishState.DRAFT
    tags: List[str] = field(default_factory=list)
    related_novel_id: str = ""
    #: Kiem duyet (Phase 4, Admin Control Center V2) — TACH BACH voi `state`
    #: o tren. `state` la truc XUAT BAN cua CHU SO HUU (draft/published, ho
    #: tu doi duoc qua `/api/animation/series/{id}/publish|unpublish`).
    #: `moderation_state` la truc GO XUONG cua QUAN TRI — cung khai niem voi
    #: `Post`/`Comment` (xem `ContentState`), CHU SO HUU KHONG doi duoc truong
    #: nay qua bat ky route nao cua ho. Neu chu so huu tu bam "Xuat ban" lai
    #: sau khi bi go, series VAN an vi `moderation_state` con la REMOVED —
    #: mot lan go xuong khong the bi hoan tac boi chinh nguoi bi go.
    #:
    #: Mac dinh VISIBLE: MOI series da ton tai truoc Phase 4 (schema chua co
    #: cot nay) duoc doc thanh VISIBLE, giu nguyen hien trang cong khai.
    moderation_state: ContentState = ContentState.VISIBLE
    #: user_id cua nguoi go xuong. Rong = chua bi go (hoac da duoc phuc hoi).
    removed_by: str = ""
    #: Ly do go xuong — hien duoc cho quan tri xem lai, KHONG ra API cong khai.
    removed_reason: str = ""
    series_id: str = field(default_factory=lambda: new_id("ani"))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "series_id": self.series_id,
            "owner_id": self.owner_id,
            "title": self.title,
            "description": self.description,
            "cover_key": self.cover_key,
            "state": self.state.value,
            "tags": list(self.tags),
            "related_novel_id": self.related_novel_id,
            "moderation_state": self.moderation_state.value,
            "removed_by": self.removed_by,
            "removed_reason": self.removed_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class AnimationEpisode:
    """
    Mot tap trong mot series — tuong duong `Chapter`.

    `source` luon la `AnimationSource.YOUTUBE` giai doan nay (xem docstring
    dau module). `external_id` la ID YouTube 11 ky tu DA CHUAN HOA qua
    `parse_youtube_id` — KHONG BAO GIO luu URL tho: hai URL khac nhau (co/khong
    tham so playlist, dang `youtu.be` hay `watch?v=`) co the cung tro toi MOT
    video, va luu tho se lam trung lap am tham khong bi phat hien.
    """

    series_id: str
    owner_id: str
    title: str
    external_id: str
    source: AnimationSource = AnimationSource.YOUTUBE
    order_index: int = 1
    state: PublishState = PublishState.DRAFT
    #: Giay — TUY CHON, do frontend ghi lai tu YouTube IFrame API sau lan phat
    #: dau (xem Phan 5I). `0` = chua biet, giao dien KHONG bia mot con so.
    duration_seconds: float = 0.0
    #: Kiem duyet (Phase 4) — CUNG khai niem voi `AnimationSeries.moderation_state`
    #: (xem docstring o do). `state` (PublishState) o tren HIEN TAI khong gac
    #: hien thi cong khai nao ca (hien thi mot tap phu thuoc TOAN BO vao trang
    #: thai series cha, xem `_may_read_series`/`AppwriteAnimationStore.
    #: _owner_permissions`) — day la truc RIENG, that su co hieu luc, danh
    #: cho quan tri go/phuc hoi TUNG TAP ma khong dong toi ca series.
    moderation_state: ContentState = ContentState.VISIBLE
    removed_by: str = ""
    removed_reason: str = ""
    #: Thuoc tinh nguon (Trusted Channels ingestion) — RONG cho tap tao qua
    #: luong thu cong thuong (khong tu nguon tin cay). Dien boi
    #: `TrustedSourceService` luc tao tap tu mot `VideoImport` (ca duong
    #: auto-import/auto-publish lan duong "Nhap" thu cong), lay THANG tu
    #: YouTube Data API — KHONG BAO GIO tu nguoi dung go tay, tranh gia mao
    #: nguon. Dung de hien "Nguon: <ten kenh>" canh trinh phat — KHONG dung
    #: de xac thuc/phan quyen bat cu dieu gi.
    source_channel_id: str = ""
    source_channel_title: str = ""
    episode_id: str = field(default_factory=lambda: new_id("anep"))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "series_id": self.series_id,
            "owner_id": self.owner_id,
            "title": self.title,
            "source": self.source.value,
            "external_id": self.external_id,
            "order_index": self.order_index,
            "state": self.state.value,
            "duration_seconds": self.duration_seconds,
            "moderation_state": self.moderation_state.value,
            "removed_by": self.removed_by,
            "removed_reason": self.removed_reason,
            "source_channel_id": self.source_channel_id,
            "source_channel_title": self.source_channel_title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
