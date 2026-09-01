"""
Mo hinh du lieu cua nen tang web.

Thiet ke SAN cho cac tinh nang giai doan sau (draft/published, quota, tier,
lich su nghe, moderation) nhung giai doan nay CHUA trien khai thanh toan hay
he thong phap ly nao.

Module nay la Python thuan: khong FastAPI, khong Qt, khong mang.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: Khoa va moc cuoi cung da phat ra, cho `now_iso_us`.
_moc_lock = threading.Lock()
_moc_cuoi: Optional[datetime] = None


def now_iso_us() -> str:
    """
    Moc thoi gian den MICRO GIAY, va TANG NGHIEM NGAT trong mot tien trinh.

    Dung cho moi ban ghi duoc doc theo THU TU: nhat ky kiem duyet, bai dang,
    binh luan, thong bao. `now_iso()` cat o giay, va hai bai dang trong cung
    mot giay se co cung moc — luc do thu tu tuy thuoc vao phep sap xep, va no
    co the ke nguoc cau chuyen.

    HAI dieu o ham nay khong hien nhien, va ca hai deu duoc mot bai test do ra:

    1. `timespec="microseconds"` — DAT TUONG MINH, khong dung mac dinh.

       `datetime.isoformat()` BO phan thap phan khi `microsecond == 0`. Luc do
       mot moc thanh "12:00:00+00:00" ben canh "12:00:00.500000+00:00", va so
       sanh CHUOI dat chung nguoc thu tu: '+' (0x2B) nho hon '.' (0x2E). Mot
       ban ghi roi dung vao micro giay tron se nhay len dau danh sach.

    2. TANG NGHIEM NGAT — moc moi luon lon hon moc truoc.

       Hai ban ghi tao trong CUNG mot micro giay (chuyen thuong xay ra tren kho
       trong bo nho, noi khong co do tre mang) se co moc GIONG NHAU, va luc do
       thu tu roi ve phep pha the — mot `post_id` sinh ngau nhien. Ket qua la
       ba binh luan hien ra theo mot thu tu ngau nhien, khong phai thu tu chung
       duoc viet. Da do duoc bang test truoc khi ai kip doc nham.

       Chi dam bao trong MOT tien trinh. Hai tien trinh cung ghi (uvicorn +
       worker) van co the trung moc, va luc do thu tu la tuy y — dieu do chap
       nhan duoc: hai su kien cach nhau duoi mot micro giay thi khong co "truoc"
       va "sau" nao co y nghia voi nguoi doc.

    Cac ban ghi KHONG duoc doc theo thu tu (ho so, truyen, chuong) giu
    `now_iso()`: chung khong can, va moc ngan thi de doc hon khi go loi.
    """
    global _moc_cuoi
    with _moc_lock:
        moc = datetime.now(timezone.utc)
        if _moc_cuoi is not None and moc <= _moc_cuoi:
            moc = _moc_cuoi + timedelta(microseconds=1)
        _moc_cuoi = moc
    return moc.isoformat(timespec="microseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


#: Gia tri thay cho van ban NHAN DANG cua mot tai khoan DA XOA, o nhung hang
#: PHAI o lai vi ly do kiem toan — `author_applications` (lich su quyet dinh
#: cua nguoi duyet) va `content_reports` (bang chung ve nguoi BI bao cao).
#:
#: MOT hang so duy nhat, khong phai mot chuoi go lai o moi cho: hai tang kho
#: (mock/Appwrite) phai ghi DUNG cung mot gia tri, neu khong bo test hop dong
#: se xanh o mock roi lech o that. Xem `MetadataStore.delete_account`.
AN_DANH_DA_XOA = "[tài khoản đã xoá]"

#: Cac bang ma `MetadataStore.delete_account` bao cao lai so hang da don.
#:
#: Khai o day, KHONG o tung kho: hai ban hien thuc phai tra ve DUNG cung hinh
#: dang, va bo test hop dong (`test_account_deletion.py`) so sanh truc tiep hai
#: dict do. Mot ban tu them/bo mot khoa la mot lech khong ai thay ngay.
BANG_XOA_TAI_KHOAN = (
    "novels", "chapters", "tts_jobs", "audio_tracks",
    "posts", "comments", "post_likes",
    "user_follows", "story_follows", "notifications",
    "author_stats", "listen_credits",
    # Hai bang GIU HANG, chi an danh — dem de nguoi van hanh doi soat duoc.
    "applications_anonymized", "reports_anonymized",
)


def bao_cao_xoa_tai_khoan() -> Dict[str, Any]:
    """Ban ghi ket qua RONG cho `MetadataStore.delete_account`.

    `object_keys` la khoa doi tuong trong kho tep MA NGUOI GOI phai xoa — kho
    metadata khong biet gi ve R2."""
    bc: Dict[str, Any] = {ten: 0 for ten in BANG_XOA_TAI_KHOAN}
    bc["object_keys"] = []
    return bc


# -----------------------------------------------------------------------------
# Enum
# -----------------------------------------------------------------------------


class PublishState(str, Enum):
    """Da chuan bi cho luong xuat ban, giai doan nay chi dung DRAFT/PUBLISHED."""

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class PublicationMode(str, Enum):
    """Che do xuat ban cua MOT `Novel` — xem mission "Anime Fanfic Production
    Canary": khi nguon KHONG the hien ro quyen tai xuat ban toan van (vd
    FanFiction.net chi cho "use=reference" trong robots.txt), Novel van duoc
    tao that nhung KHONG chua noi dung chuong day du — chi metadata + link
    tro ve nguon goc. `Chapter` cho mot Novel `METADATA_ONLY` la RONG hoac
    khong ton tai — dung `external_chapter_count` de biet do dai that."""

    FULL_TEXT = "full_text"
    METADATA_ONLY = "metadata_only"


class NovelStatus(str, Enum):
    """Trang thai hoan thanh cua mot `Novel`: dang viet (ongoing), da hoan
    thanh (completed), hoac tam ngung (hiatus). Dung cho discovery taxonomy
    va bo loc tim kiem truyen."""

    ONGOING = "ongoing"
    COMPLETED = "completed"
    HIATUS = "hiatus"


class Tier(str, Enum):
    """Cac goi du kien. CHUA co thanh toan trong giai doan nay."""

    FREE = "free"
    LISTENER_PRO = "listener_pro"
    CREATOR_PRO = "creator_pro"
    ULTRA = "ultra"


class AuthorStatus(str, Enum):
    """
    Duoc phep XUAT BAN cong khai hay khong. Day la moderation, KHONG phai uy tin.

    `none` la mac dinh cua moi nguoi dung moi: ho van viet va sua ban nhap duoc,
    chi khong dua truyen ra cong khai duoc. Xem `server/creator.py` de biet bang
    cac buoc chuyen hop le va vi sao khong co buoc `none -> approved`.
    """

    NONE = "none"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class AdminRole(str, Enum):
    """
    Ba muc quan tri (Admin Control Center V2, feature/admin-trusted-video-v2).

    KE THUA triet ly cua `Settings.admin_user_ids`: van la BIEN MOI TRUONG,
    khong phai cot du lieu — ba danh sach rieng (`FAS_OWNER_USER_IDS`,
    `FAS_ADMIN_USER_IDS`, `FAS_MODERATOR_USER_IDS`) thay vi mot, nen khong co
    duong ghi API nao leo thang duoc. Xem `Settings.admin_role_of`.

    NONE khong phai mot "vai tro" that su — no la gia tri tra ve khi user_id
    khong nam trong ca ba danh sach, dung de cac ham kiem tra so sanh dong
    nhat (`role != AdminRole.NONE` thay vi kiem `Optional[AdminRole]`).
    """

    NONE = "none"
    MODERATOR = "moderator"
    ADMIN = "admin"
    OWNER = "owner"


class ContentState(str, Enum):
    """
    Noi dung do nguoi dung tao con hien hay da bi go.

    KHONG co `deleted` o day. Kiem duyet dung `REMOVED` — hang van con, chi
    khong hien ra nua. Ly do: mot thao tac xoa that lam mat luon bang chung cua
    chinh viec kiem duyet do, va khi mot quyet dinh bi khieu nai thi khong con
    gi de xem lai. Xoa THAT chi xay ra khi CHINH CHU xoa bai cua minh.
    """

    VISIBLE = "visible"
    REMOVED = "removed"


class PostKind(str, Enum):
    """
    Bai thuong hay thong bao cua tac gia ve mot truyen.

    `STORY_UPDATE` chi tac gia DA DUYET moi dang duoc, va no gan voi mot truyen
    cu the — giao dien hien kem the truyen do.
    """

    POST = "post"
    STORY_UPDATE = "story_update"


class NotificationKind(str, Enum):
    """
    Loai thong bao. Chuoi ON DINH: chung di vao API, vao khoa chong lap, va vao
    test. Doi mot chuoi o day la lam mat khoa chong lap cua nhung thong bao da
    ton tai, nen dung doi.
    """

    FOLLOW = "follow"
    POST_LIKE = "post_like"
    POST_COMMENT = "post_comment"
    COMMENT_REPLY = "comment_reply"
    STORY_CHAPTER = "story_chapter"
    #: Co nguoi binh luan vao mot CHUONG cua minh (V3 — binh luan audio).
    CHAPTER_COMMENT = "chapter_comment"
    AUTHOR_APPROVED = "author_approved"
    AUTHOR_REJECTED = "author_rejected"
    #: Co nguoi binh luan vao mot TAP animation cua minh (V6, overnight Phase 5).
    EPISODE_COMMENT = "episode_comment"


class ReportReason(str, Enum):
    SPAM = "spam"
    HARASSMENT = "harassment"
    INAPPROPRIATE = "inappropriate"
    COPYRIGHT = "copyright"
    OTHER = "other"


class ReportStatus(str, Enum):
    """
    Vong doi cua mot bao cao.

    `OPEN` -> `RESOLVED` (da xu ly, co the da go noi dung) hoac `DISMISSED`
    (da xem, khong vi pham). Khong co duong quay lai `OPEN`: mot bao cao da
    duoc mot nguoi that doc xong thi khong tu mo lai.
    """

    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.COMPLETED, JobStatus.FAILED)


# -----------------------------------------------------------------------------
# Ban ghi
# -----------------------------------------------------------------------------


@dataclass
class Profile:
    user_id: str
    email: str
    display_name: str = ""
    tier: Tier = Tier.FREE
    #: Han muc - theo doi san, CHUA tru quota that trong MVP.
    listened_minutes: int = 0
    tts_characters_used: int = 0
    created_at: str = field(default_factory=now_iso)
    #: Ten CONG KHAI, dang chuan (xem `creator.validate_username`). Chuoi rong =
    #: chua chon. Nguoi chua chon thi KHONG co trang cong khai — ta khong tu gan
    #: cho ho mot cai ten lay tu email.
    username: str = ""
    #: Gioi thieu ngan, hien tren trang cong khai.
    bio: str = ""
    #: Moderation. Xem `AuthorStatus`.
    author_status: AuthorStatus = AuthorStatus.NONE
    #: Khoa doi tuong anh dai dien trong R2 (`server.social.object_key("avatar", ...)`).
    #: Chuoi rong = chua tai — giao dien lui ve chu cai dau ten. KHONG PHAI url:
    #: url ky (het han) duoc tinh luc tra ve, tu khoa nay — xem `_ho_so_tra_ve`
    #: va `CreatorService._public_bundle`.
    avatar_key: str = ""
    #: "Tiep tuc doc/nghe" (V4 visual completion) — CON TRO DUY NHAT toi noi
    #: dang do dang, khong phai lich su. Moi lan ghi de lan truoc: y muon la
    #: "quay lai cho gan nhat", khong phai danh sach moi truyen dang do dang.
    #: Rong = chua co gi de tiep tuc — giao dien AN module, khong bia du lieu.
    last_read_novel_id: str = ""
    last_read_chapter_id: str = ""
    last_read_at: str = ""
    last_listen_novel_id: str = ""
    last_listen_chapter_id: str = ""
    #: Giay, TU CLIENT gui len — chi de hien thi vi tri tren thanh tien do, KHONG
    #: dung lam can cu tinh uy tin (xem `creator.evaluate_listen`, doc do lay tu
    #: track o may chu). Sai lech vai giay o day chi lam gach tien do hoi le,
    #: khong anh huong gi khac.
    last_listen_position_seconds: float = 0.0
    last_listen_at: str = ""
    #: "Tiep tuc xem" (V6, overnight Phase 5) — CUNG mau voi last_listen_*:
    #: con tro DUY NHAT, khong phai lich su. Xem docstring cua last_listen_*.
    last_watch_series_id: str = ""
    last_watch_episode_id: str = ""
    last_watch_position_seconds: float = 0.0
    #: Do dai TAP dang xem, giay — GHEP VAO luc ghi tien do (client gui,
    #: xem `/api/progress/watch`) de trang chu hien "12:03 / 24:00" ma khong
    #: phai hoi lai YouTube. `0` = chua biet.
    last_watch_duration_seconds: float = 0.0
    last_watch_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """
        Hinh dang RIENG TU — chi tra ve cho chinh chu qua `/api/auth/me`.

        Co `email` va `author_status` o day. Ban CONG KHAI di qua
        `creator.public_profile()`, va do la mot danh sach cho phep rieng.
        """
        return {
            "user_id": self.user_id,
            "email": self.email,
            "display_name": self.display_name or self.email.split("@")[0],
            "tier": self.tier.value,
            "listened_minutes": self.listened_minutes,
            "tts_characters_used": self.tts_characters_used,
            "created_at": self.created_at,
            "username": self.username,
            "bio": self.bio,
            "author_status": self.author_status.value,
            "avatar_key": self.avatar_key,
            "last_read_novel_id": self.last_read_novel_id or None,
            "last_read_chapter_id": self.last_read_chapter_id or None,
            "last_read_at": self.last_read_at or None,
            "last_listen_novel_id": self.last_listen_novel_id or None,
            "last_listen_chapter_id": self.last_listen_chapter_id or None,
            "last_listen_position_seconds": self.last_listen_position_seconds,
            "last_listen_at": self.last_listen_at or None,
            "last_watch_series_id": self.last_watch_series_id or None,
            "last_watch_episode_id": self.last_watch_episode_id or None,
            "last_watch_position_seconds": self.last_watch_position_seconds,
            "last_watch_duration_seconds": self.last_watch_duration_seconds or None,
            "last_watch_at": self.last_watch_at or None,
        }


@dataclass
class AuthorApplication:
    """
    Don xin lam tac gia.

    MOT don moi nguoi dung: khi nop lai sau khi bi tu choi, ban ghi nay duoc ghi
    de va `attempts` tang len. Ly do khong luu lich su nhieu don: giai doan nay
    khong co trang quan tri de doc lich su, va mot bang cu lon dan ma khong ai
    doc la mot bang no ky thuat.

    `reviewer_note` la ghi chu cua nguoi duyet. No CO hien cho nguoi nop (ho can
    biet vi sao bi tu choi de sua), nen dung viet gi vao day ma khong muon ho doc.
    """

    user_id: str
    pen_name: str
    bio: str = ""
    genres: List[str] = field(default_factory=list)
    intro: str = ""
    #: Da doc va dong y quy dinh xuat ban. Khong tich thi khong nop duoc.
    accepted_rules: bool = False
    status: AuthorStatus = AuthorStatus.PENDING
    reviewer_note: str = ""
    attempts: int = 1
    application_id: str = field(default_factory=lambda: new_id("app"))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    #: Luc nguoi duyet ra quyet dinh. Dung de tinh thoi gian cho nop lai.
    decided_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "application_id": self.application_id,
            "user_id": self.user_id,
            "pen_name": self.pen_name,
            "bio": self.bio,
            "genres": list(self.genres),
            "intro": self.intro,
            "accepted_rules": self.accepted_rules,
            "status": self.status.value,
            "reviewer_note": self.reviewer_note,
            "attempts": self.attempts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "decided_at": self.decided_at,
        }

    def to_public_dict(self) -> Dict[str, Any]:
        """
        Ban tra cho CHINH CHU don.

        Bo `user_id` va `application_id`: nguoi nop khong can hai khoa noi bo do
        de lam gi, va moi khoa lo ra la mot thu ai do co the thu doan.
        """
        data = self.to_dict()
        for khoa in ("user_id", "application_id"):
            data.pop(khoa, None)
        return data


@dataclass
class ModerationEvent:
    """
    MOT thao tac kiem duyet da xay ra. Chi ghi, khong bao gio sua.

    VI SAO CAN: cac ham duyet/treo doi trang thai cua nguoi khac, va sau ba
    thang khong ai nho duoc ai da bam, luc nao, va vi sao. Ban ghi don chi giu
    trang thai CUOI CUNG — no bi ghi de moi lan co quyet dinh moi.

    KHONG BAO GIO ra API cong khai. `note` co the chua nhan xet noi bo cua nguoi
    duyet, va `actor_id` cho biet ai dang lam quan tri.
    """

    #: Chuoi ON DINH, di vao API quan tri va vao test — vi du
    #: `author_approved`/`user_suspend`/`trusted_source_add`. Danh sach day du
    #: dang duoc CHAP NHAN nam o Appwrite enum `moderation_events.action`
    #: (`scripts/setup_appwrite.py`) — mo rong enum do khi them hanh dong moi,
    #: KHONG tu y ghi mot chuoi ngoai danh sach (Appwrite se tu choi).
    action: str
    #: Nguoi BI tac dong (vd user bi treo, hoac rong neu doi tuong khong phai
    #: mot nguoi dung — xem `target_type`/`target_id` cho truong hop do).
    target_user_id: str
    #: Nguoi THUC HIEN. Rong = he thong (vd migration grandfather).
    actor_id: str = ""
    #: Vai tro cua actor TAI THOI DIEM hanh dong (owner/admin/moderator) — vai
    #: tro co the doi sau (bien moi truong), nen ghi lai o day de nhat ky
    #: khong ke sai "ai co quyen gi luc do".
    actor_role: str = ""
    #: Loai doi tuong bi tac dong khi KHONG PHAI la user — vi du "novel",
    #: "animation_series", "trusted_source". Rong = doi tuong la user (dung
    #: `target_user_id` o tren), giu tuong thich nguoc voi du lieu cu.
    target_type: str = ""
    #: ID cua doi tuong khi `target_type` khac rong (vd series_id, source_id).
    #: Doc lap voi `target_user_id` — mot hanh dong co the co CA HAI (vi du
    #: "admin X go xuat ban series Y cua tac gia Z").
    target_id: str = ""
    note: str = ""
    #: Metadata AN TOAN, ma hoa JSON — KHONG BAO GIO chua API key/OAuth
    #: token/BYOP token/cookie/session secret/khoa ma hoa. Xem
    #: `server/secret_redaction.py` neu can loc truoc khi ghi. Rong theo
    #: mac dinh — chi dien khi hanh dong that su can ngu canh them (vi du
    #: gia tri cu/moi cua mot co toggle).
    metadata: str = ""
    event_id: str = field(default_factory=lambda: new_id("mev"))
    #: MOC THOI GIAN DAY DU, den micro giay — KHONG dung `now_iso()`.
    #:
    #: `now_iso()` cat o giay, va mot nguoi quan tri bam Duyet roi Treo trong
    #: cung mot giay se tao ra hai ban ghi CUNG moc. Luc do thu tu doc ra tuy
    #: thuoc vao phep sap xep, va nhat ky co the ke nguoc cau chuyen — "phuc hoi"
    #: hien truoc "treo". Da do duoc bang test truoc khi ai kip doc nham.
    #:
    #: Cac ban ghi khac giu `now_iso()`: chung khong duoc doc theo THU TU trong
    #: cung mot giay, con nhat ky thi co.
    #:
    #: Truoc day day la `datetime.now(timezone.utc).isoformat()` viet thang, va
    #: no mang hai bay ma `now_iso_us()` da bit lai: moc roi vao micro giay tron
    #: se mat phan thap phan (roi so sanh chuoi dat no nguoc thu tu), va hai
    #: thao tac trong cung mot micro giay se trung moc. Xem `now_iso_us`.
    created_at: str = field(default_factory=now_iso_us)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "action": self.action,
            "target_user_id": self.target_user_id,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "note": self.note,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclass
class AccountStatus:
    """
    Trang thai tai khoan NATIVE, doc THANG tu Appwrite Users API — TACH BACH
    voi `Profile.author_status` (quyen XUAT BAN, song trong `profiles`).

    `enabled=False` nghia la tai khoan bi KHOA HOAN TOAN, khong dang nhap
    duoc nua o BAT KY duong nao (email/OAuth) — khac voi treo TAC GIA, von
    chi chan xuat ban MOI va van cho dang nhap binh thuong. Hai khai niem
    nay CO Y tach rieng (Phase 3, Admin Control Center V2): mot tac gia bi
    treo van la mot doc gia binh thuong, con mot tai khoan bi khoa thi
    khong dung duoc san pham nua o bat ky vai tro nao.

    KHONG BAO GIO ghi lai vao `profiles` — day la du lieu Appwrite Auth tra
    ve TRUC TIEP moi lan hoi, khong phai mot ban sao can dong bo.
    """

    user_id: str
    email: str
    name: str
    enabled: bool
    email_verified: bool
    phone_verified: bool
    registered_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "name": self.name,
            "enabled": self.enabled,
            "email_verified": self.email_verified,
            "phone_verified": self.phone_verified,
            "registered_at": self.registered_at,
        }


@dataclass
class AccountSession:
    """
    MOT phien dang nhap, doc tu Appwrite Users API (Phase 3).

    `current` chi co y nghia khi may chu tu goi bang chinh session dang xac
    thuc request do. Moi thao tac quan tri o day goi bang API KEY (khong
    phai session cua ai ca), nen Appwrite luon tra `False` cho MOI phien —
    khong the biet "day co phai phien trinh duyet dang mo trang quan tri
    hay khong" tu goc nhin nay.
    """

    session_id: str
    provider: str
    ip: str
    os_name: str
    client_name: str
    device_name: str
    country_name: str
    current: bool
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "provider": self.provider,
            "ip": self.ip,
            "os_name": self.os_name,
            "client_name": self.client_name,
            "device_name": self.device_name,
            "country_name": self.country_name,
            "current": self.current,
            "created_at": self.created_at,
        }


@dataclass
class AuthorStats:
    """
    Ban TONG HOP cua uy tin mot tac gia.

    Vi sao can mot bang rieng thay vi dem lai tu bang su kien moi lan co ai mo
    trang: dem lai la mot phep quet toan bang cho MOI lan hien mot huy hieu. Voi
    mot tac gia co mot van lan nghe, mot trang tim kiem hien muoi tac gia se
    thanh muoi phep quet. Bang nay duoc CONG THEM mot don vi moi khi co mot lan
    nghe hop le, nen doc no la mot lan doc mot hang.

    Doi lai, no co the LECH neu mot buoc cong bi mat. `scripts/` co san mot lenh
    dung lai tu bang su kien — xem `docs/AUTHOR_RANK.md`.
    """

    user_id: str
    qualified_listens: int = 0
    published_novels: int = 0
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "qualified_listens": self.qualified_listens,
            "published_novels": self.published_novels,
            "updated_at": self.updated_at,
        }


@dataclass
class ListenCredit:
    """
    MOT lan nghe hop le da duoc tinh.

    `credit_id` la khoa TAT DINH tu (nguoi nghe, chuong, ngay UTC) — xem
    `creator.credit_key`. Chinh tinh duy nhat cua khoa la co che chong dua: hai
    request cung luc thi mot cai thang, cai kia va vao xung dot khoa.

    Bang nay la NGUON su that de dung lai `AuthorStats` khi can.
    """

    listener_id: str
    author_id: str
    chapter_id: str
    #: So thu tu ngay UTC — xem `creator.dedupe_day_bucket`.
    day_bucket: int = 0
    listened_seconds: float = 0.0
    credit_id: str = ""
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "credit_id": self.credit_id,
            "listener_id": self.listener_id,
            "author_id": self.author_id,
            "chapter_id": self.chapter_id,
            "day_bucket": self.day_bucket,
            "listened_seconds": self.listened_seconds,
            "created_at": self.created_at,
        }


@dataclass
class Novel:
    owner_id: str
    title: str
    description: str = ""
    cover_key: Optional[str] = None          # object key trong R2, khong phai binary
    state: PublishState = PublishState.DRAFT
    tags: List[str] = field(default_factory=list)
    novel_id: str = field(default_factory=lambda: new_id("nov"))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    #: `FULL_TEXT` (mac dinh, tuong thich nguoc voi moi Novel hien co) hoac
    #: `METADATA_ONLY` khi nguon khong the hien ro quyen tai xuat ban toan
    #: van — xem `PublicationMode`.
    publication_mode: PublicationMode = PublicationMode.FULL_TEXT
    #: Danh sach `Fandom.fandom_id` — List vi mot fic co the la crossover
    #: nhieu fandom (vd "Naruto + My Hero Academia").
    fandom_ids: List[str] = field(default_factory=list)
    #: Ten TAC GIA GOC tren nguon (KHONG phai `owner_id` — voi noi dung
    #: harvester, `owner_id` la `svc_harvester`, mot tai khoan he thong,
    #: khong phai nguoi viet that).
    external_author_name: str = ""
    #: Link CANONICAL tro ve dung trang nguon — bat buoc co gia tri khi
    #: `publication_mode == METADATA_ONLY` (day la ly do ton tai cua Novel
    #: metadata-only: dan doc gia ve doc ban day du o nguon that).
    external_source_url: str = ""
    #: So chuong NHU NGUON BAO CAO — khac voi so `Chapter` THAT ta luu (co
    #: the la 0 cho Novel metadata-only, xem docstring `PublicationMode`).
    external_chapter_count: int = 0
    #: Ngay cap nhat gan nhat THEO NGUON (chuoi tho, khong ep dinh dang —
    #: moi nguon bao cao khac nhau) — khac `updated_at` la thoi diem BAN GHI
    #: nay duoc sua o he thong minh.
    external_updated_at: str = ""
    #: Ma ngon ngu cua noi dung GOC (vd "en", "vi", "ja") — rong neu chua xac dinh.
    language: str = ""
    #: Danh sach nhan vat trong truyen (Anime Fanfic Discovery Taxonomy) —
    #: List[str] chuoi tu do (vd ["Uzumaki Naruto", "Uchiha Sasuke"]).
    characters: List[str] = field(default_factory=list)
    #: Danh sach cap doi (pairings / relationships) — chuoi tu do
    #: (vd ["Naruto/Hinata", "Sasuke & Sakura"]).
    pairings: List[str] = field(default_factory=list)
    #: Trang thai hoan thanh (ongoing/completed/hiatus) — mac dinh la ONGOING.
    status: NovelStatus = NovelStatus.ONGOING

    #: --- Video draft fields (mission "SHIP 3 CHINESE AI-ANIMATION VIDEO
    #: DRAFTS", 2026-09-01) --- Reuses `Novel`/`METADATA_ONLY` rather than a
    #: new collection: METADATA_ONLY already means "we don't own the full
    #: content, just metadata + a link back to source", which is exactly
    #: what a video draft needs. All four are rong ("") for ordinary
    #: text novels and simply unused there.
    #: Nen tang nguon: "youtube", "bilibili", ... Rong neu khong phai video.
    platform: str = ""
    #: "EMBED_ONLY" (khong sao chep media, chi nhung player goc) hoac
    #: "REHOST_ALLOWED" (co quyen chuyen ma va luu ban sao) — xem
    #: mission's step 8. Rong neu khong phai video.
    rights_mode: str = ""
    #: "PENDING_SOURCE" (chua co phu de goc/ASR), "READY" (da co file
    #: WebVTT/SRT), hoac rong neu khong phai video.
    subtitle_status: str = ""
    #: ID/tham chieu nhung video tren nen tang goc (vd YouTube video_id) —
    #: du de dung lai player nhung, khong phai URL day du (da co o
    #: `external_source_url`).
    embed_ref: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "novel_id": self.novel_id,
            "owner_id": self.owner_id,
            "title": self.title,
            "description": self.description,
            "cover_key": self.cover_key,
            "state": self.state.value,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "publication_mode": self.publication_mode.value,
            "fandom_ids": list(self.fandom_ids),
            "external_author_name": self.external_author_name,
            "external_source_url": self.external_source_url,
            "external_chapter_count": self.external_chapter_count,
            "external_updated_at": self.external_updated_at,
            "language": self.language,
            "characters": list(self.characters),
            "pairings": list(self.pairings),
            "status": self.status.value,
            "platform": self.platform,
            "rights_mode": self.rights_mode,
            "subtitle_status": self.subtitle_status,
            "embed_ref": self.embed_ref,
        }


@dataclass
class Chapter:
    novel_id: str
    owner_id: str
    title: str
    content: str = ""
    order_index: int = 1
    state: PublishState = PublishState.DRAFT
    chapter_id: str = field(default_factory=lambda: new_id("chp"))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    @property
    def char_count(self) -> int:
        return len(self.content or "")

    def to_dict(self, include_content: bool = True) -> Dict[str, Any]:
        data = {
            "chapter_id": self.chapter_id,
            "novel_id": self.novel_id,
            "owner_id": self.owner_id,
            "title": self.title,
            "order_index": self.order_index,
            "state": self.state.value,
            "char_count": self.char_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_content:
            data["content"] = self.content
        return data


@dataclass
class TtsJob:
    owner_id: str
    chapter_id: str
    voice_id: str
    content_hash: str
    status: JobStatus = JobStatus.PENDING
    output_key: Optional[str] = None         # object key cua audio trong kho
    error_kind: Optional[str] = None
    error_message: str = ""
    total_parts: int = 0
    done_parts: int = 0
    rate: str = "1.0"
    chunk_chars: int = 2000
    #: Heartbeat. Worker dang chay lam moi moc nay theo chu ky; het han nghia la
    #: worker da chet. `None` = khong co lease (job cu, hoac Appwrite chua co
    #: thuoc tinh nay). Xem `docs/HANDOFF.md` muc "Worker recovery".
    lease_expires_at: Optional[str] = None
    #: Tien trinh nao dang giu lease. De hai worker khong gianh cung mot job.
    lease_owner: Optional[str] = None
    #: Da thu chay bao nhieu lan. Vuot tran thi chuyen `failed`, khong thu mai.
    attempts: int = 0
    job_id: str = field(default_factory=lambda: new_id("job"))
    created_at: str = field(default_factory=now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    @property
    def progress_percent(self) -> int:
        if not self.total_parts:
            return 0
        return int(round(100.0 * self.done_parts / self.total_parts))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "owner_id": self.owner_id,
            "chapter_id": self.chapter_id,
            "voice_id": self.voice_id,
            "content_hash": self.content_hash,
            "status": self.status.value,
            "progress": self.progress_percent,
            "total_parts": self.total_parts,
            "done_parts": self.done_parts,
            "output_key": self.output_key,
            "error_kind": self.error_kind,
            "error_message": self.error_message,
            "rate": self.rate,
            "chunk_chars": self.chunk_chars,
            "lease_expires_at": self.lease_expires_at,
            "lease_owner": self.lease_owner,
            "attempts": self.attempts,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    def lease_is_live(self, now: Optional[datetime] = None) -> bool:
        """
        Con worker nao dang thuc su giu job nay hay khong.

        Khong co lease -> coi la KHONG con song. Job cu (tao truoc khi co lease)
        va job dang kep vinh vien deu roi vao day, dung nhu y muon: chung can
        duoc recovery.
        """
        if not self.lease_expires_at:
            return False
        moment = now or datetime.now(timezone.utc)
        try:
            expires = datetime.fromisoformat(self.lease_expires_at)
        except ValueError:
            return False
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires > moment

    @property
    def is_stale(self) -> bool:
        """Dang `running` ma khong con worker nao giu — can recovery."""
        return self.status is JobStatus.RUNNING and not self.lease_is_live()


@dataclass
class AudioTrack:
    """
    Audio da hoan tat cua mot chuong.

    `content_hash` la DAU VAN TAY, khong phai ma bam cua rieng noi dung: no gom
    ca noi dung, giong, toc do va kich thuoc doan (xem `job_fingerprint`).

    Track KHONG luu `rate`/`chunk_chars`. Hai tham so do lay tu ban ghi
    `tts_jobs` co cung `content_hash` — job da luu chung tu truoc, nen khong phai
    them thuoc tinh nao vao `audio_tracks`. Xem `MetadataStore.job_settings`.
    """

    chapter_id: str
    owner_id: str
    voice_id: str
    object_key: str
    content_hash: str
    duration_seconds: float = 0.0
    size_bytes: int = 0
    track_id: str = field(default_factory=lambda: new_id("trk"))
    created_at: str = field(default_factory=now_iso)
    #: Khoa sidecar phu de dong bo trong CUNG kho voi `object_key` (vi du
    #: `audio/.../x.mp3` -> `audio/.../x.transcript.json`) — rong khi CHUA co
    #: (audio cu tu truoc tinh nang nay, hoac ffprobe khong do duoc mot phan
    #: nao do luc tong hop). Xem `server/transcript.py` (web V4, Phan 2H).
    transcript_key: str = ""
    #: Khop `transcript.TRANSCRIPT_VERSION` luc sinh — de sau nay doi cach
    #: tinh thoi gian ma van biet ban cu dung cong thuc nao.
    transcript_version: int = 0
    #: TRUNG VOI `content_hash` tai thoi diem sinh transcript — chua chac
    #: TRUNG voi `content_hash` cua track (vi du neu sau nay transcript duoc
    #: sinh lai doc lap). Dung de kiem phien ban truoc khi hien thi, tranh
    #: dong bo nham phu de cua mot ban van khac (Phan 2L).
    source_content_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "chapter_id": self.chapter_id,
            "owner_id": self.owner_id,
            "voice_id": self.voice_id,
            "object_key": self.object_key,
            "content_hash": self.content_hash,
            "duration_seconds": self.duration_seconds,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "transcript_key": self.transcript_key,
            "transcript_version": self.transcript_version,
            "source_content_hash": self.source_content_hash,
        }


@dataclass(frozen=True)
class AudioStamp:
    """
    Vua du de biet audio cua mot chuong con khop noi dung hay khong.

    Dung cho DANH SACH chuong: lay ca `AudioTrack` ve thi khong can, ma tinh
    tung chuong mot thi lai thanh N+1. Day la phan toi thieu cua track moi nhat.

    `rate`/`chunk_chars` khong nam trong track — chung duoc GHEP VAO tu ban ghi
    job co cung `content_hash`. Job da bi xoa thi hai truong nay la None va chi
    con doan duoc bang moc thoi gian.
    """

    created_at: str
    content_hash: str = ""
    voice_id: str = ""
    rate: Optional[str] = None
    chunk_chars: Optional[int] = None

    def with_settings(self, rate: Optional[str],
                      chunk_chars: Optional[int]) -> "AudioStamp":
        """Ban sao co them tham so render lay tu job."""
        return AudioStamp(
            created_at=self.created_at,
            content_hash=self.content_hash,
            voice_id=self.voice_id,
            rate=rate,
            chunk_chars=chunk_chars,
        )

    @property
    def can_verify(self) -> bool:
        """Co du tham so de TINH LAI dau van tay hay khong."""
        return bool(self.content_hash and self.voice_id
                    and self.rate is not None and self.chunk_chars is not None)


# -----------------------------------------------------------------------------
# Tang xa hoi
# -----------------------------------------------------------------------------
#
# BAY bang, va mot nguyen tac chung cho ca bay: khoa chinh cua nhung bang co
# the co ban ghi TRUNG la mot khoa TAT DINH (xem `server/social.py`). Khong co
# no, moi phep "kiem tra roi ghi" deu thua mot cuoc dua, va so dem sai vinh vien.
#
#   user_follows     rowId = khoa(nguoi theo doi, nguoi duoc theo doi)
#   story_follows    rowId = khoa(nguoi theo doi, truyen)
#   posts            rowId = post_id        moi bai mot hang
#   post_likes       rowId = khoa(nguoi, bai)
#   comments         rowId = comment_id
#   notifications    rowId = khoa(nguoi nhan, loai, nguoi gay, doi tuong, ngay)
#   content_reports  rowId = khoa(nguoi bao, loai, doi tuong)


@dataclass
class UserFollow:
    """Mot nguoi theo doi mot nguoi khac."""

    follower_id: str
    target_id: str
    follow_id: str = ""
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "follow_id": self.follow_id,
            "follower_id": self.follower_id,
            "target_id": self.target_id,
            "created_at": self.created_at,
        }


@dataclass
class StoryFollow:
    """
    Mot nguoi theo doi mot truyen.

    BANG RIENG, khong gop voi `UserFollow` bang mot cot `kind`. Ly do la truy
    van: "ai theo doi truyen nay" va "ai theo doi nguoi nay" la hai cau hoi
    khac nhau chay o hai cho khac nhau, va gop lai thi moi truy van deu phai
    mang them mot dieu kien loc chi de bo di mot nua bang.
    """

    follower_id: str
    novel_id: str
    follow_id: str = ""
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "follow_id": self.follow_id,
            "follower_id": self.follower_id,
            "novel_id": self.novel_id,
            "created_at": self.created_at,
        }


@dataclass
class Post:
    """
    Mot bai dang cong khai.

    HIEN THI: giai doan nay MOI bai deu cong khai. Khong co che do rieng tu hay
    "chi nguoi theo doi" — them mot truc hien thi keo theo phep loc o moi truy
    van bang tin, moi trang ca nhan va moi man kiem duyet, va lam sai mot cho
    trong so do la lo noi dung rieng tu ra ngoai. Mot truc, cuong che o mot cho.

    `like_count`/`comment_count` la ban TONG HOP, giong `AuthorStats`: dem lai
    tu bang `post_likes` cho MOI bai trong bang tin la mot phep quet moi hang.
    Doi lai chung co the LECH neu mot buoc cong bi mat, va bang su that van la
    `post_likes`/`comments` — co duong dem lai o tang dich vu.
    """

    author_user_id: str
    text: str = ""
    kind: PostKind = PostKind.POST
    #: Chi co nghia voi `STORY_UPDATE`. Chuoi rong voi bai thuong.
    novel_id: str = ""
    #: Khoa doi tuong trong R2 — xem `social.object_key`. KHONG phai binary.
    #: BAN CU (mot anh). Van doc/ghi duoc de hang da co tren staging khong
    #: hong; bai MOI dung `images` va de cac truong nay rong.
    image_key: str = ""
    image_mime: str = ""
    image_width: int = 0
    image_height: int = 0
    image_bytes: int = 0
    #: V3: toi da BON anh. Moi phan tu:
    #: {"key","mime","width","height","bytes"}. Luu xuong Appwrite thanh MOT
    #: cot chuoi JSON (`images_json`) — them mot bang con chi de dem bon hang
    #: la them mot vong mang cho moi bai tren bang tin.
    images: List[Dict[str, Any]] = field(default_factory=list)
    state: ContentState = ContentState.VISIBLE
    like_count: int = 0
    comment_count: int = 0
    #: Quan tri da go. Rong khi bai con hien.
    removed_by: str = ""
    removed_reason: str = ""
    post_id: str = field(default_factory=lambda: new_id("pst"))
    created_at: str = field(default_factory=now_iso_us)
    updated_at: str = field(default_factory=now_iso_us)

    @property
    def has_image(self) -> bool:
        return bool(self.image_key) or bool(self.images)

    def all_images(self) -> List[Dict[str, Any]]:
        """Danh sach anh THONG NHAT: bai cu mot-anh va bai moi nhieu-anh."""
        if self.images:
            return list(self.images)
        if self.image_key:
            return [{"key": self.image_key, "mime": self.image_mime,
                     "width": self.image_width, "height": self.image_height,
                     "bytes": self.image_bytes}]
        return []

    def to_dict(self) -> Dict[str, Any]:
        """Hinh dang LUU TRU va hinh dang cho QUAN TRI. Co ca truong kiem duyet."""
        return {
            "post_id": self.post_id,
            "author_user_id": self.author_user_id,
            "kind": self.kind.value,
            "novel_id": self.novel_id,
            "text": self.text,
            "image_key": self.image_key,
            "image_mime": self.image_mime,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "image_bytes": self.image_bytes,
            "images": list(self.images),
            "state": self.state.value,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
            "removed_by": self.removed_by,
            "removed_reason": self.removed_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_public_dict(self) -> Dict[str, Any]:
        """
        Ban CONG KHAI — danh sach cho phep, khong phai danh sach loai tru.

        `removed_by` khong ra ngoai: no cho biet quan tri nao da xu ly, va do la
        thu bien mot quyet dinh kiem duyet thanh mot muc tieu ca nhan.

        `image_key` cung khong ra: khoa doi tuong tho khong dung truc tiep duoc
        (kho la rieng tu) va lo ra cau truc khong gian ten. Tang route ghep
        `image_url` da ky vao thay cho no.
        """
        return {
            "post_id": self.post_id,
            "author_user_id": self.author_user_id,
            "kind": self.kind.value,
            "novel_id": self.novel_id,
            "text": self.text if self.state is ContentState.VISIBLE else "",
            "has_image": self.has_image and self.state is ContentState.VISIBLE,
            "image_width": self.image_width,
            "image_height": self.image_height,
            # Kich thuoc tung anh cho gallery — KHONG kem `key`; khoa tho khong
            # bao gio ra ngoai, URL da ky duoc tang route ghep vao.
            "images": ([{"width": int(a.get("width") or 0),
                         "height": int(a.get("height") or 0)}
                        for a in self.all_images()]
                       if self.state is ContentState.VISIBLE else []),
            "state": self.state.value,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class PostLike:
    """Mot luot thich. `like_id` la khoa tat dinh — xem `social.post_like_key`."""

    post_id: str
    user_id: str
    like_id: str = ""
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "like_id": self.like_id,
            "post_id": self.post_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
        }


@dataclass
class Comment:
    """
    Mot binh luan, hoac mot tra loi cho binh luan goc.

    `parent_id` rong = binh luan goc. DUNG mot cap — xem `social.REPLY_MAX_DEPTH`
    de biet vi sao khong phai mot cay khong gioi han.

    MOT loi binh luan cho HAI noi (V3): bai dang cong dong VA chuong truyen.
    `post_id` giu ten cu nhung mang nghia "id cua DICH" — voi binh luan chuong
    no chua `chapter_id`. Doi ten cot tren mot bang da co du lieu that la mot
    migration pha huy; giu ten va noi ro nghia thi khong. Hai khong gian id
    (`pst_…`/`chp_…`) khong the va cham, va `target_kind` noi tuong minh.

    DICH LA CHUONG, khong phai file MP3: tac gia tao lai audio thi `chapter_id`
    khong doi, nen chuoi binh luan SONG SOT qua moi lan tao lai. Gan vao object
    key cua R2 thi moi lan render lai la mot chuoi binh luan mo coi.
    """

    post_id: str
    author_user_id: str
    text: str = ""
    #: `comment_id` cua binh luan goc, hoac chuoi rong.
    parent_id: str = ""
    #: `""` = binh luan BAI DANG (moi hang cu deu vay — mac dinh nay chinh la
    #: phep tuong thich nguoc). `"chapter"` = binh luan chuong/audio.
    target_kind: str = ""
    #: Vi tri audio dang nghe luc binh luan, tinh bang MILI GIAY. `None` =
    #: khong dinh kem. KHONG dung -1 hay 0 lam "khong co": 0 la mot moc HOP LE
    #: (dau chuong), va mot gia tri canh gac kieu -1 se co ngay bi mot phep
    #: `or 0` nuot mat o tang doi hang.
    timestamp_ms: Optional[int] = None
    #: Nguoi viet TU danh dau co spoiler. Khong co may do spoiler nao ca.
    spoiler: bool = False
    state: ContentState = ContentState.VISIBLE
    reply_count: int = 0
    removed_by: str = ""
    removed_reason: str = ""
    comment_id: str = field(default_factory=lambda: new_id("cmt"))
    created_at: str = field(default_factory=now_iso_us)
    updated_at: str = field(default_factory=now_iso_us)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "post_id": self.post_id,
            "author_user_id": self.author_user_id,
            "parent_id": self.parent_id,
            "target_kind": self.target_kind,
            "timestamp_ms": self.timestamp_ms,
            "spoiler": self.spoiler,
            "text": self.text,
            "state": self.state.value,
            "reply_count": self.reply_count,
            "removed_by": self.removed_by,
            "removed_reason": self.removed_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_public_dict(self) -> Dict[str, Any]:
        """
        Binh luan da bi go van TRA VE, nhung khong kem noi dung.

        Vi sao khong an han: mot tra loi treo lo lung duoi mot khoang trong doc
        ra kho hieu hon la mot dong "Bình luận đã bị gỡ". Va so dem tra loi cua
        binh luan goc van dung.
        """
        da_go = self.state is not ContentState.VISIBLE
        return {
            "comment_id": self.comment_id,
            "post_id": self.post_id,
            "author_user_id": "" if da_go else self.author_user_id,
            "parent_id": self.parent_id,
            "target_kind": self.target_kind,
            "timestamp_ms": None if da_go else self.timestamp_ms,
            "spoiler": self.spoiler,
            "text": "" if da_go else self.text,
            "state": self.state.value,
            "reply_count": self.reply_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Notification:
    """
    Mot thong bao trong ung dung. KHONG co email o giai doan nay.

    `notification_id` la khoa TAT DINH co go ngay (xem
    `social.notification_key`), nen cung mot nguoi lam cung mot viec voi cung
    mot doi tuong trong mot ngay chi sinh MOT thong bao. Chinh tinh duy nhat cua
    khoa la co che chong lap — khong co bo dem nao ca.
    """

    #: Nguoi NHAN.
    user_id: str
    kind: NotificationKind = NotificationKind.FOLLOW
    #: Nguoi GAY RA. Rong = he thong (vd don duoc duyet).
    actor_id: str = ""
    #: Doi tuong duoc nhac toi: post_id, comment_id, novel_id... tuy `kind`.
    subject_id: str = ""
    #: `post` | `comment` | `novel` | `user` | rong. De frontend biet dieu huong.
    subject_kind: str = ""
    #: Mot doan ngan da cat san, de danh sach thong bao khong phai doc them bang.
    preview: str = ""
    read: bool = False
    notification_id: str = ""
    created_at: str = field(default_factory=now_iso_us)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "notification_id": self.notification_id,
            "user_id": self.user_id,
            "kind": self.kind.value,
            "actor_id": self.actor_id,
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind,
            "preview": self.preview,
            "read": self.read,
            "created_at": self.created_at,
        }

    def to_public_dict(self) -> Dict[str, Any]:
        """Ban cho CHINH NGUOI NHAN. Bo `user_id` — ho biet ho la ai."""
        data = self.to_dict()
        data.pop("user_id", None)
        return data


@dataclass
class ContentReport:
    """
    Mot bao cao cua nguoi dung ve mot bai hoac mot binh luan.

    BAO CAO KHONG BAO GIO TU GO NOI DUNG. No chi dua noi dung vao hang doi kiem
    duyet. Neu khong the: mot nhom nguoi phoi hop bam Bao cao se tro thanh mot
    cong cu xoa noi dung cua nguoi ho khong thich, va do la ket qua nguoc hoan
    toan voi muc dich cua nut do.

    `resolution_note` la ghi chu NOI BO cua quan tri — khong bao gio ra API cong
    khai, giong `ModerationEvent.note`.
    """

    reporter_id: str
    #: `post` | `comment`.
    target_kind: str = "post"
    target_id: str = ""
    #: Chu so huu noi dung bi bao cao, chep lai luc bao cao de khu quan tri khong
    #: phai doc them mot bang nua cho moi hang.
    target_owner_id: str = ""
    reason: ReportReason = ReportReason.OTHER
    detail: str = ""
    status: ReportStatus = ReportStatus.OPEN
    resolution_note: str = ""
    resolved_by: str = ""
    report_id: str = ""
    created_at: str = field(default_factory=now_iso_us)
    updated_at: str = field(default_factory=now_iso_us)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "reporter_id": self.reporter_id,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "target_owner_id": self.target_owner_id,
            "reason": self.reason.value,
            "detail": self.detail,
            "status": self.status.value,
            "resolution_note": self.resolution_note,
            "resolved_by": self.resolved_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def job_fingerprint(content: str, voice_id: str, rate: str, chunk_chars: int) -> str:
    """
    Dau van tay dung cho IDEMPOTENCY.

    Cung noi dung + cung giong + cung thiet lap => cung mot job, khong tao lai.
    """
    from desktop_app.models import content_hash

    payload = f"{content}\x1f{voice_id}\x1f{rate}\x1f{chunk_chars}"
    return content_hash(payload)


class MediaType(str, Enum):
    AUDIO = "audio"
    IMAGE = "image"
    SUBTITLES = "subtitles"
    UNKNOWN = "unknown"


class StorageTier(str, Enum):
    HOT = "hot"
    ARCHIVE = "archive"


class MediaProcessingState(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass
class MediaAsset:
    """
    Tai san da phuong tien tong quat (audio, anh bia, phu de).

    Dung cho Production Story + Audio Harvester, theo doi theo luong (tier) va
    vong doi xu ly rieng, khong phu thuoc vao luong TTS chuong (AudioTrack).
    """

    owner_id: str
    media_type: MediaType
    storage_tier: StorageTier
    object_key: str
    content_hash: str
    source: str = ""
    codec: str = ""
    bitrate: int = 0
    duration_seconds: float = 0.0
    size_bytes: int = 0
    processing_state: MediaProcessingState = MediaProcessingState.PENDING
    rights_state: PublishState = PublishState.DRAFT
    asset_id: str = field(default_factory=lambda: new_id("mas"))
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "owner_id": self.owner_id,
            "media_type": self.media_type.value,
            "storage_tier": self.storage_tier.value,
            "object_key": self.object_key,
            "content_hash": self.content_hash,
            "source": self.source,
            "codec": self.codec,
            "bitrate": self.bitrate,
            "duration_seconds": self.duration_seconds,
            "size_bytes": self.size_bytes,
            "processing_state": self.processing_state.value,
            "rights_state": self.rights_state.value,
            "created_at": self.created_at,
        }


class FandomMediaType(str, Enum):
    ANIME = "anime"
    MANGA = "manga"
    LIGHT_NOVEL = "light_novel"
    OTHER = "other"


@dataclass
class Fandom:
    """
    Dinh danh CHUAN HOA cua mot fandom anime/manga/light-novel — nhieu ten
    goi khac nhau tren nhieu nguon (vd "Boku no Hero Academia", "My Hero
    Academia", "BNHA", "MHA") deu quy ve MOT `canonical_name`.

    KHONG hardcode chi mot danh sach fandom co dinh — day la mot BAN GHI,
    dang ky moi duoc them qua vong doi binh thuong (xem
    `server/fandom_registry.py::FandomRegistry.register`), giong nguyen tac
    "new source detected" cua `site_registry.py`: fandom CHUA biet duoc gan
    co ro rang thay vi bi am tham bo qua hoac doan bua.
    """

    canonical_name: str
    media_type: FandomMediaType = FandomMediaType.ANIME
    #: Cac ten khac nhau da biet CUNG mot ngon ngu/khong ngon ngu ro rang
    #: (viet tat, ten thay the) — vd ["BNHA", "MHA", "Boku no Hero Academia"].
    aliases: List[str] = field(default_factory=list)
    #: Ten CHINH XAC nhu nguon cu the hien thi (FFN, AO3, ...) tung dung —
    #: khac `aliases` o cho day la ghi lai NGUON GOC cua ten, phuc vu doi
    #: soat/debug khi mot ten moi xuat hien, khong phai danh sach de khop.
    source_names: List[str] = field(default_factory=list)
    #: Ten theo tung ma ngon ngu (vd {"ja": "僕のヒーローアカデミア",
    #: "vi": "Học Viện Anh Hùng Của Tôi"}) — RONG neu chua co ban dich xac nhan.
    language_aliases: Dict[str, str] = field(default_factory=dict)
    fandom_id: str = field(default_factory=lambda: new_id("fdm"))
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fandom_id": self.fandom_id,
            "canonical_name": self.canonical_name,
            "media_type": self.media_type.value,
            "aliases": list(self.aliases),
            "source_names": list(self.source_names),
            "language_aliases": dict(self.language_aliases),
            "created_at": self.created_at,
        }


class RightsBasis(str, Enum):
    """Co so quyen ma nguoi nhap TU KHAI khi nhap noi dung day du (Authorized
    Import). Day la mot TIN HIEU KIEM DUYET/TRACH NHIEM GIAI TRINH, KHONG
    PHAI bang chung so huu — xem `ImportRecord`."""

    AUTHOR = "author"
    PERMISSION_GRANTED = "permission_granted"


@dataclass
class ImportRecord:
    """
    Ban ghi nguon goc/trach nhiem giai trinh cho MOT lan nhap noi dung day du
    qua Authorized Import — KHONG PHAI bang chung phap ly ve quyen so huu.

    Tu khai `rights_basis` (nguoi nhap tu nhan la tac gia HOAC da duoc tac
    gia cho phep) duoc LUU LAI kem danh tinh/thoi diem/nguon/dau van tay tep —
    du de kiem duyet dieu tra khi co khieu nai, KHONG du de tu dong xac minh
    quyen that su. Xem mission "AUTHORIZED FANFIC INGESTION": "Do not treat
    this checkbox as proof of ownership; it is provenance/accountability
    metadata and a moderation signal."

    `original_file_hash` (sha256 cua BYTE THO nguoi dung tai len, TRUOC khi
    trich xuat/chuan hoa) khac `content_hash` (sha256 cua van ban DA CHUAN
    HOA, cung quy uoc voi `bulk_import_domain.py::chuan_hoa_noi_dung`) — hai
    hash phuc vu hai muc dich khac nhau: cai truoc doi soat CHINH XAC tep da
    tai len (khieu nai ban quyen thuong dan chieu tep goc), cai sau phat hien
    NOI DUNG trung lap du dinh dang tep khac nhau.
    """

    novel_id: str
    importer_user_id: str
    rights_basis: RightsBasis
    #: "authorized_upload" cho luong tai tep len; mot URL that cho truong hop
    #: nhap-tu-URL duoc cho phep ro rang (hiem, xem mission brief muc 1).
    source: str
    original_filename: str
    original_file_hash: str
    content_hash: str
    import_id: str = field(default_factory=lambda: new_id("imr"))
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "import_id": self.import_id,
            "novel_id": self.novel_id,
            "importer_user_id": self.importer_user_id,
            "rights_basis": self.rights_basis.value,
            "source": self.source,
            "original_filename": self.original_filename,
            "original_file_hash": self.original_file_hash,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
        }
