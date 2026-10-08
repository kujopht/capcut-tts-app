"""
Sinh artefact hop dong quiz TU `server/quiz/contracts.py` (nguon duy nhat).

    python -m server.quiz.codegen           # ghi lai artefact
    python -m server.quiz.codegen --check   # exit 1 neu artefact da commit lech

Ghi vao `web/src/features/quiz/contracts/`:
  * `quiz-api.schema.json` — JSON Schema 2020-12 TAT DINH cua `PUBLIC_MODELS`.
  * `generated.ts` — kieu TS + hang so (gioi han, ma loi, endpoint). Chi la KIEU:
    validation runtime thuoc ve server.
  * `fixtures/valid|invalid/*.json` — ca hop dong `{model, why, data}`; test
    Python khang dinh valid duoc chap nhan, invalid bi tu choi.
  * `fixtures/api/*.json` — request/response THAT, chay kich ban tat dinh qua
    router (TestClient + LocalQuizStore trong thu muc tam, dong ho/id co dinh).

Khong them dependency: bo chuyen JSON Schema -> TS nho o day chi ho tro tap con
ma Pydantic sinh cho cac model nay; gap cau truc la thi bao loi thay vi doan.
"""

from __future__ import annotations

import argparse
import itertools
import json
import shutil
import sys
import tempfile
import typing
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic.json_schema import models_json_schema

from server.quiz import contracts as C

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "web" / "src" / "features" / "quiz" / "contracts"
SCHEMA_FILE = "quiz-api.schema.json"
TS_FILE = "generated.ts"
FIXTURE_DIR = "fixtures"

ENDPOINTS: List[Tuple[str, str, str, str]] = [
    # (name, method, path, auth)
    ("myEntitlements", "GET", "/api/quiz/me/entitlements", "required"),
    ("listDrafts", "GET", "/api/quiz/drafts", "required"),
    ("createDraft", "POST", "/api/quiz/drafts", "required"),
    ("getDraft", "GET", "/api/quiz/drafts/{draft_id}", "required"),
    ("updateDraft", "PUT", "/api/quiz/drafts/{draft_id}", "required"),
    ("deleteDraft", "DELETE", "/api/quiz/drafts/{draft_id}", "required"),
    ("csvValidate", "POST", "/api/quiz/drafts/{draft_id}/csv/validate", "required"),
    ("csvCommit", "POST", "/api/quiz/drafts/{draft_id}/csv/commit", "required"),
    ("publish", "POST", "/api/quiz/drafts/{draft_id}/publish", "required"),
    ("getShare", "GET", "/api/quiz/shares/{share_id}", "none"),
    ("createSession", "POST", "/api/quiz/shares/{share_id}/sessions", "required"),
    ("getSession", "GET", "/api/quiz/sessions/{session_id}", "required"),
    ("submit", "POST", "/api/quiz/sessions/{session_id}/submit", "required"),
    ("advance", "POST", "/api/quiz/sessions/{session_id}/advance", "required"),
]


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


# -- JSON Schema ------------------------------------------------------------------

def build_schema() -> Dict[str, Any]:
    _, top = models_json_schema([(m, "validation") for m in C.PUBLIC_MODELS],
                                ref_template="#/$defs/{model}")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://fanfic.world/schemas/quiz-api/{C.CONTRACT_VERSION}",
        "title": "fanfic.world quiz API (Phase 1)",
        "x-contract-version": C.CONTRACT_VERSION,
        "x-source": "server/quiz/contracts.py",
        "$defs": top["$defs"],
    }


# -- TypeScript -------------------------------------------------------------------

def _ref_name(ref: str) -> str:
    prefix = "#/$defs/"
    if not ref.startswith(prefix):
        raise ValueError(f"unsupported $ref {ref}")
    return ref[len(prefix):]


def _ts(s: Dict[str, Any]) -> str:
    if "$ref" in s:
        return _ref_name(s["$ref"])
    if "anyOf" in s:
        parts: List[str] = []
        for sub in s["anyOf"]:
            t = _ts(sub)
            if t not in parts:
                parts.append(t)
        return " | ".join(parts)
    if "const" in s:
        return json.dumps(s["const"], ensure_ascii=False)
    if "enum" in s:
        return " | ".join(json.dumps(v, ensure_ascii=False) for v in s["enum"])
    t = s.get("type")
    if t == "string":
        return "string"
    if t in ("integer", "number"):
        return "number"
    if t == "boolean":
        return "boolean"
    if t == "null":
        return "null"
    if t == "array":
        inner = _ts(s.get("items", {}))
        return f"({inner})[]" if "|" in inner else f"{inner}[]"
    raise ValueError(f"unsupported schema fragment: {json.dumps(s)[:200]}")


_CONSTRAINTS = ("minLength", "maxLength", "pattern", "minimum", "maximum", "minItems", "maxItems")


def _constraint_note(s: Dict[str, Any]) -> str:
    notes = []
    frags = [s] + list(s.get("anyOf", []))
    for f in frags:
        for key in _CONSTRAINTS:
            if key in f:
                notes.append(f"{key} {f[key]}")
        if f.get("type") == "array" and isinstance(f.get("items"), dict):
            for key in _CONSTRAINTS:
                if key in f["items"]:
                    notes.append(f"item {key} {f['items'][key]}")
    return ", ".join(dict.fromkeys(notes))


def _literal_values(alias: Any) -> List[str]:
    return list(typing.get_args(alias))


def build_ts(schema: Dict[str, Any]) -> str:
    defs: Dict[str, Any] = schema["$defs"]
    order = [m.__name__ for m in C.PUBLIC_MODELS]
    order += sorted(k for k in defs if k not in order)
    out: List[str] = [
        "// GENERATED FILE — DO NOT EDIT.",
        "// Source: server/quiz/contracts.py (Pydantic v2). Regenerate: python -m server.quiz.codegen",
        "// Types only: the server owns validation, scoring, attempts, deadlines and reveal.",
        "/* eslint-disable */",
        "",
        f'export const QUIZ_CONTRACT_VERSION = "{C.CONTRACT_VERSION}" as const;',
        "",
        "export const QUIZ_LIMITS = {",
    ]
    limits = {
        "maxQuestions": C.MAX_QUESTIONS, "minOptions": C.MIN_OPTIONS, "maxOptions": C.MAX_OPTIONS,
        "titleMax": C.TITLE_MAX, "promptMax": C.PROMPT_MAX, "optionMax": C.OPTION_MAX,
        "explanationMax": C.EXPLANATION_MAX, "timeLimitMinMs": C.TIME_LIMIT_MIN_MS,
        "timeLimitMaxMs": C.TIME_LIMIT_MAX_MS, "csvMaxChars": C.CSV_MAX_CHARS,
        "csvMaxRows": C.CSV_MAX_ROWS, "listPageMax": C.LIST_PAGE_MAX,
    }
    out += [f"  {k}: {v}," for k, v in limits.items()] + ["} as const;", ""]

    def const_list(name: str, values: List[str]) -> None:
        out.append(f"export const {name} = [")
        out.extend(f"  {json.dumps(v, ensure_ascii=False)}," for v in values)
        out.extend(["] as const;", ""])

    const_list("QUIZ_THEMES", list(C.THEMES))
    const_list("QUIZ_FREE_THEMES", list(C.FREE_THEMES))
    const_list("QUIZ_ERROR_CODES", _literal_values(C.ErrorCode))
    const_list("QUIZ_REJECT_REASONS", _literal_values(C.RejectReason))
    const_list("QUIZ_CSV_ERROR_CODES", _literal_values(C.CsvErrorCode))
    const_list("QUIZ_CSV_COLUMNS", ["kind", "prompt", "options", "correct", "explanation",
                                    "difficulty", "time_limit_ms"])
    out.append("export const QUIZ_ENDPOINTS = {")
    for name, method, path, auth in ENDPOINTS:
        out.append(f'  {name}: {{ method: "{method}", path: "{path}", auth: "{auth}" }},')
    out += ["} as const;", ""]

    for name in order:
        d = defs[name]
        if d.get("type") != "object":
            out.append(f"export type {name} = {_ts(d)};")
            out.append("")
            continue
        desc = (d.get("description") or "").strip().splitlines()
        if desc:
            out.append("/** " + " ".join(x.strip() for x in desc if x.strip()) + " */")
        out.append(f"export interface {name} {{")
        required = set(d.get("required", []))
        for prop, ps in d.get("properties", {}).items():
            note = _constraint_note(ps)
            if note:
                out.append(f"  /** {note} */")
            opt = "" if prop in required else "?"
            out.append(f"  {prop}{opt}: {_ts(ps)};")
        out.append("}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# -- Fixtures: kich ban API tat dinh ------------------------------------------------

class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


def _uid(n: int, space: int = 0) -> str:
    return str(uuid.UUID(int=(space << 64) | n))


def _question(n: int, kind: str, texts: List[str], correct: List[int], *,
              time_limit_ms: Optional[int] = None, explanation: str = "") -> Dict[str, Any]:
    opts = [{"id": _uid(n * 10 + i + 1, 0xC), "text": t} for i, t in enumerate(texts)]
    return {"id": _uid(n, 0xC), "kind": kind, "prompt": f"Câu hỏi mẫu {n}?", "options": opts,
            "correct_option_ids": [opts[i - 1]["id"] for i in correct],
            "explanation": explanation or f"Giải thích mẫu {n}.", "difficulty": "medium",
            "time_limit_ms": time_limit_ms}


SAMPLE_QUESTIONS = [
    _question(1, "single", ["Lam", "Đỏ", "Lục", "Vàng"], [3], time_limit_ms=20_000),
    _question(2, "multiple", ["2", "3", "4", "5"], [1, 3]),
    _question(3, "boolean", ["Đúng", "Sai"], [1]),
]

GOOD_CSV = ("kind,prompt,options,correct,explanation,difficulty,time_limit_ms\n"
            "single,Mẫu CSV 1?,Một|Hai|Ba,2,Vì là hai.,easy,15000\n"
            "multiple,Mẫu CSV 2?,A|B|C|D,1|4,,hard,\n")
BAD_CSV = GOOD_CSV + "boolean,Mẫu CSV 3?,Đúng|Sai|Không rõ,1,,,\nsingle,,A|B,1,,,\n"


def build_api_fixtures() -> Dict[str, Dict[str, Any]]:
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    from server.quiz.entitlements import grant_pro
    from server.quiz.local_store import LocalQuizStore
    from server.quiz.router import QuizRuntime, build_quiz_router
    from server.quiz.service import QuizService

    class _P:
        def __init__(self, uid: str) -> None:
            self.user_id = uid

    def resolve(authorization: Optional[str]) -> _P:
        if not authorization or not authorization.startswith("Bearer tok-"):
            raise HTTPException(401, "auth")
        return _P(authorization[len("Bearer tok-"):])

    tmp = Path(tempfile.mkdtemp(prefix="quiz-codegen-"))
    try:
        clock = _Clock()
        ids = itertools.count(1)
        shares = itertools.count(1)
        store = LocalQuizStore(tmp / "quiz")
        svc = QuizService(store, clock=clock, new_id=lambda: _uid(next(ids)),
                          new_share_id=lambda: f"DemoShare{next(shares):07d}")
        app = FastAPI()
        app.include_router(build_quiz_router(QuizRuntime(svc), resolve_profile=resolve))
        client = TestClient(app)
        fx: Dict[str, Dict[str, Any]] = {}

        def call(name: str, method: str, path: str, *, user: Optional[str] = "creator",
                 body: Any = None, model: Optional[str] = None, raw: Optional[str] = None) -> Any:
            headers = {"Authorization": f"Bearer tok-{user}"} if user else {}
            kwargs: Dict[str, Any] = {"headers": headers}
            if raw is not None:
                kwargs["content"] = raw.encode("utf-8")
                headers["Content-Type"] = "application/json"
            elif body is not None:
                kwargs["json"] = body
            r = client.request(method, path, **kwargs)
            resp_body = r.json() if r.content else None
            fx[name] = {
                "request": {"method": method, "path": path,
                            "auth": f"Bearer <token of {user}>" if user else None,
                            "body": body if raw is None else raw},
                "response": {"status": r.status_code, "body": resp_body},
                "response_model": model,
            }
            return resp_body

        call("entitlements.free", "GET", "/api/quiz/me/entitlements", model="EntitlementSummary")
        call("error.auth_required", "GET", "/api/quiz/drafts", user=None, model="ErrorEnvelope")
        d = call("draft.create", "POST", "/api/quiz/drafts", model="CreatorDraft",
                 body={"title": "Quiz mẫu", "theme_id": "neon-tactics", "questions": SAMPLE_QUESTIONS[:2]})
        path = f"/api/quiz/drafts/{d['draft_id']}"
        call("error.theme_not_entitled", "POST", "/api/quiz/drafts", model="ErrorEnvelope",
             body={"title": "Quiz Pro", "theme_id": "arcane-academy", "questions": []})
        call("error.invalid_request", "POST", "/api/quiz/drafts", model="ErrorEnvelope",
             body={"title": "Quiz", "theme_id": "neon-tactics", "questions": [], "owner_user_id": "x"})
        call("error.invalid_json", "POST", f"{path}/publish", model="ErrorEnvelope", raw="{oops")
        d = call("draft.update", "PUT", path, model="CreatorDraft",
                 body={"expected_revision": 1, "title": "Quiz mẫu", "theme_id": "neon-tactics",
                       "questions": SAMPLE_QUESTIONS})
        call("error.revision_conflict", "PUT", path, model="ErrorEnvelope",
             body={"expected_revision": 1, "title": "Quiz cũ", "theme_id": "neon-tactics", "questions": []})
        call("draft.get", "GET", path, model="CreatorDraft")
        call("error.draft_not_found", "GET", path, user="stranger", model="ErrorEnvelope")
        call("csv.validate.valid", "POST", f"{path}/csv/validate", model="CsvValidationResult",
             body={"csv": GOOD_CSV, "strategy": "append"})
        call("csv.validate.invalid", "POST", f"{path}/csv/validate", model="CsvValidationResult",
             body={"csv": BAD_CSV, "strategy": "append"})
        call("error.csv_invalid", "POST", f"{path}/csv/commit", model="ErrorEnvelope",
             body={"csv": BAD_CSV, "strategy": "append", "expected_revision": 2})
        d2 = call("draft.create_for_csv", "POST", "/api/quiz/drafts", model="CreatorDraft",
                  body={"title": "Nhập CSV", "theme_id": "neon-tactics"})
        call("csv.commit", "POST", f"/api/quiz/drafts/{d2['draft_id']}/csv/commit", model="CreatorDraft",
             body={"csv": GOOD_CSV, "strategy": "replace", "expected_revision": 1})
        call("draft.list", "GET", "/api/quiz/drafts?limit=20&offset=0", model="DraftList")
        pub = call("publish.created", "POST", f"{path}/publish", model="PublishResult",
                   body={"expected_revision": 2})
        call("publish.replayed", "POST", f"{path}/publish", model="PublishResult",
             body={"expected_revision": 2})
        share = f"/api/quiz/shares/{pub['share_id']}"
        call("share.snapshot", "GET", share, user=None, model="PublicQuizSnapshot")
        call("error.share_not_found", "GET", "/api/quiz/shares/NoSuchShare00000", user=None,
             model="ErrorEnvelope")
        call("error.draft_published", "DELETE", f"{path}?expected_revision=2", model="ErrorEnvelope")

        v = call("session.created", "POST", f"{share}/sessions", user="player", model="ParticipantView")
        spath = f"/api/quiz/sessions/{v['session_id']}"
        q1 = SAMPLE_QUESTIONS[0]
        o = [x["id"] for x in q1["options"]]
        first = {"request_id": _uid(1, 0xD), "question_id": q1["id"], "selected_option_ids": [o[0]],
                 "expected_question_revision": 1, "expected_attempt": 1}
        call("submit.accepted_miss", "POST", f"{spath}/submit", user="player", body=first,
             model="SubmitResponse")
        call("submit.duplicate", "POST", f"{spath}/submit", user="player", body=first,
             model="SubmitResponse")
        call("submit.rejected_payload_conflict", "POST", f"{spath}/submit", user="player",
             body=dict(first, selected_option_ids=[o[1]]), model="SubmitResponse")
        call("submit.rejected_attempt_mismatch", "POST", f"{spath}/submit", user="player",
             body=dict(first, request_id=_uid(2, 0xD), selected_option_ids=[o[1]]), model="SubmitResponse")
        call("submit.rejected_invalid_option", "POST", f"{spath}/submit", user="player",
             body=dict(first, request_id=_uid(3, 0xD), expected_attempt=2), model="SubmitResponse")
        call("submit.rejected_wrong_revision", "POST", f"{spath}/submit", user="player",
             body=dict(first, request_id=_uid(4, 0xD), expected_attempt=2, selected_option_ids=[o[2]],
                       expected_question_revision=2), model="SubmitResponse")
        res = call("submit.accepted_hit_second", "POST", f"{spath}/submit", user="player",
                   body=dict(first, request_id=_uid(5, 0xD), expected_attempt=2, selected_option_ids=[o[2]]),
                   model="SubmitResponse")
        call("error.session_not_found", "GET", spath, user="stranger", model="ErrorEnvelope")
        v = call("session.advanced", "POST", f"{spath}/advance", user="player",
                 body={"expected_question_revision": res["view"]["question_revision"]}, model="ParticipantView")
        q2 = SAMPLE_QUESTIONS[1]
        o2 = [x["id"] for x in q2["options"]]
        res = call("submit.accepted_hit_first_multiple", "POST", f"{spath}/submit", user="player",
                   body={"request_id": _uid(6, 0xD), "question_id": q2["id"], "selected_option_ids": [o2[2], o2[0]],
                         "expected_question_revision": 2, "expected_attempt": 1}, model="SubmitResponse")
        v = call("session.advanced_boolean", "POST", f"{spath}/advance", user="player",
                 body={"expected_question_revision": 2}, model="ParticipantView")
        q3 = SAMPLE_QUESTIONS[2]
        call("submit.accepted_boolean_miss", "POST", f"{spath}/submit", user="player",
             body={"request_id": _uid(7, 0xD), "question_id": q3["id"],
                   "selected_option_ids": [q3["options"][1]["id"]],
                   "expected_question_revision": 3, "expected_attempt": 1}, model="SubmitResponse")
        call("session.finished", "POST", f"{spath}/advance", user="player",
             body={"expected_question_revision": 3}, model="ParticipantView")

        late = call("session.created_timed", "POST", f"{share}/sessions", user="late-player",
                    model="ParticipantView")
        clock.now = clock.now + timedelta(seconds=30)
        call("submit.rejected_late", "POST", f"/api/quiz/sessions/{late['session_id']}/submit",
             user="late-player", model="SubmitResponse",
             body={"request_id": _uid(8, 0xD), "question_id": q1["id"], "selected_option_ids": [o[2]],
                   "expected_question_revision": 1, "expected_attempt": 1})

        for i in range(4):
            extra = call(f"_quota_draft_{i}", "POST", "/api/quiz/drafts", model="CreatorDraft",
                         body={"title": f"Quota {i}", "theme_id": "neon-tactics",
                               "questions": [SAMPLE_QUESTIONS[2]]})
            call(f"_quota_publish_{i}", "POST", f"/api/quiz/drafts/{extra['draft_id']}/publish",
                 model="PublishResult", body={"expected_revision": 1})
        call("error.quota_exceeded", "POST", f"/api/quiz/drafts/{d2['draft_id']}/publish",
             model="ErrorEnvelope", body={"expected_revision": 2})
        grant_pro(store, user_id="creator", actor="codegen-fixture", reason="synthetic Pro for fixtures",
                  now=clock(), grant_id=_uid(1, 0xE))
        call("entitlements.pro", "GET", "/api/quiz/me/entitlements", model="EntitlementSummary")
        call("draft.delete", "DELETE", f"/api/quiz/drafts/{d2['draft_id']}?expected_revision=2")
        return {k: v for k, v in fx.items() if not k.startswith("_")}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# -- Fixtures: ca hop dong valid/invalid --------------------------------------------

def build_contract_fixtures(api: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    q_single, q_multi, q_bool = SAMPLE_QUESTIONS
    view = api["session.created"]["response"]["body"]
    revealed = api["submit.accepted_hit_second"]["response"]["body"]["view"]
    snapshot = api["share.snapshot"]["response"]["body"]
    submit = {"request_id": _uid(1, 0xD), "question_id": q_single["id"],
              "selected_option_ids": [q_single["options"][0]["id"]],
              "expected_question_revision": 1, "expected_attempt": 1}
    leaky_q = dict(snapshot["questions"][0], correct_option_ids=[q_single["options"][2]["id"]])
    cases: List[Tuple[str, bool, str, str, Any]] = [
        ("draft_question_single", True, "DraftQuestion", "single choice, one key", q_single),
        ("draft_question_multiple", True, "DraftQuestion", "multiple choice, exact-set key", q_multi),
        ("draft_question_boolean", True, "DraftQuestion", "boolean with exactly two options", q_bool),
        ("draft_create_minimal", True, "DraftCreateRequest", "questions default to []",
         {"title": "Quiz", "theme_id": "neon-tactics"}),
        ("submit_request", True, "SubmitRequest", "client sends selection + expectations only", submit),
        ("participant_view_answering", True, "ParticipantView", "no reveal while answering", view),
        ("participant_view_revealed", True, "ParticipantView", "reveal after the question closes", revealed),
        ("csv_commit_request", True, "CsvCommitRequest", "append with expected revision",
         {"csv": GOOD_CSV, "strategy": "append", "expected_revision": 3}),

        ("boolean_three_options", False, "DraftQuestion", "boolean needs exactly 2 options",
         dict(q_bool, options=q_single["options"][:3], correct_option_ids=[q_single["options"][0]["id"]])),
        ("single_two_keys", False, "DraftQuestion", "single takes exactly one key",
         dict(q_single, correct_option_ids=[o["id"] for o in q_single["options"][:2]])),
        ("key_not_an_option", False, "DraftQuestion", "keys must reference own options",
         dict(q_single, correct_option_ids=[q_multi["options"][0]["id"]])),
        ("duplicate_option_ids", False, "DraftQuestion", "option ids unique",
         dict(q_single, options=[q_single["options"][0], q_single["options"][0]],
              correct_option_ids=[q_single["options"][0]["id"]])),
        ("nine_options", False, "DraftQuestion", "max 8 options",
         dict(q_single, options=[{"id": _uid(900 + i, 0xC), "text": f"O{i}"} for i in range(9)],
              correct_option_ids=[_uid(900, 0xC)])),
        ("blank_prompt", False, "DraftQuestion", "prompt must not be blank", dict(q_single, prompt="   ")),
        ("time_limit_too_short", False, "DraftQuestion", "time limit >= 5000 ms",
         dict(q_single, time_limit_ms=1000)),
        ("unknown_field", False, "DraftQuestion", "extra fields are forbidden", dict(q_single, points=5)),
        ("owner_from_client", False, "DraftCreateRequest", "owner comes from the resolved profile",
         {"title": "Quiz", "theme_id": "neon-tactics", "owner_user_id": "someone"}),
        ("unknown_theme", False, "DraftCreateRequest", "theme must be a known id",
         {"title": "Quiz", "theme_id": "sakura"}),
        ("revision_as_string", False, "DraftUpdateRequest", "strict: no string->int coercion",
         {"expected_revision": "1", "title": "Quiz", "theme_id": "neon-tactics", "questions": []}),
        ("score_from_client", False, "SubmitRequest", "client never sends score",
         dict(submit, score=1)),
        ("attempt_three", False, "SubmitRequest", "expected_attempt is 1 or 2", dict(submit, expected_attempt=3)),
        ("attempt_as_bool", False, "SubmitRequest", "strict: no bool->int", dict(submit, expected_attempt=True)),
        ("duplicate_selection", False, "SubmitRequest", "selection ids unique",
         dict(submit, selected_option_ids=submit["selected_option_ids"] * 2)),
        ("reveal_while_answering", False, "ParticipantView", "no key before reveal",
         dict(view, reveal=revealed["reveal"])),
        ("can_submit_after_reveal", False, "ParticipantView", "closed question cannot accept answers",
         dict(revealed, can_submit=True)),
        ("snapshot_with_key", False, "PublicQuizSnapshot", "public snapshot cannot carry keys",
         dict(snapshot, questions=[leaky_q] + snapshot["questions"][1:])),
        ("rejected_with_receipt", False, "SubmitResponse", "rejections carry no receipt",
         dict(api["submit.accepted_miss"]["response"]["body"], outcome="rejected", reason="late")),
        ("csv_valid_with_errors", False, "CsvValidationResult", "valid iff no errors",
         dict(api["csv.validate.invalid"]["response"]["body"], valid=True)),
    ]
    return {f"{'valid' if ok else 'invalid'}/{name}.json": {"model": model, "valid": ok, "why": why,
                                                           "data": data}
            for name, ok, model, why, data in cases}


# -- Ghi / kiem ----------------------------------------------------------------------

def build_all() -> Dict[str, str]:
    schema = build_schema()
    api = build_api_fixtures()
    files = {SCHEMA_FILE: _dumps(schema), TS_FILE: build_ts(schema)}
    for name, case in build_contract_fixtures(api).items():
        files[f"{FIXTURE_DIR}/{name}"] = _dumps(case)
    for name, fx in api.items():
        files[f"{FIXTURE_DIR}/api/{name}.json"] = _dumps(fx)
    files[f"{FIXTURE_DIR}/index.json"] = _dumps(sorted(k[len(FIXTURE_DIR) + 1:] for k in files
                                                      if k.startswith(FIXTURE_DIR + "/")))
    return files


def _existing(out_dir: Path) -> Dict[str, str]:
    found = {}
    for p in [out_dir / SCHEMA_FILE, out_dir / TS_FILE, *sorted((out_dir / FIXTURE_DIR).rglob("*.json"))]:
        if p.is_file():
            found[p.relative_to(out_dir).as_posix()] = p.read_text(encoding="utf-8").replace("\r\n", "\n")
    return found


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m server.quiz.codegen")
    ap.add_argument("--check", action="store_true", help="fail if committed artefacts differ")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)
    files = build_all()
    current = _existing(args.out)
    changed = sorted(k for k in files if current.get(k) != files[k])
    stale = sorted(k for k in current if k not in files)
    if args.check:
        if changed or stale:
            for k in changed:
                print(f"out of date: {k}")
            for k in stale:
                print(f"stale file: {k}")
            print("Run: python -m server.quiz.codegen", file=sys.stderr)
            return 1
        print(f"quiz contracts up to date ({len(files)} files)")
        return 0
    for k in stale:
        (args.out / k).unlink()
    for k, text in files.items():
        p = args.out / k
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    print(f"wrote {len(files)} files ({len(changed)} changed, {len(stale)} removed) under {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
