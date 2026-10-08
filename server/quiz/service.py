"""
`QuizService` — noi DUY NHAT quyet dinh quyen so huu, entitlement, cham diem,
so lan tra loi, han gio va reveal. Dung chung cho MOI adapter store.

Moi phuong thuc nhan `user_id` da resolve tu ho so host (khong bao gio tu
client). Tai nguyen cua nguoi khac tra 404 (khong lo su ton tai).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from server.quiz import rules
from server.quiz.contracts import (
    LIST_PAGE_MAX, TACTICAL_SUMMON, AdvanceRequest, CreatorDraft, CsvCommitRequest,
    CsvError, CsvValidateRequest, CsvValidationResult, Cue, DraftCreateRequest,
    DraftList, DraftSummary, DraftUpdateRequest, EntitlementSummary, LastAttempt,
    MAX_QUESTIONS, ParticipantView, PublicQuestion, PublicQuizSnapshot,
    PublishRequest, PublishResult, QuestionResult, Receipt, Reveal, SubmitRequest,
    SubmitResponse,
)
from server.quiz.csv_import import parse_csv, rows_to_questions
from server.quiz.entitlements import EntitlementPolicy, iso, parse_iso
from server.quiz.store import (
    AnswerKey, DraftRecord, PublishConflict, PublishContent, QuizStore,
    QuotaExceeded, RevisionConflict, SessionRecord, StoreNotFound, StoredReceipt,
    VersionRecord,
)

SHARE_ALPHABET = string.ascii_letters + string.digits
CAS_RETRIES = 8


class QuizError(Exception):
    """Loi nghiep vu -> HTTP. `extra` di vao `ErrorBody` (current_revision, limit, ...)."""

    def __init__(self, status: int, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_share_id() -> str:
    return "".join(secrets.choice(SHARE_ALPHABET) for _ in range(16))


def _sha256(obj: Any) -> str:
    data = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _not_found(kind: str) -> QuizError:
    return QuizError(404, f"{kind}_not_found", f"{kind.capitalize()} not found.")


def _revision_conflict(current: Optional[int]) -> QuizError:
    return QuizError(409, "revision_conflict",
                     "The draft changed since you loaded it. Reload and retry.",
                     current_revision=current)


class QuizService:
    def __init__(self, store: QuizStore, *, clock: Callable[[], datetime] = _utcnow,
                 new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
                 new_share_id: Callable[[], str] = _new_share_id):
        self.store = store
        self.clock = clock
        self.new_id = new_id
        self.new_share_id = new_share_id
        self.policy = EntitlementPolicy(store, clock)

    def _now(self) -> str:
        return iso(self.clock())

    # -- entitlements -----------------------------------------------------------

    def entitlements(self, user_id: str) -> EntitlementSummary:
        return self.policy.summary(user_id)

    def _require_theme(self, user_id: str, theme_id: str) -> None:
        allowance, _ = self.policy.resolve(user_id)
        if theme_id not in allowance.themes:
            raise QuizError(403, "theme_not_entitled",
                            f"Theme '{theme_id}' requires the Pro plan.")

    # -- drafts --------------------------------------------------------------------

    def _own_draft(self, user_id: str, draft_id: str) -> DraftRecord:
        rec = self.store.get_draft(draft_id)
        if rec is None or rec.owner_user_id != user_id:
            raise _not_found("draft")
        return rec

    @staticmethod
    def _creator_view(rec: DraftRecord) -> CreatorDraft:
        return CreatorDraft(
            draft_id=rec.draft_id, title=rec.title, theme_id=rec.theme_id,
            mode=TACTICAL_SUMMON, revision=rec.revision, questions=list(rec.questions),
            share_id=rec.share_id, published_version=rec.published_version,
            created_at=rec.created_at, updated_at=rec.updated_at)

    def create_draft(self, user_id: str, req: DraftCreateRequest) -> CreatorDraft:
        self._require_theme(user_id, req.theme_id)
        now = self._now()
        rec = DraftRecord(draft_id=self.new_id(), owner_user_id=user_id, title=req.title,
                          theme_id=req.theme_id, questions=list(req.questions), revision=1,
                          created_at=now, updated_at=now)
        return self._creator_view(self.store.create_draft(rec))

    def get_draft(self, user_id: str, draft_id: str) -> CreatorDraft:
        return self._creator_view(self._own_draft(user_id, draft_id))

    def list_drafts(self, user_id: str, *, limit: int, offset: int) -> DraftList:
        limit = max(1, min(limit, LIST_PAGE_MAX))
        offset = max(0, offset)
        rows, total = self.store.list_drafts(user_id, limit=limit, offset=offset)
        items = [DraftSummary(
            draft_id=r.draft_id, title=r.title, theme_id=r.theme_id, revision=r.revision,
            question_count=len(r.questions), share_id=r.share_id,
            published_version=r.published_version, updated_at=r.updated_at) for r in rows]
        nxt = offset + len(items)
        return DraftList(items=items, total=total, next_offset=nxt if nxt < total else None)

    def _save_draft(self, current: DraftRecord, expected_revision: int,
                    **changes: Any) -> DraftRecord:
        if current.revision != expected_revision:
            raise _revision_conflict(current.revision)
        new = current.model_copy(update={**changes, "revision": current.revision + 1,
                                         "updated_at": self._now()})
        new = DraftRecord.model_validate(new.model_dump())  # luat hop dong cho ban moi
        try:
            return self.store.replace_draft(new, expected_revision=expected_revision)
        except RevisionConflict as exc:
            raise _revision_conflict(exc.current_revision) from exc
        except StoreNotFound as exc:
            raise _not_found("draft") from exc

    def update_draft(self, user_id: str, draft_id: str, req: DraftUpdateRequest) -> CreatorDraft:
        current = self._own_draft(user_id, draft_id)
        if req.theme_id != current.theme_id:
            self._require_theme(user_id, req.theme_id)
        saved = self._save_draft(current, req.expected_revision, title=req.title,
                                 theme_id=req.theme_id, questions=list(req.questions))
        return self._creator_view(saved)

    def delete_draft(self, user_id: str, draft_id: str, expected_revision: int) -> None:
        current = self._own_draft(user_id, draft_id)
        if current.share_id is not None:
            raise QuizError(409, "draft_published",
                            "Published drafts cannot be deleted in Phase 1.")
        if current.revision != expected_revision:
            raise _revision_conflict(current.revision)
        try:
            self.store.delete_draft(draft_id, expected_revision=expected_revision)
        except RevisionConflict as exc:
            raise _revision_conflict(exc.current_revision) from exc
        except StoreNotFound as exc:
            raise _not_found("draft") from exc

    # -- CSV --------------------------------------------------------------------------

    def _csv(self, current: DraftRecord, csv_text: str,
             strategy: str) -> Tuple[CsvValidationResult, list]:
        rows, errors, row_count = parse_csv(csv_text)
        base = len(current.questions) if strategy == "append" else 0
        if not errors and row_count == 0:
            errors = [CsvError(row=1, column="file", code="empty_file",
                               message="CSV has a header but no question rows.")]
        if not errors and base + row_count > MAX_QUESTIONS:
            errors = [CsvError(row=1, column="file", code="draft_capacity",
                               message=f"Draft would exceed {MAX_QUESTIONS} questions.")]
        result = CsvValidationResult(
            valid=not errors, row_count=row_count, rows=rows, errors=errors,
            resulting_question_count=(base + row_count) if not errors else len(current.questions))
        return result, rows

    def csv_validate(self, user_id: str, draft_id: str,
                     req: CsvValidateRequest) -> CsvValidationResult:
        return self._csv(self._own_draft(user_id, draft_id), req.csv, req.strategy)[0]

    def csv_commit(self, user_id: str, draft_id: str, req: CsvCommitRequest) -> CreatorDraft:
        current = self._own_draft(user_id, draft_id)
        if current.revision != req.expected_revision:
            raise _revision_conflict(current.revision)
        result, rows = self._csv(current, req.csv, req.strategy)
        if not result.valid:
            raise QuizError(422, "csv_invalid", "CSV has errors; nothing was imported.",
                            csv_errors=list(result.errors))
        imported = rows_to_questions(rows, self.new_id)
        questions = (list(current.questions) + imported) if req.strategy == "append" else imported
        return self._creator_view(self._save_draft(current, req.expected_revision,
                                                   questions=questions))

    # -- publish / share ------------------------------------------------------------

    def publish(self, user_id: str, draft_id: str, req: PublishRequest) -> PublishResult:
        current = self._own_draft(user_id, draft_id)
        if current.revision != req.expected_revision:
            raise _revision_conflict(current.revision)
        if not current.questions:
            raise QuizError(422, "draft_empty", "Add at least one question before publishing.")
        self._require_theme(user_id, current.theme_id)
        allowance, _ = self.policy.resolve(user_id)

        public = [PublicQuestion(id=q.id, kind=q.kind, prompt=q.prompt, options=list(q.options),
                                 time_limit_ms=q.time_limit_ms) for q in current.questions]
        keys = [AnswerKey(question_id=q.id, correct_option_ids=list(q.correct_option_ids),
                          explanation=q.explanation) for q in current.questions]
        # Hash CHI tren noi dung cong khai: hash co ca dap an cho phep do dap an
        # bang vet can voi quiz nho.
        content_hash = _sha256({"title": current.title, "theme_id": current.theme_id,
                                "mode": TACTICAL_SUMMON.model_dump(),
                                "questions": [p.model_dump(mode="json") for p in public]})
        content = PublishContent(title=current.title, theme_id=current.theme_id,
                                 public_questions=public, keys=keys, content_hash=content_hash)
        try:
            share, version, replayed = self.store.publish(
                owner_user_id=user_id, draft_id=draft_id,
                expected_revision=req.expected_revision, content=content,
                new_share_id=self.new_share_id(), quota_limit=allowance.published_limit,
                now=self._now())
        except QuotaExceeded as exc:
            raise QuizError(403, "quota_exceeded",
                            f"Your plan allows {exc.limit} published quizzes.",
                            limit=exc.limit) from exc
        except RevisionConflict as exc:
            raise _revision_conflict(exc.current_revision) from exc
        except PublishConflict as exc:
            raise QuizError(409, "publish_conflict",
                            "Another publish of this draft is in progress. Retry.") from exc
        except StoreNotFound as exc:
            raise _not_found("draft") from exc
        return PublishResult(share_id=share.share_id, version=version.version,
                             draft_revision=version.draft_revision,
                             content_hash=version.public.content_hash,
                             question_count=version.public.question_count,
                             published_at=version.public.published_at, replayed=replayed)

    def _latest_version(self, share_id: str) -> VersionRecord:
        share = self.store.get_share(share_id)
        if share is None:
            raise _not_found("share")
        version = self.store.get_version(share_id, share.latest_version)
        if version is None:
            raise _not_found("share")
        return version

    def get_share(self, share_id: str) -> PublicQuizSnapshot:
        return self._latest_version(share_id).public

    # -- sessions (solo) -------------------------------------------------------------

    def _question_state(self, version: VersionRecord, index: int, now: datetime) -> Dict[str, Any]:
        q = version.public.questions[index]
        deadline = (iso(now + timedelta(milliseconds=q.time_limit_ms))
                    if q.time_limit_ms is not None else None)
        return {"question_index": index, "phase": "answering", "attempts_used": 0,
                "eliminated_option_ids": [], "last_attempt": None, "timed_out": False,
                "deadline_at": deadline, "cue": "summon"}

    def create_session(self, user_id: str, share_id: str) -> ParticipantView:
        version = self._latest_version(share_id)
        now_dt = self.clock()
        now = iso(now_dt)
        rec = SessionRecord(
            session_id=self.new_id(), participant_user_id=user_id, share_id=share_id,
            version=version.version, state_revision=1, score=0, results=[], receipts=[],
            created_at=now, updated_at=now, **self._question_state(version, 0, now_dt))
        return self.project(self.store.create_session(rec), version)

    def _own_session(self, user_id: str, session_id: str) -> Tuple[SessionRecord, VersionRecord]:
        rec = self.store.get_session(session_id)
        if rec is None or rec.participant_user_id != user_id:
            raise _not_found("session")
        version = self.store.get_version(rec.share_id, rec.version)
        if version is None:
            raise _not_found("session")
        return rec, version

    def _expired(self, rec: SessionRecord, now: datetime) -> bool:
        if rec.phase != "answering" or rec.deadline_at is None:
            return False
        return now > parse_iso(rec.deadline_at) + timedelta(milliseconds=rules.GRACE_MS)

    def _close_question(self, rec: SessionRecord, version: VersionRecord, *, correct: bool,
                        timed_out: bool, attempts_used: int, cue: str,
                        last_attempt: Optional[LastAttempt]) -> Dict[str, Any]:
        q = version.public.questions[rec.question_index]
        return {"phase": "revealed", "attempts_used": attempts_used, "timed_out": timed_out,
                "last_attempt": last_attempt, "cue": cue,
                "score": rec.score + (rules.CORRECT_POINTS if correct else 0),
                "results": list(rec.results) + [QuestionResult(
                    question_id=q.id, correct=correct, attempts_used=attempts_used)]}

    def _commit(self, rec: SessionRecord, changes: Dict[str, Any]) -> SessionRecord:
        new = rec.model_copy(update={**changes, "state_revision": rec.state_revision + 1,
                                     "updated_at": self._now()})
        new = SessionRecord.model_validate(new.model_dump())
        return self.store.replace_session(new, expected_state_revision=rec.state_revision)

    def _expire_changes(self, rec: SessionRecord, version: VersionRecord) -> Dict[str, Any]:
        return self._close_question(rec, version, correct=False, timed_out=True,
                                    attempts_used=rec.attempts_used, cue="miss",
                                    last_attempt=rec.last_attempt)

    def get_session(self, user_id: str, session_id: str) -> ParticipantView:
        for _ in range(CAS_RETRIES):
            rec, version = self._own_session(user_id, session_id)
            if not self._expired(rec, self.clock()):
                return self.project(rec, version)
            try:
                return self.project(self._commit(rec, self._expire_changes(rec, version)), version)
            except RevisionConflict:
                continue
        raise QuizError(409, "session_conflict", "Session is busy. Retry.")

    def submit(self, user_id: str, session_id: str, req: SubmitRequest) -> SubmitResponse:
        payload_hash = _sha256({"question_id": req.question_id,
                                "selected": sorted(req.selected_option_ids),
                                "expected_question_revision": req.expected_question_revision,
                                "expected_attempt": req.expected_attempt})
        for _ in range(CAS_RETRIES):
            rec, version = self._own_session(user_id, session_id)

            def reject(reason: str, current: SessionRecord = rec) -> SubmitResponse:
                return SubmitResponse(outcome="rejected", reason=reason, receipt=None,
                                      view=self.project(current, version))

            prior = next((r for r in rec.receipts if r.request_id == req.request_id), None)
            if prior is not None:
                if prior.payload_hash != payload_hash:
                    return reject("payload_conflict")
                return SubmitResponse(outcome="duplicate", reason=None, receipt=prior.receipt,
                                      view=self.project(rec, version))

            if self._expired(rec, self.clock()):
                try:
                    expired = self._commit(rec, self._expire_changes(rec, version))
                except RevisionConflict:
                    continue
                return reject("late", expired)
            if rec.phase != "answering":
                return reject("not_answering")
            q = version.public.questions[rec.question_index]
            if req.expected_question_revision != rec.question_index + 1 or req.question_id != q.id:
                return reject("wrong_revision")
            if req.expected_attempt != rec.attempts_used + 1:
                return reject("attempt_mismatch")
            limit = rules.attempt_limit(q.kind, len(q.options))
            if rec.attempts_used >= limit:
                return reject("attempt_exhausted")
            option_ids = {o.id for o in q.options}
            if (not rules.selection_shape_ok(q.kind, len(req.selected_option_ids))
                    or any(s not in option_ids for s in req.selected_option_ids)
                    or any(s in rec.eliminated_option_ids for s in req.selected_option_ids)):
                return reject("invalid_option")

            key = next(k for k in version.keys if k.question_id == q.id)
            attempt = rec.attempts_used + 1
            correct = rules.is_correct(req.selected_option_ids, key.correct_option_ids)
            last = LastAttempt(attempt=attempt, correct=correct,
                               selected_option_ids=list(req.selected_option_ids))
            receipt = Receipt(receipt_id=_sha256({"session": session_id, "request": req.request_id}),
                              request_id=req.request_id, question_id=q.id, attempt=attempt,
                              correct=correct)
            receipts = list(rec.receipts) + [StoredReceipt(
                request_id=req.request_id, payload_hash=payload_hash, receipt=receipt)]
            if correct or attempt >= limit:
                changes = self._close_question(
                    rec, version, correct=correct, timed_out=False, attempts_used=attempt,
                    cue=rules.hit_cue(attempt) if correct else "miss", last_attempt=last)
            else:
                eliminated = list(rec.eliminated_option_ids)
                if q.kind == "single":
                    eliminated += [s for s in req.selected_option_ids if s not in eliminated]
                changes = {"attempts_used": attempt, "last_attempt": last, "cue": "miss",
                           "eliminated_option_ids": eliminated}
            changes["receipts"] = receipts
            try:
                saved = self._commit(rec, changes)
            except RevisionConflict:
                continue  # doc lai: request trung song song se thanh "duplicate"
            return SubmitResponse(outcome="accepted", reason=None, receipt=receipt,
                                  view=self.project(saved, version))
        raise QuizError(409, "session_conflict", "Session is busy. Retry.")

    def advance(self, user_id: str, session_id: str, req: AdvanceRequest) -> ParticipantView:
        for _ in range(CAS_RETRIES):
            rec, version = self._own_session(user_id, session_id)
            current_rev = rec.question_index + 1
            already_moved = (req.expected_question_revision == current_rev - 1
                             and rec.phase == "answering")
            if already_moved or (rec.phase == "finished" and req.expected_question_revision == current_rev):
                return self.project(rec, version)  # phat lai idempotent
            if req.expected_question_revision != current_rev:
                raise QuizError(409, "session_conflict", "Question revision does not match.")
            if rec.phase == "answering" and self._expired(rec, self.clock()):
                try:
                    self._commit(rec, self._expire_changes(rec, version))
                except RevisionConflict:
                    pass
                continue
            if rec.phase != "revealed":
                raise QuizError(409, "session_conflict", "Answer or wait for the reveal first.")
            nxt = rec.question_index + 1
            if nxt < version.public.question_count:
                changes = self._question_state(version, nxt, self.clock())
            else:
                changes = {"phase": "finished", "cue": "victory", "finished_at": self._now(),
                           "last_attempt": None, "eliminated_option_ids": [], "deadline_at": None}
            try:
                return self.project(self._commit(rec, changes), version)
            except RevisionConflict:
                continue
        raise QuizError(409, "session_conflict", "Session is busy. Retry.")

    # -- projection -------------------------------------------------------------------

    def project(self, rec: SessionRecord, version: VersionRecord) -> ParticipantView:
        pub = version.public
        finished = rec.phase == "finished"
        question = None if finished else pub.questions[rec.question_index]
        limit = rules.attempt_limit(question.kind, len(question.options)) if question else 0
        used = rec.attempts_used if question else 0
        reveal = None
        if rec.phase == "revealed" and question is not None:
            key: AnswerKey = next(k for k in version.keys if k.question_id == question.id)
            reveal = Reveal(question_id=question.id, correct_option_ids=list(key.correct_option_ids),
                            explanation=key.explanation,
                            correct=bool(rec.results and rec.results[-1].correct),
                            timed_out=rec.timed_out)
        can_submit = (rec.phase == "answering" and used < limit
                      and not self._expired(rec, self.clock()))
        return ParticipantView(
            session_id=rec.session_id, share_id=rec.share_id, version=rec.version,
            title=pub.title, theme_id=pub.theme_id, mode=pub.mode, phase=rec.phase,
            state_revision=rec.state_revision, question_revision=rec.question_index + 1,
            question_count=pub.question_count, question=question, attempt_limit=limit,
            attempts_used=used, attempts_remaining=limit - used, can_submit=can_submit,
            eliminated_option_ids=list(rec.eliminated_option_ids) if question else [],
            last_attempt=rec.last_attempt if question else None, reveal=reveal,
            score=rec.score, max_score=pub.question_count,
            deadline_at=rec.deadline_at if rec.phase == "answering" else None,
            cue=Cue(event_id=f"{rec.session_id}:{rec.state_revision}", cue=rec.cue) if rec.cue else None,
            results=list(rec.results) if finished else None,
            created_at=rec.created_at, finished_at=rec.finished_at)
