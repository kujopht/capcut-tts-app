#!/usr/bin/env python3
"""PreToolUse guard for the Bash tool.

Second enforcement layer behind the ``permissions.deny`` globs in
``.claude/settings.json``. Glob rules match the raw command string; they cannot
see *through* shell structure. This guard splits the command into segments --
including the bodies of ``$(...)``, backticks and ``${...}`` -- and evaluates
every segment against the same boundary, so laundering a blocked command
through substitution or chaining does not get past it.

Contract (Claude Code PreToolUse hook):
  stdin  : {"tool_name": "Bash", "permission_mode": "auto"|"bypassPermissions"|...,
            "tool_input": {"command": "..."}}
  stdout : {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny"|"ask"|"allow",
                                   "permissionDecisionReason": "..."}}
  Staying silent (no JSON) leaves the normal permission flow untouched.

Three tiers, in strict precedence order:

  1. DENY  -- destructive git, destructive filesystem, registry/service/
     scheduled-task/Defender/firewall mutation, credential disclosure, and
     indirect arbitrary execution. Enforced in *every* mode, including
     ``bypassPermissions``. This is the hard boundary.
  2. ASK   -- genuinely consequential remote mutations: ordinary ``git push``,
     PR create/merge, workflow dispatch, production deploy. Applied in every
     mode EXCEPT ``bypassPermissions``, where the operator is physically at
     the machine and has already accepted routine remote writes.
  3. ALLOW -- provably read-only inspection (notably read-only ``gh``) that a
     glob in ``settings.json`` cannot recognise, because the read/write
     distinction lives in flags rather than in a command prefix. Emitted only
     when *every* segment of the command is read-only.

Anything unrecognised stays silent and falls through to the normal permission
flow -- the guard narrows behaviour, it does not replace the settings rules.

Precedence, measured against Claude Code 2.1.231 rather than assumed:

  * a hook ``deny`` overrides an ``allow`` rule AND ``bypassPermissions``.
    This is what makes tier 1 a real boundary.
  * a hook ``ask`` overrides an ``allow`` rule.
  * a hook ``allow`` is IGNORED -- it does not grant permission.
  * an ``ask`` rule in settings.json fires even under ``bypassPermissions``.

Two consequences shape this file and settings.json together:

  * settings.json carries NO ``Bash(...)`` ask rules. One would prompt at the
    laptop in bypass mode, which is exactly what mode exists to avoid. Tier 2
    lives here instead, where it can read the mode.
  * tier 3's no-prompt effect comes from the narrow ``permissions.allow``
    entries (including ``Bash(gh api:*)``), not from the allow emitted below.
    That allow rule is deliberately broader than the read-only set, and is
    safe only because tiers 1 and 2 here re-inspect every matching command and
    outrank it: ``gh api -X DELETE`` denies, ``gh api -X POST`` asks. Weakening
    the classifier below therefore widens that allow rule -- change both, or
    neither. The emission is kept because it is the executable definition of
    "read-only", and it starts working the day the runtime honours it.

``permission_mode`` is read from the top level of the hook payload; the field
name and its values (``auto``, ``default``, ``acceptEdits``,
``bypassPermissions``) were confirmed empirically against Claude Code 2.1.231.
Only the exact string ``bypassPermissions`` relaxes tier 2; any unknown or
missing mode keeps the prompt, so a future rename fails safe.

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

# The only mode in which tier 2 (ASK) is relaxed. Everything else -- "auto",
# "default", "acceptEdits", "plan", an unknown future name, or a missing field
# -- keeps the prompt.
BYPASS_MODE = "bypassPermissions"

# ---------------------------------------------------------------------------
# Tier 3: read-only `gh`.
#
# `gh` splits read from write at the subcommand, not at a command prefix a glob
# can anchor on -- `gh api` is a GET or a POST depending on flags that may sit
# anywhere in argv. That is precisely why the old `Bash(gh api*)` ask rule
# prompted for every read: a glob cannot see the method. These tables are
# consulted only after tier 1 has cleared the command.
# ---------------------------------------------------------------------------
GH_READ_SUBCOMMANDS = {
    ("api",),            # gated further by gh_api_is_mutating()
    ("auth", "status"),
    ("browse",),
    ("cache", "list"),
    ("gist", "list"),
    ("gist", "view"),
    ("issue", "list"),
    ("issue", "status"),
    ("issue", "view"),
    ("label", "list"),
    ("pr", "checks"),
    ("pr", "diff"),
    ("pr", "list"),
    ("pr", "status"),
    ("pr", "view"),
    ("release", "list"),
    ("release", "view"),
    ("repo", "list"),
    ("repo", "view"),
    ("ruleset", "list"),
    ("ruleset", "view"),
    ("run", "list"),
    ("run", "view"),
    ("run", "watch"),
    ("search",),
    ("secret", "list"),
    ("status",),
    ("variable", "list"),
    ("workflow", "list"),
    ("workflow", "view"),
}

# Tier 2 for `gh`: writes something on GitHub. Not destructive enough to deny
# outright, consequential enough to confirm when operating remotely.
GH_MUTATE_SUBCOMMANDS = {
    ("cache", "delete"): "GitHub Actions cache deletion",
    ("gist", "create"): "gist creation",
    ("gist", "delete"): "gist deletion",
    ("gist", "edit"): "gist edit",
    ("issue", "close"): "issue close",
    ("issue", "comment"): "issue comment",
    ("issue", "create"): "issue creation",
    ("issue", "delete"): "issue deletion",
    ("issue", "edit"): "issue edit",
    ("issue", "reopen"): "issue reopen",
    ("label", "create"): "label creation",
    ("label", "delete"): "label deletion",
    ("label", "edit"): "label edit",
    ("pr", "close"): "PR close",
    ("pr", "comment"): "PR comment",
    ("pr", "create"): "PR creation",
    ("pr", "edit"): "PR edit",
    ("pr", "merge"): "PR merge",
    ("pr", "ready"): "PR ready-for-review",
    ("pr", "reopen"): "PR reopen",
    ("pr", "review"): "PR review submission",
    ("release", "create"): "release creation",
    ("release", "delete"): "release deletion",
    ("release", "edit"): "release edit",
    ("release", "upload"): "release asset upload",
    ("repo", "archive"): "repository archive",
    ("repo", "create"): "repository creation",
    ("repo", "edit"): "repository settings change",
    ("repo", "rename"): "repository rename",
    ("repo", "sync"): "repository sync",
    ("ruleset", "create"): "ruleset creation",
    ("run", "cancel"): "workflow-run cancellation",
    ("run", "delete"): "workflow-run deletion",
    ("run", "rerun"): "workflow re-run",
    ("secret", "set"): "writing a repository/environment secret",
    ("variable", "set"): "variable mutation",
    ("variable", "delete"): "variable deletion",
    ("workflow", "disable"): "workflow disable",
    ("workflow", "enable"): "workflow enable",
    ("workflow", "run"): "workflow dispatch",
    ("auth", "login"): "interactive credential login",
    ("auth", "logout"): "credential logout",
}

# `gh api` flags. A method other than GET, or any field/input flag (which makes
# gh default to POST), means the call writes.
GH_API_METHOD_FLAGS = ("-x", "--method")
GH_API_FIELD_FLAGS = ("-f", "--field", "-f=", "--raw-field", "--input")
GH_API_READ_METHODS = ("get", "head")
# Methods that are destructive rather than merely consequential.
GH_API_DENY_METHODS = ("delete",)

# Tier 2 for everything that is not `gh`: shipping code or state off this
# machine. Matched on the flattened, lowercased segment.
DEPLOY_PATTERNS = (
    (r"(?<![\w-])wrangler\s+deploy(?![\w-])", "Cloudflare Worker deploy"),
    (r"(?<![\w-])wrangler\s+rollback(?![\w-])", "Cloudflare Worker rollback"),
    (r"(?<![\w-])wrangler\s+versions\s+deploy(?![\w-])", "Cloudflare version deploy"),
    (r"(?<![\w-])wrangler\s+login(?![\w-])", "interactive credential login"),
    (r"npm\s+run\s+cf:deploy", "Cloudflare deploy script"),
    (r"opennextjs-cloudflare\s+deploy", "OpenNext Cloudflare deploy"),
    (r"render_deploy_hook", "Render deploy hook"),
    (r"deploy-hook", "deploy hook"),
    (r"api\.render\.com", "Render API call"),
)


# Text filters that neither read anything privileged nor write. They may sit in
# a pipeline beside a read-only `gh` call without costing it its tier-3 allow.
# `sed` and `awk` are deliberately absent: `sed -i` writes and `awk` can exec.
BENIGN_FILTERS = {
    "cat", "column", "cut", "echo", "findstr", "grep", "head", "jq", "nl",
    "rev", "sort", "tail", "tr", "uniq", "wc",
}

# A redirection that targets a file writes to disk. `2>&1` and `>&1` merely
# rewire an existing stream, so they must not cost a command its allow.
FILE_REDIRECT = re.compile(r">\s*(?!&)")

# `2>&1`, `>&2` and friends. Stripped before the command is split, because
# SEGMENT_SPLIT breaks on `&` and would otherwise read the `1` of `2>&1` as a
# second command -- costing a read-only call its allow. Removing these hides
# nothing: no command can be smuggled inside a stream-merge token.
STREAM_REDIRECT = re.compile(r"\d?>&\d?")


def is_bypass(mode: str) -> bool:
    """True only for the exact bypassPermissions string -- unknown fails safe."""
    return mode == BYPASS_MODE


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
    # `git rebase` and `git branch -D` are NOT here. Both are everyday local
    # work on a trusted machine and both are recoverable from the reflog, so
    # denying them outright taxed normal development without protecting
    # anything irreversible. They are tier 2 instead: confirmed when working
    # remotely, silent at the laptop. `filter-branch`/`filter-repo` stay
    # denied -- those rewrite every commit and the reflog will not save you.
    if sub in ("filter-branch", "filter-repo"):
        return f"whole-history rewrite (git {sub})"
    if sub == "reflog" and len(rest) > 1 and rest[1] in ("expire", "delete"):
        return "reflog destruction"
    if sub == "update-ref" and "-d" in flags:
        return "ref deletion"
    if sub in ("symbolic-ref",) or (sub == "remote" and "set-url" in rest):
        return "remote/ref repointing"
    return None


# curl flags that send a body or choose a method. Short flags are matched
# CASE-SENSITIVELY on purpose: `-F` is a form upload but `-f` is `--fail`, and
# `-T` uploads but `-t` does not exist -- lowercasing them would flag ordinary
# read-only fetches like `curl -fsSL <url>` as writes.
CURL_BODY_FLAGS_EXACT = ("-d", "-F", "-T")
CURL_BODY_FLAGS_LONG = (
    "--data", "--data-raw", "--data-binary", "--data-urlencode", "--data-ascii",
    "--form", "--form-string", "--upload-file",
)
CURL_METHOD_FLAGS = ("-X", "--request")


def curl_method(tokens: list[str]) -> str:
    """HTTP method of a curl call, defaulting to GET."""
    args = tokens[1:]
    for idx, tok in enumerate(args):
        if tok in CURL_METHOD_FLAGS:
            return args[idx + 1].strip().lower() if idx + 1 < len(args) else "get"
        if tok.startswith("--request="):
            return tok.partition("=")[2].strip().lower()
        if tok.startswith("-X") and len(tok) > 2:
            return tok[2:].strip().lower()
    return "get"


def curl_is_write(tokens: list[str]) -> bool:
    """True when curl sends a body or selects a non-read method."""
    if curl_method(tokens) not in ("get", "head"):
        return True
    for tok in tokens[1:]:
        if tok in CURL_BODY_FLAGS_EXACT:
            return True
        if tok.partition("=")[0] in CURL_BODY_FLAGS_LONG:
            return True
    return False


def gh_api_method(tokens: list[str]) -> str:
    """HTTP method of a `gh api` call. Defaults to GET, as gh itself does.

    Handles `-X DELETE`, `-XDELETE`, `--method DELETE` and `--method=DELETE`.
    """
    args = tokens[1:]
    for idx, tok in enumerate(args):
        low = tok.lower()
        if "=" in low:
            head, _, tail = low.partition("=")
            if head in GH_API_METHOD_FLAGS:
                return tail.strip()
        for flag in GH_API_METHOD_FLAGS:
            if low == flag:
                if idx + 1 < len(args):
                    return args[idx + 1].strip().lower()
                return "get"
            # -XDELETE, glued short form.
            if flag == "-x" and low.startswith("-x") and len(low) > 2:
                return low[2:].strip()
    return "get"


def gh_api_is_mutating(tokens: list[str]) -> bool:
    """True when a `gh api` call writes: non-GET method, or a field/input flag.

    gh switches to POST as soon as a field flag is present, so `-f`/`--field`/
    `--raw-field`/`--input` imply mutation even with no explicit method.
    """
    if gh_api_method(tokens) not in GH_API_READ_METHODS:
        return True
    for tok in tokens[1:]:
        low = tok.lower()
        head = low.partition("=")[0]
        if head in GH_API_FIELD_FLAGS or low in GH_API_FIELD_FLAGS:
            return True
    return False


def gh_path(tokens: list[str]) -> tuple[str, ...]:
    """Positional subcommand path of a gh invocation, flags stripped."""
    return tuple(t.lower() for t in tokens[1:] if not t.startswith("-"))


def check_gh(tokens: list[str]) -> str | None:
    """Tier 1 for `gh`: enforced in every mode."""
    rest = gh_path(tokens)
    if len(rest) >= 2:
        # `secret set` is deliberately NOT here. Writing a secret is the one
        # credential operation that has a legitimate automated form: piping a
        # value straight from an authenticated provider CLI into `gh secret
        # set --body-file -`, so it never reaches a file, argv or shell
        # history. Denying it outright forced the value through a human
        # clipboard instead, which is strictly worse. It is tier 2 (ASK) --
        # see GH_MUTATE_SUBCOMMANDS. Deletion stays denied in every mode:
        # it destroys a credential and has no safe automated form.
        if rest[0] == "secret" and rest[1] in ("delete", "remove"):
            return "secret deletion"
        if rest[0] == "auth" and rest[1] in ("token", "refresh"):
            return "credential disclosure"
    if rest and rest[0] == "api" and gh_api_method(tokens) in GH_API_DENY_METHODS:
        return "destructive GitHub API call (DELETE)"
    return None


def classify_remote_mutation(tokens: list[str], flat: str, name: str) -> str | None:
    """Tier 2: writes to a remote that a careful operator would confirm."""
    low = flat.lower()

    for pattern, why in DEPLOY_PATTERNS:
        if re.search(pattern, low):
            return why

    if name == "git":
        rest = [t.lower() for t in tokens[1:] if not t.startswith("-")]
        flags = [t.lower() for t in tokens[1:] if t.startswith("-")]
        raw_flags = [t for t in tokens[1:] if t.startswith("-")]
        sub = rest[0] if rest else ""
        # --dry-run writes nothing; tier 1 has already denied force/delete.
        if sub == "push" and "--dry-run" not in flags and "-n" not in flags:
            return "push to a remote"
        # Reflog-recoverable history edits: confirmed remotely, silent locally.
        if sub == "rebase":
            return "rewriting local history (git rebase)"
        if sub == "branch" and ("-D" in raw_flags or {"--delete", "--force"} <= set(flags)):
            return "forced branch deletion"

    if name == "curl" and curl_is_write(tokens):
        # Configuring your own services through a provider REST API is normal
        # work at the laptop. Only DELETE is held at tier 1, since that is the
        # shape that removes a cloud resource.
        return "HTTP write via curl (provider API mutation)"

    if name == "gh":
        rest = gh_path(tokens)
        if rest and rest[0] == "api":
            if gh_api_is_mutating(tokens):
                return f"mutating GitHub API call ({gh_api_method(tokens).upper()})"
            return None
        for depth in (2, 1):
            if len(rest) >= depth and rest[:depth] in GH_MUTATE_SUBCOMMANDS:
                return GH_MUTATE_SUBCOMMANDS[rest[:depth]]

    return None


def classify_read_only(tokens: list[str], name: str) -> bool:
    """Tier 3: provably read-only, safe to run unattended in any mode.

    Deliberately narrow -- it exists to undo the `gh api` / `gh workflow`
    false positives, not to become a second allow-list.
    """
    if name != "gh":
        return False
    rest = gh_path(tokens)
    if not rest:
        return False
    if rest[0] == "api":
        return not gh_api_is_mutating(tokens)
    for depth in (2, 1):
        if len(rest) >= depth and rest[:depth] in GH_READ_SUBCOMMANDS:
            return True
    return False


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
    # Sending a DELETE at a provider API removes a cloud resource, which is on
    # the always-deny list in every mode. Every other curl method is tier 2.
    if name == "curl" and curl_method(tokens) == "delete":
        return "HTTP DELETE via curl (cloud resource deletion)"
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

        command = STREAM_REDIRECT.sub(" ", command)
        mode = payload.get("permission_mode") or ""

        ask_reason: str | None = None
        ask_segment = ""
        # Tier 3 is granted only if at least one segment is a read-only `gh`
        # call and no segment is anything else of substance.
        saw_read_only = False
        all_read_only = True

        for chunk in expand(command):
            for segment in SEGMENT_SPLIT.split(chunk):
                flat = segment.strip()
                if not flat:
                    continue

                # Tier 1 -- hard boundary, every mode, short-circuits.
                reason = evaluate(segment)
                if reason:
                    emit(
                        "deny",
                        f"Blocked by .claude/hooks/guard_indirect_exec.py: {reason}. "
                        f"Offending segment: {flat[:160]}",
                    )
                    return 0

                tokens = tokenize(flat)
                if not tokens:
                    continue
                name = binary_name(tokens[0])

                # Tier 2 -- remote mutation. Recorded, not emitted yet: a later
                # segment may still trip tier 1, which outranks it.
                if ask_reason is None:
                    mutation = classify_remote_mutation(tokens, flat, name)
                    if mutation:
                        ask_reason = mutation
                        ask_segment = flat

                # Tier 3 bookkeeping.
                if classify_read_only(tokens, name):
                    saw_read_only = True
                elif name in BENIGN_FILTERS:
                    pass  # neutral: neither grants nor blocks the allow
                else:
                    all_read_only = False
                if FILE_REDIRECT.search(flat):
                    all_read_only = False

        if ask_reason is not None:
            if is_bypass(mode):
                # Physically at the machine: routine remote writes proceed. The
                # tier-1 boundary above still applied, and still denied.
                return 0
            emit(
                "ask",
                f"Confirm before this runs: {ask_reason}. "
                f"Command: {ask_segment[:160]}",
            )
            return 0

        if saw_read_only and all_read_only:
            emit("allow", "Read-only GitHub inspection; no remote state is changed.")
            return 0
    except Exception as exc:  # never fail open
        emit("ask", f"Bash guard errored ({type(exc).__name__}); falling back to a prompt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
