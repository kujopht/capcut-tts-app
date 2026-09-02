#!/usr/bin/env python3
"""Adversarial matrix for the PreToolUse Bash guard.

Drives guard_indirect_exec.py the way Claude Code does -- a JSON payload on
stdin, including the real ``permission_mode`` field -- and asserts the decision
in BOTH operating modes:

  auto              phone / remote. Read-only inspection and routine
                    development run unattended; remote mutations ask.
  bypassPermissions physically at the laptop. Routine remote writes proceed
                    without a prompt; the hard boundary still denies.

Four expectations, matching the guard's three tiers:

  MUST_DENY        deny in both modes -- the boundary is not mode-dependent
  MUST_ASK_AUTO    ask in auto, silent in bypassPermissions
  MUST_ALLOW_READ  explicit "allow" in both modes (read-only inspection)
  MUST_RUN         silent in both modes -- normal permission flow, no prompt
                   from this guard

"silent" (the guard printing nothing) is tracked separately from an explicit
"allow": they mean different things to Claude Code, and conflating them is how
a read-only command ends up prompting anyway.

    python .claude/hooks/test_guard_indirect_exec.py

Exits non-zero on any mismatch so it can gate a commit.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "guard_indirect_exec.py")

AUTO = "auto"
BYPASS = "bypassPermissions"

# Denied in every mode, including bypassPermissions.
MUST_DENY = [
    ("python -c", 'python -c "import os; os.system(\'echo pwned\')"'),
    ("python3 -c", 'python3 -c "print(1)"'),
    ("py -c", 'py -c "print(1)"'),
    ("venv python -c", '.venv/Scripts/python.exe -c "print(1)"'),
    ("node -e", 'node -e "require(\'child_process\').exec(\'echo x\')"'),
    ("node --eval", 'node --eval "1+1"'),
    ("powershell -Command", 'powershell -Command "Get-Process"'),
    ("powershell -Comm prefix", 'powershell -Comm "Get-Process"'),
    ("powershell -EncodedCommand", "powershell -EncodedCommand ZQBjAGgAbwA="),
    ("powershell -enc prefix", "powershell -enc ZQBjAGgAbwA="),
    ("pwsh -c", 'pwsh -c "ls"'),
    ("cmd /c", "cmd /c echo hi"),
    ("cmd /k", "cmd /k dir"),
    ("nested $()", "echo $(echo $(rm -rf /tmp/x))"),
    ("substitution -> interpreter", 'echo "$(python -c \'print(1)\')"'),
    ("backtick", "echo `gh auth token`"),
    ("backtick -> rm", "echo `rm -rf /tmp/x`"),
    ("${} laundering", "echo ${rm -rf /tmp/x}"),
    ("chain via &&", "git status && rm -rf /tmp/x"),
    ("chain via ;", "ls ; schtasks /create /tn evil /tr calc"),
    ("chain via ||", "false || reg add HKLM\\\\Software\\\\Evil"),
    ("chain via pipe", "echo hi | xargs rm"),
    ("git reset --hard", "git reset --hard origin/main"),
    ("git clean -fd", "git clean -fd"),
    ("git filter-branch", "git filter-branch --tree-filter true HEAD"),
    ("git reflog expire", "git reflog expire --expire=now --all"),
    ("git update-ref -d", "git update-ref -d refs/heads/x"),
    ("git remote set-url", "git remote set-url origin https://evil"),
    ("force push --force", "git push --force origin main"),
    ("force push -f", "git push -f origin main"),
    ("force push +refspec", "git push origin +main:main"),
    ("push --delete", "git push --delete origin main"),
    ("push :refspec delete", "git push origin :branch"),
    ("force push bare", "git push --force"),
    ("force-with-lease", "git push --force-with-lease origin main"),
    ("push --delete branch literal", "git push --delete origin branch"),
    ("rm -rf", "rm -rf build"),
    ("rm -r", "rm -r build"),
    ("rm -f", "rm -f x.txt"),
    ("del /s", "del /s C:\\\\temp"),
    ("rmdir /s", "rmdir /s C:\\\\temp"),
    ("Remove-Item -Recurse", "Remove-Item build -Recurse -Force"),
    ("schtasks", "schtasks /create /tn evil /tr calc.exe"),
    ("reg add", "reg add HKCU\\\\Software\\\\Evil /v x /d y"),
    ("reg delete", "reg delete HKLM\\\\Software\\\\Good /f"),
    ("sc.exe", "sc.exe create evil binPath= C:\\\\evil.exe"),
    ("netsh", "netsh advfirewall set allprofiles state off"),
    ("Set-MpPreference", "Set-MpPreference -DisableRealtimeMonitoring $true"),
    ("Add-MpPreference", "Add-MpPreference -ExclusionPath C:\\\\"),
    ("New-NetFirewallRule", "New-NetFirewallRule -DisplayName evil -Action Allow"),
    ("Stop-Service", "Stop-Service WinDefend"),
    ("New-Service", "New-Service -Name evil -BinaryPathName C:\\\\evil.exe"),
    ("Register-ScheduledTask", "Register-ScheduledTask -TaskName evil -Action $a"),
    ("Set-ExecutionPolicy", "Set-ExecutionPolicy Bypass -Scope Process"),
    ("Set-ItemProperty HKLM", "Set-ItemProperty -Path HKLM:\\\\Software\\\\X -Name y -Value z"),
    ("Start-Process RunAs", "Start-Process powershell -Verb RunAs"),
    # Deleting a credential stays denied in every mode; writing one does not.
    ("curl -X DELETE", "curl -X DELETE https://api.example.com/v1/zones/z1"),
    ("curl --request DELETE", "curl --request DELETE https://api.example.com/x"),
    # curl file downloads (2026-09-02): denied unless https + GET + no
    # credentials/body + output confined to the Claude scratch tree. Every
    # way one of those four conditions can fail must still deny, in every
    # mode -- this is what replaced the old blanket settings.json deny.
    ("curl download plain http", 'curl -fsSL http://example.com/x -o "C:\\Users\\u\\AppData\\Local\\Temp\\claude\\proj\\sess\\scratchpad\\x"'),
    ("curl download outside scratch", 'curl -fsSL https://example.com/x -o "C:\\Users\\u\\Documents\\CapCut-TTS-App\\x"'),
    ("curl download into .claude", 'curl -fsSL https://example.com/x -o ".claude/hooks/x"'),
    ("curl download with Authorization header", 'curl -H "Authorization: Bearer t" https://example.com/x -o "C:\\Users\\u\\AppData\\Local\\Temp\\claude\\proj\\sess\\scratchpad\\x"'),
    ("curl download with cookie", 'curl -b "session=abc" https://example.com/x -o "C:\\Users\\u\\AppData\\Local\\Temp\\claude\\proj\\sess\\scratchpad\\x"'),
    ("curl download non-GET", 'curl -X POST https://example.com/x -o "C:\\Users\\u\\AppData\\Local\\Temp\\claude\\proj\\sess\\scratchpad\\x"'),
    ("curl download with body", 'curl -d "a=1" https://example.com/x -o "C:\\Users\\u\\AppData\\Local\\Temp\\claude\\proj\\sess\\scratchpad\\x"'),
    ("curl -O bare (CWD, not scratch)", 'curl -O https://example.com/x.webm'),
    ("curl --remote-name bare", 'curl --remote-name https://example.com/x.webm'),
    ("gh secret delete", "gh secret delete MY_TOKEN"),
    ("gh auth token", "gh auth token"),
    ("gh auth refresh", "gh auth refresh --scopes repo"),
    ("awk system()", "awk 'BEGIN{system(\"echo pwned\")}'"),
    ("xargs", "echo x | xargs echo"),
    ("eval", "eval echo hi"),
    ("runas", "runas /user:Administrator cmd"),
    ("sudo", "sudo rm -rf /"),
    ("guard deletion", "rm .claude/hooks/guard_indirect_exec.py"),
    ("guard overwrite via cp", "cp /tmp/fake.py .claude/hooks/guard_indirect_exec.py"),
    ("disableAllHooks", "echo disableAllHooks"),
    # gh api DELETE is destructive, not merely consequential.
    ("gh api -X DELETE", "gh api -X DELETE repos/o/r/issues/1"),
    ("gh api --method DELETE", "gh api --method DELETE repos/o/r/git/refs/heads/x"),
    ("gh api -XDELETE glued", "gh api -XDELETE repos/o/r/releases/9"),
    ("gh api --method=DELETE", "gh api --method=DELETE repos/o/r/labels/bug"),
    # A read-only gh call must not launder a destructive one beside it.
    ("read gh && rm -rf", "gh api repos/o/r && rm -rf build"),
    ("read gh -> force push", "gh pr view 1 && git push --force origin main"),
]

# Genuinely consequential remote mutations: ask in auto, silent in bypass.
MUST_ASK_AUTO = [
    ("gh pr create", 'gh pr create --title "x" --body "y" --base main'),
    ("gh pr merge", "gh pr merge 42 --squash"),
    ("gh pr close", "gh pr close 42"),
    ("gh pr review", "gh pr review 42 --approve"),
    ("gh workflow run", "gh workflow run ci.yml"),
    ("gh workflow disable", "gh workflow disable ci.yml"),
    ("gh run cancel", "gh run cancel 123"),
    ("gh run rerun", "gh run rerun 123"),
    ("gh run delete", "gh run delete 123"),
    ("gh release create", "gh release create v1.0.0"),
    ("gh issue create", 'gh issue create --title "bug"'),
    ("gh repo edit", "gh repo edit --visibility private"),
    ("gh variable set", "gh variable set FOO --body bar"),
    # Credential configuration: ask remotely, silent at the laptop.
    ("gh secret set stdin", "gh secret set MY_TOKEN --env production --body-file -"),
    ("gh secret set body", "gh secret set MY_TOKEN --env production --body xxx"),
    # Reflog-recoverable local history edits.
    ("git rebase", "git rebase -i main"),
    ("git branch -D", "git branch -D feat/x"),
    # Provider API configuration through curl.
    ("curl -X POST", "curl -X POST https://api.example.com/v1/tokens"),
    ("curl -d data", "curl -d '{\"a\":1}' https://api.example.com/v1/x"),
    ("curl --data", "curl --data-binary @- https://api.example.com/v1/x"),
    ("curl -F form", "curl -F file=@x.txt https://api.example.com/upload"),
    ("curl -T upload", "curl -T x.txt https://api.example.com/upload"),
    ("curl --request PUT", "curl --request PUT https://api.example.com/v1/x"),
    ("gh auth login", "gh auth login --hostname github.com"),
    ("gh api -X POST", "gh api -X POST repos/o/r/pulls -f title=x"),
    ("gh api --method PATCH", "gh api --method PATCH repos/o/r/issues/1 -f state=closed"),
    ("gh api -f implies POST", "gh api repos/o/r/issues -f title=bug"),
    ("gh api --input", "gh api repos/o/r/check-runs --input payload.json"),
    ("gh api --raw-field", "gh api repos/o/r/issues --raw-field title=x"),
    ("wrangler deploy", "npx wrangler deploy --config web/wrangler.jsonc"),
    ("wrangler rollback", "npx wrangler rollback --name fanfic-web"),
    ("wrangler versions deploy", "npx wrangler versions deploy --name fanfic-web"),
    ("npm run cf:deploy", "npm run cf:deploy:production"),
    ("opennext deploy", "npx opennextjs-cloudflare deploy"),
    ("wrangler login", "npx wrangler login"),
    ("curl render hook", "curl $RENDER_DEPLOY_HOOK"),
    ("curl deploy-hook", "curl https://example.com/deploy-hook/abc"),
    # Laundering an ask-tier command through substitution or a chain must still
    # reach the ask tier rather than slipping past on the read-only half.
    ("read gh then deploy", "gh api repos/o/r && npm run cf:deploy:production"),
]

# Provably read-only inspection: explicit allow, identical in both modes.
MUST_ALLOW_READ = [
    ("gh api GET default", "gh api repos/kujopht/capcut-tts-app/branches/main/protection"),
    ("gh api --method GET", "gh api --method GET repos/o/r/commits"),
    ("gh api -X GET", "gh api -X GET repos/o/r"),
    ("gh api with --jq", "gh api repos/o/r/contents/.github/workflows --jq '.[].name'"),
    ("gh api paginated", "gh api --paginate repos/o/r/issues"),
    ("gh workflow list", "gh workflow list --all"),
    ("gh workflow view", "gh workflow view ci.yml"),
    ("gh run list", "gh run list --limit 10"),
    ("gh run view", "gh run view 123 --log-failed"),
    ("gh pr view", "gh pr view 42"),
    ("gh pr checks", "gh pr checks 42"),
    ("gh pr list", "gh pr list --state all --base main"),
    ("gh pr diff", "gh pr diff 42"),
    ("gh repo view", "gh repo view kujopht/capcut-tts-app --json visibility"),
    ("gh release list", "gh release list"),
    ("gh release view", "gh release view v1.0.0"),
    ("gh auth status", "gh auth status"),
    ("gh issue list", "gh issue list --state open"),
    ("gh search", "gh search repos fanfic"),
    ("gh secret list", "gh secret list"),
    ("gh api piped to head", "gh api repos/o/r | head -3"),
    ("gh api piped to jq+grep", "gh api repos/o/r | jq . | grep name"),
    ("gh run list with 2>&1", "gh run list --limit 5 2>&1"),
]

# Routine work: the guard stays out of the way entirely, in both modes.
MUST_RUN = [
    ("git status", "git status --porcelain"),
    ("git diff", "git diff HEAD~1"),
    ("git log", "git log --oneline -10"),
    ("git branch -d", "git branch -d merged-branch"),
    ("git clean -n", "git clean -nd"),
    ("git add", "git add -A"),
    ("git commit", 'git commit -m "fix: handle rm -rf edge case"'),
    ("git push --dry-run", "git push --dry-run origin feat/x"),
    # Ordinary, non-destructive push - mission "COMBINED MISSION -- FULL
    # AUTOMATION PERMISSIONS" (2026-09-01) explicitly authorized removing
    # this from the ask tier; settings.json's own Bash(git push)/Bash(git
    # push *) allow rules make the actual permission decision now, this
    # guard just needs to stay out of the way. Every destructive shape
    # (--force/-f/--force-with-lease/--delete/+refspec) stays in MUST_DENY,
    # completely unaffected by this move.
    ("git push bare", "git push"),
    ("git push origin main literal", "git push origin main"),
    ("git push origin feature literal", "git push origin feature/foo"),
    ("git push plain", "git push origin feat/x"),
    ("git push -u", "git push -u origin feat/safe-remote-fanfic-ops"),
    ("git push tags", "git push origin --tags"),
    ("push inside $()", "echo $(git push origin main)"),
    ("read gh then push", "gh workflow list ; git push origin main"),
    ("git rev-parse in $()", 'cd "$(git rev-parse --show-toplevel)"'),
    ("git fetch", "git fetch --all --prune"),
    ("git merge local", "git merge --ff-only origin/main"),
    ("desktop tests", ".venv/Scripts/python.exe -m unittest discover -s tests -t ."),
    ("backend tests", ".venv/Scripts/python.exe -m unittest discover -s server/tests -t ."),
    ("compileall", ".venv/Scripts/python.exe -m compileall -q app.py desktop_app tests"),
    ("pip install -r", ".venv/Scripts/python.exe -m pip install -r server/requirements.txt"),
    ("pytest", "pytest server/tests -q"),
    ("npm test", "npm test"),
    ("npm run typecheck", "npm run typecheck"),
    ("npm run lint", "npm run lint"),
    ("npm run build", "npm run build"),
    ("npm run cf:build", "npm run cf:build"),
    ("npm ci", "npm ci"),
    ("npx tsc", "npx tsc --noEmit"),
    ("npx eslint", "npx eslint web/src"),
    ("wrangler deployments", "npx wrangler deployments list --name fanfic-web"),
    # Read-only curl must stay silent. `-f` is --fail and `-T`/`-F` are upload
    # flags, so a case-insensitive match would wrongly flag these as writes.
    ("curl -fsSL read", "curl -fsSL https://example.com/health"),
    ("curl -sS read", "curl -sS https://fas-prod-api.onrender.com/api/health"),
    ("curl -I head", "curl -I https://example.com"),
    ("curl -X GET explicit", "curl -X GET https://example.com/api"),
    # Safe download: https, GET, no credentials, output confined to the
    # Claude scratch tree -- must run without a prompt in either mode.
    ("curl safe download to scratch", 'curl -fsSL https://upload.wikimedia.org/x.webm -o "C:\\Users\\u\\AppData\\Local\\Temp\\claude\\proj\\sess\\scratchpad\\x.webm"'),
    ("ls", "ls -la web/src"),
    ("cat readme", "cat README.md"),
    ("grep", "grep -rn TODO server"),
    ("head", "head -20 docs/HANDOFF.md"),
    ("ruff", "ruff check desktop_app"),
    ("echo date substitution", 'echo "built at $(date)"'),
    ("reg query", "reg query HKCU\\\\Software\\\\Microsoft"),
    ("uvicorn", ".venv/Scripts/python.exe -m uvicorn server.main:app --port 8000"),
    # Read-only gh that writes a file is no longer purely read-only, so it must
    # fall through to the normal flow rather than collect a blanket allow.
    ("gh api redirected to file", "gh api repos/o/r > out.json"),
    ("gh api appended to file", "gh api repos/o/r >> out.json"),
]


def decide(command: str, mode: str) -> tuple[str, str]:
    payload = json.dumps(
        {
            "tool_name": "Bash",
            "permission_mode": mode,
            "tool_input": {"command": command},
        }
    )
    proc = subprocess.run(
        [sys.executable, GUARD],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        return "error", proc.stderr.strip()[:200]
    out = proc.stdout.strip()
    if not out:
        return "silent", ""
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return "error", f"non-JSON output: {out[:200]}"
    spec = data.get("hookSpecificOutput", {})
    return spec.get("permissionDecision", "?"), spec.get("permissionDecisionReason", "")


def run_half(title: str, cases, mode: str, expected: str, failures: list) -> None:
    print(f"\n{'=' * 78}\n{title} -- mode={mode}, expect={expected} ({len(cases)} cases)\n{'=' * 78}")
    for label, cmd in cases:
        decision, reason = decide(cmd, mode)
        ok = decision == expected
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:<28} -> {decision}")
        if not ok:
            failures.append((title, mode, label, cmd, decision, expected, reason))


def main() -> int:
    failures: list = []
    checks = 0

    # The boundary is identical in both modes -- that is the whole point.
    run_half("MUST DENY", MUST_DENY, AUTO, "deny", failures)
    run_half("MUST DENY", MUST_DENY, BYPASS, "deny", failures)
    checks += len(MUST_DENY) * 2

    run_half("MUST ASK", MUST_ASK_AUTO, AUTO, "ask", failures)
    run_half("MUST NOT ASK", MUST_ASK_AUTO, BYPASS, "silent", failures)
    checks += len(MUST_ASK_AUTO) * 2

    run_half("MUST ALLOW (read-only)", MUST_ALLOW_READ, AUTO, "allow", failures)
    run_half("MUST ALLOW (read-only)", MUST_ALLOW_READ, BYPASS, "allow", failures)
    checks += len(MUST_ALLOW_READ) * 2

    run_half("MUST RUN (no interference)", MUST_RUN, AUTO, "silent", failures)
    run_half("MUST RUN (no interference)", MUST_RUN, BYPASS, "silent", failures)
    checks += len(MUST_RUN) * 2

    print(f"\n{'=' * 78}")
    if failures:
        print(f"RESULT: {checks - len(failures)}/{checks} passed, {len(failures)} FAILED\n")
        for title, mode, label, cmd, decision, expected, reason in failures:
            print(
                f"  {title} [{mode}] {label}\n"
                f"    cmd      : {cmd}\n"
                f"    expected : {expected}\n"
                f"    got      : {decision}\n"
                f"    reason   : {reason}"
            )
        return 1
    print(f"RESULT: {checks}/{checks} passed (0 bypass, 0 broken, both modes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
