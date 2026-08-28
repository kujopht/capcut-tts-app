#!/usr/bin/env python3
"""Single dispatch path for the AI router — the point where routing policy
stops being prose and becomes something that actually runs.

The problem this exists to solve: CLAUDE_CONSERVATION was active all day on
2026-08-28 while a large permission-hardening task ran 100% on native Claude
with zero external dispatch. The policy was correct and simply not applied,
because applying it meant hand-writing an `agy`/`codex` command line every
time. This module makes the routed call the path of least resistance and
records it automatically, so "the router was ignored" becomes visible in the
telemetry rather than invisible in a transcript.

Two entry points, both cheap:

    # Decide only -- no worker runs, no quota spent. Use this BEFORE starting
    # any substantial task; it prints the routing decision record.
    python scripts/ai_router_dispatch.py --task-class SEARCH --risk LOW --dry-run

    # Decide and dispatch. Prompt comes from --prompt-file or stdin.
    echo "..." | python scripts/ai_router_dispatch.py --task-class SEARCH --risk LOW

Output is always a single JSON object on stdout: a `decision` block (task
class, risk, chosen pool/model, and why native Claude is or is not required)
and, when a worker ran, a `result` block. Telemetry is written by this module
itself -- a caller cannot dispatch and forget to record it.

Deliberate non-goals: no daemon, no polling, no repo content shipped by
default (the worker runs in a scratch cwd unless --add-dir is passed), and no
auto-merge/auto-deploy of anything a worker produces.

Privacy: telemetry records metadata only (provider, model, category, seconds,
success, escalation). Never prompt text, file contents, model output, or
secrets. Prompts are scanned for obvious credential shapes and the dispatch is
refused rather than leaked to a third-party CLI.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_router_telemetry  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# --------------------------------------------------------------------------
# Routing policy, expressed once, in code.
#
# This mirrors the CLAUDE_CONSERVATION table in ~/.claude/CLAUDE.md. Prose in
# a markdown file cannot refuse to route a security review to Codex; this can.
# --------------------------------------------------------------------------
NATIVE = "NATIVE_CLAUDE"

ROUTING = {
    "SEARCH": ("GEMINI_FLASH", "Repo archaeology/log reading is cheap, bounded, and does not need native Claude."),
    "MECHANICAL": ("GEMINI_FLASH", "Repetitive tests/fixtures/docs are mechanical; length is not complexity."),
    "LARGE_CONTEXT": ("GEMINI_PRO", "Repo-wide/architecture work needs long context, returned as a structured packet."),
    "IMPLEMENTATION": ("GEMINI_FLASH", "Isolated, well-specified implementation is sufficient on the cheap external tier."),
    "INTEGRATION": (NATIVE, "Cross-file integration is the thin-integrator role conservation explicitly reserves for native Claude."),
    "SEMANTIC_REVIEW": ("CLAUDE_SONNET", "Semantic/design review benefits from a Claude-family reviewer, taken from Antigravity's pool."),
    "SECURITY_REVIEW": ("CLAUDE_OPUS", "Security/auth/permission/concurrency review is the highest-risk class; frontier model, never Codex."),
    "ORDINARY_REVIEW": ("CODEX", "Ordinary code-correctness review is Codex's proven strength and gives cross-family diversity."),
    "CHALLENGER": ("GPT_OSS", "Third-opinion/adversarial challenge, deliberately from a different model family."),
}

# Pool -> (provider, role pattern used to resolve a live model id).
POOLS = {
    "GEMINI_FLASH": ("antigravity", r"^gemini-(?P<maj>\d+)\.(?P<min>\d+)-flash-low$"),
    "GEMINI_PRO": ("antigravity", r"^gemini-(?P<maj>\d+)\.(?P<min>\d+)-pro-low$"),
    "CLAUDE_SONNET": ("antigravity", r"^claude-sonnet-(?P<maj>\d+)-(?P<min>\d+)$"),
    "CLAUDE_OPUS": ("antigravity", r"^claude-opus-(?P<maj>\d+)-(?P<min>\d+)-thinking$"),
    "GPT_OSS": ("antigravity", r"^gpt-oss-(?P<maj>\d+)(?P<min>)b-medium$"),
    "CODEX": ("codex", None),
    NATIVE: (None, None),
}

# Classes that must never reach Codex, regardless of flags. Codex refused a
# real permission-profile review on 2026-08-28 ("flagged for possible
# cybersecurity risk") after being sent the identical packet that Antigravity
# reviewed successfully -- so this is measured behaviour, not caution.
CODEX_FORBIDDEN_CLASSES = {"SECURITY_REVIEW"}

# Obvious credential shapes. Not a secret scanner -- a last-ditch guard so a
# careless packet does not reach a third-party CLI.
SECRET_PATTERNS = (
    (r"gh[pousr]_[A-Za-z0-9]{20,}", "GitHub token"),
    (r"sk-[A-Za-z0-9]{20,}", "OpenAI-style key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
    (r"(?i)\b(api[_-]?key|secret|passwd|password|token)\s*[:=]\s*['\"][^'\"]{12,}", "inline credential assignment"),
)


def find_antigravity() -> Optional[str]:
    found = shutil.which("agy") or shutil.which("agy.exe")
    if found:
        return found
    candidate = os.path.join(os.environ.get("LOCALAPPDATA", ""), "agy", "bin", "agy.exe")
    return candidate if os.path.isfile(candidate) else None


def find_codex() -> Optional[str]:
    found = shutil.which("codex") or shutil.which("codex.exe")
    if found:
        return found
    # The desktop install lives under a version-hash directory that changes on
    # update. Resolve by glob; never hardcode the hash.
    pattern = os.path.join(os.environ.get("LOCALAPPDATA", ""), "OpenAI", "Codex", "bin", "*", "codex.exe")
    matches = sorted(glob.glob(pattern))
    return matches[-1] if matches else None


def resolve_model(pool: str, timeout: int = 60) -> Tuple[Optional[str], str]:
    """Pick the highest-versioned live model matching the pool's role pattern.

    Model ids move (gemini-3.5 -> 3.7 within days). Asking the CLI what exists
    now beats pinning a string that silently goes stale.
    """
    provider, pattern = POOLS[pool]
    if provider != "antigravity" or not pattern:
        return None, "no model resolution needed for this pool"
    agy = find_antigravity()
    if not agy:
        return None, "agy not found"
    try:
        out = subprocess.run(
            [agy, "models"], capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        ).stdout
    except Exception as exc:
        return None, f"model listing failed: {type(exc).__name__}"

    best, best_key = None, None
    rx = re.compile(pattern)
    for line in out.splitlines():
        ident = line.split("\t", 1)[0].strip()
        m = rx.match(ident)
        if not m:
            continue
        key = (int(m.group("maj") or 0), int(m.group("min") or 0))
        if best_key is None or key > best_key:
            best, best_key = ident, key
    if not best:
        return None, f"no live model matched role pattern {pattern}"
    return best, "resolved from live `agy models`"


def scan_for_secrets(text: str) -> Optional[str]:
    for pattern, label in SECRET_PATTERNS:
        if re.search(pattern, text):
            return label
    return None


def decide(task_class: str, risk: str, allow_codex: bool = True) -> dict:
    """Pure routing decision. No side effects, no quota spent."""
    task_class = task_class.upper()
    risk = risk.upper()
    if task_class not in ROUTING:
        raise SystemExit(f"unknown --task-class {task_class!r}; expected one of {sorted(ROUTING)}")

    pool, why = ROUTING[task_class]
    escalated, escalation_reason = False, ""

    # HIGH risk turns an ordinary review into a security-grade one. Conservation
    # saves quota; it does not lower the bar on risky work.
    if risk == "HIGH" and task_class in ("ORDINARY_REVIEW", "SEMANTIC_REVIEW"):
        pool, escalated = "CLAUDE_OPUS", True
        escalation_reason = f"risk=HIGH escalates {task_class} to the frontier reviewer"
        why = "High-risk review escalated to Claude Opus (via Antigravity), never Codex."

    if pool == "CODEX" and (task_class in CODEX_FORBIDDEN_CLASSES or not allow_codex):
        pool, escalated = "CLAUDE_OPUS", True
        escalation_reason = "Codex is not eligible for security-class work"

    native_required = pool == NATIVE
    return {
        "task_class": task_class,
        "risk": risk,
        "pool": pool,
        "provider": POOLS[pool][0] or "native-claude",
        "native_claude_required": native_required,
        "why": why,
        "why_not_native": (
            "Native Claude is the coordinator here and is NOT replaced."
            if native_required
            else "Native Claude is not required: this class is delegable under CLAUDE_CONSERVATION."
        ),
        "escalated": escalated,
        "escalation_reason": escalation_reason,
    }


def run_worker(pool: str, model: Optional[str], prompt: str, timeout: int,
               add_dir: Optional[str]) -> dict:
    provider = POOLS[pool][0]
    # Default cwd is a scratch dir so no repository content leaves the machine
    # unless the caller explicitly opts in with --add-dir.
    workdir = add_dir or tempfile.mkdtemp(prefix="ai-router-")

    if provider == "antigravity":
        binary = find_antigravity()
        if not binary:
            return {"status": "unavailable", "error": "agy not found"}
        argv = [binary]
        if model:
            argv += ["--model", model]
        # --print consumes the next argument as the prompt, so it goes last.
        argv += ["--output-format", "text", "--print-timeout", f"{timeout}s", "--print", prompt]
        stdin_data = None
    elif provider == "codex":
        binary = find_codex()
        if not binary:
            return {"status": "unavailable", "error": "codex not found"}
        # Codex reads the prompt from stdin with a trailing '-'; this is the
        # workaround for its broken local-file prompt reading.
        argv = [binary, "exec", "--skip-git-repo-check", "-"]
        stdin_data = prompt
    else:
        return {"status": "skipped", "error": "native Claude pool does not dispatch"}

    started = time.time()
    try:
        proc = subprocess.run(
            argv, input=stdin_data, capture_output=True, text=True,
            timeout=timeout, cwd=workdir, encoding="utf-8", errors="replace",
        )
        elapsed = time.time() - started
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        ok = proc.returncode == 0 and bool(out)
        return {
            "status": "ok" if ok else "failed",
            "exit_code": proc.returncode,
            "seconds": round(elapsed, 2),
            "output": out,
            # Truncated: enough to diagnose a refusal, never a transcript dump.
            "stderr_tail": err[-400:] if err else "",
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "seconds": round(time.time() - started, 2),
                "error": f"worker exceeded {timeout}s"}
    except Exception as exc:
        return {"status": "error", "seconds": round(time.time() - started, 2),
                "error": f"{type(exc).__name__}: {exc}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Route and dispatch one task to the correct worker.")
    ap.add_argument("--task-class", required=True, help=f"one of {sorted(ROUTING)}")
    ap.add_argument("--risk", default="LOW", choices=["LOW", "low", "MEDIUM", "medium", "HIGH", "high"])
    ap.add_argument("--category", default="", help="free-text label for telemetry (no content)")
    ap.add_argument("--prompt-file", default=None)
    ap.add_argument("--timeout", type=int, default=180, help="bounded; default 180s")
    ap.add_argument("--add-dir", default=None, help="opt in to giving the worker a real directory")
    ap.add_argument("--no-codex", action="store_true", help="forbid Codex for this dispatch")
    ap.add_argument("--dry-run", action="store_true", help="decide only; no worker, no quota")
    ap.add_argument("--preflight", action="store_true", help="verify paid-overage risk is zero first")
    args = ap.parse_args(argv)

    decision = decide(args.task_class, args.risk, allow_codex=not args.no_codex)
    category = args.category or decision["task_class"].lower()

    if args.preflight:
        qc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_router_quota_check.py")
        try:
            raw = subprocess.run([sys.executable, qc], capture_output=True, text=True,
                                 timeout=120, encoding="utf-8", errors="replace").stdout
            safe = json.loads(raw).get("antigravity", {}).get("paid_overage_risk_zero")
            decision["preflight_paid_overage_risk_zero"] = safe
            if safe is False:
                decision["aborted"] = "paid overage risk is NOT zero — refusing to dispatch"
                print(json.dumps({"decision": decision}, indent=2, ensure_ascii=False))
                return 2
        except Exception as exc:
            decision["preflight_paid_overage_risk_zero"] = f"unknown ({type(exc).__name__})"

    if args.dry_run or decision["native_claude_required"]:
        # Record the decision even when nothing is dispatched: a native-Claude
        # choice under CLAUDE_CONSERVATION is exactly what needs to be visible.
        # Tier is prefixed DECISION: so a routing decision can never be
        # miscounted as a real dispatch. Provider is CLAUDE because the
        # coordinator decided; no external worker was contacted.
        ai_router_telemetry.log_run(
            category=category, tier=f"DECISION:{decision['pool']}", seconds=0.0,
            success=True, provider="CLAUDE", model="(decision-only)",
            escalated=decision["escalated"],
            escalation_reason=decision["escalation_reason"] or ("dry-run" if args.dry_run else ""),
        )
        print(json.dumps({"decision": decision, "result": {"status": "not_dispatched"}},
                         indent=2, ensure_ascii=False))
        return 0

    prompt = open(args.prompt_file, encoding="utf-8").read() if args.prompt_file else sys.stdin.read()
    if not prompt.strip():
        raise SystemExit("empty prompt: pass --prompt-file or pipe text on stdin")

    leak = scan_for_secrets(prompt)
    if leak:
        decision["aborted"] = f"prompt appears to contain a {leak}; refusing to send it to an external CLI"
        print(json.dumps({"decision": decision, "result": {"status": "refused"}},
                         indent=2, ensure_ascii=False))
        return 2

    model, model_note = resolve_model(decision["pool"])
    decision["model"] = model or "(provider default)"
    decision["model_resolution"] = model_note

    result = run_worker(decision["pool"], model, prompt, args.timeout, args.add_dir)

    provider_for_log = {"antigravity": "ANTIGRAVITY", "codex": "CODEX"}.get(decision["provider"], "CLAUDE")
    ai_router_telemetry.log_run(
        category=category, tier=decision["pool"],
        seconds=float(result.get("seconds", 0.0)),
        success=result.get("status") == "ok",
        provider=provider_for_log, model=decision["model"],
        escalated=decision["escalated"], escalation_reason=decision["escalation_reason"],
    )

    if result.get("status") != "ok":
        result["fallback"] = (
            "External worker did not succeed. Per CLAUDE_CONSERVATION, native Claude "
            "handles genuine external failure — retry once, then integrate natively."
        )
    print(json.dumps({"decision": decision, "result": result}, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
