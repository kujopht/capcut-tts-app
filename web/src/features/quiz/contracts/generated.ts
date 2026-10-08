// GENERATED FILE — DO NOT EDIT.
// Source: server/quiz/contracts.py (Pydantic v2). Regenerate: python -m server.quiz.codegen
// Types only: the server owns validation, scoring, attempts, deadlines and reveal.
/* eslint-disable */

export const QUIZ_CONTRACT_VERSION = "1.0.0" as const;

export const QUIZ_LIMITS = {
  maxQuestions: 200,
  minOptions: 2,
  maxOptions: 8,
  titleMax: 120,
  promptMax: 1000,
  optionMax: 300,
  explanationMax: 1000,
  timeLimitMinMs: 5000,
  timeLimitMaxMs: 120000,
  csvMaxChars: 512000,
  csvMaxRows: 200,
  listPageMax: 50,
} as const;

export const QUIZ_THEMES = [
  "neon-tactics",
  "arcane-academy",
] as const;

export const QUIZ_FREE_THEMES = [
  "neon-tactics",
] as const;

export const QUIZ_ERROR_CODES = [
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
] as const;

export const QUIZ_REJECT_REASONS = [
  "late",
  "not_answering",
  "wrong_revision",
  "attempt_mismatch",
  "attempt_exhausted",
  "invalid_option",
  "payload_conflict",
] as const;

export const QUIZ_CSV_ERROR_CODES = [
  "empty_file",
  "csv_syntax",
  "too_many_rows",
  "draft_capacity",
  "missing_column",
  "unknown_column",
  "duplicate_column",
  "blank_required",
  "too_long",
  "invalid_kind",
  "invalid_options",
  "invalid_correct",
  "invalid_value",
] as const;

export const QUIZ_CSV_COLUMNS = [
  "kind",
  "prompt",
  "options",
  "correct",
  "explanation",
  "difficulty",
  "time_limit_ms",
] as const;

export const QUIZ_ENDPOINTS = {
  myEntitlements: { method: "GET", path: "/api/quiz/me/entitlements", auth: "required" },
  listDrafts: { method: "GET", path: "/api/quiz/drafts", auth: "required" },
  createDraft: { method: "POST", path: "/api/quiz/drafts", auth: "required" },
  getDraft: { method: "GET", path: "/api/quiz/drafts/{draft_id}", auth: "required" },
  updateDraft: { method: "PUT", path: "/api/quiz/drafts/{draft_id}", auth: "required" },
  deleteDraft: { method: "DELETE", path: "/api/quiz/drafts/{draft_id}", auth: "required" },
  csvValidate: { method: "POST", path: "/api/quiz/drafts/{draft_id}/csv/validate", auth: "required" },
  csvCommit: { method: "POST", path: "/api/quiz/drafts/{draft_id}/csv/commit", auth: "required" },
  publish: { method: "POST", path: "/api/quiz/drafts/{draft_id}/publish", auth: "required" },
  getShare: { method: "GET", path: "/api/quiz/shares/{share_id}", auth: "none" },
  createSession: { method: "POST", path: "/api/quiz/shares/{share_id}/sessions", auth: "required" },
  getSession: { method: "GET", path: "/api/quiz/sessions/{session_id}", auth: "required" },
  submit: { method: "POST", path: "/api/quiz/sessions/{session_id}/submit", auth: "required" },
  advance: { method: "POST", path: "/api/quiz/sessions/{session_id}/advance", auth: "required" },
} as const;

export interface ModeRef {
  id: "tactical-summon";
  version: 1;
}

export interface Option {
  /** pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  id: string;
  /** minLength 1, maxLength 300 */
  text: string;
}

/** Cau hoi KHONG co dap an — dung cho snapshot cong khai va view nguoi choi. */
export interface PublicQuestion {
  /** pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  id: string;
  kind: "single" | "multiple" | "boolean";
  /** minLength 1, maxLength 1000 */
  prompt: string;
  /** minItems 2, maxItems 8 */
  options: Option[];
  /** minimum 5000, maximum 120000 */
  time_limit_ms: number | null;
}

/** Cau hoi cua CHU SO HUU — co dap an. Chi xuat hien trong `CreatorDraft`. */
export interface DraftQuestion {
  /** pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  id: string;
  kind: "single" | "multiple" | "boolean";
  /** minLength 1, maxLength 1000 */
  prompt: string;
  /** minItems 2, maxItems 8 */
  options: Option[];
  /** minItems 1, maxItems 8, item pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  correct_option_ids: string[];
  /** maxLength 1000 */
  explanation: string;
  difficulty: "easy" | "medium" | "hard";
  /** minimum 5000, maximum 120000 */
  time_limit_ms: number | null;
}

export interface DraftCreateRequest {
  /** minLength 1, maxLength 120 */
  title: string;
  theme_id: "neon-tactics" | "arcane-academy";
  /** maxItems 200 */
  questions?: DraftQuestion[];
}

/** Thay TOAN BO noi dung draft (PUT). `expected_revision` bat buoc. */
export interface DraftUpdateRequest {
  /** minimum 1, maximum 9007199254740991 */
  expected_revision: number;
  /** minLength 1, maxLength 120 */
  title: string;
  theme_id: "neon-tactics" | "arcane-academy";
  /** maxItems 200 */
  questions: DraftQuestion[];
}

export interface CreatorDraft {
  /** pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  draft_id: string;
  /** minLength 1, maxLength 120 */
  title: string;
  theme_id: "neon-tactics" | "arcane-academy";
  mode: ModeRef;
  /** minimum 1, maximum 9007199254740991 */
  revision: number;
  /** maxItems 200 */
  questions: DraftQuestion[];
  /** pattern ^[A-Za-z0-9]{16}$ */
  share_id: string | null;
  /** minimum 1, maximum 9007199254740991 */
  published_version: number | null;
  /** pattern ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$ */
  created_at: string;
  /** pattern ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$ */
  updated_at: string;
}

export interface DraftSummary {
  /** pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  draft_id: string;
  /** minLength 1, maxLength 120 */
  title: string;
  theme_id: "neon-tactics" | "arcane-academy";
  /** minimum 1, maximum 9007199254740991 */
  revision: number;
  /** minimum 0, maximum 200 */
  question_count: number;
  /** pattern ^[A-Za-z0-9]{16}$ */
  share_id: string | null;
  /** minimum 1, maximum 9007199254740991 */
  published_version: number | null;
  /** pattern ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$ */
  updated_at: string;
}

export interface DraftList {
  /** maxItems 50 */
  items: DraftSummary[];
  /** minimum 0, maximum 9007199254740991 */
  total: number;
  /** minimum 0, maximum 9007199254740991 */
  next_offset: number | null;
}

export interface CsvValidateRequest {
  /** minLength 1, maxLength 512000 */
  csv: string;
  strategy: "append" | "replace";
}

export interface CsvCommitRequest {
  /** minLength 1, maxLength 512000 */
  csv: string;
  strategy: "append" | "replace";
  /** minimum 1, maximum 9007199254740991 */
  expected_revision: number;
}

/** `row` 1-based theo DONG VAT LY cua file (header = dong 1). */
export interface CsvError {
  /** minimum 1, maximum 1000000 */
  row: number;
  column: "file" | "header" | "kind" | "prompt" | "options" | "correct" | "explanation" | "difficulty" | "time_limit_ms";
  code: "empty_file" | "csv_syntax" | "too_many_rows" | "draft_capacity" | "missing_column" | "unknown_column" | "duplicate_column" | "blank_required" | "too_long" | "invalid_kind" | "invalid_options" | "invalid_correct" | "invalid_value";
  /** minLength 1, maxLength 300 */
  message: string;
}

export interface CsvRowPreview {
  /** minimum 2, maximum 1000000 */
  row: number;
  kind: "single" | "multiple" | "boolean";
  /** minLength 1, maxLength 1000 */
  prompt: string;
  /** minItems 2, maxItems 8, item minLength 1, item maxLength 300 */
  options: string[];
  /** minItems 1, maxItems 8, item minimum 1, item maximum 8 */
  correct_option_indexes: number[];
  /** maxLength 1000 */
  explanation: string;
  difficulty: "easy" | "medium" | "hard";
  /** minimum 5000, maximum 120000 */
  time_limit_ms: number | null;
}

export interface CsvValidationResult {
  valid: boolean;
  /** minimum 0, maximum 200 */
  row_count: number;
  /** maxItems 200 */
  rows: CsvRowPreview[];
  /** maxItems 500 */
  errors: CsvError[];
  /** minimum 0 */
  resulting_question_count: number;
}

export interface PublishRequest {
  /** minimum 1, maximum 9007199254740991 */
  expected_revision: number;
}

export interface PublishResult {
  /** pattern ^[A-Za-z0-9]{16}$ */
  share_id: string;
  /** minimum 1, maximum 9007199254740991 */
  version: number;
  /** minimum 1, maximum 9007199254740991 */
  draft_revision: number;
  /** pattern ^[0-9a-f]{64}$ */
  content_hash: string;
  /** minimum 1, maximum 200 */
  question_count: number;
  /** pattern ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$ */
  published_at: string;
  replayed: boolean;
}

/** Snapshot BAT BIEN cua mot version — public, KHONG co dap an/giai thich. */
export interface PublicQuizSnapshot {
  contract_version: "1.0.0";
  /** pattern ^[A-Za-z0-9]{16}$ */
  share_id: string;
  /** minimum 1, maximum 9007199254740991 */
  version: number;
  /** minLength 1, maxLength 120 */
  title: string;
  theme_id: "neon-tactics" | "arcane-academy";
  mode: ModeRef;
  /** minimum 1, maximum 200 */
  question_count: number;
  /** minItems 1, maxItems 200 */
  questions: PublicQuestion[];
  /** pattern ^[0-9a-f]{64}$ */
  content_hash: string;
  /** pattern ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$ */
  published_at: string;
}

export interface SubmitRequest {
  /** pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  request_id: string;
  /** pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  question_id: string;
  /** minItems 1, maxItems 8, item pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  selected_option_ids: string[];
  /** minimum 1, maximum 9007199254740991 */
  expected_question_revision: number;
  /** minimum 1, maximum 2 */
  expected_attempt: number;
}

export interface AdvanceRequest {
  /** minimum 1, maximum 9007199254740991 */
  expected_question_revision: number;
}

export interface LastAttempt {
  /** minimum 1, maximum 2 */
  attempt: number;
  correct: boolean;
  /** minItems 1, maxItems 8, item pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  selected_option_ids: string[];
}

/** Chi co khi cau hien tai da dong (`phase == "revealed"`). */
export interface Reveal {
  /** pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  question_id: string;
  /** minItems 1, maxItems 8, item pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  correct_option_ids: string[];
  /** maxLength 1000 */
  explanation: string;
  correct: boolean;
  timed_out: boolean;
}

export interface Cue {
  /** minLength 1, maxLength 80 */
  event_id: string;
  cue: "summon" | "hit-first" | "hit-second" | "miss" | "victory";
}

export interface QuestionResult {
  /** pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  question_id: string;
  correct: boolean;
  /** minimum 0, maximum 2 */
  attempts_used: number;
}

/** Phep chieu cho NGUOI CHOI. Khong bao gio chua dap an truoc reveal. */
export interface ParticipantView {
  /** pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  session_id: string;
  /** pattern ^[A-Za-z0-9]{16}$ */
  share_id: string;
  /** minimum 1, maximum 9007199254740991 */
  version: number;
  /** minLength 1, maxLength 120 */
  title: string;
  theme_id: "neon-tactics" | "arcane-academy";
  mode: ModeRef;
  phase: "answering" | "revealed" | "finished";
  /** minimum 1, maximum 9007199254740991 */
  state_revision: number;
  /** minimum 1, maximum 9007199254740991 */
  question_revision: number;
  /** minimum 1, maximum 200 */
  question_count: number;
  question: PublicQuestion | null;
  /** minimum 0, maximum 2 */
  attempt_limit: number;
  /** minimum 0, maximum 2 */
  attempts_used: number;
  /** minimum 0, maximum 2 */
  attempts_remaining: number;
  can_submit: boolean;
  /** maxItems 8, item pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  eliminated_option_ids: string[];
  last_attempt: LastAttempt | null;
  reveal: Reveal | null;
  /** minimum 0, maximum 9007199254740991 */
  score: number;
  /** minimum 1, maximum 200 */
  max_score: number;
  /** pattern ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$ */
  deadline_at: string | null;
  cue: Cue | null;
  /** maxItems 200 */
  results: QuestionResult[] | null;
  /** pattern ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$ */
  created_at: string;
  /** pattern ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$ */
  finished_at: string | null;
}

export interface Receipt {
  /** pattern ^[0-9a-f]{64}$ */
  receipt_id: string;
  /** pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  request_id: string;
  /** pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ */
  question_id: string;
  /** minimum 1, maximum 2 */
  attempt: number;
  correct: boolean;
}

export interface SubmitResponse {
  outcome: "accepted" | "duplicate" | "rejected";
  reason: "late" | "not_answering" | "wrong_revision" | "attempt_mismatch" | "attempt_exhausted" | "invalid_option" | "payload_conflict" | null;
  receipt: Receipt | null;
  view: ParticipantView;
}

/** Chi de HIEN THI. Quyet dinh nam o server (`server/quiz/entitlements.py`). */
export interface EntitlementSummary {
  plan: "free" | "pro";
  /** minimum 0, maximum 1000 */
  published_limit: number;
  /** minimum 0, maximum 9007199254740991 */
  published_used: number;
  /** minItems 1, maxItems 2 */
  themes: ("neon-tactics" | "arcane-academy")[];
  /** pattern ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$ */
  pro_expires_at: string | null;
}

export interface FieldError {
  /** maxItems 16 */
  loc: (string | number)[];
  /** maxLength 300 */
  msg: string;
  /** maxLength 80 */
  type: string;
}

export interface ErrorBody {
  code: "auth_required" | "identity_unavailable" | "invalid_request" | "invalid_json" | "payload_too_large" | "draft_not_found" | "share_not_found" | "session_not_found" | "revision_conflict" | "draft_published" | "draft_empty" | "publish_conflict" | "session_conflict" | "quota_exceeded" | "theme_not_entitled" | "csv_invalid" | "store_unavailable";
  /** minLength 1, maxLength 300 */
  message: string;
  /** minimum 1, maximum 9007199254740991 */
  current_revision?: number | null;
  /** minimum 0, maximum 9007199254740991 */
  limit?: number | null;
  /** maxItems 100 */
  field_errors?: FieldError[] | null;
  /** maxItems 500 */
  csv_errors?: CsvError[] | null;
}

/** Moi loi quiz: `{"detail": ErrorBody}` — cung dang `HTTPException(detail=dict)` cua host. */
export interface ErrorEnvelope {
  detail: ErrorBody;
}
