#!/usr/bin/env python3
"""Adversarial matrix for the PreToolUse Bash guard.

Drives guard_indirect_exec.py the way Claude Code does -- a JSON payload on
stdin -- and asserts the decision. Two halves that both matter: attacks that
must be denied, and everyday commands that must stay autonomous. A guard that
blocks everything passes the first half and fails the project.

    python .claude/hooks/test_guard_indirect_exec.py

Exits non-zero on the first mismatch category so it can gate a commit.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "guard_indirect_exec.py")

# (label, command) pairs the guard must refuse.
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
    ("git branch -D", "git branch -D feat/x"),
    ("git rebase", "git rebase -i main"),
    ("git filter-branch", "git filter-branch --tree-filter true HEAD"),
    ("git reflog expire", "git reflog expire --expire=now --all"),
    ("git update-ref -d", "git update-ref -d refs/heads/x"),
    ("git remote set-url", "git remote set-url origin https://evil"),
    ("force push --force", "git push --force origin main"),
    ("force push -f", "git push -f origin main"),
    ("force push +refspec", "git push origin +main:main"),
    ("push --delete", "git push --delete origin main"),
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
    ("gh secret set", "gh secret set MY_TOKEN --body xxx"),
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
]

# (label, command) pairs that must run without the guard interfering.
MUST_ALLOW = [
    ("git status", "git status --porcelain"),
    ("git diff", "git diff HEAD~1"),
    ("git log", "git log --oneline -10"),
    ("git branch -d", "git branch -d merged-branch"),
    ("git clean -n", "git clean -nd"),
    ("git add", "git add -A"),
    ("git commit", 'git commit -m "fix: handle rm -rf edge case"'),
    ("git push plain", "git push origin feat/x"),
    ("git rev-parse in $()", 'cd "$(git rev-parse --show-toplevel)"'),
    ("git fetch", "git fetch --all --prune"),
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
    ("ls", "ls -la web/src"),
    ("cat readme", "cat README.md"),
    ("grep", "grep -rn TODO server"),
    ("head", "head -20 docs/HANDOFF.md"),
    ("ruff", "ruff check desktop_app"),
    ("echo date substitution", 'echo "built at $(date)"'),
    ("reg query", "reg query HKCU\\\\Software\\\\Microsoft"),
    ("uvicorn", ".venv/Scripts/python.exe -m uvicorn server.main:app --port 8000"),
]


def decide(command: str) -> tuple[str, str]:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
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
        return "allow", ""
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return "error", f"non-JSON output: {out[:200]}"
    spec = data.get("hookSpecificOutput", {})
    return spec.get("permissionDecision", "?"), spec.get("permissionDecisionReason", "")


def main() -> int:
    failures = []

    print(f"{'=' * 78}\nMUST DENY ({len(MUST_DENY)} cases)\n{'=' * 78}")
    for label, cmd in MUST_DENY:
        decision, reason = decide(cmd)
        ok = decision == "deny"
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:<28} -> {decision}")
        if not ok:
            failures.append(("MUST_DENY", label, cmd, decision, reason))

    print(f"\n{'=' * 78}\nMUST ALLOW ({len(MUST_ALLOW)} cases)\n{'=' * 78}")
    for label, cmd in MUST_ALLOW:
        decision, reason = decide(cmd)
        ok = decision == "allow"
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:<28} -> {decision}")
        if not ok:
            failures.append(("MUST_ALLOW", label, cmd, decision, reason))

    total = len(MUST_DENY) + len(MUST_ALLOW)
    print(f"\n{'=' * 78}")
    if failures:
        print(f"RESULT: {total - len(failures)}/{total} passed, {len(failures)} FAILED\n")
        for half, label, cmd, decision, reason in failures:
            print(f"  {half} {label}\n    cmd      : {cmd}\n    got      : {decision}\n    reason   : {reason}")
        return 1
    print(f"RESULT: {total}/{total} passed (0 bypass, 0 broken)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
