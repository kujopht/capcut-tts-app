# AI Engineering Router V1 — first real burn-in

First genuine multi-agent product work run through the router built
earlier the same day (`docs/AI_ROUTER.md`). Data below is real telemetry
(`.venv\Scripts\python.exe -m scripts.ai_router_telemetry summary`), not
reconstructed after the fact.

## Task-by-task

| Task | Agent | Model | Effort | Time | Escalation | Result |
|---|---|---|---|---|---|---|
| Repo search (regression test location) | `Explore` (haiku override) | haiku | low | 12.5s | No | Correct |
| Docs summary (5-bullet rule extraction) | `Explore` (haiku override) | haiku | low | 18.2s | No | Correct |
| Cloudflare monitor scheduling investigation | `Explore` (haiku override) | haiku | low | 53.1s | No | Correct, found a real reusable systemd pattern |
| Bulk-import infrastructure inventory | `Explore` (haiku override) | haiku | low | 61.1s | No | Correct, found a real generic batch abstraction |
| Docs summary (same task, comparison) | `general-purpose` (sonnet override) | sonnet | medium | 9.2s | No | Correct content, minor format-instruction slip |
| Hard diagnosis (real race-condition, sonnet pass) | `general-purpose` (sonnet override) | sonnet | medium | 58.9s | No | Correct at the qualitative level |
| Vietnamese title parser (Phase 3 build) | `general-purpose` (sonnet override) | sonnet | medium | 903.0s | No | Done, 49 tests, independently found & respected `episode_parser.py`/`series_fingerprint.py` without being told they existed |
| Content quality scorer (Phase 6 build) | `general-purpose` (sonnet override) | sonnet | medium | 700.5s | No | Done, 47 tests, grounded in real canary evidence |
| Bulk-run service (Phase 5 build, from Opus spec) | `general-purpose` (sonnet override) | sonnet | medium | 596.6s | No | Done, 16 tests, found + fixed a real gap not in the original spec (terminal-run no-op guard) |
| Title-parser bug fixes (Codex findings) | `general-purpose` (sonnet override) | sonnet | medium | 891.6s | No | All 5 bugs fixed, independently re-verified by direct execution before merge |
| Hard diagnosis (same race-condition, opus pass) | `general-purpose` (opus override) | opus | high | 53.0s | Yes | More complete than the sonnet pass — caught a real bug (range-check gap) sonnet missed |
| Bulk-import architecture decision | `general-purpose` (opus override) | opus | high | 185.3s | Yes | Read the real code, correctly rejected the naive "reuse ImportBatch directly" option, delivered a concrete implementable spec |
| Independent review of title parser | `codex review --commit` | *external — Codex, not Claude Opus* | high | ~90s | Yes | Found 5 real bugs (2 genuine over-merge risks) neither the Sonnet builder nor this session's own reading caught |

## Summary

```
HAIKU TASKS:  4 (all Explore-agent investigations — repo search, doc
              summary, and two infrastructure-inventory passes)
SONNET TASKS: 6 (all four Phase 3/5/6 feature builds plus one bug-fix
              pass plus one benchmark comparison — the clear majority
              of implementation work, as the tier policy intends)
OPUS TASKS:   2 real Claude Opus calls (the architecture decision for
              Phase 5's bulk-import design, and one benchmark diagnosis
              pass) — both genuinely warranted escalations, not routine
              work sent to a bigger model out of caution.
FABLE TASKS:  0 — nothing this session came close to qualifying as the
              "genuinely extreme, long-horizon" bar Fable is reserved
              for. Correct outcome, not an oversight.
CODEX TASKS:  1 — an independent review of the one component explicitly
              flagged correctness-critical (the title-similarity
              confidence scorer), run via `codex review --commit`. This
              is tracked separately from the Opus figures above since
              it's a different model entirely, not a Claude escalation.
```

**UNNECESSARY FRONTIER ESCALATIONS: NO.** Every Opus call had a concrete
trigger (a real architectural decision with regression risk if wrong; a
head-to-head diagnosis comparison that then had a genuine follow-up —
Opus's answer directly led to fixing a real bug in already-merged code).
No task was sent to Opus "to be safe" without that trigger, and nothing
was sent to Fable at all. The one Codex call was likewise targeted — used
once, on the one piece of work explicitly flagged as correctness-critical
by the product spec itself, not sprayed across every PR.

## Routing issues found

Two real process issues, not benchmark-score nitpicks — both are now
documented as lessons in `docs/AI_ROUTER.md`'s "Lessons from first real
use" section rather than repeated here in full:

1. **Custom `.claude/agents/` definitions didn't load in the session that
   created them** — worked around with built-in agent types plus a
   `model` override, at the cost of losing the named agents' baked-in
   system prompts/tool restrictions/`maxTurns` caps for this run. Whether
   a *fresh* session picks them up is unverified (needs a session restart
   to check, which by definition can't happen from inside the session
   doing the checking).
2. **Concurrent writer agents + the parent session's own git branch
   switching, sharing one working tree, produced a real (recoverable)
   "where did my work go" scare** on the title-parser fix — traced to the
   parent session checking out a branch that didn't yet contain the
   agent's in-progress file. No data was actually lost; it cost real
   diagnosis time. `docs/AI_ROUTER.md` now recommends `isolation:
   "worktree"` specifically for this situation (parent session needs to
   keep branching while writers are still active), which the original
   policy hadn't anticipated as a trigger.

No changes were made to the actual tier/model assignments — the routing
itself (which task types go to which model) held up correctly under real
use. What changed is operational guidance about *how* to run concurrent
agents, which is exactly the kind of adjustment the router's own
principle calls for: "only adjust it if real engineering work reveals a
problem," not tuning for its own sake.
