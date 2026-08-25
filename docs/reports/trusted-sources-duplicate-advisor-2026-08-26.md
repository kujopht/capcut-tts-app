# Trusted Sources: duplicate-advisor investigation (2026-08-26)

## Background

PR #55 added `TrustedSourceService._phat_hien_novel_trung` — an advisory
check that flags `VideoImport.possible_duplicate_novel_id` when a YouTube
video being imported already exists as a Novel (some real Novels were
created directly from YouTube videos, via Google Drive audio import, before
Trusted Sources existed). It reuses `MetadataStore.find_novels(query=...)`,
which builds `q_or(contains("title", video_id), contains("description",
video_id))`.

A belief formed that this check wasn't firing on a real known case, and that
the cause was a missing Appwrite fulltext index (Appwrite's `search()`
requires one; `contains()` was assumed to also require one). PR #56 added
`title_fulltext_idx` + `description_fulltext_idx` to fix this.

## Finding 1 — the fulltext-index assumption was wrong

Live testing against the actual self-hosted Appwrite instance (version
1.9.6, confirmed via API version field — this is self-hosted on GCE, not
Appwrite Cloud) disproved the assumption. Method: created a disposable
collection (`zz_qa_fulltext_semantics_test`) inside the real
`fanfic-world-prod`/`fanfic_world_prod` project, with three documents (A:
unique token in title only, B: unique token in description only, C:
neither), and ran the exact `q_or(contains(title,...),
contains(description,...))` shape:

| Configuration | `contains(title, X)` | `contains(description, X)` | exact OR shape |
|---|---|---|---|
| No fulltext index at all | 200, `["A"]` | 200, `["B"]` | 200, isolates A/B correctly |
| Composite fulltext index `[title, description]` | 200, `["A"]` | 200, `["B"]` | 200, isolates A/B correctly |

Both configurations pass identically — `contains()` never required a
fulltext index on this self-hosted instance either (this matches
`q_contains`'s own docstring in `server/appwrite_store.py`, which had only
been verified against Appwrite Cloud until now). Separately, Appwrite only
permits **one** fulltext index per collection — production only ever
accepted `title_fulltext_idx`; `description_fulltext_idx` failed with
`"There is already a fulltext index in the collection"`. So PR #56's
two-index schema was never deployable as written, on top of being
unnecessary.

Collection was fully torn down after the test (deleting it removes its
attributes/indexes/documents together). No production data was touched.

**Fix:** commit `e336016` (PR #57) removes both index definitions from
`scripts/setup_appwrite.py`, keeps the unrelated `moderation_events.action`
enum fix from the same original migration, and adds a regression test
(`scripts/tests/test_setup_appwrite_readiness.py::NovelsKhongCanFulltextTest`)
locking in the revert.

## Finding 2 — the duplicate-advisor algorithm itself is correct

Rather than assume the missing index was *the* bug, the actual algorithm was
tested end to end against a real overlap: novel `nov_6b42f7954f914227`
("Conan Fanfic Luật Sư Ác Ma...", imported 2026-08-24 from Google Drive as
part of the 13-work Fanfic Staging import) has a description containing
`https://www.youtube.com/watch?v=XtJqhxbd1pY` — a real YouTube video ID.

Running `TrustedSourceService._phat_hien_novel_trung("XtJqhxbd1pY")` with
the current `main` code directly against production Appwrite (read-only,
via `find_novels`, no admin API / no HTTP layer involved) produced:

```
EXACT_OR_QUERY: q_or(contains(title, "XtJqhxbd1pY"), contains(description, "XtJqhxbd1pY"))
CANDIDATE_COUNT: 1  TOTAL_MATCHING: 1
  -> novel_id=nov_6b42f7954f914227, description_contains_video_id=true
RESULT_possible_duplicate_novel_id: nov_6b42f7954f914227   (matches expected)
```

The algorithm works correctly for this real case. A repo-wide search found
no evidence a live Trusted Source scan against this channel/video was ever
actually run before now — the "not firing" belief was never verified against
this specific real overlap; it appears to have been inferred from the same
wrong fulltext-index theory rather than observed directly.

**Conclusion: no active bug in the current duplicate-advisor logic.**

## Finding 3 — known fragility worth hardening anyway

The mechanism only works because these 13 novels' descriptions happen to
contain the raw source URL (a side effect of how the Drive import was
written, not a designed identity field), and because `find_novels(...,
limit=5)` — a hardcoded top-5 candidate window — happens not to be exceeded
today. Both are real, named risks for future imports/catalog growth:

- No structured source-identity field exists on `Novel` at all; detection
  depends entirely on incidental substring matches in free text.
- If 5+ novels ever contain the same video-ID substring, the true match
  could fall outside the candidate window and be silently missed.

See the follow-up hardening PR for the fix (raises the candidate window and
adds regression tests locking in: exact-match-beyond-old-top-5 is still
found, URL-form variants are still detected since the check is
substring-based, and title similarity alone never produces a false
positive).
