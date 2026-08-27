# Fanfic AI Engineering Router V1

Project-local policy for which Claude model/effort/subagent handles which
kind of engineering work in this repo — not a product feature, doesn't
touch application behavior. Goal: speed, rate-limit efficiency, token
efficiency, and routing the *right* amount of capability at a task instead
of defaulting to the most expensive model for everything.

## Environment inventory (2026-08-27)

| | |
|---|---|
| Claude Code version | 2.1.231 |
| Claude auth mode | Claude.ai account/subscription (not a raw API key) |
| Codex CLI | Installed (bundled with the Codex desktop app), `codex-cli 0.149.0-alpha.4.1`, authenticated via ChatGPT OAuth login, default model `gpt-5.6-sol` at high reasoning effort |
| opencode / opensquilla | Not installed |
| Prior `.claude/agents/` or routing policy | None existed before this doc |

Model names below use Claude Code's current aliases (`sonnet`, `opus`,
`haiku`, `fable`) rather than hardcoded version-pinned IDs, per the
explicit instruction not to hardcode obsolete IDs — Claude Code resolves
the alias to whatever the current release is.

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
- Cap parallel workers at 2-3 unless the tasks are genuinely independent
  (different files/subsystems, no shared state).

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

**Model future-proofing:** Codex's model is read from its own
`~/.codex/config.toml` (`model = "gpt-5.6-sol"`, `model_reasoning_effort =
"high"` as of this writing) rather than hardcoded anywhere in this repo —
if a wrapper script is ever built around the `codex` CLI, it should read
that config rather than embedding a model string, since Codex's own
available models change on OpenAI's schedule, independent of this repo.

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

## Routing telemetry

`scripts/ai_router_telemetry.py` — a tiny, dependency-free append-only
JSONL logger (`.claude/router-telemetry.jsonl`, gitignored). Records only
non-sensitive metadata: timestamp, task category, model/tier, elapsed
seconds, success/failure, whether tests were run and passed, whether an
escalation occurred and why. **Never logs prompts or file contents.** Not
wired into automatic invocation on every agent call — it's a helper any
future session can call manually (or a hook can call, if one is added
later) when it wants to record a data point; not a background service,
not a database.

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
