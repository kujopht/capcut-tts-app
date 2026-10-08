"""
Hop dong API quiz (Phase 1) — NGUON SCHEMA DUY NHAT.

Moi DTO tren day la Pydantic v2: `extra="forbid"`, `strict=True`, moi chuoi/
danh sach deu co tran, va cac luat cheo-truong (thanh vien, duy nhat, so lan
tra loi, reveal) nam trong validator. `server/quiz/codegen.py` xuat JSON Schema
TAT DINH tu cac model duoc liet ke trong `PUBLIC_MODELS` va sinh
`web/src/features/quiz/contracts/generated.ts` + fixtures. KHONG viet tay mot
ban Zod/TS song song.

Ranh gioi bi mat:
  * `DraftQuestion` (co `correct_option_ids`) CHI xuat hien trong DTO cua
    CHU SO HUU (`CreatorDraft`). Ban cong khai (`PublicQuestion`) va view cua
    nguoi choi (`ParticipantView`) KHONG co truong key nao.
  * Khoa dap an cua mot version da publish la model RIENG trong
    `server/quiz/store.py` (`AnswerKey`, `VersionRecord`) — khong nam trong
    `PUBLIC_MODELS`, khong qua union chung nao.
  * `owner_user_id` KHONG BAO GIO doc tu client: request body khong co truong
    do (extra=forbid se tra 422), service lay tu ho so da resolve.

Luat Tactical Summon (mode v1 / scoring v1): boolean 1 lan; single
min(2, so_lua_chon-1); multiple dung-tron-tap 2 lan; 1 diem/cau dung (bat ky
lan nao); khong thuong toc do. Xem `server/quiz/rules.py`.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional, Union

from pydantic import (AfterValidator, BaseModel, ConfigDict, Field,
                      StringConstraints, model_validator)

CONTRACT_VERSION = "1.0.0"
SCHEMA_VERSION = 1
MODE_ID = "tactical-summon"
MODE_VERSION = 1
SCORING_VERSION = 1

# -- Tran (bounded) ----------------------------------------------------------
MAX_QUESTIONS = 200
MIN_OPTIONS = 2
MAX_OPTIONS = 8
TITLE_MAX = 120
PROMPT_MAX = 1000
OPTION_MAX = 300
EXPLANATION_MAX = 1000
TIME_LIMIT_MIN_MS = 5_000
TIME_LIMIT_MAX_MS = 120_000
CSV_MAX_CHARS = 512_000
CSV_MAX_ROWS = MAX_QUESTIONS
CSV_MAX_ERRORS = 500
LIST_PAGE_MAX = 50
REVISION_MAX = 2**53 - 1

UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
SHARE_ID_PATTERN = r"^[A-Za-z0-9]{16}$"
HASH_PATTERN = r"^[0-9a-f]{64}$"
DATETIME_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$"


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


def _unique(values: List[str]) -> bool:
    return len(set(values)) == len(values)


Id = Annotated[str, StringConstraints(pattern=UUID_PATTERN)]
ShareId = Annotated[str, StringConstraints(pattern=SHARE_ID_PATTERN)]
Sha256Hex = Annotated[str, StringConstraints(pattern=HASH_PATTERN)]
DateTimeUtc = Annotated[str, StringConstraints(pattern=DATETIME_PATTERN)]
Revision = Annotated[int, Field(ge=1, le=REVISION_MAX)]
Counter = Annotated[int, Field(ge=0, le=REVISION_MAX)]
Title = Annotated[str, StringConstraints(min_length=1, max_length=TITLE_MAX),
                  AfterValidator(_not_blank)]
PromptText = Annotated[str, StringConstraints(min_length=1, max_length=PROMPT_MAX),
                       AfterValidator(_not_blank)]
OptionText = Annotated[str, StringConstraints(min_length=1, max_length=OPTION_MAX),
                       AfterValidator(_not_blank)]
ExplanationText = Annotated[str, StringConstraints(max_length=EXPLANATION_MAX)]
TimeLimitMs = Annotated[int, Field(ge=TIME_LIMIT_MIN_MS, le=TIME_LIMIT_MAX_MS)]
AttemptNo = Annotated[int, Field(ge=1, le=2)]
AttemptCount = Annotated[int, Field(ge=0, le=2)]

QuestionKind = Literal["single", "multiple", "boolean"]
Difficulty = Literal["easy", "medium", "hard"]
ThemeId = Literal["neon-tactics", "arcane-academy"]
Plan = Literal["free", "pro"]
SessionPhase = Literal["answering", "revealed", "finished"]
CueName = Literal["summon", "hit-first", "hit-second", "miss", "victory"]
SubmitOutcomeName = Literal["accepted", "duplicate", "rejected"]
RejectReason = Literal[
    "late",               # het gio (server dong cau hoi, view da reveal)
    "not_answering",      # cau hien tai da reveal / phien da ket thuc
    "wrong_revision",     # expected_question_revision / question_id khong khop
    "attempt_mismatch",   # expected_attempt khong phai lan ke tiep
    "attempt_exhausted",  # het luot
    "invalid_option",     # lua chon la / da bi loai / sai so luong
    "payload_conflict",   # request_id da dung voi payload KHAC
]
ErrorCode = Literal[
    "auth_required",
    "identity_unavailable",
    "invalid_request",
    "invalid_json",
    "payload_too_large",
    "draft_not_found",
    "share_not_found",
    "session_not_found",
    "revision_conflict",
    "draft_published",
    "draft_empty",
    "publish_conflict",
    "session_conflict",
    "quota_exceeded",
    "theme_not_entitled",
    "csv_invalid",
    "store_unavailable",
]
CsvColumn = Literal["file", "header", "kind", "prompt", "options", "correct",
                    "explanation", "difficulty", "time_limit_ms"]
CsvErrorCode = Literal[
    "empty_file", "csv_syntax", "too_many_rows", "draft_capacity",
    "missing_column", "unknown_column", "duplicate_column",
    "blank_required", "too_long", "invalid_kind", "invalid_options",
    "invalid_correct", "invalid_value",
]

THEMES: tuple = ("neon-tactics", "arcane-academy")
FREE_THEMES: tuple = ("neon-tactics",)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ModeRef(_Strict):
    id: Literal["tactical-summon"]
    version: Literal[1]


TACTICAL_SUMMON = ModeRef(id=MODE_ID, version=MODE_VERSION)


class Option(_Strict):
    id: Id
    text: OptionText


def _check_options(kind: str, options: List[Option]) -> None:
    if not _unique([o.id for o in options]):
        raise ValueError("option ids must be unique")
    if kind == "boolean" and len(options) != 2:
        raise ValueError("boolean questions require exactly 2 options")


class PublicQuestion(_Strict):
    """Cau hoi KHONG co dap an — dung cho snapshot cong khai va view nguoi choi."""

    id: Id
    kind: QuestionKind
    prompt: PromptText
    options: List[Option] = Field(min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)
    time_limit_ms: Optional[TimeLimitMs]

    @model_validator(mode="after")
    def _rules(self) -> "PublicQuestion":
        _check_options(self.kind, self.options)
        return self


class DraftQuestion(_Strict):
    """Cau hoi cua CHU SO HUU — co dap an. Chi xuat hien trong `CreatorDraft`."""

    id: Id
    kind: QuestionKind
    prompt: PromptText
    options: List[Option] = Field(min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)
    correct_option_ids: List[Id] = Field(min_length=1, max_length=MAX_OPTIONS)
    explanation: ExplanationText
    difficulty: Difficulty
    time_limit_ms: Optional[TimeLimitMs]

    @model_validator(mode="after")
    def _rules(self) -> "DraftQuestion":
        _check_options(self.kind, self.options)
        if not _unique(self.correct_option_ids):
            raise ValueError("correct_option_ids must be unique")
        known = {o.id for o in self.options}
        if any(c not in known for c in self.correct_option_ids):
            raise ValueError("correct_option_ids must reference this question's options")
        if self.kind != "multiple" and len(self.correct_option_ids) != 1:
            raise ValueError("single/boolean questions require exactly 1 correct option")
        return self


QuestionList = Annotated[List[DraftQuestion], Field(max_length=MAX_QUESTIONS)]


def _check_question_ids(questions: List[DraftQuestion]) -> None:
    if not _unique([q.id for q in questions]):
        raise ValueError("question ids must be unique")


# -- Draft / bank (bank = danh sach cau hoi nhung trong draft, 1:1) -----------

class DraftCreateRequest(_Strict):
    title: Title
    theme_id: ThemeId
    questions: QuestionList = Field(default_factory=list)

    @model_validator(mode="after")
    def _rules(self) -> "DraftCreateRequest":
        _check_question_ids(self.questions)
        return self


class DraftUpdateRequest(_Strict):
    """Thay TOAN BO noi dung draft (PUT). `expected_revision` bat buoc."""

    expected_revision: Revision
    title: Title
    theme_id: ThemeId
    questions: QuestionList

    @model_validator(mode="after")
    def _rules(self) -> "DraftUpdateRequest":
        _check_question_ids(self.questions)
        return self


class CreatorDraft(_Strict):
    draft_id: Id
    title: Title
    theme_id: ThemeId
    mode: ModeRef
    revision: Revision
    questions: QuestionList
    share_id: Optional[ShareId]
    published_version: Optional[Revision]
    created_at: DateTimeUtc
    updated_at: DateTimeUtc

    @model_validator(mode="after")
    def _rules(self) -> "CreatorDraft":
        _check_question_ids(self.questions)
        if (self.share_id is None) != (self.published_version is None):
            raise ValueError("share_id and published_version are set together")
        return self


class DraftSummary(_Strict):
    draft_id: Id
    title: Title
    theme_id: ThemeId
    revision: Revision
    question_count: Annotated[int, Field(ge=0, le=MAX_QUESTIONS)]
    share_id: Optional[ShareId]
    published_version: Optional[Revision]
    updated_at: DateTimeUtc


class DraftList(_Strict):
    items: List[DraftSummary] = Field(max_length=LIST_PAGE_MAX)
    total: Counter
    next_offset: Optional[Counter]


# -- CSV -----------------------------------------------------------------------

CsvText = Annotated[str, StringConstraints(min_length=1, max_length=CSV_MAX_CHARS)]


class CsvValidateRequest(_Strict):
    csv: CsvText
    strategy: Literal["append", "replace"]


class CsvCommitRequest(_Strict):
    csv: CsvText
    strategy: Literal["append", "replace"]
    expected_revision: Revision


class CsvError(_Strict):
    """`row` 1-based theo DONG VAT LY cua file (header = dong 1)."""

    row: Annotated[int, Field(ge=1, le=1_000_000)]
    column: CsvColumn
    code: CsvErrorCode
    message: Annotated[str, StringConstraints(min_length=1, max_length=300)]


class CsvRowPreview(_Strict):
    row: Annotated[int, Field(ge=2, le=1_000_000)]
    kind: QuestionKind
    prompt: PromptText
    options: List[OptionText] = Field(min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)
    correct_option_indexes: List[Annotated[int, Field(ge=1, le=MAX_OPTIONS)]] = Field(
        min_length=1, max_length=MAX_OPTIONS)
    explanation: ExplanationText
    difficulty: Difficulty
    time_limit_ms: Optional[TimeLimitMs]

    @model_validator(mode="after")
    def _rules(self) -> "CsvRowPreview":
        idx = self.correct_option_indexes
        if len(set(idx)) != len(idx) or any(i > len(self.options) for i in idx):
            raise ValueError("correct_option_indexes must be unique and within options")
        if self.kind != "multiple" and len(idx) != 1:
            raise ValueError("single/boolean rows require exactly 1 correct index")
        if self.kind == "boolean" and len(self.options) != 2:
            raise ValueError("boolean rows require exactly 2 options")
        return self


class CsvValidationResult(_Strict):
    valid: bool
    row_count: Annotated[int, Field(ge=0, le=CSV_MAX_ROWS)]
    rows: List[CsvRowPreview] = Field(max_length=CSV_MAX_ROWS)
    errors: List[CsvError] = Field(max_length=CSV_MAX_ERRORS)
    resulting_question_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _rules(self) -> "CsvValidationResult":
        if self.valid != (not self.errors):
            raise ValueError("valid must be true exactly when errors is empty")
        if self.valid and len(self.rows) != self.row_count:
            raise ValueError("a valid result previews every row")
        return self


# -- Publish / share -------------------------------------------------------------

class PublishRequest(_Strict):
    expected_revision: Revision


class PublishResult(_Strict):
    share_id: ShareId
    version: Revision
    draft_revision: Revision
    content_hash: Sha256Hex
    question_count: Annotated[int, Field(ge=1, le=MAX_QUESTIONS)]
    published_at: DateTimeUtc
    replayed: bool


class PublicQuizSnapshot(_Strict):
    """Snapshot BAT BIEN cua mot version — public, KHONG co dap an/giai thich."""

    contract_version: Literal["1.0.0"]
    share_id: ShareId
    version: Revision
    title: Title
    theme_id: ThemeId
    mode: ModeRef
    question_count: Annotated[int, Field(ge=1, le=MAX_QUESTIONS)]
    questions: List[PublicQuestion] = Field(min_length=1, max_length=MAX_QUESTIONS)
    content_hash: Sha256Hex
    published_at: DateTimeUtc

    @model_validator(mode="after")
    def _rules(self) -> "PublicQuizSnapshot":
        if not _unique([q.id for q in self.questions]):
            raise ValueError("question ids must be unique")
        if self.question_count != len(self.questions):
            raise ValueError("question_count must equal len(questions)")
        return self


# -- Session (solo) -----------------------------------------------------------

class SubmitRequest(_Strict):
    request_id: Id
    question_id: Id
    selected_option_ids: List[Id] = Field(min_length=1, max_length=MAX_OPTIONS)
    expected_question_revision: Revision
    expected_attempt: AttemptNo

    @model_validator(mode="after")
    def _rules(self) -> "SubmitRequest":
        if not _unique(self.selected_option_ids):
            raise ValueError("selected_option_ids must be unique")
        return self


class AdvanceRequest(_Strict):
    expected_question_revision: Revision


class LastAttempt(_Strict):
    attempt: AttemptNo
    correct: bool
    selected_option_ids: List[Id] = Field(min_length=1, max_length=MAX_OPTIONS)


class Reveal(_Strict):
    """Chi co khi cau hien tai da dong (`phase == "revealed"`)."""

    question_id: Id
    correct_option_ids: List[Id] = Field(min_length=1, max_length=MAX_OPTIONS)
    explanation: ExplanationText
    correct: bool
    timed_out: bool


class Cue(_Strict):
    event_id: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    cue: CueName


class QuestionResult(_Strict):
    question_id: Id
    correct: bool
    attempts_used: AttemptCount


class ParticipantView(_Strict):
    """Phep chieu cho NGUOI CHOI. Khong bao gio chua dap an truoc reveal."""

    session_id: Id
    share_id: ShareId
    version: Revision
    title: Title
    theme_id: ThemeId
    mode: ModeRef
    phase: SessionPhase
    state_revision: Revision
    question_revision: Revision
    question_count: Annotated[int, Field(ge=1, le=MAX_QUESTIONS)]
    question: Optional[PublicQuestion]
    attempt_limit: AttemptCount
    attempts_used: AttemptCount
    attempts_remaining: AttemptCount
    can_submit: bool
    eliminated_option_ids: List[Id] = Field(max_length=MAX_OPTIONS)
    last_attempt: Optional[LastAttempt]
    reveal: Optional[Reveal]
    score: Counter
    max_score: Annotated[int, Field(ge=1, le=MAX_QUESTIONS)]
    deadline_at: Optional[DateTimeUtc]
    cue: Optional[Cue]
    results: Optional[Annotated[List[QuestionResult], Field(max_length=MAX_QUESTIONS)]]
    created_at: DateTimeUtc
    finished_at: Optional[DateTimeUtc]

    @model_validator(mode="after")
    def _rules(self) -> "ParticipantView":
        if self.score > self.max_score or self.max_score != self.question_count:
            raise ValueError("score must be within max_score == question_count")
        if self.question_revision > self.question_count:
            raise ValueError("question_revision out of range")
        if self.attempts_used + self.attempts_remaining != self.attempt_limit:
            raise ValueError("attempts_used + attempts_remaining must equal attempt_limit")
        finished = self.phase == "finished"
        if finished != (self.question is None):
            raise ValueError("question is absent exactly when finished")
        if finished != (self.results is not None) or finished != (self.finished_at is not None):
            raise ValueError("results/finished_at only when finished")
        if (self.phase == "revealed") != (self.reveal is not None):
            raise ValueError("reveal is present exactly when phase is revealed")
        if self.can_submit and (self.phase != "answering" or self.attempts_remaining == 0):
            raise ValueError("can_submit requires answering with attempts left")
        q = self.question
        if q is not None:
            ids = {o.id for o in q.options}
            if any(e not in ids for e in self.eliminated_option_ids):
                raise ValueError("eliminated_option_ids must reference options")
            if q.kind != "single" and self.eliminated_option_ids:
                raise ValueError("only single-choice questions eliminate options")
            if self.reveal is not None:
                if self.reveal.question_id != q.id or any(
                        c not in ids for c in self.reveal.correct_option_ids):
                    raise ValueError("reveal must match the current question")
        elif self.eliminated_option_ids or self.last_attempt is not None:
            raise ValueError("feedback requires a current question")
        return self


class Receipt(_Strict):
    receipt_id: Sha256Hex
    request_id: Id
    question_id: Id
    attempt: AttemptNo
    correct: bool


class SubmitResponse(_Strict):
    outcome: SubmitOutcomeName
    reason: Optional[RejectReason]
    receipt: Optional[Receipt]
    view: ParticipantView

    @model_validator(mode="after")
    def _rules(self) -> "SubmitResponse":
        if self.outcome == "rejected":
            if self.reason is None or self.receipt is not None:
                raise ValueError("rejected carries a reason and no receipt")
        elif self.reason is not None or self.receipt is None:
            raise ValueError("accepted/duplicate carry a receipt and no reason")
        return self


# -- Entitlements / errors ------------------------------------------------------

class EntitlementSummary(_Strict):
    """Chi de HIEN THI. Quyet dinh nam o server (`server/quiz/entitlements.py`)."""

    plan: Plan
    published_limit: Annotated[int, Field(ge=0, le=1000)]
    published_used: Counter
    themes: List[ThemeId] = Field(min_length=1, max_length=len(THEMES))
    pro_expires_at: Optional[DateTimeUtc]


class FieldError(_Strict):
    loc: List[Union[str, int]] = Field(max_length=16)
    msg: Annotated[str, StringConstraints(max_length=300)]
    type: Annotated[str, StringConstraints(max_length=80)]


class ErrorBody(_Strict):
    code: ErrorCode
    message: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    current_revision: Optional[Revision] = None
    limit: Optional[Counter] = None
    field_errors: Optional[Annotated[List[FieldError], Field(max_length=100)]] = None
    csv_errors: Optional[Annotated[List[CsvError], Field(max_length=CSV_MAX_ERRORS)]] = None


class ErrorEnvelope(_Strict):
    """Moi loi quiz: `{"detail": ErrorBody}` — cung dang `HTTPException(detail=dict)` cua host."""

    detail: ErrorBody


#: Thu tu co dinh — codegen dung danh sach nay de xuat schema/TS tat dinh.
#: KHONG them model rieng tu (AnswerKey, VersionRecord, ...) vao day.
PUBLIC_MODELS = (
    ModeRef, Option, PublicQuestion, DraftQuestion,
    DraftCreateRequest, DraftUpdateRequest, CreatorDraft, DraftSummary, DraftList,
    CsvValidateRequest, CsvCommitRequest, CsvError, CsvRowPreview, CsvValidationResult,
    PublishRequest, PublishResult, PublicQuizSnapshot,
    SubmitRequest, AdvanceRequest, LastAttempt, Reveal, Cue, QuestionResult,
    ParticipantView, Receipt, SubmitResponse,
    EntitlementSummary, FieldError, ErrorBody, ErrorEnvelope,
)
