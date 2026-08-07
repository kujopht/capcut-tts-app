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
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence, Set

from server.config import ConfigError, Settings
from server.domain import (
    AudioTrack,
    Chapter,
    Novel,
    Profile,
    PublishState,
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
    def signed_url(self, key: str, expires_seconds: int = 3600,
                   download_name: Optional[str] = None) -> Optional[str]: ...

    def delete(self, key: str) -> bool:
        """Xoa mot object. Tra True neu da xoa, False neu von khong ton tai."""
        ...


class MetadataStore(Protocol):
    """
    Kho metadata: novels, chapters, tts_jobs, audio_tracks.

    HAI ban hien thuc PHAI tuan theo cung contract nay - `MockMetadataStore`
    (trong bo nho) va `AppwriteMetadataStore`. Tang route chi duoc goi qua day,
    khong bao gio cham thang Appwrite.

    CONTRACT chung cho moi thao tac GHI:
    - Kiem tra quyen so huu o phia server. `user_id` do client gui len KHONG
      bao gio duoc tin; chu so huu luon lay tu token da xac minh.
    - Khong tim thay -> `NotFoundError`. Sai chu so huu -> `PermissionDenied`.
    - Thao tac ghi phai BEN VUNG truoc khi tra ve. Goi xong ma doc lai phai
      thay dung trang thai moi, khong phu thuoc object tam o tang tren.
    """

    # -- novel ---------------------------------------------------------------
    def create_novel(self, novel: Novel) -> Novel: ...
    def get_novel(self, novel_id: str) -> Novel: ...
    def owned_novel(self, novel_id: str, owner_id: str) -> Novel: ...
    def list_novels(self, owner_id: Optional[str] = None,
                    published_only: bool = False) -> List[Novel]: ...

    def publish_novel(self, novel_id: str, owner_id: str) -> Novel:
        """
        Chuyen novel sang `published` VA luu ben vung.

        - Chi chu so huu moi duoc goi; nguoi khac -> `PermissionDenied`.
        - IDEMPOTENT: goi lai tren novel da `published` khong loi, khong tao
          du lieu trung, va tra ve chinh novel do.
        - Ban Appwrite con mo them quyen doc cong khai; quyen update/delete
          VAN chi thuoc chu so huu.
        - Luu that bai thi NEM LOI - tuyet doi khong tra ve nhu da thanh cong.
        """
        ...

    def update_novel(self, novel_id: str, owner_id: str,
                     fields: Dict[str, Any]) -> Novel:
        """Sua truyen. Chi chu so huu; chi nhan cac truong nguoi dung duoc sua."""
        ...

    def unpublish_novel(self, novel_id: str, owner_id: str) -> Novel:
        """Dua truyen ve ban nhap VA thu hoi quyen doc cong khai. Idempotent."""
        ...

    def delete_novel(self, novel_id: str, owner_id: str) -> None: ...

    # -- chapter -------------------------------------------------------------
    def create_chapter(self, chapter: Chapter) -> Chapter: ...
    def get_chapter(self, chapter_id: str) -> Chapter: ...
    def owned_chapter(self, chapter_id: str, owner_id: str) -> Chapter: ...
    def list_chapters(self, novel_id: str) -> List[Chapter]: ...

    def update_chapter(self, chapter_id: str, owner_id: str,
                       fields: Dict[str, Any]) -> Chapter: ...
    def delete_chapter(self, chapter_id: str, owner_id: str) -> None: ...

    def reorder_chapters(self, novel_id: str, owner_id: str,
                         chapter_ids: Sequence[str]) -> List[Chapter]:
        """
        Dat lai `order_index` cua CA truyen theo dung thu tu `chapter_ids`.

        - Chi chu so huu truyen; nguoi khac -> `PermissionDenied`.
        - `chapter_ids` phai la DUNG tap chuong cua truyen do, khong thieu khong
          thua. Lech mot cai -> `ValueError`, va KHONG duoc ghi gi ca. Rang buoc
          nay la thu chan viec lam mat chuong: khong the "sap xep lai" ma vo tinh
          bo roi mot chuong ra ngoai danh sach.
        - Chi doi `order_index`. Tieu de, noi dung, audio va trang thai publish
          khong duoc dong toi.
        - Tra ve danh sach chuong sau khi doi, da sap theo thu tu moi.
        """
        ...

    # -- tts job -------------------------------------------------------------
    def create_job(self, job: TtsJob) -> TtsJob: ...
    def save_job(self, job: TtsJob) -> TtsJob: ...
    def get_job(self, job_id: str) -> TtsJob: ...
    def owned_job(self, job_id: str, owner_id: str) -> TtsJob: ...
    def find_job_by_fingerprint(self, owner_id: str, chapter_id: str,
                                fingerprint: str) -> Optional[TtsJob]: ...
    def list_jobs(self, owner_id: str,
                  chapter_id: Optional[str] = None) -> List[TtsJob]: ...

    def delete_job(self, job_id: str) -> None: ...

    # -- audio track ---------------------------------------------------------
    def create_track(self, track: AudioTrack) -> AudioTrack: ...
    def track_for_chapter(self, chapter_id: str) -> Optional[AudioTrack]: ...
    def tracks_for_chapter(self, chapter_id: str) -> List[AudioTrack]: ...

    def audio_by_chapter(self, chapter_ids: Sequence[str]) -> Dict[str, str]:
        """
        Chuong nao DA co audio, va audio moi nhat tao luc nao.

        Tra ve `{chapter_id: created_at cua track moi nhat}`. Chuong khong co
        audio thi khong xuat hien trong ket qua.

        Ly do ton tai: danh sach chuong can hai dieu — co audio hay khong, va
        audio da cu hon lan sua noi dung gan nhat hay chua. Hoi tung chuong mot
        lam so truy van tang tuyen tinh theo so chuong. Ban cai dat PHAI tra loi
        bang so truy van khong phu thuoc so chuong (hang so, hoac theo lo) — day
        la ca ly do ky thuat cua ham nay.

        MOT truy van cho ca hai dieu, khong phai hai truy van.

        - Danh sach rong -> tra ve dict rong, KHONG duoc goi kho.
        - Chi tra ve moc thoi gian, khong tra ve URL ky: trang danh sach chua
          phat gi ca.
        """
        ...

    def delete_track(self, track_id: str) -> None: ...


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

    def delete(self, key: str) -> bool:
        target = self._path(key)
        if not target.is_file():
            return False
        target.unlink()
        return True

    def signed_url(self, key: str, expires_seconds: int = 3600,
                   download_name: Optional[str] = None) -> Optional[str]:
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

    KHONG PHAI kho ben vung. Du lieu chi song trong vong doi tien trinh: khoi
    dong lai backend la mat sach. Chi dung cho phat trien va kiem thu cuc bo.
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

    def publish_novel(self, novel_id: str, owner_id: str) -> Novel:
        """
        Xuat ban novel - xem contract o `MetadataStore.publish_novel`.

        Dung `replace()` roi moi gan lai vao kho, thay vi doi tai cho: neu co
        loi xay ra giua chung thi ban ghi dang luu VAN NGUYEN VEN, khong bao
        gio ket o trang thai nua voi. Day cung la cach ban Appwrite hanh xu
        (PATCH thanh cong hoac khong doi gi ca).
        """
        with self._lock:
            current = self.owned_novel(novel_id, owner_id)
            # Idempotent: da `published` thi khong co gi de doi
            if current.state == PublishState.PUBLISHED:
                return current
            published = replace(
                current, state=PublishState.PUBLISHED, updated_at=now_iso()
            )
            self.novels[published.novel_id] = published
            return published

    #: Chi nhung truong nay moi cho nguoi dung sua. `state`, `owner_id`,
    #: `novel_id` deu do SERVER quyet dinh.
    NOVEL_EDITABLE = ("title", "description", "tags")

    def update_novel(self, novel_id: str, owner_id: str,
                     fields: Dict[str, Any]) -> Novel:
        with self._lock:
            current = self.owned_novel(novel_id, owner_id)
            allowed = {k: v for k, v in fields.items() if k in self.NOVEL_EDITABLE}
            updated = replace(current, **allowed, updated_at=now_iso())
            self.novels[novel_id] = updated
            return updated

    def unpublish_novel(self, novel_id: str, owner_id: str) -> Novel:
        with self._lock:
            current = self.owned_novel(novel_id, owner_id)
            if current.state != PublishState.PUBLISHED:
                return current
            reverted = replace(
                current, state=PublishState.DRAFT, updated_at=now_iso()
            )
            self.novels[novel_id] = reverted
            return reverted

    def delete_novel(self, novel_id: str, owner_id: str) -> None:
        with self._lock:
            self.owned_novel(novel_id, owner_id)
            self.novels.pop(novel_id, None)

    # -- chapter -------------------------------------------------------------

    #: `owner_id`, `novel_id`, `state` khong cho client sua.
    CHAPTER_EDITABLE = ("title", "content", "order_index")

    def update_chapter(self, chapter_id: str, owner_id: str,
                       fields: Dict[str, Any]) -> Chapter:
        with self._lock:
            current = self.owned_chapter(chapter_id, owner_id)
            allowed = {k: v for k, v in fields.items() if k in self.CHAPTER_EDITABLE}
            updated = replace(current, **allowed, updated_at=now_iso())
            self.chapters[chapter_id] = updated
            return updated

    def delete_chapter(self, chapter_id: str, owner_id: str) -> None:
        with self._lock:
            self.owned_chapter(chapter_id, owner_id)
            self.chapters.pop(chapter_id, None)

    def reorder_chapters(self, novel_id: str, owner_id: str,
                         chapter_ids: Sequence[str]) -> List[Chapter]:
        """Xem contract o `MetadataStore.reorder_chapters`."""
        self.owned_novel(novel_id, owner_id)
        with self._lock:
            current = {c.chapter_id for c in self.chapters.values()
                       if c.novel_id == novel_id}
            wanted = list(dict.fromkeys(chapter_ids))
            if set(wanted) != current or len(wanted) != len(chapter_ids):
                raise ValueError(
                    "Danh sách thứ tự phải gồm đúng các chương của truyện này.")

            # Ghi sau khi da kiem tra xong: sai mot cai thi khong doi gi ca.
            #
            # KHONG dong vao `updated_at`: sap xep lai khong sua noi dung chuong,
            # ma `updated_at` chinh la moc dung de biet audio con khop noi dung
            # hay khong (xem `_audio_outdated` trong main.py). Bump o day thi moi
            # chuong deu bi bao "audio cu" oan sau mot lan keo thu tu.
            for position, chapter_id in enumerate(wanted, start=1):
                chapter = self.chapters[chapter_id]
                self.chapters[chapter_id] = replace(chapter, order_index=position)
            return [self.chapters[cid] for cid in wanted]

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
        """Ghi job lan dau - day chinh la luc trang thai `pending` duoc luu."""
        with self._lock:
            self.jobs[job.job_id] = job
            return job

    def save_job(self, job: TtsJob) -> TtsJob:
        """
        Ghi lai trang thai job sau moi transition.

        Ban mock luu cung mot doi tuong nen thao tac nay "co ve" thua - nhung
        `AppwriteMetadataStore.save_job()` moi la ban that: khong goi thi moi
        thay doi trang thai deu bien mat khi doc lai tu Appwrite. Giu chung
        mot giao dien de job runner khong phai biet dang chay che do nao.
        """
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

    def delete_job(self, job_id: str) -> None:
        with self._lock:
            self.jobs.pop(job_id, None)

    # -- audio track ---------------------------------------------------------

    def create_track(self, track: AudioTrack) -> AudioTrack:
        with self._lock:
            self.tracks[track.track_id] = track
            return track

    def track_for_chapter(self, chapter_id: str) -> Optional[AudioTrack]:
        with self._lock:
            items = [t for t in self.tracks.values() if t.chapter_id == chapter_id]
        return sorted(items, key=lambda t: t.created_at, reverse=True)[0] if items else None

    def tracks_for_chapter(self, chapter_id: str) -> List[AudioTrack]:
        with self._lock:
            return [t for t in self.tracks.values() if t.chapter_id == chapter_id]

    def audio_by_chapter(self, chapter_ids: Sequence[str]) -> Dict[str, str]:
        """Mot luot duy nhat qua bang track — xem contract o `MetadataStore`."""
        wanted = set(chapter_ids)
        if not wanted:
            return {}
        newest: Dict[str, str] = {}
        with self._lock:
            for track in self.tracks.values():
                if track.chapter_id not in wanted:
                    continue
                seen = newest.get(track.chapter_id)
                if seen is None or track.created_at > seen:
                    newest[track.chapter_id] = track.created_at
        return newest

    def delete_track(self, track_id: str) -> None:
        with self._lock:
            self.tracks.pop(track_id, None)


# -----------------------------------------------------------------------------
# Lua chon adapter theo cau hinh
# -----------------------------------------------------------------------------


def build_identity(settings: Settings) -> IdentityAdapter:
    """
    Chon adapter danh tinh theo DATA_BACKEND (tuong minh).

    `appwrite` ma thieu/sai cau hinh thi NEM LOI - tuyet doi khong am tham lui
    ve mock, vi nguoi van hanh se tuong dang chay that.
    """
    if settings.data_backend == "appwrite":
        from server.appwrite_adapter import AppwriteIdentityAdapter

        return AppwriteIdentityAdapter(settings.appwrite)
    if settings.data_backend != "mock":
        raise ConfigError(f"DATA_BACKEND không hợp lệ: {settings.data_backend!r}")
    return MockIdentityAdapter()


def build_storage(settings: Settings) -> StorageAdapter:
    """Chon adapter luu tru theo STORAGE_BACKEND (tuong minh)."""
    if settings.storage_backend == "r2":
        from server.r2_adapter import R2StorageAdapter

        return R2StorageAdapter(settings.r2)
    if settings.storage_backend != "local":
        raise ConfigError(f"STORAGE_BACKEND không hợp lệ: {settings.storage_backend!r}")
    return LocalStorageAdapter(settings.var_dir / "storage")


def build_metadata_store(settings: Settings) -> MetadataStore:
    """Kho metadata: Appwrite khi DATA_BACKEND=appwrite, nguoc lai trong bo nho."""
    if settings.data_backend == "appwrite":
        from server.appwrite_store import AppwriteMetadataStore

        return AppwriteMetadataStore(settings.appwrite)
    return MockMetadataStore()
