# Fanfic AI Engineering Router V2

Project-local policy for which **provider/model/effort/subagent** handles
which kind of engineering work in this repo — not a product feature,
doesn't touch application behavior. Goal: speed, rate-limit efficiency,
token/context efficiency, independent cross-model review, and routing the
*right* amount of capability at a task instead of defaulting to the most
expensive model for everything.

**V2 adds a second and third compute pool** (Google Antigravity/Gemini via
the user's existing Google AI Pro subscription, and continues treating
Codex as a separate cross-model worker) **on top of** the V1 Claude-tier
policy below, which is unchanged and still the default path. V2 does not
replace V1 — it decides *when* to route ordinary work to a different
already-paid-for quota pool instead of Claude's, and *when not to*.

## Environment inventory (2026-08-27)

| | |
|---|---|
| Claude Code version | 2.1.231 |
| Claude auth mode | Claude.ai account/subscription (not a raw API key) |
| Claude usage/quota introspection | **Not exposed via CLI** — `claude --help` has no usage/status/quota subcommand. Claude quota pressure must be inferred from observed rate-limit/slowdown behavior in-session, not queried directly. Real limitation, recorded rather than worked around. |
| Codex CLI | Installed (bundled with the Codex desktop app), `codex-cli 0.149.0-alpha.4.1`, authenticated via ChatGPT OAuth login, default model `gpt-5.6-sol` at high reasoning effort. Binary not on PATH in every shell — full path `C:\Users\<user>\AppData\Local\OpenAI\Codex\bin\<hash>\codex.exe`; resolve dynamically (`where codex` first, fall back to the AppData path) rather than hardcoding the hash segment, which changes on update. |
| Codex headless mode | `codex exec [PROMPT]` — non-interactive, supports `-m/--model`, `-c model_reasoning_effort=...`, `-c sandbox_permissions=[...]`, `codex exec review` for review-only mode. |
| Google Antigravity CLI | Installed 2026-08-27 from official `antigravity.google` source (SHA512-verified installer), `agy.exe` v1.1.22, authenticated via Google OAuth (user's existing Google AI Pro account), binary at `%LOCALAPPDATA%\agy\bin\agy.exe`. |
| Antigravity headless mode | `agy --print "<prompt>" --model=<id> --output-format text\|json\|stream-json`; also `--sandbox`, `--dangerously-skip-permissions`, `--mode accept-edits\|plan`, `--add-dir` for explicit workspace scoping. |
| opencode / opensquilla | Not installed |
| Prior `.claude/agents/` or routing policy | V1 (below), built earlier the same day |

Model names below use Claude Code's current aliases (`sonnet`, `opus`,
`haiku`, `fable`) rather than hardcoded version-pinned IDs, per the
explicit instruction not to hardcode obsolete IDs — Claude Code resolves
the alias to whatever the current release is.

## V2 compute pool inventory (real, queried 2026-08-27)

Actual account state, not assumed model lists. Antigravity quota was read
via `agy --print "/usage"` immediately after OAuth login; two **separate**
quota buckets exist inside one Google AI Pro account — routing pressure on
one does not affect the other.

| Provider | Model | Quota pool | Remaining (at inventory time) | Latency class | Reasoning class | Coding role | Review role |
|---|---|---|---|---|---|---|---|
| Claude | haiku | Claude subscription (not separately observable) | Not exposed | Fast | Low | No (read-only tier) | No |
| Claude | sonnet | Claude subscription | Not exposed | Medium | Medium | **Yes — default integrator** | Secondary |
| Claude | opus | Claude subscription | Not exposed | Slow | High | Plan/high-risk only | **Yes — primary high-risk reviewer** |
| Claude | fable | Claude subscription | Not exposed | Slowest | Highest | Extreme long-horizon only | No |
| Antigravity | `gemini-3.7-flash-{high,medium,low}` | Google AI Pro — **Gemini Models** bucket | 99% weekly, 99% 5-hour (resets 2026-09-03 / same-day) | Fast | Low–Medium (by effort suffix) | **Yes — bulk/mechanical** | Secondary |
| Antigravity | `gemini-3.6-flash-*`, `gemini-3.5-flash-*` | Gemini Models bucket | same pool as above | Fast | Low–Medium | Overflow when 3.7 unavailable | No |
| Antigravity | `gemini-3.1-pro-{high,low}` | Gemini Models bucket | same pool | Medium | High | Repo-wide/architecture exploration | Secondary |
| Antigravity | `claude-sonnet-4-6` (thinking) | Google AI Pro — **Claude and GPT models** bucket | 100% weekly, 100% 5-hour | Medium | Medium | **Yes — overflow compute pool for Sonnet-tier work, not a new capability** | Secondary |
| Antigravity | `claude-opus-4-6-thinking` | Claude and GPT models bucket | same pool | Slow | High | Opus-tier overflow only | Secondary |
| Antigravity | `gpt-oss-120b-medium` | Claude and GPT models bucket | same pool | Medium | Medium | No (unproven) | **Third-opinion/challenger only, benchmark-gated** |
| Codex | `gpt-5.6-sol` (default, high effort) | ChatGPT/Codex subscription (not separately observable via CLI) | Not exposed | Medium | High | Independent implementation | **Yes — primary cross-family reviewer** |

**Two real constraints this table exposes, not assumptions:**
1. Claude and Codex both have **no CLI-observable quota** — the "quota
   balancer" (Phase 15 below) can check Antigravity precisely but can only
   *infer* Claude/Codex pressure from in-session rate-limit responses.
2. `claude-sonnet-4-6`/`claude-opus-4-6-thinking` via Antigravity draw from
   the **same** "Claude and GPT models" Google-side bucket as GPT-OSS —
   routing routine work to "Google Sonnet" to relieve *native* Claude
   pressure works, but routing heavily to *both* Google-Sonnet and
   GPT-OSS at once competes for the same Google-side bucket, not two
   independent ones.

## Tiers

### Tier 0 — cheap exploration (Haiku, low/medium effort)

Grep/search, repository archaeology, file discovery, config inventory,
log/test-output summarization, doc lookup, dependency inventory,
straightforward read-only verification. **Never** use Opus/Fable merely
to search files — see the benchmark below for why that's not just a
guideline, it's measurably wasteful.

### Tier 1 — default engineering (Sonnet, medium effort)

Normal feature implementation, frontend CSS/UI, CRUD, API wiring, routine
bug fixes, unit tests, refactors with a clear specification, docs, simple
CI fixes. Sonnet should do the *majority* of implementation work in this
repo — it is the default, not the fallback.

### Tier 2 — hard engineering (Opus, high/xhigh effort)

Escalate when one or more apply: auth/authorization, Appwrite schema/data
migration, security-sensitive code, a production incident, concurrency/
race conditions, distributed-systems reasoning, destructive operations,
difficult root-cause debugging, architecture changes, a large
cross-cutting refactor, Sonnet has failed twice on the same *verified*
issue, or the change is ambiguous with real regression risk. Opus should
normally **plan/review** difficult work; Sonnet can still execute the
straightforward portions once the hard part is decided.

### Tier 3 — long-horizon critical (Fable, high effort)

Only when justified by: a genuinely large multi-hour autonomous task,
multiple tightly-coupled systems, long-horizon planning+execution,
exceptionally dense context, an exceptionally critical result, or Opus
has genuinely failed to reach the needed quality bar. **Not** for grep,
CSS tweaks, docs, ordinary testing, routine bug fixes, or routine PR
review — Fable is exceptional escalation, not a default.

## Custom subagents (`.claude/agents/`)

| Agent | Model | Effort | Tools | Purpose |
|---|---|---|---|---|
| `explorer` | haiku | low | Read, Grep, Glob, Bash, WebFetch | Search/archaeology/log inspection — read-only |
| `test-analyst` | haiku | low | Read, Grep, Glob, Bash | Diagnose a failing test's root cause — reports a fix, doesn't apply one |
| `builder` | sonnet | medium | Read, Grep, Glob, Edit, Write, Bash | Routine isolated implementation |
| `frontend-builder` | sonnet | medium | Read, Grep, Glob, Edit, Write, Bash | UI/CSS/responsive work in `web/src`, same tier as `builder` |
| `code-reviewer` | opus | high | Read, Grep, Glob, Bash | High-signal review of risky diffs — read-only |
| `incident-architect` | opus | xhigh | Read, Grep, Glob, Bash, WebFetch, WebSearch | Production incidents, architecture, concurrency, auth — plan-oriented, read-only |
| `long-horizon-lead` | fable | high | Read, Grep, Glob, Edit, Write, Bash, WebFetch, WebSearch | Exceptional mega-project escalation only |

None of the read-only agents (`explorer`, `test-analyst`, `code-reviewer`,
`incident-architect`) carry `Edit`/`Write` in their tool list — that's the
permission boundary, not a convention to remember separately.
`explorer`/`test-analyst`/`code-reviewer` carry `maxTurns` caps (15/15/20)
so a cheap lookup can't silently wander into an expensive one;
`incident-architect` gets a higher cap (40) because real diagnosis
legitimately takes longer; `long-horizon-lead` intentionally has none —
capping turns would defeat its purpose.

**`isolation: worktree` was deliberately left unset** in every agent's
frontmatter, including the two writers (`builder`, `frontend-builder`).
Worktree isolation has real setup cost (the Agent tool's own docs call it
"EXPENSIVE") and is only worth paying when multiple writers genuinely run
in parallel on the same files. A static agent definition can't know that
in advance — set `isolation: "worktree"` as a **per-call** override when
actually dispatching parallel writers, not as a blanket property of the
agent.

## V2 task taxonomy

Classify substantial work along these axes before picking a worker —
cheap, done mentally in a sentence, not a formal step:

- **Complexity:** LOW / MEDIUM / HIGH / EXTREME
- **Risk:** LOW / MEDIUM / HIGH
- **Breadth:** LOCAL / MODULE / REPO_WIDE / MULTI_SYSTEM
- **Work type:** SEARCH / ANALYSIS / IMPLEMENTATION / TESTING / REVIEW /
  UI / DOCUMENTATION / INCIDENT / ARCHITECTURE / SECURITY / MIGRATION /
  PERFORMANCE / RESEARCH
- **Parallelizable:** YES / NO / PARTIAL
- **Critical path:** YES / NO

This feeds both the complexity/risk matrix (below, unchanged from V1) and
the per-model specialization table (next section) — breadth and
parallelizability are the two axes V1 didn't need (single-provider) but
V2 does, since they determine whether a task is worth sending to a
*different quota pool* at all versus just staying on the critical-path
Sonnet thread.

## V2 per-model specialization

Grounded in the real inventory above, not capability alone — see the
quota-aware routing rule immediately after this table for how pool
pressure shifts these defaults.

| Worker | Best for | Avoid |
|---|---|---|
| **Claude Haiku** | grep/search, repo archaeology, log analysis, file discovery, test-failure classification, concise read-only summaries | Never for implementation |
| **Antigravity Gemini Flash** (3.7 first, 3.6/3.5 as overflow) | repetitive edits, fixture/unit-test generation, simple frontend/CSS, docs, data transforms, parsing rules, mechanical refactors, bulk low-risk implementation, independent read-only repo analysis | Anything needing cross-file architectural judgment |
| **Claude Sonnet (native)** | primary integrator/default engineer — feature implementation, cross-file logic, API integration, backend/frontend coordination, ordinary debugging, merging other agents' work | Pure mechanical bulk work Flash/Haiku can do cheaper |
| **Antigravity Claude Sonnet** (`claude-sonnet-4-6`) | a **separate compute pool** for isolated Sonnet-level implementation, a genuinely parallel feature branch, or overflow when native Claude quota is under pressure | Running the *same routine task* as native Sonnet redundantly — pick one |
| **Antigravity Gemini Pro** (3.1) | repo-wide understanding, large-context reasoning, architecture exploration, large-refactor planning, cross-module dependency analysis, alternative plan generation | Treating it as an automatic Opus replacement without the benchmark evidence in Phase 13/14 below |
| **Codex** | independent implementation, test/fix loops, isolated refactors, regression generation, code review, alternative diagnosis — **especially valuable as cross-family review after Claude/Gemini implementation** | Sending it plaintext secrets/production credentials — same data-minimization rule as V1 |
| **Claude Opus (native)** | auth/authorization, security, Appwrite/schema migration, concurrency/races, distributed systems, production incidents, high-blast-radius architecture decisions, difficult bugs after lower tiers fail — **plan/root-cause/final-review**, not mechanical edits | Mechanical edits Sonnet can do |
| **Antigravity Claude Opus** (`claude-opus-4-6-thinking`) | Google-quota overflow for Opus-level work when native Opus should be conserved | Routine duplication of native Opus analysis |
| **GPT-OSS-120B** | benchmark as third-opinion reasoning, alternative diagnosis, algorithm critique, plan challenger, docs/spec critic | Default implementation worker until benchmarks justify it (none do yet — see Phase 13) |
| **Fable** | only if genuinely available and only for long-horizon multi-hour, tightly-coupled multi-system work, or where Opus has demonstrably failed | Routine coding, ever |

## V2 dynamic quota-aware routing

The router considers remaining quota, not capability alone:

```
best_worker =
    sufficient_capability
    + available_quota
    + low_expected_latency
    + isolation_fit
    + critical_path_priority
```

Concrete rules, in priority order:

1. **If Claude quota pressure is inferred HIGH** (rate-limit/slowdown
   observed this session) **and Google quota is healthy** (per the real
   `/usage` buckets above): route ordinary implementation to Antigravity
   Gemini Flash or Antigravity Sonnet instead of native Sonnet.
2. **If the Gemini Models bucket is under pressure**: prefer native
   Sonnet or Codex over further Antigravity Flash/Pro dispatches.
3. **If Codex allowance appears healthy** (no recent rate-limit/failure):
   use it for independent implementation or review rather than spinning
   up a second Claude/Antigravity path for the same signal.
4. **Always preserve some strong-model quota for emergencies** — do not
   drain the Opus pool (native or Antigravity) on routine tasks early in
   a session just because it's available.
5. Since Claude/Codex quota isn't CLI-observable (see inventory above),
   "pressure" for those two is inferred from actual rate-limit/slowdown
   responses encountered during the session, checked at session start and
   major phase boundaries (Phase 15), not polled continuously.

## Context cost control

- Unrelated task → new/clean context, don't keep piling unrelated work
  into one long-running conversation.
- Compact long sessions at logical milestones, not mid-task.
- Verbose repository exploration belongs in a subagent (`explorer`), not
  inline in the main conversation — a subagent's raw tool output never
  reaches the parent context, only its final structured summary does.
- Subagent final output should be structured (`STATUS`/`FINDINGS`/
  `FILES`/`CHANGES`/`TESTS`/`RISKS`/`NEXT ACTION` — see each agent
  definition), not a raw log dump.
- Read targeted line ranges from large files rather than the whole file
  when only a section is relevant.
- Don't run five agents over the same files — if two tasks would touch
  the same file, that's one task, not a parallel-dispatch opportunity.
- **V2 concurrency starting point:** 1 coordinator + up to 3 concurrent
  WRITE workers (any provider) + up to 2 READ-ONLY research/analysis
  workers. Not a hard cap forever — Phase 13's benchmark is where 1 vs 2
  vs 3 concurrent writers gets actually measured on this machine; treat
  "3" as the conservative starting default until real timing data says
  otherwise. If wall-clock gets *worse* with more concurrent writers
  (CPU/disk contention, duplicate dependency installs, test-DB conflicts),
  reduce concurrency — more workers is not automatically faster.
- **V2 context packet** for every external/parallel dispatch (Claude
  subagent, Codex, or Antigravity alike) — a minimal, self-contained
  packet instead of the whole conversation history:

  ```
  TASK
  GOAL
  RELEVANT_FILES
  INTERFACES
  CONSTRAINTS
  EXPECTED_TESTS
  DO_NOT_TOUCH
  OUTPUT_SCHEMA
  ```

  Use a Haiku/`explorer` pass to *build* this packet first when the
  relevant files aren't already known — that's still a Tier-0 search
  task, not a reason to skip packet minimization.

## Test execution cost control

```
edit -> focused tests -> focused lint/typecheck if relevant -> continue
edits -> full suite ONCE at a meaningful gate -> review -> CI
```

Do not run the entire 2800+-test backend suite after every small edit.
Full-suite triggers: PR-ready state, a risky shared-core modification,
schema/auth/security changes, the final merge gate. This was already the
de facto practice in every PR this session (focused test files during
development, full suite immediately before opening each PR) — this
section makes it explicit policy rather than an unwritten habit.

## Codex as a cross-model worker

Codex CLI is installed and authenticated (ChatGPT OAuth), but it is a
**separate tool**, not a native Claude subagent — there is no unified
in-process handoff; delegating to it means shelling out to the `codex`
CLI as a distinct process, in a worktree, and reading its output back.

**Best uses:** independent code review (a genuinely different model
family reviewing a diff Claude wrote catches different classes of
mistakes than Claude reviewing its own work), isolated test generation,
a well-specified refactor, an alternative bug diagnosis on a stuck
problem, or an independent implementation attempt in a worktree to
compare against Claude's.

**Avoid sending Codex:** plaintext secrets, production credentials, or
files beyond what the specific task needs — the same data-minimization
principle already applied to any external tool call in this repo.

**Preferred workflow for significant code:**

```
Sonnet implementation
        |
Opus OR Codex independent review
        |
fix findings
        |
tests/CI
```

**For expensive, high-risk work:**

```
Opus plan
   |
Sonnet implementation workers
   |
Codex independent review
   |
Opus final risk review ONLY if the Codex review surfaced something serious
```

**Do NOT** routinely run Fable + Opus + Codex all on the same task — that
burns quota across three expensive paths for one answer. Pick the
cheapest path that gives real independent signal.

### V2 cross-model review policy

Prefer genuine model-family diversity between implementer and reviewer —
same-family self-review catches fewer classes of mistake than a
different model reviewing the same diff:

```
Claude implementation      -> Codex review
Antigravity/Gemini impl.   -> Codex or native Claude review
Codex implementation       -> native Sonnet or Antigravity/Gemini review
```

For high-risk work, the V1 chain gains one more optional branch:

```
Opus plan
   |
Sonnet OR Antigravity implementation workers
   |
Codex independent review
   |
Opus final risk review ONLY if the Codex review surfaced something serious
```

**Do not** use three or more frontier reviewers (e.g. Opus + Codex +
Antigravity-Opus) on an ordinary diff — that's the same quota-burning
mistake as Fable+Opus+Codex, just with a fourth provider added. One
genuinely independent reviewer is normally sufficient signal.

**Model future-proofing:** Codex's model is read from its own
`~/.codex/config.toml` (`model = "gpt-5.6-sol"`, `model_reasoning_effort =
"high"` as of this writing) rather than hardcoded anywhere in this repo —
if a wrapper script is ever built around the `codex` CLI, it should read
that config rather than embedding a model string, since Codex's own
available models change on OpenAI's schedule, independent of this repo.

## Antigravity as a cross-model worker (headless)

Like Codex, Antigravity is a **separate process/compute pool**, not a
native Claude subagent — dispatching to it means shelling out to `agy.exe`
in a worktree and reading structured output back, same integration shape
as Codex, different provider.

**Invocation pattern:**

```
agy --model=<id> --print "<task packet>" --add-dir <worktree-path> \
    --output-format json --print-timeout 5m
```

Always pass an explicit `--model` — do not depend on one global default,
since the right model depends on the task (Flash for mechanical work, Pro
for repo-wide reasoning, Google-Sonnet/Opus for overflow — see the
specialization table above). Prefer `--output-format json` for
machine-parseable structured results; fall back to `text` only for a
human-in-the-loop check.

**Every external writer (Antigravity or Codex) gets, no exceptions:**

- an isolated git worktree (`isolation: "worktree"` equivalent — a real
  `git worktree add` for CLI-shelled workers, since they're not the
  `Agent` tool and don't get that isolation for free)
- an explicit `--add-dir`/cwd scoped to only what the task needs
- a self-contained task packet (see "Context packets" below) — never the
  full conversation history
- a timeout (`--print-timeout`)
- bounded scope stated in the packet's `DO_NOT_TOUCH` field
- **no production credentials** — same data-minimization rule as Codex
- **never auto-merge, never auto-deploy**
- a required structured return shape:

```
STATUS
FINDINGS
FILES_CHANGED
TESTS
RISKS
NEXT_ACTION
```

Do not dump a worker's full transcript into the coordinator's context —
only the structured block above crosses back.

## Critical-path scheduler

For every large task: decompose into a dependency DAG, identify the
critical path, start independent branches immediately, reserve the
strongest *suitable* worker for the critical path, and run mechanical/
bulk work concurrently rather than serially. Do not wait for one branch
to finish before starting genuinely independent work.

Representative shape:

```
Sonnet (critical path):  core API contract
   parallel -> Antigravity Gemini Flash:  tests + fixtures
   parallel -> Codex:                     frontend implementation
   parallel -> Haiku:                     existing code audit
                    |
                 integrate
```

## Speculative parallelism (duplicate solvers)

Reserved for genuinely high-expected-value uncertainty, not normal
implementation: an unknown race condition, an architecture with two
credible approaches, or a production incident with uncertain root cause.
In those cases only, run two independent hypotheses concurrently (e.g.
Opus hypothesis A + Codex/Gemini hypothesis B) and have the coordinator
compare evidence — this is the same pattern as the V1 benchmark's Sonnet-
vs-Opus race-condition comparison, generalized to also allow a
cross-provider second opinion. **Do not** use duplicate solvers for
ordinary implementation — that's quota spent for no real signal.

## Complexity/risk classification

Before substantial work, classify internally:

| | Complexity: LOW | MEDIUM | HIGH | EXTREME |
|---|---|---|---|---|
| **Risk: LOW/MEDIUM** | Haiku/Sonnet | Sonnet | Opus plan/review + Sonnet execution | Fable lead + cheaper workers for bulk execution |
| **Risk: HIGH** | Opus plan/review + Sonnet execution | Opus plan/review + Sonnet execution | Opus plan/review + Sonnet execution | Fable lead + cheaper workers for bulk execution |

Do not escalate solely because a task is long in *token count* — a long
but mechanical task (e.g. applying the same rename across 40 files) stays
Sonnet-tier; length alone isn't complexity or risk.

## Escalation / de-escalation

- **Haiku → Sonnet**: when reasoning/editing exceeds straightforward
  lookup-and-report work.
- **Sonnet → Opus**: after *verified* difficulty (not just "this looks
  hard"), real architectural ambiguity, or genuine high regression risk.
- **Opus → Fable**: only when long-horizon complexity or a demonstrated
  Opus quality shortfall justifies it.
- **De-escalate immediately after the hard decision is made** — e.g. Opus
  identifies a root cause and a concrete implementation plan, then hands
  the mechanical edits/tests to Sonnet/Haiku rather than staying engaged
  for work that no longer needs its tier. Don't keep an expensive model
  active just because it was useful earlier in the task.
- **V2 cross-provider escalation:** SEARCH always stays on Haiku, never on
  a Flash/Sonnet-tier worker regardless of provider. ROUTINE
  IMPLEMENTATION starts on the cheapest sufficient worker (Flash/Sonnet/
  Codex, per the quota-aware routing rule above) — if it fails once from a
  genuine misunderstanding, retry once with a better task packet before
  escalating a tier; only escalate (e.g. Gemini Pro or Sonnet → Opus) after
  a *second*, verified-difficulty failure. Once the hard reasoning is
  resolved, de-escalate the remaining mechanical execution back down —
  same principle as the paragraph above, now applying across providers
  too, not just across Claude tiers.

## Benchmark (2026-08-27)

A small, real benchmark — not the full 6-10 task matrix, deliberately
kept small per the explicit instruction not to burn quota just to
benchmark. Three representative task types, run for real via the `Agent`
tool with explicit `model` overrides, timings and outputs as actually
returned (not estimated):

| Task | Model | Time | Tool calls | Tokens | Result |
|---|---|---|---|---|---|
| Repo search: find a specific test file/function | Haiku | 12.5s | 3 | 26.7k | **Correct.** Exact file, function, line. |
| Docs summary: 5 bullets from a CLAUDE.md section | Haiku | 18.2s | 1 | 25.2k | **Correct**, format instruction (exactly 5 one-sentence bullets) followed precisely. |
| Docs summary: same task | Sonnet | 9.2s | 2 | 32.1k | Correct content, but merged two distinct facts into one bullet — a minor format-instruction slip a "better" model still made on a task simple enough that it didn't need extra care. |
| Hard diagnosis: explain a real historical race condition (the `test_translation_job_recovery.py` flake fixed earlier this session) | Sonnet | 58.9s | 1 | 40.7k | **Correct at the qualitative level** — identified the real race (unblocked thread vs. no re-check between passes) matching the actual fix already shipped. |
| Same hard diagnosis | Opus | 53.0s | 7 | 40.5k | **More precise and more actionable** — additionally pinpointed the exact missing synchronization (the main thread never joins `worker_a`'s daemon thread) and, critically, **found a real latent bug the shipped fix hadn't caught**: the test's `assertIn(so_lan_goi, (10, 12))` range check misses the legitimately-reachable intermediate value `11`. This finding was verified and fixed in this same session (see `test_translation_job_recovery.py`'s updated range-check assertion) as a direct result of running this benchmark. |

**What this confirms:** Haiku is fully sufficient for search/lookup/
summary tasks — using Sonnet there cost more tokens for a *worse* format
result in this sample, not a better one. For a genuinely hard diagnostic
task, Opus produced a measurably more complete and more useful answer
than Sonnet at comparable latency and token cost, including catching a
real bug Sonnet's otherwise-correct answer missed — this is real evidence
for the Tier 2 escalation rule, not just a plausible-sounding policy.

This sample is illustrative, not exhaustive — it does not cover CSS bugs,
API bugs, medium refactors, or PR review as distinct task types, and
Fable was not benchmarked at all (no task in this session justified
Tier 3). Extend this table opportunistically when a task naturally
produces a comparable before/after, rather than running a dedicated
benchmark pass purely to fill in the matrix.

## V2 cross-provider benchmark (2026-08-27)

Same principle as above — a small representative slice, not the full 9×N
matrix, run for real (`agy --print`/`codex exec` shelled directly, timed
with wall-clock `date` stamps; the mechanical-edit task ran in a disposable
git worktree, never merged, then deleted). No quota was intentionally
burned beyond these five real calls.

| Task | Worker | Provider/quota pool | Time | Result |
|---|---|---|---|---|
| A. Repo search (where/how is `content_hash` computed) | Haiku | Claude subscription | not precisely timed (Claude has no CLI timer — see inventory note) | **Correct.** Exact file/function/algorithm. |
| A. Same question | `gemini-3.7-flash-medium` | Antigravity — Gemini Models bucket | ~single turn, sub-30s by observation | **Correct**, identical answer to Haiku, plus direct file/line links. |
| G. Hard diagnosis (same historical race condition as the V1 Sonnet/Opus benchmark row) | `gemini-3.1-pro-high` | Antigravity — Gemini Models bucket | 52s | **Matched Opus's precision**, not just Sonnet's — independently found the exact missing `join()` on `worker_a` and the same `so_lan_goi == 11` edge case Opus's pass in V1 caught (and Sonnet's didn't). |
| G. Same question | Codex (`gpt-5.6-sol`, high effort) | ChatGPT/Codex subscription | 56s | **Also matched Opus's precision** — same missing-`join()` root cause, same 11-edge-case, independently worded. |
| C. Mechanical implementation: add a unit test for `content_hash()` (search+test-gen, no production code touched) | `gemini-3.7-flash-medium`, `--mode accept-edits` | Antigravity — Gemini Models bucket | 87s (after one retry — see finding below) | **Correct on the first *successful* attempt.** Found the right existing test class, wrote a properly scoped test (format/determinism/sensitivity), ran pytest itself (19 passed), independently re-verified by reading the diff and re-running the test myself — clean, one file touched, zero rework needed. |
| H. Independent review of the diff above | Codex (`codex exec review --uncommitted`) | ChatGPT/Codex subscription | 48s | **Confirmed correct**, no issues raised. Codex's own first pytest attempt hit an unrelated tempdir/environment quirk in the throwaway worktree, self-recovered via `python -m unittest`, still verified 19/19 passing — an environment idiosyncrasy, not a review-quality problem. |

**Two real operational findings from this run (not policy guesses):**

1. **Antigravity headless mode fails closed on shell commands by default.**
   `--mode accept-edits` auto-approves file writes but *not* running
   pytest — the first attempt at the mechanical-edit task was auto-denied
   with a clear message rather than hanging or silently skipping. Retried
   successfully with `--dangerously-skip-permissions`, which is acceptable
   for a scoped, disposable-worktree task with no production credentials
   present, matching the same threat model already accepted for the
   `builder`/`frontend-builder` Claude subagents' unprompted `Bash` access
   in this repo — but should **not** be the default for untrusted or
   wide-scope Antigravity dispatches. Add this as the documented default
   invocation for bounded, worktree-isolated mechanical tasks; leave the
   safer prompting default in place for anything broader.
2. **`codex exec review --diff` doesn't exist** — the real flag is
   `--uncommitted` (or `--commit`/`--base`, same shape as the `codex
   review` limitation already recorded in V1's Lessons section). Second
   CLI-flag surprise from Codex this project; worth a standing reminder to
   `--help` a subcommand before assuming its flag shape carries over from
   memory of a similar tool.

## V2 measured speed target

Per the explicit instruction not to claim theoretical speedups: this is
what was actually measured, not modeled.

**The one genuine apples-to-apples comparison available**: task G (hard
diagnosis of the real historical race condition) was independently
answered by four workers across two sessions — native Sonnet (58.9s, V1),
native Opus (53.0s, V1), Antigravity Gemini Pro (52s, V2), Codex (56s,
V2). Run **serially** (as V1's two calls and V2's two calls were each
actually executed), that's 219.9s total for four independent opinions. Run
**in parallel across the four now-available quota pools** — V2's actual
new capability — wall-clock is bounded by the slowest single worker:
`max(58.9, 53.0, 52, 56) = 58.9s`. **≈3.7x** for getting four independent
opinions in the time one used to take. This is a real, measured number for
this specific task, not a general claim.

**What was *not* re-measured, honestly:** a full OLD (undifferentiated
single-Sonnet) vs. V1 vs. V2 workflow re-run on identical multi-step work,
purely to produce a headline speedup number — doing that would mean
re-running real implementation work three times solely for benchmark
purposes, which the "do not intentionally burn quota" instruction argues
against. The mechanical-edit-then-review pipeline (tasks C→H, 87s + 48s =
135s) is a genuinely dependent chain (review needs the diff), so it
doesn't parallelize — but it demonstrates V2's *actual* benefit for that
shape of work: **135s of real implementation+review happened on
Antigravity+Codex quota, consuming zero native Claude quota**, which is
capacity added, not latency removed. That is the honest characterization
of what V2 provides on non-parallelizable work: quota substitution, not
speed.

## V2 calibration (evidence, not the original proposal)

Per the explicit instruction not to preserve the proposed routing if
results contradict it — what this small sample actually supports:

- **Search stays on Haiku or Antigravity Flash interchangeably** — both
  produced the identical correct answer. No evidence either is faster or
  more reliable than the other at this task size; route by whichever
  pool has more quota headroom at the time (Phase 4's rule), not by a
  fixed preference.
- **For hard diagnosis specifically, Gemini Pro and Codex both reached
  Opus-level precision on this task**, at ~53-56s (comparable to Opus's
  53s from the V1 table) but drawing from entirely different quota pools
  than native Claude. This is real evidence for Phase 4's rule 1
  ("route ordinary-to-hard implementation to Antigravity/Codex when
  Claude quota pressure is high") extending usefully to *hard diagnosis*
  too, not just routine implementation — **with the caveat that this is
  one data point on one known bug**, not a general claim that Gemini
  Pro/Codex always match Opus. Needs more samples before promoting this
  from "promising" to "policy."
- **Antigravity Flash's mechanical/test-generation specialization holds**
  — correct, clean, self-verified, zero rework on the one real task
  tried, exactly the role Phase 3 predicted for it.
- **Codex's cross-family review role holds** — caught nothing wrong
  (correctly, since there was nothing wrong), which is itself a useful
  negative-control data point: it didn't hallucinate a false finding
  under review pressure.
- **GPT-OSS-120B was not benchmarked this round** — no task in this small
  slice justified spending on a third-opinion challenger call. Still
  correctly un-promoted to default-worker status per Phase 3's original
  caution.
- **Concurrency (1 vs 2 vs 3 writers) was not load-tested this round** —
  all five benchmark calls ran sequentially for clean timing attribution,
  not to measure contention. The 1-coordinator/3-writer/2-reader starting
  point in the Context cost control section above remains a conservative
  default, not yet empirically tuned on this machine.

## V2 quota balancer

`scripts/ai_router_quota_check.py` — a tiny, dependency-free script, run
manually at the start of a large session or a major phase boundary (or
when a provider actually rejects a call due to quota), **not polled
continuously**. Real, current output (2026-08-27, after the benchmark
above):

```json
{
  "antigravity": {
    "usage_raw": "Gemini Models: 98% weekly / 97% five-hour remaining;
                   Claude and GPT models: 100% / 100% remaining",
    "paid_overage_risk_zero": true
  },
  "codex": { "trang_thai_dang_nhap": "Logged in using ChatGPT" },
  "claude": { "note": "no CLI-observable quota — infer from in-session rate-limit responses" }
}
```

`paid_overage_risk_zero: true` is read directly from `agy --print
"/credits"`'s real "Remaining credits: 0" line — confirming zero paid
Google AI credits are available to spend even if `useG1Credits` were ever
toggled on, which combined with its documented `false` default is real,
verified evidence (not just a config default trusted on faith) that this
setup cannot silently incur Google AI spend.

**What this script can and cannot tell you, honestly:** Antigravity's two
quota buckets are precisely observable. Codex exposes no usage/quota
command at all — login status is the only real signal. Claude exposes
nothing via CLI — quota pressure must be inferred from actual rate-limit
or slowdown responses encountered during the session. The router's
Phase 4 quota-aware rules already account for this asymmetry (rule 5).

## Routing telemetry

`scripts/ai_router_telemetry.py` — a tiny, dependency-free append-only
JSONL logger (`.claude/router-telemetry.jsonl`, gitignored). Records only
non-sensitive metadata: timestamp, task category, model/tier, **provider
(V2: `CLAUDE`/`CODEX`/`ANTIGRAVITY`, defaults to `CLAUDE` for backward
compatibility with every V1 record already logged)**, elapsed seconds,
success/failure, whether tests were run and passed, whether an escalation
occurred and why. **Never logs prompts or file contents.** Not wired into
automatic invocation on every agent call — it's a helper any future
session can call manually (or a hook can call, if one is added later)
when it wants to record a data point; not a background service, not a
database. `tom_tat()`/`summary` now breaks results down both by tier and
by provider.

## Lessons from first real use (2026-08-27, product phase 2)

Real engineering work — not a benchmark pass — surfaced two genuine
process issues worth recording. Neither changes the tier/model policy
itself (Haiku/Sonnet/Opus routing all performed as expected, see the
burn-in report), both are about *how agents were run*, not *which model*.

**Project-local `.claude/agents/` definitions did not load in the
running session.** All 7 custom subagents (`explorer`, `builder`, etc.)
were unavailable via the `Agent` tool's `subagent_type` in the same
session that created them — Claude Code apparently reads
`.claude/agents/` at session start, not on a live filesystem watch.
Worked around by using the built-in `Explore`/`general-purpose` agent
types with an explicit `model` override, which achieves the same tier
routing without the named-agent convenience (system-prompt text, tool
restrictions, `maxTurns` caps — none of that applied without the real
named agent). Unverified whether a fresh session actually picks the
custom agents up; that's the natural next check, not done here since it
requires restarting the session that would be doing the checking.

**Concurrent agents sharing one working tree with the orchestrating
session's own `git checkout`/`git stash` is a real, if recoverable,
hazard.** With three Sonnet builders running in parallel and the parent
session simultaneously creating/switching/rebasing feature branches for
already-finished work, one agent's in-progress edits appeared to
"disappear" mid-task (later traced to the parent session switching the
shared working directory to a branch that didn't have that agent's
target file yet) and cost real time to diagnose afterward. Nothing was
actually lost — the agent had written to the same on-disk path the
whole time, and `git checkout` doesn't touch untracked files unless
they'd be overwritten by tracked content, so backing the file up and
re-checking out cleanly recovered it — but it was a genuine "what
happened to my work" scare, not a benchmark nitpick. **Recommendation
for next time:** when the parent session needs to keep branching/
switching while writer agents are still active, either (a) hold off on
`git checkout`/`git stash` until those agents report done, or (b) pass
`isolation: "worktree"` for those specific dispatches so each agent gets
its own working directory and the parent session's git operations can't
cross paths with it. The router policy above deliberately leaves
`isolation` unset by default (real setup cost, only worth it for
genuinely parallel writers) — this experience adds a second trigger for
turning it on: not just "multiple agents writing the same files," but
"the orchestrator itself needs to keep moving branches while agents are
still working."

**One CLI limitation found, not a bug:** `codex review` does not accept
a custom prompt combined with `--commit`/`--base` (they're mutually
exclusive modes) — use `--commit <sha>` alone for a full default review,
or drop the target flag and let it review the current working-tree diff
with custom instructions. Worked around by using `--commit` alone; still
produced a genuinely valuable independent review (see the burn-in
report) despite not being able to steer it toward one specific concern.

## Persistence

Stable, project-specific policy lives here (`docs/AI_ROUTER.md`) and in
`.claude/agents/`; `CLAUDE.md` gets a short pointer, not the full policy
inlined, matching how it already points to `docs/HANDOFF.md` for status
rather than inlining it. No global (`~/.claude/`) configuration was
touched. No machine-specific paths or credentials were committed —
`scripts/cloudflare_request_monitor.py` (built the same day, a related
but separate piece of work) reads the wrangler OAuth token from its
standard on-disk location at runtime rather than embedding it.

**V2 additions (2026-08-27):** `docs/AI_ROUTER.md` (this file, upgraded
in place — V1's Claude-only policy is unchanged and still the default
path); `CLAUDE.md`'s router pointer extended to mention the two new
external compute pools; `scripts/ai_router_telemetry.py` extended with a
`provider` field (backward-compatible, old records default to `CLAUDE`);
`scripts/ai_router_quota_check.py` (new, ~110 lines, dependency-free —
checks real Antigravity quota/credit state, Codex login status, and
documents that Claude quota isn't CLI-observable). No new heavyweight
service, no Hermes, no OpenRouter as a primary path — exactly as
instructed. Antigravity's OAuth session lives in Windows Credential
Manager (native secure keyring, per its own docs) and Codex's in
`~/.codex/`, neither ever read, copied, or persisted by anything built
this session — both CLIs manage their own credential storage
independently, the same arm's-length relationship this repo already has
with Codex from V1.
