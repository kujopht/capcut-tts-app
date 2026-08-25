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

## Production schema cleanup (completed)

After PR #57 merged, the erroneous `title_fulltext_idx` was removed from
the live `novels` collection directly (schema-key operation):

- Pre-check: repo-wide grep confirmed no live code path uses `Query.search()`
  against `novels` — only `contains()`, which does not need it.
- Document count before: 18. Document count after: 18 (unchanged).
- Remaining indexes after cleanup: `owner_idx`, `state_idx`,
  `state_created_idx`, `novel_id_idx` (all `key` type, all `available`) —
  exactly matches the corrected `scripts/setup_appwrite.py`.
- `moderation_events.action` enum re-verified intact: 43 values, includes
  `trusted_source_channel_discovery`.
- No document writes occurred at any point in this schema cleanup.

## PR #58 — candidate-window hardening

Merged (commit range `39c9763`..`9c17f1e`, squashed into `main`). Raises
`_phat_hien_novel_trung`'s candidate window from 5 to 25 and adds 4
regression tests (see PR body / commit message for detail). Independently
reviewed twice — first pass found a docstring in one new test overclaimed
what it exercised (candidate selection vs. final match); fixed in a
follow-up commit before merge.

## Trusted Sources QA artifact cleanup (completed)

Inventoried and deleted all disposable Trusted Sources canary artifacts
from production, all confirmed QA-owned (creator/owner
`6a8db1d6c8c9ed444619`, the earlier temporary QA admin account) before
deletion:

| Collection | Records deleted | Verification |
|---|---|---|
| `trusted_sources` | 2 (Library of Congress, "Nghe Truyen Di Gioi (QA dup-check, do not import)") | both `created_by=6a8db1d6c8c9ed444619` |
| `video_imports` | 100 | 100% tied to the 2 QA `trusted_source_id`s above; none had `possible_duplicate_novel_id` set (confirms no accidental flagging against the 13 real novels occurred during QA scans) |
| `animation_series` | 2 (both `state=draft`) | both `owner_id=6a8db1d6c8c9ed444619` |
| `animation_episodes` | 1 (`state=draft`) | `owner_id=6a8db1d6c8c9ed444619`, tied to one of the 2 QA series above |

All 105 deletions returned `204`. Post-cleanup verification: all four
collections now show `total=0`. The 13 real Fanfic novels were read-only
inspected only (title/owner/state/tags), never written to.

**Incidental observations, left untouched (out of scope for tonight,
predate this work, no action taken):** the `novels` collection has 5
records beyond the 13 real published works — one draft duplicate of an
already-published work (`nov_aaa1dd7254e84d44`, same `work:CAT-db51180e7286`
tag as the published `nov_f9f2ce79889d42a3`, likely an import-retry
artifact from the earlier, already-completed Drive import task) and 4
unrelated "Audio Studio" drafts including one explicitly tagged
`qa-canary`/`test`. None of these are Trusted Sources artifacts; none were
touched.

## Production certification — BLOCKED on manual deploy

Both fixes are merged to `main`, but `fas-prod-api` on Render has
`autoDeploy: false` and no `RENDER_API_KEY`/deploy hook is available to
this session — deploying requires a manual Render dashboard action. Live
HTTP-level certification of the merged fix (via the real
`/api/admin/animation/sources/*` endpoints) could not be completed as a
result. What **was** proven, directly against real production Appwrite
data using the current `main` code (bypassing only the HTTP/admin-auth
layer): `_phat_hien_novel_trung` correctly detects the real known overlap
(see Finding 2 above). This is strong evidence the algorithm itself is
correct, but does not confirm the currently-deployed Render binary
contains PR #57/#58's code.

A fresh disposable QA account was registered for when live certification
becomes possible: user_id `6a8dd1115b1ef86a585a` (credentials saved
locally, never printed). It is **not yet** in `FAS_ADMIN_USER_IDS` — needs
the same manual add-env-var-and-redeploy cycle used for prior QA sessions.

**Manual action needed:** trigger a Render deploy of `main` for
`fas-prod-api` (picks up PR #57 + #58). While doing that, also add
`6a8dd1115b1ef86a585a` to `FAS_ADMIN_USER_IDS` so live certification can
run without waking anyone. After certification, remove that user_id again
per the established QA-access pattern.

## Verdict

Given live HTTP-level certification is outstanding, Trusted Sources is
reported as **FAIL (blocked on deploy, not a code defect)** rather than an
unconditional PASS — consistent with "do not declare PASS from mocks alone
when a production behavior was the bug": here the situation is the
mirror image (direct-against-production-data evidence is strong, but the
live deployed binary is unverified), and the same caution applies. The
Universal Story Scraper work was correspondingly **not started** tonight,
per the explicit "only if Trusted Sources is fully PASS" gate.
