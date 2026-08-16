"""
Mo hinh du lieu cho Trusted Video Sources (Phase 5, Admin Control Center V2 /
Animation Phan B).

BA thuc the, mot chuoi: `TrustedSource` (mot kenh/playlist YouTube duoc quan
tri XAC NHAN la dang tin cay) -> `SeriesMapping` (anh xa MOT nguon toi MOT
`AnimationSeries` da co san, kem bo loc alias/tu khoa) -> `VideoImport` (mot
video YouTube phat hien duoc, da phan loai, cho quan tri duyet/nhap).

KHONG co duong tu dong: mot video do TAC GIA THUONG nop (qua luong tao tap
binh thuong) khong bao gio tu bien kenh cua ho thanh "tin cay" — do LUON la
mot quyet dinh quan tri rieng, xem `TrustedSource.created_by`.

Module nay la Python thuan, cung quy uoc voi `animation_domain.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from server.domain import new_id, now_iso


def video_import_id(youtube_video_id: str) -> str:
    """
    `import_id` TAT DINH tu ID video YouTube — dung LAM CA `VideoImport.
    import_id` LAN `documentId` that tren Appwrite (xem
    `AppwriteTrustedSourceStore.create_import_once`), de hai gia tri nay
    KHONG BAO GIO lech nhau. Day la co so de "quet idempotent": quet lai
    cung mot video luon tro ve DUNG mot hang, khong tao ban thu hai.
    """
    return f"vimp_{youtube_video_id}"


class TrustedSourceType(str, Enum):
    """
    Chi `YOUTUBE_*` duoc TRIEN KHAI giai doan nay (Phase 5 — chi YouTube Data
    API, KHONG scrape HTML, KHONG tai/luu lai video). Hai gia tri
    `DIRECT_*` la KIEN TRUC DANH SAN cho nguon video KHONG qua YouTube (vd
    host rieng) — chua co duong tao/quet nao gan duoc chung.
    """

    YOUTUBE_CHANNEL = "youtube_channel"
    YOUTUBE_PLAYLIST = "youtube_playlist"
    YOUTUBE_VIDEO = "youtube_video"
    DIRECT_HLS = "direct_hls"
    DIRECT_MP4 = "direct_mp4"


class SubscriptionStatus(str, Enum):
    """
    Trang thai dang ky WebSub (PubSubHubbub) — CAC TRUONG NAY TON TAI TU
    Phase 5 nhung CHUA co logic dang ky that nao ca (xem Phase 6). Gia tri
    mac dinh `NONE` nghia la "chua tung thu dang ky".
    """

    NONE = "none"
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    FAILED = "failed"


class ImportStatus(str, Enum):
    """
    Vong doi cua MOT video duoc phat hien, tu luc thay no toi luc no thanh
    (hoac khong thanh) mot `AnimationEpisode` that.

    `NEW` = da phat hien nhung KHONG khop bat ky series nao (khong co alias
    nao trung) — quan tri phai tu gan series bang tay neu muon nhap.
    `PENDING` = co series khop nhung do tin cay CHUA du nguong de tu dong,
    cho quan tri duyet bang tay.
    `AUTO_IMPORTED`/`AUTO_PUBLISHED` = HE THONG tu nhap trong luc quet (do
    tin cay du nguong VA nguon/anh xa bat auto_import/auto_publish) — Phase
    5 CHUA co WebSub nen day chi xay ra qua nut "Quet video co san" thu cong,
    khong phai tu dong hoan toan.
    `IMPORTED` = quan tri bam Nhap bang tay (khong qua co che auto).
    `REJECTED` = quan tri tu choi ro rang (vi du sai series).
    `IGNORED` = bi loai boi tu khoa loai tru (trailer/teaser/...) luc quet,
    HOAC quan tri chu dong bo qua — van GIU LAI de xem lai, khong xoa am tham.
    `DUPLICATE` = video nay DA la mot AnimationEpisode that (trung
    `external_id`) roi — khong tao them ban thu hai.
    `CONFLICT` = so tap phat hien DA co mot video KHAC chiem trong series do
    — can quan tri tu giai quyet (doi so hoac tu choi), KHONG ghi de am
    tham.
    `UNAVAILABLE` = video khong con truy cap duoc qua YouTube Data API
    (bi go/rieng tu) luc quet lai.
    `FAILED` = loi ky thuat luc goi YouTube API hoac phan loai.
    """

    NEW = "new"
    PENDING = "pending"
    AUTO_IMPORTED = "auto_imported"
    AUTO_PUBLISHED = "auto_published"
    IMPORTED = "imported"
    REJECTED = "rejected"
    IGNORED = "ignored"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass
class TrustedSource:
    source_type: TrustedSourceType = TrustedSourceType.YOUTUBE_CHANNEL
    #: ID kenh YouTube (vd "UCxxxxxxxx...") — RONG neu `source_type` la
    #: playlist/video don le khong gan voi mot kenh duoc theo doi rong hon.
    youtube_channel_id: str = ""
    #: ID playlist YouTube — CHI dien khi `source_type == YOUTUBE_PLAYLIST`.
    youtube_playlist_id: str = ""
    #: ID video YouTube (11 ky tu) — CHI dien khi `source_type ==
    #: YOUTUBE_VIDEO` (mot video DON LE duoc tin cay, khong gan voi ca
    #: kenh/playlist rong hon).
    youtube_video_id: str = ""
    display_name: str = ""
    #: URL anh dai dien/thumbnail — CHI luu URL cong khai YouTube tra ve,
    #: KHONG tai/luu lai anh.
    thumbnail_url: str = ""
    enabled: bool = True
    #: Tu dong PHAT HIEN video moi khi co su kien (Phase 6 - WebSub). Phase 5
    #: chi luu cai dat nay, chua co gi doc no ca.
    auto_discover: bool = False
    #: Tu dong TAO `AnimationEpisode` khi do tin cay du nguong (ca luc quet
    #: thu cong Phase 5 lan pipeline tu dong Phase 6 sau nay).
    auto_import: bool = False
    #: Tu dong danh dau tap la PUBLISHED (xem ghi chu o
    #: `TrustedSourceService.apply_import_decision` ve y nghia THAT SU cua
    #: co nay — KHONG dong nghia voi "hien cong khai ngay", vi
    #: `AnimationEpisode.state` hien khong gac hien thi nao, xem Phase 4).
    auto_publish: bool = False
    #: Nguong do tin cay (0.0-1.0) de tu dong nhap/xuat ban. Mac dinh 0.9 —
    #: cao, vi day la hanh dong TAO NOI DUNG THAT khong co con nguoi duyet.
    minimum_confidence: float = 0.9
    created_by: str = ""
    last_scan_at: str = ""
    last_success_at: str = ""
    last_error_at: str = ""
    last_error_message: str = ""
    subscription_status: SubscriptionStatus = SubscriptionStatus.NONE
    subscription_expires_at: str = ""
    #: Lan gan nhat THU dang ky/gia han (bat ke thanh cong hay khong) — khac
    #: `subscription_expires_at` (lan hub XAC NHAN). Phase 6 - WebSub.
    last_subscription_attempt_at: str = ""
    #: Lan gan nhat NHAN duoc mot thong bao POST that tu hub — dau hieu
    #: "dang ky con song", doc lap voi viec xu ly thong bao do co thanh
    #: cong hay khong. Phase 6.
    last_notification_at: str = ""
    #: Thong diep loi AN TOAN gan nhat lien quan WebSub (dang ky/gia han/xu
    #: ly thong bao That bai) — hien cho quan tri xem, KHONG BAO GIO chua
    #: bi mat. Phase 6.
    last_websub_error: str = ""
    #: Lan gan nhat doi chieu dinh ky (Phase 6, muc 9) thanh cong tim/xu ly
    #: xong danh sach video gan day — DOC LAP voi `last_scan_at` (quet thu
    #: cong tu trang chi tiet nguon).
    last_successful_sync_at: str = ""
    #: Bi mat HMAC dung de KY (luc dang ky) va XAC MINH (luc nhan thong bao)
    #: chu ky `X-Hub-Signature` cua hub — sinh ngau nhien luc dang ky, KHONG
    #: BAO GIO xuat hien trong `to_dict()` (xem docstring o do va
    #: `ProviderConnection.encrypted_secret` cung mau trong
    #: `translation_domain.py` — day la RANH GIOI AN TOAN duy nhat cho
    #: truong nay). Kho Appwrite dung ham rieng de ghi/doc, xem
    #: `appwrite_trusted_source_store.py::_nguon_thanh_hang`/`_nguon_tu_doc`.
    websub_secret: str = ""
    source_id: str = field(default_factory=lambda: new_id("tsrc"))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        """
        AN TOAN de tra ve qua API quan tri — xem docstring `websub_secret`.
        `websub_secret` CO CHU DICH khong nam trong dict nay: day la RANH
        GIOI DUY NHAT ngan bi mat that lo ra ngoai, cung nguyen tac voi
        `ProviderConnection.to_dict()` (BYOK, V5.1).
        """
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "youtube_channel_id": self.youtube_channel_id,
            "youtube_playlist_id": self.youtube_playlist_id,
            "youtube_video_id": self.youtube_video_id,
            "display_name": self.display_name,
            "thumbnail_url": self.thumbnail_url,
            "enabled": self.enabled,
            "auto_discover": self.auto_discover,
            "auto_import": self.auto_import,
            "auto_publish": self.auto_publish,
            "minimum_confidence": self.minimum_confidence,
            "created_by": self.created_by,
            "last_scan_at": self.last_scan_at,
            "last_success_at": self.last_success_at,
            "last_error_at": self.last_error_at,
            "last_error_message": self.last_error_message,
            "subscription_status": self.subscription_status.value,
            "subscription_expires_at": self.subscription_expires_at,
            "last_subscription_attempt_at": self.last_subscription_attempt_at,
            "last_notification_at": self.last_notification_at,
            "last_websub_error": self.last_websub_error,
            "last_successful_sync_at": self.last_successful_sync_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class SeriesMapping:
    """
    Anh xa MOT `TrustedSource` toi MOT `AnimationSeries` DA CO SAN — Phase 5
    KHONG tao series moi tu nguon tin cay, chi gan vao series mot tac gia
    that da tao qua luong thuong.

    MOT nguon co the co NHIEU anh xa (mot kenh dang nhieu series khac
    nhau) — luc phan loai mot video, tung anh xa duoc cham diem RIENG, xem
    `server/video_classifier.py`.
    """

    trusted_source_id: str = ""
    animation_series_id: str = ""
    #: Ten khac cua series de nhan dien trong tieu de video (khong phan
    #: biet hoa/thuong, khong phan biet dau — xem `video_classifier.chuan_hoa`).
    aliases: List[str] = field(default_factory=list)
    include_keywords: List[str] = field(default_factory=list)
    exclude_keywords: List[str] = field(default_factory=list)
    #: `None` = ke thua `TrustedSource.minimum_confidence`.
    minimum_confidence: Optional[float] = None
    auto_import: Optional[bool] = None
    auto_publish: Optional[bool] = None
    mapping_id: str = field(default_factory=lambda: new_id("smap"))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mapping_id": self.mapping_id,
            "trusted_source_id": self.trusted_source_id,
            "animation_series_id": self.animation_series_id,
            "aliases": list(self.aliases),
            "include_keywords": list(self.include_keywords),
            "exclude_keywords": list(self.exclude_keywords),
            "minimum_confidence": self.minimum_confidence,
            "auto_import": self.auto_import,
            "auto_publish": self.auto_publish,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class VideoImport:
    """MOT video YouTube phat hien duoc tu mot `TrustedSource` — xem
    `ImportStatus` de biet vong doi day du."""

    trusted_source_id: str = ""
    #: ID video YouTube (11 ky tu) — DUY NHAT trong toan he thong, xem
    #: `TrustedSourceStore.create_import_once`.
    youtube_video_id: str = ""
    title: str = ""
    channel_id: str = ""
    channel_title: str = ""
    thumbnail_url: str = ""
    #: ISO — thoi diem xuat ban TREN YOUTUBE (khac `created_at` la luc HE
    #: THONG phat hien ra no).
    published_at: str = ""
    duration_seconds: float = 0.0
    detected_mapping_id: str = ""
    detected_series_id: str = ""
    detected_episode_number: Optional[int] = None
    #: 0.0-1.0.
    confidence: float = 0.0
    #: Danh sach tin hieu DE HIEU ("khớp alias 'x'", "phát hiện tập 12",
    #: "chứa từ loại trừ: trailer") — de quan tri xem GIAI THICH duoc vi
    #: sao he thong quyet dinh nhu vay, khong phai mot con so bi an.
    signals: List[str] = field(default_factory=list)
    status: ImportStatus = ImportStatus.NEW
    #: Ly do o trang thai hien tai (vi du "trung voi tap #12 cua video khac").
    reason: str = ""
    #: `episode_id` THAT sau khi nhap thanh cong — rong neu chua nhap.
    created_episode_id: str = ""
    reviewed_by: str = ""
    reviewed_at: str = ""
    #: RONG o day CHI la gia tri khoi tao tam — kho (Mock/Appwrite) LUON ghi
    #: de bang `video_import_id(youtube_video_id)` truoc khi luu, xem
    #: docstring ham do. KHONG dua vao gia tri nay TRUOC khi qua
    #: `create_import_once`.
    import_id: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "import_id": self.import_id,
            "trusted_source_id": self.trusted_source_id,
            "youtube_video_id": self.youtube_video_id,
            "title": self.title,
            "channel_id": self.channel_id,
            "channel_title": self.channel_title,
            "thumbnail_url": self.thumbnail_url,
            "published_at": self.published_at,
            "duration_seconds": self.duration_seconds,
            "detected_mapping_id": self.detected_mapping_id,
            "detected_series_id": self.detected_series_id,
            "detected_episode_number": self.detected_episode_number,
            "confidence": self.confidence,
            "signals": list(self.signals),
            "status": self.status.value,
            "reason": self.reason,
            "created_episode_id": self.created_episode_id,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
