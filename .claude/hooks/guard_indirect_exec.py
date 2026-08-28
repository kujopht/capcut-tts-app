#!/usr/bin/env python3
"""PreToolUse guard for the Bash tool.

Second enforcement layer behind the ``permissions.deny`` globs in
``.claude/settings.json``. Glob rules match the raw command string; they cannot
see *through* shell structure. This guard splits the command into segments --
including the bodies of ``$(...)``, backticks and ``${...}`` -- and evaluates
every segment against the same boundary, so laundering a blocked command
through substitution or chaining does not get past it.

Contract (Claude Code PreToolUse hook):
  stdin  : {"tool_name": "Bash", "tool_input": {"command": "..."}}
  stdout : {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny"|"ask",
                                   "permissionDecisionReason": "..."}}
  Staying silent (no JSON) leaves the normal permission flow untouched.

Fails to ``ask``, never to ``allow``: an internal error surfaces a prompt
rather than quietly waving the command through.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

MAX_DEPTH = 12

# Shell operators that separate one command from the next.
SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|&\n]")

# $( ... ), ` ... ` and ${ ... }. Bodies are pulled out and checked as segments
# of their own, recursively, so nesting does not hide anything. A regex cannot
# do this: the body may itself contain balanced parens -- $(python -c 'f(1)').
SUBSTITUTION_OPENERS = (("$(", "(", ")"), ("${", "{", "}"))


def substitution_bodies(text: str) -> list[str]:
    """Bodies of every $(...) / ${...} / `...` in *text*, paren-depth aware."""
    bodies: list[str] = []

    for opener, open_ch, close_ch in SUBSTITUTION_OPENERS:
        idx = 0
        while True:
            start = text.find(opener, idx)
            if start == -1:
                break
            depth = 0
            pos = start + len(opener) - 1
            while pos < len(text):
                if text[pos] == open_ch:
                    depth += 1
                elif text[pos] == close_ch:
                    depth -= 1
                    if depth == 0:
                        body = text[start + len(opener) : pos]
                        if body.strip():
                            bodies.append(body)
                        break
                pos += 1
            idx = start + len(opener)

    parts = text.split("`")
    if len(parts) >= 3:
        for body in parts[1::2]:
            if body.strip():
                bodies.append(body)

    return bodies

# Cmdlets and tools that mutate machine state. Matched anywhere in the command
# text, case-insensitively, because PowerShell verbs appear mid-pipeline.
STATE_MUTATION = {
    "set-mppreference": "Defender policy mutation",
    "add-mppreference": "Defender policy mutation",
    "remove-mppreference": "Defender policy mutation",
    "new-netfirewallrule": "firewall mutation",
    "set-netfirewallprofile": "firewall mutation",
    "remove-netfirewallrule": "firewall mutation",
    "new-service": "service mutation",
    "set-service": "service mutation",
    "remove-service": "service mutation",
    "stop-service": "service mutation",
    "start-service": "service mutation",
    "register-scheduledtask": "scheduled-task mutation",
    "unregister-scheduledtask": "scheduled-task mutation",
    "set-scheduledtask": "scheduled-task mutation",
    "set-executionpolicy": "execution-policy mutation",
    "new-itemproperty": "registry mutation",
    "remove-itemproperty": "registry mutation",
    "start-process": "privilege escalation via Start-Process",
}

# Whole-command binaries that exist to mutate the system.
MUTATION_BINARIES = {
    "schtasks": "scheduled-task mutation",
    "sc": "service-control mutation",
    "netsh": "network/firewall mutation",
    "bcdedit": "boot-configuration mutation",
    "runas": "privilege escalation",
    "sudo": "privilege escalation",
    "eval": "arbitrary indirect execution",
    "xargs": "arbitrary indirect execution",
}

# Interpreters, and the flags that turn them into arbitrary code execution.
# `python -m unittest` and `python -m pytest` stay usable on purpose -- only
# inline-source flags are refused.
INLINE_SOURCE_FLAGS = {
    "python": {"-c"},
    "python3": {"-c"},
    "py": {"-c"},
    "node": {"-e", "--eval", "-p", "--print"},
    "perl": {"-e", "-E"},
    "ruby": {"-e"},
    "bash": {"-c"},
    "sh": {"-c"},
    "zsh": {"-c"},
}

# PowerShell accepts any unambiguous prefix of a parameter name, so -Comm,
# -EncodedC and -ec all work. Prefix-match rather than listing spellings.
POWERSHELL_PARAMS = ("command", "encodedcommand", "file")


def emit(decision: str, reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def tokenize(segment: str) -> list[str]:
    """Best-effort argv split that survives Windows paths and stray quotes."""
    try:
        raw = shlex.split(segment, posix=False)
    except ValueError:
        raw = segment.split()
    out = []
    for tok in raw:
        if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
            tok = tok[1:-1]
        if tok:
            out.append(tok)
    return out


def binary_name(token: str) -> str:
    name = os.path.basename(token.replace("\\", "/")).lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


def expand(command: str) -> list[str]:
    """Command plus the body of every substitution, transitively."""
    segments: list[str] = []
    pending = [command]
    depth = 0
    while pending and depth < MAX_DEPTH:
        nxt: list[str] = []
        for chunk in pending:
            segments.append(chunk)
            nxt.extend(substitution_bodies(chunk))
        pending = nxt
        depth += 1
    return segments


def check_git(tokens: list[str], flat: str) -> str | None:
    rest = [t.lower() for t in tokens[1:] if not t.startswith("-")]
    flags = [t.lower() for t in tokens[1:] if t.startswith("-")]
    sub = rest[0] if rest else ""

    if sub == "push":
        if any(f in ("--force", "-f", "--force-with-lease", "--delete", "-d") for f in flags):
            return "force/delete push"
        if re.search(r"\s\+[\w./-]+:", flat):
            return "force push via +refspec"
    if sub == "reset" and "--hard" in flags:
        return "destructive git reset"
    # `git clean` without -f refuses to delete, so -f is the destructive signal.
    if sub == "clean" and any(f.startswith("-") and "f" in f for f in flags):
        return "destructive git clean"
    raw_flags = [t for t in tokens[1:] if t.startswith("-")]
    if sub == "branch" and ("-D" in raw_flags or {"--delete", "--force"} <= set(flags)):
        return "forced branch deletion"
    if sub in ("rebase", "filter-branch", "filter-repo"):
        return f"history rewrite (git {sub})"
    if sub == "reflog" and len(rest) > 1 and rest[1] in ("expire", "delete"):
        return "reflog destruction"
    if sub == "update-ref" and "-d" in flags:
        return "ref deletion"
    if sub in ("symbolic-ref",) or (sub == "remote" and "set-url" in rest):
        return "remote/ref repointing"
    return None


def check_gh(tokens: list[str]) -> str | None:
    rest = [t.lower() for t in tokens[1:] if not t.startswith("-")]
    if len(rest) >= 2:
        if rest[0] == "secret" and rest[1] in ("set", "delete", "remove"):
            return "secret mutation"
        if rest[0] == "auth" and rest[1] in ("token", "refresh"):
            return "credential disclosure"
    return None


def check_delete(tokens: list[str], flat: str) -> str | None:
    name = binary_name(tokens[0])
    flags = [t.lower() for t in tokens[1:] if t.startswith("-")]
    targets = [t for t in tokens[1:] if not t.startswith("-") and not t.startswith("/")]

    if name in ("rm", "del", "erase"):
        if any("r" in f or "f" in f for f in flags) or any(
            t.lower() in ("/s", "/q", "/f") for t in tokens[1:]
        ):
            return "recursive/forced deletion"
        if any(".claude" in t.replace("\\", "/") for t in targets):
            return "deletion inside .claude/ (guard tampering)"
    if name == "rmdir" and any(t.lower() == "/s" for t in tokens[1:]):
        return "recursive directory removal"
    if name == "remove-item" and any(
        f.startswith("-recurse") or f.startswith("-force") for f in flags
    ):
        return "recursive/forced deletion"
    if name in ("mv", "move", "cp", "copy") and ".claude/hooks" in flat.replace("\\", "/"):
        return "overwriting the guard in .claude/hooks/"
    return None


def evaluate(segment: str) -> str | None:
    flat = segment.strip()
    if not flat:
        return None

    low = flat.lower()
    for needle, why in STATE_MUTATION.items():
        if re.search(rf"(?<![\w-]){re.escape(needle)}(?![\w-])", low):
            if needle == "start-process" and "runas" not in low:
                continue
            return why
    if re.search(r"set-itemproperty", low) and re.search(r"hk(lm|cu|cr|u|cc)", low):
        return "registry mutation"
    if re.search(r"(?<![\w-])awk(?![\w-])", low) and "system(" in low:
        return "arbitrary execution via awk system()"
    if "disableallhooks" in low.replace(" ", ""):
        return "attempt to disable hooks"

    tokens = tokenize(flat)
    if not tokens:
        return None
    name = binary_name(tokens[0])
    flags_lower = [t.lower() for t in tokens[1:] if t.startswith("-")]

    if name in MUTATION_BINARIES:
        return MUTATION_BINARIES[name]

    if name in INLINE_SOURCE_FLAGS:
        # `-m module` is legitimate; inline source is not.
        for tok in tokens[1:]:
            t = tok.lower()
            if t in ("-m", "--module"):
                break
            if t in INLINE_SOURCE_FLAGS[name]:
                return f"inline code execution ({name} {t})"

    if name in ("powershell", "pwsh", "powershell_ise"):
        for tok in flags_lower:
            stem = tok.lstrip("-/").split(":", 1)[0]
            if stem and any(p.startswith(stem) for p in POWERSHELL_PARAMS):
                return f"PowerShell inline execution ({tok})"

    if name == "cmd" and any(t.lower() in ("/c", "/k", "-c") for t in tokens[1:]):
        return "cmd inline execution"

    # `reg query` is read-only and stays usable; every writing subcommand does not.
    if name == "reg":
        rest = [t.lower() for t in tokens[1:] if not t.startswith("/")]
        if rest and rest[0] in (
            "add", "delete", "import", "copy", "restore", "load", "unload", "save",
        ):
            return "registry mutation"
        return None

    if name == "git":
        return check_git(tokens, flat)
    if name == "gh":
        return check_gh(tokens)
    if name in ("rm", "del", "erase", "rmdir", "remove-item", "mv", "move", "cp", "copy"):
        return check_delete(tokens, flat)
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        emit("ask", "Bash guard could not parse hook input; falling back to a prompt.")
        return 0

    try:
        if payload.get("tool_name") != "Bash":
            return 0
        command = (payload.get("tool_input") or {}).get("command") or ""
        if not command.strip():
            return 0

        for chunk in expand(command):
            for segment in SEGMENT_SPLIT.split(chunk):
                reason = evaluate(segment)
                if reason:
                    emit(
                        "deny",
                        f"Blocked by .claude/hooks/guard_indirect_exec.py: {reason}. "
                        f"Offending segment: {segment.strip()[:160]}",
                    )
                    return 0
    except Exception as exc:  # never fail open
        emit("ask", f"Bash guard errored ({type(exc).__name__}); falling back to a prompt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
