"""
`LocalQuizStore` — ban ben vung cuc bo cua `QuizStore` cho Phase 1.

Namespace RIENG: `<var_dir>/quiz/` (file `store.json` + `store.lock`), khong
dung chung file voi `MockMetadataStore`/`LocalStorageAdapter` cua host.

Tinh nguyen tu:
  * MOI phep (doc va ghi) chay duoi khoa luong (`threading.RLock`) VA khoa
    lien tien trinh tren `store.lock` (`msvcrt.locking` / `fcntl.flock` — he
    dieu hanh tu nha khi tien trinh chet, khong de lai khoa mo coi).
  * Ghi: noi dung moi -> file tam cung thu muc -> flush + fsync -> `os.replace`
    (thay nguyen tu tren NTFS va POSIX). Tien trinh chet giua chung thi
    `store.json` van la ban CU hop le; file tam mo coi bi don o lan mo sau.
  * Moi phep doc lai file duoi khoa (khong cache) — hai tien trinh/hai worker
    uvicorn dung chung thu muc van thay du lieu cua nhau.

Gioi han co y: toan bo du lieu nam trong MOT file JSON, ghi lai ca file moi lan.
Du cho Phase 1 local/QA (vai nghin ban ghi); khong phai backend production.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from server.quiz.store import (
    DraftRecord, GrantRecord, PublishConflict, PublishContent, QuotaExceeded,
    RevisionConflict, SessionRecord, ShareRecord, StoreNotFound, StoreUnavailable,
    VersionRecord, build_version,
)

STATE_FILE = "store.json"
LOCK_FILE = "store.lock"
TMP_PREFIX = "store.json.tmp-"
FORMAT_VERSION = 1
LOCK_TIMEOUT_S = 30.0


def _empty_state() -> Dict[str, Any]:
    return {"format_version": FORMAT_VERSION, "drafts": {}, "shares": {},
            "versions": {}, "version_keys": {}, "sessions": {}, "grants": {}}


class _InterProcessLock:
    """Khoa doc quyen tren mot file khoa; OS tu nha khi handle/tien trinh dong."""

    def __init__(self, path: Path, timeout: float = LOCK_TIMEOUT_S):
        self._path = path
        self._timeout = timeout
        self._fh = None

    def __enter__(self) -> "_InterProcessLock":
        fh = open(self._path, "a+b")
        deadline = time.monotonic() + self._timeout
        try:
            if os.name == "nt":
                import msvcrt
                while True:
                    try:
                        fh.seek(0)
                        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() > deadline:
                            raise StoreUnavailable("quiz store lock timeout")
                        time.sleep(0.005)
            else:
                import fcntl
                while True:
                    try:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic() > deadline:
                            raise StoreUnavailable("quiz store lock timeout")
                        time.sleep(0.005)
        except BaseException:
            fh.close()
            raise
        self._fh = fh
        return self

    def __exit__(self, *exc: Any) -> None:
        fh, self._fh = self._fh, None
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


class LocalQuizStore:
    mode = "local"

    def __init__(self, root: Path):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._state_path = self._root / STATE_FILE
        self._lock_path = self._root / LOCK_FILE
        self._thread_lock = threading.RLock()
        with self._locked():
            self._cleanup_temp_files()

    @classmethod
    def under_var_dir(cls, var_dir: Path) -> "LocalQuizStore":
        return cls(Path(var_dir) / "quiz")

    # -- ha tang file ---------------------------------------------------------

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        with self._thread_lock:
            with _InterProcessLock(self._lock_path):
                yield

    def _cleanup_temp_files(self) -> None:
        for p in self._root.glob(TMP_PREFIX + "*"):
            with contextlib.suppress(OSError):
                p.unlink()

    def _load(self) -> Dict[str, Any]:
        try:
            raw = self._state_path.read_bytes()
        except FileNotFoundError:
            return _empty_state()
        except OSError as exc:
            raise StoreUnavailable(f"cannot read quiz store: {exc}") from exc
        try:
            state = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            # KHONG tu reset ve rong: mat du lieu am tham con te hon bao loi.
            raise StoreUnavailable("quiz store file is corrupt") from exc
        if not isinstance(state, dict) or state.get("format_version") != FORMAT_VERSION:
            raise StoreUnavailable("unsupported quiz store format")
        for key, value in _empty_state().items():
            state.setdefault(key, value)
        return state

    def _write(self, state: Dict[str, Any]) -> None:
        data = json.dumps(state, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
        tmp = self._root / f"{TMP_PREFIX}{os.getpid()}-{uuid.uuid4().hex}"
        try:
            with open(tmp, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            self._replace(tmp, self._state_path)
        except OSError as exc:
            with contextlib.suppress(OSError):
                tmp.unlink()
            raise StoreUnavailable(f"cannot write quiz store: {exc}") from exc
        if os.name != "nt":
            with contextlib.suppress(OSError):
                fd = os.open(self._root, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)

    @staticmethod
    def _replace(src: Path, dst: Path) -> None:
        # Windows: trinh quet virus/indexer co the giu handle mot nhip ngan.
        for attempt in range(20):
            try:
                os.replace(src, dst)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.01)

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[Dict[str, Any]]:
        """Doc -> sua -> ghi NGUYEN TU duoi khoa. Exception = khong ghi gi."""
        with self._locked():
            state = self._load()
            yield state
            self._write(state)

    def _read(self) -> Dict[str, Any]:
        with self._locked():
            return self._load()

    # -- drafts -----------------------------------------------------------------

    def create_draft(self, record: DraftRecord) -> DraftRecord:
        with self._transaction() as st:
            if record.draft_id in st["drafts"]:
                raise RevisionConflict(None, "draft id already exists")
            st["drafts"][record.draft_id] = record.model_dump(mode="json")
        return record

    def get_draft(self, draft_id: str) -> Optional[DraftRecord]:
        raw = self._read()["drafts"].get(draft_id)
        return DraftRecord.model_validate(raw) if raw else None

    def list_drafts(self, owner_user_id: str, *, limit: int,
                    offset: int) -> Tuple[List[DraftRecord], int]:
        rows = [DraftRecord.model_validate(r) for r in self._read()["drafts"].values()
                if r.get("owner_user_id") == owner_user_id]
        rows.sort(key=lambda r: (r.updated_at, r.draft_id), reverse=True)
        return rows[offset:offset + limit], len(rows)

    def replace_draft(self, record: DraftRecord, *, expected_revision: int) -> DraftRecord:
        with self._transaction() as st:
            raw = st["drafts"].get(record.draft_id)
            if raw is None:
                raise StoreNotFound(record.draft_id)
            current = DraftRecord.model_validate(raw)
            if current.revision != expected_revision or record.revision != expected_revision + 1:
                raise RevisionConflict(current.revision)
            if current.owner_user_id != record.owner_user_id:
                raise StoreNotFound(record.draft_id)
            # share/published_version chi do `publish` doi.
            record = record.model_copy(update={"share_id": current.share_id,
                                               "published_version": current.published_version})
            st["drafts"][record.draft_id] = record.model_dump(mode="json")
        return record

    def delete_draft(self, draft_id: str, *, expected_revision: int) -> None:
        with self._transaction() as st:
            raw = st["drafts"].get(draft_id)
            if raw is None:
                raise StoreNotFound(draft_id)
            if raw["revision"] != expected_revision:
                raise RevisionConflict(raw["revision"])
            del st["drafts"][draft_id]

    # -- publish ------------------------------------------------------------------

    def publish(self, *, owner_user_id: str, draft_id: str, expected_revision: int,
                content: PublishContent, new_share_id: str, quota_limit: int,
                now: str) -> Tuple[ShareRecord, VersionRecord, bool]:
        with self._transaction() as st:
            raw = st["drafts"].get(draft_id)
            if raw is None or raw.get("owner_user_id") != owner_user_id:
                raise StoreNotFound(draft_id)
            draft = DraftRecord.model_validate(raw)
            if draft.revision != expected_revision:
                raise RevisionConflict(draft.revision)

            if draft.share_id:
                share = ShareRecord.model_validate(st["shares"][draft.share_id])
                latest = self._version_from(st, share.share_id, share.latest_version)
                if latest is not None and latest.draft_revision == draft.revision:
                    return share, latest, True
                version_no = share.latest_version + 1
            else:
                used = sum(1 for s in st["shares"].values()
                           if s.get("owner_user_id") == owner_user_id)
                if used >= quota_limit:
                    raise QuotaExceeded(quota_limit, used)
                if new_share_id in st["shares"]:
                    raise PublishConflict("share id collision")
                share = ShareRecord(share_id=new_share_id, owner_user_id=owner_user_id,
                                    draft_id=draft_id, latest_version=1, created_at=now)
                version_no = 1

            key = _version_key(share.share_id, version_no)
            if key in st["versions"]:
                raise PublishConflict("version already exists")  # bat bien: khong ghi de
            version = build_version(share.share_id, version_no, draft, content, now)
            share = share.model_copy(update={"latest_version": version_no})
            st["versions"][key] = version.public.model_dump(mode="json") | {
                "_draft_id": draft.draft_id, "_draft_revision": draft.revision,
                "_owner_user_id": owner_user_id}
            st["version_keys"][key] = [k.model_dump(mode="json") for k in version.keys]
            st["shares"][share.share_id] = share.model_dump(mode="json")
            st["drafts"][draft_id] = draft.model_copy(update={
                "share_id": share.share_id, "published_version": version_no,
            }).model_dump(mode="json")
        return share, version, False

    def count_published(self, owner_user_id: str) -> int:
        return sum(1 for s in self._read()["shares"].values()
                   if s.get("owner_user_id") == owner_user_id)

    def get_share(self, share_id: str) -> Optional[ShareRecord]:
        raw = self._read()["shares"].get(share_id)
        return ShareRecord.model_validate(raw) if raw else None

    def get_version(self, share_id: str, version: int) -> Optional[VersionRecord]:
        return self._version_from(self._read(), share_id, version)

    @staticmethod
    def _version_from(st: Dict[str, Any], share_id: str, version: int) -> Optional[VersionRecord]:
        key = _version_key(share_id, version)
        pub = st["versions"].get(key)
        keys = st["version_keys"].get(key)
        if pub is None or keys is None:
            return None
        pub = dict(pub)
        meta = {k: pub.pop(k) for k in ("_draft_id", "_draft_revision", "_owner_user_id")}
        return VersionRecord.model_validate({
            "share_id": share_id, "version": version, "draft_id": meta["_draft_id"],
            "draft_revision": meta["_draft_revision"],
            "owner_user_id": meta["_owner_user_id"], "public": pub, "keys": keys,
        })

    # -- sessions -------------------------------------------------------------------

    def create_session(self, record: SessionRecord) -> SessionRecord:
        with self._transaction() as st:
            if record.session_id in st["sessions"]:
                raise RevisionConflict(None, "session id already exists")
            st["sessions"][record.session_id] = record.model_dump(mode="json")
        return record

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        raw = self._read()["sessions"].get(session_id)
        return SessionRecord.model_validate(raw) if raw else None

    def replace_session(self, record: SessionRecord, *,
                        expected_state_revision: int) -> SessionRecord:
        with self._transaction() as st:
            raw = st["sessions"].get(record.session_id)
            if raw is None:
                raise StoreNotFound(record.session_id)
            if (raw["state_revision"] != expected_state_revision
                    or record.state_revision != expected_state_revision + 1
                    or raw["participant_user_id"] != record.participant_user_id):
                raise RevisionConflict(raw["state_revision"])
            st["sessions"][record.session_id] = record.model_dump(mode="json")
        return record

    # -- grants -------------------------------------------------------------------------

    def put_grant(self, record: GrantRecord) -> GrantRecord:
        with self._transaction() as st:
            st["grants"][record.grant_id] = record.model_dump(mode="json")
        return record

    def list_grants(self, user_id: str) -> List[GrantRecord]:
        rows = [GrantRecord.model_validate(g) for g in self._read()["grants"].values()
                if g.get("user_id") == user_id]
        rows.sort(key=lambda g: (g.created_at, g.grant_id))
        return rows


def _version_key(share_id: str, version: int) -> str:
    return f"{share_id}/{version}"

