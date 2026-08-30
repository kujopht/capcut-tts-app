"""
Generic change detection — Story Harvester V5 Phase 11.

Extends the existing fiction-only `change_detection.ChangeKind` (7 states:
UNCHANGED/NEW_CHAPTER/NEEDS_BASELINE/UPDATED_CHAPTER/REMOVED_OR_UNAVAILABLE/
SOURCE_METADATA_CHANGED/TRANSIENT_FAILURE) to work on any source unit, not
just chapters. `UnitChangeKind` below has the SAME 7 states renamed to
generic terms - `TO_FICTION_CHANGE_KIND`/`FROM_FICTION_CHANGE_KIND` are the
compatibility aliases the mission asks to keep "where useful", so existing
fiction code can translate to/from this generic layer without a rewrite.

Mirrors `incremental.diff_toc`'s existing split: index-level NEW/REMOVED
classification is pure (no network - just comparing identity keys), while
per-unit UPDATED/UNCHANGED detection needs a content hash to compare against
(supplied by the caller after acquiring a unit, mirroring how
`change_detection.revalidate` needs a real fetch to tell UPDATED from
UNCHANGED). This module does not fetch anything itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence


class UnitChangeKind(str, Enum):
    UNCHANGED = "unchanged"
    NEW_UNIT = "new_unit"
    NEEDS_BASELINE = "needs_baseline"
    UPDATED_UNIT = "updated_unit"
    REMOVED_OR_UNAVAILABLE = "removed_or_unavailable"
    SOURCE_METADATA_CHANGED = "source_metadata_changed"
    TRANSIENT_FAILURE = "transient_failure"


#: Fiction compatibility aliases - see module docstring. Imported lazily
#: inside a function (not at module top level) to avoid the universal
#: package depending on the top-level scraper package at import time for
#: something only needed by callers who explicitly want the translation.
def _fiction_change_kind_maps():
    from server.scraper.change_detection import ChangeKind
    to_fiction = {
        UnitChangeKind.UNCHANGED: ChangeKind.UNCHANGED,
        UnitChangeKind.NEW_UNIT: ChangeKind.NEW_CHAPTER,
        UnitChangeKind.NEEDS_BASELINE: ChangeKind.NEEDS_BASELINE,
        UnitChangeKind.UPDATED_UNIT: ChangeKind.UPDATED_CHAPTER,
        UnitChangeKind.REMOVED_OR_UNAVAILABLE: ChangeKind.REMOVED_OR_UNAVAILABLE,
        UnitChangeKind.SOURCE_METADATA_CHANGED: ChangeKind.SOURCE_METADATA_CHANGED,
        UnitChangeKind.TRANSIENT_FAILURE: ChangeKind.TRANSIENT_FAILURE,
    }
    from_fiction = {v: k for k, v in to_fiction.items()}
    return to_fiction, from_fiction


def to_fiction_change_kind(kind: "UnitChangeKind"):
    to_fiction, _ = _fiction_change_kind_maps()
    return to_fiction[kind]


def from_fiction_change_kind(kind) -> "UnitChangeKind":
    _, from_fiction = _fiction_change_kind_maps()
    return from_fiction[kind]


@dataclass(frozen=True)
class UnitChange:
    kind: UnitChangeKind
    unit_identity_key: str
    evidence: str = ""
    previous_content_hash: str = ""
    new_content_hash: str = ""
    status_code: Optional[int] = None
    revalidated: bool = False


@dataclass
class UnitChangePlan:
    changes: List[UnitChange] = field(default_factory=list)

    def by_kind(self, kind: UnitChangeKind) -> List[UnitChange]:
        return [c for c in self.changes if c.kind == kind]

    def counts(self) -> Dict[str, int]:
        result = {k.value: 0 for k in UnitChangeKind}
        for c in self.changes:
            result[c.kind.value] += 1
        return result

    @property
    def keys_needing_fetch(self) -> List[str]:
        """Identity keys actually worth acquiring - excludes UNCHANGED
        (the whole point of incremental detection) and TRANSIENT_FAILURE
        (retry is a separate backoff concern, not this batch)."""
        return [c.unit_identity_key for c in self.changes
               if c.kind not in (UnitChangeKind.UNCHANGED, UnitChangeKind.TRANSIENT_FAILURE)]


def classify_index(previous_keys: Sequence[str],
                    current_keys: Sequence[str]) -> UnitChangePlan:
    """Pure, index-only classification - no network, mirrors
    `incremental.diff_toc`: keys newly present are NEW_UNIT, keys that
    disappeared are REMOVED_OR_UNAVAILABLE, keys in both need a real
    content-hash comparison later (defaults to NEEDS_BASELINE here - a
    caller with a stored previous content hash should call
    `classify_unit_content` instead for those keys)."""
    prev = set(previous_keys)
    curr = set(current_keys)
    changes: List[UnitChange] = []
    for key in current_keys:
        if key not in prev:
            changes.append(UnitChange(kind=UnitChangeKind.NEW_UNIT, unit_identity_key=key))
        else:
            changes.append(UnitChange(kind=UnitChangeKind.NEEDS_BASELINE, unit_identity_key=key))
    for key in previous_keys:
        if key not in curr:
            changes.append(UnitChange(
                kind=UnitChangeKind.REMOVED_OR_UNAVAILABLE, unit_identity_key=key,
                evidence="khong con trong danh sach unit hien tai"))
    return UnitChangePlan(changes=changes)


def classify_unit_content(
        unit_identity_key: str, *, previous_content_hash: Optional[str],
        new_content_hash: Optional[str], status_code: Optional[int] = None,
        transient: bool = False) -> UnitChange:
    """Given a real acquisition outcome for ONE already-known unit, decide
    UPDATED/UNCHANGED/NEEDS_BASELINE/TRANSIENT_FAILURE/REMOVED_OR_UNAVAILABLE.
    Mirrors `change_detection.py`'s own state-machine rules exactly, just
    generalized past "chapter"."""
    if transient:
        return UnitChange(kind=UnitChangeKind.TRANSIENT_FAILURE,
                          unit_identity_key=unit_identity_key, status_code=status_code,
                          revalidated=True)
    if new_content_hash is None:
        return UnitChange(kind=UnitChangeKind.REMOVED_OR_UNAVAILABLE,
                          unit_identity_key=unit_identity_key, status_code=status_code,
                          revalidated=True)
    if previous_content_hash is None:
        return UnitChange(kind=UnitChangeKind.NEEDS_BASELINE,
                          unit_identity_key=unit_identity_key,
                          new_content_hash=new_content_hash, status_code=status_code,
                          revalidated=True)
    if previous_content_hash == new_content_hash:
        return UnitChange(kind=UnitChangeKind.UNCHANGED, unit_identity_key=unit_identity_key,
                          previous_content_hash=previous_content_hash,
                          new_content_hash=new_content_hash, status_code=status_code,
                          revalidated=True)
    return UnitChange(kind=UnitChangeKind.UPDATED_UNIT, unit_identity_key=unit_identity_key,
                      previous_content_hash=previous_content_hash,
                      new_content_hash=new_content_hash, status_code=status_code,
                      revalidated=True)
