"""
Adapter cho danh tinh (Appwrite) va luu tru file (Cloudflare R2).

Backend LUON chay duoc: khi chua co credential that, he thong dung ban mock
(trong bo nho + dia cuc bo). Doi sang ban that chi la doi bien moi truong,
khong phai sua code goi.

Giao dien duoc thiet ke san cho signed URL / Worker kiem tra quyen o giai doan
sau: `signed_url()` da co san trong Protocol.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from server.config import Settings
from server.domain import (
    AudioTrack,
    Chapter,
    Novel,
    Profile,
    TtsJob,
    new_id,
    now_iso,
)


class AuthError(Exception):
    """Sai thong tin dang nhap hoac phien khong hop le."""


class NotFoundError(Exception):
    """Khong tim thay ban ghi."""


class PermissionDenied(Exception):
    """Nguoi dung khong so huu tai nguyen nay."""


# -----------------------------------------------------------------------------
# Giao dien
# -----------------------------------------------------------------------------


class IdentityAdapter(Protocol):
    """Auth + metadata. Ban that se do Appwrite dam nhiem."""

    mode: str

    def register(self, email: str, password: str, display_name: str = "") -> Profile: ...
    def login(self, email: str, password: str) -> str: ...
    def profile_from_token(self, token: str) -> Profile: ...


class StorageAdapter(Protocol):
    """Luu file lon. Ban that se la Cloudflare R2 qua API tuong thich S3."""

    mode: str

    def put(self, key: str, data: bytes, content_type: str = "audio/mpeg") -> str: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def size(self, key: str) -> int: ...
    def signed_url(self, key: str, expires_seconds: int = 3600) -> Optional[str]: ...


# -----------------------------------------------------------------------------
# Ban mock: danh tinh
# -----------------------------------------------------------------------------


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}\x1f{password}".encode("utf-8")).hexdigest()


class MockIdentityAdapter:
    """
    Danh tinh trong bo nho - CHI dung cho phat trien cuc bo.

    Mat khau duoc bam kem salt (khong luu dang thuong), nhung day KHONG phai
    giai phap production: khong co rate limit, khong xac minh email, token
    khong het han. Ban that phai la Appwrite.
    """

    mode = "mock"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._profiles: Dict[str, Profile] = {}      # user_id -> Profile
        self._by_email: Dict[str, str] = {}          # email -> user_id
        self._passwords: Dict[str, tuple] = {}       # user_id -> (salt, hash)
        self._tokens: Dict[str, str] = {}            # token -> user_id

    def register(self, email: str, password: str, display_name: str = "") -> Profile:
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            raise AuthError("Email không hợp lệ.")
        if len(password or "") < 8:
            raise AuthError("Mật khẩu phải có ít nhất 8 ký tự.")
        with self._lock:
            if email in self._by_email:
                raise AuthError("Email này đã được đăng ký.")
            user_id = new_id("usr")
            salt = os.urandom(16).hex()
            self._passwords[user_id] = (salt, _hash_password(password, salt))
            profile = Profile(user_id=user_id, email=email, display_name=display_name)
            self._profiles[user_id] = profile
            self._by_email[email] = user_id
            return profile

    def login(self, email: str, password: str) -> str:
        email = (email or "").strip().lower()
        with self._lock:
            user_id = self._by_email.get(email)
            if user_id is None:
                raise AuthError("Email hoặc mật khẩu không đúng.")
            salt, expected = self._passwords[user_id]
            if _hash_password(password or "", salt) != expected:
                raise AuthError("Email hoặc mật khẩu không đúng.")
            token = new_id("tok")
            self._tokens[token] = user_id
            return token

    def profile_from_token(self, token: str) -> Profile:
        with self._lock:
            user_id = self._tokens.get((token or "").strip())
            if user_id is None:
                raise AuthError("Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
            return self._profiles[user_id]

    def logout(self, token: str) -> None:
        with self._lock:
            self._tokens.pop((token or "").strip(), None)


# -----------------------------------------------------------------------------
# Ban mock: luu tru
# -----------------------------------------------------------------------------


class LocalStorageAdapter:
    """
    Luu file xuong dia cuc bo, thay cho R2 khi chua co credential.

    Ghi ra file tam roi doi ten (atomic) de khong bao gio de lai file do dang.
    """

    mode = "mock"

    def __init__(self, root: Path):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Chan duong dan vuot ra ngoai thu muc goc
        safe = key.replace("\\", "/").lstrip("/")
        if ".." in safe.split("/"):
            raise ValueError(f"Object key không hợp lệ: {key}")
        return self._root / safe

    def put(self, key: str, data: bytes, content_type: str = "audio/mpeg") -> str:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        with open(tmp, "wb") as fp:
            fp.write(data)
        os.replace(tmp, target)
        return key

    def put_file(self, key: str, source: Path) -> str:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        shutil.copyfile(source, tmp)
        os.replace(tmp, target)
        return key

    def get(self, key: str) -> bytes:
        target = self._path(key)
        if not target.is_file():
            raise NotFoundError(f"Không tìm thấy file: {key}")
        return target.read_bytes()

    def exists(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except ValueError:
            return False

    def size(self, key: str) -> int:
        target = self._path(key)
        return target.stat().st_size if target.is_file() else 0

    def signed_url(self, key: str, expires_seconds: int = 3600) -> Optional[str]:
        """
        Ban cuc bo khong co URL ky san.

        Tra None de tang tren biet phai stream qua backend. Khi doi sang R2,
        ham nay se tra URL ky that va tang tren khong can doi.
        """
        return None


# -----------------------------------------------------------------------------
# Ban mock: metadata
# -----------------------------------------------------------------------------


class MockMetadataStore:
    """
    Kho metadata trong bo nho: profiles, novels, chapters, tts_jobs, audio_tracks.

    Moi truy van deu kiem tra QUYEN SO HUU - dung mo hinh phan quyen ma Appwrite
    se ap dung o ban that.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.novels: Dict[str, Novel] = {}
        self.chapters: Dict[str, Chapter] = {}
        self.jobs: Dict[str, TtsJob] = {}
        self.tracks: Dict[str, AudioTrack] = {}

    # -- novel ---------------------------------------------------------------

    def create_novel(self, novel: Novel) -> Novel:
        with self._lock:
            self.novels[novel.novel_id] = novel
            return novel

    def get_novel(self, novel_id: str) -> Novel:
        novel = self.novels.get(novel_id)
        if novel is None:
            raise NotFoundError("Không tìm thấy tiểu thuyết.")
        return novel

    def owned_novel(self, novel_id: str, owner_id: str) -> Novel:
        novel = self.get_novel(novel_id)
        if novel.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu tiểu thuyết này.")
        return novel

    def list_novels(self, owner_id: Optional[str] = None, published_only: bool = False) -> List[Novel]:
        with self._lock:
            items = list(self.novels.values())
        if owner_id:
            items = [n for n in items if n.owner_id == owner_id]
        if published_only:
            items = [n for n in items if n.state.value == "published"]
        return sorted(items, key=lambda n: n.created_at, reverse=True)

    # -- chapter -------------------------------------------------------------

    def create_chapter(self, chapter: Chapter) -> Chapter:
        with self._lock:
            self.chapters[chapter.chapter_id] = chapter
            return chapter

    def get_chapter(self, chapter_id: str) -> Chapter:
        chapter = self.chapters.get(chapter_id)
        if chapter is None:
            raise NotFoundError("Không tìm thấy chương.")
        return chapter

    def owned_chapter(self, chapter_id: str, owner_id: str) -> Chapter:
        chapter = self.get_chapter(chapter_id)
        if chapter.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu chương này.")
        return chapter

    def list_chapters(self, novel_id: str) -> List[Chapter]:
        with self._lock:
            items = [c for c in self.chapters.values() if c.novel_id == novel_id]
        return sorted(items, key=lambda c: c.order_index)

    # -- job -----------------------------------------------------------------

    def create_job(self, job: TtsJob) -> TtsJob:
        with self._lock:
            self.jobs[job.job_id] = job
            return job

    def get_job(self, job_id: str) -> TtsJob:
        job = self.jobs.get(job_id)
        if job is None:
            raise NotFoundError("Không tìm thấy job.")
        return job

    def owned_job(self, job_id: str, owner_id: str) -> TtsJob:
        job = self.get_job(job_id)
        if job.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu job này.")
        return job

    def find_job_by_fingerprint(self, owner_id: str, chapter_id: str, fingerprint: str) -> Optional[TtsJob]:
        """Tim job da co cho CUNG noi dung + giong + thiet lap (idempotency)."""
        with self._lock:
            for job in self.jobs.values():
                if (
                    job.owner_id == owner_id
                    and job.chapter_id == chapter_id
                    and job.content_hash == fingerprint
                    and job.status.value != "failed"
                ):
                    return job
        return None

    def list_jobs(self, owner_id: str, chapter_id: Optional[str] = None) -> List[TtsJob]:
        with self._lock:
            items = [j for j in self.jobs.values() if j.owner_id == owner_id]
        if chapter_id:
            items = [j for j in items if j.chapter_id == chapter_id]
        return sorted(items, key=lambda j: j.created_at, reverse=True)

    # -- audio track ---------------------------------------------------------

    def create_track(self, track: AudioTrack) -> AudioTrack:
        with self._lock:
            self.tracks[track.track_id] = track
            return track

    def track_for_chapter(self, chapter_id: str) -> Optional[AudioTrack]:
        with self._lock:
            items = [t for t in self.tracks.values() if t.chapter_id == chapter_id]
        return sorted(items, key=lambda t: t.created_at, reverse=True)[0] if items else None


# -----------------------------------------------------------------------------
# Lua chon adapter theo cau hinh
# -----------------------------------------------------------------------------


def build_identity(settings: Settings) -> IdentityAdapter:
    """
    Appwrite khi da cau hinh du, nguoc lai dung mock.

    Da khai bao cau hinh ma cau hinh sai thi NEM LOI - tuyet doi khong am tham
    lui ve mock, vi nguoi van hanh se tuong dang chay that.
    """
    if settings.appwrite.configured:
        from server.appwrite_adapter import AppwriteIdentityAdapter

        return AppwriteIdentityAdapter(settings.appwrite)
    return MockIdentityAdapter()


def build_storage(settings: Settings) -> StorageAdapter:
    """R2 khi da cau hinh du, nguoc lai luu xuong dia cuc bo."""
    if settings.r2.configured:
        from server.r2_adapter import R2StorageAdapter

        return R2StorageAdapter(settings.r2)
    return LocalStorageAdapter(settings.var_dir / "storage")
