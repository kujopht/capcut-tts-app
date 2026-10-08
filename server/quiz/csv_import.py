"""
Nhap cau hoi tu CSV — kiem tra TOAN BO truoc, commit tat-ca-hoac-khong.

Dinh dang (dong 1 la header, ten cot khong phan biet hoa thuong, thu tu tu do):

  | cot             | bat buoc | gia tri                                              |
  |-----------------|----------|------------------------------------------------------|
  | kind            | co       | single / multiple / boolean                          |
  | prompt          | co       | <= 1000 ky tu                                        |
  | options         | co       | 2..8 lua chon cach nhau boi `|` (boolean: dung 2)    |
  | correct         | co       | chi so 1-based cach nhau boi `|` (single/boolean: 1) |
  | explanation     | khong    | <= 1000 ky tu                                        |
  | difficulty      | khong    | easy / medium / hard (mac dinh medium)               |
  | time_limit_ms   | khong    | 5000..120000, trong = khong gioi han                 |

`row` trong loi la so DONG VAT LY 1-based noi ban ghi bat dau (header = 1),
khop voi so dong cua bang tinh khi khong co o nhieu dong. Toi da 200 ban ghi du
lieu; dong trong hoan toan bi bo qua. Ky tu `|` khong dung duoc trong noi dung
lua chon (Phase 1).
"""

from __future__ import annotations

import csv
import io
from typing import Callable, Dict, List, Tuple

from pydantic import ValidationError

from server.quiz.contracts import (
    CSV_MAX_ERRORS, CSV_MAX_ROWS, EXPLANATION_MAX, MAX_OPTIONS, MIN_OPTIONS,
    OPTION_MAX, PROMPT_MAX, TIME_LIMIT_MAX_MS, TIME_LIMIT_MIN_MS, CsvError,
    CsvRowPreview, DraftQuestion, Option,
)

REQUIRED_COLUMNS = ("kind", "prompt", "options", "correct")
OPTIONAL_COLUMNS = ("explanation", "difficulty", "time_limit_ms")
KNOWN_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
KINDS = ("single", "multiple", "boolean")
DIFFICULTIES = ("easy", "medium", "hard")
SEPARATOR = "|"


class _Errors:
    def __init__(self) -> None:
        self.items: List[CsvError] = []

    def add(self, row: int, column: str, code: str, message: str) -> None:
        if len(self.items) < CSV_MAX_ERRORS:
            self.items.append(CsvError(row=row, column=column, code=code, message=message))

    def __bool__(self) -> bool:
        return bool(self.items)


def parse_csv(text: str) -> Tuple[List[CsvRowPreview], List[CsvError], int]:
    """Tra `(rows, errors, row_count)`. Co loi thi `rows` chi chua cac dong hop le."""
    errors = _Errors()
    if text.startswith("﻿"):
        text = text[1:]
    if not text.strip():
        errors.add(1, "file", "empty_file", "CSV is empty.")
        return [], errors.items, 0

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    records: List[Tuple[int, List[str]]] = []
    try:
        while True:
            start = reader.line_num + 1
            try:
                cells = next(reader)
            except StopIteration:
                break
            if not any(c.strip() for c in cells):
                continue
            records.append((start, cells))
            if len(records) > CSV_MAX_ROWS + 1:
                break
    except csv.Error as exc:
        errors.add(max(1, reader.line_num), "file", "csv_syntax", f"CSV syntax error: {exc}"[:300])
        return [], errors.items, 0

    if not records:
        errors.add(1, "file", "empty_file", "CSV is empty.")
        return [], errors.items, 0

    header_row, header_cells = records[0]
    columns = [c.strip().lower() for c in header_cells]
    seen: Dict[str, int] = {}
    for idx, name in enumerate(columns):
        if name in seen:
            errors.add(header_row, "header", "duplicate_column", f"Duplicate column '{name}'."[:300])
        elif name not in KNOWN_COLUMNS:
            errors.add(header_row, "header", "unknown_column", f"Unknown column '{name}'."[:300])
        seen.setdefault(name, idx)
    for name in REQUIRED_COLUMNS:
        if name not in seen:
            errors.add(header_row, "header", "missing_column", f"Missing required column '{name}'.")
    if errors:
        return [], errors.items, 0

    data = records[1:]
    if len(data) > CSV_MAX_ROWS:
        errors.add(data[CSV_MAX_ROWS][0], "file", "too_many_rows",
                   f"At most {CSV_MAX_ROWS} question rows are allowed.")
        return [], errors.items, 0

    rows: List[CsvRowPreview] = []
    for row_no, cells in data:
        if len(cells) > len(columns) and any(c.strip() for c in cells[len(columns):]):
            errors.add(row_no, "file", "csv_syntax", "Row has more cells than the header.")
            continue
        get = lambda name: (cells[seen[name]] if name in seen and seen[name] < len(cells) else "").strip()
        preview = _parse_row(row_no, get, errors)
        if preview is not None:
            rows.append(preview)
    return rows, errors.items, len(data)


def _parse_row(row: int, get: Callable[[str], str], errors: _Errors):
    before = len(errors.items)

    kind = get("kind").lower()
    if kind not in KINDS:
        errors.add(row, "kind", "invalid_kind", "kind must be single, multiple or boolean.")

    prompt = get("prompt")
    if not prompt:
        errors.add(row, "prompt", "blank_required", "prompt is required.")
    elif len(prompt) > PROMPT_MAX:
        errors.add(row, "prompt", "too_long", f"prompt exceeds {PROMPT_MAX} characters.")

    raw_options = get("options")
    options = [o.strip() for o in raw_options.split(SEPARATOR)] if raw_options else []
    if not raw_options:
        errors.add(row, "options", "blank_required", "options is required.")
    elif any(not o for o in options):
        errors.add(row, "options", "invalid_options", "Options must not be blank.")
    elif not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
        errors.add(row, "options", "invalid_options",
                   f"Between {MIN_OPTIONS} and {MAX_OPTIONS} options are required.")
    elif kind == "boolean" and len(options) != 2:
        errors.add(row, "options", "invalid_options", "boolean requires exactly 2 options.")
    elif any(len(o) > OPTION_MAX for o in options):
        errors.add(row, "options", "too_long", f"An option exceeds {OPTION_MAX} characters.")
    elif len({o.casefold() for o in options}) != len(options):
        errors.add(row, "options", "invalid_options", "Options must be distinct.")

    raw_correct = get("correct")
    correct: List[int] = []
    if not raw_correct:
        errors.add(row, "correct", "blank_required", "correct is required.")
    else:
        try:
            correct = [int(p.strip()) for p in raw_correct.split(SEPARATOR)]
        except ValueError:
            errors.add(row, "correct", "invalid_correct", "correct must be 1-based option numbers.")
        else:
            if len(set(correct)) != len(correct) or any(
                    i < 1 or i > max(len(options), 1) or i > MAX_OPTIONS for i in correct):
                errors.add(row, "correct", "invalid_correct",
                           "correct must reference distinct existing options.")
            elif kind in ("single", "boolean") and len(correct) != 1:
                errors.add(row, "correct", "invalid_correct",
                           "single/boolean questions take exactly one correct option.")

    explanation = get("explanation")
    if len(explanation) > EXPLANATION_MAX:
        errors.add(row, "explanation", "too_long", f"explanation exceeds {EXPLANATION_MAX} characters.")

    difficulty = get("difficulty").lower() or "medium"
    if difficulty not in DIFFICULTIES:
        errors.add(row, "difficulty", "invalid_value", "difficulty must be easy, medium or hard.")

    raw_limit = get("time_limit_ms")
    time_limit = None
    if raw_limit:
        try:
            time_limit = int(raw_limit)
            if not TIME_LIMIT_MIN_MS <= time_limit <= TIME_LIMIT_MAX_MS:
                raise ValueError
        except ValueError:
            errors.add(row, "time_limit_ms", "invalid_value",
                       f"time_limit_ms must be an integer {TIME_LIMIT_MIN_MS}..{TIME_LIMIT_MAX_MS}.")

    if len(errors.items) != before:
        return None
    try:
        return CsvRowPreview(row=row, kind=kind, prompt=prompt, options=options,
                             correct_option_indexes=correct, explanation=explanation,
                             difficulty=difficulty, time_limit_ms=time_limit)
    except ValidationError as exc:  # phong ve: luat hop dong chat hon kiem tra o tren
        errors.add(row, "file", "invalid_value", str(exc.errors()[0]["msg"])[:300])
        return None


def rows_to_questions(rows: List[CsvRowPreview], new_id: Callable[[], str]) -> List[DraftQuestion]:
    out: List[DraftQuestion] = []
    for r in rows:
        options = [Option(id=new_id(), text=t) for t in r.options]
        out.append(DraftQuestion(
            id=new_id(), kind=r.kind, prompt=r.prompt, options=options,
            correct_option_ids=[options[i - 1].id for i in r.correct_option_indexes],
            explanation=r.explanation, difficulty=r.difficulty, time_limit_ms=r.time_limit_ms,
        ))
    return out
