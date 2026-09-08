"""Bo cuc kho san xuat CHINH TAC + dinh danh tac pham TAT DINH.

## Vi sao ten thu muc KHONG duoc lay tu Gemini

Gemini chuan hoa sieu du lieu (tieu de, tac gia, the loai...). No **khong**
duoc chon ten thu muc hay ten object. Ly do la mot tinh chat, khong phai mot
so thich: cung mot tac pham cham qua hai lan danh gia co the ra hai tieu de
hoi khac nhau ("Lều chõng" / "Leu Chong" / "Lều Chõng (bản đầy đủ)"). Neu ten
thu muc bam vao tieu de do, mot lan **thu lai** se de ra mot thu muc thu hai
cho cung mot tac pham — dung dieu ma khu trung lap ton tai de ngan.

Nen dinh danh duoc dan ra tu **DANH TINH NGUON**, thu khong doi:

    work_id = sha256(bucket + canonical_url)      <- tat dinh, on dinh mai mai
    slug    = tu duong dan URL, khong tu tieu de  <- doc duoc, van tat dinh

Ca hai deu la ma tinh, khong co model nao trong duong di.

## Kho cu KHONG bi dong toi

`FanficWorld/archive/` la LEGACY: raw scraping, rendered cu, backup ha tang.
Module nay khong bao gio ghi vao do, khong doi ten, khong sap xep lai. San
pham MOI di vao `FanficWorld/production/`.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from server.scraper.contract import canonicalize_url

#: Goc SAN XUAT moi. Tach hoan toan khoi `FanficWorld/archive` (legacy).
PRODUCTION_ROOT = "FanficWorld/production"

#: Ba thung tac pham. Thung duoc chon boi LAN SAN XUAT (ma biet), khong boi
#: `content_type` cua Gemini — mot chuoi tu do tu model khong duoc phep quyet
#: dinh mot duong dan.
BUCKET_FANFIC_TTS = "works/fanfic-tts"
BUCKET_EXISTING_AUDIO = "works/existing-audio"
BUCKET_CHINESE_MEDIA = "works/chinese-media"

#: Ba khu khong phai tac pham.
QUARANTINE = "quarantine"
REJECTED = "rejected"
MANIFESTS = "manifests"

BUCKETS = (BUCKET_FANFIC_TTS, BUCKET_EXISTING_AUDIO, BUCKET_CHINESE_MEDIA)
ALL_SUBTREES = BUCKETS + (QUARANTINE, REJECTED, MANIFESTS)

#: Ten tep CHUAN — mot tac pham, mot bo ten. Khong bien the, khong hau to
#: ngau nhien: mot cong cu khac phai doan duoc duong dan ma khong can hoi.
ARTIFACT_MANIFEST = "manifest.json"
ARTIFACT_SOURCE_DIR = "source"
ARTIFACT_TEXT = "text/normalized.txt"
ARTIFACT_TRANSCRIPT = "transcript/transcript.json"
ARTIFACT_SUBTITLE_VI = "subtitles/vi.srt"
ARTIFACT_AUDIO_VI = "audio/vi.mp3"
ARTIFACT_COVER = "artwork/cover.webp"
ARTIFACT_BACKGROUND = "artwork/background.webp"

#: Hai thu BAT BUOC truoc READY/PUBLISHABLE.
REQUIRED_ARTWORK = (ARTIFACT_COVER, ARTIFACT_BACKGROUND)

#: Quyet dinh sau danh gia.
DECISION_APPROVE = "approve"
DECISION_QUARANTINE = "quarantine"
DECISION_REJECT = "reject"
DECISIONS = (DECISION_APPROVE, DECISION_QUARANTINE, DECISION_REJECT)

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_SLUG_EDGES = re.compile(r"^-+|-+$")


def slugify(raw: str, *, max_len: int = 48) -> str:
    """Slug TAT DINH, ASCII, an toan cho duong dan va khoa object.

    Khong bao gio tra ve chuoi rong: chuoi rong se lam hai tac pham khac nhau
    cham vao cung mot duong dan.
    """
    chuan = unicodedata.normalize("NFKD", raw or "")
    ascii_only = chuan.encode("ascii", "ignore").decode("ascii").lower()
    s = _SLUG_EDGES.sub("", _SLUG_STRIP.sub("-", ascii_only))[:max_len]
    s = _SLUG_EDGES.sub("", s)
    return s or "work"


def source_slug(url: str) -> str:
    """Slug lay tu DUONG DAN URL — khong tu tieu de.

    URL la thu khong doi giua hai lan danh gia; tieu de thi doi. Doc duoc ma
    van tat dinh.
    """
    try:
        phan = urlsplit(canonicalize_url(url))
    except Exception:                                           # noqa: BLE001
        return "work"
    doan = [d for d in (phan.path or "").split("/") if d]
    if doan:
        return slugify(doan[-1])
    return slugify(phan.netloc or "work")


def work_id(bucket: str, url: str) -> str:
    """Dinh danh ON DINH cua mot tac pham. Chi phu thuoc (thung, URL chuan).

    KHONG phu thuoc tieu de, thoi diem, thu tu phat hien, hay bat cu thu gi
    Gemini tra ve — nen mot lan thu lai luon ra dung dinh danh cu.
    """
    if bucket not in BUCKETS:
        raise ValueError(f"thung khong hop le: {bucket!r}")
    canon = canonicalize_url(url)
    if not (url or "").strip():
        raise ValueError("URL rong — khong dung duoc dinh danh tac pham")
    digest = hashlib.sha256(f"{bucket}|{canon}".encode("utf-8")).hexdigest()
    return f"w_{digest[:20]}"


def canonical_dir(bucket: str, url: str) -> str:
    """MOT thu muc chinh tac cho mot tac pham.

    `<slug tu URL>-<work_id>` — phan slug de doc, phan `work_id` de khong bao
    gio dung nhau. Ca hai deu tat dinh, nen goi lai voi cung nguon luon ra
    cung mot duong dan.
    """
    return f"{PRODUCTION_ROOT}/{bucket}/{source_slug(url)}-{work_id(bucket, url)}"


def artifact_path(bucket: str, url: str, artifact: str) -> str:
    return f"{canonical_dir(bucket, url)}/{artifact}"


def bucket_for_lane(lane: str, *, chinese_media: bool = False) -> str:
    """Thung duoc chon boi LAN, khong boi `content_type` cua model."""
    if chinese_media:
        return BUCKET_CHINESE_MEDIA
    return BUCKET_FANFIC_TTS if lane == "text" else BUCKET_EXISTING_AUDIO


def holding_dir(decision: str, bucket: str, url: str) -> str:
    """Noi cho mot tac pham KHONG duoc duyet. Van mot thu muc tat dinh, de
    mot lan xem lai tim duoc no."""
    khu = QUARANTINE if decision == DECISION_QUARANTINE else REJECTED
    return f"{PRODUCTION_ROOT}/{khu}/{source_slug(url)}-{work_id(bucket, url)}"


@dataclass
class WorkManifest:
    """`manifest.json` — giu NGUYEN VEN moi thu goc.

    Chuan hoa khong duoc lam mat ban goc: tieu de nguon, URL, ID nha cung
    cap, hash va toan bo sieu du lieu tho deu o lai day. Neu sau nay phep
    chuan hoa doi, ta con doi chieu duoc; neu chi giu ban da chuan hoa thi
    khong.
    """
    work_id: str
    bucket: str
    canonical_dir: str
    decision: str

    # --- ban GOC, khong bao gio bi ghi de bang ban chuan hoa ---------------
    source_url: str = ""
    source_title: str = ""
    source_provider_id: str = ""
    source_hashes: Dict[str, str] = field(default_factory=dict)
    source_metadata_raw: Dict[str, Any] = field(default_factory=dict)

    # --- ban da chuan hoa (tu Gemini, qua kiem cua ma) ---------------------
    canonical_title: str = ""
    display_title: str = ""
    fandom: str = ""
    category: str = ""
    author: str = ""
    language: str = ""
    content_type: str = ""
    completeness: str = ""
    quality_score: int = 0
    tags: List[str] = field(default_factory=list)
    decision_reason: str = ""

    # --- duong PHUC VU (R2/Appwrite) ---------------------------------------
    # Dinh danh ben duong phuc vu. Chung KHONG dung de dung duong dan — duong
    # dan chi den tu (thung, URL). Chung o day de mot tac pham tren kho luu
    # tru truy nguoc duoc ve ban dang phat, va nguoc lai.
    novel_id: str = ""
    tts_job_id: str = ""
    review_model: str = ""

    # --- trang thai ---------------------------------------------------------
    artifacts: Dict[str, str] = field(default_factory=dict)
    archive_state: str = ""
    archive_path: str = ""
    #: Ket qua CUOI cua cong READY tai luc ghi. Duoc luu chu khong tinh lai
    #: khi doc: mot manifest phai noi duoc no da di qua cong o trang thai nao,
    #: ke ca khi luat cong doi sau nay.
    ready: bool = False
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: int = 1

    def missing_required_artwork(self) -> List[str]:
        return [a for a in REQUIRED_ARTWORK if not self.artifacts.get(a)]

    def publishable(self) -> bool:
        """READY/PUBLISHABLE can CA quyet dinh duyet LAN du bo tranh."""
        return (self.decision == DECISION_APPROVE
                and not self.missing_required_artwork())

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "work_id": self.work_id,
            "ready": self.ready,
            "serving": {
                "novel_id": self.novel_id,
                "tts_job_id": self.tts_job_id,
                "review_model": self.review_model,
            },
            "bucket": self.bucket,
            "canonical_dir": self.canonical_dir,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "source": {
                "url": self.source_url,
                "title": self.source_title,
                "provider_id": self.source_provider_id,
                "hashes": dict(self.source_hashes),
                "metadata_raw": dict(self.source_metadata_raw),
            },
            "normalized": {
                "canonical_title": self.canonical_title,
                "display_title": self.display_title,
                "fandom": self.fandom,
                "category": self.category,
                "author": self.author,
                "language": self.language,
                "content_type": self.content_type,
                "completeness": self.completeness,
                "quality_score": self.quality_score,
                "tags": list(self.tags),
            },
            "artifacts": dict(self.artifacts),
            "archive": {"state": self.archive_state, "path": self.archive_path},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkManifest":
        """Doc lai mot manifest da ghi.

        Ton tai vi TTS chay BAT DONG BO: khoanh khac tac pham duoc duyet va
        khoanh khac co tep mp3 khong bao gio la mot, nen phai mo lai duoc
        manifest cu de bo sung thay vi ghi de bang mot ban moi tinh (se lam
        mat `created_at`, ban an, va sieu du lieu goc).
        """
        nguon = data.get("source") or {}
        chuan = data.get("normalized") or {}
        phuc_vu = data.get("serving") or {}
        luu = data.get("archive") or {}
        return cls(
            work_id=str(data.get("work_id", "")),
            bucket=str(data.get("bucket", "")),
            canonical_dir=str(data.get("canonical_dir", "")),
            decision=str(data.get("decision", "")),
            decision_reason=str(data.get("decision_reason", "")),
            source_url=str(nguon.get("url", "")),
            source_title=str(nguon.get("title", "")),
            source_provider_id=str(nguon.get("provider_id", "")),
            source_hashes=dict(nguon.get("hashes") or {}),
            source_metadata_raw=dict(nguon.get("metadata_raw") or {}),
            canonical_title=str(chuan.get("canonical_title", "")),
            display_title=str(chuan.get("display_title", "")),
            fandom=str(chuan.get("fandom", "")),
            category=str(chuan.get("category", "")),
            author=str(chuan.get("author", "")),
            language=str(chuan.get("language", "")),
            content_type=str(chuan.get("content_type", "")),
            completeness=str(chuan.get("completeness", "")),
            quality_score=int(chuan.get("quality_score") or 0),
            tags=[str(t) for t in (chuan.get("tags") or [])],
            novel_id=str(phuc_vu.get("novel_id", "")),
            tts_job_id=str(phuc_vu.get("tts_job_id", "")),
            review_model=str(phuc_vu.get("review_model", "")),
            artifacts=dict(data.get("artifacts") or {}),
            archive_state=str(luu.get("state", "")),
            archive_path=str(luu.get("path", "")),
            ready=bool(data.get("ready", False)),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )
