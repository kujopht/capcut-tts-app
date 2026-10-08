"""
`QuizStore` — giao dien luu tru quiz + cac ban ghi RIENG TU (khong xuat API).

Moi phep ghi la MOT chuyen trang thai nguyen tu (compare-and-swap) — khong
phai "doc - sua - ghi" do service tu ghep. Hai ban cai dat:
  * `LocalQuizStore` (`local_store.py`): file JSON duoi `var_dir/quiz`, khoa ghi
    (luong + lien tien trinh) + temp file/fsync/`os.replace`.
  * `AppwriteQuizStore` (`appwrite_store.py`): documentId tat dinh lam "claim"
    nguyen tu (Appwrite tu choi id trung voi 409). Parity voi Appwrite hosted
    CHUA duoc xac minh — chi test bang fake HTTP.

Service (`service.py`) kiem danh tinh/so huu/entitlement TRUOC khi goi store,
cho CA HAI adapter; store chi bao dam tinh nguyen tu va bat bien.
"""

from __future__ import annotations

from typing import List, Optional, Protocol, Tuple

from pydantic import BaseModel, ConfigDict, Field

from server.quiz.contracts import (
    CONTRACT_VERSION, MODE_ID, MODE_VERSION, DateTimeUtc, DraftQuestion, ExplanationText, Id, LastAttempt, MAX_OPTIONS,
    PublicQuestion, PublicQuizSnapshot, QuestionResult, Receipt, Revision, SessionPhase, ShareId,
    Sha256Hex, ThemeId, Title, CueName, AttemptCount,
)


# -- Loi co kieu ---------------------------------------------------------------

class QuizStoreError(Exception):
    """Goc cua moi loi store."""


class StoreNotFound(QuizStoreError):
    pass


class RevisionConflict(QuizStoreError):
    def __init__(self, current_revision: Optional[int] = None, message: str = "revision conflict"):
        super().__init__(message)
        self.current_revision = current_revision


class QuotaExceeded(QuizStoreError):
    def __init__(self, limit: int, used: int):
        super().__init__(f"published quota exceeded ({used}/{limit})")
        self.limit = limit
        self.used = used


class PublishConflict(QuizStoreError):
    """Hai lan publish cung luc tranh cung mot so version."""


class StoreUnavailable(QuizStoreError):
    """Ha tang luu tru tam thoi khong dung duoc (503, thu lai duoc)."""


# -- Ban ghi rieng tu ------------------------------------------------------------

class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class DraftRecord(_Record):
    draft_id: Id
    owner_user_id: str = Field(min_length=1, max_length=128)
    title: Title
    theme_id: ThemeId
    questions: List[DraftQuestion] = Field(max_length=200)
    revision: Revision
    share_id: Optional[ShareId] = None
    published_version: Optional[Revision] = None
    created_at: DateTimeUtc
    updated_at: DateTimeUtc


class AnswerKey(_Record):
    """Dap an cua MOT cau trong mot version. Khong bao gio ra khoi server truoc reveal."""

    question_id: Id
    correct_option_ids: List[Id] = Field(min_length=1, max_length=MAX_OPTIONS)
    explanation: ExplanationText


class PublishContent(_Record):
    """Noi dung service da dung san cho mot lan publish (chua co share/version)."""

    title: Title
    theme_id: ThemeId
    public_questions: List[PublicQuestion] = Field(min_length=1, max_length=200)
    keys: List[AnswerKey] = Field(min_length=1, max_length=200)
    content_hash: Sha256Hex


class ShareRecord(_Record):
    share_id: ShareId
    owner_user_id: str = Field(min_length=1, max_length=128)
    draft_id: Id
    latest_version: Revision
    created_at: DateTimeUtc


class VersionRecord(_Record):
    """Version BAT BIEN: snapshot cong khai + khoa rieng, ghi mot lan."""

    share_id: ShareId
    version: Revision
    draft_id: Id
    draft_revision: Revision
    owner_user_id: str = Field(min_length=1, max_length=128)
    public: PublicQuizSnapshot
    keys: List[AnswerKey] = Field(min_length=1, max_length=200)


class StoredReceipt(_Record):
    request_id: Id
    payload_hash: Sha256Hex
    receipt: Receipt


class SessionRecord(_Record):
    session_id: Id
    participant_user_id: str = Field(min_length=1, max_length=128)
    share_id: ShareId
    version: Revision
    state_revision: Revision
    question_index: int = Field(ge=0, le=199)
    phase: SessionPhase
    attempts_used: AttemptCount
    eliminated_option_ids: List[Id] = Field(max_length=MAX_OPTIONS)
    last_attempt: Optional[LastAttempt] = None
    timed_out: bool = False
    deadline_at: Optional[DateTimeUtc] = None
    score: int = Field(ge=0, le=200)
    results: List[QuestionResult] = Field(max_length=200)
    receipts: List[StoredReceipt] = Field(max_length=400)
    cue: Optional[CueName] = None
    created_at: DateTimeUtc
    updated_at: DateTimeUtc
    finished_at: Optional[DateTimeUtc] = None


class GrantRecord(_Record):
    """Grant Pro TONG HOP cuc bo (khong gan thanh toan). Khong co route HTTP cap grant."""

    grant_id: Id
    user_id: str = Field(min_length=1, max_length=128)
    plan: str = Field(pattern=r"^pro$")
    created_at: DateTimeUtc
    created_by: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=300)
    expires_at: Optional[DateTimeUtc] = None
    revoked_at: Optional[DateTimeUtc] = None
    revoked_by: Optional[str] = Field(default=None, max_length=128)
    revoke_reason: Optional[str] = Field(default=None, max_length=300)


def build_version(share_id: str, version_no: int, draft: DraftRecord,
                  content: PublishContent, now: str) -> VersionRecord:
    """Dung chung cho moi adapter: snapshot cong khai duoc dong dau share/version."""
    public = PublicQuizSnapshot(
        contract_version=CONTRACT_VERSION, share_id=share_id, version=version_no,
        title=content.title, theme_id=content.theme_id,
        mode={"id": MODE_ID, "version": MODE_VERSION},
        question_count=len(content.public_questions),
        questions=list(content.public_questions), content_hash=content.content_hash,
        published_at=now,
    )
    return VersionRecord(share_id=share_id, version=version_no, draft_id=draft.draft_id,
                         draft_revision=draft.revision, owner_user_id=draft.owner_user_id,
                         public=public, keys=list(content.keys))


# -- Giao dien -------------------------------------------------------------------

class QuizStore(Protocol):
    mode: str

    # drafts
    def create_draft(self, record: DraftRecord) -> DraftRecord: ...
    def get_draft(self, draft_id: str) -> Optional[DraftRecord]: ...
    def list_drafts(self, owner_user_id: str, *, limit: int,
                    offset: int) -> Tuple[List[DraftRecord], int]: ...
    def replace_draft(self, record: DraftRecord, *, expected_revision: int) -> DraftRecord:
        """CAS: hien tai phai o `expected_revision`, `record.revision == expected+1`."""
    def delete_draft(self, draft_id: str, *, expected_revision: int) -> None: ...

    # publish (quota + version + share NGUYEN TU)
    def publish(self, *, owner_user_id: str, draft_id: str, expected_revision: int,
                content: PublishContent, new_share_id: str, quota_limit: int,
                now: str) -> Tuple[ShareRecord, VersionRecord, bool]:
        """Tra `(share, version, replayed)`. `replayed=True` khi draft o revision nay
        da duoc publish (khong tao version moi, khong ton quota)."""
    def count_published(self, owner_user_id: str) -> int: ...
    def get_share(self, share_id: str) -> Optional[ShareRecord]: ...
    def get_version(self, share_id: str, version: int) -> Optional[VersionRecord]: ...

    # sessions
    def create_session(self, record: SessionRecord) -> SessionRecord: ...
    def get_session(self, session_id: str) -> Optional[SessionRecord]: ...
    def replace_session(self, record: SessionRecord, *,
                        expected_state_revision: int) -> SessionRecord: ...

    # grants
    def put_grant(self, record: GrantRecord) -> GrantRecord: ...
    def list_grants(self, user_id: str) -> List[GrantRecord]: ...
