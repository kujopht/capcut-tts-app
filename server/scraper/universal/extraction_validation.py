"""
Universal Acquisition Engine — content-extraction VALIDATION module.

Given a chunk of extracted text (from ANY tier — T0 direct HTML, T2
browser-rendered DOM, T3 network JSON, T4 document text), decide whether
it is real, useful, non-boilerplate content or a false positive
(navbar/widget/empty page), and produce a numeric validation score plus
specific Vietnamese reasons.

Why this module exists (vs `server/scraper/content_extraction.py`):
`extract_content_v3`'s internal `_score()` is tightly coupled to an
HTML-tree candidate pipeline — it can only score text that arrived via
an HTML tree. Text observed from a JSON API response (T3) or pulled from
a PDF (T4) has no HTML tree to score, so it never goes through that
pipeline at all. This module validates a plain extracted TEXT STRING
(plus a bit of context: expected title, previously-seen content hashes)
regardless of which tier produced it.

Zero dependencies — stdlib `re`/`hashlib`/`dataclasses` only. `None` of
the normalization logic here imports from `content_extraction.py`; the
small normalize/hash helpers are REPLICATED locally so the hash values
match that module's convention (whitespace-collapse + strip + lowercase
→ sha256 of utf-8 bytes), keeping this module usable by T2/T3/T4 callers
that have no HTML tree at all.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set


# ---------------------------------------------------------------------------
# Scoring weights (documented, not scattered magic numbers).
#
# Each check contributes to the score via subtraction from a base of 100.0.
#   length       -> HARD GATE: if len(clean) < min_length, score is capped
#                   below the pass threshold AND passed is forced False.
#   sentence     -> -60 if sentence_count == 0 (a wall of nav labels/lists);
#                   -12 if sentence density is low for the length.
#   boilerplate  -> -55 if >60% of paragraphs are known boilerplate.
#   title_agree  -> -15 (soft, moderate deduction) if expected_title is
#                   given but not found in body. Soft on purpose: not every
#                   real page states its own title in-body.
#   junk_pattern -> -60 if the whole text matches a false-positive
#                   signature (repeated placeholder / >80% non-alphanumeric).
#
#   passed == (score >= 50.0 AND length check passed). The length check is
#   a hard floor — no amount of other-check success lets a too-short string
#   pass (the +score cannot exceed the cap below the threshold).
#
#   ceiling_below_pass = 45.0  (any value < 50.0)
# ---------------------------------------------------------------------------

#: Threshold for `passed == True` (see module docstring + scoring header).
_PASS_SCORE = 50.0
#: Cap applied to a text that fails the length hard-floor — always below the
#: pass threshold regardless of how well every other check passes.
_LENGTH_FAIL_CAP = 45.0

#: Deduction weights (as constants so they are explained once, not magic).
#: `_SENTENCE_ZERO_DEDUCT` is > 50.0 on purpose: over the min length a wall
#: of comma-separated nav labels has length but zero real sentences, and that
#: is exactly the navbar/widget-only false positive the mission calls out — it
#: must drop the score below the pass threshold, not merely nick it.
_SENTENCE_ZERO_DEDUCT = 60.0
_SENTENCE_SPARSE_DEDUCT = 12.0
_BOILERPLATE_HEAVY_DEDUCT = 55.0
_TITLE_MISS_DEDUCT = 15.0
_JUNK_PATTERN_DEDUCT = 60.0

#: A text is `passed` only if `score >= _PASS_SCORE` AND the length check
#: passed (hard floor).

#: Boilerplate ratio at/above which we deduct heavily.
_BOILERPLATE_HEAVY_THRESHOLD = 0.60

#: Sentence-final punctuation set (English + Vietnamese).
_SENTENCE_FINAL = ".!?…"
#: Case word ending a sentence — must start with an uppercase letter
#: (catches Vietnamese/English capitalised words after a period).
_CAPITAL_START = re.compile(r"[A-ZÀ-Ỹ\u00c0-\u024f]")

#: Junk regexes — deliberately anchored and linear (no nested quantifiers /
#: catastrophic-backtracking risk). Each is a single alternation checked
#: against the whole normalized text.
_NON_ALNUM = re.compile(r"\W")
_JUNK_PLACEHOLDER = re.compile(
    r"^(?:loading|đang\s*tải|\.\.\.|\.\s*)*$", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Normalization + hash (REPLICATED from content_extraction.py — must match).
# ---------------------------------------------------------------------------
def _normalize_for_compare(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _paragraph_hash(text: str) -> str:
    """sha256 of the normalized paragraph — MUST match the byte convention
    used by `content_extraction.py::_paragraph_hash`."""
    return hashlib.sha256(_normalize_for_compare(text).encode("utf-8")).hexdigest()


def _normalize_whole(text: str) -> str:
    """Whitespace-collapsed, lowercased full text — used for the content_hash
    (mission: distinct pages produce distinct hashes, deterministic)."""
    return _normalize_for_compare(text)


# ===========================================================================
# Public API
# ===========================================================================
@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    score: float  # 0.0-100.0
    reasons: List[str]  # human-readable, Vietnamese, explaining any deduction
    content_hash: str  # sha256 of normalized text, for distinct-page checks
    sentence_count: int
    boilerplate_ratio: float  # 0.0-1.0, estimate of repeated/template text

    def __init__(
        self,
        passed: bool,
        score: float,
        reasons: List[str],
        content_hash: str,
        sentence_count: int,
        boilerplate_ratio: float,
    ) -> None:
        object.__setattr__(self, "passed", passed)
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "reasons", list(reasons))
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(self, "sentence_count", sentence_count)
        object.__setattr__(self, "boilerplate_ratio", boilerplate_ratio)


def _count_sentences(text: str) -> int:
    """Heuristic sentence counter — split on sentence-final punctuation
    followed by whitespace+uppercase, or end-of-string. Linear regex, no
    catastrophic backtracking. Returns 0 for text with no sentence-final
    punctuation (e.g. a comma-separated navigation label wall)."""
    if not text:
        return 0
    count = 0
    for m in re.finditer(r"[.!?…]+(?=\s+[A-ZÀ-Ỹ\u00c0-\u024f]|\s*$)", text):
        count += 1
    return count


def _title_agreement_missing(text: str, expected_title: Optional[str]) -> bool:
    """Return True (deduct) if expected_title is given but not present (as a
    meaningful fragment or verbatim, case/whitespace-insensitive) in the body."""
    if not expected_title:
        return False
    title_norm = _normalize_for_compare(expected_title)
    if not title_norm:
        return False
    head = _normalize_for_compare(text[:500])
    if title_norm in head:
        return False
    # meaningful fragment — words longer than 3 chars
    for word in re.findall(r"\b\w{4,}\b", title_norm):
        if word in head:
            return False
    return True


def hashes_are_distinct(hash_a: str, hash_b: str) -> bool:
    """True when both hashes are non-empty and differ — the one place to
    assert the mission's "distinct pages produce distinct hashes" check."""
    return hash_a != hash_b and bool(hash_a) and bool(hash_b)


def _boilerplate_ratio(
    text: str, known_content_hashes: Optional[Set[str]]
) -> float:
    """Fraction of paragraphs (split on blank lines) whose hash is in
    known_content_hashes. 0.0 if no known hashes are provided."""
    if not known_content_hashes:
        return 0.0
    paragraphs = [
        p
        for p in re.split(r"\n\s*\n", text)
        if p.strip()
    ]
    if not paragraphs:
        return 0.0
    known = {_paragraph_hash(p) for p in paragraphs}
    matched = len(known & set(known_content_hashes))
    return matched / len(paragraphs)


def validate_extracted_content(
    text: str,
    *,
    expected_title: Optional[str] = None,
    min_length: int = 200,
    known_content_hashes: Optional[Set[str]] = None,
) -> ValidationResult:
    """Validate a plain extracted text string (from ANY tier) and return a
    numeric score plus specific Vietnamese reasons.

    See module docstring and the scoring-weights comment block for the exact
    weights. `passed` requires `score >= 50.0` AND the length hard-floor.
    """
    clean = text.strip() if text else ""
    content_hash = hashlib.sha256(
        _normalize_whole(clean).encode("utf-8")
    ).hexdigest()

    reasons: List[str] = []

    # -- Check 1: minimum useful length (HARD FLOOR) ---------------------
    length_ok = len(clean) >= min_length
    if not length_ok:
        reasons.append(
            f"van ban qua ngan ({len(clean)} ky tu) < toi thieu {min_length} ky tu"
        )

    # -- Check 2: sentence density ---------------------------------------
    sentence_count = _count_sentences(clean) if clean else 0

    # -- Check 3: boilerplate ratio ---------------------------------------
    boilerplate_ratio = _boilerplate_ratio(clean, known_content_hashes)

    # -- Check 4: title/content agreement (soft) --------------------------
    title_missing = _title_agreement_missing(clean, expected_title)

    # -- Check 6: junk pattern --------------------------------------------
    junk = False
    if clean:
        alnum_len = len(_NON_ALNUM.sub("", clean))
        if alnum_len / max(len(clean), 1) < 0.2:
            junk = True
        elif _JUNK_PLACEHOLDER.match(_normalize_for_compare(clean)):
            junk = True

    # -- Combine: start at base, subtract deductions -----------------------
    score = 100.0

    if sentence_count == 0:
        score -= _SENTENCE_ZERO_DEDUCT
        reasons.append("khong tim thay cau van thuc su (sentence_count == 0)")
    elif len(clean) > min_length * 3 and sentence_count < (len(clean) / 200):
        score -= _SENTENCE_SPARSE_DEDUCT
        reasons.append("mat do cau van qua thap so voi do dai van ban")

    if boilerplate_ratio >= _BOILERPLATE_HEAVY_THRESHOLD:
        score -= _BOILERPLATE_HEAVY_DEDUCT
        reasons.append(
            f"{boilerplate_ratio:.0%} doan van trung boilerplate da biet"
        )

    if title_missing:
        score -= _TITLE_MISS_DEDUCT
        reasons.append(
            "tieu de ky vong khong xuat hien trong phan dau noi dung "
            "(kiem tra mem — khong phai moi trang de ghi tieu de vao than bai)"
        )

    if junk:
        score -= _JUNK_PATTERN_DEDUCT
        reasons.append("van ban giong placeholder/du lieu trang lap lai")

    # -- Hard floor: length. Cap below the pass threshold no matter what. -
    if not length_ok:
        score = min(score, _LENGTH_FAIL_CAP)

    score = max(0.0, min(100.0, score))

    passed = (score >= _PASS_SCORE) and length_ok

    return ValidationResult(
        passed=passed,
        score=round(score, 1),
        reasons=reasons,
        content_hash=content_hash,
        sentence_count=sentence_count,
        boilerplate_ratio=round(boilerplate_ratio, 3),
    )
